//! YAML/JSON workflow definition loader.
//!
//! This module provides functions for loading workflow definitions from
//! YAML or JSON files into ProcessDefinition objects.

use std::collections::HashMap;
use std::path::Path;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::core::errors::{DefinitionError, DefinitionResult};
use crate::core::models::{ProcessDefinition, RoutingDefinition, TaskDefinition};

/// Raw definition format as parsed from YAML/JSON.
#[derive(Debug, Clone, Serialize, Deserialize)]
struct RawDefinition {
    name: String,
    #[serde(default = "default_version")]
    version: i32,
    #[serde(default)]
    first_task: Option<String>,
    tasks: HashMap<String, RawTaskDefinition>,
    #[serde(default)]
    routings: Vec<RawRoutingDefinition>,
    #[serde(default)]
    construct_action: Option<String>,
    #[serde(default)]
    destruct_action: Option<String>,
    #[serde(default)]
    properties: HashMap<String, serde_json::Value>,
}

fn default_version() -> i32 {
    1
}

/// Raw task definition that supports both full and shorthand formats.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
enum RawTaskDefinition {
    /// Shorthand: just a name string
    Shorthand(String),
    /// Full definition with all fields
    Full {
        #[serde(default)]
        name: Option<String>,
        #[serde(default = "default_true")]
        auto: bool,
        #[serde(default)]
        synchronized: bool,
        #[serde(default)]
        action: Option<String>,
        #[serde(default)]
        construct_action: Option<String>,
        #[serde(default)]
        destruct_action: Option<String>,
        #[serde(default)]
        properties: HashMap<String, serde_json::Value>,
    },
}

fn default_true() -> bool {
    true
}

/// Raw routing definition.
#[derive(Debug, Clone, Serialize, Deserialize)]
struct RawRoutingDefinition {
    from: String,
    to: String,
    #[serde(default)]
    parallel: bool,
    #[serde(default)]
    condition: Option<String>,
    #[serde(default)]
    name: Option<String>,
}

/// Load a workflow definition from a file.
///
/// Supports both YAML (.yaml, .yml) and JSON (.json) formats.
pub fn load_definition(path: impl AsRef<Path>) -> DefinitionResult<ProcessDefinition> {
    let path = path.as_ref();

    let content = std::fs::read_to_string(path).map_err(|e| {
        DefinitionError::Parse(format!("Failed to read file '{}': {}", path.display(), e))
    })?;

    let extension = path.extension().and_then(|e| e.to_str()).unwrap_or("");

    match extension {
        "yaml" | "yml" => load_definition_from_yaml(&content, &path.display().to_string()),
        "json" => load_definition_from_json(&content, &path.display().to_string()),
        _ => {
            // Try YAML first, then JSON
            load_definition_from_yaml(&content, &path.display().to_string())
                .or_else(|_| load_definition_from_json(&content, &path.display().to_string()))
        }
    }
}

/// Load a workflow definition from a YAML string.
pub fn load_definition_from_yaml(
    yaml_content: &str,
    source: &str,
) -> DefinitionResult<ProcessDefinition> {
    let raw: RawDefinition = serde_yaml::from_str(yaml_content)
        .map_err(|e| DefinitionError::Parse(format!("Failed to parse YAML from {}: {}", source, e)))?;

    load_definition_from_raw(raw, source)
}

/// Load a workflow definition from a JSON string.
pub fn load_definition_from_json(
    json_content: &str,
    source: &str,
) -> DefinitionResult<ProcessDefinition> {
    let raw: RawDefinition = serde_json::from_str(json_content)
        .map_err(|e| DefinitionError::Parse(format!("Failed to parse JSON from {}: {}", source, e)))?;

    load_definition_from_raw(raw, source)
}

/// Load a workflow definition from a raw parsed structure.
fn load_definition_from_raw(raw: RawDefinition, source: &str) -> DefinitionResult<ProcessDefinition> {
    let mut errors: Vec<String> = Vec::new();

    // Generate ID from name and version
    let definition_id = generate_id(&raw.name, raw.version);

    // Parse tasks
    let mut tasks: HashMap<String, TaskDefinition> = HashMap::new();

    for (task_id, raw_task) in raw.tasks {
        let task_def = match raw_task {
            RawTaskDefinition::Shorthand(name) => TaskDefinition::new(&task_id, name),
            RawTaskDefinition::Full {
                name,
                auto,
                synchronized,
                action,
                construct_action,
                destruct_action,
                properties,
            } => {
                let mut task = TaskDefinition::new(&task_id, name.unwrap_or_else(|| task_id.clone()));
                task.auto = auto;
                task.synchronized = synchronized;
                task.action = action;
                task.construct_action = construct_action;
                task.destruct_action = destruct_action;
                task.properties = properties;
                task
            }
        };
        tasks.insert(task_id, task_def);
    }

    if tasks.is_empty() {
        errors.push("At least one task is required".to_string());
    }

    // Parse routings
    let mut routings: Vec<RoutingDefinition> = Vec::new();

    for (i, raw_routing) in raw.routings.into_iter().enumerate() {
        if !tasks.contains_key(&raw_routing.from) {
            errors.push(format!(
                "Routing {}: source task '{}' not found",
                i, raw_routing.from
            ));
        }
        if !tasks.contains_key(&raw_routing.to) {
            errors.push(format!(
                "Routing {}: destination task '{}' not found",
                i, raw_routing.to
            ));
        }

        let routing_id = format!("{}_to_{}_{}", raw_routing.from, raw_routing.to, i);

        let mut routing = RoutingDefinition::new(&routing_id, &raw_routing.from, &raw_routing.to);
        routing.parallel = raw_routing.parallel;
        routing.condition = raw_routing.condition;
        routing.name = raw_routing.name;

        routings.push(routing);
    }

    // Determine first task
    let first_task_id = raw.first_task.unwrap_or_else(|| {
        tasks.keys().next().cloned().unwrap_or_default()
    });

    if !first_task_id.is_empty() && !tasks.contains_key(&first_task_id) {
        errors.push(format!("First task '{}' not found in tasks", first_task_id));
    }

    if !errors.is_empty() {
        return Err(DefinitionError::Validation(format!(
            "Invalid definition from {}: {}",
            source,
            errors.join("; ")
        )));
    }

    let mut definition = ProcessDefinition::new(definition_id, raw.name, first_task_id, tasks);
    definition.version = raw.version;
    definition.routings = routings;
    definition.construct_action = raw.construct_action;
    definition.destruct_action = raw.destruct_action;
    definition.properties = raw.properties;

    Ok(definition)
}

/// Validate a process definition for common issues.
///
/// Checks:
/// - All routing references exist
/// - First task exists
/// - No orphaned tasks (tasks with no incoming routes except first)
/// - Sync tasks have incoming routes
pub fn validate_definition(definition: &ProcessDefinition) -> Vec<String> {
    let mut errors: Vec<String> = Vec::new();

    // Check first task exists
    if !definition.tasks.contains_key(&definition.first_task_id) {
        errors.push(format!(
            "First task '{}' not found",
            definition.first_task_id
        ));
    }

    // Check routing references
    for routing in &definition.routings {
        if !definition.tasks.contains_key(&routing.source_task_id) {
            errors.push(format!(
                "Routing source '{}' not found",
                routing.source_task_id
            ));
        }
        if !definition.tasks.contains_key(&routing.dest_task_id) {
            errors.push(format!(
                "Routing destination '{}' not found",
                routing.dest_task_id
            ));
        }
    }

    // Check for orphaned tasks
    let mut tasks_with_incoming: std::collections::HashSet<&str> =
        std::collections::HashSet::new();
    tasks_with_incoming.insert(&definition.first_task_id);

    for routing in &definition.routings {
        tasks_with_incoming.insert(&routing.dest_task_id);
    }

    for task_id in definition.tasks.keys() {
        if !tasks_with_incoming.contains(task_id.as_str()) {
            errors.push(format!(
                "Task '{}' has no incoming routes and is not the first task",
                task_id
            ));
        }
    }

    // Check sync tasks have multiple incoming routes
    for (task_id, task_def) in &definition.tasks {
        if task_def.synchronized {
            let incoming = definition.get_routings_to(task_id);
            if incoming.len() < 2 {
                errors.push(format!(
                    "Synchronized task '{}' should have multiple incoming routes",
                    task_id
                ));
            }
        }
    }

    errors
}

/// Generate a unique ID from name and version.
fn generate_id(name: &str, version: i32) -> String {
    let content = format!("{}:{}", name, version);
    let mut hasher = Sha256::new();
    hasher.update(content.as_bytes());
    let result = hasher.finalize();
    hex::encode(&result[..8])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_load_definition_from_yaml() {
        let yaml = r#"
name: Test Workflow
version: 1

tasks:
  start:
    name: Start Task
    action: shell
  end:
    name: End Task

routings:
  - from: start
    to: end
"#;

        let def = load_definition_from_yaml(yaml, "test").unwrap();
        assert_eq!(def.name, "Test Workflow");
        assert_eq!(def.version, 1);
        assert_eq!(def.tasks.len(), 2);
        assert_eq!(def.routings.len(), 1);
    }

    #[test]
    fn test_load_definition_shorthand_tasks() {
        let yaml = r#"
name: Simple Workflow
tasks:
  task1: "First Task"
  task2: "Second Task"
routings:
  - from: task1
    to: task2
"#;

        let def = load_definition_from_yaml(yaml, "test").unwrap();
        assert_eq!(def.tasks.get("task1").unwrap().name, "First Task");
        assert_eq!(def.tasks.get("task2").unwrap().name, "Second Task");
    }

    #[test]
    fn test_load_definition_validation_error() {
        let yaml = r#"
name: Invalid Workflow
tasks:
  task1:
    name: Task 1
routings:
  - from: task1
    to: nonexistent
"#;

        let result = load_definition_from_yaml(yaml, "test");
        assert!(result.is_err());
        let err = result.unwrap_err().to_string();
        assert!(err.contains("nonexistent"));
    }

    #[test]
    fn test_validate_definition_orphaned_task() {
        let mut tasks = HashMap::new();
        tasks.insert("start".to_string(), TaskDefinition::new("start", "Start"));
        tasks.insert("orphan".to_string(), TaskDefinition::new("orphan", "Orphan"));
        tasks.insert("end".to_string(), TaskDefinition::new("end", "End"));

        let def = ProcessDefinition::new("test", "Test", "start", tasks).with_routings(vec![
            RoutingDefinition::new("r1", "start", "end"),
        ]);

        let errors = validate_definition(&def);
        assert!(!errors.is_empty());
        assert!(errors.iter().any(|e| e.contains("orphan")));
    }

    #[test]
    fn test_validate_definition_sync_task_warning() {
        let mut tasks = HashMap::new();
        tasks.insert("start".to_string(), TaskDefinition::new("start", "Start"));
        tasks.insert(
            "sync".to_string(),
            TaskDefinition::new("sync", "Sync").with_synchronized(true),
        );

        let def = ProcessDefinition::new("test", "Test", "start", tasks).with_routings(vec![
            RoutingDefinition::new("r1", "start", "sync"),
        ]);

        let errors = validate_definition(&def);
        assert!(!errors.is_empty());
        assert!(errors.iter().any(|e| e.contains("Synchronized")));
    }

    #[test]
    fn test_generate_id() {
        let id1 = generate_id("Test", 1);
        let id2 = generate_id("Test", 2);
        let id3 = generate_id("Test", 1);

        assert_ne!(id1, id2);
        assert_eq!(id1, id3);
        assert_eq!(id1.len(), 16); // 8 bytes = 16 hex chars
    }
}
