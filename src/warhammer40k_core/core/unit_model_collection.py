from __future__ import annotations

from warhammer40k_core.core.unit import Unit, UnitMember


def all_models_for_units(units: tuple[Unit, ...]) -> tuple[UnitMember, ...]:
    return tuple(member for unit in units for member in unit.own_models)


def alive_models_for_units(units: tuple[Unit, ...]) -> tuple[UnitMember, ...]:
    return tuple(member for unit in units for member in unit.alive_own_models())
