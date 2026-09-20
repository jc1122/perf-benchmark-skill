"""install-perf.sh deploys one runtime-only perf-benchmark skill dir."""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "bootstrap" / "install-perf.sh"


def run_install(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=str(cwd or REPO),
        capture_output=True,
        text=True,
    )


def test_installs_single_skill_dir_with_runtime_only(tmp_path):
    dest = tmp_path / "skills"
    rc = run_install("--dest", str(dest))
    assert rc.returncode == 0, rc.stderr
    skill = dest / "perf-benchmark"
    assert (skill / "SKILL.md").is_file()
    head = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert "name: perf-benchmark" in head
    # runtime present
    assert (skill / "scripts" / "perf_benchmark_pipeline.py").is_file()
    assert (skill / "scripts" / "perf_benchmark" / "verify_win.py").is_file()
    assert (skill / "scripts" / "perf_benchmark" / "select_candidate.py").is_file()
    assert (skill / "references" / "rubric.md").is_file()
    # second skill retired; dev artifacts excluded
    assert not (dest / "perf-optimization").exists()
    assert not (skill / "tests").exists()
    assert not (skill / "docs").exists()
    assert not (skill / "scripts" / "check_wave_baseline.py").exists()
    assert not (skill / ".repo-audit").exists()


def test_installed_pipeline_runs_from_skill_dir(tmp_path):
    dest = tmp_path / "skills"
    rc = run_install(str(dest))  # positional dest still works
    assert rc.returncode == 0, rc.stderr
    skill = dest / "skills" if False else dest / "perf-benchmark"
    help_proc = subprocess.run(
        [sys.executable, str(skill / "scripts" / "perf_benchmark_pipeline.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert help_proc.returncode == 0
    assert "--tier" in help_proc.stdout
    verify_proc = subprocess.run(
        [sys.executable, str(skill / "scripts" / "perf_benchmark" / "verify_win.py"), "--help"],
        capture_output=True,
        text=True,
    )
    assert verify_proc.returncode == 0
    assert "--objective" in verify_proc.stdout


def test_harness_with_explicit_dest(tmp_path):
    dest = tmp_path / "mine"
    rc = run_install("--harness", "codex", "--dest", str(dest))
    assert rc.returncode == 0, rc.stderr
    assert (dest / "perf-benchmark" / "SKILL.md").is_file()


def test_unknown_harness_fails(tmp_path):
    rc = run_install("--harness", "other")
    assert rc.returncode != 0


def test_no_dest_no_harness_fails(tmp_path):
    rc = run_install()
    assert rc.returncode != 0


def test_install_dest_with_spaces(tmp_path):
    """Skills paths with spaces install intact (PROPOSAL paths-with-spaces case)."""
    dest = tmp_path / "my skills dir"
    rc = run_install("--dest", str(dest))
    assert rc.returncode == 0, rc.stderr
    skill = dest / "perf-benchmark"
    assert (skill / "SKILL.md").is_file()
    assert (skill / "scripts" / "perf_benchmark" / "verify_win.py").is_file()


def test_install_refuses_root_dest(tmp_path):
    """--dest / is refused, never touched."""
    rc = run_install("--dest", "/")
    assert rc.returncode != 0


def test_install_backs_up_prior_skill_dir(tmp_path):
    """An existing install is preserved as a timestamped backup, not deleted."""
    dest = tmp_path / "skills"
    rc = run_install("--dest", str(dest))
    assert rc.returncode == 0, rc.stderr
    marker = dest / "perf-benchmark" / "previous.txt"
    marker.write_text("previous install content\n")
    rc = run_install("--dest", str(dest))
    assert rc.returncode == 0, rc.stderr
    assert (dest / "perf-benchmark" / "SKILL.md").is_file()
    assert not marker.exists()
    backups = list(dest.glob("perf-benchmark.bak.*"))
    assert len(backups) == 1
    assert (backups[0] / "previous.txt").is_file()


def test_install_backs_up_managed_legacy_dir(tmp_path):
    """A legacy perf-optimization dir recognizably ours is moved aside, not deleted."""
    dest = tmp_path / "skills"
    legacy = dest / "perf-optimization"
    legacy.mkdir(parents=True)
    (legacy / "SKILL.md").write_text("---\nname: perf-optimization\n---\n")
    (legacy / "notes.txt").write_text("legacy content\n")
    rc = run_install("--dest", str(dest))
    assert rc.returncode == 0, rc.stderr
    assert (dest / "perf-benchmark" / "SKILL.md").is_file()
    assert not legacy.exists()
    backups = list(dest.glob("perf-optimization.bak.*"))
    assert len(backups) == 1
    assert (backups[0] / "notes.txt").is_file()


def test_install_leaves_unmanaged_legacy_dir_untouched(tmp_path):
    """A perf-optimization dir that is not ours is preserved with a warning."""
    dest = tmp_path / "skills"
    legacy = dest / "perf-optimization"
    legacy.mkdir(parents=True)
    (legacy / "random.txt").write_text("not ours\n")
    rc = run_install("--dest", str(dest))
    assert rc.returncode == 0, rc.stderr
    assert (legacy / "random.txt").is_file()
    assert list(dest.glob("perf-optimization.bak.*")) == []
    assert "untouched" in rc.stderr


def test_install_rollback_restores_prior_on_copy_failure(tmp_path):
    """Copy failure after backup restores the prior install (failure-injection hook)."""
    import os

    dest = tmp_path / "skills"
    rc = run_install("--dest", str(dest))
    assert rc.returncode == 0, rc.stderr
    marker = dest / "perf-benchmark" / "previous.txt"
    marker.write_text("previous install content\n")
    env = dict(os.environ)
    env["PERF_INSTALL_INJECT_COPY_FAILURE"] = "1"
    fail = subprocess.run(
        ["bash", str(SCRIPT), "--dest", str(dest)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env=env,
    )
    assert fail.returncode != 0
    assert (dest / "perf-benchmark" / "previous.txt").is_file()
    assert (dest / "perf-benchmark" / "previous.txt").read_text() == ("previous install content\n")
    assert (dest / "perf-benchmark" / "SKILL.md").is_file()
    assert list(dest.glob("perf-benchmark.bak.*")) == []
