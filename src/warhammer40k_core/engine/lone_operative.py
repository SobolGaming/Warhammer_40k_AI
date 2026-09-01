from __future__ import annotations

from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.engine.shooting_selection_range import (
    target_within_shooting_selection_range,
)
from warhammer40k_core.engine.unit_abilities import (
    LoneOperativeAbilityProfile,
    lone_operative_profile_for_unit,
)
from warhammer40k_core.engine.unit_factory import UnitInstance


def lone_operative_profile_for_rules_unit(
    rules_unit: RulesUnitView,
) -> LoneOperativeAbilityProfile | None:
    if type(rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Lone Operative resolver requires a RulesUnitView.")
    alive_components = rules_unit.living_components
    if not alive_components:
        return None
    profiles: list[LoneOperativeAbilityProfile] = []
    for component in alive_components:
        profile = lone_operative_profile_for_unit(component.unit)
        if profile is None:
            return None
        profiles.append(profile)
    return max(profiles, key=lambda profile: (profile.range_inches, profile.source_id))


def lone_operative_target_allowed(
    *,
    scenario: BattlefieldScenario,
    attacker_unit: UnitInstance,
    attacker_model_instance_id: str | None,
    target_rules_unit: RulesUnitView,
    profile: LoneOperativeAbilityProfile,
) -> bool:
    if type(attacker_unit) is not UnitInstance:
        raise GameLifecycleError("Lone Operative targeting requires an attacker UnitInstance.")
    if type(target_rules_unit) is not RulesUnitView:
        raise GameLifecycleError("Lone Operative targeting requires a target RulesUnitView.")
    if type(profile) is not LoneOperativeAbilityProfile:
        raise GameLifecycleError("Lone Operative targeting requires a structured profile.")
    return target_within_shooting_selection_range(
        scenario=scenario,
        attacking_unit_instance_id=attacker_unit.unit_instance_id,
        attacker_model_instance_id=attacker_model_instance_id,
        target_unit_instance_id=target_rules_unit.unit_instance_id,
        max_range_inches=profile.range_inches,
        placed_alive_attacker_models_only=True,
        placed_alive_target_models_only=True,
    )
