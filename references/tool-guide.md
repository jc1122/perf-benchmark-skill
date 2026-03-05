# Tool Guide

When to use each tool, what it measures, and its limitations.

---

## Tool Reference

### pytest-benchmark

- **What it measures:** Wall-clock execution time with statistical analysis (min, max, mean, stddev, rounds).
- **When to use:** Dimension 1 (wall-time stability). First tool to run for any benchmark.
- **Limitations:** Measures elapsed time only; no insight into why something is slow. Results vary with system load. Set CPU governor to `performance` before measuring.
- **Key output:** Mean, stddev, CV (coefficient of variation), rounds, iterations.

### tracemalloc

- **What it measures:** Python heap allocations (peak and current) at the Python object level.
- **When to use:** Dimension 6 (memory profile). Quick Python-level memory check before reaching for massif.
- **Limitations:** Only tracks Python allocations. Does not see C extension mallocs, numpy backing arrays, or mmap regions. Adds ~5% overhead.

### /usr/bin/time -v

- **What it measures:** Wall time, user/sys CPU time, max RSS, voluntary/involuntary context switches, page faults.
- **When to use:** Quick triage. Useful as a sanity check before deeper analysis.
- **Limitations:** Process-level granularity only. No per-function breakdown. Must use the full path `/usr/bin/time` to avoid the shell built-in.

### valgrind --tool=cachegrind

- **What it measures:** Instruction counts, L1 data/instruction cache misses, last-level cache misses, branch mispredictions. All counts per source line and per function.
- **When to use:** Dimensions 3 (L1 cache), 4 (LL cache), 5 (branch prediction). Also sub-checks 0c and 0d.
- **Limitations:** Simulates a 2-level cache model (L1 + LL). There is no separate L2 simulation. LL in cachegrind maps roughly to L3 on modern hardware. Runs 20-50x slower than native. Does not measure wall time.

### cg_annotate

- **What it measures:** Post-processes cachegrind output into per-function and per-line annotated reports.
- **When to use:** After cachegrind to extract per-file metrics. Use `--include=<dir>` to filter to project source files only.
- **Limitations:** Output can be very large for complex programs. Always filter with `--include` or `--source-prefix`.

### valgrind --tool=callgrind

- **What it measures:** Instruction-level call counts, call graph, per-function instruction cost.
- **When to use:** Dimension 2 (CPU efficiency). Sub-checks 0b (call amplification) and 0f (multiplicative call paths).
- **Limitations:** 20-100x slowdown. Does not measure wall time. Thread support requires `--separate-threads=yes`.

### callgrind_annotate

- **What it measures:** Post-processes callgrind output into per-function cost breakdowns.
- **When to use:** After callgrind to identify top functions by instruction count.
- **Limitations:** Same filtering considerations as cg_annotate.

### valgrind --tool=massif

- **What it measures:** Heap allocation over time as a series of snapshots. Tracks total bytes allocated, allocation sites, and peak usage.
- **When to use:** Dimension 6 (memory profile). Sub-check 0e (allocation churn).
- **Limitations:** Heap only (no stack by default; use `--stacks=yes` for stack, but this is very slow). 10-20x slowdown.

### ms_print

- **What it measures:** Renders massif output as an ASCII allocation-over-time graph with annotated peaks.
- **When to use:** After massif to visualize allocation patterns (flat, staircase, sawtooth).
- **Limitations:** ASCII rendering can be hard to interpret for complex profiles. Parse the massif output file directly for automated scoring.

### perf stat

- **What it measures:** Hardware performance counters: cycles, instructions, IPC, cache misses, branch mispredictions, context switches.
- **When to use:** Dimension 2 (IPC), Dimension 5 (branch misprediction from hardware). Ground truth for hardware counters.
- **Limitations:** Requires `perf_event_paranoid <= 1` (`sysctl kernel.perf_event_paranoid`). Not available in all container environments. Process-level counters by default; per-function requires `perf record` + `perf report`.

### objdump -dS

- **What it measures:** Disassembles binary with interleaved source (if debug info present).
- **When to use:** Tier 4 ASM audit. Checking for SIMD vectorization, branch-free patterns, inlining.
- **Limitations:** Requires `-g` compilation. Output is large; filter to specific functions with `--start-address`/`--stop-address` or pipe through grep.

### Numba inspect_asm()

- **What it measures:** JIT-compiled assembly for a specific Numba function signature.
- **When to use:** Tier 4 ASM audit for Numba-compiled functions. Verifying vectorization and loop optimization.
- **Limitations:** Only works for Numba-decorated functions. Must call the function at least once to trigger compilation before inspecting.

---

## Decision Tree

Use this tree to select the right tool for the current bottleneck hypothesis.

```
START
  |
  +-- Algorithmic bottleneck suspected?
  |     |
  |     YES --> Tier 1: Scaling analysis
  |     |         - Run pytest-benchmark at 2+ input sizes
  |     |         - Fit T(n) = c * n^k
  |     |         - Run callgrind for call amplification
  |     |         - Run cachegrind for data reuse ratio
  |     |
  |     NO --> continue
  |
  +-- Cache bottleneck suspected?
  |     |
  |     YES --> Tier 2: cachegrind
  |     |         - valgrind --tool=cachegrind <program>
  |     |         - cg_annotate --include=src/ cachegrind.out.*
  |     |         - Score per-file, not global
  |     |
  |     NO --> continue
  |
  +-- CPU hotspot suspected?
  |     |
  |     YES --> Tier 2: callgrind
  |     |         - valgrind --tool=callgrind <program>
  |     |         - callgrind_annotate --include=src/ callgrind.out.*
  |     |         - Identify top functions by instruction %
  |     |
  |     NO --> continue
  |
  +-- Memory bottleneck suspected?
  |     |
  |     YES --> Tier 3: massif
  |     |         - valgrind --tool=massif <program>
  |     |         - Parse massif.out.* directly for automated scoring
  |     |         - ms_print massif.out.* for visual inspection
  |     |
  |     NO --> continue
  |
  +-- Hardware counter validation needed?
  |     |
  |     YES --> Tier 3: perf stat
  |     |         - Check: sysctl kernel.perf_event_paranoid <= 1
  |     |         - perf stat -e cycles,instructions,cache-misses,branch-misses <program>
  |     |
  |     NO --> continue
  |
  +-- ASM-level optimization?
        |
        YES --> Tier 4: objdump + asm-checklist
                  - objdump -dS <binary> | less
                  - For Numba: fn.inspect_asm(fn.signatures[0])
                  - Cross-reference with asm-checklist.md
```

---

## Valgrind Noise Isolation

Valgrind instruments the entire process including the Python interpreter, C runtime, and all shared libraries. Raw global numbers are dominated by interpreter overhead and are not useful for scoring project code.

### Filtering to Project Source

1. **Use `--source-prefix`** when running cachegrind/callgrind to tag source directories:
   ```
   valgrind --tool=cachegrind --cache-sim=yes ./program
   ```

2. **Use `cg_annotate --include=src/`** to restrict annotation output to project source files only:
   ```
   cg_annotate --include=src/ cachegrind.out.12345
   ```

3. **Score per-file, not global.** Global miss rates include interpreter and library code. Extract per-file or per-function metrics from the annotated output and score those against the rubric thresholds.

### Valgrind 2-Level Cache Model

Valgrind's cachegrind simulates a simplified 2-level cache hierarchy:
- **L1:** Separate L1 instruction cache (I1) and L1 data cache (D1).
- **LL:** A single "last-level" cache representing everything below L1.

Modern CPUs have 3 levels (L1, L2, L3). Cachegrind has **no separate L2 simulation**. The LL cache in cachegrind output maps roughly to L3 behavior on modern hardware. This means:
- L1 miss rates from cachegrind are reasonably accurate.
- LL miss rates approximate L3 miss rates but skip L2 effects entirely.
- Use `perf stat` hardware counters for precise L2/L3 measurements when the distinction matters.
