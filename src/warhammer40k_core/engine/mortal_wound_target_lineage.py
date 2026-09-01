from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    current_rules_unit_views_for_canonical_identity,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.engine.unit_keyword_queries import unit_has_keyword

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


FROZEN_RULES_UNIT_COMPONENTS_POLICY = "frozen_rules_unit_components"

_validate_identifier = IdentifierValidator(GameLifecycleError)


class MortalWoundTargetLineagePayload(TypedDict):
    policy: str
    canonical_target_unit_instance_id: str
    owner_player_id: str
    component_unit_instance_ids: list[str]
    character_component_unit_instance_ids: list[str]


@dataclass(frozen=True, slots=True)
class MortalWoundTargetLineage:
    """Immutable rules-unit population for one in-flight mortal-wound packet."""

    policy: str
    canonical_target_unit_instance_id: str
    owner_player_id: str
    component_unit_instance_ids: tuple[str, ...]
    character_component_unit_instance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.policy != FROZEN_RULES_UNIT_COMPONENTS_POLICY:
            raise GameLifecycleError("Mortal-wound target lineage policy is unsupported.")
        object.__setattr__(
            self,
            "canonical_target_unit_instance_id",
            _validate_identifier(
                "Mortal-wound target lineage canonical target",
                self.canonical_target_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "owner_player_id",
            _validate_identifier(
                "Mortal-wound target lineage owner",
                self.owner_player_id,
            ),
        )
        component_ids = _identifier_tuple(
            "Mortal-wound target lineage component IDs",
            self.component_unit_instance_ids,
        )
        if not component_ids:
            raise GameLifecycleError("Mortal-wound target lineage requires components.")
        character_component_ids = _identifier_tuple(
            "Mortal-wound target lineage Character component IDs",
            self.character_component_unit_instance_ids,
        )
        if not set(character_component_ids).issubset(component_ids):
            raise GameLifecycleError(
                "Mortal-wound target lineage Character components must belong to the target."
            )
        object.__setattr__(self, "component_unit_instance_ids", component_ids)
        object.__setattr__(
            self,
            "character_component_unit_instance_ids",
            character_component_ids,
        )

    @classmethod
    def freeze(
        cls,
        *,
        state: GameState,
        target_unit_instance_id: str,
        owner_player_id: str,
    ) -> Self:
        target_id = _validate_identifier(
            "Mortal-wound target lineage target_unit_instance_id",
            target_unit_instance_id,
        )
        target = rules_unit_view_by_id(state=state, unit_instance_id=target_id)
        if target.unit_instance_id != target_id:
            raise GameLifecycleError("Mortal-wound target lineage requires a canonical target.")
        requested_owner_id = _validate_identifier(
            "Mortal-wound target lineage owner_player_id",
            owner_player_id,
        )
        if target.owner_player_id != requested_owner_id:
            raise GameLifecycleError("Mortal-wound target lineage owner drift.")
        character_component_ids = _authoritative_character_component_unit_instance_ids(
            state=state,
            canonical_target_unit_instance_id=target_id,
            views=(target,),
        )
        lineage = cls(
            policy=FROZEN_RULES_UNIT_COMPONENTS_POLICY,
            canonical_target_unit_instance_id=target_id,
            owner_player_id=requested_owner_id,
            component_unit_instance_ids=tuple(sorted(target.component_unit_instance_ids)),
            character_component_unit_instance_ids=character_component_ids,
        )
        lineage.validate_for_state(state)
        return lineage

    def validate_for_state(self, state: GameState) -> tuple[RulesUnitView, ...]:
        views = current_rules_unit_views_for_canonical_identity(
            state=state,
            unit_instance_id=self.canonical_target_unit_instance_id,
        )
        if {view.owner_player_id for view in views} != {self.owner_player_id}:
            raise GameLifecycleError("Mortal-wound target lineage owner drift.")
        current_component_ids = tuple(
            sorted(
                component_id for view in views for component_id in view.component_unit_instance_ids
            )
        )
        if current_component_ids != self.component_unit_instance_ids:
            raise GameLifecycleError("Mortal-wound target lineage component inventory drift.")
        expected_character_component_ids = _authoritative_character_component_unit_instance_ids(
            state=state,
            canonical_target_unit_instance_id=self.canonical_target_unit_instance_id,
            views=views,
        )
        if expected_character_component_ids != self.character_component_unit_instance_ids:
            raise GameLifecycleError(
                "Mortal-wound target lineage Character component classification drift."
            )
        return views

    def alive_placed_models(
        self,
        *,
        state: GameState,
    ) -> tuple[tuple[ModelInstance, ...], tuple[str, ...]]:
        views = self.validate_for_state(state)
        battlefield = state.battlefield_state
        if battlefield is None:
            raise GameLifecycleError("Mortal-wound target lineage requires battlefield_state.")
        placed_model_ids = set(battlefield.placed_model_ids())
        models = tuple(
            sorted(
                (
                    model
                    for view in views
                    for model in view.own_models
                    if model.is_alive and model.model_instance_id in placed_model_ids
                ),
                key=lambda model: model.model_instance_id,
            )
        )
        model_ids = tuple(model.model_instance_id for model in models)
        if len(model_ids) != len(set(model_ids)):
            raise GameLifecycleError("Mortal-wound target lineage model inventory is duplicated.")
        character_component_ids = set(self.character_component_unit_instance_ids)
        character_model_ids = tuple(
            sorted(
                model.model_instance_id
                for model in models
                if state.unit_instance_id_for_model(model.model_instance_id)
                in character_component_ids
            )
        )
        return models, character_model_ids

    def assert_contains_model(self, *, state: GameState, model_instance_id: str) -> None:
        self.validate_for_state(state)
        requested_model_id = _validate_identifier(
            "Mortal-wound target lineage model_instance_id",
            model_instance_id,
        )
        if state.unit_instance_id_for_model(requested_model_id) not in set(
            self.component_unit_instance_ids
        ):
            raise GameLifecycleError(
                "Mortal-wound model is not in the rules unit's frozen target lineage."
            )

    def to_payload(self) -> MortalWoundTargetLineagePayload:
        return {
            "policy": self.policy,
            "canonical_target_unit_instance_id": self.canonical_target_unit_instance_id,
            "owner_player_id": self.owner_player_id,
            "component_unit_instance_ids": list(self.component_unit_instance_ids),
            "character_component_unit_instance_ids": list(
                self.character_component_unit_instance_ids
            ),
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        expected_fields = {
            "policy",
            "canonical_target_unit_instance_id",
            "owner_player_id",
            "component_unit_instance_ids",
            "character_component_unit_instance_ids",
        }
        if not isinstance(payload, dict):
            raise GameLifecycleError("Mortal-wound target lineage fields are invalid.")
        raw = cast(dict[str, object], payload)
        if set(raw) != expected_fields:
            raise GameLifecycleError("Mortal-wound target lineage fields are invalid.")
        return cls(
            policy=_payload_identifier(raw, "policy"),
            canonical_target_unit_instance_id=_payload_identifier(
                raw,
                "canonical_target_unit_instance_id",
            ),
            owner_player_id=_payload_identifier(raw, "owner_player_id"),
            component_unit_instance_ids=_payload_identifier_tuple(
                raw,
                "component_unit_instance_ids",
            ),
            character_component_unit_instance_ids=_payload_identifier_tuple(
                raw,
                "character_component_unit_instance_ids",
            ),
        )


def _identifier_tuple(label: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{label} must be a tuple.")
    validated = tuple(
        _validate_identifier(f"{label} value", value) for value in cast(tuple[object, ...], values)
    )
    if validated != tuple(sorted(set(validated))):
        raise GameLifecycleError(f"{label} must be unique and sorted.")
    return validated


def _authoritative_character_component_unit_instance_ids(
    *,
    state: GameState,
    canonical_target_unit_instance_id: str,
    views: tuple[RulesUnitView, ...],
) -> tuple[str, ...]:
    current_target_views = tuple(
        view for view in views if view.unit_instance_id == canonical_target_unit_instance_id
    )
    if current_target_views:
        if len(current_target_views) != 1:
            raise GameLifecycleError("Mortal-wound target lineage current target is ambiguous.")
        current_target = current_target_views[0]
        role_character_component_ids = {
            component.unit.unit_instance_id
            for component in current_target.components
            if current_target.is_attached_rules_unit and component.role in {"leader", "support"}
        }
    else:
        starting_records = tuple(
            record
            for record in state.starting_attached_unit_records
            if record.attached_unit_instance_id == canonical_target_unit_instance_id
        )
        if len(starting_records) != 1:
            raise GameLifecycleError(
                "Mortal-wound target lineage historical Attached Unit authority is invalid."
            )
        role_character_component_ids = set(
            starting_records[0].leader_or_support_unit_instance_ids()
        )
    components_by_id = {
        component.unit.unit_instance_id: component.unit
        for view in views
        for component in view.components
    }
    if len(components_by_id) != sum(len(view.components) for view in views):
        raise GameLifecycleError("Mortal-wound target lineage component authority is duplicated.")
    return tuple(
        sorted(
            role_character_component_ids
            | {
                component_id
                for component_id, unit in components_by_id.items()
                if unit_has_keyword(unit, "CHARACTER")
            }
        )
    )


def _payload_identifier(payload: dict[str, object], key: str) -> str:
    return _validate_identifier(f"Mortal-wound target lineage {key}", payload.get(key))


def _payload_identifier_tuple(payload: dict[str, object], key: str) -> tuple[str, ...]:
    values = payload.get(key)
    if not isinstance(values, list):
        raise GameLifecycleError(f"Mortal-wound target lineage {key} must be a list.")
    raw_values = cast(list[object], values)
    return _identifier_tuple(
        f"Mortal-wound target lineage {key}",
        tuple(raw_values),
    )


__all__ = (
    "FROZEN_RULES_UNIT_COMPONENTS_POLICY",
    "MortalWoundTargetLineage",
    "MortalWoundTargetLineagePayload",
)
