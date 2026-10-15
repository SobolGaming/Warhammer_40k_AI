from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from tests.phase11c_command_phase_helpers import (
    army_muster_request,
    complete_setup_through_gate,
    default_unit_selection,
    mustered_armies,
    phase11c_config,
    unit_selection,
)
from tests.phase17n_primary_mission_helpers import phase17n_state_with_setup
from tests.phase17n_secondary_certification_fixtures import (
    TURN_CAP_TACTICAL_IDS,
    certification_unit_selections,
    seed_sequential_tactical_turn_cap_conditions,
)
from tests.phase17n_secondary_mission_helpers import resolved_secondary_mission_selection_for_card
from tests.phase17n_step6g_secondary_certification_helpers import STEP6G_LAYOUT_ROW as _LAYOUT_ROW
from tests.phase17n_step6g_secondary_certification_helpers import (
    STEP6G_LIFECYCLE_CERTIFICATION_ROWS as _LIFECYCLE_CERTIFICATION_ROWS,
)
from tests.phase17n_step6g_secondary_certification_helpers import (
    STEP6G_MISSION_PARTITIONS,
    step6g_matrix_case_keys,
)
from tests.phase17n_step6g_secondary_certification_helpers import (
    STEP6G_SCORING_PLAYER_IDS as _SCORING_PLAYER_IDS,
)
from tests.phase17n_step6g_secondary_certification_helpers import (
    configured_step6g_lifecycle as _configured_step6g_lifecycle,
)
from tests.phase17n_step6g_secondary_certification_helpers import lifecycle_row as _lifecycle_row
from tests.phase17n_step6g_secondary_certification_helpers import (
    score_certified_row_from_state as _score_certified_row_from_state,
)
from tests.phase17n_step6g_secondary_certification_helpers import (
    secondary_transactions as _secondary_transactions,
)
from tests.phase17n_step6g_secondary_certification_helpers import (
    seed_completed_fight_phase as _seed_completed_fight_phase,
)
from tests.phase17n_step6g_secondary_certification_helpers import (
    setup_for_layout as _setup_for_layout,
)
from tests.secondary_destruction_helpers import record_secondary_destruction_for_fixture
from tests.secondary_when_drawn_rules_unit_helpers import (
    RulesUnitPresence,
    attached_when_drawn_state,
    record_unresolved_when_drawn_card,
)
from tests.setup_completion_helpers import (
    record_existing_primary_turn_start_evidence_events_for_fixture,
    record_primary_turn_start_evidence_for_fixture,
)
from warhammer40k_core.adapters.contracts import FiniteOptionSubmission
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition, ObjectiveMarkerRole
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attached_unit_reconciliation import (
    validate_attached_rules_unit_identity_after_destruction,
)
from warhammer40k_core.engine.battlefield_state import ModelPlacement
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.mission_decisions import (
    request_tactical_secondary_discard,
    request_tactical_secondary_score,
)
from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_destruction_evidence import (
    PrimaryUnattributedDestructionCause,
)
from warhammer40k_core.engine.primary_historical_events import (
    record_new_primary_battlefield_departure_events,
    record_new_primary_unit_destruction_events,
)
from warhammer40k_core.engine.reserve_arrival_requirements import reposition_destruction_policy
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
)
from warhammer40k_core.engine.secondary_mission_choices import (
    SELECT_BEACON_UNIT_DECISION_TYPE,
    SELECT_BURDEN_OF_TRUST_GUARD_DECISION_TYPE,
    SELECT_TEMPTING_TARGET_OBJECTIVE_DECISION_TYPE,
    next_secondary_mission_choice_request,
)
from warhammer40k_core.engine.secondary_mission_selection import SecondaryMissionSelection
from warhammer40k_core.engine.secondary_scoring_boundary import (
    score_turn_end_mission_scoring_boundary,
)
from warhammer40k_core.engine.secondary_scoring_context import secondary_mission_selection_for_card
from warhammer40k_core.engine.secondary_scoring_inventory import (
    SECONDARY_CARD_MODE_CERTIFICATION_COUNT,
    SECONDARY_LIFECYCLE_CERTIFICATION_COUNT,
    SECONDARY_MISSION_COUNT,
    secondary_mission_inventory_rows,
)
from warhammer40k_core.engine.secondary_when_drawn import (
    apply_tactical_secondary_when_drawn,
    next_tactical_secondary_when_drawn_request,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose


def _turn_cap_state() -> tuple[GameState, DecisionController]:
    state = _tactical_fight_state()
    state.secondary_mission_card_states = [
        card for card in state.secondary_mission_card_states if card.player_id != "player-a"
    ]
    for secondary_mission_id in TURN_CAP_TACTICAL_IDS:
        card = SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            battle_round=state.battle_round,
            source_result_id=f"phase17n-turn-cap-{secondary_mission_id}",
        )
        state.record_secondary_mission_card_state(
            card.with_selection(resolved_secondary_mission_selection_for_card(state, card))
        )
    decisions = DecisionController()
    seed_sequential_tactical_turn_cap_conditions(state, decisions=decisions)
    from tests.mission_action_history_helpers import prepare_mission_action_turn_end_for_fixture

    prepare_mission_action_turn_end_for_fixture(state=state, decisions=decisions)
    return state, _decisions_for_seeded_secondary_state(state, decisions=decisions)


def _decisions_for_seeded_secondary_state(
    state: GameState, *, decisions: DecisionController
) -> DecisionController:
    current_turn_has_snapshot = any(
        snapshot.active_player_id == state.active_player_id
        and snapshot.battle_round == state.battle_round
        for snapshot in state.primary_rules_unit_turn_start_snapshots
    )
    if current_turn_has_snapshot:
        record_existing_primary_turn_start_evidence_events_for_fixture(
            state,
            decisions=decisions,
        )
    else:
        record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    record_new_primary_battlefield_departure_events(
        state=state,
        event_log=decisions.event_log,
        departure_ids_before=(),
    )
    record_new_primary_unit_destruction_events(
        state=state,
        event_log=decisions.event_log,
        destruction_ids_before=(),
    )
    return decisions


def _tactical_fight_state() -> GameState:
    state = phase17n_state_with_setup(
        setup=_setup_for_layout(),
        active_player_id="player-a",
        phase=BattlePhase.FIGHT,
        battle_round=2,
        player_a_secondary=SecondaryMissionMode.TACTICAL,
        player_a_units=certification_unit_selections(player_id="player-a"),
        player_b_units=certification_unit_selections(player_id="player-b"),
    )
    _seed_completed_fight_phase(state)
    return state


def _command_tactical_state(*, battle_round: int) -> GameState:
    return phase17n_state_with_setup(
        setup=_setup_for_layout(),
        active_player_id="player-a",
        phase=BattlePhase.COMMAND,
        battle_round=battle_round,
        player_a_secondary=SecondaryMissionMode.TACTICAL,
        player_a_units=certification_unit_selections(player_id="player-a"),
        player_b_units=certification_unit_selections(player_id="player-b"),
    )


def _seed_single_tactical_card(state: GameState, secondary_mission_id: str) -> None:
    state.secondary_mission_card_states = [
        card for card in state.secondary_mission_card_states if card.player_id != "player-a"
    ]
    card = SecondaryMissionCardState.active_tactical(
        player_id="player-a",
        secondary_mission_id=secondary_mission_id,
        battle_round=state.battle_round,
        source_result_id=f"phase17n-review-{secondary_mission_id}",
    )
    state.record_secondary_mission_card_state(
        card.with_selection(resolved_secondary_mission_selection_for_card(state, card))
    )


def _record_unresolved_tactical(state: GameState, secondary_mission_id: str) -> None:
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            battle_round=state.battle_round,
            source_result_id=f"phase17n-when-drawn-{secondary_mission_id}",
        )
    )


def _attached_burden_state() -> GameState:
    setup = _setup_for_layout()
    catalog = phase11c_config().army_catalog
    config = replace(
        phase11c_config(),
        game_id="phase17n-burden-split",
        mission_setup=setup,
        army_muster_requests=(
            replace(
                army_muster_request(
                    catalog=catalog,
                    player_id="player-a",
                    army_id="army-alpha",
                    unit_selections=(
                        default_unit_selection("bodyguard-unit"),
                        unit_selection(
                            unit_selection_id="leader-unit",
                            datasheet_id="core-character-leader",
                            model_profile_id="core-character-leader",
                            model_count=1,
                        ),
                    ),
                    attachment_declarations=(
                        AttachmentDeclaration(
                            source_unit_selection_id="leader-unit",
                            bodyguard_unit_selection_id="bodyguard-unit",
                        ),
                    ),
                ),
                force_disposition_id=_LAYOUT_ROW.attacker_force_disposition_id,
            ),
            replace(
                army_muster_request(
                    catalog=catalog,
                    player_id="player-b",
                    army_id="army-beta",
                    unit_selections=(default_unit_selection("intercessor-unit-3"),),
                ),
                force_disposition_id=_LAYOUT_ROW.defender_force_disposition_id,
            ),
        ),
    )
    state = GameState.from_config(config)
    for army in mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17n-burden-split-battlefield",
        armies=tuple(state.army_definitions),
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=setup.terrain_features,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(player_id="player-a", mode=SecondaryMissionMode.TACTICAL)
    )
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(
            player_id="player-b",
            mode=SecondaryMissionMode.FIXED,
            fixed_mission_ids=("assassination", "bring-it-down"),
        )
    )
    complete_setup_through_gate(state=state, decisions=DecisionController(), config=config)
    assert state.battlefield_state is not None
    state.mission_setup = setup
    state.battlefield_state = replace(
        state.battlefield_state,
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=setup.terrain_features,
    )
    state.stage = GameLifecycleStage.BATTLE
    state.battle_round = 2
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    _seed_completed_fight_phase(state)
    return state


def _place_unit(state: GameState, unit_instance_id: str, x_inches: float, y_inches: float) -> None:
    if state.battlefield_state is None:
        raise AssertionError("Review fixture placement requires battlefield state.")
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    placements: list[ModelPlacement] = []
    for index, placement in enumerate(unit_placement.model_placements):
        placements.append(
            placement.with_pose(
                Pose.at(
                    x_inches + (index * 0.45),
                    y_inches,
                    placement.pose.position.z,
                    facing_degrees=placement.pose.facing.degrees,
                )
            )
        )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        unit_placement.with_model_placements(tuple(placements))
    )


def _home_objective(state: GameState, *, player_id: str) -> ObjectiveMarkerDefinition:
    if state.mission_setup is None:
        raise AssertionError("Review fixture requires MissionSetup.")
    role = (
        ObjectiveMarkerRole.ATTACKER_HOME
        if player_id == state.mission_setup.attacker_player_id
        else ObjectiveMarkerRole.DEFENDER_HOME
    )
    for marker in state.mission_setup.objective_markers:
        if marker.objective_role is role:
            return marker
    raise AssertionError("Review fixture is missing a home objective.")


def _zero_and_remove_unit(state: GameState, unit_instance_id: str) -> None:
    armies: list[ArmyDefinition] = []
    removed_ids: list[str] = []
    for army in state.army_definitions:
        units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                removed_ids.extend(model.model_instance_id for model in unit.own_models)
                unit = replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=0) for model in unit.own_models
                    ),
                )
            units.append(unit)
        armies.append(replace(army, units=tuple(units)))
    state.army_definitions = armies
    if state.battlefield_state is not None and removed_ids:
        state.replace_battlefield_state(
            state.battlefield_state.with_removed_models(tuple(removed_ids))
        )


def _restore_unit_wounds(state: GameState, unit_instance_id: str) -> None:
    armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                unit = replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=model.initial_wounds)
                        for model in unit.own_models
                    ),
                )
            units.append(unit)
        armies.append(replace(army, units=tuple(units)))
    state.army_definitions = armies


def _first_intercessor(state: GameState, *, player_id: str) -> UnitInstance:
    return _unit_for(
        state,
        player_id=player_id,
        datasheet_id="core-intercessor-like-infantry",
    )


def _unit_for(state: GameState, *, player_id: str, datasheet_id: str) -> UnitInstance:
    matches = tuple(
        unit
        for army in state.army_definitions
        if army.player_id == player_id
        for unit in army.units
        if unit.datasheet_id == datasheet_id
    )
    if not matches:
        raise AssertionError(f"Review fixture is missing {datasheet_id} for {player_id}.")
    return matches[0]


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise AssertionError(f"Review fixture is missing unit {unit_instance_id}.")


__all__: list[str] = []
__all__ += ["ArmyDefinition", "AttachmentDeclaration", "BattlePhase", "DecisionController"]
__all__ += ["DecisionError", "DecisionResult", "FiniteOptionSubmission", "GameLifecycle"]
__all__ += ["GameLifecycleError", "GameLifecycleStage", "GameState", "LifecycleStatusKind"]
__all__ += ["LocalGameSession", "ModelPlacement", "ObjectiveControlTiming"]
__all__ += ["ObjectiveMarkerDefinition", "ObjectiveMarkerRole", "Pose"]
__all__ += ["PrimaryUnattributedDestructionCause", "ReserveKind", "ReserveState"]
__all__ += ["SECONDARY_CARD_MODE_CERTIFICATION_COUNT", "RulesUnitPresence"]
__all__ += ["SECONDARY_LIFECYCLE_CERTIFICATION_COUNT", "SECONDARY_MISSION_COUNT"]
__all__ += ["SELECT_BEACON_UNIT_DECISION_TYPE", "SELECT_BURDEN_OF_TRUST_GUARD_DECISION_TYPE"]
__all__ += ["SELECT_TEMPTING_TARGET_OBJECTIVE_DECISION_TYPE", "STEP6G_MISSION_PARTITIONS"]
__all__ += ["SecondaryMissionCardMode", "SecondaryMissionCardState", "SecondaryMissionCardStatus"]
__all__ += ["SecondaryMissionChoice", "SecondaryMissionMode", "SecondaryMissionSelection"]
__all__ += ["TURN_CAP_TACTICAL_IDS", "_LAYOUT_ROW", "UnitInstance"]
__all__ += ["_LIFECYCLE_CERTIFICATION_ROWS", "_SCORING_PLAYER_IDS", "_attached_burden_state"]
__all__ += ["_command_tactical_state", "_configured_step6g_lifecycle"]
__all__ += ["_decisions_for_seeded_secondary_state", "_first_intercessor", "_home_objective"]
__all__ += ["_lifecycle_row", "_place_unit", "_record_unresolved_tactical"]
__all__ += ["_restore_unit_wounds", "_score_certified_row_from_state", "_secondary_transactions"]
__all__ += ["_seed_completed_fight_phase", "_seed_single_tactical_card", "_setup_for_layout"]
__all__ += ["_tactical_fight_state", "_turn_cap_state", "_unit_by_id", "_unit_for"]
__all__ += ["_zero_and_remove_unit", "apply_tactical_secondary_when_drawn", "army_muster_request"]
__all__ += ["attached_when_drawn_state", "certification_unit_selections"]
__all__ += ["complete_setup_through_gate", "create_deterministic_battlefield_scenario"]
__all__ += ["deepcopy", "default_unit_selection", "mustered_armies"]
__all__ += ["next_secondary_mission_choice_request", "next_tactical_secondary_when_drawn_request"]
__all__ += ["phase11c_config", "phase17n_state_with_setup", "pytest"]
__all__ += ["record_existing_primary_turn_start_evidence_events_for_fixture"]
__all__ += ["record_new_primary_battlefield_departure_events"]
__all__ += ["record_new_primary_unit_destruction_events"]
__all__ += ["record_primary_turn_start_evidence_for_fixture"]
__all__ += ["record_secondary_destruction_for_fixture", "record_unresolved_when_drawn_card"]
__all__ += ["replace", "reposition_destruction_policy", "request_tactical_secondary_discard"]
__all__ += ["request_tactical_secondary_score", "resolved_secondary_mission_selection_for_card"]
__all__ += ["score_turn_end_mission_scoring_boundary", "secondary_mission_inventory_rows"]
__all__ += ["secondary_mission_selection_for_card"]
__all__ += ["seed_sequential_tactical_turn_cap_conditions", "step6g_matrix_case_keys"]
__all__ += ["unit_selection", "validate_attached_rules_unit_identity_after_destruction"]
