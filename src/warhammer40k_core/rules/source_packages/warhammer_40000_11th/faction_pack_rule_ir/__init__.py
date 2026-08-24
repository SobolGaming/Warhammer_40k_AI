from __future__ import annotations

import hashlib
from collections.abc import Mapping
from types import MappingProxyType
from typing import Final

from warhammer40k_core.rules.rule_ir import RuleIRPayload
from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

from ._artifacts import (
    FACTION_PACK_RULE_IR_EDITION,
    FACTION_PACK_RULE_IR_PACKAGE_ARTIFACT_SCHEMA,
    FACTION_PACK_RULE_IR_REGISTRY_ID,
    FACTION_PACK_RULE_IR_SHARD_ARTIFACT_SCHEMA,
    FactionPackRuleIrManifestArtifact,
    FactionPackRuleIrRegistryError,
    FactionPackRuleIrShardArtifact,
    SourcePackageRuleIrArtifact,
    canonical_package_hash,
    manifest_from_json_bytes,
    shard_artifact_from_json_bytes,
)

_ARTIFACT_ROOT: Final = "artifacts"
_MANIFEST_PATH: Final = f"{_ARTIFACT_ROOT}/package.json"

EXPECTED_PACKAGE_HASH: Final = "a310b4bb595385a277cdcc11752108a1dd33e69a49f29f92aaed845a8b643c3c"


def _artifact_bytes(relative_path: str) -> bytes:
    try:
        return package_artifact_bytes(__name__, f"{_ARTIFACT_ROOT}/{relative_path}")
    except SourcePackageArtifactError as exc:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR generated data artifact could not be loaded."
        ) from exc


def _manifest_bytes() -> bytes:
    try:
        return package_artifact_bytes(__name__, _MANIFEST_PATH)
    except SourcePackageArtifactError as exc:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR generated data package manifest could not be loaded."
        ) from exc


def _load_shard_artifacts(
    manifest: FactionPackRuleIrManifestArtifact,
    *,
    shard_bytes_by_path: Mapping[str, bytes],
) -> Mapping[str, FactionPackRuleIrShardArtifact]:
    artifacts: dict[str, FactionPackRuleIrShardArtifact] = {}
    seen_source_package_ids: set[str] = set()
    seen_source_row_ids: set[str] = set()
    for shard_id, reference in manifest.shard_artifacts.items():
        raw = shard_bytes_by_path[reference.path]
        if hashlib.sha256(raw).hexdigest() != reference.sha256:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR shard artifact SHA-256 drifted from its manifest pin."
            )
        artifact = shard_artifact_from_json_bytes(raw)
        if artifact.shard_id != shard_id:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR shard artifact does not match its manifest key."
            )
        if artifact.supported_source_package_ids() != reference.source_package_ids:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR source-package inventory drifted from its manifest pin."
            )
        if artifact.supported_datasheet_ids() != reference.datasheet_ids:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR datasheet inventory drifted from its manifest pin."
            )
        if artifact.supported_datasheet_source_row_ids() != reference.source_row_ids:
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR source-row inventory drifted from its manifest pin."
            )
        if seen_source_package_ids.intersection(reference.source_package_ids):
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR source_package_ids must be globally unique."
            )
        if seen_source_row_ids.intersection(reference.source_row_ids):
            raise FactionPackRuleIrRegistryError(
                "Faction-pack RuleIR source_row_ids must be globally unique."
            )
        seen_source_package_ids.update(reference.source_package_ids)
        seen_source_row_ids.update(reference.source_row_ids)
        artifacts[shard_id] = artifact
    return MappingProxyType(artifacts)


def _validated_registry_artifact_set(
    *,
    manifest: FactionPackRuleIrManifestArtifact,
    shard_bytes_by_path: Mapping[str, bytes],
    expected_package_hash: str,
) -> tuple[
    Mapping[str, FactionPackRuleIrShardArtifact],
    tuple[
        Mapping[str, SourcePackageRuleIrArtifact],
        Mapping[str, SourcePackageRuleIrArtifact],
        Mapping[str, tuple[str, ...]],
        Mapping[str, str],
    ],
]:
    if manifest.package_hash != expected_package_hash:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR package manifest hash drifted from its reviewed pin."
        )
    expected_shard_paths = {reference.path for reference in manifest.shard_artifacts.values()}
    if set(shard_bytes_by_path) != expected_shard_paths:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR shard bytes must exactly match the manifest paths."
        )
    shard_artifacts = _load_shard_artifacts(
        manifest,
        shard_bytes_by_path=shard_bytes_by_path,
    )
    return shard_artifacts, _source_package_indexes(shard_artifacts)


def validate_package_artifact_set(
    *,
    manifest_bytes: bytes,
    shard_bytes_by_path: Mapping[str, bytes],
    expected_package_hash: str,
) -> None:
    """Apply the real registry loader contract to one complete artifact byte set."""
    manifest = manifest_from_json_bytes(manifest_bytes)
    _validated_registry_artifact_set(
        manifest=manifest,
        shard_bytes_by_path=shard_bytes_by_path,
        expected_package_hash=expected_package_hash,
    )


def _source_package_indexes(
    shard_artifacts: Mapping[str, FactionPackRuleIrShardArtifact],
) -> tuple[
    Mapping[str, SourcePackageRuleIrArtifact],
    Mapping[str, SourcePackageRuleIrArtifact],
    Mapping[str, tuple[str, ...]],
    Mapping[str, str],
]:
    by_source_package_id: dict[str, SourcePackageRuleIrArtifact] = {}
    by_source_row_id: dict[str, SourcePackageRuleIrArtifact] = {}
    source_package_ids_by_datasheet_id: dict[str, list[str]] = {}
    faction_id_by_datasheet_id: dict[str, str] = {}
    seen_rule_ids: set[str] = set()
    for shard_artifact in shard_artifacts.values():
        for datasheet_id, faction_id in shard_artifact.datasheet_faction_ids.items():
            existing_faction_id = faction_id_by_datasheet_id.get(datasheet_id)
            if existing_faction_id is not None and existing_faction_id != faction_id:
                raise FactionPackRuleIrRegistryError(
                    "Faction-pack RuleIR datasheet faction identity conflicts across shards."
                )
            faction_id_by_datasheet_id[datasheet_id] = faction_id
        for source_package_id, source_package in shard_artifact.source_packages.items():
            if source_package_id in by_source_package_id:
                raise FactionPackRuleIrRegistryError(
                    "Faction-pack RuleIR source_package_ids must be globally unique."
                )
            by_source_package_id[source_package_id] = source_package
            for datasheet_id in source_package.supported_datasheet_ids():
                source_package_ids_by_datasheet_id.setdefault(datasheet_id, []).append(
                    source_package_id
                )
            for source_row_id in source_package.supported_datasheet_source_row_ids():
                if source_row_id in by_source_row_id:
                    raise FactionPackRuleIrRegistryError(
                        "Faction-pack RuleIR source_row_ids must be globally unique."
                    )
                rule_ir_payload = source_package.datasheet_rule_ir_payload_by_source_row_id(
                    source_row_id
                )
                if rule_ir_payload is None:
                    raise FactionPackRuleIrRegistryError(
                        "Faction-pack RuleIR source-row inventory could not resolve its payload."
                    )
                rule_id = rule_ir_payload["rule_id"]
                if rule_id in seen_rule_ids:
                    raise FactionPackRuleIrRegistryError(
                        "Faction-pack RuleIR rule_ids must be globally unique."
                    )
                seen_rule_ids.add(rule_id)
                by_source_row_id[source_row_id] = source_package
    return (
        MappingProxyType(by_source_package_id),
        MappingProxyType(by_source_row_id),
        MappingProxyType(
            {
                datasheet_id: tuple(sorted(source_package_ids))
                for datasheet_id, source_package_ids in source_package_ids_by_datasheet_id.items()
            }
        ),
        MappingProxyType(faction_id_by_datasheet_id),
    )


def _load_registry_artifact_set() -> tuple[
    FactionPackRuleIrManifestArtifact,
    Mapping[str, FactionPackRuleIrShardArtifact],
    tuple[
        Mapping[str, SourcePackageRuleIrArtifact],
        Mapping[str, SourcePackageRuleIrArtifact],
        Mapping[str, tuple[str, ...]],
        Mapping[str, str],
    ],
]:
    manifest = manifest_from_json_bytes(_manifest_bytes())
    shard_artifacts, indexes = _validated_registry_artifact_set(
        manifest=manifest,
        shard_bytes_by_path={
            reference.path: _artifact_bytes(reference.path)
            for reference in manifest.shard_artifacts.values()
        },
        expected_package_hash=EXPECTED_PACKAGE_HASH,
    )
    return manifest, shard_artifacts, indexes


_MANIFEST, _SHARD_ARTIFACTS, _SOURCE_PACKAGE_INDEXES = _load_registry_artifact_set()
(
    _SOURCE_PACKAGE_BY_ID,
    _SOURCE_PACKAGE_BY_SOURCE_ROW_ID,
    _SOURCE_PACKAGE_IDS_BY_DATASHEET_ID,
    _FACTION_ID_BY_DATASHEET_ID,
) = _SOURCE_PACKAGE_INDEXES

ARTIFACT_SCHEMA: Final = FACTION_PACK_RULE_IR_PACKAGE_ARTIFACT_SCHEMA
SHARD_ARTIFACT_SCHEMA: Final = FACTION_PACK_RULE_IR_SHARD_ARTIFACT_SCHEMA
EDITION: Final = FACTION_PACK_RULE_IR_EDITION
REGISTRY_ID: Final = FACTION_PACK_RULE_IR_REGISTRY_ID
PACKAGE_HASH: Final = _MANIFEST.package_hash

_ALL_DATASHEET_IDS: Final = tuple(sorted(_SOURCE_PACKAGE_IDS_BY_DATASHEET_ID))
_ALL_SOURCE_PACKAGE_IDS: Final = tuple(sorted(_SOURCE_PACKAGE_BY_ID))
_ALL_SOURCE_ROW_IDS: Final = tuple(sorted(_SOURCE_PACKAGE_BY_SOURCE_ROW_ID))
_DATASHEET_IDS_BY_FACTION_ID: Final = MappingProxyType(
    {
        faction_id: tuple(
            sorted(
                datasheet_id
                for datasheet_id, candidate_faction_id in _FACTION_ID_BY_DATASHEET_ID.items()
                if candidate_faction_id == faction_id
            )
        )
        for faction_id in sorted(set(_FACTION_ID_BY_DATASHEET_ID.values()))
    }
)


def supported_faction_ids() -> tuple[str, ...]:
    return tuple(_DATASHEET_IDS_BY_FACTION_ID)


def supported_shard_ids() -> tuple[str, ...]:
    return tuple(_SHARD_ARTIFACTS)


def supported_source_package_ids(shard_id: str | None = None) -> tuple[str, ...]:
    if shard_id is None:
        return _ALL_SOURCE_PACKAGE_IDS
    return _shard_artifact(shard_id).supported_source_package_ids()


def supported_datasheet_ids(faction_id: str | None = None) -> tuple[str, ...]:
    if faction_id is None:
        return _ALL_DATASHEET_IDS
    _validate_lookup_token("faction_id", faction_id)
    datasheet_ids = _DATASHEET_IDS_BY_FACTION_ID.get(faction_id)
    if datasheet_ids is None:
        raise FactionPackRuleIrRegistryError("Faction-pack RuleIR faction_id is not registered.")
    return datasheet_ids


def supported_datasheet_ids_by_shard_id(shard_id: str) -> tuple[str, ...]:
    return _shard_artifact(shard_id).supported_datasheet_ids()


def supported_datasheet_source_row_ids(shard_id: str | None = None) -> tuple[str, ...]:
    if shard_id is None:
        return _ALL_SOURCE_ROW_IDS
    return _shard_artifact(shard_id).supported_datasheet_source_row_ids()


def source_faction_id_by_datasheet_id(datasheet_id: str) -> str | None:
    _validate_lookup_token("datasheet_id", datasheet_id)
    return _FACTION_ID_BY_DATASHEET_ID.get(datasheet_id)


def source_package_ids_by_datasheet_id(datasheet_id: str) -> tuple[str, ...]:
    _validate_lookup_token("datasheet_id", datasheet_id)
    return _SOURCE_PACKAGE_IDS_BY_DATASHEET_ID.get(datasheet_id, ())


def source_package_artifact(source_package_id: str) -> SourcePackageRuleIrArtifact:
    _validate_lookup_token("source_package_id", source_package_id)
    artifact = _SOURCE_PACKAGE_BY_ID.get(source_package_id)
    if artifact is None:
        raise FactionPackRuleIrRegistryError(
            "Faction-pack RuleIR source_package_id is not registered."
        )
    return artifact


def source_package_payload(source_package_id: str) -> dict[str, object]:
    return source_package_artifact(source_package_id).payload()


def datasheet_rule_ir_payload_by_source_row_id(source_row_id: str) -> RuleIRPayload | None:
    _validate_lookup_token("source_row_id", source_row_id)
    source_package = _SOURCE_PACKAGE_BY_SOURCE_ROW_ID.get(source_row_id)
    if source_package is None:
        return None
    return source_package.datasheet_rule_ir_payload_by_source_row_id(source_row_id)


def payload_by_source_row_id(source_row_id: str) -> RuleIRPayload | None:
    return datasheet_rule_ir_payload_by_source_row_id(source_row_id)


def _shard_artifact(shard_id: str) -> FactionPackRuleIrShardArtifact:
    _validate_lookup_token("shard_id", shard_id)
    artifact = _SHARD_ARTIFACTS.get(shard_id)
    if artifact is None:
        raise FactionPackRuleIrRegistryError("Faction-pack RuleIR shard_id is not registered.")
    return artifact


def _validate_lookup_token(field_name: str, value: object) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise FactionPackRuleIrRegistryError(
            f"Faction-pack RuleIR {field_name} must be non-empty trimmed text."
        )
    return value


__all__ = (
    "ARTIFACT_SCHEMA",
    "EDITION",
    "EXPECTED_PACKAGE_HASH",
    "PACKAGE_HASH",
    "REGISTRY_ID",
    "SHARD_ARTIFACT_SCHEMA",
    "FactionPackRuleIrRegistryError",
    "SourcePackageRuleIrArtifact",
    "canonical_package_hash",
    "datasheet_rule_ir_payload_by_source_row_id",
    "manifest_from_json_bytes",
    "payload_by_source_row_id",
    "shard_artifact_from_json_bytes",
    "source_faction_id_by_datasheet_id",
    "source_package_artifact",
    "source_package_ids_by_datasheet_id",
    "source_package_payload",
    "supported_datasheet_ids",
    "supported_datasheet_ids_by_shard_id",
    "supported_datasheet_source_row_ids",
    "supported_faction_ids",
    "supported_shard_ids",
    "supported_source_package_ids",
    "validate_package_artifact_set",
)
