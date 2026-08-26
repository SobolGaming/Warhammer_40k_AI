from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import ModelPlacement
from warhammer40k_core.engine.damage_allocation_validation import validate_exact_type_tuple
from warhammer40k_core.engine.event_log import EventLog, EventRecord, JsonValue
from warhammer40k_core.engine.model_destruction_cause_authority import (
    ModelDestructionCauseKind,
    model_destruction_cause_id,
)
from warhammer40k_core.engine.model_logical_death import (
    DamageApplicationLogicalDeathTransition,
    append_damage_application_model_logical_death_event,
    model_logical_death_record_from_event,
)
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.damage_allocation import DamageApplication
    from warhammer40k_core.engine.game_state import GameState


class MortalWoundLogicalDeathBindingKind(StrEnum):
    FIXED_PRODUCER = "fixed_producer"
    PER_MODEL_PRODUCER = "per_model_producer"


class MortalWoundLogicalDeathProducerRowPayload(TypedDict):
    model_instance_id: str
    producer_id: str


class MortalWoundLogicalDeathCauseBindingPayload(TypedDict):
    binding_kind: str
    cause_kind: str
    fixed_producer_id: str | None
    producer_rows: list[MortalWoundLogicalDeathProducerRowPayload]


@dataclass(frozen=True, slots=True)
class MortalWoundLogicalDeathProducerRow:
    model_instance_id: str
    producer_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier(
                "Mortal-wound logical-death producer model_instance_id",
                self.model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "producer_id",
            _validate_identifier(
                "Mortal-wound logical-death producer producer_id",
                self.producer_id,
            ),
        )

    def to_payload(self) -> MortalWoundLogicalDeathProducerRowPayload:
        return {
            "model_instance_id": self.model_instance_id,
            "producer_id": self.producer_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _exact_object(
            payload,
            field_name="Mortal-wound logical-death producer row",
            expected_fields={"model_instance_id", "producer_id"},
        )
        return cls(
            model_instance_id=_validate_identifier(
                "Mortal-wound logical-death producer model_instance_id",
                raw["model_instance_id"],
            ),
            producer_id=_validate_identifier(
                "Mortal-wound logical-death producer producer_id",
                raw["producer_id"],
            ),
        )


@dataclass(frozen=True, slots=True)
class MortalWoundLogicalDeathCauseBinding:
    binding_kind: MortalWoundLogicalDeathBindingKind
    cause_kind: ModelDestructionCauseKind
    fixed_producer_id: str | None
    producer_rows: tuple[MortalWoundLogicalDeathProducerRow, ...] = ()

    def __post_init__(self) -> None:
        if type(self.binding_kind) is not MortalWoundLogicalDeathBindingKind:
            raise GameLifecycleError("Mortal-wound logical-death binding kind is invalid.")
        if type(self.cause_kind) is not ModelDestructionCauseKind:
            raise GameLifecycleError("Mortal-wound logical-death cause kind is invalid.")
        fixed_producer_id = (
            None
            if self.fixed_producer_id is None
            else _validate_identifier(
                "Mortal-wound logical-death fixed_producer_id",
                self.fixed_producer_id,
            )
        )
        object.__setattr__(self, "fixed_producer_id", fixed_producer_id)
        rows = validate_exact_type_tuple(
            self.producer_rows,
            item_type=MortalWoundLogicalDeathProducerRow,
            collection_label="Mortal-wound logical-death producer rows",
        )
        model_ids = tuple(row.model_instance_id for row in rows)
        if len(model_ids) != len(set(model_ids)):
            raise GameLifecycleError(
                "Mortal-wound logical-death producer rows must not duplicate models."
            )
        object.__setattr__(self, "producer_rows", rows)
        if self.binding_kind is MortalWoundLogicalDeathBindingKind.FIXED_PRODUCER:
            if fixed_producer_id is None or rows:
                raise GameLifecycleError(
                    "Fixed mortal-wound logical-death binding requires one fixed producer."
                )
        elif fixed_producer_id is not None:
            raise GameLifecycleError(
                "Per-model mortal-wound logical-death binding cannot fix a producer."
            )

    @classmethod
    def fixed(
        cls,
        *,
        cause_kind: ModelDestructionCauseKind,
        producer_id: str,
    ) -> Self:
        return cls(
            binding_kind=MortalWoundLogicalDeathBindingKind.FIXED_PRODUCER,
            cause_kind=cause_kind,
            fixed_producer_id=producer_id,
        )

    @classmethod
    def per_model(cls, *, cause_kind: ModelDestructionCauseKind) -> Self:
        if cause_kind is not ModelDestructionCauseKind.RULE_EFFECT:
            raise GameLifecycleError(
                "Per-model mortal-wound logical-death binding is reserved for rule effects."
            )
        return cls(
            binding_kind=MortalWoundLogicalDeathBindingKind.PER_MODEL_PRODUCER,
            cause_kind=cause_kind,
            fixed_producer_id=None,
        )

    def producer_id_for_model_or_none(self, model_instance_id: str) -> str | None:
        model_id = _validate_identifier(
            "Mortal-wound logical-death model_instance_id",
            model_instance_id,
        )
        if self.binding_kind is MortalWoundLogicalDeathBindingKind.FIXED_PRODUCER:
            if self.fixed_producer_id is None:
                raise GameLifecycleError("Fixed logical-death producer binding is incomplete.")
            return self.fixed_producer_id
        for row in self.producer_rows:
            if row.model_instance_id == model_id:
                return row.producer_id
        return None

    def with_logical_death_event(self, event: EventRecord) -> Self:
        record = model_logical_death_record_from_event(event)
        if record.cause_kind is not self.cause_kind:
            raise GameLifecycleError("Mortal-wound logical-death cause kind drift.")
        existing_producer = self.producer_id_for_model_or_none(record.model_instance_id)
        if existing_producer is not None:
            if existing_producer != record.producer_id:
                raise GameLifecycleError("Mortal-wound logical-death producer identity drift.")
            return self
        if self.binding_kind is not MortalWoundLogicalDeathBindingKind.PER_MODEL_PRODUCER:
            raise GameLifecycleError("Mortal-wound logical-death fixed producer drift.")
        return replace(
            self,
            producer_rows=(
                *self.producer_rows,
                MortalWoundLogicalDeathProducerRow(
                    model_instance_id=record.model_instance_id,
                    producer_id=record.producer_id,
                ),
            ),
        )

    def to_payload(self) -> MortalWoundLogicalDeathCauseBindingPayload:
        return {
            "binding_kind": self.binding_kind.value,
            "cause_kind": self.cause_kind.value,
            "fixed_producer_id": self.fixed_producer_id,
            "producer_rows": [row.to_payload() for row in self.producer_rows],
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _exact_object(
            payload,
            field_name="Mortal-wound logical-death cause binding",
            expected_fields={
                "binding_kind",
                "cause_kind",
                "fixed_producer_id",
                "producer_rows",
            },
        )
        raw_binding_kind = raw["binding_kind"]
        raw_cause_kind = raw["cause_kind"]
        if type(raw_binding_kind) is not str or type(raw_cause_kind) is not str:
            raise GameLifecycleError("Mortal-wound logical-death binding tokens are invalid.")
        try:
            binding_kind = MortalWoundLogicalDeathBindingKind(raw_binding_kind)
            cause_kind = ModelDestructionCauseKind(raw_cause_kind)
        except ValueError as exc:
            raise GameLifecycleError(
                "Mortal-wound logical-death binding token is unsupported."
            ) from exc
        raw_fixed_producer_id = raw["fixed_producer_id"]
        if raw_fixed_producer_id is not None and type(raw_fixed_producer_id) is not str:
            raise GameLifecycleError(
                "Mortal-wound logical-death fixed_producer_id must be a string or null."
            )
        raw_rows = raw["producer_rows"]
        if not isinstance(raw_rows, list):
            raise GameLifecycleError("Mortal-wound logical-death producer_rows must be a list.")
        return cls(
            binding_kind=binding_kind,
            cause_kind=cause_kind,
            fixed_producer_id=raw_fixed_producer_id,
            producer_rows=tuple(
                MortalWoundLogicalDeathProducerRow.from_payload(row) for row in raw_rows
            ),
        )


class MortalWoundLogicalDeathRecorder(Protocol):
    def __call__(
        self,
        *,
        damage_application: DamageApplication,
        destroyed_model_placement: ModelPlacement,
        placement_retained: bool,
    ) -> EventRecord: ...


def fixed_mortal_wound_logical_death_recorder(
    *,
    state: GameState,
    event_log: EventLog,
    binding: MortalWoundLogicalDeathCauseBinding,
) -> MortalWoundLogicalDeathRecorder:
    if binding.binding_kind is not MortalWoundLogicalDeathBindingKind.FIXED_PRODUCER:
        raise GameLifecycleError("Fixed logical-death recorder requires a fixed binding.")
    producer_id = binding.fixed_producer_id
    if producer_id is None:
        raise GameLifecycleError("Fixed logical-death recorder binding is incomplete.")

    def record(
        *,
        damage_application: DamageApplication,
        destroyed_model_placement: ModelPlacement,
        placement_retained: bool,
    ) -> EventRecord:
        return append_mortal_wound_damage_logical_death_event(
            state=state,
            event_log=event_log,
            cause_kind=binding.cause_kind,
            producer_id=producer_id,
            damage_application=damage_application,
            destroyed_model_placement=destroyed_model_placement,
            placement_retained=placement_retained,
        )

    return record


def append_mortal_wound_damage_logical_death_event(
    *,
    state: GameState,
    event_log: EventLog,
    cause_kind: ModelDestructionCauseKind,
    producer_id: str,
    damage_application: DamageApplication,
    destroyed_model_placement: ModelPlacement,
    placement_retained: bool,
) -> EventRecord:
    model_id = damage_application.model_instance_id
    requested_producer_id = _validate_identifier(
        "Mortal-wound logical-death producer_id",
        producer_id,
    )
    cause_id = model_destruction_cause_id(
        game_id=state.game_id,
        cause_kind=cause_kind,
        producer_id=requested_producer_id,
        model_instance_id=model_id,
    )
    return append_damage_application_model_logical_death_event(
        state=state,
        event_log=event_log,
        cause_id=cause_id,
        cause_kind=cause_kind,
        producer_id=requested_producer_id,
        model_instance_id=model_id,
        physical_unit_instance_id=destroyed_model_placement.unit_instance_id,
        rules_unit_instance_id=damage_application.target_unit_instance_id,
        destroyed_model_placement=destroyed_model_placement,
        placement_retained=placement_retained,
        damage_application=cast(JsonValue, damage_application.to_payload()),
    )


def validate_mortal_wound_logical_death_progress(
    *,
    binding: MortalWoundLogicalDeathCauseBinding | None,
    logical_death_events: object,
    destroyed_damage_application_payloads: tuple[JsonValue, ...],
    placement_retained: bool,
) -> tuple[EventRecord, ...]:
    events = validate_exact_type_tuple(
        logical_death_events,
        item_type=EventRecord,
        collection_label="Mortal-wound logical-death events",
    )
    if len(events) != len(destroyed_damage_application_payloads):
        raise GameLifecycleError(
            "Mortal-wound logical-death events must match lethal damage applications."
        )
    if not events:
        if binding is not None and binding.producer_rows:
            raise GameLifecycleError(
                "Mortal-wound logical-death producer rows lack boundary events."
            )
        return events
    if type(binding) is not MortalWoundLogicalDeathCauseBinding:
        raise GameLifecycleError("Mortal-wound logical death requires a cause binding.")
    event_numbers: list[int] = []
    observed_rows: list[MortalWoundLogicalDeathProducerRow] = []
    for event, damage_payload in zip(events, destroyed_damage_application_payloads, strict=True):
        record = model_logical_death_record_from_event(event)
        if record.cause_kind is not binding.cause_kind:
            raise GameLifecycleError("Mortal-wound logical-death cause kind drift.")
        if record.placement_retained is not placement_retained:
            raise GameLifecycleError("Mortal-wound logical-death placement retention drift.")
        if not isinstance(record.transition, DamageApplicationLogicalDeathTransition):
            raise GameLifecycleError("Mortal-wound logical death requires damage evidence.")
        if record.transition.damage_application != damage_payload:
            raise GameLifecycleError("Mortal-wound logical-death damage evidence drift.")
        producer_id = binding.producer_id_for_model_or_none(record.model_instance_id)
        if producer_id != record.producer_id:
            raise GameLifecycleError("Mortal-wound logical-death producer binding drift.")
        expected_cause_id = model_destruction_cause_id(
            game_id=record.game_id,
            cause_kind=record.cause_kind,
            producer_id=record.producer_id,
            model_instance_id=record.model_instance_id,
        )
        if record.cause_id != expected_cause_id:
            raise GameLifecycleError("Mortal-wound logical-death cause identity drift.")
        event_numbers.append(_event_number(event))
        observed_rows.append(
            MortalWoundLogicalDeathProducerRow(
                model_instance_id=record.model_instance_id,
                producer_id=record.producer_id,
            )
        )
    if event_numbers != sorted(event_numbers) or len(event_numbers) != len(set(event_numbers)):
        raise GameLifecycleError("Mortal-wound logical-death event order drift.")
    if binding.binding_kind is MortalWoundLogicalDeathBindingKind.PER_MODEL_PRODUCER and (
        binding.producer_rows != tuple(observed_rows)
    ):
        raise GameLifecycleError("Mortal-wound per-model producer rows drifted.")
    return events


def _event_number(event: EventRecord) -> int:
    prefix = "event-"
    if not event.event_id.startswith(prefix):
        raise GameLifecycleError("Mortal-wound logical-death event ID is invalid.")
    suffix = event.event_id.removeprefix(prefix)
    if len(suffix) != 6 or not suffix.isascii() or not suffix.isdecimal():
        raise GameLifecycleError("Mortal-wound logical-death event ID is invalid.")
    return int(suffix)


def _exact_object(
    value: object,
    *,
    field_name: str,
    expected_fields: set[str],
) -> dict[str, JsonValue]:
    if type(value) is not dict:
        raise GameLifecycleError(f"{field_name} must be an object.")
    untyped = cast(dict[object, object], value)
    if any(type(key) is not str for key in untyped):
        raise GameLifecycleError(f"{field_name} must be an object.")
    raw = cast(dict[str, JsonValue], value)
    if set(raw) != expected_fields:
        raise GameLifecycleError(f"{field_name} fields are invalid.")
    return raw


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "MortalWoundLogicalDeathBindingKind",
    "MortalWoundLogicalDeathCauseBinding",
    "MortalWoundLogicalDeathCauseBindingPayload",
    "MortalWoundLogicalDeathProducerRow",
    "MortalWoundLogicalDeathProducerRowPayload",
    "MortalWoundLogicalDeathRecorder",
    "append_mortal_wound_damage_logical_death_event",
    "fixed_mortal_wound_logical_death_recorder",
    "validate_mortal_wound_logical_death_progress",
)
