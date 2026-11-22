"""The web engine factory wires the python_exec contract into prompts (#323)."""

import pytest
from zebra.definitions.loader import load_definition
from zebra.tasks.base import ExecutionContext
from zebra_agent.library import BUILTIN_WORKFLOWS_DIR
from zebra_agent_web.api import engine as engine_module
from zebra_tasks.compute.sandbox import describe_contract


@pytest.mark.django_db(transaction=True)
async def test_web_factory_engine_renders_contract_in_compute_prompt(monkeypatch):
    monkeypatch.setattr(engine_module, "_store", None)
    monkeypatch.setattr(engine_module, "_engine", None)
    await engine_module._async_init()
    engine = engine_module.get_engine()

    definition = load_definition(BUILTIN_WORKFLOWS_DIR / "compute.yaml")
    task_def = definition.tasks["plan"]
    process = await engine.create_process(definition, properties={"goal": "add"})
    context = ExecutionContext(
        engine=engine,
        store=engine.store,
        process=process,
        process_definition=definition,
        task_definition=task_def,
        extras=engine.extras,
    )
    prompt = context.resolve_template(task_def.properties["system_prompt"])

    assert describe_contract() in prompt
    assert "Assign the final value to a variable named `result`" in prompt
