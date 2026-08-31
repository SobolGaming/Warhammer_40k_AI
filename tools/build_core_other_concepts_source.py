# ruff: noqa: E501, RUF001
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = (
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "core_other_concepts_2026_08"
    / "artifacts"
    / "package.json"
)

SOURCE_URL = "https://www.40k.app/rules/06-other-concepts"
PROJECT_AUTHORITY_POLICY_ID = (
    "core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26"
)
REVIEW_AUDIT_ID = "40k-app-core-rules-2026-08-25"
REVIEW_AUDIT_ROW_ID = "category:06"
REVIEW_AUDIT_OBSERVATION_SHA256 = "646b405724eb9f1a7f441fed3b3af0cae62925c72fb4b069fc17118fbab13b73"
VISIBILITY_OBSERVED_AT = "2026-08-31T11:41:03-04:00"
MORTAL_WOUNDS_OBSERVED_AT = "2026-08-31T13:01:46-04:00"

VISIBILITY_SOURCE_TEXT = """VISIBILITY
Line of sight is used to determine visibility between models. For an observing model to have line of sight, it must be possible to draw an imaginary straight line, 1 mm wide, from any part of that model to any part of the model being observed. This line is the line of sight. While doing so, other models in the observing model’s unit and in the observed model’s unit are ignored. Other models and units can be either visible or fully visible to the observing model, as shown in the example. Note that terrain applies additional rules to visibility (13.07)."""

MORTAL_WOUNDS_SOURCE_TEXT = """MORTAL WOUNDS
Some attacks or rules inflict mortal wounds on units. Each time a unit suffers one or more mortal wounds, its controlling player must resolve the following sequence for each of those mortal wounds, until either all of them have been inflicted or that unit is destroyed:
1. Select Model: Select one model in that unit by following the first instruction below that applies:
- If a non‑CHARACTER model in that unit has lost one or more wounds, you must select that model.
- Otherwise, if that unit contains one or more non‑CHARACTER models, you must select one of those models.
- Otherwise, if one or more CHARACTER models in that unit have lost one or more wounds, you must select one of those models.
- Otherwise, you must select one CHARACTER model in that unit.
2. Resolve Damage: The selected model loses 1 wound. If this reduces that model’s remaining wounds to 0, it is destroyed."""

VISIBILITY_RUNTIME_CONSUMER_IDS = [
    "warhammer40k_core.geometry.visibility:TerrainVisibilityContext.resolve_line_of_sight",
    "warhammer40k_core.geometry.visibility_corridor:line_of_sight_corridor_intersects_model",
    "warhammer40k_core.geometry.visibility_corridor:line_of_sight_corridor_intersects_polygon",
    "warhammer40k_core.geometry.visibility_corridor:line_of_sight_corridor_intersects_polygon_union",
    "warhammer40k_core.geometry.visibility_corridor:line_of_sight_corridor_intersects_terrain_volume",
    "warhammer40k_core.engine.shooting_targets:shooting_target_candidates_for_unit",
    "warhammer40k_core.engine.shooting_targets:unit_has_line_of_sight_to_target",
]

MORTAL_WOUNDS_RUNTIME_CONSUMER_IDS = [
    "warhammer40k_core.engine.damage_allocation:mortal_wound_priority_model_ids",
    "warhammer40k_core.engine.damage_allocation:build_mortal_wound_model_request",
    "warhammer40k_core.engine.damage_allocation:continue_mortal_wound_application",
    "warhammer40k_core.engine.damage_allocation:resolve_mortal_wound_model_decision",
    "warhammer40k_core.engine.lifecycle:GameLifecycle.submit_decision",
]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _sha256_payload(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _evidence_observation_sha256(evidence: dict[str, object]) -> str:
    observation = copy.deepcopy(evidence)
    observation["observation_sha256"] = ""
    observation["load_support_status"] = "not_loaded"
    observation["semantic_execution_status"] = "not_certified"
    observation["runtime_consumer_ids"] = []
    return _sha256_payload(observation)


def _evidence_rows(
    *,
    rule_id: str,
    rule_source_id: str,
    section_id: str,
    section_heading: str,
    observed_at: str,
    transcription_sha256: str,
    runtime_consumer_ids: list[str],
) -> list[dict[str, object]]:
    shared: dict[str, object] = {
        "rule_source_id": rule_source_id,
        "app_version": None,
        "app_build": None,
        "capture_artifact_path": None,
        "capture_sha256": None,
        "transcription_sha256": transcription_sha256,
        "official_corroborating_source_ids": [],
        "observation_sha256": "",
        "load_support_status": "loaded",
        "semantic_execution_status": "executable_engine_runtime",
        "runtime_consumer_ids": runtime_consumer_ids,
    }
    review = {
        **shared,
        "evidence_id": f"core-v2-other-concepts-source-review:{rule_id}",
        "evidence_kind": "project_reviewed_app_transcription",
        "authority": "unverified_transcription_only",
        "project_authority_policy_id": None,
        "review_audit_id": None,
        "review_audit_row_id": None,
        "review_audit_source_observation_sha256": None,
        "provider_name": "CORE V2 Source Review",
        "source_title": f"Reviewed transcription of {section_id} {section_heading.title()}",
        "source_platform": "Repository",
        "source_url": None,
        "observed_at": None,
        "verification_status": "unverified",
        "provider_non_affiliation_recorded": False,
    }
    review["observation_sha256"] = _evidence_observation_sha256(review)
    mirror = {
        **shared,
        "evidence_id": f"40k-app-other-concepts-2026-08-31:{rule_id}",
        "evidence_kind": "third_party_mirror",
        "authority": "project_authoritative_app_mirror",
        "project_authority_policy_id": PROJECT_AUTHORITY_POLICY_ID,
        "review_audit_id": REVIEW_AUDIT_ID,
        "review_audit_row_id": REVIEW_AUDIT_ROW_ID,
        "review_audit_source_observation_sha256": REVIEW_AUDIT_OBSERVATION_SHA256,
        "provider_name": "40k.app",
        "source_title": f"40k.app Core Rules {section_id} {section_heading.title()}",
        "source_platform": "Web",
        "source_url": SOURCE_URL,
        "observed_at": observed_at,
        "verification_status": "authoritative_app_mirror",
        "provider_non_affiliation_recorded": True,
    }
    mirror["observation_sha256"] = _evidence_observation_sha256(mirror)
    return [review, mirror]


def build_payload() -> dict[str, object]:
    visibility_transcription_sha256 = _sha256_text(VISIBILITY_SOURCE_TEXT)
    mortal_wounds_transcription_sha256 = _sha256_text(MORTAL_WOUNDS_SOURCE_TEXT)
    payload: dict[str, object] = {
        "artifact_schema": "core-v2-other-concepts-source-v1",
        "source_package_id": "gw-11e-core-other-concepts",
        "source_version": "40k-app-other-concepts-observed-2026-08-31",
        "source_document": {
            "document_id": "40k-app-other-concepts-2026-08-31",
            "source_title": "40k.app Core Rules Other Concepts",
            "source_url": SOURCE_URL,
            "observed_at": MORTAL_WOUNDS_OBSERVED_AT,
            "project_authority_policy_id": PROJECT_AUTHORITY_POLICY_ID,
        },
        "rules": [
            {
                "rule_id": "visibility",
                "source_id": "gw-11e-core-rules:other-concepts:visibility",
                "section_id": "06.01",
                "section_heading": "VISIBILITY",
                "source_text": VISIBILITY_SOURCE_TEXT,
                "transcription_sha256": visibility_transcription_sha256,
                "load_support_status": "loaded",
                "semantic_execution_status": "executable_engine_runtime",
                "runtime_consumer_ids": VISIBILITY_RUNTIME_CONSUMER_IDS,
            },
            {
                "rule_id": "mortal-wounds",
                "source_id": "gw-11e-core-rules:other-concepts:mortal-wounds",
                "section_id": "06.02",
                "section_heading": "MORTAL WOUNDS",
                "source_text": MORTAL_WOUNDS_SOURCE_TEXT,
                "transcription_sha256": mortal_wounds_transcription_sha256,
                "load_support_status": "loaded",
                "semantic_execution_status": "executable_engine_runtime",
                "runtime_consumer_ids": MORTAL_WOUNDS_RUNTIME_CONSUMER_IDS,
            },
        ],
        "evidence": [
            *_evidence_rows(
                rule_id="visibility",
                rule_source_id="gw-11e-core-rules:other-concepts:visibility",
                section_id="06.01",
                section_heading="VISIBILITY",
                observed_at=VISIBILITY_OBSERVED_AT,
                transcription_sha256=visibility_transcription_sha256,
                runtime_consumer_ids=VISIBILITY_RUNTIME_CONSUMER_IDS,
            ),
            *_evidence_rows(
                rule_id="mortal-wounds",
                rule_source_id="gw-11e-core-rules:other-concepts:mortal-wounds",
                section_id="06.02",
                section_heading="MORTAL WOUNDS",
                observed_at=MORTAL_WOUNDS_OBSERVED_AT,
                transcription_sha256=mortal_wounds_transcription_sha256,
                runtime_consumer_ids=MORTAL_WOUNDS_RUNTIME_CONSUMER_IDS,
            ),
        ],
        "package_hash": "",
    }
    payload["package_hash"] = _sha256_payload(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the reviewed 06.01-06.02 Other Concepts source artifact."
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(build_payload(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not ARTIFACT_PATH.is_file() or ARTIFACT_PATH.read_text(encoding="utf-8") != rendered:
            raise SystemExit("Other Concepts source artifact is stale.")
        return 0
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
