from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.adapters.contracts import FiniteOptionSubmission
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    FightEligibilityKind,
    FightPolicyDescriptor,
    RulesetDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_order import (
    CHARGE_FIGHTS_FIRST_EFFECT_KIND,
    DECLINE_FIGHT_INTERRUPT_OPTION_ID,
    ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
    FIGHT_ACTIVATION_DECISION_TYPE,
    FIGHT_INTERRUPT_DECISION_TYPE,
    FIGHT_INTERRUPT_EFFECT_KIND,
    FIGHTS_FIRST_EFFECT_KIND,
    EligibleToFightPass,
    FightActivationSelection,
    FightPhaseState,
    FightsFirstRegistry,
    FightsFirstSource,
    fight_activation_option_id,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
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
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.fight import invalid_fight_interrupt_status
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack


def test_fight_phase_exposes_source_steps_and_records_json_safe_activation() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={
            "intercessor-1": Pose.at(10.0, 20.0),
            "enemy": Pose.at(13.0, 20.0),
        },
        game_id="phase15c-basic",
    )

    request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    request_payload = cast(dict[str, object], request.payload)
    option_id = fight_activation_option_id(
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        fight_type=RulesetDescriptor.warhammer_40000_eleventh().fight_policy.fight_types[0],
    )
    status = _submit_option(
        lifecycle,
        request=request,
        option_id=option_id,
        result_id="phase15c-basic-activation",
    )
    activation_event = _last_event_payload(lifecycle, "fight_activation_selected")
    lifecycle_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    assert request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    assert request.actor_id == "player-a"
    request_steps = [
        step["step"] for step in cast(list[dict[str, object]], request_payload["step_states"])
    ]
    assert request_steps == [
        "start",
        "pile_in",
        "fight",
        "consolidate",
        "end",
    ]
    assert option_id in {option.option_id for option in request.options}
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert activation_event["phase15d_resolution"] == "deferred"
    assert [record.request.decision_type for record in lifecycle.decision_controller.records] == [
        FIGHT_ACTIVATION_DECISION_TYPE,
    ]
    assert GameLifecycle.from_payload(lifecycle_payload).to_payload() == lifecycle_payload


def test_fights_first_resolves_before_remaining_combats_with_active_player_alternation() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("alpha-first", "alpha-remaining"),
        enemy_unit_ids=("enemy-first", "enemy-remaining"),
        origins={
            "alpha-first": Pose.at(10.0, 20.0),
            "enemy-first": Pose.at(13.0, 20.0),
            "alpha-remaining": Pose.at(10.0, 40.0),
            "enemy-remaining": Pose.at(13.0, 40.0),
        },
        game_id="phase15c-fights-first",
        fights_first_unit_keys=("alpha-first", "enemy-first"),
    )

    first_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    first_payload = cast(dict[str, object], first_request.payload)
    first_status = _submit_normal_fight(
        lifecycle,
        request=first_request,
        unit=units["alpha-first"],
        result_id="phase15c-alpha-first",
    )
    second_request = _decision_request(first_status)
    second_payload = cast(dict[str, object], second_request.payload)
    second_status = _submit_normal_fight(
        lifecycle,
        request=second_request,
        unit=units["enemy-first"],
        result_id="phase15c-enemy-first",
    )
    third_request = _decision_request(second_status)
    third_payload = cast(dict[str, object], third_request.payload)

    assert first_request.actor_id == "player-a"
    assert first_payload["ordering_band"] == "fights_first"
    assert _request_unit_ids(first_request) == [units["alpha-first"].unit_instance_id]
    assert second_request.actor_id == "player-b"
    assert second_payload["ordering_band"] == "fights_first"
    assert _request_unit_ids(second_request) == [units["enemy-first"].unit_instance_id]
    assert third_request.actor_id == "player-a"
    assert third_payload["ordering_band"] == "remaining_combats"
    assert _request_unit_ids(third_request) == [units["alpha-remaining"].unit_instance_id]


def test_eligible_to_fight_pass_is_offered_only_when_all_eligible_units_are_more_than_five() -> (
    None
):
    close_lifecycle, _close_units = _fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={
            "intercessor-1": Pose.at(10.0, 20.0),
            "enemy": Pose.at(13.0, 20.0),
        },
        game_id="phase15c-pass-close",
    )
    close_request = _decision_request(close_lifecycle.advance_until_decision_or_terminal())

    far_lifecycle, far_units = _fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={
            "intercessor-1": Pose.at(10.0, 20.0),
            "enemy": Pose.at(30.0, 20.0),
        },
        game_id="phase15c-pass-far",
        charge_fights_first_unit_keys=("intercessor-1",),
    )
    far_request = _decision_request(far_lifecycle.advance_until_decision_or_terminal())
    pass_status = _submit_option(
        far_lifecycle,
        request=far_request,
        option_id=ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
        result_id="phase15c-pass",
    )
    pass_payload = _last_event_payload(far_lifecycle, "eligible_to_fight_pass_recorded")

    assert ELIGIBLE_TO_FIGHT_PASS_OPTION_ID not in {
        option.option_id for option in close_request.options
    }
    assert ELIGIBLE_TO_FIGHT_PASS_OPTION_ID in {option.option_id for option in far_request.options}
    assert _request_unit_ids(far_request) == [far_units["intercessor-1"].unit_instance_id]
    assert pass_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert cast(dict[str, object], pass_payload["eligible_pass"])["eligible_unit_ids"] == [
        far_units["intercessor-1"].unit_instance_id
    ]


def test_overrun_fight_rejects_when_unit_is_no_longer_eligible() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={
            "intercessor-1": Pose.at(10.0, 20.0),
            "enemy": Pose.at(13.0, 20.0),
        },
        game_id="phase15c-overrun-stale",
    )
    request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        units["enemy"].unit_instance_id
    )
    option_id = fight_activation_option_id(
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        fight_type=RulesetDescriptor.warhammer_40000_eleventh().fight_policy.fight_types[1],
    )

    status = _submit_option(
        lifecycle,
        request=request,
        option_id=option_id,
        result_id="phase15c-stale-overrun",
    )
    status_payload = cast(dict[str, object], status.payload)

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status_payload["invalid_reason"] == "invalid_fight_activation_result"
    assert status_payload["field"] == "eligibility_context"
    assert lifecycle.decision_controller.queue.pending_requests == (request,)
    assert lifecycle.decision_controller.records == ()


def test_fight_interrupt_uses_reaction_queue_once_and_resumes_parent_sequence() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={
            "intercessor-1": Pose.at(10.0, 20.0),
            "enemy": Pose.at(13.0, 20.0),
        },
        game_id="phase15c-interrupt",
        fight_interrupt_unit_keys=("enemy",),
    )
    first_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    interrupt_status = _submit_normal_fight(
        lifecycle,
        request=first_request,
        unit=units["intercessor-1"],
        result_id="phase15c-trigger-interrupt",
    )
    interrupt_request = _decision_request(interrupt_status)
    interrupt_option_id = fight_activation_option_id(
        unit_instance_id=units["enemy"].unit_instance_id,
        fight_type=RulesetDescriptor.warhammer_40000_eleventh().fight_policy.fight_types[0],
    )
    completed_status = _submit_option(
        lifecycle,
        request=interrupt_request,
        option_id=interrupt_option_id,
        result_id="phase15c-resolve-interrupt",
    )

    assert interrupt_request.decision_type == FIGHT_INTERRUPT_DECISION_TYPE
    assert interrupt_request.actor_id == "player-b"
    assert DECLINE_FIGHT_INTERRUPT_OPTION_ID in {
        option.option_id for option in interrupt_request.options
    }
    assert len(lifecycle.reaction_queue.frames) == 0
    assert completed_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert len(_event_payloads(lifecycle, "fight_interrupt_requested")) == 1
    assert len(_event_payloads(lifecycle, "reaction_parent_resumed")) == 1
    assert len(_event_payloads(lifecycle, "fight_interrupt_activation_selected")) == 1


def test_fight_interrupt_source_is_not_offered_again_after_accepted_interrupt() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("alpha-1", "alpha-2"),
        enemy_unit_ids=("enemy-1", "enemy-2", "enemy-3"),
        origins={
            "alpha-1": Pose.at(10.0, 20.0),
            "enemy-1": Pose.at(13.0, 20.0),
            "alpha-2": Pose.at(10.0, 40.0),
            "enemy-2": Pose.at(13.0, 40.0),
            "enemy-3": Pose.at(14.5, 40.0),
        },
        game_id="phase15c-interrupt-source-accepted",
        fight_interrupt_unit_keys=("enemy-1",),
    )
    first_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    interrupt_status = _submit_normal_fight(
        lifecycle,
        request=first_request,
        unit=units["alpha-1"],
        result_id="phase15c-trigger-accepted-source-interrupt",
    )
    interrupt_request = _decision_request(interrupt_status)
    interrupt_source_effect_id = _interrupt_source_effect_id(interrupt_request)
    after_interrupt_status = _submit_normal_fight(
        lifecycle,
        request=interrupt_request,
        unit=units["enemy-1"],
        result_id="phase15c-accepted-source-interrupt",
    )
    enemy_normal_request = _decision_request(after_interrupt_status)
    after_enemy_normal_status = _submit_normal_fight(
        lifecycle,
        request=enemy_normal_request,
        unit=units["enemy-2"],
        result_id="phase15c-enemy-normal-after-interrupt",
    )
    alpha_second_request = _decision_request(after_enemy_normal_status)
    after_alpha_second_status = _submit_normal_fight(
        lifecycle,
        request=alpha_second_request,
        unit=units["alpha-2"],
        result_id="phase15c-alpha-second-after-interrupt",
    )
    resumed_request = _decision_request(after_alpha_second_status)
    state = _state(lifecycle)

    assert resumed_request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    assert resumed_request.actor_id == "player-b"
    assert _request_unit_ids(resumed_request) == [units["enemy-3"].unit_instance_id]
    assert state.fight_phase_state is not None
    assert state.fight_phase_state.resolved_interrupt_source_effect_ids == (
        interrupt_source_effect_id,
    )
    assert len(_event_payloads(lifecycle, "fight_interrupt_requested")) == 1
    assert len(_event_payloads(lifecycle, "fight_interrupt_activation_selected")) == 1


def test_fight_interrupt_decline_records_once_and_resumes_parent_sequence() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={
            "intercessor-1": Pose.at(10.0, 20.0),
            "enemy": Pose.at(13.0, 20.0),
        },
        game_id="phase15c-interrupt-decline",
        fight_interrupt_unit_keys=("enemy",),
    )
    first_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    interrupt_status = _submit_normal_fight(
        lifecycle,
        request=first_request,
        unit=units["intercessor-1"],
        result_id="phase15c-trigger-declined-interrupt",
    )
    interrupt_request = _decision_request(interrupt_status)
    resumed_status = _submit_option(
        lifecycle,
        request=interrupt_request,
        option_id=DECLINE_FIGHT_INTERRUPT_OPTION_ID,
        result_id="phase15c-decline-interrupt",
    )
    resumed_request = _decision_request(resumed_status)
    state = _state(lifecycle)

    assert resumed_request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    assert resumed_request.actor_id == "player-b"
    assert state.fight_phase_state is not None
    assert state.fight_phase_state.resolved_interrupt_ids
    assert state.fight_phase_state.resolved_interrupt_source_effect_ids
    assert len(_event_payloads(lifecycle, "fight_interrupt_declined")) == 1
    assert len(_event_payloads(lifecycle, "fight_interrupt_activation_selected")) == 0
    assert len(_event_payloads(lifecycle, "reaction_parent_resumed")) == 1


def test_fight_interrupt_source_is_not_offered_again_after_decline() -> None:
    lifecycle, units = _fight_lifecycle(
        alpha_unit_ids=("alpha-1", "alpha-2"),
        enemy_unit_ids=("enemy-1", "enemy-2"),
        origins={
            "alpha-1": Pose.at(10.0, 20.0),
            "enemy-1": Pose.at(13.0, 20.0),
            "alpha-2": Pose.at(10.0, 40.0),
            "enemy-2": Pose.at(13.0, 40.0),
        },
        game_id="phase15c-interrupt-source-declined",
        fight_interrupt_unit_keys=("enemy-1",),
    )
    first_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    interrupt_status = _submit_normal_fight(
        lifecycle,
        request=first_request,
        unit=units["alpha-1"],
        result_id="phase15c-trigger-declined-source-interrupt",
    )
    interrupt_request = _decision_request(interrupt_status)
    interrupt_source_effect_id = _interrupt_source_effect_id(interrupt_request)
    after_decline_status = _submit_option(
        lifecycle,
        request=interrupt_request,
        option_id=DECLINE_FIGHT_INTERRUPT_OPTION_ID,
        result_id="phase15c-declined-source-interrupt",
    )
    enemy_normal_request = _decision_request(after_decline_status)
    after_enemy_normal_status = _submit_normal_fight(
        lifecycle,
        request=enemy_normal_request,
        unit=units["enemy-1"],
        result_id="phase15c-enemy-normal-after-decline",
    )
    alpha_second_request = _decision_request(after_enemy_normal_status)
    stale_source_request = _retriggered_interrupt_request(interrupt_request)
    stale_interrupt_result = FiniteOptionSubmission(
        request_id=stale_source_request.request_id,
        selected_option_id=DECLINE_FIGHT_INTERRUPT_OPTION_ID,
        result_id="phase15c-replayed-declined-source-interrupt",
    ).to_result(stale_source_request)
    stale_source_status = invalid_fight_interrupt_status(
        state=_state(lifecycle),
        request=stale_source_request,
        result=stale_interrupt_result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )
    after_alpha_second_status = _submit_normal_fight(
        lifecycle,
        request=alpha_second_request,
        unit=units["alpha-2"],
        result_id="phase15c-alpha-second-after-decline",
    )
    resumed_request = _decision_request(after_alpha_second_status)
    pending_before_replayed_submit = lifecycle.decision_controller.queue.pending_requests
    replayed_submit_status = lifecycle.submit_decision(stale_interrupt_result)
    state = _state(lifecycle)

    assert stale_source_status is not None
    assert stale_source_status.status_kind is LifecycleStatusKind.INVALID
    assert stale_source_status.payload == {
        "invalid_reason": "invalid_fight_interrupt_result",
        "field": "source_effect_id",
    }
    assert resumed_request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    assert resumed_request.actor_id == "player-b"
    assert _request_unit_ids(resumed_request) == [units["enemy-2"].unit_instance_id]
    assert replayed_submit_status.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.decision_controller.queue.pending_requests == pending_before_replayed_submit
    assert state.fight_phase_state is not None
    assert state.fight_phase_state.resolved_interrupt_source_effect_ids == (
        interrupt_source_effect_id,
    )
    assert len(_event_payloads(lifecycle, "fight_interrupt_requested")) == 1
    assert len(_event_payloads(lifecycle, "fight_interrupt_declined")) == 1
    assert len(_event_payloads(lifecycle, "fight_interrupt_activation_selected")) == 0


def test_fight_phase_state_nested_payloads_round_trip() -> None:
    policy = RulesetDescriptor.warhammer_40000_eleventh().fight_policy
    source = FightsFirstSource(
        unit_instance_id="unit-a",
        effect_id="effect-a",
        source_rule_id="source-a",
        effect_kind=CHARGE_FIGHTS_FIRST_EFFECT_KIND,
    )
    registry = FightsFirstRegistry((source,))
    fight_state = FightPhaseState.start(
        battle_round=1,
        active_player_id="player-a",
        policy=policy,
        eligible_at_start_unit_ids=("unit-a",),
        fights_first_registry=registry,
    )
    eligible_pass = EligibleToFightPass(
        player_id="player-a",
        battle_round=1,
        ordering_band=fight_state.current_ordering_band,
        request_id="request-pass",
        result_id="result-pass",
        pass_distance_inches=policy.eligible_pass_distance_inches,
        eligible_unit_ids=("unit-a",),
    )
    activation = FightActivationSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="unit-a",
        ordering_band=fight_state.current_ordering_band,
        fight_type=policy.fight_types[0],
        eligibility_reasons=(FightEligibilityKind.CHARGED_THIS_TURN,),
        request_id="request-activation",
        result_id="result-activation",
        interrupt_id=None,
    )
    populated = (
        fight_state.with_next_player("player-b")
        .with_eligible_pass(eligible_pass)
        .with_activation(activation)
        .with_resolved_interrupt(interrupt_id="interrupt-a", source_effect_id="effect-interrupt-a")
        .with_next_band()
        .with_phase_complete()
    )

    assert registry.has_unit("unit-a")
    assert registry.charged_unit_ids() == ("unit-a",)
    assert FightsFirstSource.from_payload(source.to_payload()) == source
    assert FightsFirstRegistry.from_payload(registry.to_payload()) == registry
    assert FightPhaseState.from_payload(populated.to_payload()) == populated


def test_fight_phase_state_rejects_drifted_or_malformed_nested_records() -> None:
    policy = RulesetDescriptor.warhammer_40000_eleventh().fight_policy
    base_state = FightPhaseState.start(
        battle_round=1,
        active_player_id="player-a",
        policy=policy,
        eligible_at_start_unit_ids=("unit-a",),
        fights_first_registry=FightsFirstRegistry(),
    )
    activation = FightActivationSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="unit-a",
        ordering_band=base_state.current_ordering_band,
        fight_type=policy.fight_types[0],
        eligibility_reasons=(FightEligibilityKind.ENGAGED_AT_FIGHT_PHASE_START,),
        request_id="request-activation",
        result_id="result-activation",
        interrupt_id=None,
    )
    drifted_activation = FightActivationSelection(
        player_id="player-a",
        battle_round=2,
        unit_instance_id="unit-b",
        ordering_band=base_state.current_ordering_band,
        fight_type=policy.fight_types[0],
        eligibility_reasons=(FightEligibilityKind.ENGAGED_AT_FIGHT_PHASE_START,),
        request_id="request-drifted",
        result_id="result-drifted",
        interrupt_id=None,
    )
    eligible_pass = EligibleToFightPass(
        player_id="player-a",
        battle_round=1,
        ordering_band=policy.ordering_bands[1],
        request_id="request-pass",
        result_id="result-pass",
        pass_distance_inches=policy.eligible_pass_distance_inches,
        eligible_unit_ids=("unit-a",),
    )
    source = FightsFirstSource(
        unit_instance_id="unit-a",
        effect_id="effect-a",
        source_rule_id="source-a",
        effect_kind=FIGHTS_FIRST_EFFECT_KIND,
    )

    with pytest.raises(GameLifecycleError, match="requires a FightPolicyDescriptor"):
        FightPhaseState.start(
            battle_round=1,
            active_player_id="player-a",
            policy=cast(FightPolicyDescriptor, object()),
            eligible_at_start_unit_ids=("unit-a",),
            fights_first_registry=FightsFirstRegistry(),
        )
    with pytest.raises(GameLifecycleError, match="sources must be a tuple"):
        FightsFirstRegistry(cast(tuple[FightsFirstSource, ...], []))
    with pytest.raises(GameLifecycleError, match="sources must be unique"):
        FightsFirstRegistry((source, source))
    with pytest.raises(GameLifecycleError, match="step_states must not be empty"):
        FightPhaseState(
            battle_round=1,
            active_player_id="player-a",
            step_states=(),
            ordering_bands=policy.ordering_bands,
            current_band_index=0,
            next_player_id="player-a",
            eligible_at_start_unit_ids=("unit-a",),
        )
    with pytest.raises(GameLifecycleError, match="current_band_index is out of range"):
        FightPhaseState(
            battle_round=1,
            active_player_id="player-a",
            step_states=base_state.step_states,
            ordering_bands=policy.ordering_bands,
            current_band_index=99,
            next_player_id="player-a",
            eligible_at_start_unit_ids=("unit-a",),
        )
    with pytest.raises(GameLifecycleError, match="activation_selections must contain"):
        FightPhaseState(
            battle_round=1,
            active_player_id="player-a",
            step_states=base_state.step_states,
            ordering_bands=policy.ordering_bands,
            current_band_index=0,
            next_player_id="player-a",
            eligible_at_start_unit_ids=("unit-a",),
            activation_selections=cast(tuple[FightActivationSelection, ...], ("bad",)),
        )
    with pytest.raises(GameLifecycleError, match="eligible_passes must contain"):
        FightPhaseState(
            battle_round=1,
            active_player_id="player-a",
            step_states=base_state.step_states,
            ordering_bands=policy.ordering_bands,
            current_band_index=0,
            next_player_id="player-a",
            eligible_at_start_unit_ids=("unit-a",),
            eligible_passes=cast(tuple[EligibleToFightPass, ...], ("bad",)),
        )
    with pytest.raises(GameLifecycleError, match="phase_complete must be a bool"):
        FightPhaseState(
            battle_round=1,
            active_player_id="player-a",
            step_states=base_state.step_states,
            ordering_bands=policy.ordering_bands,
            current_band_index=0,
            next_player_id="player-a",
            eligible_at_start_unit_ids=("unit-a",),
            phase_complete=cast(bool, "false"),
        )
    with pytest.raises(GameLifecycleError, match="unit IDs must be unique"):
        FightPhaseState(
            battle_round=1,
            active_player_id="player-a",
            step_states=base_state.step_states,
            ordering_bands=policy.ordering_bands,
            current_band_index=0,
            next_player_id="player-a",
            eligible_at_start_unit_ids=("unit-a", "unit-a"),
        )
    with pytest.raises(GameLifecycleError, match="battle round drift"):
        base_state.with_activation(drifted_activation)
    with pytest.raises(GameLifecycleError, match="ordering band drift"):
        base_state.with_eligible_pass(eligible_pass)
    with pytest.raises(GameLifecycleError, match="already activated"):
        base_state.with_activation(activation).with_activation(activation)
    with pytest.raises(GameLifecycleError, match="already resolved"):
        base_state.with_resolved_interrupt(
            interrupt_id="interrupt-a",
            source_effect_id="effect-interrupt-a",
        ).with_resolved_interrupt(
            interrupt_id="interrupt-a",
            source_effect_id="effect-interrupt-b",
        )
    with pytest.raises(GameLifecycleError, match="source has already resolved"):
        base_state.with_resolved_interrupt(
            interrupt_id="interrupt-a",
            source_effect_id="effect-interrupt-a",
        ).with_resolved_interrupt(
            interrupt_id="interrupt-b",
            source_effect_id="effect-interrupt-a",
        )
    with pytest.raises(GameLifecycleError, match="source effect IDs must be unique"):
        FightPhaseState(
            battle_round=1,
            active_player_id="player-a",
            step_states=base_state.step_states,
            ordering_bands=policy.ordering_bands,
            current_band_index=0,
            next_player_id="player-a",
            eligible_at_start_unit_ids=("unit-a",),
            resolved_interrupt_ids=("interrupt-a", "interrupt-b"),
            resolved_interrupt_source_effect_ids=(
                "effect-interrupt-a",
                "effect-interrupt-a",
            ),
        )
    with pytest.raises(GameLifecycleError, match="resolved interrupt tracking drift"):
        FightPhaseState(
            battle_round=1,
            active_player_id="player-a",
            step_states=base_state.step_states,
            ordering_bands=policy.ordering_bands,
            current_band_index=0,
            next_player_id="player-a",
            eligible_at_start_unit_ids=("unit-a",),
            resolved_interrupt_ids=("interrupt-a",),
            resolved_interrupt_source_effect_ids=(),
        )


def _fight_lifecycle(
    *,
    alpha_unit_ids: tuple[str, ...],
    enemy_unit_ids: tuple[str, ...],
    origins: dict[str, Pose],
    game_id: str,
    fights_first_unit_keys: tuple[str, ...] = (),
    charge_fights_first_unit_keys: tuple[str, ...] = (),
    fight_interrupt_unit_keys: tuple[str, ...] = (),
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    config = _config(
        game_id=game_id,
        alpha_unit_ids=alpha_unit_ids,
        enemy_unit_ids=enemy_unit_ids,
    )
    armies = _mustered_armies(config)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id=f"{game_id}-battlefield",
        armies=armies,
    )
    units = {
        unit.unit_instance_id.split(":", maxsplit=1)[1]: unit
        for army in armies
        for unit in army.units
    }
    battlefield = scenario.battlefield_state
    for key, unit in units.items():
        army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
        player_id = "player-a" if army_id == "army-alpha" else "player-b"
        battlefield = battlefield.with_unit_placement(
            _unit_placement_at(
                unit,
                army_id=army_id,
                player_id=player_id,
                poses=_compact_test_unit_poses(
                    origin=origins[key],
                    model_count=len(unit.own_models),
                ),
            )
        )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    for key in fights_first_unit_keys:
        _record_fights_first_effect(
            state=state,
            unit=units[key],
            effect_kind=FIGHTS_FIRST_EFFECT_KIND,
        )
    for key in charge_fights_first_unit_keys:
        _record_fights_first_effect(
            state=state,
            unit=units[key],
            effect_kind=CHARGE_FIGHTS_FIRST_EFFECT_KIND,
        )
    for key in fight_interrupt_unit_keys:
        _record_fight_interrupt_effect(state=state, unit=units[key])
    payload = cast(
        GameLifecyclePayload,
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": GameLifecycle().decision_controller.to_payload(),
            "reaction_queue": {"frames": []},
        },
    )
    return GameLifecycle.from_payload(payload), units


def _config(
    *,
    game_id: str,
    alpha_unit_ids: tuple[str, ...],
    enemy_unit_ids: tuple[str, ...],
) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id=game_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase15c-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=alpha_unit_ids,
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=enemy_unit_ids,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _mission_setup() -> MissionSetup:
    mission_pack = chapter_approved_2025_26_mission_pack()
    return MissionSetup(
        mission_pack_id=mission_pack.mission_pack_id,
        source_version=mission_pack.source_version,
        source_id=mission_pack.source_id,
        mission_pool_entry_id="mission-a",
        primary_mission_id="take-and-hold",
        deployment_map_id="phase15c-open-map",
        terrain_layout_id="phase15c-open-layout",
        attacker_player_id="player-a",
        defender_player_id="player-b",
        battlefield_width_inches=100.0,
        battlefield_depth_inches=100.0,
        objective_markers=(
            ObjectiveMarkerDefinition(
                objective_marker_id="phase15c-remote-objective",
                name="Phase 15C Remote Objective",
                x_inches=95.0,
                y_inches=95.0,
                source_id="phase15c-test",
            ),
        ),
        deployment_zones=(),
        terrain_features=(),
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
            detachment_id="core-combined-arms",
        ),
        unit_selections=tuple(_unit_selection(unit_id) for unit_id in unit_selection_ids),
    )


def _unit_selection(unit_selection_id: str) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id="core-intercessor-like-infantry",
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _compact_test_unit_poses(*, origin: Pose, model_count: int) -> tuple[Pose, ...]:
    return tuple(
        Pose.at(
            origin.position.x + ((index % 5) * 1.4),
            origin.position.y + ((index // 5) * 1.4),
            origin.position.z,
            facing_degrees=origin.facing.degrees,
        )
        for index in range(model_count)
    )


def _unit_placement_at(
    unit: UnitInstance,
    *,
    army_id: str,
    player_id: str,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(unit.own_models, poses, strict=True)
        ),
    )


def _record_fights_first_effect(
    *,
    state: GameState,
    unit: UnitInstance,
    effect_kind: str,
) -> None:
    player_id = _player_id_for_unit(unit)
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"{unit.unit_instance_id}:{effect_kind}",
            source_rule_id=f"phase15c:{effect_kind}",
            owner_player_id=player_id,
            target_unit_instance_ids=(unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.CHARGE,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round,
                player_id=player_id,
            ),
            effect_payload={"effect_kind": effect_kind},
        )
    )


def _record_fight_interrupt_effect(*, state: GameState, unit: UnitInstance) -> None:
    player_id = _player_id_for_unit(unit)
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"{unit.unit_instance_id}:fight-interrupt",
            source_rule_id="phase15c:counter-offensive",
            owner_player_id=player_id,
            target_unit_instance_ids=(unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.FIGHT,
            expiration=EffectExpiration.end_phase(
                battle_round=state.battle_round,
                phase=BattlePhaseKind.FIGHT,
                player_id=player_id,
            ),
            effect_payload={
                "effect_kind": FIGHT_INTERRUPT_EFFECT_KIND,
                "source_rule_id": "phase15c:counter-offensive",
            },
        )
    )


def _player_id_for_unit(unit: UnitInstance) -> str:
    army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
    return "player-a" if army_id == "army-alpha" else "player-b"


def _submit_normal_fight(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    unit: UnitInstance,
    result_id: str,
) -> LifecycleStatus:
    return _submit_option(
        lifecycle,
        request=request,
        option_id=fight_activation_option_id(
            unit_instance_id=unit.unit_instance_id,
            fight_type=RulesetDescriptor.warhammer_40000_eleventh().fight_policy.fight_types[0],
        ),
        result_id=result_id,
    )


def _submit_option(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        FiniteOptionSubmission(
            request_id=request.request_id,
            selected_option_id=option_id,
            result_id=result_id,
        ).to_result(request)
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _request_unit_ids(request: DecisionRequest) -> list[str]:
    payload = cast(dict[str, object], request.payload)
    contexts = cast(list[dict[str, object]], payload["eligible_contexts"])
    return [cast(str, context["unit_instance_id"]) for context in contexts]


def _interrupt_source_effect_id(request: DecisionRequest) -> str:
    payload = cast(dict[str, object], request.payload)
    handler_payload = cast(dict[str, object], payload["handler_payload"])
    interrupt = cast(dict[str, object], handler_payload["interrupt"])
    return cast(str, interrupt["source_effect_id"])


def _retriggered_interrupt_request(request: DecisionRequest) -> DecisionRequest:
    payload = cast(dict[str, object], request.payload)
    handler_payload = cast(dict[str, object], payload["handler_payload"])
    original_interrupt = cast(dict[str, object], handler_payload["interrupt"])
    interrupt = dict(original_interrupt)
    interrupt_id = cast(str, interrupt["interrupt_id"])
    trigger_event_id = cast(str, interrupt["trigger_event_id"])
    interrupt["interrupt_id"] = f"{interrupt_id}:later-trigger"
    interrupt["trigger_event_id"] = f"{trigger_event_id}:later-trigger"

    retriggered_handler_payload = dict(handler_payload)
    retriggered_handler_payload["interrupt"] = interrupt
    retriggered_payload = dict(payload)
    retriggered_payload["handler_payload"] = retriggered_handler_payload
    retriggered_payload["interrupt"] = interrupt

    return DecisionRequest(
        request_id=f"{request.request_id}:later-trigger",
        decision_type=FIGHT_INTERRUPT_DECISION_TYPE,
        actor_id=request.actor_id,
        payload=cast(JsonValue, retriggered_payload),
        options=(
            DecisionOption(
                option_id=DECLINE_FIGHT_INTERRUPT_OPTION_ID,
                label="Decline Fight Interrupt",
                payload=cast(
                    JsonValue,
                    {
                        "submission_kind": "decline_fight_interrupt",
                        "interrupt": interrupt,
                    },
                ),
            ),
        ),
    )


def _state(lifecycle: GameLifecycle) -> GameState:
    assert lifecycle.state is not None
    return lifecycle.state


def _last_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, object]:
    for event in reversed(lifecycle.decision_controller.event_log.records):
        if event.event_type == event_type:
            return cast(dict[str, object], event.payload)
    raise AssertionError(f"Missing event type {event_type}.")


def _event_payloads(lifecycle: GameLifecycle, event_type: str) -> tuple[dict[str, object], ...]:
    return tuple(
        cast(dict[str, object], event.payload)
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == event_type
    )
