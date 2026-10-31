"""Retain six serial original-workload samples for a registered exact-base source scope.

Invoke from the candidate shared environment with --base-root, --head-root and a
new --output directory. No checkout, dependency installation or cleanup occurs.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
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
    optional_metadata,
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


def invoke_owned(
    name: str,
    command: list[str],
    arm: Path,
    cap: int,
    *,
    output: Path,
    deadline: float,
    attempts: list[dict[str, object]],
    run_owned: Callable[..., dict[str, object]],
    env: dict[str, str],
    check_arms: Callable[[], None],
) -> Path:
    """Retain terminal receipts and reject incomplete commands before advancing."""
    check_arms()
    if time.monotonic() + cap + 60 > deadline:
        raise TimeoutError("Insufficient controller budget for a complete command and receipt.")
    directory = output / name
    directory.mkdir()
    timed = ["/usr/bin/time", "-v", "-o", str(directory / "resource.txt"), *command]
    with (
        (directory / "stdout.txt").open("wb") as stdout,
        (directory / "stderr.txt").open("wb") as stderr,
    ):
        result = run_owned(
            timed,
            timeout=cap - 15,
            cwd=arm,
            env=env,
            stdout=stdout,
            stderr=stderr,
        )
    attempts.append({"name": name, "argv": timed, "cwd": str(arm), "cap_seconds": cap, **result})
    write(directory / "receipt.json", attempts[-1])
    write(output / "attempts.json", attempts)
    if (
        result["exit_code"] != 0
        or result["timeout"]
        or result["descendants_remained"]
        or result["cleanup_complete"] is not True
    ):
        raise RuntimeError("Failed/incomplete command " + name + "; no retries.")
    check_arms()
    return directory


def run(base: Path, head: Path, output: Path, *, scope_base: str = exact.BASE) -> None:
    scope = exact.registered_scope(scope_base)
    started = time.monotonic()
    remaining_job = (
        3600 - (time.time() - float(os.environ["REUSE_JOB_START"])) - 120
        if "REUSE_JOB_START" in os.environ
        else 3300
    )
    deadline = started + min(3300, remaining_job)
    roots = {"base": base.resolve(strict=True), "head": head.resolve(strict=True)}
    output = output.resolve()
    if any(output.is_relative_to(root) for root in roots.values()):
        raise ValueError("Harness and retained outputs must be external to both arms.")
    if platform.system() != "Linux" or roots["base"] == roots["head"] or not __debug__:
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
        != scope.base
    ):
        raise ValueError("Measurement baseline must equal the registered reviewed base.")
    head_revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=head).decode().strip()
    input_digest = canonical_digest(runtime_inputs(head))
    binding = exact.comparison_inputs(
        head, base=scope.base, head_input_digest=input_digest, measured_head=head_revision
    )
    sides = original.input_object(binding["sides"])
    for side, root in roots.items():
        expected = original.input_object(original.input_object(sides[side])["inventory"])
        observed, _ = exact.current_inventory(root, scope_base=scope.base)
        if observed != expected:
            raise ValueError(
                "Physical checkout differs from independently bound " + side + " Git bytes."
            )
    output.mkdir(parents=True, exist_ok=False)
    write(output / "input-binding-before.json", binding)
    dependencies = dependency_identity()
    write(output / "dependencies-before.json", dependencies)
    harness = {p: hashlib.sha256((head / p).read_bytes()).hexdigest() for p in scope.harness}
    if original.input_object(binding["harness"])["head"] != harness:
        raise ValueError("Executing harness differs from the admitted candidate.")
    external_harness = output / "harness"
    external_harness.mkdir()
    for relative in scope.harness:
        target = external_harness / Path(relative).name
        if target.exists():
            raise ValueError("Ambiguous copied harness basename.")
        target.write_bytes((head / relative).read_bytes())
    supervisor_spec = importlib.util.spec_from_file_location(
        "_vyper_source_supervisor", external_harness / "ci_attribution_supervisor.py"
    )
    if supervisor_spec is None or supervisor_spec.loader is None:
        raise ValueError("Cannot load the hash-bound external supervisor.")
    supervisor = importlib.util.module_from_spec(supervisor_spec)
    supervisor_spec.loader.exec_module(supervisor)
    run_owned = cast(Callable[..., dict[str, object]], supervisor.run_owned)
    attempts: list[dict[str, object]] = []
    write(
        output / "host.json",
        {
            "platform": platform.platform(),
            "python": sys.version,
            "cpus": os.cpu_count(),
            "cpuinfo": Path("/proc/cpuinfo").read_text(),
            "meminfo": Path("/proc/meminfo").read_text(),
            "cpu_max": optional_metadata(Path("/sys/fs/cgroup/cpu.max")),
            "memory_max": optional_metadata(Path("/sys/fs/cgroup/memory.max")),
        },
    )

    def check_arms() -> None:
        for arm_side, arm in roots.items():
            actual, _ = exact.current_inventory(arm, scope_base=scope.base)
            expected = original.input_object(original.input_object(sides[arm_side])["inventory"])
            if actual != expected or subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=normal"], cwd=arm
            ):
                raise ValueError("Measured arm source bytes/status drifted: " + arm_side)
        for relative, expected_hash in harness.items():
            if (
                hashlib.sha256((external_harness / Path(relative).name).read_bytes()).hexdigest()
                != expected_hash
            ):
                raise ValueError("External copied harness drifted.")
        if dependency_identity() != dependencies:
            raise ValueError("Installed interpreter/dependencies changed during the campaign.")

    def arm_environment(arm: Path) -> dict[str, str]:
        env = environment()
        env["PYTHONPATH"] = os.pathsep.join((str(arm / "src"), str(arm)))
        env["UV_PROJECT_ENVIRONMENT"] = str(Path(sys.prefix))
        env["UV_NO_SYNC"] = "1"
        return env

    def invoke(name: str, command: list[str], arm: Path, cap: int) -> Path:
        return invoke_owned(
            name,
            command,
            arm,
            cap,
            output=output,
            deadline=deadline,
            attempts=attempts,
            run_owned=run_owned,
            env=arm_environment(arm),
            check_arms=check_arms,
        )

    negatives: list[dict[str, object]] = []
    for side, arm in roots.items():
        proof_directory = output / ("command-proof-" + side)
        command = pytest_command(arm, proof_directory)
        validate_test_command(command, arm, proof_directory, cheap=False)
        for replacement in (
            command[:-1],
            [*command, "--maxfail=1"],
            ["python", *command[1:]],
            [part if part != "--no-cov" else "--cov" for part in command],
        ):
            try:
                validate_test_command(replacement, arm, proof_directory, cheap=False)
            except ValueError:
                negatives.append({"rejected": replacement})
            else:
                raise ValueError("Unsafe original command control was accepted.")
    write(output / "command-preflight.json", {"passed": True, "negative_controls": negatives})
    invoke(
        "cleanup-preflight",
        [
            sys.executable,
            str(external_harness / "check_ci_attribution_supervisor.py"),
            "checks",
            str(output / "cleanup-cases"),
        ],
        external_harness,
        120,
    )
    micro_identity: object = None
    for index, side in enumerate(ORDER):
        invoke(
            f"micro-{index}-{side}",
            [
                str(roots[side] / ".venv/bin/python"),
                "-B",
                str(external_harness / "source_reuse_experiment.py"),
                "micro",
                "--root",
                str(roots[side]),
                "--baseline",
                str(base),
                "--output",
                str(output / f"micro-{index}.json"),
            ],
            roots[side],
            60,
        )
        evidence = json.loads((output / f"micro-{index}.json").read_bytes())
        identity = (evidence["python"], evidence["dependencies"])
        if micro_identity is not None and micro_identity != identity:
            raise ValueError("Actual arm interpreter/dependencies differ.")
        micro_identity = identity
    cheap_directory = output / "cheap-family"
    cheap_command = pytest_command(head, cheap_directory, cheap=True)
    validate_test_command(cheap_command, head, cheap_directory, cheap=True)
    invoke("cheap-family", cheap_command, head, 90)
    family_cases = set(junit_cases(cheap_directory, 24))
    times: dict[str, list[float]] = {"base": [], "head": []}
    generated: dict[str, list[dict[str, str]]] = {"base": [], "head": []}
    for index, side in enumerate(ORDER):
        directory = output / f"original-{index}-{side}"
        command = pytest_command(roots[side], directory)
        validate_test_command(command, roots[side], directory, cheap=False)
        proof_code = (
            "import json,sys; from pathlib import Path; "
            "import warhammer40k_core.build_identity as m; "
            "print(json.dumps({'module':str(Path(m.__file__).resolve()),"
            "'build_id':m.verified_engine_build_identity().build_id,"
            "'prefix':sys.prefix,'executable':sys.executable}))"
        )
        proof_directory = invoke(
            f"import-proof-{index}-{side}",
            [str(roots[side] / ".venv/bin/python"), "-B", "-c", proof_code],
            roots[side],
            60,
        )
        proof = json.loads((proof_directory / "stdout.txt").read_bytes())
        if (
            not Path(proof["module"]).is_relative_to(roots[side] / "src")
            or proof["build_id"] != runtime_id(roots[side])
            or Path(proof["prefix"]).resolve() != Path(sys.prefix).resolve()
        ):
            raise ValueError("Measured process imported another arm/runtime/environment.")
        write(output / f"import-runtime-proof-{index}-{side}.json", proof)
        invoke(directory.name, command, roots[side], 420)
        original_cases = junit_cases(directory, 1)
        if side == "head":
            family_cases.update(original_cases)
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
    if len(family_cases) != 25:
        raise ValueError("Original candidate family set-union differs from 25 cases.")
    if time.monotonic() > deadline:
        raise TimeoutError("Original controller deadline exceeded before completion.")
    after = exact.comparison_inputs(
        head,
        base=scope.base,
        head_input_digest=canonical_digest(runtime_inputs(head)),
        measured_head=head_revision,
    )
    after_dependencies = dependency_identity()
    write(output / "input-binding-after.json", after)
    write(output / "dependencies-after.json", after_dependencies)
    if after != binding or after_dependencies != dependencies:
        raise ValueError("Source, harness or installed dependencies changed during measurements.")
    for side, root in roots.items():
        current, _ = exact.current_inventory(root, scope_base=scope.base)
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
        "base_revision": scope.base,
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
        base=scope.base,
        runtime_id=runtime_id(head),
        input_digest=input_digest,
        family=original.FAMILY,
        specification=original.input_object(specification),
        base_runtime_id=runtime_id(base),
        expected_inputs=expected_inputs,
        expected_binding=binding,
    )
    check_arms()
    if time.monotonic() > deadline:
        raise TimeoutError("Controller deadline exceeded during final validation.")
    write(output / "comparison.json", report)
    write(
        output / "complete.json",
        {
            "complete": True,
            "elapsed": time.monotonic() - started,
            "order": ORDER,
            "original_processes": 6,
            "source_batches": 6,
            "candidate_family_case_union": sorted(family_cases),
            "qualification": (
                "Bounded three-pair original testcase timings; process-tree RSS is max "
                "reported RSS, not concurrent summed RSS. No whole-CI claim."
            ),
        },
    )
    print(
        "Six real samples satisfy unchanged relative budgets and all exact output bindings.",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--head-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scope-base", default=exact.BASE)
    args = parser.parse_args()
    run(args.base_root, args.head_root, args.output, scope_base=args.scope_base)


if __name__ == "__main__":
    main()
