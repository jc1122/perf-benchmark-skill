# Optimization Playbook

Technique catalogue for the `perf-optimization` skill. This playbook supplies
the *what* (technique selection) while `perf-remediation-playbook.md` supplies
the *how* (execution discipline). Identify the rubric dimension from a PERF
finding's `metric.name` (see the metric-to-dimension mapping in
`perf-optimization/SKILL.md`) or from the paired `benchmark_summary.json`
rubric; then apply techniques in the listed order, escalating only when
first-line techniques have been exhausted and re-measured.

PERF findings do **not** carry a raw `dimension` field. The rubric dimension
and tier are inferred from `metric.name` (e.g., `l1_miss_rate` → L1 Cache
Efficiency) and `severity` (`"high"` → FAIL, `"medium"` → WARN).

## Standing Rules

These rules mirror and extend `perf-remediation-playbook.md` for the
optimization execution context. Both playbooks must agree before a change is
applied.

1. **Algorithmic STOP gate first.** If Algorithmic Scaling is FAIL, no
   cache/branch/ASM work is permitted until the complexity class is fixed.
   Constants do not beat asymptotics.
2. **One dimension per batch.** Never mix an algorithmic change with a
   data-layout change in one commit; attribution dies.
3. **Measure before, measure after, same environment.** Both runs same tier,
   same sizes, same machine state (governor, SMT, load). The summary's
   environment fingerprint must match between the before/after runs except
   `timestamp_utc` and `load_avg_1m`; a fingerprint mismatch voids the
   comparison.
4. **Acceptance ratchet (>= 5%).** A batch is accepted only if:
   - p50 median improves >= 5% on the target dimension's metric
   - wall-time CV stays <= max-cv in both runs
   - no other scored dimension regresses by >= 1 tier
   - the test suite is green
5. **Coverage gate (shared with code-health).** Before editing an uncovered
   file, write behavior tests for its contract. Perf wins on untested code
   are not accepted.
6. **Honest no-win.** If every candidate requires behavior changes,
   architecture work, or yields < 5%, record "evaluated, no feasible low-risk
   win" with the evidence. That is a valid, terminal outcome.
7. **Technique order is binding.** Apply first-line techniques in the listed
   order. Escalation techniques only after first-line techniques have been
   measured and found insufficient. Skipping the queue invalidates the
   evidence chain.

## Technique Catalogue

| Diagnostic tier | Dimension / metric | First-line techniques (in order) | Escalation |
|---|---|---|---|
| fast | Algorithmic Scaling (growth curve) | incremental maintenance over recompute; process deltas not history; dict/set lookup over scan; bound per-update work to changed inputs | redesign data flow; precompute indices |
| fast | Wall-time median (p50) | hoist invariants out of loops; kill redundant passes/copies; batch syscalls/IO; early-exit dominant branches | numpy vectorization / numba JIT (only after the above) |
| fast | Tail latency (p95/p99 spread) | find the tail cause: lazy init on first hit, GC pauses, pathological inputs; fix the cause, never average it away | cap input pathology; pre-warm; arena/object reuse |
| deep (cachegrind) | L1/LLC miss rate | contiguous layouts (arrays over object graphs); loop blocking/fusion; hot/cold field splitting; shrink working set | structure-of-arrays rewrite |
| deep (massif/tracemalloc) | heap peak / alloc churn | reuse buffers in loops; generators over materialized lists; `__slots__`/frozen dataclasses for hot objects; cap retained history | streaming redesign |
| deep (callgrind/perf) | CPU inclusive cost / IPC | remove interpreter overhead in hot loops (local variable caching, fewer attribute lookups); fold repeated parsing; memoize pure hot calls | C extension boundary / algorithm change |
| deep (perf) | branch-miss rate | sort/partition data so branches are predictable; replace data-dependent branches with arithmetic or table lookup; move rare cases out of the hot loop | branchless rewrite of the kernel |

## Dimension-Specific Guidance

### Algorithmic Scaling

The highest-priority dimension. A FAIL here gates all other work.

- **Incremental maintenance over recompute:** When the full result is
  recalculated on every update, maintain the result incrementally by applying
  only the delta of changed inputs.
- **Process deltas not history:** Avoid scanning the full retained state on
  each operation; bound per-update work to the size of the change, not the
  size of the accumulated state.
- **Dict/set lookup over scan:** Replace O(n) list scanning with O(1) dict
  or set membership tests in hot paths.
- **Bound per-update work to changed inputs:** If an update touches only k
  of n total elements, the work should be O(k), not O(n).
- **Escalation — redesign data flow:** When incremental maintenance is
  insufficient, restructure the data flow to avoid the complexity class
  entirely (e.g., stream processing instead of batch recomputation).
- **Escalation — precompute indices:** Build lookup indices offline or at
  write time so that queries are O(log n) or O(1).

### Wall-Time Median (p50)

The primary timing metric. First-line techniques target algorithmic
inefficiency within the current implementation before escalating to
vectorization or JIT compilation.

- **Hoist invariants out of loops:** Move computations that do not depend on
  the loop variable above the loop. Applies to attribute lookups, repeated
  function calls with constant arguments, and invariant expressions.
- **Kill redundant passes/copies:** Identify loops or passes that process the
  same data multiple times and merge them. Eliminate intermediate copies
  when a direct transformation is possible.
- **Batch syscalls/IO:** Replace per-item read/write with batched operations.
  Use `readinto`, `writelines`, or buffered IO.
- **Early-exit dominant branches:** If a conditional branch is taken > 90% of
  the time, restructure the code to check that branch first and exit early.

### Tail Latency (p95/p99)

High tail latency is caused by rare but expensive events, not average-case
behavior. Do not average the tail away.

- **Lazy init on first hit:** A common tail cause: the first request triggers
  expensive setup (module imports, connection pools, JIT compilation).
  Pre-warm during startup.
- **GC pauses:** Garbage collection pauses disproportionately affect tail
  latency. Use `gc.disable()` during timing-critical sections, or switch to
  manual memory management for hot paths.
- **Pathological inputs:** Identify specific input patterns that trigger
  worst-case behavior. Add input validation or early rejection.
- **Escalation — cap input pathology:** Reject or bound inputs that trigger
  exponential or quadratic behavior.
- **Escalation — arena/object reuse:** Pool objects instead of allocating
  and freeing them on every request.

### L1 / LLC Miss Rate

Cache misses are measured via cachegrind (simulated) at `deep` tier.

- **Contiguous layouts:** Prefer arrays of scalars (struct-of-arrays) over
  arrays of objects (array-of-structs) when only a subset of fields is
  accessed in a hot loop. This avoids loading unused fields into cache lines.
- **Loop blocking/fusion:** Split large loops into tile-sized blocks that fit
  in cache. Fuse multiple passes over the same data into a single pass.
- **Hot/cold field splitting:** Separate frequently accessed fields
  ("hot") from rarely accessed fields ("cold") into different allocations
  so that cache lines are not wasted on cold data.
- **Shrink working set:** Reduce the size of the data actively accessed in
  the hot loop. Use smaller integer types, compressed representations, or
  streaming access patterns.
- **Escalation — structure-of-arrays rewrite:** Reorganize the entire data
  model from array-of-structs to struct-of-arrays when multiple hot loops
  access different field subsets.

### Heap Peak / Alloc Churn

Measured via massif (heap profile) and tracemalloc (Python alloc tracing).

- **Reuse buffers in loops:** Allocate buffers once outside the loop and
  reuse them. Avoid `list.append` in a loop when the final size is known —
  pre-allocate with `[None] * n` or `array('d', [0]) * n`.
- **Generators over materialized lists:** Use generator expressions or
  `yield` instead of building intermediate lists. This applies especially to
  pipeline stages where one stage produces data consumed by the next.
- **`__slots__` / frozen dataclasses:** For hot objects instantiated
  many times, use `__slots__` to eliminate per-instance `__dict__`
  overhead. Use `@dataclass(frozen=True)` for hashable, reusable instances.
- **Cap retained history:** If the program accumulates all historical data
  in memory, add a retention cap (ring buffer, sliding window, or eviction
  policy).
- **Escalation — streaming redesign:** When allocation churn is inherent to
  the batch processing model, redesign as a streaming pipeline where data
  flows through fixed-size buffers.

### CPU Inclusive Cost / IPC

Measured via callgrind (instruction counts) and `perf stat` (IPC).

- **Remove interpreter overhead:** In hot Python loops, cache global and
  builtin lookups as local variables (e.g., `_len = len` at module level).
  Minimize attribute access chains (`a.b.c.d`) by assigning intermediate
  references to locals.
- **Fold repeated parsing:** If the same string is parsed multiple times,
  parse once and cache the result. Apply to regex compilation, JSON
  deserialization, and format string parsing.
- **Memoize pure hot calls:** For pure functions called repeatedly with the
  same arguments, add an LRU cache (`@functools.lru_cache`) or manual
  memoization dictionary.
- **Escalation — C extension boundary:** When Python interpreter overhead
  dominates, move the hot kernel to a C extension (Cython, ctypes, CFFI) or
  use Numba JIT for numerical kernels.

### Branch-Miss Rate

Measured via `perf stat` branch-miss counter at `deep` tier.

- **Sort/partition for predictability:** If a hot loop iterates over data
  with mixed values that control branching, sort or partition the data first
  so that branches follow a predictable pattern (long runs of the same
  branch direction).
- **Replace data-dependent branches with arithmetic:** Convert `if (x > 0)`
  to branchless arithmetic: `result = (x > 0) * value`. Use bitwise
  operations and conditional moves where the ISA supports them.
- **Table lookup over branching:** Replace a chain of `if/elif/else` with a
  precomputed lookup table (dict, array). The branch predictor is bypassed
  entirely.
- **Move rare cases out of the hot loop:** If a branch is taken < 1% of the
  time, hoist it out of the loop or restructure the loop to handle the rare
  case separately (loop fission).
- **Escalation — branchless rewrite of the kernel:** Rewrite the entire hot
  kernel without data-dependent branches, using arithmetic, bitwise
  operations, and lookup tables exclusively.

## Escalation Protocol

Escalation techniques carry higher risk (larger blast radius, behavioral
changes, or architectural restructuring). Before escalating:

1. **Exhaust first-line techniques.** All first-line techniques for the
   dimension must have been applied and measured. Document which were tried
   and what effect each had.
2. **Confirm the bottleneck persists.** Re-run `perf-benchmark` at the same
   tier to confirm the dimension is still FAIL or WARN after first-line
   changes.
3. **Assess blast radius.** Escalation techniques often span multiple files
   or modules. Estimate the number of affected files and dependent tests.
4. **Increase verification rigor.** Escalation changes require the full
   acceptance ratchet (>= 5% win, fingerprint match, no regression, suite
   green) plus manual review of the changed code paths.

## Cross-References

- **`../references/perf-remediation-playbook.md`** (in the `perf-benchmark`
  skill): The execution discipline. Supplies the standing rules, dimension
  verification procedures, and the measure → change → re-measure ratchet.
  This playbook extends that one with technique-level detail.
- **`../SKILL.md`** (the `perf-optimization` skill): The 5-stage pipeline
  workflow that drives technique selection and verification.
- **`../references/finding-schema.json`**: The PERF findings schema consumed
  as input. The rubric dimension for each finding is inferred from
  `metric.name` (see the metric-to-dimension table in
  `perf-optimization/SKILL.md`) and cross-referenced with the
  `benchmark_summary.json` rubric; there is no raw `dimension` field on
  findings.
