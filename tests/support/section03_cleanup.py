"""Constructed chosen-casualty input to the real post-choice destruction owner.

D13 has no native choice producer. These test-owned requests authenticate an
explicit caller choice; they do NOT certify native end-turn choice discovery.
"""

from tests.support.section03_fixtures import scenario

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldTransitionBatch,
    ModelRemovalRecord,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    record_primary_unit_destructions_for_end_turn_cleanup,
)
from warhammer40k_core.engine.rule_model_destruction_unplaced import (
    destroy_end_turn_coherency_models,
)
from warhammer40k_core.engine.turn_cleanup import CoherencyCleanupRemoval, EndTurnCleanupState
from warhammer40k_core.engine.unit_coherency import unit_placement_coherency_result
from warhammer40k_core.engine.unit_factory import UnitInstance


def chosen_cleanup(
    state: GameState,
    unit: UnitInstance,
    chosen_id: str,
    decisions: DecisionController,
) -> EndTurnCleanupState:
    """Return a chosen typed input without applying a casualty or automatic choice."""
    board = scenario(state)
    placed = board.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    coherency = unit_placement_coherency_result(
        scenario=board, ruleset_descriptor=state.runtime_ruleset_descriptor(), unit_placement=placed
    )
    assert not coherency.is_coherent, "No further removal choice is permitted once coherent"
    before = state.to_payload()
    request = decisions.request_decision(
        DecisionRequest(
            request_id=f"constructed:chosen-cleanup:{len(decisions.records)}",
            decision_type="constructed_post_choice_cleanup",
            actor_id=placed.player_id,
            payload={"scope": "post-choice contract; native D13 producer absent"},
            options=tuple(
                DecisionOption(
                    option_id=row.model_instance_id,
                    label=row.model_instance_id,
                    payload={"model_instance_id": row.model_instance_id},
                )
                for row in placed.model_placements
            ),
        )
    )
    assert request.actor_id == "owner"
    result = DecisionResult.for_request(
        result_id=request.request_id + ":choice", request=request, selected_option_id=chosen_id
    )
    record = decisions.submit_result(result)
    assert record.request == request
    assert record.result == result
    assert state.to_payload() == before
    assert state.active_player_id is not None
    removal = CoherencyCleanupRemoval(
        player_id=request.actor_id,
        unit_instance_id=unit.unit_instance_id,
        model_instance_id=result.selected_option_id,
    )
    cleanup = EndTurnCleanupState(
        cleanup_id=request.request_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        phase="fight",
        removals=(removal,),
        coherency_results=(coherency,),
        transition_batch=BattlefieldTransitionBatch(
            removals=(
                ModelRemovalRecord(
                    model_instance_id=chosen_id,
                    removal_kind=BattlefieldRemovalKind.DESTROYED,
                    source_phase="fight",
                    source_step="end_turn_cleanup",
                    source_rule_id=removal.source_rule_id,
                    source_event_id=None,
                    destination_id=None,
                ),
            )
        ),
    )
    return EndTurnCleanupState.from_payload(cleanup.to_payload())


def apply_chosen_cleanup(state: GameState, cleanup: EndTurnCleanupState) -> None:
    """Existing engine owners validate context/physical owner, destroy and record evidence."""
    assert state.battlefield_state is not None
    destroy_end_turn_coherency_models(state=state, cleanup=cleanup)
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(cleanup.removed_model_instance_ids)
    )
    record_primary_unit_destructions_for_end_turn_cleanup(state=state, cleanup=cleanup)
