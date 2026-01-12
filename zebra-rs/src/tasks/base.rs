//! Base traits for task actions and conditions.
//!
//! This module defines the abstract interfaces that all task actions and
//! routing conditions must implement. Corresponds to Java ITaskAction and
//! IConditionAction interfaces.

use std::sync::Arc;

use async_trait::async_trait;
use serde_json::Value;

use crate::core::errors::ExecutionResult;
use crate::core::models::{
    ProcessDefinition, ProcessInstance, RoutingDefinition, TaskDefinition, TaskInstance,
    TaskResult,
};
use crate::storage::StateStore;

/// Context passed to task actions during execution.
///
/// Provides access to the workflow engine, storage, and related objects
/// needed for task execution.
pub struct ExecutionContext<S: StateStore> {
    /// Storage backend
    pub store: Arc<S>,
    /// The process instance being executed
    pub process: ProcessInstance,
    /// The process definition
    pub process_definition: ProcessDefinition,
    /// The task definition being executed
    pub task_definition: TaskDefinition,
}

impl<S: StateStore> ExecutionContext<S> {
    /// Create a new execution context
    pub fn new(
        store: Arc<S>,
        process: ProcessInstance,
        process_definition: ProcessDefinition,
        task_definition: TaskDefinition,
    ) -> Self {
        Self {
            store,
            process,
            process_definition,
            task_definition,
        }
    }

    /// Get the output from a previously completed task.
    ///
    /// Useful for tasks that need to reference results from earlier
    /// tasks in the workflow.
    pub fn get_task_output(&self, task_id: &str) -> Option<&Value> {
        let key = format!("__task_output_{}", task_id);
        self.process.properties.get(&key)
    }

    /// Get a property from the process instance.
    pub fn get_process_property(&self, key: &str) -> Option<&Value> {
        self.process.properties.get(key)
    }

    /// Get a property from the task definition.
    pub fn get_task_property(&self, key: &str) -> Option<&Value> {
        self.task_definition.properties.get(key)
    }
}

/// Abstract trait for task actions.
///
/// Implement this trait to create custom task types. The run() method
/// is called by the engine when a task is executed.
///
/// Corresponds to Java ITaskAction interface.
#[async_trait]
pub trait TaskAction<S: StateStore>: Send + Sync {
    /// Execute the task action.
    ///
    /// # Arguments
    /// * `task` - The task instance being executed
    /// * `context` - Execution context with engine, store, and related objects
    ///
    /// # Returns
    /// TaskResult indicating success/failure and any output
    async fn run(&self, task: &TaskInstance, context: &ExecutionContext<S>)
        -> ExecutionResult<TaskResult>;

    /// Called before task execution (optional).
    ///
    /// Override this method to perform setup work before the main
    /// task action runs.
    async fn on_construct(
        &self,
        _task: &TaskInstance,
        _context: &ExecutionContext<S>,
    ) -> ExecutionResult<()> {
        Ok(())
    }

    /// Called after task completion (optional).
    ///
    /// Override this method to perform cleanup work after the main
    /// task action completes (regardless of success/failure).
    async fn on_destruct(
        &self,
        _task: &TaskInstance,
        _context: &ExecutionContext<S>,
    ) -> ExecutionResult<()> {
        Ok(())
    }
}

/// Abstract trait for routing conditions.
///
/// Implement this trait to create custom routing conditions.
/// The evaluate() method is called to determine if a routing should fire.
///
/// Corresponds to Java IConditionAction interface.
#[async_trait]
pub trait ConditionAction<S: StateStore>: Send + Sync {
    /// Evaluate whether this routing should fire.
    ///
    /// # Arguments
    /// * `routing` - The routing definition being evaluated
    /// * `task` - The task instance that just completed
    /// * `context` - Execution context with engine, store, and related objects
    ///
    /// # Returns
    /// True if the routing should fire, false otherwise
    async fn evaluate(
        &self,
        routing: &RoutingDefinition,
        task: &TaskInstance,
        context: &ExecutionContext<S>,
    ) -> ExecutionResult<bool>;
}

/// A condition that always returns true. Used as default when no condition specified.
pub struct AlwaysTrueCondition;

#[async_trait]
impl<S: StateStore> ConditionAction<S> for AlwaysTrueCondition {
    async fn evaluate(
        &self,
        _routing: &RoutingDefinition,
        _task: &TaskInstance,
        _context: &ExecutionContext<S>,
    ) -> ExecutionResult<bool> {
        Ok(true)
    }
}

/// A condition that matches the task result's next_route against the routing name.
///
/// This is useful for decision tasks where the task action determines
/// which route to take by setting result.next_route.
pub struct RouteNameCondition;

#[async_trait]
impl<S: StateStore> ConditionAction<S> for RouteNameCondition {
    async fn evaluate(
        &self,
        routing: &RoutingDefinition,
        task: &TaskInstance,
        _context: &ExecutionContext<S>,
    ) -> ExecutionResult<bool> {
        // If task has no result, only fire if routing has no name
        let Some(result) = &task.result else {
            return Ok(routing.name.is_none() || routing.name.as_deref() == Some(""));
        };

        // Try to extract next_route from result
        if let Some(obj) = result.as_object() {
            if let Some(next_route) = obj.get("next_route").and_then(|v| v.as_str()) {
                return Ok(routing.name.as_deref() == Some(next_route));
            }
        }

        // No next_route specified, all routes fire
        Ok(true)
    }
}

/// A no-op task action that always succeeds.
#[derive(Default)]
pub struct NoOpAction;

#[async_trait]
impl<S: StateStore> TaskAction<S> for NoOpAction {
    async fn run(
        &self,
        _task: &TaskInstance,
        _context: &ExecutionContext<S>,
    ) -> ExecutionResult<TaskResult> {
        Ok(TaskResult::ok())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::models::{RoutingDefinition, TaskInstance};
    use crate::storage::InMemoryStore;
    use std::collections::HashMap;
    use std::sync::Arc;

    fn create_test_context() -> ExecutionContext<InMemoryStore> {
        let store = Arc::new(InMemoryStore::new());

        let mut tasks = HashMap::new();
        tasks.insert(
            "task1".to_string(),
            TaskDefinition::new("task1", "Task 1"),
        );

        let process_def = ProcessDefinition::new("def1", "Test", "task1", tasks);
        let mut process = ProcessInstance::new("proc1", "def1");
        process
            .properties
            .insert("test_key".to_string(), Value::String("test_value".to_string()));
        process.properties.insert(
            "__task_output_previous_task".to_string(),
            Value::String("previous_output".to_string()),
        );

        let task_def = TaskDefinition::new("task1", "Task 1");

        ExecutionContext::new(store, process, process_def, task_def)
    }

    #[test]
    fn test_get_task_output() {
        let context = create_test_context();
        let output = context.get_task_output("previous_task");
        assert_eq!(output.unwrap().as_str().unwrap(), "previous_output");
    }

    #[test]
    fn test_get_process_property() {
        let context = create_test_context();
        let prop = context.get_process_property("test_key");
        assert_eq!(prop.unwrap().as_str().unwrap(), "test_value");
    }

    #[tokio::test]
    async fn test_always_true_condition() {
        let context = create_test_context();
        let condition = AlwaysTrueCondition;
        let routing = RoutingDefinition::new("r1", "task1", "task2");
        let task = TaskInstance::new("t1", "proc1", "task1", "foe1");

        let result = condition.evaluate(&routing, &task, &context).await.unwrap();
        assert!(result);
    }

    #[tokio::test]
    async fn test_no_op_action() {
        let context = create_test_context();
        let action = NoOpAction;
        let task = TaskInstance::new("t1", "proc1", "task1", "foe1");

        let result = action.run(&task, &context).await.unwrap();
        assert!(result.success);
    }
}
