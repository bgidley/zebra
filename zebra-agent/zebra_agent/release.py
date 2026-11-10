"""Release manifests: schema v1 validation and signature checks (#283).

A release manifest tells an instance what a release is: its version, the image digest to pull,
the oldest version it can update from, whether it is breaking (contracting migrations) or a
security release, and which versions it makes unsupported. One is published per release
(``releases/vX.Y.Z.json``) and copied, with its ``channel`` set, to each channel it is on
(``channels/next.json``, ``channels/stable.json``). Each file is signed with the project's
cosign key (``cosign sign-blob``); the signature sits next to it as ``<file>.sig``.

The validator and verifier are shared by the release CI (``scripts/release_manifest.py``) and,
later, the instance updater (#280). Signatures are cosign's format: base64 of a DER ECDSA
signature over SHA-256 of the exact file bytes, checked against the PEM public key from
``cosign generate-key-pair``, so ``cosign verify-blob`` and :func:`verify_blob` agree.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from datetime import datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

SCHEMA_VERSION = 1
CHANNELS = ("stable", "next", "test")
REQUIRED_PLATFORM = "linux/arm64"

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_IMAGE = re.compile(r"^[a-z0-9.-]+(?::\d+)?/[a-z0-9._/-]+@(sha256:[0-9a-f]{64})$")
_PLATFORM = re.compile(r"^[a-z0-9]+/[a-z0-9]+(?:/[a-z0-9]+)?$")
_MIGRATION = re.compile(r"^[a-z_][a-z0-9_]*\.[0-9]{4}_[A-Za-z0-9_]+$")

FIELDS: dict[str, str] = {
    "schema": "manifest schema version, always 1",
    "version": "release version X.Y.Z",
    "channel": "stable, next or test",
    "image": "registry/repo@sha256:<digest>: pull by digest, never by tag",
    "digest": "sha256:<hex>, the same digest as in image",
    "platforms": "OS/arch list; must include linux/arm64",
    "min_from": "oldest version that may update straight to this one",
    "breaking": "true when contracting migrations ship: manual approval, restore on rollback",
    "migrations": "{expand: [...], contract: [...]} as app.0001_name",
    "notes_url": "https URL of the release notes, or empty",
    "notes_md": "release notes in Markdown",
    "security": "true for a security release",
    "unsupported_below": "versions below this are unsupported (X.Y.Z), or null",
    "published_at": "UTC ISO 8601 time, e.g. 2026-11-09T12:00:00Z",
}


class ManifestError(ValueError):
    """A manifest is invalid or its signature does not verify."""


def parse_version(text: str) -> tuple[int, int, int]:
    """Parse ``X.Y.Z`` (an optional leading ``v`` is allowed) into a comparable tuple."""
    match = _SEMVER.match(text[1:] if text.startswith("v") else text)
    if not match:
        raise ManifestError(f"not a version X.Y.Z: {text!r}")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def _version_errors(manifest: dict, key: str, optional: bool = False) -> list[str]:
    value = manifest.get(key)
    if value is None and optional:
        return []
    if not isinstance(value, str) or not _SEMVER.match(value):
        return [f"{key}: expected X.Y.Z, got {value!r}"]
    return []


def manifest_errors(manifest: Any) -> list[str]:
    """Every way ``manifest`` breaks schema v1; empty when it is valid."""
    if not isinstance(manifest, dict):
        return ["manifest must be a JSON object"]
    errors = [f"{key}: missing" for key in FIELDS if key not in manifest]
    errors += [f"{key}: unknown field" for key in manifest if key not in FIELDS]
    if errors:
        return errors

    if manifest["schema"] != SCHEMA_VERSION or isinstance(manifest["schema"], bool):
        errors.append(f"schema: expected {SCHEMA_VERSION}, got {manifest['schema']!r}")
    errors += _version_errors(manifest, "version")
    errors += _version_errors(manifest, "min_from")
    errors += _version_errors(manifest, "unsupported_below", optional=True)
    if manifest["channel"] not in CHANNELS:
        errors.append(f"channel: expected one of {', '.join(CHANNELS)}")

    image, digest = manifest["image"], manifest["digest"]
    match = _IMAGE.match(image) if isinstance(image, str) else None
    if not match:
        errors.append("image: expected registry/repo@sha256:<64 hex>")
    if not isinstance(digest, str) or not _DIGEST.match(digest):
        errors.append("digest: expected sha256:<64 hex>")
    elif match and match.group(1) != digest:
        errors.append("digest: does not match the image digest")

    platforms = manifest["platforms"]
    if (
        not isinstance(platforms, list)
        or not all(isinstance(p, str) and _PLATFORM.match(p) for p in platforms)
        or REQUIRED_PLATFORM not in platforms
    ):
        errors.append(f"platforms: expected a list of os/arch including {REQUIRED_PLATFORM}")

    for key in ("breaking", "security"):
        if not isinstance(manifest[key], bool):
            errors.append(f"{key}: expected true or false")

    migrations = manifest["migrations"]
    if not isinstance(migrations, dict) or set(migrations) != {"expand", "contract"}:
        errors.append("migrations: expected {expand: [...], contract: [...]}")
    else:
        for kind in ("expand", "contract"):
            names = migrations[kind]
            if not isinstance(names, list) or not all(
                isinstance(n, str) and _MIGRATION.match(n) for n in names
            ):
                errors.append(f"migrations.{kind}: expected names like app.0001_initial")
        if migrations.get("contract") and manifest["breaking"] is not True:
            errors.append("breaking: must be true when contract migrations ship")

    notes_url = manifest["notes_url"]
    if not isinstance(notes_url, str) or (notes_url and not notes_url.startswith("https://")):
        errors.append("notes_url: expected an https URL or empty")
    if not isinstance(manifest["notes_md"], str):
        errors.append("notes_md: expected a string")

    published = manifest["published_at"]
    try:
        if not isinstance(published, str) or not published.endswith("Z"):
            raise ValueError
        datetime.fromisoformat(published[:-1] + "+00:00")
    except ValueError:
        errors.append("published_at: expected UTC ISO 8601 ending in Z")

    if not errors:
        version = parse_version(manifest["version"])
        if parse_version(manifest["min_from"]) > version:
            errors.append("min_from: above version")
        below = manifest["unsupported_below"]
        if below is not None and parse_version(below) > version:
            errors.append("unsupported_below: above version")
    return errors


def validate_manifest(manifest: Any) -> dict:
    """Return ``manifest`` if it is valid schema v1, else raise ManifestError listing why."""
    errors = manifest_errors(manifest)
    if errors:
        raise ManifestError("invalid release manifest: " + "; ".join(errors))
    return manifest


def dump_manifest(manifest: dict) -> bytes:
    """The bytes that are signed and published: sorted keys, 2-space indent, newline."""
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()


def load_public_key(pem: bytes) -> ec.EllipticCurvePublicKey:
    """Load a cosign (PEM, ECDSA P-256) public key."""
    try:
        key = serialization.load_pem_public_key(pem)
    except ValueError as exc:
        raise ManifestError(f"not a PEM public key: {exc}") from exc
    if not isinstance(key, ec.EllipticCurvePublicKey):
        raise ManifestError("the release key must be an ECDSA (cosign) public key")
    return key


def verify_blob(blob: bytes, signature_b64: bytes | str, public_key_pem: bytes) -> None:
    """Check a cosign ``sign-blob`` signature over ``blob``; raise ManifestError if it fails."""
    key = load_public_key(public_key_pem)
    try:
        signature = base64.b64decode(
            signature_b64.strip() if isinstance(signature_b64, bytes) else signature_b64.strip(),
            validate=True,
        )
        key.verify(signature, blob, ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, binascii.Error, ValueError) as exc:
        raise ManifestError("signature does not verify against the release key") from exc


def sign_blob(blob: bytes, private_key_pem: bytes, password: bytes | None = None) -> bytes:
    """Sign like ``cosign sign-blob`` with a PEM EC private key; returns the base64 signature.

    For tests and offline tooling. CI signs with ``cosign sign-blob`` and the project key.
    """
    key = serialization.load_pem_private_key(private_key_pem, password=password)
    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise ManifestError("signing key must be an EC private key")
    return base64.b64encode(key.sign(blob, ec.ECDSA(hashes.SHA256())))


def load_verified(blob: bytes, signature_b64: bytes | str, public_key_pem: bytes) -> dict:
    """Verify the signature, then parse and validate the manifest. Signature first, always."""
    verify_blob(blob, signature_b64, public_key_pem)
    try:
        manifest = json.loads(blob)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest is not JSON: {exc}") from exc
    return validate_manifest(manifest)
