from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelDisplacementKind,
)
from warhammer40k_core.engine.battlefield_transition_history import (
    prior_fall_back_applied_transition_or_none,
)
from warhammer40k_core.engine.charge_move_event_authority import (
    validate_charge_move_completed_event_authority,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.movement_decision_authority import (
    validate_movement_completion_decision_authority,
)
from warhammer40k_core.engine.mutation_decision_authority import (
    validate_mutation_decision_closure,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.shooting_model import (
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
)
from warhammer40k_core.engine.weapon_declaration import (
    ShootingDeclarationProposalRequest,
    shooting_declaration_proposal_from_json,
)
from warhammer40k_core.geometry.pathing import PathWitness

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
    return validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=mutation_index,
        request_id=request_id,
        result_id=result_id,
    )


def validate_primary_mission_movement_event_decision_authority(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    mutation_index: int,
    payload: dict[str, JsonValue],
) -> None:
    proposal = validate_movement_completion_decision_authority(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=mutation_index,
        payload=payload,
    )
    if proposal is None:
        return
    _validate_prior_fall_back_application(
        event_records=event_records,
        mutation_index=mutation_index,
        event=event_records[mutation_index],
    )
    _validate_movement_transition(
        payload=payload,
        action=_payload_string(payload, "movement_phase_action"),
        witness=proposal.witness,
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


def _validate_prior_fall_back_application(
    *,
    event_records: tuple[EventRecord, ...],
    mutation_index: int,
    event: EventRecord,
) -> None:
    prior_fall_back_applied_transition_or_none(
        event_records=event_records,
        event_index=mutation_index,
        event=event,
    )


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


def validate_physical_transition_decision_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    for event_index, event in enumerate(event_records):
        if event.event_type not in {
            "movement_activation_completed",
            "charge_move_completed",
        }:
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Physical movement event payload is invalid.")
        if event.event_type == "movement_activation_completed":
            validate_primary_mission_movement_event_decision_authority(
                event_records=event_records,
                decision_records=decision_records,
                mutation_index=event_index,
                payload=event.payload,
            )
            continue
        validate_charge_move_completed_event_authority(
            event_records=event_records,
            decision_records=decision_records,
            event_index=event_index,
            payload=event.payload,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        )
