"""Run unchanged seven-sample reconstruction driver with one common workload tree."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workload", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "linux" or not __debug__ or sys.version_info[:3] != (3, 14, 5):
        raise ValueError("Reviewed Linux interpreter and enabled assertions required")
    workload, runtime, output = (
        args.workload.resolve(),
        args.runtime.resolve(),
        args.output.resolve(),
    )
    if output.is_relative_to(workload) or output.is_relative_to(runtime):
        raise ValueError("Evidence must be outside both source trees")
    sys.path.insert(0, str(workload))
    from scripts import measure_ingress_reconstruction as driver

    if Path(driver.__file__).resolve() != workload / "scripts/measure_ingress_reconstruction.py":
        raise ValueError("Wrong workload driver imported")
    if any(
        name == "warhammer40k_core" or name.startswith("warhammer40k_core.") for name in sys.modules
    ):
        raise ValueError("Runtime imported before arm selection")
    driver._select_runtime_src(runtime / "src")
    import warhammer40k_core
    from warhammer40k_core.build_identity import verified_engine_build_identity

    if Path(warhammer40k_core.__file__).resolve() != runtime / "src/warhammer40k_core/__init__.py":
        raise ValueError("Wrong runtime package imported")
    identity = verified_engine_build_identity().build_id
    sys.argv = [
        str(Path(driver.__file__)),
        "--output",
        str(output / "raw.json"),
        "--revision",
        args.revision,
        "--runtime-src",
        str(runtime / "src"),
        "--samples",
        "7",
    ]
    outcomes = {}
    original_prepare = driver.prepare

    def record_prepared_outcome(checkpoint):
        session = original_prepare(checkpoint)
        if checkpoint in outcomes:
            raise ValueError("Unexpected duplicate preparation")
        # Original sample checks restored/source equality and distinct lifecycle/state.
        # No extra restore/alias/replay cycle is introduced.
        outcomes[checkpoint] = fingerprint(session.lifecycle.to_payload())
        return session

    driver.prepare = record_prepared_outcome
    driver.main()
    raw = json.loads((output / "raw.json").read_bytes())
    expected = {
        (checkpoint, operation)
        for checkpoint in driver.CHECKPOINTS
        for operation in driver.OPERATIONS
    }
    if {(r["checkpoint"], r["operation"]) for r in raw["rows"]} != expected:
        raise ValueError("Reconstruction hard-case membership changed")
    for row in raw["rows"]:
        if len(row["samples"]) != 7 or not all(
            s["complete"] is True and s["seconds"] > 0 and not s["work_counts"]
            for s in row["samples"]
        ):
            raise ValueError("Uninstrumented original seven samples required")
        if row["profile"]["complete"] is not True or not row["profile"]["work_counts"]:
            raise ValueError("Original separate profiled work-count sample required")

    if set(outcomes) != set(driver.CHECKPOINTS):
        raise ValueError("Prepared outcomes incomplete")
    write(
        output / "semantic.json",
        {
            "complete": True,
            "runtime_build_id": identity,
            "outcomes": outcomes,
            "python": sys.version,
            "platform": platform.platform(),
            "dependencies": {
                n: importlib.metadata.version(n)
                for n in (
                    "pytest",
                    "shapely",
                    "numpy",
                    "orjson",
                    "msgspec",
                    "pydantic",
                    "z3-solver",
                )
            },
            "qualification": (
                "Original timed samples unchanged; preparation fingerprint and original separate "
                "profile excluded. Original fresh-state and full-payload checks retained. "
                "No extra alias/Fight diagnostic or full-game claim."
            ),
        },
    )


if __name__ == "__main__":
    main()
