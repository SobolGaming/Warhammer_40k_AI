from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from typing import cast

import pytest

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.canonical_deployment import (
    canonical_deployment_config,
    canonical_deployment_prefixes,
    reproduce_canonical_deployment,
)
from warhammer40k_core.ai.canonical_deployment_coverage import (
    CanonicalDeploymentCoverage,
    _coverage,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.ai.deployment_candidate_search import DeploymentCandidateSet
from warhammer40k_core.ai.deployment_candidates import DeploymentPlacementCandidate
from warhammer40k_core.ai.training_admission import TrainingAdmissionError
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner


def test_complete_canonical_coverage_reconciles_reproduces_and_rejects_false_denominator() -> None:
    session, _ = reproduce_canonical_deployment()
    before = canonical_json(session.to_persistence_payload())
    report = CanonicalDeploymentCoverage.measure(session=session)
    payload = report.to_payload()
    rows = cast(list[dict[str, JsonValue]], payload["rows"])
    assert [row["index"] for row in rows] == list(range(11))
    assert len({canonical_json(row["route"]) for row in rows}) == 7
    assert [row["index"] for row in rows if row["kind"] == "placement"] == [4, 6, 8, 10]
    totals = cast(dict[str, dict[str, int]], payload["totals"])
    assert totals["finite"]["decision_occurrences"] == 7
    assert totals["placement"]["decision_occurrences"] == 4
    assert totals["placement"]["generated_count"] == 20
    assert totals["placement"]["reference_attempts"] == 40
    assert totals["finite"]["generated_count"] == 18
    assert totals["finite"]["accepted_count"] == 18
    assert totals["placement"]["accepted_count"] == 19
    assert totals["placement"]["legal_reference_count"] == 32
    assert totals["placement"]["covered_legal_reference_count"] == 19
    assert totals["placement"]["invalid_reference_probe_count"] == 8
    assert (
        0
        < totals["placement"]["covered_legal_reference_count"]
        < totals["placement"]["legal_reference_count"]
    )
    for kind in ("finite", "placement"):
        counts = totals[kind]
        assert counts["generated_count"] == counts["validation_attempts"]
        assert counts["validation_attempts"] == counts["accepted_count"] + counts["rejected_count"]
        assert counts["unvalidated_count"] == 0
        assert counts["reference_attempts"] == (
            counts["legal_reference_count"] + counts["invalid_reference_probe_count"]
        )
    for row in rows:
        counts = cast(dict[str, int], row["counts"])
        if row["kind"] == "finite":
            results = cast(list[dict[str, JsonValue]], row["results"])
            assert counts["covered_legal_reference_count"] == counts["legal_reference_count"]
        else:
            validation = cast(dict[str, JsonValue], row["validation"])
            results = cast(list[dict[str, JsonValue]], validation["results"])
            references = cast(dict[str, JsonValue], row["reference_validation"])
            assert validation["stop_reason"] == references["stop_reason"] == "complete"
            assert counts["missing_legal_reference_ids"]
        assert any(
            result["candidate_id"] == row["recipe_candidate_id"] and result["accepted"]
            for result in results
        )
    assert payload["stop_reason"] == "before-redeploy"
    assert "component-costs" in cast(list[str], payload["pending_stage2_evidence"])
    assert session.view(viewer_player_id="player-a")["current_setup_step"] == "redeploy_units"
    assert canonical_json(session.to_persistence_payload()) == before
    restored = LocalGameSession.from_persistence_payload(json.loads(before))
    loaded = CanonicalDeploymentCoverage.from_payload(
        json.loads(canonical_json(payload)), session=restored
    )
    assert loaded.content_hash == report.content_hash
    # One representative supported-input boundary: a fabricated legal-reference
    # denominator must not survive closed, fresh engine reproduction.
    totals["placement"]["legal_reference_count"] = 0
    with pytest.raises(TrainingAdmissionError, match="payload drifted"):
        CanonicalDeploymentCoverage.from_payload(payload, session=restored)
    assert report.to_payload()["totals"] != totals
    with pytest.raises(FrozenInstanceError):
        report._payload_json = "{}"  # type: ignore[misc]
    with pytest.raises(TrainingAdmissionError, match="ordinary session"):
        CanonicalDeploymentCoverage()


def test_coverage_counter_keeps_missing_invalid_and_unvalidated_distinct() -> None:
    counts = _coverage(
        ["generated-valid", "generated-invalid", "unvalidated"],
        [
            {"candidate_id": "generated-valid", "accepted": True},
            {"candidate_id": "generated-invalid", "accepted": False},
        ],
        [
            {"candidate_id": "generated-valid", "accepted": True},
            {"candidate_id": "missing-valid", "accepted": True},
            {"candidate_id": "invalid-reference", "accepted": False},
        ],
    )
    assert counts == {
        "generated_count": 3,
        "validation_attempts": 2,
        "accepted_count": 1,
        "rejected_count": 1,
        "unvalidated_count": 1,
        "reference_attempts": 3,
        "legal_reference_count": 2,
        "invalid_reference_probe_count": 1,
        "covered_legal_reference_count": 1,
        "missing_legal_reference_ids": ["missing-valid"],
    }


def test_coverage_rejects_other_configuration_and_ordinary_incomplete_prefix() -> None:
    for config, message in (
        (replace(canonical_deployment_config(), game_id="other-coverage"), "frozen canonical"),
        (canonical_deployment_config(), "trace or endpoint"),
    ):
        session = LocalGameSession()
        session.start(config)
        session.advance_until_decision_or_terminal()
        before = canonical_json(session.to_persistence_payload())
        with pytest.raises(TrainingAdmissionError, match=message):
            CanonicalDeploymentCoverage.measure(session=session)
        assert canonical_json(session.to_persistence_payload()) == before


def test_nonrecipe_reference_acceptance_roundtrips_without_changing_canonical_prefix() -> None:
    session, report = reproduce_canonical_deployment()
    prefixes = canonical_deployment_prefixes(session, report)
    before, context, recipe = prefixes[4]
    original = canonical_json(before.to_persistence_payload())
    seed = DeploymentPlacementCandidate.from_action(recipe, context=context)
    candidates = DeploymentCandidateSet.generate(
        seed, context=context, translations=((2.0, 0.0),), raw_budget=1
    )
    action = candidates.candidates[0].select(context)
    assert action.proposal_json is not None
    probe = before.fork()
    status = probe.submit_viewer_parameterized_payload(
        viewer=ViewerContext.for_player(action.actor_id),
        request_id=action.request_id,
        payload=json.loads(action.proposal_json),
        result_id="nonrecipe-reference-positive",
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert probe.decision_record_count() == before.decision_record_count() + 1
    checkpoint = probe.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    assert (
        ReplayRunner.from_payload(restored.replay_artifact(artifact_id="reference-positive"))
        .run()
        .reproduced_exactly
    )
    assert canonical_json(before.to_persistence_payload()) == original
    with pytest.raises(TrainingAdmissionError, match="complete recipe trace"):
        canonical_deployment_prefixes(probe, report)
