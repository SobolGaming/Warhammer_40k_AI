from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    UnitPlacement,
    UnitPlacementPayload,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.geometry.volume import Model


class RulesUnitPlacementPayload(TypedDict):
    rules_unit_instance_id: str
    component_unit_placements: list[UnitPlacementPayload]


@dataclass(frozen=True, slots=True)
class RulesUnitPlacement:
    """One physical placement for every component of a rules unit."""

    rules_unit_instance_id: str
    component_unit_placements: tuple[UnitPlacement, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rules_unit_instance_id",
            _validate_identifier(
                "RulesUnitPlacement rules_unit_instance_id",
                self.rules_unit_instance_id,
            ),
        )
        if type(self.component_unit_placements) is not tuple:
            raise GameLifecycleError(
                "RulesUnitPlacement component_unit_placements must be a tuple."
            )
        if not self.component_unit_placements:
            raise GameLifecycleError(
                "RulesUnitPlacement requires at least one component placement."
            )
        component_placements: list[UnitPlacement] = []
        component_ids: set[str] = set()
        model_ids: set[str] = set()
        army_id: str | None = None
        player_id: str | None = None
        for placement in self.component_unit_placements:
            if type(placement) is not UnitPlacement:
                raise GameLifecycleError(
                    "RulesUnitPlacement components must be UnitPlacement values."
                )
            if placement.unit_instance_id in component_ids:
                raise GameLifecycleError("RulesUnitPlacement component unit IDs must be unique.")
            component_ids.add(placement.unit_instance_id)
            if army_id is None:
                army_id = placement.army_id
                player_id = placement.player_id
            elif placement.army_id != army_id or placement.player_id != player_id:
                raise GameLifecycleError(
                    "RulesUnitPlacement components must share one army and player."
                )
            for model_placement in placement.model_placements:
                if model_placement.model_instance_id in model_ids:
                    raise GameLifecycleError(
                        "RulesUnitPlacement model IDs must be unique across components."
                    )
                model_ids.add(model_placement.model_instance_id)
            component_placements.append(placement)
        sorted_placements = tuple(
            sorted(component_placements, key=lambda placement: placement.unit_instance_id)
        )
        if len(sorted_placements) == 1:
            if sorted_placements[0].unit_instance_id != self.rules_unit_instance_id:
                raise GameLifecycleError(
                    "Single-component RulesUnitPlacement identity must match its component."
                )
        elif not self.rules_unit_instance_id.startswith("attached-unit:"):
            raise GameLifecycleError(
                "Multi-component RulesUnitPlacement requires attached-unit identity."
            )
        object.__setattr__(self, "component_unit_placements", sorted_placements)

    @classmethod
    def single(cls, placement: UnitPlacement) -> Self:
        if type(placement) is not UnitPlacement:
            raise GameLifecycleError("Single rules-unit placement requires UnitPlacement.")
        return cls(
            rules_unit_instance_id=placement.unit_instance_id,
            component_unit_placements=(placement,),
        )

    @property
    def army_id(self) -> str:
        return self.component_unit_placements[0].army_id

    @property
    def player_id(self) -> str:
        return self.component_unit_placements[0].player_id

    @property
    def component_unit_instance_ids(self) -> tuple[str, ...]:
        return tuple(placement.unit_instance_id for placement in self.component_unit_placements)

    @property
    def model_placements(self) -> tuple[ModelPlacement, ...]:
        return tuple(
            model_placement
            for component in self.component_unit_placements
            for model_placement in component.model_placements
        )

    def validate_for_view(self, view: RulesUnitView) -> None:
        if type(view) is not RulesUnitView:
            raise GameLifecycleError("RulesUnitPlacement validation requires RulesUnitView.")
        if self.rules_unit_instance_id != view.unit_instance_id:
            raise GameLifecycleError("RulesUnitPlacement rules-unit identity drift.")
        if self.player_id != view.owner_player_id:
            raise GameLifecycleError("RulesUnitPlacement owner drift.")
        if self.component_unit_instance_ids != view.component_unit_instance_ids:
            raise GameLifecycleError("RulesUnitPlacement component identity drift.")
        expected_model_ids = tuple(sorted(model.model_instance_id for model in view.alive_models()))
        submitted_model_ids = tuple(
            sorted(placement.model_instance_id for placement in self.model_placements)
        )
        if submitted_model_ids != expected_model_ids:
            raise GameLifecycleError(
                "RulesUnitPlacement must contain every alive model in the rules unit."
            )

    @classmethod
    def from_battlefield(
        cls,
        *,
        view: RulesUnitView,
        battlefield_state: BattlefieldRuntimeState,
    ) -> Self:
        if type(view) is not RulesUnitView:
            raise GameLifecycleError("Rules-unit placement requires RulesUnitView.")
        if type(battlefield_state) is not BattlefieldRuntimeState:
            raise GameLifecycleError("Rules-unit placement requires BattlefieldRuntimeState.")
        placements: list[UnitPlacement] = []
        for component_unit_id in view.component_unit_instance_ids:
            placement = battlefield_state.unit_placement_or_none(component_unit_id)
            if placement is None:
                raise GameLifecycleError("Every rules-unit component must be on the battlefield.")
            placements.append(placement)
        grouped = cls(
            rules_unit_instance_id=view.unit_instance_id,
            component_unit_placements=tuple(placements),
        )
        grouped.validate_for_view(view)
        return grouped

    def without_from_battlefield(
        self,
        battlefield_state: BattlefieldRuntimeState,
    ) -> BattlefieldRuntimeState:
        if type(battlefield_state) is not BattlefieldRuntimeState:
            raise GameLifecycleError("Rules-unit removal requires BattlefieldRuntimeState.")
        updated = battlefield_state
        for placement in self.component_unit_placements:
            updated = updated.without_unit_placement(placement.unit_instance_id)
        return updated

    def add_to_battlefield(
        self,
        battlefield_state: BattlefieldRuntimeState,
    ) -> BattlefieldRuntimeState:
        if type(battlefield_state) is not BattlefieldRuntimeState:
            raise GameLifecycleError("Rules-unit placement requires BattlefieldRuntimeState.")
        updated = battlefield_state
        for placement in self.component_unit_placements:
            updated = updated.with_added_unit_placement(placement)
        return updated

    def geometry_models(self, scenario: BattlefieldScenario) -> tuple[Model, ...]:
        if type(scenario) is not BattlefieldScenario:
            raise GameLifecycleError("Rules-unit geometry requires BattlefieldScenario.")
        return tuple(
            geometry_model_for_placement(
                model=scenario.model_instance_for_placement(placement),
                placement=placement,
            )
            for placement in self.model_placements
        )

    def to_payload(self) -> RulesUnitPlacementPayload:
        return {
            "rules_unit_instance_id": self.rules_unit_instance_id,
            "component_unit_placements": [
                placement.to_payload() for placement in self.component_unit_placements
            ],
        }

    @classmethod
    def from_payload(cls, payload: RulesUnitPlacementPayload) -> Self:
        return cls(
            rules_unit_instance_id=payload["rules_unit_instance_id"],
            component_unit_placements=tuple(
                UnitPlacement.from_payload(placement)
                for placement in payload["component_unit_placements"]
            ),
        )


_validate_identifier = IdentifierValidator(GameLifecycleError)
