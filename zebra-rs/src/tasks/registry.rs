//! Action registry for managing task actions and conditions.
//!
//! This module provides the ActionRegistry struct that manages registration
//! and lookup of TaskAction and ConditionAction implementations.

use std::collections::HashMap;
use std::sync::Arc;

use crate::core::errors::{ExecutionError, ExecutionResult};
use crate::storage::StateStore;

use super::base::{AlwaysTrueCondition, ConditionAction, TaskAction};

/// Type alias for boxed task actions
pub type BoxedAction<S> = Arc<dyn TaskAction<S>>;

/// Type alias for boxed condition actions
pub type BoxedCondition<S> = Arc<dyn ConditionAction<S>>;

/// Factory function type for creating task actions
pub type ActionFactory<S> = Box<dyn Fn() -> BoxedAction<S> + Send + Sync>;

/// Factory function type for creating condition actions
pub type ConditionFactory<S> = Box<dyn Fn() -> BoxedCondition<S> + Send + Sync>;

/// Registry for task actions and routing conditions.
///
/// Actions are registered by name and can be looked up later during
/// workflow execution. This allows workflow definitions to reference
/// actions by string name rather than Rust type references.
pub struct ActionRegistry<S: StateStore> {
    actions: HashMap<String, ActionFactory<S>>,
    conditions: HashMap<String, ConditionFactory<S>>,
}

impl<S: StateStore + 'static> ActionRegistry<S> {
    /// Create a new empty registry.
    pub fn new() -> Self {
        let mut registry = Self {
            actions: HashMap::new(),
            conditions: HashMap::new(),
        };

        // Register built-in conditions
        registry.register_condition("always_true", || Arc::new(AlwaysTrueCondition));

        registry
    }

    // =========================================================================
    // Task Action Registration
    // =========================================================================

    /// Register a task action by name.
    ///
    /// # Arguments
    /// * `name` - The name to register the action under
    /// * `factory` - A factory function that creates instances of the action
    pub fn register_action<F>(&mut self, name: impl Into<String>, factory: F)
    where
        F: Fn() -> BoxedAction<S> + Send + Sync + 'static,
    {
        self.actions.insert(name.into(), Box::new(factory));
    }

    /// Register a task action type directly.
    ///
    /// Convenience method that creates a factory for types implementing Default.
    pub fn register_action_type<A>(&mut self, name: impl Into<String>)
    where
        A: TaskAction<S> + Default + 'static,
    {
        self.register_action(name, || Arc::new(A::default()));
    }

    /// Get a task action instance by name.
    ///
    /// # Arguments
    /// * `name` - The registered name of the action
    ///
    /// # Returns
    /// A new instance of the registered TaskAction
    ///
    /// # Errors
    /// Returns ActionNotFound if no action is registered with that name
    pub fn get_action(&self, name: &str) -> ExecutionResult<BoxedAction<S>> {
        self.actions
            .get(name)
            .map(|factory| factory())
            .ok_or_else(|| ExecutionError::ActionNotFound(name.to_string()))
    }

    /// Check if a task action is registered.
    pub fn has_action(&self, name: &str) -> bool {
        self.actions.contains_key(name)
    }

    /// List all registered task action names.
    pub fn list_actions(&self) -> Vec<&str> {
        self.actions.keys().map(|s| s.as_str()).collect()
    }

    // =========================================================================
    // Condition Registration
    // =========================================================================

    /// Register a routing condition by name.
    ///
    /// # Arguments
    /// * `name` - The name to register the condition under
    /// * `factory` - A factory function that creates instances of the condition
    pub fn register_condition<F>(&mut self, name: impl Into<String>, factory: F)
    where
        F: Fn() -> BoxedCondition<S> + Send + Sync + 'static,
    {
        self.conditions.insert(name.into(), Box::new(factory));
    }

    /// Register a condition type directly.
    ///
    /// Convenience method that creates a factory for types implementing Default.
    pub fn register_condition_type<C>(&mut self, name: impl Into<String>)
    where
        C: ConditionAction<S> + Default + 'static,
    {
        self.register_condition(name, || Arc::new(C::default()));
    }

    /// Get a condition action instance by name.
    ///
    /// If name is None, returns an AlwaysTrueCondition.
    ///
    /// # Arguments
    /// * `name` - The registered name of the condition, or None
    ///
    /// # Returns
    /// A new instance of the registered ConditionAction
    ///
    /// # Errors
    /// Returns ConditionNotFound if no condition is registered with that name
    pub fn get_condition(&self, name: Option<&str>) -> ExecutionResult<BoxedCondition<S>> {
        match name {
            None => Ok(Arc::new(AlwaysTrueCondition)),
            Some(name) => self
                .conditions
                .get(name)
                .map(|factory| factory())
                .ok_or_else(|| ExecutionError::ConditionNotFound(name.to_string())),
        }
    }

    /// Check if a condition is registered.
    pub fn has_condition(&self, name: &str) -> bool {
        self.conditions.contains_key(name)
    }

    /// List all registered condition names.
    pub fn list_conditions(&self) -> Vec<&str> {
        self.conditions.keys().map(|s| s.as_str()).collect()
    }
}

impl<S: StateStore + 'static> Default for ActionRegistry<S> {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::core::models::{TaskInstance, TaskResult};
    use crate::storage::InMemoryStore;
    use crate::tasks::base::{ExecutionContext, NoOpAction};
    use async_trait::async_trait;

    #[derive(Default)]
    struct TestAction;

    #[async_trait]
    impl TaskAction<InMemoryStore> for TestAction {
        async fn run(
            &self,
            _task: &TaskInstance,
            _context: &ExecutionContext<InMemoryStore>,
        ) -> ExecutionResult<TaskResult> {
            Ok(TaskResult::ok_with_output(serde_json::json!({"test": true})))
        }
    }

    #[test]
    fn test_register_and_get_action() {
        let mut registry = ActionRegistry::<InMemoryStore>::new();
        registry.register_action("test", || Arc::new(TestAction));

        assert!(registry.has_action("test"));
        assert!(registry.get_action("test").is_ok());
        assert!(registry.get_action("nonexistent").is_err());
    }

    #[test]
    fn test_register_action_type() {
        let mut registry = ActionRegistry::<InMemoryStore>::new();
        registry.register_action_type::<NoOpAction>("noop");

        assert!(registry.has_action("noop"));
    }

    #[test]
    fn test_list_actions() {
        let mut registry = ActionRegistry::<InMemoryStore>::new();
        registry.register_action("action1", || Arc::new(NoOpAction));
        registry.register_action("action2", || Arc::new(NoOpAction));

        let actions = registry.list_actions();
        assert!(actions.contains(&"action1"));
        assert!(actions.contains(&"action2"));
    }

    #[test]
    fn test_get_condition_none() {
        let registry = ActionRegistry::<InMemoryStore>::new();
        let condition = registry.get_condition(None);
        assert!(condition.is_ok());
    }

    #[test]
    fn test_get_condition_always_true() {
        let registry = ActionRegistry::<InMemoryStore>::new();
        let condition = registry.get_condition(Some("always_true"));
        assert!(condition.is_ok());
    }

    #[test]
    fn test_get_condition_not_found() {
        let registry = ActionRegistry::<InMemoryStore>::new();
        let condition = registry.get_condition(Some("nonexistent"));
        assert!(condition.is_err());
    }
}
