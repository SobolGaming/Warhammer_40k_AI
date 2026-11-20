"""11.04 physical producer, endpoint obligations, rejection and continuation."""

import json
from types import SimpleNamespace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import add_enemy, pending
from tests.support.section11_fixtures import (
    events,
    modifier,
    propose,
    resolution,
    select,
    session_for,
    state_case,
    targets,
    witness,
)
from warhammer40k_core.engine.charge_model_endpoints import ChargeModelEndpointWitness
from warhammer40k_core.engine.charge_move_event_authority import (
    ChargeMoveCompletedEventAuthority,
    validate_charge_move_completed_event_authority,
)
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.movement_decision_authority import reuse_live_movement_history
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.geometry import milli_inch_symbolic
from warhammer40k_core.geometry.movement_envelope import MovementDistanceUnresolvedError
from warhammer40k_core.geometry.path_measurement import interpolate_pose
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize(
    ("dx", "code"),
    [
        (0, "charge_not_closer_to_target"),
        (-1, "charge_not_closer_to_target"),
        (0.5, "charge_target_not_engaged"),
        (4.25, None),
    ],
)
def test_real_native_endpoint_producer_enforces_approach_and_engagement(
    section11_definitions: Section02Definitions,
    dx: float,
    code: str | None,
) -> None:
    state, unit, enemy = state_case(section11_definitions)
    before = state.to_payload()
    result = resolution(
        state,
        unit.unit_instance_id,
        (enemy.unit_instance_id,),
        witness(state, unit.unit_instance_id, dx),
    )
    assert result.endpoint_violation_code == code
    assert result.is_valid is (code is None)
    assert state.to_payload() == before
    row = result.endpoint_witness.model_endpoints[0]
    assert row.model_instance_id == unit.own_model_ids()[0]
    assert row.component_unit_instance_id == unit.unit_instance_id
    assert row.ended_closer is (dx > 0)
    assert ChargeModelEndpointWitness.from_payload(json.loads(json.dumps(row.to_payload()))) == row
    if code is None:
        assert row.preferred_reachability.status == "satisfied"
        assert row.engagement_reachability.status == "satisfied"
        from tests.support.section03_fixtures import scenario
        from warhammer40k_core.engine.charge_movement_source import charge_movement_placement

        batch = result.transition_batch(
            before=charge_movement_placement(
                scenario=scenario(state), unit_instance_id=unit.unit_instance_id
            )
        )
        assert batch.displacements


def test_reachable_one_inch_endpoint_is_required_by_real_query(
    section11_definitions: Section02Definitions,
) -> None:
    state, unit, enemy = state_case(section11_definitions)
    result = resolution(
        state,
        unit.unit_instance_id,
        (enemy.unit_instance_id,),
        witness(state, unit.unit_instance_id, 3.5),
    )
    assert not result.is_valid
    assert result.endpoint_violation_code == "charge_preferred_distance_not_reached"
    row = result.endpoint_witness.model_endpoints[0]
    assert row.preferred_reachability.status == "reachable"
    assert row.preferred_reachability.alternative_witness is not None
    assert row.engagement_reachability.status == "satisfied"


@pytest.mark.parametrize(
    "invalid",
    ["not_closer", "too_short", "missing_model", "foreign_model", "start_drift", "missing_payload"],
)
def test_public_rejects_bad_move_without_displacement_then_accepts_legal_retry(
    section11_definitions: Section02Definitions,
    invalid: str,
) -> None:
    state, unit, enemy = state_case(section11_definitions)
    modifier(state, unit.unit_instance_id, 12)
    session = session_for(section11_definitions, state)
    select(session, unit)
    request = targets(session, (enemy.unit_instance_id,))
    before = state.battlefield_state
    effects = tuple(state.persisting_effects)
    path = witness(
        state,
        unit.unit_instance_id,
        0 if invalid == "not_closer" else 0.5 if invalid == "too_short" else 4.25,
    )
    if invalid == "missing_model":
        # Empty physical inventory is schema-invalid; foreign and missing-model
        # cases use a nonempty well-formed witness for fail-closed membership.
        path = PathWitness.for_paths((("absent:model", (Pose.at(10, 10), Pose.at(14.25, 10))),))
    elif invalid == "foreign_model":
        path = PathWitness.for_paths(
            ((enemy.own_model_ids()[0], (Pose.at(10, 10), Pose.at(14.25, 10))),)
        )
    elif invalid == "start_drift":
        path = PathWitness.for_paths(
            ((unit.own_model_ids()[0], (Pose.at(10.1, 10), Pose.at(14.25, 10))),)
        )
    if invalid == "missing_payload":
        status = session.submit_parameterized_payload(
            request_id=request.request_id, result_id="bad", payload={}
        )
    else:
        status = propose(
            session, unit.unit_instance_id, (enemy.unit_instance_id,), path, result_id="bad"
        )
    assert status.status_kind is LifecycleStatusKind.INVALID, status
    assert state.battlefield_state == before
    assert tuple(state.persisting_effects) == effects
    assert not events(session, "charge_move_completed")
    retry = pending(session)
    assert retry.decision_type == "submit_movement_proposal"
    status = propose(
        session,
        unit.unit_instance_id,
        (enemy.unit_instance_id,),
        witness(state, unit.unit_instance_id, 4.25),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert len(events(session, "charge_move_completed")) == 1
    assert pending(session).decision_type == "select_charging_unit"
    assert unit.unit_instance_id not in {o.option_id for o in pending(session).options}


@pytest.mark.parametrize("select_both", [False, True])
def test_every_selected_target_must_be_engaged_and_other_engagement_is_forbidden(
    section11_definitions: Section02Definitions,
    select_both: bool,
) -> None:
    state, unit, enemy = state_case(section11_definitions)
    assert state.battlefield_state is not None
    target_x = (
        state.battlefield_state.unit_placement_by_id(enemy.unit_instance_id)
        .model_placements[0]
        .pose.position.x
    )
    other = add_enemy(section11_definitions, state, x=target_x, y=12.5)
    ids = (
        tuple(sorted((enemy.unit_instance_id, other.unit_instance_id)))
        if select_both
        else (enemy.unit_instance_id,)
    )
    result = resolution(
        state, unit.unit_instance_id, ids, witness(state, unit.unit_instance_id, 4.9, 1.25)
    )
    assert result.is_valid is select_both
    assert result.endpoint_violation_code == (None if select_both else "charge_non_target_engaged")
    assert set(result.endpoint_witness.engaged_target_unit_instance_ids) == set(ids)
    assert result.endpoint_witness.non_target_engaged_unit_instance_ids == (
        () if select_both else (other.unit_instance_id,)
    )


def test_approaching_one_target_does_not_excuse_missing_another_selected_target(
    section11_definitions: Section02Definitions,
) -> None:
    state, unit, enemy = state_case(section11_definitions)
    other = add_enemy(section11_definitions, state, x=10, y=17)
    ids = tuple(sorted((enemy.unit_instance_id, other.unit_instance_id)))
    result = resolution(
        state, unit.unit_instance_id, ids, witness(state, unit.unit_instance_id, 4.25)
    )
    assert not result.is_valid
    assert result.endpoint_violation_code == "charge_target_not_engaged"
    assert result.endpoint_witness.engaged_target_unit_instance_ids == (enemy.unit_instance_id,)


@pytest.mark.parametrize("maximum", [4.249, 4.25, 4.251])
def test_witnessed_charge_path_obeys_rolled_distance_limit(
    section11_definitions: Section02Definitions,
    maximum: float,
) -> None:
    state, unit, enemy = state_case(section11_definitions)
    result = resolution(
        state,
        unit.unit_instance_id,
        (enemy.unit_instance_id,),
        witness(state, unit.unit_instance_id, 4.25),
        maximum,
    )
    assert result.is_valid is (maximum >= 4.25)
    assert all(r.is_valid for r in result.path_validation_results) is (maximum >= 4.25)


def test_long_detour_is_not_replaced_by_short_endpoint_distance(
    section11_definitions: Section02Definitions,
) -> None:
    state, unit, enemy = state_case(section11_definitions)
    path = PathWitness.for_paths(
        ((unit.own_model_ids()[0], (Pose.at(10, 10), Pose.at(10, 16), Pose.at(14.25, 10))),)
    )
    result = resolution(state, unit.unit_instance_id, (enemy.unit_instance_id,), path, 6)
    assert not result.is_valid
    assert not all(r.is_valid for r in result.path_validation_results)
    with pytest.raises(GameLifecycleError, match="Invalid Charge Move"):
        result.transition_batch(before=result.attempted_placement)


@pytest.mark.parametrize("choice", ["targets", "move"])
def test_optional_charge_move_consumes_declaration_without_fights_first(
    section11_definitions: Section02Definitions,
    choice: str,
) -> None:
    state, unit, enemy = state_case(section11_definitions)
    modifier(state, unit.unit_instance_id, 12)
    session = session_for(section11_definitions, state)
    select(session, unit)
    before = state.battlefield_state
    if choice == "targets":
        from tests.support.section11_fixtures import choose

        choose(session, "decline_charge_targets", result_id="decline")
    else:
        targets(session, (enemy.unit_instance_id,))
        status = propose(session, unit.unit_instance_id, (), None)
        assert status.status_kind is not LifecycleStatusKind.INVALID
    assert state.battlefield_state == before
    assert state.charge_phase_state is not None
    assert state.charge_phase_state.active_selection is None
    assert state.charge_phase_state.selected_unit_ids == (unit.unit_instance_id,)
    assert not events(session, "charge_move_completed")
    assert not any(
        isinstance(e.effect_payload, dict)
        and e.effect_payload.get("effect_kind") == "charge_grants_fights_first"
        for e in state.persisting_effects
    )
    assert unit.unit_instance_id not in {o.option_id for o in pending(session).options}


def test_real_solid_obstacle_rejects_charge_despite_short_target_range(
    section11_definitions: Section02Definitions,
) -> None:
    from tests.support.section03_fixtures import scenario
    from warhammer40k_core.engine.charge_movement_source import charge_movement_placement
    from warhammer40k_core.engine.phases.charge import resolve_charge_move
    from warhammer40k_core.geometry.pose import Point3
    from warhammer40k_core.geometry.terrain import TerrainVolume

    state, unit, enemy = state_case(section11_definitions)
    result = resolve_charge_move(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=charge_movement_placement(
            scenario=scenario(state), unit_instance_id=unit.unit_instance_id
        ),
        selected_target_unit_instance_ids=(enemy.unit_instance_id,),
        maximum_distance_inches=6,
        path_witness=witness(state, unit.unit_instance_id, 4.25),
        terrain=(TerrainVolume("constructed:solid-obstacle", Point3(12.1, 10, 0), 0.5, 3, 5),),
    )
    assert not result.is_valid
    assert any(
        v.violation_code == "terrain_feature_transit_forbidden"
        for r in result.terrain_path_legality_results
        for v in r.violations
    )


def test_one_inch_obligation_is_unreachable_when_real_budget_stops_at_engagement(
    section11_definitions: Section02Definitions,
) -> None:
    state, unit, enemy = state_case(section11_definitions)
    result = resolution(
        state,
        unit.unit_instance_id,
        (enemy.unit_instance_id,),
        witness(state, unit.unit_instance_id, 3.5),
        3.5,
    )
    assert result.is_valid
    row = result.endpoint_witness.model_endpoints[0]
    assert row.preferred_reachability.status == "unreachable"
    assert row.engagement_reachability.status == "satisfied"


def test_native_charge_certification_timeout_leaves_the_same_proposal_retryable(
    section11_definitions: Section02Definitions,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, unit, enemy = state_case(section11_definitions)
    modifier(state, unit.unit_instance_id, 12)
    session = session_for(section11_definitions, state)
    select(session, unit)
    selected_targets = (enemy.unit_instance_id,)
    request = targets(session, selected_targets)
    legal = witness(state, unit.unit_instance_id, 4.25)
    two_segments = PathWitness.for_paths(
        tuple(
            (model_id, (start, interpolate_pose(start, end, 0.5), end))
            for model_id, (start, end) in legal.model_paths
        )
    )
    before = session.lifecycle.to_payload()
    clock = iter((0.0, 11.0))
    with monkeypatch.context() as patch:
        patch.setattr(milli_inch_symbolic, "time", SimpleNamespace(monotonic=clock.__next__))
        expired = propose(
            session, unit.unit_instance_id, selected_targets, two_segments, result_id="retry-charge"
        )
    assert expired.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(expired.payload, dict)
    validation = expired.payload["proposal_validation"]
    assert isinstance(validation, dict)
    violations = validation["violations"]
    assert isinstance(violations, list)
    assert len(violations) == 1
    assert isinstance(violations[0], dict)
    assert violations[0]["violation_code"] == "movement_distance_unresolved"
    assert pending(session) == request
    assert session.lifecycle.to_payload() == before

    record_count = session.decision_record_count()
    measured = False

    def clock_before_commit() -> float:
        nonlocal measured
        assert session.decision_record_count() == record_count
        measured = True
        return 0.0

    with monkeypatch.context() as patch:
        patch.setattr(milli_inch_symbolic, "time", SimpleNamespace(monotonic=clock_before_commit))
        accepted = propose(
            session, unit.unit_instance_id, selected_targets, two_segments, result_id="retry-charge"
        )
    assert measured
    assert accepted.status_kind is not LifecycleStatusKind.INVALID
    assert len(events(session, "charge_move_completed")) == 1
    assert (
        sum(
            record.result.result_id == "retry-charge"
            for record in session.lifecycle.decision_controller.records
        )
        == 1
    )

    decisions = session.lifecycle.decision_controller
    event_records = decisions.event_log.records
    (event_index,) = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "charge_move_completed"
    )

    descriptor = session.lifecycle.config.ruleset_descriptor

    def charge_authority(history: tuple[EventRecord, ...]) -> ChargeMoveCompletedEventAuthority:
        payload = history[event_index].payload
        assert isinstance(payload, dict)
        return validate_charge_move_completed_event_authority(
            event_records=history,
            decision_records=decisions.records,
            event_index=event_index,
            payload=payload,
            ruleset_descriptor=descriptor,
            configured_ruleset_descriptor_hash=descriptor.descriptor_hash,
        )

    expected_authority = charge_authority(event_records)
    copied_charge = EventRecord.from_payload(event_records[event_index].to_payload())
    reloaded_history = (
        *event_records[:event_index],
        copied_charge,
        *event_records[event_index + 1 :],
    )

    def expire(*_args: object, **_kwargs: object) -> int:
        raise milli_inch_symbolic.UnresolvedDistanceMeasurementError("test clock expired")

    with monkeypatch.context() as patch:
        patch.setattr(milli_inch_symbolic, "symbolic_squared_path_inches_to_ticks", expire)
        with reuse_live_movement_history(decisions.event_log):
            assert charge_authority(event_records) == expected_authority
            assert charge_authority(event_records[: event_index + 1]) == expected_authority
            with pytest.raises(MovementDistanceUnresolvedError):
                charge_authority(reloaded_history)
        with pytest.raises(MovementDistanceUnresolvedError):
            charge_authority(event_records)
