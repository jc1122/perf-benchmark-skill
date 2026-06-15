from __future__ import annotations

import importlib
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

mod = importlib.import_module("check_accept_reasons")


def test_specific_reason_passes():
    ok, defect = mod.audit_reason(
        "perflint C0206 in scripts/foo.py: dict-iter residual, CHANGELOG v0.9.0"
    )
    assert ok and defect is None


def test_boilerplate_reason_fails():
    ok, defect = mod.audit_reason("migrated accepted residual — see the repo's frozen ledger")
    assert not ok and "boilerplate" in defect.lower()


def test_too_short_reason_fails():
    ok, defect = mod.audit_reason("accepted")
    assert not ok


def test_reason_without_concrete_token_fails():
    ok, defect = mod.audit_reason("this is a perfectly long sentence with no specifics here")
    assert not ok and "concrete" in defect.lower()
