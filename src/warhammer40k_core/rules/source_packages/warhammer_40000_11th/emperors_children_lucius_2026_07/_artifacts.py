from __future__ import annotations

import hashlib
import json
from typing import cast

import msgspec

from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRError, RuleIRPayload

LUCIUS_RULE_IR_ARTIFACT_SCHEMA = "core-v2-emperors-children-lucius-rule-ir-v1"
EXPECTED_SOURCE_PACKAGE_ID = "gw-11e-emperors-children-lucius-datasheet-2026-07"
EXPECTED_SOURCE_ROW_IDS = frozenset({"000004083:5", "000004083:6"})
EXPECTED_ABILITY_NAMES = {
    "000004083:5": "A Challenge Worthy of Skill",
    "000004083:6": "Duellist's Hubris",
}


class LuciusRuleIrArtifactError(ValueError):
    """Raised when the generated Lucius RuleIR artifact is invalid or stale."""


class _LuciusRuleIrRecordArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    ability_name: str
    normalized_text_sha256: str
    rule_ir: dict[str, object]

    def validated_rule_ir(self, *, source_row_id: str, source_package_id: str) -> RuleIR:
        _validate_non_empty_string("ability_name", self.ability_name)
        _validate_sha256("normalized_text_sha256", self.normalized_text_sha256)
        try:
            rule_ir = RuleIR.from_payload(cast(RuleIRPayload, self.rule_ir))
        except (KeyError, RuleIRError, TypeError) as exc:
            raise LuciusRuleIrArtifactError("Lucius generated RuleIR payload is invalid.") from exc
        if cast(dict[str, object], rule_ir.to_payload()) != self.rule_ir:
            raise LuciusRuleIrArtifactError(
                "Lucius generated RuleIR payload has unsupported fields."
            )
        if rule_ir.source_id != f"{source_package_id}:datasheet:{source_row_id}":
            raise LuciusRuleIrArtifactError("Lucius RuleIR source identity drifted.")
        normalized_hash = hashlib.sha256(rule_ir.normalized_text.encode()).hexdigest()
        if normalized_hash != self.normalized_text_sha256:
            raise LuciusRuleIrArtifactError("Lucius normalized rule text hash is stale.")
        if not rule_ir.is_supported:
            raise LuciusRuleIrArtifactError("Lucius generated RuleIR must be fully supported.")
        return rule_ir


class LuciusRuleIrPackageArtifact(
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
    review_row_id: str
    review_treatment: str
    overlay_package_hash: str
    datasheet_id: str
    datasheet_name: str
    records: dict[str, _LuciusRuleIrRecordArtifact]
    package_hash: str

    def validate(self) -> None:
        if self.artifact_schema != LUCIUS_RULE_IR_ARTIFACT_SCHEMA:
            raise LuciusRuleIrArtifactError("Lucius RuleIR artifact schema is unsupported.")
        if self.source_package_id != EXPECTED_SOURCE_PACKAGE_ID:
            raise LuciusRuleIrArtifactError("Lucius source package identity drifted.")
        if self.source_snapshot_filename != "Datasheets_abilities.json":
            raise LuciusRuleIrArtifactError("Lucius source snapshot filename drifted.")
        if not self.official_document_filename.startswith(
            "eng_22-07_warhammer_40,000_faction_pack_emperor_s_children"
        ):
            raise LuciusRuleIrArtifactError("Lucius official document identity drifted.")
        if self.official_document_pages:
            raise LuciusRuleIrArtifactError(
                "Lucius must not claim pages in a Faction Pack that did not reprint it."
            )
        if self.review_manifest_filename != "faction_pack_datasheet_review_v1.json":
            raise LuciusRuleIrArtifactError("Lucius review manifest identity drifted.")
        if (
            self.review_row_id != "source:000004083"
            or self.review_treatment != "unchanged_predecessor"
        ):
            raise LuciusRuleIrArtifactError("Lucius review treatment drifted.")
        for field_name, digest in (
            ("source_snapshot_sha256", self.source_snapshot_sha256),
            ("source_artifact_hash", self.source_artifact_hash),
            ("official_document_sha256", self.official_document_sha256),
            ("review_manifest_sha256", self.review_manifest_sha256),
            ("overlay_package_hash", self.overlay_package_hash),
            ("package_hash", self.package_hash),
        ):
            _validate_sha256(field_name, digest)
        if self.datasheet_id != "000004083" or self.datasheet_name != "Lucius the Eternal":
            raise LuciusRuleIrArtifactError("Lucius datasheet identity drifted.")
        if frozenset(self.records) != EXPECTED_SOURCE_ROW_IDS:
            raise LuciusRuleIrArtifactError("Lucius RuleIR source-row inventory drifted.")
        if self.package_hash != _package_hash(self):
            raise LuciusRuleIrArtifactError("Lucius RuleIR package hash is stale.")
        for source_row_id, record in self.records.items():
            if record.ability_name != EXPECTED_ABILITY_NAMES[source_row_id]:
                raise LuciusRuleIrArtifactError("Lucius RuleIR ability identity drifted.")
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


def lucius_rule_ir_package_artifact_from_json_bytes(
    raw: bytes,
) -> LuciusRuleIrPackageArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=LuciusRuleIrPackageArtifact)
    except msgspec.DecodeError as exc:
        raise LuciusRuleIrArtifactError("Lucius generated RuleIR artifact is invalid.") from exc
    artifact.validate()
    return artifact


def _package_hash(artifact: LuciusRuleIrPackageArtifact) -> str:
    payload = msgspec.to_builtins(artifact)
    if type(payload) is not dict:
        raise LuciusRuleIrArtifactError("Lucius RuleIR payload is invalid.")
    payload["package_hash"] = ""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_non_empty_string(field_name: str, value: object) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise LuciusRuleIrArtifactError(
            f"Lucius RuleIR artifact {field_name} must be non-empty stripped text."
        )
    return value


def _validate_sha256(field_name: str, value: object) -> str:
    token = _validate_non_empty_string(field_name, value)
    if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
        raise LuciusRuleIrArtifactError(
            f"Lucius RuleIR artifact {field_name} must be lowercase SHA-256."
        )
    return token
