#!/usr/bin/env python3
"""Binary coverage-gap convergence gate (Phase-2 B4 graduation).

Runs this repo's suite under coverage, feeds the JSON report to the coverage-gap
leaf, and ratchets findings against scripts/coverage_gap_baseline.json. Returns a
real non-zero exit on any finding outside the baseline (not piped -- L4). The leaf
path comes from $LEAF (CI clones it) or the local installed skills dir.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404: local trusted coverage + leaf invocation
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "scripts" / "coverage_gap_baseline.json"
_LEAF_REL = ".claude/skills/coverage-gap-audit/scripts/coverage_gap_audit.py"
_DEFAULT_LEAF = Path.home() / _LEAF_REL


def _leaf() -> str:
    return os.environ.get("LEAF") or str(_DEFAULT_LEAF)


def _write_rc(out_dir: Path) -> Path:
    rc = out_dir / ".coveragerc"
    rc.write_text(
        f"[run]\nparallel = true\ndata_file = {out_dir / '.coverage'}\n"
        "[report]\nignore_errors = true\n",
        encoding="utf-8",
    )
    return rc


def _coverage_env(out_dir: Path, rc: Path, capture: bool) -> dict[str, str]:
    env = dict(os.environ)
    if capture:
        hook = out_dir / "hook"
        hook.mkdir(exist_ok=True)
        (hook / "sitecustomize.py").write_text(
            "import coverage\ncoverage.process_startup()\n", encoding="utf-8"
        )
        env["PYTHONPATH"] = os.pathsep.join([str(hook), env.get("PYTHONPATH", "")])
        env["COVERAGE_PROCESS_START"] = str(rc)
    return env


def _run(cmd: Sequence[str], env: dict[str, str] | None = None) -> None:
    subprocess.run(  # nosec B603
        cmd, cwd=ROOT, check=False, capture_output=True, env=env
    )


def generate_coverage(out_dir: Path, suites: list[str], capture: bool) -> Path:
    rc = _write_rc(out_dir)
    env = _coverage_env(out_dir, rc, capture)
    cov = (sys.executable, "-m", "coverage")
    run = (*cov, "run", f"--rcfile={rc}", "-m", "pytest", *suites)
    _run((*run, "-q", "-p", "no:cacheprovider"), env=env)
    _run((*cov, "combine", f"--rcfile={rc}"))
    cov_json = out_dir / "coverage.json"
    data = out_dir / ".coverage"
    _run((*cov, "json", f"--rcfile={rc}", f"--data-file={data}", "-o", str(cov_json)))
    return cov_json


def run_leaf(cov_json: Path, out_dir: Path, prefixes: list[str]) -> list[dict]:
    prefix_args = tuple(a for p in prefixes for a in ("--source-prefix", p))
    cmd = (
        sys.executable,
        _leaf(),
        "--root",
        str(ROOT),
        "--out-dir",
        str(out_dir / "leaf"),
        "--coverage-json",
        str(cov_json),
        *prefix_args,
    )
    _run(cmd)
    findings_path = out_dir / "leaf" / "coverage-gap_findings.json"
    raw = json.loads(findings_path.read_text(encoding="utf-8"))
    rows = ({"path": f["path"], "metric": f["metric"]["name"]} for f in raw)
    return sorted(rows, key=lambda d: (d["path"], d["metric"]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Binary coverage-gap convergence gate.")
    parser.add_argument(
        "--suite",
        action="append",
        dest="suites",
        default=[],
        help="Pytest suite dir/file (repeatable).",
    )
    parser.add_argument(
        "--source-prefix",
        action="append",
        dest="prefixes",
        default=[],
        help="Production source prefix for the leaf (repeatable).",
    )
    parser.add_argument(
        "--subprocess-capture",
        action="store_true",
        help="Capture subprocess coverage (for subprocess-tested CLIs).",
    )
    return parser


def _load_baseline() -> list[dict]:
    if BASELINE.exists():
        return json.loads(BASELINE.read_text(encoding="utf-8"))
    return []


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    baseline = _load_baseline()
    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        suites = args.suites or ["tests"]
        cov_json = generate_coverage(out_dir, suites, args.subprocess_capture)
        current = run_leaf(cov_json, out_dir, args.prefixes or ["scripts"])
    new = [f for f in current if f not in baseline]
    n_base = len(baseline)
    if new:
        print(json.dumps({"status": "fail", "new_findings": new, "baseline": n_base}))
        return 1
    print(json.dumps({"status": "pass", "count": len(current), "baseline": n_base}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
