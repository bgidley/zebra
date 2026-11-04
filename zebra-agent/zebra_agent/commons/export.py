"""Signed single-workflow export files (Zebra Commons S2b, #229).

An export file carries one workflow from one Zebra to another with no network:

```json
{"format": "zebra-workflow-export", "version": 1,
 "event": {NIP-01 event of kind WORKFLOW_EXPORT_KIND, signed by the device key},
 "chain": [the DEVICE_CERT events that attribute the device to its Zebra]}
```

The event's content is ``{"name", "yaml", "commons"}``: the YAML without its ``commons``
block or local tags (neither is hashed), and the block. Tags: ``x`` = content hash,
``zebra`` = the publisher's Zebra pubkey, plus the Commons tags.

``verify_export`` accepts a file only when the event is correctly signed by the Zebra or
by one of its certified, unrevoked devices, the hash recomputes from the YAML and equals
the block's and the ``x`` tag, and the block is not ``foreign_users``. Pure: no Django,
no I/O beyond what the caller passes in.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import yaml

from zebra_agent.commons import commons_exportable, keys
from zebra_agent.commons.events import (
    COMMONS_TAG,
    PROTOCOL_VERSION_TAG,
    Event,
    sign_event,
    verify_event,
)
from zebra_agent.commons.identity import (
    DEVICE_CERT_KIND,
    DEVICE_REVOKE_KIND,
    verify_attributed,
    verify_device_chain,
)
from zebra_agent.provenance import NotHashableError, content_sha256, read_commons, relabel

if TYPE_CHECKING:
    from zebra_agent.library import WorkflowLibrary

EXPORT_FORMAT = "zebra-workflow-export"
EXPORT_VERSION = 1
# Provisional until S4 fixes the Commons kinds (nothing is published).
WORKFLOW_EXPORT_KIND = 31229
_FILE_KEYS = {"format", "version", "event", "chain"}
_LOWER_HEX = re.compile(r"^[0-9a-f]+$")


class ExportRefused(ValueError):
    """The workflow may not be exported; the message says why."""


@dataclass
class ExportVerification:
    """The outcome of ``verify_export``. ``reason`` is ``ok`` when accepted."""

    ok: bool
    reason: str
    zebra_pubkey: str | None = None
    signer_pubkey: str | None = None
    name: str | None = None
    yaml: str | None = None
    commons: dict[str, Any] | None = field(default=None)
    content_sha256: str | None = None
    display_name: str | None = None
    golden_tasks: list[dict[str, Any]] = field(default_factory=list)


def build_export(
    yaml_content: str,
    *,
    device_secret: str,
    zebra_pubkey: str,
    chain: list[Event],
    created_at: int | None = None,
    display_name: str | None = None,
    golden_tasks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a signed export of a library workflow (its file text, block included).

    The caller has checked ``commons_exportable``; this checks what the file needs: a
    block whose hash matches the content, and a device chain that verifies.
    *display_name* (the publisher Zebra's name) and *golden_tasks* (``{goal, expected,
    criteria}`` for the importer's gym, #230) are optional signed content keys.

    Raises:
        ExportRefused: No block, a hash mismatch, ``foreign_users`` or an unattributed device.
    """
    block = read_commons(yaml_content)
    if block is None:
        raise ExportRefused("workflow has no commons block")
    if block.get("foreign_users") is not False:
        raise ExportRefused("workflow saw other users' runs (foreign_users)")
    try:
        body = relabel(yaml_content)
        actual = content_sha256(body)
    except NotHashableError as e:
        raise ExportRefused(f"workflow is not hashable: {e}") from e
    if block.get("content_sha256") != actual:
        raise ExportRefused("commons block hash does not match the workflow content")
    device_pubkey = keys.public_key(device_secret)
    certs: list[Event] = []
    if device_pubkey != zebra_pubkey:
        certs = [
            e
            for e in chain
            if e.kind == DEVICE_CERT_KIND
            and e.pubkey == zebra_pubkey
            and e.tag_values("d") == [device_pubkey]
        ]
        result = verify_device_chain(device_pubkey, zebra_pubkey, chain, now=created_at)
        if not result.ok:
            raise ExportRefused(f"this device is not attributed to its Zebra ({result.reason})")
    name = _name_of(body)
    payload: dict[str, Any] = {"name": name, "yaml": body, "commons": block}
    if display_name:
        payload["display_name"] = display_name
    if golden_tasks:
        payload["golden_tasks"] = [_golden_payload(t) for t in golden_tasks]
    content = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    tags = [["x", actual], ["zebra", zebra_pubkey], COMMONS_TAG, PROTOCOL_VERSION_TAG]
    event = sign_event(device_secret, WORKFLOW_EXPORT_KIND, tags, content, created_at)
    return {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "event": event.to_dict(),
        "chain": [e.to_dict() for e in certs],
    }


async def export_workflow(
    library: WorkflowLibrary,
    name: str,
    *,
    device_secret: str,
    zebra_pubkey: str,
    chain: list[Event],
    display_name: str | None = None,
    with_golden: bool = False,
) -> str:
    """Export the active workflow *name* as the text of a signed export file.

    *display_name* is the publisher's name shown to importers; *with_golden* ships the
    library's golden tasks for the workflow (the importer scans them for personal data).

    Raises:
        ExportRefused: Unknown workflow, not ``commons_exportable`` (system, foreign or
            no block), or anything ``build_export`` refuses.
    """
    info = await library.get_workflow_info(name)
    if info is None:
        raise ExportRefused(f"no active workflow named {name!r}")
    if not commons_exportable(info):
        raise ExportRefused(
            f"{name!r} may not leave this deployment (system workflow, learnt from other "
            "users' runs, or no provenance yet)"
        )
    text = info.definition_path.read_text()
    golden = [t.to_dict() for t in library.list_golden_tasks(name)] if with_golden else None
    data = build_export(
        text,
        device_secret=device_secret,
        zebra_pubkey=zebra_pubkey,
        chain=chain,
        display_name=display_name,
        golden_tasks=golden,
    )
    file_text = dump_export(data)
    check = verify_export(file_text, revocations=chain)
    if not check.ok:  # pragma: no cover - build_export guards every reason
        raise ExportRefused(f"export failed its own verification ({check.reason})")
    return file_text


def _golden_payload(task: dict[str, Any]) -> dict[str, Any]:
    """The shareable part of a golden task: goal, expected outcome and criteria."""
    return {
        "goal": str(task.get("goal", "")),
        "expected": str(task.get("expected", "")),
        "criteria": [str(c) for c in task.get("criteria") or []],
    }


def dump_export(data: dict[str, Any]) -> str:
    """The export file text: canonical JSON, so any changed byte fails ``verify_export``."""
    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _name_of(yaml_body: str) -> str:
    data = yaml.safe_load(yaml_body)
    return str(data.get("name", "untitled")) if isinstance(data, dict) else "untitled"


def verify_export(
    file_text: str | bytes,
    *,
    expected_zebra: str | None = None,
    revocations: list[Event] | None = None,
    now: int | None = None,
) -> ExportVerification:
    """Check a signed export file.

    Args:
        file_text: The file's text (or bytes, decoded as UTF-8)
        expected_zebra: Accept only this publisher's Zebra pubkey
        revocations: Certs and ``DEVICE_REVOKE`` events the verifier already holds
            (e.g. its own device table); revokes among them reject the signer
        now: Unix time for cert expiry (default: now)

    The file must be byte-for-byte as ``dump_export`` wrote it (``not_canonical``), so a
    change that JSON would ignore (whitespace, an unused key) is still detected, and
    every event in the chain must be a valid cert of the signer from the Zebra.

    Reasons: ``ok``, ``malformed``, ``not_canonical``, ``wrong_format``, ``bad_signature``,
    ``bad_chain``, ``revoked``, ``no_cert``, ``bad_cert``, ``expired``, ``wrong_zebra``,
    ``hash_mismatch``, ``not_hashable``, ``foreign_users``.
    """
    try:
        if isinstance(file_text, bytes):
            file_text = file_text.decode("utf-8")
        data = json.loads(file_text)
    except (UnicodeDecodeError, ValueError):
        return ExportVerification(False, "malformed")
    if not isinstance(data, dict) or set(data) != _FILE_KEYS:
        return ExportVerification(False, "malformed")
    if dump_export(data) != file_text:
        return ExportVerification(False, "not_canonical")
    if data.get("format") != EXPORT_FORMAT or data.get("version") != EXPORT_VERSION:
        return ExportVerification(False, "wrong_format")
    try:
        event = Event.from_dict(data.get("event"))
        chain = [Event.from_dict(e) for e in data.get("chain") or []]
    except (ValueError, TypeError):
        return ExportVerification(False, "malformed")
    if event.kind != WORKFLOW_EXPORT_KIND:
        return ExportVerification(False, "wrong_format")
    zebra_values = event.tag_values("zebra")
    if len(zebra_values) != 1:
        return ExportVerification(False, "malformed")
    zebra_pubkey = zebra_values[0]
    if expected_zebra is not None and zebra_pubkey != expected_zebra:
        return ExportVerification(False, "wrong_zebra", zebra_pubkey, event.pubkey)

    for e in [event, *chain]:
        if not all(_LOWER_HEX.match(v) for v in (e.id, e.pubkey, e.sig)):
            return ExportVerification(False, "bad_signature", zebra_pubkey, event.pubkey)
    for cert in chain:
        if not (
            cert.kind == DEVICE_CERT_KIND
            and cert.pubkey == zebra_pubkey
            and cert.tag_values("d") == [event.pubkey]
            and verify_event(cert)
        ):
            return ExportVerification(False, "bad_chain", zebra_pubkey, event.pubkey)

    held = [e for e in revocations or [] if e.kind in (DEVICE_CERT_KIND, DEVICE_REVOKE_KIND)]
    try:
        attributed = verify_attributed(event, zebra_pubkey, chain + held, now=now)
    except (ValueError, TypeError):
        return ExportVerification(False, "bad_signature", zebra_pubkey, event.pubkey)
    if not attributed.ok:
        return ExportVerification(False, attributed.reason, zebra_pubkey, event.pubkey)

    content = event.json_content()
    if content is None:
        return ExportVerification(False, "malformed", zebra_pubkey, event.pubkey)
    body, block, name = content.get("yaml"), content.get("commons"), content.get("name")
    if not isinstance(body, str) or not isinstance(block, dict) or not isinstance(name, str):
        return ExportVerification(False, "malformed", zebra_pubkey, event.pubkey)
    try:
        actual = content_sha256(body)
    except NotHashableError:
        return ExportVerification(False, "not_hashable", zebra_pubkey, event.pubkey)
    if not (event.tag_values("x") == [actual] and block.get("content_sha256") == actual):
        return ExportVerification(False, "hash_mismatch", zebra_pubkey, event.pubkey)
    if block.get("foreign_users") is not False:
        return ExportVerification(False, "foreign_users", zebra_pubkey, event.pubkey)
    display_name = content.get("display_name")
    golden = content.get("golden_tasks", [])
    if (display_name is not None and not isinstance(display_name, str)) or not (
        isinstance(golden, list) and all(isinstance(t, dict) for t in golden)
    ):
        return ExportVerification(False, "malformed", zebra_pubkey, event.pubkey)
    return ExportVerification(
        True,
        "ok",
        zebra_pubkey=zebra_pubkey,
        signer_pubkey=event.pubkey,
        name=name,
        yaml=body,
        commons=block,
        content_sha256=actual,
        display_name=display_name or None,
        golden_tasks=golden,
    )


def adopt_export(
    library: WorkflowLibrary,
    verified: ExportVerification,
    *,
    name: str | None = None,
) -> Any:
    """Adopt a verified export into *library* (``save(writer="adopt")``); returns the path.

    Raises:
        ExportRefused: If *verified* did not verify.
        zebra_agent.library.AdoptionRefused: If the library refuses it (e.g. a taken name).
    """
    if not verified.ok or verified.yaml is None or verified.commons is None:
        raise ExportRefused(f"export did not verify ({verified.reason})")
    return library.save(
        verified.yaml,
        writer="adopt",
        received=verified.commons,
        expected_sha256=verified.content_sha256,
        name=name,
        origin_pubkey=verified.zebra_pubkey,
    )
