from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

mod = importlib.import_module("check_runner_pin")


def test_version_ok_equal():
    assert mod.version_ok("0.11.0", "0.11.0") is True


def test_version_ok_greater():
    assert mod.version_ok("0.12.0", "0.11.0") is True


def test_version_ok_lower():
    assert mod.version_ok("0.10.5", "0.11.0") is False


def test_missing_caps_full_set():
    advertised = ("lane-error-gate", "metric-ceiling", "lane-timeout")
    required = ("lane-error-gate", "metric-ceiling", "lane-timeout")
    assert mod.missing_caps(advertised, required) == []


def test_missing_caps_one_missing():
    advertised = ("lane-error-gate", "metric-ceiling")
    required = ("lane-error-gate", "metric-ceiling", "lane-timeout")
    assert mod.missing_caps(advertised, required) == ["lane-timeout"]


_ALL_CAPS = ["lane-error-gate", "metric-ceiling", "lane-timeout"]


def _fake_runner(tmp_path, payload):
    """Write a fake runner that prints *payload* as JSON for --capabilities."""
    script = tmp_path / "fake_runner.py"
    script.write_text(f"import json\nprint(json.dumps({payload!r}))\n", encoding="utf-8")
    return str(script)


def test_main_passes_with_compliant_runner(tmp_path, monkeypatch, capsys):
    runner = _fake_runner(tmp_path, {"version": "0.11.0", "capabilities": _ALL_CAPS})
    monkeypatch.setenv("WAVE_RUNNER", runner)
    assert mod.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "pass"


def test_main_fails_when_wave_runner_unset(monkeypatch, capsys):
    monkeypatch.delenv("WAVE_RUNNER", raising=False)
    assert mod.main() == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "WAVE_RUNNER unset"


def test_main_fails_on_low_version(tmp_path, monkeypatch, capsys):
    runner = _fake_runner(tmp_path, {"version": "0.1.0", "capabilities": _ALL_CAPS})
    monkeypatch.setenv("WAVE_RUNNER", runner)
    assert mod.main() == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "runner pin incoherent"


def test_main_fails_on_missing_capability(tmp_path, monkeypatch, capsys):
    runner = _fake_runner(tmp_path, {"version": "0.11.0", "capabilities": ["lane-error-gate"]})
    monkeypatch.setenv("WAVE_RUNNER", runner)
    assert mod.main() == 1
    assert "metric-ceiling" in json.loads(capsys.readouterr().out)["missing_capabilities"]


def test_main_fails_on_probe_error(tmp_path, monkeypatch, capsys):
    bad = tmp_path / "bad.py"
    bad.write_text("import sys\nsys.exit(3)\n", encoding="utf-8")  # no stdout -> JSON parse fails
    monkeypatch.setenv("WAVE_RUNNER", str(bad))
    assert mod.main() == 1
    assert json.loads(capsys.readouterr().out)["reason"] == "capabilities probe failed"
