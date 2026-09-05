from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    ModelPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.fight_on_death import model_is_present_on_battlefield
from warhammer40k_core.engine.objective_geometry import measure_model_to_objective
from warhammer40k_core.engine.objective_geometry_sources import mission_objective_geometries
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    current_rules_unit_views_for_canonical_identity,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class PrimaryUnattributedDestructionCause(StrEnum):
    DESPERATE_ESCAPE = "desperate_escape"
    EMERGENCY_DISEMBARK = "emergency_disembark"
    UNIT_COHERENCY = "unit_coherency"
    RESERVE_DEADLINE = "reserve_deadline"


class ObjectiveMarkerModelWitnessPayload(TypedDict):
    objective_marker_id: str
    model_instance_ids: list[str]


class RulesUnitObjectiveProximityWitnessPayload(TypedDict):
    rules_unit_instance_id: str
    component_unit_instance_ids: list[str]
    objective_marker_witnesses: list[ObjectiveMarkerModelWitnessPayload]


@dataclass(frozen=True, slots=True)
class ObjectiveMarkerModelWitness:
    objective_marker_id: str
    model_instance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "objective_marker_id",
            _validate_identifier("objective_marker_id", self.objective_marker_id),
        )
        object.__setattr__(
            self,
            "model_instance_ids",
            _validate_identifier_tuple(
                "model_instance_ids",
                self.model_instance_ids,
                require_non_empty=True,
            ),
        )

    def to_payload(self) -> ObjectiveMarkerModelWitnessPayload:
        return {
            "objective_marker_id": self.objective_marker_id,
            "model_instance_ids": list(self.model_instance_ids),
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _payload_mapping(
            payload,
            expected_fields={"objective_marker_id", "model_instance_ids"},
            field_name="ObjectiveMarkerModelWitness payload",
        )
        return cls(
            objective_marker_id=_validate_identifier(
                "objective_marker_id",
                raw["objective_marker_id"],
            ),
            model_instance_ids=_identifier_tuple_from_payload_list(
                "model_instance_ids",
                raw["model_instance_ids"],
                require_non_empty=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class RulesUnitObjectiveProximityWitness:
    rules_unit_instance_id: str
    component_unit_instance_ids: tuple[str, ...]
    objective_marker_witnesses: tuple[ObjectiveMarkerModelWitness, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rules_unit_instance_id",
            _validate_identifier("rules_unit_instance_id", self.rules_unit_instance_id),
        )
        component_ids = _validate_identifier_tuple(
            "component_unit_instance_ids",
            self.component_unit_instance_ids,
            require_non_empty=True,
        )
        object.__setattr__(self, "component_unit_instance_ids", component_ids)
        if type(self.objective_marker_witnesses) is not tuple:
            raise GameLifecycleError("objective_marker_witnesses must be a tuple.")
        witnesses: list[ObjectiveMarkerModelWitness] = []
        seen_marker_ids: set[str] = set()
        for witness in self.objective_marker_witnesses:
            if type(witness) is not ObjectiveMarkerModelWitness:
                raise GameLifecycleError("objective_marker_witnesses must contain typed witnesses.")
            if witness.objective_marker_id in seen_marker_ids:
                raise GameLifecycleError(
                    "objective_marker_witnesses must be unique per objective marker."
                )
            seen_marker_ids.add(witness.objective_marker_id)
            witnesses.append(witness)
        object.__setattr__(
            self,
            "objective_marker_witnesses",
            tuple(sorted(witnesses, key=lambda item: item.objective_marker_id)),
        )

    @property
    def objective_marker_ids(self) -> tuple[str, ...]:
        return tuple(witness.objective_marker_id for witness in self.objective_marker_witnesses)

    def to_payload(self) -> RulesUnitObjectiveProximityWitnessPayload:
        return {
            "rules_unit_instance_id": self.rules_unit_instance_id,
            "component_unit_instance_ids": list(self.component_unit_instance_ids),
            "objective_marker_witnesses": [
                witness.to_payload() for witness in self.objective_marker_witnesses
            ],
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        raw = _payload_mapping(
            payload,
            expected_fields={
                "rules_unit_instance_id",
                "component_unit_instance_ids",
                "objective_marker_witnesses",
            },
            field_name="RulesUnitObjectiveProximityWitness payload",
        )
        raw_witnesses = raw["objective_marker_witnesses"]
        if type(raw_witnesses) is not list:
            raise GameLifecycleError(
                "RulesUnitObjectiveProximityWitness objective_marker_witnesses must be a list."
            )
        return cls(
            rules_unit_instance_id=_validate_identifier(
                "rules_unit_instance_id",
                raw["rules_unit_instance_id"],
            ),
            component_unit_instance_ids=_identifier_tuple_from_payload_list(
                "component_unit_instance_ids",
                raw["component_unit_instance_ids"],
                require_non_empty=True,
            ),
            objective_marker_witnesses=tuple(
                ObjectiveMarkerModelWitness.from_payload(item)
                for item in cast(list[object], raw_witnesses)
            ),
        )


def rules_unit_objective_proximity_witness(
    *,
    state: GameState,
    rules_unit_instance_id: str,
    included_destroyed_model_placement: ModelPlacement | None = None,
) -> RulesUnitObjectiveProximityWitness:
    """Capture exact, group-aware objective proximity at the current event boundary."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Objective proximity evidence requires GameState.")
    requested_rules_unit_id = _validate_identifier(
        "rules_unit_instance_id",
        rules_unit_instance_id,
    )
    rules_units = current_rules_unit_views_for_canonical_identity(
        state=state,
        unit_instance_id=requested_rules_unit_id,
    )
    component_ids, model_by_id = _rules_unit_component_and_model_inventory(rules_units)
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Objective proximity evidence requires battlefield_state.")
    geometry_models_by_id: dict[str, GeometryModel] = {}
    for rules_unit in rules_units:
        for component in rules_unit.components:
            placement = battlefield.unit_placement_or_none(component.unit.unit_instance_id)
            if placement is None:
                continue
            for model_placement in placement.model_placements:
                model = model_by_id.get(model_placement.model_instance_id)
                if model is None or not model_is_present_on_battlefield(
                    state=state,
                    model_instance_id=model.model_instance_id,
                ):
                    continue
                geometry_models_by_id[model.model_instance_id] = geometry_model_for_placement(
                    model=model,
                    placement=model_placement,
                )
    if included_destroyed_model_placement is not None:
        if type(included_destroyed_model_placement) is not ModelPlacement:
            raise GameLifecycleError(
                "Included destroyed-model objective evidence must be a ModelPlacement."
            )
        destroyed_model_id = included_destroyed_model_placement.model_instance_id
        destroyed_model = model_by_id.get(destroyed_model_id)
        if destroyed_model is None:
            raise GameLifecycleError(
                "Included destroyed-model objective evidence is outside the rules unit."
            )
        if included_destroyed_model_placement.unit_instance_id not in component_ids:
            raise GameLifecycleError(
                "Included destroyed-model objective evidence component identity drift."
            )
        geometry_models_by_id[destroyed_model_id] = geometry_model_for_placement(
            model=destroyed_model,
            placement=included_destroyed_model_placement,
        )
    return _objective_proximity_witness_from_geometry_models(
        state=state,
        rules_unit_instance_id=requested_rules_unit_id,
        component_unit_instance_ids=component_ids,
        geometry_models_by_id=geometry_models_by_id,
    )


def rules_unit_objective_proximity_witness_from_placements(
    *,
    state: GameState,
    rules_unit_instance_id: str,
    model_placements: tuple[ModelPlacement, ...],
) -> RulesUnitObjectiveProximityWitness:
    """Capture objective proximity from authenticated event-time model endpoints."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Objective proximity evidence requires GameState.")
    requested_rules_unit_id = _validate_identifier(
        "rules_unit_instance_id",
        rules_unit_instance_id,
    )
    rules_units = current_rules_unit_views_for_canonical_identity(
        state=state,
        unit_instance_id=requested_rules_unit_id,
    )
    component_ids, model_by_id = _rules_unit_component_and_model_inventory(rules_units)
    if type(model_placements) is not tuple:
        raise GameLifecycleError("Objective proximity endpoint placements must be a tuple.")
    component_by_model_id = {
        model.model_instance_id: component.unit.unit_instance_id
        for rules_unit in rules_units
        for component in rules_unit.components
        for model in component.unit.own_models
    }
    geometry_models_by_id: dict[str, GeometryModel] = {}
    for placement in model_placements:
        if type(placement) is not ModelPlacement:
            raise GameLifecycleError(
                "Objective proximity endpoint evidence must contain ModelPlacement values."
            )
        model = model_by_id.get(placement.model_instance_id)
        if (
            model is None
            or component_by_model_id[model.model_instance_id] != placement.unit_instance_id
            or placement.unit_instance_id not in component_ids
        ):
            raise GameLifecycleError("Objective proximity endpoint model identity drift.")
        if placement.model_instance_id in geometry_models_by_id:
            raise GameLifecycleError("Objective proximity endpoint model identity is duplicated.")
        geometry_models_by_id[placement.model_instance_id] = geometry_model_for_placement(
            model=model,
            placement=placement,
        )
    if not geometry_models_by_id:
        raise GameLifecycleError("Objective proximity endpoint evidence must not be empty.")
    return _objective_proximity_witness_from_geometry_models(
        state=state,
        rules_unit_instance_id=requested_rules_unit_id,
        component_unit_instance_ids=component_ids,
        geometry_models_by_id=geometry_models_by_id,
    )


def _rules_unit_component_and_model_inventory(
    rules_units: tuple[RulesUnitView, ...],
) -> tuple[tuple[str, ...], dict[str, ModelInstance]]:
    if type(rules_units) is not tuple or any(
        type(rules_unit) is not RulesUnitView for rules_unit in rules_units
    ):
        raise GameLifecycleError("Objective proximity rules-unit inventory must be typed.")
    component_ids = tuple(
        sorted(
            component.unit.unit_instance_id
            for rules_unit in rules_units
            for component in rules_unit.components
        )
    )
    if not component_ids or len(component_ids) != len(set(component_ids)):
        raise GameLifecycleError("Objective proximity component inventory is invalid.")
    model_by_id = {
        model.model_instance_id: model
        for rules_unit in rules_units
        for component in rules_unit.components
        for model in component.unit.own_models
    }
    if len(model_by_id) != sum(
        len(component.unit.own_models)
        for rules_unit in rules_units
        for component in rules_unit.components
    ):
        raise GameLifecycleError("Objective proximity model inventory is duplicated.")
    return component_ids, model_by_id


def _objective_proximity_witness_from_geometry_models(
    *,
    state: GameState,
    rules_unit_instance_id: str,
    component_unit_instance_ids: tuple[str, ...],
    geometry_models_by_id: dict[str, GeometryModel],
) -> RulesUnitObjectiveProximityWitness:
    mission_setup = state.mission_setup
    if mission_setup is None:
        return RulesUnitObjectiveProximityWitness(
            rules_unit_instance_id=rules_unit_instance_id,
            component_unit_instance_ids=component_unit_instance_ids,
            objective_marker_witnesses=(),
        )
    marker_witnesses: list[ObjectiveMarkerModelWitness] = []
    for objective in mission_objective_geometries(state):
        qualifying_model_ids = tuple(
            sorted(
                model_id
                for model_id, geometry_model in geometry_models_by_id.items()
                if measure_model_to_objective(
                    model=geometry_model, objective=objective
                ).within_control_range
            )
        )
        if qualifying_model_ids:
            marker_witnesses.append(
                ObjectiveMarkerModelWitness(
                    objective_marker_id=objective.objective_id,
                    model_instance_ids=qualifying_model_ids,
                )
            )
    return RulesUnitObjectiveProximityWitness(
        rules_unit_instance_id=rules_unit_instance_id,
        component_unit_instance_ids=component_unit_instance_ids,
        objective_marker_witnesses=tuple(marker_witnesses),
    )


def destruction_source_objective_proximity_witness(
    *,
    state: GameState,
    event_log: EventLog,
    attribution: ModelDestructionAttribution,
    destroyed_model_placement: ModelPlacement,
) -> RulesUnitObjectiveProximityWitness | None:
    """Capture the source unit at emission, inheriting a Deadly Demise source death."""
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Destruction objective evidence requires EventLog.")
    if type(attribution) is not ModelDestructionAttribution:
        raise GameLifecycleError("Destruction objective evidence requires typed attribution.")
    source_rules_unit_id = attribution.source_rules_unit_instance_id
    if source_rules_unit_id is None:
        return None
    if (
        attribution.destruction_provenance.destruction_source_kind
        is DestructionSourceKind.DEADLY_DEMISE
    ):
        source_model_id = attribution.source_model_instance_id
        if source_model_id is None:
            raise GameLifecycleError(
                "Deadly Demise objective evidence requires its source model identity."
            )
        inherited = _deadly_demise_source_witness_or_none(
            event_log=event_log,
            source_model_instance_id=source_model_id,
        )
        if inherited is not None:
            if inherited.rules_unit_instance_id != source_rules_unit_id:
                raise GameLifecycleError("Deadly Demise objective evidence source identity drift.")
            return inherited
        battlefield = state.battlefield_state
        if battlefield is None:
            raise GameLifecycleError("Deadly Demise objective evidence requires battlefield_state.")
        source_placement = battlefield.model_placement_or_none(source_model_id)
        if source_placement is None:
            raise GameLifecycleError(
                "Deadly Demise objective evidence requires either an inherited source "
                "destruction witness or its source model's pre-removal placement."
            )
        return rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=source_rules_unit_id,
            included_destroyed_model_placement=source_placement,
        )
    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=destroyed_model_placement.unit_instance_id,
    )
    return rules_unit_objective_proximity_witness(
        state=state,
        rules_unit_instance_id=source_rules_unit_id,
        included_destroyed_model_placement=(
            destroyed_model_placement
            if target_rules_unit.unit_instance_id == source_rules_unit_id
            else None
        ),
    )


def _deadly_demise_source_witness_or_none(
    *,
    event_log: EventLog,
    source_model_instance_id: str,
) -> RulesUnitObjectiveProximityWitness | None:
    requested_model_id = _validate_identifier(
        "source_model_instance_id",
        source_model_instance_id,
    )
    for record in reversed(event_log.records):
        if record.event_type != "model_destroyed" or not isinstance(record.payload, dict):
            continue
        if record.payload.get("model_instance_id") != requested_model_id:
            continue
        raw_witness = record.payload.get("destroyed_rules_unit_objective_proximity_witness")
        if raw_witness is None:
            raise GameLifecycleError(
                "Deadly Demise source destruction lacks objective proximity evidence."
            )
        return RulesUnitObjectiveProximityWitness.from_payload(raw_witness)
    return None


def primary_unattributed_destruction_cause_from_token(
    value: object,
) -> PrimaryUnattributedDestructionCause:
    if isinstance(value, PrimaryUnattributedDestructionCause):
        return value
    if type(value) is not str:
        raise GameLifecycleError("Primary unattributed destruction cause must be a string.")
    try:
        return PrimaryUnattributedDestructionCause(value)
    except ValueError as exc:
        raise GameLifecycleError("Primary unattributed destruction cause is unsupported.") from exc


def _payload_mapping(
    payload: object,
    *,
    expected_fields: set[str],
    field_name: str,
) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    untyped_raw = cast(dict[object, object], payload)
    if any(type(key) is not str for key in untyped_raw):
        raise GameLifecycleError(f"{field_name} must be an object.")
    raw = cast(dict[str, object], payload)
    if set(raw) != expected_fields:
        raise GameLifecycleError(f"{field_name} fields are invalid.")
    return raw


def _identifier_tuple_from_payload_list(
    field_name: str,
    value: object,
    *,
    require_non_empty: bool,
) -> tuple[str, ...]:
    if type(value) is not list:
        raise GameLifecycleError(f"{field_name} must be a list in serialized payloads.")
    return _validate_identifier_tuple(
        field_name,
        tuple(cast(list[object], value)),
        require_non_empty=require_non_empty,
    )


def _validate_identifier_tuple(
    field_name: str,
    value: object,
    *,
    require_non_empty: bool,
) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers = tuple(
        _validate_identifier(field_name, item) for item in cast(tuple[object, ...], value)
    )
    if require_non_empty and not identifiers:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    if len(identifiers) != len(set(identifiers)):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(identifiers))


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "ObjectiveMarkerModelWitness",
    "ObjectiveMarkerModelWitnessPayload",
    "PrimaryUnattributedDestructionCause",
    "RulesUnitObjectiveProximityWitness",
    "RulesUnitObjectiveProximityWitnessPayload",
    "destruction_source_objective_proximity_witness",
    "primary_unattributed_destruction_cause_from_token",
    "rules_unit_objective_proximity_witness",
    "rules_unit_objective_proximity_witness_from_placements",
)
