from __future__ import annotations

import pytest

from warhammer40k_core.geometry.base import BaseShape, CircularBase, OvalBase, RectangularBase


@pytest.mark.parametrize(
    ("base", "transport", "distance", "expected"),
    [
        (CircularBase(1.5), CircularBase(2), 3, True),
        (CircularBase(1.5001), CircularBase(2), 3, False),
        (CircularBase(2.5), CircularBase(2), 3, False),
        (CircularBase(2.5), CircularBase(2), 6, True),
        (CircularBase(3.1), RectangularBase(6, 2), 6, False),
        (OvalBase(8, 2), RectangularBase(10, 2), 3, True),
        (OvalBase(8, 4), RectangularBase(10, 2), 3, False),
        (RectangularBase(8, 2), RectangularBase(10, 2), 3, True),
        (RectangularBase(8, 4), RectangularBase(10, 2), 3, False),
        (OvalBase(20, 2), CircularBase(2), 3, False),
        (OvalBase(5, 1), CircularBase(2), 3, True),
        (OvalBase(8, 2), CircularBase(2), 3, False),
        (RectangularBase(8, 2), CircularBase(2), 3, False),
        (OvalBase(8, 2), OvalBase(6, 2), 3, True),
        (RectangularBase(8, 2), OvalBase(6, 2), 3, True),
        (OvalBase(8, 2), RectangularBase(6, 2), 3, True),
    ],
)
def test_size_exception_requires_impossible_fit_at_every_orientation(
    base: BaseShape, transport: BaseShape, distance: float, expected: bool
) -> None:
    from warhammer40k_core.geometry.disembark_fit import base_fits_disembark_distance

    assert base_fits_disembark_distance(base, transport, distance) is expected
    assert base_fits_disembark_distance(base, transport, distance) is expected


@pytest.mark.parametrize(
    ("diameter", "gap", "valid"), [(5, 0.5, True), (5, 1, True), (5, 1.01, False), (3, 0.5, False)]
)
def test_disembark_size_proof_and_one_inch_limit(diameter: float, gap: float, valid: bool) -> None:
    from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID
    from tests.large_model_disembark_helpers import (
        large_disembark_placement,
        large_disembark_session,
    )

    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.damage_allocation import unit_by_id
    from warhammer40k_core.engine.transports import (
        DisembarkModeKind,
        DisembarkSelection,
        TransportMovementStatus,
        resolve_disembark,
    )

    session = large_disembark_session(diameter=diameter)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    result = resolve_disembark(
        scenario=battlefield_scenario_for_state(state=state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        cargo_state=state.transport_cargo_states[0],
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=PASSENGER_ID,
            transport_unit_instance_id=TRANSPORT_ID,
            attempted_placement=large_disembark_placement(session, gap=gap),
            disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=unit_by_id(state=state, unit_instance_id=PASSENGER_ID),
        transport_placement=state.battlefield_state.unit_placement_by_id(TRANSPORT_ID),
    )
    assert result.is_valid is valid, result.violations


@pytest.mark.parametrize(
    "mode_name", ["tactical_disembark", "assault_disembark", "shock_disembark"]
)
@pytest.mark.parametrize("prevalidation", [False, True])
def test_oversized_disembark_facade_retry_restore_and_exact_replay(
    mode_name: str, prevalidation: bool
) -> None:
    import json
    from dataclasses import replace

    from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID
    from tests.large_model_disembark_helpers import (
        large_disembark_placement,
        large_disembark_session,
    )
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.movement_proposals import PlacementProposalPayload, ProposalKind
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner
    from warhammer40k_core.engine.transports import (
        DisembarkModeKind,
        TransportMovementStatus,
        TransportRestrictionOverride,
        TransportRestrictionOverrideKind,
    )

    mode = DisembarkModeKind(mode_name)
    session = large_disembark_session(
        modes=() if mode is DisembarkModeKind.TACTICAL_DISEMBARK else (mode,)
    )
    request = pending_request(session)
    initial = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id, result_id="select-cargo", option_id=PASSENGER_ID
    )
    assert status.decision_request is not None
    status = session.submit_option(
        request_id=status.decision_request.request_id,
        result_id="select-disembark",
        option_id="disembark"
        if mode is DisembarkModeKind.TACTICAL_DISEMBARK
        else f"disembark:{mode.value}",
    )
    assert status.decision_request is not None
    request = status.decision_request
    state = session.lifecycle.state
    assert state is not None
    submission = PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.DISEMBARK,
        unit_instance_id=PASSENGER_ID,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_placement=large_disembark_placement(session),
        transport_unit_instance_id=TRANSPORT_ID,
        disembark_mode=mode,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
        restriction_overrides=()
        if mode is DisembarkModeKind.TACTICAL_DISEMBARK
        else (
            TransportRestrictionOverride(
                override_kind=TransportRestrictionOverrideKind.ALLOW_ASSAULT_DISEMBARK
                if mode is DisembarkModeKind.ASSAULT_DISEMBARK
                else TransportRestrictionOverrideKind.ALLOW_SHOCK_DISEMBARK,
                source_rule_id=f"test:order38:grant:{mode.value}",
            ),
        ),
        start_engaged_enemy_unit_instance_ids=()
        if mode is DisembarkModeKind.SHOCK_DISEMBARK
        else None,
    )
    # Malformed and wrong-context requests do not consume the pending decision.
    for kind in ("malformed", "wrong_context") if prevalidation else ():
        raw = validate_json_value(submission.to_payload())
        assert isinstance(raw, dict)
        if kind == "malformed":
            del raw["disembark_mode"]
        else:
            raw["transport_unit_instance_id"] = "other-transport"
        before = state.to_payload()
        records = tuple(session.lifecycle.decision_controller.records)
        rejected = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=kind,
            payload=raw,
        )
        assert rejected.status_kind is LifecycleStatusKind.INVALID
        assert state.to_payload() == before
        assert tuple(session.lifecycle.decision_controller.records) == records
        assert session.lifecycle.pending_decision_request() == request
    if prevalidation:
        # Rejected pre-pop diagnostics are checkpoint history, not DecisionRecords.
        initial = session.lifecycle.to_payload()
    # Well-formed illegal endpoints retain the cargo and expose a fresh retry.
    rejected = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="outside-one-inch",
        payload=validate_json_value(
            replace(
                submission, attempted_placement=large_disembark_placement(session, gap=1.01)
            ).to_payload()
        ),
    )
    assert rejected.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_or_none(PASSENGER_ID) is None
    request = pending_request(session)
    submission = replace(submission, proposal_request_id=request.request_id)
    restored_pending = LocalGameSession(
        lifecycle=GameLifecycle.from_payload(session.lifecycle.to_payload())
    )
    for viewer in state.player_ids:
        assert session.view(viewer_player_id=viewer) == restored_pending.view(
            viewer_player_id=viewer
        )
    for target in (session, restored_pending):
        accepted = target.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="place-large-base",
            payload=validate_json_value(submission.to_payload()),
        )
        assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted
    assert session.lifecycle.to_payload() == restored_pending.lifecycle.to_payload()
    restored = LocalGameSession(
        lifecycle=GameLifecycle.from_payload(session.lifecycle.to_payload())
    )
    for viewer in state.player_ids:
        assert session.view(viewer_player_id=viewer) == restored.view(viewer_player_id=viewer)
        assert session.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == restored.events_since(EventStreamCursor(), viewer_player_id=viewer)
    replay = ReplayRunner(
        ReplayArtifact.capture(
            artifact_id="order55",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        )
    ).run()
    assert replay.reproduced_exactly, replay
    assert "object at 0x" not in json.dumps(session.lifecycle.to_payload(), sort_keys=True)


@pytest.mark.parametrize(
    "mode_name",
    [
        "rapid_disembark",
        "tactical_disembark",
        "assault_disembark",
        "shock_disembark",
        "combat_disembark",
        "destroyed_transport",
        "emergency_disembark",
    ],
)
@pytest.mark.parametrize("enemy_nearby", [False, True])
def test_every_mode_uses_size_proof_and_requires_exceptional_models_unengaged(
    mode_name: str, enemy_nearby: bool
) -> None:
    from dataclasses import replace

    from tests.core_stratagem_helpers import _replace_unit_poses
    from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID
    from tests.large_model_disembark_helpers import (
        large_disembark_placement,
        large_disembark_session,
    )

    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.damage_allocation import unit_by_id
    from warhammer40k_core.engine.transports import (
        DisembarkModeKind,
        DisembarkSelection,
        TransportMovementStatus,
        TransportOperationViolationCode,
        TransportRestrictionOverride,
        TransportRestrictionOverrideKind,
        resolve_disembark_internal,
    )
    from warhammer40k_core.geometry.pose import Pose

    session = large_disembark_session(diameter=7)
    state = session.lifecycle.state
    assert state is not None
    mode = DisembarkModeKind(mode_name)
    if enemy_nearby:
        enemy = state.army_definitions[1].units[0]
        _replace_unit_poses(
            state,
            unit_instance_id=enemy.unit_instance_id,
            poses=tuple(Pose.at(13.5 + 2 * i, 11) for i, _ in enumerate(enemy.own_models)),
        )
    scenario = battlefield_scenario_for_state(state=state)
    permission: tuple[TransportRestrictionOverride, ...] = ()
    if mode in {DisembarkModeKind.ASSAULT_DISEMBARK, DisembarkModeKind.SHOCK_DISEMBARK}:
        permission = (
            TransportRestrictionOverride(
                override_kind=TransportRestrictionOverrideKind.ALLOW_ASSAULT_DISEMBARK
                if mode is DisembarkModeKind.ASSAULT_DISEMBARK
                else TransportRestrictionOverrideKind.ALLOW_SHOCK_DISEMBARK,
                source_rule_id="test:oversized-disembark-permission",
            ),
        )
    selection = DisembarkSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=PASSENGER_ID,
        transport_unit_instance_id=TRANSPORT_ID,
        attempted_placement=large_disembark_placement(session),
        disembark_mode=mode,
        transport_movement_status=TransportMovementStatus.NORMAL_MOVE
        if mode is DisembarkModeKind.RAPID_DISEMBARK
        else TransportMovementStatus.NOT_MOVED,
        restriction_overrides=permission,
        start_engaged_enemy_unit_instance_ids=(state.army_definitions[1].units[0].unit_instance_id,)
        if enemy_nearby and mode is DisembarkModeKind.SHOCK_DISEMBARK
        else (),
    )
    result = resolve_disembark_internal(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        cargo_state=state.transport_cargo_states[0],
        selection=selection,
        unit=unit_by_id(state=state, unit_instance_id=PASSENGER_ID),
        transport_placement=scenario.battlefield_state.unit_placement_by_id(TRANSPORT_ID),
        turn_player_id="player-a",
        require_started_phase_embarked=False,
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        terrain_features=(),
        objective_markers=(),
    )
    assert result.is_valid is (not enemy_nearby), result.violations
    if enemy_nearby:
        assert any(
            v.violation_code is TransportOperationViolationCode.ENEMY_ENGAGEMENT_RANGE
            for v in result.violations
        )
        assert result.updated_cargo_state is None
    else:
        assert type(result).from_payload(result.to_payload()) == result
    # Reusing the same geometry at another mode's distance cannot reuse a wrong proof.
    if mode is DisembarkModeKind.EMERGENCY_DISEMBARK and not enemy_nearby:
        smaller = large_disembark_session(diameter=5)
        smaller_state = smaller.lifecycle.state
        assert smaller_state is not None
        smaller_result = resolve_disembark_internal(
            scenario=battlefield_scenario_for_state(state=smaller_state),
            ruleset_descriptor=smaller_state.runtime_ruleset_descriptor(),
            cargo_state=smaller_state.transport_cargo_states[0],
            selection=replace(
                selection, attempted_placement=large_disembark_placement(smaller, gap=1.01)
            ),
            unit=unit_by_id(state=smaller_state, unit_instance_id=PASSENGER_ID),
            transport_placement=scenario.battlefield_state.unit_placement_by_id(TRANSPORT_ID),
            turn_player_id="player-a",
            require_started_phase_embarked=False,
            battlefield_width_inches=60,
            battlefield_depth_inches=44,
            terrain_features=(),
            objective_markers=(),
        )
        assert not smaller_result.is_valid
        assert any(
            v.violation_code is TransportOperationViolationCode.DISEMBARK_DISTANCE
            for v in smaller_result.violations
        )
