# tests/test_profile_discover.py
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import profile_discover as pd  # noqa: E402


def test_rank_hotspots_orders_by_cumulative_time():
    def slow(n):
        return sum(i * i for i in range(n))

    def caller():
        for _ in range(50):
            slow(2000)

    rows = pd.rank_hotspots(caller, top=5)
    # rows are dicts sorted by cumulative time, descending
    assert rows, "expected at least one hotspot row"
    assert rows == sorted(rows, key=lambda r: r["cumulative_s"], reverse=True)
    names = [r["function"] for r in rows]
    assert any("slow" in n for n in names)
    for r in rows:
        assert {"function", "ncalls", "cumulative_s", "total_s"} <= set(r)


def test_main_writes_ranked_json(tmp_path):
    target = tmp_path / "mod.py"
    target.write_text(
        "def work(n):\n    return sorted(range(n), reverse=True)\n\n"
        "def main():\n    [work(1000) for _ in range(20)]\n\n"
        "if __name__ == '__main__':\n    main()\n",
        encoding="utf-8",
    )
    out = tmp_path / "ranked.json"
    rc = pd.main(["--script", str(target), "--out", str(out), "--top", "10"])
    assert rc == 0
    data = json.loads(out.read_text())
    assert isinstance(data, list) and data
    assert "work" in {r["function"].split(":")[-1] for r in data} or any(
        "work" in r["function"] for r in data
    )
