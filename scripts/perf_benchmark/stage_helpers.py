from __future__ import annotations

import argparse
import os
import re
import shlex
import tempfile
from pathlib import Path
from typing import Any

from perf_benchmark.support import _missing_target_error

__all__ = [
    "_discover_objdump_targets",
    "_generate_tracemalloc_wrapper",
    "_parse_cachegrind_summary",
    "_parse_callgrind_output",
    "_parse_callgrind_raw",
    "_parse_gnu_time",
    "_parse_massif_out",
    "_parse_perf_report",
    "_parse_perf_stat",
    "_tracemalloc_target_error",
]


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
        match = re.search(pat, stderr)
        if not match:
            continue
        value = match.group(1)
        if key == "wall_seconds":
            parts = value.split(":")
            if len(parts) == 3:
                result[key] = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                result[key] = float(parts[0]) * 60 + float(parts[1])
            else:
                result[key] = float(value)
        else:
            result[key] = int(value)
    return result


def _generate_tracemalloc_wrapper(
    args: argparse.Namespace, targets: list[str]
) -> tuple[Path, list[str]]:
    """Generate a temporary script that injects tracemalloc into a child Python process."""
    if args.target:
        target_str = args.target.replace("{SIZE}", str(args.sizes[-1] if args.sizes else 10000))
        cmd_list = shlex.split(target_str)
    elif targets:
        cmd_list = [args.python, "-m", "pytest", "-x", "-q", "--benchmark-disable", *targets]
    else:
        raise _missing_target_error()

    wrapper_code = """\
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
"""
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
    index = 0
    while index < len(argv) and argv[index].startswith("-") and argv[index] not in {"-m", "-c"}:
        flag = argv[index]
        unsupported.append(flag)
        index += 1
        if flag in {"-X", "-W"} and index < len(argv):
            index += 1
    if unsupported:
        return "tracemalloc does not support Python interpreter flags: " + " ".join(unsupported)
    return None


def _parse_cachegrind_summary(text: str) -> dict[str, Any]:
    """Parse cg_annotate output for per-file and summary metrics."""
    result: dict[str, Any] = {"files": [], "summary": {}}
    lines = text.splitlines()
    headers: list[str] = []

    for line in lines:
        if line.strip().startswith("Ir"):
            headers = line.split()
            break

    for line in lines:
        if "PROGRAM TOTALS" not in line:
            continue
        parts = line.replace(",", "").split()
        numbers: list[int] = []
        for part in parts:
            try:
                numbers.append(int(float(part)))
            except ValueError:
                continue
        if numbers and headers:
            for header, value in zip(headers[: len(numbers)], numbers):
                result["summary"][header] = value
        break

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("-") or stripped.startswith("Ir"):
            continue
        parts = stripped.replace(",", "").split()
        if len(parts) < 10:
            continue
        filepath = parts[-1]
        if "/" not in filepath and not filepath.endswith((".py", ".c", ".h", ".pyx")):
            continue
        entry: dict[str, Any] = {"file": filepath}
        for header, value in zip(headers[: len(parts) - 1], parts[:-1]):
            try:
                entry[header] = int(value)
            except ValueError:
                pass
        if entry.get("Dr", 0) > 0:
            entry["L1d_miss_pct"] = round(100.0 * entry.get("D1mr", 0) / entry["Dr"], 3)
        if entry.get("Dr", 0) + entry.get("Dw", 0) > 0:
            total_refs = entry.get("Dr", 0) + entry.get("Dw", 0)
            entry["LL_miss_pct"] = round(
                100.0 * (entry.get("DLmr", 0) + entry.get("DLmw", 0)) / total_refs,
                3,
            )
        if entry.get("Bc", 0) > 0:
            entry["branch_mispred_pct"] = round(100.0 * entry.get("Bcm", 0) / entry["Bc"], 3)
        result["files"].append(entry)

    return result


def _parse_callgrind_output(text: str) -> dict[str, Any]:
    """Parse callgrind_annotate output for per-function costs."""
    result: dict[str, Any] = {"functions": [], "total_ir": 0}

    for line in text.splitlines():
        stripped = line.strip()
        if "PROGRAM TOTALS" in stripped:
            for part in stripped.replace(",", "").split():
                if part.isdigit():
                    result["total_ir"] = int(part)
                    break

        match = re.match(r"^\s*([\d,]+)\s+(.+?):(\d+)\s+(.+)$", line)
        if match:
            result["functions"].append(
                {
                    "Ir": int(match.group(1).replace(",", "")),
                    "file": match.group(2),
                    "line": int(match.group(3)),
                    "function": match.group(4).strip(),
                }
            )

    result["functions"].sort(key=lambda function: function.get("Ir", 0), reverse=True)
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


def _parse_massif_out(path: Path) -> dict[str, Any]:
    """Parse massif.out structured text directly."""
    result: dict[str, Any] = {
        "snapshots": [],
        "peak_bytes": 0,
        "peak_snapshot": -1,
        "alloc_sites": [],
    }
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
            match = re.match(r"n\d+:\s+(\d+)\s+(.+)", line)
            if match:
                result["alloc_sites"].append(
                    {"bytes": int(match.group(1)), "location": match.group(2).strip()}
                )

    if current_snap:
        result["snapshots"].append(current_snap)
        heap_bytes_series.append(current_snap.get("mem_heap_B", 0))

    if heap_bytes_series:
        peak_idx = max(range(len(heap_bytes_series)), key=lambda index: heap_bytes_series[index])
        result["peak_bytes"] = heap_bytes_series[peak_idx]
        result["peak_snapshot"] = peak_idx

        maxima = 0
        for index in range(1, len(heap_bytes_series) - 1):
            if (
                heap_bytes_series[index] > heap_bytes_series[index - 1]
                and heap_bytes_series[index] > heap_bytes_series[index + 1]
            ):
                maxima += 1
        result["local_maxima_count"] = maxima
        result["heap_series_len"] = len(heap_bytes_series)

    return result


def _parse_perf_stat(stderr: str) -> dict[str, Any]:
    """Parse perf stat output."""
    result: dict[str, Any] = {"counters": {}}
    for line in stderr.splitlines():
        match = re.match(r"([\d,\.]+)\s+(\S+)", line.strip())
        if not match:
            continue
        value_str = match.group(1).replace(",", "")
        name = match.group(2)
        try:
            result["counters"][name] = float(value_str) if "." in value_str else int(value_str)
        except ValueError:
            pass

    counters = result["counters"]
    if counters.get("instructions") and counters.get("cycles"):
        result["IPC"] = round(counters["instructions"] / counters["cycles"], 3)
    if counters.get("branches") and counters.get("branch-misses"):
        result["branch_mispred_pct"] = round(
            100.0 * counters["branch-misses"] / counters["branches"],
            3,
        )
    if counters.get("L1-dcache-loads") and counters.get("L1-dcache-load-misses"):
        result["L1d_miss_pct"] = round(
            100.0 * counters["L1-dcache-load-misses"] / counters["L1-dcache-loads"],
            3,
        )
    if counters.get("LLC-loads") and counters.get("LLC-load-misses"):
        result["LLC_miss_pct"] = round(
            100.0 * counters["LLC-load-misses"] / counters["LLC-loads"],
            3,
        )
    return result


def _parse_perf_report(stdout: str) -> dict[str, Any]:
    """Parse perf report --stdio hotspot rows."""
    hotspots: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^\s*([\d.]+)%\s+(\S+)\s+(\S+)\s+(.+?)\s*$", line)
        if not match:
            continue
        hotspots.append(
            {
                "overhead_pct": float(match.group(1)),
                "command": match.group(2),
                "shared_object": match.group(3),
                "symbol": match.group(4),
            }
        )
    return {"hotspots": hotspots}


def _discover_objdump_targets(root: Path, source_prefix: str | None) -> list[Path]:
    candidates = sorted(Path(root).rglob("*.so"))
    if not source_prefix:
        return candidates

    direct_matches = [candidate for candidate in candidates if source_prefix in str(candidate)]
    if direct_matches:
        return direct_matches

    source_tokens = {
        token
        for token in Path(source_prefix).parts
        if token and token not in {".", "src", "source", "python", "lib"}
    }
    token_matches = [
        candidate for candidate in candidates if source_tokens.intersection(candidate.parts)
    ]
    return token_matches or candidates
