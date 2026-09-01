from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine import model_destruction_cause_completion_restore as _mdccr
from warhammer40k_core.engine import model_destruction_cause_payload_validation as _mdcpv
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.destruction_source_attribution import (
    validate_destruction_source_identity,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.model_destruction_cause_attack_identity import (
    attack_damage_model_destruction_cause_id_for_context,
    attack_damage_model_destruction_producer_id_for_context,
)
from warhammer40k_core.engine.model_destruction_cause_authority import (
    MODEL_DESTROYED_EVENT_TYPE,
    MODEL_DESTRUCTION_CAUSE_ID_FIELD,
    ModelDestructionCauseAuthority,
    ModelDestructionCauseKind,
    consume_model_destruction_cause,
    finalize_model_destruction_cause,
    model_destruction_cause_authority_by_id_or_none,
    model_destruction_cause_id,
    record_model_destruction_cause,
    validate_model_destruction_cause_authority_restore,
)
from warhammer40k_core.engine.model_destruction_logical_death_producers import (
    attack_damage_model_logical_death_event,
    rule_effect_model_logical_death_event,
)
from warhammer40k_core.engine.model_destruction_logical_death_restore import (
    validate_model_destruction_logical_death_producer_restore,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    current_rules_unit_views_for_canonical_identity,
    rules_unit_identities_share_lineage,
    rules_unit_view_by_id,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.battlefield_state import ModelPlacement, ModelRemovalRecord
    from warhammer40k_core.engine.damage_allocation import (
        DamageApplication,
    )
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.event_log import EventRecord
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
        MortalWoundDestructionEvidence,
    )


PARENT_MODEL_DESTRUCTION_CAUSE_ID_FIELD = "parent_model_destruction_cause_id"

_ATTACK_DAMAGE_CONTEXT_KIND = "attack_damage_model_destruction"
_MORTAL_WOUND_CONTEXT_KIND = "mortal_wound_model_destruction"
_RULE_EFFECT_CONTEXT_KIND = "rule_effect_model_destruction"


def attack_damage_model_destruction_cause_id(
    *,
    state: GameState,
    attack_sequence: AttackSequence,
    model_instance_id: str,
) -> str:
    return model_destruction_cause_id(
        game_id=state.game_id,
        cause_kind=ModelDestructionCauseKind.ATTACK_DAMAGE,
        producer_id=attack_damage_model_destruction_producer_id(attack_sequence),
        model_instance_id=model_instance_id,
    )


def reserve_attack_damage_model_destruction_cause(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    damage: DamageApplication,
    parent_cause_ids: tuple[str, ...] = (),
) -> ModelDestructionCauseAuthority:
    physical_unit_id = state.unit_instance_id_for_model(damage.model_instance_id)
    rules_unit_id = rules_unit_view_by_id(
        state=state,
        unit_instance_id=damage.target_unit_instance_id,
    ).unit_instance_id
    producer_id = attack_damage_model_destruction_producer_id(attack_sequence)
    cause_id = model_destruction_cause_id(
        game_id=state.game_id,
        cause_kind=ModelDestructionCauseKind.ATTACK_DAMAGE,
        producer_id=producer_id,
        model_instance_id=damage.model_instance_id,
    )
    logical_death_event = attack_damage_model_logical_death_event(
        state=state,
        decisions=decisions,
        cause_id=cause_id,
        producer_id=producer_id,
        damage=damage,
        physical_unit_instance_id=physical_unit_id,
        rules_unit_instance_id=rules_unit_id,
    )
    return record_model_destruction_cause(
        state,
        cause_kind=ModelDestructionCauseKind.ATTACK_DAMAGE,
        producer_id=producer_id,
        model_instance_id=damage.model_instance_id,
        physical_unit_instance_id=physical_unit_id,
        rules_unit_instance_id=rules_unit_id,
        logical_death_event=logical_death_event,
        producer_context={
            "context_kind": _ATTACK_DAMAGE_CONTEXT_KIND,
            "sequence_id": attack_sequence.sequence_id,
            "attack_context_id": attack_sequence.attack_context_id(),
            "attacker_player_id": attack_sequence.attacker_player_id,
            "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
            "source_phase": attack_sequence.source_phase.value,
            "damage_application": validate_json_value(damage.to_payload()),
            "parent_cause_ids": validate_json_value(sorted(parent_cause_ids)),
        },
        parent_cause_ids=parent_cause_ids,
        source_authority_finalized=False,
    )


def finalize_attack_damage_model_destruction_cause(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    damage: DamageApplication,
    damage_event: EventRecord,
    destruction_attribution: ModelDestructionAttribution,
    destroyed_model_placement: ModelPlacement,
    removal_record: ModelRemovalRecord,
) -> ModelDestructionCauseAuthority:
    parent_cause_ids = _attack_parent_cause_ids(
        state=state,
        attack_sequence=attack_sequence,
        attribution=destruction_attribution,
    )
    cause_id = attack_damage_model_destruction_cause_id(
        state=state,
        attack_sequence=attack_sequence,
        model_instance_id=damage.model_instance_id,
    )
    pending = model_destruction_cause_authority_by_id_or_none(
        state=state,
        cause_id=cause_id,
    )
    if pending is None:
        raise GameLifecycleError(
            "Attack destruction cause must be reserved before destruction reactions."
        )
    if pending.parent_cause_ids != tuple(sorted(parent_cause_ids)):
        raise GameLifecycleError("Attack destruction cause parent authority drift.")
    source_decisions, decision_events = _attack_declaration_authority(
        state=state,
        decisions=decisions,
        attack_sequence=attack_sequence,
    )
    source_events = (*decision_events, damage_event)
    return finalize_model_destruction_cause(
        state,
        cause_id=pending.cause_id,
        producer_context={
            "context_kind": _ATTACK_DAMAGE_CONTEXT_KIND,
            "sequence_id": attack_sequence.sequence_id,
            "attack_context_id": attack_sequence.attack_context_id(),
            "attacker_player_id": attack_sequence.attacker_player_id,
            "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
            "source_phase": attack_sequence.source_phase.value,
            "damage_application": validate_json_value(damage.to_payload()),
            "parent_cause_ids": validate_json_value(sorted(parent_cause_ids)),
            "source_decision_record_ids": [record.record_id for record in source_decisions],
            "damage_event": validate_json_value(damage_event.to_payload()),
            "destruction_attribution": validate_json_value(destruction_attribution.to_payload()),
            "destroyed_model_placement": validate_json_value(
                destroyed_model_placement.to_payload()
            ),
            "removal_record": validate_json_value(removal_record.to_payload()),
        },
        source_event_records=source_events,
        source_decision_records=source_decisions,
    )


def consume_attack_damage_model_destruction_cause(
    *,
    state: GameState,
    cause_id: str,
    model_destroyed_event: EventRecord,
) -> ModelDestructionCauseAuthority:
    return consume_model_destruction_cause(
        state,
        cause_id=cause_id,
        model_destroyed_event=model_destroyed_event,
    )


def record_mortal_wound_model_destruction_cause(
    *,
    state: GameState,
    application_id: str,
    source_rule_id: str,
    source_context: JsonValue,
    application_payload: JsonValue,
    evidence: MortalWoundDestructionEvidence,
    model_instance_id: str,
    physical_unit_instance_id: str,
    rules_unit_instance_id: str,
    logical_death_event: EventRecord,
    destroyed_model_placement: ModelPlacement,
    removal_record: ModelRemovalRecord,
) -> ModelDestructionCauseAuthority:
    return record_model_destruction_cause(
        state,
        cause_kind=ModelDestructionCauseKind.MORTAL_WOUND,
        producer_id=application_id,
        model_instance_id=model_instance_id,
        physical_unit_instance_id=physical_unit_instance_id,
        rules_unit_instance_id=rules_unit_instance_id,
        logical_death_event=logical_death_event,
        producer_context={
            "context_kind": _MORTAL_WOUND_CONTEXT_KIND,
            "application_id": application_id,
            "source_rule_id": source_rule_id,
            "source_context": validate_json_value(source_context),
            "application": validate_json_value(application_payload),
            "destruction_evidence": validate_json_value(evidence.to_payload()),
            "destroyed_model_placement": validate_json_value(
                destroyed_model_placement.to_payload()
            ),
            "removal_record": validate_json_value(removal_record.to_payload()),
        },
        parent_cause_ids=_parent_cause_ids_from_context(source_context),
    )


def consume_mortal_wound_model_destruction_cause(
    *,
    state: GameState,
    cause_id: str,
    model_destroyed_event: EventRecord,
) -> ModelDestructionCauseAuthority:
    return consume_model_destruction_cause(
        state,
        cause_id=cause_id,
        model_destroyed_event=model_destroyed_event,
    )


def rule_effect_model_destruction_cause_id(
    *,
    state: GameState,
    root_context: dict[str, JsonValue],
) -> str:
    return model_destruction_cause_id(
        game_id=state.game_id,
        cause_kind=ModelDestructionCauseKind.RULE_EFFECT,
        producer_id=_context_identifier(root_context, "source_result_id"),
        model_instance_id=_context_identifier(root_context, "model_instance_id"),
    )


def reserve_rule_effect_model_destruction_cause(
    *,
    state: GameState,
    decisions: DecisionController,
    root_context: dict[str, JsonValue],
) -> ModelDestructionCauseAuthority:
    parent_cause_ids = _parent_cause_ids_from_context(root_context)
    producer_id = _context_identifier(root_context, "source_result_id")
    model_instance_id = _context_identifier(root_context, "model_instance_id")
    physical_unit_instance_id = _context_identifier(
        root_context,
        "target_unit_instance_id",
    )
    rules_unit_instance_id = _context_identifier(
        root_context,
        "rules_unit_instance_id",
    )
    cause_id = model_destruction_cause_id(
        game_id=state.game_id,
        cause_kind=ModelDestructionCauseKind.RULE_EFFECT,
        producer_id=producer_id,
        model_instance_id=model_instance_id,
    )
    logical_death_event = rule_effect_model_logical_death_event(
        state=state,
        decisions=decisions,
        root_context=root_context,
        cause_id=cause_id,
        producer_id=producer_id,
        model_instance_id=model_instance_id,
        physical_unit_instance_id=physical_unit_instance_id,
        rules_unit_instance_id=rules_unit_instance_id,
        source_rule_id=_context_identifier(root_context, "source_rule_id"),
    )
    return record_model_destruction_cause(
        state,
        cause_kind=ModelDestructionCauseKind.RULE_EFFECT,
        producer_id=producer_id,
        model_instance_id=model_instance_id,
        physical_unit_instance_id=physical_unit_instance_id,
        rules_unit_instance_id=rules_unit_instance_id,
        logical_death_event=logical_death_event,
        producer_context=rule_effect_model_destruction_authority_context(
            root_context=root_context,
        ),
        parent_cause_ids=parent_cause_ids,
        source_authority_finalized=False,
    )


def consume_rule_effect_model_destruction_cause(
    *,
    state: GameState,
    root_context: dict[str, JsonValue],
    model_destroyed_event: EventRecord,
) -> ModelDestructionCauseAuthority:
    return consume_model_destruction_cause(
        state,
        cause_id=rule_effect_model_destruction_cause_id(
            state=state,
            root_context=root_context,
        ),
        model_destroyed_event=model_destroyed_event,
    )


def append_rule_effect_model_destroyed_event(
    *,
    state: GameState,
    decisions: DecisionController,
    root_context: dict[str, JsonValue],
    payload: object,
) -> EventRecord:
    destruction_cause = reserve_rule_effect_model_destruction_cause(
        state=state,
        decisions=decisions,
        root_context=root_context,
    )
    validated_payload = validate_json_value(payload)
    if not isinstance(validated_payload, dict):
        raise GameLifecycleError("Rule model destruction payload must be an object.")
    if MODEL_DESTRUCTION_CAUSE_ID_FIELD in validated_payload:
        raise GameLifecycleError("Rule model destruction payload already names cause authority.")
    source_decisions, source_events = (
        ((), ())
        if destruction_cause.parent_cause_ids
        else _referenced_decision_authority(
            decisions=decisions,
            context=root_context,
        )
    )
    destruction_cause = finalize_model_destruction_cause(
        state,
        cause_id=destruction_cause.cause_id,
        producer_context={
            **rule_effect_model_destruction_authority_context(
                root_context=root_context,
            ),
            "source_decision_record_ids": [record.record_id for record in source_decisions],
            "model_destroyed_payload": validated_payload,
        },
        source_event_records=source_events,
        source_decision_records=source_decisions,
    )
    destroyed_event = decisions.event_log.append(
        MODEL_DESTROYED_EVENT_TYPE,
        {
            **validated_payload,
            MODEL_DESTRUCTION_CAUSE_ID_FIELD: destruction_cause.cause_id,
        },
    )
    consume_rule_effect_model_destruction_cause(
        state=state,
        root_context=root_context,
        model_destroyed_event=destroyed_event,
    )
    return destroyed_event


def attack_damage_model_destruction_producer_id(
    attack_sequence: AttackSequence,
) -> str:
    return attack_damage_model_destruction_producer_id_for_context(
        sequence_id=attack_sequence.sequence_id,
        attack_context_id=attack_sequence.attack_context_id(),
    )


def _attack_parent_cause_ids(
    *,
    state: GameState,
    attack_sequence: AttackSequence,
    attribution: ModelDestructionAttribution,
) -> tuple[str, ...]:
    provenance = attribution.destruction_provenance
    if provenance.destruction_source_kind is not DestructionSourceKind.DEADLY_DEMISE:
        return ()
    source_model_id = attribution.source_model_instance_id
    if source_model_id is None:
        raise GameLifecycleError("Deadly Demise destruction lacks its source model authority.")
    return (
        attack_damage_model_destruction_cause_id(
            state=state,
            attack_sequence=attack_sequence,
            model_instance_id=source_model_id,
        ),
    )


def _attack_declaration_authority(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
) -> tuple[tuple[DecisionRecord, ...], tuple[EventRecord, ...]]:
    matches = tuple(
        record
        for record in decisions.records
        if _decision_result_roots_attack_sequence(
            state=state,
            attack_sequence=attack_sequence,
            result_id=record.result.result_id,
        )
    )
    if len(matches) > 1:
        raise GameLifecycleError("Attack sequence has ambiguous declaration authority.")
    if not matches:
        return (), ()
    decision_event = _decision_recorded_event(
        decisions=decisions,
        decision_record=matches[0],
    )
    return matches, (decision_event,)


def _decision_result_roots_attack_sequence(
    *,
    state: GameState,
    attack_sequence: AttackSequence,
    result_id: str,
) -> bool:
    sequence_id = attack_sequence.sequence_id
    return sequence_id in {
        f"attack-sequence:{result_id}",
        f"out-of-phase-attack-sequence:{result_id}",
        (
            f"melee-sequence:{state.game_id}:round-{state.battle_round:02d}:"
            f"{attack_sequence.attacking_unit_instance_id}:{result_id}"
        ),
    }


def _referenced_decision_authority(
    *,
    decisions: DecisionController,
    context: dict[str, JsonValue],
) -> tuple[tuple[DecisionRecord, ...], tuple[EventRecord, ...]]:
    result_ids = _decision_result_ids(context)
    source_decisions = tuple(
        record for record in decisions.records if record.result.result_id in result_ids
    )
    source_events = tuple(
        _decision_recorded_event(decisions=decisions, decision_record=record)
        for record in source_decisions
    )
    return source_decisions, source_events


def _decision_result_ids(value: JsonValue) -> frozenset[str]:
    result_ids: set[str] = set()

    def collect(current: JsonValue) -> None:
        if isinstance(current, list):
            for item in current:
                collect(item)
            return
        if not isinstance(current, dict):
            return
        for key, item in current.items():
            if key.endswith("result_id") and isinstance(item, str) and item:
                result_ids.add(item)
            collect(item)

    collect(value)
    return frozenset(result_ids)


def _decision_recorded_event(
    *,
    decisions: DecisionController,
    decision_record: DecisionRecord,
) -> EventRecord:
    matches = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "decision_recorded" and event.payload == decision_record.to_payload()
    )
    if len(matches) != 1:
        raise GameLifecycleError("Destruction cause decision lacks one recorded event.")
    return matches[0]


def _parent_cause_ids_from_context(value: JsonValue) -> tuple[str, ...]:
    if not isinstance(value, dict):
        return ()
    raw_parent_id = value.get(PARENT_MODEL_DESTRUCTION_CAUSE_ID_FIELD)
    if raw_parent_id is None:
        return ()
    if not isinstance(raw_parent_id, str) or not raw_parent_id:
        raise GameLifecycleError("Parent model destruction cause ID is invalid.")
    return (raw_parent_id,)


def _context_identifier(context: dict[str, JsonValue], key: str) -> str:
    value = context.get(key)
    if not isinstance(value, str) or not value:
        raise GameLifecycleError(f"Model destruction producer context {key} is invalid.")
    return value


def rule_effect_model_destruction_authority_context(
    *,
    root_context: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    from warhammer40k_core.engine.rule_deadly_demise_continuation import (
        RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND,
        RULE_MODEL_DESTRUCTION_COLLATERAL_COMPLETION_KIND,
        RULE_MODEL_DESTRUCTION_SOURCE_COMPLETION_KIND,
        damage_application_from_rule_context,
        destruction_provenance_from_rule_context,
    )

    source_effect_ids = _mdcpv.json_identifier_list(
        root_context.get("source_effect_ids"),
        "rule destruction source_effect_ids",
    )
    destroyed_model_placement = _mdcpv.json_object_value(
        root_context.get("destroyed_model_placement"),
        "rule destruction destroyed_model_placement",
    )
    source_model_id = root_context.get("source_model_instance_id")
    if source_model_id is not None and (type(source_model_id) is not str or not source_model_id):
        raise GameLifecycleError("Rule destruction source model ID is invalid.")
    source_rules_unit_id = root_context.get("source_rules_unit_instance_id")
    if source_rules_unit_id is not None and (
        type(source_rules_unit_id) is not str or not source_rules_unit_id
    ):
        raise GameLifecycleError("Rule destruction source rules-unit ID is invalid.")
    completion_kind = _context_identifier(root_context, "completion_kind")
    parent_cause_ids = tuple(sorted(_parent_cause_ids_from_context(root_context)))
    damage = damage_application_from_rule_context(root_context)
    provenance = destruction_provenance_from_rule_context(root_context)
    attribution = ModelDestructionAttribution(
        destroying_player_id=_context_identifier(root_context, "destroying_player_id"),
        source_rules_unit_instance_id=source_rules_unit_id,
        source_model_instance_id=source_model_id,
        attacking_unit_instance_id=None,
        attacking_model_instance_id=None,
        destruction_provenance=provenance,
    )
    raw_mortal_evidence = root_context.get("mortal_wound_destruction_evidence")
    mortal_evidence: MortalWoundDestructionEvidence | None = None
    if completion_kind == RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND:
        mortal_evidence = _mdcpv.parse_mortal_wound_destruction_evidence(raw_mortal_evidence)
        if mortal_evidence.destruction_attribution != attribution:
            raise GameLifecycleError("Applied rule destruction attribution drift.")
    elif raw_mortal_evidence is not None:
        raise GameLifecycleError("Rule destruction mode carries unrelated mortal evidence.")
    if completion_kind == RULE_MODEL_DESTRUCTION_SOURCE_COMPLETION_KIND:
        if parent_cause_ids or damage is not None or source_effect_ids == ():
            raise GameLifecycleError("Source rule destruction cause mode drift.")
    elif completion_kind == RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND:
        if (
            parent_cause_ids
            or damage is None
            or damage.damage_kind.value != "mortal"
            or source_effect_ids
        ):
            raise GameLifecycleError("Applied rule destruction cause mode drift.")
    elif completion_kind == RULE_MODEL_DESTRUCTION_COLLATERAL_COMPLETION_KIND:
        if (
            len(parent_cause_ids) != 1
            or damage is None
            or damage.damage_kind.value != "mortal"
            or source_effect_ids
            or provenance.destruction_source_kind is not DestructionSourceKind.DEADLY_DEMISE
        ):
            raise GameLifecycleError("Collateral rule destruction cause mode drift.")
    else:
        raise GameLifecycleError("Rule destruction completion kind is unsupported.")
    completion_event_type: str | None = None
    completion_event_payload: dict[str, JsonValue] | None = None
    if completion_kind != RULE_MODEL_DESTRUCTION_COLLATERAL_COMPLETION_KIND:
        completion_event_type = _context_identifier(root_context, "completion_event_type")
        completion_event_payload = _mdcpv.json_object_value(
            root_context.get("completion_event_payload"),
            "rule destruction completion_event_payload",
        )
    context = validate_json_value(
        {
            "context_kind": _RULE_EFFECT_CONTEXT_KIND,
            "completion_kind": completion_kind,
            "completion_event_type": completion_event_type,
            "completion_event_payload": completion_event_payload,
            "source_rule_id": _context_identifier(root_context, "source_rule_id"),
            "source_result_id": _context_identifier(root_context, "source_result_id"),
            "model_instance_id": _context_identifier(root_context, "model_instance_id"),
            "physical_unit_instance_id": _context_identifier(
                root_context,
                "target_unit_instance_id",
            ),
            "rules_unit_instance_id": _context_identifier(
                root_context,
                "rules_unit_instance_id",
            ),
            "source_effect_ids": list(source_effect_ids),
            "source_phase": _context_identifier(root_context, "phase"),
            "source_step": _context_identifier(root_context, "source_step"),
            "destroying_player_id": attribution.destroying_player_id,
            "source_rules_unit_instance_id": source_rules_unit_id,
            "source_model_instance_id": source_model_id,
            "destroyed_model_placement": destroyed_model_placement,
            "damage_application": None if damage is None else damage.to_payload(),
            "destruction_attribution": attribution.to_payload(),
            "mortal_wound_destruction_evidence": (
                None if mortal_evidence is None else mortal_evidence.to_payload()
            ),
            "parent_cause_ids": list(parent_cause_ids),
            "referenced_result_ids": sorted(_decision_result_ids(root_context)),
        }
    )
    if not isinstance(context, dict):
        raise GameLifecycleError("Rule destruction cause context must be an object.")
    return context


def validate_model_destruction_cause_restore(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    """Validate the producer-owned ledger and every producer-specific root."""

    validate_model_destruction_cause_authority_restore(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    validate_model_destruction_cause_producer_restore(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        pending_decision_requests=pending_decision_requests,
    )
    validate_model_destruction_logical_death_producer_restore(
        state=state,
        event_records=event_records,
    )
    _mdccr.validate_model_logical_death_inventory(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        pending_decision_requests=pending_decision_requests,
    )


def validate_model_destruction_cause_producer_restore(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    """Validate each persisted cause against its owning producer's exact schema."""

    for authority in state.model_destruction_cause_authorities:
        if authority.cause_kind is ModelDestructionCauseKind.ATTACK_DAMAGE:
            _validate_attack_damage_cause_restore(
                state=state,
                authority=authority,
                event_records=event_records,
                decision_records=decision_records,
            )
        elif authority.cause_kind is ModelDestructionCauseKind.MORTAL_WOUND:
            _validate_mortal_wound_cause_restore(
                state=state,
                authority=authority,
                event_records=event_records,
            )
        else:
            _validate_rule_effect_cause_restore(
                state=state,
                authority=authority,
                event_records=event_records,
                decision_records=decision_records,
                pending_decision_requests=pending_decision_requests,
            )
    _mdccr.validate_pending_model_destruction_cause_inventory(
        state=state,
        event_records=event_records,
        pending_decision_requests=pending_decision_requests,
    )


def _validate_attack_damage_cause_restore(
    *,
    state: GameState,
    authority: ModelDestructionCauseAuthority,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    context = authority.producer_context
    base_fields = {
        "context_kind",
        "sequence_id",
        "attack_context_id",
        "attacker_player_id",
        "attacking_unit_instance_id",
        "source_phase",
        "damage_application",
        "parent_cause_ids",
    }
    if not authority.source_authority_finalized:
        _mdcpv.require_exact_context_fields(
            context,
            expected=base_fields,
            cause_kind="attack",
        )
        sequence_id, attack_context_id, parent_cause_ids = _validate_attack_context_base(
            context=context,
            authority=authority,
        )
        if authority.model_destroyed_event is not None:
            raise GameLifecycleError("Pending attack destruction cause was consumed.")
        _validate_pending_attack_parent(
            state=state,
            authority=authority,
            parent_cause_ids=parent_cause_ids,
        )
        if authority.producer_id != f"{sequence_id}:damage:{attack_context_id}":
            raise GameLifecycleError("Pending attack destruction cause context drift.")
        return
    _mdcpv.require_exact_context_fields(
        context,
        expected=base_fields
        | {
            "source_decision_record_ids",
            "damage_application",
            "damage_event",
            "destruction_attribution",
            "destroyed_model_placement",
            "removal_record",
        },
        cause_kind="attack",
    )
    sequence_id, attack_context_id, parent_cause_ids = _validate_attack_context_base(
        context=context,
        authority=authority,
    )
    damage_event_payload = _mdcpv.context_object(context, "damage_event")
    damage_event_matches = tuple(
        event
        for event in authority.source_event_records
        if event.to_payload() == damage_event_payload
    )
    if len(damage_event_matches) != 1:
        raise GameLifecycleError("Attack destruction cause damage source drift.")
    damage_event = damage_event_matches[0]
    damage_event_context = _mdcpv.json_object_value(damage_event.payload, "attack damage event")
    nested_damage_payload = _mdcpv.json_object_value(
        damage_event_context.get("payload"),
        "attack damage event payload",
    )
    damage_application = context.get("damage_application")
    if (
        damage_event.event_type != "attack_sequence_step"
        or damage_event_context.get("step") != "damage"
        or damage_event_context.get("sequence_id") != sequence_id
        or damage_event_context.get("attack_context_id") != attack_context_id
        or nested_damage_payload.get("damage_application") != damage_application
    ):
        raise GameLifecycleError("Attack destruction cause damage source drift.")
    expected_producer_id = f"{sequence_id}:damage:{attack_context_id}"
    if authority.producer_id != expected_producer_id:
        raise GameLifecycleError("Attack destruction cause producer drift.")
    _mdcpv.validate_damage_application_identity(
        damage_application,
        authority=authority,
        damage_kind=None,
    )
    destroyed_event = _mdcpv.required_destroyed_event(authority)
    destroyed_payload = _mdcpv.json_object_value(
        destroyed_event.payload,
        "attack model_destroyed",
    )
    damage = _mdcpv.json_object_value(damage_application, "attack damage application")
    attribution = ModelDestructionAttribution.from_model_destroyed_payload(destroyed_payload)
    damage_target_id = _mdcpv.json_identifier(
        damage,
        "target_unit_instance_id",
        "attack damage application",
    )
    damage_target_views = current_rules_unit_views_for_canonical_identity(
        state=state,
        unit_instance_id=damage_target_id,
    )
    source_weapon = attribution.destruction_provenance.source_weapon_profile
    if (
        destroyed_payload.get("sequence_id") != sequence_id
        or destroyed_payload.get("attack_context_id") != attack_context_id
        or destroyed_payload.get("phase") != context.get("source_phase")
        or destroyed_payload.get("target_unit_instance_id") != damage.get("target_unit_instance_id")
        or all(
            authority.physical_unit_instance_id not in view.component_unit_instance_ids
            for view in damage_target_views
        )
        or not rules_unit_identities_share_lineage(
            state=state,
            first_unit_instance_id=damage_target_id,
            second_unit_instance_id=authority.rules_unit_instance_id,
        )
        or destroyed_payload.get("damage_event_id") != damage_event.event_id
        or destroyed_payload.get("damage_kind") != damage.get("damage_kind")
        or destroyed_payload.get("destroyed_model_placement")
        != context.get("destroyed_model_placement")
        or destroyed_payload.get("removal_record") != context.get("removal_record")
        or attribution.to_payload() != context.get("destruction_attribution")
        or (
            source_weapon is not None
            and nested_damage_payload.get("weapon_profile_id") != source_weapon.profile_id
        )
    ):
        raise GameLifecycleError("Attack destruction cause payload binding drift.")
    if (
        attribution.destruction_provenance.destruction_source_kind is DestructionSourceKind.ATTACK
        and (
            attribution.destroying_player_id != context.get("attacker_player_id")
            or attribution.attacking_unit_instance_id != context.get("attacking_unit_instance_id")
            or attribution.destruction_provenance.attack_context_id != attack_context_id
        )
    ):
        raise GameLifecycleError("Attack destruction source attribution drift.")
    if attribution.destruction_provenance.destruction_source_kind in {
        DestructionSourceKind.ATTACK,
        DestructionSourceKind.DEADLY_DEMISE,
    }:
        validate_destruction_source_identity(
            state=state,
            source_rules_unit_instance_id=attribution.source_rules_unit_instance_id,
            source_model_instance_id=attribution.source_model_instance_id,
            destroying_player_id=attribution.destroying_player_id,
        )
    _validate_parent_binding(
        state=state,
        authority=authority,
        attribution=attribution,
        context=context,
        context_parent_ids=parent_cause_ids,
        exact_attack_parent=True,
    )
    _validate_attack_declaration_sources(
        state=state,
        authority=authority,
        context=context,
        sequence_id=sequence_id,
        damage_event=damage_event,
        destroyed_payload=destroyed_payload,
        event_records=event_records,
        decision_records=decision_records,
    )


def _validate_attack_declaration_sources(
    *,
    state: GameState,
    authority: ModelDestructionCauseAuthority,
    context: dict[str, JsonValue],
    sequence_id: str,
    damage_event: EventRecord,
    destroyed_payload: dict[str, JsonValue],
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    stored_record_ids = _mdcpv.json_identifier_list(
        context.get("source_decision_record_ids"),
        "attack destruction source_decision_record_ids",
    )
    damage_event_index = _mdcpv.event_index(event_records, damage_event)
    attacking_unit_id = _context_identifier(context, "attacking_unit_instance_id")
    candidate_pairs = tuple(
        (record, _decision_recorded_event_from_history(event_records, record))
        for record in decision_records
        if _decision_result_roots_attack_sequence_at_restore(
            state=state,
            sequence_id=sequence_id,
            attacking_unit_instance_id=attacking_unit_id,
            battle_round=destroyed_payload.get("battle_round"),
            result_id=record.result.result_id,
        )
    )
    expected_pairs = tuple(
        pair
        for pair in candidate_pairs
        if _mdcpv.event_index(event_records, pair[1]) < damage_event_index
    )
    expected_decisions = tuple(pair[0] for pair in expected_pairs)
    expected_decision_events = tuple(pair[1] for pair in expected_pairs)
    if len(expected_decisions) > 1:
        raise GameLifecycleError("Attack destruction cause declaration is ambiguous.")
    if (
        stored_record_ids != tuple(record.record_id for record in expected_decisions)
        or authority.source_decision_records != expected_decisions
        or authority.source_event_records != (*expected_decision_events, damage_event)
    ):
        raise GameLifecycleError("Attack destruction declaration source drift.")
    if expected_decisions and expected_decisions[0].result.actor_id != context.get(
        "attacker_player_id"
    ):
        raise GameLifecycleError("Attack destruction declaration actor drift.")


def _validate_mortal_wound_cause_restore(
    *,
    state: GameState,
    authority: ModelDestructionCauseAuthority,
    event_records: tuple[EventRecord, ...],
) -> None:
    context = authority.producer_context
    _mdcpv.require_exact_context_fields(
        context,
        expected={
            "context_kind",
            "application_id",
            "source_rule_id",
            "source_context",
            "application",
            "destruction_evidence",
            "destroyed_model_placement",
            "removal_record",
        },
        cause_kind="mortal-wound",
    )
    if (
        not authority.source_authority_finalized
        or context.get("context_kind") != _MORTAL_WOUND_CONTEXT_KIND
        or context.get("application_id") != authority.producer_id
        or authority.source_event_records
        or authority.source_decision_records
        or authority.parent_cause_ids
        != _parent_cause_ids_from_context(context.get("source_context"))
    ):
        raise GameLifecycleError("Mortal-wound destruction cause authority drift.")
    destroyed_event = _mdcpv.required_destroyed_event(authority)
    destroyed_payload = _mdcpv.json_object_value(
        destroyed_event.payload,
        "mortal-wound model_destroyed",
    )
    application = _mdcpv.parse_mortal_wound_application(context.get("application"))
    evidence = _mdcpv.parse_mortal_wound_destruction_evidence(context.get("destruction_evidence"))
    evidence.validate_for_state(state)
    destroyed_damage = destroyed_payload.get("damage_application")
    matching_damage = tuple(
        item.to_payload()
        for item in application.applications
        if item.model_instance_id == authority.model_instance_id
        and item.destroyed
        and item.to_payload() == destroyed_damage
    )
    attribution = ModelDestructionAttribution.from_model_destroyed_payload(destroyed_payload)
    if (
        len(matching_damage) != 1
        or destroyed_payload.get("damage_kind") != "mortal"
        or destroyed_payload.get("target_unit_instance_id") != authority.physical_unit_instance_id
        or destroyed_payload.get("source_rule_id") != context.get("source_rule_id")
        or destroyed_payload.get("source_context") != context.get("source_context")
        or destroyed_payload.get("destroyed_model_placement")
        != context.get("destroyed_model_placement")
        or destroyed_payload.get("removal_record") != context.get("removal_record")
        or attribution != evidence.destruction_attribution
        or destroyed_payload.get("phase") != evidence.parent_battle_phase.value
    ):
        raise GameLifecycleError("Mortal-wound destruction cause payload binding drift.")
    _validate_parent_binding(
        state=state,
        authority=authority,
        attribution=attribution,
        context=context,
        context_parent_ids=_parent_cause_ids_from_context(context.get("source_context")),
        exact_attack_parent=False,
    )
    completion_event = _mdccr.mortal_wound_completion_event_for_restore(
        authority=authority,
        destroyed_event=destroyed_event,
        event_records=event_records,
    )
    completion_payload = _mdcpv.json_object_value(
        completion_event.payload,
        "mortal-wound destruction completion",
    )
    destroyed_model_ids = _mdcpv.json_identifier_list(
        completion_payload.get("destroyed_model_instance_ids"),
        "mortal-wound completion destroyed_model_instance_ids",
    )
    destroyed_event_ids = _mdcpv.json_identifier_list(
        completion_payload.get("model_destroyed_event_ids"),
        "mortal-wound completion model_destroyed_event_ids",
    )
    if len(destroyed_model_ids) != len(destroyed_event_ids):
        raise GameLifecycleError("Mortal-wound completion destruction inventory drift.")
    _mdccr.validate_mortal_wound_application_inventory(
        state=state,
        application=application,
        destroyed_model_ids=destroyed_model_ids,
        destroyed_event_ids=destroyed_event_ids,
        event_records=event_records,
    )
    expected_physical_ids, expected_rules_ids, expected_transition = (
        _mdccr.validate_mortal_wound_completion_inventory(
            state=state,
            application_id=authority.producer_id,
            event_records=event_records,
            destroyed_model_ids=destroyed_model_ids,
            destroyed_event_ids=destroyed_event_ids,
            source_rule_id=_context_identifier(context, "source_rule_id"),
            source_context=context.get("source_context"),
        )
    )
    removal_record = _mdcpv.context_object(context, "removal_record")
    if (
        (authority.model_instance_id, destroyed_event.event_id)
        not in set(zip(destroyed_model_ids, destroyed_event_ids, strict=True))
        or completion_payload.get("game_id") != authority.game_id
        or completion_payload.get("application_id") != authority.producer_id
        or completion_payload.get("source_rule_id") != context.get("source_rule_id")
        or completion_payload.get("source_context") != context.get("source_context")
        or completion_payload.get("target_unit_instance_id") != application.target_unit_instance_id
        or completion_payload.get("application") != application.to_payload()
        or completion_payload.get("destruction_evidence") != evidence.to_payload()
        or _mdcpv.json_identifier_list(
            completion_payload.get("physical_unit_instance_ids"),
            "mortal-wound completion physical_unit_instance_ids",
        )
        != expected_physical_ids
        or _mdcpv.json_identifier_list(
            completion_payload.get("rules_unit_instance_ids"),
            "mortal-wound completion rules_unit_instance_ids",
        )
        != expected_rules_ids
        or completion_payload.get("transition_batch") != expected_transition
        or removal_record.get("source_phase") != evidence.parent_battle_phase.value
        or removal_record.get("source_step") != evidence.source_step
    ):
        raise GameLifecycleError("Mortal-wound destruction completion binding drift.")


def _validate_rule_effect_cause_restore(
    *,
    state: GameState,
    authority: ModelDestructionCauseAuthority,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    context = authority.producer_context
    base_fields = {
        "context_kind",
        "completion_kind",
        "completion_event_type",
        "completion_event_payload",
        "source_rule_id",
        "source_result_id",
        "model_instance_id",
        "physical_unit_instance_id",
        "rules_unit_instance_id",
        "source_effect_ids",
        "source_phase",
        "source_step",
        "destroying_player_id",
        "source_rules_unit_instance_id",
        "source_model_instance_id",
        "destroyed_model_placement",
        "damage_application",
        "destruction_attribution",
        "mortal_wound_destruction_evidence",
        "parent_cause_ids",
        "referenced_result_ids",
    }
    expected_context_fields = set(base_fields)
    if authority.source_authority_finalized:
        expected_context_fields |= {
            "source_decision_record_ids",
            "model_destroyed_payload",
        }
    _mdcpv.require_exact_context_fields(
        context,
        expected=expected_context_fields,
        cause_kind="rule-effect",
    )
    expected_parents = _mdcpv.json_identifier_list(
        context.get("parent_cause_ids"),
        "rule destruction parent_cause_ids",
    )
    source_effect_ids = _mdcpv.json_identifier_list(
        context.get("source_effect_ids"),
        "rule destruction source_effect_ids",
    )
    referenced_result_ids = _mdcpv.json_identifier_list(
        context.get("referenced_result_ids"),
        "rule destruction referenced_result_ids",
    )
    attribution = ModelDestructionAttribution.from_model_destroyed_payload(
        context.get("destruction_attribution")
    )
    _validate_rule_effect_mode(
        state=state,
        context=context,
        authority=authority,
        attribution=attribution,
        parent_cause_ids=expected_parents,
        source_effect_ids=source_effect_ids,
    )
    if (
        context.get("context_kind") != _RULE_EFFECT_CONTEXT_KIND
        or _context_identifier(context, "source_result_id") != authority.producer_id
        or _context_identifier(context, "model_instance_id") != authority.model_instance_id
        or _context_identifier(context, "physical_unit_instance_id")
        != authority.physical_unit_instance_id
        or _context_identifier(context, "rules_unit_instance_id")
        != authority.rules_unit_instance_id
        or authority.parent_cause_ids != expected_parents
        or tuple(sorted(expected_parents)) != expected_parents
        or tuple(sorted(referenced_result_ids)) != referenced_result_ids
        or authority.producer_id not in referenced_result_ids
    ):
        raise GameLifecycleError("Rule destruction cause context binding drift.")
    if not authority.source_authority_finalized:
        if (
            authority.source_event_records
            or authority.source_decision_records
            or authority.model_destroyed_event is not None
        ):
            raise GameLifecycleError("Pending rule destruction cause has finalized sources.")
        return
    destroyed_event = _mdcpv.required_destroyed_event(authority)
    destroyed_payload = _mdcpv.json_object_value(
        destroyed_event.payload,
        "rule model_destroyed",
    )
    public_destroyed_payload = {
        key: value
        for key, value in destroyed_payload.items()
        if key != MODEL_DESTRUCTION_CAUSE_ID_FIELD
    }
    if public_destroyed_payload != context.get("model_destroyed_payload"):
        raise GameLifecycleError("Rule destruction cause payload binding drift.")
    destroyed_attribution = ModelDestructionAttribution.from_model_destroyed_payload(
        destroyed_payload
    )
    source_model_id = context.get("source_model_instance_id")
    if source_model_id is not None and (type(source_model_id) is not str or not source_model_id):
        raise GameLifecycleError("Rule destruction source model ID is invalid.")
    removal_record = _mdcpv.json_object_value(
        destroyed_payload.get("removal_record"),
        "rule destruction removal_record",
    )
    if (
        destroyed_payload.get("source_rule_id") != context.get("source_rule_id")
        or destroyed_payload.get("source_effect_ids") != list(source_effect_ids)
        or destroyed_payload.get("phase") != context.get("source_phase")
        or destroyed_payload.get("destroyed_model_placement")
        != context.get("destroyed_model_placement")
        or destroyed_payload.get("target_unit_instance_id") != authority.physical_unit_instance_id
        or destroyed_payload.get("damage_application") != context.get("damage_application")
        or destroyed_attribution != attribution
        or attribution.source_model_instance_id != source_model_id
        or removal_record.get("source_step") != context.get("source_step")
        or removal_record.get("source_event_id") != authority.producer_id
    ):
        raise GameLifecycleError("Rule destruction source binding drift.")
    _validate_parent_binding(
        state=state,
        authority=authority,
        attribution=attribution,
        context=context,
        context_parent_ids=expected_parents,
        exact_attack_parent=False,
    )
    stored_record_ids = _mdcpv.json_identifier_list(
        context.get("source_decision_record_ids"),
        "rule destruction source_decision_record_ids",
    )
    if expected_parents:
        expected_pairs: tuple[tuple[DecisionRecord, EventRecord], ...] = ()
    else:
        destroyed_event_index = _mdcpv.event_index(event_records, destroyed_event)
        candidate_pairs = tuple(
            (record, _decision_recorded_event_from_history(event_records, record))
            for record in decision_records
            if record.result.result_id in referenced_result_ids
        )
        expected_pairs = tuple(
            pair
            for pair in candidate_pairs
            if _mdcpv.event_index(event_records, pair[1]) < destroyed_event_index
        )
    expected_decisions = tuple(pair[0] for pair in expected_pairs)
    expected_events = tuple(pair[1] for pair in expected_pairs)
    if (
        stored_record_ids != tuple(record.record_id for record in expected_decisions)
        or authority.source_decision_records != expected_decisions
        or authority.source_event_records != expected_events
    ):
        raise GameLifecycleError("Rule destruction decision authority drift.")
    _mdccr.validate_rule_effect_completion_or_pending_window(
        state=state,
        authority=authority,
        attribution=attribution,
        event_records=event_records,
        pending_decision_requests=pending_decision_requests,
    )


def _validate_rule_effect_mode(
    *,
    state: GameState,
    context: dict[str, JsonValue],
    authority: ModelDestructionCauseAuthority,
    attribution: ModelDestructionAttribution,
    parent_cause_ids: tuple[str, ...],
    source_effect_ids: tuple[str, ...],
) -> None:
    from warhammer40k_core.engine.rule_deadly_demise_continuation import (
        RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND,
        RULE_MODEL_DESTRUCTION_COLLATERAL_COMPLETION_KIND,
        RULE_MODEL_DESTRUCTION_SOURCE_COMPLETION_KIND,
    )

    completion_kind = _context_identifier(context, "completion_kind")
    physical_unit_id = state.unit_instance_id_for_model(authority.model_instance_id)
    authority_views = current_rules_unit_views_for_canonical_identity(
        state=state,
        unit_instance_id=authority.rules_unit_instance_id,
    )
    if (
        physical_unit_id != authority.physical_unit_instance_id
        or all(physical_unit_id not in view.component_unit_instance_ids for view in authority_views)
        or attribution.destroying_player_id != context.get("destroying_player_id")
        or attribution.source_rules_unit_instance_id != context.get("source_rules_unit_instance_id")
        or attribution.source_model_instance_id != context.get("source_model_instance_id")
    ):
        raise GameLifecycleError("Rule destruction attribution context drift.")
    validate_destruction_source_identity(
        state=state,
        source_rules_unit_instance_id=attribution.source_rules_unit_instance_id,
        source_model_instance_id=attribution.source_model_instance_id,
        destroying_player_id=attribution.destroying_player_id,
    )
    raw_damage = context.get("damage_application")
    raw_evidence = context.get("mortal_wound_destruction_evidence")
    source_kind = attribution.destruction_provenance.destruction_source_kind
    if completion_kind == RULE_MODEL_DESTRUCTION_SOURCE_COMPLETION_KIND:
        if (
            parent_cause_ids
            or not source_effect_ids
            or raw_damage is not None
            or raw_evidence is not None
            or source_kind is not DestructionSourceKind.ABILITY
        ):
            raise GameLifecycleError("Source rule destruction cause mode drift.")
        return
    damage = _mdcpv.parse_damage_application(raw_damage)
    damage_target_views = current_rules_unit_views_for_canonical_identity(
        state=state,
        unit_instance_id=damage.target_unit_instance_id,
    )
    if (
        not damage.destroyed
        or damage.model_instance_id != authority.model_instance_id
        or damage.damage_kind.value != "mortal"
        or all(
            authority.physical_unit_instance_id not in view.component_unit_instance_ids
            for view in damage_target_views
        )
        or not rules_unit_identities_share_lineage(
            state=state,
            first_unit_instance_id=damage.target_unit_instance_id,
            second_unit_instance_id=authority.rules_unit_instance_id,
        )
    ):
        raise GameLifecycleError("Rule destruction damage binding drift.")
    if completion_kind == RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND:
        evidence = _mdcpv.parse_mortal_wound_destruction_evidence(raw_evidence)
        evidence.validate_for_state(state)
        if (
            parent_cause_ids
            or source_effect_ids
            or evidence.destruction_attribution != attribution
            or source_kind in {DestructionSourceKind.ATTACK, DestructionSourceKind.DEADLY_DEMISE}
        ):
            raise GameLifecycleError("Applied rule destruction cause mode drift.")
        return
    if (
        completion_kind != RULE_MODEL_DESTRUCTION_COLLATERAL_COMPLETION_KIND
        or len(parent_cause_ids) != 1
        or source_effect_ids
        or raw_evidence is not None
        or source_kind is not DestructionSourceKind.DEADLY_DEMISE
    ):
        raise GameLifecycleError("Collateral rule destruction cause mode drift.")


def _validate_attack_context_base(
    *,
    context: dict[str, JsonValue],
    authority: ModelDestructionCauseAuthority,
) -> tuple[str, str, tuple[str, ...]]:
    sequence_id = _context_identifier(context, "sequence_id")
    attack_context_id = _context_identifier(context, "attack_context_id")
    _context_identifier(context, "attacker_player_id")
    _context_identifier(context, "attacking_unit_instance_id")
    _context_identifier(context, "source_phase")
    damage = _mdcpv.parse_damage_application(context.get("damage_application"))
    parent_cause_ids = _mdcpv.json_identifier_list(
        context.get("parent_cause_ids"),
        "attack destruction parent_cause_ids",
    )
    if (
        context.get("context_kind") != _ATTACK_DAMAGE_CONTEXT_KIND
        or damage.to_payload() != context.get("damage_application")
        or damage.model_instance_id != authority.model_instance_id
        or not damage.destroyed
        or authority.parent_cause_ids != parent_cause_ids
        or tuple(sorted(parent_cause_ids)) != parent_cause_ids
        or len(parent_cause_ids) > 1
    ):
        raise GameLifecycleError("Attack destruction cause context binding drift.")
    return sequence_id, attack_context_id, parent_cause_ids


def _validate_pending_attack_parent(
    *,
    state: GameState,
    authority: ModelDestructionCauseAuthority,
    parent_cause_ids: tuple[str, ...],
) -> None:
    if not parent_cause_ids:
        return
    parent = model_destruction_cause_authority_by_id_or_none(
        state=state,
        cause_id=parent_cause_ids[0],
    )
    if (
        parent is None
        or parent.cause_kind is not ModelDestructionCauseKind.ATTACK_DAMAGE
        or parent.producer_id != authority.producer_id
        or parent.sequence_number >= authority.sequence_number
    ):
        raise GameLifecycleError("Pending attack destruction parent authority drift.")


def _decision_result_roots_attack_sequence_at_restore(
    *,
    state: GameState,
    sequence_id: str,
    attacking_unit_instance_id: str,
    battle_round: JsonValue,
    result_id: str,
) -> bool:
    expected_sequence_ids = {
        f"attack-sequence:{result_id}",
        f"out-of-phase-attack-sequence:{result_id}",
    }
    if type(battle_round) is int and battle_round > 0:
        expected_sequence_ids.add(
            f"melee-sequence:{state.game_id}:round-{battle_round:02d}:"
            f"{attacking_unit_instance_id}:{result_id}"
        )
    return sequence_id in expected_sequence_ids


def _decision_recorded_event_from_history(
    event_records: tuple[EventRecord, ...],
    decision_record: DecisionRecord,
) -> EventRecord:
    matches = tuple(
        event
        for event in event_records
        if event.event_type == "decision_recorded" and event.payload == decision_record.to_payload()
    )
    if len(matches) != 1:
        raise GameLifecycleError("Destruction cause decision lacks one recorded event.")
    return matches[0]


def _validate_parent_binding(
    *,
    state: GameState,
    authority: ModelDestructionCauseAuthority,
    attribution: ModelDestructionAttribution,
    context: dict[str, JsonValue],
    context_parent_ids: tuple[str, ...],
    exact_attack_parent: bool,
) -> None:
    source_kind = attribution.destruction_provenance.destruction_source_kind
    if source_kind is not DestructionSourceKind.DEADLY_DEMISE:
        if context_parent_ids or authority.parent_cause_ids:
            raise GameLifecycleError("Non-collateral destruction cannot carry parent authority.")
        return
    source_model_id = attribution.source_model_instance_id
    source_rules_unit_id = attribution.source_rules_unit_instance_id
    if (
        source_model_id is None
        or source_rules_unit_id is None
        or len(context_parent_ids) != 1
        or authority.parent_cause_ids != context_parent_ids
    ):
        raise GameLifecycleError("Deadly Demise destruction parent authority is invalid.")
    parent = model_destruction_cause_authority_by_id_or_none(
        state=state,
        cause_id=context_parent_ids[0],
    )
    if (
        parent is None
        or parent.sequence_number >= authority.sequence_number
        or parent.model_instance_id != source_model_id
        or parent.rules_unit_instance_id != source_rules_unit_id
    ):
        raise GameLifecycleError("Deadly Demise destruction parent identity drift.")
    if exact_attack_parent:
        expected_parent_id = model_destruction_cause_id(
            game_id=state.game_id,
            cause_kind=ModelDestructionCauseKind.ATTACK_DAMAGE,
            producer_id=authority.producer_id,
            model_instance_id=source_model_id,
        )
        if parent.cause_id != expected_parent_id:
            raise GameLifecycleError("Attack destruction parent cause drift.")
        if parent.cause_kind is not ModelDestructionCauseKind.ATTACK_DAMAGE or any(
            parent.producer_context.get(field_name) != context.get(field_name)
            for field_name in (
                "sequence_id",
                "attack_context_id",
                "attacker_player_id",
                "attacking_unit_instance_id",
                "source_phase",
            )
        ):
            raise GameLifecycleError("Attack destruction child source context drift.")


__all__ = (
    "PARENT_MODEL_DESTRUCTION_CAUSE_ID_FIELD",
    "append_rule_effect_model_destroyed_event",
    "attack_damage_model_destruction_cause_id",
    "attack_damage_model_destruction_cause_id_for_context",
    "attack_damage_model_destruction_producer_id",
    "attack_damage_model_destruction_producer_id_for_context",
    "consume_attack_damage_model_destruction_cause",
    "consume_mortal_wound_model_destruction_cause",
    "consume_rule_effect_model_destruction_cause",
    "finalize_attack_damage_model_destruction_cause",
    "record_mortal_wound_model_destruction_cause",
    "reserve_attack_damage_model_destruction_cause",
    "reserve_rule_effect_model_destruction_cause",
    "rule_effect_model_destruction_authority_context",
    "rule_effect_model_destruction_cause_id",
    "validate_model_destruction_cause_producer_restore",
    "validate_model_destruction_cause_restore",
)
