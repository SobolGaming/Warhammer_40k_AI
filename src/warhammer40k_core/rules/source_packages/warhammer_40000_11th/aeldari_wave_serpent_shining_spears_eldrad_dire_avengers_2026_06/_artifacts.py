from __future__ import annotations

import hashlib
import json
from typing import cast

import msgspec

from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRError, RuleIRPayload

AELDARI_FOUR_DATASHEETS_RULE_IR_ARTIFACT_SCHEMA = (
    "core-v2-aeldari-wave-serpent-shining-spears-eldrad-dire-avengers-rule-ir-v1"
)
EXPECTED_SOURCE_PACKAGE_ID = (
    "gw-11e-aeldari-wave-serpent-shining-spears-eldrad-dire-avengers-datasheets-2026-06-14"
)
EXPECTED_DATASHEETS = {
    "000000568": "Eldrad Ulthran",
    "000000593": "Dire Avengers",
    "000000599": "Wave Serpent",
    "000000602": "Shining Spears",
}
EXPECTED_SOURCE_ROW_IDS = {
    "000000568:4",
    "000000593:2",
    "000000599:3",
    "000000602:2",
}


class AeldariFourDatasheetsRuleIrArtifactError(ValueError):
    """Raised when the generated Aeldari four-datasheet RuleIR artifact is invalid."""


class _AeldariFourDatasheetsRuleIrRecordArtifact(
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
            raise AeldariFourDatasheetsRuleIrArtifactError(
                "Aeldari four-datasheet generated RuleIR payload is invalid."
            ) from exc
        if cast(dict[str, object], rule_ir.to_payload()) != self.rule_ir:
            raise AeldariFourDatasheetsRuleIrArtifactError(
                "Aeldari four-datasheet RuleIR payload has unsupported fields."
            )
        if rule_ir.source_id != f"{source_package_id}:datasheet:{source_row_id}":
            raise AeldariFourDatasheetsRuleIrArtifactError(
                "Aeldari four-datasheet RuleIR source identity drifted."
            )
        normalized_hash = hashlib.sha256(rule_ir.normalized_text.encode()).hexdigest()
        if normalized_hash != self.normalized_text_sha256:
            raise AeldariFourDatasheetsRuleIrArtifactError(
                "Aeldari four-datasheet normalized rule text hash is stale."
            )
        if not rule_ir.is_supported:
            raise AeldariFourDatasheetsRuleIrArtifactError(
                "Aeldari four-datasheet generated RuleIR must be fully supported."
            )
        return rule_ir


class AeldariFourDatasheetsRuleIrPackageArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    source_snapshot_filename: str
    source_snapshot_sha256: str
    source_artifact_hash: str
    datasheets: dict[str, str]
    records: dict[str, _AeldariFourDatasheetsRuleIrRecordArtifact]
    package_hash: str

    def validate(self) -> None:
        if self.artifact_schema != AELDARI_FOUR_DATASHEETS_RULE_IR_ARTIFACT_SCHEMA:
            raise AeldariFourDatasheetsRuleIrArtifactError(
                "Aeldari four-datasheet RuleIR artifact schema is unsupported."
            )
        if self.source_package_id != EXPECTED_SOURCE_PACKAGE_ID:
            raise AeldariFourDatasheetsRuleIrArtifactError(
                "Aeldari four-datasheet source package identity drifted."
            )
        if self.source_snapshot_filename != "Datasheets_abilities.json":
            raise AeldariFourDatasheetsRuleIrArtifactError(
                "Aeldari four-datasheet source snapshot filename drifted."
            )
        _validate_sha256("source_snapshot_sha256", self.source_snapshot_sha256)
        _validate_sha256("source_artifact_hash", self.source_artifact_hash)
        if self.datasheets != EXPECTED_DATASHEETS:
            raise AeldariFourDatasheetsRuleIrArtifactError(
                "Aeldari four-datasheet inventory drifted."
            )
        if set(self.records) != EXPECTED_SOURCE_ROW_IDS:
            raise AeldariFourDatasheetsRuleIrArtifactError(
                "Aeldari four-datasheet RuleIR source-row inventory drifted."
            )
        _validate_sha256("package_hash", self.package_hash)
        if self.package_hash != _package_hash(self):
            raise AeldariFourDatasheetsRuleIrArtifactError(
                "Aeldari four-datasheet RuleIR package hash is stale."
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


def aeldari_four_datasheets_rule_ir_package_artifact_from_json_bytes(
    raw: bytes,
) -> AeldariFourDatasheetsRuleIrPackageArtifact:
    try:
        artifact = msgspec.json.decode(
            raw,
            type=AeldariFourDatasheetsRuleIrPackageArtifact,
        )
    except msgspec.DecodeError as exc:
        raise AeldariFourDatasheetsRuleIrArtifactError(
            "Aeldari four-datasheet generated RuleIR artifact is invalid."
        ) from exc
    artifact.validate()
    return artifact


def _package_hash(artifact: AeldariFourDatasheetsRuleIrPackageArtifact) -> str:
    payload = msgspec.to_builtins(artifact)
    if type(payload) is not dict:
        raise AeldariFourDatasheetsRuleIrArtifactError(
            "Aeldari four-datasheet RuleIR artifact payload is invalid."
        )
    payload["package_hash"] = ""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_non_empty_string(field_name: str, value: object) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise AeldariFourDatasheetsRuleIrArtifactError(
            f"Aeldari four-datasheet RuleIR artifact {field_name} must be non-empty stripped text."
        )
    return value


def _validate_sha256(field_name: str, value: object) -> str:
    token = _validate_non_empty_string(field_name, value)
    if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
        raise AeldariFourDatasheetsRuleIrArtifactError(
            f"Aeldari four-datasheet RuleIR artifact {field_name} must be lowercase SHA-256."
        )
    return token
