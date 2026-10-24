"""End-to-end: data actions in a real engine workflow, wired by templates (#66)."""

from importlib.metadata import entry_points

from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessState, TaskInstance, TaskResult
from zebra.definitions.loader import load_definition_from_yaml
from zebra.storage.memory import InMemoryStore
from zebra.tasks.base import ExecutionContext, TaskAction
from zebra.tasks.registry import ActionRegistry

from zebra_tasks.data.csv_parse import ParseCsvAction
from zebra_tasks.data.json_transform import TransformJsonAction
from zebra_tasks.data.xml_parse import ParseXmlAction

WORKFLOW = """
name: "Top Open Issues"
first_task: parse
tasks:
  parse:
    name: "Parse export"
    action: parse_csv
    properties:
      data: "{{export}}"
      output_key: issues
  top:
    name: "Top open issue"
    action: transform_json
    properties:
      data: "{{issues.rows}}"
      where: {state: open}
      sort_by: votes
      descending: true
      limit: 1
      output_key: top_issue
  title:
    name: "Its title"
    action: transform_json
    properties:
      data: "{{top_issue.result}}"
      path: "[0].title"
      output_key: top_title
  report:
    name: "Report"
    action: capture
    properties:
      message: "Top open issue: {{top_title.result}}"
routings:
  - from: parse
    to: top
  - from: top
    to: title
  - from: title
    to: report
"""


class _Capture(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        message = context.resolve_template(task.properties["message"])
        context.set_process_property("report", message)
        return TaskResult.ok(output=message)


async def test_csv_to_filtered_value_downstream():
    registry = ActionRegistry()
    registry.register_defaults()
    registry.register_action("parse_csv", ParseCsvAction)
    registry.register_action("transform_json", TransformJsonAction)
    registry.register_action("capture", _Capture)
    engine = WorkflowEngine(InMemoryStore(), registry)

    export = "title,state,votes\nalpha,open,3\nbeta,closed,99\ngamma,open,12\n"
    process = await engine.create_process(
        load_definition_from_yaml(WORKFLOW), properties={"export": export}
    )
    await engine.start_process(process.id)

    process = await engine.store.load_process(process.id)
    assert process.state == ProcessState.COMPLETE
    assert process.properties["issues"]["count"] == 3
    # beta has the most votes but is closed; gamma (12) beats alpha (3) numerically.
    assert process.properties["top_issue"]["result"] == [
        {"title": "gamma", "state": "open", "votes": "12"}
    ]
    assert process.properties["report"] == "Top open issue: gamma"


def test_registered_entry_points_and_reversible():
    registered = {ep.name: ep for ep in entry_points(group="zebra.tasks")}
    for name, cls in (
        ("parse_csv", ParseCsvAction),
        ("parse_xml", ParseXmlAction),
        ("transform_json", TransformJsonAction),
    ):
        assert registered[name].load() is cls
        assert cls.reversibility_hint == "always_reversible"
        assert cls.get_metadata().description
