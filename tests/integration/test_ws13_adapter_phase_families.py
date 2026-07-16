from __future__ import annotations

import pytest
from tests.deployment_submission_helpers import (
    default_deployment_pose,
    deployment_placement_payload_for_request,
)
from tests.movement_submission_helpers import straight_line_witness_for_unit
from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses
from tests.phase15c_fight_order_helpers import fight_lifecycle

from warhammer40k_core.adapters.event_stream import EventStreamCursor, EventStreamDeltaPayload
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.deployment import (
    SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
    SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.fight_order import (
    ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
    FIGHT_ACTIVATION_DECISION_TYPE,
)
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.list_validation import (
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
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind
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
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


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
