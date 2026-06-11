# SP9 K4 v2 Run Report (repo-P)

- Schema version: 2
- Repo root: `/home/jakub/projects/perf-benchmark-skill`
- Started UTC: 2026-06-11T10:04:16Z
- Finished UTC: 2026-06-11T12:45:00Z
- Skill versions: `perf-benchmark` 0.3.0; `perf-optimization` 0.2.0
- Push: no push was performed.

## Lane Summary

| Lane | Exit | Status | Findings |
| --- | ---: | --- | ---: |
| code-health | 2 | error, advisory residuals frozen | 44 |
| security | 1 | findings, frozen review items | 24 |
| hygiene | 0 | ok | 0 |
| docs | 0 | ok after T5 shrink ratchet | 0 |
| dependency | 0 | ok, no `[project]` manifest | 0 |
| hotspot | 1 | findings, frozen churn/coupling items | 6 |

`code-health` exit 2 is retained as the advisory GATE verdict after remaining
complexity findings were frozen. Valgrind is absent, so K4 performance evidence
is fast-tier only.

## Findings

| Signal | Count |
| --- | ---: |
| DECOMPOSE | 34 |
| SIMPLIFY | 12 |
| RESTRUCTURE | 4 |
| SECURITY | 24 |
| PERF | 0 |
| DOCS | 0 |
| TEST | 0 |

Normalized baseline: `scripts/wave_baseline.json` has 74 raw findings and 59
normalized identities.

## Final Backlog

| Class | Count |
| --- | ---: |
| accepted | 0 |
| deferred | 49 |
| coverage_gated | 0 |
| wont_fix | 25 |

T5 removed two stale baseline identities shrink-only: the sample-report
docs-consistency path and `SKILL.md` hotspot churn item.

## K4 Task Evidence

| Task | Commit(s) | Result |
| --- | --- | --- |
| K4-T1 | `ff2127a` | Created bootstrap/diagnosis artifacts and backlog at `docs/audits/20260611T100416Z/`. |
| K4-T2 | `5305c1f` | Recorded two fast-tier baseline ledger lines in `docs/perf/baseline_ledger.jsonl`. |
| K4-T3 | `8378a0e` | Recorded selector `no_candidates` and the honest no-win verdict. |
| K4-T4 | `9db2d75`, `290cbbc`, `0cc81ec` | Cleared mechanical lint items, added the wave checker, and seeded the initial frozen baseline. |
| K4-T5 | `796357f` | Applied brevity/version pass, changelogs, shrink-only wave ratchet, and this report. |

## Performance Evidence

| Artifact | Result |
| --- | --- |
| `docs/perf/baseline_ledger.jsonl` | 2 lines |
| `docs/audits/20260611T100416Z/perf-before/perf_findings.json` | empty array |
| `docs/audits/20260611T100416Z/opt/candidate.json` | `{"status":"no_candidates"}` |
| `docs/audits/20260611T100416Z/opt/verdict.json` | `evaluated, no feasible low-risk win` |

## Line Counts

| File | Before | After |
| --- | ---: | ---: |
| `SKILL.md` | 244 | 111 |
| `perf-optimization/SKILL.md` | 357 | 109 |
| `references/sample-report.md` | 296 | 54 |
| `references/tool-guide.md` | 193 | 46 |
| `CHANGELOG.md` | 0 | 15 |
| `perf-optimization/CHANGELOG.md` | 0 | 11 |

## Verification

| Command | Exit | Output |
| --- | ---: | --- |
| `python3 -m pytest -q` | 0 | `154 passed` |
| `ruff check .` | 0 | `All checks passed!` |
| `ruff format --check .` | 0 | `21 files already formatted` |
| `WAVE_RUNNER=/home/jakub/projects/repo-audit-refactor-optimize/scripts/run_diagnosis_wave.py SKILLS_ROOT=~/.claude/skills python3 scripts/check_wave_baseline.py` | 0 | `{"status":"pass","count":59,"baseline":59}` |
| `python3 -m json.tool scripts/wave_baseline.json` | 0 | valid JSON; 74 raw findings |
| `git diff --check` | 0 | empty output |
| `python3 /home/jakub/projects/repo-audit-refactor-optimize/scripts/validate_run_report.py --run-dir docs/audits/20260611T100416Z --schema 2` | 0 | `{"status":"pass"}` |

## Warnings

1. Security findings are frozen as local benchmark/profiling subprocess and
   metadata false-positive review items.
2. No optimization win was fabricated; the only allowed attempt ended with an
   honest no-candidate verdict.
3. No push was performed.
