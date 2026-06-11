# complexity-audit report

## Precision counters
- entrypoint_mi_relaxed: 4

## DECOMPOSE (32)
- `perf-optimization/scripts/select_candidate.py:50` _validate_finding — cyclomatic_complexity=12 (>10) [medium]
- `perf-optimization/scripts/verify_win.py:132` _read_ledger — cyclomatic_complexity=13 (>10) [medium]
- `perf-optimization/scripts/verify_win.py:248` main — function_nloc=51 (>50) [medium]
- `scripts/check_wave_baseline.py:21` main — function_nloc=70 (>50) [medium]
- `scripts/perf_benchmark/ledger.py:50` compare — cyclomatic_complexity=11 (>10) [medium]
- `scripts/perf_benchmark/reporting.py:67` _summarize_wall_time_metrics — cyclomatic_complexity=22 (>10) [high]
- `scripts/perf_benchmark/reporting.py:67` _summarize_wall_time_metrics — function_nloc=56 (>50) [medium]
- `scripts/perf_benchmark/reporting.py:128` write_markdown_report — cyclomatic_complexity=38 (>10) [high]
- `scripts/perf_benchmark/reporting.py:128` write_markdown_report — function_nloc=215 (>50) [medium]
- `scripts/perf_benchmark/reporting.py:355` write_json_summary — cyclomatic_complexity=17 (>10) [medium]
- `scripts/perf_benchmark/reporting.py:355` write_json_summary — function_nloc=62 (>50) [medium]
- `scripts/perf_benchmark/scoring.py:34` _fit_exponent — cyclomatic_complexity=12 (>10) [medium]
- `scripts/perf_benchmark/scoring.py:55` score_algorithmic_scaling — cyclomatic_complexity=64 (>10) [high]
- `scripts/perf_benchmark/scoring.py:55` score_algorithmic_scaling — function_nloc=130 (>50) [medium]
- `scripts/perf_benchmark/scoring.py:197` score_wall_time_stability — cyclomatic_complexity=23 (>10) [high]
- `scripts/perf_benchmark/scoring.py:244` score_cpu_efficiency — cyclomatic_complexity=16 (>10) [medium]
- `scripts/perf_benchmark/scoring.py:284` score_cache_dim — cyclomatic_complexity=17 (>10) [medium]
- `scripts/perf_benchmark/scoring.py:314` score_memory_profile — cyclomatic_complexity=17 (>10) [medium]
- `scripts/perf_benchmark/stage_helpers.py:57` _generate_tracemalloc_wrapper — function_nloc=70 (>50) [medium]
- `scripts/perf_benchmark/stage_helpers.py:150` _parse_cachegrind_summary — cyclomatic_complexity=21 (>10) [high]
- `scripts/perf_benchmark/stage_helpers.py:253` _parse_massif_out — cyclomatic_complexity=18 (>10) [medium]
- `scripts/perf_benchmark/stage_helpers.py:253` _parse_massif_out — function_nloc=51 (>50) [medium]
- `scripts/perf_benchmark/stage_helpers.py:313` _parse_perf_stat — cyclomatic_complexity=12 (>10) [medium]
- `scripts/perf_benchmark/stage_helpers.py:367` _discover_objdump_targets — cyclomatic_complexity=11 (>10) [medium]
- `scripts/perf_benchmark/support.py:60` detect_cache_topology — cyclomatic_complexity=16 (>10) [medium]
- `scripts/perf_benchmark_pipeline.py:155` stage_tier1 — cyclomatic_complexity=22 (>10) [high]
- `scripts/perf_benchmark_pipeline.py:155` stage_tier1 — function_nloc=103 (>50) [medium]
- `scripts/perf_benchmark_pipeline.py:452` stage_perf_record — function_nloc=63 (>50) [medium]
- `scripts/perf_benchmark_pipeline.py:583` run_parallel_tiers — cyclomatic_complexity=12 (>10) [medium]
- `scripts/perf_benchmark_pipeline.py:659` parse_args — function_nloc=78 (>50) [medium]
- `scripts/perf_benchmark_pipeline.py:740` main — cyclomatic_complexity=14 (>10) [medium]
- `scripts/perf_benchmark_pipeline.py:740` main — function_nloc=55 (>50) [medium]

## SIMPLIFY (8)
- `scripts/perf_benchmark/findings.py:1` <module> — maintainability_index=56.3323 (>65) [low]
- `scripts/perf_benchmark/reporting.py:1` <module> — maintainability_index=22.139 (>65) [medium]
- `scripts/perf_benchmark/reporting.py:128` write_markdown_report — parameter_count=6 (>5) [low]
- `scripts/perf_benchmark/reporting.py:355` write_json_summary — parameter_count=7 (>5) [low]
- `scripts/perf_benchmark/scoring.py:1` <module> — maintainability_index=0 (>65) [medium]
- `scripts/perf_benchmark/stage_helpers.py:1` <module> — maintainability_index=13.5895 (>65) [medium]
- `scripts/perf_benchmark/support.py:1` <module> — maintainability_index=24.6772 (>65) [medium]
- `scripts/perf_benchmark_pipeline.py:642` write_json_summary — parameter_count=6 (>5) [low]

