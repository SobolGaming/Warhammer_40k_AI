from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase14a_source_identity import (
    CORE_RULES_LEGACY_FORTY_K_APP_POLICY_ID,
    CORE_RULES_MAINTAINED_MIRROR_AUDIT_PATH,
    CORE_RULES_MAINTAINED_MIRROR_POLICY_ID,
    CORE_RULES_REVIEW_AUDIT_ID,
    CORE_RULES_REVIEW_AUDIT_PATH,
    CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    EXPECTED_SOURCE_AUTHORITY_REGISTRY_SHA256,
    PROJECT_AUTHORITY_POLICY_ID,
    SCOUT_ALTERNATION_FAQ_SOURCE_RULE_ID,
    CoreCommandPhaseSourceBuildError,
    MissionSourcePackageDefinition,
    Path,
    RuleEvidenceAuthority,
    RuleEvidenceError,
    RuleEvidenceKind,
    RuleEvidencePayload,
    RuleEvidenceRecord,
    RulesetDescriptor,
    RuleSourcePackage,
    RuleVerificationStatus,
    SourceAuthorityRegistryError,
    SourceAuthorityScope,
    SourceCatalog,
    SourceEvidenceCatalog,
    _app_hidden_transcription_artifact_path,
    _app_hidden_transcription_payload,
    _canonical_payload_sha256,
    _command_phase_evidence_observation_sha256,
    _core_command_phase_source_artifact_path,
    _core_command_phase_source_payload,
    _core_rules_review_audit_context,
    _core_stratagem_app_source_artifact_path,
    _core_stratagem_app_source_payload,
    _july_rules_update_artifact_path,
    _july_rules_update_payload,
    _observation_sha256,
    _replace_evidence_records,
    _universal_rule_payload,
    app_core_rules_hidden_2026_08_09,
    build_attached_units_source_payload,
    build_attack_sequence_source_payload,
    build_core_abilities_source_payload,
    build_core_command_phase_source_payload,
    build_fight_on_death_payloads,
    build_movement_source_payload,
    build_other_concepts_source_payload,
    build_transports_source_payload,
    chapter_approved_2026_27,
    core_abilities,
    core_abilities_2026_09,
    core_attached_units_2026_09,
    core_attack_sequence_2026_09,
    core_command_phase_2026_08,
    core_fight_on_death_2026_09,
    core_movement_phase_2026_08,
    core_other_concepts_2026_08,
    core_rules,
    core_stratagems,
    core_stratagems_2026_08,
    core_transports_2026_09,
    hashlib,
    importlib,
    json,
    july_rules_updates_2026_07,
    load_source_authority_registry_from_json_bytes,
    pytest,
    source_evidence_module,
)


def test_order39_stealth_source_is_pinned_reproducible_and_executable() -> None:
    from tools.build_core_stealth_source import build_payloads

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_stealth_2026_09 as package,
    )

    raw = Path(package.__file__).with_name("artifacts").joinpath("package.json").read_bytes()
    expected, audit = build_payloads()
    assert json.loads(raw) == expected
    assert (
        json.loads(
            Path(
                "data/source_audits/maintained_app_mirrors/stealth_2026_09_12.audit.json"
            ).read_bytes()
        )
        == audit
    )
    artifact = package.validate_source_artifact_bytes(raw)
    assert (
        artifact.package_hash
        == hashlib.sha256(
            json.dumps(
                {**expected, "package_hash": ""}, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
    )
    assert sorted(
        package.source_package().source_evidence_catalog.records, key=lambda row: row.evidence_id
    ) == sorted(package.source_evidence_records(), key=lambda row: row.evidence_id)
    (rule,) = package.source_rules()
    assert rule.source_id == package.STEALTH_SOURCE_ID
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    for consumer in rule.runtime_consumer_ids:
        module, attribute = consumer.split(":")
        assert callable(vars(importlib.import_module(module))[attribute])
    with pytest.raises(package.StealthSourceError, match="source bytes drifted"):
        package.validate_source_artifact_bytes(raw + b"\n")


def test_p09a_move_units_source_artifact_is_pinned_typed_and_executable() -> None:
    artifact_path = Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_movement_phase_2026_08/artifacts/package.json"
    )
    raw = artifact_path.read_bytes()
    package = core_movement_phase_2026_08.source_package()
    rule = core_movement_phase_2026_08.source_rule_record()
    evidence = package.source_evidence_catalog.records_for_source_id(rule.source_id)

    assert hashlib.sha256(raw).hexdigest() == (core_movement_phase_2026_08.EXPECTED_ARTIFACT_SHA256)
    assert json.loads(raw) == build_movement_source_payload()
    assert rule.section_id == "09.02"
    assert rule.transcription_sha256 == core_movement_phase_2026_08.TRANSCRIPTION_SHA256
    assert {
        "battlefield",
        "strategic reserves",
        "embarked within a TRANSPORT",
        "Disembark move (18.04)",
        "Ingress move (20.04)",
    } <= {
        token
        for token in (
            "battlefield",
            "strategic reserves",
            "embarked within a TRANSPORT",
            "Disembark move (18.04)",
            "Ingress move (20.04)",
        )
        if token in rule.source_text
    }
    assert {record.evidence_kind for record in evidence} == {
        "project_reviewed_app_transcription",
        "third_party_mirror",
    }
    assert {record.semantic_execution_status for record in evidence} == {
        "executable_engine_runtime"
    }
    assert all(record.runtime_consumer_ids for record in evidence)
    assert SourceCatalog.from_payload(package.source_catalog.to_payload()).to_payload() == (
        package.source_catalog.to_payload()
    )
    consumer_ids = set(rule.runtime_consumer_ids) | {
        consumer_id for record in evidence for consumer_id in record.runtime_consumer_ids
    }
    for consumer_id in sorted(consumer_ids):
        module_name, separator, qualified_name = consumer_id.partition(":")
        assert separator, consumer_id
        resolved: object = importlib.import_module(module_name)
        for attribute in qualified_name.split("."):
            resolved = getattr(resolved, attribute)
        assert resolved is not None, consumer_id


def test_p24f_deadly_demise_source_artifact_is_pinned_typed_and_executable() -> None:
    artifact_path = Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_abilities_2026_09/artifacts/package.json"
    )
    raw = artifact_path.read_bytes()
    package = core_abilities_2026_09.source_package()
    rule = core_abilities_2026_09.source_rule_record()
    evidence = package.source_evidence_catalog.records_for_source_id(rule.source_id)

    assert hashlib.sha256(raw).hexdigest() == core_abilities_2026_09.EXPECTED_ARTIFACT_SHA256
    assert json.loads(raw) == build_core_abilities_source_payload()
    assert rule.section_id == "24.08"
    assert rule.source_id == core_abilities_2026_09.DEADLY_DEMISE_SOURCE_ID
    assert rule.transcription_sha256 == core_abilities_2026_09.TRANSCRIPTION_SHA256
    assert "Each time a model with this ability is destroyed" in rule.source_text
    assert "when this unit is destroyed" not in rule.source_text.lower()
    assert rule.when_descriptor.startswith("Each time a model with this ability is destroyed")
    assert rule.trigger_kind == "after_model_destroyed"
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    assert {record.evidence_kind for record in evidence} == {
        "project_reviewed_app_transcription",
        "third_party_mirror",
    }
    mirror = next(
        record for record in evidence if record.authority == "project_authoritative_app_mirror"
    )
    assert mirror.provider_name == "Game Datamissions"
    assert mirror.app_version == "931"
    assert mirror.review_audit_source_observation_sha256 == (
        "1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668"
    )
    assert all(record.runtime_consumer_ids for record in evidence)
    assert SourceCatalog.from_payload(package.source_catalog.to_payload()).to_payload() == (
        package.source_catalog.to_payload()
    )


def test_p05a_destroyed_source_artifact_is_pinned_typed_and_executable() -> None:
    artifact_path = Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_attack_sequence_2026_09/artifacts/package.json"
    )
    raw = artifact_path.read_bytes()
    package = core_attack_sequence_2026_09.source_package()
    rule = core_attack_sequence_2026_09.source_rule_record()
    evidence = package.source_evidence_catalog.records_for_source_id(rule.source_id)

    assert hashlib.sha256(raw).hexdigest() == (
        core_attack_sequence_2026_09.EXPECTED_ARTIFACT_SHA256
    )
    assert json.loads(raw) == build_attack_sequence_source_payload()
    assert rule.section_id == "05.04.04"
    assert rule.source_id == core_attack_sequence_2026_09.DESTROYED_RULE_ID
    assert rule.transcription_sha256 == core_attack_sequence_2026_09.TRANSCRIPTION_SHA256
    assert "only removed after the attacking unit" in rule.source_text
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    assert {record.evidence_kind for record in evidence} == {
        "project_reviewed_app_transcription",
        "third_party_mirror",
    }
    assert all(record.runtime_consumer_ids for record in evidence)
    assert SourceCatalog.from_payload(package.source_catalog.to_payload()).to_payload() == (
        package.source_catalog.to_payload()
    )


def test_p05a_destroyed_source_loader_rejects_schema_and_byte_drift() -> None:
    artifact_path = Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_attack_sequence_2026_09/artifacts/package.json"
    )
    raw = artifact_path.read_bytes()
    payload = json.loads(raw)
    payload["rules"][0]["section_id"] = "05.04"

    with pytest.raises(
        core_attack_sequence_2026_09.CoreAttackSequenceSourceArtifactError,
        match="reviewed identity",
    ):
        core_attack_sequence_2026_09.core_attack_sequence_source_artifact_from_json_bytes(
            json.dumps(payload).encode()
        )
    with pytest.raises(
        core_attack_sequence_2026_09.CoreAttackSequenceSourceArtifactError,
        match="bytes drifted",
    ):
        core_attack_sequence_2026_09.validate_core_attack_sequence_source_artifact_bytes(
            raw + b"\n"
        )


def test_p06_other_concepts_runtime_consumer_ids_resolve() -> None:
    package = core_other_concepts_2026_08.source_package()
    rules = (
        core_other_concepts_2026_08.source_rule_record(),
        core_other_concepts_2026_08.source_rule_record_by_id("mortal-wounds"),
        core_other_concepts_2026_08.source_rule_record_by_id("visibility-classifications"),
        core_other_concepts_2026_08.source_rule_record_by_id("visibility-any-part-faq"),
    )
    consumer_ids = {consumer_id for rule in rules for consumer_id in rule.runtime_consumer_ids} | {
        consumer_id
        for evidence in package.source_evidence_catalog.records
        for consumer_id in evidence.runtime_consumer_ids
    }

    for consumer_id in sorted(consumer_ids):
        module_name, separator, qualified_name = consumer_id.partition(":")
        assert separator, consumer_id
        assert module_name, consumer_id
        assert qualified_name, consumer_id
        resolved: object = importlib.import_module(module_name)
        for attribute in qualified_name.split("."):
            resolved = getattr(resolved, attribute)
        assert resolved is not None, consumer_id


def test_p09a_move_units_source_artifact_rejects_text_and_byte_drift() -> None:
    artifact_path = Path(
        "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
        "core_movement_phase_2026_08/artifacts/package.json"
    )
    payload = cast(dict[str, object], json.loads(artifact_path.read_text()))
    rules = cast(list[dict[str, object]], payload["rules"])
    rule = rules[0]
    rule["source_text"] = f"{rule['source_text']} altered"
    with pytest.raises(
        core_movement_phase_2026_08.CoreMovementPhaseSourceArtifactError,
        match="reviewed identity",
    ):
        core_movement_phase_2026_08.core_movement_phase_source_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )

    raw = artifact_path.read_bytes()
    core_movement_phase_2026_08.validate_core_movement_phase_source_artifact_bytes(raw)
    with pytest.raises(
        core_movement_phase_2026_08.CoreMovementPhaseSourceArtifactError,
        match="artifact bytes drifted",
    ):
        core_movement_phase_2026_08.validate_core_movement_phase_source_artifact_bytes(raw + b"\n")


def test_july_app_rows_pin_historical_owner_and_project_authoritative_mirror_evidence() -> None:
    source_package = july_rules_updates_2026_07.source_package()
    evidence_records = source_package.source_evidence_catalog.records
    artifact = july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
        _july_rules_update_artifact_path().read_bytes()
    )
    rules_by_source_id = {rule.source_id: rule for rule in artifact.app_core_rules_update.rules}
    evidence_by_source_id = {
        source_id: source_package.source_evidence_catalog.records_for_source_id(source_id)
        for source_id in rules_by_source_id
    }
    review_context, review_source_observation_by_row_id = _core_rules_review_audit_context()

    assert hashlib.sha256(_july_rules_update_artifact_path().read_bytes()).hexdigest() == (
        july_rules_updates_2026_07.EXPECTED_ARTIFACT_SHA256
    )
    assert july_rules_updates_2026_07.EXPECTED_ARTIFACT_SHA256 == (
        "59ab29a5f0c8780418ba3a7fac29e16f228f235cedc3644c2bb75e84b68708fb"
    )
    assert july_rules_updates_2026_07.PACKAGE_HASH == (
        "27ecf29d722d8d139420abf538fc00c5ad1cfb922b0b2816f15c46c978e9d84d"
    )
    assert len(evidence_records) == 32
    assert len(rules_by_source_id) == len(source_package.evidence_required_source_ids) == 16
    assert set(evidence_by_source_id) == set(rules_by_source_id)
    assert all(len(records) == 2 for records in evidence_by_source_id.values())
    owner_records = tuple(
        record
        for record in evidence_records
        if record.evidence_kind == "owner_supplied_app_transcription"
    )
    mirror_records = tuple(
        record for record in evidence_records if record.evidence_kind == "third_party_mirror"
    )
    assert len(owner_records) == len(mirror_records) == 16
    assert all(record.authority == "unverified_transcription_only" for record in owner_records)
    assert all(record.verification_status == "unverified" for record in owner_records)
    assert all(record.project_authority_policy_id is None for record in owner_records)
    assert all(record.review_audit_id is None for record in owner_records)
    assert all(record.review_audit_row_id is None for record in owner_records)
    assert all(record.review_audit_source_observation_sha256 is None for record in owner_records)
    assert all(record.observed_at is None for record in owner_records)
    assert all(record.source_url is None for record in owner_records)
    assert all(record.authority == "project_authoritative_app_mirror" for record in mirror_records)
    assert all(
        record.project_authority_policy_id == PROJECT_AUTHORITY_POLICY_ID
        for record in mirror_records
    )
    assert review_context == {
        "audit_id": CORE_RULES_REVIEW_AUDIT_ID,
        "observed_at": "2026-08-25T00:00:00-04:00",
        "project_authority_policy_id": PROJECT_AUTHORITY_POLICY_ID,
        "provider_affiliation": "not_affiliated_with_or_endorsed_by_games_workshop",
    }
    assert all(record.review_audit_id == review_context["audit_id"] for record in mirror_records)
    assert all(
        record.review_audit_row_id in review_source_observation_by_row_id
        for record in mirror_records
    )
    assert all(
        record.review_audit_source_observation_sha256
        == review_source_observation_by_row_id[cast(str, record.review_audit_row_id)]
        for record in mirror_records
    )
    assert all(record.observed_at == review_context["observed_at"] for record in mirror_records)
    assert all(
        record.project_authority_policy_id == review_context["project_authority_policy_id"]
        for record in mirror_records
    )
    assert all(record.provider_name == "40k.app" for record in mirror_records)
    assert all(record.official_corroborating_source_ids == () for record in evidence_records)
    assert all(
        record.provider_non_affiliation_recorded
        == (
            review_context["provider_affiliation"]
            == "not_affiliated_with_or_endorsed_by_games_workshop"
        )
        for record in mirror_records
    )
    assert not any(record.provider_non_affiliation_recorded for record in owner_records)
    assert all(
        RuleEvidenceRecord.from_payload(record.to_payload()) == record
        for record in evidence_records
    )
    assert all(
        hashlib.sha256(rules_by_source_id[source_id].source_text.encode()).hexdigest()
        == evidence.transcription_sha256
        for source_id, records in evidence_by_source_id.items()
        for evidence in records
    )

    fight_on_death_source_id = july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS[
        "05.04.05-fight-on-death"
    ]
    fight_on_death_records = evidence_by_source_id[fight_on_death_source_id]
    assert {record.verification_status for record in fight_on_death_records} == {
        "unverified",
        "authoritative_app_mirror",
    }
    for fight_on_death in fight_on_death_records:
        assert fight_on_death.transcription_sha256 == (
            "d2b9c094f1eda640ccfa76817e741497d960ff5d6015d7d9afa7616e3cd77741"
        )
        assert fight_on_death.load_support_status == "loaded"
        assert fight_on_death.semantic_execution_status == "partial_engine_runtime"
        assert fight_on_death.runtime_consumer_ids == (
            "warhammer40k_core.engine.retained_destruction_selection:apply_retention_selection",
            "warhammer40k_core.engine.retained_destruction_cleanup:begin_retained_destruction_cleanup",
        )

    objective_consolidation_records = evidence_by_source_id[
        july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS["12.08-objective-consolidation"]
    ]
    objective_consolidation_rule = rules_by_source_id[
        july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS["12.08-objective-consolidation"]
    ]
    objective_owner = next(
        record
        for record in objective_consolidation_records
        if record.evidence_kind == "owner_supplied_app_transcription"
    )
    objective_mirror = next(
        record
        for record in objective_consolidation_records
        if record.evidence_kind == "third_party_mirror"
    )
    assert objective_consolidation_rule.behavior_descriptor == (
        "objective_consolidation_requires_unengaged_endpoint"
    )
    assert "must be unengaged" in objective_consolidation_rule.source_text
    assert objective_owner.authority == "unverified_transcription_only"
    assert objective_owner.verification_status == "unverified"
    assert objective_mirror.authority == "project_authoritative_app_mirror"
    assert objective_mirror.project_authority_policy_id == PROJECT_AUTHORITY_POLICY_ID
    assert objective_mirror.review_audit_id == CORE_RULES_REVIEW_AUDIT_ID
    assert objective_mirror.review_audit_row_id == ("finding:july-transcription-conflict-12-08")
    assert objective_mirror.review_audit_source_observation_sha256 == (
        "726ce364500c7f1d6b9776651f430ac05ad144a5899877fdbd857128e6cf041c"
    )
    assert objective_mirror.source_url == "https://www.40k.app/rules/12-fight-phase"
    assert objective_mirror.verification_status == "conflict"
    assert {record.verification_status for record in objective_consolidation_records} == {
        "unverified",
        "conflict",
    }
    assert all(
        record.semantic_execution_status == "blocked_by_source_conflict"
        for record in objective_consolidation_records
    )
    assert all(not record.runtime_consumer_ids for record in objective_consolidation_records)
    not_observed_rule_ids = {
        "faq-heavy-fly-horizontal-distance",
        "faq-hazardous-mixed-unit-keywords",
    }
    assert {
        rule_id
        for rule_id in not_observed_rule_ids
        if any(
            record.verification_status == "not_observed_on_mirror"
            for record in evidence_by_source_id[
                july_rules_updates_2026_07.APP_CORE_RULE_SOURCE_IDS[rule_id]
            ]
        )
    } == not_observed_rule_ids
    provenance = artifact.app_core_rules_update.transcription_provenance
    assert provenance.provenance_kind == "repository_transcription_without_retained_app_capture"
    assert provenance.authority == "unverified_transcription_only"
    assert provenance.observation_date is provenance.app_version is provenance.source_url is None
    assert provenance.screenshot_sha256 is provenance.source_binary_sha256 is None
    catalog_encoded = json.dumps(source_package.source_catalog.to_payload(), sort_keys=True)
    assert "40k.app" not in catalog_encoded
    assert not any(record.evidence_id in catalog_encoded for record in evidence_records)
    assert "secondary_mirror_only" not in catalog_encoded
    assert "project_authoritative_app_mirror" not in catalog_encoded
    assert not hasattr(july_rules_updates_2026_07, "source_catalog")
    assert not hasattr(july_rules_updates_2026_07, "app_core_rule_evidence_records")


def test_rule_evidence_rejects_mirror_official_authority_and_uncaptured_app_claims() -> None:
    def invalid_record(
        *,
        evidence_kind: RuleEvidenceKind,
        authority: RuleEvidenceAuthority,
        verification_status: RuleVerificationStatus,
        project_authority_policy_id: str | None = None,
        review_audit_id: str | None = None,
        review_audit_row_id: str | None = None,
        review_audit_source_observation_sha256: str | None = None,
        observed_at: str | None = "2026-08-25T12:00:00-04:00",
    ) -> RuleEvidenceRecord:
        return RuleEvidenceRecord(
            evidence_id="evidence:test",
            rule_source_id="source:test",
            evidence_kind=evidence_kind,
            authority=authority,
            project_authority_policy_id=project_authority_policy_id,
            review_audit_id=review_audit_id,
            review_audit_row_id=review_audit_row_id,
            review_audit_source_observation_sha256=review_audit_source_observation_sha256,
            provider_name="40k.app",
            source_title="Core Concepts",
            source_platform="Web",
            source_url="https://www.40k.app/rules/01-core-concepts",
            observed_at=observed_at,
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

    with pytest.raises(RuleEvidenceError, match="mirror authority classification is invalid"):
        invalid_record(
            evidence_kind="third_party_mirror",
            authority="official_primary",
            verification_status="mirror_only",
        )

    with pytest.raises(RuleEvidenceError, match="requires its authority policy ID"):
        invalid_record(
            evidence_kind="third_party_mirror",
            authority="project_authoritative_app_mirror",
            verification_status="authoritative_app_mirror",
        )

    with pytest.raises(RuleEvidenceError, match="App-data version or observation timestamp"):
        invalid_record(
            evidence_kind="third_party_mirror",
            authority="project_authoritative_app_mirror",
            verification_status="authoritative_app_mirror",
            project_authority_policy_id=PROJECT_AUTHORITY_POLICY_ID,
            review_audit_id=CORE_RULES_REVIEW_AUDIT_ID,
            review_audit_row_id="category:01",
            review_audit_source_observation_sha256=(
                "3668da89d60d6234672f11be41cb08ddca6816354db062b47c4b4adf8ebf2ec5"
            ),
            observed_at=None,
        )

    with pytest.raises(RuleEvidenceError, match="verification_status is unsupported"):
        invalid_record(
            evidence_kind="third_party_mirror",
            authority="secondary_mirror_only",
            verification_status=cast(RuleVerificationStatus, "official_corroborated"),
        )

    with pytest.raises(RuleEvidenceError, match="version, build, and a hashed retained capture"):
        invalid_record(
            evidence_kind="official_app_capture",
            authority="official_primary",
            verification_status="official_app_captured",
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "review_audit_id",
        "review_audit_row_id",
        "review_audit_source_observation_sha256",
    ],
)
def test_project_authoritative_mirror_requires_complete_retained_audit_link(
    field_name: str,
) -> None:
    record = next(
        evidence
        for evidence in july_rules_updates_2026_07.source_package().source_evidence_catalog.records
        if evidence.evidence_kind == "third_party_mirror"
        and evidence.verification_status == "authoritative_app_mirror"
    )
    payload = cast(dict[str, object], record.to_payload())
    payload[field_name] = None
    payload["observation_sha256"] = _observation_sha256(cast(RuleEvidencePayload, payload))

    with pytest.raises(RuleEvidenceError, match="maintained App-mirror record"):
        RuleEvidenceRecord.from_payload(payload)


@pytest.mark.parametrize(
    ("field_name", "replacement", "expected_message"),
    [
        ("review_audit_id", "does-not-exist", "audit ID or row ID is not registered"),
        ("review_audit_row_id", "does-not-exist", "audit ID or row ID is not registered"),
        (
            "review_audit_source_observation_sha256",
            "0" * 64,
            "audit reference does not match its registered row",
        ),
    ],
)
def test_project_authoritative_mirror_authenticates_retained_audit_registry_row(
    field_name: str,
    replacement: str,
    expected_message: str,
) -> None:
    record = next(
        evidence
        for evidence in july_rules_updates_2026_07.source_package().source_evidence_catalog.records
        if evidence.evidence_kind == "third_party_mirror"
        and evidence.verification_status == "authoritative_app_mirror"
    )
    payload = cast(dict[str, object], record.to_payload())
    payload[field_name] = replacement
    payload["observation_sha256"] = _observation_sha256(cast(RuleEvidencePayload, payload))

    with pytest.raises(RuleEvidenceError, match=expected_message):
        RuleEvidenceRecord.from_payload(payload)


def test_superseded_mirror_policy_rejects_new_observation_identity() -> None:
    record = next(
        evidence
        for evidence in july_rules_updates_2026_07.source_package().source_evidence_catalog.records
        if evidence.evidence_kind == "third_party_mirror"
        and evidence.verification_status == "authoritative_app_mirror"
    )
    payload = record.to_payload()
    payload["evidence_id"] = f"{record.evidence_id}:new-observation"
    payload["observed_at"] = "2026-09-02T00:00:00-04:00"
    payload["observation_sha256"] = _observation_sha256(payload)

    with pytest.raises(RuleEvidenceError, match="restricted to its immutable observation"):
        RuleEvidenceRecord.from_payload(payload)


def test_source_authority_registry_is_pinned_typed_and_tamper_evident() -> None:
    raw = Path("src/warhammer40k_core/rules/source_authority_registry.json").read_bytes()

    assert hashlib.sha256(raw).hexdigest() == EXPECTED_SOURCE_AUTHORITY_REGISTRY_SHA256
    registry = load_source_authority_registry_from_json_bytes(raw)
    scope = registry.scope(CORE_RULES_SOURCE_AUTHORITY_SCOPE)
    assert scope.edition == "warhammer_40000_11th"
    assert scope.corpus == "core_rules_categories_01_25"
    assert len(scope.legacy_observations) == 33
    assert len(scope.source_packages) == 54
    with pytest.raises(SourceAuthorityRegistryError, match="drifted from their reviewed pin"):
        load_source_authority_registry_from_json_bytes(raw + b"\n")


def test_maintained_mirror_evidence_accepts_either_provider_with_complete_tuple() -> None:
    existing = next(
        evidence
        for evidence in july_rules_updates_2026_07.source_package().source_evidence_catalog.records
        if evidence.evidence_kind == "third_party_mirror"
        and evidence.verification_status == "authoritative_app_mirror"
    )
    payload = existing.to_payload()
    payload.update(
        {
            "evidence_id": "game-datamissions-core-rules-data-931:test-rule",
            "project_authority_policy_id": CORE_RULES_MAINTAINED_MIRROR_POLICY_ID,
            "review_audit_id": "core-rules-maintained-app-mirrors-2026-09-02",
            "review_audit_row_id": "game-datamissions-core-rules-data-931",
            "review_audit_source_observation_sha256": (
                "1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668"
            ),
            "provider_name": "Game Datamissions",
            "source_title": "Game Datamissions Core Rules Data Changelog",
            "source_url": "https://game-datamissions.com/11th/rules/changelog",
            "observed_at": None,
            "app_version": "931",
        }
    )
    payload["observation_sha256"] = _observation_sha256(payload)

    record = RuleEvidenceRecord.from_payload(payload)

    assert record.provider_name == "Game Datamissions"
    assert record.app_version == "931"
    assert record.observed_at is None
    assert record.project_authority_policy_id == CORE_RULES_MAINTAINED_MIRROR_POLICY_ID

    missing_version = dict(payload)
    missing_version["app_version"] = None
    missing_version["observation_sha256"] = _observation_sha256(
        cast(RuleEvidencePayload, missing_version)
    )
    with pytest.raises(RuleEvidenceError, match="App-data version or observation timestamp"):
        RuleEvidenceRecord.from_payload(missing_version)

    legacy_policy = dict(payload)
    legacy_policy["project_authority_policy_id"] = PROJECT_AUTHORITY_POLICY_ID
    legacy_policy["observation_sha256"] = _observation_sha256(
        cast(RuleEvidencePayload, legacy_policy)
    )
    with pytest.raises(RuleEvidenceError, match=r"historical 40k\.app-only policy"):
        RuleEvidenceRecord.from_payload(legacy_policy)

    invalid_url = dict(payload)
    invalid_url["source_url"] = "https://game-datamissions.com/11th/rules/../factions"
    invalid_url["observation_sha256"] = _observation_sha256(cast(RuleEvidencePayload, invalid_url))
    with pytest.raises(RuleEvidenceError, match="canonical HTTPS Core Rules body or changelog URL"):
        RuleEvidenceRecord.from_payload(invalid_url)


def test_rule_evidence_official_capture_requires_authenticated_retained_bytes() -> None:
    capture_content = b"retained official App capture"
    payload: RuleEvidencePayload = {
        "evidence_id": "evidence:official-app-capture",
        "rule_source_id": "source:official-app-rule",
        "evidence_kind": "official_app_capture",
        "authority": "official_primary",
        "project_authority_policy_id": None,
        "review_audit_id": None,
        "review_audit_row_id": None,
        "review_audit_source_observation_sha256": None,
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

    missing_timestamp = dict(payload)
    missing_timestamp["observed_at"] = None
    missing_timestamp["observation_sha256"] = _observation_sha256(
        cast(RuleEvidencePayload, missing_timestamp)
    )
    with pytest.raises(RuleEvidenceError, match="requires the Games Workshop App"):
        RuleEvidenceRecord.from_payload(missing_timestamp, capture_content=capture_content)

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

    mirror_payload = next(
        record
        for record in july_rules_updates_2026_07.source_package().source_evidence_catalog.records
        if record.evidence_kind == "third_party_mirror"
        and record.verification_status == "authoritative_app_mirror"
    ).to_payload()
    mislabeled_mirror = dict(mirror_payload)
    mislabeled_mirror["provider_name"] = "Games Workshop"
    mislabeled_mirror["source_platform"] = "Warhammer 40,000 App"
    with pytest.raises(RuleEvidenceError, match="maintained App-mirror record"):
        RuleEvidenceRecord.from_payload(mislabeled_mirror)
    for invalid_url in (
        "https://www.40k.app/rulesevil",
        "https://www.40k.app/rules/../evil",
        "https://www.40k.app/rules//evil",
        "https://www.40k.app/rules/%2e%2e/evil",
        "https://www.40k.app/rules/evil\nsuffix",
        "https://www.40k.app/rules/evil\rsuffix",
        "https://www.40k.app/rules/evil\tsuffix",
    ):
        invalid_mirror_url = dict(mirror_payload)
        invalid_mirror_url["source_url"] = invalid_url
        with pytest.raises(RuleEvidenceError, match="canonical HTTPS rules URL"):
            RuleEvidenceRecord.from_payload(invalid_mirror_url)
    false_conflict_claim = dict(mirror_payload)
    false_conflict_claim["semantic_execution_status"] = "blocked_by_source_conflict"
    false_conflict_record = RuleEvidenceRecord.from_payload(false_conflict_claim)
    package = july_rules_updates_2026_07.source_package()
    with pytest.raises(RuleEvidenceError, match="must agree on load and semantic"):
        RuleSourcePackage(
            source_catalog=package.source_catalog,
            source_evidence_catalog=SourceEvidenceCatalog(
                records=_replace_evidence_records(package, false_conflict_record)
            ),
            evidence_required_source_ids=package.evidence_required_source_ids,
            source_authority_scope=package.source_authority_scope,
        )


def test_app_hidden_retains_historical_owner_and_authoritative_mirror_evidence() -> None:
    payload = _app_hidden_transcription_payload()
    raw = _app_hidden_transcription_artifact_path().read_bytes()
    artifact = app_core_rules_hidden_2026_08_09.app_hidden_transcription_artifact_from_json_bytes(
        raw
    )
    source_package = app_core_rules_hidden_2026_08_09.source_package()
    catalog = source_package.source_catalog
    catalog_payload = catalog.to_payload()
    source_capture = cast(dict[str, object], payload["source_capture"])
    evidence_records = source_package.source_evidence_catalog.records_for_source_id(
        app_core_rules_hidden_2026_08_09.RULE_SOURCE_ID
    )
    owner = next(
        record
        for record in evidence_records
        if record.evidence_kind == "owner_supplied_app_transcription"
    )
    mirror = next(
        record for record in evidence_records if record.evidence_kind == "third_party_mirror"
    )
    review_context, review_source_observation_by_row_id = _core_rules_review_audit_context()

    assert hashlib.sha256(raw).hexdigest() == (
        app_core_rules_hidden_2026_08_09.EXPECTED_ARTIFACT_SHA256
    )
    assert app_core_rules_hidden_2026_08_09.EXPECTED_ARTIFACT_SHA256 == (
        "a63c25996e95c03f0953fc3841e47228d6d9533cdb4ef34a8e2324bc29d0f902"
    )
    assert app_core_rules_hidden_2026_08_09.PACKAGE_HASH == (
        "b65d4058463a2825b8808d1d7dfff2e82c8c87641f4241bf600e1bb82a866058"
    )
    assert hashlib.sha256(artifact.rule.source_text.encode()).hexdigest() == (
        app_core_rules_hidden_2026_08_09.TRANSCRIPTION_SHA256
    )
    assert artifact.source_capture.observation_date == "2026-08-09"
    assert artifact.source_capture.provenance_kind == "owner_supplied_app_transcription"
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
    assert "supersession" not in payload
    assert artifact.source_relationship.official_pdf_source_package_id == (
        core_rules.SOURCE_PACKAGE_ID
    )
    assert artifact.source_relationship.official_pdf_rule_reference == "13.09 Hidden"
    assert artifact.source_relationship.comparison_scope == (
        "hidden_terrain_area_feature_eligibility"
    )
    assert artifact.source_relationship.relationship_status == (
        "maintained_app_wording_supersedes_pdf_by_project_source_policy"
    )
    assert len(evidence_records) == 2
    assert owner.authority == "unverified_transcription_only"
    assert owner.project_authority_policy_id is None
    assert owner.review_audit_id is None
    assert owner.review_audit_row_id is None
    assert owner.review_audit_source_observation_sha256 is None
    assert owner.observed_at is None
    assert owner.verification_status == "unverified"
    assert not owner.provider_non_affiliation_recorded
    assert owner.source_url is owner.app_version is owner.app_build is None
    assert owner.capture_artifact_path is owner.capture_sha256 is None
    assert mirror.authority == "project_authoritative_app_mirror"
    assert (
        mirror.project_authority_policy_id
        == review_context["project_authority_policy_id"]
        == PROJECT_AUTHORITY_POLICY_ID
    )
    assert mirror.review_audit_id == review_context["audit_id"] == CORE_RULES_REVIEW_AUDIT_ID
    assert mirror.review_audit_row_id == "finding:hidden-unverified-source-13-09"
    assert (
        mirror.review_audit_source_observation_sha256
        == (review_source_observation_by_row_id[mirror.review_audit_row_id])
    )
    assert mirror.review_audit_source_observation_sha256 == (
        "62d982be96a81f69059f11def8a0ee75e6ae64f2dfd6f7132e4913140e9aaaf4"
    )
    assert mirror.observed_at == review_context["observed_at"]
    assert mirror.verification_status == "authoritative_app_mirror"
    assert mirror.provider_name == "40k.app"
    assert mirror.provider_non_affiliation_recorded == (
        review_context["provider_affiliation"]
        == "not_affiliated_with_or_endorsed_by_games_workshop"
    )
    assert mirror.source_url == "https://www.40k.app/rules/13-terrain"
    assert all(record.load_support_status == "loaded" for record in evidence_records)
    assert all(
        record.semantic_execution_status == "executable_engine_runtime"
        for record in evidence_records
    )
    assert {record.runtime_consumer_ids for record in evidence_records} == {
        (
            "warhammer40k_core.engine.shooting_targets:unit_has_line_of_sight_to_target",
            "warhammer40k_core.engine.terrain_hidden:terrain_hidden_model_ids",
        )
    }
    assert all(
        RuleEvidenceRecord.from_payload(record.to_payload()) == record
        for record in evidence_records
    )
    assert len(catalog.documents) == 1
    assert catalog.catalog_version.source_date == "2026-08-09"
    assert "project-authoritative 40k.app App mirror" in catalog.documents[0].title
    assert (
        catalog.source_text_by_id(app_core_rules_hidden_2026_08_09.RULE_SOURCE_ID).raw_text
        == artifact.rule.source_text
    )
    provenance = catalog.source_text_by_id(
        f"{app_core_rules_hidden_2026_08_09.SOURCE_PACKAGE_ID}:manifest:provenance"
    )
    assert (
        "historical transcription remains explicitly unverified on its own" in provenance.raw_text
    )
    assert PROJECT_AUTHORITY_POLICY_ID in provenance.raw_text
    assert "non-affiliated hosting provider" in provenance.raw_text
    assert SourceCatalog.from_payload(catalog_payload).to_payload() == catalog_payload
    assert not hasattr(app_core_rules_hidden_2026_08_09, "source_catalog")


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


def test_app_source_artifacts_reject_project_authority_policy_id_drift() -> None:
    july_payload = _july_rules_update_payload()
    app_update = cast(dict[str, object], july_payload["app_core_rules_update"])
    contexts = cast(list[dict[str, object]], app_update["evidence_contexts"])
    mirror_context = next(
        context for context in contexts if context["evidence_kind"] == "third_party_mirror"
    )
    mirror_context["project_authority_policy_id"] = "core-rules-source-policy:wrong"

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="mirror provenance drifted",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(july_payload, sort_keys=True).encode()
        )

    hidden_payload = _app_hidden_transcription_payload()
    hidden_evidence = cast(list[dict[str, object]], hidden_payload["evidence_records"])
    hidden_mirror = next(
        record for record in hidden_evidence if record["evidence_kind"] == "third_party_mirror"
    )
    hidden_mirror["project_authority_policy_id"] = "core-rules-source-policy:wrong"
    hidden_mirror["observation_sha256"] = _observation_sha256(
        cast(RuleEvidencePayload, hidden_mirror)
    )

    with pytest.raises(
        app_core_rules_hidden_2026_08_09.AppHiddenTranscriptionArtifactError,
        match="transcription evidence is invalid",
    ):
        app_core_rules_hidden_2026_08_09.app_hidden_transcription_artifact_from_json_bytes(
            json.dumps(hidden_payload, sort_keys=True).encode()
        )


def test_app_source_artifacts_reject_retained_audit_link_drift() -> None:
    july_package = july_rules_updates_2026_07.source_package()
    july_payload = _july_rules_update_payload()
    app_update = cast(dict[str, object], july_payload["app_core_rules_update"])
    july_evidence = cast(list[dict[str, object]], app_update["evidence_records"])
    july_mirror_artifact = next(
        record
        for record in july_evidence
        if record["evidence_context_id"] == "40k-app-comparison-2026-08-25"
    )
    july_mirror_record = next(
        record
        for record in july_package.source_evidence_catalog.records
        if record.evidence_id == july_mirror_artifact["evidence_id"]
    )
    july_mirror_artifact["review_audit_row_id"] = "category:02"
    july_mirror_payload = july_mirror_record.to_payload()
    july_mirror_payload["review_audit_row_id"] = "category:02"
    july_mirror_artifact["observation_sha256"] = _observation_sha256(july_mirror_payload)

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="evidence record is invalid",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(july_payload, sort_keys=True).encode()
        )

    hidden_package = app_core_rules_hidden_2026_08_09.source_package()
    hidden_payload = _app_hidden_transcription_payload()
    hidden_evidence = cast(list[dict[str, object]], hidden_payload["evidence_records"])
    hidden_mirror_artifact = next(
        record for record in hidden_evidence if record["evidence_kind"] == "third_party_mirror"
    )
    hidden_mirror_record = next(
        record
        for record in hidden_package.source_evidence_catalog.records
        if record.evidence_id == hidden_mirror_artifact["evidence_id"]
    )
    hidden_mirror_artifact["review_audit_row_id"] = "category:13"
    hidden_mirror_payload = hidden_mirror_record.to_payload()
    hidden_mirror_payload["review_audit_row_id"] = "category:13"
    hidden_mirror_artifact["observation_sha256"] = _observation_sha256(hidden_mirror_payload)

    with pytest.raises(
        app_core_rules_hidden_2026_08_09.AppHiddenTranscriptionArtifactError,
        match="transcription evidence is invalid",
    ):
        app_core_rules_hidden_2026_08_09.app_hidden_transcription_artifact_from_json_bytes(
            json.dumps(hidden_payload, sort_keys=True).encode()
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
    evidence_ids = cast(list[str], rules[0]["evidence_ids"])
    rules[0]["evidence_ids"] = [evidence_ids[0], "40k-app:missing-evidence"]

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="unknown evidence",
    ):
        july_rules_updates_2026_07.july_rules_updates_package_artifact_from_json_bytes(
            json.dumps(payload, sort_keys=True).encode()
        )


def test_july_rules_updates_artifact_rejects_cross_rule_evidence_links() -> None:
    payload = _july_rules_update_payload()
    app_update = cast(dict[str, object], payload["app_core_rules_update"])
    rules = cast(list[dict[str, object]], app_update["rules"])
    first_evidence_ids = cast(list[str], rules[0]["evidence_ids"])
    second_evidence_ids = cast(list[str], rules[1]["evidence_ids"])
    first_mirror_id = next(
        evidence_id for evidence_id in first_evidence_ids if evidence_id.startswith("40k-app-")
    )
    second_mirror_id = next(
        evidence_id for evidence_id in second_evidence_ids if evidence_id.startswith("40k-app-")
    )
    first_evidence_ids[first_evidence_ids.index(first_mirror_id)] = second_mirror_id
    second_evidence_ids[second_evidence_ids.index(second_mirror_id)] = first_mirror_id

    with pytest.raises(
        july_rules_updates_2026_07.JulyRulesUpdateArtifactError,
        match="evidence links cross source-rule identities",
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


@pytest.mark.parametrize(
    "mutation",
    [
        "reordered_heading_sequence",
        "category_url_substitution",
        "category_scope_substitution",
    ],
)
def test_p08ab_builder_rejects_reviewed_search_observation_identity_drift(
    mutation: str,
) -> None:
    payload = _core_command_phase_source_payload()
    source_document = cast(dict[str, object], payload["source_document"])
    search_index = cast(dict[str, object], payload["search_index_observation"])
    headings = cast(list[dict[str, object]], search_index["headings"])
    if mutation == "reordered_heading_sequence":
        headings[0], headings[1] = headings[1], headings[0]
    elif mutation == "category_url_substitution":
        search_index["source_url"] = source_document["authoritative_category_url"]
    else:
        search_index["observation_scope"] = source_document["authoritative_category_scope"]

    with pytest.raises(
        CoreCommandPhaseSourceBuildError,
        match="reviewed semantic identity",
    ):
        build_core_command_phase_source_payload(payload)


def test_p08ab_builder_rejects_rehashed_category_audit_substitution_for_search_link() -> None:
    payload = _core_command_phase_source_payload()
    source_document = cast(dict[str, object], payload["source_document"])
    search_index = cast(dict[str, object], payload["search_index_observation"])
    rules = cast(list[dict[str, object]], payload["rules"])
    evidence = cast(list[dict[str, object]], payload["evidence_records"])
    search_index.update(
        {
            "observation_id": source_document["review_audit_id"],
            "observation_row_id": source_document["review_audit_row_id"],
            "source_url": source_document["authoritative_category_url"],
            "observed_at": source_document["authoritative_category_observed_at"],
            "observation_scope": source_document["authoritative_category_scope"],
            "source_observation_sha256": source_document["review_audit_source_observation_sha256"],
        }
    )
    rules_by_source_id = {cast(str, rule["source_id"]): rule for rule in rules}
    for record in evidence:
        if record["evidence_kind"] != "third_party_mirror":
            continue
        record.update(
            {
                "review_audit_id": source_document["review_audit_id"],
                "review_audit_row_id": source_document["review_audit_row_id"],
                "review_audit_source_observation_sha256": source_document[
                    "review_audit_source_observation_sha256"
                ],
                "source_url": source_document["authoritative_category_url"],
                "observed_at": source_document["authoritative_category_observed_at"],
            }
        )
        record["observation_sha256"] = _command_phase_evidence_observation_sha256(record)
        rules_by_source_id[cast(str, record["rule_source_id"])]["source_observation_sha256"] = (
            record["observation_sha256"]
        )
    payload["package_hash"] = ""
    payload["package_hash"] = _canonical_payload_sha256(payload)

    assert search_index["observation_id"] == "40k-app-core-rules-2026-08-25"
    assert search_index["observation_row_id"] == "category:08"
    assert search_index["source_observation_sha256"] == (
        "0920fa00c1f4ecbc9e46795c1d72695872b61e7577eeaa693c57eb12c26c871e"
    )
    assert all(
        rule["source_observation_sha256"]
        == next(
            record["observation_sha256"]
            for record in evidence
            if record["evidence_kind"] == "third_party_mirror"
            and record["rule_source_id"] == rule["source_id"]
        )
        for rule in rules
    )
    assert payload["package_hash"] == _canonical_payload_sha256({**payload, "package_hash": ""})

    with pytest.raises(
        CoreCommandPhaseSourceBuildError,
        match="reviewed semantic identity",
    ):
        build_core_command_phase_source_payload(payload)


def test_project_reviewed_app_transcription_is_truthful_and_insufficient_alone() -> None:
    package = core_stratagems_2026_08.source_package()
    source_id = core_stratagems_2026_08.RULE_SOURCE_IDS["crushing-impact"]
    records = package.source_evidence_catalog.records_for_source_id(source_id)
    project_review = next(
        record for record in records if record.evidence_kind == "project_reviewed_app_transcription"
    )
    payload = project_review.to_payload()
    payload["provider_name"] = "Project Owner"
    payload["observation_sha256"] = _observation_sha256(payload)

    with pytest.raises(
        RuleEvidenceError,
        match="project-reviewed App transcription must retain repository-review provenance",
    ):
        RuleEvidenceRecord.from_payload(payload)
    with pytest.raises(
        RuleEvidenceError,
        match="executable or partial semantics require an official App capture or project",
    ):
        RuleSourcePackage(
            source_catalog=package.source_catalog,
            source_evidence_catalog=SourceEvidenceCatalog(
                records=tuple(
                    record
                    for record in package.source_evidence_catalog.records
                    if record.rule_source_id != source_id or record == project_review
                )
            ),
            evidence_required_source_ids=package.evidence_required_source_ids,
            source_authority_scope=package.source_authority_scope,
        )


def test_ruleset_descriptor_hash_is_eleventh_only_and_deterministic() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    payload = descriptor.to_payload()

    assert payload["ruleset_id"]["edition"] == "11e"
    assert descriptor.descriptor_hash == RulesetDescriptor.from_payload(payload).descriptor_hash


__all__: list[str] = []
__all__ += ["CORE_RULES_LEGACY_FORTY_K_APP_POLICY_ID", "CORE_RULES_MAINTAINED_MIRROR_AUDIT_PATH"]
__all__ += ["CORE_RULES_REVIEW_AUDIT_PATH", "MissionSourcePackageDefinition"]
__all__ += ["SCOUT_ALTERNATION_FAQ_SOURCE_RULE_ID", "SourceAuthorityScope"]
__all__ += ["_core_command_phase_source_artifact_path"]
__all__ += ["_core_stratagem_app_source_artifact_path", "_core_stratagem_app_source_payload"]
__all__ += ["build_attached_units_source_payload", "build_fight_on_death_payloads"]
__all__ += ["build_other_concepts_source_payload", "build_transports_source_payload"]
__all__ += ["chapter_approved_2026_27", "core_abilities", "core_attached_units_2026_09"]
__all__ += ["core_command_phase_2026_08", "core_fight_on_death_2026_09", "core_stratagems"]
__all__ += ["core_transports_2026_09", "source_evidence_module"]
