#!/usr/bin/env python3
"""Linux performance benchmark pipeline.

Orchestrates profiling tools (Valgrind, perf, pytest-benchmark) across 4 tiers
and scores results against a 7-dimension rubric (0-28).

Usage:
    python perf_benchmark_pipeline.py --root /path/to/repo --out-dir /tmp/bench \\
        --source-prefix src/pkg/ --tier medium --sizes 10000,100000

Exit codes:
    0  All stages succeeded
    1  One or more stages failed (partial results still written)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

def check_python_version() -> bool:
    return sys.version_info >= (3, 10)


def check_valgrind() -> str | None:
    return shutil.which("valgrind")


def check_perf_paranoid() -> int:
    try:
        return int(Path("/proc/sys/kernel/perf_event_paranoid").read_text().strip())
    except (OSError, ValueError):
        return 99


def check_cpu_governor() -> str:
    try:
        gov = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor").read_text().strip()
        return gov
    except OSError:
        return "unknown"


def detect_cache_topology() -> dict[str, str]:
    """Read sysfs cache info, return Valgrind --I1/--D1/--LL flags."""
    base = Path("/sys/devices/system/cpu/cpu0/cache")
    result: dict[str, str] = {}
    mapping = {"Data": "D1", "Instruction": "I1", "Unified": None}

    indexes: dict[str, dict[str, str]] = {}
    try:
        for idx_dir in sorted(base.iterdir()):
            if not idx_dir.name.startswith("index"):
                continue
            ctype = (idx_dir / "type").read_text().strip()
            size_str = (idx_dir / "size").read_text().strip()
            assoc = (idx_dir / "ways_of_associativity").read_text().strip()
            line = (idx_dir / "coherency_line_size").read_text().strip()
            level = (idx_dir / "level").read_text().strip() if (idx_dir / "level").exists() else "0"
            # Convert size: "48K" -> 49152
            size_bytes = _parse_cache_size(size_str)
            indexes[idx_dir.name] = {
                "type": ctype, "size": str(size_bytes),
                "assoc": assoc, "line": line, "level": level,
            }
    except OSError:
        return _detect_cache_fallback()

    # Map indexes to Valgrind flags
    for _name, info in indexes.items():
        flag_val = f"{info['size']},{info['assoc']},{info['line']}"
        if info["type"] == "Data" and info["level"] == "1":
            result["D1"] = flag_val
        elif info["type"] == "Instruction" and info["level"] == "1":
            result["I1"] = flag_val
        elif info["type"] == "Unified" and int(info["level"]) >= 3:
            result["LL"] = flag_val

    if not result.get("LL"):
        # Use highest-level unified cache as LL
        for _name, info in indexes.items():
            if info["type"] == "Unified":
                result["LL"] = f"{info['size']},{info['assoc']},{info['line']}"

    return result or _detect_cache_fallback()


def _parse_cache_size(s: str) -> int:
    s = s.strip().upper()
    if s.endswith("K"):
        return int(s[:-1]) * 1024
    if s.endswith("M"):
        return int(s[:-1]) * 1024 * 1024
    return int(s)


def _detect_cache_fallback() -> dict[str, str]:
    """Fallback using getconf (may return E-core values on hybrid CPUs)."""
    _log("  WARNING: sysfs cache detection failed, using getconf (may be inaccurate on hybrid CPUs)")
    result = {}
    try:
        d1_size = os.sysconf("SC_LEVEL1_DCACHE_SIZE")
        d1_assoc = os.sysconf("SC_LEVEL1_DCACHE_ASSOC")
        d1_line = os.sysconf("SC_LEVEL1_DCACHE_LINESIZE")
        result["D1"] = f"{d1_size},{d1_assoc},{d1_line}"
    except (ValueError, OSError):
        pass
    try:
        i1_size = os.sysconf("SC_LEVEL1_ICACHE_SIZE")
        i1_assoc = os.sysconf("SC_LEVEL1_ICACHE_ASSOC")
        i1_line = os.sysconf("SC_LEVEL1_ICACHE_LINESIZE")
        result["I1"] = f"{i1_size},{i1_assoc},{i1_line}"
    except (ValueError, OSError):
        pass
    try:
        l3_size = os.sysconf("SC_LEVEL3_CACHE_SIZE")
        l3_assoc = os.sysconf("SC_LEVEL3_CACHE_ASSOC")
        l3_line = os.sysconf("SC_LEVEL3_CACHE_LINESIZE")
        result["LL"] = f"{l3_size},{l3_assoc},{l3_line}"
    except (ValueError, OSError):
        pass
    return result


def check_ram_mb() -> int:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return (pages * page_size) // (1024 * 1024)
    except (ValueError, OSError):
        return 0


def check_prerequisites(args: argparse.Namespace) -> dict[str, Any]:
    prereqs: dict[str, Any] = {}
    prereqs["python_ok"] = check_python_version()
    prereqs["valgrind"] = check_valgrind()
    prereqs["perf_paranoid"] = check_perf_paranoid()
    prereqs["governor"] = check_cpu_governor()
    prereqs["cache_topology"] = detect_cache_topology()
    prereqs["ram_mb"] = check_ram_mb()

    if prereqs["governor"] not in ("performance", "unknown"):
        _log(f"  WARNING: CPU governor is '{prereqs['governor']}', not 'performance'. Results may have 10-30% variance.")
        _log("  Fix: sudo cpupower frequency-set -g performance")

    if prereqs["perf_paranoid"] > 1:
        _log(f"  INFO: perf_event_paranoid={prereqs['perf_paranoid']}. perf stat will be skipped.")
        _log(f"  Fix: sudo sysctl kernel.perf_event_paranoid=1")

    if not prereqs["valgrind"] and args.tier != "fast":
        _log("  WARNING: valgrind not found. Tiers 2-4 will be skipped.")

    ram = prereqs["ram_mb"]
    if ram > 0 and ram < args.max_valgrind_parallel * 4000:
        _log(f"  WARNING: {ram}MB RAM with --max-valgrind-parallel={args.max_valgrind_parallel} may cause memory pressure.")

    return prereqs


# ---------------------------------------------------------------------------
# Target Discovery
# ---------------------------------------------------------------------------

def discover_targets(root: Path) -> list[str]:
    """Scan for pytest benchmark tests."""
    targets: list[str] = []
    bench_dir = root / "tests" / "benchmarks"
    if bench_dir.is_dir():
        targets.append(str(bench_dir))
        return targets

    # Scan for pytest.mark.benchmark in .py files (shallow)
    for py_file in root.rglob("test_*.py"):
        try:
            text = py_file.read_text(errors="replace")
            if "pytest.mark.benchmark" in text or "benchmark(" in text:
                targets.append(str(py_file.relative_to(root)))
        except OSError:
            continue
        if len(targets) >= 20:
            break

    return targets


# ---------------------------------------------------------------------------
# Command Builders
# ---------------------------------------------------------------------------

def _build_env(base: dict[str, str], env_pairs: list[str]) -> dict[str, str]:
    env = {**base}
    for pair in env_pairs:
        if "=" in pair:
            k, _, v = pair.partition("=")
            env[k] = v
    return env


def _build_target_cmd(args: argparse.Namespace, targets: list[str]) -> list[str]:
    """Build the command to run for benchmarking."""
    if args.binary:
        cmd = [args.binary]
        if args.sizes:
            cmd.append(str(args.sizes[-1]))
        return cmd
    if args.target:
        parts = args.target
        if args.sizes and "{SIZE}" in parts:
            parts = parts.replace("{SIZE}", str(args.sizes[-1]))
        return parts.split()
    if targets:
        return [args.python, "-m", "pytest", "-x", "-q", "--benchmark-disable"] + targets
    return [args.python, "-c", "pass"]


def _build_valgrind_target_cmd(args: argparse.Namespace, targets: list[str]) -> list[str]:
    """Build target command sized for Valgrind (smaller input)."""
    if args.binary:
        cmd = [args.binary]
        cmd.append(str(args.valgrind_size))
        return cmd
    if args.target:
        parts = args.target
        if "{SIZE}" in parts:
            parts = parts.replace("{SIZE}", str(args.valgrind_size))
        return parts.split()
    if targets:
        return [
            args.python, "-m", "pytest", "-x", "-q",
            "--benchmark-enable", "--benchmark-only",
            f"-k", f"n{args.valgrind_size}",
        ] + targets
    return [args.python, "-c", "pass"]


# ---------------------------------------------------------------------------
# Tier 1: Wall Time + Python Memory
# ---------------------------------------------------------------------------

def _parse_gnu_time(stderr: str) -> dict[str, Any]:
    """Parse /usr/bin/time -v output."""
    result: dict[str, Any] = {}
    patterns = {
        "wall_seconds": r"Elapsed \(wall clock\) time.*?: (\S+)",
        "max_rss_kb": r"Maximum resident set size.*?: (\d+)",
        "page_faults_major": r"Major .* page faults.*?: (\d+)",
        "page_faults_minor": r"Minor .* page faults.*?: (\d+)",
        "voluntary_ctx_switches": r"Voluntary context switches.*?: (\d+)",
        "involuntary_ctx_switches": r"Involuntary context switches.*?: (\d+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, stderr)
        if m:
            val = m.group(1)
            if key == "wall_seconds":
                # Format can be h:mm:ss or m:ss.ss
                parts = val.split(":")
                if len(parts) == 3:
                    result[key] = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                elif len(parts) == 2:
                    result[key] = float(parts[0]) * 60 + float(parts[1])
                else:
                    result[key] = float(val)
            else:
                result[key] = int(val)
    return result


def _generate_tracemalloc_wrapper(args: argparse.Namespace, targets: list[str]) -> Path:
    """Generate a temporary script that runs tracemalloc on the target."""
    # Build a minimal import+run statement
    if args.target:
        run_code = args.target.replace("{SIZE}", str(args.sizes[-1] if args.sizes else 10000))
    elif targets:
        run_code = f"import subprocess; subprocess.run(['{args.python}', '-m', 'pytest', '-x', '-q', '--benchmark-disable'] + {targets!r}, check=False)"
    else:
        run_code = "pass"

    wrapper_code = f'''
import tracemalloc, json, sys, os
os.chdir({str(args.root)!r})
tracemalloc.start(25)
{run_code}
current, peak = tracemalloc.get_traced_memory()
snapshot = tracemalloc.take_snapshot()
top = snapshot.statistics("lineno")[:20]
result = {{
    "current_bytes": current,
    "peak_bytes": peak,
    "top_allocators": [
        {{"traceback": str(s.traceback), "size_bytes": s.size, "count": s.count}}
        for s in top
    ]
}}
tracemalloc.stop()
with open(sys.argv[1], "w") as f:
    json.dump(result, f, indent=2)
'''
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix="_tracemalloc.py", delete=False)
    tmp.write(wrapper_code)
    tmp.close()
    return Path(tmp.name)


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
            args.python, "-m", "pytest", "-x", "-q",
            "--benchmark-enable", "--benchmark-only",
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
            results["pytest_benchmark"] = {"error": f"exit {r.returncode}", "stderr": r.stderr[:500]}

    # 2. tracemalloc (Python only)
    if not args.binary:
        tracemalloc_out = tier1_dir / "tracemalloc.json"
        wrapper = _generate_tracemalloc_wrapper(args, targets)
        try:
            _log("  -> tracemalloc wrapper...")
            subprocess.run(
                [args.python, str(wrapper), str(tracemalloc_out)],
                capture_output=True, text=True, cwd=str(args.root), env=env, timeout=300,
            )
            if tracemalloc_out.exists():
                results["tracemalloc"] = json.loads(tracemalloc_out.read_text())
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as e:
            results["tracemalloc"] = {"error": str(e)}
        finally:
            wrapper.unlink(missing_ok=True)

    # 3. /usr/bin/time -v (repeated for CV)
    target_cmd = _build_target_cmd(args, targets)
    time_results: list[dict] = []
    repeats = args.time_repeats
    _log(f"  -> /usr/bin/time -v x{repeats}...")
    for _ in range(repeats):
        r = subprocess.run(
            ["/usr/bin/time", "-v"] + target_cmd,
            capture_output=True, text=True, cwd=str(args.root), env=env,
        )
        parsed = _parse_gnu_time(r.stderr)
        if parsed:
            time_results.append(parsed)
    results["time_usage"] = time_results

    # Write raw time output
    if time_results:
        (tier1_dir / "time_usage.json").write_text(json.dumps(time_results, indent=2))

    return results


# ---------------------------------------------------------------------------
# Tier 2: Cachegrind + Callgrind
# ---------------------------------------------------------------------------

def _parse_cachegrind_summary(text: str) -> dict[str, Any]:
    """Parse cg_annotate output for per-file and summary metrics."""
    result: dict[str, Any] = {"files": [], "summary": {}}

    # Parse summary line: "Ir  I1mr  ILmr  Dr  D1mr  DLmr  Dw  D1mw  DLmw  Bc  Bcm"
    # The last summary line has "PROGRAM TOTALS"
    lines = text.splitlines()
    headers: list[str] = []
    for line in lines:
        if line.strip().startswith("Ir"):
            headers = line.split()
            break

    for line in lines:
        if "PROGRAM TOTALS" in line:
            parts = line.replace(",", "").split()
            nums = [p for p in parts if p.replace(".", "").isdigit()]
            if len(nums) >= 9 and headers:
                for h, v in zip(headers[:len(nums)], nums):
                    result["summary"][h] = int(v)
            break

    # Parse per-file lines (lines with file paths containing /)
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("-") or stripped.startswith("Ir"):
            continue
        parts = stripped.replace(",", "").split()
        # Look for lines with a file path component
        if len(parts) >= 10:
            filepath = parts[-1]
            if "/" in filepath or filepath.endswith((".py", ".c", ".h", ".pyx")):
                nums = parts[:-1]
                entry: dict[str, Any] = {"file": filepath}
                for h, v in zip(headers[:len(nums)], nums):
                    try:
                        entry[h] = int(v)
                    except ValueError:
                        pass
                if entry.get("Dr", 0) > 0:
                    entry["L1d_miss_pct"] = round(100.0 * entry.get("D1mr", 0) / entry["Dr"], 3)
                if entry.get("Dr", 0) + entry.get("Dw", 0) > 0:
                    total_refs = entry.get("Dr", 0) + entry.get("Dw", 0)
                    entry["LL_miss_pct"] = round(
                        100.0 * (entry.get("DLmr", 0) + entry.get("DLmw", 0)) / total_refs, 3
                    )
                if entry.get("Bc", 0) > 0:
                    entry["branch_mispred_pct"] = round(100.0 * entry.get("Bcm", 0) / entry["Bc"], 3)
                result["files"].append(entry)

    return result


def _parse_callgrind_output(text: str) -> dict[str, Any]:
    """Parse callgrind_annotate output for per-function costs."""
    result: dict[str, Any] = {"functions": [], "total_ir": 0}
    lines = text.splitlines()

    for line in lines:
        stripped = line.strip()
        if "PROGRAM TOTALS" in stripped:
            parts = stripped.replace(",", "").split()
            for p in parts:
                if p.isdigit():
                    result["total_ir"] = int(p)
                    break

    # Parse function-level lines: "  123,456  file:line  function_name"
    fn_pattern = re.compile(r"^\s*([\d,]+)\s+(.+?):(\d+)\s+(.+)$")
    # Also handle simpler format: "  123,456  function_name"
    fn_simple = re.compile(r"^\s*([\d,]+)\s+(\S+.*)")

    for line in lines:
        m = fn_pattern.match(line)
        if m:
            ir = int(m.group(1).replace(",", ""))
            filepath = m.group(2)
            lineno = int(m.group(3))
            funcname = m.group(4).strip()
            result["functions"].append({
                "Ir": ir, "file": filepath, "line": lineno,
                "function": funcname,
            })
            continue

    # Sort by instruction count descending
    result["functions"].sort(key=lambda f: f.get("Ir", 0), reverse=True)
    return result


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

    _log(f"  -> cachegrind: running...")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(args.root), env=env)
    if r.returncode != 0 and not outfile.exists():
        return {"error": f"cachegrind failed (exit {r.returncode})", "stderr": r.stderr[:500]}

    # Annotate with source filtering
    ann_cmd = ["cg_annotate"]
    if args.source_prefix:
        ann_cmd += [f"--include={args.source_prefix}"]
    ann_cmd.append(str(outfile))
    ann_r = subprocess.run(ann_cmd, capture_output=True, text=True)
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
        "valgrind", "--tool=callgrind",
        f"--callgrind-out-file={outfile}",
        "--", *target_cmd,
    ]
    _log("  -> callgrind: running...")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(args.root), env=env)
    if r.returncode != 0 and not outfile.exists():
        return {"error": f"callgrind failed (exit {r.returncode})", "stderr": r.stderr[:500]}

    ann_cmd = [
        "callgrind_annotate", "--tree=both", "--inclusive=yes",
    ]
    if args.source_prefix:
        ann_cmd += [f"--include={args.source_prefix}"]
    ann_cmd.append(str(outfile))
    ann_r = subprocess.run(ann_cmd, capture_output=True, text=True)
    (tier2_dir / "callgrind_annotated.txt").write_text(ann_r.stdout)

    _log("  -> callgrind: done")
    return _parse_callgrind_output(ann_r.stdout)


# ---------------------------------------------------------------------------
# Tier 3: Massif + perf stat
# ---------------------------------------------------------------------------

def _parse_massif_out(path: Path) -> dict[str, Any]:
    """Parse massif.out structured text directly."""
    result: dict[str, Any] = {"snapshots": [], "peak_bytes": 0, "peak_snapshot": -1, "alloc_sites": []}
    try:
        text = path.read_text()
    except OSError:
        return {"error": "cannot read massif.out"}

    current_snap: dict[str, Any] = {}
    heap_bytes_series: list[int] = []

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("snapshot="):
            if current_snap:
                result["snapshots"].append(current_snap)
                heap_bytes_series.append(current_snap.get("mem_heap_B", 0))
            current_snap = {"id": int(line.split("=")[1])}
        elif line.startswith("mem_heap_B="):
            current_snap["mem_heap_B"] = int(line.split("=")[1])
        elif line.startswith("mem_heap_extra_B="):
            current_snap["mem_heap_extra_B"] = int(line.split("=")[1])
        elif line.startswith("mem_stacks_B="):
            current_snap["mem_stacks_B"] = int(line.split("=")[1])
        elif line.startswith("time="):
            current_snap["time"] = int(line.split("=")[1])
        elif line.startswith("n") and ":" in line and "(" in line:
            # Allocation site: "n2: 524288 (func in file.c:42)"
            m = re.match(r"n\d+:\s+(\d+)\s+(.+)", line)
            if m:
                result["alloc_sites"].append({
                    "bytes": int(m.group(1)),
                    "location": m.group(2).strip(),
                })

    if current_snap:
        result["snapshots"].append(current_snap)
        heap_bytes_series.append(current_snap.get("mem_heap_B", 0))

    # Find peak
    if heap_bytes_series:
        peak_idx = max(range(len(heap_bytes_series)), key=lambda i: heap_bytes_series[i])
        result["peak_bytes"] = heap_bytes_series[peak_idx]
        result["peak_snapshot"] = peak_idx

        # Detect allocation churn: count local maxima
        maxima = 0
        for i in range(1, len(heap_bytes_series) - 1):
            if heap_bytes_series[i] > heap_bytes_series[i - 1] and heap_bytes_series[i] > heap_bytes_series[i + 1]:
                maxima += 1
        result["local_maxima_count"] = maxima
        result["heap_series_len"] = len(heap_bytes_series)

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
        "valgrind", "--tool=massif",
        f"--massif-out-file={outfile}",
        "--", *target_cmd,
    ]
    _log("  -> massif: running...")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(args.root), env=env)

    # Generate ms_print as human artifact
    if outfile.exists():
        ms_r = subprocess.run(["ms_print", str(outfile)], capture_output=True, text=True)
        (tier3_dir / "massif_ms_print.txt").write_text(ms_r.stdout)

    _log("  -> massif: done")
    if outfile.exists():
        return _parse_massif_out(outfile)
    return {"error": f"massif failed (exit {r.returncode})"}


def _parse_perf_stat(stderr: str) -> dict[str, Any]:
    """Parse perf stat output."""
    result: dict[str, Any] = {"counters": {}}
    for line in stderr.splitlines():
        line = line.strip()
        # Format: "  1,234,567      cycles  (99.9%)"
        m = re.match(r"([\d,\.]+)\s+(\S+)", line)
        if m:
            val_str = m.group(1).replace(",", "")
            name = m.group(2)
            try:
                val = float(val_str) if "." in val_str else int(val_str)
                result["counters"][name] = val
            except ValueError:
                pass

    # Compute derived metrics
    c = result["counters"]
    if c.get("instructions") and c.get("cycles"):
        result["IPC"] = round(c["instructions"] / c["cycles"], 3)
    if c.get("branches") and c.get("branch-misses"):
        result["branch_mispred_pct"] = round(100.0 * c["branch-misses"] / c["branches"], 3)
    if c.get("L1-dcache-loads") and c.get("L1-dcache-load-misses"):
        result["L1d_miss_pct"] = round(100.0 * c["L1-dcache-load-misses"] / c["L1-dcache-loads"], 3)
    if c.get("LLC-loads") and c.get("LLC-load-misses"):
        result["LLC_miss_pct"] = round(100.0 * c["LLC-load-misses"] / c["LLC-loads"], 3)

    return result


def stage_perf_stat(
    args: argparse.Namespace, prereqs: dict, targets: list[str], out_dir: Path
) -> dict[str, Any]:
    if prereqs.get("perf_paranoid", 99) > 1:
        return {"available": False, "reason": f"perf_event_paranoid={prereqs['perf_paranoid']}"}
    if not shutil.which("perf"):
        return {"available": False, "reason": "perf not found"}

    tier3_dir = out_dir / "tier3"
    tier3_dir.mkdir(parents=True, exist_ok=True)

    events = args.perf_events or (
        "cycles,instructions,branches,branch-misses,"
        "L1-dcache-loads,L1-dcache-load-misses,L1-icache-load-misses,"
        "LLC-loads,LLC-load-misses,dTLB-loads,dTLB-load-misses"
    )
    target_cmd = _build_target_cmd(args, targets)
    cmd = ["perf", "stat", "-r", str(args.perf_repeats), "-e", events, "--"] + target_cmd

    _log("  -> perf stat: running...")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(args.root))
    (tier3_dir / "perf_stat.txt").write_text(r.stderr)

    _log("  -> perf stat: done")
    return _parse_perf_stat(r.stderr)


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
        r = subprocess.run(["objdump", "-dS", args.binary], capture_output=True, text=True)
        outpath.write_text(r.stdout)
        generated.append(str(outpath))
    elif args.source_prefix:
        root = args.root
        for so_file in Path(root).rglob("*.so"):
            if args.source_prefix and args.source_prefix not in str(so_file):
                continue
            outpath = tier4_dir / f"objdump_{so_file.name}.txt"
            r = subprocess.run(["objdump", "-dS", str(so_file)], capture_output=True, text=True)
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

    return {"available": True, "note": "Numba detected. Use fn.inspect_asm() interactively for JIT ASM."}


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
    max_workers = args.max_valgrind_parallel + 3

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        # Class A: Valgrind (semaphore-bounded)
        if tier in ("medium", "deep", "asm") and prereqs.get("valgrind"):
            futures["cachegrind"] = pool.submit(valgrind_wrapped, stage_cachegrind, args, prereqs, targets, out_dir)
            futures["callgrind"] = pool.submit(valgrind_wrapped, stage_callgrind, args, prereqs, targets, out_dir)
        if tier in ("deep", "asm") and prereqs.get("valgrind"):
            futures["massif"] = pool.submit(valgrind_wrapped, stage_massif, args, prereqs, targets, out_dir)

        # Class B: Lightweight (no semaphore)
        if tier in ("deep", "asm"):
            futures["perf_stat"] = pool.submit(stage_perf_stat, args, prereqs, targets, out_dir)
        if tier == "asm" or args.asm_audit:
            futures["objdump"] = pool.submit(stage_objdump, args, prereqs, targets, out_dir)
            futures["numba_asm"] = pool.submit(stage_numba_asm, args, prereqs, targets, out_dir)

        for name, fut in futures.items():
            try:
                results[name] = fut.result()
                _log(f"  ✓ {name}")
            except Exception as e:
                _log(f"  ✗ {name}: {e}")
                results[name] = {"error": str(e)}

    return results


# ---------------------------------------------------------------------------
# Rubric Scoring
# ---------------------------------------------------------------------------

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
    log_n = [math.log(n) for n in sizes]
    log_t = [math.log(max(t, 1e-12)) for t in times]
    n = len(log_n)
    sum_x = sum(log_n)
    sum_y = sum(log_t)
    sum_xy = sum(x * y for x, y in zip(log_n, log_t))
    sum_x2 = sum(x * x for x in log_n)
    denom = n * sum_x2 - sum_x * sum_x
    if abs(denom) < 1e-12:
        return 1.0
    k = (n * sum_xy - sum_x * sum_y) / denom
    return round(k, 3)


def score_algorithmic_scaling(
    tier1: dict, tier234: dict, args: argparse.Namespace
) -> dict[str, Any]:
    sub_checks: dict[str, dict] = {}

    # H1: Complexity exponent
    sizes = args.sizes
    if sizes and len(sizes) >= 2:
        pb = tier1.get("pytest_benchmark", {})
        benchmarks = pb.get("benchmarks", [])
        if benchmarks:
            times_by_size: dict[int, list[float]] = {}
            for b in benchmarks:
                params = b.get("params", {}) or {}
                size = params.get("size") or b.get("extra_info", {}).get("input_size")
                if size is not None:
                    times_by_size.setdefault(int(size), []).append(b.get("stats", {}).get("mean", 0))
            matched_sizes, matched_times = [], []
            for s in sorted(sizes):
                if s in times_by_size:
                    matched_sizes.append(s)
                    matched_times.append(sum(times_by_size[s]) / len(times_by_size[s]))
            if len(matched_sizes) >= 2:
                k = _fit_exponent(matched_sizes, matched_times)
                thresholds = {"linear": (1.1, 1.3), "nlogn": (1.3, 1.8), "quadratic": (2.0, 2.5)}
                warn_k, fail_k = thresholds.get(args.expected_complexity, (1.3, 1.8))
                tier_val = "PASS" if k <= warn_k else "WARN" if k <= fail_k else "FAIL"
                sub_checks["complexity_exponent"] = {"k": k, "tier": tier_val}

    input_size = args.valgrind_size

    # H2: Call amplification
    cg = tier234.get("callgrind", {})
    if cg and not cg.get("error") and cg.get("functions"):
        max_ir = max((f.get("Ir", 0) for f in cg["functions"]), default=0)
        # Use total_ir / input_size as proxy for amplification
        if input_size > 0 and cg.get("total_ir", 0) > 0:
            amp = cg["total_ir"] / input_size
            tier_val = "PASS" if amp <= 1000 else "WARN" if amp <= 10000 else "FAIL"
            sub_checks["call_amplification"] = {"ratio": round(amp, 1), "tier": tier_val}

    # H3: Data reuse ratio
    ch = tier234.get("cachegrind", {})
    if ch and not ch.get("error"):
        total_dr = ch.get("summary", {}).get("Dr", 0)
        if input_size > 0 and total_dr > 0:
            reuse = total_dr / input_size
            tier_val = "PASS" if reuse <= 10 else "WARN" if reuse <= 100 else "FAIL"
            sub_checks["data_reuse"] = {"ratio": round(reuse, 1), "tier": tier_val}

    # H4: Write amplification
    if ch and not ch.get("error"):
        total_dr = ch.get("summary", {}).get("Dr", 0)
        total_dw = ch.get("summary", {}).get("Dw", 0)
        if total_dr > 0:
            w_ratio = total_dw / total_dr
            tier_val = "PASS" if w_ratio <= 0.2 else "WARN" if w_ratio <= 0.5 else "FAIL"
            sub_checks["write_amplification"] = {"ratio": round(w_ratio, 3), "tier": tier_val}

    # H5: Allocation churn
    massif = tier234.get("massif", {})
    if massif and not massif.get("error"):
        peaks = massif.get("local_maxima_count", 0)
        tier_val = "PASS" if peaks <= 2 else "WARN" if peaks <= 5 else "FAIL"
        sub_checks["allocation_churn"] = {"peaks": peaks, "tier": tier_val}

    # H6: Multiplicative paths (simplified: check if top fn Ir >> input_size * 1000)
    if cg and cg.get("functions") and input_size > 0:
        top_fn = cg["functions"][0] if cg["functions"] else {}
        if top_fn.get("Ir", 0) > input_size * 10000:
            sub_checks["multiplicative_paths"] = {"top_fn_ir": top_fn["Ir"], "tier": "WARN"}

    # Aggregate
    if not sub_checks:
        return {"score": -1, "tier": "N/A", "sub_checks": {}, "note": "Insufficient data for scaling analysis"}

    fails = sum(1 for c in sub_checks.values() if c["tier"] == "FAIL")
    warns = sum(1 for c in sub_checks.values() if c["tier"] == "WARN")

    if fails > 0:
        return {"score": 0, "tier": "FAIL", "sub_checks": sub_checks}
    if warns >= 2:
        return {"score": 2, "tier": "WARN", "sub_checks": sub_checks}
    return {"score": 4, "tier": "PASS", "sub_checks": sub_checks}


def score_wall_time_stability(tier1: dict) -> dict[str, Any]:
    """Dimension 1: wall-time CV."""
    # Try pytest-benchmark first
    pb = tier1.get("pytest_benchmark", {})
    benchmarks = pb.get("benchmarks", [])
    if benchmarks:
        cvs = [b.get("stats", {}).get("stddev", 0) / max(b.get("stats", {}).get("mean", 1e-12), 1e-12) * 100 for b in benchmarks]
        avg_cv = sum(cvs) / len(cvs) if cvs else 0
    else:
        # Fallback to /usr/bin/time
        times = [t.get("wall_seconds", 0) for t in tier1.get("time_usage", []) if t.get("wall_seconds")]
        avg_cv = _cv(times) if times else -1

    if avg_cv < 0:
        return {"score": -1, "tier": "N/A", "cv": None}

    tier_val = "PASS" if avg_cv <= 3 else "WARN" if avg_cv <= 8 else "FAIL"
    score = 4 if tier_val == "PASS" else 2 if tier_val == "WARN" else 0
    return {"score": score, "tier": tier_val, "cv": round(avg_cv, 2)}


def score_cpu_efficiency(tier234: dict) -> dict[str, Any]:
    """Dimension 2: CPU efficiency (hotspot concentration + IPC)."""
    cg = tier234.get("callgrind", {})
    perf = tier234.get("perf_stat", {})

    # Hotspot concentration
    concentration = None
    if cg and cg.get("functions") and cg.get("total_ir", 0) > 0:
        top_ir = cg["functions"][0].get("Ir", 0)
        concentration = round(100.0 * top_ir / cg["total_ir"], 1)

    # IPC
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


def score_cache_dim(tier234: dict, metric_key: str, pass_t: float, warn_t: float, fail_t: float) -> dict[str, Any]:
    """Generic cache dimension scorer."""
    ch = tier234.get("cachegrind", {})
    if not ch or ch.get("error"):
        return {"score": -1, "tier": "N/A"}

    values = [f.get(metric_key, 0) for f in ch.get("files", []) if f.get(metric_key) is not None]
    if not values:
        # Try summary
        summary = ch.get("summary", {})
        if metric_key == "L1d_miss_pct" and summary.get("Dr", 0) > 0:
            val = 100.0 * summary.get("D1mr", 0) / summary["Dr"]
            values = [val]
        elif metric_key == "LL_miss_pct" and (summary.get("Dr", 0) + summary.get("Dw", 0)) > 0:
            total = summary.get("Dr", 0) + summary.get("Dw", 0)
            val = 100.0 * (summary.get("DLmr", 0) + summary.get("DLmw", 0)) / total
            values = [val]
        elif metric_key == "branch_mispred_pct" and summary.get("Bc", 0) > 0:
            val = 100.0 * summary.get("Bcm", 0) / summary["Bc"]
            values = [val]

    if not values:
        return {"score": -1, "tier": "N/A"}

    worst = max(values)
    tier_val = "PASS" if worst <= pass_t else "WARN" if worst <= fail_t else "FAIL"
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

    tm = tier1.get("tracemalloc", {})
    if not peak_bytes and tm and tm.get("peak_bytes", 0) > 0:
        peak_bytes = tm["peak_bytes"]
        source = "tracemalloc"

    if not peak_bytes:
        return {"score": -1, "tier": "N/A"}

    # Check against baseline if available
    if baseline:
        base_peak = baseline.get("rubric", {}).get("dimensions", {}).get("Memory Profile", {}).get("peak_bytes", 0)
        if base_peak > 0:
            ratio = peak_bytes / base_peak
            tier_val = "PASS" if ratio <= 1.1 else "WARN" if ratio <= 1.5 else "FAIL"
            score = 4 if tier_val == "PASS" else 2 if tier_val == "WARN" else 0
            return {"score": score, "tier": tier_val, "peak_bytes": peak_bytes, "baseline_ratio": round(ratio, 2), "source": source}

    # Without baseline: check allocation churn and concentration
    churn_peaks = massif.get("local_maxima_count", 0) if massif else 0
    if churn_peaks > 5:
        return {"score": 0, "tier": "FAIL", "peak_bytes": peak_bytes, "churn_peaks": churn_peaks, "source": source}
    if churn_peaks > 2:
        return {"score": 2, "tier": "WARN", "peak_bytes": peak_bytes, "churn_peaks": churn_peaks, "source": source}
    return {"score": 4, "tier": "PASS", "peak_bytes": peak_bytes, "source": source}


def score_rubric(
    tier1: dict, tier234: dict, args: argparse.Namespace
) -> dict[str, Any]:
    baseline = None
    if args.baseline:
        try:
            baseline = json.loads(Path(args.baseline).read_text())
        except (OSError, json.JSONDecodeError):
            pass

    dimensions: list[tuple[str, dict]] = [
        ("Algorithmic Scaling", score_algorithmic_scaling(tier1, tier234, args)),
        ("Wall-Time Stability", score_wall_time_stability(tier1)),
        ("CPU Efficiency", score_cpu_efficiency(tier234)),
        ("L1 Cache Efficiency", score_cache_dim(tier234, "L1d_miss_pct", 1.0, 5.0, 5.0)),
        ("Last-Level Cache", score_cache_dim(tier234, "LL_miss_pct", 0.5, 2.0, 2.0)),
        ("Branch Prediction", score_cache_dim(tier234, "branch_mispred_pct", 1.0, 3.0, 3.0)),
        ("Memory Profile", score_memory_profile(tier1, tier234, baseline)),
    ]

    available = [(n, d) for n, d in dimensions if d.get("tier") != "N/A"]
    total = sum(d["score"] for _, d in available)
    max_possible = len(available) * 4

    return {"dimensions": dimensions, "total": total, "max_possible": max_possible}


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------

def write_markdown_report(
    rubric: dict, tier1: dict, tier234: dict, prereqs: dict,
    args: argparse.Namespace, out_dir: Path,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = []
    lines.append("# Performance Benchmark Report")
    lines.append("")
    lines.append(f"**Generated**: {now}")
    lines.append(f"**Root**: `{args.root}`")
    lines.append(f"**Tier**: {args.tier}")
    if args.sizes:
        lines.append(f"**Sizes**: {args.sizes}")
    lines.append("")

    # Prerequisites
    lines.append("## Prerequisites")
    lines.append("")
    lines.append(f"- Python: {sys.version.split()[0]} ({'OK' if prereqs['python_ok'] else 'FAIL'})")
    lines.append(f"- Valgrind: {'found' if prereqs['valgrind'] else 'not found'}")
    lines.append(f"- perf_event_paranoid: {prereqs['perf_paranoid']} ({'perf available' if prereqs['perf_paranoid'] <= 1 else 'perf UNAVAILABLE — run: sudo sysctl kernel.perf_event_paranoid=1'})")
    lines.append(f"- CPU governor: {prereqs['governor']} ({'OK' if prereqs['governor'] == 'performance' else 'WARNING — set to performance for stable results'})")
    lines.append(f"- RAM: {prereqs['ram_mb']}MB")
    cache = prereqs.get("cache_topology", {})
    if cache:
        lines.append(f"- Cache model: D1={cache.get('D1', '?')}, I1={cache.get('I1', '?')}, LL={cache.get('LL', '?')}")
    lines.append("")

    # Algorithmic Scaling (ALWAYS FIRST)
    dim0 = rubric["dimensions"][0][1]
    lines.append("## Algorithmic Scaling Analysis")
    lines.append("")
    if dim0.get("tier") == "N/A":
        lines.append("*Insufficient data. Run benchmarks at >= 2 input sizes (--sizes).*")
    else:
        lines.append(f"**Result: {dim0['tier']}** (score: {dim0['score']}/4)")
        lines.append("")
        if dim0.get("sub_checks"):
            lines.append("| Sub-check | Value | Tier |")
            lines.append("|-----------|-------|------|")
            for name, check in dim0["sub_checks"].items():
                val = check.get("k") or check.get("ratio") or check.get("peaks") or check.get("top_fn_ir", "")
                lines.append(f"| {name} | {val} | {check['tier']} |")
        if dim0["tier"] == "FAIL":
            lines.append("")
            lines.append("> **STOP**: Fix algorithmic scaling before hardware-level optimization.")
            lines.append("> Expected impact: 10-1000x improvement.")
            lines.append("> Hardware optimizations (cache, branch, ASM) are irrelevant until this is resolved.")
    lines.append("")

    # Rubric Scorecard
    lines.append("## Rubric Scorecard")
    lines.append("")
    lines.append(f"**Total: {rubric['total']}/{rubric['max_possible']}**")
    lines.append("")
    lines.append("| # | Dimension | Score | Tier |")
    lines.append("|---|-----------|-------|------|")
    for i, (name, d) in enumerate(rubric["dimensions"]):
        score_str = f"{d['score']}/4" if d.get("tier") != "N/A" else "N/A"
        lines.append(f"| {i} | {name} | {score_str} | {d.get('tier', 'N/A')} |")
    lines.append("")

    # Findings (FAIL first, then WARN)
    lines.append("## Findings")
    lines.append("")
    for severity in ("FAIL", "WARN"):
        for name, d in rubric["dimensions"]:
            if d.get("tier") == severity:
                lines.append(f"### [{severity}] {name}")
                lines.append("")
                for k, v in d.items():
                    if k not in ("score", "tier", "sub_checks"):
                        lines.append(f"- **{k}**: {v}")
                lines.append("")

    # Prescriptions
    lines.append("## Prescriptions")
    lines.append("")
    lines.append("*Priority order: Algorithmic > Data Layout > Execution > Micro*")
    lines.append("")
    for name, d in rubric["dimensions"]:
        if d.get("tier") in ("FAIL", "WARN"):
            lines.append(f"- **{name}**: ", )
            if "Algorithmic" in name:
                lines.append("  Review scaling sub-checks. Memoize, precompute, or restructure hot paths.")
            elif "L1" in name:
                lines.append("  Improve data locality: struct-of-arrays, cache-line alignment, sequential access.")
            elif "Last-Level" in name:
                lines.append("  Reduce working set size or improve spatial locality.")
            elif "Branch" in name:
                lines.append("  Replace unpredictable branches with cmov, lookup tables, or branchless arithmetic.")
            elif "CPU" in name:
                lines.append("  Reduce hotspot concentration. Consider splitting large functions.")
            elif "Memory" in name:
                lines.append("  Pre-allocate buffers, use object pools, reduce allocation churn.")
            elif "Wall" in name:
                lines.append("  Reduce measurement noise: set governor=performance, increase rounds, disable turbo boost.")
            lines.append("")

    # Cache model disclaimer
    lines.append("## Cache Model")
    lines.append("")
    lines.append("Valgrind cachegrind simulates a 2-level cache (L1 -> LL). No separate L2 simulation.")
    if cache:
        lines.append(f"Simulated: D1={cache.get('D1', '?')}, I1={cache.get('I1', '?')}, LL={cache.get('LL', '?')}")
    lines.append("On hybrid CPUs (Intel Alder/Raptor Lake), P-core cache hierarchy is simulated.")
    lines.append("")

    (out_dir / "benchmark_report.md").write_text("\n".join(lines))
    _log(f"  -> Wrote {out_dir / 'benchmark_report.md'}")


def write_json_summary(
    rubric: dict, tier1: dict, tier234: dict, prereqs: dict,
    args: argparse.Namespace, out_dir: Path,
) -> None:
    summary: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(args.root),
        "tier": args.tier,
        "rubric": {
            "total": rubric["total"],
            "max_possible": rubric["max_possible"],
            "dimensions": {name: d for name, d in rubric["dimensions"]},
        },
        "prerequisites": {
            "python_ok": prereqs["python_ok"],
            "valgrind": prereqs["valgrind"] is not None,
            "perf_paranoid": prereqs["perf_paranoid"],
            "governor": prereqs["governor"],
            "cache_topology": prereqs.get("cache_topology", {}),
            "ram_mb": prereqs["ram_mb"],
        },
    }

    # Include raw tier1 metrics
    time_data = tier1.get("time_usage", [])
    if time_data:
        walls = [t.get("wall_seconds", 0) for t in time_data if t.get("wall_seconds")]
        if walls:
            summary["wall_time_cv"] = round(_cv(walls), 2)
            summary["wall_time_mean"] = round(sum(walls) / len(walls), 4)

    tm = tier1.get("tracemalloc", {})
    if tm and tm.get("peak_bytes"):
        summary["tracemalloc_peak_bytes"] = tm["peak_bytes"]

    massif = tier234.get("massif", {})
    if massif and massif.get("peak_bytes"):
        summary["massif_peak_bytes"] = massif["peak_bytes"]

    (out_dir / "benchmark_summary.json").write_text(json.dumps(summary, indent=2))
    _log(f"  -> Wrote {out_dir / 'benchmark_summary.json'}")


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
    p.add_argument("--target", default=None, help="Explicit benchmark command (use {SIZE} placeholder)")
    p.add_argument("--binary", default=None, help="Standalone C binary to profile")
    p.add_argument("--python", default=sys.executable, help="Python interpreter")
    p.add_argument("--source-prefix", default=None, help="Source filter for annotations (e.g. src/pkg/)")
    p.add_argument("--tier", default="medium", choices=["fast", "medium", "deep", "asm"], help="Profiling depth")
    p.add_argument("--sizes", default=None, help="Comma-separated input sizes (e.g. 1000,10000,100000)")
    p.add_argument("--valgrind-size", type=int, default=10000, help="Input size for Valgrind runs")
    p.add_argument("--max-valgrind-parallel", type=int, default=2, help="Max concurrent Valgrind instances")
    p.add_argument("--expected-complexity", default="nlogn", choices=["linear", "nlogn", "quadratic"])
    p.add_argument("--baseline", default=None, help="Previous benchmark_summary.json for regression")
    p.add_argument("--perf-repeats", type=int, default=5, help="perf stat iterations")
    p.add_argument("--perf-events", default=None, help="Custom perf event list")
    p.add_argument("--time-repeats", type=int, default=5, help="/usr/bin/time iterations")
    p.add_argument("--asm-audit", action="store_true", help="Enable Tier 4 ASM audit")
    p.add_argument("--validate-scaling", action="store_true", help="Validate Valgrind scaling")
    p.add_argument("--env", action="append", default=[], help="Environment variable KEY=VALUE")

    args = p.parse_args(argv)
    if args.sizes:
        args.sizes = [int(s.strip()) for s in args.sizes.split(",")]
    else:
        args.sizes = []
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
        _log("WARNING: No benchmark targets found. Use --target or --binary.")
        _log("Continuing with minimal profiling (system-level metrics only).")

    # Stage 2: Tier 1
    _log(f"\nStage 2: Tier 1 — wall time + memory...")
    tier1_results = stage_tier1(args, prereqs, targets, out_dir)

    # Stage 3: Tiers 2-4 (parallel)
    tier234_results: dict[str, Any] = {}
    if args.tier != "fast":
        if prereqs.get("valgrind"):
            _log(f"\nStage 3: Tiers 2-4 — profiling ({args.tier})...")
            tier234_results = run_parallel_tiers(args, prereqs, targets, out_dir)
        else:
            _log("\nStage 3: Skipped (valgrind not available)")

    # Stage 4: Scoring + report
    _log("\nStage 4: Scoring rubric + generating report...")
    rubric = score_rubric(tier1_results, tier234_results, args)
    write_markdown_report(rubric, tier1_results, tier234_results, prereqs, args, out_dir)
    write_json_summary(rubric, tier1_results, tier234_results, prereqs, args, out_dir)

    _log(f"\nScore: {rubric['total']}/{rubric['max_possible']}")
    total_dims = len([d for _, d in rubric["dimensions"] if d.get("tier") != "N/A"])
    _log(f"Dimensions scored: {total_dims}/7")
    _log(f"Report: {out_dir / 'benchmark_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
