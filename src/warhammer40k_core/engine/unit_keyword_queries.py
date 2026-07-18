from __future__ import annotations

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance

_validate_identifier = IdentifierValidator(GameLifecycleError)


def unit_has_aircraft_hover_keywords(keywords: tuple[str, ...]) -> bool:
    keyword_set = {
        _validate_identifier("unit keyword", keyword).upper().replace(" ", "_").replace("-", "_")
        for keyword in keywords
    }
    return "AIRCRAFT" in keyword_set and "HOVER" in keyword_set


def unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("unit keyword check requires a UnitInstance.")
    requested_keyword = (
        _validate_identifier("unit keyword", keyword).upper().replace(" ", "_").replace("-", "_")
    )
    unit_keywords = {
        _validate_identifier("unit keyword", value).upper().replace(" ", "_").replace("-", "_")
        for value in unit.keywords
    }
    return requested_keyword in unit_keywords
