from __future__ import annotations

from collections.abc import Collection

from warhammer40k_core.engine.attack_sequence import (
    is_destroyed_transport_disembark_proposal_request,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE,
)
from warhammer40k_core.engine.catalog_setup_reactive_charge_move import (
    is_catalog_setup_reactive_charge_move_request,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, canonical_json
from warhammer40k_core.engine.fight_activation_units import active_fight_activation_rules_unit
from warhammer40k_core.engine.fight_order import FIGHT_ACTIVATION_DECISION_TYPE
from warhammer40k_core.engine.fight_resolution import (
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    MeleeDeclarationProposalRequest,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.move_completion_effects import (
    SELECT_MOVE_COMPLETION_EFFECT_DECISION_TYPE,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.reaction_queue import (
    REACTION_DECISION_TYPE,
    ReactionQueue,
    ReactionQueueFrame,
    ReactionQueueFramePayload,
)
from warhammer40k_core.engine.sequencing import SEQUENCING_DECISION_TYPE
from warhammer40k_core.engine.stratagems import (
    is_stratagem_placement_proposal_request,
)


def validate_reaction_queue_consistency(
    *,
    state: GameState,
    reaction_queue: ReactionQueue,
    pending_request: DecisionRequest | None,
    reaction_frame_decision_types: Collection[str],
) -> None:
    frames = reaction_queue.frames
    if not frames:
        if pending_request is not None and pending_request.decision_type == REACTION_DECISION_TYPE:
            raise GameLifecycleError("Lifecycle pending reaction decision requires a frame.")
        return
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Lifecycle reaction queue requires battle stage.")
    if state.current_battle_phase is None:
        raise GameLifecycleError("Lifecycle reaction queue requires a current battle phase.")
    if pending_request is None:
        raise GameLifecycleError("Lifecycle reaction queue requires a pending decision.")
    charge = state.charge_phase_state
    charge_active = charge is not None and charge.interruption is not None
    charge_types = {
        "select_charging_unit",
        "select_charge_declaration_grant",
        "select_charge_targets",
        "select_target_replacement",
        # Shared completion hooks finish before the interrupted Charge releases its frame.
        SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE,
        SELECT_MOVE_COMPLETION_EFFECT_DECISION_TYPE,
        SEQUENCING_DECISION_TYPE,
    }
    if (
        pending_request.decision_type not in reaction_frame_decision_types
        and not (charge_active and pending_request.decision_type in charge_types)
        and not _is_interrupted_fight_melee_request(state, pending_request)
        and not _is_interrupted_fight_selection(state, pending_request, frames[-1])
    ):
        raise GameLifecycleError("Lifecycle reaction queue pending decision_type drift.")
    if (
        pending_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
        and not is_stratagem_placement_proposal_request(pending_request)
        and not is_destroyed_transport_disembark_proposal_request(pending_request)
    ):
        raise GameLifecycleError("Lifecycle reaction queue pending placement decision drift.")
    if (
        pending_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
        and not is_catalog_setup_reactive_charge_move_request(pending_request)
        and not charge_active
        and not _is_interrupted_fight_pile_in(state, pending_request)
    ):
        raise GameLifecycleError("Lifecycle reaction queue pending movement decision drift.")
    seen_request_ids: set[str] = set()
    for frame in frames:
        if frame.request_id is None:
            raise GameLifecycleError("Lifecycle reaction queue frame requires request_id.")
        if frame.request_id in seen_request_ids:
            raise GameLifecycleError("Lifecycle reaction queue request_ids must be unique.")
        seen_request_ids.add(frame.request_id)
        if frame.reaction_window.timing_window.game_id != state.game_id:
            raise GameLifecycleError("Lifecycle reaction queue frame game_id drift.")
        if frame.parent_phase is not state.current_battle_phase:
            raise GameLifecycleError("Lifecycle reaction queue frame phase drift.")
    if frames[-1].request_id != pending_request.request_id:
        raise GameLifecycleError("Lifecycle reaction queue active frame request_id drift.")


def _is_interrupted_fight_selection(
    state: GameState, request: DecisionRequest, frame: ReactionQueueFrame
) -> bool:
    fight = state.fight_phase_state
    return (
        request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
        and state.current_battle_phase is BattlePhase.FIGHT
        and fight is not None
        and fight.active_activation is None
        and request.actor_id in frame.reaction_window.eligible_player_ids
        and isinstance(request.payload, dict)
        and isinstance(request.payload.get("interrupt_id"), str)
    )


def _is_interrupted_fight_pile_in(state: GameState, request: DecisionRequest) -> bool:
    fight = state.fight_phase_state
    if state.current_battle_phase is not BattlePhase.FIGHT or fight is None:
        return False
    activation = fight.active_activation
    if activation is None or activation.interrupt_id is None:
        return False
    movement = MovementProposalRequest.from_decision_request_payload(request.payload)
    return (
        movement.proposal_kind is ProposalKind.PILE_IN
        and movement.phase == BattlePhase.FIGHT.value
        and movement.actor_id == request.actor_id == activation.player_id
        and movement.unit_instance_id == activation.unit_instance_id
        and movement.source_decision_request_id == activation.request_id
        and movement.source_decision_result_id == activation.result_id
        and movement.context is not None
        and movement.context.get("fight_movement_timing") == "overrun"
    )


def _is_interrupted_fight_melee_request(state: GameState, request: DecisionRequest) -> bool:
    fight = state.fight_phase_state
    if (
        request.decision_type != SUBMIT_MELEE_DECLARATION_DECISION_TYPE
        or state.current_battle_phase is not BattlePhase.FIGHT
        or fight is None
    ):
        return False
    activation = fight.active_activation
    if (
        activation is None
        or activation.interrupt_id is None
        or request.actor_id != activation.player_id
    ):
        return False
    proposal = (
        request.payload.get("proposal_request") if isinstance(request.payload, dict) else None
    )
    if not isinstance(proposal, dict) or proposal.get("phase") != BattlePhase.FIGHT.value:
        raise GameLifecycleError("Lifecycle melee proposal_request phase drift.")
    if proposal.get("decision_type") != request.decision_type:
        raise GameLifecycleError("Lifecycle melee proposal_request decision_type drift.")
    melee = MeleeDeclarationProposalRequest.from_decision_request(request)
    rules_unit = active_fight_activation_rules_unit(state=state, activation=activation)
    return (
        rules_unit is not None
        and melee.unit_instance_id == rules_unit.unit_instance_id
        and melee.request_id == request.request_id
        and melee.actor_id == activation.player_id
        and melee.game_id == state.game_id
        and melee.battle_round == state.battle_round
        and melee.active_player_id == fight.active_player_id
        and melee.ruleset_descriptor_hash == state.ruleset_descriptor_hash
        and melee.source_decision_request_id == activation.request_id
        and melee.source_decision_result_id == activation.result_id
    )


def validate_melee_reaction_continuation(
    *,
    request_id: str,
    frames: tuple[ReactionQueueFrame, ...],
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    """Restore the single frame transfer into a pending Fight declaration."""
    events = reversed(event_records)
    handoff: dict[str, JsonValue] | None = None
    source_event: JsonValue = None
    for event in events:
        # Only the submission that issued the pending declaration can transfer its frame.
        if event.event_type == "decision_recorded":
            source_event = event.payload
            break
        if event.event_type == "reaction_window_continued":
            if handoff is not None or not isinstance(event.payload, dict):
                raise GameLifecycleError("Lifecycle melee reaction continuation drift.")
            handoff = event.payload
    if handoff is None:
        if frames:
            raise GameLifecycleError("Lifecycle melee reaction continuation drift.")
        return
    if handoff.get("next_request_id") != request_id:
        raise GameLifecycleError("Lifecycle melee reaction continuation drift.")
    if not frames:
        raise GameLifecycleError("Lifecycle melee reaction continuation requires a frame.")
    frame = frames[-1]
    if frame.request_id != request_id or not _matches_frame_event(
        frame.to_payload(), handoff, request_field="next_request_id"
    ):
        raise GameLifecycleError("Lifecycle melee reaction continuation drift.")

    if not decision_records or not isinstance(source_event, dict):
        raise GameLifecycleError("Lifecycle melee reaction continuation source decision drift.")
    source = decision_records[-1]
    source_payload = source.to_payload()
    canonical_source = canonical_json(source_payload)
    if (
        canonical_json(handoff.get("decision_record")) != canonical_source
        or canonical_json({key: source_event[key] for key in source_payload.keys() & source_event})
        != canonical_source
    ):
        raise GameLifecycleError("Lifecycle melee reaction continuation source decision drift.")

    # Continue replaces the source request's existing frame. Earlier frames in the
    # stack may belong to other windows, but this window may occur only once.
    source_request_id = source.request.request_id
    window_id = frame.reaction_window.timing_window.window_id
    if source_request_id == request_id or any(
        lower.request_id == source_request_id
        or lower.reaction_window.timing_window.window_id == window_id
        for lower in frames[:-1]
    ):
        raise GameLifecycleError("Lifecycle melee reaction continuation frame was not replaced.")

    # Opening or continuing the source set the previous request ID. The handoff
    # must preserve every other field from that assignment.
    source_frame = frame.with_request_id(source_request_id).to_payload()
    for event in events:
        if event.event_type == "reaction_window_opened":
            request_field = "request_id"
        elif event.event_type == "reaction_window_continued":
            request_field = "next_request_id"
        else:
            continue
        payload = event.payload
        if isinstance(payload, dict) and payload.get(request_field) == source_request_id:
            if _matches_frame_event(source_frame, payload, request_field=request_field):
                return
            break
    raise GameLifecycleError("Lifecycle melee reaction continuation source frame drift.")


def _matches_frame_event(
    frame: ReactionQueueFramePayload, event: dict[str, JsonValue], *, request_field: str
) -> bool:
    # Compare all serialized frame fields; the event also carries decision and visibility data.
    fields = frame.keys() - {"request_id"}
    return canonical_json(frame) == canonical_json(
        {"request_id": event.get(request_field)}
        | {key: event[key] for key in fields & event.keys()}
    )
