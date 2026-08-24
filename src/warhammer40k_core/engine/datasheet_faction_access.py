from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Self

from warhammer40k_core.core.datasheet import DatasheetDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.list_validation_errors import ListValidationError


class DatasheetFactionAccessPredicate(Protocol):
    def __call__(
        self,
        *,
        datasheet: DatasheetDefinition,
        faction: FactionDefinition,
    ) -> bool: ...


_validate_identifier = IdentifierValidator(
    error_factory=ListValidationError,
    message_prefix="Datasheet faction access",
)


@dataclass(frozen=True, slots=True)
class DatasheetFactionAccessBinding:
    binding_id: str
    source_ability_id: str
    runtime_consumer_id: str
    predicate: DatasheetFactionAccessPredicate

    def __post_init__(self) -> None:
        for field_name in ("binding_id", "source_ability_id", "runtime_consumer_id"):
            object.__setattr__(
                self,
                field_name,
                _validate_identifier(field_name, getattr(self, field_name)),
            )
        if not callable(self.predicate):
            raise ListValidationError("Datasheet faction access predicate must be callable.")


@dataclass(frozen=True, slots=True)
class DatasheetFactionAccessRegistry:
    bindings: tuple[DatasheetFactionAccessBinding, ...]

    def __post_init__(self) -> None:
        if type(self.bindings) is not tuple or any(
            type(binding) is not DatasheetFactionAccessBinding for binding in self.bindings
        ):
            raise ListValidationError("Datasheet faction access registry requires typed bindings.")
        expected_order = tuple(sorted(self.bindings, key=lambda binding: binding.binding_id))
        if self.bindings != expected_order:
            raise ListValidationError("Datasheet faction access registry bindings must be sorted.")
        for field_name in ("binding_id", "source_ability_id", "runtime_consumer_id"):
            values = tuple(getattr(binding, field_name) for binding in self.bindings)
            if len(values) != len(set(values)):
                raise ListValidationError(
                    f"Datasheet faction access registry contains duplicate {field_name} values."
                )

    @classmethod
    def from_bindings(cls, bindings: tuple[DatasheetFactionAccessBinding, ...]) -> Self:
        if type(bindings) is not tuple or any(
            type(binding) is not DatasheetFactionAccessBinding for binding in bindings
        ):
            raise ListValidationError("Datasheet faction access registry requires typed bindings.")
        return cls(bindings=tuple(sorted(bindings, key=lambda binding: binding.binding_id)))

    @property
    def runtime_consumer_ids(self) -> tuple[str, ...]:
        return tuple(binding.runtime_consumer_id for binding in self.bindings)

    def allows(
        self,
        *,
        datasheet: DatasheetDefinition,
        faction: FactionDefinition,
    ) -> bool:
        if type(datasheet) is not DatasheetDefinition:
            raise ListValidationError(
                "Datasheet faction access lookup requires a DatasheetDefinition."
            )
        if type(faction) is not FactionDefinition:
            raise ListValidationError(
                "Datasheet faction access lookup requires a FactionDefinition."
            )
        for binding in self.bindings:
            allowed = binding.predicate(datasheet=datasheet, faction=faction)
            if type(allowed) is not bool:
                raise ListValidationError("Datasheet faction access predicate must return a bool.")
            if allowed:
                return True
        return False


__all__ = (
    "DatasheetFactionAccessBinding",
    "DatasheetFactionAccessPredicate",
    "DatasheetFactionAccessRegistry",
)
