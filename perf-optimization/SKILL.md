---
name: perf-optimization
version: 0.1.0
description: >
  Iterative evidence-driven performance optimization that consumes perf-benchmark
  findings, selects the highest-impact candidate, applies one bounded change per
  iteration, re-measures with identical profiling, and records accepted wins in
  an append-only ledger. Algorithmic scaling failures gate all constant-factor work.
---

# Performance Optimization Pipeline

## Overview

Use this skill to systematically act on performance findings produced by the
`perf-benchmark` (SP6) pipeline. It applies the measure → change → re-measure
ratchet: each iteration selects one candidate from rubric findings, makes a
single bounded change, re-runs the full profiling pipeline under identical
conditions, and either accepts or discards the change based on quantified
evidence. The pipeline terminates when no feasible low-risk win remains.

This skill is the execution layer for the `perf-benchmark` diagnosis output.
It never profiles from scratch — it always consumes a findings file and a
before-run baseline.

## Use This Skill When

1. You have `perf-benchmark` findings (the `--findings-out` output) with at
   least one FAIL or WARN dimension.
2. You want to iteratively improve performance with one bounded change per
   iteration and quantified verification.
3. You need to maintain an auditable ledger of accepted performance wins.
4. You want a STOP gate that prevents constant-factor tuning when algorithmic
   scaling is the root cause.

## Inputs

The pipeline expects three inputs per iteration:

| Input | Source | Format |
|-------|--------|--------|
| **PERF findings** | `--findings-out` from `perf-benchmark` | JSON array of finding objects, `signal: "PERF"`, `leaf: "perf-benchmark"` |
| **Baseline summary** | `benchmark_summary.json` from the before-run | JSON object with `rubric`, `wall_time_mean`, `tier`, environment fingerprint |
| **Trend ledger** (optional) | `--baseline-ledger` from `perf-benchmark` | Append-only JSONL, one line per historical run |

The findings file is a JSON array of shared-schema PERF finding objects. Each
finding carries these keys (see `scripts/perf_benchmark/findings.py:
_build_finding` for the canonical shape):

| Key | Type | Example |
|-----|------|---------|
| `id` | string | deterministic SHA1 prefix |
| `leaf` | string | `"perf-benchmark"` |
| `signal` | string | `"PERF"` |
| `severity` | string | `"high"` (FAIL) or `"medium"` (WARN) |
| `path` | string | root path of the benchmark suite |
| `location` | object | `{line_start, line_end, symbol}` |
| `metric` | object | `{name, value, threshold}` — the measured metric |
| `evidence` | array | always `[]` in v0.2.0 |
| `confidence` | string | `"high"` |
| `suggested_action` | string | human-readable prescription |

The rubric dimension is **not** a direct finding field. It is inferred from
`metric.name` and the paired `benchmark_summary.json` rubric. For example,
`metric.name == "complexity_exponent"` or `"l1_miss_rate"` tells you which
dimension and sub-check produced the finding. Algorithmic Scaling findings
have metric names matching the six sub-checks:

`complexity_exponent`, `call_amplification`, `data_reuse`,
`write_amplification`, `allocation_churn`, `multiplicative_paths`.

The full mapping of metric names to rubric dimensions is:

| Rubric dimension | Metric names emitted |
|---|---|
| Algorithmic Scaling | `complexity_exponent`, `call_amplification`, `data_reuse`, `write_amplification`, `allocation_churn`, `multiplicative_paths` |
| Wall-Time Stability | `wall_time_cv` |
| CPU Efficiency | `top_fn_pct`, `IPC` |
| L1 Cache Efficiency | `l1_miss_rate` |
| Last-Level Cache | `ll_miss_rate` |
| Branch Prediction | `branch_mispred_rate` |
| Memory Profile | `peak_bytes`, `churn_peaks` |

The baseline summary must have been produced by the same `perf-benchmark`
pipeline version on the same machine with the same tier, sizes, and workload.
Environment fingerprint fields are compared to ensure comparability.

## Workflow

### Stage 1: Algorithmic STOP Gate

**Rule:** If any finding has `metric.name` matching one of the six algorithmic
sub-check names AND `severity == "high"` (which corresponds to rubric FAIL),
algorithm remediation is the **only** permissible candidate. No
constant-factor work (cache, branch, CPU, memory) is permitted until the
algorithmic finding is resolved.

The six algorithmic sub-check `metric.name` values are:
`complexity_exponent`, `call_amplification`, `data_reuse`,
`write_amplification`, `allocation_churn`, `multiplicative_paths`.

```
ALGORITHMIC_METRICS = {
    "complexity_exponent", "call_amplification", "data_reuse",
    "write_amplification", "allocation_churn", "multiplicative_paths"
}

IF any finding has metric.name in ALGORITHMIC_METRICS AND severity == "high":
    → ONLY algorithmic candidates are eligible
    → Skip all other metric.name groups
    → If no algorithmic change is feasible on the current evidence,
      stop with: "ALGORITHMIC_FAIL: must resolve complexity class before
      constant-factor tuning"
```

If algorithmic findings exist at `severity == "medium"` (rubric WARN) but
none at `"high"`, constant-factor candidates may be considered alongside
algorithmic candidates, but algorithmic candidates retain higher selection
priority.

If all six algorithmic sub-check names are absent from the findings (i.e.,
Algorithmic Scaling scored `"N/A"` — insufficient evidence), the pipeline
cannot make an algorithmic decision. Re-run `perf-benchmark` with `--tier
deep` or `--tier asm` to collect multi-size and allocation-churn evidence.

### Stage 2: Select Candidate

Run the candidate selection script (cwd is the repo root):

```bash
python perf-optimization/scripts/select_candidate.py \
  --findings /path/to/perf-findings.json \
  --out /path/to/candidate.json
```

The selector consumes the shared-schema PERF findings from `--findings` and
writes the selected candidate to `--out`. The C2 CLI contract is exactly
`--findings` and `--out`; it does not take `--summary` or `--ledger`.

The output shape is exactly:

```json
{
  "status": "ok",
  "candidate": {
    "id": "abc123...",
    "path": "src/hot_loop.py",
    "metric_name": "l1_miss_rate",
    "severity": "high",
    "ratio": 4.2,
    "stop_gate": false
  }
}
```

Fields: `id` is the finding's deterministic SHA1 prefix; `path` is the
production file associated with the finding; `metric_name` maps to a
rubric dimension via the table in the Inputs section; `severity` is
`"high"` (rubric FAIL) or `"medium"` (rubric WARN); `ratio` is
`metric.value / metric.threshold` (values > 1.0 exceed the rubric
threshold); `stop_gate` is `true` when the finding is an algorithmic
sub-check at `severity == "high"`.

The selector does **not** emit `files`, `technique`, or `rubric_dimension`.
The bounded file-set and technique are selected manually after Stage 2:
use `candidate.path` as the starting file-set and look up techniques in
`references/optimization-playbook.md` by matching `candidate.metric_name`
to the Dimension / metric column in the technique table.

**No-candidate outcome:** When no feasible low-risk candidate exists, the
selector writes:

```json
{"status": "no_candidates"}
```

and exits with code 1. The pipeline then terminates with the message:

> "evaluated, no feasible low-risk win"

along with evidence from the findings file.

The output is deterministic: same findings produce the same candidate
selection.

### Stage 3: One Bounded Change

Apply exactly **one** performance change per iteration:

- **Single dimension:** The change targets only the dimension matched from
  `candidate.metric_name` via the metric-to-dimension table in the Inputs
  section.
- **Single file-set:** Start with the production file from `candidate.path`;
  expand the file-set only when the technique (looked up in
  `references/optimization-playbook.md`) requires touching adjacent files.
  All changed files must be recorded so the verifier can check the diff.
- **TDD discipline:** Before editing an uncovered file, write behavior tests
  for its contract. Perf wins on untested code are not accepted (coverage gate,
  shared with code-health).
- **Suite green:** The full test suite must pass after the change and before
  re-profiling. Run:

```bash
python3 -m pytest tests/ -q
```

If the suite fails, fix the regression within the same single-file-set scope
before proceeding. If a fix would require a multi-file rewrite, discard the
candidate and record the blocked attempt.

**Batching rule:** Never mix an algorithmic change with a data-layout change
in one commit. Attribution dies when multiple dimensions change simultaneously.

### Stage 4: Verify

Re-run the SP6 `perf-benchmark` pipeline with the **same** tier, sizes, and
machine:

```bash
python scripts/perf_benchmark_pipeline.py \
  --root . \
  --tier <same-tier> \
  --sizes <same-sizes> \
  --target "<same-target>" \
  --out-dir /tmp/perf-verify \
  --max-cv 5.0 \
  --findings-out /tmp/perf-findings-after.json \
  --baseline-ledger /tmp/perf-ledger.jsonl
```

Then run the verification script:

```bash
python scripts/verify_win.py \
  --before /path/to/benchmark_summary_before.json \
  --after /tmp/perf-verify/benchmark_summary.json
```

**Acceptance criteria (ACCEPT):**

1. **p50 median win >= 5%:** The target dimension's primary metric shows a
   relative improvement of at least 5% at the median (p50).
2. **No noise-timing dimension:** Neither the before nor the after run has any
   timing-derived dimension scored `"N/A (noise)"`. If either run has noise,
   the measurement is invalid and the comparison is void.
3. **Environment fingerprint match:** The `environment` sections of both
   summaries match on the following five fields (from
   `_environment_fingerprint` in `scripts/perf_benchmark/reporting.py`):

   - `cpu_model`
   - `kernel`
   - `governor`
   - `smt`
   - `python_version`

   `timestamp_utc` and `load_avg_1m` are **excluded** from the comparison.
   The C3 verifier compares only these five keys — it does not compare RAM,
   cache topology, or any other prerequisites fields. A fingerprint mismatch
   on any of the five keys voids the comparison.
4. **Suite green:** The test suite passes in the after state.
5. **No regression >= 1 tier:** No other scored dimension drops by 1 or more
   rubric tiers (PASS → WARN, WARN → FAIL, PASS → FAIL).

If all five conditions hold, the result is `ACCEPT`. Otherwise, the result is
`REJECT`.

**On REJECT:** Discard the change entirely (revert the file-set to its
before state). Record the candidate, the reason for rejection, and the
measured numbers in the ledger so the same candidate is not re-selected.

### Stage 5: Ledger

After every `ACCEPT`, append the after-run to the trend ledger:

```bash
python scripts/perf_benchmark_pipeline.py \
  --root . \
  --tier <same-tier> \
  --sizes <same-sizes> \
  --target "<same-target>" \
  --out-dir /tmp/perf-accepted \
  --max-cv 5.0 \
  --findings-out /tmp/perf-findings-accepted.json \
  --baseline-ledger /tmp/perf-ledger.jsonl
```

The `--baseline-ledger` flag appends the current run and reports any vs-last
or vs-best tier regressions. Accepted runs form the evidence chain.

**Termination conditions:**

1. `select_candidate.py` returns an empty candidate → terminate with
   `"evaluated, no feasible low-risk win"` plus evidence.
2. The `--findings-out` array is empty (no FAIL or WARN dimensions remain,
   i.e., all rubric dimensions are PASS) → terminate with success.
3. A user-specified iteration limit is reached → terminate with partial status
   and remaining findings.
4. The algorithm gate cannot be passed and no algorithmic change is feasible →
   terminate with `"ALGORITHMIC_FAIL"`.

## Execution Discipline

This skill's execution discipline is defined in two cross-referenced documents:

- **`../references/perf-remediation-playbook.md`** (from the `perf-benchmark`
  skill): The measure → change → re-measure ratchet, standing rules (STOP gate,
  one dimension per batch, same-fingerprint comparison, >=5% ratchet, coverage
  gate, honest no-win), and dimension-specific verification procedures.

- **`references/optimization-playbook.md`** (from this skill): The technique
  catalogue organized by diagnostic tier and dimension, with first-line
  techniques and escalation paths. Look up the dimension selected in Stage 2
  to find the ordered list of applicable techniques.

Use the remediation playbook for *execution rules* and the optimization
playbook for *technique selection*. Both must agree before applying a change.

## Outputs

1. **Accepted changes** committed to the repository (one commit per iteration).
2. **Trend ledger** (`--baseline-ledger`) with one JSONL line per accepted run.
3. **Termination report** with final findings state and evidence chain.
4. **Rejection log** (implicit in the diff between findings iterations).

## References

1. [`references/optimization-playbook.md`](references/optimization-playbook.md): technique catalogue by diagnostic tier and dimension.
2. [`../references/perf-remediation-playbook.md`](../references/perf-remediation-playbook.md): execution discipline and standing rules.
3. [`../references/finding-schema.json`](../references/finding-schema.json): PERF findings schema consumed as input.
4. [`../scripts/perf_benchmark/ledger.py`](../scripts/perf_benchmark/ledger.py): append-only JSONL ledger library.
5. [`../scripts/perf_benchmark/findings.py`](../scripts/perf_benchmark/findings.py): PERF findings bridge and metric extraction.

## Quick Reference

```bash
# Full iteration loop (pseudo)
# cwd is the repo root; selector is in the perf-optimization skill
python perf-optimization/scripts/select_candidate.py \
  --findings /tmp/perf-findings.json \
  --out /tmp/candidate.json
# → candidate: {"status":"ok","candidate":{"id":"...","path":"src/hot_loop.py","metric_name":"l1_miss_rate","severity":"high","ratio":4.2,"stop_gate":false}}
#   or: {"status":"no_candidates"} → terminate "evaluated, no feasible low-risk win"

# Apply the change (one file-set from candidate.path, one dimension from candidate.metric_name)
# Run tests
python3 -m pytest tests/ -q

# Re-profile with same parameters
python scripts/perf_benchmark_pipeline.py --root . --tier deep --sizes 10000,100000 --target "python -m benchmark_entrypoint {SIZE}" --out-dir /tmp/perf-verify --max-cv 5.0 --findings-out /tmp/perf-findings-after.json --baseline-ledger /tmp/perf-ledger.jsonl

# Verify the win (compares cpu_model, kernel, governor, smt, python_version)
python scripts/verify_win.py --before /tmp/before_summary.json --after /tmp/perf-verify/benchmark_summary.json
# → ACCEPT or REJECT

# If ACCEPT: commit, then loop back to Stage 1
# If REJECT: revert, record rejection, loop back to Stage 2
```
