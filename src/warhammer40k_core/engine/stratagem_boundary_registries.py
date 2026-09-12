"""Compose shared Stratagem candidates at source-declared phase boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from functools import partial

from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.faction_content.stratagem_record_merge import (
    combine_stratagem_indexes_with_runtime_overrides,
)
from warhammer40k_core.engine.movement_phase_end_sequencing import with_movement_end_rules
from warhammer40k_core.engine.phase_start_sequencing import phase_start_context
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    ShootingPhaseStartHookBinding,
    ShootingPhaseStartHookRegistry,
    ShootingPhaseStartRequestContext,
)
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_stratagem_index
from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
from warhammer40k_core.engine.stratagem_timing_candidates import stratagem_timing_candidates
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex, StratagemEligibilityContext
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_end_hooks import TurnEndHookRegistry


def with_stratagem_boundary_rules(
    end: TurnEndHookRegistry,
    start: ShootingPhaseStartHookRegistry,
    *,
    abilities: Mapping[str, AbilityCatalogIndex],
    stratagems: Mapping[str, StratagemCatalogIndex],
    costs: StratagemCostModifierRegistry,
) -> tuple[TurnEndHookRegistry, ShootingPhaseStartHookRegistry]:
    indexes = {
        player: combine_stratagem_indexes_with_runtime_overrides(
            base_indexes=(eleventh_edition_stratagem_index(),),
            runtime_indexes=(index,),
        )
        for player, index in stratagems.items()
    }
    return (
        with_movement_end_rules(end, abilities=abilities, stratagems=stratagems, costs=costs),
        ShootingPhaseStartHookRegistry.from_bindings(
            (
                *start.bindings,
                ShootingPhaseStartHookBinding(
                    hook_id="core-rules:shooting-start-stratagems",
                    source_id="core-rules-lifecycle-timing",
                    candidate_handler=partial(
                        shooting_start_candidates, indexes=indexes, costs=costs
                    ),
                ),
            )
        ),
    )


def shooting_start_candidates(
    context: ShootingPhaseStartRequestContext,
    *,
    indexes: Mapping[str, StratagemCatalogIndex],
    costs: StratagemCostModifierRegistry,
) -> tuple[TimingRuleCandidate, ...]:
    window = phase_start_context(context.state).timing_window
    return tuple(
        candidate
        for player in context.state.player_ids
        for candidate in stratagem_timing_candidates(
            state=context.state,
            decisions=context.decisions,
            index=indexes[player],
            context=StratagemEligibilityContext.from_state(
                state=context.state,
                player_id=player,
                trigger_kind=TimingTriggerKind.START_PHASE,
                timing_window_id=window.window_id,
            ),
            cost_modifiers=costs,
            requested_event_type="phase_start_stratagem_requested",
        )
    )
