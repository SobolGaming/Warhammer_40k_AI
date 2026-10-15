from __future__ import annotations

from dataclasses import replace

import pytest

from tests.phase17n_primary_mission_helpers import (
    phase17n_consecrate_pending_fixture,
    phase17n_event_setup,
    phase17n_started_primary_action_fixture,
)
from warhammer40k_core.core.battlefield_regions import BattlefieldRegionKind
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import (
    mission_scoring_policies_from_setup,
    primary_scoring_rules_from_definition,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_mission_action_resolution import (
    resolve_primary_mission_actions_at_turn_end,
)
from warhammer40k_core.engine.primary_mission_choice_payloads import PrimaryMissionChoiceData
from warhammer40k_core.engine.primary_mission_choices import PRIMARY_OPERATION_MARKER_KIND
from warhammer40k_core.engine.primary_mission_state import (
    MarkerAnchorKind,
    PrimaryConsecrationDesignationState,
    PrimaryMissionMarkerState,
    PrimaryMissionProgressState,
    primary_consecration_designation_id,
    primary_mission_marker_id,
)
from warhammer40k_core.engine.primary_scoring_boundary import (
    score_primary_objective_control_boundary,
)
from warhammer40k_core.engine.primary_scoring_condition_evaluator import (
    SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS,
    PrimaryScoringConditionContext,
    evaluate_primary_scoring_condition,
)
from warhammer40k_core.engine.primary_scoring_conditions import home_objective_ids
from warhammer40k_core.engine.primary_scoring_marker_conditions import (
    PRIMARY_SCORING_MARKER_CONDITIONS,
    active_decoy_objective_ids,
    consecrated_marker_source_identity,
    decoy_marker_source_identity,
    evaluate_marker_scoring_condition,
    triangulated_marker_source_identity,
)
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    PRIMARY_SCORING_DECOY_OPPONENT_TERRITORY_OBJECTIVE_CONDITION,
    PRIMARY_SCORING_SPATIAL_CONDITIONS,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import VictoryPointSourceKind
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


def _consecrate_setup() -> MissionSetup:
    return phase17n_event_setup(
        layout_id="purge-the-foe-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="reconnaissance",
    )


def _smoke_setup() -> MissionSetup:
    return phase17n_event_setup(
        layout_id="disruption-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="reconnaissance",
    )


def _non_home_objective_ids(setup: MissionSetup) -> tuple[str, ...]:
    home_roles = {ObjectiveMarkerRole.ATTACKER_HOME, ObjectiveMarkerRole.DEFENDER_HOME}
    return tuple(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_role not in home_roles
    )


def _opponent_territory_non_home_objective_ids(
    setup: MissionSetup,
    *,
    player_id: str,
) -> tuple[str, ...]:
    opponent_id = next(
        candidate_id
        for candidate_id in (setup.attacker_player_id, setup.defender_player_id)
        if candidate_id != player_id
    )
    opponent_role = "attacker" if opponent_id == setup.attacker_player_id else "defender"
    territory = next(
        region
        for region in setup.battlefield_regions
        if region.region_kind is BattlefieldRegionKind.TERRITORY
        and region.owner_role == opponent_role
    )
    excluded_home_ids = set(home_objective_ids(setup, player_id=player_id)) | set(
        home_objective_ids(setup, player_id=opponent_id)
    )
    return tuple(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id not in excluded_home_ids
        and territory.contains_point(marker.x_inches, marker.y_inches)
    )


def _resolved_primary_action(
    *,
    layout_id: str,
    attacker_force_disposition_id: str,
    defender_force_disposition_id: str,
    player_id: str,
    mission_action_id: str,
    target_objective_id: str | None = None,
) -> tuple[GameState, ObjectiveControlRecord]:
    state, decisions, action, target_id = phase17n_started_primary_action_fixture(
        layout_id=layout_id,
        attacker_force_disposition_id=attacker_force_disposition_id,
        defender_force_disposition_id=defender_force_disposition_id,
        player_id=player_id,
        mission_action_id=mission_action_id,
        current_phase=BattlePhase.FIGHT,
        target_objective_id=target_objective_id,
    )
    _bind_force_dispositions(state)
    if target_id != action.target_id:
        raise AssertionError("Step 5B Action turn-end target drifted.")
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    decisions.event_log.append(
        "end_boundary_objective_control_determined",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.FIGHT.value,
            "record_ids": [record.record_id],
            "source_rule_id": (
                "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first"
            ),
        },
    )
    resolved = resolve_primary_mission_actions_at_turn_end(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
        turn_end_record=record,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert len(resolved) == 1
    return state, record


def _bind_force_dispositions(state: GameState) -> None:
    setup = state.mission_setup
    if setup is None:
        raise AssertionError("Step 5B fixture requires MissionSetup.")
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=setup.primary_mission_assignment_for_player(
                army.player_id
            ).force_disposition_id,
        )
        for army in state.army_definitions
    ]


def _objective_context(
    *,
    setup: MissionSetup,
    battle_round: int,
    end_of_battle: bool = False,
) -> PrimaryScoringConditionContext:
    results = tuple(
        ObjectiveControlResult.from_contributors(
            objective_id=marker.objective_marker_id,
            contributors=(),
        )
        for marker in setup.objective_markers
    )
    record = ObjectiveControlRecord(
        record_id=f"step5b-objective-record-round-{battle_round}",
        game_id="step5b-objective-game",
        battle_round=battle_round,
        active_player_id="player-a",
        timing=ObjectiveControlTiming.TURN_END,
        phase=BattlePhase.FIGHT.value,
        battlefield_id="step5b-objective-battlefield",
        results=results,
    )
    return PrimaryScoringConditionContext(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
        end_of_battle=end_of_battle,
    )


def _primary_awards_by_condition(state: GameState, *, player_id: str) -> dict[str, int]:
    awards: dict[str, int] = {}
    for ledger in state.victory_point_ledgers:
        for transaction in ledger.transactions:
            if (
                transaction.player_id != player_id
                or transaction.source_kind is not VictoryPointSourceKind.PRIMARY
                or type(transaction.metadata) is not dict
            ):
                continue
            condition = transaction.metadata.get("scoring_rule_condition")
            if type(condition) is not str:
                continue
            awards[condition] = transaction.amount
    return awards


def _consecrated_progress(
    setup: MissionSetup,
    objective_ids: tuple[str, ...],
) -> PrimaryMissionProgressState:
    if setup.primary_mission_id_for_player("player-a") != "primary-consecrate":
        raise AssertionError("Step 5B consecration fixture mission assignment drifted.")
    source_identity = consecrated_marker_source_identity()
    markers: list[PrimaryMissionMarkerState] = []
    designations: list[PrimaryConsecrationDesignationState] = []
    for index, objective_id in enumerate(objective_ids, start=1):
        designation = _consecration_designation(
            game_id="phase11c-game",
            owner_player_id="player-a",
            mission_id="primary-consecrate",
            index=index,
        )
        marker = _marker(
            game_id="phase11c-game",
            owner_player_id="player-a",
            mission_id="primary-consecrate",
            source_identity=source_identity,
            objective_id=objective_id,
            index=index,
            source_result_id=f"step5b-consecrate-result-{index:02d}",
            source_destruction_id=designation.source_destruction_id,
            source_designation_id=designation.designation_id,
        )
        markers.append(marker)
        designations.append(
            designation.consumed(
                marker_id=marker.marker_id,
                battle_round=1,
                phase=BattlePhase.FIGHT.value,
                active_player_id="player-a",
                source_id=source_identity[0],
                event_id=f"step5b-consecrate-consume-{index:02d}",
                result_id=f"step5b-consecrate-result-{index:02d}",
            )
        )
    return PrimaryMissionProgressState(
        markers=tuple(markers),
        condemned_selections=(),
        consecration_designations=tuple(designations),
    )


def _action_marker_progress(
    setup: MissionSetup,
    *,
    owner_player_id: str,
    mission_id: str,
    source_identity: tuple[str, str],
    objective_ids: tuple[str, ...],
) -> PrimaryMissionProgressState:
    if setup.primary_mission_id_for_player(owner_player_id) != mission_id:
        raise AssertionError("Step 5B marker fixture mission assignment drifted.")
    progress = PrimaryMissionProgressState.empty()
    for index, objective_id in enumerate(objective_ids, start=1):
        progress = progress.add_marker(
            _action_marker(
                owner_player_id=owner_player_id,
                mission_id=mission_id,
                source_identity=source_identity,
                objective_id=objective_id,
                index=index,
            )
        )
    return progress


def _action_marker(
    *,
    owner_player_id: str,
    mission_id: str,
    source_identity: tuple[str, str],
    objective_id: str,
    index: int,
) -> PrimaryMissionMarkerState:
    return _marker(
        game_id="phase11c-game",
        owner_player_id=owner_player_id,
        mission_id=mission_id,
        source_identity=source_identity,
        objective_id=objective_id,
        index=index,
        source_result_id=None,
        source_destruction_id=None,
        source_designation_id=None,
        source_action_id=f"step5b-action-{index:02d}",
    )


def _marker(
    *,
    game_id: str,
    owner_player_id: str,
    mission_id: str,
    source_identity: tuple[str, str],
    objective_id: str,
    index: int,
    source_result_id: str | None,
    source_destruction_id: str | None,
    source_designation_id: str | None,
    source_action_id: str | None = None,
) -> PrimaryMissionMarkerState:
    source_event_id = f"step5b-marker-event-{index:02d}"
    marker_id = primary_mission_marker_id(
        game_id=game_id,
        owner_player_id=owner_player_id,
        mission_id=mission_id,
        source_rule_id=source_identity[0],
        source_descriptor_id=source_identity[1],
        marker_kind=PRIMARY_OPERATION_MARKER_KIND,
        anchor_kind=MarkerAnchorKind.OBJECTIVE,
        objective_marker_id=objective_id,
        terrain_feature_id=None,
        created_battle_round=1,
        created_phase=BattlePhase.FIGHT.value,
        created_active_player_id=owner_player_id,
        source_event_id=source_event_id,
        source_result_id=source_result_id,
        source_action_id=source_action_id,
        source_destruction_id=source_destruction_id,
        source_designation_id=source_designation_id,
    )
    return PrimaryMissionMarkerState(
        marker_id=marker_id,
        game_id=game_id,
        owner_player_id=owner_player_id,
        mission_id=mission_id,
        source_rule_id=source_identity[0],
        source_descriptor_id=source_identity[1],
        marker_kind=PRIMARY_OPERATION_MARKER_KIND,
        anchor_kind=MarkerAnchorKind.OBJECTIVE,
        objective_marker_id=objective_id,
        terrain_feature_id=None,
        created_battle_round=1,
        created_phase=BattlePhase.FIGHT.value,
        created_active_player_id=owner_player_id,
        source_event_id=source_event_id,
        source_result_id=source_result_id,
        source_action_id=source_action_id,
        source_destruction_id=source_destruction_id,
        source_designation_id=source_designation_id,
    )


def _consecration_designation(
    *,
    game_id: str,
    owner_player_id: str,
    mission_id: str,
    index: int,
) -> PrimaryConsecrationDesignationState:
    source_rule_id = "step5b-consecration-source"
    source_descriptor_id = "consecrate-destroyer-becomes-consecration-unit"
    source_destruction_id = f"step5b-destruction-{index:02d}"
    source_event_id = f"step5b-designation-event-{index:02d}"
    rules_unit_instance_id = "army-alpha:intercessor-unit-1"
    component_unit_instance_ids = (rules_unit_instance_id,)
    designation_id = primary_consecration_designation_id(
        game_id=game_id,
        owner_player_id=owner_player_id,
        mission_id=mission_id,
        source_rule_id=source_rule_id,
        source_descriptor_id=source_descriptor_id,
        rules_unit_instance_id=rules_unit_instance_id,
        component_unit_instance_ids=component_unit_instance_ids,
        source_destruction_id=source_destruction_id,
        created_battle_round=1,
        created_phase=BattlePhase.COMMAND.value,
        created_active_player_id=owner_player_id,
        source_event_id=source_event_id,
    )
    return PrimaryConsecrationDesignationState(
        designation_id=designation_id,
        game_id=game_id,
        owner_player_id=owner_player_id,
        mission_id=mission_id,
        source_rule_id=source_rule_id,
        source_descriptor_id=source_descriptor_id,
        rules_unit_instance_id=rules_unit_instance_id,
        component_unit_instance_ids=component_unit_instance_ids,
        source_destruction_id=source_destruction_id,
        created_battle_round=1,
        created_phase=BattlePhase.COMMAND.value,
        created_active_player_id=owner_player_id,
        source_event_id=source_event_id,
    )


__all__: list[str] = []
__all__ += ["BattlePhase", "BattlefieldRegionKind", "DecisionResult", "GameLifecycle"]
__all__ += ["GameLifecycleError", "GameState", "MarkerAnchorKind", "MissionSetup"]
__all__ += ["ObjectiveControlRecord", "ObjectiveControlResult", "ObjectiveControlTiming"]
__all__ += ["PRIMARY_OPERATION_MARKER_KIND", "ObjectiveMarkerRole"]
__all__ += ["PRIMARY_SCORING_DECOY_OPPONENT_TERRITORY_OBJECTIVE_CONDITION"]
__all__ += ["PRIMARY_SCORING_MARKER_CONDITIONS", "PRIMARY_SCORING_SPATIAL_CONDITIONS"]
__all__ += ["PrimaryConsecrationDesignationState", "PrimaryMissionChoiceData"]
__all__ += ["PrimaryMissionMarkerState", "PrimaryMissionProgressState"]
__all__ += ["PrimaryScoringConditionContext", "RuntimeModifierRegistry"]
__all__ += ["SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS", "VictoryPointSourceKind"]
__all__ += ["_action_marker", "_action_marker_progress", "_bind_force_dispositions"]
__all__ += ["_consecrate_setup", "_consecrated_progress", "_consecration_designation", "_marker"]
__all__ += ["_non_home_objective_ids", "_objective_context"]
__all__ += ["_opponent_territory_non_home_objective_ids", "_primary_awards_by_condition"]
__all__ += ["_resolved_primary_action", "_smoke_setup", "active_decoy_objective_ids"]
__all__ += ["consecrated_marker_source_identity", "decoy_marker_source_identity"]
__all__ += ["evaluate_marker_scoring_condition", "evaluate_primary_scoring_condition"]
__all__ += ["home_objective_ids", "mission_scoring_policies_from_setup"]
__all__ += ["phase17n_consecrate_pending_fixture", "phase17n_event_setup"]
__all__ += ["phase17n_started_primary_action_fixture", "primary_consecration_designation_id"]
__all__ += ["primary_mission_marker_id", "primary_scoring_rules_from_definition", "pytest"]
__all__ += ["replace", "resolve_primary_mission_actions_at_turn_end"]
__all__ += ["score_primary_objective_control_boundary", "triangulated_marker_source_identity"]
__all__ += ["warhammer_event_companion_2026_07_mission_pack"]
