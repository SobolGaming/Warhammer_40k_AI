"""Explicit Mission Action request construction at its resumable OC boundary."""

from __future__ import annotations

# Request construction shares the mission decision owner's validation primitives.
# pyright: reportPrivateUsage=false
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_action_modifier_evaluation import (
    MISSION_ACTION_OC_SCOPE_KEY,
    prepare_mission_action_modifiers,
)
from warhammer40k_core.engine.mission_action_options import (
    SUPPORTED_MISSION_ACTION_TARGET_POLICIES as _SUPPORTED_MISSION_ACTION_TARGET_POLICIES,
)
from warhammer40k_core.engine.mission_action_options import (
    available_mission_actions_for_state as _available_mission_actions_for_state,
)
from warhammer40k_core.engine.mission_action_options import (
    mission_action_for_state as _mission_action_for_state,
)
from warhammer40k_core.engine.mission_action_options import (
    mission_action_start_options as _mission_action_start_options,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.primary_mission_boundary_checkpoint import (
    record_primary_mission_boundary_checkpoint,
)
from warhammer40k_core.engine.random_objective_control import (
    record_unavailable_mission_action_profiles,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def request_mission_action_start(
    *,
    state: GameState,
    decisions: DecisionController,
    player_id: str,
    mission_action_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus:
    from warhammer40k_core.engine.mission_decisions import (
        START_MISSION_ACTION_DECISION_TYPE,
        _assert_battle_state,
        _current_phase,
        _require_runtime_modifier_registry,
        _validate_active_player_id,
    )

    _assert_battle_state(state)
    _require_runtime_modifier_registry(runtime_modifier_registry)
    requested_player = _validate_active_player_id(state=state, player_id=player_id)
    phase = _current_phase(state)
    mission_action = _mission_action_for_state(state=state, mission_action_id=mission_action_id)
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise GameLifecycleError("Mission Action start requires MissionSetup.")
    available_action_ids = {
        action.mission_action_id
        for action in _available_mission_actions_for_state(
            state=state,
            player_id=requested_player,
        )
    }
    if mission_action.mission_action_id not in available_action_ids:
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="Mission Action does not belong to the active Primary or a held Secondary.",
            payload={
                "game_id": state.game_id,
                "player_id": requested_player,
                "mission_action_id": mission_action.mission_action_id,
                "mission_id": mission_action.mission_id,
                "active_primary_mission_id": mission_setup.primary_mission_id_for_player(
                    requested_player
                ),
            },
        )
    if mission_action.target_policy not in _SUPPORTED_MISSION_ACTION_TARGET_POLICIES:
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="Mission Action target selection is not implemented for this target policy.",
            payload={
                "game_id": state.game_id,
                "player_id": requested_player,
                "mission_action_id": mission_action.mission_action_id,
                "target_policy": mission_action.target_policy,
            },
        )
    if phase.value != mission_action.start_phase:
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="Mission Action cannot start in the current battle phase.",
            payload={
                "game_id": state.game_id,
                "player_id": requested_player,
                "mission_action_id": mission_action.mission_action_id,
                "current_phase": phase.value,
                "required_phase": mission_action.start_phase,
            },
        )
    evaluation = prepare_mission_action_modifiers(
        state=state,
        decisions=decisions,
        player_id=requested_player,
        actions=(mission_action,),
        explicit_action_id=mission_action.mission_action_id,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if evaluation.pending_status is not None:
        return evaluation.pending_status
    runtime_modifier_registry = evaluation.registry
    options = _mission_action_start_options(
        state=state,
        player_id=requested_player,
        action=mission_action,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if not options:
        record_unavailable_mission_action_profiles(state=state, decisions=decisions)
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="No legal Mission Action start options are available.",
            payload={
                "game_id": state.game_id,
                "player_id": requested_player,
                "mission_action_id": mission_action.mission_action_id,
            },
        )
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=START_MISSION_ACTION_DECISION_TYPE,
        actor_id=requested_player,
        payload={
            "game_id": state.game_id,
            "player_id": requested_player,
            "battle_round": state.battle_round,
            "phase": phase.value,
            "mission_action_id": mission_action.mission_action_id,
            MISSION_ACTION_OC_SCOPE_KEY: evaluation.occurrence_id,
            "legal_option_ids": [option.option_id() for option in options],
        },
        options=tuple(
            DecisionOption(
                option_id=option.option_id(),
                label=option.label(state=state),
                payload={
                    **option.payload(
                        state=state,
                        player_id=requested_player,
                        phase=phase,
                    ),
                    MISSION_ACTION_OC_SCOPE_KEY: evaluation.occurrence_id,
                },
            )
            for option in options
        ),
    )
    record_primary_mission_boundary_checkpoint(
        state=state,
        event_log=decisions.event_log,
        boundary_kind="action_request",
        player_id=requested_player,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "game_id": state.game_id,
            "player_id": requested_player,
            "decision_type": START_MISSION_ACTION_DECISION_TYPE,
        },
    )
