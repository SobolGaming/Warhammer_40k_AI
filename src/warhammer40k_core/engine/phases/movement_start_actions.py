from __future__ import annotations

# The phase owner shares these implementation steps with its action dispatcher.
# pyright: reportPrivateUsage=false
from collections.abc import Mapping

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.advance_hooks import AdvanceMoveHookRegistry
from warhammer40k_core.engine.catalog_fall_back_denial_sequencing import fall_back_denied_for_action
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.phases.movement_model import (
    MovementPhaseActionKind,
    PendingMovementActionSelection,
)
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex


def resume_move_start_action(
    *,
    state: GameState,
    decisions: DecisionController,
    pending_action: PendingMovementActionSelection,
    ruleset_descriptor: RulesetDescriptor,
    reaction_queue: ReactionQueue | None,
    stratagem_index: StratagemCatalogIndex | None,
    cost_modifiers: StratagemCostModifierRegistry,
    advance_move_hooks: AdvanceMoveHookRegistry,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    """Finish all source-owned start rules before the move's roll or proposal."""
    from warhammer40k_core.engine.movement_start_sequencing import resolve_move_start_rules
    from warhammer40k_core.engine.phases.movement_action_decisions import (
        _request_pending_movement_action_proposal,
        _resolve_pending_movement_action_after_grants,
    )
    from warhammer40k_core.engine.phases.movement_grant_sequencing import (
        selected_movement_grants,
    )
    from warhammer40k_core.engine.phases.movement_rules_units import (
        rules_unit_placement_for_movement,
    )
    from warhammer40k_core.engine.phases.movement_start_candidates import movement_start_candidates
    from warhammer40k_core.engine.phases.movement_validation import (
        _ability_index_for_player,
        _battlefield_scenario,
    )

    movement = state.movement_phase_state
    if (
        movement is None
        or movement.pending_action != pending_action
        or pending_action.movement_phase_action
        not in (
            MovementPhaseActionKind.NORMAL_MOVE,
            MovementPhaseActionKind.ADVANCE,
            MovementPhaseActionKind.FALL_BACK,
        )
    ):
        raise GameLifecycleError("Move-start continuation requires its pending movement action.")
    status = resolve_move_start_rules(
        state=state,
        decisions=decisions,
        pending_action=pending_action,
        discover=lambda: movement_start_candidates(
            state=state,
            decisions=decisions,
            pending=pending_action,
            grant_registry=advance_move_hooks,
            ability_indexes=ability_indexes_by_player_id,
            modifiers=runtime_modifier_registry,
            stratagem_index=stratagem_index,
            cost_modifiers=cost_modifiers,
        ),
    )
    if status is not None:
        return status
    state.replace_movement_phase_state(movement.without_pending_action())
    grants = selected_movement_grants(decisions, pending_action)
    if pending_action.movement_phase_action is MovementPhaseActionKind.FALL_BACK:
        if fall_back_denied_for_action(decisions=decisions, pending=pending_action):
            from warhammer40k_core.engine.phases.movement_fall_back_embark import (
                _complete_movement_activation,
            )

            _complete_movement_activation(
                state=state,
                decisions=decisions,
                result=pending_action.to_decision_result(),
                action=MovementPhaseActionKind.REMAIN_STATIONARY,
                witness=None,
                movement_payload={
                    "movement_inches": 0,
                    "model_movements": [],
                    "fall_back_denied": True,
                    "declared_movement_phase_action": MovementPhaseActionKind.FALL_BACK.value,
                },
            )
            return None
        return _request_pending_movement_action_proposal(
            state=state,
            decisions=decisions,
            pending_action=pending_action,
            ability_indexes_by_player_id=ability_indexes_by_player_id,
            selected_grants=grants,
        )
    _, placement = rules_unit_placement_for_movement(
        state=state,
        scenario=_battlefield_scenario(state),
        unit_instance_id=pending_action.unit_instance_id,
    )
    return _resolve_pending_movement_action_after_grants(
        state=state,
        decisions=decisions,
        pending_action=pending_action,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=placement,
        selected_advance_move_grants=grants,
        reaction_queue=reaction_queue,
        stratagem_index=stratagem_index,
        ability_index=_ability_index_for_player(
            ability_indexes_by_player_id, player_id=pending_action.player_id
        ),
        runtime_modifier_registry=runtime_modifier_registry,
    )
