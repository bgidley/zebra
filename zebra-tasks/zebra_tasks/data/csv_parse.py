"""CSV parsing task action."""

import csv
import io
import logging

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.data._common import input_text

logger = logging.getLogger(__name__)

DEFAULT_MAX_ROWS = 1000
MAX_ROWS_CAP = 10_000


def unique_columns(header: list[str]) -> list[str]:
    """Strip header names; a blank becomes ``column_N``, a repeat gets ``_2``, ``_3``…"""
    columns: list[str] = []
    seen: set[str] = set()
    for i, raw in enumerate(header, start=1):
        base = raw.strip() or f"column_{i}"
        name, n = base, 2
        while name in seen:
            name, n = f"{base}_{n}", n + 1
        seen.add(name)
        columns.append(name)
    return columns


class ParseCsvAction(TaskAction):
    """Parse CSV text into rows.

    With a header row (the default) each row is a dict keyed by column name;
    short rows are padded with "" and extra cells dropped, so every row has the
    same keys. A leading BOM is dropped; blank header names become ``column_N``
    and repeats get ``_2``, ``_3``, so no value is lost. Values stay strings.

    Example workflow usage:
        ```yaml
        tasks:
          parse:
            name: "Parse export"
            action: parse_csv
            properties:
              data: "{{read_export.content}}"
              output_key: export_rows
        ```

    Output:
        - rows: list of dicts (or lists when has_header is false)
        - columns: header names (empty without a header)
        - count: number of rows returned
        - truncated: true when rows were cut at max_rows
    """

    description = (
        "Parse CSV text into a list of rows (dicts keyed by header, or lists), without an LLM call."
    )
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="data",
            type="string",
            description="CSV text, usually a {{template}} of an earlier task's output",
            required=True,
        ),
        ParameterDef(
            name="has_header",
            type="bool",
            description="First row holds column names",
            required=False,
            default=True,
        ),
        ParameterDef(
            name="delimiter",
            type="string",
            description="One-character field delimiter",
            required=False,
            default=",",
        ),
        ParameterDef(
            name="max_rows",
            type="int",
            description=f"Maximum data rows to return (cap {MAX_ROWS_CAP})",
            required=False,
            default=DEFAULT_MAX_ROWS,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the result",
            required=False,
            default="csv_rows",
        ),
    ]

    outputs = [
        ParameterDef(name="rows", type="list", description="Parsed rows", required=True),
        ParameterDef(name="columns", type="list", description="Header names", required=True),
        ParameterDef(name="count", type="int", description="Rows returned", required=True),
        ParameterDef(name="truncated", type="bool", description="Cut at max_rows", required=True),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Parse the CSV text and store the rows."""
        try:
            text = input_text(task, context)
        except ValueError as e:
            return TaskResult.fail(f"parse_csv: {e}")

        delimiter = str(task.properties.get("delimiter", ","))
        if len(delimiter) != 1:
            return TaskResult.fail("parse_csv: 'delimiter' must be one character")
        try:
            max_rows = min(int(task.properties.get("max_rows", DEFAULT_MAX_ROWS)), MAX_ROWS_CAP)
        except (TypeError, ValueError):
            return TaskResult.fail("parse_csv: 'max_rows' must be an integer")
        has_header = bool(task.properties.get("has_header", True))

        reader = csv.reader(io.StringIO(text.removeprefix("﻿")), delimiter=delimiter)
        try:
            columns = unique_columns(next(reader, [])) if has_header else []
            rows: list = []
            truncated = False
            for record in reader:
                if not record:
                    continue
                if len(rows) >= max_rows:
                    truncated = True
                    break
                if has_header:
                    padded = record[: len(columns)] + [""] * (len(columns) - len(record))
                    rows.append(dict(zip(columns, padded)))
                else:
                    rows.append(record)
        except csv.Error as e:
            return TaskResult.fail(f"parse_csv: invalid CSV: {e}")

        result = {"rows": rows, "columns": columns, "count": len(rows), "truncated": truncated}
        context.set_process_property(task.properties.get("output_key", "csv_rows"), result)
        logger.info("parse_csv: %d row(s)%s", len(rows), " (truncated)" if truncated else "")
        return TaskResult.ok(output=result)
