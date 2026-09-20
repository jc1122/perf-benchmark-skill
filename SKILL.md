---
name: perf-benchmark
description: >
  Use when profiling Linux Python or C workloads for algorithmic scaling,
  wall-time stability, CPU, cache, branch, or memory behavior, or when
  verifying a claimed optimization with a before/after comparison.
metadata:
  version: 1.0.0
---

# Performance Benchmark

Measure first, change only when authorized. A benchmark run never edits code.
Optimization work starts only on explicit user request, and every claimed win
must survive an identical before/after comparison. Follow the user's repository
workflow for commits; this skill never commits by itself.

## Measure

```bash
perf-benchmark \
  --root /path/to/repo \
  --out-dir /tmp/perf-bench \
  --target "python -m benchmark_entrypoint {SIZE}" \
  --sizes 1000,4000
```

Use `--binary ./program` for standalone binaries.
Use `--target` or `--binary` for non-pytest repos.
Pytest benchmark autodiscovery is a convenience for Python repos.
Multi-size explicit targets must include `{SIZE}`.

Scripts resolve relative to the skill directory when pip is unavailable.

Regression example: `perf-benchmark --root . --out-dir /tmp/bench --sizes 1000,4000 --target "./path/to/benchmark {SIZE}" --baseline /path/to/previous/benchmark_summary.json`

## Key Flags

- `--root`, `--out-dir`: repository under analysis; where reports go.
- `--target`, `--binary`: what to run (`{SIZE}` required with `--sizes`).
- `--tier`: `fast` (default), `medium`, `deep`, or `asm`.
- `--sizes`: input sizes for scaling evidence, e.g. `1000,4000,16000`.
- `--expected-complexity`: `linear`, `nlogn` (default), or `quadratic`.
- `--max-cv`: noise gate (default 5.0); noisy timing scores `N/A (noise)`.
- `--findings-out`: shared-schema PERF findings for FAIL/WARN dimensions.
- `--baseline-ledger`: opt-in append-only JSONL run history.
- `--perf-record`, `--asm-audit`: opt-in hotspots / ASM in deep runs.

## Tiers

- `fast`: direct timing, tracemalloc, GNU time. Scores scaling exponent,
  wall-time stability, and a memory-lite check; cache, branch, and CPU
  dimensions report `N/A` instead of half-scores.
- `medium`: fast plus cachegrind and callgrind (20-100x slowdown).
- `deep`: medium plus massif, `perf stat`, optional `--perf-record`.
- `asm`: deep plus objdump and optional Numba ASM inspection.

Full Algorithmic Scaling scoring requires `deep` or `asm` because allocation churn comes from massif.

## Optimize (only when authorized)

1. Select one candidate from PERF findings (algorithmic FAIL gates all
   constant-factor work; see `references/optimization-check.md`).
2. Change one bounded file-set for one rubric dimension; add behavior tests
   before touching uncovered code.
3. Re-run the identical benchmark shape: same tier, sizes, target, machine.
4. Verify with `perf-verify-win` (or the script at
   `scripts/perf_benchmark/verify_win.py`); accept only on `accept`.
5. Record honest no-win outcomes (`evaluated, no feasible low-risk win`) with
   the evidence instead of forcing a change.

## Verify Gates

- Fingerprint (CPU, kernel, governor, SMT, Python) and workload (tier,
  sizes, target, repeats, noise gate, complexity inputs) must match; each run
  needs >= 2 wall-time samples and a typed non-empty rubric.
- Noisy timing (`N/A (noise)`) in either run voids the comparison.
- Objective policy: wall-time p50 uses the configurable `--min-win`
  threshold (default 5%, a wall-time convention only); memory compares peak
  bytes against an explicitly chosen threshold; scaling needs strict exponent
  improvement. Wall-time or exponent collapse rejects under any objective;
  cross-objective tradeoffs need explicit user approval, recorded with the run.
- The suite must be proven green by bound evidence: a structured JSON record
  via `--suite-evidence` (int `exit_code` plus a matching after-run
  `target`/`root`/`revision`), or a live run via `--suite-command`.
  Arbitrary files never count as verified. Without bound green evidence the
  best verdict is `advisory`: measurement-only, not functional proof.
- No scored dimension may be added, dropped, or regress by a tier.

```bash
perf-verify-win --before /path/to/before/benchmark_summary.json --after /path/to/after/benchmark_summary.json --suite-exit-code 0 --suite-evidence /path/to/suite-record.json --out /tmp/verdict.json
```

Verdicts: `accept` (proven win), `reject` (a gate failed), `advisory`
(measurements pass, functionality unproven), `error` (malformed input).

## Parallelism

Tier 1 stays isolated because timing and tracemalloc measurements are noise-sensitive.
Preferred subagent split: per-artifact or per-rubric-dimension after the pipeline finishes.

## Outputs

- `benchmark_report.md`: scorecard, findings, prescriptions.
- `benchmark_summary.json`: machine summary with a `workload` comparability block.
- Findings, ledger, `verdict.json` (`accept` / `reject` / `advisory` / `error`): only when requested.

## Install

```bash
bootstrap/install-perf.sh --dest <skills-dir>
bootstrap/install-perf.sh --harness codex   # ~/.agents/skills
bootstrap/install-perf.sh --harness claude  # ~/.claude/skills
```

The same content ships to both hosts; scripts resolve relative to the skill
directory. Alternatively `pip install .` provides `perf-benchmark`,
`perf-verify-win`, and `perf-select-candidate`.

## Limits

- Linux only; `/proc`, `/sys`, Valgrind, and `perf` shape depth.
- `tracemalloc` sees Python allocations, not all native memory; cachegrind
  models L1 plus last-level cache only.
- `perf stat` / `--perf-record` need permissive `perf_event_paranoid`; throughput-at-load (capacity) testing is out of scope.

## References

- `references/rubric.md`: thresholds and scoring details.
- `references/tool-guide.md`: profiler selection and limitations.
- `references/optimization-check.md`: the authorized-change loop in full.
- `references/optimization-playbook.md`: technique catalogue (appendix).
- `references/perf-remediation-playbook.md`: execution discipline.
- `references/finding-schema.json`: PERF finding schema.
- `references/question-bank.md`: advisory diagnosis prompts.
- `references/sample-report.md`: compact example report.
