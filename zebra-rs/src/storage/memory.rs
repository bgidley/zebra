//! In-memory storage implementation for testing and ephemeral workflows.

use std::collections::HashMap;
use std::sync::Arc;
use std::time::{Duration, Instant};

use async_trait::async_trait;
use tokio::sync::{Mutex, Notify, RwLock};

use crate::core::errors::Result;
use crate::core::models::{
    FlowOfExecution, ProcessDefinition, ProcessInstance, ProcessState, TaskInstance,
};

use super::base::StateStore;

/// In-memory implementation of StateStore for testing.
///
/// All data is lost when the process terminates. Useful for:
/// - Unit testing
/// - Development
/// - Single-session workflows that don't need persistence
pub struct InMemoryStore {
    definitions: RwLock<HashMap<String, ProcessDefinition>>,
    processes: RwLock<HashMap<String, ProcessInstance>>,
    tasks: RwLock<HashMap<String, TaskInstance>>,
    foes: RwLock<HashMap<String, FlowOfExecution>>,
    locks: Mutex<HashMap<String, String>>, // process_id -> owner
    lock_notify: Arc<Notify>,
}

impl Default for InMemoryStore {
    fn default() -> Self {
        Self::new()
    }
}

impl InMemoryStore {
    /// Create a new in-memory store.
    pub fn new() -> Self {
        Self {
            definitions: RwLock::new(HashMap::new()),
            processes: RwLock::new(HashMap::new()),
            tasks: RwLock::new(HashMap::new()),
            foes: RwLock::new(HashMap::new()),
            locks: Mutex::new(HashMap::new()),
            lock_notify: Arc::new(Notify::new()),
        }
    }

    /// Clear all data. Useful for testing.
    pub async fn clear(&self) {
        self.definitions.write().await.clear();
        self.processes.write().await.clear();
        self.tasks.write().await.clear();
        self.foes.write().await.clear();
        self.locks.lock().await.clear();
    }
}

#[async_trait]
impl StateStore for InMemoryStore {
    // =========================================================================
    // Process Definition Operations
    // =========================================================================

    async fn save_definition(&self, definition: ProcessDefinition) -> Result<()> {
        self.definitions
            .write()
            .await
            .insert(definition.id.clone(), definition);
        Ok(())
    }

    async fn load_definition(&self, definition_id: &str) -> Result<Option<ProcessDefinition>> {
        Ok(self.definitions.read().await.get(definition_id).cloned())
    }

    async fn list_definitions(&self) -> Result<Vec<ProcessDefinition>> {
        Ok(self.definitions.read().await.values().cloned().collect())
    }

    async fn delete_definition(&self, definition_id: &str) -> Result<bool> {
        Ok(self.definitions.write().await.remove(definition_id).is_some())
    }

    // =========================================================================
    // Process Instance Operations
    // =========================================================================

    async fn save_process(&self, process: ProcessInstance) -> Result<()> {
        self.processes
            .write()
            .await
            .insert(process.id.clone(), process);
        Ok(())
    }

    async fn load_process(&self, process_id: &str) -> Result<Option<ProcessInstance>> {
        Ok(self.processes.read().await.get(process_id).cloned())
    }

    async fn list_processes(
        &self,
        definition_id: Option<&str>,
        include_completed: bool,
    ) -> Result<Vec<ProcessInstance>> {
        let processes = self.processes.read().await;
        let terminal_states = [ProcessState::Complete, ProcessState::Failed];

        Ok(processes
            .values()
            .filter(|p| {
                let matches_definition = definition_id
                    .map(|id| p.definition_id == id)
                    .unwrap_or(true);
                let matches_state = include_completed || !terminal_states.contains(&p.state);
                matches_definition && matches_state
            })
            .cloned()
            .collect())
    }

    async fn delete_process(&self, process_id: &str) -> Result<bool> {
        let removed = self.processes.write().await.remove(process_id).is_some();

        if removed {
            // Clean up related tasks and FOEs
            self.tasks
                .write()
                .await
                .retain(|_, t| t.process_id != process_id);
            self.foes
                .write()
                .await
                .retain(|_, f| f.process_id != process_id);
        }

        Ok(removed)
    }

    // =========================================================================
    // Task Instance Operations
    // =========================================================================

    async fn save_task(&self, task: TaskInstance) -> Result<()> {
        self.tasks.write().await.insert(task.id.clone(), task);
        Ok(())
    }

    async fn load_task(&self, task_id: &str) -> Result<Option<TaskInstance>> {
        Ok(self.tasks.read().await.get(task_id).cloned())
    }

    async fn load_tasks_for_process(&self, process_id: &str) -> Result<Vec<TaskInstance>> {
        Ok(self
            .tasks
            .read()
            .await
            .values()
            .filter(|t| t.process_id == process_id)
            .cloned()
            .collect())
    }

    async fn delete_task(&self, task_id: &str) -> Result<bool> {
        Ok(self.tasks.write().await.remove(task_id).is_some())
    }

    // =========================================================================
    // Flow of Execution Operations
    // =========================================================================

    async fn save_foe(&self, foe: FlowOfExecution) -> Result<()> {
        self.foes.write().await.insert(foe.id.clone(), foe);
        Ok(())
    }

    async fn load_foe(&self, foe_id: &str) -> Result<Option<FlowOfExecution>> {
        Ok(self.foes.read().await.get(foe_id).cloned())
    }

    async fn load_foes_for_process(&self, process_id: &str) -> Result<Vec<FlowOfExecution>> {
        Ok(self
            .foes
            .read()
            .await
            .values()
            .filter(|f| f.process_id == process_id)
            .cloned()
            .collect())
    }

    // =========================================================================
    // Locking Operations
    // =========================================================================

    async fn acquire_lock(
        &self,
        process_id: &str,
        owner: &str,
        timeout_seconds: f64,
    ) -> Result<bool> {
        let deadline = Instant::now() + Duration::from_secs_f64(timeout_seconds);

        loop {
            // Try to acquire
            {
                let mut locks = self.locks.lock().await;

                if !locks.contains_key(process_id) {
                    locks.insert(process_id.to_string(), owner.to_string());
                    return Ok(true);
                }

                // Already owned by us
                if locks.get(process_id) == Some(&owner.to_string()) {
                    return Ok(true);
                }
            }

            // Check timeout
            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                return Ok(false);
            }

            // Wait for lock release with timeout
            let wait_time = remaining.min(Duration::from_secs(1));
            tokio::select! {
                _ = self.lock_notify.notified() => {}
                _ = tokio::time::sleep(wait_time) => {}
            }
        }
    }

    async fn release_lock(&self, process_id: &str, owner: &str) -> Result<bool> {
        let mut locks = self.locks.lock().await;

        if locks.get(process_id) != Some(&owner.to_string()) {
            return Ok(false);
        }

        locks.remove(process_id);
        self.lock_notify.notify_waiters();
        Ok(true)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_save_and_load_definition() {
        let store = InMemoryStore::new();

        let mut tasks = HashMap::new();
        tasks.insert(
            "task1".to_string(),
            crate::core::models::TaskDefinition::new("task1", "Task 1"),
        );

        let definition = ProcessDefinition::new("def1", "Test Definition", "task1", tasks);

        store.save_definition(definition.clone()).await.unwrap();

        let loaded = store.load_definition("def1").await.unwrap();
        assert!(loaded.is_some());
        assert_eq!(loaded.unwrap().name, "Test Definition");
    }

    #[tokio::test]
    async fn test_save_and_load_process() {
        let store = InMemoryStore::new();

        let process = ProcessInstance::new("proc1", "def1");
        store.save_process(process.clone()).await.unwrap();

        let loaded = store.load_process("proc1").await.unwrap();
        assert!(loaded.is_some());
        assert_eq!(loaded.unwrap().definition_id, "def1");
    }

    #[tokio::test]
    async fn test_list_processes_filter() {
        let store = InMemoryStore::new();

        let proc1 = ProcessInstance::new("proc1", "def1");
        let mut proc2 = ProcessInstance::new("proc2", "def1");
        proc2.state = ProcessState::Complete;
        let proc3 = ProcessInstance::new("proc3", "def2");

        store.save_process(proc1).await.unwrap();
        store.save_process(proc2).await.unwrap();
        store.save_process(proc3).await.unwrap();

        // Filter by definition, exclude completed
        let result = store.list_processes(Some("def1"), false).await.unwrap();
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].id, "proc1");

        // Filter by definition, include completed
        let result = store.list_processes(Some("def1"), true).await.unwrap();
        assert_eq!(result.len(), 2);

        // No filter, exclude completed
        let result = store.list_processes(None, false).await.unwrap();
        assert_eq!(result.len(), 2);
    }

    #[tokio::test]
    async fn test_lock_acquire_release() {
        let store = InMemoryStore::new();

        // Acquire lock
        let acquired = store.acquire_lock("proc1", "owner1", 1.0).await.unwrap();
        assert!(acquired);

        // Same owner can re-acquire
        let reacquired = store.acquire_lock("proc1", "owner1", 1.0).await.unwrap();
        assert!(reacquired);

        // Release lock
        let released = store.release_lock("proc1", "owner1").await.unwrap();
        assert!(released);

        // Different owner can now acquire
        let acquired = store.acquire_lock("proc1", "owner2", 1.0).await.unwrap();
        assert!(acquired);
    }

    #[tokio::test]
    async fn test_lock_timeout() {
        let store = Arc::new(InMemoryStore::new());

        // First owner acquires
        store.acquire_lock("proc1", "owner1", 1.0).await.unwrap();

        // Second owner times out
        let acquired = store.acquire_lock("proc1", "owner2", 0.1).await.unwrap();
        assert!(!acquired);
    }

    #[tokio::test]
    async fn test_delete_process_cleans_up() {
        let store = InMemoryStore::new();

        // Create process with tasks and FOEs
        let process = ProcessInstance::new("proc1", "def1");
        store.save_process(process).await.unwrap();

        let task =
            crate::core::models::TaskInstance::new("task1", "proc1", "task_def1", "foe1");
        store.save_task(task).await.unwrap();

        let foe = crate::core::models::FlowOfExecution::new("foe1", "proc1");
        store.save_foe(foe).await.unwrap();

        // Delete process
        store.delete_process("proc1").await.unwrap();

        // Verify cleanup
        assert!(store.load_process("proc1").await.unwrap().is_none());
        assert!(store.load_tasks_for_process("proc1").await.unwrap().is_empty());
        assert!(store.load_foes_for_process("proc1").await.unwrap().is_empty());
    }
}
