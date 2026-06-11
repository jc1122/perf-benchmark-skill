"""Tests for deterministic win-verdict wrapper (SP7 C3).

Covers all golden verdict fixtures:
- clean win    --> accept, exit 0, median_win_percent ~10%
- noisy        --> reject, reason "noise", exit 1
- fingerprint  --> reject, reason "fingerprint", exit 1
- timestamp/load_avg only differs --> still accept (ignored)
- regression   --> reject, reason "median", exit 1
- tier drop    --> reject, reason "tier", exit 1
- suite red    --> reject, reason "suite", exit 1
- ledger       --> vs_last echoed; corrupt line --> warning
- empty/missing ledger --> vs_last is {}
- malformed    --> exit 2
- byte-identical across repeated runs
"""

from __future__ import annotations

import json
import subprocess as sp
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_win.py"
CLEAN_BEFORE = FIXTURES / "summary_clean_before.json"
CLEAN_AFTER = FIXTURES / "summary_clean_after.json"


def run_verify(
    before: Path,
    after: Path,
    suite_exit_code: int = 0,
    min_win: float = 5.0,
    ledger: Path | None = None,
    out: Path | None = None,
    tmp_path: Path | None = None,
) -> sp.CompletedProcess[str]:
    """Run verify_win.py with given arguments."""
    if out is None and tmp_path is not None:
        out = tmp_path / "verdict.json"
    elif out is None:
        raise ValueError("out or tmp_path required")
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--before",
        str(before),
        "--after",
        str(after),
        "--suite-exit-code",
        str(suite_exit_code),
        "--min-win",
        str(min_win),
    ]
    if ledger is not None:
        cmd.extend(["--ledger", str(ledger)])
    cmd.extend(["--out", str(out)])
    return sp.run(cmd, capture_output=True, text=True)


# ================================================================== golden tests


def test_clean_win_accept(tmp_path: Path) -> None:
    """before p50 2.0, after p50 1.8 --> 10% win --> accept, exit 0."""
    cp = run_verify(CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 0
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "accept"
    assert verdict["median_win_percent"] == pytest.approx(10.0, rel=1e-4)
    assert verdict["reasons"] == []

    # stdout and --out are identical
    out_content = (tmp_path / "verdict.json").read_text().strip()
    assert out_content == cp.stdout.strip()


def test_clean_win_verdict_shape(tmp_path: Path) -> None:
    """Verdict JSON has exact required shape for accept case."""
    cp = run_verify(CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, tmp_path=tmp_path)

    verdict = json.loads(cp.stdout)
    assert "verdict" in verdict
    assert isinstance(verdict["verdict"], str)
    assert "median_win_percent" in verdict
    assert isinstance(verdict["median_win_percent"], (int, float))
    assert "reasons" in verdict
    assert isinstance(verdict["reasons"], list)
    assert "vs_last" in verdict
    assert verdict["vs_last"] == {}  # no ledger provided
    assert "warnings" not in verdict


def test_noisy_after_rejects(tmp_path: Path) -> None:
    """After summary has Wall-Time Stability N/A (noise) --> reject, reason 'noise', exit 1."""
    noisy_after = FIXTURES / "summary_noisy_after.json"
    cp = run_verify(CLEAN_BEFORE, noisy_after, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 1
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "reject"
    assert "noise" in verdict["reasons"]


def test_noisy_before_rejects(tmp_path: Path) -> None:
    """Before summary has noise --> reject, reason 'noise', exit 1."""
    noisy_before = FIXTURES / "summary_noisy_before.json"
    cp = run_verify(noisy_before, CLEAN_AFTER, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 1
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "reject"
    assert "noise" in verdict["reasons"]


def test_fingerprint_mismatch_governor(tmp_path: Path) -> None:
    """Different governor --> reject, reason 'fingerprint', exit 1."""
    fp_mismatch = FIXTURES / "summary_fingerprint_mismatch.json"
    cp = run_verify(CLEAN_BEFORE, fp_mismatch, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 1
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "reject"
    assert "fingerprint" in verdict["reasons"]


def test_timestamp_and_load_avg_ignored(tmp_path: Path) -> None:
    """timestamp_utc and load_avg_1m differ but all 5 FP keys match --> accept."""
    ts_mismatch = FIXTURES / "summary_timestamp_mismatch.json"
    cp = run_verify(CLEAN_BEFORE, ts_mismatch, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 0
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "accept"
    assert "fingerprint" not in verdict["reasons"]


def test_median_regression_rejects(tmp_path: Path) -> None:
    """after p50 2.2 > before p50 2.0 --> negative win --> reject, reason 'median'."""
    reg_after = FIXTURES / "summary_regression_after.json"
    cp = run_verify(CLEAN_BEFORE, reg_after, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 1
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "reject"
    assert "median" in verdict["reasons"]
    # win_percent should be negative
    assert verdict["median_win_percent"] < 0


def test_tier_drop_rejects(tmp_path: Path) -> None:
    """CPU Efficiency drops from PASS to WARN --> reject, reason 'tier'."""
    tier_drop_after = FIXTURES / "summary_tier_drop_after.json"
    cp = run_verify(CLEAN_BEFORE, tier_drop_after, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 1
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "reject"
    assert "tier" in verdict["reasons"]


def test_suite_red_rejects(tmp_path: Path) -> None:
    """Nonzero suite exit code --> reject, reason 'suite', exit 1."""
    cp = run_verify(CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=1, tmp_path=tmp_path)

    assert cp.returncode == 1
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "reject"
    assert "suite" in verdict["reasons"]


def test_multiple_reasons_reported(tmp_path: Path) -> None:
    """When multiple checks fail, all reasons are reported."""
    # regression after + nonzero suite exit
    reg_after = FIXTURES / "summary_regression_after.json"
    cp = run_verify(CLEAN_BEFORE, reg_after, suite_exit_code=1, tmp_path=tmp_path)

    assert cp.returncode == 1
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "reject"
    assert "median" in verdict["reasons"]
    assert "suite" in verdict["reasons"]


# ===================================================================== ledger tests


def test_ledger_vs_last_echoed(tmp_path: Path) -> None:
    """Ledger given --> vs_last computed and echoed in verdict JSON."""
    ledger_good = FIXTURES / "ledger_good.jsonl"
    cp = run_verify(
        CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, ledger=ledger_good, tmp_path=tmp_path
    )

    assert cp.returncode == 0
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "accept"
    # Good ledger: after dims match last entry --> no regressions --> vs_last is {}
    assert isinstance(verdict["vs_last"], dict)
    assert verdict["vs_last"] == {}


def test_ledger_corrupt_line_warns(tmp_path: Path) -> None:
    """Corrupt JSONL line --> warning emitted, no crash."""
    ledger_corrupt = FIXTURES / "ledger_corrupt.jsonl"
    cp = run_verify(
        CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, ledger=ledger_corrupt, tmp_path=tmp_path
    )

    assert cp.returncode == 0
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "accept"
    assert "warnings" in verdict
    assert any("corrupt" in w or "Skipped" in w for w in verdict["warnings"])


def test_ledger_empty_vs_last_is_empty_object(tmp_path: Path) -> None:
    """Empty ledger --> vs_last is {} (empty object)."""
    ledger_empty = FIXTURES / "ledger_empty.jsonl"
    cp = run_verify(
        CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, ledger=ledger_empty, tmp_path=tmp_path
    )

    assert cp.returncode == 0
    verdict = json.loads(cp.stdout)
    assert isinstance(verdict["vs_last"], dict)
    assert verdict["vs_last"] == {}


def test_ledger_missing_produces_warning(tmp_path: Path) -> None:
    """Missing ledger file --> warning, vs_last is {}, no crash."""
    missing = tmp_path / "nonexistent.jsonl"
    cp = run_verify(CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, ledger=missing, tmp_path=tmp_path)

    assert cp.returncode == 0
    verdict = json.loads(cp.stdout)
    assert "warnings" in verdict
    assert any("not found" in w for w in verdict["warnings"])
    assert isinstance(verdict["vs_last"], dict)
    assert verdict["vs_last"] == {}


def test_no_ledger_vs_last_empty_object(tmp_path: Path) -> None:
    """No --ledger flag --> vs_last is {}."""
    cp = run_verify(CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, ledger=None, tmp_path=tmp_path)

    assert cp.returncode == 0
    verdict = json.loads(cp.stdout)
    assert verdict["vs_last"] == {}


# ============================================================= ledger vs_last shape tests


def test_ledger_vs_last_with_regression(tmp_path: Path) -> None:
    """Ledger shows tier drop in vs_last after dimension regresses."""
    ledger = tmp_path / "ledger.jsonl"
    # Last entry has CPU Efficiency = PASS
    ledger.write_text(
        json.dumps(
            {
                "timestamp_utc": "2025-01-14T09:00:00+00:00",
                "tier": "deep",
                "rubric_total": 24,
                "wall_time_mean": 0.002,
                "dimensions": {
                    "Algorithmic Scaling": "PASS",
                    "CPU Efficiency": "PASS",
                },
            }
        )
        + "\n"
    )

    before = tmp_path / "before.json"
    after = tmp_path / "after.json"

    dims = {
        "Algorithmic Scaling": {"score": 4, "tier": "PASS"},
        "CPU Efficiency": {"score": 2, "tier": "WARN"},
    }
    base = {
        "rubric": {"dimensions": dims},
        "wall_time_percentiles": {"p50": 2.0, "p95": 3.0, "p99": 4.0},
        "environment": {
            "cpu_model": "x",
            "kernel": "x",
            "governor": "x",
            "smt": "1",
            "python_version": "3.11",
        },
    }
    before.write_text(json.dumps(base))
    base["wall_time_percentiles"] = {"p50": 1.8, "p95": 2.8, "p99": 3.8}
    after.write_text(json.dumps(base))

    cp = run_verify(before, after, suite_exit_code=0, ledger=ledger, tmp_path=tmp_path)

    # still accept because before/after comparison wins, but vs_last shows regression
    assert cp.returncode == 0
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "accept"
    assert isinstance(verdict["vs_last"], dict)
    assert "regressions" in verdict["vs_last"]
    regs = verdict["vs_last"]["regressions"]
    assert len(regs) == 1
    assert regs[0]["dimension"] == "CPU Efficiency"
    assert regs[0]["previous_tier"] == "PASS"
    assert regs[0]["current_tier"] == "WARN"
    assert regs[0]["drop"] == 1


def test_vs_last_regression_item_shape(tmp_path: Path) -> None:
    """vs_last regression items have exact shape: dimension, previous_tier, current_tier, drop."""
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        json.dumps(
            {
                "timestamp_utc": "2025-01-14T09:00:00+00:00",
                "tier": "deep",
                "rubric_total": 24,
                "wall_time_mean": 0.002,
                "dimensions": {
                    "Algorithmic Scaling": "PASS",
                    "CPU Efficiency": "PASS",
                    "Memory Profile": "PASS",
                },
            }
        )
        + "\n"
    )

    before = tmp_path / "before.json"
    after = tmp_path / "after.json"

    dims_same = {
        "Algorithmic Scaling": {"score": 2, "tier": "WARN"},
        "CPU Efficiency": {"score": 0, "tier": "FAIL"},
        "Memory Profile": {"score": 4, "tier": "PASS"},
    }
    base = {
        "rubric": {"dimensions": dims_same},
        "wall_time_percentiles": {"p50": 2.0, "p95": 3.0, "p99": 4.0},
        "environment": {
            "cpu_model": "x",
            "kernel": "x",
            "governor": "x",
            "smt": "1",
            "python_version": "3.11",
        },
    }
    before.write_text(json.dumps(base))
    base["wall_time_percentiles"] = {"p50": 1.8, "p95": 2.8, "p99": 3.8}
    after.write_text(json.dumps(base))

    cp = run_verify(before, after, suite_exit_code=0, ledger=ledger, tmp_path=tmp_path)
    # before/after tiers match -> no tier drop; ledger shows regressions
    assert cp.returncode == 0
    verdict = json.loads(cp.stdout)
    regs = verdict["vs_last"]["regressions"]
    assert len(regs) == 2  # Algorithmic Scaling: PASS->WARN, CPU: PASS->FAIL

    for item in regs:
        assert set(item.keys()) == {"dimension", "previous_tier", "current_tier", "drop"}
        assert isinstance(item["dimension"], str)
        assert isinstance(item["previous_tier"], str)
        assert isinstance(item["current_tier"], str)
        assert isinstance(item["drop"], int)
        assert item["drop"] >= 1


def test_vs_last_no_regressions_returns_empty_object(tmp_path: Path) -> None:
    """Ledger with entries but no tier drops --> vs_last is {}."""
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        json.dumps(
            {
                "timestamp_utc": "2025-01-14T09:00:00+00:00",
                "tier": "deep",
                "rubric_total": 24,
                "wall_time_mean": 0.002,
                "dimensions": {
                    "Algorithmic Scaling": "PASS",
                    "CPU Efficiency": "PASS",
                },
            }
        )
        + "\n"
    )

    before = tmp_path / "before.json"
    after = tmp_path / "after.json"

    dims = {
        "Algorithmic Scaling": {"score": 4, "tier": "PASS"},
        "CPU Efficiency": {"score": 4, "tier": "PASS"},
    }
    base = {
        "rubric": {"dimensions": dims},
        "wall_time_percentiles": {"p50": 2.0, "p95": 3.0, "p99": 4.0},
        "environment": {
            "cpu_model": "x",
            "kernel": "x",
            "governor": "x",
            "smt": "1",
            "python_version": "3.11",
        },
    }
    before.write_text(json.dumps(base))
    base["wall_time_percentiles"] = {"p50": 1.8, "p95": 2.8, "p99": 3.8}
    after.write_text(json.dumps(base))

    cp = run_verify(before, after, suite_exit_code=0, ledger=ledger, tmp_path=tmp_path)
    assert cp.returncode == 0
    verdict = json.loads(cp.stdout)
    assert verdict["vs_last"] == {}


# ============================================================ malformed input --> exit 2


def test_malformed_before_json_exit_2(tmp_path: Path) -> None:
    """Before file is not valid JSON --> exit 2."""
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    cp = run_verify(bad, CLEAN_AFTER, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 2
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "error"
    assert any("Before summary error" in w for w in verdict.get("warnings", []))


def test_malformed_after_json_exit_2(tmp_path: Path) -> None:
    """After file is not valid JSON --> exit 2."""
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    cp = run_verify(CLEAN_BEFORE, bad, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 2
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "error"


def test_missing_before_file_exit_2(tmp_path: Path) -> None:
    """Before file does not exist --> exit 2."""
    missing = tmp_path / "missing.json"
    cp = run_verify(missing, CLEAN_AFTER, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 2
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "error"


def test_before_not_a_dict_exit_2(tmp_path: Path) -> None:
    """Before root is a JSON array, not object --> exit 2."""
    bad = tmp_path / "array.json"
    bad.write_text("[]")
    cp = run_verify(bad, CLEAN_AFTER, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 2
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "error"


def test_missing_rubric_exit_2(tmp_path: Path) -> None:
    """Summary missing rubric --> exit 2."""
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"wall_time_percentiles": {"p50": 1.0}, "environment": {}}))
    cp = run_verify(bad, CLEAN_AFTER, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 2
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "error"


def test_missing_p50_exit_2(tmp_path: Path) -> None:
    """Summary missing wall_time_percentiles.p50 --> exit 2."""
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "rubric": {"dimensions": {}},
                "wall_time_percentiles": {"p95": 1.0},
                "environment": {
                    "cpu_model": "x",
                    "kernel": "x",
                    "governor": "x",
                    "smt": "1",
                    "python_version": "3.11",
                },
            }
        )
    )
    cp = run_verify(bad, CLEAN_AFTER, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 2
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "error"


# ===================================================================== determinism


def test_byte_identical_across_runs(tmp_path: Path) -> None:
    """Same inputs --> byte-identical output across repeated runs."""
    out1 = tmp_path / "v1.json"
    out2 = tmp_path / "v2.json"

    cp1 = run_verify(CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, out=out1, tmp_path=tmp_path)
    cp2 = run_verify(CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, out=out2, tmp_path=tmp_path)

    assert cp1.returncode == 0
    assert cp2.returncode == 0
    assert cp1.stdout == cp2.stdout
    assert out1.read_text() == out2.read_text()


def test_byte_identical_reject_across_runs(tmp_path: Path) -> None:
    """Same reject input --> byte-identical reject output."""
    out1 = tmp_path / "v1.json"
    out2 = tmp_path / "v2.json"
    fp_mismatch = FIXTURES / "summary_fingerprint_mismatch.json"
    cp1 = run_verify(CLEAN_BEFORE, fp_mismatch, suite_exit_code=1, out=out1, tmp_path=tmp_path)
    cp2 = run_verify(CLEAN_BEFORE, fp_mismatch, suite_exit_code=1, out=out2, tmp_path=tmp_path)
    assert cp1.stdout == cp2.stdout
    assert out1.read_text() == out2.read_text()


# ===================================================================== edge cases


def test_custom_min_win(tmp_path: Path) -> None:
    """Custom --min-win threshold changes accept/reject boundary."""
    # 10% win, min-win=11% --> should reject
    cp = run_verify(CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, min_win=11.0, tmp_path=tmp_path)

    assert cp.returncode == 1
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "reject"
    assert "median" in verdict["reasons"]

    # 10% win, min-win=10% --> exactly at threshold --> accept
    cp2 = run_verify(CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, min_win=10.0, tmp_path=tmp_path)

    assert cp2.returncode == 0
    verdict2 = json.loads(cp2.stdout)
    assert verdict2["verdict"] == "accept"
    assert "median" not in verdict2["reasons"]


def test_exact_win_at_threshold(tmp_path: Path) -> None:
    """win at exactly min-win still accepts (spec says 'below' = strict <)."""
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(
        json.dumps(
            {
                "rubric": {
                    "dimensions": {
                        "Algorithmic Scaling": {"score": 4, "tier": "PASS"},
                        "Wall-Time Stability": {"score": 4, "tier": "PASS", "cv": 2.0},
                    }
                },
                "wall_time_percentiles": {"p50": 2.0, "p95": 2.1, "p99": 2.2},
                "environment": {
                    "cpu_model": "Test CPU",
                    "kernel": "6.1",
                    "governor": "performance",
                    "smt": "1",
                    "python_version": "3.11",
                    "load_avg_1m": 0.1,
                    "timestamp_utc": "2025-01-01T00:00:00+00:00",
                },
            }
        )
    )
    after.write_text(
        json.dumps(
            {
                "rubric": {
                    "dimensions": {
                        "Algorithmic Scaling": {"score": 4, "tier": "PASS"},
                        "Wall-Time Stability": {"score": 4, "tier": "PASS", "cv": 2.0},
                    }
                },
                "wall_time_percentiles": {"p50": 1.9, "p95": 2.0, "p99": 2.1},
                "environment": {
                    "cpu_model": "Test CPU",
                    "kernel": "6.1",
                    "governor": "performance",
                    "smt": "1",
                    "python_version": "3.11",
                    "load_avg_1m": 0.2,
                    "timestamp_utc": "2025-01-01T00:00:00+00:00",
                },
            }
        )
    )

    cp = run_verify(before, after, suite_exit_code=0, min_win=5.0, tmp_path=tmp_path)
    # win = (2.0-1.9)/2.0*100 = 5.0% --> exactly at threshold --> accept
    assert cp.returncode == 0


def test_median_win_computation(tmp_path: Path) -> None:
    """Verify median win calculation with various values."""
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"

    # before=10, after=8 --> 20% win
    before.write_text(
        json.dumps(
            {
                "rubric": {
                    "dimensions": {
                        "Algorithmic Scaling": {"score": 4, "tier": "PASS"},
                    }
                },
                "wall_time_percentiles": {"p50": 10.0, "p95": 11.0, "p99": 12.0},
                "environment": {
                    "cpu_model": "x",
                    "kernel": "x",
                    "governor": "x",
                    "smt": "1",
                    "python_version": "3.11",
                },
            }
        )
    )
    after.write_text(
        json.dumps(
            {
                "rubric": {
                    "dimensions": {
                        "Algorithmic Scaling": {"score": 4, "tier": "PASS"},
                    }
                },
                "wall_time_percentiles": {"p50": 8.0, "p95": 9.0, "p99": 10.0},
                "environment": {
                    "cpu_model": "x",
                    "kernel": "x",
                    "governor": "x",
                    "smt": "1",
                    "python_version": "3.11",
                },
            }
        )
    )

    cp = run_verify(before, after, suite_exit_code=0, min_win=5.0, tmp_path=tmp_path)

    assert cp.returncode == 0
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "accept"
    assert verdict["median_win_percent"] == pytest.approx(20.0, rel=1e-4)


def test_before_p50_zero_rejects(tmp_path: Path) -> None:
    """before_p50=0 --> median check rejects (cannot compute ratio)."""
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"

    before.write_text(
        json.dumps(
            {
                "rubric": {"dimensions": {"Algorithmic Scaling": {"score": 4, "tier": "PASS"}}},
                "wall_time_percentiles": {"p50": 0.0, "p95": 0.1, "p99": 0.2},
                "environment": {
                    "cpu_model": "x",
                    "kernel": "x",
                    "governor": "x",
                    "smt": "1",
                    "python_version": "3.11",
                },
            }
        )
    )
    after.write_text(
        json.dumps(
            {
                "rubric": {"dimensions": {"Algorithmic Scaling": {"score": 4, "tier": "PASS"}}},
                "wall_time_percentiles": {"p50": 0.0, "p95": 0.1, "p99": 0.2},
                "environment": {
                    "cpu_model": "x",
                    "kernel": "x",
                    "governor": "x",
                    "smt": "1",
                    "python_version": "3.11",
                },
            }
        )
    )

    cp = run_verify(before, after, suite_exit_code=0, tmp_path=tmp_path)
    assert cp.returncode == 1
    verdict = json.loads(cp.stdout)
    assert "median" in verdict["reasons"]


def test_accept_with_missing_dimension_in_after(tmp_path: Path) -> None:
    """A dimension present in before but missing from after --> no tier drop, still accept."""
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"

    before.write_text(
        json.dumps(
            {
                "rubric": {
                    "dimensions": {
                        "Algorithmic Scaling": {"score": 4, "tier": "PASS"},
                        "CPU Efficiency": {"score": 4, "tier": "PASS"},
                    }
                },
                "wall_time_percentiles": {"p50": 2.0, "p95": 3.0, "p99": 4.0},
                "environment": {
                    "cpu_model": "x",
                    "kernel": "x",
                    "governor": "x",
                    "smt": "1",
                    "python_version": "3.11",
                },
            }
        )
    )
    after.write_text(
        json.dumps(
            {
                "rubric": {
                    "dimensions": {
                        "Algorithmic Scaling": {"score": 4, "tier": "PASS"},
                    }
                },
                "wall_time_percentiles": {"p50": 1.0, "p95": 2.0, "p99": 3.0},
                "environment": {
                    "cpu_model": "x",
                    "kernel": "x",
                    "governor": "x",
                    "smt": "1",
                    "python_version": "3.11",
                },
            }
        )
    )

    cp = run_verify(before, after, suite_exit_code=0, min_win=5.0, tmp_path=tmp_path)
    assert cp.returncode == 0
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "accept"
    assert "tier" not in verdict["reasons"]


def test_accept_with_same_tier_keep(tmp_path: Path) -> None:
    """All dimensions same tier --> no tier drop --> accept."""
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"

    dims = {
        "Algorithmic Scaling": {"score": 4, "tier": "PASS"},
        "Wall-Time Stability": {"score": 4, "tier": "PASS", "cv": 2.0},
    }
    base = {
        "rubric": {"dimensions": dims},
        "wall_time_percentiles": {"p50": 2.0, "p95": 3.0, "p99": 4.0},
        "environment": {
            "cpu_model": "x",
            "kernel": "x",
            "governor": "x",
            "smt": "1",
            "python_version": "3.11",
        },
    }
    before.write_text(json.dumps(base))
    base["wall_time_percentiles"] = {"p50": 1.8, "p95": 2.8, "p99": 3.8}
    after.write_text(json.dumps(base))

    cp = run_verify(before, after, suite_exit_code=0, min_win=5.0, tmp_path=tmp_path)
    assert cp.returncode == 0


def test_fingerprint_all_keys_compared(tmp_path: Path) -> None:
    """Verify each of the 5 fingerprint keys is checked independently."""
    env_base = {
        "rubric": {
            "dimensions": {
                "Algorithmic Scaling": {"score": 4, "tier": "PASS"},
            }
        },
        "wall_time_percentiles": {"p50": 2.0, "p95": 3.0, "p99": 4.0},
        "environment": {
            "cpu_model": "x",
            "kernel": "x",
            "governor": "x",
            "smt": "1",
            "python_version": "3.11",
            "load_avg_1m": 0.1,
            "timestamp_utc": "2025-01-01T00:00:00+00:00",
        },
    }

    mismatch_keys = {
        "cpu_model": "y",
        "kernel": "5.15.0",
        "governor": "powersave",
        "smt": "0",
        "python_version": "3.12",
    }

    for key, bad_value in mismatch_keys.items():
        before = tmp_path / f"before_{key}.json"
        after = tmp_path / f"after_{key}.json"
        before.write_text(json.dumps(env_base))
        bad_env = json.loads(json.dumps(env_base))
        bad_env["environment"][key] = bad_value
        after.write_text(json.dumps(bad_env))

        cp = run_verify(before, after, suite_exit_code=0, tmp_path=tmp_path)
        assert cp.returncode == 1, f"Key {key} mismatch should reject"
        verdict = json.loads(cp.stdout)
        assert "fingerprint" in verdict["reasons"], (
            f"Key {key} mismatch should produce fingerprint reason"
        )


def test_suite_exit_code_negative(tmp_path: Path) -> None:
    """Negative suite exit code --> reject with 'suite'."""
    cp = run_verify(CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=-1, tmp_path=tmp_path)
    assert cp.returncode == 1
    verdict = json.loads(cp.stdout)
    assert "suite" in verdict["reasons"]


def test_stdout_equals_out_file(tmp_path: Path) -> None:
    """stdout and --out file contents are identical."""
    out = tmp_path / "verdict.json"
    cp = run_verify(CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, out=out, tmp_path=tmp_path)
    assert out.exists()
    assert out.read_text().strip() == cp.stdout.strip()


def test_noise_and_median_collected(tmp_path: Path) -> None:
    """Noise and median both fail --> both in reasons."""
    noisy_before = FIXTURES / "summary_noisy_before.json"
    reg_after = FIXTURES / "summary_regression_after.json"
    cp = run_verify(noisy_before, reg_after, suite_exit_code=0, tmp_path=tmp_path)
    assert cp.returncode == 1
    verdict = json.loads(cp.stdout)
    assert "median" in verdict["reasons"]
    assert "noise" in verdict["reasons"]


def test_warnings_key_absent_when_no_warnings(tmp_path: Path) -> None:
    """When no ledger or clean ledger, warnings key is absent."""
    cp = run_verify(
        CLEAN_BEFORE,
        CLEAN_AFTER,
        suite_exit_code=0,
        ledger=FIXTURES / "ledger_good.jsonl",
        tmp_path=tmp_path,
    )
    verdict = json.loads(cp.stdout)
    # Good ledger, no corrupt lines --> no warnings key
    assert "warnings" not in verdict
