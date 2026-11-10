from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.replay import submit_replay_record
from warhammer40k_core.ai.canonical_deployment import canonical_deployment_config
from warhammer40k_core.ai.normal_move_scenario import (
    NORMAL_MOVE_SCENARIO_DEFINITION_HASH,
    NORMAL_MOVE_SCENARIO_ID,
    NormalMoveScenarioAdmission,
    normal_move_scenario_definition,
    reproduce_normal_move_scenario,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, payload_digest
from warhammer40k_core.ai.preserve_scenario import (
    EXPLOITER_UNIT_ID,
    PRESERVE_SCENARIO_DEFINITION_HASH,
    SCREEN_UNIT_ID,
    preserve_scenario_definition,
    reproduce_preserve_scenario,
)
from warhammer40k_core.ai.training_admission import TrainingAdmissionError
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner


@pytest.fixture(scope="module")
def moved() -> tuple[LocalGameSession, NormalMoveScenarioAdmission]:
    session = reproduce_normal_move_scenario()
    return session, NormalMoveScenarioAdmission.from_session(session)


def _prefix(session: LocalGameSession, count: int) -> LocalGameSession:
    fresh = LocalGameSession()
    fresh.start(canonical_deployment_config())
    fresh.advance_until_decision_or_terminal()
    for record in session.lifecycle.decision_controller.records[:count]:
        submit_replay_record(session=fresh, record=record)
        fresh.advance_until_decision_or_terminal()
    return fresh


def _model_placements(session: LocalGameSession) -> dict[str, dict[str, JsonValue]]:
    battlefield = cast(
        dict[str, JsonValue], session.view(viewer_player_id="player-a")["battlefield_state"]
    )
    return {
        cast(str, model["model_instance_id"]): model
        for army in cast(list[dict[str, JsonValue]], battlefield["placed_armies"])
        for unit in cast(list[dict[str, JsonValue]], army["unit_placements"])
        for model in cast(list[dict[str, JsonValue]], unit["model_placements"])
    }


def test_normal_move_branches_from_preservation_prefix_with_actual_witness(
    moved: tuple[LocalGameSession, NormalMoveScenarioAdmission],
) -> None:
    session, admission = moved
    preserved = reproduce_preserve_scenario()
    before = _prefix(preserved, 15)
    assert _prefix(session, 15).to_persistence_payload() == before.to_persistence_payload()
    assert payload_digest(preserve_scenario_definition()) == PRESERVE_SCENARIO_DEFINITION_HASH
    assert payload_digest(normal_move_scenario_definition()) == NORMAL_MOVE_SCENARIO_DEFINITION_HASH
    payload = admission.to_payload()
    assert payload["common_prefix_checkpoint_hash"] == payload_digest(
        before.to_persistence_payload()
    )
    assert session.decision_record_count() == 18
    assert payload["observed_routes"] == payload["required_routes"]
    assert payload["unobserved_required_routes"] == []
    assert len(cast(list[JsonValue], payload["required_routes"])) == 14
    trace = cast(list[dict[str, JsonValue]], payload["accepted_trace"])
    assert [row["record"] for row in trace] == [
        record.to_payload() for record in session.lifecycle.decision_controller.records
    ]
    assert trace[-2]["selected_candidate_id"] == "normal_move"
    evidence = cast(dict[str, JsonValue], payload["mechanic_evidence"])
    activation = cast(dict[str, JsonValue], evidence["activation"])
    details = cast(dict[str, JsonValue], activation["payload"])
    assert details["unit_instance_id"] == SCREEN_UNIT_ID
    assert details["movement_phase_action"] == "normal_move"
    witness = cast(dict[str, JsonValue], details["witness"])
    paths = cast(list[dict[str, JsonValue]], witness["model_paths"])
    assert len(paths) == 5
    before_models = _model_placements(before)
    after_models = _model_placements(session)
    assert before_models.keys() == after_models.keys()
    for path in paths:
        poses = cast(list[dict[str, JsonValue]], path["poses"])
        start = cast(dict[str, float], poses[0]["position"])
        end = cast(dict[str, float], poses[-1]["position"])
        assert end == {"x": start["x"] - 1.0, "y": start["y"], "z": start["z"]}
        assert poses[-1]["facing"] == poses[0]["facing"]
        model_id = cast(str, path["model_id"])
        assert before_models[model_id]["pose"] == poses[0]
        assert after_models[model_id] == {**before_models[model_id], "pose": poses[-1]}
    moving_ids = {cast(str, path["model_id"]) for path in paths}
    for model_id in before_models.keys() - moving_ids:
        assert after_models[model_id] == before_models[model_id]
    context = PlayerDecisionContext.from_view(
        session.view(viewer_player_id="player-a"), choice_seed=7
    )
    assert context.route.decision_type == "select_movement_unit"
    assert SCREEN_UNIT_ID not in {option["option_id"] for option in context.request["options"]}
    assert EXPLOITER_UNIT_ID in {option["option_id"] for option in context.request["options"]}
    assert payload["useful_reference_status"] == "scoped_gap"
    assert payload["reference_target"] is None
    assert payload["eligible_for_learning"] is False
    assert "witnessed-screen-or-exposure-movement-alternative" in cast(
        list[str], payload["unobserved_required_tactical_mechanics"]
    )
    assert "useful_reference_status" not in canonical_json(context.observation)


def test_normal_move_json_restore_exact_replay_and_closed_receipt(
    moved: tuple[LocalGameSession, NormalMoveScenarioAdmission],
) -> None:
    session, admission = moved
    before = canonical_json(session.to_persistence_payload())
    restored = LocalGameSession.from_persistence_payload(json.loads(before))
    assert canonical_json(restored.to_persistence_payload()) == before
    assert (
        ReplayRunner.from_payload(restored.replay_artifact(artifact_id=NORMAL_MOVE_SCENARIO_ID))
        .run()
        .reproduced_exactly
    )
    assert (
        NormalMoveScenarioAdmission.from_payload(
            json.loads(canonical_json(admission.to_payload())), session=restored
        ).content_hash
        == admission.content_hash
    )
    for actor in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=actor) == session.view(viewer_player_id=actor)
    for key, value in (("reference_target", 1), ("extra", True), ("eligible_for_learning", True)):
        changed = admission.to_payload()
        changed[key] = value
        with pytest.raises(TrainingAdmissionError, match="payload drifted"):
            NormalMoveScenarioAdmission.from_payload(changed, session=restored)
    assert admission.to_payload()["reference_target"] is None
    with pytest.raises(TrainingAdmissionError, match="ordinary session"):
        NormalMoveScenarioAdmission()


def test_normal_move_rejects_incomplete_and_extra_ordinary_choices(
    moved: tuple[LocalGameSession, NormalMoveScenarioAdmission],
) -> None:
    other = LocalGameSession()
    other.start(replace(canonical_deployment_config(), game_id="other-normal-move-scenario"))
    with pytest.raises(TrainingAdmissionError, match="frozen normal move configuration"):
        NormalMoveScenarioAdmission.from_session(other)
    with pytest.raises(TrainingAdmissionError, match="18 records"):
        NormalMoveScenarioAdmission.from_session(reproduce_preserve_scenario())
    extra = moved[0].fork()
    context = PlayerDecisionContext.from_view(
        extra.view(viewer_player_id="player-a"), choice_seed=7
    )
    extra.submit_viewer_option(
        viewer=ViewerContext.for_player("player-a"),
        request_id=context.request["request_id"],
        option_id=EXPLOITER_UNIT_ID,
        result_id="normal-move-extra-choice",
    )
    with pytest.raises(TrainingAdmissionError, match="18 records"):
        NormalMoveScenarioAdmission.from_session(extra)


def test_normal_move_distance_rejection_remains_engine_owned_and_replayable(
    moved: tuple[LocalGameSession, NormalMoveScenarioAdmission],
) -> None:
    session = _prefix(moved[0], 17)
    context = PlayerDecisionContext.from_view(
        session.view(viewer_player_id="player-a"), choice_seed=7
    )
    record = moved[0].lifecycle.decision_controller.records[-1].to_payload()
    result = cast(dict[str, JsonValue], record["result"])
    proposal = cast(dict[str, JsonValue], json.loads(canonical_json(result["payload"])))
    # Use the issued viewer capability rather than its authoritative record ID.
    pending = cast(dict[str, JsonValue], context.observation["pending_proposal"])
    proposal["proposal_request_id"] = pending["request_id"]
    witness = cast(dict[str, JsonValue], proposal["witness"])
    for path in cast(list[dict[str, JsonValue]], witness["model_paths"]):
        poses = cast(list[dict[str, JsonValue]], path["poses"])
        cast(dict[str, JsonValue], poses[-1]["position"])["x"] = 1000.0
    before = session.view(viewer_player_id="player-a")["battlefield_state"]
    status = session.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player("player-a"),
        request_id=context.request["request_id"],
        payload=proposal,
        result_id="normal-move-invalid-distance",
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.view(viewer_player_id="player-a")["battlefield_state"] == before
    assert session.decision_record_count() == 18
    with pytest.raises(TrainingAdmissionError, match="exact normal move"):
        NormalMoveScenarioAdmission.from_session(session)
    restored = LocalGameSession.from_persistence_payload(
        json.loads(canonical_json(session.to_persistence_payload()))
    )
    assert (
        ReplayRunner.from_payload(restored.replay_artifact(artifact_id="invalid-normal-move"))
        .run()
        .reproduced_exactly
    )
