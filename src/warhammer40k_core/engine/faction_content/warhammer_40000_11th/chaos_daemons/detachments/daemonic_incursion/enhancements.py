from __future__ import annotations

from dataclasses import replace
from typing import cast

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    RangeProfile,
    RangeProfileKind,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, EnhancementAssignment
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
)
from warhammer40k_core.engine.damage_allocation import FeelNoPainSource
from warhammer40k_core.engine.enhancement_effects import (
    EnhancementEffectContext,
    EnhancementFeelNoPainGrant,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.faction_content.common import canonical_keyword as _canonical_keyword
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    army_rule,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import WeaponProfileModifierContext
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance

from . import rule

CONTRIBUTION_ID = "warhammer_40000_11th:chaos_daemons:detachment:daemonic_incursion:enhancements"

ARGATH_ENHANCEMENT_ID = "000008438002"
SOULSTEALER_ENHANCEMENT_ID = "000008438003"
ENDLESS_GIFT_ENHANCEMENT_ID = "000008438004"
EVERSTAVE_ENHANCEMENT_ID = "000008438005"

ARGATH_SOURCE_RULE_ID = (
    "phase17f:phase17e:enhancement:chaos-daemons:daemonic-incursion:000008438002"
)
SOULSTEALER_SOURCE_RULE_ID = (
    "phase17f:phase17e:enhancement:chaos-daemons:daemonic-incursion:000008438003"
)
ENDLESS_GIFT_SOURCE_RULE_ID = (
    "phase17f:phase17e:enhancement:chaos-daemons:daemonic-incursion:000008438004"
)
EVERSTAVE_SOURCE_RULE_ID = (
    "phase17f:phase17e:enhancement:chaos-daemons:daemonic-incursion:000008438005"
)

ARGATH_WEAPON_PROFILE_MODIFIER_ID = (
    "warhammer_40000_11th:chaos_daemons:detachment:daemonic_incursion:"
    "enhancement:argath:melee-weapon-profile"
)
SOULSTEALER_HOOK_ID = (
    "warhammer_40000_11th:chaos_daemons:detachment:daemonic_incursion:"
    "enhancement:soulstealer:model-destroyed-heal"
)
ENDLESS_GIFT_EFFECT_ID = (
    "warhammer_40000_11th:chaos_daemons:detachment:daemonic_incursion:"
    "enhancement:endless_gift:feel-no-pain-5"
)
EVERSTAVE_WEAPON_PROFILE_MODIFIER_ID = (
    "warhammer_40000_11th:chaos_daemons:detachment:daemonic_incursion:"
    "enhancement:everstave:ranged-weapon-profile"
)

SOULSTEALER_RESOLVED_EVENT = "chaos_daemons_daemonic_incursion_soulstealer_resolved"
SOULSTEALER_D6_ROLL_TYPE = "chaos_daemons.daemonic_incursion.soulstealer_d6"


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(contribution_id=CONTRIBUTION_ID)


def argath_weapon_profile_modifier(context: WeaponProfileModifierContext) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("A'rgath weapon modifier requires context.")
    profile = context.weapon_profile
    if profile.range_profile.kind is not RangeProfileKind.MELEE:
        return profile
    assignment = _assigned_bearer_for_attack_context(
        context,
        enhancement_id=ARGATH_ENHANCEMENT_ID,
        required_keyword="KHORNE",
        rule_label="A'rgath",
    )
    if assignment is None:
        return profile
    army, _enhancement_assignment, bearer = assignment
    delta = 2 if _bearer_within_shadow(context.state, army=army, bearer=bearer) else 1
    return _profile_with_attacks_and_strength_delta(
        profile=profile,
        attacks_delta=delta,
        strength_delta=delta,
        source_id=ARGATH_SOURCE_RULE_ID,
        rule_label="A'rgath",
    )


def everstave_weapon_profile_modifier(context: WeaponProfileModifierContext) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Everstave weapon modifier requires context.")
    profile = context.weapon_profile
    if profile.range_profile.kind is not RangeProfileKind.DISTANCE:
        return profile
    assignment = _assigned_bearer_for_attack_context(
        context,
        enhancement_id=EVERSTAVE_ENHANCEMENT_ID,
        required_keyword="TZEENTCH",
        rule_label="Everstave",
    )
    if assignment is None:
        return profile
    army, _enhancement_assignment, bearer = assignment
    strength_delta = 2 if _bearer_within_shadow(context.state, army=army, bearer=bearer) else 1
    range_delta = 6 if strength_delta == 2 else 3
    return _profile_with_strength_and_range_delta(
        profile=profile,
        strength_delta=strength_delta,
        range_delta=range_delta,
        source_id=EVERSTAVE_SOURCE_RULE_ID,
        rule_label="Everstave",
    )


def endless_gift_effect(
    context: EnhancementEffectContext,
) -> tuple[EnhancementFeelNoPainGrant, ...]:
    if type(context) is not EnhancementEffectContext:
        raise GameLifecycleError("Endless Gift requires an EnhancementEffectContext.")
    if context.assignment.enhancement_id != ENDLESS_GIFT_ENHANCEMENT_ID:
        return ()
    _validate_daemonic_incursion_bearer(
        army=context.army,
        unit=context.target_unit,
        required_keyword="NURGLE",
        rule_label="Endless Gift",
    )
    return tuple(
        EnhancementFeelNoPainGrant(
            effect_id=ENDLESS_GIFT_EFFECT_ID,
            source_id=ENDLESS_GIFT_SOURCE_RULE_ID,
            enhancement_id=ENDLESS_GIFT_ENHANCEMENT_ID,
            target_unit_instance_id=context.target_unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            source=FeelNoPainSource(
                source_id=(f"{ENDLESS_GIFT_SOURCE_RULE_ID}:{model.model_instance_id}:feel-no-pain"),
                threshold=5,
            ),
            replay_payload={
                "effect_kind": "daemonic_incursion_endless_gift_feel_no_pain_5",
                "assignment_source_id": context.assignment.source_id,
                "target_unit_selection_id": context.assignment.target_unit_selection_id,
                "bearer_unit_instance_id": context.target_unit.unit_instance_id,
                "model_instance_id": model.model_instance_id,
                "threshold": 5,
            },
        )
        for model in context.target_unit.own_models
    )


def resolve_soulstealer_attack_sequence_completion(
    context: AttackSequenceCompletedContext,
) -> None:
    if type(context) is not AttackSequenceCompletedContext:
        raise GameLifecycleError("Soulstealer requires an attack sequence completion context.")
    if context.source_phase is not BattlePhase.FIGHT:
        return
    for army, assignment, bearer in _assigned_soulstealer_bearers(context.state):
        _validate_daemonic_incursion_bearer(
            army=army,
            unit=bearer,
            required_keyword="SLAANESH",
            rule_label="Soulstealer",
        )
        bearer_model_ids = {model.model_instance_id for model in bearer.own_models}
        for event_id, payload in _destroyed_enemy_model_events_for_sequence(
            context=context,
            army=army,
            bearer=bearer,
            bearer_model_ids=frozenset(bearer_model_ids),
        ):
            if _soulstealer_event_already_resolved(
                context=context,
                destroyed_model_event_id=event_id,
            ):
                continue
            bearer_model_id = _payload_identifier(payload, "attacking_model_instance_id")
            shadow_bonus = (
                1 if _bearer_within_shadow(context.state, army=army, bearer=bearer) else 0
            )
            d6_result = context.dice_manager.roll(
                DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason="Soulstealer",
                    roll_type=SOULSTEALER_D6_ROLL_TYPE,
                    actor_id=bearer_model_id,
                )
            )
            roll_total = d6_result.current_total + shadow_bonus
            heal_succeeded = roll_total >= 4
            before_wounds, after_wounds = _heal_bearer_model(
                state=context.state,
                unit_instance_id=bearer.unit_instance_id,
                model_instance_id=bearer_model_id,
                amount=1 if heal_succeeded else 0,
            )
            context.decisions.event_log.append(
                SOULSTEALER_RESOLVED_EVENT,
                _soulstealer_resolution_payload(
                    context=context,
                    army=army,
                    assignment=assignment,
                    bearer=bearer,
                    destroyed_model_event_id=event_id,
                    destroyed_model_payload=payload,
                    bearer_model_id=bearer_model_id,
                    d6_result=validate_json_value(d6_result.to_payload()),
                    shadow_bonus=shadow_bonus,
                    roll_total=roll_total,
                    heal_succeeded=heal_succeeded,
                    before_wounds=before_wounds,
                    after_wounds=after_wounds,
                ),
            )
    return


def _assigned_bearer_for_attack_context(
    context: WeaponProfileModifierContext,
    *,
    enhancement_id: str,
    required_keyword: str,
    rule_label: str,
) -> tuple[ArmyDefinition, EnhancementAssignment, UnitInstance] | None:
    for army in _daemonic_incursion_armies(context.state):
        for assignment, bearer in _assigned_units(army, enhancement_id=enhancement_id):
            if bearer.unit_instance_id != context.attacking_unit_instance_id:
                continue
            if not any(
                model.model_instance_id == context.attacker_model_instance_id
                for model in bearer.own_models
            ):
                continue
            _validate_daemonic_incursion_bearer(
                army=army,
                unit=bearer,
                required_keyword=required_keyword,
                rule_label=rule_label,
            )
            return army, assignment, bearer
    return None


def _assigned_soulstealer_bearers(
    state: GameState,
) -> tuple[tuple[ArmyDefinition, EnhancementAssignment, UnitInstance], ...]:
    assignments: list[tuple[ArmyDefinition, EnhancementAssignment, UnitInstance]] = []
    for army in _daemonic_incursion_armies(state):
        assignments.extend(
            (army, assignment, bearer)
            for assignment, bearer in _assigned_units(
                army,
                enhancement_id=SOULSTEALER_ENHANCEMENT_ID,
            )
        )
    return tuple(sorted(assignments, key=lambda item: item[2].unit_instance_id))


def _profile_with_attacks_and_strength_delta(
    *,
    profile: WeaponProfile,
    attacks_delta: int,
    strength_delta: int,
    source_id: str,
    rule_label: str,
) -> WeaponProfile:
    if source_id in profile.source_ids:
        return profile
    return replace(
        profile,
        attack_profile=_attack_profile_with_delta(
            profile.attack_profile,
            delta=attacks_delta,
            rule_label=rule_label,
        ),
        strength=_strength_with_delta(
            profile.strength,
            delta=strength_delta,
            rule_label=rule_label,
        ),
        source_ids=tuple(sorted({*profile.source_ids, source_id})),
    )


def _profile_with_strength_and_range_delta(
    *,
    profile: WeaponProfile,
    strength_delta: int,
    range_delta: int,
    source_id: str,
    rule_label: str,
) -> WeaponProfile:
    if source_id in profile.source_ids:
        return profile
    if profile.range_profile.distance_inches is None:
        raise GameLifecycleError(f"{rule_label} requires a ranged weapon profile.")
    return replace(
        profile,
        strength=_strength_with_delta(
            profile.strength,
            delta=strength_delta,
            rule_label=rule_label,
        ),
        range_profile=RangeProfile.distance(profile.range_profile.distance_inches + range_delta),
        source_ids=tuple(sorted({*profile.source_ids, source_id})),
    )


def _attack_profile_with_delta(
    profile: AttackProfile,
    *,
    delta: int,
    rule_label: str,
) -> AttackProfile:
    if type(profile) is not AttackProfile:
        raise GameLifecycleError(f"{rule_label} requires an AttackProfile.")
    if type(delta) is not int:
        raise GameLifecycleError(f"{rule_label} attack delta must be an integer.")
    if profile.fixed_attacks is not None:
        return AttackProfile.fixed(profile.fixed_attacks + delta)
    if profile.dice_expression is None:
        raise GameLifecycleError(f"{rule_label} attack profile is invalid.")
    return AttackProfile.dice(
        replace(
            profile.dice_expression,
            modifier=profile.dice_expression.modifier + delta,
        )
    )


def _strength_with_delta(
    value: CharacteristicValue,
    *,
    delta: int,
    rule_label: str,
) -> CharacteristicValue:
    if type(value) is not CharacteristicValue:
        raise GameLifecycleError(f"{rule_label} requires a Strength characteristic value.")
    if value.characteristic is not Characteristic.STRENGTH:
        raise GameLifecycleError(f"{rule_label} requires a Strength weapon profile.")
    if type(delta) is not int:
        raise GameLifecycleError(f"{rule_label} Strength delta must be an integer.")
    if not value.is_numeric:
        raise GameLifecycleError(f"{rule_label} cannot modify dash Strength.")
    return CharacteristicValue.from_raw(Characteristic.STRENGTH, value.final + delta)


def _destroyed_enemy_model_events_for_sequence(
    *,
    context: AttackSequenceCompletedContext,
    army: ArmyDefinition,
    bearer: UnitInstance,
    bearer_model_ids: frozenset[str],
) -> tuple[tuple[str, dict[str, JsonValue]], ...]:
    events: list[tuple[str, dict[str, JsonValue]]] = []
    for record in context.decisions.event_log.records:
        if record.event_type != "model_destroyed":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Soulstealer model_destroyed payload must be an object.")
        if payload.get("sequence_id") != context.attack_sequence.sequence_id:
            continue
        if payload.get("phase") != BattlePhase.FIGHT.value:
            raise GameLifecycleError("Soulstealer model_destroyed event phase drift.")
        if payload.get("destroying_player_id") != army.player_id:
            continue
        if payload.get("attacking_unit_instance_id") != bearer.unit_instance_id:
            continue
        attacker_model_id = _payload_identifier(payload, "attacking_model_instance_id")
        if attacker_model_id not in bearer_model_ids:
            continue
        target_unit_id = _payload_identifier(payload, "target_unit_instance_id")
        if (
            _owner_player_id_for_unit(context.state, unit_instance_id=target_unit_id)
            == army.player_id
        ):
            raise GameLifecycleError("Soulstealer destroyed model event target is not an enemy.")
        if not _sequence_has_bearer_melee_pool(
            context=context,
            bearer_model_id=attacker_model_id,
            target_unit_instance_id=target_unit_id,
        ):
            raise GameLifecycleError("Soulstealer destroyed model event has no melee attack pool.")
        _payload_identifier(payload, "model_instance_id")
        events.append((record.event_id, payload))
    return tuple(events)


def _sequence_has_bearer_melee_pool(
    *,
    context: AttackSequenceCompletedContext,
    bearer_model_id: str,
    target_unit_instance_id: str,
) -> bool:
    requested_model_id = _validate_identifier("bearer_model_id", bearer_model_id)
    requested_target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    return any(
        pool.attacker_model_instance_id == requested_model_id
        and pool.target_unit_instance_id == requested_target_id
        and pool.weapon_profile.range_profile.kind is RangeProfileKind.MELEE
        for pool in context.attack_sequence.attack_pools
    )


def _soulstealer_event_already_resolved(
    *,
    context: AttackSequenceCompletedContext,
    destroyed_model_event_id: str,
) -> bool:
    requested_event_id = _validate_identifier("destroyed_model_event_id", destroyed_model_event_id)
    for record in context.decisions.event_log.records:
        if record.event_type != SOULSTEALER_RESOLVED_EVENT:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Soulstealer resolution payload must be an object.")
        if payload.get("attack_sequence_id") != context.attack_sequence.sequence_id:
            continue
        if payload.get("destroyed_model_event_id") == requested_event_id:
            return True
    return False


def _heal_bearer_model(
    *,
    state: GameState,
    unit_instance_id: str,
    model_instance_id: str,
    amount: int,
) -> tuple[int, int]:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    if type(amount) is not int or amount < 0:
        raise GameLifecycleError("Soulstealer healing amount must be non-negative.")
    updated_armies: list[ArmyDefinition] = []
    before_wounds: int | None = None
    after_wounds: int | None = None
    found_model = False
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id != requested_unit_id:
                updated_units.append(unit)
                continue
            updated_models: list[ModelInstance] = []
            for model in unit.own_models:
                if model.model_instance_id != requested_model_id:
                    updated_models.append(model)
                    continue
                found_model = True
                before_wounds = model.wounds_remaining
                after_wounds = (
                    model.wounds_remaining
                    if model.wounds_remaining <= 0
                    else min(model.starting_wounds, model.wounds_remaining + amount)
                )
                updated_models.append(replace(model, wounds_remaining=after_wounds))
            updated_units.append(replace(unit, own_models=tuple(updated_models)))
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not found_model or before_wounds is None or after_wounds is None:
        raise GameLifecycleError("Soulstealer bearer model was not found.")
    if after_wounds != before_wounds:
        state.replace_army_definitions(updated_armies)
    return before_wounds, after_wounds


def _soulstealer_resolution_payload(
    *,
    context: AttackSequenceCompletedContext,
    army: ArmyDefinition,
    assignment: EnhancementAssignment,
    bearer: UnitInstance,
    destroyed_model_event_id: str,
    destroyed_model_payload: dict[str, JsonValue],
    bearer_model_id: str,
    d6_result: JsonValue,
    shadow_bonus: int,
    roll_total: int,
    heal_succeeded: bool,
    before_wounds: int,
    after_wounds: int,
) -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "active_player_id": context.state.active_player_id,
                "phase": BattlePhase.FIGHT.value,
                "player_id": army.player_id,
                "source_rule_id": SOULSTEALER_SOURCE_RULE_ID,
                "hook_id": SOULSTEALER_HOOK_ID,
                "enhancement_id": SOULSTEALER_ENHANCEMENT_ID,
                "assignment_source_id": assignment.source_id,
                "bearer_unit_instance_id": bearer.unit_instance_id,
                "bearer_model_instance_id": bearer_model_id,
                "destroyed_model_event_id": destroyed_model_event_id,
                "destroyed_model_payload": validate_json_value(destroyed_model_payload),
                "attack_sequence_id": context.attack_sequence.sequence_id,
                "attack_sequence_completed_event_id": context.attack_sequence_completed_event_id,
                "d6_result": d6_result,
                "shadow_bonus": shadow_bonus,
                "roll_total": roll_total,
                "threshold": 4,
                "heal_succeeded": heal_succeeded,
                "before_wounds": before_wounds,
                "after_wounds": after_wounds,
                "healed_wounds": after_wounds - before_wounds,
            }
        ),
    )


def _bearer_within_shadow(
    state: GameState,
    *,
    army: ArmyDefinition,
    bearer: UnitInstance,
) -> bool:
    if type(state) is not GameState:
        raise GameLifecycleError("Daemonic Incursion Shadow lookup requires GameState.")
    return army_rule.unit_within_shadow_of_chaos(
        state=state,
        player_id=army.player_id,
        unit_instance_id=bearer.unit_instance_id,
    )


def _validate_daemonic_incursion_bearer(
    *,
    army: ArmyDefinition,
    unit: UnitInstance,
    required_keyword: str,
    rule_label: str,
) -> None:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError(f"{rule_label} requires an ArmyDefinition.")
    if type(unit) is not UnitInstance:
        raise GameLifecycleError(f"{rule_label} requires a UnitInstance.")
    if not (
        army.detachment_selection.faction_id == rule.CHAOS_DAEMONS_FACTION_ID
        and rule.DAEMONIC_INCURSION_DETACHMENT_ID in army.detachment_selection.detachment_ids
    ):
        raise GameLifecycleError(f"{rule_label} requires Daemonic Incursion.")
    if not _unit_has_faction_keyword(unit, rule.LEGIONES_DAEMONICA):
        raise GameLifecycleError(f"{rule_label} requires a Legiones Daemonica model.")
    if not _unit_has_keyword(unit, required_keyword):
        raise GameLifecycleError(f"{rule_label} requires a {required_keyword.title()} model.")


def _daemonic_incursion_armies(state: GameState) -> tuple[ArmyDefinition, ...]:
    if type(state) is not GameState:
        raise GameLifecycleError("Daemonic Incursion enhancement lookup requires GameState.")
    return tuple(
        army
        for army in state.army_definitions
        if army.detachment_selection.faction_id == rule.CHAOS_DAEMONS_FACTION_ID
        and rule.DAEMONIC_INCURSION_DETACHMENT_ID in army.detachment_selection.detachment_ids
    )


def _assigned_units(
    army: ArmyDefinition,
    *,
    enhancement_id: str,
) -> tuple[tuple[EnhancementAssignment, UnitInstance], ...]:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Daemonic Incursion assignment lookup requires ArmyDefinition.")
    requested_enhancement_id = _validate_identifier("enhancement_id", enhancement_id)
    assignments: list[tuple[EnhancementAssignment, UnitInstance]] = []
    for assignment in army.enhancement_assignments:
        if assignment.enhancement_id != requested_enhancement_id:
            continue
        assignments.append((assignment, _unit_for_assignment(army, assignment=assignment)))
    return tuple(sorted(assignments, key=lambda item: item[1].unit_instance_id))


def _unit_for_assignment(
    army: ArmyDefinition,
    *,
    assignment: EnhancementAssignment,
) -> UnitInstance:
    if type(assignment) is not EnhancementAssignment:
        raise GameLifecycleError("Daemonic Incursion assignment lookup requires assignment.")
    expected_unit_instance_id = f"{army.army_id}:{assignment.target_unit_selection_id}"
    for unit in army.units:
        if unit.unit_instance_id == expected_unit_instance_id:
            return unit
    raise GameLifecycleError("Daemonic Incursion assignment target unit was not mustered.")


def _owner_player_id_for_unit(state: GameState, *, unit_instance_id: str) -> str:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        if any(unit.unit_instance_id == requested_unit_id for unit in army.units):
            return army.player_id
    raise GameLifecycleError("Daemonic Incursion unit owner was not found.")


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    requested_keyword = _canonical_keyword(keyword)
    return requested_keyword in {_canonical_keyword(stored) for stored in unit.keywords}


def _unit_has_faction_keyword(unit: UnitInstance, keyword: str) -> bool:
    requested_keyword = _canonical_keyword(keyword)
    return requested_keyword in {_canonical_keyword(stored) for stored in unit.faction_keywords}


def _payload_identifier(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Soulstealer payload requires {key}.")
    return _validate_identifier(key, value)


_validate_identifier = IdentifierValidator(GameLifecycleError)
