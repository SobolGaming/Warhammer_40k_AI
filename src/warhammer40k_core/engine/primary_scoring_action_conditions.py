from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_scoring_conditions import primary_score_count_evidence

if TYPE_CHECKING:
    from warhammer40k_core.engine.actions import MissionActionState

COMMIT_SABOTAGE_ACTION_ID = "commit-sabotage"
EXTRACT_INTELLIGENCE_ACTION_ID = "extract-intelligence"
SECURE_ASSET_ACTION_ID = "secure-asset"
SENSOR_SWEEP_EXTRACT_ACTION_ID = "sensor-sweep-extract-relic"
VANGUARD_OPERATION_ACTION_ID = "vanguard-operation"

PRIMARY_SCORING_ACTION_CONDITIONS = frozenset(
    {
        "each_friendly_unit_committed_sabotage_this_turn",
        "each_friendly_unit_extracted_intelligence_this_turn",
        "each_sabotage_unit_within_objective_range_in_opponent_territory_this_turn",
        "friendly_unit_performed_sensor_sweep_this_turn",
        "friendly_unit_performed_vanguard_operation_this_turn",
        "friendly_unit_secured_asset_this_turn",
    }
)
_EACH_UNIT_ACTION_CONDITIONS = frozenset(
    {
        "each_friendly_unit_committed_sabotage_this_turn",
        "each_friendly_unit_extracted_intelligence_this_turn",
        "each_sabotage_unit_within_objective_range_in_opponent_territory_this_turn",
    }
)
_BATTLE_ROUND_TWO_ACTION_CONDITIONS = frozenset(
    {
        "each_friendly_unit_extracted_intelligence_this_turn",
    }
)
_CONDITION_MISSION_ACTION_IDS = {
    "each_friendly_unit_committed_sabotage_this_turn": COMMIT_SABOTAGE_ACTION_ID,
    "each_friendly_unit_extracted_intelligence_this_turn": EXTRACT_INTELLIGENCE_ACTION_ID,
    "each_sabotage_unit_within_objective_range_in_opponent_territory_this_turn": (
        COMMIT_SABOTAGE_ACTION_ID
    ),
    "friendly_unit_performed_sensor_sweep_this_turn": SENSOR_SWEEP_EXTRACT_ACTION_ID,
    "friendly_unit_performed_vanguard_operation_this_turn": VANGUARD_OPERATION_ACTION_ID,
    "friendly_unit_secured_asset_this_turn": SECURE_ASSET_ACTION_ID,
}


def evaluate_action_scoring_condition(
    *,
    condition_id: str,
    actions: tuple[MissionActionState, ...],
    mission_setup: MissionSetup,
    player_id: str,
    battle_round: int,
    opponent_territory_objective_ids: tuple[str, ...] | None = None,
    opponent_player_id: str | None = None,
) -> dict[str, JsonValue]:
    if condition_id not in PRIMARY_SCORING_ACTION_CONDITIONS:
        raise GameLifecycleError(f"Unsupported primary scoring condition: {condition_id}.")
    if type(actions) is not tuple:
        raise GameLifecycleError("Primary action scoring requires MissionActionState tuples.")
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Primary action scoring requires MissionSetup.")
    if type(battle_round) is not int or battle_round < 1:
        raise GameLifecycleError("Primary action scoring battle_round must be a positive int.")
    mission_id = mission_setup.primary_mission_id_for_player(player_id)
    mission_action_id = _CONDITION_MISSION_ACTION_IDS[condition_id]
    matching = _completed_actions_this_turn(
        actions,
        player_id=player_id,
        mission_id=mission_id,
        mission_action_id=mission_action_id,
        battle_round=battle_round,
        mission_setup=mission_setup,
    )
    if condition_id in _BATTLE_ROUND_TWO_ACTION_CONDITIONS and battle_round < 2:
        matching = ()
    if condition_id == "each_sabotage_unit_within_objective_range_in_opponent_territory_this_turn":
        if opponent_territory_objective_ids is None or opponent_player_id is None:
            raise GameLifecycleError(
                "Primary scoring condition "
                "each_sabotage_unit_within_objective_range_in_opponent_territory_this_turn "
                "requires spatial evidence."
            )
        expected_ids = {marker.objective_marker_id for marker in mission_setup.objective_markers}
        if any(
            objective_id not in expected_ids for objective_id in opponent_territory_objective_ids
        ):
            raise GameLifecycleError(
                "Primary scoring sabotage territory objectives must exist in MissionSetup."
            )
        matching = tuple(
            action for action in matching if action.target_id in opponent_territory_objective_ids
        )
    unit_ids = tuple(sorted({action.unit_instance_id for action in matching}))
    action_ids = tuple(sorted(action.action_id for action in matching))
    target_ids = tuple(sorted({action.target_id for action in matching}))
    if condition_id in _EACH_UNIT_ACTION_CONDITIONS:
        score_count = len(unit_ids)
    else:
        score_count = int(bool(unit_ids))
    evidence = primary_score_count_evidence(score_count=score_count)
    evidence["mission_action_id"] = mission_action_id
    evidence["completed_action_ids"] = list(action_ids)
    evidence["completed_unit_instance_ids"] = list(unit_ids)
    evidence["completed_target_ids"] = list(target_ids)
    if condition_id == "each_sabotage_unit_within_objective_range_in_opponent_territory_this_turn":
        evidence["opponent_territory_objective_ids"] = list(opponent_territory_objective_ids or ())
        evidence["opponent_player_id"] = opponent_player_id
    return evidence


def _completed_actions_this_turn(
    actions: tuple[MissionActionState, ...],
    *,
    player_id: str,
    mission_id: str,
    mission_action_id: str,
    battle_round: int,
    mission_setup: MissionSetup,
) -> tuple[MissionActionState, ...]:
    from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus

    source_identity = _action_source_identity(mission_action_id)
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
        if action.mission_action_id != mission_action_id:
            continue
        if (action.scoring_source_id, action.mission_action_id) != source_identity:
            raise GameLifecycleError("Primary scoring completed action source identity drifted.")
        if action.completed_battle_round != battle_round:
            continue
        if (
            mission_action_id != VANGUARD_OPERATION_ACTION_ID
            and action.target_id not in expected_objective_ids
        ):
            raise GameLifecycleError(
                "Primary scoring completed action references an unknown target."
            )
        matching.append(action)
    return tuple(sorted(matching, key=lambda action: action.action_id))


def _action_source_identity(mission_action_id: str) -> tuple[str, str]:
    from warhammer40k_core.engine.mission_action_policies import mission_action_policy_for_id

    policy = mission_action_policy_for_id(mission_action_id)
    return (policy.scoring_source_id, policy.mission_action_id)


__all__ = (
    "COMMIT_SABOTAGE_ACTION_ID",
    "EXTRACT_INTELLIGENCE_ACTION_ID",
    "PRIMARY_SCORING_ACTION_CONDITIONS",
    "SECURE_ASSET_ACTION_ID",
    "SENSOR_SWEEP_EXTRACT_ACTION_ID",
    "VANGUARD_OPERATION_ACTION_ID",
    "evaluate_action_scoring_condition",
)
