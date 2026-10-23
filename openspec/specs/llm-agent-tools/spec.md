# llm-agent-tools Specification

## Purpose
TBD - created by archiving change llm-agent-workflow-tools. Update Purpose after archive.

## Requirements

### Requirement: Workflows declare an input schema
A workflow YAML MAY declare a top-level `inputs:` JSON Schema. The loader SHALL keep it in the definition's properties and the library SHALL expose it as `WorkflowInfo.inputs`. A workflow without `inputs:` SHALL be treated as taking `{goal: string}`.

#### Scenario: Declared inputs
- **WHEN** `read_web_page.yaml` declares `inputs` with a required `url`
- **THEN** its tool definition's parameters are that schema

#### Scenario: Default inputs
- **WHEN** a workflow has no `inputs:`
- **THEN** its tool definition requires a single string `goal`

### Requirement: llm_agent calls workflows as tools
The `llm_agent` action SHALL offer the workflows named in `tools`, plus up to `max_tag_tools` workflows matching any of `tool_tags` ranked by `success_rate`, as LLM tools (system workflows excluded from tag selection). Each tool call SHALL create a child process of the calling process (`parent_task_id` = the task) with the tool arguments as properties, and the task SHALL suspend until the children finish. Tool results SHALL be fed back to the model and the loop SHALL repeat until the model returns text without tool calls.

#### Scenario: Web research
- **WHEN** an `llm_agent` task with `tools: ["Web Research"]` gets a `tool_use` for `web_research`
- **THEN** a *Web Research* child process runs with the query as `goal`, the task resumes with its `summary`, and the model's final text is the task output

#### Scenario: Unknown tool
- **WHEN** the model calls a tool name that is not offered
- **THEN** the model receives an error tool result naming the available tools and no child is spawned

### Requirement: Tool calls are bounded and tracked
`llm_agent` SHALL stop after `max_tool_turns` model turns that request tools and fail the task, and SHALL run at most `max_parallel_tools` tool calls per turn, answering the rest with an error tool result. The transcript (tool name, arguments, child process id, success, result excerpt) SHALL be in the task output. Each child's `__total_cost__`, `__total_tokens__` and `__token_history__` SHALL be added to the calling process. An `llm_agent` running at `__agent_depth__` >= `max_depth` SHALL run without tools.

#### Scenario: Turn limit
- **WHEN** the model keeps requesting tools past `max_tool_turns`
- **THEN** the task fails with a message naming the limit

#### Scenario: Too many calls in one turn
- **WHEN** the model makes three tool calls in one turn with `max_parallel_tools: 2`
- **THEN** two children run and the third call gets an error result

#### Scenario: Cost roll-up
- **WHEN** a tool child spent $0.02
- **THEN** the calling process's `__total_cost__` grows by $0.02 plus the agent's own calls

### Requirement: The model can define new workflows
With `allow_define_workflow: true`, `llm_agent` SHALL offer a `define_workflow(goal, suggested_name)` tool that runs the *Define Workflow* system workflow as a subflow: an ethics gate on the request, then `workflow_creator`, which validates the workflow and saves it to the library tagged `llm-defined`. The created workflow SHALL be offered as a tool on the following turns.

#### Scenario: Define then use
- **WHEN** the model calls `define_workflow` and the subflow saves "Haiku Writer"
- **THEN** the next model turn offers `haiku_writer` and calling it runs the new workflow

#### Scenario: Ethics rejects
- **WHEN** the ethics gate rejects the request
- **THEN** the define subflow fails, nothing is saved, and the model receives the rejection as an error tool result

### Requirement: Graceful degradation
If `__workflow_library__` is missing from `context.extras`, `llm_agent` SHALL log a warning and run as a plain LLM call without tools.

#### Scenario: No library
- **WHEN** `llm_agent` runs without a library
- **THEN** it returns the model's text and spawns no children

### Requirement: JSON answers are checked
An `llm_agent` task with `response_format: json` SHALL parse its final answer leniently (code fences, JSON in prose) and SHALL accept only a JSON object or array. When the answer cannot be parsed, or is a bare string or number, it SHALL ask once more without tools, appending a JSON-only instruction, or, when the reply was cut off at the token limit, a request to be brief with twice `max_tokens`. When the second answer cannot be parsed either the task SHALL fail with the cause and SHALL NOT write `output_key`. Text answers are unchanged.

#### Scenario: Junk answer is retried
- **WHEN** the model's final answer is `" the"` and its retry is a valid JSON object
- **THEN** the task succeeds with the parsed object in `output_key`, and the retry was sent with no tools and a JSON-only instruction

#### Scenario: Answer that stays junk fails the task
- **WHEN** the final answer and the retry both cannot be parsed as JSON
- **THEN** the task fails with an error naming invalid JSON and 2 attempts and quoting the start of the reply, and `output_key` is not set

#### Scenario: Bare JSON value is not an answer
- **WHEN** the final answer is the JSON string `"the"` and its retry is a valid JSON object
- **THEN** the retry note says an object was expected, and the task stores the object

#### Scenario: Truncated twice fails
- **WHEN** the final answer and its retry are both cut off at the token limit
- **THEN** the task fails with an error naming the truncation and 2 attempts

#### Scenario: Truncated answer gets more room
- **WHEN** the final answer cannot be parsed and its `finish_reason` is `length`
- **THEN** the retry asks for twice `max_tokens` and to keep the answer brief

#### Scenario: Text answers unchanged
- **WHEN** `response_format` is not `json`
- **THEN** the final answer is stored as text without a retry
