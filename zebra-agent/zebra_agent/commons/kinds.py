"""The Zebra Commons event kinds: one table, fixed in S4 (#231).

Every Commons event is a NIP-01 event tagged ``["t","zebra-commons"]`` and ``["v","1"]``. Kind
numbers end in the slice that introduced them (228 identity, 229 export, 231 offers, ...);
addressable kinds sit in 30000-39999 (one current event per ``d`` value), regular kinds in
1000-9999. None clashes with a kind in the NIP registry. Changing a number is a protocol version
change (``v`` 2), never a local setting.

The relay write policies (``deploy/podman/*/write_policy.py``, standard library only, run inside
strfry) repeat these numbers; ``tests/test_commons_offer.py`` keeps them equal.
"""

from __future__ import annotations

DEVICE_CERT_KIND = 30228  # addressable, d = device pubkey, signed by the Zebra key (S1)
DEVICE_REVOKE_KIND = 1228  # regular, signed by the Zebra key (S1)
WORKFLOW_EXPORT_KIND = 31229  # a signed export file (S2b); never published to a relay
SKILL_KIND = 4236  # regular, private relay only, NIP-44 to one device (S3b)
RECEIPT_KIND = 1246  # regular, signed by a relay operator key (#246)
OFFER_KIND = 30231  # addressable, d = content sha256 (S4)
ATTEST_KIND = 1232  # regular, NIP-32 style label on a workflow hash (S5)
TRUST_KIND = 30233  # addressable, d = target Zebra pubkey (S6)
GRANT_KIND = 1234  # regular, vouch-and-stake (S7, parked)
TRADE_KIND = 1235  # regular, market buy / sell (S7, parked)
OUTCOME_KIND = 1236  # regular, outcome report (S7, parked)

#: Kinds a public Commons relay may carry. Anything else is refused by the client (hard filter).
PUBLIC_KINDS = frozenset(
    {
        OFFER_KIND,
        ATTEST_KIND,
        TRUST_KIND,
        GRANT_KIND,
        TRADE_KIND,
        OUTCOME_KIND,
        RECEIPT_KIND,
        DEVICE_CERT_KIND,
        DEVICE_REVOKE_KIND,
    }
)

#: Kinds the private sync relay carries (its write policy refuses the rest).
PRIVATE_KINDS = frozenset({SKILL_KIND, DEVICE_CERT_KIND, DEVICE_REVOKE_KIND, RECEIPT_KIND})

KIND_NAMES = {
    DEVICE_CERT_KIND: "DEVICE_CERT",
    DEVICE_REVOKE_KIND: "DEVICE_REVOKE",
    WORKFLOW_EXPORT_KIND: "WORKFLOW_EXPORT",
    SKILL_KIND: "SKILL",
    RECEIPT_KIND: "RECEIPT",
    OFFER_KIND: "OFFER",
    ATTEST_KIND: "ATTEST",
    TRUST_KIND: "TRUST",
    GRANT_KIND: "GRANT",
    TRADE_KIND: "TRADE",
    OUTCOME_KIND: "OUTCOME",
}


def kind_name(kind: int) -> str:
    """The Commons name of *kind* (e.g. ``OFFER``), or ``kind <n>``."""
    return KIND_NAMES.get(kind, f"kind {kind}")
