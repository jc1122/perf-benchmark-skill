# Perf Benchmark Skill Review Findings Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the reviewed defects in `perf-benchmark-skill`, add regression tests, and align published documentation with implemented behavior.

**Architecture:** Preserve the existing pipeline structure while separating Valgrind-dependent and independent stages, layering baseline comparison on top of existing rubric output, and broadening artifact discovery without changing the CLI contract.

**Tech Stack:** Python 3, pytest, argparse, subprocess, markdown documentation

---

### Task 1: Add failing regression tests

**Files:**
- Modify: `scripts/perf_benchmark_pipeline.py`
- Create: `tests/test_perf_benchmark_pipeline.py`

**Step 1: Write the failing test**

Add tests for:
- Stage 3 running `perf_stat` and `objdump` without Valgrind
- `stage_perf_stat()` passing the augmented environment
- Baseline comparison reporting regressions outside memory
- ASM discovery finding `.so` artifacts outside `--source-prefix` paths

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_perf_benchmark_pipeline.py -q`
Expected: failures matching the reviewed defects

**Step 3: Write minimal implementation**

Patch the pipeline code only enough to satisfy the new tests.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_perf_benchmark_pipeline.py -q`
Expected: all tests pass

### Task 2: Align skill documentation with actual behavior

**Files:**
- Modify: `SKILL.md`
- Modify: `README.md`

**Step 1: Write the failing test**

Represent docs correctness with assertions in the Python test module:
- no `pipeline.py` examples
- no `perf-benchmark-skill` hardcoded install path in invocation examples
- baseline language matches implemented behavior

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_perf_benchmark_pipeline.py -q`
Expected: doc assertions fail before edits

**Step 3: Write minimal implementation**

Update docs examples and wording to match the actual package layout and
implemented regression handling.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_perf_benchmark_pipeline.py -q`
Expected: docs assertions pass

### Task 3: Verify, review, and publish

**Files:**
- Modify: `scripts/perf_benchmark_pipeline.py`
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `tests/test_perf_benchmark_pipeline.py`

**Step 1: Run focused verification**

Run:
- `pytest tests/test_perf_benchmark_pipeline.py -q`
- `python3 -m py_compile scripts/perf_benchmark_pipeline.py`
- `python3 scripts/perf_benchmark_pipeline.py --help`

Expected: all succeed

**Step 2: Review diff**

Run: `git --no-pager diff --stat && git --no-pager diff`
Expected: only standalone skill repo files changed

**Step 3: Commit**

Run:
- `git add SKILL.md README.md scripts/perf_benchmark_pipeline.py tests/test_perf_benchmark_pipeline.py docs/plans/2026-03-05-review-findings-design.md docs/plans/2026-03-05-review-findings.md`
- `git commit -m "fix: address perf benchmark skill review findings"`

**Step 4: Push**

Run: `git push -u origin fix/review-findings`
Expected: branch published to GitHub
