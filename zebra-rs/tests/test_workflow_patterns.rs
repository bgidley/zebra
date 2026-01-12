//! Tests for Workflow Control-Flow Patterns.
//!
//! This module tests the implementation of workflow patterns from the
//! Workflow Patterns Initiative (http://www.workflowpatterns.com).
//!
//! Reference: Russell, N., ter Hofstede, A.H.M., van der Aalst, W.M.P., & Mulyar, N. (2006).
//! "Workflow Control-Flow Patterns: A Revised View." BPM-06-22.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use async_trait::async_trait;
use serde_json::json;

use zebra::core::errors::ExecutionResult;
use zebra::core::models::{
    ProcessDefinition, ProcessState, RoutingDefinition, TaskDefinition, TaskInstance, TaskResult,
};
use zebra::core::WorkflowEngine;
use zebra::storage::InMemoryStore;
use zebra::tasks::{ActionRegistry, ExecutionContext, TaskAction};

// ============================================================================
// Test Actions
// ============================================================================

/// A test action that records execution order.
struct RecordingAction {
    executions: Arc<Mutex<Vec<String>>>,
}

impl RecordingAction {
    fn new(executions: Arc<Mutex<Vec<String>>>) -> Self {
        Self { executions }
    }
}

#[async_trait]
impl TaskAction<InMemoryStore> for RecordingAction {
    async fn run(
        &self,
        task: &TaskInstance,
        _context: &ExecutionContext<InMemoryStore>,
    ) -> ExecutionResult<TaskResult> {
        let mut execs = self.executions.lock().unwrap();
        execs.push(task.task_definition_id.clone());
        Ok(TaskResult::ok_with_output(json!({"executed": task.task_definition_id})))
    }
}

/// A test action that returns a specific route choice.
struct RouteAction {
    executions: Arc<Mutex<Vec<String>>>,
    route: String,
}

impl RouteAction {
    fn new(executions: Arc<Mutex<Vec<String>>>, route: &str) -> Self {
        Self {
            executions,
            route: route.to_string(),
        }
    }
}

#[async_trait]
impl TaskAction<InMemoryStore> for RouteAction {
    async fn run(
        &self,
        task: &TaskInstance,
        _context: &ExecutionContext<InMemoryStore>,
    ) -> ExecutionResult<TaskResult> {
        let mut execs = self.executions.lock().unwrap();
        execs.push(task.task_definition_id.clone());
        Ok(TaskResult::ok_with_output(json!({"choice": &self.route}))
            .with_next_route(&self.route))
    }
}

// ============================================================================
// Test Helpers
// ============================================================================

fn create_engine(executions: Arc<Mutex<Vec<String>>>) -> WorkflowEngine<InMemoryStore> {
    let store = Arc::new(InMemoryStore::new());
    let mut registry = ActionRegistry::new();

    let exec_clone = executions.clone();
    registry.register_action("recording", move || {
        Arc::new(RecordingAction::new(exec_clone.clone()))
    });

    let exec_clone = executions.clone();
    registry.register_action("route_small", move || {
        Arc::new(RouteAction::new(exec_clone.clone(), "small"))
    });

    let exec_clone = executions.clone();
    registry.register_action("route_large", move || {
        Arc::new(RouteAction::new(exec_clone.clone(), "large"))
    });

    WorkflowEngine::new(store, Arc::new(registry))
}

// ============================================================================
// Basic Control-Flow Patterns (WCP-1 through WCP-5)
// ============================================================================

/// WCP-1: Sequence
/// An activity is enabled after completion of a preceding activity.
#[tokio::test]
async fn test_wcp01_sequence() {
    let executions = Arc::new(Mutex::new(Vec::new()));
    let engine = create_engine(executions.clone());

    let mut tasks = HashMap::new();
    tasks.insert(
        "task_a".to_string(),
        TaskDefinition::new("task_a", "Task A").with_action("recording"),
    );
    tasks.insert(
        "task_b".to_string(),
        TaskDefinition::new("task_b", "Task B").with_action("recording"),
    );
    tasks.insert(
        "task_c".to_string(),
        TaskDefinition::new("task_c", "Task C").with_action("recording"),
    );

    let definition = ProcessDefinition::new("wcp01", "Sequence Pattern", "task_a", tasks)
        .with_routings(vec![
            RoutingDefinition::new("r1", "task_a", "task_b"),
            RoutingDefinition::new("r2", "task_b", "task_c"),
        ]);

    let process = engine
        .create_process(definition, None, None, None)
        .await
        .unwrap();
    engine.start_process(&process.id).await.unwrap();

    let execs = executions.lock().unwrap();
    assert_eq!(*execs, vec!["task_a", "task_b", "task_c"]);
}

/// WCP-2: Parallel Split (AND-split)
/// A branch diverges into two or more parallel branches that execute concurrently.
#[tokio::test]
async fn test_wcp02_parallel_split() {
    let executions = Arc::new(Mutex::new(Vec::new()));
    let engine = create_engine(executions.clone());

    let mut tasks = HashMap::new();
    tasks.insert(
        "start".to_string(),
        TaskDefinition::new("start", "Start").with_action("recording"),
    );
    tasks.insert(
        "branch_a".to_string(),
        TaskDefinition::new("branch_a", "Branch A").with_action("recording"),
    );
    tasks.insert(
        "branch_b".to_string(),
        TaskDefinition::new("branch_b", "Branch B").with_action("recording"),
    );
    tasks.insert(
        "branch_c".to_string(),
        TaskDefinition::new("branch_c", "Branch C").with_action("recording"),
    );

    let definition = ProcessDefinition::new("wcp02", "Parallel Split Pattern", "start", tasks)
        .with_routings(vec![
            RoutingDefinition::new("r1", "start", "branch_a").with_parallel(true),
            RoutingDefinition::new("r2", "start", "branch_b").with_parallel(true),
            RoutingDefinition::new("r3", "start", "branch_c").with_parallel(true),
        ]);

    let process = engine
        .create_process(definition, None, None, None)
        .await
        .unwrap();
    engine.start_process(&process.id).await.unwrap();

    let execs = executions.lock().unwrap();
    assert_eq!(execs[0], "start");
    let branches: std::collections::HashSet<_> = execs[1..].iter().collect();
    assert!(branches.contains(&"branch_a".to_string()));
    assert!(branches.contains(&"branch_b".to_string()));
    assert!(branches.contains(&"branch_c".to_string()));
}

/// WCP-3: Synchronization (AND-join)
/// Multiple branches converge, waiting for all branches to complete before proceeding.
#[tokio::test]
async fn test_wcp03_synchronization() {
    let executions = Arc::new(Mutex::new(Vec::new()));
    let engine = create_engine(executions.clone());

    let mut tasks = HashMap::new();
    tasks.insert(
        "start".to_string(),
        TaskDefinition::new("start", "Start").with_action("recording"),
    );
    tasks.insert(
        "branch_a".to_string(),
        TaskDefinition::new("branch_a", "Branch A").with_action("recording"),
    );
    tasks.insert(
        "branch_b".to_string(),
        TaskDefinition::new("branch_b", "Branch B").with_action("recording"),
    );
    tasks.insert(
        "join".to_string(),
        TaskDefinition::new("join", "Join")
            .with_synchronized(true)
            .with_action("recording"),
    );

    let definition = ProcessDefinition::new("wcp03", "Synchronization Pattern", "start", tasks)
        .with_routings(vec![
            RoutingDefinition::new("r1", "start", "branch_a").with_parallel(true),
            RoutingDefinition::new("r2", "start", "branch_b").with_parallel(true),
            RoutingDefinition::new("r3", "branch_a", "join"),
            RoutingDefinition::new("r4", "branch_b", "join"),
        ]);

    let process = engine
        .create_process(definition, None, None, None)
        .await
        .unwrap();
    engine.start_process(&process.id).await.unwrap();

    let execs = executions.lock().unwrap();
    // Join should be last, after both branches
    assert_eq!(execs.last().unwrap(), "join");
    assert!(execs.contains(&"branch_a".to_string()));
    assert!(execs.contains(&"branch_b".to_string()));
}

/// WCP-4: Exclusive Choice (XOR-split)
/// One of several branches is chosen based on a condition.
#[tokio::test]
async fn test_wcp04_exclusive_choice() {
    let executions = Arc::new(Mutex::new(Vec::new()));
    let engine = create_engine(executions.clone());

    let mut tasks = HashMap::new();
    tasks.insert(
        "decision".to_string(),
        TaskDefinition::new("decision", "Decision").with_action("route_small"),
    );
    tasks.insert(
        "small_task".to_string(),
        TaskDefinition::new("small_task", "Small Task").with_action("recording"),
    );
    tasks.insert(
        "large_task".to_string(),
        TaskDefinition::new("large_task", "Large Task").with_action("recording"),
    );

    let definition = ProcessDefinition::new("wcp04", "Exclusive Choice Pattern", "decision", tasks)
        .with_routings(vec![
            RoutingDefinition::new("r1", "decision", "small_task")
                .with_condition("route_name")
                .with_name("small"),
            RoutingDefinition::new("r2", "decision", "large_task")
                .with_condition("route_name")
                .with_name("large"),
        ]);

    let process = engine
        .create_process(definition, None, None, None)
        .await
        .unwrap();
    engine.start_process(&process.id).await.unwrap();

    let execs = executions.lock().unwrap();
    // Only one branch should execute
    assert!(execs.contains(&"decision".to_string()));
    assert!(execs.contains(&"small_task".to_string()));
    assert!(!execs.contains(&"large_task".to_string()));
}

/// WCP-5: Simple Merge (XOR-join)
/// Multiple branches converge without synchronization; each activation passes through.
#[tokio::test]
async fn test_wcp05_simple_merge() {
    let executions = Arc::new(Mutex::new(Vec::new()));
    let engine = create_engine(executions.clone());

    let mut tasks = HashMap::new();
    tasks.insert(
        "decision".to_string(),
        TaskDefinition::new("decision", "Decision").with_action("route_small"),
    );
    tasks.insert(
        "branch_a".to_string(),
        TaskDefinition::new("branch_a", "Branch A").with_action("recording"),
    );
    tasks.insert(
        "branch_b".to_string(),
        TaskDefinition::new("branch_b", "Branch B").with_action("recording"),
    );
    tasks.insert(
        "merge".to_string(),
        TaskDefinition::new("merge", "Merge").with_action("recording"),
    );

    let definition = ProcessDefinition::new("wcp05", "Simple Merge Pattern", "decision", tasks)
        .with_routings(vec![
            RoutingDefinition::new("r1", "decision", "branch_a")
                .with_condition("route_name")
                .with_name("small"),
            RoutingDefinition::new("r2", "decision", "branch_b")
                .with_condition("route_name")
                .with_name("large"),
            RoutingDefinition::new("r3", "branch_a", "merge"),
            RoutingDefinition::new("r4", "branch_b", "merge"),
        ]);

    let process = engine
        .create_process(definition, None, None, None)
        .await
        .unwrap();
    engine.start_process(&process.id).await.unwrap();

    let execs = executions.lock().unwrap();
    // Merge should execute after one of the branches
    assert_eq!(execs.last().unwrap(), "merge");
    assert!(execs.contains(&"branch_a".to_string()) || execs.contains(&"branch_b".to_string()));
}

// ============================================================================
// Advanced Branching and Synchronization Patterns (WCP-6 through WCP-8)
// ============================================================================

/// WCP-6: Multi-Choice (OR-split) - Partial Support
/// One or more branches are activated based on conditions.
/// Note: This demonstrates the limitation - all parallel branches execute.
#[tokio::test]
async fn test_wcp06_multi_choice_partial() {
    let executions = Arc::new(Mutex::new(Vec::new()));
    let engine = create_engine(executions.clone());

    let mut tasks = HashMap::new();
    tasks.insert(
        "decision".to_string(),
        TaskDefinition::new("decision", "Decision").with_action("recording"),
    );
    tasks.insert(
        "branch_a".to_string(),
        TaskDefinition::new("branch_a", "Branch A").with_action("recording"),
    );
    tasks.insert(
        "branch_b".to_string(),
        TaskDefinition::new("branch_b", "Branch B").with_action("recording"),
    );
    tasks.insert(
        "branch_c".to_string(),
        TaskDefinition::new("branch_c", "Branch C").with_action("recording"),
    );

    let definition = ProcessDefinition::new("wcp06", "Multi-Choice Pattern", "decision", tasks)
        .with_routings(vec![
            RoutingDefinition::new("r1", "decision", "branch_a").with_parallel(true),
            RoutingDefinition::new("r2", "decision", "branch_b").with_parallel(true),
            RoutingDefinition::new("r3", "decision", "branch_c").with_parallel(true),
        ]);

    let process = engine
        .create_process(definition, None, None, None)
        .await
        .unwrap();
    engine.start_process(&process.id).await.unwrap();

    let execs = executions.lock().unwrap();
    // All branches execute (limitation: cannot selectively activate subset)
    let exec_set: std::collections::HashSet<_> = execs.iter().collect();
    assert!(exec_set.contains(&"decision".to_string()));
    assert!(exec_set.contains(&"branch_a".to_string()));
    assert!(exec_set.contains(&"branch_b".to_string()));
    assert!(exec_set.contains(&"branch_c".to_string()));
}

/// WCP-7: Structured Synchronizing Merge
/// Merges branches from a Multi-Choice, synchronizing active branches.
#[tokio::test]
async fn test_wcp07_structured_synchronizing_merge() {
    let executions = Arc::new(Mutex::new(Vec::new()));
    let engine = create_engine(executions.clone());

    let mut tasks = HashMap::new();
    tasks.insert(
        "split".to_string(),
        TaskDefinition::new("split", "Split").with_action("recording"),
    );
    tasks.insert(
        "branch_a".to_string(),
        TaskDefinition::new("branch_a", "Branch A").with_action("recording"),
    );
    tasks.insert(
        "branch_b".to_string(),
        TaskDefinition::new("branch_b", "Branch B").with_action("recording"),
    );
    tasks.insert(
        "merge".to_string(),
        TaskDefinition::new("merge", "Merge")
            .with_synchronized(true)
            .with_action("recording"),
    );

    let definition =
        ProcessDefinition::new("wcp07", "Structured Synchronizing Merge", "split", tasks)
            .with_routings(vec![
                RoutingDefinition::new("r1", "split", "branch_a").with_parallel(true),
                RoutingDefinition::new("r2", "split", "branch_b").with_parallel(true),
                RoutingDefinition::new("r3", "branch_a", "merge"),
                RoutingDefinition::new("r4", "branch_b", "merge"),
            ]);

    let process = engine
        .create_process(definition, None, None, None)
        .await
        .unwrap();
    engine.start_process(&process.id).await.unwrap();

    let execs = executions.lock().unwrap();
    // Merge waits for all branches
    assert_eq!(execs.last().unwrap(), "merge");
    assert!(execs.contains(&"branch_a".to_string()));
    assert!(execs.contains(&"branch_b".to_string()));
}

// ============================================================================
// Termination Patterns (WCP-11)
// ============================================================================

/// WCP-11: Implicit Termination
/// Process terminates when no more work can be done.
#[tokio::test]
async fn test_wcp11_implicit_termination() {
    let executions = Arc::new(Mutex::new(Vec::new()));
    let engine = create_engine(executions.clone());

    let mut tasks = HashMap::new();
    tasks.insert(
        "start".to_string(),
        TaskDefinition::new("start", "Start").with_action("recording"),
    );
    tasks.insert(
        "branch_a".to_string(),
        TaskDefinition::new("branch_a", "Branch A").with_action("recording"),
    );
    tasks.insert(
        "branch_b".to_string(),
        TaskDefinition::new("branch_b", "Branch B").with_action("recording"),
    );
    // No explicit end task - process ends when all tasks complete

    let definition =
        ProcessDefinition::new("wcp11", "Implicit Termination Pattern", "start", tasks)
            .with_routings(vec![
                RoutingDefinition::new("r1", "start", "branch_a").with_parallel(true),
                RoutingDefinition::new("r2", "start", "branch_b").with_parallel(true),
            ]);

    let process = engine
        .create_process(definition, None, None, None)
        .await
        .unwrap();
    let result = engine.start_process(&process.id).await.unwrap();

    // Process should complete when all branches finish
    assert_eq!(result.state, ProcessState::Complete);
    let execs = executions.lock().unwrap();
    assert_eq!(execs.len(), 3); // start, branch_a, branch_b
}

// ============================================================================
// Multiple Instance Patterns (WCP-12 - Partial Support)
// ============================================================================

/// WCP-12: Multiple Instances without Synchronization
/// Demonstrates how multiple instances can be created via parallel branches.
/// Note: This is a workaround, not a dedicated multiple-instance construct.
#[tokio::test]
async fn test_wcp12_multiple_instances_via_parallel() {
    let executions = Arc::new(Mutex::new(Vec::new()));
    let engine = create_engine(executions.clone());

    let mut tasks = HashMap::new();
    tasks.insert(
        "start".to_string(),
        TaskDefinition::new("start", "Start").with_action("recording"),
    );
    tasks.insert(
        "instance_1".to_string(),
        TaskDefinition::new("instance_1", "Instance 1").with_action("recording"),
    );
    tasks.insert(
        "instance_2".to_string(),
        TaskDefinition::new("instance_2", "Instance 2").with_action("recording"),
    );
    tasks.insert(
        "instance_3".to_string(),
        TaskDefinition::new("instance_3", "Instance 3").with_action("recording"),
    );

    let definition =
        ProcessDefinition::new("wcp12", "Multiple Instances Pattern", "start", tasks)
            .with_routings(vec![
                RoutingDefinition::new("r1", "start", "instance_1").with_parallel(true),
                RoutingDefinition::new("r2", "start", "instance_2").with_parallel(true),
                RoutingDefinition::new("r3", "start", "instance_3").with_parallel(true),
            ]);

    let process = engine
        .create_process(definition, None, None, None)
        .await
        .unwrap();
    let result = engine.start_process(&process.id).await.unwrap();

    assert_eq!(result.state, ProcessState::Complete);
    let execs = executions.lock().unwrap();
    // All instances should execute
    assert!(execs.contains(&"instance_1".to_string()));
    assert!(execs.contains(&"instance_2".to_string()));
    assert!(execs.contains(&"instance_3".to_string()));
}

// ============================================================================
// Complex Pattern: Split-Join with Multiple Branches
// ============================================================================

/// Test a more complex workflow with multiple parallel branches and synchronization.
#[tokio::test]
async fn test_complex_split_join() {
    let executions = Arc::new(Mutex::new(Vec::new()));
    let engine = create_engine(executions.clone());

    let mut tasks = HashMap::new();
    tasks.insert(
        "start".to_string(),
        TaskDefinition::new("start", "Start").with_action("recording"),
    );
    for i in 1..=5 {
        tasks.insert(
            format!("branch_{}", i),
            TaskDefinition::new(&format!("branch_{}", i), &format!("Branch {}", i))
                .with_action("recording"),
        );
    }
    tasks.insert(
        "join".to_string(),
        TaskDefinition::new("join", "Join")
            .with_synchronized(true)
            .with_action("recording"),
    );
    tasks.insert(
        "end".to_string(),
        TaskDefinition::new("end", "End").with_action("recording"),
    );

    let mut routings = Vec::new();
    for i in 1..=5 {
        routings.push(
            RoutingDefinition::new(&format!("r_split_{}", i), "start", &format!("branch_{}", i))
                .with_parallel(true),
        );
        routings.push(RoutingDefinition::new(
            &format!("r_join_{}", i),
            &format!("branch_{}", i),
            "join",
        ));
    }
    routings.push(RoutingDefinition::new("r_end", "join", "end"));

    let definition = ProcessDefinition::new("complex", "Complex Split-Join", "start", tasks)
        .with_routings(routings);

    let process = engine
        .create_process(definition, None, None, None)
        .await
        .unwrap();
    let result = engine.start_process(&process.id).await.unwrap();

    assert_eq!(result.state, ProcessState::Complete);
    let execs = executions.lock().unwrap();

    // Verify execution order
    assert_eq!(execs[0], "start");
    assert_eq!(execs[execs.len() - 2], "join");
    assert_eq!(execs[execs.len() - 1], "end");

    // All branches should have executed
    for i in 1..=5 {
        assert!(execs.contains(&format!("branch_{}", i)));
    }
}
