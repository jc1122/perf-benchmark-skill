from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


TIER_RANK = {"FAIL": 0, "WARN": 1, "PASS": 2}
__all__ = [
    "TIER_RANK",
    "_cv",
    "_fit_exponent",
    "score_algorithmic_scaling",
    "score_wall_time_stability",
    "score_cpu_efficiency",
    "score_cache_dim",
    "score_memory_profile",
    "score_rubric",
]


def _cv(values: list[float]) -> float:
    """Coefficient of variation (%)."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return 100.0 * math.sqrt(variance) / mean


def _fit_exponent(sizes: list[int], times: list[float]) -> float:
    """Fit time = a * N^k via log-log linear regression. Returns k."""
    if len(sizes) < 2 or len(times) < 2:
        return 1.0
    filtered_pairs = [(n, t) for n, t in zip(sizes, times) if n > 0 and t > 0]
    if len(filtered_pairs) < 2:
        return 1.0
    log_n = [math.log(n) for n, _ in filtered_pairs]
    log_t = [math.log(t) for _, t in filtered_pairs]
    count = len(log_n)
    sum_x = sum(log_n)
    sum_y = sum(log_t)
    sum_xy = sum(x * y for x, y in zip(log_n, log_t))
    sum_x2 = sum(x * x for x in log_n)
    denom = count * sum_x2 - sum_x * sum_x
    if abs(denom) < 1e-12:
        return 1.0
    k = (count * sum_xy - sum_x * sum_y) / denom
    return round(k, 3)


def score_algorithmic_scaling(
    tier1: dict, tier234: dict, args: argparse.Namespace
) -> dict[str, Any]:
    required_sub_checks = {
        "complexity_exponent",
        "call_amplification",
        "data_reuse",
        "write_amplification",
        "allocation_churn",
        "multiplicative_paths",
    }
    sub_checks: dict[str, dict] = {}

    sizes = args.sizes
    if sizes and len(sizes) >= 2:
        pb = tier1.get("pytest_benchmark", {})
        benchmarks = pb.get("benchmarks", [])
        times_by_size: dict[int, list[float]] = {}
        if benchmarks:
            for benchmark in benchmarks:
                params = benchmark.get("params", {}) or {}
                size = params.get("size") or benchmark.get("extra_info", {}).get("input_size")
                if size is not None:
                    times_by_size.setdefault(int(size), []).append(
                        benchmark.get("stats", {}).get("mean", 0)
                    )
        else:
            for size, runs in tier1.get("time_usage_by_size", {}).items():
                walls = [run.get("wall_seconds", 0.0) for run in runs if run.get("wall_seconds")]
                if walls:
                    times_by_size[int(size)] = walls
        if times_by_size:
            matched_sizes: list[int] = []
            matched_times: list[float] = []
            for size in sorted(sizes):
                if size in times_by_size:
                    matched_sizes.append(size)
                    matched_times.append(sum(times_by_size[size]) / len(times_by_size[size]))
            if len(matched_sizes) >= 2:
                k = _fit_exponent(matched_sizes, matched_times)
                thresholds = {
                    "linear": (1.1, 1.3),
                    "nlogn": (1.3, 1.5),
                    "quadratic": (2.0, 2.2),
                }
                warn_k, fail_k = thresholds.get(args.expected_complexity, (1.3, 1.8))
                tier_val = "PASS" if k <= warn_k else "WARN" if k <= fail_k else "FAIL"
                sub_checks["complexity_exponent"] = {"k": k, "tier": tier_val}

    input_size = args.valgrind_size
    callgrind = tier234.get("callgrind", {})
    if callgrind and not callgrind.get("error") and callgrind.get("functions"):
        if input_size > 0 and "total_calls" in callgrind:
            amp = callgrind["total_calls"] / input_size
            tier_val = "PASS" if amp <= 10 else "WARN" if amp <= 100 else "FAIL"
            sub_checks["call_amplification"] = {"ratio": round(amp, 1), "tier": tier_val}

    cachegrind = tier234.get("cachegrind", {})
    if cachegrind and not cachegrind.get("error"):
        files = cachegrind.get("files", [])

        reuse = None
        if input_size > 0 and files:
            reuse_values = [
                float(file_data.get("Dr", 0)) / input_size
                for file_data in files
                if file_data.get("Dr", 0) > 0
            ]
            if reuse_values:
                reuse = max(reuse_values)
        if reuse is None and input_size > 0:
            total_dr = cachegrind.get("summary", {}).get("Dr", 0)
            if total_dr > 0:
                reuse = total_dr / input_size
        if reuse is not None:
            tier_val = "PASS" if reuse <= 10 else "WARN" if reuse <= 100 else "FAIL"
            sub_checks["data_reuse"] = {"ratio": round(reuse, 1), "tier": tier_val}

        write_ratio = None
        if files:
            write_values = [
                float(file_data.get("Dw", 0)) / float(file_data.get("Dr", 0))
                for file_data in files
                if file_data.get("Dr", 0) > 0
            ]
            if write_values:
                write_ratio = max(write_values)
        if write_ratio is None:
            total_dr = cachegrind.get("summary", {}).get("Dr", 0)
            total_dw = cachegrind.get("summary", {}).get("Dw", 0)
            if total_dr > 0:
                write_ratio = total_dw / total_dr
        if write_ratio is not None:
            tier_val = "PASS" if write_ratio <= 0.2 else "WARN" if write_ratio <= 0.5 else "FAIL"
            sub_checks["write_amplification"] = {
                "ratio": round(write_ratio, 3),
                "tier": tier_val,
            }

    massif = tier234.get("massif", {})
    if massif and not massif.get("error"):
        peaks = massif.get("local_maxima_count", 0)
        tier_val = "PASS" if peaks <= 2 else "WARN" if peaks <= 5 else "FAIL"
        sub_checks["allocation_churn"] = {"peaks": peaks, "tier": tier_val}

    if callgrind and not callgrind.get("error") and "multiplicative_path_count" in callgrind:
        path_count = int(callgrind.get("multiplicative_path_count", 0))
        tier_val = "PASS" if path_count == 0 else "WARN" if path_count == 1 else "FAIL"
        sub_checks["multiplicative_paths"] = {"path_count": path_count, "tier": tier_val}

    if not sub_checks:
        return {
            "score": -1,
            "tier": "N/A",
            "sub_checks": {},
            "note": "Insufficient data for scaling analysis",
        }

    missing_sub_checks = sorted(required_sub_checks - set(sub_checks))
    if missing_sub_checks:
        return {
            "score": -1,
            "tier": "N/A",
            "sub_checks": sub_checks,
            "missing_sub_checks": missing_sub_checks,
            "note": "Incomplete evidence for strict scaling rubric",
        }

    fails = sum(1 for check in sub_checks.values() if check["tier"] == "FAIL")
    warns = sum(1 for check in sub_checks.values() if check["tier"] == "WARN")
    if fails > 0:
        return {"score": 0, "tier": "FAIL", "sub_checks": sub_checks}
    if warns >= 2:
        return {"score": 2, "tier": "WARN", "sub_checks": sub_checks}
    return {"score": 4, "tier": "PASS", "sub_checks": sub_checks}


def score_wall_time_stability(tier1: dict) -> dict[str, Any]:
    """Dimension 1: wall-time CV."""
    pb = tier1.get("pytest_benchmark", {})
    benchmarks = pb.get("benchmarks", [])
    if benchmarks:
        cvs = [
            benchmark.get("stats", {}).get("stddev", 0)
            / max(benchmark.get("stats", {}).get("mean", 1e-12), 1e-12)
            * 100
            for benchmark in benchmarks
        ]
        avg_cv = sum(cvs) / len(cvs) if cvs else 0
    else:
        time_usage_by_size = tier1.get("time_usage_by_size", {})
        if time_usage_by_size:
            cv_by_size = {
                int(size): round(
                    _cv(
                        [
                            run.get("wall_seconds", 0.0)
                            for run in runs
                            if run.get("wall_seconds")
                        ]
                    ),
                    2,
                )
                for size, runs in time_usage_by_size.items()
                if any(run.get("wall_seconds") for run in runs)
            }
            avg_cv = max(cv_by_size.values()) if cv_by_size else -1
        else:
            times = [
                item.get("wall_seconds", 0)
                for item in tier1.get("time_usage", [])
                if item.get("wall_seconds")
            ]
            cv_by_size = None
            avg_cv = _cv(times) if times else -1

    if avg_cv < 0:
        return {"score": -1, "tier": "N/A", "cv": None}

    tier_val = "PASS" if avg_cv <= 3 else "WARN" if avg_cv <= 8 else "FAIL"
    score = 4 if tier_val == "PASS" else 2 if tier_val == "WARN" else 0
    result: dict[str, Any] = {"score": score, "tier": tier_val, "cv": round(avg_cv, 2)}
    if not benchmarks and "cv_by_size" in locals() and cv_by_size is not None:
        result["cv_by_size"] = cv_by_size
    return result


def score_cpu_efficiency(tier234: dict) -> dict[str, Any]:
    """Dimension 2: CPU efficiency (hotspot concentration + IPC)."""
    callgrind = tier234.get("callgrind", {})
    perf = tier234.get("perf_stat", {})

    concentration = None
    if callgrind and callgrind.get("functions") and callgrind.get("total_ir", 0) > 0:
        top_ir = callgrind["functions"][0].get("Ir", 0)
        concentration = round(100.0 * top_ir / callgrind["total_ir"], 1)

    ipc = perf.get("IPC") if perf and not perf.get("error") else None
    if concentration is None and ipc is None:
        return {"score": -1, "tier": "N/A"}

    score = 4
    tier_val = "PASS"
    evidence: dict[str, Any] = {}
    if concentration is not None:
        evidence["top_fn_pct"] = concentration
        if concentration > 35:
            score = min(score, 0)
            tier_val = "FAIL"
        elif concentration > 20:
            score = min(score, 2)
            if tier_val == "PASS":
                tier_val = "WARN"

    if ipc is not None:
        evidence["IPC"] = ipc
        if ipc < 1.0:
            score = 0
            tier_val = "FAIL"
        elif ipc < 1.5:
            score = min(score, 2)
            if tier_val == "PASS":
                tier_val = "WARN"

    return {"score": score, "tier": tier_val, **evidence}


def score_cache_dim(tier234: dict, metric_key: str, pass_t: float, warn_t: float) -> dict[str, Any]:
    """Generic cache dimension scorer."""
    cachegrind = tier234.get("cachegrind", {})
    if not cachegrind or cachegrind.get("error"):
        return {"score": -1, "tier": "N/A"}

    values = [
        file_data.get(metric_key, 0)
        for file_data in cachegrind.get("files", [])
        if file_data.get(metric_key) is not None
    ]
    if not values:
        summary = cachegrind.get("summary", {})
        if metric_key == "L1d_miss_pct" and summary.get("Dr", 0) > 0:
            values = [100.0 * summary.get("D1mr", 0) / summary["Dr"]]
        elif metric_key == "LL_miss_pct" and (summary.get("Dr", 0) + summary.get("Dw", 0)) > 0:
            total = summary.get("Dr", 0) + summary.get("Dw", 0)
            values = [100.0 * (summary.get("DLmr", 0) + summary.get("DLmw", 0)) / total]
        elif metric_key == "branch_mispred_pct" and summary.get("Bc", 0) > 0:
            values = [100.0 * summary.get("Bcm", 0) / summary["Bc"]]

    if not values:
        return {"score": -1, "tier": "N/A"}

    worst = max(values)
    tier_val = "PASS" if worst <= pass_t else "WARN" if worst <= warn_t else "FAIL"
    score = 4 if tier_val == "PASS" else 2 if tier_val == "WARN" else 0
    return {"score": score, "tier": tier_val, "worst_pct": round(worst, 3)}


def score_memory_profile(tier1: dict, tier234: dict, baseline: dict | None) -> dict[str, Any]:
    """Dimension 6: memory profile."""
    peak_bytes = 0
    source = "none"

    massif = tier234.get("massif", {})
    if massif and not massif.get("error") and massif.get("peak_bytes", 0) > 0:
        peak_bytes = massif["peak_bytes"]
        source = "massif"

    tracemalloc = tier1.get("tracemalloc", {})
    if not peak_bytes and tracemalloc and tracemalloc.get("peak_bytes", 0) > 0:
        peak_bytes = tracemalloc["peak_bytes"]
        source = "tracemalloc"

    if not peak_bytes:
        return {"score": -1, "tier": "N/A"}

    if baseline:
        base_peak = (
            baseline.get("rubric", {})
            .get("dimensions", {})
            .get("Memory Profile", {})
            .get("peak_bytes", 0)
        )
        if base_peak > 0:
            ratio = peak_bytes / base_peak
            tier_val = "PASS" if ratio <= 1.1 else "WARN" if ratio <= 1.5 else "FAIL"
            score = 4 if tier_val == "PASS" else 2 if tier_val == "WARN" else 0
            return {
                "score": score,
                "tier": tier_val,
                "peak_bytes": peak_bytes,
                "baseline_ratio": round(ratio, 2),
                "source": source,
            }

    churn_peaks = massif.get("local_maxima_count", 0) if massif else 0
    if churn_peaks > 5:
        return {
            "score": 0,
            "tier": "FAIL",
            "peak_bytes": peak_bytes,
            "churn_peaks": churn_peaks,
            "source": source,
        }
    if churn_peaks > 2:
        return {
            "score": 2,
            "tier": "WARN",
            "peak_bytes": peak_bytes,
            "churn_peaks": churn_peaks,
            "source": source,
        }
    return {"score": 4, "tier": "PASS", "peak_bytes": peak_bytes, "source": source}


def _collect_baseline_regressions(
    dimensions: list[tuple[str, dict[str, Any]]], baseline: dict[str, Any] | None
) -> list[dict[str, Any]]:
    if not baseline:
        return []

    baseline_dimensions = baseline.get("rubric", {}).get("dimensions", {})
    regressions: list[dict[str, Any]] = []
    for name, current in dimensions:
        current_tier = current.get("tier")
        baseline_tier = baseline_dimensions.get(name, {}).get("tier")
        if current_tier not in TIER_RANK or baseline_tier not in TIER_RANK:
            continue

        drop = TIER_RANK[baseline_tier] - TIER_RANK[current_tier]
        if drop >= 1:
            regressions.append(
                {
                    "dimension": name,
                    "baseline_tier": baseline_tier,
                    "current_tier": current_tier,
                    "drop": drop,
                }
            )
    return regressions


def score_rubric(tier1: dict, tier234: dict, args: argparse.Namespace) -> dict[str, Any]:
    baseline = None
    if args.baseline:
        try:
            baseline = json.loads(Path(args.baseline).read_text())
        except (OSError, json.JSONDecodeError):
            baseline = None

    dimensions: list[tuple[str, dict]] = [
        ("Algorithmic Scaling", score_algorithmic_scaling(tier1, tier234, args)),
        ("Wall-Time Stability", score_wall_time_stability(tier1)),
        ("CPU Efficiency", score_cpu_efficiency(tier234)),
        ("L1 Cache Efficiency", score_cache_dim(tier234, "L1d_miss_pct", 1.0, 5.0)),
        ("Last-Level Cache", score_cache_dim(tier234, "LL_miss_pct", 0.5, 2.0)),
        ("Branch Prediction", score_cache_dim(tier234, "branch_mispred_pct", 1.0, 3.0)),
        ("Memory Profile", score_memory_profile(tier1, tier234, baseline)),
    ]

    available = [(name, dimension) for name, dimension in dimensions if dimension.get("tier") != "N/A"]
    total = sum(dimension["score"] for _, dimension in available)
    max_possible = len(available) * 4
    baseline_regressions = _collect_baseline_regressions(dimensions, baseline)
    return {
        "dimensions": dimensions,
        "total": total,
        "max_possible": max_possible,
        "baseline_regressions": baseline_regressions,
    }
