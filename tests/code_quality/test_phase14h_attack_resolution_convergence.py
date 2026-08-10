from __future__ import annotations

import ast
from pathlib import Path

from tests.code_quality.source_index import ast_for, source_for

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src" / "warhammer40k_core"
ATTACK_SEQUENCE_PATH = ROOT / "src" / "warhammer40k_core" / "engine" / "attack_sequence.py"
ATTACK_SEQUENCE_SPLIT_PATHS = tuple(sorted(ATTACK_SEQUENCE_PATH.parent.glob("attack_sequence*.py")))
MODEL_DESTROYED_EMITTER_PATHS = {
    "src/warhammer40k_core/engine/attack_sequence_hit_wound.py",
    "src/warhammer40k_core/engine/mortal_wound_destruction_evidence.py",
    "src/warhammer40k_core/engine/rule_model_destruction.py",
}
PRIMARY_UNIT_DESTRUCTION_TRACKING_CALLERS = {
    "src/warhammer40k_core/engine/attack_sequence_destroyed_transport.py",
    "src/warhammer40k_core/engine/battle_round_flow.py",
    "src/warhammer40k_core/engine/phases/movement_fall_back_embark.py",
    "src/warhammer40k_core/engine/primary_unit_destruction_tracking.py",
}


def test_phase14h_single_save_resolution_entry_point() -> None:
    trees = tuple(ast_for(path) for path in ATTACK_SEQUENCE_SPLIT_PATHS)
    function_names = {
        node.name for tree in trees for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }

    retired_symbols = {
        "_resolve_save_and_damage",
        "_resolve_allocation_stage",
        "_continue_after_allocation_group",
        "_attack_pool_can_use_grouped_allocation_host",
        "_allocation_group_has_interrupting_damage_choices",
    }
    assert function_names.isdisjoint(retired_symbols)
    assert "_resolve_grouped_damage_from" in function_names

    saving_throw_callers: list[str] = []
    for tree in trees:
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "resolve_saving_throw"
                for child in ast.walk(node)
            ):
                saving_throw_callers.append(node.name)

    assert saving_throw_callers == ["_resolve_grouped_damage_from"]


def test_phase14h_retired_attack_allocation_surface_is_absent() -> None:
    retired_text = (
        "select_attack_allocation",
        "SELECT_ATTACK_ALLOCATION_DECISION_TYPE",
        "AttackAllocationDecision",
        "build_attack_allocation_request",
    )
    offenders: list[str] = []
    for path in SRC_ROOT.rglob("*.py"):
        text = source_for(path)
        if any(symbol in text for symbol in retired_text):
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_model_destruction_emitters_remain_converged_on_typed_evidence() -> None:
    emitters: set[str] = set()
    for path in (SRC_ROOT / "engine").rglob("*.py"):
        tree = ast_for(path)
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "append"
            and bool(node.args)
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "model_destroyed"
            for node in ast.walk(tree)
        ):
            emitters.add(path.relative_to(ROOT).as_posix())

    assert emitters == MODEL_DESTROYED_EMITTER_PATHS
    for relative_path in MODEL_DESTROYED_EMITTER_PATHS:
        emitter_source = source_for(ROOT / relative_path)
        assert "ModelDestructionAttribution" in emitter_source
        assert "transition_batch" in emitter_source


def test_primary_unit_destruction_tracking_covers_event_and_transition_owners() -> None:
    callers: set[str] = set()
    for path in (SRC_ROOT / "engine").rglob("*.py"):
        tree = ast_for(path)
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "record_primary_unit_destructions_for_destroyed_models"
            for node in ast.walk(tree)
        ):
            callers.add(path.relative_to(ROOT).as_posix())

    assert callers == PRIMARY_UNIT_DESTRUCTION_TRACKING_CALLERS
    assert "record_primary_unit_destructions_for_end_turn_cleanup" in source_for(
        SRC_ROOT / "engine" / "game_state.py"
    )


def test_primary_unit_destruction_tracking_uses_occurrence_identity() -> None:
    tracking_source = source_for(SRC_ROOT / "engine" / "primary_unit_destruction_tracking.py")

    assert "existing_unit_ids" not in tracking_source
    assert "existing_occurrences" in tracking_source
    assert "primary_unit_destruction_id(" in tracking_source
    assert "destruction_id drift" in tracking_source
