## ADDED Requirements

### Requirement: Web search uses the Kagi v1 Search API
The `kagi_search` action SHALL query `POST https://kagi.com/api/v1/search` with a JSON body containing `query` and `limit` and an `Authorization: Bearer <KAGI_API_KEY>` header, and SHALL return only web results from `data.search`, each as `{rank, url, title, snippet, published}`, with at most `limit` results (clamped to 1–100).

#### Scenario: Successful search
- **WHEN** Kagi returns two web results and one video result for the query
- **THEN** the action succeeds with `total` = 2, ranks 1 and 2, `published` taken from each result's `time`, and stores the results under `output_key`

#### Scenario: Missing API key
- **WHEN** `KAGI_API_KEY` is not set
- **THEN** the action fails with an error naming `KAGI_API_KEY` and makes no request

#### Scenario: API error
- **WHEN** Kagi responds with a non-2xx status
- **THEN** the action fails with the status code and response body in the error

### Requirement: Page extraction uses the Kagi v1 Extract API
The `kagi_extract` action SHALL fetch a single URL via `POST https://kagi.com/api/v1/extract` (body `{"pages": [{"url": ...}]}`, Bearer auth) and SHALL return the page's markdown, truncated to `max_chars` (default 20 000), with a `truncated` flag, storing the markdown under `output_key` (default `page_content`).

#### Scenario: Successful extraction
- **WHEN** Kagi returns markdown for the requested URL
- **THEN** the action succeeds with `markdown`, `url` and `truncated` = false

#### Scenario: Content longer than max_chars
- **WHEN** the extracted markdown exceeds `max_chars`
- **THEN** the returned and stored markdown is cut to `max_chars` and `truncated` = true

#### Scenario: Page could not be extracted
- **WHEN** Kagi returns the page with an `error` and no `markdown`
- **THEN** the action fails with Kagi's error reason
