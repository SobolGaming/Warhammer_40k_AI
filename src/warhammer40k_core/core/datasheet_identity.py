"""Normalize catalog identity once, independently of runtime display names."""

from warhammer40k_core.core.validation import (
    IdentifierValidator,
    ValidationErrorFactory,
    canonical_keyword_token,
)


def normalized_datasheet_identity(
    *, datasheet_id: object, name: object, error_factory: ValidationErrorFactory
) -> tuple[str, str, str]:
    validate = IdentifierValidator(error_factory)
    identifier = validate("DatasheetDefinition datasheet_id", datasheet_id)
    if identifier.startswith("datasheet:"):
        raise error_factory(
            "DatasheetDefinition datasheet_id must not include the stable identity prefix."
        )
    display_name = validate("DatasheetDefinition name", name)
    return identifier, display_name, canonical_keyword_token(display_name)
