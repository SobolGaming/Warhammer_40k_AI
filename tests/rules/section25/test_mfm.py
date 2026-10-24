"""FAQ24: replacement attachment targets reach real mustering, not just metadata."""

from dataclasses import replace

import pytest

from tests.support.section25_fixtures import BODY, LEADER, SUPPORT, request, selection
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.engine.army_mustering import ArmyMusteringError, muster_army
from warhammer40k_core.engine.army_points import catalog_with_mfm_attachment_allowances
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.rules.mfm_source import (
    MfmFactionRecord,
    MfmLeaderAllowance,
    MfmSourcePackage,
    MfmUnitCostBracket,
    MfmUnitCostRow,
    MfmUnitRecord,
    source_label_slug,
)


@pytest.mark.parametrize("support", [False, True])
def test_mfm_replaces_stale_datasheet_target_in_physical_mustering(
    section25_catalog: ArmyCatalog, support: bool
) -> None:
    c = section25_catalog
    old = c.datasheet_by_id(BODY)
    new = replace(old, datasheet_id="s25-body-new", name="Analytical New Bodyguard")
    sheet_ids = (BODY, LEADER, SUPPORT)
    c = replace(
        c,
        datasheets=(*(d for d in c.datasheets if d.datasheet_id in sheet_ids), new),
        detachments=(replace(c.detachments[0], unit_datasheet_ids=(*sheet_ids, new.datasheet_id)),),
    )
    faction = c.factions[0]
    rows: list[MfmUnitRecord] = []
    for d in c.datasheets:
        source_id = f"constructed:s25:mfm:{d.datasheet_id}"
        allowance = MfmLeaderAllowance((source_label_slug(new.name),), (new.name,), source_id)
        rows.append(
            MfmUnitRecord(
                record_id=d.datasheet_id,
                unit_id=source_label_slug(d.name),
                raw_name=d.name,
                source_section_id=None,
                source_section_name=None,
                cost_brackets=(
                    MfmUnitCostBracket(
                        "YOUR UNIT COSTS",
                        1,
                        None,
                        (MfmUnitCostRow("1 model", 50, source_id),),
                        source_id,
                    ),
                ),
                leader_allowance=allowance if d.datasheet_id == LEADER else None,
                support_allowance=allowance if d.datasheet_id == SUPPORT else None,
                source_id=source_id,
            )
        )
    package = MfmSourcePackage(
        source_package_id="constructed-s25-mfm",
        source_title="Analytical supported MFM input",
        source_version="fixture",
        source_date="2026-10-19",
        source_url="https://mfm.warhammer-community.com/en/",
        excluded_faction_ids=(),
        factions=(
            MfmFactionRecord(
                source_label_slug(faction.name),
                faction.name,
                "/en/analytical",
                (),
                tuple(rows),
                "constructed:s25:mfm:faction",
            ),
        ),
    )
    overlaid = catalog_with_mfm_attachment_allowances(
        catalog=c, faction_id=faction.faction_id, source_package=package
    )
    source_unit = "support" if support else "commander"
    units = (
        selection(c, "commander"),
        selection(c, "body", new.datasheet_id),
        *((selection(c, "support", SUPPORT),) if support else ()),
    )
    r = replace(
        request(c, units=units),
        attachment_declarations=(AttachmentDeclaration(source_unit, "body"),),
    )
    with pytest.raises(ArmyMusteringError, match="bodyguard datasheet is not allowed"):
        muster_army(catalog=c, request=r)
    army = muster_army(catalog=overlaid, request=r)
    assert army.attached_units[0].bodyguard_unit_instance_id == "s25-army:body"
    actual = (
        army.attached_units[0].support_unit_instance_ids
        if support
        else army.attached_units[0].leader_unit_instance_ids
    )
    assert actual == (f"s25-army:{source_unit}",)
    assert (
        c.datasheet_by_id(LEADER).attachment_eligibilities
        != overlaid.datasheet_by_id(LEADER).attachment_eligibilities
    )
    stale = replace(
        r,
        unit_selections=tuple(
            selection(overlaid, "body", BODY) if u.unit_selection_id == "body" else u for u in units
        ),
    )
    with pytest.raises(ArmyMusteringError, match="bodyguard datasheet is not allowed"):
        muster_army(catalog=overlaid, request=stale)
