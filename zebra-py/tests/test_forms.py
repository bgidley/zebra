"""Tests for JSON Schema form utilities."""

import pytest

from zebra.forms import (
    FormField,
    FormSchema,
    ValidationError,
    coerce_form_data,
    get_routes_from_definition,
    schema_to_form,
    validate_form_data,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bug_report_schema():
    """A realistic bug report form schema."""
    return {
        "type": "object",
        "title": "Bug Report",
        "description": "Describe the bug you encountered.",
        "required": ["summary", "severity"],
        "properties": {
            "summary": {
                "type": "string",
                "title": "Summary",
                "description": "One-line description of the bug",
                "minLength": 10,
                "maxLength": 200,
                "placeholder": "Brief description...",
            },
            "severity": {
                "type": "string",
                "title": "Severity",
                "enum": ["critical", "high", "medium", "low"],
                "default": "medium",
            },
            "steps_to_reproduce": {
                "type": "string",
                "title": "Steps to Reproduce",
                "format": "multiline",
            },
            "affects_production": {
                "type": "boolean",
                "title": "Affects Production?",
                "default": False,
            },
            "priority_score": {
                "type": "integer",
                "title": "Priority Score",
                "minimum": 1,
                "maximum": 10,
            },
        },
    }


@pytest.fixture
def minimal_schema():
    """A minimal schema with just one field."""
    return {
        "type": "object",
        "properties": {
            "response": {"type": "string"},
        },
    }


# ---------------------------------------------------------------------------
# schema_to_form tests
# ---------------------------------------------------------------------------


class TestSchemaToForm:
    def test_basic_conversion(self, bug_report_schema):
        form = schema_to_form(bug_report_schema)

        assert isinstance(form, FormSchema)
        assert form.title == "Bug Report"
        assert form.description == "Describe the bug you encountered."
        assert len(form.fields) == 5

    def test_field_names_preserve_order(self, bug_report_schema):
        form = schema_to_form(bug_report_schema)
        names = [f.name for f in form.fields]
        assert names == [
            "summary",
            "severity",
            "steps_to_reproduce",
            "affects_production",
            "priority_score",
        ]

    def test_string_field(self, bug_report_schema):
        form = schema_to_form(bug_report_schema)
        summary = form.fields[0]

        assert summary.name == "summary"
        assert summary.widget == "text"
        assert summary.title == "Summary"
        assert summary.description == "One-line description of the bug"
        assert summary.required is True
        assert summary.min_length == 10
        assert summary.max_length == 200
        assert summary.placeholder == "Brief description..."

    def test_enum_field(self, bug_report_schema):
        form = schema_to_form(bug_report_schema)
        severity = form.fields[1]

        assert severity.widget == "select"
        assert severity.enum == ["critical", "high", "medium", "low"]
        assert severity.enum_labels == ["Critical", "High", "Medium", "Low"]
        assert severity.default == "medium"
        assert severity.required is True

    def test_multiline_field(self, bug_report_schema):
        form = schema_to_form(bug_report_schema)
        steps = form.fields[2]

        assert steps.widget == "textarea"
        assert steps.required is False

    def test_boolean_field(self, bug_report_schema):
        form = schema_to_form(bug_report_schema)
        affects = form.fields[3]

        assert affects.widget == "checkbox"
        assert affects.default is False

    def test_integer_field(self, bug_report_schema):
        form = schema_to_form(bug_report_schema)
        score = form.fields[4]

        assert score.widget == "number"
        assert score.minimum == 1
        assert score.maximum == 10

    def test_minimal_schema(self, minimal_schema):
        form = schema_to_form(minimal_schema)

        assert form.title == ""
        assert form.description is None
        assert len(form.fields) == 1
        assert form.fields[0].name == "response"
        assert form.fields[0].required is False

    def test_auto_title_from_field_name(self):
        schema = {
            "type": "object",
            "properties": {
                "first_name": {"type": "string"},
                "emailAddress": {"type": "string"},
            },
        }
        form = schema_to_form(schema)

        assert form.fields[0].title == "First Name"
        assert form.fields[1].title == "Email Address"

    def test_date_format(self):
        schema = {
            "type": "object",
            "properties": {
                "due_date": {"type": "string", "format": "date"},
            },
        }
        form = schema_to_form(schema)
        assert form.fields[0].widget == "date"

    def test_email_format(self):
        schema = {
            "type": "object",
            "properties": {
                "email": {"type": "string", "format": "email"},
            },
        }
        form = schema_to_form(schema)
        assert form.fields[0].widget == "email"

    def test_url_format(self):
        schema = {
            "type": "object",
            "properties": {
                "website": {"type": "string", "format": "url"},
            },
        }
        form = schema_to_form(schema)
        assert form.fields[0].widget == "url"

    def test_number_field(self):
        schema = {
            "type": "object",
            "properties": {
                "temperature": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            },
        }
        form = schema_to_form(schema)
        assert form.fields[0].widget == "number"
        assert form.fields[0].minimum == 0.0
        assert form.fields[0].maximum == 1.0

    def test_array_with_enum(self):
        schema = {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["bug", "feature", "docs"]},
                },
            },
        }
        form = schema_to_form(schema)
        assert form.fields[0].widget == "multiselect"

    def test_empty_schema(self):
        form = schema_to_form({"type": "object"})
        assert form.fields == []
        assert form.title == ""

    def test_custom_enum_labels(self):
        schema = {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["p0", "p1", "p2"],
                    "enumLabels": ["Critical (P0)", "High (P1)", "Medium (P2)"],
                },
            },
        }
        form = schema_to_form(schema)
        assert form.fields[0].enum_labels == ["Critical (P0)", "High (P1)", "Medium (P2)"]

    def test_pattern_field(self):
        schema = {
            "type": "object",
            "properties": {
                "code": {"type": "string", "pattern": "^[A-Z]{3}-\\d{4}$"},
            },
        }
        form = schema_to_form(schema)
        assert form.fields[0].pattern == "^[A-Z]{3}-\\d{4}$"


# ---------------------------------------------------------------------------
# validate_form_data tests
# ---------------------------------------------------------------------------


class TestValidateFormData:
    def test_valid_data(self, bug_report_schema):
        data = {
            "summary": "The login button doesn't work on mobile",
            "severity": "high",
            "steps_to_reproduce": "1. Open on mobile\n2. Tap login",
            "affects_production": True,
            "priority_score": 7,
        }
        errors = validate_form_data(bug_report_schema, data)
        assert errors == []

    def test_missing_required_field(self, bug_report_schema):
        data = {"severity": "high"}  # Missing summary
        errors = validate_form_data(bug_report_schema, data)

        field_names = [e.field for e in errors]
        assert "summary" in field_names

    def test_empty_required_field(self, bug_report_schema):
        data = {"summary": "", "severity": "high"}
        errors = validate_form_data(bug_report_schema, data)

        field_names = [e.field for e in errors]
        assert "summary" in field_names

    def test_min_length(self, bug_report_schema):
        data = {"summary": "short", "severity": "high"}
        errors = validate_form_data(bug_report_schema, data)

        summary_errors = [e for e in errors if e.field == "summary"]
        assert len(summary_errors) == 1
        assert "at least 10" in summary_errors[0].message

    def test_max_length(self, bug_report_schema):
        data = {"summary": "x" * 201, "severity": "high"}
        errors = validate_form_data(bug_report_schema, data)

        summary_errors = [e for e in errors if e.field == "summary"]
        assert len(summary_errors) == 1
        assert "at most 200" in summary_errors[0].message

    def test_invalid_enum_value(self, bug_report_schema):
        data = {"summary": "A valid summary for the bug", "severity": "extreme"}
        errors = validate_form_data(bug_report_schema, data)

        severity_errors = [e for e in errors if e.field == "severity"]
        assert len(severity_errors) == 1
        assert "one of" in severity_errors[0].message

    def test_number_minimum(self, bug_report_schema):
        data = {"summary": "A valid summary for the bug", "severity": "high", "priority_score": 0}
        errors = validate_form_data(bug_report_schema, data)

        score_errors = [e for e in errors if e.field == "priority_score"]
        assert len(score_errors) == 1
        assert "at least 1" in score_errors[0].message

    def test_number_maximum(self, bug_report_schema):
        data = {"summary": "A valid summary for the bug", "severity": "high", "priority_score": 11}
        errors = validate_form_data(bug_report_schema, data)

        score_errors = [e for e in errors if e.field == "priority_score"]
        assert len(score_errors) == 1
        assert "at most 10" in score_errors[0].message

    def test_optional_fields_skipped(self, bug_report_schema):
        """Optional fields with no value should not produce errors."""
        data = {"summary": "A valid summary for the bug", "severity": "high"}
        errors = validate_form_data(bug_report_schema, data)
        assert errors == []

    def test_pattern_validation(self):
        schema = {
            "type": "object",
            "properties": {
                "code": {"type": "string", "pattern": "^[A-Z]{3}-\\d{4}$"},
            },
        }
        errors = validate_form_data(schema, {"code": "abc-1234"})
        assert len(errors) == 1
        assert "pattern" in errors[0].message

        errors = validate_form_data(schema, {"code": "ABC-1234"})
        assert errors == []

    def test_boolean_type_check(self):
        schema = {
            "type": "object",
            "properties": {"flag": {"type": "boolean"}},
        }
        errors = validate_form_data(schema, {"flag": "not_a_bool"})
        assert len(errors) == 1

        errors = validate_form_data(schema, {"flag": True})
        assert errors == []

    def test_array_enum_validation(self):
        schema = {
            "type": "object",
            "properties": {
                "tags": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["bug", "feature"]},
                },
            },
        }
        errors = validate_form_data(schema, {"tags": ["bug", "invalid"]})
        assert len(errors) == 1
        assert "invalid" in errors[0].message.lower()

    def test_multiple_errors(self):
        schema = {
            "type": "object",
            "required": ["a", "b"],
            "properties": {
                "a": {"type": "string"},
                "b": {"type": "string"},
            },
        }
        errors = validate_form_data(schema, {})
        assert len(errors) == 2


# ---------------------------------------------------------------------------
# coerce_form_data tests
# ---------------------------------------------------------------------------


class TestCoerceFormData:
    def test_string_coercion(self):
        schema = {"properties": {"name": {"type": "string"}}}
        result = coerce_form_data(schema, {"name": "  Alice  "})
        assert result["name"] == "Alice"

    def test_integer_coercion(self):
        schema = {"properties": {"count": {"type": "integer"}}}
        result = coerce_form_data(schema, {"count": "42"})
        assert result["count"] == 42

    def test_number_coercion(self):
        schema = {"properties": {"rate": {"type": "number"}}}
        result = coerce_form_data(schema, {"rate": "3.14"})
        assert result["rate"] == 3.14

    def test_boolean_coercion_true_values(self):
        schema = {"properties": {"flag": {"type": "boolean"}}}
        for value in ["true", "1", "on", "yes", "True", "YES"]:
            result = coerce_form_data(schema, {"flag": value})
            assert result["flag"] is True, f"Failed for {value}"

    def test_boolean_coercion_false_values(self):
        schema = {"properties": {"flag": {"type": "boolean"}}}
        for value in ["false", "0", "off", "no", "False"]:
            result = coerce_form_data(schema, {"flag": value})
            assert result["flag"] is False, f"Failed for {value}"

    def test_array_from_json_string(self):
        schema = {"properties": {"tags": {"type": "array"}}}
        result = coerce_form_data(schema, {"tags": '["a", "b"]'})
        assert result["tags"] == ["a", "b"]

    def test_array_from_single_value(self):
        schema = {"properties": {"tags": {"type": "array"}}}
        result = coerce_form_data(schema, {"tags": "single"})
        assert result["tags"] == ["single"]

    def test_array_passthrough(self):
        schema = {"properties": {"tags": {"type": "array"}}}
        result = coerce_form_data(schema, {"tags": ["a", "b"]})
        assert result["tags"] == ["a", "b"]

    def test_empty_string_gets_default(self):
        schema = {"properties": {"severity": {"type": "string", "default": "medium"}}}
        result = coerce_form_data(schema, {"severity": ""})
        assert result["severity"] == "medium"

    def test_missing_field_skipped(self):
        schema = {"properties": {"name": {"type": "string"}}}
        result = coerce_form_data(schema, {})
        assert "name" not in result

    def test_invalid_integer_passthrough(self):
        """Invalid values pass through for validation to catch."""
        schema = {"properties": {"count": {"type": "integer"}}}
        result = coerce_form_data(schema, {"count": "not_a_number"})
        assert result["count"] == "not_a_number"


# ---------------------------------------------------------------------------
# get_routes_from_definition tests
# ---------------------------------------------------------------------------


class TestGetRoutesFromDefinition:
    def test_extracts_named_routes(self):
        routings = [
            {"from": "verify", "to": "fix", "condition": "route_name", "name": "no"},
            {"from": "verify", "to": "complete", "condition": "route_name", "name": "yes"},
        ]
        routes = get_routes_from_definition("verify", routings)
        assert routes == ["no", "yes"]

    def test_ignores_other_tasks(self):
        routings = [
            {"from": "verify", "to": "complete", "condition": "route_name", "name": "yes"},
            {"from": "other", "to": "elsewhere", "condition": "route_name", "name": "maybe"},
        ]
        routes = get_routes_from_definition("verify", routings)
        assert routes == ["yes"]

    def test_ignores_unconditional_routes(self):
        routings = [
            {"from": "task_a", "to": "task_b"},
        ]
        routes = get_routes_from_definition("task_a", routings)
        assert routes == []

    def test_empty_routings(self):
        routes = get_routes_from_definition("anything", [])
        assert routes == []

    def test_source_task_id_key(self):
        """Supports both 'from' and 'source_task_id' keys."""
        routings = [
            {
                "source_task_id": "review",
                "dest_task_id": "done",
                "condition": "route_name",
                "name": "approve",
            },
        ]
        routes = get_routes_from_definition("review", routings)
        assert routes == ["approve"]
