"""Human task titles and descriptions resolve {{…}} like defaults do (#231).

The *Commons Offer* approval showed "Offer {{offer.name}} to the public Commons?" on the task
page and in the inbox: only field defaults and descriptions were resolved, not titles.
"""

from datetime import UTC, datetime

from zebra.core.models import (
    ProcessDefinition,
    ProcessInstance,
    ProcessState,
    TaskDefinition,
    TaskInstance,
    TaskState,
)
from zebra.storage.memory import InMemoryStore
from zebra_agent_web.api.inbox import inbox_items
from zebra_agent_web.api.web_views import _resolve_schema_defaults

OFFER_TITLE = "Offer {{offer.name}} to the public Commons?"


def test_titles_and_descriptions_resolve_top_level_and_per_field():
    schema = {
        "type": "object",
        "title": OFFER_TITLE,
        "description": "From {{share.sphere}}",
        "properties": {
            "review": {"type": "string", "title": "About {{offer.name}}", "default": "{{x}}"},
            "n": {"type": "integer", "default": 3},
        },
    }
    props = {"offer": {"name": "Answer Question"}, "share": {"sphere": "work"}, "x": "y"}

    out = _resolve_schema_defaults(schema, props)

    assert out["title"] == "Offer Answer Question to the public Commons?"
    assert out["description"] == "From work"
    assert out["properties"]["review"]["title"] == "About Answer Question"
    assert out["properties"]["review"]["default"] == "y"
    assert out["properties"]["n"]["default"] == 3
    assert schema["title"] == OFFER_TITLE  # the definition is not mutated


async def test_inbox_title_is_resolved():
    store = InMemoryStore()
    await store.save_definition(
        ProcessDefinition(
            id="offer",
            name="Commons Offer",
            first_task_id="approve",
            tasks={
                "approve": TaskDefinition(
                    id="approve",
                    name="Offer workflow publicly?",
                    auto=False,
                    properties={"schema": {"type": "object", "title": OFFER_TITLE}},
                ),
            },
        )
    )
    now = datetime.now(UTC)
    await store.save_process(
        ProcessInstance(
            id="p",
            definition_id="offer",
            state=ProcessState.RUNNING,
            properties={"offer": {"name": "Answer Question"}},
            created_at=now,
        )
    )
    await store.save_task(
        TaskInstance(
            id="t",
            process_id="p",
            task_definition_id="approve",
            state=TaskState.READY,
            foe_id="f",
            created_at=now,
            updated_at=now,
        )
    )

    [item] = await inbox_items(store)

    assert item["title"] == "Offer Answer Question to the public Commons?"
