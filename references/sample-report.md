# Sample Performance Benchmark Report

**Target:** `graph_workload.compute_shortest_paths()`
**Tier:** `deep`
**Sizes:** `1000,5000`
**Result:** 18/28, workable baseline

## Prerequisites

| Check | Result |
| --- | --- |
| CPU governor | `performance` |
| `perf_event_paranoid` | `1` |
| Valgrind | `3.22.0` |
| Python | `3.11.8` |

## Scorecard

| Dimension | Tier | Key metric |
| --- | --- | --- |
| Algorithmic Scaling | WARN | exponent `1.45`, call amp `42x` |
| Wall-Time Stability | PASS | CV `2.1%` |
| CPU Efficiency | WARN | top function `28%` instructions |
| L1 Cache | FAIL | L1d miss `7.2%` |
| Last-Level Cache | PASS | LL miss `0.3%` |
| Branch Prediction | PASS | mispredict `0.8%` |
| Memory Profile | WARN | peak `1.3x` baseline |

## Findings

```json
[
  {
    "leaf": "perf-benchmark",
    "signal": "PERF",
    "severity": "high",
    "path": "src/graph_workload/graph.py",
    "metric": {"name": "l1_miss_rate", "value": 7.2, "threshold": 5.0},
    "suggested_action": "Improve adjacency-list locality before CPU tuning."
  }
]
```

## Prescription Order

1. Fix algorithmic or data-structure causes before hardware-level tuning.
2. Re-profile with the same tier, sizes, target, and machine.
3. Accept a change only when tests are green and the measured win survives the
   noise and fingerprint gates.

## Notes

Cachegrind uses an L1 plus last-level model; validate precise hardware-counter
claims with `perf stat` when available.
