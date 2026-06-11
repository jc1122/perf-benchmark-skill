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
    result: dict[str, Any] = {"vs_last": [], "vs_best": [], "warnings": []}

    # ── load ledger ────────────────────────────────────────────────────
    entries: list[dict[str, Any]] = []
    if ledger_path.exists():
        for lineno, raw in enumerate(ledger_path.read_text().splitlines(), start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                entries.append(json.loads(stripped))
            except json.JSONDecodeError:
                result["warnings"].append(f"Skipped corrupt line {lineno} in {ledger_path}")

    if not entries:
        return result

    # ── current dimensions as {name: tier} ─────────────────────────────
    rubric = summary.get("rubric", {}) or {}
    dimensions_map = rubric.get("dimensions", {}) or {}
    current_dims: dict[str, str] = {
        name: dim.get("tier", "N/A") for name, dim in dimensions_map.items()
    }

    # ── helpers ────────────────────────────────────────────────────────
    def _drop(cur_t: str, ref_t: str) -> int | None:
        if cur_t not in TIER_RANK or ref_t not in TIER_RANK:
            return None
        d = TIER_RANK[ref_t] - TIER_RANK[cur_t]
        return d if d >= 1 else None

    def _regressions(ref_dims: dict[str, str], prefix: str) -> list[dict[str, Any]]:
        regs: list[dict[str, Any]] = []
        for name, cur_tier in current_dims.items():
            ref_tier = ref_dims.get(name)
            if ref_tier is None:
                continue
            drop = _drop(cur_tier, ref_tier)
            if drop is not None:
                reg = {
                    "dimension": name,
                    f"{prefix}_tier": ref_tier,
                    "current_tier": cur_tier,
                    "drop": drop,
                }
                regs.append(reg)
        return regs

    # ── vs_last ────────────────────────────────────────────────────────
    last = entries[-1]
    last_dims: dict[str, str] = last.get("dimensions", {}) or {}
    result["vs_last"] = _regressions(last_dims, "previous")

    # ── vs_best (max rubric_total) ─────────────────────────────────────
    best = max(entries, key=lambda e: e.get("rubric_total", 0))
    best_dims: dict[str, str] = best.get("dimensions", {}) or {}
    result["vs_best"] = _regressions(best_dims, "best")

    return result
