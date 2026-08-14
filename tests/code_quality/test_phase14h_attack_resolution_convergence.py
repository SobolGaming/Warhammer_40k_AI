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
    "src/warhammer40k_core/engine/game_state.py",
    "src/warhammer40k_core/engine/phases/movement_fall_back_embark.py",
    "src/warhammer40k_core/engine/primary_unit_destruction_tracking.py",
}
PRIMARY_EVENT_DESTRUCTION_SHARED_OWNERS = {
    "src/warhammer40k_core/engine/battle_round_flow.py",
    "src/warhammer40k_core/engine/primary_unit_destruction_tracking.py",
}
UNATTRIBUTED_PRIMARY_DESTRUCTION_CAUSES_BY_CALLER = {
    "src/warhammer40k_core/engine/attack_sequence_destroyed_transport.py": ("EMERGENCY_DISEMBARK"),
    "src/warhammer40k_core/engine/game_state.py": "RESERVE_DEADLINE",
    "src/warhammer40k_core/engine/phases/movement_fall_back_embark.py": ("DESPERATE_ESCAPE"),
    "src/warhammer40k_core/engine/primary_unit_destruction_tracking.py": ("UNIT_COHERENCY"),
}
PRIMARY_DESTRUCTION_LEFT_BATTLEFIELD_BY_CALLER = {
    relative_path: relative_path != "src/warhammer40k_core/engine/game_state.py"
    for relative_path in PRIMARY_UNIT_DESTRUCTION_TRACKING_CALLERS
}
PRIMARY_BATTLEFIELD_DEPARTURE_CALLS = {
    "src/warhammer40k_core/engine/game_state.py": (
        "BattlefieldRemovalKind.INTO_RESERVES",
        "provider.occurrence_id",
    ),
    "src/warhammer40k_core/engine/phases/movement_fall_back_embark.py": (
        "BattlefieldRemovalKind.EMBARK",
        "result.result_id",
    ),
    "src/warhammer40k_core/engine/phases/movement_resolution_flow.py": (
        "BattlefieldRemovalKind.INTO_RESERVES",
        "result.result_id",
    ),
    "src/warhammer40k_core/engine/primary_unit_destruction_tracking.py": (
        "BattlefieldRemovalKind.DESTROYED",
        "edge_source_id",
    ),
}
PRIMARY_BATTLEFIELD_DEPARTURE_OCCURRENCES = {
    "src/warhammer40k_core/engine/game_state.py": "provider.occurrence_id",
    "src/warhammer40k_core/engine/phases/movement_fall_back_embark.py": "result.result_id",
    "src/warhammer40k_core/engine/phases/movement_resolution_flow.py": "result.result_id",
    "src/warhammer40k_core/engine/primary_unit_destruction_tracking.py": ("edge_occurrence_id"),
}
DIRECT_BATTLEFIELD_REMOVAL_CALL_COUNTS = {
    "with_removed_models": {
        "src/warhammer40k_core/engine/damage_allocation.py": 1,
        "src/warhammer40k_core/engine/fight_on_death.py": 1,
        "src/warhammer40k_core/engine/phases/movement_fall_back_embark.py": 1,
        "src/warhammer40k_core/engine/reserves.py": 1,
        "src/warhammer40k_core/engine/turn_cleanup.py": 1,
    },
    "with_unplaced_models_marked_removed": {
        "src/warhammer40k_core/engine/reserves.py": 1,
        "src/warhammer40k_core/engine/transports.py": 1,
    },
    "without_unit_placement": {
        "src/warhammer40k_core/engine/aircraft.py": 1,
        "src/warhammer40k_core/engine/prebattle.py": 1,
        "src/warhammer40k_core/engine/rules_unit_placement.py": 1,
        "src/warhammer40k_core/engine/transport_embark_groups.py": 1,
    },
    "without_from_battlefield": {
        "src/warhammer40k_core/engine/catalog_prebattle_redeploy.py": 1,
        "src/warhammer40k_core/engine/game_state.py": 1,
    },
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
        assert "source_rules_unit_objective_proximity_witness" in emitter_source
        assert "destroyed_rules_unit_objective_proximity_witness" in emitter_source


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
    for shared_function_name in (
        "record_primary_destroyed_model_departures",
        "record_primary_unit_destruction_for_logical_completion",
    ):
        shared_callers = {
            path.relative_to(ROOT).as_posix()
            for path in (SRC_ROOT / "engine").rglob("*.py")
            if any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == shared_function_name
                for node in ast.walk(ast_for(path))
            )
        }
        assert shared_callers == PRIMARY_EVENT_DESTRUCTION_SHARED_OWNERS
    for (
        relative_path,
        expected_left_battlefield,
    ) in PRIMARY_DESTRUCTION_LEFT_BATTLEFIELD_BY_CALLER.items():
        calls = tuple(
            node
            for node in ast.walk(ast_for(ROOT / relative_path))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "record_primary_unit_destructions_for_destroyed_models"
        )
        assert calls
        assert {
            keyword.value.value
            for call in calls
            for keyword in call.keywords
            if keyword.arg == "left_battlefield"
            and isinstance(keyword.value, ast.Constant)
            and isinstance(keyword.value.value, bool)
        } == {expected_left_battlefield}
    for relative_path, cause_name in UNATTRIBUTED_PRIMARY_DESTRUCTION_CAUSES_BY_CALLER.items():
        assert f"PrimaryUnattributedDestructionCause.{cause_name}" in source_for(
            ROOT / relative_path
        )
    assert "record_primary_unit_destructions_for_end_turn_cleanup" in source_for(
        SRC_ROOT / "engine" / "game_state.py"
    )


def test_primary_unit_destruction_tracking_uses_occurrence_identity() -> None:
    tracking_source = source_for(SRC_ROOT / "engine" / "primary_unit_destruction_tracking.py")
    departure_source = source_for(SRC_ROOT / "engine" / "primary_battlefield_departure.py")

    assert "existing_unit_ids" not in tracking_source
    assert "requested_occurrence_id" in tracking_source
    assert "edge_occurrence_id" in tracking_source
    assert "expected_departure_id" in tracking_source
    assert "expected.occurrence_id != edge_occurrence_id" in tracking_source
    assert "occurrence_source_id" in tracking_source
    assert "destruction.source_id == occurrence_source_id" in tracking_source
    assert "primary_unit_destruction_id(" in tracking_source
    assert "destruction_id drift" in tracking_source
    assert '"occurrence_id": requested_occurrence_id' in departure_source
    assert "occurrence_id=requested_occurrence_id" in departure_source


def test_primary_battlefield_departure_callers_and_provenance_are_fail_closed() -> None:
    calls_by_path: dict[str, list[ast.Call]] = {}
    for path in (SRC_ROOT / "engine").rglob("*.py"):
        calls = [
            node
            for node in ast.walk(ast_for(path))
            if isinstance(node, ast.Call)
            and (
                (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "record_primary_battlefield_departure"
                )
                or (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "record_primary_battlefield_departure"
                )
            )
        ]
        if calls:
            calls_by_path[path.relative_to(ROOT).as_posix()] = calls

    assert set(calls_by_path) == set(PRIMARY_BATTLEFIELD_DEPARTURE_CALLS)
    required_keywords = {
        "state",
        "rules_unit_instance_id",
        "affected_component_unit_instance_ids",
        "departed_component_unit_instance_ids",
        "removed_model_instance_ids",
        "removal_kind",
        "occurrence_id",
        "source_id",
    }
    for relative_path, (
        expected_kind,
        expected_source,
    ) in PRIMARY_BATTLEFIELD_DEPARTURE_CALLS.items():
        calls = calls_by_path[relative_path]
        assert len(calls) == 1
        keyword_expressions = {
            keyword.arg: ast.unparse(keyword.value)
            for keyword in calls[0].keywords
            if keyword.arg is not None
        }
        assert set(keyword_expressions) == required_keywords
        assert keyword_expressions["removal_kind"] == expected_kind
        assert keyword_expressions["source_id"] == expected_source
        assert (
            keyword_expressions["occurrence_id"]
            == (PRIMARY_BATTLEFIELD_DEPARTURE_OCCURRENCES[relative_path])
        )


def test_battlefield_removal_owners_converge_or_are_explicitly_prebattle() -> None:
    calls_by_method: dict[str, dict[str, int]] = {
        method_name: {} for method_name in DIRECT_BATTLEFIELD_REMOVAL_CALL_COUNTS
    }
    for path in (SRC_ROOT / "engine").rglob("*.py"):
        relative_path = path.relative_to(ROOT).as_posix()
        tree = ast_for(path)
        for method_name in calls_by_method:
            count = sum(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == method_name
                for node in ast.walk(tree)
            )
            if count:
                calls_by_method[method_name][relative_path] = count

    assert calls_by_method == DIRECT_BATTLEFIELD_REMOVAL_CALL_COUNTS

    aircraft_source = source_for(SRC_ROOT / "engine" / "aircraft.py")
    aircraft_owner_source = source_for(
        SRC_ROOT / "engine" / "phases" / "movement_resolution_flow.py"
    )
    assert "BattlefieldRemovalKind.INTO_RESERVES" in aircraft_source
    assert "source_event_id=source_event_id" in aircraft_source
    assert "source_event_id=result.result_id" in aircraft_owner_source
    assert "apply_aircraft_reserve_transition_to_battlefield(" in aircraft_owner_source
    assert "record_primary_battlefield_departure(" in aircraft_owner_source

    embark_helper_source = source_for(SRC_ROOT / "engine" / "transport_embark_groups.py")
    embark_owner_source = source_for(
        SRC_ROOT / "engine" / "phases" / "movement_fall_back_embark.py"
    )
    assert "BattlefieldRemovalKind.EMBARK" in embark_helper_source
    assert "apply_embark_to_battlefield(" in embark_owner_source
    assert "record_primary_battlefield_departure(" in embark_owner_source

    reserve_owner_source = source_for(SRC_ROOT / "engine" / "game_state.py")
    assert "rules_unit_placement.without_from_battlefield(self.battlefield_state)" in (
        reserve_owner_source
    )
    assert "record_primary_battlefield_departure(" in reserve_owner_source

    # Every destructive placement mutation converges on either the shared
    # model-destroyed event owner or an explicit unattributed transition owner.
    damage_source = source_for(SRC_ROOT / "engine" / "damage_allocation.py")
    battle_round_source = source_for(SRC_ROOT / "engine" / "battle_round_flow.py")
    fight_on_death_source = source_for(SRC_ROOT / "engine" / "fight_on_death.py")
    fall_back_source = source_for(SRC_ROOT / "engine" / "phases" / "movement_fall_back_embark.py")
    reserve_source = source_for(SRC_ROOT / "engine" / "reserves.py")
    cleanup_source = source_for(SRC_ROOT / "engine" / "turn_cleanup.py")
    assert "_remove_destroyed_model(" in damage_source
    assert "remove_models_awaiting_fight_on_death(" in fight_on_death_source
    assert "remove_models_awaiting_fight_on_death(state=state)" in battle_round_source
    assert "record_primary_destroyed_model_departures(" in battle_round_source
    assert "record_primary_unit_destruction_for_logical_completion(" in battle_round_source
    assert "record_primary_unit_destructions_for_destroyed_models(" not in battle_round_source
    assert "PrimaryUnattributedDestructionCause.DESPERATE_ESCAPE" in fall_back_source
    assert "apply_reserve_destruction_to_battlefield(" in reserve_source
    assert "PrimaryUnattributedDestructionCause.RESERVE_DEADLINE" in reserve_owner_source
    assert "CoherencyCleanupRemoval(" in cleanup_source
    assert "self._resolve_end_turn_cleanup_boundary(completed_phase=completed_phase)" in (
        reserve_owner_source
    )
    assert "record_primary_unit_destructions_for_end_turn_cleanup(state=self, cleanup=cleanup)" in (
        reserve_owner_source
    )
    assert "record_primary_unit_destructions_for_end_turn_cleanup(" in reserve_owner_source

    # Redeploy removes and replaces the same models inside one pre-battle operation.
    # TEMPORARILY_REMOVED therefore is not a historical battlefield departure.
    prebattle_source = source_for(SRC_ROOT / "engine" / "prebattle.py")
    assert "BattlefieldRemovalKind.TEMPORARILY_REMOVED" in prebattle_source
    assert "battlefield.without_unit_placement(" in prebattle_source
    assert "battlefield.with_added_unit_placement(" in prebattle_source
    assert "record_primary_battlefield_departure(" not in prebattle_source

    # Redeploy-to-reserves also occurs during setup, before turn-start history exists.
    setup_reserve_source = source_for(SRC_ROOT / "engine" / "catalog_prebattle_redeploy.py")
    assert "state.stage is not GameLifecycleStage.SETUP" in setup_reserve_source
    assert "SetupStep.REDEPLOY_UNITS" in setup_reserve_source
    assert "record_primary_battlefield_departure(" not in setup_reserve_source
