//! Zebra - A workflow engine for orchestrating tasks and processes.
//!
//! Zebra is a modern workflow engine ported from Java, designed for
//! orchestrating complex task workflows with support for:
//!
//! - Sequential and parallel task execution
//! - Synchronization/join points for parallel branches
//! - Conditional routing between tasks
//! - Manual and automatic task execution
//! - Pluggable storage backends
//! - Extensible task actions and conditions
//!
//! # Example
//!
//! ```rust,ignore
//! use std::sync::Arc;
//! use zebra::core::{WorkflowEngine, ProcessDefinition, TaskDefinition, RoutingDefinition};
//! use zebra::storage::InMemoryStore;
//! use zebra::tasks::ActionRegistry;
//! use std::collections::HashMap;
//!
//! #[tokio::main]
//! async fn main() {
//!     // Create store and registry
//!     let store = Arc::new(InMemoryStore::new());
//!     let registry = Arc::new(ActionRegistry::new());
//!
//!     // Create engine
//!     let engine = WorkflowEngine::new(store, registry);
//!
//!     // Create a simple workflow definition
//!     let mut tasks = HashMap::new();
//!     tasks.insert("start".to_string(), TaskDefinition::new("start", "Start Task"));
//!     tasks.insert("end".to_string(), TaskDefinition::new("end", "End Task"));
//!
//!     let definition = ProcessDefinition::new("my-workflow", "My Workflow", "start", tasks)
//!         .with_routings(vec![
//!             RoutingDefinition::new("r1", "start", "end"),
//!         ]);
//!
//!     // Create and start a process
//!     let process = engine.create_process(definition, None, None, None).await.unwrap();
//!     engine.start_process(&process.id).await.unwrap();
//! }
//! ```
//!
//! # Modules
//!
//! - [`core`] - Core workflow engine and models
//! - [`storage`] - Storage backends for persistence
//! - [`tasks`] - Task actions and condition traits
//! - [`definitions`] - YAML/JSON definition loading

pub mod core;
pub mod definitions;
pub mod storage;
pub mod tasks;

// Re-export commonly used types at the crate root
pub use core::{
    FlowOfExecution, ProcessDefinition, ProcessInstance, ProcessState, Result, RoutingDefinition,
    TaskDefinition, TaskInstance, TaskResult, TaskState, WorkflowEngine, ZebraError,
};
pub use definitions::{load_definition, load_definition_from_yaml, validate_definition};
pub use storage::{InMemoryStore, StateStore};
pub use tasks::{ActionRegistry, ConditionAction, ExecutionContext, TaskAction};
