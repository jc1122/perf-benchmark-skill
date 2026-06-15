#!/usr/bin/env python3
"""Reason-quality gate for `.repo-audit/accept.json` (#3): every accept reason
must be specific and non-boilerplate, not just structurally valid."""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from pathlib import Path

_acc = importlib.import_module("scripts._accept" if __package__ else "_accept")

MIN_LEN = 24
_BOILERPLATE = (
    "migrated accepted residual",
    "see the repo's frozen ledger",
    "accepted residual",
    "wip",
    "tbd",
    "n/a",
    "todo",
)
_CONCRETE = re.compile(
    r"(\b[\w./-]+\.py\b)"  # a path
    r"|([A-Z]\d{2,})"  # a rule/metric code (C0206, B603)
    r"|(\b\d{4}-\d{2}-\d{2}\b)"  # an ISO date
    r"|(\bv\d+\.\d+)"  # a version tag
)


def audit_reason(reason: str) -> tuple[bool, str | None]:
    text = (reason or "").strip()
    if len(text) < MIN_LEN:
        return False, f"reason too short (<{MIN_LEN} chars): {reason!r}"
    low = text.lower()
    if any(b in low for b in _BOILERPLATE) and not _CONCRETE.search(text):
        return False, f"reason is boilerplate: {reason!r}"
    if not _CONCRETE.search(text):
        return False, f"reason lacks a concrete token (path/code/date/tag): {reason!r}"
    return True, None


def _parse_args(argv=None):
    ap = argparse.ArgumentParser(description="Audit accept.json reason quality.")
    ap.add_argument("--file", type=Path, default=Path(".repo-audit") / "accept.json")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    if not args.file.exists():
        print(json.dumps({"status": "pass", "note": "no accept.json"}))
        return 0
    payload = json.loads(args.file.read_text(encoding="utf-8"))
    entries = _acc._parse_policy(payload)  # reuse structural validation
    defects = []
    for i, entry in enumerate(entries):
        ok, defect = audit_reason(entry.reason)
        if not ok:
            defects.append(f"accept[{i}]: {defect}")
    if defects:
        print(json.dumps({"status": "fail", "defects": defects}, indent=2))
        return 1
    print(json.dumps({"status": "pass", "count": len(entries)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
