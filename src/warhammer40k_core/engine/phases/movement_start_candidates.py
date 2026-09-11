from __future__ import annotations

# The phase owner shares its source context builders with discovery and validation.
# pyright: reportPrivateUsage=false
from collections.abc import Mapping

from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.advance_hooks import AdvanceMoveHookRegistry
from warhammer40k_core.engine.catalog_fall_back_denial_sequencing import fall_back_denial_candidates
from warhammer40k_core.engine.catalog_movement_target_pair_runtime import (
    CatalogMovementTargetPairRuntime,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phases.movement_grant_sequencing import movement_grant_candidates
from warhammer40k_core.engine.phases.movement_model import (
    MovementPhaseActionKind,
    PendingMovementActionSelection,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
from warhammer40k_core.engine.stratagem_timing_candidates import stratagem_timing_candidates
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex, StratagemEligibilityContext
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import TimingTriggerKind


def movement_start_candidates(
    *,
    state: GameState,
    decisions: DecisionController,
    pending: PendingMovementActionSelection,
    grant_registry: AdvanceMoveHookRegistry,
    ability_indexes: Mapping[str, AbilityCatalogIndex],
    modifiers: RuntimeModifierRegistry,
    stratagem_index: StratagemCatalogIndex | None,
    cost_modifiers: StratagemCostModifierRegistry,
) -> tuple[TimingRuleCandidate, ...]:
    catalog = CatalogMovementTargetPairRuntime(ability_indexes, tuple(state.army_definitions))
    return (
        *catalog.start_move_candidates(state=state, decisions=decisions, pending_action=pending),
        *movement_grant_candidates(
            state=state, decisions=decisions, pending=pending, registry=grant_registry
        ),
        *fall_back_denial_candidates(
            state=state,
            decisions=decisions,
            pending=pending,
            ability_indexes=ability_indexes,
            modifiers=modifiers,
        ),
        *_fall_back_stratagem_candidates(
            state=state,
            decisions=decisions,
            pending=pending,
            index=stratagem_index,
            cost_modifiers=cost_modifiers,
        ),
    )


def _fall_back_stratagem_candidates(
    *,
    state: GameState,
    decisions: DecisionController,
    pending: PendingMovementActionSelection,
    index: StratagemCatalogIndex | None,
    cost_modifiers: StratagemCostModifierRegistry,
) -> tuple[TimingRuleCandidate, ...]:
    from warhammer40k_core.engine.phases.movement_reactions import (
        _selected_to_fall_back_timing_window_id,
        _selected_to_fall_back_trigger_payload,
    )

    if pending.movement_phase_action is not MovementPhaseActionKind.FALL_BACK or index is None:
        return ()
    payload = _selected_to_fall_back_trigger_payload(pending)
    candidates: list[TimingRuleCandidate] = []
    for player in state.player_ids:
        if player == pending.player_id:
            continue
        window_id = _selected_to_fall_back_timing_window_id(
            pending_action=pending, reacting_player_id=player
        )
        context = StratagemEligibilityContext.from_state(
            state=state,
            player_id=player,
            trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_SELECTED_TO_FALL_BACK,
            timing_window_id=window_id,
            trigger_payload={**payload, "timing_window_id": window_id},
        )
        candidates.extend(
            stratagem_timing_candidates(
                state=state,
                decisions=decisions,
                index=index,
                context=context,
                cost_modifiers=cost_modifiers,
                requested_event_type="selected_fall_back_stratagem_requested",
            )
        )
    return tuple(candidates)
