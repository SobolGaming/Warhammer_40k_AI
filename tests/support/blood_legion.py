"""Shared source-backed fixtures and decision helpers for Blood Legion tests."""

from dataclasses import replace
from pathlib import Path

import pytest
from tests.daemons_native_source_helpers import SELECTED
from tests.support.faction_batch01 import LORD
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import pending
from tools.core_deep_strike_catalog_overlay import with_current_deep_strike
from tools.generate_ability_support_matrix import (
    BLOODLETTERS_HEIGHT_OVERRIDES,
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.core_deep_strike_successor import ABILITY_ID as DEEP_STRIKE_ABILITY_ID
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as blood_legion_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as identities,
)

BLOODMASTER = "000001455"
INFRACTORS = "000004080"
DETACHMENTS = {
    "chaos-daemons": "blood-legion",
    "emperors-children": "court-of-the-phoenician",
}
FIRST = "own:first"
SECOND = "own:second"
WRONG_KEYWORD = "own:undivided"
ENEMY = "foe:target"
BLOODTHIRSTER = "000002582"
GORE_ID = blood_legion_ir.GORE_HUNGRY_ONSLAUGHT_STRATAGEM_ID


@pytest.fixture(scope="module")
def skulls_definitions(selected_army_source_index: Path | None) -> Section02Definitions:
    package = _ability_support_catalog_package(
        datasheet_ids=(*SELECTED, BLOODTHIRSTER, "000004080", LORD, "000004090"),
        source_index_dir=selected_army_source_index,
    )
    return blood_legion_definitions(Section02Definitions(package, 0.0))


@pytest.fixture(scope="module")
def attached_skulls_definitions(selected_army_source_index: Path | None) -> Section02Definitions:
    # The production bridge has no reviewed Bloodmaster height. Use a test
    # height while retaining the source datasheet, base and attachment relation.
    test_height = replace(
        BLOODLETTERS_HEIGHT_OVERRIDES[0],
        datasheet_id=BLOODMASTER,
        model_name="Bloodmaster",
        height_source_id="test:skulls-beget-blood:bloodmaster:height",
        height_document_reference="Attached formation test fixture",
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "tools.generate_ability_support_matrix.BLOODLETTERS_HEIGHT_OVERRIDES",
            (*BLOODLETTERS_HEIGHT_OVERRIDES, test_height),
        )
        monkeypatch.setattr(
            "tools.generate_ability_support_matrix.with_current_deep_strike",
            _overlay_attached_fixture_deep_strike,
        )
        package = _ability_support_catalog_package(
            datasheet_ids=(*SELECTED, BLOODMASTER, INFRACTORS, LORD, "000004090"),
            source_index_dir=selected_army_source_index,
        )
    return blood_legion_definitions(Section02Definitions(package, 0.0))


def _overlay_attached_fixture_deep_strike(
    package: CanonicalCatalogPackage,
) -> CanonicalCatalogPackage:
    # These fixtures do not exercise the unaudited Bloodmaster
    # reserve descriptor. Keep the production overlay exact for the other rows.
    catalog = package.army_catalog
    sheets = tuple(
        replace(
            sheet,
            abilities=tuple(a for a in sheet.abilities if a.ability_id != DEEP_STRIKE_ABILITY_ID),
        )
        if sheet.datasheet_id == BLOODMASTER
        else sheet
        for sheet in catalog.datasheets
    )
    return with_current_deep_strike(
        replace(package, army_catalog=replace(catalog, datasheets=sheets))
    )


def blood_legion_definitions(native: Section02Definitions) -> Section02Definitions:
    catalog = native.package.army_catalog
    source_factions = {"CD": "chaos-daemons", "EC": "emperors-children"}
    factions = tuple(
        replace(faction, faction_id=source_factions[faction.faction_id])
        for faction in catalog.factions
    )
    detachments = tuple(
        DetachmentDefinition(
            canonical_detachment_id=row.detachment_id,
            detachment_id=row.detachment_id,
            name=row.name,
            faction_id=faction.faction_id,
            detachment_point_cost=row.detachment_point_cost,
            unit_datasheet_ids=tuple(
                sheet.datasheet_id
                for sheet in catalog.datasheets
                if set(sheet.keywords.faction_keywords).intersection(faction.faction_keywords)
            ),
            force_disposition_ids=tuple(
                sorted({row.force_disposition_id, "take-and-hold", "purge-the-foe"})
            ),
            source_ids=row.source_ids,
        )
        for faction in factions
        for row in identities.detachment_rows()
        if row.detachment_id == DETACHMENTS[faction.faction_id]
    )
    return Section02Definitions(
        replace(
            native.package,
            army_catalog=replace(catalog, factions=factions, detachments=detachments),
        ),
        native.preparation_seconds,
    )


def submit_option(session: LocalGameSession, option: str) -> LifecycleStatus:
    req = pending(session)
    return session.submit_option(
        request_id=req.request_id,
        result_id=f"{req.request_id}:skulls",
        option_id=option,
    )


def stratagem_targets(
    request: DecisionRequest, stratagem_id: str = blood_legion_ir.BLOOD_BEGETS_SKULLS_STRATAGEM_ID
) -> dict[str, str]:
    targets: dict[str, str] = {}
    for option in request.options:
        if not option.option_id.startswith(f"use-stratagem:{stratagem_id}:"):
            continue
        assert isinstance(option.payload, dict)
        binding = option.payload["target_binding"]
        assert isinstance(binding, dict)
        unit_id = binding["target_unit_instance_id"]
        assert isinstance(unit_id, str)
        targets[unit_id] = option.option_id
    return targets
