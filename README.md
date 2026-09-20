# perf-benchmark-skill

Linux performance benchmarking skill for coding agents that support Skills. It
profiles Python and C workloads, scores a 7-dimension rubric, and keeps
algorithmic issues ahead of cache, branch, and ASM tuning. When authorized to
optimize, it enforces a measure -> change -> re-measure loop with a hardened
before/after comparison.

For repo-agnostic use, pass an explicit `--target` or `--binary`.

## Installation

```bash
bootstrap/install-perf.sh --dest <skills-dir>
bootstrap/install-perf.sh --harness codex   # ~/.agents/skills
bootstrap/install-perf.sh --harness claude  # ~/.claude/skills
```

The same content ships to both hosts. Only runtime files install; tests,
history reports, and self-audit scaffolding stay in this repo.

Alternatively, `pip install .` provides `perf-benchmark`,
`perf-verify-win`, and `perf-select-candidate` (package
`perf-benchmark-tools`, version 1.0.0).

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
perf-benchmark \
  --root /path/to/repo \
  --out-dir /tmp/bench \
  --target "python -m benchmark_entrypoint {SIZE}" \
  --sizes 10000,100000 \
  --source-prefix path/to/source/ \
  --findings-out /tmp/perf-findings.json \
  --baseline-ledger /tmp/perf-ledger.jsonl
```

`--tier` defaults to `fast` (timing + tracemalloc); `medium`, `deep`, and
`asm` add opt-in Valgrind / `perf` / ASM profilers, including opt-in
`--perf-record` native hotspots and `--asm-audit` in deep runs.

`--max-cv` (default 5.0) sets the coefficient-of-variation noise gate:
timing-derived dimensions exceeding this threshold are scored `N/A (noise)`.
`--findings-out` writes shared-schema PERF findings JSON (one per FAIL/WARN
dimension, `signal: "PERF"`). `--baseline-ledger` maintains an append-only
JSONL run history with vs-last and vs-best regression checks; can be used
alongside `--baseline` for point-in-time comparison.

## Optimization Loop (authorized changes only)

```bash
perf-select-candidate --findings /tmp/perf-findings.json --out /tmp/candidate.json
# ... make one bounded change, re-run the identical benchmark shape, save the test log ...
perf-verify-win \
  --before /path/to/before/benchmark_summary.json \
  --after /path/to/after/benchmark_summary.json \
  --suite-exit-code 0 \
  --suite-evidence /path/to/test.log \
  --out /tmp/verdict.json
```

A win verifies only when workload and environment fingerprint match, timing
is not noisy, no dimension regresses a tier, and the suite is green without
an attached log the verdict is explicitly labeled `unverified`. The 5%
`--min-win` default is a wall-time convention; memory and scaling objectives
use their own honest policy (see `references/optimization-check.md`). Wins
and no-win outcomes follow the user's repository workflow; the skill never
commits by itself.

## Outputs

- `benchmark_report.md`: scorecard, findings, prescriptions
- `benchmark_summary.json`: machine-readable scores, regression data, and workload block
- `perf_findings.json`: shared-schema PERF findings (when `--findings-out` set)
- `baseline_ledger.jsonl`: append-only run history (when `--baseline-ledger` set)
- `verdict.json`: `accept` / `reject` / `error` with reasons
- `tier1/` to `tier4/`: raw profiler artifacts by depth

## More Detail

See [SKILL.md](SKILL.md) for the full workflow, tier behavior, agent guidance,
and reference links.

## License

MIT
