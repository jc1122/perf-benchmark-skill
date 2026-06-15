#!/usr/bin/env python3
"""Fail-closed validator for a `.repo-audit/accept.json` file."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

_acc = importlib.import_module("scripts._accept" if __package__ else "_accept")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an accept.json file.")
    parser.add_argument("--file", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.file.exists():
        print(json.dumps({"status": "fail", "defects": [f"Missing file: {args.file}"]}))
        return 1
    try:
        _acc._parse_policy(json.loads(args.file.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "fail", "defects": [f"invalid JSON: {exc}"]}))
        return 1
    except _acc.AcceptError as exc:
        print(json.dumps({"status": "fail", "defects": [str(exc)]}))
        return 1
    print(json.dumps({"status": "pass"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
