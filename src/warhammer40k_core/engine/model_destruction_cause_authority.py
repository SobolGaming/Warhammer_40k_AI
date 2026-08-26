from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_record import DecisionRecord, DecisionRecordPayload
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.event_log import (
    EventLogError,
    EventRecord,
    EventRecordPayload,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.model_logical_death import ModelLogicalDeathRecord


MODEL_DESTROYED_EVENT_TYPE = "model_destroyed"
MODEL_DESTRUCTION_CAUSE_ID_FIELD = "model_destruction_cause_id"
_MODEL_DESTRUCTION_CAUSE_ID_DOMAIN = "warhammer40k-core:model-destruction-cause-id:v1"
_MODEL_DESTRUCTION_CAUSE_ID_PREFIX = "model-destruction-cause"


class ModelDestructionCauseKind(StrEnum):
    ATTACK_DAMAGE = "attack_damage"
    MORTAL_WOUND = "mortal_wound"
    RULE_EFFECT = "rule_effect"


class ModelDestructionCauseAuthorityPayload(TypedDict):
    sequence_number: int
    game_id: str
    cause_id: str
    cause_kind: str
    producer_id: str
    model_instance_id: str
    physical_unit_instance_id: str
    rules_unit_instance_id: str
    logical_death_event: EventRecordPayload
    producer_context: dict[str, JsonValue]
    source_authority_finalized: bool
    source_event_records: list[EventRecordPayload]
    source_decision_records: list[DecisionRecordPayload]
    parent_cause_ids: list[str]
    model_destroyed_event: EventRecordPayload | None


@dataclass(frozen=True, slots=True)
class ModelDestructionCauseAuthority:
    """Producer-owned authority consumed by one model-destruction event."""

    sequence_number: int
    game_id: str
    cause_id: str
    cause_kind: ModelDestructionCauseKind
    producer_id: str
    model_instance_id: str
    physical_unit_instance_id: str
    rules_unit_instance_id: str
    logical_death_event: EventRecord
    producer_context: dict[str, JsonValue]
    source_authority_finalized: bool = True
    source_event_records: tuple[EventRecord, ...] = ()
    source_decision_records: tuple[DecisionRecord, ...] = ()
    parent_cause_ids: tuple[str, ...] = ()
    model_destroyed_event: EventRecord | None = None

    def __post_init__(self) -> None:
        if type(self.sequence_number) is not int or self.sequence_number <= 0:
            raise GameLifecycleError(
                "Model destruction cause authority sequence_number must be positive."
            )
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("Model destruction cause authority game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "cause_id",
            _validate_identifier("Model destruction cause authority cause_id", self.cause_id),
        )
        if type(self.cause_kind) is not ModelDestructionCauseKind:
            raise GameLifecycleError("Model destruction cause authority kind is invalid.")
        object.__setattr__(
            self,
            "producer_id",
            _validate_identifier(
                "Model destruction cause authority producer_id",
                self.producer_id,
            ),
        )
        for field_name in (
            "model_instance_id",
            "physical_unit_instance_id",
            "rules_unit_instance_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(
                    f"Model destruction cause authority {field_name}",
                    getattr(self, field_name),
                ),
            )
        expected_cause_id = model_destruction_cause_id(
            game_id=self.game_id,
            cause_kind=self.cause_kind,
            producer_id=self.producer_id,
            model_instance_id=self.model_instance_id,
        )
        if self.cause_id != expected_cause_id:
            raise GameLifecycleError("Model destruction cause authority identity drift.")
        if type(self.logical_death_event) is not EventRecord:
            raise GameLifecycleError(
                "Model destruction cause authority logical-death event is invalid."
            )
        _validate_logical_death_event_identity(
            event=self.logical_death_event,
            game_id=self.game_id,
            cause_id=self.cause_id,
            cause_kind=self.cause_kind,
            producer_id=self.producer_id,
            model_instance_id=self.model_instance_id,
            physical_unit_instance_id=self.physical_unit_instance_id,
            rules_unit_instance_id=self.rules_unit_instance_id,
        )
        producer_context = validate_json_value(self.producer_context)
        if not isinstance(producer_context, dict):
            raise GameLifecycleError(
                "Model destruction cause authority producer_context must be an object."
            )
        object.__setattr__(self, "producer_context", producer_context)
        if type(self.source_authority_finalized) is not bool:
            raise GameLifecycleError(
                "Model destruction cause source_authority_finalized must be a bool."
            )
        if not self.source_authority_finalized and (
            self.source_event_records or self.source_decision_records
        ):
            raise GameLifecycleError(
                "Pending model destruction cause authority cannot carry finalized sources."
            )
        _validate_typed_tuple(
            self.source_event_records,
            item_type=EventRecord,
            field_name="source_event_records",
        )
        _validate_typed_tuple(
            self.source_decision_records,
            item_type=DecisionRecord,
            field_name="source_decision_records",
        )
        source_event_ids = tuple(record.event_id for record in self.source_event_records)
        if len(source_event_ids) != len(set(source_event_ids)):
            raise GameLifecycleError(
                "Model destruction cause authority source events must be unique."
            )
        source_decision_ids = tuple(record.record_id for record in self.source_decision_records)
        if len(source_decision_ids) != len(set(source_decision_ids)):
            raise GameLifecycleError(
                "Model destruction cause authority source decisions must be unique."
            )
        parent_cause_ids = _validate_identifier_tuple(
            "Model destruction cause authority parent_cause_ids",
            self.parent_cause_ids,
        )
        if parent_cause_ids != tuple(sorted(parent_cause_ids)):
            raise GameLifecycleError(
                "Model destruction cause authority parent_cause_ids must be sorted."
            )
        if self.cause_id in parent_cause_ids:
            raise GameLifecycleError("Model destruction cause authority cannot parent itself.")
        object.__setattr__(self, "parent_cause_ids", parent_cause_ids)
        if self.model_destroyed_event is not None:
            if not self.source_authority_finalized:
                raise GameLifecycleError(
                    "Consumed model destruction cause authority must be finalized."
                )
            if type(self.model_destroyed_event) is not EventRecord:
                raise GameLifecycleError(
                    "Model destruction cause authority consumed event is invalid."
                )
            _validate_consumed_event(authority=self, event=self.model_destroyed_event)

    @property
    def is_consumed(self) -> bool:
        return self.model_destroyed_event is not None

    def consume(self, event: EventRecord) -> Self:
        if self.model_destroyed_event is not None:
            raise GameLifecycleError("Model destruction cause authority was consumed twice.")
        if type(event) is not EventRecord:
            raise GameLifecycleError(
                "Model destruction cause authority consumption requires EventRecord."
            )
        if not self.source_authority_finalized:
            raise GameLifecycleError(
                "Model destruction cause authority must be finalized before consumption."
            )
        consumed = replace(self, model_destroyed_event=event)
        _validate_consumed_event(authority=consumed, event=event)
        return consumed

    def finalize_source_authority(
        self,
        *,
        producer_context: dict[str, JsonValue],
        source_event_records: tuple[EventRecord, ...],
        source_decision_records: tuple[DecisionRecord, ...],
    ) -> Self:
        if self.model_destroyed_event is not None:
            raise GameLifecycleError(
                "Consumed model destruction cause authority cannot be finalized again."
            )
        finalized = replace(
            self,
            producer_context=producer_context,
            source_authority_finalized=True,
            source_event_records=source_event_records,
            source_decision_records=source_decision_records,
        )
        if self.source_authority_finalized and finalized != self:
            raise GameLifecycleError(
                "Model destruction cause source authority was finalized twice."
            )
        return finalized

    def to_payload(self) -> ModelDestructionCauseAuthorityPayload:
        return {
            "sequence_number": self.sequence_number,
            "game_id": self.game_id,
            "cause_id": self.cause_id,
            "cause_kind": self.cause_kind.value,
            "producer_id": self.producer_id,
            "model_instance_id": self.model_instance_id,
            "physical_unit_instance_id": self.physical_unit_instance_id,
            "rules_unit_instance_id": self.rules_unit_instance_id,
            "logical_death_event": self.logical_death_event.to_payload(),
            "producer_context": self.producer_context,
            "source_authority_finalized": self.source_authority_finalized,
            "source_event_records": [record.to_payload() for record in self.source_event_records],
            "source_decision_records": [
                record.to_payload() for record in self.source_decision_records
            ],
            "parent_cause_ids": list(self.parent_cause_ids),
            "model_destroyed_event": (
                None
                if self.model_destroyed_event is None
                else self.model_destroyed_event.to_payload()
            ),
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        expected_fields = {
            "sequence_number",
            "game_id",
            "cause_id",
            "cause_kind",
            "producer_id",
            "model_instance_id",
            "physical_unit_instance_id",
            "rules_unit_instance_id",
            "logical_death_event",
            "producer_context",
            "source_authority_finalized",
            "source_event_records",
            "source_decision_records",
            "parent_cause_ids",
            "model_destroyed_event",
        }
        raw = _payload_object(
            payload,
            field_name="payload",
            expected_fields=expected_fields,
        )
        sequence_number = raw["sequence_number"]
        if type(sequence_number) is not int:
            raise GameLifecycleError(
                "Model destruction cause authority sequence_number must be an int."
            )
        for field_name in (
            "game_id",
            "cause_id",
            "cause_kind",
            "producer_id",
            "model_instance_id",
            "physical_unit_instance_id",
            "rules_unit_instance_id",
        ):
            if type(raw[field_name]) is not str:
                raise GameLifecycleError(
                    f"Model destruction cause authority {field_name} must be a string."
                )
        raw_cause_kind = cast(str, raw["cause_kind"])
        try:
            cause_kind = ModelDestructionCauseKind(raw_cause_kind)
        except ValueError as exc:
            raise GameLifecycleError(
                "Model destruction cause authority kind is unsupported."
            ) from exc
        producer_context = _payload_json_object(
            raw["producer_context"],
            field_name="producer_context",
        )
        logical_death_event = _event_record_from_payload(
            raw["logical_death_event"],
            field_name="logical_death_event",
        )
        source_authority_finalized = raw["source_authority_finalized"]
        if type(source_authority_finalized) is not bool:
            raise GameLifecycleError(
                "Model destruction cause source_authority_finalized must be a bool."
            )
        source_event_records = tuple(
            _event_record_from_payload(
                value,
                field_name=f"source_event_records[{index}]",
            )
            for index, value in enumerate(_payload_list(raw, field_name="source_event_records"))
        )
        source_decision_records = tuple(
            _decision_record_from_payload(
                value,
                field_name=f"source_decision_records[{index}]",
            )
            for index, value in enumerate(_payload_list(raw, field_name="source_decision_records"))
        )
        parent_cause_ids = tuple(_payload_list_of_strings(raw, field_name="parent_cause_ids"))
        raw_destroyed_event = raw["model_destroyed_event"]
        if raw_destroyed_event is not None:
            destroyed_event = _event_record_from_payload(
                raw_destroyed_event,
                field_name="model_destroyed_event",
            )
        else:
            destroyed_event = None
        return cls(
            sequence_number=sequence_number,
            game_id=cast(str, raw["game_id"]),
            cause_id=cast(str, raw["cause_id"]),
            cause_kind=cause_kind,
            producer_id=cast(str, raw["producer_id"]),
            model_instance_id=cast(str, raw["model_instance_id"]),
            physical_unit_instance_id=cast(str, raw["physical_unit_instance_id"]),
            rules_unit_instance_id=cast(str, raw["rules_unit_instance_id"]),
            logical_death_event=logical_death_event,
            producer_context=producer_context,
            source_authority_finalized=source_authority_finalized,
            source_event_records=source_event_records,
            source_decision_records=source_decision_records,
            parent_cause_ids=parent_cause_ids,
            model_destroyed_event=destroyed_event,
        )


def model_destruction_cause_id(
    *,
    game_id: str,
    cause_kind: ModelDestructionCauseKind,
    producer_id: str,
    model_instance_id: str,
) -> str:
    requested_game_id = _validate_identifier("Model destruction cause game_id", game_id)
    if type(cause_kind) is not ModelDestructionCauseKind:
        raise GameLifecycleError("Model destruction cause kind is invalid.")
    requested_producer_id = _validate_identifier(
        "Model destruction cause producer_id",
        producer_id,
    )
    requested_model_id = _validate_identifier(
        "Model destruction cause model_instance_id",
        model_instance_id,
    )
    identity_payload: dict[str, JsonValue] = {
        "domain": _MODEL_DESTRUCTION_CAUSE_ID_DOMAIN,
        "game_id": requested_game_id,
        "cause_kind": cause_kind.value,
        "producer_id": requested_producer_id,
        "model_instance_id": requested_model_id,
    }
    digest = sha256(canonical_json(identity_payload).encode("utf-8")).hexdigest()
    return f"{_MODEL_DESTRUCTION_CAUSE_ID_PREFIX}:{cause_kind.value}:sha256:{digest}"


def record_model_destruction_cause_authority(
    state: GameState,
    authority: ModelDestructionCauseAuthority,
) -> None:
    if type(authority) is not ModelDestructionCauseAuthority:
        raise GameLifecycleError("GameState model destruction cause authority is invalid.")
    state.replace_model_destruction_cause_authorities(
        [*state.model_destruction_cause_authorities, authority]
    )


def consume_model_destruction_cause_authority(
    state: GameState,
    *,
    cause_id: str,
    model_destroyed_event: EventRecord,
) -> ModelDestructionCauseAuthority:
    requested_cause_id = _validate_identifier(
        "Model destruction cause authority cause_id",
        cause_id,
    )
    matches = tuple(
        (index, authority)
        for index, authority in enumerate(state.model_destruction_cause_authorities)
        if authority.cause_id == requested_cause_id
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Model destruction cause consumption requires one pending authority."
        )
    index, authority = matches[0]
    consumed = authority.consume(model_destroyed_event)
    updated = list(state.model_destruction_cause_authorities)
    updated[index] = consumed
    state.replace_model_destruction_cause_authorities(updated)
    return consumed


def finalize_model_destruction_cause_authority(
    state: GameState,
    *,
    cause_id: str,
    producer_context: dict[str, JsonValue],
    source_event_records: tuple[EventRecord, ...],
    source_decision_records: tuple[DecisionRecord, ...] = (),
) -> ModelDestructionCauseAuthority:
    requested_cause_id = _validate_identifier(
        "Model destruction cause authority cause_id",
        cause_id,
    )
    matches = tuple(
        (index, authority)
        for index, authority in enumerate(state.model_destruction_cause_authorities)
        if authority.cause_id == requested_cause_id
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Model destruction cause finalization requires one pending authority."
        )
    index, authority = matches[0]
    finalized = authority.finalize_source_authority(
        producer_context=producer_context,
        source_event_records=source_event_records,
        source_decision_records=source_decision_records,
    )
    updated = list(state.model_destruction_cause_authorities)
    updated[index] = finalized
    state.replace_model_destruction_cause_authorities(updated)
    return finalized


def record_model_destruction_cause(
    state: GameState,
    *,
    cause_kind: ModelDestructionCauseKind,
    producer_id: str,
    model_instance_id: str,
    physical_unit_instance_id: str,
    rules_unit_instance_id: str,
    logical_death_event: EventRecord,
    producer_context: dict[str, JsonValue],
    source_event_records: tuple[EventRecord, ...] = (),
    source_decision_records: tuple[DecisionRecord, ...] = (),
    parent_cause_ids: tuple[str, ...] = (),
    source_authority_finalized: bool = True,
) -> ModelDestructionCauseAuthority:
    cause_id = model_destruction_cause_id(
        game_id=state.game_id,
        cause_kind=cause_kind,
        producer_id=producer_id,
        model_instance_id=model_instance_id,
    )
    existing = model_destruction_cause_authority_by_id_or_none(
        state=state,
        cause_id=cause_id,
    )
    if existing is not None:
        expected = ModelDestructionCauseAuthority(
            sequence_number=existing.sequence_number,
            game_id=state.game_id,
            cause_id=cause_id,
            cause_kind=cause_kind,
            producer_id=producer_id,
            model_instance_id=model_instance_id,
            physical_unit_instance_id=physical_unit_instance_id,
            rules_unit_instance_id=rules_unit_instance_id,
            logical_death_event=logical_death_event,
            producer_context=producer_context,
            source_authority_finalized=source_authority_finalized,
            source_event_records=source_event_records,
            source_decision_records=source_decision_records,
            parent_cause_ids=tuple(sorted(parent_cause_ids)),
        )
        if existing != expected:
            raise GameLifecycleError("Model destruction cause authority identity drift.")
        return existing
    authority = ModelDestructionCauseAuthority(
        sequence_number=len(state.model_destruction_cause_authorities) + 1,
        game_id=state.game_id,
        cause_id=cause_id,
        cause_kind=cause_kind,
        producer_id=producer_id,
        model_instance_id=model_instance_id,
        physical_unit_instance_id=physical_unit_instance_id,
        rules_unit_instance_id=rules_unit_instance_id,
        logical_death_event=logical_death_event,
        producer_context=producer_context,
        source_authority_finalized=source_authority_finalized,
        source_event_records=source_event_records,
        source_decision_records=source_decision_records,
        parent_cause_ids=tuple(sorted(parent_cause_ids)),
    )
    record_model_destruction_cause_authority(state, authority)
    return authority


def consume_model_destruction_cause(
    state: GameState,
    *,
    cause_id: str,
    model_destroyed_event: EventRecord,
) -> ModelDestructionCauseAuthority:
    return consume_model_destruction_cause_authority(
        state,
        cause_id=cause_id,
        model_destroyed_event=model_destroyed_event,
    )


def finalize_model_destruction_cause(
    state: GameState,
    *,
    cause_id: str,
    producer_context: dict[str, JsonValue],
    source_event_records: tuple[EventRecord, ...],
    source_decision_records: tuple[DecisionRecord, ...] = (),
) -> ModelDestructionCauseAuthority:
    return finalize_model_destruction_cause_authority(
        state,
        cause_id=cause_id,
        producer_context=producer_context,
        source_event_records=source_event_records,
        source_decision_records=source_decision_records,
    )


def record_consumed_model_destruction_cause(
    state: GameState,
    *,
    cause_kind: ModelDestructionCauseKind,
    producer_id: str,
    model_instance_id: str,
    physical_unit_instance_id: str,
    rules_unit_instance_id: str,
    logical_death_event: EventRecord,
    producer_context: dict[str, JsonValue],
    model_destroyed_event: EventRecord,
    source_event_records: tuple[EventRecord, ...] = (),
    source_decision_records: tuple[DecisionRecord, ...] = (),
    parent_cause_ids: tuple[str, ...] = (),
) -> ModelDestructionCauseAuthority:
    pending = record_model_destruction_cause(
        state,
        cause_kind=cause_kind,
        producer_id=producer_id,
        model_instance_id=model_instance_id,
        physical_unit_instance_id=physical_unit_instance_id,
        rules_unit_instance_id=rules_unit_instance_id,
        logical_death_event=logical_death_event,
        producer_context=producer_context,
        source_event_records=source_event_records,
        source_decision_records=source_decision_records,
        parent_cause_ids=parent_cause_ids,
        source_authority_finalized=True,
    )
    return consume_model_destruction_cause(
        state,
        cause_id=pending.cause_id,
        model_destroyed_event=model_destroyed_event,
    )


def model_destruction_cause_authority_by_id_or_none(
    *,
    state: GameState,
    cause_id: str,
) -> ModelDestructionCauseAuthority | None:
    requested_cause_id = _validate_identifier("Model destruction cause_id", cause_id)
    matches = tuple(
        authority
        for authority in state.model_destruction_cause_authorities
        if authority.cause_id == requested_cause_id
    )
    if len(matches) > 1:
        raise GameLifecycleError("Model destruction cause authority is duplicated.")
    return None if not matches else matches[0]


def consumed_model_destruction_cause_authority_for_event(
    *,
    state: GameState,
    event: EventRecord,
) -> ModelDestructionCauseAuthority:
    """Return the single producer authority consumed by ``event``.

    This lookup deliberately requires the exact immutable event record stored by
    the producer-owned authority.  A payload that merely resembles a valid
    ``model_destroyed`` event is not authoritative.
    """

    if type(event) is not EventRecord or event.event_type != MODEL_DESTROYED_EVENT_TYPE:
        raise GameLifecycleError(
            "Model destruction cause lookup requires a model_destroyed EventRecord."
        )
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("model_destroyed payload must be an object.")
    raw_cause_id = event.payload.get(MODEL_DESTRUCTION_CAUSE_ID_FIELD)
    if type(raw_cause_id) is not str:
        raise GameLifecycleError(
            "model_destroyed event is missing its producer-owned cause authority."
        )
    authority = model_destruction_cause_authority_by_id_or_none(
        state=state,
        cause_id=raw_cause_id,
    )
    if authority is None or authority.model_destroyed_event != event:
        raise GameLifecycleError(
            "model_destroyed event does not consume its exact cause authority."
        )
    return authority


def validate_model_destruction_cause_authorities(
    authorities: object,
    *,
    game_id: str,
) -> list[ModelDestructionCauseAuthority]:
    requested_game_id = _validate_identifier(
        "Model destruction cause authority game_id",
        game_id,
    )
    if not isinstance(authorities, list):
        raise GameLifecycleError(
            "GameState model destruction cause authorities must be typed records."
        )
    raw_authorities = cast(list[object], authorities)
    if any(type(authority) is not ModelDestructionCauseAuthority for authority in raw_authorities):
        raise GameLifecycleError(
            "GameState model destruction cause authorities must be typed records."
        )
    typed = cast(list[ModelDestructionCauseAuthority], authorities)
    cause_ids: set[str] = set()
    logical_death_event_ids: set[str] = set()
    logical_death_boundary_ids: set[str] = set()
    destroyed_event_ids: set[str] = set()
    for sequence_number, authority in enumerate(typed, start=1):
        if authority.sequence_number != sequence_number:
            raise GameLifecycleError("Model destruction cause authority sequence is non-canonical.")
        if authority.game_id != requested_game_id:
            raise GameLifecycleError("Model destruction cause authority game drift.")
        if authority.cause_id in cause_ids:
            raise GameLifecycleError("Model destruction cause authority ID is duplicated.")
        missing_parent_ids = set(authority.parent_cause_ids) - cause_ids
        if missing_parent_ids:
            raise GameLifecycleError(
                "Model destruction cause authority parent must be registered first."
            )
        cause_ids.add(authority.cause_id)
        logical_event_id = authority.logical_death_event.event_id
        if logical_event_id in logical_death_event_ids:
            raise GameLifecycleError(
                "Model logical-death event belongs to more than one cause authority."
            )
        logical_death_event_ids.add(logical_event_id)
        logical_record = _logical_death_record_from_event(authority.logical_death_event)
        if logical_record.boundary_id in logical_death_boundary_ids:
            raise GameLifecycleError("Model logical-death boundary ID is duplicated.")
        logical_death_boundary_ids.add(logical_record.boundary_id)
        if authority.model_destroyed_event is None:
            continue
        event_id = authority.model_destroyed_event.event_id
        if event_id in destroyed_event_ids:
            raise GameLifecycleError(
                "Model destruction event consumed more than one cause authority."
            )
        destroyed_event_ids.add(event_id)
    return list(typed)


def validate_model_destruction_cause_authority_restore(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    authorities = validate_model_destruction_cause_authorities(
        state.model_destruction_cause_authorities,
        game_id=state.game_id,
    )
    events_by_id = {event.event_id: event for event in event_records}
    decisions_by_id = {record.record_id: record for record in decision_records}
    event_indexes = {event.event_id: index for index, event in enumerate(event_records)}
    consumed_by_event_id: dict[str, ModelDestructionCauseAuthority] = {}
    logical_death_indexes: list[int] = []
    for authority in authorities:
        logical_death_event = authority.logical_death_event
        if events_by_id.get(logical_death_event.event_id) != logical_death_event:
            raise GameLifecycleError("Model destruction cause logical-death event drift.")
        logical_death_index = event_indexes[logical_death_event.event_id]
        logical_death_indexes.append(logical_death_index)
        source_event_indexes: list[int] = []
        for source_event in authority.source_event_records:
            if events_by_id.get(source_event.event_id) != source_event:
                raise GameLifecycleError("Model destruction cause source event authority drift.")
            source_event_indexes.append(event_indexes[source_event.event_id])
        if source_event_indexes != sorted(source_event_indexes):
            raise GameLifecycleError(
                "Model destruction cause source events are not in canonical history order."
            )
        for source_decision in authority.source_decision_records:
            if decisions_by_id.get(source_decision.record_id) != source_decision:
                raise GameLifecycleError("Model destruction cause source decision authority drift.")
            matches = tuple(
                event
                for event in event_records
                if event.event_type == "decision_recorded"
                and event.payload == source_decision.to_payload()
            )
            if len(matches) != 1:
                raise GameLifecycleError(
                    "Model destruction cause decision lacks its authoritative event."
                )
            if matches[0] not in authority.source_event_records:
                raise GameLifecycleError(
                    "Model destruction cause decision event is missing from source authority."
                )
        destroyed_event = authority.model_destroyed_event
        if destroyed_event is None:
            continue
        canonical_event = events_by_id.get(destroyed_event.event_id)
        if canonical_event != destroyed_event:
            raise GameLifecycleError("Model destruction cause consumed event drift.")
        destroyed_index = event_indexes[destroyed_event.event_id]
        if logical_death_index >= destroyed_index:
            raise GameLifecycleError(
                "Model logical death must precede model-destruction consumption."
            )
        if any(
            event_indexes[source_event.event_id] >= destroyed_index
            for source_event in authority.source_event_records
        ):
            raise GameLifecycleError(
                "Model destruction cause source event must precede consumption."
            )
        consumed_by_event_id[destroyed_event.event_id] = authority
    if logical_death_indexes != sorted(logical_death_indexes):
        raise GameLifecycleError(
            "Model logical-death events do not follow cause-authority sequence."
        )
    authorities_by_id = {authority.cause_id: authority for authority in authorities}
    for child in authorities:
        for parent_cause_id in child.parent_cause_ids:
            parent = authorities_by_id[parent_cause_id]
            if (
                event_indexes[parent.logical_death_event.event_id]
                >= event_indexes[child.logical_death_event.event_id]
            ):
                raise GameLifecycleError(
                    "Parent model logical death must precede child logical death."
                )
            parent_event = parent.model_destroyed_event
            if parent_event is None:
                continue
            child_event = child.model_destroyed_event
            if child_event is None:
                raise GameLifecycleError(
                    "Consumed model destruction cause parent has an unconsumed child."
                )
            if event_indexes[child_event.event_id] >= event_indexes[parent_event.event_id]:
                raise GameLifecycleError(
                    "Model destruction cause child must be consumed before its parent."
                )
    cause_aware_destroyed_events = tuple(
        event
        for event in event_records
        if event.event_type == MODEL_DESTROYED_EVENT_TYPE
        and isinstance(event.payload, dict)
        and MODEL_DESTRUCTION_CAUSE_ID_FIELD in event.payload
    )
    if len(consumed_by_event_id) != len(cause_aware_destroyed_events) or any(
        event.event_id not in consumed_by_event_id for event in cause_aware_destroyed_events
    ):
        raise GameLifecycleError(
            "Every cause-aware model_destroyed event must consume exactly one cause authority."
        )


def _validate_consumed_event(
    *,
    authority: ModelDestructionCauseAuthority,
    event: EventRecord,
) -> None:
    if event.event_type != MODEL_DESTROYED_EVENT_TYPE or not isinstance(event.payload, dict):
        raise GameLifecycleError(
            "Model destruction cause authority requires a model_destroyed event."
        )
    payload = event.payload
    placement = payload.get("destroyed_model_placement")
    if not isinstance(placement, dict):
        raise GameLifecycleError(
            "Model destruction cause authority requires destroyed placement evidence."
        )
    event_rules_unit_id = payload.get("rules_unit_instance_id")
    if (
        type(event_rules_unit_id) is not str
        or not event_rules_unit_id
        or payload.get(MODEL_DESTRUCTION_CAUSE_ID_FIELD) != authority.cause_id
        or payload.get("game_id") != authority.game_id
        or payload.get("model_instance_id") != authority.model_instance_id
        or placement.get("model_instance_id") != authority.model_instance_id
        or placement.get("unit_instance_id") != authority.physical_unit_instance_id
        or event_rules_unit_id != authority.rules_unit_instance_id
    ):
        raise GameLifecycleError("Model destruction cause consumption identity drift.")
    if authority.cause_kind is ModelDestructionCauseKind.ATTACK_DAMAGE:
        damage_event_id = payload.get("damage_event_id")
        if type(damage_event_id) is not str or not any(
            source.event_id == damage_event_id for source in authority.source_event_records
        ):
            raise GameLifecycleError("Attack destruction cause damage-event drift.")
    elif authority.cause_kind is ModelDestructionCauseKind.MORTAL_WOUND:
        if payload.get("mortal_wound_application_id") != authority.producer_id:
            raise GameLifecycleError("Mortal-wound destruction cause application drift.")
    elif payload.get("source_rule_id") != authority.producer_context.get("source_rule_id"):
        raise GameLifecycleError("Rule destruction cause source-rule drift.")


def _validate_logical_death_event_identity(
    *,
    event: EventRecord,
    game_id: str,
    cause_id: str,
    cause_kind: ModelDestructionCauseKind,
    producer_id: str,
    model_instance_id: str,
    physical_unit_instance_id: str,
    rules_unit_instance_id: str,
) -> ModelLogicalDeathRecord:
    from warhammer40k_core.engine.model_logical_death import (
        validate_model_logical_death_event_identity,
    )

    return validate_model_logical_death_event_identity(
        event=event,
        game_id=game_id,
        cause_id=cause_id,
        cause_kind=cause_kind,
        producer_id=producer_id,
        model_instance_id=model_instance_id,
        physical_unit_instance_id=physical_unit_instance_id,
        rules_unit_instance_id=rules_unit_instance_id,
    )


def _logical_death_record_from_event(event: EventRecord) -> ModelLogicalDeathRecord:
    from warhammer40k_core.engine.model_logical_death import (
        model_logical_death_record_from_event,
    )

    return model_logical_death_record_from_event(event)


def _payload_object(
    value: object,
    *,
    field_name: str,
    expected_fields: set[str],
) -> dict[str, object]:
    if type(value) is not dict:
        raise GameLifecycleError(
            f"Model destruction cause authority {field_name} must be an object."
        )
    raw = cast(dict[object, object], value)
    if any(type(key) is not str for key in raw) or set(raw) != expected_fields:
        raise GameLifecycleError(
            f"Model destruction cause authority {field_name} fields are invalid."
        )
    return cast(dict[str, object], raw)


def _payload_json_object(value: object, *, field_name: str) -> dict[str, JsonValue]:
    if type(value) is not dict:
        raise GameLifecycleError(
            f"Model destruction cause authority {field_name} must be an object."
        )
    raw = cast(dict[object, object], value)
    try:
        validated = validate_json_value(raw)
    except EventLogError as exc:
        raise GameLifecycleError(
            f"Model destruction cause authority {field_name} must be JSON-safe."
        ) from exc
    if not isinstance(validated, dict):
        raise GameLifecycleError(
            f"Model destruction cause authority {field_name} must be an object."
        )
    return validated


def _payload_list(payload: dict[str, object], *, field_name: str) -> list[object]:
    value = payload[field_name]
    if type(value) is not list:
        raise GameLifecycleError(f"Model destruction cause authority {field_name} must be a list.")
    return cast(list[object], value)


def _payload_list_of_strings(
    payload: dict[str, object],
    *,
    field_name: str,
) -> list[str]:
    values = _payload_list(payload, field_name=field_name)
    if any(type(value) is not str for value in values):
        raise GameLifecycleError(
            f"Model destruction cause authority {field_name} must contain strings."
        )
    return cast(list[str], values)


def _event_record_from_payload(value: object, *, field_name: str) -> EventRecord:
    raw = _payload_object(
        value,
        field_name=field_name,
        expected_fields={"event_id", "event_type", "payload"},
    )
    if type(raw["event_id"]) is not str or type(raw["event_type"]) is not str:
        raise GameLifecycleError(
            f"Model destruction cause authority {field_name} identifiers must be strings."
        )
    try:
        return EventRecord.from_payload(cast(EventRecordPayload, raw))
    except EventLogError as exc:
        raise GameLifecycleError(
            f"Model destruction cause authority {field_name} is invalid."
        ) from exc


def _decision_record_from_payload(value: object, *, field_name: str) -> DecisionRecord:
    raw = _payload_object(
        value,
        field_name=field_name,
        expected_fields={"record_id", "request", "result"},
    )
    if type(raw["record_id"]) is not str:
        raise GameLifecycleError(
            f"Model destruction cause authority {field_name}.record_id must be a string."
        )
    _validate_decision_request_payload_shape(
        raw["request"],
        field_name=f"{field_name}.request",
    )
    _validate_decision_result_payload_shape(
        raw["result"],
        field_name=f"{field_name}.result",
    )
    try:
        return DecisionRecord.from_payload(cast(DecisionRecordPayload, raw))
    except (DecisionError, EventLogError) as exc:
        raise GameLifecycleError(
            f"Model destruction cause authority {field_name} is invalid."
        ) from exc


def _validate_decision_request_payload_shape(value: object, *, field_name: str) -> None:
    raw = _payload_object(
        value,
        field_name=field_name,
        expected_fields={"request_id", "decision_type", "actor_id", "payload", "options"},
    )
    if type(raw["request_id"]) is not str or type(raw["decision_type"]) is not str:
        raise GameLifecycleError(
            f"Model destruction cause authority {field_name} identifiers must be strings."
        )
    actor_id = raw["actor_id"]
    if actor_id is not None and type(actor_id) is not str:
        raise GameLifecycleError(
            f"Model destruction cause authority {field_name}.actor_id is invalid."
        )
    for index, option in enumerate(_payload_list(raw, field_name="options")):
        option_field_name = f"{field_name}.options[{index}]"
        option_raw = _payload_object(
            option,
            field_name=option_field_name,
            expected_fields={"option_id", "label", "payload"},
        )
        if type(option_raw["option_id"]) is not str or type(option_raw["label"]) is not str:
            raise GameLifecycleError(
                f"Model destruction cause authority {option_field_name} identifiers "
                "must be strings."
            )


def _validate_decision_result_payload_shape(value: object, *, field_name: str) -> None:
    raw = _payload_object(
        value,
        field_name=field_name,
        expected_fields={
            "result_id",
            "request_id",
            "decision_type",
            "actor_id",
            "selected_option_id",
            "payload",
        },
    )
    for identifier_field in (
        "result_id",
        "request_id",
        "decision_type",
        "selected_option_id",
    ):
        if type(raw[identifier_field]) is not str:
            raise GameLifecycleError(
                f"Model destruction cause authority {field_name}.{identifier_field} "
                "must be a string."
            )
    actor_id = raw["actor_id"]
    if actor_id is not None and type(actor_id) is not str:
        raise GameLifecycleError(
            f"Model destruction cause authority {field_name}.actor_id is invalid."
        )


def _validate_typed_tuple(
    value: object,
    *,
    item_type: type[object],
    field_name: str,
) -> None:
    if type(value) is not tuple or any(
        type(item) is not item_type for item in cast(tuple[object, ...], value)
    ):
        raise GameLifecycleError(
            f"Model destruction cause authority {field_name} must be a typed tuple."
        )


def _validate_identifier_tuple(field_name: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers = tuple(
        _validate_identifier(field_name, item) for item in cast(tuple[object, ...], value)
    )
    if len(identifiers) != len(set(identifiers)):
        raise GameLifecycleError(f"{field_name} must contain unique identifiers.")
    return identifiers


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "MODEL_DESTROYED_EVENT_TYPE",
    "MODEL_DESTRUCTION_CAUSE_ID_FIELD",
    "ModelDestructionCauseAuthority",
    "ModelDestructionCauseAuthorityPayload",
    "ModelDestructionCauseKind",
    "consume_model_destruction_cause",
    "consume_model_destruction_cause_authority",
    "consumed_model_destruction_cause_authority_for_event",
    "finalize_model_destruction_cause",
    "finalize_model_destruction_cause_authority",
    "model_destruction_cause_authority_by_id_or_none",
    "model_destruction_cause_id",
    "record_consumed_model_destruction_cause",
    "record_model_destruction_cause",
    "record_model_destruction_cause_authority",
    "validate_model_destruction_cause_authorities",
    "validate_model_destruction_cause_authority_restore",
)
