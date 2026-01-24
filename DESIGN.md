# Zebra Workflow Engine - Design Documentation

## Overview

Zebra is a workflow orchestration engine designed for AI-assisted development. It enables structured execution of complex, long-running workflows with support for parallel execution, conditional routing, synchronization points, and LLM integration.

The system has evolved from a 2004 Java implementation to a modern Python implementation, maintaining the core architectural principles while adapting to contemporary use cases.

## Core Philosophy

### Everything is a Workflow

The key architectural insight is that **everything is a workflow**. This applies not just to business processes, but to:

- **LLM Interactions**: Each LLM call is a workflow with prepare/call/parse/retry tasks
- **Agent Loops**: The agent's decision-making cycle (OBSERVE → ORIENT → DECIDE → ACT → REFLECT → LEARN) is a workflow
- **Goals**: High-level objectives are parent workflows that spawn execution attempts as sub-workflows
- **Sub-tasks**: Complex operations are decomposed into nested workflow hierarchies

This provides:
- **Complete persistence**: All state is workflow state, automatically persisted
- **Full audit trail**: Every operation tracked via Flow of Execution (FOE)
- **Pause/resume capability**: Any operation can be interrupted and resumed
- **Configurability**: Behavior defined in YAML, not hard-coded
- **Self-improvement potential**: Agents can modify their own workflow definitions

## Architecture

### Layered Architecture

```
Workflow Definitions (YAML/JSON)
         ↓
   Definition Loaders
         ↓
   WorkflowEngine (Core)
    ├── Process lifecycle (create → start → complete)
    ├── Task state transitions (ready → running → complete)
    ├── Routing evaluation (serial vs parallel)
    └── Synchronization/join handling
         ↓
    ┌────┴────┐
    ↓         ↓
TaskActions  StateStore
(pluggable)  (SQLite/Memory)
```

### Core Components

| Component | Purpose | Implementation |
|-----------|---------|----------------|
| **Engine** | Workflow execution controller | `zebra/core/engine.py` |
| **Models** | Data structures (definitions & runtime state) | `zebra/core/models.py` |
| **Storage** | Persistence abstraction | `zebra/storage/` |
| **Actions** | Pluggable task implementations | `zebra/tasks/` |
| **Loader** | YAML/JSON definition parsing | `zebra/definitions/loader.py` |

### Module Organization

The project uses a **monorepo structure** with clear separation of concerns:

```
zebra/
├── zebra-py/          # Python workflow engine
│   └── zebra/
│       ├── core/      # Engine, models, exceptions
│       ├── storage/   # SQLite & in-memory backends
│       ├── tasks/     # Task action system
│       ├── mcp/       # Model Context Protocol server
│       └── templates/ # Example workflows
│
├── zebra-tasks/       # Reusable task actions library
│   └── zebra_tasks/
│       ├── llm/       # LLM integration (provider-agnostic)
│       ├── subtasks/  # Sub-workflow management
│       ├── compute/   # Computation actions
│       └── agent/     # Agent-specific actions
│
├── zebra-agent/       # Self-improving AI agent framework
│   └── zebra_agent/
│       ├── cli.py     # Command-line interface
│       ├── loop.py    # Agent OODA loop
│       ├── library.py # Workflow library management
│       ├── memory.py  # Tiered memory system
│       └── metrics.py # Performance tracking
│
├── zebra-agent-web/   # Web interface for agent management in Django
│   └── zebra_agent_web/
│
└── legacy/            # Original Java implementation (archived)
```

## Key Concepts

### State Machines

Workflows and tasks follow explicit state machines with well-defined transitions:

**Process States**:
```
CREATED → RUNNING → COMPLETE
           ↓
         PAUSED → (resume to RUNNING)
           ↓
         FAILED
```

**Task States**:
```
PENDING → AWAITING_SYNC → READY → RUNNING → COMPLETE
                            ↓
                          FAILED
```

- **Auto tasks**: Execute immediately when READY
- **Manual tasks**: Wait in READY state for explicit transition
- **Synchronized tasks**: Wait in AWAITING_SYNC until all incoming parallel branches arrive

### Flow of Execution (FOE)

FOE is a critical concept for tracking execution paths through workflows:

**Purpose**:
- Tracks individual execution threads in parallel workflows
- Each FOE represents one path through split-join structures
- Enables complete audit trails showing how execution flowed
- Manages property inheritance across parallel branches

**Behavior**:
- **Serial routings**: Child task inherits parent FOE (continuity)
- **Parallel routings**: Each target task gets a new FOE (fork)
- **Synchronization**: Multiple FOEs converge at join points (merge)

**Example**:
```
Task A (FOE-1)
   ↓ parallel split
   ├── Task B (FOE-2)
   ├── Task C (FOE-3)
   └── Task D (FOE-4)
        ↓ all converge
Task E (synchronized, receives FOE-2, FOE-3, FOE-4)
```

### TaskAction Interface

The core extension point for custom behavior:

```python
class TaskAction(ABC):
    @abstractmethod
    async def run(
        self, 
        task: TaskInstance, 
        context: ExecutionContext
    ) -> TaskResult:
        """Execute task logic and return result."""
        pass
```

**ExecutionContext provides**:
- Access to process properties: `context.get_process_property(key)`
- Template resolution: `context.resolve_template("{{variable}}")`
- Property manipulation: `context.set_process_property(key, value)`
- Engine access for spawning sub-workflows

### StateStore Interface

Abstracts persistence layer, enabling different storage backends:

**Implementations**:
- **InMemoryStore**: Transient storage for testing
- **SQLiteStore**: Persistent storage for production
- **Custom**: Implement `StateStore` interface for specialized backends

**Capabilities**:
- Transaction management
- Process/task/FOE creation and persistence
- Locking for concurrent access
- Query operations

## Workflow Patterns

### Serial Execution

Tasks execute sequentially:

```yaml
tasks:
  analyze:
    action: llm_call
  review:
    action: manual_review
  publish:
    action: deploy

routings:
  - from: analyze
    to: review
  - from: review
    to: publish
```

### Parallel Execution (Split)

Multiple tasks execute simultaneously:

```yaml
routings:
  - from: start
    to: task_a
    parallel: true
  - from: start
    to: task_b
    parallel: true
  - from: start
    to: task_c
    parallel: true
```

### Synchronization (Join)

Wait for all parallel branches to complete:

```yaml
tasks:
  merge:
    name: "Merge Results"
    synchronized: true
    action: combine
```

### Conditional Routing

Choose paths based on conditions:

```yaml
routings:
  - from: evaluate
    to: approve
    condition: route_name
    name: pass
  - from: evaluate
    to: reject
    condition: route_name
    name: fail
```

### Hierarchical Workflows

Parent workflows spawn child workflows:

```python
# Spawn sub-workflow
sub_process = await engine.create_process(
    definition,
    parent_process_id=process.id,
    parent_task_id=task.id
)
await engine.start_process(sub_process.id)
```

## Agent Framework (zebra-agent)

### Vision

A self-improving, autonomous agent that:
- Pursues high-level goals without step-by-step instructions
- Learns from successes and failures
- Creates and optimizes workflows dynamically
- Operates within configurable guardrails
- Maintains tiered memory (working, episodic, semantic)

### Agent as Workflow

The agent's decision-making loop is itself a workflow:

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ OBSERVE  │→ │  ORIENT  │→ │  DECIDE  │→ │   ACT    │→ │  REFLECT │
│  (task)  │  │  (task)  │  │  (task)  │  │  (task)  │  │  (task)  │
└──────────┘  └──────────┘  └──────────┘  └──────────┘  └─────┬────┘
                                                               │
                                                               v
                                                          ┌──────────┐
                                                          │  LEARN   │
                                                          │  (task)  │
                                                          └──────────┘
```

**Benefits**:
- Agent behavior fully configurable via YAML
- Different "personalities" use different loop workflows
- Agent can potentially modify its own meta-workflow
- Complete persistence and audit trail

### Process Hierarchy

```
Goal Workflow (parent process)
├── Attempt 1: Agent Loop (sub-process)
│   ├── observe
│   ├── orient → LLM workflow (sub-sub-process)
│   ├── decide → LLM workflow (sub-sub-process)
│   ├── act → Task workflow (sub-sub-process)
│   ├── reflect → LLM workflow (sub-sub-process)
│   └── learn
├── Attempt 2: Agent Loop (sub-process)
│   └── ...
└── Finalize
```

### Memory System

**Three-Tier Architecture**:

1. **Working Memory**: Current context, scratch space (transient)
   - Active task data
   - Temporary calculations
   - Current loop state

2. **Episodic Memory**: Specific experiences and outcomes (persistent)
   - Goal attempts with results
   - Workflow executions
   - Success/failure patterns

3. **Semantic Memory**: Generalized knowledge (persistent)
   - Learned workflow patterns
   - Problem classifications
   - Optimization strategies

**Consolidation Process**:
- Periodic "dreaming" phase
- Extract patterns from recent episodes
- Update semantic knowledge
- Prune low-value memories

### Guardrails

Configurable safety constraints:

| Guardrail | Purpose |
|-----------|---------|
| **Token Budget** | Limit total LLM token usage |
| **Iteration Limit** | Prevent infinite loops |
| **Scope** | Allow/forbid specific actions |
| **Time Budget** | Limit execution duration |
| **Custom Rules** | Domain-specific constraints |

**Escalation**: When guardrails are violated, agent can:
- Stop execution
- Request human approval
- Modify plan and continue
- Log warning and proceed

### Learning & Self-Improvement

The agent learns through:

1. **Experience Tracking**: Every execution stored as an episode
2. **Pattern Recognition**: LLM identifies patterns across episodes
3. **Workflow Creation**: Generates new workflows for novel problems
4. **Workflow Optimization**: Refines existing workflows based on performance
5. **Knowledge Generalization**: Extracts reusable concepts from specific experiences

## Design Patterns

### Strategy Pattern
Task actions, condition actions, and lifecycle hooks are pluggable via interface implementations. Custom behavior is injected by specifying class names in workflow definitions.

### Abstract Factory Pattern
`StateStore` provides an abstraction for creating state objects, allowing different persistence implementations without modifying engine code.

### Template Method
The Engine contains the workflow execution algorithm with well-defined extension points where custom logic can be injected.

### State Pattern
Process and task instances maintain explicit state machines with well-defined transitions and validation rules.

### Observer Pattern
Workflows can trigger callbacks on state changes, enabling monitoring and integration with external systems.

## Technology Stack

### Python Implementation

**Core**:
- Python 3.11+
- UV for package management
- Pydantic for data validation
- asyncio for concurrent execution
- django for web app and REST api
- Frontend Django Templates + HTMX + Alpine.js 

**Persistence**:
- aiosqlite for async SQLite access
- SQLAlchemy (optional, for complex queries)
- Postgresql (long term likely only storage option)
- PGVector to store embeddings 

**LLM Integration**:
- Anthropic SDK
- OpenAI SDK
- Provider-agnostic abstraction layer

**Testing**:
- pytest with pytest-asyncio
- pytest-cov for coverage
- Ruff for linting and formatting

## Usage Patterns

### Basic Workflow Execution

```python
from zebra import WorkflowEngine
from zebra.storage import SQLiteStore
from zebra.tasks import ActionRegistry

# Initialize
store = SQLiteStore("workflows.db")
await store.initialize()

registry = ActionRegistry()
registry.register_defaults()

engine = WorkflowEngine(store, registry)

# Load workflow definition
definition = load_workflow("my_workflow.yaml")

# Create and execute
process = await engine.create_process(definition)
await engine.start_process(process.id)

# Check status
status = await engine.get_process_status(process.id)
print(f"Process state: {status['process']['state']}")
```

### Custom Task Action

```python
from zebra.tasks import TaskAction
from zebra.core.models import TaskInstance, TaskResult

class MyCustomAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        # Access task properties
        value = task.properties.get("my_key")
        
        # Resolve templates from process properties
        resolved = context.resolve_template("{{my_var}}")
        
        # Perform work
        result = await do_something(value, resolved)
        
        # Set process properties for downstream tasks
        context.set_process_property("output_key", result)
        
        return TaskResult.ok(output=result)
```

### Agent Goal Pursuit

```python
from zebra_agent import Agent, AgentConfig, Goal, SuccessCriterion

# Create agent
agent = await Agent.create(
    config=AgentConfig(
        name="coding-assistant",
        llm_model="claude-sonnet-4-20250514",
        max_iterations=50,
        persistence_enabled=True,
    )
)

# Define goal
goal = Goal(
    description="Implement a function to parse JSON files",
    success_criteria=[
        SuccessCriterion(
            description="Function extracts emails correctly",
            evaluation_type="computed"
        )
    ]
)

# Execute
result = await agent.run(goal)
print(f"Success: {result.success}")
print(f"Learnings: {result.learnings}")
```

## Extension Points

### 1. Custom Task Actions

Implement `TaskAction` to add new capabilities:

```python
class CustomAction(TaskAction):
    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        # Your custom logic here
        return TaskResult.ok(output=result)

# Register
registry.register_action("my_action", CustomAction)
```

### 2. Custom Condition Actions

Implement routing conditions:

```python
class CustomCondition(ConditionAction):
    async def evaluate(self, task: TaskInstance, context: ExecutionContext) -> bool:
        # Return True/False for routing decision
        return context.get_process_property("score") > 0.8
```

### 3. Custom Storage Backends

Implement `StateStore` for specialized persistence:

```python
class RedisStore(StateStore):
    async def save_process(self, process: ProcessInstance) -> None:
        # Store in Redis
        pass
    
    async def get_process(self, process_id: str) -> ProcessInstance:
        # Retrieve from Redis
        pass
```

### 4. Custom LLM Providers

Implement `LLMProvider` for new AI services:

```python
class CustomLLMProvider(LLMProvider):
    async def complete(self, messages, **kwargs) -> LLMResponse:
        # Call your LLM API
        pass
```

## Architectural Decisions

### 1. Interface-Driven Design
All core components depend on interfaces, enabling multiple implementations without changing engine code. This promotes testability and extensibility.

### 2. Workflow-First Philosophy
By making everything a workflow (even LLM calls and agent loops), the system gains uniform persistence, audit trails, and pause/resume capabilities.

### 3. Async-First Execution
All operations are async, enabling efficient handling of I/O-bound operations (LLM calls, database access) without blocking.

### 4. Separation of Concerns
Clear boundaries between:
- **Engine** (execution logic)
- **Storage** (persistence)
- **Actions** (custom behavior)
- **Definitions** (workflow structure)

### 5. Property-Based Context
Flexible key-value properties on processes and tasks eliminate the need for schema changes when adding new data.

### 6. Hierarchical Workflows
Sub-workflows with parent-child relationships enable workflow decomposition and reusability.

### 7. FOE for Audit
Flow of Execution tracking provides complete execution history, crucial for debugging and analysis.

## Future Directions

### Short Term
- Enhanced MCP integration for AI assistants
- Web UI for workflow visualization
- More built-in task actions (file operations, API calls, etc.)
- Performance optimizations for large-scale workflows

### Medium Term
- Distributed execution across multiple nodes
- Real-time collaboration features
- Advanced agent learning algorithms
- Workflow marketplace for sharing definitions

### Long Term
- Multi-agent collaboration
- Automatic workflow synthesis from natural language
- Quantum-inspired optimization algorithms
- Integration with knowledge graphs

## References

- **Core Documentation**: `zebra-py/README.md` - Python engine usage
- **Workflow Patterns**: `zebra-py/workflows.md` - 43 control-flow patterns
- **Task Actions**: `zebra-tasks/README.md` - Reusable actions library
- **Agent Design**: `zebra-agent/` - Self-improving agent framework
- **Code Guidelines**: `AGENTS.md` - Coding standards for contributors
