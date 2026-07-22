from __future__ import annotations

import re

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.text_normalization import normalize_source_label


class MfmSourceError(ValueError):
    """Raised when Munitorum Field Manual source data violates CORE V2 invariants."""


_IDENTIFIER_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

validate_identifier = IdentifierValidator(
    MfmSourceError,
    pattern=_IDENTIFIER_RE,
    pattern_message="{field_name} must be a slug identifier.",
)


def validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise MfmSourceError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise MfmSourceError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(validated)


def validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return validate_identifier(field_name, value)


def validate_source_id(value: object) -> str:
    if type(value) is not str:
        raise MfmSourceError("source_id must be a string.")
    stripped = value.strip()
    if not stripped:
        raise MfmSourceError("source_id must not be empty.")
    return stripped


def validate_raw_label(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise MfmSourceError(f"{field_name} must be a string.")
    normalized = normalize_source_label(value)
    if not normalized:
        raise MfmSourceError(f"{field_name} must not be empty.")
    return normalized


def validate_url_path(value: object) -> str:
    if type(value) is not str:
        raise MfmSourceError("url_path must be a string.")
    stripped = value.strip()
    if not stripped.startswith("/en/"):
        raise MfmSourceError("url_path must be an English MFM path.")
    return stripped


def validate_source_url(value: object) -> str:
    if type(value) is not str:
        raise MfmSourceError("source_url must be a string.")
    stripped = value.strip()
    if not stripped.startswith("https://mfm.warhammer-community.com/en/"):
        raise MfmSourceError("source_url must be the English MFM source URL.")
    return stripped


def validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise MfmSourceError(f"{field_name} must be an integer.")
    if value <= 0:
        raise MfmSourceError(f"{field_name} must be positive.")
    return value


def validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise MfmSourceError(f"{field_name} must be an integer.")
    if value < 0:
        raise MfmSourceError(f"{field_name} must not be negative.")
    return value


def validate_optional_positive_int(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    return validate_positive_int(field_name, value)


def validate_optional_non_negative_int(
    field_name: str,
    value: object | None,
) -> int | None:
    if value is None:
        return None
    return validate_non_negative_int(field_name, value)
