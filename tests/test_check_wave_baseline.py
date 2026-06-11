from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from check_wave_baseline import main  # noqa: E402


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
