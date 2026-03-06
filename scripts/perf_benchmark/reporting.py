from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["write_markdown_report", "write_json_summary"]


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _first_present_metric(check: dict[str, Any], keys: list[str]) -> Any:
    """Return the first present metric value without dropping zero."""
    for key in keys:
        if key in check:
            return check[key]
    return ""


def _summarize_wall_time_metrics(tier1: dict, cv_fn) -> dict[str, Any]:
    """Return summary-friendly wall-time metrics aligned with the scorer."""
    pytest_benchmark = tier1.get("pytest_benchmark", {})
    benchmarks = pytest_benchmark.get("benchmarks", [])
    if benchmarks:
        cvs = [
            round(
                benchmark.get("stats", {}).get("stddev", 0)
                / max(benchmark.get("stats", {}).get("mean", 1e-12), 1e-12)
                * 100,
                2,
            )
            for benchmark in benchmarks
        ]
        means = [
            round(benchmark.get("stats", {}).get("mean", 0), 4)
            for benchmark in benchmarks
            if benchmark.get("stats", {}).get("mean") is not None
        ]
        if cvs:
            summary: dict[str, Any] = {
                "wall_time_cv": round(sum(cvs) / len(cvs), 2),
                "wall_time_cv_by_benchmark": cvs,
            }
            if means:
                summary["wall_time_mean"] = round(sum(means) / len(means), 4)
            return summary

    time_usage_by_size = tier1.get("time_usage_by_size", {})
    if time_usage_by_size:
        cv_by_size = {
            str(int(size)): round(
                cv_fn(
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
        means_by_size = {
            str(int(size)): round(
                sum(run["wall_seconds"] for run in runs if run.get("wall_seconds"))
                / len([run for run in runs if run.get("wall_seconds")]),
                4,
            )
            for size, runs in time_usage_by_size.items()
            if any(run.get("wall_seconds") for run in runs)
        }
        if cv_by_size:
            return {
                "wall_time_cv": max(cv_by_size.values()),
                "wall_time_cv_by_size": cv_by_size,
                "wall_time_mean_by_size": means_by_size,
            }

    time_data = tier1.get("time_usage", [])
    walls = [item.get("wall_seconds", 0) for item in time_data if item.get("wall_seconds")]
    if walls:
        return {
            "wall_time_cv": round(cv_fn(walls), 2),
            "wall_time_mean": round(sum(walls) / len(walls), 4),
        }
    return {}


def write_markdown_report(
    rubric: dict,
    tier1: dict,
    tier234: dict,
    prereqs: dict,
    args,
    out_dir: Path,
) -> None:
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

    lines.extend(
        [
            "## Prerequisites",
            "",
            f"- Python: {sys.version.split()[0]} ({'OK' if prereqs['python_ok'] else 'FAIL'})",
            f"- Valgrind: {'found' if prereqs['valgrind'] else 'not found'}",
            (
                f"- perf_event_paranoid: {prereqs['perf_paranoid']} "
                f"({'perf available' if prereqs['perf_paranoid'] <= 1 else 'perf UNAVAILABLE — run: sudo sysctl kernel.perf_event_paranoid=1'})"
            ),
            f"- CPU governor: {prereqs['governor']} ({'OK' if prereqs['governor'] == 'performance' else 'WARNING — set to performance for stable results'})",
            f"- RAM: {prereqs['ram_mb']}MB",
        ]
    )
    cache = prereqs.get("cache_topology", {})
    if cache:
        lines.append(
            f"- Cache model: D1={cache.get('D1', '?')}, I1={cache.get('I1', '?')}, LL={cache.get('LL', '?')}"
        )
    lines.append("")

    dim0 = rubric["dimensions"][0][1]
    lines.extend(["## Algorithmic Scaling Analysis", ""])
    if dim0.get("tier") == "N/A":
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
                    "*Add at least two real input sizes via `--sizes`, and ensure explicit `--target` commands use `{SIZE}`.*"
                )
    else:
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
                    "> Hardware optimizations (cache, branch, ASM) are irrelevant until this is resolved.",
                ]
            )
    lines.append("")

    if args.baseline:
        regressions = rubric.get("baseline_regressions", [])
        lines.extend(["## Baseline Comparison", "", f"**Baseline**: `{args.baseline}`", ""])
        if regressions:
            lines.extend(
                [
                    "> **Regression blocker**: one or more scored dimensions dropped versus the baseline.",
                    "",
                    "| Dimension | Baseline | Current | Tier Drop |",
                    "|-----------|----------|---------|-----------|",
                ]
            )
            for regression in regressions:
                lines.append(
                    f"| {regression['dimension']} | {regression['baseline_tier']} | {regression['current_tier']} | {regression['drop']} |"
                )
        else:
            lines.append("No scored dimension regressed against the supplied baseline.")
        lines.append("")

    lines.extend(["## Rubric Scorecard", "", f"**Total: {rubric['total']}/{rubric['max_possible']}**", ""])
    lines.extend(["| # | Dimension | Score | Tier |", "|---|-----------|-------|------|"])
    for index, (name, dimension) in enumerate(rubric["dimensions"]):
        score_str = f"{dimension['score']}/4" if dimension.get("tier") != "N/A" else "N/A"
        lines.append(f"| {index} | {name} | {score_str} | {dimension.get('tier', 'N/A')} |")
    lines.append("")

    lines.extend(["## Findings", ""])
    for severity in ("FAIL", "WARN"):
        for name, dimension in rubric["dimensions"]:
            if dimension.get("tier") == severity:
                lines.extend([f"### [{severity}] {name}", ""])
                for key, value in dimension.items():
                    if key not in ("score", "tier", "sub_checks"):
                        lines.append(f"- **{key}**: {value}")
                lines.append("")

    lines.extend(["## Prescriptions", "", "*Priority order: Algorithmic > Data Layout > Execution > Micro*", ""])
    prescriptions = {
        "Algorithmic": "Review scaling sub-checks. Memoize, precompute, or restructure hot paths.",
        "L1": "Improve data locality: struct-of-arrays, cache-line alignment, sequential access.",
        "Last-Level": "Reduce working set size or improve spatial locality.",
        "Branch": "Replace unpredictable branches with cmov, lookup tables, or branchless arithmetic.",
        "CPU": "Reduce hotspot concentration. Consider splitting large functions.",
        "Memory": "Pre-allocate buffers, use object pools, reduce allocation churn.",
        "Wall": "Reduce measurement noise: set governor=performance, increase rounds.",
    }
    for name, dimension in rubric["dimensions"]:
        if dimension.get("tier") in ("FAIL", "WARN"):
            advice = next((value for key, value in prescriptions.items() if key in name), "See rubric for details.")
            lines.append(f"- **{name}**: {advice}")
    lines.append("")

    lines.extend(
        [
            "## Cache Model",
            "",
            "Valgrind cachegrind simulates a 2-level cache (L1 -> LL). No separate L2 simulation.",
        ]
    )
    if cache:
        lines.append(
            f"Simulated: D1={cache.get('D1', '?')}, I1={cache.get('I1', '?')}, LL={cache.get('LL', '?')}"
        )
    lines.extend(
        [
            "On hybrid CPUs (Intel Alder/Raptor Lake), P-core cache hierarchy is simulated.",
            "",
        ]
    )

    (out_dir / "benchmark_report.md").write_text("\n".join(lines))
    _log(f"  -> Wrote {out_dir / 'benchmark_report.md'}")


def write_json_summary(
    rubric: dict,
    tier1: dict,
    tier234: dict,
    prereqs: dict,
    args,
    out_dir: Path,
    cv_fn,
) -> None:
    summary: dict[str, Any] = {
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
    summary.update(_summarize_wall_time_metrics(tier1, cv_fn))

    tracemalloc = tier1.get("tracemalloc", {})
    if tracemalloc and tracemalloc.get("peak_bytes"):
        summary["tracemalloc_peak_bytes"] = tracemalloc["peak_bytes"]

    massif = tier234.get("massif", {})
    if massif and massif.get("peak_bytes"):
        summary["massif_peak_bytes"] = massif["peak_bytes"]

    (out_dir / "benchmark_summary.json").write_text(json.dumps(summary, indent=2))
    _log(f"  -> Wrote {out_dir / 'benchmark_summary.json'}")
