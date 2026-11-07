"""Tests for zebra_tasks.templating.strip_templates (#288)."""

import re
import time

import pytest

from zebra_tasks.templating import strip_templates

_LAZY = re.compile(r"\{\{.*?\}\}", re.DOTALL)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "plain text",
        "Hello {{name}}!",
        "{{a}}{{b}} and {{ c.d }}",
        "multi\n{{line\ntemplate}} end",
        "unclosed {{ here",
        "{{a}} then unclosed {{ b",
        "close first }} then {{x}}",
        "{{{x}}}",
        "{{}}",
        "{{ {{inner}} }}",
    ],
)
def test_matches_the_lazy_regex(text):
    assert strip_templates(text) == _LAZY.sub(" ", text)


def test_linear_on_many_unclosed_openers():
    hostile = "{{" * 200_000
    started = time.perf_counter()
    assert strip_templates(hostile) == hostile
    assert time.perf_counter() - started < 1.0
