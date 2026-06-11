# quality-audit report

## FORMAT (2)
- `perf-optimization/scripts/select_candidate.py:1` format_drift — Would reformat: perf-optimization/scripts/select_candidate.py [low]
- `perf-optimization/scripts/verify_win.py:1` format_drift — Would reformat: perf-optimization/scripts/verify_win.py [low]

## LINT (18)
- `perf-optimization/scripts/verify_win.py:214` E501 — Line too long (101 > 100) [medium]
- `perf-optimization/scripts/verify_win.py:252` E501 — Line too long (102 > 100) [medium]
- `perf-optimization/scripts/verify_win.py:255` E501 — Line too long (107 > 100) [medium]
- `perf-optimization/scripts/verify_win.py:256` E501 — Line too long (101 > 100) [medium]
- `perf-optimization/scripts/verify_win.py:265` E501 — Line too long (147 > 100) [medium]
- `perf-optimization/scripts/verify_win.py:275` E501 — Line too long (146 > 100) [medium]
- `scripts/perf_benchmark/reporting.py:392` B007 — Loop control variable `size` not used within loop body [medium]
- `scripts/perf_benchmark/scoring.py:38` B905 — `zip()` without an explicit `strict=` parameter [medium]
- `scripts/perf_benchmark/scoring.py:46` B905 — `zip()` without an explicit `strict=` parameter [medium]
- `scripts/perf_benchmark/scoring.py:106` SIM102 — Use a single `if` statement instead of nested `if` statements [medium]
- `scripts/perf_benchmark/stage_helpers.py:125` SIM115 — Use a context manager for opening files [medium]
- `scripts/perf_benchmark/stage_helpers.py:172` B905 — `zip()` without an explicit `strict=` parameter [medium]
- `scripts/perf_benchmark/stage_helpers.py:187` B905 — `zip()` without an explicit `strict=` parameter [medium]
- `scripts/perf_benchmark/stage_helpers.py:188` SIM105 — Use `contextlib.suppress(ValueError)` instead of `try`-`except`-`pass` [medium]
- `scripts/perf_benchmark/stage_helpers.py:324` SIM105 — Use `contextlib.suppress(ValueError)` instead of `try`-`except`-`pass` [medium]
- `scripts/perf_benchmark/support.py:116` SIM105 — Use `contextlib.suppress(ValueError, OSError)` instead of `try`-`except`-`pass` [medium]
- `scripts/perf_benchmark/support.py:126` SIM105 — Use `contextlib.suppress(ValueError, OSError)` instead of `try`-`except`-`pass` [medium]
- `scripts/perf_benchmark/support.py:136` SIM105 — Use `contextlib.suppress(ValueError, OSError)` instead of `try`-`except`-`pass` [medium]

## TYPE (2)
- `scripts/perf_benchmark/reporting.py:422` return-value — No return value expected [high]
- `scripts/perf_benchmark/stage_helpers.py:187` assignment — Incompatible types in assignment (expression has type "str", variable has type "int") [high]

