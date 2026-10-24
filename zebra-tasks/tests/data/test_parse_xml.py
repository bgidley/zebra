"""Tests for ParseXmlAction."""

import json

import pytest

from zebra_tasks.data.xml_parse import ParseXmlAction

BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
]>
<lolz>&lol2;</lolz>"""


@pytest.fixture
def action():
    return ParseXmlAction()


async def test_mapping(action, make_task, mock_context):
    data = '<feed><item id="1">A</item><item id="2">B</item><title>T</title></feed>'
    result = await action.run(make_task({"data": data}), mock_context)

    assert result.success
    assert result.output == {
        "data": {
            "feed": {
                "item": [{"@id": "1", "#text": "A"}, {"@id": "2", "#text": "B"}],
                "title": "T",
            }
        },
        "root": "feed",
    }
    assert mock_context.process.properties["xml_data"] == result.output
    json.dumps(result.output)


async def test_namespaces_dropped_and_declaration_allowed(action, make_task, mock_context):
    data = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss xmlns:dc="http://purl.org/dc/elements/1.1/" version="2.0">'
        "<channel><dc:creator>Ann</dc:creator><empty/></channel></rss>"
    )
    result = await action.run(make_task({"data": data, "output_key": "feed"}), mock_context)

    assert result.output["data"] == {
        "rss": {"@version": "2.0", "channel": {"creator": "Ann", "empty": None}}
    }
    assert mock_context.process.properties["feed"]["root"] == "rss"


async def test_namespace_collision_merges_into_list(action, make_task, mock_context):
    data = '<r xmlns:a="urn:a" xmlns:b="urn:b"><a:x>1</a:x><b:x>2</b:x></r>'
    result = await action.run(make_task({"data": data}), mock_context)

    assert result.output["data"] == {"r": {"x": ["1", "2"]}}


async def test_mixed_text_kept(action, make_task, mock_context):
    result = await action.run(make_task({"data": "<p>hello <b>x</b></p>"}), mock_context)

    assert result.output["data"] == {"p": {"b": "x", "#text": "hello"}}


@pytest.mark.parametrize(
    "data",
    [
        BILLION_LAUGHS,
        '<!DOCTYPE foo SYSTEM "http://example.com/x.dtd"><foo/>',
        '<!doctype foo [<!entity x SYSTEM "file:///etc/passwd">]><foo>&x;</foo>',
    ],
)
async def test_dtd_refused(action, make_task, mock_context, data):
    result = await action.run(make_task({"data": data}), mock_context)

    assert not result.success
    assert "DOCTYPE" in result.error
    assert "xml_data" not in mock_context.process.properties


async def test_malformed(action, make_task, mock_context):
    result = await action.run(make_task({"data": "<a><b></a>"}), mock_context)

    assert not result.success
    assert "invalid XML" in result.error


async def test_not_text(action, make_task, mock_context):
    result = await action.run(make_task({"data": {"a": 1}}), mock_context)

    assert not result.success
    assert "must be text" in result.error
