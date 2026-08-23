from __future__ import annotations

import hashlib
import json
from typing import Final, cast

import msgspec

from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRError, RuleIRPayload

ARTIFACT_SCHEMA = "core-v2-emperors-children-lord-exultant-maulerfiend-chaos-spawn-rule-ir-v1"
EXPECTED_SOURCE_PACKAGE_ID = (
    "gw-11e-emperors-children-lord-exultant-maulerfiend-chaos-spawn-datasheets-2026-08"
)
EXPECTED_SOURCE_SNAPSHOT_FILENAME = "Datasheets_abilities.json"
EXPECTED_SOURCE_SNAPSHOT_SHA256 = "45e1eb1fb71438d1e2a9d4d916184083a3e5f397b1e3a2d1c1ff1eb77ddd4a01"
EXPECTED_SOURCE_ARTIFACT_HASH = "2cf705d43ab06ba0345438d9104a8cf4dc6eff2d8c13e19f230ec8aa6169b693"
EXPECTED_OFFICIAL_DOCUMENT_FILENAME = (
    "eng_22-07_warhammer_40,000_faction_pack_emperor_s_children-srspmclqtm-i8ey7hgk2s.pdf"
)
EXPECTED_OFFICIAL_DOCUMENT_SHA256 = (
    "1808fabb911f7a3e917ae5f2f12a6a7436ed97e1e5382238566dfd5e4540aa3c"
)
EXPECTED_REVIEW_MANIFEST_FILENAME = "faction_pack_datasheet_review_v1.json"
EXPECTED_REVIEW_MANIFEST_SHA256 = "36c98b702ee0ea168a816a5c080320dcbe4d3c75584049e1441184f6c8c8f23b"
EXPECTED_OVERLAY_PACKAGE_HASH = "c8a36f8301ace9121e92418f48d47818c8bc9b64ede895a0b84556bfba5824bb"
EXPECTED_PACKAGE_HASH: Final = "75d5b1641bf61b66f81d855c7c8f1acea4b2c5868f1ebe0cc35c31fbd4420ef9"

EXPECTED_DATASHEET_REVIEWS = {
    "000004078": (
        "Lord Exultant",
        "source:000004078",
        "unchanged_predecessor",
        None,
    ),
    "000004090": (
        "Chaos Spawn",
        "source:000004090",
        "rules_update",
        "Rules Updates, physical PDF page 9",
    ),
    "000004091": (
        "Maulerfiend",
        "source:000004091",
        "unchanged_predecessor",
        None,
    ),
}
EXPECTED_RECORD_IDENTITIES = {
    "000004078:4": ("000004078", "Lord Exultant", "Euphoric Strikes"),
    "000004078:5": ("000004078", "Lord Exultant", "LORD OF THE HOST"),
    "000004090:3": ("000004090", "Chaos Spawn", "Scuttling Horrors"),
    "000004091:3": ("000004091", "Maulerfiend", "Glutton for Punishment"),
}
EXPECTED_NORMALIZED_TEXT_SHA256 = {
    "000004078:4": ("25e0b51ee3dd0032335245b2395c002487584b176310f4567aeb17cfeca3c061"),
    "000004078:5": ("3c17e8920f6d33be40be6a0c40a296b7b08f99f86d3123e2f675bd8daa01d129"),
    "000004090:3": ("877148143367d60a89ab8b522fff000e992d80ace19a4cae9f0a07029eb9ee3c"),
    "000004091:3": ("e4815aa8797fcc8c40a1551d5a84913b7fb74ea541ab58fee1cc3ae8232ae618"),
}


class EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(ValueError):
    """Raised when the grouped Emperor's Children RuleIR artifact is invalid."""


class _DatasheetReviewArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    datasheet_id: str
    datasheet_name: str
    review_row_id: str
    review_treatment: str
    pdf_page_reference: str | None


class _RuleIrRecordArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    datasheet_id: str
    datasheet_name: str
    ability_name: str
    normalized_text_sha256: str
    rule_ir: dict[str, object]

    def validated_rule_ir(self, *, source_row_id: str, source_package_id: str) -> RuleIR:
        expected_identity = EXPECTED_RECORD_IDENTITIES.get(source_row_id)
        if (
            expected_identity is None
            or (
                self.datasheet_id,
                self.datasheet_name,
                self.ability_name,
            )
            != expected_identity
        ):
            raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
                "Grouped Emperor's Children RuleIR record identity drifted."
            )
        _validate_sha256("normalized_text_sha256", self.normalized_text_sha256)
        if self.normalized_text_sha256 != EXPECTED_NORMALIZED_TEXT_SHA256[source_row_id]:
            raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
                "Grouped Emperor's Children normalized rule text identity drifted."
            )
        try:
            rule_ir = RuleIR.from_payload(cast(RuleIRPayload, self.rule_ir))
        except (KeyError, RuleIRError, TypeError) as exc:
            raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
                "Grouped Emperor's Children generated RuleIR payload is invalid."
            ) from exc
        if cast(dict[str, object], rule_ir.to_payload()) != self.rule_ir:
            raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
                "Grouped Emperor's Children RuleIR payload has unsupported fields."
            )
        if rule_ir.source_id != f"{source_package_id}:datasheet:{source_row_id}":
            raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
                "Grouped Emperor's Children RuleIR source identity drifted."
            )
        normalized_hash = hashlib.sha256(rule_ir.normalized_text.encode()).hexdigest()
        if normalized_hash != self.normalized_text_sha256:
            raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
                "Grouped Emperor's Children normalized rule text hash is stale."
            )
        if (
            not rule_ir.is_supported
            or rule_ir.diagnostics
            or any(clause.diagnostics for clause in rule_ir.clauses)
        ):
            raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
                "Grouped Emperor's Children RuleIR must be fully supported without diagnostics."
            )
        return rule_ir


class EmperorsChildrenLordMaulerfiendSpawnRuleIrPackageArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    source_snapshot_filename: str
    source_snapshot_sha256: str
    source_artifact_hash: str
    official_document_filename: str
    official_document_sha256: str
    official_document_pages: list[int]
    review_manifest_filename: str
    review_manifest_sha256: str
    overlay_package_hash: str
    datasheets: list[_DatasheetReviewArtifact]
    records: dict[str, _RuleIrRecordArtifact]
    package_hash: str

    def validate(self) -> None:
        if self.artifact_schema != ARTIFACT_SCHEMA:
            raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
                "Grouped Emperor's Children RuleIR artifact schema is unsupported."
            )
        if self.source_package_id != EXPECTED_SOURCE_PACKAGE_ID:
            raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
                "Grouped Emperor's Children source package identity drifted."
            )
        expected_provenance = {
            "source_snapshot_filename": EXPECTED_SOURCE_SNAPSHOT_FILENAME,
            "source_snapshot_sha256": EXPECTED_SOURCE_SNAPSHOT_SHA256,
            "source_artifact_hash": EXPECTED_SOURCE_ARTIFACT_HASH,
            "official_document_filename": EXPECTED_OFFICIAL_DOCUMENT_FILENAME,
            "official_document_sha256": EXPECTED_OFFICIAL_DOCUMENT_SHA256,
            "review_manifest_filename": EXPECTED_REVIEW_MANIFEST_FILENAME,
            "review_manifest_sha256": EXPECTED_REVIEW_MANIFEST_SHA256,
            "overlay_package_hash": EXPECTED_OVERLAY_PACKAGE_HASH,
        }
        actual_provenance = {
            "source_snapshot_filename": self.source_snapshot_filename,
            "source_snapshot_sha256": self.source_snapshot_sha256,
            "source_artifact_hash": self.source_artifact_hash,
            "official_document_filename": self.official_document_filename,
            "official_document_sha256": self.official_document_sha256,
            "review_manifest_filename": self.review_manifest_filename,
            "review_manifest_sha256": self.review_manifest_sha256,
            "overlay_package_hash": self.overlay_package_hash,
        }
        if actual_provenance != expected_provenance:
            raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
                "Grouped Emperor's Children source provenance drifted."
            )
        if self.official_document_pages != [9]:
            raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
                "Grouped Emperor's Children official document page inventory drifted."
            )
        actual_reviews = {
            row.datasheet_id: (
                row.datasheet_name,
                row.review_row_id,
                row.review_treatment,
                row.pdf_page_reference,
            )
            for row in self.datasheets
        }
        if actual_reviews != EXPECTED_DATASHEET_REVIEWS or len(actual_reviews) != len(
            self.datasheets
        ):
            raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
                "Grouped Emperor's Children datasheet review inventory drifted."
            )
        if set(self.records) != set(EXPECTED_RECORD_IDENTITIES):
            raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
                "Grouped Emperor's Children RuleIR source-row inventory drifted."
            )
        for field_name, digest in (
            ("source_snapshot_sha256", self.source_snapshot_sha256),
            ("source_artifact_hash", self.source_artifact_hash),
            ("official_document_sha256", self.official_document_sha256),
            ("review_manifest_sha256", self.review_manifest_sha256),
            ("overlay_package_hash", self.overlay_package_hash),
            ("package_hash", self.package_hash),
        ):
            _validate_sha256(field_name, digest)
        if self.package_hash != _package_hash(self):
            raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
                "Grouped Emperor's Children RuleIR package hash is stale."
            )
        if self.package_hash != EXPECTED_PACKAGE_HASH:
            raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
                "Grouped Emperor's Children RuleIR package hash drifted from its reviewed pin."
            )
        for source_row_id, record in self.records.items():
            record.validated_rule_ir(
                source_row_id=source_row_id,
                source_package_id=self.source_package_id,
            )

    def rule_ir_payload_by_source_row_id(self, source_row_id: str) -> RuleIRPayload | None:
        record = self.records.get(source_row_id)
        if record is None:
            return None
        return record.validated_rule_ir(
            source_row_id=source_row_id,
            source_package_id=self.source_package_id,
        ).to_payload()


def artifact_from_json_bytes(
    raw: bytes,
) -> EmperorsChildrenLordMaulerfiendSpawnRuleIrPackageArtifact:
    try:
        artifact = msgspec.json.decode(
            raw,
            type=EmperorsChildrenLordMaulerfiendSpawnRuleIrPackageArtifact,
        )
    except msgspec.DecodeError as exc:
        raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
            "Grouped Emperor's Children generated RuleIR artifact is invalid."
        ) from exc
    artifact.validate()
    return artifact


def _package_hash(
    artifact: EmperorsChildrenLordMaulerfiendSpawnRuleIrPackageArtifact,
) -> str:
    payload = msgspec.to_builtins(artifact)
    if type(payload) is not dict:
        raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
            "Grouped Emperor's Children RuleIR artifact payload is invalid."
        )
    payload["package_hash"] = ""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_non_empty_string(field_name: str, value: object) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
            f"Grouped Emperor's Children RuleIR artifact {field_name} must be non-empty text."
        )
    return value


def _validate_sha256(field_name: str, value: object) -> str:
    token = _validate_non_empty_string(field_name, value)
    if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
        raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
            f"Grouped Emperor's Children RuleIR artifact {field_name} must be lowercase SHA-256."
        )
    return token
