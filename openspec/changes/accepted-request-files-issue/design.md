## Context

#189 added *Zebra Improvement Request* processes with one human review task. The reviewer can paste an issue link but nothing files one. GitLab.com project/group access tokens need a paid plan (the `gidley` group is Free), so the token is a personal access token (preferably of a bot user with Reporter on the project) stored as the masked, protected CI variable `ZEBRA_GITLAB_TOKEN`.

## Decisions

- **Request-specific action, always routed.** `review → file_issue`; the action reads `__task_output_review` and decides. No route buttons on the human form, no generic GitLab action until something else needs one.
- **Skip rules**: verdict not `accepted` → `skipped: not accepted`; reviewer `issue_url` → `skipped: reviewer linked an issue`; `filed_issue.url` already set → `skipped: already filed` (idempotent on recovery re-run). A previous `filed_issue.error` does not skip: a re-run retries.
- **Never twice across a crash**: the body ends with a `zebra-request:<process id>` marker. Before POSTing, the action searches the project's issues (`GET …/issues?search=<marker>&in=description&state=all`) and adopts an issue whose description contains the backtick-wrapped marker exactly, instead of creating another. If the search fails it records an error and does not POST (it cannot rule out an earlier issue). A re-run happens only through crash recovery (`idempotent: true`); otherwise the reviewer pastes a link.
- **Body**: request markdown + reviewer notes + "Raised by Zebra's dream cycle (process …), accepted on /dreams/". Lines whose first non-space character is `/` get a leading `\` (GitLab only runs quick actions at line start); `@` gets a zero-width space after it. Title is clipped to 255 and gets the same `@` treatment.
- **Label** `dream-request` (GitLab creates it on first use).
- **Never fails**: errors go to `filed_issue.error` (token value never logged or stored); `TaskResult.ok` always.
- **Config**: `ZEBRA_GITLAB_TOKEN`, `ZEBRA_GITLAB_URL` (`https://gitlab.com`), `ZEBRA_GITLAB_PROJECT` (`gidley/zebra`); timeout 15s; `PRIVATE-TOKEN` header.
- **Dedupe across versions (#193)**: `_earlier_titles` collects ids of every stored definition named *Zebra Improvement Request* (`store.list_definitions()`) and lists processes for each. The per-user scoping of `DjangoStore.list_processes` for user-started cycles stays open on #193.
- **v1 processes in flight** keep their v1 definition and finish without filing; the reviewer can still paste a link.

## Risks

- A personal token on the owner's account reaches all their projects; a bot user limits that. The action only ever POSTs one issue to the configured project.
- Prompt-injected findings could shape issue text; quick actions and mentions are neutralised, and nothing is filed without a human accepting it.
