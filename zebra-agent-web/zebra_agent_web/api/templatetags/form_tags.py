"""Template tags for rendering JSON Schema forms as Tailwind-styled HTML.

Usage in templates::

    {% load form_tags %}
    {% render_schema_form form field_errors submitted_values %}

Where ``form`` is a ``FormSchema``, ``field_errors`` is a dict mapping
field names to lists of error strings, and ``submitted_values`` is an
optional dict of previously submitted data to repopulate on validation error.
"""

from typing import Any

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

from zebra.forms import FormField, FormSchema

register = template.Library()

# Sentinel to distinguish "no value submitted" from None/empty string
_UNSET = object()

# Tailwind CSS classes
INPUT_CLASS = (
    "block w-full rounded-md bg-gray-700 border border-gray-600 text-gray-100 "
    "placeholder-gray-400 px-3 py-2 text-sm focus:outline-none focus:ring-2 "
    "focus:ring-indigo-500 focus:border-indigo-500"
)
INPUT_ERROR_CLASS = (
    "block w-full rounded-md bg-gray-700 border border-red-500 text-gray-100 "
    "placeholder-gray-400 px-3 py-2 text-sm focus:outline-none focus:ring-2 "
    "focus:ring-red-500 focus:border-red-500"
)
SELECT_CLASS = INPUT_CLASS
TEXTAREA_CLASS = INPUT_CLASS + " min-h-[100px]"
CHECKBOX_CLASS = (
    "h-4 w-4 rounded bg-gray-700 border-gray-600 text-indigo-500 "
    "focus:ring-indigo-500 focus:ring-offset-gray-800"
)
LABEL_CLASS = "block text-sm font-medium text-gray-300 mb-1"
DESCRIPTION_CLASS = "text-xs text-gray-400 mt-1"
ERROR_CLASS = "text-xs text-red-400 mt-1"
REQUIRED_MARKER = '<span class="text-red-400 ml-0.5">*</span>'


@register.simple_tag
def render_schema_form(
    form: FormSchema,
    field_errors: dict | None = None,
    submitted_values: dict | None = None,
) -> str:
    """Render a FormSchema as HTML form fields.

    Args:
        form: The FormSchema with fields to render.
        field_errors: Optional dict of {field_name: [error_messages]}.
        submitted_values: Optional dict of previously submitted values to
            repopulate form fields on validation error.

    Returns:
        Safe HTML string with all form fields.
    """
    if field_errors is None:
        field_errors = {}
    if not isinstance(submitted_values, dict):
        submitted_values = {}

    parts = []
    for field in form.fields:
        errors = field_errors.get(field.name, [])
        value = submitted_values.get(field.name, _UNSET)
        parts.append(_render_field(field, errors, value))

    return mark_safe("\n".join(parts))


def _render_field(field: FormField, errors: list[str], value: Any = _UNSET) -> str:
    """Render a single form field."""
    has_error = len(errors) > 0
    input_class = INPUT_ERROR_CLASS if has_error else INPUT_CLASS

    if field.widget == "checkbox":
        return _render_checkbox(field, errors, value)
    elif field.widget == "select":
        return _render_select(field, errors, value)
    elif field.widget == "multiselect":
        return _render_multiselect(field, errors, value)
    elif field.widget == "textarea":
        return _render_textarea(field, input_class, errors, value)
    else:
        return _render_input(field, input_class, errors, value)


def _render_label(field: FormField) -> str:
    """Render a field label."""
    required = REQUIRED_MARKER if field.required else ""
    return f'<label for="field_{escape(field.name)}" class="{LABEL_CLASS}">{escape(field.title)}{required}</label>'


def _render_description(field: FormField) -> str:
    """Render field description/help text."""
    if not field.description:
        return ""
    return f'<p class="{DESCRIPTION_CLASS}">{escape(field.description)}</p>'


def _render_errors(errors: list[str]) -> str:
    """Render validation errors."""
    if not errors:
        return ""
    parts = [f'<p class="{ERROR_CLASS}">{escape(e)}</p>' for e in errors]
    return "\n".join(parts)


def _effective_value(value: Any, default: Any) -> Any:
    """Return the submitted value if present, otherwise the field default."""
    if value is _UNSET:
        return default
    return value


def _render_input(
    field: FormField, input_class: str, errors: list[str], value: Any = _UNSET
) -> str:
    """Render a text/number/email/date input."""
    input_type = {
        "text": "text",
        "number": "number",
        "email": "email",
        "url": "url",
        "date": "date",
        "datetime": "datetime-local",
    }.get(field.widget, "text")

    attrs = [
        f'type="{input_type}"',
        f'id="field_{escape(field.name)}"',
        f'name="{escape(field.name)}"',
        f'class="{input_class}"',
    ]

    if field.required:
        attrs.append("required")
    if field.placeholder:
        attrs.append(f'placeholder="{escape(field.placeholder)}"')

    effective = _effective_value(value, field.default)
    if effective is not None and effective != "":
        attrs.append(f'value="{escape(str(effective))}"')

    if field.min_length:
        attrs.append(f'minlength="{field.min_length}"')
    if field.max_length:
        attrs.append(f'maxlength="{field.max_length}"')
    if field.minimum is not None:
        attrs.append(f'min="{field.minimum}"')
    if field.maximum is not None:
        attrs.append(f'max="{field.maximum}"')
    if field.pattern:
        attrs.append(f'pattern="{escape(field.pattern)}"')
    if input_type == "number" and field.widget == "number":
        # Allow decimals for float fields
        attrs.append('step="any"')

    return f"""<div class="mb-4">
    {_render_label(field)}
    <input {" ".join(attrs)} />
    {_render_description(field)}
    {_render_errors(errors)}
</div>"""


def _render_textarea(
    field: FormField, input_class: str, errors: list[str], value: Any = _UNSET
) -> str:
    """Render a textarea."""
    textarea_class = input_class + " min-h-[100px]"
    attrs = [
        f'id="field_{escape(field.name)}"',
        f'name="{escape(field.name)}"',
        f'class="{textarea_class}"',
        'rows="4"',
    ]

    if field.required:
        attrs.append("required")
    if field.placeholder:
        attrs.append(f'placeholder="{escape(field.placeholder)}"')
    if field.min_length:
        attrs.append(f'minlength="{field.min_length}"')
    if field.max_length:
        attrs.append(f'maxlength="{field.max_length}"')

    effective = _effective_value(value, field.default)
    content = escape(str(effective)) if effective else ""

    return f"""<div class="mb-4">
    {_render_label(field)}
    <textarea {" ".join(attrs)}>{content}</textarea>
    {_render_description(field)}
    {_render_errors(errors)}
</div>"""


def _render_select(field: FormField, errors: list[str], value: Any = _UNSET) -> str:
    """Render a select dropdown."""
    has_error = len(errors) > 0
    select_class = INPUT_ERROR_CLASS if has_error else SELECT_CLASS

    attrs = [
        f'id="field_{escape(field.name)}"',
        f'name="{escape(field.name)}"',
        f'class="{select_class}"',
    ]
    if field.required:
        attrs.append("required")

    effective = _effective_value(value, field.default)

    options = ['<option value="">-- Select --</option>']
    if field.enum:
        labels = field.enum_labels or field.enum
        for opt_value, label in zip(field.enum, labels):
            selected = " selected" if effective == opt_value else ""
            options.append(
                f'<option value="{escape(str(opt_value))}"{selected}>{escape(str(label))}</option>'
            )

    return f"""<div class="mb-4">
    {_render_label(field)}
    <select {" ".join(attrs)}>
        {"".join(options)}
    </select>
    {_render_description(field)}
    {_render_errors(errors)}
</div>"""


def _render_checkbox(field: FormField, errors: list[str], value: Any = _UNSET) -> str:
    """Render a checkbox."""
    effective = _effective_value(value, field.default)
    checked = " checked" if effective else ""

    return f"""<div class="mb-4">
    <div class="flex items-center gap-2">
        <input type="checkbox" id="field_{escape(field.name)}" name="{escape(field.name)}"
               class="{CHECKBOX_CLASS}" value="true"{checked} />
        <label for="field_{escape(field.name)}" class="text-sm text-gray-300">{escape(field.title)}</label>
    </div>
    {_render_description(field)}
    {_render_errors(errors)}
</div>"""


def _render_multiselect(field: FormField, errors: list[str], value: Any = _UNSET) -> str:
    """Render a multi-select as checkboxes."""
    effective = _effective_value(value, field.default)
    selected_values = set(effective) if isinstance(effective, list) else set()

    checkboxes = []
    if field.enum:
        labels = field.enum_labels or field.enum
        for opt_value, label in zip(field.enum, labels):
            is_checked = " checked" if opt_value in selected_values else ""
            checkboxes.append(
                f"""<label class="flex items-center gap-2">
    <input type="checkbox" name="{escape(field.name)}" value="{escape(str(opt_value))}"
           class="{CHECKBOX_CLASS}"{is_checked} />
    <span class="text-sm text-gray-300">{escape(str(label))}</span>
</label>"""
            )

    return f"""<div class="mb-4">
    {_render_label(field)}
    <div class="space-y-2 mt-1">
        {"".join(checkboxes)}
    </div>
    {_render_description(field)}
    {_render_errors(errors)}
</div>"""
