# Zebra Workflow Engine - TODO

This document tracks unimplemented features and improvements based on the DESIGN.md specifications and current implementation analysis.

**Last Updated:** 2026-01-18  
**Status Legend:** ❌ Not Started | ⚠️ Partial | ✅ Complete

---

## High Priority

### .1 Tidying Up
- [x] Make zebra-agent in memory only with interfaces for the real implementation (Completed 2026-02-05)
- [x] Remove rust references (Completed 2026-02-05)
- [ ] move zebra mcp server from zebra-py to zebra-agent-web 

### .5 Learning loops
- [ ] Run page when error occurs just hangs
- [ ] Need a page to show all in progress runs
- [ ] on run goals page should load the workflow vizualization from history and show it progressing
- [ ] LLM can define new workflows and saves them to disk so can survive db wipe
- [ ] Long term memory signposts to detail memory as needed
- [ ] Dream workflows run daily to optimize memory
- [ ] Add memory into the agent loop
- [ ] When not sure LLM can run 2 parallel workflows to compare results and show to human for vote

### 1. Task Actions Library Expansion ⚠️

**Description:** The system currently has only 13 task actions. Need more built-in actions for common operations.

**Missing Actions:**
- [x] File I/O operations (read, write, copy, move, delete, search) - Completed 2026-02-01
- [ ] HTTP/REST API calling (GET, POST, PUT, DELETE with auth)
- [ ] Database operations (query, insert, update, delete)
- [ ] Git operations (clone, commit, push, pull, branch)
- [ ] Email/notification sending (SMTP, webhooks)
- [ ] Data transformations (CSV parsing, JSON processing, XML)
- [ ] Archive operations (zip, tar, extract)
- [ ] Template rendering (Jinja2, Mustache)

**Reference:** DESIGN.md lines 148-162 (TaskAction Interface)  
**Files to create:**
- `zebra-tasks/zebra_tasks/filesystem/` - File operations
- `zebra-tasks/zebra_tasks/http/` - HTTP client actions
- `zebra-tasks/zebra_tasks/database/` - DB operations
- `zebra-tasks/zebra_tasks/git/` - Git integration
- `zebra-tasks/zebra_tasks/notifications/` - Email/webhooks
- `zebra-tasks/zebra_tasks/data/` - Data transformation

### 2. Resilience ✅ 
- [x] Workflows are resumed on restart (Phase 2 Complete - 2026-01-27)

### 3. Advanced Guardrails System ⚠️

**Description:** Current guardrails are basic (token/iteration limits). Need comprehensive safety system.

**Features Required:**
- [ ] Fine-grained scope restrictions (allowed actions, resources)
- [ ] Resource usage limits (memory, CPU, disk, network)
- [ ] Custom safety rules (domain-specific constraints)
- [ ] Human-in-the-loop approval workflows
- [ ] Escalation policies (configurable responses to violations)
- [ ] Budget tracking (cost limits for LLM usage)
- [ ] Rate limiting (requests per minute/hour)
- [ ] Audit logging for all guardrail violations

**Reference:** DESIGN.md lines 341-357 (Guardrails section)  
**Files to modify:**
- `zebra-agent/zebra_agent/guardrails.py` - Expand current implementation
- `zebra-tasks/zebra_tasks/approval/` - Human approval actions

### 4. Distributed Execution Support ❌

**Description:** Enable workflow execution across multiple nodes for scalability and fault tolerance.

**Features Required:**
- [ ] Multi-node process execution
- [ ] Task distribution and load balancing
- [ ] State replication across nodes
- [ ] Fault tolerance and automatic recovery
- [ ] Distributed locking mechanism
- [ ] Node discovery and health monitoring
- [ ] Network partition handling
- [ ] Consistent state synchronization

**Technology Stack:** Redis/etcd for coordination, gRPC for communication  
**Reference:** DESIGN.md line 609 (Future Directions)  
**Files to create:**
- `zebra-distributed/` - New package for distributed features
- `zebra-py/zebra/storage/distributed.py` - Distributed StateStore

---

## Medium Priority

### 5. Advanced Workflow Patterns ⚠️

**Description:** Currently 9 of 43 control-flow patterns fully implemented. Add more useful patterns.

**Priority Patterns to Implement:**
- [ ] WCP-9: Structured Discriminator (first wins, ignore rest)
- [ ] WCP-16: Deferred Choice (runtime path selection)
- [ ] WCP-18: Milestone (state-based activation)
- [ ] WCP-22: Recursion (self-referential workflows)
- [ ] WCP-28: Blocking Discriminator (M-out-of-N completion)
- [ ] WCP-33: Static Partial Join for Multiple Instances
- [ ] WCP-41: Thread Merge (safe concurrent path merging)

**Reference:** DESIGN.md lines 186-264 (Workflow Patterns), `zebra-py/workflows.md`  
**Files to modify:**
- `zebra-py/zebra/core/engine.py` - Add pattern support
- `zebra-py/tests/test_patterns.py` - Add pattern tests

**Status:** ⚠️ Core patterns working, advanced patterns missing

### 6. Documentation Improvements ⚠️

**Description:** Technical documentation exists, but missing user-facing guides.

**Documents Needed:**
- [ ] Getting Started Tutorial (step-by-step workflow creation)
- [ ] User Guide (comprehensive feature documentation)
- [ ] API Reference (auto-generated from docstrings)
- [ ] Migration Guide (Java → Python for legacy users)
- [ ] Performance Tuning Guide (optimization best practices)
- [ ] Deployment Guide (production setup, Docker, K8s)
- [ ] Security Best Practices
- [ ] Troubleshooting Guide (common issues and solutions)
- [ ] Video tutorials (workflow basics, agent setup)

**Reference:** DESIGN.md lines 629-634 (References section)  
**Files to create:**
- `docs/` - New documentation directory
- `docs/tutorial/` - Step-by-step guides
- `docs/api/` - Generated API docs
- `docs/deployment/` - Production guides

**Status:** ⚠️ Architecture docs excellent, user guides missing

### 7. Multi-Agent Collaboration ❌

**Description:** Enable multiple agents to work together on shared goals.

**Features Required:**
- [ ] Agent-to-agent communication protocol
- [ ] Shared goal pursuit and task allocation
- [ ] Consensus mechanisms (voting, weighted decisions)
- [ ] Conflict resolution strategies
- [ ] Agent capability advertisement/discovery
- [ ] Collaborative learning (shared experiences)
- [ ] Team coordination workflows
- [ ] Message passing infrastructure

**Reference:** DESIGN.md line 615 (Future Directions)  
**Files to create:**
- `zebra-agent/zebra_agent/collaboration/` - Multi-agent features
- `zebra-tasks/zebra_tasks/agent/communication.py` - Agent messaging



---

## Low Priority / Future Enhancements

### 10. Enhanced Memory System ⚠️

**Description:** Current three-tier memory is functional but basic. Add advanced capabilities.

**Features Required:**
- [ ] Vector similarity search (embedding-based retrieval)
- [ ] Automatic knowledge extraction from episodes
- [ ] Cross-goal learning (generalize across different goals)
- [ ] Memory pruning strategies (importance-based)
- [ ] Memory visualization tools
- [ ] External knowledge base integration
- [ ] Semantic search across memories
- [ ] Memory consolidation optimization

**Reference:** DESIGN.md lines 316-339 (Memory System)  
**Files to modify:**
- `zebra-agent/zebra_agent/memory.py` - Enhance existing implementation
- Add vector database integration (Chroma, Pinecone)

**Status:** ⚠️ Basic three-tier memory works, advanced features missing

### 11. Natural Language Workflow Generation ❌

**Description:** Generate workflow definitions from plain English descriptions using LLMs.

**Features Required:**
- [ ] Natural language to YAML workflow conversion
- [ ] Interactive refinement (chat-based workflow design)
- [ ] Workflow validation and suggestion
- [ ] Auto-optimization of generated workflows
- [ ] Learning from user corrections
- [ ] Template-based generation
- [ ] Multi-turn conversation for complex workflows

**Reference:** DESIGN.md line 616 (Future Directions)  
**Files to create:**
- `zebra-tasks/zebra_tasks/synthesis/` - Workflow synthesis actions
- `zebra-agent/zebra_agent/synthesis.py` - NL workflow generation

- [ ] Google Cloud (Storage, Cloud Functions)
- [ ] Docker (container management)
- [ ] Kubernetes (pod orchestration)
- [ ] Kafka (event streaming)
- [ ] RabbitMQ (message queuing)
- [ ] Webhook support (generic HTTP callbacks)

**Reference:** Implied by DESIGN.md extensibility philosophy  
**Files to create:**
- `zebra-integrations/` - New package for integrations
- One module per integration

### 14. Advanced Agent Features ⚠️

**Description:** Enhancements to agent self-improvement and learning.

**Features Required:**
- [ ] Meta-learning (learn how to learn)
- [ ] Transfer learning across domains
- [ ] Automatic workflow optimization algorithms
- [ ] A/B testing of workflow variations
- [ ] Genetic algorithm for workflow evolution
- [ ] Reinforcement learning integration
- [ ] Explainable AI (justify decisions)
- [ ] Counterfactual reasoning ("what if" analysis)

**Reference:** DESIGN.md lines 359-367 (Learning & Self-Improvement)  
**Files to modify:**
- `zebra-agent/zebra_agent/learning.py` - New advanced learning module

**Status:** ⚠️ Basic learning implemented, advanced algorithms missing

**Note:** Highly speculative, low practical priority

### 16. Knowledge Graph Integration ❌

**Description:** Integrate with knowledge graphs for semantic workflow understanding.

**Features Required:**
- [ ] Knowledge graph storage (Neo4j, Neptune)
- [ ] Ontology-based workflow reasoning
- [ ] Semantic task relationships
- [ ] Automatic workflow generation from domain models
- [ ] Query workflows using graph patterns
- [ ] Workflow recommendation based on knowledge

**Reference:** DESIGN.md line 618 (Future Directions)  
**Files to create:**
- `zebra-knowledge/` - Knowledge graph integration

---

## Testing & Quality Improvements

### 17. Test Coverage Enhancements ⚠️

**Current Status:** Good unit/integration coverage, but gaps exist.

**Improvements Needed:**
- [ ] End-to-end tests for complete workflows
- [ ] Performance regression tests
- [ ] Chaos testing (fault injection)
- [ ] Load testing (high-volume workflows)
- [ ] Security testing (injection attacks, access control)
- [ ] Browser-based UI tests (when UI is built)
- [ ] Multi-agent interaction tests

**Files to create:**
- `tests/e2e/` - End-to-end test suites
- `tests/performance/` - Performance benchmarks
- `tests/chaos/` - Fault injection tests

**Status:** ⚠️ Good coverage, but not comprehensive

---

## Operational & Production Features

### 18. Monitoring & Observability ❌

**Description:** Production-grade monitoring and logging.

**Features Required:**
- [ ] Prometheus metrics export
- [ ] OpenTelemetry tracing integration
- [ ] Structured logging (JSON logs)
- [ ] Health check endpoints
- [ ] Performance profiling hooks
- [ ] Error tracking integration (Sentry)
- [ ] Custom metrics dashboard
- [ ] Alerting rules (PagerDuty, OpsGenie)

**Files to create:**
- `zebra-py/zebra/monitoring/` - Monitoring infrastructure
- `zebra-py/zebra/telemetry/` - OpenTelemetry integration

### 19. Deployment Automation ❌

**Description:** Production deployment tools and configurations.

**Deliverables Needed:**
- [ ] Docker images (optimized, multi-stage)
- [ ] Docker Compose configurations
- [ ] Kubernetes manifests (Deployments, Services, ConfigMaps)
- [ ] Helm charts for K8s deployment
- [ ] Terraform scripts (AWS, GCP, Azure)
- [ ] CI/CD pipelines (GitHub Actions, GitLab CI)
- [ ] Database migration scripts
- [ ] Backup and restore procedures
- [ ] Rolling update strategies
- [ ] Blue-green deployment support

**Files to create:**
- `deploy/docker/` - Dockerfiles
- `deploy/k8s/` - Kubernetes manifests
- `deploy/helm/` - Helm charts
- `deploy/terraform/` - Infrastructure as Code
- `.github/workflows/` - CI/CD pipelines

### 20. Security Hardening ❌

**Description:** Security best practices and hardening.

**Features Required:**
- [ ] Authentication and authorization (JWT, OAuth)
- [ ] Role-based access control (RBAC)
- [ ] API rate limiting
- [ ] Input validation and sanitization
- [ ] SQL injection prevention
- [ ] Secret management (Vault integration)
- [ ] Encryption at rest (database)
- [ ] Encryption in transit (TLS)
- [ ] Security audit logging
- [ ] Dependency vulnerability scanning
- [ ] OWASP compliance

**Files to create:**
- `zebra-py/zebra/security/` - Security infrastructure
- Security documentation and policies

### 21. Performance Optimization ⚠️

**Description:** Optimize for large-scale workflows.

**Optimizations Needed:**
- [ ] Database query optimization (indexing, query planning)
- [ ] Connection pooling (database, HTTP)
- [ ] Caching layer (Redis, Memcached)
- [ ] Lazy loading of workflow definitions
- [ ] Batch operations for task transitions
- [ ] Asynchronous event processing
- [ ] Memory profiling and optimization
- [ ] Parallel task execution optimization

**Files to modify:**
- `zebra-py/zebra/storage/sqlite.py` - Add indexing, query optimization
- `zebra-py/zebra/core/engine.py` - Batch operations

**Status:** ⚠️ Works well for small/medium workflows, not optimized for scale

---

## Contributing

When working on items from this TODO:

1. **Update status** - Change ❌ to ⚠️ when starting, ⚠️ to ✅ when complete
3. **Add completion date** - Note when feature was completed
4. **Update DESIGN.md** - Reflect architectural changes
5. **Add tests** - All new features require tests
6. **Update docs** - User-facing features need documentation

---

## Notes

- This TODO is based on DESIGN.md specifications and current codebase analysis (2026-01-18)
- Priorities may shift based on user needs and feedback
- Some "future" features (quantum optimization, knowledge graphs) are speculative
- Core engine is production-ready; focus should be on task actions, UI, and deployment

**For questions or to propose new features, see:** `DESIGN.md`, `AGENTS.md`, or open an issue.
