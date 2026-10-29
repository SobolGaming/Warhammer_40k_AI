"""An engine-accepted edge ingress must retain its incoming normal shooting."""

import json
from dataclasses import replace

from tests.order128_helpers import assert_checkpoint
from tests.order135_visibility_helpers import edge_shooting_boundary
from tests.phase13b_shooting_declaration_helpers import _proposal_from_request
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_visibility_context import battlefield_visibility_context
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.shooting_targets import (
    ShootingTargetViolationCode,
    shooting_target_candidates_for_unit,
)
from warhammer40k_core.geometry.physical_visibility import BattlefieldVisibilityBounds


def test_native_legal_edge_ingress_accepts_incoming_attack_with_cover_restore_and_replay() -> None:
    session, request = edge_shooting_boundary()
    state = session.lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    alpha_army = state.army_definition_for_player("player-a")
    beta_army = state.army_definition_for_player("player-b")
    assert alpha_army is not None
    assert beta_army is not None
    alpha = alpha_army.units[0]
    beta = beta_army.units[0]
    alpha_model, beta_model = (
        next(
            m
            for m in scenario.placed_geometry_models()
            if m.model_id == u.own_models[0].model_instance_id
        )
        for u in (alpha, beta)
    )
    context = battlefield_visibility_context(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        los_cache_key="order135:native-edge",
        observer_model=beta_model,
        target_models=(alpha_model,),
        target_model_keywords=((alpha_model.model_id, ()),),
        terrain_features=scenario.battlefield_state.terrain_features,
    )
    witness = context.resolve_line_of_sight()
    assert witness.unit_visible
    assert not witness.unit_fully_visible
    assert context.resolve_line_of_sight_uncached() == witness
    assert context.not_fully_visible_because_of(
        witness, target_model_id=alpha_model.model_id, sources=witness.all_blocker_records()
    )
    assert context.benefit_of_cover(witness).has_benefit
    assert type(context).from_payload(json.loads(json.dumps(context.to_payload()))) == context
    assert type(context.battlefield_bounds) is BattlefieldVisibilityBounds
    reverse = replace(
        context,
        observer_model=alpha_model,
        target_models=(beta_model,),
        target_model_keywords=((beta_model.model_id, ()),),
    )
    assert not reverse.resolve_line_of_sight().unit_visible
    assert replace(reverse, battlefield_bounds=None).resolve_line_of_sight().unit_visible
    weapon = next(
        w
        for w in session.lifecycle.config.army_catalog.wargear
        if w.wargear_id == alpha.wargear_selections[0].wargear_ids[0]
    ).weapon_profiles[0]
    (outgoing,) = shooting_target_candidates_for_unit(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=alpha,
        weapon_profile=weapon,
        target_unit_ids=(beta.unit_instance_id,),
        terrain_features=scenario.battlefield_state.terrain_features,
    )
    assert not outgoing.is_legal
    assert outgoing.violation_code is ShootingTargetViolationCode.NOT_VISIBLE
    assert outgoing.target_in_range_model_ids
    assert_checkpoint(session)
    status = session.submit_option(
        request_id=request.request_id, option_id="normal", result_id="order135:normal"
    )
    assert status.decision_request is not None
    assert status.decision_request.decision_type == "submit_shooting_declaration"
    request = status.decision_request
    proposal = _proposal_from_request(request=request, target_unit_id=alpha.unit_instance_id)
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    recovered = LocalGameSession.from_persistence_payload(checkpoint)
    forked = session.fork()
    for current in (session, recovered, forked):
        accepted = current.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="order135:incoming-declaration",
            payload=validate_json_value(proposal.to_payload()),
        )
        assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted.to_payload()
        assert any(
            e.event_type == "shooting_declaration_accepted"
            for e in current.lifecycle.decision_controller.event_log.records
        )
        for _ in range(40):
            if any(
                e.event_type == "attack_sequence_completed"
                for e in current.lifecycle.decision_controller.event_log.records
            ):
                break
            submit_fixture_request(current, pending_request(current))
        else:
            raise AssertionError("Incoming edge attack did not complete.")
    assert recovered.to_persistence_payload() == session.to_persistence_payload()
    assert forked.to_persistence_payload() == session.to_persistence_payload()
    for viewer in ("player-a", "player-b"):
        assert recovered.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert recovered.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    assert_checkpoint(session)
