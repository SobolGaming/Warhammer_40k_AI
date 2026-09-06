"""Generic effect target gates consume authenticated current applications."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, cast

from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleTargetKind

type AttackRole = Literal["attacker", "target"]

_ATTACKER_TARGET_KINDS = frozenset(
    {
        RuleTargetKind.AURA_UNITS,
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
        RuleTargetKind.AURA_UNITS,
        RuleTargetKind.FRIENDLY_UNIT,
        RuleTargetKind.SELECTED_UNIT,
        RuleTargetKind.THIS_MODEL,
        RuleTargetKind.THIS_UNIT,
    }
)


@dataclass(frozen=True, slots=True)
class GenericAttackEffect:
    persisting_effect: PersistingEffect
    role: AttackRole
    source_id: str
    rule_id: str
    rule_ir_hash: str
    clause_id: str
    effect_index: int
    target_kind: RuleTargetKind | None
    effect_kind: RuleEffectKind
    parameters: dict[str, JsonValue]
    conditions: tuple[dict[str, JsonValue], ...]
    source_model_instance_id: str | None
    effective_target_unit_instance_ids: tuple[str, ...]


def generic_effect_role_applies(
    *,
    effect: GenericAttackEffect,
    role: AttackRole,
    attacking_unit_instance_id: str,
    target_unit_instance_id: str | None,
    legacy_attacker_role_allowed: Callable[[GenericAttackEffect], bool],
    legacy_target_role_allowed: Callable[[GenericAttackEffect], bool],
) -> bool:
    requested_role = attack_role_parameter(effect.parameters)
    target_ids = set(effect.effective_target_unit_instance_ids)
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


def generic_unit_effect_applies(
    *,
    effect: GenericAttackEffect,
    unit_instance_id: str,
) -> bool:
    if unit_instance_id not in effect.effective_target_unit_instance_ids:
        return False
    requested_role = attack_role_parameter(effect.parameters)
    if requested_role is not None and requested_role != "attacker":
        return False
    return effect.target_kind is None or effect.target_kind in _ATTACKER_TARGET_KINDS


def attack_role_parameter(parameters: dict[str, JsonValue]) -> AttackRole | None:
    value = parameters.get("attack_role")
    if value is None:
        return None
    if value not in {"attacker", "target"}:
        raise GameLifecycleError("Generic RuleIR attack_role must be attacker or target.")
    return cast(AttackRole, value)
