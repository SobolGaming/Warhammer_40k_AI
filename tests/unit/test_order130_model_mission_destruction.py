from __future__ import annotations

from dataclasses import replace

import pytest
from tests.order130_helpers import (
    assert_destruction_checkpoint,
    destruction_session,
    finish_turn,
    native_destruction_session,
    unaffected_unit_with_invalid_coherency_payload,
)

from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.secondary_model_destruction_history import (
    SecondaryModelDestructionState,
    validate_secondary_model_destruction_boundary_history,
)
from warhammer40k_core.engine.secondary_scoring_conditions import (
    evaluate_secondary_scoring_condition,
)
from warhammer40k_core.engine.secondary_scoring_context import (
    secondary_scoring_condition_context_from_state,
)


@pytest.mark.parametrize("scoring_player", ["player-a", "player-b"])
@pytest.mark.parametrize("wounds", [9, 10])
def test_surviving_unit_coherency_casualty_scores_per_model(
    scoring_player: str, wounds: int
) -> None:
    session = destruction_session(scoring_player=scoring_player, wounds=wounds)
    if wounds == 9 and scoring_player == "player-a":
        invalid_placement = unaffected_unit_with_invalid_coherency_payload(session)
        with pytest.raises(GameLifecycleError, match="battlefield_state is invalid"):
            GameLifecycle.from_payload(invalid_placement)
    assert_destruction_checkpoint(session)
    state = session.lifecycle.state
    assert state is not None
    enemy = next(army for army in state.army_definitions if army.player_id != scoring_player).units[
        0
    ]
    bridge, isolated = enemy.own_models[-2:]
    finish_turn(session)
    assert any(
        isolated.model_instance_id in cleanup.removed_model_instance_ids
        for cleanup in state.end_turn_cleanup_states
    )
    assert state.battlefield_state is not None
    assert (
        len(state.battlefield_state.unit_placement_by_id(enemy.unit_instance_id).model_placements)
        == 3
    )
    assert state.primary_unit_destruction_states == []
    ledger = state.victory_point_ledger_for_player(scoring_player)
    transactions = tuple(row for row in ledger.transactions if "bring" in row.source_id)
    assert len(transactions) == (1 if wounds >= 10 else 0)
    if transactions:
        assert transactions[0].amount == 5  # Two models at four each, the admitted five-point cap.
        assert isinstance(transactions[0].metadata, dict)
        rule_evidence = transactions[0].metadata["evidence_by_rule"]
        assert isinstance(rule_evidence, dict)
        assert any(
            isinstance(row, dict)
            and row["destroyed_model_instance_ids"]
            == sorted((bridge.model_instance_id, isolated.model_instance_id))
            for row in rule_evidence.values()
        )
        record = next(
            row
            for row in state.objective_control_records
            if row.record_id == transactions[0].metadata["objective_control_record_id"]
        )
        context = secondary_scoring_condition_context_from_state(
            state=state, player_id=scoring_player, record=record, selection=None
        )
        condition = "each_enemy_model_w10_or_more_destroyed_this_turn"
        assert (
            evaluate_secondary_scoring_condition(condition=condition, context=context)[
                "score_count"
            ]
            == 2
        )
        assert (
            evaluate_secondary_scoring_condition(
                condition=condition,
                context=replace(
                    context,
                    player_id=next(
                        player for player in state.player_ids if player != scoring_player
                    ),
                ),
            )["score_count"]
            == 0
        )
        assert (
            evaluate_secondary_scoring_condition(
                condition=condition,
                context=replace(
                    context, record=replace(record, battle_round=record.battle_round + 1)
                ),
            )["score_count"]
            == 0
        )
        authority = next(
            row
            for row in state.objective_control_record_authorities
            if row.objective_control_record_id == record.record_id
        )
        before_cleanup = next(
            row
            for row in authority.boundary_checkpoint.model_states
            if row.model_instance_id == isolated.model_instance_id
        )
        assert before_cleanup.alive
        assert before_cleanup.presence == "battlefield"
        history = context.model_destruction_states
        validate_secondary_model_destruction_boundary_history(
            state=state, record=record, history=history
        )
        with pytest.raises(GameLifecycleError, match="duplicates an occurrence"):
            validate_secondary_model_destruction_boundary_history(
                state=state, record=record, history=(*history, history[0])
            )
        with pytest.raises(GameLifecycleError, match="drifted from shared history"):
            validate_secondary_model_destruction_boundary_history(
                state=state,
                record=record,
                history=(
                    replace(
                        history[0],
                        departure=replace(history[0].departure, source_id="other-source"),
                    ),
                ),
            )
        with pytest.raises(GameLifecycleError, match="lacks earlier occurrences"):
            validate_secondary_model_destruction_boundary_history(
                state=state,
                record=replace(record, battle_round=record.battle_round + 1),
                history=(),
            )
        with pytest.raises(GameLifecycleError, match="requires destroyed models"):
            SecondaryModelDestructionState(
                departure=replace(history[0].departure, removal_kind=BattlefieldRemovalKind.EMBARK),
                destroyed_models=history[0].destroyed_models,
            )
    assert not next(
        model
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
        if model.model_instance_id == isolated.model_instance_id
    ).is_alive
    assert_destruction_checkpoint(session)


def test_native_w20_casualty_uses_the_same_model_scoring_history_once() -> None:
    session = native_destruction_session()
    assert_destruction_checkpoint(session)
    finish_turn(session)
    state = session.lifecycle.state
    assert state is not None
    assert len(state.primary_unit_destruction_states) == 1
    bring = tuple(
        row
        for row in state.victory_point_ledger_for_player("player-a").transactions
        if "bring" in row.source_id
    )
    assert len(bring) == 1
    assert bring[0].amount == 4
    assert_destruction_checkpoint(session)
