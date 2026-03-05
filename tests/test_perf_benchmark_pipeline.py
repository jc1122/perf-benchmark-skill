from __future__ import annotations

import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "perf_benchmark_pipeline.py"

SPEC = importlib.util.spec_from_file_location("perf_benchmark_pipeline", MODULE_PATH)
assert SPEC and SPEC.loader
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)


def make_args(tmp_path: Path, **overrides: object) -> Namespace:
    defaults: dict[str, object] = {
        "root": tmp_path,
        "out_dir": tmp_path / "out",
        "target": None,
        "binary": None,
        "python": "python3",
        "source_prefix": None,
        "tier": "medium",
        "sizes": [],
        "valgrind_size": 10_000,
        "max_valgrind_parallel": 2,
        "expected_complexity": "nlogn",
        "baseline": None,
        "perf_repeats": 1,
        "perf_events": None,
        "time_repeats": 1,
        "asm_audit": False,
        "valgrind_timeout": 30,
        "env": [],
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def test_main_runs_non_valgrind_stages_when_valgrind_is_missing(monkeypatch, tmp_path: Path) -> None:
    args = make_args(tmp_path, tier="asm", binary="/bin/true")
    called: dict[str, bool] = {}

    monkeypatch.setattr(pipeline, "parse_args", lambda argv=None: args)
    monkeypatch.setattr(
        pipeline,
        "check_prerequisites",
        lambda _args: {
            "python_ok": True,
            "valgrind": None,
            "perf_paranoid": 0,
            "governor": "performance",
            "cache_topology": {},
            "ram_mb": 16_384,
        },
    )
    monkeypatch.setattr(pipeline, "stage_tier1", lambda *a, **k: {})

    def fake_run_parallel_tiers(*_args, **_kwargs):
        called["ran"] = True
        return {"perf_stat": {"available": False}, "objdump": {"generated": []}}

    monkeypatch.setattr(pipeline, "run_parallel_tiers", fake_run_parallel_tiers)
    monkeypatch.setattr(pipeline, "score_rubric", lambda *a, **k: {"dimensions": [], "total": 0, "max_possible": 0})
    monkeypatch.setattr(pipeline, "write_markdown_report", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "write_json_summary", lambda *a, **k: None)

    exit_code = pipeline.main([])

    assert exit_code == 0
    assert called.get("ran") is True


def test_stage_perf_stat_uses_augmented_environment(monkeypatch, tmp_path: Path) -> None:
    args = make_args(tmp_path, env=["FOO=bar"], binary="/bin/true")
    captured: dict[str, object] = {}

    monkeypatch.setattr(pipeline.shutil, "which", lambda name: "/usr/bin/perf" if name == "perf" else None)
    monkeypatch.setattr(pipeline, "_build_target_cmd", lambda *_args: ["/bin/true"])

    def fake_run(cmd, capture_output, text, cwd, env=None, timeout=None):
        captured["cmd"] = cmd
        captured["env"] = env
        return SimpleNamespace(stderr="", stdout="", returncode=0)

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    pipeline.stage_perf_stat(args, {"perf_paranoid": 0}, [], tmp_path / "out")

    assert isinstance(captured.get("env"), dict)
    assert captured["env"]["FOO"] == "bar"


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


def test_stage_objdump_discovers_extension_modules_outside_source_prefix_path(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    so_file = root / "build" / "lib.linux-x86_64-cpython-312" / "pkg" / "module.so"
    so_file.parent.mkdir(parents=True)
    so_file.write_bytes(b"ELF")
    args = make_args(root, root=root, out_dir=root / "out", source_prefix="src/pkg/", tier="asm")

    monkeypatch.setattr(
        pipeline.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(stdout="asm", stderr="", returncode=0),
    )

    result = pipeline.stage_objdump(args, {}, [], root / "out")

    assert len(result["generated"]) == 1
    generated = Path(result["generated"][0])
    assert generated.name == "objdump_module.so.txt"
    assert generated.read_text() == "asm"


def test_skill_markdown_frontmatter_uses_trigger_language() -> None:
    text = (REPO_ROOT / "SKILL.md").read_text()
    frontmatter = text.split("---", maxsplit=2)[1]
    assert "Use when" in frontmatter


def test_skill_markdown_examples_reference_real_script_names() -> None:
    text = (REPO_ROOT / "SKILL.md").read_text()
    assert "perf-benchmark-skill/scripts/perf_benchmark_pipeline.py" not in text
    assert "python pipeline.py" not in text


def test_docs_describe_explicit_target_as_repo_agnostic_path() -> None:
    skill_text = (REPO_ROOT / "SKILL.md").read_text()
    readme_text = (REPO_ROOT / "README.md").read_text()

    assert "Use `--target` or `--binary` for non-pytest repos." in skill_text
    assert "Pytest benchmark autodiscovery is a convenience for Python repos." in skill_text
    assert "For repo-agnostic use, pass an explicit `--target` or `--binary`." in readme_text


def test_skill_regression_example_uses_explicit_target_or_binary() -> None:
    text = (REPO_ROOT / "SKILL.md").read_text()

    assert "--baseline /tmp/previous/benchmark_summary.json" in text
    assert '--target "cargo run --release --bin bench -- {SIZE}" --baseline' in text


def test_main_requires_real_benchmark_target(monkeypatch, tmp_path: Path) -> None:
    args = make_args(tmp_path, tier="fast")
    called: dict[str, bool] = {}

    monkeypatch.setattr(pipeline, "parse_args", lambda argv=None: args)
    monkeypatch.setattr(
        pipeline,
        "check_prerequisites",
        lambda _args: {
            "python_ok": True,
            "valgrind": None,
            "perf_paranoid": 0,
            "governor": "performance",
            "cache_topology": {},
            "ram_mb": 16_384,
        },
    )
    monkeypatch.setattr(pipeline, "discover_targets", lambda _root: [])
    monkeypatch.setattr(
        pipeline,
        "stage_tier1",
        lambda *_args, **_kwargs: called.setdefault("tier1", True),
    )

    exit_code = pipeline.main([])

    assert exit_code == 1
    assert called == {}


def test_main_returns_error_when_stage_reports_failure(monkeypatch, tmp_path: Path) -> None:
    args = make_args(tmp_path, tier="deep", binary="/bin/true")

    monkeypatch.setattr(pipeline, "parse_args", lambda argv=None: args)
    monkeypatch.setattr(
        pipeline,
        "check_prerequisites",
        lambda _args: {
            "python_ok": True,
            "valgrind": "/usr/bin/valgrind",
            "perf_paranoid": 0,
            "governor": "performance",
            "cache_topology": {},
            "ram_mb": 16_384,
        },
    )
    monkeypatch.setattr(pipeline, "stage_tier1", lambda *a, **k: {"time_usage": []})
    monkeypatch.setattr(
        pipeline,
        "run_parallel_tiers",
        lambda *_args, **_kwargs: {"perf_stat": {"error": "exit 2"}},
    )
    monkeypatch.setattr(pipeline, "score_rubric", lambda *a, **k: {"dimensions": [], "total": 0, "max_possible": 0})
    monkeypatch.setattr(pipeline, "write_markdown_report", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "write_json_summary", lambda *a, **k: None)

    assert pipeline.main([]) == 1


def test_stage_tier1_tracemalloc_measures_child_python_process(tmp_path: Path) -> None:
    script_path = tmp_path / "alloc.py"
    script_path.write_text(
        "payload = [bytearray(4096) for _ in range(5000)]\n"
        "print(len(payload))\n"
    )
    args = make_args(
        tmp_path,
        target=f"{sys.executable} alloc.py",
        time_repeats=1,
    )

    results = pipeline.stage_tier1(args, {}, [], tmp_path / "out")

    assert results["tracemalloc"]["peak_bytes"] > 10_000_000


def test_stage_tier1_times_explicit_binary_for_each_size(monkeypatch, tmp_path: Path) -> None:
    args = make_args(
        tmp_path,
        root=tmp_path,
        out_dir=tmp_path / "out",
        binary="/bin/true",
        sizes=[10, 20],
        time_repeats=1,
    )
    seen_targets: list[list[str]] = []

    def fake_run(cmd, capture_output, text, cwd=None, env=None, timeout=None):
        if cmd[0] == "/usr/bin/time":
            seen_targets.append(cmd[2:])
            return SimpleNamespace(returncode=0, stderr="Elapsed (wall clock) time (h:mm:ss or m:ss): 0:00.01\n", stdout="")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    results = pipeline.stage_tier1(args, {}, [], tmp_path / "out")

    assert seen_targets == [["/bin/true", "10"], ["/bin/true", "20"]]
    assert sorted(results["time_usage_by_size"]) == [10, 20]


def test_score_algorithmic_scaling_uses_time_usage_by_size_when_pytest_data_missing(tmp_path: Path) -> None:
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


def test_stage_tier1_marks_tracemalloc_error_for_python_interpreter_flags(tmp_path: Path) -> None:
    script_path = tmp_path / "alloc.py"
    script_path.write_text("print('ok')\n")
    args = make_args(
        tmp_path,
        target=f"{sys.executable} -O alloc.py",
        time_repeats=1,
    )

    results = pipeline.stage_tier1(args, {}, [], tmp_path / "out")

    assert "error" in results["tracemalloc"]


def test_stage_cachegrind_annotation_uses_timeout(monkeypatch, tmp_path: Path) -> None:
    args = make_args(
        tmp_path,
        root=tmp_path,
        out_dir=tmp_path / "out",
        source_prefix="src/pkg/",
        binary="/bin/true",
    )
    captured: list[int | None] = []

    def fake_run(cmd, capture_output, text, cwd=None, env=None, timeout=None):
        if cmd[0] == "valgrind":
            (tmp_path / "out" / "tier2").mkdir(parents=True, exist_ok=True)
            (tmp_path / "out" / "tier2" / "cachegrind.out").write_text("cachegrind")
            return SimpleNamespace(returncode=0, stderr="", stdout="")
        captured.append(timeout)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    pipeline.stage_cachegrind(args, {"cache_topology": {}}, [], tmp_path / "out")

    assert captured == [args.valgrind_timeout]


def test_stage_callgrind_annotation_uses_timeout(monkeypatch, tmp_path: Path) -> None:
    args = make_args(
        tmp_path,
        root=tmp_path,
        out_dir=tmp_path / "out",
        source_prefix="src/pkg/",
        binary="/bin/true",
    )
    captured: list[int | None] = []

    def fake_run(cmd, capture_output, text, cwd=None, env=None, timeout=None):
        if cmd[0] == "valgrind":
            (tmp_path / "out" / "tier2").mkdir(parents=True, exist_ok=True)
            (tmp_path / "out" / "tier2" / "callgrind.out").write_text("callgrind")
            return SimpleNamespace(returncode=0, stderr="", stdout="")
        captured.append(timeout)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    pipeline.stage_callgrind(args, {"cache_topology": {}}, [], tmp_path / "out")

    assert captured == [args.valgrind_timeout]


def test_stage_massif_post_processing_uses_timeout(monkeypatch, tmp_path: Path) -> None:
    args = make_args(tmp_path, root=tmp_path, out_dir=tmp_path / "out", binary="/bin/true")
    captured: list[int | None] = []

    def fake_run(cmd, capture_output, text, cwd=None, env=None, timeout=None):
        if cmd[0] == "valgrind":
            (tmp_path / "out" / "tier3").mkdir(parents=True, exist_ok=True)
            (tmp_path / "out" / "tier3" / "massif.out").write_text("snapshot=0\nmem_heap_B=1\n")
            return SimpleNamespace(returncode=0, stderr="", stdout="")
        captured.append(timeout)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    pipeline.stage_massif(args, {"cache_topology": {}}, [], tmp_path / "out")

    assert captured == [args.valgrind_timeout]


def test_stage_perf_stat_uses_timeout(monkeypatch, tmp_path: Path) -> None:
    args = make_args(tmp_path, env=["FOO=bar"], binary="/bin/true")
    captured: list[int | None] = []

    monkeypatch.setattr(pipeline.shutil, "which", lambda name: "/usr/bin/perf" if name == "perf" else None)
    monkeypatch.setattr(pipeline, "_build_target_cmd", lambda *_args: ["/bin/true"])

    def fake_run(cmd, capture_output, text, cwd, env=None, timeout=None):
        captured.append(timeout)
        return SimpleNamespace(stderr="", stdout="", returncode=0)

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    pipeline.stage_perf_stat(args, {"perf_paranoid": 0}, [], tmp_path / "out")

    assert captured == [args.valgrind_timeout]


def test_stage_objdump_uses_timeout(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    so_file = root / "build" / "pkg" / "module.so"
    so_file.parent.mkdir(parents=True)
    so_file.write_bytes(b"ELF")
    args = make_args(root, root=root, out_dir=root / "out", source_prefix="src/pkg/", tier="asm")
    captured: list[int | None] = []

    def fake_run(*_args, **kwargs):
        captured.append(kwargs.get("timeout"))
        return SimpleNamespace(stdout="asm", stderr="", returncode=0)

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    pipeline.stage_objdump(args, {}, [], root / "out")

    assert captured == [args.valgrind_timeout]


def test_parse_cachegrind_summary_handles_decimal_totals() -> None:
    text = "\n".join(
        [
            "Ir I1mr D1mr",
            "123.456 7 8 PROGRAM TOTALS",
        ]
    )

    result = pipeline._parse_cachegrind_summary(text)

    assert result["summary"]["Ir"] == 123
    assert result["summary"]["I1mr"] == 7


def test_fit_exponent_ignores_non_positive_sizes() -> None:
    assert pipeline._fit_exponent([0, 100, 1000], [1.0, 10.0, 100.0]) == 1.0


def test_build_valgrind_target_cmd_does_not_assume_pytest_name_filter(tmp_path: Path) -> None:
    args = make_args(tmp_path)

    cmd = pipeline._build_valgrind_target_cmd(args, ["tests/benchmarks"])

    assert "-k" not in cmd


def test_build_valgrind_target_cmd_matches_binary_argument_behavior(tmp_path: Path) -> None:
    args = make_args(tmp_path, binary="/bin/true", sizes=[], valgrind_size=123)

    cmd = pipeline._build_valgrind_target_cmd(args, [])

    assert cmd == ["/bin/true"]


def test_score_algorithmic_scaling_is_na_when_required_subchecks_are_missing(tmp_path: Path) -> None:
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


def test_parse_callgrind_raw_tracks_total_calls_and_multiplicative_paths() -> None:
    text = "\n".join(
        [
            "events: Ir",
            "fl=src/mod.c",
            "fn=parent",
            "1 10",
            "cfl=src/mod.c",
            "cfn=child_a",
            "calls=150 0",
            "2 5",
            "cfl=src/mod.c",
            "cfn=child_b",
            "calls=250 0",
            "3 7",
        ]
    )

    result = pipeline._parse_callgrind_raw(text, input_size=100)

    assert result["total_calls"] == 400
    assert result["multiplicative_path_count"] == 2


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
    assert result["cv_by_size"] == {10: round(pipeline._cv([0.01, 0.0101]), 2), 1000: round(pipeline._cv([1.0, 1.01]), 2)}


def test_finding_schema_accepts_na_result() -> None:
    schema = json.loads((REPO_ROOT / "references" / "finding-schema.json").read_text())
    finding = {
        "dimension": "Algorithmic Scaling",
        "score": -1,
        "tier": "N/A",
    }

    jsonschema.validate(instance=finding, schema=schema)


def test_parse_args_requires_size_placeholder_for_multi_size_target(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        pipeline.parse_args(
            [
                "--root",
                str(tmp_path),
                "--out-dir",
                str(tmp_path / "out"),
                "--target",
                "python bench.py",
                "--sizes",
                "10,100",
            ]
        )


def test_write_json_summary_uses_per_size_wall_time_metrics(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    rubric = {
        "total": 4,
        "max_possible": 8,
        "dimensions": [
            ("Algorithmic Scaling", {"score": -1, "tier": "N/A"}),
            ("Wall-Time Stability", {"score": 4, "tier": "PASS", "cv": 2.12, "cv_by_size": {10: 0.7, 1000: 2.12}}),
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


def test_docs_require_size_placeholder_for_multi_size_explicit_target() -> None:
    skill_text = (REPO_ROOT / "SKILL.md").read_text()
    readme_text = (REPO_ROOT / "README.md").read_text()

    assert "Multi-size explicit targets must include `{SIZE}`." in skill_text
    assert "Multi-size explicit targets must include `{SIZE}`." in readme_text


def test_parse_args_requires_size_placeholder_for_any_explicit_target_sizes(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        pipeline.parse_args(
            [
                "--root",
                str(tmp_path),
                "--out-dir",
                str(tmp_path / "out"),
                "--target",
                "python bench.py",
                "--sizes",
                "10",
            ]
        )


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
                    "sub_checks": {
                        "multiplicative_paths": {"path_count": 0, "tier": "PASS"}
                    },
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
