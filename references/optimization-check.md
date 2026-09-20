# Optimization Check (internal)

This is not a discoverable skill. It details the authorized-change loop of
the `perf-benchmark` skill: consume benchmark findings, make one bounded
change, re-measure identically, and accept only quantified wins.

## Inputs

- PERF findings JSON from `perf-benchmark --findings-out`.
- The before-run `benchmark_summary.json` (with its `workload` block).
- Optional trend ledger from `--baseline-ledger`.
- A green functional test suite for the repository, with its log saved.

PERF findings use shared-schema fields including `id`, `leaf`, `signal`,
`severity`, `path`, `location`, `metric`, `evidence`, `confidence`, and
`suggested_action`. `metric.name` maps the finding to the rubric dimension.

Algorithmic metric names are `complexity_exponent`, `call_amplification`,
`data_reuse`, `write_amplification`, `allocation_churn`, and
`multiplicative_paths`. A high-severity algorithmic finding is a STOP gate:
algorithmic remediation is the only eligible work until it is resolved.

## Select

```bash
perf-select-candidate --findings /tmp/perf-findings.json --out /tmp/candidate.json
```

The selector writes either `{"status": "ok", "candidate": {...}}` or
`{"status": "no_candidates"}` (exit 1). `no_candidates` is a valid terminal
outcome: record `evaluated, no feasible low-risk win`.

## Change

Apply exactly one performance change per iteration.

- Target one rubric dimension from `candidate.metric_name`.
- Start with `candidate.path`; expand only when the technique requires it.
- Add behavior tests before touching uncovered production code.
- Run the full test suite before profiling; save its log.
- Do not mix algorithmic, data-layout, cache, branch, and CPU changes.

Use `optimization-playbook.md` for technique selection and
`perf-remediation-playbook.md` for execution discipline.

## Verify

Re-run the same benchmark shape: same tier, sizes, target, root, machine.
Then compare summaries:

```bash
perf-verify-win \
  --before /path/to/before/benchmark_summary.json \
  --after /path/to/after/benchmark_summary.json \
  --suite-exit-code 0 \
  --suite-evidence /path/to/suite-record.json \
  --objective wall-time \
  --ledger /path/to/perf-ledger.jsonl \
  --out /tmp/verdict.json
```

`accept` requires all of: comparable workload (tier, sizes, target, repeats,
noise gate, complexity inputs; >= 2 strict-int wall-time samples per run);
matching environment fingerprint with present non-empty keys; non-empty
rubrics with matching dimension sets and typed tiers; finite timing samples;
no `N/A (noise)` timing in either run; no added/dropped/scored-dimension
tier change; and a green suite proven by bound evidence.

Functional evidence is a structured JSON record, not an arbitrary log file:

```json
{
  "command": "pytest -q",
  "exit_code": 0,
  "passed": 12,
  "failed": 0,
  "status": "pass",
  "target": "python -m benchmark_entrypoint {SIZE}",
  "root": "/path/to/repo",
  "revision": "<git SHA, when known>"
}
```

`exit_code` (int) must equal `--suite-exit-code`; green means exit 0 with no
failures; at least one of `target`/`root`/`revision` must match the after
run. Anything else is `unverified` (best verdict: `advisory`,
measurement-only) or malformed. `--suite-command "..."` runs the suite under
the verifier instead and records the observed result; `--require-verified`
turns unverified comparisons into `reject`.

Objective policy: `--min-win` (default 5.0) is the wall-time p50 convention
and is configurable, not a universal rule. For `--objective memory` choose
the peak-improvement threshold explicitly. For `--objective scaling` demand
strict exponent improvement. Wall-time or exponent collapse rejects under
any objective; a deliberate cross-objective tradeoff (e.g. slower but much
leaner) is a user decision, recorded with its rationale -- the verifier
stays conservative and rejects it by default.

Verdicts: `accept` (exit 0), `reject` (exit 1), `advisory` (exit 3,
measurements pass but functionality unproven), `error` (exit 2, malformed
input with the uniform verdict schema).

Reject means revert the change and keep the evidence. Record accepted wins
and honest no-win outcomes in the ledger when the project uses one. Whether
anything is committed follows the user's repository workflow; this skill
never commits by itself.

## Outputs

- `candidate.json`: selected candidate or no-candidate status.
- `verdict.json`: `accept`, `reject`, or `error`, with reasons and the
  functional-verification label.
