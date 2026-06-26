from __future__ import annotations

from warhammer40k_core.core.dice import RerollComponentSelectionPolicy, RerollPermission
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartHookBinding,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    WoundRollModifierBinding,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_effect_payload,
)
from warhammer40k_core.engine.unit_factory import UnitInstance

CONTRIBUTION_ID = "warhammer_40000_11th:space_marines:army_rule:oath_of_moment"
HOOK_ID = "warhammer_40000_11th:space_marines:army_rule:oath_of_moment"
SOURCE_RULE_ID = "phase17f:phase17e:space-marines:army-rule"
SPACE_MARINES_FACTION_ID = "space-marines"
ADEPTUS_ASTARTES_KEYWORD = "ADEPTUS ASTARTES"
OATH_OF_MOMENT_EFFECT_KIND = "space_marines_oath_of_moment_target"
OATH_OF_MOMENT_SELECTION_KIND = "space_marines_oath_of_moment_target_selection"
OATH_HIT_REROLL_EFFECT_KIND = "space_marines_oath_of_moment_hit_reroll"
OATH_WOUND_MODIFIER_ID = f"{HOOK_ID}:wound-roll"
OATH_WOUND_BONUS_EXCLUDED_CHAPTER_KEYWORDS = frozenset(
    {"BLOOD ANGELS", "DARK ANGELS", "DEATHWATCH", "SPACE WOLVES"}
)


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        command_phase_start_hook_bindings=(
            CommandPhaseStartHookBinding(
                hook_id=HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=oath_of_moment_target_request,
                result_handler=apply_oath_of_moment_target_result,
            ),
        ),
        wound_roll_modifier_bindings=(
            WoundRollModifierBinding(
                modifier_id=OATH_WOUND_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=oath_of_moment_wound_roll_modifier,
            ),
        ),
    )


def oath_of_moment_target_request(
    context: CommandPhaseStartRequestContext,
) -> DecisionRequest | None:
    if type(context) is not CommandPhaseStartRequestContext:
        raise GameLifecycleError("Oath of Moment target selection requires request context.")
    army = _space_marines_army_for_player(context.state, player_id=context.active_player_id)
    if army is None:
        return None
    if (
        oath_of_moment_target_unit_id_for_player(context.state, player_id=army.player_id)
        is not None
    ):
        return None
    targets = _eligible_oath_target_units(context.state, player_id=army.player_id)
    if not targets:
        return None
    common_payload = {
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "active_player_id": army.player_id,
        "player_id": army.player_id,
        "faction_id": SPACE_MARINES_FACTION_ID,
        "source_rule_id": SOURCE_RULE_ID,
        "hook_id": HOOK_ID,
        "effect_kind": OATH_OF_MOMENT_EFFECT_KIND,
        "selection_kind": OATH_OF_MOMENT_SELECTION_KIND,
        "eligible_target_unit_instance_ids": [
            target.unit_instance_id for _owner_id, target in targets
        ],
        "expires_at_battle_round": _next_own_turn_battle_round(context.state),
    }
    return DecisionRequest(
        request_id=context.state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
        actor_id=army.player_id,
        payload=validate_json_value(common_payload),
        options=tuple(
            DecisionOption(
                option_id=f"space_marines:oath_of_moment:{target.unit_instance_id}",
                label=f"Oath of Moment: {target.name}",
                payload=validate_json_value(
                    {
                        **common_payload,
                        "target_owner_player_id": owner_id,
                        "target_unit_instance_id": target.unit_instance_id,
                        "target_unit_name": target.name,
                    }
                ),
            )
            for owner_id, target in targets
        ),
    )


def apply_oath_of_moment_target_result(context: CommandPhaseStartResultContext) -> bool:
    if type(context) is not CommandPhaseStartResultContext:
        raise GameLifecycleError("Oath of Moment target selection requires result context.")
    if (
        context.request.decision_type
        != SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
    ):
        return False
    request_payload = _payload_object(context.request.payload)
    if request_payload.get("hook_id") != HOOK_ID:
        return False
    result = context.result
    if result.actor_id is None:
        raise GameLifecycleError("Oath of Moment target selection requires an actor.")
    player_id = result.actor_id
    army = _space_marines_army_for_player(context.state, player_id=player_id)
    if army is None:
        raise GameLifecycleError("Oath of Moment actor does not own Space Marines.")
    if oath_of_moment_target_unit_id_for_player(context.state, player_id=player_id) is not None:
        raise GameLifecycleError("Oath of Moment target is already active.")
    payload = _payload_object(result.payload)
    target_unit_id = _payload_string(payload, key="target_unit_instance_id")
    target_owner_id = _payload_string(payload, key="target_owner_player_id")
    if (
        target_owner_id,
        target_unit_id,
    ) not in {
        (owner_id, unit.unit_instance_id)
        for owner_id, unit in _eligible_oath_target_units(context.state, player_id=player_id)
    }:
        raise GameLifecycleError("Oath of Moment target is no longer eligible.")

    expiration = EffectExpiration.start_turn(
        battle_round=_next_own_turn_battle_round(context.state),
        player_id=player_id,
    )
    target_effect = _oath_target_effect(
        state_battle_round=context.state.battle_round,
        player_id=player_id,
        target_owner_player_id=target_owner_id,
        target_unit_instance_id=target_unit_id,
        selected_option_id=result.selected_option_id,
        request_id=context.request.request_id,
        result_id=result.result_id,
        expiration=expiration,
    )
    context.state.record_persisting_effect(target_effect)

    reroll_effect_ids: list[str] = []
    for attacker_unit in _eligible_oath_attacker_units(army):
        reroll_effect = _oath_hit_reroll_effect(
            state_battle_round=context.state.battle_round,
            player_id=player_id,
            attacker_unit_instance_id=attacker_unit.unit_instance_id,
            target_unit_instance_id=target_unit_id,
            request_id=context.request.request_id,
            result_id=result.result_id,
            expiration=expiration,
        )
        context.state.record_persisting_effect(reroll_effect)
        reroll_effect_ids.append(reroll_effect.effect_id)

    context.decisions.event_log.append(
        "space_marines_oath_of_moment_target_selected",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "player_id": player_id,
            "target_owner_player_id": target_owner_id,
            "target_unit_instance_id": target_unit_id,
            "target_effect_id": target_effect.effect_id,
            "hit_reroll_effect_ids": reroll_effect_ids,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
            "request_id": context.request.request_id,
            "result_id": result.result_id,
        },
    )
    return True


def oath_of_moment_wound_roll_modifier(context: WoundRollModifierContext) -> int:
    if type(context) is not WoundRollModifierContext:
        raise GameLifecycleError("Oath of Moment wound modifier requires context.")
    if context.source_phase not in {BattlePhase.SHOOTING, BattlePhase.FIGHT}:
        return 0
    owner_id, attacking_unit = _unit_owner_and_instance_by_id(
        context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    )
    if owner_id is None or attacking_unit is None:
        raise GameLifecycleError("Oath of Moment attacking unit is unknown.")
    army = _space_marines_army_for_player(context.state, player_id=owner_id)
    if army is None:
        return 0
    if not _unit_has_faction_keyword(attacking_unit, ADEPTUS_ASTARTES_KEYWORD):
        return 0
    if army.detachment_selection.faction_id != SPACE_MARINES_FACTION_ID:
        return 0
    if _army_has_any_faction_keyword(
        army,
        keywords=OATH_WOUND_BONUS_EXCLUDED_CHAPTER_KEYWORDS,
    ):
        return 0
    target_unit_id = oath_of_moment_target_unit_id_for_player(context.state, player_id=owner_id)
    if target_unit_id != context.target_unit_instance_id:
        return 0
    return 1


def oath_of_moment_target_unit_id_for_player(
    state: object,
    *,
    player_id: str,
) -> str | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Oath of Moment target lookup requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    target_unit_ids: list[str] = []
    for effect in state.persisting_effects:
        if effect.owner_player_id != requested_player_id:
            continue
        if effect.source_rule_id != SOURCE_RULE_ID:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") != OATH_OF_MOMENT_EFFECT_KIND:
            continue
        target_unit_ids.extend(effect.target_unit_instance_ids)
    if len(target_unit_ids) > 1:
        raise GameLifecycleError("Multiple Oath of Moment targets are active.")
    return target_unit_ids[0] if target_unit_ids else None


def _oath_target_effect(
    *,
    state_battle_round: int,
    player_id: str,
    target_owner_player_id: str,
    target_unit_instance_id: str,
    selected_option_id: str,
    request_id: str,
    result_id: str,
    expiration: EffectExpiration,
) -> PersistingEffect:
    return PersistingEffect(
        effect_id=f"{HOOK_ID}:{player_id}:round-{state_battle_round:02d}:target",
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=player_id,
        target_unit_instance_ids=(target_unit_instance_id,),
        started_battle_round=state_battle_round,
        started_phase=BattlePhaseKind.COMMAND,
        expiration=expiration,
        effect_payload=validate_json_value(
            {
                "effect_kind": OATH_OF_MOMENT_EFFECT_KIND,
                "battle_round": state_battle_round,
                "phase": BattlePhase.COMMAND.value,
                "player_id": player_id,
                "target_owner_player_id": target_owner_player_id,
                "target_unit_instance_id": target_unit_instance_id,
                "selected_option_id": selected_option_id,
                "request_id": request_id,
                "result_id": result_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
            }
        ),
    )


def _oath_hit_reroll_effect(
    *,
    state_battle_round: int,
    player_id: str,
    attacker_unit_instance_id: str,
    target_unit_instance_id: str,
    request_id: str,
    result_id: str,
    expiration: EffectExpiration,
) -> PersistingEffect:
    permission = RerollPermission(
        source_id=(
            f"{SOURCE_RULE_ID}:hit-reroll:round-{state_battle_round:02d}:"
            f"{attacker_unit_instance_id}:{target_unit_instance_id}"
        ),
        timing_window="attack_sequence.hit",
        owning_player_id=player_id,
        eligible_roll_type="attack_sequence.hit",
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    return PersistingEffect(
        effect_id=(
            f"{HOOK_ID}:{player_id}:round-{state_battle_round:02d}:"
            f"{attacker_unit_instance_id}:hit-reroll"
        ),
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=player_id,
        target_unit_instance_ids=(attacker_unit_instance_id,),
        started_battle_round=state_battle_round,
        started_phase=BattlePhaseKind.COMMAND,
        expiration=expiration,
        effect_payload=source_backed_reroll_permission_effect_payload(
            target_unit_instance_ids=(attacker_unit_instance_id,),
            permission=permission,
            source_payload={
                "effect_kind": OATH_HIT_REROLL_EFFECT_KIND,
                "player_id": player_id,
                "target_unit_instance_id": target_unit_instance_id,
                "battle_round": state_battle_round,
                "phase": BattlePhase.COMMAND.value,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "request_id": request_id,
                "result_id": result_id,
            },
        ),
    )


def _eligible_oath_target_units(
    state: object,
    *,
    player_id: str,
) -> tuple[tuple[str, UnitInstance], ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Oath of Moment target lookup requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    targets: list[tuple[str, UnitInstance]] = []
    for army in state.army_definitions:
        if army.player_id == requested_player_id:
            continue
        for unit in army.units:
            if unit.alive_own_models():
                targets.append((army.player_id, unit))
    return tuple(sorted(targets, key=lambda item: (item[0], item[1].unit_instance_id)))


def _eligible_oath_attacker_units(army: ArmyDefinition) -> tuple[UnitInstance, ...]:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Oath of Moment attacker lookup requires ArmyDefinition.")
    return tuple(
        unit
        for unit in army.units
        if _unit_has_faction_keyword(unit, ADEPTUS_ASTARTES_KEYWORD) and unit.alive_own_models()
    )


def _space_marines_army_for_player(
    state: object,
    *,
    player_id: str,
) -> ArmyDefinition | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Oath of Moment army lookup requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    army = state.army_definition_for_player(requested_player_id)
    if army is None:
        return None
    if army.detachment_selection.faction_id == SPACE_MARINES_FACTION_ID:
        return army
    if any(_unit_has_faction_keyword(unit, ADEPTUS_ASTARTES_KEYWORD) for unit in army.units):
        return army
    return None


def _unit_owner_and_instance_by_id(
    state: object,
    *,
    unit_instance_id: str,
) -> tuple[str | None, UnitInstance | None]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Oath of Moment unit lookup requires GameState.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return army.player_id, unit
    return None, None


def _unit_has_faction_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Oath of Moment keyword lookup requires UnitInstance.")
    requested_keyword = _canonical_keyword(keyword)
    return requested_keyword in {
        _canonical_keyword(stored_keyword) for stored_keyword in unit.faction_keywords
    }


def _army_has_any_faction_keyword(
    army: ArmyDefinition,
    *,
    keywords: frozenset[str],
) -> bool:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Oath of Moment army keyword lookup requires ArmyDefinition.")
    requested_keywords = {_canonical_keyword(keyword) for keyword in keywords}
    return any(
        requested_keywords.intersection(
            {_canonical_keyword(stored_keyword) for stored_keyword in unit.faction_keywords}
        )
        for unit in army.units
    )


def _next_own_turn_battle_round(state: object) -> int:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Oath of Moment expiration lookup requires GameState.")
    if state.battle_round < 1:
        raise GameLifecycleError("Oath of Moment requires an active battle round.")
    return state.battle_round + 1


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Oath of Moment payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Oath of Moment payload missing required key: {key}.")
    value = payload[key]
    return _validate_identifier(key, value)


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Oath of Moment {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Oath of Moment {field_name} must not be empty.")
    return stripped


def _canonical_keyword(keyword: str) -> str:
    return _validate_identifier("keyword", keyword).upper().replace("_", " ")
