# Repo-Agnostic Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the perf-benchmark skill honestly repo-agnostic by requiring an explicit benchmark target unless pytest benchmark discovery succeeds, then sync the installed skill copy.

**Architecture:** Keep pytest autodiscovery as a convenience path for Python repos, but remove the misleading fallback that profiles `python -c pass`. The generic interface becomes explicit `--target` or `--binary`, with docs and tests enforcing that contract.

**Tech Stack:** Python 3.10+, pytest, argparse, Markdown docs

---

### Task 1: Lock down the missing-target behavior

**Files:**
- Modify: `tests/test_perf_benchmark_pipeline.py`
- Test: `tests/test_perf_benchmark_pipeline.py`

**Step 1: Write the failing test**

Add a test that runs `main()` with no `--target`, no `--binary`, and no discovered pytest benchmarks, and assert it returns `1` without entering Tier 1.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_perf_benchmark_pipeline.py -q`
Expected: FAIL because `main()` currently continues with the `python -c pass` fallback.

**Step 3: Write minimal implementation**

Update the pipeline entrypoint to stop early with a clear error when there is nothing real to benchmark.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_perf_benchmark_pipeline.py -q`
Expected: PASS for the new test.

### Task 2: Lock down the repo-agnostic documentation contract

**Files:**
- Modify: `tests/test_perf_benchmark_pipeline.py`
- Modify: `SKILL.md`
- Modify: `README.md`

**Step 1: Write the failing test**

Add a doc test that requires the skill docs to describe pytest autodiscovery as optional convenience and explicit `--target` / `--binary` as the generic repo-agnostic path.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_perf_benchmark_pipeline.py -q`
Expected: FAIL because the current wording overstates autodiscovery.

**Step 3: Write minimal implementation**

Revise `SKILL.md` and `README.md` so they describe the actual cross-repo contract clearly and consistently.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_perf_benchmark_pipeline.py -q`
Expected: PASS.

### Task 3: Verify, sync install, and publish

**Files:**
- Modify: `scripts/perf_benchmark_pipeline.py`
- Modify: `SKILL.md`
- Modify: `README.md`

**Step 1: Run full verification**

Run:
- `pytest -q`
- `python3 -m py_compile scripts/perf_benchmark_pipeline.py`
- `python3 scripts/perf_benchmark_pipeline.py --help`

Expected: all succeed.

**Step 2: Sync the installed skill**

Copy the updated repo contents into the installed skill directory at `~/.agents/skills/perf-benchmark` and verify the installed files match the repo.

**Step 3: Commit and push**

Run:
- `git add ...`
- `git commit -m "fix: harden repo-agnostic skill behavior"`
- `git push origin fix/repo-agnostic-skill`
- fast-forward `main` and push if verification remains green
