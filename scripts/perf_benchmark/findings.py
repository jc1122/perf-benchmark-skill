"""Shared-schema PERF findings bridge.

Converts a rubric dict into shared code-health findings with signal=PERF,
leaf=perf-benchmark. Uses stdlib only.
"""

from __future__ import annotations

import hashlib
from typing import Any

_WORKLOAD_SYMBOL = "<workload>"


def to_shared_findings(
    rubric: dict[str, Any],
    root: str = "<benchmark-suite>",
) -> list[dict[str, Any]]:
    """Convert rubric dimensions to shared-schema PERF findings.

    Only FAIL and WARN dimensions produce findings. PASS and N/A dimensions
    (including N/A (noise)) are skipped.

    Dimensions may carry explicit ``metric``/``value``/``threshold`` keys, or
    the bridge infers metric names from the dimension name and known fields
    (``cv``, ``worst_pct``, ``top_fn_pct``, ``IPC``, ``sub_checks``, etc.).

    Results are sorted by (path, metric.name) for deterministic output.
    """
    findings: list[dict[str, Any]] = []

    for name, dim in rubric.get("dimensions", []):
        tier = dim.get("tier", "N/A")
        if tier in ("PASS", "N/A", "N/A (noise)"):
            continue

        metrics = _extract_metrics(name, dim)
        for metric_name, value, threshold in metrics:
            finding = _build_finding(dim, metric_name, value, threshold, root)
            findings.append(finding)

    findings.sort(key=lambda f: (f["path"], f["metric"]["name"]))
    return findings


# ------------------------------------------------------------------ extractors


def _extract_metrics(name: str, dim: dict[str, Any]) -> list[tuple[str, float, float]]:
    """Return ``[(metric_name, value, threshold), ...]`` for a dimension."""
    # Explicit metric triplet (used in tests)
    if "metric" in dim and "value" in dim and "threshold" in dim:
        return [(str(dim["metric"]), float(dim["value"]), float(dim["threshold"]))]

    # Infer from known dimension name
    handler = _METRIC_EXTRACTORS.get(name)
    if handler:
        return handler(dim)
    return []


def _extract_wall_time(dim: dict[str, Any]) -> list[tuple[str, float, float]]:
    if "cv" in dim:
        return [("wall_time_cv", float(dim["cv"]), 3.0)]
    return []


def _extract_cpu(dim: dict[str, Any]) -> list[tuple[str, float, float]]:
    result: list[tuple[str, float, float]] = []
    if "top_fn_pct" in dim:
        result.append(("top_fn_pct", float(dim["top_fn_pct"]), 20.0))
    if "IPC" in dim:
        result.append(("IPC", float(dim["IPC"]), 1.5))
    return result


def _extract_cache(dim: dict[str, Any]) -> list[tuple[str, float, float]]:
    if "worst_pct" in dim:
        return [("l1_miss_rate", float(dim["worst_pct"]), 1.0)]
    return []


def _extract_ll_cache(dim: dict[str, Any]) -> list[tuple[str, float, float]]:
    if "worst_pct" in dim:
        return [("ll_miss_rate", float(dim["worst_pct"]), 0.5)]
    return []


def _extract_branch(dim: dict[str, Any]) -> list[tuple[str, float, float]]:
    if "worst_pct" in dim:
        return [("branch_mispred_rate", float(dim["worst_pct"]), 1.0)]
    return []


def _extract_algorithmic(dim: dict[str, Any]) -> list[tuple[str, float, float]]:
    result: list[tuple[str, float, float]] = []
    sub_checks = dim.get("sub_checks", {})
    for check_name, check in sub_checks.items():
        check_tier = check.get("tier", "")
        if check_tier not in ("FAIL", "WARN"):
            continue
        value = 0.0
        for key in ("k", "ratio", "peaks", "path_count"):
            if key in check:
                value = float(check[key])
                break
        result.append((check_name, value, 0.0))
    return result


def _extract_memory(dim: dict[str, Any]) -> list[tuple[str, float, float]]:
    result: list[tuple[str, float, float]] = []
    if "peak_bytes" in dim:
        result.append(("peak_bytes", float(dim["peak_bytes"]), 0.0))
    if "churn_peaks" in dim:
        result.append(("churn_peaks", float(dim["churn_peaks"]), 2.0))
    return result


_METRIC_EXTRACTORS: dict[str, Any] = {
    "Wall-Time Stability": _extract_wall_time,
    "CPU Efficiency": _extract_cpu,
    "L1 Cache Efficiency": _extract_cache,
    "Last-Level Cache": _extract_ll_cache,
    "Branch Prediction": _extract_branch,
    "Algorithmic Scaling": _extract_algorithmic,
    "Memory Profile": _extract_memory,
}

# -------------------------------------------------------------------- builder


_PRESCRIPTIONS: dict[str, str] = {
    "Algorithmic": "Review scaling sub-checks. Memoize, precompute, or restructure hot paths.",
    "L1": "Improve data locality: struct-of-arrays, cache-line alignment, sequential access.",
    "Last-Level": "Reduce working set size or improve spatial locality.",
    "Branch": "Replace unpredictable branches with cmov, lookup tables, or branchless arithmetic.",
    "CPU": "Reduce hotspot concentration. Consider splitting large functions.",
    "Memory": "Pre-allocate buffers, use object pools, reduce allocation churn.",
    "Wall": "Reduce measurement noise: set governor=performance, increase rounds.",
}


def _build_finding(
    dim: dict[str, Any],
    metric_name: str,
    value: float,
    threshold: float,
    root: str,
) -> dict[str, Any]:
    tier = dim.get("tier", "FAIL")
    severity = "high" if tier == "FAIL" else "medium"

    id_input = f"perf-benchmark|{root}|{_WORKLOAD_SYMBOL}|{metric_name}"
    finding_id = hashlib.sha1(id_input.encode()).hexdigest()[:16]

    return {
        "id": finding_id,
        "leaf": "perf-benchmark",
        "signal": "PERF",
        "severity": severity,
        "path": root,
        "location": {
            "line_start": 0,
            "line_end": 0,
            "symbol": _WORKLOAD_SYMBOL,
        },
        "metric": {
            "name": metric_name,
            "value": value,
            "threshold": threshold,
        },
        "evidence": [],
        "confidence": "high",
        "suggested_action": _suggested_action(dim, metric_name, tier),
    }


def _suggested_action(dim: dict[str, Any], metric_name: str, tier: str) -> str:
    for prefix, action in _PRESCRIPTIONS.items():
        if prefix in metric_name or prefix in str(dim.get("source", "")):
            return action
    return f"Investigate {metric_name} ({tier})"
