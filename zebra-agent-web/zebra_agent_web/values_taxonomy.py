"""Values-taxonomy curation: promote, reject, demote, merge and prune tags (#106).

F18 accumulates user-confirmed tags as ``candidate`` rows in
``ValuesTagModel``; ``extract_values_tags`` only anchors the LLM on
``seeded + promoted`` tags. This module is the curator's side of that loop,
shared by ``manage.py values_taxonomy`` and the ``/profile/taxonomy/`` page.

Functions are synchronous ORM calls; async callers wrap them in
``sync_to_async``. Invalid operations raise ``TaxonomyError`` and leave the
database unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from zebra_agent_web.api.models import ValuesTagModel

FIELDS = tuple(choice[0] for choice in ValuesTagModel.FIELD_CHOICES)
STATUSES = tuple(choice[0] for choice in ValuesTagModel.STATUS_CHOICES)

DEFAULT_PROMOTION_THRESHOLD = 3

# Allowed source statuses per operation; ``seeded`` and ``merged`` are never sources.
_PROMOTE_FROM = {"candidate", "rejected"}
_REJECT_FROM = {"candidate", "promoted"}
_DEMOTE_FROM = {"promoted"}
_MERGE_FROM = {"candidate", "promoted", "rejected"}
_MERGE_INTO = {"seeded", "promoted", "candidate"}


class TaxonomyError(ValueError):
    """Raised when a curation operation is not allowed."""


@dataclass(frozen=True)
class TagView:
    """A read-only snapshot of a tag row for display."""

    field: str
    slug: str
    label: str
    description: str
    status: str
    usage_count: int
    created_at: datetime | None
    promoted_at: datetime | None
    merged_into: str | None
    suggested: bool


def promotion_threshold() -> int:
    """Return the usage count at which a candidate is suggested for promotion."""
    zebra_settings = getattr(settings, "ZEBRA_AGENT_SETTINGS", {}) or {}
    return int(zebra_settings.get("VALUES_TAG_PROMOTION_THRESHOLD", DEFAULT_PROMOTION_THRESHOLD))


def list_tags(
    field: str | None = None,
    status: str | None = None,
    suggested_only: bool = False,
) -> list[TagView]:
    """List tags ordered by field, then usage (desc), then slug.

    Args:
        field: Restrict to one field.
        status: Restrict to one status.
        suggested_only: Only candidates at or above the promotion threshold.
    """
    threshold = promotion_threshold()
    qs = ValuesTagModel.objects.all()
    if field:
        _check_field(field)
        qs = qs.filter(field=field)
    if status:
        if status not in STATUSES:
            raise TaxonomyError(f"Unknown status '{status}'")
        qs = qs.filter(status=status)
    if suggested_only:
        qs = qs.filter(status="candidate", usage_count__gte=threshold)
    return [_to_view(row, threshold) for row in qs.order_by("field", "-usage_count", "slug")]


def promote(field: str, slug: str) -> TagView:
    """Promote a candidate (or previously rejected) tag to first-class status."""
    with transaction.atomic():
        row = _get_for_update(field, slug, _PROMOTE_FROM, "promote")
        row.status = "promoted"
        row.promoted_at = timezone.now()
        row.save(update_fields=["status", "promoted_at"])
    return _to_view(row, promotion_threshold())


def reject(field: str, slug: str) -> TagView:
    """Reject a candidate, or archive a promoted tag. The row is kept."""
    with transaction.atomic():
        row = _get_for_update(field, slug, _REJECT_FROM, "reject")
        row.status = "rejected"
        row.promoted_at = None
        row.save(update_fields=["status", "promoted_at"])
    return _to_view(row, promotion_threshold())


def demote(field: str, slug: str) -> TagView:
    """Return a promoted tag to candidate status."""
    with transaction.atomic():
        row = _get_for_update(field, slug, _DEMOTE_FROM, "demote")
        row.status = "candidate"
        row.promoted_at = None
        row.save(update_fields=["status", "promoted_at"])
    return _to_view(row, promotion_threshold())


def merge(field: str, source_slug: str, target_slug: str) -> TagView:
    """Merge ``source_slug`` into ``target_slug`` within one field.

    The source's usage moves to the target; the source becomes ``merged``
    with ``merged_into=target_slug``. Tags previously merged into the source
    are repointed at the target so chains never form.

    Returns:
        The updated target tag.
    """
    if source_slug == target_slug:
        raise TaxonomyError("Cannot merge a tag into itself")
    with transaction.atomic():
        source = _get_for_update(field, source_slug, _MERGE_FROM, "merge")
        target = _get_for_update(field, target_slug, _MERGE_INTO, "merge into")

        ValuesTagModel.objects.filter(pk=target.pk).update(
            usage_count=F("usage_count") + source.usage_count
        )
        ValuesTagModel.objects.filter(field=field, merged_into=source_slug).update(
            merged_into=target_slug
        )
        source.status = "merged"
        source.merged_into = target_slug
        source.usage_count = 0
        source.promoted_at = None
        source.save(update_fields=["status", "merged_into", "usage_count", "promoted_at"])
        target.refresh_from_db()
    return _to_view(target, promotion_threshold())


def prune(days: int = 90, max_usage: int = 1, dry_run: bool = False) -> list[TagView]:
    """Delete stale, rarely used candidates.

    Only ``candidate`` rows created more than ``days`` ago with
    ``usage_count <= max_usage`` are affected.

    Returns:
        The tags deleted (or that would be deleted, when ``dry_run``).
    """
    cutoff = timezone.now() - timedelta(days=days)
    qs = ValuesTagModel.objects.filter(
        status="candidate", usage_count__lte=max_usage, created_at__lt=cutoff
    )
    threshold = promotion_threshold()
    victims = [_to_view(row, threshold) for row in qs.order_by("field", "slug")]
    if not dry_run:
        qs.delete()
    return victims


def _check_field(field: str) -> None:
    if field not in FIELDS:
        raise TaxonomyError(f"Unknown field '{field}' (expected one of {', '.join(FIELDS)})")


def _get_for_update(field: str, slug: str, allowed: set[str], verb: str) -> ValuesTagModel:
    _check_field(field)
    row = ValuesTagModel.objects.select_for_update().filter(field=field, slug=slug).first()
    if row is None:
        raise TaxonomyError(f"No tag '{slug}' in {field}")
    if row.status not in allowed:
        raise TaxonomyError(
            f"Cannot {verb} '{slug}' in {field}: status is {row.status} "
            f"(allowed: {', '.join(sorted(allowed))})"
        )
    return row


def _to_view(row: ValuesTagModel, threshold: int) -> TagView:
    return TagView(
        field=row.field,
        slug=row.slug,
        label=row.label,
        description=row.description,
        status=row.status,
        usage_count=row.usage_count,
        created_at=row.created_at,
        promoted_at=row.promoted_at,
        merged_into=row.merged_into,
        suggested=row.status == "candidate" and row.usage_count >= threshold,
    )
