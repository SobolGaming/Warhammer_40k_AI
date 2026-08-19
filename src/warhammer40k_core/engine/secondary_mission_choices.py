from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.missions import ObjectiveMarkerRole
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
from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
)
from warhammer40k_core.engine.secondary_mission_selection import SecondaryMissionSelection
from warhammer40k_core.engine.secondary_scoring_context import secondary_mission_selection_for_card

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

SELECT_TEMPTING_TARGET_OBJECTIVE_DECISION_TYPE = "select_tempting_target_objective"
SELECT_BEACON_UNIT_DECISION_TYPE = "select_beacon_unit"
SELECT_BURDEN_OF_TRUST_GUARD_DECISION_TYPE = "select_burden_of_trust_guard"
SECONDARY_CHOICE_DECISION_TYPES = frozenset(
    {
        SELECT_TEMPTING_TARGET_OBJECTIVE_DECISION_TYPE,
        SELECT_BEACON_UNIT_DECISION_TYPE,
        SELECT_BURDEN_OF_TRUST_GUARD_DECISION_TYPE,
    }
)
_validate_identifier = IdentifierValidator(GameLifecycleError)


def next_secondary_mission_choice_request(
    *,
    state: GameState,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.game_state import GameState as _GameState

    if type(state) is not _GameState:
        raise GameLifecycleError("Secondary mission choice requires GameState.")
    if state.stage is not GameLifecycleStage.BATTLE or state.current_battle_phase is not (
        BattlePhase.COMMAND
    ):
        return None
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Secondary mission choice requires an active player.")
    for card in _active_tactical_cards(state=state, player_id=active_player_id):
        request = _request_for_card(state=state, card=card)
        if request is None:
            continue
        decisions.request_decision(request)
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=request,
            payload={
                "game_id": state.game_id,
                "player_id": request.actor_id,
                "secondary_mission_id": card.secondary_mission_id,
                "decision_type": request.decision_type,
            },
        )
    return None


def invalid_secondary_mission_choice_status(
    *,
    state: GameState,
    result: DecisionResult,
) -> LifecycleStatus | None:
    payload = _payload_object(result.payload)
    player_id = _payload_string(payload, "player_id")
    secondary_mission_id = _payload_string(payload, "secondary_mission_id")
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
    if result.decision_type == SELECT_TEMPTING_TARGET_OBJECTIVE_DECISION_TYPE:
        if result.actor_id == player_id:
            return _invalid(state, player_id, secondary_mission_id, "actor_player_drift")
        if result.actor_id != _opponent_player_id(state, player_id):
            return _invalid(state, player_id, secondary_mission_id, "actor_player_drift")
        return None
    if result.actor_id != player_id:
        return _invalid(state, player_id, secondary_mission_id, "actor_player_drift")
    return None


def apply_secondary_mission_choice(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    payload = _payload_object(result.payload)
    player_id = _payload_string(payload, "player_id")
    secondary_mission_id = _payload_string(payload, "secondary_mission_id")
    card = state.secondary_mission_card_state(
        player_id=player_id,
        secondary_mission_id=secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    if card is None:
        raise GameLifecycleError("Secondary mission choice requires an active card.")
    selection = secondary_mission_selection_for_card(card) or SecondaryMissionSelection()
    if result.decision_type == SELECT_TEMPTING_TARGET_OBJECTIVE_DECISION_TYPE:
        objective_id = _payload_string(payload, "objective_id")
        updated = card.with_selection(selection.with_tempting_objective(objective_id))
        state.replace_secondary_mission_card_state(updated)
        decisions.event_log.append(
            "tempting_target_objective_selected",
            _choice_event(state=state, card=updated, result=result, hidden=False),
        )
        return
    if result.decision_type == SELECT_BEACON_UNIT_DECISION_TYPE:
        unit_id = _payload_string(payload, "unit_instance_id")
        updated = card.with_selection(selection.with_beacon_unit(unit_id))
        state.replace_secondary_mission_card_state(updated)
        decisions.event_log.append(
            "beacon_unit_selected",
            _choice_event(state=state, card=updated, result=result, hidden=True),
        )
        return
    if result.decision_type == SELECT_BURDEN_OF_TRUST_GUARD_DECISION_TYPE:
        objective_id = _payload_string(payload, "objective_id")
        skip = _payload_bool(payload, "skip")
        if selection.guard_selection_battle_round != state.battle_round:
            bindings = []
            resolved_ids: list[str] = []
        else:
            bindings = list(selection.guarded_objective_unit_ids)
            resolved_ids = list(selection.resolved_guard_objective_ids)
        if not skip:
            unit_id = _payload_string(payload, "unit_instance_id")
            bindings.append((objective_id, unit_id))
        resolved_ids.append(objective_id)
        updated_selection = selection.with_guards(
            guarded_objective_unit_ids=tuple(bindings),
            resolved_guard_objective_ids=tuple(resolved_ids),
            battle_round=state.battle_round,
        )
        updated = card.with_selection(updated_selection)
        state.replace_secondary_mission_card_state(updated)
        decisions.event_log.append(
            "burden_of_trust_guard_selected",
            _choice_event(state=state, card=updated, result=result, hidden=True),
        )
        return
    raise GameLifecycleError("Secondary mission choice decision_type is unsupported.")


def _request_for_card(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
) -> DecisionRequest | None:
    selection = secondary_mission_selection_for_card(card)
    if card.secondary_mission_id == "a-tempting-target":
        if selection is not None and selection.tempting_objective_id is not None:
            return None
        return _tempting_request(state=state, card=card)
    if card.secondary_mission_id == "beacon":
        if selection is not None and selection.beacon_unit_instance_id is not None:
            return None
        return _beacon_request(state=state, card=card)
    if card.secondary_mission_id == "burden-of-trust":
        return _burden_request(state=state, card=card, selection=selection)
    return None


def _tempting_request(*, state: GameState, card: SecondaryMissionCardState) -> DecisionRequest:
    if state.mission_setup is None:
        raise GameLifecycleError("Tempting Target requires MissionSetup.")
    opponent_id = _opponent_player_id(state, card.player_id)
    objectives = tuple(
        marker.objective_marker_id
        for marker in state.mission_setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
        or marker.objective_role is ObjectiveMarkerRole.EXPANSION
    )
    if not objectives:
        raise GameLifecycleError("Tempting Target requires a No Man's Land objective.")
    context: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "player_id": card.player_id,
        "actor_player_id": opponent_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "secondary_mission_id": card.secondary_mission_id,
        "secret": False,
        "legal_option_ids": [f"tempting:{objective_id}" for objective_id in objectives],
    }
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_TEMPTING_TARGET_OBJECTIVE_DECISION_TYPE,
        actor_id=opponent_id,
        payload=context,
        options=tuple(
            DecisionOption(
                option_id=f"tempting:{objective_id}",
                label=f"Select {objective_id}",
                payload={**context, "objective_id": objective_id},
            )
            for objective_id in objectives
        ),
    )


def _beacon_request(*, state: GameState, card: SecondaryMissionCardState) -> DecisionRequest:
    unit_ids = _beacon_eligible_unit_ids(state=state, player_id=card.player_id)
    if not unit_ids:
        raise GameLifecycleError("Beacon requires a friendly unit on the battlefield.")
    context: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "player_id": card.player_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "secondary_mission_id": card.secondary_mission_id,
        "secret": True,
        "legal_option_ids": [f"beacon:{unit_id}" for unit_id in unit_ids],
    }
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_BEACON_UNIT_DECISION_TYPE,
        actor_id=card.player_id,
        payload=context,
        options=tuple(
            DecisionOption(
                option_id=f"beacon:{unit_id}",
                label=f"Beacon {unit_id}",
                payload={**context, "unit_instance_id": unit_id},
            )
            for unit_id in unit_ids
        ),
    )


def _burden_request(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    selection: SecondaryMissionSelection | None,
) -> DecisionRequest | None:
    if selection is not None and selection.guard_selection_battle_round == state.battle_round:
        remaining = _remaining_burden_objectives(
            state=state,
            assigned=selection.resolved_guard_objective_ids,
        )
        if not remaining:
            return None
        assigned_units = {
            unit_id for _objective_id, unit_id in selection.guarded_objective_unit_ids
        }
        objective_id = remaining[0]
        return _burden_objective_request(
            state=state,
            card=card,
            objective_id=objective_id,
            assigned_units=assigned_units,
        )
    remaining = _remaining_burden_objectives(state=state, assigned=())
    if not remaining:
        return None
    return _burden_objective_request(
        state=state,
        card=card,
        objective_id=remaining[0],
        assigned_units=set(),
    )


def _burden_objective_request(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    objective_id: str,
    assigned_units: set[str],
) -> DecisionRequest:
    unit_ids = tuple(
        unit_id
        for unit_id in _friendly_placed_unit_ids(state=state, player_id=card.player_id)
        if unit_id not in assigned_units
    )
    skip_id = f"skip:{objective_id}"
    option_ids: list[JsonValue] = [
        skip_id,
        *[f"guard:{objective_id}:{unit_id}" for unit_id in unit_ids],
    ]
    context: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "player_id": card.player_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "secondary_mission_id": card.secondary_mission_id,
        "objective_id": objective_id,
        "secret": True,
        "legal_option_ids": option_ids,
    }
    options = [
        DecisionOption(
            option_id=skip_id,
            label=f"Skip {objective_id}",
            payload={**context, "skip": True, "objective_id": objective_id},
        )
    ]
    options.extend(
        DecisionOption(
            option_id=f"guard:{objective_id}:{unit_id}",
            label=f"Guard {objective_id} with {unit_id}",
            payload={
                **context,
                "skip": False,
                "objective_id": objective_id,
                "unit_instance_id": unit_id,
            },
        )
        for unit_id in unit_ids
    )
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_BURDEN_OF_TRUST_GUARD_DECISION_TYPE,
        actor_id=card.player_id,
        payload=context,
        options=tuple(options),
    )


def _remaining_burden_objectives(*, state: GameState, assigned: tuple[str, ...]) -> tuple[str, ...]:
    if state.mission_setup is None:
        raise GameLifecycleError("Burden of Trust requires MissionSetup.")
    assigned_ids = frozenset(assigned)
    return tuple(
        marker.objective_marker_id
        for marker in state.mission_setup.objective_markers
        if marker.objective_marker_id not in assigned_ids
    )


def _beacon_eligible_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    if state.battlefield_state is None:
        raise GameLifecycleError("Beacon selection requires battlefield state.")
    embarked = {
        unit_id
        for cargo in state.transport_cargo_states
        for unit_id in cargo.embarked_unit_instance_ids
    }
    transport_on_battlefield = {
        cargo.transport_unit_instance_id
        for cargo in state.transport_cargo_states
        if state.battlefield_state.is_unit_placed(cargo.transport_unit_instance_id)
    }
    eligible: list[str] = []
    for view in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
        if view.owner_player_id != player_id:
            continue
        unit_id = view.unit_instance_id
        if state.battlefield_state.is_unit_placed(unit_id):
            eligible.append(unit_id)
            continue
        if unit_id in embarked:
            cargo = next(
                cargo
                for cargo in state.transport_cargo_states
                if unit_id in cargo.embarked_unit_instance_ids
            )
            if cargo.transport_unit_instance_id in transport_on_battlefield:
                eligible.append(unit_id)
    return tuple(sorted(set(eligible)))


def _friendly_placed_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    if state.battlefield_state is None:
        raise GameLifecycleError("Burden of Trust requires battlefield state.")
    return tuple(
        sorted(
            view.unit_instance_id
            for view in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
            if view.owner_player_id == player_id
            and state.battlefield_state.is_unit_placed(view.unit_instance_id)
        )
    )


def _active_tactical_cards(
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


def _opponent_player_id(state: GameState, player_id: str) -> str:
    opponents = tuple(candidate for candidate in state.player_ids if candidate != player_id)
    if len(opponents) != 1:
        raise GameLifecycleError("Secondary mission choice requires exactly one opponent.")
    return opponents[0]


def _choice_event(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    result: DecisionResult,
    hidden: bool,
) -> dict[str, JsonValue]:
    return {
        "game_id": state.game_id,
        "player_id": card.player_id,
        "active_player_id": state.active_player_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "secondary_mission_id": card.secondary_mission_id,
        "result_id": result.result_id,
        "hidden": hidden,
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
        message="Secondary mission choice option drifted.",
        payload={
            "game_id": state.game_id,
            "player_id": player_id,
            "secondary_mission_id": secondary_mission_id,
            "invalid_reason": reason,
        },
    )


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Secondary mission choice payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    return _validate_identifier(key, payload.get(key))


def _payload_int(payload: dict[str, JsonValue], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"{key} must be an int.")
    return value


def _payload_bool(payload: dict[str, JsonValue], key: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise GameLifecycleError(f"{key} must be a bool.")
    return value
