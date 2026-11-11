"""``deploy/podman/setup-tunnel.sh`` keeps the Commons relay routes (#231, #246).

Re-running the tunnel script used to drop the hand-added ``/commons`` and ``/sync`` ingress rules.
It now writes a relay's route whenever that relay's Quadlet is installed. ``--print-config``
renders the config with no sudo, network or ``cloudflared``, so it is tested here.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "deploy" / "podman" / "setup-tunnel.sh"
HOST = "zebra.example.com"


def _config(quadlet_dir: Path, **env: str) -> list[dict]:
    """The ingress rules ``--print-config`` renders, with ``quadlet_dir`` as the Quadlet dir."""
    run_env = {k: v for k, v in os.environ.items() if not k.startswith("ROUTE_")}
    run_env.update(QUADLET_DIR=str(quadlet_dir), **env)
    out = subprocess.run(
        ["bash", str(SCRIPT), "--print-config", HOST],
        env=run_env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    config = yaml.safe_load(out)
    assert config["tunnel"] == "<tunnel-id>"
    assert out.startswith("# Managed by deploy/podman/setup-tunnel.sh")
    return config["ingress"]


def _install(quadlet_dir: Path, *names: str) -> None:
    for name in names:
        (quadlet_dir / name).write_text("[Container]\n")


def _paths(ingress: list[dict]) -> list[str | None]:
    return [rule.get("path") for rule in ingress]


def test_without_relays_only_the_web_app_is_routed(tmp_path):
    ingress = _config(tmp_path)
    assert ingress == [
        {"hostname": HOST, "service": "http://127.0.0.1:8000"},
        {"service": "http_status:404"},
    ]


def test_installed_relays_get_their_routes_above_the_hostname_rule(tmp_path):
    _install(tmp_path, "zebra-commons-relay.container", "zebra-sync-relay.container")
    ingress = _config(tmp_path)
    assert ingress[:2] == [
        {"hostname": HOST, "path": "^/relay/commons$", "service": "http://127.0.0.1:7779"},
        {"hostname": HOST, "path": "^/relay/sync$", "service": "http://127.0.0.1:7778"},
    ]
    # cloudflared takes the first match, so the catch-all hostname rule must come after them.
    assert ingress[2:] == [
        {"hostname": HOST, "service": "http://127.0.0.1:8000"},
        {"service": "http_status:404"},
    ]


def test_each_relay_is_routed_on_its_own(tmp_path):
    _install(tmp_path, "zebra-sync-relay.container")
    assert _paths(_config(tmp_path)) == ["^/relay/sync$", None, None]


def test_overrides_beat_detection(tmp_path):
    _install(tmp_path, "zebra-commons-relay.container")
    assert _paths(_config(tmp_path, ROUTE_COMMONS="0", ROUTE_SYNC="1")) == [
        "^/relay/sync$",
        None,
        None,
    ]


def test_a_bad_override_fails_and_writes_nothing(tmp_path):
    result = subprocess.run(
        ["bash", str(SCRIPT), "--print-config", HOST],
        env={**os.environ, "QUADLET_DIR": str(tmp_path), "ROUTE_COMMONS": "yes"},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "expected 1 or 0" in result.stderr
    assert "ingress" not in result.stdout


@pytest.mark.parametrize(
    ("path", "relay"),
    [
        ("/relay/commons", True),
        ("/relay/sync", True),
        ("/relay/commons/", False),
        ("/relay/sync/x", False),
        ("/commons", False),
        ("/commons/", False),
        ("/commons/backup/", False),
        ("/sync", False),
    ],
)
def test_relay_paths_are_exact_so_the_web_pages_stay_on_django(tmp_path, path, relay):
    _install(tmp_path, "zebra-commons-relay.container", "zebra-sync-relay.container")
    patterns = [rule["path"] for rule in _config(tmp_path) if "path" in rule]
    assert any(re.search(p, path) for p in patterns) is relay
