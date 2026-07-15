from __future__ import annotations

import hashlib
import json
from typing import cast

import msgspec

from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRError, RuleIRPayload

AELDARI_DATASHEET_RULE_IR_ARTIFACT_SCHEMA = "core-v2-aeldari-yriel-vypers-starfangs-rule-ir-v1"


class AeldariDatasheetRuleIrArtifactError(ValueError):
    """Raised when the generated Aeldari datasheet RuleIR artifact is invalid or stale."""


class AeldariDatasheetSourceArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    datasheet_id: str
    datasheet_name: str
    source_page_numbers: list[int]


class _AeldariDatasheetRuleIrRecordArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    datasheet_id: str
    datasheet_name: str
    ability_name: str
    normalized_text_sha256: str
    rule_ir: dict[str, object]

    def validated_rule_ir(self, *, source_row_id: str, source_package_id: str) -> RuleIR:
        _validate_non_empty_string("datasheet_id", self.datasheet_id)
        _validate_non_empty_string("datasheet_name", self.datasheet_name)
        _validate_non_empty_string("ability_name", self.ability_name)
        _validate_sha256("normalized_text_sha256", self.normalized_text_sha256)
        try:
            rule_ir = RuleIR.from_payload(cast(RuleIRPayload, self.rule_ir))
        except (KeyError, RuleIRError, TypeError) as exc:
            raise AeldariDatasheetRuleIrArtifactError(
                "Aeldari datasheet generated RuleIR payload is invalid."
            ) from exc
        if cast(dict[str, object], rule_ir.to_payload()) != self.rule_ir:
            raise AeldariDatasheetRuleIrArtifactError(
                "Aeldari datasheet generated RuleIR payload has unsupported fields."
            )
        if rule_ir.source_id != f"{source_package_id}:datasheet:{source_row_id}":
            raise AeldariDatasheetRuleIrArtifactError(
                "Aeldari datasheet RuleIR source identity drifted."
            )
        normalized_hash = hashlib.sha256(rule_ir.normalized_text.encode()).hexdigest()
        if normalized_hash != self.normalized_text_sha256:
            raise AeldariDatasheetRuleIrArtifactError(
                "Aeldari datasheet normalized rule text hash is stale."
            )
        if not rule_ir.is_supported:
            raise AeldariDatasheetRuleIrArtifactError(
                "Aeldari datasheet generated RuleIR must be fully supported."
            )
        return rule_ir


class AeldariDatasheetRuleIrPackageArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    source_pdf_filename: str
    source_pdf_sha256: str
    datasheets: list[AeldariDatasheetSourceArtifact]
    records: dict[str, _AeldariDatasheetRuleIrRecordArtifact]
    package_hash: str

    def validate(self) -> None:
        if self.artifact_schema != AELDARI_DATASHEET_RULE_IR_ARTIFACT_SCHEMA:
            raise AeldariDatasheetRuleIrArtifactError(
                "Aeldari datasheet RuleIR artifact schema is unsupported."
            )
        _validate_non_empty_string("source_package_id", self.source_package_id)
        _validate_non_empty_string("source_pdf_filename", self.source_pdf_filename)
        _validate_sha256("source_pdf_sha256", self.source_pdf_sha256)
        expected_datasheets = {
            "000004193": ("Prince Yriel", [12, 13]),
            "000000605": ("Vypers", [16, 17]),
            "000004195": ("Starfangs", [18, 19]),
        }
        actual_datasheets = {
            row.datasheet_id: (row.datasheet_name, row.source_page_numbers)
            for row in self.datasheets
        }
        if actual_datasheets != expected_datasheets:
            raise AeldariDatasheetRuleIrArtifactError(
                "Aeldari datasheet source-page inventory drifted."
            )
        if set(self.records) != {
            "000004193:4",
            "000004193:5",
            "000000605:3",
            "000004195:4",
        }:
            raise AeldariDatasheetRuleIrArtifactError(
                "Aeldari datasheet RuleIR source-row inventory drifted."
            )
        for source_row_id, record in self.records.items():
            expected = expected_datasheets.get(record.datasheet_id)
            if expected is None or record.datasheet_name != expected[0]:
                raise AeldariDatasheetRuleIrArtifactError(
                    "Aeldari datasheet RuleIR record identity drifted."
                )
            record.validated_rule_ir(
                source_row_id=source_row_id,
                source_package_id=self.source_package_id,
            )
        _validate_sha256("package_hash", self.package_hash)
        if self.package_hash != _package_hash(self):
            raise AeldariDatasheetRuleIrArtifactError(
                "Aeldari datasheet RuleIR package hash is stale."
            )

    def rule_ir_payload_by_source_row_id(self, source_row_id: str) -> RuleIRPayload | None:
        record = self.records.get(source_row_id)
        if record is None:
            return None
        return record.validated_rule_ir(
            source_row_id=source_row_id,
            source_package_id=self.source_package_id,
        ).to_payload()


def aeldari_datasheet_rule_ir_package_artifact_from_json_bytes(
    raw: bytes,
) -> AeldariDatasheetRuleIrPackageArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=AeldariDatasheetRuleIrPackageArtifact)
    except msgspec.DecodeError as exc:
        raise AeldariDatasheetRuleIrArtifactError(
            "Aeldari datasheet generated RuleIR artifact is invalid."
        ) from exc
    artifact.validate()
    return artifact


def _package_hash(artifact: AeldariDatasheetRuleIrPackageArtifact) -> str:
    payload = msgspec.to_builtins(artifact)
    if type(payload) is not dict:
        raise AeldariDatasheetRuleIrArtifactError(
            "Aeldari datasheet RuleIR artifact payload is invalid."
        )
    payload["package_hash"] = ""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_non_empty_string(field_name: str, value: object) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise AeldariDatasheetRuleIrArtifactError(
            f"Aeldari datasheet RuleIR artifact {field_name} must be non-empty stripped text."
        )
    return value


def _validate_sha256(field_name: str, value: object) -> str:
    token = _validate_non_empty_string(field_name, value)
    if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
        raise AeldariDatasheetRuleIrArtifactError(
            f"Aeldari datasheet RuleIR artifact {field_name} must be lowercase SHA-256."
        )
    return token
