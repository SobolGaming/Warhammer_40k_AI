"""Source-linked Cover grants from a unit and its obscuring physical models."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.visibility import TerrainVisibilityContext, VisibilityBlockerKind
from warhammer40k_core.core.weapon_profiles import RangeProfileKind
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import (
    geometry_model_for_placement,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.generic_rule_effect_payloads import (
    generic_rule_effect_payload_grants_ability,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_unit_effects import rules_unit_effect_applications
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id, rules_unit_views_for_state
from warhammer40k_core.engine.shooting_model_blockers import shooting_dynamic_model_blockers
from warhammer40k_core.engine.shooting_selection_range import (
    geometry_models_for_unit_placements,
    unit_placements_for_rules_unit_or_none,
)
from warhammer40k_core.engine.shooting_terrain_visibility import (
    model_visibility_keywords_for_rules_unit,
    shooting_terrain_areas_for_state,
    shooting_visibility_cache_key,
    terrain_visibility_areas_from_placements,
)
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

COVER_FROM_OBSCURING_MODELS = "cover_from_obscuring_models"


def obscuring_model_cover_sources(*, state: GameState, pool: RangedAttackPool) -> JsonValue:
    """Re-evaluate present source groups against this attacking model, without mutation."""
    if pool.weapon_profile.range_profile.kind is not RangeProfileKind.DISTANCE:
        return None
    grants = tuple(
        effect
        for effect in state.persisting_effects
        if isinstance(effect.effect_payload, dict)
        and generic_rule_effect_payload_grants_ability(
            effect.effect_payload, ability=COVER_FROM_OBSCURING_MODELS
        )
    )
    if not grants:
        return None
    target = rules_unit_view_by_id(state=state, unit_instance_id=pool.target_unit_instance_id)
    commitments: list[JsonValue] = []
    source_groups: list[tuple[tuple[str, ...], JsonValue]] = []
    grant_ids = {effect.effect_id for effect in grants}
    for view in rules_unit_views_for_state(state=state):
        applications = tuple(
            a
            for a in rules_unit_effect_applications(state, view.unit_instance_id)
            if a.effect.effect_id in grant_ids
        )
        if not applications:
            continue
        # The physical rules unit owns the effect, including attached and retained
        # models. The ordinary effect lineage handles destroyed/split components.
        model_ids = tuple(
            model.model_instance_id
            for model in (
                *view.alive_models(),
                *(view.model_by_id(i) for i in view.retained_model_ids),
            )
        )
        if not model_ids:
            continue
        evidence = validate_json_value(
            {
                "source_unit_instance_id": view.unit_instance_id,
                "model_ids": list(model_ids),
                "effects": [a.effect.to_payload() for a in applications],
            }
        )
        if view.unit_instance_id == target.unit_instance_id:
            commitments.append(evidence)
        else:
            source_groups.append((model_ids, evidence))
    if source_groups:
        context = _visibility_context(state=state, pool=pool)
        witness = context.resolve_line_of_sight()
        for model_ids, evidence in source_groups:
            if any(
                context.not_fully_visible_because_of(
                    witness,
                    target_model_id=record.target_model_id,
                    sources=tuple(
                        source
                        for source in record.blocker_records
                        if source.blocker_kind is VisibilityBlockerKind.MODEL
                        and source.blocker_id in model_ids
                    ),
                )
                for record in witness.model_records
                if not record.model_fully_visible
            ):
                commitments.append(
                    {"grant": evidence, "visibility_context": context.context_fingerprint()}
                )
    return {"sources": commitments} if commitments else None


def _visibility_context(*, state: GameState, pool: RangedAttackPool) -> TerrainVisibilityContext:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Obscuring-model Cover requires battlefield state.")
    scenario = battlefield_scenario_for_state(state=state)
    observer = next(
        (
            view
            for view in rules_unit_views_for_state(state=state)
            if pool.attacker_model_instance_id
            in {
                m.model_instance_id
                for m in (
                    *view.alive_models(),
                    *(view.model_by_id(i) for i in view.retained_model_ids),
                )
            }
        ),
        None,
    )
    if observer is None:
        raise GameLifecycleError("Obscuring-model Cover requires a present attacker.")
    model = next(
        m
        for m in (
            *observer.alive_models(),
            *(observer.model_by_id(i) for i in observer.retained_model_ids),
        )
        if m.model_instance_id == pool.attacker_model_instance_id
    )
    target = rules_unit_view_by_id(state=state, unit_instance_id=pool.target_unit_instance_id)
    placements = unit_placements_for_rules_unit_or_none(scenario=scenario, rules_unit=target)
    if placements is None:
        raise GameLifecycleError("Obscuring-model Cover requires a placed target.")
    models = geometry_models_for_unit_placements(scenario=scenario, unit_placements=placements)
    areas = shooting_terrain_areas_for_state(state)
    return TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        los_cache_key=shooting_visibility_cache_key(
            scenario=scenario, terrain_features=battlefield.terrain_features, terrain_areas=areas
        ),
        observer_model=geometry_model_for_placement(
            model=model, placement=battlefield.model_placement_by_id(model.model_instance_id)
        ),
        target_models=models,
        target_model_keywords=model_visibility_keywords_for_rules_unit(
            rules_unit=target, models=models
        ),
        terrain_features=battlefield.terrain_features,
        terrain_areas=terrain_visibility_areas_from_placements(areas),
        terrain_volumes=tuple(
            v for feature in battlefield.terrain_features for v in feature.terrain_volumes()
        ),
        dynamic_model_blockers=shooting_dynamic_model_blockers(
            scenario=scenario,
            observing_unit_id=observer.unit_instance_id,
            target_unit_id=target.unit_instance_id,
        ),
        observer_keywords=model.keywords,
    )
