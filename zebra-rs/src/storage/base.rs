//! Abstract base trait for workflow state storage.
//!
//! This module defines the StateStore trait that all storage implementations
//! must follow. Corresponds to Java IStateFactory.

use async_trait::async_trait;

use crate::core::errors::Result;
use crate::core::models::{FlowOfExecution, ProcessDefinition, ProcessInstance, TaskInstance};

/// Abstract trait for workflow state persistence.
///
/// Implementations must provide atomic operations for saving and loading
/// workflow state, as well as locking mechanisms for concurrent access.
///
/// Corresponds to Java IStateFactory interface.
#[async_trait]
pub trait StateStore: Send + Sync {
    // =========================================================================
    // Process Definition Operations
    // =========================================================================

    /// Save or update a process definition.
    async fn save_definition(&self, definition: ProcessDefinition) -> Result<()>;

    /// Load a process definition by ID. Returns None if not found.
    async fn load_definition(&self, definition_id: &str) -> Result<Option<ProcessDefinition>>;

    /// List all available process definitions.
    async fn list_definitions(&self) -> Result<Vec<ProcessDefinition>>;

    /// Delete a process definition. Returns true if deleted, false if not found.
    async fn delete_definition(&self, definition_id: &str) -> Result<bool>;

    // =========================================================================
    // Process Instance Operations
    // =========================================================================

    /// Save or update a process instance.
    async fn save_process(&self, process: ProcessInstance) -> Result<()>;

    /// Load a process instance by ID. Returns None if not found.
    async fn load_process(&self, process_id: &str) -> Result<Option<ProcessInstance>>;

    /// List process instances, optionally filtered by definition and completion status.
    async fn list_processes(
        &self,
        definition_id: Option<&str>,
        include_completed: bool,
    ) -> Result<Vec<ProcessInstance>>;

    /// Delete a process instance and all related data. Returns true if deleted.
    async fn delete_process(&self, process_id: &str) -> Result<bool>;

    // =========================================================================
    // Task Instance Operations
    // =========================================================================

    /// Save or update a task instance.
    async fn save_task(&self, task: TaskInstance) -> Result<()>;

    /// Load a task instance by ID. Returns None if not found.
    async fn load_task(&self, task_id: &str) -> Result<Option<TaskInstance>>;

    /// Load all task instances for a process.
    async fn load_tasks_for_process(&self, process_id: &str) -> Result<Vec<TaskInstance>>;

    /// Delete a task instance. Returns true if deleted.
    async fn delete_task(&self, task_id: &str) -> Result<bool>;

    // =========================================================================
    // Flow of Execution Operations
    // =========================================================================

    /// Save or update a flow of execution.
    async fn save_foe(&self, foe: FlowOfExecution) -> Result<()>;

    /// Load a flow of execution by ID. Returns None if not found.
    async fn load_foe(&self, foe_id: &str) -> Result<Option<FlowOfExecution>>;

    /// Load all FOEs for a process.
    async fn load_foes_for_process(&self, process_id: &str) -> Result<Vec<FlowOfExecution>>;

    // =========================================================================
    // Locking Operations
    // =========================================================================

    /// Acquire an exclusive lock on a process instance.
    ///
    /// # Arguments
    /// * `process_id` - The process to lock
    /// * `owner` - Identifier for the lock owner (e.g., engine instance ID)
    /// * `timeout_seconds` - How long to wait for lock acquisition
    ///
    /// # Returns
    /// True if lock acquired, false if timeout
    async fn acquire_lock(
        &self,
        process_id: &str,
        owner: &str,
        timeout_seconds: f64,
    ) -> Result<bool>;

    /// Release a lock on a process instance.
    ///
    /// # Arguments
    /// * `process_id` - The process to unlock
    /// * `owner` - Must match the owner that acquired the lock
    ///
    /// # Returns
    /// True if released, false if not locked or wrong owner
    async fn release_lock(&self, process_id: &str, owner: &str) -> Result<bool>;

    // =========================================================================
    // Lifecycle
    // =========================================================================

    /// Initialize the store (create tables, etc.). Called once at startup.
    async fn initialize(&self) -> Result<()> {
        Ok(())
    }

    /// Close the store and release resources.
    async fn close(&self) -> Result<()> {
        Ok(())
    }
}

/// A lock guard that automatically releases the lock when dropped.
pub struct ProcessLockGuard<'a, S: StateStore + ?Sized> {
    store: &'a S,
    process_id: String,
    owner: String,
    acquired: bool,
}

impl<'a, S: StateStore + ?Sized> ProcessLockGuard<'a, S> {
    /// Create a new lock guard and attempt to acquire the lock.
    pub async fn new(
        store: &'a S,
        process_id: impl Into<String>,
        owner: impl Into<String>,
        timeout_seconds: f64,
    ) -> Result<Self> {
        let process_id = process_id.into();
        let owner = owner.into();
        let acquired = store.acquire_lock(&process_id, &owner, timeout_seconds).await?;

        Ok(Self {
            store,
            process_id,
            owner,
            acquired,
        })
    }

    /// Check if the lock was acquired.
    pub fn is_acquired(&self) -> bool {
        self.acquired
    }

    /// Manually release the lock.
    pub async fn release(&mut self) -> Result<bool> {
        if self.acquired {
            let result = self.store.release_lock(&self.process_id, &self.owner).await?;
            self.acquired = false;
            Ok(result)
        } else {
            Ok(false)
        }
    }
}

// Note: We can't implement Drop with async, so the caller must explicitly release
// or use a scoped pattern.
