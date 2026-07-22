from __future__ import annotations

import msgspec

ARTIFACT_SCHEMA = "core-v2-july-rules-updates-source-package-v1"
EXPECTED_SOURCE_PACKAGE_ID = "gw-11e-rules-and-event-updates-2026-07-22"
EXPECTED_EVENT_SOURCE_PACKAGE_ID = "gw-11e-warhammer-event-companion-v1-1-2026-07"
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
        _validate_non_empty_strings(
            update.document_id,
            update.source_title,
            update.source_version,
            update.source_url,
            update.local_pdf,
        )
        _validate_sha256(update.source_pdf_sha256)
        if len(update.rules) != 4:
            raise JulyRulesUpdateArtifactError(
                "Universal rules-update artifact must contain all four rules."
            )
        rule_ids = {rule.rule_id for rule in update.rules}
        if len(rule_ids) != len(update.rules):
            raise JulyRulesUpdateArtifactError("Universal rules-update rule IDs must be unique.")
        for rule in update.rules:
            _validate_non_empty_strings(
                rule.rule_id,
                rule.source_id,
                rule.source_text,
                rule.behavior_descriptor,
            )
            if not rule.source_id.startswith(f"{self.source_package_id}:universal-rules:"):
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
        _validate_non_empty_strings(
            update.document_id,
            update.source_title,
            update.source_version,
            update.source_url,
            update.local_pdf,
        )
        _validate_sha256(update.source_pdf_sha256)
        if update.updated_source_package_id != EXPECTED_EVENT_SOURCE_PACKAGE_ID:
            raise JulyRulesUpdateArtifactError("Event Companion updated source identity drifted.")
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


def _validate_sha256(value: str) -> None:
    _validate_non_empty_strings(value)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise JulyRulesUpdateArtifactError(
            "July rules-update PDF checksum must be lowercase SHA-256."
        )
