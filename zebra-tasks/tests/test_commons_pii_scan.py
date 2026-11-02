"""``commons_pii_scan`` (#229 S2b): rules plus a low-tier LLM, failing closed."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from zebra_tasks.commons.pii_scan import (
    ROUTE_CLEAN,
    ROUTE_REJECTED,
    CommonsPiiScanAction,
    collect_texts,
    rule_findings,
)
from zebra_tasks.llm.base import LLMResponse, TokenUsage
from zebra_tasks.llm.client import set_llm_factory

BUILTINS = Path(__file__).resolve().parents[2] / "zebra-agent" / "workflows"

WORKFLOW = """name: "Plan Trip"
description: "Plan a trip"
version: 1
inputs:
  type: object
  properties:
    goal:
      type: string
      default: "{default}"
      examples: ["{example}"]
tasks:
  plan:
    name: "Plan"
    action: llm_call
    properties:
      prompt: "{prompt} {{{{goal}}}}"
commons:
  content_sha256: "x"
  origin_pubkey: "jane.doe@gmail.com"
"""


def _wf(prompt="Plan the trip:", default="a weekend away", example="a city break") -> str:
    return WORKFLOW.format(prompt=prompt, default=default, example=example)


def _response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=None,
        finish_reason="stop",
        usage=TokenUsage(input_tokens=10, output_tokens=20),
        model="test-model",
    )


def _llm(*contents: str) -> MagicMock:
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=[_response(c) for c in contents])
    set_llm_factory(lambda model: provider)
    return provider


def _context(properties=None):
    props = dict(properties or {})
    ctx = MagicMock()
    ctx.process.properties = props
    ctx.process.id = "p1"
    ctx.set_process_property = MagicMock(side_effect=lambda k, v: props.__setitem__(k, v))
    ctx.resolve_template = MagicMock(side_effect=lambda x: x)
    return ctx


async def _scan(yaml_text, golden=None, **extra):
    task = SimpleNamespace(id="t1", properties={"yaml": yaml_text, "golden_tasks": golden, **extra})
    ctx = _context()
    result = await CommonsPiiScanAction().run(task, ctx)
    assert result.success
    assert ctx.process.properties["pii_scan"] == result.output
    return result


CLEAN = '{"personal_data": false, "findings": []}'


def test_hint_is_honest():
    assert CommonsPiiScanAction.reversibility_hint == "always_reversible"


class TestRules:
    @pytest.mark.parametrize(
        ("where", "value", "kind"),
        [
            ("default", "email jane.doe@gmail.com", "email"),
            ("example", "call +44 7700 900123", "phone"),
            ("prompt", "Ring 020 7946 0958 first.", "phone"),
            ("prompt", "Pay with 4111 1111 1111 1111", "card_number"),
            ("default", "NI AB 12 34 56 C", "ni_number"),
            ("example", "deliver to SW1A 1AA", "postcode"),
            ("prompt", "ssh to 81.2.69.160", "ip_address"),
            ("prompt", "use sk-abcdefghijklmnopqrstuvwx", "secret"),
            ("prompt", "fetch https://bob:hunter2@host.org/x", "url_credentials"),
        ],
    )
    async def test_finding_in_each_location_rejects_without_the_llm(self, where, value, kind):
        provider = _llm(CLEAN)
        result = await _scan(_wf(**{where: value}))
        assert result.next_route == ROUTE_REJECTED
        assert {f["kind"] for f in result.output["findings"]} >= {kind}
        assert result.output["failed_closed"] is False
        provider.complete.assert_not_called()
        # Findings are masked, never stored in full.
        assert value.split()[-1] not in json.dumps(result.output["findings"])

    async def test_golden_tasks_are_scanned(self):
        _llm(CLEAN)
        golden = [{"goal": "Plan Jane's trip; text her on 07700 900123", "criteria": ["ok"]}]
        result = await _scan(_wf(), golden=golden)
        assert result.next_route == ROUTE_REJECTED
        assert result.output["findings"][0]["path"].startswith("golden_tasks[0]")

    def test_reserved_examples_templates_and_numbers_are_not_findings(self):
        texts = collect_texts(
            {
                "prompt": "Mail {{user_email}} or test@example.com, x@foo.test; v1.2.3",
                "timeout": "600000",
                "date": "2026-01-01",
                "ip": "127.0.0.1 and 192.0.2.10",
            }
        )
        assert rule_findings(texts) == []

    def test_commons_block_is_not_scanned(self):
        texts = collect_texts({"name": "x", "commons": {"origin_pubkey": "a@gmail.com"}})
        assert {t.path for t in texts} == {"name", "name (key)"}

    def test_builtin_workflows_pass_the_rules(self):
        import yaml

        for path in sorted(BUILTINS.glob("*.yaml")):
            findings = rule_findings(collect_texts(yaml.safe_load(path.read_text())))
            assert findings == [], f"{path.name}: {findings}"


class TestLLM:
    async def test_clean_only_when_rules_and_llm_pass(self):
        provider = _llm(CLEAN)
        result = await _scan(_wf(), golden=["Plan a weekend in Paris"])
        assert result.next_route == ROUTE_CLEAN
        assert result.output["clean"] is True
        provider.complete.assert_awaited_once()
        shown = provider.complete.call_args.kwargs["messages"][1].content
        assert "Plan a weekend in Paris" in shown  # golden tasks reach the LLM
        assert "jane.doe@gmail.com" not in shown  # the commons block does not

    async def test_llm_finding_rejects(self):
        _llm(
            '{"personal_data": true, "findings": [{"path": "tasks.plan.properties.prompt",'
            ' "kind": "health", "reason": "names a diagnosis"}]}'
        )
        result = await _scan(_wf(prompt="Plan around Bob's chemotherapy:"))
        assert result.next_route == ROUTE_REJECTED
        assert result.output["findings"][0]["source"] == "llm"
        assert result.output["failed_closed"] is False

    @pytest.mark.parametrize(
        "replies",
        [("not json", "still not json"), ('{"findings": []}',), ('{"personal_data": "no"}',)],
        ids=["unparseable", "no-verdict", "non-bool"],
    )
    async def test_unusable_reply_fails_closed(self, replies):
        _llm(*replies)
        result = await _scan(_wf())
        assert result.next_route == ROUTE_REJECTED
        assert result.output["failed_closed"] is True

    async def test_provider_error_fails_closed(self):
        provider = MagicMock()
        provider.complete = AsyncMock(side_effect=TimeoutError("timed out"))
        set_llm_factory(lambda model: provider)
        result = await _scan(_wf())
        assert result.next_route == ROUTE_REJECTED
        assert result.output["failed_closed"] is True

    async def test_no_llm_fails_closed(self):
        def missing(model):
            raise ValueError("OPENROUTER_API_KEY not set")

        set_llm_factory(missing)
        result = await _scan(_wf())
        assert result.next_route == ROUTE_REJECTED
        assert result.output["failed_closed"] is True

    async def test_too_much_text_fails_closed(self):
        provider = _llm(CLEAN)
        result = await _scan(_wf(), max_chars=50)
        assert result.next_route == ROUTE_REJECTED and result.output["failed_closed"]
        provider.complete.assert_not_called()


@pytest.mark.parametrize("bad", ["", None, "a: [", "- just a list"])
async def test_bad_yaml_fails_closed(bad):
    _llm(CLEAN)
    result = await _scan(bad)
    assert result.next_route == ROUTE_REJECTED
    assert result.output["failed_closed"] is True
