## Why

Accepting a *Zebra Improvement Request* (#189) only records the verdict; someone still has to copy the request into GitLab by hand. GitLab issue #194 (related: #189, #193).

## What Changes

- New `file_improvement_issue` task action (`zebra_tasks/agent/improvements.py`): when the review verdict is `accepted` and the reviewer gave no issue link, it creates an issue on the Zebra GitLab project from the request (title, problem, evidence, suggested change, reviewer notes, link to the dream cycle) with the `dream-request` label, and stores `filed_issue = {url, iid}` on the process. Any other verdict, or a reviewer-supplied link, skips without a call.
- GitLab text from the LLM is neutralised: lines starting with `/` cannot run quick actions and `@` mentions cannot notify people.
- `zebra_improvement_request.yaml` v2: `review → file_issue`.
- The step never fails the request: missing `ZEBRA_GITLAB_TOKEN`, network or API errors are recorded in `filed_issue.error`.
- `/dreams/` shows the filed issue link (reviewer link first) or the filing error.
- Deploy copies `ZEBRA_GITLAB_TOKEN` (masked, protected CI variable) into `prod.env`; `ZEBRA_GITLAB_URL` (default `https://gitlab.com`) and `ZEBRA_GITLAB_PROJECT` (default `gidley/zebra`) configure the target.
- Fixes the version part of #193: earlier requests are found across every version of the request workflow, so bumping to v2 keeps dedupe.

## Outcomes

| # | Outcome | How we'll know |
|---|---------|----------------|
| O1 | Accepting a request with no issue link creates one GitLab issue on gidley/zebra and the request records its URL | Test with a mocked GitLab API: POST to `/projects/gidley%2Fzebra/issues` with the request title and body; `filed_issue.url` set; `/dreams/` links it |
| O2 | Nothing is filed unless the human accepted it, and never twice | Tests: rejected / duplicate / later and a reviewer-supplied link make no API call; a re-run with `filed_issue.url` set makes no call; a re-run after the POST succeeded but the URL was not saved finds the existing issue by its `zebra-request:<process id>` marker instead of creating another; a re-run after an error retries |
| O3 | Filing problems never break or lose the request | Tests: missing token, timeout, network error, non-2xx each complete the process with `filed_issue.error` (never containing the token), shown on `/dreams/` |
| O4 | LLM-written text cannot run quick actions or notify people | Table-driven test over `/close`, ` /assign @x`, `/label ~y`, `/spend 1h` lines and `@user` / `@group/sub` mentions in title and body; `#123` / `!45` links are out of scope |
| O5 | Dedupe survives this change's request-workflow bump to v2 | Test: a v1 request's title still blocks the same title once the library holds v2 |
| O6 | Live in prod with the token wired | Deploy copies `ZEBRA_GITLAB_TOKEN` into prod.env; from `zebra-web`, an authenticated issue search (`GET /projects/gidley%2Fzebra/issues?search=…`) returns 200 (token never printed; the fine-grained work-items token cannot read the project itself); one real issue filed through `file_improvement_issue` in prod, then closed |

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `dream-improvement-requests`: accepted requests are filed as GitLab issues; dedupe across workflow versions.

## Impact

- `zebra-tasks/zebra_tasks/agent/improvements.py`, `zebra-tasks/pyproject.toml`
- `zebra-agent/workflows/zebra_improvement_request.yaml` v2
- `zebra-agent-web/zebra_agent_web/api/dream_history.py`, `templates/pages/dream_cycles.html`
- `scripts/deploy-podman.sh`, `README-CICD.md`, `specs/podman-single-host-design.md`, single-host-deployment spec
- Tests in `zebra-tasks/tests/test_improvement_requests.py`, `zebra-agent/tests/test_dream_cycle_workflow.py`, `zebra-agent-web/tests/unit/test_dream_cycles_page.py`
