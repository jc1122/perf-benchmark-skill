# perf-benchmark-skill

Linux performance benchmarking skill for coding agents that support Skills. It
profiles Python and C workloads, scores a 7-dimension rubric, and keeps
algorithmic issues ahead of cache, branch, and ASM tuning.

For repo-agnostic use, pass an explicit `--target` or `--binary`.

## Installation

```bash
npx skills add <skill-source>/perf-benchmark-skill
```

`<skill-source>` means the installable source or repository path that hosts this skill.

## Scope

- Algorithmic scaling, wall-time stability, CPU efficiency, cache behavior,
  branch prediction, memory profile, and optional ASM review
- Linux-only, using `/proc`, `/sys`, Valgrind, and `perf`
- `SKILL.md` is the detailed agent-facing workflow and CLI reference

Pytest benchmark autodiscovery is a convenience for Python repos. For
non-pytest entrypoints, use `--target` or `--binary`.

Multi-size explicit targets must include `{SIZE}`.

Full Algorithmic Scaling scoring requires `deep` or `asm` because allocation churn comes from massif.

## Usage

```bash
python scripts/perf_benchmark_pipeline.py \
  --root /path/to/repo \
  --out-dir /tmp/bench \
  --tier deep \
  --target "python -m benchmark_entrypoint {SIZE}" \
  --sizes 10000,100000 \
  --source-prefix path/to/source/ \
  --perf-record \
  --max-cv 5.0 \
  --findings-out /tmp/perf-findings.json \
  --baseline-ledger /tmp/perf-ledger.jsonl
```

`--perf-record` is opt-in native hotspot sampling via `perf record` and
`perf report`. Use it when `perf` is available and you want flat sampled
hotspots in addition to the rubric.

`--max-cv` (default 5.0) sets the coefficient-of-variation noise gate:
timing-derived dimensions exceeding this threshold are scored `N/A (noise)`.
`--findings-out` writes shared-schema PERF findings JSON (one per FAIL/WARN
dimension, `signal: "PERF"`). `--baseline-ledger` maintains an append-only
JSONL run history with vs-last and vs-best regression checks; can be used
alongside `--baseline` for point-in-time comparison.

## Outputs

- `benchmark_report.md`: scorecard, findings, prescriptions
- `benchmark_summary.json`: machine-readable scores and regression data
- `perf_findings.json`: shared-schema PERF findings (when `--findings-out` set)
- `baseline_ledger.jsonl`: append-only run history (when `--baseline-ledger` set)
- `tier1/` to `tier4/`: raw profiler artifacts by depth

## More Detail

See [SKILL.md](SKILL.md) for the full workflow, tier behavior, agent guidance,
and reference links.

## License

MIT
