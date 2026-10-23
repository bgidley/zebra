## 1. Fix

- [x] 1.1 Extract `install_builtin_workflows()` in `agent_engine.py` and drop the eviction of stored definitions
- [x] 1.2 Regression tests with the real Outcome Review v3 fixture: render and complete after v4 ships (fail with the eviction restored)

## 2. Docs and delivery

- [x] 2.1 Update `specs/zebra-as-is.md` and `zebra-agent-web/AGENTS.md`
- [x] 2.2 Ruff, unit tests, CI green, merge
- [ ] 2.3 Outcome review after deploy
