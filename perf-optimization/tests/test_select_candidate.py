"""Tests for deterministic PERF candidate selection.

Covers:
- mixed severities → highest severity first
- equal severity → higher ratio first
- algorithmic STOP gate → algorithmic wins regardless of severity
- tie → (path, metric.name) order
- empty input → exit 1, status: no_candidates
- malformed JSON → exit 2
- malformed findings shape → exit 2
- stdout and --out payloads are identical/deterministic
- byte-identical across repeated runs
"""

from __future__ import annotations

import json
import subprocess as sp
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "select_candidate.py"


def run_select(findings: Path, out: Path) -> sp.CompletedProcess[str]:
    """Run select_candidate.py and return the completed process."""
    return sp.run(
        [sys.executable, str(SCRIPT), "--findings", str(findings), "--out", str(out)],
        capture_output=True,
        text=True,
    )


# ------------------------------------------------------------------ golden tests


def test_mixed_severities_highest_first(tmp_path: Path) -> None:
    """Highest severity (high > medium > low) wins."""
    out = tmp_path / "out.json"
    cp = run_select(FIXTURES / "mixed_severities.json", out)

    assert cp.returncode == 0
    result = json.loads(cp.stdout)
    assert result["status"] == "ok"
    assert result["candidate"]["severity"] == "high"
    assert result["candidate"]["metric_name"] == "l1_miss_rate"

    # stdout and --out are identical
    out_content = out.read_text().strip()
    assert out_content == cp.stdout.strip()


def test_equal_severity_higher_ratio_first(tmp_path: Path) -> None:
    """Same severity: higher ratio wins."""
    out = tmp_path / "out.json"
    cp = run_select(FIXTURES / "equal_severity.json", out)

    assert cp.returncode == 0
    result = json.loads(cp.stdout)
    assert result["status"] == "ok"
    assert result["candidate"]["severity"] == "high"
    # l1_miss_rate ratio = 9.3/5.0 = 1.86  >  branch_mispred_rate ratio = 4.0/3.0 = 1.33
    assert result["candidate"]["metric_name"] == "l1_miss_rate"
    assert result["candidate"]["ratio"] == pytest.approx(1.86, rel=1e-4)


def test_algorithmic_stop_gate_wins_regardless_of_severity(tmp_path: Path) -> None:
    """Algorithmic STOP gate finding wins even against higher severity."""
    out = tmp_path / "out.json"
    cp = run_select(FIXTURES / "algorithmic_stop_gate.json", out)

    assert cp.returncode == 0
    result = json.loads(cp.stdout)
    assert result["status"] == "ok"
    # complexity_exponent is algorithmic, severity medium, should beat high-severity l1_miss_rate
    assert result["candidate"]["metric_name"] == "complexity_exponent"
    assert result["candidate"]["severity"] == "medium"
    assert result["candidate"]["stop_gate"] is True


def test_tie_broken_by_path_then_metric_name(tmp_path: Path) -> None:
    """Tie: (path, metric_name) lexicographic order."""
    out = tmp_path / "out.json"
    cp = run_select(FIXTURES / "tie_path_metric.json", out)

    assert cp.returncode == 0
    result = json.loads(cp.stdout)
    assert result["status"] == "ok"
    # Three findings all high severity, all ratio=1.0 (5.0/5.0)
    # Sorted by (path, metric_name):
    #   /src/alpha.py, branch_mispred_rate
    #   /src/alpha.py, l1_miss_rate
    #   /src/bravo.py, l1_miss_rate
    # Winner: /src/alpha.py, branch_mispred_rate
    assert result["candidate"]["path"] == "/src/alpha.py"
    assert result["candidate"]["metric_name"] == "branch_mispred_rate"


def test_empty_input_exit_1(tmp_path: Path) -> None:
    """Empty findings array → exit 1, status: no_candidates."""
    out = tmp_path / "out.json"
    cp = run_select(FIXTURES / "empty.json", out)

    assert cp.returncode == 1
    result = json.loads(cp.stdout)
    assert result == {"status": "no_candidates"}

    out_content = out.read_text().strip()
    assert out_content == cp.stdout.strip()


def test_malformed_json_exit_2(tmp_path: Path) -> None:
    """Malformed JSON → exit 2, status: error."""
    out = tmp_path / "out.json"
    cp = run_select(FIXTURES / "malformed_json.json", out)

    assert cp.returncode == 2
    result = json.loads(cp.stdout)
    assert result["status"] == "error"
    assert "Malformed JSON" in result["message"]

    out_content = out.read_text().strip()
    assert out_content == cp.stdout.strip()


def test_malformed_findings_shape_exit_2(tmp_path: Path) -> None:
    """Valid JSON but wrong finding shape → exit 2, status: error."""
    out = tmp_path / "out.json"
    cp = run_select(FIXTURES / "malformed_shape.json", out)

    assert cp.returncode == 2
    result = json.loads(cp.stdout)
    assert result["status"] == "error"
    assert "Malformed findings shape" in result["message"]

    out_content = out.read_text().strip()
    assert out_content == cp.stdout.strip()


def test_malformed_not_a_list_exit_2(tmp_path: Path) -> None:
    """Findings root is not a JSON array → exit 2."""
    non_list = tmp_path / "non_list.json"
    non_list.write_text('{"not": "an array"}')
    out = tmp_path / "out.json"

    cp = sp.run(
        [sys.executable, str(SCRIPT), "--findings", str(non_list), "--out", str(out)],
        capture_output=True,
        text=True,
    )

    assert cp.returncode == 2
    result = json.loads(cp.stdout)
    assert result["status"] == "error"
    assert "must be a JSON array" in result["message"]


def test_missing_file_exit_2(tmp_path: Path) -> None:
    """Non-existent findings file → exit 2."""
    out = tmp_path / "out.json"
    cp = sp.run(
        [
            sys.executable,
            str(SCRIPT),
            "--findings",
            "/nonexistent/path.json",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )

    assert cp.returncode == 2
    result = json.loads(cp.stdout)
    assert result["status"] == "error"


# ----------------------------------------------------------- determinism & shape


def test_byte_identical_across_runs(tmp_path: Path) -> None:
    """Same input → byte-identical output across repeated runs."""
    out1 = tmp_path / "out1.json"
    out2 = tmp_path / "out2.json"

    cp1 = run_select(FIXTURES / "mixed_severities.json", out1)
    cp2 = run_select(FIXTURES / "mixed_severities.json", out2)

    assert cp1.returncode == 0
    assert cp2.returncode == 0
    assert cp1.stdout == cp2.stdout
    assert out1.read_text() == out2.read_text()


def test_output_shape_ok(tmp_path: Path) -> None:
    """The 'ok' output has the exact required shape."""
    out = tmp_path / "out.json"
    cp = run_select(FIXTURES / "mixed_severities.json", out)

    result = json.loads(cp.stdout)
    assert result["status"] == "ok"
    candidate = result["candidate"]
    assert set(candidate.keys()) == {
        "id",
        "path",
        "metric_name",
        "severity",
        "ratio",
        "stop_gate",
    }
    assert isinstance(candidate["id"], str)
    assert isinstance(candidate["path"], str)
    assert isinstance(candidate["metric_name"], str)
    assert isinstance(candidate["severity"], str)
    assert isinstance(candidate["ratio"], float)
    assert isinstance(candidate["stop_gate"], bool)


def test_ratio_with_zero_threshold(tmp_path: Path) -> None:
    """When threshold is 0, ratio is metric.value."""
    findings = tmp_path / "findings.json"
    findings.write_text(
        json.dumps(
            [
                {
                    "id": "x",
                    "path": "/x",
                    "severity": "high",
                    "metric": {"name": "test_metric", "value": 42.0, "threshold": 0.0},
                }
            ]
        )
    )
    out = tmp_path / "out.json"
    cp = run_select(findings, out)

    assert cp.returncode == 0
    result = json.loads(cp.stdout)
    assert result["candidate"]["ratio"] == 42.0


# ---------------------------------------------------- all algorithmic substrings


@pytest.mark.parametrize(
    "metric_name",
    [
        "complexity_exponent",
        "call_amplification",
        "data_reuse",
        "write_amplification",
        "allocation_churn",
        "multiplicative_paths",
        "algorithmic_scaling_check",
    ],
)
def test_each_algorithmic_substring_triggers_stop_gate(
    tmp_path: Path, metric_name: str
) -> None:
    """Each ALGORITHMIC_METRIC_SUBSTRINGS item triggers stop_gate."""
    findings = tmp_path / "findings.json"
    findings.write_text(
        json.dumps(
            [
                {
                    "id": "algo",
                    "path": "/algo",
                    "severity": "low",  # even low should win
                    "metric": {"name": metric_name, "value": 1.0, "threshold": 1.0},
                },
                {
                    "id": "other",
                    "path": "/other",
                    "severity": "high",
                    "metric": {
                        "name": "l1_miss_rate",
                        "value": 9.0,
                        "threshold": 5.0,
                    },
                },
            ]
        )
    )
    out = tmp_path / "out.json"
    cp = run_select(findings, out)

    assert cp.returncode == 0
    result = json.loads(cp.stdout)
    assert result["candidate"]["metric_name"] == metric_name
    assert result["candidate"]["stop_gate"] is True


def test_multiple_algorithmic_findings_sort_by_severity_then_ratio(
    tmp_path: Path,
) -> None:
    """Multiple algorithmic findings: sorted by severity, then ratio."""
    findings = tmp_path / "findings.json"
    findings.write_text(
        json.dumps(
            [
                {
                    "id": "a1",
                    "path": "/a",
                    "severity": "medium",
                    "metric": {
                        "name": "complexity_exponent",
                        "value": 1.8,
                        "threshold": 1.5,
                    },
                },
                {
                    "id": "a2",
                    "path": "/a",
                    "severity": "high",
                    "metric": {
                        "name": "call_amplification",
                        "value": 200.0,
                        "threshold": 100.0,
                    },
                },
            ]
        )
    )
    out = tmp_path / "out.json"
    cp = run_select(findings, out)

    assert cp.returncode == 0
    result = json.loads(cp.stdout)
    # Both algorithmic, high severity beats medium
    assert result["candidate"]["id"] == "a2"
    assert result["candidate"]["severity"] == "high"
    assert result["candidate"]["stop_gate"] is True


# ------------------------------------------------------------- unit-level tests


def test_is_algorithmic_substring_match() -> None:
    """_is_algorithmic matches substrings, not just exact names."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("select_candidate", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod._is_algorithmic("complexity_exponent") is True
    assert mod._is_algorithmic("my_scaling_ratio") is True
    assert mod._is_algorithmic("l1_miss_rate") is False
    assert mod._is_algorithmic("wall_time_cv") is False


def test_compute_ratio_normal() -> None:
    """_compute_ratio returns value/threshold when threshold > 0."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("select_candidate", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod._compute_ratio({"value": 10, "threshold": 5}) == 2.0
    assert mod._compute_ratio({"value": 7.5, "threshold": 2.5}) == 3.0


def test_compute_ratio_zero_threshold() -> None:
    """_compute_ratio returns value when threshold is 0."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("select_candidate", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod._compute_ratio({"value": 42, "threshold": 0}) == 42.0
    assert mod._compute_ratio({"value": 0, "threshold": 0}) == 0.0


def test_select_candidate_single_finding() -> None:
    """Single finding is selected."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("select_candidate", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result = mod.select_candidate(
        [
            {
                "id": "only",
                "path": "/only",
                "severity": "high",
                "metric": {"name": "test", "value": 1.0, "threshold": 1.0},
            }
        ]
    )
    assert result["status"] == "ok"
    assert result["candidate"]["id"] == "only"


def test_select_candidate_empty() -> None:
    """Empty list returns no_candidates."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("select_candidate", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    result = mod.select_candidate([])
    assert result == {"status": "no_candidates"}
