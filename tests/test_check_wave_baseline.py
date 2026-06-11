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


def _findings_payload(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(capsys.readouterr().out.strip())


def _identity_as_lists(finding: dict[str, str]) -> list[list[str]]:
    return [list(item) for item in sorted(finding.items())]


def test_gate_passes_when_current_equals_baseline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline = [
        {"leaf": "A", "path": "p", "symbol": "s", "metric": "m"},
    ]
    snapshot = _write_json(tmp_path / "snapshot.json", baseline)
    baseline_path = _write_json(tmp_path / "baseline.json", baseline)

    code = main(["--snapshot", str(snapshot), "--baseline", str(baseline_path)])
    payload = _findings_payload(capsys)

    assert code == 0
    assert payload["status"] == "pass"
    assert payload["count"] == 1
    assert payload["baseline"] == 1


def test_gate_fails_when_new_findings_exist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline = [{"leaf": "A", "path": "p", "symbol": "s", "metric": "m"}]
    current = [
        {"leaf": "A", "path": "p", "symbol": "s", "metric": "m"},
        {"leaf": "B", "path": "q", "symbol": "t", "metric": "n"},
    ]

    snapshot = _write_json(tmp_path / "snapshot.json", current)
    baseline_path = _write_json(tmp_path / "baseline.json", baseline)

    code = main(["--snapshot", str(snapshot), "--baseline", str(baseline_path)])
    payload = _findings_payload(capsys)
    expected_new = [_identity_as_lists({"leaf": "B", "path": "q", "symbol": "t", "metric": "n"})]

    assert code == 1
    assert payload["status"] == "fail"
    assert payload["new_findings"] == expected_new


def test_gate_fails_when_stale_baseline_findings_exist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline = [
        {"leaf": "A", "path": "p", "symbol": "s", "metric": "m"},
        {"leaf": "B", "path": "q", "symbol": "t", "metric": "n"},
    ]
    current = [{"leaf": "A", "path": "p", "symbol": "s", "metric": "m"}]

    snapshot = _write_json(tmp_path / "snapshot.json", current)
    baseline_path = _write_json(tmp_path / "baseline.json", baseline)

    code = main(["--snapshot", str(snapshot), "--baseline", str(baseline_path)])
    payload = _findings_payload(capsys)
    expected_stale = [_identity_as_lists({"leaf": "B", "path": "q", "symbol": "t", "metric": "n"})]

    assert code == 1
    assert payload["status"] == "fail"
    assert payload["stale_baseline"] == expected_stale
    assert payload["message"] == "ratchet: remove them from wave_baseline.json in the same commit"


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
        "(out / 'argv.json').write_text(json.dumps(sys.argv[1:]), encoding='utf-8')\n",
        encoding="utf-8",
    )
    baseline_path = _write_json(tmp_path / "baseline.json", [])
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

    code = main(["--baseline", str(baseline_path)])
    payload = _findings_payload(capsys)
    argv = json.loads((repo / ".wave_out" / "argv.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "pass"
    assert argv[argv.index("--rev") + 1] == "anchor-sha"
    assert argv[argv.index("--security-config") + 1] == str(security_config)
    assert argv[argv.index("--hotspot-config") + 1] == str(hotspot_config)
