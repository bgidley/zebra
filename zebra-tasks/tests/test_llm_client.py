"""get_llm / model_for / normalize_model and usage recording (#205)."""

from types import SimpleNamespace

import pytest

from zebra_tasks.llm.base import LLMProvider, LLMResponse, Message, TokenUsage
from zebra_tasks.llm.client import get_llm, model_for, set_llm_factory
from zebra_tasks.llm.models import DEFAULT_TIER, normalize_model
from zebra_tasks.llm.openrouter import OpenRouterLLM


class FakeLLM(LLMProvider):
    def __init__(self, model: str, cost: float = 0.25):
        self._model = model
        self.cost = cost

    @property
    def model(self) -> str:
        return self._model

    async def complete(self, messages, tools=None, temperature=0.7, max_tokens=4096, **kw):
        return LLMResponse(
            content="ok",
            tool_calls=None,
            finish_reason="stop",
            usage=TokenUsage(10, 5, cost_usd=self.cost),
            model="vendor/picked",
        )


@pytest.fixture
def fake():
    made: list[FakeLLM] = []

    def factory(model: str) -> FakeLLM:
        made.append(FakeLLM(model))
        return made[-1]

    previous = set_llm_factory(factory)
    yield made
    set_llm_factory(previous)


def _context(**props):
    store: dict = dict(props)
    return SimpleNamespace(
        process=SimpleNamespace(properties=store),
        extras={},
        get_process_property=lambda k, d=None: store.get(k, d),
        set_process_property=store.__setitem__,
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (None, "medium"),
        ("", "medium"),
        ("low", "low"),
        ("MAX", "max"),
        ("anthropic/claude-opus-5.5", "anthropic/claude-opus-5.5"),
        # names stored before #205
        ("haiku", "low"),
        ("sonnet", "medium"),
        ("opus", "high"),
        ("claude-haiku-5-5", "low"),
        ("claude-sonnet-4-20250514", "medium"),
        ("kimi", "low"),
    ],
)
def test_normalize_model(name, expected):
    assert normalize_model(name) == expected


def test_unknown_model_is_the_default_tier(caplog):
    assert normalize_model("gpt-4o") == DEFAULT_TIER
    assert "Unknown model 'gpt-4o'" in caplog.text


def test_get_llm_is_openrouter_by_default(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    llm = get_llm("high")
    assert isinstance(llm, OpenRouterLLM) and llm.model == "high"


def test_factory_receives_the_normalised_model(fake):
    get_llm("opus")
    get_llm()
    assert [llm.model for llm in fake] == ["high", "medium"]


async def test_llm_with_context_records_usage_on_the_process(fake):
    context = _context(__total_cost__=1.0)
    llm = get_llm("low", context)

    await llm.complete([Message.user("a")])
    await llm.complete([Message.user("b")])

    props = context.process.properties
    assert props["__total_cost__"] == pytest.approx(1.5)
    assert props["__total_tokens__"] == 30
    assert [h["cost"] for h in props["__token_history__"]] == [0.25, 0.25]
    assert props["__token_history__"][0]["model"] == "vendor/picked"
    assert llm.model == "low"


async def test_llm_without_context_records_nothing(fake):
    context = _context()
    await get_llm("low").complete([Message.user("a")])
    assert context.process.properties == {}


@pytest.mark.parametrize(
    ("task_model", "process_model", "default", "expected"),
    [
        ("high", "low", None, "high"),
        (None, "low", "max", "low"),
        (None, None, "max", "max"),
        (None, None, None, "medium"),
        (None, "sonnet", None, "medium"),
    ],
)
def test_model_for(task_model, process_model, default, expected):
    task = SimpleNamespace(properties={"model": task_model} if task_model else {})
    context = _context(**({"__llm_model__": process_model} if process_model else {}))
    assert model_for(task, context, default) == expected
