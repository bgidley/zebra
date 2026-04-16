# Plan: Write Zebra Agent Requirements Specification

## Context

Zebra is currently a workflow-based AI agent system focused on code development. The vision is to transform it into a **general-purpose AI life partner** — a collaborative peer that helps run your life, work on code, and jointly succeed with its human. Not a servant, but an equal partner and AI member of the family.

This plan covers creating the **requirements specification document** as the first deliverable. Design and coding come later.

### User's Design Choices
- **Domains**: Broad — all major life domains from the start
- **Partnership**: Collaborative peer — proposes goals, prioritises, negotiates disagreements
- **Interface**: Multi-modal — chat, web dashboard, CLI, notifications
- **Data**: Hybrid — local core memory, encrypted cloud sync for cross-device
- **Autonomy**: High — acts independently on routine tasks, learns trust boundaries
- **Users**: Personal first, extensible to family/team
- **Ethics**: Values-aligned — understands user's values, reasons about dilemmas, flags concerns

## Approach

Create a requirements specification document (`docs/requirements.md`) in the repository. The document uses numbered requirements (REQ-xxx) with priority levels (P1/P2/P3) and testable acceptance criteria. Structure follows the existing system's strengths (everything-is-a-workflow, entry-point extensibility) while defining new capabilities.

## What We'll Create

**Single file**: `docs/requirements.md` — the complete requirements specification

## Document Structure

### 1. Vision & Purpose
- One-paragraph vision statement
- Core XP values applied: simplicity, communication, feedback, courage, respect
- What "collaborative peer" means concretely (not a servant, not a boss)

### 2. Glossary
- Key terms: Agent, Human, Goal, Domain, Trust Level, Values Profile, Workflow, Task Action

### 3. User Profiles
- Primary: Single human user with personal agent (P1)
- Future: Family/household with shared agent (P3)
- Future: Team/organisation (P3)
- Design constraint: data model must namespace per-user from day one

### 4. Core Principles (non-negotiable)
- **Everything is a workflow** — preserves existing architectural strength
- **Domains as plugins** — new life areas added via entry-point pattern
- **Trust is earned** — graduated autonomy per domain
- **Values over rules** — ethics aligns with human's values
- **Local-first data** — personal knowledge stays local by default
- **Proactive, not just reactive** — agent initiates and suggests

### 5. Trust & Autonomy Model
Three trust levels per domain (SUPERVISED / SEMI-AUTONOMOUS / AUTONOMOUS) with:
- Task action reversibility classification
- Per-domain trust levels starting at SUPERVISED
- Explicit promotion/demotion by human
- Trust gates as workflow steps for visibility

### 6. Values-Aligned Ethics Framework
Extends current Kantian ethics gates with:
- Values Profile — structured record of human's values
- Values alignment in ethics reasoning
- Proactive concern flagging
- Dilemma escalation when values conflict

### 7. Collaborative Peer Interaction Model
- Agent proposes goals unprompted
- Explains reasoning for recommendations
- Can push back with reasons
- Structured disagreement protocol
- Consistent personality and long-term memory

### 8. Memory & Knowledge System
Three tiers: Working (exists), Episodic (exists), Personal Knowledge (NEW)

### 9. Multi-Modal Interface
Web dashboard (P1), Chat (P1), CLI (P1), Notifications (P2)

### 10. Domain Specifications
8 domains: Code (P1, exists), Scheduling (P1), Research (P1), Finance (P2), Health (P2), Home (P3), Creative (P3), Social (P3)

### 11. Data Model & Privacy
Local-first, encrypted cloud sync opt-in, data export, context minimisation

### 12. External Integrations
IntegrationProvider interface, entry-point pattern, OAuth2, MCP

### 13. Non-Functional Requirements
Performance, crash recovery, budget controls, observability, offline capability

### 14. Phased Delivery
Phase 1 (Foundation), Phase 2 (Expansion), Phase 3 (Full Vision)

## Key Files (Existing Code to Preserve/Extend)

| File | Status |
|---|---|
| `zebra-py/zebra/core/engine.py` | Preserve |
| `zebra-tasks/zebra_tasks/` (28 actions) | Extend |
| `zebra-tasks/zebra_tasks/agent/ethics_gate.py` | Extend |
| `zebra-agent/zebra_agent/storage/interfaces.py` | Extend |
| `zebra-agent/zebra_agent/budget.py` | Extend |
| `zebra-agent/workflows/agent_main_loop.yaml` | Extend |
| `zebra-agent-web/zebra_agent_web/` | Extend |

## Implementation Steps

1. Create `docs/` directory in project root
2. Write `docs/requirements.md` with all sections, fully fleshed out with numbered requirements (REQ-xxx), priorities, and testable acceptance criteria
3. Review with user for feedback and iteration

## Verification
- Every requirement has a priority (P1/P2/P3) and testable acceptance criteria
- All existing capabilities accounted for (preserve or extend)
- Phased delivery is realistic, each phase independently valuable
- XP values reflected throughout