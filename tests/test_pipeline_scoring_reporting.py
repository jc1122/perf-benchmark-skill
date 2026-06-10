from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from tests.helpers import REPO_ROOT, make_args, pipeline


def test_score_rubric_reports_baseline_regressions_for_any_dimension(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "rubric": {
                    "dimensions": {
                        "CPU Efficiency": {"tier": "PASS", "score": 4},
                        "Memory Profile": {"tier": "PASS", "score": 4},
                    }
                }
            }
        )
    )
    args = make_args(tmp_path, baseline=str(baseline_path))
    tier234 = {
        "callgrind": {
            "functions": [{"Ir": 80, "file": "src/mod.c", "line": 1, "function": "hot"}],
            "total_ir": 100,
        }
    }

    rubric = pipeline.score_rubric({}, tier234, args)

    assert rubric["baseline_regressions"] == [
        {
            "dimension": "CPU Efficiency",
            "baseline_tier": "PASS",
            "current_tier": "FAIL",
            "drop": 2,
        }
    ]


def test_score_algorithmic_scaling_uses_time_usage_by_size_when_pytest_data_missing(
    tmp_path: Path,
) -> None:
    args = make_args(tmp_path, binary="/bin/true", sizes=[10, 100], expected_complexity="linear")
    tier1 = {
        "time_usage_by_size": {
            10: [{"wall_seconds": 0.01}],
            100: [{"wall_seconds": 0.1}],
        }
    }

    result = pipeline.score_algorithmic_scaling(tier1, {}, args)

    assert result["tier"] == "N/A"
    assert result["sub_checks"]["complexity_exponent"]["k"] == 1.0


def test_fit_exponent_ignores_non_positive_sizes() -> None:
    assert pipeline._fit_exponent([0, 100, 1000], [1.0, 10.0, 100.0]) == 1.0


def test_score_algorithmic_scaling_is_na_when_required_subchecks_are_missing(
    tmp_path: Path,
) -> None:
    args = make_args(tmp_path, binary="/bin/true", sizes=[10, 100], expected_complexity="linear")
    tier1 = {
        "time_usage_by_size": {
            10: [{"wall_seconds": 0.01}],
            100: [{"wall_seconds": 0.1}],
        }
    }

    result = pipeline.score_algorithmic_scaling(tier1, {}, args)

    assert result["tier"] == "N/A"
    assert result["score"] == -1
    assert "missing_sub_checks" in result


def test_score_algorithmic_scaling_uses_call_counts_for_call_amplification(tmp_path: Path) -> None:
    args = make_args(tmp_path, valgrind_size=100)
    tier234 = {
        "callgrind": {
            "functions": [{"Ir": 5000, "file": "src/mod.c", "line": 1, "function": "hot"}],
            "total_ir": 5000,
            "total_calls": 5000,
            "multiplicative_path_count": 0,
        },
        "cachegrind": {
            "summary": {"Dr": 1000, "Dw": 50},
        },
        "massif": {"local_maxima_count": 1},
    }

    result = pipeline.score_algorithmic_scaling({}, tier234, args)

    assert result["sub_checks"]["call_amplification"]["ratio"] == 50.0
    assert result["sub_checks"]["call_amplification"]["tier"] == "WARN"
    assert result["tier"] == "N/A"


def test_score_wall_time_stability_groups_explicit_target_timings_by_size() -> None:
    tier1 = {
        "time_usage_by_size": {
            10: [{"wall_seconds": 0.01}, {"wall_seconds": 0.0101}],
            1000: [{"wall_seconds": 1.0}, {"wall_seconds": 1.01}],
        }
    }

    result = pipeline.score_wall_time_stability(tier1)

    assert result["tier"] == "PASS"
    assert result["cv"] < 3
    assert result["cv_by_size"] == {
        10: round(pipeline._cv([0.01, 0.0101]), 2),
        1000: round(pipeline._cv([1.0, 1.01]), 2),
    }


def test_finding_schema_accepts_na_result() -> None:
    schema = json.loads((REPO_ROOT / "references" / "finding-schema.json").read_text())
    finding = {
        "dimension": "Algorithmic Scaling",
        "score": -1,
        "tier": "N/A",
    }

    jsonschema.validate(instance=finding, schema=schema)


def test_write_json_summary_uses_per_size_wall_time_metrics(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    rubric = {
        "total": 4,
        "max_possible": 8,
        "dimensions": [
            ("Algorithmic Scaling", {"score": -1, "tier": "N/A"}),
            (
                "Wall-Time Stability",
                {"score": 4, "tier": "PASS", "cv": 2.12, "cv_by_size": {10: 0.7, 1000: 2.12}},
            ),
        ],
        "baseline_regressions": [],
    }
    tier1 = {
        "time_usage": [
            {"wall_seconds": 0.01, "input_size": 10},
            {"wall_seconds": 0.0101, "input_size": 10},
            {"wall_seconds": 1.0, "input_size": 1000},
            {"wall_seconds": 1.01, "input_size": 1000},
        ],
        "time_usage_by_size": {
            10: [{"wall_seconds": 0.01}, {"wall_seconds": 0.0101}],
            1000: [{"wall_seconds": 1.0}, {"wall_seconds": 1.01}],
        },
    }
    prereqs = {
        "python_ok": True,
        "valgrind": "/usr/bin/valgrind",
        "perf_paranoid": 0,
        "governor": "performance",
        "cache_topology": {},
        "ram_mb": 1024,
    }
    args = make_args(tmp_path, tier="fast", sizes=[10, 1000])
    expected = pipeline.score_wall_time_stability(tier1)

    pipeline.write_json_summary(rubric, tier1, {}, prereqs, args, out_dir)

    summary = json.loads((out_dir / "benchmark_summary.json").read_text())

    assert summary["wall_time_cv"] == expected["cv"]
    assert summary["wall_time_cv_by_size"] == {"10": 0.7, "1000": 0.7}


def test_write_json_summary_includes_perf_record_block(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    rubric = {"total": 0, "max_possible": 0, "dimensions": [], "baseline_regressions": []}
    prereqs = {
        "python_ok": True,
        "valgrind": None,
        "perf_paranoid": 0,
        "governor": "performance",
        "cache_topology": {},
        "ram_mb": 1024,
    }
    args = make_args(tmp_path, tier="deep", perf_record=True)
    tier234 = {
        "perf_record": {
            "available": True,
            "hotspots": [
                {
                    "overhead_pct": 42.5,
                    "command": "bench",
                    "shared_object": "bench",
                    "symbol": "[.] hot_loop",
                }
            ],
            "data_path": str(out_dir / "tier3" / "perf.data"),
        }
    }

    pipeline.write_json_summary(rubric, {}, tier234, prereqs, args, out_dir)

    summary = json.loads((out_dir / "benchmark_summary.json").read_text())

    assert summary["perf_record"]["available"] is True
    assert summary["perf_record"]["hotspots"][0]["symbol"] == "[.] hot_loop"


def test_write_markdown_report_explains_missing_algorithmic_subchecks(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    rubric = {
        "total": 4,
        "max_possible": 8,
        "dimensions": [
            (
                "Algorithmic Scaling",
                {
                    "score": -1,
                    "tier": "N/A",
                    "sub_checks": {"complexity_exponent": {"k": 1.0, "tier": "PASS"}},
                    "missing_sub_checks": [
                        "call_amplification",
                        "data_reuse",
                        "write_amplification",
                        "allocation_churn",
                        "multiplicative_paths",
                    ],
                    "note": "Incomplete evidence for strict scaling rubric",
                },
            ),
            ("Wall-Time Stability", {"score": 4, "tier": "PASS", "cv": 2.12}),
        ],
        "baseline_regressions": [],
    }
    prereqs = {
        "python_ok": True,
        "valgrind": None,
        "perf_paranoid": 0,
        "governor": "performance",
        "cache_topology": {},
        "ram_mb": 1024,
    }
    args = make_args(tmp_path, tier="fast", sizes=[10, 1000])

    pipeline.write_markdown_report(rubric, {}, {}, prereqs, args, out_dir)

    report = (out_dir / "benchmark_report.md").read_text()

    assert "Incomplete evidence for strict scaling rubric" in report
    assert "call_amplification" in report
    assert "data_reuse" in report
    assert "Run benchmarks at >= 2 input sizes" not in report


def test_write_json_summary_prefers_pytest_wall_time_metrics(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    tier1 = {
        "pytest_benchmark": {
            "benchmarks": [
                {"stats": {"mean": 1.0, "stddev": 0.01}},
                {"stats": {"mean": 1.0, "stddev": 0.02}},
            ]
        },
        "time_usage": [
            {"wall_seconds": 0.01},
            {"wall_seconds": 0.011},
            {"wall_seconds": 1.0},
            {"wall_seconds": 1.01},
        ],
    }
    rubric = {
        "total": 4,
        "max_possible": 4,
        "dimensions": [("Wall-Time Stability", pipeline.score_wall_time_stability(tier1))],
        "baseline_regressions": [],
    }
    prereqs = {
        "python_ok": True,
        "valgrind": None,
        "perf_paranoid": 0,
        "governor": "performance",
        "cache_topology": {},
        "ram_mb": 1024,
    }
    args = make_args(tmp_path, tier="fast")

    pipeline.write_json_summary(rubric, tier1, {}, prereqs, args, out_dir)

    summary = json.loads((out_dir / "benchmark_summary.json").read_text())

    assert summary["wall_time_cv"] == pipeline.score_wall_time_stability(tier1)["cv"]


def test_write_markdown_report_preserves_zero_algorithmic_values(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    rubric = {
        "total": 0,
        "max_possible": 4,
        "dimensions": [
            (
                "Algorithmic Scaling",
                {
                    "score": -1,
                    "tier": "N/A",
                    "sub_checks": {"multiplicative_paths": {"path_count": 0, "tier": "PASS"}},
                    "missing_sub_checks": ["complexity_exponent"],
                    "note": "Incomplete evidence for strict scaling rubric",
                },
            )
        ],
        "baseline_regressions": [],
    }
    prereqs = {
        "python_ok": True,
        "valgrind": None,
        "perf_paranoid": 0,
        "governor": "performance",
        "cache_topology": {},
        "ram_mb": 1024,
    }
    args = make_args(tmp_path, tier="fast", sizes=[1, 2])

    pipeline.write_markdown_report(rubric, {}, {}, prereqs, args, out_dir)

    report = (out_dir / "benchmark_report.md").read_text()

    assert "| multiplicative_paths | 0 | PASS |" in report


def test_write_markdown_report_finds_algorithmic_dimension_by_name(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    rubric = {
        "total": 4,
        "max_possible": 8,
        "dimensions": [
            ("Wall-Time Stability", {"score": 4, "tier": "PASS", "cv": 1.2}),
            (
                "Algorithmic Scaling",
                {
                    "score": 0,
                    "tier": "FAIL",
                    "sub_checks": {
                        "complexity_exponent": {"k": 2.0, "tier": "FAIL"},
                    },
                },
            ),
        ],
        "baseline_regressions": [],
    }
    prereqs = {
        "python_ok": True,
        "valgrind": None,
        "perf_paranoid": 0,
        "governor": "performance",
        "cache_topology": {},
        "ram_mb": 1024,
    }
    args = make_args(tmp_path, tier="fast", sizes=[10, 100])

    pipeline.write_markdown_report(rubric, {}, {}, prereqs, args, out_dir)

    report = (out_dir / "benchmark_report.md").read_text()

    assert "**Result: FAIL** (score: 0/4)" in report
    assert "Fix algorithmic scaling before hardware-level optimization." in report


def test_write_markdown_report_includes_native_hotspots_section(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    rubric = {
        "total": 0,
        "max_possible": 4,
        "dimensions": [
            (
                "Algorithmic Scaling",
                {"score": -1, "tier": "N/A", "sub_checks": {}, "note": "Insufficient data"},
            )
        ],
        "baseline_regressions": [],
    }
    prereqs = {
        "python_ok": True,
        "valgrind": None,
        "perf_paranoid": 0,
        "governor": "performance",
        "cache_topology": {},
        "ram_mb": 1024,
    }
    args = make_args(tmp_path, tier="deep", perf_record=True)
    tier234 = {
        "perf_record": {
            "available": True,
            "hotspots": [
                {
                    "overhead_pct": 42.5,
                    "command": "bench",
                    "shared_object": "bench",
                    "symbol": "[.] hot_loop",
                },
                {
                    "overhead_pct": 13.25,
                    "command": "bench",
                    "shared_object": "libfoo.so",
                    "symbol": "[.] helper_fn",
                },
            ],
        }
    }

    pipeline.write_markdown_report(rubric, {}, tier234, prereqs, args, out_dir)

    report = (out_dir / "benchmark_report.md").read_text()

    assert "## Native Hotspots" in report
    assert "[.] hot_loop" in report
    assert "42.5" in report


def test_score_algorithmic_scaling_uses_hotspot_level_data_reuse(tmp_path: Path) -> None:
    args = make_args(tmp_path, valgrind_size=10)
    tier234 = {
        "callgrind": {
            "functions": [{"Ir": 1, "file": "src/mod.c", "line": 1, "function": "hot"}],
            "total_calls": 1,
            "multiplicative_path_count": 0,
        },
        "cachegrind": {
            "summary": {"Dr": 120, "Dw": 12},
            "files": [
                {"file": "a.c", "Dr": 60, "Dw": 6},
                {"file": "b.c", "Dr": 60, "Dw": 6},
            ],
        },
        "massif": {"local_maxima_count": 0},
    }

    result = pipeline.score_algorithmic_scaling({}, tier234, args)

    assert result["sub_checks"]["data_reuse"]["ratio"] == 6.0
    assert result["sub_checks"]["data_reuse"]["tier"] == "PASS"


def test_score_algorithmic_scaling_uses_hotspot_level_write_amplification(tmp_path: Path) -> None:
    args = make_args(tmp_path, valgrind_size=10)
    tier234 = {
        "callgrind": {
            "functions": [{"Ir": 1, "file": "src/mod.c", "line": 1, "function": "hot"}],
            "total_calls": 1,
            "multiplicative_path_count": 0,
        },
        "cachegrind": {
            "summary": {"Dr": 10100, "Dw": 100},
            "files": [
                {"file": "hot.c", "Dr": 100, "Dw": 100},
                {"file": "cold.c", "Dr": 10000, "Dw": 0},
            ],
        },
        "massif": {"local_maxima_count": 0},
    }

    result = pipeline.score_algorithmic_scaling({}, tier234, args)

    assert result["sub_checks"]["write_amplification"]["ratio"] == 1.0
    assert result["sub_checks"]["write_amplification"]["tier"] == "FAIL"


def test_wall_time_stability_noise_gate_excludes_from_total(tmp_path: Path) -> None:
    """CV > max_cv → tier "N/A (noise)", score excluded from rubric total."""
    args = make_args(tmp_path, max_cv=5.0)
    # tier234: only L1 cache is scorable (PASS=4); all other dims stay N/A.
    tier234: dict = {
        "cachegrind": {
            "summary": {"Dr": 0},
            "files": [
                {"file": "a.c", "Dr": 5000, "D1mr": 25, "L1d_miss_pct": 0.5},
            ],
        }
    }

    # ── noise case ──────────────────────────────────────────────────────
    noisy_tier1: dict = {
        "time_usage": [
            {"wall_seconds": 1.0},
            {"wall_seconds": 1.0},
            {"wall_seconds": 1.0},
            {"wall_seconds": 3.0},
        ]
    }
    noisy_wall = pipeline.score_wall_time_stability(noisy_tier1, max_cv=5.0)
    assert noisy_wall["tier"] == "N/A (noise)"
    assert noisy_wall["score"] == -1  # excluded from total
    # Verify CV was measured
    assert "cv" in noisy_wall and noisy_wall["cv"] is not None
    assert noisy_wall["cv"] > 5.0  # CV ≈ 66.67%

    noisy_rubric = pipeline.score_rubric(noisy_tier1, tier234, args)
    wall_dim = dict(noisy_rubric["dimensions"])["Wall-Time Stability"]
    assert wall_dim["tier"] == "N/A (noise)"
    # Only L1 Cache contributes (score=4); wall-time must NOT count.
    scorable = [
        d for _, d in noisy_rubric["dimensions"] if d.get("tier") not in ("N/A", "N/A (noise)")
    ]
    assert noisy_rubric["total"] == sum(d["score"] for d in scorable)
    assert noisy_rubric["max_possible"] == len(scorable) * 4
    assert noisy_rubric["total"] == 4  # L1 Cache = PASS (4)

    # ── clean case (same max_cv, normal CV) ─────────────────────────────
    clean_tier1: dict = {
        "time_usage": [
            {"wall_seconds": 1.0},
            {"wall_seconds": 1.01},
            {"wall_seconds": 0.99},
            {"wall_seconds": 1.0},
        ]
    }
    clean_wall = pipeline.score_wall_time_stability(clean_tier1, max_cv=5.0)
    assert clean_wall["tier"] == "PASS"
    assert clean_wall["score"] == 4
    assert clean_wall["cv"] is not None and clean_wall["cv"] < 3  # CV ≈ 0.82%

    clean_rubric = pipeline.score_rubric(clean_tier1, tier234, args)
    # L1 Cache PASS (4) + Wall-Time PASS (4) = 8
    assert clean_rubric["total"] == 8


# ── T5: environment fingerprint + wall-time percentiles ──────────────


def test_write_json_summary_includes_environment_fingerprint(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    rubric = {"total": 0, "max_possible": 0, "dimensions": [], "baseline_regressions": []}
    prereqs = {
        "python_ok": True,
        "valgrind": None,
        "perf_paranoid": 0,
        "governor": "performance",
        "cache_topology": {},
        "ram_mb": 1024,
    }
    args = make_args(tmp_path, tier="fast")
    tier1 = {"time_usage": [{"wall_seconds": 0.01}]}

    pipeline.write_json_summary(rubric, tier1, {}, prereqs, args, out_dir)
    summary = json.loads((out_dir / "benchmark_summary.json").read_text())

    env = summary["environment"]
    assert isinstance(env, dict)
    assert "cpu_model" in env
    assert "kernel" in env
    assert "governor" in env
    assert "smt" in env
    assert "load_avg_1m" in env
    assert "python_version" in env
    assert "timestamp_utc" in env
    # Type checks
    assert isinstance(env["cpu_model"], str)
    assert isinstance(env["kernel"], str)
    assert isinstance(env["governor"], str)
    assert isinstance(env["smt"], str)
    assert isinstance(env["load_avg_1m"], float)
    assert isinstance(env["python_version"], str)
    assert isinstance(env["timestamp_utc"], str)


def test_write_json_summary_includes_wall_time_percentiles(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    rubric = {"total": 0, "max_possible": 0, "dimensions": [], "baseline_regressions": []}
    prereqs = {
        "python_ok": True,
        "valgrind": None,
        "perf_paranoid": 0,
        "governor": "performance",
        "cache_topology": {},
        "ram_mb": 1024,
    }
    args = make_args(tmp_path, tier="fast")
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    tier1 = {"time_usage": [{"wall_seconds": v} for v in values]}

    pipeline.write_json_summary(rubric, tier1, {}, prereqs, args, out_dir)
    summary = json.loads((out_dir / "benchmark_summary.json").read_text())

    pcts = summary["wall_time_percentiles"]
    assert isinstance(pcts, dict)
    # Exact values per plan: statistics.quantiles(values, n=100) indices 49/94/98
    assert pcts["p50"] == 5.5
    assert pcts["p95"] == 10.45
    assert pcts["p99"] == 10.89
