from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityHandlerBinding,
    AbilityHandlerRegistry,
    default_ability_handler_registry,
)
from warhammer40k_core.engine.ability_catalog import build_player_ability_index
from warhammer40k_core.engine.advance_eligibility_hooks import (
    AdvanceEligibilityHookBinding,
    AdvanceEligibilityHookRegistry,
)
from warhammer40k_core.engine.advance_hooks import AdvanceMoveHookBinding, AdvanceMoveHookRegistry
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_formation_hooks import (
    BattleFormationHookBinding,
    BattleFormationHookRegistry,
)
from warhammer40k_core.engine.battle_round_hooks import (
    BattleRoundStartHookBinding,
    BattleRoundStartHookRegistry,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockHookBinding,
    BattleShockHookRegistry,
)
from warhammer40k_core.engine.charge_declaration_hooks import (
    ChargeDeclarationHookBinding,
    ChargeDeclarationHookRegistry,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    CommandPhaseStartHookBinding,
    CommandPhaseStartHookRegistry,
)
from warhammer40k_core.engine.enhancement_effects import (
    EnhancementEffectBinding,
    EnhancementEffectRegistry,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.faction_content.activation import RuntimeContentActivation
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEventHandlerBinding,
    RuntimeContentEventHandlerRegistry,
    RuntimeContentEventIndex,
    RuntimeContentEventSubscription,
)
from warhammer40k_core.engine.faction_content.stratagem_handlers import (
    StratagemHandlerBinding,
    StratagemHandlerRegistry,
)
from warhammer40k_core.engine.faction_rule_execution import (
    FactionRuleExecutionRegistry,
    FactionRuleNamedHandler,
)
from warhammer40k_core.engine.fall_back_hooks import (
    FallBackEligibilityHookBinding,
    FallBackEligibilityHookRegistry,
)
from warhammer40k_core.engine.fight_activation_abilities import (
    FightActivationAbilityHookBinding,
    FightActivationAbilityHookRegistry,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedGrantBinding,
    FightUnitSelectedGrantRegistry,
)
from warhammer40k_core.engine.movement_end_surge_hooks import (
    MovementEndSurgeHookBinding,
    MovementEndSurgeHookRegistry,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionRegistry,
    RuleRuntimeBinding,
)
from warhammer40k_core.engine.runtime_modifiers import (
    ChargeRollModifierBinding,
    HitRollModifierBinding,
    MovementBudgetModifierBinding,
    ObjectiveControlModifierBinding,
    RuntimeModifierRegistry,
    SaveOptionModifierBinding,
    UnitCharacteristicModifierBinding,
    WeaponProfileModifierBinding,
)
from warhammer40k_core.engine.shooting_end_surge_hooks import (
    ShootingEndSurgeHookBinding,
    ShootingEndSurgeHookRegistry,
)
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    ShootingUnitSelectedGrantBinding,
    ShootingUnitSelectedGrantRegistry,
    ShootingUnitSelectedHookBinding,
    ShootingUnitSelectedHookRegistry,
)
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlHookBinding,
    PhaseEndObjectiveControlHookRegistry,
)
from warhammer40k_core.engine.stratagem_catalog import build_player_stratagem_index
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex, StratagemCatalogRecord
from warhammer40k_core.engine.target_restriction_hooks import (
    ChargeTargetRestrictionHookBinding,
    ChargeTargetRestrictionHookRegistry,
    ShootingTargetRestrictionHookBinding,
    ShootingTargetRestrictionHookRegistry,
)
from warhammer40k_core.engine.unit_destroyed_hooks import (
    UnitDestroyedHookBinding,
    UnitDestroyedHookRegistry,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionRecord,
)


class RuntimeContentBundleSummaryPayload(TypedDict):
    activation: dict[str, JsonValue]
    selected_module_paths: list[str]
    source_package_ids: list[str]
    source_package_hashes: list[str]
    contribution_ids: list[str]
    ability_index_record_ids_by_player_id: dict[str, list[str]]
    stratagem_index_record_ids_by_player_id: dict[str, list[str]]
    ability_handler_ids: list[str]
    stratagem_handler_ids: list[str]
    rule_runtime_binding_ids: list[str]
    event_subscriptions: list[dict[str, JsonValue]]
    battle_formation_hook_ids: list[str]
    battle_round_start_hook_ids: list[str]
    command_phase_start_hook_ids: list[str]
    unit_destroyed_hook_ids: list[str]
    battle_shock_hook_ids: list[str]
    advance_eligibility_hook_ids: list[str]
    advance_move_hook_ids: list[str]
    fall_back_hook_ids: list[str]
    movement_end_surge_hook_ids: list[str]
    charge_declaration_hook_ids: list[str]
    shooting_target_restriction_hook_ids: list[str]
    charge_target_restriction_hook_ids: list[str]
    shooting_unit_selected_hook_ids: list[str]
    shooting_unit_selected_grant_hook_ids: list[str]
    shooting_end_surge_hook_ids: list[str]
    enhancement_effect_binding_ids: list[str]
    fight_activation_ability_hook_ids: list[str]
    fight_unit_selected_grant_hook_ids: list[str]
    phase_end_objective_control_hook_ids: list[str]
    unit_characteristic_modifier_ids: list[str]
    hit_roll_modifier_ids: list[str]
    save_option_modifier_ids: list[str]
    movement_budget_modifier_ids: list[str]
    objective_control_modifier_ids: list[str]
    charge_roll_modifier_ids: list[str]
    weapon_profile_modifier_ids: list[str]
    faction_execution_record_ids: list[str]
    selected_execution_record_ids: list[str]
    bundle_summary_hash: str


DEFAULT_RUNTIME_CONTENT_CONTRIBUTION_ID = "runtime-content:module-default"


def _empty_named_handlers() -> Mapping[str, FactionRuleNamedHandler]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class RuntimeContentContribution:
    contribution_id: str = DEFAULT_RUNTIME_CONTENT_CONTRIBUTION_ID
    ability_records: tuple[AbilityCatalogRecord, ...] = ()
    stratagem_records: tuple[StratagemCatalogRecord, ...] = ()
    ability_handler_bindings: tuple[AbilityHandlerBinding, ...] = ()
    stratagem_handler_bindings: tuple[StratagemHandlerBinding, ...] = ()
    rule_runtime_bindings: tuple[RuleRuntimeBinding, ...] = ()
    event_subscriptions: tuple[RuntimeContentEventSubscription, ...] = ()
    event_handler_bindings: tuple[RuntimeContentEventHandlerBinding, ...] = ()
    battle_formation_hook_bindings: tuple[BattleFormationHookBinding, ...] = ()
    battle_round_start_hook_bindings: tuple[BattleRoundStartHookBinding, ...] = ()
    command_phase_start_hook_bindings: tuple[CommandPhaseStartHookBinding, ...] = ()
    unit_destroyed_hook_bindings: tuple[UnitDestroyedHookBinding, ...] = ()
    battle_shock_hook_bindings: tuple[BattleShockHookBinding, ...] = ()
    advance_eligibility_hook_bindings: tuple[AdvanceEligibilityHookBinding, ...] = ()
    advance_move_hook_bindings: tuple[AdvanceMoveHookBinding, ...] = ()
    fall_back_hook_bindings: tuple[FallBackEligibilityHookBinding, ...] = ()
    movement_end_surge_hook_bindings: tuple[MovementEndSurgeHookBinding, ...] = ()
    charge_declaration_hook_bindings: tuple[ChargeDeclarationHookBinding, ...] = ()
    shooting_target_restriction_hook_bindings: tuple[
        ShootingTargetRestrictionHookBinding,
        ...,
    ] = ()
    charge_target_restriction_hook_bindings: tuple[
        ChargeTargetRestrictionHookBinding,
        ...,
    ] = ()
    shooting_unit_selected_hook_bindings: tuple[ShootingUnitSelectedHookBinding, ...] = ()
    shooting_unit_selected_grant_hook_bindings: tuple[
        ShootingUnitSelectedGrantBinding,
        ...,
    ] = ()
    shooting_end_surge_hook_bindings: tuple[ShootingEndSurgeHookBinding, ...] = ()
    enhancement_effect_bindings: tuple[EnhancementEffectBinding, ...] = ()
    fight_activation_ability_hook_bindings: tuple[FightActivationAbilityHookBinding, ...] = ()
    fight_unit_selected_grant_hook_bindings: tuple[FightUnitSelectedGrantBinding, ...] = ()
    phase_end_objective_control_hook_bindings: tuple[PhaseEndObjectiveControlHookBinding, ...] = ()
    unit_characteristic_modifier_bindings: tuple[UnitCharacteristicModifierBinding, ...] = ()
    hit_roll_modifier_bindings: tuple[HitRollModifierBinding, ...] = ()
    save_option_modifier_bindings: tuple[SaveOptionModifierBinding, ...] = ()
    movement_budget_modifier_bindings: tuple[MovementBudgetModifierBinding, ...] = ()
    objective_control_modifier_bindings: tuple[ObjectiveControlModifierBinding, ...] = ()
    charge_roll_modifier_bindings: tuple[ChargeRollModifierBinding, ...] = ()
    weapon_profile_modifier_bindings: tuple[WeaponProfileModifierBinding, ...] = ()
    faction_named_handlers: Mapping[str, FactionRuleNamedHandler] = field(
        default_factory=_empty_named_handlers
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "contribution_id",
            _validate_identifier("contribution_id", self.contribution_id),
        )
        object.__setattr__(
            self,
            "ability_records",
            _validate_tuple(
                "RuntimeContentContribution ability_records",
                self.ability_records,
                AbilityCatalogRecord,
            ),
        )
        object.__setattr__(
            self,
            "stratagem_records",
            _validate_tuple(
                "RuntimeContentContribution stratagem_records",
                self.stratagem_records,
                StratagemCatalogRecord,
            ),
        )
        object.__setattr__(
            self,
            "ability_handler_bindings",
            _validate_tuple(
                "RuntimeContentContribution ability_handler_bindings",
                self.ability_handler_bindings,
                AbilityHandlerBinding,
            ),
        )
        object.__setattr__(
            self,
            "stratagem_handler_bindings",
            _validate_tuple(
                "RuntimeContentContribution stratagem_handler_bindings",
                self.stratagem_handler_bindings,
                StratagemHandlerBinding,
            ),
        )
        object.__setattr__(
            self,
            "rule_runtime_bindings",
            _validate_tuple(
                "RuntimeContentContribution rule_runtime_bindings",
                self.rule_runtime_bindings,
                RuleRuntimeBinding,
            ),
        )
        object.__setattr__(
            self,
            "event_subscriptions",
            _validate_tuple(
                "RuntimeContentContribution event_subscriptions",
                self.event_subscriptions,
                RuntimeContentEventSubscription,
            ),
        )
        object.__setattr__(
            self,
            "event_handler_bindings",
            _validate_tuple(
                "RuntimeContentContribution event_handler_bindings",
                self.event_handler_bindings,
                RuntimeContentEventHandlerBinding,
            ),
        )
        object.__setattr__(
            self,
            "battle_formation_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution battle_formation_hook_bindings",
                self.battle_formation_hook_bindings,
                BattleFormationHookBinding,
            ),
        )
        object.__setattr__(
            self,
            "battle_round_start_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution battle_round_start_hook_bindings",
                self.battle_round_start_hook_bindings,
                BattleRoundStartHookBinding,
            ),
        )
        object.__setattr__(
            self,
            "command_phase_start_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution command_phase_start_hook_bindings",
                self.command_phase_start_hook_bindings,
                CommandPhaseStartHookBinding,
            ),
        )
        object.__setattr__(
            self,
            "battle_shock_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution battle_shock_hook_bindings",
                self.battle_shock_hook_bindings,
                BattleShockHookBinding,
            ),
        )
        object.__setattr__(
            self,
            "unit_destroyed_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution unit_destroyed_hook_bindings",
                self.unit_destroyed_hook_bindings,
                UnitDestroyedHookBinding,
            ),
        )
        object.__setattr__(
            self,
            "advance_eligibility_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution advance_eligibility_hook_bindings",
                self.advance_eligibility_hook_bindings,
                AdvanceEligibilityHookBinding,
            ),
        )
        object.__setattr__(
            self,
            "advance_move_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution advance_move_hook_bindings",
                self.advance_move_hook_bindings,
                AdvanceMoveHookBinding,
            ),
        )
        object.__setattr__(
            self,
            "fall_back_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution fall_back_hook_bindings",
                self.fall_back_hook_bindings,
                FallBackEligibilityHookBinding,
            ),
        )
        object.__setattr__(
            self,
            "movement_end_surge_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution movement_end_surge_hook_bindings",
                self.movement_end_surge_hook_bindings,
                MovementEndSurgeHookBinding,
            ),
        )
        object.__setattr__(
            self,
            "charge_declaration_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution charge_declaration_hook_bindings",
                self.charge_declaration_hook_bindings,
                ChargeDeclarationHookBinding,
            ),
        )
        object.__setattr__(
            self,
            "shooting_target_restriction_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution shooting_target_restriction_hook_bindings",
                self.shooting_target_restriction_hook_bindings,
                ShootingTargetRestrictionHookBinding,
            ),
        )
        object.__setattr__(
            self,
            "charge_target_restriction_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution charge_target_restriction_hook_bindings",
                self.charge_target_restriction_hook_bindings,
                ChargeTargetRestrictionHookBinding,
            ),
        )
        object.__setattr__(
            self,
            "shooting_end_surge_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution shooting_end_surge_hook_bindings",
                self.shooting_end_surge_hook_bindings,
                ShootingEndSurgeHookBinding,
            ),
        )
        object.__setattr__(
            self,
            "shooting_unit_selected_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution shooting_unit_selected_hook_bindings",
                self.shooting_unit_selected_hook_bindings,
                ShootingUnitSelectedHookBinding,
            ),
        )
        object.__setattr__(
            self,
            "shooting_unit_selected_grant_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution shooting_unit_selected_grant_hook_bindings",
                self.shooting_unit_selected_grant_hook_bindings,
                ShootingUnitSelectedGrantBinding,
            ),
        )
        object.__setattr__(
            self,
            "enhancement_effect_bindings",
            _validate_tuple(
                "RuntimeContentContribution enhancement_effect_bindings",
                self.enhancement_effect_bindings,
                EnhancementEffectBinding,
            ),
        )
        object.__setattr__(
            self,
            "fight_activation_ability_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution fight_activation_ability_hook_bindings",
                self.fight_activation_ability_hook_bindings,
                FightActivationAbilityHookBinding,
            ),
        )
        object.__setattr__(
            self,
            "fight_unit_selected_grant_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution fight_unit_selected_grant_hook_bindings",
                self.fight_unit_selected_grant_hook_bindings,
                FightUnitSelectedGrantBinding,
            ),
        )
        object.__setattr__(
            self,
            "phase_end_objective_control_hook_bindings",
            _validate_tuple(
                "RuntimeContentContribution phase_end_objective_control_hook_bindings",
                self.phase_end_objective_control_hook_bindings,
                PhaseEndObjectiveControlHookBinding,
            ),
        )
        object.__setattr__(
            self,
            "unit_characteristic_modifier_bindings",
            _validate_tuple(
                "RuntimeContentContribution unit_characteristic_modifier_bindings",
                self.unit_characteristic_modifier_bindings,
                UnitCharacteristicModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "hit_roll_modifier_bindings",
            _validate_tuple(
                "RuntimeContentContribution hit_roll_modifier_bindings",
                self.hit_roll_modifier_bindings,
                HitRollModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "save_option_modifier_bindings",
            _validate_tuple(
                "RuntimeContentContribution save_option_modifier_bindings",
                self.save_option_modifier_bindings,
                SaveOptionModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "movement_budget_modifier_bindings",
            _validate_tuple(
                "RuntimeContentContribution movement_budget_modifier_bindings",
                self.movement_budget_modifier_bindings,
                MovementBudgetModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "objective_control_modifier_bindings",
            _validate_tuple(
                "RuntimeContentContribution objective_control_modifier_bindings",
                self.objective_control_modifier_bindings,
                ObjectiveControlModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "charge_roll_modifier_bindings",
            _validate_tuple(
                "RuntimeContentContribution charge_roll_modifier_bindings",
                self.charge_roll_modifier_bindings,
                ChargeRollModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "weapon_profile_modifier_bindings",
            _validate_tuple(
                "RuntimeContentContribution weapon_profile_modifier_bindings",
                self.weapon_profile_modifier_bindings,
                WeaponProfileModifierBinding,
            ),
        )
        object.__setattr__(
            self,
            "faction_named_handlers",
            _validate_named_handlers(self.faction_named_handlers),
        )

    def with_contribution_id(self, contribution_id: str) -> RuntimeContentContribution:
        return RuntimeContentContribution(
            contribution_id=contribution_id,
            ability_records=self.ability_records,
            stratagem_records=self.stratagem_records,
            ability_handler_bindings=self.ability_handler_bindings,
            stratagem_handler_bindings=self.stratagem_handler_bindings,
            rule_runtime_bindings=self.rule_runtime_bindings,
            event_subscriptions=self.event_subscriptions,
            event_handler_bindings=self.event_handler_bindings,
            battle_formation_hook_bindings=self.battle_formation_hook_bindings,
            battle_round_start_hook_bindings=self.battle_round_start_hook_bindings,
            command_phase_start_hook_bindings=self.command_phase_start_hook_bindings,
            unit_destroyed_hook_bindings=self.unit_destroyed_hook_bindings,
            battle_shock_hook_bindings=self.battle_shock_hook_bindings,
            advance_eligibility_hook_bindings=self.advance_eligibility_hook_bindings,
            advance_move_hook_bindings=self.advance_move_hook_bindings,
            fall_back_hook_bindings=self.fall_back_hook_bindings,
            movement_end_surge_hook_bindings=self.movement_end_surge_hook_bindings,
            charge_declaration_hook_bindings=self.charge_declaration_hook_bindings,
            shooting_target_restriction_hook_bindings=(
                self.shooting_target_restriction_hook_bindings
            ),
            charge_target_restriction_hook_bindings=(self.charge_target_restriction_hook_bindings),
            shooting_unit_selected_hook_bindings=self.shooting_unit_selected_hook_bindings,
            shooting_unit_selected_grant_hook_bindings=(
                self.shooting_unit_selected_grant_hook_bindings
            ),
            shooting_end_surge_hook_bindings=self.shooting_end_surge_hook_bindings,
            enhancement_effect_bindings=self.enhancement_effect_bindings,
            fight_activation_ability_hook_bindings=self.fight_activation_ability_hook_bindings,
            fight_unit_selected_grant_hook_bindings=(self.fight_unit_selected_grant_hook_bindings),
            phase_end_objective_control_hook_bindings=(
                self.phase_end_objective_control_hook_bindings
            ),
            unit_characteristic_modifier_bindings=self.unit_characteristic_modifier_bindings,
            hit_roll_modifier_bindings=self.hit_roll_modifier_bindings,
            save_option_modifier_bindings=self.save_option_modifier_bindings,
            movement_budget_modifier_bindings=self.movement_budget_modifier_bindings,
            objective_control_modifier_bindings=self.objective_control_modifier_bindings,
            charge_roll_modifier_bindings=self.charge_roll_modifier_bindings,
            weapon_profile_modifier_bindings=self.weapon_profile_modifier_bindings,
            faction_named_handlers=self.faction_named_handlers,
        )


def combine_runtime_content_contributions(
    *,
    contribution_id: str,
    contributions: tuple[RuntimeContentContribution, ...],
) -> RuntimeContentContribution:
    validated_contributions = _validate_contributions(contributions)
    return RuntimeContentContribution(
        contribution_id=contribution_id,
        ability_records=_combine_unique_values(
            "ability record",
            tuple(
                record
                for contribution in validated_contributions
                for record in contribution.ability_records
            ),
            lambda record: record.record_id,
        ),
        stratagem_records=_combine_unique_values(
            "Stratagem record",
            tuple(
                record
                for contribution in validated_contributions
                for record in contribution.stratagem_records
            ),
            lambda record: record.record_id,
        ),
        ability_handler_bindings=_combine_unique_values(
            "ability handler binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.ability_handler_bindings
            ),
            lambda binding: binding.handler_id,
        ),
        stratagem_handler_bindings=_combine_unique_values(
            "Stratagem handler binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.stratagem_handler_bindings
            ),
            lambda binding: binding.handler_id,
        ),
        rule_runtime_bindings=_combine_unique_values(
            "RuleIR binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.rule_runtime_bindings
            ),
            lambda binding: binding.binding_id,
        ),
        event_subscriptions=_combine_unique_values(
            "event subscription",
            tuple(
                subscription
                for contribution in validated_contributions
                for subscription in contribution.event_subscriptions
            ),
            lambda subscription: subscription.subscription_id,
        ),
        event_handler_bindings=_combine_unique_values(
            "event handler binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.event_handler_bindings
            ),
            lambda binding: binding.handler_id,
        ),
        battle_formation_hook_bindings=_combine_unique_values(
            "battle formation hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.battle_formation_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        battle_round_start_hook_bindings=_combine_unique_values(
            "battle-round start hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.battle_round_start_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        command_phase_start_hook_bindings=_combine_unique_values(
            "Command-phase start hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.command_phase_start_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        unit_destroyed_hook_bindings=_combine_unique_values(
            "Unit-destroyed hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.unit_destroyed_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        battle_shock_hook_bindings=_combine_unique_values(
            "Battle-shock hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.battle_shock_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        advance_eligibility_hook_bindings=_combine_unique_values(
            "Advance eligibility hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.advance_eligibility_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        advance_move_hook_bindings=_combine_unique_values(
            "Advance hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.advance_move_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        fall_back_hook_bindings=_combine_unique_values(
            "Fall Back eligibility hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.fall_back_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        movement_end_surge_hook_bindings=_combine_unique_values(
            "movement-end surge hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.movement_end_surge_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        charge_declaration_hook_bindings=_combine_unique_values(
            "charge declaration hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.charge_declaration_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        shooting_target_restriction_hook_bindings=_combine_unique_values(
            "shooting target restriction hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.shooting_target_restriction_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        charge_target_restriction_hook_bindings=_combine_unique_values(
            "charge target restriction hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.charge_target_restriction_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        shooting_end_surge_hook_bindings=_combine_unique_values(
            "shooting-end surge hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.shooting_end_surge_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        shooting_unit_selected_hook_bindings=_combine_unique_values(
            "shooting-unit-selected hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.shooting_unit_selected_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        shooting_unit_selected_grant_hook_bindings=_combine_unique_values(
            "shooting-unit-selected grant hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.shooting_unit_selected_grant_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        enhancement_effect_bindings=_combine_unique_values(
            "enhancement effect binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.enhancement_effect_bindings
            ),
            lambda binding: binding.effect_id,
        ),
        fight_activation_ability_hook_bindings=_combine_unique_values(
            "Fight activation ability hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.fight_activation_ability_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        fight_unit_selected_grant_hook_bindings=_combine_unique_values(
            "fight-unit-selected grant hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.fight_unit_selected_grant_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        phase_end_objective_control_hook_bindings=_combine_unique_values(
            "phase-end objective-control hook binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.phase_end_objective_control_hook_bindings
            ),
            lambda binding: binding.hook_id,
        ),
        unit_characteristic_modifier_bindings=_combine_unique_values(
            "unit characteristic modifier binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.unit_characteristic_modifier_bindings
            ),
            lambda binding: binding.modifier_id,
        ),
        hit_roll_modifier_bindings=_combine_unique_values(
            "Hit roll modifier binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.hit_roll_modifier_bindings
            ),
            lambda binding: binding.modifier_id,
        ),
        save_option_modifier_bindings=_combine_unique_values(
            "save option modifier binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.save_option_modifier_bindings
            ),
            lambda binding: binding.modifier_id,
        ),
        movement_budget_modifier_bindings=_combine_unique_values(
            "movement budget modifier binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.movement_budget_modifier_bindings
            ),
            lambda binding: binding.modifier_id,
        ),
        objective_control_modifier_bindings=_combine_unique_values(
            "Objective Control modifier binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.objective_control_modifier_bindings
            ),
            lambda binding: binding.modifier_id,
        ),
        charge_roll_modifier_bindings=_combine_unique_values(
            "charge roll modifier binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.charge_roll_modifier_bindings
            ),
            lambda binding: binding.modifier_id,
        ),
        weapon_profile_modifier_bindings=_combine_unique_values(
            "weapon profile modifier binding",
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.weapon_profile_modifier_bindings
            ),
            lambda binding: binding.modifier_id,
        ),
        faction_named_handlers=_merged_named_handlers(validated_contributions),
    )


@dataclass(frozen=True, slots=True)
class RuntimeContentBundle:
    activation: RuntimeContentActivation
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    stratagem_indexes_by_player_id: Mapping[str, StratagemCatalogIndex]
    ability_handler_registry: AbilityHandlerRegistry
    stratagem_handler_registry: StratagemHandlerRegistry
    rule_execution_registry: RuleExecutionRegistry
    faction_rule_execution_registry: FactionRuleExecutionRegistry
    event_index: RuntimeContentEventIndex
    battle_formation_hook_registry: BattleFormationHookRegistry
    battle_round_start_hook_registry: BattleRoundStartHookRegistry
    command_phase_start_hook_registry: CommandPhaseStartHookRegistry
    unit_destroyed_hook_registry: UnitDestroyedHookRegistry
    battle_shock_hook_registry: BattleShockHookRegistry
    advance_eligibility_hook_registry: AdvanceEligibilityHookRegistry
    advance_move_hook_registry: AdvanceMoveHookRegistry
    fall_back_hook_registry: FallBackEligibilityHookRegistry
    movement_end_surge_hook_registry: MovementEndSurgeHookRegistry
    charge_declaration_hook_registry: ChargeDeclarationHookRegistry
    shooting_target_restriction_hook_registry: ShootingTargetRestrictionHookRegistry
    charge_target_restriction_hook_registry: ChargeTargetRestrictionHookRegistry
    shooting_unit_selected_hook_registry: ShootingUnitSelectedHookRegistry
    shooting_unit_selected_grant_hook_registry: ShootingUnitSelectedGrantRegistry
    shooting_end_surge_hook_registry: ShootingEndSurgeHookRegistry
    enhancement_effect_registry: EnhancementEffectRegistry
    fight_activation_ability_hook_registry: FightActivationAbilityHookRegistry
    fight_unit_selected_grant_hook_registry: FightUnitSelectedGrantRegistry
    phase_end_objective_control_hook_registry: PhaseEndObjectiveControlHookRegistry
    runtime_modifier_registry: RuntimeModifierRegistry
    contribution_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.activation) is not RuntimeContentActivation:
            raise GameLifecycleError("RuntimeContentBundle requires RuntimeContentActivation.")
        object.__setattr__(
            self,
            "ability_indexes_by_player_id",
            _validate_index_mapping(
                "ability_indexes_by_player_id",
                self.ability_indexes_by_player_id,
                AbilityCatalogIndex,
            ),
        )
        object.__setattr__(
            self,
            "stratagem_indexes_by_player_id",
            _validate_index_mapping(
                "stratagem_indexes_by_player_id",
                self.stratagem_indexes_by_player_id,
                StratagemCatalogIndex,
            ),
        )
        if type(self.ability_handler_registry) is not AbilityHandlerRegistry:
            raise GameLifecycleError("RuntimeContentBundle requires AbilityHandlerRegistry.")
        if type(self.stratagem_handler_registry) is not StratagemHandlerRegistry:
            raise GameLifecycleError("RuntimeContentBundle requires StratagemHandlerRegistry.")
        if type(self.rule_execution_registry) is not RuleExecutionRegistry:
            raise GameLifecycleError("RuntimeContentBundle requires RuleExecutionRegistry.")
        if type(self.faction_rule_execution_registry) is not FactionRuleExecutionRegistry:
            raise GameLifecycleError("RuntimeContentBundle requires FactionRuleExecutionRegistry.")
        if type(self.event_index) is not RuntimeContentEventIndex:
            raise GameLifecycleError("RuntimeContentBundle requires RuntimeContentEventIndex.")
        if type(self.battle_formation_hook_registry) is not BattleFormationHookRegistry:
            raise GameLifecycleError("RuntimeContentBundle requires BattleFormationHookRegistry.")
        if type(self.battle_round_start_hook_registry) is not BattleRoundStartHookRegistry:
            raise GameLifecycleError("RuntimeContentBundle requires BattleRoundStartHookRegistry.")
        if type(self.command_phase_start_hook_registry) is not CommandPhaseStartHookRegistry:
            raise GameLifecycleError("RuntimeContentBundle requires CommandPhaseStartHookRegistry.")
        if type(self.unit_destroyed_hook_registry) is not UnitDestroyedHookRegistry:
            raise GameLifecycleError("RuntimeContentBundle requires UnitDestroyedHookRegistry.")
        if type(self.battle_shock_hook_registry) is not BattleShockHookRegistry:
            raise GameLifecycleError("RuntimeContentBundle requires BattleShockHookRegistry.")
        if type(self.advance_eligibility_hook_registry) is not AdvanceEligibilityHookRegistry:
            raise GameLifecycleError(
                "RuntimeContentBundle requires AdvanceEligibilityHookRegistry."
            )
        if type(self.advance_move_hook_registry) is not AdvanceMoveHookRegistry:
            raise GameLifecycleError("RuntimeContentBundle requires AdvanceMoveHookRegistry.")
        if type(self.fall_back_hook_registry) is not FallBackEligibilityHookRegistry:
            raise GameLifecycleError(
                "RuntimeContentBundle requires FallBackEligibilityHookRegistry."
            )
        if type(self.movement_end_surge_hook_registry) is not MovementEndSurgeHookRegistry:
            raise GameLifecycleError("RuntimeContentBundle requires MovementEndSurgeHookRegistry.")
        if type(self.charge_declaration_hook_registry) is not ChargeDeclarationHookRegistry:
            raise GameLifecycleError("RuntimeContentBundle requires ChargeDeclarationHookRegistry.")
        if (
            type(self.shooting_target_restriction_hook_registry)
            is not ShootingTargetRestrictionHookRegistry
        ):
            raise GameLifecycleError(
                "RuntimeContentBundle requires ShootingTargetRestrictionHookRegistry."
            )
        if (
            type(self.charge_target_restriction_hook_registry)
            is not ChargeTargetRestrictionHookRegistry
        ):
            raise GameLifecycleError(
                "RuntimeContentBundle requires ChargeTargetRestrictionHookRegistry."
            )
        if type(self.shooting_unit_selected_hook_registry) is not ShootingUnitSelectedHookRegistry:
            raise GameLifecycleError(
                "RuntimeContentBundle requires ShootingUnitSelectedHookRegistry."
            )
        if (
            type(self.shooting_unit_selected_grant_hook_registry)
            is not ShootingUnitSelectedGrantRegistry
        ):
            raise GameLifecycleError(
                "RuntimeContentBundle requires ShootingUnitSelectedGrantRegistry."
            )
        if type(self.shooting_end_surge_hook_registry) is not ShootingEndSurgeHookRegistry:
            raise GameLifecycleError("RuntimeContentBundle requires ShootingEndSurgeHookRegistry.")
        if type(self.enhancement_effect_registry) is not EnhancementEffectRegistry:
            raise GameLifecycleError("RuntimeContentBundle requires EnhancementEffectRegistry.")
        if (
            type(self.fight_activation_ability_hook_registry)
            is not FightActivationAbilityHookRegistry
        ):
            raise GameLifecycleError(
                "RuntimeContentBundle requires FightActivationAbilityHookRegistry."
            )
        if type(self.fight_unit_selected_grant_hook_registry) is not FightUnitSelectedGrantRegistry:
            raise GameLifecycleError(
                "RuntimeContentBundle requires FightUnitSelectedGrantRegistry."
            )
        if (
            type(self.phase_end_objective_control_hook_registry)
            is not PhaseEndObjectiveControlHookRegistry
        ):
            raise GameLifecycleError(
                "RuntimeContentBundle requires PhaseEndObjectiveControlHookRegistry."
            )
        if type(self.runtime_modifier_registry) is not RuntimeModifierRegistry:
            raise GameLifecycleError("RuntimeContentBundle requires RuntimeModifierRegistry.")
        object.__setattr__(
            self,
            "contribution_ids",
            _validate_identifier_tuple("contribution_ids", self.contribution_ids),
        )

    @classmethod
    def from_contributions(
        cls,
        *,
        activation: RuntimeContentActivation,
        armies: tuple[ArmyDefinition, ...],
        catalog: ArmyCatalog,
        contributions: tuple[RuntimeContentContribution, ...],
        base_ability_records: tuple[AbilityCatalogRecord, ...] = (),
        base_stratagem_records: tuple[StratagemCatalogRecord, ...] = (),
        base_ability_handler_registry: AbilityHandlerRegistry | None = None,
        base_stratagem_handler_registry: StratagemHandlerRegistry | None = None,
        base_rule_execution_registry: RuleExecutionRegistry | None = None,
        faction_execution_records: tuple[Phase17FExecutionRecord, ...] | None = None,
        include_unselected_faction_execution_records: bool = False,
    ) -> RuntimeContentBundle:
        if type(activation) is not RuntimeContentActivation:
            raise GameLifecycleError("Runtime content bundle requires activation.")
        if type(include_unselected_faction_execution_records) is not bool:
            raise GameLifecycleError("Runtime content faction execution scope flag is invalid.")
        validated_armies = _validate_armies(armies)
        if type(catalog) is not ArmyCatalog:
            raise GameLifecycleError("Runtime content bundle requires ArmyCatalog.")
        validated_contributions = _validate_contributions(contributions)
        ability_records = _merge_records(
            "ability_records",
            base_ability_records,
            tuple(
                record
                for contribution in validated_contributions
                for record in contribution.ability_records
            ),
            AbilityCatalogRecord,
        )
        stratagem_records = _merge_records(
            "stratagem_records",
            base_stratagem_records,
            tuple(
                record
                for contribution in validated_contributions
                for record in contribution.stratagem_records
            ),
            StratagemCatalogRecord,
        )
        ability_registry = _merged_ability_registry(
            base_ability_handler_registry,
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.ability_handler_bindings
            ),
        )
        stratagem_registry = _merged_stratagem_registry(
            base_stratagem_handler_registry,
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.stratagem_handler_bindings
            ),
        )
        rule_registry = _merged_rule_registry(
            base_rule_execution_registry,
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.rule_runtime_bindings
            ),
        )
        named_handlers = _merged_named_handlers(validated_contributions)
        available_records = (
            faction_execution_2026_27.execution_records()
            if faction_execution_records is None
            else faction_execution_records
        )
        records = (
            available_records
            if include_unselected_faction_execution_records
            else _selected_faction_execution_records(
                available_records=available_records,
                selected_execution_record_ids=activation.selected_execution_record_ids,
            )
        )
        faction_registry = FactionRuleExecutionRegistry.from_records(
            records,
            named_handlers=named_handlers,
        )
        contribution_ids = _validate_identifier_tuple(
            "contribution_ids",
            tuple(contribution.contribution_id for contribution in validated_contributions),
        )
        event_handler_registry = RuntimeContentEventHandlerRegistry.from_bindings(
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.event_handler_bindings
            )
        )
        event_index = RuntimeContentEventIndex.from_subscriptions(
            tuple(
                subscription
                for contribution in validated_contributions
                for subscription in contribution.event_subscriptions
            ),
            handler_registry=event_handler_registry,
        )
        battle_formation_hook_registry = BattleFormationHookRegistry.from_bindings(
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.battle_formation_hook_bindings
            )
        )
        battle_round_start_hook_registry = BattleRoundStartHookRegistry.from_bindings(
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.battle_round_start_hook_bindings
            )
        )
        command_phase_start_hook_registry = CommandPhaseStartHookRegistry.from_bindings(
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.command_phase_start_hook_bindings
            )
        )
        unit_destroyed_hook_registry = UnitDestroyedHookRegistry.from_bindings(
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.unit_destroyed_hook_bindings
            )
        )
        battle_shock_hook_registry = BattleShockHookRegistry.from_bindings(
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.battle_shock_hook_bindings
            )
        )
        advance_eligibility_hook_registry = AdvanceEligibilityHookRegistry.from_bindings(
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.advance_eligibility_hook_bindings
            )
        )
        advance_move_hook_registry = AdvanceMoveHookRegistry.from_bindings(
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.advance_move_hook_bindings
            )
        )
        fall_back_hook_registry = FallBackEligibilityHookRegistry.from_bindings(
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.fall_back_hook_bindings
            )
        )
        movement_end_surge_hook_registry = MovementEndSurgeHookRegistry.from_bindings(
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.movement_end_surge_hook_bindings
            )
        )
        charge_declaration_hook_registry = ChargeDeclarationHookRegistry.from_bindings(
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.charge_declaration_hook_bindings
            )
        )
        shooting_target_restriction_hook_registry = (
            ShootingTargetRestrictionHookRegistry.from_bindings(
                tuple(
                    binding
                    for contribution in validated_contributions
                    for binding in contribution.shooting_target_restriction_hook_bindings
                )
            )
        )
        charge_target_restriction_hook_registry = ChargeTargetRestrictionHookRegistry.from_bindings(
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.charge_target_restriction_hook_bindings
            )
        )
        shooting_end_surge_hook_registry = ShootingEndSurgeHookRegistry.from_bindings(
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.shooting_end_surge_hook_bindings
            )
        )
        shooting_unit_selected_hook_registry = ShootingUnitSelectedHookRegistry.from_bindings(
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.shooting_unit_selected_hook_bindings
            )
        )
        shooting_unit_selected_grant_hook_registry = (
            ShootingUnitSelectedGrantRegistry.from_bindings(
                tuple(
                    binding
                    for contribution in validated_contributions
                    for binding in contribution.shooting_unit_selected_grant_hook_bindings
                )
            )
        )
        enhancement_effect_registry = EnhancementEffectRegistry.from_bindings(
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.enhancement_effect_bindings
            )
        )
        fight_activation_ability_hook_registry = FightActivationAbilityHookRegistry.from_bindings(
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.fight_activation_ability_hook_bindings
            )
        )
        fight_unit_selected_grant_hook_registry = FightUnitSelectedGrantRegistry.from_bindings(
            tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.fight_unit_selected_grant_hook_bindings
            )
        )
        phase_end_objective_control_hook_registry = (
            PhaseEndObjectiveControlHookRegistry.from_bindings(
                tuple(
                    binding
                    for contribution in validated_contributions
                    for binding in contribution.phase_end_objective_control_hook_bindings
                )
            )
        )
        runtime_modifier_registry = RuntimeModifierRegistry.from_bindings(
            unit_characteristic_modifier_bindings=tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.unit_characteristic_modifier_bindings
            ),
            hit_roll_modifier_bindings=tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.hit_roll_modifier_bindings
            ),
            save_option_modifier_bindings=tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.save_option_modifier_bindings
            ),
            movement_budget_modifier_bindings=tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.movement_budget_modifier_bindings
            ),
            objective_control_modifier_bindings=tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.objective_control_modifier_bindings
            ),
            charge_roll_modifier_bindings=tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.charge_roll_modifier_bindings
            ),
            weapon_profile_modifier_bindings=tuple(
                binding
                for contribution in validated_contributions
                for binding in contribution.weapon_profile_modifier_bindings
            ),
        )
        return cls(
            activation=activation,
            ability_indexes_by_player_id=_ability_indexes_by_player_id(
                armies=validated_armies,
                catalog=catalog,
                records=ability_records,
            ),
            stratagem_indexes_by_player_id=_stratagem_indexes_by_player_id(
                armies=validated_armies,
                catalog=catalog,
                records=stratagem_records,
            ),
            ability_handler_registry=ability_registry,
            stratagem_handler_registry=stratagem_registry,
            rule_execution_registry=rule_registry,
            faction_rule_execution_registry=faction_registry,
            event_index=event_index,
            battle_formation_hook_registry=battle_formation_hook_registry,
            battle_round_start_hook_registry=battle_round_start_hook_registry,
            command_phase_start_hook_registry=command_phase_start_hook_registry,
            unit_destroyed_hook_registry=unit_destroyed_hook_registry,
            battle_shock_hook_registry=battle_shock_hook_registry,
            advance_eligibility_hook_registry=advance_eligibility_hook_registry,
            advance_move_hook_registry=advance_move_hook_registry,
            fall_back_hook_registry=fall_back_hook_registry,
            movement_end_surge_hook_registry=movement_end_surge_hook_registry,
            charge_declaration_hook_registry=charge_declaration_hook_registry,
            shooting_target_restriction_hook_registry=shooting_target_restriction_hook_registry,
            charge_target_restriction_hook_registry=charge_target_restriction_hook_registry,
            shooting_unit_selected_hook_registry=shooting_unit_selected_hook_registry,
            shooting_unit_selected_grant_hook_registry=(shooting_unit_selected_grant_hook_registry),
            shooting_end_surge_hook_registry=shooting_end_surge_hook_registry,
            enhancement_effect_registry=enhancement_effect_registry,
            fight_activation_ability_hook_registry=fight_activation_ability_hook_registry,
            fight_unit_selected_grant_hook_registry=fight_unit_selected_grant_hook_registry,
            phase_end_objective_control_hook_registry=(phase_end_objective_control_hook_registry),
            runtime_modifier_registry=runtime_modifier_registry,
            contribution_ids=contribution_ids,
        )

    def to_summary_payload(self) -> RuntimeContentBundleSummaryPayload:
        payload = {
            "activation": cast(
                dict[str, JsonValue], validate_json_value(self.activation.to_payload())
            ),
            "selected_module_paths": list(self.activation.selected_module_paths),
            "source_package_ids": list(self.activation.source_package_ids),
            "source_package_hashes": list(self.activation.source_package_hashes),
            "contribution_ids": list(self.contribution_ids),
            "ability_index_record_ids_by_player_id": {
                player_id: [record.record_id for record in index.all_records()]
                for player_id, index in self.ability_indexes_by_player_id.items()
            },
            "stratagem_index_record_ids_by_player_id": {
                player_id: [record.record_id for record in index.all_records()]
                for player_id, index in self.stratagem_indexes_by_player_id.items()
            },
            "ability_handler_ids": [
                binding.handler_id for binding in self.ability_handler_registry.all_bindings()
            ],
            "stratagem_handler_ids": [
                binding.handler_id for binding in self.stratagem_handler_registry.all_bindings()
            ],
            "rule_runtime_binding_ids": [
                binding.binding_id for binding in self.rule_execution_registry.all_bindings()
            ],
            "event_subscriptions": self.event_index.to_summary_payload(),
            "battle_formation_hook_ids": [
                binding.hook_id for binding in self.battle_formation_hook_registry.all_bindings()
            ],
            "battle_round_start_hook_ids": [
                binding.hook_id for binding in self.battle_round_start_hook_registry.all_bindings()
            ],
            "command_phase_start_hook_ids": [
                binding.hook_id for binding in self.command_phase_start_hook_registry.all_bindings()
            ],
            "unit_destroyed_hook_ids": [
                binding.hook_id for binding in self.unit_destroyed_hook_registry.all_bindings()
            ],
            "battle_shock_hook_ids": [
                binding.hook_id for binding in self.battle_shock_hook_registry.all_bindings()
            ],
            "advance_eligibility_hook_ids": [
                binding.hook_id for binding in self.advance_eligibility_hook_registry.all_bindings()
            ],
            "advance_move_hook_ids": [
                binding.hook_id for binding in self.advance_move_hook_registry.all_bindings()
            ],
            "fall_back_hook_ids": [
                binding.hook_id for binding in self.fall_back_hook_registry.all_bindings()
            ],
            "movement_end_surge_hook_ids": [
                binding.hook_id for binding in self.movement_end_surge_hook_registry.all_bindings()
            ],
            "charge_declaration_hook_ids": [
                binding.hook_id for binding in self.charge_declaration_hook_registry.all_bindings()
            ],
            "shooting_target_restriction_hook_ids": [
                binding.hook_id
                for binding in self.shooting_target_restriction_hook_registry.all_bindings()
            ],
            "charge_target_restriction_hook_ids": [
                binding.hook_id
                for binding in self.charge_target_restriction_hook_registry.all_bindings()
            ],
            "shooting_unit_selected_hook_ids": [
                binding.hook_id
                for binding in self.shooting_unit_selected_hook_registry.all_bindings()
            ],
            "shooting_unit_selected_grant_hook_ids": [
                binding.hook_id
                for binding in self.shooting_unit_selected_grant_hook_registry.all_bindings()
            ],
            "shooting_end_surge_hook_ids": [
                binding.hook_id for binding in self.shooting_end_surge_hook_registry.all_bindings()
            ],
            "enhancement_effect_binding_ids": [
                binding.effect_id for binding in self.enhancement_effect_registry.all_bindings()
            ],
            "fight_activation_ability_hook_ids": [
                binding.hook_id
                for binding in self.fight_activation_ability_hook_registry.all_bindings()
            ],
            "fight_unit_selected_grant_hook_ids": [
                binding.hook_id
                for binding in self.fight_unit_selected_grant_hook_registry.all_bindings()
            ],
            "phase_end_objective_control_hook_ids": [
                binding.hook_id
                for binding in self.phase_end_objective_control_hook_registry.all_bindings()
            ],
            "unit_characteristic_modifier_ids": [
                binding.modifier_id
                for binding in self.runtime_modifier_registry.all_unit_characteristic_bindings()
            ],
            "hit_roll_modifier_ids": [
                binding.modifier_id
                for binding in self.runtime_modifier_registry.all_hit_roll_bindings()
            ],
            "save_option_modifier_ids": [
                binding.modifier_id
                for binding in self.runtime_modifier_registry.all_save_option_bindings()
            ],
            "movement_budget_modifier_ids": [
                binding.modifier_id
                for binding in self.runtime_modifier_registry.all_movement_budget_bindings()
            ],
            "objective_control_modifier_ids": [
                binding.modifier_id
                for binding in self.runtime_modifier_registry.all_objective_control_bindings()
            ],
            "charge_roll_modifier_ids": [
                binding.modifier_id
                for binding in self.runtime_modifier_registry.all_charge_roll_bindings()
            ],
            "weapon_profile_modifier_ids": [
                binding.modifier_id
                for binding in self.runtime_modifier_registry.all_weapon_profile_bindings()
            ],
            "faction_execution_record_ids": [
                record.execution_id for record in self.faction_rule_execution_registry.all_records()
            ],
            "selected_execution_record_ids": list(self.activation.selected_execution_record_ids),
            "bundle_summary_hash": "",
        }
        payload["bundle_summary_hash"] = _summary_hash(
            cast(Mapping[str, JsonValue], validate_json_value(payload))
        )
        return cast(RuntimeContentBundleSummaryPayload, validate_json_value(payload))


def _validate_contributions(
    contributions: object,
) -> tuple[RuntimeContentContribution, ...]:
    if type(contributions) is not tuple:
        raise GameLifecycleError("Runtime content contributions must be a tuple.")
    validated: list[RuntimeContentContribution] = []
    for contribution in cast(tuple[object, ...], contributions):
        if type(contribution) is not RuntimeContentContribution:
            raise GameLifecycleError(
                "Runtime content contributions must contain RuntimeContentContribution values."
            )
        validated.append(contribution)
    return tuple(validated)


def _combine_unique_values[T](
    field_name: str,
    values: tuple[T, ...],
    identifier_for: Callable[[T], str],
) -> tuple[T, ...]:
    seen: set[str] = set()
    combined: list[T] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} id", identifier_for(value))
        if identifier in seen:
            raise GameLifecycleError(f"Runtime content {field_name} IDs must be unique.")
        seen.add(identifier)
        combined.append(value)
    return tuple(combined)


def _validate_armies(armies: object) -> tuple[ArmyDefinition, ...]:
    if type(armies) is not tuple:
        raise GameLifecycleError("Runtime content bundle armies must be a tuple.")
    validated: list[ArmyDefinition] = []
    seen: set[str] = set()
    for army in cast(tuple[object, ...], armies):
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError("Runtime content bundle armies must contain ArmyDefinition.")
        if army.player_id in seen:
            raise GameLifecycleError("Runtime content bundle player IDs must be unique.")
        seen.add(army.player_id)
        validated.append(army)
    return tuple(sorted(validated, key=lambda army: army.player_id))


def _ability_indexes_by_player_id(
    *,
    armies: tuple[ArmyDefinition, ...],
    catalog: ArmyCatalog,
    records: tuple[AbilityCatalogRecord, ...],
) -> Mapping[str, AbilityCatalogIndex]:
    return MappingProxyType(
        {
            army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
            for army in armies
        }
    )


def _stratagem_indexes_by_player_id(
    *,
    armies: tuple[ArmyDefinition, ...],
    catalog: ArmyCatalog,
    records: tuple[StratagemCatalogRecord, ...],
) -> Mapping[str, StratagemCatalogIndex]:
    return MappingProxyType(
        {
            army.player_id: build_player_stratagem_index(
                records,
                detachment_ids=army.detachment_selection.detachment_ids,
                stratagem_ids=_selected_stratagem_ids_for_army(
                    army=army,
                    catalog=catalog,
                ),
            )
            for army in armies
        }
    )


def _selected_stratagem_ids_for_army(
    *,
    army: ArmyDefinition,
    catalog: ArmyCatalog,
) -> tuple[str, ...]:
    selected: set[str] = set(army.detachment_selection.stratagem_ids)
    selected_detachment_ids = set(army.detachment_selection.detachment_ids)
    for detachment in catalog.detachments:
        if detachment.detachment_id in selected_detachment_ids:
            selected.update(detachment.stratagem_ids)
    return tuple(sorted(selected))


def _merged_ability_registry(
    base: AbilityHandlerRegistry | None,
    contribution_bindings: tuple[AbilityHandlerBinding, ...],
) -> AbilityHandlerRegistry:
    resolved_base = default_ability_handler_registry() if base is None else base
    if type(resolved_base) is not AbilityHandlerRegistry:
        raise GameLifecycleError("Runtime content base ability registry is invalid.")
    return AbilityHandlerRegistry.from_bindings(
        (*resolved_base.all_bindings(), *contribution_bindings)
    )


def _merged_stratagem_registry(
    base: StratagemHandlerRegistry | None,
    contribution_bindings: tuple[StratagemHandlerBinding, ...],
) -> StratagemHandlerRegistry:
    resolved_base = StratagemHandlerRegistry.empty() if base is None else base
    if type(resolved_base) is not StratagemHandlerRegistry:
        raise GameLifecycleError("Runtime content base Stratagem registry is invalid.")
    return StratagemHandlerRegistry.from_bindings(
        (*resolved_base.all_bindings(), *contribution_bindings)
    )


def _merged_rule_registry(
    base: RuleExecutionRegistry | None,
    contribution_bindings: tuple[RuleRuntimeBinding, ...],
) -> RuleExecutionRegistry:
    resolved_base = RuleExecutionRegistry.empty() if base is None else base
    if type(resolved_base) is not RuleExecutionRegistry:
        raise GameLifecycleError("Runtime content base rule registry is invalid.")
    return RuleExecutionRegistry.from_bindings(
        (*resolved_base.all_bindings(), *contribution_bindings)
    )


def _merged_named_handlers(
    contributions: tuple[RuntimeContentContribution, ...],
) -> Mapping[str, FactionRuleNamedHandler]:
    handlers: dict[str, FactionRuleNamedHandler] = {}
    for contribution in contributions:
        for handler_id, handler in contribution.faction_named_handlers.items():
            if handler_id in handlers:
                raise GameLifecycleError("Runtime content faction handler IDs must be unique.")
            handlers[handler_id] = handler
    return MappingProxyType(handlers)


def _selected_faction_execution_records(
    *,
    available_records: tuple[Phase17FExecutionRecord, ...],
    selected_execution_record_ids: tuple[str, ...],
) -> tuple[Phase17FExecutionRecord, ...]:
    selected_ids = set(
        _validate_identifier_tuple(
            "selected_execution_record_ids",
            selected_execution_record_ids,
        )
    )
    if not selected_ids:
        return ()
    records_by_id: dict[str, Phase17FExecutionRecord] = {}
    for record in _validate_tuple(
        "faction_execution_records",
        available_records,
        Phase17FExecutionRecord,
    ):
        if record.execution_id in records_by_id:
            raise GameLifecycleError("Runtime content faction execution record IDs must be unique.")
        records_by_id[record.execution_id] = record
    missing_ids = tuple(sorted(selected_ids.difference(records_by_id)))
    if missing_ids:
        raise GameLifecycleError(
            f"Runtime content selected unknown faction execution records: {', '.join(missing_ids)}."
        )
    return tuple(records_by_id[execution_id] for execution_id in sorted(selected_ids))


def _validate_named_handlers(value: object) -> Mapping[str, FactionRuleNamedHandler]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Runtime content named handlers must be a mapping.")
    validated: dict[str, FactionRuleNamedHandler] = {}
    for raw_handler_id, raw_handler in cast(Mapping[object, object], value).items():
        handler_id = _validate_identifier("faction handler id", raw_handler_id)
        if not callable(raw_handler):
            raise GameLifecycleError("Runtime content named handlers must be callable.")
        if handler_id in validated:
            raise GameLifecycleError("Runtime content named handler IDs must be unique.")
        validated[handler_id] = cast(FactionRuleNamedHandler, raw_handler)
    return MappingProxyType(validated)


def _validate_index_mapping[T](
    field_name: str,
    value: object,
    expected_type: type[T],
) -> Mapping[str, T]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError(f"Runtime content {field_name} must be a mapping.")
    validated: dict[str, T] = {}
    for raw_player_id, index in cast(Mapping[object, object], value).items():
        player_id = _validate_identifier("player_id", raw_player_id)
        if type(index) is not expected_type:
            raise GameLifecycleError(f"Runtime content {field_name} contains invalid index.")
        validated[player_id] = index
    return MappingProxyType(dict(sorted(validated.items())))


def _merge_records[T](
    field_name: str,
    base_records: object,
    contribution_records: tuple[T, ...],
    expected_type: type[T],
) -> tuple[T, ...]:
    return (
        *_validate_tuple(f"base {field_name}", base_records, expected_type),
        *_validate_tuple(f"contribution {field_name}", contribution_records, expected_type),
    )


def _validate_tuple[T](
    field_name: str,
    value: object,
    expected_type: type[T],
) -> tuple[T, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated: list[T] = []
    for item in cast(tuple[object, ...], value):
        if type(item) is not expected_type:
            raise GameLifecycleError(f"{field_name} contains invalid values.")
        validated.append(item)
    return tuple(validated)


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Runtime content {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Runtime content {field_name} must not be empty.")
    return stripped


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Runtime content {field_name} must be a tuple.")
    seen: set[str] = set()
    identifiers: list[str] = []
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"Runtime content {field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))


def _summary_hash(payload: Mapping[str, JsonValue]) -> str:
    serialized = canonical_json(validate_json_value(dict(payload)))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
