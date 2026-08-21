from __future__ import annotations

from warhammer40k_core.engine.damage_allocation import destroy_model_by_rule
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.game_state import GameState, GameStatePayload
from warhammer40k_core.engine.primary_destruction_evidence import (
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.primary_historical_events import (
    record_new_primary_turn_start_evidence_events,
    record_new_primary_unit_destruction_events,
    record_primary_battlefield_departure_event,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    record_primary_turn_start_evidence,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    record_primary_destroyed_model_departures,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.scoring import (
    PrimaryUnitDestructionStatePayload,
    SecondaryDestroyedModelStatePayload,
    SecondaryUnitDestructionState,
    SecondaryUnitDestructionStatePayload,
)
from warhammer40k_core.engine.secondary_unit_destruction_tracking import (
    secondary_unit_destruction_id,
)


def record_secondary_destruction_for_fixture(
    state: GameState,
    *,
    destroyed_unit_instance_id: str,
    destroying_player_id: str | None,
    source_id: str,
    event_log: EventLog | None = None,
    expected_started_turn_objective_marker_ids: tuple[str, ...] | None = None,
) -> SecondaryUnitDestructionState:
    """Destroy one real rules unit and return its authenticated Secondary projection."""
    authoritative_events = EventLog() if event_log is None else event_log
    _record_current_turn_start_evidence_if_missing(
        state=state,
        event_log=authoritative_events,
    )
    destroyed_view = rules_unit_view_by_id(
        state=state,
        unit_instance_id=destroyed_unit_instance_id,
    )
    destroyed_model_ids = tuple(
        sorted(model.model_instance_id for model in destroyed_view.alive_models())
    )
    if not destroyed_model_ids:
        raise AssertionError("Secondary destruction fixture requires a surviving target unit.")
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise AssertionError("Secondary destruction fixture requires an active battle phase.")
    destroyed_witness = rules_unit_objective_proximity_witness(
        state=state,
        rules_unit_instance_id=destroyed_view.unit_instance_id,
    )
    resolved_destroying_player_id = (
        destroyed_view.owner_player_id if destroying_player_id is None else destroying_player_id
    )
    attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id=resolved_destroying_player_id,
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=None,
        source_model_instance_id=None,
    )
    departure_ids: list[str] = []
    last_model_destroyed_event_id: str | None = None
    for model_id in destroyed_model_ids:
        event = authoritative_events.append(
            "model_destroyed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": current_phase.value,
                "model_instance_id": model_id,
                "target_unit_instance_id": destroyed_view.unit_instance_id,
                "source_id": source_id,
                "source_rules_unit_objective_proximity_witness": None,
                "destroyed_rules_unit_objective_proximity_witness": (
                    destroyed_witness.to_payload()
                ),
                **attribution.to_payload(),
            },
        )
        occurrence_id = event.event_id
        last_model_destroyed_event_id = event.event_id
        destroy_model_by_rule(state=state, model_instance_id=model_id)
        departures = record_primary_destroyed_model_departures(
            state=state,
            destroyed_model_instance_ids=(model_id,),
            source_id=f"core-rules:primary-unit-destruction-tracking:{occurrence_id}",
            occurrence_id=occurrence_id,
        )
        departure_ids.extend(departure.departure_id for departure in departures)
        for departure in departures:
            record_primary_battlefield_departure_event(
                event_log=authoritative_events,
                departure=departure,
            )
    destruction_ids_before = tuple(
        destruction.destruction_id for destruction in state.primary_unit_destruction_states
    )
    primary = state.record_primary_unit_destruction(
        destruction_attribution=attribution,
        source_model_destroyed_event_id=last_model_destroyed_event_id,
        source_rules_unit_objective_proximity_witness=None,
        source_battlefield_departure_ids=tuple(departure_ids),
        unattributed_cause=None,
        source_mutation_id=None,
        destroyed_unit_instance_id=destroyed_view.unit_instance_id,
        source_id=(
            f"core-rules:primary-unit-destruction-tracking:"
            f"{last_model_destroyed_event_id}:{destroyed_view.unit_instance_id}"
        ),
    )
    record_new_primary_unit_destruction_events(
        state=state,
        event_log=authoritative_events,
        destruction_ids_before=destruction_ids_before,
    )
    matches = tuple(
        destruction
        for destruction in state.secondary_unit_destruction_states
        if destruction.source_primary_destruction_id == primary.destruction_id
    )
    if len(matches) != 1:
        raise AssertionError("Primary destruction did not produce one Secondary projection.")
    recorded = matches[0]
    if (
        expected_started_turn_objective_marker_ids is not None
        and recorded.started_turn_objective_marker_ids
        != tuple(sorted(expected_started_turn_objective_marker_ids))
    ):
        raise AssertionError(
            "Secondary destruction fixture turn-start objective evidence does not match geometry."
        )
    return recorded


def synchronize_secondary_destruction_projection_payload(
    *,
    state_payload: GameStatePayload,
    previous_primary_destruction_id: str,
    primary_destruction_payload: PrimaryUnitDestructionStatePayload,
) -> None:
    """Keep one linked Secondary projection aligned with a tampered Primary payload."""
    projection_index, template = _secondary_projection_payload_linked_to_primary(
        state_payload=state_payload,
        primary_destruction_id=previous_primary_destruction_id,
    )
    state_payload["secondary_unit_destruction_states"][projection_index] = (
        _secondary_projection_payload_from_existing(
            state_payload=state_payload,
            primary_destruction_payload=primary_destruction_payload,
            template=template,
        )
    )


def append_secondary_destruction_projection_payload_from_existing(
    *,
    state_payload: GameStatePayload,
    existing_primary_destruction_id: str,
    primary_destruction_payload: PrimaryUnitDestructionStatePayload,
) -> None:
    """Append a projection for a forged occurrence using one existing row as its template."""
    _template_index, template = _secondary_projection_payload_linked_to_primary(
        state_payload=state_payload,
        primary_destruction_id=existing_primary_destruction_id,
    )
    new_primary_destruction_id = primary_destruction_payload["destruction_id"]
    if any(
        projection["source_primary_destruction_id"] == new_primary_destruction_id
        for projection in state_payload["secondary_unit_destruction_states"]
    ):
        raise AssertionError(
            "Secondary destruction payload append requires a new Primary occurrence."
        )
    state_payload["secondary_unit_destruction_states"].append(
        _secondary_projection_payload_from_existing(
            state_payload=state_payload,
            primary_destruction_payload=primary_destruction_payload,
            template=template,
        )
    )
    state_payload["secondary_unit_destruction_states"].sort(
        key=lambda projection: projection["destruction_id"]
    )


def _secondary_projection_payload_linked_to_primary(
    *,
    state_payload: GameStatePayload,
    primary_destruction_id: str,
) -> tuple[int, SecondaryUnitDestructionStatePayload]:
    matches = tuple(
        (index, projection)
        for index, projection in enumerate(state_payload["secondary_unit_destruction_states"])
        if projection["source_primary_destruction_id"] == primary_destruction_id
    )
    if len(matches) != 1:
        raise AssertionError(
            "Secondary destruction payload synchronization requires one linked projection."
        )
    return matches[0]


def _secondary_projection_payload_from_existing(
    *,
    state_payload: GameStatePayload,
    primary_destruction_payload: PrimaryUnitDestructionStatePayload,
    template: SecondaryUnitDestructionStatePayload,
) -> SecondaryUnitDestructionStatePayload:
    if primary_destruction_payload["game_id"] != state_payload["game_id"]:
        raise AssertionError(
            "Secondary destruction payload synchronization requires matching game identity."
        )

    primary_destruction_id = primary_destruction_payload["destruction_id"]
    return {
        "destruction_id": secondary_unit_destruction_id(
            game_id=primary_destruction_payload["game_id"],
            source_primary_destruction_id=primary_destruction_id,
        ),
        "source_primary_destruction_id": primary_destruction_id,
        "game_id": primary_destruction_payload["game_id"],
        "destroying_player_id": primary_destruction_payload["destroying_player_id"],
        "destroyed_player_id": primary_destruction_payload["destroyed_player_id"],
        "active_player_id": primary_destruction_payload["active_player_id"],
        "battle_round": primary_destruction_payload["battle_round"],
        "phase": primary_destruction_payload["phase"],
        "destroyed_unit_instance_id": primary_destruction_payload["destroyed_unit_instance_id"],
        "destroyed_models": _secondary_destroyed_models_for_primary_payload(
            state_payload=state_payload,
            primary_destruction_payload=primary_destruction_payload,
            template_models=template["destroyed_models"],
        ),
        "started_turn_objective_marker_ids": list(
            primary_destruction_payload["started_turn_objective_marker_ids"]
        ),
        "source_id": primary_destruction_payload["source_id"],
    }


def _secondary_destroyed_models_for_primary_payload(
    *,
    state_payload: GameStatePayload,
    primary_destruction_payload: PrimaryUnitDestructionStatePayload,
    template_models: list[SecondaryDestroyedModelStatePayload],
) -> list[SecondaryDestroyedModelStatePayload]:
    template_by_id = {model["model_instance_id"]: model for model in template_models}
    if len(template_by_id) != len(template_models):
        raise AssertionError("Secondary destruction projection template model IDs are ambiguous.")

    departure_ids = primary_destruction_payload["source_battlefield_departure_ids"]
    if not departure_ids:
        destroyed_model_ids = tuple(sorted(template_by_id))
    else:
        departure_by_id = {
            departure["departure_id"]: departure
            for departure in state_payload["primary_battlefield_departure_states"]
        }
        missing_departure_ids = tuple(
            departure_id for departure_id in departure_ids if departure_id not in departure_by_id
        )
        if missing_departure_ids:
            raise AssertionError(
                "Secondary destruction payload synchronization requires exact departure evidence."
            )
        destroyed_model_ids = tuple(
            sorted(
                {
                    model_id
                    for departure_id in departure_ids
                    for model_id in departure_by_id[departure_id]["removed_model_instance_ids"]
                }
            )
        )
    missing_model_ids = tuple(
        model_id for model_id in destroyed_model_ids if model_id not in template_by_id
    )
    if missing_model_ids:
        raise AssertionError(
            "Secondary destruction departure models left the projection template lineage."
        )
    if not destroyed_model_ids:
        raise AssertionError("Secondary destruction projection requires destroyed models.")
    return [
        {
            "model_instance_id": model_id,
            "starting_wounds": template_by_id[model_id]["starting_wounds"],
        }
        for model_id in destroyed_model_ids
    ]


def _record_current_turn_start_evidence_if_missing(
    *,
    state: GameState,
    event_log: EventLog,
) -> None:
    current_key = (state.active_player_id, state.battle_round)
    if any(
        (snapshot.active_player_id, snapshot.battle_round) == current_key
        for snapshot in state.primary_rules_unit_turn_start_snapshots
    ):
        return
    objective_ids_before = tuple(
        value.state_id for value in state.primary_objective_turn_start_states
    )
    snapshot_ids_before = tuple(
        value.snapshot_id for value in state.primary_rules_unit_turn_start_snapshots
    )
    record_primary_turn_start_evidence(state=state)
    record_new_primary_turn_start_evidence_events(
        state=state,
        event_log=event_log,
        objective_state_ids_before=objective_ids_before,
        snapshot_ids_before=snapshot_ids_before,
    )


__all__ = (
    "append_secondary_destruction_projection_payload_from_existing",
    "record_secondary_destruction_for_fixture",
    "synchronize_secondary_destruction_projection_payload",
)
