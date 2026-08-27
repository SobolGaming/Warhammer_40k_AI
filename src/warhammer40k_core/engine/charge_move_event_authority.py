from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelDisplacementKind,
)
from warhammer40k_core.engine.charge_declaration import (
    ChargeRollResult,
    ChargeRollResultPayload,
    phase15a_charge_roll_payload,
)
from warhammer40k_core.engine.charge_move_event_schema import (
    CHARGE_MOVE_COMPLETED_OPTIONAL_PAYLOAD_KEYS,
    CHARGE_MOVE_COMPLETED_PAYLOAD_KEYS,
    CHARGE_MOVE_COMPLETED_STATUS,
    CHARGE_MOVE_ENDPOINT_WITNESS_PAYLOAD_KEYS,
    CHARGE_MOVE_FLY_POLICY_PAYLOAD_KEYS,
    CHARGE_MOVE_MODEL_MOVEMENT_PAYLOAD_KEYS,
    CHARGE_MOVE_PROPOSAL_CONTEXT_KEYS,
    CHARGE_MOVE_PROPOSAL_REQUIRED_STATUS,
)
from warhammer40k_core.engine.charge_required_targets import (
    CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import PARAMETERIZED_DECISION_OPTION_ID
from warhammer40k_core.engine.effects import (
    EffectExpiration,
    PersistingEffect,
    PersistingEffectPayload,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.mutation_decision_authority import (
    validate_mutation_decision_closure,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.charge import (
    CHARGE_MOVE_ACTION,
    FIGHTS_FIRST_CHARGE_EFFECT_KIND,
    SELECT_CHARGING_UNIT_DECISION_TYPE,
    ChargeMoveProposal,
    ChargeMoveProposalPayload,
)
from warhammer40k_core.engine.unit_coherency import (
    UnitCoherencyResult,
    UnitCoherencyResultPayload,
)
from warhammer40k_core.geometry.pathing import (
    PathValidationResult,
    PathValidationResultPayload,
    PathWitness,
    TerrainPathLegalityResult,
    TerrainPathLegalityResultPayload,
)

_CHARGE_SELECTION_REQUEST_PAYLOAD_KEYS = frozenset(
    {"game_id", "battle_round", "phase", "active_player_id"}
)
_CHARGE_SELECTION_EVENT_PAYLOAD_KEYS = frozenset(
    {
        "game_id",
        "battle_round",
        "phase",
        "active_player_id",
        "unit_instance_id",
        "source_decision_request_id",
        "source_decision_result_id",
    }
)
_INITIAL_PROPOSAL_EVENT_PAYLOAD_KEYS = frozenset(
    {
        "game_id",
        "battle_round",
        "active_player_id",
        "phase",
        "unit_instance_id",
        "movement_phase_action",
        "movement_mode",
        "proposal_kind",
        "request_id",
        "source_decision_request_id",
        "source_decision_result_id",
        "maximum_distance_inches",
        "reachable_target_unit_instance_ids",
        CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
        "phase_body_status",
    }
)
_RETRY_PROPOSAL_EVENT_PAYLOAD_KEYS = frozenset(
    {
        "game_id",
        "battle_round",
        "active_player_id",
        "phase",
        "unit_instance_id",
        "movement_phase_action",
        "movement_mode",
        "proposal_kind",
        "request_id",
        "source_decision_request_id",
        "source_decision_result_id",
        "previous_proposal_request_id",
        "rejected_result_id",
        "phase_body_status",
    }
)


@dataclass(frozen=True, slots=True)
class ChargeMoveCompletedEventAuthority:
    event_index: int
    event_id: str
    payload: dict[str, JsonValue]
    selection_record: DecisionRecord
    proposal_record: DecisionRecord
    proposal_request: MovementProposalRequest
    proposal: ChargeMoveProposal
    charge_roll_result: ChargeRollResult
    witness: PathWitness
    transition_batch: BattlefieldTransitionBatch


def validate_charge_move_completed_event_authority(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index: int,
    payload: dict[str, JsonValue],
    ruleset_descriptor: RulesetDescriptor,
) -> ChargeMoveCompletedEventAuthority:
    """Authenticate a charge completion against its exact decision and path chain."""
    if type(event_index) is not int or not 0 <= event_index < len(event_records):
        raise GameLifecycleError("Charge move-completed event index is invalid.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Charge move-completed authority requires a ruleset.")
    event = event_records[event_index]
    if event.event_type != "charge_move_completed" or event.payload != payload:
        raise GameLifecycleError("Charge move-completed event occurrence drifted.")
    if tuple(
        index
        for index, candidate in enumerate(event_records)
        if candidate.event_id == event.event_id
    ) != (event_index,):
        raise GameLifecycleError("Charge move-completed event occurrence is ambiguous.")
    expected_payload_keys: frozenset[str] = CHARGE_MOVE_COMPLETED_PAYLOAD_KEYS | (
        CHARGE_MOVE_COMPLETED_OPTIONAL_PAYLOAD_KEYS
        if "persisting_effect" in payload
        else frozenset[str]()
    )
    if frozenset(payload) != expected_payload_keys:
        raise GameLifecycleError("Charge move-completed payload shape drifted.")

    proposal_record = validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=event_index,
        request_id=_identifier(payload, "request_id"),
        result_id=_identifier(payload, "result_id"),
    )
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        proposal_record.request.payload
    )
    if proposal_record.request != proposal_request.to_decision_request():
        raise GameLifecycleError("Charge move-completed proposal request shape drifted.")
    result_payload = _object(proposal_record.result.payload, "proposal result")
    proposal = ChargeMoveProposal.from_payload(cast(ChargeMoveProposalPayload, result_payload))
    if proposal_record.result.payload != proposal.to_payload():
        raise GameLifecycleError("Charge move-completed proposal result shape drifted.")
    proposal_validation = proposal.validation_result_for_request(proposal_request)
    if not proposal_validation.is_valid:
        raise GameLifecycleError("Charge move-completed proposal authority is invalid.")
    _validate_proposal_and_event_context(
        payload=payload,
        proposal_record=proposal_record,
        proposal_request=proposal_request,
        proposal=proposal,
        proposal_validation_payload=validate_json_value(proposal_validation.to_payload()),
    )

    selection_record = validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=event_index,
        request_id=proposal_request.source_decision_request_id,
        result_id=proposal_request.source_decision_result_id,
    )
    _validate_selection_record(
        record=selection_record,
        proposal_request=proposal_request,
    )
    charge_roll_result = _charge_roll_result(
        proposal_request=proposal_request,
        selection_record=selection_record,
    )
    _validate_causal_event_order(
        event_records=event_records,
        decision_records=decision_records,
        event_index=event_index,
        selection_record=selection_record,
        proposal_record=proposal_record,
        proposal_request=proposal_request,
        charge_roll_result=charge_roll_result,
    )

    witness = proposal.witness
    if witness is None:
        raise GameLifecycleError("Charge move-completed proposal lacks a PathWitness.")
    transition = _validate_transition_and_result_payload(
        payload=payload,
        proposal=proposal,
        proposal_request=proposal_request,
        witness=witness,
        ruleset_descriptor=ruleset_descriptor,
    )
    _validate_fights_first_effect(
        payload=payload,
        proposal_record=proposal_record,
        proposal_request=proposal_request,
        ruleset_descriptor=ruleset_descriptor,
    )
    return ChargeMoveCompletedEventAuthority(
        event_index=event_index,
        event_id=event.event_id,
        payload=payload,
        selection_record=selection_record,
        proposal_record=proposal_record,
        proposal_request=proposal_request,
        proposal=proposal,
        charge_roll_result=charge_roll_result,
        witness=witness,
        transition_batch=transition,
    )


def _validate_proposal_and_event_context(
    *,
    payload: dict[str, JsonValue],
    proposal_record: DecisionRecord,
    proposal_request: MovementProposalRequest,
    proposal: ChargeMoveProposal,
    proposal_validation_payload: JsonValue,
) -> None:
    result = proposal_record.result
    if (
        proposal_record.request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE
        or result.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE
        or result.selected_option_id != PARAMETERIZED_DECISION_OPTION_ID
        or proposal_request.request_id != proposal_record.request.request_id
        or proposal_request.request_id != result.request_id
        or proposal_request.request_id != payload.get("proposal_request_id")
        or proposal_request.request_id != payload.get("request_id")
        or result.result_id != payload.get("result_id")
        or proposal_request.proposal_kind is not ProposalKind.CHARGE_MOVE
        or proposal.proposal_kind is not ProposalKind.CHARGE_MOVE
        or proposal_request.movement_phase_action != CHARGE_MOVE_ACTION
        or proposal.movement_phase_action != CHARGE_MOVE_ACTION
        or proposal.movement_mode is not MovementMode.CHARGE
        or proposal_request.game_id != payload.get("game_id")
        or proposal_request.battle_round != payload.get("battle_round")
        or proposal_request.phase != BattlePhase.CHARGE.value
        or payload.get("phase") != BattlePhase.CHARGE.value
        or proposal_request.actor_id != payload.get("active_player_id")
        or proposal_record.request.actor_id != payload.get("active_player_id")
        or result.actor_id != payload.get("active_player_id")
        or proposal_request.unit_instance_id != payload.get("unit_instance_id")
        or proposal.unit_instance_id != payload.get("unit_instance_id")
        or payload.get("phase_body_status") != CHARGE_MOVE_COMPLETED_STATUS
        or payload.get("proposal_validation") != proposal_validation_payload
    ):
        raise GameLifecycleError("Charge move-completed proposal semantics drifted.")


def _validate_selection_record(
    *,
    record: DecisionRecord,
    proposal_request: MovementProposalRequest,
) -> None:
    request_payload = _object(record.request.payload, "selection request")
    result_payload = _object(record.result.payload, "selection result")
    selected = record.request.option_by_id(record.result.selected_option_id)
    if (
        record.request.decision_type != SELECT_CHARGING_UNIT_DECISION_TYPE
        or record.result.decision_type != SELECT_CHARGING_UNIT_DECISION_TYPE
        or record.request.actor_id != proposal_request.actor_id
        or record.result.actor_id != proposal_request.actor_id
        or frozenset(request_payload) != _CHARGE_SELECTION_REQUEST_PAYLOAD_KEYS
        or request_payload.get("game_id") != proposal_request.game_id
        or request_payload.get("battle_round") != proposal_request.battle_round
        or request_payload.get("phase") != BattlePhase.CHARGE.value
        or request_payload.get("active_player_id") != proposal_request.actor_id
        or selected.payload != record.result.payload
        or result_payload.get("submission_kind") != SELECT_CHARGING_UNIT_DECISION_TYPE
        or result_payload.get("game_id") != proposal_request.game_id
        or result_payload.get("battle_round") != proposal_request.battle_round
        or result_payload.get("phase") != BattlePhase.CHARGE.value
        or result_payload.get("active_player_id") != proposal_request.actor_id
        or result_payload.get("unit_instance_id") != proposal_request.unit_instance_id
    ):
        raise GameLifecycleError("Charge move-completed selection authority drifted.")


def _charge_roll_result(
    *,
    proposal_request: MovementProposalRequest,
    selection_record: DecisionRecord,
) -> ChargeRollResult:
    context = proposal_request.context
    if context is None or frozenset(context) != CHARGE_MOVE_PROPOSAL_CONTEXT_KEYS:
        raise GameLifecycleError("Charge move-completed proposal context shape drifted.")
    raw_roll = _object(context.get("charge_roll"), "charge roll")
    roll_result = ChargeRollResult.from_payload(cast(ChargeRollResultPayload, raw_roll))
    if raw_roll != roll_result.to_payload():
        raise GameLifecycleError("Charge move-completed charge-roll shape drifted.")
    reachable_ids = tuple(roll_result.reachable_target_distances_inches)
    required_ids = _identifier_list(
        context.get(CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY),
        CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
    )
    if (
        context.get("source_selected_option_id") != proposal_request.unit_instance_id
        or context.get("movement_mode") != MovementMode.CHARGE.value
        or context.get("maximum_distance_inches") != roll_result.value
        or context.get("reachable_target_unit_instance_ids") != list(reachable_ids)
        or context.get("reachable_target_distances_inches")
        != roll_result.reachable_target_distances_inches
        or not set(required_ids) <= set(reachable_ids)
        or roll_result.request.game_id != proposal_request.game_id
        or roll_result.request.battle_round != proposal_request.battle_round
        or roll_result.request.player_id != proposal_request.actor_id
        or roll_result.request.unit_instance_id != proposal_request.unit_instance_id
        or roll_result.request.source_decision_request_id != selection_record.request.request_id
        or roll_result.request.source_decision_result_id != selection_record.result.result_id
        or not roll_result.move_available
    ):
        raise GameLifecycleError("Charge move-completed charge-roll authority drifted.")
    return roll_result


def _validate_causal_event_order(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index: int,
    selection_record: DecisionRecord,
    proposal_record: DecisionRecord,
    proposal_request: MovementProposalRequest,
    charge_roll_result: ChargeRollResult,
) -> None:
    selection_request_index = _exact_event_index(
        event_records=event_records,
        event_type="decision_requested",
        payload=cast(dict[str, JsonValue], selection_record.request.to_payload()),
        before_index=event_index,
    )
    selection_record_index = _exact_event_index(
        event_records=event_records,
        event_type="decision_recorded",
        payload=cast(dict[str, JsonValue], selection_record.to_payload()),
        before_index=event_index,
    )
    selection_payload: dict[str, JsonValue] = {
        "game_id": proposal_request.game_id,
        "battle_round": proposal_request.battle_round,
        "phase": BattlePhase.CHARGE.value,
        "active_player_id": proposal_request.actor_id,
        "unit_instance_id": proposal_request.unit_instance_id,
        "source_decision_request_id": selection_record.request.request_id,
        "source_decision_result_id": selection_record.result.result_id,
    }
    if frozenset(selection_payload) != _CHARGE_SELECTION_EVENT_PAYLOAD_KEYS:
        raise GameLifecycleError("Charge move-completed selection event shape drifted.")
    selection_event_index = _exact_event_index(
        event_records=event_records,
        event_type="charging_unit_selected",
        payload=selection_payload,
        before_index=event_index,
    )
    roll_payload = cast(
        dict[str, JsonValue],
        validate_json_value(phase15a_charge_roll_payload(roll_result=charge_roll_result)),
    )
    roll_index = _exact_event_index(
        event_records=event_records,
        event_type="charge_roll_resolved",
        payload=roll_payload,
        before_index=event_index,
    )
    move_required_index = _exact_event_index(
        event_records=event_records,
        event_type="charge_move_required",
        payload=roll_payload,
        before_index=event_index,
    )
    proposal_request_index = _exact_event_index(
        event_records=event_records,
        event_type="decision_requested",
        payload=cast(dict[str, JsonValue], proposal_record.request.to_payload()),
        before_index=event_index,
    )
    domain_request_index = _proposal_domain_request_event_index(
        event_records=event_records,
        before_index=event_index,
        proposal_request=proposal_request,
        charge_roll_result=charge_roll_result,
        decision_records=decision_records,
    )
    proposal_record_index = _exact_event_index(
        event_records=event_records,
        event_type="decision_recorded",
        payload=cast(dict[str, JsonValue], proposal_record.to_payload()),
        before_index=event_index,
    )
    if not (
        selection_request_index
        < selection_record_index
        < selection_event_index
        < roll_index
        < move_required_index
        < proposal_request_index
        < domain_request_index
        < proposal_record_index
        < event_index
    ):
        raise GameLifecycleError("Charge move-completed causal event order drifted.")


def _proposal_domain_request_event_index(
    *,
    event_records: tuple[EventRecord, ...],
    before_index: int,
    proposal_request: MovementProposalRequest,
    charge_roll_result: ChargeRollResult,
    decision_records: tuple[DecisionRecord, ...],
) -> int:
    matches = tuple(
        (index, _object(event.payload, "proposal-request event"))
        for index, event in enumerate(event_records[:before_index])
        if event.event_type == "charge_move_proposal_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("request_id") == proposal_request.request_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Charge move-completed proposal event is ambiguous.")
    index, payload = matches[0]
    common: dict[str, JsonValue] = {
        "game_id": proposal_request.game_id,
        "battle_round": proposal_request.battle_round,
        "active_player_id": proposal_request.actor_id,
        "phase": BattlePhase.CHARGE.value,
        "unit_instance_id": proposal_request.unit_instance_id,
        "movement_phase_action": CHARGE_MOVE_ACTION,
        "movement_mode": MovementMode.CHARGE.value,
        "proposal_kind": ProposalKind.CHARGE_MOVE.value,
        "request_id": proposal_request.request_id,
        "source_decision_request_id": proposal_request.source_decision_request_id,
        "source_decision_result_id": proposal_request.source_decision_result_id,
        "phase_body_status": CHARGE_MOVE_PROPOSAL_REQUIRED_STATUS,
    }
    context = proposal_request.context or {}
    if frozenset(payload) == _INITIAL_PROPOSAL_EVENT_PAYLOAD_KEYS:
        expected = {
            **common,
            "maximum_distance_inches": charge_roll_result.value,
            "reachable_target_unit_instance_ids": list(
                charge_roll_result.reachable_target_distances_inches
            ),
            CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY: context[
                CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY
            ],
        }
        if payload != expected:
            raise GameLifecycleError("Charge move-completed proposal event drifted.")
        return index
    if frozenset(payload) != _RETRY_PROPOSAL_EVENT_PAYLOAD_KEYS:
        raise GameLifecycleError("Charge move-completed proposal event shape drifted.")
    previous_request_id = _identifier(payload, "previous_proposal_request_id")
    rejected_result_id = _identifier(payload, "rejected_result_id")
    previous = tuple(
        record
        for record in decision_records
        if record.request.request_id == previous_request_id
        and record.result.result_id == rejected_result_id
    )
    if (
        len(previous) != 1
        or previous[0].request.decision_type != (MOVEMENT_PROPOSAL_DECISION_TYPE)
        or payload
        != {
            **common,
            "previous_proposal_request_id": previous_request_id,
            "rejected_result_id": rejected_result_id,
        }
    ):
        raise GameLifecycleError("Charge move-completed retry proposal authority drifted.")
    validate_mutation_decision_closure(
        event_records=event_records,
        decision_records=decision_records,
        mutation_index=index,
        request_id=previous_request_id,
        result_id=rejected_result_id,
    )
    return index


def _validate_transition_and_result_payload(
    *,
    payload: dict[str, JsonValue],
    proposal: ChargeMoveProposal,
    proposal_request: MovementProposalRequest,
    witness: PathWitness,
    ruleset_descriptor: RulesetDescriptor,
) -> BattlefieldTransitionBatch:
    raw_transition = _object(payload.get("transition_batch"), "transition batch")
    transition = BattlefieldTransitionBatch.from_payload(
        cast(BattlefieldTransitionBatchPayload, raw_transition)
    )
    if transition.to_payload() != raw_transition or transition.placements or transition.removals:
        raise GameLifecycleError("Charge move-completed transition shape drifted.")
    model_movements = _object_list(payload.get("model_movements"), "model movements")
    raw_path_results = _object_list(
        payload.get("path_validation_results"),
        "path validation results",
    )
    raw_terrain_results = _object_list(
        payload.get("terrain_path_legality_results"),
        "terrain path legality results",
    )
    if not (
        len(model_movements) == len(raw_path_results) == len(raw_terrain_results)
        and len(model_movements) == len(witness.model_paths)
    ):
        raise GameLifecycleError("Charge move-completed model result inventory drifted.")
    maximum_distance = _integer(payload, "maximum_distance_inches")
    movement_ids: list[str] = []
    displaced_ids: list[str] = []
    for movement, raw_path, raw_terrain in zip(
        model_movements,
        raw_path_results,
        raw_terrain_results,
        strict=True,
    ):
        if frozenset(movement) != CHARGE_MOVE_MODEL_MOVEMENT_PAYLOAD_KEYS:
            raise GameLifecycleError("Charge move-completed model movement shape drifted.")
        model_id = _identifier(movement, "model_instance_id")
        if model_id in movement_ids:
            raise GameLifecycleError("Charge move-completed model movement is duplicated.")
        movement_ids.append(model_id)
        poses = witness.poses_for_model(model_id)
        path_result = PathValidationResult.from_payload(cast(PathValidationResultPayload, raw_path))
        terrain_result = TerrainPathLegalityResult.from_payload(
            cast(TerrainPathLegalityResultPayload, raw_terrain)
        )
        if (
            path_result.to_payload() != raw_path
            or terrain_result.to_payload() != raw_terrain
            or not path_result.is_valid
            or not terrain_result.is_valid
            or movement.get("movement_mode") != MovementMode.CHARGE.value
            or movement.get("maximum_distance_inches") != maximum_distance
            or movement.get("start_pose") != poses[0].to_payload()
            or movement.get("end_pose") != poses[-1].to_payload()
            or movement.get("movement_distance_witness")
            != (
                None
                if path_result.movement_distance_witness is None
                else path_result.movement_distance_witness.to_payload()
            )
            or movement.get("path_validation_result") != raw_path
            or movement.get("terrain_path_legality_result") != raw_terrain
        ):
            raise GameLifecycleError("Charge move-completed model movement authority drifted.")
        if poses[0] != poses[-1]:
            displaced_ids.append(model_id)
    if tuple(sorted(movement_ids)) != witness.model_ids():
        raise GameLifecycleError("Charge move-completed witness inventory drifted.")
    if tuple(row.model_instance_id for row in transition.displacements) != tuple(displaced_ids):
        raise GameLifecycleError("Charge move-completed displacement inventory drifted.")
    for displacement in transition.displacements:
        poses = witness.poses_for_model(displacement.model_instance_id)
        if (
            displacement.displacement_kind is not ModelDisplacementKind.CHARGE_MOVE
            or displacement.start_pose != poses[0]
            or displacement.end_pose != poses[-1]
            or displacement.path_witness
            != PathWitness.for_paths(((displacement.model_instance_id, poses),))
            or displacement.source_phase != BattlePhase.CHARGE.value
            or displacement.source_step != CHARGE_MOVE_ACTION
            or displacement.source_rule_id is not None
            or displacement.source_event_id is not None
        ):
            raise GameLifecycleError("Charge move-completed displacement witness drifted.")
    _validate_result_summary(
        payload=payload,
        proposal=proposal,
        proposal_request=proposal_request,
        witness=witness,
        maximum_distance=maximum_distance,
        ruleset_descriptor=ruleset_descriptor,
    )
    return transition


def _validate_result_summary(
    *,
    payload: dict[str, JsonValue],
    proposal: ChargeMoveProposal,
    proposal_request: MovementProposalRequest,
    witness: PathWitness,
    maximum_distance: int,
    ruleset_descriptor: RulesetDescriptor,
) -> None:
    if (
        payload.get("movement_mode") != MovementMode.CHARGE.value
        or maximum_distance != (proposal_request.context or {}).get("maximum_distance_inches")
        or payload.get("selected_target_unit_instance_ids")
        != list(proposal.charge_target_unit_instance_ids)
    ):
        raise GameLifecycleError("Charge move-completed result summary drifted.")
    raw_coherency = _object(payload.get("coherency_result"), "coherency result")
    coherency = UnitCoherencyResult.from_payload(cast(UnitCoherencyResultPayload, raw_coherency))
    if (
        coherency.to_payload() != raw_coherency
        or not coherency.is_coherent
        or coherency.ruleset_descriptor_hash != ruleset_descriptor.descriptor_hash
        or coherency.unit_instance_id != proposal.unit_instance_id
        or tuple(sorted(coherency.model_instance_ids)) != witness.model_ids()
    ):
        raise GameLifecycleError("Charge move-completed coherency authority drifted.")
    endpoint = _object(payload.get("endpoint_witness"), "endpoint witness")
    if frozenset(endpoint) != CHARGE_MOVE_ENDPOINT_WITNESS_PAYLOAD_KEYS:
        raise GameLifecycleError("Charge move-completed endpoint shape drifted.")
    selected_ids = _identifier_list(
        endpoint.get("selected_target_unit_instance_ids"),
        "selected_target_unit_instance_ids",
    )
    engaged_ids = _identifier_list(
        endpoint.get("engaged_target_unit_instance_ids"),
        "engaged_target_unit_instance_ids",
    )
    preferred_ids = _identifier_list(
        endpoint.get("preferred_distance_target_unit_instance_ids"),
        "preferred_distance_target_unit_instance_ids",
    )
    non_target_ids = _identifier_list(
        endpoint.get("non_target_engaged_unit_instance_ids"),
        "non_target_engaged_unit_instance_ids",
    )
    before_distances = _distance_map(
        endpoint.get("target_distances_before_inches"),
        "target_distances_before_inches",
    )
    after_distances = _distance_map(
        endpoint.get("target_distances_after_inches"),
        "target_distances_after_inches",
    )
    if (
        selected_ids != proposal.charge_target_unit_instance_ids
        or set(before_distances) != set(selected_ids)
        or set(after_distances) != set(selected_ids)
        or not set(engaged_ids) <= set(selected_ids)
        or not set(preferred_ids) <= set(selected_ids)
        or set(non_target_ids) & set(selected_ids)
    ):
        raise GameLifecycleError("Charge move-completed endpoint authority drifted.")
    fly_policy = _object(payload.get("fly_charge_policy"), "FLY policy")
    if frozenset(fly_policy) != CHARGE_MOVE_FLY_POLICY_PAYLOAD_KEYS or any(
        type(fly_policy[key]) is not bool for key in CHARGE_MOVE_FLY_POLICY_PAYLOAD_KEYS
    ):
        raise GameLifecycleError("Charge move-completed FLY policy shape drifted.")


def _validate_fights_first_effect(
    *,
    payload: dict[str, JsonValue],
    proposal_record: DecisionRecord,
    proposal_request: MovementProposalRequest,
    ruleset_descriptor: RulesetDescriptor,
) -> None:
    raw_effect = payload.get("persisting_effect")
    if not ruleset_descriptor.charge_policy.grants_fights_first_until_end_turn:
        if "persisting_effect" in payload:
            raise GameLifecycleError("Charge move-completed Fights First effect is unexpected.")
        return
    effect_payload = _object(raw_effect, "Fights First effect")
    effect = PersistingEffect.from_payload(cast(PersistingEffectPayload, effect_payload))
    expected = PersistingEffect(
        effect_id=f"{proposal_record.result.result_id}:charge:fights-first",
        source_rule_id="core-rules:charge:fights-first",
        owner_player_id=proposal_request.actor_id,
        target_unit_instance_ids=(proposal_request.unit_instance_id,),
        started_battle_round=proposal_request.battle_round,
        started_phase=BattlePhaseKind.CHARGE,
        expiration=EffectExpiration.end_turn(
            battle_round=proposal_request.battle_round,
            player_id=proposal_request.actor_id,
        ),
        effect_payload={
            "effect_kind": FIGHTS_FIRST_CHARGE_EFFECT_KIND,
            "proposal_request_id": proposal_request.request_id,
            "decision_result_id": proposal_record.result.result_id,
        },
    )
    if effect_payload != effect.to_payload() or effect != expected:
        raise GameLifecycleError("Charge move-completed Fights First effect drifted.")


def _exact_event_index(
    *,
    event_records: tuple[EventRecord, ...],
    event_type: str,
    payload: dict[str, JsonValue],
    before_index: int,
) -> int:
    matches = tuple(
        index
        for index, event in enumerate(event_records[:before_index])
        if event.event_type == event_type and event.payload == payload
    )
    if len(matches) != 1:
        raise GameLifecycleError(f"Charge move-completed {event_type} occurrence drifted.")
    return matches[0]


def _object(value: object, context: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Charge move-completed {context} must be an object.")
    return cast(dict[str, JsonValue], value)


def _object_list(value: object, context: str) -> tuple[dict[str, JsonValue], ...]:
    if not isinstance(value, list):
        raise GameLifecycleError(f"Charge move-completed {context} must be an object list.")
    raw_items = cast(list[object], value)
    objects: list[dict[str, JsonValue]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise GameLifecycleError(f"Charge move-completed {context} must be an object list.")
        objects.append(cast(dict[str, JsonValue], item))
    return tuple(objects)


def _identifier(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Charge move-completed {key} must be an identifier.")
    return value


def _integer(payload: dict[str, JsonValue], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Charge move-completed {key} must be an integer.")
    return value


def _identifier_list(value: object, context: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise GameLifecycleError(f"Charge move-completed {context} must be an identifier list.")
    identifiers: list[str] = []
    for item in cast(list[object], value):
        if type(item) is not str or not item:
            raise GameLifecycleError(f"Charge move-completed {context} must be an identifier list.")
        identifiers.append(item)
    if len(identifiers) != len(set(identifiers)):
        raise GameLifecycleError(f"Charge move-completed {context} is duplicated.")
    return tuple(identifiers)


def _distance_map(value: object, context: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Charge move-completed {context} must be a distance map.")
    distances: dict[str, float] = {}
    for raw_key, raw_value in cast(dict[object, object], value).items():
        if type(raw_key) is not str or not raw_key:
            raise GameLifecycleError(f"Charge move-completed {context} key is invalid.")
        if not isinstance(raw_value, int | float) or type(raw_value) is bool:
            raise GameLifecycleError(f"Charge move-completed {context} value is invalid.")
        distance = float(raw_value)
        if not math.isfinite(distance) or distance < 0.0:
            raise GameLifecycleError(f"Charge move-completed {context} value is invalid.")
        distances[raw_key] = distance
    return distances


__all__ = (
    "ChargeMoveCompletedEventAuthority",
    "validate_charge_move_completed_event_authority",
)
