# ruff: noqa: E501
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
    / "core_movement_phase_2026_08"
    / "artifacts"
    / "package.json"
)

SOURCE_TEXT = """MOVE UNITS STEP
The active player moves their units, one unit at a time, until all their units have been selected and have finished making their moves. For each unit, use the sequence below.
1 SELECT UNIT
Select a friendly unit that has not been selected in this step. That unit can either be on the battlefield, in Strategic Reserves (20.02), or embarked within a Transport model (18.01). That unit has now been selected to move.
2 SELECT MOVE TYPE
Select one of the eligible move types listed below for your unit to make. Resolve that move type, after which that unit has finished making its move.
- REMAIN STATIONARY (09.04)
- NORMAL MOVE (09.05)
- ADVANCE (09.06)
- FALL-BACK (09.07)
- DISEMBARK (18.04)
- INGRESS (20.04)"""


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


def build_payload() -> dict[str, object]:
    transcription_sha256 = _sha256_text(SOURCE_TEXT)
    runtime_consumers = [
        "warhammer40k_core.engine.phases.movement_handler:MovementPhaseHandler.begin_phase",
        "warhammer40k_core.engine.phases.movement_handler:MovementPhaseHandler.apply_decision",
        "warhammer40k_core.engine.phases.movement_action_decisions:_movement_action_options_for_selected_unit",
    ]
    mirror_evidence: dict[str, object] = {
        "evidence_id": "40k-app-movement-phase-2026-08-29:move-units-step",
        "rule_source_id": "gw-11e-core-rules:movement-phase:move-units-step",
        "evidence_kind": "third_party_mirror",
        "authority": "project_authoritative_app_mirror",
        "project_authority_policy_id": (
            "core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26"
        ),
        "review_audit_id": "40k-app-core-rules-2026-08-25",
        "review_audit_row_id": "category:09",
        "review_audit_source_observation_sha256": (
            "a00bccdc9dd090acd4fa211034bd397739392c4f018276667e3309f8d66960ae"
        ),
        "provider_name": "40k.app",
        "source_title": "40k.app Core Rules 09.02 Move Units Step",
        "source_platform": "Web",
        "source_url": "https://www.40k.app/rules/09-movement-phase",
        "observed_at": "2026-08-29T20:56:52-04:00",
        "app_version": None,
        "app_build": None,
        "capture_artifact_path": None,
        "capture_sha256": None,
        "transcription_sha256": transcription_sha256,
        "official_corroborating_source_ids": [],
        "verification_status": "authoritative_app_mirror",
        "provider_non_affiliation_recorded": True,
        "observation_sha256": "",
        "load_support_status": "loaded",
        "semantic_execution_status": "executable_engine_runtime",
        "runtime_consumer_ids": runtime_consumers,
    }
    mirror_evidence["observation_sha256"] = _evidence_observation_sha256(mirror_evidence)
    review_evidence: dict[str, object] = {
        "evidence_id": "core-v2-p09a-source-review:move-units-step",
        "rule_source_id": "gw-11e-core-rules:movement-phase:move-units-step",
        "evidence_kind": "project_reviewed_app_transcription",
        "authority": "unverified_transcription_only",
        "project_authority_policy_id": None,
        "review_audit_id": None,
        "review_audit_row_id": None,
        "review_audit_source_observation_sha256": None,
        "provider_name": "CORE V2 Source Review",
        "source_title": "Reviewed transcription of 09.02 Move Units Step",
        "source_platform": "Repository",
        "source_url": None,
        "observed_at": None,
        "app_version": None,
        "app_build": None,
        "capture_artifact_path": None,
        "capture_sha256": None,
        "transcription_sha256": transcription_sha256,
        "official_corroborating_source_ids": [],
        "verification_status": "unverified",
        "provider_non_affiliation_recorded": False,
        "observation_sha256": "",
        "load_support_status": "loaded",
        "semantic_execution_status": "executable_engine_runtime",
        "runtime_consumer_ids": runtime_consumers,
    }
    review_evidence["observation_sha256"] = _evidence_observation_sha256(review_evidence)
    payload: dict[str, object] = {
        "artifact_schema": "core-v2-movement-phase-source-v1",
        "source_package_id": "gw-11e-core-movement-phase",
        "source_version": "40k-app-move-units-observed-2026-08-29",
        "source_document": {
            "document_id": "40k-app-movement-phase-2026-08-29",
            "source_title": "40k.app Core Rules Movement Phase",
            "source_url": "https://www.40k.app/rules/09-movement-phase",
            "observed_at": "2026-08-29T20:56:52-04:00",
            "project_authority_policy_id": (
                "core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26"
            ),
        },
        "rule": {
            "rule_id": "move-units-step",
            "source_id": "gw-11e-core-rules:movement-phase:move-units-step",
            "section_id": "09.02",
            "section_heading": "MOVE UNITS STEP",
            "source_text": SOURCE_TEXT,
            "transcription_sha256": transcription_sha256,
            "load_support_status": "loaded",
            "semantic_execution_status": "executable_engine_runtime",
            "runtime_consumer_ids": runtime_consumers,
        },
        "evidence": [review_evidence, mirror_evidence],
        "package_hash": "",
    }
    payload["package_hash"] = _sha256_payload(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the reviewed 09.02 Move Units source artifact."
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(build_payload(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not ARTIFACT_PATH.is_file() or ARTIFACT_PATH.read_text(encoding="utf-8") != rendered:
            raise SystemExit("Movement-phase source artifact is stale.")
        return 0
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
