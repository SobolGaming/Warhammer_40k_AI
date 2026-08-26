from __future__ import annotations

from functools import cache

from warhammer40k_core.engine.datasheet_faction_access import (
    DatasheetFactionAccessRegistry,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.aeldari import mustering


@cache
def default_datasheet_faction_access_registry() -> DatasheetFactionAccessRegistry:
    return DatasheetFactionAccessRegistry.from_bindings(
        mustering.datasheet_faction_access_bindings()
    )


__all__ = ("default_datasheet_faction_access_registry",)
