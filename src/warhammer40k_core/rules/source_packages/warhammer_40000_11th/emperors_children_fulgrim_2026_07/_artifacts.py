from __future__ import annotations

import hashlib
import json
from typing import cast

import msgspec

from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRError, RuleIRPayload

FULGRIM_RULE_IR_ARTIFACT_SCHEMA = "core-v2-emperors-children-fulgrim-rule-ir-v1"
EXPECTED_SOURCE_PACKAGE_ID = "gw-11e-emperors-children-fulgrim-datasheet-2026-07"
EXPECTED_SOURCE_ROW_IDS = frozenset(f"000004077:{line}" for line in range(4, 10))
EXPECTED_ABILITY_NAMES = {
    "000004077:4": "Daemonic Poisons",
    "000004077:5": "Daemon Primarch of Slaanesh",
    "000004077:6": "Serpentine",
    "000004077:7": "Beguiling Form",
    "000004077:8": "Daemonic Speed",
    "000004077:9": "Enthralling Hypnosis (Aura)",
}


class FulgrimRuleIrArtifactError(ValueError):
    """Raised when the generated Fulgrim RuleIR artifact is invalid or stale."""


class _FulgrimRuleIrRecordArtifact(
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
            raise FulgrimRuleIrArtifactError(
                "Fulgrim generated RuleIR payload is invalid."
            ) from exc
        if cast(dict[str, object], rule_ir.to_payload()) != self.rule_ir:
            raise FulgrimRuleIrArtifactError(
                "Fulgrim generated RuleIR payload has unsupported fields."
            )
        if rule_ir.source_id != f"{source_package_id}:datasheet:{source_row_id}":
            raise FulgrimRuleIrArtifactError("Fulgrim RuleIR source identity drifted.")
        normalized_hash = hashlib.sha256(rule_ir.normalized_text.encode()).hexdigest()
        if normalized_hash != self.normalized_text_sha256:
            raise FulgrimRuleIrArtifactError("Fulgrim normalized rule text hash is stale.")
        if not rule_ir.is_supported:
            raise FulgrimRuleIrArtifactError("Fulgrim generated RuleIR must be fully supported.")
        return rule_ir


class FulgrimRuleIrPackageArtifact(
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
    overlay_package_hash: str
    datasheet_id: str
    datasheet_name: str
    records: dict[str, _FulgrimRuleIrRecordArtifact]
    package_hash: str

    def validate(self) -> None:
        if self.artifact_schema != FULGRIM_RULE_IR_ARTIFACT_SCHEMA:
            raise FulgrimRuleIrArtifactError("Fulgrim RuleIR artifact schema is unsupported.")
        if self.source_package_id != EXPECTED_SOURCE_PACKAGE_ID:
            raise FulgrimRuleIrArtifactError("Fulgrim source package identity drifted.")
        if self.source_snapshot_filename != "Datasheets_abilities.json":
            raise FulgrimRuleIrArtifactError("Fulgrim source snapshot filename drifted.")
        if not self.official_document_filename.startswith(
            "eng_22-07_warhammer_40,000_faction_pack_emperor_s_children"
        ):
            raise FulgrimRuleIrArtifactError("Fulgrim official document identity drifted.")
        if self.official_document_pages != [8, 9]:
            raise FulgrimRuleIrArtifactError("Fulgrim official document pages drifted.")
        for field_name, digest in (
            ("source_snapshot_sha256", self.source_snapshot_sha256),
            ("source_artifact_hash", self.source_artifact_hash),
            ("official_document_sha256", self.official_document_sha256),
            ("overlay_package_hash", self.overlay_package_hash),
            ("package_hash", self.package_hash),
        ):
            _validate_sha256(field_name, digest)
        if self.datasheet_id != "000004077" or self.datasheet_name != "Fulgrim":
            raise FulgrimRuleIrArtifactError("Fulgrim datasheet identity drifted.")
        if frozenset(self.records) != EXPECTED_SOURCE_ROW_IDS:
            raise FulgrimRuleIrArtifactError("Fulgrim RuleIR source-row inventory drifted.")
        if self.package_hash != _package_hash(self):
            raise FulgrimRuleIrArtifactError("Fulgrim RuleIR package hash is stale.")
        for source_row_id, record in self.records.items():
            if record.ability_name != EXPECTED_ABILITY_NAMES[source_row_id]:
                raise FulgrimRuleIrArtifactError("Fulgrim RuleIR ability identity drifted.")
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


def fulgrim_rule_ir_package_artifact_from_json_bytes(
    raw: bytes,
) -> FulgrimRuleIrPackageArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=FulgrimRuleIrPackageArtifact)
    except msgspec.DecodeError as exc:
        raise FulgrimRuleIrArtifactError("Fulgrim generated RuleIR artifact is invalid.") from exc
    artifact.validate()
    return artifact


def _package_hash(artifact: FulgrimRuleIrPackageArtifact) -> str:
    payload = msgspec.to_builtins(artifact)
    if type(payload) is not dict:
        raise FulgrimRuleIrArtifactError("Fulgrim RuleIR payload is invalid.")
    payload["package_hash"] = ""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_non_empty_string(field_name: str, value: object) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise FulgrimRuleIrArtifactError(
            f"Fulgrim RuleIR artifact {field_name} must be non-empty stripped text."
        )
    return value


def _validate_sha256(field_name: str, value: object) -> str:
    token = _validate_non_empty_string(field_name, value)
    if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
        raise FulgrimRuleIrArtifactError(
            f"Fulgrim RuleIR artifact {field_name} must be lowercase SHA-256."
        )
    return token
