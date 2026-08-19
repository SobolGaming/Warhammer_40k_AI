from __future__ import annotations

from itertools import combinations
from typing import TYPE_CHECKING, cast

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
from warhammer40k_core.engine.mission_action_options import (
    primary_mission_action_start_evidence_for_selection as _primary_start_evidence,
)
from warhammer40k_core.engine.mission_action_policies import (
    mission_action_policy_descriptors,
    mission_action_policy_for_id,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.primary_mission_action_decline_integrity import (
    apply_mission_action_opportunity_decline_mutation,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
    PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY,
    PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_policy import (
    capture_primary_mission_action_completion_evidence,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint import (
    primary_mission_boundary_checkpoint_for_request,
    record_primary_mission_boundary_checkpoint,
    validate_primary_mission_action_request_checkpoint,
    validate_primary_mission_boundary_checkpoint_modifier_sources,
)
from warhammer40k_core.engine.primary_mission_choices import (
    SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
    apply_primary_mission_choice,
    invalid_primary_mission_choice_request_status,
)
from warhammer40k_core.engine.rules_units import rules_unit_is_battle_shocked
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    TacticalSecondaryAchievementContext,
)
from warhammer40k_core.engine.secondary_mission_choices import (
    SECONDARY_CHOICE_DECISION_TYPES,
    apply_secondary_mission_choice,
    invalid_secondary_mission_choice_status,
)
from warhammer40k_core.engine.secondary_when_drawn import (
    RESOLVE_TACTICAL_SECONDARY_WHEN_DRAWN_DECISION_TYPE,
    apply_tactical_secondary_when_drawn,
    invalid_tactical_secondary_when_drawn_status,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
    from warhammer40k_core.engine.faction_rule_execution import FactionRuleExecutionRegistry
    from warhammer40k_core.engine.runtime_rule_ir_authority import RuntimeRuleIRAuthorityIndex

TACTICAL_SECONDARY_SCORE_DECISION_TYPE = "score_tactical_secondary_mission"
TACTICAL_SECONDARY_DISCARD_DECISION_TYPE = "discard_tactical_secondary_mission"
START_MISSION_ACTION_DECISION_TYPE = "start_mission_action"
DECLINE_MISSION_ACTION_START_OPTION_ID = "continue_to_shooting"
MISSION_DECISION_TYPES = frozenset(
    (
        TACTICAL_SECONDARY_SCORE_DECISION_TYPE,
        TACTICAL_SECONDARY_DISCARD_DECISION_TYPE,
        START_MISSION_ACTION_DECISION_TYPE,
        SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
        RESOLVE_TACTICAL_SECONDARY_WHEN_DRAWN_DECISION_TYPE,
        *SECONDARY_CHOICE_DECISION_TYPES,
    )
)
_PRIMARY_MISSION_ACTION_IDS = frozenset(
    descriptor.mission_action_id for descriptor in mission_action_policy_descriptors()
)


def mission_decision_pauses_after_apply(request: DecisionRequest) -> bool:
    if request.decision_type == SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE:
        return True
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
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    _assert_battle_state(state)
    _require_runtime_modifier_registry(runtime_modifier_registry)
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
        runtime_modifier_registry=runtime_modifier_registry,
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
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus:
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
    options = _mission_action_start_options(
        state=state,
        player_id=requested_player,
        action=mission_action,
        runtime_modifier_registry=runtime_modifier_registry,
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


def invalid_mission_decision_status(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    _require_runtime_modifier_registry(runtime_modifier_registry)
    if request.decision_type == SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE:
        return invalid_primary_mission_choice_request_status(
            state=state,
            decisions=decisions,
            request=request,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    if request.decision_type == RESOLVE_TACTICAL_SECONDARY_WHEN_DRAWN_DECISION_TYPE:
        return invalid_tactical_secondary_when_drawn_status(state=state, result=result)
    if request.decision_type in SECONDARY_CHOICE_DECISION_TYPES:
        return invalid_secondary_mission_choice_status(state=state, result=result)
    if request.decision_type == TACTICAL_SECONDARY_SCORE_DECISION_TYPE:
        payload = _payload_object(result.payload)
        player_id = _payload_string(payload, key="player_id")
        secondary_mission_id = _payload_string(payload, key="secondary_mission_id")
        drift_reason = tactical_secondary_score_drift_reason(
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
                runtime_modifier_registry=runtime_modifier_registry,
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
                    runtime_modifier_registry=runtime_modifier_registry,
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
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    runtime_modifier_registry: RuntimeModifierRegistry,
    rule_ir_authority_index: RuntimeRuleIRAuthorityIndex | None = None,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None = None,
    runtime_content_activation: RuntimeContentActivation | None = None,
) -> None:
    _require_runtime_modifier_registry(runtime_modifier_registry)
    if result.decision_type == SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE:
        if not apply_primary_mission_choice(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            runtime_modifier_registry=runtime_modifier_registry,
        ):
            raise GameLifecycleError("Primary mission choice was not handled.")
        return
    if result.decision_type == RESOLVE_TACTICAL_SECONDARY_WHEN_DRAWN_DECISION_TYPE:
        apply_tactical_secondary_when_drawn(state=state, result=result, decisions=decisions)
        return
    if result.decision_type in SECONDARY_CHOICE_DECISION_TYPES:
        apply_secondary_mission_choice(state=state, result=result, decisions=decisions)
        return
    if result.decision_type == TACTICAL_SECONDARY_SCORE_DECISION_TYPE:
        from warhammer40k_core.engine.secondary_tactical_achievement import (
            apply_tactical_secondary_score_result,
        )

        apply_tactical_secondary_score_result(state=state, result=result, decisions=decisions)
        return
    if result.decision_type == TACTICAL_SECONDARY_DISCARD_DECISION_TYPE:
        _apply_tactical_secondary_discard(state=state, result=result, decisions=decisions)
        return
    if result.decision_type == START_MISSION_ACTION_DECISION_TYPE:
        if result.selected_option_id == DECLINE_MISSION_ACTION_START_OPTION_ID:
            apply_mission_action_opportunity_decline_mutation(
                state=state,
                request=request,
                result=result,
                decisions=decisions,
                runtime_modifier_registry=runtime_modifier_registry,
                rule_ir_authority_index=rule_ir_authority_index,
                faction_rule_execution_registry=faction_rule_execution_registry,
                runtime_content_activation=runtime_content_activation,
            )
            return
        _apply_start_mission_action(
            state=state,
            result=result,
            decisions=decisions,
            runtime_modifier_registry=runtime_modifier_registry,
            rule_ir_authority_index=rule_ir_authority_index,
            faction_rule_execution_registry=faction_rule_execution_registry,
            runtime_content_activation=runtime_content_activation,
        )
        return
    raise GameLifecycleError("Mission decision handler received unsupported decision_type.")


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
    runtime_modifier_registry: RuntimeModifierRegistry,
    rule_ir_authority_index: RuntimeRuleIRAuthorityIndex | None,
    faction_rule_execution_registry: FactionRuleExecutionRegistry | None,
    runtime_content_activation: RuntimeContentActivation | None,
) -> None:
    _assert_battle_state(state)
    _require_runtime_modifier_registry(runtime_modifier_registry)
    payload = _payload_object(result.payload)
    player_id = _payload_string(payload, key="player_id")
    _validate_decision_context(state=state, payload=payload, player_id=player_id, result=result)
    mission_action = _mission_action_for_state(
        state=state,
        mission_action_id=_payload_string(payload, key="mission_action_id"),
    )
    unit_instance_id = _payload_string(payload, key="unit_instance_id")
    if rules_unit_is_battle_shocked(
        state=state,
        unit_instance_id=unit_instance_id,
    ):
        raise GameLifecycleError("Battle-shocked units cannot start actions.")
    target_id = _payload_string(payload, key="target_id")
    condition_target_id = _payload_optional_string(payload, key="condition_target_id")
    primary_policy = (
        mission_action_policy_for_id(mission_action.mission_action_id)
        if mission_action.mission_action_id in _PRIMARY_MISSION_ACTION_IDS
        else None
    )
    if primary_policy is None:
        start_evidence = None
    else:
        boundary_checkpoint, _checkpoint, _checkpoint_index = (
            primary_mission_boundary_checkpoint_for_request(
                event_records=decisions.event_log.records,
                request_id=result.request_id,
            )
        )
        validate_primary_mission_action_request_checkpoint(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            request_id=result.request_id,
            reference=boundary_checkpoint,
            player_id=player_id,
            battle_round=state.battle_round,
            phase=_current_phase(state).value,
            rule_ir_authority_index=rule_ir_authority_index,
            faction_rule_execution_registry=faction_rule_execution_registry,
            runtime_content_activation=runtime_content_activation,
        )
        validate_primary_mission_boundary_checkpoint_modifier_sources(
            state=state,
            checkpoint=_checkpoint,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        start_evidence = _primary_start_evidence(
            state=state,
            player_id=player_id,
            action=mission_action,
            unit_instance_id=unit_instance_id,
            target_id=target_id,
            condition_target_id=condition_target_id,
            opportunity=payload.get("mission_action_opportunity") is True,
            decline_option_id=DECLINE_MISSION_ACTION_START_OPTION_ID,
            boundary_checkpoint=boundary_checkpoint,
            boundary_checkpoint_evidence=_checkpoint,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    eligible_unit_instance_ids = (
        tuple(_payload_string_list(payload, key="eligible_unit_instance_ids"))
        if start_evidence is None
        else start_evidence.eligible_unit_instance_ids
    )
    action_state = MissionActionState.start(
        action_id=f"mission-action:{result.result_id}",
        mission_action_id=mission_action.mission_action_id,
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        target_id=target_id,
        condition_target_id=condition_target_id,
        mission_id=mission_action.mission_id,
        battle_round=state.battle_round,
        phase=_current_phase(state).value,
        start_timing=mission_action.start_timing,
        completion_timing=mission_action.completion_timing,
        eligible_unit_instance_ids=eligible_unit_instance_ids,
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
    start_event_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "player_id": player_id,
        "battle_round": state.battle_round,
        "phase": _current_phase(state).value,
        "mission_action_id": mission_action.mission_action_id,
        "target_id": target_id,
        "condition_target_id": condition_target_id,
        "target_policy": mission_action.target_policy,
        "mission_action_state": validate_json_value(action_state.to_payload()),
    }
    if start_evidence is not None:
        start_event_payload[PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY] = start_evidence.to_payload()
    decisions.event_log.append("mission_action_started", start_event_payload)
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
    completion_event_payload: dict[str, JsonValue] = {
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
    }
    if primary_policy is not None:
        completion_evidence = capture_primary_mission_action_completion_evidence(
            state=state,
            action=completed_state,
            policy=primary_policy,
            completed_phase=_current_phase(state),
            objective_control_record=None,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        completion_event_payload[PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY] = (
            completion_evidence.to_payload()
        )
    decisions.event_log.append("mission_action_completed", completion_event_payload)


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
    from warhammer40k_core.engine.secondary_tactical_achievement import (
        expected_tactical_secondary_award_from_state,
    )

    expected = expected_tactical_secondary_award_from_state(state=state, card_state=card_state)
    if expected is None:
        return "award_missing"
    metadata = _payload_object(expected.metadata)
    rule_ids = metadata.get("scoring_rule_ids")
    conditions = metadata.get("scoring_rule_conditions")
    source_ids = metadata.get("scoring_rule_source_ids")
    if not isinstance(rule_ids, list) or not rule_ids:
        return "scoring_rule_id_drift"
    if not isinstance(conditions, list) or not conditions:
        return "scoring_rule_condition_drift"
    if not isinstance(source_ids, list) or not source_ids:
        return "scoring_rule_source_id_drift"
    if context.victory_points != expected.amount:
        return "victory_points_drift"
    if context.scoring_rule_id != rule_ids[0]:
        return "scoring_rule_id_drift"
    if context.scoring_rule_condition != conditions[0]:
        return "scoring_rule_condition_drift"
    if context.scoring_rule_source_id != source_ids[0]:
        return "scoring_rule_source_id_drift"
    if context.scoring_timing != expected.scoring_timing:
        return "scoring_timing_drift"
    return None


def tactical_secondary_score_drift_reason(
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


def _payload_optional_string(payload: dict[str, JsonValue], *, key: str) -> str | None:
    value = payload[key]
    if value is None:
        return None
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


def _require_runtime_modifier_registry(registry: object) -> None:
    if type(registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Mission decisions require a RuntimeModifierRegistry.")


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
