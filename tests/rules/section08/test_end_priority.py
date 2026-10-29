"""08.05 source-correct policy assertions at the production ordering consumer."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section08_fixtures import command_state
from warhammer40k_core.engine.boundary_sequencing import boundary_context
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.sequencing import (
    SequencingParticipant,
    SequencingRequirement,
    SequencingRuleOrigin,
    apply_select_next_sequencing_participant_from_request,
    create_select_next_sequencing_participant_request,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind


@pytest.mark.parametrize("active", ["owner", "opponent"])
@pytest.mark.parametrize("reverse", [False, True])
def test_command_end_exhausts_nonmission_rules_before_either_players_mission(
    section08_definitions: Section02Definitions, active: str, reverse: bool
) -> None:
    state = command_state(section08_definitions)
    state.active_player_id = active
    context = boundary_context(state, TimingTriggerKind.END_PHASE)
    # Typed occurrences start after achievement, without supplying an ordering
    # override or a fake mission-scoring answer to the production consumer.
    participants = tuple(
        SequencingParticipant(
            participant_id=f"{origin.value}:{player}",
            player_id=player,
            source_rule_id=f"constructed:s08:{origin.value}:{player}",
            requirement=SequencingRequirement.MANDATORY,
            origin=origin,
            label="a" if origin is SequencingRuleOrigin.MISSION else "z",
        )
        for origin in (SequencingRuleOrigin.MISSION, SequencingRuleOrigin.PLAYER)
        for player in state.player_ids
    )
    if reverse:
        participants = tuple(reversed(participants))
    request = create_select_next_sequencing_participant_request(
        request_id="s08:end:order",
        context=context,
        previously_selected_participant_ids=(),
        remaining_participants=participants,
    )
    offered = {o.option_id for o in request.options}
    assert offered == {f"next:player:{active}"}
    other = "opponent" if active == "owner" else "owner"
    previous: tuple[str, ...] = ()
    remaining = participants
    observed: list[str] = []
    while remaining:
        request = create_select_next_sequencing_participant_request(
            request_id=f"s08:end:order:{len(previous)}",
            context=context,
            previously_selected_participant_ids=previous,
            remaining_participants=remaining,
        )
        assert len(request.options) == 1
        result = DecisionResult.for_request(
            result_id=f"s08:end:result:{len(previous)}",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
        with pytest.raises(DecisionError):
            apply_select_next_sequencing_participant_from_request(
                request=request,
                result=replace(result, actor_id=other if request.actor_id == active else active),
            )
        choice = apply_select_next_sequencing_participant_from_request(
            request=request, result=result
        )
        observed.append(choice.selected_participant_id)
        previous = (*previous, choice.selected_participant_id)
        remaining = tuple(
            p for p in remaining if p.participant_id != choice.selected_participant_id
        )
    assert observed == [
        f"player:{active}",
        f"player:{other}",
        f"mission:{active}",
        f"mission:{other}",
    ]


@pytest.mark.parametrize("active", ["owner", "opponent"])
def test_both_mission_owners_can_continue_after_nonmission_occurrences_are_exhausted(
    section08_definitions: Section02Definitions, active: str
) -> None:
    state = command_state(section08_definitions)
    state.active_player_id = active
    context = boundary_context(state, TimingTriggerKind.END_PHASE)
    remaining = tuple(
        SequencingParticipant(
            participant_id=f"mission:{player}",
            player_id=player,
            source_rule_id=f"constructed:s08:achieved:{player}",
            requirement=SequencingRequirement.MANDATORY,
            origin=SequencingRuleOrigin.MISSION,
        )
        for player in state.player_ids
    )
    observed: list[str] = []
    previous: tuple[str, ...] = ()
    while remaining:
        request = create_select_next_sequencing_participant_request(
            request_id=f"s08:mission:{len(previous)}",
            context=context,
            previously_selected_participant_ids=previous,
            remaining_participants=remaining,
        )
        assert len(request.options) == 1
        result = DecisionResult.for_request(
            result_id=f"s08:result:{len(previous)}",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
        with pytest.raises(DecisionError):
            apply_select_next_sequencing_participant_from_request(
                request=request, result=replace(result, actor_id="intruder")
            )
        choice = apply_select_next_sequencing_participant_from_request(
            request=request, result=result
        )
        observed.append(choice.selected_participant_id)
        previous = (*previous, choice.selected_participant_id)
        remaining = tuple(
            p for p in remaining if p.participant_id != choice.selected_participant_id
        )
    other = "opponent" if active == "owner" else "owner"
    assert observed == [f"mission:{active}", f"mission:{other}"]


@pytest.mark.parametrize("active", ["owner", "opponent"])
@pytest.mark.parametrize("reverse", [False, True])
def test_native_command_end_finishes_loaded_rules_before_actual_mission_scoring(
    faction_definitions: Section02Definitions, active: str, reverse: bool
) -> None:
    import json

    from tests.support.section08_native_mission import (
        STICKY_SOURCE_ID,
        assert_native_command_outcome,
        native_command_scene,
    )
    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

    s = native_command_scene(faction_definitions, active=active, reverse=reverse)
    session = s.session
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    assert request.decision_type == "resolve_sequencing_order"
    assert request.actor_id == active
    assert len(request.options) == 2
    assert not s.state.sticky_objective_control_states
    assert all(
        s.state.victory_point_ledger_for_player(p).victory_points == 0 for p in s.state.player_ids
    )
    assert isinstance(request.payload, dict)
    participants = request.payload["participants"]
    assert isinstance(participants, list)
    assert len(participants) == 2
    for participant in participants:
        assert isinstance(participant, dict)
        assert participant["origin"] == "player"
        assert participant["source_rule_id"] == STICKY_SOURCE_ID

    from warhammer40k_core.engine.primary_scoring_boundary_lifecycle import (
        validate_pending_primary_scoring_boundary_restore_authority,
    )

    # Exercise the domain validator directly, without an envelope hash guard.
    before_authority = session.lifecycle.to_payload()
    events = session.lifecycle.decision_controller.event_log.records
    with pytest.raises(GameLifecycleError, match="decision family"):
        validate_pending_primary_scoring_boundary_restore_authority(
            state=s.state,
            event_records=events,
            pending_decision_requests=(replace(request, decision_type="select_movement_unit"),),
        )
    with pytest.raises(GameLifecycleError, match="exact event provenance"):
        validate_pending_primary_scoring_boundary_restore_authority(
            state=s.state,
            event_records=tuple(
                e for e in events if e.event_type != "turn_end_faction_rule_requested"
            ),
            pending_decision_requests=(request,),
        )
    assert session.lifecycle.to_payload() == before_authority

    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    fork = session.fork()
    clean = session.fork()
    legal = DecisionResult.for_request(
        result_id="s08:native:legal",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    for invalid in (
        replace(legal, actor_id="opponent" if active == "owner" else "owner"),
        replace(legal, request_id="stale:s08"),
        replace(legal, payload={}),
        replace(legal, selected_option_id=f"next:mission:{active}"),
    ):
        before = session.lifecycle.to_payload()
        with pytest.raises((DecisionError, GameLifecycleError)):
            session.lifecycle.submit_decision(invalid)
        assert session.lifecycle.to_payload() == before
    phase_index = s.state.battle_phase_index
    s.state.battle_phase_index = s.state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    before = session.lifecycle.to_payload()
    with pytest.raises(GameLifecycleError, match="authority drifted"):
        session.lifecycle.submit_decision(legal)
    assert session.lifecycle.to_payload() == before
    s.state.battle_phase_index = phase_index
    assert session.to_persistence_payload() == checkpoint

    for branch in (session, restored, fork, clean):
        pending = branch.lifecycle.pending_decision_request()
        assert pending == request
        branch.submit_option(
            request_id=request.request_id,
            result_id="s08:native:legal",
            option_id=request.options[0].option_id,
        )
        assert_native_command_outcome(branch, active=active)
        replay = ReplayRunner.from_payload(branch.replay_artifact(artifact_id="s08:native")).run()
        assert replay.status is ReplayRunStatus.REPRODUCED, replay
    assert session.lifecycle.to_payload() == restored.lifecycle.to_payload()
    assert (
        session.lifecycle.to_payload()
        == fork.lifecycle.to_payload()
        == clean.lifecycle.to_payload()
    )
    for viewer in s.state.player_ids:
        assert session.view(viewer_player_id=viewer) == restored.view(viewer_player_id=viewer)
        assert session.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == restored.events_since(EventStreamCursor(), viewer_player_id=viewer)


@pytest.mark.parametrize("phase", ["command", "movement", "shooting", "charge", "fight"])
@pytest.mark.parametrize("trigger", [TimingTriggerKind.END_PHASE, TimingTriggerKind.START_PHASE])
def test_command_mission_exception_is_confined_to_its_source_boundary(
    section08_definitions: Section02Definitions, phase: str, trigger: TimingTriggerKind
) -> None:
    from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
    from warhammer40k_core.engine.sequencing import SequencingConflictContext

    state = command_state(section08_definitions)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase(phase))
    context = boundary_context(state, TimingTriggerKind.END_PHASE)
    context = replace(
        context,
        timing_window=replace(
            context.timing_window,
            descriptor=replace(context.timing_window.descriptor, trigger_kind=trigger),
        ),
    )
    expected = (
        "rule:08:08.05:1" if phase == "command" and trigger is TimingTriggerKind.END_PHASE else None
    )
    assert context.sequence_exception_source_id == expected
    assert SequencingConflictContext.from_payload(context.to_payload()) == context
    if expected is not None:
        payload = context.to_payload()
        payload["sequence_exception_source_id"] = None
        with pytest.raises(GameLifecycleError, match="exception authority drift"):
            SequencingConflictContext.from_payload(payload)
    # An automatic mission normally precedes player rules (01.03.01), but the
    # specific Command-end rule postpones it even past opposing optional rules.
    participants = (
        SequencingParticipant(
            participant_id="automatic-mission",
            player_id=None,
            source_rule_id="constructed:s08:automatic",
            requirement=SequencingRequirement.MANDATORY,
            origin=SequencingRuleOrigin.MISSION,
        ),
        SequencingParticipant(
            participant_id="opposing-optional",
            player_id="opponent",
            source_rule_id="constructed:s08:optional",
            requirement=SequencingRequirement.OPTIONAL,
        ),
    )
    request = create_select_next_sequencing_participant_request(
        request_id="s08:source-scope",
        context=context,
        previously_selected_participant_ids=(),
        remaining_participants=participants,
    )
    assert [option.option_id for option in request.options] == (
        ["next:opposing-optional"] if expected is not None else ["next:automatic-mission"]
    )
