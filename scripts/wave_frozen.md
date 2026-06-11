# SP9 Wave Freeze Log

## Seed

- Seed timestamp: 2026-06-11T12:31:45Z
- Source HEAD: `290cbbc49313e4df1377653dee0c5c13816a91ef`

## Command evidence

| Command | Observed result |
| --- | --- |
| `WAVE_RUNNER=/home/jakub/projects/repo-audit-refactor-optimize/scripts/run_diagnosis_wave.py SKILLS_ROOT=~/.claude/skills python3 scripts/check_wave_baseline.py` | Baseline check executed with the seeded hidden wave output; checker compares normalized finding identities and ignores the runner process status. |
| Wave summary | code-health exit `2`/status `error`/findings `44`; security exit `1`/status `findings`/findings `24`; docs exit `0`/status `ok`/findings `0`; hotspot exit `1`/status `findings`/findings `6`; dependency exit `0`/status `ok`/findings `0`; hygiene exit `0`/status `ok`/findings `0`. |
| Snapshot provenance | Findings snapshot collected in the ignored wave output directory from the same runner with prefixes `scripts` and `perf-optimization/scripts`. |

## T5 shrink-only ratchet

- Ratchet timestamp: 2026-06-11T12:40:49Z
- Removed stale identity: `docs-consistency|references/sample-report.md|tests/benchmarks/test_benchmark_graph.py|doc_path_missing`.
- Removed stale identity: `hotspot|SKILL.md|SKILL.md|churn_complexity_product`.
- Current baseline has 74 raw findings and 59 normalized identities.

## SP10 v0.5.1 ratchet

- Ratchet timestamp: 2026-06-11T15:47:00Z
- Removed stale CLI module-MI identities after running with `SKILLS_ROOT=/home/jakub/projects/repo-audit-skills/skills` at v0.5.1.
- Removed stale identities: `perf-optimization/scripts/select_candidate.py`, `perf-optimization/scripts/verify_win.py`, `scripts/check_wave_baseline.py`, and `scripts/perf_benchmark_pipeline.py` module-level `maintainability_index`.
- Current baseline has 67 raw findings and 55 normalized identities.

## SP11 iteration 2 policy/security ratchet

- Ratchet timestamp: 2026-06-11T23:55:00Z
- Added `scripts/security_audit_config.json` to count trusted subprocess rows
  under the security leaf's `trusted_subprocess` policy.
- Added `scripts/hotspot_audit_config.json` and pinned the hotspot window with
  `scripts/wave_anchor.txt` at
  `ac896751703cba56bbbd99e201c1f355c5238567`.
- Rewrote `TIER_RANK` maps to keep the `PASS` tier behind a named constant,
  removing three Bandit B105 false-positive rows without changing tier values.
- Kept deterministic PERF finding IDs stable while marking SHA-1 as
  non-security use via `usedforsecurity=False`, removing the B324 row.
- Refactored `scripts/check_wave_baseline.py` command construction, removing
  its stale `main` `function_nloc` complexity identity after the config wiring.
- Removed stale normalized identities: 9 security identities, 4 hotspot policy
  identities, and 1 checker complexity identity.
- Current baseline has 41 raw findings and 41 normalized identities.

## SP11 iteration 2 reporting complexity ratchet

- Ratchet timestamp: 2026-06-11T21:48:00Z
- Split `_summarize_wall_time_metrics` into focused helpers for pytest
  benchmark metrics, per-size timings, and flat timing lists.
- Removed the stale `_summarize_wall_time_metrics` `cyclomatic_complexity` and
  `function_nloc` identities.
- Current baseline has 39 raw findings and 39 normalized identities.

## Residual findings

The machine-readable authority is `scripts/wave_baseline.json`. The residual
baseline now contains only structural code-health debt and the two real
churn-complexity hotspot rows that must be reduced by future complexity work or
honestly recorded as residue if no bounded win remains.

| Leaf | Count | Class | Residue |
| --- | ---: | --- | --- |
| complexity | 37 | deferred-structural | Function complexity, function length, module maintainability, and parameter-count rows across the perf benchmark pipeline, reporting, scoring, ledger, support, stage helpers, and perf-optimization helpers. |
| hotspot | 2 | deferred-structural | `scripts/perf_benchmark/reporting.py` and `scripts/perf_benchmark_pipeline.py` still carry `churn_complexity_product`; policy config deliberately does not suppress churn-complexity rows. |
