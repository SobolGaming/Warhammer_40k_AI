"""Retain six serial original-workload samples for the exact Vyper source change.

Invoke from the candidate shared environment with --base-root, --head-root and a
new --output directory. No checkout, dependency installation or cleanup occurs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import cast

from tools import performance_tool_inputs as original
from tools import performance_tool_inputs_v4 as exact
from tools.performance_policy import POLICY, canonical_digest, runtime_inputs, validate_comparison

from scripts.quality_evidence import dependency_identity
from scripts.source_reuse_experiment import (
    ORDER,
    environment,
    junit_cases,
    pytest_command,
    retained_contract_tree,
    validate_test_command,
)


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def runtime_id(root: Path) -> str:
    return str(
        json.loads((root / "src/warhammer40k_core/_engine_build_manifest.json").read_bytes())[
            "build_id"
        ]
    )


def run(base: Path, head: Path, output: Path) -> None:
    roots = {"base": base.resolve(strict=True), "head": head.resolve(strict=True)}
    if roots["base"] == roots["head"] or not __debug__:
        raise ValueError("Two independent checkouts and Python assertions are required.")
    if output.exists():
        raise ValueError("Retained evidence requires a new output directory.")
    for root in roots.values():
        if (root / ".venv/bin/python").resolve(strict=True) != Path(sys.executable).resolve(
            strict=True
        ):
            raise ValueError("Both arms must use the same existing interpreter.")
        if subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=normal"], cwd=root
        ):
            raise ValueError("Measurements require clean committed source checkouts.")
    if (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=base).decode().strip()
        != exact.BASE
    ):
        raise ValueError("Measurement baseline must be exact PR600 main.")
    head_revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=head).decode().strip()
    input_digest = canonical_digest(runtime_inputs(head))
    binding = exact.comparison_inputs(
        head, base=exact.BASE, head_input_digest=input_digest, measured_head=head_revision
    )
    sides = original.input_object(binding["sides"])
    for side, root in roots.items():
        expected = original.input_object(original.input_object(sides[side])["inventory"])
        observed, _ = exact.current_inventory(root)
        if observed != expected:
            raise ValueError(
                "Physical checkout differs from independently bound " + side + " Git bytes."
            )
    output.mkdir(parents=True, exist_ok=False)
    write(output / "input-binding-before.json", binding)
    dependencies = dependency_identity()
    write(output / "dependencies-before.json", dependencies)
    harness = {p: hashlib.sha256((head / p).read_bytes()).hexdigest() for p in exact.HARNESS}
    if original.input_object(binding["harness"])["head"] != harness:
        raise ValueError("Executing harness differs from the admitted candidate.")
    times: dict[str, list[float]] = {"base": [], "head": []}
    generated: dict[str, list[dict[str, str]]] = {"base": [], "head": []}
    for index, side in enumerate(ORDER):
        directory = output / f"original-{index}-{side}"
        directory.mkdir()
        command = pytest_command(roots[side], directory)
        validate_test_command(command, roots[side], directory, cheap=False)
        env = environment()
        env["PYTHONPATH"] = os.pathsep.join((str(roots[side] / "src"), str(roots[side])))
        env["UV_PROJECT_ENVIRONMENT"] = str(Path(sys.prefix))
        env["UV_NO_SYNC"] = "1"
        proof_code = (
            "import json,sys; from pathlib import Path; "
            "import warhammer40k_core.build_identity as m; "
            "print(json.dumps({'module':str(Path(m.__file__).resolve()),"
            "'build_id':m.verified_engine_build_identity().build_id,"
            "'prefix':sys.prefix,'executable':sys.executable}))"
        )
        proof = json.loads(
            subprocess.check_output(
                [str(roots[side] / ".venv/bin/python"), "-B", "-c", proof_code],
                cwd=roots[side],
                env=env,
            )
        )
        if (
            not Path(proof["module"]).is_relative_to(roots[side] / "src")
            or proof["build_id"] != runtime_id(roots[side])
            or Path(proof["prefix"]).resolve() != Path(sys.prefix).resolve()
        ):
            raise ValueError("Measured process imported another arm/runtime/environment.")
        write(directory / "import-runtime-proof.json", proof)
        write(
            directory / "command.json",
            {
                "argv": command,
                "cwd": str(roots[side]),
                "timeout_seconds": 420,
                "coverage": False,
                "concurrency": 1,
            },
        )
        started = time.monotonic()
        with (directory / "output.log").open("wb") as stream:
            completed = subprocess.run(
                command,
                cwd=roots[side],
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=420,
                check=False,
            )
        write(
            directory / "exit.json",
            {"returncode": completed.returncode, "process_seconds": time.monotonic() - started},
        )
        completed.check_returncode()
        junit_cases(directory, 1)
        cases = ET.parse(directory / "junit.xml").findall(".//testcase")
        times[side].append(float(cases[0].attrib["time"]))
        tree = retained_contract_tree(directory / "tmp")
        actual = {
            p.relative_to(tree).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(tree.rglob("*"))
            if p.is_file()
        }
        expected_inventory = original.input_object(original.input_object(sides[side])["inventory"])
        expected_tree = {
            p.removeprefix("contracts/"): value
            for p, value in expected_inventory.items()
            if p.startswith("contracts/")
        }
        if actual != expected_tree:
            raise ValueError("Generated output differs from the complete bound " + side + " tree.")
        generated[side].append(actual)
        write(directory / "generated-tree.json", actual)
        print(
            f"{index + 1}/6 {side}: {times[side][-1]:.3f}s; complete generated tree verified",
            flush=True,
        )
    after = exact.comparison_inputs(
        head,
        base=exact.BASE,
        head_input_digest=canonical_digest(runtime_inputs(head)),
        measured_head=head_revision,
    )
    after_dependencies = dependency_identity()
    write(output / "input-binding-after.json", after)
    write(output / "dependencies-after.json", after_dependencies)
    if after != binding or after_dependencies != dependencies:
        raise ValueError("Source, harness or installed dependencies changed during measurements.")
    for side, root in roots.items():
        current, _ = exact.current_inventory(root)
        if current != original.input_object(original.input_object(sides[side])["inventory"]):
            raise ValueError("Measured checkout changed during samples: " + side)
    host = {
        "cpu": platform.processor() or platform.machine(),
        "memory_bytes": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"),
        "logical_cpus": os.cpu_count(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "role": "provisional",
    }
    common = cast(dict[str, str], binding["common"])
    expected_inputs = {
        "lock_sha256": common["uv.lock"],
        "workload_sha256": common[original.WORKLOAD],
        "fixture_sha256": str(binding["common_sha256"]),
    }
    report: dict[str, object] = {
        "policy": POLICY,
        "family": original.FAMILY,
        "workload_id": original.WORKLOAD_ID,
        "base_revision": exact.BASE,
        "head_runtime_build_id": runtime_id(head),
        "head_input_digest": input_digest,
        "budget_profile": "current-change-relative-v1",
        "historical_failures": [],
        "input_binding": binding,
        "generated_output_binding": generated,
    }
    for side, root in roots.items():
        report[side] = {
            "runtime_build_id": runtime_id(root),
            "host": host,
            **expected_inputs,
            "samples": {"orphan-write-independent-check": times[side]},
            "completed": True,
            "concurrency": 1,
            "coverage": False,
        }
    specification = original.input_object(
        original.input_object(json.loads((head / original.MAP_PATH).read_bytes()))["families"]
    )[original.FAMILY]
    validate_comparison(
        report,
        base=exact.BASE,
        runtime_id=runtime_id(head),
        input_digest=input_digest,
        family=original.FAMILY,
        specification=original.input_object(specification),
        base_runtime_id=runtime_id(base),
        expected_inputs=expected_inputs,
        expected_binding=binding,
    )
    write(output / "comparison.json", report)
    print(
        "Six real samples satisfy unchanged relative budgets and all exact output bindings.",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--head-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.base_root, args.head_root, args.output)


if __name__ == "__main__":
    main()
