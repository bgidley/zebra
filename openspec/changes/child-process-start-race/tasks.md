## 1. Diagnosis (read-only, prod)

- [x] 1.1 Step journal of the smoke goal and its child: two `process_started` events on the child
- [x] 1.2 Count children with a lost parent link; list recovery failures

## 2. Link children at creation

- [x] 2.1 `execute_goal_workflow` passes the parent link to `create_process`
- [x] 2.2 `subworkflow` and `parallel_subworkflows` do the same
- [x] 2.3 Tests: first stored state is linked; the goal queue never returns the child; one `process_started`

## 3. Recovery

- [x] 3.1 Recovery fails a process whose definition is missing, with a clear `__error__`
- [x] 3.2 Tests: missing definition fails; another process still recovers

## 4. Docs

- [x] 4.1 `specs/zebra-as-is.md` and package AGENTS.md notes
