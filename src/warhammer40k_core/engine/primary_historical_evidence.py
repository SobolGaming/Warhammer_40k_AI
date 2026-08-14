from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine import mission_terrain
from warhammer40k_core.engine.destruction_source_attribution import (
    validate_destruction_source_identity,
)
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
    validate_primary_battlefield_departure_states,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    PrimaryRulesUnitTurnStartSnapshot,
    validate_primary_rules_unit_turn_start_snapshots,
    validate_primary_turn_start_evidence_graph,
    validate_primary_unit_destruction_turn_start_evidence,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    validate_primary_unit_destruction_states,
)
from warhammer40k_core.engine.scoring import PrimaryUnitDestructionState

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def validate_primary_historical_evidence_state(
    state: GameState,
) -> tuple[
    list[PrimaryRulesUnitTurnStartSnapshot],
    list[PrimaryUnitDestructionState],
    list[PrimaryBattlefieldDepartureState],
]:
    """Validate the related Phase 17N Step 3 evidence families as one graph."""
    physical_model_ids_by_unit_id = {
        unit.unit_instance_id: unit.own_model_ids()
        for army in state.army_definitions
        for unit in army.units
    }
    model_ids_by_unit_id = {
        **physical_model_ids_by_unit_id,
        **{
            record.attached_unit_instance_id: tuple(
                sorted(
                    model_id
                    for _component_id, model_ids in (
                        record.starting_model_instance_ids_by_component
                    )
                    for model_id in model_ids
                )
            )
            for record in state.starting_attached_unit_records
        },
    }
    owner_by_unit_id = {
        **{
            unit.unit_instance_id: army.player_id
            for army in state.army_definitions
            for unit in army.units
        },
        **{
            record.attached_unit_instance_id: record.player_id
            for record in state.starting_attached_unit_records
        },
    }
    known_rules_unit_components_by_id = {
        **{unit_id: (unit_id,) for unit_id in physical_model_ids_by_unit_id},
        **{
            record.attached_unit_instance_id: record.component_unit_instance_ids
            for record in state.starting_attached_unit_records
        },
    }
    known_objective_marker_ids = tuple(
        marker.objective_marker_id
        for marker in (() if state.mission_setup is None else state.mission_setup.objective_markers)
    )
    position_snapshots = validate_primary_rules_unit_turn_start_snapshots(
        state.primary_rules_unit_turn_start_snapshots,
        game_id=state.game_id,
        player_ids=state.player_ids,
        known_component_model_ids_by_unit=tuple(physical_model_ids_by_unit_id.items()),
        known_attached_component_ids_by_rules_unit=tuple(
            (
                record.attached_unit_instance_id,
                record.component_unit_instance_ids,
            )
            for record in state.starting_attached_unit_records
        ),
        known_logical_terrain_area_ids=tuple(
            area.logical_terrain_area_id
            for area in (
                ()
                if state.mission_setup is None
                else mission_terrain.mission_logical_terrain_areas(state.mission_setup)
            )
        ),
        known_objective_marker_ids=known_objective_marker_ids,
    )
    validate_primary_turn_start_evidence_graph(
        objective_states=state.primary_objective_turn_start_states,
        position_snapshots=position_snapshots,
    )
    destruction_states = validate_primary_unit_destruction_states(
        state.primary_unit_destruction_states,
        game_id=state.game_id,
        player_ids=state.player_ids,
        owner_by_unit_id=owner_by_unit_id,
        model_ids_by_unit_id=model_ids_by_unit_id,
        known_rules_unit_components_by_id=known_rules_unit_components_by_id,
        known_objective_marker_ids=known_objective_marker_ids,
    )
    for destruction in destruction_states:
        attribution = destruction.destruction_attribution
        if attribution is None:
            continue
        validate_destruction_source_identity(
            state=state,
            source_rules_unit_instance_id=attribution.source_rules_unit_instance_id,
            source_model_instance_id=attribution.source_model_instance_id,
            destroying_player_id=attribution.destroying_player_id,
        )
    validate_primary_unit_destruction_turn_start_evidence(
        destruction_states=destruction_states,
        position_snapshots=position_snapshots,
        known_rules_unit_components_by_id=known_rules_unit_components_by_id,
    )
    departure_states = validate_primary_battlefield_departure_states(
        state.primary_battlefield_departure_states,
        game_id=state.game_id,
        player_ids=state.player_ids,
        owner_by_unit_id=owner_by_unit_id,
        model_ids_by_unit_id=physical_model_ids_by_unit_id,
        known_rules_unit_components_by_id=known_rules_unit_components_by_id,
    )
    return position_snapshots, destruction_states, departure_states


__all__ = ("validate_primary_historical_evidence_state",)
