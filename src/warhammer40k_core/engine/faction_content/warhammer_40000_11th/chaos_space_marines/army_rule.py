from __future__ import annotations

from dataclasses import replace
from enum import StrEnum
from typing import cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.faction_aliases import (
    CHAOS_SPACE_MARINES_FACTION_ID,
    faction_reference_matches,
)
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    AttackSequenceCompletedHookBinding,
)
from warhammer40k_core.engine.damage_allocation import apply_mortal_wounds_to_unit
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
    FightUnitSelectedGrantBinding,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    UnitCharacteristicModifierContext,
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    ShootingUnitSelectedContext,
    ShootingUnitSelectedGrant,
    ShootingUnitSelectedGrantBinding,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_space_marines:army_rule:scaffold"
SOURCE_RULE_ID = "phase17f:phase17e:chaos-space-marines:army-rule"
HOOK_ID = "warhammer_40000_11th:chaos_space_marines:army_rule:dark_pacts"
DARK_PACT_EFFECT_KIND = "chaos_space_marines_dark_pact"
DARK_PACTS_ABILITY_NAME = "Dark Pacts"
DARK_PACT_LEADERSHIP_ROLL_TYPE = "chaos_space_marines.dark_pact_leadership_test"
DARK_PACT_MORTAL_WOUNDS_ROLL_TYPE = "chaos_space_marines.dark_pact_mortal_wounds"

SHOOTING_LETHAL_HITS_HOOK_ID = f"{HOOK_ID}:shooting:lethal_hits"
SHOOTING_SUSTAINED_HITS_HOOK_ID = f"{HOOK_ID}:shooting:sustained_hits_1"
FIGHT_LETHAL_HITS_HOOK_ID = f"{HOOK_ID}:fight:lethal_hits"
FIGHT_SUSTAINED_HITS_HOOK_ID = f"{HOOK_ID}:fight:sustained_hits_1"
ATTACK_SEQUENCE_COMPLETED_HOOK_ID = f"{HOOK_ID}:attack_sequence_completed"
WEAPON_PROFILE_MODIFIER_ID = f"{HOOK_ID}:weapon_profile_modifier"


class DarkPactKind(StrEnum):
    LETHAL_HITS = "lethal_hits"
    SUSTAINED_HITS_1 = "sustained_hits_1"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        shooting_unit_selected_grant_hook_bindings=(
            ShootingUnitSelectedGrantBinding(
                hook_id=SHOOTING_LETHAL_HITS_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=shooting_lethal_hits_dark_pact_grant,
            ),
            ShootingUnitSelectedGrantBinding(
                hook_id=SHOOTING_SUSTAINED_HITS_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=shooting_sustained_hits_dark_pact_grant,
            ),
        ),
        fight_unit_selected_grant_hook_bindings=(
            FightUnitSelectedGrantBinding(
                hook_id=FIGHT_LETHAL_HITS_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=fight_lethal_hits_dark_pact_grant,
            ),
            FightUnitSelectedGrantBinding(
                hook_id=FIGHT_SUSTAINED_HITS_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=fight_sustained_hits_dark_pact_grant,
            ),
        ),
        attack_sequence_completed_hook_bindings=(
            AttackSequenceCompletedHookBinding(
                hook_id=ATTACK_SEQUENCE_COMPLETED_HOOK_ID,
                source_id=SOURCE_RULE_ID,
                handler=resolve_dark_pact_attack_sequence_completion,
            ),
        ),
        weapon_profile_modifier_bindings=(
            WeaponProfileModifierBinding(
                modifier_id=WEAPON_PROFILE_MODIFIER_ID,
                source_id=SOURCE_RULE_ID,
                handler=dark_pact_weapon_profile_modifier,
            ),
        ),
    )


def shooting_lethal_hits_dark_pact_grant(
    context: ShootingUnitSelectedContext,
) -> ShootingUnitSelectedGrant | None:
    return _shooting_dark_pact_grant(
        context,
        hook_id=SHOOTING_LETHAL_HITS_HOOK_ID,
        pact=DarkPactKind.LETHAL_HITS,
        label="Dark Pacts: Lethal Hits",
    )


def shooting_sustained_hits_dark_pact_grant(
    context: ShootingUnitSelectedContext,
) -> ShootingUnitSelectedGrant | None:
    return _shooting_dark_pact_grant(
        context,
        hook_id=SHOOTING_SUSTAINED_HITS_HOOK_ID,
        pact=DarkPactKind.SUSTAINED_HITS_1,
        label="Dark Pacts: Sustained Hits 1",
    )


def fight_lethal_hits_dark_pact_grant(
    context: FightUnitSelectedContext,
) -> FightUnitSelectedGrant | None:
    return _fight_dark_pact_grant(
        context,
        hook_id=FIGHT_LETHAL_HITS_HOOK_ID,
        pact=DarkPactKind.LETHAL_HITS,
        label="Dark Pacts: Lethal Hits",
    )


def fight_sustained_hits_dark_pact_grant(
    context: FightUnitSelectedContext,
) -> FightUnitSelectedGrant | None:
    return _fight_dark_pact_grant(
        context,
        hook_id=FIGHT_SUSTAINED_HITS_HOOK_ID,
        pact=DarkPactKind.SUSTAINED_HITS_1,
        label="Dark Pacts: Sustained Hits 1",
    )


def _shooting_dark_pact_grant(
    context: ShootingUnitSelectedContext,
    *,
    hook_id: str,
    pact: DarkPactKind,
    label: str,
) -> ShootingUnitSelectedGrant | None:
    if type(context) is not ShootingUnitSelectedContext:
        raise GameLifecycleError("Dark Pacts shooting grant requires selected unit context.")
    if not _dark_pacts_available(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
        phase=BattlePhase.SHOOTING,
    ):
        return None
    target_unit_ids = dark_pact_target_unit_ids(
        context.state,
        unit_instance_id=context.unit_instance_id,
    )
    return ShootingUnitSelectedGrant(
        hook_id=hook_id,
        source_id=SOURCE_RULE_ID,
        label=label,
        replay_payload={
            "effect_kind": DARK_PACT_EFFECT_KIND,
            "selected_dark_pact": pact.value,
            "trigger": "selected_to_shoot",
            "unit_instance_id": context.unit_instance_id,
            "selection_request_id": context.request_id,
            "selection_result_id": context.result_id,
        },
        unit_effect_payload=dark_pact_effect_payload(
            unit_instance_id=context.unit_instance_id,
            target_unit_instance_ids=target_unit_ids,
            trigger="selected_to_shoot",
            phase=BattlePhase.SHOOTING,
            selected_dark_pact=pact,
            source_context={
                "selection_request_id": context.request_id,
                "selection_result_id": context.result_id,
            },
        ),
        unit_effect_expiration="end_phase",
    )


def _fight_dark_pact_grant(
    context: FightUnitSelectedContext,
    *,
    hook_id: str,
    pact: DarkPactKind,
    label: str,
) -> FightUnitSelectedGrant | None:
    if type(context) is not FightUnitSelectedContext:
        raise GameLifecycleError("Dark Pacts fight grant requires selected unit context.")
    if not _dark_pacts_available(
        state=context.state,
        player_id=context.player_id,
        unit_instance_id=context.unit_instance_id,
        phase=BattlePhase.FIGHT,
    ):
        return None
    target_unit_ids = dark_pact_target_unit_ids(
        context.state,
        unit_instance_id=context.unit_instance_id,
    )
    return FightUnitSelectedGrant(
        hook_id=hook_id,
        source_id=SOURCE_RULE_ID,
        label=label,
        replay_payload={
            "effect_kind": DARK_PACT_EFFECT_KIND,
            "selected_dark_pact": pact.value,
            "trigger": "selected_to_fight",
            "unit_instance_id": context.unit_instance_id,
            "activation_request_id": context.request_id,
            "activation_result_id": context.result_id,
            "fight_type": context.fight_type,
            "ordering_band": context.ordering_band,
        },
        unit_effect_payload=dark_pact_effect_payload(
            unit_instance_id=context.unit_instance_id,
            target_unit_instance_ids=target_unit_ids,
            trigger="selected_to_fight",
            phase=BattlePhase.FIGHT,
            selected_dark_pact=pact,
            source_context={
                "activation_request_id": context.request_id,
                "activation_result_id": context.result_id,
                "fight_type": context.fight_type,
                "ordering_band": context.ordering_band,
            },
        ),
        unit_effect_expiration="end_phase",
    )


def dark_pact_effect_payload(
    *,
    unit_instance_id: str,
    target_unit_instance_ids: tuple[str, ...],
    trigger: str,
    phase: BattlePhase,
    selected_dark_pact: DarkPactKind,
    source_context: JsonValue,
) -> JsonValue:
    return validate_json_value(
        {
            "effect_kind": DARK_PACT_EFFECT_KIND,
            "unit_instance_id": _validate_identifier("unit_instance_id", unit_instance_id),
            "target_unit_instance_ids": list(
                _validate_identifier_tuple(
                    "target_unit_instance_ids",
                    target_unit_instance_ids,
                )
            ),
            "trigger": _validate_identifier("trigger", trigger),
            "phase": _battle_phase_from_token(phase).value,
            "selected_dark_pact": _dark_pact_kind_from_token(selected_dark_pact).value,
            "source_context": validate_json_value(source_context),
        }
    )


def dark_pact_weapon_profile_modifier(
    context: WeaponProfileModifierContext,
) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Dark Pacts weapon profile modifier requires context.")
    if context.source_phase not in (BattlePhase.SHOOTING, BattlePhase.FIGHT):
        return context.weapon_profile
    if context.source_phase is BattlePhase.SHOOTING:
        if context.weapon_profile.range_profile.kind is RangeProfileKind.MELEE:
            return context.weapon_profile
    elif context.weapon_profile.range_profile.kind is not RangeProfileKind.MELEE:
        return context.weapon_profile
    pact = active_dark_pact_for_unit(
        context.state,
        unit_instance_id=context.attacking_unit_instance_id,
        phase=context.source_phase,
    )
    if pact is None:
        return context.weapon_profile
    if pact is DarkPactKind.LETHAL_HITS:
        return _profile_with_keyword_and_ability(
            context.weapon_profile,
            keyword=WeaponKeyword.LETHAL_HITS,
            ability=AbilityDescriptor.lethal_hits(),
        )
    if pact is DarkPactKind.SUSTAINED_HITS_1:
        return _profile_with_keyword_and_ability(
            context.weapon_profile,
            keyword=WeaponKeyword.SUSTAINED_HITS,
            ability=AbilityDescriptor.sustained_hits(1),
        )
    raise GameLifecycleError("Dark Pacts selected pact is unsupported.")


def resolve_dark_pact_attack_sequence_completion(
    context: AttackSequenceCompletedContext,
) -> None:
    if type(context) is not AttackSequenceCompletedContext:
        raise GameLifecycleError("Dark Pacts completion hook requires context.")
    effect = _active_dark_pact_effect_for_unit(
        context.state,
        unit_instance_id=context.attack_sequence.attacking_unit_instance_id,
        phase=context.source_phase,
    )
    if effect is None:
        return
    if _dark_pact_already_resolved(
        context=context,
        effect_id=effect.effect_id,
    ):
        return
    rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.attack_sequence.attacking_unit_instance_id,
    )
    payload = _dark_pact_payload(effect.effect_payload)
    selected_pact = _dark_pact_kind_from_token(payload["selected_dark_pact"])
    leadership_target = _leadership_target_for_rules_unit(context=context, rules_unit=rules_unit)
    leadership_roll = context.dice_manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=2, sides=6),
            reason=f"Dark Pact Leadership test for {rules_unit.unit_instance_id}",
            roll_type=DARK_PACT_LEADERSHIP_ROLL_TYPE,
            actor_id=rules_unit.unit_instance_id,
        )
    )
    passed = leadership_roll.current_total >= leadership_target
    if passed:
        context.decisions.event_log.append(
            "chaos_space_marines_dark_pact_resolved",
            _dark_pact_resolution_payload(
                context=context,
                rules_unit=rules_unit,
                effect=effect,
                selected_pact=selected_pact,
                leadership_target=leadership_target,
                leadership_roll=validate_json_value(leadership_roll.to_payload()),
                passed=True,
                d3_result=None,
                mortal_wound_application=None,
            ),
        )
        return
    d3_result = context.dice_manager.roll_d3(
        reason=f"Dark Pact mortal wounds for {rules_unit.unit_instance_id}",
        roll_type=DARK_PACT_MORTAL_WOUNDS_ROLL_TYPE,
        actor_id=rules_unit.unit_instance_id,
    )
    if _rules_unit_requires_mortal_wound_feel_no_pain_decision(context.state, rules_unit):
        context.decisions.event_log.append(
            "chaos_space_marines_dark_pact_unsupported",
            {
                **_dark_pact_resolution_payload(
                    context=context,
                    rules_unit=rules_unit,
                    effect=effect,
                    selected_pact=selected_pact,
                    leadership_target=leadership_target,
                    leadership_roll=validate_json_value(leadership_roll.to_payload()),
                    passed=False,
                    d3_result=validate_json_value(d3_result.to_payload()),
                    mortal_wound_application=None,
                ),
                "unsupported_reason": "mortal_wound_feel_no_pain_requires_decision",
            },
        )
        return
    application = apply_mortal_wounds_to_unit(
        state=context.state,
        target_unit_instance_id=rules_unit.unit_instance_id,
        mortal_wounds=d3_result.value,
        spill_over=True,
        dice_manager=context.dice_manager,
        defender_player_id=rules_unit.owner_player_id,
    )
    context.decisions.event_log.append(
        "chaos_space_marines_dark_pact_resolved",
        _dark_pact_resolution_payload(
            context=context,
            rules_unit=rules_unit,
            effect=effect,
            selected_pact=selected_pact,
            leadership_target=leadership_target,
            leadership_roll=validate_json_value(leadership_roll.to_payload()),
            passed=False,
            d3_result=validate_json_value(d3_result.to_payload()),
            mortal_wound_application=validate_json_value(application.to_payload()),
        ),
    )


def active_dark_pact_for_unit(
    state: object,
    *,
    unit_instance_id: str,
    phase: BattlePhase,
) -> DarkPactKind | None:
    effect = _active_dark_pact_effect_for_unit(
        state,
        unit_instance_id=unit_instance_id,
        phase=phase,
    )
    if effect is None:
        return None
    payload = _dark_pact_payload(effect.effect_payload)
    return _dark_pact_kind_from_token(payload["selected_dark_pact"])


def dark_pact_target_unit_ids(state: object, *, unit_instance_id: str) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Dark Pacts target lookup requires GameState.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=_validate_identifier("unit_instance_id", unit_instance_id),
    )
    return tuple(
        dict.fromkeys((rules_unit.unit_instance_id, *rules_unit.component_unit_instance_ids))
    )


def _dark_pacts_available(
    *,
    state: object,
    player_id: str,
    unit_instance_id: str,
    phase: BattlePhase,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Dark Pacts eligibility requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    army = state.army_definition_for_player(requested_player_id)
    if army is None:
        raise GameLifecycleError("Dark Pacts player army is missing.")
    if army.detachment_selection.faction_id != CHAOS_SPACE_MARINES_FACTION_ID:
        return False
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=requested_unit_id)
    if rules_unit.owner_player_id != requested_player_id:
        raise GameLifecycleError("Dark Pacts unit is not owned by the acting player.")
    if not _rules_unit_has_dark_pacts(rules_unit):
        return False
    return (
        _active_dark_pact_effect_for_unit(
            state,
            unit_instance_id=requested_unit_id,
            phase=phase,
        )
        is None
    )


def _active_dark_pact_effect_for_unit(
    state: object,
    *,
    unit_instance_id: str,
    phase: BattlePhase,
) -> PersistingEffect | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Dark Pacts effect lookup requires GameState.")
    requested_phase = _battle_phase_from_token(phase)
    effects: list[PersistingEffect] = []
    for effect in state.persisting_effects_for_unit(
        _validate_identifier("unit_instance_id", unit_instance_id)
    ):
        if effect.source_rule_id != SOURCE_RULE_ID:
            continue
        payload = _dark_pact_payload(effect.effect_payload)
        if payload["phase"] != requested_phase.value:
            continue
        effects.append(effect)
    if len(effects) > 1:
        raise GameLifecycleError("Dark Pacts found multiple active effects for a unit.")
    return None if not effects else effects[0]


def _rules_unit_has_dark_pacts(rules_unit: RulesUnitView) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Dark Pacts requires a RulesUnitView.")
    return any(_unit_has_dark_pacts(component.unit) for component in rules_unit.components)


def _unit_has_dark_pacts(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Dark Pacts requires a UnitInstance.")
    if any(
        faction_reference_matches(
            faction_id=CHAOS_SPACE_MARINES_FACTION_ID,
            reference=keyword,
        )
        for keyword in unit.faction_keywords
    ):
        return True
    return any(
        _canonical_rule_token(ability.name) == _canonical_rule_token(DARK_PACTS_ABILITY_NAME)
        for ability in unit.datasheet_abilities
    )


def _leadership_target_for_rules_unit(
    *,
    context: AttackSequenceCompletedContext,
    rules_unit: RulesUnitView,
) -> int:
    alive_models = rules_unit.alive_models()
    if not alive_models:
        raise GameLifecycleError("Dark Pacts Leadership test requires alive models.")
    base_leadership = min(_model_leadership(model) for model in alive_models)
    return context.runtime_modifier_registry.modified_unit_characteristic(
        UnitCharacteristicModifierContext(
            state=context.state,
            unit_instance_id=rules_unit.unit_instance_id,
            characteristic=Characteristic.LEADERSHIP,
            base_value=base_leadership,
            current_value=base_leadership,
        )
    )


def _model_leadership(model: ModelInstance) -> int:
    if type(model) is not ModelInstance:
        raise GameLifecycleError("Dark Pacts Leadership lookup requires ModelInstance.")
    for value in model.characteristics:
        if value.characteristic is Characteristic.LEADERSHIP:
            return value.final
    raise GameLifecycleError("Dark Pacts model is missing Leadership.")


def _profile_with_keyword_and_ability(
    profile: WeaponProfile,
    *,
    keyword: WeaponKeyword,
    ability: AbilityDescriptor,
) -> WeaponProfile:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Dark Pacts weapon profile modifier requires WeaponProfile.")
    keywords = profile.keywords
    if keyword not in keywords:
        keywords = (*keywords, keyword)
    abilities = profile.abilities
    if all(existing.ability_id != ability.ability_id for existing in abilities):
        abilities = (*abilities, ability)
    source_ids = profile.source_ids
    if SOURCE_RULE_ID not in source_ids:
        source_ids = (*source_ids, SOURCE_RULE_ID)
    return replace(profile, keywords=keywords, abilities=abilities, source_ids=source_ids)


def _rules_unit_requires_mortal_wound_feel_no_pain_decision(
    state: object,
    rules_unit: RulesUnitView,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Dark Pacts Feel No Pain lookup requires GameState.")
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Dark Pacts Feel No Pain lookup requires RulesUnitView.")
    for model in rules_unit.alive_models():
        sources = state.feel_no_pain_sources_for_model(model_instance_id=model.model_instance_id)
        if len(sources) > 1:
            return True
        if state.feel_no_pain_decline_allowed_for_model(model_instance_id=model.model_instance_id):
            return True
    return False


def _dark_pact_already_resolved(
    *,
    context: AttackSequenceCompletedContext,
    effect_id: str,
) -> bool:
    requested_effect_id = _validate_identifier("effect_id", effect_id)
    for event in context.decisions.event_log.records:
        if event.event_type not in {
            "chaos_space_marines_dark_pact_resolved",
            "chaos_space_marines_dark_pact_unsupported",
        }:
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Dark Pacts resolution payload is malformed.")
        if payload.get("effect_id") != requested_effect_id:
            continue
        if payload.get("attack_sequence_id") == context.attack_sequence.sequence_id:
            return True
    return False


def _dark_pact_resolution_payload(
    *,
    context: AttackSequenceCompletedContext,
    rules_unit: RulesUnitView,
    effect: PersistingEffect,
    selected_pact: DarkPactKind,
    leadership_target: int,
    leadership_roll: JsonValue,
    passed: bool,
    d3_result: JsonValue,
    mortal_wound_application: JsonValue,
) -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": context.source_phase.value,
                "source_rule_id": SOURCE_RULE_ID,
                "hook_id": ATTACK_SEQUENCE_COMPLETED_HOOK_ID,
                "player_id": rules_unit.owner_player_id,
                "unit_instance_id": rules_unit.unit_instance_id,
                "target_unit_instance_ids": list(effect.target_unit_instance_ids),
                "effect_id": effect.effect_id,
                "selected_dark_pact": selected_pact.value,
                "attack_sequence_id": context.attack_sequence.sequence_id,
                "attack_sequence_completed_event_id": (context.attack_sequence_completed_event_id),
                "leadership_target": leadership_target,
                "leadership_roll": leadership_roll,
                "passed": passed,
                "d3_result": d3_result,
                "mortal_wound_application": mortal_wound_application,
            }
        ),
    )


def _dark_pact_payload(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Dark Pacts effect payload must be an object.")
    if payload.get("effect_kind") != DARK_PACT_EFFECT_KIND:
        raise GameLifecycleError("Dark Pacts effect kind drift.")
    if type(payload.get("unit_instance_id")) is not str:
        raise GameLifecycleError("Dark Pacts effect payload is missing unit_instance_id.")
    if type(payload.get("phase")) is not str:
        raise GameLifecycleError("Dark Pacts effect payload is missing phase.")
    if type(payload.get("selected_dark_pact")) is not str:
        raise GameLifecycleError("Dark Pacts effect payload is missing selected_dark_pact.")
    _dark_pact_kind_from_token(payload["selected_dark_pact"])
    return payload


def _dark_pact_kind_from_token(token: object) -> DarkPactKind:
    if type(token) is DarkPactKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Dark Pacts kind must be a string.")
    try:
        return DarkPactKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Dark Pacts kind: {token}.") from exc


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is BattlePhaseKind:
        return BattlePhase(token.value)
    if type(token) is not str:
        raise GameLifecycleError("Dark Pacts phase must be a BattlePhase.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported Dark Pacts phase: {token}.") from exc


def _canonical_rule_token(value: str) -> str:
    return " ".join(_validate_identifier("rule token", value).upper().split())


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Dark Pacts {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Dark Pacts {field_name} must not be empty.")
    return stripped


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Dark Pacts {field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"Dark Pacts {field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(validated)
