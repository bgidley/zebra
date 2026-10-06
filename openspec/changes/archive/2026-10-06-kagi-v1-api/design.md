## Context

Kagi moved its API to v1 (`https://kagi.com/api/v1`, OpenAPI at kagi.com/api/docs). v1 exposes only `POST /search` and `POST /extract`, authenticated with `Authorization: Bearer <key>`. Keys created in the new portal are rejected by v0.

## Decisions

- **Keep `kagi_search`'s output contract.** Workflows template `{{search_results}}`; only the transport changes. v1 has no `rank`, so rank is the list position. v1's `limit` is per category and advisory, so the action also slices to `limit` itself. Only the `search` (web) category is returned; news/video/image categories are ignored.
- **Replace rather than emulate the summarizer.** Emulating `kagi_summarize` with extract + an LLM call would hide an LLM cost inside a "web" action and duplicate `llm_call`. `kagi_extract` returns markdown (capped by `max_chars`, default 20 000, to keep process properties small); workflows summarise with `llm_call`.
- One URL per task; a per-page failure (`data[0].error`, no `markdown`) fails the task with Kagi's reason.

## Risks / Trade-offs

- Removing `kagi_summarize` breaks any user-authored workflow that referenced it; none exist in the repo, and the action could not authenticate with current keys anyway.
