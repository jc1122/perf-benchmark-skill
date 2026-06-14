#!/usr/bin/env python3
"""Convergence gate: diagnosis wave on this repo.

The wave auto-discovers `.repo-audit/accept.json` and suppresses accepted findings
into `wave_findings.accepted.json`, leaving only un-accepted findings in
`wave_findings.json`. Converged iff the active set is empty and no accepted entry is
stale (Option A — trust the wave's report/accept partition).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WAVE_ANCHOR = Path(__file__).with_name("wave_anchor.txt")
SECURITY_CONFIG = Path(__file__).with_name("security_audit_config.json")
HOTSPOT_CONFIG = Path(__file__).with_name("hotspot_audit_config.json")


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


def _run_wave() -> Path:
    runner = os.environ.get(
        "WAVE_RUNNER",
        str(
            Path.home()
            / ".claude/skills/repo-audit-refactor-optimize/scripts/run_diagnosis_wave.py"
        ),
    )
    out = REPO / ".wave_out"
    subprocess.run(_wave_command(runner, out), check=False)
    return out


def _load_sidecar(out: Path) -> tuple[list, list]:
    sidecar = out / "wave_findings.accepted.json"
    if sidecar.exists():
        data = json.loads(sidecar.read_text())
        return data.get("accepted", []), data.get("stale", [])
    return [], []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", help="Active findings JSON (testing only)")
    parser.add_argument("--accepted", help="Accepted sidecar JSON (testing only)")
    args = parser.parse_args(argv)

    if args.snapshot:
        active = json.loads(Path(args.snapshot).read_text())
        if args.accepted:
            data = json.loads(Path(args.accepted).read_text())
            accepted, stale = data.get("accepted", []), data.get("stale", [])
        else:
            accepted, stale = [], []
    else:
        out = _run_wave()
        active = json.loads((out / "wave_findings.json").read_text())
        accepted, stale = _load_sidecar(out)

    if active:
        print(json.dumps({"status": "fail", "new_findings": active}, indent=2))
        return 1
    if stale:
        print(json.dumps({"status": "fail", "stale_acceptances": stale}, indent=2))
        return 1
    print(json.dumps({"status": "pass", "accepted": len(accepted), "active": 0}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
