"""Allow authenticated casualty gaps until the mandatory turn-end cleanup."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind, BattlefieldScenario
from warhammer40k_core.engine.phase import GameLifecycleStage

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def scenario_for_required_restore_coherency(
    *, scenario: BattlefieldScenario, state: GameState
) -> BattlefieldScenario:
    """Setup and unaffected units remain subject to their ordinary coherency check.

    Destruction provenance is validated by the caller before this projection and
    the shared departure inventory is also validated during lifecycle restore.
    Casualties can split a coherent unit during a turn; the rules require its
    survivors to regain coherency through end-turn cleanup, not immediately.
    """
    if state.stage is not GameLifecycleStage.BATTLE or any(
        cleanup.battle_round == state.battle_round
        and cleanup.active_player_id == state.active_player_id
        for cleanup in state.end_turn_cleanup_states
    ):
        return scenario
    pending_components = {
        component_id
        for departure in state.primary_battlefield_departure_states
        if departure.removal_kind is BattlefieldRemovalKind.DESTROYED
        and departure.battle_round == state.battle_round
        and departure.active_player_id == state.active_player_id
        for component_id in departure.affected_component_unit_instance_ids
    }
    return replace(
        scenario,
        battlefield_state=scenario.battlefield_state.with_removed_models(
            tuple(
                model.model_instance_id
                for army in scenario.battlefield_state.placed_armies
                for unit in army.unit_placements
                if unit.unit_instance_id in pending_components
                for model in unit.model_placements
            )
        ),
    )
