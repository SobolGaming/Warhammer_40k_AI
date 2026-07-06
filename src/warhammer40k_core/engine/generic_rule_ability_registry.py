from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.advance_eligibility_hooks import (
    AdvanceEligibilityContext,
    AdvanceEligibilityGrant,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    AttackSequenceCompletedHandler,
)
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationContext,
    MortalWoundFeelNoPainContinuationHandler,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    WeaponProfileModifierContext,
    WeaponProfileModifierHandler,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    ShootingUnitSelectedContext,
    ShootingUnitSelectedGrant,
)
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionContext,
    TargetRestriction,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleIR,
    RuleTargetKind,
    parameter_payload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_shadow_legion_ir_support_2026_27 as shadow_legion_ir,
)

_Phase17FExecutionRecord = faction_execution_2026_27.Phase17FExecutionRecord
_DARK_PACT_LETHAL_HITS = "lethal_hits"
_DARK_PACT_SUSTAINED_HITS_1 = "sustained_hits_1"
_DARK_PACT_EFFECT_KIND = "chaos_space_marines_dark_pact"
_SHADOW_LEGION_SOURCE_RULE_ID = "phase17f:phase17e:chaos-daemons:shadow-legion:rule"
_SHADOW_LEGION_DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND = "chaos_daemons_shadow_legion_dark_pacts"


class GenericRuleAbilityHookFamily(StrEnum):
    ADVANCE_ELIGIBILITY = "advance_eligibility"
    SHOOTING_TARGET_RESTRICTION = "shooting_target_restriction"
    SHOOTING_UNIT_SELECTED_GRANT = "shooting_unit_selected_grant"
    FIGHT_UNIT_SELECTED_GRANT = "fight_unit_selected_grant"
    ATTACK_SEQUENCE_COMPLETED = "attack_sequence_completed"
    MORTAL_WOUND_FEEL_NO_PAIN_CONTINUATION = "mortal_wound_feel_no_pain_continuation"
    WEAPON_PROFILE_MODIFIER = "weapon_profile_modifier"


@dataclass(frozen=True, slots=True)
class GenericRuleAbilitySource:
    record: _Phase17FExecutionRecord
    rule_ir: RuleIR

    def __post_init__(self) -> None:
        if type(self.record) is not _Phase17FExecutionRecord:
            raise GameLifecycleError("Generic RuleIR ability source requires execution record.")
        if type(self.rule_ir) is not RuleIR:
            raise GameLifecycleError("Generic RuleIR ability source requires RuleIR.")
        _validate_record_rule_ir_hash(record=self.record, rule_ir=self.rule_ir)


type GenericRuleHookIdBuilder = Callable[[GenericRuleAbilitySource], str]
type GenericRuleModifierIdBuilder = Callable[[GenericRuleAbilitySource], str]
type AdvanceTargetUnitIdBuilder = Callable[[AdvanceEligibilityContext], str]
type AdvanceContextPredicate = Callable[
    [AdvanceEligibilityContext, GenericRuleAbilitySource, tuple[PersistingEffect, ...]],
    bool,
]
type AdvanceGrantBuilder = Callable[
    [AdvanceEligibilityContext, GenericRuleAbilitySource, tuple[PersistingEffect, ...]],
    AdvanceEligibilityGrant,
]
type ShootingTargetRestrictionTargetUnitIdBuilder = Callable[
    [ShootingTargetRestrictionContext], str
]
type ShootingTargetRestrictionContextPredicate = Callable[
    [ShootingTargetRestrictionContext, GenericRuleAbilitySource, tuple[PersistingEffect, ...]],
    bool,
]
type ShootingTargetRestrictionBuilder = Callable[
    [ShootingTargetRestrictionContext, GenericRuleAbilitySource, tuple[PersistingEffect, ...]],
    TargetRestriction,
]
type ShootingUnitSelectedTargetUnitIdBuilder = Callable[[ShootingUnitSelectedContext], str]
type ShootingUnitSelectedContextPredicate = Callable[
    [ShootingUnitSelectedContext, GenericRuleAbilitySource, tuple[PersistingEffect, ...]],
    bool,
]
type ShootingUnitSelectedGrantBuilder = Callable[
    [ShootingUnitSelectedContext, GenericRuleAbilitySource, tuple[PersistingEffect, ...]],
    ShootingUnitSelectedGrant,
]
type FightUnitSelectedTargetUnitIdBuilder = Callable[[FightUnitSelectedContext], str]
type FightUnitSelectedContextPredicate = Callable[
    [FightUnitSelectedContext, GenericRuleAbilitySource, tuple[PersistingEffect, ...]],
    bool,
]
type FightUnitSelectedGrantBuilder = Callable[
    [FightUnitSelectedContext, GenericRuleAbilitySource, tuple[PersistingEffect, ...]],
    FightUnitSelectedGrant,
]


@dataclass(frozen=True, slots=True)
class GenericRuleAdvanceEligibilityAbility:
    ability_id: str
    coverage_descriptor_id: str
    source_rule_id: str
    hook_id_builder: GenericRuleHookIdBuilder
    target_unit_id_builder: AdvanceTargetUnitIdBuilder
    context_predicate: AdvanceContextPredicate
    grant_builder: AdvanceGrantBuilder

    @property
    def hook_family(self) -> GenericRuleAbilityHookFamily:
        return GenericRuleAbilityHookFamily.ADVANCE_ELIGIBILITY

    def __post_init__(self) -> None:
        _validate_single_descriptor_fields(
            self.ability_id,
            coverage_descriptor_id=self.coverage_descriptor_id,
            source_rule_id=self.source_rule_id,
            set_validated_values=self._set_validated_identity,
        )
        _validate_callable(
            "Generic advance eligibility ability hook_id_builder",
            self.hook_id_builder,
        )
        _validate_callable(
            "Generic advance eligibility ability target_unit_id_builder",
            self.target_unit_id_builder,
        )
        _validate_callable(
            "Generic advance eligibility ability context_predicate",
            self.context_predicate,
        )
        _validate_callable(
            "Generic advance eligibility ability grant_builder",
            self.grant_builder,
        )

    def _set_validated_identity(
        self,
        *,
        ability_id: str,
        coverage_descriptor_id: str,
        source_rule_id: str,
    ) -> None:
        object.__setattr__(self, "ability_id", ability_id)
        object.__setattr__(self, "coverage_descriptor_id", coverage_descriptor_id)
        object.__setattr__(self, "source_rule_id", source_rule_id)

    def ability_ids(self) -> tuple[str, ...]:
        return (self.ability_id,)

    def hook_id(self, source: GenericRuleAbilitySource) -> str:
        return _validate_identifier("hook_id", self.hook_id_builder(source))

    def target_unit_instance_id(self, context: AdvanceEligibilityContext) -> str:
        return _validate_identifier("unit_instance_id", self.target_unit_id_builder(context))


@dataclass(frozen=True, slots=True)
class GenericRuleShootingTargetRestrictionAbility:
    ability_id: str
    coverage_descriptor_id: str
    source_rule_id: str
    hook_id_builder: GenericRuleHookIdBuilder
    target_unit_id_builder: ShootingTargetRestrictionTargetUnitIdBuilder
    context_predicate: ShootingTargetRestrictionContextPredicate
    restriction_builder: ShootingTargetRestrictionBuilder

    @property
    def hook_family(self) -> GenericRuleAbilityHookFamily:
        return GenericRuleAbilityHookFamily.SHOOTING_TARGET_RESTRICTION

    def __post_init__(self) -> None:
        _validate_single_descriptor_fields(
            self.ability_id,
            coverage_descriptor_id=self.coverage_descriptor_id,
            source_rule_id=self.source_rule_id,
            set_validated_values=self._set_validated_identity,
        )
        _validate_callable(
            "Generic shooting target restriction ability hook_id_builder",
            self.hook_id_builder,
        )
        _validate_callable(
            "Generic shooting target restriction ability target_unit_id_builder",
            self.target_unit_id_builder,
        )
        _validate_callable(
            "Generic shooting target restriction ability context_predicate",
            self.context_predicate,
        )
        _validate_callable(
            "Generic shooting target restriction ability restriction_builder",
            self.restriction_builder,
        )

    def _set_validated_identity(
        self,
        *,
        ability_id: str,
        coverage_descriptor_id: str,
        source_rule_id: str,
    ) -> None:
        object.__setattr__(self, "ability_id", ability_id)
        object.__setattr__(self, "coverage_descriptor_id", coverage_descriptor_id)
        object.__setattr__(self, "source_rule_id", source_rule_id)

    def ability_ids(self) -> tuple[str, ...]:
        return (self.ability_id,)

    def hook_id(self, source: GenericRuleAbilitySource) -> str:
        return _validate_identifier("hook_id", self.hook_id_builder(source))

    def target_unit_instance_id(self, context: ShootingTargetRestrictionContext) -> str:
        return _validate_identifier("unit_instance_id", self.target_unit_id_builder(context))


@dataclass(frozen=True, slots=True)
class GenericRuleShootingUnitSelectedGrantAbility:
    ability_id: str
    coverage_descriptor_id: str
    source_rule_id: str
    hook_id_builder: GenericRuleHookIdBuilder
    target_unit_id_builder: ShootingUnitSelectedTargetUnitIdBuilder
    context_predicate: ShootingUnitSelectedContextPredicate
    grant_builder: ShootingUnitSelectedGrantBuilder

    @property
    def hook_family(self) -> GenericRuleAbilityHookFamily:
        return GenericRuleAbilityHookFamily.SHOOTING_UNIT_SELECTED_GRANT

    def __post_init__(self) -> None:
        _validate_single_descriptor_fields(
            self.ability_id,
            coverage_descriptor_id=self.coverage_descriptor_id,
            source_rule_id=self.source_rule_id,
            set_validated_values=self._set_validated_identity,
        )
        _validate_callable(
            "Generic shooting selected-unit grant ability hook_id_builder",
            self.hook_id_builder,
        )
        _validate_callable(
            "Generic shooting selected-unit grant ability target_unit_id_builder",
            self.target_unit_id_builder,
        )
        _validate_callable(
            "Generic shooting selected-unit grant ability context_predicate",
            self.context_predicate,
        )
        _validate_callable(
            "Generic shooting selected-unit grant ability grant_builder",
            self.grant_builder,
        )

    def _set_validated_identity(
        self,
        *,
        ability_id: str,
        coverage_descriptor_id: str,
        source_rule_id: str,
    ) -> None:
        object.__setattr__(self, "ability_id", ability_id)
        object.__setattr__(self, "coverage_descriptor_id", coverage_descriptor_id)
        object.__setattr__(self, "source_rule_id", source_rule_id)

    def ability_ids(self) -> tuple[str, ...]:
        return (self.ability_id,)

    def hook_id(self, source: GenericRuleAbilitySource) -> str:
        return _validate_identifier("hook_id", self.hook_id_builder(source))

    def target_unit_instance_id(self, context: ShootingUnitSelectedContext) -> str:
        return _validate_identifier("unit_instance_id", self.target_unit_id_builder(context))


@dataclass(frozen=True, slots=True)
class GenericRuleFightUnitSelectedGrantAbility:
    ability_id: str
    coverage_descriptor_id: str
    source_rule_id: str
    hook_id_builder: GenericRuleHookIdBuilder
    target_unit_id_builder: FightUnitSelectedTargetUnitIdBuilder
    context_predicate: FightUnitSelectedContextPredicate
    grant_builder: FightUnitSelectedGrantBuilder

    @property
    def hook_family(self) -> GenericRuleAbilityHookFamily:
        return GenericRuleAbilityHookFamily.FIGHT_UNIT_SELECTED_GRANT

    def __post_init__(self) -> None:
        _validate_single_descriptor_fields(
            self.ability_id,
            coverage_descriptor_id=self.coverage_descriptor_id,
            source_rule_id=self.source_rule_id,
            set_validated_values=self._set_validated_identity,
        )
        _validate_callable(
            "Generic fight selected-unit grant ability hook_id_builder",
            self.hook_id_builder,
        )
        _validate_callable(
            "Generic fight selected-unit grant ability target_unit_id_builder",
            self.target_unit_id_builder,
        )
        _validate_callable(
            "Generic fight selected-unit grant ability context_predicate",
            self.context_predicate,
        )
        _validate_callable(
            "Generic fight selected-unit grant ability grant_builder",
            self.grant_builder,
        )

    def _set_validated_identity(
        self,
        *,
        ability_id: str,
        coverage_descriptor_id: str,
        source_rule_id: str,
    ) -> None:
        object.__setattr__(self, "ability_id", ability_id)
        object.__setattr__(self, "coverage_descriptor_id", coverage_descriptor_id)
        object.__setattr__(self, "source_rule_id", source_rule_id)

    def ability_ids(self) -> tuple[str, ...]:
        return (self.ability_id,)

    def hook_id(self, source: GenericRuleAbilitySource) -> str:
        return _validate_identifier("hook_id", self.hook_id_builder(source))

    def target_unit_instance_id(self, context: FightUnitSelectedContext) -> str:
        return _validate_identifier("unit_instance_id", self.target_unit_id_builder(context))


@dataclass(frozen=True, slots=True)
class GenericRuleAttackSequenceCompletedAbility:
    ability_ids_value: tuple[str, ...]
    coverage_descriptor_id: str
    source_rule_id: str
    hook_id_builder: GenericRuleHookIdBuilder
    handler: AttackSequenceCompletedHandler

    @property
    def hook_family(self) -> GenericRuleAbilityHookFamily:
        return GenericRuleAbilityHookFamily.ATTACK_SEQUENCE_COMPLETED

    def __post_init__(self) -> None:
        _validate_group_descriptor_fields(
            self.ability_ids_value,
            coverage_descriptor_id=self.coverage_descriptor_id,
            source_rule_id=self.source_rule_id,
            set_validated_values=self._set_validated_identity,
        )
        _validate_callable(
            "Generic attack sequence completed ability hook_id_builder",
            self.hook_id_builder,
        )
        _validate_callable("Generic attack sequence completed handler", self.handler)

    def _set_validated_identity(
        self,
        *,
        ability_ids: tuple[str, ...],
        coverage_descriptor_id: str,
        source_rule_id: str,
    ) -> None:
        object.__setattr__(self, "ability_ids_value", ability_ids)
        object.__setattr__(self, "coverage_descriptor_id", coverage_descriptor_id)
        object.__setattr__(self, "source_rule_id", source_rule_id)

    def ability_ids(self) -> tuple[str, ...]:
        return self.ability_ids_value

    def hook_id(self, source: GenericRuleAbilitySource) -> str:
        return _validate_identifier("hook_id", self.hook_id_builder(source))


@dataclass(frozen=True, slots=True)
class GenericRuleMortalWoundFeelNoPainAbility:
    ability_ids_value: tuple[str, ...]
    coverage_descriptor_id: str
    source_rule_id: str
    source_kind: str
    hook_id_builder: GenericRuleHookIdBuilder
    handler: MortalWoundFeelNoPainContinuationHandler

    @property
    def hook_family(self) -> GenericRuleAbilityHookFamily:
        return GenericRuleAbilityHookFamily.MORTAL_WOUND_FEEL_NO_PAIN_CONTINUATION

    def __post_init__(self) -> None:
        _validate_group_descriptor_fields(
            self.ability_ids_value,
            coverage_descriptor_id=self.coverage_descriptor_id,
            source_rule_id=self.source_rule_id,
            set_validated_values=self._set_validated_identity,
        )
        object.__setattr__(
            self,
            "source_kind",
            _validate_identifier("source_kind", self.source_kind),
        )
        _validate_callable(
            "Generic mortal wound Feel No Pain ability hook_id_builder",
            self.hook_id_builder,
        )
        _validate_callable("Generic mortal wound Feel No Pain handler", self.handler)

    def _set_validated_identity(
        self,
        *,
        ability_ids: tuple[str, ...],
        coverage_descriptor_id: str,
        source_rule_id: str,
    ) -> None:
        object.__setattr__(self, "ability_ids_value", ability_ids)
        object.__setattr__(self, "coverage_descriptor_id", coverage_descriptor_id)
        object.__setattr__(self, "source_rule_id", source_rule_id)

    def ability_ids(self) -> tuple[str, ...]:
        return self.ability_ids_value

    def hook_id(self, source: GenericRuleAbilitySource) -> str:
        return _validate_identifier("hook_id", self.hook_id_builder(source))


@dataclass(frozen=True, slots=True)
class GenericRuleWeaponProfileModifierAbility:
    ability_ids_value: tuple[str, ...]
    coverage_descriptor_id: str
    source_rule_id: str
    modifier_id_builder: GenericRuleModifierIdBuilder
    handler: WeaponProfileModifierHandler

    @property
    def hook_family(self) -> GenericRuleAbilityHookFamily:
        return GenericRuleAbilityHookFamily.WEAPON_PROFILE_MODIFIER

    def __post_init__(self) -> None:
        _validate_group_descriptor_fields(
            self.ability_ids_value,
            coverage_descriptor_id=self.coverage_descriptor_id,
            source_rule_id=self.source_rule_id,
            set_validated_values=self._set_validated_identity,
        )
        _validate_callable(
            "Generic weapon profile modifier ability modifier_id_builder",
            self.modifier_id_builder,
        )
        _validate_callable("Generic weapon profile modifier handler", self.handler)

    def _set_validated_identity(
        self,
        *,
        ability_ids: tuple[str, ...],
        coverage_descriptor_id: str,
        source_rule_id: str,
    ) -> None:
        object.__setattr__(self, "ability_ids_value", ability_ids)
        object.__setattr__(self, "coverage_descriptor_id", coverage_descriptor_id)
        object.__setattr__(self, "source_rule_id", source_rule_id)

    def ability_ids(self) -> tuple[str, ...]:
        return self.ability_ids_value

    def modifier_id(self, source: GenericRuleAbilitySource) -> str:
        return _validate_identifier("modifier_id", self.modifier_id_builder(source))


@dataclass(frozen=True, slots=True)
class GenericRuleAbilityRegistry:
    advance_eligibility_abilities: tuple[GenericRuleAdvanceEligibilityAbility, ...] = ()
    shooting_target_restriction_abilities: tuple[
        GenericRuleShootingTargetRestrictionAbility,
        ...,
    ] = ()
    shooting_unit_selected_grant_abilities: tuple[
        GenericRuleShootingUnitSelectedGrantAbility,
        ...,
    ] = ()
    fight_unit_selected_grant_abilities: tuple[
        GenericRuleFightUnitSelectedGrantAbility,
        ...,
    ] = ()
    attack_sequence_completed_abilities: tuple[
        GenericRuleAttackSequenceCompletedAbility,
        ...,
    ] = ()
    mortal_wound_feel_no_pain_abilities: tuple[
        GenericRuleMortalWoundFeelNoPainAbility,
        ...,
    ] = ()
    weapon_profile_modifier_abilities: tuple[
        GenericRuleWeaponProfileModifierAbility,
        ...,
    ] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "advance_eligibility_abilities",
            _validate_descriptor_tuple(
                self.advance_eligibility_abilities,
                descriptor_type=GenericRuleAdvanceEligibilityAbility,
            ),
        )
        object.__setattr__(
            self,
            "shooting_target_restriction_abilities",
            _validate_descriptor_tuple(
                self.shooting_target_restriction_abilities,
                descriptor_type=GenericRuleShootingTargetRestrictionAbility,
            ),
        )
        object.__setattr__(
            self,
            "shooting_unit_selected_grant_abilities",
            _validate_descriptor_tuple(
                self.shooting_unit_selected_grant_abilities,
                descriptor_type=GenericRuleShootingUnitSelectedGrantAbility,
            ),
        )
        object.__setattr__(
            self,
            "fight_unit_selected_grant_abilities",
            _validate_descriptor_tuple(
                self.fight_unit_selected_grant_abilities,
                descriptor_type=GenericRuleFightUnitSelectedGrantAbility,
            ),
        )
        object.__setattr__(
            self,
            "attack_sequence_completed_abilities",
            _validate_descriptor_tuple(
                self.attack_sequence_completed_abilities,
                descriptor_type=GenericRuleAttackSequenceCompletedAbility,
            ),
        )
        object.__setattr__(
            self,
            "mortal_wound_feel_no_pain_abilities",
            _validate_descriptor_tuple(
                self.mortal_wound_feel_no_pain_abilities,
                descriptor_type=GenericRuleMortalWoundFeelNoPainAbility,
            ),
        )
        object.__setattr__(
            self,
            "weapon_profile_modifier_abilities",
            _validate_descriptor_tuple(
                self.weapon_profile_modifier_abilities,
                descriptor_type=GenericRuleWeaponProfileModifierAbility,
            ),
        )


def rule_ir_grants_any_ability(rule_ir: RuleIR, *, abilities: tuple[str, ...]) -> bool:
    if type(rule_ir) is not RuleIR:
        raise GameLifecycleError("Generic RuleIR ability lookup requires RuleIR.")
    expected = set(_validate_ability_ids("generic ability", abilities))
    for clause in rule_ir.clauses:
        for effect in clause.effects:
            if effect.kind is not RuleEffectKind.GRANT_ABILITY:
                continue
            ability = parameter_payload(effect.parameters).get("ability")
            if type(ability) is str and ability in expected:
                return True
    return False


def generic_rule_ability_effects_for_unit(
    *,
    state: GameState,
    source: GenericRuleAbilitySource,
    unit_instance_id: str,
    ability: str,
) -> tuple[PersistingEffect, ...]:
    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR ability effects require GameState.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Generic RuleIR ability effects require source.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    requested_ability = _validate_identifier("ability", ability)
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=requested_unit_id)
    matches: list[PersistingEffect] = []
    for effect in state.persisting_effects_for_unit(rules_unit.unit_instance_id):
        if not _generic_rule_effect_grants_ability(
            effect=effect,
            source=source,
            rules_unit=rules_unit,
            ability=requested_ability,
        ):
            continue
        matches.append(effect)
    return tuple(sorted(matches, key=lambda effect: effect.effect_id))


def generic_rule_ability_source_context_payload(
    *,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
    source_rule_id: str,
    extra_context: Mapping[str, JsonValue],
) -> JsonValue:
    return validate_json_value(
        {
            "source_rule_id": _validate_identifier("source_rule_id", source_rule_id),
            "coverage_descriptor_id": source.record.coverage_descriptor_id,
            "execution_id": source.record.execution_id,
            "rule_ir_source_id": source.rule_ir.source_id,
            "rule_ir_hash": source.rule_ir.ir_hash(),
            "persisting_effect_ids": _persisting_effect_ids(matching_effects),
            **dict(extra_context),
        }
    )


def _generic_rule_effect_grants_ability(
    *,
    effect: PersistingEffect,
    source: GenericRuleAbilitySource,
    rules_unit: RulesUnitView,
    ability: str,
) -> bool:
    payload = _generic_rule_effect_payload_or_none(effect=effect, source=source)
    if payload is None:
        return False
    rule_effect = _payload_object(payload, key="effect")
    if rule_effect.get("kind") != RuleEffectKind.GRANT_ABILITY.value:
        return False
    parameters = _effect_parameters(rule_effect)
    if parameters.get("ability") != ability:
        return False
    return _required_keywords_apply(parameters=parameters, rules_unit=rules_unit)


def _generic_rule_effect_payload_or_none(
    *,
    effect: PersistingEffect,
    source: GenericRuleAbilitySource,
) -> dict[str, JsonValue] | None:
    if type(effect) is not PersistingEffect:
        raise GameLifecycleError("Generic RuleIR ability lookup requires PersistingEffect.")
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        return None
    if payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
        return None
    if payload.get("coverage_descriptor_id") != source.record.coverage_descriptor_id:
        return None
    target_payload = payload.get("target")
    if target_payload is not None:
        if not isinstance(target_payload, dict):
            raise GameLifecycleError("Generic RuleIR ability target payload is malformed.")
        if target_payload.get("kind") != RuleTargetKind.THIS_UNIT.value:
            raise GameLifecycleError("Generic RuleIR ability effect target drift.")
    return dict(payload)


def _payload_object(payload: Mapping[str, JsonValue], *, key: str) -> dict[str, JsonValue]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Generic RuleIR ability payload requires {key}.")
    return dict(value)


def _effect_parameters(effect_payload: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    raw_parameters = effect_payload.get("parameters")
    if not isinstance(raw_parameters, list):
        raise GameLifecycleError("Generic RuleIR ability effect parameters must be a list.")
    parameters: dict[str, JsonValue] = {}
    for raw_parameter in raw_parameters:
        if not isinstance(raw_parameter, dict):
            raise GameLifecycleError("Generic RuleIR ability effect parameter must be an object.")
        key = raw_parameter.get("key")
        if type(key) is not str:
            raise GameLifecycleError("Generic RuleIR ability effect parameter requires key.")
        resolved_key = _validate_identifier("parameter key", key)
        if resolved_key in parameters:
            raise GameLifecycleError("Generic RuleIR ability effect parameters must be unique.")
        parameters[resolved_key] = validate_json_value(raw_parameter.get("value"))
    return parameters


def _required_keywords_apply(
    *,
    parameters: Mapping[str, JsonValue],
    rules_unit: RulesUnitView,
) -> bool:
    required_keywords: list[str] = []
    required_keyword = parameters.get("required_keyword")
    if required_keyword is not None:
        if type(required_keyword) is not str:
            raise GameLifecycleError("Generic RuleIR ability required_keyword must be a string.")
        required_keywords.append(required_keyword)
    required_sequence = parameters.get("required_keyword_sequence")
    if required_sequence is not None:
        if not isinstance(required_sequence, list):
            raise GameLifecycleError(
                "Generic RuleIR ability required_keyword_sequence must be a list."
            )
        for item in required_sequence:
            if type(item) is not str:
                raise GameLifecycleError(
                    "Generic RuleIR ability required_keyword_sequence must contain strings."
                )
            required_keywords.append(item)
    if not required_keywords:
        return True
    return all(_rules_unit_has_keyword(rules_unit, keyword) for keyword in required_keywords)


def _rules_unit_has_keyword(rules_unit: RulesUnitView, keyword: str) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Generic RuleIR ability keyword lookup requires RulesUnitView.")
    requested_keyword = _canonical_keyword(_validate_identifier("keyword", keyword))
    return requested_keyword in {_canonical_keyword(stored) for stored in rules_unit.keywords}


def _persisting_effect_ids(matching_effects: tuple[PersistingEffect, ...]) -> list[str]:
    if type(matching_effects) is not tuple:
        raise GameLifecycleError("Generic RuleIR ability effects must be a tuple.")
    effect_ids: list[str] = []
    for effect in matching_effects:
        if type(effect) is not PersistingEffect:
            raise GameLifecycleError("Generic RuleIR ability effects require PersistingEffect.")
        effect_ids.append(effect.effect_id)
    return effect_ids


def _generic_rule_ability_unit_for_player_context(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    source: GenericRuleAbilitySource,
) -> RulesUnitView | None:
    army = _army_for_player(state=state, player_id=player_id)
    if not _army_uses_record(army=army, source=source):
        return None
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    if rules_unit.owner_player_id != player_id:
        raise GameLifecycleError("Generic RuleIR ability unit owner drift.")
    return rules_unit


def _army_for_player(*, state: GameState, player_id: str) -> ArmyDefinition:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in state.army_definitions:
        if army.player_id == requested_player_id:
            return army
    raise GameLifecycleError("Generic RuleIR ability player army is unknown.")


def _army_uses_record(*, army: ArmyDefinition, source: GenericRuleAbilitySource) -> bool:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Generic RuleIR ability source requires ArmyDefinition.")
    if source.record.detachment_id is None:
        raise GameLifecycleError("Generic RuleIR ability detachment record requires detachment_id.")
    return (
        army.detachment_selection.faction_id == source.record.faction_id
        and source.record.detachment_id in army.detachment_selection.detachment_ids
    )


def _advance_context_unit_id(context: AdvanceEligibilityContext) -> str:
    if type(context) is not AdvanceEligibilityContext:
        raise GameLifecycleError("Generic RuleIR advance ability requires context.")
    return context.unit_instance_id


def _shooting_target_restriction_target_unit_id(
    context: ShootingTargetRestrictionContext,
) -> str:
    if type(context) is not ShootingTargetRestrictionContext:
        raise GameLifecycleError("Generic RuleIR target restriction ability requires context.")
    return context.target_unit_instance_id


def _shooting_unit_selected_unit_id(context: ShootingUnitSelectedContext) -> str:
    if type(context) is not ShootingUnitSelectedContext:
        raise GameLifecycleError("Generic RuleIR shooting grant ability requires context.")
    return context.unit_instance_id


def _fight_unit_selected_unit_id(context: FightUnitSelectedContext) -> str:
    if type(context) is not FightUnitSelectedContext:
        raise GameLifecycleError("Generic RuleIR fight grant ability requires context.")
    return context.unit_instance_id


def _shadow_legion_advance_context_predicate(
    context: AdvanceEligibilityContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> bool:
    if not matching_effects:
        return False
    return (
        _generic_rule_ability_unit_for_player_context(
            state=context.state,
            player_id=context.player_id,
            unit_instance_id=context.unit_instance_id,
            source=source,
        )
        is not None
    )


def _shadow_legion_advance_grant(
    context: AdvanceEligibilityContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> AdvanceEligibilityGrant:
    return AdvanceEligibilityGrant(
        hook_id=_shadow_legion_advance_hook_id(source),
        source_id=_SHADOW_LEGION_SOURCE_RULE_ID,
        can_shoot=True,
        can_declare_charge=True,
        replay_payload=validate_json_value(
            {
                "effect_kind": "generic_rule_advance_eligibility",
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "execution_id": source.record.execution_id,
                "rule_ir_hash": source.rule_ir.ir_hash(),
                "persisting_effect_ids": _persisting_effect_ids(matching_effects),
                "unit_instance_id": context.unit_instance_id,
                "movement_request_id": context.movement_request_id,
                "movement_result_id": context.movement_result_id,
            }
        ),
    )


def _shadow_legion_snap_target_context_predicate(
    context: ShootingTargetRestrictionContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> bool:
    if not matching_effects:
        return False
    if context.shooting_type is not ShootingType.SNAP:
        return False
    target_rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.target_unit_instance_id,
    )
    target_army = _army_for_player(state=context.state, player_id=target_rules_unit.owner_player_id)
    return _army_uses_record(army=target_army, source=source)


def _shadow_legion_snap_target_restriction(
    context: ShootingTargetRestrictionContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> TargetRestriction:
    return TargetRestriction(
        hook_id=_shadow_legion_snap_restriction_hook_id(source),
        source_id=_SHADOW_LEGION_SOURCE_RULE_ID,
        violation_code="shadow_legion_shadows_caress_snap_target_forbidden",
        message="Shadow Legion units cannot be targeted by Snap Shooting attacks.",
        replay_payload=validate_json_value(
            {
                "effect_kind": "generic_rule_snap_target_restriction",
                "coverage_descriptor_id": source.record.coverage_descriptor_id,
                "execution_id": source.record.execution_id,
                "rule_ir_hash": source.rule_ir.ir_hash(),
                "persisting_effect_ids": _persisting_effect_ids(matching_effects),
                "battle_round": context.battle_round,
                "attacking_unit_instance_id": context.attacking_unit_instance_id,
                "target_unit_instance_id": context.target_unit_instance_id,
                "shooting_type": ShootingType.SNAP.value,
            }
        ),
    )


def _shadow_legion_shooting_dark_pact_context_predicate(
    context: ShootingUnitSelectedContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> bool:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
        army_rule as dark_pacts,
    )

    if not matching_effects:
        return False
    if (
        _generic_rule_ability_unit_for_player_context(
            state=context.state,
            player_id=context.player_id,
            unit_instance_id=context.unit_instance_id,
            source=source,
        )
        is None
    ):
        return False
    return (
        dark_pacts.active_dark_pact_for_unit(
            context.state,
            unit_instance_id=context.unit_instance_id,
            phase=BattlePhase.SHOOTING,
        )
        is None
    )


def _shadow_legion_fight_dark_pact_context_predicate(
    context: FightUnitSelectedContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> bool:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
        army_rule as dark_pacts,
    )

    if not matching_effects:
        return False
    if (
        _generic_rule_ability_unit_for_player_context(
            state=context.state,
            player_id=context.player_id,
            unit_instance_id=context.unit_instance_id,
            source=source,
        )
        is None
    ):
        return False
    return (
        dark_pacts.active_dark_pact_for_unit(
            context.state,
            unit_instance_id=context.unit_instance_id,
            phase=BattlePhase.FIGHT,
        )
        is None
    )


def _shadow_legion_shooting_dark_pact_grant_builder(
    pact: str,
    label: str,
) -> ShootingUnitSelectedGrantBuilder:
    def builder(
        context: ShootingUnitSelectedContext,
        source: GenericRuleAbilitySource,
        matching_effects: tuple[PersistingEffect, ...],
    ) -> ShootingUnitSelectedGrant:
        from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (  # noqa: E501
            army_rule as dark_pacts,
        )

        target_unit_ids = dark_pacts.dark_pact_target_unit_ids(
            context.state,
            unit_instance_id=context.unit_instance_id,
        )
        selected_pact = dark_pacts.DarkPactKind(pact)
        extra_context: dict[str, JsonValue] = {
            "selection_request_id": context.request_id,
            "selection_result_id": context.result_id,
        }
        return ShootingUnitSelectedGrant(
            hook_id=_shadow_legion_shooting_dark_pact_hook_id(source, pact),
            source_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            label=label,
            replay_payload=_shadow_legion_dark_pact_replay_payload(
                source=source,
                matching_effects=matching_effects,
                pact=pact,
                trigger="selected_to_shoot",
                unit_instance_id=context.unit_instance_id,
                extra_context=extra_context,
            ),
            unit_effect_payload=dark_pacts.dark_pact_effect_payload(
                unit_instance_id=context.unit_instance_id,
                target_unit_instance_ids=target_unit_ids,
                trigger="selected_to_shoot",
                phase=BattlePhase.SHOOTING,
                selected_dark_pact=selected_pact,
                source_context=generic_rule_ability_source_context_payload(
                    source=source,
                    matching_effects=matching_effects,
                    source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
                    extra_context=extra_context,
                ),
                leadership_test_auto_pass=_rules_unit_is_belakor(
                    state=context.state,
                    unit_instance_id=context.unit_instance_id,
                ),
            ),
            unit_effect_expiration="end_phase",
        )

    return builder


def _shadow_legion_fight_dark_pact_grant_builder(
    pact: str,
    label: str,
) -> FightUnitSelectedGrantBuilder:
    def builder(
        context: FightUnitSelectedContext,
        source: GenericRuleAbilitySource,
        matching_effects: tuple[PersistingEffect, ...],
    ) -> FightUnitSelectedGrant:
        from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (  # noqa: E501
            army_rule as dark_pacts,
        )

        target_unit_ids = dark_pacts.dark_pact_target_unit_ids(
            context.state,
            unit_instance_id=context.unit_instance_id,
        )
        selected_pact = dark_pacts.DarkPactKind(pact)
        extra_context: dict[str, JsonValue] = {
            "activation_request_id": context.request_id,
            "activation_result_id": context.result_id,
            "fight_type": context.fight_type,
            "ordering_band": context.ordering_band,
        }
        return FightUnitSelectedGrant(
            hook_id=_shadow_legion_fight_dark_pact_hook_id(source, pact),
            source_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            label=label,
            replay_payload=_shadow_legion_dark_pact_replay_payload(
                source=source,
                matching_effects=matching_effects,
                pact=pact,
                trigger="selected_to_fight",
                unit_instance_id=context.unit_instance_id,
                extra_context=extra_context,
            ),
            unit_effect_payload=dark_pacts.dark_pact_effect_payload(
                unit_instance_id=context.unit_instance_id,
                target_unit_instance_ids=target_unit_ids,
                trigger="selected_to_fight",
                phase=BattlePhase.FIGHT,
                selected_dark_pact=selected_pact,
                source_context=generic_rule_ability_source_context_payload(
                    source=source,
                    matching_effects=matching_effects,
                    source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
                    extra_context=extra_context,
                ),
                leadership_test_auto_pass=_rules_unit_is_belakor(
                    state=context.state,
                    unit_instance_id=context.unit_instance_id,
                ),
            ),
            unit_effect_expiration="end_phase",
        )

    return builder


def _shadow_legion_dark_pact_replay_payload(
    *,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
    pact: str,
    trigger: str,
    unit_instance_id: str,
    extra_context: Mapping[str, JsonValue],
) -> JsonValue:
    return validate_json_value(
        {
            "effect_kind": _DARK_PACT_EFFECT_KIND,
            "selected_dark_pact": _validate_identifier("selected_dark_pact", pact),
            "trigger": _validate_identifier("trigger", trigger),
            "unit_instance_id": _validate_identifier("unit_instance_id", unit_instance_id),
            "source_rule_id": _SHADOW_LEGION_SOURCE_RULE_ID,
            "coverage_descriptor_id": source.record.coverage_descriptor_id,
            "execution_id": source.record.execution_id,
            "rule_ir_source_id": source.rule_ir.source_id,
            "rule_ir_hash": source.rule_ir.ir_hash(),
            "persisting_effect_ids": _persisting_effect_ids(matching_effects),
            **dict(extra_context),
        }
    )


def _rules_unit_is_belakor(*, state: GameState, unit_instance_id: str) -> bool:
    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR ability Be'lakor lookup requires GameState.")
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    return any(_unit_is_belakor(component.unit) for component in rules_unit.components)


def _unit_is_belakor(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Generic RuleIR ability Be'lakor lookup requires UnitInstance.")
    return _canonical_name(unit.name) == "BELAKOR"


def _shadow_legion_advance_hook_id(source: GenericRuleAbilitySource) -> str:
    return _validate_identifier(
        "generic Shadow Legion advance hook_id",
        f"{source.record.execution_id}:shadow-legion:advance-eligibility",
    )


def _shadow_legion_snap_restriction_hook_id(source: GenericRuleAbilitySource) -> str:
    return _validate_identifier(
        "generic Shadow Legion snap restriction hook_id",
        f"{source.record.execution_id}:shadow-legion:snap-target-restriction",
    )


def _shadow_legion_shooting_dark_pact_hook_id(
    source: GenericRuleAbilitySource,
    pact: str,
) -> str:
    return _validate_identifier(
        "generic Shadow Legion shooting Dark Pact hook_id",
        f"{source.record.execution_id}:shadow-legion:shooting:{pact}",
    )


def _shadow_legion_fight_dark_pact_hook_id(
    source: GenericRuleAbilitySource,
    pact: str,
) -> str:
    return _validate_identifier(
        "generic Shadow Legion Fight Dark Pact hook_id",
        f"{source.record.execution_id}:shadow-legion:fight:{pact}",
    )


def _shadow_legion_shooting_dark_pact_hook_id_builder(
    pact: str,
) -> GenericRuleHookIdBuilder:
    validated_pact = _validate_identifier("generic Shadow Legion shooting Dark Pact kind", pact)

    def builder(source: GenericRuleAbilitySource) -> str:
        return _shadow_legion_shooting_dark_pact_hook_id(source, validated_pact)

    return builder


def _shadow_legion_fight_dark_pact_hook_id_builder(
    pact: str,
) -> GenericRuleHookIdBuilder:
    validated_pact = _validate_identifier("generic Shadow Legion Fight Dark Pact kind", pact)

    def builder(source: GenericRuleAbilitySource) -> str:
        return _shadow_legion_fight_dark_pact_hook_id(source, validated_pact)

    return builder


def _shadow_legion_dark_pact_completion_hook_id(source: GenericRuleAbilitySource) -> str:
    return _validate_identifier(
        "generic Shadow Legion Dark Pact completion hook_id",
        f"{source.record.execution_id}:shadow-legion:dark-pact-completion",
    )


def _shadow_legion_dark_pact_mortal_wound_fnp_hook_id(
    source: GenericRuleAbilitySource,
) -> str:
    return _validate_identifier(
        "generic Shadow Legion Dark Pact FNP hook_id",
        f"{source.record.execution_id}:shadow-legion:dark-pact-mortal-wound-fnp",
    )


def _shadow_legion_dark_pact_weapon_profile_modifier_id(
    source: GenericRuleAbilitySource,
) -> str:
    return _validate_identifier(
        "generic Shadow Legion Dark Pact weapon profile modifier_id",
        f"{source.record.execution_id}:shadow-legion:dark-pact-weapon-profile",
    )


_DARK_PACT_CHOICE_ABILITY_BY_PACT: Mapping[str, str] = MappingProxyType(
    {
        _DARK_PACT_LETHAL_HITS: (
            shadow_legion_ir.SHADOW_LEGION_DARK_PACT_LETHAL_HITS_CHOICE_ABILITY
        ),
        _DARK_PACT_SUSTAINED_HITS_1: (
            shadow_legion_ir.SHADOW_LEGION_DARK_PACT_SUSTAINED_HITS_1_CHOICE_ABILITY
        ),
    }
)
_DARK_PACT_LABEL_BY_PACT: Mapping[str, str] = MappingProxyType(
    {
        _DARK_PACT_LETHAL_HITS: "Dark Pacts: Lethal Hits",
        _DARK_PACT_SUSTAINED_HITS_1: "Dark Pacts: Sustained Hits 1",
    }
)
_SHADOW_LEGION_DARK_PACT_ABILITY_IDS = tuple(_DARK_PACT_CHOICE_ABILITY_BY_PACT.values())


def _shadow_legion_shooting_dark_pact_abilities() -> tuple[
    GenericRuleShootingUnitSelectedGrantAbility,
    ...,
]:
    return tuple(
        GenericRuleShootingUnitSelectedGrantAbility(
            ability_id=ability,
            coverage_descriptor_id=shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            hook_id_builder=_shadow_legion_shooting_dark_pact_hook_id_builder(pact),
            target_unit_id_builder=_shooting_unit_selected_unit_id,
            context_predicate=_shadow_legion_shooting_dark_pact_context_predicate,
            grant_builder=_shadow_legion_shooting_dark_pact_grant_builder(
                pact,
                _DARK_PACT_LABEL_BY_PACT[pact],
            ),
        )
        for pact, ability in _DARK_PACT_CHOICE_ABILITY_BY_PACT.items()
    )


def _shadow_legion_fight_dark_pact_abilities() -> tuple[
    GenericRuleFightUnitSelectedGrantAbility,
    ...,
]:
    return tuple(
        GenericRuleFightUnitSelectedGrantAbility(
            ability_id=ability,
            coverage_descriptor_id=shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            hook_id_builder=_shadow_legion_fight_dark_pact_hook_id_builder(pact),
            target_unit_id_builder=_fight_unit_selected_unit_id,
            context_predicate=_shadow_legion_fight_dark_pact_context_predicate,
            grant_builder=_shadow_legion_fight_dark_pact_grant_builder(
                pact,
                _DARK_PACT_LABEL_BY_PACT[pact],
            ),
        )
        for pact, ability in _DARK_PACT_CHOICE_ABILITY_BY_PACT.items()
    )


def _resolve_shadow_legion_dark_pact_attack_sequence_completion(
    context: AttackSequenceCompletedContext,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
        army_rule as dark_pacts,
    )

    return dark_pacts.resolve_dark_pact_attack_sequence_completion(context)


def _apply_shadow_legion_dark_pact_mortal_wound_feel_no_pain_decision(
    context: MortalWoundFeelNoPainContinuationContext,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
        army_rule as dark_pacts,
    )

    return dark_pacts.apply_dark_pact_mortal_wound_feel_no_pain_decision(context)


def _shadow_legion_dark_pact_weapon_profile_modifier(
    context: WeaponProfileModifierContext,
) -> WeaponProfile:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
        army_rule as dark_pacts,
    )

    return dark_pacts.dark_pact_weapon_profile_modifier(context)


class _SingleDescriptorIdentitySetter(Protocol):
    def __call__(
        self,
        *,
        ability_id: str,
        coverage_descriptor_id: str,
        source_rule_id: str,
    ) -> None: ...


class _GroupDescriptorIdentitySetter(Protocol):
    def __call__(
        self,
        *,
        ability_ids: tuple[str, ...],
        coverage_descriptor_id: str,
        source_rule_id: str,
    ) -> None: ...


type _AnyGenericRuleAbilityDescriptor = (
    GenericRuleAdvanceEligibilityAbility
    | GenericRuleShootingTargetRestrictionAbility
    | GenericRuleShootingUnitSelectedGrantAbility
    | GenericRuleFightUnitSelectedGrantAbility
    | GenericRuleAttackSequenceCompletedAbility
    | GenericRuleMortalWoundFeelNoPainAbility
    | GenericRuleWeaponProfileModifierAbility
)


def _validate_single_descriptor_fields(
    ability_id: object,
    *,
    coverage_descriptor_id: object,
    source_rule_id: object,
    set_validated_values: _SingleDescriptorIdentitySetter,
) -> None:
    set_validated_values(
        ability_id=_validate_identifier("ability_id", ability_id),
        coverage_descriptor_id=_validate_identifier(
            "coverage_descriptor_id",
            coverage_descriptor_id,
        ),
        source_rule_id=_validate_identifier("source_rule_id", source_rule_id),
    )


def _validate_group_descriptor_fields(
    ability_ids: object,
    *,
    coverage_descriptor_id: object,
    source_rule_id: object,
    set_validated_values: _GroupDescriptorIdentitySetter,
) -> None:
    set_validated_values(
        ability_ids=_validate_ability_ids("ability_ids", ability_ids),
        coverage_descriptor_id=_validate_identifier(
            "coverage_descriptor_id",
            coverage_descriptor_id,
        ),
        source_rule_id=_validate_identifier("source_rule_id", source_rule_id),
    )


def _validate_callable(field_name: str, value: object) -> None:
    if not callable(value):
        raise GameLifecycleError(f"{field_name} is not callable.")


def _validate_descriptor_tuple[T](
    value: object,
    *,
    descriptor_type: type[T],
) -> tuple[T, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Generic RuleIR ability registry descriptors must be a tuple.")
    raw_descriptors = cast(tuple[object, ...], value)
    descriptors: list[T] = []
    seen: set[tuple[str, str, tuple[str, ...], str]] = set()
    for descriptor in raw_descriptors:
        if type(descriptor) is not descriptor_type:
            raise GameLifecycleError(
                "Generic RuleIR ability registry contains an invalid descriptor."
            )
        typed_descriptor = descriptor
        key = _descriptor_key(cast(_AnyGenericRuleAbilityDescriptor, typed_descriptor))
        if key in seen:
            raise GameLifecycleError("Generic RuleIR ability registry descriptors must be unique.")
        seen.add(key)
        descriptors.append(typed_descriptor)
    return tuple(descriptors)


def _descriptor_key(
    descriptor: _AnyGenericRuleAbilityDescriptor,
) -> tuple[str, str, tuple[str, ...], str]:
    return (
        descriptor.coverage_descriptor_id,
        descriptor.source_rule_id,
        descriptor.ability_ids(),
        descriptor.hook_family.value,
    )


def _validate_ability_ids(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    if not raw_values:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        resolved = _validate_identifier(f"{field_name} value", value)
        if resolved in seen:
            raise GameLifecycleError(f"{field_name} values must be unique.")
        seen.add(resolved)
        validated.append(resolved)
    return tuple(validated)


def _validate_record_rule_ir_hash(*, record: _Phase17FExecutionRecord, rule_ir: RuleIR) -> None:
    if record.rule_ir_hash is None:
        raise GameLifecycleError("Generic RuleIR ability execution record requires rule_ir_hash.")
    if rule_ir.ir_hash() != record.rule_ir_hash:
        raise GameLifecycleError("Generic RuleIR ability execution record has stale RuleIR hash.")


def _canonical_keyword(value: str) -> str:
    return value.strip().upper().replace("_", " ").replace("-", " ")


def _canonical_name(value: str) -> str:
    return "".join(
        character
        for character in _validate_identifier("name", value).upper()
        if character.isalnum()
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)

DEFAULT_GENERIC_RULE_ABILITY_REGISTRY = GenericRuleAbilityRegistry(
    advance_eligibility_abilities=(
        GenericRuleAdvanceEligibilityAbility(
            ability_id=shadow_legion_ir.CAN_ADVANCE_AND_SHOOT_AND_CHARGE_ABILITY,
            coverage_descriptor_id=shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            hook_id_builder=_shadow_legion_advance_hook_id,
            target_unit_id_builder=_advance_context_unit_id,
            context_predicate=_shadow_legion_advance_context_predicate,
            grant_builder=_shadow_legion_advance_grant,
        ),
    ),
    shooting_target_restriction_abilities=(
        GenericRuleShootingTargetRestrictionAbility(
            ability_id=shadow_legion_ir.SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY,
            coverage_descriptor_id=shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            hook_id_builder=_shadow_legion_snap_restriction_hook_id,
            target_unit_id_builder=_shooting_target_restriction_target_unit_id,
            context_predicate=_shadow_legion_snap_target_context_predicate,
            restriction_builder=_shadow_legion_snap_target_restriction,
        ),
    ),
    shooting_unit_selected_grant_abilities=_shadow_legion_shooting_dark_pact_abilities(),
    fight_unit_selected_grant_abilities=_shadow_legion_fight_dark_pact_abilities(),
    attack_sequence_completed_abilities=(
        GenericRuleAttackSequenceCompletedAbility(
            ability_ids_value=_SHADOW_LEGION_DARK_PACT_ABILITY_IDS,
            coverage_descriptor_id=shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            hook_id_builder=_shadow_legion_dark_pact_completion_hook_id,
            handler=_resolve_shadow_legion_dark_pact_attack_sequence_completion,
        ),
    ),
    mortal_wound_feel_no_pain_abilities=(
        GenericRuleMortalWoundFeelNoPainAbility(
            ability_ids_value=_SHADOW_LEGION_DARK_PACT_ABILITY_IDS,
            coverage_descriptor_id=shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            source_kind=_SHADOW_LEGION_DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND,
            hook_id_builder=_shadow_legion_dark_pact_mortal_wound_fnp_hook_id,
            handler=_apply_shadow_legion_dark_pact_mortal_wound_feel_no_pain_decision,
        ),
    ),
    weapon_profile_modifier_abilities=(
        GenericRuleWeaponProfileModifierAbility(
            ability_ids_value=_SHADOW_LEGION_DARK_PACT_ABILITY_IDS,
            coverage_descriptor_id=shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=_SHADOW_LEGION_SOURCE_RULE_ID,
            modifier_id_builder=_shadow_legion_dark_pact_weapon_profile_modifier_id,
            handler=_shadow_legion_dark_pact_weapon_profile_modifier,
        ),
    ),
)
