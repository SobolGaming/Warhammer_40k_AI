from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    WeaponKeyword,
    WeaponProfileError,
    weapon_keyword_from_token,
)
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.faction_content.bundle_validation import validate_identifier
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import WeaponProfileModifierContext
from warhammer40k_core.engine.tracked_targets import TrackedTargetOwnerScope, TrackedTargetRole
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleTargetKind,
    parameter_payload,
)

TRACKED_TARGET_WEAPON_GRANT_TEMPLATE_ID = "phase17c:tracked-target-weapon-ability-grant"


@dataclass(frozen=True, slots=True)
class CatalogTrackedTargetWeaponGrant:
    source_rule_id: str
    owner_scope: TrackedTargetOwnerScope
    role: TrackedTargetRole

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_rule_id",
            validate_identifier("source_rule_id", self.source_rule_id),
        )
        if type(self.owner_scope) is not TrackedTargetOwnerScope:
            raise GameLifecycleError(
                "Catalog weapon keyword grant owner scope must be TrackedTargetOwnerScope."
            )
        if type(self.role) is not TrackedTargetRole:
            raise GameLifecycleError("Catalog weapon keyword grant role must be TrackedTargetRole.")


@dataclass(frozen=True, slots=True)
class CatalogWeaponKeywordGrant:
    source_id: str
    keyword: WeaponKeyword
    weapon_scope: str
    ability: AbilityDescriptor | None = None
    tracked_target: CatalogTrackedTargetWeaponGrant | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", validate_identifier("source_id", self.source_id))
        object.__setattr__(self, "keyword", _weapon_keyword_from_value(self.keyword))
        object.__setattr__(self, "weapon_scope", _weapon_scope_from_token(self.weapon_scope))
        if self.ability is not None and type(self.ability) is not AbilityDescriptor:
            raise GameLifecycleError("Catalog weapon keyword grant ability must be a descriptor.")
        if self.tracked_target is not None and type(self.tracked_target) is not (
            CatalogTrackedTargetWeaponGrant
        ):
            raise GameLifecycleError("Catalog weapon keyword grant tracked target is invalid.")


@dataclass(frozen=True, slots=True)
class CatalogTrackedTargetWeaponGrantClauseDescriptor:
    keyword: WeaponKeyword
    weapon_scope: str
    owner_scope: TrackedTargetOwnerScope
    role: TrackedTargetRole


def clause_has_invalid_exact_tracked_target_weapon_grant_shape(clause: RuleClause) -> bool:
    return (
        clause.template_id == TRACKED_TARGET_WEAPON_GRANT_TEMPLATE_ID
        and tracked_target_weapon_grant_descriptor_for_clause(clause) is None
    )


def tracked_target_weapon_grant_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogTrackedTargetWeaponGrantClauseDescriptor | None:
    if (
        not clause.is_supported
        or clause.template_id != TRACKED_TARGET_WEAPON_GRANT_TEMPLATE_ID
        or clause.trigger is not None
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or clause.target.parameters
        or clause.duration is not None
        or len(clause.conditions) != 1
        or len(clause.effects) != 1
    ):
        return None
    condition = clause.conditions[0]
    condition_parameters = parameter_payload(condition.parameters)
    effect = clause.effects[0]
    effect_parameters = parameter_payload(effect.parameters)
    if (
        condition.kind is not RuleConditionKind.TARGET_CONSTRAINT
        or condition_parameters
        != {
            "gate_subject": "attack_target",
            "relationship": "attack_targets_tracked_target",
            "target_reference": "tracked_target",
            "tracked_target_owner": effect_parameters.get("tracked_target_owner"),
            "tracked_target_role": effect_parameters.get("tracked_target_role"),
        }
        or effect.kind is not RuleEffectKind.GRANT_WEAPON_ABILITY
        or set(effect_parameters)
        != {
            "target_reference",
            "tracked_target_owner",
            "tracked_target_role",
            "weapon_ability",
            "weapon_scope",
        }
        or effect_parameters.get("target_reference") != "tracked_target"
    ):
        return None
    owner = effect_parameters.get("tracked_target_owner")
    role = effect_parameters.get("tracked_target_role")
    scope = effect_parameters.get("weapon_scope")
    if owner not in {"this_model", "this_unit"} or role not in {"prey", "quarry"}:
        return None
    if scope not in {"all", "melee", "ranged"}:
        return None
    ability = effect_parameters.get("weapon_ability")
    if type(ability) is not str:
        return None
    try:
        keyword = weapon_keyword_from_token(ability)
    except WeaponProfileError:
        return None
    return CatalogTrackedTargetWeaponGrantClauseDescriptor(
        keyword=keyword,
        weapon_scope=str(scope),
        owner_scope=TrackedTargetOwnerScope(str(owner)),
        role=TrackedTargetRole(str(role)),
    )


def tracked_target_weapon_grant_from_parameters(
    *,
    parameters: Mapping[str, object],
    source_rule_id: str,
) -> CatalogTrackedTargetWeaponGrant | None:
    if parameters.get("target_reference") != "tracked_target":
        return None
    owner = parameters.get("tracked_target_owner")
    role = parameters.get("tracked_target_role")
    if owner not in {"this_model", "this_unit"} or role not in {"prey", "quarry"}:
        raise GameLifecycleError("Catalog weapon keyword grant tracked-target metadata is invalid.")
    return CatalogTrackedTargetWeaponGrant(
        source_rule_id=source_rule_id,
        owner_scope=TrackedTargetOwnerScope(str(owner)),
        role=TrackedTargetRole(str(role)),
    )


def tracked_target_weapon_grant_from_clause(
    *,
    clause: RuleClause,
    source_rule_id: str,
) -> CatalogTrackedTargetWeaponGrant | None:
    descriptor = tracked_target_weapon_grant_descriptor_for_clause(clause)
    if descriptor is None:
        return None
    return CatalogTrackedTargetWeaponGrant(
        source_rule_id=source_rule_id,
        owner_scope=descriptor.owner_scope,
        role=descriptor.role,
    )


def clause_is_tracked_target_weapon_grant(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Tracked-target weapon grant requires RuleClause.")
    return tracked_target_weapon_grant_descriptor_for_clause(clause) is not None


def tracked_target_weapon_grant_applies(
    *,
    context: WeaponProfileModifierContext,
    grant: CatalogWeaponKeywordGrant,
) -> bool:
    if type(context) is not WeaponProfileModifierContext:
        raise GameLifecycleError("Catalog tracked-target weapon grant requires context.")
    if type(grant) is not CatalogWeaponKeywordGrant:
        raise GameLifecycleError("Catalog tracked-target weapon grant requires grant data.")
    tracked_target = grant.tracked_target
    if tracked_target is None:
        return True
    attacking_rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.attacking_unit_instance_id,
    )
    source_model_instance_id = None
    source_unit_instance_id = attacking_rules_unit.unit_instance_id
    if tracked_target.owner_scope is TrackedTargetOwnerScope.THIS_MODEL:
        source_model_instance_id = context.attacker_model_instance_id
        source_unit_instance_id = attacking_rules_unit.component_unit_id_for_model(
            context.attacker_model_instance_id
        )
    record = context.state.active_tracked_target_for(
        source_rule_id=tracked_target.source_rule_id,
        source_unit_instance_id=source_unit_instance_id,
        source_model_instance_id=source_model_instance_id,
        owner_scope=tracked_target.owner_scope,
        role=tracked_target.role,
    )
    target_unit_instance_id = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.target_unit_instance_id,
    ).unit_instance_id
    return record is not None and record.target_unit_instance_id == target_unit_instance_id


def catalog_weapon_grant_source_index_and_rules_unit(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    context: WeaponProfileModifierContext,
) -> tuple[AbilityCatalogIndex, RulesUnitView]:
    requested_unit_id = context.attacking_unit_instance_id
    if not any(
        requested_unit_id == unit.unit_instance_id
        or any(
            requested_unit_id == attached_unit.attached_unit_instance_id
            for attached_unit in army.attached_units
            if unit.unit_instance_id in attached_unit.component_unit_instance_ids
        )
        for army in armies
        for unit in army.units
    ):
        raise GameLifecycleError("Catalog weapon keyword grant unit is unknown.")
    rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=requested_unit_id,
    )
    rules_unit.component_unit_id_for_model(context.attacker_model_instance_id)
    for army in armies:
        if army.player_id == rules_unit.owner_player_id:
            index = ability_indexes_by_player_id.get(army.player_id)
            if index is None:
                raise GameLifecycleError("Catalog weapon keyword grant index is missing player.")
            return index, rules_unit
    raise GameLifecycleError("Catalog weapon keyword grant source army is unknown.")


def _weapon_scope_from_token(value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError("Catalog weapon keyword grant weapon_scope must be a string.")
    if value not in {"all", "melee", "ranged"}:
        raise GameLifecycleError("Unsupported catalog weapon keyword grant scope.")
    return value


def _weapon_keyword_from_value(value: object) -> WeaponKeyword:
    if type(value) is WeaponKeyword:
        return value
    if type(value) is str:
        try:
            return weapon_keyword_from_token(value)
        except WeaponProfileError as exc:
            raise GameLifecycleError(
                "Catalog weapon keyword grant keyword is unsupported."
            ) from exc
    raise GameLifecycleError("Catalog weapon keyword grant keyword must be a WeaponKeyword.")
