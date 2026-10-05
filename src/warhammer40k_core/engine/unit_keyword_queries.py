from __future__ import annotations

from warhammer40k_core.core.keyword_membership import (
    exclusive_name_keywords,
    keyword_inventory_contains,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance

_validate_identifier = IdentifierValidator(GameLifecycleError)


def unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("unit keyword check requires a UnitInstance.")
    return keyword_inventory_contains(
        keywords=unit.keywords,
        keyword=keyword,
        name_keywords=unit_datasheet_name_keywords(unit),
        normalizer=_canonical_keyword,
    )


def unit_has_roster_keyword(unit: UnitInstance, keyword: str) -> bool:
    """Check preserved model identity, including casualties, for lineage validation.

    Current gameplay eligibility must use RulesUnitView keywords instead.
    """
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Roster keyword identity requires a UnitInstance.")
    return keyword_inventory_contains(
        keywords=(value for model in unit.own_models for value in model.keywords),
        keyword=keyword,
        name_keywords=unit_datasheet_name_keywords(unit, include_destroyed=True),
        normalizer=_canonical_keyword,
    )


def unit_datasheet_name_keywords(
    unit: UnitInstance, *, include_destroyed: bool = False
) -> tuple[str, ...]:
    return exclusive_name_keywords(
        model.keyword_assignment
        for model in unit.own_models
        if (model.is_alive or include_destroyed)
    )


def _canonical_keyword(keyword: str) -> str:
    return _validate_identifier("unit keyword", keyword).upper().replace(" ", "_").replace("-", "_")
