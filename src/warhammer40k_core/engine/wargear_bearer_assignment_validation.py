from __future__ import annotations

from warhammer40k_core.core.datasheet import DatasheetWargearOption
from warhammer40k_core.engine.list_validation_errors import ListValidationError
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
    WargearSelection,
)


def validate_wargear_bearer_assignments(
    *,
    selections: tuple[WargearSelection, ...],
    options_by_id: dict[str, DatasheetWargearOption],
    model_profile_selections: tuple[ModelProfileSelection, ...] | None,
    requested_option_ids: frozenset[str],
) -> None:
    if model_profile_selections is None:
        if any(selection.bearer_assignments for selection in selections):
            raise ListValidationError(
                "WargearSelection bearer assignment validation requires model profile selections."
            )
        return
    model_counts = {
        selection.model_profile_id: selection.model_count for selection in model_profile_selections
    }
    option_counts_by_bearer: dict[tuple[str, str, int], int] = {}
    group_counts_by_bearer: dict[tuple[str, str, int], int] = {}
    for selection in selections:
        if not selection.wargear_ids:
            continue
        option = options_by_id[selection.option_id]
        model_count = model_counts.get(selection.model_profile_id)
        if model_count is None:
            if selection.option_id in requested_option_ids or selection.bearer_assignments:
                raise ListValidationError(
                    "WargearSelection bearer assignment model profile is not selected."
                )
            continue
        limit = option.selection_limit
        assignment_is_required = (
            bool(option.effects)
            and limit is not None
            and limit.models_per_increment == 1
            and limit.max_option_selections_per_increment > 1
            and (
                model_count > 1
                or selection.resolved_selection_count > 1
                or len(selection.wargear_ids) > 1
            )
        )
        if assignment_is_required and not selection.bearer_assignments:
            raise ListValidationError(
                "Ambiguous structured WargearSelection requires bearer assignments."
            )
        for assignment in selection.bearer_assignments:
            if assignment.model_ordinal > model_count:
                raise ListValidationError(
                    "WargearSelection bearer assignment references a missing model ordinal."
                )
            if limit is not None and limit.models_per_increment != 1:
                raise ListValidationError(
                    "WargearSelection bearer assignment requires a per-model selection limit."
                )
            option_key = (
                selection.model_profile_id,
                selection.option_id,
                assignment.model_ordinal,
            )
            option_count = option_counts_by_bearer.get(option_key, 0) + assignment.selection_count
            max_option_count = 1 if limit is None else limit.max_option_selections_per_increment
            if option_count > max_option_count:
                raise ListValidationError(
                    "WargearSelection bearer assignment exceeds the per-model option limit."
                )
            option_counts_by_bearer[option_key] = option_count
            if limit is None:
                continue
            group_key = (
                selection.model_profile_id,
                limit.selection_group_id,
                assignment.model_ordinal,
            )
            group_count = group_counts_by_bearer.get(group_key, 0) + assignment.selection_count
            if group_count > limit.max_group_selections_per_increment:
                raise ListValidationError(
                    "WargearSelection bearer assignments exceed the per-model group limit."
                )
            group_counts_by_bearer[group_key] = group_count
