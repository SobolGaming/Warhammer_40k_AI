"""Exact category relocation applicability; original measured identities remain intact."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import cast

from tools import performance_reconstruction_campaign as reconstruction
from tools import performance_tool_inputs as original
from tools import performance_tool_inputs_v2 as fresh

BASE = reconstruction.BASE
MEASURED = "241f413ce9b83586d0aff4fd87ce50f8157c0163"
TREE = "c5c4ebc8a211888e6ed76594bd4cd48907368240"
ARCHIVE = "docs/performance/policy-v3/category-migration-20261015"
INVENTORY_SHA = "018f9b0167c57e63dfbeabe2418096ab4d60f6270dbc6cc4d966aeef8b7c2154"
EXTERNAL = "EXTERNAL_READS.json.txt"
EXTERNAL_SHA = "0c80ce5afe982667d0c665d70ad3895ab5d3793b0b987d5c3c9ba7a5b29fd9da"
ASSESSMENT_MAP = "docs/performance/policy-v3/category-assessment-map-20261015"
ASSESSMENT_MAP_SHA = "8d208df61242cabad2357158c161ae47aa67d8682275b7a181740faf166ee0ef"
# Bind only after independent source review and the separate implementation commit.
# Its sole permitted post-freeze source change is this None-to-commit literal.
SOURCE_COMMIT: str | None = None
SELF = "tools/performance_category_migration.py"
CONTROLS = frozenset(
    {
        SELF,
        "scripts/check_performance_policy.py",
        "tests/code_quality/test_performance_category_migration.py",
        "tests/category_migration_preservation.py",
        "tests/code_quality/test_category_migration_preservation.py",
        "tests/code_quality/test_phase14a_source_identity.py",
        "tools/core_rules_order95_audit.py",
    }
)
SOURCE_ARCHIVES = frozenset(
    {
        "docs/performance/policy-v3/ci-compatibility-20261015/order97-original.py.txt",
        "docs/performance/policy-v3/ci-compatibility-20261015/phase14a-original.py.txt",
    }
)


def applies(*, base: str, runtime_id: str, family: str) -> bool:
    """Retained archive presence cannot capture a later PR's comparison route."""
    return (
        base == BASE
        and runtime_id == reconstruction.RUNTIME
        and family in {"reconstruction", original.FAMILY}
    )


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("Migration evidence requires an object.")
    result = cast(dict[object, object], value)
    if not all(isinstance(key, str) for key in result):
        raise ValueError("Migration evidence requires string keys.")
    return cast(dict[str, object], result)


def _strings(value: object) -> dict[str, str]:
    result = _object(value)
    if not all(isinstance(v, str) for v in result.values()):
        raise ValueError("Migration inventories require string hashes.")
    return cast(dict[str, str], result)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read(root: Path, name: str) -> bytes:
    path = root / name
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Migration input must be an owned regular file: " + name)
    return path.read_bytes()


def _git(root: Path, *args: str, payload: bytes | None = None) -> bytes:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={root.as_posix()}", *args],
        cwd=root,
        input=payload,
        timeout=60,
    )


def _selected(path: str) -> bool:
    return path.startswith(("src/", "tests/", "scripts/", "tools/", "contracts/")) or path in (
        original.CONTROL | original.REQUIRED | fresh.SELECTED
    )


def _policy_selected(path: str) -> bool:
    return path.startswith(
        ("src/", "tests/", "scripts/", "tools/", "contracts/schemas/")
    ) or path in {
        "uv.lock",
        "pyproject.toml",
        original.MAP_PATH,
    }


def _external_selected(path: str) -> bool:
    return path == "docs/DECISION_SUBMISSION_CATALOG.md" or path.startswith(
        "conformance/typescript/"
    )


def measured_snapshot(root: Path, revision: str, *, external_reads: bool = False) -> dict[str, str]:
    entries: dict[str, str] = {}
    for row in _git(root, "ls-tree", "-r", "-z", revision).decode().split("\0"):
        if not row:
            continue
        metadata, path = row.split("\t", 1)
        if path == original.SPEC_ARCHIVE:
            path = original.SPEC_PATH
        if _external_selected(path) if external_reads else _selected(path):
            mode, kind, oid = metadata.split()
            if mode not in {"100644", "100755"} or kind != "blob" or path in entries:
                raise ValueError("Invalid or duplicate measured Git member.")
            entries[path] = oid
    paths = sorted(entries)
    raw = _git(
        root, "cat-file", "--batch", payload="".join(entries[p] + "\n" for p in paths).encode()
    )
    result: dict[str, str] = {}
    offset = 0
    for path in paths:
        boundary = raw.index(b"\n", offset)
        oid, kind, length = raw[offset:boundary].decode().split()
        start, end = boundary + 1, boundary + 1 + int(length)
        if oid != entries[path] or kind != "blob" or raw[end : end + 1] != b"\n":
            raise ValueError("Measured Git payload is incomplete or changed.")
        result[path] = _digest(raw[start:end])
        offset = end + 1
    if offset != len(raw):
        raise ValueError("Trailing measured Git payload.")
    return result


def read_archive(root: Path) -> dict[str, object]:
    raw = _read(root, ARCHIVE + "/INVENTORY.json.txt")
    if _digest(raw) != INVENTORY_SHA:
        raise ValueError("Pinned migration inventory changed.")
    inventory = _strings(json.loads(raw))
    if {p.name for p in (root / ARCHIVE).iterdir()} != set(inventory) | {
        "INVENTORY.json.txt",
        EXTERNAL,
    }:
        raise ValueError("Migration archive membership changed.")
    result: dict[str, object] = {}
    for name, digest in inventory.items():
        if Path(name).name != name:
            raise ValueError("Invalid migration archive member.")
        member = _read(root, ARCHIVE + "/" + name)
        if _digest(member) != digest:
            raise ValueError("Pinned migration archive member changed: " + name)
        result[name] = json.loads(member)
    external = _read(root, ARCHIVE + "/" + EXTERNAL)
    if _digest(external) != EXTERNAL_SHA:
        raise ValueError("Independent external-read proof changed.")
    result[EXTERNAL] = json.loads(external)
    return result


def verify_external_reads(root: Path, proof: dict[str, object]) -> str:
    """Supplement historical metadata; never rewrite the selected input inventories."""
    if (
        proof.get("schema") != "retrospective-external-read-identity-v1"
        or proof.get("base_revision") != BASE
        or proof.get("measured_revision") != MEASURED
    ):
        raise ValueError("External-read proof belongs to another cohort.")
    for side, revision in (("base", BASE), ("measured", MEASURED)):
        if measured_snapshot(root, revision, external_reads=True) != proof[side]:
            raise ValueError("Frozen external-read Git identities changed.")
    expected = _strings(proof["measured"])
    if proof["current_at_preparation"] != expected:
        raise ValueError("External-read preparation does not preserve the measured bytes.")
    names = set(
        _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
        .decode()
        .split("\0")
    ) - {""}
    selected = {name for name in names if _external_selected(name) and (root / name).exists()}
    # The live cheap-family consumer reads *.ts even when Git ignores the file.
    selected.update(
        p.relative_to(root).as_posix()
        for p in (root / "conformance/typescript/src").rglob("*.ts")
        if p.is_file() or p.is_symlink()
    )
    if selected != expected.keys():
        raise ValueError("External-read current membership changed.")
    current = {name: _digest(_read(root, name)) for name in sorted(selected)}
    if current != expected:
        raise ValueError("External-read current bytes changed.")
    return original.digest({"proof_sha256": EXTERNAL_SHA, "current": current})


def reviewed_control_hashes(root: Path) -> dict[str, str]:
    if SOURCE_COMMIT is None:
        raise ValueError("Migration adapter awaits its reviewed source commit binding.")
    if len(SOURCE_COMMIT) != 40 or any(c not in "0123456789abcdef" for c in SOURCE_COMMIT):
        raise ValueError("Invalid migration source commit binding.")
    _git(root, "merge-base", "--is-ancestor", SOURCE_COMMIT, "HEAD")
    marker = b"\nSOURCE_COMMIT: str | None = None"
    bound = f'\nSOURCE_COMMIT: str | None = "{SOURCE_COMMIT}"'.encode()
    archive_root = root / "docs/performance/policy-v3/ci-compatibility-20261015"
    if {
        path.relative_to(root).as_posix()
        for path in archive_root.rglob("*")
        if path.is_file() or path.is_symlink()
    } != SOURCE_ARCHIVES:
        raise ValueError("Reviewed compatibility archive membership changed.")
    result: dict[str, str] = {}
    for path in sorted(CONTROLS | SOURCE_ARCHIVES):
        raw = _git(root, "show", SOURCE_COMMIT + ":" + path)
        if path == SELF:
            if raw.count(marker) != 1:
                raise ValueError("Source snapshot is not the reviewed unactivated implementation.")
            raw = raw.replace(marker, bound, 1)
        if _read(root, path) != raw:
            raise ValueError("Reviewed adapter control bytes changed: " + path)
        if path in CONTROLS:
            result[path] = _digest(raw)
    return result


def current_tool_inventory(root: Path) -> dict[str, str]:
    names = set(
        _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
        .decode()
        .split("\0")
    ) - {""}
    names.update(
        p.relative_to(root).as_posix() for p in (root / "src").rglob("*.py") if p.is_file()
    )
    names.update(
        p.relative_to(root).as_posix() for p in (root / "contracts").rglob("*") if p.is_file()
    )
    if (root / original.SPEC_ARCHIVE).exists():
        names.add(original.SPEC_PATH)
    result: dict[str, str] = {}
    for name in sorted(names):
        if _selected(name):
            actual = original.SPEC_ARCHIVE if name == original.SPEC_PATH else name
            if (root / actual).exists() or (root / actual).is_symlink():
                result[name] = _digest(_read(root, actual))
    return result


def verify_current_inventory(
    root: Path,
    *,
    archive: dict[str, object],
    current: dict[str, str],
    tools: dict[str, str],
    controls: dict[str, str],
) -> None:
    """Controls come only from reviewed_control_hashes in the production entry point."""
    if controls.keys() != CONTROLS:
        raise ValueError("Exact adapter control cohort required.")
    measured = _strings(archive["POLICY_MEASURED_INPUTS.json.txt"])
    expected = _strings(archive["POLICY_CURRENT_INPUTS.json.txt"])
    deltas = {
        name: {"before": measured.get(name), "after": expected.get(name)}
        for name in measured.keys() | expected.keys()
        if measured.get(name) != expected.get(name)
    }
    if len(deltas) != 296 or deltas != archive["EXACT_INPUT_DELTAS.json.txt"]:
        raise ValueError("Exact296 migration deltas changed.")
    if current != expected | controls:
        raise ValueError("Current policy inputs differ from the finite migration cohort.")
    if tools != _strings(archive["TOOL_CURRENT_INPUTS.json.txt"]) | controls:
        raise ValueError("Current tool inputs differ from the finite migration cohort.")
    files = _strings(archive["MIGRATION_FILES.json.txt"])
    for name, digest in files.items():
        # Only the exact independently frozen control cohort can supersede its
        # own historical bytes. The original migration inventory stays immutable.
        if _digest(_read(root, name)) != controls.get(name, digest):
            raise ValueError("Reviewed migration source/data changed: " + name)
    deletions = archive["MIGRATION_DELETIONS.json.txt"]
    if not isinstance(deletions, list):
        raise TypeError("Migration deletions require a list.")
    for name in cast(list[str], deletions):
        if (root / name).exists() or (root / name).is_symlink():
            raise ValueError("Deleted original collector reappeared: " + name)
    prefix = "data/source_audits/category_migration/"
    members = {
        p.relative_to(root).as_posix()
        for p in (root / prefix).rglob("*")
        if p.is_file() or p.is_symlink()
    }
    if members != {p for p in files if p.startswith(prefix)}:
        raise ValueError("Migration preservation data membership changed.")
    from tests.category_migration_preservation import MIGRATED_PATHS, verify_migrated_test

    if len(MIGRATED_PATHS) != 68:
        raise ValueError("Migration preservation cohort changed.")
    for name in sorted(MIGRATED_PATHS):
        verify_migrated_test(root, name)


def assessment_map_inputs(
    root: Path,
    *,
    archive: dict[str, object],
    current: dict[str, str],
    tools: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Relate only the pinned metadata additions to the unchanged measured map."""
    members = {"original-operation-map.json.txt", "assessment-map-additions.json.txt"}
    if {p.name for p in (root / ASSESSMENT_MAP).iterdir()} != members:
        raise ValueError("Assessment map proof membership changed.")
    proof_raw = _read(root, ASSESSMENT_MAP + "/assessment-map-additions.json.txt")
    if _digest(proof_raw) != ASSESSMENT_MAP_SHA:
        raise ValueError("Pinned assessment map proof changed.")
    proof = _object(json.loads(proof_raw))
    if proof.keys() != {"schema", "original_sha256", "current_sha256", "added_operations"}:
        raise ValueError("Assessment map proof fields changed.")
    if proof["schema"] != "exact-ci-restructure-operation-map-additions-v1":
        raise ValueError("Assessment map proof schema changed.")
    old_sha = _strings(archive["POLICY_CURRENT_INPUTS.json.txt"])[original.MAP_PATH]
    old_raw = _read(root, ASSESSMENT_MAP + "/original-operation-map.json.txt")
    if proof["original_sha256"] != old_sha or _digest(old_raw) != old_sha:
        raise ValueError("Original measured operation map changed.")
    live_raw = _read(root, original.MAP_PATH)
    live_sha = _digest(live_raw)
    if proof["current_sha256"] != live_sha:
        raise ValueError("Current operation map differs from its exact proof.")
    if current.get(original.MAP_PATH) != live_sha or tools.get(original.MAP_PATH) != live_sha:
        raise ValueError("Actual operation map input identities disagree.")
    old_map = _object(json.loads(old_raw))
    old_operations = _object(old_map["operations"])
    additions = _object(proof["added_operations"])
    if additions.keys() & old_operations.keys():
        raise ValueError("Existing operation cannot be replaced by an addition.")
    expected = old_map | {"operations": old_operations | additions}
    if _object(json.loads(live_raw)) != expected:
        raise ValueError("Original operations, families or budgets changed.")
    # The complete pinned additions were independently reviewed as exact literal
    # infrastructure paths/owners. No report-provided roles or wildcard exemption.
    return (
        current | {original.MAP_PATH: old_sha},
        tools | {original.MAP_PATH: old_sha},
    )


def retained_inputs(
    root: Path,
    *,
    current: dict[str, str],
    report: dict[str, object],
    base: str,
    runtime_id: str,
) -> tuple[dict[str, str], dict[str, object] | None, str]:
    """Authenticate current source independently, then validate original measured evidence."""
    family = report.get("family")
    if (
        base != BASE
        or runtime_id != reconstruction.RUNTIME
        or family
        not in {
            "reconstruction",
            original.FAMILY,
        }
    ):
        raise ValueError("Migration applicability belongs to another exact cohort.")
    archive = read_archive(root)
    external_receipt = verify_external_reads(root, _object(archive[EXTERNAL]))
    controls = reviewed_control_hashes(root)
    tool_inputs = current_tool_inventory(root)
    verified_current, verified_tools = assessment_map_inputs(
        root, archive=archive, current=current, tools=tool_inputs
    )
    verify_current_inventory(
        root, archive=archive, current=verified_current, tools=verified_tools, controls=controls
    )
    _git(root, "merge-base", "--is-ancestor", MEASURED, "HEAD")
    if _git(root, "rev-parse", MEASURED + "^{tree}").decode().strip() != TREE:
        raise ValueError("Original measured tree changed.")
    measured_tool = measured_snapshot(root, MEASURED)
    if measured_tool != archive["TOOL_MEASURED_INPUTS.json.txt"]:
        raise ValueError("Original measured Git inputs changed.")
    measured = _strings(archive["POLICY_MEASURED_INPUTS.json.txt"])
    if {p: v for p, v in measured_tool.items() if _policy_selected(p)} != measured:
        raise ValueError("Original measured policy input inventory changed.")
    binding: dict[str, object] | None = None
    if family == "reconstruction":
        measured, historical_receipt = reconstruction.retained_inputs(
            root, current=measured, report=report, base=base, runtime_id=runtime_id
        )
    else:
        before = measured_snapshot(root, BASE)
        if before != archive["TOOL_BASE_INPUTS.json.txt"]:
            raise ValueError("Actual PR base input inventory changed.")
        harness = {p: measured_tool[p] for p in fresh.HARNESS}
        binding = fresh.classify_inputs(
            spec=_object(archive["MEASURED_ROLE_SPEC.json.txt"]),
            base=before,
            head=measured_tool,
            base_revision=BASE,
            head_revision=MEASURED,
            head_input_digest=original.digest(measured),
            harness_base=harness,
            harness_head=harness,
        )
        if binding != archive["MEASURED_BINDING.json.txt"]:
            raise ValueError("Original measured binding changed.")
        original.validate_binding(observed=report.get("input_binding"), expected=binding)
        historical_receipt = original.digest(binding)
    receipt = original.digest(
        {
            "schema": "exact-category-migration-applicability-v1",
            "base": BASE,
            "migration_snapshot_head": MEASURED,
            "migration_snapshot_tree": TREE,
            "measured_head": reconstruction.MEASURED if family == "reconstruction" else MEASURED,
            "measured_tree": reconstruction.TREE if family == "reconstruction" else TREE,
            "source_commit": SOURCE_COMMIT,
            "current_policy_digest": original.digest(current),
            "current_tool_digest": original.digest(tool_inputs),
            "measured_policy_digest": original.digest(measured),
            "archive_sha256": INVENTORY_SHA,
            "historical_receipt": historical_receipt,
            "external_read_receipt": external_receipt,
            "assessment_map_proof_sha256": ASSESSMENT_MAP_SHA,
        }
    )
    return measured, binding, receipt
