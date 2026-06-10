# Performance Remediation Playbook

Execution discipline for acting on perf-benchmark findings. Diagnosis is the pipeline's job;
this playbook is the measure -> change -> re-measure ratchet for fixing what it finds.

## Standing Rules

1. **Algorithmic STOP gate first.** If Algorithmic Scaling is FAIL, no cache/branch/ASM work
   is permitted until the complexity class is fixed. Constants do not beat asymptotics.
2. **One dimension per batch.** Never mix an algorithmic change with a data-layout change in
   one commit; attribution dies.
3. **Measure before, measure after, same environment.** Both runs same tier, same sizes, same
   machine state (governor, SMT, load). The summary's environment fingerprint must match
   between the before/after runs; a fingerprint mismatch voids the comparison.
4. **Acceptance ratchet:** a batch is accepted only if (a) median improves >= 5% on the target
   dimension's metric, (b) wall-time CV stays <= --max-cv in both runs, (c) no other scored
   dimension regresses by >= 1 tier, and (d) the test suite is green. Otherwise discard.
5. **Coverage gate (shared with code-health):** before editing an uncovered file, write
   behavior tests for its contract. Perf wins on untested code are not accepted.
6. **Honest no-win:** if every candidate requires behavior changes, architecture work, or
   yields < 5%, record "evaluated, no feasible low-risk win" with the evidence. That is a
   valid, terminal outcome (cf. SP4 DoD).

## Dimension Procedures

| Dimension | First moves | Verify with |
|---|---|---|
| Algorithmic Scaling | Lower the complexity class: incremental maintenance over recompute; process deltas not history; index/partition/cache lookups; bound per-update work to changed inputs | multi-size re-run; growth curve matches expected class |
| L1 / LLC Cache | Contiguous layouts (arrays-of-scalars over objects), loop blocking/fusion, hot/cold field splitting, smaller working sets | cachegrind miss rates |
| Memory Profile | Kill allocation churn in loops (reuse buffers), generators over materialized lists, slots/dataclass(frozen) for hot objects, cap retained history | massif/tracemalloc peaks |
| CPU Efficiency | Hoist invariants, remove redundant passes/copies, batch syscalls/IO, vectorize (numpy) or JIT (numba) only after the above | callgrind inclusive cost, perf stat IPC |
| Branch Prediction | Sort/partition data to make branches predictable, replace data-dependent branches with arithmetic/lookup, move rare cases out of hot loops | branch-miss rate |
| Wall-Time Stability | Pin governor to performance, isolate from background load, increase repeats; if CV stays > gate, fix the measurement before the code | CV in summary |
| Latency percentiles (p95/p99) | Hunt the tail: GC pauses, lazy init on first hit, lock contention, pathological inputs; fix the tail cause, never average it away | p50/p95/p99 spread in summary |

## Scope Notes (v0.2.0)

- Service-level test types (load, stress, soak, spike, concurrency, capacity — ISTQB CT-PT
  taxonomy; ISO/IEC 25010 'capacity') are OUT OF SCOPE for this skill version: there is no
  closed-loop load driver. Do not simulate them with repeats. Recorded gap; planned SP7.
- Non-Linux hosts and Rust/criterion ingestion: out of scope v0.2.0 (P2).
