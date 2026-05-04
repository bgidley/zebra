"""DjangoRoutineRunStore — Django ORM implementation of RoutineRunStore."""

from __future__ import annotations

from datetime import UTC

from asgiref.sync import sync_to_async
from zebra_agent.scheduler.routine import RoutineRun
from zebra_agent.scheduler.store import RoutineRunStore


class DjangoRoutineRunStore(RoutineRunStore):
    """Persist routine run state via Django ORM (Oracle/SQLite)."""

    async def get_run(self, routine_name: str) -> RoutineRun | None:
        return await sync_to_async(self._get_run_sync)(routine_name)

    def _get_run_sync(self, routine_name: str) -> RoutineRun | None:
        from zebra_agent_web.api.models import RoutineRunModel

        try:
            obj = RoutineRunModel.objects.get(routine_name=routine_name)
        except RoutineRunModel.DoesNotExist:
            return None

        last_run = obj.last_run
        if last_run is not None and last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=UTC)
        next_run = obj.next_run
        if next_run.tzinfo is None:
            next_run = next_run.replace(tzinfo=UTC)

        return RoutineRun(
            routine_name=obj.routine_name,
            last_run=last_run,
            next_run=next_run,
            last_status=obj.last_status,
        )

    async def upsert_run(self, run: RoutineRun) -> None:
        await sync_to_async(self._upsert_run_sync)(run)

    def _upsert_run_sync(self, run: RoutineRun) -> None:
        from zebra_agent_web.api.models import RoutineRunModel

        RoutineRunModel.objects.update_or_create(
            routine_name=run.routine_name,
            defaults={
                "last_run": run.last_run,
                "next_run": run.next_run,
                "last_status": run.last_status,
            },
        )
