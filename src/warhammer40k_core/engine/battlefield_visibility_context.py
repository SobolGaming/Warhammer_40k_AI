"""Engine context construction supplies the authoritative battlefield boundary.

Pure geometry callers may make unbounded analytic queries. Every engine consumer
uses this extracted factory, so cached shooting, cover and faction queries cannot
omit the outgoing-origin clipping boundary.
"""

from fractions import Fraction

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.visibility import TerrainVisibilityContext
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.geometry.physical_visibility import BattlefieldVisibilityBounds
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainVolume
from warhammer40k_core.geometry.terrain_area_visibility import TerrainVisibilityArea
from warhammer40k_core.geometry.volume import Model


def battlefield_visibility_context(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    los_cache_key: str,
    observer_model: Model,
    target_models: tuple[Model, ...],
    target_model_keywords: tuple[tuple[str, tuple[str, ...]], ...],
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
    terrain_areas: tuple[TerrainVisibilityArea, ...] = (),
    terrain_volumes: tuple[TerrainVolume, ...] = (),
    dynamic_model_blockers: tuple[Model, ...] = (),
    observer_keywords: tuple[str, ...] = (),
) -> TerrainVisibilityContext:
    field = scenario.battlefield_state
    return TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=ruleset_descriptor,
        los_cache_key=los_cache_key,
        observer_model=observer_model,
        target_models=target_models,
        target_model_keywords=target_model_keywords,
        terrain_features=terrain_features,
        terrain_areas=terrain_areas,
        terrain_volumes=terrain_volumes,
        dynamic_model_blockers=dynamic_model_blockers,
        observer_keywords=observer_keywords,
        battlefield_bounds=BattlefieldVisibilityBounds(
            Fraction(0),
            Fraction(0),
            Fraction(field.battlefield_width_inches),
            Fraction(field.battlefield_depth_inches),
        ),
    )
