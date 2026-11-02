"""secp256k1 keys, BIP-340 Schnorr signatures and NIP-19 bech32 encoding.

The only module that imports the secp256k1 library (``btclib-secp256k1``, bindings to
bitcoin-core's libsecp256k1), so it can be swapped in one place. Keys are handled as
lowercase hex strings, as Nostr does: a 32-byte secret key and a 32-byte x-only public key.
"""

from __future__ import annotations

import secrets

from btclib_secp256k1 import keys as _keys
from btclib_secp256k1 import ssa as _ssa
from btclib_secp256k1 import xonly as _xonly


class InvalidKeyError(ValueError):
    """A key, signature or bech32 string is malformed."""


def generate_secret_key() -> str:
    """Return a fresh random secret key as 64 hex characters."""
    while True:
        candidate = secrets.token_bytes(32)
        if _keys.prvkey_verify(candidate):
            return candidate.hex()


def _secret_bytes(secret_hex: str) -> bytes:
    try:
        raw = bytes.fromhex(secret_hex)
    except (ValueError, TypeError) as exc:
        raise InvalidKeyError("secret key is not hex") from exc
    if len(raw) != 32 or not _keys.prvkey_verify(raw):
        raise InvalidKeyError("secret key is not a valid secp256k1 scalar")
    return raw


def public_key(secret_hex: str) -> str:
    """Return the x-only public key (64 hex) of a secret key."""
    xonly, _parity = _xonly.from_prvkey(_secret_bytes(secret_hex))
    return xonly.hex()


def is_valid_public_key(pubkey_hex: str) -> bool:
    """True if ``pubkey_hex`` is a 32-byte x-only key on the curve."""
    try:
        raw = bytes.fromhex(pubkey_hex)
    except (ValueError, TypeError):
        return False
    if len(raw) != 32:
        return False
    try:
        _xonly.parse(raw)
    except (ValueError, RuntimeError):
        return False
    return True


def sign(secret_hex: str, message32: bytes) -> str:
    """BIP-340 sign a 32-byte message; returns the 64-byte signature as hex."""
    if len(message32) != 32:
        raise InvalidKeyError("message must be 32 bytes")
    return _ssa.sign(message32, _secret_bytes(secret_hex)).hex()


def verify(pubkey_hex: str, message32: bytes, signature_hex: str) -> bool:
    """BIP-340 verify. Malformed keys or signatures verify as False, never raise."""
    try:
        pub = bytes.fromhex(pubkey_hex)
        sig = bytes.fromhex(signature_hex)
    except (ValueError, TypeError):
        return False
    if len(pub) != 32 or len(sig) != 64 or len(message32) != 32:
        return False
    try:
        return _ssa.verify(message32, pub, sig)
    except (ValueError, RuntimeError):
        return False


# ---------------------------------------------------------------------------
# Bech32 (BIP-173 reference implementation) for NIP-19 npub / nsec
# ---------------------------------------------------------------------------

_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_GEN = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)


def _polymod(values: list[int]) -> int:
    chk = 1
    for value in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ value
        for i in range(5):
            chk ^= _GEN[i] if ((top >> i) & 1) else 0
    return chk


def _hrp_expand(hrp: str) -> list[int]:
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _convertbits(data: bytes | list[int], frombits: int, tobits: int, pad: bool) -> list[int]:
    acc = 0
    bits = 0
    ret: list[int] = []
    maxv = (1 << tobits) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            raise InvalidKeyError("invalid bech32 data")
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        raise InvalidKeyError("invalid bech32 padding")
    return ret


def bech32_encode(hrp: str, data: bytes) -> str:
    """Encode bytes as bech32 with human-readable part ``hrp``."""
    five = _convertbits(data, 8, 5, True)
    polymod = _polymod(_hrp_expand(hrp) + five + [0] * 6) ^ 1
    checksum = [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(_CHARSET[d] for d in five + checksum)


def bech32_decode(text: str, expected_hrp: str) -> bytes:
    """Decode a bech32 string, checking its checksum and human-readable part."""
    text = (text or "").strip()
    if text.lower() != text and text.upper() != text:
        raise InvalidKeyError("mixed-case bech32")
    text = text.lower()
    pos = text.rfind("1")
    if pos < 1 or pos + 7 > len(text) or len(text) > 200:
        raise InvalidKeyError("not a bech32 string")
    hrp, rest = text[:pos], text[pos + 1 :]
    if hrp != expected_hrp:
        raise InvalidKeyError(f"expected {expected_hrp}, got {hrp}")
    if any(c not in _CHARSET for c in rest):
        raise InvalidKeyError("invalid bech32 character")
    values = [_CHARSET.find(c) for c in rest]
    if _polymod(_hrp_expand(hrp) + values) != 1:
        raise InvalidKeyError("bad bech32 checksum")
    return bytes(_convertbits(values[:-6], 5, 8, False))


def npub_encode(pubkey_hex: str) -> str:
    """NIP-19 ``npub`` for a public key."""
    return bech32_encode("npub", bytes.fromhex(pubkey_hex))


def npub_decode(npub: str) -> str:
    """Return the hex public key of an ``npub``; raises ``InvalidKeyError``."""
    raw = bech32_decode(npub, "npub")
    if len(raw) != 32 or not is_valid_public_key(raw.hex()):
        raise InvalidKeyError("npub does not hold a valid public key")
    return raw.hex()


def nsec_encode(secret_hex: str) -> str:
    """NIP-19 ``nsec`` for a secret key. The result is a secret: never log it."""
    return bech32_encode("nsec", _secret_bytes(secret_hex))


def nsec_decode(nsec: str) -> str:
    """Return the hex secret key of an ``nsec``; raises ``InvalidKeyError``."""
    raw = bech32_decode(nsec, "nsec")
    if len(raw) != 32:
        raise InvalidKeyError("nsec does not hold a 32-byte key")
    return _secret_bytes(raw.hex()).hex()
