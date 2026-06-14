"""Tests for the shared-schema PERF findings bridge."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FINDINGS_PATH = REPO_ROOT / "scripts" / "perf_benchmark" / "findings.py"

SPEC = importlib.util.spec_from_file_location("findings", FINDINGS_PATH)
assert SPEC and SPEC.loader
findings = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(findings)


def _expected_id(root: str, metric_name: str) -> str:
    id_input = f"perf-benchmark|{root}|<workload>|{metric_name}"
    return hashlib.sha1(id_input.encode()).hexdigest()[:16]


def test_to_shared_findings_fail_dimension_produces_finding() -> None:
    """A FAIL dimension produces a finding with exact keys and correct values."""
    rubric = {
        "dimensions": [
            (
                "L1 cache efficiency",
                {
                    "tier": "FAIL",
                    "score": 0,
                    "metric": "l1_miss_rate",
                    "value": 9.3,
                    "threshold": 5.0,
                },
            ),
        ],
        "total": 0,
        "max_possible": 4,
        "baseline_regressions": [],
    }

    result = findings.to_shared_findings(rubric, root="/repo")

    assert len(result) == 1
    f = result[0]

    # Exact keys
    expected_keys = {
        "id",
        "leaf",
        "signal",
        "severity",
        "path",
        "location",
        "metric",
        "evidence",
        "confidence",
        "suggested_action",
    }
    assert set(f.keys()) == expected_keys

    # Fixed values
    assert f["leaf"] == "perf-benchmark"
    assert f["signal"] == "PERF"
    assert f["path"] == "/repo"
    assert f["location"] == {"line_start": 0, "line_end": 0, "symbol": "<workload>"}
    assert f["metric"] == {"name": "l1_miss_rate", "value": 9.3, "threshold": 5.0}
    assert f["severity"] == "high"
    assert f["id"] == _expected_id("/repo", "l1_miss_rate")


def test_warn_dimension_produces_medium_severity() -> None:
    """A WARN dimension produces severity 'medium'."""
    rubric = {
        "dimensions": [
            (
                "L1 cache efficiency",
                {
                    "tier": "WARN",
                    "score": 2,
                    "metric": "l1_miss_rate",
                    "value": 3.2,
                    "threshold": 5.0,
                },
            ),
        ],
        "total": 2,
        "max_possible": 4,
        "baseline_regressions": [],
    }

    result = findings.to_shared_findings(rubric, root="/repo")

    assert len(result) == 1
    assert result[0]["severity"] == "medium"
    assert result[0]["id"] == _expected_id("/repo", "l1_miss_rate")


def test_pass_dimension_produces_no_finding() -> None:
    """PASS dimensions are skipped."""
    rubric = {
        "dimensions": [
            (
                "L1 cache efficiency",
                {
                    "tier": "PASS",
                    "score": 4,
                    "metric": "l1_miss_rate",
                    "value": 0.3,
                    "threshold": 5.0,
                },
            ),
        ],
        "total": 4,
        "max_possible": 4,
        "baseline_regressions": [],
    }

    result = findings.to_shared_findings(rubric, root="/repo")

    assert len(result) == 0


def test_na_dimension_produces_no_finding() -> None:
    """N/A dimensions are skipped."""
    rubric = {
        "dimensions": [
            (
                "Algorithmic Scaling",
                {
                    "score": -1,
                    "tier": "N/A",
                    "note": "Insufficient data",
                },
            ),
        ],
        "total": 0,
        "max_possible": 0,
        "baseline_regressions": [],
    }

    result = findings.to_shared_findings(rubric, root="/repo")

    assert len(result) == 0


def test_to_shared_findings_sorts_by_path_then_metric_name() -> None:
    """Findings are sorted by (path, metric.name)."""
    rubric = {
        "dimensions": [
            (
                "Branch Prediction",
                {
                    "tier": "FAIL",
                    "score": 0,
                    "metric": "branch_mispred_rate",
                    "value": 4.0,
                    "threshold": 3.0,
                },
            ),
            (
                "L1 cache efficiency",
                {
                    "tier": "FAIL",
                    "score": 0,
                    "metric": "l1_miss_rate",
                    "value": 9.3,
                    "threshold": 5.0,
                },
            ),
            (
                "Last-Level Cache",
                {
                    "tier": "FAIL",
                    "score": 0,
                    "metric": "ll_miss_rate",
                    "value": 3.0,
                    "threshold": 2.0,
                },
            ),
        ],
        "total": 0,
        "max_possible": 12,
        "baseline_regressions": [],
    }

    result = findings.to_shared_findings(rubric, root="/repo")

    assert len(result) == 3
    assert result[0]["metric"]["name"] == "branch_mispred_rate"
    assert result[1]["metric"]["name"] == "l1_miss_rate"
    assert result[2]["metric"]["name"] == "ll_miss_rate"


def test_to_shared_findings_is_byte_identical_across_calls() -> None:
    """Two calls with the same input produce byte-identical output."""
    import json

    rubric = {
        "dimensions": [
            (
                "L1 cache efficiency",
                {
                    "tier": "FAIL",
                    "score": 0,
                    "metric": "l1_miss_rate",
                    "value": 9.3,
                    "threshold": 5.0,
                },
            ),
            (
                "Wall-Time Stability",
                {
                    "tier": "PASS",
                    "score": 4,
                    "cv": 1.2,
                },
            ),
        ],
        "total": 0,
        "max_possible": 4,
        "baseline_regressions": [],
    }

    result1 = json.dumps(
        findings.to_shared_findings(rubric, root="/repo"), indent=2, sort_keys=True
    )
    result2 = json.dumps(
        findings.to_shared_findings(rubric, root="/repo"), indent=2, sort_keys=True
    )

    assert result1 == result2


def test_mixed_dimensions_only_emit_fail_and_warn() -> None:
    """Only FAIL and WARN dimensions produce findings; PASS and N/A do not."""
    rubric = {
        "dimensions": [
            (
                "L1 cache efficiency",
                {
                    "tier": "FAIL",
                    "score": 0,
                    "metric": "l1_miss_rate",
                    "value": 9.3,
                    "threshold": 5.0,
                },
            ),
            (
                "Wall-Time Stability",
                {
                    "tier": "PASS",
                    "score": 4,
                    "cv": 1.2,
                },
            ),
            (
                "Algorithmic Scaling",
                {
                    "score": -1,
                    "tier": "N/A",
                    "note": "Insufficient data",
                },
            ),
            (
                "Last-Level Cache",
                {
                    "tier": "WARN",
                    "score": 2,
                    "metric": "ll_miss_rate",
                    "value": 1.5,
                    "threshold": 2.0,
                },
            ),
        ],
        "total": 2,
        "max_possible": 8,
        "baseline_regressions": [],
    }

    result = findings.to_shared_findings(rubric, root="/repo")

    assert len(result) == 2
    severities = {f["severity"] for f in result}
    assert severities == {"high", "medium"}
    metric_names = {f["metric"]["name"] for f in result}
    assert metric_names == {"l1_miss_rate", "ll_miss_rate"}


# --- name-inference extractors (no explicit metric triplet) ---
def test_extract_wall_time_from_cv() -> None:
    rubric = {"dimensions": [("Wall-Time Stability", {"tier": "FAIL", "cv": 7.0})]}
    result = findings.to_shared_findings(rubric, root="/r")
    assert len(result) == 1
    assert result[0]["metric"] == {"name": "wall_time_cv", "value": 7.0, "threshold": 3.0}
    assert result[0]["severity"] == "high"


def test_extract_cpu_emits_top_fn_and_ipc() -> None:
    rubric = {"dimensions": [("CPU Efficiency", {"tier": "WARN", "top_fn_pct": 35.0, "IPC": 0.8})]}
    result = findings.to_shared_findings(rubric, root="/r")
    assert {f["metric"]["name"] for f in result} == {"IPC", "top_fn_pct"}
    assert all(f["severity"] == "medium" for f in result)


def test_extract_l1_cache_from_worst_pct() -> None:
    rubric = {"dimensions": [("L1 Cache Efficiency", {"tier": "FAIL", "worst_pct": 9.0})]}
    result = findings.to_shared_findings(rubric, root="/r")
    assert result[0]["metric"] == {"name": "l1_miss_rate", "value": 9.0, "threshold": 1.0}


def test_extract_ll_cache_from_worst_pct() -> None:
    rubric = {"dimensions": [("Last-Level Cache", {"tier": "FAIL", "worst_pct": 3.0})]}
    result = findings.to_shared_findings(rubric, root="/r")
    assert result[0]["metric"]["name"] == "ll_miss_rate"


def test_extract_branch_from_worst_pct() -> None:
    rubric = {"dimensions": [("Branch Prediction", {"tier": "FAIL", "worst_pct": 4.0})]}
    result = findings.to_shared_findings(rubric, root="/r")
    assert result[0]["metric"]["name"] == "branch_mispred_rate"


def test_extract_algorithmic_only_emits_fail_and_warn_subchecks() -> None:
    rubric = {
        "dimensions": [
            (
                "Algorithmic Scaling",
                {
                    "tier": "FAIL",
                    "sub_checks": {
                        "time_complexity": {"tier": "FAIL", "k": 2.5},
                        "mem_complexity": {"tier": "PASS", "k": 1.0},
                    },
                },
            )
        ]
    }
    result = findings.to_shared_findings(rubric, root="/r")
    assert len(result) == 1
    assert result[0]["metric"]["name"] == "time_complexity"
    assert result[0]["metric"]["value"] == 2.5


def test_extract_memory_emits_peak_and_churn() -> None:
    rubric = {
        "dimensions": [
            ("Memory Profile", {"tier": "WARN", "peak_bytes": 1024.0, "churn_peaks": 5.0})
        ]
    }
    result = findings.to_shared_findings(rubric, root="/r")
    assert {f["metric"]["name"] for f in result} == {"churn_peaks", "peak_bytes"}


def test_unknown_dimension_without_triplet_emits_nothing() -> None:
    rubric = {"dimensions": [("Mystery Dimension", {"tier": "FAIL"})]}
    assert findings.to_shared_findings(rubric, root="/r") == []


def test_suggested_action_uses_prescription_when_source_matches() -> None:
    rubric = {
        "dimensions": [
            ("CPU Efficiency", {"tier": "FAIL", "top_fn_pct": 50.0, "source": "CPU hotspot"})
        ]
    }
    result = findings.to_shared_findings(rubric, root="/r")
    cpu = next(f for f in result if f["metric"]["name"] == "top_fn_pct")
    assert "hotspot" in cpu["suggested_action"].lower()


def test_suggested_action_falls_back_to_investigate() -> None:
    rubric = {"dimensions": [("Memory Profile", {"tier": "FAIL", "peak_bytes": 1.0})]}
    result = findings.to_shared_findings(rubric, root="/r")
    assert result[0]["suggested_action"].startswith("Investigate")
