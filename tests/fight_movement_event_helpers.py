from __future__ import annotations

from typing import cast

from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.battlefield_state import UnitPlacement
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_resolution import FightMovementResolution
from warhammer40k_core.engine.fight_rules_unit_movement_types import (
    FightRulesUnitPlacement,
    RulesUnitFightMovementResolution,
)
from warhammer40k_core.engine.movement_proposals import ProposalKind
from warhammer40k_core.geometry.pathing import PathWitness


def grouped_fight_movement_resolution_payload(
    *,
    rules_unit_instance_id: str,
    before_component_placements: tuple[UnitPlacement, ...],
    attempted_component_placements: tuple[UnitPlacement, ...] | None = None,
) -> dict[str, JsonValue]:
    before = FightRulesUnitPlacement(
        rules_unit_instance_id=rules_unit_instance_id,
        component_unit_placements=before_component_placements,
    )
    attempted = FightRulesUnitPlacement(
        rules_unit_instance_id=rules_unit_instance_id,
        component_unit_placements=(
            before_component_placements
            if attempted_component_placements is None
            else attempted_component_placements
        ),
    )
    resolution = RulesUnitFightMovementResolution(
        unit_instance_id=rules_unit_instance_id,
        proposal_kind=ProposalKind.PILE_IN,
        movement_phase_action="pile_in",
        movement_mode=MovementMode.PILE_IN,
        maximum_distance_inches=3.0,
        before_rules_unit_placement=before,
        attempted_rules_unit_placement=attempted,
        witness=None,
        endpoint_witness={
            "target_unit_instance_ids": [],
            "objective_id": None,
            "moved_model_instance_ids": [],
            "engaged_before_unit_ids": [],
            "engaged_after_unit_ids": [],
        },
        path_validation_results=(),
        terrain_path_legality_results=(),
        coherency_result=None,
        rollback_record=None,
    )
    return cast(dict[str, JsonValue], validate_json_value(resolution.to_payload()))


def standalone_fight_movement_event_evidence(
    *,
    before: UnitPlacement,
    attempted: UnitPlacement,
    proposal_kind: ProposalKind = ProposalKind.PILE_IN,
) -> dict[str, JsonValue]:
    before_by_model_id = {
        placement.model_instance_id: placement for placement in before.model_placements
    }
    if before.unit_instance_id != attempted.unit_instance_id or set(before_by_model_id) != {
        placement.model_instance_id for placement in attempted.model_placements
    }:
        raise AssertionError("Standalone Fight movement fixture placement identity drift.")
    moved_endpoints = tuple(
        (
            placement.model_instance_id,
            before_by_model_id[placement.model_instance_id].pose,
            placement.pose,
        )
        for placement in attempted.model_placements
        if before_by_model_id[placement.model_instance_id].pose != placement.pose
    )
    movement_mode = (
        MovementMode.PILE_IN if proposal_kind is ProposalKind.PILE_IN else MovementMode.CONSOLIDATE
    )
    witness = (
        None if not moved_endpoints else PathWitness.for_straight_line_endpoints(moved_endpoints)
    )
    resolution = FightMovementResolution(
        unit_instance_id=attempted.unit_instance_id,
        proposal_kind=proposal_kind,
        movement_phase_action=proposal_kind.value,
        movement_mode=movement_mode,
        maximum_distance_inches=3.0,
        attempted_placement=attempted,
        witness=witness,
        endpoint_witness={
            "target_unit_instance_ids": [],
            "objective_id": None,
            "moved_model_instance_ids": sorted(
                placement.model_instance_id
                for placement in attempted.model_placements
                if before_by_model_id[placement.model_instance_id].pose != placement.pose
            ),
            "engaged_before_unit_ids": [],
            "engaged_after_unit_ids": [],
        },
        path_validation_results=(),
        terrain_path_legality_results=(),
        coherency_result=None,
        rollback_record=None,
    )
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "proposal_kind": proposal_kind.value,
                "transition_batch": resolution.transition_batch(before=before).to_payload(),
                "resolution": resolution.to_payload(),
                "movement_endpoint_placement": attempted.to_payload(),
            }
        ),
    )
