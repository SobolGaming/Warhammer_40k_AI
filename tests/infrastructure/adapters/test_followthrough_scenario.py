from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.canonical_deployment import canonical_deployment_config
from warhammer40k_core.ai.followthrough_scenario import (
    FOLLOWTHROUGH_DEFINITION_HASH,
    FollowthroughPairAdmission,
    followthrough_definition,
    reproduce_followthrough_pair,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, payload_digest
from warhammer40k_core.ai.preserve_scenario import EXPLOITER_UNIT_ID, SCREEN_UNIT_ID
from warhammer40k_core.ai.training_admission import TrainingAdmissionError
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner


@pytest.fixture(scope="module")
def pair() -> tuple[LocalGameSession, LocalGameSession, FollowthroughPairAdmission]:
    stationary, moved = reproduce_followthrough_pair()
    return stationary, moved, FollowthroughPairAdmission.from_sessions(stationary, moved)


def test_matched_exploiter_movement_and_engine_rejected_opponent_shooter(
    pair: tuple[LocalGameSession, LocalGameSession, FollowthroughPairAdmission],
) -> None:
    stationary, moved, admission = pair
    assert payload_digest(followthrough_definition()) == FOLLOWTHROUGH_DEFINITION_HASH
    payload = admission.to_payload()
    branches = cast(dict[str, dict[str, JsonValue]], payload["branches"])
    for name, session, count, screen_action in (
        ("stationary", stationary, 22, "remain_stationary"),
        ("normal_move", moved, 23, "normal_move"),
    ):
        branch = branches[name]
        assert session.decision_record_count() == count
        assert branch["accepted_records"] == [
            record.to_payload() for record in session.lifecycle.decision_controller.records
        ]
        assert branch["unobserved_required_routes"] == []
        context = PlayerDecisionContext.from_view(
            session.view(viewer_player_id="player-b"), choice_seed=7
        )
        assert context.route.actor_id == "player-b"
        assert context.route.decision_type == "submit_stratagem_target_proposal"
        assert context.route.battle_phase == "movement"
        assert context.route.proposal_kind == "stratagem_target_binding"
        assert "useful_reference_status" not in canonical_json(context.observation)
        activations = cast(list[dict[str, JsonValue]], branch["movement_activations"])
        details = [cast(dict[str, JsonValue], event["payload"]) for event in activations]
        assert [item["unit_instance_id"] for item in details] == [
            SCREEN_UNIT_ID,
            EXPLOITER_UNIT_ID,
            "army-alpha:strategic-reserve-unit",
        ]
        assert [item["movement_phase_action"] for item in details] == [
            screen_action,
            "normal_move",
            "remain_stationary",
        ]
        witness = cast(dict[str, JsonValue], details[1]["witness"])
        paths = cast(list[dict[str, JsonValue]], witness["model_paths"])
        assert len(paths) == 3
        for path in paths:
            poses = cast(list[dict[str, JsonValue]], path["poses"])
            start = cast(dict[str, float], poses[0]["position"])
            assert poses[-1] == {
                "position": {"x": start["x"] - 1.0, "y": start["y"], "z": start["z"]},
                "facing": poses[0]["facing"],
            }
        probe = cast(dict[str, JsonValue], branch["opponent_probe"])
        assert probe["status"] == "invalid"
        assert probe["diagnostic"] == {
            "invalid_reason": "fire_overwatch_no_legal_shooting_declaration"
        }
        assert probe["checkpoint_unchanged"] is True
        assert probe["accepted_record_count_delta"] == 0
        assert probe["event_count_delta"] == 0
    assert (
        branches["stationary"]["common_prefix_records_hash"]
        == branches["normal_move"]["common_prefix_records_hash"]
    )
    assert payload["reference_target"] is None
    assert payload["eligible_for_learning"] is False
    assert payload["useful_reference_status"] == "scoped_gap"
    assert "opponent-attack-resolution" in cast(list[str], payload["remaining_tactical_gaps"])


def test_pair_json_replay_closed_receipt_and_declined_reaction_continuation(
    pair: tuple[LocalGameSession, LocalGameSession, FollowthroughPairAdmission],
) -> None:
    sessions = pair[:2]
    restored: list[LocalGameSession] = []
    for index, session in enumerate(sessions):
        before = canonical_json(session.to_persistence_payload())
        clone = LocalGameSession.from_persistence_payload(json.loads(before))
        assert canonical_json(clone.to_persistence_payload()) == before
        assert (
            ReplayRunner.from_payload(clone.replay_artifact(artifact_id=f"followthrough:{index}"))
            .run()
            .reproduced_exactly
        )
        for actor in ("player-a", "player-b"):
            assert clone.view(viewer_player_id=actor) == session.view(viewer_player_id=actor)
        restored.append(clone)
    receipt = pair[2]
    assert (
        FollowthroughPairAdmission.from_payload(
            json.loads(canonical_json(receipt.to_payload())), restored[0], restored[1]
        ).content_hash
        == receipt.content_hash
    )
    tampered = receipt.to_payload()
    tampered["eligible_for_learning"] = True
    with pytest.raises(TrainingAdmissionError, match="payload drifted"):
        FollowthroughPairAdmission.from_payload(tampered, restored[0], restored[1])
    with pytest.raises(TrainingAdmissionError, match="ordinary sessions"):
        FollowthroughPairAdmission()
    # Declining an offered window is a separate real action, not an attack result.
    for clone in restored:
        context = PlayerDecisionContext.from_view(
            clone.view(viewer_player_id="player-b"), choice_seed=7
        )
        status = clone.submit_viewer_parameterized_payload(
            viewer=ViewerContext.for_player("player-b"),
            request_id=context.request["request_id"],
            payload={"submission_kind": "decline_stratagem_window"},
            result_id="followthrough-decline-control",
        )
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        after = PlayerDecisionContext.from_view(
            clone.view(viewer_player_id="player-a"), choice_seed=7
        )
        assert after.route.decision_type == "select_shooting_unit"
        assert after.route.battle_phase == "shooting"
        assert (
            ReplayRunner.from_payload(clone.replay_artifact(artifact_id="declined-overwatch"))
            .run()
            .reproduced_exactly
        )
    with pytest.raises(TrainingAdmissionError, match="22 and 23 records"):
        FollowthroughPairAdmission.from_sessions(restored[0], restored[1])


def test_followthrough_rejects_wrong_configuration_and_unreached_endpoints() -> None:
    other = LocalGameSession()
    other.start(replace(canonical_deployment_config(), game_id="outside-followthrough"))
    fresh = LocalGameSession()
    fresh.start(canonical_deployment_config())
    with pytest.raises(TrainingAdmissionError, match="frozen followthrough configuration"):
        FollowthroughPairAdmission.from_sessions(other, fresh)
    with pytest.raises(TrainingAdmissionError, match="22 and 23 records"):
        FollowthroughPairAdmission.from_sessions(fresh, fresh)
