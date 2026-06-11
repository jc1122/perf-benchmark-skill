# code-health-audit-pipeline report — ADVISE

## DECOMPOSE (32)
- `scripts/perf_benchmark/reporting.py:67` _summarize_wall_time_metrics [high/complexity] — Split _summarize_wall_time_metrics() — complexity 22 exceeds 10
- `scripts/perf_benchmark/reporting.py:128` write_markdown_report [high/complexity] — Split write_markdown_report() — complexity 38 exceeds 10
- `scripts/perf_benchmark/scoring.py:55` score_algorithmic_scaling [high/complexity] — Split score_algorithmic_scaling() — complexity 64 exceeds 10
- `scripts/perf_benchmark/scoring.py:197` score_wall_time_stability [high/complexity] — Split score_wall_time_stability() — complexity 23 exceeds 10
- `scripts/perf_benchmark/stage_helpers.py:150` _parse_cachegrind_summary [high/complexity] — Split _parse_cachegrind_summary() — complexity 21 exceeds 10
- `scripts/perf_benchmark_pipeline.py:155` stage_tier1 [high/complexity] — Split stage_tier1() — complexity 22 exceeds 10
- `perf-optimization/scripts/select_candidate.py:50` _validate_finding [medium/complexity] — Split _validate_finding() — complexity 12 exceeds 10
- `perf-optimization/scripts/verify_win.py:132` _read_ledger [medium/complexity] — Split _read_ledger() — complexity 13 exceeds 10
- `perf-optimization/scripts/verify_win.py:248` main [medium/complexity] — Shorten main() — 51 lines exceeds 50
- `scripts/check_wave_baseline.py:21` main [medium/complexity] — Shorten main() — 70 lines exceeds 50
- `scripts/perf_benchmark/ledger.py:50` compare [medium/complexity] — Split compare() — complexity 11 exceeds 10
- `scripts/perf_benchmark/reporting.py:67` _summarize_wall_time_metrics [medium/complexity] — Shorten _summarize_wall_time_metrics() — 56 lines exceeds 50
- `scripts/perf_benchmark/reporting.py:128` write_markdown_report [medium/complexity] — Shorten write_markdown_report() — 215 lines exceeds 50
- `scripts/perf_benchmark/reporting.py:355` write_json_summary [medium/complexity] — Split write_json_summary() — complexity 17 exceeds 10
- `scripts/perf_benchmark/reporting.py:355` write_json_summary [medium/complexity] — Shorten write_json_summary() — 62 lines exceeds 50
- `scripts/perf_benchmark/scoring.py:34` _fit_exponent [medium/complexity] — Split _fit_exponent() — complexity 12 exceeds 10
- `scripts/perf_benchmark/scoring.py:55` score_algorithmic_scaling [medium/complexity] — Shorten score_algorithmic_scaling() — 130 lines exceeds 50
- `scripts/perf_benchmark/scoring.py:244` score_cpu_efficiency [medium/complexity] — Split score_cpu_efficiency() — complexity 16 exceeds 10
- `scripts/perf_benchmark/scoring.py:284` score_cache_dim [medium/complexity] — Split score_cache_dim() — complexity 17 exceeds 10
- `scripts/perf_benchmark/scoring.py:314` score_memory_profile [medium/complexity] — Split score_memory_profile() — complexity 17 exceeds 10
- `scripts/perf_benchmark/stage_helpers.py:57` _generate_tracemalloc_wrapper [medium/complexity] — Shorten _generate_tracemalloc_wrapper() — 70 lines exceeds 50
- `scripts/perf_benchmark/stage_helpers.py:253` _parse_massif_out [medium/complexity] — Split _parse_massif_out() — complexity 18 exceeds 10
- `scripts/perf_benchmark/stage_helpers.py:253` _parse_massif_out [medium/complexity] — Shorten _parse_massif_out() — 51 lines exceeds 50
- `scripts/perf_benchmark/stage_helpers.py:313` _parse_perf_stat [medium/complexity] — Split _parse_perf_stat() — complexity 12 exceeds 10
- `scripts/perf_benchmark/stage_helpers.py:367` _discover_objdump_targets [medium/complexity] — Split _discover_objdump_targets() — complexity 11 exceeds 10
- `scripts/perf_benchmark/support.py:60` detect_cache_topology [medium/complexity] — Split detect_cache_topology() — complexity 16 exceeds 10
- `scripts/perf_benchmark_pipeline.py:155` stage_tier1 [medium/complexity] — Shorten stage_tier1() — 103 lines exceeds 50
- `scripts/perf_benchmark_pipeline.py:452` stage_perf_record [medium/complexity] — Shorten stage_perf_record() — 63 lines exceeds 50
- `scripts/perf_benchmark_pipeline.py:583` run_parallel_tiers [medium/complexity] — Split run_parallel_tiers() — complexity 12 exceeds 10
- `scripts/perf_benchmark_pipeline.py:659` parse_args [medium/complexity] — Shorten parse_args() — 78 lines exceeds 50
- `scripts/perf_benchmark_pipeline.py:740` main [medium/complexity] — Split main() — complexity 14 exceeds 10
- `scripts/perf_benchmark_pipeline.py:740` main [medium/complexity] — Shorten main() — 55 lines exceeds 50

## SIMPLIFY (8)
- `scripts/perf_benchmark/reporting.py:1` <module> [medium/complexity] — Improve maintainability of scripts/perf_benchmark/reporting.py — MI 22.1 below 65
- `scripts/perf_benchmark/scoring.py:1` <module> [medium/complexity] — Improve maintainability of scripts/perf_benchmark/scoring.py — MI 0.0 below 65
- `scripts/perf_benchmark/stage_helpers.py:1` <module> [medium/complexity] — Improve maintainability of scripts/perf_benchmark/stage_helpers.py — MI 13.6 below 65
- `scripts/perf_benchmark/support.py:1` <module> [medium/complexity] — Improve maintainability of scripts/perf_benchmark/support.py — MI 24.7 below 65
- `scripts/perf_benchmark/findings.py:1` <module> [low/complexity] — Improve maintainability of scripts/perf_benchmark/findings.py — MI 56.3 below 65
- `scripts/perf_benchmark/reporting.py:128` write_markdown_report [low/complexity] — Reduce parameters of write_markdown_report() — 6 exceeds 5
- `scripts/perf_benchmark/reporting.py:355` write_json_summary [low/complexity] — Reduce parameters of write_json_summary() — 7 exceeds 5
- `scripts/perf_benchmark_pipeline.py:642` write_json_summary [low/complexity] — Reduce parameters of write_json_summary() — 6 exceeds 5

