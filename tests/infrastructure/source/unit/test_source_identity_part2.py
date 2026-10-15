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


@pytest.mark.stubbed
@pytest.mark.parametrize(
    "drift", ["schema", "identity", "text", "status", "mode", "version", "proof"]
)
def test_order72_source_resolution_rejects_rehashed_invalid_data(
    monkeypatch: pytest.MonkeyPatch, drift: str
) -> None:
    from tools.build_core_fight_source import ARTIFACT_PATH

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_fight_2026_09 as source,
    )

    data = json.loads(ARTIFACT_PATH.read_bytes())
    if drift == "identity":
        data["source_version"] = "931"
    elif drift == "text":
        data["rules"][0]["source_text"] += " drift"
    elif drift == "status":
        data["rules"][1]["semantic_execution_status"] = "executable_engine_runtime"
    elif drift == "mode":
        data["resolution"]["forced_fight_modes"] = ["ongoing", "engaging"]
    elif drift == "version":
        data["resolution"]["app_version"] = "931"
    elif drift == "proof":
        data["resolution"]["observation_sha256"] = "0" * 64
    raw = b"{" if drift == "schema" else json.dumps(data).encode()
    # Only the pure byte validator's pin is replaced; no engine object is stubbed.
    monkeypatch.setattr(source, "EXPECTED_ARTIFACT_SHA256", hashlib.sha256(raw).hexdigest())
    with pytest.raises(source.FightSourceError):
        source.validate_fight_source_artifact_bytes(raw)


def test_order56_source_identity_binds_completed_duplicate_execution() -> None:
    from tools.build_core_duplicated_abilities_source import (
        ARTIFACT_PATH,
        AUDIT_PATH,
        build_payloads,
    )

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_duplicated_abilities_2026_09 as source,
    )

    payload, audit = build_payloads()
    assert json.loads(ARTIFACT_PATH.read_bytes()) == payload
    assert json.loads(AUDIT_PATH.read_bytes()) == audit
    package = source.source_package()
    assert package.evidence_required_source_ids == (source.DUPLICATED_ABILITIES_SOURCE_ID,)
    (rule,) = source.source_rules()
    assert rule.section_id == "24.02"
    assert rule.load_support_status == "loaded"
    assert rule.semantic_execution_status == "executable_engine_runtime"
    assert (
        "warhammer40k_core.engine.weapon_selection_context:WeaponSelectionContext"
        in rule.runtime_consumer_ids
    )
    assert any("core_ability_selection" in consumer for consumer in rule.runtime_consumer_ids)
    assert any("prebattle_instance_selection" in consumer for consumer in rule.runtime_consumer_ids)
    assert package.source_catalog.source_text_by_id(rule.source_id).raw_text == rule.source_text
    assert hashlib.sha256(rule.source_text.encode()).hexdigest() == rule.transcription_sha256
    (mirror,) = (row for row in source.source_evidence_records() if row.provider_name == "40k.app")
    assert mirror.provider_non_affiliation_recorded
    assert mirror.observed_at == "2026-09-06T14:49:36Z"
    assert mirror.app_version is None
    assert "Select Weapons step" in rule.source_text
    with pytest.raises(source.DuplicatedAbilitiesSourceError, match="reviewed pin"):
        source.validate_source_artifact_bytes(ARTIFACT_PATH.read_bytes() + b"\n")


def test_order33_source_is_immutable_reproducible_and_bound_to_live_consumers() -> None:
    from tools.build_core_indirect_shooting_source import build_payloads

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_indirect_shooting_2026_09 as package,
    )

    raw = Path(package.__file__).with_name("artifacts").joinpath("package.json").read_bytes()
    artifact = package.validate_source_artifact_bytes(raw)
    expected, audit = build_payloads()
    assert json.loads(raw) == expected
    assert (
        json.loads(
            Path(
                "data/source_audits/maintained_app_mirrors/indirect_shooting_2026_09_09.audit.json"
            ).read_bytes()
        )
        == audit
    )
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
    assert {rule.section_id for rule in package.source_rules()} == {"09.04", "10.07"}
    for rule in package.source_rules():
        assert rule.load_support_status == "loaded"
        assert rule.semantic_execution_status == "partial_engine_runtime"
        for consumer in rule.runtime_consumer_ids:
            module, attribute = consumer.split(":")
            assert callable(vars(importlib.import_module(module))[attribute])
    with pytest.raises(package.IndirectShootingSourceError, match="source bytes drifted"):
        package.validate_source_artifact_bytes(raw + b"\n")


__all__: list[str] = []
__all__ += ["CORE_RULES_LEGACY_FORTY_K_APP_POLICY_ID", "CORE_RULES_MAINTAINED_MIRROR_AUDIT_PATH"]
__all__ += ["CORE_RULES_MAINTAINED_MIRROR_POLICY_ID", "CORE_RULES_REVIEW_AUDIT_ID"]
__all__ += ["CORE_RULES_REVIEW_AUDIT_PATH", "CORE_RULES_SOURCE_AUTHORITY_SCOPE"]
__all__ += ["EXPECTED_SOURCE_AUTHORITY_REGISTRY_SHA256", "CoreCommandPhaseSourceBuildError"]
__all__ += ["PROJECT_AUTHORITY_POLICY_ID", "MissionSourcePackageDefinition"]
__all__ += ["RuleEvidenceAuthority", "RuleEvidenceError", "RuleEvidenceKind"]
__all__ += ["RuleEvidencePayload", "RuleEvidenceRecord", "RuleSourcePackage"]
__all__ += ["SCOUT_ALTERNATION_FAQ_SOURCE_RULE_ID", "RuleVerificationStatus", "RulesetDescriptor"]
__all__ += ["SourceAuthorityRegistryError", "SourceAuthorityScope", "SourceCatalog"]
__all__ += ["SourceEvidenceCatalog", "_app_hidden_transcription_artifact_path"]
__all__ += ["_app_hidden_transcription_payload", "_canonical_payload_sha256"]
__all__ += ["_command_phase_evidence_observation_sha256"]
__all__ += ["_core_command_phase_source_artifact_path", "_core_command_phase_source_payload"]
__all__ += ["_core_rules_review_audit_context", "_core_stratagem_app_source_artifact_path"]
__all__ += ["_core_stratagem_app_source_payload", "_july_rules_update_artifact_path"]
__all__ += ["_july_rules_update_payload", "_observation_sha256", "_replace_evidence_records"]
__all__ += ["_universal_rule_payload", "app_core_rules_hidden_2026_08_09"]
__all__ += ["build_attached_units_source_payload", "build_attack_sequence_source_payload"]
__all__ += ["build_core_abilities_source_payload", "build_core_command_phase_source_payload"]
__all__ += ["build_fight_on_death_payloads", "build_movement_source_payload"]
__all__ += ["build_other_concepts_source_payload", "build_transports_source_payload", "cast"]
__all__ += ["chapter_approved_2026_27", "core_abilities", "core_abilities_2026_09"]
__all__ += ["core_attached_units_2026_09", "core_attack_sequence_2026_09"]
__all__ += ["core_command_phase_2026_08", "core_fight_on_death_2026_09"]
__all__ += ["core_movement_phase_2026_08", "core_other_concepts_2026_08", "core_rules"]
__all__ += ["core_stratagems", "core_stratagems_2026_08", "core_transports_2026_09"]
__all__ += ["july_rules_updates_2026_07", "load_source_authority_registry_from_json_bytes"]
__all__ += ["source_evidence_module"]
