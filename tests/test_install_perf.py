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


def backup_root(dest: Path) -> Path:
    """Sibling backup root for a skills destination (outside discovery)."""
    return dest.parent / f"{dest.name}-backups"


def skill_manifests(dest: Path) -> list[Path]:
    """All SKILL.md files discoverable directly under a skills destination."""
    return sorted(dest.glob("*/SKILL.md"))


def test_install_backs_up_prior_skill_dir(tmp_path):
    """An existing install is preserved as a timestamped backup outside dest."""
    dest = tmp_path / "skills"
    rc = run_install("--dest", str(dest))
    assert rc.returncode == 0, rc.stderr
    marker = dest / "perf-benchmark" / "previous.txt"
    marker.write_text("previous install content\n")
    rc = run_install("--dest", str(dest))
    assert rc.returncode == 0, rc.stderr
    assert (dest / "perf-benchmark" / "SKILL.md").is_file()
    assert not marker.exists()
    assert list(dest.glob("perf-benchmark.bak.*")) == []
    backups = list(backup_root(dest).glob("perf-benchmark.bak.*"))
    assert len(backups) == 1
    assert (backups[0] / "previous.txt").is_file()
    assert (backups[0] / "SKILL.md").is_file()


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
    assert list(dest.glob("perf-optimization.bak.*")) == []
    backups = list(backup_root(dest).glob("perf-optimization.bak.*"))
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
    assert list(backup_root(dest).glob("perf-benchmark.bak.*")) == []


def test_upgrade_twice_keeps_single_discoverable_skill(tmp_path):
    """Two upgrades: exactly one SKILL.md under dest, priors recoverable outside."""
    import time

    dest = tmp_path / "skills"
    assert run_install("--dest", str(dest)).returncode == 0
    (dest / "perf-benchmark" / "version.txt").write_text("v1\n")
    time.sleep(1.1)
    assert run_install("--dest", str(dest)).returncode == 0
    (dest / "perf-benchmark" / "version.txt").write_text("v2\n")
    time.sleep(1.1)
    rc = run_install("--dest", str(dest))
    assert rc.returncode == 0, rc.stderr
    assert skill_manifests(dest) == [dest / "perf-benchmark" / "SKILL.md"]
    assert list(dest.glob("*.bak.*")) == []
    broot = backup_root(dest)
    assert broot.is_dir()
    versions = set()
    for backup in broot.glob("perf-benchmark.bak.*"):
        assert (backup / "SKILL.md").is_file()
        assert "name: perf-benchmark" in (backup / "SKILL.md").read_text()
        marker = backup / "version.txt"
        if marker.is_file():
            versions.add(marker.read_text())
    assert versions == {"v1\n", "v2\n"}


def test_install_sweeps_old_inplace_backups_outside(tmp_path):
    """Backups left inside dest by older installers are relocated, not deleted."""
    dest = tmp_path / "skills"
    assert run_install("--dest", str(dest)).returncode == 0
    stale = dest / "perf-benchmark.bak.20990101T000000-1"
    stale.mkdir()
    (stale / "SKILL.md").write_text("---\nname: perf-benchmark\n---\n")
    (stale / "previous.txt").write_text("stale content\n")
    rc = run_install("--dest", str(dest))
    assert rc.returncode == 0, rc.stderr
    assert skill_manifests(dest) == [dest / "perf-benchmark" / "SKILL.md"]
    assert not stale.exists()
    moved = list(backup_root(dest).glob("perf-benchmark.bak.*"))
    assert any((b / "previous.txt").is_file() for b in moved)


def test_install_custom_backup_dir(tmp_path):
    """--backup-dir keeps backups in an explicit external dir, dest stays single-skill."""
    dest = tmp_path / "skills"
    ext = tmp_path / "ext-backup"
    assert run_install("--dest", str(dest), "--backup-dir", str(ext)).returncode == 0
    (dest / "perf-benchmark" / "previous.txt").write_text("prev\n")
    rc = run_install("--dest", str(dest), "--backup-dir", str(ext))
    assert rc.returncode == 0, rc.stderr
    assert skill_manifests(dest) == [dest / "perf-benchmark" / "SKILL.md"]
    backups = list(ext.glob("perf-benchmark.bak.*"))
    assert len(backups) == 1
    assert (backups[0] / "previous.txt").is_file()
    assert not backup_root(dest).exists()


def test_install_backup_dir_inside_dest_refused(tmp_path):
    """A backup dir inside the skills destination is refused before any mutation."""
    dest = tmp_path / "skills"
    assert run_install("--dest", str(dest)).returncode == 0
    before = (dest / "perf-benchmark" / "SKILL.md").read_bytes()
    rc = run_install("--dest", str(dest), "--backup-dir", str(dest / "inner"))
    assert rc.returncode != 0
    assert (dest / "perf-benchmark" / "SKILL.md").read_bytes() == before
    assert not (dest / "inner").exists()
    assert skill_manifests(dest) == [dest / "perf-benchmark" / "SKILL.md"]


def test_install_upgrade_dest_with_spaces(tmp_path):
    """Upgrade of a spaced path keeps backups outside and argv-safe."""
    dest = tmp_path / "my skills dir"
    assert run_install("--dest", str(dest)).returncode == 0
    (dest / "perf-benchmark" / "previous.txt").write_text("prev\n")
    rc = run_install("--dest", str(dest))
    assert rc.returncode == 0, rc.stderr
    assert skill_manifests(dest) == [dest / "perf-benchmark" / "SKILL.md"]
    backups = list(backup_root(dest).glob("perf-benchmark.bak.*"))
    assert len(backups) == 1
    assert (backups[0] / "previous.txt").is_file()
