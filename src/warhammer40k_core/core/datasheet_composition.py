from __future__ import annotations


def validate_unit_composition_counts(
    *,
    min_models: object,
    max_models: object,
    allows_zero_models: object,
    error_type: type[ValueError],
) -> tuple[int, int, bool]:
    if type(allows_zero_models) is not bool:
        raise error_type("UnitCompositionDefinition allows_zero_models must be a bool.")
    if type(min_models) is not int:
        raise error_type("UnitCompositionDefinition min_models must be an integer.")
    if min_models < (0 if allows_zero_models else 1):
        qualifier = "not be negative" if allows_zero_models else "be at least 1"
        raise error_type(f"UnitCompositionDefinition min_models must {qualifier}.")
    if allows_zero_models and min_models != 0:
        raise error_type("UnitCompositionDefinition allows_zero_models requires min_models 0.")
    if type(max_models) is not int:
        raise error_type("UnitCompositionDefinition max_models must be an integer.")
    if max_models < 1:
        raise error_type("UnitCompositionDefinition max_models must be at least 1.")
    if max_models < min_models:
        raise error_type("UnitCompositionDefinition max_models must be at least min_models.")
    return min_models, max_models, allows_zero_models
