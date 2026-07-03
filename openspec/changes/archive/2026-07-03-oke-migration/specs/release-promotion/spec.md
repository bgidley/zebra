## ADDED Requirements

### Requirement: Build the image once per commit
The release pipeline SHALL build the `zebra-web` image once per commit and tag it with the git short SHA before any validation or deployment. Subsequent stages MUST reuse that tagged image rather than rebuilding.

#### Scenario: Image tagged by commit
- **WHEN** the build stage runs for commit `<sha>`
- **THEN** an image tagged `:<sha>` is pushed to OCIR

### Requirement: Smoke validation is isolated from prod
Smoke validation SHALL run the candidate `:<sha>` image in an ephemeral `smoke` namespace wired to a dedicated Oracle smoke schema, and MUST NOT read or write the prod schema or spend prod budget. The smoke namespace SHALL be torn down when the run completes, whether it passes or fails.

#### Scenario: Prod untouched by smoke
- **WHEN** the smoke suite runs against the ephemeral smoke instance
- **THEN** all database writes target the smoke schema
- **AND** the prod schema and prod budget are unchanged

#### Scenario: Ephemeral teardown
- **WHEN** the smoke run finishes (pass or fail)
- **THEN** the `smoke` namespace and its resources are deleted

### Requirement: Promote the validated image to prod
Deployment to prod SHALL promote the exact image that passed smoke by reference (`kubectl set image` to `:<sha>`), with no rebuild, so the deployed artifact is byte-identical to the validated one. The deploy stage MUST run only after the smoke stage succeeds.

#### Scenario: Same image promoted
- **WHEN** the deploy stage runs after a green smoke stage for `<sha>`
- **THEN** the prod `zebra-web` and `zebra-daemon` Deployments reference image `:<sha>`
- **AND** no image rebuild occurs during deploy

#### Scenario: Deploy gated on smoke
- **WHEN** the smoke stage fails
- **THEN** the deploy stage does not run and prod keeps the previous image

### Requirement: Pipeline ordering
The CI pipeline SHALL execute stages in the order `lint → test → e2e → build → smoke → deploy`, with `build`, `smoke`, and `deploy` running only on the master branch.

#### Scenario: Stage order on master
- **WHEN** a commit is pushed to master
- **THEN** stages run in order and `deploy` is reached only if every prior stage passed
