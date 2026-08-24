from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.setup_completion_helpers import enter_battle_for_fixture
from tests.support.catalog_package_fixtures import undivided_daemon_package
from tests.support.selected_target_charge_fixtures import (
    selected_target_charge_persisting_effect,
)
from tests.support.selected_to_fight_risk_fixtures import (
    attached_selected_to_fight_risk_fixture,
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import DiceRollResult, RollOffRequest
from warhammer40k_core.core.ruleset_descriptor import (
    FightEligibilityKind,
    FightOrderingBandKind,
    FightTypeKind,
    RulesetDescriptor,
)
from warhammer40k_core.core.weapon_profiles import RangeProfileKind
from warhammer40k_core.engine import (
    fight_unit_selected_grant_resolution,
    rule_model_destruction,
    rule_model_destruction_applied_damage,
)
from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldTransitionBatch,
    ModelRemovalRecord,
)
from warhammer40k_core.engine.catalog_selected_target_charge_effects import (
    selected_target_charge_constraint_for_unit,
)
from warhammer40k_core.engine.damage_allocation import (
    DECLINE_DESTRUCTION_REACTION_OPTION_ID,
    DECLINE_FEEL_NO_PAIN_OPTION_ID,
    DamageApplication,
    DamageKind,
    DestructionReactionKind,
    DestructionReactionSource,
    FeelNoPainSource,
    MortalWoundApplicationProgress,
    apply_damage_to_model,
    model_by_id,
)
from warhammer40k_core.engine.deadly_demise import deadly_demise_target_unit_ids
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectError,
    EffectExpiration,
    EffectExpirationBoundary,
    EffectExpirationKind,
    PersistingEffect,
    effect_expiration_kind_from_token,
)
from warhammer40k_core.engine.event_log import EventLog, JsonValue
from warhammer40k_core.engine.fight_activation_units import (
    active_fight_activation_rules_unit,
    finalize_rule_destruction_after_fight_activation,
)
from warhammer40k_core.engine.fight_order import FightActivationSelection
from warhammer40k_core.engine.fight_phase_end_hooks import (
    FightPhaseEndRequestContext,
    FightPhaseEndResultContext,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedGrant,
    FightUnitSelectedTimedEffect,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState, GameStatePayload
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
from warhammer40k_core.engine.opportunity_windows import (
    OpportunityActionKind,
    OpportunityLegalAction,
    OpportunityWindow,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.fight import FightPhaseHandler
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_destruction_evidence import (
    RulesUnitObjectiveProximityWitness,
)
from warhammer40k_core.engine.reaction_queue import (
    REACTION_DECISION_TYPE,
    ReactionQueue,
    ReactionQueueFrame,
    TriggeredDecisionRequest,
)
from warhammer40k_core.engine.rule_deadly_demise_continuation import (
    RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND,
)
from warhammer40k_core.engine.rule_model_destruction_applied_damage import (
    DEFER_ATTACHED_SPLIT_FIELD,
    continue_applied_mortal_wound_destruction_with_rule_reactions,
    defer_attached_split_from_rule_destruction_context,
)
from warhammer40k_core.engine.rule_model_destruction_fight_continuation import (
    apply_rule_destruction_fight_on_death_reaction,
    remove_rule_fight_on_death_contexts_for_completed_activation,
)
from warhammer40k_core.engine.rule_model_destruction_source_liabilities import (
    consume_rule_destruction_source_liabilities,
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
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleTargetKind


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
def test_selected_target_charge_effect_source_identity_survives_attached_split(
    destroyed_component: str,
) -> None:
    state, runtime, decisions, bodyguard, leader, enemy, attached_id = (
        attached_selected_to_fight_risk_fixture(pre_split=False)
    )
    state.record_persisting_effect(
        selected_target_charge_persisting_effect(
            state=state,
            effect_id=f"selected-target-charge-source-split:{destroyed_component}",
            owner_player_id="player-source",
            source_rules_unit_instance_id=attached_id,
            source_component_unit_instance_id=bodyguard.unit_instance_id,
            selected_target_unit_instance_id=enemy.unit_instance_id,
        )
    )
    destroyed_unit = bodyguard if destroyed_component == "bodyguard" else leader
    survivor = leader if destroyed_component == "bodyguard" else bodyguard
    request = runtime.next_fight_phase_end_request(
        FightPhaseEndRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    option = next(
        item
        for item in request.options
        if cast(dict[str, JsonValue], item.payload)["selected_model_instance_id"]
        == destroyed_unit.own_models[0].model_instance_id
    )
    decisions.request_decision(request)
    record = decisions.submit_result(
        DecisionResult.for_request(
            result_id=f"selected-target-charge-source-split:{destroyed_component}",
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

    constraint = selected_target_charge_constraint_for_unit(
        state=state,
        unit_instance_id=survivor.unit_instance_id,
    )

    assert constraint is not None
    assert constraint.required_target_unit_instance_ids == (enemy.unit_instance_id,)
    assert constraint.source_effect_ids == (
        f"selected-target-charge-source-split:{destroyed_component}",
    )
    assert constraint.source_lineages[0].historical_unit_instance_id == attached_id
    assert constraint.source_lineages[0].surviving_unit_instance_ids == (survivor.unit_instance_id,)


@pytest.mark.parametrize("destroyed_component", ["bodyguard", "leader"])
def test_selected_target_charge_effect_target_identity_expands_surviving_attached_successor(
    destroyed_component: str,
) -> None:
    state, runtime, decisions, bodyguard, leader, enemy, attached_id = (
        attached_selected_to_fight_risk_fixture(pre_split=False)
    )
    state.record_persisting_effect(
        selected_target_charge_persisting_effect(
            state=state,
            effect_id=f"selected-target-charge-target-split:{destroyed_component}",
            owner_player_id="player-enemy",
            source_rules_unit_instance_id=enemy.unit_instance_id,
            source_component_unit_instance_id=enemy.unit_instance_id,
            selected_target_unit_instance_id=attached_id,
        )
    )
    destroyed_unit = bodyguard if destroyed_component == "bodyguard" else leader
    survivor = leader if destroyed_component == "bodyguard" else bodyguard
    request = runtime.next_fight_phase_end_request(
        FightPhaseEndRequestContext(state=state, decisions=decisions)
    )
    assert request is not None
    option = next(
        item
        for item in request.options
        if cast(dict[str, JsonValue], item.payload)["selected_model_instance_id"]
        == destroyed_unit.own_models[0].model_instance_id
    )
    decisions.request_decision(request)
    record = decisions.submit_result(
        DecisionResult.for_request(
            result_id=f"selected-target-charge-target-split:{destroyed_component}",
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

    constraint = selected_target_charge_constraint_for_unit(
        state=state,
        unit_instance_id=enemy.unit_instance_id,
    )

    assert constraint is not None
    assert constraint.required_target_unit_instance_ids == (survivor.unit_instance_id,)
    assert constraint.selected_target_identity_ids == (attached_id,)
    assert constraint.target_lineages[0].is_split is True
    assert constraint.target_lineages[0].is_destroyed is False


def test_selected_target_charge_effect_round_trip_preserves_source_split_lineage_and_expiry() -> (
    None
):
    state, _runtime, _decisions, bodyguard, leader, enemy, attached_id = (
        attached_selected_to_fight_risk_fixture(pre_split=False)
    )
    state.persisting_effects.clear()
    state.record_persisting_effect(
        selected_target_charge_persisting_effect(
            state=state,
            effect_id="selected-target-charge-source-round-trip",
            owner_player_id="player-source",
            source_rules_unit_instance_id=attached_id,
            source_component_unit_instance_id=leader.unit_instance_id,
            selected_target_unit_instance_id=enemy.unit_instance_id,
        )
    )
    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))
    )
    restored.recover_starting_strength_after_attached_unit_split(
        player_id="player-source",
        attached_unit_instance_id=attached_id,
        surviving_unit_instance_ids=(bodyguard.unit_instance_id, leader.unit_instance_id),
        event_log=EventLog(),
    )
    expected_payload: dict[str, JsonValue] | None = None
    for source_id in sorted((bodyguard.unit_instance_id, leader.unit_instance_id)):
        constraint = selected_target_charge_constraint_for_unit(
            state=restored,
            unit_instance_id=source_id,
        )
        assert constraint is not None
        assert constraint.required_target_unit_instance_ids == (enemy.unit_instance_id,)
        if expected_payload is None:
            expected_payload = constraint.to_payload()
        else:
            assert constraint.to_payload() == expected_payload
    round_tripped = GameState.from_payload(restored.to_payload())
    round_tripped_constraint = selected_target_charge_constraint_for_unit(
        state=round_tripped,
        unit_instance_id=bodyguard.unit_instance_id,
    )
    assert round_tripped_constraint is not None
    assert round_tripped_constraint.to_payload() == expected_payload

    expired = round_tripped.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.turn_end(battle_round=1, player_id="player-source")
    )

    assert tuple(effect.effect_id for effect in expired) == (
        "selected-target-charge-source-round-trip",
    )
    assert (
        selected_target_charge_constraint_for_unit(
            state=round_tripped,
            unit_instance_id=bodyguard.unit_instance_id,
        )
        is None
    )


def test_selected_target_charge_effect_expands_all_current_attached_target_successors() -> None:
    state, _runtime, _decisions, bodyguard, leader, enemy, attached_id = (
        attached_selected_to_fight_risk_fixture()
    )
    state.persisting_effects.clear()
    state.record_persisting_effect(
        selected_target_charge_persisting_effect(
            state=state,
            effect_id="selected-target-charge-target-successors",
            owner_player_id="player-enemy",
            source_rules_unit_instance_id=enemy.unit_instance_id,
            source_component_unit_instance_id=enemy.unit_instance_id,
            selected_target_unit_instance_id=attached_id,
        )
    )

    constraint = selected_target_charge_constraint_for_unit(
        state=GameState.from_payload(state.to_payload()),
        unit_instance_id=enemy.unit_instance_id,
    )

    assert constraint is not None
    assert constraint.required_target_unit_instance_ids == tuple(
        sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
    )
    assert constraint.target_lineages[0].current_unit_instance_ids == tuple(
        sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
    )


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
        mission_action_id="attached-risk-action",
        player_id="player-source",
        unit_instance_id=attached_id,
        target_id="attached-risk-objective",
        condition_target_id="attached-risk-objective",
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


def test_fight_activation_resolves_canonical_attached_rules_unit() -> None:
    state, _runtime, _decisions, _bodyguard, _leader, _enemy, attached_id = (
        attached_selected_to_fight_risk_fixture(pre_split=False)
    )
    activation = FightActivationSelection(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=attached_id,
        ordering_band=FightOrderingBandKind.REMAINING_COMBATS,
        fight_type=FightTypeKind.NORMAL,
        eligibility_reasons=(FightEligibilityKind.CURRENTLY_ENGAGED,),
        request_id="attached-risk-ambiguous-activation-request",
        result_id="attached-risk-ambiguous-activation-result",
    )

    rules_unit = active_fight_activation_rules_unit(
        state=state,
        activation=activation,
    )

    assert rules_unit is not None
    assert rules_unit.unit_instance_id == attached_id
    assert rules_unit.is_attached_rules_unit is True


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


def test_selected_to_fight_risk_fight_on_death_cleans_at_phase_end_then_splits() -> None:
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
    assert state.battlefield_state is not None
    assert model_id in state.battlefield_state.placed_model_ids()
    checkpoint = cast(
        GameLifecyclePayload,
        {
            "config": None,
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": {"frames": []},
        },
    )
    checkpoint = GameLifecycle.from_payload(checkpoint).to_payload()
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    liability_drift = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(checkpoint, sort_keys=True)),
    )
    awaiting_effect = next(
        effect
        for effect in liability_drift["state"]["persisting_effects"]
        if cast(dict[str, JsonValue], effect["effect_payload"]).get("effect_kind")
        == "fight_on_death_awaiting_attack"
    )
    completion_context = cast(
        dict[str, JsonValue],
        cast(dict[str, JsonValue], awaiting_effect["effect_payload"])["completion_context"],
    )
    source_effect_ids = cast(list[str], completion_context["source_effect_ids"])
    assert source_effect_ids
    liability_drift["state"]["persisting_effects"] = [
        effect
        for effect in liability_drift["state"]["persisting_effects"]
        if effect["effect_id"] != source_effect_ids[0]
    ]
    with pytest.raises(GameLifecycleError, match="source liability drift"):
        GameLifecycle.from_payload(liability_drift)
    context_drift = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(checkpoint, sort_keys=True)),
    )
    drifted_awaiting_effect = next(
        effect
        for effect in context_drift["state"]["persisting_effects"]
        if cast(dict[str, JsonValue], effect["effect_payload"]).get("effect_kind")
        == "fight_on_death_awaiting_attack"
    )
    cast(
        dict[str, JsonValue],
        cast(dict[str, JsonValue], drifted_awaiting_effect["effect_payload"])["completion_context"],
    )["battle_round"] = state.battle_round + 1
    with pytest.raises(GameLifecycleError, match="model_destroyed event drift"):
        GameLifecycle.from_payload(context_drift)
    assert not any(
        event.event_type == "fight_on_death_activation_started"
        for event in decisions.event_log.records
    )

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
    removed = _last_event_payload(decisions, "fight_on_death_models_removed")
    assert removed["model_instance_ids"] == [model_id]
    assert removed["reason"] == "phase_end"


def test_fight_end_fight_on_death_does_not_grant_second_activation() -> None:
    state, runtime, decisions, bodyguard, _leader, _enemy, attached_id = (
        attached_selected_to_fight_risk_fixture(
            pre_split=False,
            bodyguard_model_count=2,
        )
    )
    fight_state = state.fight_phase_state
    assert fight_state is not None
    prior_activation = FightActivationSelection(
        player_id="player-source",
        battle_round=state.battle_round,
        unit_instance_id=attached_id,
        ordering_band=fight_state.current_ordering_band,
        fight_type=FightTypeKind.NORMAL,
        eligibility_reasons=(FightEligibilityKind.CURRENTLY_ENGAGED,),
        request_id="attached-risk-prior-activation-request",
        result_id="attached-risk-prior-activation-result",
    )
    state.replace_fight_phase_state(
        replace(
            fight_state,
            fight_order_state=fight_state.fight_order_state.with_activation(prior_activation),
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

    completed = handler.begin_phase(state=state, decisions=decisions)

    assert completed.status_kind is LifecycleStatusKind.ADVANCED
    restored_fight_state = state.fight_phase_state
    assert restored_fight_state is not None
    assert restored_fight_state.fight_order_state.activation_selections == (prior_activation,)
    assert state.battlefield_state is not None
    assert model_id not in state.battlefield_state.placed_model_ids()
    assert bodyguard.own_models[0].model_instance_id in (state.battlefield_state.placed_model_ids())
    assert not state.persisting_effects
    assert not any(
        event.event_type == "fight_on_death_activation_started"
        for event in decisions.event_log.records
    )
    removed = _last_event_payload(decisions, "fight_on_death_models_removed")
    assert removed["model_instance_ids"] == [model_id]
    assert removed["reason"] == "phase_end"


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


def test_rule_destruction_resume_rejects_source_unit_drift_without_source_model() -> None:
    state, _runtime, decisions, bodyguard, _leader, enemy, _attached_id = (
        attached_selected_to_fight_risk_fixture(
            pre_split=False,
            enemy_x=16.0,
        )
    )
    root_model_id = enemy.own_models[0].model_instance_id
    target_model_id = bodyguard.own_models[0].model_instance_id
    liability = _record_rule_destruction_liability(
        state=state,
        effect_id="test:rule-destruction:source-unit-drift-liability",
        target_unit_instance_id=enemy.unit_instance_id,
        owner_player_id="player-enemy",
    )
    state.clear_model_destruction_reaction_sources(model_instance_id=root_model_id)
    state.record_model_destruction_reaction_sources(
        model_instance_id=root_model_id,
        sources=(
            _deadly_demise_source(
                source_id="test:rule-destruction:source-unit-drift-deadly-demise",
                mortal_wounds=1,
            ),
        ),
    )
    state.record_model_feel_no_pain_sources(
        model_instance_id=target_model_id,
        sources=(
            FeelNoPainSource(
                source_id="test:rule-destruction:source-unit-drift-fnp",
                threshold=5,
            ),
        ),
        decline_allowed=True,
    )

    destruction = rule_model_destruction.destroy_model_with_rule_reactions(
        state=state,
        decisions=decisions,
        model_instance_id=root_model_id,
        rules_unit_instance_id=enemy.unit_instance_id,
        destroying_player_id="player-enemy",
        source_rule_id="test:rule-destruction:source-unit-drift",
        source_effect_ids=(liability.effect_id,),
        source_phase=BattlePhase.FIGHT,
        source_step="fight_phase_end",
        source_result_id="test:rule-destruction:source-unit-drift-result",
        completion_event_type="test_rule_destruction_source_unit_drift_completed",
        completion_event_payload={"root_model_instance_id": root_model_id},
        source_rules_unit_instance_id=enemy.unit_instance_id,
        source_model_instance_id=None,
    )

    assert destruction.status is not None
    assert destruction.status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    restored_state = GameState.from_payload(state.to_payload())
    controller_payload = decisions.to_payload()
    pending_payload = controller_payload["queue"]["pending_requests"][0]["payload"]
    assert isinstance(pending_payload, dict)
    lost_wound_context = pending_payload["lost_wound_context"]
    assert isinstance(lost_wound_context, dict)
    source_context = lost_wound_context["source_context"]
    assert isinstance(source_context, dict)
    root_context = source_context["root_context"]
    assert isinstance(root_context, dict)
    assert root_context["source_model_instance_id"] is None
    root_context["source_rules_unit_instance_id"] = bodyguard.unit_instance_id
    restored_decisions = DecisionController.from_payload(controller_payload)
    request = restored_decisions.queue.peek_next()
    result = DecisionResult.for_request(
        result_id="test:rule-destruction:source-unit-drift-declined",
        request=request,
        selected_option_id=DECLINE_FEEL_NO_PAIN_OPTION_ID,
    )
    state_before = restored_state.to_payload()
    decisions_before = restored_decisions.to_payload()

    invalid = rule_model_destruction.invalid_rule_model_destruction_mortal_wound_status(
        state=restored_state,
        request=request,
        result=result,
    )

    assert invalid is not None
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    invalid_payload = cast(dict[str, JsonValue], invalid.payload)
    assert invalid_payload["diagnostic"] == (
        "Destruction source rules unit must belong to the destroying player."
    )
    assert restored_state.to_payload() == state_before
    assert restored_decisions.to_payload() == decisions_before


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
    destroyed_payloads = {
        cast(dict[str, JsonValue], event.payload)["model_instance_id"]: cast(
            dict[str, JsonValue], event.payload
        )
        for event in round_tripped_decisions.event_log.records
        if event.event_type == "model_destroyed"
    }
    collateral_attribution = ModelDestructionAttribution.from_model_destroyed_payload(
        destroyed_payloads[bodyguard_model_id]
    )
    root_attribution = ModelDestructionAttribution.from_model_destroyed_payload(
        destroyed_payloads[root_model_id]
    )
    collateral_source_witness = RulesUnitObjectiveProximityWitness.from_payload(
        destroyed_payloads[bodyguard_model_id]["source_rules_unit_objective_proximity_witness"]
    )
    root_destroyed_witness = RulesUnitObjectiveProximityWitness.from_payload(
        destroyed_payloads[root_model_id]["destroyed_rules_unit_objective_proximity_witness"]
    )
    assert (
        collateral_attribution.destruction_provenance.destruction_source_kind
        is DestructionSourceKind.DEADLY_DEMISE
    )
    assert collateral_attribution.source_rules_unit_instance_id == enemy.unit_instance_id
    assert collateral_attribution.source_model_instance_id == root_model_id
    assert collateral_attribution.attacking_unit_instance_id is None
    assert collateral_attribution.attacking_model_instance_id is None
    assert collateral_source_witness == root_destroyed_witness
    assert collateral_source_witness.rules_unit_instance_id == enemy.unit_instance_id
    assert (
        root_attribution.destruction_provenance.destruction_source_kind
        is DestructionSourceKind.ABILITY
    )
    assert root_attribution.source_rules_unit_instance_id is None
    assert root_attribution.source_model_instance_id is None
    assert root_attribution.attacking_unit_instance_id is None
    assert root_attribution.attacking_model_instance_id is None


def test_applied_mortal_wound_destruction_finalizes_with_exact_damage_and_provenance() -> None:
    decisions = DecisionController()
    state = _battle_state(
        unit_selection_ids=("intercessor-unit-1",),
        decisions=decisions,
    )
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    unit = state.army_definitions[0].units[0]
    model = unit.own_models[0]
    evidence = MortalWoundDestructionEvidence.for_non_attack_state(
        state=state,
        destroying_player_id="player-a",
        source_rules_unit_instance_id=unit.unit_instance_id,
        source_model_instance_id=model.model_instance_id,
        destruction_source_kind=DestructionSourceKind.ABILITY,
        action_phase=BattlePhase.FIGHT,
        source_step="phase12a_applied_damage_completion",
    )
    damage = apply_damage_to_model(
        state=state,
        target_unit_instance_id=unit.unit_instance_id,
        model_instance_id=model.model_instance_id,
        damage=model.wounds_remaining,
        damage_kind=DamageKind.MORTAL,
        remove_destroyed_model=False,
    )
    state.clear_model_destruction_reaction_sources(model_instance_id=model.model_instance_id)

    destruction = continue_applied_mortal_wound_destruction_with_rule_reactions(
        state=state,
        decisions=decisions,
        damage_application=damage,
        rules_unit_instance_id=unit.unit_instance_id,
        source_rule_id="phase12a:applied-damage-completion",
        source_result_id="phase12a:applied-damage-completion:result",
        completion_event_type="phase12a_applied_damage_completed",
        completion_event_payload={"application_id": "phase12a:applied-damage"},
        destruction_evidence=evidence,
        defer_attached_split_until_fight_activation_completion=False,
    )

    assert destruction.status is None
    assert destruction.model_destroyed_event_id is not None
    assert destruction.removal_record is not None
    assert destruction.transition_batch is not None
    assert state.battlefield_state is not None
    assert model.model_instance_id not in state.battlefield_state.placed_model_ids()
    destroyed_payload = _last_event_payload(decisions, "model_destroyed")
    assert destroyed_payload["damage_application"] == damage.to_payload()
    assert (
        cast(dict[str, JsonValue], destroyed_payload["destruction_provenance"])[
            "destruction_source_kind"
        ]
        == DestructionSourceKind.ABILITY.value
    )
    assert _last_event_payload(decisions, "phase12a_applied_damage_completed") == {
        "application_id": "phase12a:applied-damage",
        "model_destroyed_event_id": destruction.model_destroyed_event_id,
    }
    finalized = _last_event_payload(
        decisions,
        rule_model_destruction.RULE_MODEL_DESTRUCTION_FINALIZED_EVENT,
    )
    assert finalized["completion_kind"] == RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND
    assert finalized[DEFER_ATTACHED_SPLIT_FIELD] is False
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()
    assert DecisionController.from_payload(decisions.to_payload()) == decisions


def test_applied_destruction_filters_optional_sources_then_decline_resumes_completion() -> None:
    decisions = DecisionController()
    state = _battle_state(
        unit_selection_ids=("intercessor-unit-1",),
        decisions=decisions,
    )
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    unit = state.army_definitions[0].units[0]
    model = unit.own_models[0]
    eligible_source = DestructionReactionSource(
        source_id="phase12a:applied:eligible-fight-on-death",
        reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
        source_rule_id="phase12a:applied:eligible-fight-on-death",
    )
    roll_source = DestructionReactionSource(
        source_id="phase12a:applied:rolled-fight-on-death",
        reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
        source_rule_id="phase12a:applied:rolled-fight-on-death",
        payload={
            "trigger_roll_threshold": 2,
            "trigger_roll_type": "phase12a_applied_optional_trigger",
        },
    )
    melee_only_source = DestructionReactionSource(
        source_id="phase12a:applied:melee-only-fight-on-death",
        reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
        source_rule_id="phase12a:applied:melee-only-fight-on-death",
        payload={
            "trigger_roll_threshold": 2,
            "requires_destroyed_by_melee_attack": True,
        },
    )
    mandatory_shoot_source = DestructionReactionSource(
        source_id="phase12a:applied:mandatory-shoot-on-death",
        reaction_kind=DestructionReactionKind.SHOOT_ON_DEATH,
        source_rule_id="phase12a:applied:mandatory-shoot-on-death",
        optional=False,
    )
    state.clear_model_destruction_reaction_sources(model_instance_id=model.model_instance_id)
    state.record_model_destruction_reaction_sources(
        model_instance_id=model.model_instance_id,
        sources=(
            eligible_source,
            roll_source,
            melee_only_source,
            mandatory_shoot_source,
        ),
    )
    evidence = MortalWoundDestructionEvidence.for_non_attack_state(
        state=state,
        destroying_player_id="player-a",
        source_rules_unit_instance_id=unit.unit_instance_id,
        source_model_instance_id=model.model_instance_id,
        destruction_source_kind=DestructionSourceKind.ABILITY,
        action_phase=BattlePhase.FIGHT,
        source_step="phase12a_applied_optional_filter",
    )
    damage = apply_damage_to_model(
        state=state,
        target_unit_instance_id=unit.unit_instance_id,
        model_instance_id=model.model_instance_id,
        damage=model.wounds_remaining,
        damage_kind=DamageKind.MORTAL,
        remove_destroyed_model=False,
    )

    destruction = continue_applied_mortal_wound_destruction_with_rule_reactions(
        state=state,
        decisions=decisions,
        damage_application=damage,
        rules_unit_instance_id=unit.unit_instance_id,
        source_rule_id="phase12a:applied-optional-filter",
        source_result_id="phase12a:applied-optional-filter:result",
        completion_event_type="phase12a_applied_optional_filter_completed",
        completion_event_payload={"filter": "optional-sources"},
        destruction_evidence=evidence,
        defer_attached_split_until_fight_activation_completion=False,
    )

    assert destruction.status is not None
    assert destruction.status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = decisions.queue.peek_next()
    source_payloads = cast(
        list[dict[str, JsonValue]], cast(dict[str, JsonValue], request.payload)["sources"]
    )
    offered_source_ids = {cast(str, payload["source_id"]) for payload in source_payloads}
    assert eligible_source.source_id in offered_source_ids
    assert melee_only_source.source_id not in offered_source_ids
    assert any(
        event.event_type == "destruction_reaction_trigger_rolled"
        for event in decisions.event_log.records
    )
    not_applicable = _last_event_payload(decisions, "destruction_reaction_trigger_not_applicable")
    assert cast(dict[str, JsonValue], not_applicable["selected_source"])["source_id"] == (
        melee_only_source.source_id
    )
    mandatory = next(
        cast(dict[str, JsonValue], event.payload)
        for event in decisions.event_log.records
        if event.event_type == "destruction_reaction_resolved"
        and cast(dict[str, JsonValue], event.payload).get("resolution_kind") == "mandatory"
    )
    assert mandatory["action_host"] == "shooting"

    record = decisions.submit_result(
        DecisionResult.for_request(
            result_id="phase12a:applied-optional-filter:declined",
            request=request,
            selected_option_id=DECLINE_DESTRUCTION_REACTION_OPTION_ID,
        )
    )
    assert (
        rule_model_destruction.apply_rule_model_destruction_reaction_decision(
            state=state,
            decisions=decisions,
            result=record.result,
        )
        is None
    )
    assert not decisions.queue.pending_requests
    assert (
        _last_event_payload(decisions, "destruction_reaction_resolved")["execution_status"]
        == "declined"
    )
    assert (
        _last_event_payload(decisions, "phase12a_applied_optional_filter_completed")["filter"]
        == "optional-sources"
    )


def test_applied_fight_on_death_continues_active_attached_activation_then_splits() -> None:
    state, _runtime, decisions, bodyguard, leader, _enemy, attached_id = (
        attached_selected_to_fight_risk_fixture(pre_split=False, enemy_x=30.0)
    )
    model = bodyguard.own_models[0]
    fight_state = state.fight_phase_state
    assert fight_state is not None
    activation = FightActivationSelection(
        player_id="player-source",
        battle_round=state.battle_round,
        unit_instance_id=attached_id,
        ordering_band=fight_state.current_ordering_band,
        fight_type=FightTypeKind.NORMAL,
        eligibility_reasons=(FightEligibilityKind.CURRENTLY_ENGAGED,),
        request_id="phase12a:applied-active-fight:request",
        result_id="phase12a:applied-active-fight:result",
    )
    state.replace_fight_phase_state(
        replace(
            fight_state,
            active_activation=activation,
            fight_order_state=fight_state.fight_order_state.with_activation(activation),
        )
    )
    source = DestructionReactionSource(
        source_id="phase12a:applied-active-fight:fight-on-death",
        reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
        source_rule_id="phase12a:applied-active-fight:fight-on-death",
    )
    state.clear_model_destruction_reaction_sources(model_instance_id=model.model_instance_id)
    state.record_model_destruction_reaction_sources(
        model_instance_id=model.model_instance_id,
        sources=(source,),
    )
    evidence = MortalWoundDestructionEvidence.for_non_attack_state(
        state=state,
        destroying_player_id="player-source",
        source_rules_unit_instance_id=bodyguard.unit_instance_id,
        source_model_instance_id=model.model_instance_id,
        destruction_source_kind=DestructionSourceKind.ABILITY,
        action_phase=BattlePhase.FIGHT,
        source_step="phase12a_applied_active_fight",
    )
    damage = apply_damage_to_model(
        state=state,
        target_unit_instance_id=attached_id,
        model_instance_id=model.model_instance_id,
        damage=model.wounds_remaining,
        damage_kind=DamageKind.MORTAL,
        remove_destroyed_model=False,
    )

    destruction = continue_applied_mortal_wound_destruction_with_rule_reactions(
        state=state,
        decisions=decisions,
        damage_application=damage,
        rules_unit_instance_id=attached_id,
        source_rule_id="phase12a:applied-active-fight",
        source_result_id="phase12a:applied-active-fight:damage-result",
        completion_event_type="phase12a_applied_active_fight_completed",
        completion_event_payload={"activation_result_id": activation.result_id},
        destruction_evidence=evidence,
        defer_attached_split_until_fight_activation_completion=True,
    )
    assert destruction.status is not None
    request = decisions.queue.peek_next()
    selected_option = next(
        option
        for option in request.options
        if option.option_id != DECLINE_DESTRUCTION_REACTION_OPTION_ID
    )
    record = decisions.submit_result(
        DecisionResult.for_request(
            result_id="phase12a:applied-active-fight:fight-on-death-accepted",
            request=request,
            selected_option_id=selected_option.option_id,
        )
    )

    apply_rule_destruction_fight_on_death_reaction(
        state=state,
        decisions=decisions,
        result=record.result,
    )
    assert state.fight_phase_state is not None
    assert state.fight_phase_state.active_activation == activation
    assert not model_by_id(state=state, model_instance_id=model.model_instance_id).is_alive
    assert state.battlefield_state is not None
    assert model.model_instance_id in state.battlefield_state.placed_model_ids()
    assert any(
        formation.attached_unit_instance_id == attached_id
        for army in state.army_definitions
        for formation in army.attached_units
    )
    continued = _last_event_payload(decisions, "fight_on_death_active_activation_continued")
    assert cast(dict[str, JsonValue], continued["activation_selection"])["result_id"] == (
        activation.result_id
    )

    state.replace_fight_phase_state(state.fight_phase_state.with_active_activation(None))
    completion_contexts = remove_rule_fight_on_death_contexts_for_completed_activation(
        state=state,
        decisions=decisions,
        activation=activation,
    )
    assert len(completion_contexts) == 1
    completion_context = completion_contexts[0]
    assert (
        finalize_rule_destruction_after_fight_activation(
            state=state,
            decisions=decisions,
            context=completion_context,
            rules_unit_instance_id=attached_id,
        )
        is None
    )
    assert state.battlefield_state is not None
    assert model.model_instance_id not in state.battlefield_state.placed_model_ids()
    assert all(
        formation.attached_unit_instance_id != attached_id
        for army in state.army_definitions
        for formation in army.attached_units
    )
    assert leader.unit_instance_id in {
        record.unit_instance_id for record in state.starting_strength_records
    }
    removed = _last_event_payload(decisions, "fight_on_death_models_removed")
    assert removed["model_instance_ids"] == [model.model_instance_id]
    assert removed["reason"] == "unit_fight_completed"


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
    melee_profile = next(
        profile
        for wargear in undivided_daemon_package().army_catalog.wargear
        for profile in wargear.weapon_profiles
        if profile.range_profile.kind is RangeProfileKind.MELEE
    )
    decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.FIGHT.value,
            **ModelDestructionAttribution.for_attack(
                destroying_player_id="player-source",
                attacking_unit_instance_id=attacking_unit_id,
                attacking_model_instance_id=bodyguard.own_models[0].model_instance_id,
                weapon_profile=melee_profile,
                attack_context_id="attack-context:selected-to-fight-lineage",
            ).to_payload(),
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


def test_fight_unit_selected_grant_resolution_rejects_invalid_typed_inputs() -> None:
    state, decisions, result, activation, grant = _fight_grant_resolution_fixture()

    with pytest.raises(GameLifecycleError, match="require GameState"):
        fight_unit_selected_grant_resolution.record_fight_unit_selected_grant_effects(
            state=cast(GameState, object()),
            decisions=decisions,
            result=result,
            activation=activation,
            grant=grant,
        )
    with pytest.raises(GameLifecycleError, match="require decisions"):
        fight_unit_selected_grant_resolution.record_fight_unit_selected_grant_effects(
            state=state,
            decisions=cast(DecisionController, object()),
            result=result,
            activation=activation,
            grant=grant,
        )
    with pytest.raises(GameLifecycleError, match="require result"):
        fight_unit_selected_grant_resolution.record_fight_unit_selected_grant_effects(
            state=state,
            decisions=decisions,
            result=cast(DecisionResult, object()),
            activation=activation,
            grant=grant,
        )
    with pytest.raises(GameLifecycleError, match="require activation"):
        fight_unit_selected_grant_resolution.record_fight_unit_selected_grant_effects(
            state=state,
            decisions=decisions,
            result=result,
            activation=cast(FightActivationSelection, object()),
            grant=grant,
        )
    with pytest.raises(GameLifecycleError, match="require grant"):
        fight_unit_selected_grant_resolution.record_fight_unit_selected_grant_effects(
            state=state,
            decisions=decisions,
            result=result,
            activation=activation,
            grant=cast(FightUnitSelectedGrant, object()),
        )

    with pytest.raises(GameLifecycleError, match="require GameState"):
        fight_unit_selected_grant_resolution.validate_fight_unit_selected_grant_effects(
            state=cast(GameState, object()),
            result=result,
            activation=activation,
            grant=grant,
        )
    with pytest.raises(GameLifecycleError, match="require result"):
        fight_unit_selected_grant_resolution.validate_fight_unit_selected_grant_effects(
            state=state,
            result=cast(DecisionResult, object()),
            activation=activation,
            grant=grant,
        )
    with pytest.raises(GameLifecycleError, match="require activation"):
        fight_unit_selected_grant_resolution.validate_fight_unit_selected_grant_effects(
            state=state,
            result=result,
            activation=cast(FightActivationSelection, object()),
            grant=grant,
        )
    with pytest.raises(GameLifecycleError, match="require grant"):
        fight_unit_selected_grant_resolution.validate_fight_unit_selected_grant_effects(
            state=state,
            result=result,
            activation=activation,
            grant=cast(FightUnitSelectedGrant, object()),
        )


def test_fight_unit_selected_timed_effects_validate_targets_expiration_and_identity() -> None:
    state, decisions, result, activation, _grant = _fight_grant_resolution_fixture()
    unit_id = activation.unit_instance_id

    opaque_grant = _timed_fight_grant(effect_payload="opaque", expiration="end_phase")
    fight_unit_selected_grant_resolution.validate_fight_unit_selected_grant_effects(
        state=state,
        result=result,
        activation=activation,
        grant=opaque_grant,
    )
    end_turn_grant = _timed_fight_grant(
        effect_payload={"target_unit_instance_ids": [unit_id]},
        expiration="end_turn",
    )
    effects = fight_unit_selected_grant_resolution.record_fight_unit_selected_grant_effects(
        state=state,
        decisions=decisions,
        result=result,
        activation=activation,
        grant=end_turn_grant,
    )
    assert len(effects) == 1
    assert effects[0].target_unit_instance_ids == (unit_id,)

    with pytest.raises(GameLifecycleError, match="already exists"):
        fight_unit_selected_grant_resolution.record_fight_unit_selected_grant_effects(
            state=state,
            decisions=decisions,
            result=result,
            activation=activation,
            grant=end_turn_grant,
        )
    with pytest.raises(GameLifecycleError, match="owner is not in the game"):
        fight_unit_selected_grant_resolution.validate_fight_unit_selected_grant_effects(
            state=state,
            result=replace(result, result_id="fight-grant-outsider-result"),
            activation=replace(activation, player_id="player-outsider"),
            grant=end_turn_grant,
        )


@pytest.mark.parametrize(
    ("effect_payload", "expiration", "expected_error"),
    [
        (
            {"target_unit_instance_ids": "not-a-list"},
            "end_phase",
            "timed target IDs must be a list",
        ),
        ({"target_unit_instance_ids": []}, "end_phase", "timed target IDs are empty"),
        (
            {
                "target_unit_instance_ids": [
                    "army-alpha:intercessor-unit-1",
                    "army-alpha:intercessor-unit-1",
                ]
            },
            "end_phase",
            "timed target IDs are duplicated",
        ),
    ],
)
def test_fight_unit_selected_timed_effects_reject_invalid_payloads(
    effect_payload: JsonValue,
    expiration: str,
    expected_error: str,
) -> None:
    state, _decisions, result, activation, _grant = _fight_grant_resolution_fixture()
    grant = _timed_fight_grant(effect_payload=effect_payload, expiration=expiration)

    with pytest.raises(GameLifecycleError, match=expected_error):
        fight_unit_selected_grant_resolution.validate_fight_unit_selected_grant_effects(
            state=state,
            result=result,
            activation=activation,
            grant=grant,
        )


def test_fight_unit_selected_timed_effect_resolution_rejects_unknown_expiration() -> None:
    state, _decisions, _result, _activation, _grant = _fight_grant_resolution_fixture()

    with pytest.raises(GameLifecycleError, match="timed effect expiration is unsupported"):
        fight_unit_selected_grant_resolution._timed_effect_expiration(  # pyright: ignore[reportPrivateUsage]
            state=state,
            expiration="unsupported",
        )


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("not_object", "must be an object"),
        ("wrong_payload_kind", "effect kind is unsupported"),
        ("missing_effect", "requires an effect object"),
        ("missing_rule_effect_kind", "requires effect kind"),
        ("unknown_rule_effect_kind", "effect kind is unsupported"),
        ("wrong_rule_effect_kind", "RuleIR effect is unsupported"),
        ("missing_target", "must target this model"),
        ("wrong_target", "must target this model"),
        ("parameters_not_list", "parameters must be a list"),
        ("parameter_not_object", "parameter must be an object"),
        ("parameter_missing_key", "parameter requires key"),
        ("duplicate_parameter", "parameters are duplicated"),
        ("wrong_dice_quantity", "require one die"),
        ("wrong_dice_sides", "require a D3"),
        ("negative_modifier", "modifier must be non-negative"),
        ("missing_source_id", "requires source_id"),
        ("same_execution_and_source", "must be distinct"),
        ("missing_execution_context", "requires execution context"),
    ],
)
def test_generic_self_mortal_wound_effect_payload_fails_closed(
    case: str,
    expected_error: str,
) -> None:
    value: JsonValue = _generic_self_mortal_wound_effect_payload()
    if case == "not_object":
        value = []
    else:
        payload = cast(dict[str, JsonValue], value)
        effect = cast(dict[str, JsonValue], payload["effect"])
        parameters = cast(list[JsonValue], effect["parameters"])
        if case == "wrong_payload_kind":
            payload["effect_kind"] = "unsupported"
        elif case == "missing_effect":
            payload["effect"] = None
        elif case == "missing_rule_effect_kind":
            effect["kind"] = None
        elif case == "unknown_rule_effect_kind":
            effect["kind"] = "unsupported"
        elif case == "wrong_rule_effect_kind":
            effect["kind"] = RuleEffectKind.GRANT_ABILITY.value
        elif case == "missing_target":
            payload["target"] = None
        elif case == "wrong_target":
            payload["target"] = {"kind": RuleTargetKind.THIS_UNIT.value}
        elif case == "parameters_not_list":
            effect["parameters"] = None
        elif case == "parameter_not_object":
            effect["parameters"] = ["invalid"]
        elif case == "parameter_missing_key":
            effect["parameters"] = [{"value": 1}]
        elif case == "duplicate_parameter":
            parameters.append({"key": "mortal_wounds_dice_quantity", "value": 1})
        elif case == "wrong_dice_quantity":
            _replace_effect_parameter(parameters, key="mortal_wounds_dice_quantity", value=2)
        elif case == "wrong_dice_sides":
            _replace_effect_parameter(parameters, key="mortal_wounds_dice_sides", value=6)
        elif case == "negative_modifier":
            _replace_effect_parameter(parameters, key="mortal_wounds_modifier", value=-1)
        elif case == "missing_source_id":
            payload["source_id"] = None
        elif case == "same_execution_and_source":
            payload["execution_id"] = payload["source_id"]
        elif case == "missing_execution_context":
            payload["context"] = None
        else:
            raise AssertionError(f"Unhandled test case: {case}")

    with pytest.raises(GameLifecycleError, match=expected_error):
        fight_unit_selected_grant_resolution._generic_self_mortal_wound_effect_payload(  # pyright: ignore[reportPrivateUsage]
            value
        )


def test_generic_self_mortal_wound_effect_payload_accepts_canonical_payload() -> None:
    payload = _generic_self_mortal_wound_effect_payload()

    assert (
        fight_unit_selected_grant_resolution._generic_self_mortal_wound_effect_payload(  # pyright: ignore[reportPrivateUsage]
            payload
        )
        == payload
    )


@pytest.mark.parametrize(
    ("value", "expected_error"),
    [
        ([], "source context must be an object"),
        ({}, "source kind drift"),
        (
            {
                "source_kind": (
                    fight_unit_selected_grant_resolution.SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND
                )
            },
            "source phase drift",
        ),
    ],
)
def test_self_mortal_wound_source_context_fails_closed_early(
    value: JsonValue,
    expected_error: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=expected_error):
        fight_unit_selected_grant_resolution._self_mortal_wound_source_context(  # pyright: ignore[reportPrivateUsage]
            value
        )


def test_self_mortal_wound_nested_payload_validators_fail_closed() -> None:
    with pytest.raises(GameLifecycleError, match="D3 result must be an object"):
        fight_unit_selected_grant_resolution._self_mortal_wound_d3_result(  # pyright: ignore[reportPrivateUsage]
            None
        )
    with pytest.raises(GameLifecycleError, match="D3 result is invalid"):
        fight_unit_selected_grant_resolution._self_mortal_wound_d3_result(  # pyright: ignore[reportPrivateUsage]
            {}
        )
    with pytest.raises(GameLifecycleError, match="destruction evidence must be an object"):
        fight_unit_selected_grant_resolution._self_mortal_wound_destruction_evidence(  # pyright: ignore[reportPrivateUsage]
            {}
        )
    with pytest.raises(GameLifecycleError, match="progress is invalid"):
        fight_unit_selected_grant_resolution._validate_self_mortal_wound_progress(  # pyright: ignore[reportPrivateUsage]
            object()  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("invalid_identifier", "hook_id"),
        ("execution_identity", "execution identity drift"),
        ("bearer_identity", "bearer identity drift"),
        ("wound_count", "invalid wound count"),
        ("d3_actor", "D3 actor drift"),
        ("d3_roll_type", "D3 roll type drift"),
        ("d3_result", "D3 result drift"),
    ],
)
def test_self_mortal_wound_source_context_rejects_identity_and_roll_drift(
    case: str,
    expected_error: str,
) -> None:
    progress, context, _evidence = _self_mortal_wound_progress_fixture()
    value = cast(dict[str, JsonValue], json.loads(json.dumps(context)))
    if case == "invalid_identifier":
        value["hook_id"] = ""
    elif case == "execution_identity":
        value["source_rule_id"] = "phase12a:drifted-execution"
    elif case == "bearer_identity":
        value["source_model_instance_id"] = "phase12a:drifted-model"
    elif case == "wound_count":
        value["mortal_wounds"] = 0
    else:
        d3_result = cast(dict[str, JsonValue], value["d3_result"])
        source_d6_result = cast(dict[str, JsonValue], d3_result["source_d6_result"])
        spec = cast(dict[str, JsonValue], source_d6_result["spec"])
        if case == "d3_actor":
            spec["actor_id"] = "phase12a:drifted-model"
        elif case == "d3_roll_type":
            spec["roll_type"] = "phase12a.drifted-roll-type"
        elif case == "d3_result":
            value["mortal_wounds"] = progress.mortal_wounds + 1
        else:
            raise AssertionError(f"Unhandled test case: {case}")

    with pytest.raises(GameLifecycleError, match=expected_error):
        fight_unit_selected_grant_resolution._self_mortal_wound_source_context(  # pyright: ignore[reportPrivateUsage]
            value
        )


def test_self_mortal_wound_source_context_accepts_canonical_payload() -> None:
    _progress, context, _evidence = _self_mortal_wound_progress_fixture()

    assert (
        fight_unit_selected_grant_resolution._self_mortal_wound_source_context(  # pyright: ignore[reportPrivateUsage]
            context
        )
        == context
    )


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("source_rule", "progress source rule drift"),
        ("target_unit", "progress target unit drift"),
        ("defender", "progress defender drift"),
        ("wound_count", "progress wound count drift"),
        ("spill_over", "must not spill over"),
        ("bearer_priority", "bearer priority drift"),
        ("destruction_evidence", "must defer destruction evidence"),
    ],
)
def test_self_mortal_wound_progress_rejects_routing_drift(
    case: str,
    expected_error: str,
) -> None:
    progress, _context, evidence = _self_mortal_wound_progress_fixture()
    if case == "source_rule":
        value = replace(progress, source_rule_id="phase12a:drifted-rule")
    elif case == "target_unit":
        value = replace(progress, target_unit_instance_id="phase12a:drifted-unit")
    elif case == "defender":
        value = replace(progress, defender_player_id="player-b")
    elif case == "wound_count":
        value = replace(
            progress,
            mortal_wounds=progress.mortal_wounds + 1,
            remaining_mortal_wounds=progress.remaining_mortal_wounds + 1,
        )
    elif case == "spill_over":
        value = replace(progress, spill_over=True)
    elif case == "bearer_priority":
        value = replace(progress, priority_model_ids=("phase12a:drifted-model",))
    elif case == "destruction_evidence":
        value = replace(progress, destruction_evidence=evidence)
    else:
        raise AssertionError(f"Unhandled test case: {case}")

    with pytest.raises(GameLifecycleError, match=expected_error):
        fight_unit_selected_grant_resolution._validate_self_mortal_wound_progress(  # pyright: ignore[reportPrivateUsage]
            value
        )


@pytest.mark.parametrize(
    ("case", "expected_error"),
    [
        ("player", "destruction player drift"),
        ("unit", "destruction unit drift"),
        ("model", "destruction model drift"),
        ("source_kind", "destruction source kind drift"),
        ("action_phase", "destruction action phase drift"),
        ("parent_phase", "destruction parent phase drift"),
        ("source_step", "destruction step drift"),
    ],
)
def test_self_mortal_wound_progress_rejects_destruction_evidence_drift(
    case: str,
    expected_error: str,
) -> None:
    progress, context, _evidence = _self_mortal_wound_progress_fixture()
    value = cast(dict[str, JsonValue], json.loads(json.dumps(context)))
    evidence = cast(dict[str, JsonValue], value["mortal_wound_destruction_evidence"])
    attribution = cast(dict[str, JsonValue], evidence["destruction_attribution"])
    provenance = cast(dict[str, JsonValue], attribution["destruction_provenance"])
    if case == "player":
        attribution["destroying_player_id"] = "player-b"
    elif case == "unit":
        attribution["source_rules_unit_instance_id"] = "phase12a:drifted-unit"
    elif case == "model":
        attribution["source_model_instance_id"] = "phase12a:drifted-model"
    elif case == "source_kind":
        provenance["destruction_source_kind"] = DestructionSourceKind.HAZARDOUS.value
    elif case == "action_phase":
        evidence["action_phase"] = BattlePhase.SHOOTING.value
    elif case == "parent_phase":
        evidence["parent_battle_phase"] = BattlePhase.SHOOTING.value
    elif case == "source_step":
        evidence["source_step"] = "phase12a_drifted_step"
    else:
        raise AssertionError(f"Unhandled test case: {case}")
    drifted_progress = replace(progress, source_context=value)

    with pytest.raises(GameLifecycleError, match=expected_error):
        fight_unit_selected_grant_resolution._validate_self_mortal_wound_progress(  # pyright: ignore[reportPrivateUsage]
            drifted_progress
        )


def test_self_mortal_wound_progress_accepts_canonical_routing_context() -> None:
    progress, _context, _evidence = _self_mortal_wound_progress_fixture()

    fight_unit_selected_grant_resolution._validate_self_mortal_wound_progress(  # pyright: ignore[reportPrivateUsage]
        progress
    )


def test_applied_damage_attached_split_context_is_fail_closed() -> None:
    assert defer_attached_split_from_rule_destruction_context({}) is False
    with pytest.raises(
        GameLifecycleError,
        match="split deferral requires applied mortal-wound destruction",
    ):
        defer_attached_split_from_rule_destruction_context({DEFER_ATTACHED_SPLIT_FIELD: True})
    with pytest.raises(GameLifecycleError, match="split context is invalid"):
        defer_attached_split_from_rule_destruction_context(
            {
                "completion_kind": RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND,
            }
        )
    assert (
        defer_attached_split_from_rule_destruction_context(
            {
                "completion_kind": RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND,
                DEFER_ATTACHED_SPLIT_FIELD: True,
            }
        )
        is True
    )


def test_rule_destruction_source_liabilities_reject_missing_and_wrong_target_effects() -> None:
    state = _battle_state(unit_selection_ids=("intercessor-unit-1",))
    alpha_unit = state.army_definitions[0].units[0]
    enemy_unit = state.army_definitions[1].units[0]

    with pytest.raises(GameLifecycleError, match="liability effect is missing"):
        consume_rule_destruction_source_liabilities(
            state=state,
            source_effect_ids=("phase12a:missing-liability",),
            rules_unit_instance_id=alpha_unit.unit_instance_id,
        )

    liability = _record_rule_destruction_liability(
        state=state,
        effect_id="phase12a:wrong-target-liability",
        target_unit_instance_id=alpha_unit.unit_instance_id,
        owner_player_id="player-a",
    )
    with pytest.raises(GameLifecycleError, match="liability target drift"):
        consume_rule_destruction_source_liabilities(
            state=state,
            source_effect_ids=(liability.effect_id,),
            rules_unit_instance_id=enemy_unit.unit_instance_id,
        )


def test_rule_destruction_source_liability_preserves_other_targets() -> None:
    state = _battle_state(unit_selection_ids=("intercessor-unit-1",))
    alpha_unit = state.army_definitions[0].units[0]
    enemy_unit = state.army_definitions[1].units[0]
    effect = _persisting_effect(
        effect_id="phase12a:multi-target-liability",
        target_unit_instance_ids=(alpha_unit.unit_instance_id, enemy_unit.unit_instance_id),
        expiration=EffectExpiration.end_of_battle(),
    )
    state.record_persisting_effect(effect)

    consume_rule_destruction_source_liabilities(
        state=state,
        source_effect_ids=(effect.effect_id,),
        rules_unit_instance_id=alpha_unit.unit_instance_id,
    )

    remaining = next(
        item for item in state.persisting_effects if item.effect_id == effect.effect_id
    )
    assert remaining.target_unit_instance_ids == (enemy_unit.unit_instance_id,)


def test_rule_model_destruction_result_requires_typed_completion_artifacts() -> None:
    with pytest.raises(GameLifecycleError, match="removal record is invalid"):
        rule_model_destruction.RuleModelDestructionResult(
            model_destroyed_event_id=None,
            removal_record=cast(ModelRemovalRecord, object()),
            transition_batch=None,
            status=None,
        )
    with pytest.raises(GameLifecycleError, match="transition batch is invalid"):
        rule_model_destruction.RuleModelDestructionResult(
            model_destroyed_event_id=None,
            removal_record=None,
            transition_batch=cast(BattlefieldTransitionBatch, object()),
            status=None,
        )
    with pytest.raises(GameLifecycleError, match="status must be LifecycleStatus"):
        rule_model_destruction.RuleModelDestructionResult(
            model_destroyed_event_id=None,
            removal_record=None,
            transition_batch=None,
            status=cast(LifecycleStatus, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires removal artifacts"):
        rule_model_destruction.RuleModelDestructionResult(
            model_destroyed_event_id=None,
            removal_record=None,
            transition_batch=None,
            status=None,
        )


def test_rule_model_destruction_payload_scalar_validators_fail_closed() -> None:
    assert (
        rule_model_destruction._payload_string(  # pyright: ignore[reportPrivateUsage]
            {"value": "identifier"}, "value"
        )
        == "identifier"
    )
    with pytest.raises(GameLifecycleError, match="must be a string"):
        rule_model_destruction._payload_string({}, "value")  # pyright: ignore[reportPrivateUsage]

    assert (
        rule_model_destruction._optional_payload_string(  # pyright: ignore[reportPrivateUsage]
            {}, "value"
        )
        is None
    )
    assert (
        rule_model_destruction._optional_payload_string(  # pyright: ignore[reportPrivateUsage]
            {"value": "identifier"}, "value"
        )
        == "identifier"
    )
    with pytest.raises(GameLifecycleError, match="value must be a string"):
        rule_model_destruction._optional_payload_string(  # pyright: ignore[reportPrivateUsage]
            {"value": 1}, "value"
        )

    assert (
        rule_model_destruction._payload_d6_target(  # pyright: ignore[reportPrivateUsage]
            {"value": 2}, "value"
        )
        == 2
    )
    assert (
        rule_model_destruction._payload_d6_target(  # pyright: ignore[reportPrivateUsage]
            {"value": 6}, "value"
        )
        == 6
    )
    with pytest.raises(GameLifecycleError, match="must be a D6 target"):
        rule_model_destruction._payload_d6_target(  # pyright: ignore[reportPrivateUsage]
            {"value": 1}, "value"
        )

    assert (
        rule_model_destruction._payload_positive_int(  # pyright: ignore[reportPrivateUsage]
            {"value": 1}, "value"
        )
        == 1
    )
    with pytest.raises(GameLifecycleError, match="must be a positive integer"):
        rule_model_destruction._payload_positive_int(  # pyright: ignore[reportPrivateUsage]
            {"value": 0}, "value"
        )

    assert (
        rule_model_destruction._payload_positive_number(  # pyright: ignore[reportPrivateUsage]
            {"value": 1}, "value"
        )
        == 1.0
    )
    assert (
        rule_model_destruction._payload_positive_number(  # pyright: ignore[reportPrivateUsage]
            {"value": 1.5}, "value"
        )
        == 1.5
    )
    with pytest.raises(GameLifecycleError, match="must be positive"):
        rule_model_destruction._payload_positive_number(  # pyright: ignore[reportPrivateUsage]
            {"value": True}, "value"
        )
    with pytest.raises(GameLifecycleError, match="must be positive"):
        rule_model_destruction._payload_positive_number(  # pyright: ignore[reportPrivateUsage]
            {"value": 0}, "value"
        )


def test_rule_model_destruction_payload_collection_validators_fail_closed() -> None:
    payload_object: dict[str, JsonValue] = {"nested": {"value": 1}}
    assert rule_model_destruction._payload_object_value(  # pyright: ignore[reportPrivateUsage]
        payload_object, "nested"
    ) == {"value": 1}
    with pytest.raises(GameLifecycleError, match="must be an object"):
        rule_model_destruction._payload_object_value(  # pyright: ignore[reportPrivateUsage]
            {"nested": []}, "nested"
        )

    assert rule_model_destruction._payload_identifier_list(  # pyright: ignore[reportPrivateUsage]
        {"values": ["value-b", "value-a"]}, "values"
    ) == ("value-b", "value-a")
    with pytest.raises(GameLifecycleError, match="must be a list"):
        rule_model_destruction._payload_identifier_list(  # pyright: ignore[reportPrivateUsage]
            {"values": cast(JsonValue, ())}, "values"
        )
    with pytest.raises(GameLifecycleError, match="contains duplicates"):
        rule_model_destruction._payload_identifier_list(  # pyright: ignore[reportPrivateUsage]
            {"values": ["duplicate", "duplicate"]}, "values"
        )

    assert (
        rule_model_destruction._payload_source_tuple(  # pyright: ignore[reportPrivateUsage]
            {"sources": []}, "sources"
        )
        == ()
    )
    with pytest.raises(GameLifecycleError, match="must be a source list"):
        rule_model_destruction._payload_source_tuple(  # pyright: ignore[reportPrivateUsage]
            {"sources": ["invalid"]}, "sources"
        )

    assert rule_model_destruction._validate_identifier_tuple(  # pyright: ignore[reportPrivateUsage]
        "values", ("value-b", "value-a"), min_length=2
    ) == ("value-a", "value-b")
    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        rule_model_destruction._validate_identifier_tuple(  # pyright: ignore[reportPrivateUsage]
            "values", [], min_length=1
        )
    with pytest.raises(GameLifecycleError, match="is invalid"):
        rule_model_destruction._validate_identifier_tuple(  # pyright: ignore[reportPrivateUsage]
            "values", ("duplicate", "duplicate"), min_length=1
        )


def test_rule_model_destruction_reaction_descriptor_and_host_helpers() -> None:
    fight_source = DestructionReactionSource(
        source_id="phase12a:fight-on-death",
        reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
        source_rule_id="phase12a:fight-on-death",
    )
    shoot_source = DestructionReactionSource(
        source_id="phase12a:shoot-on-death",
        reaction_kind=DestructionReactionKind.SHOOT_ON_DEATH,
        source_rule_id="phase12a:shoot-on-death",
    )
    deadly_demise_source = _deadly_demise_source(
        source_id="phase12a:deadly-demise",
        mortal_wounds=1,
    )
    assert rule_model_destruction._reaction_action_host(None) is None  # pyright: ignore[reportPrivateUsage]
    assert rule_model_destruction._reaction_action_host(shoot_source) == "shooting"  # pyright: ignore[reportPrivateUsage]
    assert rule_model_destruction._reaction_action_host(fight_source) == "fight"  # pyright: ignore[reportPrivateUsage]
    assert rule_model_destruction._reaction_action_host(deadly_demise_source) == "explosion"  # pyright: ignore[reportPrivateUsage]

    no_trigger = replace(fight_source, payload={"effect_kind": "fight_on_death"})
    assert rule_model_destruction._trigger_descriptor(fight_source) is None  # pyright: ignore[reportPrivateUsage]
    assert rule_model_destruction._trigger_descriptor(no_trigger) is None  # pyright: ignore[reportPrivateUsage]
    trigger_payload: dict[str, JsonValue] = {"trigger_roll_threshold": 4}
    with_trigger = replace(fight_source, payload=trigger_payload)
    assert rule_model_destruction._trigger_descriptor(with_trigger) == trigger_payload  # pyright: ignore[reportPrivateUsage]
    invalid = replace(fight_source, payload=[])
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        rule_model_destruction._trigger_descriptor(invalid)  # pyright: ignore[reportPrivateUsage]


def test_applied_mortal_wound_destruction_entrypoint_rejects_invalid_types() -> None:
    state, decisions, damage, evidence = _applied_destruction_type_guard_fixture()

    with pytest.raises(GameLifecycleError, match="requires GameState"):
        _continue_applied_destruction_type_guard(
            state=cast(GameState, object()),
            decisions=decisions,
            damage=damage,
            evidence=evidence,
            defer_attached_split=False,
        )
    with pytest.raises(GameLifecycleError, match="requires DecisionController"):
        _continue_applied_destruction_type_guard(
            state=state,
            decisions=cast(DecisionController, object()),
            damage=damage,
            evidence=evidence,
            defer_attached_split=False,
        )
    with pytest.raises(GameLifecycleError, match="requires DamageApplication"):
        _continue_applied_destruction_type_guard(
            state=state,
            decisions=decisions,
            damage=cast(DamageApplication, object()),
            evidence=evidence,
            defer_attached_split=False,
        )
    with pytest.raises(GameLifecycleError, match="requires typed destruction evidence"):
        _continue_applied_destruction_type_guard(
            state=state,
            decisions=decisions,
            damage=damage,
            evidence=cast(MortalWoundDestructionEvidence, object()),
            defer_attached_split=False,
        )
    with pytest.raises(GameLifecycleError, match="split deferral must be a bool"):
        _continue_applied_destruction_type_guard(
            state=state,
            decisions=decisions,
            damage=damage,
            evidence=evidence,
            defer_attached_split=cast(bool, 1),
        )


def test_applied_mortal_wound_destruction_context_and_damage_validation_fail_closed() -> None:
    state, _decisions, damage, _evidence = _applied_destruction_type_guard_fixture()
    with pytest.raises(GameLifecycleError, match="damage_application must be an object"):
        rule_model_destruction_applied_damage.validate_applied_damage_rule_destruction_context(
            state=state,
            context={
                "completion_kind": RULE_MODEL_DESTRUCTION_APPLIED_DAMAGE_COMPLETION_KIND,
                DEFER_ATTACHED_SPLIT_FIELD: False,
            },
        )
    with pytest.raises(GameLifecycleError, match="requires mortal damage"):
        rule_model_destruction_applied_damage._validate_destroyed_damage_matches_state(  # pyright: ignore[reportPrivateUsage]
            state=state,
            damage_application=replace(damage, damage_kind=DamageKind.NORMAL),
        )
    with pytest.raises(GameLifecycleError, match="requires lethal damage"):
        rule_model_destruction_applied_damage._validate_destroyed_damage_matches_state(  # pyright: ignore[reportPrivateUsage]
            state=state,
            damage_application=replace(
                damage,
                starting_wounds_remaining=2,
                final_wounds_remaining=1,
                destroyed=False,
            ),
        )
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        rule_model_destruction_applied_damage._object_payload(  # pyright: ignore[reportPrivateUsage]
            [], "payload"
        )


def _fight_grant_resolution_fixture() -> tuple[
    GameState,
    DecisionController,
    DecisionResult,
    FightActivationSelection,
    FightUnitSelectedGrant,
]:
    decisions = DecisionController()
    state = _battle_state(
        unit_selection_ids=("intercessor-unit-1",),
        decisions=decisions,
    )
    unit = state.army_definitions[0].units[0]
    result = DecisionResult(
        result_id="fight-grant-result",
        request_id="fight-grant-request",
        decision_type="fight-grant-test",
        actor_id="player-a",
        selected_option_id="fight-grant-option",
        payload=None,
    )
    activation = FightActivationSelection(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
        ordering_band=FightOrderingBandKind.REMAINING_COMBATS,
        fight_type=FightTypeKind.NORMAL,
        eligibility_reasons=(FightEligibilityKind.CURRENTLY_ENGAGED,),
        request_id="fight-activation-request",
        result_id="fight-activation-result",
    )
    grant = FightUnitSelectedGrant(
        hook_id="fight-grant-hook",
        source_id="fight-grant-source",
        label="fight-grant-label",
        immediate_effect_payload={},
    )
    return state, decisions, result, activation, grant


def _applied_destruction_type_guard_fixture() -> tuple[
    GameState,
    DecisionController,
    DamageApplication,
    MortalWoundDestructionEvidence,
]:
    decisions = DecisionController()
    state = _battle_state(
        unit_selection_ids=("intercessor-unit-1",),
        decisions=decisions,
    )
    _set_current_battle_phase(state, BattlePhase.FIGHT)
    unit = state.army_definitions[0].units[0]
    model = unit.own_models[0]
    damage = DamageApplication(
        target_unit_instance_id=unit.unit_instance_id,
        model_instance_id=model.model_instance_id,
        damage_kind=DamageKind.MORTAL,
        requested_damage=1,
        wounds_lost=1,
        excess_damage_lost=0,
        starting_wounds_remaining=1,
        final_wounds_remaining=0,
        destroyed=True,
    )
    evidence = MortalWoundDestructionEvidence.for_non_attack_state(
        state=state,
        destroying_player_id="player-a",
        source_rules_unit_instance_id=unit.unit_instance_id,
        source_model_instance_id=model.model_instance_id,
        destruction_source_kind=DestructionSourceKind.ABILITY,
        action_phase=BattlePhase.FIGHT,
        source_step="phase12a_applied_destruction_type_guard",
    )
    return state, decisions, damage, evidence


def _continue_applied_destruction_type_guard(
    *,
    state: GameState,
    decisions: DecisionController,
    damage: DamageApplication,
    evidence: MortalWoundDestructionEvidence,
    defer_attached_split: bool,
) -> object:
    return continue_applied_mortal_wound_destruction_with_rule_reactions(
        state=state,
        decisions=decisions,
        damage_application=damage,
        rules_unit_instance_id="army-alpha:intercessor-unit-1",
        source_rule_id="phase12a:applied-destruction",
        source_result_id="phase12a:applied-destruction-result",
        completion_event_type="phase12a_applied_destruction_completed",
        completion_event_payload={},
        destruction_evidence=evidence,
        defer_attached_split_until_fight_activation_completion=defer_attached_split,
    )


def _timed_fight_grant(*, effect_payload: JsonValue, expiration: str) -> FightUnitSelectedGrant:
    return FightUnitSelectedGrant(
        hook_id="timed-fight-grant-hook",
        source_id="timed-fight-grant-source",
        label="timed-fight-grant-label",
        timed_effects=(
            FightUnitSelectedTimedEffect(
                effect_payload=effect_payload,
                expiration=expiration,
            ),
        ),
    )


def _generic_self_mortal_wound_effect_payload(
    *,
    source_model_instance_id: str = "phase12a:self-mortal-model",
) -> dict[str, JsonValue]:
    return {
        "effect_kind": GENERIC_RULE_EFFECT_KIND,
        "source_id": "phase12a:self-mortal-rule-ir",
        "execution_id": "phase12a:self-mortal-execution",
        "target": {"kind": RuleTargetKind.THIS_MODEL.value},
        "effect": {
            "kind": RuleEffectKind.INFLICT_MORTAL_WOUNDS.value,
            "parameters": [
                {"key": "mortal_wounds_dice_quantity", "value": 1},
                {"key": "mortal_wounds_dice_sides", "value": 3},
                {"key": "mortal_wounds_modifier", "value": 1},
            ],
        },
        "context": {"source_model_instance_id": source_model_instance_id},
    }


def _self_mortal_wound_progress_fixture() -> tuple[
    MortalWoundApplicationProgress,
    dict[str, JsonValue],
    MortalWoundDestructionEvidence,
]:
    state, decisions, _damage, _type_guard_evidence = _applied_destruction_type_guard_fixture()
    unit = state.army_definitions[0].units[0]
    model = unit.own_models[0]
    immediate_payload = _generic_self_mortal_wound_effect_payload(
        source_model_instance_id=model.model_instance_id
    )
    d3_result = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
    ).roll_d3_fixed(
        reason="Phase 12A self-mortal-wound context fixture",
        roll_type=(
            fight_unit_selected_grant_resolution.SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_D3_ROLL_TYPE
        ),
        source_d6_value=5,
        actor_id=model.model_instance_id,
    )
    mortal_wounds = d3_result.value + 1
    evidence = MortalWoundDestructionEvidence.for_non_attack_state(
        state=state,
        destroying_player_id="player-a",
        source_rules_unit_instance_id=unit.unit_instance_id,
        source_model_instance_id=model.model_instance_id,
        destruction_source_kind=DestructionSourceKind.ABILITY,
        action_phase=BattlePhase.FIGHT,
        source_step="selected_to_fight_self_mortal_wounds",
    )
    source_context: dict[str, JsonValue] = {
        "source_kind": (
            fight_unit_selected_grant_resolution.SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND
        ),
        "phase": BattlePhase.FIGHT.value,
        "source_rule_id": "phase12a:self-mortal-execution",
        "hook_id": "phase12a:self-mortal-hook",
        "label": "Phase 12A self mortal wounds",
        "player_id": "player-a",
        "unit_instance_id": unit.unit_instance_id,
        "source_model_instance_id": model.model_instance_id,
        "activation_request_id": "phase12a:activation-request",
        "activation_result_id": "phase12a:activation-result",
        "grant_request_id": "phase12a:grant-request",
        "grant_result_id": "phase12a:grant-result",
        "immediate_effect_payload": immediate_payload,
        "d3_result": cast(JsonValue, d3_result.to_payload()),
        "mortal_wounds": mortal_wounds,
        "mortal_wound_destruction_evidence": cast(JsonValue, evidence.to_payload()),
    }
    progress = MortalWoundApplicationProgress.start(
        application_id="phase12a:self-mortal-application",
        source_rule_id="phase12a:self-mortal-execution",
        source_context=source_context,
        target_unit_instance_id=unit.unit_instance_id,
        defender_player_id="player-a",
        mortal_wounds=mortal_wounds,
        spill_over=False,
        destruction_evidence=None,
        priority_model_ids=(model.model_instance_id,),
    )
    return progress, source_context, evidence


def _replace_effect_parameter(
    parameters: list[JsonValue],
    *,
    key: str,
    value: JsonValue,
) -> None:
    for parameter in parameters:
        if isinstance(parameter, dict) and parameter.get("key") == key:
            parameter["value"] = value
            return
    raise AssertionError(f"Missing effect parameter: {key}")


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


def _battle_state(
    *,
    unit_selection_ids: tuple[str, ...],
    decisions: DecisionController | None = None,
) -> GameState:
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
    enter_battle_for_fixture(state, decisions=decisions)
    assert state.stage is GameLifecycleStage.BATTLE
    return state


def _battle_lifecycle(*, unit_selection_ids: tuple[str, ...]) -> GameLifecycle:
    config = _config(unit_selection_ids=unit_selection_ids)
    decisions = DecisionController()
    state = _battle_state(unit_selection_ids=unit_selection_ids, decisions=decisions)
    return GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
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
        force_disposition_id="take-and-hold",
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
                attacker_force_disposition_id="take-and-hold",
                defender_player_id="player-b",
                defender_force_disposition_id="purge-the-foe",
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
            attacker_force_disposition_id="take-and-hold",
            defender_player_id="player-b",
            defender_force_disposition_id="purge-the-foe",
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
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
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
