# code-health-audit-pipeline report — GATE

## DECOMPOSE (30)
- `scripts/perf_benchmark/reporting.py:62` _summarize_wall_time_metrics [high/complexity] — Split _summarize_wall_time_metrics() — complexity 24 exceeds 10
- `scripts/perf_benchmark/reporting.py:126` write_markdown_report [high/complexity] — Split write_markdown_report() — complexity 38 exceeds 10
- `scripts/perf_benchmark/scoring.py:55` score_algorithmic_scaling [high/complexity] — Split score_algorithmic_scaling() — complexity 64 exceeds 10
- `scripts/perf_benchmark/scoring.py:192` score_wall_time_stability [high/complexity] — Split score_wall_time_stability() — complexity 23 exceeds 10
- `scripts/perf_benchmark/stage_helpers.py:150` _parse_cachegrind_summary [high/complexity] — Split _parse_cachegrind_summary() — complexity 22 exceeds 10
- `scripts/perf_benchmark_pipeline.py:99` stage_tier1 [high/complexity] — Split stage_tier1() — complexity 22 exceeds 10
- `perf-optimization/scripts/select_candidate.py:50` _validate_finding [medium/complexity] — Split _validate_finding() — complexity 12 exceeds 10
- `perf-optimization/scripts/verify_win.py:134` _read_ledger [medium/complexity] — Split _read_ledger() — complexity 13 exceeds 10
- `scripts/perf_benchmark/ledger.py:50` compare [medium/complexity] — Split compare() — complexity 11 exceeds 10
- `scripts/perf_benchmark/reporting.py:62` _summarize_wall_time_metrics [medium/complexity] — Shorten _summarize_wall_time_metrics() — 59 lines exceeds 50
- `scripts/perf_benchmark/reporting.py:126` write_markdown_report [medium/complexity] — Shorten write_markdown_report() — 215 lines exceeds 50
- `scripts/perf_benchmark/reporting.py:353` write_json_summary [medium/complexity] — Split write_json_summary() — complexity 17 exceeds 10
- `scripts/perf_benchmark/reporting.py:353` write_json_summary [medium/complexity] — Shorten write_json_summary() — 62 lines exceeds 50
- `scripts/perf_benchmark/scoring.py:34` _fit_exponent [medium/complexity] — Split _fit_exponent() — complexity 12 exceeds 10
- `scripts/perf_benchmark/scoring.py:55` score_algorithmic_scaling [medium/complexity] — Shorten score_algorithmic_scaling() — 125 lines exceeds 50
- `scripts/perf_benchmark/scoring.py:239` score_cpu_efficiency [medium/complexity] — Split score_cpu_efficiency() — complexity 16 exceeds 10
- `scripts/perf_benchmark/scoring.py:279` score_cache_dim [medium/complexity] — Split score_cache_dim() — complexity 17 exceeds 10
- `scripts/perf_benchmark/scoring.py:309` score_memory_profile [medium/complexity] — Split score_memory_profile() — complexity 17 exceeds 10
- `scripts/perf_benchmark/stage_helpers.py:56` _generate_tracemalloc_wrapper [medium/complexity] — Shorten _generate_tracemalloc_wrapper() — 71 lines exceeds 50
- `scripts/perf_benchmark/stage_helpers.py:255` _parse_massif_out [medium/complexity] — Split _parse_massif_out() — complexity 18 exceeds 10
- `scripts/perf_benchmark/stage_helpers.py:255` _parse_massif_out [medium/complexity] — Shorten _parse_massif_out() — 51 lines exceeds 50
- `scripts/perf_benchmark/stage_helpers.py:315` _parse_perf_stat [medium/complexity] — Split _parse_perf_stat() — complexity 13 exceeds 10
- `scripts/perf_benchmark/stage_helpers.py:371` _discover_objdump_targets [medium/complexity] — Split _discover_objdump_targets() — complexity 11 exceeds 10
- `scripts/perf_benchmark/support.py:59` detect_cache_topology [medium/complexity] — Split detect_cache_topology() — complexity 16 exceeds 10
- `scripts/perf_benchmark_pipeline.py:99` stage_tier1 [medium/complexity] — Shorten stage_tier1() — 103 lines exceeds 50
- `scripts/perf_benchmark_pipeline.py:421` stage_perf_record [medium/complexity] — Shorten stage_perf_record() — 75 lines exceeds 50
- `scripts/perf_benchmark_pipeline.py:566` run_parallel_tiers [medium/complexity] — Split run_parallel_tiers() — complexity 12 exceeds 10
- `scripts/perf_benchmark_pipeline.py:642` parse_args [medium/complexity] — Shorten parse_args() — 78 lines exceeds 50
- `scripts/perf_benchmark_pipeline.py:723` main [medium/complexity] — Split main() — complexity 14 exceeds 10
- `scripts/perf_benchmark_pipeline.py:723` main [medium/complexity] — Shorten main() — 55 lines exceeds 50

## FORMAT (2)
- `perf-optimization/scripts/select_candidate.py:1` perf-optimization/scripts/select_candidate.py [low/quality] — Run the formatter on perf-optimization/scripts/select_candidate.py
- `perf-optimization/scripts/verify_win.py:1` perf-optimization/scripts/verify_win.py [low/quality] — Run the formatter on perf-optimization/scripts/verify_win.py

## LINT (18)
- `perf-optimization/scripts/verify_win.py:214` E501@214:101 [medium/quality] — Line too long (101 > 100)
- `perf-optimization/scripts/verify_win.py:252` E501@252:101 [medium/quality] — Line too long (102 > 100)
- `perf-optimization/scripts/verify_win.py:255` E501@255:101 [medium/quality] — Line too long (107 > 100)
- `perf-optimization/scripts/verify_win.py:256` E501@256:101 [medium/quality] — Line too long (101 > 100)
- `perf-optimization/scripts/verify_win.py:265` E501@265:101 [medium/quality] — Line too long (147 > 100)
- `perf-optimization/scripts/verify_win.py:275` E501@275:101 [medium/quality] — Line too long (146 > 100)
- `scripts/perf_benchmark/reporting.py:392` B007@392:13 [medium/quality] — Loop control variable `size` not used within loop body
- `scripts/perf_benchmark/scoring.py:38` B905@38:42 [medium/quality] — `zip()` without an explicit `strict=` parameter
- `scripts/perf_benchmark/scoring.py:46` B905@46:36 [medium/quality] — `zip()` without an explicit `strict=` parameter
- `scripts/perf_benchmark/scoring.py:106` SIM102@106:5 [medium/quality] — Use a single `if` statement instead of nested `if` statements
- `scripts/perf_benchmark/stage_helpers.py:125` SIM115@125:11 [medium/quality] — Use a context manager for opening files
- `scripts/perf_benchmark/stage_helpers.py:172` B905@172:34 [medium/quality] — `zip()` without an explicit `strict=` parameter
- `scripts/perf_benchmark/stage_helpers.py:187` B905@187:30 [medium/quality] — `zip()` without an explicit `strict=` parameter
- `scripts/perf_benchmark/stage_helpers.py:188` SIM105@188:13 [medium/quality] — Use `contextlib.suppress(ValueError)` instead of `try`-`except`-`pass`
- `scripts/perf_benchmark/stage_helpers.py:324` SIM105@324:9 [medium/quality] — Use `contextlib.suppress(ValueError)` instead of `try`-`except`-`pass`
- `scripts/perf_benchmark/support.py:116` SIM105@116:5 [medium/quality] — Use `contextlib.suppress(ValueError, OSError)` instead of `try`-`except`-`pass`
- `scripts/perf_benchmark/support.py:126` SIM105@126:5 [medium/quality] — Use `contextlib.suppress(ValueError, OSError)` instead of `try`-`except`-`pass`
- `scripts/perf_benchmark/support.py:136` SIM105@136:5 [medium/quality] — Use `contextlib.suppress(ValueError, OSError)` instead of `try`-`except`-`pass`

## SIMPLIFY (11)
- `scripts/perf_benchmark/reporting.py:1` <module> [medium/complexity] — Improve maintainability of scripts/perf_benchmark/reporting.py — MI 22.3 below 65
- `scripts/perf_benchmark/scoring.py:1` <module> [medium/complexity] — Improve maintainability of scripts/perf_benchmark/scoring.py — MI 0.0 below 65
- `scripts/perf_benchmark/stage_helpers.py:1` <module> [medium/complexity] — Improve maintainability of scripts/perf_benchmark/stage_helpers.py — MI 13.2 below 65
- `scripts/perf_benchmark/support.py:1` <module> [medium/complexity] — Improve maintainability of scripts/perf_benchmark/support.py — MI 24.0 below 65
- `scripts/perf_benchmark_pipeline.py:1` <module> [medium/complexity] — Improve maintainability of scripts/perf_benchmark_pipeline.py — MI 21.0 below 65
- `perf-optimization/scripts/select_candidate.py:1` <module> [low/complexity] — Improve maintainability of perf-optimization/scripts/select_candidate.py — MI 57.8 below 65
- `perf-optimization/scripts/verify_win.py:1` <module> [low/complexity] — Improve maintainability of perf-optimization/scripts/verify_win.py — MI 50.7 below 65
- `scripts/perf_benchmark/findings.py:1` <module> [low/complexity] — Improve maintainability of scripts/perf_benchmark/findings.py — MI 56.3 below 65
- `scripts/perf_benchmark/reporting.py:126` write_markdown_report [low/complexity] — Reduce parameters of write_markdown_report() — 6 exceeds 5
- `scripts/perf_benchmark/reporting.py:353` write_json_summary [low/complexity] — Reduce parameters of write_json_summary() — 7 exceeds 5
- `scripts/perf_benchmark_pipeline.py:625` write_json_summary [low/complexity] — Reduce parameters of write_json_summary() — 6 exceeds 5

## TEST (3)
- `perf-optimization/scripts/verify_win.py:1` <file> [high/coverage-gap] — Add behavior tests covering perf-optimization/scripts/verify_win.py (coverage 0.0% < 50.0%)
- `perf-optimization/scripts/select_candidate.py:1` <file> [medium/coverage-gap] — Add behavior tests covering perf-optimization/scripts/select_candidate.py (coverage 36.73% < 50.0%)
- `scripts/perf_benchmark/findings.py:1` <file> [medium/coverage-gap] — Add behavior tests covering scripts/perf_benchmark/findings.py (coverage 47.5% < 50.0%)

## TYPE (2)
- `scripts/perf_benchmark/reporting.py:422` return-value@422 [high/quality] — No return value expected
- `scripts/perf_benchmark/stage_helpers.py:187` assignment@187 [high/quality] — Incompatible types in assignment (expression has type "str", variable has type "int")

