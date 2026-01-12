//! Custom error types for the Zebra workflow engine.

use thiserror::Error;

/// Base error type for all Zebra workflow errors.
#[derive(Error, Debug)]
pub enum ZebraError {
    /// Error related to workflow definitions
    #[error(transparent)]
    Definition(#[from] DefinitionError),

    /// Error related to workflow state management
    #[error(transparent)]
    State(#[from] StateError),

    /// Error during workflow execution
    #[error(transparent)]
    Execution(#[from] ExecutionError),

    /// Storage-related error
    #[error("Storage error: {0}")]
    Storage(String),

    /// Generic error
    #[error("{0}")]
    Other(String),
}

/// Error related to workflow definitions.
#[derive(Error, Debug)]
pub enum DefinitionError {
    /// Raised when a referenced definition cannot be found
    #[error("Definition not found: {0}")]
    NotFound(String),

    /// Raised when a definition fails validation
    #[error("Validation error: {0}")]
    Validation(String),

    /// Error parsing definition file
    #[error("Parse error: {0}")]
    Parse(String),
}

/// Error related to workflow state management.
#[derive(Error, Debug)]
pub enum StateError {
    /// Raised when a process instance cannot be found
    #[error("Process not found: {0}")]
    ProcessNotFound(String),

    /// Raised when a task instance cannot be found
    #[error("Task not found: {0}")]
    TaskNotFound(String),

    /// Raised when an invalid state transition is attempted
    #[error("Invalid state transition: {0}")]
    InvalidStateTransition(String),

    /// Raised when a lock cannot be acquired on a process
    #[error("Lock error: {0}")]
    Lock(String),
}

/// Error during workflow execution.
#[derive(Error, Debug)]
pub enum ExecutionError {
    /// Error during task execution
    #[error("Task execution error: {0}")]
    TaskExecution(String),

    /// Error during routing evaluation
    #[error("Routing error: {0}")]
    Routing(String),

    /// Action not found error
    #[error("Action not found: {0}")]
    ActionNotFound(String),

    /// Condition not found error
    #[error("Condition not found: {0}")]
    ConditionNotFound(String),

    /// Generic action error
    #[error("Action error: {0}")]
    Action(String),
}

/// Result type alias for Zebra operations
pub type Result<T> = std::result::Result<T, ZebraError>;

/// Result type alias for definition operations
pub type DefinitionResult<T> = std::result::Result<T, DefinitionError>;

/// Result type alias for state operations
pub type StateResult<T> = std::result::Result<T, StateError>;

/// Result type alias for execution operations
pub type ExecutionResult<T> = std::result::Result<T, ExecutionError>;

impl From<String> for ZebraError {
    fn from(s: String) -> Self {
        ZebraError::Other(s)
    }
}

impl From<&str> for ZebraError {
    fn from(s: &str) -> Self {
        ZebraError::Other(s.to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_error_display() {
        let err = DefinitionError::NotFound("test-def".to_string());
        assert_eq!(err.to_string(), "Definition not found: test-def");

        let err = StateError::ProcessNotFound("proc-123".to_string());
        assert_eq!(err.to_string(), "Process not found: proc-123");

        let err = ExecutionError::ActionNotFound("my_action".to_string());
        assert_eq!(err.to_string(), "Action not found: my_action");
    }

    #[test]
    fn test_error_conversion() {
        let def_err = DefinitionError::NotFound("test".to_string());
        let zebra_err: ZebraError = def_err.into();
        assert!(matches!(zebra_err, ZebraError::Definition(_)));
    }
}
