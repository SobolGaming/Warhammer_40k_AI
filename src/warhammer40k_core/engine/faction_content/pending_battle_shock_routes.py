from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warhammer40k_core.engine.battle_shock_hooks import (
        BattleShockPendingOutcomeAuthorityContext,
        BattleShockPendingOutcomeAuthorityValidator,
    )


def pending_battle_shock_outcome_needs_validation(
    validator: BattleShockPendingOutcomeAuthorityValidator,
    context: BattleShockPendingOutcomeAuthorityContext,
) -> bool:
    from .warhammer_40000_11th.chaos_daemons import battle_shock_outcome_authority

    return battle_shock_outcome_authority.native_pending_outcome_needs_validation(
        validator, context
    )
