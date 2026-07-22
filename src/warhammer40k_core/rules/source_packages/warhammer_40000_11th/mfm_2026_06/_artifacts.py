from __future__ import annotations

import msgspec

from warhammer40k_core.rules.mfm_source import (
    MfmDetachmentRecordPayload,
    MfmEnhancementRecordPayload,
    MfmFactionRecordPayload,
    MfmLeaderAllowancePayload,
    MfmSourceError,
    MfmUnitCostBracketPayload,
    MfmUnitCostRowPayload,
    MfmUnitRecordPayload,
    MfmWargearCostPayload,
)

MFM_SOURCE_PACKAGE_ARTIFACT_SCHEMA = "core-v2-mfm-source-package-v2"


class _MfmUnitCostRowArtifact(msgspec.Struct, frozen=True):
    raw_label: str
    label: str
    model_count: int | None
    model_name: str | None
    model_id: str | None
    model_component_counts: list[int]
    model_component_names: list[str]
    model_component_ids: list[str]
    additional_model_count: int | None
    additional_model_name: str | None
    additional_model_id: str | None
    points: int
    source_id: str

    def to_payload(self) -> MfmUnitCostRowPayload:
        return {
            "raw_label": self.raw_label,
            "label": self.label,
            "model_count": self.model_count,
            "model_name": self.model_name,
            "model_id": self.model_id,
            "model_component_counts": self.model_component_counts,
            "model_component_names": self.model_component_names,
            "model_component_ids": self.model_component_ids,
            "additional_model_count": self.additional_model_count,
            "additional_model_name": self.additional_model_name,
            "additional_model_id": self.additional_model_id,
            "points": self.points,
            "source_id": self.source_id,
        }


class _MfmUnitCostBracketArtifact(msgspec.Struct, frozen=True):
    raw_label: str
    label: str
    unit_number_min: int
    unit_number_max: int | None
    rows: list[_MfmUnitCostRowArtifact]
    source_id: str

    def to_payload(self) -> MfmUnitCostBracketPayload:
        return {
            "raw_label": self.raw_label,
            "label": self.label,
            "unit_number_min": self.unit_number_min,
            "unit_number_max": self.unit_number_max,
            "rows": [row.to_payload() for row in self.rows],
            "source_id": self.source_id,
        }


class _MfmWargearCostArtifact(msgspec.Struct, frozen=True):
    raw_name: str
    name: str
    wargear_id: str
    points_per_item: int
    source_id: str

    def to_payload(self) -> MfmWargearCostPayload:
        return {
            "raw_name": self.raw_name,
            "name": self.name,
            "wargear_id": self.wargear_id,
            "points_per_item": self.points_per_item,
            "source_id": self.source_id,
        }


class _MfmLeaderAllowanceArtifact(msgspec.Struct, frozen=True):
    allowed_bodyguard_unit_ids: list[str]
    allowed_bodyguard_names: list[str]
    source_id: str

    def to_payload(self) -> MfmLeaderAllowancePayload:
        return {
            "allowed_bodyguard_unit_ids": self.allowed_bodyguard_unit_ids,
            "allowed_bodyguard_names": self.allowed_bodyguard_names,
            "source_id": self.source_id,
        }


class _MfmUnitRecordArtifact(msgspec.Struct, frozen=True):
    record_id: str
    unit_id: str
    raw_name: str
    name: str
    source_section_id: str | None
    source_section_name: str | None
    cost_brackets: list[_MfmUnitCostBracketArtifact]
    wargear_costs: list[_MfmWargearCostArtifact]
    leader_allowance: _MfmLeaderAllowanceArtifact | None
    support_allowance: _MfmLeaderAllowanceArtifact | None
    source_id: str

    def to_payload(self) -> MfmUnitRecordPayload:
        return {
            "record_id": self.record_id,
            "unit_id": self.unit_id,
            "raw_name": self.raw_name,
            "name": self.name,
            "source_section_id": self.source_section_id,
            "source_section_name": self.source_section_name,
            "cost_brackets": [bracket.to_payload() for bracket in self.cost_brackets],
            "wargear_costs": [cost.to_payload() for cost in self.wargear_costs],
            "leader_allowance": (
                None if self.leader_allowance is None else self.leader_allowance.to_payload()
            ),
            "support_allowance": (
                None if self.support_allowance is None else self.support_allowance.to_payload()
            ),
            "source_id": self.source_id,
        }


class _MfmEnhancementRecordArtifact(msgspec.Struct, frozen=True):
    enhancement_id: str
    raw_name: str
    name: str
    points: int
    is_upgrade: bool
    leader_allowance: _MfmLeaderAllowanceArtifact | None
    source_id: str

    def to_payload(self) -> MfmEnhancementRecordPayload:
        return {
            "enhancement_id": self.enhancement_id,
            "raw_name": self.raw_name,
            "name": self.name,
            "points": self.points,
            "is_upgrade": self.is_upgrade,
            "leader_allowance": (
                None if self.leader_allowance is None else self.leader_allowance.to_payload()
            ),
            "source_id": self.source_id,
        }


class _MfmDetachmentRecordArtifact(msgspec.Struct, frozen=True):
    detachment_id: str
    raw_name: str
    name: str
    force_disposition_id: str | None
    detachment_point_cost: int | None
    enhancements: list[_MfmEnhancementRecordArtifact]
    source_id: str

    def to_payload(self) -> MfmDetachmentRecordPayload:
        return {
            "detachment_id": self.detachment_id,
            "raw_name": self.raw_name,
            "name": self.name,
            "force_disposition_id": self.force_disposition_id,
            "detachment_point_cost": self.detachment_point_cost,
            "enhancements": [enhancement.to_payload() for enhancement in self.enhancements],
            "source_id": self.source_id,
        }


class _MfmFactionRecordArtifact(msgspec.Struct, frozen=True):
    faction_id: str
    raw_name: str
    name: str
    url_path: str
    detachments: list[_MfmDetachmentRecordArtifact]
    units: list[_MfmUnitRecordArtifact]
    source_id: str

    def to_payload(self) -> MfmFactionRecordPayload:
        return {
            "faction_id": self.faction_id,
            "raw_name": self.raw_name,
            "name": self.name,
            "url_path": self.url_path,
            "detachments": [detachment.to_payload() for detachment in self.detachments],
            "units": [unit.to_payload() for unit in self.units],
            "source_id": self.source_id,
        }


class MfmPackageArtifact(msgspec.Struct, frozen=True):
    artifact_schema: str
    source_package_id: str
    source_title: str
    source_version: str
    source_date: str
    source_url: str
    excluded_faction_ids: list[str]
    faction_artifacts: dict[str, str]
    source_payload_checksum_sha256: str

    def validate(self) -> None:
        if self.artifact_schema != MFM_SOURCE_PACKAGE_ARTIFACT_SCHEMA:
            raise MfmSourceError("MFM package artifact schema is unsupported.")
        if not self.faction_artifacts:
            raise MfmSourceError("MFM package artifact must list faction artifacts.")
        seen_paths: set[str] = set()
        for faction_id, artifact_path in self.faction_artifacts.items():
            _validate_artifact_path(artifact_path)
            if artifact_path in seen_paths:
                raise MfmSourceError("MFM package artifact paths must not duplicate.")
            seen_paths.add(artifact_path)
            expected_suffix = f"{faction_id}.json"
            if not artifact_path.endswith(expected_suffix):
                raise MfmSourceError("MFM package artifact path must match faction_id.")


def mfm_package_artifact_from_json_bytes(raw: bytes) -> MfmPackageArtifact:
    artifact = _decode_json_artifact(
        raw,
        MfmPackageArtifact,
        artifact_description="package manifest",
    )
    artifact.validate()
    return artifact


def mfm_faction_payload_from_json_bytes(raw: bytes) -> MfmFactionRecordPayload:
    return _decode_json_artifact(
        raw,
        _MfmFactionRecordArtifact,
        artifact_description="faction payload",
    ).to_payload()


def _decode_json_artifact[ArtifactT](
    raw: bytes,
    artifact_type: type[ArtifactT],
    *,
    artifact_description: str,
) -> ArtifactT:
    try:
        return msgspec.json.decode(raw, type=artifact_type)
    except msgspec.DecodeError as exc:
        raise MfmSourceError(f"MFM {artifact_description} artifact is invalid.") from exc


def _validate_artifact_path(path: str) -> None:
    if type(path) is not str:
        raise MfmSourceError("MFM faction artifact path must be a string.")
    if "\\" in path or path.startswith("/") or path.endswith("/") or ".." in path.split("/"):
        raise MfmSourceError("MFM faction artifact path must be a normalized relative path.")
    if not path.startswith("factions/") or not path.endswith(".json"):
        raise MfmSourceError("MFM faction artifact path must reference a faction JSON artifact.")
