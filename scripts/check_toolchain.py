#!/usr/bin/env python3
"""Toolchain-drift gate (#10): assert installed tool versions match the pin
manifest, so findings are never produced by a drifted/missing toolchain."""

from __future__ import annotations

import json
import sys
from importlib import metadata
from pathlib import Path

MANIFEST = Path(__file__).with_name("toolchain_pins.json")


def installed_versions(names) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for name in names:
        try:
            out[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            out[name] = None
    return out


def diff_versions(pins: dict[str, str], installed: dict[str, str | None]) -> list[str]:
    drift = []
    for name, want in sorted(pins.items()):
        got = installed.get(name)
        if got is None:
            drift.append(f"{name}: pinned {want}, installed MISSING")
        elif got != want:
            drift.append(f"{name}: pinned {want}, installed {got}")
    return drift


def main() -> int:
    pins = json.loads(MANIFEST.read_text(encoding="utf-8"))
    drift = diff_versions(pins, installed_versions(pins))
    if drift:
        print(json.dumps({"status": "fail", "drift": drift}, indent=2))
        return 1
    print(json.dumps({"status": "pass", "checked": len(pins)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
