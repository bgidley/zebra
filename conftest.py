"""Root conftest.py for running all tests together."""

import pytest


@pytest.fixture(autouse=True)
def _reset_llm_factory():
    """Undo any ``set_llm_factory`` a test made, so fakes never leak between tests (#205)."""
    from zebra_tasks.llm.client import set_llm_factory

    previous = set_llm_factory(None)
    yield
    set_llm_factory(previous)
