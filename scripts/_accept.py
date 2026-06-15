"""Portable acceptance policy: load + fail-closed validate acceptance entries.

Validates `<repo>/.repo-audit/accept.json`. The audit leaves detect everything by
design; this module is consulted one layer up (the wave's reporting stage and the
MPRR engine's remediation stage) to mark findings acceptable. A malformed policy
is a hard error — never silently "accept nothing" or "accept everything".
See docs/superpowers/specs/2026-06-14-portable-acceptance-safeguard-design.md.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

ACCEPT_RELPATH = Path(".repo-audit") / "accept.json"
_STAGES = frozenset({"report", "remediation"})
_KINDS = frozenset({"finding", "path", "rule"})

# Keys that may appear in a match object and are always string-typed.
_MATCH_KEYS = ("leaf", "path", "symbol", "metric", "glob")
# The four keys that uniquely identify a "finding" kind entry.
_FINDING_KEYS = ("leaf", "path", "symbol", "metric")


class AcceptError(ValueError):
    """Raised on any malformed acceptance policy (fail-closed)."""


@dataclass(frozen=True)
class AcceptEntry:
    """One parsed and validated acceptance entry."""

    kind: str
    fields: dict[str, str]
    reason: str
    applies: frozenset[str]
    expires: str | None
    max_value: float | None = None

    def is_expired(self, today: date | None = None) -> bool:
        """True only for an ISO date in the past; non-date tokens never auto-expire."""
        if not self.expires:
            return False
        try:
            parsed = date.fromisoformat(self.expires)
        except ValueError:
            return False
        return parsed < (today or date.today())

    def exceeds_ceiling(self, finding: dict[str, Any]) -> bool:
        """True when a numeric ceiling is set and the finding's value exceeds it."""
        if self.max_value is None:
            return False
        value = finding.get("value")
        try:
            return value is not None and float(value) > float(self.max_value)
        except (TypeError, ValueError):
            return False


def _require(cond: bool, msg: str) -> None:
    """Raise AcceptError with *msg* when *cond* is falsy (fail-closed guard)."""
    if not cond:
        raise AcceptError(msg)


def _validate_match(kind: str, fields: dict[str, str], index: int) -> None:
    """Validate kind-specific match field requirements (raises AcceptError)."""
    if kind == "finding":
        missing = [k for k in _FINDING_KEYS if k not in fields]
        _require(not missing, f"accept[{index}] finding match missing {missing}")
    elif kind == "path":
        _require("glob" in fields, f"accept[{index}] path match needs 'glob'")
        glob = fields["glob"]
        _require(
            ".." not in glob and not glob.startswith("/"),
            f"accept[{index}] glob must be repo-relative (no '..' or leading '/')",
        )
    else:  # rule
        _require(
            "leaf" in fields or "metric" in fields,
            f"accept[{index}] rule match needs 'leaf' and/or 'metric'",
        )


def _parse_fields(match: dict[str, Any], index: int) -> dict[str, str]:
    """Extract and type-check string match fields from a raw match object."""
    fields: dict[str, str] = {}
    for key in _MATCH_KEYS:
        if key in match:
            value = match[key]
            _require(
                isinstance(value, str),
                f"accept[{index}].match.{key} must be a string",
            )
            fields[key] = value
    return fields


def _parse_applies(raw: Any, index: int) -> frozenset[str]:
    """Validate and return the stage set for an entry (defaults to both stages)."""
    applies_raw = raw.get("applies", ["report", "remediation"])
    _require(
        isinstance(applies_raw, list) and bool(applies_raw),
        f"accept[{index}].applies must be a non-empty array",
    )
    _require(
        all(a in _STAGES for a in applies_raw),
        f"accept[{index}].applies values must be in {sorted(_STAGES)}",
    )
    return frozenset(applies_raw)


def _parse_entry(raw: Any, index: int) -> AcceptEntry:
    """Parse and validate one raw JSON entry into an AcceptEntry."""
    _require(isinstance(raw, dict), f"accept[{index}] must be an object")
    match = raw.get("match")
    _require(isinstance(match, dict), f"accept[{index}].match must be an object")
    kind = match.get("kind")
    _require(
        kind in _KINDS,
        f"accept[{index}].match.kind must be one of {sorted(_KINDS)}",
    )
    reason = raw.get("reason")
    _require(
        isinstance(reason, str) and bool(reason.strip()),
        f"accept[{index}].reason is required",
    )
    applies = _parse_applies(raw, index)
    fields = _parse_fields(match, index)
    _validate_match(kind, fields, index)
    expires = raw.get("expires")
    _require(
        expires is None or isinstance(expires, str),
        f"accept[{index}].expires must be string|null",
    )
    max_value = raw.get("max_value")
    _require(
        max_value is None
        or (isinstance(max_value, (int, float)) and not isinstance(max_value, bool)),
        f"accept[{index}].max_value must be number|null",
    )
    return AcceptEntry(kind, fields, reason, applies, expires, max_value)


def _parse_policy(payload: Any) -> list[AcceptEntry]:
    """Parse a validated acceptance policy JSON object into a list of entries."""
    _require(isinstance(payload, dict), "accept policy must be a JSON object")
    _require(payload.get("version") == 1, "accept policy version must be 1")
    accept = payload.get("accept")
    _require(isinstance(accept, list), "accept policy 'accept' must be an array")
    return [_parse_entry(raw, i) for i, raw in enumerate(accept)]


def _match_finding(fields: dict[str, str], finding: dict[str, Any]) -> bool:
    """All four identity keys must match exactly."""
    return all(str(finding.get(k, "")) == fields[k] for k in _FINDING_KEYS)


def _match_path(fields: dict[str, str], finding: dict[str, Any]) -> bool:
    """Any path associated with the finding must match the glob pattern."""
    glob = fields["glob"]
    paths = [finding.get("path", "")] + list(finding.get("files", []) or [])
    return any(p and fnmatch.fnmatch(p, glob) for p in paths)


def _match_rule(fields: dict[str, str], finding: dict[str, Any]) -> bool:
    """Every specified field must match (AND logic; at least one field is present)."""
    return all(str(finding.get(k, "")) == v for k, v in fields.items())


class AcceptPolicy:
    """A validated set of acceptance entries with stage-scoped matching."""

    def __init__(self, entries: list[AcceptEntry]) -> None:
        """Initialise with a list of pre-validated AcceptEntry objects."""
        self.entries = entries

    def merge(self, other: AcceptPolicy) -> AcceptPolicy:
        """Return a new policy combining entries from both policies."""
        return AcceptPolicy(self.entries + other.entries)

    @staticmethod
    def _entry_matches(entry: AcceptEntry, finding: dict[str, Any]) -> bool:
        """Dispatch to the per-kind match helper."""
        if entry.kind == "finding":
            return _match_finding(entry.fields, finding)
        if entry.kind == "path":
            return _match_path(entry.fields, finding)
        return _match_rule(entry.fields, finding)

    def matches(self, finding: dict[str, Any], stage: str) -> AcceptEntry | None:
        """Return the first entry that accepts *finding* at *stage*, or None."""
        for entry in self.entries:
            if stage in entry.applies and self._entry_matches(entry, finding):
                return entry
        return None

    def _first_hit(
        self, finding: dict[str, Any], stage_entries: list[AcceptEntry]
    ) -> tuple[int, AcceptEntry] | None:
        """Return (index, entry) for the first matching stage entry, or None."""
        for i, entry in enumerate(stage_entries):
            if self._entry_matches(entry, finding):
                return (i, entry)
        return None

    def partition(
        self, findings: list[dict[str, Any]], stage: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        """Split findings into (active, accepted, stale).

        - *active*: findings not matched by any entry.
        - *accepted*: findings matched; carry ``accepted``, ``accept_reason``,
          and ``expired`` annotations.
        - *stale*: stage-scoped entries that matched nothing (sidecar note).
        """
        stage_entries = [e for e in self.entries if stage in e.applies]
        matched: set[int] = set()
        active: list[dict[str, Any]] = []
        accepted: list[dict[str, Any]] = []
        for finding in findings:
            hit = self._first_hit(finding, stage_entries)  # identity-only match
            if hit is None:
                active.append(finding)
                continue
            idx, entry = hit
            matched.add(idx)  # found its target -> never stale
            if entry.is_expired():
                active.append({**finding, "accept_expired": True, "accept_reason": entry.reason})
            elif entry.exceeds_ceiling(finding):
                active.append(
                    {
                        **finding,
                        "ceiling_exceeded": True,
                        "accepted_value": entry.max_value,
                        "actual_value": finding.get("value"),
                    }
                )
            else:
                accepted.append(
                    {
                        **finding,
                        "accepted": True,
                        "accept_reason": entry.reason,
                        "expired": entry.is_expired(),
                    }
                )
        stale = [f"{e.kind}:{e.fields}" for i, e in enumerate(stage_entries) if i not in matched]
        return active, accepted, stale


def _read_json(path: Path) -> Any:
    """Read and parse a JSON file; raise AcceptError on any failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AcceptError(f"{path} is invalid JSON: {exc}") from exc
    except OSError as exc:
        raise AcceptError(f"cannot read {path}: {exc}") from exc


def load_accept(repo: Path, extra: Path | None = None) -> AcceptPolicy:
    """Discover `<repo>/.repo-audit/accept.json` (+ optional --accept file).

    Raises AcceptError on any malformed policy (fail-closed).
    """
    entries: list[AcceptEntry] = []
    in_repo = Path(repo) / ACCEPT_RELPATH
    if in_repo.exists():
        entries.extend(_parse_policy(_read_json(in_repo)))
    if extra is not None:
        entries.extend(_parse_policy(_read_json(Path(extra))))
    return AcceptPolicy(entries)


def identity_of(match: dict[str, str]) -> tuple[str, str, str, str]:
    """The 4-tuple identity of a `finding`-kind match (parity with identity)."""
    return (
        match.get("leaf", ""),
        match.get("path", ""),
        match.get("symbol", ""),
        match.get("metric", ""),
    )


def from_baseline(rows: list[dict[str, str]]) -> AcceptPolicy:
    """Adapt a legacy flat --baseline array into report-stage finding acceptances."""
    entries = [
        AcceptEntry(
            "finding",
            {k: str(r.get(k, "")) for k in _FINDING_KEYS},
            "(legacy --baseline)",
            frozenset({"report"}),
            None,
        )
        for r in rows
    ]
    return AcceptPolicy(entries)
