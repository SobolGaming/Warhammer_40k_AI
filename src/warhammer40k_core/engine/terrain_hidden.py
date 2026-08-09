from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.shooting_selection_range import (
    geometry_models_for_unit_placements,
    unit_placements_for_rules_unit_or_none,
)
from warhammer40k_core.engine.shooting_terrain_visibility import (
    terrain_visibility_areas_from_placements,
)
from warhammer40k_core.geometry.terrain_area_visibility import (
    classification_has_visibility_semantics,
    model_intersects_terrain_area,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def unit_is_hidden_by_terrain(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    unit_instance_id: str,
) -> bool:
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Terrain Hidden evaluation requires RulesetDescriptor.")
    policy = ruleset_descriptor.terrain_visibility_policy
    if not policy.hidden_supported:
        return False
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    required_keywords = {_canonical_keyword(keyword) for keyword in policy.hidden_requires_keywords}
    unit_keywords = {_canonical_keyword(keyword) for keyword in rules_unit.keywords}
    if required_keywords and not required_keywords.intersection(unit_keywords):
        return False
    if policy.hidden_lost_after_shooting and (
        state.unit_made_ranged_attacks_current_or_previous_turn(
            unit_instance_id=rules_unit.unit_instance_id
        )
    ):
        return False
    if not policy.hidden_requires_terrain_area_occupancy:
        return True
    mission_setup = state.mission_setup
    if mission_setup is None:
        return False
    eligible_areas = tuple(
        area
        for area in terrain_visibility_areas_from_placements(mission_setup.terrain_areas)
        if classification_has_visibility_semantics(area.classification)
    )
    if not eligible_areas:
        return False
    scenario = battlefield_scenario_for_state(state=state)
    placements = unit_placements_for_rules_unit_or_none(
        scenario=scenario,
        rules_unit=rules_unit,
    )
    if placements is None:
        return False
    models = geometry_models_for_unit_placements(
        scenario=scenario,
        unit_placements=placements,
    )
    return bool(models) and all(
        any(model_intersects_terrain_area(model, area) for area in eligible_areas)
        for model in models
    )


def _canonical_keyword(keyword: str) -> str:
    return keyword.strip().upper().replace(" ", "_").replace("-", "_")
