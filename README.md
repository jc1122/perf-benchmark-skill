# perf-benchmark-skill

Linux performance benchmarking skill for coding agents that support Skills. It
measures algorithmic scaling, CPU cycles, L1/L2/L3 cache efficiency, branch
prediction, memory profile, and ASM metrics using industry-standard tools.

## Installation

```bash
npx skills add jc1122/perf-benchmark-skill
```

## What It Does

Runs a 4-tier profiling pipeline and scores results against a **7-dimension rubric (0-28)**:

| # | Dimension | Impact | Tools Used |
|---|-----------|--------|------------|
| 0 | Algorithmic Scaling | 100-1000x | pytest-benchmark + callgrind |
| 1 | Wall-Time Stability | quality gate | pytest-benchmark / GNU time |
| 2 | CPU Efficiency | 2-5x | callgrind + perf stat |
| 3 | L1 Cache Efficiency | 5-20x | Valgrind cachegrind |
| 4 | Last-Level Cache | 5-20x | Valgrind cachegrind |
| 5 | Branch Prediction | 2-5x | cachegrind / perf stat |
| 6 | Memory Profile | 5-20x | Valgrind massif + tracemalloc |

Algorithmic issues are always prioritized over hardware micro-optimizations.

## Requirements

- **Linux** (uses `/proc`, `/sys`, Valgrind, perf)
- **Python >= 3.10**
- **Valgrind** (required for Tiers 2-4): `sudo apt install valgrind`
- **perf** (optional, for hardware PMU counters): `sudo apt install linux-tools-common`
  - Requires: `sudo sysctl kernel.perf_event_paranoid=1`
- **pytest-benchmark** (optional, for Tier 1): `pip install pytest-benchmark`

## Quick Start

```bash
# Fast mode (seconds) — wall time + memory only
python scripts/perf_benchmark_pipeline.py \
  --root /path/to/repo \
  --out-dir /tmp/bench \
  --tier fast \
  --sizes 10000,100000

# Medium mode (minutes) — adds cache + CPU profiling
python scripts/perf_benchmark_pipeline.py \
  --root /path/to/repo \
  --out-dir /tmp/bench \
  --tier medium \
  --source-prefix src/mypackage/ \
  --sizes 10000,100000

# Profile a standalone C binary
python scripts/perf_benchmark_pipeline.py \
  --root . \
  --out-dir /tmp/bench \
  --binary ./build/my_program \
  --tier deep \
  --asm-audit
```

## Output

```
out-dir/
├── benchmark_report.md       # Rubric scorecard + findings + prescriptions
├── benchmark_summary.json    # Machine-readable (for regression baselines)
├── tier1/                    # Wall time, tracemalloc, GNU time
├── tier2/                    # Cachegrind + callgrind annotated output
├── tier3/                    # Massif heap profile + perf stat
└── tier4/                    # objdump disassembly (if --asm-audit)
```

When `--baseline` is supplied, the report and summary also include
`baseline_regressions` and a `regression_blocker` flag for any scored
dimension that drops by at least one tier versus the baseline.

## CLI Reference

| Flag | Default | Description |
|------|---------|-------------|
| `--root` | (required) | Repository root path |
| `--out-dir` | (required) | Output directory |
| `--tier` | `medium` | `fast` / `medium` / `deep` / `asm` |
| `--sizes` | none | Comma-separated input sizes for scaling analysis |
| `--target` | auto-detect | Explicit benchmark command (`{SIZE}` placeholder) |
| `--binary` | none | Standalone C binary to profile |
| `--source-prefix` | none | Source filter for `cg_annotate --include` |
| `--valgrind-size` | `10000` | Input size for Valgrind runs |
| `--max-valgrind-parallel` | `2` | Max concurrent Valgrind instances |
| `--expected-complexity` | `nlogn` | `linear` / `nlogn` / `quadratic` |
| `--baseline` | none | Previous `benchmark_summary.json` for regression |
| `--perf-repeats` | `5` | perf stat iterations |
| `--perf-events` | curated set | Custom perf event list |
| `--time-repeats` | `5` | GNU time iterations (when no pytest-benchmark) |
| `--asm-audit` | off | Enable Tier 4 objdump + Numba ASM |
| `--valgrind-timeout` | `1800` | Timeout per Valgrind run in seconds |
| `--env` | none | Environment variable `KEY=VALUE` (repeatable) |

## License

MIT
