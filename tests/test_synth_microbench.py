# tests/test_synth_microbench.py
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import synth_microbench as sm  # noqa: E402


def test_generate_writes_runnable_harness_and_stub(tmp_path):
    # a target module to benchmark
    pkg = tmp_path / "src"
    pkg.mkdir()
    (pkg / "algo.py").write_text("def find_max(data):\n    return max(data)\n", encoding="utf-8")
    out = tmp_path / "perf" / "find_max"
    paths = sm.generate(
        out_dir=out,
        name="find_max",
        import_root=pkg,
        module="algo",
        func="find_max",
    )
    assert paths["bench"].exists()
    assert paths["make_input"].exists()
    # the stub must be present and raise until the agent fills it
    assert "NotImplementedError" in paths["make_input"].read_text()

    # fill make_input so the harness is runnable, then run it for a size
    paths["make_input"].write_text(
        "def make_input(size):\n    return list(range(size))\n", encoding="utf-8"
    )
    proc = subprocess.run(
        [sys.executable, str(paths["bench"]), "1000"],
        capture_output=True,
        text=True,
        cwd=str(out),
    )
    assert proc.returncode == 0, proc.stderr


def test_target_command_uses_size_placeholder(tmp_path):
    out = tmp_path / "perf" / "x"
    paths = sm.generate(out_dir=out, name="x", import_root=tmp_path, module="m", func="f")
    assert "{SIZE}" in paths["target_command"]
    assert paths["bench"].name in paths["target_command"]


def test_validate_make_input_flags_unfilled_stub(tmp_path):
    out = tmp_path / "perf" / "x"
    sm.generate(out_dir=out, name="x", import_root=tmp_path, module="m", func="f")
    res = sm.validate_make_input(out)  # stub still raises NotImplementedError
    assert res["ok"] is False and "stub" in res["reason"].lower()


def test_validate_make_input_flags_non_scaling(tmp_path):
    out = tmp_path / "perf" / "x"
    sm.generate(out_dir=out, name="x", import_root=tmp_path, module="m", func="f")
    (out / "make_input.py").write_text(
        "def make_input(size):\n    return [0, 1, 2]\n", encoding="utf-8"
    )
    res = sm.validate_make_input(out)
    assert res["ok"] is False and "scale" in res["reason"].lower()


def test_validate_make_input_accepts_scaling(tmp_path):
    out = tmp_path / "perf" / "x"
    sm.generate(out_dir=out, name="x", import_root=tmp_path, module="m", func="f")
    (out / "make_input.py").write_text(
        "def make_input(size):\n    return list(range(size))\n", encoding="utf-8"
    )
    res = sm.validate_make_input(out)
    assert res["ok"] is True
