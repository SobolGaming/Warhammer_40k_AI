from __future__ import annotations

from warhammer40k_core.core.datasheet import DatasheetDefinition
from warhammer40k_core.engine.unit_resources import UnitStartingResourceAllocation
from warhammer40k_core.engine.wargear_selections import WargearSelection


class UnitResourceEntitlementError(ValueError):
    """Raised when source-backed unit-resource wargear choices are inconsistent."""


def derive_starting_resource_allocations(
    *,
    datasheet: DatasheetDefinition,
    wargear_selections: tuple[WargearSelection, ...],
) -> tuple[UnitStartingResourceAllocation, ...]:
    if type(datasheet) is not DatasheetDefinition:
        raise UnitResourceEntitlementError("Resource entitlement requires a DatasheetDefinition.")
    if type(wargear_selections) is not tuple:
        raise UnitResourceEntitlementError("Resource entitlement selections must be a tuple.")
    options_by_id = {option.option_id: option for option in datasheet.wargear_options}
    amounts_by_kind: dict[str, int] = {}
    for selection in wargear_selections:
        if type(selection) is not WargearSelection:
            raise UnitResourceEntitlementError(
                "Resource entitlement selections must contain WargearSelection values."
            )
        option = options_by_id.get(selection.option_id)
        if option is None:
            raise UnitResourceEntitlementError(
                "Resource entitlement selection references an unknown option."
            )
        selection_limit = option.selection_limit
        if selection_limit is None:
            continue
        resource_kind = selection_limit.unit_resource_kind
        if resource_kind is None:
            continue
        if len(option.allowed_wargear_ids) != 1:
            raise UnitResourceEntitlementError(
                "Unit-resource wargear option must allow exactly one wargear ID."
            )
        if option.default_wargear_ids or option.conditions or option.effects:
            raise UnitResourceEntitlementError(
                "Unit-resource wargear option must not include model wargear semantics."
            )
        amount_per_selection = selection_limit.unit_resource_amount_per_selection
        if amount_per_selection is None:
            raise UnitResourceEntitlementError(
                "Unit-resource wargear option is missing its allocation amount."
            )
        selected_count = selection.resolved_selection_count
        if selected_count == 0:
            continue
        amounts_by_kind[resource_kind] = (
            amounts_by_kind.get(resource_kind, 0) + selected_count * amount_per_selection
        )
    return tuple(
        UnitStartingResourceAllocation(resource_kind=resource_kind, amount=amount)
        for resource_kind, amount in sorted(amounts_by_kind.items())
    )
