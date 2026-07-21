from __future__ import annotations

import json

import pytest
from tests.support.wahapedia_bridge_fixtures import (
    keeper_of_secrets_non_single_item_choice_source_artifacts,
)
from tests.support.wahapedia_source_fixtures import (
    artifact_by_table,
    bridge_package_id,
    catalog_package_id,
    catalog_version,
    conditioned_weapon_keyword_bridge_artifacts,
    unowned_wargear_profile_ability_source_artifacts,
    unsupported_ability_type_source_artifacts,
    unsupported_wargear_rule_source_artifacts,
    wahapedia_source_artifacts,
)

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySupport,
)
from warhammer40k_core.core.model_geometry_catalog import (
    GeometrySourceUnits,
)
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.wahapedia_bridge import (
    ModelHeightOverride,
    WahapediaBridgeError,
    build_wahapedia_canonical_bridge_artifacts,
)


def test_phase17k_keeper_bridge_rejects_non_single_item_equipment_choice() -> None:
    with pytest.raises(WahapediaBridgeError, match="single-item additive choices"):
        build_wahapedia_canonical_bridge_artifacts(
            source_artifacts=keeper_of_secrets_non_single_item_choice_source_artifacts(),
            bridge_package_id=bridge_package_id(),
            datasheet_ids=("000001137",),
            height_overrides=(
                ModelHeightOverride(
                    datasheet_id="000001137",
                    model_name="Keeper of Secrets",
                    height=5.6,
                    height_units=GeometrySourceUnits.INCHES,
                    height_source_id="geometry-review:chaos-daemons:keeper-of-secrets:height",
                    height_document_reference="Chaos Daemons Faction Pack p.90-91",
                ),
            ),
        )


def test_phase17k_bridge_rejects_unowned_wargear_profile_ability() -> None:
    with pytest.raises(
        WahapediaBridgeError,
        match="Wargear profile ability must map to exactly one wargear item",
    ):
        build_wahapedia_canonical_bridge_artifacts(
            source_artifacts=unowned_wargear_profile_ability_source_artifacts(),
            bridge_package_id=bridge_package_id(),
            datasheet_ids=("test-wargear-profile-owner",),
            height_overrides=(
                ModelHeightOverride(
                    datasheet_id="test-wargear-profile-owner",
                    model_name="Profile Bearer",
                    height=1.0,
                    height_units=GeometrySourceUnits.INCHES,
                    height_source_id="test-source:wargear-profile-owner-height",
                    height_document_reference="test-doc:wargear-profile-owner-height",
                ),
            ),
        )


@pytest.mark.parametrize(
    ("description", "message"),
    [
        ("[]", "weapon keyword list must not be empty"),
        ("[: MONSTER]", "weapon keyword must not be empty"),
        ("[LETHAL HITS:]", "weapon keyword condition must not be empty"),
        ("[ANTI-INFANTRY 4+: MONSTER]", "Anti weapon keywords do not support target conditions"),
        ("[EXTRA ATTACKS: MONSTER]", "Unsupported conditioned Wahapedia weapon keyword"),
        ("[RAPID FIRE]", "Valued Wahapedia weapon keyword is missing its value"),
        ("[UNKNOWN]", "Unsupported Wahapedia weapon keyword"),
        ("[LETHAL HITS, LETHAL HITS]", "must not duplicate"),
        (
            "[DEVASTATING WOUNDS: INFANTRY, DEVASTATING WOUNDS: MONSTER]",
            "duplicate non-Anti ability kinds",
        ),
        (
            "[MELTA 2: non-MONSTER/VEHICLE, MELTA 4: INFANTRY]",
            "duplicate non-Anti ability kinds",
        ),
        ("[LETHAL HITS: non-]", "Invalid Wahapedia weapon ability descriptor"),
    ],
)
def test_phase17k_bridge_rejects_invalid_conditioned_wargear_weapon_keywords(
    description: str,
    message: str,
) -> None:
    with pytest.raises(WahapediaBridgeError, match=message):
        conditioned_weapon_keyword_bridge_artifacts(description)


def test_phase17k_bridge_rejects_unsupported_datasheet_ability_type() -> None:
    with pytest.raises(WahapediaBridgeError, match="Unsupported datasheet ability type"):
        build_wahapedia_canonical_bridge_artifacts(
            source_artifacts=unsupported_ability_type_source_artifacts(),
            bridge_package_id=bridge_package_id(),
            datasheet_ids=("test-unsupported-ability-type",),
            height_overrides=(
                ModelHeightOverride(
                    datasheet_id="test-unsupported-ability-type",
                    model_name="Invalid",
                    height=1.0,
                    height_units=GeometrySourceUnits.INCHES,
                    height_source_id="test-source:invalid-height",
                    height_document_reference="test-doc:invalid-height",
                ),
            ),
        )


def test_phase17k_bridge_preserves_unsupported_rule_ir_diagnostics() -> None:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=unsupported_wargear_rule_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-unsupported-unit",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-unsupported-unit",
                model_name="Alpha",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:unsupported-height",
                height_document_reference="test-doc:unsupported-height",
            ),
        ),
    )
    ability_row = next(
        row
        for row in artifact_by_table(bridge_artifacts, "Datasheets_abilities").rows
        if row.runtime_fields_payload()["name"] == "Scatter Icon"
    )
    fields = ability_row.runtime_fields_payload()
    diagnostics = json.loads(fields["rule_ir_diagnostics"])
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=bridge_artifacts,
    )
    abilities_by_name = {
        ability.name: ability
        for ability in package.army_catalog.datasheet_by_id("test-unsupported-unit").abilities
    }
    ability = abilities_by_name["Scatter Icon"]

    assert fields["support"] == "unsupported"
    assert fields["rule_ir_payload"]
    assert diagnostics[0]["reason"] == "unsupported_language"
    assert diagnostics[0]["source_span"]["text"] == (
        "Roll a scatter die and consult the legacy table."
    )
    assert ability.support is CatalogAbilitySupport.UNSUPPORTED
    assert ability.rule_ir_payload is not None
    assert ability.rule_ir_diagnostics == tuple(diagnostics)


def test_phase17k_bridge_requires_accepted_height_overrides() -> None:
    with pytest.raises(WahapediaBridgeError, match="height override"):
        build_wahapedia_canonical_bridge_artifacts(
            source_artifacts=wahapedia_source_artifacts(),
            bridge_package_id=bridge_package_id(),
            datasheet_ids=("000001115",),
            height_overrides=(),
        )
