# F7: OS Keychain Credential Store

**GitLab issue**: #7  
**Requirements**: REQ-DATA-006, REQ-INT-002  
**Status**: Implemented

---

## 1. Goal & scope

Replace `.env`-based secret handling with a proper credential store backed by the
OS keychain (macOS Keychain, Secret Service on Linux, Windows Credential Manager)
with a filesystem fallback for headless/CI environments.

**In scope:**
- `CredentialStore` ABC + `InMemoryCredentialStore` in `storage/interfaces.py`
- `KeyringCredentialStore` and `FileCredentialStore` in `storage/credentials.py`
- `zebra-agent credential` CLI subcommands (set / get / list / delete)
- `ScrubCredentialsFilter` logging filter
- Default registration of `credential_store` in `ZebraContainer`

**Out of scope:**
- DEK/KEK envelope encryption (REQ-DATA-006 — deferred; credential values are
  currently stored as plaintext within the OS keychain or 0600 files)
- Integration with `IntegrationProvider` framework (F8+)
- Django ORM-backed `DjangoCredentialStore` (F7 targets CLI/standalone usage)

---

## 2. Data model changes

### New types in `zebra_agent/storage/interfaces.py`

```python
@dataclass
class CredentialKey:
    user_id: str
    integration_name: str
    credential_type: str

class CredentialStore(ABC):
    async def get(user_id, integration_name, credential_type) -> str | None
    async def set(user_id, integration_name, credential_type, value) -> None
    async def delete(user_id, integration_name, credential_type) -> None
    async def list(user_id) -> list[CredentialKey]

class InMemoryCredentialStore(CredentialStore):
    """For testing; no persistence."""
```

Credentials are indexed by `(user_id, integration_name, credential_type)`.

### FileCredentialStore on-disk layout

```
~/.zebra-agent/credentials/
  <user_id>/
    .index.json               # [{user_id, integration_name, credential_type}, ...]
    <integration_name>/
      <credential_type>.cred  # raw value, mode 0600
```

All directories are created with mode 0700. All `.cred` files are mode 0600.

### Keyring namespace

`zebra/<user_id>/<integration_name>/<credential_type>` (the service name passed to
the `keyring` library).

---

## 3. API / interface changes

### New module: `zebra_agent/storage/credentials.py`

- `KeyringCredentialStore` — wraps `keyring` library; supports enumeration only
  via `list()` returning `[]` (keyring backends don't expose enumeration).
- `FileCredentialStore(base_dir=None)` — filesystem backend; full CRUD + list.

### New module: `zebra_agent/logging_filters.py`

- `ScrubCredentialsFilter` — `logging.Filter` that regex-redacts patterns like
  `api_key=<value>`, `token=<value>`, `password=<value>`, `secret=<value>` from
  log messages and string args.

### New CLI: `zebra_agent/cli.py`

Entry point: `zebra-agent` (registered in `pyproject.toml` `[project.scripts]`).

```
zebra-agent [--user USER] [--backend {keyring,file,memory}] credential set <integration> <type> <value>
zebra-agent [--user USER] [--backend {keyring,file,memory}] credential get <integration> <type>
zebra-agent [--user USER] [--backend {keyring,file,memory}] credential list
zebra-agent [--user USER] [--backend {keyring,file,memory}] credential delete <integration> <type>
```

`get` outputs a masked value (`***<last-4>`) — for verification only.

### ZebraContainer update (`ioc/container.py`)

`ZebraContainer.__init__()` now calls `_register_default_credential_store()` which
registers `KeyringCredentialStore` (or `FileCredentialStore` if `keyring` is absent)
as a singleton under the name `credential_store`.

---

## 4. Control flow

Credentials are accessed synchronously by the CLI via `asyncio.run()`. In the
workflow engine they are accessed through the `CredentialStore` interface from
`context.extras["__credential_store__"]` (the caller must inject the store — no
injection is performed automatically by this change).

---

## 5. Configuration

| Setting | Default | Notes |
|---------|---------|-------|
| `--backend` CLI flag | `keyring` | Per-invocation override |
| `base_dir` (FileCredentialStore) | `~/.zebra-agent/credentials/` | Constructor arg |

No new env vars or Django settings are introduced in F7.

---

## 6. Open questions / risks

- **Keyring enumeration gap**: `KeyringCredentialStore.list()` always returns `[]`
  because the `keyring` library does not expose a cross-backend enumerate API.
  Callers that need listing should use `FileCredentialStore`.
- **Envelope encryption deferred**: credential values are stored as plaintext in
  the OS keychain or in 0600 files.  The DEK/KEK design (REQ-DATA-006) is
  described in `zebra-to-be.md §11` and targeted for a later change.
- **No Django backend**: the web app currently has no `DjangoCredentialStore`.
  Integration tokens for web users should be wired via the file or keyring
  backend on the server, or a future Django implementation.
