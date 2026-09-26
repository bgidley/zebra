> Branch: `f118/ethics-fail-closed` (per fN/short-description). Reference `#118` in commits.

## 1. Implementation

- [x] 1.1 `_MAX_RESPONSE_TOKENS = 2000`; use it for the ethics LLM call
- [x] 1.2 `JSONDecodeError` branch: `approved: false`, route `reject`, resubmit concern, ERROR log
- [x] 1.3 Audit unparseable as `approved=false`, `check_type="kantian+unparseable"`, real `user_id`

## 2. Tests

- [x] 2.1 Update `test_handles_malformed_json` (business rule changed: fail closed)
- [x] 2.2 Truncated-JSON (prod case), audit record, and token-cap tests — verified failing before the fix
- [x] 2.3 Run lint + format (`uv run ruff check --fix . && uv run ruff format .`)

## 3. Docs & delivery

- [x] 3.1 `zebra-tasks/AGENTS.md` EthicsGateAction note; `specs/zebra-as-is.md` weakness removed
- [x] 3.2 Zebra feedback; push branch; green pipeline; merge; archive this change
