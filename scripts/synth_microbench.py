# scripts/synth_microbench.py
"""Synthesize a perf-benchmark-shaped microbench harness for one target.

The harness imports an agent-authored ``make_input(size)`` and the target
callable, then runs the callable once per invocation. perf-benchmark drives it
with ``--target "python bench_<name>.py {SIZE}"`` and owns all timing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_BENCH_TEMPLATE = '''\
"""Synthesized microbench for {func} (target of perf-benchmark). Do not edit by hand."""
import sys
from pathlib import Path

sys.path.insert(0, {import_root!r})
sys.path.insert(0, str(Path(__file__).resolve().parent))

from make_input import make_input  # agent-authored, same directory
from {module} import {func} as _target


def main() -> None:
    size = int(sys.argv[1])
    data = make_input(size)
    _target(data)


if __name__ == "__main__":
    main()
'''

_MAKE_INPUT_STUB = '''\
"""Agent-authored input generator. Must produce realistic, size-scalable input.

Return whatever single argument ``{func}`` expects, sized by ``size``.
Replace the body below before running the benchmark.
"""


def make_input(size):
    raise NotImplementedError("Author a realistic, scalable input generator for {func}")
'''


def generate(
    *, out_dir: Path, name: str, import_root: Path, module: str, func: str
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bench = out_dir / f"bench_{name}.py"
    make_input = out_dir / "make_input.py"
    bench.write_text(
        _BENCH_TEMPLATE.format(func=func, module=module, import_root=str(import_root)),
        encoding="utf-8",
    )
    make_input.write_text(_MAKE_INPUT_STUB.format(func=func), encoding="utf-8")
    target_command = (
        f"python3 {bench.name} {{SIZE}}"  # python3 for portability (python may be absent)
    )
    spec = {
        "name": name,
        "module": module,
        "func": func,
        "import_root": str(import_root),
        "bench": str(bench),
        "make_input": str(make_input),
        "target_command": target_command,
    }
    (out_dir / "synth_spec.json").write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    return {
        "bench": bench,
        "make_input": make_input,
        "target_command": target_command,
        "spec": spec,
    }


def validate_make_input(
    harness_dir: Path, *, probe_sizes: tuple[int, int] = (256, 1024)
) -> dict[str, Any]:
    """Cheap pre-measurement guard run BEFORE the expensive pipeline.

    Catches the common failure modes early instead of paying for a valgrind run that
    then refuses: (1) the stub was never filled (``NotImplementedError``), (2) ``make_input``
    raises, (3) it does not scale (output size does not grow with ``size``). Returns
    ``{"ok": bool, "reason": str, "sizes": {...}}`` — never raises on user-code errors.
    """
    import importlib.util

    path = Path(harness_dir) / "make_input.py"
    if not path.is_file():
        return {"ok": False, "reason": "make_input.py missing"}
    spec = importlib.util.spec_from_file_location("_synth_make_input", path)
    if spec is None or spec.loader is None:
        return {"ok": False, "reason": "make_input.py not importable"}
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        small, large = probe_sizes
        out_small, out_large = mod.make_input(small), mod.make_input(large)
    except NotImplementedError:
        return {
            "ok": False,
            "reason": "make_input is still the stub (NotImplementedError) — author it",
        }
    except Exception as exc:  # noqa: BLE001 — user code
        return {"ok": False, "reason": f"make_input raised: {exc!r}"}
    try:
        len_small, len_large = len(out_small), len(out_large)
    except TypeError:
        return {
            "ok": True,
            "reason": "non-sized input; cannot verify scaling statically",
            "sizes": None,
        }
    if len_large <= len_small:
        return {
            "ok": False,
            "reason": f"make_input does not scale: {len_small}→{len_large} for {small}→{large}",
            "sizes": {small: len_small, large: len_large},
        }
    return {"ok": True, "reason": "scales", "sizes": {small: len_small, large: len_large}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Synthesize a microbench harness for a target.")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--import-root", required=True, type=Path)
    parser.add_argument("--module", required=True)
    parser.add_argument("--func", required=True)
    args = parser.parse_args(argv)
    res = generate(
        out_dir=args.out_dir,
        name=args.name,
        import_root=args.import_root,
        module=args.module,
        func=args.func,
    )
    print(json.dumps(res["spec"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
