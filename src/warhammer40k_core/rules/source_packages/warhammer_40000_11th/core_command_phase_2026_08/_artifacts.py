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

ARTIFACT_SCHEMA: Final = "core-v2-command-phase-source-v2"
EXPECTED_SOURCE_PACKAGE_ID: Final = "gw-11e-core-command-phase"
EXPECTED_SOURCE_VERSION: Final = "40k-app-search-index-observed-2026-08-26"
EXPECTED_CATEGORY_URL: Final = "https://www.40k.app/rules/08-command-phase"
EXPECTED_CATEGORY_OBSERVED_AT: Final = "2026-08-25T00:00:00-04:00"
EXPECTED_SEARCH_INDEX_URL: Final = "https://www.40k.app/rules"
EXPECTED_SEARCH_INDEX_OBSERVED_AT: Final = "2026-08-26T14:49:10-04:00"
EXPECTED_SEARCH_INDEX_OBSERVATION_ID: Final = "40k-app-command-phase-search-index-2026-08-26"
EXPECTED_SEARCH_INDEX_OBSERVATION_ROW_ID: Final = "heading-sequence:command-phase"
EXPECTED_SEARCH_INDEX_OBSERVATION_SCOPE: Final = "command_phase_five_heading_sequence_only"
EXPECTED_SEARCH_INDEX_NORMALIZED_TEXT: Final = (
    "START OF COMMAND PHASE\nGAIN CORE CP\nBATTLE-SHOCK\nCOMMAND ABILITIES\nEND OF COMMAND PHASE"
)
EXPECTED_SEARCH_INDEX_SEQUENCE_TRANSCRIPTION_SHA256: Final = (
    "3ab49c279f743d16d6a122b6b3d3ea42736bd64acf2009b61e5b946f45a03a4c"
)
EXPECTED_SEARCH_INDEX_SOURCE_OBSERVATION_SHA256: Final = (
    "e646d81ba284b1a4b5572b96d68cbfca52ef8cdf15cedf7c2c69ae8b5066c0ab"
)
EXPECTED_REVIEW_AUDIT_ID: Final = "40k-app-core-rules-2026-08-25"
EXPECTED_CATEGORY_AUDIT_FINGERPRINT: Final = (
    "0920fa00c1f4ecbc9e46795c1d72695872b61e7577eeaa693c57eb12c26c871e"
)
PROJECT_AUTHORITY_POLICY_ID: Final = (
    "core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26"
)
EXPECTED_OFFICIAL_PDF_SOURCE_ID: Final = "gw-11e-core-rules:manifest:local-core-rules-pdf"
EXPECTED_OFFICIAL_PDF_PATH: Final = (
    "docs/source_rules/eng_01-06_warhammer40k_new40k_core_rules-was6fbu1ix-hfewhmxyiy.pdf"
)
EXPECTED_OFFICIAL_PDF_SHA256: Final = (
    "f6a2443a44627ac5f0ef08407d29aa5ec7e97339998f05bc35f3ae37bf276833"
)
EXPECTED_ARTIFACT_SHA256: Final = "78b2264047e263ab5537c71c7d1be681874bdda31191816b6b297eb9a39425e6"
EXPECTED_PACKAGE_HASH: Final = "8785dda65406ce76add419f29263be499239122e1330941ab55a1dc3e6f10127"

EXPECTED_SEARCH_INDEX_HEADINGS: Final = (
    ("start-of-command-phase", 1, "START OF COMMAND PHASE"),
    ("gain-core-cp", 2, "GAIN CORE CP"),
    ("battle-shock", 3, "BATTLE-SHOCK"),
    ("command-abilities", 4, "COMMAND ABILITIES"),
    ("end-of-command-phase", 5, "END OF COMMAND PHASE"),
)
EXPECTED_SEARCH_INDEX_HEADING_SHA256_BY_HEADING_ID: Final = {
    "start-of-command-phase": "c7076d22487eaacd4966ce616ed23632f73c1c1e77e97264779f58571855cd33",
    "gain-core-cp": "15b5a4c0e0184c03730be6b15d9aad113b1b59bb262028d00173ea5475f7a42f",
    "battle-shock": "621c1dac0261aaeb2443a843f9d4dd05d253f6ac01a6e251620739eece408e56",
    "command-abilities": "f4ea3d1b71326aa37f7fa0d10387f5d36584781ec17cc6bbd8ccb431626265f2",
    "end-of-command-phase": "2783396269169e5333be1049e5cb0ca511b6601ecf3d650668316155988dca01",
}

EXPECTED_RULE_IDENTITY: Final = {
    "start-of-command-phase": (
        "08.01",
        1,
        "START OF COMMAND PHASE",
        "gw-11e-core-rules:command-phase:start-of-command-phase",
        "Rules that are triggered at the start of the Command phase are resolved now.",
        (
            "warhammer40k_core.engine.command_phase_start_authority:"
            "resolve_command_phase_start_boundary",
        ),
        "executable_engine_runtime",
    ),
    "gain-core-cp": (
        "08.02",
        2,
        "GAIN CORE CP",
        "gw-11e-core-rules:command-phase:gain-core-cp",
        "Both players gain 1 Command Point (CP).",
        ("warhammer40k_core.engine.phases.command:_resolve_gain_core_command_points_step",),
        "executable_engine_runtime",
    ),
    "battle-shock": (
        "08.03",
        3,
        "BATTLE-SHOCK",
        "gw-11e-core-rules:command-phase:battle-shock",
        (
            "The active player must now make one battle-shock roll (01.07) for each unit in their "
            "army that fulfils one or both of the following conditions:\n"
            "- That unit is currently battle-shocked.\n"
            "- That unit is at, or below, half-strength.\n"
            "If a unit was battle-shocked at the start of this step and its battle-shock roll "
            "during this step succeeds, it is no longer battle-shocked."
        ),
        (
            "warhammer40k_core.engine.phases.command:_resolve_battle_shock_step",
            "warhammer40k_core.engine.battle_shock:collect_battle_shock_test_requests",
            "warhammer40k_core.engine.battle_shock_resolution:"
            "record_battle_shock_result_and_outcome_events",
        ),
        "partial_engine_runtime",
    ),
}
EXPECTED_TRANSCRIPTION_SHA256_BY_RULE_ID: Final = {
    "start-of-command-phase": ("c7076d22487eaacd4966ce616ed23632f73c1c1e77e97264779f58571855cd33"),
    "gain-core-cp": "15b5a4c0e0184c03730be6b15d9aad113b1b59bb262028d00173ea5475f7a42f",
    "battle-shock": "621c1dac0261aaeb2443a843f9d4dd05d253f6ac01a6e251620739eece408e56",
}
EXPECTED_OFFICIAL_PDF_TRANSCRIPTION_SHA256_BY_RULE_ID: Final = {
    "start-of-command-phase": ("539a37c85bcb22ebe08ae017a6e926489bbc8b311680d80514d5151855ed1c31"),
    "gain-core-cp": "6a09ea8b545e04dfbb0755408986862f7cf19991bb023106cafcbbb63b8e55d0",
    "battle-shock": "f674a5dd207cb868ab364152a82090c61c1191479531c92464c99fe5318ef958",
}
EXPECTED_SOURCE_OBSERVATION_SHA256_BY_RULE_ID: Final = {
    "start-of-command-phase": "9b5ce8b7402b6719772dec0ebca6e477d6f2c9a0ddb3b83f8504d2337d5c6d76",
    "gain-core-cp": "9809dd16794d824ee12f6b7d6a8e0075e61cabde43c93a9bdfe9b797b5df283a",
    "battle-shock": "e60b785371c3815fe3a9a2b77ca4dc012c6e5541c95dbcc22f68b5452c576a78",
}
EXPECTED_PROJECT_REVIEW_EVIDENCE_ID_BY_RULE_ID: Final = {
    "start-of-command-phase": "core-v2-p08a-source-review:start-of-command-phase",
    "gain-core-cp": "core-v2-p08a-source-review:gain-core-cp",
    "battle-shock": "core-v2-p08b-source-review:battle-shock",
}


class CoreCommandPhaseSourceArtifactError(ValueError):
    """Raised when the reviewed Command-phase source artifact is invalid."""


class CoreCommandPhaseSourceDocumentArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    document_id: str
    source_title: str
    authoritative_category_url: str
    authoritative_category_observed_at: str
    authoritative_category_scope: str
    category_body_capture_status: str
    review_audit_id: str
    review_audit_row_id: str
    review_audit_source_observation_sha256: str
    official_pdf_source_id: str
    official_pdf_path: str
    official_pdf_sha256: str
    exact_text_source_scope: str


class CoreCommandPhaseSearchIndexHeadingArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    heading_id: str
    display_order: int
    normalized_heading: str
    transcription_sha256: str


class CoreCommandPhaseSearchIndexObservationArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    observation_id: str
    observation_row_id: str
    provider_name: str
    source_platform: str
    source_url: str
    observed_at: str
    observation_scope: str
    project_authority_policy_id: str
    provider_non_affiliation_recorded: bool
    headings: tuple[CoreCommandPhaseSearchIndexHeadingArtifact, ...]
    normalized_observed_text: str
    sequence_transcription_sha256: str
    source_observation_sha256: str


class CoreCommandPhaseSourceRuleArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    rule_id: str
    source_id: str
    section_id: str
    display_order: int
    section_heading: str
    source_text: str
    official_pdf_source_text: str
    transcription_sha256: str
    official_pdf_transcription_sha256: str
    source_observation_sha256: str
    evidence_ids: tuple[str, ...]
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class CoreCommandPhaseEvidenceArtifact(
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
            review_audit_source_observation_sha256=(self.review_audit_source_observation_sha256),
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


class CoreCommandPhaseSourcePackageArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    source_version: str
    source_document: CoreCommandPhaseSourceDocumentArtifact
    search_index_observation: CoreCommandPhaseSearchIndexObservationArtifact
    rules: tuple[CoreCommandPhaseSourceRuleArtifact, ...]
    evidence_records: tuple[CoreCommandPhaseEvidenceArtifact, ...]
    package_hash: str

    def validate(self) -> None:
        if self.artifact_schema != ARTIFACT_SCHEMA:
            raise CoreCommandPhaseSourceArtifactError(
                "Command-phase source artifact schema is unsupported."
            )
        if (self.source_package_id, self.source_version) != (
            EXPECTED_SOURCE_PACKAGE_ID,
            EXPECTED_SOURCE_VERSION,
        ):
            raise CoreCommandPhaseSourceArtifactError(
                "Command-phase source package identity drifted."
            )
        _validate_source_document(self.source_document)
        _validate_rules(self.rules)
        _validate_search_index_observation(self.search_index_observation, rules=self.rules)
        _validate_evidence(
            self.evidence_records,
            rules=self.rules,
            search_index_observation=self.search_index_observation,
        )
        _validate_sha256("package_hash", self.package_hash)
        if self.package_hash != core_command_phase_source_package_hash(self):
            raise CoreCommandPhaseSourceArtifactError("Command-phase source package hash is stale.")
        if self.package_hash != EXPECTED_PACKAGE_HASH:
            raise CoreCommandPhaseSourceArtifactError(
                "Command-phase source package hash drifted from its reviewed pin."
            )


def core_command_phase_source_artifact_from_json_bytes(
    raw: bytes,
) -> CoreCommandPhaseSourcePackageArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=CoreCommandPhaseSourcePackageArtifact)
    except msgspec.DecodeError as exc:
        raise CoreCommandPhaseSourceArtifactError(
            "Command-phase source artifact is invalid."
        ) from exc
    artifact.validate()
    return artifact


def core_command_phase_source_package_hash(
    artifact: CoreCommandPhaseSourcePackageArtifact,
) -> str:
    payload = msgspec.to_builtins(artifact)
    if type(payload) is not dict:
        raise CoreCommandPhaseSourceArtifactError(
            "Command-phase source artifact payload is invalid."
        )
    payload["package_hash"] = ""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def core_command_phase_search_index_source_observation_sha256(
    observation: CoreCommandPhaseSearchIndexObservationArtifact,
) -> str:
    payload = msgspec.to_builtins(observation)
    if type(payload) is not dict:
        raise CoreCommandPhaseSourceArtifactError(
            "Command-phase search-index observation payload is invalid."
        )
    payload["source_observation_sha256"] = ""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_source_document(source: CoreCommandPhaseSourceDocumentArtifact) -> None:
    if (
        source.document_id,
        source.source_title,
        source.authoritative_category_url,
        source.authoritative_category_observed_at,
        source.authoritative_category_scope,
        source.category_body_capture_status,
        source.review_audit_id,
        source.review_audit_row_id,
        source.review_audit_source_observation_sha256,
        source.official_pdf_source_id,
        source.official_pdf_path,
        source.official_pdf_sha256,
        source.exact_text_source_scope,
    ) != (
        "warhammer-40000-command-phase-observed-2026-08-26",
        "Warhammer 40,000 Core Rules - Command Phase",
        EXPECTED_CATEGORY_URL,
        EXPECTED_CATEGORY_OBSERVED_AT,
        "category_08_review_audit_record",
        "review_audit_without_retained_page_body",
        EXPECTED_REVIEW_AUDIT_ID,
        "category:08",
        EXPECTED_CATEGORY_AUDIT_FINGERPRINT,
        EXPECTED_OFFICIAL_PDF_SOURCE_ID,
        EXPECTED_OFFICIAL_PDF_PATH,
        EXPECTED_OFFICIAL_PDF_SHA256,
        "retained_official_pdf_sections_08.01_through_08.03",
    ):
        raise CoreCommandPhaseSourceArtifactError(
            "Command-phase source-document provenance drifted."
        )


def _validate_search_index_observation(
    observation: CoreCommandPhaseSearchIndexObservationArtifact,
    *,
    rules: tuple[CoreCommandPhaseSourceRuleArtifact, ...],
) -> None:
    if (
        observation.observation_id,
        observation.observation_row_id,
        observation.provider_name,
        observation.source_platform,
        observation.source_url,
        observation.observed_at,
        observation.observation_scope,
        observation.project_authority_policy_id,
        observation.provider_non_affiliation_recorded,
    ) != (
        EXPECTED_SEARCH_INDEX_OBSERVATION_ID,
        EXPECTED_SEARCH_INDEX_OBSERVATION_ROW_ID,
        "40k.app",
        "Web",
        EXPECTED_SEARCH_INDEX_URL,
        EXPECTED_SEARCH_INDEX_OBSERVED_AT,
        EXPECTED_SEARCH_INDEX_OBSERVATION_SCOPE,
        PROJECT_AUTHORITY_POLICY_ID,
        True,
    ):
        raise CoreCommandPhaseSourceArtifactError(
            "Command-phase search-index observation provenance drifted."
        )
    observed_headings = tuple(
        (heading.heading_id, heading.display_order, heading.normalized_heading)
        for heading in observation.headings
    )
    if observed_headings != EXPECTED_SEARCH_INDEX_HEADINGS:
        raise CoreCommandPhaseSourceArtifactError(
            "Command-phase search-index heading sequence drifted."
        )
    if (
        observation.normalized_observed_text
        != "\n".join(heading.normalized_heading for heading in observation.headings)
        or observation.normalized_observed_text != EXPECTED_SEARCH_INDEX_NORMALIZED_TEXT
    ):
        raise CoreCommandPhaseSourceArtifactError(
            "Command-phase search-index normalized text drifted."
        )
    for heading in observation.headings:
        _validate_sha256("heading transcription_sha256", heading.transcription_sha256)
        if (
            hashlib.sha256(heading.normalized_heading.encode()).hexdigest()
            != heading.transcription_sha256
            or heading.transcription_sha256
            != EXPECTED_SEARCH_INDEX_HEADING_SHA256_BY_HEADING_ID[heading.heading_id]
        ):
            raise CoreCommandPhaseSourceArtifactError(
                "Command-phase search-index heading transcription drifted."
            )
    _validate_sha256(
        "sequence_transcription_sha256",
        observation.sequence_transcription_sha256,
    )
    if (
        hashlib.sha256(observation.normalized_observed_text.encode()).hexdigest()
        != observation.sequence_transcription_sha256
        or observation.sequence_transcription_sha256
        != EXPECTED_SEARCH_INDEX_SEQUENCE_TRANSCRIPTION_SHA256
    ):
        raise CoreCommandPhaseSourceArtifactError(
            "Command-phase search-index sequence transcription drifted."
        )
    _validate_sha256("source_observation_sha256", observation.source_observation_sha256)
    if (
        observation.source_observation_sha256
        != core_command_phase_search_index_source_observation_sha256(observation)
        or observation.source_observation_sha256 != EXPECTED_SEARCH_INDEX_SOURCE_OBSERVATION_SHA256
    ):
        raise CoreCommandPhaseSourceArtifactError(
            "Command-phase search-index source observation drifted."
        )
    if (
        tuple((rule.rule_id, rule.display_order, rule.section_heading) for rule in rules)
        != EXPECTED_SEARCH_INDEX_HEADINGS[: len(rules)]
    ):
        raise CoreCommandPhaseSourceArtifactError(
            "Command-phase source rows drifted from the observed heading sequence."
        )


def _validate_rules(rules: tuple[CoreCommandPhaseSourceRuleArtifact, ...]) -> None:
    if type(rules) is not tuple or tuple(rule.rule_id for rule in rules) != tuple(
        EXPECTED_RULE_IDENTITY
    ):
        raise CoreCommandPhaseSourceArtifactError(
            "Command-phase source rule inventory or order drifted."
        )
    for rule in rules:
        (
            expected_section_id,
            expected_display_order,
            expected_heading,
            expected_source_id,
            expected_pdf_text,
            expected_runtime_consumer_ids,
            expected_semantic_execution_status,
        ) = EXPECTED_RULE_IDENTITY[rule.rule_id]
        if (
            rule.section_id,
            rule.display_order,
            rule.section_heading,
            rule.source_text,
            rule.source_id,
            rule.official_pdf_source_text,
        ) != (
            expected_section_id,
            expected_display_order,
            expected_heading,
            expected_heading,
            expected_source_id,
            expected_pdf_text,
        ):
            raise CoreCommandPhaseSourceArtifactError(
                "Command-phase source rule identity or exact text drifted."
            )
        _validate_sha256("transcription_sha256", rule.transcription_sha256)
        if (
            hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256
            or rule.transcription_sha256 != EXPECTED_TRANSCRIPTION_SHA256_BY_RULE_ID[rule.rule_id]
        ):
            raise CoreCommandPhaseSourceArtifactError(
                "Command-phase project transcription drifted from its reviewed pin."
            )
        _validate_sha256(
            "official_pdf_transcription_sha256",
            rule.official_pdf_transcription_sha256,
        )
        if (
            hashlib.sha256(rule.official_pdf_source_text.encode()).hexdigest()
            != rule.official_pdf_transcription_sha256
            or rule.official_pdf_transcription_sha256
            != EXPECTED_OFFICIAL_PDF_TRANSCRIPTION_SHA256_BY_RULE_ID[rule.rule_id]
        ):
            raise CoreCommandPhaseSourceArtifactError(
                "Command-phase official-PDF transcription drifted from its reviewed pin."
            )
        if (
            rule.source_observation_sha256
            != EXPECTED_SOURCE_OBSERVATION_SHA256_BY_RULE_ID[rule.rule_id]
        ):
            raise CoreCommandPhaseSourceArtifactError(
                "Command-phase source observation drifted from its reviewed pin."
            )
        if (
            rule.evidence_ids
            != (
                EXPECTED_PROJECT_REVIEW_EVIDENCE_ID_BY_RULE_ID[rule.rule_id],
                f"40k-app-command-phase-search-index-2026-08-26:{rule.rule_id}",
            )
            or rule.load_support_status != "loaded"
            or rule.semantic_execution_status != expected_semantic_execution_status
            or rule.runtime_consumer_ids != expected_runtime_consumer_ids
        ):
            raise CoreCommandPhaseSourceArtifactError(
                "Command-phase source evidence linkage or support status drifted."
            )


def _validate_evidence(
    evidence_records: tuple[CoreCommandPhaseEvidenceArtifact, ...],
    *,
    rules: tuple[CoreCommandPhaseSourceRuleArtifact, ...],
    search_index_observation: CoreCommandPhaseSearchIndexObservationArtifact,
) -> None:
    evidence_by_id = {record.evidence_id: record for record in evidence_records}
    expected_ids = tuple(evidence_id for rule in rules for evidence_id in rule.evidence_ids)
    if len(evidence_by_id) != len(evidence_records) or tuple(evidence_by_id) != expected_ids:
        raise CoreCommandPhaseSourceArtifactError(
            "Command-phase source evidence inventory drifted."
        )
    records_by_id: dict[str, RuleEvidenceRecord] = {}
    for evidence in evidence_records:
        try:
            records_by_id[evidence.evidence_id] = evidence.to_rule_evidence_record()
        except RuleEvidenceError as exc:
            raise CoreCommandPhaseSourceArtifactError(
                "Command-phase source evidence is invalid."
            ) from exc
    for rule in rules:
        project_review = records_by_id[rule.evidence_ids[0]]
        mirror = records_by_id[rule.evidence_ids[1]]
        if (
            project_review.evidence_kind,
            project_review.authority,
            project_review.provider_name,
            project_review.source_title,
            project_review.source_platform,
            project_review.source_url,
            project_review.observed_at,
            project_review.verification_status,
        ) != (
            "project_reviewed_app_transcription",
            "unverified_transcription_only",
            "CORE V2 Source Review",
            "Reviewed transcription of the Command-phase section heading",
            "Repository",
            None,
            None,
            "unverified",
        ):
            raise CoreCommandPhaseSourceArtifactError(
                "Command-phase project-review provenance drifted."
            )
        if (
            mirror.evidence_kind,
            mirror.authority,
            mirror.project_authority_policy_id,
            mirror.review_audit_id,
            mirror.review_audit_row_id,
            mirror.review_audit_source_observation_sha256,
            mirror.provider_name,
            mirror.source_title,
            mirror.source_platform,
            mirror.source_url,
            mirror.observed_at,
            mirror.verification_status,
            mirror.provider_non_affiliation_recorded,
        ) != (
            "third_party_mirror",
            "project_authoritative_app_mirror",
            PROJECT_AUTHORITY_POLICY_ID,
            search_index_observation.observation_id,
            search_index_observation.observation_row_id,
            search_index_observation.source_observation_sha256,
            "40k.app",
            "40k.app Core Rules search-index Command-phase heading sequence",
            "Web",
            search_index_observation.source_url,
            search_index_observation.observed_at,
            "authoritative_app_mirror",
            True,
        ):
            raise CoreCommandPhaseSourceArtifactError(
                "Command-phase search-index mirror provenance drifted."
            )
        if any(
            (
                record.rule_source_id,
                record.transcription_sha256,
                record.official_corroborating_source_ids,
                record.load_support_status,
                record.semantic_execution_status,
                record.runtime_consumer_ids,
            )
            != (
                rule.source_id,
                rule.transcription_sha256,
                (),
                rule.load_support_status,
                rule.semantic_execution_status,
                rule.runtime_consumer_ids,
            )
            for record in (project_review, mirror)
        ):
            raise CoreCommandPhaseSourceArtifactError(
                "Command-phase source/evidence execution linkage drifted."
            )
        if mirror.observation_sha256 != rule.source_observation_sha256:
            raise CoreCommandPhaseSourceArtifactError(
                "Command-phase search-index observation linkage drifted."
            )


def _validate_sha256(field_name: str, value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise CoreCommandPhaseSourceArtifactError(
            f"Command-phase source {field_name} must be a lowercase SHA-256 digest."
        )
    return value


__all__ = (
    "EXPECTED_ARTIFACT_SHA256",
    "EXPECTED_CATEGORY_OBSERVED_AT",
    "EXPECTED_CATEGORY_URL",
    "EXPECTED_OFFICIAL_PDF_SHA256",
    "EXPECTED_PACKAGE_HASH",
    "EXPECTED_SEARCH_INDEX_OBSERVED_AT",
    "EXPECTED_SEARCH_INDEX_SEQUENCE_TRANSCRIPTION_SHA256",
    "EXPECTED_SEARCH_INDEX_SOURCE_OBSERVATION_SHA256",
    "EXPECTED_SEARCH_INDEX_URL",
    "CoreCommandPhaseSearchIndexObservationArtifact",
    "CoreCommandPhaseSourceArtifactError",
    "CoreCommandPhaseSourcePackageArtifact",
    "CoreCommandPhaseSourceRuleArtifact",
    "core_command_phase_search_index_source_observation_sha256",
    "core_command_phase_source_artifact_from_json_bytes",
)
