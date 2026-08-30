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

SOURCE_URL = "https://www.40k.app/rules/09-movement-phase"
PROJECT_AUTHORITY_POLICY_ID = (
    "core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26"
)
REVIEW_AUDIT_ID = "40k-app-core-rules-2026-08-25"
REVIEW_AUDIT_ROW_ID = "category:09"
REVIEW_AUDIT_OBSERVATION_SHA256 = "a00bccdc9dd090acd4fa211034bd397739392c4f018276667e3309f8d66960ae"
OBSERVED_AT = "2026-08-30T13:55:17-04:00"

MOVE_UNITS_SOURCE_TEXT = """MOVE UNITS STEP
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

SELECTING_MODES_SOURCE_TEXT = """SELECTING MODES
Some rules instruct you to select a mode, such as fall-back moves (09.07). Modes are mutually exclusive, and you must assess each one in the order presented. When making a move, if your unit does not meet the conditions of any of the modes, it cannot make that move.
Sometimes a mode will be mandatory if applicable (e.g. consolidation modes, 12.08), but in the case of fall-back moves, ordered retreat is not mandatory, so you could select desperate escape instead.
Many move types state conditions you must meet while/after moving. Those that are labelled with a mode name only apply if you selected that mode; those not labelled with a mode name always apply."""

FALL_BACK_SOURCE_TEXT = """FALL-BACK MOVE
When eligible: Your unit is engaged.
Maximum distance: Your unit's M characteristic.
Effect: Your unit moves as described in Moving (03).
Before moving: Select fall-back mode:
* Ordered Retreat: If your unit is not battle-shocked, you can select this mode.
* Desperate Escape: Otherwise, you must select this mode. Make a hazard roll for each model in your unit (06.03).
While moving:
* Desperate Escape: Each model that is moved can be moved through enemy models.
After moving:
* Your unit must be unengaged.
* Until the end of the turn, unless otherwise stated, your unit is not eligible to shoot, declare a charge or start an action.
* Desperate Escape: If your unit is not battle-shocked, you must make a battle-shock roll for your unit (01.07)."""


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
    source_id: str,
    section_title: str,
    transcription_sha256: str,
    semantic_execution_status: str,
    runtime_consumer_ids: list[str],
    observed_at: str,
) -> list[dict[str, object]]:
    shared: dict[str, object] = {
        "rule_source_id": source_id,
        "app_version": None,
        "app_build": None,
        "capture_artifact_path": None,
        "capture_sha256": None,
        "transcription_sha256": transcription_sha256,
        "official_corroborating_source_ids": [],
        "observation_sha256": "",
        "load_support_status": "loaded",
        "semantic_execution_status": semantic_execution_status,
        "runtime_consumer_ids": runtime_consumer_ids,
    }
    review = {
        **shared,
        "evidence_id": f"core-v2-movement-source-review:{rule_id}",
        "evidence_kind": "project_reviewed_app_transcription",
        "authority": "unverified_transcription_only",
        "project_authority_policy_id": None,
        "review_audit_id": None,
        "review_audit_row_id": None,
        "review_audit_source_observation_sha256": None,
        "provider_name": "CORE V2 Source Review",
        "source_title": f"Reviewed transcription of {section_title}",
        "source_platform": "Repository",
        "source_url": None,
        "observed_at": None,
        "verification_status": "unverified",
        "provider_non_affiliation_recorded": False,
    }
    review["observation_sha256"] = _evidence_observation_sha256(review)
    mirror = {
        **shared,
        "evidence_id": f"40k-app-movement-phase-2026-08-30:{rule_id}",
        "evidence_kind": "third_party_mirror",
        "authority": "project_authoritative_app_mirror",
        "project_authority_policy_id": PROJECT_AUTHORITY_POLICY_ID,
        "review_audit_id": REVIEW_AUDIT_ID,
        "review_audit_row_id": REVIEW_AUDIT_ROW_ID,
        "review_audit_source_observation_sha256": REVIEW_AUDIT_OBSERVATION_SHA256,
        "provider_name": "40k.app",
        "source_title": f"40k.app Core Rules {section_title}",
        "source_platform": "Web",
        "source_url": SOURCE_URL,
        "observed_at": observed_at,
        "verification_status": "authoritative_app_mirror",
        "provider_non_affiliation_recorded": True,
    }
    mirror["observation_sha256"] = _evidence_observation_sha256(mirror)
    return [review, mirror]


def build_payload() -> dict[str, object]:
    rule_inputs = (
        (
            "move-units-step",
            "gw-11e-core-rules:movement-phase:move-units-step",
            "09.02",
            "MOVE UNITS STEP",
            MOVE_UNITS_SOURCE_TEXT,
            "executable_engine_runtime",
            [
                "warhammer40k_core.engine.phases.movement_handler:MovementPhaseHandler.begin_phase",
                "warhammer40k_core.engine.phases.movement_handler:MovementPhaseHandler.apply_decision",
                "warhammer40k_core.engine.phases.movement_action_decisions:_movement_action_options_for_selected_unit",
            ],
        ),
        (
            "selecting-modes",
            "gw-11e-core-rules:movement-phase:selecting-modes",
            "09.02.02",
            "SELECTING MODES",
            SELECTING_MODES_SOURCE_TEXT,
            "partial_engine_runtime",
            [
                "warhammer40k_core.engine.phases.movement_validation:_fall_back_modes_for_parameterized_option",
                "warhammer40k_core.engine.phases.movement_validation:_fall_back_mode_violation_code",
            ],
        ),
        (
            "fall-back-move",
            "gw-11e-core-rules:movement-phase:fall-back-move",
            "09.07",
            "FALL-BACK MOVE",
            FALL_BACK_SOURCE_TEXT,
            "executable_engine_runtime",
            [
                "warhammer40k_core.engine.phases.movement_geometry:_desperate_escape_requirements_for_fall_back",
                "warhammer40k_core.engine.phases.movement_resolution_flow:_apply_movement_proposal_decision",
                "warhammer40k_core.engine.phases.movement_fall_back_embark:_apply_fall_back_result",
            ],
        ),
    )
    rules: list[dict[str, object]] = []
    evidence: list[dict[str, object]] = []
    for (
        rule_id,
        source_id,
        section_id,
        section_heading,
        source_text,
        semantic_status,
        consumers,
    ) in rule_inputs:
        transcription_sha256 = _sha256_text(source_text)
        rules.append(
            {
                "rule_id": rule_id,
                "source_id": source_id,
                "section_id": section_id,
                "section_heading": section_heading,
                "source_text": source_text,
                "transcription_sha256": transcription_sha256,
                "load_support_status": "loaded",
                "semantic_execution_status": semantic_status,
                "runtime_consumer_ids": consumers,
            }
        )
        evidence.extend(
            _evidence_rows(
                rule_id=rule_id,
                source_id=source_id,
                section_title=f"{section_id} {section_heading.title()}",
                transcription_sha256=transcription_sha256,
                semantic_execution_status=semantic_status,
                runtime_consumer_ids=consumers,
                observed_at=OBSERVED_AT,
            )
        )
    payload: dict[str, object] = {
        "artifact_schema": "core-v2-movement-phase-source-v2",
        "source_package_id": "gw-11e-core-movement-phase",
        "source_version": "40k-app-movement-phase-observed-2026-08-30",
        "source_document": {
            "document_id": "40k-app-movement-phase-2026-08-30",
            "source_title": "40k.app Core Rules Movement Phase",
            "source_url": SOURCE_URL,
            "observed_at": OBSERVED_AT,
            "project_authority_policy_id": PROJECT_AUTHORITY_POLICY_ID,
        },
        "rules": rules,
        "evidence": evidence,
        "package_hash": "",
    }
    payload["package_hash"] = _sha256_payload(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the reviewed 09.02, 09.02.02, and 09.07 source artifact."
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
