from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_state import (
    MarkerAnchorKind,
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    PrimaryMissionProgressState,
)
from warhammer40k_core.engine.primary_scoring_conditions import primary_score_count_evidence
from warhammer40k_core.engine.primary_scoring_position_witness import (
    PrimaryScoringRulesUnitPositionWitness,
    validate_primary_scoring_position_witnesses,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.actions import MissionActionState

SURVEIL_ENEMY_UNIT_ACTION_ID = "surveil-enemy-unit"
ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION = (
    "one_or_more_enemy_units_surveilled_this_turn_unless_all_within_range_of_"
    "objectives_with_operation_markers"
)
PRIMARY_SCORING_SURVEIL_CONDITIONS = frozenset({ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION})
_OPERATION_MARKER_KIND = "operation"


def surveil_enemy_unit_source_identity() -> tuple[str, str]:
    from warhammer40k_core.engine.mission_action_policies import mission_action_policy_for_id

    policy = mission_action_policy_for_id(SURVEIL_ENEMY_UNIT_ACTION_ID)
    return (policy.scoring_source_id, policy.mission_action_id)


def evaluate_surveil_scoring_condition(
    *,
    condition_id: str,
    actions: tuple[MissionActionState, ...],
    progress: PrimaryMissionProgressState,
    mission_setup: MissionSetup,
    player_id: str,
    battle_round: int,
    position_witnesses: tuple[PrimaryScoringRulesUnitPositionWitness, ...] | None = None,
) -> dict[str, JsonValue]:
    if condition_id not in PRIMARY_SCORING_SURVEIL_CONDITIONS:
        raise GameLifecycleError(f"Unsupported primary scoring condition: {condition_id}.")
    if type(actions) is not tuple:
        raise GameLifecycleError("Primary surveil scoring requires MissionActionState tuples.")
    if type(progress) is not PrimaryMissionProgressState:
        raise GameLifecycleError("Primary surveil scoring requires mission progress state.")
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Primary surveil scoring requires MissionSetup.")
    if type(battle_round) is not int or battle_round < 1:
        raise GameLifecycleError("Primary surveil scoring battle_round must be a positive int.")
    mission_id = mission_setup.primary_mission_id_for_player(player_id)
    matching = _completed_surveil_actions_this_turn(
        actions,
        player_id=player_id,
        mission_id=mission_id,
        battle_round=battle_round,
        mission_setup=mission_setup,
    )
    surveilled_unit_ids = tuple(sorted({action.target_id for action in matching}))
    completed_action_ids = tuple(sorted(action.action_id for action in matching))
    if not surveilled_unit_ids:
        return _surveil_evidence(
            score_count=0,
            completed_action_ids=(),
            surveilled_unit_instance_ids=(),
            excepted_unit_instance_ids=(),
            operation_objective_ids=(),
            operation_marker_ids=(),
        )
    if position_witnesses is None:
        raise GameLifecycleError(
            f"Primary scoring condition {condition_id} requires position witnesses."
        )
    validated_witnesses = validate_primary_scoring_position_witnesses(position_witnesses)
    operation_markers = _active_objective_operation_markers(
        progress,
        mission_setup=mission_setup,
    )
    operation_objective_ids = tuple(
        sorted(
            {
                marker.objective_marker_id
                for marker in operation_markers
                if marker.objective_marker_id is not None
            }
        )
    )
    operation_marker_ids = tuple(sorted(marker.marker_id for marker in operation_markers))
    marked_objectives = frozenset(operation_objective_ids)
    excepted_unit_ids = tuple(
        unit_id
        for unit_id in surveilled_unit_ids
        if _surveilled_unit_is_within_marked_objective_range(
            unit_id,
            witnesses=validated_witnesses,
            marked_objective_ids=marked_objectives,
            mission_setup=mission_setup,
        )
    )
    score_count = int(excepted_unit_ids != surveilled_unit_ids)
    return _surveil_evidence(
        score_count=score_count,
        completed_action_ids=completed_action_ids,
        surveilled_unit_instance_ids=surveilled_unit_ids,
        excepted_unit_instance_ids=excepted_unit_ids,
        operation_objective_ids=operation_objective_ids,
        operation_marker_ids=operation_marker_ids,
    )


def _completed_surveil_actions_this_turn(
    actions: tuple[MissionActionState, ...],
    *,
    player_id: str,
    mission_id: str,
    battle_round: int,
    mission_setup: MissionSetup,
) -> tuple[MissionActionState, ...]:
    from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus

    source_identity = surveil_enemy_unit_source_identity()
    expected_objective_ids = {
        marker.objective_marker_id for marker in mission_setup.objective_markers
    }
    matching: list[MissionActionState] = []
    seen_ids: set[str] = set()
    for action in actions:
        if type(action) is not MissionActionState:
            raise GameLifecycleError("Primary scoring actions must be typed MissionActionState.")
        if action.action_id in seen_ids:
            raise GameLifecycleError("Primary scoring actions must not duplicate action_id.")
        seen_ids.add(action.action_id)
        if action.status is not MissionActionStatus.COMPLETED:
            continue
        if action.player_id != player_id or action.mission_id != mission_id:
            continue
        if action.mission_action_id != SURVEIL_ENEMY_UNIT_ACTION_ID:
            continue
        if (action.scoring_source_id, action.mission_action_id) != source_identity:
            raise GameLifecycleError("Primary scoring completed action source identity drifted.")
        if action.completed_battle_round != battle_round:
            continue
        if action.target_id in expected_objective_ids:
            raise GameLifecycleError(
                "Primary scoring Surveil Action references an objective target."
            )
        matching.append(action)
    return tuple(sorted(matching, key=lambda action: action.action_id))


def _active_objective_operation_markers(
    progress: PrimaryMissionProgressState,
    *,
    mission_setup: MissionSetup,
) -> tuple[PrimaryMissionMarkerState, ...]:
    expected_objective_ids = {
        marker.objective_marker_id for marker in mission_setup.objective_markers
    }
    matching: list[PrimaryMissionMarkerState] = []
    for marker in progress.markers:
        if type(marker) is not PrimaryMissionMarkerState:
            raise GameLifecycleError(
                "Primary surveil scoring markers must be typed PrimaryMissionMarkerState."
            )
        if marker.status is not PrimaryMissionMarkerStatus.ACTIVE:
            continue
        if marker.marker_kind != _OPERATION_MARKER_KIND:
            continue
        if marker.anchor_kind is not MarkerAnchorKind.OBJECTIVE:
            continue
        objective_id = marker.objective_marker_id
        if objective_id is None:
            raise GameLifecycleError(
                "Primary scoring operation marker is missing its objective anchor."
            )
        if objective_id not in expected_objective_ids:
            raise GameLifecycleError(
                "Primary scoring operation marker references an unknown objective."
            )
        matching.append(marker)
    return tuple(sorted(matching, key=lambda marker: marker.marker_id))


def _surveilled_unit_is_within_marked_objective_range(
    unit_instance_id: str,
    *,
    witnesses: tuple[PrimaryScoringRulesUnitPositionWitness, ...],
    marked_objective_ids: frozenset[str],
    mission_setup: MissionSetup,
) -> bool:
    matching = tuple(
        witness
        for witness in witnesses
        if _witness_covers_unit(witness, unit_instance_id=unit_instance_id)
    )
    if len(matching) > 1:
        raise GameLifecycleError(
            "Primary scoring Surveil target matched multiple position witnesses."
        )
    if not matching:
        return False
    expected_objective_ids = {
        marker.objective_marker_id for marker in mission_setup.objective_markers
    }
    witness_objective_ids = matching[0].rules_unit_membership.objective_marker_ids
    if any(objective_id not in expected_objective_ids for objective_id in witness_objective_ids):
        raise GameLifecycleError(
            "Primary scoring Surveil position witness references an unknown objective."
        )
    return bool(marked_objective_ids.intersection(witness_objective_ids))


def _witness_covers_unit(
    witness: PrimaryScoringRulesUnitPositionWitness,
    *,
    unit_instance_id: str,
) -> bool:
    membership = witness.rules_unit_membership
    return (
        membership.rules_unit_instance_id == unit_instance_id
        or unit_instance_id in membership.component_unit_instance_ids
    )


def _surveil_evidence(
    *,
    score_count: int,
    completed_action_ids: tuple[str, ...],
    surveilled_unit_instance_ids: tuple[str, ...],
    excepted_unit_instance_ids: tuple[str, ...],
    operation_objective_ids: tuple[str, ...],
    operation_marker_ids: tuple[str, ...],
) -> dict[str, JsonValue]:
    evidence = primary_score_count_evidence(score_count=score_count)
    evidence["mission_action_id"] = SURVEIL_ENEMY_UNIT_ACTION_ID
    evidence["completed_action_ids"] = list(completed_action_ids)
    evidence["surveilled_unit_instance_ids"] = list(surveilled_unit_instance_ids)
    evidence["excepted_unit_instance_ids"] = list(excepted_unit_instance_ids)
    evidence["operation_objective_ids"] = list(operation_objective_ids)
    evidence["operation_marker_ids"] = list(operation_marker_ids)
    return evidence


__all__ = (
    "ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION",
    "PRIMARY_SCORING_SURVEIL_CONDITIONS",
    "SURVEIL_ENEMY_UNIT_ACTION_ID",
    "evaluate_surveil_scoring_condition",
    "surveil_enemy_unit_source_identity",
)
