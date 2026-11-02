## ADDED Requirements

### Requirement: Ship results carry the branch diff read on the host
A `propose` or `ship` result SHALL include `diff_excerpt`, the branch's diff against the base
branch from the same host-side compare call as its changed files, redacted of every builder
credential and capped at the patch excerpt size, and `diff_truncated` saying whether it was cut.

#### Scenario: Large diff
- **WHEN** the compare diff is longer than the excerpt cap
- **THEN** `diff_excerpt` is cut to the cap and `diff_truncated` is true
