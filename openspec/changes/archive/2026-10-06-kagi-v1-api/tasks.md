## 1. Implementation

- [x] 1.1 Migrate `kagi_search` to `POST /api/v1/search` with Bearer auth and `data.search[]` parsing
- [x] 1.2 Add `kagi_extract` action on `POST /api/v1/extract`; register entry point
- [x] 1.3 Remove `kagi_summarize` action, tests and entry point

## 2. Tests and docs

- [x] 2.1 Update `kagi_search` tests for v1 request/response shape; add `kagi_extract` tests
- [x] 2.2 Live check of both actions against Kagi v1 with the rotated key
- [x] 2.3 Sync `specs/zebra-as-is.md`

## 3. Operations

- [x] 3.1 Rotate `KAGI_API_KEY` in GitLab CI variables and host `prod.env`
