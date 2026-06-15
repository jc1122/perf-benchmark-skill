"""Tests for the binary coverage-gap convergence gate (B4)."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

g = importlib.import_module("check_coverage_gap")


def test_build_parser_defaults():
    ns = g.build_parser().parse_args([])
    assert ns.suites == []
    assert ns.prefixes == []
    assert ns.subprocess_capture is False


def test_build_parser_repeatable_and_capture():
    ns = g.build_parser().parse_args(
        [
            "--suite",
            "tests",
            "--suite",
            "x/tests",
            "--source-prefix",
            "scripts",
            "--source-prefix",
            "y",
            "--subprocess-capture",
        ]
    )
    assert ns.suites == ["tests", "x/tests"]
    assert ns.prefixes == ["scripts", "y"]
    assert ns.subprocess_capture is True


def test_leaf_env_override(monkeypatch):
    monkeypatch.setenv("LEAF", "/custom/leaf.py")
    assert g._leaf() == "/custom/leaf.py"


def test_leaf_default(monkeypatch):
    monkeypatch.delenv("LEAF", raising=False)
    assert g._leaf().endswith("coverage-gap-audit/scripts/coverage_gap_audit.py")


def test_write_rc_contents(tmp_path):
    rc = g._write_rc(tmp_path)
    txt = rc.read_text(encoding="utf-8")
    assert "parallel = true" in txt
    assert "ignore_errors = true" in txt


def test_coverage_env_capture_off(tmp_path):
    rc = g._write_rc(tmp_path)
    env = g._coverage_env(tmp_path, rc, capture=False)
    assert "COVERAGE_PROCESS_START" not in env


def test_coverage_env_capture_on_sets_hook(tmp_path):
    rc = g._write_rc(tmp_path)
    env = g._coverage_env(tmp_path, rc, capture=True)
    assert env["COVERAGE_PROCESS_START"] == str(rc)
    assert str(tmp_path / "hook") in env["PYTHONPATH"]
    assert (tmp_path / "hook" / "sitecustomize.py").is_file()


def test_main_passes_when_no_new_findings(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "BASELINE", tmp_path / "absent.json")
    monkeypatch.setattr(g, "generate_coverage", lambda out, suites, capture: tmp_path / "cov.json")
    monkeypatch.setattr(g, "run_leaf", lambda cov, out, prefixes: [])
    assert g.main(["--suite", "tests", "--source-prefix", "scripts"]) == 0


def test_main_fails_on_new_finding(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "BASELINE", tmp_path / "absent.json")
    monkeypatch.setattr(g, "generate_coverage", lambda out, suites, capture: tmp_path / "cov.json")
    monkeypatch.setattr(
        g,
        "run_leaf",
        lambda cov, out, prefixes: [{"path": "scripts/x.py", "metric": "file_coverage_percent"}],
    )
    assert g.main(["--suite", "tests"]) == 1


def test_main_accepts_baselined_finding(monkeypatch, tmp_path):
    base = tmp_path / "baseline.json"
    base.write_text(
        json.dumps([{"path": "scripts/x.py", "metric": "file_coverage_percent"}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(g, "BASELINE", base)
    monkeypatch.setattr(g, "generate_coverage", lambda out, suites, capture: tmp_path / "cov.json")
    monkeypatch.setattr(
        g,
        "run_leaf",
        lambda cov, out, prefixes: [{"path": "scripts/x.py", "metric": "file_coverage_percent"}],
    )
    assert g.main([]) == 0
