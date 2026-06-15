from __future__ import annotations

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.advance_hooks import (
    AdvanceMoveContext,
    AdvanceMoveGrant,
    AdvanceMoveHookBinding,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import BattleSize
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance

CONTRIBUTION_ID = "warhammer_40000_11th:aeldari:army_rule:scaffold"
HOOK_ID = "warhammer_40000_11th:aeldari:army_rule:star_engines"
SOURCE_RULE_ID = "phase17f:phase17e:aeldari:army-rule"
BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND = "aeldari_battle_focus_token_spent"
STAR_ENGINES_MANEUVER = "star_engines"
AELDARI_FACTION_ID = "aeldari"
ASURYANI = "ASURYANI"
AELDARI = "AELDARI"
VEHICLE = "VEHICLE"
_BATTLE_FOCUS_TOKENS_BY_BATTLE_SIZE = {BattleSize.STRIKE_FORCE: 4}


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        advance_move_hook_bindings=(
            AdvanceMoveHookBinding(
                hook_id=HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=star_engines_advance_grant,
            ),
        ),
    )


def star_engines_advance_grant(context: AdvanceMoveContext) -> AdvanceMoveGrant | None:
    if type(context) is not AdvanceMoveContext:
        raise GameLifecycleError("Aeldari Star Engines requires an AdvanceMoveContext.")
    army = context.state.army_definition_for_player(context.player_id)
    if army is None:
        raise GameLifecycleError("Aeldari Star Engines player army is missing.")
    if army.detachment_selection.faction_id != AELDARI_FACTION_ID:
        return None
    unit = _unit_by_id(context.state, context.unit_instance_id)
    if not _army_contains_unit(army=army, unit=unit):
        raise GameLifecycleError("Aeldari Star Engines unit is not in the acting army.")
    if not _unit_has_keyword(unit, VEHICLE):
        return None
    if not (_unit_has_faction_keyword(unit, ASURYANI) or _unit_has_faction_keyword(unit, AELDARI)):
        return None
    if _battle_focus_tokens_remaining(state=context.state, army=army) <= 0:
        return None
    if _unit_already_performed_agile_manoeuvre_this_phase(context=context, unit=unit):
        return None
    if _star_engines_already_used_this_phase(context=context):
        return None
    return AdvanceMoveGrant(
        hook_id=HOOK_ID,
        source_id=SOURCE_RULE_ID,
        label="Battle Focus: Star Engines",
        granted_ranged_weapon_keywords=(WeaponKeyword.ASSAULT.value,),
        replay_payload={
            "effect_kind": "aeldari_star_engines",
            "unit_instance_id": unit.unit_instance_id,
            "movement_action_request_id": context.movement_request_id,
            "movement_action_result_id": context.movement_result_id,
        },
        decision_effect_payload={
            "effect_kind": BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND,
            "maneuver": STAR_ENGINES_MANEUVER,
            "unit_instance_id": unit.unit_instance_id,
            "battle_focus_token_cost": 1,
            "movement_action_request_id": context.movement_request_id,
            "movement_action_result_id": context.movement_result_id,
        },
    )


def _battle_focus_tokens_remaining(*, state: GameState, army: ArmyDefinition) -> int:
    tokens = _battle_focus_token_count(army)
    spent = sum(
        1
        for effect in _battle_focus_spend_effects(state=state, player_id=army.player_id)
        if effect.started_battle_round == state.battle_round
    )
    return max(0, tokens - spent)


def _battle_focus_token_count(army: ArmyDefinition) -> int:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Aeldari Battle Focus token count requires an ArmyDefinition.")
    token_count = _BATTLE_FOCUS_TOKENS_BY_BATTLE_SIZE.get(army.battle_size)
    if token_count is None:
        raise GameLifecycleError("Aeldari Battle Focus battle size is unsupported.")
    return token_count


def _unit_already_performed_agile_manoeuvre_this_phase(
    *,
    context: AdvanceMoveContext,
    unit: UnitInstance,
) -> bool:
    for effect in _battle_focus_spend_effects(
        state=context.state,
        player_id=context.player_id,
    ):
        if effect.started_battle_round != context.battle_round:
            continue
        if effect.started_phase is not BattlePhaseKind.MOVEMENT:
            continue
        payload = _battle_focus_spend_payload(effect.effect_payload)
        if payload["unit_instance_id"] == unit.unit_instance_id:
            return True
    return False


def _star_engines_already_used_this_phase(*, context: AdvanceMoveContext) -> bool:
    for effect in _battle_focus_spend_effects(
        state=context.state,
        player_id=context.player_id,
    ):
        if effect.started_battle_round != context.battle_round:
            continue
        if effect.started_phase is not BattlePhaseKind.MOVEMENT:
            continue
        payload = _battle_focus_spend_payload(effect.effect_payload)
        if payload["maneuver"] == STAR_ENGINES_MANEUVER:
            return True
    return False


def _battle_focus_spend_effects(
    *, state: GameState, player_id: str
) -> tuple[PersistingEffect, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    effects: list[PersistingEffect] = []
    for effect in state.persisting_effects:
        if effect.owner_player_id != requested_player_id:
            continue
        if effect.source_rule_id != SOURCE_RULE_ID:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Aeldari Battle Focus spend effect payload is malformed.")
        if payload.get("effect_kind") != BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND:
            continue
        _battle_focus_spend_payload(payload)
        effects.append(effect)
    return tuple(sorted(effects, key=lambda effect: effect.effect_id))


def _battle_focus_spend_payload(payload: JsonValue) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Aeldari Battle Focus spend effect payload must be an object.")
    if payload.get("effect_kind") != BATTLE_FOCUS_TOKEN_SPENT_EFFECT_KIND:
        raise GameLifecycleError("Aeldari Battle Focus spend effect kind drift.")
    maneuver = payload.get("maneuver")
    unit_instance_id = payload.get("unit_instance_id")
    if type(maneuver) is not str or type(unit_instance_id) is not str:
        raise GameLifecycleError("Aeldari Battle Focus spend effect payload is incomplete.")
    return {
        "maneuver": _validate_identifier("maneuver", maneuver),
        "unit_instance_id": _validate_identifier("unit_instance_id", unit_instance_id),
    }


def _army_contains_unit(*, army: ArmyDefinition, unit: UnitInstance) -> bool:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Aeldari Star Engines army must be an ArmyDefinition.")
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Aeldari Star Engines unit must be a UnitInstance.")
    return any(stored.unit_instance_id == unit.unit_instance_id for stored in army.units)


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    raise GameLifecycleError("Aeldari Star Engines target unit is unknown.")


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Aeldari Star Engines keyword lookup requires a UnitInstance.")
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.keywords)


def _unit_has_faction_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError(
            "Aeldari Star Engines faction keyword lookup requires a UnitInstance."
        )
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.faction_keywords)


def _canonical_keyword(value: str) -> str:
    return value.strip().replace("_", " ").replace("-", " ").upper()


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Aeldari Star Engines {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Aeldari Star Engines {field_name} must not be empty.")
    return stripped
