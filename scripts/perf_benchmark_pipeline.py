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
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from perf_benchmark.reporting import write_json_summary as _write_json_summary
from perf_benchmark.reporting import write_markdown_report
from perf_benchmark.scoring import _cv, _fit_exponent, score_algorithmic_scaling
from perf_benchmark.scoring import score_cache_dim, score_cpu_efficiency, score_memory_profile
from perf_benchmark.scoring import score_rubric, score_wall_time_stability

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
        _log("  Fix: sudo sysctl kernel.perf_event_paranoid=1")

    if not prereqs["valgrind"] and args.tier != "fast":
        _log("  WARNING: valgrind not found. Valgrind-backed stages will be skipped.")

    ram = prereqs["ram_mb"]
    if ram > 0 and ram < args.max_valgrind_parallel * 4000:
        _log(f"  WARNING: {ram}MB RAM with --max-valgrind-parallel={args.max_valgrind_parallel} may cause memory pressure.")

    return prereqs


# ---------------------------------------------------------------------------
# Target Discovery
# ---------------------------------------------------------------------------

def discover_targets(root: Path) -> list[str]:
    """Scan for pytest benchmark tests. Returns paths relative to root."""
    targets: list[str] = []
    bench_dir = root / "tests" / "benchmarks"
    if bench_dir.is_dir():
        targets.append(str(bench_dir.relative_to(root)))
        return targets

    # Scan for pytest.mark.benchmark in .py files
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


def _missing_target_error() -> ValueError:
    return ValueError(
        "No benchmark target found. Pass --target or --binary, or add pytest benchmark tests."
    )


def _build_target_cmd(
    args: argparse.Namespace, targets: list[str], size_override: int | None = None
) -> list[str]:
    """Build the command to run for benchmarking."""
    size_value = size_override
    if size_value is None and args.sizes:
        size_value = args.sizes[-1]
    if args.binary:
        cmd = [args.binary]
        if size_value is not None:
            cmd.append(str(size_value))
        return cmd
    if args.target:
        expanded = args.target
        if size_value is not None and "{SIZE}" in expanded:
            expanded = expanded.replace("{SIZE}", str(size_value))
        return shlex.split(expanded)
    if targets:
        return [args.python, "-m", "pytest", "-x", "-q", "--benchmark-disable"] + targets
    raise _missing_target_error()


def _build_valgrind_target_cmd(args: argparse.Namespace, targets: list[str]) -> list[str]:
    """Build target command sized for Valgrind (smaller input)."""
    if args.binary:
        cmd = [args.binary]
        if args.sizes:
            cmd.append(str(args.valgrind_size))
        return cmd
    if args.target:
        expanded = args.target
        if "{SIZE}" in expanded:
            expanded = expanded.replace("{SIZE}", str(args.valgrind_size))
        return shlex.split(expanded)
    if targets:
        return [
            args.python, "-m", "pytest", "-x", "-q",
            "--benchmark-enable", "--benchmark-only",
        ] + targets
    raise _missing_target_error()


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


def _generate_tracemalloc_wrapper(
    args: argparse.Namespace, targets: list[str]
) -> tuple[Path, list[str]]:
    """Generate a temporary script that injects tracemalloc into a child Python process.

    Returns (wrapper_path, target_cmd_list).  The target command is passed via
    a JSON-encoded argv list in sys.argv[3] to avoid code injection through
    ``--target`` values.
    """
    if args.target:
        target_str = args.target.replace("{SIZE}", str(args.sizes[-1] if args.sizes else 10000))
        cmd_list = shlex.split(target_str)
    elif targets:
        cmd_list = [args.python, "-m", "pytest", "-x", "-q", "--benchmark-disable"] + targets
    else:
        raise _missing_target_error()

    wrapper_code = '''\
import json, os, runpy, sys, tracemalloc
os.chdir(json.loads(sys.argv[2]))
cmd = json.loads(sys.argv[3])
trace_out = sys.argv[1]
exe = os.path.basename(cmd[0]).lower()
if "python" not in exe:
    with open(trace_out, "w") as f:
        json.dump({"error": "tracemalloc requires a Python target command"}, f, indent=2)
    raise SystemExit(0)

python_argv = cmd[1:]
status = 0
tracemalloc.start(25)
old_argv = sys.argv[:]

try:
    if not python_argv:
        status = 0
    elif python_argv[0] == "-m" and len(python_argv) >= 2:
        sys.argv = [python_argv[1]] + python_argv[2:]
        runpy.run_module(python_argv[1], run_name="__main__", alter_sys=True)
    elif python_argv[0] == "-c" and len(python_argv) >= 2:
        sys.argv = ["-c"] + python_argv[2:]
        exec(python_argv[1], {"__name__": "__main__", "__file__": "<string>"})
    else:
        sys.argv = python_argv
        runpy.run_path(python_argv[0], run_name="__main__")
except SystemExit as exc:
    code = exc.code
    status = code if isinstance(code, int) else 0
finally:
    current, peak = tracemalloc.get_traced_memory()
    snapshot = tracemalloc.take_snapshot()
    top = snapshot.statistics("lineno")[:20]
    with open(trace_out, "w") as f:
        json.dump(
            {
                "current_bytes": current,
                "peak_bytes": peak,
                "top_allocators": [
                    {
                        "traceback": str(s.traceback),
                        "size_bytes": s.size,
                        "count": s.count,
                    }
                    for s in top
                ],
            },
            f,
            indent=2,
        )
    tracemalloc.stop()
    sys.argv = old_argv

raise SystemExit(status)
'''
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix="_tracemalloc.py", delete=False)
    tmp.write(wrapper_code)
    tmp.close()
    return Path(tmp.name), cmd_list


def _tracemalloc_target_error(cmd_list: list[str]) -> str | None:
    exe = os.path.basename(cmd_list[0]).lower()
    if "python" not in exe:
        return "tracemalloc requires a Python target command"

    argv = cmd_list[1:]
    unsupported: list[str] = []
    i = 0
    while i < len(argv) and argv[i].startswith("-") and argv[i] not in {"-m", "-c"}:
        flag = argv[i]
        unsupported.append(flag)
        i += 1
        if flag in {"-X", "-W"} and i < len(argv):
            i += 1
    if unsupported:
        return "tracemalloc does not support Python interpreter flags: " + " ".join(unsupported)
    return None


def _stage_has_error(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("error"):
            return True
        return any(_stage_has_error(item) for item in value.values())
    if isinstance(value, list):
        return any(_stage_has_error(item) for item in value)
    return False


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
        wrapper_path, wrapper_cmd = _generate_tracemalloc_wrapper(args, targets)
        try:
            target_error = _tracemalloc_target_error(wrapper_cmd)
            if target_error:
                results["tracemalloc"] = {"error": target_error}
            else:
                _log("  -> tracemalloc wrapper...")
                r = subprocess.run(
                    [
                        args.python, str(wrapper_path), str(tracemalloc_out),
                        json.dumps(str(args.root)),
                        json.dumps(wrapper_cmd),
                    ],
                    capture_output=True, text=True, cwd=str(args.root), env=env, timeout=300,
                )
                if r.returncode != 0:
                    results["tracemalloc"] = {"error": f"exit {r.returncode}", "stderr": r.stderr[:500]}
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
                capture_output=True, text=True, cwd=str(args.root), env=env,
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
            nums: list[int] = []
            for part in parts:
                try:
                    nums.append(int(float(part)))
                except ValueError:
                    continue
            if nums and headers:
                for h, v in zip(headers[:len(nums)], nums):
                    result["summary"][h] = v
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


def _parse_callgrind_raw(text: str, input_size: int) -> dict[str, int]:
    """Parse raw callgrind output for call counts and multiplicative paths."""
    total_calls = 0
    multiplicative_path_count = 0
    threshold = max(input_size, 0)

    for line in text.splitlines():
        match = re.match(r"^calls=(\d+)\b", line.strip())
        if not match:
            continue
        call_count = int(match.group(1))
        total_calls += call_count
        if threshold > 0 and call_count > threshold:
            multiplicative_path_count += 1

    return {
        "total_calls": total_calls,
        "multiplicative_path_count": multiplicative_path_count,
    }


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
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(args.root), env=env,
                        timeout=args.valgrind_timeout)
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
        "valgrind", "--tool=callgrind",
        f"--callgrind-out-file={outfile}",
        "--", *target_cmd,
    ]
    _log("  -> callgrind: running...")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(args.root), env=env,
                        timeout=args.valgrind_timeout)
    if not outfile.exists():
        return {"error": f"callgrind failed (exit {r.returncode})", "stderr": r.stderr[:500]}

    ann_cmd = [
        "callgrind_annotate", "--tree=both", "--inclusive=yes",
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
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(args.root), env=env,
                        timeout=args.valgrind_timeout)

    # Generate ms_print as human artifact
    if outfile.exists():
        ms_r = subprocess.run(
            ["ms_print", str(outfile)],
            capture_output=True,
            text=True,
            timeout=args.valgrind_timeout,
        )
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
    env = _build_env(os.environ.copy(), args.env)

    events = args.perf_events or (
        "cycles,instructions,branches,branch-misses,"
        "L1-dcache-loads,L1-dcache-load-misses,L1-icache-load-misses,"
        "LLC-loads,LLC-load-misses,dTLB-loads,dTLB-load-misses"
    )
    target_cmd = _build_target_cmd(args, targets)
    cmd = ["perf", "stat", "-r", str(args.perf_repeats), "-e", events, "--"] + target_cmd

    _log("  -> perf stat: running...")
    r = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(args.root),
        env=env,
        timeout=args.valgrind_timeout,
    )
    (tier3_dir / "perf_stat.txt").write_text(r.stderr)
    if r.returncode != 0:
        return {"error": f"perf stat failed (exit {r.returncode})", "stderr": r.stderr[:500]}

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


def _discover_objdump_targets(root: Path, source_prefix: str | None) -> list[Path]:
    candidates = sorted(Path(root).rglob("*.so"))
    if not source_prefix:
        return candidates

    direct_matches = [so_file for so_file in candidates if source_prefix in str(so_file)]
    if direct_matches:
        return direct_matches

    source_tokens = {
        token
        for token in Path(source_prefix).parts
        if token and token not in {".", "src", "source", "python", "lib"}
    }
    token_matches = [so_file for so_file in candidates if source_tokens.intersection(so_file.parts)]
    if token_matches:
        return token_matches

    return candidates


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
    p.add_argument("--valgrind-timeout", type=int, default=1800, help="Timeout per Valgrind run in seconds (default 1800)")
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
