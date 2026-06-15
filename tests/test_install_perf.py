"""install-perf.sh deploys perf-benchmark + perf-optimization into a dest."""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bootstrap" / "install-perf.sh"


def test_installs_both_skill_dirs(tmp_path):
    dest = tmp_path / "skills"
    rc = subprocess.run(
        ["bash", str(SCRIPT), str(dest)], cwd=str(REPO), capture_output=True, text=True
    )
    assert rc.returncode == 0, rc.stderr
    assert (dest / "perf-benchmark" / "SKILL.md").is_file()
    assert (dest / "perf-optimization" / "SKILL.md").is_file()
    head = (dest / "perf-benchmark" / "SKILL.md").read_text(encoding="utf-8")
    assert "name: perf-benchmark" in head
    opt = (dest / "perf-optimization" / "SKILL.md").read_text(encoding="utf-8")
    assert "name: perf-optimization" in opt
