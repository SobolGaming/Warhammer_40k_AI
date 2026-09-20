"""Category 23 restrictions use canonical unit and individual model keywords."""

from __future__ import annotations

from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_view_from_armies,
    rules_unit_view_with_retained_models,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_aircraft_2026_09 import (
    COMBAT_SOURCE_ID as COMBAT_SOURCE_ID,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_aircraft_2026_09 import (
    MOVEMENT_SOURCE_ID as MOVEMENT_SOURCE_ID,
)

AIRCRAFT_INGRESS_ONLY = "aircraft_ingress_only"


def aircraft_rules_unit(scenario: BattlefieldScenario, unit_id: str) -> RulesUnitView:
    return rules_unit_view_with_retained_models(
        view=rules_unit_view_from_armies(armies=scenario.armies, unit_instance_id=unit_id),
        retained_model_ids=scenario.present_destroyed_model_ids,
    )


def aircraft_movement_target_ids(
    scenario: BattlefieldScenario, mover_id: str, target_ids: tuple[str, ...]
) -> tuple[str, ...]:
    mover = aircraft_rules_unit(scenario, mover_id)
    return tuple(
        target_id
        for target_id in target_ids
        if aircraft_movement_target_allowed(
            mover,
            aircraft_rules_unit(scenario, target_id),
        )
    )


def aircraft_movement_target_allowed(mover: RulesUnitView, target: RulesUnitView) -> bool:
    """Pile-in, Consolidation and Surge ignore Aircraft for non-FLY units."""
    return "AIRCRAFT" not in target.keywords or "FLY" in mover.keywords


def aircraft_melee_target_allowed(
    attacker: RulesUnitView, model_instance_id: str, target: RulesUnitView
) -> bool:
    model = attacker.model_by_id(model_instance_id)
    return ("AIRCRAFT" not in attacker.keywords or "FLY" in target.keywords) and (
        "AIRCRAFT" not in target.keywords or "FLY" in model.keywords
    )


def aircraft_melee_target_ids(
    *,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
    model_instance_id: str,
    target_ids: tuple[str, ...],
) -> tuple[str, ...]:
    attacker = aircraft_rules_unit(scenario, unit_instance_id)
    return tuple(
        target_id
        for target_id in target_ids
        if aircraft_melee_target_allowed(
            attacker,
            model_instance_id,
            aircraft_rules_unit(scenario, target_id),
        )
    )
