# QA Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Improve maintainability and test quality of the standalone perf-benchmark skill without changing its benchmark behavior or weakening internal regression safety.

**Architecture:** Keep `scripts/perf_benchmark_pipeline.py` as the entrypoint shim, but move its logic into a few small internal modules under `scripts/perf_benchmark/`. Add end-to-end contract tests on top of the existing white-box suite, and add minimal Python quality tooling so lint/format checks are reproducible.

**Tech Stack:** Python 3.10+, pytest, pathlib, argparse, Ruff, pre-commit

---

### Task 1: Add end-to-end artifact contract tests

**Files:**
- Modify: `tests/test_perf_benchmark_pipeline.py`
- Modify: `scripts/perf_benchmark_pipeline.py`

**Step 1: Write the failing tests**

Add focused `main()` tests that:
- run the pipeline with a simple explicit target in `fast` mode
- assert `benchmark_report.md` and `benchmark_summary.json` are written
- assert key contract strings/fields exist in those outputs

Keep monkeypatching limited to prerequisites or external tools; assert on the
actual file outputs rather than helper return values.

**Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_perf_benchmark_pipeline.py::test_main_writes_report_and_summary_artifacts -q
pytest tests/test_perf_benchmark_pipeline.py::test_main_report_contains_scorecard_sections -q
```

Expected: FAIL before the new support code or assertions are in place.

**Step 3: Write minimal implementation**

Adjust only what is needed so the end-to-end tests can reliably inspect the
produced artifacts without weakening existing behavior.

**Step 4: Run tests to verify they pass**

Run the same commands and expect PASS.

**Step 5: Commit**

```bash
git add tests/test_perf_benchmark_pipeline.py scripts/perf_benchmark_pipeline.py
git commit -m "test: add end-to-end artifact contract coverage"
```

### Task 2: Small module split with stable CLI entrypoint

**Files:**
- Create: `scripts/perf_benchmark/__init__.py`
- Create: `scripts/perf_benchmark/stages.py`
- Create: `scripts/perf_benchmark/scoring.py`
- Create: `scripts/perf_benchmark/reporting.py`
- Create: `scripts/perf_benchmark/cli.py`
- Modify: `scripts/perf_benchmark_pipeline.py`
- Test: `tests/test_perf_benchmark_pipeline.py`

**Step 1: Write the failing regression test**

Add or adapt a test that imports the top-level script module and asserts the
public functions used by the current test suite still exist on that module
after the split.

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_perf_benchmark_pipeline.py::test_pipeline_module_re_exports_existing_tested_api -q
```

Expected: FAIL once the test names the intended preserved surface.

**Step 3: Write minimal implementation**

Split the monolith into small modules:
- `stages.py`: stage runners, parsers, discovery helpers
- `scoring.py`: rubric/scoring helpers
- `reporting.py`: markdown/json report generation
- `cli.py`: argument parsing and `main()`

Keep `scripts/perf_benchmark_pipeline.py` as a thin compatibility shim that
re-exports the tested functions and calls `main()`.

**Step 4: Run focused tests**

Run:

```bash
pytest tests/test_perf_benchmark_pipeline.py -q
```

Expected: PASS

**Step 5: Commit**

```bash
git add scripts/perf_benchmark scripts/perf_benchmark_pipeline.py tests/test_perf_benchmark_pipeline.py
git commit -m "refactor: split perf benchmark pipeline into modules"
```

### Task 3: Tighten internal-safety tests around scoring semantics

**Files:**
- Modify: `tests/test_perf_benchmark_pipeline.py`
- Modify: `scripts/perf_benchmark/scoring.py`
- Modify: `README.md`
- Modify: `SKILL.md`

**Step 1: Write the failing tests**

Add tests for:
- per-file `data_reuse` semantics
- per-file `write_amplification` semantics
- strict documentation that Dimension 0 needs `deep` for full scoring

**Step 2: Run tests to verify they fail**

Run:

```bash
pytest tests/test_perf_benchmark_pipeline.py::test_score_algorithmic_scaling_uses_hotspot_level_data_reuse -q
pytest tests/test_perf_benchmark_pipeline.py::test_score_algorithmic_scaling_uses_hotspot_level_write_amplification -q
pytest tests/test_perf_benchmark_pipeline.py::test_docs_state_dimension_zero_requires_deep_for_full_score -q
```

Expected: FAIL with current semantics/docs.

**Step 3: Write minimal implementation**

Change the scoring code to use per-file cachegrind metrics for the Dimension 0
sub-checks that the rubric already defines as hotspot-level, and update docs to
say full Algorithmic Scaling scoring requires `deep`.

**Step 4: Run tests to verify they pass**

Run the same commands and expect PASS.

**Step 5: Commit**

```bash
git add tests/test_perf_benchmark_pipeline.py scripts/perf_benchmark/scoring.py README.md SKILL.md
git commit -m "fix: align hotspot scoring and strict deep-tier docs"
```

### Task 4: Add minimal Python quality tooling

**Files:**
- Create: `pyproject.toml`
- Create: `.pre-commit-config.yaml`
- Modify: `README.md`

**Step 1: Write the failing expectation**

Add a small test that asserts the repo contains a `pyproject.toml` with a Ruff
section, or check this manually if a test would be too indirect.

**Step 2: Implement minimal tooling**

Add:
- Ruff config
- basic formatting/lint target version
- pre-commit hooks for Ruff

Keep this minimal; no type-checker required if it is not installable in the
current environment.

**Step 3: Run checks**

Run:

```bash
ruff check .
ruff format --check .
```

If Ruff is unavailable in the environment, document that limitation and still
commit the config.

**Step 4: Commit**

```bash
git add pyproject.toml .pre-commit-config.yaml README.md
git commit -m "chore: add minimal python quality tooling"
```

### Task 5: Document and review parallelization opportunities

**Files:**
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `scripts/perf_benchmark/cli.py`

**Step 1: Write the failing docs expectation**

Add a test or doc assertion that:
- Tier 1 stays non-parallelized because it is timing-sensitive
- artifact parsing / rubric dimensions are the preferred subagent split

**Step 2: Run test to verify it fails**

Run the focused doc test and confirm failure.

**Step 3: Implement minimal documentation/runtime comments**

Clarify:
- why Tier 1 remains isolated
- what is safe to parallelize in code
- what is safe to split across subagents

**Step 4: Run doc tests**

Run the focused doc test and expect PASS.

**Step 5: Commit**

```bash
git add SKILL.md README.md scripts/perf_benchmark/cli.py tests/test_perf_benchmark_pipeline.py
git commit -m "docs: clarify safe parallelization boundaries"
```

### Task 6: Full verification and publish

**Files:**
- Modify: `/home/jakub/.agents/skills/perf-benchmark` via sync after verification

**Step 1: Run focused verification**

Run:

```bash
pytest -q tests/test_perf_benchmark_pipeline.py
```

**Step 2: Run full verification**

Run:

```bash
pytest -q
python3 -m py_compile scripts/perf_benchmark_pipeline.py
python3 scripts/perf_benchmark_pipeline.py --help
```

If Ruff is available:

```bash
ruff check .
ruff format --check .
```

**Step 3: Sync installed skill**

Run:

```bash
rsync -a --delete --exclude '.git' --exclude '.pytest_cache' --exclude '__pycache__' /home/jakub/projects/perf-benchmark-skill/ /home/jakub/.agents/skills/perf-benchmark/
diff -qr --exclude .git --exclude .pytest_cache --exclude __pycache__ /home/jakub/projects/perf-benchmark-skill /home/jakub/.agents/skills/perf-benchmark
```

Then verify:

```bash
npx skills ls -g -a github-copilot
npx skills ls -g -a claude-code
npx skills ls -g -a codex
```

**Step 4: Publish to GitHub**

Run:

```bash
git push -u origin fix/qa-hardening
git checkout main
git merge --ff-only fix/qa-hardening
git push origin main
```

**Step 5: Final status**

Report:
- repo path
- commit
- commands run
- tooling availability limits
- installed skill sync state
