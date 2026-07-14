from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    WeaponKeyword,
    WeaponProfileError,
    weapon_keyword_from_token,
)
from warhammer40k_core.engine.faction_content.bundle_validation import validate_identifier
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import WeaponProfileModifierContext
from warhammer40k_core.engine.tracked_targets import TrackedTargetOwnerScope, TrackedTargetRole
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleTargetKind,
    parameter_payload,
)


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


def clause_is_tracked_target_weapon_grant(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Tracked-target weapon grant requires RuleClause.")
    if (
        not clause.is_supported
        or clause.trigger is not None
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or len(clause.effects) != 1
    ):
        return False
    effect = clause.effects[0]
    if effect.kind is not RuleEffectKind.GRANT_WEAPON_ABILITY:
        return False
    effect_parameters = parameter_payload(effect.parameters)
    owner = effect_parameters.get("tracked_target_owner")
    role = effect_parameters.get("tracked_target_role")
    if (
        effect_parameters.get("target_reference") != "tracked_target"
        or owner not in {"this_model", "this_unit"}
        or role not in {"prey", "quarry"}
    ):
        return False
    return any(
        condition.kind is RuleConditionKind.TARGET_CONSTRAINT
        and parameter_payload(condition.parameters).get("relationship")
        == "attack_targets_tracked_target"
        and parameter_payload(condition.parameters).get("target_reference") == "tracked_target"
        and parameter_payload(condition.parameters).get("tracked_target_owner") == owner
        and parameter_payload(condition.parameters).get("tracked_target_role") == role
        and parameter_payload(condition.parameters).get("gate_subject") == "attack_target"
        for condition in clause.conditions
    )


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
    source_model_instance_id = (
        context.attacker_model_instance_id
        if tracked_target.owner_scope is TrackedTargetOwnerScope.THIS_MODEL
        else None
    )
    record = context.state.active_tracked_target_for(
        source_rule_id=tracked_target.source_rule_id,
        source_unit_instance_id=context.attacking_unit_instance_id,
        source_model_instance_id=source_model_instance_id,
        owner_scope=tracked_target.owner_scope,
        role=tracked_target.role,
    )
    return record is not None and record.target_unit_instance_id == context.target_unit_instance_id


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
