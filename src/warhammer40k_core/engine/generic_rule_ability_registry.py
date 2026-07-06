from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.advance_eligibility_hooks import (
    AdvanceEligibilityContext,
    AdvanceEligibilityGrant,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedHandler,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.enhancement_effects import EnhancementEffectContext
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_phase_start_hooks import (
    FightPhaseStartRequestContext,
    FightPhaseStartResultContext,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationHandler,
)
from warhammer40k_core.engine.movement_end_surge_hooks import (
    MovementEndSurgeContext,
    MovementEndSurgeGrant,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    ObjectiveControlModifierContext,
    WeaponProfileModifierHandler,
)
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    ShootingUnitSelectedContext,
    ShootingUnitSelectedGrant,
)
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlContext,
    StickyObjectiveControlState,
)
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionContext,
    TargetRestriction,
)
from warhammer40k_core.engine.turn_end_hooks import TurnEndRequestContext, TurnEndResultContext
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleIR,
    RuleTargetKind,
    parameter_payload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
)

_Phase17FExecutionRecord = faction_execution_2026_27.Phase17FExecutionRecord


class GenericRuleAbilityHookFamily(StrEnum):
    ADVANCE_ELIGIBILITY = "advance_eligibility"
    SHOOTING_TARGET_RESTRICTION = "shooting_target_restriction"
    SHOOTING_UNIT_SELECTED_GRANT = "shooting_unit_selected_grant"
    FIGHT_UNIT_SELECTED_GRANT = "fight_unit_selected_grant"
    ATTACK_SEQUENCE_COMPLETED = "attack_sequence_completed"
    MORTAL_WOUND_FEEL_NO_PAIN_CONTINUATION = "mortal_wound_feel_no_pain_continuation"
    WEAPON_PROFILE_MODIFIER = "weapon_profile_modifier"
    MOVEMENT_END_SURGE = "movement_end_surge"
    PHASE_END_OBJECTIVE_CONTROL = "phase_end_objective_control"
    ENHANCEMENT_EFFECT = "enhancement_effect"
    OBJECTIVE_CONTROL_MODIFIER = "objective_control_modifier"
    UNIT_DESTROYED = "unit_destroyed"
    TURN_END = "turn_end"
    FIGHT_PHASE_START = "fight_phase_start"


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
type MovementEndSurgeContextPredicate = Callable[
    [MovementEndSurgeContext, GenericRuleAbilitySource],
    bool,
]
type MovementEndSurgeGrantBuilder = Callable[
    [MovementEndSurgeContext, GenericRuleAbilitySource],
    tuple[MovementEndSurgeGrant, ...],
]
type PhaseEndObjectiveControlContextPredicate = Callable[
    [PhaseEndObjectiveControlContext, GenericRuleAbilitySource],
    bool,
]
type PhaseEndObjectiveControlStateBuilder = Callable[
    [PhaseEndObjectiveControlContext, GenericRuleAbilitySource],
    tuple[StickyObjectiveControlState, ...],
]
type EnhancementEffectContextPredicate = Callable[
    [EnhancementEffectContext, GenericRuleAbilitySource],
    bool,
]
type EnhancementEffectBuilder = Callable[
    [EnhancementEffectContext, GenericRuleAbilitySource],
    tuple[object, ...],
]
type ObjectiveControlModifierContextPredicate = Callable[
    [ObjectiveControlModifierContext, GenericRuleAbilitySource],
    bool,
]
type ObjectiveControlModifierBuilder = Callable[
    [ObjectiveControlModifierContext, GenericRuleAbilitySource],
    int,
]
type UnitDestroyedBuilder = Callable[
    [UnitDestroyedContext, GenericRuleAbilitySource], object | None
]
type TurnEndRequestBuilder = Callable[
    [TurnEndRequestContext, GenericRuleAbilitySource],
    DecisionRequest | None,
]
type TurnEndResultBuilder = Callable[[TurnEndResultContext, GenericRuleAbilitySource], bool]
type FightPhaseStartRequestBuilder = Callable[
    [FightPhaseStartRequestContext, GenericRuleAbilitySource],
    DecisionRequest | None,
]
type FightPhaseStartResultBuilder = Callable[
    [FightPhaseStartResultContext, GenericRuleAbilitySource],
    bool | LifecycleStatus,
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
class GenericRuleMovementEndSurgeAbility:
    ability_id: str
    coverage_descriptor_id: str
    source_rule_id: str
    hook_id_builder: GenericRuleHookIdBuilder
    context_predicate: MovementEndSurgeContextPredicate
    grant_builder: MovementEndSurgeGrantBuilder

    @property
    def hook_family(self) -> GenericRuleAbilityHookFamily:
        return GenericRuleAbilityHookFamily.MOVEMENT_END_SURGE

    def __post_init__(self) -> None:
        _validate_single_descriptor_fields(
            self.ability_id,
            coverage_descriptor_id=self.coverage_descriptor_id,
            source_rule_id=self.source_rule_id,
            set_validated_values=self._set_validated_identity,
        )
        _validate_callable(
            "Generic movement-end surge ability hook_id_builder",
            self.hook_id_builder,
        )
        _validate_callable(
            "Generic movement-end surge ability context_predicate",
            self.context_predicate,
        )
        _validate_callable(
            "Generic movement-end surge ability grant_builder",
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


@dataclass(frozen=True, slots=True)
class GenericRulePhaseEndObjectiveControlAbility:
    ability_id: str
    coverage_descriptor_id: str
    source_rule_id: str
    hook_id_builder: GenericRuleHookIdBuilder
    context_predicate: PhaseEndObjectiveControlContextPredicate
    state_builder: PhaseEndObjectiveControlStateBuilder

    @property
    def hook_family(self) -> GenericRuleAbilityHookFamily:
        return GenericRuleAbilityHookFamily.PHASE_END_OBJECTIVE_CONTROL

    def __post_init__(self) -> None:
        _validate_single_descriptor_fields(
            self.ability_id,
            coverage_descriptor_id=self.coverage_descriptor_id,
            source_rule_id=self.source_rule_id,
            set_validated_values=self._set_validated_identity,
        )
        _validate_callable(
            "Generic phase-end objective-control ability hook_id_builder",
            self.hook_id_builder,
        )
        _validate_callable(
            "Generic phase-end objective-control ability context_predicate",
            self.context_predicate,
        )
        _validate_callable(
            "Generic phase-end objective-control ability state_builder",
            self.state_builder,
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


@dataclass(frozen=True, slots=True)
class GenericRuleEnhancementEffectAbility:
    ability_id: str
    coverage_descriptor_id: str
    source_rule_id: str
    enhancement_id: str
    effect_id_builder: GenericRuleHookIdBuilder
    context_predicate: EnhancementEffectContextPredicate
    effect_builder: EnhancementEffectBuilder

    @property
    def hook_family(self) -> GenericRuleAbilityHookFamily:
        return GenericRuleAbilityHookFamily.ENHANCEMENT_EFFECT

    def __post_init__(self) -> None:
        _validate_single_descriptor_fields(
            self.ability_id,
            coverage_descriptor_id=self.coverage_descriptor_id,
            source_rule_id=self.source_rule_id,
            set_validated_values=self._set_validated_identity,
        )
        object.__setattr__(
            self,
            "enhancement_id",
            _validate_identifier("enhancement_id", self.enhancement_id),
        )
        _validate_callable(
            "Generic enhancement effect ability effect_id_builder", self.effect_id_builder
        )
        _validate_callable(
            "Generic enhancement effect ability context_predicate", self.context_predicate
        )
        _validate_callable("Generic enhancement effect ability effect_builder", self.effect_builder)

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

    def effect_id(self, source: GenericRuleAbilitySource) -> str:
        return _validate_identifier("effect_id", self.effect_id_builder(source))


@dataclass(frozen=True, slots=True)
class GenericRuleObjectiveControlModifierAbility:
    ability_id: str
    coverage_descriptor_id: str
    source_rule_id: str
    modifier_id_builder: GenericRuleModifierIdBuilder
    context_predicate: ObjectiveControlModifierContextPredicate
    modifier_builder: ObjectiveControlModifierBuilder

    @property
    def hook_family(self) -> GenericRuleAbilityHookFamily:
        return GenericRuleAbilityHookFamily.OBJECTIVE_CONTROL_MODIFIER

    def __post_init__(self) -> None:
        _validate_single_descriptor_fields(
            self.ability_id,
            coverage_descriptor_id=self.coverage_descriptor_id,
            source_rule_id=self.source_rule_id,
            set_validated_values=self._set_validated_identity,
        )
        _validate_callable(
            "Generic objective-control modifier ability modifier_id_builder",
            self.modifier_id_builder,
        )
        _validate_callable(
            "Generic objective-control modifier ability context_predicate",
            self.context_predicate,
        )
        _validate_callable(
            "Generic objective-control modifier ability modifier_builder",
            self.modifier_builder,
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

    def modifier_id(self, source: GenericRuleAbilitySource) -> str:
        return _validate_identifier("modifier_id", self.modifier_id_builder(source))


@dataclass(frozen=True, slots=True)
class GenericRuleUnitDestroyedAbility:
    ability_id: str
    coverage_descriptor_id: str
    source_rule_id: str
    hook_id_builder: GenericRuleHookIdBuilder
    effect_builder: UnitDestroyedBuilder

    @property
    def hook_family(self) -> GenericRuleAbilityHookFamily:
        return GenericRuleAbilityHookFamily.UNIT_DESTROYED

    def __post_init__(self) -> None:
        _validate_single_descriptor_fields(
            self.ability_id,
            coverage_descriptor_id=self.coverage_descriptor_id,
            source_rule_id=self.source_rule_id,
            set_validated_values=self._set_validated_identity,
        )
        _validate_callable("Generic unit-destroyed ability hook_id_builder", self.hook_id_builder)
        _validate_callable("Generic unit-destroyed ability effect_builder", self.effect_builder)

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


@dataclass(frozen=True, slots=True)
class GenericRuleTurnEndAbility:
    ability_id: str
    coverage_descriptor_id: str
    source_rule_id: str
    hook_id_builder: GenericRuleHookIdBuilder
    request_builder: TurnEndRequestBuilder
    result_builder: TurnEndResultBuilder

    @property
    def hook_family(self) -> GenericRuleAbilityHookFamily:
        return GenericRuleAbilityHookFamily.TURN_END

    def __post_init__(self) -> None:
        _validate_single_descriptor_fields(
            self.ability_id,
            coverage_descriptor_id=self.coverage_descriptor_id,
            source_rule_id=self.source_rule_id,
            set_validated_values=self._set_validated_identity,
        )
        _validate_callable("Generic turn-end ability hook_id_builder", self.hook_id_builder)
        _validate_callable("Generic turn-end ability request_builder", self.request_builder)
        _validate_callable("Generic turn-end ability result_builder", self.result_builder)

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


@dataclass(frozen=True, slots=True)
class GenericRuleFightPhaseStartAbility:
    ability_id: str
    coverage_descriptor_id: str
    source_rule_id: str
    hook_id_builder: GenericRuleHookIdBuilder
    request_builder: FightPhaseStartRequestBuilder
    result_builder: FightPhaseStartResultBuilder

    @property
    def hook_family(self) -> GenericRuleAbilityHookFamily:
        return GenericRuleAbilityHookFamily.FIGHT_PHASE_START

    def __post_init__(self) -> None:
        _validate_single_descriptor_fields(
            self.ability_id,
            coverage_descriptor_id=self.coverage_descriptor_id,
            source_rule_id=self.source_rule_id,
            set_validated_values=self._set_validated_identity,
        )
        _validate_callable(
            "Generic fight-phase-start ability hook_id_builder",
            self.hook_id_builder,
        )
        _validate_callable(
            "Generic fight-phase-start ability request_builder",
            self.request_builder,
        )
        _validate_callable(
            "Generic fight-phase-start ability result_builder",
            self.result_builder,
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
    movement_end_surge_abilities: tuple[
        GenericRuleMovementEndSurgeAbility,
        ...,
    ] = ()
    phase_end_objective_control_abilities: tuple[
        GenericRulePhaseEndObjectiveControlAbility,
        ...,
    ] = ()
    enhancement_effect_abilities: tuple[
        GenericRuleEnhancementEffectAbility,
        ...,
    ] = ()
    objective_control_modifier_abilities: tuple[
        GenericRuleObjectiveControlModifierAbility,
        ...,
    ] = ()
    unit_destroyed_abilities: tuple[
        GenericRuleUnitDestroyedAbility,
        ...,
    ] = ()
    turn_end_abilities: tuple[
        GenericRuleTurnEndAbility,
        ...,
    ] = ()
    fight_phase_start_abilities: tuple[
        GenericRuleFightPhaseStartAbility,
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
        object.__setattr__(
            self,
            "movement_end_surge_abilities",
            _validate_descriptor_tuple(
                self.movement_end_surge_abilities,
                descriptor_type=GenericRuleMovementEndSurgeAbility,
            ),
        )
        object.__setattr__(
            self,
            "phase_end_objective_control_abilities",
            _validate_descriptor_tuple(
                self.phase_end_objective_control_abilities,
                descriptor_type=GenericRulePhaseEndObjectiveControlAbility,
            ),
        )
        object.__setattr__(
            self,
            "enhancement_effect_abilities",
            _validate_descriptor_tuple(
                self.enhancement_effect_abilities,
                descriptor_type=GenericRuleEnhancementEffectAbility,
            ),
        )
        object.__setattr__(
            self,
            "objective_control_modifier_abilities",
            _validate_descriptor_tuple(
                self.objective_control_modifier_abilities,
                descriptor_type=GenericRuleObjectiveControlModifierAbility,
            ),
        )
        object.__setattr__(
            self,
            "unit_destroyed_abilities",
            _validate_descriptor_tuple(
                self.unit_destroyed_abilities,
                descriptor_type=GenericRuleUnitDestroyedAbility,
            ),
        )
        object.__setattr__(
            self,
            "turn_end_abilities",
            _validate_descriptor_tuple(
                self.turn_end_abilities,
                descriptor_type=GenericRuleTurnEndAbility,
            ),
        )
        object.__setattr__(
            self,
            "fight_phase_start_abilities",
            _validate_descriptor_tuple(
                self.fight_phase_start_abilities,
                descriptor_type=GenericRuleFightPhaseStartAbility,
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
            "persisting_effect_ids": generic_rule_persisting_effect_ids(matching_effects),
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
    required_keywords = _required_keyword_values(
        parameters=parameters,
        singular_key="required_keyword",
        sequence_key="required_keyword_sequence",
    )
    required_faction_keywords = _required_keyword_values(
        parameters=parameters,
        singular_key="required_faction_keyword",
        sequence_key="required_faction_keyword_sequence",
    )
    if not required_keywords and not required_faction_keywords:
        return True
    return all(
        _rules_unit_has_keyword(rules_unit, keyword) for keyword in required_keywords
    ) and all(
        _rules_unit_has_faction_keyword(rules_unit, keyword)
        for keyword in required_faction_keywords
    )


def _required_keyword_values(
    *,
    parameters: Mapping[str, JsonValue],
    singular_key: str,
    sequence_key: str,
) -> tuple[str, ...]:
    required_keywords: list[str] = []
    required_keyword = parameters.get(singular_key)
    if required_keyword is not None:
        if type(required_keyword) is not str:
            raise GameLifecycleError(f"Generic RuleIR ability {singular_key} must be a string.")
        required_keywords.append(required_keyword)
    required_sequence = parameters.get(sequence_key)
    if required_sequence is not None:
        if not isinstance(required_sequence, list):
            raise GameLifecycleError(f"Generic RuleIR ability {sequence_key} must be a list.")
        for item in required_sequence:
            if type(item) is not str:
                raise GameLifecycleError(
                    f"Generic RuleIR ability {sequence_key} must contain strings."
                )
            required_keywords.append(item)
    return tuple(required_keywords)


def _rules_unit_has_keyword(rules_unit: RulesUnitView, keyword: str) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Generic RuleIR ability keyword lookup requires RulesUnitView.")
    requested_keyword = _canonical_keyword(_validate_identifier("keyword", keyword))
    return requested_keyword in {_canonical_keyword(stored) for stored in rules_unit.keywords}


def _rules_unit_has_faction_keyword(rules_unit: RulesUnitView, keyword: str) -> bool:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Generic RuleIR ability keyword lookup requires RulesUnitView.")
    requested_keyword = _canonical_keyword(_validate_identifier("keyword", keyword))
    return requested_keyword in {
        _canonical_keyword(stored) for stored in rules_unit.faction_keywords
    }


def generic_rule_persisting_effect_ids(matching_effects: tuple[PersistingEffect, ...]) -> list[str]:
    if type(matching_effects) is not tuple:
        raise GameLifecycleError("Generic RuleIR ability effects must be a tuple.")
    effect_ids: list[str] = []
    for effect in matching_effects:
        if type(effect) is not PersistingEffect:
            raise GameLifecycleError("Generic RuleIR ability effects require PersistingEffect.")
        effect_ids.append(effect.effect_id)
    return effect_ids


def generic_rule_ability_unit_for_player_context(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    source: GenericRuleAbilitySource,
) -> RulesUnitView | None:
    army = generic_rule_army_for_player(state=state, player_id=player_id)
    if not generic_rule_army_uses_record(army=army, source=source):
        return None
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    if rules_unit.owner_player_id != player_id:
        raise GameLifecycleError("Generic RuleIR ability unit owner drift.")
    return rules_unit


def generic_rule_army_for_player(*, state: GameState, player_id: str) -> ArmyDefinition:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in state.army_definitions:
        if army.player_id == requested_player_id:
            return army
    raise GameLifecycleError("Generic RuleIR ability player army is unknown.")


def generic_rule_army_uses_record(
    *, army: ArmyDefinition, source: GenericRuleAbilitySource
) -> bool:
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Generic RuleIR ability source requires ArmyDefinition.")
    if source.record.detachment_id is None:
        raise GameLifecycleError("Generic RuleIR ability detachment record requires detachment_id.")
    return (
        army.detachment_selection.faction_id == source.record.faction_id
        and source.record.detachment_id in army.detachment_selection.detachment_ids
    )


def generic_rule_advance_context_unit_id(context: AdvanceEligibilityContext) -> str:
    if type(context) is not AdvanceEligibilityContext:
        raise GameLifecycleError("Generic RuleIR advance ability requires context.")
    return context.unit_instance_id


def generic_rule_shooting_target_restriction_target_unit_id(
    context: ShootingTargetRestrictionContext,
) -> str:
    if type(context) is not ShootingTargetRestrictionContext:
        raise GameLifecycleError("Generic RuleIR target restriction ability requires context.")
    return context.target_unit_instance_id


def generic_rule_shooting_unit_selected_unit_id(context: ShootingUnitSelectedContext) -> str:
    if type(context) is not ShootingUnitSelectedContext:
        raise GameLifecycleError("Generic RuleIR shooting grant ability requires context.")
    return context.unit_instance_id


def generic_rule_fight_unit_selected_unit_id(context: FightUnitSelectedContext) -> str:
    if type(context) is not FightUnitSelectedContext:
        raise GameLifecycleError("Generic RuleIR fight grant ability requires context.")
    return context.unit_instance_id


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
    | GenericRuleMovementEndSurgeAbility
    | GenericRulePhaseEndObjectiveControlAbility
    | GenericRuleEnhancementEffectAbility
    | GenericRuleObjectiveControlModifierAbility
    | GenericRuleUnitDestroyedAbility
    | GenericRuleTurnEndAbility
    | GenericRuleFightPhaseStartAbility
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


_validate_identifier = IdentifierValidator(GameLifecycleError)
