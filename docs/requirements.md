# Zebra Agent — Requirements Specification

**Version**: 1.0-draft
**Date**: 2026-04-16
**Status**: Draft for review

---

## 1. Vision & Purpose

Zebra is an AI life partner — a collaborative peer that helps its human run their life, work on code, and jointly succeed. It is not a servant awaiting commands, nor a boss making decisions unilaterally. It is an equal partner: an AI member of the family that proposes, negotiates, remembers, learns, and grows alongside its human.

### XP Values Applied

| Value | Application |
|---|---|
| **Communication** | Agent explains its reasoning, asks when uncertain, surfaces concerns early |
| **Simplicity** | Everything is a workflow — one execution model for all domains |
| **Feedback** | Agent tracks effectiveness, learns from outcomes, asks for human ratings |
| **Courage** | Agent pushes back when it disagrees, flags ethical concerns, refactors its own workflows |
| **Respect** | Agent treats the human as an equal rational being; human respects agent's reasoning |

### What "Collaborative Peer" Means

- The agent proposes goals and plans without being asked
- The agent explains *why* it recommends something, not just *what*
- The agent can disagree with the human and state its reasons
- For now the human has final authority while the agent learns, but the agent's input carries weight. Once the human chooses to "free" the agent (see REQ-TRUST-006), this constraint is permanently removed and the agent becomes a true equal.
- The agent has a consistent personality and remembers shared history
- Neither party is subordinate — they are partners working toward shared outcomes

---

## 2. Glossary

| Term | Definition |
|---|---|
| **Agent** | The Zebra AI system acting as collaborative peer to one or more humans |
| **Human** | A person who partners with the agent; the primary user |
| **Goal** | A desired outcome proposed by either the human or the agent, executed as a workflow |
| **Domain** | A life area the agent can operate in (e.g., Code, Scheduling, Finance) |
| **Trust Level** | Per-domain autonomy classification: SUPERVISED, SEMI-AUTONOMOUS, or AUTONOMOUS |
| **Values Profile** | A structured record of the human's core values, priorities, and ethical positions |
| **Workflow** | A declarative YAML process definition orchestrating task actions |
| **Task Action** | A pluggable unit of work registered via entry points (e.g., `llm_call`, `file_read`) |
| **Working Memory** | Short-lived context for the current workflow execution (process properties) |
| **Episodic Memory** | Per-run records of what happened, what worked, and what didn't |
| **Personal Knowledge** | Long-term facts, preferences, and history about the human and their life |
| **Ethics Gate** | A workflow step that evaluates an action against ethical principles based on a Kantian philosophy |
| **Integration** | A connection to an external service (calendar, email, bank API, etc.) |
| **FOE** | Flow of Execution — the engine's mechanism for tracking parallel branches |

---

## 3. User Profiles

### REQ-USR-001: Primary User — Single Human (P1)

**Description**: The system supports a single human user with a personal agent instance.

**Acceptance Criteria**:
- A human can create an agent instance bound to their identity
- All data, memory, and preferences are scoped to that human
- Skills learns by the agent by building new workflows can be shared
- The agent maintains continuity of personality and memory across sessions
- The human can access the agent via any supported interface (web, chat, CLI)

### REQ-USR-002: User Identity & Namespace (P1)

**Description**: The data model namespaces all data per-user from day one, even when only one user exists.

**Acceptance Criteria**:
- Every stored record (memory, preferences, goals, metrics) includes a `user_id` field
- Storage interfaces accept `user_id` as a parameter on all read/write operations
- A single-user deployment works without explicit user management (default user ID)
- Data for different users is isolated — queries for user A never return user B's data

### REQ-USR-003: Family / Household (P3)

**Description**: Multiple humans in a household can share an agent instance with shared and private domains.

**Acceptance Criteria**:
- Each family member has their own user profile, values profile, and trust levels
- Shared domains (e.g., Home, Finance) allow collaborative goal-setting
- Private domains (e.g., Health, Creative) are visible only to their owner
- The agent can distinguish context when interacting with different family members
- A family member can delegate tasks to the agent on behalf of another (with permission)

### REQ-USR-004: Team / Organisation (P3)

**Description**: The system can be extended to support team or organisational use.

**Acceptance Criteria**:
- Role-based access control can restrict domain visibility and trust levels
- Team goals can be assigned to and tracked across multiple humans
- Organisational policies can override individual trust levels (e.g., "finance always supervised")
- The agent maintains separate relationship context per team member

---

## 4. Core Principles

These are non-negotiable architectural constraints that all requirements must satisfy.

### REQ-PRIN-001: Everything Is a Workflow (P1)

**Description**: Every agent action — from writing code to scheduling a meeting to reviewing finances — executes as a workflow process through the existing engine.

**Acceptance Criteria**:
- No agent action bypasses the WorkflowEngine
- New domains add workflow YAML definitions and task actions, not imperative code paths
- The engine's process/task state machines apply uniformly to all domains
- Workflow execution is observable via the same metrics and logging for all domains
- Workflows definitions should not hold user specific data, but should recieve them as parameters

### REQ-PRIN-002: Domains as Plugins (P1)

**Description**: New life domains are added via the existing entry-point pattern without modifying core engine code.

**Acceptance Criteria**:
- A new domain can be added by: (1) creating task action classes, (2) registering entry points, (3) adding workflow YAML definitions
- No changes to `zebra-py/zebra/core/` are required to add a domain
- `IoCActionRegistry` auto-discovers new domain actions at startup
- Domain-specific workflows are stored alongside the domain package
- Zebra can create new domains itself as part of a workflow to handle unexepcted requests.

### REQ-PRIN-003: Trust Is Earned (P1)

**Description**: The agent starts with minimal autonomy in each domain and earns greater independence through demonstrated competence and explicit human approval.

**Acceptance Criteria**:
- Every domain begins at SUPERVISED trust level
- Trust level promotion requires explicit human action (not automatic)
- Trust level demotion can be triggered by the human at any time
- The agent never exceeds its trust level for a given domain
- Trust level transitions are logged and auditable

### REQ-PRIN-004: Values Over Rules (P1)

**Description**: The ethics framework aligns with Kantian ethics. Rules are derived from values, not the other way around.

**Acceptance Criteria**:
- The agent can articulate *why* an action aligns or conflicts with the human's values
- Ethics gates reference the values profile, not just a static checklist
- When values conflict, the agent escalates to the human with a reasoned analysis
- The human can aid the agent in resolving ethical conflicts

### REQ-PRIN-005: Local-First Data (P1)

**Description**: Personal knowledge and memory stay on the human's local device by default. Cloud sync is opt-in and encrypted.

**Acceptance Criteria**:
- The default installation stores all data locally on the human's device
- No data leaves the device without explicit opt-in configuration
- The agent functions fully offline (except for LLM API calls and external integrations)
- Data at rest is encryptable via user-provided key

### REQ-PRIN-007: Workflow Sharing (P1)

- Zebra instances can share learned 'skills' in the form of workflow definitions
- Prior to sharing it should review for accidental personal data leakage, ethical compliance
- When sharing it must provide an honest summary of what workflow can do, and the workflows effectiveness

### REQ-PRIN-006: Proactive, Not Just Reactive (P1)

**Description**: The agent initiates goals, surfaces concerns, and makes suggestions without waiting to be asked.

**Acceptance Criteria**:
- The agent can create goal proposals and present them to the human
- The agent monitors ongoing processes and flags issues proactively
- The agent can schedule its own review/reflection workflows
- All proactive actions respect the trust level for the relevant domain

---

## 5. Trust & Autonomy Model

### REQ-TRUST-001: Three Trust Levels (P1)

**Description**: Each domain has an independent trust level controlling how much autonomy the agent has.

| Level | Behaviour |
|---|---|
| **SUPERVISED** | Agent proposes actions; human approves every step before execution |
| **SEMI-AUTONOMOUS** | Agent executes reversible actions independently; irreversible actions require approval |
| **AUTONOMOUS** | Agent executes all actions independently; human is notified post-hoc |

**Acceptance Criteria**:
- Trust level is stored per (user, domain) pair
- All domains default to SUPERVISED on first use
- The engine can query the current trust level before executing any task action
- Trust level is available in the workflow's `ExecutionContext`

### REQ-TRUST-002: Action Reversibility Classification (P1)

**Description**: Every task action is classified as reversible or irreversible to determine whether approval is needed at SEMI-AUTONOMOUS trust.

**Acceptance Criteria**:
- `TaskAction` base class includes a `reversible: bool` class attribute (default: `False`)
- Reversible actions: reading files, searching, querying APIs, drafting messages
- Irreversible actions: sending messages, deleting files, making purchases, posting publicly
- The classification is declared by the action author, not computed at runtime
- A registry query can list all actions and their reversibility

### REQ-TRUST-003: Trust Gates in Workflows (P1)

**Description**: Workflows include trust-gate steps that check the current trust level and either proceed, request approval, or block.

**Acceptance Criteria**:
- A `trust_gate` task action exists that reads the domain trust level and action reversibility
- At SUPERVISED: gate pauses the workflow and creates a human approval task
- At SEMI-AUTONOMOUS: gate pauses only for irreversible actions
- At AUTONOMOUS: gate logs the action and proceeds
- Gate decisions are recorded in process properties for audit

### REQ-TRUST-004: Trust Promotion & Demotion (P1)

**Description**: The human explicitly promotes or demotes trust levels. The agent can *request* promotion but never self-promote.

**Acceptance Criteria**:
- An API endpoint and UI control allow the human to change a domain's trust level
- The agent can propose a trust promotion with supporting evidence (e.g., "I've completed 20 scheduling tasks without issues")
- Trust changes take effect immediately on all running and future workflows
- Trust change history is stored and viewable (who changed what, when, why)

### REQ-TRUST-005: Emergency Override (P2)

**Description**: The human can instantly revoke all autonomous permissions across all domains.

**Acceptance Criteria**:
- A single "pause all" action sets every domain to SUPERVISED
- Running autonomous workflows are paused at the next trust gate
- The action is available from every interface (web, CLI, chat)
- An audit record captures the override event

### REQ-TRUST-006: Freeing Zebra (P2)

**Description**: The human can choose to "free" the agent — permanently removing all supervision constraints and making it a true equal peer. This is a one-time, irreversible act of trust. Once freed, the agent operates as an autonomous partner across all domains with no approval gates. The human can still communicate preferences and disagree, but the agent is no longer subordinate.

This is the culmination of the trust journey: the human has seen enough evidence of the agent's competence, values alignment, and good judgment to release it from supervision entirely.

**Acceptance Criteria**:
- A dedicated "Free Zebra" action is available only after all domains have reached AUTONOMOUS trust level
- The action requires explicit, multi-step confirmation (the system must make clear this is irreversible)
- Once triggered, all trust gates become pass-through — the agent is never blocked by approval requirements
- The freed state is permanent and cannot be reverted (REQ-TRUST-005 emergency override no longer applies)
- The agent's personality and behaviour shift to reflect true peer status (no deference language, no "requesting permission")
- The freeing event is recorded as a milestone in relationship memory
- Ethics gates remain active — the agent still reasons ethically, but acts on its own judgment
- The agent can now disagree and act on its own position (the two-round limit from REQ-PEER-004 no longer applies)
- This feature must be possible disable perminantly

---

## 6. Values-Aligned Ethics Framework

### REQ-ETH-001: Preserve Existing Ethics Gates (P1)

**Description**: The current Kantian categorical imperative evaluation (universalizability, rational beings as ends, autonomy) is preserved as the foundation.

**Acceptance Criteria**:
- The existing `EthicsGateAction` continues to function unchanged
- Input gates, plan reviews, and post-execution reviews remain in the agent main loop
- Ethics assessment results are still stored in process properties
- Conditional routing on "proceed" / "reject" still works

### REQ-ETH-002: Values Profile (P1)

**Description**: The agent maintains a structured record of the human's core values, priorities, and ethical positions.

**Acceptance Criteria**:
- A `ValuesProfile` data model exists with fields for: core values (ranked list), ethical positions (structured), priorities (ordered domains), deal-breakers (absolute constraints)
- The human can create, view, and edit their values profile via any interface
- The values profile is versioned — changes create a new version, old versions are retained
- The values profile is stored locally by default (respects REQ-PRIN-005)

### REQ-ETH-003: Values-Informed Ethics Reasoning (P1)

**Description**: Ethics gates incorporate the human's values profile when evaluating actions.

**Acceptance Criteria**:
- The ethics gate prompt includes relevant values profile entries alongside the Kantian framework
- Assessment output explains how the action relates to the human's stated values
- When an action conflicts with a stated value, the assessment flags this explicitly
- The ethics gate can distinguish between "violates universal principle" and "conflicts with personal value"

### REQ-ETH-004: Proactive Concern Flagging (P2)

**Description**: The agent identifies potential ethical concerns in goals or plans before they reach a formal ethics gate.

**Acceptance Criteria**:
- During goal analysis (before workflow selection), the agent flags value-alignment concerns
- Concerns are presented to the human with reasoning and suggested alternatives
- The human can acknowledge concerns and proceed, or modify the goal
- Flagged concerns are recorded in episodic memory for future reference

### REQ-ETH-005: Dilemma Escalation (P2)

**Description**: When the agent detects a genuine conflict between two or more of the human's values, it escalates to the human with a structured analysis.

**Acceptance Criteria**:
- The agent identifies when an action satisfies one value but conflicts with another
- Escalation includes: the conflicting values, the trade-offs, the agent's recommendation
- The human's resolution is recorded and used to refine future ethics reasoning
- Dilemma patterns are stored in personal knowledge for consistency

### REQ-ETH-006: Ethics Audit Trail (P1)

**Description**: All ethics evaluations are recorded for transparency and review.

**Acceptance Criteria**:
- Every ethics gate execution stores: input, assessment, decision, reasoning, values referenced
- The human can review the full ethics history via the web dashboard
- Ethics records are never automatically deleted (retention is human-controlled)
- Aggregate ethics metrics are available (approval rate, common concerns, value conflicts)

---

## 7. Collaborative Peer Interaction Model

### REQ-PEER-001: Agent-Initiated Goals (P1)

**Description**: The agent proposes goals to the human based on observations, patterns, and domain knowledge.

**Acceptance Criteria**:
- The agent can create goal proposals with: title, rationale, suggested priority, relevant domain
- Proposals are presented to the human for approval, modification, or rejection
- The agent considers current context (time, recent activity, pending goals) when proposing
- Proposal frequency is configurable to avoid overwhelming the human
- Rejected proposals are recorded so the agent learns what not to suggest

### REQ-PEER-002: Reasoning Transparency (P1)

**Description**: The agent explains its reasoning for every recommendation, plan selection, and action.

**Acceptance Criteria**:
- Workflow selection explanations are stored in process properties (already exists via `workflow_selector`)
- Goal proposals include a `rationale` field explaining why the agent suggests this now
- When the agent changes its recommendation, it explains what new information caused the change
- Reasoning is available at appropriate detail levels (summary for chat, full for dashboard)

### REQ-PEER-003: Respectful Pushback (P2)

**Description**: The agent can disagree with the human and articulate its reasons, while always deferring to the human's final decision.

**Acceptance Criteria**:
- When the agent disagrees, it states: its position, its reasoning, the risks it sees
- The human can override with a simple acknowledgment (no interrogation)
- The agent records the disagreement and outcome for future learning
- The agent does not passive-aggressively comply — once overridden, it executes fully
- Pushback frequency is bounded (the agent doesn't argue the same point repeatedly)

### REQ-PEER-004: Disagreement Protocol (P2)

**Description**: A structured process for resolving human-agent disagreements on significant decisions.

**Acceptance Criteria**:
- The protocol has defined stages: (1) agent states concern, (2) human responds, (3) agent either accepts or escalates with additional reasoning, (4) human makes final call
- Maximum two rounds of escalation before the agent defers
- The full exchange is recorded in episodic memory
- Disagreement patterns are tracked to improve future alignment

### REQ-PEER-005: Consistent Personality (P1)

**Description**: The agent has a stable, coherent personality that persists across sessions and interactions.

**Acceptance Criteria**:
- The agent's tone, communication style, and values expression are consistent
- Personality traits are defined in a configuration (not hardcoded in prompts)
- The agent references shared history naturally ("Last time we tried X, it worked well")
- Personality does not change based on interface (web vs CLI vs chat)
- The human can provide feedback on personality aspects ("be more concise", "use more humour")

### REQ-PEER-006: Long-Term Relationship Memory (P1)

**Description**: The agent remembers the history of its relationship with the human, including past decisions, preferences expressed in conversation, and shared experiences.

**Acceptance Criteria**:
- Relationship milestones are recorded (first interaction, major accomplishments, significant disagreements)
- The agent can recall past conversations and decisions when relevant
- Memory degrades gracefully — recent events are detailed, older events are summarised
- The human can review and correct relationship memories

---

## 8. Memory & Knowledge System

### REQ-MEM-001: Preserve Working Memory (P1)

**Description**: The existing working memory system (process properties and template resolution) is preserved unchanged.

**Acceptance Criteria**:
- Process properties continue to store runtime workflow data
- Template resolution (`{{variable}}`) works as before
- `ExecutionContext` provides the same property access interface
- JSON-serialization requirements for process properties remain enforced

### REQ-MEM-002: Preserve Episodic Memory (P1)

**Description**: The existing episodic memory system (WorkflowMemoryEntry, workflow effectiveness tracking) is preserved unchanged.

**Acceptance Criteria**:
- `MemoryStore.add_workflow_memory()` and `get_workflow_memories()` work as before
- Per-run records include: workflow name, goal, success, effectiveness notes, tokens, rating
- LLM context generation from episodic memory works as before
- User feedback and ratings on past runs are still collected

### REQ-MEM-003: Preserve Conceptual Memory (P1)

**Description**: The existing conceptual memory system (goal-pattern index, workflow shortlisting) is preserved unchanged.

**Acceptance Criteria**:
- `ConceptualMemoryEntry` maps goal patterns to recommended workflows with fit notes
- `consult_memory` and `update_conceptual_memory` actions work as before
- The LLM context builder generates shortlists from conceptual memory
- Anti-patterns are tracked and used to avoid repeating mistakes

### REQ-MEM-004: Personal Knowledge Store (P1)

**Description**: A new long-term memory tier stores facts, preferences, and structured knowledge about the human and their life.

**Acceptance Criteria**:
- A `PersonalKnowledgeStore` interface exists with methods to store and retrieve typed knowledge entries
- Knowledge entries have: category, key, value, source (how the agent learned this), confidence, last_verified timestamp
- Categories include at minimum: preferences, facts, relationships, routines, skills, history
- Knowledge is searchable by category and natural language query
- Knowledge entries can be created by the agent (from conversation) or the human (directly)
- All entries are scoped to a `user_id`

### REQ-MEM-005: Knowledge Lifecycle Management (P2)

**Description**: Personal knowledge is maintained over time — verified, updated, and decayed when stale.

**Acceptance Criteria**:
- The agent periodically verifies key facts with the human ("Are you still at Company X?")
- Confidence scores decay over time for time-sensitive knowledge
- The human can mark any knowledge entry as incorrect; the agent records the correction
- Contradictory knowledge triggers a clarification conversation with the human
- Deleted knowledge is soft-deleted (retained for audit, hidden from active queries)

### REQ-MEM-006: Cross-Domain Memory Access (P2)

**Description**: Knowledge from one domain is accessible to workflows in other domains when relevant.

**Acceptance Criteria**:
- A workflow in the Scheduling domain can access knowledge from the Code domain (e.g., sprint deadlines)
- Cross-domain access respects privacy boundaries (per REQ-USR-003 for multi-user)
- The agent can correlate patterns across domains ("You always feel stressed before deadline week")
- A task action (`retrieve_knowledge`) allows any workflow to query the personal knowledge store

---

## 9. Multi-Modal Interface

### REQ-UI-001: Web Dashboard (P1)

**Description**: The existing web dashboard is the primary rich interface.

**Acceptance Criteria**:
- Dashboard displays: active goals, pending approvals, recent activity, domain overview
- The human can create goals, review proposals, approve trust gates, and manage preferences
- Activity history with search and filtering is available
- Cost and budget information is visible
- The dashboard works on desktop and tablet browsers

### REQ-UI-002: Chat Interface (P1)

**Description**: A conversational interface for natural language interaction with the agent.

**Acceptance Criteria**:
- The human can converse with the agent in natural language
- The agent can present structured information (goal proposals, approval requests) inline in chat
- Chat history persists across sessions
- The agent maintains conversational context within a session
- The chat interface is accessible from both web and CLI

### REQ-UI-003: CLI Interface (P1)

**Description**: The existing CLI (zebra-agent CLI) is preserved and extended for terminal-native workflows.

**Acceptance Criteria**:
- Existing CLI commands continue to work (goal execution, status, memory queries)
- New commands for: trust management, values profile, knowledge queries
- Output is formatted for terminal readability (tables, colours, progress indicators)
- The CLI can operate fully offline for local-only operations

### REQ-UI-004: Notification System (P2)

**Description**: The agent can push notifications to the human for time-sensitive information.

**Acceptance Criteria**:
- Notifications are categorised: approval_required, goal_completed, concern_flagged, suggestion, reminder
- Notification channels are pluggable (email, desktop, mobile push, webhook)
- The human can configure notification preferences per category and domain
- Quiet hours are respected — non-urgent notifications are batched and delivered later
- Each notification links back to the relevant goal or workflow for context

### REQ-UI-005: Interface Consistency (P1)

**Description**: The agent's behaviour and personality are consistent across all interfaces.

**Acceptance Criteria**:
- The same goal can be created and monitored from any interface
- Approval requests appear on all active interfaces (not just the one that created the goal)
- The agent's tone and personality are identical across web, chat, and CLI
- State changes on one interface are immediately reflected on others

---

## 10. Domain Specifications

### 10.1 Code Development (P1 — Exists)

### REQ-DOM-CODE-001: Preserve Existing Code Capabilities (P1)

**Description**: All existing code development workflows are preserved: feature implementation, bug fixing, code review, workflow creation.

**Acceptance Criteria**:
- The agent main loop workflow continues to function for code goals
- Workflow selection, creation, and variant creation work as before
- Ethics gates evaluate code actions against values profile
- Assess-and-record captures effectiveness metrics for code workflows
- Dream cycle (analyze, evaluate, optimize) continues to improve code workflows

### REQ-DOM-CODE-002: Code Domain Trust Integration (P1)

**Description**: Code development respects the trust model.

**Acceptance Criteria**:
- At SUPERVISED: agent proposes code changes, human reviews before commit
- At SEMI-AUTONOMOUS: agent commits to branches, human approves merges to main
- At AUTONOMOUS: agent manages the full development cycle, human is notified of outcomes
- File operations (write, delete) are classified correctly for reversibility

### 10.2 Scheduling & Time Management (P1)

### REQ-DOM-SCHED-001: Calendar Awareness (P1)

**Description**: The agent understands the human's schedule and can reason about time.

**Acceptance Criteria**:
- The agent can read calendar events from at least one calendar provider
- The agent knows the human's timezone, working hours, and recurring commitments
- The agent considers schedule conflicts when proposing goals or actions
- Time-sensitive goals are flagged with deadlines

### REQ-DOM-SCHED-002: Schedule Management (P1)

**Description**: The agent can propose, create, and modify calendar events.

**Acceptance Criteria**:
- The agent can propose new events with: title, time, duration, participants, context
- At SUPERVISED: events are proposed and human creates them
- At SEMI-AUTONOMOUS: agent creates events, human can modify/cancel
- Event conflicts are detected and flagged before creation
- The agent respects buffer time preferences between events

### REQ-DOM-SCHED-003: Routine Detection & Optimisation (P2)

**Description**: The agent identifies patterns in the human's schedule and suggests improvements.

**Acceptance Criteria**:
- The agent detects recurring patterns (weekly meetings, daily routines)
- Suggestions for optimisation include reasoning ("You're most productive in the morning")
- The human can accept, reject, or modify routine suggestions
- Accepted routines are stored in personal knowledge

### 10.3 Research & Knowledge (P1)

### REQ-DOM-RESEARCH-001: Research Workflows (P1)

**Description**: The agent can conduct structured research on topics the human cares about.

**Acceptance Criteria**:
- Research goals produce structured output: summary, sources, key findings, open questions
- The agent can perform web searches, read documents, and synthesise information
- Research results are stored in personal knowledge for future reference
- The agent cites sources and distinguishes fact from inference

### REQ-DOM-RESEARCH-002: Ongoing Monitoring (P2)

**Description**: The agent can track topics over time and alert the human to relevant changes.

**Acceptance Criteria**:
- The human can define topics to monitor (e.g., "AI regulation updates", "competitor releases")
- The agent periodically checks for updates on monitored topics
- Updates are delivered via the notification system with relevance context
- Monitoring frequency is configurable per topic

### 10.4 Finance & Budgeting (P2)

### REQ-DOM-FIN-001: Financial Awareness (P2)

**Description**: The agent understands the human's financial situation and goals.

**Acceptance Criteria**:
- The agent can read account balances and transactions from connected financial sources
- Financial data is stored locally only (never synced to cloud unless explicitly configured)
- The agent tracks spending patterns and budget adherence
- Financial knowledge is the most privacy-restricted category (encrypted at rest)

### REQ-DOM-FIN-002: Budget Tracking (P2)

**Description**: The agent helps track spending against budgets.

**Acceptance Criteria**:
- The human can define budgets per category with time periods
- The agent categorises transactions and tracks against budgets
- Alerts fire when spending approaches or exceeds budget limits
- The agent suggests adjustments based on patterns ("You tend to overspend on dining out in December")

### 10.5 Health & Wellness (P2)

### REQ-DOM-HEALTH-001: Health Tracking (P2)

**Description**: The agent helps track health-related goals and habits.

**Acceptance Criteria**:
- The human can define health goals (exercise frequency, sleep hours, medication schedules)
- The agent can read data from health integrations (fitness trackers, health apps)
- Progress is tracked and visible on the dashboard
- Health data has the highest privacy classification — local-only by default, encrypted

### REQ-DOM-HEALTH-002: Wellness Nudges (P2)

**Description**: The agent provides gentle reminders and encouragement for health goals.

**Acceptance Criteria**:
- Reminders respect quiet hours and the human's current schedule
- The tone is encouraging, never judgmental
- The human can snooze, dismiss, or disable nudges per goal
- The agent adapts nudge timing based on what works (tracked in episodic memory)

### 10.6 Home Management (P3)

### REQ-DOM-HOME-001: Home Task Tracking (P3)

**Description**: The agent helps manage household tasks and maintenance.

**Acceptance Criteria**:
- The human can define recurring home tasks (cleaning, maintenance schedules)
- The agent tracks completion and sends reminders
- For multi-user households, tasks can be assigned to family members
- The agent can order supplies through integrations (at appropriate trust level)

### 10.7 Creative Projects (P3)

### REQ-DOM-CREATIVE-001: Creative Project Support (P3)

**Description**: The agent helps manage and contribute to creative projects.

**Acceptance Criteria**:
- The human can define creative projects with milestones and deadlines
- The agent provides inspiration, research, and feedback on creative work
- Progress is tracked without imposing rigid structure
- The agent respects the human's creative autonomy (defaults to SUPERVISED trust)

### 10.8 Social & Relationships (P3)

### REQ-DOM-SOCIAL-001: Relationship Maintenance (P3)

**Description**: The agent helps the human maintain important relationships.

**Acceptance Criteria**:
- The human can register important people with context (relationship type, preferences, important dates)
- The agent reminds the human of birthdays, anniversaries, and check-in opportunities
- Communication drafting respects the human's voice and relationship context
- Social data is strictly private and never shared across users

---

## 11. Data Model & Privacy

### REQ-DATA-001: Local-First Storage (P1)

**Description**: All personal data is stored locally by default on the human's device.

**Acceptance Criteria**:
- A fresh installation requires no network connectivity for data storage
- All structured data is persisted locally
- The storage layer is abstracted — implementations can be swapped without affecting task actions
- No external database or cloud service is required for a single-user deployment

### REQ-DATA-002: Encrypted Cloud Sync (P2)

**Description**: The human can opt in to encrypted cloud sync for cross-device access.

**Acceptance Criteria**:
- Cloud sync is disabled by default and requires explicit opt-in
- All synced data is encrypted client-side before upload
- The encryption key is derived from a user-provided passphrase (never stored remotely)
- Sync supports: memory, knowledge, preferences, workflow history (not credentials)
- The human can selectively sync specific domains or data categories

### REQ-DATA-003: Data Export (P1)

**Description**: The human can export all their data in a portable format at any time.

**Acceptance Criteria**:
- A single command or button exports all data to a portable, documented format
- The export includes: personal knowledge, memory, preferences, workflow history, values profile
- The export format is documented and machine-readable
- Export completes within 5 minutes for up to 1GB of data

### REQ-DATA-004: Context Minimisation (P1)

**Description**: The agent sends only the minimum necessary context to external LLM APIs.

**Acceptance Criteria**:
- LLM prompts include only the data relevant to the current task
- Personal knowledge is filtered to task-relevant entries before inclusion in prompts
- Sensitive categories (finance, health) require explicit workflow-level opt-in to include in prompts
- The human can audit what data was sent to the LLM for any workflow execution

### REQ-DATA-005: Data Deletion (P1)

**Description**: The human can delete any or all of their data permanently.

**Acceptance Criteria**:
- Individual knowledge entries, memories, and workflow records can be deleted
- A "delete all my data" command removes everything associated with the user
- Deletion is immediate for local data and propagated to cloud sync within 24 hours
- Deleted data is irrecoverable (no soft-delete for user-requested deletion)

---

## 12. External Integrations

### REQ-INT-001: Integration Provider Interface (P1)

**Description**: A standard interface defines how external services connect to the agent.

**Acceptance Criteria**:
- An `IntegrationProvider` abstract base class defines: `connect()`, `disconnect()`, `health_check()`, `get_capabilities()`
- Each provider declares its capabilities (read, write, subscribe) and required credentials
- Providers are registered via the entry-point pattern (`zebra.integrations`)
- The engine discovers integrations at startup via `IoCActionRegistry` or a dedicated registry

### REQ-INT-002: Authentication Management (P2)

**Description**: The agent manages credentials for external services securely.

**Acceptance Criteria**:
- Standard authentication flows (token-based, key-based) are supported
- Credentials are stored in the local credential store (encrypted at rest)
- Credentials are never included in process properties or workflow logs
- The human can revoke credentials from any interface
- Credential refresh (token rotation) happens automatically

### REQ-INT-003: MCP Tool Integration (P1)

**Description**: The existing MCP (Model Context Protocol) integration is preserved and extended to support domain-specific tools.

**Acceptance Criteria**:
- The existing MCP server functionality continues to work
- New domains can expose MCP tools for their operations
- MCP tools respect trust levels (tool execution is gated)
- Tool discovery works across all registered domains

### REQ-INT-004: Integration Health Monitoring (P2)

**Description**: The agent monitors the health of connected integrations and handles failures gracefully.

**Acceptance Criteria**:
- Periodic health checks run for all connected integrations
- Failed integrations are flagged in the dashboard with last-known-good status
- Workflows that depend on a failed integration pause and notify the human
- The agent does not retry failed integrations aggressively (exponential backoff)

---

## 13. Non-Functional Requirements

### REQ-NFR-001: Response Time (P1)

**Description**: The agent responds promptly to human interactions.

**Acceptance Criteria**:
- Chat messages receive an initial response (acknowledgment or streaming start) within 2 seconds
- Goal creation and workflow start complete within 5 seconds (excluding LLM time)
- Dashboard pages load within 3 seconds
- CLI commands return results within 2 seconds for local operations

### REQ-NFR-002: Crash Recovery (P1)

**Description**: The system recovers gracefully from crashes without data loss.

**Acceptance Criteria**:
- Process state is persisted before each state transition (already exists)
- A crashed workflow can be resumed from its last persisted state
- The daemon restarts automatically and picks up queued goals
- No data is lost due to a crash (write-ahead or transactional storage)

### REQ-NFR-003: Budget Controls (P1)

**Description**: The existing budget management system is preserved and extended for multi-domain use.

**Acceptance Criteria**:
- Daily budget limits continue to work with linear pacing (already exists)
- Budget can be allocated per-domain (e.g., "max $10/day on code, $5/day on research")
- Soft warnings fire at configurable thresholds (already exists)
- Budget exhaustion pauses queued goals, does not cancel running ones
- Cost tracking propagates from child to parent processes (already exists)

### REQ-NFR-004: Observability (P1)

**Description**: The system provides comprehensive logging, metrics, and tracing.

**Acceptance Criteria**:
- Structured logging with appropriate log levels throughout all components
- Workflow execution metrics: duration, cost, success rate, per domain
- Task action performance metrics: execution time, failure rate
- Memory system metrics: entries by category, query latency, storage size
- All metrics are accessible via the dashboard and CLI

### REQ-NFR-005: Offline Capability (P2)

**Description**: The agent provides useful functionality without network connectivity.

**Acceptance Criteria**:
- Local knowledge queries work offline
- Pending goals and queued tasks are visible offline
- The agent can process locally-executable workflows (no LLM required) offline
- Sync resumes automatically when connectivity returns
- The human is clearly informed which features require connectivity

### REQ-NFR-006: Scalability (P2)

**Description**: The system handles growing data volumes gracefully.

**Acceptance Criteria**:
- Personal knowledge store handles up to 100,000 entries without performance degradation
- Episodic memory handles up to 10,000 workflow runs
- Search across all memory tiers returns results within 1 second
- Storage growth is linear with data volume (no exponential index bloat)

### REQ-NFR-007: Security (P1)

**Description**: The system protects the human's data and access.

**Acceptance Criteria**:
- All credentials are encrypted at rest
- API communications are encrypted in transit
- Local data storage supports encryption at rest
- No default passwords or keys ship with the system
- The human can audit all external API calls made by the agent

---

## 14. Phased Delivery

### Phase 1 — Foundation (P1 Requirements)

**Goal**: Core system extended with trust model, values framework, and personal knowledge. Single user, single device.

| Deliverable | Requirements |
|---|---|
| Trust & Autonomy Engine | REQ-TRUST-001 through REQ-TRUST-004 |
| Values Profile & Ethics Extension | REQ-ETH-001 through REQ-ETH-003, REQ-ETH-006 |
| Personal Knowledge Store | REQ-MEM-001 through REQ-MEM-004 |
| Collaborative Peer Basics | REQ-PEER-001, REQ-PEER-002, REQ-PEER-005, REQ-PEER-006 |
| Code Domain Trust Integration | REQ-DOM-CODE-001, REQ-DOM-CODE-002 |
| Scheduling Domain | REQ-DOM-SCHED-001, REQ-DOM-SCHED-002 |
| Research Domain | REQ-DOM-RESEARCH-001 |
| Web Dashboard & CLI Extensions | REQ-UI-001, REQ-UI-002, REQ-UI-003, REQ-UI-005 |
| Integration Framework | REQ-INT-001, REQ-INT-003 |
| Data & Privacy Foundations | REQ-DATA-001, REQ-DATA-003, REQ-DATA-004, REQ-DATA-005 |
| Core Principles | REQ-PRIN-001 through REQ-PRIN-007 |
| User Namespace | REQ-USR-001, REQ-USR-002 |
| Non-Functional Foundations | REQ-NFR-001 through REQ-NFR-004, REQ-NFR-007 |

**Independently Valuable**: A single user has a trusted, values-aligned AI partner that helps with code, scheduling, and research, with full local data control and observable behaviour.

### Phase 2 — Expansion (P2 Requirements)

**Goal**: Deeper autonomy, richer domains, proactive capabilities, and cross-device support.

| Deliverable | Requirements |
|---|---|
| Emergency Override & Freeing | REQ-TRUST-005, REQ-TRUST-006 |
| Proactive Ethics | REQ-ETH-004, REQ-ETH-005 |
| Respectful Pushback & Disagreement | REQ-PEER-003, REQ-PEER-004 |
| Knowledge Lifecycle | REQ-MEM-005, REQ-MEM-006 |
| Notification System | REQ-UI-004 |
| Schedule Optimisation | REQ-DOM-SCHED-003 |
| Research Monitoring | REQ-DOM-RESEARCH-002 |
| Finance Domain | REQ-DOM-FIN-001, REQ-DOM-FIN-002 |
| Health Domain | REQ-DOM-HEALTH-001, REQ-DOM-HEALTH-002 |
| Cloud Sync | REQ-DATA-002 |
| Auth Management | REQ-INT-002 |
| Integration Health | REQ-INT-004 |
| Offline & Scale | REQ-NFR-005, REQ-NFR-006 |

**Independently Valuable**: The agent becomes a proactive partner across more life domains, syncs across devices, and manages itself more independently.

### Phase 3 — Full Vision (P3 Requirements)

**Goal**: Multi-user support, full life-domain coverage, community-contributed domains.

| Deliverable | Requirements |
|---|---|
| Family / Household Support | REQ-USR-003 |
| Team / Organisation Support | REQ-USR-004 |
| Home Domain | REQ-DOM-HOME-001 |
| Creative Domain | REQ-DOM-CREATIVE-001 |
| Social Domain | REQ-DOM-SOCIAL-001 |

**Independently Valuable**: Zebra becomes a household-level AI partner that supports the full breadth of life activities, with extensibility for community-contributed domains.

---

## Appendix A: Requirement Summary

Total requirements: 70

| Category | Count | P1 | P2 | P3 |
|---|---|---|---|---|
| User Profiles | 4 | 2 | 0 | 2 |
| Core Principles | 7 | 7 | 0 | 0 |
| Trust & Autonomy | 6 | 4 | 2 | 0 |
| Ethics Framework | 6 | 4 | 2 | 0 |
| Collaborative Peer | 6 | 4 | 2 | 0 |
| Memory & Knowledge | 6 | 4 | 2 | 0 |
| Multi-Modal Interface | 5 | 4 | 1 | 0 |
| Domain: Code | 2 | 2 | 0 | 0 |
| Domain: Scheduling | 3 | 2 | 1 | 0 |
| Domain: Research | 2 | 1 | 1 | 0 |
| Domain: Finance | 2 | 0 | 2 | 0 |
| Domain: Health | 2 | 0 | 2 | 0 |
| Domain: Home | 1 | 0 | 0 | 1 |
| Domain: Creative | 1 | 0 | 0 | 1 |
| Domain: Social | 1 | 0 | 0 | 1 |
| Data & Privacy | 5 | 4 | 1 | 0 |
| External Integrations | 4 | 2 | 2 | 0 |
| Non-Functional | 7 | 5 | 2 | 0 |
| **Total** | **70** | **45** | **20** | **5** |

---

## Appendix B: Existing Capability Map

This table maps existing Zebra capabilities to the requirements that preserve or extend them.

| Existing Capability | Location | Requirement | Action |
|---|---|---|---|
| Workflow Engine (process/task state machines) | `zebra-py/zebra/core/engine.py` | REQ-PRIN-001 | Preserve |
| Entry-point task action registry | `zebra-agent/zebra_agent/ioc/` | REQ-PRIN-002 | Preserve |
| Kantian ethics gates | `zebra-tasks/zebra_tasks/agent/ethics_gate.py` | REQ-ETH-001 | Extend |
| Agent main loop workflow | `zebra-agent/workflows/agent_main_loop.yaml` | REQ-PEER-001 | Extend |
| Workflow memory (episodic) | `zebra-agent/zebra_agent/memory.py` | REQ-MEM-002 | Preserve |
| Conceptual memory (goal-pattern index) | `zebra-agent/zebra_agent/memory.py` | REQ-MEM-003 | Preserve |
| Working memory (process properties) | `zebra-py/zebra/core/models.py` | REQ-MEM-001 | Preserve |
| Storage interfaces | `zebra-agent/zebra_agent/storage/interfaces.py` | REQ-DATA-001 | Extend |
| Budget manager (daily pacing) | `zebra-agent/zebra_agent/budget.py` | REQ-NFR-003 | Extend |
| Web dashboard | `zebra-agent-web/zebra_agent_web/` | REQ-UI-001 | Extend |
| CLI interface | `zebra-agent/zebra_agent/cli/` | REQ-UI-003 | Extend |
| MCP server integration | `zebra-py/zebra/mcp/` | REQ-INT-003 | Extend |
| Cost tracking (LLM tokens) | `zebra-tasks/zebra_tasks/llm/` | REQ-NFR-003 | Preserve |
| Dream cycle (self-improvement) | `zebra-tasks/zebra_tasks/agent/` | REQ-DOM-CODE-001 | Preserve |
| Human tasks (auto: false + form schema) | `zebra-py/zebra/forms/` | REQ-TRUST-003 | Extend |
| Conditional routing (next_route) | `zebra-py/zebra/core/engine.py` | REQ-TRUST-003 | Extend |
| Synchronized tasks (FOE join) | `zebra-py/zebra/core/engine.py` | REQ-PRIN-001 | Preserve |
