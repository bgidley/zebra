## ADDED Requirements

### Requirement: A request can be sent to Zebra to build
The request's review SHALL offer the verdict `build` ("Accept and let Zebra build it"), which is
filed as a GitLab issue like `accepted`. After filing, the request SHALL start one *Improve Zebra*
process for the filed issue, or for the issue the reviewer linked, and record it as
`improvement_build`. Any other verdict, or no issue, SHALL start nothing, and starting SHALL never
fail the request.

#### Scenario: Build chosen
- **WHEN** the reviewer chooses `build` and the issue is filed as #42
- **THEN** an Improve Zebra process for issue 42 is running and `improvement_build` names it

#### Scenario: Accepted only
- **WHEN** the reviewer chooses `accepted`
- **THEN** the issue is filed and `improvement_build` records a skip
