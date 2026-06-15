from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

checker = importlib.import_module("check_wave_baseline")
main = checker.main


def _write_json(path: Path, obj: object) -> Path:
    path.write_text(json.dumps(obj))
    return path


def _payload(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def test_gate_passes_when_active_empty_and_no_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshot = _write_json(tmp_path / "active.json", [])
    accepted = _write_json(tmp_path / "acc.json", {"accepted": [{"leaf": "A"}], "stale": []})
    code = main(["--snapshot", str(snapshot), "--accepted", str(accepted)])
    payload = _payload(capsys)
    assert code == 0
    assert payload["status"] == "pass"
    assert payload["accepted"] == 1
    assert payload["active"] == 0


def test_gate_fails_on_active_findings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    snapshot = _write_json(
        tmp_path / "active.json",
        [{"leaf": "B", "path": "q", "symbol": "t", "metric": "n"}],
    )
    code = main(["--snapshot", str(snapshot)])
    payload = _payload(capsys)
    assert code == 1
    assert payload["status"] == "fail"
    assert payload["new_findings"][0]["leaf"] == "B"


def test_gate_fails_on_stale_acceptances(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshot = _write_json(tmp_path / "active.json", [])
    accepted = _write_json(tmp_path / "acc.json", {"accepted": [], "stale": ["finding:{leaf=A}"]})
    code = main(["--snapshot", str(snapshot), "--accepted", str(accepted)])
    payload = _payload(capsys)
    assert code == 1
    assert payload["status"] == "fail"
    assert payload["stale_acceptances"]


def test_fail_when_a_lane_errored_even_if_active_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshot = _write_json(tmp_path / "active.json", [])
    accepted = _write_json(tmp_path / "acc.json", {"accepted": [], "stale": []})
    summary = _write_json(
        tmp_path / "summary.json",
        {"complexity": {"status": "ok"}, "security": {"status": "error"}},
    )
    code = main(
        [
            "--snapshot",
            str(snapshot),
            "--accepted",
            str(accepted),
            "--summary",
            str(summary),
        ]
    )
    payload = _payload(capsys)
    assert code == 1
    assert payload["status"] == "fail"
    assert payload["reason"] == "lane_error"
    assert payload["errored_lanes"] == ["security"]
    assert payload["runner_exit"] == 0


def test_pass_when_all_lanes_ok_and_active_empty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshot = _write_json(tmp_path / "active.json", [])
    accepted = _write_json(tmp_path / "acc.json", {"accepted": [], "stale": []})
    summary = _write_json(
        tmp_path / "summary.json",
        {"complexity": {"status": "ok"}, "security": {"status": "ok"}},
    )
    code = main(
        [
            "--snapshot",
            str(snapshot),
            "--accepted",
            str(accepted),
            "--summary",
            str(summary),
        ]
    )
    payload = _payload(capsys)
    assert code == 0
    assert payload["status"] == "pass"
    assert payload["active"] == 0


def test_live_wave_forwards_anchor_and_configs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner = tmp_path / "runner.py"
    runner.write_text(
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n"
        "out = Path(sys.argv[sys.argv.index('--out-dir') + 1])\n"
        "out.mkdir(parents=True, exist_ok=True)\n"
        "(out / 'wave_findings.json').write_text('[]', encoding='utf-8')\n"
        "(out / 'wave_findings.accepted.json').write_text("
        "json.dumps({'accepted': [], 'stale': []}), encoding='utf-8')\n"
        "(out / 'wave_summary.json').write_text("
        "json.dumps({'complexity': {'status': 'ok'}}), encoding='utf-8')\n"
        "(out / 'argv.json').write_text(json.dumps(sys.argv[1:]), encoding='utf-8')\n",
        encoding="utf-8",
    )
    anchor = tmp_path / "wave_anchor.txt"
    anchor.write_text("anchor-sha\n", encoding="utf-8")
    security_config = tmp_path / "security_audit_config.json"
    security_config.write_text("{}\n", encoding="utf-8")
    hotspot_config = tmp_path / "hotspot_audit_config.json"
    hotspot_config.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(checker, "REPO", repo)
    monkeypatch.setattr(checker, "WAVE_ANCHOR", anchor)
    monkeypatch.setattr(checker, "SECURITY_CONFIG", security_config)
    monkeypatch.setattr(checker, "HOTSPOT_CONFIG", hotspot_config)
    monkeypatch.setenv("WAVE_RUNNER", str(runner))
    monkeypatch.setenv("SKILLS_ROOT", str(tmp_path / "skills"))
    monkeypatch.delenv("WAVE_REV", raising=False)
    monkeypatch.delenv("SECURITY_CONFIG", raising=False)
    monkeypatch.delenv("HOTSPOT_CONFIG", raising=False)

    code = main([])
    payload = _payload(capsys)
    argv = json.loads((repo / ".wave_out" / "argv.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "pass"
    assert argv[argv.index("--rev") + 1] == "anchor-sha"
    assert argv[argv.index("--security-config") + 1] == str(security_config)
    assert argv[argv.index("--hotspot-config") + 1] == str(hotspot_config)
