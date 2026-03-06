from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import make_args, pipeline


def test_discover_targets_requires_explicit_pytest_benchmark_marker(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "test_perf_like.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_helper(benchmark):\n    benchmark(lambda: None)\n")

    assert pipeline.discover_targets(tmp_path) == []


def test_discover_targets_accepts_pytest_benchmark_marker(tmp_path: Path) -> None:
    test_file = tmp_path / "tests" / "test_benchmark_marked.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        "import pytest\n\n"
        "@pytest.mark.benchmark\n"
        "def test_bench(benchmark):\n"
        "    benchmark(lambda: None)\n"
    )

    assert pipeline.discover_targets(tmp_path) == ["tests/test_benchmark_marked.py"]


def test_stage_perf_stat_uses_augmented_environment(monkeypatch, tmp_path: Path) -> None:
    args = make_args(tmp_path, env=["FOO=bar"], binary="/bin/true")
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        pipeline.shutil, "which", lambda name: "/usr/bin/perf" if name == "perf" else None
    )
    monkeypatch.setattr(pipeline, "_build_target_cmd", lambda *_args: ["/bin/true"])

    def fake_run(cmd, capture_output, text, cwd, env=None, timeout=None):
        captured["cmd"] = cmd
        captured["env"] = env
        return SimpleNamespace(stderr="", stdout="", returncode=0)

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    pipeline.stage_perf_stat(args, {"perf_paranoid": 0}, [], tmp_path / "out")

    assert isinstance(captured.get("env"), dict)
    assert captured["env"]["FOO"] == "bar"


def test_parse_perf_report_extracts_top_hotspots() -> None:
    text = "\n".join(
        [
            "# Overhead  Command  Shared Object      Symbol",
            "# ........  .......  .................  ...............................",
            "    42.50%  bench    bench              [.] hot_loop",
            "    13.25%  bench    libfoo.so          [.] helper_fn",
        ]
    )

    result = pipeline._parse_perf_report(text)

    assert result["hotspots"] == [
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
    ]


def test_stage_perf_record_returns_unavailable_when_perf_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    args = make_args(tmp_path, perf_record=True, binary="/bin/true")
    monkeypatch.setattr(pipeline.shutil, "which", lambda name: None)

    result = pipeline.stage_perf_record(args, {"perf_paranoid": 0}, [], tmp_path / "out")

    assert result == {"available": False, "reason": "perf not found"}


def test_stage_perf_record_uses_augmented_environment(monkeypatch, tmp_path: Path) -> None:
    args = make_args(tmp_path, env=["FOO=bar"], perf_record=True, binary="/bin/true")
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        pipeline.shutil, "which", lambda name: "/usr/bin/perf" if name == "perf" else None
    )
    monkeypatch.setattr(pipeline, "_build_target_cmd", lambda *_args: ["/bin/true"])

    def fake_run(cmd, capture_output, text, cwd, env=None, timeout=None):
        if cmd[:2] == ["perf", "record"]:
            captured["record_env"] = env
            output_idx = cmd.index("-o") + 1
            Path(cmd[output_idx]).write_bytes(b"perfdata")
            return SimpleNamespace(stderr="", stdout="", returncode=0)
        if cmd[:2] == ["perf", "report"]:
            captured["report_env"] = env
            return SimpleNamespace(
                stderr="",
                stdout=(
                    "# Overhead  Command  Shared Object  Symbol\n"
                    "    100.00%  bench    bench          [.] hot\n"
                ),
                returncode=0,
            )
        raise AssertionError(cmd)

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    pipeline.stage_perf_record(args, {"perf_paranoid": 0}, [], tmp_path / "out")

    assert isinstance(captured.get("record_env"), dict)
    assert captured["record_env"]["FOO"] == "bar"
    assert captured["report_env"]["FOO"] == "bar"


def test_stage_perf_record_uses_timeout(monkeypatch, tmp_path: Path) -> None:
    args = make_args(tmp_path, perf_record=True, binary="/bin/true")
    captured: list[int | None] = []

    monkeypatch.setattr(
        pipeline.shutil, "which", lambda name: "/usr/bin/perf" if name == "perf" else None
    )
    monkeypatch.setattr(pipeline, "_build_target_cmd", lambda *_args: ["/bin/true"])

    def fake_run(cmd, capture_output, text, cwd, env=None, timeout=None):
        captured.append(timeout)
        if cmd[:2] == ["perf", "record"]:
            output_idx = cmd.index("-o") + 1
            Path(cmd[output_idx]).write_bytes(b"perfdata")
            return SimpleNamespace(stderr="", stdout="", returncode=0)
        return SimpleNamespace(
            stdout="# Overhead  Command  Shared Object  Symbol\n", stderr="", returncode=0
        )

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    pipeline.stage_perf_record(args, {"perf_paranoid": 0}, [], tmp_path / "out")

    assert captured == [args.valgrind_timeout, args.valgrind_timeout]


def test_stage_perf_record_preserves_raw_report_when_parsing_yields_no_rows(
    monkeypatch, tmp_path: Path
) -> None:
    args = make_args(tmp_path, perf_record=True, binary="/bin/true")

    monkeypatch.setattr(
        pipeline.shutil, "which", lambda name: "/usr/bin/perf" if name == "perf" else None
    )
    monkeypatch.setattr(pipeline, "_build_target_cmd", lambda *_args: ["/bin/true"])

    def fake_run(cmd, capture_output, text, cwd, env=None, timeout=None):
        if cmd[:2] == ["perf", "record"]:
            output_idx = cmd.index("-o") + 1
            Path(cmd[output_idx]).write_bytes(b"perfdata")
            return SimpleNamespace(stderr="", stdout="", returncode=0)
        return SimpleNamespace(stdout="no parseable hotspots here\n", stderr="", returncode=0)

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    result = pipeline.stage_perf_record(args, {"perf_paranoid": 0}, [], tmp_path / "out")

    report_path = tmp_path / "out" / "tier3" / "perf_report.txt"
    assert report_path.read_text() == "no parseable hotspots here\n"
    assert result["available"] is True
    assert result["hotspots"] == []
    assert result["parse_error"] == "no hotspots parsed from perf report"


def test_stage_objdump_discovers_extension_modules_outside_source_prefix_path(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    so_file = root / "build" / "lib.linux-x86_64-cpython-312" / "pkg" / "module.so"
    so_file.parent.mkdir(parents=True)
    so_file.write_bytes(b"ELF")
    args = make_args(
        root, root=root, out_dir=root / "out", source_prefix="source/module/", tier="asm"
    )

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


def test_stage_tier1_tracemalloc_measures_child_python_process(tmp_path: Path) -> None:
    script_path = tmp_path / "alloc.py"
    script_path.write_text(
        "payload = [bytearray(4096) for _ in range(5000)]\nprint(len(payload))\n"
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
            return SimpleNamespace(
                returncode=0,
                stderr="Elapsed (wall clock) time (h:mm:ss or m:ss): 0:00.01\n",
                stdout="",
            )
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    results = pipeline.stage_tier1(args, {}, [], tmp_path / "out")

    assert seen_targets == [["/bin/true", "10"], ["/bin/true", "20"]]
    assert sorted(results["time_usage_by_size"]) == [10, 20]


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
        source_prefix="source/module/",
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
        source_prefix="source/module/",
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


def test_stage_massif_skips_ms_print_when_tool_is_missing(monkeypatch, tmp_path: Path) -> None:
    args = make_args(tmp_path, root=tmp_path, out_dir=tmp_path / "out", binary="/bin/true")

    def fake_run(cmd, capture_output, text, cwd=None, env=None, timeout=None):
        if cmd[0] == "valgrind":
            (tmp_path / "out" / "tier3").mkdir(parents=True, exist_ok=True)
            (tmp_path / "out" / "tier3" / "massif.out").write_text("snapshot=0\nmem_heap_B=1\n")
            return SimpleNamespace(returncode=0, stderr="", stdout="")
        raise AssertionError(cmd)

    monkeypatch.setattr(pipeline.shutil, "which", lambda name: None)
    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    result = pipeline.stage_massif(args, {"cache_topology": {}}, [], tmp_path / "out")

    assert result["peak_bytes"] == 1
    assert not (tmp_path / "out" / "tier3" / "massif_ms_print.txt").exists()


def test_stage_perf_stat_uses_timeout(monkeypatch, tmp_path: Path) -> None:
    args = make_args(tmp_path, env=["FOO=bar"], binary="/bin/true")
    captured: list[int | None] = []

    monkeypatch.setattr(
        pipeline.shutil, "which", lambda name: "/usr/bin/perf" if name == "perf" else None
    )
    monkeypatch.setattr(pipeline, "_build_target_cmd", lambda *_args: ["/bin/true"])

    def fake_run(cmd, capture_output, text, cwd, env=None, timeout=None):
        captured.append(timeout)
        return SimpleNamespace(stderr="", stdout="", returncode=0)

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    pipeline.stage_perf_stat(args, {"perf_paranoid": 0}, [], tmp_path / "out")

    assert captured == [args.valgrind_timeout]


def test_stage_perf_stat_retries_with_minimal_events_on_unsupported_counter_failure(
    monkeypatch, tmp_path: Path
) -> None:
    args = make_args(tmp_path, binary="/bin/true")
    seen_event_sets: list[str] = []

    monkeypatch.setattr(
        pipeline.shutil, "which", lambda name: "/usr/bin/perf" if name == "perf" else None
    )
    monkeypatch.setattr(pipeline, "_build_target_cmd", lambda *_args: ["/bin/true"])

    def fake_run(cmd, capture_output, text, cwd, env=None, timeout=None):
        event_set = cmd[cmd.index("-e") + 1]
        seen_event_sets.append(event_set)
        if len(seen_event_sets) == 1:
            return SimpleNamespace(
                stderr=(
                    "event syntax error: 'L1-icache-load-misses'\n"
                    "Run 'perf list' for a list of valid events\n"
                ),
                stdout="",
                returncode=129,
            )
        return SimpleNamespace(
            stderr="100 cycles\n200 instructions\n10 branches\n1 branch-misses\n",
            stdout="",
            returncode=0,
        )

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    result = pipeline.stage_perf_stat(args, {"perf_paranoid": 0}, [], tmp_path / "out")

    assert seen_event_sets == [
        (
            "cycles,instructions,branches,branch-misses,"
            "L1-dcache-loads,L1-dcache-load-misses,L1-icache-load-misses,"
            "LLC-loads,LLC-load-misses,dTLB-loads,dTLB-load-misses"
        ),
        "cycles,instructions,branches,branch-misses",
    ]
    assert result["IPC"] == 2.0
    assert result["branch_mispred_pct"] == 10.0


def test_stage_perf_stat_does_not_retry_custom_event_sets(monkeypatch, tmp_path: Path) -> None:
    args = make_args(tmp_path, binary="/bin/true", perf_events="cycles,cache-misses")
    seen_event_sets: list[str] = []

    monkeypatch.setattr(
        pipeline.shutil, "which", lambda name: "/usr/bin/perf" if name == "perf" else None
    )
    monkeypatch.setattr(pipeline, "_build_target_cmd", lambda *_args: ["/bin/true"])

    def fake_run(cmd, capture_output, text, cwd, env=None, timeout=None):
        seen_event_sets.append(cmd[cmd.index("-e") + 1])
        return SimpleNamespace(
            stderr="event syntax error: 'cache-misses'\n",
            stdout="",
            returncode=129,
        )

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)

    result = pipeline.stage_perf_stat(args, {"perf_paranoid": 0}, [], tmp_path / "out")

    assert seen_event_sets == ["cycles,cache-misses"]
    assert result["error"] == "perf stat failed (exit 129)"


def test_run_parallel_tiers_schedules_perf_record_when_enabled(monkeypatch, tmp_path: Path) -> None:
    args = make_args(tmp_path, tier="deep", perf_record=True, binary="/bin/true")

    monkeypatch.setattr(pipeline, "stage_cachegrind", lambda *a, **k: {"stage": "cachegrind"})
    monkeypatch.setattr(pipeline, "stage_callgrind", lambda *a, **k: {"stage": "callgrind"})
    monkeypatch.setattr(pipeline, "stage_massif", lambda *a, **k: {"stage": "massif"})
    monkeypatch.setattr(pipeline, "stage_perf_stat", lambda *a, **k: {"stage": "perf_stat"})
    monkeypatch.setattr(pipeline, "stage_perf_record", lambda *a, **k: {"stage": "perf_record"})

    result = pipeline.run_parallel_tiers(
        args, {"valgrind": "/usr/bin/valgrind"}, [], tmp_path / "out"
    )

    assert result["perf_record"] == {"stage": "perf_record"}


def test_stage_objdump_uses_timeout(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "repo"
    so_file = root / "build" / "pkg" / "module.so"
    so_file.parent.mkdir(parents=True)
    so_file.write_bytes(b"ELF")
    args = make_args(
        root, root=root, out_dir=root / "out", source_prefix="source/module/", tier="asm"
    )
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


def test_build_valgrind_target_cmd_does_not_assume_pytest_name_filter(tmp_path: Path) -> None:
    args = make_args(tmp_path)

    cmd = pipeline._build_valgrind_target_cmd(args, ["tests/benchmarks"])

    assert "-k" not in cmd


def test_build_valgrind_target_cmd_matches_binary_argument_behavior(tmp_path: Path) -> None:
    args = make_args(tmp_path, binary="/bin/true", sizes=[], valgrind_size=123)

    cmd = pipeline._build_valgrind_target_cmd(args, [])

    assert cmd == ["/bin/true"]


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
