from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import stat
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from itertools import product
from pathlib import Path, PurePosixPath
from statistics import median
from typing import TypedDict, cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = REPOSITORY_ROOT / "tests"
EXCLUDED_TEST_DIRECTORIES = {"benchmarks", "code_quality"}
SHARD_STRATEGY = "largest-processing-time-by-derived-selector-weight"


class ProfileEvidence(TypedDict):
    source: str
    junit_sha256: list[str]
    test_cases: int
    test_files: int


@dataclass(frozen=True, slots=True)
class Shard:
    shard_id: int
    duration_seconds: float
    test_files: tuple[str, ...]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build or verify duration-balanced behavioral pytest shard manifests."
    )
    parser.add_argument("--check", action="store_true", help="Verify committed manifests.")
    parser.add_argument(
        "--junit",
        type=Path,
        action="append",
        help="Complete run: XML file or directory of shard XMLs; repeat for medians.",
    )
    parser.add_argument(
        "--profile-source",
        action="append",
        help="Run URL, commit and runner description, one per --junit.",
    )
    parser.add_argument("--shard-count", type=int, default=12)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPOSITORY_ROOT / "ci" / "test_shards",
    )
    args = parser.parse_args()
    if args.shard_count < 1:
        parser.error("--shard-count must be positive")
    output_dir = args.output_dir.resolve()
    if args.check:
        _check_manifests(output_dir=output_dir, shard_count=args.shard_count)
        return 0
    if args.junit is None:
        parser.error("--junit is required unless --check is used")
    if args.profile_source is None or len(args.profile_source) != len(args.junit):
        parser.error("one --profile-source is required per --junit")
    durations, profiles = _profile_medians(tuple(args.junit), tuple(args.profile_source))
    durations = _rounded_durations(_partitioned_durations(durations))
    shards = _balanced_shards(durations=durations, shard_count=args.shard_count)
    _write_manifests(output_dir=output_dir, shards=shards, durations=durations, profiles=profiles)
    return 0


CUTOVER_PATH = "data/source_audits/ci64_provenance_v1/test-cutover.json"
CUTOVER_BASE = "5734eace50abe8fe99bbe46282652e4ab3c021b4"
CUTOVER_TREE = "29eb413bb3c6c698c7f12a74e96b373e1084fd46"
CUTOVER_LEDGER_SHA256 = "207e59b1e4f56c209ca35f1839823a3dfa94e0ad71e231334549b3ce74945217"
RETIRED_TEST_COUNT = 92
RETIRED_TEST_PATHS_SHA256 = "a60c2ab82c17e8703ae1faec743b8b1ff463094252e4249876cb7cca14800bf0"
RETIRED_TEST_ROWS_SHA256 = "30ce81d57e4fe404dfac0de28662f1ae428d716a29ef095d711f520a4315ad46"
ACTIVE_TEST_ROOTS = ("tests/rules", "tests/factions", "tests/infrastructure", "tests/performance")
RETAINED_ACTIVE_FILES = (
    "tests/unit/test_dice.py",
    "tests/unit/test_phase10i_terrain_movement.py",
)


@dataclass(frozen=True, slots=True)
class BehavioralSelection:
    active_files: tuple[str, ...]
    inactive_files: tuple[str, ...]
    quality_files: tuple[str, ...]
    benchmark_files: tuple[str, ...]
    manifest_sha256: str

    def check_explicit(self, root: Path, arguments: tuple[str, ...]) -> None:
        """Reject explicit quarantined files; pytest otherwise bypasses ignore lists."""
        for argument in arguments:
            name = argument.split("::", 1)[0]
            path = Path(name)
            if ".." in path.parts:
                raise SystemExit("Test selector must not contain parent aliases: " + name)
            candidate = path if path.is_absolute() else root / path
            _selection_no_links(root, candidate)
            if candidate.is_dir():
                if candidate != root and not candidate.is_relative_to(root / "tests"):
                    raise SystemExit("Test selector escaped tests: " + name)
                continue
            relative = candidate.relative_to(root).as_posix()
            if relative in self.inactive_files:
                raise SystemExit("Explicit inactive legacy test is quarantined: " + relative)
            if relative not in (*self.active_files, *self.quality_files, *self.benchmark_files):
                raise SystemExit("Explicit test is outside the declared cutover: " + relative)


def _selection_no_links(root: Path, path: Path) -> None:
    if not path.is_relative_to(root):
        raise SystemExit("Test selection escaped repository: " + str(path))
    for member in (path, *path.parents):
        if member == root:
            break
        if member.is_symlink():
            raise SystemExit("Test selection contains a symlink alias: " + str(member))


def _selection_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise SystemExit("Duplicate cutover field: " + key)
        value[key] = item
    return value


def _selection_members(
    value: object, root: Path, *, current: dict[str, dict[str, object]] | None = None
) -> dict[str, dict[str, object]]:
    if not isinstance(value, dict) or not value:
        raise SystemExit("Cutover members must be a nonempty object.")
    result: dict[str, dict[str, object]] = {}
    for name, item in value.items():
        if (
            not isinstance(name, str)
            or name != PurePosixPath(name).as_posix()
            or PurePosixPath(name).is_absolute()
            or ".." in PurePosixPath(name).parts
            or "\\" in name
            or ":" in name
            or not name.startswith("tests/")
            or not PurePosixPath(name).name.startswith("test_")
            or not name.endswith(".py")
            or not isinstance(item, dict)
            or item.keys() != {"mode", "blob_sha1", "sha256", "bytes"}
            or item["mode"] not in {"100644", "100755"}
            or type(item["bytes"]) is not int
            or item["bytes"] < 0
        ):
            raise SystemExit("Malformed cutover member: " + str(name))
        for key, size in (("sha256", 64), ("blob_sha1", 40)):
            token = item[key]
            if (
                not isinstance(token, str)
                or len(token) != size
                or set(token) - set("0123456789abcdef")
            ):
                raise SystemExit("Malformed cutover digest: " + name)
        path = root / name
        _selection_no_links(root, path)
        if not path.is_file():
            raise SystemExit("Missing declared cutover member: " + name)
        observed = item if current is None else current.get(name, item)
        raw = path.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False)
        if (
            len(raw) != observed["bytes"]
            or hashlib.sha256(raw).hexdigest() != observed["sha256"]
            or blob.hexdigest() != observed["blob_sha1"]
        ):
            raise SystemExit("Cutover member bytes changed: " + name)
        if os.name != "nt" and bool(path.stat().st_mode & 0o100) != (observed["mode"] == "100755"):
            raise SystemExit("Cutover member mode changed: " + name)
        result[name] = item
    if len({name.casefold() for name in result}) != len(result):
        raise SystemExit("Case aliases in cutover membership.")
    return result


def _selection_retirements(root: Path, value: object, native: object) -> frozenset[str]:
    """Fresh exact tombstones and owned native text archives; no virtual live bytes."""
    if not isinstance(value, list) or not isinstance(native, dict):
        raise SystemExit("Retirement data must be an exact list over the native ledger.")
    paths: list[str] = []
    rows: dict[str, object] = {}
    for row in value:
        if (
            not isinstance(row, dict)
            or row.keys() != {"path", "archive", "native"}
            or not isinstance(row["path"], str)
            or not isinstance(row["archive"], str)
        ):
            raise SystemExit("Malformed finite retirement row.")
        name = row["path"]
        if name in rows or name not in native or row["native"] != native[name]:
            raise SystemExit("Retirement native membership or identity changed.")
        archive = "data/source_audits/ci64_provenance_v1/retired-tests/" + name + ".txt"
        if row["archive"] != archive:
            raise SystemExit("Retirement archive path is not the exact owned location.")
        paths.append(name)
        rows[name] = row["native"]
    if (
        paths != sorted(paths)
        or len(paths) != RETIRED_TEST_COUNT
        or hashlib.sha256(json.dumps(paths, separators=(",", ":")).encode()).hexdigest()
        != RETIRED_TEST_PATHS_SHA256
        or hashlib.sha256(
            json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        != RETIRED_TEST_ROWS_SHA256
    ):
        raise SystemExit("Approved finite retirement set changed.")
    for row in value:
        name = row["path"]
        path = root / name
        _selection_no_links(root, path)
        if path.exists() or path.is_symlink():
            raise SystemExit("Retired test path reappeared: " + name)
        archive = root / row["archive"]
        _selection_no_links(root, archive)
        try:
            resolved_before = archive.resolve(strict=True)
            before = archive.lstat()
        except FileNotFoundError as error:
            raise SystemExit("Retirement archive is missing before acquisition.") from error
        if resolved_before != archive:
            raise SystemExit("Retirement archive has a physical path alias.")
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or (os.name != "nt" and before.st_mode & 0o111)
        ):
            raise SystemExit("Retirement archive must be an owned regular non-executable file.")
        fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        before_identity = tuple(getattr(before, name) for name in fields)
        try:
            stream = archive.open("rb")
        except FileNotFoundError as error:
            raise SystemExit("Retirement archive disappeared before open.") from error
        with stream:
            opened = os.fstat(stream.fileno())
            opened_identity = tuple(getattr(opened, name) for name in fields)
            # Windows lstat/fstat ctime meanings can differ: compare it only within
            # the same API. All remaining ownership/identity fields must agree.
            if opened_identity[:-1] != before_identity[:-1]:
                raise SystemExit("Retirement archive handle identity differs from its path.")
            raw = stream.read()
            finished = os.fstat(stream.fileno())
            if tuple(getattr(finished, name) for name in fields) != opened_identity:
                raise SystemExit("Retirement archive changed while its handle was open.")
        _selection_no_links(root, archive)
        try:
            resolved_after = archive.resolve(strict=True)
            after = archive.lstat()
        except FileNotFoundError as error:
            raise SystemExit("Retirement archive disappeared during acquisition.") from error
        if resolved_after != archive:
            raise SystemExit("Retirement archive physical path changed during acquisition.")
        if tuple(getattr(after, name) for name in fields) != before_identity:
            raise SystemExit("Retirement archive path identity changed during acquisition.")
        expected = row["native"]
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False)
        if (
            len(raw) != expected["bytes"]
            or hashlib.sha256(raw).hexdigest() != expected["sha256"]
            or blob.hexdigest() != expected["blob_sha1"]
        ):
            raise SystemExit("Retirement archive differs from authentic native bytes: " + name)
    return frozenset(paths)


def deferred_comparison_cases(value: object) -> tuple[str, ...]:
    """The owner's finite PR591 comparison exception, not behavioral deselection."""
    if not isinstance(value, dict):
        raise SystemExit("Invalid comparison deferral record.")
    nodes = value["deferred_quality_cases"]
    if (
        value["comparison_disposition"] != "deferred"
        or not isinstance(nodes, list)
        or len(nodes) != 260
        or not all(isinstance(node, str) for node in nodes)
        or nodes != sorted(set(nodes))
        or hashlib.sha256(
            json.dumps(nodes, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        != "e419ac241cf7908e138b1bd78289a523416bddd51cb65a5356c60e6763d167c7"
    ):
        raise SystemExit("Comparison deferral differs from the approved 260 quality cases.")
    ledger = {
        name: value[name]
        for name in (
            "source_base",
            "active_roots",
            "native_active_files",
            "retained_active_files",
            "inactive_legacy_files",
            "benchmark_files",
        )
    }
    if (
        hashlib.sha256(
            json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        != CUTOVER_LEDGER_SHA256
    ):
        raise SystemExit("Comparison deferral changed the native behavioral ledger.")
    coverage = value["coverage"]
    if (
        coverage["metric"] != "coverage.py total with branch=true"
        or coverage["source"] != ["warhammer40k_core"]
        or type(coverage["current_floor"]) is not int
        or coverage["current_floor"] != 64
    ):
        raise SystemExit("Comparison deferral changed full-package branch coverage.")
    return tuple(nodes)


def validate_acts_inactive_source(root: Path) -> None:
    """Authenticate the single reviewed inactive API successor independently of its ledger."""
    exact = {
        "tests/unit/test_phase17g_adepta_sororitas_army_rule.py": (
            "cb7c48432f4c26fc42af074122e3cf2a377f9892aa9bb8eac9a2188ffd985362"
        ),
        "docs/performance/policy-v3/acts-provenance-20261031/inactive-acts-predecessor.py.txt": (
            "c4fe28349415081f36acaf612cd6715d8a383c6892e70830ad1bcc1d6a4e968e"
        ),
        "docs/performance/policy-v3/acts-provenance-20261031/inactive-acts-api-recipe.json": (
            "7206bee260fe831e3c9626042dd4e7954dea5e074590a32f9cb40cd6161e82fa"
        ),
    }
    for relative, expected in exact.items():
        target = root / relative
        _selection_no_links(root, target)
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise SystemExit("Acts inactive API successor/preimage changed.")


def behavioral_selection(root: Path) -> BehavioralSelection:
    """Fresh finite cutover admission shared by pytest and shard discovery."""
    root = root.resolve(strict=True)
    path = root / CUTOVER_PATH
    _selection_no_links(root, path)
    raw = path.read_bytes()
    value = json.loads(raw, object_pairs_hook=_selection_object)
    fields = {
        "schema",
        "source_base",
        "active_roots",
        "active_files",
        "retained_active_files",
        "inactive_legacy_files",
        "inactive_updates",
        "native_active_files",
        "benchmark_files",
        "retirements",
        "coverage",
        "comparison_disposition",
        "deferred_quality_cases",
    }
    if (
        not isinstance(value, dict)
        or value.keys() != fields
        or value["schema"] != "finite-test-cutover-v1"
    ):
        raise SystemExit("Invalid finite test cutover schema.")
    deferred_comparison_cases(value)
    if value["source_base"] != {"commit": CUTOVER_BASE, "tree": CUTOVER_TREE}:
        raise SystemExit("Test cutover source authority changed.")
    if value["active_roots"] != list(ACTIVE_TEST_ROOTS):
        raise SystemExit("Test cutover roots or approved retirement set changed.")
    expected_coverage = {
        "metric": "coverage.py total with branch=true",
        "source": ["warhammer40k_core"],
        "current_floor": 64,
        "restoration_floor": 85,
        "restoration_condition": (
            "post-merge rebuild until complete selected behavioral coverage meets85; then restore85"
        ),
    }
    if (
        value["coverage"] != expected_coverage
        or type(value["coverage"]["current_floor"]) is not int
        or type(value["coverage"]["restoration_floor"]) is not int
    ):
        raise SystemExit("Test cutover coverage authority changed.")
    ledger_fields = (
        "source_base",
        "active_roots",
        "native_active_files",
        "retained_active_files",
        "inactive_legacy_files",
        "benchmark_files",
    )
    ledger = {name: value[name] for name in ledger_fields}
    if (
        hashlib.sha256(
            json.dumps(ledger, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        != CUTOVER_LEDGER_SHA256
    ):
        raise SystemExit("Native behavioral classification ledger changed.")
    if not isinstance(value["native_active_files"], dict):
        raise SystemExit("Native active file ledger must be an object.")
    active = _selection_members(value["active_files"], root)
    if not value["native_active_files"].keys() <= active.keys():
        raise SystemExit("A native active Core/regression file was omitted.")
    retained = _selection_members(value["retained_active_files"], root)
    updates = value["inactive_updates"]
    allowed_updates = {
        "tests/unit/test_phase17g_adepta_sororitas_army_rule.py": "acts-turn-api-maintenance-v1",
        "tests/unit/test_phase15c_fight_order.py": "add-pending-decision-requests-v1",
        "tests/unit/test_phase13b_shooting_declarations.py": "add-pending-decision-requests-v1",
        "tests/integration/test_embarked_ability_authority.py": "type-only-battle-phase-cast-v1",
        "tests/unit/test_phase18e_server_api.py": "type-only-server-session-test-access-v1",
    }
    if not isinstance(updates, dict) or set(updates) - allowed_updates.keys():
        raise SystemExit("Inactive update membership changed.")
    current: dict[str, dict[str, object]] = {}
    for name, update in updates.items():
        if (
            not isinstance(update, dict)
            or update.keys() != {"before", "after", "recipe"}
            or update["recipe"] != allowed_updates[name]
            or not isinstance(value["inactive_legacy_files"], dict)
            or update["before"] != value["inactive_legacy_files"].get(name)
        ):
            raise SystemExit("Inactive update native preimage/recipe changed.")
        current.update(_selection_members({name: update["after"]}, root))
    if "tests/unit/test_phase17g_adepta_sororitas_army_rule.py" in current:
        validate_acts_inactive_source(root)
    retired = _selection_retirements(root, value["retirements"], value["inactive_legacy_files"])
    if current.keys() & retired:
        raise SystemExit("A retired test cannot also carry a live inactive update.")
    present_inactive = {
        name: row for name, row in value["inactive_legacy_files"].items() if name not in retired
    }
    inactive = _selection_members(present_inactive, root, current=current)
    inactive.update({name: value["inactive_legacy_files"][name] for name in retired})
    benchmarks = _selection_members(value["benchmark_files"], root)
    if tuple(sorted(retained)) != RETAINED_ACTIVE_FILES or any(
        active.get(n) != row for n, row in retained.items()
    ):
        raise SystemExit("Retained active regression files changed.")
    if set(active) & set(inactive) or (set(active) | set(inactive)) & set(benchmarks):
        raise SystemExit("Cutover status memberships overlap.")
    if any(
        not any(name.startswith(prefix + "/") for prefix in ACTIVE_TEST_ROOTS)
        and name not in retained
        for name in active
    ):
        raise SystemExit("Active file is outside approved roots and retained files.")
    if any(
        not name.startswith(("tests/unit/", "tests/integration/", "tests/replay/"))
        for name in inactive
    ):
        raise SystemExit("Inactive file is outside the finite legacy roots.")
    if any(not name.startswith("tests/benchmarks/") for name in benchmarks):
        raise SystemExit("Measurement file is outside benchmark root.")
    found: set[str] = set()
    tests_root = root / "tests"
    _selection_no_links(root, tests_root)
    for directory, directories, filenames in os.walk(tests_root, followlinks=False):
        base = Path(directory)
        for entry in directories:
            _selection_no_links(root, base / entry)
        for filename in filenames:
            if filename.endswith("_test.py") and not filename.startswith("test_"):
                raise SystemExit("Undeclared alternate pytest naming: " + str(base / filename))
            if filename.startswith("test_") and filename.endswith(".py"):
                member = base / filename
                _selection_no_links(root, member)
                found.add(member.relative_to(root).as_posix())
    quality = {name for name in found if name.startswith("tests/code_quality/")}
    declared = set(active) | (set(inactive) - retired) | set(benchmarks) | quality
    if found != declared:
        raise SystemExit("Cutover test membership changed: " + repr(sorted(found ^ declared)))
    if len({name.casefold() for name in found}) != len(found):
        raise SystemExit("Case aliases in physical test membership.")
    for name in ACTIVE_TEST_ROOTS:
        if not (root / name).is_dir():
            raise SystemExit("Missing active test root: " + name)
    for name in retired:
        path = root / name
        _selection_no_links(root, path)
        if path.exists() or path.is_symlink():
            raise SystemExit("Retired test path reappeared before admission closed: " + name)
    return BehavioralSelection(
        tuple(sorted(active)),
        tuple(sorted(inactive)),
        tuple(sorted(quality)),
        tuple(sorted(benchmarks)),
        hashlib.sha256(raw).hexdigest(),
    )


def _behavioral_test_files() -> tuple[str, ...]:
    return behavioral_selection(REPOSITORY_ROOT).active_files


CASE_PARTITION_PATH = "ci/test_shards/case-partitions.json"
CASE_PARTITION_FILE = "tests/rules/rules04/unit/test_s25_permission_relevance.py"
CASE_PARTITION_SHA256 = "be09d3680ac4ac47c248a1962b24846a3791824821c14a5a4080f5cab8b73c07"


def _literal_partition_nodes(root: Path) -> tuple[str, ...]:
    path = root / CASE_PARTITION_FILE
    _selection_no_links(root, path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CASE_PARTITION_SHA256:
        raise SystemExit("Finite case partition source changed; regeneration/review required.")
    module = ast.parse(raw.decode(), filename=CASE_PARTITION_FILE)
    functions = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]
    if (
        len(functions) != 1
        or functions[0].name != "test_normal_native_relevant_operations_and_owned_selected_sources"
    ):
        raise SystemExit("Finite case partition test function changed.")
    function = functions[0]
    if len(function.decorator_list) != 2:
        raise SystemExit("Finite case partition decorators changed.")
    axes: list[tuple[str, ...]] = []
    for decorator, name, count in zip(
        reversed(function.decorator_list), ("mode", "player"), (10, 2), strict=True
    ):
        if (
            not isinstance(decorator, ast.Call)
            or ast.unparse(decorator.func) != "pytest.mark.parametrize"
            or len(decorator.args) != 2
            or decorator.keywords
            or not isinstance(decorator.args[0], ast.Constant)
            or decorator.args[0].value != name
            or not isinstance(decorator.args[1], ast.List)
        ):
            raise SystemExit("Only the reviewed literal parameter axes are admitted.")
        values: list[str] = []
        for value in decorator.args[1].elts:
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                raise SystemExit("Partition parameters must be literal strings.")
            values.append(value.value)
        if len(values) != count or len(set(values)) != count:
            raise SystemExit("Partition parameter count or uniqueness changed.")
        axes.append(tuple(values))
    nodes = tuple(
        CASE_PARTITION_FILE + "::" + function.name + "[" + "-".join(row) + "]"
        for row in product(*axes)
    )
    if len(nodes) != 20 or len(set(nodes)) != 20:
        raise SystemExit("Finite partition must contain exactly twenty unique nodes.")
    return nodes


def worksteal_relevance_order(nodeids: tuple[str, ...], *, workers: int) -> tuple[int, ...]:
    """Start the finite expensive S25 cases on distinct existing worker chunks.

    Worksteal initially sends floor(remaining / remaining workers) consecutive
    items. Adjacent expensive cases otherwise become an unstealable serial tail.
    Keep both relative orders and leave every other collection untouched.
    """
    original = tuple(range(len(nodeids)))
    heavy = tuple(
        index for index, node in enumerate(nodeids) if node.startswith(CASE_PARTITION_FILE + "::")
    )
    if workers != 4 or not 1 <= len(heavy) <= workers or len(nodeids) < 2 * workers:
        return original
    declared = frozenset(_literal_partition_nodes(REPOSITORY_ROOT))
    if any(nodeids[index] not in declared for index in heavy):
        raise SystemExit("Worksteal relevance ordering requires declared finite cases.")
    ordinary = iter(index for index in original if index not in heavy)
    ordered: list[int] = []
    for worker in range(workers):
        count = (len(nodeids) - len(ordered)) // (workers - worker)
        first = (heavy[worker],) if worker < len(heavy) else ()
        ordered.extend(first)
        ordered.extend(next(ordinary) for _ in range(count - len(first)))
    return tuple(ordered)


def _case_partition(root: Path, files: frozenset[str]) -> dict[str, float]:
    if CASE_PARTITION_FILE not in files:
        return {}
    path = root / CASE_PARTITION_PATH
    _selection_no_links(root, path)
    value = json.loads(path.read_bytes(), object_pairs_hook=_selection_object)
    fields = {"schema", "source_file", "source_sha256", "nodes", "weights", "evidence"}
    if (
        not isinstance(value, dict)
        or value.keys() != fields
        or value["schema"] != "finite-behavior-node-partition-v1"
        or value["source_file"] != CASE_PARTITION_FILE
        or value["source_sha256"] != CASE_PARTITION_SHA256
    ):
        raise SystemExit("Finite node partition schema or source identity changed.")
    nodes = _literal_partition_nodes(root)
    if (
        value["nodes"] != list(nodes)
        or not isinstance(value["weights"], dict)
        or value["weights"].keys() != set(nodes)
    ):
        raise SystemExit("Finite node partition is not the complete exact literal inventory.")
    result: dict[str, float] = {}
    for node in nodes:
        weight = value["weights"][node]
        if (
            isinstance(weight, bool)
            or not isinstance(weight, int | float)
            or not math.isfinite(weight)
            or weight <= 0
        ):
            raise SystemExit("Finite partition weights must be positive finite scheduling values.")
        result[node] = float(weight)
    evidence = value["evidence"]
    if (
        not isinstance(evidence, dict)
        or evidence.get("purpose")
        != "Derived scheduling weights only; not current performance or full-suite qualification"
    ):
        raise SystemExit("Finite partition must retain its scheduling-only evidence label.")
    return result


def _behavioral_shard_selectors() -> tuple[str, ...]:
    files = frozenset(_behavioral_test_files())
    partition = _case_partition(REPOSITORY_ROOT, files)
    return (
        tuple(sorted((files - {CASE_PARTITION_FILE}) | partition.keys()))
        if partition
        else tuple(sorted(files))
    )


def _partitioned_durations(durations: dict[str, float]) -> dict[str, float]:
    """Preserve file totals; node ratios are derived scheduling weights, not case profiles."""
    partition = _case_partition(REPOSITORY_ROOT, frozenset(durations))
    if not partition:
        return dict(durations)
    result = dict(durations)
    total = result.pop(CASE_PARTITION_FILE)
    denominator = sum(partition.values())
    result.update({node: total * weight / denominator for node, weight in partition.items()})
    return result


def _profile_medians(
    paths: tuple[Path, ...],
    sources: tuple[str, ...],
) -> tuple[dict[str, float], tuple[ProfileEvidence, ...]]:
    if not paths or len(paths) != len(sources) or any(not source.strip() for source in sources):
        raise SystemExit("Each complete JUnit run requires a non-empty source description.")
    profiles: list[ProfileEvidence] = []
    measurements: list[dict[str, float]] = []
    for path, source in zip(paths, sources, strict=True):
        durations, hashes, case_count = _read_junit_profile(path)
        measurements.append(durations)
        profiles.append(
            ProfileEvidence(
                source=source,
                junit_sha256=list(hashes),
                test_cases=case_count,
                test_files=len(durations),
            )
        )
    return (
        {name: median(run[name] for run in measurements) for name in measurements[0]},
        tuple(profiles),
    )


def _durations_from_junit(junit_path: Path) -> dict[str, float]:
    return _read_junit_profile(junit_path)[0]


def _read_junit_profile(junit_path: Path) -> tuple[dict[str, float], tuple[str, ...], int]:
    paths = tuple(sorted(junit_path.rglob("*.xml"))) if junit_path.is_dir() else (junit_path,)
    if not paths or any(not path.is_file() for path in paths):
        raise SystemExit(f"JUnit profile does not exist or is empty: {junit_path}")
    durations: dict[str, float] = {}
    seen: set[tuple[str, str, str]] = set()
    hashes: list[str] = []
    expected = frozenset(_behavioral_test_files())
    for path in paths:
        content = path.read_bytes()
        hashes.append(hashlib.sha256(content).hexdigest())
        root = ET.fromstring(content)
        for suite in root.iter("testsuite"):
            declared = suite.get("tests")
            if (
                declared is None
                or not declared.isdecimal()
                or int(declared) != len(list(suite.iter("testcase")))
            ):
                raise SystemExit(f"JUnit suite testcase count is missing or drifted: {path}")
        for testcase in root.iter("testcase"):
            if any(testcase.find(tag) is not None for tag in ("failure", "error", "skipped")):
                raise SystemExit(f"JUnit profile contains unsuccessful cases: {path}")
            duration_text = testcase.get("time")
            if duration_text is None:
                raise SystemExit("Every JUnit testcase must contain a time attribute.")
            test_file = _test_file_from_testcase(testcase, expected=expected)
            name = testcase.get("name")
            if not name:
                raise SystemExit("Every JUnit testcase must have a non-empty name.")
            identity = (test_file, testcase.get("classname", ""), name)
            if identity in seen:
                raise SystemExit(f"Duplicate JUnit testcase: {identity}")
            seen.add(identity)
            try:
                duration = float(duration_text)
            except ValueError as error:
                raise SystemExit(
                    f"JUnit testcase has an invalid duration: {duration_text}"
                ) from error
            if not math.isfinite(duration) or duration < 0.0:
                raise SystemExit(
                    f"JUnit testcase duration must be finite and non-negative: {duration_text}"
                )
            durations[test_file] = durations.get(test_file, 0.0) + duration
    missing = sorted(set(expected) - set(durations))
    unexpected = sorted(set(durations) - set(expected))
    if missing or unexpected:
        raise SystemExit(_coverage_error(missing=missing, unexpected=unexpected))
    return durations, tuple(sorted(hashes)), len(seen)


def _test_file_from_testcase(
    testcase: ET.Element,
    *,
    expected: frozenset[str],
) -> str:
    file_attribute = testcase.get("file")
    if file_attribute is not None:
        normalized = file_attribute.replace("\\", "/")
        file_path = PurePosixPath(normalized)
        if file_path.is_absolute() or ".." in file_path.parts:
            raise SystemExit(f"JUnit testcase file is not repository-relative: {file_attribute}")
        test_file = file_path.as_posix()
        if test_file not in expected:
            raise SystemExit(f"JUnit testcase file is not a behavioral test: {file_attribute}")
        return test_file

    classname = testcase.get("classname")
    if classname is None:
        raise SystemExit("Every JUnit testcase must contain a file or classname attribute.")
    classname_parts = classname.split(".")
    for part_count in range(len(classname_parts), 0, -1):
        candidate = "/".join(classname_parts[:part_count]) + ".py"
        if candidate in expected:
            return candidate
    raise SystemExit(f"JUnit testcase classname does not identify a behavioral test: {classname}")


def _rounded_durations(durations: dict[str, float]) -> dict[str, float]:
    return {path: round(duration, 3) for path, duration in durations.items()}


def _balanced_shards(*, durations: dict[str, float], shard_count: int) -> tuple[Shard, ...]:
    assignments: list[list[str]] = [[] for _ in range(shard_count)]
    totals = [0.0] * shard_count
    for test_file, duration in sorted(durations.items(), key=lambda item: (-item[1], item[0])):
        shard_index = min(range(shard_count), key=lambda index: (totals[index], index))
        assignments[shard_index].append(test_file)
        totals[shard_index] += duration
    return tuple(
        Shard(
            shard_id=index + 1,
            duration_seconds=totals[index],
            test_files=tuple(sorted(assignments[index])),
        )
        for index in range(shard_count)
    )


def _write_manifests(
    *,
    output_dir: Path,
    shards: tuple[Shard, ...],
    durations: dict[str, float],
    profiles: tuple[ProfileEvidence, ...] = (),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale_manifest in output_dir.glob("shard-*.txt"):
        stale_manifest.unlink()
    for shard in shards:
        manifest_path = output_dir / f"shard-{shard.shard_id}.txt"
        manifest_path.write_text("\n".join(shard.test_files) + "\n", encoding="utf-8", newline="\n")
    summary = _summary_payload(shards=shards, durations=durations, profiles=profiles)
    (output_dir / "durations.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _check_manifests(output_dir=output_dir, shard_count=len(shards))


def _check_manifests(*, output_dir: Path, shard_count: int) -> None:
    expected = set(_behavioral_shard_selectors())
    manifest_names = {path.name for path in output_dir.glob("shard-*.txt")}
    if manifest_names != {f"shard-{index}.txt" for index in range(1, shard_count + 1)}:
        raise SystemExit("Shard manifest count does not match --shard-count.")
    seen: dict[str, int] = {}
    manifest_entries: dict[int, tuple[str, ...]] = {}
    for shard_id in range(1, shard_count + 1):
        manifest_path = output_dir / f"shard-{shard_id}.txt"
        if not manifest_path.is_file():
            raise SystemExit(f"Missing shard manifest: {manifest_path}")
        entries = tuple(
            line.strip()
            for line in manifest_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if entries != tuple(sorted(entries)):
            raise SystemExit(f"Shard manifest must be sorted: {manifest_path}")
        manifest_entries[shard_id] = entries
        for entry in entries:
            seen[entry] = seen.get(entry, 0) + 1

    missing = sorted(expected - set(seen))
    unexpected = sorted(set(seen) - expected)
    duplicates = sorted(path for path, count in seen.items() if count != 1)
    if missing or unexpected or duplicates:
        detail = _coverage_error(missing=missing, unexpected=unexpected)
        if duplicates:
            detail += "\nDuplicate test files:\n" + "\n".join(duplicates)
        raise SystemExit(detail)

    summary_path = output_dir / "durations.json"
    if not summary_path.is_file():
        raise SystemExit(f"Missing shard duration summary: {summary_path}")
    try:
        summary: object = json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"Shard duration summary is not valid JSON: {summary_path}") from error
    durations = _summary_durations(summary=summary, expected=expected)
    shards = _balanced_shards(durations=durations, shard_count=shard_count)
    for shard in shards:
        if manifest_entries[shard.shard_id] != shard.test_files:
            manifest_path = output_dir / f"shard-{shard.shard_id}.txt"
            raise SystemExit(
                f"Shard manifest does not match the duration-balanced assignment: {manifest_path}"
            )
    profiles = _summary_profiles(summary)
    expected_summary = _summary_payload(shards=shards, durations=durations, profiles=profiles)
    if summary != expected_summary:
        raise SystemExit("Shard duration summary does not match the committed manifests.")


def _summary_payload(
    *,
    shards: tuple[Shard, ...],
    durations: dict[str, float],
    profiles: tuple[ProfileEvidence, ...] = (),
) -> dict[str, object]:
    return {
        "strategy": SHARD_STRATEGY,
        "profiles": list(profiles),
        "shard_count": len(shards),
        "total_test_duration_seconds": round(sum(durations.values()), 3),
        "files": {path: round(duration, 3) for path, duration in sorted(durations.items())},
        "shards": [
            {
                "shard_id": shard.shard_id,
                "duration_seconds": round(shard.duration_seconds, 3),
                "test_file_count": len(shard.test_files),
            }
            for shard in shards
        ],
    }


def _summary_profiles(summary: object) -> tuple[ProfileEvidence, ...]:
    if not isinstance(summary, dict) or not isinstance(summary.get("profiles"), list):
        raise SystemExit("Shard summary requires profile evidence.")
    profiles = cast(list[object], summary["profiles"])
    for item in profiles:
        if not isinstance(item, dict) or set(item) != {
            "source",
            "junit_sha256",
            "test_cases",
            "test_files",
        }:
            raise SystemExit("Shard profile evidence fields are invalid.")
        if not isinstance(item["source"], str) or not item["source"].strip():
            raise SystemExit("Shard profile requires a source description.")
        hashes = item["junit_sha256"]
        if (
            not isinstance(hashes, list)
            or not hashes
            or any(
                not isinstance(value, str)
                or len(value) != 64
                or set(value) - set("0123456789abcdef")
                for value in hashes
            )
        ):
            raise SystemExit("Shard profile requires SHA-256 report identities.")
        if any(type(item[key]) is not int or item[key] < 1 for key in ("test_cases", "test_files")):
            raise SystemExit("Shard profile requires positive inventory counts.")
    return tuple(cast(ProfileEvidence, item) for item in profiles)


def _summary_durations(*, summary: object, expected: set[str]) -> dict[str, float]:
    if not isinstance(summary, dict):
        raise SystemExit("Shard duration summary must be a JSON object.")
    summary_fields = cast(dict[str, object], summary)
    files_value = summary_fields.get("files")
    if not isinstance(files_value, dict):
        raise SystemExit("Shard duration summary must contain a files object.")
    files = cast(dict[object, object], files_value)
    durations: dict[str, float] = {}
    for path, duration in files.items():
        if not isinstance(path, str):
            raise SystemExit("Shard duration summary file paths must be strings.")
        if isinstance(duration, bool) or not isinstance(duration, int | float):
            raise SystemExit(f"Shard duration for {path} must be numeric.")
        normalized_duration = float(duration)
        if not math.isfinite(normalized_duration) or normalized_duration < 0.0:
            raise SystemExit(f"Shard duration for {path} must be finite and non-negative.")
        durations[path] = normalized_duration

    measured = set(durations)
    missing = sorted(expected - measured)
    unexpected = sorted(measured - expected)
    if missing or unexpected:
        raise SystemExit(_coverage_error(missing=missing, unexpected=unexpected))
    return durations


def _coverage_error(*, missing: list[str], unexpected: list[str]) -> str:
    details = ["Behavioral test shard coverage is not exact."]
    if missing:
        details.append("Missing test files:\n" + "\n".join(missing))
    if unexpected:
        details.append("Unexpected test files:\n" + "\n".join(unexpected))
    return "\n".join(details)


if __name__ == "__main__":
    raise SystemExit(main())
