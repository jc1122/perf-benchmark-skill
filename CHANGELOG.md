# Changelog

## 0.6.1 - 2026-06-16

Add `bootstrap/install-perf.sh`: deploys both skills this repo provides
(`perf-benchmark` from the repo root, `perf-optimization` from the subdir) into a
destination skills dir. This is the installer the repo-audit family's one-line
self-bootstrap (`repo-audit-refactor-optimize` `bootstrap/install.sh`) invokes for
the perf source. Idempotent; deploys committed content via `git archive`.
Regression test in `tests/test_install_perf.py`.

## 0.6.0 - 2026-06-15

Dogfood gap remediation — Wave C (scope / deploy parity). Closes the cross-repo
pin-coherence gap so a stale runner pin can never silently run an old runner and
pass the wave gate:

- **#8 runner pin-coherence gate.** New `scripts/check_runner_pin.py` +
  `scripts/runner_requirements.json` (`min_version` 0.11.0, capabilities
  `lane-error-gate`/`metric-ceiling`/`lane-timeout`). The gate invokes
  `$WAVE_RUNNER --capabilities`, parses the advertised `{version, capabilities}`,
  and fails (exit 1) when the pinned runner is below the minimum version, is
  missing any required capability, or `WAVE_RUNNER` is unset/unparseable. Pure
  `version_ok` / `missing_caps` helpers are unit-tested. Wired into CI before the
  convergence gate.
- **Runner re-pin v0.9.0 → v0.11.0**, the tag that advertises the required
  capability surface.
- **Leaf re-pin v0.7.5 → v0.8.0** (`repo-audit-skills`), bringing repo-A lane
  parity (perf-smell/hotspot/exec gates) and the standalone-deploy fixes.

## 0.5.0 - 2026-06-15

Dogfood gap remediation — Wave A (trustworthy green). Mirrors the convergence-gate
hardening into perf-benchmark and re-pins the diagnosis-wave runner:

- **#1 errored lane no longer passes the gate.** `check_wave_baseline.py` now reads
  `wave_summary.json` + the runner exit code and fails on any `status:"error"` lane.
- **#3 accept-reason quality gate.** New `check_accept_reasons.py` (with vendored
  stdlib `_accept.py`/`validate_accept.py`) rejects boilerplate reasons; existing
  reasons enriched with their finding identity. Wired into CI.
- **#10 toolchain-drift assertion.** New `scripts/toolchain_pins.json` is the source of
  truth; CI installs from it and `check_toolchain.py` asserts the running env matches.
- **Runner re-pin v0.8.2 → v0.9.0**, bringing the runner-side fixes that reach
  perf-benchmark by pin: #9 per-lane timeout and #2 metric value ceilings.

## 0.4.3 - 2026-06-15

Re-pin the convergence-gate wave runner to `repo-audit-refactor-optimize` v0.8.2, which
scopes the `perf-smell` lane to `--source-prefix`. With the fixed runner, perf-smell no
longer scans `tests/` or `benchmarks/`, so the perf-smell accepts for those paths in
`.repo-audit/accept.json` are stale and have been pruned (3 entries). Surfaced by a
skillset-on-skillset dogfood run.

## 0.4.2 - 2026-06-14

Self-contained convergent family — Phase 1. New `convergence-gate` CI job runs the
Tier-1 deterministic wave against repo-P self-contained and reproducibly: pinned
leaves (`v0.7.2`) + pinned runner (`repo-audit-refactor-optimize` `v0.8.1`), pinned
toolchain, Python 3.14, jscpd via `$GITHUB_PATH`, full git history (`fetch-depth: 0`,
needed by the history-mining hotspot/growth lanes), gated on the real exit code. With
the runner at `v0.8.1` the wave now includes the `perf-smell` lane, so repo-P's own
scripts are perf-smell-audited; findings triaged (genuine fixes applied, perflint
over-approximations justify-accepted in `.repo-audit/accept.json`). Also accepts the
cross-skill jscpd duplication clone (the JSONL-ledger reader shared by
`scripts/perf_benchmark/ledger.py` and `perf-optimization/scripts/verify_win.py`,
which are separate independently-installed skills). Added `tests/test_accept_policy.py`
guarding the acceptance policy, and dropped the stale `wave_baseline.json`
declared-coupling pair.

## 0.4.1 - 2026-06-14

- Re-anchored the convergence wave and fixed two real TYPE findings in source
  (`profile_discover.py` pstats typeshed gap; `synth_microbench.py` ModuleSpec
  None-guard).
- Phase 2 acceptance-safeguard migration: the internal residual baseline now lives in
  `.repo-audit/accept.json` (a `growth-audit` rule accepts expected surface growth);
  `wave_baseline.json` removed. The convergence gate (`check_wave_baseline.py`) now
  trusts the wave's report/accept partition — converged iff the active set is empty and
  no accepted entry is stale.

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
