## Context

Three follow-ups from the Wave 1 outcome reviews (#267, #268, #270). All are small; most of the
change is tests.

## Decisions

### claude_code_build is context_dependent (not split)
Splitting `ship` / `merge` into their own action would change *Improve Zebra* and the builder
watcher for no gain: the stage is a task property, so `context_dependent` lets a trust gate's
assessment see it (a `patch` build is staged, a `merge` is not). Strict gym mode refuses it, which
is right: a gym run must never submit a builder job. Gate mode (`unsafe_reason` without `strict`)
still allows `context_dependent`, so no current workflow changes behaviour (none trust-gates or gyms
it). `REVERSIBLE_WRITERS` loses its entry; the new test
`test_no_always_reversible_action_submits_builds` refuses any `always_reversible` action whose
module calls `submit_build`, with no allowlist.

### Hints are declared on the registered class
The as-is spec already says "on its own class"; the test was looser. Inheritance hides decisions:
a new `_GitAction` subclass that pushes would silently be reversible. Each git action now sets its
hint, `_GitAction` sets none (it falls back to `TaskAction`'s `context_dependent`, the safe
default), and the test reads `vars(cls)` only.

### Restart test uses two subprocesses
`sys.executable -c` with a small script: process A creates the device and Zebra keys in a
`FileCredentialStore(key_dir)`, signs this device's `DEVICE_CERT`, prints npub, pubkeys and the
cert as JSON. Process B (fresh interpreter, same dir) reloads the keys, prints the npub and pubkeys
and checks `verify_device_chain(device_pub, zebra_pub, [cert])` itself. The test compares both and
re-verifies in the parent. No key material is printed: only public keys and the signed cert.

### Stamped / legacy runs
A small driver workflow `select (workflow_selector) → run (execute_goal_workflow)` on a real
`WorkflowEngine` and `WorkflowLibrary`, with a scripted LLM answering the selector and a stub `ok`
action in the goal workflow. Stamped = saved through `library.add_workflow` (has a block); legacy =
a YAML file written straight to the library dir.

## Risks
- Trust-gating `claude_code_build` now costs a low-tier LLM assessment instead of a short-circuit.
  No built-in workflow gates it today.
