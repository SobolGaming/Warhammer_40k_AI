from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from tests.phase13b_shooting_declaration_helpers import _shooting_lifecycle
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.canonical_deployment import canonical_deployment_config
from warhammer40k_core.ai.followthrough_scenario import (
    FOLLOWTHROUGH_DEFINITION_HASH,
    reproduce_followthrough_pair,
)
from warhammer40k_core.ai.normal_shooting_policy import (
    NormalShootingGap,
    NormalShootingGapReason,
    generate_normal_shooting_candidates,
    normal_shooting_registration,
    rank_normal_shooting_candidates,
)
from warhammer40k_core.ai.opposing_shooter_scenario import OpposingShooterQualification
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyRouter, payload_digest
from warhammer40k_core.ai.preserve_scenario import EXPLOITER_UNIT_ID, OPPONENT_UNIT_ID
from warhammer40k_core.ai.training_admission import TrainingAdmissionError
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifactPayload, ReplayRunner
from warhammer40k_core.geometry.pose import Pose


def test_exact_pair_shooter_diagnostics_and_ordinary_opposing_attack_replay() -> None:
    stationary, moved = reproduce_followthrough_pair()
    before = [canonical_json(session.to_persistence_payload()) for session in (stationary, moved)]
    report = OpposingShooterQualification.from_sessions(stationary, moved)
    payload = report.to_payload()
    assert json.loads(canonical_json(payload)) == payload
    assert payload_digest(payload) == report.content_hash
    definition = cast(dict[str, JsonValue], payload["definition"])
    assert definition["historical_followthrough_definition_hash"] == FOLLOWTHROUGH_DEFINITION_HASH
    assert definition["attack_branch"] == "stationary-only"
    endpoints = cast(dict[str, dict[str, JsonValue]], payload["endpoints"])
    for name, count in (("stationary", 22), ("normal_move", 23)):
        diagnostic = endpoints[name]
        assert diagnostic["accepted_record_count"] == count
        assert diagnostic["shooter_unit_instance_id"] == OPPONENT_UNIT_ID
        assert diagnostic["shooter_ineligibility_reason"] is None
        equipment = cast(list[dict[str, JsonValue]], diagnostic["equipped_models"])
        assert len(equipment) == 5
        for model in equipment:
            wargear = cast(dict[str, JsonValue], model["wargear"])
            assert wargear["wargear_id"] == "core-bolt-rifle"
            profiles = cast(list[dict[str, JsonValue]], wargear["weapon_profiles"])
            assert len(profiles) == 1
            assert profiles[0]["range_profile"] == {"kind": "distance", "distance_inches": 24}
            assert profiles[0]["attack_profile"] == {"fixed_attacks": 2, "dice_expression": None}
        targets = cast(list[dict[str, JsonValue]], diagnostic["targets"])
        assert len(targets) == 3
        assert all(row["within_equipped_24_inch_range"] is False for row in targets)
        assert [row["independently_visible"] for row in targets] == [True, False, False]
        assert targets[0]["target_unit_instance_id"] == EXPLOITER_UNIT_ID
        candidates = cast(list[dict[str, JsonValue]], diagnostic["per_model_candidates"])
        assert len(candidates) == 15
        for row in candidates:
            candidate = cast(dict[str, JsonValue], row["candidate"])
            assert candidate["is_legal"] is False
            assert candidate["violation_code"] == "out_of_range"
            # The ordinary target query short-circuits range. This is not a
            # negative visibility result: the separate E query above is true.
            assert candidate["line_of_sight_witness"] is None
    trace = cast(list[dict[str, JsonValue]], payload["attack_trace"])
    routes = [cast(dict[str, JsonValue], row["route"]) for row in trace]
    assert len(trace) == 41
    records = [
        record
        for row in trace
        for record in cast(list[dict[str, JsonValue]], row["accepted_records"])
    ]
    assert len(records) == 43
    origin = cast(dict[str, JsonValue], payload["attack_origin"])
    assert origin["prefix_record_count"] == 65
    assert sum(route["decision_type"] == "submit_movement_proposal" for route in routes) == 3
    assert sum(route["decision_type"] == "submit_shooting_declaration" for route in routes) == 1
    assert [route["actor_id"] for route in routes if route["decision_type"] == "use_stratagem"] == [
        "player-b",
        "player-b",
        "player-b",
        "player-b",
        "player-a",
    ]
    assert routes[-1]["decision_type"] == "select_damage_allocation_model"
    assert routes[-1]["actor_id"] == "player-a"
    assert trace[-1]["selected_option_id"] == EXPLOITER_UNIT_ID + ":core-deep-strike-model:001"
    declaration_row = next(
        row
        for row in trace
        if cast(dict[str, JsonValue], row["route"])["decision_type"]
        == "submit_shooting_declaration"
    )
    automatic_records = cast(list[dict[str, JsonValue]], declaration_row["accepted_records"])
    assert [
        cast(dict[str, JsonValue], record["request"])["decision_type"]
        for record in automatic_records
    ] == [
        "submit_shooting_declaration",
        "select_resolve_target_unit",
        "select_attack_weapon_group",
    ]
    declarations = [
        cast(dict[str, JsonValue], row["submitted_payload"])
        for row in trace
        if cast(dict[str, JsonValue], row["route"])["decision_type"]
        == "submit_shooting_declaration"
    ]
    weapons = cast(list[dict[str, JsonValue]], declarations[0]["declarations"])
    assert len(weapons) == 1
    assert (
        weapons[0]["attacker_model_instance_id"] == OPPONENT_UNIT_ID + ":core-intercessor-like:003"
    )
    assert weapons[0]["target_unit_instance_id"] == EXPLOITER_UNIT_ID
    assert declarations[0]["battle_round"] == 3
    events = cast(list[dict[str, JsonValue]], payload["attack_events"])
    assert sum(event["event_type"] == "attack_sequence_completed" for event in events) == 1
    completed = next(
        event for event in events if event["event_type"] == "attack_sequence_completed"
    )
    completed_payload = cast(dict[str, JsonValue], completed["payload"])
    assert completed_payload["attacker_player_id"] == "player-b"
    assert completed_payload["attacking_unit_instance_id"] == OPPONENT_UNIT_ID
    assert any(event["event_type"] == "attack_sequence_step" for event in events)
    assert (
        ReplayRunner.from_payload(cast(ReplayArtifactPayload, payload["attack_replay_artifact"]))
        .run()
        .reproduced_exactly
    )
    assert before == [
        canonical_json(session.to_persistence_payload()) for session in (stationary, moved)
    ]
    for session in (stationary, moved):
        for player in ("player-a", "player-b"):
            view_json = canonical_json(session.view(viewer_player_id=player))
            assert "opposing-shooter-qualification" not in view_json
        context = PlayerDecisionContext.from_view(
            session.view(viewer_player_id="player-b"), choice_seed=7
        )
        assert context.route.decision_type == "submit_stratagem_target_proposal"
    assert payload["eligible_for_learning"] is False
    assert payload["reference_target"] is None
    assert payload["useful_reference_status"] == "scoped_gap"
    assert "matched-opponent-response-and-exploiter-benefit" in cast(
        list[str], payload["remaining_tactical_gaps"]
    )
    payload["eligible_for_learning"] = True
    assert report.to_payload()["eligible_for_learning"] is False


def test_opposing_qualification_rejects_unreached_and_wrong_configuration() -> None:
    with pytest.raises(TrainingAdmissionError, match="exact ordinary sessions"):
        OpposingShooterQualification()
    fresh = LocalGameSession()
    fresh.start(canonical_deployment_config())
    other = LocalGameSession()
    other.start(replace(canonical_deployment_config(), game_id="outside-opposing-shooter"))
    with pytest.raises(TrainingAdmissionError, match="configuration drifted"):
        OpposingShooterQualification.from_sessions(other, fresh)
    with pytest.raises(TrainingAdmissionError, match="22/23-record endpoints"):
        OpposingShooterQualification.from_sessions(fresh, fresh)


@pytest.mark.parametrize("fire", [False, True])
def test_normal_shooting_policy_uses_the_projected_offer_and_native_submission(fire: bool) -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("exploiter",),
        alpha_unit_specs=(("exploiter", "core-deep-strike-unit", "core-deep-strike-model", 3),),
        enemy_pose=Pose.at(23.0, 35.0),
    )
    session = LocalGameSession(lifecycle=lifecycle)
    viewer = ViewerContext.for_player("player-a")
    session.advance_until_decision_or_terminal()
    unit_context = PlayerDecisionContext.from_view(
        session.view_for_context(viewer=viewer), choice_seed=1
    )
    with pytest.raises(NormalShootingGap) as gap:
        generate_normal_shooting_candidates(unit_context)
    assert gap.value.reason is NormalShootingGapReason.NO_ORDINARY_DECLARATION
    assert (
        session.submit_viewer_option(
            viewer=viewer,
            request_id=unit_context.request["request_id"],
            result_id="normal-focus-select-unit",
            option_id=units["exploiter"].unit_instance_id,
        ).status_kind
        is LifecycleStatusKind.WAITING_FOR_DECISION
    )

    type_context = PlayerDecisionContext.from_view(
        session.view_for_context(viewer=viewer), choice_seed=1
    )
    normal = next(
        option
        for option in type_context.request["options"]
        if isinstance(option["payload"], dict) and option["payload"]["shooting_type"] == "normal"
    )
    assert (
        session.submit_viewer_option(
            viewer=viewer,
            request_id=type_context.request["request_id"],
            result_id="normal-focus-select-type",
            option_id=normal["option_id"],
        ).status_kind
        is LifecycleStatusKind.WAITING_FOR_DECISION
    )

    before = session.view_for_context(viewer=viewer)
    context = PlayerDecisionContext.from_view(before, choice_seed=1)
    candidates = generate_normal_shooting_candidates(context)
    ranked = rank_normal_shooting_candidates(candidates)
    assert ranked == rank_normal_shooting_candidates(tuple(reversed(candidates)))
    assert [
        (candidate.target_unit_instance_id, candidate.declaration_count) for candidate in ranked
    ] == [
        (units["enemy"].unit_instance_id, 3),
        (None, 0),
    ]
    assert len({candidate.candidate_id for candidate in ranked}) == 2
    router = PolicyRouter((normal_shooting_registration("player-a"),))
    ranked_action = router.resolve(context.route).policy.choose(context)
    assert ranked_action == ranked[0].action
    assert session.view_for_context(viewer=viewer) == before
    action = ranked_action if fire else ranked[-1].action
    assert action.proposal_json is not None
    status = session.submit_viewer_parameterized_payload(
        viewer=viewer,
        request_id=action.request_id,
        result_id="normal-focus-declaration",
        payload=json.loads(action.proposal_json),
    )
    assert status.status_kind in (
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
    )
    accepted = [
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "shooting_declaration_accepted"
    ]
    (event,) = accepted
    assert isinstance(event.payload, dict)
    pools = event.payload["attack_pools"]
    assert isinstance(pools, list)
    assert len(pools) == (3 if fire else 0)
