"""``zebra.forms.resolve_template_text`` / ``resolve_schema_templates`` (#231)."""

from zebra.forms import resolve_schema_templates, resolve_template_text


def test_text_reference_forms():
    props = {"a": "x", "__task_output_t": "out", "d": {"e": {"f": 1}}}

    assert resolve_template_text("{{a}}-{{t.output}}-{{d.e.f}}", props) == "x-out-1"


def test_unresolved_references_become_empty():
    assert resolve_template_text("[{{missing}}][{{d.nope}}]", {"d": {}}) == "[][]"


def test_schema_display_text_resolves_and_the_rest_is_untouched():
    schema = {
        "title": "Adopt {{incoming.name}}?",
        "description": "{{incoming.reason}}",
        "properties": {"f": {"title": "{{incoming.name}}", "default": "{{a}}", "x": "{{a}}"}},
    }
    props = {"incoming": {"name": "Web Research", "reason": "new"}, "a": "z"}

    out = resolve_schema_templates(schema, props)

    assert out["title"] == "Adopt Web Research?"
    assert out["description"] == "new"
    assert out["properties"]["f"] == {"title": "Web Research", "default": "z", "x": "{{a}}"}
    assert schema["title"] == "Adopt {{incoming.name}}?"
