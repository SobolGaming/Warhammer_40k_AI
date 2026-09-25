"""One capability and blocker owner for live and historical Charge paths."""

from __future__ import annotations

from collections.abc import Mapping

from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.aircraft import AircraftMovementPolicy
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.charge_rule_effects import (
    charge_path_context_with_rule_effect_permissions,
)
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pathing import (
    PathValidationContext,
    PathWitness,
    TerrainPathLegalityContext,
)
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainVolume
from warhammer40k_core.geometry.volume import Model


def charge_model_path_contexts(
    *,
    unit: UnitInstance,
    moving_model: Model,
    witness: PathWitness,
    ruleset: RulesetDescriptor,
    owner_player_id: str,
    current_model_instance_ids: tuple[str, ...],
    take_to_the_skies: bool,
    ability_index: AbilityCatalogIndex | None,
    effects: tuple[PersistingEffect, ...],
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    friendly_models: tuple[Model, ...],
    enemy_models: tuple[Model, ...],
    units_by_model_id: Mapping[str, UnitInstance],
    retained_model_ids: frozenset[str],
    maximum_distance_inches: float,
    terrain: tuple[TerrainVolume, ...],
    terrain_features: tuple[TerrainFeatureDefinition, ...],
) -> tuple[PathValidationContext, TerrainPathLegalityContext]:
    legality = MovementLegalityContext.from_keywords(
        keywords=AircraftMovementPolicy.from_unit(
            unit=unit, ruleset_descriptor=ruleset
        ).effective_keywords,
        ruleset_descriptor=ruleset,
        movement_mode=MovementMode.CHARGE,
        take_to_the_skies=take_to_the_skies,
        movement_phase_action=None,
        displacement_kind=ModelDisplacementKind.CHARGE_MOVE,
        ability_index=ability_index,
        unit=unit,
        model_instance_id=moving_model.model_id,
        current_model_instance_ids=current_model_instance_ids,
        unit_persisting_effects=effects,
        owner_player_id=owner_player_id,
    )

    def matching(models: tuple[Model, ...], keywords: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            sorted(
                m.model_id
                for m in models
                if set(keywords) & set(units_by_model_id[m.model_id].keywords)
            )
        )

    def blockers(models: tuple[Model, ...], keywords: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    *matching(models, keywords),
                    *(m.model_id for m in models if m.model_id in retained_model_ids),
                }
            )
        )

    enemies_vm = matching(enemy_models, ("VEHICLE", "MONSTER"))
    path = legality.to_path_validation_context(
        moving_model=moving_model,
        witness=witness,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        friendly_models=friendly_models,
        enemy_models=enemy_models,
        terrain=(),
        friendly_vehicle_monster_model_ids=matching(friendly_models, ("VEHICLE", "MONSTER")),
        enemy_vehicle_monster_model_ids=enemies_vm,
        friendly_model_transit_blocker_ids=blockers(
            friendly_models, legality.capabilities.friendly_model_transit_blocker_keywords
        ),
        enemy_model_transit_blocker_ids=blockers(
            enemy_models, legality.capabilities.enemy_model_transit_blocker_keywords
        ),
        aircraft_model_ids=tuple(
            sorted(
                m.model_id
                for m in (*friendly_models, *enemy_models)
                if m.model_id not in retained_model_ids
                and "AIRCRAFT"
                in next(
                    model.keywords
                    for model in units_by_model_id[m.model_id].own_models
                    if model.model_instance_id == m.model_id
                )
            )
        ),
        movement_distance_budget_inches=maximum_distance_inches,
    )
    path = charge_path_context_with_rule_effect_permissions(
        path,
        unit_persisting_effects=effects,
        owner_player_id=owner_player_id,
        enemy_vehicle_monster_model_ids=enemies_vm,
    )
    return path, legality.to_terrain_path_legality_context(
        moving_model=moving_model,
        witness=witness,
        terrain=terrain,
        terrain_features=terrain_features,
    )
