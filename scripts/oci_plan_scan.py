"""Scan a Terraform plan of the Zebra OCI stack against the Always Free allowlist (#279).

Reads the JSON from ``terraform show -json <plan>`` and checks every managed resource the
plan creates or keeps against ``deploy/oci/free_tier_allowlist.yaml``:

- a resource type not under ``resources`` fails (named ``denied`` types say why);
- each type's ``max_count``, ``require`` and ``max`` rules must hold, with values known at
  plan time;
- across the plan, Arm A1 OCPUs and memory and total block storage stay within ``limits``.

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
            elif actual != expected:
                errors.append(f"{address}: {path} must be {expected!r}, got {actual!r}")
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
            boot = _number(_lookup(after, "source_details.0.boot_volume_size_in_gbs"))
            storage += boot if boot is not None else limits.get("default_boot_volume_gb", 47)
        elif rtype == "oci_core_volume":
            storage += _number(after.get("size_in_gbs")) or 0

    for rtype, count in sorted(counts.items()):
        most = (resources.get(rtype) or {}).get("max_count")
        if most is not None and count > most:
            errors.append(f"{rtype}: {count} planned, Always Free allows {most}")

    for name, total, unit in (
        ("a1_ocpus", a1_ocpus, "OCPU"),
        ("a1_memory_gb", a1_memory, "GB A1 memory"),
        ("block_storage_gb", storage, "GB block storage"),
    ):
        if name in limits and total > limits[name]:
            errors.append(f"plan total: {total:g} {unit}, Always Free allows {limits[name]}")
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
