from __future__ import annotations

from typing import cast

from warhammer40k_core.core.missions import MissionActionDefinition
from warhammer40k_core.engine import mission_terrain
from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import mission_pack_for_id
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.scoring import (
    PrimaryTerrainTrapState,
    SecondaryObjectiveCleanseState,
    SecondaryTerrainPlunderState,
)


def validate_primary_terrain_trap_states(
    states: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
    mission_setup: MissionSetup | None,
    mission_action_states: list[MissionActionState],
) -> list[PrimaryTerrainTrapState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState primary terrain trap states must be a list.")
    validated: list[PrimaryTerrainTrapState] = []
    seen_ids: set[str] = set()
    seen_traps: set[tuple[str, str]] = set()
    logical_areas = mission_terrain.optional_mission_logical_terrain_areas(mission_setup)
    known_area_ids = {area.logical_terrain_area_id for area in logical_areas}
    objective_area_ids = mission_terrain.objective_logical_terrain_area_ids(mission_setup)
    for state in cast(list[object], states):
        if type(state) is not PrimaryTerrainTrapState:
            raise GameLifecycleError(
                "GameState primary terrain trap states must contain state values."
            )
        if state.game_id != game_id:
            raise GameLifecycleError("PrimaryTerrainTrapState game_id drift.")
        if state.player_id not in player_ids or state.active_player_id not in player_ids:
            raise GameLifecycleError("PrimaryTerrainTrapState player_id is not in this game.")
        if state.trap_id in seen_ids:
            raise GameLifecycleError("GameState primary terrain trap states must be unique.")
        if state.terrain_feature_id not in known_area_ids:
            raise GameLifecycleError(
                "PrimaryTerrainTrapState references an unknown logical terrain area."
            )
        if state.is_objective != (state.terrain_feature_id in objective_area_ids):
            raise GameLifecycleError(
                "PrimaryTerrainTrapState objective association drifted from MissionSetup."
            )
        trap_key = (state.player_id, state.terrain_feature_id)
        if trap_key in seen_traps:
            raise GameLifecycleError(
                "GameState primary terrain trap states must be unique per player and terrain."
            )
        seen_ids.add(state.trap_id)
        seen_traps.add(trap_key)
        validated.append(state)
    if validated and mission_setup is None:
        raise GameLifecycleError("PrimaryTerrainTrapState requires MissionSetup.")
    for state in validated:
        validate_primary_terrain_trap_action_link(
            state,
            mission_setup=cast(MissionSetup, mission_setup),
            mission_action_states=mission_action_states,
        )
    return sorted(validated, key=lambda state: state.trap_id)


def validate_secondary_objective_cleanse_states(
    states: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
    mission_setup: MissionSetup | None,
    mission_action_states: list[MissionActionState],
) -> list[SecondaryObjectiveCleanseState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState secondary objective cleanse states must be a list.")
    validated: list[SecondaryObjectiveCleanseState] = []
    seen_ids: set[str] = set()
    seen_actions: set[str] = set()
    seen_objective_turns: set[tuple[str, int, str, str]] = set()
    for state in cast(list[object], states):
        if type(state) is not SecondaryObjectiveCleanseState:
            raise GameLifecycleError(
                "GameState secondary objective cleanse states must contain state values."
            )
        if state.game_id != game_id:
            raise GameLifecycleError("SecondaryObjectiveCleanseState game_id drift.")
        if state.player_id not in player_ids or state.active_player_id not in player_ids:
            raise GameLifecycleError(
                "SecondaryObjectiveCleanseState player_id is not in this game."
            )
        if state.cleanse_id in seen_ids:
            raise GameLifecycleError("GameState secondary objective cleanse states must be unique.")
        if state.action_id in seen_actions:
            raise GameLifecycleError(
                "GameState secondary objective cleanse states must be unique per action."
            )
        objective_key = (
            state.player_id,
            state.battle_round,
            state.active_player_id,
            state.objective_marker_id,
        )
        if objective_key in seen_objective_turns:
            raise GameLifecycleError(
                "GameState secondary objective cleanse states must be unique per objective turn."
            )
        seen_ids.add(state.cleanse_id)
        seen_actions.add(state.action_id)
        seen_objective_turns.add(objective_key)
        validated.append(state)
    if validated and mission_setup is None:
        raise GameLifecycleError("SecondaryObjectiveCleanseState requires MissionSetup.")
    for state in validated:
        validate_secondary_objective_cleanse_action_link(
            state,
            mission_setup=cast(MissionSetup, mission_setup),
            mission_action_states=mission_action_states,
        )
    return sorted(validated, key=lambda state: state.cleanse_id)


def validate_secondary_terrain_plunder_states(
    states: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
    mission_setup: MissionSetup | None,
    mission_action_states: list[MissionActionState],
) -> list[SecondaryTerrainPlunderState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState secondary terrain plunder states must be a list.")
    validated: list[SecondaryTerrainPlunderState] = []
    seen_ids: set[str] = set()
    seen_actions: set[str] = set()
    seen_player_turns: set[tuple[str, int, str]] = set()
    logical_areas = mission_terrain.optional_mission_logical_terrain_areas(mission_setup)
    known_area_ids = {area.logical_terrain_area_id for area in logical_areas}
    for state in cast(list[object], states):
        if type(state) is not SecondaryTerrainPlunderState:
            raise GameLifecycleError(
                "GameState secondary terrain plunder states must contain state values."
            )
        if state.game_id != game_id:
            raise GameLifecycleError("SecondaryTerrainPlunderState game_id drift.")
        if state.player_id not in player_ids or state.active_player_id not in player_ids:
            raise GameLifecycleError("SecondaryTerrainPlunderState player_id is not in this game.")
        if state.plunder_id in seen_ids:
            raise GameLifecycleError("GameState secondary terrain plunder states must be unique.")
        if state.terrain_feature_id not in known_area_ids:
            raise GameLifecycleError(
                "SecondaryTerrainPlunderState references an unknown logical terrain area."
            )
        if state.action_id in seen_actions:
            raise GameLifecycleError(
                "GameState secondary terrain plunder states must be unique per action."
            )
        player_turn_key = (state.player_id, state.battle_round, state.active_player_id)
        if player_turn_key in seen_player_turns:
            raise GameLifecycleError(
                "GameState secondary terrain plunder states must be unique per player turn."
            )
        seen_ids.add(state.plunder_id)
        seen_actions.add(state.action_id)
        seen_player_turns.add(player_turn_key)
        validated.append(state)
    if validated and mission_setup is None:
        raise GameLifecycleError("SecondaryTerrainPlunderState requires MissionSetup.")
    for state in validated:
        validate_secondary_terrain_plunder_action_link(
            state,
            mission_setup=cast(MissionSetup, mission_setup),
            mission_action_states=mission_action_states,
        )
    return sorted(validated, key=lambda state: state.plunder_id)


def validate_primary_terrain_trap_action_link(
    state: PrimaryTerrainTrapState,
    *,
    mission_setup: MissionSetup,
    mission_action_states: list[MissionActionState],
) -> None:
    expected_trap_id = (
        f"primary-terrain-trap:{state.game_id}:round-{state.battle_round:02d}:"
        f"{state.player_id}:{state.terrain_feature_id}"
    )
    _validate_mission_action_evidence_link(
        evidence_kind="PrimaryTerrainTrapState",
        evidence_id=state.trap_id,
        expected_evidence_id=expected_trap_id,
        player_id=state.player_id,
        active_player_id=state.active_player_id,
        battle_round=state.battle_round,
        phase=state.phase,
        target_id=state.terrain_feature_id,
        action_id=state.action_id,
        source_id=state.source_id,
        expected_target_policy="trappable_terrain_area",
        expected_mission_kind="primary",
        mission_setup=mission_setup,
        mission_action_states=mission_action_states,
    )


def validate_secondary_objective_cleanse_action_link(
    state: SecondaryObjectiveCleanseState,
    *,
    mission_setup: MissionSetup,
    mission_action_states: list[MissionActionState],
) -> None:
    expected_cleanse_id = (
        f"secondary-objective-cleanse:{state.game_id}:round-{state.battle_round:02d}:"
        f"{state.player_id}:{state.objective_marker_id}"
    )
    _validate_mission_action_evidence_link(
        evidence_kind="SecondaryObjectiveCleanseState",
        evidence_id=state.cleanse_id,
        expected_evidence_id=expected_cleanse_id,
        player_id=state.player_id,
        active_player_id=state.active_player_id,
        battle_round=state.battle_round,
        phase=state.phase,
        target_id=state.objective_marker_id,
        action_id=state.action_id,
        source_id=state.source_id,
        expected_target_policy="objective_marker",
        expected_mission_kind="secondary",
        mission_setup=mission_setup,
        mission_action_states=mission_action_states,
    )


def validate_secondary_terrain_plunder_action_link(
    state: SecondaryTerrainPlunderState,
    *,
    mission_setup: MissionSetup,
    mission_action_states: list[MissionActionState],
) -> None:
    expected_plunder_id = (
        f"secondary-terrain-plunder:{state.game_id}:round-{state.battle_round:02d}:"
        f"{state.player_id}:{state.terrain_feature_id}"
    )
    _validate_mission_action_evidence_link(
        evidence_kind="SecondaryTerrainPlunderState",
        evidence_id=state.plunder_id,
        expected_evidence_id=expected_plunder_id,
        player_id=state.player_id,
        active_player_id=state.active_player_id,
        battle_round=state.battle_round,
        phase=state.phase,
        target_id=state.terrain_feature_id,
        action_id=state.action_id,
        source_id=state.source_id,
        expected_target_policy="plunderable_terrain_area",
        expected_mission_kind="secondary",
        mission_setup=mission_setup,
        mission_action_states=mission_action_states,
    )


def source_action_for_mission_identity(
    *,
    mission_setup: MissionSetup,
    mission_id: str,
    expected_target_policy: str,
    expected_mission_kind: str,
    evidence_kind: str,
) -> MissionActionDefinition:
    mission_pack = mission_pack_for_id(mission_setup.mission_pack_id)
    matches = tuple(
        action
        for action in mission_pack.mission_actions
        if action.mission_id == mission_id
        and action.target_policy == expected_target_policy
        and action.mission_kind == expected_mission_kind
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            f"{evidence_kind} mission identity does not select one source-backed Mission Action."
        )
    return matches[0]


def _validate_mission_action_evidence_link(
    *,
    evidence_kind: str,
    evidence_id: str,
    expected_evidence_id: str,
    player_id: str,
    active_player_id: str,
    battle_round: int,
    phase: str,
    target_id: str,
    action_id: str,
    source_id: str,
    expected_target_policy: str,
    expected_mission_kind: str,
    mission_setup: MissionSetup,
    mission_action_states: list[MissionActionState],
) -> None:
    if evidence_id != expected_evidence_id:
        raise GameLifecycleError(f"{evidence_kind} identity drifted from canonical fields.")
    if active_player_id != player_id:
        raise GameLifecycleError(f"{evidence_kind} must be recorded during its owner's turn.")
    matching_actions = tuple(
        action for action in mission_action_states if action.action_id == action_id
    )
    if len(matching_actions) != 1:
        raise GameLifecycleError(
            f"{evidence_kind} requires exactly one matching completed MissionActionState."
        )
    action_state = matching_actions[0]
    source_action = _source_terrain_mission_action(
        mission_setup=mission_setup,
        source_id=source_id,
        expected_target_policy=expected_target_policy,
        expected_mission_kind=expected_mission_kind,
        evidence_kind=evidence_kind,
    )
    if (
        action_state.status is not MissionActionStatus.COMPLETED
        or action_state.victory_points != 0
        or action_state.score_transaction_id is not None
    ):
        raise GameLifecycleError(
            f"{evidence_kind} requires a completed zero-VP MissionActionState."
        )
    if action_state.player_id != player_id or action_state.target_id != target_id:
        raise GameLifecycleError(f"{evidence_kind} Mission Action player or target drifted.")
    if (
        action_state.battle_round_started != battle_round
        or action_state.completed_battle_round != battle_round
        or action_state.completed_phase != phase
    ):
        raise GameLifecycleError(f"{evidence_kind} Mission Action completion timing drifted.")
    if (
        action_state.mission_id != source_action.mission_id
        or action_state.phase_started != source_action.start_phase
        or action_state.start_timing != source_action.start_timing
        or action_state.completion_timing != source_action.completion_timing
        or action_state.interruption_conditions != source_action.interruption_conditions
        or action_state.scoring_source_id != source_action.scoring_source_id
        or action_state.victory_points != source_action.victory_points
    ):
        raise GameLifecycleError(
            f"{evidence_kind} Mission Action drifted from its source-backed descriptor."
        )
    if expected_mission_kind == "primary":
        assignment = mission_setup.primary_mission_assignment_for_player(player_id)
        if assignment.primary_mission_id != source_action.mission_id:
            raise GameLifecycleError(
                f"{evidence_kind} Mission Action does not match the player's Primary mission."
            )


def _source_terrain_mission_action(
    *,
    mission_setup: MissionSetup,
    source_id: str,
    expected_target_policy: str,
    expected_mission_kind: str,
    evidence_kind: str,
) -> MissionActionDefinition:
    mission_pack = mission_pack_for_id(mission_setup.mission_pack_id)
    matches = tuple(
        action for action in mission_pack.mission_actions if action.source_id == source_id
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            f"{evidence_kind} source_id does not identify one source-backed Mission Action."
        )
    source_action = matches[0]
    if (
        source_action.target_policy != expected_target_policy
        or source_action.mission_kind != expected_mission_kind
    ):
        raise GameLifecycleError(
            f"{evidence_kind} source-backed Mission Action has the wrong terrain target policy."
        )
    return source_action


__all__ = (
    "source_action_for_mission_identity",
    "validate_primary_terrain_trap_action_link",
    "validate_primary_terrain_trap_states",
    "validate_secondary_objective_cleanse_action_link",
    "validate_secondary_objective_cleanse_states",
    "validate_secondary_terrain_plunder_action_link",
    "validate_secondary_terrain_plunder_states",
)
