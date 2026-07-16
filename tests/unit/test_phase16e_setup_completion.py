from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from tests.deployment_submission_helpers import (
    default_deployment_pose,
    submit_all_deployments_if_pending,
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import (
    ArmyMusterRequest,
    DedicatedTransportCapacityProfile,
    DedicatedTransportManifest,
    muster_army,
)
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.deployment import create_empty_deployment_battlefield_state
from warhammer40k_core.engine.event_log import EventLog, JsonValue
from warhammer40k_core.engine.game_state import (
    DedicatedTransportSetupConsequence,
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.setup_completion import (
    SetupCompletionGate,
    SetupCompletionViolationCode,
    SetupLegalityReport,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.transports import TransportCapacityProfile, TransportCargoState
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def test_phase16e_full_setup_enters_battle_through_completion_gate() -> None:
    lifecycle, deployment_status = _advance_to_first_deployment_selection()

    follow_up = submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase16e-deploy",
    )

    assert lifecycle.state is not None
    assert lifecycle.state.stage is GameLifecycleStage.BATTLE
    assert lifecycle.state.battle_round == 1
    assert lifecycle.state.active_player_id == "player-a"
    assert lifecycle.state.current_battle_phase is not None
    assert follow_up.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.UNSUPPORTED,
        LifecycleStatusKind.TERMINAL,
    }

    battle_started = _single_event_payload(lifecycle, "battle_started")
    legality_report = _payload_object(battle_started, "setup_legality_report")
    pre_checkpoint = _payload_object(battle_started, "pre_battle_checkpoint")
    post_checkpoint = _payload_object(battle_started, "post_battle_start_checkpoint")

    assert battle_started["record_id"] == "battle-start:phase16e-game:round-01"
    assert battle_started["completed_setup_step"] == SetupStep.RESOLVE_PREBATTLE_ACTIONS.value
    assert battle_started["battle_round"] == 1
    assert battle_started["active_player_id"] == "player-a"
    assert battle_started["first_battle_phase"] == "command"
    assert legality_report["is_legal"] is True
    assert legality_report["violations"] == []
    assert pre_checkpoint["stage"] == GameLifecycleStage.SETUP.value
    assert post_checkpoint["stage"] == GameLifecycleStage.BATTLE.value

    encoded = json.dumps(lifecycle.to_payload(), sort_keys=True)
    assert "phase10a_deterministic_bridge" not in encoded
    assert " object at 0x" not in encoded
    assert "<" not in encoded


def test_phase16e_gate_rejects_direct_setup_step_bypass_with_unplaced_units() -> None:
    config = _config()
    state = _state_at_final_setup_step_without_deployments(config)
    gate = SetupCompletionGate()

    report = gate.evaluate(
        state=state,
        decisions=DecisionController(),
        config=config,
    )

    assert report.is_legal is False
    assert SetupCompletionViolationCode.UNRESOLVED_DEPLOYMENT.value in _violation_codes(report)
    assert state.stage is GameLifecycleStage.SETUP
    assert state.battle_round == 0


def test_phase16e_game_state_final_setup_step_requires_completion_gate() -> None:
    state = _state_at_final_setup_step_without_deployments(_config())

    with pytest.raises(
        GameLifecycleError,
        match="Final setup step completion requires the setup completion gate",
    ):
        state.complete_current_setup_step()

    assert state.stage is GameLifecycleStage.SETUP
    assert state.current_setup_step is SetupStep.RESOLVE_PREBATTLE_ACTIONS
    assert state.battle_round == 0


def test_phase16e_gate_rejects_pending_setup_decisions_without_queue_pop() -> None:
    config = _config()
    state = _pre_battle_gate_ready_state()
    decisions = DecisionController()
    pending_request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type="phase16e_pending_setup_probe",
        actor_id="player-a",
        payload={"probe": "phase16e"},
        options=(
            DecisionOption(
                option_id="phase16e-probe-option",
                label="Phase 16E Probe Option",
                payload={"probe": "phase16e"},
            ),
        ),
    )
    decisions.request_decision(pending_request)

    status = SetupCompletionGate().invalid_status_if_not_ready(
        state=state,
        decisions=decisions,
        config=config,
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    report_payload = status.payload["setup_legality_report"]
    assert isinstance(report_payload, dict)
    violations = report_payload["violations"]
    assert isinstance(violations, list)
    assert any(
        isinstance(violation, dict)
        and violation["violation_code"] == SetupCompletionViolationCode.PENDING_DECISION_QUEUE.value
        for violation in violations
    )
    assert decisions.queue.peek_next() == pending_request
    assert state.stage is GameLifecycleStage.SETUP


def test_phase16e_gate_rejects_incomplete_setup_with_reaction_queue() -> None:
    config = _config()
    state = GameState.from_config(config)
    status = SetupCompletionGate().invalid_status_if_not_ready(
        state=state,
        decisions=DecisionController(),
        config=config,
        reaction_frame_count=2,
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    report_payload = status.payload["setup_legality_report"]
    assert isinstance(report_payload, dict)
    violations = report_payload["violations"]
    assert isinstance(violations, list)
    codes = {
        violation["violation_code"]
        for violation in violations
        if isinstance(violation, dict) and isinstance(violation["violation_code"], str)
    }
    assert SetupCompletionViolationCode.SETUP_SEQUENCE_INCOMPLETE.value in codes
    assert SetupCompletionViolationCode.REACTION_QUEUE_NOT_DRAINED.value in codes
    assert SetupCompletionViolationCode.MISSING_ARMY.value in codes
    assert SetupCompletionViolationCode.UNRESOLVED_SECONDARY_MISSIONS.value in codes
    assert SetupCompletionViolationCode.MISSING_BATTLEFIELD.value in codes
    assert state.stage is GameLifecycleStage.SETUP
    assert state.battle_round == 0


def test_phase16e_gate_rejects_empty_dedicated_transport_manifest_without_consequence() -> None:
    config = _empty_dedicated_transport_config()
    state = _dedicated_transport_state_without_transport_reconciliation(config)

    report = SetupCompletionGate().evaluate(
        state=state,
        decisions=DecisionController(),
        config=config,
    )

    assert report.is_legal is False
    assert SetupCompletionViolationCode.ILLEGAL_DEDICATED_TRANSPORT_SETUP.value in (
        _violation_codes(report)
    )
    transport_violations = [
        violation
        for violation in report.violations
        if violation.unit_instance_id == "army-alpha:transport-unit"
    ]
    assert [violation.field for violation in transport_violations] == [
        "dedicated_transport_setup_consequences"
    ]
    assert state.stage is GameLifecycleStage.SETUP
    assert state.battle_round == 0


def test_phase16e_gate_rejects_empty_manifest_with_cargo_or_deployment() -> None:
    config = _empty_dedicated_transport_config()
    state = _dedicated_transport_state_without_transport_reconciliation(config)
    state.transport_cargo_states.append(
        _transport_cargo_state(
            transport_unit_instance_id="army-alpha:transport-unit",
            embarked_unit_instance_ids=(),
        )
    )
    _place_transport(state)

    report = SetupCompletionGate().evaluate(
        state=state,
        decisions=DecisionController(),
        config=config,
    )

    assert report.is_legal is False
    transport_violations = [
        violation
        for violation in report.violations
        if violation.unit_instance_id == "army-alpha:transport-unit"
    ]
    assert [violation.field for violation in transport_violations] == [
        "dedicated_transport_setup_consequences",
        "transport_cargo_states",
        "battlefield_state",
    ]
    assert state.stage is GameLifecycleStage.SETUP
    assert state.battle_round == 0


def test_phase16e_gate_rejects_non_empty_dedicated_transport_manifest_without_cargo() -> None:
    config = _cargo_dedicated_transport_config()
    state = _dedicated_transport_state_without_transport_reconciliation(config)

    report = SetupCompletionGate().evaluate(
        state=state,
        decisions=DecisionController(),
        config=config,
    )

    assert report.is_legal is False
    transport_violations = [
        violation
        for violation in report.violations
        if violation.unit_instance_id == "army-alpha:transport-unit"
    ]
    assert [violation.field for violation in transport_violations] == ["transport_cargo_states"]
    assert transport_violations[0].detail == {
        "source_id": "manifest:transport-unit",
        "expected_embarked_unit_instance_ids": ["army-alpha:passenger-unit"],
    }
    assert state.stage is GameLifecycleStage.SETUP
    assert state.battle_round == 0


def test_phase16e_gate_rejects_non_empty_manifest_with_mismatched_cargo_or_consequence() -> None:
    config = _cargo_dedicated_transport_config()
    state = _dedicated_transport_state_without_transport_reconciliation(config)
    state.transport_cargo_states.append(
        _transport_cargo_state(
            transport_unit_instance_id="army-alpha:transport-unit",
            embarked_unit_instance_ids=(),
        )
    )
    state.dedicated_transport_setup_consequences.append(
        DedicatedTransportSetupConsequence.empty_dedicated_transport(
            player_id="player-a",
            transport_unit_instance_id="army-alpha:transport-unit",
            source_id="manifest:transport-unit",
        )
    )

    report = SetupCompletionGate().evaluate(
        state=state,
        decisions=DecisionController(),
        config=config,
    )

    assert report.is_legal is False
    transport_violations = [
        violation
        for violation in report.violations
        if violation.unit_instance_id == "army-alpha:transport-unit"
    ]
    assert [violation.field for violation in transport_violations] == [
        "transport_cargo_states",
        "dedicated_transport_setup_consequences",
    ]
    assert state.stage is GameLifecycleStage.SETUP
    assert state.battle_round == 0


def test_phase16e_lifecycle_replay_round_trip_preserves_battle_start_record() -> None:
    lifecycle, deployment_status = _advance_to_first_deployment_selection()
    submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase16e-replay-deploy",
    )
    payload = lifecycle.to_payload()

    restored = GameLifecycle.from_payload(
        cast(GameLifecyclePayload, json.loads(json.dumps(payload, sort_keys=True)))
    )

    assert restored.to_payload() == payload
    assert _single_event_payload(restored, "battle_started") == _single_event_payload(
        lifecycle,
        "battle_started",
    )


def test_phase16e_setup_gate_paths_do_not_call_deterministic_placement_bridge() -> None:
    root = Path(__file__).resolve().parents[2]
    checked_paths = (
        root / "src" / "warhammer40k_core" / "engine" / "setup_completion.py",
        root / "src" / "warhammer40k_core" / "engine" / "setup_flow.py",
        root / "src" / "warhammer40k_core" / "engine" / "lifecycle.py",
    )

    offenders = [
        str(path.relative_to(root))
        for path in checked_paths
        if "create_deterministic_battlefield_scenario" in path.read_text(encoding="utf-8")
        or "phase10a_deterministic_bridge" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_phase16e_setup_completion_events_do_not_shift_later_rng_history() -> None:
    setup_step_payload: dict[str, JsonValue] = {
        "game_id": "phase16e-rng-game",
        "completed_step": SetupStep.RESOLVE_PREBATTLE_ACTIONS.value,
    }
    base_log = EventLog()
    base_log.append("setup_step_completed", setup_step_payload)
    augmented_log = EventLog()
    augmented_log.append("setup_completion_gate_passed", {"game_id": "phase16e-rng-game"})
    augmented_log.append("battle_started", {"game_id": "phase16e-rng-game"})
    augmented_log.append("setup_step_completed", setup_step_payload)
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=5, sides=6),
        reason="Phase 16E RNG neutrality probe",
        roll_type="phase16e_rng_neutrality_probe",
        actor_id="phase16e-rng",
    )

    base_roll = DiceRollManager("phase16e-rng-seed", event_log=base_log).roll(spec)
    augmented_roll = DiceRollManager("phase16e-rng-seed", event_log=augmented_log).roll(spec)

    assert augmented_roll.current_values == base_roll.current_values
    assert augmented_roll.current_total == base_roll.current_total


def _advance_to_first_deployment_selection(
    config: GameConfig | None = None,
) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle = GameLifecycle()
    lifecycle.start(_config() if config is None else config)
    first_status = lifecycle.advance_until_decision_or_terminal()
    assert _decision_request(first_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    second_status = _submit_result(
        lifecycle,
        request=_decision_request(first_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase16e-secondary-player-a",
    )
    assert _decision_request(second_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    deployment_status = _submit_result(
        lifecycle,
        request=_decision_request(second_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase16e-secondary-player-b",
    )
    return lifecycle, deployment_status


def _pre_battle_gate_ready_state() -> GameState:
    config = _config()
    lifecycle, deployment_status = _advance_to_first_deployment_selection(config)
    submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase16e-ready-deploy",
    )
    assert lifecycle.state is not None
    payload = lifecycle.state.to_payload()
    payload["stage"] = GameLifecycleStage.SETUP.value
    payload["setup_step_index"] = len(lifecycle.state.setup_sequence) - 1
    payload["battle_phase_index"] = None
    payload["battle_round"] = 0
    payload["active_player_id"] = None
    payload["command_step_state"] = None
    payload["primary_objective_turn_start_states"] = []
    return GameState.from_payload(payload)


def _state_at_final_setup_step_without_deployments(config: GameConfig) -> GameState:
    state = GameState.from_config(config)
    for request in config.army_muster_requests:
        state.record_army_definition(muster_army(catalog=config.army_catalog, request=request))
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(
            player_id="player-a",
            mode=SecondaryMissionMode.FIXED,
            fixed_mission_ids=("assassination", "bring_it_down"),
        )
    )
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(
            player_id="player-b",
            mode=SecondaryMissionMode.FIXED,
            fixed_mission_ids=("assassination", "bring_it_down"),
        )
    )
    _advance_setup_state_to_step(state, SetupStep.CREATE_BATTLEFIELD)
    state.record_battlefield_state(create_empty_deployment_battlefield_state(state=state))
    _advance_setup_state_to_step(state, SetupStep.RESOLVE_PREBATTLE_ACTIONS)
    return state


def _dedicated_transport_state_without_transport_reconciliation(config: GameConfig) -> GameState:
    state = GameState.from_config(config)
    for request in config.army_muster_requests:
        state.record_army_definition(muster_army(catalog=config.army_catalog, request=request))
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(
            player_id="player-a",
            mode=SecondaryMissionMode.FIXED,
            fixed_mission_ids=("area-denial", "assassination"),
        )
    )
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(
            player_id="player-b",
            mode=SecondaryMissionMode.FIXED,
            fixed_mission_ids=("area-denial", "assassination"),
        )
    )
    _advance_setup_state_to_step(state, SetupStep.CREATE_BATTLEFIELD)
    state.record_battlefield_state(create_empty_deployment_battlefield_state(state=state))
    _advance_setup_state_to_step(state, SetupStep.RESOLVE_PREBATTLE_ACTIONS)
    assert not state.dedicated_transport_setup_consequences
    assert not state.transport_cargo_states
    return state


def _transport_cargo_state(
    *,
    transport_unit_instance_id: str,
    embarked_unit_instance_ids: tuple[str, ...],
) -> TransportCargoState:
    return TransportCargoState(
        player_id="player-a",
        transport_unit_instance_id=transport_unit_instance_id,
        capacity_profile=TransportCapacityProfile(
            transport_datasheet_id="core-transport",
            max_model_count=6,
            allowed_keywords=("Infantry",),
            excluded_keywords=(),
            source_id="transport-capacity:core-transport:6",
        ),
        embarked_unit_instance_ids=embarked_unit_instance_ids,
        phase_battle_round=None,
        started_phase_embarked_unit_instance_ids=embarked_unit_instance_ids,
        disembarked_this_phase_unit_instance_ids=(),
    )


def _place_transport(state: GameState) -> None:
    battlefield = state.battlefield_state
    assert battlefield is not None
    transport_model_id = "army-alpha:transport-unit:core-transport:001"
    state.battlefield_state = battlefield.with_added_unit_placement(
        UnitPlacement(
            army_id="army-alpha",
            player_id="player-a",
            unit_instance_id="army-alpha:transport-unit",
            model_placements=(
                ModelPlacement(
                    army_id="army-alpha",
                    player_id="player-a",
                    unit_instance_id="army-alpha:transport-unit",
                    model_instance_id=transport_model_id,
                    pose=default_deployment_pose(20, "player-a", transport_model_id),
                ),
            ),
        )
    )


def _advance_setup_state_to_step(state: GameState, target_step: SetupStep) -> None:
    while state.current_setup_step is not target_step:
        state.complete_current_setup_step()


def _submit_result(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=option_id,
        )
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _single_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, JsonValue]:
    matches = [
        event.payload
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == event_type
    ]
    assert len(matches) == 1
    payload = matches[0]
    assert isinstance(payload, dict)
    return payload


def _payload_object(payload: dict[str, JsonValue], key: str) -> dict[str, JsonValue]:
    value = payload[key]
    assert isinstance(value, dict)
    return value


def _violation_codes(report: SetupLegalityReport) -> set[str]:
    return {violation.violation_code.value for violation in report.violations}


def _config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase16e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=_army_muster_requests(catalog),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "assassination",
            "bring_it_down",
            "cleanse",
        ),
        mission_setup=_mission_setup(),
    )


def _empty_dedicated_transport_config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase16e-empty-dedicated-transport",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _transport_roster_request(catalog, embarked_unit_selection_ids=()),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "area-denial",
            "assassination",
            "bring_it_down",
        ),
        mission_setup=_mission_setup(),
    )


def _cargo_dedicated_transport_config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase16e-cargo-dedicated-transport",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _transport_roster_request(catalog, embarked_unit_selection_ids=("passenger-unit",)),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "area-denial",
            "assassination",
            "bring_it_down",
        ),
        mission_setup=_mission_setup(),
    )


def _transport_roster_request(
    catalog: ArmyCatalog,
    *,
    embarked_unit_selection_ids: tuple[str, ...],
) -> ArmyMusterRequest:
    passenger_selections = tuple(
        _unit_selection(unit_selection_id=selection_id)
        for selection_id in embarked_unit_selection_ids
    )
    return ArmyMusterRequest(
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
            *passenger_selections,
            _unit_selection(
                unit_selection_id="transport-unit",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        ),
        dedicated_transport_manifests=(
            DedicatedTransportManifest(
                transport_unit_selection_id="transport-unit",
                embarked_unit_selection_ids=embarked_unit_selection_ids,
                capacity_profile=DedicatedTransportCapacityProfile(
                    transport_datasheet_id="core-transport",
                    max_model_count=6,
                    allowed_keywords=("Infantry",),
                    excluded_keywords=(),
                    source_id="transport-capacity:core-transport:6",
                ),
                source_id=(
                    "manifest:empty"
                    if not embarked_unit_selection_ids
                    else "manifest:transport-unit"
                ),
            ),
        ),
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase16e-test")


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _army_muster_requests(catalog: ArmyCatalog) -> tuple[ArmyMusterRequest, ...]:
    return (
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
            unit_selection_id="intercessor-unit-2",
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
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=(_unit_selection(unit_selection_id=unit_selection_id),),
    )


def _unit_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str = "core-intercessor-like-infantry",
    model_profile_id: str = "core-intercessor-like",
    model_count: int = 5,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
    )
