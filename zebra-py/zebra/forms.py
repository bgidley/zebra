"""JSON Schema to form field conversion and validation.

Converts JSON Schema definitions (used in human task properties) into
form field descriptors that can be rendered by templates, and validates
form submissions against the schema.

Supports a practical subset of JSON Schema:
- type: string, number, integer, boolean, array
- format: multiline, date, email, url, date-time
- enum: for select dropdowns
- required, default, minLength, maxLength, minimum, maximum
- title, description for labels and help text
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FormField:
    """A renderable form field derived from JSON Schema."""

    name: str
    widget: str  # "text", "textarea", "number", "select", "checkbox", "date", "email", "url"
    title: str
    description: str | None = None
    required: bool = False
    default: Any = None
    enum: list[str] | None = None
    enum_labels: list[str] | None = None  # Human-readable labels for enum values
    min_length: int | None = None
    max_length: int | None = None
    minimum: float | None = None
    maximum: float | None = None
    pattern: str | None = None
    placeholder: str | None = None


@dataclass
class FormSchema:
    """A complete form schema with fields, title, and metadata."""

    title: str
    description: str | None = None
    fields: list[FormField] = field(default_factory=list)


@dataclass
class ValidationError:
    """A validation error for a specific field."""

    field: str
    message: str


# Widget mapping from JSON Schema type + format
_WIDGET_MAP: dict[tuple[str, str | None], str] = {
    ("string", None): "text",
    ("string", "multiline"): "textarea",
    ("string", "date"): "date",
    ("string", "date-time"): "datetime",
    ("string", "email"): "email",
    ("string", "url"): "url",
    ("number", None): "number",
    ("integer", None): "number",
    ("boolean", None): "checkbox",
    ("array", None): "multiselect",
}


def schema_to_form(schema: dict[str, Any]) -> FormSchema:
    """Convert a JSON Schema object into a FormSchema with ordered fields.

    Args:
        schema: A JSON Schema dict with type "object" and "properties".

    Returns:
        FormSchema with fields in the order they appear in the schema.

    Example schema::

        {
            "type": "object",
            "title": "Bug Report",
            "required": ["summary", "severity"],
            "properties": {
                "summary": {"type": "string", "title": "Summary", "minLength": 10},
                "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                "details": {"type": "string", "format": "multiline"}
            }
        }
    """
    title = schema.get("title", "")
    description = schema.get("description")
    required_fields = set(schema.get("required", []))
    properties = schema.get("properties", {})

    fields = []
    for name, prop in properties.items():
        field_obj = _property_to_field(name, prop, name in required_fields)
        fields.append(field_obj)

    return FormSchema(title=title, description=description, fields=fields)


def _property_to_field(name: str, prop: dict[str, Any], required: bool) -> FormField:
    """Convert a single JSON Schema property to a FormField."""
    prop_type = prop.get("type", "string")
    prop_format = prop.get("format")
    enum = prop.get("enum")

    # Determine widget
    if enum and prop_type == "string":
        widget = "select"
    elif enum and prop_type == "array":
        widget = "multiselect"
    else:
        widget = _WIDGET_MAP.get((prop_type, prop_format), "text")

    # Title defaults to humanized field name
    title = prop.get("title", _humanize(name))

    # Enum labels
    enum_labels = prop.get("enumLabels")
    if enum and not enum_labels:
        enum_labels = [_humanize(str(v)) for v in enum]

    return FormField(
        name=name,
        widget=widget,
        title=title,
        description=prop.get("description"),
        required=required,
        default=prop.get("default"),
        enum=enum,
        enum_labels=enum_labels,
        min_length=prop.get("minLength"),
        max_length=prop.get("maxLength"),
        minimum=prop.get("minimum"),
        maximum=prop.get("maximum"),
        pattern=prop.get("pattern"),
        placeholder=prop.get("placeholder"),
    )


def validate_form_data(schema: dict[str, Any], data: dict[str, Any]) -> list[ValidationError]:
    """Validate form submission data against a JSON Schema.

    Performs basic validation without the jsonschema library:
    - Required field checks
    - Type coercion and checking
    - minLength/maxLength for strings
    - minimum/maximum for numbers
    - enum membership
    - pattern matching

    Args:
        schema: The JSON Schema dict.
        data: The submitted form data.

    Returns:
        List of ValidationError objects. Empty list means valid.
    """
    errors: list[ValidationError] = []
    required_fields = set(schema.get("required", []))
    properties = schema.get("properties", {})

    for field_name, prop in properties.items():
        value = data.get(field_name)
        prop_type = prop.get("type", "string")

        # Required check
        if field_name in required_fields:
            if value is None or (isinstance(value, str) and value.strip() == ""):
                errors.append(ValidationError(field_name, "This field is required."))
                continue

        # Skip validation for empty optional fields
        if value is None or (isinstance(value, str) and value.strip() == ""):
            continue

        # Type-specific validation
        if prop_type == "string":
            if not isinstance(value, str):
                errors.append(ValidationError(field_name, "Must be a string."))
                continue
            _validate_string(field_name, value, prop, errors)

        elif prop_type in ("number", "integer"):
            _validate_number(field_name, value, prop, prop_type, errors)

        elif prop_type == "boolean":
            if not isinstance(value, bool):
                errors.append(ValidationError(field_name, "Must be true or false."))

        elif prop_type == "array":
            if not isinstance(value, list):
                errors.append(ValidationError(field_name, "Must be a list."))
                continue
            enum = prop.get("items", {}).get("enum")
            if enum:
                invalid = [v for v in value if v not in enum]
                if invalid:
                    errors.append(
                        ValidationError(
                            field_name, f"Invalid values: {', '.join(str(v) for v in invalid)}."
                        )
                    )

    return errors


def coerce_form_data(schema: dict[str, Any], raw_data: dict[str, Any]) -> dict[str, Any]:
    """Coerce raw form data (all strings from HTML forms) to proper types.

    HTML forms submit everything as strings. This converts values to the
    types specified in the JSON Schema.

    Args:
        schema: The JSON Schema dict.
        raw_data: Raw form data from request.POST.

    Returns:
        Coerced data dict with proper types.
    """
    properties = schema.get("properties", {})
    result: dict[str, Any] = {}

    for field_name, prop in properties.items():
        value = raw_data.get(field_name)
        prop_type = prop.get("type", "string")

        if value is None or (isinstance(value, str) and value.strip() == ""):
            # Keep None for missing values, let validation handle required
            if field_name in raw_data:
                result[field_name] = prop.get("default")
            continue

        if prop_type == "string":
            result[field_name] = str(value).strip()

        elif prop_type == "integer":
            try:
                result[field_name] = int(value)
            except (ValueError, TypeError):
                result[field_name] = value  # Let validation catch it

        elif prop_type == "number":
            try:
                result[field_name] = float(value)
            except (ValueError, TypeError):
                result[field_name] = value  # Let validation catch it

        elif prop_type == "boolean":
            if isinstance(value, bool):
                result[field_name] = value
            elif isinstance(value, str):
                result[field_name] = value.lower() in ("true", "1", "on", "yes")
            else:
                result[field_name] = bool(value)

        elif prop_type == "array":
            if isinstance(value, list):
                result[field_name] = value
            elif isinstance(value, str):
                # Try JSON array, fall back to single-item list
                try:
                    parsed = json.loads(value)
                    result[field_name] = parsed if isinstance(parsed, list) else [value]
                except json.JSONDecodeError:
                    result[field_name] = [value]
            else:
                result[field_name] = [value]
        else:
            result[field_name] = value

    return result


def get_routes_from_definition(
    task_definition_id: str, routings: list[dict[str, Any]]
) -> list[str]:
    """Extract route names from routing definitions for a task.

    When a task has conditional routings with `condition: route_name`,
    the user needs to choose which route to take. This extracts the
    available route names.

    Args:
        task_definition_id: The task definition ID to find routes for.
        routings: List of routing definition dicts.

    Returns:
        List of route name strings. Empty if no named routes.
    """
    routes = []
    for routing in routings:
        source = routing.get("source_task_id") or routing.get("from")
        if source != task_definition_id:
            continue
        condition = routing.get("condition")
        name = routing.get("name")
        if condition == "route_name" and name:
            routes.append(name)
    return routes


def _validate_string(
    field_name: str,
    value: str,
    prop: dict[str, Any],
    errors: list[ValidationError],
) -> None:
    """Validate a string value against schema constraints."""
    min_len = prop.get("minLength")
    max_len = prop.get("maxLength")
    pattern = prop.get("pattern")
    enum = prop.get("enum")

    if min_len is not None and len(value) < min_len:
        errors.append(ValidationError(field_name, f"Must be at least {min_len} characters."))
    if max_len is not None and len(value) > max_len:
        errors.append(ValidationError(field_name, f"Must be at most {max_len} characters."))
    if pattern is not None and not re.search(pattern, value):
        errors.append(ValidationError(field_name, f"Must match pattern: {pattern}"))
    if enum is not None and value not in enum:
        errors.append(
            ValidationError(field_name, f"Must be one of: {', '.join(str(v) for v in enum)}.")
        )


def _validate_number(
    field_name: str,
    value: Any,
    prop: dict[str, Any],
    prop_type: str,
    errors: list[ValidationError],
) -> None:
    """Validate a number value against schema constraints."""
    # Coerce for validation
    try:
        if prop_type == "integer":
            num_value = int(value) if not isinstance(value, int) else value
        else:
            num_value = float(value) if not isinstance(value, (int, float)) else value
    except (ValueError, TypeError):
        errors.append(ValidationError(field_name, "Must be a valid number."))
        return

    minimum = prop.get("minimum")
    maximum = prop.get("maximum")

    if minimum is not None and num_value < minimum:
        errors.append(ValidationError(field_name, f"Must be at least {minimum}."))
    if maximum is not None and num_value > maximum:
        errors.append(ValidationError(field_name, f"Must be at most {maximum}."))


def _humanize(name: str) -> str:
    """Convert a snake_case or camelCase name to a human-readable title."""
    # Handle snake_case
    result = name.replace("_", " ")
    # Handle camelCase
    result = re.sub(r"([a-z])([A-Z])", r"\1 \2", result)
    return result.title()
