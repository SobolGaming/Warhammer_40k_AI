from __future__ import annotations

import inspect
import json
from typing import cast

import pytest

from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    BattlePhaseSequenceDescriptor,
    RulesetDescriptor,
    SetupSequenceDescriptor,
    SetupStepKind,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameConfig, GameStatePayload
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
    game_lifecycle_stage_from_token,
    lifecycle_status_kind_from_token,
)
from warhammer40k_core.engine.phases.command import (
    TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
    CommandPhaseHandler,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE


def _config(
    *,
    ruleset_descriptor: RulesetDescriptor | None = None,
) -> GameConfig:
    descriptor = ruleset_descriptor
    if descriptor is None:
        descriptor = RulesetDescriptor.warhammer_40000_tenth(
            descriptor_version="core-v2-phase9b-test"
        )
    return GameConfig(
        game_id="phase9b-game",
        ruleset_descriptor=descriptor,
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "assassination",
            "bring_it_down",
            "cleanse",
        ),
    )


def _descriptor_with_sequences(
    *,
    setup_steps: tuple[SetupStepKind, ...] | None = None,
    battle_phases: tuple[BattlePhaseKind, ...] | None = None,
) -> RulesetDescriptor:
    base = RulesetDescriptor.warhammer_40000_tenth(
        descriptor_version="core-v2-phase9b-sequence-test"
    )
    return RulesetDescriptor(
        ruleset_id=base.ruleset_id,
        source_date=base.source_date,
        descriptor_version=base.descriptor_version,
        engagement_policy=base.engagement_policy,
        movement_policy=base.movement_policy,
        charge_policy=base.charge_policy,
        terrain_visibility_policy=base.terrain_visibility_policy,
        objective_policy=base.objective_policy,
        coherency_policy=base.coherency_policy,
        fly_policy=base.fly_policy,
        mission_policy=base.mission_policy,
        setup_sequence=SetupSequenceDescriptor(
            steps=setup_steps
            if setup_steps is not None
            else SetupSequenceDescriptor.warhammer_40000_tenth_default().steps
        ),
        battle_phase_sequence=BattlePhaseSequenceDescriptor(
            phases=battle_phases
            if battle_phases is not None
            else BattlePhaseSequenceDescriptor.warhammer_40000_tenth_default().phases
        ),
    )


def _start_lifecycle(config: GameConfig | None = None) -> GameLifecycle:
    lifecycle = GameLifecycle()
    lifecycle.start(_config() if config is None else config)
    return lifecycle


def _state(lifecycle: GameLifecycle) -> GameStatePayload:
    payload = lifecycle.to_payload()
    return payload["state"]


def _pending_request(lifecycle: GameLifecycle) -> DecisionRequest:
    return lifecycle.decision_controller.queue.peek_next()


def _request_payload(request: DecisionRequest) -> dict[str, JsonValue]:
    assert isinstance(request.payload, dict)
    return request.payload


def _public_secondary_choices(payload: dict[str, JsonValue]) -> list[JsonValue]:
    choices = payload["secondary_mission_choices"]
    assert isinstance(choices, list)
    return choices


def _current_battle_phase(lifecycle: GameLifecycle) -> BattlePhaseKind | None:
    assert lifecycle.state is not None
    return lifecycle.state.current_battle_phase


def _submit_pending(lifecycle: GameLifecycle, *, option_id: str, result_number: int) -> None:
    request = _pending_request(lifecycle)
    result = DecisionResult.for_request(
        result_id=f"decision-result-{result_number:06d}",
        request=request,
        selected_option_id=option_id,
    )
    lifecycle.submit_decision(result)


def _advance_to_secondary_mission_step(lifecycle: GameLifecycle) -> None:
    while lifecycle.state is not None and (
        lifecycle.state.current_setup_step is not SetupStep.SELECT_SECONDARY_MISSIONS
    ):
        lifecycle.advance_until_decision_or_terminal()


def _choose_secondaries(
    lifecycle: GameLifecycle,
    *,
    player_a_option: str = "fixed:assassination:bring_it_down",
    player_b_option: str = "fixed:assassination:bring_it_down",
) -> None:
    _advance_to_secondary_mission_step(lifecycle)
    status = lifecycle.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.actor_id == "player-a"
    assert status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    _submit_pending(lifecycle, option_id=player_a_option, result_number=1)

    status = lifecycle.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.actor_id == "player-b"
    assert status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    _submit_pending(lifecycle, option_id=player_b_option, result_number=2)


def _advance_to_battle(lifecycle: GameLifecycle) -> None:
    _choose_secondaries(lifecycle)
    while lifecycle.state is not None and lifecycle.state.stage is not GameLifecycleStage.BATTLE:
        lifecycle.advance_until_decision_or_terminal()


def test_new_game_starts_at_muster_armies_and_records_descriptor_hash() -> None:
    config = _config()
    lifecycle = GameLifecycle()
    status = lifecycle.start(config)

    assert status.status_kind is LifecycleStatusKind.ADVANCED
    assert lifecycle.state is not None
    assert lifecycle.state.stage is GameLifecycleStage.SETUP
    assert lifecycle.state.current_setup_step is SetupStep.MUSTER_ARMIES
    assert lifecycle.state.ruleset_descriptor_hash == config.ruleset_descriptor.descriptor_hash
    assert _state(lifecycle)["ruleset_descriptor_hash"] == config.ruleset_descriptor.descriptor_hash


def test_setup_steps_advance_in_ruleset_descriptor_order() -> None:
    lifecycle = _start_lifecycle()
    assert lifecycle.state is not None
    observed_steps = [lifecycle.state.current_setup_step]

    while lifecycle.state.stage is GameLifecycleStage.SETUP:
        status = lifecycle.advance_until_decision_or_terminal()
        if status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION:
            selected_option = (
                "tactical"
                if status.decision_request is not None
                and status.decision_request.actor_id == "player-a"
                else "fixed:assassination:bring_it_down"
            )
            result_number = len(lifecycle.decision_controller.records) + 1
            _submit_pending(lifecycle, option_id=selected_option, result_number=result_number)
        if lifecycle.state.stage is GameLifecycleStage.SETUP:
            current_step = lifecycle.state.current_setup_step
            if observed_steps[-1] is not current_step:
                observed_steps.append(current_step)

    assert observed_steps == list(RulesetDescriptor.warhammer_40000_tenth().setup_sequence.steps)


def test_lifecycle_reads_setup_order_from_ruleset_descriptor() -> None:
    setup_steps = (
        SetupStepKind.MUSTER_ARMIES,
        SetupStepKind.SELECT_SECONDARY_MISSIONS,
        SetupStepKind.SELECT_MISSION,
        SetupStepKind.CREATE_BATTLEFIELD,
        SetupStepKind.DETERMINE_ATTACKER_DEFENDER,
        SetupStepKind.DECLARE_BATTLE_FORMATIONS,
        SetupStepKind.DEPLOY_ARMIES,
        SetupStepKind.REDEPLOY_UNITS,
        SetupStepKind.DETERMINE_FIRST_TURN,
        SetupStepKind.RESOLVE_PREBATTLE_ACTIONS,
    )
    lifecycle = _start_lifecycle(
        _config(ruleset_descriptor=_descriptor_with_sequences(setup_steps=setup_steps))
    )

    lifecycle.advance_until_decision_or_terminal()

    assert lifecycle.state is not None
    assert lifecycle.state.current_setup_step is SetupStep.SELECT_SECONDARY_MISSIONS


def test_setup_completion_enters_battle_round_one_command_phase() -> None:
    lifecycle = _start_lifecycle()

    _advance_to_battle(lifecycle)

    assert lifecycle.state is not None
    assert lifecycle.state.stage is GameLifecycleStage.BATTLE
    assert lifecycle.state.battle_round == 1
    assert lifecycle.state.active_player_id == "player-a"
    assert lifecycle.state.current_battle_phase is BattlePhase.COMMAND


def test_battle_phases_advance_command_movement_shooting_charge_fight() -> None:
    lifecycle = _start_lifecycle()
    _advance_to_battle(lifecycle)

    assert lifecycle.state is not None
    assert _current_battle_phase(lifecycle) is BattlePhase.COMMAND
    lifecycle.advance_until_decision_or_terminal()
    assert _current_battle_phase(lifecycle) is BattlePhase.MOVEMENT
    lifecycle.advance_until_decision_or_terminal()
    assert _current_battle_phase(lifecycle) is BattlePhase.SHOOTING
    lifecycle.advance_until_decision_or_terminal()
    assert _current_battle_phase(lifecycle) is BattlePhase.CHARGE
    lifecycle.advance_until_decision_or_terminal()
    assert _current_battle_phase(lifecycle) is BattlePhase.FIGHT


def test_lifecycle_reads_battle_phase_order_from_ruleset_descriptor() -> None:
    descriptor = _descriptor_with_sequences(
        battle_phases=(
            BattlePhaseKind.COMMAND,
            BattlePhaseKind.SHOOTING,
            BattlePhaseKind.MOVEMENT,
            BattlePhaseKind.CHARGE,
            BattlePhaseKind.FIGHT,
        )
    )
    lifecycle = _start_lifecycle(_config(ruleset_descriptor=descriptor))
    _advance_to_battle(lifecycle)

    lifecycle.advance_until_decision_or_terminal()

    assert lifecycle.state is not None
    assert lifecycle.state.current_battle_phase is BattlePhase.SHOOTING


def test_phase_wrap_switches_active_player() -> None:
    lifecycle = _start_lifecycle()
    _advance_to_battle(lifecycle)

    for _ in range(5):
        lifecycle.advance_until_decision_or_terminal()

    assert lifecycle.state is not None
    assert lifecycle.state.battle_round == 1
    assert lifecycle.state.active_player_id == "player-b"
    assert lifecycle.state.current_battle_phase is BattlePhase.COMMAND


def test_battle_round_increments_after_all_players_complete_fight_phase() -> None:
    lifecycle = _start_lifecycle()
    _advance_to_battle(lifecycle)

    for _ in range(10):
        lifecycle.advance_until_decision_or_terminal()

    assert lifecycle.state is not None
    assert lifecycle.state.battle_round == 2
    assert lifecycle.state.active_player_id == "player-a"
    assert lifecycle.state.current_battle_phase is BattlePhase.COMMAND


def test_lifecycle_stops_at_decision_request() -> None:
    lifecycle = _start_lifecycle()
    _advance_to_secondary_mission_step(lifecycle)

    status = lifecycle.advance_until_decision_or_terminal()

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.actor_id == "player-a"
    assert status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    assert lifecycle.state is not None
    assert lifecycle.state.current_setup_step is SetupStep.SELECT_SECONDARY_MISSIONS


def test_select_secondary_missions_emits_secret_requests_for_both_players() -> None:
    lifecycle = _start_lifecycle()
    _advance_to_secondary_mission_step(lifecycle)

    first_status = lifecycle.advance_until_decision_or_terminal()
    assert first_status.decision_request is not None
    assert _request_payload(first_status.decision_request)["secret"] is True
    assert first_status.decision_request.actor_id == "player-a"
    _submit_pending(lifecycle, option_id="tactical", result_number=1)

    second_status = lifecycle.advance_until_decision_or_terminal()
    assert second_status.decision_request is not None
    assert _request_payload(second_status.decision_request)["secret"] is True
    assert second_status.decision_request.actor_id == "player-b"
    _submit_pending(lifecycle, option_id="fixed:assassination:bring_it_down", result_number=2)

    assert lifecycle.state is not None
    assert lifecycle.state.missing_secondary_mission_player_ids() == ()


def test_secondary_mission_public_payload_does_not_leak_hidden_opponent_choices() -> None:
    lifecycle = _start_lifecycle()
    _choose_secondaries(
        lifecycle,
        player_a_option="tactical",
        player_b_option="fixed:bring_it_down:cleanse",
    )
    assert lifecycle.state is not None

    player_a_payload = lifecycle.state.to_public_payload(viewer_player_id="player-a")
    player_b_payload = lifecycle.state.to_public_payload(viewer_player_id="player-b")
    player_a_blob = json.dumps(player_a_payload, sort_keys=True)

    assert "bring_it_down" not in player_a_blob
    assert "cleanse" not in player_a_blob
    assert {
        "player_id": "player-b",
        "selected": True,
        "hidden": True,
    } in _public_secondary_choices(player_a_payload)
    assert "bring_it_down" in json.dumps(player_b_payload, sort_keys=True)
    assert "cleanse" in json.dumps(player_b_payload, sort_keys=True)


def test_tactical_secondary_draws_occur_in_command_phase_not_setup() -> None:
    lifecycle = _start_lifecycle()
    _choose_secondaries(
        lifecycle,
        player_a_option="tactical",
        player_b_option="fixed:assassination:bring_it_down",
    )
    setup_decision_types = [
        record.request.decision_type for record in lifecycle.decision_controller.records
    ]

    while lifecycle.state is not None and lifecycle.state.stage is not GameLifecycleStage.BATTLE:
        status = lifecycle.advance_until_decision_or_terminal()
        assert status.status_kind is not LifecycleStatusKind.WAITING_FOR_DECISION

    status = lifecycle.advance_until_decision_or_terminal()

    assert setup_decision_types == [
        SECONDARY_MISSION_DECISION_TYPE,
        SECONDARY_MISSION_DECISION_TYPE,
    ]
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == TACTICAL_SECONDARY_DRAW_DECISION_TYPE
    assert status.decision_request.actor_id == "player-a"
    assert _request_payload(status.decision_request)["phase"] == BattlePhase.COMMAND.value


def test_tactical_secondary_draw_decision_records_command_draw_and_advances() -> None:
    lifecycle = _start_lifecycle()
    _choose_secondaries(
        lifecycle,
        player_a_option="tactical",
        player_b_option="fixed:assassination:bring_it_down",
    )
    while lifecycle.state is not None and lifecycle.state.stage is not GameLifecycleStage.BATTLE:
        lifecycle.advance_until_decision_or_terminal()

    status = lifecycle.advance_until_decision_or_terminal()
    assert status.decision_request is not None
    draw_result = DecisionResult.for_request(
        result_id="decision-result-000003",
        request=status.decision_request,
        selected_option_id="draw",
    )
    lifecycle.submit_decision(draw_result)

    assert lifecycle.state is not None
    assert lifecycle.state.current_battle_phase is BattlePhase.MOVEMENT
    assert len(lifecycle.state.tactical_secondary_draws) == 1
    draw = lifecycle.state.tactical_secondary_draws[0]
    assert draw.player_id == "player-a"
    assert draw.battle_round == 1
    assert draw.draw_count == 2
    assert lifecycle.decision_controller.queue.pending_requests == ()
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    assert GameLifecycle.from_payload(payload).to_payload() == lifecycle.to_payload()


def test_descriptor_hash_is_recorded_in_lifecycle_replay_payloads() -> None:
    config = _config()
    lifecycle = _start_lifecycle(config)
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    assert payload["config"] is not None
    assert payload["config"]["ruleset_descriptor"]["descriptor_hash"] == (
        config.ruleset_descriptor.descriptor_hash
    )
    assert payload["state"]["ruleset_descriptor_hash"] == config.ruleset_descriptor.descriptor_hash
    assert GameLifecycle.from_payload(payload).to_payload() == lifecycle.to_payload()


def test_no_ui_or_headless_specific_phase_path_exists() -> None:
    public_methods = {
        name
        for name, _member in inspect.getmembers(GameLifecycle, inspect.isfunction)
        if not name.startswith("_")
    }

    assert public_methods == {
        "advance_until_decision_or_terminal",
        "start",
        "submit_decision",
        "to_payload",
    }
    assert callable(GameLifecycle.from_payload)


def test_lifecycle_and_command_handler_fail_fast_on_invalid_entry_points() -> None:
    lifecycle = GameLifecycle()
    with pytest.raises(GameLifecycleError, match="has not started"):
        lifecycle.advance_until_decision_or_terminal()

    config = _config()
    lifecycle.start(config)
    with pytest.raises(GameLifecycleError, match="already started"):
        lifecycle.start(config)

    _advance_to_battle(lifecycle)
    assert CommandPhaseHandler().phase is BattlePhase.COMMAND
    lifecycle.advance_until_decision_or_terminal()
    assert lifecycle.state is not None
    assert lifecycle.state.current_battle_phase is BattlePhase.MOVEMENT
    with pytest.raises(GameLifecycleError, match="only in the COMMAND phase"):
        CommandPhaseHandler().begin_phase(
            state=lifecycle.state,
            decisions=lifecycle.decision_controller,
        )


def test_lifecycle_status_payloads_are_serializable_and_fail_fast() -> None:
    advanced = LifecycleStatus.advanced(
        stage=GameLifecycleStage.SETUP,
        payload={"step": SetupStep.MUSTER_ARMIES.value},
    )
    terminal = LifecycleStatus.terminal(
        stage=GameLifecycleStage.COMPLETE,
        message="complete",
    )
    unsupported = LifecycleStatus.unsupported(
        stage=GameLifecycleStage.BATTLE,
        message="phase body unsupported",
    )

    for status in (advanced, terminal, unsupported):
        payload = json.loads(json.dumps(status.to_payload(), sort_keys=True))
        assert LifecycleStatus.from_payload(payload).to_payload() == status.to_payload()

    with pytest.raises(GameLifecycleError, match="requires a decision_request"):
        LifecycleStatus(
            stage=GameLifecycleStage.SETUP,
            status_kind=LifecycleStatusKind.WAITING_FOR_DECISION,
        )
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        LifecycleStatus.terminal(stage=GameLifecycleStage.COMPLETE, message=" ")
    with pytest.raises(GameLifecycleError, match="token must be a string"):
        game_lifecycle_stage_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported GameLifecycleStage"):
        game_lifecycle_stage_from_token("unsupported")
    with pytest.raises(GameLifecycleError, match="token must be a string"):
        lifecycle_status_kind_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported LifecycleStatusKind"):
        lifecycle_status_kind_from_token("bad_kind")
