from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_rule_effects import (
    charge_transit_through_non_vehicle_monster_models_allowed,
)
from warhammer40k_core.geometry.pathing import PathValidationContext


def charge_path_context_with_rule_effect_permissions(
    path_context: PathValidationContext,
    *,
    unit_persisting_effects: tuple[PersistingEffect, ...],
    owner_player_id: str,
    enemy_vehicle_monster_model_ids: tuple[str, ...],
) -> PathValidationContext:
    if not charge_transit_through_non_vehicle_monster_models_allowed(
        unit_persisting_effects,
        owner_player_id=owner_player_id,
    ):
        return path_context
    return replace(
        path_context,
        may_transit_enemy_models=True,
        enemy_vehicle_monster_model_ids=enemy_vehicle_monster_model_ids,
    )


def enemy_vehicle_monster_model_ids_for_player(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    model_ids: list[str] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == requested_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            unit = scenario.unit_instance_for_placement(unit_placement)
            if not unit_has_vehicle_or_monster_keyword(unit.keywords):
                continue
            model_ids.extend(
                placement.model_instance_id for placement in unit_placement.model_placements
            )
    return tuple(sorted(model_ids))


def unit_has_vehicle_or_monster_keyword(keywords: tuple[str, ...]) -> bool:
    keyword_set = {_canonical_keyword(keyword) for keyword in keywords}
    return "VEHICLE" in keyword_set or "MONSTER" in keyword_set


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).upper().replace(" ", "_").replace("-", "_")


_validate_identifier = IdentifierValidator(GameLifecycleError)
