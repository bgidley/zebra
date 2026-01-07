# Zebra Workflow Engine - Design Summary

## Overview

**Zebra** is a lightweight, Java-based workflow engine originally developed by Anite (Central Government Division) in 2004, with significant modifications by Ben Gidley in 2010. It provides a robust framework for executing business process workflows with support for complex execution patterns including sequential processing, parallel execution, synchronization points, and conditional routing.

## Project Purpose

Zebra enables organizations to:
- Define and execute business process workflows
- Handle both automated and manual task processing
- Support parallel task execution with synchronization
- Apply conditional routing logic for dynamic workflow paths
- Persist workflow state across different storage backends
- Track audit trails and execution history

## Architecture

### High-Level Architecture

Zebra follows a **layered architecture** with clear separation between workflow definition, execution engine, and persistence:

```
┌─────────────────────────────────────┐
│     Workflow Definitions (XML)      │
│         Process Templates           │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│  Definition Loaders & Factories     │
│   (zebra-process-definition-loader) │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│      Core Engine (zebra-core)       │
│  - Workflow execution controller    │
│  - Task/Process lifecycle           │
│  - Routing & Synchronization        │
│  - State machine management         │
└─────────────────────────────────────┘
                 ↓
┌─────────────────────────────────────┐
│  State Factory (Persistence Layer)  │
│  - IStateFactory interface          │
│  - Hibernate/JPA (zebra-service)    │
│  - In-Memory (zebra-inmemory)       │
└─────────────────────────────────────┘
```

### Module Structure

The project is organized as a **multi-module Maven build** with clear responsibilities:

| Module | Purpose |
|--------|---------|
| **zebra-core** | Core workflow engine containing interfaces and implementation |
| **zebra-service** | Persistence layer with Hibernate/JPA entity mappings |
| **zebra-inmemory** | In-memory implementation for testing without database |
| **zebra-process-definition-loader** | Loads workflow definitions into engine |
| **zebra-xmlloader** | XML-based process definition loader (legacy) |
| **zebra-hivemind** | HiveMind IoC container integration (legacy) |
| **zebra-defs** | Additional definitions |

Legacy code from the original CVS repository is preserved in the `import` folder.

## Core Components

### 1. Engine Layer (zebra-core)

#### Engine (`com.anite.zebra.core.Engine`)
The main workflow execution controller implementing the `IEngine` interface:

**Key Responsibilities:**
- Process creation and lifecycle management
- Task state transitions and execution
- Routing evaluation (serial vs parallel)
- Synchronization point handling
- Process instance locking for concurrency safety
- Flow of Execution (FOE) management

**Primary Operations:**
- `createProcess()` - Instantiate a workflow from a definition
- `startProcess()` - Begin workflow execution
- `transitionTask()` - Move a task through its lifecycle

#### Core Interfaces

**Workflow Execution:**
- `IEngine` - Main engine interface
- `ITaskAction` - Implemented by custom task logic classes
- `IConditionAction` - Implements routing conditions
- `IProcessConstruct/IProcessDestruct` - Process lifecycle hooks
- `ITaskConstruct/ITaskDestruct` - Task lifecycle hooks

**State Model:**
- `IProcessInstance` - Running process instance
- `ITaskInstance` - Running task instance
- `IFOE` - Flow of Execution tracking for parallel branches

**Definition Model:**
- `IProcessDefinition` - Workflow template
- `ITaskDefinition` - Task template with properties
- `IRoutingDefinition` - Connections between tasks

### 2. State Management

#### Process States
A process instance progresses through these states:
- **CREATED** - Initial state after instantiation
- **INITIALISING** - Running process construct hooks
- **RUNNING** - Active execution
- **COMPLETING** - Running process destruct hooks
- **COMPLETE** - Terminal state

#### Task States
Tasks have a more complex lifecycle:
- **AWAITINGSYNC** - Waiting for parallel paths to converge
- **AWAITINGINITIALISATION** - Queued for initialization
- **INITIALISING** - Running task construct hooks
- **READY** - Ready to execute (manual tasks wait here)
- **RUNNING** - Executing task action
- **AWAITINGCOMPLETE** - Execution finished, awaiting completion
- **COMPLETING** - Running task destruct hooks
- **COMPLETE** - Terminal state
- **ERRORROUTING** - Routing evaluation failed

### 3. Persistence Layer (zebra-service)

#### JPA Entity Model
The persistence layer uses Hibernate with JPA annotations:

**Core Entities:**
- `ProcessInstance` - Workflow instance with property sets and history
- `TaskInstance` - Task instance with property sets
- `FOE` - Flow of Execution entity for parallel tracking
- `ProcessDefinition`, `TaskDefinition`, `RoutingDefinition` - Definition entities
- `PropertySetEntry` - Flexible key-value storage for runtime data

#### IStateFactory Interface
Abstract persistence interface providing:
- Transaction management (`beginTransaction()`, `commit()`, `rollback()`)
- Object persistence (`saveObject()`, `deleteObject()`)
- Factory methods (`createProcessInstance()`, `createTaskInstance()`, `createFOE()`)
- Locking (`acquireLock()`, `releaseLock()`)

Multiple implementations available:
- **Hibernate/JPA** - Database-backed persistence (zebra-service)
- **In-Memory** - Transient storage for testing (zebra-inmemory)

### 4. Flow of Execution (FOE) Concept

FOE is a critical architectural concept for tracking execution paths through workflows:

**Purpose:**
- Tracks individual execution threads in parallel workflows
- Each FOE represents one path through split-join structures
- Enables audit trails showing how execution flowed
- Manages property inheritance in parallel branches

**Behavior:**
- **Serial routings** - Child task inherits parent FOE
- **Parallel routings** - Each target task gets a new FOE
- **Synchronization** - Multiple FOEs converge at join points

## Design Patterns

### Strategy Pattern
Task actions, condition actions, and lifecycle hooks are pluggable via interface implementations. Custom behavior is injected by specifying class names in workflow definitions.

### Abstract Factory Pattern
`IStateFactory` provides an abstraction for creating state objects, allowing different persistence implementations without modifying engine code.

### Template Method
The Engine contains the workflow execution algorithm with well-defined extension points where custom logic can be injected.

### State Pattern
Process and task instances maintain explicit state machines with well-defined transitions and validation rules.

### Dependency Injection
Apache Tapestry IoC manages component lifecycles and dependencies, promoting loose coupling.

## Key Architectural Decisions

### 1. Interface-Driven Design
The core engine depends only on interfaces (`IStateFactory`, `IProcessDefinition`, etc.), enabling multiple implementations without changing engine code. This promotes testability and extensibility.

### 2. Routing Model

**Serial Routing:**
- Conditional branching with ordered evaluation
- First matching condition wins
- Reuses parent FOE for continuity

**Parallel Routing:**
- All routings execute simultaneously (split/fork)
- Each branch creates a new FOE
- Used for concurrent task execution

### 3. Synchronization Strategy
Tasks can be marked as synchronized, requiring multiple incoming FOEs before execution. This enables join patterns where parallel branches reconverge.

### 4. Locking for Concurrency
Process instances are locked during transitions to prevent race conditions. The state factory manages lock acquisition and release, supporting multi-threaded environments.

### 5. Property Sets
Flexible key-value storage on processes and tasks allows workflow-specific data without schema changes. Properties are automatically disposed when workflows complete.

### 6. Subflow Support
Processes can spawn child processes with parent-child relationship tracking. This enables hierarchical workflow decomposition.

### 7. Audit Trail
Task history is preserved through `TaskInstanceHistory` entities, and FOE tracking provides complete execution path analysis.

## Technology Stack

**Core Technologies:**
- Java 1.5 (compiler target)
- Maven - Build and dependency management
- SLF4J + Logback - Logging framework
- Apache Commons Lang - Utility functions

**Persistence:**
- Hibernate 3.3.2 - ORM framework
- JPA Annotations - Entity mapping
- Hibernate Annotations 3.4.0

**Dependency Injection:**
- Apache Tapestry IoC 5.1.0.5 - Inversion of Control container

**Testing:**
- JUnit 3.8.1 - Unit testing
- TestNG 5.9 - Alternative testing framework
- Hamcrest - Matcher library for assertions

**XML Processing:**
- Custom XML loaders for workflow definitions (`.acgwfd.xml` files)

## Workflow Definition Format

Workflows are defined in XML with the following elements:
- Process definitions with unique names
- Task definitions with properties (auto-execution, synchronized, class names)
- Routing definitions connecting tasks (serial/parallel, with conditions)
- Class references for task actions, condition actions, and lifecycle hooks

## Usage Pattern

Typical workflow execution follows this pattern:

1. **Load Definition** - Parse XML workflow definition
2. **Create Process** - Instantiate process from definition via `IEngine.createProcess()`
3. **Start Process** - Begin execution via `IEngine.startProcess()`
4. **Execute Tasks** - Engine automatically processes auto tasks
5. **Manual Intervention** - Manual tasks wait for external `transitionTask()` calls
6. **Routing** - Engine evaluates conditions and follows appropriate paths
7. **Synchronization** - Join points wait for all parallel branches
8. **Completion** - Process reaches terminal state

## Key Files Reference

**Core Interfaces:**
- `zebra-core/src/main/java/com/anite/zebra/core/api/IEngine.java`
- `zebra-core/src/main/java/com/anite/zebra/core/api/ITaskAction.java`
- `zebra-core/src/main/java/com/anite/zebra/core/factory/api/IStateFactory.java`

**Main Engine Implementation:**
- `zebra-core/src/main/java/com/anite/zebra/core/Engine.java`

**Persistence Entities:**
- `zebra-service/src/main/java/uk/co/gidley/zebra/service/om/state/ProcessInstance.java`
- `zebra-service/src/main/java/uk/co/gidley/zebra/service/om/state/TaskInstance.java`

**Example Tests:**
- `zebra-core/src/test/java/com/anite/zebra/core/test/SplitJoinTest.java`

## Strengths

1. **Clean separation of concerns** between engine logic and persistence
2. **Extensibility** through interface-based design
3. **Support for complex workflows** including parallel execution and synchronization
4. **Multiple persistence options** without code changes
5. **Comprehensive state management** with well-defined lifecycles
6. **Audit capabilities** through FOE and history tracking
7. **Flexible data model** via property sets

## Legacy Considerations

- Original code from 2004 CVS repository preserved in `import` folder
- Uses older Java 1.5 language features
- Some modules (zebra-hivemind, zebra-xmlloader) support legacy IoC containers
- Migration to modern Java versions and frameworks would require careful planning
