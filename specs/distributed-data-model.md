# Distributed Data Model for Multi-User Zebra

**Status**: Draft
**Date**: 2026-04-16
**Relates to**: REQ-DATA-001, REQ-DATA-002, REQ-PRIN-005, REQ-USR-003, REQ-USR-004

---

## 1. Problem Statement

Zebra's core architecture is local-first: all data lives on the user's device, the system works offline, and no central server is required (REQ-DATA-001, REQ-PRIN-005). Phase 2 adds encrypted cloud sync for cross-device access for a single user (REQ-DATA-002).

Phase 3 introduces multi-user scenarios that fundamentally require shared mutable state:

- **Family/Household (REQ-USR-003)**: Shared domains (Home, Finance) with collaborative goal-setting, private domains visible only to their owner
- **Team/Organisation (REQ-USR-004)**: RBAC restricting domain visibility, team goals assigned across humans, organisational policy overrides

The traditional solution — a centralised database with server-enforced RBAC — directly violates local-first principles. We need a model that supports shared state, access control, and conflict resolution without requiring a central authority.

---

## 2. Design Constraints

From the existing requirements:

1. **Local-first**: Each device is the primary store for its user's data. No mandatory server.
2. **Offline-capable**: Users can work without connectivity. Sync catches up when online.
3. **Encrypted**: Data in transit and at rest must be encryptable with user-controlled keys.
4. **Privacy boundaries**: Private domains must be invisible to other users, not just read-protected.
5. **Eventually consistent**: Multi-user shared state need not be strongly consistent — causal consistency is sufficient for Zebra's use cases (goal tracking, shared calendars, household tasks).
6. **No global consensus required**: We don't need total ordering of all events across all users. Causal ordering within shared domains is enough.

---

## 3. Architectural Approach: CRDTs + Signed Capabilities

### 3.1 Why Not...

| Approach | Why not |
|----------|---------|
| **Centralised DB + server RBAC** | Violates local-first. Requires always-on server. Single point of failure. |
| **Blockchain / full DLT** | Overkill. Global consensus is unnecessary — we only need agreement within shared domains. Expensive compute for what's a small-group collaboration problem. |
| **Matrix Protocol** | Designed for chat, not structured data replication. Heavy homeserver dependency. Would need significant adaptation. However, worth revisiting as a transport layer. |
| **Simple file sync (Dropbox-style)** | No conflict resolution. Last-write-wins destroys concurrent edits. No access control model. |

### 3.2 Core Architecture

```
+------------------+        +------------------+
|   Device A       |        |   Device B       |
|                  |        |                  |
|  Local SQLite    |        |  Local SQLite    |
|  (CRDT-aware)    |  sync  |  (CRDT-aware)    |
|                  |<------>|                  |
|  Capability      |        |  Capability      |
|  Keyring         |        |  Keyring         |
+------------------+        +------------------+
         |                           |
         |    (optional relay)       |
         +---------> Relay <---------+
                   Server
```

Three layers:

1. **CRDT Storage Layer** — conflict-free data replication
2. **Capability Layer** — cryptographic access control
3. **Sync Transport Layer** — how changes move between devices

---

## 4. Layer 1: CRDT Storage

### 4.1 What Are CRDTs

Conflict-free Replicated Data Types are data structures where concurrent edits by different users always merge deterministically without coordination. There's no "conflict" — the merge function is mathematically guaranteed to converge.

### 4.2 Choice: cr-sqlite

[cr-sqlite](https://vlcn.io/docs/cr-sqlite) extends SQLite with CRDT semantics. Each table can be marked as a "CRDT table" where:

- Rows have vector clocks tracking causal history
- Concurrent inserts of the same primary key merge (last-writer-wins per column, or custom merge)
- Deletes are causal (a delete only removes versions it has "seen")
- The merge is performed at the SQLite level — the application sees normal SQL

This is ideal for Zebra because:
- We already use SQLite as the local store
- Existing queries and models work unchanged
- Sync is "push your changes, pull theirs, let cr-sqlite merge"
- Proven technology with active development

### 4.3 CRDT Table Design

Not all data needs to be shared. Tables are categorised:

| Category | Shared? | CRDT? | Examples |
|----------|---------|-------|----------|
| **Private user data** | Never | No | Values profile, health data, private knowledge |
| **User-scoped shared** | Per-domain opt-in | Yes | Shared goals, household tasks, team projects |
| **Domain config** | Within domain members | Yes | Shared domain settings, trust policies |
| **Sync metadata** | Between syncing peers | Yes | Vector clocks, peer identities |

### 4.4 Conflict Semantics

For Zebra's data types:

| Data type | Merge strategy | Rationale |
|-----------|---------------|-----------|
| **Goal/task state** | Last-writer-wins per field | State transitions are monotonic (CREATED→RUNNING→COMPLETE) — LWW is safe |
| **Knowledge entries** | Last-writer-wins with tombstone | Owner's edits win; deletions propagate |
| **Process properties** | Last-writer-wins per key | Each task writes distinct keys — true conflicts are rare |
| **Episodic memory** | Append-only set | Observations are additive — no conflicts |
| **RBAC grants** | Add-wins set | Adding a permission should not be undone by a concurrent removal race |
| **Budget/cost counters** | PN-Counter (positive-negative counter) | Allows concurrent increment/decrement and converges to correct total |

---

## 5. Layer 2: Capability-Based Access Control

### 5.1 Why Not Server RBAC

Traditional RBAC has a central authority that checks "is user X allowed to do Y". In a local-first system there is no central authority. We need access control that:

- Works offline (the device can evaluate permissions locally)
- Is decentralised (no single point of authority)
- Is cryptographically verifiable (you can't forge a permission)

### 5.2 Signed Capability Tokens

A **capability** is a signed token granting a specific permission:

```
Capability {
    id: uuid
    issuer: public_key          # Who granted this
    subject: public_key         # Who receives this
    scope: {
        domain: "finance"       # Which domain
        access: "read_write"    # What level
        resources: ["goals", "budgets"]  # Which data types
    }
    constraints: {
        expires: "2027-01-01"   # Optional expiry
        delegatable: false      # Can subject re-grant?
    }
    signature: ed25519_sig      # Issuer's signature
}
```

### 5.3 Capability Chain

- **Household creator** generates a root keypair. This is the trust anchor.
- Creator issues capabilities to family members' public keys.
- Each device stores its user's private key in the OS keychain.
- When syncing, each change carries the capability chain proving the author is authorised.
- Devices validate the chain locally — no server needed.

For **team/org** (REQ-USR-004):
- The org admin's key is the root.
- Org policies are signed documents: "finance domain is always SUPERVISED" — signed by the admin key.
- Devices enforce policies locally by checking the signed policy document.

### 5.4 Revocation

Revocation in decentralised systems is hard (the "negative credential" problem). Options:

1. **Short-lived capabilities with renewal**: Capabilities expire every N days. Non-renewal = revocation. Requires periodic online check-in.
2. **Revocation list**: The issuer publishes a signed revocation list. Devices fetch it when online and cache locally.
3. **Epoch-based rotation**: The household rotates the shared domain encryption key periodically. Revoked users don't get the new key.

**Recommendation**: Combine (1) and (2). Short-lived capabilities (e.g., 30-day expiry) with a lightweight revocation list for immediate revocation. This balances offline capability with timely access removal.

### 5.5 Privacy Boundaries

Private domains are not just access-controlled — they're **invisible**:

- Private domain data is encrypted with the user's personal key
- The CRDT sync layer never replicates private domain data
- There's no "encrypted blob you can see but can't read" — the data simply isn't in the shared sync scope
- The sync scope is configured per-domain: `sync: none | private | shared`

---

## 6. Layer 3: Sync Transport

### 6.1 Peer-to-Peer (LAN)

For household devices on the same network:
- mDNS discovery of Zebra peers
- Direct WebSocket connection for low-latency sync
- No external server needed

### 6.2 Relay Server (WAN)

For devices not on the same network:
- A lightweight relay server that stores-and-forwards encrypted CRDT change packets
- The relay sees only encrypted blobs — it cannot read the data
- Can be self-hosted or provided as a service
- This extends the existing REQ-DATA-002 cloud sync infrastructure

### 6.3 Sync Protocol

```
1. Device connects to peer (or relay)
2. Exchange vector clocks to determine what each side is missing
3. Push missing changesets (each changeset is signed by author's capability)
4. Receiver validates capability chain
5. If valid: apply changes via cr-sqlite merge
6. If invalid: reject and log (potential security event)
```

---

## 7. How This Maps to Requirements

### REQ-USR-003 (Family/Household)

- Each family member has a keypair and a local Zebra instance
- Household creator issues capabilities for shared domains
- Shared domains (Home, Finance) sync via CRDTs
- Private domains (Health, Creative) stay local — not even in the sync scope
- The agent distinguishes context via the user's keypair identity

### REQ-USR-004 (Team/Organisation)

- Org admin keypair is the trust root
- RBAC is expressed as capability grants: role → set of capabilities
- Org policies are signed documents enforced locally
- "Finance always supervised" = a signed policy that overrides per-user trust level
- Team goals sync across members with write access to the relevant domain

### REQ-DATA-001 (Local-First)

- Fully preserved. The local SQLite database remains the primary store.
- CRDT extensions add sync capability but don't require it.
- A device with no peers functions identically to today.

### REQ-DATA-002 (Cloud Sync)

- The relay server is the Phase 2 cloud sync mechanism.
- Phase 3 extends it from single-user multi-device to multi-user multi-device.
- Same encryption, same client-side key management.

---

## 8. Migration Path

### Phase 1 (No change)
- Local SQLite, single user, no sync

### Phase 2 (Cloud Sync)
- Add cr-sqlite extension to SQLite
- Add CRDT metadata columns to synced tables
- Implement relay server for encrypted changeset forwarding
- Single user, but the sync infrastructure is reusable for Phase 3

### Phase 3 (Multi-User)
- Add keypair generation and capability token model
- Add capability validation to the sync protocol
- Add domain-level sync scope configuration (none/private/shared)
- Add org policy document model
- LAN peer discovery (mDNS)

The key insight: **Phase 2 cloud sync and Phase 3 multi-user use the same CRDT sync mechanism**. Phase 3 adds the capability layer on top, not a different architecture.

---

## 9. Technology Candidates

| Component | Candidates | Notes |
|-----------|-----------|-------|
| CRDT storage | [cr-sqlite](https://vlcn.io/docs/cr-sqlite), [Electric SQL](https://electric-sql.com/) | cr-sqlite is lighter, Electric SQL has more features |
| Capability signing | Ed25519 via [PyNaCl](https://pynacl.readthedocs.io/) | Fast, small signatures, well-supported |
| Key storage | OS keychain (via [keyring](https://pypi.org/project/keyring/)) | Platform-native secure storage |
| LAN discovery | [zeroconf](https://pypi.org/project/zeroconf/) (Python mDNS) | Mature, cross-platform |
| Relay server | Lightweight WebSocket relay (custom, minimal) | Stores-and-forwards encrypted blobs only |
| Encryption | XChaCha20-Poly1305 (via PyNaCl) | Fast authenticated encryption |

---

## 10. Open Questions

1. **Capability UX**: How do household members exchange public keys and capabilities? QR code? Shared secret? This needs to be simple enough for non-technical family members.

2. **Agent identity**: In multi-user, is there one agent instance per user, or one shared agent? The requirements suggest separate relationship contexts (REQ-USR-004), which implies per-user agent instances that share data, not a single shared agent.

3. **Conflict notification**: When CRDTs auto-merge concurrent edits, should the agent notify users? "Your partner also edited the grocery budget — here's what merged."

4. **cr-sqlite maturity**: cr-sqlite is relatively new. We should evaluate its stability and whether we need a fallback strategy (e.g., application-level CRDTs over plain SQLite).

5. **Org policy enforcement**: With local enforcement of signed policies, a malicious device could ignore the policy. Is this acceptable (trust the device), or do we need the relay to also enforce?

---

## 11. References

- [Local-First Software](https://www.inkandswitch.com/local-first/) — Ink & Switch (foundational paper)
- [CRDTs: The Hard Parts](https://martin.kleppmann.com/2020/07/06/crdt-hard-parts-hydra.html) — Martin Kleppmann
- [cr-sqlite](https://vlcn.io/docs/cr-sqlite) — CRDT-native SQLite extension
- [Object Capabilities](https://en.wikipedia.org/wiki/Object-capability_model) — Capability-based security model
- [Matrix Spec](https://spec.matrix.org/) — For reference on decentralised auth and federation
