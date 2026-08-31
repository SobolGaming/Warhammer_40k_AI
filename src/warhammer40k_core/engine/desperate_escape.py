from __future__ import annotations

from typing import Final

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_movement_phase_2026_08 as core_movement_phase_source,
)

DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_KIND: Final = "desperate_escape_battle_shock"
DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_RULE_ID: Final = (
    core_movement_phase_source.FALL_BACK_MOVE_SOURCE_ID
)
FALL_BACK_SELECTING_MODES_SOURCE_RULE_ID: Final = (
    core_movement_phase_source.SELECTING_MODES_SOURCE_ID
)

__all__ = (
    "DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_KIND",
    "DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_RULE_ID",
    "FALL_BACK_SELECTING_MODES_SOURCE_RULE_ID",
)
