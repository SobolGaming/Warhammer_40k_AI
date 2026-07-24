from __future__ import annotations

from itertools import combinations
from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.actions import MissionActionState
from warhammer40k_core.engine.battlefield_state import PlacementError
from warhammer40k_core.engine.command_points import (
    CommandPointGainStatus,
    CommandPointSourceKind,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
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
    mission_action_opportunity_drift_reason as _mission_action_opportunity_drift_reason,
)
from warhammer40k_core.engine.mission_action_options import (
    mission_action_opportunity_options as _mission_action_opportunity_options,
)
from warhammer40k_core.engine.mission_action_options import (
    mission_action_start_options as _mission_action_start_options,
)
from warhammer40k_core.engine.missions import mission_scoring_policy_from_setup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    TacticalSecondaryAchievementContext,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)

TACTICAL_SECONDARY_SCORE_DECISION_TYPE = "score_tactical_secondary_mission"
TACTICAL_SECONDARY_DISCARD_DECISION_TYPE = "discard_tactical_secondary_mission"
START_MISSION_ACTION_DECISION_TYPE = "start_mission_action"
DECLINE_MISSION_ACTION_START_OPTION_ID = "continue_to_shooting"
MISSION_DECISION_TYPES = frozenset(
    (
        TACTICAL_SECONDARY_SCORE_DECISION_TYPE,
        TACTICAL_SECONDARY_DISCARD_DECISION_TYPE,
        START_MISSION_ACTION_DECISION_TYPE,
    )
)


def mission_decision_pauses_after_apply(request: DecisionRequest) -> bool:
    if request.decision_type != START_MISSION_ACTION_DECISION_TYPE:
        return False
    payload = _payload_object(request.payload)
    opportunity = payload.get("mission_action_opportunity")
    if opportunity is not None and type(opportunity) is not bool:
        raise GameLifecycleError("mission_action_opportunity must be a bool.")
    return opportunity is not True


def request_mission_action_opportunity(
    *,
    state: GameState,
    decisions: DecisionController,
    player_id: str,
) -> LifecycleStatus | None:
    _assert_battle_state(state)
    requested_player = _validate_active_player_id(state=state, player_id=player_id)
    phase = _current_phase(state)
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        raise GameLifecycleError("Mission Action opportunity requires ShootingPhaseState.")
    if shooting_state.mission_action_opportunity_declined:
        return None
    relevant_actions = _available_mission_actions_for_state(
        state=state,
        player_id=requested_player,
    )
    unsupported_actions = tuple(
        action
        for action in relevant_actions
        if action.start_phase == phase.value
        and action.target_policy not in _SUPPORTED_MISSION_ACTION_TARGET_POLICIES
    )
    if unsupported_actions:
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="A held Mission Action uses an unsupported target policy.",
            payload={
                "game_id": state.game_id,
                "player_id": requested_player,
                "mission_action_ids": [action.mission_action_id for action in unsupported_actions],
                "target_policies": [action.target_policy for action in unsupported_actions],
            },
        )
    options = _mission_action_opportunity_options(
        state=state,
        player_id=requested_player,
        relevant_actions=relevant_actions,
    )
    if not options:
        return None
    legal_action_option_id_values = [option.option_id() for option in options]
    legal_action_option_ids = cast(list[JsonValue], legal_action_option_id_values)
    legal_mission_action_ids = cast(
        list[JsonValue],
        sorted({option.action.mission_action_id for option in options}),
    )
    legal_option_ids = cast(
        list[JsonValue],
        sorted((*legal_action_option_id_values, DECLINE_MISSION_ACTION_START_OPTION_ID)),
    )
    opportunity_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "player_id": requested_player,
        "battle_round": state.battle_round,
        "phase": phase.value,
        "mission_action_opportunity": True,
        "legal_mission_action_ids": legal_mission_action_ids,
        "legal_action_option_ids": legal_action_option_ids,
        "legal_option_ids": legal_option_ids,
    }
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=START_MISSION_ACTION_DECISION_TYPE,
        actor_id=requested_player,
        payload=opportunity_payload,
        options=(
            *(
                DecisionOption(
                    option_id=option.option_id(),
                    label=option.label(state=state),
                    payload={
                        **option.payload(
                            state=state,
                            player_id=requested_player,
                            phase=phase,
                        ),
                        "mission_action_opportunity": True,
                        "legal_action_option_ids": legal_action_option_ids,
                    },
                )
                for option in options
            ),
            DecisionOption(
                option_id=DECLINE_MISSION_ACTION_START_OPTION_ID,
                label="Continue to shooting",
                payload={
                    "game_id": state.game_id,
                    "player_id": requested_player,
                    "battle_round": state.battle_round,
                    "phase": phase.value,
                    "mission_action_opportunity": True,
                    "legal_action_option_ids": legal_action_option_ids,
                },
            ),
        ),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "game_id": state.game_id,
            "player_id": requested_player,
            "decision_type": START_MISSION_ACTION_DECISION_TYPE,
            "mission_action_opportunity": True,
            "legal_action_option_count": len(legal_action_option_ids),
        },
    )


def request_tactical_secondary_discard(
    *,
    state: GameState,
    decisions: DecisionController,
    player_id: str,
) -> LifecycleStatus:
    _assert_battle_state(state)
    requested_player = _validate_player_id(state=state, player_id=player_id)
    phase = _current_phase(state)
    active_player_id = _active_player_id(state)
    active_cards = _active_tactical_secondary_cards(state=state, player_id=requested_player)
    if not active_cards:
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="No active Tactical secondary mission cards can be discarded.",
            payload={
                "game_id": state.game_id,
                "player_id": requested_player,
                "decision_type": TACTICAL_SECONDARY_DISCARD_DECISION_TYPE,
            },
        )
    discard_cp_reward_window_id = _tactical_secondary_discard_cp_reward_window_id(
        state=state,
        player_id=requested_player,
    )
    reward_window_used = state.has_tactical_secondary_discard_cp_reward_window(
        discard_cp_reward_window_id
    )
    if requested_player == active_player_id and reward_window_used:
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="Tactical secondary discard CP reward window was already used.",
            payload={
                "game_id": state.game_id,
                "player_id": requested_player,
                "decision_type": TACTICAL_SECONDARY_DISCARD_DECISION_TYPE,
                "discard_cp_reward_window_id": discard_cp_reward_window_id,
            },
        )
    discard_sets = _active_tactical_secondary_discard_sets(active_cards)
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=TACTICAL_SECONDARY_DISCARD_DECISION_TYPE,
        actor_id=requested_player,
        payload={
            "game_id": state.game_id,
            "player_id": requested_player,
            "active_player_id": active_player_id,
            "battle_round": state.battle_round,
            "phase": phase.value,
            "legal_secondary_mission_ids": [card.secondary_mission_id for card in active_cards],
            "legal_secondary_mission_id_sets": [list(card_ids) for card_ids in discard_sets],
            "discard_cp_reward_window_id": discard_cp_reward_window_id,
            "discard_cp_reward_window_used": reward_window_used,
        },
        options=tuple(
            DecisionOption(
                option_id=_tactical_secondary_discard_option_id(card_ids),
                label=f"Discard {', '.join(card_ids)}",
                payload={
                    "game_id": state.game_id,
                    "player_id": requested_player,
                    "active_player_id": active_player_id,
                    "battle_round": state.battle_round,
                    "phase": phase.value,
                    "secondary_mission_ids": list(card_ids),
                    "discard_cp_reward_window_id": discard_cp_reward_window_id,
                },
            )
            for card_ids in discard_sets
        ),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "game_id": state.game_id,
            "player_id": requested_player,
            "decision_type": TACTICAL_SECONDARY_DISCARD_DECISION_TYPE,
        },
    )


def request_tactical_secondary_score(
    *,
    state: GameState,
    decisions: DecisionController,
    achievement_context: TacticalSecondaryAchievementContext,
) -> LifecycleStatus:
    _assert_battle_state(state)
    if type(achievement_context) is not TacticalSecondaryAchievementContext:
        raise GameLifecycleError(
            "Tactical secondary score requires a TacticalSecondaryAchievementContext."
        )
    recorded_context = state.tactical_secondary_achievement_context(
        achievement_context.achievement_id
    )
    requested_player = _validate_player_id(state=state, player_id=achievement_context.player_id)
    requested_secondary_id = achievement_context.secondary_mission_id
    if recorded_context is None or recorded_context != achievement_context:
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="Tactical secondary score requires an engine-owned achievement context.",
            payload={
                "game_id": state.game_id,
                "player_id": requested_player,
                "secondary_mission_id": requested_secondary_id,
                "achievement_id": achievement_context.achievement_id,
                "decision_type": TACTICAL_SECONDARY_SCORE_DECISION_TYPE,
            },
        )
    drift_reason = _tactical_secondary_achievement_context_drift_reason(
        state=state,
        context=recorded_context,
    )
    if drift_reason is not None:
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="Tactical secondary achievement context is no longer current.",
            payload={
                "game_id": state.game_id,
                "player_id": requested_player,
                "secondary_mission_id": requested_secondary_id,
                "achievement_id": achievement_context.achievement_id,
                "decision_type": TACTICAL_SECONDARY_SCORE_DECISION_TYPE,
                "unsupported_reason": drift_reason,
            },
        )
    context = _tactical_secondary_score_context(recorded_context)
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=TACTICAL_SECONDARY_SCORE_DECISION_TYPE,
        actor_id=requested_player,
        payload={
            **context,
            "legal_option_ids": [
                f"score:{requested_secondary_id}",
                f"retain:{requested_secondary_id}",
            ],
        },
        options=(
            DecisionOption(
                option_id=f"score:{requested_secondary_id}",
                label=f"Score {requested_secondary_id}",
                payload={**context, "score": True},
            ),
            DecisionOption(
                option_id=f"retain:{requested_secondary_id}",
                label=f"Retain {requested_secondary_id}",
                payload={**context, "score": False},
            ),
        ),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "game_id": state.game_id,
            "player_id": requested_player,
            "secondary_mission_id": requested_secondary_id,
            "achievement_id": achievement_context.achievement_id,
            "decision_type": TACTICAL_SECONDARY_SCORE_DECISION_TYPE,
        },
    )


def request_mission_action_start(
    *,
    state: GameState,
    decisions: DecisionController,
    player_id: str,
    mission_action_id: str,
) -> LifecycleStatus:
    _assert_battle_state(state)
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
                "active_primary_mission_id": mission_setup.primary_mission_id,
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
    options = _mission_action_start_options(
        state=state,
        player_id=requested_player,
        action=mission_action,
    )
    if not options:
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
            "legal_option_ids": [option.option_id() for option in options],
        },
        options=tuple(
            DecisionOption(
                option_id=option.option_id(),
                label=option.label(state=state),
                payload=option.payload(
                    state=state,
                    player_id=requested_player,
                    phase=phase,
                ),
            )
            for option in options
        ),
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


def invalid_mission_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if request.decision_type == TACTICAL_SECONDARY_SCORE_DECISION_TYPE:
        payload = _payload_object(result.payload)
        player_id = _payload_string(payload, key="player_id")
        secondary_mission_id = _payload_string(payload, key="secondary_mission_id")
        drift_reason = _tactical_secondary_score_drift_reason(
            state=state,
            payload=payload,
            player_id=player_id,
            secondary_mission_id=secondary_mission_id,
            result=result,
        )
        if drift_reason is not None:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Tactical secondary score option drifted.",
                payload={
                    "game_id": state.game_id,
                    "player_id": player_id,
                    "secondary_mission_id": secondary_mission_id,
                    "invalid_reason": drift_reason,
                },
            )
        return None
    if request.decision_type == TACTICAL_SECONDARY_DISCARD_DECISION_TYPE:
        payload = _payload_object(result.payload)
        player_id = _payload_string(payload, key="player_id")
        secondary_mission_ids = _payload_identifier_tuple_from_list(
            payload,
            key="secondary_mission_ids",
        )
        drift_reason = _decision_context_drift_reason(
            state=state,
            payload=payload,
            player_id=player_id,
            result=result,
        )
        if drift_reason is not None:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Tactical secondary discard option drifted.",
                payload={
                    "game_id": state.game_id,
                    "player_id": player_id,
                    "secondary_mission_ids": list(secondary_mission_ids),
                    "invalid_reason": drift_reason,
                },
            )
        discard_cp_reward_window_id = _payload_string(payload, key="discard_cp_reward_window_id")
        if player_id == _active_player_id(state) and (
            discard_cp_reward_window_id
            != _tactical_secondary_discard_cp_reward_window_id(
                state=state,
                player_id=player_id,
            )
        ):
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Tactical secondary discard option drifted.",
                payload={
                    "game_id": state.game_id,
                    "player_id": player_id,
                    "secondary_mission_ids": list(secondary_mission_ids),
                    "invalid_reason": "discard_cp_reward_window_drift",
                },
            )
        if player_id == _active_player_id(
            state
        ) and state.has_tactical_secondary_discard_cp_reward_window(discard_cp_reward_window_id):
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Tactical secondary discard option drifted.",
                payload={
                    "game_id": state.game_id,
                    "player_id": player_id,
                    "secondary_mission_ids": list(secondary_mission_ids),
                    "invalid_reason": "discard_cp_reward_window_used",
                },
            )
        active_ids = {
            card.secondary_mission_id
            for card in _active_tactical_secondary_cards(state=state, player_id=player_id)
        }
        if any(card_id not in active_ids for card_id in secondary_mission_ids):
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Tactical secondary discard option drifted.",
                payload={
                    "game_id": state.game_id,
                    "player_id": player_id,
                    "secondary_mission_ids": list(secondary_mission_ids),
                    "invalid_reason": "card_not_active",
                },
            )
        return None
    if request.decision_type == START_MISSION_ACTION_DECISION_TYPE:
        payload = _payload_object(result.payload)
        player_id = _payload_string(payload, key="player_id")
        drift_reason = _decision_context_drift_reason(
            state=state,
            payload=payload,
            player_id=player_id,
            result=result,
        )
        if drift_reason is not None:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Mission Action start option drifted.",
                payload={
                    "game_id": state.game_id,
                    "player_id": player_id,
                    "invalid_reason": drift_reason,
                },
            )
        opportunity = payload.get("mission_action_opportunity")
        if opportunity is not None and type(opportunity) is not bool:
            raise GameLifecycleError("mission_action_opportunity must be a bool.")
        if opportunity is True:
            opportunity_drift_reason = _mission_action_opportunity_drift_reason(
                state=state,
                payload=payload,
                player_id=player_id,
            )
            if opportunity_drift_reason is not None:
                return LifecycleStatus.invalid(
                    stage=state.stage,
                    message="Mission Action opportunity option drifted.",
                    payload={
                        "game_id": state.game_id,
                        "player_id": player_id,
                        "invalid_reason": opportunity_drift_reason,
                    },
                )
        if result.selected_option_id == DECLINE_MISSION_ACTION_START_OPTION_ID:
            if opportunity is not True:
                return LifecycleStatus.invalid(
                    stage=state.stage,
                    message="Mission Action decline requires an engine-owned opportunity.",
                    payload={
                        "game_id": state.game_id,
                        "player_id": player_id,
                        "invalid_reason": "missing_mission_action_opportunity",
                    },
                )
            return None
        mission_action_id = _payload_string(payload, key="mission_action_id")
        unit_instance_id = _payload_string(payload, key="unit_instance_id")
        target_id = _payload_string(payload, key="target_id")
        try:
            action = _mission_action_for_state(
                state=state,
                mission_action_id=mission_action_id,
            )
            available_action_ids = {
                available_action.mission_action_id
                for available_action in _available_mission_actions_for_state(
                    state=state,
                    player_id=player_id,
                )
            }
            option_ids = {
                option.option_id()
                for option in _mission_action_start_options(
                    state=state,
                    player_id=player_id,
                    action=action,
                )
            }
        except PlacementError as exc:
            raise GameLifecycleError("Mission Action drift validation failed.") from exc
        if action.mission_action_id not in available_action_ids:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Mission Action start option drifted.",
                payload={
                    "game_id": state.game_id,
                    "player_id": player_id,
                    "mission_action_id": mission_action_id,
                    "unit_instance_id": unit_instance_id,
                    "target_id": target_id,
                    "invalid_reason": "mission_action_not_held",
                },
            )
        if f"start:{mission_action_id}:{unit_instance_id}:{target_id}" not in option_ids:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Mission Action start option drifted.",
                payload={
                    "game_id": state.game_id,
                    "player_id": player_id,
                    "mission_action_id": mission_action_id,
                    "unit_instance_id": unit_instance_id,
                    "target_id": target_id,
                },
            )
        return None
    raise GameLifecycleError("Mission decision validator received unsupported decision_type.")


def apply_mission_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    if result.decision_type == TACTICAL_SECONDARY_SCORE_DECISION_TYPE:
        _apply_tactical_secondary_score(state=state, result=result, decisions=decisions)
        return
    if result.decision_type == TACTICAL_SECONDARY_DISCARD_DECISION_TYPE:
        _apply_tactical_secondary_discard(state=state, result=result, decisions=decisions)
        return
    if result.decision_type == START_MISSION_ACTION_DECISION_TYPE:
        if result.selected_option_id == DECLINE_MISSION_ACTION_START_OPTION_ID:
            _apply_mission_action_opportunity_decline(
                state=state,
                result=result,
                decisions=decisions,
            )
            return
        _apply_start_mission_action(state=state, result=result, decisions=decisions)
        return
    raise GameLifecycleError("Mission decision handler received unsupported decision_type.")


def _apply_tactical_secondary_score(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    _assert_battle_state(state)
    payload = _payload_object(result.payload)
    player_id = _payload_string(payload, key="player_id")
    secondary_mission_id = _payload_string(payload, key="secondary_mission_id")
    achievement_id = _payload_string(payload, key="achievement_id")
    drift_reason = _tactical_secondary_score_drift_reason(
        state=state,
        payload=payload,
        player_id=player_id,
        secondary_mission_id=secondary_mission_id,
        result=result,
    )
    if drift_reason is not None:
        raise GameLifecycleError(f"Tactical secondary score option drifted: {drift_reason}.")
    achievement_context = state.tactical_secondary_achievement_context(achievement_id)
    if achievement_context is None:
        raise GameLifecycleError("Tactical secondary achievement context is missing.")
    achievement_payload = validate_json_value(achievement_context.to_payload())
    if _payload_bool(payload, key="score"):
        scored = state.score_secondary_mission(
            player_id=player_id,
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=_current_phase(state),
        )
        if scored.scored_transaction_id is None:
            raise GameLifecycleError("Scored Tactical secondary requires a transaction ID.")
        transaction = _victory_point_transaction_by_id(
            state=state,
            player_id=player_id,
            transaction_id=scored.scored_transaction_id,
        )
        decisions.event_log.append(
            "tactical_secondary_mission_scored",
            {
                "game_id": state.game_id,
                "player_id": player_id,
                "active_player_id": _active_player_id(state),
                "battle_round": state.battle_round,
                "phase": _current_phase(state).value,
                "achievement_context": achievement_payload,
                "secondary_mission_card_state": validate_json_value(scored.to_payload()),
                "victory_point_transaction": validate_json_value(transaction.to_payload()),
                "discarded_after_score": True,
            },
        )
        state.consume_tactical_secondary_achievement_context(achievement_id)
        return
    card_state = state.secondary_mission_card_state(
        player_id=player_id,
        secondary_mission_id=secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    if card_state is None:
        raise GameLifecycleError("Retained Tactical secondary card is not active.")
    decisions.event_log.append(
        "tactical_secondary_mission_score_declined",
        {
            "game_id": state.game_id,
            "player_id": player_id,
            "active_player_id": _active_player_id(state),
            "battle_round": state.battle_round,
            "phase": _current_phase(state).value,
            "achievement_context": achievement_payload,
            "secondary_mission_card_state": validate_json_value(card_state.to_payload()),
            "retained": True,
        },
    )
    state.consume_tactical_secondary_achievement_context(achievement_id)


def _apply_tactical_secondary_discard(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    _assert_battle_state(state)
    payload = _payload_object(result.payload)
    player_id = _payload_string(payload, key="player_id")
    secondary_mission_ids = _payload_identifier_tuple_from_list(
        payload,
        key="secondary_mission_ids",
    )
    _validate_decision_context(state=state, payload=payload, player_id=player_id, result=result)
    discarded = tuple(
        state.discard_tactical_secondary(
            player_id=player_id,
            secondary_mission_id=secondary_mission_id,
            result_id=result.result_id,
        )
        for secondary_mission_id in secondary_mission_ids
    )
    command_point_gain = _apply_tactical_secondary_discard_cp_reward(
        state=state,
        decisions=decisions,
        result=result,
        player_id=player_id,
        discard_cp_reward_window_id=_payload_string(payload, key="discard_cp_reward_window_id"),
    )
    reward_eligible = player_id == _active_player_id(state)
    decisions.event_log.append(
        "tactical_secondary_missions_discarded",
        {
            "game_id": state.game_id,
            "player_id": player_id,
            "active_player_id": _active_player_id(state),
            "battle_round": state.battle_round,
            "phase": _current_phase(state).value,
            "secondary_mission_ids": list(secondary_mission_ids),
            "secondary_mission_card_states": [
                validate_json_value(card.to_payload()) for card in discarded
            ],
            "command_point_reward_eligible": reward_eligible,
            "command_point_reward_reason": (
                "discarding_players_turn" if reward_eligible else "not_discarding_players_turn"
            ),
            "command_point_gain": command_point_gain,
        },
    )


def _apply_start_mission_action(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    _assert_battle_state(state)
    payload = _payload_object(result.payload)
    player_id = _payload_string(payload, key="player_id")
    _validate_decision_context(state=state, payload=payload, player_id=player_id, result=result)
    mission_action = _mission_action_for_state(
        state=state,
        mission_action_id=_payload_string(payload, key="mission_action_id"),
    )
    action_state = MissionActionState.start(
        action_id=f"mission-action:{result.result_id}",
        player_id=player_id,
        unit_instance_id=_payload_string(payload, key="unit_instance_id"),
        target_id=_payload_string(payload, key="target_id"),
        mission_id=mission_action.mission_id,
        battle_round=state.battle_round,
        phase=_current_phase(state).value,
        start_timing=mission_action.start_timing,
        completion_timing=mission_action.completion_timing,
        eligible_unit_instance_ids=tuple(
            _payload_string_list(payload, key="eligible_unit_instance_ids")
        ),
        interruption_conditions=mission_action.interruption_conditions,
        scoring_source_id=mission_action.scoring_source_id,
        victory_points=mission_action.victory_points,
        battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
    )
    if mission_action.completion_timing == "immediate":
        completed_state = action_state.complete_without_award(
            battle_round=state.battle_round,
            phase=_current_phase(state).value,
            completion_timing=mission_action.completion_timing,
            battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
        )
        state.record_mission_action_state(completed_state)
    else:
        completed_state = None
        state.record_mission_action_state(action_state)
    decisions.event_log.append(
        "mission_action_started",
        {
            "game_id": state.game_id,
            "player_id": player_id,
            "battle_round": state.battle_round,
            "phase": _current_phase(state).value,
            "mission_action_id": mission_action.mission_action_id,
            "target_id": _payload_string(payload, key="target_id"),
            "target_policy": mission_action.target_policy,
            "mission_action_state": validate_json_value(action_state.to_payload()),
        },
    )
    if completed_state is None:
        return
    trap_state_payload: JsonValue | None = None
    plunder_state_payload: JsonValue | None = None
    if mission_action.target_policy == "trappable_terrain_area":
        trap_state = state.record_primary_terrain_trap(
            player_id=player_id,
            terrain_feature_id=completed_state.target_id,
            action_id=completed_state.action_id,
            phase=_current_phase(state),
            source_id=mission_action.source_id,
        )
        trap_state_payload = validate_json_value(trap_state.to_payload())
        decisions.event_log.append(
            "primary_terrain_area_trapped",
            {
                "game_id": state.game_id,
                "player_id": player_id,
                "battle_round": state.battle_round,
                "phase": _current_phase(state).value,
                "mission_action_id": mission_action.mission_action_id,
                "terrain_feature_id": trap_state.terrain_feature_id,
                "primary_terrain_trap_state": trap_state_payload,
            },
        )
    if mission_action.target_policy == "plunderable_terrain_area":
        plunder_state = state.record_secondary_terrain_plunder(
            player_id=player_id,
            terrain_feature_id=completed_state.target_id,
            action_id=completed_state.action_id,
            phase=_current_phase(state),
            source_id=mission_action.source_id,
        )
        plunder_state_payload = validate_json_value(plunder_state.to_payload())
        decisions.event_log.append(
            "secondary_terrain_area_plundered",
            {
                "game_id": state.game_id,
                "player_id": player_id,
                "battle_round": state.battle_round,
                "phase": _current_phase(state).value,
                "mission_action_id": mission_action.mission_action_id,
                "terrain_feature_id": plunder_state.terrain_feature_id,
                "secondary_terrain_plunder_state": plunder_state_payload,
            },
        )
    decisions.event_log.append(
        "mission_action_completed",
        {
            "game_id": state.game_id,
            "player_id": player_id,
            "battle_round": state.battle_round,
            "phase": _current_phase(state).value,
            "mission_action_id": mission_action.mission_action_id,
            "target_id": completed_state.target_id,
            "target_policy": mission_action.target_policy,
            "mission_action_state": validate_json_value(completed_state.to_payload()),
            "primary_terrain_trap_state": trap_state_payload,
            "secondary_terrain_plunder_state": plunder_state_payload,
        },
    )


def _apply_mission_action_opportunity_decline(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    _assert_battle_state(state)
    payload = _payload_object(result.payload)
    player_id = _payload_string(payload, key="player_id")
    _validate_decision_context(state=state, payload=payload, player_id=player_id, result=result)
    if not _payload_bool(payload, key="mission_action_opportunity"):
        raise GameLifecycleError("Mission Action decline requires an opportunity payload.")
    drift_reason = _mission_action_opportunity_drift_reason(
        state=state,
        payload=payload,
        player_id=player_id,
    )
    if drift_reason is not None:
        raise GameLifecycleError(f"Mission Action opportunity drifted: {drift_reason}.")
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        raise GameLifecycleError("Mission Action decline requires ShootingPhaseState.")
    state.replace_shooting_phase_state(shooting_state.with_mission_action_opportunity_declined())
    decisions.event_log.append(
        "mission_action_opportunity_declined",
        {
            "game_id": state.game_id,
            "player_id": player_id,
            "battle_round": state.battle_round,
            "phase": _current_phase(state).value,
            "request_id": result.request_id,
            "result_id": result.result_id,
        },
    )


def _active_tactical_secondary_cards(
    *,
    state: GameState,
    player_id: str,
) -> tuple[SecondaryMissionCardState, ...]:
    return tuple(
        sorted(
            (
                card
                for card in state.secondary_mission_card_states
                if card.player_id == player_id
                and card.mode is SecondaryMissionCardMode.TACTICAL
                and card.status is SecondaryMissionCardStatus.ACTIVE
            ),
            key=lambda card: card.secondary_mission_id,
        )
    )


def _active_tactical_secondary_discard_sets(
    active_cards: tuple[SecondaryMissionCardState, ...],
) -> tuple[tuple[str, ...], ...]:
    card_ids = tuple(card.secondary_mission_id for card in active_cards)
    return tuple(
        card_set
        for set_size in range(1, len(card_ids) + 1)
        for card_set in combinations(card_ids, set_size)
    )


def _tactical_secondary_discard_option_id(card_ids: tuple[str, ...]) -> str:
    _validate_identifier_tuple(
        "card_ids",
        card_ids,
        min_length=1,
        sort_values=False,
    )
    return f"discard:{'+'.join(card_ids)}"


def _validate_decision_context(
    *,
    state: GameState,
    payload: dict[str, JsonValue],
    player_id: str,
    result: DecisionResult,
) -> None:
    drift_reason = _decision_context_drift_reason(
        state=state,
        payload=payload,
        player_id=player_id,
        result=result,
    )
    if drift_reason is not None:
        raise GameLifecycleError(f"Mission decision context drift: {drift_reason}.")


def _decision_context_drift_reason(
    *,
    state: GameState,
    payload: dict[str, JsonValue],
    player_id: str,
    result: DecisionResult,
) -> str | None:
    if result.actor_id != player_id:
        return "actor_player_drift"
    if _payload_string(payload, key="game_id") != state.game_id:
        return "game_id_drift"
    if _payload_int(payload, key="battle_round") != state.battle_round:
        return "battle_round_drift"
    if _payload_string(payload, key="phase") != _current_phase(state).value:
        return "phase_drift"
    active_player_payload = payload.get("active_player_id")
    if active_player_payload is not None and (
        _validate_identifier("active_player_id", active_player_payload) != _active_player_id(state)
    ):
        return "active_player_id_drift"
    return None


def _tactical_secondary_score_context(
    context: TacticalSecondaryAchievementContext,
) -> dict[str, JsonValue]:
    if type(context) is not TacticalSecondaryAchievementContext:
        raise GameLifecycleError("Tactical secondary score requires an achievement context.")
    return cast(dict[str, JsonValue], context.to_payload())


def _tactical_secondary_achievement_context_drift_reason(
    *,
    state: GameState,
    context: TacticalSecondaryAchievementContext,
) -> str | None:
    if context.game_id != state.game_id:
        return "game_id_drift"
    if context.player_id not in state.player_ids:
        return "player_id_drift"
    if context.active_player_id != _active_player_id(state):
        return "active_player_id_drift"
    if context.battle_round != state.battle_round:
        return "battle_round_drift"
    if context.phase != _current_phase(state).value:
        return "phase_drift"
    if context.mode is not SecondaryMissionCardMode.TACTICAL:
        return "mode_drift"
    card_state = state.secondary_mission_card_state(
        player_id=context.player_id,
        secondary_mission_id=context.secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    if card_state is None:
        return "card_not_active"
    if context.card_battle_round != card_state.battle_round:
        return "card_battle_round_drift"
    if state.mission_setup is None:
        raise GameLifecycleError("Tactical secondary achievement context requires MissionSetup.")
    policy = mission_scoring_policy_from_setup(state.mission_setup)
    award = policy.secondary_award(
        player_id=context.player_id,
        battle_round=state.battle_round,
        phase=_current_phase(state).value,
        secondary_mission_id=context.secondary_mission_id,
        source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
        hidden=False,
    )
    metadata = _payload_object(award.metadata)
    if context.victory_points != award.amount:
        return "victory_points_drift"
    if context.scoring_rule_id != _payload_string(metadata, key="scoring_rule_id"):
        return "scoring_rule_id_drift"
    if context.scoring_rule_condition != _payload_string(metadata, key="scoring_rule_condition"):
        return "scoring_rule_condition_drift"
    if context.scoring_rule_source_id != _payload_string(metadata, key="scoring_rule_source_id"):
        return "scoring_rule_source_id_drift"
    if context.scoring_timing != award.scoring_timing:
        return "scoring_timing_drift"
    return None


def _tactical_secondary_score_drift_reason(
    *,
    state: GameState,
    payload: dict[str, JsonValue],
    player_id: str,
    secondary_mission_id: str,
    result: DecisionResult,
) -> str | None:
    drift_reason = _decision_context_drift_reason(
        state=state,
        payload=payload,
        player_id=player_id,
        result=result,
    )
    if drift_reason is not None:
        return drift_reason
    if _payload_string(payload, key="mode") != SecondaryMissionCardMode.TACTICAL.value:
        return "mode_drift"
    achievement_id = _payload_string(payload, key="achievement_id")
    recorded_context = state.tactical_secondary_achievement_context(achievement_id)
    if recorded_context is None:
        return "achievement_context_missing"
    recorded_payload = _tactical_secondary_score_context(recorded_context)
    for key, expected_value in recorded_payload.items():
        if payload[key] != expected_value:
            return f"{key}_drift"
    context_drift_reason = _tactical_secondary_achievement_context_drift_reason(
        state=state,
        context=recorded_context,
    )
    if context_drift_reason is not None:
        return context_drift_reason
    card_state = state.secondary_mission_card_state(
        player_id=player_id,
        secondary_mission_id=secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    if card_state is None:
        return "card_not_active"
    if _payload_int(payload, key="card_battle_round") != card_state.battle_round:
        return "card_battle_round_drift"
    return None


def _victory_point_transaction_by_id(
    *,
    state: GameState,
    player_id: str,
    transaction_id: str,
) -> VictoryPointTransaction:
    requested_transaction_id = _validate_identifier("transaction_id", transaction_id)
    ledger = state.victory_point_ledger_for_player(player_id)
    for transaction in ledger.transactions:
        if transaction.transaction_id == requested_transaction_id:
            return transaction
    raise GameLifecycleError("Victory point transaction was not found.")


def _apply_tactical_secondary_discard_cp_reward(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    player_id: str,
    discard_cp_reward_window_id: str,
) -> JsonValue | None:
    if player_id != _active_player_id(state):
        return None
    expected_window_id = _tactical_secondary_discard_cp_reward_window_id(
        state=state,
        player_id=player_id,
    )
    requested_window_id = _validate_identifier(
        "discard_cp_reward_window_id",
        discard_cp_reward_window_id,
    )
    if requested_window_id != expected_window_id:
        raise GameLifecycleError("Tactical secondary discard CP reward window drift.")
    if state.has_tactical_secondary_discard_cp_reward_window(requested_window_id):
        raise GameLifecycleError("Tactical secondary discard CP reward window already used.")
    state.record_tactical_secondary_discard_cp_reward_window(requested_window_id)
    gain = state.gain_command_points(
        player_id=player_id,
        amount=1,
        source_id=f"{_tactical_secondary_procedure_source_id(state)}:discard:"
        f"{result.result_id}:cp-reward",
        source_kind=CommandPointSourceKind.OTHER,
    )
    gain_payload = validate_json_value(gain.to_payload())
    decisions.event_log.append(
        "command_points_gained"
        if gain.status is CommandPointGainStatus.APPLIED
        else "command_points_gain_capped",
        gain_payload,
    )
    return gain_payload


def _tactical_secondary_procedure_source_id(state: GameState) -> str:
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise GameLifecycleError("Tactical secondary procedure requires MissionSetup.")
    return f"{mission_setup.source_id}:secondary:tactical-procedure"


def _tactical_secondary_discard_cp_reward_window_id(
    *,
    state: GameState,
    player_id: str,
) -> str:
    requested_player = _validate_player_id(state=state, player_id=player_id)
    return (
        f"tactical-secondary-discard-cp:{state.game_id}:round-{state.battle_round:02d}:"
        f"{_active_player_id(state)}:{_current_phase(state).value}:{requested_player}"
    )


def _assert_battle_state(state: GameState) -> None:
    if type(state) is not GameState:
        raise GameLifecycleError("Mission decision requires GameState.")
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Mission decision can be applied only during battle.")


def _current_phase(state: GameState) -> BattlePhase:
    phase = state.current_battle_phase
    if phase is None:
        raise GameLifecycleError("Mission decision requires a battle phase.")
    return phase


def _active_player_id(state: GameState) -> str:
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Mission decision requires an active player.")
    return active_player_id


def _validate_player_id(*, state: GameState, player_id: str) -> str:
    requested_player = _validate_identifier("player_id", player_id)
    if requested_player not in state.player_ids:
        raise GameLifecycleError("Mission decision player_id is not in this game.")
    return requested_player


def _validate_active_player_id(*, state: GameState, player_id: str) -> str:
    requested_player = _validate_player_id(state=state, player_id=player_id)
    if state.active_player_id != requested_player:
        raise GameLifecycleError("Mission decision player_id must be the active player.")
    return requested_player


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Mission decision payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload[key]
    return _validate_identifier(key, value)


def _payload_string_list(payload: dict[str, JsonValue], *, key: str) -> list[str]:
    value = payload[key]
    if not isinstance(value, list):
        raise GameLifecycleError(f"Mission decision payload key must be a list: {key}.")
    return [_validate_identifier(f"{key} value", item) for item in cast(list[object], value)]


def _payload_identifier_tuple_from_list(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> tuple[str, ...]:
    return _validate_identifier_tuple(
        key,
        tuple(_payload_string_list(payload, key=key)),
        min_length=1,
        sort_values=True,
    )


def _payload_int(payload: dict[str, JsonValue], *, key: str) -> int:
    value = payload[key]
    if type(value) is not int:
        raise GameLifecycleError(f"Mission decision payload key must be an integer: {key}.")
    return value


def _payload_bool(payload: dict[str, JsonValue], *, key: str) -> bool:
    value = payload[key]
    if type(value) is not bool:
        raise GameLifecycleError(f"Mission decision payload key must be a bool: {key}.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
    sort_values: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    if len(identifiers) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    if sort_values:
        return tuple(sorted(identifiers))
    return tuple(identifiers)
