from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Final

import msgspec

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

SOURCE_PACKAGE_ID: Final = "gw-11e-faction-packs-2026-07"
SOURCE_TITLE: Final = "Warhammer 40,000 11th Edition July 22 Faction Packs"
SOURCE_VERSION: Final = "2026-07-22"
SOURCE_DATE: Final = "2026-07-22"
ACTIVATION_STATUS: Final = "current"
ARTIFACT_SCHEMA: Final = "core-v2-july-current-faction-source-set-v1"
ARTIFACT_PACKAGE: Final = "warhammer40k_core.rules.source_packages.warhammer_40000_11th"
ARTIFACT_PATH: Final = "july_faction_packs_2026_07/artifacts/current-sources.json"
DEATHWATCH_FACTION_ID: Final = "deathwatch"
DEATHWATCH_PACKAGE_ID: Final = "gw-11e-deathwatch-faction-pack-2026-06"
DEATHWATCH_SHA256: Final = "698b7063a71e3f10301aab1498effcb88ad2be41f3f491e24737c2abc9f988ce"
DEATHWATCH_PDF_PATH: Final = (
    "data/raw/faction_packs/"
    "eng_08-06_warhammer40000_faction_pack_deathwatch-z0ebavrfze-muhcibnets.pdf"
)
NO_ACTION_FACTION_IDS: Final = frozenset(
    {
        "adeptus-custodes",
        "aeldari",
        "black-templars",
        "chaos-knights",
        "dark-angels",
        "death-guard",
        "drukhari",
        "genestealer-cults",
        "imperial-agents",
        "leagues-of-votann",
        "space-wolves",
        "tau-empire",
        "world-eaters",
    }
)
PROMOTED_FACTION_IDS: Final = frozenset(
    {
        "adepta-sororitas",
        "adeptus-custodes",
        "adeptus-mechanicus",
        "aeldari",
        "astra-militarum",
        "black-templars",
        "blood-angels",
        "chaos-daemons",
        "chaos-knights",
        "chaos-space-marines",
        "dark-angels",
        "death-guard",
        "drukhari",
        "emperors-children",
        "genestealer-cults",
        "grey-knights",
        "imperial-agents",
        "imperial-knights",
        "leagues-of-votann",
        "necrons",
        "orks",
        "space-marines",
        "space-wolves",
        "tau-empire",
        "thousand-sons",
        "tyranids",
        "world-eaters",
    }
)
CURRENT_FACTION_IDS: Final = PROMOTED_FACTION_IDS | {DEATHWATCH_FACTION_ID}
PHASE17E_SOURCE_PACKAGE_ID: Final = "gw-11e-phase17e-faction-coverage-2026-07"
PHASE17F_SOURCE_PACKAGE_ID: Final = "gw-11e-phase17f-faction-execution-2026-07"
_RUNTIME_MODULE_BASE: Final = "warhammer40k_core.engine.faction_content.warhammer_40000_11th"
_JULY_RUNTIME_FACTION_IDS: Final = frozenset(
    {"chaos-daemons", "emperors-children", "thousand-sons"}
)


class FactionSourcePromotionError(ValueError):
    """Raised when the July current-source cutover is incomplete or inconsistent."""


class CurrentFactionSourceRecord(msgspec.Struct, frozen=True):
    faction_id: str
    faction_name: str
    package_id: str
    title: str
    source_date: str
    pdf_path: str
    sha256: str
    bytes: int
    predecessor_package_id: str | None
    predecessor_pdf_path: str | None
    predecessor_pdf_sha256: str | None
    semantic_change_status: str

    def validate(self) -> None:
        _validate_identifier("faction_id", self.faction_id)
        _validate_text("faction_name", self.faction_name)
        _validate_identifier("package_id", self.package_id)
        _validate_text("title", self.title)
        _validate_text("source_date", self.source_date)
        _validate_pdf_path(self.pdf_path)
        _validate_sha256("sha256", self.sha256)
        if type(self.bytes) is not int or self.bytes <= 0:
            raise FactionSourcePromotionError("Current faction source bytes must be positive.")
        if self.faction_id == DEATHWATCH_FACTION_ID:
            if (
                self.package_id != DEATHWATCH_PACKAGE_ID
                or self.sha256 != DEATHWATCH_SHA256
                or self.pdf_path != DEATHWATCH_PDF_PATH
                or self.predecessor_package_id is not None
                or self.predecessor_pdf_path is not None
                or self.predecessor_pdf_sha256 is not None
                or self.semantic_change_status != "current_no_successor"
            ):
                raise FactionSourcePromotionError(
                    "Deathwatch must retain its exact June current-source identity."
                )
            return
        expected_package_id = f"gw-11e-{self.faction_id}-faction-pack-2026-07"
        expected_predecessor_id = f"gw-11e-{self.faction_id}-faction-pack-2026-06"
        if (
            self.package_id != expected_package_id
            or self.source_date != SOURCE_DATE
            or self.predecessor_package_id != expected_predecessor_id
            or self.predecessor_pdf_path is None
            or self.predecessor_pdf_sha256 is None
        ):
            raise FactionSourcePromotionError(
                "Promoted faction source must link its exact July package and June predecessor."
            )
        _validate_pdf_path(self.predecessor_pdf_path)
        _validate_sha256("predecessor_pdf_sha256", self.predecessor_pdf_sha256)
        expected_status = (
            "provenance_only" if self.faction_id in NO_ACTION_FACTION_IDS else "reviewed_delta"
        )
        if self.semantic_change_status != expected_status:
            raise FactionSourcePromotionError(
                "July faction source semantic-change classification drifted."
            )

    @property
    def pdf_filename(self) -> str:
        return PurePosixPath(self.pdf_path).name


class CurrentFactionSourceSet(msgspec.Struct, frozen=True):
    artifact_schema: str
    source_package_id: str
    source_title: str
    source_version: str
    source_date: str
    activation_status: str
    records: list[CurrentFactionSourceRecord]
    excluded_content_categories: list[str]

    def validate(self) -> None:
        if (
            self.artifact_schema != ARTIFACT_SCHEMA
            or self.source_package_id != SOURCE_PACKAGE_ID
            or self.source_title != SOURCE_TITLE
            or self.source_version != SOURCE_VERSION
            or self.source_date != SOURCE_DATE
            or self.activation_status != ACTIVATION_STATUS
        ):
            raise FactionSourcePromotionError("July current-source artifact identity drifted.")
        if self.excluded_content_categories != ["imperial-armour", "legends"]:
            raise FactionSourcePromotionError(
                "July promotion must exclude Imperial Armour and Legends."
            )
        seen_factions: set[str] = set()
        seen_packages: set[str] = set()
        for record in self.records:
            record.validate()
            if record.faction_id in seen_factions or record.package_id in seen_packages:
                raise FactionSourcePromotionError(
                    "July current-source records must map factions and packages exactly once."
                )
            seen_factions.add(record.faction_id)
            seen_packages.add(record.package_id)
        if frozenset(seen_factions) != CURRENT_FACTION_IDS:
            raise FactionSourcePromotionError(
                "July current-source artifact must contain the exact 28-faction set."
            )


def current_source_set() -> CurrentFactionSourceSet:
    try:
        raw = package_artifact_bytes(ARTIFACT_PACKAGE, ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise FactionSourcePromotionError(
            "July current-source artifact could not be loaded."
        ) from exc
    try:
        artifact = msgspec.json.decode(raw, type=CurrentFactionSourceSet)
    except msgspec.DecodeError as exc:
        raise FactionSourcePromotionError("July current-source artifact is invalid.") from exc
    artifact.validate()
    return artifact


def current_source_records() -> tuple[CurrentFactionSourceRecord, ...]:
    return tuple(current_source_set().records)


def current_source_package_ids() -> tuple[str, ...]:
    return tuple(record.package_id for record in current_source_records())


def predecessor_source_package_ids() -> tuple[str, ...]:
    return tuple(
        record.predecessor_package_id
        for record in current_source_records()
        if record.predecessor_package_id is not None
    )


def audit_exact_current_source_mapping(
    records: tuple[CurrentFactionSourceRecord, ...],
) -> None:
    if type(records) is not tuple:
        raise FactionSourcePromotionError("Current-source audit requires a tuple.")
    CurrentFactionSourceSet(
        artifact_schema=ARTIFACT_SCHEMA,
        source_package_id=SOURCE_PACKAGE_ID,
        source_title=SOURCE_TITLE,
        source_version=SOURCE_VERSION,
        source_date=SOURCE_DATE,
        activation_status=ACTIVATION_STATUS,
        records=list(records),
        excluded_content_categories=["imperial-armour", "legends"],
    ).validate()


def audit_atomic_current_activation(
    *,
    current_source_package_ids: tuple[str, ...],
    phase17_source_package_ids: tuple[str, ...],
    runtime_source_package_ids: tuple[str, ...],
    runtime_module_paths_by_faction: Mapping[str, str],
    generated_current_documents: Mapping[str, str],
) -> None:
    groups = (
        current_source_package_ids,
        phase17_source_package_ids,
        runtime_source_package_ids,
    )
    if any(type(group) is not tuple for group in groups):
        raise FactionSourcePromotionError("July activation audit package-ID groups must be tuples.")
    records = current_source_records()
    expected_current_package_ids = tuple(record.package_id for record in records)
    if current_source_package_ids != expected_current_package_ids:
        raise FactionSourcePromotionError(
            "Default current-source packages are not the exact promoted set."
        )
    if phase17_source_package_ids != (
        PHASE17E_SOURCE_PACKAGE_ID,
        PHASE17F_SOURCE_PACKAGE_ID,
    ):
        raise FactionSourcePromotionError(
            "Phase 17E and Phase 17F did not switch to July together."
        )
    if runtime_source_package_ids != (PHASE17F_SOURCE_PACKAGE_ID,):
        raise FactionSourcePromotionError(
            "Default runtime registry is not linked to July Phase 17F."
        )
    if frozenset(runtime_module_paths_by_faction) != CURRENT_FACTION_IDS:
        raise FactionSourcePromotionError(
            "Default runtime registry must map the exact 28-faction set."
        )
    for faction_id, module_path in runtime_module_paths_by_faction.items():
        if type(faction_id) is not str or type(module_path) is not str:
            raise FactionSourcePromotionError(
                "Default runtime mappings must contain text identifiers."
            )
        module_name = faction_id.replace("-", "_")
        module_filename = "july_2026" if faction_id in _JULY_RUNTIME_FACTION_IDS else "manifest"
        expected_module_path = f"{_RUNTIME_MODULE_BASE}.{module_name}.{module_filename}"
        if module_path != expected_module_path:
            raise FactionSourcePromotionError("Default runtime faction module mapping drifted.")
    expected_filenames = {f"{faction_id}.md" for faction_id in CURRENT_FACTION_IDS}
    if set(generated_current_documents) != expected_filenames:
        raise FactionSourcePromotionError(
            "Generated current-support documents must cover exactly 28 factions."
        )
    records_by_faction = {record.faction_id: record for record in records}
    for filename, document in generated_current_documents.items():
        if type(filename) is not str or type(document) is not str:
            raise FactionSourcePromotionError(
                "Generated current-support documents must map filenames to text."
            )
        record = records_by_faction[filename.removesuffix(".md")]
        if (
            f"Current source package: `{record.package_id}`" not in document
            or record.pdf_filename not in document
        ):
            raise FactionSourcePromotionError(
                "Generated current-support document has stale source provenance."
            )


_validate_identifier = IdentifierValidator(FactionSourcePromotionError)


def _validate_text(field_name: str, value: object) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise FactionSourcePromotionError(
            f"July current-source {field_name} must be normalized text."
        )
    return value


def _validate_sha256(field_name: str, value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise FactionSourcePromotionError(
            f"July current-source {field_name} must be a lowercase SHA-256."
        )
    return value


def _validate_pdf_path(value: object) -> str:
    if (
        type(value) is not str
        or "\\" in value
        or ".." in value.split("/")
        or not value.startswith("data/raw/faction_packs/eng_")
        or not value.endswith(".pdf")
    ):
        raise FactionSourcePromotionError(
            "July current-source PDF path must be normalized faction-pack evidence."
        )
    return value


__all__ = (
    "ACTIVATION_STATUS",
    "CURRENT_FACTION_IDS",
    "DEATHWATCH_FACTION_ID",
    "DEATHWATCH_PACKAGE_ID",
    "DEATHWATCH_PDF_PATH",
    "DEATHWATCH_SHA256",
    "NO_ACTION_FACTION_IDS",
    "PHASE17E_SOURCE_PACKAGE_ID",
    "PHASE17F_SOURCE_PACKAGE_ID",
    "PROMOTED_FACTION_IDS",
    "SOURCE_DATE",
    "SOURCE_PACKAGE_ID",
    "SOURCE_TITLE",
    "SOURCE_VERSION",
    "CurrentFactionSourceRecord",
    "CurrentFactionSourceSet",
    "FactionSourcePromotionError",
    "audit_atomic_current_activation",
    "audit_exact_current_source_mapping",
    "current_source_package_ids",
    "current_source_records",
    "current_source_set",
    "predecessor_source_package_ids",
)
