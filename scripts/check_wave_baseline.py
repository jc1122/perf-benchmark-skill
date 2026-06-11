#!/usr/bin/env python3
"""Convergence gate: diagnosis wave on this repo, equality-ratcheted against wave_baseline.json."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE = Path(__file__).with_name("wave_baseline.json")
WAVE_ANCHOR = Path(__file__).with_name("wave_anchor.txt")
SECURITY_CONFIG = Path(__file__).with_name("security_audit_config.json")
HOTSPOT_CONFIG = Path(__file__).with_name("hotspot_audit_config.json")


def identities(fs: list[dict[str, str]]) -> set[tuple[tuple[str, str], ...]]:
    return {tuple(sorted(item.items())) for item in fs}


def _optional_config_arg(env_name: str, default_path: Path, flag: str) -> list[str]:
    value = os.environ.get(env_name)
    if not value and default_path.exists():
        value = str(default_path)
    return [flag, value] if value else []


def _wave_command(runner: str, out: Path) -> list[str]:
    cmd = [
        sys.executable,
        runner,
        "--repo",
        str(REPO),
        "--out-dir",
        str(out),
        "--skills-root",
        os.environ.get("SKILLS_ROOT", str(Path.home() / ".claude/skills")),
        "--source-prefix",
        "scripts",
        "--source-prefix",
        "perf-optimization/scripts",
    ]
    rev = os.environ.get("WAVE_REV")
    if not rev and WAVE_ANCHOR.exists():
        rev = WAVE_ANCHOR.read_text(encoding="utf-8").strip()
    if rev:
        cmd += ["--rev", rev]
    cmd += _optional_config_arg("SECURITY_CONFIG", SECURITY_CONFIG, "--security-config")
    cmd += _optional_config_arg("HOTSPOT_CONFIG", HOTSPOT_CONFIG, "--hotspot-config")
    return cmd


def _run_wave() -> list[dict[str, str]]:
    runner = os.environ.get(
        "WAVE_RUNNER",
        str(
            Path.home()
            / ".claude/skills/repo-audit-refactor-optimize/scripts/run_diagnosis_wave.py"
        ),
    )
    out = REPO / ".wave_out"
    subprocess.run(_wave_command(runner, out), check=False)
    return json.loads((out / "wave_findings.json").read_text())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot")
    parser.add_argument("--baseline")
    args = parser.parse_args(argv)

    current = json.loads(Path(args.snapshot).read_text()) if args.snapshot else _run_wave()

    baseline = json.loads(Path(args.baseline or BASELINE).read_text())
    current_identities = identities(current)
    baseline_identities = identities(baseline)
    new_findings = current_identities - baseline_identities
    stale_baseline = baseline_identities - current_identities
    if new_findings:
        print(
            json.dumps(
                {"status": "fail", "new_findings": sorted(map(list, new_findings))},
                indent=2,
            )
        )
        return 1
    if stale_baseline:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "stale_baseline": sorted(map(list, stale_baseline)),
                    "message": f"ratchet: remove them from {BASELINE.name} in the same commit",
                },
                indent=2,
            )
        )
        return 1
    print(
        json.dumps(
            {
                "status": "pass",
                "count": len(current_identities),
                "baseline": len(baseline_identities),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
