"""Typed model/enemy selections for the source-backed Explosives Stratagem."""

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


SELECTION_KIND = "source_model_and_enemy_unit"
MODEL_KEY = "source_model_instance_id"
TARGET_KEY = "enemy_target_unit_instance_id"
KEYWORDS = frozenset(("EXPLOSIVES", "GRENADES"))


@dataclass(frozen=True, slots=True)
class ExplosivesSelection:
    source_model_instance_id: str
    enemy_target_unit_instance_id: str

    def __post_init__(self) -> None:
        for value in (self.source_model_instance_id, self.enemy_target_unit_instance_id):
            if type(value) is not str or not value or value != value.strip():
                raise GameLifecycleError("Explosives selection requires stripped identifiers.")

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "effect_selection_kind": SELECTION_KIND,
            MODEL_KEY: self.source_model_instance_id,
            TARGET_KEY: self.enemy_target_unit_instance_id,
        }

    @classmethod
    def from_payload(cls, payload: JsonValue) -> ExplosivesSelection:
        if not isinstance(payload, dict) or set(payload) != {
            "effect_selection_kind",
            MODEL_KEY,
            TARGET_KEY,
        }:
            raise GameLifecycleError("Explosives selection fields are malformed.")
        model_id, target_id = payload[MODEL_KEY], payload[TARGET_KEY]
        if (
            payload["effect_selection_kind"] != SELECTION_KIND
            or type(model_id) is not str
            or type(target_id) is not str
        ):
            raise GameLifecycleError("Explosives selection values are malformed.")
        return cls(model_id, target_id)


def explosives_effect_selections(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
) -> tuple[JsonValue, ...]:
    from warhammer40k_core.engine.stratagems_geometry import (
        _explosives_context_error,
        explosives_source_error,
    )

    if (
        explosives_source_error(state=state, context=context, target_binding=target_binding)
        is not None
    ):
        return ()
    unit_id = target_binding.target_unit_instance_id
    if unit_id is None:
        raise GameLifecycleError("Explosives requires a source rules unit.")
    source = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    selections: list[JsonValue] = []
    enemies = tuple(
        u
        for u in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
        if u.owner_player_id != context.player_id
    )
    for model in sorted(source.alive_models(), key=lambda m: m.model_instance_id):
        if not KEYWORDS.intersection(model.keywords):
            continue
        for enemy in enemies:
            payload = ExplosivesSelection(
                model.model_instance_id, enemy.unit_instance_id
            ).to_payload()
            if (
                _explosives_context_error(
                    state=state,
                    context=context,
                    target_binding=target_binding,
                    effect_selection=payload,
                )
                is None
            ):
                selections.append(payload)
    return tuple(selections)
