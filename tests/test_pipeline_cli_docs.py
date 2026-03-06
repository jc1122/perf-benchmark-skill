from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.helpers import REPO_ROOT, make_args, pipeline


def test_main_runs_non_valgrind_stages_when_valgrind_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
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
    monkeypatch.setattr(
        pipeline, "score_rubric", lambda *a, **k: {"dimensions": [], "total": 0, "max_possible": 0}
    )
    monkeypatch.setattr(pipeline, "write_markdown_report", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "write_json_summary", lambda *a, **k: None)

    exit_code = pipeline.main([])

    assert exit_code == 0
    assert called.get("ran") is True


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
    monkeypatch.setattr(
        pipeline, "score_rubric", lambda *a, **k: {"dimensions": [], "total": 0, "max_possible": 0}
    )
    monkeypatch.setattr(pipeline, "write_markdown_report", lambda *a, **k: None)
    monkeypatch.setattr(pipeline, "write_json_summary", lambda *a, **k: None)

    assert pipeline.main([]) == 1


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


def test_parse_args_enables_perf_record_flag(tmp_path: Path) -> None:
    args = pipeline.parse_args(
        [
            "--root",
            str(tmp_path),
            "--out-dir",
            str(tmp_path / "out"),
            "--binary",
            "/bin/true",
            "--perf-record",
        ]
    )

    assert args.perf_record is True


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


def test_main_writes_report_and_summary_artifacts(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"

    exit_code = pipeline.main(
        [
            "--root",
            str(tmp_path),
            "--out-dir",
            str(out_dir),
            "--tier",
            "fast",
            "--target",
            f'{sys.executable} -c "print(1)"',
        ]
    )

    assert exit_code == 0
    assert (out_dir / "benchmark_report.md").exists()
    assert (out_dir / "benchmark_summary.json").exists()


def test_main_report_contains_scorecard_sections(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"

    pipeline.main(
        [
            "--root",
            str(tmp_path),
            "--out-dir",
            str(out_dir),
            "--tier",
            "fast",
            "--target",
            f'{sys.executable} -c "print(1)"',
        ]
    )

    report = (out_dir / "benchmark_report.md").read_text()

    assert "## Rubric Scorecard" in report
    assert "## Algorithmic Scaling Analysis" in report


def test_pipeline_module_re_exports_existing_tested_api() -> None:
    for name in [
        "main",
        "parse_args",
        "stage_tier1",
        "score_algorithmic_scaling",
        "write_markdown_report",
        "write_json_summary",
    ]:
        assert hasattr(pipeline, name)


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
    assert "mypkg" not in skill_text
    assert "mypkg" not in readme_text
    assert "src/pkg/" not in skill_text
    assert "src/mypkg/" not in readme_text
    assert "cargo run --release --bin bench" not in skill_text
    assert "./my_program" not in skill_text
    assert "./build/my_program" not in skill_text
    assert "jc1122/perf-benchmark-skill" not in readme_text


def test_readme_explains_skill_source_placeholder() -> None:
    readme_text = (REPO_ROOT / "README.md").read_text()

    assert (
        "`<skill-source>` means the installable source or repository path that hosts this skill."
        in readme_text
    )


def test_skill_regression_example_uses_explicit_target_or_binary() -> None:
    text = (REPO_ROOT / "SKILL.md").read_text()

    assert "--baseline /path/to/previous/benchmark_summary.json" in text
    assert '--target "./path/to/benchmark {SIZE}" --baseline' in text


def test_docs_require_size_placeholder_for_multi_size_explicit_target() -> None:
    skill_text = (REPO_ROOT / "SKILL.md").read_text()
    readme_text = (REPO_ROOT / "README.md").read_text()

    assert "Multi-size explicit targets must include `{SIZE}`." in skill_text
    assert "Multi-size explicit targets must include `{SIZE}`." in readme_text


def test_docs_state_dimension_zero_requires_deep_for_full_score() -> None:
    skill_text = (REPO_ROOT / "SKILL.md").read_text()
    readme_text = (REPO_ROOT / "README.md").read_text()
    expected_text = (
        "Full Algorithmic Scaling scoring requires `deep` or `asm` "
        "because allocation churn comes from massif."
    )

    assert expected_text in skill_text
    assert expected_text in readme_text


def test_docs_describe_opt_in_perf_record_stage() -> None:
    skill_text = (REPO_ROOT / "SKILL.md").read_text()
    readme_text = (REPO_ROOT / "README.md").read_text()
    tool_guide_text = (REPO_ROOT / "references" / "tool-guide.md").read_text()

    assert "`--perf-record`" in skill_text
    assert "`--perf-record`" in readme_text
    assert "opt-in" in skill_text
    assert "opt-in" in readme_text
    assert "perf record" in tool_guide_text
    assert "perf report" in tool_guide_text


def test_docs_describe_safe_parallelization_boundaries() -> None:
    skill_text = (REPO_ROOT / "SKILL.md").read_text()
    expected_split_text = (
        "Preferred subagent split: per-artifact or per-rubric-dimension "
        "after the pipeline finishes."
    )

    assert (
        "Tier 1 stays isolated because timing and tracemalloc measurements are noise-sensitive."
        in skill_text
    )
    assert expected_split_text in skill_text


def test_sample_report_uses_generic_example_names() -> None:
    text = (REPO_ROOT / "references" / "sample-report.md").read_text()

    assert "graphcore" not in text
    assert "test_bench_graph.py" not in text
    assert "bench_shortest_paths" not in text
    assert "src/graphcore/" not in text


def test_test_helpers_default_to_current_python_interpreter() -> None:
    args = make_args(Path("/tmp"))

    assert args.python == sys.executable
