## 1. Engine

- [x] 1.1 `_on_process_terminal` resumes every suspended task of the parent process waiting on the child

## 2. Actions

- [x] 2.1 Shared helper: start a child (bounded by `timeout`) and build a result from a `subflow_results` entry
- [x] 2.2 `subworkflow` suspends on its child (`wait: true`); `timeout` bounds the inline start
- [x] 2.3 `wait_subworkflow` suspends on a child of its process; fails for a non-child; warns on `timeout`
- [x] 2.4 `parallel_subworkflows` suspends on all children; keys on the task; `fail_fast` stops starting more
- [x] 2.5 Remove the polling loops

## 3. Tests & docs

- [x] 3.1 Unit tests: first run suspends, resume builds the legacy result, for all three actions
- [x] 3.2 Engine tests: child parked on a human task, parent resumes; `wait_subworkflow` on a `wait: false` child; parallel keys/routes; timeout
- [x] 3.3 `specs/zebra-as-is.md`, zebra-py / zebra-tasks AGENTS.md
