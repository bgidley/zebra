"""Tests for ParseCsvAction."""

import pytest

from zebra_tasks.data._common import MAX_INPUT_CHARS
from zebra_tasks.data.csv_parse import ParseCsvAction


@pytest.fixture
def action():
    return ParseCsvAction()


async def test_header_rows(action, make_task, mock_context):
    result = await action.run(make_task({"data": "name,age\nAnn,30\nBob,41\n"}), mock_context)

    assert result.success
    assert result.output == {
        "rows": [{"name": "Ann", "age": "30"}, {"name": "Bob", "age": "41"}],
        "columns": ["name", "age"],
        "count": 2,
        "truncated": False,
    }
    assert mock_context.process.properties["csv_rows"] == result.output


async def test_headerless_rows(action, make_task, mock_context):
    result = await action.run(
        make_task({"data": "a,b\nc,d", "has_header": False, "output_key": "grid"}), mock_context
    )

    assert result.output["rows"] == [["a", "b"], ["c", "d"]]
    assert result.output["columns"] == []
    assert mock_context.process.properties["grid"]["count"] == 2


async def test_delimiter_and_quoting(action, make_task, mock_context):
    data = 'name;note\nAnn;"likes; semicolons"\n'
    result = await action.run(make_task({"data": data, "delimiter": ";"}), mock_context)

    assert result.output["rows"] == [{"name": "Ann", "note": "likes; semicolons"}]


async def test_ragged_rows_padded_and_trimmed(action, make_task, mock_context):
    result = await action.run(make_task({"data": "a,b,c\n1\n1,2,3,4\n\n"}), mock_context)

    assert result.output["rows"] == [
        {"a": "1", "b": "", "c": ""},
        {"a": "1", "b": "2", "c": "3"},
    ]


async def test_quoted_newline_kept_in_cell(action, make_task, mock_context):
    result = await action.run(make_task({"data": 'a,b\n"line 1\nline 2",x\n'}), mock_context)

    assert result.output["rows"] == [{"a": "line 1\nline 2", "b": "x"}]


async def test_bom_blank_and_duplicate_headers(action, make_task, mock_context):
    result = await action.run(make_task({"data": "﻿id, ,id,id\n1,2,3,4"}), mock_context)

    assert result.output["columns"] == ["id", "column_2", "id_2", "id_3"]
    assert result.output["rows"] == [{"id": "1", "column_2": "2", "id_2": "3", "id_3": "4"}]


async def test_truncated_at_max_rows(action, make_task, mock_context):
    data = "n\n" + "\n".join(str(i) for i in range(10))
    result = await action.run(make_task({"data": data, "max_rows": 3}), mock_context)

    assert result.output["count"] == 3
    assert result.output["truncated"] is True
    assert [r["n"] for r in result.output["rows"]] == ["0", "1", "2"]


async def test_exactly_max_rows_not_truncated(action, make_task, mock_context):
    result = await action.run(make_task({"data": "n\n1\n2", "max_rows": 2}), mock_context)

    assert result.output["truncated"] is False


async def test_template_input(action, make_task, mock_context):
    mock_context.process.properties["read_file"] = {"content": "x\n1"}
    result = await action.run(make_task({"data": "{{read_file.content}}"}), mock_context)

    assert result.output["rows"] == [{"x": "1"}]


@pytest.mark.parametrize(
    ("props", "message"),
    [
        ({}, "'data' is required"),
        ({"data": "   "}, "empty"),
        ({"data": ["a"]}, "must be text"),
        ({"data": "a,b", "delimiter": ";;"}, "one character"),
        ({"data": "a,b", "max_rows": "lots"}, "integer"),
        ({"data": "x" * (MAX_INPUT_CHARS + 1)}, "limit"),
    ],
)
async def test_bad_input_fails(action, make_task, mock_context, props, message):
    result = await action.run(make_task(props), mock_context)

    assert not result.success
    assert message in result.error
    assert "csv_rows" not in mock_context.process.properties
