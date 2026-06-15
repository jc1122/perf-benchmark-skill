from __future__ import annotations

import importlib
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
