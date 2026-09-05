from __future__ import annotations

import copy
import hashlib
import json
from typing import Final, cast

import msgspec

from warhammer40k_core.rules.source_evidence import (
    LoadSupportStatus,
    RuleEvidenceAuthority,
    RuleEvidenceKind,
    RuleEvidenceRecord,
    RuleVerificationStatus,
    SemanticExecutionStatus,
)

ARTIFACT_SCHEMA: Final = "core-v2-core-abilities-source-v1"
EXPECTED_SOURCE_PACKAGE_ID: Final = "gw-11e-core-abilities"
EXPECTED_SOURCE_VERSION: Final = "game-datamissions-v931-observed-2026-09-02"
EXPECTED_DOCUMENT_IDENTITY: Final = (
    "game-datamissions-core-rules-data-931",
    "https://game-datamissions.com/11th/rules/changelog",
    "2026-09-02T12:30:09-04:00",
    "931",
)
EXPECTED_RULE_IDENTITY: Final = (
    "deadly-demise",
    "core-deadly-demise",
    "core:deadly-demise",
    "gw-11e-core-abilities:core:deadly-demise",
    "24.08",
    "DEADLY DEMISE",
    "after_model_destroyed",
    "a5ca19362fe04090968372fe83f3398cfa1236d52d69a2a87ad6ca555f429ff4",
)
EXPECTED_SCOUT_ALTERNATION_RULE_IDENTITY: Final = (
    "alternating-scout-moves-faq",
    "core-scouts",
    "core:scouts",
    "gw-11e-core-abilities:faq:alternating-scout-moves",
    "FAQ",
    "ALTERNATING SCOUT MOVES",
    "before_battle",
    "e2e4740b73d2ea159eecb42da7246c399dc157bef038a623f9ecd94d07ba1296",
)
EXPECTED_HAZARDOUS_RULE_IDENTITY: Final = (
    "hazardous",
    "core-hazardous",
    "core:hazardous",
    "gw-11e-core-abilities:core:hazardous",
    "24.15",
    "HAZARDOUS",
    "after_unit_attacks_resolved",
    "2ecefae469a748d8f5b337dcbbb4a1c3211bfa4c3555626fbbd05ee6fbde3832",
)
EXPECTED_DESCRIPTORS: Final = (
    "Each time a model with this ability is destroyed, after the units embarked within it "
    "(if any) have made their emergency disembark moves",
    'roll one D6. On a 6, that model suffers a deadly demise; each unit within 6" of that '
    "model suffers a number of mortal wounds denoted by X (if this is a random number, roll "
    'separately for each unit within 6").',
    "This ability always takes the form Deadly Demise X.",
)
EXPECTED_SCOUT_ALTERNATION_DESCRIPTORS: Final = (
    "If both players have units with pre-battle rules to resolve",
    "players alternate resolving those units, starting with the player who will take the first "
    "turn",
    "skip a player only when that player has no unresolved pre-battle rule",
)
EXPECTED_HAZARDOUS_DESCRIPTORS: Final = (
    "Each time a unit is selected to shoot or selected to fight, after that unit has resolved "
    "all of its attacks",
    "make a number of hazard rolls for that unit equal to the number of Hazardous weapons "
    "selected in the Select Weapons step",
    "each selected physical Hazardous weapon instance contributes one roll; make all hazard "
    "rolls simultaneously under 06.03",
)
EXPECTED_OBSERVATION_SHA256S: Final = (
    "18455fe967731b81b8ceacbe9e0121c3750b6bf648e4ec3a781113aaf5b12511",
    "3b3c615e97dab76873c0ab7974cf593480baa4a028eb88a1312254d0c3a6252b",
    "4df59af220872b1b09a3dcd36acef6b792b5e8c11245bd6ca2bea2f12433e9fe",
    "cb6c3244b50cff6017b30f269dff2530f1a8c8a461627710cc149064034d1453",
    "a80ec4f83e554f7004a396a7363977db41f9ca0e3a8675df1c0163bab3967ffd",
    "8292a0b2aaa7640ee6b82b2dca9e822aa2ce26d59759dfb72a276a9e63b77e1b",
)
EXPECTED_PACKAGE_HASH: Final = "ceda170f6ff51083eb2976ea97ee4d9096095dc3276d25ff7335d1cacabb9bfb"


class CoreAbilitiesSourceArtifactError(ValueError):
    """Raised when the reviewed Core Abilities source artifact is invalid."""


class CoreAbilitiesSourceDocumentArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    document_id: str
    source_title: str
    source_url: str
    observed_at: str
    app_version: str
    project_authority_policy_id: str


class CoreAbilitiesSourceRuleArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    rule_id: str
    runtime_ability_id: str
    runtime_handler_id: str
    source_id: str
    section_id: str
    section_heading: str
    source_text: str
    when_descriptor: str
    effect_descriptor: str
    restrictions_descriptor: str
    trigger_kind: str
    transcription_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class CoreAbilitiesEvidenceArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    evidence_id: str
    rule_source_id: str
    evidence_kind: RuleEvidenceKind
    authority: RuleEvidenceAuthority
    project_authority_policy_id: str | None
    review_audit_id: str | None
    review_audit_row_id: str | None
    review_audit_source_observation_sha256: str | None
    provider_name: str
    source_title: str
    source_platform: str
    source_url: str | None
    observed_at: str | None
    app_version: str | None
    app_build: str | None
    capture_artifact_path: str | None
    capture_sha256: str | None
    transcription_sha256: str
    official_corroborating_source_ids: tuple[str, ...]
    verification_status: RuleVerificationStatus
    provider_non_affiliation_recorded: bool
    observation_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]

    def to_rule_evidence_record(self) -> RuleEvidenceRecord:
        return RuleEvidenceRecord(
            evidence_id=self.evidence_id,
            rule_source_id=self.rule_source_id,
            evidence_kind=self.evidence_kind,
            authority=self.authority,
            project_authority_policy_id=self.project_authority_policy_id,
            review_audit_id=self.review_audit_id,
            review_audit_row_id=self.review_audit_row_id,
            review_audit_source_observation_sha256=self.review_audit_source_observation_sha256,
            provider_name=self.provider_name,
            source_title=self.source_title,
            source_platform=self.source_platform,
            source_url=self.source_url,
            observed_at=self.observed_at,
            app_version=self.app_version,
            app_build=self.app_build,
            capture_artifact_path=self.capture_artifact_path,
            capture_sha256=self.capture_sha256,
            transcription_sha256=self.transcription_sha256,
            official_corroborating_source_ids=self.official_corroborating_source_ids,
            verification_status=self.verification_status,
            provider_non_affiliation_recorded=self.provider_non_affiliation_recorded,
            observation_sha256=self.observation_sha256,
            load_support_status=self.load_support_status,
            semantic_execution_status=self.semantic_execution_status,
            runtime_consumer_ids=self.runtime_consumer_ids,
        )


class CoreAbilitiesSourcePackageArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    source_version: str
    source_document: CoreAbilitiesSourceDocumentArtifact
    rules: tuple[CoreAbilitiesSourceRuleArtifact, ...]
    evidence: tuple[CoreAbilitiesEvidenceArtifact, ...]
    package_hash: str


def _sha256_payload(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def core_abilities_source_artifact_from_json_bytes(
    raw: bytes,
) -> CoreAbilitiesSourcePackageArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=CoreAbilitiesSourcePackageArtifact)
    except msgspec.DecodeError as exc:
        raise CoreAbilitiesSourceArtifactError(
            "Core Abilities source artifact schema is invalid."
        ) from exc
    if len(artifact.rules) != 3:
        raise CoreAbilitiesSourceArtifactError(
            "Core Abilities source artifact drifted from its reviewed identity."
        )
    actual_document_identity = (
        artifact.source_document.document_id,
        artifact.source_document.source_url,
        artifact.source_document.observed_at,
        artifact.source_document.app_version,
    )
    actual_rule_identities = tuple(
        (
            rule.rule_id,
            rule.runtime_ability_id,
            rule.runtime_handler_id,
            rule.source_id,
            rule.section_id,
            rule.section_heading,
            rule.trigger_kind,
            rule.transcription_sha256,
        )
        for rule in artifact.rules
    )
    actual_descriptors = tuple(
        (
            rule.when_descriptor,
            rule.effect_descriptor,
            rule.restrictions_descriptor,
        )
        for rule in artifact.rules
    )
    rules_by_source_id = {rule.source_id: rule for rule in artifact.rules}
    if (
        artifact.artifact_schema != ARTIFACT_SCHEMA
        or artifact.source_package_id != EXPECTED_SOURCE_PACKAGE_ID
        or artifact.source_version != EXPECTED_SOURCE_VERSION
        or actual_document_identity != EXPECTED_DOCUMENT_IDENTITY
        or actual_rule_identities
        != (
            EXPECTED_RULE_IDENTITY,
            EXPECTED_SCOUT_ALTERNATION_RULE_IDENTITY,
            EXPECTED_HAZARDOUS_RULE_IDENTITY,
        )
        or actual_descriptors
        != (
            EXPECTED_DESCRIPTORS,
            EXPECTED_SCOUT_ALTERNATION_DESCRIPTORS,
            EXPECTED_HAZARDOUS_DESCRIPTORS,
        )
        or any(
            hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256
            for rule in artifact.rules
        )
        or len(artifact.evidence) != 6
        or any(
            evidence.rule_source_id not in rules_by_source_id
            or evidence.transcription_sha256
            != rules_by_source_id[evidence.rule_source_id].transcription_sha256
            for evidence in artifact.evidence
        )
        or tuple(evidence.observation_sha256 for evidence in artifact.evidence)
        != EXPECTED_OBSERVATION_SHA256S
        or artifact.package_hash != EXPECTED_PACKAGE_HASH
    ):
        raise CoreAbilitiesSourceArtifactError(
            "Core Abilities source artifact drifted from its reviewed identity."
        )
    decoded_payload: object = json.loads(raw)
    if type(decoded_payload) is not dict:
        raise CoreAbilitiesSourceArtifactError("Core Abilities source artifact must be an object.")
    payload = copy.deepcopy(cast(dict[str, object], decoded_payload))
    payload["package_hash"] = ""
    if _sha256_payload(payload) != artifact.package_hash:
        raise CoreAbilitiesSourceArtifactError(
            "Core Abilities source artifact package hash is stale."
        )
    try:
        for evidence in artifact.evidence:
            evidence.to_rule_evidence_record()
    except ValueError as exc:
        raise CoreAbilitiesSourceArtifactError(
            "Core Abilities source evidence is invalid."
        ) from exc
    return artifact


__all__ = (
    "EXPECTED_DESCRIPTORS",
    "EXPECTED_DOCUMENT_IDENTITY",
    "EXPECTED_HAZARDOUS_DESCRIPTORS",
    "EXPECTED_HAZARDOUS_RULE_IDENTITY",
    "EXPECTED_OBSERVATION_SHA256S",
    "EXPECTED_PACKAGE_HASH",
    "EXPECTED_RULE_IDENTITY",
    "EXPECTED_SCOUT_ALTERNATION_DESCRIPTORS",
    "EXPECTED_SCOUT_ALTERNATION_RULE_IDENTITY",
    "CoreAbilitiesSourceArtifactError",
    "CoreAbilitiesSourcePackageArtifact",
    "CoreAbilitiesSourceRuleArtifact",
    "core_abilities_source_artifact_from_json_bytes",
)
