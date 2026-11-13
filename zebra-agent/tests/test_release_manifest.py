"""Release manifests (#283, R3): schema v1, cosign-format signatures, channels, publishing.

Signing uses a throwaway ECDSA P-256 key in PEM, which ``sign_file`` signs in-process the way
``cosign sign-blob`` does (base64 DER ECDSA over SHA-256 of the file). The oci CLI and cosign
are replaced by a recording fake runner.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from zebra_agent.release import (
    ManifestError,
    dump_manifest,
    load_verified,
    manifest_errors,
    sign_blob,
    validate_manifest,
    verify_blob,
)

ROOT = Path(__file__).resolve().parents[2]
DIGEST = "sha256:" + "ab" * 32
IMAGE = f"lhr.ocir.io/ns/zebra@{DIGEST}"


@pytest.fixture(scope="module")
def rm():
    spec = importlib.util.spec_from_file_location(
        "release_manifest", ROOT / "scripts" / "release_manifest.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["release_manifest"] = module
    spec.loader.exec_module(module)
    return module


def _keypair(tmp_path: Path, name: str = "release") -> tuple[Path, Path]:
    key = ec.generate_private_key(ec.SECP256R1())
    private = tmp_path / f"{name}.key"
    public = tmp_path / f"{name}.pub"
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return private, public


@pytest.fixture
def keys(tmp_path):
    return _keypair(tmp_path)


def _manifest(**overrides) -> dict:
    manifest = {
        "schema": 1,
        "version": "0.3.0",
        "channel": "next",
        "image": IMAGE,
        "digest": DIGEST,
        "platforms": ["linux/arm64"],
        "min_from": "0.2.0",
        "breaking": False,
        "migrations": {"expand": ["api.0037_add_release"], "contract": []},
        "notes_url": "",
        "notes_md": "## Zebra v0.3.0\n",
        "security": False,
        "unsupported_below": None,
        "published_at": "2026-11-09T12:00:00Z",
    }
    manifest.update(overrides)
    return manifest


class FakeRunner:
    def __init__(self, fail: set[str] = frozenset()):
        self.calls: list[list[str]] = []
        self.fail = fail

    def __call__(self, cmd):
        cmd = list(cmd)
        self.calls.append(cmd)
        if cmd[0] in self.fail or (len(cmd) > 1 and cmd[1] in self.fail):
            raise subprocess.CalledProcessError(1, cmd, "", "refused")
        if cmd[:4] == ["oci", "os", "object", "get"]:
            Path(cmd[cmd.index("--file") + 1]).write_text("{}")
        return subprocess.CompletedProcess(cmd, 0, "", "")


# --- schema ---------------------------------------------------------------------------------


class TestSchema:
    def test_valid_manifest(self):
        assert validate_manifest(_manifest()) == _manifest()

    @pytest.mark.parametrize(
        ("overrides", "error"),
        [
            ({"schema": 2}, "schema"),
            ({"version": "v0.3"}, "version"),
            ({"channel": "beta"}, "channel"),
            ({"image": "lhr.ocir.io/ns/zebra:0.3.0"}, "image"),  # a tag, not a digest
            ({"digest": "sha256:" + "cd" * 32}, "does not match"),
            ({"platforms": ["linux/amd64"]}, "platforms"),
            ({"min_from": "0.4.0"}, "min_from: above"),
            ({"unsupported_below": "1.0.0"}, "unsupported_below: above"),
            ({"breaking": "no"}, "breaking"),
            ({"migrations": {"expand": ["drop table x"], "contract": []}}, "migrations.expand"),
            (
                {"migrations": {"expand": [], "contract": ["api.0038_drop_x"]}},
                "breaking: must be true",
            ),
            ({"notes_url": "http://example.com"}, "notes_url"),
            ({"published_at": "2026-11-09 12:00"}, "published_at"),
            ({"extra": 1}, "extra: unknown field"),
        ],
    )
    def test_invalid_manifests(self, overrides, error):
        errors = manifest_errors(_manifest(**overrides))
        assert any(error in e for e in errors), errors
        with pytest.raises(ManifestError):
            validate_manifest(_manifest(**overrides))

    def test_missing_field(self):
        manifest = _manifest()
        del manifest["min_from"]
        assert manifest_errors(manifest) == ["min_from: missing"]

    def test_breaking_release_with_contract_is_valid(self):
        validate_manifest(
            _manifest(breaking=True, migrations={"expand": [], "contract": ["api.0038_drop_x"]})
        )

    def test_security_release_marks_old_versions_unsupported(self):
        validate_manifest(_manifest(security=True, unsupported_below="0.2.1"))


# --- signatures -----------------------------------------------------------------------------


class TestSignatures:
    def test_round_trip(self, keys):
        private, public = keys
        blob = dump_manifest(_manifest())
        signature = sign_blob(blob, private.read_bytes())
        assert load_verified(blob, signature, public.read_bytes()) == _manifest()

    def test_every_single_byte_change_fails(self, keys):
        private, public = keys
        blob = dump_manifest(_manifest())
        signature = sign_blob(blob, private.read_bytes())
        for index in range(0, len(blob), 7):
            tampered = bytearray(blob)
            tampered[index] ^= 0x01
            with pytest.raises(ManifestError, match="does not verify"):
                verify_blob(bytes(tampered), signature, public.read_bytes())

    def test_other_key_fails(self, keys, tmp_path):
        _, public = keys
        other_private, _ = _keypair(tmp_path, "other")
        blob = dump_manifest(_manifest())
        signature = sign_blob(blob, other_private.read_bytes())
        with pytest.raises(ManifestError, match="does not verify"):
            verify_blob(blob, signature, public.read_bytes())

    def test_garbage_signature_fails(self, keys):
        with pytest.raises(ManifestError):
            verify_blob(b"{}", b"not base64!!", keys[1].read_bytes())

    def test_signature_checked_before_schema(self, keys):
        private, public = keys
        blob = b'{"schema": 9}'
        with pytest.raises(ManifestError, match="does not verify"):
            load_verified(blob, base64.b64encode(b"x" * 70), public.read_bytes())
        # Correctly signed but invalid: the schema still refuses it.
        with pytest.raises(ManifestError, match="invalid release manifest"):
            load_verified(blob, sign_blob(blob, private.read_bytes()), public.read_bytes())

    def test_rejects_a_non_ec_public_key(self):
        with pytest.raises(ManifestError):
            verify_blob(
                b"{}", b"AA==", b"-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----"
            )


# --- build / sign / promote / publish -------------------------------------------------------


class TestReleaseManifestScript:
    def test_added_migrations(self, rm):
        paths = [
            "zebra-agent-web/zebra_agent_web/api/migrations/0037_add_release.py",
            "zebra-agent-web/zebra_agent_web/api/migrations/__init__.py",
            "zebra-agent-web/zebra_agent_web/api/models.py",
        ]
        assert rm.added_migrations(paths) == ["api.0037_add_release"]

    def test_previous_tag(self, rm):
        tags = ["v0.1.0", "v0.10.0", "v0.2.0", "v0.3.0", "nightly"]
        assert rm.previous_tag("0.3.0", tags) == "v0.2.0"
        assert rm.previous_tag("0.11.0", tags) == "v0.10.0"
        assert rm.previous_tag("0.1.0", tags) is None

    def test_build_moves_contract_migrations(self, rm):
        manifest = rm.build_manifest(
            version="0.3.0",
            image=IMAGE,
            migrations=["api.0037_add_release", "api.0038_drop_x"],
            contract=["api.0038_drop_x"],
            breaking=True,
        )
        assert manifest["migrations"] == {
            "expand": ["api.0037_add_release"],
            "contract": ["api.0038_drop_x"],
        }
        assert manifest["digest"] == DIGEST

    def test_build_refuses_contract_without_breaking(self, rm):
        with pytest.raises(ManifestError, match="breaking"):
            rm.build_manifest(
                version="0.3.0",
                image=IMAGE,
                migrations=["api.0038_drop_x"],
                contract=["api.0038_drop_x"],
            )

    def _release(self, rm, tmp_path, keys) -> Path:
        directory = tmp_path / "dist"
        manifest = rm.build_manifest(version="0.3.0", image=IMAGE, notes_md="notes")
        for relative in (rm.release_path("0.3.0"), rm.channel_path("next")):
            rm.sign_file(rm.write_manifest(directory, relative, manifest), keys[0])
        return directory

    def test_sign_and_verify_files(self, rm, tmp_path, keys):
        directory = self._release(tmp_path=tmp_path, rm=rm, keys=keys)
        next_file = directory / "channels/next.json"
        assert rm.verify_file(next_file, keys[1])["channel"] == "next"
        assert json.loads((directory / "releases/v0.3.0.json").read_text())["version"] == "0.3.0"

    def test_tampered_file_fails_verify(self, rm, tmp_path, keys):
        directory = self._release(rm, tmp_path, keys)
        path = directory / "channels/next.json"
        path.write_bytes(path.read_bytes().replace(b'"0.3.0"', b'"0.3.1"', 1))
        with pytest.raises(ManifestError, match="does not verify"):
            rm.verify_file(path, keys[1])
        assert (
            rm.main(["--dir", str(directory), "verify", "--pubkey", str(keys[1]), str(path)]) == 1
        )

    def test_unsigned_file_fails_verify(self, rm, tmp_path, keys):
        directory = self._release(rm, tmp_path, keys)
        (directory / "channels/next.json.sig").unlink()
        with pytest.raises(ManifestError, match="missing"):
            rm.verify_file(directory / "channels/next.json", keys[1])

    def test_promote_changes_only_the_channel_file(self, rm, tmp_path, keys):
        directory = self._release(rm, tmp_path, keys)
        before = {p: p.read_bytes() for p in directory.rglob("*") if p.is_file()}
        stable = rm.promote(directory, "0.3.0", keys[1])
        rm.sign_file(stable, keys[0])

        after = {p: p.read_bytes() for p in directory.rglob("*") if p.is_file()}
        assert set(after) - set(before) == {stable, rm.sig_path(stable)}
        assert all(after[p] == before[p] for p in before)  # nothing else touched
        promoted = rm.verify_file(stable, keys[1])
        release = json.loads((directory / "releases/v0.3.0.json").read_text())
        assert promoted == {**release, "channel": "stable"}

    def test_promote_refuses_a_tampered_release(self, rm, tmp_path, keys):
        directory = self._release(rm, tmp_path, keys)
        release = directory / "releases/v0.3.0.json"
        release.write_bytes(release.read_bytes().replace(DIGEST.encode(), b"sha256:" + b"cd" * 32))
        with pytest.raises(ManifestError):
            rm.promote(directory, "0.3.0", keys[1])
        assert not (directory / "channels/stable.json").exists()

    def test_rewriting_a_file_drops_its_old_signature(self, rm, tmp_path, keys):
        directory = self._release(rm, tmp_path, keys)
        rm.write_manifest(directory, rm.channel_path("next"), _manifest())
        assert not (directory / "channels/next.json.sig").exists()

    def test_cosign_key_signs_with_cosign_offline(self, rm, tmp_path):
        key = tmp_path / "cosign.key"
        key.write_text("-----BEGIN ENCRYPTED SIGSTORE PRIVATE KEY-----\nx\n")
        blob = tmp_path / "m.json"
        blob.write_text("{}")
        runner = FakeRunner()
        rm.sign_file(blob, key, run=runner)
        (cmd,) = runner.calls
        assert cmd[:2] == ["cosign", "sign-blob"]
        assert "--tlog-upload=false" in cmd
        assert cmd[cmd.index("--output-signature") + 1] == str(tmp_path / "m.json.sig")

    def test_verify_can_cross_check_with_cosign(self, rm, tmp_path, keys):
        directory = self._release(rm, tmp_path, keys)
        runner = FakeRunner()
        rm.verify_file(directory / "channels/next.json", keys[1], use_cosign=True, run=runner)
        assert runner.calls[0][:2] == ["cosign", "verify-blob"]
        with pytest.raises(ManifestError, match="cosign verify-blob refused"):
            rm.verify_file(
                directory / "channels/next.json",
                keys[1],
                use_cosign=True,
                run=FakeRunner(fail={"verify-blob"}),
            )

    def test_publish_uploads_file_then_signature(self, rm, tmp_path, keys):
        directory = self._release(rm, tmp_path, keys)
        runner = FakeRunner()
        names = rm.publish(
            directory, [directory / "channels/next.json"], "zebra-releases", "ns", run=runner
        )
        assert names == ["channels/next.json", "channels/next.json.sig"]
        first = runner.calls[0]
        assert first[:4] == ["oci", "os", "object", "put"]
        assert first[first.index("--bucket-name") + 1] == "zebra-releases"
        assert first[first.index("--namespace") + 1] == "ns"
        assert first[first.index("--content-type") + 1] == "application/json"

    def test_publish_refuses_unsigned(self, rm, tmp_path, keys):
        directory = self._release(rm, tmp_path, keys)
        (directory / "channels/next.json.sig").unlink()
        runner = FakeRunner()
        with pytest.raises(ManifestError, match="unsigned"):
            rm.publish(directory, [directory / "channels/next.json"], "b", None, run=runner)
        assert runner.calls == []

    def test_fetch(self, rm, tmp_path):
        runner = FakeRunner()
        paths = rm.fetch(tmp_path, ["releases/v0.3.0.json"], "zebra-releases", None, run=runner)
        assert paths == [tmp_path / "releases/v0.3.0.json"]
        assert paths[0].exists()


# --- CI -------------------------------------------------------------------------------------


class TestCiJobs:
    @pytest.fixture(scope="class")
    def ci(self):
        return yaml.safe_load((ROOT / ".gitlab-ci.yml").read_text())

    @pytest.mark.parametrize("job", ["release:manifest", "release:promote-stable"])
    def test_release_jobs_run_only_on_configured_release_tags(self, ci, job):
        rules = ci[job]["rules"]
        assert all("$CI_COMMIT_TAG =~" in rule["if"] for rule in rules)
        assert all("$RELEASE_BUCKET" in rule["if"] for rule in rules)
        assert all("$COSIGN_PRIVATE_KEY" in rule["if"] for rule in rules)
        assert all("CI_COMMIT_BRANCH" not in rule["if"] for rule in rules)

    def test_promote_is_manual(self, ci):
        (rule,) = ci["release:promote-stable"]["rules"]
        assert rule["when"] == "manual"

    def test_deploy_still_master_push_only(self, ci):
        assert ci["deploy"]["rules"] == [
            {"if": '$CI_COMMIT_BRANCH == "master" && $CI_PIPELINE_SOURCE == "push"'}
        ]
