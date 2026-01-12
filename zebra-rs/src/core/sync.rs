//! Task synchronization logic for handling join points in parallel workflows.
//!
//! This module contains the logic for determining when a synchronized (join) task
//! can execute. A sync task waits until all parallel branches that can reach it
//! have completed.
//!
//! Ported from Java TaskSync class.

use std::collections::HashSet;

use super::models::{ProcessDefinition, TaskDefinition, TaskInstance};

/// Helper struct for task synchronization logic.
///
/// Handles determining when a synchronized task (join point) can execute.
/// A sync task is blocked until all active tasks that can potentially
/// route to it have completed.
#[derive(Debug, Default)]
pub struct TaskSync;

impl TaskSync {
    /// Create a new TaskSync instance
    pub fn new() -> Self {
        Self
    }

    /// Find all sync tasks that this task can potentially block.
    ///
    /// Iterates through all outbound routes from this task, looking for
    /// tasks with synchronized=true and returns them.
    ///
    /// # Arguments
    /// * `task_def` - The task definition to check outbound routes from
    /// * `process_def` - The process definition containing all tasks/routings
    ///
    /// # Returns
    /// Set of task IDs that are sync points reachable from this task
    pub fn get_potential_task_locks(
        &self,
        task_def: &TaskDefinition,
        process_def: &ProcessDefinition,
    ) -> HashSet<String> {
        let mut sync_tasks: HashSet<String> = HashSet::new();
        let mut visited: HashSet<String> = HashSet::new();
        let mut to_check: HashSet<String> = HashSet::new();
        to_check.insert(task_def.id.clone());

        while let Some(current_id) = to_check.iter().next().cloned() {
            to_check.remove(&current_id);
            visited.insert(current_id.clone());

            // Get outbound routings from this task
            let routings = process_def.get_routings_from(&current_id);

            for routing in routings {
                let dest_id = &routing.dest_task_id;

                if let Some(dest_task) = process_def.get_task(dest_id) {
                    if dest_task.synchronized {
                        sync_tasks.insert(dest_id.clone());
                    }

                    // Even if we find a sync task, keep looking - there may be
                    // more further down the chain that we can block
                    if !visited.contains(dest_id) && !to_check.contains(dest_id) {
                        to_check.insert(dest_id.clone());
                    }
                }
            }
        }

        sync_tasks
    }

    /// Check if a synchronized task is blocked by other active tasks.
    ///
    /// A sync task is blocked if there are any active tasks in the process
    /// that can potentially route to it.
    ///
    /// # Arguments
    /// * `task` - The sync task instance to check
    /// * `task_def` - The definition of the sync task
    /// * `process_def` - The process definition
    /// * `active_tasks` - List of currently active task instances
    ///
    /// # Returns
    /// True if the task is blocked, false if it can proceed
    pub fn is_task_blocked(
        &self,
        task: &TaskInstance,
        task_def: &TaskDefinition,
        process_def: &ProcessDefinition,
        active_tasks: &[TaskInstance],
    ) -> bool {
        // Build up a unique list of task definitions from currently running tasks
        // These are all potential blockers
        let mut blocking_def_ids: HashSet<String> = HashSet::new();

        for active_task in active_tasks {
            // Don't include the task itself
            if active_task.id != task.id {
                // Only consider tasks that are actually active (not completed)
                if !active_task.state.is_terminal() {
                    blocking_def_ids.insert(active_task.task_definition_id.clone());
                }
            }
        }

        self.check_def_in_path(&blocking_def_ids, &task_def.id, process_def)
    }

    /// Check if any of the blocking task definitions can reach the sync task.
    ///
    /// Traverses the routings BACKWARDS from the sync task to see if any
    /// of the blocking tasks are in the path.
    fn check_def_in_path(
        &self,
        blocking_def_ids: &HashSet<String>,
        sync_task_id: &str,
        process_def: &ProcessDefinition,
    ) -> bool {
        let mut visited: HashSet<String> = HashSet::new();
        let mut to_check: HashSet<String> = HashSet::new();
        to_check.insert(sync_task_id.to_string());

        while let Some(current_id) = to_check.iter().next().cloned() {
            to_check.remove(&current_id);

            // Get inbound routings to this task
            let routings = process_def.get_routings_to(&current_id);

            for routing in routings {
                let source_id = &routing.source_task_id;

                // If a blocking task can reach us, we're blocked
                if blocking_def_ids.contains(source_id) {
                    return true;
                }

                if !visited.contains(source_id) && !to_check.contains(source_id) {
                    to_check.insert(source_id.clone());
                }
            }

            visited.insert(current_id);
        }

        false
    }

    /// Get the list of tasks that are blocking a sync task.
    ///
    /// Useful for debugging and understanding why a sync task isn't executing.
    ///
    /// # Arguments
    /// * `task` - The sync task instance to check
    /// * `task_def` - The definition of the sync task
    /// * `process_def` - The process definition
    /// * `active_tasks` - List of currently active task instances
    ///
    /// # Returns
    /// List of task instances that are blocking this sync task
    pub fn get_blocking_tasks<'a>(
        &self,
        task: &TaskInstance,
        task_def: &TaskDefinition,
        process_def: &ProcessDefinition,
        active_tasks: &'a [TaskInstance],
    ) -> Vec<&'a TaskInstance> {
        let mut blocking: Vec<&TaskInstance> = Vec::new();

        for active_task in active_tasks {
            if active_task.id == task.id {
                continue;
            }
            if active_task.state.is_terminal() {
                continue;
            }

            // Check if this task's definition can reach the sync task
            let mut def_ids = HashSet::new();
            def_ids.insert(active_task.task_definition_id.clone());

            if self.check_def_in_path(&def_ids, &task_def.id, process_def) {
                blocking.push(active_task);
            }
        }

        blocking
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::models::{RoutingDefinition, TaskDefinition, TaskState};
    use std::collections::HashMap;

    fn create_test_process_def() -> ProcessDefinition {
        let mut tasks = HashMap::new();
        tasks.insert(
            "start".to_string(),
            TaskDefinition::new("start", "Start"),
        );
        tasks.insert(
            "branch_a".to_string(),
            TaskDefinition::new("branch_a", "Branch A"),
        );
        tasks.insert(
            "branch_b".to_string(),
            TaskDefinition::new("branch_b", "Branch B"),
        );
        tasks.insert(
            "join".to_string(),
            TaskDefinition::new("join", "Join").with_synchronized(true),
        );

        ProcessDefinition::new("test", "Test Process", "start", tasks).with_routings(vec![
            RoutingDefinition::new("r1", "start", "branch_a").with_parallel(true),
            RoutingDefinition::new("r2", "start", "branch_b").with_parallel(true),
            RoutingDefinition::new("r3", "branch_a", "join"),
            RoutingDefinition::new("r4", "branch_b", "join"),
        ])
    }

    #[test]
    fn test_get_potential_task_locks() {
        let sync = TaskSync::new();
        let process_def = create_test_process_def();
        let start_def = process_def.get_task("start").unwrap();

        let locks = sync.get_potential_task_locks(start_def, &process_def);

        assert!(locks.contains("join"));
        assert_eq!(locks.len(), 1);
    }

    #[test]
    fn test_is_task_blocked() {
        let sync = TaskSync::new();
        let process_def = create_test_process_def();
        let join_def = process_def.get_task("join").unwrap();

        let join_task = TaskInstance::new("join-1", "proc-1", "join", "foe-1")
            .with_state(TaskState::AwaitingSync);

        let branch_a_task = TaskInstance::new("branch-a-1", "proc-1", "branch_a", "foe-2")
            .with_state(TaskState::Running);

        let active_tasks = vec![join_task.clone(), branch_a_task];

        // Join should be blocked because branch_a is still running
        assert!(sync.is_task_blocked(&join_task, join_def, &process_def, &active_tasks));
    }

    #[test]
    fn test_is_task_not_blocked() {
        let sync = TaskSync::new();
        let process_def = create_test_process_def();
        let join_def = process_def.get_task("join").unwrap();

        let join_task = TaskInstance::new("join-1", "proc-1", "join", "foe-1")
            .with_state(TaskState::AwaitingSync);

        // No other active tasks
        let active_tasks = vec![join_task.clone()];

        // Join should not be blocked
        assert!(!sync.is_task_blocked(&join_task, join_def, &process_def, &active_tasks));
    }
}
