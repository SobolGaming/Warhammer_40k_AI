from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import AttackProfile, RangeProfileKind, WeaponProfile
from warhammer40k_core.engine.advance_eligibility_hooks import (
    AdvanceEligibilityContext,
    AdvanceEligibilityGrant,
    AdvanceEligibilityHookBinding,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartHookBinding,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.common import (
    payload_object as _payload_object,
)
from warhammer40k_core.engine.faction_content.common import (
    payload_string as _payload_string,
)
from warhammer40k_core.engine.faction_rule_states import FactionRuleState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, SetupStep
from warhammer40k_core.engine.runtime_modifiers import (
    SaveOptionModifierBinding,
    SaveOptionModifierContext,
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, SaveOption
from warhammer40k_core.engine.unit_factory import UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

CONTRIBUTION_ID = "warhammer_40000_11th:orks:army_rule:waaagh"
HOOK_ID = "warhammer_40000_11th:orks:army_rule:waaagh"
ADVANCE_ELIGIBILITY_HOOK_ID = f"{HOOK_ID}:advance-eligibility"
WEAPON_PROFILE_MODIFIER_ID = f"{HOOK_ID}:weapon-profile"
SAVE_OPTION_MODIFIER_ID = f"{HOOK_ID}:invulnerable-save"
SOURCE_RULE_ID = "phase17f:phase17e:orks:army-rule"
ORKS_FACTION_ID = "orks"
ORKS_FACTION_KEYWORD = "ORKS"
WAAAGH_EFFECT_KIND = "orks_waaagh_active"
WAAAGH_CALL_STATE_KIND = "orks_waaagh_called"
WAAAGH_DECLINE_STATE_KIND = "orks_waaagh_declined_command_phase"
WAAAGH_SELECTION_KIND = "orks_waaagh_call"
WAAAGH_CALL_OPTION_ID = "orks:waaagh:call"
WAAAGH_DECLINE_OPTION_ID = "orks:waaagh:decline"
WAAAGH_RULE_UPDATE_SOURCE = (
    "warhammer_40000_11th:orks:faction_pack:rules_updates:waaagh_first_paragraph"
)


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        command_phase_start_hook_bindings=(
            CommandPhaseStartHookBinding(
                hook_id=HOOK_ID,
                source_id=SOURCE_RULE_ID,
                request_handler=waaagh_call_request,
                result_handler=apply_waaagh_call_result,
            ),
        ),
        advance_eligibility_hook_bindings=(
            AdvanceEligibilityHookBinding(
                hook_id=ADVANCE_ELIGIBILITY_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=waaagh_advance_eligibility,
            ),
        ),
        weapon_profile_modifier_bindings=(
            WeaponProfileModifierBinding(
                modifier_id=WEAPON_PROFILE_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=waaagh_weapon_profile_modifier,
            ),
        ),
        save_option_modifier_bindings=(
            SaveOptionModifierBinding(
                modifier_id=SAVE_OPTION_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=waaagh_save_option_modifier,
            ),
        ),
    )


def waaagh_call_request(context: CommandPhaseStartRequestContext) -> DecisionRequest | None:
    if type(context) is not CommandPhaseStartRequestContext:
        raise GameLifecycleError("Waaagh! call requires request context.")
    army = _orks_army_for_player(context.state, player_id=context.active_player_id)
    if army is None:
        return None
    if waaagh_called_for_player(context.state, player_id=army.player_id):
        return None
    if _waaagh_declined_this_command_phase(context.state, player_id=army.player_id):
        return None
    target_unit_ids = _eligible_waaagh_unit_ids_for_army(army)
    if not target_unit_ids:
        return None

    common_payload = {
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "active_player_id": army.player_id,
        "player_id": army.player_id,
        "faction_id": ORKS_FACTION_ID,
        "source_rule_id": SOURCE_RULE_ID,
        "hook_id": HOOK_ID,
        "effect_kind": WAAAGH_EFFECT_KIND,
        "selection_kind": WAAAGH_SELECTION_KIND,
        "eligible_target_unit_instance_ids": list(target_unit_ids),
        "expires_at_battle_round": _next_own_turn_battle_round(context.state),
        "rules_update_source": WAAAGH_RULE_UPDATE_SOURCE,
    }
    return DecisionRequest(
        request_id=context.state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
        actor_id=army.player_id,
        payload=validate_json_value(common_payload),
        options=(
            DecisionOption(
                option_id=WAAAGH_CALL_OPTION_ID,
                label="Call Waaagh!",
                payload=validate_json_value(
                    {
                        **common_payload,
                        "submission_kind": WAAAGH_SELECTION_KIND,
                        "selected_waaagh_option": "call",
                    }
                ),
            ),
            DecisionOption(
                option_id=WAAAGH_DECLINE_OPTION_ID,
                label="Do not call Waaagh!",
                payload=validate_json_value(
                    {
                        **common_payload,
                        "submission_kind": WAAAGH_SELECTION_KIND,
                        "selected_waaagh_option": "decline",
                    }
                ),
            ),
        ),
    )


def apply_waaagh_call_result(context: CommandPhaseStartResultContext) -> bool:
    if type(context) is not CommandPhaseStartResultContext:
        raise GameLifecycleError("Waaagh! call requires result context.")
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
        raise GameLifecycleError("Waaagh! call requires an actor.")
    player_id = result.actor_id
    army = _orks_army_for_player(context.state, player_id=player_id)
    if army is None:
        raise GameLifecycleError("Waaagh! actor does not own Orks.")
    if waaagh_called_for_player(context.state, player_id=player_id):
        raise GameLifecycleError("Waaagh! has already been called this battle.")
    if _waaagh_declined_this_command_phase(context.state, player_id=player_id):
        raise GameLifecycleError("Waaagh! has already been declined this Command phase.")

    payload = _payload_object(result.payload)
    selection = _payload_string(payload, key="selected_waaagh_option")
    target_unit_ids = _eligible_waaagh_unit_ids_for_army(army)
    if not target_unit_ids:
        raise GameLifecycleError("Waaagh! call has no eligible units.")
    if selection == "decline":
        _record_waaagh_decline(context, player_id=player_id)
        return True
    if selection != "call":
        raise GameLifecycleError("Waaagh! selection is unsupported.")
    if result.selected_option_id != WAAAGH_CALL_OPTION_ID:
        raise GameLifecycleError("Waaagh! call option ID drift.")

    call_state = _waaagh_call_state(
        context=context,
        player_id=player_id,
        target_unit_ids=target_unit_ids,
    )
    context.state.record_faction_rule_state(call_state)
    effect = _waaagh_active_effect(
        context=context,
        player_id=player_id,
        target_unit_ids=target_unit_ids,
    )
    context.state.record_persisting_effect(effect)
    context.decisions.event_log.append(
        "orks_waaagh_called",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "player_id": player_id,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
            "target_unit_instance_ids": list(target_unit_ids),
            "faction_rule_state": validate_json_value(call_state.to_payload()),
            "persisting_effect": validate_json_value(effect.to_payload()),
        },
    )
    return True


def waaagh_called_for_player(state: GameState, *, player_id: str) -> bool:
    _validate_game_state(state)
    requested_player_id = _validate_identifier("player_id", player_id)
    states = tuple(
        state_record
        for state_record in state.faction_rule_states_for_player(
            player_id=requested_player_id,
            state_kind=WAAAGH_CALL_STATE_KIND,
        )
        if state_record.source_rule_id == SOURCE_RULE_ID
    )
    if len(states) > 1:
        raise GameLifecycleError("Waaagh! lookup found multiple call states.")
    return bool(states)


def waaagh_active_for_player(state: GameState, *, player_id: str) -> bool:
    _validate_game_state(state)
    return bool(_active_waaagh_effects_for_player(state, player_id=player_id))


def waaagh_is_active_for_unit(state: GameState, *, unit_instance_id: str) -> bool:
    _validate_game_state(state)
    unit, army = _unit_and_army_by_id(state, unit_instance_id=unit_instance_id)
    if not _unit_has_waaagh(unit):
        return False
    return bool(
        _active_waaagh_effects_for_player(state, player_id=army.player_id)
        or _active_generic_waaagh_effects_for_unit(state, unit_instance_id=unit_instance_id)
    )


def waaagh_advance_eligibility(
    context: AdvanceEligibilityContext,
) -> AdvanceEligibilityGrant | None:
    if type(context) is not AdvanceEligibilityContext:
        raise GameLifecycleError("Waaagh! advance eligibility requires context.")
    unit, army = _unit_and_army_by_id(context.state, unit_instance_id=context.unit_instance_id)
    if army.player_id != context.player_id:
        raise GameLifecycleError("Waaagh! advance eligibility player drift.")
    if not _unit_has_waaagh(unit):
        return None
    if not waaagh_active_for_player(context.state, player_id=army.player_id):
        return None
    return AdvanceEligibilityGrant(
        hook_id=ADVANCE_ELIGIBILITY_HOOK_ID,
        source_id=SOURCE_RULE_ID,
        can_shoot=False,
        can_declare_charge=True,
        replay_payload={
            "effect_kind": WAAAGH_EFFECT_KIND,
            "player_id": army.player_id,
            "battle_round": context.battle_round,
            "unit_instance_id": context.unit_instance_id,
            "movement_request_id": context.movement_request_id,
            "movement_result_id": context.movement_result_id,
            "can_declare_charge_after_advance": True,
        },
    )


def waaagh_weapon_profile_modifier(context: WeaponProfileModifierContext) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Waaagh! weapon profile modifier requires context.")
    if context.source_phase is not BattlePhase.FIGHT:
        return context.weapon_profile
    if context.weapon_profile.range_profile.kind is not RangeProfileKind.MELEE:
        return context.weapon_profile
    if not waaagh_is_active_for_unit(
        context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    ):
        return context.weapon_profile
    return replace(
        context.weapon_profile,
        attack_profile=_attack_profile_with_plus_one(context.weapon_profile.attack_profile),
        strength=_strength_with_plus_one(context.weapon_profile.strength),
        source_ids=_source_ids_with_waaagh(context.weapon_profile.source_ids),
    )


def waaagh_save_option_modifier(context: SaveOptionModifierContext) -> tuple[SaveOption, ...]:
    if type(context) is not SaveOptionModifierContext:
        raise GameLifecycleError("Waaagh! save option modifier requires context.")
    if not waaagh_is_active_for_unit(
        context.state,
        unit_instance_id=context.target_unit_instance_id,
    ):
        return context.save_options

    invulnerable = [
        option for option in context.save_options if option.save_kind is SaveKind.INVULNERABLE
    ]
    if not invulnerable:
        return (
            *context.save_options,
            SaveOption(
                save_kind=SaveKind.INVULNERABLE,
                target_number=5,
                characteristic_target_number=5,
                armor_penetration=0,
                source_rule_ids=(SOURCE_RULE_ID,),
            ),
        )
    if len(invulnerable) > 1:
        raise GameLifecycleError("Waaagh! save option lookup found multiple invulnerable saves.")

    existing = invulnerable[0]
    if existing.target_number <= 5 and existing.characteristic_target_number <= 5:
        return context.save_options
    improved = replace(
        existing,
        target_number=5,
        characteristic_target_number=5,
        source_rule_ids=_source_ids_with_waaagh(existing.source_rule_ids),
    )
    return tuple(
        improved if option.save_kind is SaveKind.INVULNERABLE else option
        for option in context.save_options
    )


def _record_waaagh_decline(
    context: CommandPhaseStartResultContext,
    *,
    player_id: str,
) -> None:
    if context.result.selected_option_id != WAAAGH_DECLINE_OPTION_ID:
        raise GameLifecycleError("Waaagh! decline option ID drift.")
    state_record = FactionRuleState(
        state_id=f"{HOOK_ID}:{player_id}:round-{context.state.battle_round:02d}:declined",
        player_id=player_id,
        faction_id=ORKS_FACTION_ID,
        source_rule_id=SOURCE_RULE_ID,
        state_kind=WAAAGH_DECLINE_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=context.request.request_id,
        result_id=context.result.result_id,
        payload=validate_json_value(
            {
                "selection_kind": WAAAGH_SELECTION_KIND,
                "selected_waaagh_option": "decline",
                "selected_option_id": context.result.selected_option_id,
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "player_id": player_id,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
            }
        ),
    )
    context.state.record_faction_rule_state(state_record)
    context.decisions.event_log.append(
        "orks_waaagh_declined",
        {
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "player_id": player_id,
            "source_rule_id": SOURCE_RULE_ID,
            "hook_id": HOOK_ID,
            "faction_rule_state": validate_json_value(state_record.to_payload()),
        },
    )


def _waaagh_call_state(
    *,
    context: CommandPhaseStartResultContext,
    player_id: str,
    target_unit_ids: tuple[str, ...],
) -> FactionRuleState:
    return FactionRuleState(
        state_id=f"{HOOK_ID}:{player_id}:called",
        player_id=player_id,
        faction_id=ORKS_FACTION_ID,
        source_rule_id=SOURCE_RULE_ID,
        state_kind=WAAAGH_CALL_STATE_KIND,
        setup_step=SetupStep.DECLARE_BATTLE_FORMATIONS,
        request_id=context.request.request_id,
        result_id=context.result.result_id,
        payload=validate_json_value(
            {
                "selection_kind": WAAAGH_SELECTION_KIND,
                "selected_waaagh_option": "call",
                "selected_option_id": context.result.selected_option_id,
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "player_id": player_id,
                "faction_id": ORKS_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "effect_kind": WAAAGH_EFFECT_KIND,
                "target_unit_instance_ids": list(target_unit_ids),
                "rules_update_source": WAAAGH_RULE_UPDATE_SOURCE,
            }
        ),
    )


def _waaagh_active_effect(
    *,
    context: CommandPhaseStartResultContext,
    player_id: str,
    target_unit_ids: tuple[str, ...],
) -> PersistingEffect:
    expiration = EffectExpiration.start_turn(
        battle_round=_next_own_turn_battle_round(context.state),
        player_id=player_id,
    )
    return PersistingEffect(
        effect_id=f"{HOOK_ID}:{player_id}:round-{context.state.battle_round:02d}:active",
        source_rule_id=SOURCE_RULE_ID,
        owner_player_id=player_id,
        target_unit_instance_ids=target_unit_ids,
        started_battle_round=context.state.battle_round,
        started_phase=BattlePhaseKind.COMMAND,
        expiration=expiration,
        effect_payload=validate_json_value(
            {
                "effect_kind": WAAAGH_EFFECT_KIND,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "player_id": player_id,
                "faction_id": ORKS_FACTION_ID,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": HOOK_ID,
                "selected_option_id": context.result.selected_option_id,
                "request_id": context.request.request_id,
                "result_id": context.result.result_id,
                "target_unit_instance_ids": list(target_unit_ids),
                "expires_at": expiration.to_payload(),
                "rules_update_source": WAAAGH_RULE_UPDATE_SOURCE,
            }
        ),
    )


def _active_waaagh_effects_for_player(
    state: GameState,
    *,
    player_id: str,
) -> tuple[PersistingEffect, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    matching: list[PersistingEffect] = []
    for effect in state.persisting_effects:
        if effect.owner_player_id != requested_player_id:
            continue
        if effect.source_rule_id != SOURCE_RULE_ID:
            continue
        payload = _payload_object(effect.effect_payload)
        if payload.get("effect_kind") != WAAAGH_EFFECT_KIND:
            continue
        matching.append(effect)
    if len(matching) > 1:
        raise GameLifecycleError("Waaagh! lookup found multiple active effects.")
    return tuple(matching)


def _active_generic_waaagh_effects_for_unit(
    state: GameState,
    *,
    unit_instance_id: str,
) -> tuple[PersistingEffect, ...]:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    matching: list[PersistingEffect] = []
    for effect in state.persisting_effects_for_unit(requested_unit_id):
        payload = _payload_object(effect.effect_payload)
        if payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
            continue
        effect_payload = payload.get("effect")
        if not isinstance(effect_payload, dict):
            raise GameLifecycleError("Generic Waaagh! payload must include effect object.")
        if effect_payload.get("kind") != "set_contextual_status":
            continue
        if _generic_status_parameter(effect_payload) == WAAAGH_EFFECT_KIND:
            matching.append(effect)
    return tuple(sorted(matching, key=lambda stored: stored.effect_id))


def _generic_status_parameter(effect_payload: dict[str, JsonValue]) -> str | None:
    raw_parameters = effect_payload.get("parameters")
    if not isinstance(raw_parameters, list):
        raise GameLifecycleError("Generic Waaagh! effect parameters must be a list.")
    status: str | None = None
    for raw_parameter in raw_parameters:
        if not isinstance(raw_parameter, dict):
            raise GameLifecycleError("Generic Waaagh! parameter must be an object.")
        key = raw_parameter.get("key")
        if key != "status":
            continue
        if status is not None:
            raise GameLifecycleError("Generic Waaagh! status parameter is duplicated.")
        value = raw_parameter.get("value")
        if type(value) is not str:
            raise GameLifecycleError("Generic Waaagh! status parameter must be a string.")
        status = value
    return status


def _waaagh_declined_this_command_phase(state: GameState, *, player_id: str) -> bool:
    requested_player_id = _validate_identifier("player_id", player_id)
    states = tuple(
        state_record
        for state_record in state.faction_rule_states_for_player(
            player_id=requested_player_id,
            state_kind=WAAAGH_DECLINE_STATE_KIND,
        )
        if _decline_state_matches_current_command_phase(state, state_record)
    )
    if len(states) > 1:
        raise GameLifecycleError("Waaagh! lookup found multiple decline states.")
    return bool(states)


def _decline_state_matches_current_command_phase(
    state: GameState,
    state_record: FactionRuleState,
) -> bool:
    payload = _payload_object(state_record.payload)
    return (
        state_record.source_rule_id == SOURCE_RULE_ID
        and payload.get("battle_round") == state.battle_round
        and payload.get("phase") == BattlePhase.COMMAND.value
        and payload.get("selected_waaagh_option") == "decline"
    )


def _eligible_waaagh_unit_ids_for_army(army: ArmyDefinition) -> tuple[str, ...]:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Waaagh! requires an ArmyDefinition.")
    return tuple(unit.unit_instance_id for unit in army.units if _unit_has_waaagh(unit))


def _unit_has_waaagh(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Waaagh! requires a UnitInstance.")
    if _unit_has_keyword_token(unit.faction_keywords, ORKS_FACTION_KEYWORD):
        return True
    return any(ability.source_id == SOURCE_RULE_ID for ability in unit.datasheet_abilities)


def _orks_armies(state: GameState) -> tuple[ArmyDefinition, ...]:
    _validate_game_state(state)
    return tuple(
        army
        for army in state.army_definitions
        if army.detachment_selection.faction_id == ORKS_FACTION_ID
    )


def _orks_army_for_player(state: GameState, *, player_id: str) -> ArmyDefinition | None:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in _orks_armies(state):
        if army.player_id == requested_player_id:
            return army
    return None


def _unit_and_army_by_id(
    state: GameState,
    *,
    unit_instance_id: str,
) -> tuple[UnitInstance, ArmyDefinition]:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit, army
    raise GameLifecycleError("Waaagh! unit_instance_id was not found.")


def _attack_profile_with_plus_one(profile: AttackProfile) -> AttackProfile:
    if type(profile) is not AttackProfile:
        raise GameLifecycleError("Waaagh! attack profile requires AttackProfile.")
    if profile.fixed_attacks is not None:
        return AttackProfile.fixed(profile.fixed_attacks + 1)
    expression = profile.dice_expression
    if expression is None:
        raise GameLifecycleError("Waaagh! attack profile is missing a dice expression.")
    return AttackProfile.dice(
        DiceExpression(
            quantity=expression.quantity,
            sides=expression.sides,
            modifier=expression.modifier + 1,
        )
    )


def _strength_with_plus_one(strength: CharacteristicValue) -> CharacteristicValue:
    if type(strength) is not CharacteristicValue:
        raise GameLifecycleError("Waaagh! strength requires CharacteristicValue.")
    if strength.characteristic is not Characteristic.STRENGTH:
        raise GameLifecycleError("Waaagh! strength characteristic drift.")
    if not strength.is_numeric:
        raise GameLifecycleError("Waaagh! cannot modify non-numeric Strength.")
    return CharacteristicValue.from_raw(Characteristic.STRENGTH, strength.final + 1)


def _source_ids_with_waaagh(source_ids: tuple[str, ...]) -> tuple[str, ...]:
    if type(source_ids) is not tuple:
        raise GameLifecycleError("Waaagh! source IDs must be a tuple.")
    if SOURCE_RULE_ID in source_ids:
        return source_ids
    return (*source_ids, SOURCE_RULE_ID)


def _unit_has_keyword_token(values: tuple[str, ...], expected: str) -> bool:
    if type(values) is not tuple:
        raise GameLifecycleError("Waaagh! keyword values must be a tuple.")
    return _validate_identifier("keyword", expected) in values


def _next_own_turn_battle_round(state: GameState) -> int:
    _validate_game_state(state)
    return state.battle_round + 1


def _validate_game_state(state: object) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Waaagh! requires GameState.")


_validate_identifier = IdentifierValidator(GameLifecycleError)
