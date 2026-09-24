from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.revival_phase_start import revival_phase_start_evidence
from warhammer40k_core.engine.rules_units import RulesUnitView

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def healing_phase_start_model_ids(
    *,
    state: GameState,
    decisions: DecisionController,
    rules_unit: RulesUnitView,
) -> tuple[str, ...]:
    evidence = revival_phase_start_evidence(
        state=state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
        target_unit_instance_id=rules_unit.unit_instance_id,
    )
    return tuple(evidence["model_ids"])


def healing_rules_unit_placements(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> tuple[ModelPlacement, ...]:
    battlefield = healing_battlefield_state(state)
    component_ids = set(rules_unit.component_unit_instance_ids)
    model_ids = {model.model_instance_id for model in rules_unit.own_models}
    placements: list[ModelPlacement] = []
    for placed_army in battlefield.placed_armies:
        if placed_army.player_id != rules_unit.owner_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            _append_component_placements(
                placements=placements,
                unit_placement=unit_placement,
                component_ids=component_ids,
                model_ids=model_ids,
            )
    return tuple(sorted(placements, key=lambda placement: placement.model_instance_id))


def healing_opposing_player_id(*, state: GameState, player_id: str) -> str:
    opponents = tuple(sorted(candidate for candidate in state.player_ids if candidate != player_id))
    if len(opponents) != 1:
        raise GameLifecycleError("Healing resolution requires one opposing player.")
    return opponents[0]


def healing_battlefield_state(state: GameState) -> BattlefieldRuntimeState:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Healing requires battlefield_state.")
    if type(battlefield) is not BattlefieldRuntimeState:
        raise GameLifecycleError("Healing battlefield_state is invalid.")
    return battlefield


def _append_component_placements(
    *,
    placements: list[ModelPlacement],
    unit_placement: UnitPlacement,
    component_ids: set[str],
    model_ids: set[str],
) -> None:
    if unit_placement.unit_instance_id not in component_ids:
        return
    placements.extend(
        placement
        for placement in unit_placement.model_placements
        if placement.model_instance_id in model_ids
    )


__all__ = (
    "healing_battlefield_state",
    "healing_opposing_player_id",
    "healing_phase_start_model_ids",
    "healing_rules_unit_placements",
)
