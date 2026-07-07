from __future__ import annotations

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.generic_rule_ability_registry import (
    GenericRuleAbilitySource,
    GenericRuleReserveArrivalDistanceAbility,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserve_arrival_hooks import (
    ReserveArrivalDistanceContext,
    ReserveArrivalDistanceGrant,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_daemonic_incursion_ir_support_2026_27 as daemonic_incursion_ir,
)


def _daemonic_incursion_warp_rifts_context_predicate(
    context: ReserveArrivalDistanceContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(context) is not ReserveArrivalDistanceContext:
        raise GameLifecycleError("Daemonic Incursion reserve-arrival distance requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Daemonic Incursion reserve-arrival distance requires source.")
    return (
        source.record.coverage_descriptor_id
        == daemonic_incursion_ir.DAEMONIC_INCURSION_DETACHMENT_RULE_DESCRIPTOR_ID
    )


def _daemonic_incursion_warp_rifts_grants(
    context: ReserveArrivalDistanceContext,
    source: GenericRuleAbilitySource,
) -> tuple[ReserveArrivalDistanceGrant, ...]:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Daemonic Incursion reserve-arrival grants require source.")
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.daemonic_incursion import (  # noqa: E501
        rule,
    )

    return rule.warp_rifts_distance_grants(context, source=source)


def _daemonic_incursion_warp_rifts_hook_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Daemonic Incursion reserve-arrival hook ID requires source.")
    return _validate_identifier(
        "generic Daemonic Incursion Warp Rifts hook_id",
        daemonic_incursion_ir.WARP_RIFTS_HOOK_ID,
    )


daemonic_incursion_reserve_arrival_distance_abilities = (
    GenericRuleReserveArrivalDistanceAbility(
        ability_id=daemonic_incursion_ir.WARP_RIFTS_DEEP_STRIKE_DISTANCE_ABILITY,
        coverage_descriptor_id=(
            daemonic_incursion_ir.DAEMONIC_INCURSION_DETACHMENT_RULE_DESCRIPTOR_ID
        ),
        source_rule_id=daemonic_incursion_ir.DAEMONIC_INCURSION_SOURCE_RULE_ID,
        hook_id_builder=_daemonic_incursion_warp_rifts_hook_id,
        context_predicate=_daemonic_incursion_warp_rifts_context_predicate,
        grant_builder=_daemonic_incursion_warp_rifts_grants,
    ),
)


_validate_identifier = IdentifierValidator(GameLifecycleError)
