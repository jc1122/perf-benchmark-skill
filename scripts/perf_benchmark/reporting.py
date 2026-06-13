from __future__ import annotations

import json
import os
import platform
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["write_markdown_report", "write_json_summary"]


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _environment_fingerprint() -> dict[str, Any]:
    cpu_model = ""
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    governor_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    smt_path = Path("/sys/devices/system/cpu/smt/active")
    return {
        "cpu_model": cpu_model,
        "kernel": platform.release(),
        "governor": governor_path.read_text().strip() if governor_path.exists() else "unknown",
        "smt": smt_path.read_text().strip() if smt_path.exists() else "unknown",
        "load_avg_1m": round(os.getloadavg()[0], 2),
        "python_version": platform.python_version(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _first_present_metric(check: dict[str, Any], keys: list[str]) -> Any:
    """Return the first present metric value without dropping zero."""
    for key in keys:
        if key in check:
            return check[key]
    return ""


def _dimension_by_name(rubric: dict, name: str) -> dict[str, Any]:
    for dimension_name, dimension in rubric.get("dimensions", []):
        if dimension_name == name:
            return dimension
    return {"score": -1, "tier": "N/A", "sub_checks": {}, "note": f"Missing dimension: {name}"}


def _format_cache_model(prefix: str, cache: dict[str, Any]) -> str:
    return (
        f"{prefix}: D1={cache.get('D1', '?')}, I1={cache.get('I1', '?')}, LL={cache.get('LL', '?')}"
    )


def _wall_seconds(runs: list[dict[str, Any]]) -> list[float]:
    return [run["wall_seconds"] for run in runs if run.get("wall_seconds")]


def _summarize_pytest_benchmark_metrics(benchmarks: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not benchmarks:
        return None
    cvs = [
        round(
            benchmark.get("stats", {}).get("stddev", 0)
            / max(benchmark.get("stats", {}).get("mean", 1e-12), 1e-12)
            * 100,
            2,
        )
        for benchmark in benchmarks
    ]
    if not cvs:
        return None
    means = [
        round(benchmark.get("stats", {}).get("mean", 0), 4)
        for benchmark in benchmarks
        if benchmark.get("stats", {}).get("mean") is not None
    ]
    summary: dict[str, Any] = {
        "wall_time_cv": round(sum(cvs) / len(cvs), 2),
        "wall_time_cv_by_benchmark": cvs,
    }
    if means:
        summary["wall_time_mean"] = round(sum(means) / len(means), 4)
    return summary


def _summarize_size_wall_time_metrics(
    time_usage_by_size: dict[Any, list[dict[str, Any]]],
    cv_fn,
) -> dict[str, Any] | None:
    if not time_usage_by_size:
        return None
    cv_by_size: dict[str, float] = {}
    means_by_size: dict[str, float] = {}
    for size, runs in time_usage_by_size.items():
        walls = _wall_seconds(runs)
        if walls:
            key = str(int(size))
            cv_by_size[key] = round(cv_fn(walls), 2)
            means_by_size[key] = round(sum(walls) / len(walls), 4)
    if not cv_by_size:
        return None
    return {
        "wall_time_cv": max(cv_by_size.values()),
        "wall_time_cv_by_size": cv_by_size,
        "wall_time_mean_by_size": means_by_size,
    }


def _summarize_flat_wall_time_metrics(
    time_data: list[dict[str, Any]], cv_fn
) -> dict[str, Any] | None:
    walls = _wall_seconds(time_data)
    if not walls:
        return None
    return {
        "wall_time_cv": round(cv_fn(walls), 2),
        "wall_time_mean": round(sum(walls) / len(walls), 4),
    }


def _summarize_wall_time_metrics(tier1: dict, cv_fn) -> dict[str, Any]:
    """Return summary-friendly wall-time metrics aligned with the scorer."""
    summaries = (
        _summarize_pytest_benchmark_metrics(
            tier1.get("pytest_benchmark", {}).get("benchmarks", [])
        ),
        _summarize_size_wall_time_metrics(tier1.get("time_usage_by_size", {}), cv_fn),
        _summarize_flat_wall_time_metrics(tier1.get("time_usage", []), cv_fn),
    )
    return next((summary for summary in summaries if summary), {})


def _append_prerequisites_section(lines: list[str], prereqs: dict[str, Any]) -> dict[str, Any]:
    perf_status = "perf available"
    if prereqs["perf_paranoid"] > 1:
        perf_status = "perf UNAVAILABLE, run: sudo sysctl kernel.perf_event_paranoid=1"
    governor_status = "OK"
    if prereqs["governor"] != "performance":
        governor_status = "WARNING, set to performance for stable results"

    lines.extend(
        [
            "## Prerequisites",
            "",
            f"- Python: {sys.version.split()[0]} ({'OK' if prereqs['python_ok'] else 'FAIL'})",
            f"- Valgrind: {'found' if prereqs['valgrind'] else 'not found'}",
            (f"- perf_event_paranoid: {prereqs['perf_paranoid']} ({perf_status})"),
            f"- CPU governor: {prereqs['governor']} ({governor_status})",
            f"- RAM: {prereqs['ram_mb']}MB",
        ]
    )
    cache = prereqs.get("cache_topology", {})
    if cache:
        lines.append(_format_cache_model("- Cache model", cache))
    lines.append("")
    return cache


def _append_algorithmic_na_section(lines: list[str], dim0: dict[str, Any]) -> None:
    lines.append(f"*{dim0.get('note', 'Insufficient data for strict algorithmic scoring.')}*")
    lines.append("")
    if dim0.get("sub_checks"):
        lines.extend(
            [
                "| Available Sub-check | Value | Tier |",
                "|---------------------|-------|------|",
            ]
        )
        for name, check in dim0["sub_checks"].items():
            val = _first_present_metric(check, ["k", "ratio", "peaks", "path_count", "top_fn_ir"])
            lines.append(f"| {name} | {val} | {check['tier']} |")
        lines.append("")
    missing_sub_checks = dim0.get("missing_sub_checks", [])
    if missing_sub_checks:
        lines.append("Missing sub-checks:")
        for name in missing_sub_checks:
            lines.append(f"- `{name}`")
        lines.append("")
        if "complexity_exponent" in missing_sub_checks:
            lines.append(
                "*Add at least two real input sizes via `--sizes`, and ensure "
                "explicit `--target` commands use `{SIZE}`.*"
            )


def _append_algorithmic_result_section(lines: list[str], dim0: dict[str, Any]) -> None:
    lines.extend(
        [
            f"**Result: {dim0['tier']}** (score: {dim0['score']}/4)",
            "",
        ]
    )
    if dim0.get("sub_checks"):
        lines.extend(["| Sub-check | Value | Tier |", "|-----------|-------|------|"])
        for name, check in dim0["sub_checks"].items():
            val = _first_present_metric(check, ["k", "ratio", "peaks", "path_count", "top_fn_ir"])
            lines.append(f"| {name} | {val} | {check['tier']} |")
    if dim0["tier"] == "FAIL":
        lines.extend(
            [
                "",
                "> **STOP**: Fix algorithmic scaling before hardware-level optimization.",
                "> Expected impact: 10-1000x improvement.",
                "> Hardware optimizations (cache, branch, ASM) are irrelevant "
                "until this is resolved.",
            ]
        )


def _append_algorithmic_section(lines: list[str], rubric: dict[str, Any]) -> None:
    dim0 = _dimension_by_name(rubric, "Algorithmic Scaling")
    lines.extend(["## Algorithmic Scaling Analysis", ""])
    if dim0.get("tier") == "N/A":
        _append_algorithmic_na_section(lines, dim0)
    else:
        _append_algorithmic_result_section(lines, dim0)
    lines.append("")


def _append_baseline_section(lines: list[str], rubric: dict[str, Any], args) -> None:
    if not args.baseline:
        return
    regressions = rubric.get("baseline_regressions", [])
    lines.extend(["## Baseline Comparison", "", f"**Baseline**: `{args.baseline}`", ""])
    if regressions:
        lines.extend(
            [
                "> **Regression blocker**: one or more scored dimensions "
                "dropped versus the baseline.",
                "",
                "| Dimension | Baseline | Current | Tier Drop |",
                "|-----------|----------|---------|-----------|",
            ]
        )
        for regression in regressions:
            regression_row = (
                f"| {regression['dimension']} | {regression['baseline_tier']} | "
                f"{regression['current_tier']} | {regression['drop']} |"
            )
            lines.append(regression_row)
    else:
        lines.append("No scored dimension regressed against the supplied baseline.")
    lines.append("")


def _append_rubric_scorecard(lines: list[str], rubric: dict[str, Any]) -> None:
    lines.extend(
        ["## Rubric Scorecard", "", f"**Total: {rubric['total']}/{rubric['max_possible']}**", ""]
    )
    lines.extend(["| # | Dimension | Score | Tier |", "|---|-----------|-------|------|"])
    for index, (name, dimension) in enumerate(rubric["dimensions"]):
        score_str = f"{dimension['score']}/4" if dimension.get("tier") != "N/A" else "N/A"
        lines.append(f"| {index} | {name} | {score_str} | {dimension.get('tier', 'N/A')} |")
    lines.append("")


def _append_findings_section(lines: list[str], rubric: dict[str, Any]) -> None:
    lines.extend(["## Findings", ""])
    for severity in ("FAIL", "WARN"):
        for name, dimension in rubric["dimensions"]:
            if dimension.get("tier") == severity:
                lines.extend([f"### [{severity}] {name}", ""])
                for key, value in dimension.items():
                    if key not in ("score", "tier", "sub_checks"):
                        lines.append(f"- **{key}**: {value}")
                lines.append("")


def _append_native_hotspots(lines: list[str], tier234: dict[str, Any]) -> None:
    perf_record = tier234.get("perf_record")
    if not perf_record:
        return
    lines.extend(["## Native Hotspots", ""])
    if not perf_record.get("available", True):
        lines.append(f"*Unavailable: {perf_record.get('reason', 'unknown reason')}*")
    else:
        _append_available_hotspots(lines, perf_record)
        _append_perf_artifact_lines(lines, perf_record)
    lines.append("")


def _append_available_hotspots(lines: list[str], perf_record: dict[str, Any]) -> None:
    hotspots = perf_record.get("hotspots", [])
    if hotspots:
        lines.extend(
            [
                "| Overhead | Command | Shared Object | Symbol |",
                "|----------|---------|---------------|--------|",
            ]
        )
        for hotspot in hotspots[:5]:
            row = (
                f"| {hotspot.get('overhead_pct', 0)} | "
                f"{hotspot.get('command', '')} | "
                f"{hotspot.get('shared_object', '')} | "
                f"{hotspot.get('symbol', '')} |"
            )
            lines.append(row)
    else:
        error_message = (
            perf_record.get("parse_error")
            or perf_record.get("report_error")
            or "No hotspots parsed."
        )
        lines.append(f"*{error_message}*")


def _append_perf_artifact_lines(lines: list[str], perf_record: dict[str, Any]) -> None:
    artifact_lines: list[str] = []
    if perf_record.get("data_path"):
        artifact_lines.append(f"- perf.data: `{perf_record['data_path']}`")
    if perf_record.get("report_path"):
        artifact_lines.append(f"- perf report: `{perf_record['report_path']}`")
    if artifact_lines:
        lines.append("")
        lines.extend(artifact_lines)


def _append_prescriptions(lines: list[str], rubric: dict[str, Any]) -> None:
    lines.extend(
        [
            "## Prescriptions",
            "",
            "*Priority order: Algorithmic > Data Layout > Execution > Micro*",
            "",
        ]
    )
    prescriptions = {
        "Algorithmic": "Review scaling sub-checks. Memoize, precompute, or restructure hot paths.",
        "L1": "Improve data locality: struct-of-arrays, cache-line alignment, sequential access.",
        "Last-Level": "Reduce working set size or improve spatial locality.",
        "Branch": (
            "Replace unpredictable branches with cmov, lookup tables, or branchless arithmetic."
        ),
        "CPU": "Reduce hotspot concentration. Consider splitting large functions.",
        "Memory": "Pre-allocate buffers, use object pools, reduce allocation churn.",
        "Wall": "Reduce measurement noise: set governor=performance, increase rounds.",
    }
    for name, dimension in rubric["dimensions"]:
        if dimension.get("tier") in ("FAIL", "WARN"):
            advice = next(
                (value for key, value in prescriptions.items() if key in name),
                "See rubric for details.",
            )
            lines.append(f"- **{name}**: {advice}")
    lines.append("")


def _append_cache_model(lines: list[str], cache: dict[str, Any]) -> None:
    lines.extend(
        [
            "## Cache Model",
            "",
            "Valgrind cachegrind simulates a 2-level cache (L1 -> LL). No separate L2 simulation.",
        ]
    )
    if cache:
        lines.append(_format_cache_model("Simulated", cache))
    lines.extend(
        [
            "On hybrid CPUs (Intel Alder/Raptor Lake), P-core cache hierarchy is simulated.",
            "",
        ]
    )


def write_markdown_report(
    rubric: dict,
    tier1: dict,
    tier234: dict,
    prereqs: dict,
    *extra,
) -> None:
    args = extra[0]
    out_dir = extra[1]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = [
        "# Performance Benchmark Report",
        "",
        f"**Generated**: {now}",
        f"**Root**: `{args.root}`",
        f"**Tier**: {args.tier}",
    ]
    if args.sizes:
        lines.append(f"**Sizes**: {args.sizes}")
    lines.append("")
    cache = _append_prerequisites_section(lines, prereqs)
    _append_algorithmic_section(lines, rubric)
    _append_baseline_section(lines, rubric, args)
    _append_rubric_scorecard(lines, rubric)
    _append_findings_section(lines, rubric)
    _append_native_hotspots(lines, tier234)
    _append_prescriptions(lines, rubric)
    _append_cache_model(lines, cache)

    (out_dir / "benchmark_report.md").write_text("\n".join(lines))
    _log(f"  -> Wrote {out_dir / 'benchmark_report.md'}")


def build_summary_contract(rubric: dict) -> dict:
    """Stable top-level signals for repo-B's synthesis gate (decoupled from rubric)."""
    dims = dict(rubric.get("dimensions", []))
    algo = dims.get("Algorithmic Scaling", {})
    k = algo.get("sub_checks", {}).get("complexity_exponent", {}).get("k")
    cpu_tier = dims.get("CPU Efficiency", {}).get("tier")
    return {
        "complexity_exponent": k,
        "deterministic_tier": cpu_tier not in (None, "N/A"),
    }


def _base_json_summary(rubric: dict, prereqs: dict, args) -> dict[str, Any]:
    return {
        **build_summary_contract(
            rubric
        ),  # complexity_exponent, deterministic_tier (top-level contract)
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(args.root),
        "tier": args.tier,
        "rubric": {
            "total": rubric["total"],
            "max_possible": rubric["max_possible"],
            "dimensions": {name: dimension for name, dimension in rubric["dimensions"]},
        },
        "prerequisites": {
            "python_ok": prereqs["python_ok"],
            "valgrind": prereqs["valgrind"] is not None,
            "perf_paranoid": prereqs["perf_paranoid"],
            "governor": prereqs["governor"],
            "cache_topology": prereqs.get("cache_topology", {}),
            "ram_mb": prereqs["ram_mb"],
        },
        "baseline_regressions": rubric.get("baseline_regressions", []),
        "regression_blocker": bool(rubric.get("baseline_regressions")),
    }


def _wall_time_samples(tier1: dict[str, Any]) -> list[float]:
    time_data = tier1.get("time_usage", [])
    walls = [item.get("wall_seconds", 0.0) for item in time_data if item.get("wall_seconds")]
    if not walls:
        time_usage_by_size = tier1.get("time_usage_by_size", {})
        for runs in time_usage_by_size.values():
            walls.extend(run.get("wall_seconds", 0.0) for run in runs if run.get("wall_seconds"))
    return walls


def _add_wall_time_percentiles(summary: dict[str, Any], tier1: dict[str, Any]) -> None:
    walls = _wall_time_samples(tier1)
    if len(walls) >= 2:
        q = statistics.quantiles(walls, n=100)
        summary["wall_time_percentiles"] = {
            "p50": q[49],
            "p95": q[94],
            "p99": q[98],
        }


def _add_memory_peaks(
    summary: dict[str, Any], tier1: dict[str, Any], tier234: dict[str, Any]
) -> None:
    tracemalloc = tier1.get("tracemalloc", {})
    if tracemalloc and tracemalloc.get("peak_bytes"):
        summary["tracemalloc_peak_bytes"] = tracemalloc["peak_bytes"]

    massif = tier234.get("massif", {})
    if massif and massif.get("peak_bytes"):
        summary["massif_peak_bytes"] = massif["peak_bytes"]


def _perf_record_summary(perf_record: dict[str, Any]) -> dict[str, Any]:
    perf_record_summary = {"available": perf_record.get("available", True)}
    for key in ("reason", "data_path", "report_path", "report_error", "parse_error"):
        if key in perf_record:
            perf_record_summary[key] = perf_record[key]
    if "hotspots" in perf_record:
        perf_record_summary["hotspots"] = perf_record.get("hotspots", [])[:5]
    return perf_record_summary


def _add_perf_record_summary(summary: dict[str, Any], tier234: dict[str, Any]) -> None:
    perf_record = tier234.get("perf_record", {})
    if perf_record:
        summary["perf_record"] = _perf_record_summary(perf_record)


def write_json_summary(
    rubric: dict,
    tier1: dict,
    tier234: dict,
    prereqs: dict,
    *extra,
) -> dict[str, Any]:
    args = extra[0]
    out_dir = extra[1]
    cv_fn = extra[2]
    summary = _base_json_summary(rubric, prereqs, args)
    summary.update(_summarize_wall_time_metrics(tier1, cv_fn))
    summary["environment"] = _environment_fingerprint()
    _add_wall_time_percentiles(summary, tier1)
    _add_memory_peaks(summary, tier1, tier234)
    _add_perf_record_summary(summary, tier234)

    (out_dir / "benchmark_summary.json").write_text(json.dumps(summary, indent=2))
    _log(f"  -> Wrote {out_dir / 'benchmark_summary.json'}")
    return summary
