"""D07 source scope and shared-consumer preservation, without runtime certification."""

import ast
import hashlib
import json
from pathlib import Path

from tests.category_migration_preservation import read_historical_test_bytes
from tests.d09_test_preservation_helpers import preserved_d09_predecessor_test_bytes
from tests.support.section13_preservation import pre_section13_descriptor_bytes

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "data/source_audits/d07"


def _assertion_fingerprint(raw: bytes) -> str:
    tree = ast.parse(raw)
    # The sole approved expected-value update is the truthful descriptor pin.
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and node.value == "358ded485e5c9aab3619b2ac06048820dbc60ad96443737f0a4d1a2e21a31536"
        ):
            node.value = "f1862a7da1e38e7cf5c68505b69d4ccd990a52cbd4b17145d0913730994fe83f"
    assertions = [
        ast.dump(node, include_attributes=False)
        for node in ast.walk(tree)
        if isinstance(node, ast.Assert)
    ]
    return hashlib.sha256(json.dumps(assertions, separators=(",", ":")).encode()).hexdigest()


def _decorator_fingerprint(raw: bytes) -> str:
    decorators = [
        (node.name, [ast.dump(d, include_attributes=False) for d in node.decorator_list])
        for node in ast.walk(ast.parse(raw))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    return hashlib.sha256(json.dumps(decorators, separators=(",", ":")).encode()).hexdigest()


def test_d07_complete_sources_archives_and_original_tests_remain_pinned() -> None:
    provenance = json.loads((ARCHIVE / "provenance.json").read_text(encoding="utf-8"))
    for path, pin in provenance["archives"].items():
        assert hashlib.sha256((ARCHIVE / path).read_bytes()).hexdigest() == pin["sha256"]
    source = (ARCHIVE / "selected-source.json").read_bytes()
    assert hashlib.sha256(source).hexdigest() == provenance["selected_source_sha256"]
    records = json.loads(source)["source_inventory"]
    assert {row["locator"] for row in records} == {"13.06", "02.05.01", "19.03"}
    for row in records:
        assert [block["ordinal"] for block in row["blocks"]] == list(
            range(1, len(row["blocks"]) + 1)
        )
        for block in row["blocks"]:
            raw = json.dumps(
                block["value"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
            assert hashlib.sha256(raw).hexdigest() == block["sha256"]
    maintenance_raw = (ARCHIVE / "fixture-identity-maintenance.json").read_bytes()
    assert hashlib.sha256(maintenance_raw).hexdigest() == provenance["fixture_maintenance_sha256"]
    maintenance = json.loads(maintenance_raw)
    approved = {row["path"]: row for row in maintenance["files"]}
    original_raw = (ARCHIVE / "original-tests.json").read_bytes()
    assert hashlib.sha256(original_raw).hexdigest() == provenance["original_tests_sha256"]
    originals = json.loads(original_raw)
    assert approved.keys() <= originals.keys()
    for path, digest in originals.items():
        raw = read_historical_test_bytes(ROOT, path).replace(b"\r\n", b"\n")
        raw = preserved_d09_predecessor_test_bytes(path, raw)
        current = hashlib.sha256(raw).hexdigest()
        if path in approved:
            pin = approved[path]
            assert digest == pin["before_sha256"]
            assert current == pin["after_sha256"]
            assert _assertion_fingerprint(raw) == pin["original_assertions_sha256"]
            assert _decorator_fingerprint(raw) == pin["original_decorators_sha256"]
        else:
            assert current == digest
    assert provenance["original_assertions_archives_branches_ceilings_preserved"]
    assert provenance["original_test_bytes_changed_under_explicit_identity_exception"]


def test_d07_valid_contact_history_uses_physical_model_and_authenticated_grants() -> None:
    path = ROOT / "src/warhammer40k_core/engine/base_contact_history.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "model_movement_terrain_context"
    ]
    assert len(calls) == 1
    assert {keyword.arg for keyword in calls[0].keywords} == {
        "model",
        "context",
        "granted_keywords",
    }
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "completion_choice"
        for node in ast.walk(tree)
    )


def test_d07_all_movement_consumers_bind_physical_model_and_history() -> None:
    consumers = {
        "base_contact_fight_history.py": 2,
        "charge_path_contexts.py": 1,
        "consolidation_model_constraints.py": 1,
        "fight_movement_paths.py": 1,
        "phases/movement_resolvers.py": 1,
        "scout_movement_paths.py": 1,
        "triggered_movement_resolution.py": 1,
    }
    for name, count in consumers.items():
        tree = ast.parse((ROOT / "src/warhammer40k_core/engine" / name).read_text(encoding="utf-8"))
        wrapped = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "model_movement_terrain_context"
        ]
        factories = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "to_terrain_path_legality_context"
        ]
        assert len(wrapped) == len(factories) == count
        assert all({"model", "context"} <= {k.arg for k in call.keywords} for call in wrapped)
        assert all(
            any(
                any(k.arg == "context" and k.value is factory for k in call.keywords)
                for call in wrapped
            )
            for factory in factories
        )


def test_d07_ruins_changes_only_the_monster_endpoint_token() -> None:
    path = "src/warhammer40k_core/core/ruleset_descriptor.py"
    old = ast.parse((ARCHIVE / "baseline" / (path + ".txt")).read_text(encoding="utf-8"))
    new = ast.parse(pre_section13_descriptor_bytes(ROOT))
    owners = [
        node
        for node in new.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_terrain_feature_movement_policies_for_eleventh"
    ]
    assert len(owners) == 1
    assignment = next(
        node
        for node in owners[0].body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "ruins_upper_floor_keywords"
            for target in node.targets
        )
    )
    assert isinstance(assignment.value, ast.Tuple)
    assert isinstance(assignment.value.elts[-1], ast.Constant)
    assert assignment.value.elts[-1].value == "MONSTER"
    assignment.value.elts.pop()
    assert ast.dump(new, include_attributes=False) == ast.dump(old, include_attributes=False)


def test_d07_native_geometry_rejection_owner_is_unchanged() -> None:
    path = "src/warhammer40k_core/engine/phases/movement_resolution_flow.py"
    old = (ARCHIVE / "baseline" / (path + ".txt")).read_text(encoding="utf-8")
    current = (ROOT / path).read_text(encoding="utf-8")
    assert ast.dump(ast.parse(current), include_attributes=False) == ast.dump(
        ast.parse(old), include_attributes=False
    )


def test_d07_upper_floor_owners_do_not_re_normalize_catalog_keyword_identity() -> None:
    owners = {
        "endpoint_placement.py": "terrain_endpoint_placement_violation",
        "model_movement_permission.py": "model_movement_terrain_context",
        "emergency_disembark_placement.py": "_setup_terrain",
    }
    for name, function in owners.items():
        tree = ast.parse((ROOT / "src/warhammer40k_core/engine" / name).read_text())
        owner = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == function
        )
        assert any(
            isinstance(node, ast.Attribute) and node.attr == "keywords" for node in ast.walk(owner)
        ), "Physical model catalog authority must remain explicit."
        assert not [
            node
            for node in ast.walk(owner)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"upper", "lower", "casefold", "replace"}
        ], "Gameplay permission must consume materialized canonical catalog tokens."
