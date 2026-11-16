"""Pure pre-flight validators for the Oracle Cloud signup guide (#277, S2).

No network calls and no OCI SDK: everything here checks the *shape* of what a user pastes.
Only non-secret values are accepted (tenancy OCID, region id); anything that looks like a
key, token or password is refused outright.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Regions that offer Always Free Autonomous AI Database 26ai (Oracle docs, checked 2026-11-16;
# the page says they are the only homes where vector search is free). uk-london-1 is the default.
DEFAULT_REGION = "uk-london-1"
ALWAYS_FREE_26AI_REGIONS: dict[str, str] = {
    "uk-london-1": "UK South (London)",
    "us-phoenix-1": "US West (Phoenix)",
    "us-ashburn-1": "US East (Ashburn)",
    "eu-paris-1": "France Central (Paris)",
    "ap-sydney-1": "Australia East (Sydney)",
    "ap-mumbai-1": "India West (Mumbai)",
    "ap-singapore-1": "Singapore",
    "ap-tokyo-1": "Japan East (Tokyo)",
}

_TENANCY_OCID = re.compile(r"^ocid1\.tenancy\.oc\d+\.\.[a-z0-9]{20,80}$")
_REGION_ID = re.compile(r"^[a-z]{2}-[a-z]+(?:-[a-z]+)?-\d{1,2}$")
_SECRET_SHAPES = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bocid1\.(?!tenancy\b)[a-z0-9_]+\.", re.IGNORECASE),
    re.compile(r"\b(?:password|passwd|secret|token|api[_ -]?key)\b\s*[:=]", re.IGNORECASE),
    re.compile(r"\b[0-9a-f]{2}(?::[0-9a-f]{2}){15}\b", re.IGNORECASE),  # key fingerprint
)

PAYG_STATES = ("none", "pending", "active")


@dataclass
class PreflightResult:
    """Outcome of validating one pasted value."""

    ok: bool
    value: str = ""
    error: str = ""
    warnings: list[str] = field(default_factory=list)


def looks_like_secret(text: str) -> bool:
    """True when ``text`` has the shape of a private key, token, password or user/key OCID."""
    return any(p.search(text) for p in _SECRET_SHAPES)


def _refuse_secret(raw: str) -> PreflightResult | None:
    if looks_like_secret(raw):
        return PreflightResult(
            ok=False,
            error=(
                "That looks like a key, token, password or credential identifier. "
                "Zebra never needs it here: paste only the tenancy OCID and region id."
            ),
        )
    return None


def validate_tenancy_ocid(raw: str) -> PreflightResult:
    """Check the shape ``ocid1.tenancy.oc1..<id>`` (an empty value is allowed: optional)."""
    value = (raw or "").strip()
    if not value:
        return PreflightResult(ok=True)
    if refused := _refuse_secret(value):
        return refused
    if not _TENANCY_OCID.match(value):
        return PreflightResult(
            ok=False,
            error="A tenancy OCID looks like ocid1.tenancy.oc1..aaaa (lowercase letters, digits).",
        )
    return PreflightResult(ok=True, value=value)


def validate_region(raw: str) -> PreflightResult:
    """Check a region id such as ``uk-london-1``; warn if it lacks Always Free 26ai."""
    value = (raw or "").strip().lower()
    if not value:
        return PreflightResult(ok=True)
    if refused := _refuse_secret(value):
        return refused
    if not _REGION_ID.match(value):
        return PreflightResult(
            ok=False, error="A region id looks like uk-london-1 (area-city-number)."
        )
    warnings = []
    if value not in ALWAYS_FREE_26AI_REGIONS:
        warnings.append(
            f"{value} is not in Oracle's list of regions with Always Free 26ai databases "
            "(no free vector search). The home region cannot be changed later."
        )
    elif value != DEFAULT_REGION:
        warnings.append(f"Zebra's default and tested region is {DEFAULT_REGION}.")
    return PreflightResult(ok=True, value=value, warnings=warnings)
