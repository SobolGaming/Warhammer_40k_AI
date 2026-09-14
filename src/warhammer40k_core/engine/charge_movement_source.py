"""Canonical Charge actors with explicit physical component ownership."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    UnitPlacement,
)
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    ProposalValidationResult,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.geometry.pathing import PathWitness

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

type ChargePlacement = UnitPlacement | RulesUnitPlacement


def charge_placement_id(placement: ChargePlacement) -> str:
    if isinstance(placement, RulesUnitPlacement):
        return placement.rules_unit_instance_id
    return placement.unit_instance_id


def charge_movement_placement(
    *, scenario: BattlefieldScenario, unit_instance_id: str
) -> ChargePlacement:
    view = rules_unit_view_from_armies(armies=scenario.armies, unit_instance_id=unit_instance_id)
    if view.unit_instance_id != unit_instance_id:
        raise GameLifecycleError("Charge actor must use canonical rules-unit identity.")
    components: list[UnitPlacement] = []
    for component in view.living_components:
        current = scenario.battlefield_state.unit_placement_or_none(component.unit.unit_instance_id)
        if current is None:
            raise GameLifecycleError("Charge requires every living component on the battlefield.")
        living = {model.model_instance_id for model in component.unit.own_models if model.is_alive}
        placement = current.with_model_placements(
            tuple(model for model in current.model_placements if model.model_instance_id in living)
        )
        if {model.model_instance_id for model in placement.model_placements} != living:
            raise GameLifecycleError("Charge living-model placement inventory drifted.")
        components.append(placement)
    if not components:
        raise GameLifecycleError("Charge requires living movable models.")
    grouped = RulesUnitPlacement(
        rules_unit_instance_id=view.unit_instance_id, component_unit_placements=tuple(components)
    )
    grouped.validate_for_view(view)
    return grouped if view.is_attached_rules_unit else components[0]


def charge_placement_components(placement: ChargePlacement) -> tuple[UnitPlacement, ...]:
    if isinstance(placement, RulesUnitPlacement):
        return placement.component_unit_placements
    return (placement,)


def charge_attempted_placement(before: ChargePlacement, witness: PathWitness) -> ChargePlacement:
    components = tuple(
        component.with_model_placements(
            tuple(
                model.with_pose(witness.final_pose_for_model(model.model_instance_id))
                for model in component.model_placements
            )
        )
        for component in charge_placement_components(before)
    )
    if isinstance(before, RulesUnitPlacement):
        return RulesUnitPlacement(
            rules_unit_instance_id=before.rules_unit_instance_id,
            component_unit_placements=components,
        )
    return components[0]


def battlefield_with_charge_placement(
    battlefield: BattlefieldRuntimeState,
    placement: ChargePlacement,
) -> BattlefieldRuntimeState:
    """Construct every component change before the engine commits the returned state."""
    result = battlefield
    for component in charge_placement_components(placement):
        current = battlefield.unit_placement_by_id(component.unit_instance_id)
        endpoints = {model.model_instance_id: model for model in component.model_placements}
        if not set(endpoints) <= {model.model_instance_id for model in current.model_placements}:
            raise GameLifecycleError("Charge cannot add models during movement.")
        result = result.with_unit_placement(
            current.with_model_placements(
                tuple(
                    endpoints.get(model.model_instance_id, model)
                    for model in current.model_placements
                )
            )
        )
    return result


def validate_charge_witness_for_proposal(
    *,
    state: GameState,
    request: MovementProposalRequest,
    witness: PathWitness | None,
) -> ProposalValidationResult | None:
    """Reject stale paths before any Charge consumer records a decision."""
    if witness is None:
        return None
    placement = charge_movement_placement(
        scenario=battlefield_scenario_for_state(state=state),
        unit_instance_id=request.unit_instance_id,
    )
    if witness.model_ids() != tuple(
        sorted(model.model_instance_id for model in placement.model_placements)
    ):
        return ProposalValidationResult.invalid(
            proposal_request_id=request.request_id,
            proposal_kind=request.proposal_kind,
            violation_code="charge_witness_unit_drift",
            message="Charge Move witness model IDs do not match the selected rules unit.",
            field="witness",
        )
    if any(
        witness.poses_for_model(model.model_instance_id)[0] != model.pose
        for model in placement.model_placements
    ):
        return ProposalValidationResult.invalid(
            proposal_request_id=request.request_id,
            proposal_kind=request.proposal_kind,
            violation_code="charge_witness_start_drift",
            message="Charge Move witness does not start at the current model pose.",
            field="witness",
        )
    return None
