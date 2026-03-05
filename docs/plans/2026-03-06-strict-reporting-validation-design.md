# Strict Reporting Validation Design

## Context

The latest review found three contract problems in the standalone
`perf-benchmark-skill` repo:

1. Explicit `--target` runs can use `--sizes` without a `{SIZE}` placeholder,
   which labels repeated identical commands as different input sizes.
2. `benchmark_summary.json` still computes pooled wall-time metrics even though
   the rubric scorer now evaluates explicit multi-size runs per input size.
3. The markdown report collapses all strict Dimension 0 `N/A` cases into the
   same “run at >= 2 sizes” advice and hides which rubric sub-checks are
   actually missing.

These issues are real behavior defects, not just documentation drift. They
break the repo-agnostic contract and make the summary/report disagree with the
scoring logic.

## Chosen Approach

Apply the strict contract end-to-end.

- Add hard validation for `--target` plus `--sizes`: if more than one size is
  requested, the explicit target must include `{SIZE}`.
- Make the JSON summary derive wall-time statistics from the same per-size
  grouping used by the scorer.
- Make the markdown report surface strict `N/A` causes using
  `missing_sub_checks` instead of generic stale advice.
- Update README and SKILL docs so the repo-agnostic examples and expectations
  match the enforced behavior.

## Alternatives Considered

### 1. Reporting-only patch

Rejected. It would leave the CLI able to fabricate scaling evidence from fake
size labels.

### 2. Larger CLI redesign

Rejected. Adding separate fixed-size and parameterized target modes would be
cleaner, but it is unnecessary for these review findings.

## Implementation Notes

- Follow TDD strictly: add failing tests first for validation, summary
  consistency, and strict `N/A` report messaging.
- Keep the existing CLI shape; add validation rather than new flags.
- Preserve current explicit-binary behavior.
- Sync the installed skill after the standalone repo is verified.
