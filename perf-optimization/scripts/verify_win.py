#!/usr/bin/env python3
"""Deterministic win-verdict wrapper for SP6-pipeline before/after comparisons.

Consumes two benchmark_summary.json files (before + after), a test-suite
exit code, and an optional ledger to decide ACCEPT or REJECT according to
the acceptance ratchet defined in perf-optimization/SKILL.md.

Usage:
    python verify_win.py \
        --before summary_before.json \
        --after summary_after.json \
        --suite-exit-code 0 \
        --min-win 5.0 \
        --ledger perf-ledger.jsonl \
        --out verdict.json
"""

from __future__ import annotations

import argparse
import json
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


# ----------------------------------------------------------------- validation


def _load_summary(path: str) -> dict[str, Any]:
    """Read a summary JSON file. Returns the parsed dict.

    Raises OSError if the file cannot be read.
    Raises json.JSONDecodeError / ValueError if the content is invalid.
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
    wpt = data.get("wall_time_percentiles")
    if not isinstance(wpt, dict) or "p50" not in wpt or not isinstance(wpt["p50"], (int, float)):
        raise ValueError("summary.wall_time_percentiles.p50 is missing or not a number")
    env = data.get("environment")
    if not isinstance(env, dict):
        raise ValueError("summary.environment is missing or not a JSON object")
    return data


def _dimension_tiers(rubric: dict[str, Any]) -> dict[str, str]:
    """Extract {dimension_name: tier} from a rubric dict."""
    dims = rubric.get("dimensions", {})
    return {name: dim.get("tier", "N/A") for name, dim in dims.items()}


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
            if dim.get("tier") == _NOISE_TIER:
                reasons.append("noise")
                break
    return reasons


def _check_fingerprint(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Check that *before* and *after* environments match on the 5
    fingerprint keys.  timestamp_utc and load_avg_1m are excluded."""
    for key in _FINGERPRINT_KEYS:
        if before.get("environment", {}).get(key) != after.get("environment", {}).get(key):
            return ["fingerprint"]
    return []


def _check_tier_drops(before_dims: dict[str, str], after_dims: dict[str, str]) -> list[str]:
    """Reject if any dimension tier drops by >=1 step (PASS > WARN > FAIL).
    N/A (noise) dimensions are already handled by the noise check and are
    considered incomparable here; other non-PASS/WARN/FAIL tiers are also
    skipped.
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


# ------------------------------------------------------------ ledger reading


def _read_ledger(ledger_path: str, after_dims: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
    """Read the JSONL ledger, compare after dimensions against the last entry.

    Returns (vs_last_dict, warnings).  vs_last_dict is ALWAYS a dict:
      - {} when no entries exist or no regressions found
      - {"regressions": [...]} when tier drops are detected

    Corrupt lines produce a warning and are skipped.
    A missing ledger file produces a warning and {}.
    """
    warnings: list[str] = []
    entries: list[dict[str, Any]] = []

    lpath = Path(ledger_path)
    if not lpath.exists():
        warnings.append(f"Ledger file not found: {ledger_path}")
        return {}, warnings

    for lineno, raw in enumerate(lpath.read_text().splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            entries.append(json.loads(stripped))
        except json.JSONDecodeError:
            warnings.append(f"Skipped corrupt line {lineno} in {ledger_path}")

    if not entries:
        return {}, warnings

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

    if regressions:
        return {"regressions": regressions}, warnings
    return {}, warnings


# -------------------------------------------------------------- orchestration


def _build_verdict(
    before: dict[str, Any],
    after: dict[str, Any],
    suite_exit_code: int,
    min_win: float,
    ledger_path: str | None,
) -> dict[str, Any]:
    """Run all checks in fixed order and build the verdict dict."""

    before_p50 = float(before["wall_time_percentiles"]["p50"])
    after_p50 = float(after["wall_time_percentiles"]["p50"])

    before_dims = _dimension_tiers(before.get("rubric", {}))
    after_dims = _dimension_tiers(after.get("rubric", {}))

    median_win, median_reasons = _check_median(before_p50, after_p50, min_win)
    noise_reasons = _check_noise(before, after)
    fingerprint_reasons = _check_fingerprint(before, after)
    tier_reasons = _check_tier_drops(before_dims, after_dims)
    suite_reasons = _check_suite(suite_exit_code)

    all_reasons = (
        median_reasons + noise_reasons + fingerprint_reasons + tier_reasons + suite_reasons
    )

    verdict = "reject" if all_reasons else "accept"

    result: dict[str, Any] = {
        "verdict": verdict,
        "median_win_percent": median_win,
        "reasons": all_reasons or [],
        "vs_last": {},
    }

    if ledger_path:
        vs_last_dict, ledger_warnings = _read_ledger(ledger_path, after_dims)
        result["vs_last"] = vs_last_dict
        if ledger_warnings:
            result["warnings"] = ledger_warnings

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic SP6-pipeline win verdict wrapper")
    parser.add_argument(
        "--before", required=True, type=str, help="Before-run benchmark_summary.json"
    )
    parser.add_argument("--after", required=True, type=str, help="After-run benchmark_summary.json")
    parser.add_argument("--suite-exit-code", required=True, type=int, help="Test suite exit code")
    parser.add_argument(
        "--min-win",
        type=float,
        default=5.0,
        help="Minimum median win pct (default: 5.0)",
    )
    parser.add_argument(
        "--ledger", type=str, default=None, help="Optional append-only JSONL ledger"
    )
    parser.add_argument("--out", required=True, type=str, help="Path for verdict JSON output")
    args = parser.parse_args(argv)

    # Load before summary
    try:
        before = _load_summary(args.before)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _write_output(
            {
                "verdict": "error",
                "median_win_percent": 0.0,
                "reasons": ["malformed"],
                "vs_last": {},
                "warnings": [f"Before summary error: {exc}"],
            },
            args.out,
        )
        return 2

    # Load after summary
    try:
        after = _load_summary(args.after)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _write_output(
            {
                "verdict": "error",
                "median_win_percent": 0.0,
                "reasons": ["malformed"],
                "vs_last": {},
                "warnings": [f"After summary error: {exc}"],
            },
            args.out,
        )
        return 2

    # Build verdict
    verdict_payload = _build_verdict(before, after, args.suite_exit_code, args.min_win, args.ledger)

    _write_output(verdict_payload, args.out)

    if verdict_payload["verdict"] == "accept":
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
