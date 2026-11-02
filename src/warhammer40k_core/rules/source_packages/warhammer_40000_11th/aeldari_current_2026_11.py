from __future__ import annotations

import hashlib
from functools import cache
from importlib.resources import files

import msgspec

from warhammer40k_core.rules.faction_source_governance import (
    FactionSourceAudit,
    FactionSourceError,
    validate_faction_source_audit_bytes,
)
from warhammer40k_core.rules.faction_source_package import faction_source_package_from_audit
from warhammer40k_core.rules.source_evidence import RuleSourcePackage
from warhammer40k_core.rules.source_overlay import (
    SourceOverlayError,
    SourceOverlayPack,
    SourceOverlayPackPayload,
    SourceReleaseManifest,
)

ARTIFACT_NAME = "aeldari_current_2026_11.overlay-pack.json"


def overlay_pack() -> SourceOverlayPack:
    source_package()
    return overlay_pack_from_json_bytes(files(__package__).joinpath(ARTIFACT_NAME).read_bytes())


def overlay_pack_from_json_bytes(raw: bytes) -> SourceOverlayPack:
    try:
        payload = msgspec.json.decode(raw, type=SourceOverlayPackPayload)
    except msgspec.DecodeError as exc:
        raise SourceOverlayError("Aeldari current-source overlay artifact is invalid.") from exc
    return SourceOverlayPack.from_payload(payload)


def source_release_manifest() -> SourceReleaseManifest:
    pack = overlay_pack()
    base_edition_suffix = "".join(("1", "0", "th"))
    return SourceReleaseManifest(
        release_id="aeldari-current-source-release-2026-11",
        catalog_version=pack.catalog_version,
        base_source_package_id=pack.base_source_package_id,
        base_source_edition=f"warhammer-40000-{base_edition_suffix}",
        target_edition=pack.target_edition,
        overlay_package_ids=(pack.package_id,),
    )


AUDIT_ARTIFACT_NAME = "aeldari_current_2026_11.audit.json"
AUDIT_SHA256 = "07f9881e6bca01f4b477cea4bce7eb3b4019e283acbbb9ef0de405513ba766dc"
SOURCE_PACKAGE_NAME = "reviewed-aeldari-app-observations-2026-11"


def source_audit_from_json_bytes(raw: bytes) -> FactionSourceAudit:
    if hashlib.sha256(raw).hexdigest() != AUDIT_SHA256:
        raise FactionSourceError("Aeldari source audit bytes drifted from their reviewed pin.")
    return validate_faction_source_audit_bytes(raw)


@cache
def source_audit() -> FactionSourceAudit:
    return source_audit_from_json_bytes(
        files(__package__).joinpath(AUDIT_ARTIFACT_NAME).read_bytes()
    )


@cache
def source_package() -> RuleSourcePackage:
    return faction_source_package_from_audit(source_audit(), package_name=SOURCE_PACKAGE_NAME)
