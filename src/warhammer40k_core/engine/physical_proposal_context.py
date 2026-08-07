from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, TypedDict

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserves import ReserveState, ReserveStatePayload
from warhammer40k_core.engine.transports import (
    TransportCargoState,
    TransportCargoStatePayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phase import LifecycleStatus

PHYSICAL_PROPOSAL_CONTEXT_VERSION = "physical-proposal-context-v1"


class PhysicalModelContextPayload(TypedDict):
    army_id: str
    unit_instance_id: str
    model_instance_id: str
    is_alive: bool
    base_size: JsonValue
    geometry: JsonValue


class PhysicalProposalContextPayload(TypedDict):
    context_version: str
    battlefield_state: JsonValue
    mission_setup: JsonValue
    models: list[PhysicalModelContextPayload]
    reserve_states: list[ReserveStatePayload]
    transport_cargo_states: list[TransportCargoStatePayload]


def physical_proposal_context_hash(
    *,
    armies: tuple[ArmyDefinition, ...],
    battlefield_state: BattlefieldRuntimeState,
    mission_setup: MissionSetup,
    reserve_states: tuple[ReserveState, ...],
    transport_cargo_states: tuple[TransportCargoState, ...],
) -> str:
    if type(armies) is not tuple or any(type(army) is not ArmyDefinition for army in armies):
        raise GameLifecycleError(
            "Physical proposal context armies must be an ArmyDefinition tuple."
        )
    if type(battlefield_state) is not BattlefieldRuntimeState:
        raise GameLifecycleError("Physical proposal context requires BattlefieldRuntimeState.")
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Physical proposal context requires MissionSetup.")
    if type(reserve_states) is not tuple or any(
        type(reserve_state) is not ReserveState for reserve_state in reserve_states
    ):
        raise GameLifecycleError(
            "Physical proposal context reserve_states must be a ReserveState tuple."
        )
    if type(transport_cargo_states) is not tuple or any(
        type(cargo_state) is not TransportCargoState for cargo_state in transport_cargo_states
    ):
        raise GameLifecycleError(
            "Physical proposal context transport_cargo_states must be a TransportCargoState tuple."
        )
    models = [
        PhysicalModelContextPayload(
            army_id=army.army_id,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            is_alive=model.is_alive,
            base_size=validate_json_value(model.base_size.to_payload()),
            geometry=validate_json_value(model.geometry.to_payload()),
        )
        for army in sorted(armies, key=lambda value: value.army_id)
        for unit in sorted(army.units, key=lambda value: value.unit_instance_id)
        for model in sorted(unit.own_models, key=lambda value: value.model_instance_id)
    ]
    battlefield_payload = validate_json_value(
        {
            "battlefield_id": battlefield_state.battlefield_id,
            "battlefield_width_inches": battlefield_state.battlefield_width_inches,
            "battlefield_depth_inches": battlefield_state.battlefield_depth_inches,
            "terrain_features": [
                _source_backed_rules_geometry(
                    rules_geometry_payload=feature.to_rules_geometry_payload(),
                    source_id=feature.source_id,
                )
                for feature in battlefield_state.terrain_features
            ],
            "placed_armies": [army.to_payload() for army in battlefield_state.placed_armies],
            "removed_model_ids": list(battlefield_state.removed_model_ids),
        }
    )
    mission_payload = validate_json_value(
        {
            "mission_pack_id": mission_setup.mission_pack_id,
            "source_version": mission_setup.source_version,
            "source_id": mission_setup.source_id,
            "mission_pool_entry_id": mission_setup.mission_pool_entry_id,
            "primary_mission_id": mission_setup.primary_mission_id,
            "battlefield_layout_id": mission_setup.battlefield_layout_id,
            "deployment_map_id": mission_setup.deployment_map_id,
            "terrain_layout_id": mission_setup.terrain_layout_id,
            "battlefield_width_inches": mission_setup.battlefield_width_inches,
            "battlefield_depth_inches": mission_setup.battlefield_depth_inches,
            "objective_markers": [
                marker.to_payload() for marker in mission_setup.objective_markers
            ],
            "deployment_zones": [zone.to_payload() for zone in mission_setup.deployment_zones],
            "battlefield_regions": [
                region.to_payload() for region in mission_setup.battlefield_regions
            ],
            "terrain_areas": [area.to_payload() for area in mission_setup.terrain_areas],
            "objective_terrain_areas": [
                area.to_payload() for area in mission_setup.objective_terrain_areas
            ],
            "terrain_features": [
                _source_backed_rules_geometry(
                    rules_geometry_payload=feature.to_rules_geometry_payload(),
                    source_id=feature.source_id,
                )
                for feature in mission_setup.terrain_features
            ],
        }
    )
    payload = PhysicalProposalContextPayload(
        context_version=PHYSICAL_PROPOSAL_CONTEXT_VERSION,
        battlefield_state=validate_json_value(battlefield_payload),
        mission_setup=validate_json_value(mission_payload),
        models=models,
        reserve_states=[
            reserve_state.to_payload()
            for reserve_state in sorted(
                reserve_states,
                key=lambda value: (value.player_id, value.unit_instance_id),
            )
        ],
        transport_cargo_states=[
            cargo_state.to_payload()
            for cargo_state in sorted(
                transport_cargo_states,
                key=lambda value: (value.player_id, value.transport_unit_instance_id),
            )
        ],
    )
    json_payload = validate_json_value(payload)
    return hashlib.sha256(canonical_json(json_payload).encode("utf-8")).hexdigest()


def physical_proposal_context_hash_for_state(state: GameState) -> str:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Physical proposal context requires GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError(
            "Physical proposal context requires authoritative battlefield state."
        )
    if state.mission_setup is None:
        raise GameLifecycleError("Physical proposal context requires mission setup.")
    return physical_proposal_context_hash(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
        mission_setup=state.mission_setup,
        reserve_states=tuple(state.reserve_states),
        transport_cargo_states=tuple(state.transport_cargo_states),
    )


def invalid_physical_proposal_spatial_context_status(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.movement_proposals import (
        MOVEMENT_PROPOSAL_DECISION_TYPE,
        MovementProposalRequest,
    )
    from warhammer40k_core.engine.phase import LifecycleStatus

    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    spatial_validation = proposal_request.spatial_context_validation(
        current_spatial_context_hash=physical_proposal_context_hash_for_state(state)
    )
    if spatial_validation.is_valid:
        return None
    event_type = (
        "movement_proposal_invalid"
        if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
        else "placement_proposal_invalid"
    )
    payload = validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": spatial_validation.status,
            "proposal_validation": validate_json_value(spatial_validation.to_payload()),
        }
    )
    decisions.event_log.append(event_type, payload)
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Physical proposal spatial context is stale.",
        payload=payload,
    )


def _source_backed_rules_geometry(
    *, rules_geometry_payload: object, source_id: str | None
) -> JsonValue:
    payload = validate_json_value(rules_geometry_payload)
    if not isinstance(payload, dict):
        raise GameLifecycleError("Terrain rules geometry payload must be a JSON object.")
    return validate_json_value({**payload, "source_id": source_id})


def validate_physical_proposal_context_hash(field_name: str, value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise GameLifecycleError(f"{field_name} must be a lowercase SHA-256 digest.")
    return value
