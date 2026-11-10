"""Bounded operator coverage of the frozen canonical deployment prefix.

References are independently declared feasible choices, not tactical labels.
Each attempted alternative starts on a fresh fork of the exact canonical prefix.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import cast

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.canonical_deployment import (
    CanonicalDeploymentAdmission,
    canonical_deployment_prefixes,
    reproduce_canonical_deployment,
)
from warhammer40k_core.ai.deployment_candidate_search import (
    DEFAULT_TRANSLATIONS,
    DeploymentCandidateSet,
)
from warhammer40k_core.ai.deployment_candidate_validation import ValidatedDeploymentCandidates
from warhammer40k_core.ai.deployment_candidates import DeploymentPlacementCandidate
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyAction, payload_digest
from warhammer40k_core.ai.training_admission import TrainingAdmissionError
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatusKind

CANONICAL_COVERAGE_SCHEMA = "canonical-deployment-coverage-v1"
# Declared independently of DEFAULT_TRANSLATIONS: these are exact formation
# translations in inches, not an exhaustive region or a tactical reference.
REFERENCE_TRANSLATIONS = (
    (0.0, 0.0),
    (1.0, 0.0),
    (-1.0, 0.0),
    (0.0, 1.0),
    (0.0, -1.0),
    (2.0, 0.0),
    (-2.0, 0.0),
    (0.0, 2.0),
    (0.0, -2.0),
    (100.0, 100.0),
)
FINITE_ATTEMPT_LIMIT = 512


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TrainingAdmissionError(message)


def _finite_results(
    session: LocalGameSession, context: PlayerDecisionContext, reference_ids: tuple[str, ...]
) -> list[dict[str, JsonValue]]:
    results: list[dict[str, JsonValue]] = []
    for candidate_id in reference_ids:
        action = context.select_option(candidate_id)
        probe = session.fork()
        before_count = probe.decision_record_count()
        status = probe.submit_viewer_option(
            viewer=ViewerContext.for_player(action.actor_id),
            request_id=action.request_id,
            option_id=candidate_id,
            result_id="canonical-finite-probe:"
            + payload_digest([context.observation_hash, candidate_id]),
        )
        _require(
            status.status_kind
            in (
                LifecycleStatusKind.ADVANCED,
                LifecycleStatusKind.WAITING_FOR_DECISION,
                LifecycleStatusKind.TERMINAL,
                LifecycleStatusKind.INVALID,
            ),
            "Canonical finite probe stopped with an unsupported engine status.",
        )
        accepted = status.status_kind is not LifecycleStatusKind.INVALID
        _require(
            not accepted or probe.decision_record_count() > before_count,
            "Canonical finite probe did not record its accepted choice.",
        )
        results.append(
            {
                "candidate_id": candidate_id,
                "accepted": accepted,
                "status": status.status_kind.value,
                "message": status.message,
                "diagnostics": status.payload,
            }
        )
    return results


def _coverage(
    generated_ids: list[str],
    results: list[dict[str, JsonValue]],
    reference_results: list[dict[str, JsonValue]],
) -> dict[str, JsonValue]:
    accepted = [cast(str, row["candidate_id"]) for row in results if row["accepted"]]
    references = [cast(str, row["candidate_id"]) for row in reference_results if row["accepted"]]
    covered = [candidate_id for candidate_id in references if candidate_id in accepted]
    return {
        "generated_count": len(generated_ids),
        "validation_attempts": len(results),
        "accepted_count": len(accepted),
        "rejected_count": len(results) - len(accepted),
        "unvalidated_count": len(generated_ids) - len(results),
        "reference_attempts": len(reference_results),
        "legal_reference_count": len(references),
        "invalid_reference_probe_count": len(reference_results) - len(references),
        "covered_legal_reference_count": len(covered),
        "missing_legal_reference_ids": [
            candidate_id for candidate_id in references if candidate_id not in accepted
        ],
    }


def _placement_row(
    session: LocalGameSession, context: PlayerDecisionContext, action: PolicyAction
) -> dict[str, JsonValue]:
    seed = DeploymentPlacementCandidate.from_action(action, context=context)
    generated = DeploymentCandidateSet.generate(seed, context=context)
    validated = ValidatedDeploymentCandidates.validate(
        generated,
        context=context,
        session=session,
        validation_budget=len(DEFAULT_TRANSLATIONS),
        accepted_limit=16,
    )
    # References are generated from their declared geometry, never selected from
    # the generated set or its acceptance list. Reuse the same translation owner.
    reference_set = DeploymentCandidateSet.generate(
        seed, context=context, translations=REFERENCE_TRANSLATIONS, raw_budget=10
    )
    reference_validated = ValidatedDeploymentCandidates.validate(
        reference_set, context=context, session=session, validation_budget=10, accepted_limit=16
    )
    results = cast(list[dict[str, JsonValue]], validated.to_payload()["results"])
    reference_results = cast(
        list[dict[str, JsonValue]], reference_validated.to_payload()["results"]
    )
    generated_ids = [candidate.candidate_id for candidate in generated.candidates]
    _require(
        validated.to_payload()["stop_reason"] == "complete"
        and reference_validated.to_payload()["stop_reason"] == "complete"
        and seed.candidate_id in validated.accepted_ids
        and seed.candidate_id in reference_validated.accepted_ids,
        "Canonical placement coverage did not complete or lost its recipe positive control.",
    )
    return {
        "kind": "placement",
        "recipe_candidate_id": seed.candidate_id,
        "candidate_set": cast(JsonValue, generated.to_payload()),
        "validation": validated.to_payload(),
        "reference_set": reference_set.to_payload(),
        "reference_validation": reference_validated.to_payload(),
        "counts": _coverage(generated_ids, results, reference_results),
    }


@dataclass(frozen=True, slots=True, init=False)
class CanonicalDeploymentCoverage:
    """Closed reproducible evidence for one fixed experiment, never actor input."""

    _payload_json: str

    def __init__(self) -> None:
        raise TrainingAdmissionError("Measure canonical coverage through its ordinary session.")

    @classmethod
    def measure(cls, *, session: LocalGameSession) -> CanonicalDeploymentCoverage:
        admission = CanonicalDeploymentAdmission.from_session(session)
        before = canonical_json(session.to_persistence_payload())
        reproduced, report = reproduce_canonical_deployment()
        prefixes = canonical_deployment_prefixes(reproduced, report)
        rows: list[dict[str, JsonValue]] = []
        finite_attempts = 0
        for index, (prefix, context, action) in enumerate(prefixes):
            checkpoint_hash = payload_digest(prefix.to_persistence_payload())
            row: dict[str, JsonValue]
            if action.option_id is None:
                row = _placement_row(prefix, context, action)
            else:
                candidates = FiniteCandidateSet.from_context(context)
                reference_ids = tuple(option["option_id"] for option in context.request["options"])
                finite_attempts += len(reference_ids)
                _require(
                    finite_attempts <= FINITE_ATTEMPT_LIMIT,
                    "Canonical finite coverage exceeds its explicit total attempt limit.",
                )
                reference_results = _finite_results(prefix, context, reference_ids)
                results = [
                    result
                    for result in reference_results
                    if result["candidate_id"] in candidates.candidate_ids
                ]
                _require(
                    any(
                        result["candidate_id"] == action.option_id and result["accepted"]
                        for result in results
                    ),
                    "Canonical finite coverage lost its recipe positive control.",
                )
                # Finite reference universe is the pending engine option inventory;
                # it is exact only at this prefix, not over alternate continuations.
                row = {
                    "kind": "finite",
                    "recipe_candidate_id": action.option_id,
                    "candidate_set": cast(JsonValue, candidates.to_payload()),
                    "results": cast(JsonValue, results),
                    "reference_options": cast(JsonValue, context.request["options"]),
                    "reference_results": cast(JsonValue, reference_results),
                    "counts": _coverage(list(candidates.candidate_ids), results, reference_results),
                }
            _require(
                payload_digest(prefix.to_persistence_payload()) == checkpoint_hash,
                "Canonical coverage mutated a live prefix.",
            )
            row.update(
                {
                    "index": index,
                    "route": validate_json_value(asdict(context.route)),
                    "observation_hash": context.observation_hash,
                    "checkpoint_hash": checkpoint_hash,
                    "choice_seed": context.choice_seed,
                }
            )
            rows.append(row)
        totals: dict[str, JsonValue] = {}
        for kind in ("finite", "placement"):
            selected = [
                cast(dict[str, JsonValue], row["counts"]) for row in rows if row["kind"] == kind
            ]
            totals[kind] = {
                "decision_occurrences": len(selected),
                **{
                    key: sum(cast(int, counts[key]) for counts in selected)
                    for key in (
                        "generated_count",
                        "validation_attempts",
                        "accepted_count",
                        "rejected_count",
                        "unvalidated_count",
                        "reference_attempts",
                        "legal_reference_count",
                        "invalid_reference_probe_count",
                        "covered_legal_reference_count",
                    )
                },
            }
        _require(
            canonical_json(session.to_persistence_payload()) == before,
            "Canonical coverage mutated the supplied endpoint.",
        )
        payload = {
            "schema_version": CANONICAL_COVERAGE_SCHEMA,
            "admission": admission.to_payload(),
            "admission_hash": admission.content_hash,
            "reference_definition": {
                "finite": "all-current-engine-enumerated-options-at-each-canonical-prefix",
                "placement": "independent-fixed-whole-formation-xy-offsets-in-inches-v1",
                "translations": [list(offset) for offset in REFERENCE_TRANSLATIONS],
                "denominator": "independently-engine-accepted-reference-candidates-per-occurrence",
                "numerator": "reference-candidates-also-generated-and-engine-accepted",
                "invalid_probes": "reported-separately-excluded-from-legal-reference-denominator",
                "usefulness": "distinct-feasible-choices-only-no-tactical-value-or-outcome-label",
            },
            "budgets": {
                "finite_total_attempt_limit": FINITE_ATTEMPT_LIMIT,
                "placement_generated_per_occurrence": len(DEFAULT_TRANSLATIONS),
                "placement_reference_per_occurrence": len(REFERENCE_TRANSLATIONS),
                "validation": "all-supplied-candidates-no-truncation",
            },
            "rows": rows,
            "totals": totals,
            "scope": "eleven-canonical-prefix-occurrences-seven-routes-four-units-fourteen-models",
            "stop_reason": "before-redeploy",
            "pending_stage2_evidence": [
                "component-costs",
                "broader-useful-reference-qualification",
            ],
            "unmeasured": [
                "alternate-prefix-continuations-and-deployment-orders",
                "rotations-reshaping-other-distances-and-continuous-legal-placement-space",
                "tactical-screen-preserve-follow-through-or-ranking-quality",
                "redeploy-scouts-battle-scoring-and-full-game",
            ],
        }
        result = object.__new__(cls)
        object.__setattr__(result, "_payload_json", canonical_json(validate_json_value(payload)))
        return result

    @classmethod
    def from_payload(
        cls, payload: object, *, session: LocalGameSession
    ) -> CanonicalDeploymentCoverage:
        expected = cls.measure(session=session)
        _require(
            canonical_json(validate_json_value(payload)) == expected._payload_json,
            "Canonical deployment coverage payload drifted from reproduction.",
        )
        return expected

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._payload_json))

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())
