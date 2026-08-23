from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, cast

import msgspec

from warhammer40k_core.rules.parsed_tokens import RuleTokenError
from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRError, RuleIRPayload

FACTION_PACK_RULE_IR_PACKAGE_ARTIFACT_SCHEMA: Final = "core-v2-faction-pack-rule-ir-package-v1"
FACTION_PACK_RULE_IR_SHARD_ARTIFACT_SCHEMA: Final = "core-v2-faction-pack-rule-ir-shard-v1"
FACTION_PACK_RULE_IR_EDITION: Final = 11
FACTION_PACK_RULE_IR_REGISTRY_ID: Final = "warhammer-40000-11th-faction-pack-rule-ir"


class FactionPackRuleIrRegistryError(ValueError):
    """Raised when the generated faction-pack RuleIR registry is invalid."""


class _ShardArtifactReferenceWire(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    path: str
    sha256: str
    source_package_ids: list[str]
    datasheet_ids: list[str]
    source_row_ids: list[str]


class _ManifestWire(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    edition: int
    registry_id: str
    shard_artifacts: dict[str, _ShardArtifactReferenceWire]
    package_hash: str


class _DatasheetFactionIdsProvenanceWire(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    source_snapshot_filename: str
    source_snapshot_sha256: str
    source_artifact_hash: str


class _ShardArtifactWire(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    edition: int
    shard_id: str
    datasheet_faction_ids: dict[str, str]
    datasheet_faction_ids_provenance: _DatasheetFactionIdsProvenanceWire
    source_packages: dict[str, dict[str, object]]
    package_hash: str


class _SnapshotMultiDatasheetSourcePackageWire(
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
    records: dict[str, dict[str, object]]
    package_hash: str


class _DualSnapshotMultiDatasheetSourcePackageWire(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    source_snapshot_filename: str
    source_snapshot_sha256: str
    source_artifact_hash: str
    datasheet_source_snapshot_filename: str
    datasheet_source_snapshot_sha256: str
    datasheet_source_artifact_hash: str
    datasheets: dict[str, str]
    records: dict[str, dict[str, object]]
    package_hash: str


class _SnapshotSingleDatasheetSourcePackageWire(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    source_snapshot_filename: str
    source_snapshot_sha256: str
    source_artifact_hash: str
    datasheet_id: str
    datasheet_name: str
    records: dict[str, dict[str, object]]
    package_hash: str


class _PdfSingleDatasheetSourcePackageWire(
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
    records: dict[str, dict[str, object]]
    package_hash: str


class _PdfDatasheetWire(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    datasheet_id: str
    datasheet_name: str
    source_page_numbers: list[int]


class _PdfMultiDatasheetSourcePackageWire(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    source_pdf_filename: str
    source_pdf_sha256: str
    datasheets: list[_PdfDatasheetWire]
    records: dict[str, dict[str, object]]
    package_hash: str


class _OfficialSnapshotSingleDatasheetSourcePackageWire(
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
    records: dict[str, dict[str, object]]
    package_hash: str


class _OfficialSnapshotMultiDatasheetSourcePackageWire(
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
    datasheets: dict[str, str]
    records: dict[str, dict[str, object]]
    package_hash: str


class _ReviewedDatasheetWire(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    datasheet_id: str
    datasheet_name: str
    review_row_id: str
    review_treatment: str
    pdf_page_reference: str | None


class _ReviewedOfficialSnapshotMultiDatasheetSourcePackageWire(
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
    review_manifest_filename: str
    review_manifest_sha256: str
    datasheets: list[_ReviewedDatasheetWire]
    records: dict[str, dict[str, object]]
    package_hash: str


class _ReviewedOfficialSnapshotSingleDatasheetSourcePackageWire(
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
    review_manifest_filename: str
    review_manifest_sha256: str
    review_row_id: str
    review_treatment: str
    datasheet_id: str
    datasheet_name: str
    records: dict[str, dict[str, object]]
    package_hash: str


@dataclass(frozen=True, slots=True)
class RuleIrShardArtifactReference:
    path: str
    sha256: str
    source_package_ids: tuple[str, ...]
    datasheet_ids: tuple[str, ...]
    source_row_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FactionPackRuleIrManifestArtifact:
    artifact_schema: str
    edition: int
    registry_id: str
    shard_artifacts: Mapping[str, RuleIrShardArtifactReference]
    package_hash: str


@dataclass(frozen=True, slots=True)
class DatasheetFactionIdsProvenance:
    source_snapshot_filename: str
    source_snapshot_sha256: str
    source_artifact_hash: str


@dataclass(frozen=True, slots=True)
class _SourcePackageDescriptor:
    artifact_schema: str
    package_hash: str
    wire_type: type[msgspec.Struct]


_SOURCE_PACKAGE_DESCRIPTOR_BY_ID: Final = MappingProxyType(
    {
        "gw-11e-aeldari-aspect-warriors-datasheets-2026-06-14": _SourcePackageDescriptor(
            artifact_schema="core-v2-aeldari-aspect-warriors-rule-ir-v1",
            package_hash="17baafd1a74f9d4fbf95c984022c31cee6700cac6252653d149d0ebc51067c9a",
            wire_type=_SnapshotMultiDatasheetSourcePackageWire,
        ),
        "gw-11e-aeldari-autarchs-datasheets-2026-06-14": _SourcePackageDescriptor(
            artifact_schema="core-v2-aeldari-autarchs-rule-ir-v1",
            package_hash="cf07556046e8afedaceb7e8bfdce9232d0d0c1a636d9a184492b5a3a18b7285d",
            wire_type=_SnapshotMultiDatasheetSourcePackageWire,
        ),
        "gw-11e-aeldari-banshees-phoenix-lords-spiritseer-2026-06-14": (
            _SourcePackageDescriptor(
                artifact_schema=("core-v2-aeldari-banshees-phoenix-lords-spiritseer-rule-ir-v1"),
                package_hash=("5a7ce021398b87a25afc09d09caa88899a1a02ced42800e0ebb948dd98f922f3"),
                wire_type=_SnapshotMultiDatasheetSourcePackageWire,
            )
        ),
        "gw-11e-aeldari-corsair-skyreavers-datasheet-2026-06-09": (
            _SourcePackageDescriptor(
                artifact_schema="core-v2-corsair-skyreavers-datasheet-rule-ir-v1",
                package_hash=("0b101ecff4e275e775cdd18168907924362dde91fa23234048e80fa809234bd8"),
                wire_type=_PdfSingleDatasheetSourcePackageWire,
            )
        ),
        "gw-11e-aeldari-corsair-void-units-datasheets-2026-06-14": (
            _SourcePackageDescriptor(
                artifact_schema="core-v2-corsair-void-units-datasheet-rule-ir-v1",
                package_hash=("27757f36ccef22e12d95a41f9cc556bbd675ea3e1f319f8c46458fd525d317fe"),
                wire_type=_SnapshotMultiDatasheetSourcePackageWire,
            )
        ),
        "gw-11e-aeldari-kharseth-datasheet-2026-06-09": _SourcePackageDescriptor(
            artifact_schema="core-v2-kharseth-datasheet-rule-ir-v1",
            package_hash="dfc876685dbb22509fa6bc5b9943566502ab0be41b0d6c4318501a6a31cdcdd7",
            wire_type=_PdfSingleDatasheetSourcePackageWire,
        ),
        "gw-11e-aeldari-night-spinner-datasheet-2026-06-14": _SourcePackageDescriptor(
            artifact_schema="core-v2-aeldari-night-spinner-rule-ir-v1",
            package_hash="48799f43bc37a0550a7e98108f4e7db1751f3b6ab81d91c129608861a5807bf4",
            wire_type=_SnapshotSingleDatasheetSourcePackageWire,
        ),
        "gw-11e-aeldari-shroud-runners-wraithblades-datasheets-2026-06-14": (
            _SourcePackageDescriptor(
                artifact_schema="core-v2-aeldari-shroud-runners-wraithblades-rule-ir-v1",
                package_hash=("68fb87b5cc51bee327efbd5b067ba8b00ee51c6ea52e4b95f66eddc948ce53c4"),
                wire_type=_SnapshotMultiDatasheetSourcePackageWire,
            )
        ),
        "gw-11e-aeldari-war-walkers-wraithlord-datasheets-2026-06-14": (
            _SourcePackageDescriptor(
                artifact_schema="core-v2-aeldari-war-walkers-wraithlord-rule-ir-v1",
                package_hash=("39c0dabeb1520084ad34d920aaf714a5a0bfacc34d0e63d88cc55b4aa2600391"),
                wire_type=_SnapshotMultiDatasheetSourcePackageWire,
            )
        ),
        "gw-11e-aeldari-wave-serpent-shining-spears-eldrad-dire-avengers-datasheets-2026-06-14": (
            _SourcePackageDescriptor(
                artifact_schema=(
                    "core-v2-aeldari-wave-serpent-shining-spears-eldrad-dire-avengers-rule-ir-v1"
                ),
                package_hash=("5f39ee4b924f4cedcc23c45fda700e032963f5f73dbdbd32bbe12f27321db6f6"),
                wire_type=_SnapshotMultiDatasheetSourcePackageWire,
            )
        ),
        "gw-11e-aeldari-yriel-vypers-starfangs-datasheets-2026-06-09": (
            _SourcePackageDescriptor(
                artifact_schema="core-v2-aeldari-yriel-vypers-starfangs-rule-ir-v1",
                package_hash=("4c4365b3bab531561639f390b6cf12d18ee35fd5eb3a11ad8b61d3c7e6a78627"),
                wire_type=_PdfMultiDatasheetSourcePackageWire,
            )
        ),
        "gw-11e-chaos-daemons-datasheet-ir-2026-27": _SourcePackageDescriptor(
            artifact_schema="core-v2-chaos-daemons-datasheet-rule-ir-v1",
            package_hash="b0a9d9c6e9d8bd96d578bb17751362b2a3cd9aff531940c59b35498668b72754",
            wire_type=_DualSnapshotMultiDatasheetSourcePackageWire,
        ),
        "gw-11e-emperors-children-fulgrim-datasheet-2026-07": _SourcePackageDescriptor(
            artifact_schema="core-v2-emperors-children-fulgrim-rule-ir-v1",
            package_hash="90b27e3a76f6a2c5b0b5cd3ad678ea284f202ac8f072ef35126d0762792a6d09",
            wire_type=_OfficialSnapshotSingleDatasheetSourcePackageWire,
        ),
        "gw-11e-emperors-children-infractors-tormentors-datasheets-2026-08": (
            _SourcePackageDescriptor(
                artifact_schema=("core-v2-emperors-children-infractors-tormentors-rule-ir-v1"),
                package_hash=("076824923ec39f2ce539c6e2dbd1c763143797c688fb36abebfd4104d8f38059"),
                wire_type=_OfficialSnapshotMultiDatasheetSourcePackageWire,
            )
        ),
        "gw-11e-emperors-children-lord-exultant-maulerfiend-chaos-spawn-datasheets-2026-08": (
            _SourcePackageDescriptor(
                artifact_schema=(
                    "core-v2-emperors-children-lord-exultant-maulerfiend-chaos-spawn-rule-ir-v1"
                ),
                package_hash=("75d5b1641bf61b66f81d855c7c8f1acea4b2c5868f1ebe0cc35c31fbd4420ef9"),
                wire_type=_ReviewedOfficialSnapshotMultiDatasheetSourcePackageWire,
            )
        ),
        "gw-11e-emperors-children-lucius-datasheet-2026-07": _SourcePackageDescriptor(
            artifact_schema="core-v2-emperors-children-lucius-rule-ir-v1",
            package_hash="7c770c35c173b33b320af89cc878ca4398567976741160f7ff4873272118877f",
            wire_type=_ReviewedOfficialSnapshotSingleDatasheetSourcePackageWire,
        ),
    }
)


@dataclass(frozen=True, slots=True)
class SourcePackageRuleIrArtifact:
    shard_id: str
    source_package_id: str
    artifact_schema: str
    package_hash: str
    _payload: dict[str, object] = field(repr=False)
    _rule_ir_by_source_row_id: Mapping[str, RuleIR] = field(repr=False)
    _datasheet_ids: tuple[str, ...] = field(repr=False)

    def payload(self) -> dict[str, object]:
        return deepcopy(self._payload)

    def supported_datasheet_ids(self) -> tuple[str, ...]:
        return self._datasheet_ids

    def supported_datasheet_source_row_ids(self) -> tuple[str, ...]:
        return tuple(self._rule_ir_by_source_row_id)

    def datasheet_rule_ir_payload_by_source_row_id(
        self,
        source_row_id: str,
    ) -> RuleIRPayload | None:
        _validate_lookup_token("source_row_id", source_row_id)
        rule_ir = self._rule_ir_by_source_row_id.get(source_row_id)
        return None if rule_ir is None else rule_ir.to_payload()

    def validate_generated_artifact_bytes(self, raw: bytes) -> None:
        candidate_payload = _json_object_from_bytes(
            raw,
            artifact_description="source-package component",
        )
        candidate_source_package_id = _required_non_empty_string(
            candidate_payload,
            "source_package_id",
        )
        if candidate_source_package_id != self.source_package_id:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR component source identity does not match its source package."
            )
        candidate = _source_package_artifact_from_payload(
            candidate_payload,
            shard_id=self.shard_id,
        )
        if candidate.source_package_id != self.source_package_id:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR component source_package_id does not match its registry pin."
            )
        if candidate.package_hash != self.package_hash:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR component package_hash does not match its registry pin."
            )
        if candidate.payload() != self.payload():
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR component payload does not match its registry pin."
            )


@dataclass(frozen=True, slots=True)
class FactionPackRuleIrShardArtifact:
    artifact_schema: str
    edition: int
    shard_id: str
    datasheet_faction_ids: Mapping[str, str]
    datasheet_faction_ids_provenance: DatasheetFactionIdsProvenance
    source_packages: Mapping[str, SourcePackageRuleIrArtifact]
    package_hash: str

    def supported_source_package_ids(self) -> tuple[str, ...]:
        return tuple(self.source_packages)

    def supported_datasheet_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    datasheet_id
                    for source_package in self.source_packages.values()
                    for datasheet_id in source_package.supported_datasheet_ids()
                }
            )
        )

    def supported_datasheet_source_row_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                source_row_id
                for source_package in self.source_packages.values()
                for source_row_id in source_package.supported_datasheet_source_row_ids()
            )
        )


def manifest_from_json_bytes(raw: bytes) -> FactionPackRuleIrManifestArtifact:
    payload = _json_object_from_bytes(raw, artifact_description="package manifest")
    wire = _decode_wire(raw, _ManifestWire, artifact_description="package manifest")
    _validate_manifest_wire(wire, payload=payload)
    references = {
        shard_id: RuleIrShardArtifactReference(
            path=reference.path,
            sha256=reference.sha256,
            source_package_ids=tuple(reference.source_package_ids),
            datasheet_ids=tuple(reference.datasheet_ids),
            source_row_ids=tuple(reference.source_row_ids),
        )
        for shard_id, reference in sorted(wire.shard_artifacts.items())
    }
    return FactionPackRuleIrManifestArtifact(
        artifact_schema=wire.artifact_schema,
        edition=wire.edition,
        registry_id=wire.registry_id,
        shard_artifacts=MappingProxyType(references),
        package_hash=wire.package_hash,
    )


def shard_artifact_from_json_bytes(raw: bytes) -> FactionPackRuleIrShardArtifact:
    payload = _json_object_from_bytes(raw, artifact_description="physical shard")
    wire = _decode_wire(raw, _ShardArtifactWire, artifact_description="physical shard")
    _validate_shard_wire(wire, payload=payload)
    source_packages: dict[str, SourcePackageRuleIrArtifact] = {}
    seen_source_row_ids: set[str] = set()
    for source_package_id, source_package_payload in sorted(wire.source_packages.items()):
        source_package = _source_package_artifact_from_payload(
            source_package_payload,
            shard_id=wire.shard_id,
        )
        if source_package.source_package_id != source_package_id:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR source-package mapping key does not match source_package_id."
            )
        duplicate_source_row_ids = seen_source_row_ids.intersection(
            source_package.supported_datasheet_source_row_ids()
        )
        if duplicate_source_row_ids:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR source_row_ids must be unique across source packages."
            )
        seen_source_row_ids.update(source_package.supported_datasheet_source_row_ids())
        source_packages[source_package_id] = source_package
    supported_datasheet_ids = {
        datasheet_id
        for source_package in source_packages.values()
        for datasheet_id in source_package.supported_datasheet_ids()
    }
    if set(wire.datasheet_faction_ids) != supported_datasheet_ids:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR shard datasheet faction inventory does not match its source "
            "packages."
        )
    datasheet_faction_ids = {
        _validate_lookup_token("datasheet_id", datasheet_id): _validate_canonical_id(
            "datasheet faction_id",
            faction_id,
        )
        for datasheet_id, faction_id in sorted(wire.datasheet_faction_ids.items())
    }
    provenance = wire.datasheet_faction_ids_provenance
    _validate_provenance_filename(
        "datasheet faction source_snapshot_filename",
        provenance.source_snapshot_filename,
        suffix=".json",
    )
    _validate_sha256(
        "datasheet faction source_snapshot_sha256",
        provenance.source_snapshot_sha256,
    )
    _validate_sha256(
        "datasheet faction source_artifact_hash",
        provenance.source_artifact_hash,
    )
    return FactionPackRuleIrShardArtifact(
        artifact_schema=wire.artifact_schema,
        edition=wire.edition,
        shard_id=wire.shard_id,
        datasheet_faction_ids=MappingProxyType(datasheet_faction_ids),
        datasheet_faction_ids_provenance=DatasheetFactionIdsProvenance(
            source_snapshot_filename=provenance.source_snapshot_filename,
            source_snapshot_sha256=provenance.source_snapshot_sha256,
            source_artifact_hash=provenance.source_artifact_hash,
        ),
        source_packages=MappingProxyType(source_packages),
        package_hash=wire.package_hash,
    )


def _validate_manifest_wire(wire: _ManifestWire, *, payload: dict[str, object]) -> None:
    if wire.artifact_schema != FACTION_PACK_RULE_IR_PACKAGE_ARTIFACT_SCHEMA:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR package manifest schema is unsupported."
        )
    if wire.edition != FACTION_PACK_RULE_IR_EDITION:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR package manifest edition is unsupported."
        )
    if wire.registry_id != FACTION_PACK_RULE_IR_REGISTRY_ID:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR package manifest registry_id is unsupported."
        )
    if not wire.shard_artifacts:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR package manifest must list shard artifacts."
        )
    _validate_package_hash(payload, artifact_description="package manifest")

    seen_paths: set[str] = set()
    seen_source_package_ids: set[str] = set()
    seen_source_row_ids: set[str] = set()
    for shard_id, reference in wire.shard_artifacts.items():
        _validate_canonical_id("shard_id", shard_id)
        expected_path = f"shards/{shard_id}.json"
        if reference.path != expected_path:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR shard artifact path must match shard_id."
            )
        if reference.path in seen_paths:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR shard artifact paths must be unique."
            )
        seen_paths.add(reference.path)
        _validate_sha256("shard artifact sha256", reference.sha256)
        source_package_ids = _validate_sorted_inventory(
            "source_package_ids",
            reference.source_package_ids,
        )
        _validate_sorted_inventory("datasheet_ids", reference.datasheet_ids)
        source_row_ids = _validate_sorted_inventory("source_row_ids", reference.source_row_ids)
        if seen_source_package_ids.intersection(source_package_ids):
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR source_package_ids must be globally unique."
            )
        if seen_source_row_ids.intersection(source_row_ids):
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR source_row_ids must be globally unique."
            )
        seen_source_package_ids.update(source_package_ids)
        seen_source_row_ids.update(source_row_ids)


def _validate_shard_wire(
    wire: _ShardArtifactWire,
    *,
    payload: dict[str, object],
) -> None:
    if wire.artifact_schema != FACTION_PACK_RULE_IR_SHARD_ARTIFACT_SCHEMA:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR shard artifact schema is unsupported."
        )
    if wire.edition != FACTION_PACK_RULE_IR_EDITION:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR shard artifact edition is unsupported."
        )
    _validate_canonical_id("shard_id", wire.shard_id)
    if not wire.datasheet_faction_ids:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR shard must contain datasheet faction identities."
        )
    if not wire.source_packages:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR shard artifact must contain source packages."
        )
    _validate_package_hash(payload, artifact_description="shard artifact")


def _source_package_artifact_from_payload(
    payload: dict[str, object],
    *,
    shard_id: str,
) -> SourcePackageRuleIrArtifact:
    source_package_id = _required_non_empty_string(payload, "source_package_id")
    descriptor = _SOURCE_PACKAGE_DESCRIPTOR_BY_ID.get(source_package_id)
    if descriptor is None:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR source_package_id is not registered."
        )
    _validate_source_package_shape(payload, descriptor=descriptor)
    artifact_schema = _required_non_empty_string(payload, "artifact_schema")
    if artifact_schema != descriptor.artifact_schema:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR source-package component schema is unsupported; "
            "package_hash does not match its registry pin."
        )
    package_hash = _required_non_empty_string(payload, "package_hash")
    _validate_package_hash(payload, artifact_description="source-package component")
    try:
        _validate_source_package_provenance(payload)
    except FactionPackRuleIrRegistryError as exc:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR source-package provenance is malformed; package_hash does not "
            "match its registry pin."
        ) from exc
    datasheet_names = _datasheet_names_by_id(payload)
    records_value = payload.get("records")
    if type(records_value) is not dict or not records_value:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR source-package records must be a non-empty object."
        )
    records = cast(dict[str, object], records_value)
    rule_ir_by_source_row_id: dict[str, RuleIR] = {}
    seen_rule_ids: set[str] = set()
    represented_datasheet_ids: set[str] = set()
    for source_row_id, record_value in sorted(records.items()):
        _validate_lookup_token("source_row_id", source_row_id)
        datasheet_id = _datasheet_id_from_source_row_id(source_row_id)
        if datasheet_id not in datasheet_names:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR source row references an undeclared datasheet_id."
            )
        represented_datasheet_ids.add(datasheet_id)
        if type(record_value) is not dict:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR source-package record must be an object."
            )
        record = cast(dict[str, object], record_value)
        rule_ir = _validated_record_rule_ir(
            record,
            source_row_id=source_row_id,
            source_package_id=source_package_id,
            datasheet_id=datasheet_id,
            datasheet_name=datasheet_names[datasheet_id],
        )
        if rule_ir.rule_id in seen_rule_ids:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR rule_ids must be unique within a source package."
            )
        seen_rule_ids.add(rule_ir.rule_id)
        rule_ir_by_source_row_id[source_row_id] = rule_ir
    if represented_datasheet_ids != set(datasheet_names):
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR declared datasheet inventory does not match its records."
        )
    if package_hash != descriptor.package_hash:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR source-package component package_hash does not match its "
            "registry pin (reviewed pin)."
        )
    return SourcePackageRuleIrArtifact(
        shard_id=shard_id,
        source_package_id=source_package_id,
        artifact_schema=artifact_schema,
        package_hash=package_hash,
        _payload=deepcopy(payload),
        _rule_ir_by_source_row_id=MappingProxyType(rule_ir_by_source_row_id),
        _datasheet_ids=tuple(sorted(datasheet_names)),
    )


def _validate_source_package_shape(
    payload: dict[str, object],
    *,
    descriptor: _SourcePackageDescriptor,
) -> None:
    try:
        msgspec.convert(payload, type=descriptor.wire_type, strict=True)
    except msgspec.ValidationError as exc:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR source-package component has an invalid typed shape."
        ) from exc


def _validate_source_package_provenance(payload: dict[str, object]) -> None:
    for field_name in (
        "source_snapshot_sha256",
        "source_artifact_hash",
        "datasheet_source_snapshot_sha256",
        "datasheet_source_artifact_hash",
        "source_pdf_sha256",
        "official_document_sha256",
        "overlay_package_hash",
        "review_manifest_sha256",
    ):
        if field_name in payload:
            _validate_sha256(field_name, payload[field_name])
    for field_name, suffix in (
        ("source_snapshot_filename", ".json"),
        ("datasheet_source_snapshot_filename", ".json"),
        ("source_pdf_filename", ".pdf"),
        ("official_document_filename", ".pdf"),
        ("review_manifest_filename", ".json"),
    ):
        if field_name in payload:
            _validate_provenance_filename(field_name, payload[field_name], suffix=suffix)
    if "source_page_numbers" in payload:
        _validate_page_numbers(
            "source_page_numbers",
            payload["source_page_numbers"],
            allow_empty=False,
        )
    if "official_document_pages" in payload:
        _validate_page_numbers(
            "official_document_pages",
            payload["official_document_pages"],
            allow_empty=True,
        )
    for field_name in ("review_row_id", "review_treatment"):
        if field_name in payload:
            _validate_non_empty_string(field_name, payload[field_name])

    datasheets_value = payload.get("datasheets")
    if type(datasheets_value) is not list:
        return
    for datasheet_value in cast(list[object], datasheets_value):
        if type(datasheet_value) is not dict:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR datasheet provenance row must be an object."
            )
        datasheet = cast(dict[str, object], datasheet_value)
        if "source_page_numbers" in datasheet:
            _validate_page_numbers(
                "source_page_numbers",
                datasheet["source_page_numbers"],
                allow_empty=False,
            )
        for field_name in ("review_row_id", "review_treatment"):
            if field_name in datasheet:
                _validate_non_empty_string(field_name, datasheet[field_name])
        if "pdf_page_reference" in datasheet and datasheet["pdf_page_reference"] is not None:
            _validate_non_empty_string("pdf_page_reference", datasheet["pdf_page_reference"])


def _validate_provenance_filename(field_name: str, value: object, *, suffix: str) -> str:
    filename = _validate_non_empty_string(field_name, value)
    if not filename.lower().endswith(suffix):
        raise FactionPackRuleIrRegistryError(
            f"Faction-pack RuleIR {field_name} must reference a {suffix} artifact."
        )
    return filename


def _validate_page_numbers(
    field_name: str,
    value: object,
    *,
    allow_empty: bool,
) -> tuple[int, ...]:
    if type(value) is not list:
        raise FactionPackRuleIrRegistryError(
            f"Faction-pack RuleIR {field_name} must be an array of page numbers."
        )
    pages = cast(list[object], value)
    if (not allow_empty and not pages) or any(type(page) is not int or page <= 0 for page in pages):
        raise FactionPackRuleIrRegistryError(
            f"Faction-pack RuleIR {field_name} must contain positive integer page numbers."
        )
    if pages != sorted(set(cast(list[int], pages))):
        raise FactionPackRuleIrRegistryError(
            f"Faction-pack RuleIR {field_name} must be sorted and unique."
        )
    return tuple(cast(list[int], pages))


def _validated_record_rule_ir(
    record: dict[str, object],
    *,
    source_row_id: str,
    source_package_id: str,
    datasheet_id: str,
    datasheet_name: str,
) -> RuleIR:
    allowed_fields = {
        "ability_name",
        "datasheet_id",
        "datasheet_name",
        "normalized_text_sha256",
        "rule_ir",
    }
    if not set(record).issubset(allowed_fields):
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR source-package record contains unsupported fields."
        )
    _required_non_empty_string(record, "ability_name")
    normalized_text_sha256 = _required_non_empty_string(record, "normalized_text_sha256")
    _validate_sha256("normalized_text_sha256", normalized_text_sha256)
    if "datasheet_id" in record:
        declared_datasheet_id = _required_non_empty_string(record, "datasheet_id")
        if declared_datasheet_id != datasheet_id:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR record datasheet_id does not match source_row_id."
            )
    if "datasheet_name" in record:
        declared_datasheet_name = _required_non_empty_string(record, "datasheet_name")
        if declared_datasheet_name != datasheet_name:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR record datasheet_name does not match its datasheet inventory."
            )
    rule_ir_value = record.get("rule_ir")
    if type(rule_ir_value) is not dict:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR record rule_ir must be an object."
        )
    rule_ir_payload = cast(dict[str, object], rule_ir_value)
    try:
        rule_ir = RuleIR.from_payload(cast(RuleIRPayload, rule_ir_payload))
    except (KeyError, RuleIRError, RuleTokenError, TypeError) as exc:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR record contains invalid RuleIR."
        ) from exc
    if cast(dict[str, object], rule_ir.to_payload()) != rule_ir_payload:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR record contains unsupported RuleIR fields."
        )
    expected_source_id = f"{source_package_id}:datasheet:{source_row_id}"
    if rule_ir.source_id != expected_source_id:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR record source identity does not match its source package."
        )
    if hashlib.sha256(rule_ir.normalized_text.encode()).hexdigest() != normalized_text_sha256:
        raise FactionPackRuleIrRegistryError("Faction-pack RuleIR normalized_text_sha256 is stale.")
    if (
        not rule_ir.is_supported
        or rule_ir.diagnostics
        or any(clause.diagnostics for clause in rule_ir.clauses)
    ):
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR records must be fully supported without diagnostics."
        )
    return rule_ir


def _datasheet_names_by_id(payload: dict[str, object]) -> dict[str, str]:
    has_single_datasheet = "datasheet_id" in payload
    has_datasheet_inventory = "datasheets" in payload
    if has_single_datasheet == has_datasheet_inventory:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR source package must declare one datasheet inventory shape."
        )
    if has_single_datasheet:
        datasheet_id = _required_non_empty_string(payload, "datasheet_id")
        datasheet_name = _required_non_empty_string(payload, "datasheet_name")
        return {datasheet_id: datasheet_name}

    datasheets_value = payload["datasheets"]
    if type(datasheets_value) is dict:
        datasheets = cast(dict[str, object], datasheets_value)
        if not datasheets:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR datasheet inventory must not be empty."
            )
        return {
            _validate_lookup_token("datasheet_id", datasheet_id): _validate_non_empty_string(
                "datasheet_name",
                datasheet_name,
            )
            for datasheet_id, datasheet_name in datasheets.items()
        }
    if type(datasheets_value) is not list or not datasheets_value:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR datasheets must be a non-empty object or array."
        )
    names_by_id: dict[str, str] = {}
    for datasheet_value in cast(list[object], datasheets_value):
        if type(datasheet_value) is not dict:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR datasheet inventory rows must be objects."
            )
        datasheet = cast(dict[str, object], datasheet_value)
        datasheet_id = _required_non_empty_string(datasheet, "datasheet_id")
        datasheet_name = _required_non_empty_string(datasheet, "datasheet_name")
        if datasheet_id in names_by_id:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR datasheet inventory IDs must be unique."
            )
        names_by_id[datasheet_id] = datasheet_name
    return names_by_id


def _datasheet_id_from_source_row_id(source_row_id: str) -> str:
    datasheet_id, separator, row_id = source_row_id.partition(":")
    if not separator or not datasheet_id or not row_id:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR source_row_id must be datasheet-qualified."
        )
    return datasheet_id


def _decode_wire[ArtifactT](
    raw: bytes,
    artifact_type: type[ArtifactT],
    *,
    artifact_description: str,
) -> ArtifactT:
    try:
        return msgspec.json.decode(raw, type=artifact_type)
    except msgspec.DecodeError as exc:
        raise FactionPackRuleIrRegistryError(
            f"Faction-pack RuleIR {artifact_description} is invalid."
        ) from exc


def _json_object_from_bytes(raw: bytes, *, artifact_description: str) -> dict[str, object]:
    if type(raw) is not bytes:
        raise FactionPackRuleIrRegistryError(
            f"Faction-pack RuleIR {artifact_description} bytes must be bytes."
        )
    try:
        decoded: object = json.loads(
            raw,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_non_finite_json_number,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FactionPackRuleIrRegistryError(
            f"Faction-pack RuleIR {artifact_description} is not valid JSON."
        ) from exc
    if type(decoded) is not dict:
        raise FactionPackRuleIrRegistryError(
            f"Faction-pack RuleIR {artifact_description} must be a JSON object."
        )
    return cast(dict[str, object], decoded)


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR JSON object keys must be unique."
            )
        payload[key] = value
    return payload


def _reject_non_finite_json_number(token: str) -> object:
    raise FactionPackRuleIrRegistryError(
        f"Faction-pack RuleIR JSON number must be finite, not {token}."
    )


def _validate_package_hash(
    payload: dict[str, object],
    *,
    artifact_description: str,
) -> None:
    package_hash = _required_non_empty_string(payload, "package_hash")
    _validate_sha256("package_hash", package_hash)
    if package_hash != canonical_package_hash(payload):
        raise FactionPackRuleIrRegistryError(
            f"Faction-pack RuleIR {artifact_description} package_hash is stale."
        )


def canonical_package_hash(payload: dict[str, object]) -> str:
    normalized = dict(payload)
    normalized["package_hash"] = ""
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_sorted_inventory(field_name: str, values: list[str]) -> tuple[str, ...]:
    if not values:
        raise FactionPackRuleIrRegistryError(
            f"Faction-pack RuleIR {field_name} inventory must not be empty."
        )
    validated = tuple(_validate_non_empty_string(field_name, value) for value in values)
    if validated != tuple(sorted(set(validated))):
        raise FactionPackRuleIrRegistryError(
            f"Faction-pack RuleIR {field_name} inventory must be sorted and unique."
        )
    return validated


def _validate_canonical_id(field_name: str, value: object) -> str:
    canonical_id = _validate_non_empty_string(field_name, value)
    if (
        canonical_id != canonical_id.lower()
        or canonical_id.startswith("-")
        or canonical_id.endswith("-")
        or any(
            character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in canonical_id
        )
    ):
        raise FactionPackRuleIrRegistryError(
            f"Faction-pack RuleIR {field_name} must be a normalized lowercase slug."
        )
    return canonical_id


def _required_non_empty_string(payload: dict[str, object], field_name: str) -> str:
    if field_name not in payload:
        raise FactionPackRuleIrRegistryError(
            f"Faction-pack RuleIR artifact is missing {field_name}."
        )
    return _validate_non_empty_string(field_name, payload[field_name])


def _validate_lookup_token(field_name: str, value: object) -> str:
    return _validate_non_empty_string(field_name, value)


def _validate_non_empty_string(field_name: str, value: object) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise FactionPackRuleIrRegistryError(
            f"Faction-pack RuleIR {field_name} must be non-empty trimmed text."
        )
    return value


def _validate_sha256(field_name: str, value: object) -> str:
    token = _validate_non_empty_string(field_name, value)
    if len(token) != 64 or any(character not in "0123456789abcdef" for character in token):
        raise FactionPackRuleIrRegistryError(
            f"Faction-pack RuleIR {field_name} must be lowercase SHA-256."
        )
    return token


__all__ = (
    "FACTION_PACK_RULE_IR_EDITION",
    "FACTION_PACK_RULE_IR_PACKAGE_ARTIFACT_SCHEMA",
    "FACTION_PACK_RULE_IR_REGISTRY_ID",
    "FACTION_PACK_RULE_IR_SHARD_ARTIFACT_SCHEMA",
    "DatasheetFactionIdsProvenance",
    "FactionPackRuleIrManifestArtifact",
    "FactionPackRuleIrRegistryError",
    "FactionPackRuleIrShardArtifact",
    "RuleIrShardArtifactReference",
    "SourcePackageRuleIrArtifact",
    "canonical_package_hash",
    "manifest_from_json_bytes",
    "shard_artifact_from_json_bytes",
)
