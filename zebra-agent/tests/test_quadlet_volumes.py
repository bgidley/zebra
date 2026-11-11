"""Both prod containers see the same Commons keys and workflow library (#228).

The daemon publishes to the Commons relays, runs the dream cycle's Commons step and skill sync,
all signed with this deployment's device key. Without the key volume it found no device key and
quietly stayed off, or could have made a second device key that dies with the container.
"""

import configparser
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
QUADLET_DIR = REPO / "deploy" / "podman" / "quadlet"
CONTAINERS = ("zebra-web.container", "zebra-daemon.container")


def _volumes(name: str) -> dict[str, str]:
    """``{volume: mount point}`` of a Quadlet's ``Volume=`` lines."""
    volumes = {}
    for line in (QUADLET_DIR / name).read_text().splitlines():
        if line.startswith("Volume="):
            source, target = line.removeprefix("Volume=").split(":")[:2]
            volumes[source] = target
    return volumes


@pytest.mark.parametrize("name", CONTAINERS)
def test_quadlet_parses(name):
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read_string((QUADLET_DIR / name).read_text().replace("%", "%%"))
    assert parser["Container"]["Image"] == "localhost/zebra-web:prod"


@pytest.mark.parametrize(
    ("volume", "target"),
    [
        ("zebra-commons-keys", "/root/.zebra-agent/commons-keys"),
        ("zebra-workflows", "/root/.zebra/workflows"),
    ],
)
def test_web_and_daemon_share_the_volume(volume, target):
    for name in CONTAINERS:
        assert _volumes(name).get(volume) == target, f"{name} must mount {volume} at {target}"


def test_key_mount_is_the_default_key_dir_of_root():
    """The containers run as root and set no ``ZEBRA_COMMONS_KEY_DIR``: the default
    ``~/.zebra-agent/commons-keys`` (settings.py) must be the mount point."""
    settings_py = REPO / "zebra-agent-web" / "zebra_agent_web" / "settings.py"
    assert '"ZEBRA_COMMONS_KEY_DIR", "~/.zebra-agent/commons-keys"' in settings_py.read_text()
    for name in CONTAINERS:
        assert "ZEBRA_COMMONS_KEY_DIR" not in (QUADLET_DIR / name).read_text()
