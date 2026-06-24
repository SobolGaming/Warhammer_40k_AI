from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import PlacementError
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import BattleSize
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.reserves import ReserveOrigin
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndHookBinding,
    TurnEndRequestContext,
    TurnEndResultContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range

CONTRIBUTION_ID = "warhammer_40000_11th:grey_knights:army_rule:scaffold"
HOOK_ID = "warhammer_40000_11th:grey_knights:army_rule:gate_of_infinity"
SOURCE_RULE_ID = "phase17f:phase17e:grey-knights:army-rule:000010345"
GREY_KNIGHTS_FACTION_ID = "grey-knights"
GATE_OF_INFINITY_ABILITY_ID = "000010345"
GATE_OF_INFINITY_ABILITY_NAME = "Gate of Infinity"
TELEPORT_ASSAULT_ABILITY_NAME = "Teleport Assault"
SUBMISSION_KIND = "grey_knights_gate_of_infinity_turn_end"
GATE_OF_INFINITY_USED_EVENT = "grey_knights_gate_of_infinity_used"
GATE_OF_INFINITY_COMPLETED_EVENT = "grey_knights_gate_of_infinity_completed"

_BATTLE_SIZE_CAPS = {
    BattleSize.INCURSION: 2,
    BattleSize.STRIKE_FORCE: 3,
    BattleSize.ONSLAUGHT: 4,
}


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        turn_end_hook_bindings=(
            TurnEndHookBinding(
                hook_id=HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=gate_of_infinity_turn_end_request,
                result_handler=apply_gate_of_infinity_turn_end_result,
            ),
        ),
    )


def gate_of_infinity_turn_end_request(
    context: TurnEndRequestContext,
) -> DecisionRequest | None:
    if type(context) is not TurnEndRequestContext:
        raise GameLifecycleError("Grey Knights Gate of Infinity requires request context.")
    if context.completed_phase is not BattlePhase.FIGHT:
        return None
    active_player_id = _active_player_id(context.state)
    for army in _grey_knights_armies(context.state):
        if army.player_id == active_player_id:
            continue
        if _gate_of_infinity_completed_this_turn(context, player_id=army.player_id):
            continue
        selected_rules_unit_ids = _used_rules_unit_ids_this_turn(
            context,
            player_id=army.player_id,
        )
        max_units = gate_of_infinity_max_units_for_battle_size(army.battle_size)
        remaining_units = max_units - len(selected_rules_unit_ids)
        if remaining_units <= 0:
            continue
        eligible_views = _eligible_gate_of_infinity_rules_units(
            state=context.state,
            army=army,
        )
        if not eligible_views:
            continue
        return DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
            actor_id=army.player_id,
            payload=_request_payload(
                context=context,
                army=army,
                active_player_id=active_player_id,
                max_units=max_units,
                selected_rules_unit_ids=selected_rules_unit_ids,
                eligible_views=eligible_views,
            ),
            options=(
                *(
                    _gate_of_infinity_option(
                        player_id=army.player_id,
                        rules_unit_view=view,
                        use_ability=True,
                    )
                    for view in eligible_views
                ),
                _gate_of_infinity_complete_option(player_id=army.player_id),
            ),
        )
    return None


def apply_gate_of_infinity_turn_end_result(context: TurnEndResultContext) -> bool:
    if type(context) is not TurnEndResultContext:
        raise GameLifecycleError("Grey Knights Gate of Infinity requires result context.")
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != HOOK_ID:
        return False
    result_payload = _payload_object(context.result.payload)
    _validate_result_matches_request_context(
        state=context.state,
        request=context.request,
        result=context.result,
        request_payload=request_payload,
        result_payload=result_payload,
    )
    player_id = _payload_string(result_payload, "player_id")
    use_ability = _payload_bool(result_payload, "use_ability")
    if not use_ability:
        context.decisions.event_log.append(
            GATE_OF_INFINITY_COMPLETED_EVENT,
            _completion_event_payload(
                context=context,
                player_id=player_id,
            ),
        )
        return True

    target_rules_unit_instance_id = _payload_string(
        result_payload,
        "target_rules_unit_instance_id",
    )
    if target_rules_unit_instance_id not in _payload_string_tuple(
        request_payload,
        "eligible_rules_unit_instance_ids",
    ):
        raise GameLifecycleError("Grey Knights Gate of Infinity target option drift.")
    if _gate_of_infinity_completed_this_turn_for_payload(
        state=context.state,
        request_payload=request_payload,
        decisions_event_records=context.decisions.event_log.records,
        player_id=player_id,
    ):
        raise GameLifecycleError("Grey Knights Gate of Infinity was already completed this turn.")
    used_rules_unit_ids = _used_rules_unit_ids_this_turn_for_payload(
        state=context.state,
        request_payload=request_payload,
        decisions_event_records=context.decisions.event_log.records,
        player_id=player_id,
    )
    max_units = _payload_int(request_payload, "max_units")
    if len(used_rules_unit_ids) >= max_units:
        raise GameLifecycleError("Grey Knights Gate of Infinity cap is already exhausted.")
    army = _army_for_player(context.state, player_id=player_id)
    rules_unit_view = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=target_rules_unit_instance_id,
    )
    _assert_rules_unit_still_matches_result(
        army=army,
        rules_unit_view=rules_unit_view,
        result_payload=result_payload,
    )
    _assert_rules_unit_can_enter_strategic_reserves(
        state=context.state,
        rules_unit_view=rules_unit_view,
    )
    required_arrival_battle_round = _next_movement_battle_round(context.state)
    reserve_state_payloads: list[JsonValue] = []
    for unit_instance_id in rules_unit_view.component_unit_instance_ids:
        reserve_state = context.state.reposition_unit_to_strategic_reserves(
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
            source_rule_ids=(SOURCE_RULE_ID,),
            required_arrival_battle_round=required_arrival_battle_round,
            required_arrival_phase=BattlePhase.MOVEMENT,
            required_arrival_source_rule_id=SOURCE_RULE_ID,
        )
        reserve_state_payloads.append(cast(JsonValue, reserve_state.to_payload()))
    context.decisions.event_log.append(
        GATE_OF_INFINITY_USED_EVENT,
        _used_event_payload(
            context=context,
            player_id=player_id,
            rules_unit_view=rules_unit_view,
            reserve_state_payloads=tuple(reserve_state_payloads),
            selected_count_after=len(used_rules_unit_ids) + 1,
            max_units=max_units,
        ),
    )
    return True


def gate_of_infinity_max_units_for_battle_size(battle_size: BattleSize) -> int:
    resolved_battle_size = BattleSize(battle_size)
    return _BATTLE_SIZE_CAPS[resolved_battle_size]


def _request_payload(
    *,
    context: TurnEndRequestContext,
    army: ArmyDefinition,
    active_player_id: str,
    max_units: int,
    selected_rules_unit_ids: tuple[str, ...],
    eligible_views: tuple[RulesUnitView, ...],
) -> JsonValue:
    return validate_json_value(
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "active_player_id": active_player_id,
            "phase": context.completed_phase.value,
            "player_id": army.player_id,
            "faction_id": GREY_KNIGHTS_FACTION_ID,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
            "ability_id": GATE_OF_INFINITY_ABILITY_ID,
            "ability_name": GATE_OF_INFINITY_ABILITY_NAME,
            "max_units": max_units,
            "selected_count": len(selected_rules_unit_ids),
            "remaining_units": max_units - len(selected_rules_unit_ids),
            "selected_rules_unit_instance_ids": selected_rules_unit_ids,
            "eligible_rules_unit_instance_ids": tuple(
                view.unit_instance_id for view in eligible_views
            ),
            "eligible_component_unit_instance_ids_by_rules_unit": {
                view.unit_instance_id: view.component_unit_instance_ids for view in eligible_views
            },
        }
    )


def _gate_of_infinity_option(
    *,
    player_id: str,
    rules_unit_view: RulesUnitView,
    use_ability: bool,
) -> DecisionOption:
    action = "use" if use_ability else "complete"
    return DecisionOption(
        option_id=(f"grey-knights:gate-of-infinity:{rules_unit_view.unit_instance_id}:{action}"),
        label=f"Use Gate of Infinity: {rules_unit_view.unit_instance_id}",
        payload=validate_json_value(
            {
                "submission_kind": SUBMISSION_KIND,
                "player_id": player_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "ability_id": GATE_OF_INFINITY_ABILITY_ID,
                "ability_name": GATE_OF_INFINITY_ABILITY_NAME,
                "target_rules_unit_instance_id": rules_unit_view.unit_instance_id,
                "component_unit_instance_ids": list(rules_unit_view.component_unit_instance_ids),
                "use_ability": use_ability,
                "action": action,
            }
        ),
    )


def _gate_of_infinity_complete_option(*, player_id: str) -> DecisionOption:
    return DecisionOption(
        option_id="grey-knights:gate-of-infinity:complete",
        label="Complete Gate of Infinity",
        payload=validate_json_value(
            {
                "submission_kind": SUBMISSION_KIND,
                "player_id": player_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "ability_id": GATE_OF_INFINITY_ABILITY_ID,
                "ability_name": GATE_OF_INFINITY_ABILITY_NAME,
                "target_rules_unit_instance_id": None,
                "component_unit_instance_ids": [],
                "use_ability": False,
                "action": "complete",
            }
        ),
    )


def _eligible_gate_of_infinity_rules_units(
    *,
    state: GameState,
    army: ArmyDefinition,
) -> tuple[RulesUnitView, ...]:
    seen_rules_unit_ids: set[str] = set()
    eligible: list[RulesUnitView] = []
    for unit in sorted(army.units, key=lambda stored: stored.unit_instance_id):
        rules_unit_view = rules_unit_view_by_id(
            state=state,
            unit_instance_id=unit.unit_instance_id,
        )
        if rules_unit_view.unit_instance_id in seen_rules_unit_ids:
            continue
        seen_rules_unit_ids.add(rules_unit_view.unit_instance_id)
        if not _rules_unit_has_gate_of_infinity(rules_unit_view):
            continue
        if _rules_unit_can_enter_strategic_reserves(
            state=state,
            rules_unit_view=rules_unit_view,
        ):
            eligible.append(rules_unit_view)
    return tuple(sorted(eligible, key=lambda view: view.unit_instance_id))


def _rules_unit_has_gate_of_infinity(rules_unit_view: RulesUnitView) -> bool:
    return all(
        _unit_has_gate_of_infinity(component.unit) for component in rules_unit_view.components
    )


def _unit_has_gate_of_infinity(unit: UnitInstance) -> bool:
    for ability in unit.datasheet_abilities:
        if ability.ability_id == GATE_OF_INFINITY_ABILITY_ID:
            return True
        if ability.name in {GATE_OF_INFINITY_ABILITY_NAME, TELEPORT_ASSAULT_ABILITY_NAME}:
            return True
    return False


def _rules_unit_can_enter_strategic_reserves(
    *,
    state: GameState,
    rules_unit_view: RulesUnitView,
) -> bool:
    if state.battlefield_state is None:
        raise GameLifecycleError("Grey Knights Gate of Infinity requires battlefield_state.")
    if _rules_unit_within_enemy_engagement_range(state=state, rules_unit_view=rules_unit_view):
        return False
    for component in rules_unit_view.components:
        unit_instance_id = component.unit.unit_instance_id
        if state.reserve_state_for_unit(unit_instance_id) is not None:
            return False
        try:
            placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
        except PlacementError:
            return False
        if placement.player_id != rules_unit_view.owner_player_id:
            raise GameLifecycleError(
                "Grey Knights Gate of Infinity unit placement player_id drift."
            )
    return True


def _assert_rules_unit_can_enter_strategic_reserves(
    *,
    state: GameState,
    rules_unit_view: RulesUnitView,
) -> None:
    if state.battlefield_state is None:
        raise GameLifecycleError("Grey Knights Gate of Infinity requires battlefield_state.")
    if _rules_unit_within_enemy_engagement_range(state=state, rules_unit_view=rules_unit_view):
        raise GameLifecycleError("Grey Knights Gate of Infinity unit is within Engagement Range.")
    for component in rules_unit_view.components:
        unit_instance_id = component.unit.unit_instance_id
        if state.reserve_state_for_unit(unit_instance_id) is not None:
            raise GameLifecycleError(
                "Grey Knights Gate of Infinity unit already has a ReserveState."
            )
        try:
            placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
        except PlacementError as exc:
            raise GameLifecycleError(
                "Grey Knights Gate of Infinity unit must be on the battlefield."
            ) from exc
        if placement.player_id != rules_unit_view.owner_player_id:
            raise GameLifecycleError(
                "Grey Knights Gate of Infinity unit placement player_id drift."
            )


def _rules_unit_within_enemy_engagement_range(
    *,
    state: GameState,
    rules_unit_view: RulesUnitView,
) -> bool:
    for component in rules_unit_view.components:
        if unit_within_enemy_engagement_range(
            state=state,
            unit_instance_id=component.unit.unit_instance_id,
        ):
            return True
    return False


def _assert_rules_unit_still_matches_result(
    *,
    army: ArmyDefinition,
    rules_unit_view: RulesUnitView,
    result_payload: dict[str, JsonValue],
) -> None:
    if rules_unit_view.owner_player_id != army.player_id:
        raise GameLifecycleError("Grey Knights Gate of Infinity target owner drift.")
    if not _rules_unit_has_gate_of_infinity(rules_unit_view):
        raise GameLifecycleError("Grey Knights Gate of Infinity target lost the ability.")
    result_component_ids = _payload_string_tuple(result_payload, "component_unit_instance_ids")
    if result_component_ids != rules_unit_view.component_unit_instance_ids:
        raise GameLifecycleError("Grey Knights Gate of Infinity component drift.")


def _used_event_payload(
    *,
    context: TurnEndResultContext,
    player_id: str,
    rules_unit_view: RulesUnitView,
    reserve_state_payloads: tuple[JsonValue, ...],
    selected_count_after: int,
    max_units: int,
) -> dict[str, JsonValue]:
    return {
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "active_player_id": context.state.active_player_id,
        "phase": BattlePhase.FIGHT.value,
        "player_id": player_id,
        "faction_id": GREY_KNIGHTS_FACTION_ID,
        "source_rule_id": SOURCE_RULE_ID,
        "hook_id": HOOK_ID,
        "ability_id": GATE_OF_INFINITY_ABILITY_ID,
        "ability_name": GATE_OF_INFINITY_ABILITY_NAME,
        "target_rules_unit_instance_id": rules_unit_view.unit_instance_id,
        "component_unit_instance_ids": list(rules_unit_view.component_unit_instance_ids),
        "request_id": context.request.request_id,
        "result_id": context.result.result_id,
        "selected_option_id": context.result.selected_option_id,
        "use_ability": True,
        "selected_count_after": selected_count_after,
        "max_units": max_units,
        "required_arrival_battle_round": _next_movement_battle_round(context.state),
        "required_arrival_phase": BattlePhase.MOVEMENT.value,
        "reserve_states": list(reserve_state_payloads),
    }


def _completion_event_payload(
    *,
    context: TurnEndResultContext,
    player_id: str,
) -> dict[str, JsonValue]:
    return {
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "active_player_id": context.state.active_player_id,
        "phase": BattlePhase.FIGHT.value,
        "player_id": player_id,
        "faction_id": GREY_KNIGHTS_FACTION_ID,
        "source_rule_id": SOURCE_RULE_ID,
        "hook_id": HOOK_ID,
        "ability_id": GATE_OF_INFINITY_ABILITY_ID,
        "ability_name": GATE_OF_INFINITY_ABILITY_NAME,
        "request_id": context.request.request_id,
        "result_id": context.result.result_id,
        "selected_option_id": context.result.selected_option_id,
        "use_ability": False,
    }


def _validate_result_matches_request_context(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    request_payload: dict[str, JsonValue],
    result_payload: dict[str, JsonValue],
) -> None:
    if _payload_string(request_payload, "game_id") != state.game_id:
        raise GameLifecycleError("Grey Knights Gate of Infinity game_id drift.")
    if _payload_int(request_payload, "battle_round") != state.battle_round:
        raise GameLifecycleError("Grey Knights Gate of Infinity battle round drift.")
    if _payload_string(request_payload, "active_player_id") != _active_player_id(state):
        raise GameLifecycleError("Grey Knights Gate of Infinity active player drift.")
    if _payload_string(request_payload, "phase") != BattlePhase.FIGHT.value:
        raise GameLifecycleError("Grey Knights Gate of Infinity phase drift.")
    if state.current_battle_phase is not BattlePhase.FIGHT:
        raise GameLifecycleError("Grey Knights Gate of Infinity current phase drift.")
    if request.actor_id != _payload_string(request_payload, "player_id"):
        raise GameLifecycleError("Grey Knights Gate of Infinity request actor drift.")
    if result.actor_id != request.actor_id:
        raise GameLifecycleError("Grey Knights Gate of Infinity result actor drift.")
    for key in (
        "player_id",
        "source_rule_id",
        "hook_id",
        "ability_id",
        "ability_name",
    ):
        if request_payload.get(key) != result_payload.get(key):
            raise GameLifecycleError("Grey Knights Gate of Infinity result payload drift.")
    if _payload_string(result_payload, "submission_kind") != SUBMISSION_KIND:
        raise GameLifecycleError("Grey Knights Gate of Infinity submission kind drift.")


def _gate_of_infinity_completed_this_turn(
    context: TurnEndRequestContext,
    *,
    player_id: str,
) -> bool:
    return _gate_of_infinity_completed_this_turn_for_payload(
        state=context.state,
        request_payload={
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "active_player_id": _active_player_id(context.state),
            "phase": context.completed_phase.value,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
        },
        decisions_event_records=context.decisions.event_log.records,
        player_id=player_id,
    )


def _gate_of_infinity_completed_this_turn_for_payload(
    *,
    state: GameState,
    request_payload: dict[str, JsonValue],
    decisions_event_records: tuple[EventRecord, ...],
    player_id: str,
) -> bool:
    for record_payload in _matching_gate_of_infinity_payloads(
        state=state,
        request_payload=request_payload,
        decisions_event_records=decisions_event_records,
        event_type=GATE_OF_INFINITY_COMPLETED_EVENT,
        player_id=player_id,
    ):
        if record_payload.get("use_ability") is False:
            return True
    return False


def _used_rules_unit_ids_this_turn(
    context: TurnEndRequestContext,
    *,
    player_id: str,
) -> tuple[str, ...]:
    return _used_rules_unit_ids_this_turn_for_payload(
        state=context.state,
        request_payload={
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "active_player_id": _active_player_id(context.state),
            "phase": context.completed_phase.value,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
        },
        decisions_event_records=context.decisions.event_log.records,
        player_id=player_id,
    )


def _used_rules_unit_ids_this_turn_for_payload(
    *,
    state: GameState,
    request_payload: dict[str, JsonValue],
    decisions_event_records: tuple[EventRecord, ...],
    player_id: str,
) -> tuple[str, ...]:
    used: list[str] = []
    for payload in _matching_gate_of_infinity_payloads(
        state=state,
        request_payload=request_payload,
        decisions_event_records=decisions_event_records,
        event_type=GATE_OF_INFINITY_USED_EVENT,
        player_id=player_id,
    ):
        if payload.get("use_ability") is not True:
            continue
        unit_id = payload.get("target_rules_unit_instance_id")
        if type(unit_id) is str:
            used.append(unit_id)
    return tuple(sorted(set(used)))


def _matching_gate_of_infinity_payloads(
    *,
    state: GameState,
    request_payload: dict[str, JsonValue],
    decisions_event_records: tuple[EventRecord, ...],
    event_type: str,
    player_id: str,
) -> tuple[dict[str, JsonValue], ...]:
    matched: list[dict[str, JsonValue]] = []
    for record in decisions_event_records:
        if record.event_type != event_type:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != state.game_id:
            continue
        if payload.get("battle_round") != request_payload.get("battle_round"):
            continue
        if payload.get("active_player_id") != request_payload.get("active_player_id"):
            continue
        if payload.get("phase") != request_payload.get("phase"):
            continue
        if payload.get("player_id") != player_id:
            continue
        if payload.get("source_rule_id") != SOURCE_RULE_ID:
            continue
        if payload.get("hook_id") != HOOK_ID:
            continue
        matched.append(payload)
    return tuple(matched)


def _grey_knights_armies(state: GameState) -> tuple[ArmyDefinition, ...]:
    if type(state) is not GameState:
        raise GameLifecycleError("Grey Knights Gate of Infinity requires GameState.")
    return tuple(
        army
        for army in state.army_definitions
        if army.detachment_selection.faction_id == GREY_KNIGHTS_FACTION_ID
    )


def _army_for_player(state: GameState, *, player_id: str) -> ArmyDefinition:
    requested_player_id = _validate_string("player_id", player_id)
    for army in _grey_knights_armies(state):
        if army.player_id == requested_player_id:
            return army
    raise GameLifecycleError("Grey Knights Gate of Infinity army is unavailable.")


def _next_movement_battle_round(state: GameState) -> int:
    active_player_id = _active_player_id(state)
    if state.turn_order[-1] == active_player_id:
        return state.battle_round + 1
    return state.battle_round


def _active_player_id(state: GameState) -> str:
    if type(state) is not GameState:
        raise GameLifecycleError("Grey Knights Gate of Infinity requires GameState.")
    if state.active_player_id is None:
        raise GameLifecycleError("Grey Knights Gate of Infinity requires active player.")
    return state.active_player_id


def _payload_object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Grey Knights Gate of Infinity payload must be an object.")
    return value


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Grey Knights Gate of Infinity {key} must be a string.")
    return value


def _payload_bool(payload: dict[str, JsonValue], key: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise GameLifecycleError(f"Grey Knights Gate of Infinity {key} must be a bool.")
    return value


def _payload_int(payload: dict[str, JsonValue], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Grey Knights Gate of Infinity {key} must be an int.")
    return value


def _payload_string_tuple(payload: dict[str, JsonValue], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Grey Knights Gate of Infinity {key} must be a list.")
    values: list[str] = []
    for item in value:
        if type(item) is not str:
            raise GameLifecycleError(f"Grey Knights Gate of Infinity {key} must contain strings.")
        values.append(item)
    return tuple(values)


def _validate_string(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Grey Knights Gate of Infinity {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Grey Knights Gate of Infinity {field_name} must not be empty.")
    return stripped
