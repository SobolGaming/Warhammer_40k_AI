from __future__ import annotations

import json
from collections.abc import Callable
from typing import cast

import pytest
from tests.deployment_submission_helpers import (
    submit_deployment_placement,
    submit_deployment_unit_selection,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.projection import GameViewPayload
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.engine.battlefield_state import ModelPlacement
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.deployment import (
    SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
    SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, LifecycleStatus
from warhammer40k_core.engine.prebattle import (
    SCOUT_MOVE_PROPOSAL_KIND,
    SELECT_PREBATTLE_ACTION_DECISION_TYPE,
    SELECT_REDEPLOY_UNIT_DECISION_TYPE,
    SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE,
    SUBMIT_SCOUT_MOVE_DECISION_TYPE,
    PreBattlePlacementProposal,
    PreBattleProposalRequest,
    ScoutMoveProposal,
)
from warhammer40k_core.engine.reserve_declarations import (
    SELECT_RESERVE_DECLARATION_DECISION_TYPE,
)
from warhammer40k_core.engine.sequencing import SEQUENCING_DECISION_TYPE
from warhammer40k_core.engine.setup_completion import SetupCompletionGate
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.integration
def test_setup_prebattle_ui_smoke_projects_real_requests_and_typed_terrain() -> None:
    session = LocalGameSession()
    session.start(canonical_setup_prebattle_smoke_config())
    status = session.advance_until_decision_or_terminal()
    observed_decision_types: list[str] = []

    status = _submit_finite(
        session,
        status=status,
        expected_decision_type=SECONDARY_MISSION_DECISION_TYPE,
        option_id="fixed:assassination:bring_it_down",
        result_id="setup-smoke-secondary-a",
        observed_decision_types=observed_decision_types,
    )
    status = _submit_finite(
        session,
        status=status,
        expected_decision_type=SECONDARY_MISSION_DECISION_TYPE,
        option_id="fixed:assassination:bring_it_down",
        result_id="setup-smoke-secondary-b",
        observed_decision_types=observed_decision_types,
    )

    reserve_request = _projected_request(
        session,
        status=status,
        expected_decision_type=SELECT_RESERVE_DECLARATION_DECISION_TYPE,
        observed_decision_types=observed_decision_types,
    )
    assert _option_ids(reserve_request) == (
        "complete_reserve_declarations",
        "declare_deep_strike:army-alpha:deep-strike-unit",
        "declare_strategic_reserves:army-alpha:strategic-reserve-unit",
    )
    status = session.submit_option(
        request_id=reserve_request.request_id,
        option_id="declare_strategic_reserves:army-alpha:strategic-reserve-unit",
        result_id="setup-smoke-strategic-reserve",
    )
    status = _submit_finite(
        session,
        status=status,
        expected_decision_type=SELECT_RESERVE_DECLARATION_DECISION_TYPE,
        option_id="declare_deep_strike:army-alpha:deep-strike-unit",
        result_id="setup-smoke-deep-strike",
        observed_decision_types=observed_decision_types,
    )

    status = _submit_deployment_pair(
        session,
        status=status,
        expected_option_id="deploy:army-beta:scout-redeploy-unit",
        result_id_prefix="setup-smoke-deploy-b",
        observed_decision_types=observed_decision_types,
    )
    status = _submit_deployment_pair(
        session,
        status=status,
        expected_option_id="deploy:army-alpha:scout-redeploy-unit",
        result_id_prefix="setup-smoke-deploy-a",
        observed_decision_types=observed_decision_types,
    )

    status = _submit_ordering(
        session,
        status=status,
        setup_prefix="prebattle:redeploy_units",
        result_id="setup-smoke-redeploy-sequencing",
        observed_decision_types=observed_decision_types,
    )
    redeploy_request = _projected_request(
        session,
        status=status,
        expected_decision_type=SELECT_REDEPLOY_UNIT_DECISION_TYPE,
        observed_decision_types=observed_decision_types,
    )
    failed_gate_status = SetupCompletionGate().invalid_status_if_not_ready(
        state=_state(session),
        decisions=session.lifecycle.decision_controller,
        config=session.lifecycle.config,
    )
    assert failed_gate_status is not None
    assert isinstance(failed_gate_status.payload, dict)
    assert failed_gate_status.payload["invalid_reason"] == "setup_completion_gate_failed"
    assert _state(session).stage is GameLifecycleStage.SETUP

    status = session.submit_option(
        request_id=redeploy_request.request_id,
        option_id="redeploy:army-beta:scout-redeploy-unit",
        result_id="setup-smoke-select-redeploy-b",
    )
    redeploy_placement_request = _projected_request(
        session,
        status=status,
        expected_decision_type=SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE,
        observed_decision_types=observed_decision_types,
    )
    _assert_pending_proposal(session.view(viewer_player_id="player-b"), "redeploy_placement")
    status = session.submit_parameterized_payload(
        request_id=redeploy_placement_request.request_id,
        payload=_prebattle_placement_payload(
            state=_state(session),
            request=redeploy_placement_request,
            pose_factory=lambda index: Pose.at(
                57.0 - ((index // 3) * 1.8),
                24.0 + ((index % 3) * 1.8),
                0.0,
                facing_degrees=180.0,
            ),
        ),
        result_id="setup-smoke-place-redeploy-b",
    )
    status = _submit_finite(
        session,
        status=status,
        expected_decision_type=SELECT_REDEPLOY_UNIT_DECISION_TYPE,
        option_id="complete_redeploys",
        result_id="setup-smoke-complete-redeploy-a",
        observed_decision_types=observed_decision_types,
    )

    status = _submit_ordering(
        session,
        status=status,
        setup_prefix="prebattle:resolve_prebattle_actions",
        result_id="setup-smoke-prebattle-sequencing",
        observed_decision_types=observed_decision_types,
    )
    status = _submit_finite(
        session,
        status=status,
        expected_decision_type=SELECT_PREBATTLE_ACTION_DECISION_TYPE,
        option_id="scout_move:army-beta:scout-redeploy-unit",
        result_id="setup-smoke-select-scout-b",
        observed_decision_types=observed_decision_types,
    )
    scout_request = _projected_request(
        session,
        status=status,
        expected_decision_type=SUBMIT_SCOUT_MOVE_DECISION_TYPE,
        observed_decision_types=observed_decision_types,
    )
    _assert_pending_proposal(session.view(viewer_player_id="player-b"), SCOUT_MOVE_PROPOSAL_KIND)
    status = session.submit_parameterized_payload(
        request_id=scout_request.request_id,
        payload=_scout_move_payload(
            state=_state(session),
            request=scout_request,
            dx=-1.0,
        ),
        result_id="setup-smoke-submit-scout-b",
    )
    status = _submit_finite(
        session,
        status=status,
        expected_decision_type=SELECT_PREBATTLE_ACTION_DECISION_TYPE,
        option_id="complete_prebattle_actions",
        result_id="setup-smoke-complete-prebattle-a",
        observed_decision_types=observed_decision_types,
    )

    event_types = tuple(
        event.event_type for event in session.lifecycle.decision_controller.event_log.records
    )
    assert _state(session).stage is GameLifecycleStage.BATTLE
    assert "setup_completion_gate_passed" in event_types
    assert "battle_started" in event_types
    assert {
        SELECT_RESERVE_DECLARATION_DECISION_TYPE,
        SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
        SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
        SEQUENCING_DECISION_TYPE,
        SELECT_REDEPLOY_UNIT_DECISION_TYPE,
        SUBMIT_REDEPLOY_PLACEMENT_DECISION_TYPE,
        SELECT_PREBATTLE_ACTION_DECISION_TYPE,
        SUBMIT_SCOUT_MOVE_DECISION_TYPE,
    }.issubset(set(observed_decision_types))
    encoded = json.dumps(session.lifecycle.to_payload(), sort_keys=True)
    assert " object at 0x" not in encoded
    assert "<" not in encoded


def _submit_finite(
    session: LocalGameSession,
    *,
    status: LifecycleStatus,
    expected_decision_type: str,
    option_id: str,
    result_id: str,
    observed_decision_types: list[str],
) -> LifecycleStatus:
    request = _projected_request(
        session,
        status=status,
        expected_decision_type=expected_decision_type,
        observed_decision_types=observed_decision_types,
    )
    assert option_id in _option_ids(request)
    return session.submit_option(
        request_id=request.request_id,
        option_id=option_id,
        result_id=result_id,
    )


def _submit_deployment_pair(
    session: LocalGameSession,
    *,
    status: LifecycleStatus,
    expected_option_id: str,
    result_id_prefix: str,
    observed_decision_types: list[str],
) -> LifecycleStatus:
    selection_request = _projected_request(
        session,
        status=status,
        expected_decision_type=SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
        observed_decision_types=observed_decision_types,
    )
    assert expected_option_id in _option_ids(selection_request)
    placement_status = submit_deployment_unit_selection(
        session.lifecycle,
        request=selection_request,
        option_id=expected_option_id,
        result_id=f"{result_id_prefix}-select",
    )
    placement_request = _projected_request(
        session,
        status=placement_status,
        expected_decision_type=SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
        observed_decision_types=observed_decision_types,
    )
    _assert_pending_proposal(
        session.view(viewer_player_id=cast(str, placement_request.actor_id)),
        "deployment_placement",
    )
    return submit_deployment_placement(
        session.lifecycle,
        request=placement_request,
        result_id=f"{result_id_prefix}-place",
    )


def _submit_ordering(
    session: LocalGameSession,
    *,
    status: LifecycleStatus,
    setup_prefix: str,
    result_id: str,
    observed_decision_types: list[str],
) -> LifecycleStatus:
    request = _projected_request(
        session,
        status=status,
        expected_decision_type=SEQUENCING_DECISION_TYPE,
        observed_decision_types=observed_decision_types,
    )
    option_id = _option_with_prefix(request, f"order:{setup_prefix}:player-b")
    return session.submit_option(
        request_id=request.request_id,
        option_id=option_id,
        result_id=result_id,
    )


def _projected_request(
    session: LocalGameSession,
    *,
    status: LifecycleStatus,
    expected_decision_type: str,
    observed_decision_types: list[str],
) -> DecisionRequest:
    request = _decision_request(status)
    assert request.decision_type == expected_decision_type
    viewer = "player-a" if request.actor_id is None else request.actor_id
    view = session.view(viewer_player_id=viewer)
    pending = view["pending_decision"]
    assert pending is not None
    assert pending["request_id"] == request.request_id
    assert pending["decision_type"] == expected_decision_type
    assert pending["options"] == [option.to_payload() for option in request.options]
    _assert_all_terrain_features_have_display_geometry(view)
    observed_decision_types.append(expected_decision_type)
    return request


def _assert_all_terrain_features_have_display_geometry(view: GameViewPayload) -> None:
    mission_setup = view["mission_setup"]
    assert isinstance(mission_setup, dict)
    terrain_features = mission_setup["terrain_features"]
    assert isinstance(terrain_features, list)
    assert terrain_features
    for feature in terrain_features:
        assert isinstance(feature, dict)
        display_geometry = feature["display_geometry"]
        assert isinstance(display_geometry, dict)
        assert display_geometry["schema_version"] == "terrain-display-v1"
        assert display_geometry["coordinate_space"] == "battlefield_inches"
        assert display_geometry["footprint_kind"] == "polygon"
        polygon = display_geometry["footprint_polygon"]
        assert isinstance(polygon, list)
        assert len(polygon) >= 3


def _assert_pending_proposal(view: GameViewPayload, proposal_kind: str) -> None:
    proposal = view["pending_proposal"]
    assert isinstance(proposal, dict)
    assert proposal["proposal_kind"] == proposal_kind
    mission_setup = proposal["mission_setup"]
    assert isinstance(mission_setup, dict)
    terrain_features = mission_setup["terrain_features"]
    assert isinstance(terrain_features, list)
    assert terrain_features
    for feature in terrain_features:
        assert isinstance(feature, dict)
        assert isinstance(feature["display_geometry"], dict)


def _prebattle_placement_payload(
    *,
    state: GameState,
    request: DecisionRequest,
    pose_factory: _PoseFactory,
) -> dict[str, JsonValue]:
    request_context = PreBattleProposalRequest.from_decision_request_payload(request.payload)
    placements: list[ModelPlacement] = []
    for index, model_instance_id in enumerate(request_context.model_instance_ids):
        army_id, player_id, unit_instance_id = _model_source_for_id(
            state=state,
            model_instance_id=model_instance_id,
        )
        placements.append(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit_instance_id,
                model_instance_id=model_instance_id,
                pose=pose_factory(index),
            )
        )
    if request_context.placement_kind is None:
        raise GameLifecycleError("Redeploy smoke request requires placement_kind.")
    payload = validate_json_value(
        PreBattlePlacementProposal(
            proposal_request_id=request_context.request_id,
            proposal_kind=request_context.proposal_kind,
            game_id=request_context.game_id,
            ruleset_descriptor_hash=request_context.ruleset_descriptor_hash,
            setup_step=request_context.setup_step,
            player_id=request_context.player_id,
            unit_instance_id=request_context.unit_instance_id,
            action_kind=request_context.action_kind,
            source_rule_id=request_context.source_rule_id,
            placement_kind=request_context.placement_kind,
            model_placements=tuple(placements),
            context=request_context.context,
        ).to_payload()
    )
    if not isinstance(payload, dict):
        raise GameLifecycleError("Redeploy smoke payload must be an object.")
    return payload


type _PoseFactory = Callable[[int], Pose]


def _scout_move_payload(
    *,
    state: GameState,
    request: DecisionRequest,
    dx: float,
) -> dict[str, JsonValue]:
    request_context = PreBattleProposalRequest.from_decision_request_payload(request.payload)
    if request_context.scout_distance_inches is None:
        raise GameLifecycleError("Scout smoke request requires scout_distance_inches.")
    payload = validate_json_value(
        ScoutMoveProposal(
            proposal_request_id=request_context.request_id,
            proposal_kind=SCOUT_MOVE_PROPOSAL_KIND,
            game_id=request_context.game_id,
            ruleset_descriptor_hash=request_context.ruleset_descriptor_hash,
            setup_step=request_context.setup_step,
            player_id=request_context.player_id,
            unit_instance_id=request_context.unit_instance_id,
            action_kind=request_context.action_kind,
            source_rule_id=request_context.source_rule_id,
            scout_distance_inches=request_context.scout_distance_inches,
            witness=_scout_witness(state=state, request_context=request_context, dx=dx),
            context=request_context.context,
        ).to_payload()
    )
    if not isinstance(payload, dict):
        raise GameLifecycleError("Scout smoke payload must be an object.")
    return payload


def _scout_witness(
    *,
    state: GameState,
    request_context: PreBattleProposalRequest,
    dx: float,
) -> PathWitness:
    if state.battlefield_state is None:
        raise GameLifecycleError("Scout smoke witness requires battlefield_state.")
    unit_placement = state.battlefield_state.unit_placement_by_id(request_context.unit_instance_id)
    paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement in unit_placement.model_placements:
        start = placement.pose
        end = Pose.at(
            start.position.x + dx,
            start.position.y,
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        paths.append(
            (
                placement.model_instance_id,
                (
                    start,
                    Pose.at(
                        start.position.x + (dx / 2.0),
                        start.position.y,
                        start.position.z,
                        facing_degrees=start.facing.degrees,
                    ),
                    end,
                ),
            )
        )
    return PathWitness.for_paths(tuple(paths))


def _model_source_for_id(
    *,
    state: GameState,
    model_instance_id: str,
) -> tuple[str, str, str]:
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id == model_instance_id:
                    return army.army_id, army.player_id, unit.unit_instance_id
    raise GameLifecycleError("Smoke model_instance_id is not mustered.")


def _state(session: LocalGameSession) -> GameState:
    state = session.lifecycle.state
    assert state is not None
    return state


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.decision_request is not None
    return status.decision_request


def _option_ids(request: DecisionRequest) -> tuple[str, ...]:
    return tuple(option.option_id for option in request.options)


def _option_with_prefix(request: DecisionRequest, prefix: str) -> str:
    for option in request.options:
        if option.option_id.startswith(prefix):
            return option.option_id
    raise GameLifecycleError("Expected sequencing option was not emitted.")
