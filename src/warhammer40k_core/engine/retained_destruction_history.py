from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.attack_sequence_model import AttackSequencePayload
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.model_destruction_cause_attack_restore import (
    validate_pending_attack_destruction_boundary,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.retained_attack_permissions import retained_attack_selection
from warhammer40k_core.engine.retained_destruction_selection import (
    retention_request,
    validate_retention_grants,
)
from warhammer40k_core.engine.retained_destruction_state import (
    DestructionOwnerKind,
    RetainedDestructionStage,
    RetainedModelDestruction,
    destruction_cause_ancestor_ids,
    retained_destructions,
    validate_retained_placement,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.game_state import GameState


def validate_retained_destruction_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> tuple[RetainedModelDestruction, ...]:
    if any(
        isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind") == "fight_on_death_awaiting_attack"
        for effect in state.persisting_effects
    ) or any(
        event.event_type
        in {"fight_on_death_model_awaiting_attack", "fight_on_death_models_removed"}
        for event in event_records
    ):
        raise GameLifecycleError(
            "Obsolete Fight On Death removal-and-restoration authority is unsupported."
        )
    records: dict[str, RetainedModelDestruction] = {}
    opened: set[str] = set()
    decisions_by_result = {record.result.result_id: record for record in decision_records}
    causes = {cause.cause_id: cause for cause in state.model_destruction_cause_authorities}
    indexes = {event.event_id: index for index, event in enumerate(event_records)}
    opening_payloads: dict[str, dict[str, JsonValue]] = {}
    selection_indexes: dict[str, int] = {}
    for index, event in enumerate(event_records):
        if event.event_type == "fight_on_death_retention_opened":
            payload = _object(event.payload)
            from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
                core_fight_on_death_2026_09,
            )

            if (
                set(payload)
                != {
                    "game_id",
                    "battle_round",
                    "active_player_id",
                    "phase",
                    "source_rule_id",
                    "destruction",
                }
                or payload["game_id"] != state.game_id
                or type(payload["battle_round"]) is not int
                or payload["source_rule_id"] != core_fight_on_death_2026_09.FIGHT_ON_DEATH_SOURCE_ID
            ):
                raise GameLifecycleError("Fight On Death opening source authority drift.")
            record = RetainedModelDestruction.from_payload(payload.get("destruction"))
            if record.cause_id in opened or record.stage not in (
                RetainedDestructionStage.OFFERED,
                RetainedDestructionStage.NOT_TRIGGERED,
            ):
                raise GameLifecycleError(
                    "Fight On Death retention opened twice or in a completed state."
                )
            cause = causes.get(record.cause_id)
            if (
                cause is None
                or cause.model_instance_id != record.model_instance_id
                or cause.logical_death_event.event_id != record.logical_death_event_id
            ):
                raise GameLifecycleError("Fight On Death history logical-death identity drift.")
            logical_index = indexes.get(record.logical_death_event_id)
            if (
                logical_index is None
                or logical_index >= index
                or event_records[logical_index] != cause.logical_death_event
            ):
                raise GameLifecycleError("Fight On Death retention precedes its logical death.")
            if record.owner_kind is DestructionOwnerKind.ATTACK:
                sequence = AttackSequence.from_payload(
                    cast(AttackSequencePayload, record.owner_context)
                )
                pending = sequence.current_pending_attack_destruction
                if (
                    pending is None
                    or pending.damage_application.model_instance_id != record.model_instance_id
                    or pending.destroyed_model_placement != record.placement.to_payload()
                    or pending.destruction_sources != record.sources
                ):
                    raise GameLifecycleError(
                        "Fight On Death retained attack source snapshot drift."
                    )
                validate_pending_attack_destruction_boundary(
                    attack_sequence=sequence,
                    pending=pending,
                    event_records=event_records[:index],
                    pending_decision_requests=(),
                )
            elif record.owner_kind is DestructionOwnerKind.RULE:
                from warhammer40k_core.engine.model_destruction_cause_producers import (
                    rule_effect_model_destruction_authority_context,
                )

                if rule_effect_model_destruction_authority_context(
                    root_context=record.owner_context
                ) != {
                    key: value
                    for key, value in cause.producer_context.items()
                    if not cause.source_authority_finalized
                    or key not in {"source_decision_record_ids", "model_destroyed_payload"}
                }:
                    raise GameLifecycleError("Fight On Death rule source context drift.")
            opened.add(record.cause_id)
            from warhammer40k_core.engine.retained_destruction_trigger_history import (
                validate_retention_trigger_history,
            )

            validate_retention_trigger_history(
                record=record,
                cause=cause,
                battle_round=payload["battle_round"],
                active_player_id=_string(payload, "active_player_id"),
                phase=_string(payload, "phase"),
                event_records=event_records[:index],
            )
            opening_payloads[record.cause_id] = payload
            records[record.cause_id] = record
        elif event.event_type == "fight_on_death_retention_selected":
            payload = _object(event.payload)
            record = _record(records, payload)
            decision = decisions_by_result.get(_string(payload, "result_id"))
            if decision is None or decision.request != retention_request(record):
                raise GameLifecycleError(
                    "Fight On Death retained selection lacks its exact decision."
                )
            selected_id, action = retained_attack_selection(
                request=decision.request, result=decision.result
            )
            updated = replace(
                record,
                result_id=decision.result.result_id,
                selected_source_id=selected_id,
                selected_action=action,
                stage=RetainedDestructionStage.DECLINED
                if selected_id is None
                else RetainedDestructionStage.WAITING,
            )
            expected_payload = validate_json_value(
                {
                    "cause_id": record.cause_id,
                    "logical_death_event_id": record.logical_death_event_id,
                    "model_instance_id": record.model_instance_id,
                    "request_id": record.request_id,
                    "result_id": decision.result.result_id,
                    "selected_source_id": selected_id,
                    "selected_action": None if action is None else action.value,
                    "stage": updated.stage.value,
                    "model_placement": record.placement.to_payload(),
                }
            )
            if payload != expected_payload:
                raise GameLifecycleError("Fight On Death retained selection evidence drift.")
            records[record.cause_id] = updated
            selection_indexes[record.cause_id] = index
        elif event.event_type == "fight_on_death_destruction_ready":
            payload = _object(event.payload)
            record = _record(records, payload)
            if record.stage is not RetainedDestructionStage.WAITING:
                raise GameLifecycleError("Fight On Death completion boundary is duplicated.")
            reason = _string(payload, "reason")
            opening = opening_payloads[record.cause_id]
            if (
                set(payload)
                != {
                    "cause_id",
                    "model_instance_id",
                    "reason",
                    "unit_instance_id",
                    "battle_round",
                    "active_player_id",
                    "phase",
                }
                or payload["battle_round"] != opening["battle_round"]
                or payload["active_player_id"] != opening["active_player_id"]
                or payload["phase"] != opening["phase"]
            ):
                raise GameLifecycleError("Fight On Death cleanup timing authority drift.")
            interval = event_records[selection_indexes[record.cause_id] + 1 : index]
            if reason == "phase_end":
                boundaries = tuple(
                    previous
                    for previous in event_records[:index]
                    if previous.event_type == "end_boundary_objective_control_determined"
                    and isinstance(previous.payload, dict)
                    and previous.payload.get("battle_round") == payload.get("battle_round")
                    and previous.payload.get("phase") == payload.get("phase")
                    and any(
                        objective_record.active_player_id == payload["active_player_id"]
                        and previous.payload.get("record_ids") == [objective_record.record_id]
                        for objective_record in state.objective_control_records
                    )
                )
                if not boundaries or payload["unit_instance_id"] is not None:
                    raise GameLifecycleError("Fight On Death phase cleanup lacks its end boundary.")
            elif reason == "model_shoot_completed":
                boundaries = tuple(
                    previous
                    for previous in interval
                    if previous.event_type == "retained_shooting_attacks_completed"
                    and isinstance(previous.payload, dict)
                    and previous.payload.get("cause_id") == record.cause_id
                    and previous.payload.get("model_instance_id") == record.model_instance_id
                )
                if (
                    len(boundaries) != 1
                    or payload["unit_instance_id"] != record.placement.unit_instance_id
                ):
                    raise GameLifecycleError(
                        "Retained shooting cleanup lacks its completed model attack."
                    )
            elif reason == "unit_fight_completed":
                boundaries = tuple(
                    previous
                    for previous in interval
                    if previous.event_type == "unit_has_fought"
                    and isinstance(previous.payload, dict)
                    and previous.payload.get("battle_round") == opening["battle_round"]
                    and previous.payload.get("phase") == opening["phase"]
                    and isinstance(previous.payload.get("activation_selection"), dict)
                    and cast(dict[str, JsonValue], previous.payload["activation_selection"]).get(
                        "unit_instance_id"
                    )
                    == payload.get("unit_instance_id")
                )
                from warhammer40k_core.engine.rules_units import rules_unit_identities_share_lineage

                if not boundaries or not rules_unit_identities_share_lineage(
                    state=state,
                    first_unit_instance_id=_string(payload, "unit_instance_id"),
                    second_unit_instance_id=record.placement.unit_instance_id,
                ):
                    raise GameLifecycleError(
                        "Fight On Death unit cleanup lacks its completed activation."
                    )
            else:
                raise GameLifecycleError("Fight On Death completion reason is unsupported.")
            records[record.cause_id] = replace(
                record, stage=RetainedDestructionStage.READY, completion_reason=reason
            )
        elif event.event_type == "fight_on_death_destruction_suspended":
            payload = _object(event.payload)
            record = _record(records, payload)
            child_id = _string(payload, "child_cause_id")
            child = records.get(child_id)
            if (
                set(payload) != {"cause_id", "model_instance_id", "child_cause_id"}
                or record.stage
                not in (RetainedDestructionStage.READY, RetainedDestructionStage.RESOLVING)
                or child is None
                or child.stage is not RetainedDestructionStage.WAITING
                or record.cause_id
                not in destruction_cause_ancestor_ids(state=state, cause_id=child_id)
            ):
                raise GameLifecycleError("Retained destruction suspension ancestry drift.")
            records[record.cause_id] = replace(record, stage=RetainedDestructionStage.SUSPENDED)
        elif event.event_type == "fight_on_death_destruction_progressed":
            payload = _object(event.payload)
            record = _record(records, payload)
            if set(payload) != {
                "cause_id",
                "model_instance_id",
                "attack_sequence",
                "pending_request_ids",
            }:
                raise GameLifecycleError("Retained destruction progress fields drift.")
            progress = _object(payload["attack_sequence"])
            sequence = AttackSequence.from_payload(cast(AttackSequencePayload, progress))
            original_payload = (
                record.owner_context
                if record.owner_kind is DestructionOwnerKind.ATTACK
                else record.owner_context["attack_sequence"]
            )
            original = AttackSequence.from_payload(cast(AttackSequencePayload, original_payload))
            if (
                replace(
                    sequence,
                    pending_attack_destructions=original.pending_attack_destructions,
                    pending_destroyed_transport_disembark=original.pending_destroyed_transport_disembark,
                )
                != original
            ):
                raise GameLifecycleError("Retained destruction progress attack identity drift.")
            request_ids = payload["pending_request_ids"]
            if not isinstance(request_ids, list) or not request_ids:
                raise GameLifecycleError("Retained destruction progress lacks a pending decision.")
            for request_id in request_ids:
                if not any(
                    prior.event_type == "decision_requested"
                    and isinstance(prior.payload, dict)
                    and prior.payload.get("request_id") == request_id
                    for prior in event_records[:index]
                ):
                    raise GameLifecycleError(
                        "Retained destruction progress request authority drift."
                    )
            records[record.cause_id] = replace(
                record,
                stage=RetainedDestructionStage.RESOLVING
                if record.stage is RetainedDestructionStage.READY
                else record.stage,
                owner_progress=progress,
            )
        elif event.event_type == "model_destroyed":
            payload = _object(event.payload)
            matching = tuple(
                record
                for record in records.values()
                if record.model_instance_id == payload.get("model_instance_id")
            )
            for record in matching:
                if record.stage in (
                    RetainedDestructionStage.OFFERED,
                    RetainedDestructionStage.WAITING,
                ):
                    raise GameLifecycleError(
                        "Fight On Death model was removed before its completion boundary."
                    )
                if record.is_retained:
                    records[record.cause_id] = replace(
                        record, stage=RetainedDestructionStage.REMOVED
                    )
                else:
                    del records[record.cause_id]
        elif event.event_type == "fight_on_death_destruction_completed":
            payload = _object(event.payload)
            record = _record(records, payload)
            cause = causes[record.cause_id]
            if (
                record.stage is not RetainedDestructionStage.REMOVED
                or cause.model_destroyed_event is None
                or indexes[cause.model_destroyed_event.event_id] >= index
                or payload
                != {
                    "cause_id": record.cause_id,
                    "model_instance_id": record.model_instance_id,
                    "model_destroyed_event_id": cause.model_destroyed_event.event_id,
                    "reason": record.completion_reason,
                }
            ):
                raise GameLifecycleError("Fight On Death completion history drift.")
            del records[record.cause_id]
    current = retained_destructions(state=state)
    if {record.cause_id for record in current} != set(records):
        raise GameLifecycleError("Fight On Death retained continuation inventory drift.")
    for record in current:
        expected = records[record.cause_id]
        stage = (
            RetainedDestructionStage.READY
            if record.stage is RetainedDestructionStage.RESOLVING
            else record.stage
        )
        expected_stage = (
            RetainedDestructionStage.READY
            if expected.stage is RetainedDestructionStage.RESOLVING
            else expected.stage
        )
        if {**record.to_payload(), "stage": stage.value} != {
            **expected.to_payload(),
            "stage": expected_stage.value,
        }:
            raise GameLifecycleError(
                "Fight On Death retained state differs from its event history."
            )
        validate_retained_placement(state=state, record=record)
        if record.stage is RetainedDestructionStage.OFFERED:
            validate_retention_grants(state=state, record=record)
        if (
            record.owner_kind is DestructionOwnerKind.RULE
            and record.stage is not RetainedDestructionStage.REMOVED
        ):
            from warhammer40k_core.engine.rule_model_destruction_source_liabilities import (
                validate_rule_destruction_source_liabilities,
            )

            source_effect_ids = record.owner_context.get("source_effect_ids")
            if not isinstance(source_effect_ids, list) or any(
                type(value) is not str for value in source_effect_ids
            ):
                raise GameLifecycleError("Retained rule source liability inventory is invalid.")
            validate_rule_destruction_source_liabilities(
                state=state,
                source_effect_ids=cast(tuple[str, ...], tuple(source_effect_ids)),
                rules_unit_instance_id=_string(record.owner_context, "rules_unit_instance_id"),
            )
        if (
            record.stage is RetainedDestructionStage.OFFERED
            and sum(request == retention_request(record) for request in pending_decision_requests)
            != 1
        ):
            raise GameLifecycleError("Fight On Death retention lost its pending source request.")
    from warhammer40k_core.engine.retained_shooting_history import (
        validate_retained_shooting_history,
    )

    validate_retained_shooting_history(state=state, event_records=event_records)
    from warhammer40k_core.engine.model_attack_history import validate_retained_model_attack_history

    validate_retained_model_attack_history(
        event_records=event_records,
        model_instance_ids=frozenset(
            record.model_instance_id
            for opening in opening_payloads.values()
            for record in (RetainedModelDestruction.from_payload(opening["destruction"]),)
            if any(
                isinstance(source.payload, dict)
                and source.payload.get("requires_not_shot_or_fought_this_phase") is True
                for source in record.sources
            )
        ),
    )
    return current


def retained_attack_sequence_for_cause(
    *, state: GameState, records: tuple[RetainedModelDestruction, ...], cause_id: str
) -> AttackSequence | None:
    matches = tuple(
        record
        for record in records
        if record.owner_kind
        in (DestructionOwnerKind.ATTACK, DestructionOwnerKind.ATTACK_COLLATERAL)
        and (
            record.cause_id == cause_id
            or cause_id in destruction_cause_ancestor_ids(state=state, cause_id=record.cause_id)
        )
    )
    if not matches:
        return None
    nearest = min(
        matches,
        key=lambda record: len(
            destruction_cause_ancestor_ids(state=state, cause_id=record.cause_id)
        ),
    )
    context = (
        nearest.owner_context
        if nearest.owner_kind is DestructionOwnerKind.ATTACK
        else nearest.owner_context["attack_sequence"]
    )
    return AttackSequence.from_payload(cast(AttackSequencePayload, context))


def retained_model_ids_before_event(
    *, event_records: tuple[EventRecord, ...], event_index: int
) -> frozenset[str]:
    retained: set[str] = set()
    for event in event_records[:event_index]:
        if event.event_type == "fight_on_death_retention_selected":
            payload = _object(event.payload)
            if payload.get("selected_source_id") is not None:
                model_id = _string(payload, "model_instance_id")
                if model_id in retained:
                    raise GameLifecycleError("Historical Fight On Death presence is duplicated.")
                retained.add(model_id)
        elif event.event_type == "model_destroyed":
            retained.discard(_string(_object(event.payload), "model_instance_id"))
    return frozenset(retained)


def _record(
    records: dict[str, RetainedModelDestruction], payload: dict[str, JsonValue]
) -> RetainedModelDestruction:
    record = records.get(_string(payload, "cause_id"))
    if record is None or record.model_instance_id != payload.get("model_instance_id"):
        raise GameLifecycleError("Fight On Death history continuation identity drift.")
    return record


def _object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Fight On Death history payload must be an object.")
    return value


def _string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise GameLifecycleError("Fight On Death history identifier is invalid.")
    return value
