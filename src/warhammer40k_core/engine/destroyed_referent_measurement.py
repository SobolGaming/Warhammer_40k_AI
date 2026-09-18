"""Source-authorized measurement to destroyed models and destroyed units."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import geometry_model_for_placement
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.model_logical_death import (
    MODEL_LOGICAL_DEATH_RECORDED_EVENT,
    ModelLogicalDeathRecord,
    model_logical_death_record_from_event,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_measuring_to_destroyed_2026_09 as measuring_to_destroyed_source,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

MEASURING_TO_DESTROYED_SOURCE_ID = measuring_to_destroyed_source.MEASURING_TO_DESTROYED_SOURCE_ID
MEASUREMENT_POLICY = measuring_to_destroyed_source.MEASUREMENT_POLICY


@dataclass(frozen=True, slots=True)
class DestroyedModelFormerFootprint:
    source_rule_id: str
    model_instance_id: str
    physical_unit_instance_id: str
    rules_unit_instance_id: str
    logical_death: ModelLogicalDeathRecord
    geometry: GeometryModel

    def __post_init__(self) -> None:
        if self.source_rule_id != MEASURING_TO_DESTROYED_SOURCE_ID:
            raise GameLifecycleError("Destroyed-referent footprint source rule drifted.")
        if type(self.logical_death) is not ModelLogicalDeathRecord:
            raise GameLifecycleError("Destroyed-referent footprint requires logical death.")
        if type(self.geometry) is not GeometryModel:
            raise GameLifecycleError("Destroyed-referent footprint requires geometry.")
        if self.logical_death.model_instance_id != self.model_instance_id:
            raise GameLifecycleError("Destroyed-referent footprint model identity drifted.")
        if self.logical_death.physical_unit_instance_id != self.physical_unit_instance_id:
            raise GameLifecycleError("Destroyed-referent footprint physical unit drifted.")
        if self.logical_death.rules_unit_instance_id != self.rules_unit_instance_id:
            raise GameLifecycleError("Destroyed-referent footprint rules unit drifted.")
        if self.geometry.model_id != self.model_instance_id:
            raise GameLifecycleError("Destroyed-referent footprint geometry identity drifted.")
        if MEASUREMENT_POLICY.grants_living_battlefield_authority:
            raise GameLifecycleError(
                "Destroyed-referent measurement must not grant living authority."
            )


def former_footprint_for_destroyed_model(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    model_instance_id: str,
) -> DestroyedModelFormerFootprint:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    model = model_by_id(state=state, model_instance_id=requested_model_id)
    if model.is_alive:
        raise GameLifecycleError("Destroyed-model measurement requires a destroyed model.")
    record = _logical_death_for_model(
        event_records=_typed_event_records(event_records),
        model_instance_id=requested_model_id,
    )
    _assert_physical_identity(state=state, model=model, record=record)
    return _footprint_from_record(model=model, record=record)


def former_footprint_for_destroyed_unit(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    unit_instance_id: str,
) -> DestroyedModelFormerFootprint:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    view = rules_unit_view_by_id(state=state, unit_instance_id=requested_unit_id)
    if any(model.is_alive for model in view.own_models):
        raise GameLifecycleError("Destroyed-unit measurement requires a destroyed rules unit.")
    records = _logical_deaths_for_rules_unit(
        event_records=_typed_event_records(event_records),
        rules_unit_instance_id=view.unit_instance_id,
        component_unit_instance_ids=view.component_unit_instance_ids,
    )
    destroyed_ids = {model.model_instance_id for model in view.own_models}
    death_ids = {record.model_instance_id for record in records}
    if destroyed_ids != death_ids:
        raise GameLifecycleError(
            "Destroyed-unit measurement is missing authenticated former placement."
        )
    last_record = records[-1]
    last_model = model_by_id(state=state, model_instance_id=last_record.model_instance_id)
    if last_model.is_alive:
        raise GameLifecycleError("Destroyed-unit last model must remain destroyed.")
    _assert_physical_identity(state=state, model=last_model, record=last_record)
    return _footprint_from_record(model=last_model, record=last_record)


def distance_to_destroyed_model(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    source_model_instance_id: str,
    destroyed_model_instance_id: str,
) -> float:
    context = measurement_context_to_destroyed_model(
        state=state,
        event_records=event_records,
        source_model_instance_id=source_model_instance_id,
        destroyed_model_instance_id=destroyed_model_instance_id,
    )
    return context.closest_distance_inches()


def distance_to_destroyed_unit(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    source_model_instance_id: str,
    destroyed_unit_instance_id: str,
) -> float:
    context = measurement_context_to_destroyed_unit(
        state=state,
        event_records=event_records,
        source_model_instance_id=source_model_instance_id,
        destroyed_unit_instance_id=destroyed_unit_instance_id,
    )
    return context.closest_distance_inches()


def measurement_context_to_destroyed_model(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    source_model_instance_id: str,
    destroyed_model_instance_id: str,
) -> DistanceMeasurementContext:
    source = _placed_source_geometry(
        state=state,
        model_instance_id=source_model_instance_id,
    )
    target = former_footprint_for_destroyed_model(
        state=state,
        event_records=event_records,
        model_instance_id=destroyed_model_instance_id,
    )
    return DistanceMeasurementContext.from_models(source, target.geometry)


def measurement_context_to_destroyed_unit(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    source_model_instance_id: str,
    destroyed_unit_instance_id: str,
) -> DistanceMeasurementContext:
    source = _placed_source_geometry(
        state=state,
        model_instance_id=source_model_instance_id,
    )
    target = former_footprint_for_destroyed_unit(
        state=state,
        event_records=event_records,
        unit_instance_id=destroyed_unit_instance_id,
    )
    return DistanceMeasurementContext.from_models(source, target.geometry)


def former_geometry_for_destroyed_or_placed_model(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    model_instance_id: str,
) -> GeometryModel:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Destroyed-referent measurement requires battlefield_state.")
    placement = battlefield.model_placement_or_none(requested_model_id)
    if placement is not None:
        return geometry_model_for_placement(
            model=model_by_id(state=state, model_instance_id=requested_model_id),
            placement=placement,
        )
    return former_footprint_for_destroyed_model(
        state=state,
        event_records=event_records,
        model_instance_id=requested_model_id,
    ).geometry


def _footprint_from_record(
    *,
    model: ModelInstance,
    record: ModelLogicalDeathRecord,
) -> DestroyedModelFormerFootprint:
    if not MEASUREMENT_POLICY.uses_former_footprint:
        raise GameLifecycleError("Destroyed-referent measurement requires former-footprint policy.")
    if not MEASUREMENT_POLICY.uses_catalog_geometry_for_base_or_hull:
        raise GameLifecycleError("Destroyed-referent measurement requires catalog geometry.")
    return DestroyedModelFormerFootprint(
        source_rule_id=MEASURING_TO_DESTROYED_SOURCE_ID,
        model_instance_id=record.model_instance_id,
        physical_unit_instance_id=record.physical_unit_instance_id,
        rules_unit_instance_id=record.rules_unit_instance_id,
        logical_death=record,
        geometry=geometry_model_for_placement(
            model=model,
            placement=record.destroyed_model_placement,
        ),
    )


def _placed_source_geometry(*, state: GameState, model_instance_id: str) -> GeometryModel:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Destroyed-referent measurement requires battlefield_state.")
    placement = battlefield.model_placement_or_none(requested_model_id)
    if placement is None:
        raise GameLifecycleError("Destroyed-referent measurement source model must remain placed.")
    return geometry_model_for_placement(
        model=model_by_id(state=state, model_instance_id=requested_model_id),
        placement=placement,
    )


def _logical_death_for_model(
    *,
    event_records: tuple[EventRecord, ...],
    model_instance_id: str,
) -> ModelLogicalDeathRecord:
    matches: list[ModelLogicalDeathRecord] = []
    for event in event_records:
        if event.event_type != MODEL_LOGICAL_DEATH_RECORDED_EVENT:
            continue
        record = model_logical_death_record_from_event(event)
        if record.model_instance_id == model_instance_id:
            matches.append(record)
    if not matches:
        raise GameLifecycleError(
            "Destroyed-model measurement is missing authenticated former placement."
        )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Destroyed-model measurement found duplicate logical-death records."
        )
    return matches[0]


def _logical_deaths_for_rules_unit(
    *,
    event_records: tuple[EventRecord, ...],
    rules_unit_instance_id: str,
    component_unit_instance_ids: tuple[str, ...],
) -> tuple[ModelLogicalDeathRecord, ...]:
    if not MEASUREMENT_POLICY.destroyed_unit_resolves_to_last_destroyed_model:
        raise GameLifecycleError("Destroyed-unit measurement requires last-destroyed-model policy.")
    component_ids = set(component_unit_instance_ids)
    matches: list[ModelLogicalDeathRecord] = []
    seen_model_ids: set[str] = set()
    for event in event_records:
        if event.event_type != MODEL_LOGICAL_DEATH_RECORDED_EVENT:
            continue
        record = model_logical_death_record_from_event(event)
        if (
            record.rules_unit_instance_id != rules_unit_instance_id
            and record.physical_unit_instance_id not in component_ids
        ):
            continue
        if record.model_instance_id in seen_model_ids:
            raise GameLifecycleError(
                "Destroyed-unit measurement found duplicate logical-death records."
            )
        seen_model_ids.add(record.model_instance_id)
        matches.append(record)
    if not matches:
        raise GameLifecycleError(
            "Destroyed-unit measurement is missing authenticated former placement."
        )
    return tuple(matches)


def _assert_physical_identity(
    *,
    state: GameState,
    model: ModelInstance,
    record: ModelLogicalDeathRecord,
) -> None:
    if (
        state.unit_instance_id_for_model(model.model_instance_id)
        != record.physical_unit_instance_id
    ):
        raise GameLifecycleError("Destroyed-referent measurement physical-unit identity drifted.")
    view = rules_unit_view_by_id(state=state, unit_instance_id=record.rules_unit_instance_id)
    if record.physical_unit_instance_id not in view.component_unit_instance_ids:
        raise GameLifecycleError("Destroyed-referent measurement rules-unit identity drifted.")
    if record.destroyed_model_placement.model_instance_id != model.model_instance_id:
        raise GameLifecycleError("Destroyed-referent measurement placement identity drifted.")


def _typed_event_records(value: object) -> tuple[EventRecord, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(
            "Destroyed-referent event_records must contain EventRecord values."
        )
    items = cast(tuple[object, ...], value)
    if any(type(item) is not EventRecord for item in items):
        raise GameLifecycleError(
            "Destroyed-referent event_records must contain EventRecord values."
        )
    return cast(tuple[EventRecord, ...], items)


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "MEASUREMENT_POLICY",
    "MEASURING_TO_DESTROYED_SOURCE_ID",
    "DestroyedModelFormerFootprint",
    "distance_to_destroyed_model",
    "distance_to_destroyed_unit",
    "former_footprint_for_destroyed_model",
    "former_footprint_for_destroyed_unit",
    "former_geometry_for_destroyed_or_placed_model",
    "measurement_context_to_destroyed_model",
    "measurement_context_to_destroyed_unit",
)
