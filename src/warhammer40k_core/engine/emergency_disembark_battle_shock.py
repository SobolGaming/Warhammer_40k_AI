"""18.05 direct Battle-shock from the accepted Emergency setup occurrence.

The existing unit_disembarked event is the source authority. Ordinary/attached
producers share the completion recorder and the shared Battle-shock mutation;
no test, roll, decision type or separate status lifetime is invented here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battle_shock import BattleShockedUnitState
from warhammer40k_core.engine.battle_shock_state import apply_direct_battle_shock_state
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.movement_proposals import (
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
    ProposalKind,
)
from warhammer40k_core.engine.mutation_decision_authority import validate_mutation_decision_closure
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import current_rules_unit_views_for_canonical_identity
from warhammer40k_core.engine.transport_disembark_state import (
    EMERGENCY_DISEMBARK_RULE_ID,
    DisembarkedUnitState,
    DisembarkedUnitStatePayload,
    DisembarkModeKind,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


def is_emergency_disembark_completion(event: EventRecord) -> bool:
    return (
        event.event_type == "unit_disembarked"
        and isinstance(event.payload, dict)
        and event.payload.get("disembark_mode") == DisembarkModeKind.EMERGENCY_DISEMBARK.value
    )


def _status(event: EventRecord, state: GameState) -> DisembarkedUnitState:
    payload = event.payload
    if not is_emergency_disembark_completion(event) or not isinstance(payload, dict):
        raise GameLifecycleError("Emergency Battle-shock requires its accepted setup event.")
    raw = payload.get("disembarked_unit_state")
    if not isinstance(raw, dict):
        raise GameLifecycleError("Emergency Battle-shock setup status is missing.")
    status = DisembarkedUnitState.from_payload(cast(DisembarkedUnitStatePayload, raw))
    if (
        payload.get("game_id") != state.game_id
        or payload.get("battle_round") != status.battle_round
        or payload.get("active_player_id") != status.turn_player_id
        or payload.get("unit_instance_id") != status.unit_instance_id
        or payload.get("transport_unit_instance_id") != status.transport_unit_instance_id
        or status.disembark_mode is not DisembarkModeKind.EMERGENCY_DISEMBARK
        or status.source_rule_id != EMERGENCY_DISEMBARK_RULE_ID
        or status.battle_shocked_until != "until_cleared"
        or type(payload.get("result_id")) is not str
        or not payload["result_id"]
    ):
        raise GameLifecycleError("Emergency Battle-shock source occurrence drift.")
    return status


def apply_emergency_disembark_battle_shock(
    *, state: GameState, decisions: DecisionController, event: EventRecord
) -> None:
    status = _status(event, state)
    views = current_rules_unit_views_for_canonical_identity(
        state=state, unit_instance_id=status.unit_instance_id
    )
    if not any(model.is_alive for view in views for model in view.own_models):
        return
    assert isinstance(event.payload, dict)
    apply_direct_battle_shock_state(
        state=state,
        decisions=decisions,
        player_id=status.player_id,
        unit_instance_id=status.unit_instance_id,
        source_result_id=cast(str, event.payload["result_id"]),
        battle_round=status.battle_round,
    )


def replay_emergency_disembark_battle_shock(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index: int,
    replayed_states: dict[str, BattleShockedUnitState],
    owner_by_unit_id: dict[str, str],
    model_ids_by_unit_id: dict[str, tuple[str, ...]],
) -> None:
    event = event_records[event_index]
    status = _status(event, state)
    payload = event.payload
    assert isinstance(payload, dict)
    request_id = payload.get("request_id")
    if type(request_id) is not str:
        raise GameLifecycleError("Emergency Battle-shock setup request is missing.")
    record = validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=event_index,
        request_id=request_id,
        result_id=cast(str, payload["result_id"]),
    )
    proposal = MovementProposalRequest.from_decision_request_payload(record.request.payload)
    result = record.result.payload
    if not isinstance(result, dict):
        raise GameLifecycleError("Emergency Battle-shock proposal result is missing.")
    submitted = PlacementProposalPayload.from_payload(cast(PlacementProposalPayloadPayload, result))
    if (
        record.request.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE
        or proposal.proposal_kind is not ProposalKind.DISEMBARK
        or proposal.actor_id != status.player_id
        or proposal.unit_instance_id != status.unit_instance_id
        or proposal.context is None
        or proposal.context.get("destruction_timing") != "destroyed_transport"
        or submitted.disembark_mode is not DisembarkModeKind.EMERGENCY_DISEMBARK
        or submitted.transport_unit_instance_id != status.transport_unit_instance_id
        or owner_by_unit_id.get(status.unit_instance_id) != status.player_id
        or status.unit_instance_id not in model_ids_by_unit_id
    ):
        raise GameLifecycleError("Emergency Battle-shock accepted setup authority drift.")
    # Emergency acceptance already certifies the exact living survivors. Use its
    # decision-bound placement, not a new pre-mutation physical-anchor contract.
    # Some supported clause kernels intentionally start at an attack checkpoint.
    raw_transition = payload.get("transition_batch")
    if not isinstance(raw_transition, dict):
        raise GameLifecycleError("Emergency Battle-shock setup transition is missing.")
    transition = BattlefieldTransitionBatch.from_payload(
        cast(BattlefieldTransitionBatchPayload, raw_transition)
    )
    proposed = submitted.resolved_rules_unit_placement().model_placements
    alive_ids = {row.model_instance_id for row in transition.placements}
    if {row.model_instance_id: row.pose for row in transition.placements} != {
        row.model_instance_id: row.pose for row in proposed
    } or not alive_ids <= set(model_ids_by_unit_id[status.unit_instance_id]):
        raise GameLifecycleError("Emergency Battle-shock accepted survivor placement drift.")
    if status.unit_instance_id not in replayed_states and alive_ids.intersection(
        model_ids_by_unit_id[status.unit_instance_id]
    ):
        replayed_states[status.unit_instance_id] = BattleShockedUnitState(
            player_id=status.player_id,
            unit_instance_id=status.unit_instance_id,
            model_instance_ids=model_ids_by_unit_id[status.unit_instance_id],
            source_result_id=cast(str, payload["result_id"]),
            battle_round_started=status.battle_round,
        )
