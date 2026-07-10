from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.army_mustering import ArmyDefinition, AttachedUnitFormation
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

RulesUnitComponentRole = Literal["bodyguard", "leader", "support", "unit"]


@dataclass(frozen=True, slots=True)
class RulesUnitComponent:
    unit: UnitInstance
    role: RulesUnitComponentRole

    def __post_init__(self) -> None:
        if type(self.unit) is not UnitInstance:
            raise GameLifecycleError("RulesUnitComponent unit must be a UnitInstance.")
        if self.role not in {"bodyguard", "leader", "support", "unit"}:
            raise GameLifecycleError("RulesUnitComponent has unsupported role.")


@dataclass(frozen=True, slots=True)
class RulesUnitView:
    unit_instance_id: str
    owner_player_id: str
    components: tuple[RulesUnitComponent, ...]
    attached_unit: AttachedUnitFormation | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("RulesUnitView unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "owner_player_id",
            _validate_identifier("RulesUnitView owner_player_id", self.owner_player_id),
        )
        if type(self.components) is not tuple:
            raise GameLifecycleError("RulesUnitView components must be a tuple.")
        if not self.components:
            raise GameLifecycleError("RulesUnitView requires at least one component.")
        for component in self.components:
            if type(component) is not RulesUnitComponent:
                raise GameLifecycleError(
                    "RulesUnitView components must contain RulesUnitComponent values."
                )
        if self.attached_unit is not None and type(self.attached_unit) is not (
            AttachedUnitFormation
        ):
            raise GameLifecycleError(
                "RulesUnitView attached_unit must be an AttachedUnitFormation."
            )
        if self.attached_unit is None and len(self.components) != 1:
            raise GameLifecycleError("Physical RulesUnitView requires exactly one component.")

    @property
    def component_unit_instance_ids(self) -> tuple[str, ...]:
        return tuple(component.unit.unit_instance_id for component in self.components)

    @property
    def own_models(self) -> tuple[ModelInstance, ...]:
        return tuple(model for component in self.components for model in component.unit.own_models)

    @property
    def keywords(self) -> tuple[str, ...]:
        keywords = {keyword for component in self.components for keyword in component.unit.keywords}
        return tuple(sorted(keywords))

    @property
    def faction_keywords(self) -> tuple[str, ...]:
        keywords = {
            keyword for component in self.components for keyword in component.unit.faction_keywords
        }
        return tuple(sorted(keywords))

    @property
    def is_attached_rules_unit(self) -> bool:
        return self.attached_unit is not None

    def component_unit_id_for_model(self, model_instance_id: str) -> str:
        requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
        for component in self.components:
            if any(
                model.model_instance_id == requested_model_id for model in component.unit.own_models
            ):
                return component.unit.unit_instance_id
        raise GameLifecycleError("RulesUnitView model_instance_id is not in the rules unit.")

    def component_role_for_model(self, model_instance_id: str) -> RulesUnitComponentRole:
        requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
        for component in self.components:
            if any(
                model.model_instance_id == requested_model_id for model in component.unit.own_models
            ):
                return component.role
        raise GameLifecycleError("RulesUnitView model_instance_id is not in the rules unit.")

    def alive_models(self) -> tuple[ModelInstance, ...]:
        return tuple(model for model in self.own_models if model.is_alive)

    def bodyguard_model_ids(self, models: Iterable[ModelInstance]) -> tuple[str, ...]:
        if self.attached_unit is None:
            return ()
        return tuple(
            sorted(
                model.model_instance_id
                for model in models
                if self.component_role_for_model(model.model_instance_id) == "bodyguard"
            )
        )

    def character_model_ids(self, models: Iterable[ModelInstance]) -> tuple[str, ...]:
        if self.attached_unit is None:
            return ()
        return tuple(
            sorted(
                model.model_instance_id
                for model in models
                if self.component_role_for_model(model.model_instance_id) in {"leader", "support"}
            )
        )


def rules_unit_view_by_id(*, state: GameState, unit_instance_id: str) -> RulesUnitView:
    return rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=unit_instance_id,
    )


def rules_unit_view_from_armies(
    *,
    armies: tuple[ArmyDefinition, ...],
    unit_instance_id: str,
) -> RulesUnitView:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in armies:
        attached_unit = _attached_unit_for_id(army=army, unit_instance_id=requested_id)
        if attached_unit is not None:
            return _attached_rules_unit_view(army=army, attached_unit=attached_unit)
    for army in armies:
        for unit in army.units:
            if unit.unit_instance_id == requested_id:
                return RulesUnitView(
                    unit_instance_id=unit.unit_instance_id,
                    owner_player_id=army.player_id,
                    components=(RulesUnitComponent(unit=unit, role="unit"),),
                    attached_unit=None,
                )
    raise GameLifecycleError("Rules unit_instance_id is unknown.")


def rules_unit_id_for_unit_id(
    *,
    armies: tuple[ArmyDefinition, ...],
    unit_instance_id: str,
) -> str:
    return rules_unit_view_from_armies(
        armies=armies,
        unit_instance_id=unit_instance_id,
    ).unit_instance_id


def rules_unit_owner_player_id(*, state: GameState, unit_instance_id: str) -> str:
    return rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id).owner_player_id


def placed_alive_models_for_component_unit(
    *, state: GameState, unit_instance_id: str
) -> tuple[ModelInstance, ...]:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    if state.battlefield_state is None:
        return ()
    placed_model_ids = frozenset(state.battlefield_state.placed_model_ids())
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=requested_id)
    component = next(
        (
            candidate
            for candidate in rules_unit.components
            if candidate.unit.unit_instance_id == requested_id
        ),
        None,
    )
    if component is None:
        raise GameLifecycleError("Rules unit does not contain the requested component unit.")
    return tuple(
        sorted(
            (
                model
                for model in component.unit.own_models
                if model.is_alive and model.model_instance_id in placed_model_ids
            ),
            key=lambda model: model.model_instance_id,
        )
    )


def _attached_unit_for_id(
    *,
    army: ArmyDefinition,
    unit_instance_id: str,
) -> AttachedUnitFormation | None:
    for attached_unit in army.attached_units:
        if attached_unit.attached_unit_instance_id == unit_instance_id:
            return attached_unit
        if unit_instance_id in attached_unit.component_unit_instance_ids:
            return attached_unit
    return None


def _attached_rules_unit_view(
    *,
    army: ArmyDefinition,
    attached_unit: AttachedUnitFormation,
) -> RulesUnitView:
    unit_by_id = {unit.unit_instance_id: unit for unit in army.units}
    components: list[RulesUnitComponent] = []
    for unit_id in attached_unit.component_unit_instance_ids:
        unit = unit_by_id.get(unit_id)
        if unit is None:
            raise GameLifecycleError("Attached rules-unit component is unknown.")
        if unit_id == attached_unit.bodyguard_unit_instance_id:
            role: RulesUnitComponentRole = "bodyguard"
        elif unit_id in attached_unit.leader_unit_instance_ids:
            role = "leader"
        elif unit_id in attached_unit.support_unit_instance_ids:
            role = "support"
        else:
            raise GameLifecycleError("Attached rules-unit component role is unknown.")
        components.append(RulesUnitComponent(unit=unit, role=role))
    return RulesUnitView(
        unit_instance_id=attached_unit.attached_unit_instance_id,
        owner_player_id=army.player_id,
        components=tuple(components),
        attached_unit=attached_unit,
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)
