## 1. Provenance

- [x] 1.1 `provenance.builtin_block(content_hash, sphere)`
- [x] 1.2 `copy_builtin_workflows` writes installed / upgraded built-ins with the built-in block
- [x] 1.3 Backfill: stamp an unmodified blockless installed built-in in place, mtime kept
- [x] 1.4 `restore()` keeps the block or re-derives it (built-in clean, else `foreign_users`)

## 2. Tests and docs

- [x] 2.1 Tests in `zebra-agent/tests/test_provenance.py` (install, upgrade, backfill, modified copy, restore); `test_library.py` built-in tests unchanged
- [x] 2.2 `specs/zebra-as-is.md`, `zebra-agent/AGENTS.md`
- [ ] 2.3 Post-deploy: read-only check in `zebra-web` that non-system built-ins carry a block with a hash
