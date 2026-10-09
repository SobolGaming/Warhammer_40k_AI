"""One override request authority for live submission, application and restore."""

from __future__ import annotations

# The shared validator consumes the override owner's closed payload helpers.
# pyright: reportPrivateUsage=false
from typing import TYPE_CHECKING

from warhammer40k_core.core.dice import DiceError, DiceRollState
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice_result_override_descriptors import (
    dice_result_override_descriptors_for_abilities,
)
from warhammer40k_core.engine.dice_result_overrides import (
    DICE_RESULT_OVERRIDE_DECISION_TYPE,
    _context_fingerprint_without_stored,
    _request_payload,
    critical_trigger_markers_for_attack,
    request_dice_result_override_if_available,
)
from warhammer40k_core.engine.dice_roll_history import latest_roll_state
from warhammer40k_core.engine.event_log import canonical_json
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.unit_resource_state import unit_resource_total

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


def invalid_dice_result_override_status(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    invalid = _invalid_finite_override_status(
        state=state,
        request=request,
        result=result,
    )
    if invalid is not None:
        return invalid
    return _invalid_override_request_status(state=state, decisions=decisions, request=request)


def validate_dice_result_override_request(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    just_recorded: bool = False,
) -> None:
    """Share current occurrence authority between application and restoration."""
    invalid = _invalid_override_request_status(
        state=state, decisions=decisions, request=request, just_recorded=just_recorded
    )
    if invalid is not None:
        raise GameLifecycleError(f"Dice result override authority drift: {invalid.payload}")


def validate_pending_dice_result_overrides(
    *, state: GameState, decisions: DecisionController
) -> None:
    for request in decisions.queue.pending_requests:
        if request.decision_type == DICE_RESULT_OVERRIDE_DECISION_TYPE:
            validate_dice_result_override_request(state=state, decisions=decisions, request=request)


def _invalid_override_request_status(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    just_recorded: bool = False,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.gathered_dice_occurrence import unresolved_dice_occurrence
    from warhammer40k_core.engine.lifecycle_state_queries import active_attack_sequence_for_state

    if request.decision_type != DICE_RESULT_OVERRIDE_DECISION_TYPE:
        raise GameLifecycleError("Dice result override validator received another decision type.")
    try:
        payload = _request_payload(request)
    except GameLifecycleError:
        return _invalid_status(state, field="payload")
    issued = tuple(
        event.payload
        for event in decisions.event_log.records
        if event.event_type == "decision_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("request_id") == request.request_id
    )
    if len(issued) != 1 or canonical_json(issued[0]) != canonical_json(request.to_payload()):
        return _invalid_status(state, field="issued_request")
    matching_records = tuple(
        record for record in decisions.records if record.request.request_id == request.request_id
    )
    if just_recorded:
        if (
            len(matching_records) != 1
            or matching_records[0] != decisions.records[-1]
            or matching_records[0].request != request
        ):
            return _invalid_status(state, field="accepted_prefix")
    elif matching_records:
        return _invalid_status(state, field="already_answered")
    if payload["context_fingerprint"] != _context_fingerprint_without_stored(payload):
        return _invalid_status(state, field="context_fingerprint")
    host = active_attack_sequence_for_state(state)
    if host is None or host.sequence_id != payload["sequence_id"]:
        return _invalid_status(state, field="sequence_id")
    try:
        occurrence = unresolved_dice_occurrence(sequence=host, events=decisions.event_log.records)
    except (GameLifecycleError, DiceError):  # fmt: skip
        return _invalid_status(state, field="resolution_frontier")
    sequence = occurrence.sequence
    pool = sequence.current_pool()
    expected_attack_identity = (
        sequence.attack_context_id(),
        sequence.pool_index,
        sequence.attack_index,
        sequence.attacking_unit_instance_id,
        pool.attacker_model_instance_id,
        pool.target_unit_instance_id,
        pool.weapon_profile_id,
        sequence.source_phase.value,
    )
    request_attack_identity = (
        payload["attack_context_id"],
        payload["pool_index"],
        payload["attack_index"],
        payload["attacking_unit_instance_id"],
        payload["attacker_model_instance_id"],
        payload["target_unit_instance_id"],
        payload["weapon_profile_id"],
        payload["source_phase"],
    )
    if expected_attack_identity != request_attack_identity:
        return _invalid_status(state, field="attack_context")
    if payload["roll_type"] != occurrence.step or payload["roll_id"] != occurrence.physical.roll_id:
        return _invalid_status(state, field="physical_occurrence")
    latest_state = latest_roll_state(
        decisions=decisions,
        roll_id=payload["roll_id"],
    )
    try:
        request_roll_state = DiceRollState.from_payload(payload["roll_state"])
    except (DiceError, KeyError, TypeError):  # fmt: skip
        return _invalid_status(state, field="roll_state")
    if latest_state.original_result != occurrence.physical:
        return _invalid_status(state, field="original_roll")
    if latest_state != request_roll_state or latest_state.result_override is not None:
        return _invalid_status(state, field="roll_state")
    if latest_state.original_result.spec.roll_type != payload["roll_spec_type"]:
        return _invalid_status(state, field="roll_spec_type")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=payload["attacking_unit_instance_id"],
    )
    if request.actor_id != rules_unit.owner_player_id:
        return _invalid_status(state, field="actor_id")
    if payload["source_component_unit_instance_id"] not in (rules_unit.component_unit_instance_ids):
        return _invalid_status(state, field="source_component_unit_instance_id")
    source_component = next(
        component.unit
        for component in rules_unit.components
        if component.unit.unit_instance_id == payload["source_component_unit_instance_id"]
    )
    if not any(model.is_alive for model in source_component.own_models):
        return _invalid_status(state, field="source_component_alive")
    attacker_model = rules_unit.model_by_id(payload["attacker_model_instance_id"])
    descriptors = tuple(
        descriptor
        for descriptor in dice_result_override_descriptors_for_abilities(
            source_component.datasheet_abilities
        )
        if descriptor.descriptor_id == payload["descriptor_id"]
    )
    if len(descriptors) != 1:
        return _invalid_status(state, field="descriptor_id")
    descriptor = descriptors[0]
    if (
        descriptor.source_rule_id != payload["source_rule_id"]
        or descriptor.resource_kind != payload["resource_kind"]
        or descriptor.resource_cost != payload["resource_cost"]
        or descriptor.replacement_value != payload["replacement_value"]
        or payload["roll_type"] not in descriptor.roll_types
        or any(keyword in attacker_model.keywords for keyword in descriptor.excluded_model_keywords)
    ):
        return _invalid_status(state, field="descriptor_context")
    current_count = unit_resource_total(
        state=state,
        unit_instance_id=source_component.unit_instance_id,
        resource_kind=descriptor.resource_kind,
    )
    if current_count != payload["current_count"] or current_count < descriptor.resource_cost:
        return _invalid_status(state, field="current_count")
    target_keywords = rules_unit_view_by_id(
        state=state,
        unit_instance_id=pool.target_unit_instance_id,
    ).keywords
    expected_markers = [
        marker.to_payload()
        for marker in critical_trigger_markers_for_attack(
            roll_type=payload["roll_type"],
            weapon_profile=pool.weapon_profile,
            target_keywords=target_keywords,
            name_keywords=rules_unit_view_by_id(
                state=state, unit_instance_id=pool.target_unit_instance_id
            ).datasheet_name_keywords,
        )
    ]
    if payload["critical_trigger_markers"] != expected_markers:
        return _invalid_status(state, field="critical_trigger_markers")
    expected = request_dice_result_override_if_available(
        state=state,
        decisions=decisions,
        roll_state=latest_state,
        roll_type=occurrence.step,
        roll_successful=payload["roll_successful"],
        roll_critical=payload["roll_critical"],
        source_phase=sequence.source_phase.value,
        sequence_id=sequence.sequence_id,
        attack_context_id=sequence.attack_context_id(),
        pool_index=sequence.pool_index,
        attack_index=sequence.attack_index,
        attacking_unit_instance_id=sequence.attacking_unit_instance_id,
        attacker_model_instance_id=pool.attacker_model_instance_id,
        target_unit_instance_id=pool.target_unit_instance_id,
        weapon_profile_id=pool.weapon_profile_id,
        weapon_profile=pool.weapon_profile,
        target_keywords=target_keywords,
        request_id=request.request_id,
        just_recorded_request_id=request.request_id if just_recorded else None,
    )
    if expected is None or canonical_json(expected.to_payload()) != canonical_json(
        request.to_payload()
    ):
        return _invalid_status(state, field="source_request")
    return None


def _invalid_status(state: GameState, *, field: str) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Dice result override context is stale or invalid.",
        payload={
            "invalid_reason": "invalid_dice_result_override_context",
            "field": field,
        },
    )


def _invalid_finite_override_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    field: str | None = None
    if result.request_id != request.request_id:
        field = "request_id"
    elif result.decision_type != request.decision_type:
        field = "decision_type"
    elif result.actor_id != request.actor_id:
        field = "actor_id"
    elif result.selected_option_id not in {option.option_id for option in request.options}:
        field = "selected_option_id"
    else:
        selected_payload = next(
            option.payload
            for option in request.options
            if option.option_id == result.selected_option_id
        )
        if result.payload != selected_payload:
            field = "payload"
    if field is None:
        return None
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Dice result override result does not match the pending request.",
        payload={
            "invalid_reason": "invalid_dice_result_override_result",
            "field": field,
        },
    )
