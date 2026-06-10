"""Deterministic self-benchmark: parse a synthetic massif.out of SIZE snapshots."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from perf_benchmark.stage_helpers import _parse_massif_out  # noqa: E402


def make_massif(path: Path, size: int) -> None:
    lines = ["desc: synthetic", "cmd: bench", "time_unit: i"]
    for i in range(size):
        lines += [
            f"snapshot={i}",
            f"time={i}",
            f"mem_heap_B={i * 13}",
            "mem_heap_extra_B=0",
            "mem_stacks_B=0",
            "heap_tree=empty",
        ]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    size = int(sys.argv[1])
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "massif.out"
        make_massif(p, size)
        for _ in range(20):
            result = _parse_massif_out(p)
    assert result, "parse produced nothing"


if __name__ == "__main__":
    main()
