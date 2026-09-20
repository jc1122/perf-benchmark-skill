#!/usr/bin/env python3
"""Deterministic win-verdict check for before/after benchmark comparisons.

Consumes two benchmark_summary.json files (before + after), a test-suite
exit code, and functional-verification evidence to decide ACCEPT, REJECT,
ADVISORY, or ERROR.

Verdicts (exit codes):
- ``accept`` (0): every gate passed AND the suite is proven green by bound
  evidence. This is the only verdict that endorses acting on the win.
- ``reject`` (1): at least one gate failed (see ``reasons``).
- ``error`` (2): malformed input or invocation; same schema as normal
  verdicts with null sentinels, never a bare shape.
- ``advisory`` (3): measurement gates passed but functional status is
  ``unverified`` (no bound green evidence). A measurement-only signal,
  explicitly NOT functional proof; re-run with evidence before acting.

Acceptance requires ALL of:
- comparable workload (same tier, sizes, target/binary, method, repeats,
  noise gate, and complexity inputs; >=2 wall-time samples on both sides),
- matching environment fingerprint on the 5 compared keys, where every key
  must be a present non-empty string in BOTH runs,
- non-empty rubric dimensions with matching dimension sets and typed tiers
  (added/dropped dimensions and untyped tiers never pass silently),
- finite timing samples (NaN/inf rejected as malformed),
- objective improvement plus cross-objective no-collapse guards,
- no N/A (noise) timing dimension in either run,
- no scored-dimension tier drop,
- a green suite proven by evidence bound to the after run
  (``--suite-evidence`` structured record or ``--suite-command`` live run).

Usage:
    python verify_win.py \
        --before summary_before.json \
        --after summary_after.json \
        --suite-exit-code 0 \
        --suite-evidence /path/to/suite-record.json \
        --objective wall-time \
        --min-win 5.0 \
        --ledger perf-ledger.jsonl \
        --out verdict.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# -- fingerprint keys compared exactly --
_FINGERPRINT_KEYS = ("cpu_model", "kernel", "governor", "smt", "python_version")

# -- tier order for drop detection --
_SUCCESS_TIER = "PASS"
TIER_RANK: dict[str, int] = {"FAIL": 0, "WARN": 1, _SUCCESS_TIER: 2}

# noise-tier literal (exact string match required)
_NOISE_TIER = "N/A (noise)"

# binding keys linking a suite record to the after run
_BINDING_KEYS = ("target", "binary", "root", "revision")

# suite-record status values that assert green
_GREEN_STATUSES = {"pass", "passed", "ok", "success", "green"}

# workload comparability vocabularies (pipeline argparse choices)
_VALID_TIERS = {"fast", "medium", "deep", "asm"}
_VALID_COMPLEXITIES = {"linear", "nlogn", "quadratic"}

OBJECTIVES = ("wall-time", "memory", "scaling")

EXIT_CODES = {"accept": 0, "reject": 1, "error": 2, "advisory": 3}


# ----------------------------------------------------------------- validation


def _is_finite_number(value: Any) -> bool:
    """True for real int/float values that are finite (excludes bool/NaN/inf)."""
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float)) and math.isfinite(value)


def _is_strict_int(value: Any) -> bool:
    """True for genuine ints (excludes bool)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _load_summary(path: str) -> dict[str, Any]:
    """Read a summary JSON file. Returns the parsed dict.

    Raises OSError if the file cannot be read.
    Raises json.JSONDecodeError / ValueError if the content is invalid,
    including empty rubric dimensions, untyped tiers, and non-finite
    timing samples.
    """
    raw = Path(path).read_text()
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"summary root must be a JSON object, got {type(data).__name__}")
    rubric = data.get("rubric")
    if not isinstance(rubric, dict):
        raise ValueError("summary.rubric is missing or not a JSON object")
    dims = rubric.get("dimensions")
    if not isinstance(dims, dict):
        raise ValueError("summary.rubric.dimensions is missing or not a JSON object")
    if not dims:
        raise ValueError("summary.rubric.dimensions is empty: no measured dimensions")
    for name, dim in dims.items():
        if not isinstance(dim, dict):
            raise ValueError(f"summary.rubric.dimensions[{name!r}] is not a JSON object")
        tier = dim.get("tier")
        if not isinstance(tier, str) or not tier:
            raise ValueError(f"summary.rubric.dimensions[{name!r}].tier must be a non-empty string")
    wpt = data.get("wall_time_percentiles")
    if not isinstance(wpt, dict):
        raise ValueError("summary.wall_time_percentiles is missing or not a JSON object")
    p50 = wpt.get("p50")
    if not _is_finite_number(p50) or float(p50) <= 0:
        raise ValueError(
            "summary.wall_time_percentiles.p50 must be a strictly positive finite number"
        )
    for key in ("p95", "p99"):
        if key in wpt and not _is_finite_number(wpt[key]):
            raise ValueError(f"summary.wall_time_percentiles.{key} is not a finite number")
    env = data.get("environment")
    if not isinstance(env, dict):
        raise ValueError("summary.environment is missing or not a JSON object")
    return data


def _dimension_tiers(rubric: dict[str, Any]) -> dict[str, str]:
    """Extract {dimension_name: tier} from a validated rubric dict."""
    dims = rubric.get("dimensions", {})
    return {name: dim["tier"] for name, dim in dims.items()}


# ----------------------------------------------------- check logic functions


def _check_median(before_p50: float, after_p50: float, min_win: float) -> tuple[float, list[str]]:
    """Compute median_win_percent and check against *min_win*."""
    if before_p50 == 0.0:
        return 0.0, ["median"]
    win = round((before_p50 - after_p50) / before_p50 * 100.0, 6)
    if win < min_win:
        return win, ["median"]
    return win, []


def _check_noise(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Reject if any rubric dimension in before or after has tier == 'N/A (noise)'."""
    reasons: list[str] = []
    for _label, summary in (("before", before), ("after", after)):
        rubric = summary.get("rubric", {})
        dims = rubric.get("dimensions", {})
        for _name, dim in dims.items():
            if isinstance(dim, dict) and dim.get("tier") == _NOISE_TIER:
                reasons.append("noise")
                break
    return reasons


def _fingerprint_value(env: dict[str, Any], key: str) -> str | None:
    """Return the stripped string value for *key*, or None when absent/empty."""
    value = env.get(key)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _check_fingerprint(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Check that *before* and *after* environments match on the 5
    fingerprint keys.  timestamp_utc and load_avg_1m are excluded.

    Every compared key must be a present, non-empty string in BOTH runs:
    two missing (or empty, or non-string) values never count as equal.
    """
    before_env = before.get("environment", {})
    after_env = after.get("environment", {})
    if not isinstance(before_env, dict) or not isinstance(after_env, dict):
        return ["fingerprint"]
    for key in _FINGERPRINT_KEYS:
        before_val = _fingerprint_value(before_env, key)
        after_val = _fingerprint_value(after_env, key)
        if before_val is None or after_val is None or before_val != after_val:
            return ["fingerprint"]
    return []


def _workload_of(summary: dict[str, Any]) -> dict[str, Any] | None:
    """Return the workload comparability block, or None when absent."""
    workload = summary.get("workload")
    return workload if isinstance(workload, dict) else None


def _normalize_size(value: Any) -> int:
    """Strict input-size normalization: int, integral float, or digit string.

    Bool, non-integral floats, and non-digit strings are rejected so that
    ``[1000]``, ``[1000.0]``, and ``["1000"]`` compare equal while
    ``["1000.0"]``, ``[true]``, or ``[null]`` never silently pass.
    """
    if isinstance(value, bool):
        raise ValueError(f"input size must not be boolean: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise ValueError(f"input size must be integral: {value!r}")
    if isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        return int(value.strip())
    raise ValueError(f"input size has unsupported type: {value!r}")


def _normalize_sizes(value: Any) -> list[int]:
    """Normalize a sizes list, or raise ValueError when it is not typed."""
    if not isinstance(value, list) or not value:
        raise ValueError("sizes must be a non-empty list")
    return [_normalize_size(item) for item in value]


def _check_workload(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Reject when the two runs are not comparable: missing workload block,
    missing keys, unknown tiers, differing tier / sizes / target / binary /
    method / repeats / noise-gate / complexity inputs, or symmetrically
    invalid typed inputs (shared nonsense never counts as comparable)."""
    before_wl = _workload_of(before)
    after_wl = _workload_of(after)
    if before_wl is None or after_wl is None:
        return ["workload"]
    for key in ("tier", "target", "binary", "method"):
        if key not in before_wl or key not in after_wl:
            return ["workload"]
        # None == None is comparable (e.g. both runs have no --binary);
        # a missing key above is what counts as incomparable metadata.
        if before_wl[key] != after_wl[key]:
            return ["workload"]
    tier = before_wl.get("tier")
    if not isinstance(tier, str) or not tier:
        return ["workload"]
    if before_wl.get("tier") not in _VALID_TIERS or after_wl.get("tier") not in _VALID_TIERS:
        return ["workload"]
    try:
        if _normalize_sizes(before_wl.get("sizes")) != _normalize_sizes(after_wl.get("sizes")):
            return ["workload"]
    except ValueError:
        return ["workload"]
    for key in ("time_repeats", "max_cv", "expected_complexity"):
        if key not in before_wl or key not in after_wl:
            return ["workload"]
        if before_wl[key] != after_wl[key]:
            return ["workload"]
    # Typed validation even when both sides agree: symmetric gibberish
    # (e.g. both time_repeats "banana") must reject, not pass on equality.
    before_repeats = before_wl.get("time_repeats")
    after_repeats = after_wl.get("time_repeats")
    if not (
        _is_strict_int(before_repeats)
        and before_repeats >= 1
        and _is_strict_int(after_repeats)
        and after_repeats >= 1
    ):
        return ["workload"]
    before_cv = before_wl.get("max_cv")
    after_cv = after_wl.get("max_cv")
    if not (
        _is_finite_number(before_cv)
        and float(before_cv) >= 0
        and _is_finite_number(after_cv)
        and float(after_cv) >= 0
    ):
        return ["workload"]
    if (
        before_wl.get("expected_complexity") not in _VALID_COMPLEXITIES
        or after_wl.get("expected_complexity") not in _VALID_COMPLEXITIES
    ):
        return ["workload"]
    return []


def _check_samples(before: dict[str, Any], after: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Reject when either run has fewer than 2 wall-time samples.

    ``sample_count`` must be a strict int (bool excluded) >= 2 on BOTH
    sides. Missing, non-int, or <2 counts reject with reason ``evidence``;
    the human-readable detail rides along in warnings. A single sample
    (or none) can never prove a median win.
    """
    reasons: list[str] = []
    warnings: list[str] = []
    for label, summary in (("before", before), ("after", after)):
        workload = _workload_of(summary) or {}
        count = workload.get("sample_count")
        if not _is_strict_int(count) or count < 2:
            reasons.append("evidence")
            warnings.append(
                f"{label} workload sample_count is {count!r}: "
                "need a strict int >= 2 wall-time samples to compare medians"
            )
    return reasons, warnings


def _resolve_peak_bytes(summary: dict[str, Any]) -> float | None:
    """Resolve a comparable memory peak (massif > tracemalloc > rubric)."""
    for key in ("massif_peak_bytes", "tracemalloc_peak_bytes"):
        value = summary.get(key)
        if _is_finite_number(value) and float(value) > 0:
            return float(value)
    try:
        dims = summary.get("rubric", {}).get("dimensions", {})
        peak = dims.get("Memory Profile", {}).get("peak_bytes")
    except AttributeError:
        peak = None
    if _is_finite_number(peak) and float(peak) > 0:  # type: ignore[arg-type]
        return float(peak)  # type: ignore[arg-type]
    return None


def _check_memory_objective(
    before: dict[str, Any], after: dict[str, Any], min_win: float
) -> tuple[float | None, list[str]]:
    """Compare memory peaks. Returns (win_percent_or_None, reasons)."""
    before_peak = _resolve_peak_bytes(before)
    after_peak = _resolve_peak_bytes(after)
    if before_peak is None or after_peak is None:
        return None, ["evidence"]
    win = round((before_peak - after_peak) / before_peak * 100.0, 6)
    if win < min_win:
        return win, ["objective"]
    return win, []


def _complexity_exponent(summary: dict[str, Any]) -> float | None:
    """Extract the fitted complexity exponent k, or None when unavailable."""
    try:
        dims = summary.get("rubric", {}).get("dimensions", {})
        k = (
            dims.get("Algorithmic Scaling", {})
            .get("sub_checks", {})
            .get("complexity_exponent", {})
            .get("k")
        )
    except AttributeError:
        return None
    return float(k) if _is_finite_number(k) else None


def _check_dimensions(before_dims: dict[str, str], after_dims: dict[str, str]) -> list[str]:
    """Reject added/dropped dimensions and scored-vs-unmeasured mismatches.

    Both runs must measure the same dimension set. A dimension that is
    unmeasured (any tier outside PASS/WARN/FAIL) on BOTH sides is comparable
    and passes; scored on one side and unmeasured on the other rejects, so a
    dropped FAIL (or a freshly added FAIL) can never hide behind absence.
    """
    if set(before_dims) != set(after_dims):
        return ["tier"]
    for name in before_dims:
        before_scored = before_dims[name] in TIER_RANK
        after_scored = after_dims[name] in TIER_RANK
        if before_scored != after_scored:
            return ["tier"]
    return []


def _check_tier_drops(before_dims: dict[str, str], after_dims: dict[str, str]) -> list[str]:
    """Reject if any dimension tier drops by >=1 step (PASS > WARN > FAIL).

    Only jointly scored dimensions reach this check (see
    ``_check_dimensions``); N/A tiers are incomparable here and N/A (noise)
    is already handled by the noise check.
    """
    for name, after_tier in after_dims.items():
        before_tier = before_dims.get(name)
        if before_tier is None:
            continue
        if after_tier not in TIER_RANK or before_tier not in TIER_RANK:
            continue
        if TIER_RANK[before_tier] - TIER_RANK[after_tier] >= 1:
            return ["tier"]
    return []


def _check_suite(suite_exit_code: int) -> list[str]:
    """Reject if suite-exit-code is non-zero."""
    if suite_exit_code != 0:
        return ["suite"]
    return []


# ------------------------------------------------------- functional evidence


def _after_identity(after: dict[str, Any]) -> dict[str, Any]:
    """Identity of the after run that a suite record must bind to."""
    workload = _workload_of(after) or {}
    return {
        "target": workload.get("target"),
        "binary": workload.get("binary"),
        "root": after.get("root"),
        "revision": workload.get("revision"),
    }


def _preload_evidence(path: str, suite_exit_code: int) -> dict[str, Any]:
    """Load a structured suite record, or raise ValueError.

    A record must be a JSON object carrying an ``exit_code`` int (bool
    excluded) equal to the supplied ``--suite-exit-code``. Arbitrary bytes,
    non-JSON, non-objects, missing exit codes, and exit-code mismatches are
    malformed invocations, never silent ``verified`` labels.
    """
    try:
        record = json.loads(Path(path).read_text())
    except OSError as exc:
        raise ValueError(f"suite evidence cannot be read: {exc}") from None
    except json.JSONDecodeError as exc:
        raise ValueError(f"suite evidence is not JSON: {exc}") from None
    if not isinstance(record, dict):
        raise ValueError("suite evidence must be a JSON object (test record)")
    exit_code = record.get("exit_code")
    if not _is_strict_int(exit_code):
        raise ValueError("suite evidence record needs an int 'exit_code'")
    if exit_code != suite_exit_code:
        raise ValueError(
            "suite evidence exit_code "
            f"{exit_code} disagrees with --suite-exit-code {suite_exit_code}"
        )
    return record


def _validate_evidence_record(
    record: dict[str, Any], after: dict[str, Any]
) -> tuple[str, list[str], dict[str, Any] | None]:
    """Validate a preloaded record against the after run.

    Returns (status, reasons, verified_record_or_None) where status is
    ``verified`` or ``unverified``. Verified needs a green record
    (exit 0, no failures, green status when those keys are present) AND at
    least one binding key (target/binary/root/revision) matching the after
    run. A bound-but-red record yields a ``suite`` reason; a binding
    mismatch yields ``evidence``; an unbound record stays ``unverified``.
    When the after run carries a revision, a record omitting it cannot
    verify: a stale pre-change record at the same root/target must never
    endorse a changed candidate.
    """
    identity = _after_identity(after)
    if identity.get("revision") is not None and record.get("revision") is None:
        return "unverified", ["evidence"], None
    exit_code = record["exit_code"]
    failed = record.get("failed")
    status = record.get("status")
    green = (
        exit_code == 0
        and (failed is None or (_is_strict_int(failed) and failed == 0))
        and (
            status is None
            or (isinstance(status, str) and status.strip().lower() in _GREEN_STATUSES)
        )
    )
    bound = 0
    for key in _BINDING_KEYS:
        claim = record.get(key)
        if claim is None:
            continue
        actual = identity.get(key)
        if actual is None:
            continue  # after run carries no such identity; cannot bind on it
        if claim != actual:
            return "unverified", ["evidence"], None
        bound += 1
    verified_record: dict[str, Any] = {
        "status": "verified",
        "exit_code": exit_code,
        "binding": {k: record[k] for k in _BINDING_KEYS if record.get(k) is not None},
    }
    for passthrough in ("command", "output_tail"):
        if record.get(passthrough) is not None:
            verified_record[passthrough] = record[passthrough]
    if not green:
        return "verified", ["suite"], verified_record
    if bound < 1:
        return "unverified", [], None
    return "verified", [], verified_record


def _cwd_revision(directory: str) -> str | None:
    """Best-effort git revision of the directory actually executed in."""
    try:
        proc = subprocess.run(
            ["git", "-C", directory, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return (proc.stdout or "").strip() or None


def _run_suite_command(
    command: str,
    after: dict[str, Any],
    suite_exit_code: int,
    timeout: float,
) -> tuple[dict[str, Any], list[str]]:
    """Run *command* and build the suite record from the observed result.

    The command runs with the after-run root as cwd; a missing root or a
    root that is not a directory is a malformed invocation (running the
    wrong tree under the verifier's cwd must never claim after identity).
    The record carries the actual executed-tree revision, so a stale tree
    mismatches the after revision at validation time instead of verifying.
    An observed exit code disagreeing with ``--suite-exit-code`` is also
    malformed. Returns (record, warnings).
    """
    root = after.get("root")
    if not isinstance(root, str) or not root:
        raise ValueError("suite command needs after-run root: missing or empty root")
    if not Path(root).is_dir():
        raise ValueError(f"suite command needs after-run root: not a directory: {root}")
    cwd = root
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"suite command timed out after {timeout}s: {command}") from exc
    if proc.returncode != suite_exit_code:
        raise ValueError(
            "suite command exit "
            f"{proc.returncode} disagrees with --suite-exit-code {suite_exit_code}"
        )
    tail = (proc.stdout + (proc.stderr or ""))[-2000:]
    identity = _after_identity(after)
    actual_revision = _cwd_revision(cwd)
    record: dict[str, Any] = {
        "command": command,
        "exit_code": proc.returncode,
        "status": "pass" if proc.returncode == 0 else "fail",
        "output_tail": tail,
    }
    for key in ("target", "binary", "root"):
        value = identity.get(key)
        if value is not None:
            record[key] = value
    # Revision is the observed tree's, never the claimed after-run value:
    # a stale tree then mismatches (or omits, triggering the omission
    # guard) at validation instead of silently verifying.
    if actual_revision is not None:
        record["revision"] = actual_revision
    return record, []


# ------------------------------------------------------------ ledger reading


def _load_ledger_entries(ledger_path: str) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    lpath = Path(ledger_path)
    if not lpath.exists():
        warnings.append(f"Ledger file not found: {ledger_path}")
        return [], warnings

    entries: list[dict[str, Any]] = []
    for lineno, raw in enumerate(lpath.read_text().splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            entries.append(json.loads(stripped))
        except json.JSONDecodeError:
            warnings.append(f"Skipped corrupt line {lineno} in {ledger_path}")
    return entries, warnings


def _ledger_dimension_mismatch(
    last_dims: dict[str, Any], after_dims: dict[str, str]
) -> list[dict[str, Any]]:
    """Report ledger dimension-set drift (added/dropped vs the last entry)."""
    mismatch: list[dict[str, Any]] = []
    for name in sorted(set(last_dims) | set(after_dims)):
        ref_tier = last_dims.get(name)
        cur_tier = after_dims.get(name)
        if (ref_tier is None) != (cur_tier is None):
            mismatch.append(
                {
                    "dimension": name,
                    "previous_tier": ref_tier,
                    "current_tier": cur_tier,
                }
            )
    return mismatch


def _ledger_regressions(
    entries: list[dict[str, Any]], after_dims: dict[str, str]
) -> list[dict[str, Any]]:
    if not entries:
        return []

    last = entries[-1]
    last_dims: dict[str, str] = last.get("dimensions", {}) or {}
    regressions: list[dict[str, Any]] = []
    for name, after_tier in after_dims.items():
        ref_tier = last_dims.get(name)
        if ref_tier is None:
            continue
        if after_tier not in TIER_RANK or ref_tier not in TIER_RANK:
            continue
        drop = TIER_RANK[ref_tier] - TIER_RANK[after_tier]
        if drop >= 1:
            regressions.append(
                {
                    "dimension": name,
                    "previous_tier": ref_tier,
                    "current_tier": after_tier,
                    "drop": drop,
                }
            )
    return regressions


def _read_ledger(ledger_path: str, after_dims: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    """Read the JSONL ledger, compare after dimensions against the last entry.

    Returns (vs_last_dict, warnings).  vs_last_dict is ALWAYS a dict:
      - {} when no entries exist or nothing drifted
      - {"regressions": [...]} when tier drops are detected
      - {"dimension_mismatch": [...]} when dimensions were added/dropped
      - both keys when both drift kinds are detected

    Corrupt lines produce a warning and are skipped.
    A missing ledger file produces a warning and {}.
    """
    entries, warnings = _load_ledger_entries(ledger_path)
    if not entries:
        return {}, warnings
    last_dims: dict[str, Any] = entries[-1].get("dimensions", {}) or {}
    vs_last: dict[str, Any] = {}
    regressions = _ledger_regressions(entries, after_dims)
    if regressions:
        vs_last["regressions"] = regressions
    mismatch = _ledger_dimension_mismatch(last_dims, after_dims)
    if mismatch:
        vs_last["dimension_mismatch"] = mismatch
    return vs_last, warnings


# -------------------------------------------------------------- orchestration


def _build_verdict(
    before: dict[str, Any],
    after: dict[str, Any],
    suite_exit_code: int,
    min_win: float,
    ledger_path: str | None,
    objective: str = "wall-time",
    evidence_record: dict[str, Any] | None = None,
    require_verified: bool = False,
) -> dict[str, Any]:
    """Run all checks in fixed order and build the verdict dict."""

    before_p50 = float(before["wall_time_percentiles"]["p50"])
    after_p50 = float(after["wall_time_percentiles"]["p50"])

    before_dims = _dimension_tiers(before.get("rubric", {}))
    after_dims = _dimension_tiers(after.get("rubric", {}))

    median_win, _ = _check_median(before_p50, after_p50, min_win)
    noise_reasons = _check_noise(before, after)
    fingerprint_reasons = _check_fingerprint(before, after)
    workload_reasons = _check_workload(before, after)
    sample_reasons, sample_warnings = _check_samples(before, after)
    dimension_reasons = _check_dimensions(before_dims, after_dims)
    tier_reasons = _check_tier_drops(before_dims, after_dims)
    suite_reasons = _check_suite(suite_exit_code)

    # -- objective gate plus cross-objective no-collapse guards --
    before_k = _complexity_exponent(before)
    after_k = _complexity_exponent(after)
    objective_delta: float | None = median_win
    objective_reasons: list[str] = []
    memory_win: float | None = None
    k_delta: float | None = None
    if objective == "memory":
        memory_win, objective_reasons = _check_memory_objective(before, after, min_win)
        objective_delta = memory_win
        if after_p50 > before_p50:
            objective_reasons = objective_reasons + ["objective"]  # wall-time collapse
        if (
            before_k is not None
            and after_k is not None
            and after_k > before_k
            and "objective" not in objective_reasons
        ):
            objective_reasons = objective_reasons + ["objective"]  # exponent worsened
    elif objective == "scaling":
        if before_k is None or after_k is None:
            k_delta, objective_reasons = None, ["evidence"]
        else:
            k_delta = round(before_k - after_k, 6)
            if k_delta <= 0:
                objective_reasons = ["objective"]  # scaling needs strict improvement
        objective_delta = k_delta
        if after_p50 > before_p50 and "objective" not in objective_reasons:
            objective_reasons = objective_reasons + ["objective"]  # wall-time collapse
    else:
        _win, median_reasons = _check_median(before_p50, after_p50, min_win)
        objective_reasons = median_reasons
        if (
            before_k is not None
            and after_k is not None
            and after_k > before_k
            and "objective" not in objective_reasons
        ):
            objective_reasons = objective_reasons + ["objective"]  # exponent worsened

    # -- functional evidence: verified record or explicitly unverified --
    functional = "unverified"
    evidence_reasons: list[str] = []
    verified_record: dict[str, Any] | None = None
    if evidence_record is not None:
        functional, evidence_reasons, verified_record = _validate_evidence_record(
            evidence_record, after
        )
        if functional == "unverified" and require_verified:
            evidence_reasons = evidence_reasons + ["suite"]
    elif require_verified:
        evidence_reasons = ["suite"]

    all_reasons = (
        objective_reasons
        + noise_reasons
        + fingerprint_reasons
        + workload_reasons
        + sample_reasons
        + dimension_reasons
        + tier_reasons
        + suite_reasons
        + evidence_reasons
    )

    if all_reasons:
        verdict = "reject"
    elif functional == "verified":
        verdict = "accept"
    else:
        # Measurement gates passed but nothing proves the suite: an
        # explicitly advisory measurement-only outcome, never an accept.
        verdict = "advisory"

    result: dict[str, Any] = {
        "verdict": verdict,
        "median_win_percent": median_win,
        "reasons": all_reasons or [],
        "vs_last": {},
        "objective": objective,
        "objective_delta": objective_delta,
        "functional_verification": functional,
        "suite_exit_code": suite_exit_code,
    }
    if memory_win is not None:
        result["memory_win_percent"] = memory_win
    if k_delta is not None:
        result["complexity_delta_k"] = k_delta
    if verified_record is not None:
        result["suite_evidence"] = verified_record

    warnings: list[str] = list(sample_warnings)
    if functional == "unverified":
        warnings.append(
            "functional verification record absent or unbound: "
            "this verdict is measurement-only, not functional proof"
        )
    if ledger_path:
        vs_last_dict, ledger_warnings = _read_ledger(ledger_path, after_dims)
        result["vs_last"] = vs_last_dict
        warnings.extend(ledger_warnings)
    if warnings:
        result["warnings"] = warnings

    return result


def _write_output(payload: dict[str, Any], out_path: str) -> str:
    """Serialize *payload* to deterministic JSON, write to *out_path*, and
    print to stdout.  Returns the JSON string."""
    json_str = json.dumps(payload, sort_keys=True)
    print(json_str)
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json_str + "\n")
    return json_str


# --------------------------------------------------------------------- CLI


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic win-verdict check for benchmark before/after comparisons"
    )
    parser.add_argument(
        "--before", required=True, type=str, help="Before-run benchmark_summary.json"
    )
    parser.add_argument("--after", required=True, type=str, help="After-run benchmark_summary.json")
    parser.add_argument("--suite-exit-code", required=True, type=int, help="Test suite exit code")
    parser.add_argument(
        "--suite-evidence",
        type=str,
        default=None,
        help="Path to a structured JSON suite record "
        "(needs int 'exit_code' plus at least one binding key: "
        "target/binary/root/revision matching the after run). "
        "Without bound green evidence the best possible verdict is 'advisory'.",
    )
    parser.add_argument(
        "--suite-command",
        type=str,
        default=None,
        help="Test command the verifier runs itself (after-run root as cwd); "
        "the observed exit code is recorded. Mutually exclusive with "
        "--suite-evidence.",
    )
    parser.add_argument(
        "--suite-timeout",
        type=float,
        default=600.0,
        help="Timeout in seconds for --suite-command (default: 600).",
    )
    parser.add_argument(
        "--require-verified",
        action="store_true",
        help="Reject (reason 'suite') instead of 'advisory' when no valid "
        "bound green evidence is attached.",
    )
    parser.add_argument(
        "--objective",
        choices=list(OBJECTIVES),
        default="wall-time",
        help="Measured objective under comparison (default: wall-time). "
        "memory compares peak bytes; scaling needs strict exponent "
        "improvement (no percent rule). Cross-objective collapse "
        "(wall-time or exponent worsening) rejects under any objective.",
    )
    parser.add_argument(
        "--min-win",
        type=float,
        default=5.0,
        help="Minimum improvement pct for wall-time p50 or memory peak "
        "(default: 5.0, the wall-time convention; choose explicitly per "
        "objective -- it is not a universal rule for unrelated metrics).",
    )
    parser.add_argument(
        "--ledger", type=str, default=None, help="Optional append-only JSONL ledger"
    )
    parser.add_argument("--out", required=True, type=str, help="Path for verdict JSON output")
    return parser


def _error_payload(warning: str, objective: str, suite_exit_code: int) -> dict[str, Any]:
    """Uniform error verdict: same keys as a normal verdict, null sentinels."""
    return {
        "verdict": "error",
        "median_win_percent": 0.0,
        "reasons": ["malformed"],
        "vs_last": {},
        "objective": objective,
        "objective_delta": None,
        "functional_verification": "unverified",
        "suite_exit_code": suite_exit_code,
        "warnings": [warning],
    }


def _load_checked_summary(
    path: str, label: str, out_path: str, objective: str, suite_exit_code: int
) -> tuple[dict[str, Any], int]:
    try:
        return _load_summary(path), 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _write_output(
            _error_payload(f"{label} summary error: {exc}", objective, suite_exit_code),
            out_path,
        )
        return {}, 2


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.objective not in OBJECTIVES:
        _write_output(
            _error_payload(
                f"invocation error: unknown objective: {args.objective}",
                str(args.objective),
                args.suite_exit_code,
            ),
            args.out,
        )
        return 2
    if not math.isfinite(args.min_win):
        _write_output(
            _error_payload(
                "invocation error: --min-win must be a finite number",
                args.objective,
                args.suite_exit_code,
            ),
            args.out,
        )
        return 2
    if not math.isfinite(args.suite_timeout) or args.suite_timeout <= 0:
        _write_output(
            _error_payload(
                "invocation error: --suite-timeout must be a positive finite number",
                args.objective,
                args.suite_exit_code,
            ),
            args.out,
        )
        return 2
    if args.suite_evidence and args.suite_command:
        _write_output(
            _error_payload(
                "invocation error: --suite-evidence and --suite-command are mutually exclusive",
                args.objective,
                args.suite_exit_code,
            ),
            args.out,
        )
        return 2

    before, exit_code = _load_checked_summary(
        args.before, "Before", args.out, args.objective, args.suite_exit_code
    )
    if exit_code:
        return exit_code
    after, exit_code = _load_checked_summary(
        args.after, "After", args.out, args.objective, args.suite_exit_code
    )
    if exit_code:
        return exit_code

    evidence_record: dict[str, Any] | None = None
    try:
        if args.suite_command:
            evidence_record, _cmd_warnings = _run_suite_command(
                args.suite_command, after, args.suite_exit_code, args.suite_timeout
            )
        elif args.suite_evidence:
            evidence_record = _preload_evidence(args.suite_evidence, args.suite_exit_code)
    except ValueError as exc:
        _write_output(
            _error_payload(f"invocation error: {exc}", args.objective, args.suite_exit_code),
            args.out,
        )
        return 2

    verdict_payload = _build_verdict(
        before,
        after,
        args.suite_exit_code,
        args.min_win,
        args.ledger,
        objective=args.objective,
        evidence_record=evidence_record,
        require_verified=args.require_verified,
    )
    _write_output(verdict_payload, args.out)

    return EXIT_CODES[verdict_payload["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
