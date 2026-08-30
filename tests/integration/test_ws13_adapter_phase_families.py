from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.deployment_submission_helpers import (
    default_deployment_pose,
    deployment_placement_payload_for_request,
)
from tests.movement_submission_helpers import straight_line_witness_for_unit
from tests.phase11c_command_phase_helpers import (
    complete_setup_through_gate,
    mustered_armies,
    phase11c_config,
    secondary_choice,
)
from tests.phase13b_shooting_declaration_helpers import (
    _proposal_from_request as shooting_declaration_proposal,
)
from tests.phase13b_shooting_declaration_helpers import (
    _shooting_lifecycle as shooting_lifecycle,
)
from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses
from tests.phase15c_fight_order_helpers import fight_lifecycle

from warhammer40k_core.adapters.event_stream import EventStreamCursor, EventStreamDeltaPayload
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition, StratagemDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import (
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.command_points import CommandPointGainStatus, CommandPointSourceKind
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.deployment import (
    SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
    SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_order import (
    ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
    FIGHT_ACTIVATION_DECISION_TYPE,
)
from warhammer40k_core.engine.fight_resolution import (
    CONSOLIDATE_ACTION,
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    MeleeDeclarationProposalRequest,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState, SecondaryMissionMode
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.phases.charge import (
    COMPLETE_CHARGE_PHASE_OPTION_ID,
    SELECT_CHARGING_UNIT_DECISION_TYPE,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.phases.shooting import (
    COMPLETE_SHOOTING_PHASE_OPTION_ID,
    SELECT_SHOOTING_TYPE_DECISION_TYPE,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_mission_choices import (
    PRIMARY_MISSION_CHOICE_RESOLVED_EVENT,
    SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
    punishment_choice_request,
)
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_DECISION_TYPE,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    chapter_approved_2026_27_mission_pack,
    warhammer_event_companion_2026_07_mission_pack,
)


@pytest.mark.integration
def test_local_session_drives_setup_movement_shooting_and_charge_via_facade() -> None:
    session = LocalGameSession()
    session.start(_config())
    status = session.advance_until_decision_or_terminal()
    cursor = _cursor_after(session, viewer_player_id="player-a")

    status = _submit_fixed_secondaries(session, status=status)
    status = _submit_all_deployments(session, status=status)
    _assert_pending_view(session, viewer_player_id="player-a", decision_type="select_movement_unit")

    status = _submit_pending_option(
        session,
        status=status,
        option_id="army-alpha:intercessor-unit-1",
        result_id="ws13-select-first-mover",
    )
    _assert_request(status, SELECT_MOVEMENT_ACTION_DECISION_TYPE)
    status = _submit_pending_option(
        session,
        status=status,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        result_id="ws13-first-normal-move",
    )
    status = _submit_movement_proposal(
        session,
        status=status,
        result_id="ws13-first-normal-move-proposal",
        dx=3.0,
    )
    status = _decline_optional_stratagem(session, status=status, result_id="ws13-decline-window")

    status = _submit_pending_option(
        session,
        status=status,
        option_id="army-alpha:intercessor-unit-2",
        result_id="ws13-select-second-mover",
    )
    _assert_request(status, SELECT_MOVEMENT_ACTION_DECISION_TYPE)
    status = _submit_pending_option(
        session,
        status=status,
        option_id=MovementPhaseActionKind.REMAIN_STATIONARY.value,
        result_id="ws13-second-remains-stationary",
    )
    status = _decline_optional_stratagem(
        session,
        status=status,
        result_id="ws13-decline-end-movement-window",
    )

    _assert_request(status, SELECT_SHOOTING_UNIT_DECISION_TYPE)
    _assert_event_types(
        session.events_since(cursor, viewer_player_id="player-a"),
        "movement_activation_completed",
        "battle_phase_completed",
    )
    cursor = _cursor_after(session, viewer_player_id="player-a")

    status = _submit_pending_option(
        session,
        status=status,
        option_id=COMPLETE_SHOOTING_PHASE_OPTION_ID,
        result_id="ws13-complete-shooting",
    )
    _assert_request(status, SELECT_MOVEMENT_UNIT_DECISION_TYPE)
    _assert_event_types(
        session.events_since(cursor, viewer_player_id="player-a"),
        "shooting_phase_completed",
        "battle_phase_completed",
    )
    _assert_pending_view(session, viewer_player_id="player-b", decision_type="select_movement_unit")


@pytest.mark.integration
def test_local_session_projects_and_completes_one_attached_movement_activation() -> None:
    bodyguard = UnitMusterSelection(
        unit_selection_id="attached-bodyguard",
        datasheet_id="core-intercessor-like-infantry",
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
    )
    leader = UnitMusterSelection(
        unit_selection_id="attached-leader",
        datasheet_id="core-character-leader",
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
    )
    config = phase11c_config(
        game_id="ws13-attached-movement-projection",
        player_a_units=(bodyguard, leader),
        player_a_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="attached-leader",
                bodyguard_unit_selection_id="attached-bodyguard",
            ),
        ),
    )
    session = LocalGameSession()
    session.start(config)
    status = _submit_fixed_secondaries(
        session,
        status=session.advance_until_decision_or_terminal(),
    )
    status = _submit_all_deployments(session, status=status)
    request = _assert_request(status, SELECT_MOVEMENT_UNIT_DECISION_TYPE)
    state = session.lifecycle.state
    assert state is not None
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id="army-alpha:attached-bodyguard",
    )
    canonical_id = rules_unit.unit_instance_id
    component_ids = rules_unit.component_unit_instance_ids
    model_ids = tuple(sorted(model.model_instance_id for model in rules_unit.alive_models()))

    assert tuple(option.option_id for option in request.options) == (canonical_id,)
    option_payload = _json_object(request.option_by_id(canonical_id).payload)
    assert option_payload["component_unit_instance_ids"] == list(component_ids)
    assert option_payload["model_instance_ids"] == list(model_ids)
    for viewer_player_id in state.player_ids:
        pending = session.view(viewer_player_id=viewer_player_id)["pending_decision"]
        assert pending is not None
        assert [option["option_id"] for option in pending["options"]] == [canonical_id]
        assert pending["options"][0]["payload"] == option_payload

    status = session.submit_option(
        request_id=request.request_id,
        option_id=canonical_id,
        result_id="ws13-attached-movement-select",
    )
    action_request = _assert_request(status, SELECT_MOVEMENT_ACTION_DECISION_TYPE)
    status = session.submit_option(
        request_id=action_request.request_id,
        option_id=MovementPhaseActionKind.REMAIN_STATIONARY.value,
        result_id="ws13-attached-movement-remain",
    )

    completion_events = tuple(
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "movement_activation_completed"
    )
    assert len(completion_events) == 1
    completion_payload = _json_object(completion_events[0].payload)
    assert completion_payload["unit_instance_id"] == canonical_id
    assert completion_payload["unit_instance_id"] not in component_ids
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="replay:ws13:attached-movement")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


@pytest.mark.integration
def test_local_session_drives_charge_completion_via_projection_and_events() -> None:
    lifecycle, _units = charge_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(20.0, 20.0), model_count=5),
        game_id="ws13-charge-completion",
    )
    session = LocalGameSession(lifecycle=lifecycle)
    cursor = _cursor_after(session, viewer_player_id="player-a")

    status = session.advance_until_decision_or_terminal()
    request = _assert_request(status, SELECT_CHARGING_UNIT_DECISION_TYPE)
    _assert_pending_view(session, viewer_player_id="player-a", decision_type="select_charging_unit")
    assert COMPLETE_CHARGE_PHASE_OPTION_ID in {option.option_id for option in request.options}

    status = _submit_pending_option(
        session,
        status=status,
        option_id=COMPLETE_CHARGE_PHASE_OPTION_ID,
        result_id="ws13-complete-charge",
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    _assert_event_types(
        session.events_since(cursor, viewer_player_id="player-a"),
        "charge_phase_completed",
        "battle_phase_completed",
    )
    _assert_pending_view(session, viewer_player_id="player-b", decision_type="select_movement_unit")


@pytest.mark.integration
def test_local_session_drives_fight_pass_via_projection_and_events() -> None:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={
            "intercessor-1": Pose.at(10.0, 20.0),
            "enemy": Pose.at(30.0, 20.0),
        },
        game_id="ws13-fight-pass",
        charge_fights_first_unit_keys=("intercessor-1",),
    )
    session = LocalGameSession(lifecycle=lifecycle)
    cursor = _cursor_after(session, viewer_player_id="player-a")

    status = session.advance_until_decision_or_terminal()
    request = _assert_request(status, FIGHT_ACTIVATION_DECISION_TYPE)
    _assert_pending_view(
        session,
        viewer_player_id="player-a",
        decision_type="select_fight_activation",
    )
    assert ELIGIBLE_TO_FIGHT_PASS_OPTION_ID in {option.option_id for option in request.options}

    status = _submit_pending_option(
        session,
        status=status,
        option_id=ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
        result_id="ws13-fight-pass",
    )
    event_delta = session.events_since(cursor, viewer_player_id="player-a")

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert units["intercessor-1"].unit_instance_id in str(event_delta["events"])
    _assert_event_types(event_delta, "eligible_to_fight_pass_recorded")


@pytest.mark.integration
@pytest.mark.parametrize(
    ("scenario", "expected_violation", "records_attempt", "expects_retry"),
    [
        ("missing_field", "proposal_payload_missing_field", False, False),
        ("non_object", "proposal_payload_malformed", False, False),
        ("stale_request", "stale_proposal_request", False, False),
        ("proposal_kind_drift", "proposal_kind_drift", False, False),
        ("unit_drift", "proposal_unit_drift", False, False),
        ("no_move_witness", "no_move_witness_forbidden", False, False),
        ("target_missing_witness", "fight_movement_witness_required", False, False),
        ("witness_model_drift", "fight_movement_witness_model_drift", False, False),
        ("witness_start_drift", "fight_movement_witness_start_drift", False, False),
        ("spatial_context_drift", "spatial_context_drift", False, False),
        ("endpoint_only", "endpoint_only_path", True, True),
        ("over_distance", "movement_distance_exceeded", True, True),
    ],
)
def test_local_session_rejects_invalid_fight_movement_proposals_without_hidden_mutation(
    scenario: str,
    expected_violation: str,
    records_attempt: bool,
    expects_retry: bool,
) -> None:
    session, status, attacker_id, enemy_id = _fight_pile_in_facade_session(
        game_id=f"ws13-fight-movement-{scenario}"
    )
    request = _assert_request(status, MOVEMENT_PROPOSAL_DECISION_TYPE)
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement_before = state.battlefield_state.unit_placement_by_id(attacker_id).to_payload()
    event_cursor = _cursor_after(session, viewer_player_id="player-a")
    payload: JsonValue = _fight_pile_in_payload(
        session,
        proposal_request=proposal_request,
        target_unit_ids=(),
    )

    if scenario == "missing_field":
        payload = {}
    elif scenario == "non_object":
        payload = None
    elif scenario == "stale_request":
        payload = {
            **_json_object(payload),
            "proposal_request_id": f"{proposal_request.request_id}:stale",
        }
    elif scenario == "proposal_kind_drift":
        payload = {
            **_json_object(payload),
            "proposal_kind": ProposalKind.CONSOLIDATE.value,
            "movement_phase_action": CONSOLIDATE_ACTION,
            "movement_mode": MovementMode.CONSOLIDATE.value,
        }
    elif scenario == "unit_drift":
        payload = {**_json_object(payload), "unit_instance_id": enemy_id}
    elif scenario == "no_move_witness":
        payload = {
            **_json_object(payload),
            "witness": validate_json_value(
                straight_line_witness_for_unit(
                    session.lifecycle,
                    unit_instance_id=attacker_id,
                    dx=0.25,
                ).to_payload()
            ),
        }
    elif scenario == "target_missing_witness":
        payload = _fight_pile_in_payload(
            session,
            proposal_request=proposal_request,
            target_unit_ids=(enemy_id,),
        )
    elif scenario == "witness_model_drift":
        payload = _fight_pile_in_payload(
            session,
            proposal_request=proposal_request,
            target_unit_ids=(enemy_id,),
            witness=straight_line_witness_for_unit(
                session.lifecycle,
                unit_instance_id=enemy_id,
                dx=-0.25,
            ),
        )
    elif scenario == "witness_start_drift":
        witness = straight_line_witness_for_unit(
            session.lifecycle,
            unit_instance_id=attacker_id,
            dx=0.25,
        )
        witness = PathWitness.for_paths(
            tuple(
                (
                    model_id,
                    (
                        Pose.at(
                            poses[0].position.x + 0.1,
                            poses[0].position.y,
                            poses[0].position.z,
                            facing_degrees=poses[0].facing.degrees,
                        ),
                        *poses[1:],
                    ),
                )
                for model_id, poses in witness.model_paths
            )
        )
        payload = _fight_pile_in_payload(
            session,
            proposal_request=proposal_request,
            target_unit_ids=(enemy_id,),
            witness=witness,
        )
    elif scenario == "spatial_context_drift":
        witness = straight_line_witness_for_unit(
            session.lifecycle,
            unit_instance_id=attacker_id,
            dx=0.25,
        )
        _shift_unit_placement(session, unit_instance_id=attacker_id, dx=0.1)
        payload = _fight_pile_in_payload(
            session,
            proposal_request=proposal_request,
            target_unit_ids=(enemy_id,),
            witness=witness,
        )
    elif scenario == "endpoint_only":
        payload = _fight_pile_in_payload(
            session,
            proposal_request=proposal_request,
            target_unit_ids=(enemy_id,),
            witness=_endpoint_only_witness(
                session,
                unit_instance_id=attacker_id,
                dx=0.25,
            ),
        )
    elif scenario == "over_distance":
        payload = _fight_pile_in_payload(
            session,
            proposal_request=proposal_request,
            target_unit_ids=(enemy_id,),
            witness=straight_line_witness_for_unit(
                session.lifecycle,
                unit_instance_id=attacker_id,
                dx=3.5,
            ),
        )

    invalid = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=payload,
        result_id=f"ws13-fight-movement-{scenario}-result",
    )

    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert _first_proposal_violation(invalid) == expected_violation
    assert session.decision_record_count() == int(records_attempt)
    assert state.battlefield_state is not None
    if scenario != "spatial_context_drift":
        assert (
            state.battlefield_state.unit_placement_by_id(attacker_id).to_payload()
            == placement_before
        )
    pending = session.lifecycle.pending_decision_request()
    assert pending is not None
    assert (pending.request_id != request.request_id) is expects_retry
    if not expects_retry:
        assert pending.to_payload() == request.to_payload()
    delta = session.events_since(event_cursor, viewer_player_id="player-a")
    if records_attempt:
        _assert_event_types(delta, "decision_recorded", "fight_movement_invalid")
    elif scenario == "spatial_context_drift":
        _assert_event_types(delta, "movement_proposal_invalid")
    else:
        assert delta["events"] == []


@pytest.mark.integration
def test_local_session_accepts_no_move_fight_proposal_and_replays_continuation() -> None:
    session, status, attacker_id, _enemy_id = _fight_pile_in_facade_session(
        game_id="ws13-fight-movement-valid-no-move"
    )
    request = _assert_request(status, MOVEMENT_PROPOSAL_DECISION_TYPE)
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    cursor = _cursor_after(session, viewer_player_id="player-a")

    continued = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=_fight_pile_in_payload(
            session,
            proposal_request=proposal_request,
            target_unit_ids=(),
        ),
        result_id="ws13-fight-movement-valid-no-move-result",
    )

    next_request = _assert_request(continued)
    assert next_request.request_id != request.request_id
    assert session.decision_record_count() == 1
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_by_id(attacker_id)
    _assert_event_types(
        session.events_since(cursor, viewer_player_id="player-a"),
        "decision_recorded",
        "fight_movement_completed",
    )
    completed_event = next(
        event
        for event in reversed(session.lifecycle.decision_controller.event_log.records)
        if event.event_type == "fight_movement_completed"
    )
    completed_payload = _json_object(completed_event.payload)
    assert completed_payload["active_player_id"] == "player-a"
    assert "rules_unit_instance_id" not in _json_object(completed_payload["resolution"])
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="replay:ws13:fight-movement-no-move")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


@pytest.mark.integration
def test_local_session_moves_attached_rules_unit_once_and_replays_canonical_event() -> None:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("bodyguard", "leader"),
        enemy_unit_ids=("enemy",),
        origins={
            "bodyguard": Pose.at(10.0, 20.0),
            "leader": Pose.at(10.0, 21.7),
            "enemy": Pose.at(10.0, 18.0),
        },
        game_id="ws13-attached-fight-movement",
        alpha_unit_specs={
            "leader": ("core-character-leader", "core-character-leader", 1),
        },
        alpha_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader",
                bodyguard_unit_selection_id="bodyguard",
            ),
        ),
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=units["leader"].unit_instance_id,
    )
    canonical_id = rules_unit.unit_instance_id
    component_ids = rules_unit.component_unit_instance_ids
    before_y_by_model_id = {
        model.model_instance_id: model.pose.position.y
        for component_id in component_ids
        for model in state.battlefield_state.unit_placement_by_id(component_id).model_placements
    }
    session = LocalGameSession(lifecycle=lifecycle)
    status = session.advance_until_decision_or_terminal()
    request = _assert_request(status, MOVEMENT_PROPOSAL_DECISION_TYPE)
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    context = _json_object(proposal_request.context)

    assert proposal_request.unit_instance_id == canonical_id
    assert context["eligible_unit_ids"] == [canonical_id]
    assert context["legal_target_unit_instance_ids"] == [units["enemy"].unit_instance_id]

    continued = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=_fight_pile_in_payload(
            session,
            proposal_request=proposal_request,
            target_unit_ids=(units["enemy"].unit_instance_id,),
            witness=_straight_line_witness_for_rules_unit(
                session,
                unit_instance_id=canonical_id,
                dy=-0.25,
            ),
        ),
        result_id="ws13-attached-fight-movement-result",
    )

    assert continued.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert session.decision_record_count() == 1
    assert state.battlefield_state is not None
    for component_id in component_ids:
        placement = state.battlefield_state.unit_placement_by_id(component_id)
        for model in placement.model_placements:
            assert model.pose.position.y == before_y_by_model_id[model.model_instance_id] - 0.25
    completed_event = next(
        event
        for event in reversed(lifecycle.decision_controller.event_log.records)
        if event.event_type == "fight_movement_completed"
    )
    completed_payload = _json_object(completed_event.payload)
    resolution_payload = _json_object(completed_payload["resolution"])
    transition_payload = _json_object(completed_payload["transition_batch"])
    witness_payload = _json_object(resolution_payload["witness"])
    witness_paths = cast(list[dict[str, JsonValue]], witness_payload["model_paths"])
    displacement_payloads = cast(
        list[dict[str, JsonValue]],
        transition_payload["displacements"],
    )

    assert completed_payload["unit_instance_id"] == canonical_id
    assert completed_payload["active_player_id"] == "player-a"
    assert resolution_payload["rules_unit_instance_id"] == canonical_id
    assert resolution_payload["component_unit_instance_ids"] == list(component_ids)
    assert {cast(str, path["model_id"]) for path in witness_paths} == set(before_y_by_model_id)
    assert {
        cast(str, displacement["model_instance_id"]) for displacement in displacement_payloads
    } == set(before_y_by_model_id)
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="replay:ws13:attached-fight-movement")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


@pytest.mark.integration
@pytest.mark.parametrize(
    ("scenario", "expected_violation"),
    [
        ("non_object", "proposal_payload_malformed"),
        ("missing_fields", "proposal_payload_malformed"),
        ("proposal_kind_invalid", "proposal_payload_malformed"),
        ("stale_request", "stale_proposal_request"),
        ("player_drift", "proposal_player_drift"),
        ("battle_round_drift", "proposal_battle_round_drift"),
        ("unit_drift", "proposal_unit_drift"),
        ("source_request_drift", "source_decision_request_drift"),
        ("source_result_drift", "source_decision_result_drift"),
        ("no_declarations", "melee_declaration_required"),
        ("duplicate_declaration", "duplicate_melee_weapon_declaration"),
        ("unavailable_weapon", "melee_weapon_not_available"),
        ("target_not_engaged", "melee_target_not_engaged_with_model"),
        ("attack_count_drift", "melee_attack_count_drift"),
        ("too_many_targets", "melee_target_count_exceeds_attacks"),
    ],
)
def test_local_session_rejects_invalid_melee_declarations_before_mutation(
    scenario: str,
    expected_violation: str,
) -> None:
    session, status, attacker_id, _enemy_id = _fight_melee_facade_session(
        game_id=f"ws13-melee-invalid-{scenario}"
    )
    request = _assert_request(status, SUBMIT_MELEE_DECLARATION_DECISION_TYPE)
    payload: JsonValue = _minimal_melee_declaration_payload(request)
    payload_object = cast(dict[str, JsonValue], json.loads(json.dumps(payload)))
    declarations = cast(list[dict[str, JsonValue]], payload_object["declarations"])

    if scenario == "non_object":
        payload = None
    elif scenario == "missing_fields":
        payload = {}
    elif scenario == "proposal_kind_invalid":
        payload_object["proposal_kind"] = ProposalKind.PILE_IN.value
    elif scenario == "stale_request":
        payload_object["proposal_request_id"] = f"{request.request_id}:stale"
    elif scenario == "player_drift":
        payload_object["player_id"] = "player-b"
    elif scenario == "battle_round_drift":
        payload_object["battle_round"] = 2
    elif scenario == "unit_drift":
        payload_object["unit_instance_id"] = attacker_id.replace("army-alpha", "army-beta")
    elif scenario == "source_request_drift":
        payload_object["source_decision_request_id"] = "decision-request:stale-source"
    elif scenario == "source_result_drift":
        payload_object["source_decision_result_id"] = "decision-result:stale-source"
    elif scenario == "no_declarations":
        payload_object["declarations"] = []
    elif scenario == "duplicate_declaration":
        declarations.append(cast(dict[str, JsonValue], json.loads(json.dumps(declarations[0]))))
    elif scenario == "unavailable_weapon":
        declarations[0]["wargear_id"] = "not-an-available-melee-weapon"
    elif scenario == "target_not_engaged":
        allocations = cast(list[dict[str, JsonValue]], declarations[0]["target_allocations"])
        allocations[0]["target_unit_instance_id"] = attacker_id
    elif scenario == "attack_count_drift":
        allocations = cast(list[dict[str, JsonValue]], declarations[0]["target_allocations"])
        allocations[0]["attacks"] = 1
    elif scenario == "too_many_targets":
        declarations[0]["target_allocations"] = [
            {"target_unit_instance_id": f"army-beta:target-{index:03d}"} for index in range(6)
        ]

    if scenario not in {"non_object", "missing_fields"}:
        payload = validate_json_value(payload_object)
    records_before = session.decision_record_count()
    state = session.lifecycle.state
    assert state is not None
    fight_state_before = state.fight_phase_state
    assert fight_state_before is not None
    cursor = _cursor_after(session, viewer_player_id="player-a")

    invalid = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=payload,
        result_id=f"ws13-melee-invalid-{scenario}-result",
    )

    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert _first_proposal_violation(invalid) == expected_violation
    assert session.decision_record_count() == records_before
    assert state.fight_phase_state == fight_state_before
    pending = session.lifecycle.pending_decision_request()
    assert pending is not None
    assert pending.to_payload() == request.to_payload()
    assert session.events_since(cursor, viewer_player_id="player-a")["events"] == []


@pytest.mark.integration
def test_local_session_accepts_melee_declaration_and_replays_attack_continuation() -> None:
    session, status, _attacker_id, _enemy_id = _fight_melee_facade_session(
        game_id="ws13-melee-valid-replay"
    )
    request = _assert_request(status, SUBMIT_MELEE_DECLARATION_DECISION_TYPE)
    cursor = _cursor_after(session, viewer_player_id="player-a")
    records_before = session.decision_record_count()

    continued = session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=_minimal_melee_declaration_payload(request),
        result_id="ws13-melee-valid-replay-result",
    )

    next_request = _assert_request(continued)
    assert next_request.request_id != request.request_id
    assert session.decision_record_count() > records_before
    assert any(
        record.result.result_id == "ws13-melee-valid-replay-result"
        for record in session.lifecycle.decision_controller.records[records_before:]
    )
    state = session.lifecycle.state
    assert state is not None
    _assert_event_types(
        session.events_since(cursor, viewer_player_id="player-a"),
        "decision_recorded",
        "melee_declaration_accepted",
        "attack_sequence_completed",
    )
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="replay:ws13:melee-declaration")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


@pytest.mark.integration
def test_local_session_drives_armour_of_contempt_fight_save_completion_and_replay() -> None:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("defender",),
        origins={
            "attacker": Pose.at(10.0, 20.0),
            "defender": Pose.at(12.0, 20.0),
        },
        game_id="ws14-armour-of-contempt-fight-facade",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
        catalog=_armour_of_contempt_catalog(),
        enemy_unit_specs={
            "defender": (
                "ws14-adeptus-astartes-character",
                "core-character-leader",
                1,
            ),
        },
        enemy_faction_id="space-marines",
        enemy_detachment_ids=("gladius-task-force",),
    )
    state = lifecycle.state
    assert state is not None
    _grant_facade_cp(state=state, player_id="player-b")
    session = LocalGameSession(lifecycle=lifecycle)

    status = _drain_facade_movement_requests(
        session,
        session.advance_until_decision_or_terminal(),
        result_prefix="ws14-aoc-fight-opening",
    )
    activation_request = _assert_request(status, FIGHT_ACTIVATION_DECISION_TYPE)
    activation_option = next(
        option
        for option in activation_request.options
        if units["attacker"].unit_instance_id in str(option.payload)
    )
    status = session.submit_option(
        request_id=activation_request.request_id,
        option_id=activation_option.option_id,
        result_id="ws14-aoc-fight-activation",
    )
    status = _drain_facade_movement_requests(
        session,
        status,
        result_prefix="ws14-aoc-fight-pile-in",
    )
    declaration_request = _assert_request(status, SUBMIT_MELEE_DECLARATION_DECISION_TYPE)
    status = session.submit_parameterized_payload(
        request_id=declaration_request.request_id,
        payload=_minimal_melee_declaration_payload(declaration_request),
        result_id="ws14-aoc-melee-declaration",
    )

    stratagem_request = _assert_request(status, STRATAGEM_DECISION_TYPE)
    _assert_pending_request_for_both_players(session, stratagem_request)
    stratagem_option = next(
        option
        for option in stratagem_request.options
        if _option_stratagem_id(option.payload) == "000008352002"
        and _option_target_unit_id(option.payload) == units["defender"].unit_instance_id
    )
    status = session.submit_option(
        request_id=stratagem_request.request_id,
        option_id=stratagem_option.option_id,
        result_id="ws14-aoc-fight-use-stratagem",
    )
    assert state.command_point_total("player-b") == 0

    status = _drive_attack_sequence_through_facade(
        session,
        status,
        result_prefix="ws14-aoc-fight-resolution",
    )

    assert _assert_request(status).decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    assert not any(
        "000008352002" in effect.source_rule_id
        for effect in state.persisting_effects_for_unit(units["defender"].unit_instance_id)
    )
    _assert_attack_save_used_modified_ap(lifecycle, expected_armor_penetration=-1)
    assert _event_type_count(lifecycle, "attack_sequence_completed") == 1
    assert _event_type_count(lifecycle, "rule_execution_effect_applied") == 1
    assert _event_type_count(lifecycle, "generic_rule_attack_sequence_effects_expired") == 1
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="replay:ws14:aoc:fight-facade")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


@pytest.mark.integration
def test_local_session_drives_armour_of_contempt_shared_shooting_path() -> None:
    lifecycle, units = shooting_lifecycle(
        alpha_unit_ids=("attacker",),
        game_id="ws14-armour-of-contempt-shooting-facade-step3-2",
        enemy_unit_specs=(
            (
                "defender",
                "ws14-adeptus-astartes-infantry",
                "core-intercessor-like",
                5,
            ),
        ),
        catalog=_armour_of_contempt_catalog(),
        enemy_faction_id="space-marines",
        enemy_detachment_ids=("gladius-task-force",),
    )
    lifecycle = GameLifecycle.from_payload(lifecycle.to_payload())
    state = lifecycle.state
    assert state is not None
    _grant_facade_cp(state=state, player_id="player-b")
    session = LocalGameSession(lifecycle=lifecycle)

    status = session.advance_until_decision_or_terminal()
    selection_request = _assert_request(status, SELECT_SHOOTING_UNIT_DECISION_TYPE)
    status = session.submit_option(
        request_id=selection_request.request_id,
        option_id=units["attacker"].unit_instance_id,
        result_id="ws14-aoc-select-shooter",
    )
    shooting_type_request = _assert_request(status, SELECT_SHOOTING_TYPE_DECISION_TYPE)
    status = session.submit_option(
        request_id=shooting_type_request.request_id,
        option_id=ShootingType.NORMAL.value,
        result_id="ws14-aoc-select-shooting-type",
    )
    declaration_request = _assert_request(status, SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE)
    proposal = shooting_declaration_proposal(
        request=declaration_request,
        target_unit_id=units["defender"].unit_instance_id,
    )
    status = session.submit_parameterized_payload(
        request_id=declaration_request.request_id,
        payload=validate_json_value(proposal.to_payload()),
        result_id="ws14-aoc-shooting-declaration",
    )

    stratagem_request = _assert_request(status, STRATAGEM_DECISION_TYPE)
    _assert_pending_request_for_both_players(session, stratagem_request)
    stratagem_option = next(
        option
        for option in stratagem_request.options
        if _option_stratagem_id(option.payload) == "000008352002"
        and _option_target_unit_id(option.payload) == units["defender"].unit_instance_id
    )
    status = session.submit_option(
        request_id=stratagem_request.request_id,
        option_id=stratagem_option.option_id,
        result_id="ws14-aoc-shooting-use-stratagem",
    )
    status = _drive_attack_sequence_through_facade(
        session,
        status,
        result_prefix="ws14-aoc-shooting-resolution",
    )

    resumed_request = _assert_request(status)
    assert resumed_request.decision_type != STRATAGEM_DECISION_TYPE
    assert not any(
        "000008352002" in effect.source_rule_id
        for effect in state.persisting_effects_for_unit(units["defender"].unit_instance_id)
    )
    _assert_attack_save_used_modified_ap(lifecycle, expected_armor_penetration=0)
    assert _event_type_count(lifecycle, "attack_sequence_completed") == 1
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="replay:ws14:aoc:shooting-facade")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


@pytest.mark.integration
def test_local_session_drives_primary_mission_choice_with_public_views_and_replay() -> None:
    session, status, enemy_unit_id = _primary_mission_choice_facade_session()
    request = _assert_request(status, SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE)
    assert request.actor_id == "player-a"
    assert len(request.options) == 1

    player_a_view = session.view(viewer_player_id="player-a")
    player_b_view = session.view(viewer_player_id="player-b")
    player_a_pending = player_a_view["pending_decision"]
    player_b_pending = player_b_view["pending_decision"]
    assert player_a_pending is not None
    assert player_b_pending is not None
    assert player_a_pending["request_id"] == request.request_id
    assert player_b_pending["request_id"] == request.request_id
    assert player_a_pending["payload"] == player_b_pending["payload"]
    assert player_a_pending["options"] == player_b_pending["options"]
    assert player_a_pending["interaction"] == player_b_pending["interaction"]
    interaction = player_a_pending["interaction"]
    assert interaction is not None
    assert interaction["interaction_kind"] == "finite_option_list"
    assert interaction["submission_kind"] == "finite"

    cursor = EventStreamCursor(session.event_record_count())
    record_count = session.decision_record_count()
    selected_option = request.options[0]
    status = session.submit_option(
        request_id=request.request_id,
        option_id=selected_option.option_id,
        result_id="phase17n-punishment-choice-facade-result",
    )

    assert status.status_kind is LifecycleStatusKind.ADVANCED
    assert session.decision_record_count() == record_count + 1
    record = session.lifecycle.decision_controller.records[-1]
    record_payload = record.to_payload()
    restored_record = DecisionRecord.from_payload(record_payload)
    assert restored_record == record
    serialized_record = json.dumps(record_payload, sort_keys=True)
    assert serialized_record == json.dumps(restored_record.to_payload(), sort_keys=True)
    assert "object at 0x" not in serialized_record

    state = session.lifecycle.state
    assert state is not None
    condemned = state.primary_mission_progress_state.condemned_selections
    assert len(condemned) == 1
    assert condemned[0].selected_rules_unit_instance_ids == (enemy_unit_id,)

    player_a_events = session.events_since(cursor, viewer_player_id="player-a")
    player_b_events = session.events_since(cursor, viewer_player_id="player-b")
    assert player_a_events["viewer_player_id"] == "player-a"
    assert player_b_events["viewer_player_id"] == "player-b"
    assert player_a_events["events"] == player_b_events["events"]
    _assert_event_types(
        player_a_events,
        "decision_recorded",
        PRIMARY_MISSION_CHOICE_RESOLVED_EVENT,
    )

    player_a_resolved = session.view(viewer_player_id="player-a")
    player_b_resolved = session.view(viewer_player_id="player-b")
    assert player_a_resolved["pending_decision"] is None
    assert player_b_resolved["pending_decision"] is None
    assert (
        player_a_resolved["primary_mission_progress_state"]
        == (player_b_resolved["primary_mission_progress_state"])
    )
    assert player_a_resolved["primary_mission_progress_state"] == (
        state.primary_mission_progress_state.to_payload()
    )

    artifact = session.replay_artifact(artifact_id="replay:phase17n:punishment-choice-facade")
    serialized_artifact = json.dumps(artifact, sort_keys=True)
    assert "object at 0x" not in serialized_artifact
    replay = ReplayRunner.from_payload(artifact).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


@pytest.mark.integration
def test_local_session_rejects_drifted_primary_mission_choice_before_mutation() -> None:
    session, status, enemy_unit_id = _primary_mission_choice_facade_session()
    request = _assert_request(status, SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    progress_before = state.primary_mission_progress_state.to_payload()
    record_count_before = session.decision_record_count()
    event_count_before = session.event_record_count()

    state.battlefield_state = state.battlefield_state.without_unit_placement(enemy_unit_id)
    invalid = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="phase17n-punishment-choice-drifted-result",
    )

    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert _json_object(invalid.payload)["invalid_reason"] == (
        "primary_mission_choice_request_drift"
    )
    assert session.decision_record_count() == record_count_before
    assert session.event_record_count() == event_count_before
    assert state.primary_mission_progress_state.to_payload() == progress_before
    pending = session.lifecycle.pending_decision_request()
    assert pending is not None
    assert pending.to_payload() == request.to_payload()


def _primary_mission_choice_facade_session() -> tuple[LocalGameSession, LifecycleStatus, str]:
    setup = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-purge-the-foe-vs-disruption-layout-1",
        terrain_layout_id="purge-the-foe-vs-disruption-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="disruption",
    )
    base = phase11c_config()
    catalog = replace(
        base.army_catalog,
        detachments=tuple(
            replace(
                detachment,
                force_disposition_ids=(*detachment.force_disposition_ids, "disruption"),
            )
            if detachment.detachment_id == "core-combined-arms"
            else detachment
            for detachment in base.army_catalog.detachments
        ),
    )
    config = replace(
        base,
        game_id="phase17n-primary-mission-choice-facade",
        army_catalog=catalog,
        mission_setup=setup,
        army_muster_requests=tuple(
            replace(
                request,
                force_disposition_id=(
                    "purge-the-foe" if request.player_id == "player-a" else "disruption"
                ),
            )
            for request in base.army_muster_requests
        ),
    )
    state = GameState.from_config(config)
    for army in mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17n-primary-mission-choice-facade-battlefield",
        armies=tuple(state.army_definitions),
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=setup.terrain_features,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            secondary_choice(player_id=player_id, mode=SecondaryMissionMode.FIXED)
        )
    decisions = DecisionController()
    complete_setup_through_gate(state=state, decisions=decisions, config=config)
    request = punishment_choice_request(
        state=state,
        decisions=decisions,
    )
    assert request is not None
    decisions.request_decision(request)
    decisions.event_log.append(
        "primary_mission_choice_requested",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.COMMAND.value,
            "request_id": request.request_id,
            "decision_type": request.decision_type,
            "actor_id": request.actor_id,
        },
    )
    enemy_unit_id = next(
        unit.unit_instance_id
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    lifecycle = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": decisions.to_payload(),
                "reaction_queue": {"frames": []},
            },
        )
    )
    session = LocalGameSession(lifecycle=lifecycle)
    status = session.advance_until_decision_or_terminal()
    return session, status, enemy_unit_id


def _submit_fixed_secondaries(
    session: LocalGameSession,
    *,
    status: LifecycleStatus,
) -> LifecycleStatus:
    current = status
    for result_id in ("ws13-secondary-a", "ws13-secondary-b"):
        request = _assert_request(current, SECONDARY_MISSION_DECISION_TYPE)
        current = session.submit_option(
            request_id=request.request_id,
            option_id="fixed:assassination:bring_it_down",
            result_id=result_id,
        )
    return current


def _submit_all_deployments(
    session: LocalGameSession,
    *,
    status: LifecycleStatus,
) -> LifecycleStatus:
    current = status
    result_number = 1
    while current.decision_request is not None and current.decision_request.decision_type in {
        SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
        SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
    }:
        request = current.decision_request
        result_id = f"ws13-deploy-{result_number:06d}"
        if request.decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE:
            current = session.submit_option(
                request_id=request.request_id,
                option_id=request.options[0].option_id,
                result_id=result_id,
            )
        else:
            current = session.submit_parameterized_payload(
                request_id=request.request_id,
                payload=deployment_placement_payload_for_request(
                    session.lifecycle,
                    request=request,
                    pose_factory=_shooting_reachable_deployment_pose,
                ),
                result_id=result_id,
            )
        result_number += 1
    return current


def _submit_pending_option(
    session: LocalGameSession,
    *,
    status: LifecycleStatus,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    request = _assert_request(status)
    return session.submit_option(
        request_id=request.request_id,
        option_id=option_id,
        result_id=result_id,
    )


def _submit_movement_proposal(
    session: LocalGameSession,
    *,
    status: LifecycleStatus,
    result_id: str,
    dx: float,
) -> LifecycleStatus:
    request = _assert_request(status, MOVEMENT_PROPOSAL_DECISION_TYPE)
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    payload = MovementProposalPayload(
        proposal_request_id=proposal.request_id,
        proposal_kind=ProposalKind.NORMAL_MOVE,
        unit_instance_id=proposal.unit_instance_id,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
        movement_mode=MovementMode.NORMAL.value,
        witness=straight_line_witness_for_unit(
            session.lifecycle,
            unit_instance_id=proposal.unit_instance_id,
            dx=dx,
        ),
    ).to_payload()
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=validate_json_value(payload),
        result_id=result_id,
    )


def _decline_optional_stratagem(
    session: LocalGameSession,
    *,
    status: LifecycleStatus,
    result_id: str,
) -> LifecycleStatus:
    request = _assert_request(status)
    if request.decision_type != STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        return status
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        payload=stratagem_decline_payload(),
        result_id=result_id,
    )


def _assert_request(
    status: LifecycleStatus,
    decision_type: str | None = None,
) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    if decision_type is not None:
        assert status.decision_request.decision_type == decision_type
    return status.decision_request


def _assert_pending_view(
    session: LocalGameSession,
    *,
    viewer_player_id: str,
    decision_type: str,
) -> None:
    view = session.view(viewer_player_id=viewer_player_id)
    pending = view["pending_decision"]
    assert pending is not None
    assert pending["decision_type"] == decision_type
    assert "object at 0x" not in str(view)


def _assert_event_types(
    event_delta: EventStreamDeltaPayload,
    *event_types: str,
) -> None:
    visible_event_types = {event["event_type"] for event in event_delta["events"]}
    for event_type in event_types:
        assert event_type in visible_event_types


def _cursor_after(session: LocalGameSession, *, viewer_player_id: str) -> EventStreamCursor:
    event_delta = session.events_since(EventStreamCursor(), viewer_player_id=viewer_player_id)
    return EventStreamCursor(event_delta["next_cursor"])


def _armour_of_contempt_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    character = base_catalog.datasheet_by_id("core-character-leader")
    infantry = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    astartes_character = replace(
        character,
        datasheet_id="ws14-adeptus-astartes-character",
        name="WS14 Adeptus Astartes Character",
        keywords=DatasheetKeywordSet(
            keywords=character.keywords.keywords,
            faction_keywords=("ADEPTUS ASTARTES",),
        ),
        source_ids=("datasheet:ws14-adeptus-astartes-character",),
    )
    astartes_infantry = replace(
        infantry,
        datasheet_id="ws14-adeptus-astartes-infantry",
        name="WS14 Adeptus Astartes Infantry",
        keywords=DatasheetKeywordSet(
            keywords=infantry.keywords.keywords,
            faction_keywords=("ADEPTUS ASTARTES",),
        ),
        source_ids=("datasheet:ws14-adeptus-astartes-infantry",),
    )
    return replace(
        base_catalog,
        catalog_id="ws14-armour-of-contempt-facade",
        source_package_id="data-package:core-v2:ws14-armour-of-contempt-facade:0.1.0",
        datasheets=(*base_catalog.datasheets, astartes_character, astartes_infantry),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id="space-marines",
                name="Space Marines",
                faction_keywords=("ADEPTUS ASTARTES",),
                source_ids=("faction:space-marines",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id="gladius-task-force",
                name="Gladius Task Force",
                faction_id="space-marines",
                detachment_point_cost=1,
                unit_datasheet_ids=(
                    astartes_character.datasheet_id,
                    astartes_infantry.datasheet_id,
                ),
                force_disposition_ids=("purge-the-foe",),
                stratagem_ids=("000008352002",),
                source_ids=("detachment:gladius-task-force",),
            ),
        ),
        stratagems=(
            *base_catalog.stratagems,
            StratagemDefinition(
                stratagem_id="000008352002",
                name="Armour of Contempt",
                source_id=("phase17e:stratagem:space-marines:gladius-task-force:000008352002"),
                command_point_cost=1,
                timing_tags=("shooting", "fight"),
            ),
        ),
    )


def _fight_pile_in_facade_session(
    *,
    game_id: str,
) -> tuple[LocalGameSession, LifecycleStatus, str, str]:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("enemy",),
        origins={
            "attacker": Pose.at(10.0, 20.0),
            "enemy": Pose.at(12.0, 20.0),
        },
        game_id=game_id,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    session = LocalGameSession(lifecycle=lifecycle)
    status = session.advance_until_decision_or_terminal()
    return (
        session,
        status,
        units["attacker"].unit_instance_id,
        units["enemy"].unit_instance_id,
    )


def _fight_melee_facade_session(
    *,
    game_id: str,
) -> tuple[LocalGameSession, LifecycleStatus, str, str]:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("enemy",),
        origins={
            "attacker": Pose.at(10.0, 20.0),
            "enemy": Pose.at(12.0, 20.0),
        },
        game_id=game_id,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    session = LocalGameSession(lifecycle=lifecycle)
    status = _drain_facade_movement_requests(
        session,
        session.advance_until_decision_or_terminal(),
        result_prefix=f"{game_id}-opening-movement",
    )
    activation_request = _assert_request(status, FIGHT_ACTIVATION_DECISION_TYPE)
    attacker_id = units["attacker"].unit_instance_id
    activation_option = next(
        option for option in activation_request.options if attacker_id in str(option.payload)
    )
    status = session.submit_option(
        request_id=activation_request.request_id,
        option_id=activation_option.option_id,
        result_id=f"{game_id}-activation",
    )
    status = _drain_facade_movement_requests(
        session,
        status,
        result_prefix=f"{game_id}-pile-in",
    )
    _assert_request(status, SUBMIT_MELEE_DECLARATION_DECISION_TYPE)
    return session, status, attacker_id, units["enemy"].unit_instance_id


def _fight_pile_in_payload(
    session: LocalGameSession,
    *,
    proposal_request: MovementProposalRequest,
    target_unit_ids: tuple[str, ...],
    witness: PathWitness | None = None,
) -> JsonValue:
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=proposal_request.unit_instance_id,
    )
    for component_id in rules_unit.component_unit_instance_ids:
        state.battlefield_state.unit_placement_by_id(component_id)
    context = cast(dict[str, JsonValue], proposal_request.context)
    assert proposal_request.movement_phase_action is not None
    payload: dict[str, JsonValue] = {
        "proposal_request_id": proposal_request.request_id,
        "proposal_kind": proposal_request.proposal_kind.value,
        "unit_instance_id": proposal_request.unit_instance_id,
        "movement_phase_action": proposal_request.movement_phase_action,
        "movement_mode": cast(str, context["movement_mode"]),
    }
    if target_unit_ids:
        payload["pile_in_target_unit_instance_ids"] = list(target_unit_ids)
    if witness is not None:
        payload["witness"] = validate_json_value(witness.to_payload())
    return validate_json_value(payload)


def _straight_line_witness_for_rules_unit(
    session: LocalGameSession,
    *,
    unit_instance_id: str,
    dy: float,
) -> PathWitness:
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for component_id in rules_unit.component_unit_instance_ids:
        placement = state.battlefield_state.unit_placement_by_id(component_id)
        for model in placement.model_placements:
            start = model.pose
            middle = Pose.at(
                start.position.x,
                start.position.y + dy / 2.0,
                start.position.z,
                facing_degrees=start.facing.degrees,
            )
            end = Pose.at(
                start.position.x,
                start.position.y + dy,
                start.position.z,
                facing_degrees=start.facing.degrees,
            )
            model_paths.append((model.model_instance_id, (start, middle, end)))
    return PathWitness.for_paths(tuple(model_paths))


def _endpoint_only_witness(
    session: LocalGameSession,
    *,
    unit_instance_id: str,
    dx: float,
) -> PathWitness:
    endpoints = straight_line_witness_for_unit(
        session.lifecycle,
        unit_instance_id=unit_instance_id,
        dx=dx,
        include_midpoint=False,
    )
    return PathWitness.for_paths(
        tuple(
            (
                model_id,
                (
                    endpoints.poses_for_model(model_id)[0],
                    endpoints.poses_for_model(model_id)[-1],
                    endpoints.poses_for_model(model_id)[-1],
                ),
            )
            for model_id in endpoints.model_ids()
        )
    )


def _shift_unit_placement(
    session: LocalGameSession,
    *,
    unit_instance_id: str,
    dx: float,
) -> None:
    state = session.lifecycle.state
    assert state is not None
    battlefield = state.battlefield_state
    assert battlefield is not None
    placement = battlefield.unit_placement_by_id(unit_instance_id)
    state.replace_battlefield_state(
        battlefield.with_unit_placement(
            placement.with_model_placements(
                tuple(
                    model_placement.with_pose(
                        Pose.at(
                            model_placement.pose.position.x + dx,
                            model_placement.pose.position.y,
                            model_placement.pose.position.z,
                            facing_degrees=model_placement.pose.facing.degrees,
                        )
                    )
                    for model_placement in placement.model_placements
                )
            )
        )
    )


def _first_proposal_violation(status: LifecycleStatus) -> str:
    payload = _json_object(status.payload)
    validation = _json_object(payload["proposal_validation"])
    violations = cast(list[dict[str, JsonValue]], validation["violations"])
    assert violations
    violation_code = violations[0]["violation_code"]
    assert type(violation_code) is str
    return violation_code


def _grant_facade_cp(*, state: GameState, player_id: str) -> None:
    result = state.gain_command_points(
        player_id=player_id,
        amount=1,
        source_id=f"ws14-aoc-facade-grant:{player_id}",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    assert result.status is CommandPointGainStatus.APPLIED


def _minimal_melee_declaration_payload(request: DecisionRequest) -> JsonValue:
    proposal = MeleeDeclarationProposalRequest.from_decision_request(request)
    declarations: list[dict[str, JsonValue]] = []
    selected_model_ids: set[str] = set()
    for raw_weapon in proposal.available_weapons:
        weapon = cast(dict[str, JsonValue], raw_weapon)
        model_instance_id = cast(str, weapon["model_instance_id"])
        target_unit_ids = cast(list[str], weapon["engaged_target_unit_instance_ids"])
        if (
            model_instance_id in selected_model_ids
            or weapon["is_extra_attacks"] is True
            or not target_unit_ids
        ):
            continue
        selected_model_ids.add(model_instance_id)
        declarations.append(
            {
                "attacker_model_instance_id": model_instance_id,
                "wargear_id": weapon["wargear_id"],
                "weapon_profile_id": weapon["weapon_profile_id"],
                "target_allocations": [
                    {"target_unit_instance_id": target_unit_ids[0]},
                ],
            }
        )
    assert declarations
    return validate_json_value(
        {
            "proposal_request_id": proposal.request_id,
            "proposal_kind": proposal.proposal_kind,
            "player_id": proposal.actor_id,
            "battle_round": proposal.battle_round,
            "unit_instance_id": proposal.unit_instance_id,
            "source_decision_request_id": proposal.source_decision_request_id,
            "source_decision_result_id": proposal.source_decision_result_id,
            "declarations": declarations,
        }
    )


def _drain_facade_movement_requests(
    session: LocalGameSession,
    status: LifecycleStatus,
    *,
    result_prefix: str,
) -> LifecycleStatus:
    current = status
    result_index = 1
    while (
        current.decision_request is not None
        and current.decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    ):
        request = current.decision_request
        proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
        context = cast(dict[str, JsonValue], proposal.context)
        current = session.submit_parameterized_payload(
            request_id=request.request_id,
            payload=validate_json_value(
                {
                    "proposal_request_id": proposal.request_id,
                    "proposal_kind": proposal.proposal_kind.value,
                    "unit_instance_id": proposal.unit_instance_id,
                    "movement_phase_action": proposal.movement_phase_action,
                    "movement_mode": context["movement_mode"],
                }
            ),
            result_id=f"{result_prefix}-{result_index:03d}",
        )
        result_index += 1
    return current


def _drive_attack_sequence_through_facade(
    session: LocalGameSession,
    status: LifecycleStatus,
    *,
    result_prefix: str,
) -> LifecycleStatus:
    current = status
    for result_index in range(1, 129):
        if _event_type_count(session.lifecycle, "attack_sequence_completed") == 1:
            return current
        request = _assert_request(current)
        if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            current = _drain_facade_movement_requests(
                session,
                current,
                result_prefix=f"{result_prefix}-movement-{result_index:03d}",
            )
            continue
        decline_option = next(
            (
                option
                for option in request.options
                if option.option_id == "decline_stratagem_window"
            ),
            None,
        )
        selected_option = request.options[0] if decline_option is None else decline_option
        current = session.submit_option(
            request_id=request.request_id,
            option_id=selected_option.option_id,
            result_id=f"{result_prefix}-{result_index:03d}",
        )
    raise AssertionError("Attack sequence did not resume to its phase selection request.")


def _assert_pending_request_for_both_players(
    session: LocalGameSession,
    request: DecisionRequest,
) -> None:
    for viewer_player_id in ("player-a", "player-b"):
        pending = session.view(viewer_player_id=viewer_player_id)["pending_decision"]
        assert pending is not None
        assert pending["request_id"] == request.request_id
        assert pending["decision_type"] == STRATAGEM_DECISION_TYPE
        assert "object at 0x" not in json.dumps(pending, sort_keys=True)


def _option_stratagem_id(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict):
        return None
    catalog_record = payload.get("catalog_record")
    if not isinstance(catalog_record, dict):
        return None
    definition = catalog_record.get("definition")
    if not isinstance(definition, dict):
        return None
    value = definition.get("stratagem_id")
    return value if isinstance(value, str) else None


def _option_target_unit_id(payload: JsonValue) -> str | None:
    if not isinstance(payload, dict):
        return None
    target_binding = payload.get("target_binding")
    if not isinstance(target_binding, dict):
        return None
    value = target_binding.get("target_unit_instance_id")
    return value if isinstance(value, str) else None


def _assert_attack_save_used_modified_ap(
    lifecycle: GameLifecycle,
    *,
    expected_armor_penetration: int,
) -> None:
    save_options = tuple(
        option
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "attack_sequence_step"
        for event_payload in (_json_object(event.payload),)
        if event_payload.get("step") == "save"
        for save_payload in (_json_object(event_payload["payload"]),)
        for option in cast(list[dict[str, JsonValue]], save_payload["save_options"])
    )
    assert save_options
    assert any(option["armor_penetration"] == expected_armor_penetration for option in save_options)


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _event_type_count(lifecycle: GameLifecycle, event_type: str) -> int:
    return sum(
        event.event_type == event_type for event in lifecycle.decision_controller.event_log.records
    )


def _config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="ws13-adapter-phase-families",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-ws13-adapter-phase-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1", "intercessor-unit-2"),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
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


def _shooting_reachable_deployment_pose(
    index: int,
    player_id: str,
    model_instance_id: str,
) -> Pose:
    unit_instance_id = model_instance_id.rsplit(":", 2)[0]
    if unit_instance_id in {
        "army-alpha:intercessor-unit-1",
        "army-beta:intercessor-unit-3",
    }:
        x = 15.5 if player_id == "player-a" else 43.5
        facing = 0.0 if player_id == "player-a" else 180.0
        return Pose.at(x, 17.0 + (index * 1.8), 0.0, facing_degrees=facing)
    return default_deployment_pose(index, player_id, model_instance_id)
