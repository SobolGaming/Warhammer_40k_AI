from __future__ import annotations

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance

DEEP_STRIKE_ABILITY_IDS = frozenset({"000008343", "core-deep-strike", "deep-strike"})
DEEP_STRIKE_ABILITY_NAMES = frozenset({"DEEP_STRIKE", "CORE_DEEP_STRIKE"})


def unit_has_deep_strike(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Deep Strike ability check requires a UnitInstance.")
    return _unit_has_keyword(unit, "DEEP_STRIKE") or any(
        ability.ability_id in DEEP_STRIKE_ABILITY_IDS
        or _canonical_token(ability.name) in DEEP_STRIKE_ABILITY_NAMES
        for ability in unit.datasheet_abilities
    )


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    requested_keyword = _canonical_token(keyword)
    return requested_keyword in {_canonical_token(stored) for stored in unit.keywords}


def _canonical_token(value: str) -> str:
    if type(value) is not str:
        raise GameLifecycleError("Ability or keyword token must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError("Ability or keyword token must not be empty.")
    return stripped.upper().replace(" ", "_").replace("-", "_")
