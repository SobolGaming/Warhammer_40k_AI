from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.volume import Model

type IdentifierValidatorCallable = Callable[[str, object], str]


@dataclass(frozen=True, slots=True)
class PathValidationModelReferenceIds:
    friendly_vehicle_monster_model_ids: tuple[str, ...]
    enemy_vehicle_monster_model_ids: tuple[str, ...]
    friendly_model_transit_blocker_ids: tuple[str, ...]
    enemy_model_transit_blocker_ids: tuple[str, ...]
    aircraft_model_ids: tuple[str, ...]


def validate_model_tuple_for_path_validation(
    field_name: str,
    values: object,
) -> tuple[Model, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    models = tuple(
        _validate_model(f"{field_name} model", value) for value in cast(tuple[object, ...], values)
    )
    _validate_unique_model_ids_for_path_validation(field_name, models)
    return tuple(sorted(models, key=lambda model: model.model_id))


def validate_disjoint_path_validation_model_ids(
    *,
    moving_model: Model,
    friendly_models: tuple[Model, ...],
    enemy_models: tuple[Model, ...],
) -> None:
    blocker_ids = {model.model_id for model in (*friendly_models, *enemy_models)}
    if moving_model.model_id in blocker_ids:
        raise GeometryError("PathValidationContext blockers must not include the moving model.")
    if {model.model_id for model in friendly_models} & {model.model_id for model in enemy_models}:
        raise GeometryError("PathValidationContext friendly and enemy models must be disjoint.")


def validate_path_validation_model_reference_ids(
    *,
    friendly_models: tuple[Model, ...],
    enemy_models: tuple[Model, ...],
    friendly_vehicle_monster_model_ids: object,
    enemy_vehicle_monster_model_ids: object,
    friendly_model_transit_blocker_ids: object,
    enemy_model_transit_blocker_ids: object,
    aircraft_model_ids: object,
    validate_identifier: IdentifierValidatorCallable,
) -> PathValidationModelReferenceIds:
    friendly_model_ids = {model.model_id for model in friendly_models}
    enemy_model_ids = {model.model_id for model in enemy_models}
    blocker_model_ids = friendly_model_ids | enemy_model_ids
    friendly_vehicle_monster_ids = _validated_model_reference_ids(
        field_name="PathValidationContext friendly_vehicle_monster_model_ids",
        values=friendly_vehicle_monster_model_ids,
        allowed_model_ids=friendly_model_ids,
        relation_label="friendly models",
        validate_identifier=validate_identifier,
    )
    enemy_vehicle_monster_ids = _validated_model_reference_ids(
        field_name="PathValidationContext enemy_vehicle_monster_model_ids",
        values=enemy_vehicle_monster_model_ids,
        allowed_model_ids=enemy_model_ids,
        relation_label="enemy models",
        validate_identifier=validate_identifier,
    )
    friendly_transit_blocker_ids = _validated_model_reference_ids(
        field_name="PathValidationContext friendly_model_transit_blocker_ids",
        values=friendly_model_transit_blocker_ids,
        allowed_model_ids=friendly_model_ids,
        relation_label="friendly models",
        validate_identifier=validate_identifier,
    )
    enemy_transit_blocker_ids = _validated_model_reference_ids(
        field_name="PathValidationContext enemy_model_transit_blocker_ids",
        values=enemy_model_transit_blocker_ids,
        allowed_model_ids=enemy_model_ids,
        relation_label="enemy models",
        validate_identifier=validate_identifier,
    )
    aircraft_ids = _validated_model_reference_ids(
        field_name="PathValidationContext aircraft_model_ids",
        values=aircraft_model_ids,
        allowed_model_ids=blocker_model_ids,
        relation_label="blocker models",
        validate_identifier=validate_identifier,
    )
    return PathValidationModelReferenceIds(
        friendly_vehicle_monster_model_ids=friendly_vehicle_monster_ids,
        enemy_vehicle_monster_model_ids=enemy_vehicle_monster_ids,
        friendly_model_transit_blocker_ids=friendly_transit_blocker_ids,
        enemy_model_transit_blocker_ids=enemy_transit_blocker_ids,
        aircraft_model_ids=aircraft_ids,
    )


def _validated_model_reference_ids(
    *,
    field_name: str,
    values: object,
    allowed_model_ids: set[str],
    relation_label: str,
    validate_identifier: IdentifierValidatorCallable,
) -> tuple[str, ...]:
    identifiers = _validate_identifier_tuple(field_name, values, validate_identifier)
    if any(model_id not in allowed_model_ids for model_id in identifiers):
        raise GeometryError(f"{field_name} must reference {relation_label}.")
    return identifiers


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    validate_identifier: IdentifierValidatorCallable,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GeometryError(f"{field_name} must not contain duplicate identifiers.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))


def _validate_model(field_name: str, value: object) -> Model:
    if type(value) is not Model:
        raise GeometryError(f"{field_name} must be a Model.")
    return value


def _validate_unique_model_ids_for_path_validation(
    field_name: str,
    models: tuple[Model, ...],
) -> None:
    seen: set[str] = set()
    for model in models:
        if model.model_id in seen:
            raise GeometryError(f"{field_name} must not contain duplicate model IDs.")
        seen.add(model.model_id)
