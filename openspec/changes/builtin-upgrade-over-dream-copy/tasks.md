## 1. Fix

- [x] 1.1 `copy_builtin_workflows`: install a built-in over an older retired copy (rename it `<stem>.builtin-v<N>.yaml`), retire same-name active copies on every upgrade, log still-shadowed built-ins
- [x] 1.2 Tests in `zebra-agent/tests/test_library.py` for O1–O4
- [x] 1.3 Bump *Read Zebra Source* to v5 so the deploy replaces the broken prod dream copy (O5)

## 2. Docs and delivery

- [x] 2.1 Update `specs/zebra-as-is.md` and `zebra-agent/AGENTS.md`
- [ ] 2.2 Ruff, unit tests, CI green, merge
- [ ] 2.3 Outcome review after deploy
