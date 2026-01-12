//! Core data models for the Zebra workflow engine.
//!
//! This module defines the data structures used throughout the workflow engine,
//! including both definition models (workflow blueprints) and runtime state models.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;

// =============================================================================
// Process and Task States (Runtime)
// =============================================================================

/// State machine for process instances.
///
/// Lifecycle: CREATED -> RUNNING -> COMPLETE
///                          |-> PAUSED -> RUNNING
///                          |-> FAILED
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ProcessState {
    /// Initial state after instantiation
    Created,
    /// Active execution
    Running,
    /// Suspended, can be resumed
    Paused,
    /// Terminal state - success
    Complete,
    /// Terminal state - error
    Failed,
}

impl ProcessState {
    /// Check if this is a terminal state
    pub fn is_terminal(&self) -> bool {
        matches!(self, ProcessState::Complete | ProcessState::Failed)
    }
}

/// State machine for task instances.
///
/// Lifecycle for auto tasks: PENDING -> READY -> RUNNING -> COMPLETE
/// Lifecycle for sync tasks: PENDING -> AWAITING_SYNC -> READY -> RUNNING -> COMPLETE
/// Manual tasks wait in READY state until explicitly transitioned.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum TaskState {
    /// Created but not yet processed
    Pending,
    /// Waiting for parallel branches (join point)
    #[serde(rename = "awaiting_sync")]
    AwaitingSync,
    /// Ready to execute (manual tasks wait here)
    Ready,
    /// Currently executing
    Running,
    /// Terminal state - success
    Complete,
    /// Terminal state - error
    Failed,
}

impl TaskState {
    /// Check if this is a terminal state
    pub fn is_terminal(&self) -> bool {
        matches!(self, TaskState::Complete | TaskState::Failed)
    }
}

// =============================================================================
// Definition Models (Workflow Blueprints)
// =============================================================================

/// Definition of a task within a workflow.
///
/// Corresponds to Java ITaskDefinition. Defines the blueprint for a task
/// including its behavior (auto vs manual), synchronization, and action class.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskDefinition {
    /// Unique identifier for this task within the process
    pub id: String,
    /// Human-readable name for the task
    pub name: String,
    /// If true, task executes automatically. If false, waits for manual transition.
    #[serde(default = "default_true")]
    pub auto: bool,
    /// If true, this is a join point that waits for all incoming parallel branches.
    #[serde(default)]
    pub synchronized: bool,
    /// Name of the TaskAction to execute (registered in ActionRegistry)
    #[serde(default)]
    pub action: Option<String>,
    /// Action to run before task execution (setup)
    #[serde(default)]
    pub construct_action: Option<String>,
    /// Action to run after task completion (cleanup)
    #[serde(default)]
    pub destruct_action: Option<String>,
    /// Task-specific configuration properties
    #[serde(default)]
    pub properties: HashMap<String, Value>,
}

fn default_true() -> bool {
    true
}

impl TaskDefinition {
    /// Create a new task definition with required fields
    pub fn new(id: impl Into<String>, name: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            name: name.into(),
            auto: true,
            synchronized: false,
            action: None,
            construct_action: None,
            destruct_action: None,
            properties: HashMap::new(),
        }
    }

    /// Builder method to set auto execution
    pub fn with_auto(mut self, auto: bool) -> Self {
        self.auto = auto;
        self
    }

    /// Builder method to set synchronized flag
    pub fn with_synchronized(mut self, synchronized: bool) -> Self {
        self.synchronized = synchronized;
        self
    }

    /// Builder method to set action
    pub fn with_action(mut self, action: impl Into<String>) -> Self {
        self.action = Some(action.into());
        self
    }

    /// Builder method to set properties
    pub fn with_properties(mut self, properties: HashMap<String, Value>) -> Self {
        self.properties = properties;
        self
    }
}

/// Definition of a routing (edge) between tasks.
///
/// Corresponds to Java IRoutingDefinition. Defines how execution flows
/// from one task to another, with optional conditions and parallel execution.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RoutingDefinition {
    /// Unique identifier for this routing
    pub id: String,
    /// ID of the originating task
    pub source_task_id: String,
    /// ID of the destination task
    pub dest_task_id: String,
    /// If true, this routing executes in parallel with others. Creates new FOE.
    #[serde(default)]
    pub parallel: bool,
    /// Name of ConditionAction to evaluate. If None, routing always fires.
    #[serde(default)]
    pub condition: Option<String>,
    /// Optional name for the routing (used by some condition actions)
    #[serde(default)]
    pub name: Option<String>,
}

impl RoutingDefinition {
    /// Create a new routing definition
    pub fn new(
        id: impl Into<String>,
        source_task_id: impl Into<String>,
        dest_task_id: impl Into<String>,
    ) -> Self {
        Self {
            id: id.into(),
            source_task_id: source_task_id.into(),
            dest_task_id: dest_task_id.into(),
            parallel: false,
            condition: None,
            name: None,
        }
    }

    /// Builder method to set parallel flag
    pub fn with_parallel(mut self, parallel: bool) -> Self {
        self.parallel = parallel;
        self
    }

    /// Builder method to set condition
    pub fn with_condition(mut self, condition: impl Into<String>) -> Self {
        self.condition = Some(condition.into());
        self
    }

    /// Builder method to set name
    pub fn with_name(mut self, name: impl Into<String>) -> Self {
        self.name = Some(name.into());
        self
    }
}

/// Definition of a complete workflow process.
///
/// Corresponds to Java IProcessDefinition. This is the blueprint for a
/// workflow, containing all task and routing definitions.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcessDefinition {
    /// Unique identifier for this process definition
    pub id: String,
    /// Human-readable name for the workflow
    pub name: String,
    /// Version number for the definition
    #[serde(default = "default_version")]
    pub version: i32,
    /// ID of the entry point task
    pub first_task_id: String,
    /// Map of task ID to task definition
    pub tasks: HashMap<String, TaskDefinition>,
    /// List of routing definitions
    #[serde(default)]
    pub routings: Vec<RoutingDefinition>,
    /// Action to run when process starts
    #[serde(default)]
    pub construct_action: Option<String>,
    /// Action to run when process completes
    #[serde(default)]
    pub destruct_action: Option<String>,
    /// Process-level configuration properties
    #[serde(default)]
    pub properties: HashMap<String, Value>,
}

fn default_version() -> i32 {
    1
}

impl ProcessDefinition {
    /// Create a new process definition
    pub fn new(
        id: impl Into<String>,
        name: impl Into<String>,
        first_task_id: impl Into<String>,
        tasks: HashMap<String, TaskDefinition>,
    ) -> Self {
        Self {
            id: id.into(),
            name: name.into(),
            version: 1,
            first_task_id: first_task_id.into(),
            tasks,
            routings: Vec::new(),
            construct_action: None,
            destruct_action: None,
            properties: HashMap::new(),
        }
    }

    /// Get a task definition by ID
    pub fn get_task(&self, task_id: &str) -> Option<&TaskDefinition> {
        self.tasks.get(task_id)
    }

    /// Get all outgoing routings from a task
    pub fn get_routings_from(&self, task_id: &str) -> Vec<&RoutingDefinition> {
        self.routings
            .iter()
            .filter(|r| r.source_task_id == task_id)
            .collect()
    }

    /// Get all incoming routings to a task
    pub fn get_routings_to(&self, task_id: &str) -> Vec<&RoutingDefinition> {
        self.routings
            .iter()
            .filter(|r| r.dest_task_id == task_id)
            .collect()
    }

    /// Builder method to add routings
    pub fn with_routings(mut self, routings: Vec<RoutingDefinition>) -> Self {
        self.routings = routings;
        self
    }

    /// Builder method to set construct action
    pub fn with_construct_action(mut self, action: impl Into<String>) -> Self {
        self.construct_action = Some(action.into());
        self
    }

    /// Builder method to set destruct action
    pub fn with_destruct_action(mut self, action: impl Into<String>) -> Self {
        self.destruct_action = Some(action.into());
        self
    }
}

// =============================================================================
// Runtime State Models (Instances)
// =============================================================================

/// Tracks a single execution path through the workflow.
///
/// Corresponds to Java IFOE. When a workflow splits into parallel branches,
/// each branch gets its own FOE. When branches join (sync point), FOEs are
/// merged. This enables tracking of parallel execution and proper synchronization.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FlowOfExecution {
    /// Unique identifier for this FOE
    pub id: String,
    /// ID of the owning process instance
    pub process_id: String,
    /// Parent FOE ID (for tracking lineage)
    #[serde(default)]
    pub parent_foe_id: Option<String>,
    /// When this FOE was created
    pub created_at: DateTime<Utc>,
}

impl FlowOfExecution {
    /// Create a new FOE
    pub fn new(id: impl Into<String>, process_id: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            process_id: process_id.into(),
            parent_foe_id: None,
            created_at: Utc::now(),
        }
    }

    /// Builder method to set parent FOE
    pub fn with_parent(mut self, parent_foe_id: impl Into<String>) -> Self {
        self.parent_foe_id = Some(parent_foe_id.into());
        self
    }
}

/// Runtime instance of a task within a running process.
///
/// Corresponds to Java ITaskInstance. Represents the current state of a
/// specific task execution, including its FOE for parallel tracking.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskInstance {
    /// Unique identifier for this task instance
    pub id: String,
    /// ID of the owning process instance
    pub process_id: String,
    /// ID of the task definition
    pub task_definition_id: String,
    /// Current state of the task
    pub state: TaskState,
    /// Flow of Execution ID for parallel tracking
    pub foe_id: String,
    /// Runtime properties (can be modified during execution)
    #[serde(default)]
    pub properties: HashMap<String, Value>,
    /// Output from task execution
    #[serde(default)]
    pub result: Option<Value>,
    /// Error message if task failed
    #[serde(default)]
    pub error: Option<String>,
    /// When this task was created
    pub created_at: DateTime<Utc>,
    /// When this task was last updated
    pub updated_at: DateTime<Utc>,
    /// When this task completed
    #[serde(default)]
    pub completed_at: Option<DateTime<Utc>>,
}

impl TaskInstance {
    /// Create a new task instance
    pub fn new(
        id: impl Into<String>,
        process_id: impl Into<String>,
        task_definition_id: impl Into<String>,
        foe_id: impl Into<String>,
    ) -> Self {
        let now = Utc::now();
        Self {
            id: id.into(),
            process_id: process_id.into(),
            task_definition_id: task_definition_id.into(),
            state: TaskState::Pending,
            foe_id: foe_id.into(),
            properties: HashMap::new(),
            result: None,
            error: None,
            created_at: now,
            updated_at: now,
            completed_at: None,
        }
    }

    /// Builder method to set state
    pub fn with_state(mut self, state: TaskState) -> Self {
        self.state = state;
        self
    }

    /// Builder method to set properties
    pub fn with_properties(mut self, properties: HashMap<String, Value>) -> Self {
        self.properties = properties;
        self
    }
}

/// Runtime instance of a workflow process.
///
/// Corresponds to Java IProcessInstance. Represents a running or completed
/// workflow execution with all its state.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcessInstance {
    /// Unique identifier for this process instance
    pub id: String,
    /// ID of the process definition
    pub definition_id: String,
    /// Current state of the process
    pub state: ProcessState,
    /// Runtime properties accessible to all tasks
    #[serde(default)]
    pub properties: HashMap<String, Value>,
    /// Parent process ID for subflows
    #[serde(default)]
    pub parent_process_id: Option<String>,
    /// Parent task ID that spawned this subflow
    #[serde(default)]
    pub parent_task_id: Option<String>,
    /// When this process was created
    pub created_at: DateTime<Utc>,
    /// When this process was last updated
    pub updated_at: DateTime<Utc>,
    /// When this process completed
    #[serde(default)]
    pub completed_at: Option<DateTime<Utc>>,
}

impl ProcessInstance {
    /// Create a new process instance
    pub fn new(id: impl Into<String>, definition_id: impl Into<String>) -> Self {
        let now = Utc::now();
        Self {
            id: id.into(),
            definition_id: definition_id.into(),
            state: ProcessState::Created,
            properties: HashMap::new(),
            parent_process_id: None,
            parent_task_id: None,
            created_at: now,
            updated_at: now,
            completed_at: None,
        }
    }

    /// Builder method to set properties
    pub fn with_properties(mut self, properties: HashMap<String, Value>) -> Self {
        self.properties = properties;
        self
    }

    /// Builder method to set parent process
    pub fn with_parent_process(mut self, parent_process_id: impl Into<String>) -> Self {
        self.parent_process_id = Some(parent_process_id.into());
        self
    }

    /// Builder method to set parent task
    pub fn with_parent_task(mut self, parent_task_id: impl Into<String>) -> Self {
        self.parent_task_id = Some(parent_task_id.into());
        self
    }
}

// =============================================================================
// Task Results
// =============================================================================

/// Result from executing a task action.
///
/// Returned by TaskAction::run() to indicate success/failure and provide output.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TaskResult {
    /// Whether the task completed successfully
    pub success: bool,
    /// Output data from the task
    #[serde(default)]
    pub output: Option<Value>,
    /// Error message if failed
    #[serde(default)]
    pub error: Option<String>,
    /// For decision tasks: name of the routing to follow (overrides conditions)
    #[serde(default)]
    pub next_route: Option<String>,
}

impl TaskResult {
    /// Create a successful result
    pub fn ok() -> Self {
        Self {
            success: true,
            output: None,
            error: None,
            next_route: None,
        }
    }

    /// Create a successful result with output
    pub fn ok_with_output(output: Value) -> Self {
        Self {
            success: true,
            output: Some(output),
            error: None,
            next_route: None,
        }
    }

    /// Create a failed result
    pub fn fail(error: impl Into<String>) -> Self {
        Self {
            success: false,
            output: None,
            error: Some(error.into()),
            next_route: None,
        }
    }

    /// Builder method to set next route
    pub fn with_next_route(mut self, route: impl Into<String>) -> Self {
        self.next_route = Some(route.into());
        self
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_process_state_is_terminal() {
        assert!(!ProcessState::Created.is_terminal());
        assert!(!ProcessState::Running.is_terminal());
        assert!(!ProcessState::Paused.is_terminal());
        assert!(ProcessState::Complete.is_terminal());
        assert!(ProcessState::Failed.is_terminal());
    }

    #[test]
    fn test_task_state_is_terminal() {
        assert!(!TaskState::Pending.is_terminal());
        assert!(!TaskState::AwaitingSync.is_terminal());
        assert!(!TaskState::Ready.is_terminal());
        assert!(!TaskState::Running.is_terminal());
        assert!(TaskState::Complete.is_terminal());
        assert!(TaskState::Failed.is_terminal());
    }

    #[test]
    fn test_task_definition_builder() {
        let task = TaskDefinition::new("t1", "Task 1")
            .with_auto(false)
            .with_synchronized(true)
            .with_action("my_action");

        assert_eq!(task.id, "t1");
        assert_eq!(task.name, "Task 1");
        assert!(!task.auto);
        assert!(task.synchronized);
        assert_eq!(task.action.as_deref(), Some("my_action"));
    }

    #[test]
    fn test_task_result_ok() {
        let result = TaskResult::ok();
        assert!(result.success);
        assert!(result.output.is_none());
        assert!(result.error.is_none());
    }

    #[test]
    fn test_task_result_fail() {
        let result = TaskResult::fail("something went wrong");
        assert!(!result.success);
        assert!(result.output.is_none());
        assert_eq!(result.error.as_deref(), Some("something went wrong"));
    }
}
