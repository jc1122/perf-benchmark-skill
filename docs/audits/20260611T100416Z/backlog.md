# K4-T1 backlog

Run path: `docs/audits/20260611T100416Z`  
Source HEAD: `ceff6b77535392a5df3b7b16b3db18749ac7ee90`  
Installed leaves: `0.4.0`

## Command evidence

| Command | Observed result |
| --- | --- |
| bootstrap checker | exit `0`; active lanes `bootstrap`, `code-health-python`, `security`, `performance`, `hygiene`, `orchestration`; performance lane `full`; selected `perf-benchmark`, `perf-optimization` |
| coverage | exit `0`; `151` passed; coverage JSON at `/tmp/sp9-k4/coverage.json` |
| code-health | exit `2`; `66` findings; `test-effectiveness` skipped because `mutation_scope` artifact required |
| security | exit `1`; `22` findings |
| dependency | exit `0`; `0` findings; `manifest=false` |
| hygiene | exit `0`; `0` findings |
| docs | exit `1`; `20` findings |
| hotspot | exit `1`; `6` findings |

## Manifest semantics

- `pyproject.toml` contains only `[tool.ruff]`, `[tool.ruff.lint]`, and `[tool.ruff.format]`; it has no `[project]` section.
- Dependency audit metadata is recorded exactly as: `{"status":"ok","findings":0,"leaf":"dependency","manifest":false}`.
- This is recorded honestly and not fixed in `repo-P`.

## Triaged backlog

### accepted-mechanical (K4-T4 candidates)

| Path | Symbol | Metric | Action |
| --- | --- | --- | --- |
| perf-optimization/scripts/select_candidate.py | perf-optimization/scripts/select_candidate.py | format_drift | Run the formatter on `perf-optimization/scripts/select_candidate.py` |
| perf-optimization/scripts/verify_win.py | perf-optimization/scripts/verify_win.py | format_drift | Run the formatter on `perf-optimization/scripts/verify_win.py` |
| perf-optimization/scripts/verify_win.py | E501@214:101 | E501 | Line too long (101 > 100) |
| perf-optimization/scripts/verify_win.py | E501@252:101 | E501 | Line too long (102 > 100) |
| perf-optimization/scripts/verify_win.py | E501@255:101 | E501 | Line too long (107 > 100) |
| perf-optimization/scripts/verify_win.py | E501@256:101 | E501 | Line too long (101 > 100) |
| perf-optimization/scripts/verify_win.py | E501@265:101 | E501 | Line too long (147 > 100) |
| perf-optimization/scripts/verify_win.py | E501@275:101 | E501 | Line too long (146 > 100) |
| scripts/perf_benchmark/reporting.py | B007@392:13 | B007 | Loop control variable `size` not used within loop body |
| scripts/perf_benchmark/reporting.py | return-value@422 | return-value | No return value expected |
| scripts/perf_benchmark/scoring.py | B905@38:42 | B905 | `zip()` without an explicit `strict=` parameter |
| scripts/perf_benchmark/scoring.py | B905@46:36 | B905 | `zip()` without an explicit `strict=` parameter |
| scripts/perf_benchmark/scoring.py | SIM102@106:5 | SIM102 | Use a single `if` statement instead of nested `if` statements |
| scripts/perf_benchmark/stage_helpers.py | SIM115@125:11 | SIM115 | Use a context manager for opening files |
| scripts/perf_benchmark/stage_helpers.py | B905@172:34 | B905 | `zip()` without an explicit `strict=` parameter |
| scripts/perf_benchmark/stage_helpers.py | B905@187:30 | B905 | `zip()` without an explicit `strict=` parameter |
| scripts/perf_benchmark/stage_helpers.py | assignment@187 | assignment | Incompatible types in assignment (expression has type "str", variable has type "int") |
| scripts/perf_benchmark/stage_helpers.py | SIM105@188:13 | SIM105 | Use `contextlib.suppress(ValueError)` instead of `try`-`except`-`pass` |
| scripts/perf_benchmark/stage_helpers.py | SIM105@324:9 | SIM105 | Use `contextlib.suppress(ValueError)` instead of `try`-`except`-`pass` |
| scripts/perf_benchmark/support.py | SIM105@116:5 | SIM105 | Use `contextlib.suppress(ValueError, OSError)` instead of `try`-`except`-`pass` |
| scripts/perf_benchmark/support.py | SIM105@126:5 | SIM105 | Use `contextlib.suppress(ValueError, OSError)` instead of `try`-`except`-`pass` |
| scripts/perf_benchmark/support.py | SIM105@136:5 | SIM105 | Use `contextlib.suppress(ValueError, OSError)` instead of `try`-`except`-`pass` |

### deferred-structural

#### complexity

| Path | Metric | Signal count | Representative symbol/metric triggers |
| --- | --- | --- | --- |
| perf-optimization/scripts/select_candidate.py | maintainability_index / cyclomatic_complexity | 2 | `<module>` MI 57.8 (`SIMPLIFY`), `_validate_finding` CCN=12 (`DECOMPOSE`) |
| perf-optimization/scripts/verify_win.py | maintainability_index / cyclomatic_complexity | 2 | `<module>` MI 50.7 (`SIMPLIFY`), `_read_ledger` CCN=13 (`DECOMPOSE`) |
| scripts/perf_benchmark/findings.py | maintainability_index | 1 | `<module>` MI 56.3 (`SIMPLIFY`) |
| scripts/perf_benchmark/ledger.py | cyclomatic_complexity | 1 | `compare` CCN=11 (`DECOMPOSE`) |
| scripts/perf_benchmark/reporting.py | complexity family | 9 | `_summarize_wall_time_metrics` (CCN/NLOC), `write_markdown_report` (CCN/NLOC/parameter_count), `write_json_summary` (CCN/NLOC/parameter_count) |
| scripts/perf_benchmark/scoring.py | complexity family | 8 | `_fit_exponent`, `score_algorithmic_scaling`, `score_wall_time_stability`, `score_cpu_efficiency`, `score_cache_dim`, `score_memory_profile` plus module MI |
| scripts/perf_benchmark/stage_helpers.py | complexity family | 7 | `_generate_tracemalloc_wrapper` NLOC, `_parse_cachegrind_summary`, `_parse_massif_out` (CCN/NLOC), `_parse_perf_stat`, `_discover_objdump_targets` |
| scripts/perf_benchmark/support.py | complexity family | 2 | `detect_cache_topology` CCN=16 (`DECOMPOSE`), module MI (`SIMPLIFY`) |
| scripts/perf_benchmark_pipeline.py | complexity family | 9 | `stage_tier1` (CCN/NLOC), `run_parallel_tiers` CCN=12, `stage_perf_record` NLOC=75, `parse_args` NLOC=78, `main` (CCN/NLOC), module MI, `write_json_summary` parameter_count |
| Total (complexity findings) |  | 41 | `code-health` leaf reports 41 complexity rows |

#### hotspot (non-FP)

| Path | Metric | Severity | Action |
| --- | --- | --- | --- |
| README.md | temporal_coupling_ratio | RESTRUCTURE | Co-change README with SKILL.md (0.88) and `scripts/perf_benchmark_pipeline.py` (0.7); review ownership boundaries |
| SKILL.md | temporal_coupling_ratio | RESTRUCTURE | Co-change SKILL.md with `scripts/perf_benchmark_pipeline.py` (0.88) |
| SKILL.md | churn_complexity_product | DECOMPOSE | SKILL.md churn/size is high (`1488`); split and stabilize doc-driven changes |
| scripts/perf_benchmark_pipeline.py | churn_complexity_product | DECOMPOSE | `10455` churn/size hotspot; split this high-volatility file |

### coverage-gated

| Path | Metric | Action |
| --- | --- | --- |
| perf-optimization/scripts/select_candidate.py | file_coverage_percent 36.73 (< 50.0) | Add behavior tests |
| perf-optimization/scripts/verify_win.py | file_coverage_percent 0.0 (< 50.0) | Add behavior tests |
| scripts/perf_benchmark/findings.py | file_coverage_percent 47.5 (< 50.0) | Add behavior tests |

### won't-fix-FP

#### docs-consistency (`expires: v0.5.0 reinstall`)

| Path | Symbol | Finding | Justification |
| --- | --- | --- | --- |
| docs/plans/2026-06-10-sp6-perf-bench-v0.2.md | shared/health_common.py | doc_path_missing | `0.4.0` checker cannot exclude docs/plans references from the `docs` consistency surface in this run; keep the referenced design path mapping as-is for now |
| docs/plans/2026-06-10-sp6-perf-bench-v0.2.md | references/remediation-playbook.md | doc_path_missing | Same as above; intentional missing references are from a doc plan, not code breakage |
| docs/plans/2026-06-10-sp6-perf-bench-v0.2.md | references/prioritization.md | doc_path_missing | Same as above |
| docs/plans/2026-06-10-sp6-perf-bench-v0.2.md | references/remediation-playbook.md | doc_path_missing | Same as above |
| docs/plans/2026-06-10-sp6-perf-bench-v0.2.md | references/prioritization.md | doc_path_missing | Same as above |
| docs/plans/2026-06-10-sp6-perf-bench-v0.2.md | references/remediation-playbook.md | doc_path_missing | Same as above |
| docs/plans/2026-06-10-sp6-perf-bench-v0.2.md | references/prioritization.md | doc_path_missing | Same as above |
| perf-optimization/SKILL.md | references/optimization-playbook.md | doc_path_missing | Nested path under `perf-optimization` currently out of scope for 0.4.0 relative resolution semantics |
| perf-optimization/SKILL.md | references/optimization-playbook.md | doc_path_missing | Nested path under `perf-optimization` currently out of scope for 0.4.0 relative resolution semantics |
| perf-optimization/SKILL.md | ../references/perf-remediation-playbook.md | doc_path_missing | Relative parent reference does not resolve in this leaf version |
| perf-optimization/SKILL.md | references/optimization-playbook.md | doc_path_missing | Nested path under `perf-optimization` currently out of scope for 0.4.0 relative resolution semantics |
| perf-optimization/SKILL.md | ../references/perf-remediation-playbook.md | doc_path_missing | Relative parent reference does not resolve in this leaf version |
| perf-optimization/SKILL.md | ../references/finding-schema.json | doc_path_missing | Relative parent reference does not resolve in this leaf version |
| perf-optimization/SKILL.md | ../scripts/perf_benchmark/ledger.py | doc_path_missing | Relative parent reference to repo script is mis-scoped under this 0.4.0 audit layout |
| perf-optimization/SKILL.md | ../scripts/perf_benchmark/findings.py | doc_path_missing | Relative parent reference to repo script is mis-scoped under this 0.4.0 audit layout |
| perf-optimization/references/optimization-playbook.md | ../references/perf-remediation-playbook.md | doc_path_missing | Relative parent reference does not resolve in this leaf version |
| perf-optimization/references/optimization-playbook.md | ../SKILL.md | doc_path_missing | Mis-scoped sibling reference in nested reference doc under current layout |
| perf-optimization/references/optimization-playbook.md | ../references/finding-schema.json | doc_path_missing | Relative parent reference does not resolve in this leaf version |
| references/sample-report.md | tests/benchmarks/test_benchmark_graph.py | doc_path_missing | Missing sample fixture path is known-in-waiting for `sample-report` doc and not a runtime regression |

#### hotspot author_concentration (`expires: v0.5.0 reinstall`)

| Path | Symbol | Metric | Note |
| --- | --- | --- | --- |
| scripts/perf_benchmark_pipeline.py | `author_concentration` | value=1.0 | Single-author concentration in high-traffic file; requires broader review process before remediation |

#### security (`expires: none`)

| Path | Symbol | Metric | Justification | Expires |
| --- | --- | --- | --- | --- |
| perf-optimization/scripts/verify_win.py | hardcoded_password_string | bandit_B105 | Constant string map is `TIER_RANK`/status metadata, not credentials | none |
| scripts/perf_benchmark/findings.py | hashlib | bandit_B324 | SHA1 is used only for deterministic finding-id generation (`perf-benchmark` IDs) | none |
| scripts/perf_benchmark/ledger.py | hardcoded_password_string | bandit_B105 | `TIER_RANK` mapping is status metadata, not secrets | none |
| scripts/perf_benchmark/scoring.py | hardcoded_password_string | bandit_B105 | `TIER_RANK` mapping is status metadata, not secrets | none |
| scripts/perf_benchmark_pipeline.py | blacklist | bandit_B404 | Intentional use of `subprocess` for benchmark and profiling tool orchestration | none |
| scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | Intentional `subprocess.run([...])` for pytest/objdump/valgrind/perf (shell=False) | none |
| scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | Intentional `subprocess.run([...])` in `tracemalloc` wrapper path (shell=False) | none |
| scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | Intentional `subprocess.run([...])` in `/usr/bin/time` flow (shell=False) | none |
| scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | Intentional `subprocess.run([...])` for cachegrind (shell=False) | none |
| scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | Intentional `subprocess.run([...])` for cachegrind annotations (shell=False) | none |
| scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | Intentional `subprocess.run([...])` for callgrind (shell=False) | none |
| scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | Intentional `subprocess.run([...])` for callgrind annotations (shell=False) | none |
| scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | Intentional `subprocess.run([...])` for massif runs (shell=False) | none |
| scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | Intentional `subprocess.run([...])` for massif text report generation (shell=False) | none |
| scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | Intentional `subprocess.run([...])` for perf stat (shell=False) | none |
| scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | Intentional `subprocess.run([...])` for perf record (shell=False) | none |
| scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | Intentional `subprocess.run([...])` for perf report parsing (shell=False) | none |
| scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | Intentional `subprocess.run([...])` for objdump with benchmark binary path | none |
| scripts/perf_benchmark_pipeline.py | start_process_with_partial_path | bandit_B607 | Intended objdump invocation on resolved relative/absolute paths under controlled benchmark context | none |
| scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | Intentional `subprocess.run([...])` for iterative objdump over discovered binaries | none |
| scripts/perf_benchmark_pipeline.py | start_process_with_partial_path | bandit_B607 | Intended objdump invocation for each discovered shared object | none |
| scripts/perf_benchmark_pipeline.py | subprocess_without_shell_equals_true | bandit_B603 | Intentional `subprocess.run([args.python, '-c', ...])` for numba presence probe | none |
