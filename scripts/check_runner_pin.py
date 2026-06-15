#!/usr/bin/env python3
"""Runner pin-coherence gate (#8): assert the tag-pinned WAVE_RUNNER actually
meets the version + capability requirements perf-benchmark depends on, so a
stale pin can never silently run an old runner and pass the wave gate."""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404: fixed argv, shell=False
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REQUIREMENTS = Path(__file__).with_name("runner_requirements.json")


def version_ok(actual: str, minimum: str) -> bool:
    """True when semver ``actual`` >= ``minimum`` (stdlib-only X.Y.Z parse)."""
    return _parse_version(actual) >= _parse_version(minimum)


def _parse_version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.strip().split("."))


def missing_caps(advertised: Iterable[str], required: Iterable[str]) -> list[str]:
    """Required capabilities absent from the advertised set, sorted."""
    have = set(advertised)
    return sorted(cap for cap in required if cap not in have)


def _advertised(runner: str) -> dict[str, Any]:
    proc = subprocess.run(  # nosec B603: fixed argv, shell=False
        [sys.executable, runner, "--capabilities"],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(proc.stdout)


def main() -> int:
    requirements = json.loads(REQUIREMENTS.read_text(encoding="utf-8"))
    runner = os.environ.get("WAVE_RUNNER")
    if not runner:
        print(json.dumps({"status": "fail", "reason": "WAVE_RUNNER unset"}))
        return 1
    try:
        advertised = _advertised(runner)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "reason": "capabilities probe failed",
                    "error": str(exc),
                }
            )
        )
        return 1
    actual_version = str(advertised.get("version", "0.0.0"))
    min_version = str(requirements["min_version"])
    gaps = missing_caps(advertised.get("capabilities", ()), requirements["capabilities"])
    if not version_ok(actual_version, min_version) or gaps:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "reason": "runner pin incoherent",
                    "runner_version": actual_version,
                    "min_version": min_version,
                    "missing_capabilities": gaps,
                },
                indent=2,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": "pass",
                "runner_version": actual_version,
                "min_version": min_version,
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
