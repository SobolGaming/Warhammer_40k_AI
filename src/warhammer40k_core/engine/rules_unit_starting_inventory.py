"""Frozen battle membership, including source-authorized pre-battle partitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


@dataclass(frozen=True, slots=True)
class RulesUnitStartingMembership:
    rules_unit_instance_id: str
    player_id: str
    component_models: tuple[tuple[str, tuple[str, ...]], ...]
    is_attached: bool

    @property
    def component_ids(self) -> tuple[str, ...]:
        return tuple(component for component, _ in self.component_models)

    @property
    def model_ids(self) -> tuple[str, ...]:
        return tuple(sorted(model for _, models in self.component_models for model in models))


def starting_rules_unit_inventory(state: GameState) -> tuple[RulesUnitStartingMembership, ...]:
    originals = {r.attached_unit_instance_id: r for r in state.starting_attached_unit_records}
    rows: list[RulesUnitStartingMembership] = []
    for view in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
        split = view.split_record
        if split is not None:
            component_models = tuple(
                (
                    component.unit.unit_instance_id,
                    tuple(
                        sorted(
                            model.model_instance_id
                            for source in split.source_units
                            for model in source.own_models
                            if model.model_instance_id in component.unit.own_model_ids()
                        )
                    ),
                )
                for component in view.components
            )
        elif view.unit_instance_id in originals:
            component_models = originals[
                view.unit_instance_id
            ].starting_model_instance_ids_by_component
        else:
            component_models = tuple(
                (component.unit.unit_instance_id, component.unit.own_model_ids())
                for component in view.components
            )
        rows.append(
            RulesUnitStartingMembership(
                view.unit_instance_id,
                view.owner_player_id,
                tuple(sorted(component_models)),
                view.is_attached_rules_unit,
            )
        )
    return tuple(rows)
