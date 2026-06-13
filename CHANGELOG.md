# Changelog

## 0.4.0 - 2026-06-14

- Benchmark-synthesis primitives for the `synthesizable` performance lane:
  `scripts/profile_discover.py` (stdlib cProfile hotspot ranking, the fallback
  when `perf`/valgrind are absent) and `scripts/synth_microbench.py` (generate a
  perf-benchmark-shaped harness + `make_input` stub, with a `validate_make_input`
  pre-measurement guard).
- `reporting.build_summary_contract` exposes a stable top-level summary contract
  (`complexity_exponent`, `deterministic_tier`) so consumers gate on it instead of
  reaching into nested rubric internals. Additive; existing keys unchanged.

## 0.3.8 - 2026-06-12

- Split perf benchmark ledger comparison into focused loading, tier, and
  regression helpers while preserving `vs_last`, `vs_best`, and warning output.
- Ratcheted the wave baseline from 32 to 31 normalized identities.

## 0.3.7 - 2026-06-12

- Split perf benchmark CLI argument registration into focused helpers while
  preserving parser options, validation, and public `parse_args(argv)` behavior.
- Ratcheted the wave baseline from 33 to 32 normalized identities after the
  iteration-eight parser split.

## 0.3.6 - 2026-06-12

- Split perf-optimization verdict CLI parsing and checked summary loading into
  focused helpers.
- Ratcheted the wave baseline from 33 to 32 normalized identities.

## 0.3.5 - 2026-06-12

- Split perf-optimization candidate finding validation into focused helpers.
- Split perf-optimization ledger validation into focused loading/comparison
  helpers.
- Ratcheted the wave baseline from 35 to 33 normalized identities.

## 0.3.4 - 2026-06-12

- Split massif parser snapshot and heap-summary handling into focused helpers.
- Ratcheted the wave baseline from 37 to 35 normalized identities.

## 0.3.3 - 2026-06-12

- Split reporting Markdown and JSON summary assembly into focused helpers.
- Ratcheted the wave baseline from 39 to 35 normalized identities.

## 0.3.2 - 2026-06-11

- Split scoring wall-time CV collection into focused helpers.
- Split cache metric collection into file-level, summary-derived, and fallback
  helpers.
- Ratcheted the wave baseline from 41 to 39 normalized identities.

## 0.3.1 - 2026-06-11

- Added counted security trusted-subprocess policy support to the repo wave
  baseline.
- Added hotspot policy config for intentional README/SKILL/pipeline coupling
  and single-maintainer concentration.
- Removed Bandit false positives while preserving deterministic finding IDs.
- Split wall-time summary reporting helpers and ratcheted the wave baseline
  from 55 to 39 normalized identities.
- Updated CI workflow actions to current majors.

## 0.3.0 - 2026-06-11

- Added SP9 self-audit evidence for the perf benchmark repository.
- Seeded the wave convergence baseline and freeze ledger.
- Recorded fast-tier benchmark ledger evidence and an honest no-candidate
  optimization verdict.
- Shortened the agent-facing skill instructions while preserving CLI contracts,
  outputs, tiers, and limits.

## 0.2.0

- Added rubric scoring, findings output, baseline ledger support, and the
  remediation playbook.
