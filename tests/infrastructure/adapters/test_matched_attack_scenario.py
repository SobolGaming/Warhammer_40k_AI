from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.canonical_deployment import canonical_deployment_config
from warhammer40k_core.ai.followthrough_scenario import reproduce_followthrough_pair
from warhammer40k_core.ai.matched_attack_scenario import (
    MatchedAttackComparison,
    matched_attack_definition,
)
from warhammer40k_core.ai.opposing_shooter_scenario import opposing_shooter_definition
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, payload_digest
from warhammer40k_core.ai.preserve_scenario import EXPLOITER_UNIT_ID, OPPONENT_UNIT_ID
from warhammer40k_core.ai.training_admission import TrainingAdmissionError
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.replay import ReplayArtifactPayload, ReplayRunner


@pytest.fixture(scope="module")
def comparison() -> tuple[LocalGameSession, LocalGameSession, MatchedAttackComparison]:
    stationary, moved = reproduce_followthrough_pair()
    before = [canonical_json(item.to_persistence_payload()) for item in (stationary, moved)]
    report = MatchedAttackComparison.from_sessions(stationary, moved)
    assert before == [canonical_json(item.to_persistence_payload()) for item in (stationary, moved)]
    return stationary, moved, report


def test_both_ordinary_attacks_have_matched_timing_cooperation_and_local_outcomes(
    comparison: tuple[LocalGameSession, LocalGameSession, MatchedAttackComparison],
) -> None:
    payload = comparison[2].to_payload()
    assert payload["definition_hash"] == payload_digest(matched_attack_definition())
    branches = cast(dict[str, dict[str, JsonValue]], payload["branches"])
    for name, count in (("stationary", 65), ("normal_move", 66)):
        branch = branches[name]
        assert cast(dict[str, JsonValue], branch["origin"])["prefix_record_count"] == count
        attack_boundary = cast(dict[str, JsonValue], branch["attack_boundary"])
        assert attack_boundary["battle_round"] == 3
        assert attack_boundary["active_player_id"] == "player-b"
        assert cast(dict[str, JsonValue], attack_boundary["route"])["decision_type"] == (
            "submit_shooting_declaration"
        )
        horizon = cast(dict[str, JsonValue], branch["horizon"])
        assert horizon["battle_round"] == 4
        assert horizon["active_player_id"] == "player-a"
        route = cast(dict[str, JsonValue], horizon["route"])
        assert (route["actor_id"], route["battle_phase"], route["decision_type"]) == (
            "player-a",
            "movement",
            "select_movement_unit",
        )
        choices = cast(list[dict[str, JsonValue]], branch["controlled_choices"])
        assert len(choices) == 41
        assert sum(row["option_id"] == "remain_stationary" for row in choices) == 6
        assert sum(row["option_id"] == "complete_shooting_phase" for row in choices) == 5
        assert sum(row["option_id"] == "decline_stratagem_window" for row in choices) == 5
        assert (
            sum(
                row["proposal"] == {"submission_kind": "decline_stratagem_window"}
                for row in choices
            )
            == 6
        )
        moves = [
            cast(dict[str, JsonValue], row["proposal"])
            for row in choices
            if cast(dict[str, JsonValue], row["route"])["decision_type"]
            == "submit_movement_proposal"
        ]
        assert len(moves) == 3
        assert all(move["unit_instance_id"] == OPPONENT_UNIT_ID for move in moves)
        for move in moves:
            witness = cast(dict[str, JsonValue], move["witness"])
            assert len(cast(list[JsonValue], witness["model_paths"])) == 5
        shots = [
            cast(dict[str, JsonValue], row["proposal"])
            for row in choices
            if cast(dict[str, JsonValue], row["route"])["decision_type"]
            == "submit_shooting_declaration"
        ]
        assert len(shots) == 1
        assert shots[0]["battle_round"] == 3
        weapons = cast(list[dict[str, JsonValue]], shots[0]["declarations"])
        assert len(weapons) == 1
        assert weapons[0]["attacker_model_instance_id"] == (
            OPPONENT_UNIT_ID + ":core-intercessor-like:003"
        )
        assert weapons[0]["target_unit_instance_id"] == EXPLOITER_UNIT_ID
        assert choices[-1]["option_id"] == EXPLOITER_UNIT_ID + ":core-deep-strike-model:001"
        trace = cast(list[dict[str, JsonValue]], branch["attack_trace"])
        assert sum(len(cast(list[JsonValue], row["accepted_records"])) for row in trace) == 43
        events = cast(list[dict[str, JsonValue]], branch["attack_events"])
        assert sum(event["event_type"] == "attack_sequence_completed" for event in events) == 1
        assert branch["initial_exploiter"] == branch["before_attack_exploiter"]
        initial = cast(dict[str, JsonValue], branch["initial_exploiter"])
        final = cast(dict[str, JsonValue], branch["final_exploiter"])
        assert initial["alive_model_count"] == final["alive_model_count"] == 3
        assert final["survives"] is True
        assert branch["wounds_lost"] == 0
        assert initial["total_wounds_remaining"] == final["total_wounds_remaining"] == 6
        before_models = cast(list[dict[str, JsonValue]], initial["models"])
        after_models = cast(list[dict[str, JsonValue]], final["models"])
        assert [row["pose"] for row in before_models] == [row["pose"] for row in after_models]
        assert all(row["pose"] is not None for row in after_models)
        assert [row["wounds_remaining"] for row in after_models] == [2, 2, 2]
        assert sum(cast(int, row["wounds_remaining"]) for row in after_models) == (
            cast(int, final["total_wounds_remaining"])
        )
    assert (
        branches["stationary"]["controlled_choices"]
        == branches["normal_move"]["controlled_choices"]
    )
    assert branches["stationary"]["horizon"] == branches["normal_move"]["horizon"]
    assert payload["comparison"] == {
        "same_initial_exploiter": True,
        "same_before_attack_exploiter": True,
        "same_final_exploiter": True,
        "normal_move_minus_stationary_wounds": 0,
        "normal_move_minus_stationary_alive_models": 0,
        "tactical_benefit": "not-established-by-one-fixed-seed-cooperative-pair",
    }


def test_matched_report_replays_both_branches_and_stays_export_only(
    comparison: tuple[LocalGameSession, LocalGameSession, MatchedAttackComparison],
) -> None:
    report = comparison[2]
    payload = report.to_payload()
    assert json.loads(canonical_json(payload)) == payload
    assert report.content_hash == payload_digest(payload)
    branches = cast(dict[str, dict[str, JsonValue]], payload["branches"])
    for branch in branches.values():
        artifact = cast(ReplayArtifactPayload, branch["replay_artifact"])
        assert payload_digest(artifact) == branch["replay_artifact_hash"]
        assert ReplayRunner.from_payload(artifact).run().reproduced_exactly
    # Origins already restore each complete generated endpoint through strict
    # persistence; keep the original 22/23 endpoints and their views unextended.
    assert [item.decision_record_count() for item in comparison[:2]] == [22, 23]
    for session in comparison[:2]:
        for player in ("player-a", "player-b"):
            view = canonical_json(session.view(viewer_player_id=player))
            assert "matched-attack-comparison" not in view
            assert "same_final_exploiter" not in view
    assert opposing_shooter_definition()["attack_branch"] == "stationary-only"
    assert payload["eligible_for_learning"] is False
    assert payload["reference_target"] is None
    assert payload["useful_reference_status"] == "scoped_gap"
    payload["eligible_for_learning"] = True
    branches["stationary"]["wounds_lost"] = 99
    assert report.to_payload()["eligible_for_learning"] is False
    assert payload_digest(report.to_payload()) == report.content_hash
    assert report.to_payload() != payload


def test_matched_report_rejects_wrong_config_unreached_and_extra_ordinary_decisions(
    comparison: tuple[LocalGameSession, LocalGameSession, MatchedAttackComparison],
) -> None:
    with pytest.raises(TrainingAdmissionError, match="exact ordinary sessions"):
        MatchedAttackComparison()
    fresh = LocalGameSession()
    fresh.start(canonical_deployment_config())
    other = LocalGameSession()
    other.start(replace(canonical_deployment_config(), game_id="outside-matched-attack"))
    with pytest.raises(TrainingAdmissionError, match="configuration drifted"):
        MatchedAttackComparison.from_sessions(other, fresh)
    with pytest.raises(TrainingAdmissionError, match="22/23-record endpoints"):
        MatchedAttackComparison.from_sessions(fresh, fresh)
    stationary, moved = comparison[:2]
    extra = moved.fork()
    context = PlayerDecisionContext.from_view(
        extra.view(viewer_player_id="player-b"), choice_seed=7
    )
    extra.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player("player-b"),
        request_id=context.request["request_id"],
        payload={"submission_kind": "decline_stratagem_window"},
        result_id="matched-extra-decline",
    )
    before = canonical_json(extra.to_persistence_payload())
    with pytest.raises(TrainingAdmissionError, match="22/23-record endpoints"):
        MatchedAttackComparison.from_sessions(stationary, extra)
    assert canonical_json(extra.to_persistence_payload()) == before


def test_matched_report_rejects_same_count_endpoint_drift(
    comparison: tuple[LocalGameSession, LocalGameSession, MatchedAttackComparison],
) -> None:
    stationary, moved = comparison[:2]
    drifted = moved.fork()
    assert drifted.lifecycle.state is not None
    # Explicit endpoint trust-boundary control; this edit is not normal gameplay.
    drifted.lifecycle.state.battle_round = 2
    before = canonical_json(drifted.to_persistence_payload())
    with pytest.raises(TrainingAdmissionError, match="differ from ordinary reproduction"):
        MatchedAttackComparison.from_sessions(stationary, drifted)
    assert canonical_json(drifted.to_persistence_payload()) == before
