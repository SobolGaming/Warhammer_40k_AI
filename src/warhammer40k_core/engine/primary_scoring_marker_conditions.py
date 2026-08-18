from __future__ import annotations

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_state import (
    MarkerAnchorKind,
    PrimaryConsecrationStatus,
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    PrimaryMissionProgressState,
    is_consecrated_objective_marker,
)
from warhammer40k_core.engine.primary_scoring_conditions import (
    home_objective_ids,
    primary_score_count_evidence,
)

DECOY_OBJECTIVE_ACTION_ID = "decoy-objective"
TRIANGULATE_OBJECTIVE_ACTION_ID = "triangulate-objective"

PRIMARY_SCORING_MARKER_CONDITIONS = frozenset(
    {
        "each_decoy_objective",
        "each_decoy_objective_in_opponent_territory_bonus",
        "enemy_home_objective_consecrated_end_of_battle",
        "exactly_one_triangulated_objective",
        "exactly_two_triangulated_objectives",
        "four_or_more_decoy_objectives_end_of_battle",
        "one_or_two_objectives_consecrated",
        "three_or_more_objectives_consecrated",
        "three_or_more_triangulated_objectives",
    }
)


def consecrated_marker_source_identity() -> tuple[str, str]:
    from warhammer40k_core.engine.mission_action_policies import (
        primary_mission_choice_rule_for_id,
    )
    from warhammer40k_core.engine.primary_mission_choices import CONSECRATE_CHOICE_RULE_ID

    descriptor = primary_mission_choice_rule_for_id(CONSECRATE_CHOICE_RULE_ID)
    return (descriptor.source_id, descriptor.choice_rule_id)


def decoy_marker_source_identity() -> tuple[str, str]:
    from warhammer40k_core.engine.mission_action_policies import mission_action_policy_for_id

    policy = mission_action_policy_for_id(DECOY_OBJECTIVE_ACTION_ID)
    return (policy.source_id, policy.mission_action_id)


def triangulated_marker_source_identity() -> tuple[str, str]:
    from warhammer40k_core.engine.mission_action_policies import mission_action_policy_for_id

    policy = mission_action_policy_for_id(TRIANGULATE_OBJECTIVE_ACTION_ID)
    return (policy.source_id, policy.mission_action_id)


def active_consecrated_objective_ids(
    progress: PrimaryMissionProgressState,
    *,
    player_id: str,
    mission_id: str,
    mission_setup: MissionSetup,
) -> tuple[str, ...]:
    return _active_objective_ids_for_identity(
        progress,
        player_id=player_id,
        mission_id=mission_id,
        mission_setup=mission_setup,
        source_identity=consecrated_marker_source_identity(),
        require_consecrated_designation=True,
    )


def active_decoy_objective_ids(
    progress: PrimaryMissionProgressState,
    *,
    player_id: str,
    mission_id: str,
    mission_setup: MissionSetup,
) -> tuple[str, ...]:
    return _active_objective_ids_for_identity(
        progress,
        player_id=player_id,
        mission_id=mission_id,
        mission_setup=mission_setup,
        source_identity=decoy_marker_source_identity(),
        require_consecrated_designation=False,
    )


def active_triangulated_objective_ids(
    progress: PrimaryMissionProgressState,
    *,
    player_id: str,
    mission_id: str,
    mission_setup: MissionSetup,
) -> tuple[str, ...]:
    return _active_objective_ids_for_identity(
        progress,
        player_id=player_id,
        mission_id=mission_id,
        mission_setup=mission_setup,
        source_identity=triangulated_marker_source_identity(),
        require_consecrated_designation=False,
    )


def evaluate_marker_scoring_condition(
    *,
    condition_id: str,
    progress: PrimaryMissionProgressState,
    mission_setup: MissionSetup,
    player_id: str,
    battle_round: int,
    end_of_battle: bool,
    opponent_territory_objective_ids: tuple[str, ...] | None = None,
    opponent_player_id: str | None = None,
) -> dict[str, JsonValue]:
    if condition_id not in PRIMARY_SCORING_MARKER_CONDITIONS:
        raise GameLifecycleError(f"Unsupported primary scoring condition: {condition_id}.")
    if type(progress) is not PrimaryMissionProgressState:
        raise GameLifecycleError("Primary marker scoring requires mission progress state.")
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Primary marker scoring requires MissionSetup.")
    if type(end_of_battle) is not bool:
        raise GameLifecycleError("Primary marker scoring end_of_battle must be a bool.")
    if type(battle_round) is not int or battle_round < 1:
        raise GameLifecycleError("Primary marker scoring battle_round must be a positive int.")
    mission_id = mission_setup.primary_mission_id_for_player(player_id)
    if condition_id in {
        "one_or_two_objectives_consecrated",
        "three_or_more_objectives_consecrated",
        "enemy_home_objective_consecrated_end_of_battle",
    }:
        matching = active_consecrated_objective_ids(
            progress,
            player_id=player_id,
            mission_id=mission_id,
            mission_setup=mission_setup,
        )
        return _consecrated_condition_evidence(
            condition_id=condition_id,
            matching=matching,
            mission_setup=mission_setup,
            player_id=player_id,
            end_of_battle=end_of_battle,
        )
    if condition_id in {
        "exactly_one_triangulated_objective",
        "exactly_two_triangulated_objectives",
        "three_or_more_triangulated_objectives",
    }:
        matching = active_triangulated_objective_ids(
            progress,
            player_id=player_id,
            mission_id=mission_id,
            mission_setup=mission_setup,
        )
        windowed = matching if battle_round >= 2 else ()
        return _triangulated_condition_evidence(condition_id=condition_id, matching=windowed)
    matching = active_decoy_objective_ids(
        progress,
        player_id=player_id,
        mission_id=mission_id,
        mission_setup=mission_setup,
    )
    return _decoy_condition_evidence(
        condition_id=condition_id,
        matching=matching,
        end_of_battle=end_of_battle,
        opponent_territory_objective_ids=opponent_territory_objective_ids,
        opponent_player_id=opponent_player_id,
    )


def _active_objective_ids_for_identity(
    progress: PrimaryMissionProgressState,
    *,
    player_id: str,
    mission_id: str,
    mission_setup: MissionSetup,
    source_identity: tuple[str, str],
    require_consecrated_designation: bool,
) -> tuple[str, ...]:
    if type(progress) is not PrimaryMissionProgressState:
        raise GameLifecycleError("Primary marker scoring requires mission progress state.")
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Primary marker scoring requires MissionSetup.")
    expected_objective_ids = {
        marker.objective_marker_id for marker in mission_setup.objective_markers
    }
    matching: list[str] = []
    seen: set[str] = set()
    for marker in progress.markers:
        if not _marker_matches_identity(
            marker,
            progress=progress,
            player_id=player_id,
            mission_id=mission_id,
            source_identity=source_identity,
            require_consecrated_designation=require_consecrated_designation,
        ):
            continue
        objective_id = marker.objective_marker_id
        if objective_id is None:
            raise GameLifecycleError("Primary scoring marker is missing its objective anchor.")
        if objective_id not in expected_objective_ids:
            raise GameLifecycleError("Primary scoring marker references an unknown objective.")
        if objective_id in seen:
            raise GameLifecycleError("Primary scoring markers must not duplicate an objective.")
        seen.add(objective_id)
        matching.append(objective_id)
    return tuple(sorted(matching))


def _marker_matches_identity(
    marker: PrimaryMissionMarkerState,
    *,
    progress: PrimaryMissionProgressState,
    player_id: str,
    mission_id: str,
    source_identity: tuple[str, str],
    require_consecrated_designation: bool,
) -> bool:
    if type(marker) is not PrimaryMissionMarkerState:
        raise GameLifecycleError("Primary scoring markers must be typed marker state.")
    if marker.status is not PrimaryMissionMarkerStatus.ACTIVE:
        return False
    if marker.owner_player_id != player_id or marker.mission_id != mission_id:
        return False
    if marker.anchor_kind is not MarkerAnchorKind.OBJECTIVE:
        return False
    if (marker.source_rule_id, marker.source_descriptor_id) != source_identity:
        return False
    if not require_consecrated_designation:
        return True
    if not is_consecrated_objective_marker(marker, source_identity):
        return False
    designation = next(
        (
            candidate
            for candidate in progress.consecration_designations
            if candidate.designation_id == marker.source_designation_id
        ),
        None,
    )
    if designation is None:
        raise GameLifecycleError("Primary scoring consecrated marker is missing its designation.")
    if designation.status is not PrimaryConsecrationStatus.CONSUMED:
        raise GameLifecycleError(
            "Primary scoring consecrated marker requires a consumed designation."
        )
    if designation.consumed_marker_id != marker.marker_id:
        raise GameLifecycleError("Primary scoring consecrated marker designation linkage drifted.")
    return True


def _consecrated_condition_evidence(
    *,
    condition_id: str,
    matching: tuple[str, ...],
    mission_setup: MissionSetup,
    player_id: str,
    end_of_battle: bool,
) -> dict[str, JsonValue]:
    if condition_id == "one_or_two_objectives_consecrated":
        evidence = primary_score_count_evidence(
            score_count=1 if 1 <= len(matching) <= 2 else 0,
            controlled_objective_ids=matching,
        )
        evidence["consecrated_objective_ids"] = list(matching)
        return evidence
    if condition_id == "three_or_more_objectives_consecrated":
        evidence = primary_score_count_evidence(
            score_count=1 if len(matching) >= 3 else 0,
            controlled_objective_ids=matching,
        )
        evidence["consecrated_objective_ids"] = list(matching)
        evidence["objective_count_threshold"] = 3
        return evidence
    counted = matching if end_of_battle else ()
    opponent_player_id = _opponent_player_id(mission_setup, player_id=player_id)
    opponent_home_ids = home_objective_ids(mission_setup, player_id=opponent_player_id)
    hit = tuple(objective_id for objective_id in counted if objective_id in opponent_home_ids)
    evidence = primary_score_count_evidence(
        score_count=1 if hit else 0,
        controlled_objective_ids=hit,
        home_objective_ids=opponent_home_ids,
    )
    evidence["consecrated_objective_ids"] = list(matching)
    evidence["opponent_home_objective_ids"] = list(opponent_home_ids)
    evidence["opponent_player_id"] = opponent_player_id
    return evidence


def _triangulated_condition_evidence(
    *,
    condition_id: str,
    matching: tuple[str, ...],
) -> dict[str, JsonValue]:
    count = len(matching)
    if condition_id == "exactly_one_triangulated_objective":
        score_count = 1 if count == 1 else 0
        threshold: int | None = None
    elif condition_id == "exactly_two_triangulated_objectives":
        score_count = 1 if count == 2 else 0
        threshold = None
    else:
        score_count = 1 if count >= 3 else 0
        threshold = 3
    evidence = primary_score_count_evidence(
        score_count=score_count,
        controlled_objective_ids=matching,
    )
    evidence["triangulated_objective_ids"] = list(matching)
    if threshold is not None:
        evidence["objective_count_threshold"] = threshold
    return evidence


def _decoy_condition_evidence(
    *,
    condition_id: str,
    matching: tuple[str, ...],
    end_of_battle: bool,
    opponent_territory_objective_ids: tuple[str, ...] | None,
    opponent_player_id: str | None,
) -> dict[str, JsonValue]:
    if condition_id == "each_decoy_objective":
        evidence = primary_score_count_evidence(
            score_count=len(matching),
            controlled_objective_ids=matching,
        )
        evidence["decoy_objective_ids"] = list(matching)
        return evidence
    if condition_id == "four_or_more_decoy_objectives_end_of_battle":
        counted = matching if end_of_battle else ()
        evidence = primary_score_count_evidence(
            score_count=1 if len(counted) >= 4 else 0,
            controlled_objective_ids=counted,
        )
        evidence["decoy_objective_ids"] = list(matching)
        evidence["objective_count_threshold"] = 4
        return evidence
    if opponent_territory_objective_ids is None or opponent_player_id is None:
        raise GameLifecycleError(
            "Primary scoring condition each_decoy_objective_in_opponent_territory_bonus "
            "requires spatial evidence."
        )
    in_territory = tuple(
        objective_id
        for objective_id in matching
        if objective_id in opponent_territory_objective_ids
    )
    evidence = primary_score_count_evidence(
        score_count=len(in_territory),
        controlled_objective_ids=in_territory,
    )
    evidence["decoy_objective_ids"] = list(matching)
    evidence["opponent_territory_objective_ids"] = list(opponent_territory_objective_ids)
    evidence["opponent_player_id"] = opponent_player_id
    return evidence


def _opponent_player_id(mission_setup: MissionSetup, *, player_id: str) -> str:
    mission_player_ids = (
        mission_setup.attacker_player_id,
        mission_setup.defender_player_id,
    )
    if player_id not in mission_player_ids:
        raise GameLifecycleError("Primary marker scoring player is not in MissionSetup.")
    return next(
        mission_player_id
        for mission_player_id in mission_player_ids
        if mission_player_id != player_id
    )


__all__ = (
    "DECOY_OBJECTIVE_ACTION_ID",
    "PRIMARY_SCORING_MARKER_CONDITIONS",
    "TRIANGULATE_OBJECTIVE_ACTION_ID",
    "active_consecrated_objective_ids",
    "active_decoy_objective_ids",
    "active_triangulated_objective_ids",
    "consecrated_marker_source_identity",
    "decoy_marker_source_identity",
    "evaluate_marker_scoring_condition",
    "triangulated_marker_source_identity",
)
