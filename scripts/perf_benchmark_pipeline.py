#!/usr/bin/env python3
"""Linux performance benchmark pipeline.

Orchestrates profiling tools (Valgrind, perf, pytest-benchmark) across 4 tiers
and scores results against a 7-dimension rubric (0-28).

Usage:
    python perf_benchmark_pipeline.py --root /path/to/repo --out-dir /tmp/bench \\
        --source-prefix path/to/source/ --tier medium --sizes 10000,100000

Exit codes:
    0  All stages succeeded
    1  One or more stages failed (partial results still written)
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

_reporting = importlib.import_module("perf_benchmark.reporting")
_scoring = importlib.import_module("perf_benchmark.scoring")
_stage_helpers = importlib.import_module("perf_benchmark.stage_helpers")
_support = importlib.import_module("perf_benchmark.support")

_write_json_summary = _reporting.write_json_summary
write_markdown_report = _reporting.write_markdown_report
_cv = _scoring._cv
_fit_exponent = _scoring._fit_exponent
score_algorithmic_scaling = _scoring.score_algorithmic_scaling
score_cache_dim = _scoring.score_cache_dim
score_cpu_efficiency = _scoring.score_cpu_efficiency
score_memory_profile = _scoring.score_memory_profile
score_rubric = _scoring.score_rubric
score_wall_time_stability = _scoring.score_wall_time_stability
_discover_objdump_targets = _stage_helpers._discover_objdump_targets
_generate_tracemalloc_wrapper = _stage_helpers._generate_tracemalloc_wrapper
_parse_cachegrind_summary = _stage_helpers._parse_cachegrind_summary
_parse_callgrind_output = _stage_helpers._parse_callgrind_output
_parse_callgrind_raw = _stage_helpers._parse_callgrind_raw
_parse_gnu_time = _stage_helpers._parse_gnu_time
_parse_massif_out = _stage_helpers._parse_massif_out
_parse_perf_report = _stage_helpers._parse_perf_report
_parse_perf_stat = _stage_helpers._parse_perf_stat
_tracemalloc_target_error = _stage_helpers._tracemalloc_target_error
_build_env = _support._build_env
_build_target_cmd = _support._build_target_cmd
_build_valgrind_target_cmd = _support._build_valgrind_target_cmd
_log = _support._log
check_prerequisites = _support.check_prerequisites
discover_targets = _support.discover_targets

DEFAULT_PERF_STAT_EVENTS = (
    "cycles,instructions,branches,branch-misses,"
    "L1-dcache-loads,L1-dcache-load-misses,L1-icache-load-misses,"
    "LLC-loads,LLC-load-misses,dTLB-loads,dTLB-load-misses"
)
MINIMAL_PERF_STAT_EVENTS = "cycles,instructions,branches,branch-misses"
PERF_EVENT_FAILURE_MARKERS = (
    "event syntax error",
    "no such event",
    "not supported",
    "cannot find pmu",
    "unknown tracepoint",
    "parser error",
)


def _stage_has_error(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("error"):
            return True
        return any(_stage_has_error(item) for item in value.values())
    if isinstance(value, list):
        return any(_stage_has_error(item) for item in value)
    return False


def _looks_like_unsupported_perf_event(stderr: str) -> bool:
    stderr_lower = stderr.lower()
    return any(marker in stderr_lower for marker in PERF_EVENT_FAILURE_MARKERS)


def stage_tier1(
    args: argparse.Namespace, prereqs: dict, targets: list[str], out_dir: Path
) -> dict[str, Any]:
    """Tier 1: wall time, tracemalloc, GNU time. Runs alone (timing-sensitive)."""
    tier1_dir = out_dir / "tier1"
    tier1_dir.mkdir(parents=True, exist_ok=True)
    env = _build_env(os.environ.copy(), args.env)
    results: dict[str, Any] = {}

    # 1. pytest-benchmark
    if targets and not args.binary:
        bench_json = tier1_dir / "pytest_benchmark.json"
        cmd = [
            args.python,
            "-m",
            "pytest",
            "-x",
            "-q",
            "--benchmark-enable",
            "--benchmark-only",
            f"--benchmark-json={bench_json}",
        ] + targets
        _log(f"  -> pytest-benchmark: {' '.join(cmd[:6])}...")
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(args.root), env=env)
        if bench_json.exists():
            try:
                results["pytest_benchmark"] = json.loads(bench_json.read_text())
            except json.JSONDecodeError:
                results["pytest_benchmark"] = {"error": "invalid JSON"}
        else:
            results["pytest_benchmark"] = {
                "error": f"exit {r.returncode}",
                "stderr": r.stderr[:500],
            }

    # 2. tracemalloc (Python only)
    if not args.binary:
        tracemalloc_out = tier1_dir / "tracemalloc.json"
        wrapper_path, wrapper_cmd = _generate_tracemalloc_wrapper(args, targets)
        try:
            target_error = _tracemalloc_target_error(wrapper_cmd)
            if target_error:
                results["tracemalloc"] = {"error": target_error}
            else:
                _log("  -> tracemalloc wrapper...")
                r = subprocess.run(
                    [
                        args.python,
                        str(wrapper_path),
                        str(tracemalloc_out),
                        json.dumps(str(args.root)),
                        json.dumps(wrapper_cmd),
                    ],
                    capture_output=True,
                    text=True,
                    cwd=str(args.root),
                    env=env,
                    timeout=300,
                )
                if r.returncode != 0:
                    results["tracemalloc"] = {
                        "error": f"exit {r.returncode}",
                        "stderr": r.stderr[:500],
                    }
                elif tracemalloc_out.exists():
                    results["tracemalloc"] = json.loads(tracemalloc_out.read_text())
                else:
                    results["tracemalloc"] = {"error": "missing tracemalloc output"}
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
            results["tracemalloc"] = {"error": str(e)}
        finally:
            wrapper_path.unlink(missing_ok=True)

    # 3. /usr/bin/time -v (repeated for CV)
    time_results: list[dict] = []
    time_usage_by_size: dict[int, list[dict[str, Any]]] = {}
    repeats = args.time_repeats
    size_runs = args.sizes if (args.target or args.binary) and args.sizes else [None]
    _log(f"  -> /usr/bin/time -v x{repeats}...")
    for size_value in size_runs:
        target_cmd = _build_target_cmd(args, targets, size_override=size_value)
        for _ in range(repeats):
            r = subprocess.run(
                ["/usr/bin/time", "-v"] + target_cmd,
                capture_output=True,
                text=True,
                cwd=str(args.root),
                env=env,
            )
            if r.returncode != 0:
                results["time_error"] = {
                    "error": f"exit {r.returncode}",
                    "stderr": r.stderr[:500],
                    "input_size": size_value,
                }
                break
            parsed = _parse_gnu_time(r.stderr)
            if parsed:
                if size_value is not None:
                    parsed["input_size"] = size_value
                    time_usage_by_size.setdefault(size_value, []).append(parsed)
                time_results.append(parsed)
        if results.get("time_error"):
            break
    results["time_usage"] = time_results
    if time_usage_by_size:
        results["time_usage_by_size"] = time_usage_by_size

    # Write raw time output
    if time_results:
        (tier1_dir / "time_usage.json").write_text(json.dumps(time_results, indent=2))

    return results


def stage_cachegrind(
    args: argparse.Namespace, prereqs: dict, targets: list[str], out_dir: Path
) -> dict[str, Any]:
    tier2_dir = out_dir / "tier2"
    tier2_dir.mkdir(parents=True, exist_ok=True)
    env = _build_env(os.environ.copy(), args.env)

    target_cmd = _build_valgrind_target_cmd(args, targets)
    cache = prereqs.get("cache_topology", {})
    outfile = tier2_dir / "cachegrind.out"

    cmd = ["valgrind", "--tool=cachegrind"]
    if cache.get("I1"):
        cmd.append(f"--I1={cache['I1']}")
    if cache.get("D1"):
        cmd.append(f"--D1={cache['D1']}")
    if cache.get("LL"):
        cmd.append(f"--LL={cache['LL']}")
    cmd += [f"--cachegrind-out-file={outfile}", "--"] + target_cmd

    _log("  -> cachegrind: running...")
    r = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(args.root),
        env=env,
        timeout=args.valgrind_timeout,
    )
    if not outfile.exists():
        return {"error": f"cachegrind failed (exit {r.returncode})", "stderr": r.stderr[:500]}
    if "Invalid argument" in r.stderr or "Bad option" in r.stderr:
        return {"error": "cachegrind bad flags", "stderr": r.stderr[:500]}

    # Annotate with source filtering
    ann_cmd = ["cg_annotate"]
    if args.source_prefix:
        ann_cmd += [f"--include={args.source_prefix}"]
    ann_cmd.append(str(outfile))
    ann_r = subprocess.run(
        ann_cmd,
        capture_output=True,
        text=True,
        timeout=args.valgrind_timeout,
    )
    annotated_path = tier2_dir / "cachegrind_annotated.txt"
    annotated_path.write_text(ann_r.stdout)

    _log("  -> cachegrind: done")
    return _parse_cachegrind_summary(ann_r.stdout)


def stage_callgrind(
    args: argparse.Namespace, prereqs: dict, targets: list[str], out_dir: Path
) -> dict[str, Any]:
    tier2_dir = out_dir / "tier2"
    tier2_dir.mkdir(parents=True, exist_ok=True)
    env = _build_env(os.environ.copy(), args.env)

    target_cmd = _build_valgrind_target_cmd(args, targets)
    outfile = tier2_dir / "callgrind.out"

    cmd = [
        "valgrind",
        "--tool=callgrind",
        f"--callgrind-out-file={outfile}",
        "--",
        *target_cmd,
    ]
    _log("  -> callgrind: running...")
    r = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(args.root),
        env=env,
        timeout=args.valgrind_timeout,
    )
    if not outfile.exists():
        return {"error": f"callgrind failed (exit {r.returncode})", "stderr": r.stderr[:500]}

    ann_cmd = [
        "callgrind_annotate",
        "--tree=both",
        "--inclusive=yes",
    ]
    if args.source_prefix:
        ann_cmd += [f"--include={args.source_prefix}"]
    ann_cmd.append(str(outfile))
    ann_r = subprocess.run(
        ann_cmd,
        capture_output=True,
        text=True,
        timeout=args.valgrind_timeout,
    )
    (tier2_dir / "callgrind_annotated.txt").write_text(ann_r.stdout)

    _log("  -> callgrind: done")
    result = _parse_callgrind_output(ann_r.stdout)
    try:
        result.update(_parse_callgrind_raw(outfile.read_text(), args.valgrind_size))
    except OSError:
        result["raw_parse_error"] = "cannot read callgrind.out"
    return result


def stage_massif(
    args: argparse.Namespace, prereqs: dict, targets: list[str], out_dir: Path
) -> dict[str, Any]:
    tier3_dir = out_dir / "tier3"
    tier3_dir.mkdir(parents=True, exist_ok=True)
    env = _build_env(os.environ.copy(), args.env)

    target_cmd = _build_valgrind_target_cmd(args, targets)
    outfile = tier3_dir / "massif.out"

    cmd = [
        "valgrind",
        "--tool=massif",
        f"--massif-out-file={outfile}",
        "--",
        *target_cmd,
    ]
    _log("  -> massif: running...")
    r = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(args.root),
        env=env,
        timeout=args.valgrind_timeout,
    )

    # Generate ms_print as human artifact
    ms_print_path = shutil.which("ms_print")
    if outfile.exists() and ms_print_path:
        ms_r = subprocess.run(
            [ms_print_path, str(outfile)],
            capture_output=True,
            text=True,
            timeout=args.valgrind_timeout,
        )
        (tier3_dir / "massif_ms_print.txt").write_text(ms_r.stdout)
    elif outfile.exists():
        _log("  INFO: ms_print not found. Skipping Massif text rendering.")

    _log("  -> massif: done")
    if outfile.exists():
        return _parse_massif_out(outfile)
    return {"error": f"massif failed (exit {r.returncode})"}


def stage_perf_stat(
    args: argparse.Namespace, prereqs: dict, targets: list[str], out_dir: Path
) -> dict[str, Any]:
    if prereqs.get("perf_paranoid", 99) > 1:
        return {"available": False, "reason": f"perf_event_paranoid={prereqs['perf_paranoid']}"}
    if not shutil.which("perf"):
        return {"available": False, "reason": "perf not found"}

    tier3_dir = out_dir / "tier3"
    tier3_dir.mkdir(parents=True, exist_ok=True)
    env = _build_env(os.environ.copy(), args.env)

    target_cmd = _build_target_cmd(args, targets)
    events = args.perf_events or DEFAULT_PERF_STAT_EVENTS

    def run_perf_stat(event_set: str) -> subprocess.CompletedProcess[str]:
        cmd = ["perf", "stat", "-r", str(args.perf_repeats), "-e", event_set, "--", *target_cmd]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(args.root),
            env=env,
            timeout=args.valgrind_timeout,
        )

    _log("  -> perf stat: running...")
    r = run_perf_stat(events)
    stderr_blocks = [r.stderr]
    if (
        r.returncode != 0
        and args.perf_events is None
        and _looks_like_unsupported_perf_event(r.stderr)
    ):
        _log("  -> perf stat: retrying with minimal portable event set...")
        events = MINIMAL_PERF_STAT_EVENTS
        r = run_perf_stat(events)
        stderr_blocks.extend(
            [
                "\n[perf stat fallback to minimal event set]\n",
                r.stderr,
            ]
        )
    (tier3_dir / "perf_stat.txt").write_text("".join(stderr_blocks))
    if r.returncode != 0:
        return {"error": f"perf stat failed (exit {r.returncode})", "stderr": r.stderr[:500]}

    _log("  -> perf stat: done")
    result = _parse_perf_stat(r.stderr)
    result["perf_events_used"] = events
    if len(stderr_blocks) > 1:
        result["perf_event_fallback"] = True
    return result


def stage_perf_record(
    args: argparse.Namespace, prereqs: dict, targets: list[str], out_dir: Path
) -> dict[str, Any]:
    if prereqs.get("perf_paranoid", 99) > 1:
        return {"available": False, "reason": f"perf_event_paranoid={prereqs['perf_paranoid']}"}
    if not shutil.which("perf"):
        return {"available": False, "reason": "perf not found"}

    tier3_dir = out_dir / "tier3"
    tier3_dir.mkdir(parents=True, exist_ok=True)
    env = _build_env(os.environ.copy(), args.env)

    target_cmd = _build_target_cmd(args, targets)
    data_path = tier3_dir / "perf.data"
    report_path = tier3_dir / "perf_report.txt"

    record_cmd = [
        "perf",
        "record",
        "-o",
        str(data_path),
        "--call-graph",
        "dwarf",
        "--",
        *target_cmd,
    ]
    _log("  -> perf record: running...")
    record_r = subprocess.run(
        record_cmd,
        capture_output=True,
        text=True,
        cwd=str(args.root),
        env=env,
        timeout=args.valgrind_timeout,
    )
    if record_r.returncode != 0 or not data_path.exists():
        return {
            "error": f"perf record failed (exit {record_r.returncode})",
            "stderr": record_r.stderr[:500],
        }

    report_cmd = [
        "perf",
        "report",
        "--stdio",
        "--no-children",
        "--sort",
        "overhead,comm,dso,symbol",
        "--percent-limit",
        "0",
        "-i",
        str(data_path),
    ]
    report_r = subprocess.run(
        report_cmd,
        capture_output=True,
        text=True,
        cwd=str(args.root),
        env=env,
        timeout=args.valgrind_timeout,
    )
    report_path.write_text(report_r.stdout)

    result: dict[str, Any] = {
        "available": True,
        "data_path": str(data_path),
        "report_path": str(report_path),
        "hotspots": [],
    }
    if report_r.returncode != 0:
        result["report_error"] = f"perf report failed (exit {report_r.returncode})"
        if report_r.stderr:
            result["report_stderr"] = report_r.stderr[:500]
        return result

    parsed = _parse_perf_report(report_r.stdout)
    result["hotspots"] = parsed.get("hotspots", [])[:10]
    if not result["hotspots"]:
        result["parse_error"] = "no hotspots parsed from perf report"

    _log("  -> perf record: done")
    return result


# ---------------------------------------------------------------------------
# Tier 4: ASM Audit
# ---------------------------------------------------------------------------


def stage_objdump(
    args: argparse.Namespace, prereqs: dict, targets: list[str], out_dir: Path
) -> dict[str, Any]:
    tier4_dir = out_dir / "tier4"
    tier4_dir.mkdir(parents=True, exist_ok=True)
    generated: list[str] = []

    if args.binary:
        outpath = tier4_dir / f"objdump_{Path(args.binary).name}.txt"
        r = subprocess.run(
            ["objdump", "-dS", args.binary],
            capture_output=True,
            text=True,
            timeout=args.valgrind_timeout,
        )
        outpath.write_text(r.stdout)
        generated.append(str(outpath))
    else:
        root = args.root
        for so_file in _discover_objdump_targets(root, args.source_prefix):
            outpath = tier4_dir / f"objdump_{so_file.name}.txt"
            r = subprocess.run(
                ["objdump", "-dS", str(so_file)],
                capture_output=True,
                text=True,
                timeout=args.valgrind_timeout,
            )
            outpath.write_text(r.stdout)
            generated.append(str(outpath))

    return {"generated": generated}


def stage_numba_asm(
    args: argparse.Namespace, prereqs: dict, targets: list[str], out_dir: Path
) -> dict[str, Any]:
    """Try to extract Numba JIT ASM if Numba is available."""
    tier4_dir = out_dir / "tier4"
    tier4_dir.mkdir(parents=True, exist_ok=True)

    check_cmd = [args.python, "-c", "import numba; print('ok')"]
    r = subprocess.run(check_cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return {"available": False, "reason": "numba not importable"}

    return {
        "available": True,
        "note": "Numba detected. Use fn.inspect_asm() interactively for JIT ASM.",
    }


# ---------------------------------------------------------------------------
# Parallel Execution Engine
# ---------------------------------------------------------------------------


def run_parallel_tiers(
    args: argparse.Namespace, prereqs: dict, targets: list[str], out_dir: Path
) -> dict[str, Any]:
    """Run Tiers 2-4 with two concurrency classes."""
    valgrind_sem = threading.Semaphore(args.max_valgrind_parallel)
    results: dict[str, Any] = {}

    def valgrind_wrapped(fn, *a, **kw):
        with valgrind_sem:
            return fn(*a, **kw)

    tier = args.tier
    futures: dict[str, Future] = {}
    max_workers = args.max_valgrind_parallel + 4

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        # Class A: Valgrind (semaphore-bounded)
        if tier in ("medium", "deep", "asm") and prereqs.get("valgrind"):
            futures["cachegrind"] = pool.submit(
                valgrind_wrapped, stage_cachegrind, args, prereqs, targets, out_dir
            )
            futures["callgrind"] = pool.submit(
                valgrind_wrapped, stage_callgrind, args, prereqs, targets, out_dir
            )
        if tier in ("deep", "asm") and prereqs.get("valgrind"):
            futures["massif"] = pool.submit(
                valgrind_wrapped, stage_massif, args, prereqs, targets, out_dir
            )

        # Class B: Lightweight (no semaphore)
        if tier in ("deep", "asm"):
            futures["perf_stat"] = pool.submit(stage_perf_stat, args, prereqs, targets, out_dir)
            if args.perf_record:
                futures["perf_record"] = pool.submit(
                    stage_perf_record, args, prereqs, targets, out_dir
                )
        if tier == "asm" or args.asm_audit:
            futures["objdump"] = pool.submit(stage_objdump, args, prereqs, targets, out_dir)
            futures["numba_asm"] = pool.submit(stage_numba_asm, args, prereqs, targets, out_dir)

        for name, fut in futures.items():
            try:
                results[name] = fut.result()
                _log(f"  done: {name}")
            except subprocess.TimeoutExpired:
                _log(f"  TIMEOUT: {name} (exceeded {args.valgrind_timeout}s)")
                results[name] = {"error": f"timeout after {args.valgrind_timeout}s"}
            except Exception as e:
                _log(f"  FAIL: {name}: {e}")
                results[name] = {"error": str(e)}

    return results


# ---------------------------------------------------------------------------
# Rubric Scoring + Reporting
# ---------------------------------------------------------------------------


def write_json_summary(
    rubric: dict,
    tier1: dict,
    tier234: dict,
    prereqs: dict,
    args: argparse.Namespace,
    out_dir: Path,
) -> None:
    """Compatibility wrapper around the extracted reporting module."""
    _write_json_summary(rubric, tier1, tier234, prereqs, args, out_dir, _cv)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Linux performance benchmark pipeline — 7-dimension rubric scoring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--root", required=True, type=Path, help="Repository root")
    p.add_argument("--out-dir", required=True, type=Path, help="Output directory")
    p.add_argument(
        "--target", default=None, help="Explicit benchmark command (use {SIZE} placeholder)"
    )
    p.add_argument("--binary", default=None, help="Standalone C binary to profile")
    p.add_argument("--python", default=sys.executable, help="Python interpreter")
    p.add_argument(
        "--source-prefix", default=None, help="Source filter for annotations (e.g. path/to/source/)"
    )
    p.add_argument(
        "--tier",
        default="medium",
        choices=["fast", "medium", "deep", "asm"],
        help="Profiling depth",
    )
    p.add_argument(
        "--sizes", default=None, help="Comma-separated input sizes (e.g. 1000,10000,100000)"
    )
    p.add_argument("--valgrind-size", type=int, default=10000, help="Input size for Valgrind runs")
    p.add_argument(
        "--max-valgrind-parallel", type=int, default=2, help="Max concurrent Valgrind instances"
    )
    p.add_argument(
        "--expected-complexity", default="nlogn", choices=["linear", "nlogn", "quadratic"]
    )
    p.add_argument(
        "--baseline", default=None, help="Previous benchmark_summary.json for regression"
    )
    p.add_argument("--perf-repeats", type=int, default=5, help="perf stat iterations")
    p.add_argument("--perf-events", default=None, help="Custom perf event list")
    p.add_argument(
        "--perf-record",
        action="store_true",
        help="Enable opt-in native hotspot sampling via perf record/report",
    )
    p.add_argument("--time-repeats", type=int, default=5, help="/usr/bin/time iterations")
    p.add_argument("--asm-audit", action="store_true", help="Enable Tier 4 ASM audit")
    p.add_argument(
        "--valgrind-timeout",
        type=int,
        default=1800,
        help="Timeout per Valgrind run in seconds (default 1800)",
    )
    p.add_argument("--env", action="append", default=[], help="Environment variable KEY=VALUE")

    args = p.parse_args(argv)
    if args.sizes:
        args.sizes = [int(s.strip()) for s in args.sizes.split(",")]
    else:
        args.sizes = []
    if args.target and args.sizes and "{SIZE}" not in args.target:
        p.error("Explicit --target with --sizes requires a {SIZE} placeholder.")
    args.root = args.root.resolve()
    args.out_dir = args.out_dir.resolve()
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    _log("=" * 60)
    _log("Performance Benchmark Pipeline")
    _log("=" * 60)

    # Stage 1: Prerequisites
    _log("\nStage 1: Checking prerequisites...")
    prereqs = check_prerequisites(args)
    if not prereqs["python_ok"]:
        _log("ERROR: Python >= 3.10 required")
        return 1

    targets = discover_targets(args.root) if not args.target and not args.binary else []
    if args.target:
        _log(f"  Target: {args.target}")
    elif args.binary:
        _log(f"  Binary: {args.binary}")
    elif targets:
        _log(f"  Discovered {len(targets)} benchmark target(s): {targets}")
    else:
        _log("ERROR: No benchmark target found.")
        _log("Pass --target or --binary, or add pytest benchmark tests for autodiscovery.")
        return 1

    # Stage 2: Tier 1
    _log("\nStage 2: Tier 1 — wall time + memory...")
    tier1_results = stage_tier1(args, prereqs, targets, out_dir)

    # Stage 3: Tiers 2-4 (parallel)
    tier234_results: dict[str, Any] = {}
    if args.tier != "fast":
        _log(f"\nStage 3: Tiers 2-4 — profiling ({args.tier})...")
        tier234_results = run_parallel_tiers(args, prereqs, targets, out_dir)

    # Stage 4: Scoring + report
    _log("\nStage 4: Scoring rubric + generating report...")
    rubric = score_rubric(tier1_results, tier234_results, args)
    write_markdown_report(rubric, tier1_results, tier234_results, prereqs, args, out_dir)
    write_json_summary(rubric, tier1_results, tier234_results, prereqs, args, out_dir)

    if _stage_has_error(tier1_results) or _stage_has_error(tier234_results):
        _log("One or more stages reported errors.")
        return 1

    _log(f"\nScore: {rubric['total']}/{rubric['max_possible']}")
    total_dims = len([d for _, d in rubric["dimensions"] if d.get("tier") != "N/A"])
    _log(f"Dimensions scored: {total_dims}/7")
    _log(f"Report: {out_dir / 'benchmark_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
