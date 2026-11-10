from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from typing import cast

import pytest

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.canonical_deployment import (
    CANONICAL_DEPLOYMENT_CONFIG_HASH,
    CANONICAL_DEPLOYMENT_ID,
    CanonicalDeploymentAdmission,
    canonical_deployment_config,
    reproduce_canonical_deployment,
)
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, payload_digest
from warhammer40k_core.ai.runner import RunReport
from warhammer40k_core.ai.training_admission import TrainingAdmissionError
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner


@pytest.fixture(scope="module")
def canonical() -> tuple[LocalGameSession, RunReport, CanonicalDeploymentAdmission]:
    session, report = reproduce_canonical_deployment()
    return session, report, CanonicalDeploymentAdmission.from_session(session)


def test_canonical_recipe_reconciles_exact_accepted_routes_and_endpoint(
    canonical: tuple[LocalGameSession, RunReport, CanonicalDeploymentAdmission],
) -> None:
    session, report, admission = canonical
    payload = admission.to_payload()
    assert payload["configuration_hash"] == CANONICAL_DEPLOYMENT_CONFIG_HASH
    assert payload_digest(payload["configuration"]) == CANONICAL_DEPLOYMENT_CONFIG_HASH
    assert payload["configuration"] == canonical_deployment_config().to_payload()
    assert report.stop_reason == "requested_boundary"
    assert report.final_record_count == 11
    assert len(report.decisions) == 11
    assert all(attempt.accepted and attempt.recorded_decisions == 1 for attempt in report.decisions)
    required = cast(list[dict[str, JsonValue]], payload["required_routes"])
    assert [
        (route["actor_id"], route["decision_type"], route["setup_step"], route["proposal_kind"])
        for route in required
    ] == [
        ("player-a", "select_secondary_missions", "select_secondary_missions", None),
        ("player-b", "select_secondary_missions", "select_secondary_missions", None),
        ("player-a", "select_reserve_declaration", "declare_battle_formations", None),
        ("player-b", "select_deployment_unit", "deploy_armies", None),
        ("player-b", "submit_deployment_placement", "deploy_armies", "deployment_placement"),
        ("player-a", "select_deployment_unit", "deploy_armies", None),
        ("player-a", "submit_deployment_placement", "deploy_armies", "deployment_placement"),
    ]
    assert payload["observed_routes"] == required
    assert payload["unobserved_required_routes"] == []
    endpoint = cast(dict[str, JsonValue], payload["endpoint_route"])
    assert endpoint["setup_step"] == "redeploy_units"
    assert endpoint not in required
    assert payload["episode_end"] == "truncated"
    assert payload["pending_stage2_evidence"] == [
        "candidate-reference-alternative-coverage",
        "component-costs",
    ]
    assert "redeploy-and-scout-movement" in cast(list[str], payload["unsupported_by_recipe"])
    trace = cast(list[dict[str, JsonValue]], payload["accepted_trace"])
    assert [item["record"] for item in trace] == [
        record.to_payload() for record in session.lifecycle.decision_controller.records
    ]
    view = session.view(viewer_player_id="player-a")
    battlefield = cast(dict[str, JsonValue], view["battlefield_state"])
    armies = cast(list[dict[str, JsonValue]], battlefield["placed_armies"])
    units = [
        unit
        for army in armies
        for unit in cast(list[dict[str, JsonValue]], army["unit_placements"])
    ]
    assert sorted(len(cast(list[JsonValue], unit["model_placements"])) for unit in units) == [
        1,
        3,
        5,
        5,
    ]


def test_canonical_endpoint_roundtrips_json_save_and_exact_replay(
    canonical: tuple[LocalGameSession, RunReport, CanonicalDeploymentAdmission],
) -> None:
    session, _, admission = canonical
    before = canonical_json(session.to_persistence_payload())
    restored = LocalGameSession.from_persistence_payload(json.loads(before))
    assert canonical_json(restored.to_persistence_payload()) == before
    assert (
        ReplayRunner.from_payload(restored.replay_artifact(artifact_id=CANONICAL_DEPLOYMENT_ID))
        .run()
        .reproduced_exactly
    )
    loaded = CanonicalDeploymentAdmission.from_payload(admission.to_payload(), session=restored)
    assert loaded.content_hash == admission.content_hash
    for actor in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=actor) == session.view(viewer_player_id=actor)
        assert "f0" * 32 not in canonical_json(restored.view(viewer_player_id=actor))
        assert CANONICAL_DEPLOYMENT_CONFIG_HASH not in canonical_json(
            restored.view(viewer_player_id=actor)
        )
    assert canonical_json(session.to_persistence_payload()) == before


def test_fixture_discloses_roster_geometry_and_scoring_exceptions(
    canonical: tuple[LocalGameSession, RunReport, CanonicalDeploymentAdmission],
) -> None:
    _, _, admission = canonical
    payload = admission.to_payload()
    config = canonical_deployment_config()
    assert config.allow_legacy_non_strict_rosters is True
    assert config.army_catalog.catalog_id == "phase9a-canonical"
    assert config.mission_setup is not None
    assert config.mission_setup.source_id == "gw-11e-warhammer-event-companion-v1-1-2026-07"
    assert [(item.unit_instance_id, item.points) for item in config.reserve_unit_points] == [
        ("army-alpha:strategic-reserve-unit", 300)
    ]
    exceptions = cast(list[str], payload["fixture_exceptions"])
    assert "legacy-model-volumes-not-source-measured-model-heights" in exceptions
    assert "setup-smoke-REDEPLOY-and-SCOUTS-overlay-retained-not-exercised" in exceptions
    assert cast(dict[str, JsonValue], payload["source_obligations"])["scoring"] == (
        "fixed-secondary-selection-only-no-scoring-window-or-outcome-label"
    )
    detached = admission.to_payload()
    detached["fixture_exceptions"] = []
    assert admission.to_payload()["fixture_exceptions"] == exceptions
    with pytest.raises(FrozenInstanceError):
        admission._payload_json = "{}"  # type: ignore[misc]
    with pytest.raises(TrainingAdmissionError, match="ordinary session"):
        CanonicalDeploymentAdmission()


@pytest.mark.parametrize("change", ["seed", "game-id"])
def test_other_ordinary_configuration_cannot_inherit_canonical_admission(change: str) -> None:
    config = canonical_deployment_config()
    changed = (
        replace(config, private_rng_seed="ab" * 32)
        if change == "seed"
        else replace(config, game_id="different-canonical-game")
    )
    session = LocalGameSession()
    session.start(changed)
    session.advance_until_decision_or_terminal()
    with pytest.raises(TrainingAdmissionError, match="frozen canonical"):
        CanonicalDeploymentAdmission.from_session(session)


def test_ordinary_incomplete_prefix_is_not_the_deployed_endpoint() -> None:
    session = LocalGameSession()
    session.start(canonical_deployment_config())
    session.advance_until_decision_or_terminal()
    context = PlayerDecisionContext.from_view(
        session.view(viewer_player_id="player-a"), choice_seed=7
    )
    status = session.submit_viewer_option(
        viewer=ViewerContext.for_player("player-a"),
        request_id=context.request["request_id"],
        option_id="fixed:assassination:cleanse",
        result_id="different-ordinary-choice",
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    before = canonical_json(session.to_persistence_payload())
    with pytest.raises(TrainingAdmissionError, match="trace or endpoint"):
        CanonicalDeploymentAdmission.from_session(session)
    assert canonical_json(session.to_persistence_payload()) == before


@pytest.mark.parametrize(
    "field",
    [
        "configuration",
        "recipe",
        "accepted_trace",
        "observed_routes",
        "endpoint_route",
        "fixture_exceptions",
        "source_obligations",
        "pending_stage2_evidence",
    ],
)
def test_canonical_receipt_loader_rejects_closed_evidence_drift(
    canonical: tuple[LocalGameSession, RunReport, CanonicalDeploymentAdmission],
    field: str,
) -> None:
    session, _, admission = canonical
    payload = admission.to_payload()
    payload[field] = None
    with pytest.raises(TrainingAdmissionError, match="payload drifted"):
        CanonicalDeploymentAdmission.from_payload(payload, session=session)
