# health-metrics-reporting Specification

## Purpose
TBD - created by archiving change health-metrics-uncertainty. Update Purpose after archive.

## Requirements

### Requirement: Sample sizes and intervals on success rates
The metrics analysis SHALL report, for each workflow, the number of successful runs, the number of eligible runs and a 95% Wilson score interval for the success rate, and the health report prompt SHALL show them next to every rate.

#### Scenario: Small sample
- **WHEN** a workflow has 3 successful runs out of 3 in the window
- **THEN** its stat shows `successful_runs: 3`, `total_runs: 3` and an interval whose lower bound is below 0.5

#### Scenario: Prompt text
- **WHEN** the evaluator prompt is built from the analysis
- **THEN** each workflow line reads `successes/runs`, the percentage and the interval

### Requirement: Data sufficiency distinguishes no runs from too few
The analysis SHALL label each known workflow `none` (no eligible runs), `insufficient` (fewer than the minimum runs) or `adequate`, and SHALL list workflows with no runs instead of omitting them.

#### Scenario: Zero-run workflow
- **WHEN** a known workflow has no goal runs in the window
- **THEN** it appears with `confidence: none`, no interval and no success rate claim

#### Scenario: Thin data not judged
- **WHEN** a workflow is `insufficient` or `none`
- **THEN** the prompt tells the model not to assess its health

### Requirement: Performer categories respect uncertainty
A workflow SHALL be a high performer only when it is `adequate` and the lower bound of its interval is at least 0.7 with a rate of at least 0.9.

#### Scenario: Perfect but tiny
- **WHEN** a workflow succeeds 3 of 3 times
- **THEN** it is not in `high_performers`
