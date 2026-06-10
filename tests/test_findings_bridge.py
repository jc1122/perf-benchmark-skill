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
