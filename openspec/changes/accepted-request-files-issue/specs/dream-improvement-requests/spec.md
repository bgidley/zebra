## MODIFIED Requirements

### Requirement: Requests are few and not repeated
The step SHALL start at most `max_requests` (default 2) requests per cycle. It SHALL NOT start a request whose normalised title matches an earlier *Zebra Improvement Request* process in any state and of any version of that workflow, and SHALL show the earlier titles to the LLM.

#### Scenario: Cap
- **WHEN** the LLM proposes more requests than `max_requests`
- **THEN** only the first `max_requests` are started

#### Scenario: Duplicate of an earlier request
- **WHEN** a proposal's title matches an earlier request, ignoring case and punctuation
- **THEN** no new process is started and the proposal is reported as skipped

#### Scenario: Earlier request from an older workflow version
- **WHEN** an earlier request was made with version 1 of the request workflow and the library now holds version 2
- **THEN** a proposal with the same title is still skipped as a duplicate

### Requirement: Human reviews each request
A *Zebra Improvement Request* SHALL wait on one human task whose form shows the request and records a verdict (`accepted`, `rejected`, `duplicate`, `later`), an optional issue link and notes. It SHALL be a system workflow, never picked by the goal selector.

#### Scenario: Review recorded
- **WHEN** the human submits the review with verdict `accepted` and an issue link
- **THEN** the process completes without filing an issue and `/dreams/` shows the request as accepted with the reviewer's link

## ADDED Requirements

### Requirement: Accepted requests are filed as GitLab issues
After the review, a `file_improvement_issue` step SHALL create one issue on the configured GitLab project (`ZEBRA_GITLAB_PROJECT`, default `gidley/zebra`, at `ZEBRA_GITLAB_URL`, authenticated with `ZEBRA_GITLAB_TOKEN`) when the verdict is `accepted` and no issue link was given, and SHALL record `filed_issue = {url, iid}` on the process. It SHALL make no request for any other verdict, when the reviewer gave a link, or when an issue was already filed.

#### Scenario: Accepted without a link
- **WHEN** the reviewer accepts a request and leaves the issue link empty
- **THEN** one issue is created with the request title and a body holding the problem, evidence, suggested change, reviewer notes and the dream-cycle process id, labelled `dream-request`, and `/dreams/` links to it

#### Scenario: Not accepted
- **WHEN** the verdict is `rejected`, `duplicate` or `later`
- **THEN** no GitLab request is made

### Requirement: Issue text cannot act inside GitLab
The filed issue SHALL NOT be able to run GitLab quick actions or notify users: any line whose first non-space character is `/` SHALL be escaped and every `@` SHALL be broken so it is not a mention.

#### Scenario: Injected quick action
- **WHEN** the request text contains a line `/close` or `/assign @someone`
- **THEN** the posted body contains the text escaped so GitLab treats it as text

### Requirement: Filing never fails the request
A missing token, network error or non-2xx response SHALL be recorded in `filed_issue.error` without the token value, the process SHALL complete, and `/dreams/` SHALL show the error.

#### Scenario: No token configured
- **WHEN** `ZEBRA_GITLAB_TOKEN` is unset and a request is accepted
- **THEN** the process completes with `filed_issue.error` naming the missing variable and no request is made
