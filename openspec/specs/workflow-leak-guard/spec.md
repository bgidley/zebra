# workflow-leak-guard Specification

## Purpose
Keep run specifics (names, emails, domains, numbers, pasted run text) out of workflows written by an LLM: each writer checks the text it added against the untrusted texts it was shown, rewrites once to generalise, and the dream-cycle optimizer rejects what still copies run content (#237).

## Requirements

### Requirement: Leak check on added workflow text
`LeakGuard` SHALL report a hit for each string literal (mapping key or string value) of a generated workflow that is not in its parent and contains, outside `{{templates}}`: a phrase of at least 4 normalised tokens from the run texts, a phrase of at least 8 normalised tokens from the goal texts, or a name, email address, URL/email domain or number of at least 3 digits found in either. Text present in the parent workflow or in the writer's allow text (its system prompt and action list) SHALL NOT be reported.

#### Scenario: Name from a run
- **WHEN** a run text is "Update the Acme migration plan for Jane" and the new workflow adds a prompt "Check Acme's SLA with Jane"
- **THEN** the guard reports name hits for "Acme" and "Jane"

#### Scenario: Snake-case key
- **WHEN** a run text mentions "Acme" and the new workflow adds a task id `check_acme_sla`
- **THEN** the guard reports a name hit for "Acme"

#### Scenario: Already in the parent
- **WHEN** the parent workflow already contains "Acme" and the modified workflow keeps it
- **THEN** no hit is reported for "Acme"

#### Scenario: Topic words from the writer's own goal
- **WHEN** the creator's goal is "plan a birthday party for my friend" and the workflow's description is "Plan a birthday party"
- **THEN** no hit is reported

#### Scenario: Words Zebra itself supplied
- **WHEN** a goal mentions "Python" and "Python" appears in the writer's system prompt or action list
- **THEN** "Python" in the workflow is not reported

### Requirement: Generalise once, then reject or keep
Each LLM workflow writer (`workflow_creator`, `workflow_variant_creator`, `workflow_optimizer` create and modify) SHALL run the leak check before saving or staging a workflow. On hits it SHALL regenerate exactly once with an instruction to replace the listed specifics with `{{goal}}` or task inputs. If the regenerated workflow still has hits, the optimizer SHALL reject the change and save or stage nothing, while the creator and variant creator SHALL keep the rewrite and record the hits with `leak_guard.status` `kept`. If the check itself fails, the optimizer SHALL reject the change.

#### Scenario: Generalised on the second attempt
- **WHEN** the optimizer's first reply hard-codes a name from the sample failed goals and the second reply does not
- **THEN** the second workflow is saved (or staged for the golden gym) and the change records `leak_guard.status` `generalised` with the first attempt's hits

#### Scenario: Optimizer rejection
- **WHEN** both optimizer replies hard-code run specifics
- **THEN** nothing is saved or staged and `failed_changes` gains an entry whose reason starts "Leak guard" and whose `leak_hits` list the hits

#### Scenario: Creator keeps and records
- **WHEN** both creator (or variant creator) replies hard-code specifics from the goal
- **THEN** the task succeeds, the rewrite is added to the library and the output's `leak_guard` has status `kept` and the hits

#### Scenario: Guard failure in the dream cycle
- **WHEN** the leak check raises an error during an optimizer change
- **THEN** the change is rejected and nothing is saved

#### Scenario: Acronyms
- **WHEN** a sample failed goal mentions "SLA" and the optimizer's workflow says "SLA"
- **THEN** no hit is reported

### Requirement: Exposure recorded and rule stated
The evaluator SHALL record in its output `run_exposure`, the run texts it put in its prompt (sample failed goals, error types, continuation comments, capability-gap comments). The optimizer SHALL check against `run_exposure`. Every writer's prompt SHALL tell the LLM never to copy goals, names, numbers or outputs from runs into the YAML.

#### Scenario: Evaluator exposure
- **WHEN** the metrics analysis has a failure pattern with sample goal "Fix Jane's invoice" and a continuation comment "also email Bob"
- **THEN** the evaluation output's `run_exposure` contains both texts

#### Scenario: Rejections in the dream-cycle summary
- **WHEN** a dream cycle's optimizer rejects a change for leaks
- **THEN** the change appears under failed changes in the summary and on the dream-cycle page with its leak hits
