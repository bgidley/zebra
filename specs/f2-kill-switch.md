---
name: f2-kill-switch
description: Kill switch implementation — persisted halted flag, web endpoint, daemon awareness, CLI command
metadata:
  type: feature-spec
  issue: "#2"
  requirement: REQ-TRUST-007
  status: implemented
---

# F2: Kill Switch

**GitLab issue**: #2  
**Requirement**: REQ-TRUST-007  
**Status**: Implemented

## Goal & scope

One-click web endpoint + management command that halts every process outside the engine. A persisted `halted` flag blocks daemon pickup; in-flight tasks are aborted at the next poll cycle.

Out of scope: hardware/OS-level watchdog (Phase 2 risk item).

## Data model changes

New table `zebra_system_state` via migration `0008_kill_switch_system_state.py`:

```python
class SystemStateModel(models.Model):  # singleton, pk=1
    halted = models.BooleanField(default=False)
    halted_at = models.DateTimeField(null=True, blank=True)
    halted_reason = models.CharField(max_length=500, blank=True)
```

(The model also carries F4 identity fields added in a later migration.)

## API / interface changes

**REST endpoint**: `GET|POST /api/kill-switch/`  
- `GET` returns `{halted, halted_at, halted_reason}`  
- `POST {action: "halt"|"resume", reason: "..."}` sets/clears the flag  
- Listed in `_ALWAYS_ALLOWED` — reachable without auth (intentional: emergency access)

**Management command**: `python manage.py kill_switch --halt|--resume|--status [--reason TEXT]`  
Key file: `zebra_agent_web/api/management/commands/kill_switch.py`  
Uses synchronous `set_halted_sync` / `get_status_sync` helpers.

**Helper module**: `zebra_agent_web/api/kill_switch.py`  
Provides async (`is_halted`, `set_halted`, `get_status`) and sync (`is_halted_sync`, `set_halted_sync`, `get_status_sync`) variants.

## Control flow

1. `_tick()` in `daemon.py` calls `is_halted()` **before** `pick_next()` — skips goal pickup entirely if halted.
2. After starting a process, `_tick()` re-checks `is_halted()` on every 2-second poll.
3. If the switch is activated mid-flight, `engine.fail_process()` is called, aborting the in-flight run.

## Configuration

None — the flag is stored in the DB singleton; no env var needed.

## Open questions / risks

- **Auth bypass is intentional** but widens attack surface — a malicious request could trigger halt. Mitigation: the separate-token approach from the to-be design (Phase 2) would harden this.
- **Kill switch does not cancel in-progress LLM HTTP calls** — it aborts at the next poll boundary (≤2 s), not immediately.
- **No audit record** of who activated it (changed_by is not stored). The to-be design calls for an `AuditEntry`; not yet implemented.
