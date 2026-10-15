"""Retain original three-pair tool workload; admit only pinned build-ID output deltas."""

import json
import math
import statistics
import xml.etree.ElementTree as ET

from source_reuse_experiment import (
    ORDER,
    junit_cases,
    pytest_command,
    retained_contract_tree,
    sha,
    validate_test_command,
    write,
)


def run_source_token(roots, harness, output, manifest, invoke):
    identity = None
    for index, side in enumerate(ORDER):
        invoke(
            f"micro-{index}-{side}",
            [
                str(roots[side] / ".venv/bin/python"),
                "-B",
                str(harness / "source_reuse_experiment.py"),
                "micro",
                "--root",
                str(roots[side]),
                "--baseline",
                str(roots["base"]),
                "--output",
                str(output / f"micro-{index}.json"),
            ],
            roots[side],
            60,
        )
        observed = json.loads((output / f"micro-{index}.json").read_bytes())
        current = (observed["python"], observed["dependencies"])
        if identity is not None and current != identity:
            raise ValueError("Source-token interpreter/dependencies differ")
        identity = current
    directory = output / "cheap-family"
    command = pytest_command(roots["head"], directory, cheap=True)
    validate_test_command(command, roots["head"], directory, cheap=True)
    invoke(directory.name, command, roots["head"], 90)
    cases = set(junit_cases(directory, 24))
    trees = {"base": [], "head": []}
    times = {"base": [], "head": []}
    for index, side in enumerate(ORDER):
        directory = output / f"original-{index}-{side}"
        command = pytest_command(roots[side], directory)
        validate_test_command(command, roots[side], directory, cheap=False)
        invoke(directory.name, command, roots[side], 420)
        original_cases = junit_cases(directory, 1)
        if side == "head":
            cases.update(original_cases)
        xml = ET.parse(directory / "junit.xml").findall(".//testcase")
        times[side].append(float(xml[0].attrib["time"]))
        contract = retained_contract_tree(directory / "tmp")
        tree = {
            p.relative_to(contract).as_posix(): sha(p)
            for p in sorted(contract.rglob("*"))
            if p.is_file()
        }
        expected = manifest["sides"][side]["contract_sha256"]
        if tree.keys() != expected.keys():
            raise ValueError("Generated corpus membership differs from bound source")
        for path, digest in tree.items():
            if expected.get(path) != digest:
                raise ValueError(
                    "Generated output differs from reviewed side-specific source: " + path
                )
        if trees[side] and tree != trees[side][0]:
            raise ValueError("Same-arm generated output nondeterminism")
        trees[side].append(tree)
        write(directory / "generated-tree.json", tree)
    if len(cases) != 25:
        raise ValueError("Original candidate family set-union differs from 25 cases")
    before, after = trees["base"][0], trees["head"][0]
    if before.keys() != after.keys():
        raise ValueError("Generated output membership changed")
    changed = {path for path in before if before[path] != after[path]}
    if changed != set(manifest["generated_contract_changed_paths"]):
        raise ValueError("Unexpected cross-arm generated differences")
    # Explicit pre-reviewed per-leaf deltas, not a recursive deletion of hash fields.
    # Expected bytes are checked above on every repetition; identities remain in output.
    expected_changed = {
        path
        for path in manifest["sides"]["base"]["contract_sha256"]
        if path in after
        and manifest["sides"]["base"]["contract_sha256"][path]
        != manifest["sides"]["head"]["contract_sha256"][path]
    }
    if changed != expected_changed:
        raise ValueError("Bound generated identity delta incomplete")
    write(output / "generated-output-binding.json", trees)
    mean_limit = 1.25 * statistics.mean(times["base"]) + 0.05
    max_limit = 1.5 * max(times["base"]) + 0.10
    if not all(math.isfinite(t) and t > 0 for values in times.values() for t in values):
        raise ValueError("Invalid source-token duration")
    passed = statistics.mean(times["head"]) <= mean_limit and max(times["head"]) <= max_limit
    write(
        output / "relative-budgets.json",
        {
            "samples": times,
            "mean_limit": mean_limit,
            "maximum_limit": max_limit,
            "passed": passed,
            "generated_changed_paths": sorted(changed),
            "candidate_family_cases": sorted(cases),
            "qualification": (
                "Three-pair original JUnit timings. Raw evidence requires reviewed "
                "v2 input binding before policy admission."
            ),
        },
    )
    if not passed:
        raise RuntimeError("Original source-token relative budget failed")
