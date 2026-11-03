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

ARTIFACT_NAME = "starfang_keyword_2026_11.overlay-pack.json"


def overlay_pack() -> SourceOverlayPack:
    source_package()
    return overlay_pack_from_json_bytes(files(__package__).joinpath(ARTIFACT_NAME).read_bytes())


def overlay_pack_from_json_bytes(raw: bytes) -> SourceOverlayPack:
    if (
        hashlib.sha256(raw).hexdigest()
        != "477ce675ddebbf0f86ea4478a3b4ebf0656b59b9cbfe0e0e1b693406c5c16c78"
    ):
        raise SourceOverlayError("Starfang keyword overlay drifted from reviewed pin.")
    try:
        payload = msgspec.json.decode(raw, type=SourceOverlayPackPayload)
    except msgspec.DecodeError as exc:
        raise SourceOverlayError("Starfang keyword overlay artifact is invalid.") from exc
    return SourceOverlayPack.from_payload(payload)


def source_release_manifest() -> SourceReleaseManifest:
    pack = overlay_pack()
    base_edition_suffix = "".join(("1", "0", "th"))
    return SourceReleaseManifest(
        release_id="starfang-keyword-source-release-2026-11",
        catalog_version=pack.catalog_version,
        base_source_package_id=pack.base_source_package_id,
        base_source_edition=f"warhammer-40000-{base_edition_suffix}",
        target_edition=pack.target_edition,
        overlay_package_ids=(pack.package_id,),
    )


AUDIT_ARTIFACT_NAME = "starfang_keyword_2026_11.audit.json"
AUDIT_SHA256 = "6c003c857a8bba59ad8fb6b369208800bc8e5271ea858560df7532b32bb493df"
SOURCE_PACKAGE_NAME = "reviewed-starfang-keyword-observations-2026-11"


def source_audit_from_json_bytes(raw: bytes) -> FactionSourceAudit:
    if hashlib.sha256(raw).hexdigest() != AUDIT_SHA256:
        raise FactionSourceError("Starfang keyword audit bytes drifted from their reviewed pin.")
    return validate_faction_source_audit_bytes(raw)


@cache
def source_audit() -> FactionSourceAudit:
    return source_audit_from_json_bytes(
        files(__package__).joinpath(AUDIT_ARTIFACT_NAME).read_bytes()
    )


@cache
def source_package() -> RuleSourcePackage:
    return faction_source_package_from_audit(source_audit(), package_name=SOURCE_PACKAGE_NAME)
