from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from re import Pattern

ValidationErrorFactory = Callable[[str], ValueError]


def validate_identifier(
    field_name: str,
    value: object,
    *,
    error_factory: ValidationErrorFactory,
    reject_object_repr: bool = False,
    message_prefix: str = "",
    pattern: Pattern[str] | None = None,
    pattern_message: str | None = None,
) -> str:
    display_name = _display_field_name(field_name, message_prefix=message_prefix)
    if type(value) is not str:
        raise error_factory(f"{display_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise error_factory(f"{display_name} must not be empty.")
    if pattern is not None and not pattern.fullmatch(stripped):
        message = (
            f"{display_name} is invalid."
            if pattern_message is None
            else pattern_message.format(field_name=display_name)
        )
        raise error_factory(message)
    if reject_object_repr and ("<" in stripped or "object at 0x" in stripped):
        raise error_factory(f"{display_name} must be JSON-safe and not an object repr.")
    return stripped


@dataclass(frozen=True, slots=True)
class IdentifierValidator:
    error_factory: ValidationErrorFactory
    reject_object_repr: bool = False
    message_prefix: str = ""
    pattern: Pattern[str] | None = None
    pattern_message: str | None = None

    def __call__(self, field_name: str, value: object) -> str:
        return validate_identifier(
            field_name,
            value,
            error_factory=self.error_factory,
            reject_object_repr=self.reject_object_repr,
            message_prefix=self.message_prefix,
            pattern=self.pattern,
            pattern_message=self.pattern_message,
        )


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


def _display_field_name(field_name: str, *, message_prefix: str) -> str:
    if not message_prefix:
        return field_name
    return f"{message_prefix} {field_name}"
