from __future__ import annotations

import hashlib
import json
from typing import Final

import msgspec

from warhammer40k_core.rules.source_evidence import (
    LoadSupportStatus,
    RuleEvidenceAuthority,
    RuleEvidenceError,
    RuleEvidenceKind,
    RuleEvidenceRecord,
    RuleVerificationStatus,
    SemanticExecutionStatus,
)

ARTIFACT_SCHEMA: Final = "core-v2-core-stratagem-app-source-v2"
EXPECTED_SOURCE_PACKAGE_ID: Final = "gw-11e-core-stratagems"
EXPECTED_SOURCE_VERSION: Final = "reviewed-stratagems-observed-2026-09-02"
EXPECTED_OBSERVED_AT: Final = "2026-08-26T11:15:23-04:00"
EXPECTED_SOURCE_URL: Final = "https://www.40k.app/rules/15-stratagems"
EXPECTED_INSANE_BRAVERY_FAQ_SOURCE_URL: Final = "https://game-datamissions.com/11th/rules/changelog"
EXPECTED_INSANE_BRAVERY_FAQ_OBSERVED_AT: Final = "2026-09-02T12:30:09-04:00"
EXPECTED_INSANE_BRAVERY_FAQ_APP_VERSION: Final = "931"
PROJECT_AUTHORITY_POLICY_ID: Final = (
    "core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26"
)
MAINTAINED_MIRROR_AUTHORITY_POLICY_ID: Final = (
    "core-rules-source-policy:maintained-direct-app-data-mirrors:2026-09-02"
)
EXPECTED_REVIEW_AUDIT_ID: Final = "40k-app-core-rules-2026-08-25"
EXPECTED_MAINTAINED_MIRROR_AUDIT_ID: Final = "core-rules-maintained-app-mirrors-2026-09-02"
EXPECTED_MAINTAINED_MIRROR_AUDIT_ROW_ID: Final = "game-datamissions-core-rules-data-931"
EXPECTED_MAINTAINED_MIRROR_AUDIT_FINGERPRINT: Final = (
    "1c4cdfada35a93ef2773cbed06d9267175edb321423316d5f9dac29dc23b8668"
)
EXPECTED_CATEGORY_15_AUDIT_FINGERPRINT: Final = (
    "90d660a2388e7f6799e71fe8c2305d019409614b70ee9fcb962609851ab15f59"
)
EXPECTED_NUMBERING_FINDING_AUDIT_FINGERPRINT: Final = (
    "743ece521c82481891e362e74ca916da5b24910e2dbf75ee27c9aed133e9480d"
)
EXPECTED_CATEGORY_12_AUDIT_FINGERPRINT: Final = (
    "e993a6133af95dc2f1361b32dc95b7d9b7502eb4aabc226f9e5e6dff34b92a63"
)
EXPECTED_OFFICIAL_PDF_SHA256: Final = (
    "f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833"
)
EXPECTED_ARTIFACT_SHA256: Final = "25a89aadcee9ec31939dd08fedcec76e2bd1983aea1b94472a17c4721d89f17c"
EXPECTED_PACKAGE_HASH: Final = "f373b194b005a56b5caa0f52f540e26ddee45655ac9e89e8f8e85d4d642616d7"
EXPECTED_ANOMALY_OBSERVATION_SHA256: Final = (
    "561c686491968ed20a2a6dd257a5b34cc02b72b0bcb633356d0baf96f815cc46"
)
EXPECTED_ANOMALY_TRANSCRIPTION_SHA256: Final = (
    "b2a5f5ff431ab3728a163d8d785d3c21a2270b9fc5793444af5ec5f150098dff"
)
EXPECTED_ANOMALY_SOURCE_TEXT: Final = (
    "Because both RED**** units made charge moves this turn, they are both Fights First "
    "units this phase and are both eligible to make pile-in moves, even though the MONSTER "
    "is unengaged as it destroyed its charge target in the Charge phase using the Crushing "
    "Impact stratagem (15.06)."
)

EXPECTED_RULE_IDENTITY: Final = {
    "crushing-impact": (
        "15.05",
        "Crushing Impact",
        "gw-11e-core-stratagems:core:crushing-impact",
        "core:crushing-impact",
        "stratagem",
        "Charge Phase",
        1,
    ),
    "explosives": (
        "15.06",
        "Explosives",
        "gw-11e-core-stratagems:core:explosives",
        "core:explosives",
        "stratagem",
        "Shooting Phase",
        1,
    ),
    "rapid-ingress": (
        "15.07",
        "Rapid Ingress",
        "gw-11e-core-stratagems:core:rapid-ingress",
        "core:rapid-ingress",
        "stratagem",
        "Movement Phase",
        1,
    ),
    "fire-overwatch": (
        "15.08",
        "Fire Overwatch",
        "gw-11e-core-stratagems:core:fire-overwatch",
        "core:fire-overwatch",
        "stratagem",
        "Movement Phase",
        1,
    ),
    "snap-shooting": (
        "15.09",
        "Snap Shooting",
        "gw-11e-core-stratagems:rule:snap-shooting",
        "core:snap-shooting",
        "shooting_type",
        None,
        None,
    ),
    "insane-bravery": (
        "FAQ",
        "Insane Bravery",
        "gw-11e-core-stratagems:core:insane-bravery",
        "core:insane-bravery",
        "stratagem_faq",
        "Command Phase",
        1,
    ),
}
EXPECTED_TRANSCRIPTION_SHA256_BY_RULE_ID: Final = {
    "crushing-impact": "63fe27d984e7863a906d1ff7edeaef678fa69cdc1c6a7040869409749353e060",
    "explosives": "c3b1f80f88da3e8772eed3d8fa49694c0f2c2539498a74aadd1b39cc859f897f",
    "rapid-ingress": "2e9028ed2bf0c1fa19d7774ceb7bb81d415097e38b47c78ab67d7cff303955f6",
    "fire-overwatch": "7cbb6c048a5c5420b2209a7c585b6063dafebfbca4f1d6e52af607282c77c8f0",
    "snap-shooting": "d9a660775aab4e7e07277850b27f2930682a232115bc720c81cb1618b50c5545",
    "insane-bravery": "caf8973ed7c25c2c99db11bc0e489e3d9803300012b40b4f29eb878df54b1a25",
}
EXPECTED_SOURCE_OBSERVATION_SHA256_BY_RULE_ID: Final = {
    "crushing-impact": "329f378b3cb1f78f28f7f32047e01e2b78295d155c30df9fde775bf0cab3afa4",
    "explosives": "45c1a404c497f2d3d1cb0feb00ce09371fd3520bce8af43214930bc474dd9c41",
    "rapid-ingress": "42c4328d54aa18d826225dedd0b1e0043f4d8e3fe0f2e09d1ab12db7913314a6",
    "fire-overwatch": "6cfdfa59d51b3bc1302101ac70a142bc3926ac2f532fb035254f4cc08eb6f9a1",
    "snap-shooting": "b88a09f338d839344e4d589dcc17b658cf075d11f20c079a9c55297ed70d1a26",
    "insane-bravery": "11af8114a1e14df4c9e2d6f52425c29a46c17385791480dc364129b84fe77252",
}
EXPECTED_SEMANTIC_STATUS_BY_RULE_ID: Final = {
    "crushing-impact": "partial_engine_runtime",
    "explosives": "partial_engine_runtime",
    "rapid-ingress": "partial_engine_runtime",
    "fire-overwatch": "partial_engine_runtime",
    "snap-shooting": "partial_engine_runtime",
    "insane-bravery": "executable_engine_runtime",
}
EXPECTED_RUNTIME_CONSUMERS_BY_RULE_ID: Final = {
    "crushing-impact": (
        "warhammer40k_core.engine.stratagems_targeting:_target_binding_error",
        "warhammer40k_core.engine.stratagems_geometry:_crushing_impact_context_error",
        "warhammer40k_core.engine.stratagems_effect_handlers:_apply_crushing_impact_handler",
    ),
    "explosives": (
        "warhammer40k_core.engine.stratagems_geometry:_explosives_context_error",
        "warhammer40k_core.engine.stratagems_effect_handlers:_apply_explosives_handler",
    ),
    "rapid-ingress": (
        "warhammer40k_core.engine.stratagems_targeting:_rapid_ingress_unit_ids",
        "warhammer40k_core.engine.stratagems_core_handlers:_apply_rapid_ingress_handler",
        "warhammer40k_core.engine.stratagems_ingress:_apply_rapid_ingress_placement",
    ),
    "fire-overwatch": (
        "warhammer40k_core.engine.stratagems_eligibility:_handler_unavailable_reason",
        "warhammer40k_core.engine.stratagems_targeting:_fire_overwatch_target_binding_error",
        "warhammer40k_core.engine.stratagems_fire_overwatch:_apply_fire_overwatch_handler",
    ),
    "snap-shooting": (
        "warhammer40k_core.engine.phases.shooting_targeting:"
        "_snap_shooting_type_allowed_for_unit_target",
        "warhammer40k_core.engine.phases.shooting_declaration_validation:"
        "_attack_pools_or_validation",
        "warhammer40k_core.engine.attack_sequence_hit_wound:_roll_hit",
    ),
    "insane-bravery": (
        "warhammer40k_core.engine.stratagem_catalog:"
        "eleventh_edition_core_stratagem_catalog_records",
        "warhammer40k_core.engine.stratagems_targeting:_target_binding_error",
        "warhammer40k_core.engine.stratagems_apply:invalid_stratagem_target_proposal_status",
        "warhammer40k_core.engine.stratagems_apply:_apply_stratagem_use",
        "warhammer40k_core.engine.command_insane_bravery_authority:"
        "validate_loaded_command_auto_pass_authority",
    ),
}


class CoreStratagemAppSourceArtifactError(ValueError):
    """Raised when the reviewed Core Stratagem App-source artifact is invalid."""


class CoreStratagemSourceDocumentArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    document_id: str
    source_title: str
    source_platform: str
    provider_name: str
    source_url: str
    provider_non_affiliation_recorded: bool
    official_pdf_source_package_id: str
    official_pdf_document_id: str
    official_pdf_sha256: str
    supersession_scope: str


class CoreStratagemFaqSourceDocumentArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    document_id: str
    source_title: str
    source_platform: str
    provider_name: str
    source_url: str
    app_version: str
    observed_at: str
    provider_non_affiliation_recorded: bool
    project_authority_policy_id: str
    rule_source_ids: tuple[str, ...]


class CoreStratagemEvidenceContextArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    context_id: str
    evidence_kind: RuleEvidenceKind
    authority: RuleEvidenceAuthority
    project_authority_policy_id: str | None
    review_audit_id: str | None
    provider_name: str
    source_title: str
    source_platform: str
    observed_at: str | None
    app_version: str | None
    app_build: str | None
    capture_artifact_path: str | None
    capture_sha256: str | None
    official_corroborating_source_ids: tuple[str, ...]
    provider_non_affiliation_recorded: bool


class CoreStratagemEvidenceArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    evidence_id: str
    evidence_context_id: str
    rule_source_id: str
    source_url: str | None
    review_audit_row_id: str | None
    review_audit_source_observation_sha256: str | None
    transcription_sha256: str
    verification_status: RuleVerificationStatus
    observation_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]

    def to_rule_evidence_record(
        self,
        *,
        context: CoreStratagemEvidenceContextArtifact,
    ) -> RuleEvidenceRecord:
        return RuleEvidenceRecord(
            evidence_id=self.evidence_id,
            rule_source_id=self.rule_source_id,
            evidence_kind=context.evidence_kind,
            authority=context.authority,
            project_authority_policy_id=context.project_authority_policy_id,
            review_audit_id=context.review_audit_id,
            review_audit_row_id=self.review_audit_row_id,
            review_audit_source_observation_sha256=(self.review_audit_source_observation_sha256),
            provider_name=context.provider_name,
            source_title=context.source_title,
            source_platform=context.source_platform,
            source_url=self.source_url,
            observed_at=context.observed_at,
            app_version=context.app_version,
            app_build=context.app_build,
            capture_artifact_path=context.capture_artifact_path,
            capture_sha256=context.capture_sha256,
            transcription_sha256=self.transcription_sha256,
            official_corroborating_source_ids=context.official_corroborating_source_ids,
            verification_status=self.verification_status,
            provider_non_affiliation_recorded=context.provider_non_affiliation_recorded,
            observation_sha256=self.observation_sha256,
            load_support_status=self.load_support_status,
            semantic_execution_status=self.semantic_execution_status,
            runtime_consumer_ids=self.runtime_consumer_ids,
        )


class CoreStratagemSourceRuleArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    rule_id: str
    source_id: str
    runtime_rule_id: str
    section_id: str
    title: str
    kind: str
    phase_text: str | None
    command_point_cost: int | None
    target_text: str | None
    when_text: str
    effect_text: str
    restrictions_text: str | None
    source_text: str
    transcription_sha256: str
    source_observation_sha256: str
    evidence_ids: tuple[str, ...]
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class CoreStratagemNumberingAnomalyArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    anomaly_id: str
    section_id: str
    source_url: str
    observed_at: str
    referenced_title: str
    observed_reference_text: str
    stale_section_id: str
    resolved_section_id: str
    resolved_source_id: str
    resolution_basis: str
    project_authority_policy_id: str
    review_audit_id: str
    review_audit_row_id: str
    review_audit_source_observation_sha256: str
    related_review_finding_id: str
    related_review_finding_source_observation_sha256: str
    source_text: str
    transcription_sha256: str
    source_observation_sha256: str


class CoreStratagemAppSourcePackageArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    source_version: str
    source_document: CoreStratagemSourceDocumentArtifact
    faq_source_document: CoreStratagemFaqSourceDocumentArtifact
    evidence_contexts: tuple[CoreStratagemEvidenceContextArtifact, ...]
    rules: tuple[CoreStratagemSourceRuleArtifact, ...]
    evidence_records: tuple[CoreStratagemEvidenceArtifact, ...]
    numbering_anomalies: tuple[CoreStratagemNumberingAnomalyArtifact, ...]
    package_hash: str

    def validate(self) -> None:
        if self.artifact_schema != ARTIFACT_SCHEMA:
            raise CoreStratagemAppSourceArtifactError(
                "Core Stratagem App-source artifact schema is unsupported."
            )
        if (
            self.source_package_id,
            self.source_version,
        ) != (
            EXPECTED_SOURCE_PACKAGE_ID,
            EXPECTED_SOURCE_VERSION,
        ):
            raise CoreStratagemAppSourceArtifactError(
                "Core Stratagem App-source package identity drifted."
            )
        _validate_source_document(self.source_document)
        _validate_faq_source_document(self.faq_source_document)
        _validate_rules(self.rules)
        _validate_evidence(
            contexts=self.evidence_contexts,
            evidence_records=self.evidence_records,
            rules=self.rules,
        )
        _validate_numbering_anomalies(self.numbering_anomalies)
        _validate_sha256("package_hash", self.package_hash)
        if self.package_hash != core_stratagem_app_source_package_hash(self):
            raise CoreStratagemAppSourceArtifactError(
                "Core Stratagem App-source package hash is stale."
            )
        if self.package_hash != EXPECTED_PACKAGE_HASH:
            raise CoreStratagemAppSourceArtifactError(
                "Core Stratagem App-source package hash drifted from its reviewed pin."
            )

    def evidence_record_values(self) -> tuple[RuleEvidenceRecord, ...]:
        contexts_by_id = {context.context_id: context for context in self.evidence_contexts}
        return tuple(
            evidence.to_rule_evidence_record(context=contexts_by_id[evidence.evidence_context_id])
            for evidence in self.evidence_records
        )


def core_stratagem_app_source_artifact_from_json_bytes(
    raw: bytes,
) -> CoreStratagemAppSourcePackageArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=CoreStratagemAppSourcePackageArtifact)
    except msgspec.DecodeError as exc:
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem App-source artifact is invalid."
        ) from exc
    artifact.validate()
    return artifact


def core_stratagem_app_source_package_hash(
    artifact: CoreStratagemAppSourcePackageArtifact,
) -> str:
    payload = msgspec.to_builtins(artifact)
    if type(payload) is not dict:
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem App-source artifact payload is invalid."
        )
    payload["package_hash"] = ""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_source_document(source: CoreStratagemSourceDocumentArtifact) -> None:
    if (
        source.document_id,
        source.source_title,
        source.source_platform,
        source.provider_name,
        source.source_url,
        source.provider_non_affiliation_recorded,
        source.official_pdf_source_package_id,
        source.official_pdf_document_id,
        source.official_pdf_sha256,
        source.supersession_scope,
    ) != (
        "warhammer-40000-app-core-stratagems-observed-2026-08-26",
        "Warhammer 40,000 App Core Rules - Stratagems",
        "Web",
        "40k.app",
        EXPECTED_SOURCE_URL,
        True,
        "gw-11e-core-rules",
        "eng_01-06_warhammer40k_new40k_core_rules",
        EXPECTED_OFFICIAL_PDF_SHA256,
        "maintained_app_wording_and_provider_locators_15.05_through_15.09",
    ):
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem App-source document provenance drifted."
        )


def _validate_faq_source_document(source: CoreStratagemFaqSourceDocumentArtifact) -> None:
    if (
        source.document_id,
        source.source_title,
        source.source_platform,
        source.provider_name,
        source.source_url,
        source.app_version,
        source.observed_at,
        source.provider_non_affiliation_recorded,
        source.project_authority_policy_id,
        source.rule_source_ids,
    ) != (
        "game-datamissions-core-rules-data-931",
        "Game Datamissions Core Rules Data Changelog v931",
        "Web",
        "Game Datamissions",
        EXPECTED_INSANE_BRAVERY_FAQ_SOURCE_URL,
        EXPECTED_INSANE_BRAVERY_FAQ_APP_VERSION,
        EXPECTED_INSANE_BRAVERY_FAQ_OBSERVED_AT,
        True,
        MAINTAINED_MIRROR_AUTHORITY_POLICY_ID,
        ("gw-11e-core-stratagems:core:insane-bravery",),
    ):
        raise CoreStratagemAppSourceArtifactError(
            "Insane Bravery FAQ source-document provenance drifted."
        )


def _expected_evidence_ids(rule_id: str) -> tuple[str, str]:
    if rule_id == "insane-bravery":
        return (
            "core-v2-p15f-source-review:insane-bravery",
            "game-datamissions-core-rules-data-931:insane-bravery",
        )
    return (
        f"core-v2-p15d-source-review:{rule_id}",
        f"40k-app-core-stratagems-2026-08-26:{rule_id}",
    )


def _validate_rules(rules: tuple[CoreStratagemSourceRuleArtifact, ...]) -> None:
    if type(rules) is not tuple or tuple(rule.rule_id for rule in rules) != tuple(
        EXPECTED_RULE_IDENTITY
    ):
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem App-source rule inventory drifted."
        )
    for rule in rules:
        expected_identity = EXPECTED_RULE_IDENTITY[rule.rule_id]
        if (
            rule.section_id,
            rule.title,
            rule.source_id,
            rule.runtime_rule_id,
            rule.kind,
            rule.phase_text,
            rule.command_point_cost,
        ) != expected_identity:
            raise CoreStratagemAppSourceArtifactError(
                "Core Stratagem App-source rule identity drifted."
            )
        for field_name, value in (
            ("when_text", rule.when_text),
            ("effect_text", rule.effect_text),
            ("source_text", rule.source_text),
        ):
            _validate_non_empty_text(field_name, value)
        _validate_optional_text("target_text", rule.target_text)
        _validate_optional_text("restrictions_text", rule.restrictions_text)
        _validate_sha256("transcription_sha256", rule.transcription_sha256)
        if hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256:
            raise CoreStratagemAppSourceArtifactError(
                "Core Stratagem App-source transcription hash is stale."
            )
        if rule.transcription_sha256 != EXPECTED_TRANSCRIPTION_SHA256_BY_RULE_ID[rule.rule_id]:
            raise CoreStratagemAppSourceArtifactError(
                "Core Stratagem App source text drifted from its reviewed pin."
            )
        _validate_sha256("source_observation_sha256", rule.source_observation_sha256)
        if (
            rule.source_observation_sha256
            != EXPECTED_SOURCE_OBSERVATION_SHA256_BY_RULE_ID[rule.rule_id]
        ):
            raise CoreStratagemAppSourceArtifactError(
                "Core Stratagem App source observation drifted from its reviewed pin."
            )
        if (
            rule.load_support_status != "loaded"
            or rule.semantic_execution_status != EXPECTED_SEMANTIC_STATUS_BY_RULE_ID[rule.rule_id]
            or rule.runtime_consumer_ids != EXPECTED_RUNTIME_CONSUMERS_BY_RULE_ID[rule.rule_id]
        ):
            raise CoreStratagemAppSourceArtifactError(
                "Core Stratagem App-source support status drifted."
            )
        if rule.evidence_ids != _expected_evidence_ids(rule.rule_id):
            raise CoreStratagemAppSourceArtifactError(
                "Core Stratagem App-source evidence linkage drifted."
            )


def _validate_evidence(
    *,
    contexts: tuple[CoreStratagemEvidenceContextArtifact, ...],
    evidence_records: tuple[CoreStratagemEvidenceArtifact, ...],
    rules: tuple[CoreStratagemSourceRuleArtifact, ...],
) -> None:
    contexts_by_id = {context.context_id: context for context in contexts}
    if len(contexts_by_id) != len(contexts) or tuple(contexts_by_id) != (
        "core-v2-p15d-project-source-review",
        "40k-app-core-stratagems-observed-2026-08-26",
        "core-v2-p15f-project-source-review",
        "game-datamissions-core-rules-data-931",
    ):
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem App-source evidence contexts drifted."
        )
    project_review = contexts_by_id["core-v2-p15d-project-source-review"]
    if (
        project_review.evidence_kind,
        project_review.authority,
        project_review.project_authority_policy_id,
        project_review.review_audit_id,
        project_review.provider_name,
        project_review.source_title,
        project_review.source_platform,
        project_review.observed_at,
        project_review.app_version,
        project_review.app_build,
        project_review.capture_artifact_path,
        project_review.capture_sha256,
        project_review.official_corroborating_source_ids,
        project_review.provider_non_affiliation_recorded,
    ) != (
        "project_reviewed_app_transcription",
        "unverified_transcription_only",
        None,
        None,
        "CORE V2 Source Review",
        "Reviewed transcription of 40k.app Core Stratagems",
        "Repository",
        None,
        None,
        None,
        None,
        None,
        (),
        False,
    ):
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem project-reviewed transcription provenance drifted."
        )
    mirror = contexts_by_id["40k-app-core-stratagems-observed-2026-08-26"]
    if (
        mirror.evidence_kind,
        mirror.authority,
        mirror.project_authority_policy_id,
        mirror.review_audit_id,
        mirror.provider_name,
        mirror.source_title,
        mirror.source_platform,
        mirror.observed_at,
        mirror.app_version,
        mirror.app_build,
        mirror.capture_artifact_path,
        mirror.capture_sha256,
        mirror.official_corroborating_source_ids,
        mirror.provider_non_affiliation_recorded,
    ) != (
        "third_party_mirror",
        "project_authoritative_app_mirror",
        PROJECT_AUTHORITY_POLICY_ID,
        EXPECTED_REVIEW_AUDIT_ID,
        "40k.app",
        "40k.app Core Rules - Stratagems",
        "Web",
        EXPECTED_OBSERVED_AT,
        None,
        None,
        None,
        None,
        (),
        True,
    ):
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem authoritative-mirror provenance drifted."
        )
    faq_project_review = contexts_by_id["core-v2-p15f-project-source-review"]
    if (
        faq_project_review.evidence_kind,
        faq_project_review.authority,
        faq_project_review.project_authority_policy_id,
        faq_project_review.review_audit_id,
        faq_project_review.provider_name,
        faq_project_review.source_title,
        faq_project_review.source_platform,
        faq_project_review.observed_at,
        faq_project_review.app_version,
        faq_project_review.app_build,
        faq_project_review.capture_artifact_path,
        faq_project_review.capture_sha256,
        faq_project_review.official_corroborating_source_ids,
        faq_project_review.provider_non_affiliation_recorded,
    ) != (
        "project_reviewed_app_transcription",
        "unverified_transcription_only",
        None,
        None,
        "CORE V2 Source Review",
        "Reviewed transcription of the Insane Bravery FAQ",
        "Repository",
        None,
        None,
        None,
        None,
        None,
        (),
        False,
    ):
        raise CoreStratagemAppSourceArtifactError(
            "Insane Bravery project-reviewed transcription provenance drifted."
        )
    faq_mirror = contexts_by_id["game-datamissions-core-rules-data-931"]
    if (
        faq_mirror.evidence_kind,
        faq_mirror.authority,
        faq_mirror.project_authority_policy_id,
        faq_mirror.review_audit_id,
        faq_mirror.provider_name,
        faq_mirror.source_title,
        faq_mirror.source_platform,
        faq_mirror.observed_at,
        faq_mirror.app_version,
        faq_mirror.app_build,
        faq_mirror.capture_artifact_path,
        faq_mirror.capture_sha256,
        faq_mirror.official_corroborating_source_ids,
        faq_mirror.provider_non_affiliation_recorded,
    ) != (
        "third_party_mirror",
        "project_authoritative_app_mirror",
        MAINTAINED_MIRROR_AUTHORITY_POLICY_ID,
        EXPECTED_MAINTAINED_MIRROR_AUDIT_ID,
        "Game Datamissions",
        "Game Datamissions Core Rules Data Changelog v931",
        "Web",
        None,
        EXPECTED_INSANE_BRAVERY_FAQ_APP_VERSION,
        None,
        None,
        None,
        (),
        True,
    ):
        raise CoreStratagemAppSourceArtifactError(
            "Insane Bravery authoritative-mirror provenance drifted."
        )
    evidence_by_id = {evidence.evidence_id: evidence for evidence in evidence_records}
    expected_evidence_ids = tuple(
        evidence_id for rule in rules for evidence_id in _expected_evidence_ids(rule.rule_id)
    )
    if (
        len(evidence_by_id) != len(evidence_records)
        or tuple(evidence_by_id) != expected_evidence_ids
    ):
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem App-source evidence inventory drifted."
        )
    expected_context_id_by_evidence_id = {
        evidence_id: (
            "core-v2-p15f-project-source-review"
            if evidence_id.startswith("core-v2-p15f-source-review:")
            else "game-datamissions-core-rules-data-931"
            if evidence_id.startswith("game-datamissions-core-rules-data-931:")
            else "core-v2-p15d-project-source-review"
            if evidence_id.startswith("core-v2-p15d-source-review:")
            else "40k-app-core-stratagems-observed-2026-08-26"
        )
        for evidence_id in expected_evidence_ids
    }
    if any(
        evidence.evidence_context_id != expected_context_id_by_evidence_id[evidence.evidence_id]
        for evidence in evidence_records
    ):
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem App-source evidence context linkage drifted."
        )
    records_by_id: dict[str, RuleEvidenceRecord] = {}
    for evidence in evidence_records:
        try:
            context = contexts_by_id[evidence.evidence_context_id]
        except KeyError as exc:
            raise CoreStratagemAppSourceArtifactError(
                "Core Stratagem evidence context is unknown."
            ) from exc
        try:
            records_by_id[evidence.evidence_id] = evidence.to_rule_evidence_record(context=context)
        except RuleEvidenceError as exc:
            raise CoreStratagemAppSourceArtifactError(
                "Core Stratagem App-source evidence is invalid."
            ) from exc
    for rule in rules:
        try:
            records = tuple(records_by_id[evidence_id] for evidence_id in rule.evidence_ids)
        except KeyError as exc:
            raise CoreStratagemAppSourceArtifactError(
                "Core Stratagem App-source evidence linkage is incomplete."
            ) from exc
        project_record, mirror_record = records
        if (
            project_record.evidence_kind,
            project_record.authority,
            project_record.project_authority_policy_id,
            project_record.review_audit_id,
            project_record.source_url,
            project_record.observed_at,
            project_record.verification_status,
        ) != (
            "project_reviewed_app_transcription",
            "unverified_transcription_only",
            None,
            None,
            None,
            None,
            "unverified",
        ):
            raise CoreStratagemAppSourceArtifactError(
                "Core Stratagem project-reviewed evidence drifted."
            )
        if rule.rule_id == "insane-bravery":
            expected_policy_id = MAINTAINED_MIRROR_AUTHORITY_POLICY_ID
            expected_audit_id = EXPECTED_MAINTAINED_MIRROR_AUDIT_ID
            expected_provider_name = "Game Datamissions"
            expected_source_url = EXPECTED_INSANE_BRAVERY_FAQ_SOURCE_URL
            expected_observed_at = None
            expected_app_version = EXPECTED_INSANE_BRAVERY_FAQ_APP_VERSION
            expected_review_row = EXPECTED_MAINTAINED_MIRROR_AUDIT_ROW_ID
            expected_review_fingerprint = EXPECTED_MAINTAINED_MIRROR_AUDIT_FINGERPRINT
        else:
            expected_policy_id = PROJECT_AUTHORITY_POLICY_ID
            expected_audit_id = EXPECTED_REVIEW_AUDIT_ID
            expected_provider_name = "40k.app"
            expected_source_url = EXPECTED_SOURCE_URL
            expected_observed_at = EXPECTED_OBSERVED_AT
            expected_app_version = None
            expected_review_row = (
                "finding:official-pdf-mirror-order-15-05-15-06"
                if rule.rule_id in {"crushing-impact", "explosives"}
                else "category:15"
            )
            expected_review_fingerprint = (
                EXPECTED_NUMBERING_FINDING_AUDIT_FINGERPRINT
                if rule.rule_id in {"crushing-impact", "explosives"}
                else EXPECTED_CATEGORY_15_AUDIT_FINGERPRINT
            )
        if (
            project_record.evidence_id,
            mirror_record.evidence_id,
            mirror_record.evidence_kind,
            mirror_record.authority,
            mirror_record.project_authority_policy_id,
            mirror_record.review_audit_id,
            mirror_record.provider_name,
            mirror_record.source_url,
            mirror_record.observed_at,
            mirror_record.app_version,
            mirror_record.review_audit_row_id,
            mirror_record.review_audit_source_observation_sha256,
            mirror_record.verification_status,
            mirror_record.observation_sha256,
        ) != (
            _expected_evidence_ids(rule.rule_id)[0],
            _expected_evidence_ids(rule.rule_id)[1],
            "third_party_mirror",
            "project_authoritative_app_mirror",
            expected_policy_id,
            expected_audit_id,
            expected_provider_name,
            expected_source_url,
            expected_observed_at,
            expected_app_version,
            expected_review_row,
            expected_review_fingerprint,
            "authoritative_app_mirror",
            rule.source_observation_sha256,
        ):
            raise CoreStratagemAppSourceArtifactError(
                "Core Stratagem authoritative-mirror evidence drifted."
            )
        if any(
            (
                record.rule_source_id,
                record.transcription_sha256,
                record.load_support_status,
                record.semantic_execution_status,
                record.runtime_consumer_ids,
            )
            != (
                rule.source_id,
                rule.transcription_sha256,
                rule.load_support_status,
                rule.semantic_execution_status,
                rule.runtime_consumer_ids,
            )
            for record in records
        ):
            raise CoreStratagemAppSourceArtifactError(
                "Core Stratagem source/evidence support linkage drifted."
            )


def _validate_numbering_anomalies(
    anomalies: tuple[CoreStratagemNumberingAnomalyArtifact, ...],
) -> None:
    if type(anomalies) is not tuple or len(anomalies) != 1:
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem numbering-anomaly inventory drifted."
        )
    anomaly = anomalies[0]
    if (
        anomaly.anomaly_id,
        anomaly.section_id,
        anomaly.source_url,
        anomaly.observed_at,
        anomaly.referenced_title,
        anomaly.observed_reference_text,
        anomaly.stale_section_id,
        anomaly.resolved_section_id,
        anomaly.resolved_source_id,
        anomaly.resolution_basis,
        anomaly.project_authority_policy_id,
        anomaly.review_audit_id,
        anomaly.review_audit_row_id,
        anomaly.review_audit_source_observation_sha256,
        anomaly.related_review_finding_id,
        anomaly.related_review_finding_source_observation_sha256,
        anomaly.source_text,
    ) != (
        "gw-11e-core-stratagems:anomaly:fight-example-crushing-impact-cross-reference",
        "12.01",
        "https://www.40k.app/rules/12-fight-phase",
        EXPECTED_OBSERVED_AT,
        "Crushing Impact",
        "using the Crushing Impact stratagem (15.06).",
        "15.06",
        "15.05",
        "gw-11e-core-stratagems:core:crushing-impact",
        "stable_title_and_complete_operative_text",
        PROJECT_AUTHORITY_POLICY_ID,
        EXPECTED_REVIEW_AUDIT_ID,
        "category:12",
        EXPECTED_CATEGORY_12_AUDIT_FINGERPRINT,
        "finding:official-pdf-mirror-order-15-05-15-06",
        EXPECTED_NUMBERING_FINDING_AUDIT_FINGERPRINT,
        EXPECTED_ANOMALY_SOURCE_TEXT,
    ):
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem numbering-anomaly resolution drifted."
        )
    _validate_sha256("transcription_sha256", anomaly.transcription_sha256)
    if (
        hashlib.sha256(anomaly.source_text.encode()).hexdigest() != anomaly.transcription_sha256
        or anomaly.transcription_sha256 != EXPECTED_ANOMALY_TRANSCRIPTION_SHA256
    ):
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem numbering-anomaly transcription hash drifted."
        )
    _validate_sha256("source_observation_sha256", anomaly.source_observation_sha256)
    payload = msgspec.to_builtins(anomaly)
    if type(payload) is not dict:
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem numbering anomaly payload is invalid."
        )
    payload["source_observation_sha256"] = ""
    computed = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if (
        anomaly.source_observation_sha256 != computed
        or anomaly.source_observation_sha256 != EXPECTED_ANOMALY_OBSERVATION_SHA256
    ):
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem numbering-anomaly observation hash drifted."
        )


def _validate_non_empty_text(field_name: str, value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise CoreStratagemAppSourceArtifactError(
            f"Core Stratagem App-source {field_name} must be non-empty stripped text."
        )
    return value


def _validate_optional_text(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    return _validate_non_empty_text(field_name, value)


def _validate_sha256(field_name: str, value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CoreStratagemAppSourceArtifactError(
            f"Core Stratagem App-source {field_name} must be a lowercase SHA-256 digest."
        )
    return value


__all__ = (
    "EXPECTED_ANOMALY_OBSERVATION_SHA256",
    "EXPECTED_ANOMALY_SOURCE_TEXT",
    "EXPECTED_ANOMALY_TRANSCRIPTION_SHA256",
    "EXPECTED_ARTIFACT_SHA256",
    "EXPECTED_CATEGORY_12_AUDIT_FINGERPRINT",
    "EXPECTED_CATEGORY_15_AUDIT_FINGERPRINT",
    "EXPECTED_INSANE_BRAVERY_FAQ_APP_VERSION",
    "EXPECTED_INSANE_BRAVERY_FAQ_OBSERVED_AT",
    "EXPECTED_INSANE_BRAVERY_FAQ_SOURCE_URL",
    "EXPECTED_MAINTAINED_MIRROR_AUDIT_FINGERPRINT",
    "EXPECTED_MAINTAINED_MIRROR_AUDIT_ID",
    "EXPECTED_MAINTAINED_MIRROR_AUDIT_ROW_ID",
    "EXPECTED_NUMBERING_FINDING_AUDIT_FINGERPRINT",
    "EXPECTED_OBSERVED_AT",
    "EXPECTED_PACKAGE_HASH",
    "EXPECTED_RUNTIME_CONSUMERS_BY_RULE_ID",
    "EXPECTED_SEMANTIC_STATUS_BY_RULE_ID",
    "EXPECTED_SOURCE_OBSERVATION_SHA256_BY_RULE_ID",
    "EXPECTED_SOURCE_PACKAGE_ID",
    "EXPECTED_SOURCE_URL",
    "EXPECTED_SOURCE_VERSION",
    "EXPECTED_TRANSCRIPTION_SHA256_BY_RULE_ID",
    "MAINTAINED_MIRROR_AUTHORITY_POLICY_ID",
    "CoreStratagemAppSourceArtifactError",
    "CoreStratagemAppSourcePackageArtifact",
    "CoreStratagemFaqSourceDocumentArtifact",
    "CoreStratagemNumberingAnomalyArtifact",
    "CoreStratagemSourceRuleArtifact",
    "core_stratagem_app_source_artifact_from_json_bytes",
    "core_stratagem_app_source_package_hash",
)
