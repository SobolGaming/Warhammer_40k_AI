"""A fixed Charge witness across one native Dense terrain barrier."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from tests.phase15c_fight_order_helpers import fight_config, mustered_armies, unit_placement_at
from tests.setup_completion_helpers import (
    record_current_battlefield_placements_for_fixture,
    record_primary_turn_start_evidence_for_fixture,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.charge_flight_admission import (
    ChargeFlightUnresolved,
    ChargeFlightUnresolvedReason,
    ProvenChargeFlightAdvantage,
    ProvenChargeFlightChoice,
    choose_proven_charge_flight_mode,
    inspect_charge_flight_offer,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext
from warhammer40k_core.core.ruleset_descriptor import (
    MovementMode,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.movement_proposals import ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatusKind
from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_cavalcade_2026_11,
)

ACTOR = "player-a"
VIEWER = ViewerContext.for_player(ACTOR)
MOVER = "army-alpha:mover"
TARGET = "army-beta:target"
START = Pose.at(10, 20)


def _wall(
    *, height: float = 10.5, depth: float = 24, rotation: float = 0
) -> TerrainFeatureDefinition:
    footprint_width = 2 if rotation else 1
    footprint_depth = depth + 1 if rotation else depth
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=13.25,
        center_y_inches=20,
        width_inches=footprint_width,
        depth_inches=footprint_depth,
        display_template_id=None,
    )
    return TerrainFeatureDefinition(
        "charge-barrier",
        TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
        13.25,
        20,
        footprint_width,
        footprint_depth,
        display.footprint_polygon,
        display,
        walls=(TerrainWallDefinition("wall", 13.25, 20, 0, 1, depth, height, rotation),),
        classification=TerrainAreaClassification.DENSE,
    )


def _scenario(
    seed: int, *, wall: TerrainFeatureDefinition | None, target_x: float = 21
) -> tuple[LocalGameSession, PlayerDecisionContext, PathWitness]:
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
    assert config.mission_setup is not None
    config = replace(
        config,
        private_rng_seed=f"{seed:064x}",
        mission_setup=replace(
            config.mission_setup, terrain_features=() if wall is None else (wall,)
        ),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="pre-roll-charge-flight-fixture",
        ),
    )
    mission = config.mission_setup
    assert mission is not None
    armies = mustered_armies(config)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id=f"{game_id}-battlefield",
        armies=armies,
        battlefield_width_inches=mission.battlefield_width_inches,
        battlefield_depth_inches=mission.battlefield_depth_inches,
        terrain_features=mission.terrain_features,
    )
    board = scenario.battlefield_state
    state = GameState.from_config(config)
    for army, pose in zip(armies, (START, Pose.at(target_x, 20)), strict=True):
        state.record_army_definition(army)
        (unit,) = army.units
        board = board.with_unit_placement(
            unit_placement_at(unit, army_id=army.army_id, player_id=army.player_id, poses=(pose,))
        )
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=army.player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    state.record_battlefield_state(board)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    state.battle_round = 1
    state.active_player_id = ACTOR
    decisions = DecisionController()
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": {"frames": []},
        }
    )
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    context = _context(session)
    offer = inspect_charge_flight_offer(context, unit_id=MOVER, target_id=TARGET).offer
    assert offer is not None
    end = Pose.at(START.position.x + offer.target_filter_distance_inches, 20)
    return session, context, PathWitness.for_paths(((offer.model_id, (START, end)),))


def _context(session: LocalGameSession) -> PlayerDecisionContext:
    return PlayerDecisionContext.from_view(session.view_for_context(viewer=VIEWER), choice_seed=0)


def _submit_fixed_target_and_path(session: LocalGameSession, witness: PathWitness) -> None:
    request = _context(session).request
    assert request["decision_type"] == "select_charge_targets"
    (option,) = [
        row
        for row in request["options"]
        if isinstance(row["payload"], dict) and row["payload"].get("target_ids") == [TARGET]
    ]
    session.submit_viewer_option(
        viewer=VIEWER,
        request_id=request["request_id"],
        option_id=option["option_id"],
        result_id="barrier:fixed-target",
    )
    request = _context(session).request
    proposal = ChargeMoveProposal(
        proposal_request_id=request["request_id"],
        proposal_kind=ProposalKind.CHARGE_MOVE,
        unit_instance_id=MOVER,
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=(TARGET,),
        witness=witness,
    )
    status = session.submit_viewer_parameterized_payload(
        viewer=VIEWER,
        request_id=request["request_id"],
        payload=cast(JsonValue, proposal.to_payload()),
        result_id="barrier:fixed-path",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status


def test_dense_wall_native_flight_advantage_replays() -> None:
    session, context, witness = _scenario(12, wall=_wall())
    other, other_context, other_witness = _scenario(2, wall=_wall())
    original = session.to_persistence_payload()
    assert original != other.to_persistence_payload()
    assert context == other_context
    assert witness == other_witness
    baseline = session.lifecycle.decision_controller.event_log.records
    assert not any(event.event_type == "dice_rolled" for event in baseline)
    assert "private_rng_seed" not in context.observation_json

    proof = choose_proven_charge_flight_mode(
        session, context, unit_id=MOVER, target_id=TARGET, witness=witness
    )
    assert isinstance(proof, ProvenChargeFlightAdvantage), proof
    assert proof == choose_proven_charge_flight_mode(
        other, other_context, unit_id=MOVER, target_id=TARGET, witness=other_witness
    )
    assert proof.offer.flight_penalty_inches == 2
    assert proof.ground_upper_bound.rolls == (11, 12)
    assert proof.ground_upper_bound.ordered_outcomes == 3
    assert proof.flight_lower_bound.rolls == (9, 10, 11, 12)
    assert proof.flight_lower_bound.ordered_outcomes == 10
    assert proof.action == context.select_option(proof.offer.flight_option_id)
    assert session.to_persistence_payload() == original

    assert proof.action.option_id is not None
    session.submit_viewer_option(
        viewer=VIEWER,
        request_id=proof.action.request_id,
        option_id=proof.action.option_id,
        result_id="barrier:flight-mode",
    )
    records = session.lifecycle.decision_controller
    tail = records.event_log.records[len(baseline) :]
    kinds = [event.event_type for event in tail]
    assert kinds.index("charging_unit_selected") < kinds.index("dice_rolled")
    assert kinds.count("dice_rolled") == 1
    (rolled,) = [event.payload for event in tail if event.event_type == "charge_roll_resolved"]
    assert isinstance(rolled, dict)
    roll_result = rolled["roll_result"]
    assert isinstance(roll_result, dict)
    assert roll_result["value"] == 10
    assert rolled["maximum_distance_inches"] == 8
    assert 10 not in proof.ground_upper_bound.rolls
    (declared,) = [
        record
        for record in records.records
        if record.request.decision_type == "select_charging_unit"
    ]
    assert isinstance(declared.result.payload, dict)
    assert declared.result.payload["take_to_the_skies"] is True
    _submit_fixed_target_and_path(session, witness)
    assert any(event.event_type == "charge_move_completed" for event in records.event_log.records)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="barrier:charge")).run()
    assert replay.reproduced_exactly, replay.to_payload()
    stale = choose_proven_charge_flight_mode(
        session, context, unit_id=MOVER, target_id=TARGET, witness=witness
    )
    assert isinstance(stale, ChargeFlightUnresolved)
    assert stale.reason is ChargeFlightUnresolvedReason.OBSERVATION_DRIFT


def test_barrier_flight_preserves_open_board_ground_choice() -> None:
    session, context, witness = _scenario(3, wall=None)
    result = choose_proven_charge_flight_mode(
        session, context, unit_id=MOVER, target_id=TARGET, witness=witness
    )
    assert isinstance(result, ProvenChargeFlightChoice), result
    assert result.action == context.select_option(result.offer.ground_option_id)
    assert result.ground.successful_outcomes == 21
    assert result.flight.successful_outcomes == 10


@pytest.mark.parametrize(
    "case", ["low", "short", "rotated", "uncertified-endpoints", "bad-witness"]
)
def test_wall_charge_abstains_without_a_separated_bound(case: str) -> None:
    feature = {
        "low": _wall(height=8.5),
        "short": _wall(depth=8),
        "rotated": _wall(rotation=1),
        "uncertified-endpoints": _wall(),
        "bad-witness": _wall(),
    }[case]
    session, context, witness = _scenario(
        3, wall=feature, target_x=19 if case == "uncertified-endpoints" else 21
    )
    if case == "bad-witness":
        witness = PathWitness.for_paths(((witness.model_ids()[0], (START, Pose.at(8, 20))),))
    before = session.to_persistence_payload()
    result = choose_proven_charge_flight_mode(
        session, context, unit_id=MOVER, target_id=TARGET, witness=witness
    )
    assert isinstance(result, ChargeFlightUnresolved), result
    assert result.reason is (
        ChargeFlightUnresolvedReason.UNSUPPORTED_PROOF_CONTEXT
        if case in {"rotated", "uncertified-endpoints"}
        else ChargeFlightUnresolvedReason.BOUNDS_OVERLAP
    )
    assert result.offer is not None
    assert session.to_persistence_payload() == before
