"""Golden gym (#171): Django score store, the /gym/ read model and page."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from zebra_agent.gym import GoldenTask
from zebra_agent.metrics import GymScore
from zebra_agent_web.api import gym
from zebra_agent_web.api.models import GymScoreModel
from zebra_agent_web.metrics_store import DjangoMetricsStore

T0 = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)


def _score(golden_id="answer_question_capital", variant="current", score=1.0, **kw) -> GymScore:
    fields = {
        "id": f"{golden_id}-{variant}-{kw.get('gym_run_id', 'run-1')}-{score}",
        "gym_run_id": "run-1",
        "golden_id": golden_id,
        "workflow_name": "Answer Question",
        "variant": variant,
        "score": score,
        "created_at": T0,
        "details": {"mode": "on_demand"},
    }
    fields.update(kw)
    return GymScore(**fields)


@pytest.mark.django_db(transaction=True)
class TestDjangoGymScores:
    async def test_round_trip_filters_and_order(self):
        store = DjangoMetricsStore()
        await store.record_gym_scores(
            [
                _score(score=0.5),
                _score(
                    variant="candidate",
                    score=None,
                    error="judge failed",
                    created_at=T0 + timedelta(hours=1),
                    details={"mode": "gate", "decision": "rejected", "criteria": [{"score": 1}]},
                ),
                _score(golden_id="other", gym_run_id="run-2", created_at=T0 - timedelta(days=1)),
            ]
        )

        scores = await store.get_gym_scores()
        assert [s.golden_id for s in scores] == [
            "answer_question_capital",
            "answer_question_capital",
            "other",
        ]
        assert scores[0].variant == "candidate"
        assert scores[0].score is None and scores[0].error == "judge failed"
        assert scores[0].details["decision"] == "rejected"
        assert [s.score for s in await store.get_gym_scores(variant="current", limit=1)] == [0.5]
        assert len(await store.get_gym_scores(golden_id="other")) == 1
        assert len(await store.get_gym_scores(workflow_name="Nope")) == 0

    async def test_empty_record_is_a_no_op(self):
        await DjangoMetricsStore().record_gym_scores([])
        assert await DjangoMetricsStore().get_gym_scores() == []


def test_rows_show_latest_and_history_oldest_first():
    task = GoldenTask("g1", "Answer Question", "Goal?", "Answer", ["c"])
    scores = [
        _score("g1", score=0.9, created_at=T0 + timedelta(days=2)),
        _score("g1", variant="candidate", score=0.1, created_at=T0 + timedelta(days=1)),
        _score("g1", score=0.7, created_at=T0),
    ]
    (row,) = gym.golden_task_rows([task], scores)
    assert row["latest"].score == 0.9
    assert [s.score for s in row["history"]] == [0.7, 0.9]


def test_decisions_group_by_run_and_workflow():
    gate = {"mode": "gate", "decision": "rejected"}
    scores = [
        _score("g1", variant="candidate", score=0.0, details=gate),
        _score("g2", variant="candidate", score=0.5, details=gate),
        _score("g1", score=1.0, details=gate),
        _score("g2", score=1.0, details=gate),
        _score("g1", gym_run_id="run-0", score=1.0),  # on demand: not a decision
    ]
    (decision,) = gym.gate_decisions(scores)
    assert decision["decision"] == "rejected"
    assert decision["current_mean"] == 1.0
    assert decision["candidate_mean"] == 0.25
    assert decision["golden_ids"] == ["g1", "g2"]


def test_unscored_run_has_no_mean():
    gate = {"mode": "gate", "decision": "rejected"}
    (decision,) = gym.gate_decisions(
        [
            _score("g1", variant="candidate", score=None, details=gate),
            _score("g1", score=1.0, details=gate),
        ]
    )
    assert decision["candidate_mean"] is None


@pytest.fixture
def completed_setup(db):
    from zebra_agent_web.api.identity import set_identity_sync

    set_identity_sync("Test User")


def _row(**fields) -> None:
    GymScoreModel.objects.create(
        **{
            "id": "s1",
            "gym_run_id": "run-1",
            "golden_id": "answer_question_capital",
            "workflow_name": "Answer Question",
            "variant": "current",
            "score": 0.75,
            "created_at": T0,
            "details": {"mode": "on_demand"},
            **fields,
        }
    )


@pytest.mark.django_db(transaction=True)
def test_gym_page_lists_golden_tasks_scores_and_decisions(authenticated_client, completed_setup):
    _row()
    gate = {"mode": "gate", "decision": "rejected"}
    _row(id="s2", gym_run_id="dream-1", score=1.0, details=gate, created_at=T0 + timedelta(1))
    _row(
        id="s3",
        gym_run_id="dream-1",
        variant="candidate",
        score=0.25,
        details=gate,
        created_at=T0 + timedelta(1),
    )

    response = authenticated_client.get("/gym/")

    assert response.status_code == 200
    html = response.content.decode()
    # The shipped golden tasks are listed
    assert "What is the capital of Australia" in html
    assert 'id="golden-summarize_text_meeting"' in html
    assert "not run yet" in html
    # Latest current-version score, then the gate decision with both means
    assert "1.00" in html and "0.75" in html
    assert 'data-decision="rejected"' in html
    assert "1.00 → 0.25" in html
    assert 'href="/gym/"' in html  # nav item


@pytest.mark.django_db(transaction=True)
def test_gym_page_empty_decisions(authenticated_client, completed_setup):
    response = authenticated_client.get("/gym/")
    assert response.status_code == 200
    assert "No changes tested yet." in response.content.decode()
