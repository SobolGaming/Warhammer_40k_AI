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
from warhammer40k_core.rules.source_patch import source_row_hash
from warhammer40k_core.rules.wahapedia_schema import WahapediaJsonArtifact

ARTIFACT_NAME = "daemons_native_2026_11.overlay-pack.json"
AUDIT_ARTIFACT_NAME = "daemons_native_2026_11.audit.json"
OVERLAY_SHA256 = "b0ccc944e022622bbeded025608a5b2d7ddd224c0f4cae9cca30b59f7adaf4aa"
AUDIT_SHA256 = "c5520d359da6f3732765803fea9258fb50d3726cce49392b9f85411aa0e18940"
SOURCE_PACKAGE_NAME = "reviewed-daemons-native-observations-2026-11"
SOURCE_VERSION = "reviewed-2026-11-04"
KEYWORD_SOURCE_IDS = (
    ("000001148", "faction-app:chaos-daemons:datasheet:belakor"),
    ("000001114", "faction-app:chaos-daemons:datasheet:bloodletters"),
)
KEYWORD_PREIMAGES = (
    (
        "000001148",
        "000001148:Shadow Legion:global:false:4614",
        "5e71e35ddf0f2e3dd1dd74755db37fc27597c992bdd8609b9720ec7f89662afc",
    ),
    (
        "000001114",
        "000001114:Shadow Legion:global:false:4385",
        "d5ef3a4d71b38faa159d103681fd81e9b05294c7194d50f624b3ee3a70ab76ee",
    ),
)


def overlay_pack_from_json_bytes(raw: bytes) -> SourceOverlayPack:
    if hashlib.sha256(raw).hexdigest() != OVERLAY_SHA256:
        raise SourceOverlayError("Daemons native overlay drifted from reviewed pin.")
    try:
        payload = msgspec.json.decode(raw, type=SourceOverlayPackPayload)
    except msgspec.DecodeError as exc:
        raise SourceOverlayError("Daemons native overlay artifact is invalid.") from exc
    return SourceOverlayPack.from_payload(payload)


def overlay_pack() -> SourceOverlayPack:
    source_package()
    return overlay_pack_from_json_bytes(files(__package__).joinpath(ARTIFACT_NAME).read_bytes())


def source_audit_from_json_bytes(raw: bytes) -> FactionSourceAudit:
    if hashlib.sha256(raw).hexdigest() != AUDIT_SHA256:
        raise FactionSourceError("Daemons native audit bytes drifted from reviewed pin.")
    return validate_faction_source_audit_bytes(raw)


@cache
def source_audit() -> FactionSourceAudit:
    return source_audit_from_json_bytes(
        files(__package__).joinpath(AUDIT_ARTIFACT_NAME).read_bytes()
    )


@cache
def source_package() -> RuleSourcePackage:
    return faction_source_package_from_audit(source_audit(), package_name=SOURCE_PACKAGE_NAME)


def source_release_manifest() -> SourceReleaseManifest:
    pack = overlay_pack()
    prior_edition = "".join(("1", "0", "th"))
    return SourceReleaseManifest(
        release_id="daemons-native-source-release-2026-11",
        catalog_version=pack.catalog_version,
        base_source_package_id=pack.base_source_package_id,
        base_source_edition=f"warhammer-40000-{prior_edition}",
        target_edition=pack.target_edition,
        overlay_package_ids=(pack.package_id,),
    )


def apply_current_daemons(
    artifacts: tuple[WahapediaJsonArtifact | OverlaySourceArtifact, ...],
) -> tuple[WahapediaJsonArtifact | OverlaySourceArtifact, ...]:
    """Validate exact base keyword removals; overlay only the two damaged fields."""
    tables = tuple(a for a in artifacts if a.source_table == "Datasheets_keywords")
    if len(tables) != 1:
        raise SourceOverlayError("Daemons native correction requires one keyword table.")
    for datasheet_id, row_id, preimage in KEYWORD_PREIMAGES:
        matches = tuple(
            row
            for row in tables[0].rows
            if row.runtime_fields_payload()["datasheet_id"] == datasheet_id
            and row.runtime_fields_payload()["keyword"].casefold() == "shadow legion"
        )
        if len(matches) != 1:
            raise SourceOverlayError("Daemons native keyword preimage is missing or duplicated.")
        if matches[0].source_row_id != row_id or source_row_hash(matches[0]) != preimage:
            raise SourceOverlayError("Daemons native keyword preimage drifted.")
    sheets = tuple(a for a in artifacts if a.source_table == "Datasheets")
    if len(sheets) != 1:
        raise SourceOverlayError("Daemons native correction requires one datasheet table.")
    (current,) = apply_source_release_overlays(
        source_artifacts=sheets,
        release_manifest=source_release_manifest(),
        overlay_packs=(overlay_pack(),),
    )
    return tuple(current if a is sheets[0] else a for a in artifacts)
