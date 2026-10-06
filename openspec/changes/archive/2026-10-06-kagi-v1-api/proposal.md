## Why

The Kagi API key expired, and newly generated keys return `401 Unauthorized` on the legacy `/api/v0/search` and `/api/v0/summarize` endpoints — they only authenticate against `https://kagi.com/api/v1`. `kagi_search` (used by `web_search.yaml`) is therefore broken in prod. Issue #145.

## What Changes

- `kagi_search` calls `POST /api/v1/search` (Bearer auth, JSON body) and reads web results from `data.search[]`. Output shape (`results[{rank,url,title,snippet,published}]`, `query`, `total`) is unchanged; `rank` is now the 1-based position and `published` comes from `time`.
- **BREAKING**: `kagi_summarize` is removed — Kagi v1 has no summarizer endpoint. It is replaced by `kagi_extract` (`POST /api/v1/extract`), which returns a page's content as markdown; pair it with `llm_call` to summarise. No shipped workflow used `kagi_summarize`.
- `KAGI_API_KEY` rotated in GitLab CI variables and the host `prod.env` (operational, not code).

## Capabilities

### New Capabilities
- `web-search`: Kagi-backed web search and page extraction task actions.

### Modified Capabilities
<!-- none -->

## Impact

- `zebra-tasks/zebra_tasks/web/kagi_search.py`, new `kagi_extract.py`, removed `kagi_summarize.py`; entry points in `zebra-tasks/pyproject.toml`.
- Tests in `zebra-tasks/tests/web/`.
