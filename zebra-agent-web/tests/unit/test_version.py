"""Tests for version metadata loading and /api/version/ endpoint."""

import json

import pytest
from django.test import Client
from zebra_agent_web.api.version import _FALLBACK, load_version


class TestLoadVersion:
    def test_reads_valid_version_json(self, tmp_path):
        data = {
            "short_hash": "abc1234",
            "date": "2026-05-05",
            "commits": [{"hash": "abc1234", "date": "2026-05-05", "subject": "feat: test"}],
        }
        f = tmp_path / "version.json"
        f.write_text(json.dumps(data))

        result = load_version(f)

        assert result["short_hash"] == "abc1234"
        assert result["date"] == "2026-05-05"
        assert len(result["commits"]) == 1

    def test_fallback_when_file_missing(self, tmp_path):
        result = load_version(tmp_path / "nonexistent.json")

        assert result == _FALLBACK
        assert result["short_hash"] == "unknown"
        assert result["commits"] == []

    def test_fallback_when_json_malformed(self, tmp_path):
        f = tmp_path / "version.json"
        f.write_text("not valid json {{{")

        result = load_version(f)

        assert result == _FALLBACK

    def test_fallback_when_root_not_dict(self, tmp_path):
        f = tmp_path / "version.json"
        f.write_text("[1, 2, 3]")

        result = load_version(f)

        assert result == _FALLBACK


@pytest.mark.django_db
class TestVersionEndpoint:
    def test_returns_200_with_version_keys(self):
        client = Client()
        response = client.get("/api/version/")

        assert response.status_code == 200
        data = response.json()
        assert "short_hash" in data
        assert "date" in data
        assert "commits" in data

    def test_no_auth_required(self):
        # Unauthenticated client should receive 200, not 401/403
        client = Client()
        response = client.get("/api/version/")

        assert response.status_code == 200
