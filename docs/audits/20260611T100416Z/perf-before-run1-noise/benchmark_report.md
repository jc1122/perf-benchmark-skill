# Performance Benchmark Report

**Generated**: 2026-06-11 10:13:09 UTC
**Root**: `/home/jakub/projects/perf-benchmark-skill`
**Tier**: fast
**Sizes**: [1000, 4000, 16000]

## Prerequisites

- Python: 3.14.4 (OK)
- Valgrind: not found
- perf_event_paranoid: 4 (perf UNAVAILABLE, run: sudo sysctl kernel.perf_event_paranoid=1)
- CPU governor: powersave (WARNING, set to performance for stable results)
- RAM: 15091MB
- Cache model: D1=49152,12,64, I1=32768,8,64, LL=12582912,8,64

## Algorithmic Scaling Analysis

*Incomplete evidence for strict scaling rubric*

| Available Sub-check | Value | Tier |
|---------------------|-------|------|
| complexity_exponent | 0.809 | PASS |

Missing sub-checks:
- `allocation_churn`
- `call_amplification`
- `data_reuse`
- `multiplicative_paths`
- `write_amplification`


## Rubric Scorecard

**Total: 4/4**

| # | Dimension | Score | Tier |
|---|-----------|-------|------|
| 0 | Algorithmic Scaling | N/A | N/A |
| 1 | Wall-Time Stability | -1/4 | N/A (noise) |
| 2 | CPU Efficiency | N/A | N/A |
| 3 | L1 Cache Efficiency | N/A | N/A |
| 4 | Last-Level Cache | N/A | N/A |
| 5 | Branch Prediction | N/A | N/A |
| 6 | Memory Profile | 4/4 | PASS |

## Findings

## Prescriptions

*Priority order: Algorithmic > Data Layout > Execution > Micro*


## Cache Model

Valgrind cachegrind simulates a 2-level cache (L1 -> LL). No separate L2 simulation.
Simulated: D1=49152,12,64, I1=32768,8,64, LL=12582912,8,64
On hybrid CPUs (Intel Alder/Raptor Lake), P-core cache hierarchy is simulated.
