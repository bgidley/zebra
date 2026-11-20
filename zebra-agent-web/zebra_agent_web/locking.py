"""Row locks that work on every database backend we run on.

``qs.select_for_update().first()`` is the obvious way to lock one row, but ``.first()`` adds
``LIMIT 1`` and Oracle rejects ``FOR UPDATE`` with ``FETCH FIRST``
(``supports_select_for_update_with_limit = False``): "LIMIT/OFFSET is not supported with
select_for_update on this database backend". SQLite accepts it, so tests never noticed (#232).
"""

from __future__ import annotations

from typing import TypeVar

from django.db.models import Model, QuerySet

M = TypeVar("M", bound=Model)


def first_for_update(queryset: QuerySet[M]) -> M | None:
    """Lock and return the first row of *queryset*, or None. Call inside ``transaction.atomic()``.

    Locks every row the queryset matches, without a ``LIMIT``: use it on a filter that matches
    at most one row (a primary or unique key).
    """
    for row in queryset.select_for_update():
        return row
    return None
