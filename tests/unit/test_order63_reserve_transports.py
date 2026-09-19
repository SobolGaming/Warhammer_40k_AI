from copy import deepcopy

import pytest
from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID
from tests.order63_reserve_transport_helpers import reserve_transport_session, submit_ingress


def test_carrier_ingresses_without_placing_or_releasing_cargo() -> None:
    session = reserve_transport_session()
    submit_ingress(session)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_or_none(TRANSPORT_ID) is not None
    assert state.battlefield_state.unit_placement_or_none(PASSENGER_ID) is None
    assert state.transport_cargo_states[0].embarked_unit_instance_ids == (PASSENGER_ID,)
    assert state.reserve_state_for_unit(PASSENGER_ID) is None


def test_legal_rapid_disembark_restores_and_replays() -> None:
    from tests.order63_reserve_transport_helpers import rapid_disembark

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner

    session = reserve_transport_session()
    initial = session.lifecycle.to_payload()
    submit_ingress(session)
    arrived = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(arrived).to_payload() == arrived
    outcome = rapid_disembark(session, y=5)
    assert outcome.status_kind is not LifecycleStatusKind.INVALID, outcome
    final = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(final).to_payload() == final
    replay = ReplayRunner(
        ReplayArtifact.capture(
            artifact_id="order63:carrier-cargo",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        )
    ).run()
    assert replay.reproduced_exactly, replay


def test_rapid_disembark_inherits_enemy_distance_on_every_model() -> None:
    from tests.core_stratagem_helpers import _replace_unit_poses
    from tests.order63_reserve_transport_helpers import rapid_disembark

    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.geometry.pose import Pose

    session = reserve_transport_session()
    state = session.lifecycle.state
    assert state is not None
    enemy = state.army_definitions[1].units[0]
    _replace_unit_poses(
        state,
        unit_instance_id=enemy.unit_instance_id,
        poses=tuple(Pose.at(10.7 + i * 1.3, 14) for i in range(len(enemy.own_models))),
    )
    submit_ingress(session)
    assert state.battlefield_state is not None
    before = state.battlefield_state.to_payload()
    outcome = rapid_disembark(session, y=5)
    assert outcome.status_kind is LifecycleStatusKind.INVALID
    assert "rapid_disembark_ingress_restriction" in str(outcome.payload)
    assert state.battlefield_state.to_payload() == before


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("enemy_distance_inches", 1.0),
        ("edge_distance_inches", None),
        ("excludes_enemy_deployment_zone", False),
        ("placement_kind", "deep_strike"),
        (
            "source_distances",
            [
                {
                    "source_id": "forged",
                    "source_model_instance_id": "unknown",
                    "minimum_distance_inches": 12.0,
                }
            ],
        ),
    ],
)
def test_restore_reconstructs_arrival_policy_instead_of_trusting_saved_claims(
    field: str, value: object
) -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = reserve_transport_session()
    submit_ingress(session)
    payload = deepcopy(session.lifecycle.to_payload())
    for event in payload["decisions"]["event_log"]:
        if event["event_type"] == "reinforcement_unit_arrived":
            event_payload = event["payload"]
            assert isinstance(event_payload, dict)
            policy = event_payload["ingress_placement_restrictions"]
            assert isinstance(policy, dict)
            from warhammer40k_core.engine.event_log import validate_json_value

            policy[field] = validate_json_value(value)
    with pytest.raises(GameLifecycleError, match=r"Ingress|ingress"):
        GameLifecycle.from_payload(payload)


def test_restore_requires_independent_pre_ingress_origin() -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = reserve_transport_session()
    submit_ingress(session)
    payload = session.lifecycle.to_payload()
    del payload["ingress_placement_history_origin"]
    with pytest.raises(GameLifecycleError, match="pre-ingress authority"):
        GameLifecycle.from_payload(payload)


def test_rapid_disembark_rejects_model_outside_inherited_edge_band() -> None:
    from tests.order63_reserve_transport_helpers import rapid_disembark

    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = reserve_transport_session()
    submit_ingress(session)
    outcome = rapid_disembark(session, y=5.7)
    assert outcome.status_kind is LifecycleStatusKind.INVALID
    assert "rapid_disembark_ingress_restriction" in str(outcome.payload)


def test_cargo_cannot_independently_ingress() -> None:
    from tests.psychic_modifier_helpers import pending_request

    session = reserve_transport_session()
    request = pending_request(session)
    outcome = session.submit_option(
        request_id=request.request_id,
        result_id="order63:cargo-before-carrier",
        option_id=PASSENGER_ID,
    )
    assert outcome.decision_request is not None
    assert "ingress" not in {option.option_id for option in outcome.decision_request.options}


def test_internal_ingress_evidence_is_absent_from_both_viewers() -> None:
    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.engine.event_log import canonical_json, validate_json_value

    session = reserve_transport_session()
    submit_ingress(session)
    for player_id in ("player-a", "player-b"):
        text = canonical_json(
            validate_json_value(
                {
                    "view": session.view(viewer_player_id=player_id),
                    "events": session.events_since(EventStreamCursor(), viewer_player_id=player_id),
                }
            )
        )
        assert "ingress_placement_history_origin" not in text
        assert "ingress_placement_restrictions" not in text


@pytest.mark.parametrize("change", ["stale", "malformed", "wrong_transport"])
def test_invalid_passenger_submission_preserves_request_and_state(change: str) -> None:
    from tests.order63_reserve_transport_helpers import rapid_disembark_proposal

    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = reserve_transport_session()
    submit_ingress(session)
    request, proposal = rapid_disembark_proposal(session, y=5)
    payload = validate_json_value(proposal.to_payload())
    assert isinstance(payload, dict)
    if change == "stale":
        payload["proposal_request_id"] = "old-request"
    elif change == "malformed":
        payload["attempted_placement"] = "not-a-placement"
    else:
        payload["transport_unit_instance_id"] = "other-transport"
    before = session.lifecycle.to_payload()
    outcome = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="order63:bad", payload=payload
    )
    assert outcome.status_kind is LifecycleStatusKind.INVALID
    after = session.lifecycle.to_payload()
    assert after["state"] == before["state"]
    assert after["decisions"]["queue"] == before["decisions"]["queue"]
    assert after["decisions"]["records"] == before["decisions"]["records"]


def test_rule_invalid_inherited_edge_retries_then_replays() -> None:
    from dataclasses import replace

    from tests.order63_reserve_transport_helpers import rapid_disembark_proposal
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner
    from warhammer40k_core.geometry.pose import Pose

    session = reserve_transport_session()
    initial = session.lifecycle.to_payload()
    submit_ingress(session)
    request, proposal = rapid_disembark_proposal(session, y=5.7)
    outcome = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order63:edge-invalid",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert outcome.status_kind is LifecycleStatusKind.INVALID
    request = pending_request(session)
    assert proposal.attempted_placement is not None
    legal = replace(
        proposal,
        proposal_request_id=request.request_id,
        attempted_placement=replace(
            proposal.attempted_placement,
            model_placements=tuple(
                replace(row, pose=Pose.at(row.pose.position.x, 5))
                for row in proposal.attempted_placement.model_placements
            ),
        ),
    )
    outcome = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order63:retry",
        payload=validate_json_value(legal.to_payload()),
    )
    assert outcome.status_kind is not LifecycleStatusKind.INVALID
    replay = ReplayRunner(
        ReplayArtifact.capture(
            artifact_id="order63:retry",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        )
    ).run()
    assert replay.reproduced_exactly, replay


@pytest.mark.parametrize(("battle_round", "invalid"), [(2, True), (3, False)])
@pytest.mark.parametrize("player_id", ["player-a", "player-b"])
def test_inherited_enemy_deployment_zone_uses_owner_and_arrival_round(
    battle_round: int, invalid: bool, player_id: str
) -> None:
    from tests.order63_reserve_transport_helpers import placement

    from warhammer40k_core.core.deployment_zones import DeploymentZone
    from warhammer40k_core.engine.battlefield_state import (
        BattlefieldPlacementKind,
        BattlefieldScenario,
    )
    from warhammer40k_core.engine.ingress_placement_restrictions import (
        restrictions_for_arrival,
        validate_inherited_placement,
    )
    from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement

    session = reserve_transport_session()
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    # No enemy placements: this isolates zone ownership from the independent range rule.
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state.without_unit_placement(
            "army-beta:enemy-unit"
        ).without_unit_placement("army-alpha:remaining-unit"),
    )
    models = RulesUnitPlacement.single(placement(session, PASSENGER_ID, x=10, y=5)).geometry_models(
        scenario
    )
    if player_id == "player-b":
        from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
        from warhammer40k_core.geometry.pose import Pose

        army = state.army_definitions[1]
        unit = army.units[0]
        beta = UnitPlacement(
            army_id=army.army_id,
            player_id=army.player_id,
            unit_instance_id=unit.unit_instance_id,
            model_placements=tuple(
                ModelPlacement(
                    army_id=army.army_id,
                    player_id=army.player_id,
                    unit_instance_id=unit.unit_instance_id,
                    model_instance_id=model.model_instance_id,
                    pose=Pose.at(10 + i * 1.5, 5),
                )
                for i, model in enumerate(unit.own_models)
            ),
        )
        models = RulesUnitPlacement.single(beta).geometry_models(scenario)
    enemy = "player-b" if player_id == "player-a" else "player-a"
    zone = DeploymentZone.rectangle("enemy", enemy, min_x=0, min_y=0, max_x=60, max_y=6)
    policy = restrictions_for_arrival(
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        battle_round=battle_round,
        strategic_rule=None,
        deep_strike_enemy_distance=None,
        source_restrictions=(),
        distance_grants=(),
    )
    failures = validate_inherited_placement(
        restrictions=policy,
        scenario=scenario,
        models=models,
        player_id=player_id,
        enemy_deployment_zones=(zone,),
        deployment_zones=(zone,),
    )
    assert bool(failures) is invalid
    if invalid:
        assert set(failures) == {model.model_id for model in models}


def test_order63_source_bytes_and_partial_execution_status_are_honest() -> None:
    from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_reserve_transport_2026_09 as source,
    )

    raw = package_artifact_bytes(source.__name__, "artifacts/package.json")
    artifact = source.validate_source_artifact_bytes(raw)
    assert [rule.semantic_execution_status for rule in artifact.rules] == [
        "executable_engine_runtime",
        "partial_engine_runtime",
        "partial_engine_runtime",
    ]
    with pytest.raises(source.ReserveTransportSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(raw + b" ")
    assert source.RESERVE_TRANSPORT_POLICY.cargo_remains_embarked


def test_deep_strike_transport_passengers_use_carrier_placement_rules_without_own_ability() -> None:
    from tests.order63_reserve_transport_helpers import rapid_disembark

    from warhammer40k_core.engine.damage_allocation import unit_by_id
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.unit_abilities import unit_has_deep_strike

    session = reserve_transport_session(deep_strike=True)
    state = session.lifecycle.state
    assert state is not None
    assert not unit_has_deep_strike(unit_by_id(state=state, unit_instance_id=PASSENGER_ID))
    submit_ingress(session, deep_strike=True)
    outcome = rapid_disembark(session, y=15)
    assert outcome.status_kind is not LifecycleStatusKind.INVALID, outcome
    saved = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(saved).to_payload() == saved
