# Strict Summary Rendering Design

## Context

The latest review found three remaining contract issues in the standalone
`perf-benchmark-skill` repo:

1. `benchmark_summary.json` can disagree with the rubric scorer for wall-time
   stability when pytest-benchmark data exists.
2. Explicit `--target` still allows synthetic size labels for fixed commands
   when `--sizes` is present but `{SIZE}` is absent.
3. The markdown report hides zero-valued algorithmic evidence because it uses
   truthiness-based value selection.

These are all output or validation defects. They do not require a new CLI
shape, only stricter alignment between the scorer, summary, and reporting
paths.

## Chosen Approach

Apply strict end-to-end alignment:

- Make summary wall-time metrics prefer pytest-benchmark data, matching the
- scorer’s precedence.
- Reject explicit `--target` whenever `--sizes` is used without `{SIZE}`,
  including the single-size case.
- Add a report formatting helper that preserves zero-valued metrics.

## Alternatives Considered

### 1. Fix JSON/report only

Rejected. It would still allow misleading single-size explicit-target metadata.

### 2. Larger CLI redesign

Rejected. A separate “parameterized target” mode would be cleaner, but it is
not necessary for the reviewed defects.

## Implementation Notes

- Follow TDD strictly: tests first, verify red, then patch minimal code.
- Reuse scorer-derived wall-time logic instead of adding a second metric path.
- Keep docs honest if the validation contract changes.
