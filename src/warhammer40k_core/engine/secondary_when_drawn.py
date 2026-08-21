from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.rules_units import placed_alive_rules_unit_views
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
)
from warhammer40k_core.engine.secondary_mission_selection import SecondaryMissionSelection
from warhammer40k_core.engine.secondary_scoring_context import secondary_mission_selection_for_card

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

RESOLVE_TACTICAL_SECONDARY_WHEN_DRAWN_DECISION_TYPE = "resolve_tactical_secondary_when_drawn"
_validate_identifier = IdentifierValidator(GameLifecycleError)
_OPTIONAL_DISCARD_CONDITIONS = frozenset(
    {
        "may_discard_if_no_enemy_units_starting_strength_13_or_more_on_battlefield",
        "may_discard_if_no_enemy_models_w10_or_more_on_battlefield",
    }
)
_OPTIONAL_FIRST_ROUND_SHUFFLE_CONDITIONS = frozenset(
    {"first_battle_round_may_shuffle_card_back_and_draw_one"}
)
_MANDATORY_FIRST_ROUND_SHUFFLE_CONDITIONS = frozenset(
    {"first_battle_round_must_shuffle_card_back_and_draw_one"}
)
_OPTIONAL_SHUFFLE_IF_PLUNDER_CONDITIONS = frozenset({"may_shuffle_back_if_plunder_active"})
_OPTIONAL_SHUFFLE_IF_CLEANSE_CONDITIONS = frozenset({"may_shuffle_back_if_cleanse_active"})
_WHEN_DRAWN_ACTION_TIMINGS = frozenset({"when_drawn", "when_drawn_or_start_of_your_turn"})


@dataclass(frozen=True, slots=True)
class _WhenDrawnPolicy:
    action: str
    eligible: bool
    mandatory: bool


def next_tactical_secondary_when_drawn_request(
    *,
    state: GameState,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.game_state import GameState as _GameState

    if type(state) is not _GameState:
        raise GameLifecycleError("When Drawn resolution requires GameState.")
    if state.stage is not GameLifecycleStage.BATTLE:
        return None
    if state.current_battle_phase is not BattlePhase.COMMAND:
        return None
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("When Drawn resolution requires an active player.")
    for _step in range(64):
        pending = _pending_when_drawn_card(state=state, player_id=active_player_id)
        if pending is None:
            return None
        if _auto_apply_when_drawn(state=state, card=pending, decisions=decisions):
            continue
        policy = _when_drawn_policy(state=state, card=pending)
        if policy is None:
            raise GameLifecycleError("When Drawn pending card is missing a source policy.")
        request = _when_drawn_request(state=state, card=pending, action=policy.action)
        decisions.request_decision(request)
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=request,
            payload={
                "game_id": state.game_id,
                "player_id": active_player_id,
                "secondary_mission_id": pending.secondary_mission_id,
                "decision_type": RESOLVE_TACTICAL_SECONDARY_WHEN_DRAWN_DECISION_TYPE,
            },
        )
    raise GameLifecycleError("When Drawn resolution did not terminate.")


def invalid_tactical_secondary_when_drawn_status(
    *,
    state: GameState,
    result: DecisionResult,
) -> LifecycleStatus | None:
    payload = _payload_object(result.payload)
    player_id = _payload_string(payload, "player_id")
    secondary_mission_id = _payload_string(payload, "secondary_mission_id")
    if result.actor_id != player_id or player_id != state.active_player_id:
        return _invalid(state, player_id, secondary_mission_id, "actor_player_drift")
    if _payload_string(payload, "game_id") != state.game_id:
        return _invalid(state, player_id, secondary_mission_id, "game_id_drift")
    if _payload_int(payload, "battle_round") != state.battle_round:
        return _invalid(state, player_id, secondary_mission_id, "battle_round_drift")
    card = state.secondary_mission_card_state(
        player_id=player_id,
        secondary_mission_id=secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    if card is None:
        return _invalid(state, player_id, secondary_mission_id, "card_not_active")
    selection = secondary_mission_selection_for_card(card)
    if selection is not None and selection.when_drawn_resolved:
        return _invalid(state, player_id, secondary_mission_id, "when_drawn_already_resolved")
    return None


def apply_tactical_secondary_when_drawn(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    payload = _payload_object(result.payload)
    player_id = _payload_string(payload, "player_id")
    secondary_mission_id = _payload_string(payload, "secondary_mission_id")
    action = _payload_string(payload, "action")
    card = state.secondary_mission_card_state(
        player_id=player_id,
        secondary_mission_id=secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    if card is None:
        raise GameLifecycleError("When Drawn apply requires an active card.")
    if action == "keep":
        _mark_when_drawn_resolved(state=state, card=card)
        decisions.event_log.append(
            "tactical_secondary_when_drawn_kept",
            _event_payload(state=state, card=card, result=result, action="keep"),
        )
        return
    if action == "discard":
        discarded = state.discard_tactical_secondary(
            player_id=player_id,
            secondary_mission_id=secondary_mission_id,
            result_id=result.result_id,
        )
        drawn = state.draw_tactical_secondary_cards(
            player_id=player_id,
            source_result_id=result.result_id,
            draw_count=1,
        )
        decisions.event_log.append(
            "tactical_secondary_when_drawn_discarded",
            {
                **_event_payload(state=state, card=discarded, result=result, action="discard"),
                "drawn_secondary_mission_card_states": [
                    validate_json_value(drawn_card.to_payload()) for drawn_card in drawn
                ],
            },
        )
        return
    if action == "shuffle":
        drawn = _draw_replacement_then_forget(
            state=state,
            card=card,
            source_result_id=result.result_id,
        )
        decisions.event_log.append(
            "tactical_secondary_when_drawn_shuffled",
            {
                **_event_payload(state=state, card=card, result=result, action="shuffle"),
                "drawn_secondary_mission_card_states": [
                    validate_json_value(drawn_card.to_payload()) for drawn_card in drawn
                ],
            },
        )
        return
    raise GameLifecycleError("When Drawn action is unsupported.")


def _pending_when_drawn_card(
    *,
    state: GameState,
    player_id: str,
) -> SecondaryMissionCardState | None:
    matches = tuple(
        card
        for card in state.secondary_mission_card_states
        if card.player_id == player_id
        and card.mode is SecondaryMissionCardMode.TACTICAL
        and card.status is SecondaryMissionCardStatus.ACTIVE
        and not _when_drawn_resolved(card)
        and _when_drawn_policy(state=state, card=card) is not None
    )
    if not matches:
        return None
    return sorted(matches, key=lambda card: card.secondary_mission_id)[0]


def _when_drawn_policy(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
) -> _WhenDrawnPolicy | None:
    conditions = _when_drawn_source_conditions(
        state=state,
        secondary_mission_id=card.secondary_mission_id,
    )
    action_conditions = tuple(condition for condition in conditions if _action_condition(condition))
    if not action_conditions:
        return None
    if len(action_conditions) != 1:
        raise GameLifecycleError("Secondary When Drawn source describes multiple actions.")
    condition = action_conditions[0]
    if condition in _OPTIONAL_DISCARD_CONDITIONS:
        return _WhenDrawnPolicy(
            action="discard",
            eligible=_discard_is_eligible(state=state, card=card, condition=condition),
            mandatory=False,
        )
    if condition in _OPTIONAL_FIRST_ROUND_SHUFFLE_CONDITIONS:
        return _WhenDrawnPolicy(
            action="shuffle",
            eligible=state.battle_round == 1,
            mandatory=False,
        )
    if condition in _MANDATORY_FIRST_ROUND_SHUFFLE_CONDITIONS:
        return _WhenDrawnPolicy(
            action="shuffle",
            eligible=state.battle_round == 1,
            mandatory=True,
        )
    if condition in _OPTIONAL_SHUFFLE_IF_PLUNDER_CONDITIONS:
        return _WhenDrawnPolicy(
            action="shuffle",
            eligible=_player_has_active_tactical(
                state,
                player_id=card.player_id,
                secondary_mission_id="plunder",
            ),
            mandatory=False,
        )
    if condition in _OPTIONAL_SHUFFLE_IF_CLEANSE_CONDITIONS:
        return _WhenDrawnPolicy(
            action="shuffle",
            eligible=_player_has_active_tactical(
                state,
                player_id=card.player_id,
                secondary_mission_id="cleanse",
            ),
            mandatory=False,
        )
    raise GameLifecycleError("Unsupported When Drawn source condition.")


def _action_condition(condition: str) -> bool:
    return condition in (
        _OPTIONAL_DISCARD_CONDITIONS
        | _OPTIONAL_FIRST_ROUND_SHUFFLE_CONDITIONS
        | _MANDATORY_FIRST_ROUND_SHUFFLE_CONDITIONS
        | _OPTIONAL_SHUFFLE_IF_PLUNDER_CONDITIONS
        | _OPTIONAL_SHUFFLE_IF_CLEANSE_CONDITIONS
    )


def _when_drawn_source_conditions(
    *,
    state: GameState,
    secondary_mission_id: str,
) -> tuple[str, ...]:
    from warhammer40k_core.engine.missions import mission_pack_for_id

    if state.mission_setup is None:
        raise GameLifecycleError("When Drawn resolution requires MissionSetup.")
    mission_pack = mission_pack_for_id(state.mission_setup.mission_pack_id)
    matches = tuple(
        mission
        for mission in mission_pack.secondary_missions
        if mission.secondary_mission_id == secondary_mission_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("When Drawn source mission is missing.")
    return tuple(
        rule.condition
        for rule in matches[0].scoring_rules
        if rule.timing in _WHEN_DRAWN_ACTION_TIMINGS
    )


def _auto_apply_when_drawn(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    decisions: DecisionController,
) -> bool:
    policy = _when_drawn_policy(state=state, card=card)
    if policy is None:
        _mark_when_drawn_resolved(state=state, card=card)
        return True
    if not policy.eligible:
        _mark_when_drawn_resolved(state=state, card=card)
        return True
    if not policy.mandatory:
        return False
    _apply_mandatory_shuffle(state=state, card=card, decisions=decisions)
    return True


def _apply_mandatory_shuffle(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    decisions: DecisionController,
) -> None:
    source_id = (
        f"when-drawn-mandatory:{state.game_id}:{card.player_id}:"
        f"{card.secondary_mission_id}:round-{state.battle_round:02d}"
    )
    drawn = _draw_replacement_then_forget(
        state=state,
        card=card,
        source_result_id=source_id,
    )
    decisions.event_log.append(
        "tactical_secondary_when_drawn_shuffled",
        {
            "game_id": state.game_id,
            "player_id": card.player_id,
            "active_player_id": card.player_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "secondary_mission_id": card.secondary_mission_id,
            "action": "shuffle",
            "result_id": source_id,
            "mandatory": True,
            "hidden": True,
            "secondary_mission_card_state": validate_json_value(card.to_payload()),
            "drawn_secondary_mission_card_states": [
                validate_json_value(drawn_card.to_payload()) for drawn_card in drawn
            ],
        },
    )


def _draw_replacement_then_forget(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    source_result_id: str,
) -> tuple[SecondaryMissionCardState, ...]:
    drawn = state.draw_tactical_secondary_cards(
        player_id=card.player_id,
        source_result_id=source_result_id,
        draw_count=1,
    )
    state.forget_secondary_mission_card_state(card)
    return drawn


def _discard_is_eligible(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    condition: str,
) -> bool:
    if condition == "may_discard_if_no_enemy_units_starting_strength_13_or_more_on_battlefield":
        return not _enemy_starting_strength_13_present(state, card.player_id)
    if condition == "may_discard_if_no_enemy_models_w10_or_more_on_battlefield":
        return not _enemy_wounds_10_present(state, card.player_id)
    raise GameLifecycleError("Unsupported When Drawn discard condition.")


def _player_has_active_tactical(
    state: GameState,
    *,
    player_id: str,
    secondary_mission_id: str,
) -> bool:
    return any(
        card.player_id == player_id
        and card.secondary_mission_id == secondary_mission_id
        and card.mode is SecondaryMissionCardMode.TACTICAL
        and card.status is SecondaryMissionCardStatus.ACTIVE
        for card in state.secondary_mission_card_states
    )


def _enemy_starting_strength_13_present(state: GameState, player_id: str) -> bool:
    for rules_unit in placed_alive_rules_unit_views(state=state):
        if rules_unit.owner_player_id == player_id:
            continue
        starting = state.starting_strength_record_for_unit(rules_unit.unit_instance_id)
        if starting.starting_model_count >= 13:
            return True
    return False


def _enemy_wounds_10_present(state: GameState, player_id: str) -> bool:
    for rules_unit in placed_alive_rules_unit_views(state=state):
        if rules_unit.owner_player_id == player_id:
            continue
        if any(model.starting_wounds >= 10 for model in rules_unit.alive_models()):
            return True
    return False


def _when_drawn_resolved(card: SecondaryMissionCardState) -> bool:
    selection = secondary_mission_selection_for_card(card)
    return selection is not None and selection.when_drawn_resolved


def _mark_when_drawn_resolved(*, state: GameState, card: SecondaryMissionCardState) -> None:
    selection = secondary_mission_selection_for_card(card) or SecondaryMissionSelection()
    state.replace_secondary_mission_card_state(
        card.with_selection(selection.with_when_drawn_resolved())
    )


def _when_drawn_request(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    action: str,
) -> DecisionRequest:
    keep_id = f"keep:{card.secondary_mission_id}"
    action_id = f"{action}:{card.secondary_mission_id}"
    context: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "player_id": card.player_id,
        "active_player_id": card.player_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "secondary_mission_id": card.secondary_mission_id,
        "secret": True,
        "legal_option_ids": [keep_id, action_id],
    }
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=RESOLVE_TACTICAL_SECONDARY_WHEN_DRAWN_DECISION_TYPE,
        actor_id=card.player_id,
        payload=context,
        options=(
            DecisionOption(
                option_id=keep_id,
                label=f"Keep {card.secondary_mission_id}",
                payload={**context, "action": "keep"},
            ),
            DecisionOption(
                option_id=action_id,
                label=f"{action.title()} {card.secondary_mission_id}",
                payload={**context, "action": action},
            ),
        ),
    )


def _event_payload(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    result: DecisionResult,
    action: str,
) -> dict[str, JsonValue]:
    return {
        "game_id": state.game_id,
        "player_id": card.player_id,
        "active_player_id": card.player_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "secondary_mission_id": card.secondary_mission_id,
        "action": action,
        "result_id": result.result_id,
        "hidden": True,
        "secondary_mission_card_state": validate_json_value(card.to_payload()),
    }


def _invalid(
    state: GameState,
    player_id: str,
    secondary_mission_id: str,
    reason: str,
) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Tactical secondary When Drawn option drifted.",
        payload={
            "game_id": state.game_id,
            "player_id": player_id,
            "secondary_mission_id": secondary_mission_id,
            "invalid_reason": reason,
        },
    )


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("When Drawn payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    return _validate_identifier(key, value)


def _payload_int(payload: dict[str, JsonValue], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"{key} must be an int.")
    return value
