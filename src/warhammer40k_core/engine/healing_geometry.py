from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.geometry.pose import Pose

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
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield,
    )
    ruleset_descriptor = state.runtime_ruleset_descriptor()
    own_placements = healing_rules_unit_placements(state=state, rules_unit=rules_unit)
    engaged_enemy_ids: set[str] = set()
    for own_placement in own_placements:
        own_model_instance = scenario.model_instance_for_placement(own_placement)
        if not own_model_instance.is_alive:
            continue
        own_model = geometry_model_for_placement(model=own_model_instance, placement=own_placement)
        for placed_army in battlefield.placed_armies:
            if placed_army.player_id == rules_unit.owner_player_id:
                continue
            for unit_placement in placed_army.unit_placements:
                for enemy_placement in unit_placement.model_placements:
                    enemy_model_instance = scenario.model_instance_for_placement(enemy_placement)
                    if not enemy_model_instance.is_alive:
                        continue
                    enemy_model = geometry_model_for_placement(
                        model=enemy_model_instance,
                        placement=enemy_placement,
                    )
                    if own_model.is_within_engagement_range(
                        enemy_model,
                        horizontal_inches=(ruleset_descriptor.engagement_policy.horizontal_inches),
                        vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
                    ):
                        engaged_enemy_ids.add(enemy_placement.model_instance_id)
    return tuple(sorted(engaged_enemy_ids))


def healing_revival_placements_for_rules_unit(
    *,
    state: GameState,
    army: ArmyDefinition,
    rules_unit: RulesUnitView,
) -> tuple[ModelPlacement, ...]:
    battlefield = healing_battlefield_state(state)
    removed_model_ids = set(battlefield.removed_model_ids)
    missing_models = tuple(
        sorted(
            (
                model
                for model in rules_unit.own_models
                if not model.is_alive and model.model_instance_id in removed_model_ids
            ),
            key=lambda model: model.model_instance_id,
        )
    )
    if not missing_models:
        return ()
    anchors = healing_rules_unit_placements(state=state, rules_unit=rules_unit)
    if not anchors:
        raise GameLifecycleError("Healing revival requires placed anchors.")
    placements: list[ModelPlacement] = []
    for index, model in enumerate(missing_models):
        anchor = anchors[index % len(anchors)]
        placements.append(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=rules_unit.component_unit_id_for_model(model.model_instance_id),
                model_instance_id=model.model_instance_id,
                pose=_candidate_revival_pose(
                    battlefield=battlefield,
                    anchor=anchor,
                    index=index,
                ),
            )
        )
    return tuple(placements)


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


def _candidate_revival_pose(
    *,
    battlefield: BattlefieldRuntimeState,
    anchor: ModelPlacement,
    index: int,
) -> Pose:
    offset = 0.5 + (index * 0.1)
    anchor_position = anchor.pose.position
    candidate_x = anchor_position.x + offset
    candidate_y = anchor_position.y
    if candidate_x > battlefield.battlefield_width_inches:
        candidate_x = anchor_position.x - offset
    if candidate_x < 0:
        candidate_x = anchor_position.x
        candidate_y = anchor_position.y + offset
    if candidate_y > battlefield.battlefield_depth_inches:
        candidate_y = anchor_position.y - offset
    if candidate_y < 0:
        raise GameLifecycleError("Healing could not derive revival placement.")
    return Pose.at(candidate_x, candidate_y, anchor_position.z)


__all__ = (
    "healing_battlefield_state",
    "healing_opposing_player_id",
    "healing_phase_start_enemy_engagement_model_ids",
    "healing_phase_start_model_ids",
    "healing_revival_placements_for_rules_unit",
    "healing_rules_unit_placements",
)
