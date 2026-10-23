"""Authenticate live successors before exposing immutable pre-migration evidence."""

from __future__ import annotations

import ast
import collections
import copy
import hashlib
import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import TypedDict, cast

from tests.support.faction_layout_preservation import (
    ORIGINALS as FACTION_LAYOUT_ORIGINALS,
)
from tests.support.faction_layout_preservation import (
    layout_live_reference,
    verify_layout_original,
)
from tests.support.section13_preservation import preserved_section13_golden_bytes

MANIFEST = "data/source_audits/category_migration/preservation.json"
MANIFEST_SHA256 = "b19ad632479d97f4d0624bbdeb2bc8c9c42bc351fcfd4a0894b499791e149438"
UTF8_TEST = "tests/code_quality/test_order97_inventory.py"
UTF8_ARCHIVE = "docs/performance/policy-v3/ci-compatibility-20261015/order97-original.py.txt"
UTF8_BEFORE_SHA256 = "78697c357cf227480a58cf22d2f1d201e621d1cb3e7c0e1631151613bacf3955"
UTF8_AFTER_SHA256 = "7b4ce6c6d14243afe9f08fedf616e867f9555a5101e98de45bad130f66f32a99"
EDITION_TEST = "tests/code_quality/test_phase14a_source_identity.py"
EDITION_ARCHIVE = "docs/performance/policy-v3/ci-compatibility-20261015/phase14a-original.py.txt"
EDITION_BEFORE_SHA256 = "22146cd184b4267c71b482cba021cd31387c8df1bd4a0d27f1157647cbc93e8b"
EDITION_AFTER_SHA256 = "d67b860dbe557bd557536537d43c466176e2e6d14e1e48d6b8c08c1cb4d34eaf"
MIGRATED_PATHS: frozenset[str] = frozenset(
    [
        "tests/integration/test_horror_split_materialization.py",
        "tests/integration/test_ws14_generic_ir_lifecycle.py",
        "tests/unit/reporting/test_runtime_consumer_evidence.py",
        "tests/unit/reporting/test_support_evidence_inventories.py",
        "tests/unit/test_generic_ir_support_validation.py",
        "tests/unit/test_generic_rule_ability_registry.py",
        "tests/unit/test_generic_rule_effect_identity.py",
        "tests/unit/test_lifecycle_hooks.py",
        "tests/unit/test_order135_tactical_setup_proof.py",
        "tests/unit/test_order54_setup.py",
        "tests/unit/test_order86_table_quarters.py",
        "tests/unit/test_order97_facade_evidence.py",
        "tests/unit/test_order98_source_reconciliation.py",
        "tests/unit/test_phase10d_battlefield_transitions.py",
        "tests/unit/test_phase11a_mission_pack.py",
        "tests/unit/test_phase11e_mission_scoring_cleanup.py",
        "tests/unit/test_phase11f_game_end_scoring.py",
        "tests/unit/test_phase12d_ability_registry.py",
        "tests/unit/test_phase14a_source_identity.py",
        "tests/unit/test_phase16a_deployment.py",
        "tests/unit/test_phase16b_prebattle.py",
        "tests/unit/test_phase16e_setup_completion.py",
        "tests/unit/test_phase17_source_overlays.py",
        "tests/unit/test_phase17a1_transition_patches.py",
        "tests/unit/test_phase17d_rule_execution.py",
        "tests/unit/test_phase17g_black_templars_army_rule.py",
        "tests/unit/test_phase17g_runtime_content.py",
        "tests/unit/test_phase17i_blocked_row_classification.py",
        "tests/unit/test_phase17i_named_handler_budget.py",
        "tests/unit/test_phase17j_event_companion.py",
        "tests/unit/test_phase17n_boundary_checkpoint_physical_authority.py",
        "tests/unit/test_phase17n_boundary_checkpoint_redaction.py",
        "tests/unit/test_phase17n_pending_request_integrity.py",
        "tests/unit/test_phase17n_primary_scoring_boundary_lifecycle.py",
        "tests/unit/test_phase17n_primary_scoring_conditions.py",
        "tests/unit/test_phase17n_primary_scoring_grammar.py",
        "tests/unit/test_phase17n_primary_scoring_position_history_integrity.py",
        "tests/unit/test_phase17n_primary_scoring_spatial_evidence.py",
        "tests/unit/test_phase17n_primary_scoring_state_bridge.py",
        "tests/unit/test_phase17n_step5b_marker_conditions.py",
        "tests/unit/test_phase17n_step5d_condemned_departure_conditions.py",
        "tests/unit/test_phase17n_step5e_operation_marker_conditions.py",
        "tests/unit/test_phase17n_step5f_surveil_conditions.py",
        "tests/unit/test_phase17n_step5g_pairing_certification.py",
        "tests/unit/test_phase17n_step5g_pairing_certification_layout_b.py",
        "tests/unit/test_phase17n_step5g_pairing_certification_layout_c.py",
        "tests/unit/test_phase17n_step6g_secondary_certification.py",
        "tests/unit/test_phase17n_step6g_secondary_certification_a_grievous_through_beacon.py",
        "tests/unit/test_phase17n_step6g_secondary_certification_behind_through_cleanse.py",
        "tests/unit/test_phase17n_step6g_secondary_certification_defend_through_forward.py",
        "tests/unit/test_phase17n_step6g_secondary_certification_no_prisoners_through_secure.py",
        "tests/unit/test_phase18b_opportunity_windows.py",
        "tests/unit/test_phase18f_session_commands.py",
        "tests/unit/test_phase18g_18h_session_security.py",
        "tests/unit/test_phase18l_session_persistence.py",
        "tests/unit/test_phase9b_lifecycle.py",
        "tests/unit/test_physical_proposal_prevalidation.py",
        "tests/unit/test_return_on_death.py",
        "tests/unit/test_rule_text_normalization.py",
        "tests/unit/test_ruleset_descriptor.py",
        "tests/unit/test_runtime_hook_bindings.py",
        "tests/unit/test_s25_applicability_inventory.py",
        "tests/unit/test_s25_characteristic_profile_gates.py",
        "tests/unit/test_s25_permission_relevance.py",
        "tests/unit/test_secondary_scoring_state_evidence_authority.py",
        "tests/unit/test_tracked_targets.py",
        "tests/unit/test_unit_rule_effects.py",
        "tests/unit/test_unit_splitting.py",
    ]
)


class MigrationRecord(TypedDict):
    archive: str
    original_sha256: str
    successors: dict[str, str]
    support_modules: list[str]
    definitions: dict[str, str]


class MigrationManifest(TypedDict):
    schema: str
    originals: dict[str, MigrationRecord]
    definitions_by_successor: dict[str, list[str]]


def _read(root: Path, relative: str) -> bytes:
    name = Path(relative)
    if name.is_absolute() or ".." in name.parts:
        raise ValueError("Migration evidence path is outside its declared root.")
    path = root / name
    if path.resolve() != path.absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Migration evidence cannot use a symbolic alias or escape its root.")
    return path.read_bytes()


type FrozenManifest = tuple[Mapping[str, str], Mapping[str, tuple[str, ...]]]


@lru_cache(maxsize=4)
def _frozen_manifest(raw: bytes) -> FrozenManifest:
    result = cast(MigrationManifest, json.loads(raw))
    if result["schema"] != "category-migration-preservation-v1":
        raise ValueError("Unknown migration preservation schema.")
    records = MappingProxyType(
        {path: json.dumps(record) for path, record in result["originals"].items()}
    )
    definitions = MappingProxyType(
        {path: tuple(names) for path, names in result["definitions_by_successor"].items()}
    )
    return records, definitions


def _manifest(raw: bytes) -> FrozenManifest:
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError("Migration preservation manifest drifted.")
    result = _frozen_manifest(raw)
    if set(result[0]) != set(MIGRATED_PATHS):
        raise ValueError("Migration preservation registry is incomplete.")
    return result


class _RepositoryAnchor(ast.NodeTransformer):
    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        expected = ast.parse("Path(__file__).resolve().parents[2]", mode="eval").body
        if ast.dump(node) == ast.dump(expected):
            return ast.copy_location(ast.Name(id="REPOSITORY_ROOT", ctx=ast.Load()), node)
        return self.generic_visit(node)


def _normalized(node: ast.AST, *, original: bool) -> ast.AST:
    result = copy.deepcopy(node)
    if original:
        result = _RepositoryAnchor().visit(result)
    for value in ast.walk(result):
        if isinstance(value, (ast.Import, ast.ImportFrom)):
            for alias in value.names:
                if alias.asname == alias.name:
                    alias.asname = None
    return result


@lru_cache(maxsize=512)
def _definitions(raw: bytes, original: bool) -> tuple[tuple[str, str], ...]:
    result: dict[str, str] = {}
    for node in ast.parse(raw).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in result:
                raise ValueError("Duplicate migration successor definition.")
            result[node.name] = ast.dump(_normalized(node, original=original))
    return tuple(result.items())


def _exports(node: ast.AST) -> bool:
    if isinstance(node, ast.AnnAssign):
        return isinstance(node.target, ast.Name) and node.target.id == "__all__"
    if isinstance(node, ast.Assign):
        return any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        )
    return (
        isinstance(node, ast.AugAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "__all__"
    )


@lru_cache(maxsize=512)
def _initializers(raw: bytes, original: bool, preserve_exports: bool) -> tuple[str, ...]:
    result: list[str] = []
    for value in ast.parse(raw).body:
        node = _normalized(value, original=original)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue
        if _exports(node):
            continue
        if isinstance(node, ast.ImportFrom) and (
            node.module in {"__future__", "tests.shared.repository_root"}
            or (node.module or "").startswith("tests.shared.category_migration")
        ):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                result.append(
                    repr(
                        (
                            type(node).__name__,
                            node.module if isinstance(node, ast.ImportFrom) else None,
                            node.level if isinstance(node, ast.ImportFrom) else 0,
                            alias.name,
                            alias.asname,
                        )
                    )
                )
        else:
            result.append(ast.dump(node))
    return tuple(result)


INTEGRATION_PREIMAGES: dict[str, tuple[str, str, str]] = {
    "tests/unit/test_phase11e_mission_scoring_cleanup.py": (
        "data/source_audits/integration_2026_10_19/migration/tests/unit/test_phase11e_mission_scoring_cleanup.py.before.py.txt",
        "5704133047a16d4606d2f1160b5cddffd139d1c61d0af3c6f156893db6cf2b1e",
        "008b0b412980a292b956fae4fa4bccb79d2f403a9c3e89cf168e63a7d3e14ecb",
    ),
    "tests/unit/test_phase17_source_overlays.py": (
        "data/source_audits/integration_2026_10_19/migration/tests/unit/test_phase17_source_overlays.py.before.py.txt",
        "7c9b7975b79a88b8c4f6e9b2aaf65331bb06e4f7ce7b9e62dbe50867fb80e20b",
        "f035cb204d30032784e3b9daa599485bc82561e5bc5e7503f55f4e9e0eeeac22",
    ),
    "tests/unit/test_phase17n_primary_scoring_spatial_evidence.py": (
        "data/source_audits/integration_2026_10_19/migration/tests/unit/test_phase17n_primary_scoring_spatial_evidence.py.before.py.txt",
        "7b6276643dc3f2683fbebb0368faa29fb399840c630e23595ca840e93f4046ab",
        "2a846f2f5a2373b03abc0ecfff5f311c274bfd573002e7ee22190558b10ed6a2",
    ),
}


INTEGRATION_OVERLAY_ADDITIONS = (
    "data/source_audits/integration_2026_10_19/migration/source-overlays-accepted-additions.py.txt",
    "45d376633291ee88c17385c4ae58d98fb9309202e921036a7b982813ba404814",
)


def assert_integration_migration_ast(
    path: str, before: bytes, current: bytes, *, root: Path | None = None
) -> None:
    """Allow only the independently reviewed fixture/preservation changes."""
    if path == "tests/unit/test_phase17_source_overlays.py":
        actual_root = Path(__file__).resolve().parents[1] if root is None else root
        archive, digest = INTEGRATION_OVERLAY_ADDITIONS
        additions = _read(actual_root, archive)
        if hashlib.sha256(additions).hexdigest() != digest:
            raise ValueError("Exact additive source-index tests drifted.")
        expected_definitions = dict(_definitions(before, False))
        added_definitions = dict(_definitions(additions, False))
        if len(added_definitions) != 10 or expected_definitions.keys() & added_definitions.keys():
            raise ValueError("Additive source-index definition membership drifted.")
        expected_definitions.update(added_definitions)
        if expected_definitions != dict(_definitions(current, False)) or (
            collections.Counter(_initializers(before, False, False))
            + collections.Counter(_initializers(additions, False, False))
            != collections.Counter(_initializers(current, False, False))
        ):
            raise ValueError("Integration source-overlay AST or initialization drifted.")
        return
    expected, actual = ast.parse(before), ast.parse(current)

    def function(name: str) -> ast.FunctionDef:
        matches = [n for n in expected.body if isinstance(n, ast.FunctionDef) and n.name == name]
        if len(matches) != 1:
            raise ValueError("Integration fixture function membership drifted.")
        return matches[0]

    def replace_statement(owner: ast.FunctionDef, old: str, new: str) -> None:
        wanted = ast.dump(ast.parse(old).body[0])
        matches = [i for i, n in enumerate(owner.body) if ast.dump(n) == wanted]
        if len(matches) != 1:
            raise ValueError("Integration literal fixture preimage drifted.")
        index = matches[0]
        owner.body[index : index + 1] = ast.parse(new).body

    if path == "tests/unit/test_phase17n_primary_scoring_spatial_evidence.py":
        owner = function("test_primary_spatial_evidence_counts_survivors_after_coherency_cleanup")
        calls = [
            n
            for n in ast.walk(owner)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "resolve_end_turn_cleanup"
        ]
        if len(calls) != 1 or any(k.arg == "chosen_model_instance_ids" for k in calls[0].keywords):
            raise ValueError("Integration selected-casualty fixture preimage drifted.")
        calls[0].keywords.append(
            ast.keyword(
                arg="chosen_model_instance_ids",
                value=ast.parse("(isolated.model_instance_id,)", mode="eval").body,
            )
        )
    elif path == "tests/unit/test_phase11e_mission_scoring_cleanup.py":
        owner = function(
            "test_end_turn_coherency_cleanup_removes_models_without_destroyed_triggers"
        )
        replace_statement(
            owner,
            "assert status.status_kind in {LifecycleStatusKind.WAITING_FOR_DECISION, "
            "LifecycleStatusKind.TERMINAL}",
            """
assert status.status_kind in {
    LifecycleStatusKind.WAITING_FOR_DECISION, LifecycleStatusKind.TERMINAL
}
request = lifecycle.pending_decision_request()
assert request is not None
assert request.decision_type == "select_coherency_casualty"
assert request.actor_id == "player-a"
assert {option.option_id for option in request.options} == {
    row.model_instance_id for row in broken.model_placements
}
assert removed_model_id not in state.battlefield_state.removed_model_ids
status = lifecycle.submit_decision(DecisionResult.for_request(
    request=request, result_id="explicit-coherency-choice", selected_option_id=removed_model_id
))
""",
        )
        matches = [
            n
            for n in ast.walk(owner)
            if isinstance(n, ast.keyword)
            and n.arg == "match"
            and isinstance(n.value, ast.Constant)
            and n.value.value
            == "Unit Coherency departure requires an authoritative phase-boundary event"
        ]
        if len(matches) != 1:
            raise ValueError("Original phase-boundary rejection assertion drifted.")
        # The archived mutation remains intact. Independent review reproduced this
        # current typed rejection; the original literal stays in the pinned archive.
        matches[0].value = ast.Constant(
            "ObjectiveControlRecord phase-start history lacks exactly one prior "
            "completed phase event"
        )
        owner.body.extend(
            ast.parse("""
forged_payload = cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
forged_events = forged_payload["decisions"]["event_log"]
for event in forged_events:
    if event["event_type"] == "coherency_cleanup_model_removed":
        event["event_type"] = "battle_phase_boundary_tampered"
with pytest.raises(
    GameLifecycleError, match="Coherency casualty requires one preceding owner decision"
):
    GameLifecycle.from_payload(forged_payload)
""").body
        )
        owner = function("test_turn_end_control_and_primary_scoring_use_pre_cleanup_battlefield")
        replace_statement(
            owner,
            'state = _battle_state_for_primary("primary-immovable-object")',
            """
lifecycle = _battle_lifecycle_for_primary("primary-immovable-object")
state = lifecycle.state
assert state is not None
""",
        )
        replace_statement(
            owner,
            "state.advance_to_next_battle_phase()",
            """
status = lifecycle.advance_until_decision_or_terminal()
status = _decline_stratagem_window_if_pending(lifecycle, status, result_id="control-decline")
request = lifecycle.pending_decision_request()
assert request is not None
assert request.decision_type == "select_coherency_casualty"
assert isolated_objective_model_id not in state.battlefield_state.removed_model_ids
lifecycle.submit_decision(DecisionResult.for_request(
    request=request, result_id="control-chosen", selected_option_id=isolated_objective_model_id
))
""",
        )
    else:
        raise ValueError("Unknown integration fixture preservation path.")
    if ast.dump(actual) != ast.dump(expected):
        raise ValueError("Integration whole-module assertion or fixture AST drifted.")


def _integration_migration_predecessor(root: Path, path: str, current: bytes) -> bytes:
    if path not in INTEGRATION_PREIMAGES:
        return current
    archive, before_hash, current_hash = INTEGRATION_PREIMAGES[path]
    before = _read(root, archive)
    if (
        hashlib.sha256(before).hexdigest() != before_hash
        or hashlib.sha256(current).hexdigest() != current_hash
    ):
        raise ValueError("Exact integration fixture or predecessor bytes drifted.")
    assert_integration_migration_ast(path, before, current, root=root)
    return before


def verify_migrated_test(root: Path, relative: str) -> tuple[bytes, MigrationRecord]:
    """Read current bytes every time; cache only immutable AST fingerprints by bytes."""
    if relative not in MIGRATED_PATHS:
        raise ValueError("Unknown migrated test path: " + relative)
    records, definition_membership = _manifest(_read(root, MANIFEST))
    record = cast(MigrationRecord, json.loads(records[relative]))
    original = _read(root, record["archive"])
    if hashlib.sha256(original).hexdigest() != record["original_sha256"]:
        raise ValueError("Original migrated test archive drifted: " + relative)
    current: dict[str, bytes] = {}
    for path, expected in record["successors"].items():
        raw = preserved_section13_golden_bytes(
            root, path, _integration_migration_predecessor(root, path, _read(root, path))
        )
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Live migration successor bytes drifted: " + path)
        current[path] = raw
        if path in definition_membership and set(dict(_definitions(raw, False))) != set(
            definition_membership[path]
        ):
            raise ValueError("Live successor definition membership changed: " + path)
    old_definitions = dict(_definitions(original, True))
    if old_definitions.keys() != record["definitions"].keys():
        raise ValueError("Original migration definition membership changed: " + relative)
    for name, successor in record["definitions"].items():
        path, target_name = successor.split("::", 1)
        if dict(_definitions(current[path], False))[target_name] != old_definitions[name]:
            raise ValueError(
                "Original test/helper/assertion/decorator semantics changed: " + successor
            )
    preserve_exports = any(_exports(node) for node in ast.parse(original).body)
    before = collections.Counter(_initializers(original, True, preserve_exports))
    after = sum(
        (
            collections.Counter(_initializers(current[path], False, preserve_exports))
            for path in record["support_modules"]
        ),
        collections.Counter[str](),
    )
    if before != after:
        raise ValueError("Original module initialization/import bindings changed: " + relative)
    return original, record


def read_historical_test_bytes(root: Path, relative: str) -> bytes:
    """Historical readers alone may request predecessor bytes after live verification."""
    if relative in FACTION_LAYOUT_ORIGINALS:
        return verify_layout_original(root, relative)[0]
    if relative == EDITION_TEST:
        current = _read(root, relative).replace(b"\r\n", b"\n")
        original = _read(root, EDITION_ARCHIVE)
        if (
            hashlib.sha256(current).hexdigest() != EDITION_AFTER_SHA256
            or hashlib.sha256(original).hexdigest() != EDITION_BEFORE_SHA256
        ):
            raise ValueError("Exact edition-scanner maintenance bytes changed.")
        before = b'_without_non_edition_references(path.read_text(encoding="utf-8"))'
        after = b"_without_non_edition_references(_active_identity_text(path))"
        if current.count(after) != 1:
            raise ValueError("Exact edition-scanner maintenance call changed.")
        old_tree = ast.parse(original)
        new_tree = ast.parse(current.replace(after, before, 1))
        additions = {
            "_active_identity_text",
            "test_historical_report_keys_are_scoped_to_exact_reviewed_document",
            "test_historical_report_identity_exception_rejects_any_byte_drift",
            "test_historical_report_does_not_exempt_other_active_documents",
        }
        if {
            node.name
            for node in new_tree.body
            if isinstance(node, ast.FunctionDef) and node.name in additions
        } != additions:
            raise ValueError("Edition-scanner maintenance controls are incomplete.")
        new_tree.body = [
            node
            for node in new_tree.body
            if not (isinstance(node, ast.FunctionDef) and node.name in additions)
        ]
        if ast.dump(new_tree) != ast.dump(old_tree):
            raise ValueError("Original edition assertions or unrelated semantics changed.")
        return original
    if relative == UTF8_TEST:
        current = _read(root, relative).replace(b"\r\n", b"\n")
        original = _read(root, UTF8_ARCHIVE)
        before = b"audit.REPORT.read_text() == audit.markdown(inventory)"
        after = b'audit.REPORT.read_text(encoding="utf-8") == audit.markdown(inventory)'
        if (
            hashlib.sha256(current).hexdigest() != UTF8_AFTER_SHA256
            or hashlib.sha256(original).hexdigest() != UTF8_BEFORE_SHA256
            or original.count(before) != 1
            or original.replace(before, after, 1) != current
        ):
            raise ValueError("Exact Order97 UTF-8-only maintenance proof changed.")
        return original
    if relative in MIGRATED_PATHS:
        return verify_migrated_test(root, relative)[0]
    return _read(root, relative)


def live_test_reference(root: Path, reference: str) -> str:
    """Live audits follow the real current node; they never parse an archival substitute."""
    path, separator, name = reference.partition("::")
    if path in FACTION_LAYOUT_ORIGINALS:
        return layout_live_reference(root, reference)
    if path not in MIGRATED_PATHS:
        return reference
    if not separator or not name:
        raise ValueError("A live migrated reference needs a complete test or helper node.")
    _, record = verify_migrated_test(root, path)
    outer, *nested = name.split("::")
    if outer not in record["definitions"]:
        raise ValueError("Unknown migrated test definition: " + reference)
    return "::".join((record["definitions"][outer], *nested))
