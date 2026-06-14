"""Guard repo-P's own .repo-audit/accept.json: well-formed + every entry justified."""

from __future__ import annotations

import json
from pathlib import Path

ACCEPT = Path(__file__).resolve().parents[1] / ".repo-audit" / "accept.json"
_STAGES = {"report", "remediation"}
_KINDS = {"finding", "path", "rule"}


def _entries() -> list[dict]:
    data = json.loads(ACCEPT.read_text(encoding="utf-8"))
    assert data.get("version") == 1, "version must be 1"
    accept = data.get("accept")
    assert isinstance(accept, list) and accept, "accept must be a non-empty array"
    return accept


def test_accept_exists():
    assert ACCEPT.is_file(), f"missing {ACCEPT}"


def test_every_entry_well_formed_and_justified():
    for i, e in enumerate(_entries()):
        m = e.get("match")
        assert isinstance(m, dict) and m.get("kind") in _KINDS, f"accept[{i}].match invalid"
        assert isinstance(e.get("reason"), str) and e["reason"].strip(), (
            f"accept[{i}] reason required"
        )
        applies = e.get("applies", ["report", "remediation"])
        assert applies and set(applies) <= _STAGES, f"accept[{i}].applies invalid"
        if m["kind"] == "finding":
            assert all(k in m for k in ("leaf", "path", "symbol", "metric")), (
                f"accept[{i}] finding incomplete"
            )
        elif m["kind"] == "path":
            assert isinstance(m.get("glob"), str) and ".." not in m["glob"], (
                f"accept[{i}] glob invalid"
            )
        else:
            assert "leaf" in m or "metric" in m, f"accept[{i}] rule needs leaf/metric"
