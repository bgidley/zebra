"""Task synchronization logic for handling join points in parallel workflows.

This module contains the logic for determining when a synchronized (join) task
can execute. A sync task waits until all parallel branches that can reach it
have completed.

Ported from Java TaskSync class.
"""

from zebra.core.models import (
    ProcessDefinition,
    ProcessInstance,
    TaskDefinition,
    TaskInstance,
    TaskState,
)


class TaskSync:
    """Helper class for task synchronization logic.

    Handles determining when a synchronized task (join point) can execute.
    A sync task is blocked until all active tasks that can potentially
    route to it have completed.
    """

    def get_potential_task_locks(
        self, task_def: TaskDefinition, process_def: ProcessDefinition
    ) -> set[str]:
        """Find all sync tasks that this task can potentially block.

        Iterates through all outbound routes from this task, looking for
        tasks with synchronized=True and returns them.

        Args:
            task_def: The task definition to check outbound routes from
            process_def: The process definition containing all tasks/routings

        Returns:
            Set of task IDs that are sync points reachable from this task
        """
        sync_tasks: set[str] = set()
        visited: set[str] = set()
        to_check: set[str] = {task_def.id}

        while to_check:
            current_id = to_check.pop()
            visited.add(current_id)

            # Get outbound routings from this task
            routings = process_def.get_routings_from(current_id)

            for routing in routings:
                dest_id = routing.dest_task_id
                dest_task = process_def.get_task(dest_id)

                if dest_task.synchronized:
                    sync_tasks.add(dest_id)

                # Even if we find a sync task, keep looking - there may be
                # more further down the chain that we can block
                if dest_id not in visited and dest_id not in to_check:
                    to_check.add(dest_id)

        return sync_tasks

    def is_task_blocked(
        self,
        task: TaskInstance,
        task_def: TaskDefinition,
        process: ProcessInstance,
        process_def: ProcessDefinition,
        active_tasks: list[TaskInstance],
    ) -> bool:
        """Check if a synchronized task is blocked by other active tasks.

        A sync task is blocked if there are any active tasks in the process
        that can potentially route to it.

        Args:
            task: The sync task instance to check
            task_def: The definition of the sync task
            process: The process instance
            process_def: The process definition
            active_tasks: List of currently active task instances

        Returns:
            True if the task is blocked, False if it can proceed
        """
        # Build up a unique list of task definitions from currently running tasks
        # These are all potential blockers
        blocking_def_ids: set[str] = set()

        for active_task in active_tasks:
            # Don't include the task itself
            if active_task.id != task.id:
                # Only consider tasks that are actually active (not completed)
                if active_task.state not in {TaskState.COMPLETE, TaskState.FAILED}:
                    blocking_def_ids.add(active_task.task_definition_id)

        return self._check_def_in_path(blocking_def_ids, task_def.id, process_def)

    def _check_def_in_path(
        self, blocking_def_ids: set[str], sync_task_id: str, process_def: ProcessDefinition
    ) -> bool:
        """Check if any of the blocking task definitions can reach the sync task.

        Traverses the routings BACKWARDS from the sync task to see if any
        of the blocking tasks are in the path.

        Args:
            blocking_def_ids: Set of task definition IDs that might be blocking
            sync_task_id: The ID of the sync task we're checking
            process_def: The process definition

        Returns:
            True if blocked (a blocking task can reach the sync point)
        """
        visited: set[str] = set()
        to_check: set[str] = {sync_task_id}

        while to_check:
            current_id = to_check.pop()

            # Get inbound routings to this task
            routings = process_def.get_routings_to(current_id)

            for routing in routings:
                source_id = routing.source_task_id

                # If a blocking task can reach us, we're blocked
                if source_id in blocking_def_ids:
                    return True

                if source_id not in visited and source_id not in to_check:
                    to_check.add(source_id)

            visited.add(current_id)

        return False

    def get_blocking_tasks(
        self,
        task: TaskInstance,
        task_def: TaskDefinition,
        process_def: ProcessDefinition,
        active_tasks: list[TaskInstance],
    ) -> list[TaskInstance]:
        """Get the list of tasks that are blocking a sync task.

        Useful for debugging and understanding why a sync task isn't executing.

        Args:
            task: The sync task instance to check
            task_def: The definition of the sync task
            process_def: The process definition
            active_tasks: List of currently active task instances

        Returns:
            List of task instances that are blocking this sync task
        """
        blocking: list[TaskInstance] = []

        for active_task in active_tasks:
            if active_task.id == task.id:
                continue
            if active_task.state in {TaskState.COMPLETE, TaskState.FAILED}:
                continue

            # Check if this task's definition can reach the sync task
            if self._check_def_in_path({active_task.task_definition_id}, task_def.id, process_def):
                blocking.append(active_task)

        return blocking
