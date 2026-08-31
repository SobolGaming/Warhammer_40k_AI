from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.catalog_selected_target_battle_shock_continuation import (
    validate_restored_catalog_selected_target_battle_shock_continuation,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.phases.movement_battle_shock_continuation import (
    validate_restored_desperate_escape_battle_shock_continuation,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.game_state import GameState


def validate_restored_battle_shock_continuations(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_content_bundle: RuntimeContentBundle | None,
) -> None:
    validate_restored_desperate_escape_battle_shock_continuation(
        state=state,
        decisions=decisions,
        runtime_content_bundle=runtime_content_bundle,
    )
    validate_restored_catalog_selected_target_battle_shock_continuation(
        state=state,
        decisions=decisions,
        runtime_content_bundle=runtime_content_bundle,
    )


__all__ = ("validate_restored_battle_shock_continuations",)
