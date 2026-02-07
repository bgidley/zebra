"""Custom exceptions for the Zebra workflow engine."""


class ZebraError(Exception):
    """Base exception for all Zebra workflow errors."""

    pass


class DefinitionError(ZebraError):
    """Error related to workflow definitions."""

    pass


class DefinitionNotFoundError(DefinitionError):
    """Raised when a referenced definition cannot be found."""

    pass


class ValidationError(DefinitionError):
    """Raised when a definition fails validation."""

    pass


class StateError(ZebraError):
    """Error related to workflow state management."""

    pass


class ProcessNotFoundError(StateError):
    """Raised when a process instance cannot be found."""

    pass


class TaskNotFoundError(StateError):
    """Raised when a task instance cannot be found."""

    pass


class InvalidStateTransitionError(StateError):
    """Raised when an invalid state transition is attempted."""

    pass


class LockError(StateError):
    """Raised when a lock cannot be acquired on a process."""

    pass


class ExecutionError(ZebraError):
    """Error during workflow execution."""

    pass


class TaskExecutionError(ExecutionError):
    """Error during task execution."""

    pass


class RoutingError(ExecutionError):
    """Error during routing evaluation."""

    pass


class ActionError(ExecutionError):
    """Error related to task/condition actions."""

    pass


class ActionNotFoundError(ActionError):
    """Raised when a referenced action is not registered."""

    pass


class SerializationError(StateError):
    """Raised when properties or data cannot be serialized for storage.

    Properties on processes and tasks must be JSON-serializable (strings,
    numbers, booleans, lists, dicts, and None). This error is raised when
    a non-serializable value is detected during persistence.
    """

    pass
