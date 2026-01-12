//! Core workflow engine implementation.
//!
//! This module contains the WorkflowEngine struct that controls the execution
//! of workflow processes. Ported from Java Engine class.

use std::collections::HashMap;
use std::sync::Arc;

use chrono::Utc;
use tracing::{error, info, warn};
use uuid::Uuid;

use super::errors::{DefinitionError, ExecutionError, Result, StateError, ZebraError};
use super::models::{
    FlowOfExecution, ProcessDefinition, ProcessInstance, ProcessState, RoutingDefinition,
    TaskDefinition, TaskInstance, TaskResult, TaskState,
};
use super::sync::TaskSync;
use crate::storage::StateStore;
use crate::tasks::{ActionRegistry, ExecutionContext};

/// Main workflow engine that controls process execution.
///
/// Corresponds to Java Engine class. Handles:
/// - Process creation and lifecycle
/// - Task state transitions
/// - Routing evaluation (serial and parallel)
/// - Synchronization/join points
/// - Action execution
pub struct WorkflowEngine<S: StateStore> {
    /// Storage backend for persistence
    pub store: Arc<S>,
    /// Registry of task actions and conditions
    pub actions: Arc<ActionRegistry<S>>,
    /// Unique ID for this engine instance (for locking)
    pub engine_id: String,
    /// Task synchronization helper
    task_sync: TaskSync,
}

impl<S: StateStore + 'static> WorkflowEngine<S> {
    /// Create a new workflow engine.
    ///
    /// # Arguments
    /// * `store` - Storage backend for persistence
    /// * `action_registry` - Registry of task actions and conditions
    pub fn new(store: Arc<S>, action_registry: Arc<ActionRegistry<S>>) -> Self {
        Self {
            store,
            actions: action_registry,
            engine_id: Uuid::new_v4().to_string(),
            task_sync: TaskSync::new(),
        }
    }

    /// Create a new workflow engine with a custom engine ID.
    pub fn with_engine_id(
        store: Arc<S>,
        action_registry: Arc<ActionRegistry<S>>,
        engine_id: impl Into<String>,
    ) -> Self {
        Self {
            store,
            actions: action_registry,
            engine_id: engine_id.into(),
            task_sync: TaskSync::new(),
        }
    }

    // =========================================================================
    // Process Lifecycle
    // =========================================================================

    /// Create a new process instance from a definition.
    ///
    /// The process is created in CREATED state and must be started
    /// with start_process() to begin execution.
    pub async fn create_process(
        &self,
        definition: ProcessDefinition,
        properties: Option<HashMap<String, serde_json::Value>>,
        parent_process_id: Option<String>,
        parent_task_id: Option<String>,
    ) -> Result<ProcessInstance> {
        // Ensure definition is saved
        self.store.save_definition(definition.clone()).await?;

        let mut process = ProcessInstance::new(Uuid::new_v4().to_string(), &definition.id);
        process.state = ProcessState::Created;
        process.properties = properties.unwrap_or_default();
        process.parent_process_id = parent_process_id;
        process.parent_task_id = parent_task_id;
        process.created_at = Utc::now();
        process.updated_at = Utc::now();

        self.store.save_process(process.clone()).await?;
        info!("Created process {} from definition {}", process.id, definition.id);

        Ok(process)
    }

    /// Start a process that is in CREATED state.
    ///
    /// Creates the first task and begins execution. If the first task
    /// is auto-executable, it will be transitioned immediately.
    pub async fn start_process(&self, process_id: &str) -> Result<ProcessInstance> {
        let process = self.load_process(process_id).await?;

        if process.state != ProcessState::Created {
            return Err(StateError::InvalidStateTransition(format!(
                "Process {} is in state {:?}, expected Created",
                process_id, process.state
            ))
            .into());
        }

        let definition = self.load_definition(&process.definition_id).await?;

        // Run process construct action if defined
        if definition.construct_action.is_some() {
            self.run_process_construct(&process, &definition).await?;
        }

        // Update state to RUNNING
        let mut process = process;
        process.state = ProcessState::Running;
        process.updated_at = Utc::now();
        self.store.save_process(process.clone()).await?;

        // Create the first FOE and task
        let foe = self.create_foe(&process, None).await?;
        let first_task_def = definition
            .get_task(&definition.first_task_id)
            .ok_or_else(|| {
                DefinitionError::NotFound(format!(
                    "First task '{}' not found in definition",
                    definition.first_task_id
                ))
            })?;

        let task = self.create_task(first_task_def, &process, &foe).await?;
        info!("Started process {}, first task is {}", process_id, task.id);

        // If first task is auto, transition it
        if first_task_def.auto {
            self.transition_task(&task.id).await?;
        }

        self.load_process(process_id).await
    }

    /// Pause a running process.
    ///
    /// The process can be resumed later with resume_process().
    pub async fn pause_process(&self, process_id: &str) -> Result<ProcessInstance> {
        let process = self.load_process(process_id).await?;

        if process.state != ProcessState::Running {
            return Err(StateError::InvalidStateTransition(format!(
                "Process {} is in state {:?}, expected Running",
                process_id, process.state
            ))
            .into());
        }

        let mut process = process;
        process.state = ProcessState::Paused;
        process.updated_at = Utc::now();
        self.store.save_process(process.clone()).await?;

        info!("Paused process {}", process_id);
        Ok(process)
    }

    /// Resume a paused process.
    pub async fn resume_process(&self, process_id: &str) -> Result<ProcessInstance> {
        let process = self.load_process(process_id).await?;

        if process.state != ProcessState::Paused {
            return Err(StateError::InvalidStateTransition(format!(
                "Process {} is in state {:?}, expected Paused",
                process_id, process.state
            ))
            .into());
        }

        let mut process = process;
        process.state = ProcessState::Running;
        process.updated_at = Utc::now();
        self.store.save_process(process.clone()).await?;

        info!("Resumed process {}", process_id);

        // Check if there are any auto tasks that need to run
        self.process_pending_auto_tasks(&process).await?;

        Ok(process)
    }

    // =========================================================================
    // Task Transitions
    // =========================================================================

    /// Transition a task through its lifecycle.
    ///
    /// This is the main entry point for task execution. It handles:
    /// - Acquiring a lock on the process
    /// - Running the task action (if any)
    /// - Evaluating outbound routings
    /// - Creating new tasks based on routing results
    /// - Processing auto tasks recursively
    pub async fn transition_task(&self, task_id: &str) -> Result<Vec<TaskInstance>> {
        let task = self.load_task(task_id).await?;
        let process = self.load_process(&task.process_id).await?;

        // Acquire lock on process
        let acquired = self
            .store
            .acquire_lock(&process.id, &self.engine_id, 30.0)
            .await?;

        if !acquired {
            return Err(StateError::Lock(format!("Failed to acquire lock on process {}", process.id)).into());
        }

        let result = self.transition_task_locked(&task, &process).await;

        // Always release lock
        let _ = self.store.release_lock(&process.id, &self.engine_id).await;

        result
    }

    async fn transition_task_locked(
        &self,
        initial_task: &TaskInstance,
        process: &ProcessInstance,
    ) -> Result<Vec<TaskInstance>> {
        // Stack-based processing for auto tasks
        let mut task_stack: Vec<TaskInstance> = vec![initial_task.clone()];
        let mut all_created_tasks: Vec<TaskInstance> = Vec::new();

        while let Some(current_task) = task_stack.pop() {
            match self.transition_task_internal(&current_task, process).await {
                Ok(created_tasks) => {
                    all_created_tasks.extend(created_tasks.clone());

                    // Add auto tasks to stack for processing
                    let definition = self.load_definition(&process.definition_id).await?;
                    for new_task in created_tasks {
                        if let Some(task_def) = definition.get_task(&new_task.task_definition_id) {
                            if task_def.auto || task_def.synchronized {
                                if !task_stack.iter().any(|t| t.id == new_task.id) {
                                    task_stack.push(new_task);
                                }
                            }
                        }
                    }
                }
                Err(e) => {
                    error!("Error transitioning task {}: {}", current_task.id, e);
                    return Err(e);
                }
            }
        }

        // Check if process is complete
        let process = self.load_process(&process.id).await?;
        let tasks = self.store.load_tasks_for_process(&process.id).await?;
        let active_tasks: Vec<_> = tasks.iter().filter(|t| !t.state.is_terminal()).collect();

        if active_tasks.is_empty() {
            self.complete_process(&process).await?;
        }

        Ok(all_created_tasks)
    }

    /// Complete a manual task and transition it.
    ///
    /// Use this for tasks that are not auto-executable (e.g., waiting
    /// for user input).
    pub async fn complete_task(
        &self,
        task_id: &str,
        result: Option<TaskResult>,
    ) -> Result<Vec<TaskInstance>> {
        let task = self.load_task(task_id).await?;

        if !matches!(task.state, TaskState::Ready | TaskState::Running) {
            return Err(StateError::InvalidStateTransition(format!(
                "Task {} is in state {:?}, expected Ready or Running",
                task_id, task.state
            ))
            .into());
        }

        // Update task with result
        let mut task = task;
        task.updated_at = Utc::now();
        task.completed_at = Some(Utc::now());

        if let Some(ref result) = result {
            task.result = result.output.clone();
            task.error = result.error.clone();
            task.state = if result.success {
                TaskState::Complete
            } else {
                TaskState::Failed
            };
        } else {
            task.state = TaskState::Complete;
        }

        self.store.save_task(task.clone()).await?;

        // Store result in process properties for later reference
        let process = self.load_process(&task.process_id).await?;
        if let Some(result) = &result {
            if let Some(output) = &result.output {
                let mut process = process.clone();
                process.properties.insert(
                    format!("__task_output_{}", task.task_definition_id),
                    output.clone(),
                );
                process.updated_at = Utc::now();
                self.store.save_process(process).await?;
            }
        }

        self.transition_task(&task.id).await
    }

    // =========================================================================
    // Internal Methods
    // =========================================================================

    async fn transition_task_internal(
        &self,
        task: &TaskInstance,
        process: &ProcessInstance,
    ) -> Result<Vec<TaskInstance>> {
        let definition = self.load_definition(&process.definition_id).await?;
        let task_def = definition.get_task(&task.task_definition_id).ok_or_else(|| {
            DefinitionError::NotFound(format!("Task definition '{}' not found", task.task_definition_id))
        })?;

        let mut task = task.clone();

        // Handle sync tasks
        if task_def.synchronized && task.state == TaskState::AwaitingSync {
            let active_tasks = self.store.load_tasks_for_process(&process.id).await?;
            if self.task_sync.is_task_blocked(&task, task_def, &definition, &active_tasks) {
                info!("Task {} is blocked, waiting for sync", task.id);
                return Ok(Vec::new());
            }

            // Unblocked - transition to READY
            task.state = TaskState::Ready;
            task.updated_at = Utc::now();
            self.store.save_task(task.clone()).await?;
        }

        // Run task if in READY state
        if task.state == TaskState::Ready {
            self.run_task(&task, task_def, process, &definition).await?;
            task = self.load_task(&task.id).await?; // Reload after run
        }

        // Check if task completed
        if task.state != TaskState::Complete {
            info!("Task {} is in state {:?}, not transitioning further", task.id, task.state);
            return Ok(Vec::new());
        }

        // Run routing
        let created_tasks = self.run_routing(&task, task_def, process, &definition).await?;

        // Check for sync tasks that might now be unblocked
        let active_tasks = self.store.load_tasks_for_process(&process.id).await?;
        let sync_task_ids = self.task_sync.get_potential_task_locks(task_def, &definition);

        let mut result_tasks = created_tasks;
        for active_task in &active_tasks {
            if sync_task_ids.contains(&active_task.task_definition_id) {
                if active_task.state == TaskState::AwaitingSync {
                    if !result_tasks.iter().any(|t| t.id == active_task.id) {
                        result_tasks.push(active_task.clone());
                    }
                }
            }
        }

        // Delete completed task
        self.store.delete_task(&task.id).await?;

        Ok(result_tasks)
    }

    async fn run_task(
        &self,
        task: &TaskInstance,
        task_def: &TaskDefinition,
        process: &ProcessInstance,
        definition: &ProcessDefinition,
    ) -> Result<()> {
        // Update state to RUNNING
        let mut task = task.clone();
        task.state = TaskState::Running;
        task.updated_at = Utc::now();
        self.store.save_task(task.clone()).await?;

        let context = ExecutionContext::new(
            self.store.clone(),
            process.clone(),
            definition.clone(),
            task_def.clone(),
        );

        let result: TaskResult;

        if let Some(action_name) = &task_def.action {
            match self.actions.get_action(action_name) {
                Ok(action) => {
                    // Run construct if defined
                    if let Err(e) = action.on_construct(&task, &context).await {
                        warn!("Error in task construct: {}", e);
                    }

                    // Run main action
                    match action.run(&task, &context).await {
                        Ok(r) => result = r,
                        Err(e) => {
                            error!("Error running task {}: {}", task.id, e);
                            result = TaskResult::fail(e.to_string());
                        }
                    }

                    // Run destruct
                    if let Err(e) = action.on_destruct(&task, &context).await {
                        warn!("Error in task destruct: {}", e);
                    }
                }
                Err(_) => {
                    result = TaskResult::fail(format!("Action '{}' not found", action_name));
                }
            }
        } else {
            // No action - auto-complete
            result = TaskResult::ok();
        }

        // Update task with result
        let new_state = if result.success {
            TaskState::Complete
        } else {
            TaskState::Failed
        };

        task.state = new_state;
        task.result = result.output.clone();
        task.error = result.error.clone();
        task.updated_at = Utc::now();
        task.completed_at = Some(Utc::now());
        self.store.save_task(task.clone()).await?;

        // Store result in process properties
        if let Some(output) = &result.output {
            let mut process = process.clone();
            process
                .properties
                .insert(format!("__task_output_{}", task_def.id), output.clone());
            process.updated_at = Utc::now();
            self.store.save_process(process).await?;
        }

        Ok(())
    }

    async fn run_routing(
        &self,
        task: &TaskInstance,
        task_def: &TaskDefinition,
        process: &ProcessInstance,
        definition: &ProcessDefinition,
    ) -> Result<Vec<TaskInstance>> {
        let routings = definition.get_routings_from(&task_def.id);
        if routings.is_empty() {
            return Ok(Vec::new());
        }

        let context = ExecutionContext::new(
            self.store.clone(),
            process.clone(),
            definition.clone(),
            task_def.clone(),
        );

        let mut done_serial_routing = false;
        let mut create_list: Vec<&RoutingDefinition> = Vec::new();

        for routing in &routings {
            let do_routing = if !routing.parallel && !done_serial_routing {
                true
            } else {
                routing.parallel
            };

            if do_routing {
                // Evaluate condition
                let should_fire = match self.actions.get_condition(routing.condition.as_deref()) {
                    Ok(condition) => match condition.evaluate(routing, task, &context).await {
                        Ok(result) => result,
                        Err(e) => {
                            error!("Error evaluating condition: {}", e);
                            false
                        }
                    },
                    Err(_) => {
                        warn!(
                            "Condition '{:?}' not found, defaulting to true",
                            routing.condition
                        );
                        true
                    }
                };

                if should_fire {
                    create_list.push(routing);
                    if !routing.parallel {
                        done_serial_routing = true;
                    }
                }
            }
        }

        // Check for routing errors
        if create_list.is_empty() && !routings.is_empty() {
            let task_id = task.id.clone();
            let mut task = task.clone();
            task.state = TaskState::Failed;
            task.error = Some("No routing fired".to_string());
            self.store.save_task(task).await?;
            return Err(ExecutionError::Routing(format!(
                "Routing exists for task {} but none fired",
                task_id
            ))
            .into());
        }

        // Create new tasks
        let mut created_tasks: Vec<TaskInstance> = Vec::new();
        let mut foe_serial: Option<FlowOfExecution> = None;

        for routing in create_list {
            let dest_task_def = definition.get_task(&routing.dest_task_id).ok_or_else(|| {
                DefinitionError::NotFound(format!(
                    "Destination task '{}' not found",
                    routing.dest_task_id
                ))
            })?;

            let foe = if routing.parallel {
                self.create_foe(process, Some(&task.foe_id)).await?
            } else if let Some(ref foe) = foe_serial {
                foe.clone()
            } else {
                let foe = match self.store.load_foe(&task.foe_id).await? {
                    Some(foe) => foe,
                    None => self.create_foe(process, Some(&task.foe_id)).await?,
                };
                foe_serial = Some(foe.clone());
                foe
            };

            let new_task = self.create_task(dest_task_def, process, &foe).await?;
            if !created_tasks.iter().any(|t| t.id == new_task.id) {
                created_tasks.push(new_task);
            }
        }

        Ok(created_tasks)
    }

    async fn create_task(
        &self,
        task_def: &TaskDefinition,
        process: &ProcessInstance,
        foe: &FlowOfExecution,
    ) -> Result<TaskInstance> {
        // For sync tasks, check if one already exists
        if task_def.synchronized {
            let existing_tasks = self.store.load_tasks_for_process(&process.id).await?;
            for existing in existing_tasks {
                if existing.task_definition_id == task_def.id {
                    info!("Reusing existing sync task {}", existing.id);
                    return Ok(existing);
                }
            }
        }

        // Determine initial state
        let initial_state = if task_def.synchronized {
            TaskState::AwaitingSync
        } else if task_def.construct_action.is_some() {
            TaskState::Pending
        } else {
            TaskState::Ready
        };

        // For sync tasks, create a new FOE
        let foe = if task_def.synchronized {
            self.create_foe(process, Some(&foe.id)).await?
        } else {
            foe.clone()
        };

        let mut task = TaskInstance::new(
            Uuid::new_v4().to_string(),
            &process.id,
            &task_def.id,
            &foe.id,
        );
        task.state = initial_state;
        task.properties = task_def
            .properties
            .iter()
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect();

        self.store.save_task(task.clone()).await?;
        info!(
            "Created task {} ({}) in state {:?}",
            task.id, task_def.name, initial_state
        );

        Ok(task)
    }

    async fn create_foe(
        &self,
        process: &ProcessInstance,
        parent_foe_id: Option<&str>,
    ) -> Result<FlowOfExecution> {
        let mut foe = FlowOfExecution::new(Uuid::new_v4().to_string(), &process.id);
        foe.parent_foe_id = parent_foe_id.map(String::from);
        foe.created_at = Utc::now();

        self.store.save_foe(foe.clone()).await?;
        Ok(foe)
    }

    async fn complete_process(&self, process: &ProcessInstance) -> Result<()> {
        let definition = self.load_definition(&process.definition_id).await?;

        // Run destruct action if defined
        if definition.destruct_action.is_some() {
            if let Err(e) = self.run_process_destruct(process, &definition).await {
                error!("Error running process destruct: {}", e);
                // Don't return error - process completion should still happen
            }
        }

        let mut process = process.clone();
        process.state = ProcessState::Complete;
        process.updated_at = Utc::now();
        process.completed_at = Some(Utc::now());
        self.store.save_process(process.clone()).await?;

        info!("Process {} completed", process.id);
        Ok(())
    }

    async fn run_process_construct(
        &self,
        process: &ProcessInstance,
        definition: &ProcessDefinition,
    ) -> Result<()> {
        let Some(ref action_name) = definition.construct_action else {
            return Ok(());
        };

        let action = self.actions.get_action(action_name).map_err(|_| {
            ExecutionError::ActionNotFound(action_name.clone())
        })?;

        // Create a dummy task instance for the construct action
        let task = TaskInstance::new(
            Uuid::new_v4().to_string(),
            &process.id,
            "__process_construct__",
            "__process_construct__",
        )
        .with_state(TaskState::Running);

        let task_def = TaskDefinition::new("__process_construct__", "Process Construct");

        let context = ExecutionContext::new(
            self.store.clone(),
            process.clone(),
            definition.clone(),
            task_def,
        );

        action.run(&task, &context).await.map_err(|e| {
            ZebraError::Execution(ExecutionError::Action(format!("Process construct failed: {}", e)))
        })?;

        Ok(())
    }

    async fn run_process_destruct(
        &self,
        process: &ProcessInstance,
        definition: &ProcessDefinition,
    ) -> Result<()> {
        let Some(ref action_name) = definition.destruct_action else {
            return Ok(());
        };

        let action = self.actions.get_action(action_name).map_err(|_| {
            ExecutionError::ActionNotFound(action_name.clone())
        })?;

        let task = TaskInstance::new(
            Uuid::new_v4().to_string(),
            &process.id,
            "__process_destruct__",
            "__process_destruct__",
        )
        .with_state(TaskState::Running);

        let task_def = TaskDefinition::new("__process_destruct__", "Process Destruct");

        let context = ExecutionContext::new(
            self.store.clone(),
            process.clone(),
            definition.clone(),
            task_def,
        );

        action.run(&task, &context).await.map_err(|e| {
            ZebraError::Execution(ExecutionError::Action(format!("Process destruct failed: {}", e)))
        })?;

        Ok(())
    }

    async fn process_pending_auto_tasks(&self, process: &ProcessInstance) -> Result<()> {
        let tasks = self.store.load_tasks_for_process(&process.id).await?;
        let definition = self.load_definition(&process.definition_id).await?;

        for task in tasks {
            if task.state == TaskState::Ready {
                if let Some(task_def) = definition.get_task(&task.task_definition_id) {
                    if task_def.auto {
                        self.transition_task(&task.id).await?;
                    }
                }
            }
        }

        Ok(())
    }

    // =========================================================================
    // Helper Methods
    // =========================================================================

    async fn load_process(&self, process_id: &str) -> Result<ProcessInstance> {
        self.store
            .load_process(process_id)
            .await?
            .ok_or_else(|| StateError::ProcessNotFound(process_id.to_string()).into())
    }

    async fn load_task(&self, task_id: &str) -> Result<TaskInstance> {
        self.store
            .load_task(task_id)
            .await?
            .ok_or_else(|| StateError::TaskNotFound(task_id.to_string()).into())
    }

    async fn load_definition(&self, definition_id: &str) -> Result<ProcessDefinition> {
        self.store
            .load_definition(definition_id)
            .await?
            .ok_or_else(|| DefinitionError::NotFound(definition_id.to_string()).into())
    }

    // =========================================================================
    // Query Methods
    // =========================================================================

    /// Get detailed status of a process.
    pub async fn get_process_status(
        &self,
        process_id: &str,
    ) -> Result<ProcessStatus> {
        let process = self.load_process(process_id).await?;
        let tasks = self.store.load_tasks_for_process(process_id).await?;
        let definition = self.load_definition(&process.definition_id).await?;

        let task_statuses: Vec<TaskStatus> = tasks
            .iter()
            .map(|t| {
                let name = definition
                    .get_task(&t.task_definition_id)
                    .map(|d| d.name.clone())
                    .unwrap_or_else(|| t.task_definition_id.clone());

                TaskStatus {
                    id: t.id.clone(),
                    name,
                    state: t.state,
                    result: t.result.clone(),
                    error: t.error.clone(),
                }
            })
            .collect();

        Ok(ProcessStatus {
            id: process.id.clone(),
            definition_name: definition.name.clone(),
            state: process.state,
            created_at: process.created_at,
            updated_at: process.updated_at,
            tasks: task_statuses,
            properties: process.properties.clone(),
        })
    }

    /// Get all tasks waiting for manual completion.
    pub async fn get_pending_tasks(&self, process_id: &str) -> Result<Vec<TaskInstance>> {
        let tasks = self.store.load_tasks_for_process(process_id).await?;
        Ok(tasks
            .into_iter()
            .filter(|t| t.state == TaskState::Ready)
            .collect())
    }
}

/// Status information for a process.
#[derive(Debug, Clone)]
pub struct ProcessStatus {
    pub id: String,
    pub definition_name: String,
    pub state: ProcessState,
    pub created_at: chrono::DateTime<Utc>,
    pub updated_at: chrono::DateTime<Utc>,
    pub tasks: Vec<TaskStatus>,
    pub properties: HashMap<String, serde_json::Value>,
}

/// Status information for a task.
#[derive(Debug, Clone)]
pub struct TaskStatus {
    pub id: String,
    pub name: String,
    pub state: TaskState,
    pub result: Option<serde_json::Value>,
    pub error: Option<String>,
}
