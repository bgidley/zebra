# Workflow Control-Flow Patterns in Zebra

This document describes how to implement the 43 Workflow Control-Flow Patterns from the [Workflow Patterns Initiative](http://www.workflowpatterns.com) using the Zebra workflow engine.

> **Reference**: Russell, N., ter Hofstede, A.H.M., van der Aalst, W.M.P., & Mulyar, N. (2006). "Workflow Control-Flow Patterns: A Revised View." BPM-06-22.

## Pattern Support Legend

- ✅ **Supported**: Fully supported in Zebra
- ⚠️ **Partial**: Partially supported or requires workarounds
- ❌ **Not Supported**: Not currently supported

---

## Basic Control-Flow Patterns

### ✅ WCP-1: Sequence

**Description**: An activity is enabled after completion of a preceding activity.

**Zebra Implementation**:

```yaml
name: "Sequence Example"
version: 1

tasks:
  verify_account:
    name: "Verify Account"
    action: prompt
    auto: false
    properties:
      prompt: "Verify the account details"

  process_payment:
    name: "Process Payment"
    action: prompt
    auto: false
    properties:
      prompt: "Process the payment"

routings:
  - from: verify_account
    to: process_payment
```

---

### ✅ WCP-2: Parallel Split (AND-split)

**Description**: A branch diverges into two or more parallel branches that execute concurrently.

**Zebra Implementation**:

```yaml
name: "Parallel Split Example"
version: 1

tasks:
  capture_enrolment:
    name: "Capture Enrolment"
    action: prompt
    auto: false

  create_profile:
    name: "Create Student Profile"
    action: prompt
    auto: false

  issue_confirmation:
    name: "Issue Confirmation"
    action: prompt
    auto: false

routings:
  - from: capture_enrolment
    to: create_profile
    parallel: true

  - from: capture_enrolment
    to: issue_confirmation
    parallel: true
```

---

### ✅ WCP-3: Synchronization (AND-join)

**Description**: Multiple branches converge, waiting for all branches to complete before proceeding.

**Zebra Implementation**:

```yaml
name: "Synchronization Example"
version: 1

tasks:
  start:
    name: "Start Order"

  check_invoice:
    name: "Check Invoice"
    action: prompt
    auto: false

  produce_invoice:
    name: "Produce Invoice"
    action: prompt
    auto: false

  despatch_goods:
    name: "Despatch Goods"
    synchronized: true
    action: prompt
    auto: false

routings:
  - from: start
    to: check_invoice
    parallel: true

  - from: start
    to: produce_invoice
    parallel: true

  - from: check_invoice
    to: despatch_goods

  - from: produce_invoice
    to: despatch_goods
```

---

### ✅ WCP-4: Exclusive Choice (XOR-split)

**Description**: One of several branches is chosen based on a condition.

**Zebra Implementation**:

```yaml
name: "Exclusive Choice Example"
version: 1

tasks:
  assess_volume:
    name: "Assess Volume"
    action: prompt
    auto: false
    properties:
      prompt: "Assess earth volume (small/large)"

  dispatch_bobcat:
    name: "Dispatch Bobcat"
    action: prompt
    auto: false

  dispatch_excavator:
    name: "Dispatch D9 Excavator"
    action: prompt
    auto: false

routings:
  - from: assess_volume
    to: dispatch_bobcat
    condition: route_name
    name: "small"

  - from: assess_volume
    to: dispatch_excavator
    condition: route_name
    name: "large"
```

**Notes**:
- Task `assess_volume` returns a result with `next_route` set to "small" or "large"
- Use `TaskResult.ok(output="result", next_route="small")` when completing the task

---

### ✅ WCP-5: Simple Merge (XOR-join)

**Description**: Multiple branches converge without synchronization; each activation passes through.

**Zebra Implementation**:

```yaml
name: "Simple Merge Example"
version: 1

tasks:
  payment_choice:
    name: "Choose Payment Method"
    action: prompt
    auto: false

  cash_payment:
    name: "Cash Payment"
    action: prompt
    auto: false

  credit_payment:
    name: "Credit Payment"
    action: prompt
    auto: false

  produce_receipt:
    name: "Produce Receipt"
    action: prompt
    auto: false

routings:
  - from: payment_choice
    to: cash_payment
    condition: route_name
    name: "cash"

  - from: payment_choice
    to: credit_payment
    condition: route_name
    name: "credit"

  - from: cash_payment
    to: produce_receipt

  - from: credit_payment
    to: produce_receipt
```

---

## Advanced Branching and Synchronization

### ⚠️ WCP-6: Multi-Choice (OR-split)

**Description**: One or more branches are activated based on independent conditions.

**Zebra Implementation**:

Partial support - requires multiple conditional routings from the same source task.

```yaml
name: "Multi-Choice Example"
version: 1

tasks:
  emergency_call:
    name: "Receive Emergency Call"
    action: prompt
    auto: false
    properties:
      prompt: "Type of emergency? (police/fire/ambulance - space separated)"

  despatch_police:
    name: "Despatch Police"
    action: prompt
    auto: false

  despatch_fire:
    name: "Despatch Fire"
    action: prompt
    auto: false

  despatch_ambulance:
    name: "Despatch Ambulance"
    action: prompt
    auto: false

routings:
  - from: emergency_call
    to: despatch_police
    condition: contains_police
    parallel: true

  - from: emergency_call
    to: despatch_fire
    condition: contains_fire
    parallel: true

  - from: emergency_call
    to: despatch_ambulance
    condition: contains_ambulance
    parallel: true
```

**Limitations**: Requires custom condition actions to evaluate each branch independently.

---

### ✅ WCP-7: Structured Synchronizing Merge

**Description**: Merges branches from a Multi-Choice, synchronizing only active branches.

**Zebra Implementation**:

```yaml
name: "Structured Synchronizing Merge"
version: 1

tasks:
  emergency_call:
    name: "Emergency Call"
    action: prompt
    auto: false

  despatch_police:
    name: "Despatch Police"
    action: prompt
    auto: false

  despatch_ambulance:
    name: "Despatch Ambulance"
    action: prompt
    auto: false

  transfer_patient:
    name: "Transfer Patient"
    synchronized: true
    action: prompt
    auto: false

routings:
  - from: emergency_call
    to: despatch_police
    parallel: true

  - from: emergency_call
    to: despatch_ambulance
    parallel: true

  - from: despatch_police
    to: transfer_patient

  - from: despatch_ambulance
    to: transfer_patient
```

**Notes**: Zebra's `synchronized: true` waits for all incoming branches. For true OR-join semantics (waiting only for active branches), additional logic may be needed.

---

### ⚠️ WCP-8: Multi-Merge

**Description**: Multiple branches merge without synchronization; each thread passes through independently.

**Status**: Requires verification - may need testing with concurrent execution.

---

### ❌ WCP-9: Structured Discriminator

**Description**: Waits for the first incoming branch, then proceeds (ignoring subsequent branches until reset).

**Status**: Not directly supported. Would require custom action implementation.

---

## Multiple Instance Patterns

### ⚠️ WCP-12: Multiple Instances without Synchronization

**Description**: Multiple instances of an activity execute without synchronization.

**Status**: Zebra supports multiple task instances via parallel branches, but dedicated multiple-instance constructs are not built-in.

---

### ❌ WCP-13: Multiple Instances with A Priori Design-Time Knowledge

**Description**: Known number of instances at design time, with synchronization.

**Status**: Not directly supported as a built-in pattern.

---

### ❌ WCP-14: Multiple Instances with A Priori Run-Time Knowledge

**Description**: Number of instances determined at runtime.

**Status**: Not directly supported.

---

### ❌ WCP-15: Multiple Instances without A Priori Knowledge

**Description**: Instances created dynamically during execution.

**Status**: Not directly supported.

---

## State-Based Patterns

### ❌ WCP-16: Deferred Choice

**Description**: The environment (not process logic) determines which branch executes.

**Status**: Not directly supported. All routing decisions in Zebra are made by task completion logic.

---

### ❌ WCP-17: Interleaved Parallel Routing

**Description**: Activities execute sequentially in any order (non-deterministic sequence).

**Status**: Not directly supported.

---

### ❌ WCP-18: Milestone

**Description**: An activity is only enabled when the process is in a specific state.

**Status**: Not directly supported.

---

## Cancellation Patterns

### ⚠️ WCP-19: Cancel Activity

**Description**: Cancel a specific activity before or during execution.

**Status**: Partial support - investigation needed into engine's task cancellation capabilities.

---

### ⚠️ WCP-20: Cancel Case

**Description**: Cancel an entire process instance.

**Status**: Partial support - process instances can be cancelled via the engine API, but not declaratively in YAML.

---

### ❌ WCP-25: Cancel Region

**Description**: Cancel a set of activities in a region.

**Status**: Not directly supported.

---

### ❌ WCP-26: Cancel Multiple Instance Activity

**Description**: Cancel all instances of a multiple-instance activity.

**Status**: Not directly supported.

---

### ❌ WCP-27: Complete Multiple Instance Activity

**Description**: Force early completion of multiple-instance activity.

**Status**: Not directly supported.

---

## Iteration Patterns

### ✅ WCP-10: Arbitrary Cycles

**Description**: Loops with multiple entry/exit points.

**Zebra Implementation**:

```yaml
name: "Arbitrary Cycle Example"
version: 1

tasks:
  start:
    name: "Start Process"

  review:
    name: "Review Document"
    action: prompt
    auto: false

  revise:
    name: "Revise Document"
    action: prompt
    auto: false

  approve:
    name: "Approve Document"
    action: prompt
    auto: false

routings:
  - from: start
    to: review

  - from: review
    to: approve
    condition: route_name
    name: "approved"

  - from: review
    to: revise
    condition: route_name
    name: "needs_revision"

  - from: revise
    to: review  # Loop back
```

---

### ⚠️ WCP-21: Structured Loop

**Description**: While/repeat loops with single entry/exit point.

**Zebra Implementation**:

```yaml
name: "Structured Loop Example"
version: 1

tasks:
  check_fuel:
    name: "Check Fuel Level"
    action: prompt
    auto: false

  production:
    name: "Run Production"
    action: prompt
    auto: false

  complete:
    name: "Complete"
    action: prompt
    auto: false

routings:
  - from: check_fuel
    to: production
    condition: route_name
    name: "has_fuel"

  - from: check_fuel
    to: complete
    condition: route_name
    name: "no_fuel"

  - from: production
    to: check_fuel  # Loop back
```

**Notes**: While and repeat loops can be modeled using conditional routing back to earlier tasks.

---

### ❌ WCP-22: Recursion

**Description**: An activity invokes itself or an ancestor.

**Status**: Not directly supported.

---

## Trigger Patterns

### ❌ WCP-23: Transient Trigger

**Description**: External trigger that is only valid if the activity is enabled at trigger time.

**Status**: Not directly supported.

---

### ❌ WCP-24: Persistent Trigger

**Description**: External trigger that persists until the activity becomes enabled.

**Status**: Not directly supported.

---

## Advanced Discriminator Patterns

### ❌ WCP-28: Blocking Discriminator

**Description**: Like discriminator but blocks additional threads until reset.

**Status**: Not directly supported.

---

### ❌ WCP-29: Cancelling Discriminator

**Description**: Like discriminator but cancels remaining branches after first completes.

**Status**: Not directly supported.

---

### ❌ WCP-30-32: Structured/Blocking/Cancelling Partial Join

**Description**: N-out-of-M join patterns.

**Status**: Not directly supported.

---

### ❌ WCP-33: Generalized AND-Join

**Description**: Flexible AND-join for highly concurrent processes.

**Status**: Not directly supported.

---

## Multiple Instance Join Patterns

### ❌ WCP-34: Static Partial Join for Multiple Instances

**Description**: N-out-of-M synchronization for multiple instances (known at design time).

**Status**: Not directly supported.

---

### ❌ WCP-35: Cancelling Partial Join for Multiple Instances

**Description**: N-out-of-M with cancellation of remaining instances.

**Status**: Not directly supported.

---

### ❌ WCP-36: Dynamic Partial Join for Multiple Instances

**Description**: N-out-of-M determined at runtime.

**Status**: Not directly supported.

---

## Advanced Synchronization Patterns

### ❌ WCP-37: Acyclic Synchronizing Merge

**Description**: OR-join using local semantics (no loops).

**Status**: Not directly supported.

---

### ❌ WCP-38: General Synchronizing Merge

**Description**: OR-join with non-local semantics (handles loops).

**Status**: Not directly supported.

---

## Concurrency Patterns

### ❌ WCP-39: Critical Section

**Description**: Mutual exclusion for activities.

**Status**: Not directly supported.

---

### ❌ WCP-40: Interleaved Routing

**Description**: Set of activities executed in sequence, one at a time, with arbitrary ordering.

**Status**: Not directly supported.

---

### ❌ WCP-41: Thread Merge

**Description**: Multiple threads coalesce into a single thread at a point in the process.

**Status**: May be supported implicitly through routing.

---

### ❌ WCP-42: Thread Split

**Description**: Single thread diverges into multiple threads at a point in the process.

**Status**: May be supported via parallel routing.

---

## Termination Patterns

### ✅ WCP-11: Implicit Termination

**Description**: Process terminates when no more work can be done.

**Zebra Implementation**:

Default behavior - a process completes when all tasks are complete and no tasks are waiting.

---

### ❌ WCP-43: Explicit Termination

**Description**: Specific activity explicitly terminates the process.

**Status**: Not directly supported. Workaround: route to a single end task that has no outgoing routings.

---

## Summary

**Total Patterns**: 43

**Supported**: 11 patterns (✅)
- WCP-1: Sequence
- WCP-2: Parallel Split
- WCP-3: Synchronization
- WCP-4: Exclusive Choice
- WCP-5: Simple Merge
- WCP-7: Structured Synchronizing Merge
- WCP-10: Arbitrary Cycles
- WCP-11: Implicit Termination
- WCP-21: Structured Loop (via cycles)

**Partial Support**: 6 patterns (⚠️)
- WCP-6: Multi-Choice (requires custom conditions)
- WCP-8: Multi-Merge (needs verification)
- WCP-12: Multiple Instances (via parallel branches)
- WCP-19: Cancel Activity
- WCP-20: Cancel Case

**Not Supported**: 26 patterns (❌)

---

## Extension Opportunities

Zebra could be extended to support additional patterns through:

1. **Multiple Instance Support**: Add dedicated multiple-instance task constructs with configurable synchronization
2. **Discriminator Patterns**: Implement first-wins semantics with various reset strategies
3. **Partial Join Patterns**: Add N-out-of-M synchronization constructs
4. **OR-Join**: Implement true OR-join with local or non-local semantics
5. **Deferred Choice**: Add environment-driven branching (e.g., timers, external events)
6. **Cancellation**: Expand cancellation support with region and activity-level control
7. **Critical Sections**: Add mutex/semaphore constructs for activity execution
8. **Explicit Termination**: Add explicit termination actions

---

## Resources

- [Workflow Patterns Website](http://www.workflowpatterns.com)
- [Original Patterns Paper](http://www.workflowpatterns.com/documentation/documents/BPM-06-22.pdf)
- [Zebra Workflow Engine Documentation](README.md)
