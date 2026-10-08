## 1. Loader

- [x] 1.1 Copy top-level `result_key` into `ProcessDefinition.properties` (explicit `properties.result_key` wins)
- [x] 1.2 Loader tests

## 2. Creator

- [x] 2.1 Prompt: data flow, routing semantics, human decisions, side effects, worked example
- [x] 2.2 Temperature 0.3 and one repair attempt on parse/validation failure
- [x] 2.3 Creator tests (prompt content, repair success, repair failure, truncation not repaired)

## 3. Docs

- [x] 3.1 Update `specs/zebra-as-is.md` where it describes the creator / `result_key`
