# SP9 K5 Convergence Run - perf-benchmark-skill

Schema: v2

## Cleanup

- Commit: `0f7bbcc`
- Finding class: duplication
- Result: four v0.5.0 duplication findings cleared; wave baseline unchanged

## Verification

| Command | Result |
| --- | --- |
| `python3 -m pytest -q` | Pass; 154 passed |
| `ruff check . && ruff format --check .` | Pass; all checks passed, 21 files already formatted |
| `check_wave_baseline.py` with v0.5.0 skill root | Pass twice; count 59, baseline 59 |

The K4 seeded baseline remains equality-stable after the K5 cleanup.
