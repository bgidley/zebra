"""Tests for Routine / RoutineRun schedule computation."""

from datetime import UTC, datetime, timedelta

import pytest

from zebra_agent.scheduler.routine import Routine, RoutineRun, _parse_interval, next_run_for


class TestParseInterval:
    def test_minutes(self):
        assert _parse_interval("30m") == timedelta(minutes=30)

    def test_hours(self):
        assert _parse_interval("2h") == timedelta(hours=2)

    def test_days(self):
        assert _parse_interval("1d") == timedelta(days=1)

    def test_invalid(self):
        with pytest.raises(ValueError):
            _parse_interval("10s")


class TestNextRunFor:
    def setup_method(self):
        self.now = datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC)

    def test_every_interval_no_last_run(self):
        """First run with no last_run returns now."""
        result = next_run_for({"every": "30m"}, None, self.now)
        assert result == self.now

    def test_every_interval_with_last_run(self):
        """Next run = last_run + interval."""
        last = self.now - timedelta(minutes=10)
        result = next_run_for({"every": "30m"}, last, self.now)
        assert result == last + timedelta(minutes=30)

    def test_cron_next_run(self):
        """Cron schedule returns the next matching time after now."""
        # "0 12 * * *" = daily at noon
        result = next_run_for("0 12 * * *", None, self.now)
        # now is 10:00 so next noon is today
        assert result.hour == 12
        assert result.minute == 0

    def test_cron_next_run_past_today(self):
        """If cron already fired today, returns tomorrow."""
        noon = datetime(2026, 5, 4, 12, 0, 0, tzinfo=UTC)
        after_noon = datetime(2026, 5, 4, 13, 0, 0, tzinfo=UTC)
        result = next_run_for("0 12 * * *", None, after_noon)
        assert result > noon
        assert result.day == 5  # next day


class TestRoutineRunAdvance:
    def setup_method(self):
        self.now = datetime(2026, 5, 4, 10, 0, 0, tzinfo=UTC)
        self.routine = Routine(name="test", schedule={"every": "30m"})

    def test_initial_fires_immediately(self):
        run = RoutineRun.initial(self.routine, self.now)
        assert run.next_run == self.now
        assert run.last_run is None

    def test_advance_updates_times(self):
        run = RoutineRun.initial(self.routine, self.now)
        advanced = run.advance(self.routine, self.now, status="ok")
        assert advanced.last_run == self.now
        assert advanced.next_run == self.now + timedelta(minutes=30)
        assert advanced.last_status == "ok"
