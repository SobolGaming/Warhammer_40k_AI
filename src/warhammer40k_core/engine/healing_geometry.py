from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.physical_engagement import (
    physical_geometry_models_for_rules_unit,
)
from warhammer40k_core.engine.rules_units import RulesUnitView

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def healing_phase_start_model_ids(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            placement.model_instance_id
            for placement in healing_rules_unit_placements(
                state=state,
                rules_unit=rules_unit,
            )
        )
    )


def healing_phase_start_enemy_engagement_model_ids(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> tuple[str, ...]:
    battlefield = healing_battlefield_state(state)
    scenario = battlefield_scenario_for_state(state=state)
    ruleset_descriptor = state.runtime_ruleset_descriptor()
    own_models = physical_geometry_models_for_rules_unit(
        scenario=scenario,
        unit_instance_id=rules_unit.unit_instance_id,
    )
    engaged_enemy_ids: set[str] = set()
    for placed_army in battlefield.placed_armies:
        if placed_army.player_id == rules_unit.owner_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            for enemy_placement in unit_placement.model_placements:
                if not scenario.model_is_present_at_placement(enemy_placement):
                    continue
                enemy_model = geometry_model_for_placement(
                    model=scenario.model_instance_for_placement(enemy_placement),
                    placement=enemy_placement,
                )
                if any(
                    own_model.is_within_engagement_range(
                        enemy_model,
                        horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
                        vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
                    )
                    for own_model in own_models
                ):
                    engaged_enemy_ids.add(enemy_placement.model_instance_id)
    return tuple(sorted(engaged_enemy_ids))


def healing_rules_unit_placements(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> tuple[ModelPlacement, ...]:
    battlefield = healing_battlefield_state(state)
    component_ids = set(rules_unit.component_unit_instance_ids)
    model_ids = {model.model_instance_id for model in rules_unit.own_models}
    placements: list[ModelPlacement] = []
    for placed_army in battlefield.placed_armies:
        if placed_army.player_id != rules_unit.owner_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            _append_component_placements(
                placements=placements,
                unit_placement=unit_placement,
                component_ids=component_ids,
                model_ids=model_ids,
            )
    return tuple(sorted(placements, key=lambda placement: placement.model_instance_id))


def healing_opposing_player_id(*, state: GameState, player_id: str) -> str:
    opponents = tuple(sorted(candidate for candidate in state.player_ids if candidate != player_id))
    if len(opponents) != 1:
        raise GameLifecycleError("Healing resolution requires one opposing player.")
    return opponents[0]


def healing_battlefield_state(state: GameState) -> BattlefieldRuntimeState:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Healing requires battlefield_state.")
    if type(battlefield) is not BattlefieldRuntimeState:
        raise GameLifecycleError("Healing battlefield_state is invalid.")
    return battlefield


def _append_component_placements(
    *,
    placements: list[ModelPlacement],
    unit_placement: UnitPlacement,
    component_ids: set[str],
    model_ids: set[str],
) -> None:
    if unit_placement.unit_instance_id not in component_ids:
        return
    placements.extend(
        placement
        for placement in unit_placement.model_placements
        if placement.model_instance_id in model_ids
    )


__all__ = (
    "healing_battlefield_state",
    "healing_opposing_player_id",
    "healing_phase_start_enemy_engagement_model_ids",
    "healing_phase_start_model_ids",
    "healing_rules_unit_placements",
)
