from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal, cast

from warhammer40k_core.core.attributes import (
    Characteristic,
    CharacteristicValue,
    characteristic_from_token,
)
from warhammer40k_core.core.dice import RerollComponentSelectionPolicy, RerollPermission
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AttackProfile,
    DamageProfile,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
    WeaponProfileError,
    weapon_keyword_from_token,
)
from warhammer40k_core.engine.battlefield_state import (
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    DamageRollModifierContext,
    HitRollModifierContext,
    MovementBudgetModifierContext,
    ObjectiveControlModifierContext,
    SaveOptionModifierContext,
    UnitCharacteristicModifierContext,
    WeaponProfileModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.saves import SaveOption
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.volume import Model
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


def generic_rule_hit_roll_modifier(context: HitRollModifierContext) -> int:
    if type(context) is not HitRollModifierContext:
        raise GameLifecycleError("Generic hit roll hooks require HitRollModifierContext.")
    return _dice_roll_modifier_for_attack(
        state=context.state,
        attacking_unit_instance_id=context.attacking_unit_instance_id,
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
    for effect in _matching_generic_attack_effects(
        state=context.state,
        attacking_unit_instance_id=context.attacking_unit_instance_id,
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


def generic_rule_modified_weapon_profile(context: WeaponProfileModifierContext) -> WeaponProfile:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Generic weapon hooks require WeaponProfileModifierContext.")
    profile = context.weapon_profile
    for effect in _matching_generic_attack_effects(
        state=context.state,
        attacking_unit_instance_id=context.attacking_unit_instance_id,
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
    roll_type: str,
    timing_window: str,
    target_unit_instance_id: str | None,
) -> GenericRuleRerollPermissionContext | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR reroll lookup requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
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


def _dice_roll_modifier_for_attack(
    *,
    state: object,
    attacking_unit_instance_id: str,
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
    attacker_id = _validate_identifier("attacking_unit_instance_id", attacking_unit_instance_id)
    target_id = (
        None
        if target_unit_instance_id is None
        else _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    )
    target_lookup_ids = (target_id,) if target_unit_lookup_ids is None else target_unit_lookup_ids
    role_unit_ids: tuple[tuple[AttackRole, str], ...] = (("attacker", attacker_id),)
    for raw_target_id in target_lookup_ids:
        if raw_target_id is None:
            continue
        role_unit_ids = (
            *role_unit_ids,
            ("target", _validate_identifier("target_unit_instance_id", raw_target_id)),
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
        parameters=_parameters_from_effect_payload(effect_payload),
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
    target_unit_instance_id: str | None,
    source_phase: object,
    weapon_profile: WeaponProfile | None,
    attack_strength: int | None,
    target_toughness: int | None,
) -> bool:
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
    if not _generic_effect_required_keyword_sequence_applies(
        state=state,
        effect=effect,
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
    if "weapon_scope" not in effect.parameters:
        return True
    if weapon_profile is None:
        return False
    return _weapon_scope_matches_profile(effect.parameters, weapon_profile)


def _generic_effect_target_constraint_applies(
    *,
    state: object,
    effect: _GenericAttackEffect,
    attacking_unit_instance_id: str,
    target_unit_instance_id: str | None,
    attack_strength: int | None,
    target_toughness: int | None,
) -> bool:
    constraint = effect.parameters.get("target_constraint")
    if constraint is None:
        return True
    if type(constraint) is not str:
        raise GameLifecycleError("Generic RuleIR target_constraint must be a string.")
    if constraint == "closest_eligible_target_within_18":
        if target_unit_instance_id is None:
            return False
        return _target_is_closest_enemy_within_distance(
            state=state,
            attacking_unit_instance_id=attacking_unit_instance_id,
            target_unit_instance_id=target_unit_instance_id,
            distance_inches=18.0,
        )
    if constraint == "attack_strength_greater_than_target_toughness":
        if attack_strength is None or target_toughness is None:
            return False
        return attack_strength > target_toughness
    if constraint == "eligible_unit_within_12":
        if target_unit_instance_id is None:
            return False
        return _target_is_enemy_within_distance(
            state=state,
            attacking_unit_instance_id=attacking_unit_instance_id,
            target_unit_instance_id=target_unit_instance_id,
            distance_inches=12.0,
        )
    raise GameLifecycleError("Unsupported generic RuleIR target_constraint.")


def _source_phase_value_or_none(source_phase: object) -> str | None:
    if source_phase is None:
        return None
    value = getattr(source_phase, "value", source_phase)
    if type(value) is not str:
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
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Generic weapon ability grant requires WeaponProfile.")
    keyword = _weapon_keyword_parameter(effect.parameters)
    ability = _weapon_ability_descriptor(effect.parameters, keyword=keyword)
    keywords = profile.keywords
    if keyword not in keywords:
        keywords = tuple(sorted((*keywords, keyword), key=lambda value: value.value))
    abilities = profile.abilities
    if ability is not None and all(
        existing.ability_id != ability.ability_id for existing in abilities
    ):
        abilities = tuple(sorted((*abilities, ability), key=lambda value: value.ability_id))
    source_ids = _source_ids_with(profile.source_ids, _modifier_source_id(effect))
    if (
        keywords == profile.keywords
        and abilities == profile.abilities
        and source_ids == profile.source_ids
    ):
        return profile
    return replace(profile, keywords=keywords, abilities=abilities, source_ids=source_ids)


def _profile_with_characteristic_modifier(
    *,
    profile: WeaponProfile,
    effect: _GenericAttackEffect,
) -> WeaponProfile:
    characteristic = _characteristic_parameter(effect.parameters)
    delta = _required_int_parameter(effect.parameters, key="delta")
    source_ids = _source_ids_with(profile.source_ids, _modifier_source_id(effect))
    if characteristic is Characteristic.STRENGTH:
        return replace(
            profile,
            strength=_modified_characteristic_value(profile.strength, delta),
            source_ids=source_ids,
        )
    if characteristic is Characteristic.ARMOR_PENETRATION:
        return replace(
            profile,
            armor_penetration=_modified_characteristic_value(profile.armor_penetration, delta),
            source_ids=source_ids,
        )
    if characteristic in {Characteristic.BALLISTIC_SKILL, Characteristic.WEAPON_SKILL}:
        if profile.skill.characteristic is not characteristic:
            return replace(profile, source_ids=source_ids)
        return replace(
            profile,
            skill=_modified_characteristic_value(profile.skill, delta),
            source_ids=source_ids,
        )
    if characteristic is Characteristic.ATTACKS:
        return replace(
            profile,
            attack_profile=_modified_attack_profile(profile.attack_profile, delta),
            source_ids=source_ids,
        )
    if characteristic is Characteristic.DAMAGE:
        return replace(
            profile,
            damage_profile=_modified_damage_profile(profile.damage_profile, delta),
            source_ids=source_ids,
        )
    return profile


def _modified_characteristic_value(value: CharacteristicValue, delta: int) -> CharacteristicValue:
    if type(value) is not CharacteristicValue:
        raise GameLifecycleError("Generic characteristic modifier requires value.")
    if not value.is_numeric:
        raise GameLifecycleError("Generic characteristic modifier cannot modify dash values.")
    return CharacteristicValue.from_raw(value.characteristic, value.final + delta)


def _modified_attack_profile(profile: AttackProfile, delta: int) -> AttackProfile:
    if type(profile) is not AttackProfile:
        raise GameLifecycleError("Generic Attacks modifier requires AttackProfile.")
    if profile.fixed_attacks is not None:
        return AttackProfile.fixed(max(1, profile.fixed_attacks + delta))
    if profile.dice_expression is None:
        raise GameLifecycleError("AttackProfile requires fixed attacks or dice expression.")
    return AttackProfile.dice(
        replace(profile.dice_expression, modifier=profile.dice_expression.modifier + delta)
    )


def _modified_damage_profile(profile: DamageProfile, delta: int) -> DamageProfile:
    if type(profile) is not DamageProfile:
        raise GameLifecycleError("Generic Damage modifier requires DamageProfile.")
    if profile.fixed_damage is not None:
        return DamageProfile.fixed(max(1, profile.fixed_damage + delta))
    if profile.dice_expression is None:
        raise GameLifecycleError("DamageProfile requires fixed damage or dice expression.")
    return DamageProfile.dice(
        replace(profile.dice_expression, modifier=profile.dice_expression.modifier + delta)
    )


def _weapon_scope_matches_profile(
    parameters: dict[str, JsonValue],
    profile: WeaponProfile,
) -> bool:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Generic weapon scope requires WeaponProfile.")
    scope = parameters.get("weapon_scope")
    if scope is None:
        return True
    if type(scope) is not str:
        raise GameLifecycleError("Generic weapon_scope must be a string.")
    if scope == "all":
        return True
    if scope == "melee":
        return profile.range_profile.kind is RangeProfileKind.MELEE
    if scope == "ranged":
        return profile.range_profile.kind is RangeProfileKind.DISTANCE
    raise GameLifecycleError("Unsupported generic weapon_scope.")


def _weapon_keyword_parameter(parameters: dict[str, JsonValue]) -> WeaponKeyword:
    value = _required_string_parameter(parameters, key="weapon_ability")
    try:
        return weapon_keyword_from_token(value)
    except WeaponProfileError as exc:
        raise GameLifecycleError("Generic weapon ability grant has unsupported keyword.") from exc


def _weapon_ability_descriptor(
    parameters: dict[str, JsonValue],
    *,
    keyword: WeaponKeyword,
) -> AbilityDescriptor | None:
    if keyword is WeaponKeyword.LETHAL_HITS:
        return AbilityDescriptor.lethal_hits()
    if keyword is WeaponKeyword.DEVASTATING_WOUNDS:
        return AbilityDescriptor.devastating_wounds()
    if keyword is WeaponKeyword.HEAVY:
        return AbilityDescriptor.heavy()
    if keyword is WeaponKeyword.SUSTAINED_HITS:
        return AbilityDescriptor.sustained_hits(_required_weapon_ability_value(parameters))
    if keyword is WeaponKeyword.RAPID_FIRE:
        return AbilityDescriptor.rapid_fire(_required_positive_int_parameter(parameters))
    if keyword is WeaponKeyword.MELTA:
        return AbilityDescriptor.melta(_required_positive_int_parameter(parameters))
    if keyword is WeaponKeyword.CLEAVE:
        return AbilityDescriptor.cleave(_required_positive_int_parameter(parameters))
    if keyword is WeaponKeyword.HUNTER:
        raise GameLifecycleError("Generic weapon ability grant cannot infer Hunter targets.")
    return None


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


def _parameters_from_effect_payload(effect_payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    raw_parameters = effect_payload.get("parameters")
    if not isinstance(raw_parameters, list):
        raise GameLifecycleError("Generic RuleIR effect parameters must be a list.")
    parameters: dict[str, JsonValue] = {}
    for raw_parameter in raw_parameters:
        if not isinstance(raw_parameter, dict):
            raise GameLifecycleError("Generic RuleIR parameter must be an object.")
        key = raw_parameter.get("key")
        if type(key) is not str:
            raise GameLifecycleError("Generic RuleIR parameter key must be a string.")
        parameter_key = _validate_identifier("parameter key", key)
        if parameter_key in parameters:
            raise GameLifecycleError("Generic RuleIR parameters must not duplicate keys.")
        if "value" not in raw_parameter:
            raise GameLifecycleError("Generic RuleIR parameter requires value.")
        parameters[parameter_key] = validate_json_value(raw_parameter["value"])
    return parameters


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


def _required_numeric_parameter(parameters: dict[str, JsonValue], *, key: str) -> float:
    value = parameters.get(key)
    if type(value) not in {int, float}:
        raise GameLifecycleError(f"Generic RuleIR parameter {key} must be numeric.")
    return float(cast(int | float, value))


def _required_weapon_ability_value(parameters: dict[str, JsonValue]) -> int | str:
    value = parameters.get("weapon_ability_value")
    if type(value) in {int, str}:
        if type(value) is int and value < 1:
            raise GameLifecycleError("Generic weapon_ability_value must be positive.")
        if type(value) is str and not value.strip():
            raise GameLifecycleError("Generic weapon_ability_value must not be empty.")
        return cast(int | str, value)
    raise GameLifecycleError("Generic weapon_ability_value is required.")


def _required_positive_int_parameter(parameters: dict[str, JsonValue]) -> int:
    value = parameters.get("weapon_ability_value")
    if type(value) is not int or value < 1:
        raise GameLifecycleError("Generic weapon_ability_value must be a positive int.")
    return value


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


def _source_ids_with(source_ids: tuple[str, ...], source_id: str) -> tuple[str, ...]:
    if source_id in source_ids:
        return source_ids
    return tuple(sorted((*source_ids, source_id)))


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
    conditional_wound_reroll = _conditional_wound_reroll_payload(effect)
    if conditional_wound_reroll is not None:
        payload["conditional_wound_reroll"] = conditional_wound_reroll
    return payload


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
    required_keyword = effect.parameters.get("full_reroll_required_attacker_keyword")
    if required_keyword is not None and type(required_keyword) is not str:
        raise GameLifecycleError(
            "Generic RuleIR full_reroll_required_attacker_keyword must be a string."
        )
    if not reroll_values and full_reroll is False and required_keyword is None:
        return None
    payload: dict[str, JsonValue] = {
        "reroll_unmodified_values": reroll_values,
        "full_reroll_if_target_within_objective_range": full_reroll,
    }
    if required_keyword is not None:
        payload["full_reroll_required_attacker_keyword"] = required_keyword
    return payload


def _target_is_closest_enemy_within_distance(
    *,
    state: object,
    attacking_unit_instance_id: str,
    target_unit_instance_id: str,
    distance_inches: float,
) -> bool:
    attacker_owner = _unit_owner(state=state, unit_instance_id=attacking_unit_instance_id)
    target_owner = _unit_owner(state=state, unit_instance_id=target_unit_instance_id)
    if attacker_owner == target_owner:
        return False
    target_distance = _closest_unit_distance_inches(
        state=state,
        first_unit_instance_id=attacking_unit_instance_id,
        second_unit_instance_id=target_unit_instance_id,
    )
    if target_distance > distance_inches:
        return False
    for enemy_unit_id in _enemy_unit_ids_for_player(state=state, player_id=attacker_owner):
        candidate_distance = _closest_unit_distance_inches(
            state=state,
            first_unit_instance_id=attacking_unit_instance_id,
            second_unit_instance_id=enemy_unit_id,
        )
        if candidate_distance < target_distance:
            return False
    return True


def _target_is_enemy_within_distance(
    *,
    state: object,
    attacking_unit_instance_id: str,
    target_unit_instance_id: str,
    distance_inches: float,
) -> bool:
    attacker_owner = _unit_owner(state=state, unit_instance_id=attacking_unit_instance_id)
    target_owner = _unit_owner(state=state, unit_instance_id=target_unit_instance_id)
    if attacker_owner == target_owner:
        return False
    return (
        _closest_unit_distance_inches(
            state=state,
            first_unit_instance_id=attacking_unit_instance_id,
            second_unit_instance_id=target_unit_instance_id,
        )
        <= distance_inches
    )


def _enemy_unit_ids_for_player(*, state: object, player_id: str) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR target constraints require GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    ids: list[str] = []
    for army in state.army_definitions:
        if army.player_id == requested_player_id:
            continue
        ids.extend(unit.unit_instance_id for unit in army.units)
    return tuple(sorted(ids))


def _unit_owner(*, state: object, unit_instance_id: str) -> str:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR target constraints require GameState.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return army.player_id
    raise GameLifecycleError("Generic RuleIR target constraint unit is unknown.")


def _unit_has_keyword(*, state: object, unit_instance_id: str, keyword: str) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR keyword gate requires GameState.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    requested_keyword = _canonical_keyword(_validate_identifier("keyword", keyword))
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id != requested_unit_id:
                continue
            return requested_keyword in {
                _canonical_keyword(stored) for stored in (*unit.keywords, *unit.faction_keywords)
            }
    raise GameLifecycleError("Generic RuleIR keyword gate unit is unknown.")


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


def _canonical_keyword(value: str) -> str:
    return value.strip().upper().replace("_", " ").replace("-", " ")


def _closest_unit_distance_inches(
    *,
    state: object,
    first_unit_instance_id: str,
    second_unit_instance_id: str,
) -> float:
    first_models = _geometry_models_for_unit(
        state=state,
        unit_instance_id=first_unit_instance_id,
    )
    second_models = _geometry_models_for_unit(
        state=state,
        unit_instance_id=second_unit_instance_id,
    )
    if not first_models or not second_models:
        raise GameLifecycleError("Generic RuleIR target constraint requires placed models.")
    return min(
        DistanceMeasurementContext.from_models(first_model, second_model).closest_distance_inches()
        for first_model in first_models
        for second_model in second_models
    )


def _geometry_models_for_unit(
    *,
    state: object,
    unit_instance_id: str,
) -> tuple[Model, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR target constraints require GameState.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Generic RuleIR target constraint requires battlefield_state.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id != requested_unit_id:
                continue
            try:
                return tuple(
                    geometry_model_for_placement(
                        model=model,
                        placement=battlefield_state.model_placement_by_id(model.model_instance_id),
                    )
                    for model in unit.own_models
                    if model.is_alive
                )
            except PlacementError as exc:
                raise GameLifecycleError(
                    "Generic RuleIR target constraint placement is invalid."
                ) from exc
    raise GameLifecycleError("Generic RuleIR target constraint unit is unknown.")


_validate_identifier = IdentifierValidator(GameLifecycleError)
