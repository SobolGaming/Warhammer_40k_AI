from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Final, cast

from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.mission_action_policies import (
    primary_mission_state_rule_for_id,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_destruction_evidence import (
    RulesUnitObjectiveProximityWitness,
)
from warhammer40k_core.engine.primary_mission_state import (
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    PrimaryMissionProgressState,
)
from warhammer40k_core.engine.rules_units import (
    current_rules_unit_views_for_identity,
    rules_unit_identities_share_lineage,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


SURVEIL_MOVE_COMPLETION_EVENT_TYPES: Final = frozenset(
    {
        "catalog_setup_reactive_charge_move_completed",
        "charge_move_completed",
        "fight_movement_completed",
        "heroic_intervention_charge_move_completed",
        "movement_activation_completed",
        "triggered_movement_resolved",
    }
)
SURVEIL_MOVE_PROCESSED_EVENT: Final = "primary_surveil_move_marker_removal_resolved"
_SURVEIL_STATE_RULE_ID: Final = "surveil-remove-operation-markers-after-move"
_OPERATION_MARKER_KIND: Final = "operation"
_PROCESSED_EVENT_KEYS: Final = frozenset(
    {
        "game_id",
        "battle_round",
        "active_player_id",
        "phase",
        "player_id",
        "moving_rules_unit_instance_id",
        "moving_rules_unit_objective_proximity_witness",
        "objective_marker_ids",
        "removed_primary_mission_markers",
        "trigger_event_id",
        "trigger_event_type",
        "source_id",
    }
)


def surveil_move_event_unit_id(payload: Mapping[str, JsonValue]) -> str | None:
    for key in ("unit_instance_id", "target_unit_instance_id"):
        value = payload.get(key)
        if type(value) is str:
            return value
    return None


def validate_surveil_marker_removal_events(
    *,
    state: GameState,
    progress: PrimaryMissionProgressState,
    event_records: tuple[EventRecord, ...],
) -> dict[str, int]:
    """Authenticate Surveil move triggers and their exact marker tombstone sets."""

    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Surveil marker integrity requires GameState.")
    if type(progress) is not PrimaryMissionProgressState:
        raise GameLifecycleError("Surveil marker integrity requires mission progress state.")
    if type(event_records) is not tuple or any(
        type(record) is not EventRecord for record in event_records
    ):
        raise GameLifecycleError("Surveil marker integrity requires EventRecords.")
    event_by_id = {record.event_id: record for record in event_records}
    if len(event_by_id) != len(event_records):
        raise GameLifecycleError("Surveil marker integrity requires unique event IDs.")
    event_index_by_id = {record.event_id: index for index, record in enumerate(event_records)}
    mission_setup = state.mission_setup
    if mission_setup is None:
        if any(record.event_type == SURVEIL_MOVE_PROCESSED_EVENT for record in event_records):
            raise GameLifecycleError("Surveil marker events require MissionSetup.")
        return {}
    descriptor = primary_mission_state_rule_for_id(_SURVEIL_STATE_RULE_ID)
    objective_ids = frozenset(
        marker.objective_marker_id for marker in mission_setup.objective_markers
    )
    processed_trigger_ids: set[str] = set()
    processed_index_by_marker_id: dict[str, int] = {}
    for processed_index, processed in enumerate(event_records):
        if processed.event_type != SURVEIL_MOVE_PROCESSED_EVENT:
            continue
        payload = _event_payload(processed, label="Surveil processed event")
        if frozenset(payload) != _PROCESSED_EVENT_KEYS:
            raise GameLifecycleError("Surveil processed event shape drifted.")
        trigger_id = _string(payload.get("trigger_event_id"), label="trigger_event_id")
        if trigger_id in processed_trigger_ids:
            raise GameLifecycleError("Surveil move trigger was processed more than once.")
        processed_trigger_ids.add(trigger_id)
        trigger = event_by_id.get(trigger_id)
        if trigger is None:
            raise GameLifecycleError("Surveil processed event trigger is unknown.")
        if event_index_by_id[trigger_id] >= processed_index:
            raise GameLifecycleError("Surveil processed event predates its trigger.")
        _validate_trigger_context(
            state=state,
            descriptor_primary_mission_id=descriptor.primary_mission_id,
            trigger=trigger,
            processed_payload=payload,
        )
        proximity_witness = RulesUnitObjectiveProximityWitness.from_payload(
            payload.get("moving_rules_unit_objective_proximity_witness")
        )
        _validate_proximity_witness(
            state=state,
            witness=proximity_witness,
            player_id=cast(str, payload["player_id"]),
            moving_unit_id=cast(str, payload["moving_rules_unit_instance_id"]),
        )
        row_objective_ids = _string_list(
            payload.get("objective_marker_ids"),
            label="objective_marker_ids",
        )
        if row_objective_ids != proximity_witness.objective_marker_ids or not set(
            row_objective_ids
        ).issubset(objective_ids):
            raise GameLifecycleError("Surveil processed objective identities drifted.")
        if payload.get("source_id") != descriptor.source_id:
            raise GameLifecycleError("Surveil processed source identity drifted.")
        player_id = cast(str, payload["player_id"])
        expected_markers = _eligible_markers_at_trigger(
            progress=progress,
            player_id=player_id,
            objective_ids=frozenset(row_objective_ids),
            trigger=trigger,
            processed_payload=payload,
            source_id=descriptor.source_id,
            event_index_by_id=event_index_by_id,
        )
        raw_removed = _payload_list(
            payload.get("removed_primary_mission_markers"),
            label="removed_primary_mission_markers",
        )
        removed = tuple(PrimaryMissionMarkerState.from_payload(raw) for raw in raw_removed)
        if removed != expected_markers:
            raise GameLifecycleError("Surveil processed marker-removal set drifted.")
        for marker in removed:
            if marker.marker_id in processed_index_by_marker_id:
                raise GameLifecycleError("Surveil marker was processed more than once.")
            processed_index_by_marker_id[marker.marker_id] = processed_index
    return processed_index_by_marker_id


def _validate_trigger_context(
    *,
    state: GameState,
    descriptor_primary_mission_id: str,
    trigger: EventRecord,
    processed_payload: dict[str, JsonValue],
) -> None:
    trigger_type = _string(
        processed_payload.get("trigger_event_type"),
        label="trigger_event_type",
    )
    if (
        trigger.event_type != trigger_type
        or trigger_type not in SURVEIL_MOVE_COMPLETION_EVENT_TYPES
    ):
        raise GameLifecycleError("Surveil marker removal trigger type is invalid.")
    trigger_payload = _event_payload(trigger, label="Surveil move trigger")
    game_id = _string(processed_payload.get("game_id"), label="game_id")
    battle_round = processed_payload.get("battle_round")
    phase = _string(processed_payload.get("phase"), label="phase")
    active_player_id = _string(
        processed_payload.get("active_player_id"),
        label="active_player_id",
    )
    player_id = _string(processed_payload.get("player_id"), label="player_id")
    moving_unit_id = _string(
        processed_payload.get("moving_rules_unit_instance_id"),
        label="moving_rules_unit_instance_id",
    )
    if (
        game_id != state.game_id
        or type(battle_round) is not int
        or battle_round < 1
        or phase not in {battle_phase.value for battle_phase in BattlePhase}
        or active_player_id not in state.player_ids
        or player_id not in state.player_ids
        or trigger_payload.get("game_id") != game_id
        or trigger_payload.get("battle_round") != battle_round
        or trigger_payload.get("phase") != phase
    ):
        raise GameLifecycleError("Surveil processed event battle context drifted.")
    trigger_active_player_id = trigger_payload.get("active_player_id")
    if trigger_active_player_id is not None and trigger_active_player_id != active_player_id:
        raise GameLifecycleError("Surveil move trigger active player drifted.")
    if (
        trigger_type == "movement_activation_completed"
        and trigger_payload.get("movement_phase_action") == "remain_stationary"
    ):
        raise GameLifecycleError("Remain Stationary cannot trigger Surveil marker removal.")
    trigger_unit_id = surveil_move_event_unit_id(trigger_payload)
    if trigger_unit_id is None:
        raise GameLifecycleError("Surveil move trigger lacks a moving unit identity.")
    if not rules_unit_identities_share_lineage(
        state=state,
        first_unit_instance_id=trigger_unit_id,
        second_unit_instance_id=moving_unit_id,
    ):
        raise GameLifecycleError("Surveil processed mover drifted from its trigger.")
    trigger_owner = _rules_unit_owner(state=state, unit_instance_id=trigger_unit_id)
    moving_owner = _rules_unit_owner(state=state, unit_instance_id=moving_unit_id)
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise GameLifecycleError("Surveil marker events require MissionSetup.")
    if (
        trigger_owner != player_id
        or moving_owner != player_id
        or mission_setup.primary_mission_id_for_player(player_id) != descriptor_primary_mission_id
    ):
        raise GameLifecycleError("Surveil processed mover ownership drifted.")


def _eligible_markers_at_trigger(
    *,
    progress: PrimaryMissionProgressState,
    player_id: str,
    objective_ids: frozenset[str],
    trigger: EventRecord,
    processed_payload: dict[str, JsonValue],
    source_id: str,
    event_index_by_id: dict[str, int],
) -> tuple[PrimaryMissionMarkerState, ...]:
    trigger_index = event_index_by_id[trigger.event_id]
    candidates: list[PrimaryMissionMarkerState] = []
    for marker in progress.markers:
        creation_index = event_index_by_id.get(marker.source_event_id)
        if creation_index is None:
            raise GameLifecycleError("Surveil marker creation event is unknown.")
        removal_index = (
            None
            if marker.removal_event_id is None
            else event_index_by_id.get(marker.removal_event_id)
        )
        if marker.removal_event_id is not None and removal_index is None:
            raise GameLifecycleError("Surveil marker removal event is unknown.")
        if creation_index >= trigger_index or (
            removal_index is not None and removal_index < trigger_index
        ):
            continue
        if (
            marker.marker_kind != _OPERATION_MARKER_KIND
            or marker.owner_player_id == player_id
            or marker.objective_marker_id not in objective_ids
        ):
            continue
        if (
            marker.status is not PrimaryMissionMarkerStatus.REMOVED
            or marker.removal_event_id != trigger.event_id
            or marker.removal_source_id != source_id
            or marker.removal_action_id is not None
            or marker.removal_result_id is not None
            or marker.removed_battle_round != processed_payload.get("battle_round")
            or marker.removed_phase != processed_payload.get("phase")
            or marker.removed_active_player_id != processed_payload.get("active_player_id")
        ):
            raise GameLifecycleError(
                "Surveil eligible marker was not tombstoned by its move trigger."
            )
        candidates.append(marker)
    return tuple(candidates)


def _validate_proximity_witness(
    *,
    state: GameState,
    witness: RulesUnitObjectiveProximityWitness,
    player_id: str,
    moving_unit_id: str,
) -> None:
    if witness.rules_unit_instance_id != moving_unit_id:
        raise GameLifecycleError("Surveil objective witness mover identity drifted.")
    views = current_rules_unit_views_for_identity(
        state=state,
        unit_instance_id=moving_unit_id,
    )
    component_ids = tuple(
        sorted(
            {component_id for view in views for component_id in view.component_unit_instance_ids}
        )
    )
    if {view.owner_player_id for view in views} != {
        player_id
    } or witness.component_unit_instance_ids != component_ids:
        raise GameLifecycleError("Surveil objective witness rules-unit identity drifted.")
    model_ids = {
        model.model_instance_id
        for army in state.army_definitions
        if army.player_id == player_id
        for unit in army.units
        if unit.unit_instance_id in component_ids
        for model in unit.own_models
    }
    witnessed_model_ids = {
        model_id
        for marker_witness in witness.objective_marker_witnesses
        for model_id in marker_witness.model_instance_ids
    }
    if not witnessed_model_ids.issubset(model_ids):
        raise GameLifecycleError("Surveil objective witness model ownership drifted.")


def _rules_unit_owner(*, state: GameState, unit_instance_id: str) -> str:
    views = current_rules_unit_views_for_identity(
        state=state,
        unit_instance_id=unit_instance_id,
    )
    owners = {view.owner_player_id for view in views}
    if len(owners) != 1:
        raise GameLifecycleError("Surveil moving rules-unit ownership is ambiguous.")
    return owners.pop()


def _event_payload(record: EventRecord, *, label: str) -> dict[str, JsonValue]:
    if not isinstance(record.payload, dict):
        raise GameLifecycleError(f"{label} payload must be an object.")
    return record.payload


def _payload_list(value: object, *, label: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise GameLifecycleError(f"Surveil {label} must be a list.")
    return cast(list[JsonValue], value)


def _string_list(value: object, *, label: str) -> tuple[str, ...]:
    raw = _payload_list(value, label=label)
    if any(type(item) is not str for item in raw):
        raise GameLifecycleError(f"Surveil {label} must contain strings.")
    return cast(tuple[str, ...], tuple(raw))


def _string(value: object, *, label: str) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Surveil {label} must be a string.")
    return value


__all__ = (
    "SURVEIL_MOVE_COMPLETION_EVENT_TYPES",
    "SURVEIL_MOVE_PROCESSED_EVENT",
    "surveil_move_event_unit_id",
    "validate_surveil_marker_removal_events",
)
