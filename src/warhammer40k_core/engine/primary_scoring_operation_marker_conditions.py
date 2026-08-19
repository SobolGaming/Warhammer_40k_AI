from __future__ import annotations

import math

from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mission_terrain import mission_logical_terrain_areas
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_state import (
    MarkerAnchorKind,
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    PrimaryMissionProgressState,
)
from warhammer40k_core.engine.primary_scoring_action_conditions import (
    EXTRACT_INTELLIGENCE_ACTION_ID,
)
from warhammer40k_core.engine.primary_scoring_conditions import (
    home_objective_ids,
    primary_score_count_evidence,
)
from warhammer40k_core.engine.primary_scoring_position_witness import (
    PrimaryScoringRulesUnitPositionWitness,
)
from warhammer40k_core.geometry.measurement import OBJECTIVE_CONTROL_HORIZONTAL_INCHES

MAINTAIN_CONTROL_ACTION_ID = "maintain-control"
_OPERATION_MARKER_KIND = "operation"

ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN = (
    "only_one_opponent_operation_marker_remains_with_friendly_unit_and_no_enemy_in_terrain_area"
)
ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN_END_OF_BATTLE = (
    "only_one_opponent_operation_marker_remains_with_friendly_unit_and_no_enemy_in_terrain_area"
    "_end_of_battle"
)
ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN = (
    "only_one_friendly_operation_marker_remains_with_friendly_unit_and_no_enemy_in_terrain_area"
)
ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN_END_OF_BATTLE = (
    "only_one_friendly_operation_marker_remains_with_friendly_unit_and_no_enemy_in_terrain_area"
    "_end_of_battle"
)
THREE_OR_MORE_FRIENDLY_OPERATION_MARKERS_END_OF_BATTLE = (
    "three_or_more_friendly_operation_markers_on_battlefield_end_of_battle"
)
FRIENDLY_OPERATION_MARKER_WITHIN_OPPONENT_HOME_RANGE_END_OF_BATTLE = (
    "friendly_operation_marker_within_opponent_home_objective_range_end_of_battle"
)
EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE = (
    "each_friendly_operation_marker_within_range_of_controlled_central_objective"
)
NO_ENEMY_OPERATION_MARKERS_ON_BATTLEFIELD = "no_enemy_operation_markers_on_battlefield"

PRIMARY_SCORING_OPERATION_MARKER_CONDITIONS = frozenset(
    {
        ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN,
        ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN_END_OF_BATTLE,
        ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN,
        ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN_END_OF_BATTLE,
        THREE_OR_MORE_FRIENDLY_OPERATION_MARKERS_END_OF_BATTLE,
        FRIENDLY_OPERATION_MARKER_WITHIN_OPPONENT_HOME_RANGE_END_OF_BATTLE,
        EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE,
        NO_ENEMY_OPERATION_MARKERS_ON_BATTLEFIELD,
    }
)
PRIMARY_SCORING_OPERATION_MARKER_TERRAIN_CONDITIONS = frozenset(
    {
        ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN,
        ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN_END_OF_BATTLE,
        ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN,
        ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN_END_OF_BATTLE,
    }
)
_END_OF_BATTLE_OPERATION_MARKER_CONDITIONS = frozenset(
    {
        ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN_END_OF_BATTLE,
        ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN_END_OF_BATTLE,
        THREE_OR_MORE_FRIENDLY_OPERATION_MARKERS_END_OF_BATTLE,
        FRIENDLY_OPERATION_MARKER_WITHIN_OPPONENT_HOME_RANGE_END_OF_BATTLE,
    }
)
_EXTRACT_INTELLIGENCE_OPERATION_MARKER_CONDITIONS = frozenset(
    {
        THREE_OR_MORE_FRIENDLY_OPERATION_MARKERS_END_OF_BATTLE,
        FRIENDLY_OPERATION_MARKER_WITHIN_OPPONENT_HOME_RANGE_END_OF_BATTLE,
    }
)


def extract_intelligence_marker_source_identity() -> tuple[str, str]:
    from warhammer40k_core.engine.mission_action_policies import mission_action_policy_for_id

    policy = mission_action_policy_for_id(EXTRACT_INTELLIGENCE_ACTION_ID)
    return (policy.source_id, policy.mission_action_id)


def maintain_control_marker_source_identity() -> tuple[str, str]:
    from warhammer40k_core.engine.mission_action_policies import mission_action_policy_for_id

    policy = mission_action_policy_for_id(MAINTAIN_CONTROL_ACTION_ID)
    return (policy.source_id, policy.mission_action_id)


def locate_and_deny_marker_source_identity() -> tuple[str, str]:
    from warhammer40k_core.engine.mission_action_policies import (
        primary_mission_choice_rule_for_id,
    )
    from warhammer40k_core.engine.primary_mission_choices import LOCATE_AND_DENY_CHOICE_RULE_ID

    descriptor = primary_mission_choice_rule_for_id(LOCATE_AND_DENY_CHOICE_RULE_ID)
    return (descriptor.source_id, descriptor.choice_rule_id)


def evaluate_operation_marker_scoring_condition(
    *,
    condition_id: str,
    progress: PrimaryMissionProgressState,
    mission_setup: MissionSetup,
    player_id: str,
    battle_round: int,
    end_of_battle: bool,
    controlled_objective_ids: tuple[str, ...] = (),
    position_witnesses: tuple[PrimaryScoringRulesUnitPositionWitness, ...] | None = None,
) -> dict[str, JsonValue]:
    if condition_id not in PRIMARY_SCORING_OPERATION_MARKER_CONDITIONS:
        raise GameLifecycleError(f"Unsupported primary scoring condition: {condition_id}.")
    if type(progress) is not PrimaryMissionProgressState:
        raise GameLifecycleError(
            "Primary operation-marker scoring requires mission progress state."
        )
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Primary operation-marker scoring requires MissionSetup.")
    if type(end_of_battle) is not bool:
        raise GameLifecycleError("Primary operation-marker scoring end_of_battle must be a bool.")
    if type(battle_round) is not int or battle_round < 1:
        raise GameLifecycleError(
            "Primary operation-marker scoring battle_round must be a positive int."
        )
    if type(controlled_objective_ids) is not tuple:
        raise GameLifecycleError(
            "Primary operation-marker scoring controlled_objective_ids must be a tuple."
        )
    opponent_player_id = _opponent_player_id(mission_setup, player_id=player_id)
    if condition_id in _END_OF_BATTLE_OPERATION_MARKER_CONDITIONS and not end_of_battle:
        return _empty_operation_marker_evidence(
            condition_id=condition_id,
            matching=(),
            opponent_player_id=opponent_player_id,
        )
    if condition_id in PRIMARY_SCORING_OPERATION_MARKER_TERRAIN_CONDITIONS:
        if position_witnesses is None:
            raise GameLifecycleError(
                "Primary operation-marker terrain scoring requires position witnesses."
            )
        owner_player_id = (
            opponent_player_id
            if condition_id
            in {
                ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN,
                ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN_END_OF_BATTLE,
            }
            else player_id
        )
        matching = _active_operation_markers(progress, owner_player_id=owner_player_id)
        return _single_terrain_occupancy_evidence(
            matching=matching,
            mission_setup=mission_setup,
            scoring_player_id=player_id,
            opponent_player_id=opponent_player_id,
            position_witnesses=position_witnesses,
        )
    if condition_id == NO_ENEMY_OPERATION_MARKERS_ON_BATTLEFIELD:
        matching = _active_operation_markers(progress, owner_player_id=opponent_player_id)
        evidence = primary_score_count_evidence(score_count=1 if not matching else 0)
        evidence["operation_marker_ids"] = [marker.marker_id for marker in matching]
        evidence["opponent_player_id"] = opponent_player_id
        return evidence
    if condition_id == EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE:
        matching = _active_objective_operation_markers_for_identity(
            progress,
            owner_player_id=player_id,
            mission_id=mission_setup.primary_mission_id_for_player(player_id),
            source_identity=maintain_control_marker_source_identity(),
            mission_setup=mission_setup,
            require_unique_objective_anchors=False,
        )
        return _controlled_central_range_evidence(
            matching=matching,
            mission_setup=mission_setup,
            controlled_objective_ids=controlled_objective_ids,
        )
    matching = _active_objective_operation_markers_for_identity(
        progress,
        owner_player_id=player_id,
        mission_id=mission_setup.primary_mission_id_for_player(player_id),
        source_identity=extract_intelligence_marker_source_identity(),
        mission_setup=mission_setup,
        require_unique_objective_anchors=True,
    )
    if condition_id not in _EXTRACT_INTELLIGENCE_OPERATION_MARKER_CONDITIONS:
        raise GameLifecycleError(f"Unsupported primary scoring condition: {condition_id}.")
    if condition_id == THREE_OR_MORE_FRIENDLY_OPERATION_MARKERS_END_OF_BATTLE:
        evidence = primary_score_count_evidence(score_count=1 if len(matching) >= 3 else 0)
        evidence["operation_marker_ids"] = [marker.marker_id for marker in matching]
        evidence["objective_marker_ids"] = [_required_objective_id(marker) for marker in matching]
        evidence["objective_count_threshold"] = 3
        return evidence
    return _opponent_home_range_evidence(
        matching=matching,
        mission_setup=mission_setup,
        opponent_player_id=opponent_player_id,
    )


def _active_operation_markers(
    progress: PrimaryMissionProgressState,
    *,
    owner_player_id: str,
) -> tuple[PrimaryMissionMarkerState, ...]:
    matching = tuple(
        marker
        for marker in progress.markers
        if marker.status is PrimaryMissionMarkerStatus.ACTIVE
        and marker.marker_kind == _OPERATION_MARKER_KIND
        and marker.owner_player_id == owner_player_id
    )
    return tuple(sorted(matching, key=lambda marker: marker.marker_id))


def _active_objective_operation_markers_for_identity(
    progress: PrimaryMissionProgressState,
    *,
    owner_player_id: str,
    mission_id: str,
    source_identity: tuple[str, str],
    mission_setup: MissionSetup,
    require_unique_objective_anchors: bool,
) -> tuple[PrimaryMissionMarkerState, ...]:
    if type(require_unique_objective_anchors) is not bool:
        raise GameLifecycleError(
            "Primary scoring operation-marker uniqueness policy must be a bool."
        )
    expected_objective_ids = {
        marker.objective_marker_id for marker in mission_setup.objective_markers
    }
    matching: list[PrimaryMissionMarkerState] = []
    seen_objectives: set[str] = set()
    for marker in progress.markers:
        if marker.status is not PrimaryMissionMarkerStatus.ACTIVE:
            continue
        if marker.marker_kind != _OPERATION_MARKER_KIND:
            continue
        if marker.owner_player_id != owner_player_id or marker.mission_id != mission_id:
            continue
        if (marker.source_rule_id, marker.source_descriptor_id) != source_identity:
            continue
        if marker.anchor_kind is not MarkerAnchorKind.OBJECTIVE:
            raise GameLifecycleError(
                "Primary scoring operation marker source identity requires an objective anchor."
            )
        objective_id = _required_objective_id(marker)
        if objective_id not in expected_objective_ids:
            raise GameLifecycleError(
                "Primary scoring operation marker references an unknown objective."
            )
        if require_unique_objective_anchors:
            if objective_id in seen_objectives:
                raise GameLifecycleError(
                    "Primary scoring operation markers must not duplicate an objective."
                )
            seen_objectives.add(objective_id)
        matching.append(marker)
    return tuple(sorted(matching, key=lambda marker: marker.marker_id))


def _single_terrain_occupancy_evidence(
    *,
    matching: tuple[PrimaryMissionMarkerState, ...],
    mission_setup: MissionSetup,
    scoring_player_id: str,
    opponent_player_id: str,
    position_witnesses: tuple[PrimaryScoringRulesUnitPositionWitness, ...],
) -> dict[str, JsonValue]:
    terrain_area_ids = {
        area.logical_terrain_area_id for area in mission_logical_terrain_areas(mission_setup)
    }
    _validate_position_witnesses(
        position_witnesses,
        scoring_player_id=scoring_player_id,
        opponent_player_id=opponent_player_id,
        terrain_area_ids=terrain_area_ids,
    )
    if len(matching) != 1:
        evidence = primary_score_count_evidence(score_count=0)
        evidence["operation_marker_ids"] = [marker.marker_id for marker in matching]
        evidence["terrain_feature_ids"] = []
        evidence["friendly_unit_instance_ids"] = []
        evidence["enemy_unit_instance_ids"] = []
        evidence["opponent_player_id"] = opponent_player_id
        return evidence
    remaining = matching[0]
    if remaining.anchor_kind is not MarkerAnchorKind.TERRAIN_FEATURE:
        evidence = primary_score_count_evidence(score_count=0)
        evidence["operation_marker_ids"] = [remaining.marker_id]
        evidence["terrain_feature_ids"] = []
        evidence["friendly_unit_instance_ids"] = []
        evidence["enemy_unit_instance_ids"] = []
        evidence["opponent_player_id"] = opponent_player_id
        return evidence
    terrain_id = remaining.terrain_feature_id
    if terrain_id is None or terrain_id not in terrain_area_ids:
        raise GameLifecycleError(
            "Primary scoring operation marker references an unknown terrain area."
        )
    friendly_unit_ids = _occupying_unit_ids(
        position_witnesses,
        owner_player_id=scoring_player_id,
        terrain_id=terrain_id,
    )
    enemy_unit_ids = _occupying_unit_ids(
        position_witnesses,
        owner_player_id=opponent_player_id,
        terrain_id=terrain_id,
    )
    evidence = primary_score_count_evidence(
        score_count=1 if friendly_unit_ids and not enemy_unit_ids else 0
    )
    evidence["operation_marker_ids"] = [remaining.marker_id]
    evidence["terrain_feature_ids"] = [terrain_id]
    evidence["friendly_unit_instance_ids"] = list(friendly_unit_ids)
    evidence["enemy_unit_instance_ids"] = list(enemy_unit_ids)
    evidence["opponent_player_id"] = opponent_player_id
    return evidence


def _controlled_central_range_evidence(
    *,
    matching: tuple[PrimaryMissionMarkerState, ...],
    mission_setup: MissionSetup,
    controlled_objective_ids: tuple[str, ...],
) -> dict[str, JsonValue]:
    central_ids = {
        marker.objective_marker_id
        for marker in mission_setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    }
    controlled_central_ids = tuple(
        sorted(
            objective_id for objective_id in controlled_objective_ids if objective_id in central_ids
        )
    )
    scored = tuple(
        marker
        for marker in matching
        if any(
            _objective_within_control_range(
                mission_setup,
                source_objective_id=_required_objective_id(marker),
                target_objective_id=central_id,
            )
            for central_id in controlled_central_ids
        )
    )
    evidence = primary_score_count_evidence(
        score_count=len(scored),
        controlled_objective_ids=controlled_central_ids,
    )
    evidence["operation_marker_ids"] = [marker.marker_id for marker in scored]
    evidence["objective_marker_ids"] = [_required_objective_id(marker) for marker in scored]
    evidence["controlled_central_objective_ids"] = list(controlled_central_ids)
    return evidence


def _opponent_home_range_evidence(
    *,
    matching: tuple[PrimaryMissionMarkerState, ...],
    mission_setup: MissionSetup,
    opponent_player_id: str,
) -> dict[str, JsonValue]:
    opponent_home_ids = home_objective_ids(mission_setup, player_id=opponent_player_id)
    scored = tuple(
        marker
        for marker in matching
        if any(
            _objective_within_control_range(
                mission_setup,
                source_objective_id=_required_objective_id(marker),
                target_objective_id=home_id,
            )
            for home_id in opponent_home_ids
        )
    )
    evidence = primary_score_count_evidence(
        score_count=1 if scored else 0,
        home_objective_ids=opponent_home_ids,
    )
    evidence["operation_marker_ids"] = [marker.marker_id for marker in scored]
    evidence["objective_marker_ids"] = [_required_objective_id(marker) for marker in scored]
    evidence["opponent_home_objective_ids"] = list(opponent_home_ids)
    evidence["opponent_player_id"] = opponent_player_id
    return evidence


def _empty_operation_marker_evidence(
    *,
    condition_id: str,
    matching: tuple[PrimaryMissionMarkerState, ...],
    opponent_player_id: str,
) -> dict[str, JsonValue]:
    evidence = primary_score_count_evidence(score_count=0)
    evidence["operation_marker_ids"] = [marker.marker_id for marker in matching]
    if condition_id in PRIMARY_SCORING_OPERATION_MARKER_TERRAIN_CONDITIONS:
        evidence["terrain_feature_ids"] = []
        evidence["friendly_unit_instance_ids"] = []
        evidence["enemy_unit_instance_ids"] = []
        evidence["opponent_player_id"] = opponent_player_id
    return evidence


def _occupying_unit_ids(
    position_witnesses: tuple[PrimaryScoringRulesUnitPositionWitness, ...],
    *,
    owner_player_id: str,
    terrain_id: str,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                witness.rules_unit_instance_id
                for witness in position_witnesses
                if witness.owner_player_id == owner_player_id
                and terrain_id in witness.rules_unit_membership.logical_terrain_area_ids
            }
        )
    )


def _validate_position_witnesses(
    position_witnesses: tuple[PrimaryScoringRulesUnitPositionWitness, ...],
    *,
    scoring_player_id: str,
    opponent_player_id: str,
    terrain_area_ids: set[str],
) -> None:
    if type(position_witnesses) is not tuple:
        raise GameLifecycleError(
            "Primary operation-marker terrain scoring requires position-witness tuples."
        )
    seen_ids: set[str] = set()
    allowed_owners = {scoring_player_id, opponent_player_id}
    for witness in position_witnesses:
        if type(witness) is not PrimaryScoringRulesUnitPositionWitness:
            raise GameLifecycleError(
                "Primary operation-marker terrain scoring requires typed position witnesses."
            )
        if witness.rules_unit_instance_id in seen_ids:
            raise GameLifecycleError("Primary operation-marker position witnesses must be unique.")
        seen_ids.add(witness.rules_unit_instance_id)
        if witness.owner_player_id not in allowed_owners:
            raise GameLifecycleError(
                "Primary operation-marker position witness owner is not in MissionSetup."
            )
        unknown_terrain = (
            set(witness.rules_unit_membership.logical_terrain_area_ids) - terrain_area_ids
        )
        if unknown_terrain:
            raise GameLifecycleError(
                "Primary operation-marker position witness references an unknown terrain area."
            )


def _objective_within_control_range(
    mission_setup: MissionSetup,
    *,
    source_objective_id: str,
    target_objective_id: str,
) -> bool:
    if source_objective_id == target_objective_id:
        return True
    source = _objective_coordinates(mission_setup, source_objective_id)
    target = _objective_coordinates(mission_setup, target_objective_id)
    return math.hypot(source[0] - target[0], source[1] - target[1]) <= (
        OBJECTIVE_CONTROL_HORIZONTAL_INCHES
    )


def _objective_coordinates(mission_setup: MissionSetup, objective_id: str) -> tuple[float, float]:
    for marker in mission_setup.objective_markers:
        if marker.objective_marker_id == objective_id:
            return (marker.x_inches, marker.y_inches)
    raise GameLifecycleError("Primary scoring operation marker references an unknown objective.")


def _required_objective_id(marker: PrimaryMissionMarkerState) -> str:
    objective_id = marker.objective_marker_id
    if objective_id is None:
        raise GameLifecycleError(
            "Primary scoring operation marker is missing its objective anchor."
        )
    return objective_id


def _opponent_player_id(mission_setup: MissionSetup, *, player_id: str) -> str:
    mission_player_ids = (
        mission_setup.attacker_player_id,
        mission_setup.defender_player_id,
    )
    if player_id not in mission_player_ids:
        raise GameLifecycleError("Primary operation-marker scoring player is not in MissionSetup.")
    return next(
        mission_player_id
        for mission_player_id in mission_player_ids
        if mission_player_id != player_id
    )


__all__ = (
    "EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE",
    "FRIENDLY_OPERATION_MARKER_WITHIN_OPPONENT_HOME_RANGE_END_OF_BATTLE",
    "MAINTAIN_CONTROL_ACTION_ID",
    "NO_ENEMY_OPERATION_MARKERS_ON_BATTLEFIELD",
    "ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN",
    "ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN_END_OF_BATTLE",
    "ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN",
    "ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN_END_OF_BATTLE",
    "PRIMARY_SCORING_OPERATION_MARKER_CONDITIONS",
    "PRIMARY_SCORING_OPERATION_MARKER_TERRAIN_CONDITIONS",
    "THREE_OR_MORE_FRIENDLY_OPERATION_MARKERS_END_OF_BATTLE",
    "evaluate_operation_marker_scoring_condition",
    "extract_intelligence_marker_source_identity",
    "locate_and_deny_marker_source_identity",
    "maintain_control_marker_source_identity",
)
