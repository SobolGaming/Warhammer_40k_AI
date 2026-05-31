from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec, DiceRollState
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.command_points import (
    CommandPointGainStatus,
    CommandPointSourceKind,
    CommandStepState,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionOption,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    TacticalSecondaryDraw,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    PlacementProposalPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveState,
    ReserveStatus,
)
from warhammer40k_core.engine.stratagem_catalog import tenth_edition_stratagem_catalog_records
from warhammer40k_core.engine.stratagems import (
    COMMAND_REROLL_DICE_CONTEXT_KEY,
    STRATAGEM_DECISION_TYPE,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    StratagemCatalogRecord,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetProposal,
    StratagemTargetProposalPayload,
    create_stratagem_use_decision_request,
    request_stratagem_target_proposal,
    request_stratagem_use,
    stratagem_use_options,
)
from warhammer40k_core.engine.timing_windows import (
    ReactionWindow,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack


def test_command_reroll_source_handler_resolves_via_restored_lifecycle() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=1)
    command_reroll = _source_stratagem_record("command-reroll")
    assert "advance_roll" in command_reroll.definition.eligible_roll_types
    assert "desperate_escape_roll" in command_reroll.definition.eligible_roll_types
    assert "battle_shock_roll" not in command_reroll.definition.eligible_roll_types
    roll_state = _roll_command_reroll_candidate(lifecycle, actor_id="player-a")
    trigger_payload = validate_json_value(
        {COMMAND_REROLL_DICE_CONTEXT_KEY: validate_json_value(roll_state.to_payload())}
    )
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=trigger_payload,
    )

    waiting = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=(command_reroll,),
        context=context,
    )
    request = _decision_request(waiting)
    restored = GameLifecycle.from_payload(_lifecycle_payload_copy(lifecycle))
    restored_request = _decision_request(restored.advance_until_decision_or_terminal())

    restored.submit_decision(
        DecisionResult.for_request(
            result_id="phase12c-command-reroll",
            request=restored_request,
            selected_option_id=request.options[0].option_id,
        )
    )
    restored_state = _state(restored)

    assert restored_state.command_point_total("player-a") == 0
    assert len(restored_state.stratagem_use_records) == 1
    assert restored_state.stratagem_use_records[0].handler_id == "core:command-reroll"
    assert _has_event(restored.decision_controller, "dice_reroll_resolved")
    assert (
        _last_event_payload(restored.decision_controller, "command_reroll_resolved")[
            "stratagem_use"
        ]
        == restored_state.stratagem_use_records[0].to_payload()
    )
    assert "<" not in json.dumps(restored.to_payload(), sort_keys=True)


def test_command_reroll_source_eligibility_rejects_unlisted_roll_type_before_queue_pop() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=1)
    command_reroll = _source_stratagem_record("command-reroll")
    roll_state = _roll_command_reroll_candidate(
        lifecycle,
        actor_id="player-a",
        roll_type="validation_roll",
    )
    trigger_payload = validate_json_value(
        {COMMAND_REROLL_DICE_CONTEXT_KEY: validate_json_value(roll_state.to_payload())}
    )
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=trigger_payload,
    )

    assert (
        stratagem_use_options(
            state=state,
            catalog_records=(command_reroll,),
            context=context,
        )
        == ()
    )
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(
            _handcrafted_stratagem_option(
                record=command_reroll,
                context=context,
                binding=StratagemTargetBinding.none(),
            ),
        ),
    )
    lifecycle.decision_controller.request_decision(request)

    rejected = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12c-command-reroll-ineligible-roll",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
    )

    assert rejected.status_kind is LifecycleStatusKind.INVALID
    assert rejected.payload == {"invalid_reason": "ineligible_dice_roll_type"}
    assert state.command_point_total("player-a") == 1
    assert state.stratagem_use_records == []
    assert lifecycle.decision_controller.queue.pending_requests == (request,)


def test_command_reroll_rejects_opponent_roll_actor_drift_before_queue_pop() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=1)
    command_reroll = _source_stratagem_record("command-reroll")
    roll_state = _roll_command_reroll_candidate(lifecycle, actor_id="player-b")
    trigger_payload = validate_json_value(
        {COMMAND_REROLL_DICE_CONTEXT_KEY: validate_json_value(roll_state.to_payload())}
    )
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=trigger_payload,
    )

    assert (
        stratagem_use_options(
            state=state,
            catalog_records=(command_reroll,),
            context=context,
        )
        == ()
    )
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(
            _handcrafted_stratagem_option(
                record=command_reroll,
                context=context,
                binding=StratagemTargetBinding.none(),
            ),
        ),
    )
    lifecycle.decision_controller.request_decision(request)

    rejected = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12c-command-reroll-actor-drift",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
    )

    assert rejected.status_kind is LifecycleStatusKind.INVALID
    assert rejected.payload == {"invalid_reason": "dice_roll_actor_drift"}
    assert state.command_point_total("player-a") == 1
    assert state.stratagem_use_records == []
    assert lifecycle.decision_controller.queue.pending_requests == (request,)


def test_command_reroll_allows_tenth_edition_desperate_escape_roll_for_actor() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=1)
    command_reroll = _source_stratagem_record("command-reroll")
    roll_state = _roll_command_reroll_candidate(
        lifecycle,
        actor_id="player-a",
        roll_type="desperate_escape_roll",
    )
    trigger_payload = validate_json_value(
        {COMMAND_REROLL_DICE_CONTEXT_KEY: validate_json_value(roll_state.to_payload())}
    )
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=trigger_payload,
    )

    waiting = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=(command_reroll,),
        context=context,
    )
    request = _decision_request(waiting)

    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12c-command-reroll-desperate-escape",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
    )

    assert state.command_point_total("player-a") == 0
    assert len(state.stratagem_use_records) == 1
    assert _has_event(lifecycle.decision_controller, "command_reroll_resolved")


def test_command_reroll_source_handler_can_resume_reaction_parent() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-b", amount=1)
    roll_state = _roll_command_reroll_candidate(lifecycle, actor_id="player-b")
    trigger_payload = validate_json_value(
        {COMMAND_REROLL_DICE_CONTEXT_KEY: validate_json_value(roll_state.to_payload())}
    )
    context = _context(
        state=state,
        player_id="player-b",
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        trigger_payload=trigger_payload,
    )
    options = stratagem_use_options(
        state=state,
        catalog_records=(_source_stratagem_record("command-reroll"),),
        context=context,
    )
    assert len(options) == 1
    lifecycle.reaction_queue.emit_decision_request(
        state=state,
        decisions=lifecycle.decision_controller,
        reaction_window=_reaction_window(state, eligible_player_id="player-b"),
        parent_phase=BattlePhase.MOVEMENT,
        parent_step="movement_reaction_step",
        resume_token="phase12c_resume_token",
        actor_id="player-b",
        decision_type=STRATAGEM_DECISION_TYPE,
        options=options,
        payload=validate_json_value(
            {
                "stratagem_context": validate_json_value(context.to_payload()),
                "finite": True,
            }
        ),
    )

    pending = _decision_request(lifecycle.advance_until_decision_or_terminal())
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12c-reactive-command-reroll",
            request=pending,
            selected_option_id=options[0].option_id,
        )
    )

    assert state.command_point_total("player-b") == 0
    assert len(lifecycle.reaction_queue.frames) == 0
    resumed = _last_event_payload(lifecycle.decision_controller, "reaction_parent_resumed")
    assert resumed["resume_token"] == "phase12c_resume_token"
    assert _has_event(lifecycle.decision_controller, "command_reroll_resolved")


def test_insane_bravery_target_proposal_spends_cp_and_auto_passes_battle_shock() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    _record_secondary_choices(
        state,
        player_a_mode=SecondaryMissionMode.FIXED,
        player_b_mode=SecondaryMissionMode.FIXED,
    )
    _set_command_step_ready_for_battle_shock(state)
    _grant_cp(state, player_id="player-a", amount=1)
    target_unit_id = "army-alpha:intercessor-unit-1"
    _remove_first_models(state, unit_instance_id=target_unit_id, count=3)
    proposal_request = StratagemTargetProposal.for_request(
        context=_context(
            state=state,
            player_id="player-a",
            trigger_kind=TimingTriggerKind.START_PHASE,
        ),
        catalog_record=_source_stratagem_record("insane-bravery"),
    )
    waiting = request_stratagem_target_proposal(
        state=state,
        decisions=lifecycle.decision_controller,
        proposal_request=proposal_request,
    )
    request = _decision_request(waiting)
    submitted = _proposal_request_from_decision(request).with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id="player-a",
            target_unit_instance_id=target_unit_id,
        )
    )

    lifecycle.submit_decision(
        _target_proposal_result(
            request=request,
            result_id="phase12c-insane-bravery",
            proposal=submitted,
        )
    )

    assert state.command_point_total("player-a") == 0
    assert len(state.stratagem_use_records) == 1
    assert state.stratagem_use_records[0].handler_id == "core:insane-bravery"
    assert (
        _last_event_payload(lifecycle.decision_controller, "stratagem_used")["handler_id"]
        == "core:insane-bravery"
    )
    assert _has_event(lifecycle.decision_controller, "insane_bravery_auto_pass_registered")
    auto_passed = _last_event_payload(lifecycle.decision_controller, "battle_shock_test_resolved")
    result_payload = cast(dict[str, JsonValue], auto_passed["battle_shock_result"])
    request_payload = cast(dict[str, JsonValue], result_payload["request"])
    assert request_payload["unit_instance_id"] == target_unit_id
    assert auto_passed["auto_passed"] is True
    assert target_unit_id not in state.battle_shocked_unit_ids


def test_new_orders_finite_source_handler_discards_and_draws_replacement_card() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    _record_secondary_choices(
        state,
        player_a_mode=SecondaryMissionMode.TACTICAL,
        player_b_mode=SecondaryMissionMode.FIXED,
    )
    _set_command_step_ready_for_tactical_secondary(state)
    _grant_cp(state, player_id="player-a", amount=1)
    state.record_tactical_secondary_draw(
        TacticalSecondaryDraw(
            player_id="player-a",
            battle_round=state.battle_round,
            request_id="phase12c-initial-tactical-draw-request",
            result_id="phase12c-initial-tactical-draw",
            draw_count=state.tactical_secondary_draw_count,
        )
    )
    initial_cards = state.draw_tactical_secondary_cards(
        player_id="player-a",
        source_result_id="phase12c-initial-tactical-draw",
    )
    target_card_id = initial_cards[0].secondary_mission_id

    waiting = request_stratagem_use(
        state=state,
        decisions=lifecycle.decision_controller,
        catalog_records=(_source_stratagem_record("new-orders"),),
        context=_context(
            state=state,
            player_id="player-a",
            trigger_kind=TimingTriggerKind.START_PHASE,
        ),
    )
    request = _decision_request(waiting)
    selected_option = next(
        option
        for option in request.options
        if option.option_id.endswith(f"target:{target_card_id}")
    )

    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12c-new-orders",
            request=request,
            selected_option_id=selected_option.option_id,
        )
    )

    active_card_ids = {
        card.secondary_mission_id
        for card in state.secondary_mission_card_states
        if card.player_id == "player-a" and card.status.value == "active"
    }
    discarded_matches = [
        card
        for card in state.secondary_mission_card_states
        if card.player_id == "player-a" and card.secondary_mission_id == target_card_id
    ]
    assert len(discarded_matches) == 1
    assert discarded_matches[0].status.value == "discarded"
    assert state.command_point_total("player-a") == 0
    assert target_card_id not in active_card_ids
    assert len(active_card_ids) == state.tactical_secondary_draw_count
    assert (
        _last_event_payload(lifecycle.decision_controller, "new_orders_resolved")[
            "discarded_secondary_mission_id"
        ]
        == target_card_id
    )


def test_tactical_secondary_target_binding_requires_card_fields() -> None:
    with pytest.raises(
        ValueError,
        match=r"Tactical secondary StratagemTargetBinding requires target card fields\.",
    ):
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.TACTICAL_SECONDARY_CARD,
            target_player_id="player-a",
        )


def test_deferred_core_stratagem_descriptors_exist_and_fail_explicitly() -> None:
    deferred_ids = {
        "counter-offensive",
        "epic-challenge",
        "fire-overwatch",
        "go-to-ground",
        "grenade",
        "heroic-intervention",
        "smokescreen",
        "tank-shock",
    }
    deferred_records = tuple(
        _source_stratagem_record(stratagem_id) for stratagem_id in deferred_ids
    )
    assert {record.definition.stratagem_id for record in deferred_records} == deferred_ids
    assert all(record.availability_kind.value == "core" for record in deferred_records)
    assert all(
        record.definition.handler_id.startswith("unsupported:")
        and record.definition.target_spec.target_policy_id.startswith("unsupported:")
        for record in deferred_records
    )

    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    _grant_cp(state, player_id="player-a", amount=3)
    context = _context(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
    )
    assert (
        stratagem_use_options(
            state=state,
            catalog_records=deferred_records,
            context=context,
        )
        == ()
    )
    for record in deferred_records:
        proposal_request = StratagemTargetProposal.for_request(
            context=context,
            catalog_record=record,
        )
        unavailable = request_stratagem_target_proposal(
            state=state,
            decisions=lifecycle.decision_controller,
            proposal_request=proposal_request,
        )
        assert unavailable.status_kind is LifecycleStatusKind.UNSUPPORTED
        assert unavailable.payload == {
            "player_id": "player-a",
            "stratagem_id": record.definition.stratagem_id,
            "unavailable_reason": "unsupported_handler",
        }
    assert len(lifecycle.decision_controller.queue.pending_requests) == 0

    finite_lifecycle = _battle_lifecycle()
    finite_state = _state(finite_lifecycle)
    _set_current_battle_phase(finite_state, BattlePhase.MOVEMENT)
    _grant_cp(finite_state, player_id="player-a", amount=3)
    finite_context = _context(
        state=finite_state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
    )
    handcraft_record = _source_stratagem_record("fire-overwatch")
    handcraft_request = create_stratagem_use_decision_request(
        state=finite_state,
        context=finite_context,
        options=(
            _handcrafted_stratagem_option(
                record=handcraft_record,
                context=finite_context,
                binding=StratagemTargetBinding(
                    target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                    target_player_id="player-a",
                    target_unit_instance_id="army-alpha:intercessor-unit-1",
                ),
            ),
        ),
    )
    finite_lifecycle.decision_controller.request_decision(handcraft_request)
    rejected_finite = finite_lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase12c-deferred-core-finite",
            request=handcraft_request,
            selected_option_id=handcraft_request.options[0].option_id,
        )
    )
    assert rejected_finite.status_kind is LifecycleStatusKind.INVALID
    assert rejected_finite.payload == {"invalid_reason": "unsupported_handler"}
    assert finite_state.command_point_total("player-a") == 3
    assert finite_state.stratagem_use_records == []
    assert finite_lifecycle.decision_controller.queue.pending_requests == (handcraft_request,)

    parameterized_lifecycle = _battle_lifecycle()
    parameterized_state = _state(parameterized_lifecycle)
    _set_current_battle_phase(parameterized_state, BattlePhase.MOVEMENT)
    _grant_cp(parameterized_state, player_id="player-a", amount=1)
    parameterized_context = _context(
        state=parameterized_state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
    )
    parameterized_proposal = StratagemTargetProposal.for_request(
        context=parameterized_context,
        catalog_record=handcraft_record,
    )
    pending_proposal_request = DecisionRequest(
        request_id=parameterized_state.next_decision_request_id(),
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        actor_id=parameterized_proposal.player_id,
        payload=validate_json_value({"proposal_request": parameterized_proposal.to_payload()}),
        options=(parameterized_decision_option(),),
    )
    parameterized_lifecycle.decision_controller.request_decision(pending_proposal_request)
    rejected_parameterized = parameterized_lifecycle.submit_decision(
        _target_proposal_result(
            request=pending_proposal_request,
            result_id="phase12c-deferred-core-parameterized",
            proposal=parameterized_proposal.with_binding(
                StratagemTargetBinding(
                    target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                    target_player_id="player-a",
                    target_unit_instance_id="army-alpha:intercessor-unit-1",
                )
            ),
        )
    )
    assert rejected_parameterized.status_kind is LifecycleStatusKind.INVALID
    assert rejected_parameterized.payload == {"invalid_reason": "unsupported_handler"}
    assert parameterized_state.command_point_total("player-a") == 1
    assert parameterized_state.stratagem_use_records == []
    assert parameterized_lifecycle.decision_controller.queue.pending_requests == (
        pending_proposal_request,
    )


def test_rapid_ingress_target_and_placement_proposals_resolve_through_lifecycle() -> None:
    lifecycle = _battle_lifecycle()
    state, reserve_state, reserve_unit, reserve_army, placement_request = (
        _request_rapid_ingress_placement(lifecycle)
    )
    assert state.command_point_total("player-b") == 0
    assert len(state.stratagem_use_records) == 1

    placement = _reserve_placement(
        army=reserve_army,
        reserve_unit=reserve_unit,
        poses=tuple(
            Pose.at(x=12.0 + index * 2.0, y=40.0, z=0.0, facing_degrees=180.0)
            for index, _model in enumerate(reserve_unit.own_models)
        ),
    )
    placement_payload = PlacementProposalPayload(
        proposal_request_id=placement_request.request_id,
        proposal_kind=ProposalKind.REINFORCEMENT,
        unit_instance_id=reserve_state.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,
        attempted_placement=placement,
    )

    lifecycle.submit_decision(
        DecisionResult(
            result_id="phase12c-rapid-ingress-placement",
            request_id=placement_request.request_id,
            decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=placement_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(placement_payload.to_payload()),
        )
    )

    arrived_state = state.reserve_state_for_unit(reserve_state.unit_instance_id)
    assert arrived_state is not None
    assert arrived_state.status is ReserveStatus.ARRIVED
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_by_id(reserve_state.unit_instance_id) == placement
    assert _has_event(lifecycle.decision_controller, "reinforcement_unit_arrived")
    assert (
        _last_event_payload(lifecycle.decision_controller, "rapid_ingress_resolved")[
            "stratagem_use"
        ]
        == state.stratagem_use_records[0].to_payload()
    )
    assert "<" not in json.dumps(lifecycle.to_payload(), sort_keys=True)


def test_rapid_ingress_reaction_target_and_placement_restore_before_parent_resumes() -> None:
    lifecycle = _battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.battle_round = 2
    _grant_cp(state, player_id="player-b", amount=1)
    reserve_state, _reserve_unit, _reserve_army = _move_unit_to_reserves(
        state,
        player_id="player-b",
        unit_instance_id="army-beta:enemy-unit",
    )
    proposal_request = StratagemTargetProposal.for_request(
        context=_context(
            state=state,
            player_id="player-b",
            trigger_kind=TimingTriggerKind.END_PHASE,
        ),
        catalog_record=_source_stratagem_record("rapid-ingress"),
    )
    lifecycle.reaction_queue.emit_decision_request(
        state=state,
        decisions=lifecycle.decision_controller,
        reaction_window=_reaction_window_for_trigger(
            state,
            eligible_player_id="player-b",
            trigger_kind=TimingTriggerKind.END_PHASE,
            source_rule_id="phase12c-rapid-ingress-reaction",
            window_id="phase12c-rapid-ingress-window",
        ),
        parent_phase=BattlePhase.MOVEMENT,
        parent_step="end_movement_phase_reactions",
        resume_token="phase12c_rapid_ingress_resume_token",
        actor_id="player-b",
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        options=(parameterized_decision_option(),),
        payload=validate_json_value(
            {"proposal_request": validate_json_value(proposal_request.to_payload())}
        ),
    )
    restored_target = GameLifecycle.from_payload(_lifecycle_payload_copy(lifecycle))
    target_request = _decision_request(restored_target.advance_until_decision_or_terminal())

    target_status = restored_target.submit_decision(
        _target_proposal_result(
            request=target_request,
            result_id="phase12c-rapid-ingress-reaction-target",
            proposal=_proposal_request_from_decision(target_request).with_binding(
                StratagemTargetBinding(
                    target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                    target_player_id="player-b",
                    target_unit_instance_id=reserve_state.unit_instance_id,
                )
            ),
        )
    )
    placement_request = _decision_request(target_status)

    assert placement_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
    assert len(restored_target.reaction_queue.frames) == 1
    assert restored_target.reaction_queue.frames[0].request_id == placement_request.request_id
    assert not _has_event(restored_target.decision_controller, "reaction_parent_resumed")
    assert _has_event(restored_target.decision_controller, "reaction_window_continued")

    restored_placement = GameLifecycle.from_payload(_lifecycle_payload_copy(restored_target))
    restored_state = _state(restored_placement)
    restored_reserve_state = restored_state.reserve_state_for_unit(reserve_state.unit_instance_id)
    assert restored_reserve_state is not None
    restored_army = restored_state.army_definition_for_player("player-b")
    assert restored_army is not None
    restored_reserve_unit = restored_army.unit_by_id(reserve_state.unit_instance_id)
    restored_placement_request = _decision_request(
        restored_placement.advance_until_decision_or_terminal()
    )
    placement = _reserve_placement(
        army=restored_army,
        reserve_unit=restored_reserve_unit,
        poses=tuple(
            Pose.at(x=12.0 + index * 2.0, y=40.0, z=0.0, facing_degrees=180.0)
            for index, _model in enumerate(restored_reserve_unit.own_models)
        ),
    )
    placement_payload = PlacementProposalPayload(
        proposal_request_id=restored_placement_request.request_id,
        proposal_kind=ProposalKind.REINFORCEMENT,
        unit_instance_id=restored_reserve_state.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,
        attempted_placement=placement,
    )

    resumed = restored_placement.submit_decision(
        DecisionResult(
            result_id="phase12c-rapid-ingress-reaction-placement",
            request_id=restored_placement_request.request_id,
            decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=restored_placement_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(placement_payload.to_payload()),
        )
    )

    assert restored_placement.reaction_queue.frames == ()
    assert resumed.status_kind is not LifecycleStatusKind.INVALID
    resumed_payload = _last_event_payload(
        restored_placement.decision_controller,
        "reaction_parent_resumed",
    )
    assert resumed_payload["resume_token"] == "phase12c_rapid_ingress_resume_token"
    assert _has_event(restored_placement.decision_controller, "rapid_ingress_resolved")
    arrived_state = restored_state.reserve_state_for_unit(restored_reserve_state.unit_instance_id)
    assert arrived_state is not None
    assert arrived_state.status is ReserveStatus.ARRIVED


def test_rapid_ingress_invalid_placement_is_typed_invalid_without_arrival() -> None:
    lifecycle = _battle_lifecycle()
    state, reserve_state, reserve_unit, reserve_army, placement_request = (
        _request_rapid_ingress_placement(lifecycle)
    )
    invalid_placement = _reserve_placement(
        army=reserve_army,
        reserve_unit=reserve_unit,
        poses=tuple(
            Pose.at(x=12.0 + index * 2.0, y=8.0, z=0.0, facing_degrees=180.0)
            for index, _model in enumerate(reserve_unit.own_models)
        ),
    )
    placement_payload = PlacementProposalPayload(
        proposal_request_id=placement_request.request_id,
        proposal_kind=ProposalKind.REINFORCEMENT,
        unit_instance_id=reserve_state.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,
        attempted_placement=invalid_placement,
    )

    status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase12c-rapid-ingress-invalid-placement",
            request_id=placement_request.request_id,
            decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=placement_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(placement_payload.to_payload()),
        )
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    assert status.payload["phase_body_status"] == "rapid_ingress_placement_invalid"
    next_request_id = status.payload["next_request_id"]
    assert type(next_request_id) is str
    retry_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    assert retry_request.request_id == next_request_id
    assert retry_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
    assert state.reserve_state_for_unit(reserve_state.unit_instance_id) == reserve_state
    assert state.battlefield_state is not None
    assert not any(
        unit_placement.unit_instance_id == reserve_state.unit_instance_id
        for placed_army in state.battlefield_state.placed_armies
        for unit_placement in placed_army.unit_placements
    )
    assert _has_event(lifecycle.decision_controller, "rapid_ingress_placement_invalid")


def test_rapid_ingress_reaction_invalid_placement_keeps_parent_blocked_for_retry() -> None:
    lifecycle = _battle_lifecycle()
    state, reserve_state, reserve_unit, reserve_army, placement_request = (
        _request_rapid_ingress_reaction_placement(lifecycle)
    )
    invalid_placement = _reserve_placement(
        army=reserve_army,
        reserve_unit=reserve_unit,
        poses=tuple(
            Pose.at(x=12.0 + index * 2.0, y=8.0, z=0.0, facing_degrees=180.0)
            for index, _model in enumerate(reserve_unit.own_models)
        ),
    )
    placement_payload = PlacementProposalPayload(
        proposal_request_id=placement_request.request_id,
        proposal_kind=ProposalKind.REINFORCEMENT,
        unit_instance_id=reserve_state.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,
        attempted_placement=invalid_placement,
    )

    status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase12c-rapid-ingress-reaction-invalid-placement",
            request_id=placement_request.request_id,
            decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=placement_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(placement_payload.to_payload()),
        )
    )
    retry_request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    assert status.payload["next_request_id"] == retry_request.request_id
    assert len(lifecycle.reaction_queue.frames) == 1
    assert lifecycle.reaction_queue.frames[0].request_id == retry_request.request_id
    assert not _has_event(lifecycle.decision_controller, "reaction_parent_resumed")
    assert state.reserve_state_for_unit(reserve_state.unit_instance_id) == reserve_state


def test_rapid_ingress_stale_placement_proposal_rejects_before_queue_pop() -> None:
    lifecycle = _battle_lifecycle()
    state, reserve_state, reserve_unit, reserve_army, placement_request = (
        _request_rapid_ingress_placement(lifecycle)
    )
    stale_placement = _reserve_placement(
        army=reserve_army,
        reserve_unit=reserve_unit,
        poses=tuple(
            Pose.at(x=12.0 + index * 2.0, y=40.0, z=0.0, facing_degrees=180.0)
            for index, _model in enumerate(reserve_unit.own_models)
        ),
    )
    stale_payload = PlacementProposalPayload(
        proposal_request_id="phase12c-stale-placement-request",
        proposal_kind=ProposalKind.REINFORCEMENT,
        unit_instance_id=reserve_state.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,
        attempted_placement=stale_placement,
    )

    status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase12c-rapid-ingress-stale-placement",
            request_id=placement_request.request_id,
            decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=placement_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(stale_payload.to_payload()),
        )
    )
    still_pending = _decision_request(lifecycle.advance_until_decision_or_terminal())

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    validation_payload = cast(dict[str, JsonValue], status.payload["proposal_validation"])
    violations = cast(list[JsonValue], validation_payload["violations"])
    violation_payload = cast(dict[str, JsonValue], violations[0])
    assert violation_payload["violation_code"] == "stale_proposal_request"
    assert still_pending == placement_request
    assert state.reserve_state_for_unit(reserve_state.unit_instance_id) == reserve_state


def test_rapid_ingress_malformed_placement_payload_rejects_before_queue_pop() -> None:
    lifecycle = _battle_lifecycle()
    state, reserve_state, _reserve_unit, _reserve_army, placement_request = (
        _request_rapid_ingress_placement(lifecycle)
    )

    status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase12c-rapid-ingress-malformed-placement",
            request_id=placement_request.request_id,
            decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=placement_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=None,
        )
    )
    still_pending = _decision_request(lifecycle.advance_until_decision_or_terminal())

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status.payload == {"invalid_reason": "malformed"}
    assert still_pending == placement_request
    assert state.reserve_state_for_unit(reserve_state.unit_instance_id) == reserve_state


def _source_stratagem_record(stratagem_id: str) -> StratagemCatalogRecord:
    for record in tenth_edition_stratagem_catalog_records():
        if record.definition.stratagem_id == stratagem_id:
            return record
    raise AssertionError(f"Missing source stratagem record: {stratagem_id}")


def _roll_command_reroll_candidate(
    lifecycle: GameLifecycle,
    *,
    actor_id: str,
    roll_type: str = "advance_roll",
) -> DiceRollState:
    state = _state(lifecycle)
    return DiceRollManager(
        state.game_id,
        event_log=lifecycle.decision_controller.event_log,
    ).roll_fixed(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason="Phase 12C Command Re-roll candidate",
            roll_type=roll_type,
            actor_id=actor_id,
        ),
        [1],
    )


def _context(
    *,
    state: GameState,
    player_id: str,
    trigger_kind: TimingTriggerKind,
    trigger_payload: JsonValue = None,
) -> StratagemEligibilityContext:
    return StratagemEligibilityContext.from_state(
        state=state,
        player_id=player_id,
        trigger_kind=trigger_kind,
        trigger_payload=trigger_payload,
    )


def _reaction_window(state: GameState, *, eligible_player_id: str) -> ReactionWindow:
    return _reaction_window_for_trigger(
        state=state,
        eligible_player_id=eligible_player_id,
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        source_rule_id="phase12c-command-reroll-reaction",
        window_id="phase12c-reaction-window-instance",
    )


def _reaction_window_for_trigger(
    state: GameState,
    *,
    eligible_player_id: str,
    trigger_kind: TimingTriggerKind,
    source_rule_id: str,
    window_id: str,
) -> ReactionWindow:
    descriptor = TimingWindowDescriptor(
        descriptor_id="phase12c-reaction-window",
        trigger_kind=trigger_kind,
        source_rule_id=source_rule_id,
        phase=BattlePhase.MOVEMENT,
    )
    window = TimingWindow(
        window_id=window_id,
        descriptor=descriptor,
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        phase=BattlePhase.MOVEMENT,
        trigger_event_id="phase12c-trigger-event",
    )
    return ReactionWindow(
        timing_window=window,
        eligible_player_ids=(eligible_player_id,),
    )


def _target_proposal_result(
    *,
    request: DecisionRequest,
    result_id: str,
    proposal: StratagemTargetProposal,
) -> DecisionResult:
    return DecisionResult(
        result_id=result_id,
        request_id=request.request_id,
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value({"proposal": proposal.to_payload()}),
    )


def _handcrafted_stratagem_option(
    *,
    record: StratagemCatalogRecord,
    context: StratagemEligibilityContext,
    binding: StratagemTargetBinding,
) -> DecisionOption:
    return DecisionOption(
        option_id=f"use-stratagem:{record.definition.stratagem_id}:target:handcrafted",
        label=record.definition.name,
        payload=validate_json_value(
            {
                "submission_kind": STRATAGEM_DECISION_TYPE,
                "context": context.to_payload(),
                "catalog_record": record.to_payload(),
                "target_binding": binding.to_payload(),
            }
        ),
    )


def _proposal_request_from_decision(request: DecisionRequest) -> StratagemTargetProposal:
    payload = cast(dict[str, JsonValue], request.payload)
    return StratagemTargetProposal.from_payload(
        cast(StratagemTargetProposalPayload, payload["proposal_request"])
    )


def _move_unit_to_reserves(
    state: GameState,
    *,
    player_id: str,
    unit_instance_id: str,
) -> tuple[ReserveState, UnitInstance, ArmyDefinition]:
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    state.replace_battlefield_state(battlefield_state.without_unit_placement(unit_instance_id))
    reserve_state = ReserveState.declared_before_battle(
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        reserve_kind=ReserveKind.RESERVES,
        destruction_deadline_policy=ReserveDestructionTimingPolicy.chapter_approved_2025_26(),
    )
    state.record_reserve_state(reserve_state)
    army = state.army_definition_for_player(player_id)
    assert army is not None
    return reserve_state, army.unit_by_id(unit_instance_id), army


def _request_rapid_ingress_placement(
    lifecycle: GameLifecycle,
) -> tuple[GameState, ReserveState, UnitInstance, ArmyDefinition, DecisionRequest]:
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.battle_round = 2
    _grant_cp(state, player_id="player-b", amount=1)
    reserve_state, reserve_unit, reserve_army = _move_unit_to_reserves(
        state,
        player_id="player-b",
        unit_instance_id="army-beta:enemy-unit",
    )
    proposal_request = StratagemTargetProposal.for_request(
        context=_context(
            state=state,
            player_id="player-b",
            trigger_kind=TimingTriggerKind.END_PHASE,
        ),
        catalog_record=_source_stratagem_record("rapid-ingress"),
    )
    waiting = request_stratagem_target_proposal(
        state=state,
        decisions=lifecycle.decision_controller,
        proposal_request=proposal_request,
    )
    request = _decision_request(waiting)
    target_status = lifecycle.submit_decision(
        _target_proposal_result(
            request=request,
            result_id="phase12c-rapid-ingress-target",
            proposal=_proposal_request_from_decision(request).with_binding(
                StratagemTargetBinding(
                    target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                    target_player_id="player-b",
                    target_unit_instance_id=reserve_state.unit_instance_id,
                )
            ),
        )
    )
    placement_request = _decision_request(target_status)
    assert placement_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
    return state, reserve_state, reserve_unit, reserve_army, placement_request


def _request_rapid_ingress_reaction_placement(
    lifecycle: GameLifecycle,
) -> tuple[GameState, ReserveState, UnitInstance, ArmyDefinition, DecisionRequest]:
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)
    state.battle_round = 2
    _grant_cp(state, player_id="player-b", amount=1)
    reserve_state, reserve_unit, reserve_army = _move_unit_to_reserves(
        state,
        player_id="player-b",
        unit_instance_id="army-beta:enemy-unit",
    )
    proposal_request = StratagemTargetProposal.for_request(
        context=_context(
            state=state,
            player_id="player-b",
            trigger_kind=TimingTriggerKind.END_PHASE,
        ),
        catalog_record=_source_stratagem_record("rapid-ingress"),
    )
    lifecycle.reaction_queue.emit_decision_request(
        state=state,
        decisions=lifecycle.decision_controller,
        reaction_window=_reaction_window_for_trigger(
            state,
            eligible_player_id="player-b",
            trigger_kind=TimingTriggerKind.END_PHASE,
            source_rule_id="phase12c-rapid-ingress-retry-reaction",
            window_id="phase12c-rapid-ingress-retry-window",
        ),
        parent_phase=BattlePhase.MOVEMENT,
        parent_step="end_movement_phase_reactions",
        resume_token="phase12c_rapid_ingress_retry_resume_token",
        actor_id="player-b",
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        options=(parameterized_decision_option(),),
        payload=validate_json_value(
            {"proposal_request": validate_json_value(proposal_request.to_payload())}
        ),
    )
    target_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    target_status = lifecycle.submit_decision(
        _target_proposal_result(
            request=target_request,
            result_id="phase12c-rapid-ingress-reaction-retry-target",
            proposal=_proposal_request_from_decision(target_request).with_binding(
                StratagemTargetBinding(
                    target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                    target_player_id="player-b",
                    target_unit_instance_id=reserve_state.unit_instance_id,
                )
            ),
        )
    )
    placement_request = _decision_request(target_status)
    assert placement_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
    assert lifecycle.reaction_queue.frames[0].request_id == placement_request.request_id
    return state, reserve_state, reserve_unit, reserve_army, placement_request


def _reserve_placement(
    *,
    army: ArmyDefinition,
    reserve_unit: UnitInstance,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=reserve_unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=reserve_unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(reserve_unit.own_models, poses, strict=True)
        ),
    )


def _remove_first_models(state: GameState, *, unit_instance_id: str, count: int) -> None:
    assert state.battlefield_state is not None
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    removed_ids = tuple(
        placement.model_instance_id for placement in unit_placement.model_placements[:count]
    )
    state.battlefield_state = state.battlefield_state.with_removed_models(removed_ids)


def _record_secondary_choices(
    state: GameState,
    *,
    player_a_mode: SecondaryMissionMode,
    player_b_mode: SecondaryMissionMode,
) -> None:
    state.record_secondary_mission_choice(
        _secondary_choice(player_id="player-a", mode=player_a_mode)
    )
    state.record_secondary_mission_choice(
        _secondary_choice(player_id="player-b", mode=player_b_mode)
    )


def _secondary_choice(*, player_id: str, mode: SecondaryMissionMode) -> SecondaryMissionChoice:
    if mode is SecondaryMissionMode.TACTICAL:
        return SecondaryMissionChoice(player_id=player_id, mode=mode)
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=mode,
        fixed_mission_ids=("assassination", "cleanse"),
    )


def _set_command_step_ready_for_battle_shock(state: GameState) -> None:
    command_state = CommandStepState.start(
        battle_round=state.battle_round,
        active_player_id="player-a",
    )
    state.command_step_state = (
        command_state.with_command_points_granted()
        .with_scoring_hooks_resolved()
        .with_tactical_secondary_resolved()
    )


def _set_command_step_ready_for_tactical_secondary(state: GameState) -> None:
    command_state = CommandStepState.start(
        battle_round=state.battle_round,
        active_player_id="player-a",
    )
    state.command_step_state = (
        command_state.with_command_points_granted().with_scoring_hooks_resolved()
    )


def _battle_lifecycle() -> GameLifecycle:
    config = _config()
    state = _battle_state(config=config)
    return GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": False,
            "state": state.to_payload(),
            "decisions": DecisionController().to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        }
    )


def _battle_state(config: GameConfig | None = None) -> GameState:
    resolved_config = _config() if config is None else config
    armies = _mustered_armies(resolved_config)
    state = GameState.from_config(resolved_config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase12c-battlefield",
        armies=armies,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    while state.current_setup_step is not None:
        state.complete_current_setup_step()
    assert state.stage is GameLifecycleStage.BATTLE
    return state


def _config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase12c-game",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_tenth_chapter_approved_2025_26(
            descriptor_version="core-v2-phase12c-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="enemy-unit",
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
    unit_selection_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_id="core-combined-arms",
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _grant_cp(state: GameState, *, player_id: str, amount: int) -> None:
    result = state.gain_command_points(
        player_id=player_id,
        amount=amount,
        source_id=f"phase12c-grant:{player_id}:{amount}",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    assert result.status is CommandPointGainStatus.APPLIED


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _state(lifecycle: GameLifecycle) -> GameState:
    state = lifecycle.state
    assert state is not None
    return state


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)


def _lifecycle_payload_copy(lifecycle: GameLifecycle) -> GameLifecyclePayload:
    return cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )


def _has_event(decisions: DecisionController, event_type: str) -> bool:
    return any(event.event_type == event_type for event in decisions.event_log.records)


def _last_event_payload(
    decisions: DecisionController,
    event_type: str,
) -> dict[str, JsonValue]:
    for event in reversed(decisions.event_log.records):
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"Missing event type: {event_type}")
