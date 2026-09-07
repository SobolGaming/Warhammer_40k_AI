from __future__ import annotations

from warhammer40k_core.core.modifiers import resolve_targeting_range
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.terrain_areas import PlacedTerrainArea
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.engine.shooting_model_blockers import shooting_dynamic_model_blockers
from warhammer40k_core.engine.shooting_terrain_visibility import (
    blocker_record_is_solid,
    model_visibility_keywords_for_rules_unit,
    model_within_solid_terrain,
    terrain_visibility_areas_from_placements,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.geometry.visibility import TerrainVisibilityContext
from warhammer40k_core.geometry.volume import Model


def hidden_detection_eligible_target_model_ids(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    attacker_unit: UnitInstance,
    attacker_models: tuple[Model, ...],
    target_rules_unit: RulesUnitView,
    target_models: tuple[Model, ...],
    visibility_cache_key: str,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    terrain_areas: tuple[PlacedTerrainArea, ...],
    hidden_target_model_ids: tuple[str, ...],
    target_unit_ids_with_recent_ranged_attacks: tuple[str, ...],
    target_detection_range_bonus_inches: int,
) -> tuple[str, ...]:
    target_model_ids = {model.model_id for model in target_models}
    hidden_model_ids = target_model_ids.intersection(hidden_target_model_ids)
    if not hidden_model_ids:
        return tuple(sorted(target_model_ids))
    visibility_policy = ruleset_descriptor.terrain_visibility_policy
    if not visibility_policy.hidden_supported:
        raise GameLifecycleError("Hidden target state requires hidden visibility support.")
    hidden_detection_range = visibility_policy.hidden_detection_range_inches
    if hidden_detection_range is None:
        raise GameLifecycleError("Hidden target state requires a detection range.")
    base_detection_range = hidden_detection_range + float(target_detection_range_bonus_inches)
    dynamic_model_blockers = shooting_dynamic_model_blockers(
        scenario=scenario,
        observing_unit_id=attacker_unit.unit_instance_id,
        target_unit_id=target_rules_unit.unit_instance_id,
    )
    eligible_model_ids = target_model_ids - hidden_model_ids
    target_made_recent_ranged_attacks = (
        target_rules_unit.unit_instance_id in target_unit_ids_with_recent_ranged_attacks
    )
    for target_model in target_models:
        if target_model.model_id not in hidden_model_ids:
            continue
        for attacker_model in attacker_models:
            effective_detection_range = base_detection_range
            if (
                not target_made_recent_ranged_attacks
                and visibility_policy.hidden_gone_to_ground_detection_penalty_inches > 0.0
                and _target_model_has_gone_to_ground_against_attacker(
                    ruleset_descriptor=ruleset_descriptor,
                    attacker_unit=attacker_unit,
                    attacker_model=attacker_model,
                    target_rules_unit=target_rules_unit,
                    target_model=target_model,
                    visibility_cache_key=visibility_cache_key,
                    terrain_features=terrain_features,
                    terrain_areas=terrain_areas,
                    dynamic_model_blockers=dynamic_model_blockers,
                )
            ):
                effective_detection_range -= (
                    visibility_policy.hidden_gone_to_ground_detection_penalty_inches
                )
            if attacker_model.range_to(target_model) <= resolve_targeting_range(
                effective_detection_range
            ):
                eligible_model_ids.add(target_model.model_id)
                break
    return tuple(sorted(eligible_model_ids))


def _target_model_has_gone_to_ground_against_attacker(
    *,
    ruleset_descriptor: RulesetDescriptor,
    attacker_unit: UnitInstance,
    attacker_model: Model,
    target_rules_unit: RulesUnitView,
    target_model: Model,
    visibility_cache_key: str,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    terrain_areas: tuple[PlacedTerrainArea, ...],
    dynamic_model_blockers: tuple[Model, ...],
) -> bool:
    if not model_within_solid_terrain(
        ruleset_descriptor=ruleset_descriptor,
        model=target_model,
        terrain_features=terrain_features,
        terrain_areas=terrain_areas,
    ):
        return False
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=ruleset_descriptor,
        los_cache_key=visibility_cache_key,
        observer_model=attacker_model,
        target_models=(target_model,),
        target_model_keywords=model_visibility_keywords_for_rules_unit(
            rules_unit=target_rules_unit,
            models=(target_model,),
        ),
        terrain_features=terrain_features,
        terrain_areas=terrain_visibility_areas_from_placements(terrain_areas),
        dynamic_model_blockers=dynamic_model_blockers,
        observer_keywords=attacker_unit.keywords,
    )
    witness = context.resolve_line_of_sight()
    if witness.unit_fully_visible:
        return False
    return any(
        record.blocks_full_visibility
        and blocker_record_is_solid(
            ruleset_descriptor=ruleset_descriptor,
            record=record,
            terrain_features=terrain_features,
        )
        for record in witness.all_blocker_records()
    )
