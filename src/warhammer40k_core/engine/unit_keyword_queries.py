from __future__ import annotations

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance

_validate_identifier = IdentifierValidator(GameLifecycleError)


def unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("unit keyword check requires a UnitInstance.")
    requested_keyword = _canonical_keyword(keyword)
    unit_keywords = {_canonical_keyword(value) for value in unit.keywords}
    return requested_keyword in unit_keywords


def unit_has_roster_keyword(unit: UnitInstance, keyword: str) -> bool:
    """Check preserved model identity, including casualties, for lineage validation.

    Current gameplay eligibility must use RulesUnitView keywords instead.
    """
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Roster keyword identity requires a UnitInstance.")
    requested_keyword = _canonical_keyword(keyword)
    return any(
        _canonical_keyword(value) == requested_keyword
        for model in unit.own_models
        for value in model.keywords
    )


def _canonical_keyword(keyword: str) -> str:
    return _validate_identifier("unit keyword", keyword).upper().replace(" ", "_").replace("-", "_")
