> Branch: `f189/dream-improvements`. Reference `#189` in commits.

## 1. Implementation

- [x] 1.1 `propose_zebra_improvements` action: gather inputs, skip when empty, LLM call, validate, cap, dedupe, start processes
- [x] 1.2 `zebra_improvement_request.yaml` system workflow with review human task
- [x] 1.3 Entry point; `dream_cycle.yaml` v7 step + "Improvements requested" summary section
- [x] 1.4 `/dreams/` lists requests (status, verdict, issue link, Review link) and per-cycle count

## 2. Tests & docs

- [x] 2.1 Action tests: request started, nothing-to-analyse no LLM call, cap, dedupe, bad JSON, missing provider/library
- [x] 2.2 Dream cycle definition tests; request workflow valid and system-tagged
- [x] 2.3 `/dreams/` page test with a request
- [x] 2.4 `specs/zebra-as-is.md`, package AGENTS docs
