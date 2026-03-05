# Perf Benchmark Skill Review Findings Design

## Context

The standalone `perf-benchmark-skill` repository contains the source of truth
for the published skill. A prior review found five concrete issues:

1. `SKILL.md` and `README.md` contain incorrect invocation paths and examples.
2. Baseline regression comparison is documented as cross-dimension blocking, but
   the implementation only compares memory usage.
3. Stage 3 is skipped entirely when Valgrind is unavailable, even though
   `perf stat` and `objdump` do not depend on Valgrind.
4. `--env` is not propagated to `perf stat`, which makes measurements
   inconsistent across stages.
5. ASM artifact discovery is too strict for Python extension modules and often
   produces no disassembly files.

## Goals

- Fix the implementation defects without changing the public CLI shape.
- Make the published docs match actual behavior.
- Add regression tests that lock the reviewed issues down.
- Keep the repository self-contained; no changes in `DegreeGraph2`.

## Chosen Approach

Use a targeted bugfix approach:

- Add focused tests around pipeline control flow and baseline comparison.
- Refactor Stage 3 orchestration so Valgrind-backed tasks and non-Valgrind tasks
  are gated independently.
- Extend rubric/report generation with explicit baseline regression comparison
  across scored dimensions.
- Broaden ASM discovery to inspect likely compiled artifact locations instead of
  requiring a path substring match.
- Correct the skill docs to reference the real script path and the implemented
  regression behavior.

This keeps the pipeline architecture intact while fixing the reviewed defects.

## Rejected Alternatives

### Docs-only correction

This would make the skill less misleading, but it would leave the actual
runtime defects in place. The review findings would still stand.

### Full pipeline redesign

This would add unnecessary risk for a bugfix pass. The issues are localized and
do not require a new architecture.

## Testing Strategy

- Add a `pytest` test module for:
  - Stage 3 gating without Valgrind
  - `--env` propagation in `perf stat`
  - Baseline regression comparison output
  - ASM discovery coverage for extension modules
- Run the new test module first to observe failures.
- Run the full test module after implementation.
- Verify the script still parses and exposes `--help`.

## Documentation Strategy

- Update `SKILL.md` frontmatter description to describe triggering conditions,
  not the workflow.
- Fix example paths and commands in `SKILL.md`.
- Update `README.md` to reflect the corrected invocation model and baseline
  comparison semantics.

## Delivery

- Commit fixes on a dedicated branch in the standalone repo.
- Push the branch to GitHub.
