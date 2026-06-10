# SP6: perf-benchmark v0.2.0 — Complete Performance Bench Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.
>
> **For the SP6 Opus orchestrator:** this plan is designed for PARALLEL workers — see the wave map. Workers implement tasks VERBATIM via TDD in isolated worktrees; you own all merges, re-run every gate yourself, and read real output. A worker's "green" is NOT evidence.

**Goal:** Upgrade perf-benchmark from a diagnostic-only profiler to the family's performance member: fix the environment-dependent test, add CI, a documented statistical-rigor policy with a noise gate, an environment fingerprint, a shared-schema PERF findings bridge, a baseline trend ledger, latency percentiles, and a perf-remediation playbook — then prove it in Phase 2 by benchmarking and ratchet-optimizing one of its own hot paths.

**Architecture:** The skill is a single pipeline script (`scripts/perf_benchmark_pipeline.py`, argparse at lines 645–689) over four helper modules (`scripts/perf_benchmark/{scoring,reporting,stage_helpers,support}.py`). All additions are new modules or additive args — no output contract changes; `benchmark_summary.json` only gains keys. Integration with the orchestrator is docs-only in a second repo.

**Tech Stack:** Python 3.10+ stdlib only (matches existing code), pytest (baseline: 61 tests, 1 env-dependent failure), ruff (pyproject: line-length 100, select E,F,I,UP).

**Repos:**
- A = `/home/jakub/projects/perf-benchmark-skill` (main work; no docs/ dir at baseline — this plan creates it)
- B = `/home/jakub/projects/repo-audit-refactor-optimize` (docs-only: PERF integration into playbook + prioritization)

---

## Design Decisions (locked)

1. **The failing test is a TEST bug, not a code bug.** `stage_massif` already passes `timeout=args.valgrind_timeout` to the `ms_print` run (pipeline.py:348–353). `test_stage_massif_post_processing_uses_timeout` fails only because it never monkeypatches `shutil.which`, so on machines without valgrind the ms_print branch is skipped and `captured == []`. Fix the test, not the code.
2. **PERF findings bridge, no repo-audit-skills change.** perf-benchmark emits findings in the shared code-health finding *shape* (the `Finding.to_dict()` layout from repo-audit-skills `shared/health_common.py`: id/leaf/signal/severity/path/location/metric/evidence/confidence/suggested_action) with `signal: "PERF"`, via a new `--findings-out` flag. Adding `"PERF"` to the canonical `SIGNALS` frozenset is DEFERRED to the next repo-audit-skills release (it triggers the 6-copy re-vendor + ratchet machinery; note it in the report). Consumers (the orchestrator's synthesis) merge dicts and do not validate against `SIGNALS`.
3. **Statistical rigor = noise gate + policy, not pipeline-level re-runs.** Repeats already exist (`--time-repeats` 5, `--perf-repeats` 5, pytest-benchmark rounds). v0.2.0 adds: a documented policy in rubric.md (median-of-repeats, CV reporting, SPEC/JMH-style disclosure) and a `--max-cv` gate (default 5.0): any timing-derived dimension whose CV exceeds the gate scores `N/A (noise)` instead of a number. Refusing to score noise is the rigor.
4. **Latency percentiles, not a load harness.** Tier-1 wall-time repeats gain p50/p95/p99 in the summary (ISO 25010 time-behaviour measures). The full ISTQB service-level lane (load/stress/soak/spike with closed-loop drivers) is explicitly DEFERRED to SP7 — recorded as a scoped gap in the playbook, not faked.
5. **Phase 2 runs at `--tier fast` only**: this machine has NO valgrind/ms_print (verified 2026-06-10). Tier-1 self-benchmark is honest and sufficient for the ratchet demo; the report must record the tooling absence.
6. Version bump SKILL.md 0.1.0 → 0.2.0. Commit locally per task. **Do NOT push, tag, or release** — human reviews.

## File Structure (repo A unless noted)

- Modify: `tests/test_pipeline_stages.py` (T1 fix), `tests/test_pipeline_scoring_reporting.py` (T4/T5/T7 tests)
- Create: `.github/workflows/check.yml` (T2)
- Create: `references/perf-remediation-playbook.md` (T3)
- Modify: `references/rubric.md` (T4 policy + ISO mapping), `scripts/perf_benchmark/scoring.py` (T4 gate)
- Modify: `scripts/perf_benchmark/reporting.py` (T5 fingerprint + percentiles)
- Create: `scripts/perf_benchmark/findings.py` + `tests/test_findings_bridge.py` (T6)
- Create: `scripts/perf_benchmark/ledger.py` + `tests/test_ledger.py` (T7)
- Modify: `scripts/perf_benchmark_pipeline.py` argparse + wiring (T6, T7 — same file, SERIALIZED)
- Modify (repo B): `references/remediation-playbook.md`, `references/prioritization.md` (T8)
- Modify: `SKILL.md`, `README.md` (T9)
- Create: `benchmarks/bench_parse_massif.py`, `docs/dogfood/2026-06-10-sp6-self-bench.md` (Phase 2)

## Worker wave map (PARALLEL agents; cap 4; one packet = one worker = own worktree)

- **Wave 1 (4 workers):** W-A=T1 (test fix) ∥ W-B=T2 (CI) ∥ W-C=T3 (playbook) ∥ W-D=T4 (stats policy + noise gate). Disjoint files (W-A edits `test_pipeline_stages.py`; W-D edits `test_pipeline_scoring_reporting.py` + `scoring.py` + `rubric.md`).
- **Wave 2 (3 workers):** W-E=T5 (fingerprint + percentiles; `reporting.py`) ∥ W-F=T6 (findings bridge; new module + pipeline argparse) ∥ W-G=T8 (repo B docs — different repo, fully parallel).
- **Wave 2b (1 worker):** W-H=T7 (ledger) — AFTER T6 merged (both touch `perf_benchmark_pipeline.py` argparse; serialize to avoid merge conflicts).
- **Gate (orchestrator):** full suite + CI-equivalent locally; then T9 (version/README, one worker or orchestrator).
- **Phase 2 (orchestrator-driven):** self-benchmark + ratchet optimization, one worker per batch, serialized.

Merge discipline: orchestrator owns all merges; after each merge run `python3 -m pytest tests/ -q` from repo A root and read it. Never merge two workers touching the same file without rebasing the second.

---

### Task 1: Fix the environment-dependent massif test (W-A)

**Files:** Modify: `tests/test_pipeline_stages.py` (test at ~line 316)

- [ ] **Step 1:** Reproduce: `python3 -m pytest tests/test_pipeline_stages.py::test_stage_massif_post_processing_uses_timeout -q` → FAILS `assert [] == [30]` on machines without valgrind (`shutil.which("ms_print")` → None).
- [ ] **Step 2:** In that test, after the `fake_run` monkeypatch, add:

```python
    monkeypatch.setattr(pipeline.shutil, "which", lambda name: f"/usr/bin/{name}")
```

(Verify the adjacent passing test `test_stage_massif_skips_ms_print_when_tool_is_missing` still covers the None branch — do not touch it.)
- [ ] **Step 3:** Run: `python3 -m pytest tests/ -q` → Expected: `61 passed`.
- [ ] **Step 4:** Commit: `git commit -m "test: massif ms_print timeout test no longer depends on installed valgrind (SP6 T1)"`

### Task 2: CI workflow (W-B)

**Files:** Create: `.github/workflows/check.yml`

- [ ] **Step 1:** Create the workflow: on push/PR to main; ubuntu-latest; `actions/checkout@v4`; `actions/setup-python@v5` (python 3.12); `pip install pytest ruff`; steps: `ruff check scripts/ tests/`, `ruff format --check scripts/ tests/` (if format fails at baseline, run `ruff format` in this task and commit the diff as a separate first commit), `python3 -m pytest tests/ -q`. Do NOT install valgrind in CI — T1 makes the suite valgrind-independent; assert that by running the suite in a bare venv locally.
- [ ] **Step 2:** Validate statically (actionlint if available, else careful read). CI cannot run before a human pushes — record that in the run report.
- [ ] **Step 3:** Commit: `git commit -m "ci: pytest + ruff gates on push (SP6 T2)"`

### Task 3: Perf remediation playbook (W-C)

**Files:** Create: `references/perf-remediation-playbook.md`

- [ ] **Step 1:** Create with exactly this content:

```markdown
# Performance Remediation Playbook

Execution discipline for acting on perf-benchmark findings. Diagnosis is the pipeline's job;
this playbook is the measure -> change -> re-measure ratchet for fixing what it finds.

## Standing Rules

1. **Algorithmic STOP gate first.** If Algorithmic Scaling is FAIL, no cache/branch/ASM work
   is permitted until the complexity class is fixed. Constants do not beat asymptotics.
2. **One dimension per batch.** Never mix an algorithmic change with a data-layout change in
   one commit; attribution dies.
3. **Measure before, measure after, same environment.** Both runs same tier, same sizes, same
   machine state (governor, SMT, load). The summary's environment fingerprint must match
   between the before/after runs; a fingerprint mismatch voids the comparison.
4. **Acceptance ratchet:** a batch is accepted only if (a) median improves >= 5% on the target
   dimension's metric, (b) wall-time CV stays <= --max-cv in both runs, (c) no other scored
   dimension regresses by >= 1 tier, and (d) the test suite is green. Otherwise discard.
5. **Coverage gate (shared with code-health):** before editing an uncovered file, write
   behavior tests for its contract. Perf wins on untested code are not accepted.
6. **Honest no-win:** if every candidate requires behavior changes, architecture work, or
   yields < 5%, record "evaluated, no feasible low-risk win" with the evidence. That is a
   valid, terminal outcome (cf. SP4 DoD).

## Dimension Procedures

| Dimension | First moves | Verify with |
|---|---|---|
| Algorithmic Scaling | Lower the complexity class: incremental maintenance over recompute; process deltas not history; index/partition/cache lookups; bound per-update work to changed inputs | multi-size re-run; growth curve matches expected class |
| L1 / LLC Cache | Contiguous layouts (arrays-of-scalars over objects), loop blocking/fusion, hot/cold field splitting, smaller working sets | cachegrind miss rates |
| Memory Profile | Kill allocation churn in loops (reuse buffers), generators over materialized lists, slots/dataclass(frozen) for hot objects, cap retained history | massif/tracemalloc peaks |
| CPU Efficiency | Hoist invariants, remove redundant passes/copies, batch syscalls/IO, vectorize (numpy) or JIT (numba) only after the above | callgrind inclusive cost, perf stat IPC |
| Branch Prediction | Sort/partition data to make branches predictable, replace data-dependent branches with arithmetic/lookup, move rare cases out of hot loops | branch-miss rate |
| Wall-Time Stability | Pin governor to performance, isolate from background load, increase repeats; if CV stays > gate, fix the measurement before the code | CV in summary |
| Latency percentiles (p95/p99) | Hunt the tail: GC pauses, lazy init on first hit, lock contention, pathological inputs; fix the tail cause, never average it away | p50/p95/p99 spread in summary |

## Scope Notes (v0.2.0)

- Service-level test types (load, stress, soak, spike, concurrency, capacity — ISTQB CT-PT
  taxonomy; ISO/IEC 25010 'capacity') are OUT OF SCOPE for this skill version: there is no
  closed-loop load driver. Do not simulate them with repeats. Recorded gap; planned SP7.
- Non-Linux hosts and Rust/criterion ingestion: out of scope v0.2.0 (P2).
```

- [ ] **Step 2:** Commit: `git commit -m "docs: perf remediation playbook — measure/change/re-measure ratchet (SP6 T3)"`

### Task 4: Statistical-rigor policy + CV noise gate (W-D, TDD)

**Files:** Modify: `scripts/perf_benchmark/scoring.py`, `references/rubric.md`; Test: `tests/test_pipeline_scoring_reporting.py`

- [ ] **Step 1 (failing test):** Append to `tests/test_pipeline_scoring_reporting.py` a test that builds the minimal scoring input used by existing tests in that file (REUSE the file's existing fixture/helper pattern for constructing rubric inputs — read the top of the file first), with wall-time repeat values `[1.0, 1.0, 1.0, 3.0]` (CV ≈ 66%) and `max_cv=5.0`, and asserts: the Wall-Time Stability dimension's tier is the string `"N/A (noise)"` and its score does not count toward `rubric["total"]`; with values `[1.0, 1.01, 0.99, 1.0]` the dimension scores normally. Run it → FAIL.
- [ ] **Step 2 (implement):** In `scoring.py` (the module already exposes `_cv` at line 23): thread a `max_cv: float` parameter (default 5.0) into the scoring entry point that produces the wall-time stability dimension; when `_cv(values) > max_cv`, emit tier `"N/A (noise)"`, score excluded from total, and attach the measured CV in the dimension payload. Apply the same gate to any other dimension whose inputs are the timing repeats (grep scoring.py for the consumers of wall-time means). Wire a new pipeline arg in `scripts/perf_benchmark_pipeline.py` argparse block (after `--time-repeats`, line ~681): `p.add_argument("--max-cv", type=float, default=5.0, help="CV%% above which timing-based dimensions score N/A (noise)")` and pass it through to scoring.
- [ ] **Step 3 (policy doc):** Append to `references/rubric.md` a `## Measurement Policy (v0.2.0)` section stating: median-of-repeats is the scored statistic; CV is always reported; CV > `--max-cv` (default 5%) → dimension is N/A (noise), never scored — per SPEC CPU run-rule spirit (multiple runs, median) and JMH/pyperf methodology; environment fingerprint (T5) is part of every disclosure; map each dimension to its ISO/IEC 25010 performance-efficiency sub-characteristic (time behaviour: scaling/wall-time/CPU/branch/percentiles; resource utilization: cache/memory; capacity: not covered, see playbook scope note).
- [ ] **Step 4:** `python3 -m pytest tests/ -q` → all pass (61 + new). Commit: `git commit -m "feat(scoring): --max-cv noise gate + measurement policy, ISO 25010 mapping (SP6 T4)"`

### Task 5: Environment fingerprint + latency percentiles (W-E, TDD)

**Files:** Modify: `scripts/perf_benchmark/reporting.py` (summary assembly ends at line ~377); Test: `tests/test_pipeline_scoring_reporting.py`

- [ ] **Step 1 (failing tests):** Two tests: (a) the written `benchmark_summary.json` contains an `"environment"` object with keys `cpu_model, kernel, governor, smt, load_avg_1m, python_version, timestamp_utc`; (b) given wall-time repeat values `[1,2,3,...,10]` the summary contains `"wall_time_percentiles": {"p50": ..., "p95": ..., "p99": ...}` computed by `statistics.quantiles(values, n=100)` indices 49/94/98 (assert exact values for the fixed input).
- [ ] **Step 2 (implement):** New helper in `reporting.py`:

```python
def _environment_fingerprint() -> dict[str, Any]:
    cpu_model = ""
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    governor_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    smt_path = Path("/sys/devices/system/cpu/smt/active")
    return {
        "cpu_model": cpu_model,
        "kernel": platform.release(),
        "governor": governor_path.read_text().strip() if governor_path.exists() else "unknown",
        "smt": smt_path.read_text().strip() if smt_path.exists() else "unknown",
        "load_avg_1m": round(os.getloadavg()[0], 2),
        "python_version": platform.python_version(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
```

Add `summary["environment"] = _environment_fingerprint()` and the percentile block beside the existing `_summarize_wall_time_metrics` call (line ~357). NOTE: `timestamp_utc` is metadata — exclude it (and `load_avg_1m`) from any determinism comparison; keep them inside `environment` only.
- [ ] **Step 3:** Suite green; commit: `git commit -m "feat(report): environment fingerprint + p50/p95/p99 wall-time percentiles (SP6 T5)"`

### Task 6: Shared-schema PERF findings bridge (W-F, TDD)

**Files:** Create: `scripts/perf_benchmark/findings.py`, `tests/test_findings_bridge.py`; Modify: `scripts/perf_benchmark_pipeline.py` (argparse + one call after summary write)

- [ ] **Step 1 (failing test):** `tests/test_findings_bridge.py`: feed a rubric dict with one FAIL dimension (e.g. `("L1 cache efficiency", {"tier": "FAIL", "score": 0, "metric": "l1_miss_rate", "value": 9.3, "threshold": 5.0})` — mirror the real rubric dimension payload shape from existing scoring tests) and assert `findings.to_shared_findings(rubric, root="/repo")` returns a list of dicts each with EXACTLY the keys `id, leaf, signal, severity, path, location, metric, evidence, confidence, suggested_action`, where `signal == "PERF"`, `leaf == "perf-benchmark"`, `location == {"line_start": 0, "line_end": 0, "symbol": "<workload>"}`, `metric == {"name": "l1_miss_rate", "value": 9.3, "threshold": 5.0}`, severity `"high"` for FAIL / `"medium"` for WARN, and `id` is the first 16 hex chars of `sha1("perf-benchmark|<path>|<workload>|l1_miss_rate")`. PASS/N-A dimensions produce no finding. Sort by `(path, metric.name)`. Byte-identical across two calls.
- [ ] **Step 2 (implement):** `findings.py` (stdlib only) implementing exactly that mapping (`path` = the benchmark target identifier passed in, default `"<benchmark-suite>"`). Wire: `p.add_argument("--findings-out", type=Path, default=None, help="Write shared-schema PERF findings JSON here")` in the argparse block, and after the summary is written, if set: `Path(args.findings_out).write_text(json.dumps(findings_list, indent=2, sort_keys=True) + "\n")`.
- [ ] **Step 3:** Suite green; commit: `git commit -m "feat(findings): --findings-out shared-schema PERF findings bridge (SP6 T6)"`

### Task 7: Baseline trend ledger (W-H, AFTER T6 merged, TDD)

**Files:** Create: `scripts/perf_benchmark/ledger.py`, `tests/test_ledger.py`; Modify: `scripts/perf_benchmark_pipeline.py` (argparse + wiring next to existing `--baseline` handling, line ~672)

- [ ] **Step 1 (failing test):** `ledger.append_run(ledger_path, summary)` appends one JSON line `{"timestamp_utc", "tier", "rubric_total", "wall_time_mean", "dimensions": {name: tier}}`; `ledger.compare(ledger_path, summary)` returns `{"vs_last": {...}, "vs_best": {...}}` where each lists dimensions that dropped >= 1 tier vs the last entry and vs the best-ever entry (best = max rubric_total). Empty/missing ledger → both empty. Corrupt line → skipped with a warning string in the result, never a crash.
- [ ] **Step 2 (implement):** `ledger.py` stdlib-only, JSONL append-only. Wire `p.add_argument("--baseline-ledger", type=Path, default=None, help="Append-only JSONL run history; enables vs-last and vs-best regression checks")`; when set: run `compare` BEFORE `append_run`, merge results into `summary["ledger_regressions"]`, and append. The existing single-file `--baseline` flag is unchanged (back-compat).
- [ ] **Step 3:** Suite green; commit: `git commit -m "feat(ledger): append-only run history with vs-last/vs-best regression (SP6 T7)"`

### Task 8: Orchestrator PERF integration — repo B, docs only (W-G, parallel with Wave 2)

**Files (repo B):** Modify: `references/remediation-playbook.md`, `references/prioritization.md`

- [ ] **Step 1:** In repo B `references/remediation-playbook.md`, add one row to the Signal Procedures table: `| PERF | perf-benchmark | Failing perf rubric dimension | Follow the perf-benchmark skill's references/perf-remediation-playbook.md: algorithmic STOP gate, one dimension per batch, >=5% median win within CV bounds, before/after fingerprints must match. |`
- [ ] **Step 2:** In repo B `references/prioritization.md`, under Coverage-Gated Actionability append: `PERF findings rank by dimension priority (algorithmic scaling above all hardware dimensions) and are coverage-gated like all others: an uncovered hot file is characterize-first.`
- [ ] **Step 3:** Repo B suite still green (`python3 -m pytest tests/ -q` → 53 passed — docs-only change). Commit in repo B: `git commit -m "docs: PERF signal procedure + prioritization (SP6 T8)"`

### Task 9: Version + README (orchestrator or 1 worker)

- [ ] SKILL.md frontmatter `version: 0.2.0`; document the new flags (`--max-cv`, `--findings-out`, `--baseline-ledger`) in SKILL.md Workflow and README; add the playbook to a references list in SKILL.md. Suite green. Commit: `git commit -m "feat(skill): v0.2.0 — stats gate, fingerprint, findings bridge, ledger, playbook (SP6 T9)"`

---

## Phase 2: Self-benchmark + ratchet optimization (orchestrator drives; 1 worker per batch)

This machine has NO valgrind (verified): run `--tier fast` only and record that in the report.

- [ ] **Step 1 (bench harness, 1 worker):** Create `benchmarks/bench_parse_massif.py`:

```python
"""Deterministic self-benchmark: parse a synthetic massif.out of SIZE snapshots."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from perf_benchmark.stage_helpers import _parse_massif_out  # noqa: E402


def make_massif(path: Path, size: int) -> None:
    lines = ["desc: synthetic", "cmd: bench", "time_unit: i"]
    for i in range(size):
        lines += [f"snapshot={i}", f"time={i}", f"mem_heap_B={i * 13}",
                  "mem_heap_extra_B=0", "mem_stacks_B=0", "heap_tree=empty"]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    size = int(sys.argv[1])
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "massif.out"
        make_massif(p, size)
        for _ in range(20):
            result = _parse_massif_out(p)
    assert result, "parse produced nothing"


if __name__ == "__main__":
    main()
```

Smoke it: `python3 benchmarks/bench_parse_massif.py 1000` exits 0. Commit.
- [ ] **Step 2 (baseline, orchestrator):**

```bash
python3 scripts/perf_benchmark_pipeline.py --root . \
  --target "python3 benchmarks/bench_parse_massif.py {SIZE}" \
  --sizes 2000,20000 --tier fast --max-cv 5.0 \
  --baseline-ledger /tmp/sp6-self/ledger.jsonl \
  --findings-out /tmp/sp6-self/perf-findings.json \
  --out-dir /tmp/sp6-self/run-baseline
```

Read the summary: percentiles + environment + (if any dimension FAIL/WARN) PERF findings present. If wall-time CV > 5%, the gate must mark stability N/A — that itself is T4 evidence; re-run once on a quiet machine before judging.
- [ ] **Step 3 (ratchet batches, max 2, 1 worker each):** Per `references/perf-remediation-playbook.md`: candidate optimizations for `_parse_massif_out` (stage_helpers.py:255) — e.g. single-pass line parse without intermediate lists, avoiding repeated string scans. ACCEPT only if: median wall-time improves ≥5% at both sizes, CV ≤ 5% in both runs, fingerprints match, suite green. Re-run Step 2's command into `run-batchN` and compare medians yourself. If no candidate clears the bar, record "evaluated, no feasible low-risk win" with both runs' numbers — a valid terminal outcome.
- [ ] **Step 4 (evidence):** Write `docs/dogfood/2026-06-10-sp6-self-bench.md`: commands, baseline vs final medians + percentiles + CV, ledger tail showing ≥2 entries with vs-last/vs-best, findings file (or "no findings — all dimensions PASS"), valgrind-absence note, batch accept/discard table. Commit.

---

## Definition of Done (report with evidence)

1. Repo A suite green INCLUDING on a machine without valgrind (the T1 point); exact final test count reported (baseline 61 + new from T4/T5/T6/T7).
2. CI workflow committed + statically validated; post-push verification flagged to human.
3. `--max-cv` gate: noisy timing scores `N/A (noise)`, excluded from total — test-proven; measurement policy + ISO 25010 mapping present in rubric.md.
4. `benchmark_summary.json` gains `environment` + `wall_time_percentiles` (additive only — no existing key changed or removed).
5. `--findings-out` emits byte-deterministic shared-shape PERF findings (exact key set test-pinned); canonical `SIGNALS` addition explicitly deferred to next repo-audit-skills release and noted in the report.
6. `--baseline-ledger` appends JSONL and reports vs-last/vs-best regressions; corrupt lines never crash.
7. Repo B playbook + prioritization mention PERF; repo B suite still 53 passed.
8. Phase 2: self-benchmark ran at fast tier with ledger + findings; ≥1 ratchet batch accepted with ≥5% median win, OR a documented evaluated-no-win with both runs' numbers. Evidence doc committed.
9. SKILL.md v0.2.0; both repos: commits local only — **nothing pushed, tagged, or released**.

---

## Launch (paste as the goal of a fresh Opus session in /home/jakub/projects/perf-benchmark-skill)

```
You are the ORCHESTRATOR (Opus) for the SP6 perf-benchmark v0.2.0 run, in
/home/jakub/projects/perf-benchmark-skill. Coordinate ONLY, never implement: dispatch MULTIPLE
OpenCode DeepSeek v4 Pro Max workers in parallel (one packet each, own git worktree), keep the
pool SATURATED at the cap of 4, verify every gate yourself by reading real output, own all
merges. Commit locally per task/round; do NOT push, tag, or release — human reviews.

READ FIRST, authoritative: docs/plans/2026-06-10-sp6-perf-bench-v0.2.md. Workers implement plan
tasks VERBATIM via TDD — code, commands, and Expected outputs are in the plan. A worker's
"green" is NOT evidence — re-run gates yourself.

WORKERS: PRIMARY = OpenCode DeepSeek v4 Pro Max via opencode-worker-bridge, multiple concurrent.
FALLBACK (automatic, one-way, logged) ONLY on infrastructure dispatch failure (credits/quota,
auth/billing, bridge unreachable): NATIVE OPUS workers (Agent tool, isolated worktree, same
packet + gates) from then on. A gate-failing CHANGE is a normal discard/retry, NOT a switch.

PRE-FLIGHT (any failure -> STOP): repo clean; python3 -m pytest tests/ -q shows EXACTLY 1
failure (test_stage_massif_post_processing_uses_timeout — environment-dependent, T1 fixes it)
and 60 passed; valgrind ABSENT is expected; repo-audit-refactor-optimize clean (53 passed);
worker-bridge loads.

WAVES (saturate, don't serialize):
  Wave 1: T1 (test fix) || T2 (CI) || T3 (playbook) || T4 (noise gate, TDD) — 4 workers.
  Wave 2: T5 (fingerprint+percentiles) || T6 (findings bridge) || T8 (repo B docs) — 3 workers.
  Wave 2b: T7 (ledger) AFTER T6 merged (same argparse file — serialize).
  Then: T9 version/README. Per-merge gate: suite green in worktree AND re-run by you.
PHASE 2 — SELF-BENCH RATCHET (do not skip): bench harness, baseline run at --tier fast
(valgrind absent — record it), then max 2 optimization batches on _parse_massif_out per the
new perf playbook: ACCEPT only >=5% median win at both sizes, CV <= 5%, fingerprints match,
suite green; else record evaluated-no-win with numbers. Evidence doc committed.

DEFINITION OF DONE: plan's DoD, all 9 items, each with evidence (final test count, gate
outputs, summary keys, findings file, ledger tail, batch table, v0.2.0). Nothing pushed.
```
