from __future__ import annotations

import json
import multiprocessing
from dataclasses import replace

import pytest

from tests.charge_distance_helpers import add_modifier, select_source, select_targets
from tests.phase15a_charge_declaration_helpers import (
    charge_config,
    compact_test_unit_poses,
    mustered_armies,
    unit_placement_at,
)
from tests.setup_completion_helpers import (
    ensure_army_mustered_events_for_fixture,
    record_completed_command_occurrences_for_fixture,
    record_current_battlefield_placements_for_fixture,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.ground_charge_candidates import (
    ChargeSearchStop,
    GroundChargeExhaustedError,
    generate_ground_charge_candidates,
)
from warhammer40k_core.ai.ground_charge_policy import prepare_ground_charge_policy
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError, payload_digest
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatusKind
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.geometry.pose import Pose

ACTOR = "player-a"
TARGET = "army-beta:enemy"


@pytest.fixture
def selected_ground_charge() -> LocalGameSession:
    config = charge_config(
        game_id="six-ground-charge",
        alpha_unit_ids=("source",),
        enemy_unit_ids=("enemy",),
    )
    alpha, beta = config.army_muster_requests
    (source,) = alpha.unit_selections
    (profile,) = source.model_profile_selections
    leader = config.army_catalog.datasheet_by_id("core-character-leader")
    (enemy,) = beta.unit_selections
    config = replace(
        config,
        army_muster_requests=(
            replace(
                alpha,
                unit_selections=(
                    replace(source, model_profile_selections=(replace(profile, model_count=6),)),
                ),
            ),
            replace(
                beta,
                unit_selections=(
                    replace(
                        enemy,
                        datasheet_id=leader.datasheet_id,
                        model_profile_selections=(
                            replace(
                                profile, model_profile_id="core-character-leader", model_count=1
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    mission = config.mission_setup
    assert mission is not None
    config = replace(
        config,
        ruleset_descriptor=runtime_ruleset_descriptor_for_mission_setup(
            mission, rules_overlay_ids=config.ruleset_descriptor.rules_overlay_ids
        ),
    )
    armies = mustered_armies(config)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="six-ground-charge",
        armies=armies,
        battlefield_width_inches=mission.battlefield_width_inches,
        battlefield_depth_inches=mission.battlefield_depth_inches,
    )
    battlefield = scenario.battlefield_state
    state = GameState.from_config(config)
    poses = (compact_test_unit_poses(origin=Pose.at(10, 20), model_count=6), (Pose.at(13, 25),))
    for army, placement_poses in zip(armies, poses, strict=True):
        state.record_army_definition(army)
        (unit,) = army.units
        battlefield = battlefield.with_unit_placement(
            unit_placement_at(
                unit,
                army_id=army.army_id,
                player_id=army.player_id,
                poses=placement_poses,
            )
        )
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=army.player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    state.record_battlefield_state(battlefield)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    state.battle_round = 1
    state.active_player_id = ACTOR
    decisions = GameLifecycle().decision_controller
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_completed_command_occurrences_for_fixture(state, decisions=decisions, config=config)
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": {"frames": []},
        }
    )
    assert lifecycle.state is not None
    add_modifier(lifecycle.state, effect_id="fixture", kind="modify_dice_roll", delta=10)
    session = LocalGameSession(lifecycle)
    request = select_targets(session, select_source(session), (TARGET,))
    assert request.decision_type == "submit_movement_proposal"
    return session


def test_ground_charge_generation_is_stable_and_limits_are_typed(
    selected_ground_charge: LocalGameSession,
) -> None:
    view = selected_ground_charge.view(viewer_player_id=ACTOR)
    context = PlayerDecisionContext.from_view(view, choice_seed=1)
    alternate = PlayerDecisionContext.from_view(view, choice_seed=5)
    generated = generate_ground_charge_candidates(context, raw_limit=4)
    assert generated == generate_ground_charge_candidates(alternate, raw_limit=4)
    assert generated.stop is ChargeSearchStop.RAW_LIMIT
    assert len(generated.candidates) == 4
    assert len({candidate.candidate_id for candidate in generated.candidates}) == 4
    assert any(candidate.waypoint_count for candidate in generated.candidates)
    with pytest.raises(GroundChargeExhaustedError) as caught:
        generate_ground_charge_candidates(context, geometry_limit=1)
    assert caught.value.reason is ChargeSearchStop.GEOMETRY_LIMIT
    assert caught.value.counts.geometry_work == 1
    assert caught.value.counts.raw == 0


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="Native ground charge preparation requires a fork-capable host.",
)
def test_ground_charge_ranks_only_native_accepts_and_checks_binding(
    selected_ground_charge: LocalGameSession,
) -> None:
    session = selected_ground_charge
    view = session.view(viewer_player_id=ACTOR)
    context = PlayerDecisionContext.from_view(view, choice_seed=0)
    before = payload_digest(session.lifecycle.to_payload())
    prepared = prepare_ground_charge_policy(session, context, raw_limit=4, accepted_limit=2)
    assert payload_digest(session.lifecycle.to_payload()) == before
    assert prepared.counts.accepted == 2
    assert prepared.counts.timed_out == 0
    assert set(prepared.ranked_accepted_ids) == {
        receipt.candidate_id
        for receipt in prepared.validations
        if receipt.status not in (LifecycleStatusKind.INVALID, None)
    }
    action = prepared.registration.policy.choose(context)
    assert action.proposal_json is not None
    status = session.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(ACTOR),
        request_id=action.request_id,
        payload=json.loads(action.proposal_json),
        result_id="validated-charge",
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    completed = [
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "charge_move_completed"
    ]
    assert len(completed) == 1
    view["projection_state_hash"] = "a" * 64
    stale = PlayerDecisionContext.from_view(view, choice_seed=0)
    with pytest.raises(PolicyError, match="stale"):
        prepared.registration.policy.choose(stale)
