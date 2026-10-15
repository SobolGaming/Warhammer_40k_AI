"""Archived bytes require intact live successors, including after cache warming."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import cast

import pytest
from tools.core_rules_order95_audit import (
    RETIRED_REFERENCE_SUCCESSORS,
    AuditError,
    validate_owner_reference,
)

from tests import category_migration_preservation as migration

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = "tests/unit/test_phase11e_mission_scoring_cleanup.py"


def _manifest() -> migration.MigrationManifest:
    return cast(migration.MigrationManifest, json.loads((ROOT / migration.MANIFEST).read_bytes()))


@pytest.fixture
def preserved_root(tmp_path: Path) -> Path:
    record = _manifest()["originals"][ORIGINAL]
    for name in [migration.MANIFEST, record["archive"], *record["successors"]]:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / name).read_bytes())
    return tmp_path


def test_every_original_archive_has_complete_equivalent_live_successors() -> None:
    manifest = _manifest()
    assert len(manifest["originals"]) == len(migration.MIGRATED_PATHS) == 68
    for path, record in manifest["originals"].items():
        raw, verified = migration.verify_migrated_test(ROOT, path)
        assert raw == (ROOT / record["archive"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == record["original_sha256"]
        assert verified == record
        assert migration.read_historical_test_bytes(ROOT, path) == raw


def test_live_reference_resolves_actual_current_module_without_archival_substitution() -> None:
    manifest = _manifest()
    for original, record in manifest["originals"].items():
        for name, successor in record["definitions"].items():
            if successor.split("::", 1)[0] != original:
                current = migration.live_test_reference(ROOT, original + "::" + name)
                assert current == successor
                path, symbol = current.split("::", 1)
                assert path.startswith("tests/")
                assert path.endswith(".py")
                tree = ast.parse((ROOT / path).read_bytes())
                assert any(
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    and node.name == symbol
                    for node in tree.body
                )
                return
    pytest.fail("The migration must include an actual relocated definition.")


def test_returned_record_cannot_poison_the_next_manifest_verification(preserved_root: Path) -> None:
    original, record = migration.verify_migrated_test(preserved_root, ORIGINAL)
    record["successors"].clear()
    record["definitions"].clear()
    after, intact = migration.verify_migrated_test(preserved_root, ORIGINAL)
    assert after == original
    assert intact["successors"]
    assert intact["definitions"]


@pytest.mark.parametrize(
    "mutation",
    [
        "archive",
        "missing_successor",
        "added_definition",
        "removed_definition",
        "duplicated_definition",
        "assertion",
        "decorator",
        "helper",
        "fixture_scope",
        "import_binding",
        "module_initializer",
        "repository_anchor",
        "manifest_repin",
    ],
)
def test_actual_file_drift_is_rejected_after_successful_cached_verification(
    preserved_root: Path, mutation: str
) -> None:
    _, record = migration.verify_migrated_test(preserved_root, ORIGINAL)
    definitions = record["definitions"]
    selected = next(value for name, value in definitions.items() if name.startswith("test_"))
    relative, name = selected.split("::", 1)
    target = preserved_root / relative
    if mutation == "archive":
        target = preserved_root / record["archive"]
    elif mutation == "repository_anchor":
        target = preserved_root / "tests/shared/repository_root.py"
    elif mutation in {"helper", "fixture_scope", "import_binding", "module_initializer"}:
        helper = next(
            value
            for key, value in definitions.items()
            if key == "authentic_primary_destruction_lifecycle_payload"
        )
        relative, name = helper.split("::", 1)
        target = preserved_root / relative
    before = target.read_bytes()
    if mutation == "missing_successor":
        target.unlink()
    elif mutation in {"archive", "manifest_repin"}:
        target.write_bytes(before + b"\n")
        if mutation == "manifest_repin":
            manifest = _manifest()
            manifest["originals"][ORIGINAL]["successors"][relative] = hashlib.sha256(
                target.read_bytes()
            ).hexdigest()
            (preserved_root / migration.MANIFEST).write_text(json.dumps(manifest))
    elif mutation == "repository_anchor":
        target.write_bytes(before.replace(b"parents[2]", b"parents[1]"))
    else:
        tree = ast.parse(before)
        function = next(
            node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name
        )
        if mutation == "added_definition":
            tree.body.extend(
                ast.parse("def test_unregistered_successor():\n    assert True\n").body
            )
        elif mutation == "removed_definition":
            tree.body.remove(function)
        elif mutation == "duplicated_definition":
            tree.body.append(function)
        elif mutation == "assertion":
            statement = next(node for node in ast.walk(function) if isinstance(node, ast.Assert))
            statement.test = ast.Constant(True)
        elif mutation == "decorator":
            function.decorator_list.append(ast.Name(id="changed_parameter_factory", ctx=ast.Load()))
        elif mutation == "helper":
            function.body.append(ast.Pass())
        elif mutation == "fixture_scope":
            decorator = next(node for node in function.decorator_list if isinstance(node, ast.Call))
            scope = next(keyword for keyword in decorator.keywords if keyword.arg == "scope")
            assert isinstance(scope.value, ast.Constant)
            assert scope.value.value == "module"
            scope.value = ast.Constant("session")
        elif mutation == "import_binding":
            imported = next(node for node in tree.body if isinstance(node, ast.ImportFrom))
            imported.module = "changed_dependency"
        elif mutation == "module_initializer":
            tree.body.extend(ast.parse("unexpected_migration_initializer = True").body)
        target.write_text(ast.unparse(tree) + "\n")
    with pytest.raises((ValueError, FileNotFoundError)):
        migration.verify_migrated_test(preserved_root, ORIGINAL)
    target.write_bytes(before)
    (preserved_root / migration.MANIFEST).write_bytes((ROOT / migration.MANIFEST).read_bytes())
    assert migration.verify_migrated_test(preserved_root, ORIGINAL)[0]


def test_unknown_migration_path_and_definition_cannot_select_nearby_evidence() -> None:
    with pytest.raises(ValueError, match="Unknown migrated test path"):
        migration.verify_migrated_test(ROOT, "tests/unit/unknown_migrated_test.py")
    with pytest.raises(ValueError, match="Unknown migrated test definition"):
        migration.live_test_reference(ROOT, ORIGINAL + "::test_nonexistent_successor")


def test_unmigrated_historical_reader_keeps_actual_current_bytes(tmp_path: Path) -> None:
    relative = "tests/unmoved_source.py"
    path = tmp_path / relative
    path.parent.mkdir()
    path.write_bytes(b"original source\n")
    assert migration.read_historical_test_bytes(tmp_path, relative) == b"original source\n"
    path.write_bytes(b"changed source\n")
    assert migration.read_historical_test_bytes(tmp_path, relative) == b"changed source\n"
    assert migration.live_test_reference(tmp_path, relative + "::test_current") == (
        relative + "::test_current"
    )


MOVED = "tests/unit/test_phase9b_lifecycle.py"
REFERENCE = MOVED + "::test_phase_wrap_switches_active_player"


@pytest.fixture
def migrated_root(tmp_path: Path) -> Path:
    manifest = json.loads((ROOT / migration.MANIFEST).read_bytes())
    record = manifest["originals"][MOVED]
    for name in [migration.MANIFEST, record["archive"], *record["successors"]]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    return tmp_path


def test_order95_accepts_only_authenticated_live_migrated_owners(migrated_root: Path) -> None:
    assert RETIRED_REFERENCE_SUCCESSORS[REFERENCE] == (
        migration.live_test_reference(migrated_root, REFERENCE),
    )
    validate_owner_reference(REFERENCE, migrated_root)
    validate_owner_reference(MOVED, migrated_root)
    with pytest.raises(AuditError, match="reference is absent"):
        validate_owner_reference(MOVED + "::test_unregistered_successor", migrated_root)


@pytest.mark.parametrize("mutation", ["missing_successor", "changed_assertion", "archive"])
def test_order95_successor_and_independent_migration_proof_reject_drift(
    migrated_root: Path, mutation: str
) -> None:
    validate_owner_reference(REFERENCE, migrated_root)
    _, record = migration.verify_migrated_test(migrated_root, MOVED)
    successor = record["definitions"]["test_phase_wrap_switches_active_player"].split("::")[0]
    target = migrated_root / (record["archive"] if mutation == "archive" else successor)
    if mutation == "missing_successor":
        target.unlink()
    else:
        raw = target.read_bytes()
        target.write_bytes(
            raw + b"\n# altered archival byte\n"
            if mutation == "archive"
            else raw.replace(b"assert ", b"assert True or ", 1)
        )
    if mutation == "missing_successor":
        with pytest.raises(AuditError, match="reference is absent"):
            validate_owner_reference(REFERENCE, migrated_root)
    else:
        with pytest.raises(ValueError, match="drifted"):
            migration.verify_migrated_test(migrated_root, MOVED)


def test_order95_migrated_owner_cannot_reappear_at_the_retired_node(migrated_root: Path) -> None:
    validate_owner_reference(REFERENCE, migrated_root)
    target = migrated_root / MOVED
    target.write_bytes(
        target.read_bytes() + b"\ndef test_phase_wrap_switches_active_player():\n    pass\n"
    )
    with pytest.raises(AuditError, match="retired owner was reintroduced"):
        validate_owner_reference(REFERENCE, migrated_root)


@pytest.fixture
def utf8_root(tmp_path: Path) -> Path:
    for name in (migration.UTF8_TEST, migration.UTF8_ARCHIVE):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    return tmp_path


def test_utf8_maintenance_returns_original_only_after_exact_live_check(utf8_root: Path) -> None:
    original = migration.read_historical_test_bytes(utf8_root, migration.UTF8_TEST)
    assert hashlib.sha256(original).hexdigest() == migration.UTF8_BEFORE_SHA256
    assert original == (ROOT / migration.UTF8_ARCHIVE).read_bytes()
    assert (
        b'audit.REPORT.read_text(encoding="utf-8")'
        in (utf8_root / migration.UTF8_TEST).read_bytes()
    )


@pytest.mark.parametrize("member", ["live", "archive"])
def test_utf8_maintenance_rejects_drift_after_success(utf8_root: Path, member: str) -> None:
    migration.read_historical_test_bytes(utf8_root, migration.UTF8_TEST)
    target = utf8_root / (migration.UTF8_TEST if member == "live" else migration.UTF8_ARCHIVE)
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="UTF-8-only maintenance proof changed"):
        migration.read_historical_test_bytes(utf8_root, migration.UTF8_TEST)


def test_utf8_maintenance_proves_only_the_encoding_edit_even_with_recomputed_live_pin(
    utf8_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = utf8_root / migration.UTF8_TEST
    changed = target.read_bytes().replace(b"assert ", b"assert True or ", 1).replace(b"\r\n", b"\n")
    target.write_bytes(changed)
    monkeypatch.setattr(migration, "UTF8_AFTER_SHA256", hashlib.sha256(changed).hexdigest())
    with pytest.raises(ValueError, match="UTF-8-only maintenance proof changed"):
        migration.read_historical_test_bytes(utf8_root, migration.UTF8_TEST)


@pytest.fixture
def edition_root(tmp_path: Path) -> Path:
    for name in (migration.EDITION_TEST, migration.EDITION_ARCHIVE):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    return tmp_path


def test_edition_maintenance_preserves_all_original_assertions(edition_root: Path) -> None:
    original = migration.read_historical_test_bytes(edition_root, migration.EDITION_TEST)
    assert hashlib.sha256(original).hexdigest() == migration.EDITION_BEFORE_SHA256


@pytest.mark.parametrize("member", ["live", "archive"])
def test_edition_maintenance_rechecks_complete_bytes_after_success(
    edition_root: Path, member: str
) -> None:
    migration.read_historical_test_bytes(edition_root, migration.EDITION_TEST)
    target = edition_root / (
        migration.EDITION_TEST if member == "live" else migration.EDITION_ARCHIVE
    )
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="edition-scanner maintenance bytes changed"):
        migration.read_historical_test_bytes(edition_root, migration.EDITION_TEST)


def test_edition_maintenance_rejects_an_assertion_change_even_with_recomputed_live_pin(
    edition_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = edition_root / migration.EDITION_TEST
    changed = target.read_bytes().replace(
        b"assert not violations", b"assert True or not violations", 1
    )
    target.write_bytes(changed)
    monkeypatch.setattr(migration, "EDITION_AFTER_SHA256", hashlib.sha256(changed).hexdigest())
    with pytest.raises(
        ValueError, match="Original edition assertions or unrelated semantics changed"
    ):
        migration.read_historical_test_bytes(edition_root, migration.EDITION_TEST)
