from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.canonical_deployment import (
    canonical_deployment_config,
    reproduce_canonical_deployment,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, payload_digest
from warhammer40k_core.ai.preserve_scenario import (
    EXPLOITER_UNIT_ID,
    OPPONENT_UNIT_ID,
    PRESERVE_SCENARIO_DEFINITION_HASH,
    PRESERVE_SCENARIO_ID,
    SCREEN_UNIT_ID,
    PreserveScenarioAdmission,
    preserve_scenario_definition,
    reproduce_preserve_scenario,
)
from warhammer40k_core.ai.training_admission import TrainingAdmissionError
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner


@pytest.fixture(scope="module")
def canonical() -> LocalGameSession:
    return reproduce_canonical_deployment()[0]


@pytest.fixture(scope="module")
def preserve() -> tuple[LocalGameSession, PreserveScenarioAdmission]:
    session = reproduce_preserve_scenario()
    return session, PreserveScenarioAdmission.from_session(session)


def test_preserve_prefix_has_exact_routes_candidates_and_scoped_tactical_gaps(
    canonical: LocalGameSession,
    preserve: tuple[LocalGameSession, PreserveScenarioAdmission],
) -> None:
    session, admission = preserve
    payload = admission.to_payload()
    assert payload_digest(preserve_scenario_definition()) == PRESERVE_SCENARIO_DEFINITION_HASH
    assert session.decision_record_count() == 17
    assert payload["observed_routes"] == payload["required_routes"]
    assert payload["unobserved_required_routes"] == []
    assert len(cast(list[JsonValue], payload["required_routes"])) == 13
    trace = cast(list[dict[str, JsonValue]], payload["accepted_trace"])
    assert len(trace) == 17
    assert [row["record"] for row in trace] == [
        record.to_payload() for record in session.lifecycle.decision_controller.records
    ]
    candidate_set = cast(dict[str, JsonValue], trace[-1]["finite_candidates"])
    options = cast(list[dict[str, JsonValue]], candidate_set["options"])
    assert [option["option_id"] for option in options] == [
        "advance",
        "normal_move",
        "remain_stationary",
    ]
    assert trace[-1]["selected_candidate_id"] == "remain_stationary"
    assert trace[-1]["observation_hash"] == candidate_set["observation_hash"]
    evidence = cast(dict[str, JsonValue], payload["mechanic_evidence"])
    activation = cast(list[dict[str, JsonValue]], evidence["activation"])
    details = cast(dict[str, JsonValue], activation[0]["payload"])
    assert details["unit_instance_id"] == SCREEN_UNIT_ID
    assert details["movement_inches"] == 0
    assert details["model_movements"] == []
    assert details["witness"] is None
    view = session.view(viewer_player_id="player-a")
    assert (
        view["battlefield_state"]
        == canonical.view(viewer_player_id="player-a")["battlefield_state"]
    )
    context = PlayerDecisionContext.from_view(view, choice_seed=7)
    assert context.route.battle_phase == "movement"
    assert context.route.decision_type == "select_movement_unit"
    assert SCREEN_UNIT_ID not in {option["option_id"] for option in context.request["options"]}
    assert EXPLOITER_UNIT_ID in {option["option_id"] for option in context.request["options"]}
    assert payload["useful_reference_status"] == "scoped_gap"
    assert payload["reference_target"] is None
    assert payload["eligible_for_learning"] is False
    definition = cast(dict[str, JsonValue], payload["definition"])
    assert (
        payload["unobserved_required_tactical_mechanics"]
        == definition["required_tactical_mechanics"]
    )
    assert "later-scoring-or-attack-benefit-compared-with-preservation" in cast(
        list[str], payload["unobserved_required_tactical_mechanics"]
    )
    obligations = cast(list[dict[str, JsonValue]], definition["pending_tactical_route_obligations"])
    assert all(row["status"] == "unobserved" for row in obligations)
    assert [row["unit_instance_id"] for row in obligations] == [
        SCREEN_UNIT_ID,
        EXPLOITER_UNIT_ID,
        OPPONENT_UNIT_ID,
    ]
    assert "setup-smoke-overlay-decline-only-no-redeploy-or-scout-movement" in cast(
        list[str], payload["fixture_exceptions"]
    )
    assert "useful_reference_status" not in canonical_json(view)
    assert "required_tactical_mechanics" not in canonical_json(view)
    detached = admission.to_payload()
    detached["useful_reference_status"] = "qualified"
    assert admission.to_payload()["useful_reference_status"] == "scoped_gap"
    with pytest.raises(TrainingAdmissionError, match="ordinary session"):
        PreserveScenarioAdmission()


def test_preserve_prefix_persists_replays_and_rejects_changed_closed_evidence(
    preserve: tuple[LocalGameSession, PreserveScenarioAdmission],
) -> None:
    session, admission = preserve
    before = canonical_json(session.to_persistence_payload())
    restored = LocalGameSession.from_persistence_payload(json.loads(before))
    assert canonical_json(restored.to_persistence_payload()) == before
    assert (
        ReplayRunner.from_payload(restored.replay_artifact(artifact_id=PRESERVE_SCENARIO_ID))
        .run()
        .reproduced_exactly
    )
    assert (
        PreserveScenarioAdmission.from_payload(
            admission.to_payload(), session=restored
        ).content_hash
        == admission.content_hash
    )
    for actor in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=actor) == session.view(viewer_player_id=actor)
    changed = admission.to_payload()
    changed["useful_reference_status"] = "qualified"
    with pytest.raises(TrainingAdmissionError, match="payload drifted"):
        PreserveScenarioAdmission.from_payload(changed, session=restored)
    assert canonical_json(session.to_persistence_payload()) == before


def test_preserve_prefix_rejects_other_config_incomplete_and_extra_ordinary_choices(
    canonical: LocalGameSession,
    preserve: tuple[LocalGameSession, PreserveScenarioAdmission],
) -> None:
    other = LocalGameSession()
    other.start(replace(canonical_deployment_config(), game_id="other-preserve-scenario"))
    with pytest.raises(TrainingAdmissionError, match="frozen preserve configuration"):
        PreserveScenarioAdmission.from_session(other)
    with pytest.raises(TrainingAdmissionError, match="17 records"):
        PreserveScenarioAdmission.from_session(canonical)
    extra = preserve[0].fork()
    context = PlayerDecisionContext.from_view(
        extra.view(viewer_player_id="player-a"), choice_seed=7
    )
    status = extra.submit_viewer_option(
        viewer=ViewerContext.for_player("player-a"),
        request_id=context.request["request_id"],
        option_id=EXPLOITER_UNIT_ID,
        result_id="preserve-extra-ordinary-choice",
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert extra.decision_record_count() == 18
    with pytest.raises(TrainingAdmissionError, match="17 records"):
        PreserveScenarioAdmission.from_session(extra)
