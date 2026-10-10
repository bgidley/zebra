"""Tests for scripts/build_css.py (pinned Tailwind binary handling, #159)."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import urllib.error
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "build_css.py"


@pytest.fixture(scope="module")
def build_css():
    spec = importlib.util.spec_from_file_location("build_css", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("system", "machine", "expected"),
    [
        ("Linux", "aarch64", "tailwindcss-linux-arm64"),
        ("Linux", "x86_64", "tailwindcss-linux-x64"),
        ("Darwin", "arm64", "tailwindcss-macos-arm64"),
        ("Darwin", "x86_64", "tailwindcss-macos-x64"),
    ],
)
def test_asset_name_maps_supported_platforms(build_css, system, machine, expected):
    assert build_css.asset_name(system, machine) == expected


def test_asset_name_rejects_unpinned_platform(build_css):
    with pytest.raises(build_css.BuildError):
        build_css.asset_name("Windows", "AMD64")


def test_every_pinned_hash_is_a_sha256(build_css):
    assert build_css.SHA256
    for digest in build_css.SHA256.values():
        assert len(digest) == 64 and int(digest, 16) >= 0


def test_verify_accepts_matching_and_rejects_other_content(build_css, tmp_path):
    binary = tmp_path / "tailwindcss"
    binary.write_bytes(b"real binary")
    good = hashlib.sha256(b"real binary").hexdigest()

    build_css.verify(binary, good)
    with pytest.raises(build_css.BuildError, match="Checksum mismatch"):
        build_css.verify(binary, "0" * 64)


def test_tampered_cached_binary_is_refused_before_running(build_css, tmp_path, monkeypatch):
    name = build_css.asset_name()
    (tmp_path / name).write_bytes(b"not the pinned binary")
    monkeypatch.setattr(
        build_css.urllib.request,
        "urlopen",
        lambda *a, **k: pytest.fail("must not download when a cached binary exists"),
    )

    with pytest.raises(build_css.BuildError, match="Checksum mismatch"):
        build_css.ensure_binary(cache_dir=tmp_path)


def test_download_failure_raises_clear_error_and_leaves_no_partial_file(
    build_css, tmp_path, monkeypatch
):
    def offline(*_a, **_k):
        raise urllib.error.URLError("Temporary failure in name resolution")

    monkeypatch.setattr(build_css.urllib.request, "urlopen", offline)

    with pytest.raises(build_css.BuildError, match="Could not download .*name resolution"):
        build_css.ensure_binary(cache_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_downloaded_binary_with_wrong_checksum_is_discarded(build_css, tmp_path, monkeypatch):
    class FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        build_css.urllib.request, "urlopen", lambda *a, **k: FakeResponse(b"tampered")
    )

    with pytest.raises(build_css.BuildError, match="Checksum mismatch"):
        build_css.ensure_binary(cache_dir=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_main_returns_error_without_running_binary_on_checksum_failure(
    build_css, monkeypatch, capsys
):
    def boom(*_a, **_k):
        raise build_css.BuildError("Checksum mismatch for tailwindcss-linux-arm64")

    monkeypatch.setattr(build_css, "ensure_binary", boom)
    monkeypatch.setattr(
        build_css.subprocess, "call", lambda *a, **k: pytest.fail("binary must not run")
    )

    assert build_css.main([]) == 1
    assert "Checksum mismatch" in capsys.readouterr().err
