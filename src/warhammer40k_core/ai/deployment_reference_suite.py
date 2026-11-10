"""Predeclared deployment-order/diagonal references, exclusively operator evidence."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import cast

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.canonical_deployment import (
    _STEPS,  # pyright: ignore[reportPrivateUsage]
    CANONICAL_DEPLOYMENT_CONFIG_HASH,
    CanonicalDeploymentAdmission,
    _recipe_prefixes,  # pyright: ignore[reportPrivateUsage]
    _reproduce_recipe,  # pyright: ignore[reportPrivateUsage]
    _Step,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.ai.canonical_deployment_coverage import (
    _measure_prefixes,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.ai.player_policy import payload_digest
from warhammer40k_core.ai.runner import RunReport
from warhammer40k_core.ai.training_admission import TrainingAdmissionError, VerifiedEpisodeOrigin
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value

REFERENCE_SUITE_ID = "deployment-order-diagonal-reference-suite-v2"
REFERENCE_SUITE_SCHEMA = "deployment-reference-suite-v1"
# Fixed before engine measurement. Reordering only complete select/place pairs
# changes occupied-prefix geometry without editing a lifecycle or its history.
REFERENCE_CASES = (
    ("deep-scout-vehicle", (5, 7, 9)),
    ("vehicle-scout-deep", (9, 7, 5)),
    ("scout-deep-vehicle", (7, 5, 9)),
)
# Independently declared geometry: neither sliced from DEFAULT_TRANSLATIONS nor
# filtered by measured acceptance. Diagonals deliberately probe its known shape.
SUITE_REFERENCE_TRANSLATIONS = (
    (0.0, 0.0),
    (2.0, 0.0),
    (-2.0, 0.0),
    (0.0, 2.0),
    (0.0, -2.0),
    (1.0, 1.0),
    (-1.0, 1.0),
    (1.0, -1.0),
    (-1.0, -1.0),
    (100.0, 100.0),
)
# V2 changes only suite identity and generated budget; the historical v1 pin and
# evidence remain under docs/performance/deployment-reference-suite-v1. Set before
# measuring v2; definition drift requires deliberate versioning.
REFERENCE_SUITE_DEFINITION_HASH = "7f8b9428acb03cfdce6b86396c520f487bc38369aacd90ce9d4d377dd9e8fa00"


def reference_case_steps(case_id: str) -> tuple[_Step, ...]:
    for identity, order in REFERENCE_CASES:
        if identity == case_id:
            return _STEPS[:5] + tuple(_STEPS[index + part] for index in order for part in (0, 1))
    raise TrainingAdmissionError("Unknown deployment reference case.")


def reference_suite_definition() -> dict[str, JsonValue]:
    definition = {
        "suite_id": REFERENCE_SUITE_ID,
        "configuration_hash": CANONICAL_DEPLOYMENT_CONFIG_HASH,
        "policy_seed": 7,
        "cases": [
            {
                "case_id": case_id,
                "recipe": [asdict(step) for step in reference_case_steps(case_id)],
            }
            for case_id, _ in REFERENCE_CASES
        ],
        "translations": [list(offset) for offset in SUITE_REFERENCE_TRANSLATIONS],
        "finite": "all-current-engine-enumerated-options-at-each-declared-prefix",
        "denominator": "engine-accepted-references-per-case-and-occurrence",
        "numerator": "references-also-generated-and-engine-accepted-at-that-occurrence",
        "invalid_probes": "reported-separately-excluded-from-legal-denominator",
        "required_controls": "all-three-complete-recipes-and-every-placement-seed-accepted",
        "budget": (
            "all-finite-options-and-thirteen-generated-ten-reference-placements-no-truncation"
        ),
        "endpoint": "before-redeploy",
        "intended_diversity": [
            "three-of-six-player-a-deployment-orders",
            "different-already-occupied-friendly-unit-prefixes",
            "cardinal-and-diagonal-whole-formation-translations",
            "one-three-five-model-formations-with-32mm-and-120mm-bases",
            "terrain-friendly-overlap-battlefield-edge-and-deployment-zone-constraints",
        ],
        "exclusions": [
            "other-orders-configurations-layouts-rosters-seeds-and-opponent-responses",
            "rotations-reshaping-other-distances-and-continuous-legal-placement-space",
            "redeploy-scouts-reserve-arrival-attachments-transports-battle-and-scoring",
            "tactical-utility-ranking-learning-full-game-or-representative-coverage",
        ],
        "qualification": "finite-feasibility-reference-suite-not-tactical-reference",
    }
    return cast(dict[str, JsonValue], validate_json_value(definition))


def require_reference_suite_definition() -> dict[str, JsonValue]:
    definition = reference_suite_definition()
    if payload_digest(definition) != REFERENCE_SUITE_DEFINITION_HASH:
        raise TrainingAdmissionError("Deployment reference suite definition drifted.")
    return definition


def reproduce_reference_case(case_id: str) -> tuple[LocalGameSession, RunReport]:
    require_reference_suite_definition()
    return _reproduce_recipe(
        reference_case_steps(case_id), recipe_id=REFERENCE_SUITE_ID + ":" + case_id
    )


def measure_reference_case(case_id: str) -> dict[str, JsonValue]:
    session, report = reproduce_reference_case(case_id)
    before = canonical_json(session.to_persistence_payload())
    origin = VerifiedEpisodeOrigin.from_session(session, config=session.lifecycle.config)
    prefixes = _recipe_prefixes(session, report, steps=reference_case_steps(case_id))
    rows, totals = _measure_prefixes(prefixes, reference_translations=SUITE_REFERENCE_TRANSLATIONS)
    if canonical_json(session.to_persistence_payload()) != before:
        raise TrainingAdmissionError("Deployment reference measurement changed its endpoint.")
    payload = {
        "case_id": case_id,
        "origin": origin.to_payload(),
        "accepted_records": [
            record.to_payload() for record in session.lifecycle.decision_controller.records
        ],
        "rows": rows,
        "totals": totals,
        "endpoint_checkpoint_hash": payload_digest(session.to_persistence_payload()),
        "replay_artifact_hash": payload_digest(
            session.replay_artifact(artifact_id=REFERENCE_SUITE_ID + ":" + case_id)
        ),
    }

    return cast(dict[str, JsonValue], validate_json_value(payload))


@dataclass(frozen=True, slots=True, init=False)
class DeploymentReferenceSuite:
    """Closed reproducible suite receipt; no actor-view or training extension."""

    _payload_json: str

    def __init__(self) -> None:
        raise TrainingAdmissionError("Measure the declared deployment reference suite.")

    @classmethod
    def measure(cls) -> DeploymentReferenceSuite:
        definition = require_reference_suite_definition()
        # Preserve the original canonical admission and its source limitations.
        canonical, _ = _reproduce_recipe(_STEPS, recipe_id="canonical-deployment-v1")
        admission = CanonicalDeploymentAdmission.from_session(canonical)
        cases = [measure_reference_case(case_id) for case_id, _ in REFERENCE_CASES]
        totals: dict[str, JsonValue] = {}
        for kind in ("finite", "placement"):
            selected = [
                cast(dict[str, int], cast(dict[str, JsonValue], case["totals"])[kind])
                for case in cases
            ]
            totals[kind] = {key: sum(row[key] for row in selected) for key in selected[0]}
        payload = {
            "schema_version": REFERENCE_SUITE_SCHEMA,
            "definition": definition,
            "definition_hash": REFERENCE_SUITE_DEFINITION_HASH,
            "canonical_admission": admission.to_payload(),
            "cases": cases,
            "totals": totals,
            "aggregation": "occurrence-weighted-not-unique-geometry-or-independent-samples",
            "pending_stage2_evidence": [
                "tactical-usefulness-reference-qualification",
                "broader-workload-qualification",
            ],
            "generator_gap_disposition": "report-feasible-misses-for-separately-scoped-follow-up",
        }
        result = object.__new__(cls)
        object.__setattr__(result, "_payload_json", canonical_json(validate_json_value(payload)))
        return result

    @classmethod
    def from_payload(cls, payload: object) -> DeploymentReferenceSuite:
        if not isinstance(payload, dict):
            raise TrainingAdmissionError("Deployment reference suite declaration drifted.")
        value = cast(dict[str, object], payload)
        if (
            value.get("schema_version") != REFERENCE_SUITE_SCHEMA
            or value.get("definition") != require_reference_suite_definition()
            or value.get("definition_hash") != REFERENCE_SUITE_DEFINITION_HASH
        ):
            raise TrainingAdmissionError("Deployment reference suite declaration drifted.")
        expected = cls.measure()
        if canonical_json(validate_json_value(value)) != expected._payload_json:
            raise TrainingAdmissionError("Deployment reference suite payload drifted.")
        return expected

    def to_payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self._payload_json))

    @property
    def content_hash(self) -> str:
        return payload_digest(self.to_payload())
