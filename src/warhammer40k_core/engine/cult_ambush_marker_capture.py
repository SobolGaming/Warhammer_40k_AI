from __future__ import annotations

# Historical qualification shares the source owner's placement and distance validators.
# pyright: reportPrivateUsage=false
from dataclasses import replace

from warhammer40k_core.engine.cult_ambush import SOURCE_RULE_ID, CultAmbushMarker
from warhammer40k_core.engine.cult_ambush_marker_removal import (
    _marker_placement_event_evidence,
    _rules_unit_is_within_marker_removal_distance,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.fight_rules_unit_movement_types import (
    rules_unit_views_for_completed_move_event,
)
from warhammer40k_core.engine.move_completion_geometry import completed_move_model_placements
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.unit_move_completed_hooks import UnitMoveCompletedContext


def cult_marker_participants_at_trigger(
    context: UnitMoveCompletedContext,
) -> tuple[SequencingParticipant, ...]:
    state, decisions = context.state, context.decisions
    if decisions is None:
        raise GameLifecycleError("Cult marker capture authority requires decisions.")
    sources = tuple(
        (index, event)
        for index, event in enumerate(decisions.event_log.records)
        if event.event_id == context.trigger_event_id
    )
    if len(sources) != 1:
        raise GameLifecycleError("Cult marker capture authority requires its source move.")
    source_index, event = sources[0]
    markers = {
        marker_id: marker
        for marker_id, (index, marker) in _marker_placement_event_evidence(
            state=state, decisions=decisions
        ).items()
        if index < source_index and marker.player_id != context.triggering_player_id
    }
    for prior in decisions.event_log.records[:source_index]:
        payload = prior.payload
        if not isinstance(payload, dict):
            continue
        marker_id: object
        if prior.event_type == "genestealer_cults_cult_ambush_marker_removed":
            raw = payload.get("marker")
            if not isinstance(raw, dict):
                raise GameLifecycleError("Cult marker removal history requires its marker.")
            marker_id = raw.get("marker_id")
        elif prior.event_type in {
            "genestealer_cults_cult_ambush_unit_arrived",
            "genestealer_cults_cult_ambush_marker_ingress_declined",
        }:
            marker_id = payload.get("marker_id")
        else:
            continue
        if type(marker_id) is not str:
            raise GameLifecycleError("Cult marker history requires its marker identity.")
        if marker_id not in markers:
            continue
        if prior.event_type == "genestealer_cults_cult_ambush_marker_ingress_declined":
            markers[marker_id] = replace(markers[marker_id], ingress_window_closed=True)
        else:
            del markers[marker_id]
    if not markers:
        return ()
    views = rules_unit_views_for_completed_move_event(
        state=state,
        event_type=event.event_type,
        unit_instance_id=context.triggering_unit_instance_id,
    )
    if {view.owner_player_id for view in views} != {context.triggering_player_id}:
        raise GameLifecycleError("Cult captured mover ownership drift.")
    placements = completed_move_model_placements(state=state, event=event)
    physical_components = {row.unit_instance_id for row in placements}
    if any(
        "AIRCRAFT" in (*component.unit.keywords, *component.unit.faction_keywords)
        for view in views
        for component in view.components
        if component.unit.unit_instance_id in physical_components
    ):
        return ()
    eligible: dict[str, list[CultAmbushMarker]] = {}
    for marker in markers.values():
        if _rules_unit_is_within_marker_removal_distance(
            state=state, marker=marker, rules_units=views, placements=placements
        ):
            eligible.setdefault(marker.player_id, []).append(marker)
    return tuple(
        SequencingParticipant(
            participant_id=f"cult-marker-removal:{event.event_id}:{player_id}",
            player_id=player_id,
            source_rule_id=SOURCE_RULE_ID,
            requirement=SequencingRequirement.MANDATORY,
            payload=validate_json_value(
                {
                    "trigger_event_id": event.event_id,
                    "trigger_event_type": event.event_type,
                    "moving_unit_instance_id": context.triggering_unit_instance_id,
                    "markers": [marker.to_payload() for marker in owned_markers],
                }
            ),
        )
        for player_id, owned_markers in sorted(eligible.items())
    )
