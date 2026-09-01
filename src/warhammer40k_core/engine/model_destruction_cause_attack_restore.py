from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine import model_destruction_cause_payload_validation as _mdcpv
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.model_destruction_cause_attack_identity import (
    attack_damage_model_destruction_cause_id_for_context,
)
from warhammer40k_core.engine.model_destruction_cause_authority import (
    ModelDestructionCauseAuthority,
    ModelDestructionCauseKind,
    model_destruction_cause_authority_by_id_or_none,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_attack_sequence_2026_09,
)

CORE_DESTROYED_TIMING_RULE_ID = core_attack_sequence_2026_09.DESTROYED_RULE_ID

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_destruction_model import (
        PendingAttackDestruction,
    )
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.damage_allocation import DamageApplication
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.event_log import EventRecord
    from warhammer40k_core.engine.game_state import GameState


def active_attack_destruction_context_ids(
    attack_sequence: AttackSequence,
) -> tuple[str, ...]:
    context_ids = tuple(
        pending.attack_context["attack_context_id"]
        for pending in attack_sequence.pending_attack_destructions
    )
    if attack_sequence.is_complete:
        return context_ids
    return (*context_ids, attack_sequence.attack_context_id())


def validate_pending_attack_destruction_boundary(
    *,
    attack_sequence: AttackSequence,
    pending: PendingAttackDestruction,
    event_records: tuple[EventRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    from warhammer40k_core.engine.attack_sequence_destruction_model import (
        PendingAttackDestruction,
    )

    if type(pending) is not PendingAttackDestruction:
        raise GameLifecycleError("Pending attack destruction boundary record is invalid.")
    by_id = {event.event_id: event for event in event_records}
    indexes = {event.event_id: index for index, event in enumerate(event_records)}
    damage_event = by_id.get(pending.damage_event_id)
    if (
        damage_event is None
        or damage_event.event_type != "attack_sequence_step"
        or not isinstance(damage_event.payload, dict)
        or damage_event.payload.get("sequence_id") != attack_sequence.sequence_id
        or damage_event.payload.get("attack_context_id")
        != pending.attack_context["attack_context_id"]
        or damage_event.payload.get("step") != "damage"
        or not isinstance(damage_event.payload.get("payload"), dict)
        or cast(dict[str, JsonValue], damage_event.payload["payload"]).get("damage_application")
        != pending.damage_application.to_payload()
    ):
        raise GameLifecycleError("Pending attack destruction damage event drift.")
    deferred_matches = tuple(
        event
        for event in event_records
        if event.event_type == "attack_model_destruction_deferred"
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == attack_sequence.sequence_id
        and event.payload.get("attack_context_id") == pending.attack_context["attack_context_id"]
        and event.payload.get("model_instance_id") == pending.damage_application.model_instance_id
        and event.payload.get("damage_event_id") == pending.damage_event_id
        and event.payload.get("timing_rule_id") == CORE_DESTROYED_TIMING_RULE_ID
        and event.payload.get("destruction_sources")
        == [source.to_payload() for source in pending.destruction_sources]
        and event.payload.get("destroyed_model_placement") == pending.destroyed_model_placement
    )
    if len(deferred_matches) != 1:
        raise GameLifecycleError("Pending attack destruction deferral evidence drift.")
    deferred_payload = cast(dict[str, JsonValue], deferred_matches[0].payload)
    if deferred_payload.get("attack_pool_sha256") != pending.attack_pool_evidence_sha256:
        raise GameLifecycleError("Pending attack destruction attack pool evidence drift.")
    sequence_deferrals = tuple(
        event
        for event in event_records
        if event.event_type == "attack_model_destruction_deferred"
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == attack_sequence.sequence_id
        and event.payload.get("timing_rule_id") == CORE_DESTROYED_TIMING_RULE_ID
    )
    boundary_matches = tuple(
        event
        for event in event_records
        if event.event_type == "attack_sequence_attacks_resolved"
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == attack_sequence.sequence_id
        and event.payload.get("timing_rule_id") == CORE_DESTROYED_TIMING_RULE_ID
    )
    if attack_sequence.attacks_resolved_event_id is None:
        if boundary_matches:
            raise GameLifecycleError("Pending attack destruction boundary evidence drift.")
        _validate_pending_attack_destruction_queue_order(
            attack_sequence=attack_sequence,
            sequence_deferrals=sequence_deferrals,
            before_boundary=True,
        )
        if not attack_sequence.is_complete:
            _validate_pre_boundary_attack_destruction_evidence(
                attack_sequence=attack_sequence,
                damage_event=damage_event,
                deferred_event=deferred_matches[0],
                sequence_deferrals=sequence_deferrals,
                indexes=indexes,
            )
            return
        if not _has_pending_devastating_wounds_continuation(
            sequence_id=attack_sequence.sequence_id,
            pending_decision_requests=pending_decision_requests,
        ):
            raise GameLifecycleError("Pending attack destruction lacks attacks-resolved evidence.")
        _validate_pre_boundary_attack_destruction_evidence(
            attack_sequence=attack_sequence,
            damage_event=damage_event,
            deferred_event=deferred_matches[0],
            sequence_deferrals=sequence_deferrals,
            indexes=indexes,
        )
        return
    attacks_resolved_event = by_id.get(attack_sequence.attacks_resolved_event_id)
    if (
        attacks_resolved_event is None
        or attacks_resolved_event.event_type != "attack_sequence_attacks_resolved"
        or not isinstance(attacks_resolved_event.payload, dict)
        or attacks_resolved_event.payload.get("sequence_id") != attack_sequence.sequence_id
        or attacks_resolved_event.payload.get("attacker_player_id")
        != attack_sequence.attacker_player_id
        or attacks_resolved_event.payload.get("attacking_unit_instance_id")
        != attack_sequence.attacking_unit_instance_id
        or attacks_resolved_event.payload.get("timing_rule_id") != CORE_DESTROYED_TIMING_RULE_ID
        or attacks_resolved_event.payload.get("pending_destruction_count")
        != len(sequence_deferrals)
        or not sequence_deferrals
        or len(boundary_matches) != 1
        or boundary_matches[0].event_id != attacks_resolved_event.event_id
        or any(
            indexes[event.event_id] >= indexes[attacks_resolved_event.event_id]
            for event in sequence_deferrals
        )
        or indexes[damage_event.event_id] >= indexes[deferred_matches[0].event_id]
        or indexes[deferred_matches[0].event_id] >= indexes[attacks_resolved_event.event_id]
    ):
        raise GameLifecycleError("Pending attack destruction boundary evidence drift.")
    _validate_pending_attack_destruction_queue_order(
        attack_sequence=attack_sequence,
        sequence_deferrals=sequence_deferrals,
        before_boundary=False,
    )


def _validate_pending_attack_destruction_queue_order(
    *,
    attack_sequence: AttackSequence,
    sequence_deferrals: tuple[EventRecord, ...],
    before_boundary: bool,
) -> None:
    pending_order = tuple(
        (
            queued.damage_event_id,
            queued.attack_context["attack_context_id"],
        )
        for queued in attack_sequence.pending_attack_destructions
    )
    deferral_order = tuple(
        (
            cast(dict[str, JsonValue], event.payload).get("damage_event_id"),
            cast(dict[str, JsonValue], event.payload).get("attack_context_id"),
        )
        for event in sequence_deferrals
    )
    expected_order = (
        deferral_order
        if before_boundary
        else deferral_order[len(deferral_order) - len(pending_order) :]
    )
    if pending_order != expected_order:
        raise GameLifecycleError("Pending attack destruction queue order drift.")


def _validate_pre_boundary_attack_destruction_evidence(
    *,
    attack_sequence: AttackSequence,
    damage_event: EventRecord,
    deferred_event: EventRecord,
    sequence_deferrals: tuple[EventRecord, ...],
    indexes: dict[str, int],
) -> None:
    if (
        not sequence_deferrals
        or len(sequence_deferrals) != len(attack_sequence.pending_attack_destructions)
        or indexes[damage_event.event_id] >= indexes[deferred_event.event_id]
    ):
        raise GameLifecycleError("Pending attack destruction pre-boundary evidence drift.")


def _has_pending_devastating_wounds_continuation(
    *,
    sequence_id: str,
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> bool:
    from warhammer40k_core.engine.mortal_wound_model_allocation import (
        is_mortal_wound_resolution_request,
        mortal_wound_resolution_source_context,
    )

    for request in pending_decision_requests:
        if not is_mortal_wound_resolution_request(request):
            continue
        source_context = mortal_wound_resolution_source_context(request)
        if (
            isinstance(source_context, dict)
            and source_context.get("source_kind") == "devastating_wounds"
            and source_context.get("sequence_id") == sequence_id
        ):
            return True
    return False


def require_pending_attack_continuation(
    *,
    state: GameState,
    attack_sequence: AttackSequence,
    event_records: tuple[EventRecord, ...],
    damage_payload: JsonValue,
    attack_context_id: str | None = None,
) -> str:
    damage = _mdcpv.parse_damage_application(damage_payload)
    resolved_context_id = (
        attack_sequence.attack_context_id() if attack_context_id is None else attack_context_id
    )
    cause_id = attack_damage_model_destruction_cause_id_for_context(
        state=state,
        sequence_id=attack_sequence.sequence_id,
        attack_context_id=resolved_context_id,
        model_instance_id=damage.model_instance_id,
    )
    authority = model_destruction_cause_authority_by_id_or_none(
        state=state,
        cause_id=cause_id,
    )
    if authority is None or authority.source_authority_finalized:
        raise GameLifecycleError("Attack continuation lacks its pending destruction cause.")
    expected_parent_ids = _pending_attack_parent_cause_ids(
        state=state,
        authority=authority,
        damage=damage,
        event_records=event_records,
    )
    expected_context = {
        "context_kind": "attack_damage_model_destruction",
        "sequence_id": attack_sequence.sequence_id,
        "attack_context_id": resolved_context_id,
        "attacker_player_id": attack_sequence.attacker_player_id,
        "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
        "source_phase": attack_sequence.source_phase.value,
        "damage_application": validate_json_value(damage.to_payload()),
        "parent_cause_ids": validate_json_value(list(expected_parent_ids)),
    }
    if (
        authority.parent_cause_ids != expected_parent_ids
        or authority.producer_context != expected_context
    ):
        raise GameLifecycleError("Pending attack destruction continuation context drift.")
    return cause_id


def _pending_attack_parent_cause_ids(
    *,
    state: GameState,
    authority: ModelDestructionCauseAuthority,
    damage: DamageApplication,
    event_records: tuple[EventRecord, ...],
) -> tuple[str, ...]:
    damage_payload = damage.to_payload()
    matches = tuple(
        event
        for event in event_records
        if event.event_type == "deadly_demise_mortal_wounds_applied"
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == authority.producer_context.get("sequence_id")
        and event.payload.get("attack_context_id")
        == authority.producer_context.get("attack_context_id")
        and mortal_application_contains_damage(
            event.payload.get("mortal_wound_application"),
            damage_payload=damage_payload,
        )
    )
    if not matches:
        return ()
    if len(matches) != 1:
        raise GameLifecycleError("Pending attack destruction parent evidence is ambiguous.")
    applied_payload = _mdcpv.json_object_value(
        matches[0].payload,
        "pending attack Deadly Demise application",
    )
    source_payload = applied_payload.get("source")
    if not isinstance(source_payload, dict):
        raise GameLifecycleError("Pending attack destruction parent source is invalid.")
    candidates = tuple(
        candidate
        for candidate in state.model_destruction_cause_authorities
        if candidate.sequence_number < authority.sequence_number
        and candidate.cause_kind is ModelDestructionCauseKind.ATTACK_DAMAGE
        and candidate.producer_id == authority.producer_id
        and any(
            source.to_payload() == source_payload
            for source in state.destruction_reaction_sources_for_model(
                model_instance_id=candidate.model_instance_id
            )
        )
    )
    if len(candidates) != 1:
        raise GameLifecycleError("Pending attack destruction parent identity drift.")
    return (candidates[0].cause_id,)


def mortal_application_contains_damage(
    value: JsonValue,
    *,
    damage_payload: object,
) -> bool:
    if not isinstance(value, dict):
        return False
    applications = value.get("applications")
    return isinstance(applications, list) and damage_payload in applications


__all__ = (
    "active_attack_destruction_context_ids",
    "mortal_application_contains_damage",
    "require_pending_attack_continuation",
    "validate_pending_attack_destruction_boundary",
)
