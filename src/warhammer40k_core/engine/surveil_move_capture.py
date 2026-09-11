from __future__ import annotations

from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.mission_action_policies import primary_mission_state_rule_for_id
from warhammer40k_core.engine.move_completion_geometry import completed_move_model_placements
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_destruction_evidence import (
    rules_unit_objective_proximity_witness_from_placements,
)
from warhammer40k_core.engine.primary_marker_history import primary_marker_was_active_at_event
from warhammer40k_core.engine.primary_mission_marker_integrity import (
    SURVEIL_MOVE_COMPLETION_EVENT_TYPES,
)
from warhammer40k_core.engine.rules_units import current_rules_unit_views_for_identity
from warhammer40k_core.engine.sequencing import (
    SequencingParticipant,
    SequencingRequirement,
    SequencingRuleOrigin,
)
from warhammer40k_core.engine.unit_move_completed_hooks import UnitMoveCompletedContext


def surveil_participants_at_trigger(
    context: UnitMoveCompletedContext,
) -> tuple[SequencingParticipant, ...]:
    state, decisions = context.state, context.decisions
    if decisions is None:
        raise GameLifecycleError("Surveil capture authority requires its decisions.")
    descriptor = primary_mission_state_rule_for_id("surveil-remove-operation-markers-after-move")
    if (
        state.mission_setup is None
        or state.mission_setup.primary_mission_id_for_player(context.triggering_player_id)
        != descriptor.primary_mission_id
    ):
        return ()
    sources = tuple(
        event for event in decisions.event_log.records if event.event_id == context.trigger_event_id
    )
    if len(sources) != 1:
        raise GameLifecycleError("Surveil capture authority requires its source move.")
    event = sources[0]
    if event.event_type not in SURVEIL_MOVE_COMPLETION_EVENT_TYPES:
        return ()
    views = current_rules_unit_views_for_identity(
        state=state, unit_instance_id=context.triggering_unit_instance_id
    )
    if {view.owner_player_id for view in views} != {context.triggering_player_id}:
        raise GameLifecycleError("Surveil captured mover ownership drift.")
    mover_id = (
        context.triggering_unit_instance_id
        if event.event_type == "fight_movement_completed" or len(views) != 1
        else views[0].unit_instance_id
    )
    markers = tuple(
        marker
        for marker in state.primary_mission_progress_state.markers
        if marker.marker_kind == "operation"
        and marker.owner_player_id != context.triggering_player_id
        and primary_marker_was_active_at_event(
            marker=marker, event_id=event.event_id, event_records=decisions.event_log.records
        )
    )
    if not markers:
        return ()
    placements = completed_move_model_placements(state=state, event=event)
    if not placements:
        return ()
    witness = rules_unit_objective_proximity_witness_from_placements(
        state=state, rules_unit_instance_id=mover_id, model_placements=placements
    )
    marker_ids = tuple(
        marker.marker_id
        for marker in markers
        if marker.objective_marker_id in witness.objective_marker_ids
    )
    if not marker_ids:
        return ()
    return (
        SequencingParticipant(
            participant_id=f"surveil-marker-removal:{event.event_id}:{mover_id}",
            player_id=context.triggering_player_id,
            source_rule_id=descriptor.source_id,
            requirement=SequencingRequirement.MANDATORY,
            origin=SequencingRuleOrigin.MISSION,
            payload=validate_json_value(
                {
                    "trigger_event_id": event.event_id,
                    "moving_rules_unit_instance_id": mover_id,
                    "objective_marker_ids": list(witness.objective_marker_ids),
                    "objective_proximity_witness": witness.to_payload(),
                    "marker_ids": list(marker_ids),
                }
            ),
        ),
    )
