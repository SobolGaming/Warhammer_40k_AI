"""Pre-roll Charge flight admission stays detached from native chance and replay."""

from __future__ import annotations

from dataclasses import replace
from itertools import product
from math import isclose

import pytest

from tests.charge_distance_helpers import add_modifier
from tests.phase15c_fight_order_helpers import fight_config, fight_lifecycle
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.charge_flight_admission import (
    ChargeFlightOffer,
    ChargeFlightUnresolved,
    ChargeFlightUnresolvedReason,
    ProvenChargeFlightChoice,
    choose_proven_charge_flight_mode,
    inspect_charge_flight_offer,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.charge_declaration import ChargeRollRequest
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_cavalcade_2026_11,
)

ACTOR = "player-a"
VIEWER = ViewerContext.for_player(ACTOR)
MOVER = "army-alpha:mover"
TARGET = "army-beta:target"


def _fixture(private_seed: int, *, target_x: float = 18) -> LocalGameSession:
    game_id = "pre-roll-charge-flight"
    package = chaos_daemons_cavalcade_2026_11.catalog_package()
    config = fight_config(
        game_id=game_id,
        alpha_unit_ids=("mover",),
        enemy_unit_ids=("target",),
        datasheet_id="000002582",
        model_profile_id="000002582:bloodthirster",
        model_count=1,
        alpha_faction_id="chaos-daemons",
        enemy_faction_id="chaos-daemons",
        alpha_detachment_ids=("cavalcade-of-chaos", "shadow-legion"),
        enemy_detachment_ids=("cavalcade-of-chaos", "shadow-legion"),
        catalog=package.army_catalog,
    )
    config = replace(
        config,
        private_rng_seed=f"{private_seed:064x}",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="pre-roll-charge-flight-fixture",
        ),
    )
    lifecycle, _ = fight_lifecycle(
        game_id=game_id,
        alpha_unit_ids=("mover",),
        enemy_unit_ids=("target",),
        origins={"mover": Pose.at(10, 20), "target": Pose.at(target_x, 20)},
        battle_phase=BattlePhase.CHARGE,
        config=config,
        record_deployment=True,
    )
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    return session


def _context(session: LocalGameSession) -> PlayerDecisionContext:
    return PlayerDecisionContext.from_view(session.view_for_context(viewer=VIEWER), choice_seed=0)


def _admit(context: PlayerDecisionContext) -> ChargeFlightOffer:
    result = inspect_charge_flight_offer(context, unit_id=MOVER, target_id=TARGET)
    assert result.reason is ChargeFlightUnresolvedReason.MINIMUM_ROLL_UNPROVEN
    assert result.offer is not None
    return result.offer


def test_charge_flight_admits_native_offer_without_claiming_a_minimum() -> None:
    session = _fixture(2)
    counterpart = _fixture(3)
    context = _context(session)
    original = session.to_persistence_payload()
    assert original != counterpart.to_persistence_payload()
    assert _context(counterpart) == context
    assert "private_rng_seed" not in context.observation_json
    assert "charge_roll_state" not in context.observation_json
    assert "movement_budget" not in context.observation_json
    offer = _admit(context)
    assert _admit(_context(counterpart)) == offer
    assert offer.request_id == context.request["request_id"]
    assert offer.observation_hash == context.observation_hash
    assert (offer.unit_id, offer.target_id) == (MOVER, TARGET)
    assert offer.flight_penalty_inches == 2
    assert offer.target_filter_distance_inches > 0
    assert (
        inspect_charge_flight_offer(context, unit_id=MOVER, target_id=MOVER).reason
        is ChargeFlightUnresolvedReason.UNADMITTED_TARGET
    )
    assert (
        inspect_charge_flight_offer(context, unit_id=TARGET, target_id=MOVER).reason
        is ChargeFlightUnresolvedReason.UNSUPPORTED_MOVER
    )
    assert session.to_persistence_payload() == original
    baseline = session.lifecycle.decision_controller.event_log.records
    assert not any(event.event_type == "dice_rolled" for event in baseline)

    for flies, option_id in ((False, offer.ground_option_id), (True, offer.flight_option_id)):
        arm = session.fork()
        assert arm.to_persistence_payload() == original
        assert _context(arm) == context
        # This is an explicit test control, not a decision made by admission.
        arm.submit_viewer_option(
            viewer=VIEWER,
            request_id=offer.request_id,
            option_id=option_id,
            result_id="fixture:charge-mode",
        )
        decisions = arm.lifecycle.decision_controller
        tail = decisions.event_log.records[len(baseline) :]
        kinds = [event.event_type for event in tail]
        assert kinds.index("charging_unit_selected") < kinds.index("dice_rolled")
        assert kinds.index("dice_rolled") < kinds.index("charge_roll_started")
        (rolled,) = [event for event in tail if event.event_type == "charge_roll_started"]
        payload = rolled.payload
        assert isinstance(payload, dict)
        roll_request = payload["charge_roll_request"]
        assert isinstance(roll_request, dict)
        assert roll_request["take_to_the_skies"] is flies
        assert roll_request["roll_modifiers"] == []
        (record,) = [
            item
            for item in decisions.records
            if item.request.decision_type == "select_charging_unit"
        ]
        assert roll_request["source_decision_request_id"] == record.request.request_id
        assert roll_request["source_decision_result_id"] == record.result.result_id
        roll_state = payload["charge_roll_state"]
        assert isinstance(roll_state, dict)
        assert roll_state["rerolls"] == []
        assert kinds.count("dice_rolled") == 1
        (resolved,) = [
            event.payload for event in tail if event.event_type == "charge_roll_resolved"
        ]
        assert isinstance(resolved, dict)
        roll_result = resolved["roll_result"]
        assert isinstance(roll_result, dict)
        value = roll_result["value"]
        assert isinstance(value, int)
        penalty = offer.flight_penalty_inches if flies else 0
        assert resolved["maximum_distance_inches"] == max(0, value - penalty)
        # This native negative has a failed ground roll and an offered flight target.
        # Realized rolls on the two arms cannot settle the earlier mode choice.
        assert resolved["charge_move_available"] is flies
        post_roll_view = arm.view_for_context(viewer=VIEWER)
        pending = post_roll_view["pending_decision"]
        if pending is not None and pending["actor_id"] == ACTOR:
            assert (
                inspect_charge_flight_offer(_context(arm), unit_id=MOVER, target_id=TARGET).reason
                is ChargeFlightUnresolvedReason.NOT_ORDINARY_CHARGE_OFFER
            )
        else:
            assert post_roll_view["active_player_id"] != ACTOR
        replay = ReplayRunner.from_payload(arm.replay_artifact(artifact_id="charge-flight")).run()
        assert replay.reproduced_exactly, replay.to_payload()
    assert session.to_persistence_payload() == original

    # The proof shares the ordinary prefix with the original native fork controls.
    # The supplied destination is evidence only; the policy returns a finite choice.
    start = Pose.at(10, 20)
    terminal = Pose.at(10 + offer.target_filter_distance_inches, 20)
    witness = PathWitness.for_paths(((offer.model_id, (start, terminal)),))
    assert isclose(offer.target_filter_distance_inches, 3.2755905511811036, abs_tol=1e-9)
    proof = choose_proven_charge_flight_mode(
        session, context, unit_id=MOVER, target_id=TARGET, witness=witness
    )
    assert isinstance(proof, ProvenChargeFlightChoice), proof
    assert proof.offer == offer
    assert proof.action == context.select_option(offer.ground_option_id)
    assert proof.ground.minimum_roll == 4
    assert proof.ground.successful_rolls == tuple(range(4, 13))
    assert proof.ground.successful_outcomes == 33
    assert proof.flight.minimum_roll == 6
    assert proof.flight.successful_rolls == tuple(range(6, 13))
    assert proof.flight.successful_outcomes == 26
    assert session.to_persistence_payload() == original
    assert not any(event.event_type == "dice_rolled" for event in baseline)

    different = _fixture(2, target_x=19)
    different_context = _context(different)
    different_offer = _admit(different_context)
    different_witness = PathWitness.for_paths(
        (
            (
                different_offer.model_id,
                (start, Pose.at(10 + different_offer.target_filter_distance_inches, 20)),
            ),
        )
    )
    stale = choose_proven_charge_flight_mode(
        different, context, unit_id=MOVER, target_id=TARGET, witness=witness
    )
    assert isinstance(stale, ChargeFlightUnresolved)
    assert stale.reason is ChargeFlightUnresolvedReason.OBSERVATION_DRIFT
    changed = choose_proven_charge_flight_mode(
        different, different_context, unit_id=MOVER, target_id=TARGET, witness=different_witness
    )
    assert isinstance(changed, ProvenChargeFlightChoice), changed
    assert (changed.ground.minimum_roll, changed.ground.successful_outcomes) == (5, 30)
    assert (changed.flight.minimum_roll, changed.flight.successful_outcomes) == (7, 21)

    wrong_witness = PathWitness.for_paths(((offer.model_id, (start, Pose.at(9, 20))),))
    unsupported = choose_proven_charge_flight_mode(
        session, context, unit_id=MOVER, target_id=TARGET, witness=wrong_witness
    )
    assert isinstance(unsupported, ChargeFlightUnresolved)
    assert unsupported.reason is ChargeFlightUnresolvedReason.MINIMUM_ROLL_UNPROVEN
    modified = session.fork()
    assert modified.lifecycle.state is not None
    add_modifier(
        modified.lifecycle.state,
        effect_id="proof:modifier",
        kind="modify_dice_roll",
        delta=1,
        unit_instance_id=MOVER,
    )
    excluded = choose_proven_charge_flight_mode(
        modified, _context(modified), unit_id=MOVER, target_id=TARGET, witness=witness
    )
    assert isinstance(excluded, ChargeFlightUnresolved)
    assert excluded.reason is ChargeFlightUnresolvedReason.UNSUPPORTED_PROOF_CONTEXT

    policy_arm = session.fork()
    # Qualify on the actual submission session, not a certificate from another session.
    chosen = choose_proven_charge_flight_mode(
        policy_arm, _context(policy_arm), unit_id=MOVER, target_id=TARGET, witness=witness
    )
    assert isinstance(chosen, ProvenChargeFlightChoice), chosen
    assert chosen == proof
    assert policy_arm.to_persistence_payload() == original
    assert chosen.action.option_id is not None
    policy_arm.submit_viewer_option(
        viewer=VIEWER,
        request_id=chosen.action.request_id,
        option_id=chosen.action.option_id,
        result_id="fixture:policy-charge-mode",
    )
    journal = policy_arm.lifecycle.decision_controller
    first = journal.event_log.records[len(baseline) :]
    kinds = [event.event_type for event in first]
    assert kinds.index("charging_unit_selected") < kinds.index("dice_rolled")
    (declared,) = [
        record
        for record in journal.records
        if record.request.decision_type == "select_charging_unit"
    ]
    after_roll = choose_proven_charge_flight_mode(
        policy_arm, context, unit_id=MOVER, target_id=TARGET, witness=witness
    )
    assert isinstance(after_roll, ChargeFlightUnresolved)
    assert after_roll.reason is ChargeFlightUnresolvedReason.OBSERVATION_DRIFT
    committed = declared.result.payload
    assert isinstance(committed, dict)
    assert committed["take_to_the_skies"] is False
    replay = ReplayRunner.from_payload(
        policy_arm.replay_artifact(artifact_id="charge-flight-policy")
    ).run()
    assert replay.reproduced_exactly, replay.to_payload()
    assert session.to_persistence_payload() == original


@pytest.mark.parametrize(
    ("ground_cost", "flight_cost", "expected"),
    [(7, 7, (21, 10)), (10, 6, (6, 15)), (9, 7, (10, 10))],
)
def test_unmodified_charge_probability_synthetic_controls(
    ground_cost: int, flight_cost: int, expected: tuple[int, int]
) -> None:
    # These costs are stipulated exact minima, never evidence about the native fixture.
    request = ChargeRollRequest(
        request_id="fixture:roll",
        game_id="fixture",
        battle_round=1,
        player_id=ACTOR,
        unit_instance_id=MOVER,
        source_decision_request_id="fixture:request",
        source_decision_result_id="fixture:result",
    )
    expression = request.spec.expression
    assert expression.quantity == 2
    assert expression.sides == 6
    faces = range(1, expression.sides + 1)
    pairs = tuple(product(faces, repeat=expression.quantity))
    assert len(pairs) == 36
    assert (
        sum(sum(pair) >= ground_cost for pair in pairs),
        sum(sum(pair) - 2 >= flight_cost for pair in pairs),
    ) == expected
