"""Confidentiality scan and sensitivity check for skill sync (#236): rules and fail closed."""

import json

import pytest

from zebra_tasks.commons.confidentiality import (
    configured_patterns,
    scan_confidential,
)
from zebra_tasks.commons.sensitivity import check_sensitivity
from zebra_tasks.llm.base import LLMProvider, LLMResponse, TokenUsage


class Reply(LLMProvider):
    def __init__(self, content: str | Exception):
        self.content = content

    async def complete(self, messages, tools=None, temperature=0.7, max_tokens=4096, **kw):
        if isinstance(self.content, Exception):
            raise self.content
        return LLMResponse(
            content=self.content,
            tool_calls=None,
            finish_reason="end_turn",
            usage=TokenUsage(1, 1),
            model="m",
        )

    async def stream(self, *a, **k):
        raise NotImplementedError
        yield ""

    @property
    def name(self):
        return "reply"

    @property
    def model(self):
        return "m"

    @property
    def max_context_tokens(self):
        return 1000


CLEAN = Reply(json.dumps({"confidential": False, "findings": []}))


def _wf(prompt: str) -> str:
    return f'name: W\ntasks:\n  a:\n    name: A\n    properties:\n      prompt: "{prompt}"\n'


@pytest.mark.parametrize(
    "text,kind",
    [
        ("Check build.corp for status", "internal_host"),
        ("Fetch https://wiki.acme-inc.com/page", "url"),
        ("Ping 10.1.2.3 first", "internal_host"),
        ("Update the Project Falcon tracker", "codename"),
        ("Draft a reply for the customer Globex", "customer"),
        ("Login with password: hunter22", "credential"),
    ],
)
async def test_rules_block(text, kind):
    result = await scan_confidential(_wf(text), patterns=[], llm=CLEAN)
    assert not result["clean"]
    assert kind in {f["kind"] for f in result["findings"]}
    assert text not in json.dumps(result)  # findings are masked


async def test_device_patterns_block():
    result = await scan_confidential(_wf("Notes for nightjar"), patterns=["NIGHTJAR"], llm=CLEAN)
    assert result["findings"][0]["kind"] == "confidential_pattern"


def test_configured_patterns_read_env(monkeypatch):
    monkeypatch.setenv("ZEBRA_SYNC_CONFIDENTIAL_PATTERNS", "alpha;;beta\ngamma")
    assert configured_patterns(["delta"]) == ["alpha", "beta", "gamma", "delta"]


async def test_clean_only_when_rules_and_llm_pass():
    ok = await scan_confidential(
        _wf("Review {{goal}} at https://example.com"), patterns=[], llm=CLEAN
    )
    assert ok["clean"]
    flagged = Reply(json.dumps({"confidential": True, "findings": [{"kind": "customer"}]}))
    assert not (await scan_confidential(_wf("Review it"), patterns=[], llm=flagged))["clean"]


@pytest.mark.parametrize(
    "llm",
    [None, Reply(RuntimeError("down")), Reply("not json"), Reply(json.dumps({"x": 1}))],
)
async def test_confidentiality_fails_closed(llm):
    result = await scan_confidential(_wf("Review it"), patterns=[], llm=llm)
    assert not result["clean"] and result["failed_closed"]


async def test_bad_pattern_fails_closed():
    result = await scan_confidential(_wf("Review it"), patterns=["("], llm=CLEAN)
    assert result["failed_closed"]


async def test_sensitivity_reads_verdict():
    yes = Reply(json.dumps({"sensitive": True, "topics": ["job search"], "reason": "job"}))
    result = await check_sensitivity(
        _wf("Track job applications"), sphere="work", observed=True, llm=yes
    )
    assert result["sensitive"] and result["topics"] == ["job search"]
    no = Reply(json.dumps({"sensitive": False, "reason": "ordinary"}))
    assert not (await check_sensitivity(_wf("Review"), sphere="home", observed=False, llm=no))[
        "sensitive"
    ]


@pytest.mark.parametrize(
    "llm",
    [None, Reply(RuntimeError("down")), Reply("garbage"), Reply(json.dumps({"sensitive": "no"}))],
)
async def test_sensitivity_fails_closed(llm):
    result = await check_sensitivity(_wf("Review"), sphere="work", observed=True, llm=llm)
    assert result["sensitive"] and result["failed_closed"]
