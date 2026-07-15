from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal, cast

from warhammer40k_core.core.attributes import (
    Characteristic,
    characteristic_from_token,
)
from warhammer40k_core.core.dice import RerollComponentSelectionPolicy, RerollPermission
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import (
    WeaponProfile,
)
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.generic_rule_attack_conditions import (
    generic_rule_conditions_from_payload,
    generic_rule_conditions_require_source_model_instance_id,
    generic_rule_parameters_from_effect_payload,
    generic_rule_source_model_applies,
    generic_rule_source_model_instance_id_from_payload,
    generic_rule_target_allegiance_applies,
    generic_rule_target_allegiance_values,
    generic_rule_target_constraint_values,
    generic_rule_target_constraints_apply,
    generic_rule_target_proximity_keyword_gate_applies,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rule_ir_weapon_modifiers import (
    rule_ir_modified_weapon_profile,
    rule_ir_weapon_ability_granted_profile,
    rule_ir_weapon_selector_applies,
)
from warhammer40k_core.engine.rule_target_resolution import unit_has_required_keywords
from warhammer40k_core.engine.runtime_modifiers import (
    ChargeRollModifierContext,
    DamageRollModifierContext,
    HitRollMinimumUnmodifiedSuccessContext,
    HitRollModifierContext,
    MovementBudgetModifierContext,
    ObjectiveControlModifierContext,
    SaveOptionModifierContext,
    UnitCharacteristicModifierContext,
    WeaponProfileModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, SaveOption
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleTargetKind

type AttackRole = Literal["attacker", "target"]

_ATTACKER_TARGET_KINDS = frozenset(
    {
        RuleTargetKind.FRIENDLY_UNIT,
        RuleTargetKind.PLAYER,
        RuleTargetKind.SELECTED_UNIT,
        RuleTargetKind.THIS_MODEL,
        RuleTargetKind.THIS_UNIT,
        RuleTargetKind.WEAPON,
    }
)
_TARGET_TARGET_KINDS = frozenset({RuleTargetKind.ENEMY_UNIT, RuleTargetKind.SELECTED_TARGET})
_LEGACY_SELF_TARGET_KINDS = frozenset(
    {
        RuleTargetKind.FRIENDLY_UNIT,
        RuleTargetKind.SELECTED_UNIT,
        RuleTargetKind.THIS_MODEL,
        RuleTargetKind.THIS_UNIT,
    }
)


@dataclass(frozen=True, slots=True)
class GenericRuleRerollPermissionContext:
    permission: RerollPermission
    source_payload: dict[str, JsonValue]

    def __post_init__(self) -> None:
        if type(self.permission) is not RerollPermission:
            raise GameLifecycleError("Generic RuleIR reroll context requires permission.")
        source_payload = validate_json_value(self.source_payload)
        if not isinstance(source_payload, dict):
            raise GameLifecycleError("Generic RuleIR reroll source payload must be an object.")
        object.__setattr__(self, "source_payload", source_payload)


@dataclass(frozen=True, slots=True)
class _GenericAttackEffect:
    persisting_effect: PersistingEffect
    role: AttackRole
    source_id: str
    rule_id: str
    rule_ir_hash: str
    clause_id: str
    target_kind: RuleTargetKind | None
    effect_kind: RuleEffectKind
    parameters: dict[str, JsonValue]
    conditions: tuple[dict[str, JsonValue], ...]
    source_model_instance_id: str | None


def generic_rule_hit_roll_modifier(context: HitRollModifierContext) -> int:
    if type(context) is not HitRollModifierContext:
        raise GameLifecycleError("Generic hit roll hooks require HitRollModifierContext.")
    return _dice_roll_modifier_for_attack(
        state=context.state,
        attacking_unit_instance_id=context.attacking_unit_instance_id,
        attacker_model_instance_id=context.attacker_model_instance_id,
        target_unit_instance_id=context.target_unit_instance_id,
        source_phase=context.source_phase,
        weapon_profile=context.weapon_profile,
        expected_roll_type="hit",
        legacy_attacker_role_allowed=lambda effect: (
            _required_int_parameter(
                effect.parameters,
                key="delta",
            )
            >= 0
        ),
        legacy_target_role_allowed=lambda effect: (
            _required_int_parameter(
                effect.parameters,
                key="delta",
            )
            <= 0
        ),
    )


def generic_rule_wound_roll_modifier(context: WoundRollModifierContext) -> int:
    if type(context) is not WoundRollModifierContext:
        raise GameLifecycleError("Generic wound roll hooks require WoundRollModifierContext.")
    return _dice_roll_modifier_for_attack(
        state=context.state,
        attacking_unit_instance_id=context.attacking_unit_instance_id,
        attacker_model_instance_id=context.attacker_model_instance_id,
        target_unit_instance_id=context.target_unit_instance_id,
        source_phase=context.source_phase,
        weapon_profile=context.weapon_profile,
        attack_strength=context.strength,
        target_toughness=context.toughness,
        expected_roll_type="wound",
        legacy_attacker_role_allowed=lambda effect: (
            _required_int_parameter(
                effect.parameters,
                key="delta",
            )
            >= 0
        ),
        legacy_target_role_allowed=lambda effect: (
            _required_int_parameter(
                effect.parameters,
                key="delta",
            )
            <= 0
        ),
    )


def generic_rule_damage_roll_modifier(context: DamageRollModifierContext) -> int:
    if type(context) is not DamageRollModifierContext:
        raise GameLifecycleError("Generic damage roll hooks require DamageRollModifierContext.")
    return _dice_roll_modifier_for_attack(
        state=context.state,
        attacking_unit_instance_id=context.attacking_unit_instance_id,
        attacker_model_instance_id=context.attacker_model_instance_id,
        target_unit_instance_id=context.target_unit_instance_id,
        source_phase=context.source_phase,
        weapon_profile=context.weapon_profile,
        expected_roll_type="damage",
        legacy_attacker_role_allowed=lambda effect: (
            _required_int_parameter(
                effect.parameters,
                key="delta",
            )
            >= 0
        ),
        legacy_target_role_allowed=lambda effect: (
            _required_int_parameter(
                effect.parameters,
                key="delta",
            )
            <= 0
        ),
    )


def generic_rule_minimum_unmodified_hit_success(
    context: HitRollMinimumUnmodifiedSuccessContext,
) -> int:
    if type(context) is not HitRollMinimumUnmodifiedSuccessContext:
        raise GameLifecycleError(
            "Generic minimum hit success hooks require HitRollMinimumUnmodifiedSuccessContext."
        )
    current = context.current_minimum_unmodified_success
    for effect in _matching_generic_attack_effects(
        state=context.state,
        attacking_unit_instance_id=context.attacking_unit_instance_id,
        attacker_model_instance_id=context.attacker_model_instance_id,
        target_unit_instance_id=context.target_unit_instance_id,
        source_phase=context.source_phase,
        weapon_profile=context.weapon_profile,
        effect_kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
        legacy_attacker_role_allowed=lambda _candidate: True,
        legacy_target_role_allowed=lambda _candidate: False,
    ):
        if (
            _required_string_parameter(effect.parameters, key="status")
            != "minimum_unmodified_hit_success"
        ):
            continue
        if not _roll_type_matches(effect.parameters, expected="hit"):
            continue
        if not _targeting_rule_gate_applies(
            effect.parameters,
            targeting_rule_ids=context.targeting_rule_ids,
        ):
            continue
        current = min(current, _minimum_unmodified_success_parameter(effect.parameters))
    return current


def generic_rule_modified_save_options(
    context: SaveOptionModifierContext,
) -> tuple[SaveOption, ...]:
    if type(context) is not SaveOptionModifierContext:
        raise GameLifecycleError("Generic save hooks require SaveOptionModifierContext.")
    if (
        context.attacking_unit_instance_id is None
        or context.attacker_model_instance_id is None
        or context.weapon_profile is None
        or context.source_phase is None
    ):
        return context.save_options
    current = context.save_options
    for effect in _matching_generic_unit_effects(
        state=context.state,
        unit_instance_id=context.target_unit_instance_id,
        effect_kind=RuleEffectKind.SET_CHARACTERISTIC,
    ):
        if _characteristic_parameter(effect.parameters) is not Characteristic.INVULNERABLE_SAVE:
            continue
        if context.allocated_model_instance_id is None:
            if not _generic_this_model_effect_targets_only_alive_model(
                state=context.state,
                effect=effect,
                unit_instance_id=context.target_unit_instance_id,
            ):
                continue
        elif effect.source_model_instance_id != context.allocated_model_instance_id:
            continue
        current = _save_options_with_invulnerable_save(
            current,
            target_number=_required_int_parameter(effect.parameters, key="value"),
            source_id=_modifier_source_id(effect),
        )
    for effect in _matching_generic_attack_effects(
        state=context.state,
        attacking_unit_instance_id=context.attacking_unit_instance_id,
        attacker_model_instance_id=context.attacker_model_instance_id,
        target_unit_instance_id=context.target_unit_instance_id,
        source_phase=context.source_phase,
        weapon_profile=context.weapon_profile,
        effect_kind=RuleEffectKind.MODIFY_DICE_ROLL,
        legacy_attacker_role_allowed=lambda candidate: (
            _required_int_parameter(
                candidate.parameters,
                key="delta",
            )
            <= 0
        ),
        legacy_target_role_allowed=lambda candidate: (
            _required_int_parameter(
                candidate.parameters,
                key="delta",
            )
            >= 0
        ),
    ):
        if not _roll_type_matches(effect.parameters, expected="save"):
            continue
        delta = _required_int_parameter(effect.parameters, key="delta")
        source_id = _modifier_source_id(effect)
        current = tuple(
            _save_option_with_roll_modifier(option, delta, source_id) for option in current
        )
    return current


def _generic_this_model_effect_targets_only_alive_model(
    *, state: object, effect: _GenericAttackEffect, unit_instance_id: str
) -> bool:
    if effect.target_kind is not RuleTargetKind.THIS_MODEL:
        return True
    source_model_id = effect.source_model_instance_id
    if source_model_id is None:
        raise GameLifecycleError("Generic THIS_MODEL save effect requires source model.")
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    if type(state) is not GameState:
        raise GameLifecycleError("Generic THIS_MODEL save effect requires GameState.")
    alive_ids = tuple(
        model.model_instance_id
        for model in rules_unit_view_by_id(
            state=state, unit_instance_id=unit_instance_id
        ).alive_models()
    )
    return alive_ids == (source_model_id,)


def _save_options_with_invulnerable_save(
    options: tuple[SaveOption, ...], *, target_number: int, source_id: str
) -> tuple[SaveOption, ...]:
    if target_number < 2 or target_number > 6:
        raise GameLifecycleError("Generic invulnerable save target must be 2-6.")
    replacement = SaveOption(
        save_kind=SaveKind.INVULNERABLE,
        target_number=target_number,
        characteristic_target_number=target_number,
        armor_penetration=0,
        source_rule_ids=(source_id,),
    )
    return (
        *tuple(option for option in options if option.save_kind is not SaveKind.INVULNERABLE),
        replacement,
    )


def generic_rule_modified_weapon_profile(context: WeaponProfileModifierContext) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Generic weapon hooks require WeaponProfileModifierContext.")
    profile = context.weapon_profile
    for effect in _matching_generic_attack_effects(
        state=context.state,
        attacking_unit_instance_id=context.attacking_unit_instance_id,
        attacker_model_instance_id=context.attacker_model_instance_id,
        target_unit_instance_id=context.target_unit_instance_id,
        source_phase=context.source_phase,
        weapon_profile=profile,
        effect_kind=RuleEffectKind.GRANT_WEAPON_ABILITY,
        legacy_attacker_role_allowed=lambda _candidate: True,
        legacy_target_role_allowed=lambda _candidate: False,
    ):
        if not _weapon_scope_matches_profile(effect.parameters, profile):
            continue
        profile = _profile_with_weapon_ability_grant(profile=profile, effect=effect)
    for effect in _matching_generic_attack_effects(
        state=context.state,
        attacking_unit_instance_id=context.attacking_unit_instance_id,
        attacker_model_instance_id=context.attacker_model_instance_id,
        target_unit_instance_id=context.target_unit_instance_id,
        source_phase=context.source_phase,
        weapon_profile=profile,
        effect_kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
        legacy_attacker_role_allowed=lambda _candidate: True,
        legacy_target_role_allowed=lambda _candidate: False,
    ):
        profile = _profile_with_characteristic_modifier(profile=profile, effect=effect)
    return profile


def generic_rule_reroll_permission_context_for_unit(
    *,
    state: object,
    player_id: str,
    unit_instance_id: str,
    model_instance_id: str | None = None,
    roll_type: str,
    timing_window: str,
    target_unit_instance_id: str | None,
) -> GenericRuleRerollPermissionContext | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR reroll lookup requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    requested_model_id = (
        None
        if model_instance_id is None
        else _validate_identifier("model_instance_id", model_instance_id)
    )
    requested_roll_type = _validate_identifier("roll_type", roll_type)
    requested_timing_window = _validate_identifier("timing_window", timing_window)
    requested_target_id = (
        None
        if target_unit_instance_id is None
        else _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    )
    candidates: list[GenericRuleRerollPermissionContext] = []
    target_ids = (requested_target_id,) if requested_target_id is not None else ()
    for effect in _matching_generic_attack_effects(
        state=state,
        attacking_unit_instance_id=requested_unit_id,
        attacker_model_instance_id=requested_model_id,
        target_unit_instance_id=requested_target_id,
        source_phase=None,
        effect_kind=RuleEffectKind.REROLL_PERMISSION,
        legacy_attacker_role_allowed=lambda _candidate: True,
        legacy_target_role_allowed=lambda _candidate: False,
        target_unit_lookup_ids=target_ids,
    ):
        if effect.persisting_effect.owner_player_id != requested_player_id:
            continue
        if not _roll_type_matches(effect.parameters, expected=requested_roll_type):
            continue
        expected_window = _timing_window_for_roll_type(effect.parameters, requested_roll_type)
        if expected_window != requested_timing_window:
            continue
        permission = RerollPermission(
            source_id=_modifier_source_id(effect),
            timing_window=requested_timing_window,
            owning_player_id=requested_player_id,
            eligible_roll_type=requested_roll_type,
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        )
        candidates.append(
            GenericRuleRerollPermissionContext(
                permission=permission,
                source_payload=_generic_source_payload(effect, requested_target_id),
            )
        )
    if len(candidates) > 1:
        raise GameLifecycleError("Multiple generic RuleIR reroll permissions are available.")
    return candidates[0] if candidates else None


def generic_rule_modified_unit_characteristic(
    context: UnitCharacteristicModifierContext,
) -> int:
    if type(context) is not UnitCharacteristicModifierContext:
        raise GameLifecycleError(
            "Generic unit characteristic hooks require UnitCharacteristicModifierContext."
        )
    current = context.current_value
    for effect in _matching_generic_unit_effects(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
        effect_kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
    ):
        if _characteristic_parameter(effect.parameters) is not context.characteristic:
            continue
        current = max(0, current + _required_int_parameter(effect.parameters, key="delta"))
    return current


def generic_rule_modified_movement_inches(
    context: MovementBudgetModifierContext,
) -> float:
    if type(context) is not MovementBudgetModifierContext:
        raise GameLifecycleError("Generic movement hooks require MovementBudgetModifierContext.")
    current = context.current_movement_inches
    for effect in _matching_generic_unit_effects(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
        effect_kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
    ):
        if _characteristic_parameter(effect.parameters) is not Characteristic.MOVEMENT:
            continue
        current = max(0.0, current + _required_int_parameter(effect.parameters, key="delta"))
    for effect in _matching_generic_unit_effects(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
        effect_kind=RuleEffectKind.MODIFY_MOVE_DISTANCE,
    ):
        current = max(0.0, current + _required_numeric_parameter(effect.parameters, key="delta"))
    return current


def generic_rule_modified_objective_control(
    context: ObjectiveControlModifierContext,
) -> int:
    if type(context) is not ObjectiveControlModifierContext:
        raise GameLifecycleError(
            "Generic Objective Control hooks require ObjectiveControlModifierContext."
        )
    current = context.current_objective_control
    for effect in _matching_generic_unit_effects(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
        effect_kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
    ):
        if _characteristic_parameter(effect.parameters) is not Characteristic.OBJECTIVE_CONTROL:
            continue
        current = max(0, current + _required_int_parameter(effect.parameters, key="delta"))
    return current


def generic_rule_charge_roll_modifiers(
    context: ChargeRollModifierContext,
) -> tuple[RollModifier, ...]:
    if type(context) is not ChargeRollModifierContext:
        raise GameLifecycleError("Generic charge hooks require ChargeRollModifierContext.")
    from warhammer40k_core.engine.stratagems_generic_rule_ir_runtime import (
        charge_roll_modifiers_from_generic_rule_ir,
    )

    return charge_roll_modifiers_from_generic_rule_ir(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
        current_roll_modifiers=context.current_roll_modifiers,
    )


def _dice_roll_modifier_for_attack(
    *,
    state: object,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str | None,
    target_unit_instance_id: str,
    source_phase: object,
    expected_roll_type: str,
    legacy_attacker_role_allowed: Callable[[_GenericAttackEffect], bool],
    legacy_target_role_allowed: Callable[[_GenericAttackEffect], bool],
    weapon_profile: WeaponProfile | None = None,
    attack_strength: int | None = None,
    target_toughness: int | None = None,
) -> int:
    total = 0
    for effect in _matching_generic_attack_effects(
        state=state,
        attacking_unit_instance_id=attacking_unit_instance_id,
        attacker_model_instance_id=attacker_model_instance_id,
        target_unit_instance_id=target_unit_instance_id,
        source_phase=source_phase,
        attack_strength=attack_strength,
        target_toughness=target_toughness,
        effect_kind=RuleEffectKind.MODIFY_DICE_ROLL,
        legacy_attacker_role_allowed=legacy_attacker_role_allowed,
        legacy_target_role_allowed=legacy_target_role_allowed,
        weapon_profile=weapon_profile,
    ):
        if not _roll_type_matches(effect.parameters, expected=expected_roll_type):
            continue
        total += _required_int_parameter(effect.parameters, key="delta")
    return total


def _matching_generic_unit_effects(
    *,
    state: object,
    unit_instance_id: str,
    effect_kind: RuleEffectKind,
) -> tuple[_GenericAttackEffect, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR unit hooks require GameState.")
    unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    matches: list[_GenericAttackEffect] = []
    for persisting_effect in state.persisting_effects_for_unit(unit_id):
        generic_effect = _generic_attack_effect_or_none(
            persisting_effect=persisting_effect,
            role="attacker",
            expected_effect_kind=effect_kind,
        )
        if generic_effect is None:
            continue
        if not _generic_unit_effect_applies(effect=generic_effect, unit_instance_id=unit_id):
            continue
        matches.append(generic_effect)
    return tuple(sorted(matches, key=lambda effect: _modifier_source_id(effect)))


def _matching_generic_attack_effects(
    *,
    state: object,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str | None = None,
    target_unit_instance_id: str | None,
    source_phase: object,
    effect_kind: RuleEffectKind,
    legacy_attacker_role_allowed: Callable[[_GenericAttackEffect], bool],
    legacy_target_role_allowed: Callable[[_GenericAttackEffect], bool],
    target_unit_lookup_ids: tuple[str | None, ...] | None = None,
    weapon_profile: WeaponProfile | None = None,
    attack_strength: int | None = None,
    target_toughness: int | None = None,
) -> tuple[_GenericAttackEffect, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR attack hooks require GameState.")
    physical_attacker_id = _validate_identifier(
        "attacking_unit_instance_id",
        attacking_unit_instance_id,
    )
    attacker_model_id = (
        None
        if attacker_model_instance_id is None
        else _validate_identifier("attacker_model_instance_id", attacker_model_instance_id)
    )
    physical_target_id = (
        None
        if target_unit_instance_id is None
        else _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    attacker_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=physical_attacker_id,
    )
    attacker_id = attacker_rules_unit.unit_instance_id
    if attacker_model_id is not None:
        owning_component_id = attacker_rules_unit.component_unit_id_for_model(attacker_model_id)
        if physical_attacker_id not in {attacker_id, owning_component_id}:
            raise GameLifecycleError(
                "Generic RuleIR attacker model does not belong to the supplied component unit."
            )
    target_id = (
        None
        if physical_target_id is None
        else rules_unit_view_by_id(
            state=state,
            unit_instance_id=physical_target_id,
        ).unit_instance_id
    )
    target_lookup_ids = (
        (physical_target_id,) if target_unit_lookup_ids is None else target_unit_lookup_ids
    )
    role_unit_ids: tuple[tuple[AttackRole, str], ...] = (("attacker", attacker_id),)
    for raw_target_id in target_lookup_ids:
        if raw_target_id is None:
            continue
        canonical_target_id = rules_unit_view_by_id(
            state=state,
            unit_instance_id=_validate_identifier(
                "target_unit_instance_id",
                raw_target_id,
            ),
        ).unit_instance_id
        role_unit_ids = (
            *role_unit_ids,
            ("target", canonical_target_id),
        )
    matches: list[_GenericAttackEffect] = []
    seen: set[tuple[str, AttackRole]] = set()
    for role, unit_id in role_unit_ids:
        for persisting_effect in state.persisting_effects_for_unit(unit_id):
            generic_effect = _generic_attack_effect_or_none(
                persisting_effect=persisting_effect,
                role=role,
                expected_effect_kind=effect_kind,
            )
            if generic_effect is None:
                continue
            if not _generic_effect_role_applies(
                effect=generic_effect,
                role=role,
                attacking_unit_instance_id=attacker_id,
                target_unit_instance_id=target_id,
                legacy_attacker_role_allowed=legacy_attacker_role_allowed,
                legacy_target_role_allowed=legacy_target_role_allowed,
            ):
                continue
            if not _generic_effect_context_applies(
                state=state,
                effect=generic_effect,
                attacking_unit_instance_id=attacker_id,
                attacker_model_instance_id=attacker_model_id,
                target_unit_instance_id=target_id,
                source_phase=source_phase,
                weapon_profile=weapon_profile,
                attack_strength=attack_strength,
                target_toughness=target_toughness,
            ):
                continue
            key = (generic_effect.persisting_effect.effect_id, role)
            if key in seen:
                continue
            seen.add(key)
            matches.append(generic_effect)
    return tuple(sorted(matches, key=lambda effect: _modifier_source_id(effect)))


def _generic_attack_effect_or_none(
    *,
    persisting_effect: PersistingEffect,
    role: AttackRole,
    expected_effect_kind: RuleEffectKind,
) -> _GenericAttackEffect | None:
    payload = persisting_effect.effect_payload
    if not isinstance(payload, dict):
        return None
    if payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
        return None
    effect_payload = payload.get("effect")
    if not isinstance(effect_payload, dict):
        raise GameLifecycleError("Generic RuleIR effect payload must include effect object.")
    effect_kind = _effect_kind_from_payload(effect_payload)
    if effect_kind is not expected_effect_kind:
        return None
    return _GenericAttackEffect(
        persisting_effect=persisting_effect,
        role=role,
        source_id=_required_identifier_payload(payload, "source_id"),
        rule_id=_required_identifier_payload(payload, "rule_id"),
        rule_ir_hash=_required_identifier_payload(payload, "rule_ir_hash"),
        clause_id=_required_identifier_payload(payload, "clause_id"),
        target_kind=_target_kind_from_payload(payload),
        effect_kind=effect_kind,
        parameters=generic_rule_parameters_from_effect_payload(effect_payload),
        conditions=generic_rule_conditions_from_payload(payload),
        source_model_instance_id=generic_rule_source_model_instance_id_from_payload(payload),
    )


def _generic_effect_role_applies(
    *,
    effect: _GenericAttackEffect,
    role: AttackRole,
    attacking_unit_instance_id: str,
    target_unit_instance_id: str | None,
    legacy_attacker_role_allowed: Callable[[_GenericAttackEffect], bool],
    legacy_target_role_allowed: Callable[[_GenericAttackEffect], bool],
) -> bool:
    requested_role = _attack_role_parameter(effect.parameters)
    target_ids = set(effect.persisting_effect.target_unit_instance_ids)
    if requested_role is not None:
        if requested_role != role:
            return False
        if role == "attacker":
            return attacking_unit_instance_id in target_ids
        if target_unit_instance_id is None:
            return False
        return target_unit_instance_id in target_ids
    target_kind = effect.target_kind
    if role == "attacker":
        return (
            attacking_unit_instance_id in target_ids
            and (target_kind is None or target_kind in _ATTACKER_TARGET_KINDS)
            and legacy_attacker_role_allowed(effect)
        )
    if target_unit_instance_id is None or target_unit_instance_id not in target_ids:
        return False
    if target_kind in _TARGET_TARGET_KINDS:
        return True
    if target_kind is None or target_kind in _LEGACY_SELF_TARGET_KINDS:
        return legacy_target_role_allowed(effect)
    return False


def _generic_unit_effect_applies(
    *,
    effect: _GenericAttackEffect,
    unit_instance_id: str,
) -> bool:
    if unit_instance_id not in effect.persisting_effect.target_unit_instance_ids:
        return False
    requested_role = _attack_role_parameter(effect.parameters)
    if requested_role is not None and requested_role != "attacker":
        return False
    return effect.target_kind is None or effect.target_kind in _ATTACKER_TARGET_KINDS


def _generic_effect_context_applies(
    *,
    state: object,
    effect: _GenericAttackEffect,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str | None,
    target_unit_instance_id: str | None,
    source_phase: object,
    weapon_profile: WeaponProfile | None,
    attack_strength: int | None,
    target_toughness: int | None,
) -> bool:
    if not generic_rule_source_model_applies(
        target_kind=effect.target_kind,
        source_model_instance_id=effect.source_model_instance_id,
        attacker_model_instance_id=attacker_model_instance_id,
        requires_source_model_instance_id=generic_rule_conditions_require_source_model_instance_id(
            effect.conditions
        ),
    ):
        return False
    if not _generic_effect_source_phase_applies(effect=effect, source_phase=source_phase):
        return False
    if not _generic_effect_required_ability_gate_applies(
        state=state,
        effect=effect,
        attacking_unit_instance_id=attacking_unit_instance_id,
    ):
        return False
    if not _generic_effect_charge_move_gate_applies(
        state=state,
        effect=effect,
        attacking_unit_instance_id=attacking_unit_instance_id,
    ):
        return False
    if not _generic_effect_target_keyword_gate_applies(
        state=state,
        effect=effect,
        target_unit_instance_id=target_unit_instance_id,
    ):
        return False
    if not _generic_effect_selected_target_gate_applies(
        state=state,
        effect=effect,
        target_unit_instance_id=target_unit_instance_id,
    ):
        return False
    if not _generic_effect_required_keyword_sequence_applies(
        state=state,
        effect=effect,
        attacking_unit_instance_id=attacking_unit_instance_id,
        target_unit_instance_id=target_unit_instance_id,
    ):
        return False
    if not generic_rule_target_proximity_keyword_gate_applies(
        state=state,
        parameters=effect.parameters,
        attacking_unit_instance_id=attacking_unit_instance_id,
        target_unit_instance_id=target_unit_instance_id,
    ):
        return False
    if not generic_rule_target_allegiance_applies(
        state=state,
        allegiances=generic_rule_target_allegiance_values(
            parameters=effect.parameters,
            conditions=effect.conditions,
        ),
        attacking_unit_instance_id=attacking_unit_instance_id,
        target_unit_instance_id=target_unit_instance_id,
    ):
        return False
    if not _generic_effect_weapon_scope_applies(effect=effect, weapon_profile=weapon_profile):
        return False
    if not _generic_effect_waaagh_gate_applies(
        state=state,
        effect=effect,
        attacking_unit_instance_id=attacking_unit_instance_id,
    ):
        return False
    return _generic_effect_target_constraint_applies(
        state=state,
        effect=effect,
        attacking_unit_instance_id=attacking_unit_instance_id,
        target_unit_instance_id=target_unit_instance_id,
        attack_strength=attack_strength,
        target_toughness=target_toughness,
    )


def _generic_effect_source_phase_applies(
    *,
    effect: _GenericAttackEffect,
    source_phase: object,
) -> bool:
    required_phase = effect.parameters.get("source_phase")
    if required_phase is None:
        return True
    if type(required_phase) is not str:
        raise GameLifecycleError("Generic RuleIR source_phase must be a string.")
    phase_value = _source_phase_value_or_none(source_phase)
    if phase_value is None:
        return False
    return phase_value == required_phase


def _generic_effect_selected_target_gate_applies(
    *,
    state: object,
    effect: _GenericAttackEffect,
    target_unit_instance_id: str | None,
) -> bool:
    selected_target_id = effect.parameters.get("selected_target_unit_instance_id")
    if selected_target_id is None:
        return True
    if type(selected_target_id) is not str:
        raise GameLifecycleError(
            "Generic RuleIR selected_target_unit_instance_id must be a string."
        )
    if (
        effect.target_kind is RuleTargetKind.SELECTED_UNIT
        and _attack_role_parameter(effect.parameters) == "attacker"
    ):
        return True
    if target_unit_instance_id is None:
        return False
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR selected-target gate requires GameState.")
    selected_rules_unit_id = rules_unit_view_by_id(
        state=state,
        unit_instance_id=_validate_identifier(
            "selected_target_unit_instance_id",
            selected_target_id,
        ),
    ).unit_instance_id
    current_target_rules_unit_id = rules_unit_view_by_id(
        state=state,
        unit_instance_id=_validate_identifier(
            "target_unit_instance_id",
            target_unit_instance_id,
        ),
    ).unit_instance_id
    return current_target_rules_unit_id == selected_rules_unit_id


def _generic_effect_waaagh_gate_applies(
    *,
    state: object,
    effect: _GenericAttackEffect,
    attacking_unit_instance_id: str,
) -> bool:
    required = effect.parameters.get("requires_waaagh_active_for_unit")
    if required is None or required is False:
        return True
    if required is not True:
        raise GameLifecycleError("Generic RuleIR requires_waaagh_active_for_unit must be boolean.")
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.orks.army_rule import (
        waaagh_is_active_for_unit,
    )
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR Waaagh gate requires GameState.")
    return waaagh_is_active_for_unit(state, unit_instance_id=attacking_unit_instance_id)


def _generic_effect_required_ability_gate_applies(
    *,
    state: object,
    effect: _GenericAttackEffect,
    attacking_unit_instance_id: str,
) -> bool:
    required_ability = effect.parameters.get("ability_required")
    if required_ability is None:
        return True
    if type(required_ability) is not str:
        raise GameLifecycleError("Generic RuleIR ability_required must be a string.")
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR ability_required gate requires GameState.")
    for persisting_effect in state.persisting_effects_for_unit(attacking_unit_instance_id):
        generic_effect = _generic_attack_effect_or_none(
            persisting_effect=persisting_effect,
            role="attacker",
            expected_effect_kind=RuleEffectKind.GRANT_ABILITY,
        )
        if generic_effect is None:
            continue
        if (
            attacking_unit_instance_id
            not in generic_effect.persisting_effect.target_unit_instance_ids
        ):
            continue
        if _required_string_parameter(generic_effect.parameters, key="ability") == required_ability:
            return True
    return False


def _generic_effect_charge_move_gate_applies(
    *,
    state: object,
    effect: _GenericAttackEffect,
    attacking_unit_instance_id: str,
) -> bool:
    required = effect.parameters.get("requires_charge_move_this_turn")
    if required is None or required is False:
        return True
    if required is not True:
        raise GameLifecycleError("Generic RuleIR requires_charge_move_this_turn must be boolean.")
    from warhammer40k_core.engine.fight_order import CHARGE_FIGHTS_FIRST_EFFECT_KIND
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR charge-move gate requires GameState.")
    for persisting_effect in state.persisting_effects_for_unit(attacking_unit_instance_id):
        payload = persisting_effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") == CHARGE_FIGHTS_FIRST_EFFECT_KIND:
            return True
    return False


def _generic_effect_target_keyword_gate_applies(
    *,
    state: object,
    effect: _GenericAttackEffect,
    target_unit_instance_id: str | None,
) -> bool:
    required_keyword = effect.parameters.get("target_required_keyword")
    if required_keyword is None:
        return True
    if type(required_keyword) is not str:
        raise GameLifecycleError("Generic RuleIR target_required_keyword must be a string.")
    if target_unit_instance_id is None:
        return False
    return _unit_has_keyword(
        state=state,
        unit_instance_id=target_unit_instance_id,
        keyword=required_keyword,
    )


def _generic_effect_required_keyword_sequence_applies(
    *,
    state: object,
    effect: _GenericAttackEffect,
    attacking_unit_instance_id: str,
    target_unit_instance_id: str | None,
) -> bool:
    required_keywords = _keyword_sequence_parameter(
        effect.parameters.get("required_keyword_sequence")
    )
    required_keyword = effect.parameters.get("required_keyword")
    if required_keyword is not None:
        if type(required_keyword) is not str:
            raise GameLifecycleError("Generic RuleIR required_keyword must be a string.")
        required_keywords = (*required_keywords, required_keyword)
    if not required_keywords:
        return True
    if effect.role == "attacker":
        unit_id = attacking_unit_instance_id
    else:
        if target_unit_instance_id is None:
            return False
        unit_id = target_unit_instance_id
    return all(
        _unit_has_keyword(state=state, unit_instance_id=unit_id, keyword=keyword)
        for keyword in required_keywords
    )


def _generic_effect_weapon_scope_applies(
    *,
    effect: _GenericAttackEffect,
    weapon_profile: WeaponProfile | None,
) -> bool:
    if not any(key in effect.parameters for key in ("weapon_scope", "weapon_name", "weapon_names")):
        return True
    if weapon_profile is None:
        return False
    return rule_ir_weapon_selector_applies(
        parameters=effect.parameters,
        profile=weapon_profile,
    )


def _generic_effect_target_constraint_applies(
    *,
    state: object,
    effect: _GenericAttackEffect,
    attacking_unit_instance_id: str,
    target_unit_instance_id: str | None,
    attack_strength: int | None,
    target_toughness: int | None,
) -> bool:
    return generic_rule_target_constraints_apply(
        state=state,
        constraints=generic_rule_target_constraint_values(
            parameters=effect.parameters,
            conditions=effect.conditions,
        ),
        attacking_unit_instance_id=attacking_unit_instance_id,
        target_unit_instance_id=target_unit_instance_id,
        attack_strength=attack_strength,
        target_toughness=target_toughness,
    )


def _source_phase_value_or_none(source_phase: object) -> str | None:
    if source_phase is None:
        return None
    if type(source_phase) is BattlePhase:
        value = source_phase.value
    elif type(source_phase) is str:
        value = source_phase
    else:
        raise GameLifecycleError("Generic RuleIR source phase must be a phase token.")
    return _validate_identifier("source_phase", value)


def _roll_type_matches(parameters: dict[str, JsonValue], *, expected: str) -> bool:
    roll_type = _required_string_parameter(parameters, key="roll_type")
    requested = _roll_type_suffix(expected)
    return _roll_type_suffix(roll_type) == requested


def _roll_type_suffix(roll_type: str) -> str:
    token = _validate_identifier("roll_type", roll_type)
    return token.rsplit(".", maxsplit=1)[-1]


def _timing_window_for_roll_type(
    parameters: dict[str, JsonValue],
    requested_roll_type: str,
) -> str:
    timing_window = parameters.get("timing_window")
    if timing_window is not None:
        if type(timing_window) is not str:
            raise GameLifecycleError("Generic RuleIR timing_window must be a string.")
        return _validate_identifier("timing_window", timing_window)
    roll_suffix = _roll_type_suffix(_required_string_parameter(parameters, key="roll_type"))
    requested_suffix = _roll_type_suffix(requested_roll_type)
    if roll_suffix != requested_suffix:
        raise GameLifecycleError("Generic RuleIR reroll roll_type drift.")
    return requested_roll_type


def _save_option_with_roll_modifier(
    option: SaveOption,
    delta: int,
    source_id: str,
) -> SaveOption:
    if type(option) is not SaveOption:
        raise GameLifecycleError("Generic save modifier requires SaveOption.")
    modified_target = max(2, option.target_number - delta)
    modified_characteristic_target = max(2, option.characteristic_target_number - delta)
    source_ids = option.source_rule_ids
    if source_id not in source_ids:
        source_ids = tuple(sorted((*source_ids, source_id)))
    return replace(
        option,
        target_number=modified_target,
        characteristic_target_number=modified_characteristic_target,
        source_rule_ids=source_ids,
    )


def _profile_with_weapon_ability_grant(
    *,
    profile: WeaponProfile,
    effect: _GenericAttackEffect,
) -> WeaponProfile:
    return rule_ir_weapon_ability_granted_profile(
        parameters=effect.parameters,
        profile=profile,
        source_id=_modifier_source_id(effect),
    )


def _profile_with_characteristic_modifier(
    *,
    profile: WeaponProfile,
    effect: _GenericAttackEffect,
) -> WeaponProfile:
    return rule_ir_modified_weapon_profile(
        parameters=effect.parameters,
        profile=profile,
        source_id=_modifier_source_id(effect),
    )


def _weapon_scope_matches_profile(
    parameters: dict[str, JsonValue],
    profile: WeaponProfile,
) -> bool:
    return rule_ir_weapon_selector_applies(parameters=parameters, profile=profile)


def _characteristic_parameter(parameters: dict[str, JsonValue]) -> Characteristic:
    value = _required_string_parameter(parameters, key="characteristic")
    try:
        return characteristic_from_token(value)
    except ValueError as exc:
        raise GameLifecycleError("Generic characteristic modifier is unsupported.") from exc


def _effect_kind_from_payload(effect_payload: dict[str, JsonValue]) -> RuleEffectKind:
    value = effect_payload.get("kind")
    if type(value) is not str:
        raise GameLifecycleError("Generic RuleIR effect kind must be a string.")
    try:
        return RuleEffectKind(value)
    except ValueError as exc:
        raise GameLifecycleError("Generic RuleIR effect kind is unsupported.") from exc


def _target_kind_from_payload(payload: dict[str, JsonValue]) -> RuleTargetKind | None:
    target_payload = payload.get("target")
    if target_payload is None:
        return None
    if not isinstance(target_payload, dict):
        raise GameLifecycleError("Generic RuleIR target payload must be an object.")
    value = target_payload.get("kind")
    if type(value) is not str:
        raise GameLifecycleError("Generic RuleIR target kind must be a string.")
    try:
        return RuleTargetKind(value)
    except ValueError as exc:
        raise GameLifecycleError("Generic RuleIR target kind is unsupported.") from exc


def _attack_role_parameter(parameters: dict[str, JsonValue]) -> AttackRole | None:
    value = parameters.get("attack_role")
    if value is None:
        return None
    if value not in {"attacker", "target"}:
        raise GameLifecycleError("Generic RuleIR attack_role must be attacker or target.")
    return cast(AttackRole, value)


def _required_string_parameter(parameters: dict[str, JsonValue], *, key: str) -> str:
    value = parameters.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Generic RuleIR parameter {key} must be a string.")
    return value


def _required_int_parameter(parameters: dict[str, JsonValue], *, key: str) -> int:
    value = parameters.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Generic RuleIR parameter {key} must be an int.")
    return value


def _minimum_unmodified_success_parameter(parameters: dict[str, JsonValue]) -> int:
    value = _required_int_parameter(parameters, key="minimum_unmodified_success")
    if not 2 <= value <= 6:
        raise GameLifecycleError(
            "Generic RuleIR parameter minimum_unmodified_success must be between 2 and 6."
        )
    return value


def _targeting_rule_gate_applies(
    parameters: dict[str, JsonValue],
    *,
    targeting_rule_ids: tuple[str, ...],
) -> bool:
    required_rule = parameters.get("required_targeting_rule_id")
    if required_rule is None:
        return True
    if type(required_rule) is not str:
        raise GameLifecycleError("Generic RuleIR required_targeting_rule_id must be a string.")
    return _validate_identifier("required_targeting_rule_id", required_rule) in targeting_rule_ids


def _required_numeric_parameter(parameters: dict[str, JsonValue], *, key: str) -> float:
    value = parameters.get(key)
    if type(value) not in {int, float}:
        raise GameLifecycleError(f"Generic RuleIR parameter {key} must be numeric.")
    return float(cast(int | float, value))


def _required_identifier_payload(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Generic RuleIR payload {key} must be a string.")
    return _validate_identifier(key, value)


def _modifier_source_id(effect: _GenericAttackEffect) -> str:
    return _validate_identifier(
        "generic modifier source_id",
        f"{effect.source_id}:{effect.clause_id}:{effect.effect_kind.value}",
    )


def _generic_source_payload(
    effect: _GenericAttackEffect,
    target_unit_instance_id: str | None,
) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "effect_kind": GENERIC_RULE_EFFECT_KIND,
        "rule_id": effect.rule_id,
        "source_id": effect.source_id,
        "rule_ir_hash": effect.rule_ir_hash,
        "clause_id": effect.clause_id,
        "effect_id": effect.persisting_effect.effect_id,
        "target_role": effect.role,
        "target_kind": None if effect.target_kind is None else effect.target_kind.value,
    }
    if target_unit_instance_id is not None:
        payload["target_unit_instance_id"] = target_unit_instance_id
    conditional_hit_reroll = _conditional_hit_reroll_payload(effect)
    if conditional_hit_reroll is not None:
        payload["conditional_hit_reroll"] = conditional_hit_reroll
    conditional_wound_reroll = _conditional_wound_reroll_payload(effect)
    if conditional_wound_reroll is not None:
        payload["conditional_wound_reroll"] = conditional_wound_reroll
    conditional_save_reroll = _conditional_save_reroll_payload(effect)
    if conditional_save_reroll is not None:
        payload["conditional_save_reroll"] = conditional_save_reroll
    return payload


def _conditional_hit_reroll_payload(
    effect: _GenericAttackEffect,
) -> dict[str, JsonValue] | None:
    if effect.effect_kind is not RuleEffectKind.REROLL_PERMISSION:
        return None
    if not _roll_type_matches(effect.parameters, expected="hit"):
        return None
    reroll_value = effect.parameters.get("reroll_unmodified_value")
    if reroll_value is None:
        return None
    if type(reroll_value) is not int:
        raise GameLifecycleError("Generic RuleIR hit reroll_unmodified_value must be an int.")
    if reroll_value < 1 or reroll_value > 6:
        raise GameLifecycleError("Generic RuleIR hit reroll_unmodified_value must be 1-6.")
    return {"reroll_unmodified_values": [reroll_value]}


def _conditional_wound_reroll_payload(
    effect: _GenericAttackEffect,
) -> dict[str, JsonValue] | None:
    reroll_values: list[JsonValue] = []
    reroll_value = effect.parameters.get("reroll_unmodified_value")
    if reroll_value is not None:
        if type(reroll_value) is not int:
            raise GameLifecycleError("Generic RuleIR reroll_unmodified_value must be an int.")
        reroll_values.append(reroll_value)
    full_reroll = effect.parameters.get("full_reroll_if_target_within_objective_range")
    if full_reroll is None:
        full_reroll = False
    if type(full_reroll) is not bool:
        raise GameLifecycleError(
            "Generic RuleIR full_reroll_if_target_within_objective_range must be boolean."
        )
    full_battle_shock_reroll = effect.parameters.get("full_reroll_if_target_battle_shocked")
    if full_battle_shock_reroll is None:
        full_battle_shock_reroll = False
    if type(full_battle_shock_reroll) is not bool:
        raise GameLifecycleError(
            "Generic RuleIR full_reroll_if_target_battle_shocked must be boolean."
        )
    required_keyword = effect.parameters.get("full_reroll_required_attacker_keyword")
    if required_keyword is not None and type(required_keyword) is not str:
        raise GameLifecycleError(
            "Generic RuleIR full_reroll_required_attacker_keyword must be a string."
        )
    if (
        not reroll_values
        and full_reroll is False
        and full_battle_shock_reroll is False
        and required_keyword is None
    ):
        return None
    payload: dict[str, JsonValue] = {
        "reroll_unmodified_values": reroll_values,
    }
    if full_reroll:
        payload["full_reroll_if_target_within_objective_range"] = True
    if full_battle_shock_reroll:
        payload["full_reroll_if_target_battle_shocked"] = True
    if required_keyword is not None:
        payload["full_reroll_required_attacker_keyword"] = required_keyword
    return payload


def _conditional_save_reroll_payload(
    effect: _GenericAttackEffect,
) -> dict[str, JsonValue] | None:
    if effect.effect_kind is not RuleEffectKind.REROLL_PERMISSION:
        return None
    roll_type = _required_string_parameter(effect.parameters, key="roll_type")
    if not roll_type.startswith("attack_sequence.save."):
        return None
    reroll_value = effect.parameters.get("reroll_unmodified_value")
    if reroll_value is None:
        return None
    if type(reroll_value) is not int:
        raise GameLifecycleError("Generic RuleIR save reroll_unmodified_value must be an int.")
    if reroll_value < 1 or reroll_value > 6:
        raise GameLifecycleError("Generic RuleIR save reroll_unmodified_value must be 1-6.")
    return {"reroll_unmodified_values": [reroll_value]}


def _unit_has_keyword(*, state: object, unit_instance_id: str, keyword: str) -> bool:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR keyword gate requires GameState.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=_validate_identifier("unit_instance_id", unit_instance_id),
    )
    return unit_has_required_keywords(
        unit_keywords=rules_unit.keywords,
        faction_keywords=rules_unit.faction_keywords,
        required_keywords=(_validate_identifier("keyword", keyword),),
    )


def _keyword_sequence_parameter(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise GameLifecycleError("Generic RuleIR required_keyword_sequence must be a list.")
    keywords: list[str] = []
    for item in cast(list[object], value):
        if type(item) is not str:
            raise GameLifecycleError(
                "Generic RuleIR required_keyword_sequence must contain strings."
            )
        keywords.append(_validate_identifier("required_keyword_sequence", item))
    if not keywords:
        raise GameLifecycleError("Generic RuleIR required_keyword_sequence must not be empty.")
    return tuple(keywords)


_validate_identifier = IdentifierValidator(GameLifecycleError)
