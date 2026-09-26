"""Django management command: curate the values-tag taxonomy (#106).

Usage:
    python manage.py values_taxonomy list [--field F] [--status S] [--suggested]
    python manage.py values_taxonomy promote <field> <slug>
    python manage.py values_taxonomy reject <field> <slug>
    python manage.py values_taxonomy demote <field> <slug>
    python manage.py values_taxonomy merge <field> <source_slug> <target_slug>
    python manage.py values_taxonomy prune [--days 90] [--max-usage 1] [--dry-run]

Promoted tags join the approved set that ``extract_values_tags`` anchors the
LLM on. See ``zebra_agent_web.values_taxonomy`` for the lifecycle rules.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from zebra_agent_web import values_taxonomy as taxonomy


class Command(BaseCommand):
    help = "Review and curate values-taxonomy tags (promote, reject, demote, merge, prune)."

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest="action", required=True)

        list_p = sub.add_parser("list", help="List tags")
        list_p.add_argument("--field", choices=taxonomy.FIELDS)
        list_p.add_argument("--status", choices=taxonomy.STATUSES)
        list_p.add_argument(
            "--suggested",
            action="store_true",
            help="Only candidates at or above the promotion threshold",
        )

        for name, text in (
            ("promote", "Promote a candidate or rejected tag"),
            ("reject", "Reject a candidate or archive a promoted tag"),
            ("demote", "Return a promoted tag to candidate"),
        ):
            p = sub.add_parser(name, help=text)
            p.add_argument("field", choices=taxonomy.FIELDS)
            p.add_argument("slug")

        merge_p = sub.add_parser("merge", help="Merge a tag into another in the same field")
        merge_p.add_argument("field", choices=taxonomy.FIELDS)
        merge_p.add_argument("source")
        merge_p.add_argument("target")

        prune_p = sub.add_parser("prune", help="Delete stale, rarely used candidates")
        prune_p.add_argument("--days", type=int, default=90)
        prune_p.add_argument("--max-usage", type=int, default=1)
        prune_p.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        action = options["action"]
        try:
            if action == "list":
                self._list(options)
            elif action == "merge":
                target = taxonomy.merge(options["field"], options["source"], options["target"])
                self._ok(
                    f"Merged {options['source']} into {target.slug} "
                    f"({options['field']}, usage now {target.usage_count})"
                )
            elif action == "prune":
                self._prune(options)
            else:
                operation = getattr(taxonomy, action)
                tag = operation(options["field"], options["slug"])
                self._ok(f"{tag.field}/{tag.slug} is now {tag.status}")
        except taxonomy.TaxonomyError as exc:
            raise CommandError(str(exc)) from exc

    def _list(self, options) -> None:
        tags = taxonomy.list_tags(
            field=options.get("field"),
            status=options.get("status"),
            suggested_only=options.get("suggested", False),
        )
        if not tags:
            self.stdout.write("No tags match.")
            return
        for tag in tags:
            extra = f" -> {tag.merged_into}" if tag.merged_into else ""
            flag = "  [suggested]" if tag.suggested else ""
            self.stdout.write(
                f"{tag.field:<18} {tag.slug:<30} {tag.status:<10}{extra} "
                f"usage={tag.usage_count}{flag}"
            )
        self.stdout.write(
            f"{len(tags)} tag(s); promotion threshold {taxonomy.promotion_threshold()}"
        )

    def _prune(self, options) -> None:
        dry_run = options["dry_run"]
        victims = taxonomy.prune(
            days=options["days"], max_usage=options["max_usage"], dry_run=dry_run
        )
        for tag in victims:
            self.stdout.write(f"{tag.field}/{tag.slug} usage={tag.usage_count}")
        verb = "Would delete" if dry_run else "Deleted"
        self._ok(f"{verb} {len(victims)} stale candidate tag(s)")

    def _ok(self, message: str) -> None:
        self.stdout.write(self.style.SUCCESS(message))
