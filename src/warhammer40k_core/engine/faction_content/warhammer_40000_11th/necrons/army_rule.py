from __future__ import annotations

from warhammer40k_core.core.dice import D3RollResult, DiceExpression, DiceRollSpec
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartHookBinding,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.common import (
    canonical_keyword as _canonical_keyword,
)
from warhammer40k_core.engine.faction_content.common import (
    event_payload_object,
    payload_identifier,
    payload_object,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.healing import HealingEffect, resolve_healing_until_blocked
from warhammer40k_core.engine.healing_geometry import (
    healing_battlefield_state,
    healing_opposing_player_id,
    healing_phase_start_enemy_engagement_model_ids,
    healing_phase_start_model_ids,
    healing_rules_unit_placements,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.unit_factory import UnitInstance

_event_payload_object = event_payload_object
_payload_object = payload_object


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Reanimation Protocols payload missing required key {key}.")
    return payload_identifier(payload, key)


CONTRIBUTION_ID = "warhammer_40000_11th:necrons:army_rule:reanimation_protocols"
HOOK_ID = "warhammer_40000_11th:necrons:army_rule:reanimation_protocols"
SOURCE_RULE_ID = "phase17f:phase17e:necrons:army-rule"
NECRONS_FACTION_ID = "necrons"
NECRONS_FACTION_KEYWORD = "NECRONS"
REANIMATION_EFFECT_KIND = "necrons_reanimation_protocols"
REANIMATION_SELECTION_KIND = "necrons_reanimation_protocols_activation"
REANIMATION_ROLL_TYPE = "necrons.reanimation_protocols_d3"
REANIMATION_RESOLVED_EVENT = "necrons_reanimation_protocols_resolved"
REANIMATION_PENDING_EVENT = "necrons_reanimation_protocols_healing_pending"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        command_phase_start_hook_bindings=(
            CommandPhaseStartHookBinding(
                hook_id=HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=reanimation_protocols_request,
                result_handler=apply_reanimation_protocols_result,
            ),
        ),
    )


def reanimation_protocols_request(
    context: CommandPhaseStartRequestContext,
) -> DecisionRequest | None:
    if type(context) is not CommandPhaseStartRequestContext:
        raise GameLifecycleError("Reanimation Protocols requires request context.")
    army = _necrons_army_for_player(context.state, player_id=context.active_player_id)
    if army is None:
        return None
    unresolved_rules_units = tuple(
        rules_unit
        for rules_unit in _eligible_reanimation_rules_units(context.state, army=army)
        if not _reanimation_resolved_for_rules_unit(
            records=context.decisions.event_log.records,
            state=context.state,
            player_id=army.player_id,
            rules_unit_instance_id=rules_unit.unit_instance_id,
        )
    )
    if not unresolved_rules_units:
        return None
    common_payload = {
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "active_player_id": army.player_id,
        "player_id": army.player_id,
        "faction_id": NECRONS_FACTION_ID,
        "source_rule_id": SOURCE_RULE_ID,
        "hook_id": HOOK_ID,
        "effect_kind": REANIMATION_EFFECT_KIND,
        "selection_kind": REANIMATION_SELECTION_KIND,
        "eligible_rules_unit_instance_ids": [
            rules_unit.unit_instance_id for rules_unit in unresolved_rules_units
        ],
    }
    return DecisionRequest(
        request_id=context.state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
        actor_id=army.player_id,
        payload=validate_json_value(common_payload),
        options=tuple(
            DecisionOption(
                option_id=_reanimation_option_id(rules_unit.unit_instance_id),
                label=f"Reanimation Protocols: {_rules_unit_label(rules_unit)}",
                payload=validate_json_value(
                    {
                        **common_payload,
                        "rules_unit_instance_id": rules_unit.unit_instance_id,
                        "rules_unit_owner_player_id": army.player_id,
                        "rules_unit_name": _rules_unit_label(rules_unit),
                        "component_unit_instance_ids": list(rules_unit.component_unit_instance_ids),
                    }
                ),
            )
            for rules_unit in unresolved_rules_units
        ),
    )


def apply_reanimation_protocols_result(context: CommandPhaseStartResultContext) -> bool:
    if type(context) is not CommandPhaseStartResultContext:
        raise GameLifecycleError("Reanimation Protocols requires result context.")
    if (
        context.request.decision_type
        != SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
    ):
        return False
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != HOOK_ID:
        return False
    result = context.result
    result.validate_for_request(context.request)
    if result.actor_id is None:
        raise GameLifecycleError("Reanimation Protocols requires an actor.")
    player_id = result.actor_id
    if player_id != context.active_player_id:
        raise GameLifecycleError("Reanimation Protocols actor must be the active player.")
    army = _necrons_army_for_player(context.state, player_id=player_id)
    if army is None:
        raise GameLifecycleError("Reanimation Protocols actor does not own Necrons.")

    payload = _payload_object(result.payload)
    if payload.get("hook_id") != HOOK_ID:
        raise GameLifecycleError("Reanimation Protocols hook_id drift.")
    if _payload_string(payload, key="player_id") != player_id:
        raise GameLifecycleError("Reanimation Protocols player drift.")
    rules_unit_id = _payload_string(payload, key="rules_unit_instance_id")
    if result.selected_option_id != _reanimation_option_id(rules_unit_id):
        raise GameLifecycleError("Reanimation Protocols option_id drift.")
    unresolved_rules_units = {
        rules_unit.unit_instance_id: rules_unit
        for rules_unit in _eligible_reanimation_rules_units(context.state, army=army)
        if not _reanimation_resolved_for_rules_unit(
            records=context.decisions.event_log.records,
            state=context.state,
            player_id=player_id,
            rules_unit_instance_id=rules_unit.unit_instance_id,
        )
    }
    rules_unit = unresolved_rules_units.get(rules_unit_id)
    if rules_unit is None:
        raise GameLifecycleError("Reanimation Protocols rules unit is no longer eligible.")

    d3_result = _roll_reanimation_d3(
        state=context.state,
        decisions=context.decisions,
        rules_unit=rules_unit,
    )
    effect = _reanimation_healing_effect(
        state=context.state,
        army=army,
        rules_unit=rules_unit,
        result_id=result.result_id,
        request_id=context.request.request_id,
        selected_option_id=result.selected_option_id,
        d3_result=d3_result,
    )
    resolved_effect, pending_request = resolve_healing_until_blocked(
        state=context.state,
        decisions=context.decisions,
        ruleset_descriptor=context.state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    if pending_request is None:
        _emit_reanimation_resolved(
            context=context,
            player_id=player_id,
            rules_unit_id=rules_unit.unit_instance_id,
            d3_result=d3_result,
            healing_effect=resolved_effect,
        )
        return True
    context.decisions.event_log.append(
        REANIMATION_PENDING_EVENT,
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "player_id": player_id,
            "rules_unit_instance_id": rules_unit.unit_instance_id,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
            "request_id": context.request.request_id,
            "result_id": result.result_id,
            "d3_result": validate_json_value(d3_result.to_payload()),
            "healing_effect": validate_json_value(resolved_effect.to_payload()),
            "pending_request_id": pending_request.request_id,
        },
    )
    return True


def _reanimation_healing_effect(
    *,
    state: GameState,
    army: ArmyDefinition,
    rules_unit: RulesUnitView,
    request_id: str,
    result_id: str,
    selected_option_id: str,
    d3_result: D3RollResult,
) -> HealingEffect:
    source_context = validate_json_value(
        {
            "hook_id": HOOK_ID,
            "effect_kind": REANIMATION_EFFECT_KIND,
            "battle_round": state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "player_id": army.player_id,
            "rules_unit_instance_id": rules_unit.unit_instance_id,
            "selected_option_id": selected_option_id,
            "request_id": request_id,
            "result_id": result_id,
            "d3_result": d3_result.to_payload(),
        }
    )
    return HealingEffect(
        effect_id=(
            f"{HOOK_ID}:{army.player_id}:round-{state.battle_round:02d}:"
            f"{rules_unit.unit_instance_id}:{result_id}"
        ),
        target_unit_instance_id=rules_unit.unit_instance_id,
        amount=d3_result.value,
        opposing_player_id=healing_opposing_player_id(
            state=state,
            player_id=army.player_id,
        ),
        selection_actor_player_id=army.player_id,
        source_rule_id=SOURCE_RULE_ID,
        source_context=source_context,
        phase_start_model_ids=healing_phase_start_model_ids(
            state=state,
            rules_unit=rules_unit,
        ),
        phase_start_enemy_engagement_model_ids=healing_phase_start_enemy_engagement_model_ids(
            state=state,
            rules_unit=rules_unit,
        ),
    )


def _eligible_reanimation_rules_units(
    state: GameState,
    *,
    army: ArmyDefinition,
) -> tuple[RulesUnitView, ...]:
    if type(state) is not GameState:
        raise GameLifecycleError("Reanimation Protocols lookup requires GameState.")
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Reanimation Protocols lookup requires ArmyDefinition.")
    healing_battlefield_state(state)
    rules_units: list[RulesUnitView] = []
    seen: set[str] = set()
    for unit in army.units:
        rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
        if rules_unit.unit_instance_id in seen:
            continue
        seen.add(rules_unit.unit_instance_id)
        if rules_unit.owner_player_id != army.player_id:
            raise GameLifecycleError("Reanimation Protocols rules-unit owner drift.")
        if not _rules_unit_has_necrons_keyword(rules_unit):
            continue
        if not _rules_unit_is_on_battlefield(state=state, rules_unit=rules_unit):
            continue
        rules_units.append(rules_unit)
    return tuple(sorted(rules_units, key=lambda rules_unit: rules_unit.unit_instance_id))


def _reanimation_resolved_for_rules_unit(
    *,
    records: tuple[EventRecord, ...],
    state: GameState,
    player_id: str,
    rules_unit_instance_id: str,
) -> bool:
    return rules_unit_instance_id in _resolved_reanimation_rules_unit_ids(
        records=records,
        state=state,
        player_id=player_id,
    )


def _resolved_reanimation_rules_unit_ids(
    *,
    records: tuple[EventRecord, ...],
    state: GameState,
    player_id: str,
) -> set[str]:
    resolved: set[str] = set()
    for record in records:
        if type(record) is not EventRecord:
            raise GameLifecycleError("Reanimation Protocols event records must be EventRecord.")
        if record.event_type == REANIMATION_RESOLVED_EVENT:
            payload = _event_payload_object(record)
            if _reanimation_event_matches_state(
                payload=payload,
                state=state,
                player_id=player_id,
            ):
                resolved.add(_payload_string(payload, key="rules_unit_instance_id"))
            continue
        if record.event_type != "healing_resolved":
            continue
        payload = _event_payload_object(record)
        effect = payload.get("effect")
        if not isinstance(effect, dict):
            raise GameLifecycleError("Reanimation Protocols healing event missing effect.")
        source_context = effect.get("source_context")
        if not isinstance(source_context, dict) or source_context.get("hook_id") != HOOK_ID:
            continue
        if _reanimation_event_matches_state(
            payload=source_context,
            state=state,
            player_id=player_id,
        ):
            resolved.add(
                _payload_string(
                    effect,
                    key="target_unit_instance_id",
                )
            )
    return resolved


def _reanimation_event_matches_state(
    *,
    payload: dict[str, JsonValue],
    state: GameState,
    player_id: str,
) -> bool:
    return (
        payload.get("hook_id") == HOOK_ID
        and payload.get("player_id") == player_id
        and payload.get("battle_round") == state.battle_round
        and payload.get("phase") == BattlePhase.COMMAND.value
    )


def _emit_reanimation_resolved(
    *,
    context: CommandPhaseStartResultContext,
    player_id: str,
    rules_unit_id: str,
    d3_result: D3RollResult,
    healing_effect: HealingEffect,
) -> None:
    context.decisions.event_log.append(
        REANIMATION_RESOLVED_EVENT,
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "player_id": player_id,
            "rules_unit_instance_id": rules_unit_id,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
            "request_id": context.request.request_id,
            "result_id": context.result.result_id,
            "d3_result": validate_json_value(d3_result.to_payload()),
            "healing_effect": validate_json_value(healing_effect.to_payload()),
        },
    )


def _roll_reanimation_d3(
    *,
    state: GameState,
    decisions: DecisionController,
    rules_unit: RulesUnitView,
) -> D3RollResult:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Reanimation Protocols rolling requires decisions.")
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Reanimation Protocols for {_rules_unit_label(rules_unit)}",
            roll_type=REANIMATION_ROLL_TYPE,
            actor_id=rules_unit.unit_instance_id,
        )
    )
    return D3RollResult.from_source_d6_result(roll_state.original_result)


def _rules_unit_is_on_battlefield(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> bool:
    if not rules_unit.alive_models():
        return False
    placed_model_ids = {
        placement.model_instance_id
        for placement in healing_rules_unit_placements(state=state, rules_unit=rules_unit)
    }
    return any(model.model_instance_id in placed_model_ids for model in rules_unit.alive_models())


def _necrons_army_for_player(state: object, *, player_id: str) -> ArmyDefinition | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Reanimation Protocols army lookup requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    army = state.army_definition_for_player(requested_player_id)
    if army is None:
        return None
    if army.detachment_selection.faction_id == NECRONS_FACTION_ID:
        return army
    if any(_unit_has_necrons_keyword(unit) for unit in army.units):
        return army
    return None


def _rules_unit_has_necrons_keyword(rules_unit: RulesUnitView) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Reanimation Protocols keyword lookup requires rules unit.")
    return _canonical_keyword(NECRONS_FACTION_KEYWORD) in {
        _canonical_keyword(keyword) for keyword in rules_unit.faction_keywords
    }


def _unit_has_necrons_keyword(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Reanimation Protocols keyword lookup requires UnitInstance.")
    return _canonical_keyword(NECRONS_FACTION_KEYWORD) in {
        _canonical_keyword(keyword) for keyword in unit.faction_keywords
    }


def _rules_unit_label(rules_unit: RulesUnitView) -> str:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Reanimation Protocols label requires rules unit.")
    return " + ".join(component.unit.name for component in rules_unit.components)


def _reanimation_option_id(rules_unit_instance_id: str) -> str:
    rules_unit_id = _validate_identifier("rules_unit_instance_id", rules_unit_instance_id)
    return f"necrons:reanimation_protocols:{rules_unit_id}"


_validate_identifier = IdentifierValidator(GameLifecycleError)
