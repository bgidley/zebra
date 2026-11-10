"""Build, sign, verify, promote and publish release manifests (#283, slice R3).

Layout (local ``--dir`` and the public release bucket alike)::

    releases/vX.Y.Z.json(.sig)   one manifest per release, channel "next" when built
    channels/next.json(.sig)     newest release, written automatically by the tag pipeline
    channels/stable.json(.sig)   written only by ``promote`` (the manual release:promote-stable)

Subcommands::

    build    --version X.Y.Z --image REG/REPO@sha256:... [--channel next] [--min-from V]
             [--breaking] [--contract app.0042_drop_x] [--security] [--unsupported-below V]
             [--notes-file F | --notes-gitlab] [--notes-url URL] [--previous-tag vA.B.C]
    sign     --key KEY FILE...     cosign sign-blob (a plain PEM EC key signs in-process)
    verify   --pubkey PUB FILE     signature first, then schema v1; --cosign also asks cosign
    promote  --version X.Y.Z --pubkey PUB [--to stable]: copy a verified release manifest to a
             channel; only the channel file changes
    publish  --bucket B [FILE...]  upload with the oci CLI (default: every file under --dir)
    fetch    --bucket B NAME...    download into --dir

Expand migrations are the Django migration files added since the previous release tag; any
named with ``--contract`` move to ``contract`` and need ``--breaking``. Schema and signature
checks live in ``zebra_agent.release`` so the instance updater (#280) uses the same code.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from zebra_agent.release import (
    ManifestError,
    dump_manifest,
    load_verified,
    parse_version,
    sign_blob,
    validate_manifest,
)

DEFAULT_PLATFORM = "linux/arm64"
_MIGRATION_PATH = re.compile(r"(?:^|/)([a-z_][a-z0-9_]*)/migrations/([0-9]{4}_[A-Za-z0-9_]+)\.py$")
_TAG = re.compile(r"^v\d+\.\d+\.\d+$")

Runner = Callable[[Sequence[str]], subprocess.CompletedProcess]


def _run(cmd: Sequence[str]) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), capture_output=True, text=True, check=True)


# --- build ----------------------------------------------------------------------------------


def release_path(version: str) -> str:
    return f"releases/v{version}.json"


def channel_path(channel: str) -> str:
    return f"channels/{channel}.json"


def previous_tag(version: str, tags: list[str]) -> str | None:
    """The highest release tag below ``version``."""
    target = parse_version(version)
    older = [t for t in tags if _TAG.match(t) and parse_version(t) < target]
    return max(older, key=parse_version) if older else None


def added_migrations(paths: list[str]) -> list[str]:
    """``app.0001_name`` for each Django migration file in ``paths``, sorted."""
    names = []
    for path in paths:
        match = _MIGRATION_PATH.search(path)
        if match:
            names.append(f"{match.group(1)}.{match.group(2)}")
    return sorted(names)


def migrations_since(previous: str | None, ref: str, run: Runner = _run) -> list[str]:
    """Migration files added in ``previous..ref`` (all of them for the first release)."""
    if previous:
        args = ["git", "diff", "--name-only", "--diff-filter=A", f"{previous}..{ref}"]
    else:
        args = ["git", "ls-tree", "-r", "--name-only", ref]
    return added_migrations(run(args).stdout.splitlines())


def build_manifest(
    *,
    version: str,
    image: str,
    channel: str = "next",
    platforms: list[str] | None = None,
    min_from: str = "0.0.0",
    migrations: list[str] = (),
    contract: list[str] = (),
    breaking: bool = False,
    security: bool = False,
    unsupported_below: str | None = None,
    notes_md: str = "",
    notes_url: str = "",
    published_at: str | None = None,
) -> dict:
    """Assemble and validate a schema v1 manifest."""
    unknown = sorted(set(contract) - set(migrations))
    if unknown:
        raise ManifestError(f"--contract names migrations not in this release: {unknown}")
    digest = image.rpartition("@")[2]
    manifest = {
        "schema": 1,
        "version": version,
        "channel": channel,
        "image": image,
        "digest": digest,
        "platforms": platforms or [DEFAULT_PLATFORM],
        "min_from": min_from,
        "breaking": breaking,
        "migrations": {
            "expand": [m for m in migrations if m not in contract],
            "contract": sorted(contract),
        },
        "notes_url": notes_url,
        "notes_md": notes_md,
        "security": security,
        "unsupported_below": unsupported_below,
        "published_at": published_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return validate_manifest(manifest)


def write_manifest(directory: Path, relative: str, manifest: dict) -> Path:
    path = directory / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dump_manifest(manifest))
    stale = path.with_name(path.name + ".sig")
    stale.unlink(missing_ok=True)  # a rewritten file must be signed again
    return path


def gitlab_release_notes(api_url: str, project: str, tag: str, token: str) -> str:
    """The description of the GitLab release ``tag`` (written by release_tag.py)."""
    quoted = urllib.parse.quote(project, safe="")
    request = urllib.request.Request(f"{api_url}/projects/{quoted}/releases/{tag}")
    request.add_header("PRIVATE-TOKEN", token)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return str(json.loads(response.read()).get("description") or "")
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise ManifestError(f"could not read the notes of release {tag}: {exc}") from exc


# --- sign / verify --------------------------------------------------------------------------


def sig_path(path: Path) -> Path:
    return path.with_name(path.name + ".sig")


def is_plain_pem_key(key: bytes) -> bool:
    return b"-----BEGIN EC PRIVATE KEY-----" in key or b"-----BEGIN PRIVATE KEY-----" in key


def sign_file(path: Path, key_path: Path, run: Runner = _run) -> Path:
    """Write ``<file>.sig``: cosign for a cosign key, in-process for a plain PEM EC key."""
    out = sig_path(path)
    key = key_path.read_bytes()
    if is_plain_pem_key(key):
        out.write_bytes(sign_blob(path.read_bytes(), key) + b"\n")
    else:
        # COSIGN_PASSWORD comes from the environment. Offline: no transparency log upload.
        run(
            [
                "cosign",
                "sign-blob",
                "--yes",
                "--tlog-upload=false",
                "--key",
                str(key_path),
                "--output-signature",
                str(out),
                str(path),
            ]
        )
    return out


def verify_file(path: Path, pubkey: Path, *, use_cosign: bool = False, run: Runner = _run) -> dict:
    """Verify ``<file>.sig`` then the schema; optionally cross-check with cosign verify-blob."""
    signature = sig_path(path)
    if not signature.exists():
        raise ManifestError(f"{signature} is missing")
    manifest = load_verified(path.read_bytes(), signature.read_bytes(), pubkey.read_bytes())
    if use_cosign:
        try:
            run(
                [
                    "cosign",
                    "verify-blob",
                    "--key",
                    str(pubkey),
                    "--signature",
                    str(signature),
                    "--insecure-ignore-tlog=true",
                    str(path),
                ]
            )
        except subprocess.CalledProcessError as exc:
            raise ManifestError(f"cosign verify-blob refused {path}: {exc.stderr}") from exc
    return manifest


def promote(directory: Path, version: str, pubkey: Path, to: str = "stable") -> Path:
    """Copy the verified release manifest to channel ``to``; return the channel file."""
    source = directory / release_path(version)
    manifest = verify_file(source, pubkey)
    manifest = validate_manifest({**manifest, "channel": to})
    return write_manifest(directory, channel_path(to), manifest)


# --- bucket ---------------------------------------------------------------------------------


def oci_base(bucket: str, namespace: str | None) -> tuple[list[str], list[str]]:
    """The ``oci os object`` command and its bucket arguments."""
    where = (["--namespace", namespace] if namespace else []) + ["--bucket-name", bucket]
    return ["oci", "os", "object"], where


def publish(
    directory: Path, files: list[Path], bucket: str, namespace: str | None, run: Runner = _run
) -> list[str]:
    """Upload ``files`` (each needs its .sig, uploaded after it) to the bucket."""
    base, where = oci_base(bucket, namespace)
    names = []
    for path in files:
        if not sig_path(path).exists():
            raise ManifestError(f"refusing to publish unsigned {path}")
        for item in (path, sig_path(path)):
            name = item.relative_to(directory).as_posix()
            kind = "application/json" if item.suffix == ".json" else "text/plain"
            run(
                [*base, "put", *where, "--name", name, "--file", str(item)]
                + ["--content-type", kind, "--force"]
            )
            names.append(name)
    return names


def fetch(
    directory: Path, names: list[str], bucket: str, namespace: str | None, run: Runner = _run
) -> list[Path]:
    """Download objects (e.g. ``releases/v1.2.0.json`` and its .sig) into ``directory``."""
    base, where = oci_base(bucket, namespace)
    paths = []
    for name in names:
        out = directory / name
        out.parent.mkdir(parents=True, exist_ok=True)
        run([*base, "get", *where, "--name", name, "--file", str(out)])
        paths.append(out)
    return paths


# --- CLI ------------------------------------------------------------------------------------


def ensure_history(run: Runner = _run) -> None:
    """Fetch tags, and the full history if the CI clone is shallow (best effort)."""
    try:
        shallow = run(["git", "rev-parse", "--is-shallow-repository"]).stdout.strip() == "true"
        run(["git", "fetch", "--quiet", "--tags", *(["--unshallow"] if shallow else []), "origin"])
    except subprocess.CalledProcessError as exc:
        print(f"release_manifest: warning: could not fetch history: {exc.stderr}", file=sys.stderr)


def _cmd_build(args: argparse.Namespace, env: dict[str, str]) -> int:
    directory = Path(args.dir)
    if args.fetch:
        ensure_history()
    tags = [t for t in _run(["git", "tag", "--list", "v*"]).stdout.split() if t]
    previous = args.previous_tag or previous_tag(args.version, tags)
    ref = args.ref or (f"v{args.version}" if f"v{args.version}" in tags else "HEAD")
    if args.notes_gitlab:
        token = env.get("RELEASE_GITLAB_TOKEN", "")
        if not token:
            raise ManifestError("--notes-gitlab needs RELEASE_GITLAB_TOKEN")
        notes = gitlab_release_notes(
            env.get("CI_API_V4_URL", "https://gitlab.com/api/v4"),
            env.get("CI_PROJECT_PATH", "gidley/zebra"),
            f"v{args.version}",
            token,
        )
    else:
        notes = Path(args.notes_file).read_text() if args.notes_file else ""
    security = args.security or "### Security" in notes
    manifest = build_manifest(
        version=args.version,
        image=args.image,
        channel=args.channel,
        platforms=args.platform or None,
        min_from=args.min_from,
        migrations=migrations_since(previous, ref),
        contract=args.contract,
        breaking=args.breaking,
        security=security,
        unsupported_below=args.unsupported_below or None,
        notes_md=notes,
        notes_url=args.notes_url,
    )
    for relative in (release_path(args.version), channel_path(args.channel)):
        print(write_manifest(directory, relative, manifest))
    return 0


def _files(args: argparse.Namespace) -> list[Path]:
    if args.files:
        return [Path(f) for f in args.files]
    return sorted(Path(args.dir).rglob("*.json"))


def main(argv: list[str] | None = None) -> int:
    env = dict(os.environ)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dir", default="release-dist", help="local mirror of the bucket")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build")
    build.add_argument("--version", required=True)
    build.add_argument("--image", required=True, help="registry/repo@sha256:<digest>")
    build.add_argument("--channel", default="next")
    build.add_argument("--platform", action="append", default=[])
    build.add_argument("--min-from", default="0.0.0")
    build.add_argument("--breaking", action="store_true")
    build.add_argument("--contract", action="append", default=[])
    build.add_argument("--security", action="store_true")
    build.add_argument("--unsupported-below", default=env.get("RELEASE_UNSUPPORTED_BELOW", ""))
    build.add_argument("--notes-file")
    build.add_argument("--notes-gitlab", action="store_true")
    build.add_argument("--notes-url", default="")
    build.add_argument("--previous-tag")
    build.add_argument("--ref")
    build.add_argument("--no-fetch", dest="fetch", action="store_false", help="skip git fetch")

    sign = sub.add_parser("sign")
    sign.add_argument("--key", required=True)
    sign.add_argument("files", nargs="*")

    verify = sub.add_parser("verify")
    verify.add_argument("--pubkey", required=True)
    verify.add_argument("--cosign", action="store_true", help="also run cosign verify-blob")
    verify.add_argument("files", nargs="*")

    prom = sub.add_parser("promote")
    prom.add_argument("--version", required=True)
    prom.add_argument("--pubkey", required=True)
    prom.add_argument("--to", default="stable")

    pub = sub.add_parser("publish")
    pub.add_argument("--bucket", required=True)
    pub.add_argument("--namespace", default=env.get("RELEASE_BUCKET_NAMESPACE") or None)
    pub.add_argument("files", nargs="*")

    get = sub.add_parser("fetch")
    get.add_argument("--bucket", required=True)
    get.add_argument("--namespace", default=env.get("RELEASE_BUCKET_NAMESPACE") or None)
    get.add_argument("names", nargs="+")

    args = parser.parse_args(argv)
    directory = Path(args.dir)
    try:
        if args.command == "build":
            return _cmd_build(args, env)
        if args.command == "sign":
            for path in _files(args):
                print(sign_file(path, Path(args.key)))
        elif args.command == "verify":
            for path in _files(args):
                manifest = verify_file(path, Path(args.pubkey), use_cosign=args.cosign)
                print(f"OK {path}: v{manifest['version']} ({manifest['channel']})")
        elif args.command == "promote":
            print(promote(directory, args.version, Path(args.pubkey), args.to))
        elif args.command == "publish":
            for name in publish(directory, _files(args), args.bucket, args.namespace):
                print(f"uploaded {name}")
        elif args.command == "fetch":
            for path in fetch(directory, args.names, args.bucket, args.namespace):
                print(path)
    except (ManifestError, subprocess.CalledProcessError, OSError) as exc:
        detail = getattr(exc, "stderr", "") or ""
        print(f"release_manifest: {exc} {detail}".rstrip(), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
