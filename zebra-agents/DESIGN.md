# zebra-agents Design Document

## Overview

A Python package that implements a **self-improving looping AI agent** built on top of the zebra workflow engine. The agent can learn, execute, and create workflows to achieve high-level goals autonomously.

### Core Principle: Everything is a Workflow

The key architectural insight is that **everything is a workflow**:

| Concept | Implementation |
|---------|---------------|
| **Goal** | Parent workflow that manages attempts and success criteria |
| **Agent Loop** | Sub-workflow (OBSERVE → ORIENT → DECIDE → ACT → REFLECT → LEARN) |
| **LLM Calls** | Sub-workflows with prepare/call/parse/retry tasks |
| **Task Execution** | Sub-workflows spawned by the ACT phase |

This provides:
- **Full persistence**: All state is workflow state, automatically persisted
- **Audit trail**: Complete history via Flow of Execution (FOE) tracking
- **Pause/resume**: Any operation can be paused and resumed
- **Configurability**: Behavior is defined in YAML, not hard-coded
- **Self-improvement**: Agent can modify its own workflow definitions

### Process Hierarchy

```
Goal Workflow (parent)
├── Agent Loop Attempt 1 (sub-process)
│   ├── observe
│   ├── orient → LLM workflow (sub-sub-process)
│   ├── decide → LLM workflow (sub-sub-process)
│   ├── act → Task workflow (sub-sub-process)
│   ├── reflect → LLM workflow (sub-sub-process)
│   └── learn
├── Agent Loop Attempt 2 (sub-process)
│   └── ...
└── Finalize
```

## Requirements

1. **Separate package**: `zebra-agents` as standalone package depending on `zebra`
2. **Provider-agnostic LLM**: Abstract interface supporting Anthropic, OpenAI, etc.
3. **Self-improving loop**: Agent iterates to improve performance on problems
4. **Workflow learning/creation**: Uses LLMs, classifications, heuristics, computation; can create new workflows
5. **Goal-driven autonomy**: Given high-level goals, agent decides what to do
6. **Configurable persistence**: Option to persist across sessions or start fresh
7. **Configurable guardrails**: Rules/limits for autonomous operation with escalation
8. **Everything-as-workflow**: Goals, agent loop, and LLM calls are all workflows

---

## Dependencies

```
zebra-agents depends on:
├── zebra          # Core workflow engine
└── zebra-tasks    # Reusable task actions (LLM, subtasks)
```

The `zebra-tasks` package provides:
- **LLM calling**: `LLMCallAction`, `LLMProvider`, provider implementations
- **Subtasks**: `SubworkflowAction`, `ParallelSubworkflowsAction`

This avoids duplicating LLM and subtask logic.

## Package Structure

```
zebra-agents/
├── pyproject.toml
├── README.md
├── DESIGN.md
├── zebra_agents/
│   ├── __init__.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── agent.py          # Agent class (orchestrates workflows)
│   │   ├── goal.py           # Goal, GoalExecution, GoalResult models
│   │   └── exceptions.py
│   │
│   ├── workflows/            # Built-in workflow definitions (YAML)
│   │   ├── __init__.py
│   │   ├── goal.yaml         # Goal pursuit workflow
│   │   ├── agent_loop.yaml   # Agent loop (OODA) workflow
│   │   └── loader.py         # Load built-in workflows
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── base.py           # Memory abstract interface
│   │   ├── episodic.py       # Episode/experience memory
│   │   ├── semantic.py       # Learned concepts/patterns
│   │   ├── working.py        # Short-term working memory
│   │   └── store.py          # AgentMemoryStore (SQLite-backed)
│   │
│   ├── learning/
│   │   ├── __init__.py
│   │   ├── workflow_learner.py   # Learn workflows from examples
│   │   ├── workflow_creator.py   # Create new workflows via LLM
│   │   ├── classifier.py         # Problem/pattern classification
│   │   └── evaluator.py          # Performance evaluation
│   │
│   ├── guardrails/
│   │   ├── __init__.py
│   │   ├── base.py           # Guardrail abstract interface
│   │   ├── budget.py         # Token/cost budget limits
│   │   ├── scope.py          # Allowed/forbidden actions
│   │   ├── rules.py          # Custom rule-based guardrails
│   │   └── escalation.py     # Escalation handlers
│   │
│   ├── actions/              # Agent-specific TaskActions
│   │   ├── __init__.py
│   │   ├── loop/             # Agent loop phase actions
│   │   │   ├── observe.py    # ObserveTaskAction
│   │   │   ├── orient.py     # OrientTaskAction (uses zebra-tasks LLM)
│   │   │   ├── decide.py     # DecideTaskAction (uses zebra-tasks LLM)
│   │   │   ├── act.py        # ActTaskAction (uses zebra-tasks subtasks)
│   │   │   ├── reflect.py    # ReflectTaskAction (uses zebra-tasks LLM)
│   │   │   └── learn.py      # LearnTaskAction
│   │   ├── goal/             # Goal workflow actions
│   │   │   ├── initialize.py
│   │   │   ├── spawn_loop.py # Uses zebra-tasks SubworkflowAction
│   │   │   ├── evaluate.py
│   │   │   └── finalize.py
│   │   └── guardrails.py     # CheckGuardrailsAction, EscalateAction
│   │
│   └── config/
│       ├── __init__.py
│       ├── agent_config.py   # AgentConfig, PersistenceConfig
│       └── presets.py        # Pre-built configurations
│
└── tests/
    ├── __init__.py
    ├── test_agent.py
    ├── test_workflows.py
    ├── test_memory.py
    └── test_guardrails.py
```

---

## Core Abstractions

### 1. Agent as Workflow

The agent's state machine is itself a zebra workflow. Instead of hard-coded loop logic, the agent's behavior (OBSERVE → ORIENT → DECIDE → ACT → REFLECT → LEARN) is defined as a configurable workflow definition.

**Benefits:**
- Agent behavior is fully configurable via YAML
- Different agent "personalities" can use different loop workflows
- The agent can potentially modify its own meta-workflow (self-improvement)
- Full zebra benefits: persistence, audit trail, visualization, pause/resume

#### Agent Loop Workflow Definition

```yaml
# agent_loop.yaml - The meta-workflow that defines agent behavior
name: "Agent Loop"
version: 1

tasks:
  observe:
    name: "Observe"
    action: observe
    properties:
      gather_goal_state: true
      retrieve_memories: true
      check_environment: true

  orient:
    name: "Orient"
    action: orient
    properties:
      classify_problem: true
      match_patterns: true
      assess_complexity: true

  decide:
    name: "Decide"
    action: decide
    properties:
      select_or_create_workflow: true
      break_into_steps: true

  act:
    name: "Act"
    action: act
    properties:
      execute_sub_workflow: true
      collect_results: true

  reflect:
    name: "Reflect"
    action: reflect
    auto: false  # Pauses to evaluate
    properties:
      check_success_criteria: true
      analyze_effectiveness: true

  learn:
    name: "Learn"
    action: learn
    properties:
      extract_learnings: true
      update_memory: true
      generalize_patterns: true

  check_guardrails:
    name: "Check Guardrails"
    action: check_guardrails
    properties:
      check_all: true

  escalate:
    name: "Escalate"
    action: escalate
    auto: false  # Waits for human input
    properties:
      notify_human: true

  complete:
    name: "Complete"
    action: finalize
    properties:
      summarize_result: true

routings:
  # Main loop flow
  - id: start_to_guardrails
    from: __start__
    to: check_guardrails

  - id: guardrails_to_observe
    from: check_guardrails
    to: observe
    condition: route_name
    name: ok

  - id: guardrails_to_escalate
    from: check_guardrails
    to: escalate
    condition: route_name
    name: violation

  - id: observe_to_orient
    from: observe
    to: orient

  - id: orient_to_decide
    from: orient
    to: decide

  - id: decide_to_act
    from: decide
    to: act

  - id: act_to_reflect
    from: act
    to: reflect

  # Reflection outcomes
  - id: reflect_goal_achieved
    from: reflect
    to: learn
    condition: route_name
    name: goal_achieved

  - id: reflect_continue
    from: reflect
    to: check_guardrails
    condition: route_name
    name: continue

  - id: reflect_failed
    from: reflect
    to: escalate
    condition: route_name
    name: failed

  # Learning to completion
  - id: learn_to_complete
    from: learn
    to: complete

  # Escalation outcomes
  - id: escalate_continue
    from: escalate
    to: check_guardrails
    condition: route_name
    name: continue

  - id: escalate_stop
    from: escalate
    to: complete
    condition: route_name
    name: stop

first_task: check_guardrails
```

#### Agent Class

```python
from dataclasses import dataclass, field
from typing import Any, Callable

from zebra.core.engine import WorkflowEngine
from zebra.core.models import ProcessDefinition, ProcessInstance


@dataclass
class AgentConfig:
    """Configuration for an Agent."""
    name: str
    llm_provider: str = "anthropic"
    llm_model: str = "claude-sonnet-4-20250514"
    max_iterations: int = 100
    max_tokens_per_turn: int = 4000
    max_total_tokens: int = 1_000_000
    persistence_enabled: bool = True
    memory_path: str | None = None
    guardrails: list[str] = field(default_factory=lambda: ["budget", "scope"])
    auto_learn: bool = True

    # The workflow definition for the agent loop itself
    loop_workflow: str | ProcessDefinition = "default"  # "default", path, or definition


@dataclass
class Agent:
    """
    The main agent abstraction.

    The agent's execution loop is itself a zebra workflow, making the
    agent's behavior fully configurable and introspectable.

    An Agent:
    1. Receives high-level goals
    2. Runs a meta-workflow (the agent loop) to pursue goals
    3. The meta-workflow orchestrates sub-workflows for actual tasks
    4. Learns from successes and failures
    5. Can modify its own loop workflow for self-improvement
    """
    config: AgentConfig
    engine: WorkflowEngine
    llm: "LLMProvider"
    memory: "Memory"
    guardrails: list["Guardrail"]

    # The agent loop is a workflow process
    loop_definition: ProcessDefinition
    loop_process: ProcessInstance | None = None

    current_goal: "Goal | None" = None
    iteration_count: int = 0

    # Callbacks
    on_state_change: Callable[[str, str], None] | None = None
    on_iteration: Callable[[int, dict], None] | None = None
    on_goal_complete: Callable[["Goal", "GoalResult"], None] | None = None

    @classmethod
    async def create(
        cls,
        config: AgentConfig,
        guardrails: list["Guardrail"] | None = None,
    ) -> "Agent":
        """Create an agent with its loop workflow."""
        engine = WorkflowEngine(...)
        llm = create_llm_provider(config.llm_provider, config.llm_model)
        memory = create_memory(config)

        # Load the agent loop workflow
        if config.loop_workflow == "default":
            loop_def = load_default_agent_loop()
        elif isinstance(config.loop_workflow, str):
            loop_def = load_workflow_from_file(config.loop_workflow)
        else:
            loop_def = config.loop_workflow

        return cls(
            config=config,
            engine=engine,
            llm=llm,
            memory=memory,
            guardrails=guardrails or [],
            loop_definition=loop_def,
        )

    async def run(self, goal: "Goal") -> "GoalResult":
        """
        Run the agent to achieve a goal.

        This starts the agent loop workflow, which orchestrates
        the observe/orient/decide/act/reflect/learn cycle.
        """
        self.current_goal = goal
        self.iteration_count = 0

        # Inject context into the loop workflow
        initial_properties = {
            "__goal__": goal,
            "__llm_provider__": self.llm,
            "__memory__": self.memory,
            "__guardrails__": self.guardrails,
            "__agent__": self,
        }

        # Create and start the agent loop as a workflow process
        self.loop_process = await self.engine.create_process(
            self.loop_definition,
            properties=initial_properties,
        )
        await self.engine.start_process(self.loop_process.id)

        # Run until the loop workflow completes
        while True:
            status = await self.engine.get_process_status(self.loop_process.id)

            if status["process"]["state"] == "complete":
                break

            # Handle manual tasks (reflect, escalate)
            pending = await self.engine.get_pending_tasks(self.loop_process.id)
            for task in pending:
                await self._handle_pending_task(task)

            self.iteration_count += 1

        return self._build_result()

    @property
    def current_state(self) -> str:
        """Get current state from the running loop workflow."""
        if self.loop_process is None:
            return "idle"
        # Find the currently running or ready task
        # This reflects the agent's current phase
        ...

    async def pause(self) -> None:
        """Pause the agent loop."""
        if self.loop_process:
            await self.engine.pause_process(self.loop_process.id)

    async def resume(self) -> None:
        """Resume the agent loop."""
        if self.loop_process:
            await self.engine.resume_process(self.loop_process.id)
```

### 2. Goal as Workflow

Goals are also workflows. The **goal workflow** is the parent process that:
- Tracks overall goal state and success criteria
- Spawns **agent loop executions** as sub-processes
- Handles retries and multiple attempts
- Evaluates success criteria after each attempt

#### Process Hierarchy

```
Goal Workflow (parent process)
├── Attempt 1: Agent Loop (sub-process)
│   ├── observe → LLM call (sub-sub-process)
│   ├── orient → LLM call (sub-sub-process)
│   ├── decide → LLM call (sub-sub-process)
│   ├── act → Task Workflow (sub-sub-process)
│   ├── reflect → LLM call (sub-sub-process)
│   └── learn
├── Attempt 2: Agent Loop (sub-process)
│   └── ...
└── Finalize
```

#### Goal Workflow Definition

```yaml
# goal.yaml - The workflow that manages goal pursuit
name: "Goal Pursuit"
version: 1

tasks:
  initialize:
    name: "Initialize Goal"
    action: initialize_goal
    properties:
      validate_criteria: true
      setup_context: true

  attempt:
    name: "Attempt Goal"
    action: spawn_agent_loop
    properties:
      max_iterations: "{{max_iterations}}"

  evaluate_criteria:
    name: "Evaluate Success Criteria"
    action: evaluate_success
    properties:
      criteria: "{{success_criteria}}"

  decide_retry:
    name: "Decide Retry"
    action: decide_retry
    auto: false  # May need human input
    properties:
      max_attempts: "{{max_attempts}}"

  finalize_success:
    name: "Finalize Success"
    action: finalize_goal
    properties:
      status: achieved

  finalize_failure:
    name: "Finalize Failure"
    action: finalize_goal
    properties:
      status: failed

routings:
  - from: initialize
    to: attempt

  - from: attempt
    to: evaluate_criteria

  - from: evaluate_criteria
    to: finalize_success
    condition: route_name
    name: all_criteria_met

  - from: evaluate_criteria
    to: decide_retry
    condition: route_name
    name: criteria_not_met

  - from: decide_retry
    to: attempt
    condition: route_name
    name: retry

  - from: decide_retry
    to: finalize_failure
    condition: route_name
    name: give_up

first_task: initialize
```

#### Goal Data Model

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from zebra.core.models import ProcessDefinition, ProcessInstance


class GoalPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class SuccessCriterion:
    """A measurable criterion for goal success."""
    id: str
    description: str
    evaluation_type: str  # "llm", "heuristic", "computed"
    evaluator: str | None = None
    threshold: float | None = None
    is_met: bool = False


@dataclass
class Goal:
    """
    A high-level objective represented as a workflow.

    The goal itself becomes a parent process that spawns
    agent loop executions as sub-processes.
    """
    id: str
    description: str
    priority: GoalPriority = GoalPriority.MEDIUM

    # Success criteria
    success_criteria: list[SuccessCriterion] = field(default_factory=list)

    # Hierarchical goals (sub-goals become sub-workflows)
    parent_goal_id: str | None = None
    subgoal_ids: list[str] = field(default_factory=list)

    # Context and constraints
    context: dict[str, Any] = field(default_factory=dict)
    constraints: list[str] = field(default_factory=list)

    # Execution limits
    max_attempts: int = 3
    max_iterations_per_attempt: int = 50

    # Deadline (optional)
    deadline: datetime | None = None

    # Workflow references
    goal_workflow: str | ProcessDefinition = "default"  # The goal pursuit workflow
    loop_workflow: str | ProcessDefinition = "default"  # The agent loop to use

    def to_workflow_properties(self) -> dict[str, Any]:
        """Convert goal to workflow properties for process creation."""
        return {
            "__goal_id__": self.id,
            "__goal_description__": self.description,
            "success_criteria": [c.__dict__ for c in self.success_criteria],
            "context": self.context,
            "constraints": self.constraints,
            "max_attempts": self.max_attempts,
            "max_iterations": self.max_iterations_per_attempt,
        }


@dataclass
class GoalExecution:
    """
    Runtime state of a goal being pursued.

    This wraps the goal workflow process instance.
    """
    goal: Goal
    process: ProcessInstance  # The goal workflow process
    attempts: list[ProcessInstance] = field(default_factory=list)  # Agent loop sub-processes

    @property
    def status(self) -> str:
        """Get goal status from workflow process state."""
        return self.process.state.value

    @property
    def current_attempt(self) -> int:
        return len(self.attempts)


@dataclass
class GoalResult:
    """The outcome of pursuing a goal."""
    goal: Goal
    success: bool
    criteria_results: dict[str, bool]
    summary: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    total_iterations: int = 0
    total_tokens: int = 0
    duration_seconds: float = 0.0
    learnings: list[str] = field(default_factory=list)

    # References to workflow processes for full audit trail
    goal_process_id: str | None = None
    attempt_process_ids: list[str] = field(default_factory=list)
```

#### Spawning Goal as Workflow

```python
class Agent:
    async def run(self, goal: Goal) -> GoalResult:
        """
        Run the agent to achieve a goal.

        The goal itself is a workflow that spawns agent loop
        executions as sub-processes.
        """
        self.current_goal = goal

        # Load goal workflow definition
        if goal.goal_workflow == "default":
            goal_def = load_default_goal_workflow()
        elif isinstance(goal.goal_workflow, str):
            goal_def = load_workflow_from_file(goal.goal_workflow)
        else:
            goal_def = goal.goal_workflow

        # Create goal workflow process
        goal_process = await self.engine.create_process(
            goal_def,
            properties={
                **goal.to_workflow_properties(),
                "__agent__": self,
                "__llm_provider__": self.llm,
                "__memory__": self.memory,
                "__guardrails__": self.guardrails,
                "__loop_workflow__": goal.loop_workflow,
            },
        )

        # Start goal workflow
        await self.engine.start_process(goal_process.id)

        # Create execution tracker
        execution = GoalExecution(goal=goal, process=goal_process)

        # Run until goal workflow completes
        while True:
            status = await self.engine.get_process_status(goal_process.id)

            if status["process"]["state"] in ("complete", "failed"):
                break

            # Handle manual tasks (decide_retry, escalations)
            pending = await self.engine.get_pending_tasks(goal_process.id)
            for task in pending:
                await self._handle_pending_task(task)

        return self._build_result(execution)
```

### 3. LLM Provider Interface

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """A message in a conversation."""
    role: MessageRole
    content: str
    name: str | None = None  # For tool messages
    tool_call_id: str | None = None
    tool_calls: list["ToolCall"] | None = None


@dataclass
class ToolCall:
    """A tool/function call request."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolDefinition:
    """Definition of a tool the LLM can call."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    handler: "Callable | None" = None


@dataclass
class LLMResponse:
    """Response from an LLM call."""
    content: str | None
    tool_calls: list[ToolCall] | None
    finish_reason: str
    usage: "TokenUsage"
    model: str
    raw_response: Any = None


@dataclass
class TokenUsage:
    """Token usage statistics."""
    input_tokens: int
    output_tokens: int
    total_tokens: int


class LLMProvider(ABC):
    """
    Abstract interface for LLM providers.

    Implementations must handle:
    - Message formatting for the specific provider
    - Tool/function calling translation
    - Streaming support
    - Error handling and retries
    """

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        stop_sequences: list[str] | None = None,
    ) -> LLMResponse:
        """Generate a completion."""
        pass

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Stream a completion."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Get the model name."""
        pass

    @property
    @abstractmethod
    def max_context_tokens(self) -> int:
        """Get maximum context window size."""
        pass
```

---

## Agent Loop Architecture

The agent loop is implemented as a **zebra workflow**, not hard-coded logic. Each phase (OBSERVE, ORIENT, DECIDE, ACT, REFLECT, LEARN) is a task in the workflow, and transitions are routings.

```
                    ┌─────────────────────────────────────────┐
                    │                                         │
                    v                                         │
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────┴─────┐
│ OBSERVE  │->│  ORIENT  │->│  DECIDE  │->│   ACT    │->│  REFLECT │
│  (task)  │  │  (task)  │  │  (task)  │  │  (task)  │  │  (task)  │
└──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
     │              │             │             │              │
     v              v             v             v              v
  Gather        Classify      Create/       Execute        Evaluate
  context       problem       refine       sub-workflow     results
  & state       type          plan
                                                              │
                                                              v
                                                         ┌──────────┐
                                                         │  LEARN   │
                                                         │  (task)  │
                                                         └──────────┘
```

### Workflow-as-State-Machine

The agent's state is determined by which task is currently executing in the loop workflow:
- **observe** task running → agent is in OBSERVE state
- **orient** task running → agent is in ORIENT state
- **reflect** task pending (manual) → agent is waiting for reflection decision
- etc.

This means:
- State transitions are workflow routings
- State persistence is automatic (zebra persists process state)
- The agent can be paused/resumed at any point
- Full audit trail of state transitions via FOE tracking

### Loop Phases as Tasks

Each phase is a TaskAction that can internally use LLM calls (also as workflow tasks):

#### OBSERVE Task
- Gathers current goal and progress
- Retrieves relevant memories
- Checks environment state
- **May spawn LLM sub-workflow** for context summarization

#### ORIENT Task
- Classifies problem type
- Identifies patterns from memory
- Matches to known workflows
- **Spawns LLM sub-workflow** for classification

#### DECIDE Task
- Selects existing workflow or creates new plan
- **Spawns LLM sub-workflow** for planning/workflow creation

#### ACT Task
- Converts plan to ProcessDefinition
- **Spawns and executes sub-workflow** for the actual task
- Collects execution results

#### REFLECT Task
- Checks success criteria
- Analyzes effectiveness
- **Spawns LLM sub-workflow** for evaluation
- Returns routing decision: goal_achieved, continue, or failed

#### LEARN Task
- Extracts learnings from episode
- Updates episodic and semantic memory
- **May spawn LLM sub-workflow** for generalization

---

## Integration with Zebra

### LLM Calls as Workflow Tasks

LLM calls are **not direct function calls** but are themselves workflow tasks. This provides:
- **Persistence**: LLM call state is persisted; can resume after crash
- **Audit trail**: Full history of all LLM interactions
- **Retry logic**: Workflow engine handles retries on failure
- **Cost tracking**: Token usage tracked per task
- **Composability**: LLM calls can be chained, parallelized, or conditionally executed

#### LLM Workflow Pattern

```yaml
# llm_call.yaml - A reusable LLM call workflow
name: "LLM Call"
version: 1

tasks:
  prepare:
    name: "Prepare Messages"
    action: prepare_messages
    properties:
      system_prompt: "{{system_prompt}}"
      user_prompt: "{{prompt}}"

  call_llm:
    name: "Call LLM"
    action: llm_api_call
    properties:
      provider: "{{provider}}"
      model: "{{model}}"
      temperature: "{{temperature}}"
      max_tokens: "{{max_tokens}}"

  parse_response:
    name: "Parse Response"
    action: parse_llm_response
    properties:
      expected_format: "{{response_format}}"

  handle_error:
    name: "Handle Error"
    action: llm_error_handler
    properties:
      retry_count: "{{retry_count}}"

routings:
  - from: prepare
    to: call_llm
  - from: call_llm
    to: parse_response
    condition: route_name
    name: success
  - from: call_llm
    to: handle_error
    condition: route_name
    name: error
  - from: handle_error
    to: call_llm
    condition: route_name
    name: retry
  - from: handle_error
    to: parse_response
    condition: route_name
    name: give_up

first_task: prepare
```

#### Spawning LLM Sub-Workflows

Tasks that need LLM calls spawn sub-workflows:

```python
class OrientTaskAction(TaskAction):
    """Orient phase - classifies problem using LLM sub-workflow."""

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        goal = context.get_process_property("__goal__")
        memories = context.get_process_property("retrieved_memories")

        # Create LLM sub-workflow for classification
        llm_workflow = create_llm_workflow(
            system_prompt="You are a problem classifier.",
            prompt=f"""Classify this problem:
Goal: {goal.description}
Context: {memories}

Output JSON: {{"problem_type": "...", "complexity": "...", "patterns": [...]}}""",
            response_format="json",
        )

        # Execute as sub-process
        sub_process = await context.engine.create_process(
            llm_workflow,
            parent_process_id=context.process.id,
            parent_task_id=task.id,
        )
        await context.engine.start_process(sub_process.id)

        # Wait for sub-workflow completion
        result = await context.engine.wait_for_process(sub_process.id)

        # Store classification result
        context.set_process_property("classification", result.output)

        return TaskResult.ok(output=result.output)
```

### Custom Task Actions

These extend `zebra.tasks.base.TaskAction`:

| Action | Purpose |
|--------|---------|
| `ObserveTaskAction` | Gather context, memories, environment state |
| `OrientTaskAction` | Classify problem via LLM sub-workflow |
| `DecideTaskAction` | Plan/select workflow via LLM sub-workflow |
| `ActTaskAction` | Execute sub-workflow for actual task |
| `ReflectTaskAction` | Evaluate results via LLM sub-workflow |
| `LearnTaskAction` | Extract learnings, update memory |
| `LLMAPICallAction` | Low-level LLM API call (used in sub-workflows) |
| `CheckGuardrailsAction` | Check all guardrails, return violation or ok |
| `EscalateAction` | Pause for human intervention |

### LLMAPICallAction (Low-Level)

```python
class LLMAPICallAction(TaskAction):
    """
    Low-level LLM API call action used within LLM sub-workflows.

    This is the actual API call - higher-level actions spawn
    workflows that use this action.
    """

    async def run(self, task: TaskInstance, context: ExecutionContext) -> TaskResult:
        llm: LLMProvider = context.process.properties.get("__llm_provider__")
        messages = context.get_process_property("prepared_messages")

        try:
            response = await llm.complete(
                messages,
                temperature=task.properties.get("temperature", 0.7),
                max_tokens=task.properties.get("max_tokens", 2000)
            )

            # Track token usage
            tokens_used = context.get_process_property("total_tokens", 0)
            context.set_process_property(
                "total_tokens",
                tokens_used + response.usage.total_tokens
            )

            context.set_process_property("llm_response", response.content)
            context.set_process_property("llm_usage", {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            })

            return TaskResult.ok(
                output=response.content,
                next_route="success"
            )

        except Exception as e:
            context.set_process_property("llm_error", str(e))
            return TaskResult.ok(next_route="error")
```

### Plan-to-Workflow Conversion

```python
from zebra.core.models import ProcessDefinition, TaskDefinition, RoutingDefinition


@dataclass
class PlanStep:
    """A single step in a plan."""
    id: str
    description: str
    action_type: str  # "llm", "think", "execute", "decide", etc.
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class Plan:
    """A plan for achieving a goal."""
    id: str
    goal_id: str
    steps: list[PlanStep]

    @property
    def needs_workflow(self) -> bool:
        """Whether this plan needs to be converted to a workflow."""
        return len(self.steps) > 1 or any(s.depends_on for s in self.steps)

    def to_workflow_definition(self) -> ProcessDefinition:
        """Convert this plan to a zebra workflow definition."""
        tasks = {}
        routings = []

        for step in self.steps:
            task_def = TaskDefinition(
                id=step.id,
                name=step.description,
                action=self._action_type_to_action(step.action_type),
                auto=step.action_type != "decide",
                properties={
                    **step.inputs,
                    "outputs": step.outputs,
                }
            )
            tasks[step.id] = task_def

            # Create routings based on dependencies
            for dep_id in step.depends_on:
                routings.append(RoutingDefinition(
                    id=f"{dep_id}_to_{step.id}",
                    source_task_id=dep_id,
                    dest_task_id=step.id,
                ))

        # Find first task (no dependencies)
        first_task = next(
            (s.id for s in self.steps if not s.depends_on),
            self.steps[0].id
        )

        return ProcessDefinition(
            id=f"plan_{self.id}",
            name=f"Plan for {self.goal_id}",
            first_task_id=first_task,
            tasks=tasks,
            routings=routings,
        )

    def _action_type_to_action(self, action_type: str) -> str:
        """Map plan action types to zebra action names."""
        mapping = {
            "llm": "llm_call",
            "think": "think",
            "execute": "shell",
            "decide": "decision",
            "reflect": "reflect",
            "learn": "learn",
        }
        return mapping.get(action_type, "llm_call")
```

### Dynamic Workflow Creation

```python
class WorkflowCreator:
    """Creates zebra workflow definitions dynamically using LLM."""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def create_workflow(
        self,
        goal: Goal,
        context: dict,
        available_actions: list[str],
    ) -> ProcessDefinition:
        """Create a workflow definition for achieving a goal."""

        prompt = f"""Create a workflow to achieve this goal:

Goal: {goal.description}
Context: {json.dumps(context)}
Available Actions: {available_actions}

Output a workflow as JSON with this structure:
{{
    "name": "Workflow name",
    "tasks": {{
        "task_id": {{
            "name": "Task name",
            "action": "action_name",
            "auto": true/false,
            "properties": {{}}
        }}
    }},
    "routings": [
        {{"from": "task_id", "to": "task_id", "condition": "optional"}}
    ],
    "first_task": "task_id"
}}

Design a workflow that:
1. Breaks the goal into logical steps
2. Uses appropriate actions for each step
3. Handles potential failures with branching
4. Includes reflection points for complex goals
"""

        response = await self.llm.complete([
            Message(role=MessageRole.USER, content=prompt)
        ], temperature=0.3)

        workflow_dict = self._parse_workflow_json(response.content)
        return self._dict_to_definition(workflow_dict)
```

---

## Memory System

### Three-Tier Architecture

1. **Working Memory**: Current context, scratch space (transient)
2. **Episodic Memory**: Specific experiences and outcomes (persistent)
3. **Semantic Memory**: Generalized concepts and patterns (persistent)

### Memory Interface

```python
from abc import ABC, abstractmethod


@dataclass
class MemoryEntry:
    """A single memory entry."""
    id: str
    content: str
    memory_type: str  # "episodic", "semantic", "working"
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    importance: float = 0.5  # 0-1 scale


@dataclass
class Episode:
    """An episodic memory - a specific experience."""
    id: str
    goal_id: str
    workflow_id: str | None
    actions: list[dict[str, Any]]
    outcome: str  # "success", "failure", "partial"
    learnings: list[str]
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Concept:
    """A semantic memory - learned knowledge."""
    id: str
    name: str
    description: str
    category: str  # "workflow_pattern", "problem_type", "strategy", etc.
    examples: list[str] = field(default_factory=list)
    related_concepts: list[str] = field(default_factory=list)
    confidence: float = 0.5
    source_episodes: list[str] = field(default_factory=list)


class Memory(ABC):
    """Abstract memory interface."""

    @abstractmethod
    async def store(self, entry: MemoryEntry) -> str:
        """Store a memory entry."""
        pass

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        memory_types: list[str] | None = None,
        limit: int = 10,
        relevance_threshold: float = 0.5,
    ) -> list[MemoryEntry]:
        """Retrieve relevant memories."""
        pass

    @abstractmethod
    async def forget(self, entry_id: str) -> bool:
        """Remove a memory entry."""
        pass

    @abstractmethod
    async def consolidate(self) -> None:
        """Consolidate memories - move working to long-term, merge, decay."""
        pass
```

### SQLite Storage Schema

```sql
-- Episodes (experiences)
CREATE TABLE episodes (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL,
    workflow_id TEXT,
    actions JSON NOT NULL,
    outcome TEXT NOT NULL,
    learnings JSON NOT NULL,
    embedding BLOB,
    created_at TEXT NOT NULL
);

-- Concepts (learned patterns)
CREATE TABLE concepts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    examples JSON,
    related_concepts JSON,
    confidence REAL DEFAULT 0.5,
    source_episodes JSON,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Learned Workflows
CREATE TABLE learned_workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    source_goal_pattern TEXT,
    success_rate REAL DEFAULT 0.0,
    usage_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Performance Metrics
CREATE TABLE metrics (
    id TEXT PRIMARY KEY,
    goal_id TEXT NOT NULL,
    workflow_id TEXT,
    success INTEGER NOT NULL,
    iterations INTEGER NOT NULL,
    total_tokens INTEGER NOT NULL,
    duration_seconds REAL NOT NULL,
    created_at TEXT NOT NULL
);

-- Working Memory (transient)
CREATE TABLE working_memory (
    key TEXT PRIMARY KEY,
    value JSON NOT NULL,
    expires_at TEXT
);

-- Indexes
CREATE INDEX idx_episodes_goal ON episodes(goal_id);
CREATE INDEX idx_concepts_category ON concepts(category);
CREATE INDEX idx_metrics_workflow ON metrics(workflow_id);
```

---

## Guardrails System

### Guardrail Interface

```python
from abc import ABC, abstractmethod


@dataclass
class GuardrailViolation:
    """Represents a guardrail violation."""
    guardrail_name: str
    severity: str  # "warning", "error", "critical"
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    suggested_action: str = "stop"  # "stop", "escalate", "warn"


class Guardrail(ABC):
    """Abstract base for guardrails."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Guardrail name."""
        pass

    @abstractmethod
    async def check(self, agent: Agent) -> GuardrailViolation | None:
        """Check if guardrail is violated. Returns None if OK."""
        pass

    async def on_violation(
        self,
        agent: Agent,
        violation: GuardrailViolation,
    ) -> None:
        """Called when this guardrail is violated."""
        pass
```

### Built-in Guardrails

| Guardrail | Purpose |
|-----------|---------|
| `TokenBudgetGuardrail` | Limit total token usage |
| `IterationLimitGuardrail` | Limit loop iterations |
| `ScopeGuardrail` | Allow/forbid specific actions |
| `RuleBasedGuardrail` | Custom rules (Python expressions) |

### Example: TokenBudgetGuardrail

```python
class TokenBudgetGuardrail(Guardrail):
    """Limits total token usage."""

    def __init__(self, max_tokens: int, warning_threshold: float = 0.8):
        self.max_tokens = max_tokens
        self.warning_threshold = warning_threshold

    @property
    def name(self) -> str:
        return "token_budget"

    async def check(self, agent: Agent) -> GuardrailViolation | None:
        current = agent.memory.get_working("total_tokens_used", 0)

        if current >= self.max_tokens:
            return GuardrailViolation(
                guardrail_name=self.name,
                severity="error",
                message=f"Token budget exceeded: {current}/{self.max_tokens}",
                suggested_action="stop"
            )

        if current >= self.max_tokens * self.warning_threshold:
            return GuardrailViolation(
                guardrail_name=self.name,
                severity="warning",
                message=f"Approaching token budget: {current}/{self.max_tokens}",
                suggested_action="warn"
            )

        return None
```

### Escalation Handler

```python
@dataclass
class EscalationResult:
    """Result of an escalation."""
    action: str  # "continue", "stop", "modify", "approve"
    input: Any = None
    modified_plan: Plan | None = None
    message: str = ""


class EscalationHandler(ABC):
    """Handles escalation when agent needs human intervention."""

    @abstractmethod
    async def escalate(
        self,
        agent: Agent,
        reason: str,
        context: dict,
    ) -> EscalationResult:
        """Escalate to human. Returns the human's decision/input."""
        pass
```

---

## Persistence Configuration

```python
from enum import Enum


class PersistenceMode(str, Enum):
    NONE = "none"          # In-memory only
    SESSION = "session"    # Clear on restart
    FULL = "full"          # Persist across sessions
    SELECTIVE = "selective"  # Only successful learnings


@dataclass
class PersistenceConfig:
    """Configuration for agent persistence."""
    mode: PersistenceMode = PersistenceMode.FULL

    # Paths (None = use defaults)
    workflow_db_path: str | None = None
    memory_db_path: str | None = None

    # What to persist
    persist_episodes: bool = True
    persist_concepts: bool = True
    persist_workflows: bool = True
    persist_metrics: bool = True

    # Retention
    max_episodes: int = 1000
    max_age_days: int = 90

    # On startup
    load_learned_workflows: bool = True
    load_recent_episodes: int = 100
```

---

## Example Usage

### Basic Agent

```python
import asyncio
from zebra_agents import Agent, AgentConfig, Goal, SuccessCriterion
from zebra_agents.llm import AnthropicProvider
from zebra_agents.guardrails import TokenBudgetGuardrail, ScopeGuardrail


async def main():
    # Create agent
    agent = await Agent.create(
        config=AgentConfig(
            name="coding-assistant",
            llm_provider="anthropic",
            llm_model="claude-sonnet-4-20250514",
            max_iterations=50,
            max_total_tokens=500_000,
            persistence_enabled=True,
        ),
        guardrails=[
            TokenBudgetGuardrail(max_tokens=500_000),
            ScopeGuardrail(
                allowed_actions=["llm", "think", "reflect", "shell"],
                require_confirmation_for=["shell"],
            ),
        ],
    )

    # Define a goal
    goal = Goal(
        id="goal-001",
        description="Implement a function to parse JSON files and extract emails",
        success_criteria=[
            SuccessCriterion(
                id="sc-1",
                description="Function correctly extracts emails from test files",
                evaluation_type="computed",
            ),
        ],
        context={
            "language": "python",
            "test_files": ["test1.json", "test2.json"],
        },
    )

    # Run agent
    result = await agent.run(goal)

    print(f"Goal achieved: {result.success}")
    print(f"Iterations: {result.iterations}")
    print(f"Tokens used: {result.total_tokens}")


asyncio.run(main())
```

### Self-Improving Workflow Definition

```yaml
name: "Self-Improving Problem Solver"
version: 1

tasks:
  analyze_problem:
    name: "Analyze Problem"
    action: think
    properties:
      problem: "{{goal.description}}"
      output_key: analysis

  check_existing:
    name: "Check Existing Solutions"
    action: llm_call
    properties:
      prompt: |
        Given this analysis: {{analysis.output}}
        Search memory for similar problems and their solutions.
      output_key: existing_solutions

  decide_approach:
    name: "Decide Approach"
    action: decision
    auto: false
    properties:
      prompt: "Based on analysis and existing solutions, which approach?"
      options:
        - use_existing
        - modify_existing
        - create_new

  execute_solution:
    name: "Execute Solution"
    action: llm_call
    properties:
      prompt: "Execute the chosen approach: {{decision.output}}"
      output_key: solution

  evaluate:
    name: "Evaluate Results"
    action: reflect
    properties:
      criteria: "{{goal.success_criteria}}"

  learn:
    name: "Extract Learnings"
    action: learn
    properties:
      episode_data: "{{execution_history}}"

routings:
  - from: analyze_problem
    to: check_existing
  - from: check_existing
    to: decide_approach
  - from: decide_approach
    to: execute_solution
  - from: execute_solution
    to: evaluate
  - from: evaluate
    to: learn
    condition: route_name
    name: success
  - from: evaluate
    to: analyze_problem
    condition: route_name
    name: retry
```

---

## Critical Files to Reference

| File | Purpose |
|------|---------|
| `zebra-py/zebra/core/engine.py` | WorkflowEngine - process lifecycle |
| `zebra-py/zebra/tasks/base.py` | TaskAction, ExecutionContext interfaces |
| `zebra-py/zebra/core/models.py` | ProcessDefinition, TaskInstance models |
| `zebra-py/zebra/storage/base.py` | StateStore interface pattern |

---

## Implementation Phases

### Phase 1: Package Foundation
1. Create package structure with `pyproject.toml`
2. Implement LLM provider interface + Anthropic provider
3. Create basic Agent, AgentConfig, Goal models
4. Write initial test suite

### Phase 2: Core Loop
1. Implement AgentLoop with OODA phases
2. Create Plan model and plan-to-workflow conversion
3. Integrate with zebra WorkflowEngine
4. Add custom TaskActions (llm, think, reflect)

### Phase 3: Memory System
1. Implement Memory interface
2. Create AgentMemoryStore with SQLite
3. Add episodic and semantic memory
4. Implement memory retrieval

### Phase 4: Learning
1. Implement WorkflowCreator (LLM-based)
2. Add WorkflowLearner for pattern extraction
3. Create problem classifier
4. Build performance evaluator

### Phase 5: Guardrails
1. Implement Guardrail interface
2. Add built-in guardrails (budget, scope, rules)
3. Create escalation handlers
4. Add CLI escalation interface

### Phase 6: Polish
1. Add OpenAI provider
2. Create example workflows
3. Write documentation
4. Comprehensive tests

---

## Verification Plan

1. **Unit tests**: Test each component in isolation
2. **Integration tests**: Test agent with zebra engine
3. **Example scenarios**:
   - Simple goal achievement
   - Multi-step workflow creation
   - Learning from failures
   - Guardrail escalation
4. **Run examples**: Execute example agents with real LLM calls
