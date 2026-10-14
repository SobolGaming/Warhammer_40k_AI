"""Profile an actual pytest or generator entry point; retain partial timeout evidence."""

from __future__ import annotations

import cProfile
import json
import os
import runpy
import signal
import sys
import time
from pathlib import Path


def validate_request(argv: list[str]) -> tuple[Path, str, list[str]]:
    """Reject malformed argv/source destinations before enabling a profiler or writing."""
    if len(argv) < 2:
        raise ValueError("A profile destination and exact entry point are required")
    destination, target, *arguments = argv
    repository = Path(__file__).resolve().parents[1]
    output = Path(destination).resolve()
    run_output = Path(os.environ["ATTRIBUTION_RUN_OUTPUT"]).resolve()
    if run_output.is_relative_to(repository) or output.parent != run_output:
        raise ValueError(
            "Profile destination must be inside the external invocation output directory"
        )
    if output.suffix != ".prof":
        raise ValueError("Profile destination must have the .prof suffix")
    for path in (Path(destination), output.with_suffix(".status.json")):
        if path.resolve().is_relative_to(repository) or path.exists() or path.is_symlink():
            raise ValueError(f"Refusing tracked-source, existing or symlink profile output: {path}")
    generator = repository / "scripts/build_external_contract.py"
    if target != "pytest" and Path(target).resolve() != generator:
        raise ValueError(f"Unsupported profile target: {target}")
    return output, target, arguments


def main() -> None:
    output, target, arguments = validate_request(sys.argv[1:])
    interrupted = []

    def stop(signum: int, _frame: object) -> None:
        interrupted.append(signum)
        raise SystemExit(124)

    signal.signal(signal.SIGTERM, stop)
    started = time.perf_counter()
    profiler = cProfile.Profile()
    # Match the native entry point's sys.path[0] and argv, including sibling imports.
    sys.path[0] = str(Path.cwd() if target == "pytest" else Path(target).resolve().parent)
    sys.argv = [target, *arguments]
    profiler.enable()
    try:
        if target == "pytest":
            runpy.run_module("pytest", run_name="__main__", alter_sys=True)
        else:
            runpy.run_path(target, run_name="__main__")
    finally:
        profiler.disable()
        profiler.dump_stats(str(output))
        output.with_suffix(".status.json").write_text(
            json.dumps(
                {
                    "target": target,
                    "arguments": arguments,
                    "seconds": time.perf_counter() - started,
                    "interrupt_signals": interrupted,
                    "qualification": (
                        "Raw profile is not a pass receipt; inspect pytest and exit status."
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
