from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

_SUCCESS_TIER = "PASS"
TIER_RANK = {"FAIL": 0, "WARN": 1, _SUCCESS_TIER: 2}
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


def _compute_log_log_slope(log_n: list[float], log_t: list[float]) -> float:
    """Linear regression slope on log-log data. Returns 1.0 when degenerate."""
    count = len(log_n)
    sum_x = sum(log_n)
    sum_y = sum(log_t)
    sum_xy = sum(x * y for x, y in zip(log_n, log_t, strict=True))
    sum_x2 = sum(x * x for x in log_n)
    denom = count * sum_x2 - sum_x * sum_x
    if abs(denom) < 1e-12:
        return 1.0
    return (count * sum_xy - sum_x * sum_y) / denom


def _fit_exponent(sizes: list[int], times: list[float]) -> float:
    """Fit time = a * N^k via log-log linear regression. Returns k."""
    if len(sizes) < 2 or len(times) < 2:
        return 1.0
    filtered_pairs = [(n, t) for n, t in zip(sizes, times, strict=False) if n > 0 and t > 0]
    if len(filtered_pairs) < 2:
        return 1.0
    log_n = [math.log(n) for n, _ in filtered_pairs]
    log_t = [math.log(t) for _, t in filtered_pairs]
    k = _compute_log_log_slope(log_n, log_t)
    return round(k, 3)


# ── score_algorithmic_scaling helpers ──────────────────────────────────────


def _times_from_pytest_benchmark(pb: dict) -> dict[int, list[float]]:
    """Collect per-size times from pytest-benchmark data."""
    times_by_size: dict[int, list[float]] = {}
    for benchmark in pb.get("benchmarks", []):
        params = benchmark.get("params", {}) or {}
        size = params.get("size") or benchmark.get("extra_info", {}).get("input_size")
        if size is not None:
            times_by_size.setdefault(int(size), []).append(
                benchmark.get("stats", {}).get("mean", 0)
            )
    return times_by_size


def _times_from_explicit_targets(tier1: dict) -> dict[int, list[float]]:
    """Collect per-size times from explicit target time_usage_by_size."""
    times_by_size: dict[int, list[float]] = {}
    for size, runs in tier1.get("time_usage_by_size", {}).items():
        walls = [run.get("wall_seconds", 0.0) for run in runs if run.get("wall_seconds")]
        if walls:
            times_by_size[int(size)] = walls
    return times_by_size


def _collect_times_by_size(tier1: dict, args: argparse.Namespace) -> dict[int, list[float]] | None:
    """Collect per-size wall-clock times from tier1 benchmark data."""
    sizes = args.sizes
    if not sizes or len(sizes) < 2:
        return None
    pb = tier1.get("pytest_benchmark", {})
    if pb.get("benchmarks"):
        times_by_size = _times_from_pytest_benchmark(pb)
    else:
        times_by_size = _times_from_explicit_targets(tier1)
    return times_by_size if times_by_size else None


def _score_scaling_exponent(tier1: dict, args: argparse.Namespace) -> dict | None:
    """Score the algorithmic complexity exponent sub-check."""
    sizes = args.sizes
    if not sizes or len(sizes) < 2:
        return None
    times_by_size = _collect_times_by_size(tier1, args)
    if not times_by_size:
        return None
    matched_sizes: list[int] = []
    matched_times: list[float] = []
    for size in sorted(sizes):
        if size in times_by_size:
            matched_sizes.append(size)
            matched_times.append(sum(times_by_size[size]) / len(times_by_size[size]))
    if len(matched_sizes) < 2:
        return None
    k = _fit_exponent(matched_sizes, matched_times)
    thresholds = {
        "linear": (1.1, 1.3),
        "nlogn": (1.3, 1.5),
        "quadratic": (2.0, 2.2),
    }
    warn_k, fail_k = thresholds.get(args.expected_complexity, (1.3, 1.8))
    tier_val = "PASS" if k <= warn_k else "WARN" if k <= fail_k else "FAIL"
    return {"k": k, "tier": tier_val}


def _score_call_amplification(callgrind: dict, input_size: int) -> dict | None:
    """Score call amplification from callgrind data."""
    if (
        callgrind
        and not callgrind.get("error")
        and callgrind.get("functions")
        and input_size > 0
        and "total_calls" in callgrind
    ):
        amp = callgrind["total_calls"] / input_size
        tier_val = "PASS" if amp <= 10 else "WARN" if amp <= 100 else "FAIL"
        return {"ratio": round(amp, 1), "tier": tier_val}
    return None


def _reuse_value(cachegrind: dict, input_size: int) -> float | None:
    """Compute data reuse ratio from cachegrind, preferring per-file max."""
    files = cachegrind.get("files", [])
    if input_size > 0 and files:
        vals = [float(f.get("Dr", 0)) / input_size for f in files if f.get("Dr", 0) > 0]
        if vals:
            return max(vals)
    total_dr = cachegrind.get("summary", {}).get("Dr", 0)
    if input_size > 0 and total_dr > 0:
        return total_dr / input_size
    return None


def _score_data_reuse(cachegrind: dict, input_size: int) -> dict | None:
    """Score data reuse from cachegrind D-read data."""
    if not cachegrind or cachegrind.get("error"):
        return None
    reuse = _reuse_value(cachegrind, input_size)
    if reuse is not None:
        tier_val = "PASS" if reuse <= 10 else "WARN" if reuse <= 100 else "FAIL"
        return {"ratio": round(reuse, 1), "tier": tier_val}
    return None


def _write_ratio_value(cachegrind: dict) -> float | None:
    """Compute write ratio from cachegrind, preferring per-file max."""
    files = cachegrind.get("files", [])
    if files:
        vals = [float(f.get("Dw", 0)) / float(f.get("Dr", 0)) for f in files if f.get("Dr", 0) > 0]
        if vals:
            return max(vals)
    total_dr = cachegrind.get("summary", {}).get("Dr", 0)
    total_dw = cachegrind.get("summary", {}).get("Dw", 0)
    if total_dr > 0:
        return total_dw / total_dr
    return None


def _score_write_amplification(cachegrind: dict) -> dict | None:
    """Score write amplification from cachegrind D-write vs D-read data."""
    if not cachegrind or cachegrind.get("error"):
        return None
    wr = _write_ratio_value(cachegrind)
    if wr is not None:
        tier_val = "PASS" if wr <= 0.2 else "WARN" if wr <= 0.5 else "FAIL"
        return {"ratio": round(wr, 3), "tier": tier_val}
    return None


def _score_allocation_churn(massif: dict) -> dict | None:
    """Score allocation churn from massif data."""
    if massif and not massif.get("error"):
        peaks = massif.get("local_maxima_count", 0)
        tier_val = "PASS" if peaks <= 2 else "WARN" if peaks <= 5 else "FAIL"
        return {"peaks": peaks, "tier": tier_val}
    return None


def _score_multiplicative_paths(callgrind: dict) -> dict | None:
    """Score multiplicative paths from callgrind data."""
    if callgrind and not callgrind.get("error") and "multiplicative_path_count" in callgrind:
        path_count = int(callgrind.get("multiplicative_path_count", 0))
        tier_val = "PASS" if path_count == 0 else "WARN" if path_count == 1 else "FAIL"
        return {"path_count": path_count, "tier": tier_val}
    return None


def _collect_algorithmic_sub_checks(
    tier1: dict, tier234: dict, args: argparse.Namespace
) -> dict[str, dict]:
    """Run every algorithmic sub-check and return {name: result} for the scored ones."""
    sub_checks: dict[str, dict] = {}
    input_size = args.valgrind_size
    callgrind = tier234.get("callgrind", {})
    cachegrind = tier234.get("cachegrind", {})
    massif = tier234.get("massif", {})

    ce = _score_scaling_exponent(tier1, args)
    if ce is not None:
        sub_checks["complexity_exponent"] = ce
    ca = _score_call_amplification(callgrind, input_size)
    if ca is not None:
        sub_checks["call_amplification"] = ca
    dr = _score_data_reuse(cachegrind, input_size)
    if dr is not None:
        sub_checks["data_reuse"] = dr
    wa = _score_write_amplification(cachegrind)
    if wa is not None:
        sub_checks["write_amplification"] = wa
    ac = _score_allocation_churn(massif)
    if ac is not None:
        sub_checks["allocation_churn"] = ac
    mp = _score_multiplicative_paths(callgrind)
    if mp is not None:
        sub_checks["multiplicative_paths"] = mp
    return sub_checks


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
    sub_checks = _collect_algorithmic_sub_checks(tier1, tier234, args)

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


def _pytest_benchmark_cv(benchmarks: list[dict[str, Any]]) -> float | None:
    if benchmarks:
        cvs = [
            benchmark.get("stats", {}).get("stddev", 0)
            / max(benchmark.get("stats", {}).get("mean", 1e-12), 1e-12)
            * 100
            for benchmark in benchmarks
        ]
        return sum(cvs) / len(cvs) if cvs else 0.0
    return None


def _explicit_size_wall_time_cv(time_usage_by_size: dict) -> tuple[float, dict[int, float]] | None:
    if not time_usage_by_size:
        return None
    cv_by_size = {
        int(size): round(
            _cv([run.get("wall_seconds", 0.0) for run in runs if run.get("wall_seconds")]),
            2,
        )
        for size, runs in time_usage_by_size.items()
        if any(run.get("wall_seconds") for run in runs)
    }
    return (max(cv_by_size.values()) if cv_by_size else -1.0, cv_by_size)


def _flat_wall_time_cv(time_usage: list[dict[str, Any]]) -> float:
    times = [item.get("wall_seconds", 0) for item in time_usage if item.get("wall_seconds")]
    return _cv(times) if times else -1.0


def _wall_time_cv_payload(tier1: dict) -> tuple[float, dict[int, float] | None]:
    pb = tier1.get("pytest_benchmark", {})
    benchmark_cv = _pytest_benchmark_cv(pb.get("benchmarks", []))
    if benchmark_cv is not None:
        return benchmark_cv, None

    explicit_size_cv = _explicit_size_wall_time_cv(tier1.get("time_usage_by_size", {}))
    if explicit_size_cv is not None:
        return explicit_size_cv

    return _flat_wall_time_cv(tier1.get("time_usage", [])), None


def score_wall_time_stability(tier1: dict, max_cv: float = 5.0) -> dict[str, Any]:
    """Dimension 1: wall-time CV.  CV > *max_cv* ⇒ tier ``N/A (noise)``, excluded from total."""
    avg_cv, cv_by_size = _wall_time_cv_payload(tier1)

    if avg_cv < 0:
        return {"score": -1, "tier": "N/A", "cv": None}

    if avg_cv > max_cv:
        return {"score": -1, "tier": "N/A (noise)", "cv": round(avg_cv, 2)}

    tier_val = "PASS" if avg_cv <= 3 else "WARN" if avg_cv <= 8 else "FAIL"
    score = 4 if tier_val == "PASS" else 2 if tier_val == "WARN" else 0
    result: dict[str, Any] = {"score": score, "tier": tier_val, "cv": round(avg_cv, 2)}
    if cv_by_size is not None:
        result["cv_by_size"] = cv_by_size
    return result


# ── score_cpu_efficiency helpers ───────────────────────────────────────────


def _score_concentration(
    concentration: float | None, current_score: int, current_tier: str
) -> tuple[int, str, dict[str, Any]]:
    """Assess hotspot concentration and return (score, tier, evidence)."""
    if concentration is None:
        return current_score, current_tier, {}
    if concentration > 35:
        return min(current_score, 0), "FAIL", {"top_fn_pct": concentration}
    if concentration > 20:
        return (
            min(current_score, 2),
            "WARN" if current_tier == "PASS" else current_tier,
            {"top_fn_pct": concentration},
        )
    return current_score, current_tier, {"top_fn_pct": concentration}


def _score_ipc(
    ipc: float | None, current_score: int, current_tier: str
) -> tuple[int, str, dict[str, Any]]:
    """Assess IPC and return (score, tier, evidence)."""
    if ipc is None:
        return current_score, current_tier, {}
    if ipc < 1.0:
        return 0, "FAIL", {"IPC": ipc}
    if ipc < 1.5:
        return (
            min(current_score, 2),
            "WARN" if current_tier == "PASS" else current_tier,
            {"IPC": ipc},
        )
    return current_score, current_tier, {"IPC": ipc}


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

    score, tier_val, evidence = _score_concentration(concentration, 4, "PASS")
    s, t, e = _score_ipc(ipc, score, tier_val)
    return {"score": s, "tier": t, **evidence, **e}


def _cache_file_metric_values(cachegrind: dict[str, Any], metric_key: str) -> list[float]:
    return [
        file_data.get(metric_key, 0)
        for file_data in cachegrind.get("files", [])
        if file_data.get(metric_key) is not None
    ]


def _cache_summary_metric_values(summary: dict[str, Any], metric_key: str) -> list[float]:
    if metric_key == "L1d_miss_pct" and summary.get("Dr", 0) > 0:
        return [100.0 * summary.get("D1mr", 0) / summary["Dr"]]
    if metric_key == "LL_miss_pct" and (summary.get("Dr", 0) + summary.get("Dw", 0)) > 0:
        total = summary.get("Dr", 0) + summary.get("Dw", 0)
        return [100.0 * (summary.get("DLmr", 0) + summary.get("DLmw", 0)) / total]
    if metric_key == "branch_mispred_pct" and summary.get("Bc", 0) > 0:
        return [100.0 * summary.get("Bcm", 0) / summary["Bc"]]
    return []


def _cache_metric_values(cachegrind: dict[str, Any], metric_key: str) -> list[float]:
    values = _cache_file_metric_values(cachegrind, metric_key)
    if values:
        return values
    return _cache_summary_metric_values(cachegrind.get("summary", {}), metric_key)


def score_cache_dim(tier234: dict, metric_key: str, pass_t: float, warn_t: float) -> dict[str, Any]:
    """Generic cache dimension scorer."""
    cachegrind = tier234.get("cachegrind", {})
    if not cachegrind or cachegrind.get("error"):
        return {"score": -1, "tier": "N/A"}

    values = _cache_metric_values(cachegrind, metric_key)
    if not values:
        return {"score": -1, "tier": "N/A"}

    worst = max(values)
    tier_val = "PASS" if worst <= pass_t else "WARN" if worst <= warn_t else "FAIL"
    score = 4 if tier_val == "PASS" else 2 if tier_val == "WARN" else 0
    return {"score": score, "tier": tier_val, "worst_pct": round(worst, 3)}


# ── score_memory_profile helpers ───────────────────────────────────────────


def _resolve_peak_bytes(tier1: dict, tier234: dict) -> tuple[int, str]:
    """Determine peak bytes and data source (massif or tracemalloc)."""
    massif = tier234.get("massif", {})
    if massif and not massif.get("error") and massif.get("peak_bytes", 0) > 0:
        return massif["peak_bytes"], "massif"

    tracemalloc = tier1.get("tracemalloc", {})
    if tracemalloc and tracemalloc.get("peak_bytes", 0) > 0:
        return tracemalloc["peak_bytes"], "tracemalloc"

    return 0, "none"


def _score_memory_vs_baseline(peak_bytes: int, baseline: dict, source: str) -> dict | None:
    """Score memory against a baseline if one exists. Returns None if not applicable."""
    base_peak = (
        baseline.get("rubric", {})
        .get("dimensions", {})
        .get("Memory Profile", {})
        .get("peak_bytes", 0)
    )
    if base_peak <= 0:
        return None
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


def score_memory_profile(tier1: dict, tier234: dict, baseline: dict | None) -> dict[str, Any]:
    """Dimension 6: memory profile."""
    peak_bytes, source = _resolve_peak_bytes(tier1, tier234)

    if not peak_bytes:
        return {"score": -1, "tier": "N/A"}

    if baseline:
        result = _score_memory_vs_baseline(peak_bytes, baseline, source)
        if result is not None:
            return result

    massif = tier234.get("massif", {})
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

    max_cv = getattr(args, "max_cv", 5.0)

    dimensions: list[tuple[str, dict]] = [
        ("Algorithmic Scaling", score_algorithmic_scaling(tier1, tier234, args)),
        ("Wall-Time Stability", score_wall_time_stability(tier1, max_cv=max_cv)),
        ("CPU Efficiency", score_cpu_efficiency(tier234)),
        ("L1 Cache Efficiency", score_cache_dim(tier234, "L1d_miss_pct", 1.0, 5.0)),
        ("Last-Level Cache", score_cache_dim(tier234, "LL_miss_pct", 0.5, 2.0)),
        ("Branch Prediction", score_cache_dim(tier234, "branch_mispred_pct", 1.0, 3.0)),
        ("Memory Profile", score_memory_profile(tier1, tier234, baseline)),
    ]

    available = [
        (name, dimension)
        for name, dimension in dimensions
        if dimension.get("tier") not in ("N/A", "N/A (noise)")
    ]
    total = sum(dimension["score"] for _, dimension in available)
    max_possible = len(available) * 4
    baseline_regressions = _collect_baseline_regressions(dimensions, baseline)
    return {
        "dimensions": dimensions,
        "total": total,
        "max_possible": max_possible,
        "baseline_regressions": baseline_regressions,
    }
