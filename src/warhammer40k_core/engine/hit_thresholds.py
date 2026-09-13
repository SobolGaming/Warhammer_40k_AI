"""Source-linked hit thresholds, with absolute shooting-mode failure floors."""

from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import HitRollMinimumUnmodifiedSuccessContext
from warhammer40k_core.engine.weapon_abilities import FIRE_OVERWATCH_RULE_ID, SNAP_SHOOTING_RULE_ID
from warhammer40k_core.rules.rule_ir import RuleEffectKind
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_critical_hits_2026_09 as sources,
)


@dataclass(frozen=True, slots=True)
class HitThresholds:
    minimum_success: int
    critical_threshold: int
    source_ids: tuple[str, ...]


def resolve_hit_thresholds(context: HitRollMinimumUnmodifiedSuccessContext) -> HitThresholds:
    from warhammer40k_core.engine.generic_rule_attack_hooks import (
        _matching_generic_attack_effects,  # pyright: ignore[reportPrivateUsage]
        _required_int_parameter,  # pyright: ignore[reportPrivateUsage]
        _required_string_parameter,  # pyright: ignore[reportPrivateUsage]
        _roll_type_matches,  # pyright: ignore[reportPrivateUsage]
        generic_rule_modifier_source_id,
    )

    if type(context) is not HitRollMinimumUnmodifiedSuccessContext:
        raise GameLifecycleError("Hit thresholds require HitRollMinimumUnmodifiedSuccessContext.")
    minimum = context.current_minimum_unmodified_success
    critical = 6
    source_ids: set[str] = {sources.CRITICAL_SUCCESS_SOURCE_ID}
    snap_ids = {FIRE_OVERWATCH_RULE_ID, SNAP_SHOOTING_RULE_ID}
    is_snap = bool(snap_ids.intersection(context.targeting_rule_ids))
    if is_snap:
        source_ids.add(sources.SNAP_CRITICAL_SOURCE_ID)
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
        status = _required_string_parameter(effect.parameters, key="status")
        if status not in {"minimum_unmodified_hit_success", "critical_hit_threshold"}:
            continue
        if not _roll_type_matches(effect.parameters, expected="hit"):
            continue
        if not _targeting_rule_gate_applies(
            effect.parameters, targeting_rule_ids=context.targeting_rule_ids
        ):
            continue
        # A source-compiled Snap/Overwatch gate supplies explicit permission.
        gate = effect.parameters.get("required_targeting_rule_id")
        if is_snap and not (type(gate) is str and gate in snap_ids):
            continue
        value = _required_int_parameter(
            effect.parameters,
            key="critical_threshold"
            if status == "critical_hit_threshold"
            else "minimum_unmodified_success",
        )
        if not 2 <= value <= 6:
            raise GameLifecycleError("Hit threshold must be between 2 and 6.")
        source_ids.add(generic_rule_modifier_source_id(effect))
        if status == "critical_hit_threshold":
            critical = min(critical, value)
            if is_snap:
                minimum = min(minimum, value)
        else:
            minimum = min(minimum, value)
    # Indirect Shooting's stated failed faces remain failures. Critical hits
    # bypass the ordinary skill comparison, never that absolute failure floor.
    return HitThresholds(minimum, max(minimum, critical), tuple(sorted(source_ids)))


def _targeting_rule_gate_applies(
    parameters: dict[str, JsonValue], *, targeting_rule_ids: tuple[str, ...]
) -> bool:
    required_rule = parameters.get("required_targeting_rule_id")
    if required_rule is None:
        return True
    if (
        type(required_rule) is not str
        or not required_rule.strip()
        or required_rule != required_rule.strip()
    ):
        raise GameLifecycleError("Generic RuleIR required_targeting_rule_id must be an identifier.")
    return required_rule in targeting_rule_ids
