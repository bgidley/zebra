"""Every built-in workflow keeps its output contracts (#271)."""

from pathlib import Path

import pytest
from zebra.definitions.contracts import ERROR, validate_contracts
from zebra.definitions.loader import load_definition

import zebra_agent

BUILTINS = sorted((Path(zebra_agent.__file__).parent.parent / "workflows").glob("*.yaml"))


def test_builtin_workflows_found():
    assert len(BUILTINS) > 10


@pytest.mark.parametrize("path", BUILTINS, ids=lambda p: p.name)
def test_builtin_has_no_contract_errors(path):
    errors = [str(f) for f in validate_contracts(load_definition(path)) if f.severity == ERROR]

    assert errors == []
