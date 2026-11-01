"""Archived bytes require intact live successors, including after cache warming."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import cast

import pytest
from tools import performance_ci60_qualification as ci60
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
    for name in [
        migration.MANIFEST,
        record["archive"],
        *record["successors"],
        *(pin[0] for pin in migration.INTEGRATION_PREIMAGES.values()),
        migration.INTEGRATION_OVERLAY_ADDITIONS[0],
    ]:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        current = (ROOT / name).read_bytes()
        if name in {
            "tests/shared/category_migration/phase11e_mission_scoring_cleanup_configuration.py",
            "tests/shared/category_migration/phase11e_mission_scoring_cleanup_history_and_reserves.py",
        }:
            current = ci60.historical_test_preimage(ROOT, name, current)
        destination.write_bytes(current)
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
    for name in (
        migration.EDITION_TEST,
        migration.EDITION_ARCHIVE,
        migration.EDITION_PREDECESSOR_ARCHIVE,
        migration.EDITION_REGISTERED_PREDECESSOR_ARCHIVE,
        migration.EDITION_REGISTERED_HELPER,
        "docs/performance/policy-v3/acts-provenance-20261031/source-scope-predecessor.py.txt",
    ):
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


@pytest.mark.parametrize("path", tuple(migration.INTEGRATION_PREIMAGES))
def test_integration_whole_module_ast_rejects_assertion_drift_without_hash_gate(path: str) -> None:
    archive, _before_hash, _current_hash = migration.INTEGRATION_PREIMAGES[path]
    before = (ROOT / archive).read_bytes()
    current = (ROOT / path).read_bytes()
    migration.assert_integration_migration_ast(path, before, current)
    tree = ast.parse(current)
    assertion = next(n for n in ast.walk(tree) if isinstance(n, ast.Assert))
    assertion.test = ast.Constant(value=False)
    with pytest.raises(ValueError, match=r"Integration.*(AST|initialization)"):
        migration.assert_integration_migration_ast(path, before, ast.unparse(tree).encode())


def test_integration_exact_preimage_byte_drift_is_rejected(preserved_root: Path) -> None:
    archive = migration.INTEGRATION_PREIMAGES[ORIGINAL][0]
    target = preserved_root / archive
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="predecessor bytes drifted"):
        migration.verify_migrated_test(preserved_root, ORIGINAL)


@pytest.mark.parametrize(
    "reference",
    [
        "tests/unit/test_order60_emergency_disembark.py",
        "tests/unit/test_phase11b_objective_control.py",
    ],
)
def test_inventory_predecessor_AST_rejects_unrelated_assertion_drift(reference: str) -> None:
    from tools.core_rules_order97_history import (
        INTEGRATION_INVENTORY_PREIMAGES,
        assert_integration_inventory_ast,
    )

    archive = INTEGRATION_INVENTORY_PREIMAGES[reference][0]
    before = (ROOT / archive).read_bytes()
    current = (ROOT / reference).read_bytes()
    assert_integration_inventory_ast(reference, before, current)
    tree = ast.parse(current)
    assertion = next(n for n in ast.walk(tree) if isinstance(n, ast.Assert))
    assertion.test = ast.Constant(value=False)
    with pytest.raises(ValueError, match="whole-module AST drifted"):
        assert_integration_inventory_ast(reference, before, ast.unparse(tree).encode())


@pytest.mark.parametrize(
    "reference",
    [
        "tests/unit/test_order60_emergency_disembark.py",
        "tests/unit/test_phase11b_objective_control.py",
    ],
)
def test_inventory_predecessor_exact_archive_bytes_reject_drift(
    reference: str,
    tmp_path: Path,
) -> None:
    from tools.core_rules_order97_history import (
        INTEGRATION_INVENTORY_PREIMAGES,
    )

    archive = INTEGRATION_INVENTORY_PREIMAGES[reference][0]
    for name in [reference, archive]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    # Exercise the exact integration view without unrelated historical mappings.
    from tools.core_rules_order97_history import integration_inventory_history

    assert integration_inventory_history(reference, root=tmp_path) == tmp_path / archive
    target = tmp_path / archive
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="input bytes drifted"):
        integration_inventory_history(reference, root=tmp_path)


@pytest.mark.parametrize(
    "reference",
    [
        "tests/conftest.py",
        "tests/indirect_shooting_helpers.py",
        "tests/psychic_modifier_helpers.py",
        "tests/support/ability_presence_fixtures.py",
        "tests/unit/test_phase12a_timing_reactions_effects.py",
    ],
)
def test_reviewed_inventory_fixture_whole_AST_rejects_unlisted_initializers(reference: str) -> None:
    from tools.core_rules_order97_history import (
        REVIEWED_INVENTORY_FIXTURES,
        assert_reviewed_inventory_fixture_ast,
    )

    accepted_path = REVIEWED_INVENTORY_FIXTURES[reference][2]
    accepted = (ROOT / accepted_path).read_bytes()
    current = (ROOT / reference).read_bytes()
    assert_reviewed_inventory_fixture_ast(accepted, current)
    tree = ast.parse(current)
    tree.body.extend(ast.parse("unlisted_inventory_fixture_initializer = True").body)
    with pytest.raises(ValueError, match="fixture AST drifted"):
        assert_reviewed_inventory_fixture_ast(accepted, ast.unparse(tree).encode())


@pytest.mark.parametrize("path", sorted(ci60.HISTORICAL_TEST_PINS))
def test_ci60_historical_test_view_requires_current_bytes_and_original_native_pin(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = (ROOT / path).read_bytes()
    before = ci60.historical_test_preimage(ROOT, path, current)
    assert hashlib.sha256(before).hexdigest() == ci60.HISTORICAL_TEST_PINS[path]
    with pytest.raises(ValueError, match="unrelated current bytes"):
        ci60.historical_test_preimage(ROOT, path, current + b"\n")
    monkeypatch.setitem(ci60.HISTORICAL_TEST_PINS, path, "0" * 64)
    with pytest.raises(ValueError, match="native preimage changed"):
        ci60.historical_test_preimage(ROOT, path, current)


def test_vyper_edition_predecessor_is_exact_before_original_assertion_proof(
    edition_root: Path,
) -> None:
    current = (edition_root / migration.EDITION_TEST).read_bytes()
    registered = migration.edition_registered_predecessor(edition_root, current)
    assert registered == (ROOT / migration.EDITION_REGISTERED_PREDECESSOR_ARCHIVE).read_bytes()
    prior = migration.edition_provenance_predecessor(edition_root, registered)
    assert hashlib.sha256(prior).hexdigest() == migration.EDITION_PREDECESSOR_SHA256
    assert prior == (ROOT / migration.EDITION_PREDECESSOR_ARCHIVE).read_bytes()
    assert prior != current
    assert (
        migration.read_historical_test_bytes(edition_root, migration.EDITION_TEST)
        == (ROOT / migration.EDITION_ARCHIVE).read_bytes()
    )
    assert (edition_root / migration.EDITION_TEST).read_bytes() == current


def test_vyper_edition_predecessor_archive_is_rechecked_after_success(
    edition_root: Path,
) -> None:
    migration.read_historical_test_bytes(edition_root, migration.EDITION_TEST)
    archive = edition_root / migration.EDITION_PREDECESSOR_ARCHIVE
    archive.write_bytes(archive.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="predecessor archive changed"):
        migration.read_historical_test_bytes(edition_root, migration.EDITION_TEST)


@pytest.mark.parametrize(
    "mutation", ["added_assertion", "removed_control", "duplicate_control", "route", "initializer"]
)
def test_vyper_edition_additions_remain_exact_with_recomputed_live_pin(
    edition_root: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    path = edition_root / migration.EDITION_TEST
    tree = ast.parse(path.read_bytes())
    control = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_historical_snapshot_inputs"
    )
    if mutation == "added_assertion":
        assertion = next(node for node in ast.walk(control) if isinstance(node, ast.Assert))
        assertion.test = ast.Constant(True)
    elif mutation == "removed_control":
        tree.body.remove(control)
    elif mutation == "duplicate_control":
        tree.body.append(control)
    elif mutation == "route":
        route = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_active_identity_text"
        )
        assert isinstance(route.body[4], ast.If)
        route.body[4].test = ast.Constant(True)
    else:
        tree.body.append(ast.parse("unreviewed_guard_initializer = True").body[0])
    changed = (ast.unparse(tree) + "\n").encode()
    path.write_bytes(changed)
    monkeypatch.setattr(migration, "EDITION_AFTER_SHA256", hashlib.sha256(changed).hexdigest())
    with pytest.raises(ValueError, match=r"edition provenance|Original edition"):
        migration.read_historical_test_bytes(edition_root, migration.EDITION_TEST)


@pytest.mark.parametrize("member", ["predecessor", "helper"])
def test_registered_provenance_inputs_rechecked_after_success(
    edition_root: Path, member: str
) -> None:
    migration.read_historical_test_bytes(edition_root, migration.EDITION_TEST)
    relative = (
        migration.EDITION_REGISTERED_PREDECESSOR_ARCHIVE
        if member == "predecessor"
        else migration.EDITION_REGISTERED_HELPER
    )
    target = edition_root / relative
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="registered edition provenance inputs changed"):
        migration.read_historical_test_bytes(edition_root, migration.EDITION_TEST)


@pytest.mark.parametrize("mutation", ["import", "route", "initializer"])
def test_registered_projection_rejects_repin_of_changed_successor(
    edition_root: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    path = edition_root / migration.EDITION_TEST
    tree = ast.parse(path.read_bytes())
    if mutation == "import":
        node = next(
            n
            for n in tree.body
            if isinstance(n, ast.ImportFrom) and n.module == "tools.source_scope_provenance"
        )
        node.names[0].name = "unreviewed_projection"
    elif mutation == "route":
        route = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "_active_identity_text"
        )
        assert isinstance(route.body[3], ast.If)
        route.body[3].test = ast.Constant(True)
    else:
        tree.body.append(ast.parse("unreviewed_initializer = True").body[0])
    changed = (ast.unparse(tree) + "\n").encode()
    path.write_bytes(changed)
    monkeypatch.setattr(migration, "EDITION_AFTER_SHA256", hashlib.sha256(changed).hexdigest())
    with pytest.raises(ValueError, match=r"edition provenance|Original edition"):
        migration.read_historical_test_bytes(edition_root, migration.EDITION_TEST)


@pytest.mark.parametrize(
    "drift", [None, "archive", "original", "addition", "omission", "duplicate"]
)
def test_acts_additions_preserve_every_original_assertion(
    tmp_path: Path, drift: str | None
) -> None:
    from tests.support.acts_preservation import ARCHIVE, TEST_PATH, acts_predecessor

    archive = tmp_path / ARCHIVE
    archive.parent.mkdir(parents=True)
    archive.write_bytes((ROOT / ARCHIVE).read_bytes())
    raw = (ROOT / TEST_PATH).read_bytes()
    if drift is None:
        assert acts_predecessor(tmp_path, TEST_PATH, raw) == archive.read_bytes()
        assert acts_predecessor(tmp_path, "tests/unrelated.py", raw) == raw
        return
    if drift == "archive":
        archive.write_bytes(archive.read_bytes() + b"\n")
    else:
        tree = ast.parse(raw)
        original = next(node for node in tree.body if isinstance(node, ast.FunctionDef))
        addition = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_acts_")
        )
        if drift in {"original", "addition"}:
            (original if drift == "original" else addition).body = [ast.Pass()]
        elif drift == "omission":
            tree.body.remove(addition)
        else:
            tree.body.append(addition)
        raw = ast.unparse(tree).encode()
    with pytest.raises(ValueError, match="Acts"):
        acts_predecessor(tmp_path, TEST_PATH, raw)


@pytest.mark.parametrize(
    "mutation", [None, "archive", "original", "addition", "omission", "duplicate"]
)
def test_acts_comparison_registration_preserves_exact_historical_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str | None
) -> None:
    from tests.support import acts_preservation as acts

    target = tmp_path / acts.PROVENANCE_ARCHIVE
    target.parent.mkdir(parents=True)
    target.write_bytes((ROOT / acts.PROVENANCE_ARCHIVE).read_bytes())
    current = acts.defiler_provenance_predecessor(
        (ROOT / "tools/source_scope_provenance.py").read_bytes()
    )
    if mutation is None:
        assert acts.acts_provenance_predecessor(tmp_path, current) == target.read_bytes()
        return
    if mutation == "archive":
        target.write_bytes(target.read_bytes() + b"\n")
    elif mutation == "original":
        current = current.replace(b"return contexts.get(relative)", b"return None")
    elif mutation == "addition":
        current = current.replace(b"(scopes.ACTS_BASE,)", b"(scopes.EC_BASE,)")
    elif mutation == "omission":
        current = current.replace(acts.PROVENANCE_ADDITIONS[0], b"")
    else:
        current += acts.PROVENANCE_ADDITIONS[0]
    # Re-pinning current bytes cannot hide a changed old predicate or broadened addition.
    monkeypatch.setattr(acts, "PROVENANCE_AFTER_SHA256", hashlib.sha256(current).hexdigest())
    with pytest.raises(ValueError, match="registered edition provenance inputs changed"):
        acts.acts_provenance_predecessor(tmp_path, current)


@pytest.mark.parametrize(
    "mutation", [None, "archive", "unrelated", "omission", "duplicate", "adjacent"]
)
def test_acts_live_consumer_rename_preserves_exact_original_bytes(
    tmp_path: Path, mutation: str | None
) -> None:
    from tests.support import acts_preservation as acts

    target = tmp_path / acts.CONSUMER_ARCHIVE
    target.parent.mkdir(parents=True)
    target.write_bytes((ROOT / acts.CONSUMER_ARCHIVE).read_bytes())
    current = (ROOT / acts.CONSUMER_PATH).read_bytes()
    if mutation is None:
        assert acts.acts_predecessor(tmp_path, acts.CONSUMER_PATH, current) == target.read_bytes()
        # Exercise the actual immutable migration consumer, not only the projection helper.
        original, record = migration.verify_migrated_test(
            ROOT, "tests/unit/reporting/test_runtime_consumer_evidence.py"
        )
        assert hashlib.sha256(original).hexdigest() == record["original_sha256"]
        return
    if mutation == "archive":
        target.write_bytes(target.read_bytes() + b"\n")
    elif mutation == "unrelated":
        current += b"\nUNRELATED_INITIALIZER = True\n"
    elif mutation == "omission":
        current = current.replace(acts.CONSUMER_NEW_TOKEN, acts.CONSUMER_OLD_TOKEN)
    elif mutation == "duplicate":
        current += b"\n" + acts.CONSUMER_NEW_TOKEN
    else:
        current = current.replace(
            acts.CONSUMER_NEW_TOKEN, b"adepta_sororitas_army_rule.UNIT_DESTROYED_HOOK_ID"
        )
    with pytest.raises(ValueError, match="Acts runtime-consumer"):
        acts.acts_predecessor(tmp_path, acts.CONSUMER_PATH, current)


@pytest.mark.parametrize(
    "mutation", [None, "archive", "recipe", "assertion", "initializer", "omission"]
)
def test_acts_inactive_api_maintenance_preserves_original_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str | None
) -> None:
    from scripts.build_test_shards import behavioral_selection, validate_acts_inactive_source

    from tests.support import acts_preservation as acts

    for path in (acts.INACTIVE_ARCHIVE, acts.INACTIVE_RECIPE):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    current = (ROOT / acts.INACTIVE_PATH).read_bytes()
    live = tmp_path / acts.INACTIVE_PATH
    live.parent.mkdir(parents=True, exist_ok=True)
    live.write_bytes(current)
    if mutation is None:
        validate_acts_inactive_source(tmp_path)
        behavioral_selection(ROOT)
        original = acts.acts_inactive_predecessor(tmp_path, current)
        ledger = json.loads(
            (ROOT / "data/source_audits/ci64_provenance_v1/test-cutover.json").read_bytes()
        )
        assert (
            hashlib.sha256(original).hexdigest()
            == ledger["inactive_legacy_files"][acts.INACTIVE_PATH]["sha256"]
        )
        assert acts.INACTIVE_PATH not in ledger["active_files"]
        assert (
            ledger["inactive_updates"][acts.INACTIVE_PATH]["recipe"]
            == "acts-turn-api-maintenance-v1"
        )
        return
    if mutation in {"archive", "recipe"}:
        target = tmp_path / (
            acts.INACTIVE_ARCHIVE if mutation == "archive" else acts.INACTIVE_RECIPE
        )
        target.write_bytes(target.read_bytes() + b"\n")
    elif mutation == "assertion":
        current = current.replace(b"assert len(pool) == 1", b"assert True", 1)
    elif mutation == "initializer":
        current += b"\nUNRELATED_INITIALIZER = True\n"
    else:
        current = current.replace(
            b"army_rule.TURN_START_TRIGGER", b"army_rule.BATTLE_ROUND_START_TRIGGER", 1
        )
    live.write_bytes(current)
    with pytest.raises(SystemExit, match="Acts inactive"):
        validate_acts_inactive_source(tmp_path)
    with pytest.raises(ValueError, match="Acts inactive"):
        acts.acts_inactive_predecessor(tmp_path, current)

    if mutation == "initializer":
        ledger_path = ROOT / "data/source_audits/ci64_provenance_v1/test-cutover.json"
        ledger = json.loads(ledger_path.read_bytes())
        ledger["inactive_updates"][acts.INACTIVE_PATH]["after"] = {
            "mode": "100644",
            "bytes": len(current),
            "sha256": hashlib.sha256(current).hexdigest(),
            "blob_sha1": hashlib.sha1(
                b"blob " + str(len(current)).encode() + b"\0" + current
            ).hexdigest(),
        }
        original_read_bytes = Path.read_bytes

        def repinned_bytes(target: Path) -> bytes:
            if target == ROOT / acts.INACTIVE_PATH:
                return current
            if target == ledger_path:
                return json.dumps(ledger).encode()
            return original_read_bytes(target)

        # Even a coordinated current-file and metadata re-pin cannot widen admission.
        with monkeypatch.context() as patch:
            patch.setattr(Path, "read_bytes", repinned_bytes)
            with pytest.raises(SystemExit, match="Acts inactive"):
                behavioral_selection(ROOT)


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "original",
        "scope",
        "omission",
        "duplicate",
        "ec_addition",
        "ec_omission",
        "ec_duplicate",
    ],
)
def test_defiler_registration_retains_exact_acts_predecessor(mutation: str | None) -> None:
    from tests.support import acts_preservation as acts

    raw = (ROOT / "tools/source_scope_provenance.py").read_bytes()
    addition = b"COMPARISON_ONLY_SCOPE_BASES = (scopes.ACTS_BASE, scopes.DEFILER_BASE)"
    if mutation is None:
        assert hashlib.sha256(acts.defiler_provenance_predecessor(raw)).hexdigest() == (
            "40ef539dc75aa669df54a099d7788b74ca68453c7ae18a1e009194c48a42f64a"
        )
        return
    if mutation == "original":
        raw = raw.replace(b"return contexts.get(relative)", b"return None")
    elif mutation == "scope":
        raw = raw.replace(b"scopes.DEFILER_BASE", b"scopes.EC_BASE")
    elif mutation == "omission":
        raw = raw.replace(addition, b"")
    elif mutation == "ec_addition":
        raw = raw.replace(b"CURRENT_EC_OVERLAY_SHA256", b"ALTERED_EC_OVERLAY_SHA256")
    elif mutation == "ec_omission":
        raw = raw.replace(b"    current = current_ec_overlay_provenance(root, path, raw)\n", b"")
    elif mutation == "ec_duplicate":
        raw += raw[
            raw.index(b"# Current source-only admission:") : raw.index(
                b"\ndef registered_provenance_context("
            )
        ]
    else:
        raw += addition
    with pytest.raises(ValueError, match="registered edition provenance inputs changed"):
        acts.defiler_provenance_predecessor(raw)
