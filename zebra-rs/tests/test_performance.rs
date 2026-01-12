//! Performance tests for the Zebra workflow engine.

use std::collections::HashMap;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Instant;

use async_trait::async_trait;
use serde_json::json;
use tokio::task::JoinSet;

use zebra::core::errors::ExecutionResult;
use zebra::core::models::{
    ProcessDefinition, RoutingDefinition, TaskDefinition, TaskInstance, TaskResult,
};
use zebra::core::WorkflowEngine;
use zebra::storage::InMemoryStore;
use zebra::tasks::{ActionRegistry, ExecutionContext, TaskAction};
use zebra::StateStore;

/// A lightweight action for performance testing.
struct PerfAction;

#[async_trait]
impl TaskAction<InMemoryStore> for PerfAction {
    async fn run(
        &self,
        _task: &TaskInstance,
        _context: &ExecutionContext<InMemoryStore>,
    ) -> ExecutionResult<TaskResult> {
        // Simulate minimal work
        Ok(TaskResult::ok_with_output(json!({"status": "done"})))
    }
}

/// Create a workflow definition with a configurable number of sequential tasks.
fn create_sequential_workflow(num_tasks: usize) -> ProcessDefinition {
    let mut tasks = HashMap::new();
    let mut routings = Vec::new();

    for i in 0..num_tasks {
        let task_id = format!("task_{}", i);
        tasks.insert(
            task_id.clone(),
            TaskDefinition::new(&task_id, format!("Task {}", i)).with_action("perf"),
        );

        if i > 0 {
            let prev_task_id = format!("task_{}", i - 1);
            routings.push(RoutingDefinition::new(
                format!("r_{}", i),
                &prev_task_id,
                &task_id,
            ));
        }
    }

    ProcessDefinition::new("perf_sequential", "Performance Sequential", "task_0", tasks)
        .with_routings(routings)
}

/// Create a workflow with parallel branches that join.
fn create_parallel_workflow(num_branches: usize) -> ProcessDefinition {
    let mut tasks = HashMap::new();
    let mut routings = Vec::new();

    // Start task
    tasks.insert(
        "start".to_string(),
        TaskDefinition::new("start", "Start").with_action("perf"),
    );

    // Parallel branches
    for i in 0..num_branches {
        let branch_id = format!("branch_{}", i);
        tasks.insert(
            branch_id.clone(),
            TaskDefinition::new(&branch_id, format!("Branch {}", i)).with_action("perf"),
        );
        routings.push(
            RoutingDefinition::new(format!("r_start_{}", i), "start", &branch_id).with_parallel(true),
        );
        routings.push(RoutingDefinition::new(
            format!("r_join_{}", i),
            &branch_id,
            "join",
        ));
    }

    // Join task
    tasks.insert(
        "join".to_string(),
        TaskDefinition::new("join", "Join")
            .with_synchronized(true)
            .with_action("perf"),
    );

    // End task
    tasks.insert(
        "end".to_string(),
        TaskDefinition::new("end", "End").with_action("perf"),
    );
    routings.push(RoutingDefinition::new("r_end", "join", "end"));

    ProcessDefinition::new("perf_parallel", "Performance Parallel", "start", tasks)
        .with_routings(routings)
}

fn create_engine() -> Arc<WorkflowEngine<InMemoryStore>> {
    let store = Arc::new(InMemoryStore::new());
    let mut registry = ActionRegistry::new();
    registry.register_action("perf", || Arc::new(PerfAction));

    Arc::new(WorkflowEngine::new(store, Arc::new(registry)))
}

#[tokio::test]
async fn perf_100_parallel_workflows_sequential_tasks() {
    const NUM_WORKFLOWS: usize = 100;
    const TASKS_PER_WORKFLOW: usize = 10;

    let engine = create_engine();
    let definition = create_sequential_workflow(TASKS_PER_WORKFLOW);

    // Pre-save the definition
    engine
        .store
        .save_definition(definition.clone())
        .await
        .unwrap();

    let start = Instant::now();
    let completed = Arc::new(AtomicUsize::new(0));

    // Spawn all workflows in parallel
    let mut join_set = JoinSet::new();

    for i in 0..NUM_WORKFLOWS {
        let engine = engine.clone();
        let definition = definition.clone();
        let completed = completed.clone();

        join_set.spawn(async move {
            let process = engine
                .create_process(definition, None, None, None)
                .await
                .expect(&format!("Failed to create process {}", i));

            engine
                .start_process(&process.id)
                .await
                .expect(&format!("Failed to start process {}", i));

            completed.fetch_add(1, Ordering::SeqCst);
        });
    }

    // Wait for all workflows to complete
    while let Some(result) = join_set.join_next().await {
        result.expect("Task panicked");
    }

    let elapsed = start.elapsed();
    let completed_count = completed.load(Ordering::SeqCst);

    println!("\n=== Performance Test: 100 Parallel Workflows (Sequential Tasks) ===");
    println!("Workflows completed: {}", completed_count);
    println!("Tasks per workflow: {}", TASKS_PER_WORKFLOW);
    println!("Total tasks executed: {}", completed_count * TASKS_PER_WORKFLOW);
    println!("Total time: {:.2?}", elapsed);
    println!(
        "Workflows per second: {:.2}",
        completed_count as f64 / elapsed.as_secs_f64()
    );
    println!(
        "Tasks per second: {:.2}",
        (completed_count * TASKS_PER_WORKFLOW) as f64 / elapsed.as_secs_f64()
    );
    println!("Average time per workflow: {:.2?}", elapsed / NUM_WORKFLOWS as u32);

    assert_eq!(completed_count, NUM_WORKFLOWS);
}

#[tokio::test]
async fn perf_100_parallel_workflows_with_branching() {
    const NUM_WORKFLOWS: usize = 100;
    const BRANCHES_PER_WORKFLOW: usize = 5;

    let engine = create_engine();
    let definition = create_parallel_workflow(BRANCHES_PER_WORKFLOW);

    // Pre-save the definition
    engine
        .store
        .save_definition(definition.clone())
        .await
        .unwrap();

    let start = Instant::now();
    let completed = Arc::new(AtomicUsize::new(0));

    // Spawn all workflows in parallel
    let mut join_set = JoinSet::new();

    for i in 0..NUM_WORKFLOWS {
        let engine = engine.clone();
        let definition = definition.clone();
        let completed = completed.clone();

        join_set.spawn(async move {
            let process = engine
                .create_process(definition, None, None, None)
                .await
                .expect(&format!("Failed to create process {}", i));

            engine
                .start_process(&process.id)
                .await
                .expect(&format!("Failed to start process {}", i));

            completed.fetch_add(1, Ordering::SeqCst);
        });
    }

    // Wait for all workflows to complete
    while let Some(result) = join_set.join_next().await {
        result.expect("Task panicked");
    }

    let elapsed = start.elapsed();
    let completed_count = completed.load(Ordering::SeqCst);
    // Tasks: start + branches + join + end = 1 + branches + 1 + 1 = branches + 3
    let tasks_per_workflow = BRANCHES_PER_WORKFLOW + 3;

    println!("\n=== Performance Test: 100 Parallel Workflows (With Branching) ===");
    println!("Workflows completed: {}", completed_count);
    println!("Branches per workflow: {}", BRANCHES_PER_WORKFLOW);
    println!("Tasks per workflow: {}", tasks_per_workflow);
    println!("Total tasks executed: {}", completed_count * tasks_per_workflow);
    println!("Total time: {:.2?}", elapsed);
    println!(
        "Workflows per second: {:.2}",
        completed_count as f64 / elapsed.as_secs_f64()
    );
    println!(
        "Tasks per second: {:.2}",
        (completed_count * tasks_per_workflow) as f64 / elapsed.as_secs_f64()
    );
    println!("Average time per workflow: {:.2?}", elapsed / NUM_WORKFLOWS as u32);

    assert_eq!(completed_count, NUM_WORKFLOWS);
}

#[tokio::test]
async fn perf_1000_workflows_quick() {
    const NUM_WORKFLOWS: usize = 1000;
    const TASKS_PER_WORKFLOW: usize = 5;

    let engine = create_engine();
    let definition = create_sequential_workflow(TASKS_PER_WORKFLOW);

    engine
        .store
        .save_definition(definition.clone())
        .await
        .unwrap();

    let start = Instant::now();
    let completed = Arc::new(AtomicUsize::new(0));

    let mut join_set = JoinSet::new();

    for i in 0..NUM_WORKFLOWS {
        let engine = engine.clone();
        let definition = definition.clone();
        let completed = completed.clone();

        join_set.spawn(async move {
            let process = engine
                .create_process(definition, None, None, None)
                .await
                .expect(&format!("Failed to create process {}", i));

            engine
                .start_process(&process.id)
                .await
                .expect(&format!("Failed to start process {}", i));

            completed.fetch_add(1, Ordering::SeqCst);
        });
    }

    while let Some(result) = join_set.join_next().await {
        result.expect("Task panicked");
    }

    let elapsed = start.elapsed();
    let completed_count = completed.load(Ordering::SeqCst);

    println!("\n=== Performance Test: 1000 Workflows (Quick) ===");
    println!("Workflows completed: {}", completed_count);
    println!("Tasks per workflow: {}", TASKS_PER_WORKFLOW);
    println!("Total tasks executed: {}", completed_count * TASKS_PER_WORKFLOW);
    println!("Total time: {:.2?}", elapsed);
    println!(
        "Workflows per second: {:.2}",
        completed_count as f64 / elapsed.as_secs_f64()
    );
    println!(
        "Tasks per second: {:.2}",
        (completed_count * TASKS_PER_WORKFLOW) as f64 / elapsed.as_secs_f64()
    );

    assert_eq!(completed_count, NUM_WORKFLOWS);
}
