"""Tests for scripts/oci_plan_scan.py and the deploy/oci stack's Always Free guards (#279).

``fixtures/clean_plan.json`` is the stack's own plan (``scripts/oci_iac_check.sh
--keep-plan``, trimmed to ``resource_changes``). Each bad plan below breaks exactly one
allowlist rule, starting from the clean one; every bad plan must fail the scan.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
STACK = ROOT / "deploy" / "oci"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

_spec = importlib.util.spec_from_file_location("oci_plan_scan", ROOT / "scripts/oci_plan_scan.py")
oci_plan_scan = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oci_plan_scan)

Plan = dict[str, Any]


@pytest.fixture(scope="module")
def allowlist() -> dict[str, Any]:
    return oci_plan_scan.load_allowlist(STACK / "free_tier_allowlist.yaml")


@pytest.fixture
def clean_plan() -> Plan:
    return json.loads((FIXTURES / "clean_plan.json").read_text())


def _resource(plan: Plan, rtype: str) -> dict[str, Any]:
    return next(rc for rc in plan["resource_changes"] if rc["type"] == rtype)


def _after(plan: Plan, rtype: str) -> dict[str, Any]:
    return _resource(plan, rtype)["change"]["after"]


def _add(plan: Plan, rtype: str, after: dict[str, Any], name: str = "extra") -> None:
    plan["resource_changes"].append(
        {
            "address": f"{rtype}.{name}",
            "mode": "managed",
            "type": rtype,
            "name": name,
            "change": {"actions": ["create"], "after": after},
        }
    )


def _duplicate(plan: Plan, rtype: str) -> None:
    _add(plan, rtype, copy.deepcopy(_after(plan, rtype)), name="second")


def _set(rtype: str, path: str, value: Any) -> Callable[[Plan], None]:
    def mutate(plan: Plan) -> None:
        target: Any = _after(plan, rtype)
        *parents, last = path.split(".")
        for part in parents:
            target = target[int(part)] if part.isdigit() else target[part]
        target[last] = value

    return mutate


# One known-bad plan per rule: (rule id, mutation, text the failure must mention).
BAD_PLANS: list[tuple[str, Callable[[Plan], None], str]] = [
    (
        "unlisted_type",
        lambda p: _add(p, "oci_containerengine_cluster", {"name": "k8s"}),
        "not on the Always Free allowlist",
    ),
    (
        "paid_shape",
        _set("oci_core_instance", "shape", "VM.Standard.E5.Flex"),
        "shape must be 'VM.Standard.A1.Flex'",
    ),
    ("a1_ocpus_over_2", _set("oci_core_instance", "shape_config.0.ocpus", 4), "ocpus is 4"),
    (
        "a1_memory_over_12",
        _set("oci_core_instance", "shape_config.0.memory_in_gbs", 24),
        "memory_in_gbs is 24",
    ),
    ("second_instance", lambda p: _duplicate(p, "oci_core_instance"), "oci_core_instance: 2"),
    (
        "boot_volume_over_200",
        _set("oci_core_instance", "source_details.0.boot_volume_size_in_gbs", 250),
        "GB block storage",
    ),
    (
        "block_volume_over_total",
        lambda p: _add(p, "oci_core_volume", {"size_in_gbs": 150}),
        "250 GB block storage",
    ),
    (
        "adb_not_free_tier",
        _set("oci_database_autonomous_database", "is_free_tier", False),
        "is_free_tier must be True",
    ),
    (
        "adb_free_tier_unknown",
        lambda p: _after(p, "oci_database_autonomous_database").pop("is_free_tier"),
        "not set at plan time",
    ),
    (
        "second_adb",
        lambda p: _duplicate(p, "oci_database_autonomous_database"),
        "oci_database_autonomous_database: 2",
    ),
    (
        "private_vault",
        _set("oci_kms_vault", "vault_type", "VIRTUAL_PRIVATE"),
        "vault_type must be 'DEFAULT'",
    ),
    (
        "hsm_key",
        _set("oci_kms_key", "protection_mode", "HSM"),
        "protection_mode must be 'SOFTWARE'",
    ),
    (
        "reserved_ip",
        lambda p: _add(p, "oci_core_public_ip", {"lifetime": "RESERVED"}),
        "lifetime must be 'EPHEMERAL'",
    ),
    (
        "load_balancer",
        lambda p: _add(p, "oci_load_balancer_load_balancer", {"shape": "flexible"}),
        "load balancer",
    ),
    (
        "network_load_balancer",
        lambda p: _add(p, "oci_network_load_balancer_network_load_balancer", {}),
        "network load balancer",
    ),
    ("nat_gateway", lambda p: _add(p, "oci_core_nat_gateway", {}), "NAT gateway"),
    ("drg", lambda p: _add(p, "oci_core_drg", {}), "dynamic routing gateway"),
    (
        "archive_bucket",
        _set("oci_objectstorage_bucket", "storage_tier", "Archive"),
        "storage_tier must be 'Standard'",
    ),
]


def test_clean_plan_passes(clean_plan: Plan, allowlist: dict[str, Any]) -> None:
    assert oci_plan_scan.scan(clean_plan, allowlist) == []


@pytest.mark.parametrize(
    ("rule", "mutate", "expected"), BAD_PLANS, ids=[rule for rule, _, _ in BAD_PLANS]
)
def test_bad_plan_fails(
    rule: str,
    mutate: Callable[[Plan], None],
    expected: str,
    clean_plan: Plan,
    allowlist: dict[str, Any],
) -> None:
    mutate(clean_plan)
    errors = oci_plan_scan.scan(clean_plan, allowlist)
    assert errors, f"bad plan {rule!r} passed the scan"
    assert any(expected in e for e in errors), errors


def test_clean_plan_counts_the_real_boot_volume(clean_plan: Plan, allowlist: dict) -> None:
    """The provider plans boot_volume_size_in_gbs as a string; it must still count."""
    _add(clean_plan, "oci_core_volume", {"size_in_gbs": 101})  # 100 boot + 101 > 200
    assert any("201 GB block storage" in e for e in oci_plan_scan.scan(clean_plan, allowlist))


def test_deleted_resources_are_ignored(clean_plan: Plan, allowlist: dict[str, Any]) -> None:
    _add(clean_plan, "oci_core_nat_gateway", {})
    clean_plan["resource_changes"][-1]["change"]["actions"] = ["delete"]
    assert oci_plan_scan.scan(clean_plan, allowlist) == []


def test_cli_exit_codes(tmp_path: Path, clean_plan: Plan, capsys: pytest.CaptureFixture) -> None:
    good = tmp_path / "good.json"
    good.write_text(json.dumps(clean_plan))
    assert oci_plan_scan.main([str(good)]) == 0

    _set("oci_kms_key", "protection_mode", "HSM")(clean_plan)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(clean_plan))
    assert oci_plan_scan.main([str(bad)]) == 1
    assert "FAIL" in capsys.readouterr().out

    junk = tmp_path / "junk.json"
    junk.write_text("{}")
    assert oci_plan_scan.main([str(junk)]) == 2


def test_clean_fixture_covers_every_stack_resource(clean_plan: Plan) -> None:
    """The fixture must stay a snapshot of the real stack, not drift into a toy."""
    declared = set(re.findall(r'^resource "(\w+)" "(\w+)"', _tf_source(), re.MULTILINE))
    planned = {
        (rc["type"], rc["name"]) for rc in clean_plan["resource_changes"] if rc["mode"] == "managed"
    }
    assert planned == declared


# --- Stack guards: no variable reaches a paid resource; the form matches the variables. ---

ALLOWED_VARIABLES = {
    "tenancy_ocid",
    "region",
    "compartment_ocid",
    "ssh_public_key",
    "domain",
    "release_channel",
}


def _tf_source() -> str:
    return "\n".join(p.read_text() for p in sorted(STACK.glob("*.tf")))


def _variables() -> set[str]:
    return set(re.findall(r'^variable "(\w+)"', _tf_source(), re.MULTILINE))


def test_only_approved_variables() -> None:
    """Adding a variable (e.g. shape or size) must be a deliberate, reviewed change."""
    assert _variables() == ALLOWED_VARIABLES


def test_schema_lists_every_variable() -> None:
    schema = yaml.safe_load((STACK / "schema.yaml").read_text())
    assert set(schema["variables"]) == _variables()
    grouped = {v for group in schema["variableGroups"] for v in group["variables"]}
    assert grouped == _variables()
    assert schema["variables"]["region"]["default"] == "uk-london-1"


def test_locals_match_allowlist_limits(allowlist: dict[str, Any]) -> None:
    source = _tf_source()

    def local(name: str) -> str:
        match = re.search(rf"^\s*{name}\s*=\s*(\S+)", source, re.MULTILINE)
        assert match, f"local {name} missing"
        return match.group(1).strip('"')

    limits = allowlist["limits"]
    assert int(local("a1_ocpus")) <= limits["a1_ocpus"]
    assert int(local("a1_memory_gb")) <= limits["a1_memory_gb"]
    assert int(local("boot_volume_gb")) <= limits["block_storage_gb"]
    assert local("a1_shape") == "VM.Standard.A1.Flex"
    assert local("adb_free_tier") == "true"
    assert local("vault_type") == "DEFAULT"
    assert local("key_protection_mode") == "SOFTWARE"
