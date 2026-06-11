---
name: perf-optimization
version: 0.2.0
description: >
  Evidence-driven performance optimization that consumes perf-benchmark
  findings, selects one bounded candidate, re-measures with identical profiling,
  and records accepted wins or honest no-win outcomes.
---

# Performance Optimization Pipeline

## Overview

Use this skill after `perf-benchmark` has produced PERF findings. It enforces a
measure -> change -> re-measure loop: select one candidate, change one bounded
file-set, re-run the same benchmark, accept only quantified wins, and record
rejections or no-candidate outcomes.

## Inputs

- PERF findings JSON from `perf-benchmark --findings-out`.
- The before-run `benchmark_summary.json`.
- Optional trend ledger from `--baseline-ledger`.
- A green functional test suite for the repository.

PERF findings use shared-schema fields including `id`, `leaf`, `signal`,
`severity`, `path`, `location`, `metric`, `evidence`, `confidence`, and
`suggested_action`. `metric.name` maps the finding to the rubric dimension.

Algorithmic metric names are `complexity_exponent`, `call_amplification`,
`data_reuse`, `write_amplification`, `allocation_churn`, and
`multiplicative_paths`. A high-severity algorithmic finding is a STOP gate:
algorithmic remediation is the only eligible work until it is resolved.

## Select

```bash
python perf-optimization/scripts/select_candidate.py \
  --findings /tmp/perf-findings.json \
  --out /tmp/candidate.json
```

The selector writes either:

```json
{"status":"ok","candidate":{"id":"...","path":"src/hot_loop.py","metric_name":"l1_miss_rate","severity":"high","ratio":4.2,"stop_gate":false}}
```

or:

```json
{"status":"no_candidates"}
```

`no_candidates` exits 1 and is a valid terminal outcome: record
`evaluated, no feasible low-risk win`.

## Change

Apply exactly one performance change per iteration.

- Target one rubric dimension from `candidate.metric_name`.
- Start with `candidate.path`; expand only when the technique requires it.
- Add behavior tests before touching uncovered production code.
- Run the full test suite before profiling.
- Do not mix algorithmic, data-layout, cache, branch, and CPU changes.

Use `references/optimization-playbook.md` for technique selection and
`../references/perf-remediation-playbook.md` for execution discipline.

## Verify

Re-run the same `perf-benchmark` command shape: same tier, sizes, target, root,
and machine. Then compare summaries:

```bash
python perf-optimization/scripts/verify_win.py \
  --before /path/to/before/benchmark_summary.json \
  --after /path/to/after/benchmark_summary.json \
  --suite-exit-code 0 \
  --ledger docs/perf/baseline_ledger.jsonl \
  --out /tmp/verdict.json
```

Accept only when all hold:

- p50 median improvement is at least 5% for the target dimension.
- Neither run has timing scored `N/A (noise)`.
- Environment fingerprint matches on CPU model, kernel, governor, SMT, and
  Python version.
- The functional suite is green.
- No other scored dimension regresses by one or more tiers.

Reject means revert the change and keep the evidence. Accepted wins are
committed one iteration at a time and appended to the ledger.

## Outputs

- `candidate.json`: selected candidate or no-candidate status.
- `verdict.json`: accept, reject, or no-feasible-win evidence.
- Updated baseline ledger for accepted or recorded verification runs.
- One commit per accepted optimization, or an evidence commit for no-candidate.

## Limits

- This skill does not profile from scratch; run `perf-benchmark` first.
- A high-severity algorithmic finding blocks constant-factor tuning.
- One iteration may change only one bounded file-set and one dimension.
- Noisy or fingerprint-mismatched measurements cannot prove a win.
