from __future__ import annotations

from datetime import date

from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_overlay import (
    SourceOverlayOperation,
    SourceOverlayOperationKind,
    SourceOverlayPack,
    SourceReleaseManifest,
)

BASE_EDITION_SUFFIX = "".join(("1", "0", "th"))
BASE_SOURCE_PACKAGE_ID = DataPackageId(
    namespace="wahapedia",
    package_name="source-mirror",
    version=f"{BASE_EDITION_SUFFIX}-edition-2026-06-14",
)
OVERLAY_PACKAGE_ID = DataPackageId(
    namespace="gw",
    package_name="emperors-children-datasheet-overlay",
    version="11th-2026-06-10",
)
CATALOG_VERSION = CatalogVersion.dated(
    version_id="warhammer-40000-11th-emperors-children-datasheet-overlay",
    source_date=date(2026, 6, 10),
)
SOURCE_REFERENCE = "gw-11e-emperors-children-faction-pack-2026-06:datasheets"
SOURCE_DATE = "2026-06-10"
TARGET_EDITION = "warhammer-40000-11th"

SCUTTLING_HORRORS_DESCRIPTION = (
    "In your opponent's Movement phase, if an enemy unit ends a move within 8\" of this "
    "unit, if this unit is not within Engagement Range of one or more enemy units, this "
    'unit can make a Normal move of up to 6".'
)
LETHAL_OBSESSION_DESCRIPTION = (
    "In your Shooting phase, after this unit has shot, you can use this ability. If you "
    "do, select one enemy unit hit by those ranged attacks. Until the end of the turn, "
    "when this unit declares a charge:\n"
    "- This unit can re-roll that charge roll.\n"
    "- This unit must end that charge move engaged with that enemy unit."
)
SERPENTINE_DESCRIPTION = (
    "Each time this model makes a Normal, Advance or Fall Back move, it can move over "
    'sections of terrain features that are 4" or less in height.'
)


def source_release_manifest() -> SourceReleaseManifest:
    return SourceReleaseManifest(
        release_id="emperors-children-11e-datasheet-overlay-2026-06",
        catalog_version=CATALOG_VERSION,
        base_source_package_id=BASE_SOURCE_PACKAGE_ID,
        base_source_edition=f"warhammer-40000-{BASE_EDITION_SUFFIX}",
        target_edition=TARGET_EDITION,
        overlay_package_ids=(OVERLAY_PACKAGE_ID,),
    )


def overlay_pack() -> SourceOverlayPack:
    return SourceOverlayPack(
        package_id=OVERLAY_PACKAGE_ID,
        catalog_version=CATALOG_VERSION,
        base_source_package_id=BASE_SOURCE_PACKAGE_ID,
        target_edition=TARGET_EDITION,
        effective_date=SOURCE_DATE,
        operations=_operations(),
    )


def source_package_identity_payload() -> dict[str, str]:
    package = overlay_pack()
    return {
        "source_package_id": OVERLAY_PACKAGE_ID.stable_identity(),
        "source_payload_checksum_sha256": package.package_hash(),
        "source_date": SOURCE_DATE,
        "source_edition": TARGET_EDITION,
    }


def _operations() -> tuple[SourceOverlayOperation, ...]:
    return (
        _update_row(
            op_id="ec-chaos-spawn-scuttling-horrors",
            order_index=10,
            source_table="Datasheets_abilities",
            source_row_id="000004090:3",
            expected_preimage_hash="135a09ec959165ea2ebb0a2d056c9b801dadc5397cc260a03b4f3fa78919a99f",
            fields=(("description", SCUTTLING_HORRORS_DESCRIPTION),),
        ),
        _update_row(
            op_id="ec-chaos-terminators-lethal-obsession",
            order_index=20,
            source_table="Datasheets_abilities",
            source_row_id="000004081:3",
            expected_preimage_hash="d0ab5fa66840b31d6c7a8b2c4fedbb7bcf5a55667c99513463c83a61ee0eff25",
            fields=(("description", LETHAL_OBSESSION_DESCRIPTION),),
        ),
        _update_row(
            op_id="ec-fulgrim-serpentine",
            order_index=30,
            source_table="Datasheets_abilities",
            source_row_id="000004077:6",
            expected_preimage_hash="d8ea1ab6f6cb8dee2cf190bbab5878dd8c0d9b2a111b7e224eac1c87d10351bf",
            fields=(("description", SERPENTINE_DESCRIPTION),),
        ),
        _update_row(
            op_id="ec-heldrake-profile",
            order_index=40,
            source_table="Datasheets_models",
            source_row_id="000004092:1",
            expected_preimage_hash="b325fc0131495cf2dd5dfeb0fa9cb557f9e2544a011deb1ab36bdde131b94b84",
            fields=(("M", '12"'), ("Sv", "3+"), ("OC", "-")),
        ),
        _update_row(
            op_id="ec-flawless-blades-blissblade-attacks",
            order_index=50,
            source_table="Datasheets_wargear",
            source_row_id="000004089:2:1:8694",
            expected_preimage_hash="3e56c99479338cda1dcc3f15d1a2074efb6595d830cef2acf2590742e60b339b",
            fields=(("A", "4"),),
        ),
        _update_row(
            op_id="ec-tormentors-power-sword-strength",
            order_index=60,
            source_table="Datasheets_wargear",
            source_row_id="000004079:9:1:8650",
            expected_preimage_hash="e236e5e5d5b0518daa4f137d796d42e42c19b95408f223230c939c4ed866ed89",
            fields=(("S", "5"),),
        ),
        _update_row(
            op_id="ec-infractors-power-sword-strength",
            order_index=70,
            source_table="Datasheets_wargear",
            source_row_id="000004080:5:1:8656",
            expected_preimage_hash="3ebed7b85d4852b82d7e5407012a7a50b939ddc91bff253e309029bcb8214fa1",
            fields=(("S", "5"),),
        ),
        _supersede_row(
            op_id="ec-heldrake-remove-aircraft",
            order_index=80,
            source_row_id="000004092:Aircraft:global:false:14821",
            expected_preimage_hash="35dcd04f4905a479d39fb93c736ebf0f29c898ca6294cbb11f9a66b55d14e359",
            reason="Heldrake no longer has the Aircraft keyword.",
        ),
        *_blank_keyword_supersede_operations(),
        _add_keyword_row(
            op_id="ec-chaos-land-raider-frame",
            order_index=210,
            source_row_id="000004082:Frame:global:false:212",
            datasheet_id="000004082",
            keyword="Frame",
        ),
        _add_keyword_row(
            op_id="ec-chaos-rhino-frame",
            order_index=220,
            source_row_id="000004093:Frame:global:false:222",
            datasheet_id="000004093",
            keyword="Frame",
        ),
    )


def _blank_keyword_supersede_operations() -> tuple[SourceOverlayOperation, ...]:
    rows = (
        (
            90,
            "000004077:blank-keyword:global:true:14697",
            "2834bd29058a27b54322af93f6269852147c18ac90bcba20150873d619463834",
        ),
        (
            100,
            "000004079:blank-keyword:global:true:14716",
            "e672fd1f1a57df6c2733674a1480bbc4eb005614a13467d38ea8eaf7279c41d6",
        ),
        (
            110,
            "000004080:blank-keyword:global:true:14724",
            "f96b2f614255fad2a837cdf5d7166e9112e2136c1b0e7e25067ecbadfbf1ccc2",
        ),
        (
            120,
            "000004081:blank-keyword:global:true:14732",
            "ddf2efe0baa211300b64493699640004b82c12de3e949a880dbf06e21dd9a8aa",
        ),
        (
            130,
            "000004082:blank-keyword:global:true:14739",
            "c4f10106a47bfaa274e7e189beeace4f05e93f27ba05f276cdd750fc8ae8c907",
        ),
        (
            140,
            "000004089:blank-keyword:global:true:14795",
            "839031e144fcb10d4f7648ab50b7b6229dc5e0bcb0ff40689f4c4febdcacc16e",
        ),
        (
            150,
            "000004090:blank-keyword:global:true:14803",
            "39df7bdda1bbc40c2cb7613b36d6a62d974fbd79bd6039c32dd1d7fa235593e5",
        ),
        (
            160,
            "000004092:blank-keyword:global:true:14816",
            "5fd8e189992d73a920cba4e5420f149089fa4b7b26996e43320ee004a8e1e422",
        ),
        (
            170,
            "000004093:blank-keyword:global:true:14826",
            "9afb97df7e2885eb6c28fcc2e8a04311a7b78e94a3b985ae6cbb436754070eff",
        ),
    )
    return tuple(
        _supersede_row(
            op_id=f"ec-supersede-empty-keyword-{index}",
            order_index=order_index,
            source_row_id=source_row_id,
            expected_preimage_hash=expected_preimage_hash,
            reason="Supersede empty keyword source row before 11e bridge.",
        )
        for index, (order_index, source_row_id, expected_preimage_hash) in enumerate(
            rows,
            start=1,
        )
    )


def _update_row(
    *,
    op_id: str,
    order_index: int,
    source_table: str,
    source_row_id: str,
    expected_preimage_hash: str,
    fields: tuple[tuple[str, str], ...],
) -> SourceOverlayOperation:
    return SourceOverlayOperation(
        op_id=op_id,
        order_index=order_index,
        operation_kind=SourceOverlayOperationKind.UPDATE_ROW,
        target_edition=TARGET_EDITION,
        source_table=source_table,
        source_row_id=source_row_id,
        source_reference=SOURCE_REFERENCE,
        effective_date=SOURCE_DATE,
        reason="Apply Emperor's Children 11e datasheet update.",
        expected_preimage_hash=expected_preimage_hash,
        fields=fields,
    )


def _supersede_row(
    *,
    op_id: str,
    order_index: int,
    source_row_id: str,
    expected_preimage_hash: str,
    reason: str,
) -> SourceOverlayOperation:
    return SourceOverlayOperation(
        op_id=op_id,
        order_index=order_index,
        operation_kind=SourceOverlayOperationKind.SUPERSEDE_ROW,
        target_edition=TARGET_EDITION,
        source_table="Datasheets_keywords",
        source_row_id=source_row_id,
        source_reference=SOURCE_REFERENCE,
        effective_date=SOURCE_DATE,
        reason=reason,
        expected_preimage_hash=expected_preimage_hash,
        fields=(),
    )


def _add_keyword_row(
    *,
    op_id: str,
    order_index: int,
    source_row_id: str,
    datasheet_id: str,
    keyword: str,
) -> SourceOverlayOperation:
    return SourceOverlayOperation(
        op_id=op_id,
        order_index=order_index,
        operation_kind=SourceOverlayOperationKind.ADD_ROW,
        target_edition=TARGET_EDITION,
        source_table="Datasheets_keywords",
        source_row_id=source_row_id,
        source_reference=SOURCE_REFERENCE,
        effective_date=SOURCE_DATE,
        reason="Add Emperor's Children 11e datasheet keyword.",
        expected_preimage_hash=None,
        fields=(
            ("datasheet_id", datasheet_id),
            ("keyword", keyword),
            ("model", ""),
            ("is_faction_keyword", "false"),
        ),
    )
