# Sample Performance Benchmark Report

**Target:** graph_workload library -- `compute_shortest_paths()` on adjacency list graph
**Date:** 2026-03-05
**Analyst:** perf-benchmark-skill (automated)

---

## 1. Prerequisites

| Check | Status |
|-------|--------|
| CPU governor | `performance` (confirmed via `/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor`) |
| perf_event_paranoid | 1 (hardware counters available) |
| System load | idle (load avg 0.02) |
| Valgrind version | 3.22.0 |
| Python version | 3.11.8 |
| Warm-up rounds | 5 (pytest-benchmark default) |

---

## 2. Benchmark Targets

| Target | Function | Input Sizes |
|--------|----------|-------------|
| Primary | `graph_workload.compute_shortest_paths()` | N=1000, N=5000 |
| Entry point | `benchmark_shortest_paths` in `tests/benchmarks/test_benchmark_graph.py` |

---

## 3. Algorithmic Scaling Analysis (Dimension 0)

### Complexity Exponent

| Input Size (N) | Wall Time (ms) | Ratio |
|----------------|----------------|-------|
| 1000 | 12.4 | -- |
| 5000 | 105.8 | 8.53x |

Fit: `T(n) = c * n^k` where `k = log(105.8/12.4) / log(5000/1000) = 1.45`

Expected complexity: O(n log n) (default `--expected-complexity nlogn`, FAIL threshold k > 1.5).

**Result: k = 1.45 -- WARN** (within nlogn threshold but above ideal linear scaling)

### Sub-check Summary

| Sub-check | Metric | Value | Tier |
|-----------|--------|-------|------|
| 0a: Complexity exponent | k | 1.45 | WARN |
| 0b: Call amplification | calls/N | 42x | WARN |
| 0c: Data reuse ratio | Dr/N | 8.2x | PASS |
| 0d: Write amplification | Dw/Dr | 0.15 | PASS |
| 0e: Allocation churn | pattern | staircase | WARN |
| 0f: Multiplicative paths | count | 0 | PASS |

**Dimension 0 composite: WARN (2)** -- Three WARN sub-checks, no FAIL.

---

## 4. Scorecard

| Dim | Dimension | Score | Tier | Key Metric |
|-----|-----------|-------|------|------------|
| 0 | Algorithmic Scaling | 2 | WARN | k=1.45, call amp 42x |
| 1 | Wall-time stability | 4 | PASS | CV 2.1% |
| 2 | CPU efficiency | 2 | WARN | top fn 28% of Ir |
| 3 | L1 cache efficiency | 0 | FAIL | L1d miss 7.2% |
| 4 | Last-level cache | 4 | PASS | LL miss 0.3% |
| 5 | Branch prediction | 4 | PASS | mispred 0.8% |
| 6 | Memory profile | 2 | WARN | peak 1.3x baseline |
| **Total** | | **18/28** | | **Workable baseline** |

---

## 5. Findings

### Finding: Dimension 0 -- Algorithmic Scaling (WARN)

```json
{
  "dimension": "Algorithmic Scaling",
  "score": 2,
  "tier": "WARN",
  "evidence": [
    {
      "file": "src/graph_workload/pathfinder.py",
      "line": 87,
      "function": "compute_shortest_paths",
      "metric": "complexity_exponent",
      "value": 1.45,
      "unit": "ratio",
      "threshold_pass": 1.3,
      "threshold_fail": 1.8
    },
    {
      "file": "src/graph_workload/pathfinder.py",
      "line": 112,
      "function": "_relax_edges",
      "metric": "call_amplification",
      "value": 42,
      "unit": "calls/N",
      "threshold_pass": 10,
      "threshold_fail": 100
    }
  ],
  "prescription": "Call amplification in _relax_edges (42x) suggests redundant neighbor lookups. Consider caching the adjacency list iteration or converting to a CSR representation for O(1) neighbor access. This should reduce k toward 1.2-1.3."
}
```

### Finding: Dimension 1 -- Wall-time Stability (PASS)

```json
{
  "dimension": "Wall-time stability",
  "score": 4,
  "tier": "PASS",
  "evidence": [
    {
      "file": "tests/benchmarks/test_benchmark_graph.py",
      "function": "benchmark_shortest_paths",
      "metric": "wall_time_cv",
      "value": 2.1,
      "unit": "%",
      "threshold_pass": 3,
      "threshold_fail": 8
    }
  ],
  "prescription": "No action needed. CV of 2.1% indicates stable measurement conditions."
}
```

### Finding: Dimension 2 -- CPU Efficiency (WARN)

```json
{
  "dimension": "CPU efficiency",
  "score": 2,
  "tier": "WARN",
  "evidence": [
    {
      "file": "src/graph_workload/pathfinder.py",
      "line": 112,
      "function": "_relax_edges",
      "metric": "instruction_share",
      "value": 28,
      "unit": "%",
      "threshold_pass": 20,
      "threshold_fail": 35
    },
    {
      "file": "perf_stat_output",
      "metric": "IPC",
      "value": 1.62,
      "unit": "insn/cycle",
      "threshold_pass": 1.5,
      "threshold_fail": 1.0
    }
  ],
  "prescription": "_relax_edges accounts for 28% of instructions. IPC is healthy (1.62) so the bottleneck is instruction count, not stalls. Reducing call amplification (Dim 0 fix) will directly reduce this function's share."
}
```

### Finding: Dimension 3 -- L1 Cache Efficiency (FAIL)

```json
{
  "dimension": "L1 cache efficiency",
  "score": 0,
  "tier": "FAIL",
  "evidence": [
    {
      "file": "src/graph_workload/graph.py",
      "line": 45,
      "function": "AdjacencyList.__getitem__",
      "metric": "L1d_miss_rate",
      "value": 7.2,
      "unit": "%",
      "threshold_pass": 1,
      "threshold_fail": 5
    },
    {
      "file": "src/graph_workload/graph.py",
      "line": 62,
      "function": "AdjacencyList.neighbors",
      "metric": "L1d_miss_rate",
      "value": 5.8,
      "unit": "%",
      "threshold_pass": 1,
      "threshold_fail": 5
    }
  ],
  "prescription": "L1d miss rate of 7.2% in AdjacencyList.__getitem__ indicates poor spatial locality. The adjacency list uses Python dicts of lists, causing pointer chasing. Convert to a flat CSR (Compressed Sparse Row) representation using numpy arrays for contiguous memory layout. Expected improvement: 5-15x for neighbor traversal."
}
```

### Finding: Dimension 4 -- Last-Level Cache (PASS)

```json
{
  "dimension": "Last-level cache",
  "score": 4,
  "tier": "PASS",
  "evidence": [
    {
      "file": "src/graph_workload/graph.py",
      "function": "AdjacencyList.__getitem__",
      "metric": "LL_miss_rate",
      "value": 0.3,
      "unit": "%",
      "threshold_pass": 0.5,
      "threshold_fail": 2
    }
  ],
  "prescription": "No action needed. Working set fits in LLC despite L1 misses, confirming the issue is spatial locality, not total data size."
}
```

### Finding: Dimension 5 -- Branch Prediction (PASS)

```json
{
  "dimension": "Branch prediction",
  "score": 4,
  "tier": "PASS",
  "evidence": [
    {
      "file": "src/graph_workload/pathfinder.py",
      "function": "_relax_edges",
      "metric": "branch_mispred_rate",
      "value": 0.8,
      "unit": "%",
      "threshold_pass": 1,
      "threshold_fail": 3
    }
  ],
  "prescription": "No action needed. Branch prediction is within acceptable bounds."
}
```

### Finding: Dimension 6 -- Memory Profile (WARN)

```json
{
  "dimension": "Memory profile",
  "score": 2,
  "tier": "WARN",
  "evidence": [
    {
      "file": "src/graph_workload/pathfinder.py",
      "function": "compute_shortest_paths",
      "metric": "heap_peak_ratio",
      "value": 1.3,
      "unit": "ratio",
      "threshold_pass": 1.1,
      "threshold_fail": 1.5
    }
  ],
  "prescription": "Peak heap is 1.3x the input graph size, indicating temporary allocations during path computation. The staircase pattern in massif (sub-check 0e) suggests distance arrays are re-allocated per source vertex. Pre-allocate a single distance buffer and reuse across iterations."
}
```

---

## 6. Prescriptions (Priority-Ordered)

| Priority | Action | Expected Impact | Dimensions Affected |
|----------|--------|-----------------|---------------------|
| 1 (Algorithmic) | Convert adjacency list from dict-of-lists to CSR numpy arrays | 5-15x for neighbor traversal | Dim 0, Dim 3, Dim 2 |
| 2 (Algorithmic) | Pre-allocate distance buffer; reuse across source vertices | Reduce allocation churn, lower peak memory | Dim 0, Dim 6 |
| 3 (Execution) | After CSR conversion, re-profile to confirm L1d miss rate drops below 1% | Validates data layout fix | Dim 3 |

---

## 7. Valgrind Cache Model

The following cache parameters were used by cachegrind during this analysis:

```
I1:  32768 B, 8-way, 64 B lines
D1:  32768 B, 8-way, 64 B lines
LL:  8388608 B, 16-way, 64 B lines
```

Note: Cachegrind uses a 2-level cache model (L1 + LL). There is no separate L2 simulation. The LL parameters approximate L3 behavior. L1 miss rates are reliable; LL miss rates should be cross-validated with `perf stat` hardware counters if precise L2/L3 distinction is needed.

All cachegrind metrics were scored per-file using `cg_annotate --include=src/graph_workload/` to exclude interpreter and library overhead.

---

## 8. Next Steps

1. Implement CSR conversion (Priority 1). This single change is expected to resolve Dim 3 (FAIL -> PASS) and improve Dim 0 and Dim 2.
2. Re-run the full benchmark suite after the CSR change to validate improvements.
3. Implement buffer pre-allocation (Priority 2) to address Dim 6.
4. Target score after fixes: 24-26/28 (strong performance profile).
