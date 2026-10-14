"""One bounded, external Linux controller; no campaign starts without explicit run mode."""

from __future__ import annotations

import argparse
import ast
import gc
import hashlib
import importlib.metadata
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
from typing import Any, cast

BASE = "22a12094cfe3839d8fe8c5296ec0a7e7d32abade"
NODE = (
    "tests/code_quality/test_phase18m_conformance_boundary.py::"
    "test_external_contract_write_mode_removes_orphan_generated_fixture"
)
FILES = (
    "tests/code_quality/test_proposal_source_index.py",
    "tests/code_quality/test_phase18m_conformance_boundary.py",
    "tests/code_quality/test_decision_submission_catalog.py",
)
ORDER = ("base", "head", "head", "base", "base", "head")


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def optional_metadata(path: Path) -> dict[str, str | None]:
    """Keep optional host-file absence explicit without changing admission checks."""
    try:
        value = path.read_text()
    except OSError as error:
        return {
            "path": str(path),
            "status": "unavailable",
            "value": None,
            "error": type(error).__name__,
            "reason": str(error),
        }
    return {"path": str(path), "status": "available", "value": value, "error": None, "reason": None}


def retained_contract_tree(temporary: Path) -> Path:
    """Accept pytest's current alias only when it resolves to the same owned tree."""
    owned = temporary.resolve(strict=True)
    targets: set[Path] = set()
    for candidate in temporary.glob("*/write-mode-output/contracts"):
        target = candidate.resolve(strict=True)
        if not target.is_dir() or not target.is_relative_to(owned):
            raise ValueError(
                "Retained contract output is not a directory inside the owned tmp root"
            )
        targets.add(target)
    if len(targets) != 1:
        raise ValueError("Expected one distinct retained contracts tree")
    return targets.pop()


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def environment() -> dict[str, str]:
    result = os.environ.copy()
    for key in tuple(result):
        if key.startswith(
            ("PYTHON", "PYTEST", "COVERAGE", "TEST_TIMING", "_WARHAMMER40K_EXTERNAL")
        ):
            del result[key]
    result.update(PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0")
    return result


def scanner(root: Path, *, source_root: Path | None = None) -> Callable[[], tuple[str, ...]]:
    builder = root / "scripts/build_external_contract.py"
    tree = ast.parse(builder.read_text(encoding="utf-8"))
    names = {"_source_paths", "_proposal_kind_tokens", "_string_constant"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in nodes} != names:
        raise ValueError("Actual scanner source owners changed")
    namespace: dict[str, Any] = {
        "ast": ast,
        "Path": Path,
        "SRC_ROOT": (source_root or root) / "src/warhammer40k_core",
    }
    helper = root / "scripts/proposal_source_index.py"
    if helper.exists():
        spec = importlib.util.spec_from_file_location("_reviewed_arm_index", helper)
        if spec is None or spec.loader is None:
            raise ValueError("Cannot load actual arm source index")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        namespace["_PROPOSAL_SOURCE_INDEX"] = module.ProposalSourceIndex()
    exec(
        compile(ast.Module(body=list[ast.stmt](nodes), type_ignores=[]), str(builder), "exec"),
        namespace,
    )
    return cast(Callable[[], tuple[str, ...]], namespace["_proposal_kind_tokens"])


def micro(root: Path, baseline: Path, output: Path) -> None:
    if any(output.resolve().is_relative_to(arm.resolve()) for arm in (root, baseline)):
        raise ValueError("Source-only evidence must be outside both checkouts")
    linux_resource = importlib.import_module("resource")

    if sys.version_info[:3] != (3, 14, 5):
        raise ValueError("Arm interpreter does not match the reviewed Python version")
    oracle = scanner(baseline, source_root=root)()
    rows = []
    for count in (1, 6, 3):
        function = scanner(root)
        gc.collect()  # Retire prior scenario namespaces outside the timed lookup region.
        samples = []
        for _ in range(count):
            cpu, wall = time.process_time(), time.perf_counter()
            tokens = function()
            samples.append({"wall": time.perf_counter() - wall, "cpu": time.process_time() - cpu})
            if tokens != oracle:
                raise ValueError("Token oracle mismatch")
        rows.append({"reads": count, "samples": samples})
    function = scanner(root)
    gc.collect()
    real_parse, calls = ast.parse, []

    def counted(*args: Any, **kwargs: Any) -> ast.Module:
        calls.append(1)
        return cast(ast.Module, real_parse(*args, **kwargs))

    ast.parse = cast(Any, counted)  # Transparent counter preserves the parser's overloaded API.
    try:
        assert function() == oracle
        cold = len(calls)
        assert function() == oracle
        warm = len(calls) - cold
    finally:
        ast.parse = real_parse
    source_count = sum(path.is_file() for path in (root / "src/warhammer40k_core").rglob("*.py"))
    if cold != source_count or warm != (
        0 if (root / "scripts/proposal_source_index.py").exists() else source_count
    ):
        raise ValueError("Actual AST work count differs from declared implementation")
    if any(name.startswith("warhammer40k_core") for name in sys.modules):
        raise ValueError("Microbenchmark imported engine runtime")
    write(
        output,
        {
            "complete": True,
            "scenarios": rows,
            "cold_parses": cold,
            "warm_parses": warm,
            "tokens": oracle,
            "python": sys.version,
            "dependencies": {
                name: importlib.metadata.version(name)
                for name in (
                    "pytest",
                    "pytest-cov",
                    "pytest-xdist",
                    "coverage",
                    "numpy",
                    "shapely",
                    "z3-solver",
                )
            },
            "peak_self_rss_kib": linux_resource.getrusage(linux_resource.RUSAGE_SELF).ru_maxrss,
            "qualification": (
                "Fresh application instances; uncontrolled OS page cache; "
                "instrumented proof excluded from times"
            ),
        },
    )


def check_arm(root: Path, binding: dict[str, Any], side: str) -> None:
    expected = {
        **binding["common"],
        **binding["sides"][side]["implementation"],
        **binding["sides"][side]["control_plane"],
    }
    for relative, expected_hash in expected.items():
        path = root / relative
        actual = sha(path) if path.is_file() else None
        if path.is_symlink() or actual != expected_hash:
            raise ValueError(f"{side} source input drift: {relative}")
    corpus = {
        path.relative_to(root).as_posix() for path in (root / "src").rglob("*.py") if path.is_file()
    }
    expected_corpus = {
        path
        for path, value in expected.items()
        if path.startswith("src/") and path.endswith(".py") and value is not None
    }
    if corpus != expected_corpus:
        raise ValueError("Actual source corpus membership differs from its binding")
    contracts = {
        path.relative_to(root).as_posix()
        for path in (root / "contracts").rglob("*")
        if path.is_file()
    }
    if contracts != {
        path
        for path, value in expected.items()
        if path.startswith("contracts/") and value is not None
    }:
        raise ValueError("Actual copied contract tree differs from its binding")
    if git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError(f"{side} source checkout is not clean")


def pytest_command(root: Path, directory: Path, *, cheap: bool = False) -> list[str]:
    command = [str(root / ".venv/bin/python"), "-B", "-m", "pytest"]
    if cheap:
        command.extend(FILES)
        command.extend(
            ["-k", "not test_external_contract_write_mode_removes_orphan_generated_fixture"]
        )
    else:
        command.append(NODE)
    command.extend(
        [
            "-q",
            "-n",
            "0",
            "--no-cov",
            "--durations=0",
            "--durations-min=0",
            f"--basetemp={directory / 'tmp'}",
            f"--junitxml={directory / 'junit.xml'}",
        ]
    )
    return command


def validate_test_command(command: list[str], root: Path, directory: Path, *, cheap: bool) -> None:
    if command != pytest_command(root, directory, cheap=cheap):
        raise ValueError("Only the exact original or declared cheap pytest command is allowed")


def validate_paths(
    base: Path, head: Path, harness: Path, output: Path, temporary: Path, workspace: Path
) -> None:
    if (base, head, harness, output) != (
        temporary / "reuse-base",
        workspace,
        temporary / "reuse-harness",
        temporary / "source-reuse-output",
    ):
        raise ValueError("Paths are outside the exact isolated workflow destinations")


def junit_cases(directory: Path, count: int) -> list[str]:
    cases = ET.parse(directory / "junit.xml").findall(".//testcase")
    if len(cases) != count or any(
        case.find(tag) is not None for case in cases for tag in ("failure", "error", "skipped")
    ):
        raise ValueError("Original assertion execution count/outcomes changed")
    return [f"{case.attrib['classname']}::{case.attrib['name']}" for case in cases]


def run(args: argparse.Namespace) -> None:
    started = time.monotonic()
    if platform.system() != "Linux" or not __debug__ or os.cpu_count() != 4:
        raise ValueError("Expected native Linux, assertions, four logical CPUs")
    if os.environ.get("GITHUB_RUN_ATTEMPT") != "1":
        raise ValueError("One approved attempt only; no automatic reruns")
    roots = {
        "base": cast(Path, args.base_root).resolve(),
        "head": cast(Path, args.head_root).resolve(),
    }
    output = cast(Path, args.output).resolve()
    harness = Path(__file__).resolve().parent
    validate_paths(
        roots["base"],
        roots["head"],
        harness,
        output,
        Path(os.environ["RUNNER_TEMP"]).resolve(),
        Path(os.environ["GITHUB_WORKSPACE"]).resolve(),
    )
    remaining_job = 3600 - (time.time() - float(os.environ["REUSE_JOB_START"])) - 120
    deadline = started + min(3300, remaining_job)
    if any(output.is_relative_to(root) or harness.is_relative_to(root) for root in roots.values()):
        raise ValueError("Harness and outputs must be external to both checkouts")
    if roots["base"] == roots["head"] or git(roots["base"], "rev-parse", "HEAD") != BASE:
        raise ValueError("Wrong actual PR baseline")
    if git(roots["head"], "rev-parse", "HEAD") != args.expected_head:
        raise ValueError("Candidate revision mismatch")
    binding = json.loads(args.binding.read_bytes())
    if (
        binding["sides"]["base"]["revision"] != BASE
        or binding["sides"]["head"]["revision"] != args.expected_head
    ):
        raise ValueError("Binding revision mismatch")
    for relative, expected in binding["harness"]["head"].items():
        source = roots["head"] / relative
        if sha(source) != expected:
            raise ValueError("Frozen harness drift")
        if relative.endswith(".py") and sha(harness / source.name) != expected:
            raise ValueError("External copied harness differs")
    supervisor_spec = importlib.util.spec_from_file_location(
        "_source_reuse_supervisor", harness / "ci_attribution_supervisor.py"
    )
    if supervisor_spec is None or supervisor_spec.loader is None:
        raise ValueError("Cannot load the hash-verified external supervisor")
    supervisor = importlib.util.module_from_spec(supervisor_spec)
    supervisor_spec.loader.exec_module(supervisor)
    run_owned = cast(Callable[..., dict[str, Any]], supervisor.run_owned)
    output.mkdir(parents=True, exist_ok=False)
    write(output / "binding.json", binding)
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
    for side, root in roots.items():
        check_arm(root, binding, side)
    rows = []

    commands = []
    for side, root in roots.items():
        directory = output / f"command-proof-{side}"
        original = pytest_command(root, directory)
        validate_test_command(original, root, directory, cheap=False)
        for replacement in (
            original[:-1],
            [*original, "--maxfail=1"],
            ["python", *original[1:]],
            [part if part != "--no-cov" else "--cov" for part in original],
        ):
            try:
                validate_test_command(replacement, root, directory, cheap=False)
            except ValueError:
                commands.append({"rejected": replacement})
            else:
                raise ValueError("Unsafe command negative was accepted")
    write(output / "command-preflight.json", {"passed": True, "negative_controls": commands})

    def invoke(name: str, command: list[str], root: Path, cap: int) -> Path:
        if time.monotonic() + cap + 60 > deadline:
            raise TimeoutError(
                "Insufficient controller budget for next complete command and receipt"
            )
        directory = output / name
        directory.mkdir()
        timed = ["/usr/bin/time", "-v", "-o", str(directory / "resource.txt"), *command]
        with (
            (directory / "stdout.txt").open("wb") as stdout,
            (directory / "stderr.txt").open("wb") as stderr,
        ):
            result = run_owned(
                timed, timeout=cap - 15, cwd=root, env=environment(), stdout=stdout, stderr=stderr
            )
        rows.append({"name": name, "argv": timed, "cwd": str(root), "cap_seconds": cap, **result})
        write(directory / "receipt.json", rows[-1])
        write(output / "attempts.json", rows)
        if result["exit_code"] != 0 or result["timeout"] or result["descendants_remained"]:
            raise RuntimeError(f"Failed/incomplete command {name}; no retries")
        for side, arm in roots.items():
            check_arm(arm, binding, side)
        return directory

    invoke(
        "cleanup-preflight",
        [
            sys.executable,
            str(harness / "check_ci_attribution_supervisor.py"),
            "checks",
            str(output / "cleanup-cases"),
        ],
        harness,
        120,
    )
    dependency_identity = None
    for index, side in enumerate(ORDER):
        root = roots[side]
        invoke(
            f"micro-{index}-{side}",
            [
                str(root / ".venv/bin/python"),
                "-B",
                str(Path(__file__).resolve()),
                "micro",
                "--root",
                str(root),
                "--baseline",
                str(roots["base"]),
                "--output",
                str(output / f"micro-{index}.json"),
            ],
            root,
            60,
        )
        evidence = json.loads((output / f"micro-{index}.json").read_bytes())
        identity = (evidence["python"], evidence["dependencies"])
        if dependency_identity is not None and identity != dependency_identity:
            raise ValueError("Actual arm interpreter/dependencies differ")
        dependency_identity = identity
    cheap = output / "cheap-family"
    cheap_command = pytest_command(roots["head"], cheap, cheap=True)
    validate_test_command(cheap_command, roots["head"], cheap, cheap=True)
    invoke("cheap-family", cheap_command, roots["head"], 90)
    family_cases = set(junit_cases(cheap, 24))
    trees: list[dict[str, str]] = []
    for index, side in enumerate(ORDER):
        directory = output / f"original-{index}-{side}"
        command = pytest_command(roots[side], directory)
        validate_test_command(command, roots[side], directory, cheap=False)
        invoke(directory.name, command, roots[side], 420)
        original_cases = junit_cases(directory, 1)
        if side == "head":
            family_cases.update(original_cases)
        contract = retained_contract_tree(directory / "tmp")
        tree = {
            p.relative_to(contract).as_posix(): sha(p)
            for p in sorted(contract.rglob("*"))
            if p.is_file()
        }
        write(directory / "generated-tree.json", tree)
        if trees and tree != trees[0]:
            raise ValueError("Actual base/head generated output tree differs")
        trees.append(tree)
    if time.monotonic() > deadline:
        raise TimeoutError("Controller deadline exceeded before final completion")
    if len(family_cases) != 25:
        raise ValueError("Candidate family set-union inventory differs from 25 cases")
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
                "Bounded three-pair pilot; process-tree resource peak is max reported RSS, "
                "not concurrent summed RSS. No whole-CI claim."
            ),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    modes = parser.add_subparsers(dest="mode", required=True)
    small = modes.add_parser("micro")
    small.add_argument("--root", type=Path, required=True)
    small.add_argument("--baseline", type=Path, required=True)
    small.add_argument("--output", type=Path, required=True)
    campaign = modes.add_parser("run")
    for name in ("base-root", "head-root", "binding", "output"):
        campaign.add_argument(f"--{name}", type=Path, required=True)
    campaign.add_argument("--expected-head", required=True)
    args = parser.parse_args()
    if args.mode == "micro":
        micro(args.root, args.baseline, args.output)
    else:
        try:
            run(args)
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
            destination = cast(Path, args.output).resolve()
            owned = Path(os.environ["RUNNER_TEMP"]).resolve() / "source-reuse-output"
            if destination == owned and destination.is_dir():
                write(
                    destination / "failure.json",
                    {"complete": False, "type": type(error).__name__, "error": str(error)},
                )
            raise


if __name__ == "__main__":
    main()
