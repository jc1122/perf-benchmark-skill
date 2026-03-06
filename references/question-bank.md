# Question Bank

Performance audit questions organized by category. Use these during analysis to systematically identify bottlenecks and validate findings.

---

## Algorithmic Complexity

- Is the hot function memory-bound or compute-bound?
- What is the expected algorithmic complexity? Does measured scaling match?
- Is there a lower-complexity algorithm or data structure for the same result?
- Can the search space be pruned, partitioned, indexed, or short-circuited earlier?
- Can any inner loop computation be hoisted or precomputed?
- Can repeated subproblems be memoized, cached, or maintained incrementally?
- Are there redundant traversals of the same data structure?
- Are queries scanning full state where an index, summary, or cached partial result would suffice?
- Is the code doing work proportional to all candidates instead of only the needed matches?
- Does the call graph show multiplicative paths (e.g., O(n) calls each doing O(n) work)?
- Is call amplification (calls per input element) within expected bounds?
- Are there unnecessary copies of large data structures inside loops?
- Is unchanged data being reread or recomputed even though the current result depends on only a subset?
- Can a more efficient algorithm or data structure reduce the complexity class?

---

## Streaming and Incremental Workloads

- Should per-update work scale with delta size or with total retained state? What does the benchmark show?
- Is each update or batch recomputing results over the full historical dataset?
- Which prior-state fields are actually needed for one update, and which are touched anyway?
- Is unchanged historical data being reread, reparsed, rehashed, resorted, or recopied?
- Can derived state be maintained incrementally instead of rebuilt from scratch?
- Can append-only history be summarized once so old records are not repeatedly reprocessed?
- Can state be partitioned, windowed, compacted, or checkpointed so cold history stays untouched?
- Can prefix aggregates, sketches, materialized indexes, or caches bound per-update work?

---

## Data Layout

- Is data layout struct-of-arrays or array-of-structs?
- Are hot fields co-located in the same cache line?
- Is data accessed sequentially or randomly?
- Are arrays contiguous in memory (C-order vs Fortran-order for multidimensional)?
- Is the stride between accessed elements 1 (sequential) or larger (strided)?
- Can hot fields be separated from cold fields to improve cache utilization?
- For Python: are NumPy arrays used instead of lists of objects for numeric data?

---

## Cache Behavior

- Which functions have the highest L1d miss rate?
- Is the working set larger than L1d? Than L2? Than L3?
- Are there cache line false sharing issues in concurrent code?
- Does the access pattern cause conflict misses (power-of-2 stride aliasing)?
- Can loop tiling or blocking reduce the working set per iteration?
- Are prefetch hints appropriate for predictable access patterns with long stride?
- Is the data reuse ratio (reads per input element) reasonable for the algorithm?

---

## Branch Patterns

- Which branches have >1% misprediction rate?
- Can conditional branches be replaced with cmov or lookup tables?
- Are branch hints or likely/unlikely annotations appropriate?
- Is the branch pattern data-dependent or control-dependent?
- Can sorting or partitioning input data reduce branch mispredictions?
- Are there branches inside inner loops that could be hoisted outside?

---

## Memory Allocation

- Does the allocation pattern suggest object pooling would help?
- Is there allocation churn (repeated alloc/free cycles)?
- Can stack allocation replace heap allocation for short-lived objects?
- Does the massif profile show sawtooth, staircase, or flat patterns?
- Is peak memory usage within expected bounds for the input size?
- Are there memory leaks (monotonically increasing allocation without corresponding frees)?
- For Python: is tracemalloc peak significantly different from massif peak (indicating C-level allocations)?

---

## Measurement Quality

- Is wall-time CV below 3%?
- Is the CPU governor set to performance?
- Are benchmarks run at multiple input sizes for scaling analysis?
- Is the system under low background load during measurement?
- Are enough warm-up rounds configured to avoid cold-start effects?
- Is Valgrind output filtered to project source files (not scoring interpreter overhead)?
- Are hardware counter results from perf stat consistent with Valgrind simulation?
- Is `perf_event_paranoid` set to <= 1 for hardware counter access?

---

## Optimization Priority

- Are algorithmic issues resolved before pursuing hardware optimizations?
- What is the expected impact (100-1000x algorithmic vs 5-20x data layout vs 2-5x execution)?
- Which optimization gives the best ROI for the current bottleneck?
- Has the baseline been measured before and after each change to confirm improvement?
- Is there a risk of regression in other dimensions (e.g., improving cache at the cost of memory)?
- Are micro-optimizations (Tier 4) being deferred until Tiers 1-3 are clean?
- Is the workload representative of production usage?
