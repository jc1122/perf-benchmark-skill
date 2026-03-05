from __future__ import annotations

import importlib.util
import json
import sys
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
