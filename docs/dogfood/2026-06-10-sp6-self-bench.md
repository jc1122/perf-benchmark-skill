# SP6 Phase 2 Self-Benchmark Ratchet - 2026-06-10

## Purpose

Run the perf-benchmark pipeline against its own parser benchmark
(`bench_parse_massif.py`) as a dogfood ratchet.  The goal was to identify
a measurable performance improvement of at least **5 % median wall-time**
relative to a pre-recorded baseline and merge it into `main`.

**Result**: neither optimization candidate cleared the acceptance
threshold, so neither was merged.  This document records the evidence
and the no-win outcome.

---

## Benchmark Target

```
python3 benchmarks/bench_parse_massif.py {SIZE}
```

`{SIZE}` is replaced at runtime with the massif file size used for that
invocation (2000 or 20000 in this ratchet).

---

## Pipeline Command Shape

```
python3 scripts/perf_benchmark_pipeline.py \
  --root . \
  --target "python3 benchmarks/bench_parse_massif.py {SIZE}" \
  --sizes 2000,20000 \
  --tier fast \
  --max-cv 5.0 \
  --baseline-ledger /tmp/sp6-self/ledger.jsonl \
  --findings-out /tmp/sp6-self/perf-findings.json \
  --out-dir /tmp/sp6-self/run-{batch}
```

The pipeline was run once for the **baseline** and once for each
optimization batch (`run-baseline`, `run-batch1`, `run-batch2`).

---

## Environment Caveats

| Parameter            | Value                                      |
| -------------------- | ------------------------------------------ |
| CPU                  | 13th Gen Intel(R) Core(TM) i5-1340P        |
| Kernel               | `7.0.0-22-generic`                         |
| Python               | `3.14.4`                                   |
| CPU governor         | `powersave`                                |
| SMT                  | `1` (single-thread)                        |
| `perf_event_paranoid`| `4` - `perf stat` was skipped              |
| `valgrind`           | unavailable in this environment            |

**Noise note**: the `powersave` governor and general-purpose system
load introduced enough jitter that small wall-time deltas (under
~10 %) cannot be reliably attributed to code changes.  This is
reflected in the Wall-Time Stability dimension being scored `WARN` or
`N/A (noise)` across all runs.

---

## Baseline

| Property            | Value                                        |
| ------------------- | -------------------------------------------- |
| Run dir             | `/tmp/sp6-self/run-baseline`                 |
| Timestamp           | `2026-06-10T20:08:04+00:00`                  |
| Pipeline CV         | **3.67** (within 5.0 cap)                    |
| CV by size          | 2000 -> 0.0, 20000 -> 3.67                     |

### Wall-Time Measurements (seconds)

| Size   | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | Median | Mean   |
| ------ | ----- | ----- | ----- | ----- | ----- | ------ | ------ |
| 2000   | 0.07  | 0.07  | 0.07  | 0.07  | 0.07  | 0.07   | 0.07   |
| 20000  | 0.54  | 0.56  | 0.56  | 0.59  | 0.54  | 0.56   | 0.558  |

### Rubric Summary

| Dimension            | Score |
| -------------------- | ----- |
| Wall-Time Stability  | WARN  |
| Memory Profile       | PASS  |
| Algorithmic Scaling  | N/A   |
| **Summary**          | **6 / 8** (2 of 7 dimensions scored) |

The baseline run produced one **medium** PERF finding in
`/tmp/sp6-self/perf-findings.json` for `wall_time_cv=3.67` exceeding
the preferred threshold of **3.0**.

---

## Batch 1 - `sp6-p2-opt1`

| Property       | Value                                                                 |
| -------------- | --------------------------------------------------------------------- |
| Branch         | `sp6-p2-opt1`                                                         |
| Commit         | `4c89ce936bf61b4b7be974e4bf8894d827b6c5fb`                            |
| Run dir        | `/tmp/sp6-self/run-batch1`                                            |
| Pre-flight     | bridge contracts passed, ruff passed, ruff format passed, `pytest -q` -> **101 passed** |

### Wall-Time Measurements (seconds)

| Size   | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | Median | Mean   |
| ------ | ----- | ----- | ----- | ----- | ----- | ------ | ------ |
| 2000   | 0.09  | 0.08  | 0.09  | 0.09  | 0.09  | 0.09   | 0.088  |
| 20000  | 0.64  | 0.67  | 0.65  | 0.63  | 0.65  | 0.65   | 0.648  |

| Metric      | Value   |
| ----------- | ------- |
| Pipeline CV | **5.08**|
| CV by size  | 2000 -> 5.08, 20000 -> 2.29 |

### Rubric

| Dimension            | Score        |
| -------------------- | ------------ |
| Wall-Time Stability  | N/A (noise)  |
| Memory Profile       | PASS         |
| **Summary**          | **4 / 8**    |

### Outcome - **REJECTED**

Batch 1 regressed relative to baseline on both median (26 % slower at
2000, 16 % slower at 20000) and exceeded the **max-cv 5.0** cap.
**Not merged.**

---

## Batch 2 - `sp6-p2-opt2`

| Property       | Value                                                                 |
| -------------- | --------------------------------------------------------------------- |
| Branch         | `sp6-p2-opt2`                                                         |
| Commit         | `f301ffeb3ca07c976f36907ceddbd5d13ab8167c`                            |
| Run dir        | `/tmp/sp6-self/run-batch2`                                            |
| Pre-flight     | bridge contracts passed, benchmark smoke passed, ruff passed, ruff format passed, `pytest -q` -> **99 passed** |

### Wall-Time Measurements (seconds)

| Size   | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 | Median | Mean   |
| ------ | ----- | ----- | ----- | ----- | ----- | ------ | ------ |
| 2000   | 0.07  | 0.08  | 0.08  | 0.08  | 0.08  | 0.08   | 0.078  |
| 20000  | 0.64  | 0.64  | 0.65  | 0.67  | 0.62  | 0.64   | 0.644  |

| Metric      | Value   |
| ----------- | ------- |
| Pipeline CV | **5.73**|
| CV by size  | 2000 -> 5.73, 20000 -> 2.82 |

### Rubric

| Dimension            | Score        |
| -------------------- | ------------ |
| Wall-Time Stability  | N/A (noise)  |
| Memory Profile       | PASS         |
| **Summary**          | **4 / 8**    |

### Outcome - **REJECTED**

Batch 2 improved 20000-line median from 0.65 to 0.64 relative to
batch 1 but remained **14 % slower** than the baseline median.  It
also exceeded the **max-cv 5.0** cap.  **Not merged.**

---

## Run Comparison (all batches)

| Run        | Median (2000) | Median (20000) | CV    | Rubric | Merged? |
| ---------- | ------------- | -------------- | ----- | ------ | ------- |
| Baseline   | **0.07**      | **0.56**       | 3.67  | 6 / 8  | N/A     |
| Batch 1    | 0.09 (+26 %)  | 0.65 (+16 %)   | 5.08  | 4 / 8  | **No**  |
| Batch 2    | 0.08 (+14 %)  | 0.64 (+14 %)   | 5.73  | 4 / 8  | **No**  |

---

## Ledger

**`/tmp/sp6-self/ledger.jsonl`** contains three entries: baseline,
batch 1, batch 2.

| Entry     | Wall-Time Stability | Memory Profile | Rubric Total |
| --------- | ------------------- | -------------- | ------------ |
| Baseline  | WARN                | PASS           | 6            |
| Batch 1   | N/A (noise)         | PASS           | 4            |
| Batch 2   | N/A (noise)         | PASS           | 4            |

Each pipeline append reported `vs_last=0 vs_best=0 warnings=0` -
confirming no improvement was detected relative to the best (baseline).

---

## Final Decision

- **No Phase 2 optimization branch was merged.**
- Current `main` retains the self-benchmark harness and all v0.2.0 SP6
  feature work, but does **not** include either rejected parser
  candidate.
- The ratchet itself functioned correctly: both candidates were
  evaluated, both failed the 5 % median-improvement gate, and both
  exceeded the CV cap of 5.0, so the pipeline correctly rejected them.

### Recommendation for the next ratchet

1. **Stabilise the environment** - switch the CPU governor from
   `powersave` to `performance` and reduce background load to lower
   jitter.
2. **Select a more dominant target** - the current parser benchmark
   spends very little time in the optimised code path relative to
   measurement overhead.  A target where the hot path dominates wall
   time more strongly will produce a larger signal-to-noise ratio.
