from __future__ import annotations

from collections.abc import Mapping
from functools import partial

from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.catalog_movement_end_selected_target_effects import (
    CatalogMovementEndSelectedTargetEffectRuntime,
)
from warhammer40k_core.engine.catalog_setup_reactive_sequencing import setup_reactive_end_candidates
from warhammer40k_core.engine.core_movement_end_sequencing import core_movement_end_candidates
from warhammer40k_core.engine.movement_phase_end_mortal_wounds import movement_phase_end_candidates
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_stratagem_index
from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_end_hooks import (
    TurnEndHookBinding,
    TurnEndHookRegistry,
    TurnEndRequestContext,
)


def with_movement_end_rules(
    registry: TurnEndHookRegistry,
    *,
    abilities: Mapping[str, AbilityCatalogIndex],
    stratagems: Mapping[str, StratagemCatalogIndex],
    costs: StratagemCostModifierRegistry,
) -> TurnEndHookRegistry:
    from warhammer40k_core.engine.faction_content.stratagem_record_merge import (
        combine_stratagem_indexes_with_runtime_overrides,
    )

    combined_indexes = {
        player: combine_stratagem_indexes_with_runtime_overrides(
            base_indexes=(eleventh_edition_stratagem_index(),),
            runtime_indexes=(index,),
        )
        for player, index in stratagems.items()
    }
    return TurnEndHookRegistry.from_bindings(
        (
            *registry.bindings,
            TurnEndHookBinding(
                hook_id="core-rules:movement-end-providers",
                source_id="core-rules-lifecycle-timing",
                trigger_kind=TimingTriggerKind.END_PHASE,
                candidate_handler=partial(
                    movement_end_candidates,
                    abilities=abilities,
                    stratagems=combined_indexes,
                    costs=costs,
                ),
            ),
        )
    )


def movement_end_candidates(
    context: TurnEndRequestContext,
    *,
    abilities: Mapping[str, AbilityCatalogIndex],
    stratagems: Mapping[str, StratagemCatalogIndex],
    costs: StratagemCostModifierRegistry,
) -> tuple[TimingRuleCandidate, ...]:
    if context.completed_phase is not BattlePhase.MOVEMENT:
        return ()
    selected = CatalogMovementEndSelectedTargetEffectRuntime(
        ability_indexes_by_player_id=abilities,
        armies=tuple(context.state.army_definitions),
    )
    return (
        *movement_phase_end_candidates(state=context.state, decisions=context.decisions),
        *selected.candidates(state=context.state, decisions=context.decisions),
        *setup_reactive_end_candidates(context, ability_indexes=abilities),
        *core_movement_end_candidates(context, indexes=stratagems, cost_modifiers=costs),
    )
