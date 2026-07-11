from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.datasheet import (
    DamagedEffectDefinition,
    DamagedEffectKind,
    DamagedWeaponScope,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierBinding,
    HitRollModifierContext,
    ObjectiveControlModifierBinding,
    ObjectiveControlModifierContext,
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


CATALOG_DAMAGED_HIT_ROLL_MODIFIER_ID = "catalog-datasheet:damaged:hit-roll-modifier"
CATALOG_DAMAGED_OBJECTIVE_CONTROL_MODIFIER_ID = (
    "catalog-datasheet:damaged:objective-control-modifier"
)
CATALOG_DAMAGED_WEAPON_ATTACKS_MODIFIER_ID = "catalog-datasheet:damaged:weapon-attacks-modifier"


@dataclass(frozen=True, slots=True)
class CatalogDamagedShootingWeaponSelectionLimit:
    damaged_effect_id: str
    source_id: str
    model_instance_id: str
    weapon_keyword: WeaponKeyword
    max_selections: int
    baseline_max_selections: int
    damaged_profile_active: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "damaged_effect_id",
            _validate_identifier(
                "DAMAGED shooting weapon selection limit damaged_effect_id",
                self.damaged_effect_id,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier(
                "DAMAGED shooting weapon selection limit source_id",
                self.source_id,
            ),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier(
                "DAMAGED shooting weapon selection limit model_instance_id",
                self.model_instance_id,
            ),
        )
        if type(self.weapon_keyword) is not WeaponKeyword:
            raise GameLifecycleError(
                "DAMAGED shooting weapon selection limit requires a weapon keyword."
            )
        object.__setattr__(
            self,
            "max_selections",
            _validate_positive_int(
                "DAMAGED shooting weapon selection limit max_selections",
                self.max_selections,
            ),
        )
        object.__setattr__(
            self,
            "baseline_max_selections",
            _validate_positive_int(
                "DAMAGED shooting weapon selection limit baseline_max_selections",
                self.baseline_max_selections,
            ),
        )
        if self.baseline_max_selections < self.max_selections:
            raise GameLifecycleError(
                "DAMAGED shooting weapon selection limit baseline is below max."
            )
        if type(self.damaged_profile_active) is not bool:
            raise GameLifecycleError(
                "DAMAGED shooting weapon selection limit active flag must be a bool."
            )


@dataclass(frozen=True, slots=True)
class CatalogDamagedEffectRuntime:
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "armies", _validate_armies(self.armies))

    def hit_roll_bindings(self) -> tuple[HitRollModifierBinding, ...]:
        if not _has_damaged_effect_kind(self.armies, DamagedEffectKind.HIT_ROLL_MODIFIER):
            return ()
        return (
            HitRollModifierBinding(
                modifier_id=CATALOG_DAMAGED_HIT_ROLL_MODIFIER_ID,
                source_id=CATALOG_DAMAGED_HIT_ROLL_MODIFIER_ID,
                handler=self.hit_roll_modifier,
            ),
        )

    def objective_control_bindings(self) -> tuple[ObjectiveControlModifierBinding, ...]:
        if not _has_damaged_effect_kind(
            self.armies,
            DamagedEffectKind.OBJECTIVE_CONTROL_MODIFIER,
        ):
            return ()
        return (
            ObjectiveControlModifierBinding(
                modifier_id=CATALOG_DAMAGED_OBJECTIVE_CONTROL_MODIFIER_ID,
                source_id=CATALOG_DAMAGED_OBJECTIVE_CONTROL_MODIFIER_ID,
                handler=self.objective_control_modifier,
            ),
        )

    def weapon_profile_bindings(self) -> tuple[WeaponProfileModifierBinding, ...]:
        if not any(
            _has_damaged_effect_kind(self.armies, effect_kind)
            for effect_kind in (
                DamagedEffectKind.WEAPON_ATTACKS_MODIFIER,
                DamagedEffectKind.WEAPON_ATTACKS_HALVE,
            )
        ):
            return ()
        return (
            WeaponProfileModifierBinding(
                modifier_id=CATALOG_DAMAGED_WEAPON_ATTACKS_MODIFIER_ID,
                source_id=CATALOG_DAMAGED_WEAPON_ATTACKS_MODIFIER_ID,
                handler=self.weapon_profile_modifier,
            ),
        )

    def hit_roll_modifier(self, context: HitRollModifierContext) -> int:
        if type(context) is not HitRollModifierContext:
            raise GameLifecycleError("DAMAGED Hit roll modifier requires context.")
        unit = _unit_by_id(context.state, context.attacking_unit_instance_id)
        model = _model_in_unit_by_id(unit, context.attacker_model_instance_id)
        return sum(
            effect.modifier
            for effect in _active_damaged_effects_for_model(unit=unit, model=model)
            if effect.effect_kind is DamagedEffectKind.HIT_ROLL_MODIFIER
            and effect.modifier is not None
        )

    def objective_control_modifier(self, context: ObjectiveControlModifierContext) -> int:
        if type(context) is not ObjectiveControlModifierContext:
            raise GameLifecycleError("DAMAGED Objective Control modifier requires context.")
        unit = _unit_by_id(context.state, context.unit_instance_id)
        model = _model_in_unit_by_id(unit, context.model_instance_id)
        modifier = sum(
            effect.modifier
            for effect in _active_damaged_effects_for_model(unit=unit, model=model)
            if effect.effect_kind is DamagedEffectKind.OBJECTIVE_CONTROL_MODIFIER
            and effect.modifier is not None
        )
        return max(0, context.current_objective_control + modifier)

    def weapon_profile_modifier(self, context: WeaponProfileModifierContext) -> WeaponProfile:
        if type(context) is not WeaponProfileModifierContext:
            raise GameLifecycleError("DAMAGED weapon profile modifier requires context.")
        unit = _unit_by_id(context.state, context.attacking_unit_instance_id)
        model = _model_in_unit_by_id(unit, context.attacker_model_instance_id)
        profile = context.weapon_profile
        for effect in _active_damaged_effects_for_model(unit=unit, model=model):
            if effect.effect_kind not in {
                DamagedEffectKind.WEAPON_ATTACKS_MODIFIER,
                DamagedEffectKind.WEAPON_ATTACKS_HALVE,
            }:
                continue
            if not _damaged_weapon_scope_matches(effect=effect, profile=profile):
                continue
            profile = _profile_with_damaged_attacks_effect(profile=profile, effect=effect)
        return profile


def catalog_damaged_effect_hit_roll_modifier_bindings(
    *,
    armies: tuple[ArmyDefinition, ...],
) -> tuple[HitRollModifierBinding, ...]:
    return CatalogDamagedEffectRuntime(armies=armies).hit_roll_bindings()


def catalog_damaged_effect_objective_control_modifier_bindings(
    *,
    armies: tuple[ArmyDefinition, ...],
) -> tuple[ObjectiveControlModifierBinding, ...]:
    return CatalogDamagedEffectRuntime(armies=armies).objective_control_bindings()


def catalog_damaged_effect_weapon_profile_modifier_bindings(
    *,
    armies: tuple[ArmyDefinition, ...],
) -> tuple[WeaponProfileModifierBinding, ...]:
    return CatalogDamagedEffectRuntime(armies=armies).weapon_profile_bindings()


def catalog_damaged_shooting_weapon_selection_limit_for_profile(
    *,
    unit: UnitInstance,
    model: ModelInstance,
    profile: WeaponProfile,
) -> CatalogDamagedShootingWeaponSelectionLimit | None:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("DAMAGED shooting weapon selection limit requires a unit.")
    if type(model) is not ModelInstance:
        raise GameLifecycleError("DAMAGED shooting weapon selection limit requires a model.")
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("DAMAGED shooting weapon selection limit requires a profile.")
    if not model.is_alive:
        return None
    keyword = _shooting_weapon_selection_keyword_for_profile(profile)
    if keyword is None:
        return None
    effects: list[DamagedEffectDefinition] = []
    for effect in unit.damaged_effects:
        if effect.effect_kind is not DamagedEffectKind.SHOOTING_WEAPON_SELECTION_LIMIT:
            continue
        if not _damaged_effect_targets_model(effect=effect, model=model):
            continue
        effects.append(effect)
    if len(effects) == 0:
        return None
    if len(effects) != 1:
        raise GameLifecycleError("DAMAGED shooting weapon selection limit is ambiguous.")
    effect = effects[0]
    if effect.max_selections is None:
        raise GameLifecycleError("DAMAGED shooting weapon selection limit is missing max.")
    if effect.baseline_max_selections is None:
        raise GameLifecycleError("DAMAGED shooting weapon selection limit is missing baseline.")
    active = effect.applies_to_wounds(model.wounds_remaining)
    return CatalogDamagedShootingWeaponSelectionLimit(
        damaged_effect_id=effect.damaged_effect_id,
        source_id=effect.source_id,
        model_instance_id=model.model_instance_id,
        weapon_keyword=keyword,
        max_selections=effect.max_selections if active else effect.baseline_max_selections,
        baseline_max_selections=effect.baseline_max_selections,
        damaged_profile_active=active,
    )


def _active_damaged_effects_for_model(
    *,
    unit: UnitInstance,
    model: ModelInstance,
) -> tuple[DamagedEffectDefinition, ...]:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("DAMAGED effects require a unit.")
    if type(model) is not ModelInstance:
        raise GameLifecycleError("DAMAGED effects require a model.")
    return tuple(
        effect
        for effect in unit.damaged_effects
        if _damaged_effect_targets_model(effect=effect, model=model)
        and model.is_alive
        and effect.applies_to_wounds(model.wounds_remaining)
    )


def _damaged_effect_targets_model(
    *,
    effect: DamagedEffectDefinition,
    model: ModelInstance,
) -> bool:
    if type(effect) is not DamagedEffectDefinition:
        raise GameLifecycleError("DAMAGED model targeting requires an effect.")
    if type(model) is not ModelInstance:
        raise GameLifecycleError("DAMAGED model targeting requires a model.")
    if effect.model_profile_id is None:
        return True
    return effect.model_profile_id == model.model_profile_id


def _profile_with_damaged_attacks_effect(
    *,
    profile: WeaponProfile,
    effect: DamagedEffectDefinition,
) -> WeaponProfile:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("DAMAGED weapon Attacks effect requires a profile.")
    if type(effect) is not DamagedEffectDefinition:
        raise GameLifecycleError("DAMAGED weapon Attacks effect requires descriptor data.")
    fixed_attacks = profile.attack_profile.fixed_attacks
    if fixed_attacks is None:
        raise GameLifecycleError("DAMAGED weapon Attacks effects require fixed Attacks profiles.")
    if effect.effect_kind is DamagedEffectKind.WEAPON_ATTACKS_MODIFIER:
        if effect.modifier is None:
            raise GameLifecycleError("DAMAGED weapon Attacks modifier is missing.")
        attacks = max(1, fixed_attacks + effect.modifier)
    elif effect.effect_kind is DamagedEffectKind.WEAPON_ATTACKS_HALVE:
        attacks = max(1, (fixed_attacks + 1) // 2)
    else:
        raise GameLifecycleError("DAMAGED weapon Attacks effect kind is unsupported.")
    source_ids = (
        profile.source_ids
        if effect.source_id in profile.source_ids
        else tuple(sorted((*profile.source_ids, effect.source_id)))
    )
    return replace(
        profile,
        attack_profile=AttackProfile.fixed(attacks),
        source_ids=source_ids,
    )


def _damaged_weapon_scope_matches(
    *,
    effect: DamagedEffectDefinition,
    profile: WeaponProfile,
) -> bool:
    if type(effect) is not DamagedEffectDefinition:
        raise GameLifecycleError("DAMAGED weapon scope matching requires an effect.")
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("DAMAGED weapon scope matching requires a profile.")
    if effect.weapon_scope is DamagedWeaponScope.ALL:
        return True
    if effect.weapon_scope is DamagedWeaponScope.MELEE:
        return profile.range_profile.kind is RangeProfileKind.MELEE
    if effect.weapon_scope is DamagedWeaponScope.NAMED:
        profile_name_key = _name_key(profile.name)
        return any(
            profile_name_key == _name_key(weapon_name) for weapon_name in effect.weapon_names
        )
    raise GameLifecycleError("DAMAGED weapon Attacks effect is missing weapon scope.")


def _shooting_weapon_selection_keyword_for_profile(
    profile: WeaponProfile,
) -> WeaponKeyword | None:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("DAMAGED shooting weapon selection requires a profile.")
    if WeaponKeyword.CTAN_POWER in profile.keywords:
        return WeaponKeyword.CTAN_POWER
    return None


def _has_damaged_effect_kind(
    armies: tuple[ArmyDefinition, ...],
    effect_kind: DamagedEffectKind,
) -> bool:
    if type(effect_kind) is not DamagedEffectKind:
        raise GameLifecycleError("DAMAGED effect kind query requires a kind.")
    return any(
        effect.effect_kind is effect_kind
        for army in armies
        for unit in army.units
        for effect in unit.damaged_effects
    )


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    _validate_game_state(state)
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_id:
                return unit
    raise GameLifecycleError("DAMAGED effect unit was not found.")


def _model_in_unit_by_id(unit: UnitInstance, model_instance_id: str) -> ModelInstance:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("DAMAGED effect model lookup requires a unit.")
    requested_id = _validate_identifier("model_instance_id", model_instance_id)
    for model in unit.own_models:
        if model.model_instance_id == requested_id:
            return model
    raise GameLifecycleError("DAMAGED effect model was not found in the unit.")


def _validate_armies(value: object) -> tuple[ArmyDefinition, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("DAMAGED runtime armies must be a tuple.")
    armies: list[ArmyDefinition] = []
    for army in cast(tuple[object, ...], value):
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError("DAMAGED runtime armies must contain ArmyDefinition values.")
        armies.append(army)
    return tuple(sorted(armies, key=lambda army: army.army_id))


def _validate_game_state(value: object) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(value) is not GameState:
        raise GameLifecycleError("DAMAGED effect state must be GameState.")


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(f"{field_name} must be greater than zero.")
    return value


def _name_key(value: str) -> str:
    key = "".join(character.casefold() for character in value if character.isalnum())
    if not key:
        raise GameLifecycleError("DAMAGED weapon name key must not be empty.")
    return key
