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

## SP11 iteration 2 C-6 hotspot re-anchor

- Ratchet timestamp: 2026-06-11T22:18:00Z
- Advanced `scripts/wave_anchor.txt` to
  `b5ed162ef4224340a7776e913321c38ec38bcf90`.
- Added the ratchet ledger pair
  `scripts/wave_baseline.json<->scripts/wave_frozen.md` to
  `scripts/hotspot_audit_config.json`; the hotspot leaf counts the suppression
  under `declared_coupling`.
- Re-anchor surfaced two loop-induced churn rows:
  `scripts/perf_benchmark/scoring.py` from accepted security/constant work and
  `scripts/wave_baseline.json` from repeated ratchets. Per SP11 pre-flight rule
  5, both are recorded as real re-anchor residue for the next iteration rather
  than hidden or treated as unfixable growth.
- Current baseline has 41 raw findings and 41 normalized identities.

## SP11 iteration 3 scoring wall-time ratchet

- Ratchet timestamp: 2026-06-11T23:12:56Z
- Split wall-time CV collection in `scripts/perf_benchmark/scoring.py` into
  private helpers for pytest-benchmark, explicit per-size timings, and flat
  timing lists while preserving the public `score_wall_time_stability` result
  shape.
- Removed the stale `score_wall_time_stability` `cyclomatic_complexity`
  identity.
- Current baseline has 40 raw findings and 40 normalized identities.

## SP11 iteration 3 scoring cache ratchet

- Ratchet timestamp: 2026-06-11T23:14:43Z
- Split cache metric collection in `scripts/perf_benchmark/scoring.py` into
  private helpers for file-level metrics, summary-derived metrics, and fallback
  source selection while preserving `score_cache_dim` thresholds and result
  shape.
- Removed the stale `score_cache_dim` `cyclomatic_complexity` identity.
- Current baseline has 39 raw findings and 39 normalized identities.

## SP11 iteration 3 C-6 hotspot re-anchor

- Ratchet timestamp: 2026-06-11T23:56:27Z
- Advanced `scripts/wave_anchor.txt` to
  `d97f087b418b2cb9798eee4d7ace0d47d1848115`.
- Re-running the wave after re-anchor produced no new or stale normalized
  identities.
- Current baseline remains 39 raw findings and 39 normalized identities.

## SP11 iteration 4 reporting markdown ratchet

- Ratchet timestamp: 2026-06-12T02:43:00Z
- Split `write_markdown_report` in `scripts/perf_benchmark/reporting.py` into
  focused section renderers for prerequisites, algorithmic analysis, baseline
  comparison, scorecard, findings, native hotspots, prescriptions, and cache
  model output while preserving the generated Markdown surface.
- Removed stale `write_markdown_report` `cyclomatic_complexity` and
  `function_nloc` identities.
- Current baseline has 37 raw findings and 37 normalized identities.

## SP11 iteration 4 reporting JSON ratchet

- Ratchet timestamp: 2026-06-12T02:49:00Z
- Split `write_json_summary` in `scripts/perf_benchmark/reporting.py` into
  helpers for the base summary payload, wall-time percentile samples, memory
  peaks, and perf-record summaries while preserving the summary JSON contract.
- Removed stale `write_json_summary` `cyclomatic_complexity` and
  `function_nloc` identities.
- Current baseline has 35 raw findings and 35 normalized identities.

## SP11 iteration 4 C-6 hotspot re-anchor

- Ratchet timestamp: 2026-06-12T01:33:45Z
- Advanced `scripts/wave_anchor.txt` to
  `69ee41a604f8aa7924f30531e23c94f5673d63ee`.
- Re-anchor surfaced two loop-induced churn rows: `SKILL.md` from the
  iteration 4 release-version bump and `scripts/wave_frozen.md` from repeated
  ratchet evidence updates.
- Per SP11 pre-flight rule 5, both rows are recorded as real re-anchor residue
  for a future iteration rather than hidden or treated as unfixable growth.
- Current baseline has 37 raw findings and 37 normalized identities.

## SP11 iteration 5 massif parser ratchet

- Ratchet timestamp: 2026-06-12T02:22:24Z
- Split `_parse_massif_out` in `scripts/perf_benchmark/stage_helpers.py` into
  helpers for snapshot accumulation, allocation-site parsing, and heap-series
  summary calculation while preserving the parsed massif payload shape.
- Removed stale `_parse_massif_out` `cyclomatic_complexity` and
  `function_nloc` identities.
- Current baseline has 35 raw findings and 35 normalized identities.

## SP11 iteration 5 C-6 hotspot re-anchor

- Ratchet timestamp: 2026-06-12T02:51:38Z
- Advanced `scripts/wave_anchor.txt` to
  `836d1153ce85f228d997ec2078da553efccc80b3`.
- Re-anchor surfaced the release documentation pair `CHANGELOG.md<->SKILL.md`.
  Added that pair to `scripts/hotspot_audit_config.json`; the hotspot leaf
  counts it under `declared_coupling` rather than hiding it.
- Re-running the wave after the counted policy update produced no new or stale
  normalized identities.
- Current baseline remains 35 raw findings and 35 normalized identities.

## SP11 iteration 6 perf-optimization candidate validation ratchet

- Ratchet timestamp: 2026-06-12T03:43:50Z
- Split `_validate_finding` in `perf-optimization/scripts/select_candidate.py`
  into focused required-key and field-type helpers while preserving the
  malformed-finding error contract.
- Removed the stale `_validate_finding` `cyclomatic_complexity` identity.
- Current baseline has 34 raw findings and 34 normalized identities.

## SP11 iteration 6 perf-optimization ledger validation ratchet

- Ratchet timestamp: 2026-06-12T03:45:44Z
- Split `_read_ledger` in `perf-optimization/scripts/verify_win.py` into
  ledger-entry loading and regression-comparison helpers while preserving the
  verdict `vs_last` and warning contract.
- Removed the stale `_read_ledger` `cyclomatic_complexity` identity.
- Current baseline has 33 raw findings and 33 normalized identities.

## Residual findings

The machine-readable authority is `scripts/wave_baseline.json`. The residual
baseline now contains only structural code-health debt and the six real
churn-complexity hotspot rows that must be reduced by future complexity work or
honestly recorded as residue if no bounded win remains.

| Leaf | Count | Class | Residue |
| --- | ---: | --- | --- |
| complexity | 27 | deferred-structural | Function complexity, function length, module maintainability, and parameter-count rows across the perf benchmark pipeline, reporting, scoring, ledger, support, stage helpers, and perf-optimization helpers. |
| hotspot | 6 | deferred-structural / loop-reanchor-residue | `scripts/perf_benchmark/reporting.py`, `scripts/perf_benchmark/scoring.py`, `scripts/perf_benchmark_pipeline.py`, `scripts/wave_baseline.json`, `SKILL.md`, and `scripts/wave_frozen.md` still carry `churn_complexity_product`; policy config deliberately does not suppress churn-complexity rows. |
