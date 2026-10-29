"""FAQ 30 / P04H: one bearer may use different target models for range and LoS."""

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.fire_overwatch_helpers import choose_shooter, pending_overwatch
from tests.phase13b_shooting_declaration_helpers import (
    _first_weapon_profile,
    _proposal_from_request,
)
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from tests.range_visibility_helpers import SHOOTER, TARGET, range_visibility_scene

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.weapon_profiles import RangeProfile, WeaponKeyword
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.shooting_targets import (
    ShootingTargetCandidate,
    ShootingTargetViolationCode,
    shooting_target_candidate_for_model,
)
from warhammer40k_core.engine.weapon_abilities import INDIRECT_FIRE_NO_VISIBLE_RULE_ID


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("indirect", [False, True])
@pytest.mark.parametrize("hidden_near_model", [False, True])
def test_range_and_visibility_use_independent_models_with_complete_witnesses(
    attached: bool, indirect: bool, hidden_near_model: bool
) -> None:
    session, units = range_visibility_scene(attached=attached)
    lifecycle = session.lifecycle
    state = lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    shooter = units["shooter"]
    profile = replace(
        _first_weapon_profile(lifecycle, shooter), range_profile=RangeProfile.distance(21)
    )
    if indirect:
        profile = replace(profile, keywords=(*profile.keywords, WeaponKeyword.INDIRECT_FIRE))
    candidate = shooting_target_candidate_for_model(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=shooter,
        attacker_model_instance_id=shooter.own_models[0].model_instance_id,
        weapon_profile=profile,
        target_unit_id=TARGET,
        terrain_features=scenario.battlefield_state.terrain_features,
        hidden_target_model_ids=(units["enemy"].own_models[0].model_instance_id,)
        if hidden_near_model
        else (),
    )
    witness = candidate.line_of_sight_witness
    assert witness is not None
    assert witness.visible_model_ids
    assert candidate.target_in_range_model_ids
    assert set(witness.visible_model_ids).isdisjoint(candidate.target_in_range_model_ids)
    assert candidate.is_legal, candidate.to_payload()
    assert candidate.target_visible_model_ids == witness.visible_model_ids
    assert INDIRECT_FIRE_NO_VISIBLE_RULE_ID not in candidate.targeting_rule_ids
    assert len(witness.model_records) == 2
    assert (
        ShootingTargetCandidate.from_payload(json.loads(json.dumps(candidate.to_payload())))
        == candidate
    )


@pytest.mark.parametrize(
    ("range_inches", "expected"), [(1, ShootingTargetViolationCode.OUT_OF_RANGE)]
)
def test_visibility_does_not_replace_required_weapon_range(
    range_inches: int, expected: ShootingTargetViolationCode
) -> None:
    session, units = range_visibility_scene()
    state = session.lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    shooter = units["shooter"]
    candidate = shooting_target_candidate_for_model(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=shooter,
        attacker_model_instance_id=shooter.own_models[0].model_instance_id,
        weapon_profile=replace(
            _first_weapon_profile(session.lifecycle, shooter),
            range_profile=RangeProfile.distance(range_inches),
        ),
        target_unit_id=TARGET,
        terrain_features=scenario.battlefield_state.terrain_features,
    )
    assert not candidate.is_legal
    assert candidate.violation_code is expected


@pytest.mark.parametrize("all_hidden", [False, True])
def test_detection_and_visibility_remain_required(all_hidden: bool) -> None:
    session, units = range_visibility_scene()
    state = session.lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    shooter = units["shooter"]
    hidden_models = units["enemy"].own_models if all_hidden else units["enemy"].own_models[1:]
    candidate = shooting_target_candidate_for_model(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=shooter,
        attacker_model_instance_id=shooter.own_models[0].model_instance_id,
        weapon_profile=replace(
            _first_weapon_profile(session.lifecycle, shooter),
            range_profile=RangeProfile.distance(21),
        ),
        target_unit_id=TARGET,
        terrain_features=scenario.battlefield_state.terrain_features,
        hidden_target_model_ids=tuple(model.model_instance_id for model in hidden_models),
    )
    assert not candidate.is_legal
    assert candidate.violation_code is (
        ShootingTargetViolationCode.OUTSIDE_DETECTION_RANGE
        if all_hidden
        else ShootingTargetViolationCode.NOT_VISIBLE
    )


@pytest.mark.parametrize(
    ("target_key", "expected"),
    [
        ("enemy", ShootingTargetViolationCode.NOT_VISIBLE),
        ("leader", ShootingTargetViolationCode.OUT_OF_RANGE),
    ],
)
def test_different_enemy_units_cannot_combine_range_and_visibility(
    target_key: str, expected: ShootingTargetViolationCode
) -> None:
    session, units = range_visibility_scene(attached=True, separate_units=True)
    state = session.lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    shooter = units["shooter"]
    candidate = shooting_target_candidate_for_model(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=shooter,
        attacker_model_instance_id=shooter.own_models[0].model_instance_id,
        weapon_profile=replace(
            _first_weapon_profile(session.lifecycle, shooter),
            range_profile=RangeProfile.distance(21),
        ),
        target_unit_id=units[target_key].unit_instance_id,
        terrain_features=scenario.battlefield_state.terrain_features,
    )
    assert not candidate.is_legal
    assert candidate.violation_code is expected


def test_hidden_near_model_still_supplies_rapid_fire_half_range() -> None:
    session, _ = range_visibility_scene(rapid_fire=True)
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, option_id=SHOOTER, result_id="order104:unit"
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, option_id="normal", result_id="order104:type"
    )
    request = pending_request(session)
    proposal = _proposal_from_request(request=request, target_unit_id=TARGET)
    accepted = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order104:rapid-fire",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID
    event = next(
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "shooting_declaration_accepted"
    )
    pool = cast(
        list[dict[str, JsonValue]], cast(dict[str, JsonValue], event.payload)["attack_pools"]
    )[0]
    assert len(cast(list[str], pool["target_visible_model_ids"])) == 1
    assert len(cast(list[str], pool["target_in_range_model_ids"])) == 2
    assert pool["attacks"] == 3


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("overwatch", [False, True])
def test_facade_accepts_separate_witnesses_with_restore_continuation_and_replay(
    attached: bool, overwatch: bool
) -> None:
    session, _ = range_visibility_scene(attached=attached, overwatch=overwatch)
    initial = session.lifecycle.to_payload()
    if overwatch:
        status = choose_shooter(session, pending_overwatch(session))
        request = status.decision_request
        assert request is not None
    else:
        request = pending_request(session)
        session.submit_option(
            request_id=request.request_id, option_id=SHOOTER, result_id="order104:unit"
        )
        request = pending_request(session)
        session.submit_option(
            request_id=request.request_id, option_id="normal", result_id="order104:type"
        )
        request = pending_request(session)
    state = session.lifecycle.state
    assert state is not None
    target_id = rules_unit_view_by_id(state=state, unit_instance_id=TARGET).unit_instance_id
    proposal = _proposal_from_request(request=request, target_unit_id=target_id)
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    for current in (session, restored):
        invalid = current.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="order104:stale",
            payload=validate_json_value({**proposal.to_payload(), "proposal_request_id": "stale"}),
        )
        assert invalid.status_kind is LifecycleStatusKind.INVALID
        assert current.to_persistence_payload() == checkpoint
        accepted = current.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="order104:declaration",
            payload=validate_json_value(proposal.to_payload()),
        )
        assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    history = session.lifecycle.decision_controller.event_log.records
    declaration_type = (
        "out_of_phase_shooting_declaration_accepted"
        if overwatch
        else "shooting_declaration_accepted"
    )
    declaration_event = next(event for event in history if event.event_type == declaration_type)
    pools = cast(
        list[dict[str, JsonValue]],
        cast(dict[str, JsonValue], declaration_event.payload)["attack_pools"],
    )
    assert pools
    for pool in pools:
        visible = cast(list[str], pool["target_visible_model_ids"])
        in_range = cast(list[str], pool["target_in_range_model_ids"])
        assert visible
        assert in_range
        assert set(visible).isdisjoint(in_range)
    # Restore the engine-generated accepted attack, then finish through the facade.
    restored = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    for current in (session, restored):
        for _ in range(30):
            if any(
                event.event_type == "attack_sequence_completed"
                for event in current.lifecycle.decision_controller.event_log.records
            ):
                break
            submit_fixture_request(current, pending_request(current))
        else:
            raise AssertionError("Order104 attacks did not complete.")
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    replay = ReplayRunner.from_payload(
        ReplayArtifact.capture(
            artifact_id="order104:replay",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        ).to_payload()
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay
