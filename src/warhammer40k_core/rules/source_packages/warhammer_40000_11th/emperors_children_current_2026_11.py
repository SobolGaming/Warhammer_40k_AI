from __future__ import annotations

from importlib.resources import files

import msgspec

from warhammer40k_core.rules.source_overlay import (
    SourceOverlayError,
    SourceOverlayPack,
    SourceOverlayPackPayload,
    SourceReleaseManifest,
)

ARTIFACT_NAME = "emperors_children_current_2026_11.overlay-pack.json"


def overlay_pack() -> SourceOverlayPack:
    return overlay_pack_from_json_bytes(files(__package__).joinpath(ARTIFACT_NAME).read_bytes())


def overlay_pack_from_json_bytes(raw: bytes) -> SourceOverlayPack:
    try:
        payload = msgspec.json.decode(raw, type=SourceOverlayPackPayload)
    except msgspec.DecodeError as exc:
        raise SourceOverlayError(
            "Emperor's Children current-source overlay artifact is invalid."
        ) from exc
    return SourceOverlayPack.from_payload(payload)


def source_release_manifest() -> SourceReleaseManifest:
    pack = overlay_pack()
    base_edition_suffix = "".join(("1", "0", "th"))
    return SourceReleaseManifest(
        release_id="emperors-children-current-source-release-2026-11",
        catalog_version=pack.catalog_version,
        base_source_package_id=pack.base_source_package_id,
        base_source_edition=f"warhammer-40000-{base_edition_suffix}",
        target_edition=pack.target_edition,
        overlay_package_ids=(pack.package_id,),
    )
