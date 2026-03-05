# Strict Rubric Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the reviewed rubric, scoring, and schema defects in `perf-benchmark-skill` without widening the public CLI surface.

**Architecture:** Keep the existing pipeline shape, but tighten Dimension 0 evidence handling, split wall-time stability by input size for repo-agnostic timing runs, and make the schema match the emitted `N/A` structure. The implementation should match the published rubric instead of relying on looser heuristics.

**Tech Stack:** Python 3, pytest, argparse, JSON Schema, Markdown docs

---

### Task 1: Lock down the reviewed scoring defects

**Files:**
- Modify: `tests/test_perf_benchmark_pipeline.py`
- Test: `tests/test_perf_benchmark_pipeline.py`

**Step 1: Write the failing test**

Add tests that prove:
- Dimension 0 does not return `PASS` with incomplete sub-check coverage
- call amplification follows the documented thresholds
- wall-time stability for explicit target/binary runs is computed per input size, not across pooled sizes
- the schema accepts `N/A` outputs

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_perf_benchmark_pipeline.py -q`
Expected: FAIL on the new rubric-alignment assertions

**Step 3: Write minimal implementation**

Patch only the scoring and schema logic needed to satisfy the tests.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_perf_benchmark_pipeline.py -q`
Expected: PASS

### Task 2: Align rubric and schema references

**Files:**
- Modify: `references/rubric.md`
- Modify: `references/finding-schema.json`

**Step 1: Write the failing test**

Represent any changed contract with assertions in the Python test file.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_perf_benchmark_pipeline.py -q`
Expected: FAIL if docs/schema still disagree with implementation

**Step 3: Write minimal implementation**

Update the reference documents so they match the corrected runtime behavior.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_perf_benchmark_pipeline.py -q`
Expected: PASS

### Task 3: Verify and publish

**Files:**
- Modify: `scripts/perf_benchmark_pipeline.py`
- Modify: `tests/test_perf_benchmark_pipeline.py`
- Modify: `references/rubric.md`
- Modify: `references/finding-schema.json`

**Step 1: Run focused verification**

Run:
- `pytest tests/test_perf_benchmark_pipeline.py -q`
- `pytest -q`
- `python3 -m py_compile scripts/perf_benchmark_pipeline.py`
- `python3 scripts/perf_benchmark_pipeline.py --help`

Expected: all succeed

**Step 2: Sync installed skill**

Copy the verified repo contents into `~/.agents/skills/perf-benchmark` and confirm the installed files match the repo copy.

**Step 3: Commit and push**

Run:
- `git add ...`
- `git commit -m "fix: align scoring with strict rubric"`
- `git push origin fix/review-round-4`
- fast-forward `main` and push after verification on `main`
