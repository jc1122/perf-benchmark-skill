# SP9 Wave Freeze Log

## Seed

- Seed timestamp: 2026-06-11T12:31:45Z
- Source HEAD: `290cbbc49313e4df1377653dee0c5c13816a91ef`

## Command evidence

| Command | Observed result |
| --- | --- |
| `WAVE_RUNNER=/home/jakub/projects/repo-audit-refactor-optimize/scripts/run_diagnosis_wave.py SKILLS_ROOT=~/.claude/skills python3 scripts/check_wave_baseline.py` | Baseline check executed with the seeded hidden wave output; checker compares normalized finding identities and ignores the runner process status. |
| Wave summary | code-health exit `2`/status `error`/findings `44`; security exit `1`/status `findings`/findings `24`; docs exit `1`/status `findings`/findings `1`; hotspot exit `1`/status `findings`/findings `7`; dependency exit `0`/status `ok`/findings `0`; hygiene exit `0`/status `ok`/findings `0`. |
| Snapshot provenance | Findings snapshot collected in the ignored wave output directory from the same runner with prefixes `scripts` and `perf-optimization/scripts`. |

## Residual findings

The code-health lane contains findings; there are no missing-artifact failures in this snapshot.

| Leaf | Path | Symbol | Metric | Class | Justification | Expires |
| --- | --- | --- | --- | --- | --- | --- |
| complexity | scripts/perf_benchmark/reporting.py | _summarize_wall_time_metrics | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/reporting.py | write_markdown_report | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/scoring.py | score_algorithmic_scaling | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/scoring.py | score_wall_time_stability | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/stage_helpers.py | _parse_cachegrind_summary | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark_pipeline.py | stage_tier1 | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | perf-optimization/scripts/verify_win.py | <module> | maintainability_index | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/reporting.py | <module> | maintainability_index | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/scoring.py | <module> | maintainability_index | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/stage_helpers.py | <module> | maintainability_index | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/support.py | <module> | maintainability_index | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark_pipeline.py | <module> | maintainability_index | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | perf-optimization/scripts/select_candidate.py | _validate_finding | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | perf-optimization/scripts/verify_win.py | _read_ledger | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | perf-optimization/scripts/verify_win.py | main | function_nloc | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/check_wave_baseline.py | main | function_nloc | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/ledger.py | compare | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/reporting.py | _summarize_wall_time_metrics | function_nloc | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/reporting.py | write_markdown_report | function_nloc | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/reporting.py | write_json_summary | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/reporting.py | write_json_summary | function_nloc | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/scoring.py | _fit_exponent | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/scoring.py | score_algorithmic_scaling | function_nloc | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/scoring.py | score_cpu_efficiency | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/scoring.py | score_cache_dim | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/scoring.py | score_memory_profile | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/stage_helpers.py | _generate_tracemalloc_wrapper | function_nloc | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/stage_helpers.py | _parse_massif_out | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/stage_helpers.py | _parse_massif_out | function_nloc | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/stage_helpers.py | _parse_perf_stat | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/stage_helpers.py | _discover_objdump_targets | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/support.py | detect_cache_topology | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark_pipeline.py | stage_tier1 | function_nloc | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark_pipeline.py | stage_perf_record | function_nloc | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark_pipeline.py | run_parallel_tiers | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark_pipeline.py | parse_args | function_nloc | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark_pipeline.py | main | cyclomatic_complexity | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark_pipeline.py | main | function_nloc | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | perf-optimization/scripts/select_candidate.py | <module> | maintainability_index | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/check_wave_baseline.py | <module> | maintainability_index | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/findings.py | <module> | maintainability_index | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/reporting.py | write_markdown_report | parameter_count | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark/reporting.py | write_json_summary | parameter_count | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| complexity | scripts/perf_benchmark_pipeline.py | write_json_summary | parameter_count | deferred-structural | Exceeds K4 mechanical scope and requires decomposition/refactor, not a mechanical lint-class fix. | none |
| security | perf-optimization/scripts/verify_win.py | hardcoded_password_string | bandit_B105 | wont-fix-FP | `TIER_RANK`/status constants are metadata, not credentials. | none |
| security | scripts/check_wave_baseline.py | blacklist | bandit_B404 | wont-fix-FP | Subprocess blacklist usage is tied to trusted wave-runner invocation and controlled command flow. | none |
| security | scripts/check_wave_baseline.py | subprocess_without_shell_equals_true | bandit_B603 | wont-fix-FP | Intentional wave-runner invocation with list args and `shell=False`. | none |
| security | scripts/perf_benchmark/findings.py | hashlib | bandit_B324 | wont-fix-FP | `hashlib` is used only for deterministic finding-id generation, not security hashing. | none |
| security | scripts/perf_benchmark/ledger.py | hardcoded_password_string | bandit_B105 | wont-fix-FP | `TIER_RANK`/status constants are metadata, not credentials. | none |
| security | scripts/perf_benchmark/scoring.py | hardcoded_password_string | bandit_B105 | wont-fix-FP | `TIER_RANK`/status constants are metadata, not credentials. | none |
| security | scripts/perf_benchmark_pipeline.py | blacklist | bandit_B404 | wont-fix-FP | Intentional benchmark/profiling tool orchestration (pytest, valgrind, cachegrind, callgrind, massif, perf, objdump, numba probe) via subprocess. | none |
| security | scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | wont-fix-FP | Intentional subprocess orchestration for benchmark/profiling flow with `shell=False` and fixed argument lists. | none |
| security | scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | wont-fix-FP | Intentional subprocess orchestration for benchmark/profiling flow with `shell=False` and fixed argument lists. | none |
| security | scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | wont-fix-FP | Intentional subprocess orchestration for benchmark/profiling flow with `shell=False` and fixed argument lists. | none |
| security | scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | wont-fix-FP | Intentional subprocess orchestration for benchmark/profiling flow with `shell=False` and fixed argument lists. | none |
| security | scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | wont-fix-FP | Intentional subprocess orchestration for benchmark/profiling flow with `shell=False` and fixed argument lists. | none |
| security | scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | wont-fix-FP | Intentional subprocess orchestration for benchmark/profiling flow with `shell=False` and fixed argument lists. | none |
| security | scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | wont-fix-FP | Intentional subprocess orchestration for benchmark/profiling flow with `shell=False` and fixed argument lists. | none |
| security | scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | wont-fix-FP | Intentional subprocess orchestration for benchmark/profiling flow with `shell=False` and fixed argument lists. | none |
| security | scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | wont-fix-FP | Intentional subprocess orchestration for benchmark/profiling flow with `shell=False` and fixed argument lists. | none |
| security | scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | wont-fix-FP | Intentional subprocess orchestration for benchmark/profiling flow with `shell=False` and fixed argument lists. | none |
| security | scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | wont-fix-FP | Intentional subprocess orchestration for benchmark/profiling flow with `shell=False` and fixed argument lists. | none |
| security | scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | wont-fix-FP | Intentional subprocess orchestration for benchmark/profiling flow with `shell=False` and fixed argument lists. | none |
| security | scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | wont-fix-FP | Intentional subprocess orchestration for benchmark/profiling flow with `shell=False` and fixed argument lists. | none |
| security | scripts/perf_benchmark_pipeline.py | start_process_with_partial_path | bandit_B607 | wont-fix-FP | `objdump` invocation path is controlled by benchmark context; no shell interpolation occurs. | none |
| security | scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | wont-fix-FP | Intentional subprocess orchestration for benchmark/profiling flow with `shell=False` and fixed argument lists. | none |
| security | scripts/perf_benchmark_pipeline.py | start_process_with_partial_path | bandit_B607 | wont-fix-FP | `objdump` invocation path is controlled by benchmark context; no shell interpolation occurs. | none |
| security | scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | wont-fix-FP | Intentional subprocess orchestration for benchmark/profiling flow with `shell=False` and fixed argument lists. | none |
| docs-consistency | references/sample-report.md | tests/benchmarks/test_benchmark_graph.py | doc_path_missing | wont-fix-FP | Sample/report fixture reference under installed 0.4.0 docs leaf remains frozen for K5 ratchet/doc-scope cleanup. | v0.5.0 reinstall |
| hotspot | README.md | README.md<->SKILL.md | temporal_coupling_ratio | deferred-structural | Real architecture/churn signal; not a K4 mechanical lint-class fix. | none |
| hotspot | README.md | README.md<->scripts/perf_benchmark_pipeline.py | temporal_coupling_ratio | deferred-structural | Real architecture/churn signal; not a K4 mechanical lint-class fix. | none |
| hotspot | SKILL.md | SKILL.md | churn_complexity_product | deferred-structural | Real architecture/churn signal; not a K4 mechanical lint-class fix. | none |
| hotspot | SKILL.md | SKILL.md<->scripts/perf_benchmark_pipeline.py | temporal_coupling_ratio | deferred-structural | Real architecture/churn signal; not a K4 mechanical lint-class fix. | none |
| hotspot | scripts/perf_benchmark/reporting.py | scripts/perf_benchmark/reporting.py | churn_complexity_product | deferred-structural | Real architecture/churn signal; not a K4 mechanical lint-class fix. | none |
| hotspot | scripts/perf_benchmark_pipeline.py | scripts/perf_benchmark_pipeline.py | churn_complexity_product | deferred-structural | Real architecture/churn signal; not a K4 mechanical lint-class fix. | none |
| hotspot | scripts/perf_benchmark_pipeline.py | scripts/perf_benchmark_pipeline.py | author_concentration | wont-fix-FP | Single-author noise per SP9 FP evidence. | v0.5.0 reinstall |
