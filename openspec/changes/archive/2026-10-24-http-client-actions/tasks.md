## 1. Shared pieces

- [x] 1.1 Move the nested template resolver to `zebra_tasks/templating.py`; `notify_webhook` uses it
- [x] 1.2 `zebra_tasks/http/guard.py`: `check_url()` (public-address check + allow-list)
- [x] 1.3 `zebra_tasks/http/guard.py`: `load_credential()` / auth for bearer, basic, header

## 2. Actions

- [x] 2.1 `zebra_tasks/http/actions.py`: shared send (manual redirects, bounded body, output)
- [x] 2.2 `HttpGetAction` (`http_get`, always_reversible) and `HttpRequestAction`
      (`http_request`, always_irreversible)
- [x] 2.3 Entry points in `zebra-tasks/pyproject.toml`; `uv sync --all-packages`
- [x] 2.4 Creator prompt rule 10 names `http_request`

## 3. Tests

- [x] 3.1 Guard: blocked ranges, IPv4-mapped IPv6, allow-list, bad scheme
- [x] 3.2 Actions: JSON GET, query params, POST JSON, method check, redirects (same host, to
      internal, cross-host credential drop), credentials, truncation, status handling
- [x] 3.3 Trust-gate hint and gym `unsafe_reason` for both actions; action metadata

## 4. Docs

- [x] 4.1 `zebra-tasks/README.md`, `zebra-tasks/AGENTS.md`, `specs/zebra-as-is.md`
- [ ] 4.2 Prod check: `http_get` of `http://169.254.169.254/` in `zebra-web` is refused
