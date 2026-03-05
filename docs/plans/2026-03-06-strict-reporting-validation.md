# Strict Reporting Validation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enforce honest multi-size target validation and align the summary/report outputs with the strict scoring contract.

**Architecture:** Keep the current CLI and scoring structure, but add validation at argument parsing time for explicit multi-size targets, centralize wall-time summary derivation around the per-size timing model, and make the markdown report expose strict `N/A` causes from the rubric result instead of generic advice.

**Tech Stack:** Python 3.10+, pytest, jsonschema, argparse, markdown report generation

---

### Task 1: Add red tests for strict target validation

**Files:**
- Modify: `tests/test_perf_benchmark_pipeline.py`
- Modify: `scripts/perf_benchmark_pipeline.py`

**Step 1: Write the failing test**

Add a test that calls `parse_args()` with:

```python
["--root", str(tmp_path), "--out-dir", str(tmp_path / "out"), "--target", "python bench.py", "--sizes", "10,100"]
```

and asserts `SystemExit` because `{SIZE}` is missing.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_perf_benchmark_pipeline.py::test_parse_args_requires_size_placeholder_for_multi_size_target -q`

Expected: FAIL because the current parser accepts the invalid combination.

**Step 3: Write minimal implementation**

Add argument validation in `parse_args()`:
- If `args.target` is set
- And `len(args.sizes) >= 2`
- And `"{SIZE}" not in args.target`
- Then call `p.error(...)`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_perf_benchmark_pipeline.py::test_parse_args_requires_size_placeholder_for_multi_size_target -q`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_perf_benchmark_pipeline.py scripts/perf_benchmark_pipeline.py
git commit -m "fix: validate multi-size explicit targets"
```

### Task 2: Add red tests for wall-time summary consistency

**Files:**
- Modify: `tests/test_perf_benchmark_pipeline.py`
- Modify: `scripts/perf_benchmark_pipeline.py`

**Step 1: Write the failing test**

Add a test that writes a JSON summary for:

```python
tier1 = {
    "time_usage": [
        {"wall_seconds": 0.01, "input_size": 10},
        {"wall_seconds": 0.0101, "input_size": 10},
        {"wall_seconds": 1.0, "input_size": 1000},
        {"wall_seconds": 1.01, "input_size": 1000},
    ],
    "time_usage_by_size": {
        10: [{"wall_seconds": 0.01}, {"wall_seconds": 0.0101}],
        1000: [{"wall_seconds": 1.0}, {"wall_seconds": 1.01}],
    },
}
```

and asserts the JSON summary records the same `wall_time_cv` and per-size
breakdown as `score_wall_time_stability()`, not the pooled 113% CV.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_perf_benchmark_pipeline.py::test_write_json_summary_uses_per_size_wall_time_metrics -q`

Expected: FAIL because the current summary still pools `time_usage`.

**Step 3: Write minimal implementation**

Adjust `write_json_summary()` to:
- Prefer `time_usage_by_size` when present
- Store `wall_time_cv` using the same worst-per-size aggregation as the scorer
- Include `wall_time_cv_by_size`
- Only fall back to pooled `time_usage` when no grouped timings exist

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_perf_benchmark_pipeline.py::test_write_json_summary_uses_per_size_wall_time_metrics -q`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_perf_benchmark_pipeline.py scripts/perf_benchmark_pipeline.py
git commit -m "fix: align summary wall-time metrics with scorer"
```

### Task 3: Add red tests for strict `N/A` algorithmic reporting

**Files:**
- Modify: `tests/test_perf_benchmark_pipeline.py`
- Modify: `scripts/perf_benchmark_pipeline.py`

**Step 1: Write the failing test**

Add a test that writes a markdown report with:

```python
{
    "score": -1,
    "tier": "N/A",
    "sub_checks": {"complexity_exponent": {"k": 1.0, "tier": "PASS"}},
    "missing_sub_checks": [
        "call_amplification",
        "data_reuse",
        "write_amplification",
        "allocation_churn",
        "multiplicative_paths",
    ],
    "note": "Incomplete evidence for strict scaling rubric",
}
```

and asserts the report mentions the missing sub-checks and does not print the
generic “Run benchmarks at >= 2 input sizes” message when sizes are already
present.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_perf_benchmark_pipeline.py::test_write_markdown_report_explains_missing_algorithmic_subchecks -q`

Expected: FAIL because the current report hides `missing_sub_checks`.

**Step 3: Write minimal implementation**

Update `write_markdown_report()` so Dimension 0 `N/A`:
- Prints `note` if present
- Prints a bullet list of `missing_sub_checks`
- Only suggests adding more sizes when the missing set includes
  `complexity_exponent`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_perf_benchmark_pipeline.py::test_write_markdown_report_explains_missing_algorithmic_subchecks -q`

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_perf_benchmark_pipeline.py scripts/perf_benchmark_pipeline.py
git commit -m "fix: report strict algorithmic evidence gaps"
```

### Task 4: Align documentation with the enforced contract

**Files:**
- Modify: `README.md`
- Modify: `SKILL.md`
- Test: `tests/test_perf_benchmark_pipeline.py`

**Step 1: Write the failing test**

Add documentation assertions that:
- README explains multi-size explicit targets must use `{SIZE}`
- SKILL explains the same contract

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_perf_benchmark_pipeline.py::test_docs_require_size_placeholder_for_multi_size_explicit_target -q`

Expected: FAIL until docs are updated.

**Step 3: Write minimal implementation**

Update README and SKILL examples/CLI notes to say:
- Multi-size explicit targets require `{SIZE}`
- Fixed-size explicit targets should omit `--sizes`
- Strict `N/A` algorithmic reports list missing evidence

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_perf_benchmark_pipeline.py::test_docs_require_size_placeholder_for_multi_size_explicit_target -q`

Expected: PASS

**Step 5: Commit**

```bash
git add README.md SKILL.md tests/test_perf_benchmark_pipeline.py
git commit -m "docs: clarify strict multi-size target contract"
```

### Task 5: Full verification and publish

**Files:**
- Modify: `/home/jakub/.agents/skills/perf-benchmark` via sync after repo verification

**Step 1: Run focused suite**

Run:

```bash
pytest -q tests/test_perf_benchmark_pipeline.py
```

Expected: all focused tests pass.

**Step 2: Run full verification**

Run:

```bash
pytest -q
python3 -m py_compile scripts/perf_benchmark_pipeline.py
python3 scripts/perf_benchmark_pipeline.py --help
```

Expected: all pass with exit code 0.

**Step 3: Sync installed skill**

Run:

```bash
rsync -a --delete --exclude '.git' --exclude '.pytest_cache' --exclude '__pycache__' /home/jakub/projects/perf-benchmark-skill/ /home/jakub/.agents/skills/perf-benchmark/
```

Then verify:

```bash
diff -qr --exclude .git --exclude .pytest_cache --exclude __pycache__ /home/jakub/projects/perf-benchmark-skill /home/jakub/.agents/skills/perf-benchmark
npx skills ls -g -a github-copilot
npx skills ls -g -a claude-code
npx skills ls -g -a codex
```

**Step 4: Publish to GitHub**

Run:

```bash
git push -u origin fix/review-round-5
git checkout main
git merge --ff-only fix/review-round-5
git push origin main
```

**Step 5: Final status**

Report:
- local repo path
- branch and commit
- verification commands actually run
- whether the installed skill is in sync
