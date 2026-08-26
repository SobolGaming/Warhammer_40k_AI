from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    current_rules_unit_views_for_canonical_identity,
    rules_unit_view_from_armies,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class FightMovementTargetAuthorityRowPayload(TypedDict):
    target_unit_instance_id: str
    placed_living_model_instance_ids: list[str]


def selectable_enemy_unit_ids_in_canonical_inventory(
    *,
    scenario: BattlefieldScenario,
    selectable_enemy_ids: tuple[str, ...],
    canonical_inventory: tuple[str, ...],
) -> tuple[str, ...]:
    canonical_ids = frozenset(canonical_inventory)
    return tuple(
        enemy_id
        for enemy_id in selectable_enemy_ids
        if rules_unit_view_from_armies(
            armies=scenario.armies,
            unit_instance_id=enemy_id,
        ).unit_instance_id
        in canonical_ids
    )


def build_fight_movement_target_authority_witness(
    *,
    state: GameState,
    target_unit_instance_ids: tuple[str, ...],
) -> JsonValue:
    """Capture target liveness immediately before a Fight movement is resolved."""

    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Fight movement target authority requires battlefield_state.")
    placed_model_ids = frozenset(battlefield.placed_model_ids())
    rows: list[FightMovementTargetAuthorityRowPayload] = []
    witnessed_target_ids: set[str] = set()
    witnessed_model_ids: set[str] = set()
    for target_unit_id in target_unit_instance_ids:
        if target_unit_id in witnessed_target_ids:
            raise GameLifecycleError("Fight movement target authority is duplicated.")
        target_rules_units = current_rules_unit_views_for_canonical_identity(
            state=state,
            unit_instance_id=target_unit_id,
        )
        living_model_ids = tuple(
            sorted(
                model.model_instance_id
                for target_rules_unit in target_rules_units
                for model in target_rules_unit.own_models
                if model.is_alive and model.model_instance_id in placed_model_ids
            )
        )
        if not living_model_ids or witnessed_model_ids.intersection(living_model_ids):
            raise GameLifecycleError(
                "Fight movement target authority requires a distinct placed living target."
            )
        rows.append(
            {
                "target_unit_instance_id": target_unit_id,
                "placed_living_model_instance_ids": list(living_model_ids),
            }
        )
        witnessed_target_ids.add(target_unit_id)
        witnessed_model_ids.update(living_model_ids)
    return validate_json_value(rows)


__all__ = (
    "FightMovementTargetAuthorityRowPayload",
    "build_fight_movement_target_authority_witness",
    "selectable_enemy_unit_ids_in_canonical_inventory",
)
