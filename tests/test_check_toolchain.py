from __future__ import annotations

import importlib
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

mod = importlib.import_module("check_toolchain")


def test_match_when_versions_equal():
    drift = mod.diff_versions({"pytest": "9.0.3"}, {"pytest": "9.0.3"})
    assert drift == []


def test_drift_when_version_differs():
    drift = mod.diff_versions({"pytest": "9.0.3"}, {"pytest": "8.0.0"})
    assert drift == ["pytest: pinned 9.0.3, installed 8.0.0"]


def test_drift_when_missing():
    drift = mod.diff_versions({"pytest": "9.0.3"}, {"pytest": None})
    assert drift == ["pytest: pinned 9.0.3, installed MISSING"]
