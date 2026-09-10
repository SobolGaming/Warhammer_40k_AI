"""Authenticate pending 15.07 choices against their existing decision/use provenance."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.movement_proposals import (
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rapid_ingress_eligibility import rapid_ingress_target_error
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.stratagems_model import (
    CORE_RAPID_INGRESS_HANDLER_ID,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    StratagemTargetProposal,
    StratagemTargetProposalPayload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry


def rapid_ingress_placement_error(
    *, state: GameState, proposal: MovementProposalRequest
) -> str | None:
    context = proposal.context or {}
    uses = tuple(
        use
        for use in state.stratagem_use_records
        if use.request_id == proposal.source_decision_request_id
        and use.result_id == proposal.source_decision_result_id
    )
    rapid_uses = tuple(use for use in uses if use.handler_id == CORE_RAPID_INGRESS_HANDLER_ID)
    if not rapid_uses and context.get("stratagem_handler_id") != CORE_RAPID_INGRESS_HANDLER_ID:
        return None
    if len(rapid_uses) != 1:
        return "rapid_ingress_origin_drift"
    use = rapid_uses[0]
    if (
        use.battle_round != state.battle_round
        or use.phase is not state.current_battle_phase
        or use.active_player_id != state.active_player_id
        or proposal.game_id != state.game_id
        or proposal.battle_round != state.battle_round
        or proposal.phase != use.phase.value
        or proposal.actor_id != use.player_id
        or proposal.unit_instance_id != use.target_binding.target_unit_instance_id
    ):
        return "rapid_ingress_origin_drift"
    error = rapid_ingress_target_error(
        state=state, player_id=use.player_id, unit_instance_id=proposal.unit_instance_id
    )
    if error is not None:
        return error
    reserve = state.reserve_state_for_unit(proposal.unit_instance_id)
    if reserve is None:
        raise GameLifecycleError("Eligible Rapid Ingress target lost its reserve state.")
    unit = rules_unit_view_by_id(state=state, unit_instance_id=proposal.unit_instance_id)
    expected = {
        "stratagem_handler_id": CORE_RAPID_INGRESS_HANDLER_ID,
        "stratagem_use": use.to_payload(),
        "reserve_state": reserve.to_payload(),
        "component_unit_instance_ids": [
            component.unit.unit_instance_id for component in unit.living_components
        ],
        "model_instance_ids": sorted(model.model_instance_id for model in unit.alive_models()),
    }
    if context != expected:
        return "rapid_ingress_origin_drift"
    return None


def _has_rapid_ingress_identity(payload: JsonValue) -> bool:
    if not isinstance(payload, dict):
        return False
    record = payload.get("catalog_record")
    if isinstance(record, dict):
        definition = record.get("definition")
        if (
            isinstance(definition, dict)
            and definition.get("handler_id") == CORE_RAPID_INGRESS_HANDLER_ID
        ):
            return True
    context = payload.get("context")
    if isinstance(context, dict):
        use = context.get("stratagem_use")
        return context.get("stratagem_handler_id") == CORE_RAPID_INGRESS_HANDLER_ID or (
            isinstance(use, dict) and use.get("handler_id") == CORE_RAPID_INGRESS_HANDLER_ID
        )
    return False


def _is_rapid_request_payload(payload: JsonValue) -> bool:
    if not isinstance(payload, dict):
        return False
    body = payload.get("payload")
    if isinstance(body, dict) and _has_rapid_ingress_identity(body.get("proposal_request")):
        return True
    options = payload.get("options")
    return isinstance(options, list) and any(
        isinstance(option, dict) and _has_rapid_ingress_identity(option.get("payload"))
        for option in options
    )


def validate_pending_rapid_ingress_authority(
    *,
    state: GameState,
    pending_request: DecisionRequest | None,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry | None,
) -> None:
    if pending_request is None:
        return
    requested = tuple(
        event
        for event in event_records
        if event.event_type == "decision_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("request_id") == pending_request.request_id
    )
    if not _is_rapid_request_payload(cast(JsonValue, pending_request.to_payload())) and not any(
        _is_rapid_request_payload(event.payload) for event in requested
    ):
        return
    if len(requested) != 1 or requested[0].payload != pending_request.to_payload():
        raise GameLifecycleError("Pending Rapid Ingress request origin drift.")
    from warhammer40k_core.engine.primary_reserve_arrival_integrity import (
        validate_primary_reserve_arrival_ingress_use_authority,
    )
    from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_core_stratagem_index
    from warhammer40k_core.engine.stratagems_requests import (
        _parameterized_stratagem_unavailable_reason,  # pyright: ignore[reportPrivateUsage]
    )

    core = next(
        record
        for record in eleventh_edition_core_stratagem_index().all_records()
        if record.definition.handler_id == CORE_RAPID_INGRESS_HANDLER_ID
    )
    if pending_request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        payload = pending_request.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Pending Rapid Ingress target payload is malformed.")
        target = StratagemTargetProposal.from_payload(
            cast(StratagemTargetProposalPayload, payload["proposal_request"])
        )
        if target.catalog_record != core or target.target_binding is not None:
            raise GameLifecycleError("Pending Rapid Ingress target source drift.")
        error = _parameterized_stratagem_unavailable_reason(
            state=state,
            record=core,
            context=target.context,
            stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
            require_legal_affordable_target=False,
        )
        if error is not None:
            raise GameLifecycleError(f"Pending Rapid Ingress target is ineligible: {error}.")
    elif pending_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE:
        proposal = MovementProposalRequest.from_decision_request_payload(pending_request.payload)
        error = rapid_ingress_placement_error(state=state, proposal=proposal)
        if error is not None:
            raise GameLifecycleError(f"Pending Rapid Ingress placement is ineligible: {error}.")
        uses = tuple(
            use
            for use in state.stratagem_use_records
            if use.request_id == proposal.source_decision_request_id
            and use.result_id == proposal.source_decision_result_id
        )
        if len(uses) != 1 or uses[0].handler_id != CORE_RAPID_INGRESS_HANDLER_ID:
            raise GameLifecycleError("Pending Rapid Ingress placement use origin drift.")
        event_indices = {event.event_id: index for index, event in enumerate(event_records)}
        validate_primary_reserve_arrival_ingress_use_authority(
            state=state,
            use=uses[0],
            proposal_request=proposal,
            event_records=event_records,
            decision_records=decision_records,
            event_index_by_id=event_indices,
            placement_request_order=event_indices[requested[0].event_id],
            stratagem_indexes_by_player_id=None,
        )
