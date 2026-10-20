"""Template defaults in human task forms (#98): nested dict keys resolve at any depth."""

from zebra_agent_web.api.web_views import _resolve_schema_defaults


def resolve(default: str, props: dict) -> str:
    schema = {"type": "object", "properties": {"f": {"type": "string", "default": default}}}
    return _resolve_schema_defaults(schema, props)["properties"]["f"]["default"]


def test_flat_property():
    assert resolve("{{title}}", {"title": "Add hello"}) == "Add hello"


def test_task_output_shorthand():
    assert resolve("{{review.output}}", {"__task_output_review": "ok"}) == "ok"


def test_nested_keys():
    props = {"__task_output_await_build": {"summary": "Done", "test": {"rc": 0, "command": "x"}}}
    assert resolve("{{__task_output_await_build.summary}}", props) == "Done"
    assert resolve("rc={{__task_output_await_build.test.rc}}", props) == "rc=0"


def test_missing_keys_are_empty():
    props = {"build": {"test": {}}}
    assert resolve("[{{build.test.rc}}][{{build.nope.deeper}}][{{absent.key}}]", props) == "[][][]"
