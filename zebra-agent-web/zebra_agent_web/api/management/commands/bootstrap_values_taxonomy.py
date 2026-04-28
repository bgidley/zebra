"""Django management command: LLM-bootstrap the values-taxonomy starter set.

Usage:
    python manage.py bootstrap_values_taxonomy
    python manage.py bootstrap_values_taxonomy --force
    python manage.py bootstrap_values_taxonomy --output path/to/file.yaml --force

Calls Claude to draft a starter taxonomy across the four values-profile
fields, then writes a reviewable YAML fixture. The fixture is NOT loaded
into the database directly — the maintainer reviews it, commits it, and a
data migration loads it on first ``migrate``.

By default, the command refuses to overwrite an existing fixture file. Pass
``--force`` to overwrite (or accept the default of writing to a ``.new``
sibling for diff review when the path exists without ``--force``).
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import yaml
from django.core.management.base import BaseCommand, CommandError
from zebra_tasks.llm import get_provider
from zebra_tasks.llm.base import Message

_DEFAULT_OUTPUT = (
    Path(__file__).parent.parent.parent.parent / "fixtures" / "values_taxonomy_seed.yaml"
)


_FIELDS = ("core_values", "ethical_positions", "priorities", "deal_breakers")


_SYSTEM_PROMPT = """\
You are seeding a values-profile taxonomy for an AI-assistant project. The
taxonomy has four fields:

- core_values        (e.g. honesty, growth, family, autonomy)
- ethical_positions  (e.g. animal-welfare, environmental-care, fairness)
- priorities         (life domains, e.g. family, career, health, learning)
- deal_breakers      (absolute constraints, e.g. no-deception, no-harm-to-children)

For each field, propose 8–12 sensible starter tags. Use kebab-case slugs,
human-readable labels, and a short (one-sentence) description.

Output strictly valid JSON of this shape:

{
  "core_values":       [{"slug": "honesty", "label": "Honesty", "description": "..."}, ...],
  "ethical_positions": [...],
  "priorities":        [...],
  "deal_breakers":     [...]
}

Deal-breakers should be conservative and uncontroversial — they should be
things almost any user would endorse as hard limits.
"""


_USER_PROMPT = "Generate a starter taxonomy for the four fields. JSON only."


class Command(BaseCommand):
    help = (
        "LLM-bootstrap a starter values-taxonomy YAML fixture for review. "
        "Maintainer reviews and commits the fixture; a data migration loads "
        "it into Tag rows on first migrate."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=str,
            default=str(_DEFAULT_OUTPUT),
            help=f"Output path for the YAML fixture (default: {_DEFAULT_OUTPUT}).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Overwrite an existing fixture file. Default: refuse.",
        )
        parser.add_argument(
            "--provider",
            type=str,
            default="anthropic",
            help="LLM provider name (default: anthropic).",
        )
        parser.add_argument(
            "--model",
            type=str,
            default="sonnet",
            help="LLM model alias or full id (default: sonnet).",
        )

    def handle(self, *args, **options):
        output = Path(options["output"])
        force = options["force"]
        provider_name = options["provider"]
        model = options["model"]

        if output.exists() and not force:
            raise CommandError(
                f"Refusing to overwrite existing fixture at {output}. "
                "Pass --force to overwrite (or move it aside first)."
            )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Bootstrapping values taxonomy via {provider_name}/{model}..."
            )
        )
        try:
            taxonomy = asyncio.run(_call_llm(provider_name, model))
        except Exception as exc:
            raise CommandError(f"LLM call failed: {exc}") from exc

        try:
            validated = _validate_taxonomy(taxonomy)
        except ValueError as exc:
            raise CommandError(f"LLM output failed validation: {exc}") from exc

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(yaml.safe_dump(validated, sort_keys=False))

        total = sum(len(v) for v in validated.values())
        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote {total} tags across {len(validated)} fields to {output}.\n"
                "Review the file by hand, then commit it. The 0013 data "
                "migration will load it as status=seeded on first migrate."
            )
        )


async def _call_llm(provider_name: str, model: str) -> dict:
    provider = get_provider(provider_name, model=model)
    response = await provider.complete(
        messages=[
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=_USER_PROMPT),
        ],
        temperature=0.4,
        max_tokens=3000,
    )
    match = re.search(r"\{.*\}", response.content, re.DOTALL)
    if match is None:
        raise ValueError("LLM response did not contain a JSON object")
    return json.loads(match.group(0))


def _validate_taxonomy(data: dict) -> dict:
    """Sanity-check the LLM output and normalise the shape."""
    if not isinstance(data, dict):
        raise ValueError("Expected top-level JSON object")
    out: dict[str, list[dict]] = {}
    for field in _FIELDS:
        items = data.get(field, [])
        if not isinstance(items, list) or not items:
            raise ValueError(f"Field '{field}' must be a non-empty list")
        cleaned: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug") or "").strip()
            label = str(item.get("label") or slug).strip()
            description = str(item.get("description") or "").strip()
            if not slug:
                continue
            cleaned.append({"slug": slug, "label": label, "description": description})
        if not cleaned:
            raise ValueError(f"Field '{field}' yielded no valid entries")
        out[field] = cleaned
    return out
