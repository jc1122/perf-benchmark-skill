# QA Hardening Design

## Context

The standalone `perf-benchmark-skill` repository has stabilized functionally,
but the QA review exposed structural weaknesses:

1. The code lives in one 1,700+ line script with several oversized functions.
2. The test suite is mostly white-box and helper-oriented, with limited
   end-to-end contract coverage.
3. The repository has no active Python quality configuration (`pyproject.toml`,
   Ruff, or pre-commit hooks).
4. The implementation already has natural concurrency boundaries, but the code
   and docs do not clearly separate timing-sensitive work from safe parallel
   work.

The user explicitly chose:
- a **small module split is acceptable**
- **internal safety matters**

That means the refactor should improve structure without aggressively replacing
internal tests with black-box tests. We should add contract coverage while
keeping internal regression guards.

## Chosen Approach

Apply a small, behavior-preserving module split while keeping the existing
entrypoint script path stable:

- Move the current script logic into a small internal package under `scripts/`
  with focused modules for stages, scoring/reporting, and CLI/runtime.
- Keep `scripts/perf_benchmark_pipeline.py` as the executable shim so the skill
  contract and docs do not break.
- Add a handful of end-to-end tests for `main()` that assert output artifacts,
  while preserving existing internal helper tests.
- Add minimal Ruff and pre-commit configuration for lightweight quality gates.
- Tighten documentation about which work is safe to parallelize in code and via
  subagents.

## Alternatives Considered

### 1. Leave the code monolithic and only add more tests

Rejected. It would improve coverage but preserve the main maintainability
problem: all orchestration, scoring, parsing, and reporting remain entangled in
one file.

### 2. Full package redesign

Rejected. A larger package and API redesign would create churn without clear
benefit for a small standalone skill repo.

## Boundaries

- No behavior changes to the benchmark pipeline unless needed to preserve the
  current tested contract during the split.
- No attempt to “black-box only” the suite; internal safety remains a goal.
- No performance-sensitive changes to Tier 1 timing logic.

## Expected Outcome

- Smaller modules with the same CLI contract.
- Better test pyramid balance via added end-to-end artifact tests.
- Lightweight Python quality tooling that can run in CI and pre-commit.
- Clearer guidance on parallelization opportunities and limits.
