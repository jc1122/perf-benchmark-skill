# Strict Summary Rendering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Align summary/report output with the scoring contract and fully reject synthetic size labels for explicit targets.

**Architecture:** Keep the current pipeline structure, but tighten argument validation in `parse_args()`, make summary wall-time derivation follow the same data precedence as the scorer, and centralize algorithmic sub-check value formatting so zero-valued evidence is rendered correctly.

**Tech Stack:** Python 3.10+, pytest, argparse, markdown report generation

---

### Task 1: Add red tests for strict explicit-target size validation

**Files:**
- Modify: `tests/test_perf_benchmark_pipeline.py`
- Modify: `scripts/perf_benchmark_pipeline.py`

**Step 1: Write the failing test**

Add a test that calls:

```python
pipeline.parse_args(
    [
        "--root", str(tmp_path),
        "--out-dir", str(tmp_path / "out"),
        "--target", "python bench.py",
        "--sizes", "10",
    ]
)
```

and asserts `SystemExit`.

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_perf_benchmark_pipeline.py::test_parse_args_requires_size_placeholder_for_any_explicit_target_sizes -q
```

Expected: FAIL because the parser currently allows the invalid single-size case.

**Step 3: Write minimal implementation**

Change `parse_args()` so any explicit `--target` combined with non-empty
`--sizes` requires `{SIZE}`.

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add tests/test_perf_benchmark_pipeline.py scripts/perf_benchmark_pipeline.py
git commit -m "fix: reject synthetic explicit target sizes"
```

### Task 2: Add red tests for pytest-summary consistency

**Files:**
- Modify: `tests/test_perf_benchmark_pipeline.py`
- Modify: `scripts/perf_benchmark_pipeline.py`

**Step 1: Write the failing test**

Add a test with:

```python
tier1 = {
    "pytest_benchmark": {
        "benchmarks": [
            {"stats": {"mean": 1.0, "stddev": 0.01}},
            {"stats": {"mean": 1.0, "stddev": 0.02}},
        ]
    },
    "time_usage": [
        {"wall_seconds": 0.01},
        {"wall_seconds": 0.011},
        {"wall_seconds": 1.0},
        {"wall_seconds": 1.01},
    ],
}
```

Assert that `write_json_summary()` records the same `wall_time_cv` as
`score_wall_time_stability(tier1)` instead of the pooled `/usr/bin/time` CV.

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_perf_benchmark_pipeline.py::test_write_json_summary_prefers_pytest_wall_time_metrics -q
```

Expected: FAIL because the current summary ignores pytest-benchmark data.

**Step 3: Write minimal implementation**

Update `_summarize_wall_time_metrics()` to:
- Prefer pytest-benchmark data first
- Return a summary `wall_time_cv` aligned with the scorer
- Optionally expose a summary of the contributing pytest benchmark CVs

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add tests/test_perf_benchmark_pipeline.py scripts/perf_benchmark_pipeline.py
git commit -m "fix: align summary pytest metrics with scorer"
```

### Task 3: Add red tests for zero-valued report evidence

**Files:**
- Modify: `tests/test_perf_benchmark_pipeline.py`
- Modify: `scripts/perf_benchmark_pipeline.py`

**Step 1: Write the failing test**

Add a test that renders a markdown report for:

```python
{
    "score": -1,
    "tier": "N/A",
    "sub_checks": {
        "multiplicative_paths": {"path_count": 0, "tier": "PASS"}
    },
    "missing_sub_checks": ["complexity_exponent"],
    "note": "Incomplete evidence for strict scaling rubric",
}
```

and assert the report contains `| multiplicative_paths | 0 | PASS |`.

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_perf_benchmark_pipeline.py::test_write_markdown_report_preserves_zero_algorithmic_values -q
```

Expected: FAIL because the current `or` chain renders zero as blank.

**Step 3: Write minimal implementation**

Introduce a helper that selects the first present metric key without treating
zero as false, and reuse it in both algorithmic table render paths.

**Step 4: Run test to verify it passes**

Run the same command and expect PASS.

**Step 5: Commit**

```bash
git add tests/test_perf_benchmark_pipeline.py scripts/perf_benchmark_pipeline.py
git commit -m "fix: preserve zero-valued report evidence"
```

### Task 4: Full verification and publish

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

Expected: all pass.

**Step 3: Sync installed skill**

Run:

```bash
rsync -a --delete --exclude '.git' --exclude '.pytest_cache' --exclude '__pycache__' /home/jakub/projects/perf-benchmark-skill/ /home/jakub/.agents/skills/perf-benchmark/
diff -qr --exclude .git --exclude .pytest_cache --exclude __pycache__ /home/jakub/projects/perf-benchmark-skill /home/jakub/.agents/skills/perf-benchmark
```

Then verify visibility:

```bash
npx skills ls -g -a github-copilot
npx skills ls -g -a claude-code
npx skills ls -g -a codex
```

**Step 4: Publish to GitHub**

Run:

```bash
git push -u origin fix/review-round-6
git checkout main
git merge --ff-only fix/review-round-6
git push origin main
```

**Step 5: Final status**

Report:
- repo path
- branch and commit
- verification commands run
- installed skill sync status
