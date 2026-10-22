"""Explicit exact-source successor route; historical measurement APIs stay immutable.

This module admits preservation evidence for one locally qualified successor.
Its receipt is never a current runtime measurement or an assertion of ancestry
between a protected squash and its worker commits. Independent review is required
before using this review candidate beyond local qualification.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

from tools import performance_category_migration as legacy
from tools import performance_reconstruction_campaign as reconstruction
from tools import performance_tool_inputs as original

SCHEMA = "cumulative-preservation-pr587-v1"
NAMESPACE = "data/source_audits/cumulative_preservation_v1"
REGISTRY_SHA = "ba78843b597acd3ef86f6b3f05c094b8267711bc9efb50876a746177bbbdf327"
ACCEPTED = "b75bfcf352e3e8bb5346e210a6b427a7af3a4242"
CONTENT_BASE = "5f509724da25a2f6ded0c2739a8e7c84bdf59c91"
CONTENT_TREE = "1fa709a167abb369932e651f89babbd0034941c5"
SOURCE_ID = "12e945f358deceff8ba7fc32c7ca7e9d325eecf0e39728c12c684311b4f7b5fb"
# The only permitted post-freeze edit is the None-to-commit literal below.
SOURCE_COMMIT: str | None = "036a1aa2b066fe37b0a9be37d4d9f45436a24e32"
SELF = "tools/cumulative_preservation.py"
BASE, MEASURED, TREE = legacy.BASE, legacy.MEASURED, legacy.TREE
ARCHIVE, EXTERNAL = legacy.ARCHIVE, legacy.EXTERNAL
ASSESSMENT_MAP = NAMESPACE + "/map"
SOURCE_ARCHIVES = legacy.SOURCE_ARCHIVES
CONTROLS = legacy.CONTROLS | frozenset(
    {
        SELF,
        "tests/code_quality/test_d07_upper_floor_preservation.py",
        "tests/code_quality/test_cumulative_preservation.py",
    }
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read(root: Path, name: str) -> bytes:
    from tests.d07_geometry_containment import read_owned_geometry_member

    if root.is_symlink() or root.is_junction() or root.absolute() != root.resolve(strict=True):
        raise ValueError("Aliased cumulative root.")
    try:
        return read_owned_geometry_member(root.resolve(strict=True), name)
    except FileNotFoundError as error:
        raise ValueError("Cumulative member missing: " + name) from error


def _git(root: Path, *args: str, payload: bytes | None = None) -> bytes:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={root.as_posix()}", *args],
        cwd=root,
        input=payload,
        timeout=60,
    )


def _json(root: Path, name: str) -> Any:
    return json.loads(_read(root, name))


def _registry(root: Path) -> dict[str, Any]:
    raw = _read(root, NAMESPACE + "/registry.json")
    if _sha(raw) != REGISTRY_SHA:
        raise ValueError("Cumulative registry changed.")
    record = cast(dict[str, Any], json.loads(raw))
    if record["schema"] != SCHEMA or record["accepted_source"] != SOURCE_ID:
        raise ValueError("Cumulative registry identity changed.")
    members = record["members"]
    actual = {
        p.relative_to(root / NAMESPACE).as_posix()
        for p in (root / NAMESPACE).rglob("*")
        if p.is_file() or p.is_symlink()
    }
    if actual != set(members) | {"registry.json"}:
        raise ValueError("Cumulative evidence membership changed.")
    for name, pin in members.items():
        if _sha(_read(root, NAMESPACE + "/" + name)) != pin:
            raise ValueError("Cumulative evidence member changed: " + name)
    return record


def read_archive(root: Path) -> dict[str, object]:
    return legacy.read_archive(root)


def applies(*, base: str, runtime_id: str, family: str) -> bool:
    return legacy.applies(base=base, runtime_id=runtime_id, family=family)


def measured_snapshot(root: Path, revision: str, *, external_reads: bool = False) -> dict[str, str]:
    return legacy.measured_snapshot(root, revision, external_reads=external_reads)


def current_tool_inventory(root: Path) -> dict[str, str]:
    return legacy.current_tool_inventory(root)


def reviewed_control_hashes(root: Path) -> dict[str, str]:
    """The separate genuine implementation freeze authenticates all seven controls."""
    if SOURCE_COMMIT is None:
        raise ValueError("Cumulative adapter awaits its reviewed source commit binding.")
    if len(SOURCE_COMMIT) != 40 or any(c not in "0123456789abcdef" for c in SOURCE_COMMIT):
        raise ValueError("Invalid cumulative source commit binding.")
    _git(root, "merge-base", "--is-ancestor", SOURCE_COMMIT, "HEAD")
    directory = root / "docs/performance/policy-v3/ci-compatibility-20261015"
    if {
        p.relative_to(root).as_posix()
        for p in directory.rglob("*")
        if p.is_file() or p.is_symlink()
    } != SOURCE_ARCHIVES:
        raise ValueError("Reviewed compatibility archive membership changed.")
    marker = b"\nSOURCE_COMMIT: str | None = None"
    bound = f'\nSOURCE_COMMIT: str | None = "{SOURCE_COMMIT}"'.encode()
    result = {}
    for name in sorted(CONTROLS | SOURCE_ARCHIVES):
        raw = _git(root, "show", SOURCE_COMMIT + ":" + name)
        if name == SELF:
            if raw.count(marker) != 1:
                raise ValueError("Source freeze must contain the unactivated cumulative adapter.")
            raw = raw.replace(marker, bound, 1)
        if _read(root, name) != raw:
            raise ValueError(
                "Reviewed migration source/data changed; control bytes changed: " + name
            )
        if name in CONTROLS:
            result[name] = _sha(raw)
    return result


def expected_source(root: Path) -> dict[str, str]:
    record = _registry(root)
    source = _json(root, NAMESPACE + "/accepted-source.json")
    if original.digest(source) != SOURCE_ID:
        raise ValueError("Accepted source manifest changed.")
    controls = reviewed_control_hashes(root)
    # No wildcard successor exception. Every changed/new implementation member
    # is frozen as an exact Git blob in the genuine local implementation commit.
    for name in record["integration_members"]:
        raw = _git(root, "show", str(SOURCE_COMMIT) + ":" + name)
        source[name] = controls.get(name, _sha(raw))
    return cast(dict[str, str], source)


def expected_inputs(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    source = expected_source(root)
    policy = {p: v for p, v in source.items() if legacy._policy_selected(p)}
    tools = {p: v for p, v in source.items() if legacy._selected(p)}
    if original.SPEC_ARCHIVE in source:
        tools[original.SPEC_PATH] = source[original.SPEC_ARCHIVE]
    old = cast(dict[str, str], read_archive(root)["POLICY_CURRENT_INPUTS.json.txt"])
    return policy | {original.MAP_PATH: old[original.MAP_PATH]}, tools | {
        original.MAP_PATH: old[original.MAP_PATH]
    }


def verify_live(root: Path) -> str:
    """No success cache: every request rechecks physical source and collector bytes."""
    if root.is_symlink() or root.is_junction():
        raise ValueError("Aliased cumulative root.")
    expected = expected_source(root)
    names = set(
        _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
        .decode()
        .split("\0")
    ) - {""}
    # Actual consumers also discover ignored Python, schema and TypeScript files.
    for prefix, pattern in (
        ("src", "*"),
        ("tests", "*.py"),
        ("tools", "*.py"),
        ("scripts", "*.py"),
        ("contracts", "*"),
        ("conformance/typescript/src", "*.ts"),
    ):
        names.update(
            p.relative_to(root).as_posix()
            for p in (root / prefix).rglob(pattern)
            if p.is_file() or p.is_symlink()
        )
    if names != expected.keys():
        raise ValueError("Reviewed cumulative source membership changed.")
    for name, pin in expected.items():
        if _sha(_read(root, name)) != pin:
            raise ValueError("Reviewed migration source/data changed: " + name)
    verify_owner_ledger(root)
    verify_control_transformations(root)
    return original.digest({"schema": SCHEMA, "source": expected, "freeze": SOURCE_COMMIT})


def verify_baseline(root: Path) -> str:
    """Content authentication, without claiming squash/worker ancestry."""
    _registry(root)
    canonical = _json(root, NAMESPACE + "/baseline.json")
    raw = _git(root, "cat-file", "commit", CONTENT_BASE)
    oid = hashlib.sha1(b"commit " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if oid != CONTENT_BASE or raw.splitlines()[0] != b"tree " + CONTENT_TREE.encode():
        raise ValueError("Protected content-base commit/tree changed.")
    rows = []
    for row in _git(root, "ls-tree", "-rz", CONTENT_BASE).split(b"\0"):
        if row:
            metadata, path = row.split(b"\t")
            mode, kind, blob = metadata.decode().split()
            rows.append({"path": path.decode(), "mode": mode, "kind": kind, "git_oid": blob})
    if rows != canonical:
        raise ValueError("Protected content-base canonical membership changed.")
    return original.digest({"commit": oid, "tree": CONTENT_TREE, "members": rows})


def _ast(raw: bytes) -> Any:
    """Serializable fields retain statement order, decorators and multiplicity."""

    def fields(value: Any) -> Any:
        if isinstance(value, ast.AST):
            return {
                "_type": type(value).__name__,
                **{k: fields(v) for k, v in ast.iter_fields(value)},
            }
        if isinstance(value, list):
            return [fields(v) for v in value]
        if isinstance(value, bytes):
            return {"_bytes": value.hex()}
        if isinstance(value, complex):
            return {"_complex": [value.real, value.imag]}
        if value is Ellipsis:
            return {"_ellipsis": True}
        return value

    return fields(ast.parse(raw))


def assert_recipe(before: bytes, current: bytes, recipe: dict[str, Any]) -> None:
    """Apply only frozen field/statement edits, then compare the entire AST.

    Exact occurrence paths preserve original assertion order and repeated nodes;
    editable live hashes cannot admit an extra assertion or initializer change.
    """
    expected = copy.deepcopy(_ast(before))
    for edit in recipe["edits"]:
        owner = expected
        for part in edit["at"]:
            owner = owner[part]
        if edit["kind"] == "splice":
            if owner[edit["start"] : edit["end"]] != edit["before"]:
                raise ValueError("Cumulative recipe preimage occurrence changed.")
            owner[edit["start"] : edit["end"]] = edit["after"]
            continue
        parent = expected
        for part in edit["at"][:-1]:
            parent = parent[part]
        key = edit["at"][-1]
        if parent[key] != edit["before"]:
            raise ValueError("Cumulative recipe preimage occurrence changed.")
        parent[key] = edit["after"]
    if expected != _ast(current):
        raise ValueError("Cumulative whole-module assertion/fixture/initializer drift.")


def verify_owner_ledger(root: Path) -> None:
    from tools.performance_policy import owner_hashes

    ledger = _json(root, NAMESPACE + "/owner-ledger.json")
    if len(ledger) != 153 or len({(r["path"], r["owner"]) for r in ledger}) != 153:
        raise ValueError("Cumulative owner ledger membership changed.")
    projections: dict[str, dict[str, str]] = {}
    for row in ledger:
        path = row["path"]
        if path not in projections:
            projections[path] = owner_hashes(path, _read(root, path))
        if projections[path].get(row["owner"]) != row["current_ast_sha256"]:
            raise ValueError("Cumulative owner binding changed: " + path + "::" + row["owner"])
        for evidence in row["source_documents"]:
            if _sha(_read(root, evidence["path"])) != evidence["sha256"]:
                raise ValueError("Cumulative source authority changed.")


def verify_control_transformations(root: Path) -> None:
    """Preserve seven authenticated control stages and all three exact changes."""
    rows = _json(root, NAMESPACE + "/control-transformations.json")
    if {row["path"] for row in rows} != legacy.CONTROLS or len(rows) != len(legacy.CONTROLS):
        raise ValueError("Cumulative control admission membership changed.")
    for row in rows:
        name = row["path"]
        historical = _git(root, "show", str(legacy.SOURCE_COMMIT) + ":" + name)
        if name == legacy.SELF:
            marker = b"\nSOURCE_COMMIT: str | None = None"
            if historical.count(marker) != 1:
                raise ValueError("Historical control activation occurrence changed.")
            historical = historical.replace(
                marker, f'\nSOURCE_COMMIT: str | None = "{legacy.SOURCE_COMMIT}"'.encode(), 1
            )
        baseline = _git(root, "show", CONTENT_BASE + ":" + name)
        accepted = _git(root, "show", ACCEPTED + ":" + name)
        current = _read(root, name)
        for raw, key in (
            (historical, "legacy_sha256"),
            (baseline, "pr587_sha256"),
            (accepted, "accepted_sha256"),
            (current, "current_sha256"),
        ):
            if _sha(raw) != row[key]:
                raise ValueError("Cumulative exact control-stage bytes changed: " + name)
        assert_recipe(historical, accepted, row["historical_to_accepted"])
        assert_recipe(baseline, accepted, row["baseline_to_accepted"])
        assert_recipe(accepted, current, row["accepted_to_integration"])


def d07_predecessors(root: Path) -> dict[str, bytes]:
    """One atomic historical request; live proofs precede predecessor exposure."""
    from tests.category_migration_preservation import read_historical_test_bytes
    from tests.d09_test_preservation_helpers import preserved_d09_predecessor_test_bytes

    live_receipt = verify_live(root)
    verify_baseline(root)
    recipes = _json(root, NAMESPACE + "/d07-recipes.json")
    later = _json(root, NAMESPACE + "/later-d07-recipes.json")
    if recipes.keys() & later.keys():
        raise ValueError("Historical and later D07 recipes overlap.")
    recipes = recipes | later
    canonical = {row["path"]: row for row in _json(root, NAMESPACE + "/baseline.json")}
    d09 = _json(root, NAMESPACE + "/d09-recipes.json")
    originals = _json(root, "data/source_audits/d07/original-tests.json")
    results = {}
    for path in originals:
        live = read_historical_test_bytes(root, path).replace(b"\r\n", b"\n")
        if path in d09:
            stage_recipe = d09[path]
            stage = _read(root, NAMESPACE + "/" + stage_recipe["d09_stage"])
            if (
                _sha(stage) != stage_recipe["d09_after_sha256"]
                or _sha(live) != stage_recipe["after_sha256"]
            ):
                raise ValueError("Cumulative D09 exact stage/live binding changed.")
            assert_recipe(stage, live, stage_recipe)
            historical = preserved_d09_predecessor_test_bytes(path, stage)
            if (
                _sha(historical) != stage_recipe["d09_before_sha256"]
                or _sha(historical) != stage_recipe["d07_effective_sha256"]
            ):
                raise ValueError("Cumulative original D09/D07 stage binding changed.")
            results[path] = historical
        elif path in recipes:
            recipe = recipes[path]
            before = _read(root, NAMESPACE + "/predecessors/" + path + ".txt")
            if _sha(before) != recipe["before_sha256"] or _sha(live) != recipe["after_sha256"]:
                raise ValueError("Cumulative D07 live/predecessor bytes changed: " + path)
            blob = hashlib.sha1(b"blob " + str(len(before)).encode() + b"\0" + before).hexdigest()
            if blob != recipe["baseline_blob"] or blob != canonical[path]["git_oid"]:
                raise ValueError("Cumulative predecessor is not its canonical Git blob.")
            assert_recipe(before, live, recipe)
            results[path] = before
        else:
            results[path] = preserved_d09_predecessor_test_bytes(path, live)
    if verify_live(root) != live_receipt:
        raise ValueError("Cumulative source changed during historical request.")
    return results


def assessment_map_inputs(
    root: Path, *, archive: dict[str, object], current: dict[str, str], tools: dict[str, str]
) -> tuple[dict[str, str], dict[str, str]]:
    directory = root / ASSESSMENT_MAP
    if not directory.is_dir() or {p.name for p in directory.iterdir()} != {
        "original-operation-map.json.txt",
        "assessment-map-additions.json.txt",
    }:
        raise ValueError("Assessment map proof membership changed.")
    # Registry authentication is independent of report-supplied hashes.
    _registry(root)
    proof = _json(root, ASSESSMENT_MAP + "/assessment-map-additions.json.txt")
    old_raw = _read(root, ASSESSMENT_MAP + "/original-operation-map.json.txt")
    live = _read(root, original.MAP_PATH)
    old_sha = cast(dict[str, str], archive["POLICY_CURRENT_INPUTS.json.txt"])[original.MAP_PATH]
    if proof["original_sha256"] != old_sha or _sha(old_raw) != old_sha:
        raise ValueError("Original operation map changed.")
    live_sha = _sha(live)
    if live_sha != proof["current_sha256"]:
        raise ValueError("Current operation map differs from exact cumulative proof.")
    if current.get(original.MAP_PATH) != live_sha or tools.get(original.MAP_PATH) != live_sha:
        raise ValueError("Actual operation map input identities disagree.")
    if json.loads(live) != proof["expected_map"]:
        raise ValueError("Literal operation union or historical budgets changed.")
    return current | {original.MAP_PATH: old_sha}, tools | {original.MAP_PATH: old_sha}


def verify_current_inventory(
    root: Path,
    *,
    archive: dict[str, object],
    current: dict[str, str],
    tools: dict[str, str],
    controls: dict[str, str],
) -> None:
    if controls.keys() != CONTROLS:
        raise ValueError("Exact adapter control cohort required.")
    if archive != read_archive(root):
        raise ValueError("Exact296 historical migration deltas changed.")
    expected_current, expected_tools = expected_inputs(root)
    if current != expected_current or tools != expected_tools:
        raise ValueError("Current inputs differ from the finite migration cohort.")
    if controls != reviewed_control_hashes(root):
        raise ValueError("Exact adapter control hashes changed.")
    verify_live(root)


def verify_external_reads(root: Path, proof: dict[str, object]) -> str:
    historical = legacy._object(read_archive(root)[EXTERNAL])
    if proof != historical:
        raise ValueError("External-read historical proof changed.")
    for side, revision in (("base", BASE), ("measured", MEASURED)):
        if measured_snapshot(root, revision, external_reads=True) != proof[side]:
            raise ValueError("Frozen external-read Git identities changed.")
    _registry(root)
    expected = _json(root, NAMESPACE + "/external.json")
    names = set(
        _git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
        .decode()
        .split("\0")
    ) - {""}
    selected = {p for p in names if legacy._external_selected(p) and (root / p).exists()}
    selected.update(
        p.relative_to(root).as_posix()
        for p in (root / "conformance/typescript/src").rglob("*.ts")
        if p.is_file() or p.is_symlink()
    )
    if selected != expected.keys():
        raise ValueError("External-read current membership changed.")
    current = {p: _sha(_read(root, p)) for p in sorted(selected)}
    if current != expected:
        raise ValueError("External-read current bytes changed.")
    for name, recipe in _json(root, NAMESPACE + "/external-transformations.json").items():
        before = _git(root, "show", MEASURED + ":" + name)
        lines = before.decode().splitlines(keepends=True)
        for edit in reversed(recipe["edits"]):
            if lines[edit["start"] : edit["end"]] != edit["before"]:
                raise ValueError("External-read exact transformation preimage changed.")
            lines[edit["start"] : edit["end"]] = edit["after"]
        if "".join(lines).encode() != _read(root, name):
            raise ValueError("External-read exact transformation changed.")
    return original.digest({"schema": SCHEMA, "historical_proof": proof, "current": current})


def retained_inputs(
    root: Path, *, current: dict[str, str], report: dict[str, object], base: str, runtime_id: str
) -> tuple[dict[str, str], dict[str, object] | None, str]:
    """Separate historical evidence from exact validated successor applicability."""
    if not applies(base=base, runtime_id=runtime_id, family=str(report.get("family"))):
        raise ValueError("Cumulative applicability belongs to another exact cohort.")
    reviewed_control_hashes(root)
    archive = read_archive(root)
    actual_tools = current_tool_inventory(root)
    p, t = assessment_map_inputs(root, archive=archive, current=current, tools=actual_tools)
    verify_current_inventory(
        root, archive=archive, current=p, tools=t, controls=reviewed_control_hashes(root)
    )
    content = verify_baseline(root)
    external = verify_external_reads(root, legacy._object(archive[EXTERNAL]))
    measured = legacy._strings(archive["POLICY_MEASURED_INPUTS.json.txt"])
    tool_snapshot = measured_snapshot(root, MEASURED)
    if tool_snapshot != archive["TOOL_MEASURED_INPUTS.json.txt"]:
        raise ValueError("Original measured Git inputs changed.")
    if _git(root, "rev-parse", MEASURED + "^{tree}").decode().strip() != TREE:
        raise ValueError("Original measured tree changed.")
    binding = None
    if report.get("family") == "reconstruction":
        measured, historical = reconstruction.retained_inputs(
            root, current=measured, report=report, base=base, runtime_id=runtime_id
        )
    else:
        from tools import performance_tool_inputs_v2 as fresh

        before = measured_snapshot(root, BASE)
        if before != archive["TOOL_BASE_INPUTS.json.txt"]:
            raise ValueError("Original measured base inputs changed.")
        harness = {p: tool_snapshot[p] for p in fresh.HARNESS}
        binding = fresh.classify_inputs(
            spec=legacy._object(archive["MEASURED_ROLE_SPEC.json.txt"]),
            base=before,
            head=tool_snapshot,
            base_revision=BASE,
            head_revision=MEASURED,
            head_input_digest=original.digest(measured),
            harness_base=harness,
            harness_head=harness,
        )
        if binding != archive["MEASURED_BINDING.json.txt"]:
            raise ValueError("Original measured binding changed.")
        original.validate_binding(observed=report.get("input_binding"), expected=binding)
        historical = original.digest(binding)
    receipt = original.digest(
        {
            "schema": SCHEMA,
            "content_base": CONTENT_BASE,
            "content_tree": CONTENT_TREE,
            "execution_freeze": SOURCE_COMMIT,
            "ancestry_claim": "local-implementation-only",
            "content_receipt": content,
            "external_receipt": external,
            "historical_receipt": historical,
            "successor_source": original.digest(expected_source(root)),
            "measurement_credit": "original-producing-cohort-only",
        }
    )
    return measured, binding, receipt
