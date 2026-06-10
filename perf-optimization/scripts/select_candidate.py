#!/usr/bin/env python3
"""Deterministic PERF candidate selection with algorithmic STOP gate.

Selects the single highest-priority PERF finding from a shared-schema findings
JSON file.  The algorithmic STOP gate always wins regardless of severity.
Otherwise highest severity, then highest ratio, then (path, metric.name) order.

Usage:
    python select_candidate.py --findings PATH --out PATH
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ALGORITHMIC_METRIC_SUBSTRINGS = (
    "scaling",
    "complexity_exponent",
    "call_amplification",
    "data_reuse",
    "write_amplification",
    "allocation_churn",
    "multiplicative_paths",
)

SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1, "info": 0}

_REQUIRED_FINDING_KEYS = {"id", "path", "severity", "metric"}
_REQUIRED_METRIC_KEYS = {"name", "value", "threshold"}


def _is_algorithmic(metric_name: str) -> bool:
    """Return True if *metric_name* contains any algorithmic substring."""
    return any(sub in metric_name for sub in ALGORITHMIC_METRIC_SUBSTRINGS)


def _compute_ratio(metric: dict[str, Any]) -> float:
    """Compute ratio = value / threshold, or value if threshold is 0."""
    value = float(metric["value"])
    threshold = float(metric["threshold"])
    if threshold == 0.0:
        return value
    return value / threshold


def _validate_finding(finding: Any) -> None:
    """Validate a single finding has required shape.  Raises ValueError."""
    if not isinstance(finding, dict):
        raise ValueError("finding is not a JSON object")
    missing = _REQUIRED_FINDING_KEYS - set(finding)
    if missing:
        raise ValueError(f"finding missing required keys: {sorted(missing)}")
    metric = finding.get("metric")
    if not isinstance(metric, dict):
        raise ValueError("finding.metric is not a JSON object")
    missing_metric = _REQUIRED_METRIC_KEYS - set(metric)
    if missing_metric:
        raise ValueError(
            f"finding.metric missing required keys: {sorted(missing_metric)}"
        )
    # Validate types
    for key in ("id", "path"):
        if not isinstance(finding[key], str):
            raise ValueError(f"finding.{key} must be a string")
    if not isinstance(finding["severity"], str):
        raise ValueError("finding.severity must be a string")
    for key in ("name",):
        if not isinstance(metric[key], str):
            raise ValueError(f"finding.metric.{key} must be a string")
    for key in ("value", "threshold"):
        if not isinstance(metric[key], (int, float)):
            raise ValueError(f"finding.metric.{key} must be a number")


def _validate_findings(findings: Any) -> list[dict[str, Any]]:
    """Validate the findings array.  Returns list of valid findings.

    Raises ValueError if the input is not a list, or if any item fails
    shape validation.
    """
    if not isinstance(findings, list):
        raise ValueError("findings root must be a JSON array")
    for i, finding in enumerate(findings):
        try:
            _validate_finding(finding)
        except ValueError as exc:
            raise ValueError(f"finding[{i}]: {exc}") from None
    return findings


def select_candidate(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Select the single highest-priority candidate from *findings*.

    Returns a dict with keys ``status`` and ``candidate`` (or just
    ``status`` if no candidates).
    """
    if not findings:
        return {"status": "no_candidates"}

    # Build sortable records
    records: list[dict[str, Any]] = []
    for f in findings:
        metric_name = f["metric"]["name"]
        stop_gate = _is_algorithmic(metric_name)
        severity_rank = SEVERITY_RANK.get(f["severity"], 0)
        ratio = _compute_ratio(f["metric"])
        records.append(
            {
                "id": f["id"],
                "path": f["path"],
                "metric_name": metric_name,
                "severity": f["severity"],
                "ratio": round(ratio, 6),
                "stop_gate": stop_gate,
                "_sort_key": (
                    not stop_gate,  # False (0) sorts before True (1) → stop_gate first
                    -severity_rank,
                    -ratio,
                    f["path"],
                    metric_name,
                ),
            }
        )

    # Sort deterministically
    records.sort(key=lambda r: r["_sort_key"])

    best = records[0]
    return {
        "status": "ok",
        "candidate": {
            "id": best["id"],
            "path": best["path"],
            "metric_name": best["metric_name"],
            "severity": best["severity"],
            "ratio": best["ratio"],
            "stop_gate": best["stop_gate"],
        },
    }


def _write_output(payload: dict[str, Any], out_path: str | None) -> str:
    """Serialize *payload* to JSON string and write to *out_path* if given.

    Returns the JSON string (also printed to stdout).
    """
    json_str = json.dumps(payload, sort_keys=True)
    print(json_str)
    if out_path:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json_str + "\n")
    return json_str


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic PERF candidate selection"
    )
    parser.add_argument(
        "--findings", required=True, type=str, help="Path to PERF findings JSON file"
    )
    parser.add_argument(
        "--out", required=True, type=str, help="Path for output JSON file"
    )
    args = parser.parse_args(argv)

    # Read input
    try:
        raw = Path(args.findings).read_text()
    except OSError as exc:
        _write_output(
            {"status": "error", "message": f"Cannot read findings file: {exc}"},
            args.out,
        )
        return 2

    # Parse JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        _write_output(
            {"status": "error", "message": f"Malformed JSON: {exc}"},
            args.out,
        )
        return 2

    # Validate shape
    try:
        findings = _validate_findings(data)
    except ValueError as exc:
        _write_output(
            {"status": "error", "message": f"Malformed findings shape: {exc}"},
            args.out,
        )
        return 2

    # Select candidate
    result = select_candidate(findings)
    _write_output(result, args.out)

    if result["status"] == "no_candidates":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
