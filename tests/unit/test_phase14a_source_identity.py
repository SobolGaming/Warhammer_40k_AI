from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from warhammer40k_core.core.missions import MissionSourcePackageDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.rules.source_catalog import SourceCatalog
from warhammer40k_core.rules.source_evidence import (
    RuleEvidenceAuthority,
    RuleEvidenceError,
    RuleEvidenceKind,
    RuleEvidencePayload,
    RuleEvidenceRecord,
    RuleVerificationStatus,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    app_core_rules_hidden_2026_08_09,
    chapter_approved_2026_27,
    core_abilities,
    core_rules,
    core_stratagems,
    july_rules_updates_2026_07,
)


def test_eleventh_core_rules_source_catalog_cites_local_pdf_and_round_trips() -> None:
    catalog = core_rules.source_catalog()
    payload = catalog.to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    bundle = catalog.ruleset_bundles[0]
    document = catalog.documents[0]

    assert bundle.ruleset_id.to_payload()["edition"] == "11e"
    assert core_rules.LOCAL_CORE_RULES_PDF in document.title
    assert any(
        core_rules.LOCAL_CORE_RULES_PDF in source.raw_text for source in document.source_texts
    )
    assert len(document.source_texts) == 1
    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert SourceCatalog.from_payload(payload).to_payload() == payload


def test_july_rules_updates_source_catalog_cites_pdfs_and_preserves_identity() -> None:
    catalog = july_rules_updates_2026_07.source_catalog()
    payload = catalog.to_payload()
    encoded = json.dumps(payload, sort_keys=True)

    assert len(catalog.documents) == 3
    universal_documents = tuple(
        document
        for document in catalog.documents
        if july_rules_updates_2026_07.UNIVERSAL_RULES_LOCAL_PDF in document.title
    )
    event_companion_documents = tuple(
        document
        for document in catalog.documents
        if july_rules_updates_2026_07.EVENT_COMPANION_LOCAL_PDF in document.title
    )
    app_core_documents = tuple(
        document
        for document in catalog.documents
        if "Warhammer 40,000 App Core Rules" in document.title
    )
    assert len(universal_documents) == 1
    assert len(event_companion_documents) == 1
    assert len(app_core_documents) == 1
    universal_document = universal_documents[0]
    event_companion_document = event_companion_documents[0]
    universal_rules = july_rules_updates_2026_07.universal_rule_records()
    event_rules = july_rules_updates_2026_07.event_companion_rule_records()
    app_core_rules = july_rules_updates_2026_07.app_core_rule_records()
    assert {rule.rule_id: rule.behavior_descriptor for rule in universal_rules} == {
        "modifying-a-stratagem-cp-cost": "unnamed_zero_cp_reduces_cost_by_one",
        "stratagem-repeat-and-limit-exceptions": (
            "repeat_or_limit_exception_requires_named_stratagem"
        ),
        "stratagems-that-prevent-targeting": ("protective_targeting_range_is_eighteen_inches"),
        "stratagems-that-add-identical-units": ("identical_unit_replacement_once_per_battle"),
    }
    assert {rule.rule_id: rule.behavior_descriptor for rule in event_rules} == {
        "generating-command-points": "non_core_cp_gain_maximum_one_per_battle_round",
    }
    assert len(app_core_rules) == 16
    assert {rule.rule_id for rule in app_core_rules} == set(
        july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS
    )
    assert {rule.behavior_descriptor for rule in app_core_rules} >= {
        "fight_on_death_models_wait_for_their_units_single_attack_selection",
        "embarked_return_requires_remaining_transport_capacity",
        "post_roll_profile_changes_split_attack_pools",
        "forced_desperate_escape_tests_all_models_and_battle_shock",
        "objective_consolidation_requires_unengaged_endpoint",
        "objective_control_determined_first_at_phase_and_turn_end",
        "precision_mortals_prioritize_selected_character_group",
        "torrent_excludes_indirect_fire_and_precision",
        "incursion_allows_one_three_dp_detachment",
        "normal_move_limited_to_once_per_unit_per_phase",
        "fly_heavy_uses_horizontal_distance_for_three_inch_limit",
        "infantry_monster_vehicle_hazard_failure_inflicts_one_mortal_wound",
    }
    assert len(july_rules_updates_2026_07.changed_event_layouts()) == 8
    assert all(
        not row.deployment_zones_changed
        for row in july_rules_updates_2026_07.changed_event_layouts()
    )
    assert july_rules_updates_2026_07.UNIVERSAL_RULES_LOCAL_PDF in encoded
    assert july_rules_updates_2026_07.EVENT_COMPANION_LOCAL_PDF in encoded
    assert july_rules_updates_2026_07.UNIVERSAL_RULES_PDF_SHA256 in encoded
    assert july_rules_updates_2026_07.EVENT_COMPANION_PDF_SHA256 in encoded
    universal_source_ids = {source.source_id for source in universal_document.source_texts}
    event_source_texts_by_id = {
        source.source_id: source for source in event_companion_document.source_texts
    }
    assert {rule.source_id for rule in universal_rules} <= universal_source_ids
    assert july_rules_updates_2026_07.NON_CORE_CP_GAIN_CAP_SOURCE_ID not in universal_source_ids
    assert july_rules_updates_2026_07.NON_CORE_CP_GAIN_CAP_SOURCE_ID in event_source_texts_by_id
    assert (
        "maximum of 1CP per battle round"
        in event_source_texts_by_id[
            july_rules_updates_2026_07.NON_CORE_CP_GAIN_CAP_SOURCE_ID
        ].raw_text
    )
    assert {rule.source_id for rule in app_core_rules} == {
        source.source_id for source in app_core_documents[0].source_texts
    }
    assert any("Bane of Cowards" in rule.source_text for rule in app_core_rules)
    assert SourceCatalog.from_payload(payload).to_payload() == payload
    assert (
        hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        == "5dc3a27783541c49a3ffbd90c4deab9874f364c5bf3a2237133d7af2d6188d59"
    )

    for relative_path, expected_sha256 in (
        (
            july_rules_updates_2026_07.UNIVERSAL_RULES_LOCAL_PDF,
            july_rules_updates_2026_07.UNIVERSAL_RULES_PDF_SHA256,
        ),
        (
            july_rules_updates_2026_07.EVENT_COMPANION_LOCAL_PDF,
            july_rules_updates_2026_07.EVENT_COMPANION_PDF_SHA256,
        ),
    ):
        assert hashlib.sha256(Path(relative_path).read_bytes()).hexdigest() == expected_sha256


def test_july_app_rows_are_hash_pinned_and_quarantined_from_official_authority() -> None:
    evidence_records = july_rules_updates_2026_07.app_core_rule_evidence_records()
    rules_by_source_id = {
        rule.source_id: rule for rule in july_rules_updates_2026_07.app_core_rule_records()
    }
    evidence_by_source_id = {record.rule_source_id: record for record in evidence_records}

    assert hashlib.sha256(_july_rules_update_artifact_path().read_bytes()).hexdigest() == (
        july_rules_updates_2026_07.EXPECTED_ARTIFACT_SHA256
    )
    assert july_rules_updates_2026_07.PACKAGE_HASH == (
        "d9e36c4522463da052d3458568aaa5ad5c5279d649f1a0489ced6f80f9e3b08a"
    )
    assert len(evidence_records) == len(rules_by_source_id) == 16
    assert set(evidence_by_source_id) == set(rules_by_source_id)
    assert all(record.evidence_kind == "third_party_mirror" for record in evidence_records)
    assert all(record.authority == "secondary_mirror_only" for record in evidence_records)
    assert all(record.provider_name == "40k.app" for record in evidence_records)
    assert all(record.official_corroborating_source_ids == () for record in evidence_records)
    assert all(record.provider_non_affiliation_recorded for record in evidence_records)
    assert all(
        RuleEvidenceRecord.from_payload(record.to_payload()) == record
        for record in evidence_records
    )
    assert all(
        hashlib.sha256(rules_by_source_id[source_id].source_text.encode()).hexdigest()
        == evidence.transcription_sha256
        for source_id, evidence in evidence_by_source_id.items()
    )

    fight_on_death_source_id = july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS[
        "05.04.05-fight-on-death"
    ]
    fight_on_death = evidence_by_source_id[fight_on_death_source_id]
    assert fight_on_death.transcription_sha256 == (
        "d2b9c094f1eda640ccfa76817e741497d960ff5d6015d7d9afa7616e3cd77741"
    )
    assert fight_on_death.verification_status == "mirror_only"
    assert fight_on_death.load_support_status == "loaded"
    assert fight_on_death.semantic_execution_status == "partial_engine_runtime"
    assert fight_on_death.runtime_consumer_ids == (
        "warhammer40k_core.engine.fight_on_death:restore_model_awaiting_fight_on_death",
        "warhammer40k_core.engine.rule_model_destruction_fight_continuation:"
        "remove_remaining_fight_on_death_models_at_phase_end",
    )

    objective_consolidation = evidence_by_source_id[
        july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS["12.08-objective-consolidation"]
    ]
    assert objective_consolidation.verification_status == "conflict"
    assert objective_consolidation.semantic_execution_status == "blocked_by_source_conflict"
    not_observed_rule_ids = {
        "faq-heavy-fly-horizontal-distance",
        "faq-hazardous-mixed-unit-keywords",
    }
    assert {
        rule_id
        for rule_id in not_observed_rule_ids
        if evidence_by_source_id[
            july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS[rule_id]
        ].verification_status
        == "not_observed_on_mirror"
    } == not_observed_rule_ids
    provenance = july_rules_updates_2026_07.app_core_transcription_provenance()
    assert provenance.provenance_kind == ("repository_transcription_without_retained_app_capture")
    assert provenance.authority == "unverified_transcription_only"
    assert provenance.observation_date is None
    assert provenance.app_version is None
    assert provenance.source_url is None
    assert provenance.screenshot_sha256 is None
    assert provenance.source_binary_sha256 is None
    catalog_encoded = json.dumps(
        july_rules_updates_2026_07.source_catalog().to_payload(), sort_keys=True
    )
    assert "40k.app" not in catalog_encoded
    assert not any(record.evidence_id in catalog_encoded for record in evidence_records)
    assert "secondary_mirror_only" not in catalog_encoded


def test_rule_evidence_rejects_mirror_official_authority_and_uncaptured_app_claims() -> None:
    def invalid_record(
        *,
        evidence_kind: RuleEvidenceKind,
        authority: RuleEvidenceAuthority,
        verification_status: RuleVerificationStatus,
    ) -> RuleEvidenceRecord:
        return RuleEvidenceRecord(
            evidence_id="evidence:test",
            rule_source_id="source:test",
            evidence_kind=evidence_kind,
            authority=authority,
            provider_name="40k.app",
            source_title="Core Concepts",
            source_platform="Web",
            source_url="https://www.40k.app/rules/01-core-concepts",
            observed_at="2026-08-25T12:00:00-04:00",
            app_version=None,
            app_build=None,
            capture_artifact_path=None,
            capture_sha256=None,
            transcription_sha256="0" * 64,
            official_corroborating_source_ids=(),
            provider_non_affiliation_recorded=True,
            observation_sha256="0" * 64,
            load_support_status="loaded",
            semantic_execution_status="not_certified",
            runtime_consumer_ids=(),
            verification_status=verification_status,
        )

    with pytest.raises(RuleEvidenceError, match="secondary mirror authority"):
        invalid_record(
            evidence_kind="third_party_mirror",
            authority="official_primary",
            verification_status="official_corroborated",
        )

    with pytest.raises(RuleEvidenceError, match="version, build, and a hashed retained capture"):
        invalid_record(
            evidence_kind="official_app_capture",
            authority="official_primary",
            verification_status="official_app_captured",
        )


def test_rule_evidence_official_capture_requires_authenticated_retained_bytes() -> None:
    capture_content = b"retained official App capture"
    payload: RuleEvidencePayload = {
        "evidence_id": "evidence:official-app-capture",
        "rule_source_id": "source:official-app-rule",
        "evidence_kind": "official_app_capture",
        "authority": "official_primary",
        "provider_name": "Games Workshop",
        "source_title": "Warhammer 40,000 App Core Rules",
        "source_platform": "Warhammer 40,000 App",
        "source_url": None,
        "observed_at": "2026-08-25T12:00:00-04:00",
        "app_version": "11.0.0",
        "app_build": "test-build",
        "capture_artifact_path": "docs/source_rules/app_captures/core-rules.bin",
        "capture_sha256": hashlib.sha256(capture_content).hexdigest(),
        "transcription_sha256": hashlib.sha256(b"captured official rule text").hexdigest(),
        "official_corroborating_source_ids": [],
        "verification_status": "official_app_captured",
        "provider_non_affiliation_recorded": False,
        "observation_sha256": "",
        "load_support_status": "loaded",
        "semantic_execution_status": "not_certified",
        "runtime_consumer_ids": [],
    }
    observation_payload = dict(payload)
    observation_payload["observation_sha256"] = ""
    observation_payload["load_support_status"] = "not_loaded"
    observation_payload["semantic_execution_status"] = "not_certified"
    observation_payload["runtime_consumer_ids"] = []
    payload["observation_sha256"] = hashlib.sha256(
        json.dumps(observation_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    record = RuleEvidenceRecord.from_payload(payload, capture_content=capture_content)
    assert (
        RuleEvidenceRecord.from_payload(record.to_payload(), capture_content=capture_content)
        == record
    )

    with pytest.raises(RuleEvidenceError, match="retained capture bytes"):
        RuleEvidenceRecord.from_payload(payload)
    with pytest.raises(RuleEvidenceError, match="retained capture bytes"):
        RuleEvidenceRecord.from_payload(payload, capture_content=b"different capture")

    mirror_claim = dict(payload)
    mirror_claim["provider_name"] = "40k.app"
    mirror_claim["source_platform"] = "Web"
    mirror_claim["source_url"] = "https://www.40k.app/rules/01-core-concepts"
    with pytest.raises(RuleEvidenceError, match="requires the Games Workshop App"):
        RuleEvidenceRecord.from_payload(mirror_claim, capture_content=capture_content)

    traversal_claim = dict(payload)
    traversal_claim["capture_artifact_path"] = "../capture.bin"
    with pytest.raises(RuleEvidenceError, match="normalized relative POSIX path"):
        RuleEvidenceRecord.from_payload(traversal_claim, capture_content=capture_content)
    for invalid_path in ("C:/escape.bin", r"safe\..\escape.bin"):
        platform_escape_claim = dict(payload)
        platform_escape_claim["capture_artifact_path"] = invalid_path
        with pytest.raises(RuleEvidenceError, match="normalized relative POSIX path"):
            RuleEvidenceRecord.from_payload(
                platform_escape_claim,
                capture_content=capture_content,
            )

    unknown_field_claim = dict(payload)
    unknown_field_claim["unexpected"] = True
    with pytest.raises(RuleEvidenceError, match="payload fields drifted"):
        RuleEvidenceRecord.from_payload(unknown_field_claim, capture_content=capture_content)

    invalid_list_claim = dict(payload)
    invalid_list_claim["runtime_consumer_ids"] = "not-a-list"
    with pytest.raises(RuleEvidenceError, match="runtime_consumer_ids must be a list"):
        RuleEvidenceRecord.from_payload(invalid_list_claim, capture_content=capture_content)

    mirror_payload = july_rules_updates_2026_07.app_core_rule_evidence_records()[0].to_payload()
    mislabeled_mirror = dict(mirror_payload)
    mislabeled_mirror["provider_name"] = "Games Workshop"
    mislabeled_mirror["source_platform"] = "Warhammer 40,000 App"
    with pytest.raises(RuleEvidenceError, match="third-party mirror"):
        RuleEvidenceRecord.from_payload(mislabeled_mirror)
    invalid_mirror_url = dict(mirror_payload)
    invalid_mirror_url["source_url"] = "https://www.40k.app/rulesevil"
    with pytest.raises(RuleEvidenceError, match="canonical HTTPS rules URL"):
        RuleEvidenceRecord.from_payload(invalid_mirror_url)
    false_conflict_claim = dict(mirror_payload)
    false_conflict_claim["semantic_execution_status"] = "blocked_by_source_conflict"
    with pytest.raises(RuleEvidenceError, match="must coincide"):
        RuleEvidenceRecord.from_payload(false_conflict_claim)


def test_app_hidden_transcription_is_source_hashed_honest_and_cataloged() -> None:
    artifact = app_core_rules_hidden_2026_08_09.hidden_transcription_artifact()
    payload = _app_hidden_transcription_payload()
    raw = _app_hidden_transcription_artifact_path().read_bytes()
    catalog = app_core_rules_hidden_2026_08_09.source_catalog()
    catalog_payload = catalog.to_payload()
    source_capture = cast(dict[str, object], payload["source_capture"])

    assert hashlib.sha256(raw).hexdigest() == (
        app_core_rules_hidden_2026_08_09.EXPECTED_ARTIFACT_SHA256
    )
    assert hashlib.sha256(artifact.rule.source_text.encode()).hexdigest() == (
        app_core_rules_hidden_2026_08_09.TRANSCRIPTION_SHA256
    )
    assert artifact.source_capture.observation_date == "2026-08-09"
    assert artifact.source_capture.provenance_kind == (
        "project_owner_supplied_official_app_transcription"
    )
    assert artifact.source_capture.availability == (
        "transcription_only_no_source_url_app_version_or_binary"
    )
    assert set(source_capture) == {
        "availability",
        "observation_date",
        "provenance_kind",
        "source_platform",
        "source_title",
        "supplied_by",
    }
    assert artifact.supersession.supersedes_source_package_id == core_rules.SOURCE_PACKAGE_ID
    assert artifact.supersession.supersedes_rule_reference == "13.09 Hidden"
    assert artifact.supersession.supersession_scope == ("hidden_terrain_area_feature_eligibility")
    assert len(catalog.documents) == 1
    assert catalog.catalog_version.source_date == "2026-08-09"
    assert "App version unavailable" in catalog.documents[0].title
    assert (
        catalog.source_text_by_id(app_core_rules_hidden_2026_08_09.RULE_SOURCE_ID).raw_text
        == artifact.rule.source_text
    )
    provenance = catalog.source_text_by_id(
        f"{app_core_rules_hidden_2026_08_09.SOURCE_PACKAGE_ID}:manifest:provenance"
    )
    assert "no upstream artifact hash is claimed" in provenance.raw_text
    assert "supersedes" in provenance.raw_text
    assert SourceCatalog.from_payload(catalog_payload).to_payload() == catalog_payload


def test_app_hidden_transcription_artifact_rejects_unrecorded_source_metadata() -> None:
    payload = _app_hidden_transcription_payload()
    source_capture = cast(dict[str, object], payload["source_capture"])
    source_capture["source_url"] = "https://example.invalid/unrecorded"

    with pytest.raises(
        app_core_rules_hidden_2026_08_09.AppHiddenTranscriptionArtifactError,
        match="artifact is invalid",
    ):
        app_core_rules_hidden_2026_08_09.app_hidden_transcription_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


def test_app_hidden_transcription_artifact_rejects_text_and_byte_drift() -> None:
    payload = _app_hidden_transcription_payload()
    rule = cast(dict[str, object], payload["rule"])
    rule["source_text"] = f"{rule['source_text']} altered"

    with pytest.raises(
        app_core_rules_hidden_2026_08_09.AppHiddenTranscriptionArtifactError,
        match="source-text hash is stale",
    ):
        app_core_rules_hidden_2026_08_09.app_hidden_transcription_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )

    raw = _app_hidden_transcription_artifact_path().read_bytes()
    app_core_rules_hidden_2026_08_09.validate_hidden_transcription_artifact_bytes(raw)
    semantically_equivalent_bytes = json.dumps(
        _app_hidden_transcription_payload(), sort_keys=True
    ).encode()
    assert semantically_equivalent_bytes != raw
    with pytest.raises(
        app_core_rules_hidden_2026_08_09.AppHiddenTranscriptionArtifactError,
        match="artifact bytes drifted",
    ):
        app_core_rules_hidden_2026_08_09.validate_hidden_transcription_artifact_bytes(
            semantically_equivalent_bytes
        )


def test_july_rules_updates_artifact_rejects_unknown_fields() -> None:
    payload = _july_rules_update_payload()
    payload["unexpected"] = True

    with pytest.raises(july_rules_updates_2026_07.JulyRulesUpdateArtifactError):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


def test_july_rules_updates_artifact_rejects_unknown_app_evidence_reference() -> None:
    payload = _july_rules_update_payload()
    app_update = cast(dict[str, object], payload["app_core_rules_update"])
    rules = cast(list[dict[str, object]], app_update["rules"])
    rules[0]["evidence_ids"] = ["40k-app:missing-evidence"]

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="unknown evidence",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


def test_july_rules_updates_artifact_rejects_transcription_and_raw_byte_drift() -> None:
    payload = _july_rules_update_payload()
    app_update = cast(dict[str, object], payload["app_core_rules_update"])
    rules = cast(list[dict[str, object]], app_update["rules"])
    rules[0]["source_text"] = f"{rules[0]['source_text']} altered"

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="transcription hash is stale",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )

    raw = _july_rules_update_artifact_path().read_bytes()
    july_rules_updates_2026_07.validate_july_rules_update_artifact_bytes(raw)
    semantically_equivalent_bytes = json.dumps(
        _july_rules_update_payload(), sort_keys=True
    ).encode()
    assert semantically_equivalent_bytes != raw
    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="artifact bytes drifted",
    ):
        july_rules_updates_2026_07.validate_july_rules_update_artifact_bytes(
            semantically_equivalent_bytes
        )


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("rule_id", "unexpected-global-rule"),
        ("behavior_descriptor", "unexpected_global_behavior"),
    ],
)
def test_july_rules_updates_artifact_rejects_universal_rule_identity_drift(
    field_name: str,
    replacement: str,
) -> None:
    payload = _july_rules_update_payload()
    _universal_rule_payload(payload)[field_name] = replacement

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="Universal rules-update rule identity inventory drifted",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


def test_july_rules_updates_artifact_rejects_universal_rule_source_suffix_drift() -> None:
    payload = _july_rules_update_payload()
    _universal_rule_payload(payload)["source_id"] = (
        "gw-11e-rules-and-event-updates-2026-07-22:universal-rules:wrong-rule"
    )

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="Universal rules-update source identity drifted",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


@pytest.mark.parametrize(
    "field_name",
    ["document_id", "source_version", "source_url", "local_pdf"],
)
def test_july_rules_updates_artifact_rejects_universal_document_metadata_drift(
    field_name: str,
) -> None:
    payload = _july_rules_update_payload()
    universal_update = cast(dict[str, object], payload["universal_rules_update"])
    universal_update[field_name] = "unexpected"

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="Universal rules-update document metadata drifted",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


def test_eleventh_source_package_identity_payloads_are_json_safe() -> None:
    mission_package = chapter_approved_2026_27.source_package_definition()
    mission_payload = mission_package.to_payload()
    ability_identity = core_abilities.source_package_identity_payload()
    stratagem_identity = core_stratagems.source_package_identity_payload()
    payload = {
        "mission_package": mission_payload,
        "ability_identity": ability_identity,
        "stratagem_identity": stratagem_identity,
    }
    encoded = json.dumps(payload, sort_keys=True)

    assert mission_payload["edition_id"] == "warhammer_40000_11th"
    assert ability_identity["edition_id"] == "warhammer_40000_11th"
    assert stratagem_identity["edition_id"] == "warhammer_40000_11th"
    assert mission_payload["source_package_id"].startswith("gw-11e-")
    assert ability_identity["source_package_id"].startswith("gw-11e-")
    assert stratagem_identity["source_package_id"].startswith("gw-11e-")
    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert MissionSourcePackageDefinition.from_payload(mission_payload).to_payload() == (
        mission_payload
    )


def test_ruleset_descriptor_hash_is_eleventh_only_and_deterministic() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    payload = descriptor.to_payload()

    assert payload["ruleset_id"]["edition"] == "11e"
    assert descriptor.descriptor_hash == RulesetDescriptor.from_payload(payload).descriptor_hash


def _july_rules_update_payload() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(
            Path(
                "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
                "july_rules_updates_2026_07/artifacts/package.json"
            ).read_text()
        ),
    )


def _july_rules_update_artifact_path() -> Path:
    return Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "july_rules_updates_2026_07/artifacts/package.json"
    )


def _app_hidden_transcription_artifact_path() -> Path:
    return Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "app_core_rules_hidden_2026_08_09/artifacts/hidden.json"
    )


def _app_hidden_transcription_payload() -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads(_app_hidden_transcription_artifact_path().read_text()),
    )


def _universal_rule_payload(payload: dict[str, object]) -> dict[str, object]:
    universal_update = cast(dict[str, object], payload["universal_rules_update"])
    rules = cast(list[dict[str, object]], universal_update["rules"])
    return rules[0]
