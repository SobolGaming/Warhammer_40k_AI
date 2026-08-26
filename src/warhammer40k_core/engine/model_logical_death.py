from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    ModelPlacement,
    ModelPlacementPayload,
    PlacementError,
)
from warhammer40k_core.engine.damage_allocation_targets import damage_kind_from_token
from warhammer40k_core.engine.event_log import (
    EventLog,
    EventLogError,
    EventRecord,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pose import GeometryError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.model_destruction_cause_authority import (
        ModelDestructionCauseKind,
    )


MODEL_LOGICAL_DEATH_RECORDED_EVENT = "model_logical_death_recorded"
_MODEL_LOGICAL_DEATH_BOUNDARY_ID_DOMAIN = "warhammer40k-core:model-logical-death:v1"
_MODEL_LOGICAL_DEATH_BOUNDARY_ID_PREFIX = "model-logical-death"


class ModelLogicalDeathTransitionKind(StrEnum):
    DAMAGE_APPLICATION = "damage_application"
    DIRECT_RULE = "direct_rule"


class LogicalDeathDamageApplicationPayload(TypedDict):
    target_unit_instance_id: str
    model_instance_id: str
    damage_kind: str
    requested_damage: int
    wounds_lost: int
    excess_damage_lost: int
    starting_wounds_remaining: int
    final_wounds_remaining: int
    destroyed: bool


class DamageApplicationLogicalDeathTransitionPayload(TypedDict):
    transition_kind: str
    damage_application: LogicalDeathDamageApplicationPayload


class DirectRuleLogicalDeathTransitionPayload(TypedDict):
    transition_kind: str
    source_rule_id: str
    source_result_id: str


type ModelLogicalDeathTransitionPayload = (
    DamageApplicationLogicalDeathTransitionPayload | DirectRuleLogicalDeathTransitionPayload
)


class ModelLogicalDeathRecordPayload(TypedDict):
    boundary_id: str
    game_id: str
    cause_id: str
    cause_kind: str
    producer_id: str
    model_instance_id: str
    physical_unit_instance_id: str
    rules_unit_instance_id: str
    destroyed_model_placement: ModelPlacementPayload
    placement_retained: bool
    transition: ModelLogicalDeathTransitionPayload


@dataclass(frozen=True, slots=True)
class DamageApplicationLogicalDeathTransition:
    damage_application: LogicalDeathDamageApplicationPayload

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "damage_application",
            _lethal_damage_application_payload(self.damage_application),
        )

    @property
    def transition_kind(self) -> ModelLogicalDeathTransitionKind:
        return ModelLogicalDeathTransitionKind.DAMAGE_APPLICATION

    def to_payload(self) -> DamageApplicationLogicalDeathTransitionPayload:
        return {
            "transition_kind": self.transition_kind.value,
            "damage_application": self.damage_application,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _exact_object(
            payload,
            field_name="damage-application logical-death transition",
            expected_fields={"transition_kind", "damage_application"},
        )
        if raw["transition_kind"] != ModelLogicalDeathTransitionKind.DAMAGE_APPLICATION.value:
            raise GameLifecycleError("Logical-death transition kind drift.")
        return cls(damage_application=_lethal_damage_application_payload(raw["damage_application"]))


@dataclass(frozen=True, slots=True)
class DirectRuleLogicalDeathTransition:
    source_rule_id: str
    source_result_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("Logical-death source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "source_result_id",
            _validate_identifier("Logical-death source_result_id", self.source_result_id),
        )

    @property
    def transition_kind(self) -> ModelLogicalDeathTransitionKind:
        return ModelLogicalDeathTransitionKind.DIRECT_RULE

    def to_payload(self) -> DirectRuleLogicalDeathTransitionPayload:
        return {
            "transition_kind": self.transition_kind.value,
            "source_rule_id": self.source_rule_id,
            "source_result_id": self.source_result_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _exact_object(
            payload,
            field_name="direct-rule logical-death transition",
            expected_fields={"transition_kind", "source_rule_id", "source_result_id"},
        )
        if raw["transition_kind"] != ModelLogicalDeathTransitionKind.DIRECT_RULE.value:
            raise GameLifecycleError("Logical-death transition kind drift.")
        return cls(
            source_rule_id=_validate_identifier(
                "Logical-death source_rule_id", raw["source_rule_id"]
            ),
            source_result_id=_validate_identifier(
                "Logical-death source_result_id", raw["source_result_id"]
            ),
        )


type ModelLogicalDeathTransition = (
    DamageApplicationLogicalDeathTransition | DirectRuleLogicalDeathTransition
)


@dataclass(frozen=True, slots=True)
class ModelLogicalDeathRecord:
    boundary_id: str
    game_id: str
    cause_id: str
    cause_kind: ModelDestructionCauseKind
    producer_id: str
    model_instance_id: str
    physical_unit_instance_id: str
    rules_unit_instance_id: str
    destroyed_model_placement: ModelPlacement
    placement_retained: bool
    transition: ModelLogicalDeathTransition

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.model_destruction_cause_authority import (
            ModelDestructionCauseKind,
        )

        for field_name in (
            "game_id",
            "cause_id",
            "producer_id",
            "model_instance_id",
            "physical_unit_instance_id",
            "rules_unit_instance_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(f"Logical-death {field_name}", getattr(self, field_name)),
            )
        if type(self.cause_kind) is not ModelDestructionCauseKind:
            raise GameLifecycleError("Logical-death cause_kind is invalid.")
        expected_boundary_id = model_logical_death_boundary_id(
            game_id=self.game_id,
            cause_id=self.cause_id,
            model_instance_id=self.model_instance_id,
        )
        if self.boundary_id != expected_boundary_id:
            raise GameLifecycleError("Logical-death boundary identity drift.")
        if type(self.destroyed_model_placement) is not ModelPlacement:
            raise GameLifecycleError("Logical-death placement must be ModelPlacement.")
        if (
            self.destroyed_model_placement.model_instance_id != self.model_instance_id
            or self.destroyed_model_placement.unit_instance_id != self.physical_unit_instance_id
        ):
            raise GameLifecycleError("Logical-death placement identity drift.")
        if type(self.placement_retained) is not bool:
            raise GameLifecycleError("Logical-death placement_retained must be a bool.")
        if type(self.transition) not in {
            DamageApplicationLogicalDeathTransition,
            DirectRuleLogicalDeathTransition,
        }:
            raise GameLifecycleError("Logical-death transition is invalid.")
        if isinstance(self.transition, DamageApplicationLogicalDeathTransition):
            damage = self.transition.damage_application
            if (
                damage["model_instance_id"] != self.model_instance_id
                or damage["target_unit_instance_id"] != self.rules_unit_instance_id
            ):
                raise GameLifecycleError("Logical-death damage identity drift.")
        else:
            if self.cause_kind is not ModelDestructionCauseKind.RULE_EFFECT:
                raise GameLifecycleError("Direct-rule logical death requires rule-effect cause.")
            if not self.placement_retained:
                raise GameLifecycleError("Direct-rule logical death must retain placement.")

    def to_payload(self) -> ModelLogicalDeathRecordPayload:
        return {
            "boundary_id": self.boundary_id,
            "game_id": self.game_id,
            "cause_id": self.cause_id,
            "cause_kind": self.cause_kind.value,
            "producer_id": self.producer_id,
            "model_instance_id": self.model_instance_id,
            "physical_unit_instance_id": self.physical_unit_instance_id,
            "rules_unit_instance_id": self.rules_unit_instance_id,
            "destroyed_model_placement": self.destroyed_model_placement.to_payload(),
            "placement_retained": self.placement_retained,
            "transition": self.transition.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _exact_object(
            payload,
            field_name="model logical-death record",
            expected_fields={
                "boundary_id",
                "game_id",
                "cause_id",
                "cause_kind",
                "producer_id",
                "model_instance_id",
                "physical_unit_instance_id",
                "rules_unit_instance_id",
                "destroyed_model_placement",
                "placement_retained",
                "transition",
            },
        )
        cause_kind = _cause_kind(raw["cause_kind"])
        placement_retained = raw["placement_retained"]
        if type(placement_retained) is not bool:
            raise GameLifecycleError("Logical-death placement_retained must be a bool.")
        return cls(
            boundary_id=_validate_identifier("Logical-death boundary_id", raw["boundary_id"]),
            game_id=_validate_identifier("Logical-death game_id", raw["game_id"]),
            cause_id=_validate_identifier("Logical-death cause_id", raw["cause_id"]),
            cause_kind=cause_kind,
            producer_id=_validate_identifier("Logical-death producer_id", raw["producer_id"]),
            model_instance_id=_validate_identifier(
                "Logical-death model_instance_id", raw["model_instance_id"]
            ),
            physical_unit_instance_id=_validate_identifier(
                "Logical-death physical_unit_instance_id",
                raw["physical_unit_instance_id"],
            ),
            rules_unit_instance_id=_validate_identifier(
                "Logical-death rules_unit_instance_id", raw["rules_unit_instance_id"]
            ),
            destroyed_model_placement=_model_placement(raw["destroyed_model_placement"]),
            placement_retained=placement_retained,
            transition=_transition(raw["transition"]),
        )


def model_logical_death_boundary_id(
    *,
    game_id: str,
    cause_id: str,
    model_instance_id: str,
) -> str:
    identity: dict[str, JsonValue] = {
        "domain": _MODEL_LOGICAL_DEATH_BOUNDARY_ID_DOMAIN,
        "game_id": _validate_identifier("Logical-death game_id", game_id),
        "cause_id": _validate_identifier("Logical-death cause_id", cause_id),
        "model_instance_id": _validate_identifier(
            "Logical-death model_instance_id", model_instance_id
        ),
    }
    digest = sha256(canonical_json(identity).encode("utf-8")).hexdigest()
    return f"{_MODEL_LOGICAL_DEATH_BOUNDARY_ID_PREFIX}:sha256:{digest}"


def append_damage_application_model_logical_death_event(
    *,
    state: GameState,
    event_log: EventLog,
    cause_id: str,
    cause_kind: ModelDestructionCauseKind,
    producer_id: str,
    model_instance_id: str,
    physical_unit_instance_id: str,
    rules_unit_instance_id: str,
    destroyed_model_placement: ModelPlacement,
    placement_retained: bool,
    damage_application: JsonValue,
) -> EventRecord:
    return append_model_logical_death_event(
        state=state,
        event_log=event_log,
        cause_id=cause_id,
        cause_kind=cause_kind,
        producer_id=producer_id,
        model_instance_id=model_instance_id,
        physical_unit_instance_id=physical_unit_instance_id,
        rules_unit_instance_id=rules_unit_instance_id,
        destroyed_model_placement=destroyed_model_placement,
        placement_retained=placement_retained,
        transition=DamageApplicationLogicalDeathTransition(
            damage_application=_lethal_damage_application_payload(damage_application)
        ),
    )


def append_direct_rule_model_logical_death_event(
    *,
    state: GameState,
    event_log: EventLog,
    cause_id: str,
    producer_id: str,
    model_instance_id: str,
    physical_unit_instance_id: str,
    rules_unit_instance_id: str,
    destroyed_model_placement: ModelPlacement,
    source_rule_id: str,
    source_result_id: str,
) -> EventRecord:
    from warhammer40k_core.engine.model_destruction_cause_authority import (
        ModelDestructionCauseKind,
    )

    return append_model_logical_death_event(
        state=state,
        event_log=event_log,
        cause_id=cause_id,
        cause_kind=ModelDestructionCauseKind.RULE_EFFECT,
        producer_id=producer_id,
        model_instance_id=model_instance_id,
        physical_unit_instance_id=physical_unit_instance_id,
        rules_unit_instance_id=rules_unit_instance_id,
        destroyed_model_placement=destroyed_model_placement,
        placement_retained=True,
        transition=DirectRuleLogicalDeathTransition(
            source_rule_id=source_rule_id,
            source_result_id=source_result_id,
        ),
    )


def append_model_logical_death_event(
    *,
    state: GameState,
    event_log: EventLog,
    cause_id: str,
    cause_kind: ModelDestructionCauseKind,
    producer_id: str,
    model_instance_id: str,
    physical_unit_instance_id: str,
    rules_unit_instance_id: str,
    destroyed_model_placement: ModelPlacement,
    placement_retained: bool,
    transition: ModelLogicalDeathTransition,
) -> EventRecord:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Logical-death append requires GameState.")
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Logical-death append requires EventLog.")
    record = ModelLogicalDeathRecord(
        boundary_id=model_logical_death_boundary_id(
            game_id=state.game_id,
            cause_id=cause_id,
            model_instance_id=model_instance_id,
        ),
        game_id=state.game_id,
        cause_id=cause_id,
        cause_kind=cause_kind,
        producer_id=producer_id,
        model_instance_id=model_instance_id,
        physical_unit_instance_id=physical_unit_instance_id,
        rules_unit_instance_id=rules_unit_instance_id,
        destroyed_model_placement=destroyed_model_placement,
        placement_retained=placement_retained,
        transition=transition,
    )
    existing = model_logical_death_event_for_cause_id_or_none(
        event_records=event_log.records,
        cause_id=record.cause_id,
    )
    if existing is not None:
        if model_logical_death_record_from_event(existing) != record:
            raise GameLifecycleError("Logical-death event idempotent replay drift.")
        return existing
    _validate_record_against_current_state(state=state, record=record)
    return event_log.append(MODEL_LOGICAL_DEATH_RECORDED_EVENT, record.to_payload())


def model_logical_death_record_from_event(event: EventRecord) -> ModelLogicalDeathRecord:
    if type(event) is not EventRecord or event.event_type != MODEL_LOGICAL_DEATH_RECORDED_EVENT:
        raise GameLifecycleError("Logical-death parsing requires its exact event type.")
    return ModelLogicalDeathRecord.from_payload(event.payload)


def model_logical_death_event_for_cause_id_or_none(
    *,
    event_records: tuple[EventRecord, ...],
    cause_id: str,
) -> EventRecord | None:
    requested_cause_id = _validate_identifier("Logical-death cause_id", cause_id)
    _typed_event_records(event_records)
    matches: list[EventRecord] = []
    for event in event_records:
        if event.event_type != MODEL_LOGICAL_DEATH_RECORDED_EVENT:
            continue
        record = model_logical_death_record_from_event(event)
        if record.cause_id == requested_cause_id:
            matches.append(event)
    if len(matches) > 1:
        raise GameLifecycleError("Logical-death cause has duplicate boundary events.")
    return None if not matches else matches[0]


def model_logical_death_event_for_cause_id(
    *,
    event_records: tuple[EventRecord, ...],
    cause_id: str,
) -> EventRecord:
    event = model_logical_death_event_for_cause_id_or_none(
        event_records=event_records,
        cause_id=cause_id,
    )
    if event is None:
        raise GameLifecycleError("Logical-death cause is missing its boundary event.")
    return event


def model_logical_death_events_for_cause_ids(
    *,
    event_records: tuple[EventRecord, ...],
    cause_ids: tuple[str, ...],
) -> tuple[EventRecord, ...]:
    requested_cause_ids = _identifier_tuple("Logical-death cause_ids", cause_ids)
    if len(requested_cause_ids) != len(set(requested_cause_ids)):
        raise GameLifecycleError("Logical-death cause_ids contain duplicates.")
    events = tuple(
        model_logical_death_event_for_cause_id(
            event_records=event_records,
            cause_id=cause_id,
        )
        for cause_id in requested_cause_ids
    )
    event_indexes = {event.event_id: index for index, event in enumerate(event_records)}
    indexes = tuple(event_indexes[event.event_id] for event in events)
    if indexes != tuple(sorted(indexes)):
        raise GameLifecycleError("Logical-death events are not in requested causal order.")
    return events


def validate_model_logical_death_event_identity(
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
    record = model_logical_death_record_from_event(event)
    expected = (
        _validate_identifier("Logical-death game_id", game_id),
        _validate_identifier("Logical-death cause_id", cause_id),
        cause_kind,
        _validate_identifier("Logical-death producer_id", producer_id),
        _validate_identifier("Logical-death model_instance_id", model_instance_id),
        _validate_identifier("Logical-death physical_unit_instance_id", physical_unit_instance_id),
        _validate_identifier("Logical-death rules_unit_instance_id", rules_unit_instance_id),
    )
    actual = (
        record.game_id,
        record.cause_id,
        record.cause_kind,
        record.producer_id,
        record.model_instance_id,
        record.physical_unit_instance_id,
        record.rules_unit_instance_id,
    )
    if actual != expected:
        raise GameLifecycleError("Logical-death event authority identity drift.")
    return record


def _validate_record_against_current_state(
    *,
    state: GameState,
    record: ModelLogicalDeathRecord,
) -> None:
    if record.game_id != state.game_id:
        raise GameLifecycleError("Logical-death event game drift.")
    if state.unit_instance_id_for_model(record.model_instance_id) != (
        record.physical_unit_instance_id
    ):
        raise GameLifecycleError("Logical-death physical-unit identity drift.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=record.rules_unit_instance_id,
    )
    if record.physical_unit_instance_id not in rules_unit.component_unit_instance_ids:
        raise GameLifecycleError("Logical-death rules-unit identity drift.")
    models = tuple(
        model
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
        if model.model_instance_id == record.model_instance_id
    )
    if len(models) != 1 or models[0].is_alive:
        raise GameLifecycleError("Logical-death append requires one destroyed model.")
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Logical-death append requires battlefield state.")
    current_placement = battlefield.model_placement_or_none(record.model_instance_id)
    if record.placement_retained:
        if current_placement != record.destroyed_model_placement:
            raise GameLifecycleError("Logical-death retained placement drift.")
    elif (
        current_placement is not None
        or record.model_instance_id not in battlefield.removed_model_ids
    ):
        raise GameLifecycleError("Logical-death removed placement drift.")


def _transition(value: object) -> ModelLogicalDeathTransition:
    raw = _object(value, field_name="logical-death transition")
    kind = raw.get("transition_kind")
    if kind == ModelLogicalDeathTransitionKind.DAMAGE_APPLICATION.value:
        return DamageApplicationLogicalDeathTransition.from_payload(raw)
    if kind == ModelLogicalDeathTransitionKind.DIRECT_RULE.value:
        return DirectRuleLogicalDeathTransition.from_payload(raw)
    raise GameLifecycleError("Logical-death transition kind is unsupported.")


def _lethal_damage_application_payload(value: object) -> LogicalDeathDamageApplicationPayload:
    raw = _exact_object(
        value,
        field_name="logical-death damage_application",
        expected_fields={
            "target_unit_instance_id",
            "model_instance_id",
            "damage_kind",
            "requested_damage",
            "wounds_lost",
            "excess_damage_lost",
            "starting_wounds_remaining",
            "final_wounds_remaining",
            "destroyed",
        },
    )
    target_id = _validate_identifier(
        "Logical-death damage target_unit_instance_id",
        raw["target_unit_instance_id"],
    )
    model_id = _validate_identifier(
        "Logical-death damage model_instance_id", raw["model_instance_id"]
    )
    raw_damage_kind = raw["damage_kind"]
    if type(raw_damage_kind) is not str:
        raise GameLifecycleError("Logical-death damage_kind must be a string.")
    damage_kind = damage_kind_from_token(raw_damage_kind)
    requested_damage = _positive_int("Logical-death requested_damage", raw["requested_damage"])
    wounds_lost = _positive_int("Logical-death wounds_lost", raw["wounds_lost"])
    excess_damage_lost = _non_negative_int(
        "Logical-death excess_damage_lost", raw["excess_damage_lost"]
    )
    starting_wounds = _positive_int(
        "Logical-death starting_wounds_remaining",
        raw["starting_wounds_remaining"],
    )
    final_wounds = _non_negative_int(
        "Logical-death final_wounds_remaining",
        raw["final_wounds_remaining"],
    )
    destroyed = raw["destroyed"]
    if type(destroyed) is not bool or not destroyed:
        raise GameLifecycleError("Logical-death damage must be lethal.")
    if (
        final_wounds != 0
        or wounds_lost != starting_wounds
        or requested_damage != wounds_lost + excess_damage_lost
    ):
        raise GameLifecycleError("Logical-death damage accounting drift.")
    return {
        "target_unit_instance_id": target_id,
        "model_instance_id": model_id,
        "damage_kind": damage_kind.value,
        "requested_damage": requested_damage,
        "wounds_lost": wounds_lost,
        "excess_damage_lost": excess_damage_lost,
        "starting_wounds_remaining": starting_wounds,
        "final_wounds_remaining": final_wounds,
        "destroyed": True,
    }


def _model_placement(value: object) -> ModelPlacement:
    raw = _exact_object(
        value,
        field_name="logical-death destroyed_model_placement",
        expected_fields={"army_id", "player_id", "unit_instance_id", "model_instance_id", "pose"},
    )
    for key in ("army_id", "player_id", "unit_instance_id", "model_instance_id"):
        _validate_identifier(f"Logical-death placement {key}", raw[key])
    pose = _exact_object(
        raw["pose"],
        field_name="logical-death placement pose",
        expected_fields={"position", "facing"},
    )
    position = _exact_object(
        pose["position"],
        field_name="logical-death placement position",
        expected_fields={"x", "y", "z"},
    )
    facing = _exact_object(
        pose["facing"],
        field_name="logical-death placement facing",
        expected_fields={"degrees"},
    )
    for key in ("x", "y", "z"):
        _number(f"Logical-death placement position {key}", position[key])
    _number("Logical-death placement facing degrees", facing["degrees"])
    try:
        return ModelPlacement.from_payload(cast(ModelPlacementPayload, raw))
    except (GeometryError, PlacementError) as exc:
        raise GameLifecycleError("Logical-death placement is invalid.") from exc


def _cause_kind(value: object) -> ModelDestructionCauseKind:
    from warhammer40k_core.engine.model_destruction_cause_authority import (
        ModelDestructionCauseKind,
    )

    if type(value) is not str:
        raise GameLifecycleError("Logical-death cause_kind must be a string.")
    try:
        return ModelDestructionCauseKind(value)
    except ValueError as exc:
        raise GameLifecycleError("Logical-death cause_kind is unsupported.") from exc


def _typed_event_records(value: object) -> tuple[EventRecord, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Logical-death event_records must contain EventRecord values.")
    items = cast(tuple[object, ...], value)
    if any(type(item) is not EventRecord for item in items):
        raise GameLifecycleError("Logical-death event_records must contain EventRecord values.")
    return cast(tuple[EventRecord, ...], items)


def _identifier_tuple(field_name: str, value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    return tuple(_validate_identifier(field_name, item) for item in cast(tuple[object, ...], value))


def _exact_object(
    value: object,
    *,
    field_name: str,
    expected_fields: set[str],
) -> dict[str, JsonValue]:
    raw = _object(value, field_name=field_name)
    if set(raw) != expected_fields:
        raise GameLifecycleError(f"{field_name} fields drift.")
    return raw


def _object(value: object, *, field_name: str) -> dict[str, JsonValue]:
    try:
        validated = validate_json_value(value)
    except EventLogError as exc:
        raise GameLifecycleError(f"{field_name} must be JSON-safe.") from exc
    if not isinstance(validated, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return validated


def _positive_int(field_name: str, value: object) -> int:
    if type(value) is not int or value <= 0:
        raise GameLifecycleError(f"{field_name} must be a positive integer.")
    return value


def _non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int or value < 0:
        raise GameLifecycleError(f"{field_name} must be a non-negative integer.")
    return value


def _number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise GameLifecycleError(f"{field_name} must be a number.")
    return float(value)


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "MODEL_LOGICAL_DEATH_RECORDED_EVENT",
    "DamageApplicationLogicalDeathTransition",
    "DamageApplicationLogicalDeathTransitionPayload",
    "DirectRuleLogicalDeathTransition",
    "DirectRuleLogicalDeathTransitionPayload",
    "LogicalDeathDamageApplicationPayload",
    "ModelLogicalDeathRecord",
    "ModelLogicalDeathRecordPayload",
    "ModelLogicalDeathTransition",
    "ModelLogicalDeathTransitionKind",
    "ModelLogicalDeathTransitionPayload",
    "append_damage_application_model_logical_death_event",
    "append_direct_rule_model_logical_death_event",
    "append_model_logical_death_event",
    "model_logical_death_boundary_id",
    "model_logical_death_event_for_cause_id",
    "model_logical_death_event_for_cause_id_or_none",
    "model_logical_death_events_for_cause_ids",
    "model_logical_death_record_from_event",
    "validate_model_logical_death_event_identity",
)
