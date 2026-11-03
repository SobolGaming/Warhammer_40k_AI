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
    OverlaySourceArtifact,
    SourceOverlayError,
    SourceOverlayPack,
    SourceOverlayPackPayload,
    SourceReleaseManifest,
    apply_source_release_overlays,
)
from warhammer40k_core.rules.wahapedia_schema import WahapediaJsonArtifact

ARTIFACT_NAME = "wave_serpent_frame_2026_11.overlay-pack.json"


def overlay_pack() -> SourceOverlayPack:
    source_package()
    return overlay_pack_from_json_bytes(files(__package__).joinpath(ARTIFACT_NAME).read_bytes())


def overlay_pack_from_json_bytes(raw: bytes) -> SourceOverlayPack:
    if (
        hashlib.sha256(raw).hexdigest()
        != "0e1eefbb84497d8204f91e9add31c3e9ece010f6783000c30f6c26a0eaf2b66a"
    ):
        raise SourceOverlayError("Wave Serpent FRAME overlay drifted from reviewed pin.")
    try:
        payload = msgspec.json.decode(raw, type=SourceOverlayPackPayload)
    except msgspec.DecodeError as exc:
        raise SourceOverlayError("Wave Serpent FRAME overlay artifact is invalid.") from exc
    return SourceOverlayPack.from_payload(payload)


def source_release_manifest() -> SourceReleaseManifest:
    pack = overlay_pack()
    base_edition_suffix = "".join(("1", "0", "th"))
    return SourceReleaseManifest(
        release_id="wave-serpent-frame-source-release-2026-11",
        catalog_version=pack.catalog_version,
        base_source_package_id=pack.base_source_package_id,
        base_source_edition=f"warhammer-40000-{base_edition_suffix}",
        target_edition=pack.target_edition,
        overlay_package_ids=(pack.package_id,),
    )


AUDIT_ARTIFACT_NAME = "wave_serpent_frame_2026_11.audit.json"
AUDIT_SHA256 = "b4c1acebb902bac7811df028b8f107ed47e531ba8bf0e3e69fbb8b1e9f518e7d"
SOURCE_PACKAGE_NAME = "reviewed-wave-serpent-frame-observations-2026-11"


def source_audit_from_json_bytes(raw: bytes) -> FactionSourceAudit:
    if hashlib.sha256(raw).hexdigest() != AUDIT_SHA256:
        raise FactionSourceError("Wave Serpent FRAME audit bytes drifted from their reviewed pin.")
    return validate_faction_source_audit_bytes(raw)


@cache
def source_audit() -> FactionSourceAudit:
    return source_audit_from_json_bytes(
        files(__package__).joinpath(AUDIT_ARTIFACT_NAME).read_bytes()
    )


@cache
def source_package() -> RuleSourcePackage:
    return faction_source_package_from_audit(source_audit(), package_name=SOURCE_PACKAGE_NAME)


def apply_current_frame(
    artifacts: tuple[WahapediaJsonArtifact | OverlaySourceArtifact, ...],
) -> tuple[WahapediaJsonArtifact | OverlaySourceArtifact, ...]:
    """Admit the one reviewed addition, leaving all other source artifacts intact."""
    tables = tuple(a for a in artifacts if a.source_table == "Datasheets_keywords")
    if len(tables) != 1:
        raise SourceOverlayError("Wave Serpent FRAME requires one keyword predecessor table.")
    table = tables[0]
    if any(
        row.runtime_fields_payload()["datasheet_id"] == "000000599"
        and row.runtime_fields_payload()["keyword"].upper() == "FRAME"
        for row in table.rows
    ):
        raise SourceOverlayError("Wave Serpent FRAME requires keyword absence.")
    if table.artifact_hash() != "57547424449eddebc6e565d253ade49d21a54090d89cbcd087bf1652fc9fead6":
        raise SourceOverlayError("Wave Serpent FRAME keyword predecessor drifted.")
    (current,) = apply_source_release_overlays(
        source_artifacts=(table,),
        release_manifest=source_release_manifest(),
        overlay_packs=(overlay_pack(),),
    )
    return tuple(current if a is table else a for a in artifacts)
