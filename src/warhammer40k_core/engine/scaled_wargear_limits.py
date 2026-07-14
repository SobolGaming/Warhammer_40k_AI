from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScaledWargearSelection:
    option_id: str
    selection_group_id: str
    models_per_increment: int
    max_group_selections_per_increment: int
    max_option_selections_per_increment: int
    selected_count: int


def validate_scaled_wargear_selections(
    *,
    unit_model_count: int,
    selections: tuple[ScaledWargearSelection, ...],
    error_type: type[ValueError],
) -> None:
    if type(unit_model_count) is not int or unit_model_count < 1:
        raise error_type("Scaled wargear unit model count must be a positive integer.")
    if type(selections) is not tuple or not selections:
        raise error_type("Scaled wargear validation requires selections.")
    limits_by_group: dict[str, tuple[int, int, int]] = {}
    group_selection_counts: dict[str, int] = {}
    for selection in selections:
        if type(selection) is not ScaledWargearSelection:
            raise error_type("Scaled wargear selections contain an invalid value.")
        _validate_scaled_wargear_selection(selection=selection, error_type=error_type)
        signature = (
            selection.models_per_increment,
            selection.max_group_selections_per_increment,
            selection.max_option_selections_per_increment,
        )
        existing = limits_by_group.get(selection.selection_group_id)
        if existing is not None and existing != signature:
            raise error_type("Scaled wargear options in one group must share limit metadata.")
        limits_by_group[selection.selection_group_id] = signature
        increments = unit_model_count // selection.models_per_increment
        if selection.selected_count > increments * selection.max_option_selections_per_increment:
            raise error_type("WargearSelection exceeds its model-count-scaled option limit.")
        group_selection_counts[selection.selection_group_id] = (
            group_selection_counts.get(selection.selection_group_id, 0) + selection.selected_count
        )
    for group_id, selected_count in group_selection_counts.items():
        models_per_increment, max_group_per_increment, _max_option = limits_by_group[group_id]
        increments = unit_model_count // models_per_increment
        if selected_count > increments * max_group_per_increment:
            raise error_type("WargearSelection group exceeds its model-count-scaled limit.")


def _validate_scaled_wargear_selection(
    *, selection: ScaledWargearSelection, error_type: type[ValueError]
) -> None:
    for field_name, value in (
        ("option_id", selection.option_id),
        ("selection_group_id", selection.selection_group_id),
    ):
        if type(value) is not str or not value.strip() or value != value.strip():
            raise error_type(f"Scaled wargear {field_name} must be non-empty stripped text.")
    _validate_positive_int(
        "models_per_increment", selection.models_per_increment, error_type=error_type
    )
    _validate_positive_int(
        "max_group_selections_per_increment",
        selection.max_group_selections_per_increment,
        error_type=error_type,
    )
    _validate_positive_int(
        "max_option_selections_per_increment",
        selection.max_option_selections_per_increment,
        error_type=error_type,
    )
    if type(selection.selected_count) is not int or selection.selected_count < 0:
        raise error_type("Scaled wargear selected_count must be a non-negative integer.")


def _validate_positive_int(field_name: str, value: object, *, error_type: type[ValueError]) -> None:
    if type(value) is not int or value < 1:
        raise error_type(f"Scaled wargear {field_name} must be a positive integer.")
