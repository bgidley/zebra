"""Tests for TransformJsonAction and its path helpers."""

import pytest

from zebra_tasks.data.json_transform import TransformJsonAction, get_path, parse_path

ISSUES = [
    {"title": "a", "state": "open", "votes": "3", "meta": {"team": "x"}},
    {"title": "b", "state": "closed", "votes": "10", "meta": {"team": "y"}},
    {"title": "c", "state": "open", "votes": "25", "meta": {"team": "x"}},
    {"title": "d", "state": "open", "meta": {"team": "y"}},
]


@pytest.fixture
def action():
    return TransformJsonAction()


@pytest.mark.parametrize(
    ("path", "tokens"),
    [
        ("a", ["a"]),
        ("a.b[0].c", ["a", "b", 0, "c"]),
        ("items[*].name", ["items", "*", "name"]),
        ("[-1]", [-1]),
        ("[0][1]", [0, 1]),
    ],
)
def test_parse_path(path, tokens):
    assert parse_path(path) == tokens


@pytest.mark.parametrize("path", ["", ".a", "a..b", "a[x]", "a[0"])
def test_parse_path_invalid(path):
    with pytest.raises(ValueError):
        parse_path(path)


def test_get_path_missing_is_none():
    data = {"a": [1, 2]}
    assert get_path(data, ["a", 5]) is None
    assert get_path(data, ["b", "c"]) is None
    assert get_path(data, ["a", "x"]) is None
    assert get_path(data, ["a", -1]) == 2


def test_wildcard_single_value_treated_as_list():
    assert get_path({"item": {"name": "x"}}, ["item", "*", "name"]) == ["x"]
    assert get_path({}, ["item", "*", "name"]) == []


async def test_path_selection(action, make_task, mock_context):
    data = {"a": {"items": [{"name": "x"}, {"name": "y"}]}}
    result = await action.run(make_task({"data": data, "path": "a.items[*].name"}), mock_context)

    assert result.success
    assert result.output == {"result": ["x", "y"], "count": 2}
    assert mock_context.process.properties["json_result"] == result.output


async def test_missing_path_is_null(action, make_task, mock_context):
    result = await action.run(make_task({"data": {"a": 1}, "path": "b.c[3]"}), mock_context)

    assert result.success
    assert result.output == {"result": None}


async def test_where_sort_limit_pick_in_order(action, make_task, mock_context):
    props = {
        "data": ISSUES,
        "where": {"state": "open", "meta.team": "x"},
        "sort_by": "votes",
        "descending": True,
        "limit": 1,
        "pick": ["title", "meta.team"],
        "output_key": "top",
    }
    result = await action.run(make_task(props), mock_context)

    # Numeric sort ("25" > "3"), and sorting/filtering used fields that pick then drops.
    assert result.output == {"result": [{"title": "c", "meta.team": "x"}], "count": 1}
    assert mock_context.process.properties["top"] == result.output


async def test_sort_numeric_strings_with_nulls_last(action, make_task, mock_context):
    asc = await action.run(make_task({"data": ISSUES, "sort_by": "votes"}), mock_context)
    desc = await action.run(
        make_task({"data": ISSUES, "sort_by": "votes", "descending": True}), mock_context
    )

    assert [i["title"] for i in asc.output["result"]] == ["a", "b", "c", "d"]
    assert [i["title"] for i in desc.output["result"]] == ["c", "b", "a", "d"]


async def test_sort_text_and_mixed_types(action, make_task, mock_context):
    data = [{"k": "pear"}, {"k": "apple"}, {"k": 3}]
    result = await action.run(make_task({"data": data, "sort_by": "k"}), mock_context)

    assert [i["k"] for i in result.output["result"]] == [3, "apple", "pear"]


async def test_where_compares_as_text(action, make_task, mock_context):
    result = await action.run(
        make_task({"data": ISSUES, "where": {"votes": 10}, "pick": "title"}), mock_context
    )

    assert result.output["result"] == [{"title": "b"}]


async def test_where_missing_field_matches_nothing(action, make_task, mock_context):
    result = await action.run(make_task({"data": ISSUES, "where": {"nope": "x"}}), mock_context)

    assert result.output == {"result": [], "count": 0}


async def test_sort_is_stable(action, make_task, mock_context):
    result = await action.run(
        make_task({"data": ISSUES, "sort_by": "meta.team", "pick": "title"}), mock_context
    )

    assert [i["title"] for i in result.output["result"]] == ["a", "c", "b", "d"]


async def test_pick_from_dict(action, make_task, mock_context):
    result = await action.run(
        make_task({"data": ISSUES[0], "pick": ["title", "missing"]}), mock_context
    )

    assert result.output == {"result": {"title": "a", "missing": None}}


async def test_fenced_llm_reply(action, make_task, mock_context):
    mock_context.process.properties["llm_response"] = (
        'Here you go:\n```json\n{"items": [{"n": 1}, {"n": 2}]}\n```'
    )
    result = await action.run(
        make_task({"data": "{{llm_response}}", "path": "items[*].n"}), mock_context
    )

    assert result.output["result"] == [1, 2]


async def test_template_keeps_structure(action, make_task, mock_context):
    mock_context.process.properties["csv_rows"] = {"rows": [{"a": "1"}, {"a": "2"}]}
    result = await action.run(make_task({"data": "{{csv_rows.rows}}", "limit": 1}), mock_context)

    assert result.output["result"] == [{"a": "1"}]


@pytest.mark.parametrize(
    ("props", "message"),
    [
        ({"data": "no json here"}, "transform_json"),
        ({"data": {"a": 1}, "where": {"a": 1}}, "'where' needs a list"),
        ({"data": [1], "where": ["a"]}, "mapping"),
        ({"data": {"a": 1}, "sort_by": "a"}, "'sort_by' needs a list"),
        ({"data": {"a": 1}, "limit": 1}, "'limit' needs a list"),
        ({"data": [1], "limit": "x"}, "integer"),
        ({"data": 5, "pick": ["a"]}, "'pick' needs"),
        ({"data": [1], "path": "a..b"}, "invalid path"),
        ({}, "'data' is required"),
    ],
)
async def test_bad_input_fails(action, make_task, mock_context, props, message):
    result = await action.run(make_task(props), mock_context)

    assert not result.success
    assert message in result.error
    assert "json_result" not in mock_context.process.properties
