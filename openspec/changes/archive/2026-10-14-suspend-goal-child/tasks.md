## 1. Engine

- [x] 1.1 Use `StateStore.list_child_processes()` (from #184; own method dropped at merge)
- [x] 1.2 `fail_process` fails every live child linked by `parent_process_id`

## 2. Goal workflow action

- [x] 2.1 `execute_goal_workflow` suspends on its child after the bounded inline start
- [x] 2.2 Build the result, task executions and progress events from the child on resume
- [x] 2.3 Remove the polling wait loop and its #183 timeout helper

## 3. Tests & docs

- [x] 3.1 Goal parked on the child's human task is not timed out; failing it fails the child
- [x] 3.2 Re-attach / recovery tests drive the suspended task; restarts do not count against it
- [x] 3.3 Engine test: a linked child no task waits on is failed with its parent
- [x] 3.4 `specs/zebra-as-is.md`, zebra-py / zebra-tasks / zebra-agent AGENTS.md
