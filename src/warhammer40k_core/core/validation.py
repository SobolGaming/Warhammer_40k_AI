from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.geometry.validation import (
    IdentifierValidator,
    ValidationErrorFactory,
    validate_identifier,
)

__all__ = (
    "FixedMessageIdentifierValidator",
    "IdentifierValidator",
    "ValidationErrorFactory",
    "canonical_keyword_token",
    "validate_identifier",
)


def canonical_keyword_token(value: str) -> str:
    return value.upper()


@dataclass(frozen=True, slots=True)
class FixedMessageIdentifierValidator:
    error_factory: ValidationErrorFactory
    string_message: str
    empty_message: str

    def __call__(self, value: object) -> str:
        if type(value) is not str:
            raise self.error_factory(self.string_message)
        stripped = value.strip()
        if not stripped:
            raise self.error_factory(self.empty_message)
        return stripped
