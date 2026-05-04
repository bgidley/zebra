"""Tests for RoutineRegistry."""

import logging
from pathlib import Path

import pytest
import yaml

from zebra_agent.scheduler.registry import RoutineRegistry
from zebra_agent.scheduler.routine import Routine


@pytest.fixture
def registry():
    return RoutineRegistry()


@pytest.fixture
def routines_dir(tmp_path):
    return tmp_path


def write_yaml(directory: Path, filename: str, data: dict) -> Path:
    p = directory / filename
    p.write_text(yaml.dump(data))
    return p


class TestRoutineRegistryBasics:
    def test_empty_registry(self, registry):
        assert registry.all() == []

    def test_register_and_get(self, registry):
        r = Routine(name="test", schedule={"every": "30m"})
        registry.register(r)
        assert registry.get("test") is r

    def test_register_overwrites(self, registry):
        r1 = Routine(name="r", schedule={"every": "30m"})
        r2 = Routine(name="r", schedule={"every": "1h"})
        registry.register(r1)
        registry.register(r2)
        assert registry.get("r") is r2


class TestLoadYamlDir:
    def test_valid_every_routine(self, registry, routines_dir):
        write_yaml(
            routines_dir,
            "check.yaml",
            {"name": "health_check", "schedule": {"every": "10m"}, "workflow": "health"},
        )
        registry.load_yaml_dir(routines_dir)
        r = registry.get("health_check")
        assert r is not None
        assert r.workflow == "health"
        assert r.schedule == {"every": "10m"}

    def test_valid_cron_routine(self, registry, routines_dir):
        write_yaml(
            routines_dir,
            "nightly.yaml",
            {"name": "nightly_job", "schedule": "0 3 * * *"},
        )
        registry.load_yaml_dir(routines_dir)
        r = registry.get("nightly_job")
        assert r is not None
        assert r.schedule == "0 3 * * *"

    def test_budget_aware_flag(self, registry, routines_dir):
        write_yaml(
            routines_dir,
            "expensive.yaml",
            {"name": "expensive", "schedule": {"every": "1h"}, "budget_aware": True},
        )
        registry.load_yaml_dir(routines_dir)
        assert registry.get("expensive").budget_aware is True

    def test_missing_name_skipped(self, registry, routines_dir, caplog):
        write_yaml(routines_dir, "bad.yaml", {"schedule": {"every": "5m"}})
        with caplog.at_level(logging.WARNING):
            registry.load_yaml_dir(routines_dir)
        assert registry.all() == []
        assert "missing required fields" in caplog.text

    def test_missing_schedule_skipped(self, registry, routines_dir, caplog):
        write_yaml(routines_dir, "bad.yaml", {"name": "incomplete"})
        with caplog.at_level(logging.WARNING):
            registry.load_yaml_dir(routines_dir)
        assert registry.all() == []

    def test_non_existent_dir_ignored(self, registry, tmp_path):
        registry.load_yaml_dir(tmp_path / "nonexistent")
        assert registry.all() == []

    def test_multiple_files_all_loaded(self, registry, routines_dir):
        write_yaml(routines_dir, "a.yaml", {"name": "r_a", "schedule": {"every": "5m"}})
        write_yaml(routines_dir, "b.yaml", {"name": "r_b", "schedule": "0 12 * * *"})
        registry.load_yaml_dir(routines_dir)
        assert len(registry.all()) == 2
