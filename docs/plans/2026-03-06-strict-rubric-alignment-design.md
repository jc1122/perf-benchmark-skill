# Strict Rubric Alignment Design

**Goal:** Align the perf-benchmark skill's implementation, schema, and published guidance with the documented scoring rubric so scores are defensible and reproducible.

**Context:** A full review found four issues in the current `main` branch:
- Dimension 0 can return `PASS` from incomplete evidence.
- Call amplification is scored with a looser proxy and thresholds than the rubric documents.
- Wall-time stability pools measurements from different input sizes for explicit `--target` / `--binary` runs.
- The finding schema cannot represent the `N/A` results that the implementation already emits.

## Chosen Approach

Use strict rubric alignment rather than relaxing the docs:

1. Make Dimension 0 require all six sub-checks to be present and passing before it can score `PASS`.
2. Change call amplification scoring to match the published rubric thresholds and language, while keeping the current implementation honest about what it can measure.
3. Compute wall-time stability per input size for repo-agnostic timing runs, then aggregate within-size CVs instead of mixing different workload sizes.
4. Expand the finding schema so `N/A` results are valid outputs when evidence is unavailable.

## Alternatives Considered

### Docs-only correction

This would be cheaper, but it would leave the scoring defects in place and the reported totals would still be misleading.

### Partial-evidence WARN fallback

This is less strict, but it still changes the published rubric contract. The current repo already presents the rubric as normative, so the implementation should conform to it.

## Design Details

### Dimension 0

- Treat each documented sub-check as required evidence.
- If fewer than six sub-checks are available, Dimension 0 returns `N/A` rather than `PASS`.
- Preserve the existing composite rule once all six checks exist:
  - any `FAIL` => `FAIL`
  - two or more `WARN` => `WARN`
  - otherwise `PASS`

### Call Amplification

- Score against the documented thresholds from `references/rubric.md`.
- Update the code comment and variable naming so the implementation no longer implies true `call_count` if it is still using instruction-derived data.
- If the underlying metric cannot support the rubric honestly, downgrade to `N/A` instead of inventing confidence.

### Wall-Time Stability

- For explicit `--target` / `--binary` runs with `--sizes`, compute CV independently per input size.
- Aggregate stability from the per-size CV values rather than the raw pooled timings.
- Keep existing pytest-benchmark behavior unchanged.

### Finding Schema

- Allow `score = -1` and empty evidence when `tier = "N/A"`.
- Keep the stricter requirements for `PASS` / `WARN` / `FAIL`.

## Files

- Modify: `scripts/perf_benchmark_pipeline.py`
- Modify: `tests/test_perf_benchmark_pipeline.py`
- Modify: `references/rubric.md`
- Modify: `references/finding-schema.json`

## Verification

- Focused red-green cycle in `tests/test_perf_benchmark_pipeline.py`
- Full `pytest -q`
- `python3 -m py_compile scripts/perf_benchmark_pipeline.py`
- `python3 scripts/perf_benchmark_pipeline.py --help`
