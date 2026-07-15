from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING or __package__:
    from tools.aeldari_datasheet_semantic_coverage import (
        GENERATED_BY,
        SCHEMA_VERSION,
        SOURCE_ARTIFACT_TABLES,
        ExactAbilitySemanticEvidence,
        ExactSemanticConsumerEvidence,
        exact_ability_semantic_bucket,
    )
    from tools.aeldari_datasheet_semantic_evidence import (
        SourceDerivedAeldariAbilityEvidence,
        source_derived_aeldari_exact_ability_evidence,
    )
    from tools.faction_pack_datasheet_review import (
        DatasheetSourceTreatment,
        faction_pack_datasheet_review,
    )
    from tools.generate_ability_support_matrix import (
        DEFAULT_SOURCE_JSON_DIR,
        _load_source_artifacts,
    )
else:
    from aeldari_datasheet_semantic_coverage import (
        GENERATED_BY,
        SCHEMA_VERSION,
        SOURCE_ARTIFACT_TABLES,
        ExactAbilitySemanticEvidence,
        ExactSemanticConsumerEvidence,
        exact_ability_semantic_bucket,
    )
    from aeldari_datasheet_semantic_evidence import (
        SourceDerivedAeldariAbilityEvidence,
        source_derived_aeldari_exact_ability_evidence,
    )
    from faction_pack_datasheet_review import (
        DatasheetSourceTreatment,
        faction_pack_datasheet_review,
    )
    from generate_ability_support_matrix import DEFAULT_SOURCE_JSON_DIR, _load_source_artifacts
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_overlay import (
    OverlaySourceArtifact,
    SourceOverlayOperation,
    SourceOverlayOperationKind,
    SourceOverlayPack,
    SourceReleaseManifest,
    apply_source_release_overlays,
)
from warhammer40k_core.rules.source_patch import source_row_hash
from warhammer40k_core.rules.wahapedia_bridge_rows import bridge_rows_by_table
from warhammer40k_core.rules.wahapedia_datasheet_ability_bridge import (
    WahapediaDatasheetAbilityBridgeError,
)
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = (
    REPO_ROOT
    / "data"
    / "generated"
    / "ability_coverage"
    / "aeldari_datasheet_semantic_coverage.json"
)
OVERLAY_DIR = REPO_ROOT / "data" / "source_overlays" / "aeldari_faction_pack_2026_06"
OVERLAY_PACK_PATH = OVERLAY_DIR / "aeldari-faction-pack-datasheet-overlay.overlay-pack.json"
RELEASE_MANIFEST_PATH = OVERLAY_DIR / "source_release_manifest.json"
SOURCE_DATE = "2026-06-09"
SOURCE_REFERENCE = "pdf:aeldari-faction-pack:2026-06-09:p23"
KHARSETH_SOURCE_REFERENCE = "pdf:aeldari-faction-pack:2026-06-09:p14-15"
PRINCE_YRIEL_SOURCE_REFERENCE = "pdf:aeldari-faction-pack:2026-06-09:p12-13"
VYPERS_SOURCE_REFERENCE = "pdf:aeldari-faction-pack:2026-06-09:p16-17"
STARFANGS_SOURCE_REFERENCE = "pdf:aeldari-faction-pack:2026-06-09:p18-19"
CORSAIR_SKYREAVERS_SOURCE_REFERENCE = "pdf:aeldari-faction-pack:2026-06-09:p20-21"
CORSAIR_VOID_UNITS_KEYWORD_SOURCE_REFERENCE = (
    "data-package:wahapedia:source-mirror:10th-edition-2026-06-14:Datasheets_keywords"
)
TARGET_EDITION = "warhammer-40000-11th"
BASE_SOURCE_PACKAGE_ID = DataPackageId(
    namespace="wahapedia",
    package_name="source-mirror",
    version="10th-edition-2026-06-14",
)
OVERLAY_PACKAGE_ID = DataPackageId(
    namespace="gw",
    package_name="aeldari-faction-pack-datasheet-overlay",
    version="11th-2026-06-09",
)
CATALOG_VERSION = CatalogVersion.dated(
    version_id="warhammer-40000-11th-aeldari-faction-pack-2026-06",
    source_date=date.fromisoformat(SOURCE_DATE),
)
SUPPORT_ABILITY_ID = "core-v2-11e-support"

ASPECT_SHRINE_TOKEN_DESCRIPTION = (
    "Once per battle for each Aspect Shrine token this unit has, you can change the result of "
    "one Hit roll or one Wound roll made for a model in this unit (excluding CHARACTER models) "
    "to an unmodified 6."
)
ASPECT_SHRINE_DATASHEET_IDS = (
    "000000607",
    "000000593",
    "000000596",
    "000000594",
    "000000595",
    "000000600",
    "000000601",
)


@dataclass(frozen=True, slots=True)
class _UpdateSpec:
    datasheet_id: str
    source_table: str
    source_row_id: str
    fields: tuple[tuple[str, str], ...]
    reason: str


def main() -> None:
    overlay_pack, release_manifest, coverage_payload = (
        generated_aeldari_datasheet_semantic_coverage()
    )
    OVERLAY_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(OVERLAY_PACK_PATH, overlay_pack.to_payload())
    _write_json(RELEASE_MANIFEST_PATH, release_manifest.to_payload())
    _write_json(OUTPUT_PATH, coverage_payload)


def generated_aeldari_datasheet_semantic_coverage() -> tuple[
    SourceOverlayPack,
    SourceReleaseManifest,
    dict[str, object],
]:
    source_artifacts = _load_source_artifacts(DEFAULT_SOURCE_JSON_DIR)
    rows_by_table = bridge_rows_by_table(
        source_artifacts,
        error_type=WahapediaDatasheetAbilityBridgeError,
    )
    overlay_pack = _overlay_pack(rows_by_table)
    release_manifest = _release_manifest()
    effective_artifacts = apply_source_release_overlays(
        source_artifacts=source_artifacts,
        release_manifest=release_manifest,
        overlay_packs=(overlay_pack,),
    )
    _validate_effective_updates(effective_artifacts)
    coverage_payload = _coverage_payload(
        effective_artifacts=effective_artifacts,
        overlay_pack=overlay_pack,
        release_manifest=release_manifest,
    )
    return overlay_pack, release_manifest, coverage_payload


def _overlay_pack(
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]],
) -> SourceOverlayPack:
    specs = _update_specs(rows_by_table)
    review = faction_pack_datasheet_review("aeldari")
    expected_update_ids = {
        row.datasheet_id
        for row in review.rows_for(DatasheetSourceTreatment.RULES_UPDATE)
        if row.datasheet_id is not None
    }
    actual_update_ids = {spec.datasheet_id for spec in specs}
    if actual_update_ids != expected_update_ids:
        raise ValueError(
            "Aeldari overlay operations must cover every reviewed rules-update datasheet."
        )
    operations: list[SourceOverlayOperation] = []
    for index, spec in enumerate(specs, start=1):
        row = _required_row(rows_by_table, spec.source_table, spec.source_row_id)
        operations.append(
            SourceOverlayOperation(
                op_id=f"aeldari-update-{index:03d}-{spec.datasheet_id}",
                order_index=index,
                operation_kind=SourceOverlayOperationKind.UPDATE_ROW,
                target_edition=TARGET_EDITION,
                source_table=spec.source_table,
                source_row_id=spec.source_row_id,
                source_reference=SOURCE_REFERENCE,
                effective_date=SOURCE_DATE,
                reason=spec.reason,
                expected_preimage_hash=source_row_hash(row),
                fields=spec.fields,
            )
        )
    kharseth_model_row = _required_row(
        rows_by_table,
        "Datasheets_models",
        "000004194:1",
    )
    operations.append(
        SourceOverlayOperation(
            op_id="aeldari-correct-kharseth-model-name",
            order_index=len(operations) + 1,
            operation_kind=SourceOverlayOperationKind.UPDATE_ROW,
            target_edition=TARGET_EDITION,
            source_table="Datasheets_models",
            source_row_id="000004194:1",
            source_reference=KHARSETH_SOURCE_REFERENCE,
            effective_date=SOURCE_DATE,
            reason="Correct the mirrored Kharseth model name from the reviewed datasheet.",
            expected_preimage_hash=source_row_hash(kharseth_model_row),
            fields=(("name", "Kharseth"),),
        )
    )
    kharseth_blank_keyword_row = _required_row(
        rows_by_table,
        "Datasheets_keywords",
        "000004194:blank-keyword:global:true:15622",
    )
    operations.append(
        SourceOverlayOperation(
            op_id="aeldari-supersede-kharseth-blank-faction-keyword",
            order_index=len(operations) + 1,
            operation_kind=SourceOverlayOperationKind.SUPERSEDE_ROW,
            target_edition=TARGET_EDITION,
            source_table="Datasheets_keywords",
            source_row_id=kharseth_blank_keyword_row.source_row_id,
            source_reference=KHARSETH_SOURCE_REFERENCE,
            effective_date=SOURCE_DATE,
            reason=(
                "Supersede the mirrored blank faction-keyword row before the strict "
                "Kharseth catalog bridge."
            ),
            expected_preimage_hash=source_row_hash(kharseth_blank_keyword_row),
            fields=(),
        )
    )
    for datasheet_id, datasheet_name, source_row_id in (
        (
            "000002531",
            "Corsair Voidreavers",
            "000002531:blank-keyword:global:true:6675",
        ),
        (
            "000002532",
            "Corsair Voidscarred",
            "000002532:blank-keyword:global:true:6682",
        ),
    ):
        blank_keyword_row = _required_row(
            rows_by_table,
            "Datasheets_keywords",
            source_row_id,
        )
        operations.append(
            SourceOverlayOperation(
                op_id=f"aeldari-supersede-{datasheet_id}-blank-faction-keyword",
                order_index=len(operations) + 1,
                operation_kind=SourceOverlayOperationKind.SUPERSEDE_ROW,
                target_edition=TARGET_EDITION,
                source_table="Datasheets_keywords",
                source_row_id=blank_keyword_row.source_row_id,
                source_reference=CORSAIR_VOID_UNITS_KEYWORD_SOURCE_REFERENCE,
                effective_date=SOURCE_DATE,
                reason=(
                    "Supersede the mirrored blank faction-keyword row before the strict "
                    f"{datasheet_name} catalog bridge."
                ),
                expected_preimage_hash=source_row_hash(blank_keyword_row),
                fields=(),
            )
        )
    skyreavers_blank_keyword_row = _required_row(
        rows_by_table,
        "Datasheets_keywords",
        "000004196:blank-keyword:global:true:15640",
    )
    operations.append(
        SourceOverlayOperation(
            op_id="aeldari-supersede-corsair-skyreavers-blank-faction-keyword",
            order_index=len(operations) + 1,
            operation_kind=SourceOverlayOperationKind.SUPERSEDE_ROW,
            target_edition=TARGET_EDITION,
            source_table="Datasheets_keywords",
            source_row_id=skyreavers_blank_keyword_row.source_row_id,
            source_reference=CORSAIR_SKYREAVERS_SOURCE_REFERENCE,
            effective_date=SOURCE_DATE,
            reason=(
                "Supersede the mirrored blank faction-keyword row before the strict "
                "Corsair Skyreavers catalog bridge."
            ),
            expected_preimage_hash=source_row_hash(skyreavers_blank_keyword_row),
            fields=(),
        )
    )
    for datasheet_id, datasheet_name, source_row_id, source_reference in (
        (
            "000004193",
            "Prince Yriel",
            "000004193:blank-keyword:global:true:15614",
            PRINCE_YRIEL_SOURCE_REFERENCE,
        ),
        (
            "000000605",
            "Vypers",
            "000000605:blank-keyword:global:true:2352",
            VYPERS_SOURCE_REFERENCE,
        ),
        (
            "000004195",
            "Starfangs",
            "000004195:blank-keyword:global:true:15631",
            STARFANGS_SOURCE_REFERENCE,
        ),
    ):
        blank_keyword_row = _required_row(
            rows_by_table,
            "Datasheets_keywords",
            source_row_id,
        )
        operations.append(
            SourceOverlayOperation(
                op_id=f"aeldari-supersede-{datasheet_id}-blank-faction-keyword",
                order_index=len(operations) + 1,
                operation_kind=SourceOverlayOperationKind.SUPERSEDE_ROW,
                target_edition=TARGET_EDITION,
                source_table="Datasheets_keywords",
                source_row_id=blank_keyword_row.source_row_id,
                source_reference=source_reference,
                effective_date=SOURCE_DATE,
                reason=(
                    "Supersede the mirrored blank faction-keyword row before the strict "
                    f"{datasheet_name} catalog bridge."
                ),
                expected_preimage_hash=source_row_hash(blank_keyword_row),
                fields=(),
            )
        )
    add_index = len(operations) + 1
    operations.append(
        SourceOverlayOperation(
            op_id="aeldari-add-support-core-ability",
            order_index=add_index,
            operation_kind=SourceOverlayOperationKind.ADD_ROW,
            target_edition=TARGET_EDITION,
            source_table="Abilities",
            source_row_id=f"{SUPPORT_ABILITY_ID}:global",
            source_reference=SOURCE_REFERENCE,
            effective_date=SOURCE_DATE,
            reason="Add the 11th Edition Support core ability referenced by the Warlock update.",
            expected_preimage_hash=None,
            fields=(
                ("id", SUPPORT_ABILITY_ID),
                ("faction_id", ""),
                ("name", "Support"),
                ("description", "This model has the Support ability."),
            ),
        )
    )
    for datasheet_id in ("000000603", "000000606"):
        add_index += 1
        operations.append(
            SourceOverlayOperation(
                op_id=f"aeldari-add-frame-keyword-{datasheet_id}",
                order_index=add_index,
                operation_kind=SourceOverlayOperationKind.ADD_ROW,
                target_edition=TARGET_EDITION,
                source_table="Datasheets_keywords",
                source_row_id=f"{datasheet_id}:FRAME:global:false:{add_index + 2}",
                source_reference=SOURCE_REFERENCE,
                effective_date=SOURCE_DATE,
                reason="Add the Faction Pack FRAME keyword.",
                expected_preimage_hash=None,
                fields=(
                    ("datasheet_id", datasheet_id),
                    ("keyword", "FRAME"),
                    ("model", ""),
                    ("is_faction_keyword", "false"),
                ),
            )
        )
    return SourceOverlayPack(
        package_id=OVERLAY_PACKAGE_ID,
        catalog_version=CATALOG_VERSION,
        base_source_package_id=BASE_SOURCE_PACKAGE_ID,
        target_edition=TARGET_EDITION,
        effective_date=SOURCE_DATE,
        operations=tuple(operations),
    )


def _release_manifest() -> SourceReleaseManifest:
    return SourceReleaseManifest(
        release_id="aeldari-faction-pack-datasheet-release-2026-06",
        catalog_version=CATALOG_VERSION,
        base_source_package_id=BASE_SOURCE_PACKAGE_ID,
        base_source_edition="warhammer-40000-10th",
        target_edition=TARGET_EDITION,
        overlay_package_ids=(OVERLAY_PACKAGE_ID,),
    )


def _update_specs(
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]],
) -> tuple[_UpdateSpec, ...]:
    specs: list[_UpdateSpec] = []
    for datasheet_id in ASPECT_SHRINE_DATASHEET_IDS:
        specs.append(
            _ability_update(
                rows_by_table,
                datasheet_id=datasheet_id,
                ability_name="Aspect Shrine Token",
                description=ASPECT_SHRINE_TOKEN_DESCRIPTION,
            )
        )
    specs.extend(
        (
            _ability_update(
                rows_by_table,
                datasheet_id="000000571",
                ability_name="Hand of Asuryan",
                description=(
                    "Once per battle, when this model is selected to shoot, it can use this "
                    "ability. If it does, until the end of the phase, its Bloody Twins weapon "
                    "has a Damage characteristic of 3 and the [ANTI-INFANTRY 5+] and "
                    "[DEVASTATING WOUNDS] abilities."
                ),
            ),
            _ability_update(
                rows_by_table,
                datasheet_id="000000575",
                ability_name="Cloudstrider",
                description=(
                    "While this model is leading a unit, at the end of your opponent's turn, if "
                    "that unit is not within Engagement Range of one or more enemy units, you "
                    "can remove it from the battlefield and place it into Strategic Reserves. "
                    "In addition, while this model is leading a unit, when that unit is set up "
                    "on the battlefield using the Deep Strike ability, in your Movement phase, "
                    "it can use this ability. If it does, that unit can be set up anywhere on "
                    'the battlefield that is more than 6" horizontally away from all enemy '
                    "models, but until the end of the turn, it is not eligible to declare a charge."
                ),
            ),
            _field_update(
                datasheet_id="000002531",
                source_table="Datasheets_options",
                source_row_id="000002531:3",
                fields=(
                    (
                        "description",
                        "Any number of Corsair Voidreavers in this unit can each have their "
                        "shuriken pistol and power sword replaced with 1 shuriken rifle.",
                    ),
                ),
                reason="Apply the Corsair Voidreavers wargear-option update.",
            ),
            _field_update(
                datasheet_id="000000609",
                source_table="Datasheets",
                source_row_id="000000609",
                fields=(("transport", _falcon_transport()),),
                reason="Apply the Falcon transport update.",
            ),
            _field_update(
                datasheet_id="000000582",
                source_table="Datasheets_leader",
                source_row_id="000000582:000000584:130",
                fields=(("attached_id", "000000584"),),
                reason="Apply the Farseer Leader-section update.",
            ),
            _ability_update(
                rows_by_table,
                datasheet_id="000000592",
                ability_name="Path of the Outcast",
                description=(
                    "In your opponent's Movement phase, if an enemy unit ends a move within "
                    '8" of this unit, if this unit is not within Engagement Range of one or '
                    'more enemy units, this unit can make a Normal move of up to D6".'
                ),
            ),
            _field_update(
                datasheet_id="000002535",
                source_table="Datasheets_options",
                source_row_id="000002535:1",
                fields=(
                    (
                        "description",
                        "This model's shuriken pistol can be replaced with 1 neuro disruptor.",
                    ),
                ),
                reason="Apply the Shadowseer wargear-option update.",
            ),
            _ability_update(
                rows_by_table,
                datasheet_id="000002541",
                ability_name="Rapid Embarkation",
                description=(
                    "At the end of the Fight phase, if there are no models currently embarked "
                    "within this TRANSPORT, you can select one friendly Harlequins Infantry "
                    'unit that has 6 or fewer models that is wholly within 6" of this '
                    "TRANSPORT. Unless that unit is within Engagement Range of one or more "
                    "enemy units, it can embark within this TRANSPORT. That unit can embark "
                    "within this TRANSPORT in a turn it disembarked from this TRANSPORT."
                ),
            ),
            _field_update(
                datasheet_id="000000603",
                source_table="Datasheets_models",
                source_row_id="000000603:1",
                fields=(("M", "-"), ("OC", "-")),
                reason="Apply the Crimson Hunter profile update.",
            ),
            _field_update(
                datasheet_id="000000606",
                source_table="Datasheets_models",
                source_row_id="000000606:1",
                fields=(("M", "-"), ("OC", "-")),
                reason="Apply the Hemlock Wraithfighter profile update.",
            ),
            _field_update(
                datasheet_id="000000599",
                source_table="Datasheets",
                source_row_id="000000599",
                fields=(("transport", _wave_serpent_transport()),),
                reason="Apply the Wave Serpent transport update.",
            ),
            _field_update(
                datasheet_id="000000584",
                source_table="Datasheets",
                source_row_id="000000584",
                fields=(("leader_footer", _warlock_conclave_leader()),),
                reason="Apply the Warlock Conclave keyword and Leader-section update.",
            ),
            _ability_update(
                rows_by_table,
                datasheet_id="000000587",
                ability_name="Runes of Battle (Psychic)",
                description=(
                    "Weapons equipped by models in this unit have the [IGNORES COVER] ability."
                ),
            ),
            _ability_update(
                rows_by_table,
                datasheet_id="000002542",
                ability_name="Herald of Ynnead",
                description=(
                    "At the start of the Fight phase, select one enemy unit within Engagement "
                    "Range of this model. Until the end of the phase, each time a friendly "
                    "AELDARI model makes an attack that targets that unit, you can re-roll a "
                    "Wound roll of 1."
                ),
            ),
            _ability_update(
                rows_by_table,
                datasheet_id="000003921",
                ability_name="Lithe Embarkation",
                description=(
                    "At the end of the Fight phase, if there are no models currently embarked "
                    "within this TRANSPORT, you can select one friendly Ynnari Infantry unit "
                    "that only includes models from the units listed in this unit's Transport "
                    'section, that has 6 or fewer models and that is wholly within 6" of this '
                    "TRANSPORT. Unless that unit is within Engagement Range of one or more "
                    "enemy units, it can embark within this TRANSPORT. That unit can embark "
                    "within this TRANSPORT in a turn it disembarked from this TRANSPORT."
                ),
            ),
            _field_update(
                datasheet_id="000003918",
                source_table="Datasheets_wargear",
                source_row_id="000003918:1:1:7619",
                fields=(("AP", "-2"),),
                reason="Apply the Ynnari Incubi demiklaives AP update.",
            ),
            _field_update(
                datasheet_id="000000585",
                source_table="Datasheets_abilities",
                source_row_id="000000585:1",
                fields=(("ability_id", SUPPORT_ABILITY_ID),),
                reason="Replace the Warlock Leader core ability with Support.",
            ),
        )
    )
    return tuple(specs)


def _coverage_payload(
    *,
    effective_artifacts: tuple[OverlaySourceArtifact, ...],
    overlay_pack: SourceOverlayPack,
    release_manifest: SourceReleaseManifest,
) -> dict[str, object]:
    review = faction_pack_datasheet_review("aeldari")
    datasheet_id_names = tuple(
        (row.datasheet_id, row.datasheet_name)
        for row in review.rows
        if row.datasheet_id is not None
    )
    source_evidence = source_derived_aeldari_exact_ability_evidence(
        effective_artifacts=effective_artifacts,
        datasheet_id_names=datasheet_id_names,
    )
    rows_by_datasheet: dict[str, list[SourceDerivedAeldariAbilityEvidence]] = {
        datasheet_id: [] for datasheet_id, _ in datasheet_id_names
    }
    for row in source_evidence:
        rows_by_datasheet[row.datasheet_id].append(row)
    datasheet_payloads: list[dict[str, object]] = []
    bucket_counts: Counter[str] = Counter()
    for review_row in review.rows:
        if review_row.datasheet_id is None:
            raise ValueError("Aeldari effective coverage requires source-backed datasheet IDs.")
        ability_rows = rows_by_datasheet[review_row.datasheet_id]
        if not ability_rows:
            raise ValueError("Aeldari effective coverage requires exact abilities per datasheet.")
        ability_payloads: list[dict[str, object]] = []
        semantic_evidence: list[ExactAbilitySemanticEvidence] = []
        for ability_row in ability_rows:
            semantic_consumers = tuple(
                ExactSemanticConsumerEvidence(
                    semantic_id=semantic.semantic_id,
                    semantic_kind=semantic.semantic_kind,
                    runtime_consumer_ids=semantic.runtime_consumer_ids,
                )
                for semantic in ability_row.semantic_consumers
            )
            semantic_evidence.append(
                ExactAbilitySemanticEvidence(
                    support_stage=ability_row.support_stage,
                    semantic_consumers=semantic_consumers,
                    runtime_consumer_ids=ability_row.runtime_consumer_ids,
                    diagnostic_reasons=ability_row.diagnostic_reasons,
                )
            )
            ability_payloads.append(ability_row.to_ability_payload())
        bucket = exact_ability_semantic_bucket(tuple(semantic_evidence))
        bucket_counts[bucket] += 1
        datasheet_payloads.append(
            {
                "datasheet_id": review_row.datasheet_id,
                "datasheet_name": review_row.datasheet_name,
                "group": review_row.group,
                "treatment": review_row.treatment.value,
                "pdf_page_reference": review_row.pdf_page_reference,
                "semantic_bucket": bucket,
                "abilities": ability_payloads,
            }
        )
    exact_ability_count = len(source_evidence)
    source_artifact_hashes = {
        artifact.source_table: artifact.artifact_hash() for artifact in effective_artifacts
    }
    if source_artifact_hashes.keys() != set(SOURCE_ARTIFACT_TABLES):
        raise ValueError("Aeldari semantic coverage source artifact scope drifted.")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": GENERATED_BY,
        "faction_id": review.faction_id,
        "faction_name": review.faction_name,
        "pdf_filename": review.pdf_filename,
        "pdf_sha256": review.pdf_sha256,
        "source_snapshot_path": DEFAULT_SOURCE_JSON_DIR.as_posix(),
        "source_artifact_hashes": dict(sorted(source_artifact_hashes.items())),
        "overlay_pack_hash": overlay_pack.package_hash(),
        "release_hash": release_manifest.release_hash(),
        "treatment_counts": {
            treatment.value: len(review.rows_for(treatment))
            for treatment in DatasheetSourceTreatment
        },
        "semantic_bucket_counts": dict(sorted(bucket_counts.items())),
        "datasheet_count": len(datasheet_payloads),
        "exact_ability_count": exact_ability_count,
        "datasheets": datasheet_payloads,
    }


def _validate_effective_updates(
    effective_artifacts: tuple[OverlaySourceArtifact, ...],
) -> None:
    rows = bridge_rows_by_table(
        effective_artifacts,
        error_type=WahapediaDatasheetAbilityBridgeError,
    )
    _assert_keyword(rows, "000000603", "FRAME", present=True)
    _assert_keyword(rows, "000000606", "FRAME", present=True)
    _assert_keyword(rows, "000000584", "CHARACTER", present=False)
    _assert_keyword(rows, "000000587", "CHARACTER", present=False)
    leader_targets = {
        row.runtime_fields_payload()["attached_id"]
        for row in rows["Datasheets_leader"]
        if row.runtime_fields_payload()["leader_id"] == "000000582"
    }
    if leader_targets != {"000000584", "000000589", "000000590"}:
        raise ValueError("Aeldari Farseer Leader update did not resolve exact targets.")
    warlock_ability = _required_row(rows, "Datasheets_abilities", "000000585:1")
    if warlock_ability.runtime_fields_payload()["ability_id"] != SUPPORT_ABILITY_ID:
        raise ValueError("Aeldari Warlock Support update did not apply.")
    kharseth_model = _required_row(rows, "Datasheets_models", "000004194:1")
    if kharseth_model.runtime_fields_payload()["name"] != "Kharseth":
        raise ValueError("Aeldari Kharseth model-name correction did not apply.")
    _assert_keyword(rows, "000004194", "", present=False)
    _assert_keyword(rows, "000004196", "", present=False)
    _assert_keyword(rows, "000002531", "", present=False)
    _assert_keyword(rows, "000002532", "", present=False)


def _assert_keyword(
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]],
    datasheet_id: str,
    keyword: str,
    *,
    present: bool,
) -> None:
    keywords = {
        row.runtime_fields_payload()["keyword"].upper()
        for row in rows_by_table["Datasheets_keywords"]
        if row.runtime_fields_payload()["datasheet_id"] == datasheet_id
    }
    if (keyword in keywords) is not present:
        raise ValueError("Aeldari effective keyword assertion failed.")


def _ability_update(
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]],
    *,
    datasheet_id: str,
    ability_name: str,
    description: str,
) -> _UpdateSpec:
    matches = tuple(
        row
        for row in rows_by_table["Datasheets_abilities"]
        if row.runtime_fields_payload().get("datasheet_id") == datasheet_id
        and row.runtime_fields_payload().get("name", "").casefold() == ability_name.casefold()
    )
    if len(matches) != 1:
        raise ValueError("Aeldari update ability target must resolve exactly once.")
    return _field_update(
        datasheet_id=datasheet_id,
        source_table="Datasheets_abilities",
        source_row_id=matches[0].source_row_id,
        fields=(("description", description),),
        reason=f"Apply the {ability_name} Faction Pack update.",
    )


def _field_update(
    *,
    datasheet_id: str,
    source_table: str,
    source_row_id: str,
    fields: tuple[tuple[str, str], ...],
    reason: str,
) -> _UpdateSpec:
    return _UpdateSpec(
        datasheet_id=datasheet_id,
        source_table=source_table,
        source_row_id=source_row_id,
        fields=fields,
        reason=reason,
    )


def _required_row(
    rows_by_table: dict[str, tuple[NormalizedSourceRow, ...]],
    source_table: str,
    source_row_id: str,
) -> NormalizedSourceRow:
    matches = tuple(
        row for row in rows_by_table.get(source_table, ()) if row.source_row_id == source_row_id
    )
    if len(matches) != 1:
        raise ValueError("Aeldari update source row must resolve exactly once.")
    return matches[0]


def _falcon_transport() -> str:
    return (
        "This model has a transport capacity of 6 Aeldari Infantry models. Each Wraith "
        "Construct model takes the space of 2 models. It cannot transport Jump Pack models "
        "or Ynnari models (excluding Asuryani, Yvraine and The Visarch models)."
    )


def _wave_serpent_transport() -> str:
    return (
        "This model has a transport capacity of 12 Asuryani Infantry models. Each Wraith "
        "Construct model takes the space of 2 models. It cannot transport Jump Pack models "
        "or Ynnari models (excluding Asuryani, Yvraine and The Visarch models)."
    )


def _warlock_conclave_leader() -> str:
    return (
        "At the start of the Declare Battle Formations step, if this unit is not an Attached "
        "unit, this unit can join one Guardian Defenders or Storm Guardians unit from your "
        "army (a unit cannot have more than one WARLOCK CONCLAVE unit joined to it). If it "
        "does, until the end of the battle, every model in this unit counts as being part of "
        "that Bodyguard unit, and that Bodyguard unit's Starting Strength is increased accordingly."
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
