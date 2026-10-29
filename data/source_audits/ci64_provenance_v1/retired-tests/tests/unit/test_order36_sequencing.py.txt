from __future__ import annotations

from dataclasses import replace

import pytest

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sequencing import (
    SequencingConflictContext,
    SequencingParticipant,
    SequencingRequirement,
    apply_select_next_sequencing_participant_from_request,
    create_select_next_sequencing_participant_request,
    create_sequencing_decision_request,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)


def test_secondary_candidate_refresh_observes_battle_shock_registry_changes() -> None:
    from tests.phase17n_step6g_secondary_certification_helpers import (
        STEP6G_LIFECYCLE_CERTIFICATION_ROWS,
        secondary_certification_session,
    )

    from warhammer40k_core.engine.mission_turn_end_sequencing import mission_turn_end_record
    from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies
    from warhammer40k_core.engine.secondary_scoring_context import (
        secondary_scoring_condition_context_from_state,
    )

    row = next(
        row
        for row in STEP6G_LIFECYCLE_CERTIFICATION_ROWS
        if row.secondary_mission_id == "engage-on-all-fronts"
        and row.mode == "fixed"
        and row.scoring_player_id == "player-a"
    )
    session, _, _ = secondary_certification_session(row)
    session.advance_until_decision_or_terminal()
    state = session.lifecycle.state
    assert state is not None
    record = mission_turn_end_record(state)

    def quarters() -> tuple[str, ...]:
        context = secondary_scoring_condition_context_from_state(
            state=state, player_id="player-a", record=record, selection=None
        )
        assert context.occupancy is not None
        return context.occupancy.presence_quarter_ids

    assert state.battle_shocked_unit_ids == []
    original = quarters()
    assert len(original) >= 3
    state.battle_shocked_unit_ids = [
        view.unit_instance_id
        for view in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
        if view.owner_player_id == "player-a"
    ]
    assert quarters() == ()
    state.battle_shocked_unit_ids.clear()
    assert quarters() == original


def test_primary_scoring_commit_preserves_one_mission_owner() -> None:
    """A selected mission must never commit the other player's Primary awards."""
    from tests.phase17n_primary_mission_helpers import phase17n_state_with_setup
    from tests.phase17n_step5g_pairing_certification_helpers import setup_for_lifecycle_row

    from warhammer40k_core.engine.event_log import EventLog
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.primary_scoring_boundary import score_primary_player_boundary
    from warhammer40k_core.engine.primary_scoring_pairing_certification import (
        event_companion_pairing_lifecycle_certification_rows,
    )
    from warhammer40k_core.engine.primary_scoring_state_evidence import (
        PrimaryScoringStateEvidence,
    )

    setup = setup_for_lifecycle_row(event_companion_pairing_lifecycle_certification_rows()[0])
    state = phase17n_state_with_setup(
        setup=setup, active_player_id="player-a", phase=BattlePhase.FIGHT, battle_round=2
    )
    record = state.prepare_current_turn_end_boundary(
        completed_phase=BattlePhase.FIGHT, runtime_modifier_registry=None
    )
    events = EventLog()
    opposing_ledger = state.victory_point_ledger_for_player("player-b").to_payload()
    score_primary_player_boundary(
        state=state,
        record=record,
        scoring_player_id="player-a",
        end_of_battle=False,
        event_log=events,
    )
    (evidence,) = state.primary_scoring_state_evidence_records
    assert evidence.scoring_player_id == "player-a"
    assert PrimaryScoringStateEvidence.from_payload(evidence.to_payload()) == evidence
    assert state.victory_point_ledger_for_player("player-b").to_payload() == opposing_ledger
    assert isinstance(events.records[0].payload, dict)
    assert events.records[0].payload["scoring_player_id"] == "player-a"
    before = state.to_payload(), events.to_payload()
    score_primary_player_boundary(
        state=state,
        record=record,
        scoring_player_id="player-a",
        end_of_battle=False,
        event_log=events,
    )
    assert (state.to_payload(), events.to_payload()) == before


def test_opposing_primary_missions_keep_distinct_commits_at_one_boundary() -> None:
    from tests.phase17n_primary_mission_helpers import phase17n_state_with_setup
    from tests.phase17n_step5g_pairing_certification_helpers import setup_for_lifecycle_row

    from warhammer40k_core.engine.event_log import EventLog
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.primary_scoring_boundary import score_primary_player_boundary
    from warhammer40k_core.engine.primary_scoring_pairing_certification import (
        event_companion_pairing_lifecycle_certification_rows,
    )
    from warhammer40k_core.engine.primary_scoring_transaction_integrity import (
        validate_primary_transaction_semantics,
    )

    row = next(
        row
        for row in event_companion_pairing_lifecycle_certification_rows()
        if row.layout_id == "purge-the-foe-vs-disruption-layout-1"
    )
    state = phase17n_state_with_setup(
        setup=setup_for_lifecycle_row(row),
        active_player_id="player-b",
        phase=BattlePhase.FIGHT,
        battle_round=2,
    )
    record = state.prepare_current_turn_end_boundary(
        completed_phase=BattlePhase.FIGHT, runtime_modifier_registry=None
    )
    events = EventLog()
    for player_id in ("player-b", "player-a"):
        previous_ids = tuple(e.evidence_id for e in state.primary_scoring_state_evidence_records)
        score_primary_player_boundary(
            state=state,
            record=record,
            scoring_player_id=player_id,
            end_of_battle=False,
            event_log=events,
        )
        assert (
            tuple(e.evidence_id for e in state.primary_scoring_state_evidence_records[:-1])
            == previous_ids
        )
        evidence = state.primary_scoring_state_evidence_records[-1]
        assert evidence.scoring_player_id == player_id
        assert evidence.active_player_id == "player-b"
        with pytest.raises(GameLifecycleError, match="hash drifted"):
            replace(
                evidence, scoring_player_id="player-a" if player_id == "player-b" else "player-b"
            )
    validate_primary_transaction_semantics(state=state)
    assert {row.scoring_player_id for row in state.primary_scoring_boundary_lifecycles} == {
        "player-a",
        "player-b",
    }
    assert len({e.evidence_id for e in state.primary_scoring_state_evidence_records}) == 2
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()
    before = state.to_payload(), events.to_payload()
    with pytest.raises(GameLifecycleError, match="scoring player"):
        score_primary_player_boundary(
            state=state,
            record=record,
            scoring_player_id="unknown",
            end_of_battle=False,
            event_log=events,
        )
    assert (state.to_payload(), events.to_payload()) == before


def _context(
    trigger: TimingTriggerKind = TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
) -> SequencingConflictContext:
    return SequencingConflictContext(
        conflict_id="order36-conflict",
        game_id="order36-game",
        timing_window=TimingWindow(
            window_id="order36-window",
            descriptor=TimingWindowDescriptor(
                descriptor_id="order36-descriptor",
                trigger_kind=trigger,
                source_rule_id="order36-source",
                phase=BattlePhaseKind.SHOOTING,
            ),
            game_id="order36-game",
            battle_round=1,
            active_player_id="player-a",
            phase=BattlePhaseKind.SHOOTING,
        ),
        player_ids=("player-a", "player-b"),
        active_player_id="player-a",
    )


@pytest.mark.parametrize("first_family", ["primary-scoring", "secondary-scoring"])
def test_mission_turn_end_offers_owner_order_between_primary_and_fixed_secondary(
    first_family: str,
) -> None:
    from tests.phase17n_step6g_secondary_certification_helpers import (
        STEP6G_LIFECYCLE_CERTIFICATION_ROWS,
        secondary_certification_session,
    )

    from warhammer40k_core.engine.sequencing import SEQUENCING_DECISION_TYPE

    row = next(
        row
        for row in STEP6G_LIFECYCLE_CERTIFICATION_ROWS
        if row.secondary_mission_id == "engage-on-all-fronts"
        and row.mode == "fixed"
        and row.scoring_player_id == "player-a"
    )
    session, initial_payload, _ = secondary_certification_session(row)
    status = session.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    assert request.decision_type == SEQUENCING_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert len(request.options) >= 2
    state = session.lifecycle.state
    assert state is not None
    assert not state.primary_scoring_state_evidence_records
    assert not state.victory_point_ledger_for_player("player-a").transactions

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.decision_request import DecisionError
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.mission_turn_end_sequencing import mission_turn_end_context
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.scoring import VictoryPointSourceKind
    from warhammer40k_core.engine.timing_batch_runtime import timing_batches_for_context

    context = mission_turn_end_context(state)
    # The pending owner choice, including its source population, survives restore.
    restored = session.fork()
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    before = session.lifecycle.to_payload()
    with pytest.raises(DecisionError, match="finite action space"):
        session.submit_option(
            request_id=request.request_id,
            option_id="invented-order",
            result_id="invalid-mission-order",
        )
    assert session.lifecycle.to_payload() == before
    option = next(
        option for option in request.options if option.option_id.startswith(f"next:{first_family}:")
    )
    for target in (session, restored):
        result = target.submit_option(
            request_id=request.request_id, option_id=option.option_id, result_id="mission-order"
        )
        assert result.status_kind is not LifecycleStatusKind.INVALID
        target.advance_until_decision_or_terminal()
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    batches = timing_batches_for_context(session.lifecycle.decision_controller, context)
    assert len(batches) == 1
    assert batches[0].completed_participant_ids[0].startswith(first_family + ":")
    transactions = state.victory_point_ledger_for_player("player-a").transactions
    kinds = tuple(transaction.source_kind for transaction in transactions)
    assert VictoryPointSourceKind.FIXED_SECONDARY in kinds
    if VictoryPointSourceKind.PRIMARY in kinds:
        assert kinds[0] is (
            VictoryPointSourceKind.PRIMARY
            if first_family == "primary-scoring"
            else VictoryPointSourceKind.FIXED_SECONDARY
        )
    replayed = LocalGameSession(GameLifecycle.from_payload(initial_payload))
    replay_request = replayed.advance_until_decision_or_terminal().decision_request
    assert replay_request == request
    replayed.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="mission-order"
    )
    replayed.advance_until_decision_or_terminal()
    assert replayed.lifecycle.to_payload() == session.lifecycle.to_payload()


@pytest.mark.parametrize("consume", [False, True])
def test_consecration_subject_order_restores_without_a_fixed_designation_prefix(
    consume: bool,
) -> None:
    from tests.phase11c_command_phase_helpers import default_unit_selection
    from tests.phase17n_primary_mission_helpers import phase17n_consecrate_turn_end_fixture
    from tests.phase17n_step5g_pairing_certification_helpers import pairing_certification_config
    from tests.phase17n_step6g_secondary_certification_helpers import seed_completed_fight_phase

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.primary_mission_choices import (
        SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
    )
    from warhammer40k_core.engine.primary_scoring_pairing_certification import (
        event_companion_pairing_lifecycle_certification_rows,
    )
    from warhammer40k_core.engine.sequencing import SEQUENCING_DECISION_TYPE

    state, decisions = phase17n_consecrate_turn_end_fixture(subjects=2, capture_boundary=False)
    seed_completed_fight_phase(state)
    row = next(
        row
        for row in event_companion_pairing_lifecycle_certification_rows()
        if row.layout_id == "purge-the-foe-vs-reconnaissance-layout-1"
    )
    config = pairing_certification_config(
        row=row,
        setup_game_id=state.game_id,
        player_a_units=tuple(default_unit_selection(f"consecrator-{index}") for index in range(2)),
        player_b_units=tuple(default_unit_selection(f"victim-{index}") for index in range(2)),
    )
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": {"frames": []},
        }
    )
    session = LocalGameSession(lifecycle)
    pending = session.advance_until_decision_or_terminal().decision_request
    assert pending is not None
    assert pending.decision_type == SEQUENCING_DECISION_TYPE
    assert len(pending.options) == 2
    restored = session.fork()
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    option = pending.options[-1]
    if consume:
        designation = next(
            value
            for value in state.primary_mission_progress_state.consecration_designations
            if value.rules_unit_instance_id.endswith(":consecrator-0")
        )
        option = next(
            option
            for option in pending.options
            if option.option_id == f"next:consecration:{designation.designation_id}"
        )
    session.submit_option(
        request_id=pending.request_id,
        option_id=option.option_id,
        result_id="second-consecration-first",
    )
    choice = session.advance_until_decision_or_terminal().decision_request
    assert choice is not None
    assert choice.decision_type == SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
    assert isinstance(choice.payload, dict)
    first_subject = choice.payload["subject_id"]
    decline = next(
        option
        for option in choice.options
        if isinstance(option.payload, dict)
        and bool(option.payload["selected_target_ids"]) is consume
    )
    session.submit_option(
        request_id=choice.request_id,
        option_id=decline.option_id,
        result_id="decline-second-consecration",
    )
    next_choice = session.advance_until_decision_or_terminal().decision_request
    assert next_choice is not None
    assert next_choice.decision_type == SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE
    assert isinstance(next_choice.payload, dict)
    assert next_choice.payload["subject_id"] != first_subject
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()


def test_active_tactical_choice_precedes_opposing_primary_without_committing_it() -> None:
    from tests.phase17n_primary_mission_helpers import phase17n_event_setup
    from tests.phase17n_step6g_secondary_certification_helpers import (
        STEP6G_LIFECYCLE_CERTIFICATION_ROWS,
        secondary_certification_session,
    )

    from warhammer40k_core.engine.mission_decisions import TACTICAL_SECONDARY_SCORE_DECISION_TYPE
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    row = next(
        row
        for row in STEP6G_LIFECYCLE_CERTIFICATION_ROWS
        if row.secondary_mission_id == "engage-on-all-fronts"
        and row.mode == "tactical"
        and row.scoring_player_id == "player-b"
    )
    setup = phase17n_event_setup(
        layout_id="purge-the-foe-vs-disruption-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="disruption",
    )
    session, _, _ = secondary_certification_session(row, mission_setup=setup)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    assert request.decision_type == TACTICAL_SECONDARY_SCORE_DECISION_TYPE
    assert request.actor_id == "player-b"
    state = session.lifecycle.state
    assert state is not None
    assert state.active_player_id == "player-b"
    assert {value.scoring_player_id for value in state.primary_scoring_state_evidence_records} == {
        "player-b"
    }
    assert not state.victory_point_ledger_for_player("player-a").transactions
    restored = session.fork()
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    option = next(option for option in request.options if option.option_id.startswith("score:"))
    result = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="active-tactical-first"
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID
    events = session.lifecycle.decision_controller.event_log.records
    tactical_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "tactical_secondary_mission_scored"
    )
    opposing_commit_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == "primary_scoring_commit_checkpoint_recorded"
        and isinstance(event.payload, dict)
        and event.payload["scoring_player_id"] == "player-a"
    )
    assert tactical_index < opposing_commit_index
    restored.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="active-tactical-first"
    )
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    session.advance_until_decision_or_terminal()
    assert {value.scoring_player_id for value in state.primary_scoring_state_evidence_records} == {
        "player-a",
        "player-b",
    }
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()


@pytest.mark.parametrize("first_family", ["primary-action", "primary-scoring"])
def test_primary_action_and_scoring_keep_the_selected_commit_order(first_family: str) -> None:
    from tests.phase17n_primary_mission_helpers import phase17n_started_primary_action_fixture
    from tests.phase17n_step5g_pairing_certification_helpers import pairing_certification_config
    from tests.phase17n_step6g_secondary_certification_helpers import seed_completed_fight_phase

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.actions import MissionActionStatus
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
    from warhammer40k_core.engine.primary_scoring_pairing_certification import (
        event_companion_pairing_lifecycle_certification_rows,
    )
    from warhammer40k_core.engine.sequencing import SEQUENCING_DECISION_TYPE

    row = next(
        row
        for row in event_companion_pairing_lifecycle_certification_rows()
        if row.layout_id == "disruption-vs-reconnaissance-layout-1"
    )
    state, decisions, action, _ = phase17n_started_primary_action_fixture(
        layout_id=row.layout_id,
        attacker_force_disposition_id=row.attacker_force_disposition_id,
        defender_force_disposition_id=row.defender_force_disposition_id,
        player_id="player-a",
        mission_action_id="decoy-objective",
        current_phase=BattlePhase.FIGHT,
    )
    setup = state.mission_setup
    assert setup is not None
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=setup.primary_mission_assignment_for_player(
                army.player_id
            ).force_disposition_id,
        )
        for army in state.army_definitions
    ]
    seed_completed_fight_phase(state)
    config = pairing_certification_config(row=row, setup_game_id=state.game_id)
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": {"frames": []},
        }
    )
    session = LocalGameSession(lifecycle)
    pending = session.advance_until_decision_or_terminal().decision_request
    assert pending is not None
    assert pending.decision_type == SEQUENCING_DECISION_TYPE
    assert len(pending.options) == 2
    restored = session.fork()
    option = next(
        option for option in pending.options if option.option_id.startswith(f"next:{first_family}:")
    )
    for target in (session, restored):
        result = target.submit_option(
            request_id=pending.request_id,
            option_id=option.option_id,
            result_id="primary-action-order",
        )
        assert result.status_kind is not LifecycleStatusKind.INVALID
        target.advance_until_decision_or_terminal()
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    current = session.lifecycle.state
    assert current is not None
    evidence = next(
        value
        for value in current.primary_scoring_state_evidence_records
        if value.scoring_player_id == "player-a"
    )
    frozen = next(
        value
        for value in evidence.primary_mission_action_states
        if value.action_id == action.action_id
    )
    assert frozen.status is (
        MissionActionStatus.COMPLETED
        if first_family == "primary-action"
        else MissionActionStatus.STARTED
    )
    assert (
        next(
            value for value in current.mission_action_states if value.action_id == action.action_id
        ).status
        is MissionActionStatus.COMPLETED
    )
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()


def test_sensor_sweep_internal_choice_finishes_before_other_mission_rules() -> None:
    from tests.phase17n_primary_mission_helpers import phase17n_sensor_turn_end_fixture
    from tests.phase17n_step5g_pairing_certification_helpers import pairing_certification_config
    from tests.phase17n_step6g_secondary_certification_helpers import seed_completed_fight_phase

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.mission_turn_end_sequencing import mission_turn_end_context
    from warhammer40k_core.engine.primary_mission_choices import (
        SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
    )
    from warhammer40k_core.engine.primary_scoring_pairing_certification import (
        event_companion_pairing_lifecycle_certification_rows,
    )
    from warhammer40k_core.engine.timing_batch_runtime import timing_batches_for_context

    state, decisions, action = phase17n_sensor_turn_end_fixture()
    row = next(
        row
        for row in event_companion_pairing_lifecycle_certification_rows()
        if row.layout_id == "disruption-vs-priority-assets-layout-1"
    )
    seed_completed_fight_phase(state)
    config = pairing_certification_config(row=row, setup_game_id=state.game_id)
    session = LocalGameSession(
        GameLifecycle.from_payload(
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": decisions.to_payload(),
                "reaction_queue": {"frames": []},
            }
        )
    )
    pending = session.advance_until_decision_or_terminal().decision_request
    assert pending is not None
    option = next(
        option
        for option in pending.options
        if option.option_id == f"next:primary-action:{action.action_id}"
    )
    session.submit_option(
        request_id=pending.request_id, option_id=option.option_id, result_id="sensor-action-first"
    )
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    assert request.decision_type == SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE
    current = session.lifecycle.state
    assert current is not None
    assert not current.primary_scoring_state_evidence_records
    context = mission_turn_end_context(current)
    (batch,) = timing_batches_for_context(session.lifecycle.decision_controller, context)
    assert batch.selected_participant_id == f"primary-action:{action.action_id}"
    assert not batch.completed_participant_ids
    restored = session.fork()
    for target in (session, restored):
        target.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id="sensor-remove-marker",
        )
        target.advance_until_decision_or_terminal()
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    (batch,) = timing_batches_for_context(session.lifecycle.decision_controller, context)
    assert batch.current_batch_complete
    assert batch.completed_participant_ids[0] == f"primary-action:{action.action_id}"
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()


def _participant(
    identifier: str,
    owner: str,
    requirement: SequencingRequirement = SequencingRequirement.MANDATORY,
) -> SequencingParticipant:
    return SequencingParticipant(
        participant_id=identifier,
        player_id=owner,
        source_rule_id=identifier,
        requirement=requirement,
    )


def test_active_rules_precede_opposing_rules() -> None:
    request = create_sequencing_decision_request(
        request_id="order36-cross-owner",
        context=_context(),
        participants=(
            _participant("active-rule", "player-a"),
            _participant("opposing-rule", "player-b"),
        ),
    )
    assert "order:opposing-rule,active-rule" not in {option.option_id for option in request.options}


@pytest.mark.parametrize(
    ("trigger", "mission_first"),
    [
        (TimingTriggerKind.START_BATTLE_ROUND, True),
        (TimingTriggerKind.END_BATTLE_ROUND, False),
        (TimingTriggerKind.END_TURN, False),
    ],
)
def test_unowned_mission_priority_preserves_source_exceptions(
    trigger: TimingTriggerKind,
    mission_first: bool,
) -> None:
    from warhammer40k_core.engine.sequencing import SequencingRuleOrigin

    context = _context(trigger)
    mission = tuple(
        SequencingParticipant(
            participant_id=f"mission-{index}",
            player_id=None,
            source_rule_id=f"mission-{index}",
            requirement=SequencingRequirement.MANDATORY,
            origin=SequencingRuleOrigin.MISSION,
        )
        for index in range(2)
    )
    player = _participant("opponent-rule", "player-b")
    request = create_select_next_sequencing_participant_request(
        request_id="mission-order",
        context=context,
        previously_selected_participant_ids=(),
        remaining_participants=(*mission, player),
    )
    assert request.actor_id == ("player-a" if mission_first else "player-b")
    assert {option.option_id for option in request.options} == (
        {"next:mission-0", "next:mission-1"} if mission_first else {"next:opponent-rule"}
    )
    assert SequencingConflictContext.from_payload(context.to_payload()) == context
    if not mission_first:
        payload = context.to_payload()
        payload["sequence_exception_source_id"] = None
        with pytest.raises(GameLifecycleError, match="exception authority drift"):
            SequencingConflictContext.from_payload(payload)


def test_opponent_chooses_order_of_opponents_rules() -> None:
    request = create_sequencing_decision_request(
        request_id="order36-opposing-owner",
        context=_context(),
        participants=(
            _participant("opposing-rule-a", "player-b"),
            _participant("opposing-rule-b", "player-b"),
        ),
    )
    assert request.actor_id == "player-b"


@pytest.mark.parametrize(
    "trigger", [TimingTriggerKind.START_BATTLE_ROUND, TimingTriggerKind.END_BATTLE_ROUND]
)
def test_round_boundary_needs_no_rolloff(trigger: TimingTriggerKind) -> None:
    request = create_sequencing_decision_request(
        request_id="order36-round-boundary",
        context=_context(trigger),
        participants=(
            _participant("active-rule-a", "player-a"),
            _participant("active-rule-b", "player-a"),
        ),
    )
    assert request.actor_id == "player-a"


def test_select_next_excludes_later_owner_and_rejects_actor_drift() -> None:
    participants = (
        _participant("active-a", "player-a"),
        _participant("active-b", "player-a"),
        _participant("opposing", "player-b"),
    )
    request = create_select_next_sequencing_participant_request(
        request_id="order36-select-next",
        context=_context(),
        previously_selected_participant_ids=(),
        remaining_participants=participants,
    )
    assert {option.option_id for option in request.options} == {"next:active-a", "next:active-b"}
    drifted = replace(request, actor_id="player-b")
    result = DecisionResult.for_request(
        request=drifted, result_id="order36-drifted-result", selected_option_id="next:active-a"
    )
    with pytest.raises(GameLifecycleError, match="authority drifted"):
        apply_select_next_sequencing_participant_from_request(request=drifted, result=result)


def test_all_four_tiers_give_each_owner_their_own_choices() -> None:
    participants = tuple(
        _participant(f"{owner}-{requirement.value}-{index}", owner, requirement)
        for owner in ("player-b", "player-a")
        for requirement in (SequencingRequirement.OPTIONAL, SequencingRequirement.MANDATORY)
        for index in range(2)
    )
    selected: list[str] = []
    for owner, requirement in (
        ("player-a", SequencingRequirement.MANDATORY),
        ("player-a", SequencingRequirement.OPTIONAL),
        ("player-b", SequencingRequirement.MANDATORY),
        ("player-b", SequencingRequirement.OPTIONAL),
    ):
        for index in (1, 0):
            request = create_select_next_sequencing_participant_request(
                request_id=f"order36-tier-{len(selected)}",
                context=_context(),
                previously_selected_participant_ids=tuple(selected),
                remaining_participants=tuple(
                    participant
                    for participant in participants
                    if participant.participant_id not in selected
                ),
            )
            assert request.actor_id == owner
            assert {option.option_id for option in request.options} == {
                f"next:{owner}-{requirement.value}-{candidate}" for candidate in range(index + 1)
            }
            result = DecisionResult.for_request(
                request=request,
                result_id=f"order36-tier-result-{len(selected)}",
                selected_option_id=f"next:{owner}-{requirement.value}-{index}",
            )
            decision = apply_select_next_sequencing_participant_from_request(
                request=request, result=result
            )
            selected.append(decision.selected_participant_id)


def test_batch_defers_new_rules_until_original_batch_completes() -> None:
    from warhammer40k_core.engine.timing_batch_state import TimingBatch

    original = (_participant("original-a", "player-a"), _participant("original-b", "player-b"))
    batch = TimingBatch.open(context=_context(), participants=original)
    batch = batch.select("original-a")
    batch = batch.defer((_participant("new-a", "player-a"),))
    batch = batch.complete("original-a")
    assert batch.eligible_participants() == (original[1],)
    with pytest.raises(GameLifecycleError, match="eligible"):
        batch.select("new-a")
    restored = TimingBatch.from_payload(batch.to_payload())
    assert restored == batch
    batch = restored.select("original-b").complete("original-b")
    assert batch.current_batch_complete
    next_batch = batch.release_deferred()
    assert next_batch is not None
    assert tuple(p.participant_id for p in next_batch.eligible_participants()) == ("new-a",)


def test_batch_cannot_complete_unselected_or_duplicate_rule() -> None:
    from warhammer40k_core.engine.timing_batch_state import TimingBatch

    batch = TimingBatch.open(context=_context(), participants=(_participant("a", "player-a"),))
    with pytest.raises(GameLifecycleError, match="selected"):
        batch.complete("a")
    finished = batch.select("a").complete("a")
    with pytest.raises(GameLifecycleError, match="selected"):
        finished.complete("a")
    with pytest.raises(GameLifecycleError, match="eligible"):
        finished.select("a")


def test_fighting_unit_owner_becomes_active_until_activation_ends() -> None:
    from tests.phase11c_command_phase_helpers import battle_state

    from warhammer40k_core.core.ruleset_descriptor import (
        FightEligibilityKind,
        FightOrderingBandKind,
        FightTypeKind,
    )
    from warhammer40k_core.engine.fight_order import FightActivationSelection, FightPhaseState
    from warhammer40k_core.engine.fights_first import FightsFirstRegistry
    from warhammer40k_core.engine.phase import BattlePhase

    state = battle_state()
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    unit = next(army for army in state.army_definitions if army.player_id == "player-b").units[0]
    selection = FightActivationSelection(
        player_id="player-b",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        ordering_band=FightOrderingBandKind.REMAINING_COMBATS,
        fight_type=FightTypeKind.NORMAL,
        eligibility_reasons=(FightEligibilityKind.CURRENTLY_ENGAGED,),
        request_id="order36-fight-request",
        result_id="order36-fight-result",
    )
    phase = (
        FightPhaseState.start(
            battle_round=state.battle_round,
            active_player_id="player-a",
            policy=state.runtime_ruleset_descriptor().fight_policy,
            engaged_at_fight_step_start_unit_ids=(unit.unit_instance_id,),
            fights_first_registry=FightsFirstRegistry.from_state(state),
        )
        .with_activation(selection)
        .with_active_activation(selection)
    )
    state.replace_fight_phase_state(phase)
    assert state.active_player_id == "player-a"
    assert state.effective_active_player_id() == "player-b"
    state.replace_fight_phase_state(phase.with_active_activation(None))
    assert state.effective_active_player_id() == "player-a"


def test_runtime_defers_new_rule_until_original_population_finishes() -> None:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.sequencing import sequencing_decision_event_from_request
    from warhammer40k_core.engine.timing_batch_runtime import (
        select_timing_participant,
        timing_batches_for_context,
    )

    decisions = DecisionController()
    original = (
        _participant("a-1", "player-a"),
        _participant("a-2", "player-a"),
        _participant("b-1", "player-b"),
    )
    selection = select_timing_participant(
        decisions=decisions,
        context=_context(),
        unresolved_participants=original,
        next_request_id=lambda: "order36-runtime-order",
    )
    request = selection.request
    assert request is not None
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        request=request,
        result_id="order36-runtime-result",
        selected_option_id="next:a-2",
    )
    decisions.submit_result(result)
    event_type, payload = sequencing_decision_event_from_request(request=request, result=result)
    decisions.event_log.append(event_type, payload)
    selection = select_timing_participant(
        decisions=decisions,
        context=_context(),
        unresolved_participants=original,
        next_request_id=lambda: "order36-unused",
    )
    assert selection.participant_id == "a-2"
    candidates = (*original, _participant("new-a", "player-a"))
    for completed, expected in (("a-2", "a-1"), ("a-1", "b-1"), ("b-1", "new-a")):
        decisions = DecisionController.from_payload(decisions.to_payload())
        selection = select_timing_participant(
            decisions=decisions,
            context=_context(),
            unresolved_participants=candidates,
            completed_participant_id=completed,
            next_request_id=lambda: "order36-unused",
        )
        assert selection.participant_id == expected
    selection = select_timing_participant(
        decisions=decisions,
        context=_context(),
        unresolved_participants=candidates,
        completed_participant_id="new-a",
        next_request_id=lambda: "order36-unused",
    )
    assert selection.participant_id is None
    assert selection.request is None
    history = timing_batches_for_context(decisions, _context())
    assert len(history) == 2
    assert history[0].completed_participant_ids == ("a-2", "a-1", "b-1")
    assert history[1].completed_participant_ids == ("new-a",)


def test_batch_selection_cannot_be_forged_without_a_decision_record() -> None:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.timing_batch_runtime import timing_batches_for_context
    from warhammer40k_core.engine.timing_batch_state import TimingBatch

    decisions = DecisionController()
    batch = TimingBatch.open(
        context=_context(),
        participants=(_participant("a-1", "player-a"), _participant("a-2", "player-a")),
    )
    decisions.event_log.append(
        "timing_batch_transition", {"transition": "opened", "batch": batch.to_payload()}
    )
    decisions.event_log.append(
        "timing_batch_transition",
        {"transition": "selected", "batch": batch.select("a-2").to_payload()},
    )
    with pytest.raises(GameLifecycleError, match="recorded choice"):
        timing_batches_for_context(decisions, _context())
    from warhammer40k_core.engine.rule_trigger_state import rule_trigger_history

    with pytest.raises(GameLifecycleError, match="recorded choice"):
        rule_trigger_history(decisions)


@pytest.mark.parametrize("field", ["source_rule_id", "player_id", "requirement", "payload"])
def test_command_batch_rejects_consistent_participant_tampering(field: str) -> None:
    from tests.phase11c_command_phase_helpers import battle_state, remove_first_models

    from warhammer40k_core.engine.command_battle_shock_batch_history import (
        validate_command_test_batches,
    )
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.phases.command import CommandPhaseHandler
    from warhammer40k_core.engine.rule_trigger_state import rule_trigger_history
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex

    decisions = DecisionController()
    state = battle_state(decisions=decisions)
    remove_first_models(state, unit_instance_id="army-alpha:intercessor-unit-1", count=3)
    CommandPhaseHandler(stratagem_index=StratagemCatalogIndex.from_records(())).begin_phase(
        state=state, decisions=decisions
    )
    history = rule_trigger_history(decisions)
    validate_command_test_batches(state=state, decisions=decisions, history=history)
    tampered = decisions.to_payload()
    replacements: dict[str, JsonValue] = {
        "source_rule_id": "forged-source",
        "player_id": "player-b",
        "requirement": "optional",
        "payload": {"invented_candidate": True},
    }
    changed = 0
    for event in tampered["event_log"]:
        if event["event_type"] != "timing_batch_transition":
            continue
        payload = event["payload"]
        assert isinstance(payload, dict)
        batch = payload["batch"]
        assert isinstance(batch, dict)
        participants = batch["participants"]
        assert isinstance(participants, list)
        for participant in participants:
            assert isinstance(participant, dict)
            if (
                participant["participant_id"]
                == "command-battle-shock-test:army-alpha:intercessor-unit-1"
            ):
                participant[field] = replacements[field]
                changed += 1
    assert changed == 3  # opening, selection and completion all carry the same forgery.
    forged = DecisionController.from_payload(tampered)
    before = (state.to_payload(), forged.to_payload())
    with pytest.raises(GameLifecycleError, match="source population drifted"):
        validate_command_test_batches(
            state=state, decisions=forged, history=rule_trigger_history(forged)
        )
    assert (state.to_payload(), forged.to_payload()) == before


def test_sequencing_request_never_contains_a_later_secret_tier() -> None:
    import json

    from warhammer40k_core.adapters.access_control import ViewerContext
    from warhammer40k_core.adapters.redaction import (
        decision_request_hidden_from_context,
        public_event_record_payload,
    )
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.timing_batch_decisions import request_for_timing_batch
    from warhammer40k_core.engine.timing_batch_runtime import select_timing_participant
    from warhammer40k_core.engine.timing_batch_state import TimingBatch

    secret = replace(_participant("secret-opponent-rule", "player-b"), secret=True)
    participants = (_participant("a-1", "player-a"), _participant("a-2", "player-a"), secret)
    decisions = DecisionController()
    selection = select_timing_participant(
        decisions=decisions,
        context=_context(),
        unresolved_participants=participants,
        next_request_id=lambda: "order36-public-tier",
    )
    assert selection.request is not None
    assert "secret-opponent-rule" not in json.dumps(selection.request.to_payload())
    batch = TimingBatch.open(context=_context(), participants=(secret,))
    secret_request = request_for_timing_batch(batch, request_id="order36-secret-tier")
    viewer_a = ViewerContext.for_player("player-a")
    viewer_b = ViewerContext.for_player("player-b")
    assert decision_request_hidden_from_context(request=secret_request, viewer=viewer_a)
    assert not decision_request_hidden_from_context(request=secret_request, viewer=viewer_b)
    event = decisions.event_log.records[0]
    assert public_event_record_payload(**event.to_payload(), viewer=viewer_a) is None
    assert public_event_record_payload(**event.to_payload(), viewer=viewer_b) is None


@pytest.mark.parametrize("drift", ["owner", "round", "prefix"])
def test_sequencing_submission_rebuilds_batch_authority_before_mutation(drift: str) -> None:
    from copy import deepcopy

    from tests.phase11c_command_phase_helpers import battle_state

    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.phase_start_sequencing import phase_start_context
    from warhammer40k_core.engine.sequencing_submission_authority import (
        validate_sequencing_submission_authority,
    )
    from warhammer40k_core.engine.timing_batch_runtime import select_timing_participant

    state = battle_state()
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    decisions = DecisionController()
    selection = select_timing_participant(
        decisions=decisions,
        context=phase_start_context(state),
        unresolved_participants=(
            _participant("a-one", "player-a"),
            _participant("a-two", "player-a"),
        ),
        next_request_id=state.next_decision_request_id,
    )
    request = selection.request
    assert request is not None
    decisions.request_decision(request)
    before = (state.to_payload(), decisions.to_payload())
    validate_sequencing_submission_authority(state=state, decisions=decisions, request=request)
    assert (state.to_payload(), decisions.to_payload()) == before
    if drift == "owner":
        request = replace(request, actor_id="player-b")
    elif drift == "round":
        state.battle_round += 1
    else:
        payload = deepcopy(request.payload)
        assert isinstance(payload, dict)
        payload["previously_selected_participant_ids"] = ["invented-rule"]
        request = replace(request, payload=payload)
    # A hostile pending request still cannot become authoritative merely by occupying the queue.
    if drift != "round":
        corrupted = decisions.to_payload()
        corrupted["queue"]["pending_requests"][0] = request.to_payload()
        decisions = DecisionController.from_payload(corrupted)
    before_invalid = (state.to_payload(), decisions.to_payload())
    with pytest.raises(GameLifecycleError, match=r"timing batch|trigger or active-player"):
        validate_sequencing_submission_authority(state=state, decisions=decisions, request=request)
    assert (state.to_payload(), decisions.to_payload()) == before_invalid


def test_secret_request_candidate_retains_source_visibility_without_issuing_ids() -> None:
    from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
    from warhammer40k_core.engine.timing_request_candidates import timing_candidate_for_request

    issued: list[str] = []

    def issue() -> str:
        issued.append("issued")
        return "issued"

    template = DecisionRequest(
        request_id="template",
        decision_type="source-choice",
        actor_id="player-b",
        payload={"secret": True},
        options=(DecisionOption(option_id="use", label="Use", payload={}),),
    )
    candidate = timing_candidate_for_request(
        template=template,
        participant_id="secret-source",
        source_rule_id="secret-rule",
        requirement=SequencingRequirement.OPTIONAL,
        next_request_id=issue,
    )
    assert issued == []
    assert candidate.participant.secret is True
    assert candidate.request_template == template
    activated = candidate.activate()
    assert activated == replace(template, request_id="issued")
    assert issued == ["issued"]


@pytest.mark.parametrize("corruption", ["identity", "duplicate", "orphan", "reversed"])
def test_window_boundary_rejects_drift_before_reentry(corruption: str) -> None:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
    from warhammer40k_core.engine.timing_window_events import record_timing_window_boundary

    decisions = DecisionController()
    window = _context().timing_window
    payload: dict[str, JsonValue] = {
        "timing_window": validate_json_value(window.to_payload()),
        "resolution_order": [],
    }
    if corruption == "identity":
        changed = replace(window, descriptor=replace(window.descriptor, source_rule_id="forged"))
        decisions.event_log.append(
            "timing_window_opened",
            {"timing_window": changed.to_payload(), "resolution_order": []},
        )
    elif corruption == "duplicate":
        decisions.event_log.append("timing_window_opened", payload)
        decisions.event_log.append("timing_window_opened", payload)
    else:
        decisions.event_log.append("timing_window_resolved", payload)
        if corruption == "reversed":
            decisions.event_log.append("timing_window_opened", payload)
    before = decisions.to_payload()
    with pytest.raises(GameLifecycleError, match="Timing window"):
        record_timing_window_boundary(decisions=decisions, window=window, completed=False)
    assert decisions.to_payload() == before


def test_new_trigger_waits_for_all_original_rules_and_survives_checkpoint() -> None:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.rule_trigger_state import (
        RuleTriggerKind,
        complete_rule_trigger,
        observe_rule_trigger,
        release_rule_trigger,
        rule_trigger_history,
    )
    from warhammer40k_core.engine.timing_batch_runtime import select_timing_participant

    decisions = DecisionController()
    participants = (
        _participant("active-move", "player-a"),
        _participant("opposing-response", "player-b"),
    )
    assert (
        select_timing_participant(
            decisions=decisions,
            context=_context(),
            unresolved_participants=participants,
            next_request_id=lambda: "unused-request",
        ).participant_id
        == "active-move"
    )
    child = observe_rule_trigger(
        decisions=decisions,
        kind=RuleTriggerKind.BATTLE_SHOCK_OUTCOME,
        context={"battle_shock_result": {"result_id": "nested-outcome"}},
    )
    assert not release_rule_trigger(decisions=decisions, trigger=child)
    assert (
        select_timing_participant(
            decisions=decisions,
            context=_context(),
            unresolved_participants=participants,
            next_request_id=lambda: "unused-request",
            completed_participant_id="active-move",
        ).participant_id
        == "opposing-response"
    )
    decisions = DecisionController.from_payload(decisions.to_payload())
    assert not release_rule_trigger(decisions=decisions, trigger=child)
    assert not rule_trigger_history(decisions).ready()
    assert (
        select_timing_participant(
            decisions=decisions,
            context=_context(),
            unresolved_participants=participants,
            next_request_id=lambda: "unused-request",
            completed_participant_id="opposing-response",
        ).participant_id
        is None
    )
    assert release_rule_trigger(decisions=decisions, trigger=child)
    complete_rule_trigger(decisions=decisions, trigger=child)
    assert not rule_trigger_history(decisions).ready()
    assert not release_rule_trigger(decisions=decisions, trigger=child)


def test_trigger_disposition_rejects_early_release_and_completion_without_mutation() -> None:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.rule_trigger_state import (
        RuleTriggerKind,
        complete_rule_trigger,
        observe_rule_trigger,
        release_rule_trigger,
    )
    from warhammer40k_core.engine.timing_batch_runtime import select_timing_participant

    decisions = DecisionController()
    first, second = (
        observe_rule_trigger(
            decisions=decisions,
            kind=RuleTriggerKind.BATTLE_SHOCK_OUTCOME,
            context={"battle_shock_result": {"result_id": result_id}},
        )
        for result_id in ("first", "second")
    )
    before = decisions.to_payload()
    assert not release_rule_trigger(decisions=decisions, trigger=second)
    assert decisions.to_payload() == before
    assert release_rule_trigger(decisions=decisions, trigger=first)
    context = replace(_context(), conflict_id=first.conflict_id)
    select_timing_participant(
        decisions=decisions,
        context=context,
        unresolved_participants=(_participant("first-effect", "player-a"),),
        next_request_id=lambda: "unused",
    )
    before = decisions.to_payload()
    with pytest.raises(GameLifecycleError, match="unfinished timing rules"):
        complete_rule_trigger(decisions=decisions, trigger=first)
    assert decisions.to_payload() == before


def test_trigger_history_rejects_early_release() -> None:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.rule_trigger_state import (
        RuleTriggerKind,
        observe_rule_trigger,
        rule_trigger_history,
    )
    from warhammer40k_core.engine.timing_batch_runtime import select_timing_participant

    decisions = DecisionController()
    select_timing_participant(
        decisions=decisions,
        context=_context(),
        unresolved_participants=(_participant("active-rule", "player-a"),),
        next_request_id=lambda: "unused-request",
    )
    child = observe_rule_trigger(
        decisions=decisions,
        kind=RuleTriggerKind.BATTLE_SHOCK_OUTCOME,
        context={"battle_shock_result": {"result_id": "nested-outcome"}},
    )
    decisions.event_log.append("rule_trigger_released", {"trigger_id": child.trigger_id})
    with pytest.raises(GameLifecycleError, match="before its parent batch completed"):
        rule_trigger_history(decisions)


@pytest.mark.parametrize(
    "kind_value",
    ["battle_shock_outcome", "attack_completion", "move_completion", "model_destruction"],
)
def test_blocked_root_keeps_its_action_host_but_deferred_child_releases_it(kind_value: str) -> None:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.phase import GameLifecycleStage, LifecycleStatusKind
    from warhammer40k_core.engine.rule_trigger_state import (
        RuleTrigger,
        RuleTriggerKind,
        complete_rule_trigger,
        observe_rule_trigger,
        release_rule_trigger,
        unreleased_rule_trigger_status,
    )
    from warhammer40k_core.engine.timing_batch_runtime import (
        complete_timing_participant,
        select_timing_participant,
    )

    decisions = DecisionController()
    kind = RuleTriggerKind(kind_value)
    context: dict[str, JsonValue] = {
        "trigger_event_id": "completion-source",
        "attack_sequence": {"sequence_id": "completed-attacks"},
        "battle_shock_result": {"result_id": "completed-test"},
    }
    earlier = observe_rule_trigger(
        decisions=decisions,
        kind=RuleTriggerKind.MODEL_DESTRUCTION,
        context={"trigger_event_id": "earlier-source"},
    )
    root = observe_rule_trigger(decisions=decisions, kind=kind, context=context)
    before = decisions.to_payload()
    assert not release_rule_trigger(decisions=decisions, trigger=root)
    status = unreleased_rule_trigger_status(
        decisions=decisions, trigger=root, stage=GameLifecycleStage.BATTLE
    )
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.ADVANCED
    assert decisions.to_payload() == before
    assert release_rule_trigger(decisions=decisions, trigger=earlier)
    complete_rule_trigger(decisions=decisions, trigger=earlier)
    assert release_rule_trigger(decisions=decisions, trigger=root)
    complete_rule_trigger(decisions=decisions, trigger=root)
    assert (
        unreleased_rule_trigger_status(
            decisions=decisions, trigger=root, stage=GameLifecycleStage.BATTLE
        )
        is None
    )

    select_timing_participant(
        decisions=decisions,
        context=_context(),
        unresolved_participants=(_participant("parent", "player-a"),),
        next_request_id=lambda: "unused",
    )
    child = observe_rule_trigger(
        decisions=decisions, kind=kind, context={**context, "trigger_event_id": "child-source"}
    )
    decisions = DecisionController.from_payload(decisions.to_payload())
    before = decisions.to_payload()
    assert not release_rule_trigger(decisions=decisions, trigger=child)
    assert (
        unreleased_rule_trigger_status(
            decisions=decisions, trigger=child, stage=GameLifecycleStage.BATTLE
        )
        is None
    )
    assert decisions.to_payload() == before
    unknown = RuleTrigger(kind, {"trigger_event_id": "unknown"}, None, None)
    with pytest.raises(GameLifecycleError, match="no observed occurrence"):
        unreleased_rule_trigger_status(
            decisions=decisions, trigger=unknown, stage=GameLifecycleStage.BATTLE
        )
    complete_timing_participant(decisions=decisions, context=_context(), participant_id="parent")
    assert release_rule_trigger(decisions=decisions, trigger=child)


@pytest.mark.parametrize("mutation", ["state", "existing_event", "new_event"])
def test_end_rule_discovery_rejects_each_provider_mutation(mutation: str) -> None:
    from typing import cast

    from tests.rapid_ingress_helpers import ingress_session

    from warhammer40k_core.engine.event_log import JsonValue
    from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
    from warhammer40k_core.engine.turn_end_hooks import (
        TurnEndHookBinding,
        TurnEndHookRegistry,
        TurnEndRequestContext,
    )

    session = ingress_session(battle_round=2, inventory=("INFANTRY",))
    state = session.lifecycle.state
    assert state is not None
    assert state.current_battle_phase is not None
    decisions = session.lifecycle.decision_controller
    event = decisions.event_log.append("discovery-guard-test", {"nested": ["original"]})
    visited: list[str] = []

    def mutate(context: TurnEndRequestContext) -> tuple[TimingRuleCandidate, ...]:
        visited.append("mutator")
        if mutation == "state":
            context.state.battle_shocked_unit_ids.append("army-beta:reserve-0")
        elif mutation == "existing_event":
            payload = cast(dict[str, JsonValue], event.payload)
            cast(list[JsonValue], payload["nested"]).append("changed")
        else:
            context.decisions.event_log.append("unexpected-discovery-event", {})
        return ()

    def later(context: TurnEndRequestContext) -> tuple[TimingRuleCandidate, ...]:
        visited.append("later")
        return ()

    registry = TurnEndHookRegistry.from_bindings(
        (
            TurnEndHookBinding(
                hook_id="guard:first", source_id="guard:source", candidate_handler=mutate
            ),
            TurnEndHookBinding(
                hook_id="guard:later", source_id="guard:source", candidate_handler=later
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="End-rule discovery mutated engine state"):
        registry.candidates_for(
            TurnEndRequestContext(
                state=state, decisions=decisions, completed_phase=state.current_battle_phase
            )
        )
    assert visited == ["mutator"]
