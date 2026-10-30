from __future__ import annotations

from typing import Final

from warhammer40k_core.rules.mfm_source import (
    MfmFactionRecord,
    MfmSourceError,
    MfmSourcePackage,
    MfmSourcePackagePayload,
)
from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

from ._artifacts import (
    MfmPackageArtifact,
    mfm_faction_payload_from_json_bytes,
    mfm_package_artifact_from_json_bytes,
)

_ARTIFACT_ROOT: Final = "artifacts"


def _load_manifest() -> MfmPackageArtifact:
    try:
        return mfm_package_artifact_from_json_bytes(
            package_artifact_bytes(__name__, f"{_ARTIFACT_ROOT}/package.json")
        )
    except SourcePackageArtifactError as exc:
        raise MfmSourceError("MFM generated data package manifest could not be loaded.") from exc


_MANIFEST: Final = _load_manifest()

SOURCE_PACKAGE_ID: Final = _MANIFEST.source_package_id
SOURCE_TITLE: Final = _MANIFEST.source_title
SOURCE_VERSION: Final = _MANIFEST.source_version
SOURCE_DATE: Final = _MANIFEST.source_date
SOURCE_URL: Final = _MANIFEST.source_url
SOURCE_PAYLOAD_CHECKSUM_SHA256: Final = _MANIFEST.source_payload_checksum_sha256
EXCLUDED_FACTION_IDS: Final = tuple(_MANIFEST.excluded_faction_ids)
_FACTION_ARTIFACTS: Final = _MANIFEST.faction_artifacts

_FACTION_CACHE: dict[str, MfmFactionRecord] = {}
_source_package_cache: MfmSourcePackage | None = None


def supported_faction_ids() -> tuple[str, ...]:
    return tuple(sorted(_FACTION_ARTIFACTS))


def faction_record(faction_id: str) -> MfmFactionRecord:
    cached = _FACTION_CACHE.get(faction_id)
    if cached is not None:
        return cached
    artifact_path = _FACTION_ARTIFACTS.get(faction_id)
    if artifact_path is None:
        raise MfmSourceError("MFM faction_id was not found in generated package.")
    raw_artifact = _artifact_bytes(artifact_path)
    record = MfmFactionRecord.from_payload(mfm_faction_payload_from_json_bytes(raw_artifact))
    if record.faction_id != faction_id:
        raise MfmSourceError("MFM faction artifact payload does not match requested faction_id.")
    _FACTION_CACHE[faction_id] = record
    return record


def source_package() -> MfmSourcePackage:
    global _source_package_cache
    if _source_package_cache is None:
        _source_package_cache = MfmSourcePackage.from_payload(_source_package_payload())
    return _source_package_cache


def _source_package_payload() -> MfmSourcePackagePayload:
    return {
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_title": SOURCE_TITLE,
        "source_version": SOURCE_VERSION,
        "source_date": SOURCE_DATE,
        "source_url": SOURCE_URL,
        "excluded_faction_ids": list(EXCLUDED_FACTION_IDS),
        "factions": [
            faction_record(faction_id).to_payload() for faction_id in supported_faction_ids()
        ],
        "source_payload_checksum_sha256": SOURCE_PAYLOAD_CHECKSUM_SHA256,
    }


def _artifact_bytes(relative_path: str) -> bytes:
    try:
        return package_artifact_bytes(__name__, f"{_ARTIFACT_ROOT}/{relative_path}")
    except SourcePackageArtifactError as exc:
        raise MfmSourceError("MFM generated data artifact could not be loaded.") from exc
