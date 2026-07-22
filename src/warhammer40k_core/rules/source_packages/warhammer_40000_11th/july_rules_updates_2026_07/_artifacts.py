from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

import msgspec

ARTIFACT_SCHEMA = "core-v2-july-rules-updates-source-package-v1"
EXPECTED_SOURCE_PACKAGE_ID = "gw-11e-rules-and-event-updates-2026-07-22"
EXPECTED_SOURCE_TITLE = "Warhammer 40,000 July 2026 Rules and Event Updates"
EXPECTED_SOURCE_VERSION = "2026-07-22"
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


class JulyRulesUpdatesPackageArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    source_package_id: str
    source_title: str
    source_version: str
    source_date: str
    universal_rules_update: UniversalRulesUpdateArtifact
    event_companion: EventCompanionUpdateArtifact

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
