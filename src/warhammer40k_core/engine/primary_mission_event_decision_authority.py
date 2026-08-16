from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelDisplacementKind,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalPayloadPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.movement_model import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
)
from warhammer40k_core.engine.phases.shooting_model import (
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
)
from warhammer40k_core.engine.weapon_declaration import (
    ShootingDeclarationProposalRequest,
    shooting_declaration_proposal_from_json,
)
from warhammer40k_core.geometry.pathing import PathWitness

_MOVING_ACTION_KINDS = frozenset({"normal_move", "advance", "fall_back"})
_DISPLACEMENT_KIND_BY_ACTION = {
    "normal_move": ModelDisplacementKind.NORMAL_MOVE,
    "advance": ModelDisplacementKind.ADVANCE,
    "fall_back": ModelDisplacementKind.FALL_BACK,
}


def validate_primary_mission_mutation_decision_closure(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    mutation_index: int,
    request_id: str,
    result_id: str,
) -> DecisionRecord:
    records = _authoritative_decision_records(decision_records)
    matches = tuple(
        record
        for record in records
        if record.request.request_id == request_id
        and record.result.request_id == request_id
        and record.result.result_id == result_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Primary mission physical mutation decision authority drifted.")
    record = matches[0]
    _validate_record_event_closure(
        event_records=event_records,
        mutation_index=mutation_index,
        record=record,
    )
    return record


def validate_primary_mission_movement_event_decision_authority(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    mutation_index: int,
    payload: dict[str, JsonValue],
) -> None:
    action_record = validate_primary_mission_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=mutation_index,
        request_id=_payload_string(payload, "request_id"),
        result_id=_payload_string(payload, "result_id"),
    )
    action = _payload_string(payload, "movement_phase_action")
    unit_id = _payload_string(payload, "unit_instance_id")
    _validate_action_record(record=action_record, payload=payload, action=action, unit_id=unit_id)
    if action not in _MOVING_ACTION_KINDS:
        if payload.get("witness") is not None or payload.get("transition_batch") is not None:
            raise GameLifecycleError("Primary mission stationary movement mutation drifted.")
        return

    proposal_records = tuple(
        record
        for record in _authoritative_decision_records(decision_records)
        if record.request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
        and _movement_proposal_request_sources(record)
        == (action_record.request.request_id, action_record.result.result_id)
    )
    if len(proposal_records) != 1:
        raise GameLifecycleError("Primary mission movement proposal authority drifted.")
    proposal_record = proposal_records[0]
    _validate_record_event_closure(
        event_records=event_records,
        mutation_index=mutation_index,
        record=proposal_record,
    )
    if proposal_record.request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
        raise GameLifecycleError("Primary mission movement proposal type drifted.")
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        proposal_record.request.payload
    )
    result_payload = proposal_record.result.payload
    if not isinstance(result_payload, dict):
        raise GameLifecycleError("Primary mission movement proposal result is invalid.")
    proposal = MovementProposalPayload.from_payload(
        cast(MovementProposalPayloadPayload, result_payload)
    )
    validation = proposal.validation_result_for_request(proposal_request)
    if not validation.is_valid:
        raise GameLifecycleError("Primary mission movement proposal/result authority drifted.")
    if (
        proposal_record.request.actor_id != payload.get("active_player_id")
        or proposal_record.result.actor_id != payload.get("active_player_id")
        or proposal_request.game_id != payload.get("game_id")
        or proposal_request.battle_round != payload.get("battle_round")
        or proposal_request.phase != payload.get("phase")
        or proposal_request.actor_id != payload.get("active_player_id")
        or proposal_request.unit_instance_id != unit_id
        or proposal_request.movement_phase_action != action
        or proposal.unit_instance_id != unit_id
        or proposal.movement_phase_action != action
        or payload.get("witness") != proposal.witness.to_payload()
    ):
        raise GameLifecycleError("Primary mission movement proposal semantics drifted.")
    _validate_movement_transition(
        payload=payload,
        action=action,
        witness=proposal.witness,
    )


def _movement_proposal_request_sources(record: DecisionRecord) -> tuple[str, str]:
    proposal_request = MovementProposalRequest.from_decision_request_payload(record.request.payload)
    return (
        proposal_request.source_decision_request_id,
        proposal_request.source_decision_result_id,
    )


def validate_primary_mission_shooting_event_decision_authority(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    mutation_index: int,
    payload: dict[str, JsonValue],
) -> None:
    record = validate_primary_mission_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=mutation_index,
        request_id=_payload_string(payload, "request_id"),
        result_id=_payload_string(payload, "result_id"),
    )
    request_payload = record.request.payload
    result_payload = record.result.payload
    if not isinstance(request_payload, dict) or not isinstance(result_payload, dict):
        raise GameLifecycleError("Primary mission shooting decision payload is invalid.")
    raw_proposal_request = request_payload.get("proposal_request")
    if not isinstance(raw_proposal_request, dict):
        raise GameLifecycleError("Primary mission shooting proposal request is invalid.")
    proposal_request = ShootingDeclarationProposalRequest(
        request_id=_payload_string(raw_proposal_request, "request_id"),
        active_player_id=_payload_string(raw_proposal_request, "active_player_id"),
        battle_round=_payload_int(raw_proposal_request, "battle_round"),
        unit_instance_id=_payload_string(raw_proposal_request, "unit_instance_id"),
        source_decision_request_id=_payload_string(
            raw_proposal_request, "source_decision_request_id"
        ),
        source_decision_result_id=_payload_string(
            raw_proposal_request, "source_decision_result_id"
        ),
        visibility_cache_key=_payload_string(raw_proposal_request, "visibility_cache_key"),
        proposal_kind=_payload_string(raw_proposal_request, "proposal_kind"),
    )
    proposal = shooting_declaration_proposal_from_json(result_payload)
    validation = proposal.validation_result_for_request(proposal_request)
    if not validation.is_valid:
        raise GameLifecycleError("Primary mission shooting proposal authority drifted.")
    if (
        record.request.decision_type != SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE
        or record.result.decision_type != SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE
        or record.request.actor_id != payload.get("active_player_id")
        or record.result.actor_id != payload.get("active_player_id")
        or proposal_request.request_id != record.request.request_id
        or proposal_request.request_id != payload.get("proposal_request_id")
        or proposal_request.active_player_id != payload.get("active_player_id")
        or proposal_request.battle_round != payload.get("battle_round")
        or proposal_request.unit_instance_id != payload.get("unit_instance_id")
        or proposal.player_id != payload.get("active_player_id")
        or proposal.battle_round != payload.get("battle_round")
        or proposal.unit_instance_id != payload.get("unit_instance_id")
        or proposal.visibility_cache_key != payload.get("visibility_cache_key")
    ):
        raise GameLifecycleError("Primary mission shooting decision semantics drifted.")


def _validate_action_record(
    *,
    record: DecisionRecord,
    payload: dict[str, JsonValue],
    action: str,
    unit_id: str,
) -> None:
    request_payload = record.request.payload
    result_payload = record.result.payload
    if not isinstance(request_payload, dict) or not isinstance(result_payload, dict):
        raise GameLifecycleError("Primary mission movement action decision payload is invalid.")
    selected = record.request.option_by_id(record.result.selected_option_id)
    if (
        record.request.decision_type != SELECT_MOVEMENT_ACTION_DECISION_TYPE
        or record.result.decision_type != SELECT_MOVEMENT_ACTION_DECISION_TYPE
        or record.request.actor_id != payload.get("active_player_id")
        or record.result.actor_id != payload.get("active_player_id")
        or request_payload.get("game_id") != payload.get("game_id")
        or request_payload.get("battle_round") != payload.get("battle_round")
        or request_payload.get("phase") != BattlePhase.MOVEMENT.value
        or request_payload.get("active_player_id") != payload.get("active_player_id")
        or request_payload.get("unit_instance_id") != unit_id
        or result_payload.get("unit_instance_id") != unit_id
        or result_payload.get("movement_phase_action") != action
        or selected.payload != result_payload
    ):
        raise GameLifecycleError("Primary mission movement action decision semantics drifted.")


def _validate_movement_transition(
    *,
    payload: dict[str, JsonValue],
    action: str,
    witness: PathWitness,
) -> None:
    raw_transition = payload.get("transition_batch")
    if not isinstance(raw_transition, dict):
        raise GameLifecycleError("Primary mission movement transition authority is missing.")
    transition = BattlefieldTransitionBatch.from_payload(
        cast(BattlefieldTransitionBatchPayload, raw_transition)
    )
    if transition.placements:
        raise GameLifecycleError("Primary mission movement transition cannot place models.")
    expected_kind = _DISPLACEMENT_KIND_BY_ACTION[action]
    removal_ids = {row.model_instance_id for row in transition.removals}
    witness_paths = dict(witness.model_paths)
    if not removal_ids <= set(witness_paths):
        raise GameLifecycleError("Primary mission movement removal witness drifted.")
    expected_displaced_ids = {
        model_id
        for model_id, poses in witness.model_paths
        if poses[0] != poses[-1] and model_id not in removal_ids
    }
    if {row.model_instance_id for row in transition.displacements} != expected_displaced_ids:
        raise GameLifecycleError("Primary mission movement transition inventory drifted.")
    for displacement in transition.displacements:
        poses = witness_paths[displacement.model_instance_id]
        if (
            displacement.displacement_kind is not expected_kind
            or displacement.start_pose != poses[0]
            or displacement.end_pose != poses[-1]
            or displacement.path_witness
            != PathWitness.for_paths(((displacement.model_instance_id, poses),))
            or displacement.source_phase != BattlePhase.MOVEMENT.value
            or displacement.source_step != "move_units"
            or displacement.source_rule_id is not None
            or displacement.source_event_id is not None
        ):
            raise GameLifecycleError("Primary mission movement transition witness drifted.")
    raw_kind = payload.get("displacement_kind")
    if transition.displacements and raw_kind != expected_kind.value:
        raise GameLifecycleError("Primary mission movement displacement kind drifted.")
    if not transition.displacements and raw_kind not in {None, expected_kind.value}:
        raise GameLifecycleError("Primary mission movement displacement kind drifted.")


def _validate_record_event_closure(
    *,
    event_records: tuple[EventRecord, ...],
    mutation_index: int,
    record: DecisionRecord,
) -> None:
    prior = event_records[:mutation_index]
    recorded = tuple(
        (index, event)
        for index, event in enumerate(prior)
        if event.event_type == "decision_recorded" and event.payload == record.to_payload()
    )
    if len(recorded) != 1:
        raise GameLifecycleError("Primary mission mutation lacks its exact decision ledger event.")
    record_index, _record_event = recorded[0]
    requested = tuple(
        event
        for event in prior[:record_index]
        if event.event_type == "decision_requested" and event.payload == record.request.to_payload()
    )
    if len(requested) != 1:
        raise GameLifecycleError("Primary mission physical mutation lacks its exact request event.")


def _authoritative_decision_records(value: object) -> tuple[DecisionRecord, ...]:
    if type(value) is not tuple or any(
        type(record) is not DecisionRecord for record in cast(tuple[object, ...], value)
    ):
        raise GameLifecycleError("Primary mission mutation decision ledger is invalid.")
    return cast(tuple[DecisionRecord, ...], value)


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Primary mission movement {key} is invalid.")
    return value


def _payload_int(payload: dict[str, JsonValue], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Primary mission movement {key} is invalid.")
    return value


__all__ = (
    "validate_primary_mission_movement_event_decision_authority",
    "validate_primary_mission_mutation_decision_closure",
    "validate_primary_mission_shooting_event_decision_authority",
)
