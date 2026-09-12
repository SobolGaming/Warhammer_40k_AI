"""One complete model-target query; no retained history or serialized derived state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.terrain_areas import PlacedTerrainArea
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.event_log import canonical_json, validate_json_value
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition

if TYPE_CHECKING:
    from warhammer40k_core.engine.shooting_targets import ShootingTargetCandidate

_last_query: tuple[str, ShootingTargetCandidate] | None = None


def clear_target_candidate_cache() -> None:
    global _last_query
    _last_query = None


def cached_target_candidate_for_model(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    attacker_unit: UnitInstance,
    attacker_model_instance_id: str,
    weapon_profile: WeaponProfile,
    target_unit_id: str,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    terrain_areas: tuple[PlacedTerrainArea, ...],
    hidden_target_model_ids: tuple[str, ...],
    target_unit_ids_with_recent_ranged_attacks: tuple[str, ...],
    target_detection_range_bonus_inches: int,
) -> ShootingTargetCandidate:
    from warhammer40k_core.engine.shooting_targets import shooting_target_candidate_for_model

    global _last_query
    # Serialize every input, including nested catalog RuleIR mappings. Frozen
    # outer domain objects alone do not guarantee hashable or immutable children.
    key = canonical_json(
        validate_json_value(
            {
                "scenario": scenario.to_payload(),
                "ruleset": ruleset_descriptor.to_payload(),
                "attacker": attacker_unit.to_payload(),
                "attacker_model_instance_id": attacker_model_instance_id,
                "weapon_profile": weapon_profile.to_payload(),
                "target_unit_id": target_unit_id,
                "terrain_features": [feature.to_payload() for feature in terrain_features],
                "terrain_areas": [area.to_payload() for area in terrain_areas],
                "hidden_target_model_ids": list(hidden_target_model_ids),
                "target_unit_ids_with_recent_ranged_attacks": list(
                    target_unit_ids_with_recent_ranged_attacks
                ),
                "target_detection_range_bonus_inches": target_detection_range_bonus_inches,
            }
        )
    )
    previous = _last_query
    if previous is not None and previous[0] == key:
        return previous[1]
    candidate = shooting_target_candidate_for_model(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        attacker_unit=attacker_unit,
        attacker_model_instance_id=attacker_model_instance_id,
        weapon_profile=weapon_profile,
        target_unit_id=target_unit_id,
        terrain_features=terrain_features,
        terrain_areas=terrain_areas,
        hidden_target_model_ids=hidden_target_model_ids,
        target_unit_ids_with_recent_ranged_attacks=target_unit_ids_with_recent_ranged_attacks,
        target_detection_range_bonus_inches=target_detection_range_bonus_inches,
    )
    # Publish the key/result together. Concurrent callers can only lose reuse,
    # never observe a key paired with a different query's answer.
    _last_query = (key, candidate)
    return candidate
