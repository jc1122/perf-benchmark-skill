from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "perf_benchmark_pipeline.py"

SPEC = importlib.util.spec_from_file_location("perf_benchmark_pipeline", MODULE_PATH)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


def make_args(tmp_path: Path, **overrides: object) -> Namespace:
    defaults: dict[str, object] = {
        "root": tmp_path,
        "out_dir": tmp_path / "out",
        "target": None,
        "binary": None,
        "python": sys.executable,
        "source_prefix": None,
        "tier": "medium",
        "sizes": [],
        "valgrind_size": 10_000,
        "max_valgrind_parallel": 2,
        "expected_complexity": "nlogn",
        "baseline": None,
        "perf_repeats": 1,
        "perf_events": None,
        "perf_record": False,
        "time_repeats": 1,
        "asm_audit": False,
        "valgrind_timeout": 30,
        "env": [],
    }
    defaults.update(overrides)
    return Namespace(**defaults)
