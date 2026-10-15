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

MANIFEST = "data/source_audits/category_migration/preservation.json"
MANIFEST_SHA256 = "3214a0f3951b6fb921cd09e71bea7f741c06ba06a214db4f4573da5bd7d644e5"
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
        raw = _read(root, path)
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
    if path not in MIGRATED_PATHS:
        return reference
    if not separator or not name:
        raise ValueError("A live migrated reference needs a complete test or helper node.")
    _, record = verify_migrated_test(root, path)
    outer, *nested = name.split("::")
    if outer not in record["definitions"]:
        raise ValueError("Unknown migrated test definition: " + reference)
    return "::".join((record["definitions"][outer], *nested))
