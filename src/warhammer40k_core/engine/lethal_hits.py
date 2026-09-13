"""Canonical per-critical-hit choice, shared by every attack host."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.attack_sequence_model import HitRoll, HitRollPayload
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, canonical_json
from warhammer40k_core.engine.finite_decision_validation import invalid_finite_decision_status
from warhammer40k_core.engine.lifecycle_state_queries import active_attack_sequence_for_state
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.weapon_abilities import lethal_hits_applies
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_lethal_hits_2026_09 import (
    LETHAL_HITS_SOURCE_ID,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState

SELECT_LETHAL_HIT_WOUND_DECISION_TYPE = "select_lethal_hit_wound"
AUTO_WOUND_OPTION_ID = "auto-wound"
ROLL_TO_WOUND_OPTION_ID = "roll-to-wound"


def lethal_hit_wound_choice(
    *,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
    hit: HitRoll,
) -> tuple[bool, LifecycleStatus | None]:
    """Return the recorded choice, or pause before any wound is resolved."""
    if sequence.generated_hit_index != 0 or not hit.critical:
        return False, None
    request_id = f"{sequence.attack_context_id()}:lethal-hit-wound"
    records = tuple(
        record for record in decisions.records if record.request.request_id == request_id
    )
    if not _eligible(state, sequence, hit):
        if records:
            raise GameLifecycleError("Lethal Hits recorded choice lost its attack eligibility.")
        return False, None
    request = _request(state, sequence, hit)
    if records:
        if len(records) != 1 or records[0].request != request:
            raise GameLifecycleError("Lethal Hits recorded choice has drifted from its attack.")
        result = records[0].result
        invalid = invalid_finite_decision_status(
            state=state, request=request, result=result, invalid_reason="invalid_lethal_hit_wound"
        )
        if invalid is not None:
            raise GameLifecycleError("Lethal Hits recorded option has drifted.")
        return result.selected_option_id == AUTO_WOUND_OPTION_ID, None
    decisions.request_decision(request)
    return False, LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": sequence.source_phase.value,
            "phase_body_status": "lethal_hit_wound_pending",
            "attack_context_id": sequence.attack_context_id(),
        },
    )


def invalid_lethal_hit_wound_status(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    invalid = invalid_finite_decision_status(
        state=state, request=request, result=result, invalid_reason="invalid_lethal_hit_wound"
    )
    if invalid is not None:
        return invalid
    try:
        validate_lethal_hit_request(
            state=state, event_records=decisions.event_log.records, request=request
        )
    except GameLifecycleError as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message=str(exc),
            payload={"invalid_reason": "lethal_hit_wound_context_drift", "field": "attack_context"},
        )
    return None


def apply_lethal_hit_wound_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> None:
    """Require an accepted canonical record before the engine resumes the attack."""
    if decisions.record_for_result(result).request != request:
        raise GameLifecycleError("Lethal Hits result requires its owning recorded request.")
    invalid = invalid_lethal_hit_wound_status(
        state=state, decisions=decisions, request=request, result=result
    )
    if invalid is not None:
        raise GameLifecycleError("Lethal Hits cannot apply an invalid recorded choice.")


def validate_pending_lethal_hit_requests(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    for request in pending_decision_requests:
        if request.decision_type == SELECT_LETHAL_HIT_WOUND_DECISION_TYPE:
            validate_lethal_hit_request(state=state, event_records=event_records, request=request)


def validate_lethal_hit_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    """Every issued choice must retain its answer or its owning pending request."""
    from warhammer40k_core.engine.attack_hit_authority import validate_attack_hit_authority

    choices: dict[str, DecisionRecord] = {}
    for record in decision_records:
        if record.request.decision_type != SELECT_LETHAL_HIT_WOUND_DECISION_TYPE:
            continue
        payload = record.request.payload
        if not isinstance(payload, dict) or type(payload.get("attack_context_id")) is not str:
            raise GameLifecycleError("Lethal Hits history requires its attack context.")
        attack_id = cast(str, payload["attack_context_id"])
        if (
            attack_id in choices
            or record.request.request_id != f"{attack_id}:lethal-hit-wound"
            or payload.get("source_rule_id") != LETHAL_HITS_SOURCE_ID
            or record.request.options != _options()
            or invalid_finite_decision_status(
                state=state,
                request=record.request,
                result=record.result,
                invalid_reason="invalid_lethal_hit_wound",
            )
            is not None
        ):
            raise GameLifecycleError("Lethal Hits history has a duplicate or drifted choice.")
        choices[attack_id] = record
    answer_positions = _validate_lethal_decision_evidence(
        choices=choices,
        event_records=event_records,
        pending_decision_requests=pending_decision_requests,
    )
    if choices:
        validate_attack_hit_authority(
            state=state,
            event_records=event_records,
            pending_decision_requests=tuple(record.request for record in choices.values()),
        )
    for position, event in enumerate(event_records):
        if event.event_type != "attack_sequence_step" or not isinstance(event.payload, dict):
            continue
        if event.payload.get("step") != "wound":
            continue
        wound = event.payload.get("payload")
        if not isinstance(wound, dict):
            raise GameLifecycleError("Lethal Hits wound history requires a payload object.")
        wound_attack_id = event.payload.get("attack_context_id")
        if type(wound_attack_id) is not str:
            raise GameLifecycleError("Lethal Hits wound history requires attack identity.")
        choice = choices.get(wound_attack_id)
        if choice is not None and answer_positions[wound_attack_id] >= position:
            raise GameLifecycleError("Lethal Hits wound precedes its recorded answer.")
        automatic = choice is not None and choice.result.selected_option_id == AUTO_WOUND_OPTION_ID
        if wound.get("skipped") is not automatic:
            raise GameLifecycleError(
                "Lethal Hits wound differs from the controlling player's choice."
            )


def _validate_lethal_decision_evidence(
    *,
    choices: dict[str, DecisionRecord],
    event_records: tuple[EventRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> dict[str, int]:
    """Authenticate both directions of the request/answer journal, before Wound exists.

    The issued request freezes the historical target and weapon context. Comparing
    only HitRoll, or re-evaluating today's target, cannot authenticate those fields.
    """
    issued: dict[str, tuple[int, dict[str, JsonValue]]] = {}
    answered: dict[str, tuple[int, dict[str, JsonValue]]] = {}
    hit_positions: dict[str, int] = {}
    for position, event in enumerate(event_records):
        payload = event.payload
        if not isinstance(payload, dict):
            continue
        if event.event_type == "attack_sequence_step" and payload.get("step") == "hit":
            attack_id = payload.get("attack_context_id")
            if type(attack_id) is str:
                hit_positions[attack_id] = position
        if event.event_type not in ("decision_requested", "decision_recorded"):
            continue
        raw_request = (
            payload if event.event_type == "decision_requested" else payload.get("request")
        )
        if (
            not isinstance(raw_request, dict)
            or raw_request.get("decision_type") != SELECT_LETHAL_HIT_WOUND_DECISION_TYPE
        ):
            continue
        request_id = raw_request.get("request_id")
        inventory = issued if event.event_type == "decision_requested" else answered
        if type(request_id) is not str or request_id in inventory:
            raise GameLifecycleError(
                "Lethal Hits journal has missing or duplicate request identity."
            )
        inventory[request_id] = (position, payload)

    answers = {f"{attack_id}:lethal-hit-wound": record for attack_id, record in choices.items()}
    requests = {request_id: record.request for request_id, record in answers.items()}
    for request in pending_decision_requests:
        if request.decision_type != SELECT_LETHAL_HIT_WOUND_DECISION_TYPE:
            continue
        request_id = request.request_id
        if type(request_id) is not str or request_id in requests:
            raise GameLifecycleError("Lethal Hits request cannot be both pending and answered.")
        requests[request_id] = request
    if issued.keys() != requests.keys() or answered.keys() != answers.keys():
        raise GameLifecycleError("Lethal Hits issued choices and recorded answers are incomplete.")

    answer_positions: dict[str, int] = {}
    for request_id, request in requests.items():
        issued_position, issued_payload = issued[request_id]
        if canonical_json(issued_payload) != canonical_json(request.to_payload()):
            raise GameLifecycleError("Lethal Hits history differs from its issued attack context.")
        payload = request.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Lethal Hits issued request requires an attack context.")
        attack_id = payload.get("attack_context_id")
        if (
            type(attack_id) is not str
            or attack_id not in hit_positions
            or hit_positions[attack_id] >= issued_position
        ):
            raise GameLifecycleError("Lethal Hits issued choice must follow its recorded Hit.")
        if request_id in answers:
            answered_position, answered_payload = answered[request_id]
            if issued_position >= answered_position or canonical_json(
                answered_payload
            ) != canonical_json(answers[request_id].to_payload()):
                raise GameLifecycleError("Lethal Hits history differs from its recorded decision.")
            answer_positions[attack_id] = answered_position
    return answer_positions


def validate_lethal_hit_request(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    request: DecisionRequest,
) -> None:
    sequence = active_attack_sequence_for_state(state)
    if sequence is None:
        raise GameLifecycleError("Lethal Hits requires an active attack sequence.")
    hits = tuple(
        event.payload
        for event in event_records
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("step") == "hit"
        and event.payload.get("sequence_id") == sequence.sequence_id
        and event.payload.get("pool_index") == sequence.pool_index
    )
    if not hits:
        raise GameLifecycleError("Lethal Hits requires an owning recorded Hit.")
    # Grouped resolution persists the pool at index zero and reuses completed
    # rolls when resuming. Its latest recorded Hit is the unresolved frontier;
    # the request must not select its own arbitrary index within that pool.
    frontier = hits[-1]
    attack_index = frontier.get("attack_index")
    if (
        type(attack_index) is not int
        or not sequence.attack_index <= attack_index < sequence.current_pool().attacks
        or (sequence.attack_index != 0 and attack_index != sequence.attack_index)
        or sequence.generated_hit_index != 0
        or sequence.post_roll_attack_pools is not None
        or sequence.pending_grouped_damage is not None
    ):
        raise GameLifecycleError("Lethal Hits recorded Hit is outside the unresolved attack pool.")
    sequence = replace(sequence, attack_index=attack_index)
    if frontier.get("attack_context_id") != sequence.attack_context_id() or any(
        event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("step") == "wound"
        and event.payload.get("attack_context_id") == sequence.attack_context_id()
        for event in event_records
    ):
        raise GameLifecycleError("Lethal Hits requires an unresolved original hit.")
    raw_hit = frontier.get("payload")
    if not isinstance(raw_hit, dict):
        raise GameLifecycleError("Lethal Hits recorded Hit requires a payload object.")
    hit = HitRoll.from_payload(cast(HitRollPayload, raw_hit))
    if not _eligible(state, sequence, hit):
        raise GameLifecycleError("Lethal Hits choice is no longer eligible for this attack.")
    expected = _request(state, sequence, hit)
    if canonical_json(request.to_payload()) != canonical_json(expected.to_payload()):
        raise GameLifecycleError("Lethal Hits request has drifted from its owning attack.")


def _eligible(state: GameState, sequence: AttackSequence, hit: HitRoll) -> bool:
    return (
        sequence.generated_hit_index == 0
        and hit.successful
        and hit.critical
        and not hit.skipped
        and lethal_hits_applies(
            sequence.current_pool().weapon_profile,
            target_keywords=rules_unit_view_by_id(
                state=state, unit_instance_id=sequence.current_pool().target_unit_instance_id
            ).keywords,
        )
    )


def _request(state: GameState, sequence: AttackSequence, hit: HitRoll) -> DecisionRequest:
    pool = sequence.current_pool()
    return DecisionRequest(
        request_id=f"{sequence.attack_context_id()}:lethal-hit-wound",
        decision_type=SELECT_LETHAL_HIT_WOUND_DECISION_TYPE,
        actor_id=sequence.attacker_player_id,
        payload={
            "source_rule_id": LETHAL_HITS_SOURCE_ID,
            "source_phase": sequence.source_phase.value,
            "sequence_id": sequence.sequence_id,
            "attack_context_id": sequence.attack_context_id(),
            "pool_index": sequence.pool_index,
            "attack_index": sequence.attack_index,
            "generated_hit_index": sequence.generated_hit_index,
            "attacker_player_id": sequence.attacker_player_id,
            "attacking_unit_instance_id": sequence.attacking_unit_instance_id,
            "attacker_model_instance_id": pool.attacker_model_instance_id,
            "target_unit_instance_id": pool.target_unit_instance_id,
            "target_keywords": list(
                rules_unit_view_by_id(
                    state=state, unit_instance_id=pool.target_unit_instance_id
                ).keywords
            ),
            "weapon_profile_id": pool.weapon_profile_id,
            "weapon_profile": cast(JsonValue, pool.weapon_profile.to_payload()),
            "selected_weapon_ability_ids": list(pool.selected_weapon_ability_ids),
            "hit_roll": cast(JsonValue, hit.to_payload()),
        },
        options=_options(),
    )


def _options() -> tuple[DecisionOption, ...]:
    return (
        DecisionOption(
            option_id=AUTO_WOUND_OPTION_ID,
            label="Automatically wound",
            payload={"choice": AUTO_WOUND_OPTION_ID},
        ),
        DecisionOption(
            option_id=ROLL_TO_WOUND_OPTION_ID,
            label="Roll to wound",
            payload={"choice": ROLL_TO_WOUND_OPTION_ID},
        ),
    )
