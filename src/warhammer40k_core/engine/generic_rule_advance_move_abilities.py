from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.advance_hooks import AdvanceMoveContext, AdvanceMoveGrant
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.generic_rule_ability_registry import (
        GenericRuleAbilityHookFamily,
        GenericRuleAbilitySource,
    )

type AdvanceMoveTargetUnitIdBuilder = Callable[[AdvanceMoveContext], str]
type AdvanceMoveContextPredicate = Callable[
    [AdvanceMoveContext, "GenericRuleAbilitySource", tuple[PersistingEffect, ...]],
    bool,
]
type AdvanceMoveGrantBuilder = Callable[
    [AdvanceMoveContext, "GenericRuleAbilitySource", tuple[PersistingEffect, ...]],
    AdvanceMoveGrant,
]
type AdvanceMoveHookIdBuilder = Callable[["GenericRuleAbilitySource"], str]


@dataclass(frozen=True, slots=True)
class GenericRuleAdvanceMoveAbility:
    ability_id: str
    coverage_descriptor_id: str
    source_rule_id: str
    hook_id_builder: AdvanceMoveHookIdBuilder
    target_unit_id_builder: AdvanceMoveTargetUnitIdBuilder
    context_predicate: AdvanceMoveContextPredicate
    grant_builder: AdvanceMoveGrantBuilder

    @property
    def hook_family(self) -> GenericRuleAbilityHookFamily:
        from warhammer40k_core.engine.generic_rule_ability_registry import (
            GenericRuleAbilityHookFamily,
        )

        return GenericRuleAbilityHookFamily.ADVANCE_MOVE

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ability_id",
            _validate_identifier("generic advance move ability_id", self.ability_id),
        )
        object.__setattr__(
            self,
            "coverage_descriptor_id",
            _validate_identifier(
                "generic advance move coverage_descriptor_id",
                self.coverage_descriptor_id,
            ),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("generic advance move source_rule_id", self.source_rule_id),
        )
        _validate_callable("Generic advance move ability hook_id_builder", self.hook_id_builder)
        _validate_callable(
            "Generic advance move ability target_unit_id_builder",
            self.target_unit_id_builder,
        )
        _validate_callable(
            "Generic advance move ability context_predicate",
            self.context_predicate,
        )
        _validate_callable("Generic advance move ability grant_builder", self.grant_builder)

    def ability_ids(self) -> tuple[str, ...]:
        return (self.ability_id,)

    def hook_id(self, source: GenericRuleAbilitySource) -> str:
        return _validate_identifier("hook_id", self.hook_id_builder(source))

    def target_unit_instance_id(self, context: AdvanceMoveContext) -> str:
        return _validate_identifier("unit_instance_id", self.target_unit_id_builder(context))


def _validate_callable(field_name: str, value: object) -> None:
    if not callable(value):
        raise GameLifecycleError(f"{field_name} must be callable.")


_validate_identifier = IdentifierValidator(GameLifecycleError)
