"""Reproduce the reviewed Order 53 source package and observation audit offline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "gw-11e-core-super-heavy-walker"
VERSION = "maintained-app-mirrors-observed-2026-09-16"
OBSERVED_AT = "2026-09-16T00:00:00+00:00"
AUDIT_ID = "core-super-heavy-walker-maintained-app-mirrors-2026-09-16"
POLICY = "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
SOURCE_ID = f"{PACKAGE_ID}:super-heavy-walker"
TEXT = (
    "Before moving that unit, you can select for all models in that unit to have "
    "the MOBILE keyword until that move ends."
)
URL = "https://www.40k.app/rules/24-core-abilities"
CONSUMERS = [
    "warhammer40k_core.engine.move_ability_choices:movement_keyword_options",
    "warhammer40k_core.engine.movement_legality:MovementCapabilitySet",
    "warhammer40k_core.engine.move_keyword_completion:move_keyword_completion_bindings",
]
OBLIGATIONS = [
    "Applies to each Normal, Advance and Fall Back move of a unit with this ability.",
    "Every model may transit other models, including Monster and Vehicle but excluding Titanic.",
    "Every model may move horizontally through terrain sections at most four inches high.",
    "Before moving, the owner may grant all models MOBILE until that move ends.",
    "Choosing MOBILE requires one D6 at move completion; a one makes the unit Battle-shocked.",
    "MOBILE permits horizontal movement through dense terrain; normal endpoints still apply.",
]
DESCRIPTOR = {
    "descriptor_id": "core-move-ability:super-heavy-walker",
    "source_rule_id": SOURCE_ID,
    "ability_ids": ["core-super-heavy-walker", "super-heavy-walker"],
    "activation_keyword": "SUPER_HEAVY_WALKER",
    "movement_modes": ["normal", "advance", "fall_back", "fly_take_to_skies"],
    "model_transit_excluded_keywords": ["TITANIC"],
    "horizontal_terrain_transit_height_inches": 4.0,
    "optional_move_keywords": ["MOBILE"],
    "completion_roll_expression": "D6",
    "battle_shocked_roll_values": [1],
}
ARTIFACT_PATH = ROOT / (
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "core_super_heavy_walker_2026_09/artifacts/package.json"
)
AUDIT_PATH = (
    ROOT / "data/source_audits/maintained_app_mirrors/super_heavy_walker_2026_09_16.audit.json"
)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_payloads() -> tuple[dict[str, object], dict[str, object]]:
    transcription = hashlib.sha256(TEXT.encode()).hexdigest()
    audit: dict[str, object] = {
        "row_id": "super-heavy-walker",
        "provider_name": "40k.app",
        "source_url": URL,
        "observed_at": OBSERVED_AT,
        "app_version": None,
        "policy_id": POLICY,
        "rule_source_id": SOURCE_ID,
        "transcription_sha256": transcription,
        "provider_non_affiliation_recorded": True,
        "transcription_scope": (
            "Short excerpt; complete 24.35 operative text reviewed in the search index."
        ),
        "reviewed_obligations": OBLIGATIONS,
    }
    audit_hash = _hash(audit)
    row: dict[str, object] = {
        "evidence_id": "core-super-heavy-walker-mirror:super-heavy-walker",
        "rule_source_id": SOURCE_ID,
        "evidence_kind": "third_party_mirror",
        "authority": "project_authoritative_app_mirror",
        "project_authority_policy_id": POLICY,
        "review_audit_id": AUDIT_ID,
        "review_audit_row_id": "super-heavy-walker",
        "review_audit_source_observation_sha256": audit_hash,
        "provider_name": "40k.app",
        "source_title": "40k.app 24.35 Super-Heavy Walker",
        "source_platform": "Web",
        "source_url": URL,
        "observed_at": OBSERVED_AT,
        "app_version": None,
        "app_build": None,
        "capture_artifact_path": None,
        "capture_sha256": None,
        "transcription_sha256": transcription,
        "official_corroborating_source_ids": [],
        "verification_status": "authoritative_app_mirror",
        "provider_non_affiliation_recorded": True,
        "observation_sha256": "",
        "load_support_status": "loaded",
        "semantic_execution_status": "executable_engine_runtime",
        "runtime_consumer_ids": CONSUMERS,
    }
    row["observation_sha256"] = _hash(
        {
            **row,
            "load_support_status": "not_loaded",
            "semantic_execution_status": "not_certified",
            "runtime_consumer_ids": [],
        }
    )
    review = {
        **row,
        "evidence_id": "core-super-heavy-walker-review:super-heavy-walker",
        "evidence_kind": "project_reviewed_app_transcription",
        "authority": "unverified_transcription_only",
        "project_authority_policy_id": None,
        "review_audit_id": None,
        "review_audit_row_id": None,
        "review_audit_source_observation_sha256": None,
        "provider_name": "CORE V2 Source Review",
        "source_platform": "Repository",
        "source_url": None,
        "observed_at": None,
        "verification_status": "unverified",
        "provider_non_affiliation_recorded": False,
        "observation_sha256": "",
    }
    review["observation_sha256"] = _hash(
        {
            **review,
            "load_support_status": "not_loaded",
            "semantic_execution_status": "not_certified",
            "runtime_consumer_ids": [],
        }
    )
    artifact: dict[str, object] = {
        "artifact_schema": "core-v2-core-super-heavy-walker-source-v1",
        "source_package_id": PACKAGE_ID,
        "source_version": VERSION,
        "rules": [
            {
                "source_id": SOURCE_ID,
                "section_id": "24.35",
                "source_text": TEXT,
                "transcription_sha256": transcription,
                "load_support_status": "loaded",
                "semantic_execution_status": "executable_engine_runtime",
                "runtime_consumer_ids": CONSUMERS,
            }
        ],
        "evidence": [review, row],
        "movement_abilities": [DESCRIPTOR],
        "package_hash": "",
    }
    artifact["package_hash"] = _hash(artifact)
    return artifact, {
        "audit_id": AUDIT_ID,
        "observed_at": OBSERVED_AT,
        "observation_time_precision": "day",
        "rows": [{**audit, "source_observation_sha256": audit_hash}],
        "observation_method": "Complete search-index text; direct retrieval returned HTTP 403.",
        "co_version_comparison": "No second-provider observation asserted.",
        "official_historical_source": {
            "source_id": "gw-11e-core-rules",
            "sha256": "f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833",
        },
        "official_review": {
            "artifact_path": (
                "docs/source_rules/eng_01-06_warhammer40k_new40k_core_rules-was6fbu1ix-hfewhmxyiy.pdf"
            ),
            "pages": [85],
            "sections": ["24.35"],
            "reviewed_obligations": OBLIGATIONS,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, payload in zip((ARTIFACT_PATH, AUDIT_PATH), build_payloads(), strict=True):
        raw = (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode()
        if args.check:
            if path.read_bytes() != raw:
                raise SystemExit(f"Order 53 source artifact drift: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        print(f"{path.relative_to(ROOT)}: {hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
