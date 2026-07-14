from __future__ import annotations

import hashlib
import json
from typing import cast

import msgspec

from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRError, RuleIRPayload

KHARSETH_RULE_IR_ARTIFACT_SCHEMA = "core-v2-kharseth-datasheet-rule-ir-v1"


class KharsethRuleIrArtifactError(ValueError):
    """Raised when the generated Kharseth RuleIR artifact is invalid or stale."""


class _KharsethRuleIrRecordArtifact(
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
            raise KharsethRuleIrArtifactError(
                "Kharseth generated RuleIR payload is invalid."
            ) from exc
        if cast(dict[str, object], rule_ir.to_payload()) != self.rule_ir:
            raise KharsethRuleIrArtifactError(
                "Kharseth generated RuleIR payload has unsupported fields."
            )
        expected_source_id = f"{source_package_id}:datasheet:{source_row_id}"
        if rule_ir.source_id != expected_source_id:
            raise KharsethRuleIrArtifactError("Kharseth RuleIR source identity drifted.")
        normalized_hash = hashlib.sha256(rule_ir.normalized_text.encode()).hexdigest()
        if normalized_hash != self.normalized_text_sha256:
            raise KharsethRuleIrArtifactError("Kharseth normalized rule text hash is stale.")
        if not rule_ir.is_supported:
            raise KharsethRuleIrArtifactError("Kharseth generated RuleIR must be fully supported.")
        return rule_ir


class KharsethRuleIrPackageArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    source_pdf_filename: str
    source_pdf_sha256: str
    source_page_numbers: list[int]
    datasheet_id: str
    datasheet_name: str
    records: dict[str, _KharsethRuleIrRecordArtifact]
    package_hash: str

    def validate(self) -> None:
        if self.artifact_schema != KHARSETH_RULE_IR_ARTIFACT_SCHEMA:
            raise KharsethRuleIrArtifactError("Kharseth RuleIR artifact schema is unsupported.")
        _validate_non_empty_string("source_package_id", self.source_package_id)
        _validate_non_empty_string("source_pdf_filename", self.source_pdf_filename)
        _validate_sha256("source_pdf_sha256", self.source_pdf_sha256)
        if self.source_page_numbers != [14, 15]:
            raise KharsethRuleIrArtifactError("Kharseth source page provenance drifted.")
        if self.datasheet_id != "000004194" or self.datasheet_name != "Kharseth":
            raise KharsethRuleIrArtifactError("Kharseth datasheet identity drifted.")
        if set(self.records) != {"000004194:4", "000004194:5"}:
            raise KharsethRuleIrArtifactError("Kharseth RuleIR source-row inventory drifted.")
        _validate_sha256("package_hash", self.package_hash)
        if self.package_hash != _package_hash(self):
            raise KharsethRuleIrArtifactError("Kharseth RuleIR package hash is stale.")
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


def kharseth_rule_ir_package_artifact_from_json_bytes(
    raw: bytes,
) -> KharsethRuleIrPackageArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=KharsethRuleIrPackageArtifact)
    except msgspec.DecodeError as exc:
        raise KharsethRuleIrArtifactError("Kharseth generated RuleIR artifact is invalid.") from exc
    artifact.validate()
    return artifact


def _package_hash(artifact: KharsethRuleIrPackageArtifact) -> str:
    payload = msgspec.to_builtins(artifact)
    if type(payload) is not dict:
        raise KharsethRuleIrArtifactError("Kharseth RuleIR artifact payload is invalid.")
    payload["package_hash"] = ""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_non_empty_string(field_name: str, value: object) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise KharsethRuleIrArtifactError(
            f"Kharseth RuleIR artifact {field_name} must be non-empty stripped text."
        )
    return value


def _validate_sha256(field_name: str, value: object) -> str:
    token = _validate_non_empty_string(field_name, value)
    if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
        raise KharsethRuleIrArtifactError(
            f"Kharseth RuleIR artifact {field_name} must be lowercase SHA-256."
        )
    return token
