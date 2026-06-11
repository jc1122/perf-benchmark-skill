# Tool Guide

Use the cheapest tool that can answer the current bottleneck question, then
escalate only when evidence remains ambiguous.

## Tools

| Tool | Measures | Use For | Limits |
| --- | --- | --- | --- |
| `pytest-benchmark` | wall time stats | stability, scaling | no causal detail; load-sensitive |
| `tracemalloc` | Python heap | quick memory profile | misses native/C allocations |
| `/usr/bin/time -v` | process time/RSS | sanity check | process-level only |
| `cachegrind` | instruction/cache/branch simulation | L1, LL, branch, reuse | 20-50x slowdown; simulated cache |
| `cg_annotate` | cachegrind attribution | per-file/per-function metrics | filter with `--include` |
| `callgrind` | call graph and instruction cost | CPU efficiency, call amplification | 20-100x slowdown |
| `callgrind_annotate` | callgrind attribution | hot functions | large output; filter source |
| `massif` | heap over time | peak/churn profile | heap only; slow |
| `ms_print` | massif rendering | visual allocation shape | parse raw massif for automation |
| `perf stat` | hardware counters | IPC, cache/branch misses | needs `perf_event_paranoid <= 1` |
| `perf record` | sampled native hotspots | realistic hotspot confirmation | opt-in; symbols improve value |
| `perf report --stdio` | sampled hotspot summary | parse/inspect `perf.data` | version-dependent output |
| `objdump -dS` | assembly with source | SIMD, branches, inlining | requires symbols/debug info |
| Numba `inspect_asm()` | JIT assembly | Numba loop inspection | compile once before inspection |

## Selection

1. Scaling suspicion: run multi-size Tier 1, then callgrind/cachegrind for
   call amplification, reuse, write amplification, and multiplicative paths.
2. Cache suspicion: run cachegrind and score project files, not interpreter
   totals.
3. CPU hotspot suspicion: run callgrind, then confirm with `perf record` when
   hardware sampling is available.
4. Memory suspicion: start with tracemalloc; use massif for native heap and
   churn shape.
5. Hardware-counter validation: use `perf stat`.
6. ASM-level suspicion: use objdump or Numba ASM after higher-level evidence.

## Isolation Rules

- Always filter profiler output to project source with `--source-prefix`,
  `cg_annotate --include`, or `callgrind_annotate --include`.
- Treat global Valgrind rates from Python processes as interpreter-heavy noise.
- Use `--max-cv` to refuse unstable timing instead of scoring it.
- Keep tier, sizes, target, machine, and environment stable for comparisons.
- Cachegrind has no separate L2 model; use hardware counters when L2/L3
  distinction matters.
