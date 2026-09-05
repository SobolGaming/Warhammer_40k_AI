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
    / "core_abilities_2026_09"
    / "artifacts"
    / "package.json"
)

SOURCE_URL = "https://game-datamissions.com/11th/rules/changelog"
APP_VERSION = "931"
OBSERVED_AT = "2026-09-02T12:30:09-04:00"
PROJECT_AUTHORITY_POLICY_ID = (
    "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
)
REVIEW_AUDIT_ID = "core-rules-maintained-app-mirrors-2026-09-02"
REVIEW_AUDIT_ROW_ID = "game-datamissions-core-rules-data-931"
REVIEW_AUDIT_OBSERVATION_SHA256 = "1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668"

DEADLY_DEMISE_SOURCE_TEXT = """This ability always takes the form Deadly Demise X. Each time a model with this ability is destroyed, after the units embarked within it (if any) have made their emergency disembark moves, roll one D6. On a 6, that model suffers a deadly demise; each unit within 6\" of that model suffers a number of mortal wounds denoted by X (if this is a random number, roll separately for each unit within 6\")."""
DEADLY_DEMISE_WHEN_DESCRIPTOR = "Each time a model with this ability is destroyed, after the units embarked within it (if any) have made their emergency disembark moves"
DEADLY_DEMISE_EFFECT_DESCRIPTOR = 'roll one D6. On a 6, that model suffers a deadly demise; each unit within 6" of that model suffers a number of mortal wounds denoted by X (if this is a random number, roll separately for each unit within 6").'
DEADLY_DEMISE_RESTRICTIONS_DESCRIPTOR = "This ability always takes the form Deadly Demise X."
SCOUT_ALTERNATION_SOURCE_TEXT = """If both players have units with the Scouts ability, do they alternate resolving scout moves?
Yes, players alternate resolving any pre-battle rules units from their army may have, starting with the player who will take the first turn."""
SCOUT_ALTERNATION_WHEN_DESCRIPTOR = "If both players have units with pre-battle rules to resolve"
SCOUT_ALTERNATION_EFFECT_DESCRIPTOR = (
    "players alternate resolving those units, starting with the player who will take the first turn"
)
SCOUT_ALTERNATION_RESTRICTIONS_DESCRIPTOR = (
    "skip a player only when that player has no unresolved pre-battle rule"
)
HAZARDOUS_SOURCE_TEXT = """Each time a unit is selected to shoot or selected to fight, after that unit has resolved all of its attacks, make a number of hazard rolls (06.03) for that unit equal to the number of [HAZARDOUS] weapons you selected in the Select Weapons step."""
HAZARDOUS_WHEN_DESCRIPTOR = (
    "Each time a unit is selected to shoot or selected to fight, after that unit has "
    "resolved all of its attacks"
)
HAZARDOUS_EFFECT_DESCRIPTOR = (
    "make a number of hazard rolls for that unit equal to the number of Hazardous weapons "
    "selected in the Select Weapons step"
)
HAZARDOUS_RESTRICTIONS_DESCRIPTOR = (
    "each selected physical Hazardous weapon instance contributes one roll; make all hazard "
    "rolls simultaneously under 06.03"
)

DEADLY_DEMISE_RUNTIME_CONSUMER_IDS = [
    "warhammer40k_core.engine.ability_catalog:eleventh_edition_core_ability_catalog_records",
    "warhammer40k_core.engine.abilities:default_ability_handler_registry",
    "warhammer40k_core.engine.attack_sequence_damage_resolution:_resolve_deadly_demise_before_removal",
    "warhammer40k_core.engine.catalog_rule_consumption:record_core_deadly_demise_sources_for_unit",
    "warhammer40k_core.engine.deadly_demise:resolve_deadly_demise_trigger",
    "warhammer40k_core.engine.rule_model_destruction:destroy_model_with_rule_reactions",
]
SCOUT_ALTERNATION_RUNTIME_CONSUMER_IDS = [
    "warhammer40k_core.engine.game_state:GameState.record_prebattle_action",
    "warhammer40k_core.engine.game_state:GameState.set_prebattle_alternation_cursor",
    "warhammer40k_core.engine.prebattle:_timing_state_for_step",
    "warhammer40k_core.engine.prebattle:prebattle_action_selection_request",
    "warhammer40k_core.engine.prebattle:prebattle_next_player_id_for_timing_state",
    "warhammer40k_core.engine.prebattle_alternation:align_prebattle_alternation_cursor",
    "warhammer40k_core.engine.prebattle_alternation:validate_prebattle_alternation_restore",
    "warhammer40k_core.engine.prebattle_records:PreBattleAlternationCursor",
    "warhammer40k_core.engine.setup_flow:SetupFlow._advance_resolve_prebattle_actions",
]
HAZARDOUS_RUNTIME_CONSUMER_IDS = [
    "warhammer40k_core.engine.ability_catalog:eleventh_edition_core_ability_catalog_records",
    "warhammer40k_core.engine.abilities:default_ability_handler_registry",
    "warhammer40k_core.engine.attack_sequence_dispatch:resolve_attack_sequence_until_blocked",
    "warhammer40k_core.engine.attack_sequence_group_selection:_continue_hazardous_after_mortal_wound_feel_no_pain",
    "warhammer40k_core.engine.attack_sequence_hazardous:_resolve_hazardous_tests",
    "warhammer40k_core.engine.attack_sequence_hazardous:validate_hazardous_mortal_wound_source_context",
    "warhammer40k_core.engine.attack_sequence_hazardous:validate_pending_hazardous_mortal_wound_requests",
    "warhammer40k_core.engine.weapon_declaration:RangedAttackPool",
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
    evidence_slug: str,
    review_source_title: str,
    mirror_source_title: str,
    source_url: str,
    transcription_sha256: str,
    runtime_consumer_ids: list[str],
) -> list[dict[str, object]]:
    shared: dict[str, object] = {
        "rule_source_id": rule_source_id,
        "app_version": APP_VERSION,
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
        "evidence_id": f"core-v2-core-abilities-source-review:{evidence_slug}",
        "evidence_kind": "project_reviewed_app_transcription",
        "authority": "unverified_transcription_only",
        "project_authority_policy_id": None,
        "review_audit_id": None,
        "review_audit_row_id": None,
        "review_audit_source_observation_sha256": None,
        "provider_name": "CORE V2 Source Review",
        "source_title": review_source_title,
        "source_platform": "Repository",
        "source_url": None,
        "observed_at": None,
        "verification_status": "unverified",
        "provider_non_affiliation_recorded": False,
    }
    review["observation_sha256"] = _evidence_observation_sha256(review)
    mirror = {
        **shared,
        "evidence_id": f"game-datamissions-core-rules-data-931:{evidence_slug}",
        "evidence_kind": "third_party_mirror",
        "authority": "project_authoritative_app_mirror",
        "project_authority_policy_id": PROJECT_AUTHORITY_POLICY_ID,
        "review_audit_id": REVIEW_AUDIT_ID,
        "review_audit_row_id": REVIEW_AUDIT_ROW_ID,
        "review_audit_source_observation_sha256": REVIEW_AUDIT_OBSERVATION_SHA256,
        "provider_name": "Game Datamissions",
        "source_title": mirror_source_title,
        "source_platform": "Web",
        "source_url": source_url,
        "observed_at": None,
        "verification_status": "authoritative_app_mirror",
        "provider_non_affiliation_recorded": True,
    }
    mirror["observation_sha256"] = _evidence_observation_sha256(mirror)
    return [review, mirror]


def build_payload() -> dict[str, object]:
    deadly_demise_transcription_sha256 = _sha256_text(DEADLY_DEMISE_SOURCE_TEXT)
    scout_alternation_transcription_sha256 = _sha256_text(SCOUT_ALTERNATION_SOURCE_TEXT)
    hazardous_transcription_sha256 = _sha256_text(HAZARDOUS_SOURCE_TEXT)
    payload: dict[str, object] = {
        "artifact_schema": "core-v2-core-abilities-source-v1",
        "source_package_id": "gw-11e-core-abilities",
        "source_version": "game-datamissions-v931-observed-2026-09-02",
        "source_document": {
            "document_id": REVIEW_AUDIT_ROW_ID,
            "source_title": "Game Datamissions Core Rules Data Changelog v931",
            "source_url": SOURCE_URL,
            "observed_at": OBSERVED_AT,
            "app_version": APP_VERSION,
            "project_authority_policy_id": PROJECT_AUTHORITY_POLICY_ID,
        },
        "rules": [
            {
                "rule_id": "deadly-demise",
                "runtime_ability_id": "core-deadly-demise",
                "runtime_handler_id": "core:deadly-demise",
                "source_id": "gw-11e-core-abilities:core:deadly-demise",
                "section_id": "24.08",
                "section_heading": "DEADLY DEMISE",
                "source_text": DEADLY_DEMISE_SOURCE_TEXT,
                "when_descriptor": DEADLY_DEMISE_WHEN_DESCRIPTOR,
                "effect_descriptor": DEADLY_DEMISE_EFFECT_DESCRIPTOR,
                "restrictions_descriptor": DEADLY_DEMISE_RESTRICTIONS_DESCRIPTOR,
                "trigger_kind": "after_model_destroyed",
                "transcription_sha256": deadly_demise_transcription_sha256,
                "load_support_status": "loaded",
                "semantic_execution_status": "executable_engine_runtime",
                "runtime_consumer_ids": DEADLY_DEMISE_RUNTIME_CONSUMER_IDS,
            },
            {
                "rule_id": "alternating-scout-moves-faq",
                "runtime_ability_id": "core-scouts",
                "runtime_handler_id": "core:scouts",
                "source_id": "gw-11e-core-abilities:faq:alternating-scout-moves",
                "section_id": "FAQ",
                "section_heading": "ALTERNATING SCOUT MOVES",
                "source_text": SCOUT_ALTERNATION_SOURCE_TEXT,
                "when_descriptor": SCOUT_ALTERNATION_WHEN_DESCRIPTOR,
                "effect_descriptor": SCOUT_ALTERNATION_EFFECT_DESCRIPTOR,
                "restrictions_descriptor": SCOUT_ALTERNATION_RESTRICTIONS_DESCRIPTOR,
                "trigger_kind": "before_battle",
                "transcription_sha256": scout_alternation_transcription_sha256,
                "load_support_status": "loaded",
                "semantic_execution_status": "executable_engine_runtime",
                "runtime_consumer_ids": SCOUT_ALTERNATION_RUNTIME_CONSUMER_IDS,
            },
            {
                "rule_id": "hazardous",
                "runtime_ability_id": "core-hazardous",
                "runtime_handler_id": "core:hazardous",
                "source_id": "gw-11e-core-abilities:core:hazardous",
                "section_id": "24.15",
                "section_heading": "HAZARDOUS",
                "source_text": HAZARDOUS_SOURCE_TEXT,
                "when_descriptor": HAZARDOUS_WHEN_DESCRIPTOR,
                "effect_descriptor": HAZARDOUS_EFFECT_DESCRIPTOR,
                "restrictions_descriptor": HAZARDOUS_RESTRICTIONS_DESCRIPTOR,
                "trigger_kind": "after_unit_attacks_resolved",
                "transcription_sha256": hazardous_transcription_sha256,
                "load_support_status": "loaded",
                "semantic_execution_status": "executable_engine_runtime",
                "runtime_consumer_ids": HAZARDOUS_RUNTIME_CONSUMER_IDS,
            },
        ],
        "evidence": [
            *_evidence_rows(
                rule_source_id="gw-11e-core-abilities:core:deadly-demise",
                evidence_slug="deadly-demise",
                review_source_title="Reviewed transcription of 24.08 Deadly Demise",
                mirror_source_title="Game Datamissions Core Rules 24.08 Deadly Demise",
                source_url=SOURCE_URL,
                transcription_sha256=deadly_demise_transcription_sha256,
                runtime_consumer_ids=DEADLY_DEMISE_RUNTIME_CONSUMER_IDS,
            ),
            *_evidence_rows(
                rule_source_id="gw-11e-core-abilities:faq:alternating-scout-moves",
                evidence_slug="alternating-scout-moves",
                review_source_title="Reviewed transcription of Core Rules FAQ Alternating Scout Moves",
                mirror_source_title="Game Datamissions Core Rules FAQ Alternating Scout Moves",
                source_url=SOURCE_URL,
                transcription_sha256=scout_alternation_transcription_sha256,
                runtime_consumer_ids=SCOUT_ALTERNATION_RUNTIME_CONSUMER_IDS,
            ),
            *_evidence_rows(
                rule_source_id="gw-11e-core-abilities:core:hazardous",
                evidence_slug="hazardous",
                review_source_title="Reviewed transcription of 24.15 Hazardous",
                mirror_source_title="Game Datamissions Core Rules 24.15 Hazardous",
                source_url=SOURCE_URL,
                transcription_sha256=hazardous_transcription_sha256,
                runtime_consumer_ids=HAZARDOUS_RUNTIME_CONSUMER_IDS,
            ),
        ],
        "package_hash": "",
    }
    payload["package_hash"] = _sha256_payload(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the reviewed Core Abilities source artifact."
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = json.dumps(build_payload(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not ARTIFACT_PATH.is_file() or ARTIFACT_PATH.read_text(encoding="utf-8") != rendered:
            raise SystemExit("Core abilities source artifact is stale.")
        return 0
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(rendered, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
