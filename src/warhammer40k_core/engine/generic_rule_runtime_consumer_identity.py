from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.generic_rule_ability_registry import GenericRuleAbilitySource
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_subrules_2026_27,
)


@dataclass(frozen=True, slots=True)
class GenericRuleRuntimeConsumerIdBuilder:
    coverage_descriptor_id: str
    consumer_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "coverage_descriptor_id",
            _validate_identifier("coverage_descriptor_id", self.coverage_descriptor_id),
        )
        object.__setattr__(
            self,
            "consumer_id",
            _validate_identifier("consumer_id", self.consumer_id),
        )

    def __call__(self, source: GenericRuleAbilitySource) -> str:
        if type(source) is not GenericRuleAbilitySource:
            raise GameLifecycleError("Generic runtime consumer ID requires a generic source.")
        if source.record.coverage_descriptor_id != self.coverage_descriptor_id:
            raise GameLifecycleError("Generic runtime consumer source coverage descriptor drift.")
        if source.record.runtime_support_status != (
            faction_subrules_2026_27.SourceSubruleRuntimeStatus.ENGINE_CONSUMED.value
        ):
            raise GameLifecycleError("Generic runtime consumer source is not engine-consumed.")
        if self.consumer_id not in source.record.runtime_consumer_ids:
            raise GameLifecycleError("Generic runtime consumer identity drift.")
        return self.consumer_id


def generic_rule_runtime_consumer_id_builder(
    *,
    coverage_descriptor_id: str,
    consumer_id: str,
) -> GenericRuleRuntimeConsumerIdBuilder:
    return GenericRuleRuntimeConsumerIdBuilder(
        coverage_descriptor_id=coverage_descriptor_id,
        consumer_id=consumer_id,
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "GenericRuleRuntimeConsumerIdBuilder",
    "generic_rule_runtime_consumer_id_builder",
)
