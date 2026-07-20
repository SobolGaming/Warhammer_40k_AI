from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, TypeVar, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.weapon_profiles import (
    RangeProfileKind,
    WeaponProfile,
)
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilitySourceKind,
)
from warhammer40k_core.engine.advance_hooks import (
    AdvanceMoveContext,
    AdvanceMoveGrant,
    AdvanceMoveHookBinding,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.catalog_any_phase_once_per_battle import (
    CatalogAnyPhaseOncePerBattleRuntime,
)
from warhammer40k_core.engine.catalog_conditional_leader_queries import (
    catalog_granted_stealth_hit_roll_modifier,
)
from warhammer40k_core.engine.catalog_datasheet_rule_descriptors import (
    CatalogConditionalAttackRerollDescriptor,
    CatalogConditionalInvulnerableSaveDescriptor,
    CatalogConditionalProximityEffectsDescriptor,
    CatalogFightOnDeathDescriptor,
    CatalogFirstFailedSaveDamageReplacementDescriptor,
    CatalogInvulnerableSaveDescriptor,
    CatalogMovementActionGrantDescriptor,
    CatalogPassiveHitRerollDescriptor,
    conditional_attack_reroll_descriptor_for_clause,
    conditional_invulnerable_save_descriptor_for_clause,
    conditional_proximity_effects_descriptor_for_clause,
    fight_on_death_descriptor_for_clause,
    first_failed_save_damage_replacement_descriptor_for_clause,
    invulnerable_save_descriptor_for_clause,
    movement_action_grant_descriptor_for_clause,
    passive_hit_reroll_descriptor_for_clause,
)
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
    CATALOG_IR_FIGHT_ACTIVATION_MOVEMENT_DISTANCE_CONSUMER_ID,
    CATALOG_IR_FIGHT_ON_DEATH_SOURCE_CONSUMER_ID,
    CATALOG_IR_FIGHT_SELECTED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
    CATALOG_IR_GRANTED_STEALTH_CONSUMER_ID,
    CATALOG_IR_STEALTH_AURA_CONSUMER_ID,
    clause_is_charge_end_leading_unit_weapon_ability_grant,
    clause_is_conditional_lone_operative,
    clause_is_consolidation_move_distance_modifier,
    clause_is_fight_selected_weapon_ability_choice,
    clause_is_granted_stealth_effect,
    clause_is_leading_unit_hit_roll_modifier,
    clause_is_leading_unit_wound_roll_modifier,
    clause_is_passive_characteristic_modifier,
    clause_is_stealth_aura,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_record_current_wargear_bearer_model_ids,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionKind,
    DestructionReactionSource,
)
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEventHandlerBinding,
    RuntimeContentEventSubscription,
)
from warhammer40k_core.engine.fight_activation_abilities import (
    FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
    FightActivationAbilityContext,
    FightActivationAbilityHookBinding,
    FightActivationAbilityOption,
)
from warhammer40k_core.engine.fight_order import CHARGE_FIGHTS_FIRST_EFFECT_KIND
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
    FightUnitSelectedGrantBinding,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    generic_rule_effect_payload,
    rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.rule_ir_weapon_modifiers import (
    rule_ir_modified_weapon_profile,
    rule_ir_weapon_ability_granted_profile,
    rule_ir_weapon_selector_applies,
)
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    AttackRerollPermissionBinding,
    AttackRerollPermissionContext,
    FailedSaveDamageReplacement,
    FailedSaveDamageReplacementBinding,
    FailedSaveDamageReplacementContext,
    HitRollModifierBinding,
    HitRollModifierContext,
    MovementBudgetModifierBinding,
    MovementBudgetModifierContext,
    SaveOptionModifierBinding,
    SaveOptionModifierContext,
    UnitCharacteristicModifierBinding,
    UnitCharacteristicModifierContext,
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
    WoundRollModifierBinding,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, SaveOption
from warhammer40k_core.engine.shooting_selection_range import (
    target_within_shooting_selection_range,
)
from warhammer40k_core.engine.source_backed_rerolls import (
    SourceBackedRerollPermissionContext,
)
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionContext,
    ShootingTargetRestrictionHookBinding,
    TargetRestriction,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_proximity import (
    rules_unit_within_friendly_keyworded_models,
    rules_unit_within_friendly_keyworded_units,
)
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    parameter_payload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


@dataclass(frozen=True, slots=True)
class _CatalogClauseSource:
    player_id: str
    record: AbilityCatalogRecord
    unit: UnitInstance
    clause: RuleClause
    rule_ir: RuleIR

    @property
    def binding_id(self) -> str:
        return f"catalog-ir:datasheet:{self.unit.unit_instance_id}:{self.clause.clause_id}"


_DescriptorT = TypeVar("_DescriptorT")


@dataclass(frozen=True, slots=True)
class CatalogDatasheetRuleRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _validate_indexes(self.ability_indexes_by_player_id)
        armies = _validate_armies(self.armies)
        if set(indexes) != {army.player_id for army in armies}:
            raise GameLifecycleError("Catalog datasheet runtime indexes must match armies.")
        object.__setattr__(self, "ability_indexes_by_player_id", indexes)
        object.__setattr__(self, "armies", armies)

    def unit_characteristic_modifier_bindings(
        self,
    ) -> tuple[UnitCharacteristicModifierBinding, ...]:
        bindings = tuple(
            UnitCharacteristicModifierBinding(
                modifier_id=source.binding_id,
                source_id=source.rule_ir.source_id,
                handler=self._unit_characteristic_handler(source),
            )
            for source in self._sources(clause_is_passive_characteristic_modifier)
            if _source_characteristic(source) is Characteristic.TOUGHNESS
        )
        proximity_bindings = tuple(
            UnitCharacteristicModifierBinding(
                modifier_id=f"{source.binding_id}:conditional-characteristic",
                source_id=source.rule_ir.source_id,
                handler=self._conditional_proximity_characteristic_handler(source, descriptor),
            )
            for source, descriptor in self._described_sources(
                conditional_proximity_effects_descriptor_for_clause
            )
        )
        return (*bindings, *proximity_bindings)

    def record_static_destruction_reaction_sources(
        self,
        *,
        state: object,
    ) -> tuple[tuple[str, DestructionReactionSource], ...]:
        from warhammer40k_core.engine.game_state import GameState

        if type(state) is not GameState:
            raise GameLifecycleError(
                "Catalog destruction-reaction registration requires GameState."
            )
        recorded: list[tuple[str, DestructionReactionSource]] = []
        for source, descriptor in self._described_sources(fight_on_death_descriptor_for_clause):
            for model_id in _static_source_model_ids(source):
                reaction = _catalog_fight_on_death_source(
                    source=source,
                    descriptor=descriptor,
                    model_instance_id=model_id,
                )
                _record_destruction_reaction_source(
                    state=state,
                    model_instance_id=model_id,
                    source=reaction,
                )
                recorded.append((model_id, reaction))
        return tuple(sorted(recorded, key=lambda item: (item[0], item[1].source_id)))

    def record_static_sources(self, *, state: GameState) -> None:
        from warhammer40k_core.engine.catalog_conditional_leader_abilities import (
            CatalogConditionalLeaderAbilityRuntime,
        )

        self.record_static_destruction_reaction_sources(state=state)
        CatalogConditionalLeaderAbilityRuntime(
            self.ability_indexes_by_player_id,
            self.armies,
        ).record_static_effects(state=state)

    def event_handler_bindings(self) -> tuple[RuntimeContentEventHandlerBinding, ...]:
        return CatalogAnyPhaseOncePerBattleRuntime(
            self.ability_indexes_by_player_id, self.armies
        ).event_handler_bindings()

    def event_subscriptions(self) -> tuple[RuntimeContentEventSubscription, ...]:
        return CatalogAnyPhaseOncePerBattleRuntime(
            self.ability_indexes_by_player_id, self.armies
        ).event_subscriptions()

    def movement_budget_modifier_bindings(self) -> tuple[MovementBudgetModifierBinding, ...]:
        passive = tuple(
            MovementBudgetModifierBinding(
                modifier_id=source.binding_id,
                source_id=source.rule_ir.source_id,
                handler=self._movement_handler(source),
            )
            for source in self._sources(clause_is_passive_characteristic_modifier)
            if _source_characteristic(source) is Characteristic.MOVEMENT
        )
        grants = tuple(
            MovementBudgetModifierBinding(
                modifier_id=f"{source.binding_id}:movement-action-grant",
                source_id=source.rule_ir.source_id,
                handler=self._movement_action_grant_movement_handler(source, descriptor),
            )
            for source, descriptor in self._described_sources(
                movement_action_grant_descriptor_for_clause
            )
        )
        return (*passive, *grants)

    def advance_move_hook_bindings(self) -> tuple[AdvanceMoveHookBinding, ...]:
        return tuple(
            AdvanceMoveHookBinding(
                hook_id=f"{source.binding_id}:movement-action-grant",
                source_id=source.rule_ir.source_id,
                handler=self._movement_action_grant_handler(source, descriptor),
            )
            for source, descriptor in self._described_sources(
                movement_action_grant_descriptor_for_clause
            )
        )

    def save_option_modifier_bindings(self) -> tuple[SaveOptionModifierBinding, ...]:
        passive = tuple(
            SaveOptionModifierBinding(
                modifier_id=source.binding_id,
                source_id=source.rule_ir.source_id,
                handler=self._save_option_handler(source, descriptor),
            )
            for source, descriptor in self._described_sources(
                invulnerable_save_descriptor_for_clause
            )
        )
        conditional = tuple(
            SaveOptionModifierBinding(
                modifier_id=f"{source.binding_id}:conditional-invulnerable-save",
                source_id=source.rule_ir.source_id,
                handler=self._conditional_invulnerable_save_handler(source, descriptor),
            )
            for source, descriptor in self._described_sources(
                conditional_invulnerable_save_descriptor_for_clause
            )
        )
        return (*passive, *conditional)

    def attack_reroll_permission_bindings(
        self,
    ) -> tuple[AttackRerollPermissionBinding, ...]:
        passive = tuple(
            AttackRerollPermissionBinding(
                modifier_id=source.binding_id,
                source_id=source.rule_ir.source_id,
                handler=self._attack_reroll_permission_handler(source, descriptor),
            )
            for source, descriptor in self._described_sources(
                passive_hit_reroll_descriptor_for_clause
            )
        )
        conditional = tuple(
            AttackRerollPermissionBinding(
                modifier_id=f"{source.binding_id}:conditional-attack-rerolls",
                source_id=source.rule_ir.source_id,
                handler=self._conditional_attack_reroll_permission_handler(source, descriptor),
            )
            for source, descriptor in self._described_sources(
                conditional_attack_reroll_descriptor_for_clause
            )
        )
        return (*passive, *conditional)

    def failed_save_damage_replacement_bindings(
        self,
    ) -> tuple[FailedSaveDamageReplacementBinding, ...]:
        return tuple(
            FailedSaveDamageReplacementBinding(
                modifier_id=source.binding_id,
                source_id=source.rule_ir.source_id,
                handler=self._failed_save_damage_replacement_handler(source, descriptor),
            )
            for source, descriptor in self._described_sources(
                first_failed_save_damage_replacement_descriptor_for_clause
            )
        )

    def weapon_profile_modifier_bindings(self) -> tuple[WeaponProfileModifierBinding, ...]:
        bindings: list[WeaponProfileModifierBinding] = []
        bindings.extend(
            WeaponProfileModifierBinding(
                modifier_id=source.binding_id,
                source_id=source.rule_ir.source_id,
                handler=self._weapon_characteristic_handler(source),
            )
            for source in self._sources(clause_is_passive_characteristic_modifier)
            if _source_characteristic(source) in {Characteristic.ATTACKS, Characteristic.STRENGTH}
        )
        bindings.extend(
            WeaponProfileModifierBinding(
                modifier_id=source.binding_id,
                source_id=source.rule_ir.source_id,
                handler=self._charge_end_weapon_ability_handler(source),
            )
            for source in self._sources(clause_is_charge_end_leading_unit_weapon_ability_grant)
        )
        bindings.extend(
            WeaponProfileModifierBinding(
                modifier_id=f"{source.binding_id}:conditional-weapon-characteristic",
                source_id=source.rule_ir.source_id,
                handler=self._conditional_proximity_weapon_handler(source, descriptor),
            )
            for source, descriptor in self._described_sources(
                conditional_proximity_effects_descriptor_for_clause
            )
            if descriptor.weapon_characteristic_deltas
        )
        return tuple(bindings)

    def hit_roll_modifier_bindings(self) -> tuple[HitRollModifierBinding, ...]:
        sources = self._sources(clause_is_stealth_aura)
        bindings: list[HitRollModifierBinding] = []
        if sources:
            bindings.append(
                HitRollModifierBinding(
                    modifier_id=CATALOG_IR_STEALTH_AURA_CONSUMER_ID,
                    source_id=CATALOG_IR_STEALTH_AURA_CONSUMER_ID,
                    handler=self._stealth_handler(sources),
                )
            )
        bindings.extend(
            HitRollModifierBinding(
                modifier_id=source.binding_id,
                source_id=source.rule_ir.source_id,
                handler=self._leading_unit_hit_roll_handler(source),
            )
            for source in self._sources(clause_is_leading_unit_hit_roll_modifier)
        )
        bindings.extend(
            HitRollModifierBinding(
                modifier_id=f"{source.binding_id}:conditional-hit-roll",
                source_id=source.rule_ir.source_id,
                handler=self._conditional_proximity_hit_roll_handler(source, descriptor),
            )
            for source, descriptor in self._described_sources(
                conditional_proximity_effects_descriptor_for_clause
            )
            if descriptor.hit_roll_delta is not None
        )
        if self._sources(clause_is_granted_stealth_effect):
            bindings.append(
                HitRollModifierBinding(
                    modifier_id=CATALOG_IR_GRANTED_STEALTH_CONSUMER_ID,
                    source_id=CATALOG_IR_GRANTED_STEALTH_CONSUMER_ID,
                    handler=self._granted_stealth_handler,
                )
            )
        return tuple(bindings)

    def wound_roll_modifier_bindings(self) -> tuple[WoundRollModifierBinding, ...]:
        return tuple(
            WoundRollModifierBinding(
                modifier_id=source.binding_id,
                source_id=source.rule_ir.source_id,
                handler=self._wound_roll_handler(source),
            )
            for source in self._sources(clause_is_leading_unit_wound_roll_modifier)
        )

    def shooting_target_restriction_bindings(
        self,
    ) -> tuple[ShootingTargetRestrictionHookBinding, ...]:
        sources = self._sources(clause_is_conditional_lone_operative)
        if not sources:
            return ()
        return (
            ShootingTargetRestrictionHookBinding(
                hook_id=CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
                source_id=CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
                handler=self._lone_operative_handler(sources),
            ),
        )

    def fight_activation_ability_hook_bindings(
        self,
    ) -> tuple[FightActivationAbilityHookBinding, ...]:
        return tuple(
            FightActivationAbilityHookBinding(
                hook_id=source.binding_id,
                source_id=source.rule_ir.source_id,
                handler=self._fight_activation_movement_handler(source),
            )
            for source in self._sources(clause_is_consolidation_move_distance_modifier)
        )

    def fight_unit_selected_grant_bindings(
        self,
    ) -> tuple[FightUnitSelectedGrantBinding, ...]:
        bindings: list[FightUnitSelectedGrantBinding] = []
        for source in self._sources(clause_is_fight_selected_weapon_ability_choice):
            for effect in source.clause.effects:
                option_id = _required_string(
                    parameter_payload(effect.parameters), "selection_option_id"
                )
                hook_id = f"{source.binding_id}:{option_id}"
                bindings.append(
                    FightUnitSelectedGrantBinding(
                        hook_id=hook_id,
                        source_id=source.rule_ir.source_id,
                        handler=self._fight_grant_handler(
                            source=source,
                            effect=effect,
                            hook_id=hook_id,
                        ),
                    )
                )
        return tuple(bindings)

    def _sources(self, predicate: Callable[[RuleClause], bool]) -> tuple[_CatalogClauseSource, ...]:
        sources: list[_CatalogClauseSource] = []
        for army in self.armies:
            index = self.ability_indexes_by_player_id[army.player_id]
            for record in index.all_records():
                if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                    continue
                rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
                for unit in army.units:
                    if not catalog_rule_record_source_matches_unit(
                        record=record,
                        unit=unit,
                        current_model_instance_ids=unit.own_model_ids(),
                    ):
                        continue
                    sources.extend(
                        _CatalogClauseSource(
                            player_id=army.player_id,
                            record=record,
                            unit=unit,
                            clause=clause,
                            rule_ir=rule_ir,
                        )
                        for clause in catalog_rule_clauses_from_record(record)
                        if predicate(clause)
                    )
        return tuple(sorted(sources, key=lambda source: source.binding_id))

    def _described_sources(
        self,
        parser: Callable[[RuleClause], _DescriptorT | None],
    ) -> tuple[tuple[_CatalogClauseSource, _DescriptorT], ...]:
        described: list[tuple[_CatalogClauseSource, _DescriptorT]] = []
        for source in self._sources(lambda clause: parser(clause) is not None):
            descriptor = parser(source.clause)
            if descriptor is None:
                raise GameLifecycleError("Catalog datasheet descriptor classification drift.")
            described.append((source, descriptor))
        return tuple(described)

    def _unit_characteristic_handler(
        self, source: _CatalogClauseSource
    ) -> Callable[[UnitCharacteristicModifierContext], int]:
        def handler(context: UnitCharacteristicModifierContext) -> int:
            if not _source_applies_to_rules_unit(
                source=source, context_unit_id=context.unit_instance_id, state=context.state
            ):
                return context.current_value
            characteristic, delta = _source_characteristic_delta(source)
            if characteristic is not context.characteristic or not _source_keyword_gate_applies(
                source
            ):
                return context.current_value
            return context.current_value + delta

        return handler

    def _movement_handler(
        self, source: _CatalogClauseSource
    ) -> Callable[[MovementBudgetModifierContext], float]:
        def handler(context: MovementBudgetModifierContext) -> float:
            if not _source_applies_to_rules_unit(
                source=source, context_unit_id=context.unit_instance_id, state=context.state
            ):
                return context.current_movement_inches
            if context.model_instance_id not in _current_source_model_ids(
                state=context.state, source=source
            ) or not _source_keyword_gate_applies(source):
                return context.current_movement_inches
            return context.current_movement_inches + float(_source_characteristic_delta(source)[1])

        return handler

    def _save_option_handler(
        self,
        source: _CatalogClauseSource,
        descriptor: CatalogInvulnerableSaveDescriptor,
    ) -> Callable[[SaveOptionModifierContext], tuple[SaveOption, ...]]:
        def handler(context: SaveOptionModifierContext) -> tuple[SaveOption, ...]:
            allocated_model_id = context.allocated_model_instance_id
            if allocated_model_id is None or not _source_applies_to_rules_unit(
                source=source,
                context_unit_id=context.target_unit_instance_id,
                state=context.state,
            ):
                return context.save_options
            if allocated_model_id not in _current_source_model_ids(
                state=context.state,
                source=source,
            ):
                return context.save_options
            replacement = SaveOption(
                save_kind=SaveKind.INVULNERABLE,
                target_number=descriptor.target_number,
                characteristic_target_number=descriptor.target_number,
                armor_penetration=0,
                source_rule_ids=(source.rule_ir.source_id,),
            )
            return (
                *tuple(
                    option
                    for option in context.save_options
                    if option.save_kind is not SaveKind.INVULNERABLE
                ),
                replacement,
            )

        return handler

    def _conditional_invulnerable_save_handler(
        self,
        source: _CatalogClauseSource,
        descriptor: CatalogConditionalInvulnerableSaveDescriptor,
    ) -> Callable[[SaveOptionModifierContext], tuple[SaveOption, ...]]:
        def handler(context: SaveOptionModifierContext) -> tuple[SaveOption, ...]:
            allocated_model_id = context.allocated_model_instance_id
            profile = context.weapon_profile
            if (
                allocated_model_id is None
                or profile is None
                or profile.range_profile.kind is not RangeProfileKind.DISTANCE
                or descriptor.attack_kind != "ranged"
                or not _source_applies_to_rules_unit(
                    source=source,
                    context_unit_id=context.target_unit_instance_id,
                    state=context.state,
                )
                or allocated_model_id
                not in _current_source_model_ids(state=context.state, source=source)
            ):
                return context.save_options
            replacement = SaveOption(
                save_kind=SaveKind.INVULNERABLE,
                target_number=descriptor.target_number,
                characteristic_target_number=descriptor.target_number,
                armor_penetration=0,
                source_rule_ids=(source.rule_ir.source_id,),
            )
            return (
                *tuple(
                    option
                    for option in context.save_options
                    if option.save_kind is not SaveKind.INVULNERABLE
                ),
                replacement,
            )

        return handler

    def _conditional_proximity_characteristic_handler(
        self,
        source: _CatalogClauseSource,
        descriptor: CatalogConditionalProximityEffectsDescriptor,
    ) -> Callable[[UnitCharacteristicModifierContext], int]:
        def handler(context: UnitCharacteristicModifierContext) -> int:
            if (
                context.characteristic is not descriptor.characteristic
                or not _source_applies_to_rules_unit(
                    source=source,
                    context_unit_id=context.unit_instance_id,
                    state=context.state,
                )
                or not _friendly_keyworded_unit_within(source=source, state=context.state)
            ):
                return context.current_value
            return descriptor.characteristic_value

        return handler

    def _conditional_proximity_hit_roll_handler(
        self,
        source: _CatalogClauseSource,
        descriptor: CatalogConditionalProximityEffectsDescriptor,
    ) -> Callable[[HitRollModifierContext], int]:
        def handler(context: HitRollModifierContext) -> int:
            if not _source_applies_to_rules_unit(
                source=source,
                context_unit_id=context.attacking_unit_instance_id,
                state=context.state,
            ) or not _friendly_keyworded_unit_within(source=source, state=context.state):
                return 0
            if descriptor.hit_roll_delta is None:
                raise GameLifecycleError(
                    "Catalog conditional proximity hit-roll descriptor is malformed."
                )
            return descriptor.hit_roll_delta

        return handler

    def _conditional_proximity_weapon_handler(
        self,
        source: _CatalogClauseSource,
        descriptor: CatalogConditionalProximityEffectsDescriptor,
    ) -> Callable[[WeaponProfileModifierContext], WeaponProfile]:
        def handler(context: WeaponProfileModifierContext) -> WeaponProfile:
            if (
                not _source_applies_to_rules_unit(
                    source=source,
                    context_unit_id=context.attacking_unit_instance_id,
                    state=context.state,
                )
                or context.attacker_model_instance_id
                not in _current_source_model_ids(state=context.state, source=source)
                or not _friendly_keyworded_unit_within(source=source, state=context.state)
            ):
                return context.weapon_profile
            profile = context.weapon_profile
            for characteristic, delta in descriptor.weapon_characteristic_deltas:
                profile = rule_ir_modified_weapon_profile(
                    parameters={
                        "characteristic": characteristic.value,
                        "delta": delta,
                    },
                    profile=profile,
                    source_id=source.rule_ir.source_id,
                )
            return profile

        return handler

    def _attack_reroll_permission_handler(
        self,
        source: _CatalogClauseSource,
        descriptor: CatalogPassiveHitRerollDescriptor,
    ) -> Callable[[AttackRerollPermissionContext], SourceBackedRerollPermissionContext | None]:
        def handler(
            context: AttackRerollPermissionContext,
        ) -> SourceBackedRerollPermissionContext | None:
            if (
                context.player_id != source.player_id
                or context.roll_type != "attack_sequence.hit"
                or context.timing_window != "attack_sequence.hit"
                or not _source_applies_to_rules_unit(
                    source=source,
                    context_unit_id=context.attacking_unit_instance_id,
                    state=context.state,
                )
            ):
                return None
            return SourceBackedRerollPermissionContext(
                permission=RerollPermission(
                    source_id=source.binding_id,
                    timing_window=context.timing_window,
                    owning_player_id=context.player_id,
                    eligible_roll_type=context.roll_type,
                    component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
                ),
                source_payload={
                    "catalog_record_id": source.record.record_id,
                    "source_rule_id": source.rule_ir.source_id,
                    "source_unit_instance_id": source.unit.unit_instance_id,
                    "conditional_hit_reroll": {
                        "reroll_unmodified_values": [descriptor.reroll_unmodified_value],
                        "full_reroll_if_target_within_objective_range": (
                            descriptor.full_reroll_if_target_within_objective_range
                        ),
                    },
                },
            )

        return handler

    def _movement_action_grant_movement_handler(
        self,
        source: _CatalogClauseSource,
        descriptor: CatalogMovementActionGrantDescriptor,
    ) -> Callable[[MovementBudgetModifierContext], float]:
        def handler(context: MovementBudgetModifierContext) -> float:
            if not _source_applies_to_rules_unit(
                source=source,
                context_unit_id=context.unit_instance_id,
                state=context.state,
            ):
                return context.current_movement_inches
            rules_unit = rules_unit_view_by_id(
                state=context.state, unit_instance_id=context.unit_instance_id
            )
            if context.model_instance_id not in {
                model.model_instance_id for model in rules_unit.alive_models()
            }:
                return context.current_movement_inches
            for effect in context.state.persisting_effects_for_unit(rules_unit.unit_instance_id):
                payload = effect.effect_payload
                if (
                    isinstance(payload, dict)
                    and payload.get("effect_kind") == "catalog_movement_action_grant"
                    and payload.get("source_rule_id") == source.rule_ir.source_id
                ):
                    value = payload.get("movement_characteristic")
                    if type(value) is not int or value != descriptor.movement_characteristic:
                        raise GameLifecycleError(
                            "Catalog movement action grant characteristic drifted."
                        )
                    return float(value)
            return context.current_movement_inches

        return handler

    def _movement_action_grant_handler(
        self,
        source: _CatalogClauseSource,
        descriptor: CatalogMovementActionGrantDescriptor,
    ) -> Callable[[AdvanceMoveContext], AdvanceMoveGrant | None]:
        def handler(context: AdvanceMoveContext) -> AdvanceMoveGrant | None:
            if (
                context.player_id != source.player_id
                or context.movement_phase_action != descriptor.movement_action
                or not _source_applies_to_rules_unit(
                    source=source,
                    context_unit_id=context.unit_instance_id,
                    state=context.state,
                )
            ):
                return None
            return AdvanceMoveGrant(
                hook_id=f"{source.binding_id}:movement-action-grant",
                source_id=source.rule_ir.source_id,
                label=source.record.definition.name,
                granted_ranged_weapon_keywords=(),
                automatic=False,
                replay_payload={
                    "consumer_id": "catalog-ir:movement-action-grant",
                    "catalog_record_id": source.record.record_id,
                    "source_rule_id": source.rule_ir.source_id,
                    "source_unit_instance_id": source.unit.unit_instance_id,
                    "rules_unit_instance_id": context.unit_instance_id,
                    "clause_id": source.clause.clause_id,
                },
                unit_effect_payload={
                    "effect_kind": "catalog_movement_action_grant",
                    "catalog_record_id": source.record.record_id,
                    "source_rule_id": source.rule_ir.source_id,
                    "source_unit_instance_id": source.unit.unit_instance_id,
                    "rules_unit_instance_id": context.unit_instance_id,
                    "clause_id": source.clause.clause_id,
                    "movement_characteristic": descriptor.movement_characteristic,
                    "charge_forbidden": descriptor.charge_forbidden,
                    "phase_end_mortal_wounds": {
                        "roll_expression": "D6",
                        "roll_count_scope": "each_model_in_this_unit_at_phase_end",
                        "success_value": descriptor.phase_end_roll_success_value,
                        "mortal_wounds_per_success": descriptor.mortal_wounds_per_success,
                    },
                },
                unit_effect_expiration="end_turn",
            )

        return handler

    def _conditional_attack_reroll_permission_handler(
        self,
        source: _CatalogClauseSource,
        descriptor: CatalogConditionalAttackRerollDescriptor,
    ) -> Callable[[AttackRerollPermissionContext], SourceBackedRerollPermissionContext | None]:
        def handler(
            context: AttackRerollPermissionContext,
        ) -> SourceBackedRerollPermissionContext | None:
            roll_type_by_context = {
                "attack_sequence.hit": "hit_roll",
                "attack_sequence.wound": "wound_roll",
            }
            descriptor_roll_type = roll_type_by_context.get(context.roll_type)
            if context.roll_type.startswith("random_characteristic.damage."):
                descriptor_roll_type = "damage_roll"
            if (
                context.player_id != source.player_id
                or context.source_phase.value != descriptor.phase
                or context.timing_window != context.roll_type
                or descriptor_roll_type not in descriptor.roll_types
                or not _source_applies_to_rules_unit(
                    source=source,
                    context_unit_id=context.attacking_unit_instance_id,
                    state=context.state,
                )
                or context.attacker_model_instance_id is None
                or context.attacker_model_instance_id
                not in _alive_rules_unit_model_ids(
                    state=context.state,
                    unit_instance_id=context.attacking_unit_instance_id,
                )
                or not _rules_unit_has_any_keyword(
                    rules_unit_view_by_id(
                        state=context.state,
                        unit_instance_id=context.target_unit_instance_id,
                    ),
                    descriptor.required_target_keywords,
                )
            ):
                return None
            return SourceBackedRerollPermissionContext(
                permission=RerollPermission(
                    source_id=f"{source.binding_id}:{descriptor_roll_type}",
                    timing_window=context.timing_window,
                    owning_player_id=context.player_id,
                    eligible_roll_type=context.roll_type,
                    component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
                ),
                source_payload={
                    "effect_kind": "catalog_conditional_attack_reroll",
                    "catalog_record_id": source.record.record_id,
                    "source_rule_id": source.rule_ir.source_id,
                    "source_unit_instance_id": source.unit.unit_instance_id,
                    "required_target_keywords": list(descriptor.required_target_keywords),
                    "roll_type": descriptor_roll_type,
                },
            )

        return handler

    def _failed_save_damage_replacement_handler(
        self,
        source: _CatalogClauseSource,
        descriptor: CatalogFirstFailedSaveDamageReplacementDescriptor,
    ) -> Callable[[FailedSaveDamageReplacementContext], FailedSaveDamageReplacement | None]:
        def handler(
            context: FailedSaveDamageReplacementContext,
        ) -> FailedSaveDamageReplacement | None:
            if not _source_applies_to_rules_unit(
                source=source,
                context_unit_id=context.target_unit_instance_id,
                state=context.state,
            ):
                return None
            return FailedSaveDamageReplacement(
                source_id=source.binding_id,
                source_unit_instance_id=source.unit.unit_instance_id,
                replacement_damage=descriptor.replacement_damage,
            )

        return handler

    def _weapon_characteristic_handler(
        self, source: _CatalogClauseSource
    ) -> Callable[[WeaponProfileModifierContext], WeaponProfile]:
        def handler(context: WeaponProfileModifierContext) -> WeaponProfile:
            if not _source_applies_to_rules_unit(
                source=source,
                context_unit_id=context.attacking_unit_instance_id,
                state=context.state,
            ):
                return context.weapon_profile
            if context.attacker_model_instance_id not in _current_source_model_ids(
                state=context.state, source=source
            ) or not _source_keyword_gate_applies(source):
                return context.weapon_profile
            return rule_ir_modified_weapon_profile(
                parameters=parameter_payload(source.clause.effects[0].parameters),
                profile=context.weapon_profile,
                source_id=source.rule_ir.source_id,
            )

        return handler

    def _charge_end_weapon_ability_handler(
        self, source: _CatalogClauseSource
    ) -> Callable[[WeaponProfileModifierContext], WeaponProfile]:
        def handler(context: WeaponProfileModifierContext) -> WeaponProfile:
            if (
                not _source_applies_to_rules_unit(
                    source=source,
                    context_unit_id=context.attacking_unit_instance_id,
                    state=context.state,
                )
                or not _source_currently_leading_rules_unit(
                    source=source,
                    context_unit_id=context.attacking_unit_instance_id,
                    state=context.state,
                )
                or not _source_keyword_gate_applies(source)
                or not _rules_unit_charged_this_turn(
                    state=context.state,
                    unit_instance_id=context.attacking_unit_instance_id,
                )
            ):
                return context.weapon_profile
            effect = source.clause.effects[0]
            if effect.kind is not RuleEffectKind.GRANT_WEAPON_ABILITY:
                raise GameLifecycleError("Catalog datasheet weapon grant effect is malformed.")
            parameters = parameter_payload(effect.parameters)
            if not rule_ir_weapon_selector_applies(
                parameters=parameters, profile=context.weapon_profile
            ):
                return context.weapon_profile
            return rule_ir_weapon_ability_granted_profile(
                parameters=parameters,
                profile=context.weapon_profile,
                source_id=source.rule_ir.source_id,
            )

        return handler

    def _wound_roll_handler(
        self, source: _CatalogClauseSource
    ) -> Callable[[WoundRollModifierContext], int]:
        def handler(context: WoundRollModifierContext) -> int:
            if not _source_applies_to_rules_unit(
                source=source,
                context_unit_id=context.attacking_unit_instance_id,
                state=context.state,
            ) or not _source_currently_leading_rules_unit(
                source=source,
                context_unit_id=context.attacking_unit_instance_id,
                state=context.state,
            ):
                return 0
            parameters = parameter_payload(source.clause.effects[0].parameters)
            delta = parameters.get("delta")
            if type(delta) is not int:
                raise GameLifecycleError("Catalog datasheet wound delta must be integer.")
            return delta

        return handler

    def _leading_unit_hit_roll_handler(
        self, source: _CatalogClauseSource
    ) -> Callable[[HitRollModifierContext], int]:
        def handler(context: HitRollModifierContext) -> int:
            if not _source_applies_to_rules_unit(
                source=source,
                context_unit_id=context.attacking_unit_instance_id,
                state=context.state,
            ) or not _source_currently_leading_rules_unit(
                source=source,
                context_unit_id=context.attacking_unit_instance_id,
                state=context.state,
            ):
                return 0
            parameters = parameter_payload(source.clause.effects[0].parameters)
            delta = parameters.get("delta")
            if type(delta) is not int:
                raise GameLifecycleError("Catalog datasheet hit delta must be integer.")
            return delta

        return handler

    def _granted_stealth_handler(self, context: HitRollModifierContext) -> int:
        return catalog_granted_stealth_hit_roll_modifier(context)

    def _stealth_handler(
        self, sources: tuple[_CatalogClauseSource, ...]
    ) -> Callable[[HitRollModifierContext], int]:
        def handler(context: HitRollModifierContext) -> int:
            if (
                context.target_unit_instance_id == context.attacking_unit_instance_id
                or context.weapon_profile.range_profile.kind is not RangeProfileKind.DISTANCE
            ):
                return 0
            target = rules_unit_view_by_id(
                state=context.state, unit_instance_id=context.target_unit_instance_id
            )
            for source in sources:
                if (
                    not _source_is_alive(context.state, source)
                    or target.owner_player_id != source.player_id
                    or not _rules_unit_has_required_aura_keyword(target, source.clause)
                ):
                    continue
                if _rules_units_within(
                    context.state,
                    source.unit.unit_instance_id,
                    target.unit_instance_id,
                    _clause_distance(source.clause),
                ):
                    return -1
            return 0

        return handler

    def _fight_activation_movement_handler(
        self, source: _CatalogClauseSource
    ) -> Callable[[FightActivationAbilityContext], FightActivationAbilityOption | None]:
        def handler(
            context: FightActivationAbilityContext,
        ) -> FightActivationAbilityOption | None:
            if context.player_id != source.player_id or not _source_applies_to_rules_unit(
                source=source,
                context_unit_id=context.unit_instance_id,
                state=context.state,
            ):
                return None
            parameters = parameter_payload(source.clause.effects[0].parameters)
            if (
                parameters.get("movement_mode") != "consolidate"
                or parameters.get("operation") != "set_maximum"
            ):
                raise GameLifecycleError(
                    "Catalog datasheet fight activation movement effect is malformed."
                )
            distance = _positive_float_parameter(parameters, "distance_inches")
            replaced_distance = _positive_float_parameter(parameters, "replaced_distance_inches")
            return FightActivationAbilityOption(
                hook_id=source.binding_id,
                source_id=source.rule_ir.source_id,
                ability_id=source.binding_id,
                enhancement_id=source.record.record_id,
                effect_kind=FIGHT_ACTIVATION_MOVEMENT_DISTANCE_EFFECT_KIND,
                pile_in_distance_inches=replaced_distance,
                consolidate_distance_inches=distance,
                replay_payload={
                    "consumer_id": CATALOG_IR_FIGHT_ACTIVATION_MOVEMENT_DISTANCE_CONSUMER_ID,
                    "catalog_record_id": source.record.record_id,
                    "source_rule_id": source.rule_ir.source_id,
                    "source_unit_instance_id": source.unit.unit_instance_id,
                    "rules_unit_instance_id": context.unit_instance_id,
                    "clause_id": source.clause.clause_id,
                    "movement_mode": "consolidate",
                    "distance_inches": distance,
                    "replaced_distance_inches": replaced_distance,
                    "activation_request_id": context.activation.request_id,
                    "activation_result_id": context.activation.result_id,
                },
            )

        return handler

    def _lone_operative_handler(
        self, sources: tuple[_CatalogClauseSource, ...]
    ) -> Callable[[ShootingTargetRestrictionContext], TargetRestriction | None]:
        def handler(context: ShootingTargetRestrictionContext) -> TargetRestriction | None:
            for source in sources:
                if not _source_applies_to_rules_unit(
                    source=source,
                    context_unit_id=context.target_unit_instance_id,
                    state=context.state,
                ) or not _friendly_keyworded_unit_within(source=source, state=context.state):
                    continue
                if _rules_units_within(
                    context.state,
                    context.attacking_unit_instance_id,
                    context.target_unit_instance_id,
                    12,
                    attacker_model_instance_id=context.attacker_model_instance_id,
                ):
                    return None
                return TargetRestriction(
                    hook_id=CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
                    source_id=CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
                    violation_code="conditional_lone_operative_range",
                    message=(
                        'Target has Lone Operative and the attacking model is not within 12".'
                    ),
                    replay_payload={
                        "consumer_id": CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
                        "catalog_record_id": source.record.record_id,
                        "source_rule_id": source.rule_ir.source_id,
                        "source_unit_instance_id": source.unit.unit_instance_id,
                        "target_unit_instance_id": context.target_unit_instance_id,
                    },
                )
            return None

        return handler

    def _fight_grant_handler(
        self, *, source: _CatalogClauseSource, effect: RuleEffectSpec, hook_id: str
    ) -> Callable[[FightUnitSelectedContext], FightUnitSelectedGrant | None]:
        def handler(context: FightUnitSelectedContext) -> FightUnitSelectedGrant | None:
            if context.player_id != source.player_id or not _source_applies_to_rules_unit(
                source=source, context_unit_id=context.unit_instance_id, state=context.state
            ):
                return None
            source_model_id = _alive_source_model_id(context.state, source)
            execution_context = RuleExecutionContext(
                game_id=context.state.game_id,
                player_id=source.player_id,
                battle_round=context.state.battle_round,
                phase=BattlePhaseKind.FIGHT,
                active_player_id=context.state.active_player_id,
                timing_window_id="selected_to_fight",
                source_unit_instance_id=context.unit_instance_id,
                source_model_instance_id=source_model_id,
                target_unit_instance_ids=(context.unit_instance_id,),
                source_keywords=tuple(
                    sorted((*source.unit.keywords, *source.unit.faction_keywords))
                ),
                trigger_payload={
                    "catalog_record_id": source.record.record_id,
                    "consumer_id": CATALOG_IR_FIGHT_SELECTED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
                    "activation_request_id": context.request_id,
                    "activation_result_id": context.result_id,
                },
                state=context.state,
                event_log=None,
                record_persisting_effects=False,
            )
            parameters = parameter_payload(effect.parameters)
            return FightUnitSelectedGrant(
                hook_id=hook_id,
                source_id=source.rule_ir.source_id,
                label=_required_string(parameters, "weapon_ability"),
                replay_payload={
                    "catalog_record_id": source.record.record_id,
                    "clause_id": source.clause.clause_id,
                    "rule_ir_hash": source.rule_ir.ir_hash(),
                },
                unit_effect_payload=generic_rule_effect_payload(
                    rule_ir=source.rule_ir,
                    clause=source.clause,
                    effect=effect,
                    context=execution_context,
                    target_unit_instance_ids=(context.unit_instance_id,),
                ),
                unit_effect_expiration="end_phase",
                decline_allowed=False,
            )

        return handler


def _source_characteristic(source: _CatalogClauseSource) -> Characteristic:
    return _source_characteristic_delta(source)[0]


def _source_characteristic_delta(source: _CatalogClauseSource) -> tuple[Characteristic, int]:
    parameters = parameter_payload(source.clause.effects[0].parameters)
    try:
        characteristic = Characteristic(_required_string(parameters, "characteristic"))
    except ValueError as exc:
        raise GameLifecycleError("Catalog datasheet characteristic is invalid.") from exc
    delta = parameters.get("delta")
    if type(delta) is not int:
        raise GameLifecycleError("Catalog datasheet characteristic delta must be integer.")
    return characteristic, delta


def _source_keyword_gate_applies(source: _CatalogClauseSource) -> bool:
    required = {
        _required_string(parameter_payload(condition.parameters), "required_keyword")
        for condition in source.clause.conditions
        if condition.kind is RuleConditionKind.KEYWORD_GATE
    }
    keywords = {*source.unit.keywords, *source.unit.faction_keywords}
    return required.issubset(keywords)


def _source_applies_to_rules_unit(
    *, source: _CatalogClauseSource, context_unit_id: str, state: object
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog datasheet runtime requires GameState.")
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=context_unit_id)
    return (
        source.unit.unit_instance_id in rules_unit.component_unit_instance_ids
        and _source_is_alive(state, source)
    )


def _source_currently_leading_rules_unit(
    *, source: _CatalogClauseSource, context_unit_id: str, state: object
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog datasheet leading query requires GameState.")
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=context_unit_id)
    if not rules_unit.is_attached_rules_unit:
        return False
    return any(
        component.unit.unit_instance_id == source.unit.unit_instance_id
        and component.role in {"leader", "support"}
        for component in rules_unit.components
    )


def _rules_unit_charged_this_turn(*, state: object, unit_instance_id: str) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog datasheet charge query requires GameState.")
    for effect in state.persisting_effects_for_unit(unit_instance_id):
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") == CHARGE_FIGHTS_FIRST_EFFECT_KIND:
            return True
    return False


def _source_is_alive(state: object, source: _CatalogClauseSource) -> bool:
    return bool(_current_source_model_ids(state=state, source=source))


def _alive_source_model_id(state: object, source: _CatalogClauseSource) -> str:
    model_ids = _current_source_model_ids(state=state, source=source)
    if not model_ids:
        raise GameLifecycleError("Catalog datasheet source model is not placed and alive.")
    return model_ids[0]


def _current_source_model_ids(*, state: object, source: _CatalogClauseSource) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog datasheet source query requires GameState.")
    current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
        state=state,
        unit=source.unit,
    )
    if source.record.source_kind is not AbilitySourceKind.WARGEAR:
        return current_model_ids
    return catalog_rule_record_current_wargear_bearer_model_ids(
        record=source.record,
        unit=source.unit,
        current_model_instance_ids=current_model_ids,
    )


def _alive_rules_unit_model_ids(*, state: object, unit_instance_id: str) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog datasheet rules-unit query requires GameState.")
    return tuple(
        sorted(
            model.model_instance_id
            for model in rules_unit_view_by_id(
                state=state,
                unit_instance_id=unit_instance_id,
            ).alive_models()
        )
    )


def _static_source_model_ids(source: _CatalogClauseSource) -> tuple[str, ...]:
    model_ids = source.unit.own_model_ids()
    if source.record.source_kind is not AbilitySourceKind.WARGEAR:
        return model_ids
    return catalog_rule_record_current_wargear_bearer_model_ids(
        record=source.record,
        unit=source.unit,
        current_model_instance_ids=model_ids,
    )


def _catalog_fight_on_death_source(
    *,
    source: _CatalogClauseSource,
    descriptor: CatalogFightOnDeathDescriptor,
    model_instance_id: str,
) -> DestructionReactionSource:
    return DestructionReactionSource(
        source_id=(
            f"{source.rule_ir.source_id}:{source.clause.clause_id}:"
            f"{model_instance_id}:fight-on-death"
        ),
        reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
        source_rule_id=source.rule_ir.source_id,
        payload={
            "catalog_record_id": source.record.record_id,
            "clause_id": source.clause.clause_id,
            "consumer_id": CATALOG_IR_FIGHT_ON_DEATH_SOURCE_CONSUMER_ID,
            "rule_ir_hash": source.rule_ir.ir_hash(),
            "trigger_roll_threshold": descriptor.trigger_roll_threshold,
            "trigger_roll_type": descriptor.trigger_roll_type,
            "requires_destroyed_by_melee_attack": (descriptor.requires_destroyed_by_melee_attack),
            "requires_not_fought_this_phase": descriptor.requires_not_fought_this_phase,
            "unit_instance_id": source.unit.unit_instance_id,
            "model_instance_id": model_instance_id,
        },
        optional=True,
    )


def _record_destruction_reaction_source(
    *,
    state: object,
    model_instance_id: str,
    source: DestructionReactionSource,
) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog destruction-reaction registration requires GameState.")
    existing_sources = state.destruction_reaction_sources_for_model(
        model_instance_id=model_instance_id
    )
    for existing_source in existing_sources:
        if existing_source.source_id != source.source_id:
            continue
        if existing_source != source:
            raise GameLifecycleError(
                "Catalog destruction-reaction source conflicts with existing state."
            )
        return
    state.record_model_destruction_reaction_sources(
        model_instance_id=model_instance_id,
        sources=(*existing_sources, source),
    )


def _friendly_keyworded_unit_within(*, source: _CatalogClauseSource, state: object) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog conditional ability requires GameState.")
    distance_condition = next(
        condition
        for condition in source.clause.conditions
        if condition.kind is RuleConditionKind.DISTANCE_PREDICATE
    )
    parameters = parameter_payload(distance_condition.parameters)
    required = parameters.get("required_keyword_sequence")
    if not isinstance(required, tuple) or not all(type(value) is str for value in required):
        raise GameLifecycleError("Catalog conditional ability keyword sequence is malformed.")
    object_kind = parameters.get("object_kind")
    if type(object_kind) is not str:
        raise GameLifecycleError("Catalog conditional ability object kind is unsupported.")
    proximity_query = {
        "model": rules_unit_within_friendly_keyworded_models,
        "unit": rules_unit_within_friendly_keyworded_units,
    }.get(object_kind)
    if proximity_query is None:
        raise GameLifecycleError("Catalog conditional ability object kind is unsupported.")
    return proximity_query(
        state=state,
        source_unit_instance_id=source.unit.unit_instance_id,
        required_keyword_sequence=required,
        max_range_inches=_clause_distance(source.clause),
    )


def _rules_unit_has_required_aura_keyword(view: RulesUnitView, clause: RuleClause) -> bool:
    required = {
        _required_string(parameter_payload(condition.parameters), "required_keyword")
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.KEYWORD_GATE
    }
    keywords = {*view.keywords, *view.faction_keywords}
    return required.issubset(keywords)


def _rules_unit_has_any_keyword(view: RulesUnitView, required_keywords: tuple[str, ...]) -> bool:
    keywords = frozenset((*view.keywords, *view.faction_keywords))
    return any(keyword in keywords for keyword in required_keywords)


def _clause_distance(clause: RuleClause) -> float:
    condition = next(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.DISTANCE_PREDICATE
    )
    value = parameter_payload(condition.parameters).get("distance_inches")
    if not isinstance(value, int | float) or type(value) is bool or value <= 0:
        raise GameLifecycleError("Catalog datasheet distance must be positive numeric.")
    return float(value)


def _rules_units_within(
    state: object,
    first_unit_id: str,
    second_unit_id: str,
    distance: float,
    *,
    attacker_model_instance_id: str | None = None,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState or state.battlefield_state is None:
        raise GameLifecycleError("Catalog datasheet range query requires battlefield state.")
    return target_within_shooting_selection_range(
        scenario=BattlefieldScenario(
            armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
        ),
        attacking_unit_instance_id=first_unit_id,
        attacker_model_instance_id=attacker_model_instance_id,
        target_unit_instance_id=second_unit_id,
        max_range_inches=distance,
    )


def _required_string(parameters: Mapping[str, object], key: str) -> str:
    value = parameters.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Catalog datasheet {key} must be a non-empty string.")
    return value


def _positive_float_parameter(parameters: Mapping[str, object], key: str) -> float:
    value = parameters.get(key)
    if type(value) is int:
        numeric = float(value)
    elif type(value) is float:
        numeric = value
    else:
        raise GameLifecycleError(f"Catalog datasheet {key} must be positive numeric.")
    if numeric <= 0:
        raise GameLifecycleError(f"Catalog datasheet {key} must be positive numeric.")
    return numeric


def _validate_indexes(value: object) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Catalog datasheet runtime indexes must be a mapping.")
    indexes: dict[str, AbilityCatalogIndex] = {}
    for player_id, index in cast(Mapping[object, object], value).items():
        if type(player_id) is not str or type(index) is not AbilityCatalogIndex:
            raise GameLifecycleError("Catalog datasheet runtime index entry is invalid.")
        indexes[player_id] = index
    return MappingProxyType(indexes)


def _validate_armies(value: object) -> tuple[ArmyDefinition, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Catalog datasheet runtime requires ArmyDefinition tuple.")
    armies = cast(tuple[object, ...], value)
    if not all(type(army) is ArmyDefinition for army in armies):
        raise GameLifecycleError("Catalog datasheet runtime requires ArmyDefinition tuple.")
    return cast(tuple[ArmyDefinition, ...], armies)
