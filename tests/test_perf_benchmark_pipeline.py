from __future__ import annotations

import importlib.util
import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace


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

    def fake_run(cmd, capture_output, text, cwd, env=None):
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
