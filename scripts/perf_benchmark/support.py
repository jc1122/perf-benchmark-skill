from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import sys
from pathlib import Path
from typing import Any

__all__ = [
    "_build_env",
    "_build_target_cmd",
    "_build_valgrind_target_cmd",
    "_detect_cache_fallback",
    "_log",
    "_missing_target_error",
    "_parse_cache_size",
    "check_cpu_governor",
    "check_perf_paranoid",
    "check_prerequisites",
    "check_python_version",
    "check_ram_mb",
    "check_valgrind",
    "detect_cache_topology",
    "discover_targets",
]

_PYTEST_BENCHMARK_MARKER = re.compile(r"(?:@\s*|pytestmark\s*=\s*)(?:pytest\.)?mark\.benchmark\b")


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


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
        return Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor").read_text().strip()
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
            size_bytes = _parse_cache_size(size_str)
            indexes[idx_dir.name] = {
                "type": ctype,
                "size": str(size_bytes),
                "assoc": assoc,
                "line": line,
                "level": level,
            }
    except OSError:
        return _detect_cache_fallback()

    for info in indexes.values():
        flag_val = f"{info['size']},{info['assoc']},{info['line']}"
        if info["type"] == "Data" and info["level"] == "1":
            result["D1"] = flag_val
        elif info["type"] == "Instruction" and info["level"] == "1":
            result["I1"] = flag_val
        elif info["type"] == "Unified" and int(info["level"]) >= 3:
            result["LL"] = flag_val

    if not result.get("LL"):
        for info in indexes.values():
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
    _log(
        "  WARNING: sysfs cache detection failed, using getconf (may be inaccurate on hybrid CPUs)"
    )
    result = {}
    try:
        result["D1"] = ",".join(
            [
                str(os.sysconf("SC_LEVEL1_DCACHE_SIZE")),
                str(os.sysconf("SC_LEVEL1_DCACHE_ASSOC")),
                str(os.sysconf("SC_LEVEL1_DCACHE_LINESIZE")),
            ]
        )
    except (ValueError, OSError):
        pass
    try:
        result["I1"] = ",".join(
            [
                str(os.sysconf("SC_LEVEL1_ICACHE_SIZE")),
                str(os.sysconf("SC_LEVEL1_ICACHE_ASSOC")),
                str(os.sysconf("SC_LEVEL1_ICACHE_LINESIZE")),
            ]
        )
    except (ValueError, OSError):
        pass
    try:
        result["LL"] = ",".join(
            [
                str(os.sysconf("SC_LEVEL3_CACHE_SIZE")),
                str(os.sysconf("SC_LEVEL3_CACHE_ASSOC")),
                str(os.sysconf("SC_LEVEL3_CACHE_LINESIZE")),
            ]
        )
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
    prereqs: dict[str, Any] = {
        "python_ok": check_python_version(),
        "valgrind": check_valgrind(),
        "perf_paranoid": check_perf_paranoid(),
        "governor": check_cpu_governor(),
        "cache_topology": detect_cache_topology(),
        "ram_mb": check_ram_mb(),
    }

    if prereqs["governor"] not in ("performance", "unknown"):
        _log(
            f"  WARNING: CPU governor is '{prereqs['governor']}', not 'performance'. "
            "Results may have 10-30% variance."
        )
        _log("  Fix: sudo cpupower frequency-set -g performance")

    if prereqs["perf_paranoid"] > 1:
        _log(f"  INFO: perf_event_paranoid={prereqs['perf_paranoid']}. perf stat will be skipped.")
        _log("  Fix: sudo sysctl kernel.perf_event_paranoid=1")

    if not prereqs["valgrind"] and args.tier != "fast":
        _log("  WARNING: valgrind not found. Valgrind-backed stages will be skipped.")

    ram = prereqs["ram_mb"]
    if ram > 0 and ram < args.max_valgrind_parallel * 4000:
        _log(
            f"  WARNING: {ram}MB RAM with --max-valgrind-parallel="
            f"{args.max_valgrind_parallel} may cause memory pressure."
        )

    return prereqs


def discover_targets(root: Path) -> list[str]:
    """Scan for pytest benchmark tests. Returns paths relative to root."""
    bench_dir = root / "tests" / "benchmarks"
    if bench_dir.is_dir():
        return [str(bench_dir.relative_to(root))]

    targets: list[str] = []
    for py_file in root.rglob("test_*.py"):
        try:
            text = py_file.read_text(errors="replace")
        except OSError:
            continue
        if _PYTEST_BENCHMARK_MARKER.search(text):
            targets.append(str(py_file.relative_to(root)))
        if len(targets) >= 20:
            break
    return targets


def _build_env(base: dict[str, str], env_pairs: list[str]) -> dict[str, str]:
    env = {**base}
    for pair in env_pairs:
        if "=" in pair:
            key, _, value = pair.partition("=")
            env[key] = value
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
        return [args.python, "-m", "pytest", "-x", "-q", "--benchmark-disable", *targets]
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
            args.python,
            "-m",
            "pytest",
            "-x",
            "-q",
            "--benchmark-enable",
            "--benchmark-only",
            *targets,
        ]
    raise _missing_target_error()
