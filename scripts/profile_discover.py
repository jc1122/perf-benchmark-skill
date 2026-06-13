# scripts/profile_discover.py
"""Discovery tier: rank function hotspots of a representative run via cProfile.

Deterministic ranking (relative timings only — never used for the win gate).
"""

from __future__ import annotations

import argparse
import cProfile
import json
import pstats
import runpy
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _stats_to_rows(stats: pstats.Stats, top: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    # stats.stats: {(file, line, func): (cc, nc, tt, ct, callers)}
    for (fname, lineno, func), (_cc, nc, tt, ct, _callers) in stats.stats.items():
        rows.append(
            {
                "function": f"{Path(fname).name}:{lineno}:{func}",
                "ncalls": nc,
                "total_s": round(tt, 6),
                "cumulative_s": round(ct, 6),
            }
        )
    rows.sort(key=lambda r: (r["cumulative_s"], r["total_s"]), reverse=True)
    return rows[:top]


def rank_hotspots(fn: Callable[[], Any], top: int = 20) -> list[dict[str, Any]]:
    profiler = cProfile.Profile()
    profiler.enable()
    fn()
    profiler.disable()
    return _stats_to_rows(pstats.Stats(profiler), top)


def _run_script(path: Path) -> Callable[[], None]:
    def runner() -> None:
        runpy.run_path(str(path), run_name="__main__")

    return runner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rank hotspots of a representative run.")
    parser.add_argument(
        "--script", required=True, type=Path, help="Python script to run under cProfile"
    )
    parser.add_argument("--out", required=True, type=Path, help="Output ranked JSON path")
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args(argv)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        rows = rank_hotspots(_run_script(args.script), top=args.top)
    except BaseException as exc:  # noqa: BLE001 — the representative run is arbitrary user code
        args.out.write_text(
            json.dumps({"error": f"representative run failed: {exc!r}"}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"profile_discover: representative run failed: {exc!r}", file=sys.stderr)
        return 2
    args.out.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
