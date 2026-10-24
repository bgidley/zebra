"""XML parsing task action."""

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

from zebra.core.models import TaskInstance, TaskResult
from zebra.tasks.base import ExecutionContext, ParameterDef, TaskAction

from zebra_tasks.data._common import input_text

logger = logging.getLogger(__name__)

# DTDs are the only route to entity expansion (billion laughs, external
# entities); feeds and API replies don't need them, so refuse them outright.
_DTD_RE = re.compile(r"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)


def _local(name: str) -> str:
    """Drop a ``{namespace}`` prefix from a tag or attribute name."""
    return name.rsplit("}", 1)[-1]


def element_to_value(element: ET.Element) -> Any:
    """Convert an element to a JSON-serializable value.

    A leaf without attributes is its text (``None`` if empty). Otherwise a dict
    of ``@attr`` keys, child tags (a list when a tag repeats) and ``#text``.
    """
    text = (element.text or "").strip()
    children = list(element)
    if not children and not element.attrib:
        return text or None

    value: dict[str, Any] = {f"@{_local(k)}": v for k, v in element.attrib.items()}
    for child in children:
        tag = _local(child.tag)
        child_value = element_to_value(child)
        if tag not in value:
            value[tag] = child_value
        elif isinstance(value[tag], list):
            value[tag].append(child_value)
        else:
            value[tag] = [value[tag], child_value]
    if text:
        value["#text"] = text
    return value


class ParseXmlAction(TaskAction):
    """Parse XML text into a nested dict.

    Mapping: attributes become ``@name`` keys, repeated child tags become lists,
    the text of an element with attributes or children is ``#text``, and a plain
    leaf is its text. Namespaces are dropped to local names. Documents with a
    DOCTYPE or ENTITY declaration are refused.

    Example workflow usage:
        ```yaml
        tasks:
          parse_feed:
            name: "Parse RSS"
            action: parse_xml
            properties:
              data: "{{fetch_feed.body}}"
              output_key: feed
        ```

    Output:
        - data: ``{root_tag: value}``
        - root: the root element's tag
    """

    description = (
        "Parse XML text into a nested dict (@attributes, #text, repeated tags as lists); "
        "refuses DOCTYPE/ENTITY declarations."
    )
    reversibility_hint = "always_reversible"

    inputs = [
        ParameterDef(
            name="data",
            type="string",
            description="XML text, usually a {{template}} of an earlier task's output",
            required=True,
        ),
        ParameterDef(
            name="output_key",
            type="string",
            description="Process property key to store the result",
            required=False,
            default="xml_data",
        ),
    ]

    outputs = [
        ParameterDef(name="data", type="dict", description="{root_tag: value}", required=True),
        ParameterDef(name="root", type="string", description="Root tag", required=True),
    ]

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        """Parse the XML text and store the dict."""
        try:
            text = input_text(task, context)
        except ValueError as e:
            return TaskResult.fail(f"parse_xml: {e}")
        if _DTD_RE.search(text):
            return TaskResult.fail("parse_xml: DOCTYPE and ENTITY declarations are not allowed")

        try:
            root = ET.fromstring(text.strip())
        except ET.ParseError as e:
            return TaskResult.fail(f"parse_xml: invalid XML: {e}")

        tag = _local(root.tag)
        result = {"data": {tag: element_to_value(root)}, "root": tag}
        context.set_process_property(task.properties.get("output_key", "xml_data"), result)
        logger.info("parse_xml: parsed <%s>", tag)
        return TaskResult.ok(output=result)
