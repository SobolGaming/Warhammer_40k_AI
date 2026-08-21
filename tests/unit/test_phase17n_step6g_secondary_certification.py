from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
from tests.phase11c_command_phase_helpers import (
    army_muster_request,
    complete_setup_through_gate,
    default_unit_selection,
    mustered_armies,
    phase11c_config,
    unit_selection,
)
from tests.phase17n_primary_mission_helpers import phase17n_state_with_setup
from tests.phase17n_secondary_certification_fixtures import (
    TURN_CAP_TACTICAL_IDS,
    certification_unit_selections,
    seed_sequential_tactical_turn_cap_conditions,
)
from tests.phase17n_secondary_mission_helpers import resolved_secondary_mission_selection_for_card
from tests.phase17n_step6g_secondary_certification_helpers import (
    STEP6G_LAYOUT_ROW as _LAYOUT_ROW,
)
from tests.phase17n_step6g_secondary_certification_helpers import (
    STEP6G_LIFECYCLE_CERTIFICATION_ROWS as _LIFECYCLE_CERTIFICATION_ROWS,
)
from tests.phase17n_step6g_secondary_certification_helpers import (
    STEP6G_MISSION_PARTITIONS,
    step6g_matrix_case_keys,
)
from tests.phase17n_step6g_secondary_certification_helpers import (
    STEP6G_SCORING_PLAYER_IDS as _SCORING_PLAYER_IDS,
)
from tests.phase17n_step6g_secondary_certification_helpers import (
    configured_step6g_lifecycle as _configured_step6g_lifecycle,
)
from tests.phase17n_step6g_secondary_certification_helpers import (
    lifecycle_row as _lifecycle_row,
)
from tests.phase17n_step6g_secondary_certification_helpers import (
    score_certified_row_from_state as _score_certified_row_from_state,
)
from tests.phase17n_step6g_secondary_certification_helpers import (
    secondary_transactions as _secondary_transactions,
)
from tests.phase17n_step6g_secondary_certification_helpers import (
    seed_completed_fight_phase as _seed_completed_fight_phase,
)
from tests.phase17n_step6g_secondary_certification_helpers import (
    setup_for_layout as _setup_for_layout,
)
from tests.secondary_destruction_helpers import record_secondary_destruction_for_fixture
from tests.secondary_when_drawn_rules_unit_helpers import (
    RulesUnitPresence,
    attached_when_drawn_state,
    record_unresolved_when_drawn_card,
)
from tests.setup_completion_helpers import (
    record_existing_primary_turn_start_evidence_events_for_fixture,
    record_primary_turn_start_evidence_for_fixture,
)

from warhammer40k_core.adapters.contracts import FiniteOptionSubmission
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition, ObjectiveMarkerRole
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attached_unit_reconciliation import (
    split_attached_rules_unit_if_required,
)
from warhammer40k_core.engine.battlefield_state import ModelPlacement
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.mission_decisions import (
    request_tactical_secondary_discard,
    request_tactical_secondary_score,
)
from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_destruction_evidence import (
    PrimaryUnattributedDestructionCause,
)
from warhammer40k_core.engine.primary_historical_events import (
    record_new_primary_battlefield_departure_events,
    record_new_primary_unit_destruction_events,
)
from warhammer40k_core.engine.reserve_arrival_requirements import (
    reposition_destruction_policy,
)
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
)
from warhammer40k_core.engine.secondary_mission_choices import (
    SELECT_BEACON_UNIT_DECISION_TYPE,
    SELECT_BURDEN_OF_TRUST_GUARD_DECISION_TYPE,
    SELECT_TEMPTING_TARGET_OBJECTIVE_DECISION_TYPE,
    next_secondary_mission_choice_request,
)
from warhammer40k_core.engine.secondary_mission_selection import SecondaryMissionSelection
from warhammer40k_core.engine.secondary_scoring_boundary import (
    score_turn_end_mission_scoring_boundary,
)
from warhammer40k_core.engine.secondary_scoring_context import (
    secondary_mission_selection_for_card,
)
from warhammer40k_core.engine.secondary_scoring_inventory import (
    SECONDARY_CARD_MODE_CERTIFICATION_COUNT,
    SECONDARY_LIFECYCLE_CERTIFICATION_COUNT,
    SECONDARY_MISSION_COUNT,
    secondary_mission_inventory_rows,
)
from warhammer40k_core.engine.secondary_when_drawn import (
    apply_tactical_secondary_when_drawn,
    next_tactical_secondary_when_drawn_request,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose


def test_phase17n_step6g_inventory_covers_every_secondary_card_and_mode() -> None:
    rows = secondary_mission_inventory_rows()
    assert len(rows) == SECONDARY_MISSION_COUNT
    assert sum(len(row.modes) for row in rows) == SECONDARY_CARD_MODE_CERTIFICATION_COUNT
    assert all(row.state_backed for row in rows)
    assert {row.secondary_mission_id for row in rows} == {
        "a-grievous-blow",
        "a-tempting-target",
        "assassination",
        "beacon",
        "behind-enemy-lines",
        "bring-it-down",
        "burden-of-trust",
        "centre-ground",
        "cleanse",
        "defend-stronghold",
        "display-of-might",
        "engage-on-all-fronts",
        "forward-position",
        "no-prisoners",
        "outflank",
        "overwhelming-force",
        "plunder",
        "secure-no-mans-land",
    }
    assert len(_LIFECYCLE_CERTIFICATION_ROWS) == SECONDARY_LIFECYCLE_CERTIFICATION_COUNT
    assert {row.layout_id for row in _LIFECYCLE_CERTIFICATION_ROWS} == {_LAYOUT_ROW.layout_id}
    assert {row.scoring_player_id for row in _LIFECYCLE_CERTIFICATION_ROWS} == set(
        _SCORING_PLAYER_IDS
    )
    for partition_index, partition in enumerate(STEP6G_MISSION_PARTITIONS):
        assert all(
            partition.isdisjoint(other_partition)
            for other_partition in STEP6G_MISSION_PARTITIONS[partition_index + 1 :]
        )
    assert frozenset().union(*STEP6G_MISSION_PARTITIONS) == {
        row.secondary_mission_id for row in rows
    }
    partition_case_keys = tuple(
        step6g_matrix_case_keys(partition) for partition in STEP6G_MISSION_PARTITIONS
    )
    for partition_index, partition_keys in enumerate(partition_case_keys):
        assert all(
            partition_keys.isdisjoint(other_partition_keys)
            for other_partition_keys in partition_case_keys[partition_index + 1 :]
        )
    expected_case_keys = {
        (row.secondary_mission_id, row.mode, row.scoring_player_id, outcome)
        for row in _LIFECYCLE_CERTIFICATION_ROWS
        for outcome in (("score", "retain") if row.mode == "tactical" else ("score",))
    }
    assert frozenset().union(*partition_case_keys) == expected_case_keys
    assert len(expected_case_keys) == 80


@pytest.mark.parametrize(
    ("secondary_mission_id", "decision_type", "event_type"),
    [
        (
            "a-tempting-target",
            SELECT_TEMPTING_TARGET_OBJECTIVE_DECISION_TYPE,
            "tempting_target_objective_selected",
        ),
        ("beacon", SELECT_BEACON_UNIT_DECISION_TYPE, "beacon_unit_selected"),
        (
            "burden-of-trust",
            SELECT_BURDEN_OF_TRUST_GUARD_DECISION_TYPE,
            "burden_of_trust_guard_selected",
        ),
    ],
)
def test_phase17n_step6g_secondary_selection_uses_adapter_decision_path(
    secondary_mission_id: str,
    decision_type: str,
    event_type: str,
) -> None:
    state = phase17n_state_with_setup(
        setup=_setup_for_layout(),
        active_player_id="player-a",
        phase=BattlePhase.COMMAND,
        battle_round=2,
        player_a_units=certification_unit_selections(player_id="player-a"),
        player_b_units=certification_unit_selections(player_id="player-b"),
    )
    state.secondary_mission_choices = [
        choice for choice in state.secondary_mission_choices if choice.player_id != "player-a"
    ]
    state.secondary_mission_card_states = [
        card for card in state.secondary_mission_card_states if card.player_id != "player-a"
    ]
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(player_id="player-a", mode=SecondaryMissionMode.TACTICAL)
    )
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            battle_round=state.battle_round,
            source_result_id=f"phase17n-choice-{secondary_mission_id}",
        )
    )
    lifecycle = _configured_step6g_lifecycle(
        state=state,
        decisions=DecisionController(),
    )
    lifecycle_state = lifecycle.state
    assert lifecycle_state is not None

    waiting = next_secondary_mission_choice_request(
        state=lifecycle_state,
        decisions=lifecycle.decision_controller,
    )

    assert waiting is not None
    assert waiting.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = lifecycle.pending_decision_request()
    assert request is not None
    assert request.decision_type == decision_type
    assert request.actor_id == (
        "player-b"
        if decision_type == SELECT_TEMPTING_TARGET_OBJECTIVE_DECISION_TYPE
        else "player-a"
    )
    option = (
        next(candidate for candidate in request.options if candidate.option_id.startswith("guard:"))
        if decision_type == SELECT_BURDEN_OF_TRUST_GUARD_DECISION_TYPE
        else request.options[0]
    )
    status = LocalGameSession(lifecycle=lifecycle).submit_option(
        request_id=request.request_id,
        option_id=option.option_id,
        result_id=f"phase17n-choice-result-{secondary_mission_id}",
    )

    assert status.status_kind is not LifecycleStatusKind.INVALID
    updated = lifecycle_state.secondary_mission_card_state(
        player_id="player-a",
        secondary_mission_id=secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    assert updated is not None
    selection = secondary_mission_selection_for_card(updated)
    assert selection is not None
    if secondary_mission_id == "a-tempting-target":
        assert selection.tempting_objective_id == option.option_id.removeprefix("tempting:")
    elif secondary_mission_id == "beacon":
        assert selection.beacon_unit_instance_id == option.option_id.removeprefix("beacon:")
    else:
        objective_id, unit_id = option.option_id.removeprefix("guard:").split(":", maxsplit=1)
        assert selection.resolved_guard_objective_ids == (objective_id,)
        assert selection.guarded_objective_unit_ids == ((objective_id, unit_id),)
    assert any(
        event.event_type == event_type for event in lifecycle.decision_controller.event_log.records
    )
    restored = GameLifecycle.from_payload(deepcopy(lifecycle.to_payload()))
    assert restored.to_payload() == lifecycle.to_payload()


def test_zero_secondary_turn_capacity_cannot_score_or_discard_an_achieved_tactical() -> None:
    state = _turn_cap_state()
    decisions = _decisions_for_seeded_secondary_state(state)
    for secondary_mission_id in TURN_CAP_TACTICAL_IDS[:3]:
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=decisions.event_log,
        )
        transactions = _secondary_transactions(
            state,
            player_id="player-a",
            source_id=secondary_mission_id,
        )
        assert len(transactions) == 1
        assert transactions[0].amount == 5
    capped_secondary_id = TURN_CAP_TACTICAL_IDS[-1]
    current_records = tuple(
        record
        for record in state.objective_control_records
        if record.battle_round == state.battle_round
        and record.active_player_id == state.active_player_id
        and record.phase == BattlePhase.FIGHT.value
        and record.timing is ObjectiveControlTiming.TURN_END
    )
    assert len(current_records) == 1
    ordinary_discard_state_payload = deepcopy(state.to_payload())
    ordinary_discard_decisions_payload = deepcopy(decisions.to_payload())
    score_turn_end_mission_scoring_boundary(
        state=state,
        record=current_records[0],
        end_of_battle=False,
        event_log=decisions.event_log,
    )
    achievement = next(
        context
        for context in state.tactical_secondary_achievement_contexts
        if context.player_id == "player-a" and context.secondary_mission_id == capped_secondary_id
    )
    ledger_before = state.victory_point_ledger_for_player("player-a")

    with pytest.raises(GameLifecycleError, match="must award at least 1 VP"):
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id=capped_secondary_id,
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=decisions.event_log,
        )

    assert state.victory_point_ledger_for_player("player-a") == ledger_before
    assert (
        _secondary_transactions(
            state,
            player_id="player-a",
            source_id=capped_secondary_id,
        )
        == ()
    )
    active = state.secondary_mission_card_state(
        player_id="player-a",
        secondary_mission_id=capped_secondary_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    assert active is not None
    assert active.status is SecondaryMissionCardStatus.ACTIVE
    assert state.tactical_secondary_achievement_context(achievement.achievement_id) == achievement

    waiting = request_tactical_secondary_score(
        state=state,
        decisions=decisions,
        achievement_context=achievement,
    )
    assert waiting.decision_request is not None
    score_session = LocalGameSession(
        lifecycle=_configured_step6g_lifecycle(state=state, decisions=decisions)
    )
    score_state = score_session.lifecycle.state
    assert score_state is not None
    request = score_session.lifecycle.pending_decision_request()
    assert request is not None
    assert [option.option_id for option in request.options] == [f"retain:{capped_secondary_id}"]
    with pytest.raises(DecisionError, match="finite action space"):
        score_session.submit_option(
            request_id=request.request_id,
            option_id=f"score:{capped_secondary_id}",
            result_id="phase17n-zero-cap-illegal-score",
        )
    assert score_session.lifecycle.pending_decision_request() == request
    assert (
        score_state.tactical_secondary_achievement_context(achievement.achievement_id)
        == achievement
    )
    assert (
        score_state.secondary_mission_card_state(
            player_id="player-a",
            secondary_mission_id=capped_secondary_id,
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        == active
    )
    assert [option.option_id for option in request.options] == [f"retain:{capped_secondary_id}"]
    assert (
        _secondary_transactions(
            score_state,
            player_id="player-a",
            source_id=capped_secondary_id,
        )
        == ()
    )
    GameLifecycle.from_payload(deepcopy(score_session.lifecycle.to_payload()))

    discard_state = GameState.from_payload(ordinary_discard_state_payload)
    discard_card_battle_round = discard_state.battle_round
    discard_decisions = DecisionController.from_payload(ordinary_discard_decisions_payload)
    discard_waiting = request_tactical_secondary_discard(
        state=discard_state,
        decisions=discard_decisions,
        player_id="player-a",
    )
    assert discard_waiting.decision_request is not None
    discard_session = LocalGameSession(
        lifecycle=_configured_step6g_lifecycle(
            state=discard_state,
            decisions=discard_decisions,
        )
    )
    discard_request = discard_session.lifecycle.pending_decision_request()
    assert discard_request is not None
    discard_option = next(
        option.option_id
        for option in discard_request.options
        if option.option_id == f"discard:{capped_secondary_id}"
    )
    discard_session.submit_option(
        request_id=discard_request.request_id,
        option_id=discard_option,
        result_id="phase17n-zero-cap-ordinary-discard",
    )
    discarded_state = discard_session.lifecycle.state
    assert discarded_state is not None
    discarded = next(
        card
        for card in discarded_state.secondary_mission_card_states
        if card.player_id == "player-a"
        and card.secondary_mission_id == capped_secondary_id
        and card.battle_round == discard_card_battle_round
    )
    assert discarded.status is SecondaryMissionCardStatus.DISCARDED
    assert (
        _secondary_transactions(
            discarded_state,
            player_id="player-a",
            source_id=capped_secondary_id,
        )
        == ()
    )
    assert not any(
        event.event_type == "tactical_secondary_mission_scored"
        for event in discard_session.lifecycle.decision_controller.event_log.records
    )
    GameLifecycle.from_payload(deepcopy(discard_session.lifecycle.to_payload()))


def test_tactical_score_rejects_stale_result_after_other_cards_exhaust_turn_cap() -> None:
    state = _turn_cap_state()
    decisions = _decisions_for_seeded_secondary_state(state)
    record = state.prepare_current_turn_end_boundary(
        completed_phase=BattlePhase.FIGHT,
        runtime_modifier_registry=None,
    )
    decisions.event_log.append(
        "end_boundary_objective_control_determined",
        {
            "game_id": record.game_id,
            "battle_round": record.battle_round,
            "phase": record.phase,
            "record_ids": [record.record_id],
            "source_rule_id": (
                "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first"
            ),
        },
    )
    score_turn_end_mission_scoring_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )
    target_secondary_id = TURN_CAP_TACTICAL_IDS[-1]
    target_achievement = next(
        context
        for context in state.tactical_secondary_achievement_contexts
        if context.player_id == "player-a" and context.secondary_mission_id == target_secondary_id
    )
    waiting = request_tactical_secondary_score(
        state=state,
        decisions=decisions,
        achievement_context=target_achievement,
    )
    request = waiting.decision_request
    assert request is not None
    assert {option.option_id for option in request.options} == {
        f"score:{target_secondary_id}",
        f"retain:{target_secondary_id}",
    }
    stale_score_result = FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=f"score:{target_secondary_id}",
        result_id="phase17n-stale-tactical-score-after-turn-cap",
    ).to_result(request)

    for secondary_mission_id in TURN_CAP_TACTICAL_IDS[:3]:
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=decisions.event_log,
        )
    assert (
        sum(
            transaction.amount
            for secondary_mission_id in TURN_CAP_TACTICAL_IDS[:3]
            for transaction in _secondary_transactions(
                state,
                player_id="player-a",
                source_id=secondary_mission_id,
            )
        )
        == 15
    )
    lifecycle = _configured_step6g_lifecycle(state=state, decisions=decisions)
    lifecycle_state = lifecycle.state
    assert lifecycle_state is not None
    pending_before = lifecycle.pending_decision_request()
    assert pending_before == request
    ledger_before = lifecycle_state.victory_point_ledger_for_player("player-a")
    records_before = lifecycle.decision_controller.records
    active_before = lifecycle_state.secondary_mission_card_state(
        player_id="player-a",
        secondary_mission_id=target_secondary_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    assert active_before is not None
    achievement_before = lifecycle_state.tactical_secondary_achievement_context(
        target_achievement.achievement_id
    )
    assert achievement_before is not None

    status = lifecycle.submit_decision(stale_score_result)

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    assert status.payload["invalid_reason"] == "victory_point_capacity_exhausted"
    assert lifecycle.pending_decision_request() == pending_before
    assert lifecycle.decision_controller.records == records_before
    assert lifecycle_state.victory_point_ledger_for_player("player-a") == ledger_before
    assert (
        _secondary_transactions(
            lifecycle_state,
            player_id="player-a",
            source_id=target_secondary_id,
        )
        == ()
    )
    assert (
        lifecycle_state.secondary_mission_card_state(
            player_id="player-a",
            secondary_mission_id=target_secondary_id,
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        == active_before
    )
    assert (
        lifecycle_state.tactical_secondary_achievement_context(target_achievement.achievement_id)
        == achievement_before
    )


def test_delayed_tactical_score_reuses_boundary_evidence_after_selection_resolution() -> None:
    state = _turn_cap_state()
    decisions = _decisions_for_seeded_secondary_state(state)
    record = state.prepare_current_turn_end_boundary(
        completed_phase=BattlePhase.FIGHT,
        runtime_modifier_registry=None,
    )
    decisions.event_log.append(
        "end_boundary_objective_control_determined",
        {
            "game_id": record.game_id,
            "battle_round": record.battle_round,
            "phase": record.phase,
            "record_ids": [record.record_id],
            "source_rule_id": (
                "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first"
            ),
        },
    )

    score_turn_end_mission_scoring_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )

    target_secondary_id = TURN_CAP_TACTICAL_IDS[-1]
    achievement = next(
        context
        for context in state.tactical_secondary_achievement_contexts
        if context.player_id == "player-a" and context.secondary_mission_id == target_secondary_id
    )
    active_card = state.secondary_mission_card_state(
        player_id="player-a",
        secondary_mission_id=target_secondary_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    assert active_card is not None
    resolved_selection = secondary_mission_selection_for_card(active_card)
    assert resolved_selection is not None
    assert record.record_id in resolved_selection.resolved_objective_control_record_ids
    evidence_before = tuple(
        evidence
        for evidence in state.secondary_scoring_state_evidence_records
        if evidence.scoring_player_id == "player-a"
        and evidence.secondary_mission_id == target_secondary_id
        and evidence.objective_control_record_id == record.record_id
    )
    assert len(evidence_before) == 1
    assert evidence_before[0].selection_payload != active_card.selection_payload

    waiting = request_tactical_secondary_score(
        state=state,
        decisions=decisions,
        achievement_context=achievement,
    )
    request = waiting.decision_request
    assert request is not None
    session = LocalGameSession(
        lifecycle=_configured_step6g_lifecycle(state=state, decisions=decisions)
    )

    status = session.submit_option(
        request_id=request.request_id,
        option_id=f"score:{target_secondary_id}",
        result_id="phase17n-delayed-tactical-score-reuses-boundary-evidence",
    )

    assert status.status_kind is not LifecycleStatusKind.INVALID
    scored_state = session.lifecycle.state
    assert scored_state is not None
    evidence_after = tuple(
        evidence
        for evidence in scored_state.secondary_scoring_state_evidence_records
        if evidence.scoring_player_id == "player-a"
        and evidence.secondary_mission_id == target_secondary_id
        and evidence.objective_control_record_id == record.record_id
    )
    assert evidence_after == evidence_before
    transactions = _secondary_transactions(
        scored_state,
        player_id="player-a",
        source_id=target_secondary_id,
    )
    assert len(transactions) == 1
    metadata = transactions[0].metadata
    assert isinstance(metadata, dict)
    assert metadata["secondary_scoring_state_evidence_id"] == evidence_before[0].evidence_id
    assert metadata["secondary_scoring_state_evidence_hash"] == evidence_before[0].evidence_hash


def test_positive_partial_tactical_award_scores_and_discards_the_card() -> None:
    state = _turn_cap_state()
    decisions = _decisions_for_seeded_secondary_state(state)
    for secondary_mission_id, expected_amount in (
        ("a-tempting-target", 5),
        ("centre-ground", 5),
        ("behind-enemy-lines", 3),
    ):
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=decisions.event_log,
        )
        assert (
            _secondary_transactions(
                state,
                player_id="player-a",
                source_id=secondary_mission_id,
            )[0].amount
            == expected_amount
        )

    scored = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="plunder",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=decisions.event_log,
    )
    transaction = _secondary_transactions(
        state,
        player_id="player-a",
        source_id="plunder",
    )[0]
    assert scored.status is SecondaryMissionCardStatus.SCORED
    assert transaction.amount == 2
    assert isinstance(transaction.metadata, dict)
    audit = transaction.metadata["vp_cap_audit"]
    assert isinstance(audit, dict)
    assert audit["requested_amount"] == 5
    assert audit["applied_amount"] == 2
    assert audit["secondary_turn_points_before"] == 13
    assert audit["secondary_turn_points_after"] == 15
    assert audit["secondary_turn_remaining_capacity"] == 0
    GameState.from_payload(state.to_payload())


def test_spatial_secondary_restore_survives_later_qualifying_unit_mutation() -> None:
    row = _lifecycle_row("engage-on-all-fronts", mode="tactical", scoring_player_id="player-a")
    state, _event_log, expectation = _score_certified_row_from_state(row)
    qualifying_unit = _first_intercessor(state, player_id="player-a")
    _zero_and_remove_unit(state, qualifying_unit.unit_instance_id)
    restored = GameState.from_payload(state.to_payload())
    transactions = _secondary_transactions(
        restored,
        player_id="player-a",
        source_id="engage-on-all-fronts",
    )
    assert len(transactions) == 1
    assert transactions[0].amount == expectation.expected_amount


def test_unattributed_and_self_destruction_score_bring_it_down() -> None:
    unattributed_state = _tactical_fight_state()
    unattributed_state.battle_round = 3
    unattributed_state.active_player_id = "player-b"
    _seed_completed_fight_phase(unattributed_state)
    _seed_single_tactical_card(unattributed_state, "bring-it-down")
    reserve_vehicle = _unit_for(
        unattributed_state,
        player_id="player-b",
        datasheet_id="core-vehicle-monster",
    )
    battlefield = unattributed_state.battlefield_state
    mission_setup = unattributed_state.mission_setup
    assert battlefield is not None
    assert mission_setup is not None
    unattributed_state.replace_battlefield_state(
        battlefield.without_unit_placement(reserve_vehicle.unit_instance_id)
    )
    declared_reserve = ReserveState.declared_before_battle(
        player_id="player-b",
        unit_instance_id=reserve_vehicle.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        destruction_deadline_policy=reposition_destruction_policy(
            mission_setup=mission_setup,
            destruction_deadline_policy=None,
        ),
    )
    unattributed_state.record_reserve_state(declared_reserve)
    unattributed_decisions = DecisionController()
    unattributed_decisions.event_log.append(
        "reserve_unit_declared",
        {
            "game_id": unattributed_state.game_id,
            "player_id": declared_reserve.player_id,
            "unit_instance_id": declared_reserve.unit_instance_id,
            "reserve_state": declared_reserve.to_payload(),
        },
    )
    record_primary_turn_start_evidence_for_fixture(
        unattributed_state,
        decisions=unattributed_decisions,
    )
    destruction_ids_before = tuple(
        destruction.destruction_id
        for destruction in unattributed_state.primary_unit_destruction_states
    )
    unattributed_state._resolve_unarrived_reserve_destruction_boundary(  # pyright: ignore[reportPrivateUsage]
        end_of_battle=False
    )
    record_new_primary_unit_destruction_events(
        state=unattributed_state,
        event_log=unattributed_decisions.event_log,
        destruction_ids_before=destruction_ids_before,
    )
    (unattributed_destruction,) = tuple(
        destruction
        for destruction in unattributed_state.secondary_unit_destruction_states
        if destruction.destroyed_unit_instance_id == reserve_vehicle.unit_instance_id
    )
    assert unattributed_destruction.destroying_player_id is None
    primary_destruction = next(
        destruction
        for destruction in unattributed_state.primary_unit_destruction_states
        if destruction.destruction_id == unattributed_destruction.source_primary_destruction_id
    )
    assert (
        primary_destruction.unattributed_cause
        is PrimaryUnattributedDestructionCause.RESERVE_DEADLINE
    )
    unattributed_state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=unattributed_decisions.event_log,
    )
    unattributed_transactions = _secondary_transactions(
        unattributed_state,
        player_id="player-a",
        source_id="bring-it-down",
    )
    assert unattributed_transactions[0].amount == 5
    restored_unattributed_lifecycle = _configured_step6g_lifecycle(
        state=unattributed_state,
        decisions=unattributed_decisions,
    )
    restored_unattributed_state = restored_unattributed_lifecycle.state
    assert restored_unattributed_state is not None
    assert restored_unattributed_state.to_payload() == unattributed_state.to_payload()
    assert (
        GameLifecycle.from_payload(
            deepcopy(restored_unattributed_lifecycle.to_payload())
        ).to_payload()
        == restored_unattributed_lifecycle.to_payload()
    )

    self_kill_state = _tactical_fight_state()
    _seed_single_tactical_card(self_kill_state, "bring-it-down")
    vehicle = _unit_for(
        self_kill_state,
        player_id="player-b",
        datasheet_id="core-vehicle-monster",
    )
    decisions = record_primary_turn_start_evidence_for_fixture(self_kill_state)
    record_secondary_destruction_for_fixture(
        self_kill_state,
        destroying_player_id="player-b",
        destroyed_unit_instance_id=vehicle.unit_instance_id,
        source_id="phase17n-self-kill-bring-it-down",
        event_log=decisions.event_log,
    )
    self_kill_state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=decisions.event_log,
    )
    assert (
        _secondary_transactions(
            self_kill_state,
            player_id="player-a",
            source_id="bring-it-down",
        )[0].amount
        == 5
    )


def test_assassination_all_destroyed_survives_character_return_to_life() -> None:
    row = _lifecycle_row("assassination", mode="tactical", scoring_player_id="player-a")
    state, _event_log, expectation = _score_certified_row_from_state(row)
    character = _unit_for(
        state,
        player_id="player-b",
        datasheet_id="core-character-leader",
    )
    _restore_unit_wounds(state, character.unit_instance_id)
    restored = GameState.from_payload(state.to_payload())
    transactions = _secondary_transactions(
        restored,
        player_id="player-a",
        source_id="assassination",
    )
    assert transactions[0].amount == expectation.expected_amount
    metadata = transactions[0].metadata
    if type(metadata) is not dict:
        raise AssertionError("Assassination transaction metadata must be an object.")
    assert metadata["scoring_rule_ids"] == ["assassination-tactical-all-characters-destroyed"]


def test_cleanse_when_drawn_shuffle_is_optional_while_plunder_is_active() -> None:
    state = _command_tactical_state(battle_round=2)
    _record_unresolved_tactical(state, "plunder")
    _record_unresolved_tactical(state, "cleanse")
    decisions = DecisionController()
    status = next_tactical_secondary_when_drawn_request(state=state, decisions=decisions)
    assert status is not None
    request = status.decision_request
    assert request is not None
    request_payload = request.payload
    assert isinstance(request_payload, dict)
    assert request_payload["secondary_mission_id"] == "cleanse"
    assert [option.option_id for option in request.options] == [
        "keep:cleanse",
        "shuffle:cleanse",
    ]
    apply_tactical_secondary_when_drawn(
        state=state,
        result=DecisionResult.for_request(
            result_id="phase17n-when-drawn-shuffle-cleanse",
            request=request,
            selected_option_id="shuffle:cleanse",
        ),
        decisions=decisions,
    )
    assert (
        state.secondary_mission_card_state(
            player_id="player-a",
            secondary_mission_id="cleanse",
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        is None
    )
    plunder = state.secondary_mission_card_state(
        player_id="player-a",
        secondary_mission_id="plunder",
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    assert plunder is not None
    assert plunder.status is SecondaryMissionCardStatus.ACTIVE


def test_plunder_when_drawn_shuffle_is_optional_while_cleanse_is_active() -> None:
    state = _command_tactical_state(battle_round=2)
    _record_unresolved_tactical(state, "cleanse")
    _record_unresolved_tactical(state, "plunder")
    decisions = DecisionController()
    first = next_tactical_secondary_when_drawn_request(state=state, decisions=decisions)
    assert first is not None
    assert first.decision_request is not None
    apply_tactical_secondary_when_drawn(
        state=state,
        result=DecisionResult.for_request(
            result_id="phase17n-when-drawn-keep-cleanse",
            request=first.decision_request,
            selected_option_id="keep:cleanse",
        ),
        decisions=decisions,
    )
    second = next_tactical_secondary_when_drawn_request(state=state, decisions=decisions)
    assert second is not None
    assert second.decision_request is not None
    second_payload = second.decision_request.payload
    assert isinstance(second_payload, dict)
    assert second_payload["secondary_mission_id"] == "plunder"
    assert [option.option_id for option in second.decision_request.options] == [
        "keep:plunder",
        "shuffle:plunder",
    ]
    apply_tactical_secondary_when_drawn(
        state=state,
        result=DecisionResult.for_request(
            result_id="phase17n-when-drawn-keep-plunder",
            request=second.decision_request,
            selected_option_id="keep:plunder",
        ),
        decisions=decisions,
    )
    assert next_tactical_secondary_when_drawn_request(state=state, decisions=decisions) is None
    for secondary_mission_id in ("cleanse", "plunder"):
        card = state.secondary_mission_card_state(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        assert card is not None
        assert card.status is SecondaryMissionCardStatus.ACTIVE


def test_defend_stronghold_first_round_when_drawn_shuffles_without_keep_option() -> None:
    state = _command_tactical_state(battle_round=1)
    _record_unresolved_tactical(state, "defend-stronghold")
    decisions = DecisionController()
    status = next_tactical_secondary_when_drawn_request(state=state, decisions=decisions)
    assert (
        state.secondary_mission_card_state(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        is None
    )
    shuffled = [
        event
        for event in decisions.event_log.records
        if event.event_type == "tactical_secondary_when_drawn_shuffled"
    ]
    assert len(shuffled) == 1
    payload = shuffled[0].payload
    if type(payload) is not dict:
        raise AssertionError("Defend Stronghold When Drawn event payload must be an object.")
    assert payload["mandatory"] is True
    assert payload["secondary_mission_id"] == "defend-stronghold"
    if status is not None and status.decision_request is not None:
        status_payload = status.decision_request.payload
        assert isinstance(status_payload, dict)
        assert status_payload["secondary_mission_id"] != "defend-stronghold"
        assert all(
            not option.option_id.startswith("keep:defend-stronghold")
            for option in status.decision_request.options
        )


@pytest.mark.parametrize(
    "card_player_id",
    ["player-a", "player-b"],
    ids=("attacker-owns-card", "defender-owns-card"),
)
def test_a_grievous_blow_when_drawn_sees_enemy_attached_unit(
    card_player_id: str,
) -> None:
    state = attached_when_drawn_state(
        setup=_setup_for_layout(),
        card_player_id=card_player_id,
        bodyguard_model_count=12,
        secondary_mission_id="a-grievous-blow",
    )
    enemy_army = next(army for army in state.army_definitions if army.player_id != card_player_id)
    formation = enemy_army.attached_units[0]
    assert len(enemy_army.unit_by_id(formation.bodyguard_unit_instance_id).own_models) == 12
    assert len(enemy_army.unit_by_id(formation.leader_unit_instance_ids[0]).own_models) == 1
    assert (
        state.starting_strength_record_for_unit(
            formation.attached_unit_instance_id
        ).starting_model_count
        == 13
    )

    assert (
        next_tactical_secondary_when_drawn_request(
            state=state,
            decisions=DecisionController(),
        )
        is None
    )


def test_a_grievous_blow_when_drawn_allows_discard_below_13_models() -> None:
    state = attached_when_drawn_state(
        setup=_setup_for_layout(),
        card_player_id="player-a",
        bodyguard_model_count=11,
        secondary_mission_id="a-grievous-blow",
    )
    status = next_tactical_secondary_when_drawn_request(
        state=state,
        decisions=DecisionController(),
    )
    assert status is not None
    assert status.decision_request is not None
    assert {option.option_id for option in status.decision_request.options} == {
        "keep:a-grievous-blow",
        "discard:a-grievous-blow",
    }


@pytest.mark.parametrize("presence", ["reserves", "embarked"])
def test_a_grievous_blow_when_drawn_excludes_off_battlefield_attached_units(
    presence: RulesUnitPresence,
) -> None:
    state = attached_when_drawn_state(
        setup=_setup_for_layout(),
        card_player_id="player-a",
        bodyguard_model_count=12,
        secondary_mission_id="a-grievous-blow",
        presence=presence,
    )
    status = next_tactical_secondary_when_drawn_request(
        state=state,
        decisions=DecisionController(),
    )
    assert status is not None
    assert status.decision_request is not None
    assert "discard:a-grievous-blow" in {
        option.option_id for option in status.decision_request.options
    }


@pytest.mark.parametrize(
    ("bodyguard_model_count", "discard_available"),
    [(12, True), (13, False)],
)
def test_a_grievous_blow_when_drawn_uses_post_split_descendant_starting_strength(
    bodyguard_model_count: int,
    discard_available: bool,
) -> None:
    state = attached_when_drawn_state(
        setup=_setup_for_layout(),
        card_player_id="player-a",
        bodyguard_model_count=bodyguard_model_count,
        secondary_mission_id="a-grievous-blow",
        record_card=False,
    )
    formation = state.army_definitions[1].attached_units[0]
    leader_id = formation.leader_unit_instance_ids[0]
    _zero_and_remove_unit(state, leader_id)
    assert split_attached_rules_unit_if_required(
        state=state,
        event_log=EventLog(),
        rules_unit_instance_id=formation.attached_unit_instance_id,
    ) == (formation.bodyguard_unit_instance_id,)
    assert (
        state.starting_strength_record_for_unit(
            formation.bodyguard_unit_instance_id
        ).starting_model_count
        == bodyguard_model_count
    )
    record_unresolved_when_drawn_card(
        state,
        player_id="player-a",
        secondary_mission_id="a-grievous-blow",
    )

    status = next_tactical_secondary_when_drawn_request(
        state=state,
        decisions=DecisionController(),
    )
    if discard_available:
        assert status is not None
        assert status.decision_request is not None
        assert "discard:a-grievous-blow" in {
            option.option_id for option in status.decision_request.options
        }
    else:
        assert status is None


def test_bring_it_down_when_drawn_sees_w10_model_inside_attached_unit() -> None:
    state = attached_when_drawn_state(
        setup=_setup_for_layout(),
        card_player_id="player-a",
        bodyguard_model_count=5,
        secondary_mission_id="bring-it-down",
        leader_starting_wounds=10,
    )
    enemy_army = state.army_definitions[1]
    formation = enemy_army.attached_units[0]
    leader = enemy_army.unit_by_id(formation.leader_unit_instance_ids[0])
    assert leader.own_models[0].starting_wounds == 10
    assert (
        next_tactical_secondary_when_drawn_request(
            state=state,
            decisions=DecisionController(),
        )
        is None
    )


def test_burden_of_trust_still_scores_after_attached_unit_split() -> None:
    state = _attached_burden_state()
    formation = state.army_definitions[0].attached_units[0]
    attached_id = formation.attached_unit_instance_id
    bodyguard_id = formation.bodyguard_unit_instance_id
    leader_id = formation.leader_unit_instance_ids[0]
    home = _home_objective(state, player_id="player-a")
    _place_unit(state, bodyguard_id, home.x_inches, home.y_inches)
    _place_unit(state, leader_id, home.x_inches, home.y_inches)
    card = SecondaryMissionCardState.active_tactical(
        player_id="player-a",
        secondary_mission_id="burden-of-trust",
        battle_round=state.battle_round,
        source_result_id="phase17n-burden-split",
    )
    assert state.mission_setup is not None
    state.record_secondary_mission_card_state(
        card.with_selection(
            SecondaryMissionSelection().with_guards(
                guarded_objective_unit_ids=((home.objective_marker_id, attached_id),),
                resolved_guard_objective_ids=tuple(
                    marker.objective_marker_id for marker in state.mission_setup.objective_markers
                ),
                battle_round=state.battle_round,
            )
        )
    )
    bodyguard = _unit_by_id(state, bodyguard_id)
    _zero_and_remove_unit(state, bodyguard.unit_instance_id)
    surviving = split_attached_rules_unit_if_required(
        state=state,
        event_log=EventLog(),
        rules_unit_instance_id=attached_id,
    )
    assert leader_id in surviving
    _place_unit(state, leader_id, home.x_inches, home.y_inches)
    decisions = record_primary_turn_start_evidence_for_fixture(state)
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="burden-of-trust",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=decisions.event_log,
    )
    transactions = _secondary_transactions(
        state,
        player_id="player-a",
        source_id="burden-of-trust",
    )
    assert len(transactions) == 1
    assert transactions[0].amount == 2


def _turn_cap_state() -> GameState:
    state = _tactical_fight_state()
    state.secondary_mission_card_states = [
        card for card in state.secondary_mission_card_states if card.player_id != "player-a"
    ]
    for secondary_mission_id in TURN_CAP_TACTICAL_IDS:
        card = SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            battle_round=state.battle_round,
            source_result_id=f"phase17n-turn-cap-{secondary_mission_id}",
        )
        state.record_secondary_mission_card_state(
            card.with_selection(resolved_secondary_mission_selection_for_card(state, card))
        )
    seed_sequential_tactical_turn_cap_conditions(state)
    return state


def _decisions_for_seeded_secondary_state(state: GameState) -> DecisionController:
    decisions = DecisionController()
    current_turn_has_snapshot = any(
        snapshot.active_player_id == state.active_player_id
        and snapshot.battle_round == state.battle_round
        for snapshot in state.primary_rules_unit_turn_start_snapshots
    )
    if current_turn_has_snapshot:
        record_existing_primary_turn_start_evidence_events_for_fixture(
            state,
            decisions=decisions,
        )
    else:
        record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    record_new_primary_battlefield_departure_events(
        state=state,
        event_log=decisions.event_log,
        departure_ids_before=(),
    )
    record_new_primary_unit_destruction_events(
        state=state,
        event_log=decisions.event_log,
        destruction_ids_before=(),
    )
    return decisions


def _tactical_fight_state() -> GameState:
    state = phase17n_state_with_setup(
        setup=_setup_for_layout(),
        active_player_id="player-a",
        phase=BattlePhase.FIGHT,
        battle_round=2,
        player_a_secondary=SecondaryMissionMode.TACTICAL,
        player_a_units=certification_unit_selections(player_id="player-a"),
        player_b_units=certification_unit_selections(player_id="player-b"),
    )
    _seed_completed_fight_phase(state)
    return state


def _command_tactical_state(*, battle_round: int) -> GameState:
    return phase17n_state_with_setup(
        setup=_setup_for_layout(),
        active_player_id="player-a",
        phase=BattlePhase.COMMAND,
        battle_round=battle_round,
        player_a_secondary=SecondaryMissionMode.TACTICAL,
        player_a_units=certification_unit_selections(player_id="player-a"),
        player_b_units=certification_unit_selections(player_id="player-b"),
    )


def _seed_single_tactical_card(state: GameState, secondary_mission_id: str) -> None:
    state.secondary_mission_card_states = [
        card for card in state.secondary_mission_card_states if card.player_id != "player-a"
    ]
    card = SecondaryMissionCardState.active_tactical(
        player_id="player-a",
        secondary_mission_id=secondary_mission_id,
        battle_round=state.battle_round,
        source_result_id=f"phase17n-review-{secondary_mission_id}",
    )
    state.record_secondary_mission_card_state(
        card.with_selection(resolved_secondary_mission_selection_for_card(state, card))
    )


def _record_unresolved_tactical(state: GameState, secondary_mission_id: str) -> None:
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            battle_round=state.battle_round,
            source_result_id=f"phase17n-when-drawn-{secondary_mission_id}",
        )
    )


def _attached_burden_state() -> GameState:
    setup = _setup_for_layout()
    catalog = phase11c_config().army_catalog
    config = replace(
        phase11c_config(),
        game_id="phase17n-burden-split",
        mission_setup=setup,
        army_muster_requests=(
            replace(
                army_muster_request(
                    catalog=catalog,
                    player_id="player-a",
                    army_id="army-alpha",
                    unit_selections=(
                        default_unit_selection("bodyguard-unit"),
                        unit_selection(
                            unit_selection_id="leader-unit",
                            datasheet_id="core-character-leader",
                            model_profile_id="core-character-leader",
                            model_count=1,
                        ),
                    ),
                    attachment_declarations=(
                        AttachmentDeclaration(
                            source_unit_selection_id="leader-unit",
                            bodyguard_unit_selection_id="bodyguard-unit",
                        ),
                    ),
                ),
                force_disposition_id=_LAYOUT_ROW.attacker_force_disposition_id,
            ),
            replace(
                army_muster_request(
                    catalog=catalog,
                    player_id="player-b",
                    army_id="army-beta",
                    unit_selections=(default_unit_selection("intercessor-unit-3"),),
                ),
                force_disposition_id=_LAYOUT_ROW.defender_force_disposition_id,
            ),
        ),
    )
    state = GameState.from_config(config)
    for army in mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17n-burden-split-battlefield",
        armies=tuple(state.army_definitions),
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=setup.terrain_features,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(player_id="player-a", mode=SecondaryMissionMode.TACTICAL)
    )
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(
            player_id="player-b",
            mode=SecondaryMissionMode.FIXED,
            fixed_mission_ids=("assassination", "bring-it-down"),
        )
    )
    complete_setup_through_gate(state=state, decisions=DecisionController(), config=config)
    assert state.battlefield_state is not None
    state.mission_setup = setup
    state.battlefield_state = replace(
        state.battlefield_state,
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=setup.terrain_features,
    )
    state.stage = GameLifecycleStage.BATTLE
    state.battle_round = 2
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    _seed_completed_fight_phase(state)
    return state


def _place_unit(state: GameState, unit_instance_id: str, x_inches: float, y_inches: float) -> None:
    if state.battlefield_state is None:
        raise AssertionError("Review fixture placement requires battlefield state.")
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    placements: list[ModelPlacement] = []
    for index, placement in enumerate(unit_placement.model_placements):
        placements.append(
            placement.with_pose(
                Pose.at(
                    x_inches + (index * 0.45),
                    y_inches,
                    placement.pose.position.z,
                    facing_degrees=placement.pose.facing.degrees,
                )
            )
        )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        unit_placement.with_model_placements(tuple(placements))
    )


def _home_objective(state: GameState, *, player_id: str) -> ObjectiveMarkerDefinition:
    if state.mission_setup is None:
        raise AssertionError("Review fixture requires MissionSetup.")
    role = (
        ObjectiveMarkerRole.ATTACKER_HOME
        if player_id == state.mission_setup.attacker_player_id
        else ObjectiveMarkerRole.DEFENDER_HOME
    )
    for marker in state.mission_setup.objective_markers:
        if marker.objective_role is role:
            return marker
    raise AssertionError("Review fixture is missing a home objective.")


def _zero_and_remove_unit(state: GameState, unit_instance_id: str) -> None:
    armies: list[ArmyDefinition] = []
    removed_ids: list[str] = []
    for army in state.army_definitions:
        units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                removed_ids.extend(model.model_instance_id for model in unit.own_models)
                unit = replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=0) for model in unit.own_models
                    ),
                )
            units.append(unit)
        armies.append(replace(army, units=tuple(units)))
    state.army_definitions = armies
    if state.battlefield_state is not None and removed_ids:
        state.replace_battlefield_state(
            state.battlefield_state.with_removed_models(tuple(removed_ids))
        )


def _restore_unit_wounds(state: GameState, unit_instance_id: str) -> None:
    armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                unit = replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=model.starting_wounds)
                        for model in unit.own_models
                    ),
                )
            units.append(unit)
        armies.append(replace(army, units=tuple(units)))
    state.army_definitions = armies


def _first_intercessor(state: GameState, *, player_id: str) -> UnitInstance:
    return _unit_for(
        state,
        player_id=player_id,
        datasheet_id="core-intercessor-like-infantry",
    )


def _unit_for(state: GameState, *, player_id: str, datasheet_id: str) -> UnitInstance:
    matches = tuple(
        unit
        for army in state.army_definitions
        if army.player_id == player_id
        for unit in army.units
        if unit.datasheet_id == datasheet_id
    )
    if not matches:
        raise AssertionError(f"Review fixture is missing {datasheet_id} for {player_id}.")
    return matches[0]


def _unit_by_id(state: GameState, unit_instance_id: str) -> UnitInstance:
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return unit
    raise AssertionError(f"Review fixture is missing unit {unit_instance_id}.")
