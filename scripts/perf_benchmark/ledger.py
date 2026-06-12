"""Append-only JSONL run-history ledger with vs-last / vs-best regression checks.

Stdlib-only.  One line per run, each a JSON object.  ``compare`` reads the
ledger and reports any dimension whose tier dropped >= 1 step against the
immediately-preceding entry (vs_last) and against the best-ever entry
(highest ``rubric_total``).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["append_run", "compare"]

_SUCCESS_TIER = "PASS"
TIER_RANK: dict[str, int] = {"FAIL": 0, "WARN": 1, _SUCCESS_TIER: 2}


# ── public API ──────────────────────────────────────────────────────────────


def append_run(ledger_path: Path, summary: dict[str, Any]) -> None:
    """Append one JSON line representing *summary* to *ledger_path*.

    The written line contains:

    * ``timestamp_utc`` – ISO-8601 UTC now
    * ``tier``          – profiling depth (``summary["tier"]``)
    * ``rubric_total``  – ``summary["rubric"]["total"]`` (default 0)
    * ``wall_time_mean`` – ``summary["wall_time_mean"]`` (may be *None*)
    * ``dimensions``    – ``{name: tier}`` mapped from
      ``summary["rubric"]["dimensions"]``
    """
    rubric = summary.get("rubric", {}) or {}
    dimensions_map = rubric.get("dimensions", {}) or {}
    entry: dict[str, Any] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "tier": summary.get("tier", "unknown"),
        "rubric_total": rubric.get("total", 0),
        "wall_time_mean": summary.get("wall_time_mean"),
        "dimensions": {name: dim.get("tier", "N/A") for name, dim in dimensions_map.items()},
    }
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger_path, "a") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")


def _read_ledger_entries(
    ledger_path: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not ledger_path.exists():
        return entries, warnings
    for lineno, raw in enumerate(ledger_path.read_text().splitlines(), start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            entries.append(json.loads(stripped))
        except json.JSONDecodeError:
            warnings.append(f"Skipped corrupt line {lineno} in {ledger_path}")
    return entries, warnings


def _summary_dimension_tiers(summary: dict[str, Any]) -> dict[str, str]:
    rubric = summary.get("rubric", {}) or {}
    dimensions_map = rubric.get("dimensions", {}) or {}
    return {name: dim.get("tier", "N/A") for name, dim in dimensions_map.items()}


def _tier_drop(current_tier: str, reference_tier: str) -> int | None:
    if current_tier not in TIER_RANK or reference_tier not in TIER_RANK:
        return None
    drop = TIER_RANK[reference_tier] - TIER_RANK[current_tier]
    return drop if drop >= 1 else None


def _dimension_regressions(
    current_dims: dict[str, str], reference_dims: dict[str, str], prefix: str
) -> list[dict[str, Any]]:
    regressions: list[dict[str, Any]] = []
    for name, current_tier in current_dims.items():
        reference_tier = reference_dims.get(name)
        if reference_tier is None:
            continue
        drop = _tier_drop(current_tier, reference_tier)
        if drop is None:
            continue
        regressions.append(
            {
                "dimension": name,
                f"{prefix}_tier": reference_tier,
                "current_tier": current_tier,
                "drop": drop,
            }
        )
    return regressions


def compare(ledger_path: Path, summary: dict[str, Any]) -> dict[str, Any]:
    """Return per-dimension tier drops vs the last and best ledger entries.

    Returns a dict with three keys:

    ``vs_last``
        Dimensions whose tier dropped >= 1 step compared to the
        chronologically last (most recent) entry in the ledger.

    ``vs_best``
        Dimensions whose tier dropped >= 1 step compared to the entry with
        the highest ``rubric_total`` (the "best-ever" run).

    ``warnings``
        Strings describing corrupt lines that were skipped (never raises).

    An empty / missing ledger produces empty ``vs_last`` and ``vs_best``
    lists.  Dimensions that only appear in the current summary but not in
    the comparison entry are silently ignored.
    """
    entries, warnings = _read_ledger_entries(ledger_path)
    result: dict[str, Any] = {"vs_last": [], "vs_best": [], "warnings": warnings}
    if not entries:
        return result

    current_dims = _summary_dimension_tiers(summary)

    # ── vs_last ────────────────────────────────────────────────────────
    last = entries[-1]
    last_dims: dict[str, str] = last.get("dimensions", {}) or {}
    result["vs_last"] = _dimension_regressions(current_dims, last_dims, "previous")

    # ── vs_best (max rubric_total) ─────────────────────────────────────
    best = max(entries, key=lambda e: e.get("rubric_total", 0))
    best_dims: dict[str, str] = best.get("dimensions", {}) or {}
    result["vs_best"] = _dimension_regressions(current_dims, best_dims, "best")

    return result
