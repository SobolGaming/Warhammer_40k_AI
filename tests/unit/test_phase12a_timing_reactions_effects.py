from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.setup_completion_helpers import enter_battle_for_fixture
from tests.support.catalog_package_fixtures import undivided_daemon_package
from tests.support.selected_to_fight_risk_fixtures import (
    attached_selected_to_fight_risk_fixture,
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import DiceRollResult, RollOffRequest
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine import rule_model_destruction
from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.damage_allocation import (
    DECLINE_DESTRUCTION_REACTION_OPTION_ID,
    DECLINE_FEEL_NO_PAIN_OPTION_ID,
    DestructionReactionKind,
    DestructionReactionSource,
    FeelNoPainSource,
    model_by_id,
)
from warhammer40k_core.engine.deadly_demise import deadly_demise_target_unit_ids
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
from warhammer40k_core.engine.event_log import EventLog, JsonValue
from warhammer40k_core.engine.fight_phase_end_hooks import (
    FightPhaseEndRequestContext,
    FightPhaseEndResultContext,
)
from warhammer40k_core.engine.fight_resolution import (
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.opportunity_windows import (
    OpportunityActionKind,
    OpportunityLegalAction,
    OpportunityWindow,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.fight import FightPhaseHandler
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
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


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


def test_lifecycle_rejects_stale_reaction_opportunity_before_reaction_resolution() -> None:
    lifecycle = _battle_lifecycle(unit_selection_ids=("intercessor-unit-1",))
    state = lifecycle.state
    assert state is not None
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    reaction_window = ReactionWindow(
        timing_window=_timing_window(
            state=state,
            trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
            phase=BattlePhase.MOVEMENT,
            window_id="phase18b-generic-opportunity-reaction-window",
        ),
        eligible_player_ids=("player-b",),
    )
    opportunity_window = OpportunityWindow(
        window_id="phase18b-generic-opportunity-window",
        timing_window=reaction_window.timing_window,
        state_hash="phase18b-stale-reaction-opportunity-state",
        sequence_number=99,
        revision=1,
        anchor_event_ids=("event-source-000001",),
        acting_player_id="player-a",
        eligible_player_ids=("player-b",),
        priority_order=("player-b",),
        legal_actions=(
            OpportunityLegalAction(
                action_id="pass",
                source_id="core:pass",
                action_kind=OpportunityActionKind.PASS,
                controller_id=None,
                label="Pass",
            ),
            OpportunityLegalAction(
                action_id="use_reaction_ability",
                source_id="phase18b:reaction-ability",
                action_kind=OpportunityActionKind.ABILITY,
                controller_id="player-b",
                label="Use Reaction Ability",
                target_ids=("army-alpha:intercessor-unit-1",),
            ),
        ),
        default_action_id="pass",
    )

    triggered = lifecycle.reaction_queue.emit_decision_request(
        state=state,
        decisions=lifecycle.decision_controller,
        reaction_window=reaction_window,
        parent_phase=BattlePhase.MOVEMENT,
        parent_step="move_units",
        resume_token="resume-after-generic-opportunity",
        actor_id="player-b",
        options=opportunity_window.decision_options_for_player("player-b"),
        payload_factory=lambda request_id, decision_type, actor_id: (
            opportunity_window.decision_request(
                request_id=request_id,
                actor_id=actor_id,
                decision_type=decision_type,
            ).payload
        ),
    )
    waiting = lifecycle.advance_until_decision_or_terminal()
    assert waiting.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = waiting.decision_request
    assert request is not None
    assert request == triggered.decision_request

    invalid = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase18b-stale-generic-opportunity-reaction",
            request=request,
            selected_option_id="use_reaction_ability",
        )
    )

    assert invalid.status_kind is LifecycleStatusKind.INVALID
    payload = cast(dict[str, object], invalid.payload)
    assert payload["invalid_reason"] == "stale_opportunity_state_hash"
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    assert lifecycle.reaction_queue.frames
    assert not any(
        event.event_type == "reaction_window_resolved"
        for event in lifecycle.decision_controller.event_log.records
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
    participants = _sequencing_participants()

    request = create_sequencing_decision_request(
        request_id=request_id,
        context=context,
        participants=participants,
        dice_manager=manager,
    )
    roll_payload = cast(dict[str, object], request.payload)["roll_off_result"]
    assert request.actor_id == "player-b"
    assert roll_payload is not None
    assert decisions.event_log.records[-1].event_type == "roll_off_resolved"

    drifted_request = replace(
        request,
        actor_id="player-a",
        options=tuple(
            replace(
                option,
                payload={
                    **cast(dict[str, JsonValue], option.payload),
                    "deciding_player_id": "player-a",
                },
            )
            for option in request.options
        ),
    )
    drifted_result = DecisionResult.for_request(
        result_id="phase12a-sequencing-drifted-winner",
        request=drifted_request,
        selected_option_id=drifted_request.options[0].option_id,
    )

    with pytest.raises(GameLifecycleError, match="authoritative context"):
        apply_sequencing_decision(
            request=drifted_request,
            result=drifted_result,
            context=context,
            participants=participants,
        )


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
        event_log=EventLog(),
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


def test_selected_to_fight_risk_split_creates_one_liability_per_survivor() -> None:
    state, runtime, decisions, bodyguard, leader, _enemy, _attached_id = (
        attached_selected_to_fight_risk_fixture()
    )
    first = runtime.next_fight_phase_end_request(
        FightPhaseEndRequestContext(state=state, decisions=decisions)
    )
    assert first is not None
    decisions.request_decision(first)
    record = decisions.submit_result(
        DecisionResult.for_request(
            result_id="attached-risk-first-destruction",
            request=first,
            selected_option_id=first.options[0].option_id,
        )
    )
    assert (
        runtime.apply_fight_phase_end_result(
            FightPhaseEndResultContext(
                state=state, decisions=decisions, request=record.request, result=record.result
            )
        )
        is True
    )
    second = runtime.next_fight_phase_end_request(
        FightPhaseEndRequestContext(state=state, decisions=decisions)
    )
    assert second is not None
    first_unit = cast(str, cast(dict[str, JsonValue], first.payload)["rules_unit_instance_id"])
    second_unit = cast(str, cast(dict[str, JsonValue], second.payload)["rules_unit_instance_id"])
    assert {first_unit, second_unit} == {bodyguard.unit_instance_id, leader.unit_instance_id}
    assert len(state.persisting_effects) == 2


@pytest.mark.parametrize("destroyed_component", ["bodyguard", "leader"])
def test_selected_to_fight_risk_destruction_splits_attached_unit_after_final_component_model(
    destroyed_component: str,
) -> None:
    state, runtime, decisions, bodyguard, leader, _enemy, attached_id = (
        attached_selected_to_fight_risk_fixture(pre_split=False)
    )
    target = bodyguard if destroyed_component == "bodyguard" else leader
    carried_effect = replace(
        _persisting_effect(
            effect_id=f"attached-risk-carried-effect:{destroyed_component}",
            target_unit_instance_ids=(attached_id,),
            expiration=EffectExpiration.end_battle_round(battle_round=1),
        ),
        owner_player_id="player-source",
    )
    state.record_persisting_effect(carried_effect)
    mission_action = MissionActionState.start(
        action_id=f"attached-risk-action:{destroyed_component}",
        player_id="player-source",
        unit_instance_id=attached_id,
        target_id="attached-risk-objective",
        mission_id="attached-risk-mission",
        battle_round=state.battle_round,
        phase=BattlePhase.FIGHT.value,
        start_timing="fight_phase",
        completion_timing="turn_end",
        eligible_unit_instance_ids=(attached_id,),
        interruption_conditions=("unit_destroyed",),
        scoring_source_id="attached-risk-mission",
        victory_points=0,
    )
    state.record_mission_action_state(mission_action)
    request = runtime.next_fight_phase_end_request(
        FightPhaseEndRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    option = next(
        item
        for item in request.options
        if cast(dict[str, JsonValue], item.payload)["selected_model_instance_id"]
        == target.own_models[0].model_instance_id
    )
    decisions.request_decision(request)
    record = decisions.submit_result(
        DecisionResult.for_request(
            result_id=f"attached-risk-destroy-{destroyed_component}",
            request=request,
            selected_option_id=option.option_id,
        )
    )

    assert (
        runtime.apply_fight_phase_end_result(
            FightPhaseEndResultContext(
                state=state,
                decisions=decisions,
                request=record.request,
                result=record.result,
            )
        )
        is True
    )
    assert all(
        formation.attached_unit_instance_id != attached_id
        for army in state.army_definitions
        for formation in army.attached_units
    )
    assert attached_id not in {item.unit_instance_id for item in state.starting_strength_records}
    expected_survivor_id = (
        leader.unit_instance_id
        if destroyed_component == "bodyguard"
        else bodyguard.unit_instance_id
    )
    assert expected_survivor_id in {
        item.unit_instance_id for item in state.starting_strength_records
    }
    expected_carried_effect = carried_effect.with_attached_unit_split(
        attached_unit_instance_id=attached_id,
        surviving_unit_instance_ids=(expected_survivor_id,),
    )
    assert state.persisting_effects == [expected_carried_effect]
    interrupted_action = state.mission_action_state_by_id(mission_action.action_id)
    assert interrupted_action.status is MissionActionStatus.INTERRUPTED
    assert interrupted_action.interrupted_reason == "unit_destroyed"
    assert any(
        item.event_type == "mission_action_interrupted" for item in decisions.event_log.records
    )
    assert any(
        item.event_type == "catalog_failed_fight_activation_model_destroyed"
        for item in decisions.event_log.records
    )


def test_selected_to_fight_risk_non_final_bodyguard_destruction_keeps_attached_unit() -> None:
    state, runtime, decisions, bodyguard, _leader, _enemy, attached_id = (
        attached_selected_to_fight_risk_fixture(
            pre_split=False,
            bodyguard_model_count=2,
        )
    )
    request = runtime.next_fight_phase_end_request(
        FightPhaseEndRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    target_model_id = bodyguard.own_models[0].model_instance_id
    option = next(
        item
        for item in request.options
        if cast(dict[str, JsonValue], item.payload)["selected_model_instance_id"] == target_model_id
    )
    decisions.request_decision(request)
    record = decisions.submit_result(
        DecisionResult.for_request(
            result_id="attached-risk-destroy-non-final-bodyguard",
            request=request,
            selected_option_id=option.option_id,
        )
    )

    assert (
        runtime.apply_fight_phase_end_result(
            FightPhaseEndResultContext(
                state=state,
                decisions=decisions,
                request=record.request,
                result=record.result,
            )
        )
        is True
    )
    assert any(
        formation.attached_unit_instance_id == attached_id
        for army in state.army_definitions
        for formation in army.attached_units
    )
    assert attached_id in {item.unit_instance_id for item in state.starting_strength_records}
    assert model_by_id(
        state=state,
        model_instance_id=bodyguard.own_models[1].model_instance_id,
    ).is_alive
    assert not state.persisting_effects


def test_selected_to_fight_risk_fight_on_death_defers_attached_split_until_activation() -> None:
    state, runtime, decisions, bodyguard, leader, _enemy, attached_id = (
        attached_selected_to_fight_risk_fixture(
            pre_split=False,
            enemy_x=30.0,
        )
    )
    model_id = bodyguard.own_models[0].model_instance_id
    state.record_model_destruction_reaction_sources(
        model_instance_id=model_id,
        sources=(
            DestructionReactionSource(
                source_id="test:attached-risk:fight-on-death",
                reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
                source_rule_id="test:attached-risk:fight-on-death",
            ),
        ),
    )
    request = runtime.next_fight_phase_end_request(
        FightPhaseEndRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    option = next(
        item
        for item in request.options
        if cast(dict[str, JsonValue], item.payload)["selected_model_instance_id"] == model_id
    )
    decisions.request_decision(request)
    destruction_record = decisions.submit_result(
        DecisionResult.for_request(
            result_id="attached-risk-fight-on-death-destruction",
            request=request,
            selected_option_id=option.option_id,
        )
    )
    status = runtime.apply_fight_phase_end_result(
        FightPhaseEndResultContext(
            state=state,
            decisions=decisions,
            request=destruction_record.request,
            result=destruction_record.result,
        )
    )
    assert type(status) is not bool
    reaction_request = decisions.queue.peek_next()
    reaction_option = next(
        item
        for item in reaction_request.options
        if item.option_id != DECLINE_DESTRUCTION_REACTION_OPTION_ID
    )
    reaction_record = decisions.submit_result(
        DecisionResult.for_request(
            result_id="attached-risk-fight-on-death-accepted",
            request=reaction_request,
            selected_option_id=reaction_option.option_id,
        )
    )
    package = undivided_daemon_package()
    handler = FightPhaseHandler(
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=package.army_catalog,
    )

    assert (
        handler.apply_decision(
            state=state,
            decisions=decisions,
            result=reaction_record.result,
        )
        is None
    )
    assert any(
        formation.attached_unit_instance_id == attached_id
        for army in state.army_definitions
        for formation in army.attached_units
    )
    assert state.persisting_effects

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    assert all(
        formation.attached_unit_instance_id != attached_id
        for army in state.army_definitions
        for formation in army.attached_units
    )
    assert leader.unit_instance_id in {
        item.unit_instance_id for item in state.starting_strength_records
    }
    assert not state.persisting_effects
    assert state.battlefield_state is not None
    assert model_id not in state.battlefield_state.placed_model_ids()


def test_selected_to_fight_risk_fight_on_death_exposes_only_destroyed_models_weapons() -> None:
    state, runtime, decisions, bodyguard, _leader, _enemy, _attached_id = (
        attached_selected_to_fight_risk_fixture(
            pre_split=False,
            bodyguard_model_count=2,
        )
    )
    model_id = bodyguard.own_models[1].model_instance_id
    state.record_model_destruction_reaction_sources(
        model_instance_id=model_id,
        sources=(
            DestructionReactionSource(
                source_id="test:attached-risk:model-only-fight-on-death",
                reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
                source_rule_id="test:attached-risk:model-only-fight-on-death",
            ),
        ),
    )
    request = runtime.next_fight_phase_end_request(
        FightPhaseEndRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    option = next(
        item
        for item in request.options
        if cast(dict[str, JsonValue], item.payload)["selected_model_instance_id"] == model_id
    )
    decisions.request_decision(request)
    destruction_record = decisions.submit_result(
        DecisionResult.for_request(
            result_id="attached-risk-model-only-fight-on-death-destruction",
            request=request,
            selected_option_id=option.option_id,
        )
    )
    status = runtime.apply_fight_phase_end_result(
        FightPhaseEndResultContext(
            state=state,
            decisions=decisions,
            request=destruction_record.request,
            result=destruction_record.result,
        )
    )
    assert type(status) is not bool
    reaction_request = decisions.queue.peek_next()
    reaction_option = next(
        item
        for item in reaction_request.options
        if item.option_id != DECLINE_DESTRUCTION_REACTION_OPTION_ID
    )
    reaction_record = decisions.submit_result(
        DecisionResult.for_request(
            result_id="attached-risk-model-only-fight-on-death-accepted",
            request=reaction_request,
            selected_option_id=reaction_option.option_id,
        )
    )
    package = undivided_daemon_package()
    handler = FightPhaseHandler(
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=package.army_catalog,
    )
    assert (
        handler.apply_decision(
            state=state,
            decisions=decisions,
            result=reaction_record.result,
        )
        is None
    )

    melee_status = handler.begin_phase(state=state, decisions=decisions)

    assert melee_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert melee_status.decision_request is not None
    assert melee_status.decision_request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE
    payload = cast(dict[str, JsonValue], melee_status.decision_request.payload)
    proposal_request = cast(dict[str, JsonValue], payload["proposal_request"])
    available_weapons = cast(list[JsonValue], proposal_request["available_weapons"])
    assert available_weapons
    assert {
        cast(str, cast(dict[str, JsonValue], weapon)["model_instance_id"])
        for weapon in available_weapons
    } == {model_id}


def test_deadly_demise_targets_attached_rules_unit_once() -> None:
    state, _runtime, _decisions, _bodyguard, _leader, enemy, attached_id = (
        attached_selected_to_fight_risk_fixture(
            pre_split=False,
            enemy_x=16.0,
        )
    )

    target_ids = deadly_demise_target_unit_ids(
        state=state,
        source_model_instance_id=enemy.own_models[0].model_instance_id,
        range_inches=6.0,
    )

    assert target_ids == (attached_id,)


def test_rule_deadly_demise_collateral_chain_restores_nested_fnp_continuation() -> None:
    state, _runtime, decisions, bodyguard, leader, enemy, attached_id = (
        attached_selected_to_fight_risk_fixture(
            pre_split=False,
            enemy_x=16.0,
        )
    )
    root_model_id = enemy.own_models[0].model_instance_id
    bodyguard_model_id = bodyguard.own_models[0].model_instance_id
    leader_model_id = leader.own_models[0].model_instance_id
    liability = _record_rule_destruction_liability(
        state=state,
        effect_id="test:rule-deadly-demise:nested-fnp-liability",
        target_unit_instance_id=enemy.unit_instance_id,
        owner_player_id="player-enemy",
    )
    root_source = _deadly_demise_source(
        source_id="test:rule-deadly-demise:root",
        mortal_wounds=bodyguard.own_models[0].wounds_remaining,
    )
    collateral_source = _deadly_demise_source(
        source_id="test:rule-deadly-demise:collateral",
        mortal_wounds=1,
    )
    state.clear_model_destruction_reaction_sources(model_instance_id=root_model_id)
    state.record_model_destruction_reaction_sources(
        model_instance_id=root_model_id,
        sources=(root_source,),
    )
    state.record_model_destruction_reaction_sources(
        model_instance_id=bodyguard_model_id,
        sources=(collateral_source,),
    )
    state.record_model_feel_no_pain_sources(
        model_instance_id=leader_model_id,
        sources=(FeelNoPainSource(source_id="test:nested-deadly-demise:fnp", threshold=5),),
        decline_allowed=True,
    )

    destruction = rule_model_destruction.destroy_model_with_rule_reactions(
        state=state,
        decisions=decisions,
        model_instance_id=root_model_id,
        rules_unit_instance_id=enemy.unit_instance_id,
        destroying_player_id="player-enemy",
        source_rule_id="test:rule-deadly-demise:root-destruction",
        source_effect_ids=(liability.effect_id,),
        source_phase=BattlePhase.FIGHT,
        source_step="fight_phase_end",
        source_result_id="test:rule-deadly-demise:root-result",
        completion_event_type="test_rule_deadly_demise_completed",
        completion_event_payload={"root_model_instance_id": root_model_id},
    )

    assert destruction.status is not None
    assert destruction.status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert state.battlefield_state is not None
    assert root_model_id in state.battlefield_state.placed_model_ids()
    assert bodyguard_model_id in state.battlefield_state.placed_model_ids()
    restored_state = GameState.from_payload(state.to_payload())
    restored_decisions = DecisionController.from_payload(decisions.to_payload())
    fnp_request = restored_decisions.queue.peek_next()
    assert rule_model_destruction.is_rule_model_destruction_mortal_wound_request(fnp_request)
    fnp_record = restored_decisions.submit_result(
        DecisionResult.for_request(
            result_id="test:rule-deadly-demise:nested-fnp-declined",
            request=fnp_request,
            selected_option_id=DECLINE_FEEL_NO_PAIN_OPTION_ID,
        )
    )

    final_status = rule_model_destruction.apply_rule_model_destruction_mortal_wound_decision(
        state=restored_state,
        decisions=restored_decisions,
        result=fnp_record.result,
    )
    assert final_status is None
    assert restored_state.battlefield_state is not None
    assert root_model_id not in restored_state.battlefield_state.placed_model_ids()
    assert bodyguard_model_id not in restored_state.battlefield_state.placed_model_ids()
    assert model_by_id(
        state=restored_state,
        model_instance_id=leader_model_id,
    ).wounds_remaining == (leader.own_models[0].starting_wounds - 1)
    assert all(
        effect.effect_id != liability.effect_id for effect in restored_state.persisting_effects
    )
    applied = tuple(
        cast(dict[str, JsonValue], event.payload)
        for event in restored_decisions.event_log.records
        if event.event_type == "deadly_demise_mortal_wounds_applied"
    )
    root_packets = tuple(
        payload
        for payload in applied
        if cast(dict[str, JsonValue], payload["source"])["source_id"] == root_source.source_id
    )
    collateral_reactions = tuple(
        cast(dict[str, JsonValue], event.payload)
        for event in restored_decisions.event_log.records
        if event.event_type == "destruction_reaction_resolved"
        and cast(dict[str, JsonValue], event.payload)["selected_reaction_kind"]
        == DestructionReactionKind.DEADLY_DEMISE.value
        and cast(
            dict[str, JsonValue],
            cast(dict[str, JsonValue], event.payload)["selected_source"],
        )["source_id"]
        == collateral_source.source_id
    )
    assert len(root_packets) == 1
    assert root_packets[0]["target_unit_instance_id"] == attached_id
    assert len(collateral_reactions) == 1
    assert (
        cast(dict[str, JsonValue], collateral_reactions[0]["destruction_provenance"])[
            "destruction_source_kind"
        ]
        == "deadly_demise"
    )
    assert GameState.from_payload(restored_state.to_payload()).to_payload() == (
        restored_state.to_payload()
    )
    assert DecisionController.from_payload(restored_decisions.to_payload()) == restored_decisions


@pytest.mark.parametrize(
    ("mandatory_kind", "expected_action_host"),
    [
        (DestructionReactionKind.FIGHT_ON_DEATH, "fight"),
        (DestructionReactionKind.SHOOT_ON_DEATH, "shooting"),
    ],
)
def test_rule_deadly_demise_collateral_routes_mandatory_action_host_after_restore(
    mandatory_kind: DestructionReactionKind,
    expected_action_host: str,
) -> None:
    state, _runtime, decisions, bodyguard, leader, enemy, _attached_id = (
        attached_selected_to_fight_risk_fixture(
            pre_split=True,
            bodyguard_model_count=2,
            enemy_x=16.0,
        )
    )
    root_model_id = enemy.own_models[0].model_instance_id
    first_casualty_id = bodyguard.own_models[0].model_instance_id
    pending_casualty_id = bodyguard.own_models[1].model_instance_id
    pending_target_model_id = leader.own_models[0].model_instance_id
    source_id = f"test:rule-deadly-demise:mandatory:{mandatory_kind.value}"
    liability = _record_rule_destruction_liability(
        state=state,
        effect_id=f"{source_id}:liability",
        target_unit_instance_id=enemy.unit_instance_id,
        owner_player_id="player-enemy",
    )
    state.clear_model_destruction_reaction_sources(model_instance_id=root_model_id)
    state.record_model_destruction_reaction_sources(
        model_instance_id=root_model_id,
        sources=(
            _deadly_demise_source(
                source_id="test:rule-deadly-demise:root",
                mortal_wounds=sum(model.wounds_remaining for model in bodyguard.own_models),
            ),
        ),
    )
    state.record_model_destruction_reaction_sources(
        model_instance_id=first_casualty_id,
        sources=(
            DestructionReactionSource(
                source_id=source_id,
                reaction_kind=mandatory_kind,
                source_rule_id=source_id,
                optional=False,
            ),
            DestructionReactionSource(
                source_id=f"{source_id}:optional-pause",
                reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
                source_rule_id=f"{source_id}:optional-pause",
            ),
        ),
    )

    destruction = rule_model_destruction.destroy_model_with_rule_reactions(
        state=state,
        decisions=decisions,
        model_instance_id=root_model_id,
        rules_unit_instance_id=enemy.unit_instance_id,
        destroying_player_id="player-enemy",
        source_rule_id=f"{source_id}:root-destruction",
        source_effect_ids=(liability.effect_id,),
        source_phase=BattlePhase.FIGHT,
        source_step="fight_phase_end",
        source_result_id=f"{source_id}:root-result",
        completion_event_type="test_rule_deadly_demise_mandatory_completed",
        completion_event_payload={"root_model_instance_id": root_model_id},
    )

    assert destruction.status is not None
    assert destruction.status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert state.battlefield_state is not None
    assert first_casualty_id not in state.battlefield_state.placed_model_ids()
    assert pending_casualty_id in state.battlefield_state.placed_model_ids()
    assert pending_target_model_id in state.battlefield_state.placed_model_ids()
    restored_state = GameState.from_payload(state.to_payload())
    restored_decisions = DecisionController.from_payload(decisions.to_payload())
    pause_request = restored_decisions.queue.peek_next()
    pause_record = restored_decisions.submit_result(
        DecisionResult.for_request(
            result_id=f"{source_id}:optional-declined",
            request=pause_request,
            selected_option_id=DECLINE_DESTRUCTION_REACTION_OPTION_ID,
        )
    )

    assert (
        rule_model_destruction.apply_rule_model_destruction_reaction_decision(
            state=restored_state,
            decisions=restored_decisions,
            result=pause_record.result,
        )
        is None
    )
    assert restored_state.battlefield_state is not None
    placed_model_ids = restored_state.battlefield_state.placed_model_ids()
    assert root_model_id not in placed_model_ids
    assert pending_casualty_id not in placed_model_ids
    assert pending_target_model_id not in placed_model_ids
    records = restored_decisions.event_log.records
    mandatory_index, mandatory_record = next(
        (index, record)
        for index, record in enumerate(records)
        if record.event_type == "destruction_reaction_resolved"
        and cast(
            dict[str, JsonValue],
            cast(dict[str, JsonValue], record.payload)["selected_source"],
        )["source_id"]
        == source_id
    )
    mandatory_payload = cast(dict[str, JsonValue], mandatory_record.payload)
    pending_casualty_index = next(
        index
        for index, record in enumerate(records)
        if record.event_type == "model_destroyed"
        and cast(dict[str, JsonValue], record.payload)["model_instance_id"] == pending_casualty_id
    )
    pending_target_index = next(
        index
        for index, record in enumerate(records)
        if record.event_type == "deadly_demise_mortal_wounds_applied"
        and cast(dict[str, JsonValue], record.payload)["target_unit_instance_id"]
        == leader.unit_instance_id
    )
    assert mandatory_payload["selected_reaction_kind"] == mandatory_kind.value
    assert mandatory_payload["action_host"] == expected_action_host
    assert mandatory_payload["execution_status"] == "recorded_for_action_host"
    assert (
        cast(dict[str, JsonValue], mandatory_payload["destruction_provenance"])[
            "destruction_source_kind"
        ]
        == "deadly_demise"
    )
    assert mandatory_index < pending_casualty_index < pending_target_index
    assert all(
        effect.effect_id != liability.effect_id for effect in restored_state.persisting_effects
    )


def test_rule_deadly_demise_collateral_fight_on_death_resumes_root_destruction() -> None:
    state, _runtime, decisions, bodyguard, _leader, enemy, _attached_id = (
        attached_selected_to_fight_risk_fixture(
            pre_split=False,
            enemy_x=16.0,
        )
    )
    root_model_id = enemy.own_models[0].model_instance_id
    bodyguard_model_id = bodyguard.own_models[0].model_instance_id
    liability = _record_rule_destruction_liability(
        state=state,
        effect_id="test:rule-deadly-demise:collateral-fod-liability",
        target_unit_instance_id=enemy.unit_instance_id,
        owner_player_id="player-enemy",
    )
    state.clear_model_destruction_reaction_sources(model_instance_id=root_model_id)
    state.record_model_destruction_reaction_sources(
        model_instance_id=root_model_id,
        sources=(
            _deadly_demise_source(
                source_id="test:rule-deadly-demise:fod-root",
                mortal_wounds=bodyguard.own_models[0].wounds_remaining,
            ),
        ),
    )
    state.record_model_destruction_reaction_sources(
        model_instance_id=bodyguard_model_id,
        sources=(
            DestructionReactionSource(
                source_id="test:rule-deadly-demise:collateral-fod",
                reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
                source_rule_id="test:rule-deadly-demise:collateral-fod",
            ),
        ),
    )

    destruction = rule_model_destruction.destroy_model_with_rule_reactions(
        state=state,
        decisions=decisions,
        model_instance_id=root_model_id,
        rules_unit_instance_id=enemy.unit_instance_id,
        destroying_player_id="player-enemy",
        source_rule_id="test:rule-deadly-demise:fod-root-destruction",
        source_effect_ids=(liability.effect_id,),
        source_phase=BattlePhase.FIGHT,
        source_step="fight_phase_end",
        source_result_id="test:rule-deadly-demise:fod-root-result",
        completion_event_type="test_rule_deadly_demise_fod_completed",
        completion_event_payload={"root_model_instance_id": root_model_id},
    )

    assert destruction.status is not None
    reaction_request = decisions.queue.peek_next()
    reaction_option = next(
        option
        for option in reaction_request.options
        if option.option_id != DECLINE_DESTRUCTION_REACTION_OPTION_ID
    )
    reaction_record = decisions.submit_result(
        DecisionResult.for_request(
            result_id="test:rule-deadly-demise:collateral-fod-accepted",
            request=reaction_request,
            selected_option_id=reaction_option.option_id,
        )
    )
    package = undivided_daemon_package()
    handler = FightPhaseHandler(
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=package.army_catalog,
    )

    assert (
        handler.apply_decision(
            state=state,
            decisions=decisions,
            result=reaction_record.result,
        )
        is None
    )
    round_tripped_state = GameState.from_payload(state.to_payload())
    round_tripped_decisions = DecisionController.from_payload(decisions.to_payload())
    completed = handler.begin_phase(
        state=round_tripped_state,
        decisions=round_tripped_decisions,
    )

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    assert round_tripped_state.battlefield_state is not None
    assert root_model_id not in round_tripped_state.battlefield_state.placed_model_ids()
    assert bodyguard_model_id not in round_tripped_state.battlefield_state.placed_model_ids()
    assert all(
        effect.effect_id != liability.effect_id for effect in round_tripped_state.persisting_effects
    )
    destroyed_ids = tuple(
        cast(dict[str, JsonValue], event.payload)["model_instance_id"]
        for event in round_tripped_decisions.event_log.records
        if event.event_type == "model_destroyed"
    )
    assert destroyed_ids[-2:] == (bodyguard_model_id, root_model_id)


@pytest.mark.parametrize(
    ("attacking_unit_kind", "expected_candidate_kind"),
    [("attached", None), ("bodyguard", "leader")],
)
def test_selected_to_fight_risk_split_preserves_exact_attack_lineage(
    attacking_unit_kind: str,
    expected_candidate_kind: str | None,
) -> None:
    state, runtime, decisions, bodyguard, leader, enemy, attached_id = (
        attached_selected_to_fight_risk_fixture()
    )
    attacking_unit_id = (
        attached_id if attacking_unit_kind == "attached" else bodyguard.unit_instance_id
    )
    decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.FIGHT.value,
            "destroying_player_id": "player-source",
            "attacking_unit_instance_id": attacking_unit_id,
            "attacking_model_instance_id": bodyguard.own_models[0].model_instance_id,
            "target_unit_instance_id": enemy.unit_instance_id,
            "model_instance_id": enemy.own_models[0].model_instance_id,
        },
    )
    request = runtime.next_fight_phase_end_request(
        FightPhaseEndRequestContext(state=state, decisions=decisions)
    )
    if expected_candidate_kind is None:
        assert request is None
        return
    assert request is not None
    assert cast(dict[str, JsonValue], request.payload)["rules_unit_instance_id"] == (
        leader.unit_instance_id
    )


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


def _record_rule_destruction_liability(
    *,
    state: GameState,
    effect_id: str,
    target_unit_instance_id: str,
    owner_player_id: str,
) -> PersistingEffect:
    effect = PersistingEffect(
        effect_id=effect_id,
        source_rule_id="test:rule-deadly-demise:liability",
        owner_player_id=owner_player_id,
        target_unit_instance_ids=(target_unit_instance_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhase.FIGHT,
        expiration=EffectExpiration.end_phase(
            battle_round=state.battle_round,
            phase=BattlePhase.FIGHT,
            player_id=owner_player_id,
        ),
        effect_payload={"effect_kind": "test_rule_destruction_liability"},
    )
    state.record_persisting_effect(effect)
    return effect


def _deadly_demise_source(
    *,
    source_id: str,
    mortal_wounds: int,
) -> DestructionReactionSource:
    return DestructionReactionSource(
        source_id=source_id,
        reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
        source_rule_id=source_id,
        payload={
            "trigger_roll_threshold": 2,
            "range_inches": 6.0,
            "mortal_wounds": {"kind": "fixed", "value": mortal_wounds},
        },
        optional=False,
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
    enter_battle_for_fixture(state)
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
        force_disposition_id="purge-the-foe",
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
            allow_legacy_non_strict_rosters=True,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
                descriptor_version="core-v2-phase12a-test"
            ),
            army_catalog=catalog,
            army_muster_requests=(alpha_request, beta_request),
            player_ids=("player-a", "player-b"),
            turn_order=("player-a", "player-b"),
            fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
            mission_setup=MissionSetup.from_mission_pack(
                mission_pack=chapter_approved_2026_27_mission_pack(),
                mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
                terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
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
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
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
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
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
        force_disposition_id="purge-the-foe",
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
