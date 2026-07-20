from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.validation import IdentifierValidator, canonical_keyword_token
from warhammer40k_core.engine.catalog_conditional_leader_queries import (
    conditional_granted_ability_distance_inches,
    conditional_granted_ability_effects_for_unit,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.engine.unit_abilities import (
    scouts_ability_descriptors_for_unit,
    scouts_distance_inches_from_descriptor,
)

CORE_SCOUTS_SOURCE_RULE_ID = "core_rules:scouts"


class ScoutAbilityInstancePayload(TypedDict):
    model_instance_id: str
    distance_inches: float
    source_id: str


@dataclass(frozen=True, slots=True)
class ScoutAbilityInstance:
    model_instance_id: str
    distance_inches: float
    source_id: str = CORE_SCOUTS_SOURCE_RULE_ID

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier("ScoutAbilityInstance model_instance_id", self.model_instance_id),
        )
        object.__setattr__(
            self,
            "distance_inches",
            _validate_positive_number("ScoutAbilityInstance distance_inches", self.distance_inches),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("ScoutAbilityInstance source_id", self.source_id),
        )

    def to_payload(self) -> ScoutAbilityInstancePayload:
        return {
            "model_instance_id": self.model_instance_id,
            "distance_inches": self.distance_inches,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: ScoutAbilityInstancePayload) -> Self:
        return cls(
            model_instance_id=payload["model_instance_id"],
            distance_inches=payload["distance_inches"],
            source_id=payload["source_id"],
        )


def scout_ability_instances_for_rules_unit(
    *,
    state: GameState,
    view: RulesUnitView,
    army_catalog: ArmyCatalog,
) -> tuple[ScoutAbilityInstance, ...]:
    if type(state) is not GameState:
        raise GameLifecycleError("Scouts ability lookup requires a GameState.")
    if type(view) is not RulesUnitView:
        raise GameLifecycleError("Scouts ability lookup requires a RulesUnitView.")
    if type(army_catalog) is not ArmyCatalog:
        raise GameLifecycleError("Scouts ability lookup requires an ArmyCatalog.")
    instances: list[ScoutAbilityInstance] = []
    for component in view.components:
        descriptors = scouts_ability_descriptors_for_unit(component.unit)
        conditional_effects = conditional_granted_ability_effects_for_unit(
            state=state,
            rules_unit_instance_id=view.unit_instance_id,
            component_unit_instance_id=component.unit.unit_instance_id,
            ability="scouts",
        )
        if not descriptors and not conditional_effects:
            if canonical_keyword_token("SCOUTS") in {
                canonical_keyword_token(keyword) for keyword in component.unit.keywords
            }:
                raise GameLifecycleError(
                    "Scouts keyword requires a structured datasheet ability descriptor."
                )
            return ()
        for model in component.unit.alive_own_models():
            instances.extend(
                ScoutAbilityInstance(
                    model_instance_id=model.model_instance_id,
                    distance_inches=scouts_distance_inches_from_descriptor(descriptor),
                    source_id=descriptor.source_id,
                )
                for descriptor in descriptors
            )
            instances.extend(
                ScoutAbilityInstance(
                    model_instance_id=model.model_instance_id,
                    distance_inches=conditional_granted_ability_distance_inches(effect),
                    source_id=effect.source_rule_id,
                )
                for effect in conditional_effects
            )
    return tuple(
        sorted(
            instances,
            key=lambda instance: (
                instance.model_instance_id,
                instance.distance_inches,
                instance.source_id,
            ),
        )
    )


def _validate_positive_number(field_name: str, value: object) -> float:
    if type(value) not in {int, float}:
        raise GameLifecycleError(f"{field_name} must be a number.")
    number = float(cast(int | float, value))
    if not math.isfinite(number) or number <= 0.0:
        raise GameLifecycleError(f"{field_name} must be a positive finite number.")
    return number


_validate_identifier = IdentifierValidator(GameLifecycleError)
