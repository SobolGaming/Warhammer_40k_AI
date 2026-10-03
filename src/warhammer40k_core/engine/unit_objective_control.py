"""Core 14.02: unit range and a positive-OC model are separate conditions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.engine.objective_control import (
    ObjectiveControlResult,
    model_objective_control_characteristic,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.profile_snapshot import profile_snapshot_from_json
from warhammer40k_core.engine.rules_units import (
    rules_unit_is_battle_shocked,
    rules_unit_view_by_id,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


@dataclass(frozen=True, slots=True)
class UnitObjectiveControl:
    player_id: str
    component_unit_ids: frozenset[str]
    has_positive_objective_control: bool

    def controls(self, result: ObjectiveControlResult) -> bool:
        return (
            result.controlled_by_player_id == self.player_id
            and self.has_positive_objective_control
            and self.within_range(result)
        )

    def within_range(self, result: ObjectiveControlResult) -> bool:
        return any(
            row.player_id == self.player_id and row.unit_instance_id in self.component_unit_ids
            for row in result.contributors
        )


def current_unit_objective_control(
    *,
    state: GameState,
    unit_instance_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> UnitObjectiveControl:
    unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Unit objective control requires battlefield state.")
    shocked = rules_unit_is_battle_shocked(state=state, unit_instance_id=unit.unit_instance_id)
    return UnitObjectiveControl(
        player_id=unit.owner_player_id,
        component_unit_ids=frozenset(unit.component_unit_instance_ids),
        has_positive_objective_control=not shocked
        and any(
            model_objective_control_characteristic(
                model,
                battle_shocked=False,
                state=state,
                unit_instance_id=unit.component_unit_id_for_model(model.model_instance_id),
                runtime_modifier_registry=runtime_modifier_registry,
            ).final
            > 0
            for model in unit.own_models
            if (model.is_alive or model.model_instance_id in unit.retained_model_ids)
            and battlefield.model_placement_or_none(model.model_instance_id) is not None
        ),
    )


def boundary_unit_objective_control(
    *,
    state: GameState,
    record_id: str,
    player_id: str,
    unit_identity_ids: tuple[str, ...],
) -> UnitObjectiveControl:
    """Use the existing immutable all-model OC checkpoint, never later live models."""
    authorities = tuple(
        authority
        for authority in state.objective_control_record_authorities
        if authority.objective_control_record_id == record_id
    )
    if len(authorities) != 1:
        raise GameLifecycleError("Unit objective control requires one boundary authority.")
    checkpoint = authorities[0].boundary_checkpoint
    identities = frozenset(unit_identity_ids)
    models = tuple(
        row
        for row in checkpoint.model_states
        if row.owner_player_id == player_id
        and (
            row.rules_unit_instance_id in identities or row.component_unit_instance_id in identities
        )
    )
    shocked_ids = frozenset(checkpoint.battle_shocked_unit_instance_ids)
    return UnitObjectiveControl(
        player_id=player_id,
        component_unit_ids=frozenset(row.component_unit_instance_id for row in models),
        has_positive_objective_control=any(
            profile_snapshot_from_json(row.resolved_objective_control_json).final > 0
            for row in models
            if row.presence == "battlefield"
            and row.rules_unit_instance_id not in shocked_ids
            and row.component_unit_instance_id not in shocked_ids
        ),
    )
