# SP10 T5 Steady-State Run - perf-benchmark-skill

Schema: v2

## Results

| Check | Result |
| --- | --- |
| Bootstrap probe | Pass; restart_required=false, stop_before_discovery=false |
| Wave ratchet | Baseline 59 -> 55; four entrypoint module-MI rows removed |
| Wave convergence | Pass twice; count 55, baseline 55 |
| `python3 -m pytest -q` | Pass; 154 passed |
| Version | Remains 0.3.0; SP10 changed only baseline/docs artifacts |

## Remaining Backlog

| Class | Decision | Evidence |
| --- | --- | --- |
| structural-code-health | deferred | 40 code-health findings remain across benchmark scoring, reporting, stage helpers, and pipeline orchestration. |
| security-fp | deferred | 21 security findings remain in the existing freeze-ledger classes. |
| hotspot-ordering | deferred | 6 hotspot findings remain as future ordering signals. |

## Warnings

- Installed repo-audit leaves still read as 0.5.0 until T6 reinstall.
- No repo-P version bump was made because baseline/docs ratchets alone do not bump the skill version.
