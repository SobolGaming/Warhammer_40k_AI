from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from types import MappingProxyType

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

ARTIFACT_SCHEMA = "core-v2-july-rules-updates-source-package-v3"
EXPECTED_SOURCE_PACKAGE_ID = "gw-11e-rules-and-event-updates-2026-07-22"
EXPECTED_SOURCE_TITLE = "Warhammer 40,000 July 2026 Rules and Event Updates"
EXPECTED_SOURCE_VERSION = "2026-07-22"
EXPECTED_PACKAGE_HASH = "d9e36c4522463da052d3458568aaa5ad5c5279d649f1a0489ced6f80f9e3b08a"
EXPECTED_EVENT_SOURCE_PACKAGE_ID = "gw-11e-warhammer-event-companion-v1-1-2026-07"
EXPECTED_UNIVERSAL_RULE_BEHAVIORS: Mapping[str, str] = MappingProxyType(
    {
        "modifying-a-stratagem-cp-cost": "unnamed_zero_cp_reduces_cost_by_one",
        "stratagem-repeat-and-limit-exceptions": (
            "repeat_or_limit_exception_requires_named_stratagem"
        ),
        "stratagems-that-prevent-targeting": ("protective_targeting_range_is_eighteen_inches"),
        "stratagems-that-add-identical-units": ("identical_unit_replacement_once_per_battle"),
    }
)
EXPECTED_EVENT_COMPANION_RULE_BEHAVIORS: Mapping[str, str] = MappingProxyType(
    {
        "generating-command-points": "non_core_cp_gain_maximum_one_per_battle_round",
    }
)
EXPECTED_APP_CORE_RULE_BEHAVIORS: Mapping[str, str] = MappingProxyType(
    {
        "01.02.03-embarked-model-return": "embarked_return_requires_remaining_transport_capacity",
        "05.03.02-post-roll-attack-profiles": "post_roll_profile_changes_split_attack_pools",
        "05.04.05-fight-on-death": (
            "fight_on_death_models_wait_for_their_units_single_attack_selection"
        ),
        "09.07.01-desperate-escape-definition": "desperate_escape_test_means_hazard_rolls",
        "09.07.01-forced-desperate-escape": (
            "forced_desperate_escape_tests_all_models_and_battle_shock"
        ),
        "09-normal-move-one-per-phase": "normal_move_limited_to_once_per_unit_per_phase",
        "12.08-objective-consolidation": "objective_consolidation_requires_unengaged_endpoint",
        "14.02.01-control-first": "objective_control_determined_first_at_phase_and_turn_end",
        "18.01-dedicated-transport": "empty_dedicated_transport_models_destroyed_without_triggers",
        "20.01.02-strategic-reserves": (
            "strategic_reserves_destroyed_at_final_turn_without_triggers"
        ),
        "faq-heavy-fly-horizontal-distance": (
            "fly_heavy_uses_horizontal_distance_for_three_inch_limit"
        ),
        "faq-hazardous-mixed-unit-keywords": (
            "infantry_monster_vehicle_hazard_failure_inflicts_one_mortal_wound"
        ),
        "24.28.01-precision-devastating-wounds": (
            "precision_mortals_prioritize_selected_character_group"
        ),
        "24.37.01-torrent": "torrent_excludes_indirect_fire_and_precision",
        "25.04-epic-hero-enhancements": "epic_hero_models_cannot_be_given_enhancements",
        "25.04-incursion-detachment": "incursion_allows_one_three_dp_detachment",
    }
)
EXPECTED_APP_CORE_DOCUMENT_METADATA = (
    "warhammer-40000-app-core-rules-2026-07-22",
    "Warhammer 40,000 App Core Rules",
    "2026-07-22",
    "Warhammer 40,000 App",
)
EXPECTED_APP_TRANSCRIPTION_PROVENANCE = (
    "repository_transcription_without_retained_app_capture",
    "unverified_transcription_only",
    "transcription_only_no_source_url_app_version_screenshot_or_binary",
    None,
    None,
    None,
    None,
    None,
)
EXPECTED_APP_MIRROR_URL_BY_RULE_ID: Mapping[str, str] = MappingProxyType(
    {
        "01.02.03-embarked-model-return": "https://www.40k.app/rules/01-core-concepts",
        "05.03.02-post-roll-attack-profiles": "https://www.40k.app/rules/05-attack-sequence",
        "05.04.05-fight-on-death": "https://www.40k.app/rules/05-attack-sequence",
        "09.07.01-desperate-escape-definition": ("https://www.40k.app/rules/09-movement-phase"),
        "09.07.01-forced-desperate-escape": ("https://www.40k.app/rules/09-movement-phase"),
        "09-normal-move-one-per-phase": "https://www.40k.app/rules/09-movement-phase",
        "12.08-objective-consolidation": "https://www.40k.app/rules/12-fight-phase",
        "14.02.01-control-first": "https://www.40k.app/rules/14-objectives",
        "18.01-dedicated-transport": "https://www.40k.app/rules/18-transports",
        "20.01.02-strategic-reserves": ("https://www.40k.app/rules/20-strategic-reserves"),
        "faq-heavy-fly-horizontal-distance": ("https://www.40k.app/rules/21-flying-and-surging"),
        "faq-hazardous-mixed-unit-keywords": ("https://www.40k.app/rules/24-core-abilities"),
        "24.28.01-precision-devastating-wounds": ("https://www.40k.app/rules/24-core-abilities"),
        "24.37.01-torrent": "https://www.40k.app/rules/24-core-abilities",
        "25.04-epic-hero-enhancements": "https://www.40k.app/rules/25-muster-armies",
        "25.04-incursion-detachment": "https://www.40k.app/rules/25-muster-armies",
    }
)
EXPECTED_FIGHT_ON_DEATH_RUNTIME_CONSUMERS = (
    "warhammer40k_core.engine.fight_on_death:restore_model_awaiting_fight_on_death",
    "warhammer40k_core.engine.rule_model_destruction_fight_continuation:"
    "remove_remaining_fight_on_death_models_at_phase_end",
)
EXPECTED_UNIVERSAL_DOCUMENT_METADATA = (
    "eng_22-07_warhammer40000_universal_rules_updates",
    "Warhammer 40,000 Universal Rules Updates v1.0",
    "1.0",
    (
        "https://assets.warhammer-community.com/"
        "eng_22-07_warhammer_40,000_universal_rules_updates-coltxp7ngi-3kvdfxwyon.pdf"
    ),
    (
        "docs/source_rules/"
        "eng_22-07_warhammer40000_universal_rules_updates-coltxp7ngi-3kvdfxwyon.pdf"
    ),
    "a16ede8a54d693c91e24253e8731f12d298b68fd29f4ee457dd7ba4c69c0c053",
)
EXPECTED_EVENT_COMPANION_DOCUMENT_METADATA = (
    "eng_22-07_warhammer40000_event_companion",
    "Warhammer Event Companion v1.1",
    "1.1",
    (
        "https://assets.warhammer-community.com/"
        "eng_22-07_warhammer_40,000_event_companion-alyapl19us-b2drgwkji4.pdf"
    ),
    ("docs/source_rules/eng_22-07_warhammer40000_event_companion-alyapl19us-b2drgwkji4.pdf"),
    "97ae5591be2e58bdb636e97127eac0877f9bf28b29fc607ed4ead4d377fb8f20",
)
EXPECTED_CHANGED_LAYOUT_IDS: frozenset[str] = frozenset(
    (
        "take-and-hold-vs-purge-the-foe-layout-1",
        "take-and-hold-vs-purge-the-foe-layout-2",
        "take-and-hold-vs-purge-the-foe-layout-3",
        "purge-the-foe-vs-disruption-layout-1",
        "purge-the-foe-vs-disruption-layout-2",
        "purge-the-foe-vs-disruption-layout-3",
        "disruption-vs-reconnaissance-layout-1",
        "disruption-vs-reconnaissance-layout-3",
    )
)


class JulyRulesUpdateArtifactError(ValueError):
    """Raised when the July rules-update source artifact is invalid."""


class UniversalRuleUpdateRecord(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    rule_id: str
    source_id: str
    source_text: str
    behavior_descriptor: str


class EventCompanionRuleUpdateRecord(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    rule_id: str
    source_id: str
    source_text: str
    behavior_descriptor: str


class AppCoreRuleUpdateRecord(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    rule_id: str
    source_id: str
    source_text: str
    behavior_descriptor: str
    evidence_ids: tuple[str, ...]


class AppCoreTranscriptionProvenanceArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    provenance_kind: str
    authority: str
    availability: str
    observation_date: str | None
    app_version: str | None
    source_url: str | None
    screenshot_sha256: str | None
    source_binary_sha256: str | None


class AppCoreMirrorEvidenceContextArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    evidence_kind: RuleEvidenceKind
    authority: RuleEvidenceAuthority
    provider_name: str
    source_title: str
    source_platform: str
    observed_at: str
    app_version: str | None
    app_build: str | None
    capture_artifact_path: str | None
    capture_sha256: str | None
    official_corroborating_source_ids: tuple[str, ...]
    provider_non_affiliation_recorded: bool


class AppCoreRuleEvidenceArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    evidence_id: str
    rule_source_id: str
    source_url: str
    transcription_sha256: str
    verification_status: RuleVerificationStatus
    observation_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]

    def to_rule_evidence_record(
        self,
        *,
        context: AppCoreMirrorEvidenceContextArtifact,
    ) -> RuleEvidenceRecord:
        return RuleEvidenceRecord(
            evidence_id=self.evidence_id,
            rule_source_id=self.rule_source_id,
            evidence_kind=context.evidence_kind,
            authority=context.authority,
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


class EventLayoutRevisionRecord(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    layout_id: str
    source_page: int
    terrain_changed: bool
    deployment_zones_changed: bool
    deployment_zone_template_number: int
    source_id: str


class UniversalRulesUpdateArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    document_id: str
    source_title: str
    source_version: str
    source_url: str
    local_pdf: str
    source_pdf_sha256: str
    rules: tuple[UniversalRuleUpdateRecord, ...]
    identical_unit_replacement_stratagem_source_ids: tuple[str, ...]
    protective_targeting_stratagem_source_ids: tuple[str, ...]


class EventCompanionUpdateArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    document_id: str
    source_title: str
    source_version: str
    source_url: str
    local_pdf: str
    source_pdf_sha256: str
    updated_source_package_id: str
    rules: tuple[EventCompanionRuleUpdateRecord, ...]
    changed_layouts: tuple[EventLayoutRevisionRecord, ...]


class AppCoreRulesUpdateArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    document_id: str
    source_title: str
    source_version: str
    source_platform: str
    transcription_provenance: AppCoreTranscriptionProvenanceArtifact
    mirror_evidence_context: AppCoreMirrorEvidenceContextArtifact
    evidence_records: tuple[AppCoreRuleEvidenceArtifact, ...]
    rules: tuple[AppCoreRuleUpdateRecord, ...]


class JulyRulesUpdatesPackageArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    source_package_id: str
    source_title: str
    source_version: str
    source_date: str
    universal_rules_update: UniversalRulesUpdateArtifact
    event_companion: EventCompanionUpdateArtifact
    app_core_rules_update: AppCoreRulesUpdateArtifact
    package_hash: str

    def validate(self) -> None:
        if self.artifact_schema != ARTIFACT_SCHEMA:
            raise JulyRulesUpdateArtifactError("July rules-update artifact schema is unsupported.")
        if self.source_package_id != EXPECTED_SOURCE_PACKAGE_ID:
            raise JulyRulesUpdateArtifactError("July rules-update package identity drifted.")
        if (
            self.source_title != EXPECTED_SOURCE_TITLE
            or self.source_version != EXPECTED_SOURCE_VERSION
        ):
            raise JulyRulesUpdateArtifactError("July rules-update package metadata drifted.")
        if self.source_date != "2026-07-22":
            raise JulyRulesUpdateArtifactError("July rules-update source date drifted.")
        _validate_non_empty_strings(
            self.source_title,
            self.source_version,
            self.source_date,
        )
        self._validate_universal_rules_update()
        self._validate_event_companion_update()
        self._validate_app_core_rules_update()
        _validate_sha256("package_hash", self.package_hash)
        if self.package_hash != july_rules_updates_package_hash(self):
            raise JulyRulesUpdateArtifactError("July rules-update package hash is stale.")
        if self.package_hash != EXPECTED_PACKAGE_HASH:
            raise JulyRulesUpdateArtifactError(
                "July rules-update package hash drifted from its reviewed pin."
            )

    def _validate_universal_rules_update(self) -> None:
        update = self.universal_rules_update
        if (
            update.document_id,
            update.source_title,
            update.source_version,
            update.source_url,
            update.local_pdf,
            update.source_pdf_sha256,
        ) != EXPECTED_UNIVERSAL_DOCUMENT_METADATA:
            raise JulyRulesUpdateArtifactError("Universal rules-update document metadata drifted.")
        rule_behaviors = {rule.rule_id: rule.behavior_descriptor for rule in update.rules}
        if rule_behaviors != EXPECTED_UNIVERSAL_RULE_BEHAVIORS or len(rule_behaviors) != len(
            update.rules
        ):
            raise JulyRulesUpdateArtifactError(
                "Universal rules-update rule identity inventory drifted."
            )
        for rule in update.rules:
            _validate_non_empty_strings(
                rule.rule_id,
                rule.source_id,
                rule.source_text,
                rule.behavior_descriptor,
            )
            if rule.source_id != (f"{self.source_package_id}:universal-rules:{rule.rule_id}"):
                raise JulyRulesUpdateArtifactError(
                    "Universal rules-update source identity drifted."
                )
        _validate_unique_source_ids(
            update.identical_unit_replacement_stratagem_source_ids,
            expected_count=6,
        )
        _validate_unique_source_ids(
            update.protective_targeting_stratagem_source_ids,
            expected_count=10,
        )

    def _validate_event_companion_update(self) -> None:
        update = self.event_companion
        if (
            update.document_id,
            update.source_title,
            update.source_version,
            update.source_url,
            update.local_pdf,
            update.source_pdf_sha256,
        ) != EXPECTED_EVENT_COMPANION_DOCUMENT_METADATA:
            raise JulyRulesUpdateArtifactError("Event Companion document metadata drifted.")
        if update.updated_source_package_id != EXPECTED_EVENT_SOURCE_PACKAGE_ID:
            raise JulyRulesUpdateArtifactError("Event Companion updated source identity drifted.")
        rule_behaviors = {rule.rule_id: rule.behavior_descriptor for rule in update.rules}
        if rule_behaviors != EXPECTED_EVENT_COMPANION_RULE_BEHAVIORS or len(rule_behaviors) != len(
            update.rules
        ):
            raise JulyRulesUpdateArtifactError("Event Companion rule identity inventory drifted.")
        for rule in update.rules:
            _validate_non_empty_strings(
                rule.rule_id,
                rule.source_id,
                rule.source_text,
                rule.behavior_descriptor,
            )
            if rule.source_id != (f"{update.updated_source_package_id}:rules:{rule.rule_id}"):
                raise JulyRulesUpdateArtifactError("Event Companion rule source identity drifted.")
        rows_by_layout_id = {row.layout_id: row for row in update.changed_layouts}
        if frozenset(rows_by_layout_id) != EXPECTED_CHANGED_LAYOUT_IDS:
            raise JulyRulesUpdateArtifactError("Event Companion changed-layout inventory drifted.")
        if len(rows_by_layout_id) != len(update.changed_layouts):
            raise JulyRulesUpdateArtifactError("Event Companion changed-layout IDs must be unique.")
        for row in update.changed_layouts:
            _validate_non_empty_strings(row.layout_id, row.source_id)
            if row.source_page < 1:
                raise JulyRulesUpdateArtifactError(
                    "Event Companion changed-layout source page must be positive."
                )
            if type(row.terrain_changed) is not bool or not row.terrain_changed:
                raise JulyRulesUpdateArtifactError(
                    "Event Companion changed layouts must record a terrain revision."
                )
            if type(row.deployment_zones_changed) is not bool or row.deployment_zones_changed:
                raise JulyRulesUpdateArtifactError(
                    "Event Companion v1.1 did not revise these deployment zones."
                )
            if row.deployment_zone_template_number not in {1, 2, 3, 4, 5}:
                raise JulyRulesUpdateArtifactError(
                    "Event Companion deployment-zone template number is invalid."
                )
            if not row.source_id.startswith(f"{update.updated_source_package_id}:layout-revision:"):
                raise JulyRulesUpdateArtifactError(
                    "Event Companion layout-revision source identity drifted."
                )

    def _validate_app_core_rules_update(self) -> None:
        update = self.app_core_rules_update
        if (
            update.document_id,
            update.source_title,
            update.source_version,
            update.source_platform,
        ) != EXPECTED_APP_CORE_DOCUMENT_METADATA:
            raise JulyRulesUpdateArtifactError("App core-rules document metadata drifted.")
        provenance = update.transcription_provenance
        if (
            provenance.provenance_kind,
            provenance.authority,
            provenance.availability,
            provenance.observation_date,
            provenance.app_version,
            provenance.source_url,
            provenance.screenshot_sha256,
            provenance.source_binary_sha256,
        ) != EXPECTED_APP_TRANSCRIPTION_PROVENANCE:
            raise JulyRulesUpdateArtifactError("App core-rules transcription provenance drifted.")
        rule_behaviors = {rule.rule_id: rule.behavior_descriptor for rule in update.rules}
        if rule_behaviors != EXPECTED_APP_CORE_RULE_BEHAVIORS or len(rule_behaviors) != len(
            update.rules
        ):
            raise JulyRulesUpdateArtifactError("App core-rules identity inventory drifted.")
        for rule in update.rules:
            _validate_non_empty_strings(
                rule.rule_id,
                rule.source_id,
                rule.source_text,
                rule.behavior_descriptor,
            )
            if rule.source_id != f"{self.source_package_id}:app-core-rules:{rule.rule_id}":
                raise JulyRulesUpdateArtifactError("App core-rules source identity drifted.")
            if len(rule.evidence_ids) != 1 or len(set(rule.evidence_ids)) != 1:
                raise JulyRulesUpdateArtifactError(
                    "Each App core-rules row must reference one evidence record."
                )
        evidence_by_id = {record.evidence_id: record for record in update.evidence_records}
        if len(evidence_by_id) != len(update.evidence_records) or len(evidence_by_id) != len(
            update.rules
        ):
            raise JulyRulesUpdateArtifactError(
                "App core-rules evidence identity inventory drifted."
            )
        rules_by_source_id = {rule.source_id: rule for rule in update.rules}
        if len(rules_by_source_id) != len(update.rules):
            raise JulyRulesUpdateArtifactError("App core-rules source IDs must be unique.")
        referenced_evidence_ids = {
            evidence_id for rule in update.rules for evidence_id in rule.evidence_ids
        }
        unknown_evidence_ids = referenced_evidence_ids - set(evidence_by_id)
        if unknown_evidence_ids:
            raise JulyRulesUpdateArtifactError("App core-rules row references unknown evidence.")
        if referenced_evidence_ids != set(evidence_by_id):
            raise JulyRulesUpdateArtifactError("App core-rules evidence contains orphan records.")
        for evidence_id, evidence in evidence_by_id.items():
            try:
                record = evidence.to_rule_evidence_record(context=update.mirror_evidence_context)
            except RuleEvidenceError as exc:
                raise JulyRulesUpdateArtifactError(
                    "App core-rules evidence record is invalid."
                ) from exc
            if (
                record.evidence_kind,
                record.authority,
                record.provider_name,
                record.source_title,
                record.source_platform,
                record.observed_at,
                record.load_support_status,
            ) != (
                "third_party_mirror",
                "secondary_mirror_only",
                "40k.app",
                "40k.app Core Rules",
                "Web",
                "2026-08-25T00:00:00-04:00",
                "loaded",
            ):
                raise JulyRulesUpdateArtifactError("App core-rules mirror provenance drifted.")
            evidenced_rule = rules_by_source_id.get(record.rule_source_id)
            if evidenced_rule is None or evidenced_rule.evidence_ids != (evidence_id,):
                raise JulyRulesUpdateArtifactError(
                    "App core-rules evidence is attached to the wrong source row."
                )
            expected_evidence_id = f"40k-app-core-rules-2026-08-25:{evidenced_rule.rule_id}"
            if evidence_id != expected_evidence_id:
                raise JulyRulesUpdateArtifactError("App core-rules evidence identity drifted.")
            expected_mirror_url = EXPECTED_APP_MIRROR_URL_BY_RULE_ID[evidenced_rule.rule_id]
            if record.source_url != expected_mirror_url:
                raise JulyRulesUpdateArtifactError("App core-rules mirror URL drifted.")
            transcription_sha256 = hashlib.sha256(evidenced_rule.source_text.encode()).hexdigest()
            if record.transcription_sha256 != transcription_sha256:
                raise JulyRulesUpdateArtifactError("App core-rules transcription hash is stale.")
            if evidenced_rule.rule_id == "12.08-objective-consolidation":
                expected_verification_status = "conflict"
            elif evidenced_rule.rule_id in {
                "faq-heavy-fly-horizontal-distance",
                "faq-hazardous-mixed-unit-keywords",
            }:
                expected_verification_status = "not_observed_on_mirror"
            else:
                expected_verification_status = "mirror_only"
            if record.verification_status != expected_verification_status:
                raise JulyRulesUpdateArtifactError("App core-rules verification status drifted.")
            if evidenced_rule.rule_id == "05.04.05-fight-on-death":
                if (
                    record.semantic_execution_status != "partial_engine_runtime"
                    or record.runtime_consumer_ids != EXPECTED_FIGHT_ON_DEATH_RUNTIME_CONSUMERS
                ):
                    raise JulyRulesUpdateArtifactError("Fight On Death execution evidence drifted.")
            elif evidenced_rule.rule_id == "12.08-objective-consolidation":
                if (
                    record.semantic_execution_status != "blocked_by_source_conflict"
                    or record.runtime_consumer_ids
                ):
                    raise JulyRulesUpdateArtifactError(
                        "Objective Consolidation conflict evidence drifted."
                    )
            elif record.semantic_execution_status != "not_certified" or record.runtime_consumer_ids:
                raise JulyRulesUpdateArtifactError(
                    "Uncertified App core-rules execution evidence drifted."
                )


def july_rules_updates_package_artifact_from_json_bytes(
    raw: bytes,
) -> JulyRulesUpdatesPackageArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=JulyRulesUpdatesPackageArtifact)
    except msgspec.DecodeError as exc:
        raise JulyRulesUpdateArtifactError(
            "July rules-update generated artifact is invalid."
        ) from exc
    artifact.validate()
    return artifact


def july_rules_updates_package_hash(artifact: JulyRulesUpdatesPackageArtifact) -> str:
    payload = msgspec.to_builtins(artifact)
    if type(payload) is not dict:
        raise JulyRulesUpdateArtifactError("July rules-update artifact payload is invalid.")
    payload["package_hash"] = ""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_unique_source_ids(source_ids: tuple[str, ...], *, expected_count: int) -> None:
    if len(source_ids) != expected_count or len(set(source_ids)) != expected_count:
        raise JulyRulesUpdateArtifactError("July rules-update source-ID inventory drifted.")
    _validate_non_empty_strings(*source_ids)


def _validate_non_empty_strings(*values: object) -> None:
    if any(
        type(value) is not str or not value.strip() or value != value.strip() for value in values
    ):
        raise JulyRulesUpdateArtifactError(
            "July rules-update text values must be non-empty stripped strings."
        )


def _validate_sha256(field_name: str, value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise JulyRulesUpdateArtifactError(
            f"July rules-update {field_name} must be lowercase SHA-256."
        )
    return value


__all__ = (
    "ARTIFACT_SCHEMA",
    "EXPECTED_PACKAGE_HASH",
    "AppCoreMirrorEvidenceContextArtifact",
    "AppCoreRuleEvidenceArtifact",
    "AppCoreRuleUpdateRecord",
    "AppCoreRulesUpdateArtifact",
    "AppCoreTranscriptionProvenanceArtifact",
    "EventCompanionRuleUpdateRecord",
    "EventCompanionUpdateArtifact",
    "EventLayoutRevisionRecord",
    "JulyRulesUpdateArtifactError",
    "JulyRulesUpdatesPackageArtifact",
    "UniversalRuleUpdateRecord",
    "UniversalRulesUpdateArtifact",
    "july_rules_updates_package_artifact_from_json_bytes",
    "july_rules_updates_package_hash",
)
