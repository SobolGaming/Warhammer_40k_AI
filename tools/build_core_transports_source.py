# ruff: noqa: E501,RUF001
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
    / "core_transports_2026_09"
    / "artifacts"
    / "package.json"
)

EMERGENCY_SOURCE_URL = "https://www.40k.app/rules/18-transports"
EMERGENCY_OBSERVED_AT = "2026-09-01T18:46:11-04:00"
EMERGENCY_PROJECT_AUTHORITY_POLICY_ID = (
    "core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26"
)
EMERGENCY_REVIEW_AUDIT_ID = "40k-app-core-rules-2026-08-25"
EMERGENCY_REVIEW_AUDIT_ROW_ID = "category:18"
EMERGENCY_REVIEW_AUDIT_OBSERVATION_SHA256 = (
    "d9a06d3c5b350f66bad9e4b89f62242fd0f0b4c54579ea3ad6bbf2c2674b8d0e"
)

ASSAULT_SOURCE_URL = "https://game-datamissions.com/11th/rules/changelog"
ASSAULT_APP_VERSION = "931"
ASSAULT_OBSERVED_AT = "2026-09-02T12:30:09-04:00"
ASSAULT_PROJECT_AUTHORITY_POLICY_ID = (
    "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
)
ASSAULT_REVIEW_AUDIT_ID = "core-rules-maintained-app-mirrors-2026-09-02"
ASSAULT_REVIEW_AUDIT_ROW_ID = "game-datamissions-core-rules-data-931"
ASSAULT_REVIEW_AUDIT_OBSERVATION_SHA256 = (
    "1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668"
)

EMERGENCY_SOURCE_TEXT = """EMERGENCY DISEMBARK MOVE
When eligible: Your unit is embarked within a TRANSPORT model that was just destroyed.
Maximum distance: SET-UP DISTANCE: 6\"
Effect: Your unit is set up as described in Set Up (03.02)
Before moving: Make a hazard roll for each model in your unit (06.03)
While moving: Set up each model in your unit:
- Wholly within the set-up distance of that TRANSPORT, and as close as possible to that TRANSPORT.
- Or: If the above is not possible while remaining unengaged, set up that model wholly within the set-up distance of that TRANSPORT, as close as possible to that TRANSPORT, and engaged.
Each model that still cannot be set up is destroyed.
After moving: Your unit is battle-shocked and, until the end of the turn, it is not eligible to declare a charge."""

ASSAULT_SOURCE_TEXT = """ASSAULT DISEMBARK MOVE
Your unit is set up as described in Set Up (Core Rules, 03.02). As stated in the rule allowing this move type, if all of the following apply to your unit: Embarked within a TRANSPORT model that is on the battlefield. Did not embark within that TRANSPORT this phase. That TRANSPORT has not made an advance/fall‑back move this phase. Set up each model in your unit wholly within the set‑up distance of that TRANSPORT. 3\" 18.06"""

EMERGENCY_RUNTIME_CONSUMER_IDS = [
    "warhammer40k_core.engine.attack_sequence_destroyed_transport:_continue_pending_destroyed_transport_disembark",
    "warhammer40k_core.engine.attack_sequence_destroyed_transport:_request_destroyed_transport_disembark_placement",
    "warhammer40k_core.engine.emergency_disembark:apply_transport_hazard_mortal_wounds_service",
    "warhammer40k_core.engine.emergency_disembark:resolve_destroyed_transport_hazard_rolls_service",
]

ASSAULT_RUNTIME_CONSUMER_IDS = [
    "warhammer40k_core.engine.assault_disembark:assault_disembark_restriction_overrides",
    "warhammer40k_core.engine.phases.charge:_charge_unit_ineligibility_reason",
    "warhammer40k_core.engine.phases.movement_transports:_disembark_candidate_for_movement_unit",
    "warhammer40k_core.engine.transport_disembark_state:DisembarkedUnitState.for_mode",
    "warhammer40k_core.engine.transports:resolve_disembark",
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
    rule_source_id: str,
    rule_slug: str,
    section_id: str,
    section_heading: str,
    transcription_sha256: str,
    runtime_consumer_ids: list[str],
    provider_name: str,
    source_url: str,
    observed_at: str | None,
    app_version: str | None,
    project_authority_policy_id: str,
    review_audit_id: str,
    review_audit_row_id: str,
    review_audit_observation_sha256: str,
    mirror_evidence_id: str,
) -> list[dict[str, object]]:
    shared: dict[str, object] = {
        "rule_source_id": rule_source_id,
        "app_version": app_version,
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
        "app_version": None,
        "evidence_id": f"core-v2-transports-source-review:{rule_slug}",
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
        "evidence_id": mirror_evidence_id,
        "evidence_kind": "third_party_mirror",
        "authority": "project_authoritative_app_mirror",
        "project_authority_policy_id": project_authority_policy_id,
        "review_audit_id": review_audit_id,
        "review_audit_row_id": review_audit_row_id,
        "review_audit_source_observation_sha256": review_audit_observation_sha256,
        "provider_name": provider_name,
        "source_title": f"{provider_name} Core Rules {section_id} {section_heading.title()}",
        "source_platform": "Web",
        "source_url": source_url,
        "observed_at": observed_at,
        "verification_status": "authoritative_app_mirror",
        "provider_non_affiliation_recorded": True,
    }
    mirror["observation_sha256"] = _evidence_observation_sha256(mirror)
    return [review, mirror]


def build_payload() -> dict[str, object]:
    emergency_transcription_sha256 = _sha256_text(EMERGENCY_SOURCE_TEXT)
    assault_transcription_sha256 = _sha256_text(ASSAULT_SOURCE_TEXT)
    payload: dict[str, object] = {
        "artifact_schema": "core-v2-transports-source-v1",
        "source_package_id": "gw-11e-core-transports",
        "source_version": "reviewed-transports-observed-2026-09-02",
        "source_documents": [
            {
                "document_id": "40k-app-transports-2026-09-01",
                "source_title": "40k.app Core Rules Transports",
                "source_url": EMERGENCY_SOURCE_URL,
                "observed_at": EMERGENCY_OBSERVED_AT,
                "app_version": None,
                "project_authority_policy_id": EMERGENCY_PROJECT_AUTHORITY_POLICY_ID,
                "rule_source_ids": ["gw-11e-core-rules:transports:emergency-disembark-move"],
            },
            {
                "document_id": "game-datamissions-core-rules-data-931",
                "source_title": "Game Datamissions Core Rules Data Changelog v931",
                "source_url": ASSAULT_SOURCE_URL,
                "observed_at": ASSAULT_OBSERVED_AT,
                "app_version": ASSAULT_APP_VERSION,
                "project_authority_policy_id": ASSAULT_PROJECT_AUTHORITY_POLICY_ID,
                "rule_source_ids": ["gw-11e-core-rules:transports:assault-disembark-move"],
            },
        ],
        "rules": [
            {
                "rule_id": "emergency-disembark-move",
                "source_id": "gw-11e-core-rules:transports:emergency-disembark-move",
                "section_id": "18.05",
                "section_heading": "EMERGENCY DISEMBARK MOVE",
                "source_text": EMERGENCY_SOURCE_TEXT,
                "transcription_sha256": emergency_transcription_sha256,
                "load_support_status": "loaded",
                "semantic_execution_status": "executable_engine_runtime",
                "runtime_consumer_ids": EMERGENCY_RUNTIME_CONSUMER_IDS,
            },
            {
                "rule_id": "assault-disembark-move",
                "source_id": "gw-11e-core-rules:transports:assault-disembark-move",
                "section_id": "18.06",
                "section_heading": "ASSAULT DISEMBARK MOVE",
                "source_text": ASSAULT_SOURCE_TEXT,
                "transcription_sha256": assault_transcription_sha256,
                "load_support_status": "loaded",
                "semantic_execution_status": "executable_engine_runtime",
                "runtime_consumer_ids": ASSAULT_RUNTIME_CONSUMER_IDS,
            },
        ],
        "evidence": [
            *_evidence_rows(
                rule_source_id="gw-11e-core-rules:transports:emergency-disembark-move",
                rule_slug="emergency-disembark-move",
                section_id="18.05",
                section_heading="EMERGENCY DISEMBARK MOVE",
                transcription_sha256=emergency_transcription_sha256,
                runtime_consumer_ids=EMERGENCY_RUNTIME_CONSUMER_IDS,
                provider_name="40k.app",
                source_url=EMERGENCY_SOURCE_URL,
                observed_at=EMERGENCY_OBSERVED_AT,
                app_version=None,
                project_authority_policy_id=EMERGENCY_PROJECT_AUTHORITY_POLICY_ID,
                review_audit_id=EMERGENCY_REVIEW_AUDIT_ID,
                review_audit_row_id=EMERGENCY_REVIEW_AUDIT_ROW_ID,
                review_audit_observation_sha256=(EMERGENCY_REVIEW_AUDIT_OBSERVATION_SHA256),
                mirror_evidence_id=("40k-app-transports-2026-09-01:emergency-disembark-move"),
            ),
            *_evidence_rows(
                rule_source_id="gw-11e-core-rules:transports:assault-disembark-move",
                rule_slug="assault-disembark-move",
                section_id="18.06",
                section_heading="ASSAULT DISEMBARK MOVE",
                transcription_sha256=assault_transcription_sha256,
                runtime_consumer_ids=ASSAULT_RUNTIME_CONSUMER_IDS,
                provider_name="Game Datamissions",
                source_url=ASSAULT_SOURCE_URL,
                observed_at=None,
                app_version=ASSAULT_APP_VERSION,
                project_authority_policy_id=ASSAULT_PROJECT_AUTHORITY_POLICY_ID,
                review_audit_id=ASSAULT_REVIEW_AUDIT_ID,
                review_audit_row_id=ASSAULT_REVIEW_AUDIT_ROW_ID,
                review_audit_observation_sha256=(ASSAULT_REVIEW_AUDIT_OBSERVATION_SHA256),
                mirror_evidence_id=("game-datamissions-core-rules-data-931:assault-disembark-move"),
            ),
        ],
        "package_hash": "",
    }
    payload["package_hash"] = _sha256_payload(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the reviewed 18.05 and 18.06 Transport source artifact."
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(build_payload(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not ARTIFACT_PATH.is_file() or ARTIFACT_PATH.read_text(encoding="utf-8") != rendered:
            raise SystemExit("Transports source artifact is stale.")
        return 0
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
