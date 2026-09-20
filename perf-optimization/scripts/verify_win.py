#!/usr/bin/env python3
"""Backward-compatible wrapper for verify_win.

Canonical code lives in scripts/perf_benchmark/verify_win.py.
Kept for one migration release; new callers should use the canonical path
or the `perf-verify-win` console script.
"""

from __future__ import annotations

import sys
from pathlib import Path

_CANONICAL = Path(__file__).resolve().parents[2] / "scripts" / "perf_benchmark" / "verify_win.py"

if __name__ == "__main__":
    import runpy

    sys.argv[0] = str(_CANONICAL)
    runpy.run_path(str(_CANONICAL), run_name="__main__")
