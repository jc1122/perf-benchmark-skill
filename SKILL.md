---
name: perf-benchmark
version: 0.4.3
description: >
  Use when profiling Linux Python or C workloads for algorithmic scaling,
  cache, branch, memory, or ASM bottlenecks, or when comparing a benchmark run
  against a saved performance baseline.
---

# Performance Benchmark Pipeline

## Overview

Run a deterministic Linux performance diagnosis. The pipeline profiles an
explicit benchmark target or binary, scores a 7-dimension rubric, writes raw
artifacts, and can emit shared-schema PERF findings plus an append-only trend
ledger.

Use this skill when you need evidence for algorithmic scaling, wall-time
stability, CPU efficiency, cache behavior, branch prediction, memory profile,
or ASM-level review.

## Command

```bash
python scripts/perf_benchmark_pipeline.py \
  --root /path/to/repo \
  --out-dir /tmp/perf-bench \
  --target "python -m benchmark_entrypoint {SIZE}" \
  --sizes 1000,4000,16000 \
  --tier fast \
  --max-cv 5.0 \
  --findings-out /tmp/perf-findings.json \
  --baseline-ledger /tmp/perf-ledger.jsonl
```

Use `--binary ./program` instead of `--target` for standalone binaries.
Use `--target` or `--binary` for non-pytest repos.
Pytest benchmark autodiscovery is a convenience for Python repos.
Multi-size explicit targets must include `{SIZE}`.

## Key Flags

- `--root`: repository root under analysis.
- `--out-dir`: output directory for reports and raw profiler artifacts.
- `--target`: command template to benchmark; include `{SIZE}` with `--sizes`.
- `--binary`: standalone binary entrypoint.
- `--source-prefix`: project source filter; repeat for multiple prefixes.
- `--tier`: `fast`, `medium`, `deep`, or `asm`.
- `--sizes`: comma-separated input sizes for scaling checks.
- `--expected-complexity`: expected growth class for scaling scoring.
- `--max-cv`: timing-noise gate; noisy timing dimensions become `N/A (noise)`.
- `--baseline`: point-in-time `benchmark_summary.json` comparison.
- `--baseline-ledger`: append JSONL history and compare vs last/best entries.
- `--findings-out`: shared-schema PERF findings for FAIL/WARN dimensions.
- `--perf-record`: opt-in native sampled hotspots in deep/asm runs.
- `--asm-audit`: include objdump/Numba ASM checks in asm tier.

## Tiers

- `fast`: pytest-benchmark or direct timing, tracemalloc, GNU time.
- `medium`: fast plus cachegrind and callgrind.
- `deep`: medium plus massif, perf stat, and optional `--perf-record`.
- `asm`: deep plus objdump and optional Numba ASM inspection.

## Outputs

- `benchmark_report.md`: human report with scorecard and prescriptions.
- `benchmark_summary.json`: machine summary and regression comparison data.
- `perf_findings.json`: PERF findings when `--findings-out` is set.
- `baseline_ledger.jsonl`: trend history when `--baseline-ledger` is set.
- `tier1/` through `tier4/`: raw profiler artifacts by tier.

## Interpretation

The rubric scores Algorithmic Scaling, Wall-Time Stability, CPU Efficiency,
L1 Cache, Last-Level Cache, Branch Prediction, and Memory Profile from 0 to 4.
If Algorithmic Scaling fails, fix asymptotic behavior before cache, branch, or
ASM tuning. Full scaling evidence requires multi-size runs; allocation churn
requires `deep` or `asm` because it comes from massif.
Full Algorithmic Scaling scoring requires `deep` or `asm` because allocation churn comes from massif.

Regression example:

```bash
python scripts/perf_benchmark_pipeline.py \
  --root . --out-dir /tmp/bench --sizes 1000,4000 \
  --target "./path/to/benchmark {SIZE}" --baseline /path/to/previous/benchmark_summary.json
```

## Agent Parallelism

Tier 1 stays isolated because timing and tracemalloc measurements are noise-sensitive.
Preferred subagent split: per-artifact or per-rubric-dimension after the pipeline finishes.

## References

- `references/rubric.md`: thresholds and scoring details.
- `references/tool-guide.md`: profiler selection and limitations.
- `references/perf-remediation-playbook.md`: measure/change/re-measure rules.
- `references/question-bank.md`: advisory diagnosis prompts.
- `references/finding-schema.json`: PERF finding schema.
- `references/sample-report.md`: compact example report.

## Limits

- Linux only; `/proc`, `/sys`, Valgrind, and `perf` availability shape depth.
- Valgrind slows runs heavily and models L1 plus last-level cache only.
- `perf stat` and `--perf-record` require permissive `perf_event_paranoid`.
- `tracemalloc` sees Python allocations, not all native/C extension memory.
- Noisy timing is refused by `--max-cv` instead of being over-interpreted.
