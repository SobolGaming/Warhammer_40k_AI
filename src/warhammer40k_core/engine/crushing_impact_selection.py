"""Source-model choices and capped results for the existing Crushing Impact handler."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id, rules_unit_views_from_armies

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems_model import (
        StratagemEligibilityContext,
        StratagemTargetBinding,
    )

MODEL_KEY = "model_instance_id"
ENEMY_KEY = "enemy_target_unit_instance_id"


@dataclass(frozen=True, slots=True)
class CrushingImpactSelection:
    enemy_target_unit_instance_id: str
    model_instance_id: str

    def __post_init__(self) -> None:
        for value in (self.enemy_target_unit_instance_id, self.model_instance_id):
            if type(value) is not str or not value or value != value.strip():
                raise GameLifecycleError("Crushing Impact requires stripped selection IDs.")

    def to_payload(self) -> dict[str, JsonValue]:
        return {ENEMY_KEY: self.enemy_target_unit_instance_id, MODEL_KEY: self.model_instance_id}

    @classmethod
    def from_payload(cls, payload: JsonValue) -> CrushingImpactSelection:
        if not isinstance(payload, dict) or set(payload) != {ENEMY_KEY, MODEL_KEY}:
            raise GameLifecycleError("Crushing Impact selection fields are malformed.")
        enemy_id, model_id = payload[ENEMY_KEY], payload[MODEL_KEY]
        if type(enemy_id) is not str or type(model_id) is not str:
            raise GameLifecycleError("Crushing Impact selection values are malformed.")
        return cls(enemy_id, model_id)


def crushing_impact_effect_selections(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
) -> tuple[JsonValue, ...]:
    from warhammer40k_core.engine.stratagems_geometry import _crushing_impact_context_error

    source_id = target_binding.target_unit_instance_id
    if source_id is None:
        raise GameLifecycleError("Crushing Impact requires a source rules unit.")
    source = rules_unit_view_by_id(state=state, unit_instance_id=source_id)
    selections: list[JsonValue] = []
    for enemy in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
        if enemy.owner_player_id == context.player_id:
            continue
        for model in sorted(source.alive_models(), key=lambda m: m.model_instance_id):
            selection = CrushingImpactSelection(enemy.unit_instance_id, model.model_instance_id)
            if (
                _crushing_impact_context_error(
                    state=state,
                    context=context,
                    target_binding=target_binding,
                    effect_selection=selection.to_payload(),
                )
                is None
            ):
                selections.append(selection.to_payload())
    return tuple(selections)


def crushing_impact_mortal_wounds(values: tuple[int, ...]) -> tuple[int, int]:
    from warhammer40k_core.engine.stratagems_model import CRUSHING_IMPACT_MAX_MORTAL_WOUNDS_PER_UNIT

    if not values or any(type(value) is not int or not 1 <= value <= 6 for value in values):
        raise GameLifecycleError("Crushing Impact requires a nonempty D6 result.")
    cap = CRUSHING_IMPACT_MAX_MORTAL_WOUNDS_PER_UNIT
    return min(cap, values.count(1)), min(cap, sum(value >= 5 for value in values))
