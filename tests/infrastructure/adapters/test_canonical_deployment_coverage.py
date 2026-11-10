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
    assert totals["placement"]["generated_count"] == 52
    assert totals["placement"]["reference_attempts"] == 40
    assert totals["finite"]["generated_count"] == 18
    assert totals["finite"]["accepted_count"] == 18
    assert totals["placement"]["accepted_count"] == 46
    assert totals["placement"]["legal_reference_count"] == 32
    assert totals["placement"]["covered_legal_reference_count"] == 32
    assert totals["placement"]["invalid_reference_probe_count"] == 8
    assert (
        0
        < totals["placement"]["covered_legal_reference_count"]
        == totals["placement"]["legal_reference_count"]
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
        row_counts = cast(dict[str, JsonValue], row["counts"])
        if row["kind"] == "finite":
            results = cast(list[dict[str, JsonValue]], row["results"])
            assert (
                row_counts["covered_legal_reference_count"] == row_counts["legal_reference_count"]
            )
        else:
            validation = cast(dict[str, JsonValue], row["validation"])
            results = cast(list[dict[str, JsonValue]], validation["results"])
            references = cast(dict[str, JsonValue], row["reference_validation"])
            assert validation["stop_reason"] == references["stop_reason"] == "complete"
            assert row_counts["missing_legal_reference_ids"] == []
            # Independently pin all formerly missing second-ring alternatives,
            # including the three rejected directions; do not infer usefulness
            # merely from equality of the generator/reference inventories.
            accepted_second_ring = {
                4: {(2, 0), (-2, 0), (0, 2), (0, -2)},
                6: {(-2, 0), (0, 2), (0, -2)},
                8: {(2, 0), (-2, 0), (0, 2)},
                10: {(2, 0), (-2, 0), (0, -2)},
            }
            expected_rejections: dict[int, dict[tuple[float, float], set[str]]] = {
                4: {(100, 100): {"battlefield_edge_crossed", "deployment_zone_violation"}},
                6: {
                    (2, 0): {"terrain_endpoint_illegal"},
                    (100, 100): {"battlefield_edge_crossed", "deployment_zone_violation"},
                },
                8: {
                    (0, -2): {"model_overlap"},
                    (100, 100): {"battlefield_edge_crossed", "deployment_zone_violation"},
                },
                10: {
                    (0, 1): {"battlefield_edge_crossed", "deployment_zone_violation"},
                    (0, 2): {"battlefield_edge_crossed", "deployment_zone_violation"},
                    (100, 100): {"battlefield_edge_crossed", "deployment_zone_violation"},
                },
            }
            reference_set = cast(dict[str, JsonValue], row["reference_set"])
            reference_results = cast(list[dict[str, JsonValue]], references["results"])
            reference_candidates = cast(list[dict[str, JsonValue]], reference_set["candidates"])
            offsets = cast(list[list[float]], reference_set["translations"])
            seed = cast(dict[str, JsonValue], reference_set["seed"])
            seed_proposal = cast(dict[str, JsonValue], seed["proposal"])
            index = cast(int, row["index"])
            observed_second_ring: set[tuple[float, float]] = set()
            for offset, candidate, result in zip(
                offsets, reference_candidates, reference_results, strict=True
            ):
                dx, dy = offset
                expected = cast(dict[str, JsonValue], json.loads(canonical_json(seed_proposal)))
                model_placements = cast(list[dict[str, JsonValue]], expected["model_placements"])
                for placement in model_placements:
                    pose = cast(dict[str, JsonValue], placement["pose"])
                    position = cast(dict[str, float], pose["position"])
                    position["x"] += dx
                    position["y"] += dy
                # Exact complete-proposal equality preserves model membership,
                # pairwise formation, Z/facing and context, not just a centroid.
                assert candidate["proposal"] == expected
                assert result["candidate_id"] == candidate["candidate_id"]
                if result["accepted"] and abs(dx) + abs(dy) == 2:
                    observed_second_ring.add((dx, dy))
                if (dx, dy) in expected_rejections[index]:
                    assert result["accepted"] is False
                    assert result["status"] == "invalid"
                    diagnostics = cast(dict[str, JsonValue], result["diagnostics"])
                    violations = cast(list[dict[str, JsonValue]], diagnostics["violations"])
                    assert {cast(str, item["violation_code"]) for item in violations} == (
                        expected_rejections[index][(dx, dy)]
                    )
                else:
                    assert result["accepted"] is True
            assert observed_second_ring == accepted_second_ring[index]
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
    candidates = DeploymentCandidateSet.generate(seed, context=context)
    assert cast(list[JsonValue], candidates.to_payload()["translations"])[5] == [2.0, 0.0]
    action = candidates.candidates[5].select(context)
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


def test_reference_suite_definition_is_pinned_and_closed() -> None:
    from warhammer40k_core.ai.deployment_reference_suite import (
        REFERENCE_SUITE_DEFINITION_HASH,
        DeploymentReferenceSuite,
        reference_case_steps,
        require_reference_suite_definition,
    )
    from warhammer40k_core.ai.player_policy import payload_digest

    definition = require_reference_suite_definition()
    assert (
        payload_digest(definition)
        == REFERENCE_SUITE_DEFINITION_HASH
        == ("7f8b9428acb03cfdce6b86396c520f487bc38369aacd90ce9d4d377dd9e8fa00")
    )
    with pytest.raises(TrainingAdmissionError, match="Unknown deployment reference case"):
        reference_case_steps("unregistered-order")
    with pytest.raises(TrainingAdmissionError, match="Measure the declared"):
        DeploymentReferenceSuite()
    with pytest.raises(TrainingAdmissionError, match="declaration drifted"):
        DeploymentReferenceSuite.from_payload({"definition": definition})
    predecessor = dict(definition)
    predecessor["suite_id"] = "deployment-order-diagonal-reference-suite-v1"
    predecessor["budget"] = (
        "all-finite-options-and-nine-generated-ten-reference-placements-no-truncation"
    )
    with pytest.raises(TrainingAdmissionError, match="declaration drifted"):
        DeploymentReferenceSuite.from_payload(
            {
                "schema_version": "deployment-reference-suite-v1",
                "definition": predecessor,
                "definition_hash": payload_digest(predecessor),
            }
        )


@pytest.mark.parametrize(
    "case_id",
    ["deep-scout-vehicle", "vehicle-scout-deep", "scout-deep-vehicle"],
)
def test_reference_case_ordinary_prefixes_geometry_and_feasible_gaps(case_id: str) -> None:
    from warhammer40k_core.ai.deployment_reference_suite import measure_reference_case

    payload = measure_reference_case(case_id)
    rows = cast(list[dict[str, JsonValue]], payload["rows"])
    assert [row["index"] for row in rows] == list(range(11))
    assert len(cast(list[JsonValue], payload["accepted_records"])) == 11
    totals = cast(dict[str, dict[str, int]], payload["totals"])
    assert totals["finite"]["accepted_count"] == totals["finite"]["legal_reference_count"] == 18
    assert totals["placement"]["generated_count"] == 52
    assert totals["placement"]["reference_attempts"] == 40
    assert totals["placement"]["unvalidated_count"] == 0
    assert totals["placement"]["accepted_count"] == 46
    assert totals["placement"]["legal_reference_count"] == 31
    assert totals["placement"]["covered_legal_reference_count"] == 31
    assert totals["placement"]["invalid_reference_probe_count"] == 9
    missing = 0
    violation_codes: set[str] = set()
    for row in rows:
        if row["kind"] != "placement":
            continue
        reference_set = cast(dict[str, JsonValue], row["reference_set"])
        candidates = cast(list[dict[str, JsonValue]], reference_set["candidates"])
        validation = cast(dict[str, JsonValue], row["reference_validation"])
        results = cast(list[dict[str, JsonValue]], validation["results"])
        assert validation["stop_reason"] == "complete"
        counts = cast(dict[str, JsonValue], row["counts"])
        missing_ids = cast(list[str], counts["missing_legal_reference_ids"])
        assert missing_ids == []
        generated = cast(dict[str, JsonValue], row["candidate_set"])
        generated_candidates = cast(list[dict[str, JsonValue]], generated["candidates"])
        generated_validation = cast(dict[str, JsonValue], row["validation"])
        generated_results = cast(list[dict[str, JsonValue]], generated_validation["results"])
        assert generated_validation["stop_reason"] == "complete"
        assert generated["generator_id"] == "actor-formation-xy-translations-v2"
        assert len(generated_candidates) == len(generated_results) == 13
        seed = cast(dict[str, JsonValue], reference_set["seed"])
        proposal = cast(dict[str, JsonValue], seed["proposal"])
        edge_codes = {"battlefield_edge_crossed", "deployment_zone_violation"}
        expected_rejections: dict[tuple[float, float], set[str]] = {(100, 100): edge_codes}
        if proposal["unit_instance_id"] == "army-alpha:deep-strike-unit":
            expected_rejections[(2, 0)] = {"terrain_endpoint_illegal"}
            if case_id != "deep-scout-vehicle":
                expected_rejections[(0, 2)] = {"model_overlap"}
        elif proposal["unit_instance_id"] == "army-alpha:scout-redeploy-unit":
            if case_id == "deep-scout-vehicle":
                expected_rejections[(0, -2)] = {"model_overlap"}
        elif proposal["unit_instance_id"] == "army-alpha:strategic-reserve-unit":
            expected_rejections.update(
                {(0, 2): edge_codes, (1, 1): edge_codes, (-1, 1): edge_codes}
            )
        for offset, candidate, result in zip(
            cast(list[list[float]], reference_set["translations"]), candidates, results, strict=True
        ):
            # Independent arithmetic proves exact whole-formation geometry:
            # all identity/context/Z/facing fields remain those of the seed.
            expected = cast(dict[str, JsonValue], json.loads(canonical_json(seed["proposal"])))
            for placement in cast(list[dict[str, JsonValue]], expected["model_placements"]):
                pose = cast(dict[str, JsonValue], placement["pose"])
                position = cast(dict[str, float], pose["position"])
                position["x"] += offset[0]
                position["y"] += offset[1]
            assert candidate["proposal"] == expected
            assert candidate["candidate_id"] == result["candidate_id"]
            assert result["accepted"] is (tuple(offset) not in expected_rejections)
            if result["accepted"]:
                assert candidate["candidate_id"] not in missing_ids
                assert candidate in generated_candidates
            missing += int(candidate["candidate_id"] in missing_ids)
            if abs(offset[0]) == abs(offset[1]) == 1:
                generated_index = next(
                    index
                    for index, item in enumerate(generated_candidates)
                    if item["candidate_id"] == candidate["candidate_id"]
                )
                assert generated_candidates[generated_index] == candidate
                assert generated_results[generated_index] == result
            if not result["accepted"]:
                diagnostics = cast(dict[str, JsonValue], result["diagnostics"])
                codes = {
                    cast(str, violation["violation_code"])
                    for violation in cast(list[dict[str, JsonValue]], diagnostics["violations"])
                }
                assert codes == expected_rejections[(offset[0], offset[1])]
                violation_codes.update(codes)
        assert results[0]["accepted"] is True
        assert results[-1]["accepted"] is False
    assert missing == (
        totals["placement"]["legal_reference_count"]
        - totals["placement"]["covered_legal_reference_count"]
    )
    assert {
        "terrain_endpoint_illegal",
        "battlefield_edge_crossed",
        "deployment_zone_violation",
    } <= (violation_codes)

    if case_id == "scout-deep-vehicle":
        from warhammer40k_core.ai.canonical_deployment import (
            _recipe_prefixes,  # pyright: ignore[reportPrivateUsage]
        )
        from warhammer40k_core.ai.deployment_reference_suite import (
            reference_case_steps,
            reproduce_reference_case,
        )

        session, recipe = reproduce_reference_case(case_id)
        prefixes = _recipe_prefixes(session, recipe, steps=reference_case_steps(case_id))
        prefix, context, _ = prefixes[8]
        row = rows[8]
        generated = cast(dict[str, JsonValue], row["candidate_set"])
        candidates = cast(list[dict[str, JsonValue]], generated["candidates"])
        diagonal_candidate = DeploymentPlacementCandidate.from_payload(
            candidates[9],
            context=context,
        )
        action = diagonal_candidate.select(context)
        before = canonical_json(session.to_persistence_payload())
        status = prefix.submit_viewer_parameterized_payload(
            viewer=ViewerContext.for_player(action.actor_id),
            request_id=action.request_id,
            payload=json.loads(cast(str, action.proposal_json)),
            result_id="suite-diagonal-positive",
        )
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        checkpoint = canonical_json(prefix.to_persistence_payload())
        restored = LocalGameSession.from_persistence_payload(json.loads(checkpoint))
        assert canonical_json(restored.to_persistence_payload()) == checkpoint
        assert (
            ReplayRunner.from_payload(
                restored.replay_artifact(artifact_id="suite-diagonal-positive")
            )
            .run()
            .reproduced_exactly
        )
        assert canonical_json(session.to_persistence_payload()) == before
        for actor in ("player-a", "player-b"):
            assert restored.view(viewer_player_id=actor) == prefix.view(viewer_player_id=actor)
            assert "definition_hash" not in canonical_json(restored.view(viewer_player_id=actor))
