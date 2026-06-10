"""Tests for append-only run history ledger with vs-last/vs-best regression checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from perf_benchmark.ledger import append_run, compare  # noqa: E402


def _make_summary(
    *,
    tier: str = "medium",
    total: int = 20,
    wall_time_mean: float | None = 0.05,
    dimensions: dict[str, str] | None = None,
) -> dict:
    """Build a minimal benchmark_summary dict."""
    if dimensions is None:
        dimensions = {
            "Algorithmic Scaling": "PASS",
            "Wall-Time Stability": "PASS",
            "CPU Efficiency": "PASS",
        }
    dims = {name: {"tier": t, "score": 4} for name, t in dimensions.items()}
    return {
        "tier": tier,
        "rubric": {"total": total, "max_possible": 28, "dimensions": dims},
        "wall_time_mean": wall_time_mean,
    }


# ── append_run ────────────────────────────────────────────────────────


def test_append_run_creates_file_with_one_json_line(tmp_path: Path) -> None:
    ledger_path = tmp_path / "runs.jsonl"
    summary = _make_summary()
    append_run(ledger_path, summary)
    assert ledger_path.exists()
    lines = ledger_path.read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["tier"] == "medium"
    assert entry["rubric_total"] == 20
    assert entry["wall_time_mean"] == 0.05
    assert entry["dimensions"]["Algorithmic Scaling"] == "PASS"


def test_append_run_includes_timestamp_utc_and_required_keys(tmp_path: Path) -> None:
    ledger_path = tmp_path / "runs.jsonl"
    summary = _make_summary()
    append_run(ledger_path, summary)
    entry = json.loads(ledger_path.read_text().strip().splitlines()[0])
    required_keys = {"timestamp_utc", "tier", "rubric_total", "wall_time_mean", "dimensions"}
    assert required_keys <= set(entry)
    # timestamp_utc must end with Z or +00:00 (ISO 8601 UTC)
    assert entry["timestamp_utc"].endswith("Z") or "+00:00" in entry["timestamp_utc"]


def test_append_run_appends_second_line(tmp_path: Path) -> None:
    ledger_path = tmp_path / "runs.jsonl"
    append_run(ledger_path, _make_summary(total=10))
    append_run(ledger_path, _make_summary(total=20))
    lines = ledger_path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["rubric_total"] == 10
    assert json.loads(lines[1])["rubric_total"] == 20


def test_append_run_creates_parent_directories(tmp_path: Path) -> None:
    ledger_path = tmp_path / "deeply" / "nested" / "ledger.jsonl"
    assert not ledger_path.parent.exists()
    append_run(ledger_path, _make_summary())
    assert ledger_path.exists()


def test_append_run_handles_none_wall_time_mean(tmp_path: Path) -> None:
    ledger_path = tmp_path / "runs.jsonl"
    summary = _make_summary(wall_time_mean=None)
    append_run(ledger_path, summary)
    entry: dict = json.loads(ledger_path.read_text().strip().splitlines()[0])
    assert entry["wall_time_mean"] is None


# ── compare ───────────────────────────────────────────────────────────


def test_compare_missing_ledger_returns_empty(tmp_path: Path) -> None:
    ledger_path = tmp_path / "nonexistent.jsonl"
    result = compare(ledger_path, _make_summary())
    assert result["vs_last"] == []
    assert result["vs_best"] == []
    assert result["warnings"] == []


def test_compare_empty_ledger_returns_empty(tmp_path: Path) -> None:
    ledger_path = tmp_path / "empty.jsonl"
    ledger_path.write_text("")
    result = compare(ledger_path, _make_summary())
    assert result["vs_last"] == []
    assert result["vs_best"] == []
    assert result["warnings"] == []


def test_compare_single_entry_returns_empty(tmp_path: Path) -> None:
    ledger_path = tmp_path / "single.jsonl"
    ledger_path.write_text(
        json.dumps(
            {
                "timestamp_utc": "2024-01-01T00:00:00Z",
                "tier": "medium",
                "rubric_total": 24,
                "wall_time_mean": 0.05,
                "dimensions": {"CPU Efficiency": "PASS", "Memory Profile": "PASS"},
            }
        )
        + "\n"
    )
    result = compare(
        ledger_path,
        _make_summary(dimensions={"CPU Efficiency": "PASS", "Memory Profile": "PASS"}),
    )
    assert result["vs_last"] == []  # same tiers, no drop
    assert result["vs_best"] == []
    assert result["warnings"] == []


def test_compare_detects_regression_vs_last_entry(tmp_path: Path) -> None:
    ledger_path = tmp_path / "runs.jsonl"
    # First run: CPU = PASS
    ledger_path.write_text(
        json.dumps(
            {
                "timestamp_utc": "2024-01-01T00:00:00Z",
                "tier": "medium",
                "rubric_total": 24,
                "wall_time_mean": 0.05,
                "dimensions": {"CPU Efficiency": "PASS", "Memory Profile": "PASS"},
            }
        )
        + "\n"
    )
    # Second run: CPU = WARN, Memory = WARN
    ledger_path.open("a").write(
        json.dumps(
            {
                "timestamp_utc": "2024-01-02T00:00:00Z",
                "tier": "medium",
                "rubric_total": 20,
                "wall_time_mean": 0.08,
                "dimensions": {"CPU Efficiency": "WARN", "Memory Profile": "WARN"},
            }
        )
        + "\n"
    )
    # Current run: CPU = FAIL, Memory = WARN (CPU dropped vs last, Memory same)
    summary = _make_summary(
        dimensions={"CPU Efficiency": "FAIL", "Memory Profile": "WARN"},
        total=16,
    )
    result = compare(ledger_path, summary)
    # vs_last: CPU dropped WARN→FAIL (drop=1), Memory same
    assert len(result["vs_last"]) == 1
    assert result["vs_last"][0]["dimension"] == "CPU Efficiency"
    assert result["vs_last"][0]["previous_tier"] == "WARN"
    assert result["vs_last"][0]["current_tier"] == "FAIL"
    assert result["vs_last"][0]["drop"] == 1
    # vs_best: best entry is the first (rubric_total=24, CPU=PASS, Memory=PASS)
    # CPU dropped PASS→FAIL (drop=2), Memory dropped PASS→WARN (drop=1)
    assert len(result["vs_best"]) == 2
    vs_best_by_dim = {r["dimension"]: r for r in result["vs_best"]}
    assert vs_best_by_dim["CPU Efficiency"]["best_tier"] == "PASS"
    assert vs_best_by_dim["CPU Efficiency"]["current_tier"] == "FAIL"
    assert vs_best_by_dim["CPU Efficiency"]["drop"] == 2
    assert vs_best_by_dim["Memory Profile"]["best_tier"] == "PASS"
    assert vs_best_by_dim["Memory Profile"]["current_tier"] == "WARN"
    assert vs_best_by_dim["Memory Profile"]["drop"] == 1


def test_compare_no_regressions_when_all_unchanged(tmp_path: Path) -> None:
    ledger_path = tmp_path / "runs.jsonl"
    ledger_path.write_text(
        json.dumps(
            {
                "timestamp_utc": "2024-01-01T00:00:00Z",
                "tier": "medium",
                "rubric_total": 24,
                "wall_time_mean": 0.05,
                "dimensions": {"CPU Efficiency": "PASS", "Memory Profile": "PASS"},
            }
        )
        + "\n"
    )
    result = compare(
        ledger_path,
        _make_summary(dimensions={"CPU Efficiency": "PASS", "Memory Profile": "PASS"}),
    )
    assert result["vs_last"] == []
    assert result["vs_best"] == []


def test_compare_vs_best_uses_max_rubric_total(tmp_path: Path) -> None:
    """vs_best should compare against the entry with the highest rubric_total."""
    ledger_path = tmp_path / "runs.jsonl"
    # Entry 1: total=20, CPU=PASS
    # Entry 2: total=24, CPU=WARN
    # Entry 3: total=12, CPU=FAIL
    lines = [
        {
            "timestamp_utc": "2024-01-01T00:00:00Z",
            "tier": "medium",
            "rubric_total": 20,
            "wall_time_mean": 0.05,
            "dimensions": {"CPU Efficiency": "PASS"},
        },
        {
            "timestamp_utc": "2024-01-02T00:00:00Z",
            "tier": "medium",
            "rubric_total": 24,
            "wall_time_mean": 0.06,
            "dimensions": {"CPU Efficiency": "WARN"},
        },
        {
            "timestamp_utc": "2024-01-03T00:00:00Z",
            "tier": "medium",
            "rubric_total": 12,
            "wall_time_mean": 0.07,
            "dimensions": {"CPU Efficiency": "FAIL"},
        },
    ]
    ledger_path.write_text("\n".join(json.dumps(entry) for entry in lines) + "\n")
    # Current: CPU=FAIL, total=8
    result = compare(
        ledger_path,
        _make_summary(dimensions={"CPU Efficiency": "FAIL"}, total=8),
    )
    # vs_last: last entry (total=12, CPU=FAIL) — same tier, no drop
    assert result["vs_last"] == []
    # vs_best: best entry (total=24, CPU=WARN) — CPU went WARN→FAIL, drop=1
    assert len(result["vs_best"]) == 1
    assert result["vs_best"][0]["dimension"] == "CPU Efficiency"
    assert result["vs_best"][0]["best_tier"] == "WARN"
    assert result["vs_best"][0]["drop"] == 1


def test_compare_skips_corrupt_line_with_warning(tmp_path: Path) -> None:
    ledger_path = tmp_path / "runs.jsonl"
    ledger_path.write_text(
        "not valid json\n"
        + json.dumps(
            {
                "timestamp_utc": "2024-01-01T00:00:00Z",
                "tier": "medium",
                "rubric_total": 24,
                "wall_time_mean": 0.05,
                "dimensions": {"CPU Efficiency": "PASS"},
            }
        )
        + "\n"
    )
    result = compare(
        ledger_path,
        _make_summary(dimensions={"CPU Efficiency": "PASS"}, total=24),
    )
    assert result["vs_last"] == []
    assert result["vs_best"] == []
    assert len(result["warnings"]) == 1
    assert "corrupt" in result["warnings"][0].lower() or "line" in result["warnings"][0].lower()


def test_compare_skips_blank_lines_without_warning(tmp_path: Path) -> None:
    ledger_path = tmp_path / "runs.jsonl"
    ledger_path.write_text(
        "\n"
        + json.dumps(
            {
                "timestamp_utc": "2024-01-01T00:00:00Z",
                "tier": "medium",
                "rubric_total": 24,
                "wall_time_mean": 0.05,
                "dimensions": {"CPU Efficiency": "PASS"},
            }
        )
        + "\n\n"
    )
    result = compare(
        ledger_path,
        _make_summary(dimensions={"CPU Efficiency": "PASS"}, total=24),
    )
    assert result["warnings"] == []
    assert result["vs_last"] == []


def test_compare_handles_missing_dimensions_gracefully(tmp_path: Path) -> None:
    """Dimension present in current but not in ledger entry should be ignored."""
    ledger_path = tmp_path / "runs.jsonl"
    ledger_path.write_text(
        json.dumps(
            {
                "timestamp_utc": "2024-01-01T00:00:00Z",
                "tier": "medium",
                "rubric_total": 24,
                "wall_time_mean": 0.05,
                "dimensions": {"CPU Efficiency": "PASS"},
            }
        )
        + "\n"
    )
    # Current summary has a new dimension not in the ledger
    result = compare(
        ledger_path,
        _make_summary(
            dimensions={"CPU Efficiency": "WARN", "New Dimension": "PASS"},
            total=20,
        ),
    )
    # CPU dropped vs last, New Dimension not in ledger → ignored
    assert len(result["vs_last"]) == 1
    assert result["vs_last"][0]["dimension"] == "CPU Efficiency"


def test_compare_handles_unknown_tiers(tmp_path: Path) -> None:
    """Non-standard tier values should not cause a crash."""
    ledger_path = tmp_path / "runs.jsonl"
    ledger_path.write_text(
        json.dumps(
            {
                "timestamp_utc": "2024-01-01T00:00:00Z",
                "tier": "medium",
                "rubric_total": 24,
                "wall_time_mean": 0.05,
                "dimensions": {"CPU Efficiency": "CUSTOM_TIER"},
            }
        )
        + "\n"
    )
    result = compare(
        ledger_path,
        _make_summary(dimensions={"CPU Efficiency": "PASS"}, total=20),
    )
    # Unknown tiers are not in TIER_RANK, so no comparison possible
    assert result["vs_last"] == []
    assert result["vs_best"] == []
    assert result["warnings"] == []


def test_compare_never_crashes_on_empty_dimensions(tmp_path: Path) -> None:
    """Ledger entry with missing or None dimensions should be handled."""
    ledger_path = tmp_path / "runs.jsonl"
    ledger_path.write_text(
        json.dumps(
            {
                "timestamp_utc": "2024-01-01T00:00:00Z",
                "tier": "medium",
                "rubric_total": 24,
                "wall_time_mean": 0.05,
            }
        )
        + "\n"
    )
    result = compare(
        ledger_path,
        _make_summary(dimensions={"CPU Efficiency": "PASS"}, total=20),
    )
    # No dimensions in ledger entry → nothing to compare
    assert result["vs_last"] == []
    assert result["vs_best"] == []
    assert result["warnings"] == []


def test_compare_detects_improvement_without_false_regression(tmp_path: Path) -> None:
    """Improvements (tier going up) should NOT be reported as regressions."""
    ledger_path = tmp_path / "runs.jsonl"
    ledger_path.write_text(
        json.dumps(
            {
                "timestamp_utc": "2024-01-01T00:00:00Z",
                "tier": "medium",
                "rubric_total": 16,
                "wall_time_mean": 0.10,
                "dimensions": {"CPU Efficiency": "FAIL"},
            }
        )
        + "\n"
    )
    # Current is better than ledger
    result = compare(
        ledger_path,
        _make_summary(dimensions={"CPU Efficiency": "PASS"}, total=24),
    )
    assert result["vs_last"] == []
    assert result["vs_best"] == []


def test_compare_multiple_regressions_vs_last(tmp_path: Path) -> None:
    """Multiple dimensions can regress simultaneously."""
    ledger_path = tmp_path / "runs.jsonl"
    ledger_path.write_text(
        json.dumps(
            {
                "timestamp_utc": "2024-01-01T00:00:00Z",
                "tier": "medium",
                "rubric_total": 24,
                "wall_time_mean": 0.05,
                "dimensions": {
                    "CPU Efficiency": "PASS",
                    "Memory Profile": "PASS",
                    "L1 Cache Efficiency": "WARN",
                },
            }
        )
        + "\n"
    )
    result = compare(
        ledger_path,
        _make_summary(
            dimensions={
                "CPU Efficiency": "FAIL",
                "Memory Profile": "FAIL",
                "L1 Cache Efficiency": "FAIL",
            },
            total=0,
        ),
    )
    assert len(result["vs_last"]) == 3
    names = {r["dimension"] for r in result["vs_last"]}
    assert names == {"CPU Efficiency", "Memory Profile", "L1 Cache Efficiency"}
