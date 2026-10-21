"""Resume the accepted Fall Back witness after its shared hazard damage packet."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import UnitPlacement
from warhammer40k_core.engine.damage_allocation import (
    MortalWoundApplication,
    MortalWoundApplicationPayload,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult, DecisionResultPayload
from warhammer40k_core.engine.desperate_escape_mortal_wounds import (
    CONTINUED,
    pending_escape_movement,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.phases.movement_model import FallBackActionResultPayload
from warhammer40k_core.engine.phases.movement_state import FallBackActionResult
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
    from warhammer40k_core.engine.reaction_queue import ReactionQueue


def resume_escape_movement(
    *,
    state: GameState,
    decisions: DecisionController,
    handler: MovementPhaseHandler,
    reaction_queue: ReactionQueue | None,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.phases.movement_fall_back_embark import _apply_fall_back_result
    from warhammer40k_core.engine.phases.movement_geometry import _ability_index_for_player
    from warhammer40k_core.engine.phases.movement_validation import _ruleset_descriptor_for_handler

    source = pending_escape_movement(state=state, decisions=decisions)
    if source is None:
        raise GameLifecycleError("Desperate Escape has no completed hazard packet to resume.")
    resolution = FallBackActionResult.from_payload(
        cast(FallBackActionResultPayload, _object(source, "fall_back_result"))
    )
    action = DecisionResult.from_payload(
        cast(DecisionResultPayload, _object(source, "action_result"))
    )
    if action.actor_id is None:
        raise GameLifecycleError("Desperate Escape continuation requires its actor.")
    actor_id = action.actor_id
    application = MortalWoundApplication.from_payload(
        cast(MortalWoundApplicationPayload, _object(source, "mortal_application"))
    )
    if application.target_unit_instance_id != resolution.unit_instance_id:
        raise GameLifecycleError("Desperate Escape hazard packet target drift.")
    destroyed_ids = tuple(d.model_instance_id for d in application.applications if d.destroyed)
    attempted = resolution.attempted_placement
    components = (
        (attempted,)
        if isinstance(attempted, UnitPlacement)
        else attempted.component_unit_placements
    )
    starts = tuple(
        component.with_model_placements(
            tuple(
                p.with_pose(resolution.witness.poses_for_model(p.model_instance_id)[0])
                for p in component.model_placements
            )
        )
        for component in components
    )
    before = (
        starts[0]
        if isinstance(attempted, UnitPlacement)
        else RulesUnitPlacement(
            rules_unit_instance_id=attempted.rules_unit_instance_id,
            component_unit_placements=starts,
        )
    )
    resolution = replace(
        resolution,
        movement_payload={
            **resolution.movement_payload,
            "desperate_escape_mortal_application_id": source["application_id"],
        },
    )
    action = replace(
        action,
        payload={
            "movement_phase_action": "fall_back",
            "unit_instance_id": resolution.unit_instance_id,
            "witness": validate_json_value(resolution.witness.to_payload()),
            **resolution.movement_payload,
        },
    )
    decisions.event_log.append(
        CONTINUED,
        {
            "application_id": source["application_id"],
            "movement_proposal_request_id": source["movement_proposal_request_id"],
        },
    )
    return _apply_fall_back_result(
        state=state,
        decisions=decisions,
        result=action,
        destruction_source_result_id=None,
        unit_placement=before,
        fall_back_result=resolution,
        destroyed_model_ids=destroyed_ids,
        mortal_wound_application=application,
        movement_proposal_request_id=cast(str, source["movement_proposal_request_id"]),
        ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
        fall_back_hooks=handler.fall_back_hooks,
        battle_shock_hooks=handler.battle_shock_hooks,
        ability_index=_ability_index_for_player(
            handler.ability_indexes_by_player_id, player_id=actor_id
        ),
        runtime_modifier_registry=handler.runtime_modifier_registry,
        reaction_queue=reaction_queue,
        stratagem_index=handler.stratagem_index,
    )


def _object(source: dict[str, JsonValue], key: str) -> dict[str, JsonValue]:
    value = source.get(key)
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Desperate Escape continuation requires {key}.")
    return value


RETRY_PACKET_KEY = "desperate_escape_completed_packet_id"


def request_escape_survivor_retry(
    *,
    state: GameState,
    decisions: DecisionController,
    movement_proposal_request_id: str,
    application: MortalWoundApplication,
    packet_id: JsonValue,
    result: DecisionResult,
) -> DecisionRequest:
    from warhammer40k_core.engine.phases.movement_action_decisions import (
        _request_movement_proposal_retry,
    )

    if not isinstance(packet_id, str):
        raise GameLifecycleError("Hazard survivor retry requires its completed packet ID.")
    from warhammer40k_core.engine.desperate_escape_mortal_wounds import RESOLVED

    matching = [
        e
        for e in decisions.event_log.records
        if e.event_type == RESOLVED
        and isinstance(e.payload, dict)
        and e.payload.get("application_id") == packet_id
        and e.payload.get("mortal_application") == application.to_payload()
    ]
    if len(matching) != 1:
        raise GameLifecycleError(
            "Hazard survivor retry packet differs from its completion receipt."
        )
    records = [r for r in decisions.records if r.request.request_id == movement_proposal_request_id]
    if len(records) != 1:
        raise GameLifecycleError("Hazard survivor retry lost its accepted proposal.")
    proposal = MovementProposalRequest.from_decision_request_payload(records[0].request.payload)
    proposal = replace(proposal, context={**(proposal.context or {}), RETRY_PACKET_KEY: packet_id})
    return _request_movement_proposal_retry(
        state=state,
        decisions=decisions,
        proposal_request=proposal,
        rejected_result=result,
    )


def completed_escape_retry(
    *,
    state: GameState,
    decisions: DecisionController,
    proposal: MovementProposalRequest,
    resolution: FallBackActionResult,
) -> tuple[FallBackActionResult, MortalWoundApplication] | None:
    from warhammer40k_core.engine.desperate_escape_mortal_wounds import RESOLVED

    packet_id = (proposal.context or {}).get(RETRY_PACKET_KEY)
    if packet_id is None:
        return None
    if not isinstance(packet_id, str):
        raise GameLifecycleError("Hazard survivor retry requires its completed packet ID.")
    sources = [
        e.payload
        for e in decisions.event_log.records
        if e.event_type == RESOLVED
        and isinstance(e.payload, dict)
        and e.payload.get("application_id") == packet_id
    ]
    if len(sources) != 1:
        raise GameLifecycleError("Hazard survivor retry lacks a unique completed packet.")
    source = sources[0]
    original = FallBackActionResult.from_payload(
        cast(FallBackActionResultPayload, _object(source, "fall_back_result"))
    )
    action = DecisionResult.from_payload(
        cast(DecisionResultPayload, _object(source, "action_result"))
    )
    application = MortalWoundApplication.from_payload(
        cast(MortalWoundApplicationPayload, _object(source, "mortal_application"))
    )
    movement = state.movement_phase_state
    if (
        movement is None
        or movement.active_selection is None
        or movement.active_selection.unit_instance_id != original.unit_instance_id
        or proposal.unit_instance_id != original.unit_instance_id
        or proposal.actor_id != action.actor_id
        or proposal.source_decision_request_id != action.request_id
        or proposal.source_decision_result_id != action.result_id
        or resolution.movement_payload.get("fall_back_mode")
        != original.movement_payload.get("fall_back_mode")
        or application.target_unit_instance_id != original.unit_instance_id
    ):
        raise GameLifecycleError("Hazard survivor retry source or selection drift.")
    rolls = {r.requirement.model_instance_id: r for r in original.desperate_escape_rolls}
    if any(r.model_instance_id not in rolls for r in resolution.desperate_escape_requirements):
        raise GameLifecycleError("Hazard survivor retry introduced an untested model.")
    # A new legal witness may change overflight details. Preserve each model's
    # actual die and modifiers; the immutable original packet retains the first witness.
    saved_rolls = tuple(
        replace(rolls[r.model_instance_id], requirement=r)
        for r in resolution.desperate_escape_requirements
    )
    resolution = FallBackActionResult.with_desperate_escape_rolls(
        resolution=resolution,
        desperate_escape_rolls=saved_rolls,
    )
    return replace(
        resolution,
        movement_payload={
            **resolution.movement_payload,
            "desperate_escape_mortal_application_id": packet_id,
        },
    ), application
