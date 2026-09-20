"""Hardening tests for verify_win comparison integrity.

Behavior-based regression tests for the empty-fingerprint / empty-rubric
acceptance hole (parent-reproduced probe), non-finite samples, workload
comparability, suite-evidence labeling, and the per-objective policy.
"""

from __future__ import annotations

import json
import subprocess as sp
import sys
from pathlib import Path

import pytest
from test_verify_win import _WORKLOAD, CLEAN_AFTER, CLEAN_BEFORE, SCRIPT, _ev, run_verify


def _env(**overrides):
    base = {
        "cpu_model": "Test CPU",
        "kernel": "6.1",
        "governor": "performance",
        "smt": "1",
        "python_version": "3.11",
        "load_avg_1m": 0.1,
        "timestamp_utc": "2025-01-01T00:00:00+00:00",
    }
    base.update(overrides)
    return base


def _write_summary(
    path: Path,
    *,
    dims=None,
    p50: float = 2.0,
    env=None,
    workload="default",
    top_extra=None,
    root=None,
) -> Path:
    payload: dict = {
        "rubric": {
            "dimensions": (
                dims if dims is not None else {"Algorithmic Scaling": {"score": 4, "tier": "PASS"}}
            )
        },
        "wall_time_percentiles": {"p50": p50, "p95": p50 * 1.1, "p99": p50 * 1.2},
        "environment": env if env is not None else _env(),
    }
    if workload == "default":
        payload["workload"] = dict(_WORKLOAD)
    elif workload is not None:
        payload["workload"] = workload
    if root is not None:
        payload["root"] = root
    if top_extra:
        payload.update(top_extra)
    path.write_text(json.dumps(payload))
    return path


def _scaling_dims(k: float) -> dict:
    return {
        "Algorithmic Scaling": {
            "score": 4,
            "tier": "PASS",
            "sub_checks": {"complexity_exponent": {"k": k, "tier": "PASS"}},
        },
        "Wall-Time Stability": {"score": 4, "tier": "PASS", "cv": 2.0},
    }


# --------------------------------------------------- empty-metadata rejection


def test_empty_dimensions_is_malformed(tmp_path: Path) -> None:
    """Empty rubric dimensions --> error exit 2, never accept."""
    bad = _write_summary(tmp_path / "bad.json", dims={})
    good = _write_summary(tmp_path / "good.json")
    cp = run_verify(bad, good, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 2
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "error"
    assert verdict["verdict"] != "accept"


def test_probe_hole_empty_fingerprints_and_dims_never_accepts(tmp_path: Path) -> None:
    """Parent-reproduced probe: empty fingerprints + empty dims + suite 0.

    Must not accept: empty dimensions are malformed (exit 2).
    """
    empty_env = {k: "" for k in ("cpu_model", "kernel", "governor", "smt", "python_version")}
    before = _write_summary(tmp_path / "before.json", dims={}, env=empty_env)
    after = _write_summary(tmp_path / "after.json", dims={}, env=empty_env)
    cp = run_verify(before, after, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 2
    assert json.loads(cp.stdout)["verdict"] != "accept"


def test_empty_fingerprint_values_reject(tmp_path: Path) -> None:
    """Present-but-empty fingerprint keys in both runs --> reject fingerprint."""
    empty_env = {k: "" for k in ("cpu_model", "kernel", "governor", "smt", "python_version")}
    before = _write_summary(tmp_path / "before.json", env=empty_env)
    after = _write_summary(tmp_path / "after.json", env=empty_env)
    cp = run_verify(before, after, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 1
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "reject"
    assert "fingerprint" in verdict["reasons"]


def test_one_sided_empty_fingerprint_rejects(tmp_path: Path) -> None:
    """Empty value on one side only --> reject (no empty==equal)."""
    full = _env()
    empty = _env(cpu_model="")
    before = _write_summary(tmp_path / "before.json", env=full)
    after = _write_summary(tmp_path / "after.json", env=empty)
    cp = run_verify(before, after, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 1
    assert "fingerprint" in json.loads(cp.stdout)["reasons"]


def test_missing_fingerprint_key_rejects(tmp_path: Path) -> None:
    """A missing fingerprint key on one side --> reject fingerprint."""
    full = _env()
    partial = _env()
    del partial["governor"]
    before = _write_summary(tmp_path / "before.json", env=full)
    after = _write_summary(tmp_path / "after.json", env=partial)
    cp = run_verify(before, after, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 1
    assert "fingerprint" in json.loads(cp.stdout)["reasons"]


# ------------------------------------------------------- non-finite samples


def test_nan_p50_is_malformed(tmp_path: Path) -> None:
    """NaN p50 --> error exit 2, never accept."""
    before = _write_summary(tmp_path / "before.json")
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "rubric": {"dimensions": {"Algorithmic Scaling": {"score": 4, "tier": "PASS"}}},
                "wall_time_percentiles": {"p50": float("nan"), "p95": 1.0, "p99": 1.0},
                "environment": _env(),
                "workload": dict(_WORKLOAD),
            }
        )
    )
    cp = run_verify(before, bad, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 2
    assert json.loads(cp.stdout)["verdict"] != "accept"


def test_inf_p50_is_malformed(tmp_path: Path) -> None:
    """Inf p50 --> error exit 2, never accept."""
    before = _write_summary(tmp_path / "before.json")
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "rubric": {"dimensions": {"Algorithmic Scaling": {"score": 4, "tier": "PASS"}}},
                "wall_time_percentiles": {"p50": float("inf"), "p95": 1.0, "p99": 1.0},
                "environment": _env(),
                "workload": dict(_WORKLOAD),
            }
        )
    )
    cp = run_verify(before, bad, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 2
    assert json.loads(cp.stdout)["verdict"] != "accept"


# ------------------------------------------------------ workload comparability


def test_missing_workload_rejects(tmp_path: Path) -> None:
    """A summary without a workload block is incomparable --> reject."""
    before = _write_summary(tmp_path / "before.json", workload=None)
    after = _write_summary(tmp_path / "after.json")
    cp = run_verify(before, after, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 1
    assert "workload" in json.loads(cp.stdout)["reasons"]


def test_workload_tier_mismatch_rejects(tmp_path: Path) -> None:
    """Different profiling tiers are incomparable --> reject workload."""
    before = _write_summary(tmp_path / "before.json")
    after_wl = dict(_WORKLOAD)
    after_wl["tier"] = "fast"
    after = _write_summary(tmp_path / "after.json", workload=after_wl)
    cp = run_verify(before, after, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 1
    assert "workload" in json.loads(cp.stdout)["reasons"]


def test_workload_sizes_mismatch_rejects(tmp_path: Path) -> None:
    """Different input sizes are incomparable --> reject workload."""
    before = _write_summary(tmp_path / "before.json")
    after_wl = dict(_WORKLOAD)
    after_wl["sizes"] = [1000, 8000]
    after = _write_summary(tmp_path / "after.json", workload=after_wl)
    cp = run_verify(before, after, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 1
    assert "workload" in json.loads(cp.stdout)["reasons"]


def test_workload_target_mismatch_rejects(tmp_path: Path) -> None:
    """Different benchmark targets are incomparable --> reject workload."""
    before = _write_summary(tmp_path / "before.json")
    after_wl = dict(_WORKLOAD)
    after_wl["target"] = "python3 -m other {SIZE}"
    after = _write_summary(tmp_path / "after.json", workload=after_wl)
    cp = run_verify(before, after, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 1
    assert "workload" in json.loads(cp.stdout)["reasons"]


# ------------------------------------------------------------- suite evidence


def test_suite_evidence_verified_shape(tmp_path: Path) -> None:
    """Attached bound record --> verified with binding echoed in the verdict."""
    evidence = _ev(tmp_path)
    cp = run_verify(
        CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, suite_evidence=evidence, tmp_path=tmp_path
    )

    assert cp.returncode == 0
    verdict = json.loads(cp.stdout)
    assert verdict["functional_verification"] == "verified"
    assert verdict["suite_evidence"]["status"] == "verified"
    assert verdict["suite_evidence"]["exit_code"] == 0
    assert verdict["suite_evidence"]["binding"]["target"] == _WORKLOAD["target"]
    assert verdict["suite_evidence"]["binding"]["root"] == "/tmp/bench"


def test_missing_suite_evidence_file_is_malformed(tmp_path: Path) -> None:
    """A named evidence file that does not exist --> error exit 2."""
    cp = run_verify(
        CLEAN_BEFORE,
        CLEAN_AFTER,
        suite_exit_code=0,
        suite_evidence=tmp_path / "absent.log",
        tmp_path=tmp_path,
    )

    assert cp.returncode == 2
    assert json.loads(cp.stdout)["verdict"] == "error"


# ------------------------------------------------------- objective policy


def test_memory_objective_accepts_configured_win(tmp_path: Path) -> None:
    """Memory peak 1000 -> 900 with --min-win 5 and objective memory --> accept."""
    before = _write_summary(tmp_path / "before.json", top_extra={"tracemalloc_peak_bytes": 1000})
    after = _write_summary(tmp_path / "after.json", top_extra={"tracemalloc_peak_bytes": 900})
    cp = run_verify(
        before,
        after,
        suite_exit_code=0,
        min_win=5.0,
        objective="memory",
        suite_evidence=_ev(tmp_path, root=None),
        tmp_path=tmp_path,
    )

    assert cp.returncode == 0
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "accept"
    assert verdict["objective"] == "memory"
    assert verdict["memory_win_percent"] == pytest.approx(10.0, rel=1e-4)
    assert verdict["objective_delta"] == pytest.approx(10.0, rel=1e-4)


def test_memory_objective_threshold_is_configurable(tmp_path: Path) -> None:
    """Same 10% memory win with --min-win 11 --> reject on objective, not median."""
    before = _write_summary(tmp_path / "before.json", top_extra={"tracemalloc_peak_bytes": 1000})
    after = _write_summary(tmp_path / "after.json", top_extra={"tracemalloc_peak_bytes": 900})
    cp = run_verify(
        before, after, suite_exit_code=0, min_win=11.0, objective="memory", tmp_path=tmp_path
    )

    assert cp.returncode == 1
    verdict = json.loads(cp.stdout)
    assert "objective" in verdict["reasons"]
    assert "median" not in verdict["reasons"]


def test_memory_objective_missing_peaks_rejects_evidence(tmp_path: Path) -> None:
    """No comparable peak data --> reject with evidence reason."""
    before = _write_summary(tmp_path / "before.json")
    after = _write_summary(tmp_path / "after.json")
    cp = run_verify(before, after, suite_exit_code=0, objective="memory", tmp_path=tmp_path)

    assert cp.returncode == 1
    assert "evidence" in json.loads(cp.stdout)["reasons"]


def test_scaling_objective_rejects_worsened_exponent(tmp_path: Path) -> None:
    """Exponent 1.1 -> 1.9 under objective scaling --> reject objective."""
    before = _write_summary(tmp_path / "before.json", dims=_scaling_dims(1.1))
    after = _write_summary(tmp_path / "after.json", dims=_scaling_dims(1.9))
    cp = run_verify(before, after, suite_exit_code=0, objective="scaling", tmp_path=tmp_path)

    assert cp.returncode == 1
    verdict = json.loads(cp.stdout)
    assert "objective" in verdict["reasons"]
    assert verdict["complexity_delta_k"] == pytest.approx(-0.8, rel=1e-4)


def test_scaling_objective_accepts_improved_exponent(tmp_path: Path) -> None:
    """Exponent 1.9 -> 1.1 under objective scaling --> accept (no percent rule)."""
    before = _write_summary(tmp_path / "before.json", dims=_scaling_dims(1.9), p50=2.0)
    after = _write_summary(tmp_path / "after.json", dims=_scaling_dims(1.1), p50=2.0)
    cp = run_verify(
        before,
        after,
        suite_exit_code=0,
        objective="scaling",
        suite_evidence=_ev(tmp_path, root=None),
        tmp_path=tmp_path,
    )

    assert cp.returncode == 0
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "accept"
    assert verdict["complexity_delta_k"] == pytest.approx(0.8, rel=1e-4)


def test_scaling_objective_missing_exponent_rejects_evidence(tmp_path: Path) -> None:
    """No fitted exponent on either side --> reject with evidence reason."""
    before = _write_summary(tmp_path / "before.json")
    after = _write_summary(tmp_path / "after.json")
    cp = run_verify(before, after, suite_exit_code=0, objective="scaling", tmp_path=tmp_path)

    assert cp.returncode == 1
    assert "evidence" in json.loads(cp.stdout)["reasons"]


# ------------------------------------------------------------------ selector


def _run_select(findings: Path, out: Path) -> sp.CompletedProcess[str]:
    script = Path(__file__).resolve().parents[1] / "scripts" / "select_candidate.py"
    return sp.run(
        [sys.executable, str(script), "--findings", str(findings), "--out", str(out)],
        capture_output=True,
        text=True,
    )


def test_selector_rejects_nonfinite_metric(tmp_path: Path) -> None:
    """NaN metric value --> error exit 2, never a candidate."""
    findings = tmp_path / "findings.json"
    findings.write_text(
        json.dumps(
            [
                {
                    "id": "a",
                    "path": "/src/x.py",
                    "severity": "high",
                    "metric": {"name": "l1_miss_rate", "value": float("nan"), "threshold": 5.0},
                }
            ]
        )
    )
    cp = _run_select(findings, tmp_path / "out.json")

    assert cp.returncode == 2
    assert json.loads(cp.stdout)["status"] == "error"


# ------------------------------------------------- item 1: sample support


def _wl_sample(count) -> dict:
    wl = dict(_WORKLOAD)
    wl["sample_count"] = count
    return wl


def test_zero_samples_cannot_prove_win(tmp_path: Path) -> None:
    """Review repro: p50 100 -> 90 with sample_count 0/0 must reject, not accept."""
    before = _write_summary(tmp_path / "before.json", p50=100.0, workload=_wl_sample(0))
    after = _write_summary(tmp_path / "after.json", p50=90.0, workload=_wl_sample(0))
    cp = run_verify(
        before, after, suite_exit_code=0, suite_evidence=_ev(tmp_path), tmp_path=tmp_path
    )

    assert cp.returncode == 1
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "reject"
    assert "evidence" in verdict["reasons"]


def test_single_sample_cannot_prove_win(tmp_path: Path) -> None:
    """sample_count 1/1 must reject, not accept."""
    before = _write_summary(tmp_path / "before.json", p50=100.0, workload=_wl_sample(1))
    after = _write_summary(tmp_path / "after.json", p50=90.0, workload=_wl_sample(1))
    cp = run_verify(
        before, after, suite_exit_code=0, suite_evidence=_ev(tmp_path), tmp_path=tmp_path
    )

    assert cp.returncode == 1
    assert "evidence" in json.loads(cp.stdout)["reasons"]


def test_missing_sample_count_rejects(tmp_path: Path) -> None:
    """Workload without sample_count must reject, not silently pass."""
    wl = dict(_WORKLOAD)
    del wl["sample_count"]
    before = _write_summary(tmp_path / "before.json", p50=100.0, workload=wl)
    after = _write_summary(tmp_path / "after.json", p50=90.0, workload=dict(wl))
    cp = run_verify(
        before, after, suite_exit_code=0, suite_evidence=_ev(tmp_path), tmp_path=tmp_path
    )

    assert cp.returncode == 1
    assert "evidence" in json.loads(cp.stdout)["reasons"]


@pytest.mark.parametrize("count", [2.0, "10", True, None])
def test_untyped_sample_count_rejects(tmp_path: Path, count) -> None:
    """Float, string, bool, or null sample counts must reject."""
    before = _write_summary(tmp_path / "before.json", p50=100.0, workload=_wl_sample(count))
    after = _write_summary(tmp_path / "after.json", p50=90.0, workload=_wl_sample(10))
    cp = run_verify(
        before, after, suite_exit_code=0, suite_evidence=_ev(tmp_path), tmp_path=tmp_path
    )

    assert cp.returncode == 1
    assert "evidence" in json.loads(cp.stdout)["reasons"]


# ------------------------------------------------- item 2: evidence binding


def test_random_json_file_is_not_evidence(tmp_path: Path) -> None:
    """A random JSON file is not a suite record --> error exit 2, never verified."""
    evidence = tmp_path / "random.json"
    evidence.write_text(json.dumps({"true": True}))
    cp = run_verify(
        CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, suite_evidence=evidence, tmp_path=tmp_path
    )

    assert cp.returncode == 2
    assert json.loads(cp.stdout)["verdict"] == "error"


def test_non_json_evidence_is_malformed(tmp_path: Path) -> None:
    """Arbitrary bytes are not evidence --> error exit 2."""
    evidence = tmp_path / "random.log"
    evidence.write_text("all tests passed, trust me\n")
    cp = run_verify(
        CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, suite_evidence=evidence, tmp_path=tmp_path
    )

    assert cp.returncode == 2
    assert json.loads(cp.stdout)["verdict"] == "error"


def test_evidence_exit_code_mismatch_is_malformed(tmp_path: Path) -> None:
    """Record exit_code disagreeing with --suite-exit-code --> error exit 2."""
    evidence = tmp_path / "record.json"
    evidence.write_text(
        json.dumps({"command": "pytest -q", "exit_code": 1, "target": _WORKLOAD["target"]})
    )
    cp = run_verify(
        CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, suite_evidence=evidence, tmp_path=tmp_path
    )

    assert cp.returncode == 2
    assert json.loads(cp.stdout)["verdict"] == "error"


def test_red_record_rejects_on_suite(tmp_path: Path) -> None:
    """A bound record describing a red suite --> reject (suite)."""
    evidence = tmp_path / "record.json"
    evidence.write_text(
        json.dumps(
            {
                "command": "pytest -q",
                "exit_code": 1,
                "failed": 2,
                "status": "fail",
                "target": _WORKLOAD["target"],
                "root": "/tmp/bench",
            }
        )
    )
    cp = run_verify(
        CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=1, suite_evidence=evidence, tmp_path=tmp_path
    )

    assert cp.returncode == 1
    verdict = json.loads(cp.stdout)
    assert "suite" in verdict["reasons"]
    assert verdict["functional_verification"] == "verified"


def test_unbound_record_stays_unverified(tmp_path: Path) -> None:
    """A green record with no binding keys --> advisory, never accept."""
    evidence = tmp_path / "record.json"
    evidence.write_text(
        json.dumps({"command": "pytest -q", "exit_code": 0, "passed": 5, "status": "pass"})
    )
    cp = run_verify(
        CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, suite_evidence=evidence, tmp_path=tmp_path
    )

    assert cp.returncode == 3
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "advisory"
    assert verdict["functional_verification"] == "unverified"


def test_binding_mismatch_rejects_evidence(tmp_path: Path) -> None:
    """A record bound to a different target --> reject (evidence)."""
    evidence = tmp_path / "record.json"
    evidence.write_text(
        json.dumps(
            {
                "command": "pytest -q",
                "exit_code": 0,
                "passed": 5,
                "status": "pass",
                "target": "python3 -m something-else {SIZE}",
            }
        )
    )
    cp = run_verify(
        CLEAN_BEFORE, CLEAN_AFTER, suite_exit_code=0, suite_evidence=evidence, tmp_path=tmp_path
    )

    assert cp.returncode == 1
    assert "evidence" in json.loads(cp.stdout)["reasons"]


def test_suite_command_live_run_verifies(tmp_path: Path) -> None:
    """--suite-command runs the suite and records the observed result."""
    before = _write_summary(tmp_path / "before.json", p50=2.0, root=str(tmp_path))
    after = _write_summary(tmp_path / "after.json", p50=1.8, root=str(tmp_path))
    out = tmp_path / "verdict.json"
    cp = sp.run(
        [
            sys.executable,
            str(SCRIPT),
            "--before",
            str(before),
            "--after",
            str(after),
            "--suite-exit-code",
            "0",
            "--suite-command",
            "exit 0",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )

    assert cp.returncode == 0, cp.stderr + cp.stdout
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "accept"
    assert verdict["functional_verification"] == "verified"
    assert verdict["suite_evidence"]["command"] == "exit 0"


def test_suite_command_exit_mismatch_is_malformed(tmp_path: Path) -> None:
    """Observed suite exit disagreeing with --suite-exit-code --> error exit 2."""
    before = _write_summary(tmp_path / "before.json", p50=2.0, root=str(tmp_path))
    after = _write_summary(tmp_path / "after.json", p50=1.8, root=str(tmp_path))
    out = tmp_path / "verdict.json"
    cp = sp.run(
        [
            sys.executable,
            str(SCRIPT),
            "--before",
            str(before),
            "--after",
            str(after),
            "--suite-exit-code",
            "0",
            "--suite-command",
            "exit 1",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )

    assert cp.returncode == 2
    assert json.loads(cp.stdout)["verdict"] == "error"


def test_evidence_and_command_are_mutually_exclusive(tmp_path: Path) -> None:
    """--suite-evidence with --suite-command --> error exit 2."""
    out = tmp_path / "verdict.json"
    cp = sp.run(
        [
            sys.executable,
            str(SCRIPT),
            "--before",
            str(CLEAN_BEFORE),
            "--after",
            str(CLEAN_AFTER),
            "--suite-exit-code",
            "0",
            "--suite-evidence",
            str(_ev(tmp_path)),
            "--suite-command",
            "exit 0",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )

    assert cp.returncode == 2
    assert json.loads(cp.stdout)["verdict"] == "error"


# ------------------------------------------------- item 4: tier typing


def test_non_string_tier_is_malformed(tmp_path: Path) -> None:
    """An after dim with numeric tier evades nothing: malformed exit 2."""
    dims = {"Algorithmic Scaling": {"score": 4, "tier": 0}}
    before = _write_summary(tmp_path / "before.json")
    after = _write_summary(tmp_path / "after.json", dims=dims)
    cp = run_verify(before, after, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 2
    assert json.loads(cp.stdout)["verdict"] == "error"


def test_missing_tier_is_malformed(tmp_path: Path) -> None:
    """A dim without tier is malformed exit 2, not silent N/A."""
    dims = {"Algorithmic Scaling": {"score": 4}}
    before = _write_summary(tmp_path / "before.json")
    after = _write_summary(tmp_path / "after.json", dims=dims)
    cp = run_verify(before, after, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 2
    assert json.loads(cp.stdout)["verdict"] == "error"


# ------------------------------------------------- item 5: cross-objective


def test_wall_win_with_worsened_exponent_rejects(tmp_path: Path) -> None:
    """p50 win but exponent 1.1 -> 1.9 under wall-time --> reject (objective)."""
    before = _write_summary(tmp_path / "before.json", dims=_scaling_dims(1.1), p50=2.0)
    after = _write_summary(tmp_path / "after.json", dims=_scaling_dims(1.9), p50=1.8)
    cp = run_verify(
        before,
        after,
        suite_exit_code=0,
        min_win=5.0,
        suite_evidence=_ev(tmp_path, root=None),
        tmp_path=tmp_path,
    )

    assert cp.returncode == 1
    assert "objective" in json.loads(cp.stdout)["reasons"]


def test_memory_win_with_wall_collapse_rejects(tmp_path: Path) -> None:
    """Peak 1000 -> 900 but p50 100 -> 150 under memory --> reject (objective)."""
    before = _write_summary(
        tmp_path / "before.json", p50=100.0, top_extra={"tracemalloc_peak_bytes": 1000}
    )
    after = _write_summary(
        tmp_path / "after.json", p50=150.0, top_extra={"tracemalloc_peak_bytes": 900}
    )
    cp = run_verify(
        before,
        after,
        suite_exit_code=0,
        min_win=5.0,
        objective="memory",
        suite_evidence=_ev(tmp_path, root=None),
        tmp_path=tmp_path,
    )

    assert cp.returncode == 1
    assert "objective" in json.loads(cp.stdout)["reasons"]


def test_scaling_equality_rejects(tmp_path: Path) -> None:
    """Exponent 1.5 -> 1.5 is no improvement --> reject (objective)."""
    before = _write_summary(tmp_path / "before.json", dims=_scaling_dims(1.5), p50=2.0)
    after = _write_summary(tmp_path / "after.json", dims=_scaling_dims(1.5), p50=2.0)
    cp = run_verify(
        before,
        after,
        suite_exit_code=0,
        objective="scaling",
        suite_evidence=_ev(tmp_path, root=None),
        tmp_path=tmp_path,
    )

    assert cp.returncode == 1
    assert "objective" in json.loads(cp.stdout)["reasons"]


# ------------------------------------------------- workload strictness


def test_workload_method_inputs_mismatch_rejects(tmp_path: Path) -> None:
    """Differing time_repeats / max_cv / expected_complexity --> reject workload."""
    for key, bad in (("time_repeats", 3), ("max_cv", 10.0), ("expected_complexity", "linear")):
        after_wl = dict(_WORKLOAD)
        after_wl[key] = bad
        before = _write_summary(tmp_path / f"before_{key}.json")
        after = _write_summary(tmp_path / f"after_{key}.json", workload=after_wl)
        cp = run_verify(
            before, after, suite_exit_code=0, suite_evidence=_ev(tmp_path), tmp_path=tmp_path
        )

        assert cp.returncode == 1, key
        assert "workload" in json.loads(cp.stdout)["reasons"], key


def test_sizes_dot_zero_string_rejects(tmp_path: Path) -> None:
    """sizes ['1000.0'] vs [1000] is untyped --> reject workload."""
    after_wl = dict(_WORKLOAD)
    after_wl["sizes"] = ["1000.0", "4000.0"]
    before = _write_summary(tmp_path / "before.json")
    after = _write_summary(tmp_path / "after.json", workload=after_wl)
    cp = run_verify(
        before, after, suite_exit_code=0, suite_evidence=_ev(tmp_path), tmp_path=tmp_path
    )

    assert cp.returncode == 1
    assert "workload" in json.loads(cp.stdout)["reasons"]


@pytest.mark.parametrize("sizes", [[1000.0, 4000.0], ["1000", "4000"]])
def test_sizes_strict_equal_forms_compare(tmp_path: Path, sizes) -> None:
    """Integral floats and digit strings normalize to the same sizes."""
    after_wl = dict(_WORKLOAD)
    after_wl["sizes"] = sizes
    before = _write_summary(tmp_path / "before.json")
    after = _write_summary(tmp_path / "after.json", workload=after_wl)
    cp = run_verify(
        before, after, suite_exit_code=0, suite_evidence=_ev(tmp_path), tmp_path=tmp_path
    )

    assert "workload" not in json.loads(cp.stdout)["reasons"]


# ------------------------------------------------- item 3: ledger drift


def test_ledger_dimension_mismatch_reported(tmp_path: Path) -> None:
    """Ledger entry with an extra dimension surfaces dimension_mismatch."""
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
                    "Ghost Dimension": "PASS",
                },
            }
        )
        + "\n"
    )
    before = _write_summary(tmp_path / "before.json")
    after = _write_summary(tmp_path / "after.json")
    after_payload = json.loads(after.read_text())
    after_payload["wall_time_percentiles"] = {"p50": 1.8, "p95": 2.8, "p99": 3.8}
    after.write_text(json.dumps(after_payload))
    cp = run_verify(
        before,
        after,
        suite_exit_code=0,
        ledger=ledger,
        suite_evidence=_ev(tmp_path, root=None),
        tmp_path=tmp_path,
    )

    verdict = json.loads(cp.stdout)
    assert "dimension_mismatch" in verdict["vs_last"]
    names = {item["dimension"] for item in verdict["vs_last"]["dimension_mismatch"]}
    assert names == {"CPU Efficiency", "Ghost Dimension"}


# ------------------------------------------- final review blockers (2026-09-20)


def test_after_revision_record_omitting_revision_cannot_verify(tmp_path: Path) -> None:
    """After run carries revision but record omits it --> unverified + evidence, never accept."""
    workload = dict(_WORKLOAD)
    workload["revision"] = "abc123"
    before = _write_summary(tmp_path / "before.json", p50=2.0, workload=workload)
    after = _write_summary(tmp_path / "after.json", p50=1.8, workload=workload)
    record = {
        "command": "pytest -q",
        "exit_code": 0,
        "failed": 0,
        "status": "pass",
        "target": _WORKLOAD["target"],
        "root": "/tmp/bench",
    }
    evidence = tmp_path / "suite.json"
    evidence.write_text(json.dumps(record))
    cp = run_verify(before, after, suite_exit_code=0, suite_evidence=evidence, tmp_path=tmp_path)

    assert cp.returncode == 1
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "reject"
    assert "evidence" in verdict["reasons"]
    assert verdict["functional_verification"] == "unverified"


def test_suite_command_rejects_nonexistent_root(tmp_path: Path) -> None:
    """After root that is not a directory --> malformed, never verified."""
    before = _write_summary(tmp_path / "before.json", p50=2.0)
    after = _write_summary(tmp_path / "after.json", p50=1.8, root="/nonexistent-after-root-xyz")
    out = tmp_path / "verdict.json"
    cp = sp.run(
        [
            sys.executable,
            str(SCRIPT),
            "--before",
            str(before),
            "--after",
            str(after),
            "--suite-exit-code",
            "0",
            "--suite-command",
            "exit 0",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )

    assert cp.returncode == 2
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "error"
    assert verdict["functional_verification"] == "unverified"


def test_suite_command_rejects_missing_root(tmp_path: Path) -> None:
    """After summary with no root --> malformed for --suite-command."""
    before = _write_summary(tmp_path / "before.json", p50=2.0)
    after = _write_summary(tmp_path / "after.json", p50=1.8)
    assert "root" not in json.loads(after.read_text())
    out = tmp_path / "verdict.json"
    cp = sp.run(
        [
            sys.executable,
            str(SCRIPT),
            "--before",
            str(before),
            "--after",
            str(after),
            "--suite-exit-code",
            "0",
            "--suite-command",
            "exit 0",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )

    assert cp.returncode == 2
    assert json.loads(cp.stdout)["verdict"] == "error"


def test_suite_command_stale_revision_rejects(tmp_path: Path) -> None:
    """Executed tree revision differing from after revision --> reject, never verified."""
    repo = tmp_path / "repo"
    repo.mkdir()
    sp.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    sp.run(
        ["git", "-C", str(repo), "config", "user.email", "t@t.t"],
        check=True,
        capture_output=True,
    )
    sp.run(
        ["git", "-C", str(repo), "config", "user.name", "t"],
        check=True,
        capture_output=True,
    )
    (repo / "f.txt").write_text("one\n")
    sp.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    sp.run(
        ["git", "-C", str(repo), "commit", "-qm", "one"],
        check=True,
        capture_output=True,
    )
    rev1 = sp.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    workload = dict(_WORKLOAD)
    workload["revision"] = rev1
    before = _write_summary(tmp_path / "before.json", p50=2.0, workload=workload, root=str(repo))
    after = _write_summary(tmp_path / "after.json", p50=1.8, workload=workload, root=str(repo))
    # Move the tree forward so the observed revision is stale vs the claim.
    (repo / "f.txt").write_text("two\n")
    sp.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    sp.run(
        ["git", "-C", str(repo), "commit", "-qm", "two"],
        check=True,
        capture_output=True,
    )
    out = tmp_path / "verdict.json"
    cp = sp.run(
        [
            sys.executable,
            str(SCRIPT),
            "--before",
            str(before),
            "--after",
            str(after),
            "--suite-exit-code",
            "0",
            "--suite-command",
            "exit 0",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )

    assert cp.returncode == 1, cp.stdout + cp.stderr
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "reject"
    assert "evidence" in verdict["reasons"]
    assert verdict["functional_verification"] == "unverified"


@pytest.mark.parametrize("bad_p50", [0, 0.0, -5, -0.5])
def test_nonpositive_p50_is_malformed(tmp_path: Path, bad_p50) -> None:
    """p50 <= 0 on either side --> error exit 2, never accept."""
    before = _write_summary(tmp_path / "before.json", p50=2.0)
    after = _write_summary(tmp_path / "after.json", p50=bad_p50)
    cp = run_verify(before, after, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 2
    verdict = json.loads(cp.stdout)
    assert verdict["verdict"] == "error"
    assert verdict["verdict"] != "accept"


def test_unknown_workload_tier_rejects_symmetrically(tmp_path: Path) -> None:
    """Both tiers BANANA (equal nonsense) --> reject workload, never pass on equality."""
    workload = dict(_WORKLOAD)
    workload["tier"] = "BANANA"
    before = _write_summary(tmp_path / "before.json", workload=workload)
    after = _write_summary(tmp_path / "after.json", workload=workload)
    cp = run_verify(before, after, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 1
    assert "workload" in json.loads(cp.stdout)["reasons"]


@pytest.mark.parametrize(
    "key,bad",
    [
        ("time_repeats", "banana"),
        ("time_repeats", 2.5),
        ("time_repeats", True),
        ("max_cv", "banana"),
        ("max_cv", float("nan")),
        ("expected_complexity", "BANANA"),
        ("expected_complexity", None),
    ],
)
def test_symmetric_invalid_method_inputs_reject(tmp_path: Path, key, bad) -> None:
    """Equal-but-untyped repeats/CV/complexity on both sides --> reject workload."""
    import math as _math

    workload = dict(_WORKLOAD)
    workload[key] = bad
    before = _write_summary(tmp_path / "before.json", workload=workload)
    after = _write_summary(tmp_path / "after.json", workload=workload)
    # NaN needs special JSON handling: json dumps NaN by default; keep it.
    if isinstance(bad, float) and _math.isnan(bad):
        for path in (before, after):
            payload = json.loads(path.read_text())
            payload["workload"][key] = float("nan")
            path.write_text(json.dumps(payload))
    cp = run_verify(before, after, suite_exit_code=0, tmp_path=tmp_path)

    assert cp.returncode == 1, key
    assert "workload" in json.loads(cp.stdout)["reasons"], key
