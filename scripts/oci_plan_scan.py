"""Scan a Terraform plan of the Zebra OCI stack against the Always Free allowlist (#279).

Reads the JSON from ``terraform show -json <plan>`` and checks every managed resource the
plan creates or keeps against ``deploy/oci/free_tier_allowlist.yaml``:

- a resource type not under ``resources`` fails (named ``denied`` types say why);
- each type's ``max_count``, ``require``, ``max``, ``one_of`` and ``nonempty`` rules must hold,
  with values known at plan time;
- across the plan, Arm A1 OCPUs and memory and total block storage stay within ``limits``; a
  boot-volume size unknown at plan time fails rather than being guessed (#298);
- the billing guardrails (``guardrails``) are all planned or none, and every budget gets exactly
  the listed alert rules.

Exit 0 when the plan is clean, 1 when it breaks a rule, 2 on bad input.

Usage: uv run python scripts/oci_plan_scan.py plan.json [--allowlist path]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

DEFAULT_ALLOWLIST = Path(__file__).resolve().parent.parent / "deploy/oci/free_tier_allowlist.yaml"
A1_SHAPE = "VM.Standard.A1.Flex"
_MISSING = object()


def load_allowlist(path: Path) -> dict[str, Any]:
    """Load and minimally validate the allowlist YAML."""
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("resources"), dict):
        raise ValueError(f"{path}: allowlist needs a 'resources' mapping")
    data.setdefault("denied", {})
    data.setdefault("limits", {})
    data.setdefault("guardrails", {})
    return data


def _lookup(values: Any, path: str) -> Any:
    """Follow a dotted path (numbers index lists) through planned values."""
    current = values
    for part in path.split("."):
        if isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


def _is_unknown(rc: dict[str, Any], path: str) -> bool:
    """True when ``after_unknown`` marks the value, or a parent of it, as known only after apply."""
    current = rc.get("change", {}).get("after_unknown")
    for part in path.split("."):
        if current is True:
            return True
        if isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False
    return current is True


def _planned(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Managed resources that will exist after the plan is applied."""
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        raise ValueError("plan has no resource_changes list (is it `terraform show -json` output?)")
    return [
        rc
        for rc in changes
        if rc.get("mode") == "managed" and rc.get("change", {}).get("actions") != ["delete"]
    ]


def _number(value: Any) -> float | None:
    """A planned number; the oci provider types some sizes as strings ("100")."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def scan(plan: dict[str, Any], allowlist: dict[str, Any]) -> list[str]:
    """Return one message per broken rule; an empty list means the plan is Always Free."""
    resources: dict[str, dict[str, Any]] = allowlist["resources"]
    denied: dict[str, str] = allowlist["denied"]
    limits: dict[str, Any] = allowlist["limits"]
    errors: list[str] = []
    counts: Counter[str] = Counter()
    a1_ocpus = a1_memory = storage = 0.0
    alert_rules: list[dict[str, Any]] = []

    for rc in _planned(plan):
        rtype, address = rc.get("type", "?"), rc.get("address", "?")
        after = rc.get("change", {}).get("after") or {}
        counts[rtype] += 1

        if rtype in denied:
            errors.append(f"{address}: {rtype} is not allowed: {denied[rtype]}")
            continue
        rules = resources.get(rtype)
        if rules is None:
            errors.append(f"{address}: {rtype} is not on the Always Free allowlist")
            continue

        for path, expected in (rules.get("require") or {}).items():
            actual = _lookup(after, path)
            if actual is _MISSING or actual is None:
                errors.append(f"{address}: {path} must be {expected!r} but is not set at plan time")
            elif isinstance(expected, list) and isinstance(actual, list) and actual != expected:
                missing = [item for item in expected if item not in actual]
                extra = [item for item in actual if item not in expected]
                errors.append(
                    f"{address}: {path} must be exactly the {len(expected)} listed values in order"
                    f"; missing {missing}, unexpected {extra}"
                )
            elif actual != expected:
                errors.append(f"{address}: {path} must be {expected!r}, got {actual!r}")
        for path, allowed in (rules.get("one_of") or {}).items():
            actual = _lookup(after, path)
            if actual is _MISSING or actual is None:
                errors.append(f"{address}: {path} must be one of {allowed} but is not set")
            elif actual not in allowed:
                errors.append(f"{address}: {path} must be one of {allowed}, got {actual!r}")
        for path in rules.get("nonempty") or []:
            actual = _lookup(after, path)
            if actual is _MISSING or actual is None or actual == "" or actual == []:
                errors.append(f"{address}: {path} must be set at plan time")
        for path, ceiling in (rules.get("max") or {}).items():
            actual = _number(_lookup(after, path))
            if actual is None:
                errors.append(f"{address}: {path} must be a number <= {ceiling}, not set")
            elif actual > ceiling:
                errors.append(f"{address}: {path} is {actual:g}, Always Free allows {ceiling}")

        if rtype == "oci_core_instance":
            if after.get("shape") == A1_SHAPE:
                a1_ocpus += _number(_lookup(after, "shape_config.0.ocpus")) or 0
                a1_memory += _number(_lookup(after, "shape_config.0.memory_in_gbs")) or 0
            boot_path = "source_details.0.boot_volume_size_in_gbs"
            raw = _lookup(after, boot_path)
            if raw is None and not _is_unknown(rc, boot_path):
                storage += limits.get("default_boot_volume_gb", 47)  # omitted: OCI's default
            elif raw is _MISSING or _is_unknown(rc, boot_path) or _number(raw) is None:
                # Unknown until apply: it could resolve above the free limit, so fail closed.
                errors.append(
                    f"{address}: {boot_path} is unknown at plan time; "
                    "set it so the block storage limit can be checked"
                )
            else:
                storage += _number(raw)
        elif rtype == "oci_budget_alert_rule":
            alert_rules.append(after)
        elif rtype == "oci_core_volume":
            storage += _number(after.get("size_in_gbs")) or 0

    for rtype, count in sorted(counts.items()):
        most = (resources.get(rtype) or {}).get("max_count")
        if most is not None and count > most:
            errors.append(f"{rtype}: {count} planned, the allowlist allows {most}")

    for name, total, unit in (
        ("a1_ocpus", a1_ocpus, "OCPU"),
        ("a1_memory_gb", a1_memory, "GB A1 memory"),
        ("block_storage_gb", storage, "GB block storage"),
    ):
        if name in limits and total > limits[name]:
            errors.append(f"plan total: {total:g} {unit}, Always Free allows {limits[name]}")
    errors.extend(_guardrail_errors(allowlist.get("guardrails") or {}, counts, alert_rules))
    return errors


def _alert_key(rule: dict[str, Any]) -> tuple[Any, Any, float | None]:
    return (rule.get("type"), rule.get("threshold_type"), _number(rule.get("threshold")))


def _guardrail_errors(
    guardrails: dict[str, Any], counts: Counter[str], alert_rules: list[dict[str, Any]]
) -> list[str]:
    """Guardrails are all planned or none, and each budget has exactly the listed alerts."""
    errors: list[str] = []
    expected_counts: dict[str, int] = guardrails.get("all_or_none") or {}
    if any(counts[rtype] for rtype in expected_counts):
        for rtype, want in sorted(expected_counts.items()):
            if counts[rtype] != want:
                errors.append(
                    f"guardrails: {counts[rtype]} {rtype} planned, need exactly {want} "
                    "(guardrails are all or none)"
                )
    per_budget = guardrails.get("alert_rules_per_budget")
    if per_budget is not None:
        budgets = counts["oci_budget_budget"]
        want = Counter(_alert_key(rule) for rule in per_budget for _ in range(budgets))
        got = Counter(_alert_key(rule) for rule in alert_rules)
        for key in sorted(set(want) | set(got), key=repr):
            if want[key] != got[key]:
                kind, threshold_type, threshold = key
                errors.append(
                    f"guardrails: {got[key]} alert rule(s) {kind} {threshold_type} {threshold:g} "
                    f"planned, need {want[key]} ({len(per_budget)} per budget)"
                    if threshold is not None
                    else f"guardrails: alert rule {kind} {threshold_type} has no threshold"
                )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan", type=Path, help="output of `terraform show -json <plan>`")
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    args = parser.parse_args(argv)
    try:
        plan = json.loads(args.plan.read_text())
        allowlist = load_allowlist(args.allowlist)
        errors = scan(plan, allowlist)
        total = len(_planned(plan))
    except (OSError, ValueError) as exc:
        print(f"oci_plan_scan: {exc}", file=sys.stderr)
        return 2
    if errors:
        print(f"FAIL: the plan leaves the OCI Always Free tier ({len(errors)} problem(s)):")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"OK: {total} planned resources, all on the Always Free allowlist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
