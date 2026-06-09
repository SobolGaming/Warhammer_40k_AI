from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import DiceRollResult, RollOffRequest
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import (
    EffectError,
    EffectExpiration,
    EffectExpirationBoundary,
    EffectExpirationKind,
    PersistingEffect,
    effect_expiration_kind_from_token,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_queue import (
    REACTION_DECISION_TYPE,
    ReactionQueue,
    ReactionQueueFrame,
    TriggeredDecisionRequest,
)
from warhammer40k_core.engine.sequencing import (
    SEQUENCING_DECISION_TYPE,
    SequencingConflictContext,
    SequencingDecision,
    SequencingParticipant,
    apply_sequencing_decision,
    create_sequencing_decision_request,
    request_sequencing_decision,
)
from warhammer40k_core.engine.timing_windows import (
    OutOfPhaseActionContext,
    ReactionWindow,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
    TimingWindowError,
    timing_trigger_kind_from_token,
)
from warhammer40k_core.engine.transports import TransportCapacityProfile, TransportCargoState
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack


def test_reaction_window_emits_interrupt_decision_and_resumes_parent_phase() -> None:
    state = _battle_state(unit_selection_ids=("intercessor-unit-1",))
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    decisions = DecisionController()
    queue = ReactionQueue()
    reaction_window = ReactionWindow(
        timing_window=_timing_window(
            state=state,
            trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
            phase=BattlePhase.MOVEMENT,
            window_id="phase12a-reaction-window",
        ),
        eligible_player_ids=("player-b",),
    )

    triggered = queue.emit_decision_request(
        state=state,
        decisions=decisions,
        reaction_window=reaction_window,
        parent_phase=BattlePhase.MOVEMENT,
        parent_step="move_units",
        resume_token="resume-after-reaction",
        actor_id="player-b",
        options=(
            DecisionOption(
                option_id="decline",
                label="Decline",
                payload={"reaction": "decline"},
            ),
            DecisionOption(
                option_id="react",
                label="React",
                payload={"reaction": "react"},
            ),
        ),
        payload={"source": "after_enemy_unit_ends_move"},
    )

    request = triggered.decision_request
    payload = cast(dict[str, object], request.payload)
    assert queue.parent_is_blocked is True
    assert request.decision_type == REACTION_DECISION_TYPE
    assert request.actor_id == "player-b"
    assert payload["interrupts_parent"] is True
    assert decisions.queue.pending_requests == (request,)

    result = DecisionResult.for_request(
        result_id="phase12a-reaction-result",
        request=request,
        selected_option_id="decline",
    )
    decisions.submit_result(result)
    resume = queue.resolve_reaction(result=result, decisions=decisions)

    assert queue.frames == ()
    assert resume.parent_phase == BattlePhase.MOVEMENT
    assert resume.parent_step == "move_units"
    assert resume.resume_token == "resume-after-reaction"
    assert _last_event_payload(decisions, "reaction_parent_resumed")["resume_token"] == (
        "resume-after-reaction"
    )


def test_lifecycle_submit_decision_resolves_reaction_after_replay_restore() -> None:
    lifecycle = _battle_lifecycle(unit_selection_ids=("intercessor-unit-1",))
    state = lifecycle.state
    assert state is not None
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    reaction_window = ReactionWindow(
        timing_window=_timing_window(
            state=state,
            trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
            phase=BattlePhase.MOVEMENT,
            window_id="phase12a-lifecycle-reaction-window",
        ),
        eligible_player_ids=("player-b",),
    )

    triggered = lifecycle.reaction_queue.emit_decision_request(
        state=state,
        decisions=lifecycle.decision_controller,
        reaction_window=reaction_window,
        parent_phase=BattlePhase.MOVEMENT,
        parent_step="move_units",
        resume_token="resume-after-replay",
        actor_id="player-b",
        options=(
            DecisionOption(
                option_id="decline",
                label="Decline",
                payload={"reaction": "decline"},
            ),
            DecisionOption(
                option_id="react",
                label="React",
                payload={"reaction": "react"},
            ),
        ),
    )
    waiting = lifecycle.advance_until_decision_or_terminal()
    assert waiting.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert waiting.decision_request == triggered.decision_request

    restored = GameLifecycle.from_payload(_lifecycle_payload_copy(lifecycle))
    restored_waiting = restored.advance_until_decision_or_terminal()
    assert restored_waiting.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert restored_waiting.decision_request is not None
    result = DecisionResult.for_request(
        result_id="phase12a-restored-reaction-result",
        request=restored_waiting.decision_request,
        selected_option_id="decline",
    )

    resumed = restored.submit_decision(result)

    assert restored.reaction_queue.frames == ()
    assert resumed.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert (
        _last_event_payload(
            restored.decision_controller,
            "reaction_parent_resumed",
        )["resume_token"]
        == "resume-after-replay"
    )


def test_lifecycle_rejects_pending_reaction_payload_without_matching_frame() -> None:
    lifecycle = _battle_lifecycle(unit_selection_ids=("intercessor-unit-1",))
    state = lifecycle.state
    assert state is not None
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    reaction_window = ReactionWindow(
        timing_window=_timing_window(
            state=state,
            trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
            phase=BattlePhase.MOVEMENT,
            window_id="phase12a-lifecycle-reaction-drift-window",
        ),
        eligible_player_ids=("player-b",),
    )

    triggered = lifecycle.reaction_queue.emit_decision_request(
        state=state,
        decisions=lifecycle.decision_controller,
        reaction_window=reaction_window,
        parent_phase=BattlePhase.MOVEMENT,
        parent_step="move_units",
        resume_token="resume-after-drift-check",
        actor_id="player-b",
        options=(
            DecisionOption(
                option_id="decline",
                label="Decline",
                payload={"reaction": "decline"},
            ),
        ),
    )
    assert triggered.decision_request.decision_type == REACTION_DECISION_TYPE
    payload = _lifecycle_payload_copy(lifecycle)

    missing_frame_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(payload, sort_keys=True)),
    )
    missing_frame_payload["reaction_queue"] = {"frames": []}
    with pytest.raises(
        GameLifecycleError,
        match="pending reaction decision requires a frame",
    ):
        GameLifecycle.from_payload(missing_frame_payload)

    drift_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(payload, sort_keys=True)),
    )
    reaction_queue_payload = cast(dict[str, object], drift_payload["reaction_queue"])
    frames = cast(list[dict[str, object]], reaction_queue_payload["frames"])
    frames[0]["request_id"] = "phase12a-other-reaction-request"
    with pytest.raises(
        GameLifecycleError,
        match="active frame request_id drift",
    ):
        GameLifecycle.from_payload(drift_payload)


def test_out_of_phase_shooting_does_not_trigger_unrelated_shooting_phase_abilities() -> None:
    state = _battle_state(unit_selection_ids=("intercessor-unit-1",))
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    window = _timing_window(
        state=state,
        trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
        phase=BattlePhase.MOVEMENT,
        window_id="phase12a-out-of-phase-window",
    )
    context = OutOfPhaseActionContext(
        context_id="phase12a-overwatch-context",
        parent_window=window,
        action_phase=BattlePhase.SHOOTING,
        action_kind="shoot",
        source_rule_id="fire_overwatch",
    )

    assert context.allows_action("shoot") is True
    assert context.allows_action("normal_shooting_phase_bonus") is False
    assert context.allows_normal_phase_trigger(BattlePhase.SHOOTING) is False
    assert context.allows_normal_phase_trigger(BattlePhase.MOVEMENT) is True

    explicit = replace(context, allow_normal_phase_triggers=True)
    assert explicit.allows_normal_phase_trigger(BattlePhase.SHOOTING) is True
    assert OutOfPhaseActionContext.from_payload(context.to_payload()) == context


def test_active_player_chooses_order_for_simultaneous_during_battle_rules() -> None:
    state = _battle_state(unit_selection_ids=("intercessor-unit-1",))
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    context = SequencingConflictContext(
        conflict_id="phase12a-during-battle-conflict",
        game_id=state.game_id,
        timing_window=_timing_window(
            state=state,
            trigger_kind=TimingTriggerKind.AFTER_UNIT_DESTROYED,
            phase=BattlePhase.SHOOTING,
            window_id="phase12a-during-battle-window",
        ),
        player_ids=state.player_ids,
        active_player_id=state.active_player_id,
    )
    participants = _sequencing_participants()

    request = create_sequencing_decision_request(
        request_id="phase12a-sequencing-during-battle",
        context=context,
        participants=participants,
    )
    result = DecisionResult.for_request(
        result_id="phase12a-sequencing-during-result",
        request=request,
        selected_option_id="order:rule-beta,rule-alpha",
    )
    decision = apply_sequencing_decision(
        request=request,
        result=result,
        context=context,
        participants=participants,
    )

    assert request.decision_type == SEQUENCING_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert decision.deciding_player_id == "player-a"
    assert decision.ordered_participant_ids == ("rule-beta", "rule-alpha")
    assert decision.roll_off_result is None
    assert SequencingDecision.from_payload(decision.to_payload()) == decision


def test_lifecycle_submit_decision_resolves_sequencing_decision() -> None:
    lifecycle = _battle_lifecycle(unit_selection_ids=("intercessor-unit-1",))
    state = lifecycle.state
    assert state is not None
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    context = SequencingConflictContext(
        conflict_id="phase12a-lifecycle-sequencing-conflict",
        game_id=state.game_id,
        timing_window=_timing_window(
            state=state,
            trigger_kind=TimingTriggerKind.AFTER_UNIT_DESTROYED,
            phase=BattlePhase.MOVEMENT,
            window_id="phase12a-lifecycle-sequencing-window",
        ),
        player_ids=state.player_ids,
        active_player_id=state.active_player_id,
    )

    request = request_sequencing_decision(
        context=context,
        participants=_sequencing_participants(),
        decisions=lifecycle.decision_controller,
        request_id=state.next_decision_request_id(),
    )
    waiting = lifecycle.advance_until_decision_or_terminal()
    assert waiting.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert waiting.decision_request == request
    result = DecisionResult.for_request(
        result_id="phase12a-lifecycle-sequencing-result",
        request=request,
        selected_option_id="order:rule-beta,rule-alpha",
    )

    status = lifecycle.submit_decision(result)
    payload = _last_event_payload(lifecycle.decision_controller, "sequencing_order_resolved")

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert payload["ordered_participant_ids"] == ["rule-beta", "rule-alpha"]
    assert lifecycle.decision_controller.records[-1].request.decision_type == (
        SEQUENCING_DECISION_TYPE
    )


def test_roll_off_decides_simultaneous_start_or_end_battle_round_rules() -> None:
    state = _battle_state(unit_selection_ids=("intercessor-unit-1",))
    context = SequencingConflictContext(
        conflict_id="phase12a-battle-round-conflict",
        game_id=state.game_id,
        timing_window=_timing_window(
            state=state,
            trigger_kind=TimingTriggerKind.END_BATTLE_ROUND,
            phase=None,
            window_id="phase12a-battle-round-window",
        ),
        player_ids=state.player_ids,
        active_player_id=None,
    )
    request_id = "phase12a-sequencing-round"
    roll_off_request = RollOffRequest(
        request_id=f"{request_id}:roll-off",
        purpose="sequencing_conflict",
        player_ids=state.player_ids,
        resolving_decision_id=request_id,
    )
    injected = (
        DiceRollResult.from_values(
            roll_id="roll-000001",
            spec=DiceRollManager.roll_off_spec(
                roll_off_request,
                round_number=1,
                player_id="player-a",
            ),
            values=[2],
            source="rng",
        ),
        DiceRollResult.from_values(
            roll_id="roll-000002",
            spec=DiceRollManager.roll_off_spec(
                roll_off_request,
                round_number=1,
                player_id="player-b",
            ),
            values=[6],
            source="rng",
        ),
    )
    decisions = DecisionController()
    manager = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
        injected_results=injected,
    )

    request = create_sequencing_decision_request(
        request_id=request_id,
        context=context,
        participants=_sequencing_participants(),
        dice_manager=manager,
    )
    roll_payload = cast(dict[str, object], request.payload)["roll_off_result"]
    assert request.actor_id == "player-b"
    assert roll_payload is not None
    assert decisions.event_log.records[-1].event_type == "roll_off_resolved"


def test_persisting_effect_survives_embark_and_disembark() -> None:
    state, passenger_id, transport_id = _transport_state_with_embarked_passenger()
    effect = _persisting_effect(
        effect_id="phase12a-effect-embark",
        target_unit_instance_ids=(passenger_id,),
        expiration=EffectExpiration.end_turn(battle_round=1, player_id="player-a"),
    )

    state.record_persisting_effect(effect)
    cargo_state = state.transport_cargo_state_for_transport(transport_id)
    assert cargo_state is not None
    assert state.persisting_effects_for_unit(passenger_id) == (effect,)

    state.replace_transport_cargo_state(cargo_state.with_disembarked_unit(passenger_id))
    assert state.persisting_effects_for_unit(passenger_id) == (effect,)
    assert GameState.from_payload(state.to_payload()).persisting_effects_for_unit(passenger_id) == (
        effect,
    )


def test_persisting_effect_survives_attached_unit_split() -> None:
    state = _battle_state(unit_selection_ids=("intercessor-unit-1", "intercessor-unit-2"))
    attached_id = "attached-unit:phase12a-intercessors"
    state.starting_strength_records.append(
        StartingStrengthRecord(
            player_id="player-a",
            unit_instance_id=attached_id,
            starting_model_count=10,
            single_model_starting_wounds=None,
            source_id="phase12a-attached-unit-join",
        )
    )
    state.starting_strength_records.sort(key=lambda record: record.unit_instance_id)
    effect = _persisting_effect(
        effect_id="phase12a-effect-attached-split",
        target_unit_instance_ids=(attached_id,),
        expiration=EffectExpiration.end_battle_round(battle_round=1),
    )
    state.record_persisting_effect(effect)

    recovered = state.recover_starting_strength_after_attached_unit_split(
        player_id="player-a",
        attached_unit_instance_id=attached_id,
        surviving_unit_instance_ids=(
            "army-alpha:intercessor-unit-1",
            "army-alpha:intercessor-unit-2",
        ),
    )

    assert tuple(record.unit_instance_id for record in recovered) == (
        "army-alpha:intercessor-unit-1",
        "army-alpha:intercessor-unit-2",
    )
    assert state.persisting_effects_for_unit(attached_id) == ()
    expected = effect.with_attached_unit_split(
        attached_unit_instance_id=attached_id,
        surviving_unit_instance_ids=(
            "army-alpha:intercessor-unit-1",
            "army-alpha:intercessor-unit-2",
        ),
    )
    assert state.persisting_effects_for_unit("army-alpha:intercessor-unit-1") == (expected,)
    assert state.persisting_effects_for_unit("army-alpha:intercessor-unit-2") == (expected,)


def test_persisting_effects_expire_at_deterministic_lifecycle_boundaries() -> None:
    state = _battle_state(unit_selection_ids=("intercessor-unit-1",))
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    effect = _persisting_effect(
        effect_id="phase12a-effect-expire",
        target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhase.MOVEMENT,
            player_id="player-a",
        ),
    )
    state.record_persisting_effect(effect)

    completed = state.advance_to_next_battle_phase()

    assert completed is BattlePhase.MOVEMENT
    assert state.current_battle_phase is BattlePhase.SHOOTING
    assert state.persisting_effects == []


def test_persisting_effects_expire_at_start_lifecycle_boundaries() -> None:
    state = _battle_state(unit_selection_ids=("intercessor-unit-1",))
    unit_id = "army-alpha:intercessor-unit-1"
    state.record_persisting_effect(
        _persisting_effect(
            effect_id="phase12a-start-phase-effect",
            target_unit_instance_ids=(unit_id,),
            expiration=EffectExpiration.start_phase(
                battle_round=1,
                phase=BattlePhase.MOVEMENT,
                player_id="player-a",
            ),
        )
    )
    state.record_persisting_effect(
        _persisting_effect(
            effect_id="phase12a-start-turn-effect",
            target_unit_instance_ids=(unit_id,),
            expiration=EffectExpiration.start_turn(battle_round=1, player_id="player-b"),
        )
    )
    state.record_persisting_effect(
        _persisting_effect(
            effect_id="phase12a-start-round-effect",
            target_unit_instance_ids=(unit_id,),
            expiration=EffectExpiration.start_battle_round(battle_round=2),
        )
    )

    completed = state.advance_to_next_battle_phase()

    assert completed is BattlePhase.COMMAND
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    assert tuple(effect.effect_id for effect in state.persisting_effects) == (
        "phase12a-start-round-effect",
        "phase12a-start-turn-effect",
    )

    while state.active_player_id == "player-a":
        state.advance_to_next_battle_phase()

    assert state.active_player_id == "player-b"
    assert tuple(effect.effect_id for effect in state.persisting_effects) == (
        "phase12a-start-round-effect",
    )

    while state.battle_round == 1:
        state.advance_to_next_battle_phase()

    assert state.battle_round == 2
    assert state.active_player_id == "player-a"
    assert state.persisting_effects == []


def test_unsupported_timing_windows_fail_explicitly_before_options_are_emitted() -> None:
    decisions = DecisionController()

    with pytest.raises(TimingWindowError, match="Unsupported TimingTriggerKind token"):
        timing_trigger_kind_from_token("after_unrepresented_rule_text")

    with pytest.raises(TimingWindowError, match="Unsupported TimingTriggerKind token"):
        TimingWindowDescriptor(
            descriptor_id="unsupported-timing-descriptor",
            trigger_kind=cast(TimingTriggerKind, "after_unrepresented_rule_text"),
            source_rule_id="unsupported_rule",
        )
    assert decisions.queue.pending_requests == ()
    assert decisions.event_log.records == ()


def test_phase12a_payloads_round_trip_without_object_reprs() -> None:
    state = _battle_state(unit_selection_ids=("intercessor-unit-1",))
    window = _timing_window(
        state=state,
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        phase=BattlePhase.COMMAND,
        window_id="phase12a-payload-window",
    )
    effect = _persisting_effect(
        effect_id="phase12a-effect-payload",
        target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        expiration=EffectExpiration.end_of_battle(),
    )
    payloads = [window.to_payload(), effect.to_payload()]
    blob = json.dumps(payloads, sort_keys=True)

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert TimingWindow.from_payload(window.to_payload()) == window
    assert PersistingEffect.from_payload(effect.to_payload()) == effect


def test_reaction_queue_payloads_round_trip_while_parent_is_blocked() -> None:
    state = _battle_state(unit_selection_ids=("intercessor-unit-1",))
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    decisions = DecisionController()
    queue = ReactionQueue()
    reaction_window = ReactionWindow(
        timing_window=_timing_window(
            state=state,
            trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
            phase=BattlePhase.MOVEMENT,
            window_id="phase12a-reaction-payload-window",
        ),
        eligible_player_ids=("player-b",),
    )
    triggered = queue.emit_decision_request(
        state=state,
        decisions=decisions,
        reaction_window=reaction_window,
        parent_phase=BattlePhase.MOVEMENT,
        parent_step="move_units",
        resume_token="resume-payload",
        actor_id="player-b",
        options=(
            DecisionOption(
                option_id="decline",
                label="Decline",
                payload={"reaction": "decline"},
            ),
        ),
    )

    restored_queue = ReactionQueue.from_payload(queue.to_payload())
    restored_triggered = TriggeredDecisionRequest.from_payload(triggered.to_payload())
    frame = restored_queue.frames[0]

    assert restored_queue.parent_is_blocked is True
    assert frame == ReactionQueueFrame.from_payload(frame.to_payload())
    assert frame.with_request_id("replacement-request").request_id == "replacement-request"
    assert restored_triggered.decision_request == triggered.decision_request


def test_reaction_queue_rejects_wrong_phase_and_ineligible_actor_before_request() -> None:
    state = _battle_state(unit_selection_ids=("intercessor-unit-1",))
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    decisions = DecisionController()
    queue = ReactionQueue()
    reaction_window = ReactionWindow(
        timing_window=_timing_window(
            state=state,
            trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
            phase=BattlePhase.MOVEMENT,
            window_id="phase12a-reaction-guard-window",
        ),
        eligible_player_ids=("player-b",),
    )

    with pytest.raises(GameLifecycleError, match="parent phase must match current phase"):
        queue.emit_decision_request(
            state=state,
            decisions=decisions,
            reaction_window=reaction_window,
            parent_phase=BattlePhase.SHOOTING,
            parent_step="shooting",
            resume_token="bad-phase",
            actor_id="player-b",
            options=(DecisionOption(option_id="decline", label="Decline", payload=None),),
        )

    with pytest.raises(GameLifecycleError, match="actor must be eligible"):
        queue.emit_decision_request(
            state=state,
            decisions=decisions,
            reaction_window=reaction_window,
            parent_phase=BattlePhase.MOVEMENT,
            parent_step="move_units",
            resume_token="bad-actor",
            actor_id="player-a",
            options=(DecisionOption(option_id="decline", label="Decline", payload=None),),
        )
    assert decisions.queue.pending_requests == ()


def test_sequencing_helpers_enqueue_and_reject_missing_rolloff_manager() -> None:
    state = _battle_state(unit_selection_ids=("intercessor-unit-1",))
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    context = SequencingConflictContext(
        conflict_id="phase12a-helper-conflict",
        game_id=state.game_id,
        timing_window=_timing_window(
            state=state,
            trigger_kind=TimingTriggerKind.AFTER_UNIT_DESTROYED,
            phase=BattlePhase.SHOOTING,
            window_id="phase12a-helper-window",
        ),
        player_ids=state.player_ids,
        active_player_id=state.active_player_id,
    )
    participants = tuple(
        SequencingParticipant.from_payload(participant.to_payload())
        for participant in _sequencing_participants()
    )
    decisions = DecisionController()

    request = request_sequencing_decision(
        request_id="phase12a-helper-sequencing",
        context=SequencingConflictContext.from_payload(context.to_payload()),
        participants=participants,
        decisions=decisions,
    )

    assert decisions.queue.pending_requests == (request,)
    assert request.decision_type == SEQUENCING_DECISION_TYPE

    rolloff_context = SequencingConflictContext(
        conflict_id="phase12a-helper-rolloff-conflict",
        game_id=state.game_id,
        timing_window=_timing_window(
            state=state,
            trigger_kind=TimingTriggerKind.START_BATTLE_ROUND,
            phase=None,
            window_id="phase12a-helper-rolloff-window",
        ),
        player_ids=state.player_ids,
        active_player_id=None,
    )
    with pytest.raises(GameLifecycleError, match="roll-off requires a DiceRollManager"):
        create_sequencing_decision_request(
            request_id="phase12a-helper-rolloff",
            context=rolloff_context,
            participants=participants,
        )


def test_effect_and_timing_fail_fast_validation_branches() -> None:
    state = _battle_state(unit_selection_ids=("intercessor-unit-1", "intercessor-unit-2"))
    effect = _persisting_effect(
        effect_id="phase12a-effect-no-split",
        target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        expiration=EffectExpiration.end_turn(battle_round=1, player_id="player-a"),
    )

    assert EffectExpiration.from_payload(effect.expiration.to_payload()) == effect.expiration
    assert (
        effect.with_attached_unit_split(
            attached_unit_instance_id="army-alpha:intercessor-unit-2",
            surviving_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        )
        is effect
    )
    with pytest.raises(EffectError, match="requires round, phase, and player"):
        EffectExpiration(expiration_kind=cast(EffectExpirationKind, "end_phase"))
    with pytest.raises(EffectError, match="must not include a phase"):
        EffectExpiration(
            expiration_kind=cast(EffectExpirationKind, "end_turn"),
            battle_round=1,
            phase=BattlePhase.MOVEMENT,
            player_id="player-a",
        )
    with pytest.raises(EffectError, match="Turn effect expiration requires round and player"):
        EffectExpiration(expiration_kind=EffectExpirationKind.START_TURN, battle_round=1)
    with pytest.raises(EffectError, match="Battle-round effect expiration requires a round"):
        EffectExpiration(expiration_kind=EffectExpirationKind.START_BATTLE_ROUND)
    with pytest.raises(
        EffectError,
        match="Battle-round effect expiration must not include phase/player",
    ):
        EffectExpiration(
            expiration_kind=EffectExpirationKind.START_BATTLE_ROUND,
            battle_round=1,
            player_id="player-a",
        )
    with pytest.raises(EffectError, match="must not include timing context"):
        EffectExpiration(
            expiration_kind=cast(EffectExpirationKind, "end_of_battle"),
            battle_round=1,
        )
    with pytest.raises(EffectError, match="EffectExpirationKind token must be a string"):
        effect_expiration_kind_from_token(1)
    with pytest.raises(EffectError, match="Unsupported EffectExpirationKind token"):
        effect_expiration_kind_from_token("unsupported_expiration")
    with pytest.raises(EffectError, match="must be a supported BattlePhaseKind"):
        EffectExpiration(
            expiration_kind=EffectExpirationKind.START_PHASE,
            battle_round=1,
            phase=cast(BattlePhase, "unsupported_phase"),
            player_id="player-a",
        )
    with pytest.raises(EffectError, match="expiration must be an EffectExpiration"):
        PersistingEffect(
            effect_id="phase12a-invalid-expiration",
            source_rule_id="phase12a-source-rule",
            owner_player_id="player-a",
            target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            started_battle_round=1,
            expiration=cast(EffectExpiration, object()),
            effect_payload={"modifier": "benefit_of_cover"},
        )
    with pytest.raises(EffectError, match="must be an EffectExpirationBoundary"):
        effect.expires_at(cast(EffectExpirationBoundary, object()))

    descriptor = TimingWindowDescriptor.from_payload(
        TimingWindowDescriptor(
            descriptor_id="phase12a-timing-payload-descriptor",
            trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
            source_rule_id="timing_payload_source",
            phase=BattlePhase.COMMAND,
        ).to_payload()
    )
    assert timing_trigger_kind_from_token(TimingTriggerKind.AFTER_DICE_ROLL) is (
        TimingTriggerKind.AFTER_DICE_ROLL
    )
    assert descriptor.phase == BattlePhase.COMMAND
    with pytest.raises(TimingWindowError, match="trigger requires a phase"):
        TimingWindowDescriptor(
            descriptor_id="phase12a-missing-phase",
            trigger_kind=TimingTriggerKind.START_PHASE,
            source_rule_id="missing_phase_source",
        )
    with pytest.raises(TimingWindowError, match="phase does not match descriptor phase"):
        TimingWindow(
            window_id="phase12a-phase-drift",
            descriptor=descriptor,
            game_id=state.game_id,
            battle_round=state.battle_round,
            active_player_id=state.active_player_id,
            phase=BattlePhase.MOVEMENT,
        )
    with pytest.raises(TimingWindowError, match="must not contain duplicates"):
        ReactionWindow(
            timing_window=_timing_window(
                state=state,
                trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
                phase=BattlePhase.COMMAND,
                window_id="phase12a-duplicate-eligible-window",
            ),
            eligible_player_ids=("player-a", "player-a"),
        )


def test_phase12a_collection_validators_reject_malformed_payloads() -> None:
    state = _battle_state(unit_selection_ids=("intercessor-unit-1",))
    window = _timing_window(
        state=state,
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        phase=BattlePhase.COMMAND,
        window_id="phase12a-validator-window",
    )

    with pytest.raises(EffectError, match="must contain at least 1 value"):
        _persisting_effect(
            effect_id="phase12a-empty-target-effect",
            target_unit_instance_ids=(),
            expiration=EffectExpiration.end_of_battle(),
        )
    with pytest.raises(EffectError, match="target_unit_instance_ids must be a tuple"):
        _persisting_effect(
            effect_id="phase12a-list-target-effect",
            target_unit_instance_ids=cast(tuple[str, ...], ["army-alpha:intercessor-unit-1"]),
            expiration=EffectExpiration.end_of_battle(),
        )
    with pytest.raises(EffectError, match="must not contain duplicates"):
        _persisting_effect(
            effect_id="phase12a-duplicate-target-effect",
            target_unit_instance_ids=(
                "army-alpha:intercessor-unit-1",
                "army-alpha:intercessor-unit-1",
            ),
            expiration=EffectExpiration.end_of_battle(),
        )
    with pytest.raises(TimingWindowError, match="eligible_player_ids must be a tuple"):
        ReactionWindow(
            timing_window=window,
            eligible_player_ids=cast(tuple[str, ...], ["player-a"]),
        )
    with pytest.raises(GameLifecycleError, match="requires at least two participants"):
        create_sequencing_decision_request(
            request_id="phase12a-single-participant",
            context=SequencingConflictContext(
                conflict_id="phase12a-single-participant-conflict",
                game_id=state.game_id,
                timing_window=window,
                player_ids=state.player_ids,
                active_player_id=state.active_player_id,
            ),
            participants=(_sequencing_participants()[0],),
        )


def _timing_window(
    *,
    state: GameState,
    trigger_kind: TimingTriggerKind,
    phase: BattlePhase | None,
    window_id: str,
) -> TimingWindow:
    descriptor = TimingWindowDescriptor(
        descriptor_id=f"{window_id}:descriptor",
        trigger_kind=trigger_kind,
        source_rule_id=f"{window_id}:source",
        phase=phase,
    )
    return TimingWindow(
        window_id=window_id,
        descriptor=descriptor,
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        phase=phase,
        trigger_event_id="event-source-000001",
    )


def _sequencing_participants() -> tuple[SequencingParticipant, ...]:
    return (
        SequencingParticipant(
            participant_id="rule-alpha",
            player_id="player-a",
            source_rule_id="alpha_rule",
            payload={"priority": 1},
        ),
        SequencingParticipant(
            participant_id="rule-beta",
            player_id="player-b",
            source_rule_id="beta_rule",
            payload={"priority": 2},
        ),
    )


def _persisting_effect(
    *,
    effect_id: str,
    target_unit_instance_ids: tuple[str, ...],
    expiration: EffectExpiration,
) -> PersistingEffect:
    return PersistingEffect(
        effect_id=effect_id,
        source_rule_id="phase12a-source-rule",
        owner_player_id="player-a",
        target_unit_instance_ids=target_unit_instance_ids,
        started_battle_round=1,
        started_phase=BattlePhase.MOVEMENT,
        expiration=expiration,
        effect_payload={"modifier": "benefit_of_cover"},
    )


def _battle_state(*, unit_selection_ids: tuple[str, ...]) -> GameState:
    config = _config(unit_selection_ids=unit_selection_ids)
    armies = _mustered_armies(config)
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase12a-battlefield",
        armies=armies,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    while state.current_setup_step is not None:
        state.complete_current_setup_step()
    assert state.stage is GameLifecycleStage.BATTLE
    return state


def _battle_lifecycle(*, unit_selection_ids: tuple[str, ...]) -> GameLifecycle:
    config = _config(unit_selection_ids=unit_selection_ids)
    state = _battle_state(unit_selection_ids=unit_selection_ids)
    return GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": DecisionController().to_payload(),
            "reaction_queue": {"frames": []},
        }
    )


def _lifecycle_payload_copy(lifecycle: GameLifecycle) -> GameLifecyclePayload:
    return cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )


def _transport_state_with_embarked_passenger() -> tuple[GameState, str, str]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    alpha_request = ArmyMusterRequest(
        army_id="army-alpha",
        player_id="player-a",
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id="passenger-unit",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
            UnitMusterSelection(
                unit_selection_id="transport-1",
                datasheet_id="core-transport",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-transport",
                        model_count=1,
                    ),
                ),
            ),
        ),
    )
    beta_request = _army_muster_request(
        catalog=catalog,
        player_id="player-b",
        army_id="army-beta",
        unit_selection_ids=("enemy-unit",),
    )
    alpha = muster_army(
        catalog=catalog,
        request=alpha_request,
    )
    beta = muster_army(
        catalog=catalog,
        request=beta_request,
    )
    state = GameState.from_config(
        GameConfig(
            game_id="phase12a-transport-game",
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2025_26(
                descriptor_version="core-v2-phase12a-test"
            ),
            army_catalog=catalog,
            army_muster_requests=(alpha_request, beta_request),
            player_ids=("player-a", "player-b"),
            turn_order=("player-a", "player-b"),
            fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
            mission_setup=MissionSetup.from_mission_pack(
                mission_pack=chapter_approved_2025_26_mission_pack(),
                mission_pool_entry_id="mission-a",
                terrain_layout_id="layout-1",
                attacker_player_id="player-a",
                defender_player_id="player-b",
            ),
        )
    )
    state.record_army_definition(alpha)
    state.record_army_definition(beta)
    passenger_id = "army-alpha:passenger-unit"
    transport_id = "army-alpha:transport-1"
    state.record_transport_cargo_state(
        TransportCargoState(
            player_id="player-a",
            transport_unit_instance_id=transport_id,
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id="core-transport",
                max_model_count=10,
                allowed_keywords=("INFANTRY",),
            ),
            embarked_unit_instance_ids=(passenger_id,),
            phase_battle_round=1,
            started_phase_embarked_unit_instance_ids=(passenger_id,),
        )
    )
    return state, passenger_id, transport_id


def _config(*, unit_selection_ids: tuple[str, ...]) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase12a-game",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2025_26(
            descriptor_version="core-v2-phase12a-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=unit_selection_ids,
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("enemy-unit",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2025_26_mission_pack(),
            mission_pool_entry_id="mission-a",
            terrain_layout_id="layout-1",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)


def _last_event_payload(
    decisions: DecisionController,
    event_type: str,
) -> dict[str, JsonValue]:
    for event in reversed(decisions.event_log.records):
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"Missing event type: {event_type}")
