from __future__ import annotations

from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentContribution
from warhammer40k_core.engine.generic_rule_effect_payloads import rule_effect_grants_ability
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionContext,
    ShootingTargetRestrictionHookBinding,
    TargetRestriction,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_spectacle_of_slaughter_ir_support_2026_27,
)

CONTRIBUTION_ID = (
    "warhammer_40000_11th:emperors_children:detachment:spectacle_of_slaughter:enhancements:rule_ir"
)
BEGUILING_GROTESQUERIE_DESCRIPTOR_ID = (
    "phase17e:enhancement:emperors-children:spectacle-of-slaughter:000010900002"
)
BEGUILING_GROTESQUERIE_SOURCE_ID = (
    "gw-11e-phase17e-faction-coverage-2026-27:phase17e:"
    "enhancement:emperors-children:spectacle-of-slaughter:000010900002:source-text"
)
BEGUILING_GROTESQUERIE_SNAP_TARGET_RESTRICTION_HOOK_ID = (
    "warhammer_40000_11th:emperors_children:spectacle_of_slaughter:"
    "beguiling_grotesquerie:snap_target_restriction"
)
SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY = (
    faction_spectacle_of_slaughter_ir_support_2026_27.SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY
)


def runtime_contribution() -> RuntimeContentContribution:
    return RuntimeContentContribution(
        contribution_id=CONTRIBUTION_ID,
        shooting_target_restriction_hook_bindings=(
            ShootingTargetRestrictionHookBinding(
                hook_id=BEGUILING_GROTESQUERIE_SNAP_TARGET_RESTRICTION_HOOK_ID,
                source_id=BEGUILING_GROTESQUERIE_SOURCE_ID,
                handler=beguiling_grotesquerie_snap_target_restriction,
            ),
        ),
    )


def beguiling_grotesquerie_snap_target_restriction(
    context: ShootingTargetRestrictionContext,
) -> TargetRestriction | None:
    if type(context) is not ShootingTargetRestrictionContext:
        raise GameLifecycleError("Beguiling Grotesquerie target restriction requires context.")
    if context.shooting_type is not ShootingType.SNAP:
        return None
    if not _target_has_beguiling_grotesquerie_effect(
        context=context,
        target_unit_instance_id=context.target_unit_instance_id,
    ):
        return None
    return TargetRestriction(
        hook_id=BEGUILING_GROTESQUERIE_SNAP_TARGET_RESTRICTION_HOOK_ID,
        source_id=BEGUILING_GROTESQUERIE_SOURCE_ID,
        violation_code="spectacle_of_slaughter_beguiling_grotesquerie_snap_target_forbidden",
        message="Beguiling Grotesquerie units cannot be targeted by Snap Shooting attacks.",
        replay_payload=validate_json_value(
            {
                "battle_round": context.battle_round,
                "attacking_unit_instance_id": context.attacking_unit_instance_id,
                "target_unit_instance_id": context.target_unit_instance_id,
                "shooting_type": ShootingType.SNAP.value,
            }
        ),
    )


def _target_has_beguiling_grotesquerie_effect(
    *,
    context: ShootingTargetRestrictionContext,
    target_unit_instance_id: str,
) -> bool:
    for effect in context.state.persisting_effects_for_unit(target_unit_instance_id):
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("coverage_descriptor_id") != BEGUILING_GROTESQUERIE_DESCRIPTOR_ID:
            continue
        rule_effect = payload.get("effect")
        if not isinstance(rule_effect, dict):
            raise GameLifecycleError("Beguiling Grotesquerie effect payload is malformed.")
        if rule_effect_grants_ability(
            rule_effect,
            ability=SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY,
        ):
            return True
    return False
