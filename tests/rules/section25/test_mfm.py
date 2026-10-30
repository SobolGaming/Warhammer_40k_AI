"""FAQ24: replacement attachment targets reach real mustering, not just metadata."""

import gzip
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
from tools.build_mfm_update_review import build_current_review_payload

from tests.support.section25_fixtures import BODY, LEADER, SUPPORT, assignment, request, selection
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.engine.army_mustering import ArmyMusteringError, muster_army
from warhammer40k_core.engine.army_points import (
    calculate_mfm_army_points,
    catalog_with_mfm_attachment_allowances,
    catalog_with_mfm_points,
)
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.rules.mfm_source import (
    MfmDetachmentRecord,
    MfmFactionRecord,
    MfmIndexFaction,
    MfmLeaderAllowance,
    MfmSourceError,
    MfmSourcePackage,
    MfmUnitCostBracket,
    MfmUnitCostRow,
    MfmUnitRecord,
    parse_mfm_faction_html,
    parse_mfm_index_html,
    parse_mfm_version_html,
    source_label_slug,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    mfm_2026_07,
    mfm_2026_10,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.mfm_2026_10._artifacts import (
    mfm_faction_payload_from_json_bytes,
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


def test_current_mfm_reproduces_all_checked_official_pages_and_review() -> None:
    root = Path(__file__).resolve().parents[3]
    sources = json.loads((root / "data/source_manifests/mfm_2026_10_sources.json").read_text())
    capture_root = root / "data/source_audits/mfm_2026_10"
    pages = {
        row["source_id"]: gzip.decompress(
            (capture_root / f"{row['source_id']}.html.gz").read_bytes()
        )
        for row in sources["captures"]
    }
    assert len(pages) == 29
    assert sources["inaccessible_sources"] == []
    for row in sources["captures"]:
        assert hashlib.sha256(pages[row["source_id"]]).hexdigest() == row["sha256"]
        assert parse_mfm_version_html(pages[row["source_id"]].decode()) == "v1.6"
    factions = parse_mfm_index_html(pages["index"].decode())
    for faction in factions:
        if faction.faction_id in mfm_2026_10.EXCLUDED_FACTION_IDS:
            continue
        actual = parse_mfm_faction_html(
            html=pages[faction.faction_id].decode(),
            faction=faction,
            source_package_id=mfm_2026_10.SOURCE_PACKAGE_ID,
        )
        assert actual == mfm_2026_10.faction_record(faction.faction_id)
    assert mfm_2026_10.supported_faction_ids() == mfm_2026_07.supported_faction_ids()
    assert mfm_2026_07.SOURCE_PAYLOAD_CHECKSUM_SHA256 == (
        "2232872565be8652618da1152e6ddb875d8dff2bc74d1e2dcd54d1f16f8cf281"
    )
    assert build_current_review_payload() == json.loads(
        (root / "data/source_manifests/mfm_2026_10_review.json").read_text()
    )
    assert mfm_2026_10.source_package().source_payload_checksum_sha256() == (
        mfm_2026_10.SOURCE_PAYLOAD_CHECKSUM_SHA256
    )


def _current_mfm_catalog(
    catalog: ArmyCatalog,
    *,
    faction: str,
    unit: str,
    detachment: str,
    enhancement: str | None = None,
) -> ArmyCatalog:
    sheet = replace(catalog.datasheet_by_id(LEADER), name=unit, attachment_eligibilities=())
    enhancements = (
        () if enhancement is None else (replace(catalog.enhancements[0], name=enhancement),)
    )
    return replace(
        catalog,
        factions=(replace(catalog.factions[0], name=faction),),
        datasheets=(sheet,),
        enhancements=enhancements,
        detachments=(
            replace(
                catalog.detachments[0],
                name=detachment,
                unit_datasheet_ids=(LEADER,),
                enhancement_ids=tuple(e.enhancement_id for e in enhancements),
            ),
        ),
    )


def test_current_mfm_default_prices_repeated_units_and_detachment_disposition(
    section25_catalog: ArmyCatalog,
) -> None:
    catalog = _current_mfm_catalog(
        section25_catalog,
        faction="Adepta Sororitas",
        unit="Castigator",
        detachment="Hallowed Martyrs",
    )
    units = tuple(selection(catalog, f"tank-{i}") for i in range(3))
    roster = request(catalog, units=units)
    old = calculate_mfm_army_points(
        catalog=catalog, request=roster, source_package=mfm_2026_07.source_package()
    )
    current = calculate_mfm_army_points(catalog=catalog, request=roster)
    assert [line.total_points for line in old.unit_lines] == [165, 165, 175]
    assert [line.total_points for line in current.unit_lines] == [165, 165, 185]
    assert all("gw-11e-mfm-2026-10:" in line.source_ids[0] for line in current.unit_lines)
    overlaid = catalog_with_mfm_points(catalog=catalog, faction_id=catalog.factions[0].faction_id)
    assert overlaid.detachments[0].detachment_point_cost == 3
    assert overlaid.detachments[0].force_disposition_ids == ("priority-assets", "take-and-hold")
    historical = catalog_with_mfm_points(
        catalog=catalog,
        faction_id=catalog.factions[0].faction_id,
        source_package=mfm_2026_07.source_package(),
    )
    assert historical.detachments[0].force_disposition_ids == ("priority-assets",)
    legal_roster = replace(
        roster, unit_selections=units[:1], unit_points=current.roster_unit_point_values()[:1]
    )
    for disposition in ("take-and-hold", "priority-assets"):
        assert (
            muster_army(
                catalog=overlaid,
                request=replace(
                    legal_roster,
                    force_disposition_id=disposition,
                ),
            ).army_id
            == roster.army_id
        )
    with pytest.raises(ArmyMusteringError, match="detachment selection is invalid"):
        muster_army(
            catalog=overlaid,
            request=replace(
                legal_roster,
                force_disposition_id="purge-the-foe",
            ),
        )


def test_current_mfm_default_enhancement_points_reach_roster_total(
    section25_catalog: ArmyCatalog,
) -> None:
    catalog = _current_mfm_catalog(
        section25_catalog,
        faction="T'au Empire",
        unit="Hammerhead Gunship",
        detachment="Mont'ka",
        enhancement="Strike Swiftly",
    )
    unit = selection(catalog, "commander")
    roster = request(catalog, units=(unit,), assignments=(assignment(unit),))
    old = calculate_mfm_army_points(
        catalog=catalog, request=roster, source_package=mfm_2026_07.source_package()
    )
    current = calculate_mfm_army_points(catalog=catalog, request=roster)
    assert old.enhancement_lines[0].points == 35
    assert current.enhancement_lines[0].points == 45
    assert current.total_points == current.unit_lines[0].total_points + 45
    overlay = catalog_with_mfm_points(catalog=catalog, faction_id=catalog.factions[0].faction_id)
    assert overlay.enhancements[0].points == 45


def test_mfm_streamed_cards_keep_own_section_and_current_enhancement_rows() -> None:
    html = """
    <html><body><h3>DETACHMENTS</h3>
    <div class="flex flex-col space-y-1 m-1">
      <div class="flex flex-row justify-between px-1 py-0.5 text-white">
        <span>Example</span><span>2DP</span></div><div>TAKE AND HOLD</div>
      <div class="space-y-1"><div>ENHANCEMENTS</div><ul>
        <li><div><span>First</span><span>15 pts</span></div></li>
        <li><span>LEADER:</span><span>Example Unit</span></li>
        <li><div><span>Second</span><span>20 pts</span></div></li>
        <li><span>SUPPORT:</span><span>Example Unit</span></li>
      </ul></div></div>
    <h3>ULTRAMARINES</h3><template id="P:card"></template>
    <h3>WHITE SCARS</h3>
    <div hidden id="S:card"><div class="flex flex-col space-y-1 m-1">
      <div class="px-1 py-0.5 font-bold text-xl text-white">Example Unit</div>
      <div class="space-y-1"><div>YOUR UNIT COSTS</div><ul>
        <li><span>1 model</span><template id="P:cost"></template></li>
      </ul></div></div></div><div hidden id="S:cost"><span>50 pts</span></div>
    </body></html>
    """
    faction = MfmIndexFaction("space-marines", "Space Marines", "/en/space-marines")
    record = parse_mfm_faction_html(html=html, faction=faction, source_package_id="test-current")
    assert record.units[0].record_id == "ultramarines-example-unit"
    assert record.units[0].cost_brackets[0].rows[0].points == 50
    first, second = record.detachments[0].enhancements
    assert (first.points, second.points) == (15, 20)
    assert first.leader_allowance is not None
    assert first.leader_allowance.allowed_bodyguard_unit_ids == ("example-unit",)
    assert second.leader_allowance is None  # SUPPORT never becomes LEADER permission.
    assert second.support_allowance is not None
    assert second.support_allowance.allowed_bodyguard_unit_ids == ("example-unit",)
    legacy_html = html.replace(
        "<li><div><span>First</span><span>15 pts</span></div></li>",
        "<div><li><div><span>First</span><span>15 pts</span></div></li></div>",
    )
    legacy = parse_mfm_faction_html(
        html=legacy_html, faction=faction, source_package_id="test-current"
    )
    assert legacy == record
    with pytest.raises(MfmSourceError, match="unknown section heading"):
        parse_mfm_faction_html(
            html=html.replace("WHITE SCARS", "UNREVIEWED"),
            faction=faction,
            source_package_id="test-current",
        )
    excluded = parse_mfm_faction_html(
        html=html.replace("ULTRAMARINES", "LEGENDS")
        .replace("WHITE SCARS", "UNITS")
        .replace(
            "<h3>DETACHMENTS</h3>",
            "<h3>UNITS</h3>"
            + (
                '<div class="flex flex-col space-y-1 m-1">'
                '<div class="px-1 py-0.5 font-bold text-xl text-white">Permitted</div>'
                '<div class="space-y-1"><div>YOUR UNIT COSTS</div><ul>'
                "<li><span>1 model</span><span>20 pts</span></li></ul></div></div>"
                "<h3>DETACHMENTS</h3>"
            ),
        ),
        faction=faction,
        source_package_id="test-current",
    )
    assert [unit.unit_id for unit in excluded.units] == ["permitted"]


def test_current_mfm_new_wargear_surcharge_prices_selected_equipment(
    section25_catalog: ArmyCatalog,
) -> None:
    catalog = _current_mfm_catalog(
        section25_catalog,
        faction="Space Marines",
        unit="Impulsor",
        detachment="Gladius Task Force",
    )
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(wargear, name="Orbital comms array")
            if wargear.wargear_id == "core-leader-blade"
            else wargear
            for wargear in catalog.wargear
        ),
    )
    roster = request(catalog)
    historical = calculate_mfm_army_points(
        catalog=catalog, request=roster, source_package=mfm_2026_07.source_package()
    )
    current = calculate_mfm_army_points(catalog=catalog, request=roster)
    assert historical.unit_lines[0].wargear_points == 0
    assert current.unit_lines[0].wargear_points == 10
    assert current.total_points == current.unit_lines[0].base_points + 10


def test_current_mfm_detachment_cost_replaces_previous_charge(
    section25_catalog: ArmyCatalog,
) -> None:
    catalog = _current_mfm_catalog(
        section25_catalog,
        faction="Adeptus Mechanicus",
        unit="Belisarius Cawl",
        detachment="Cohort Cybernetica",
    )
    historical = catalog_with_mfm_points(
        catalog=catalog,
        faction_id=catalog.factions[0].faction_id,
        source_package=mfm_2026_07.source_package(),
    )
    current = catalog_with_mfm_points(catalog=catalog, faction_id=catalog.factions[0].faction_id)
    assert historical.detachments[0].detachment_point_cost == 2
    assert current.detachments[0].detachment_point_cost == 1
    assert current.detachments[0].force_disposition_ids == ("take-and-hold",)


@pytest.mark.parametrize("support", [False, True])
def test_current_mfm_new_attachment_permissions_reach_real_mustering(
    section25_catalog: ArmyCatalog,
    support: bool,
) -> None:
    base = section25_catalog
    faction = "Adeptus Mechanicus" if support else "Adepta Sororitas"
    commander = "Belisarius Cawl" if support else "Canoness with Jump Pack"
    body_name = "Kastelan Robots" if support else "Seraphim Squad"
    sheets = [
        replace(base.datasheet_by_id(LEADER), name=commander),
        replace(base.datasheet_by_id(BODY), name=body_name),
    ]
    if support:
        sheets.append(replace(base.datasheet_by_id(SUPPORT), name="Cybernetica Datasmith"))
    else:
        sheets.append(
            replace(base.datasheet_by_id(BODY), datasheet_id="zephyrim", name="Zephyrim Squad")
        )
    catalog = replace(
        base,
        factions=(replace(base.factions[0], name=faction),),
        datasheets=tuple(sheets),
        detachments=(
            replace(base.detachments[0], unit_datasheet_ids=tuple(d.datasheet_id for d in sheets)),
        ),
    )
    units = (
        selection(catalog, "commander"),
        selection(catalog, "body", BODY),
        *((selection(catalog, "support", SUPPORT),) if support else ()),
    )
    roster = replace(
        request(catalog, units=units),
        attachment_declarations=(
            AttachmentDeclaration("support" if support else "commander", "body"),
        ),
    )
    historical = catalog_with_mfm_attachment_allowances(
        catalog=catalog,
        faction_id=catalog.factions[0].faction_id,
        source_package=mfm_2026_07.source_package(),
    )
    with pytest.raises(ArmyMusteringError):
        muster_army(catalog=historical, request=roster)
    current = catalog_with_mfm_attachment_allowances(
        catalog=catalog,
        faction_id=catalog.factions[0].faction_id,
    )
    army = muster_army(catalog=current, request=roster)
    attached = army.attached_units[0]
    assert attached.bodyguard_unit_instance_id == "s25-army:body"
    assert (
        attached.support_unit_instance_ids if support else attached.leader_unit_instance_ids
    ) == ("s25-army:support" if support else "s25-army:commander",)


def test_current_mfm_v3_rejects_missing_or_inconsistent_dispositions() -> None:
    payload = mfm_2026_10.faction_record("adepta-sororitas").to_payload()
    detachment = payload["detachments"][0]
    del detachment["force_disposition_ids"]
    with pytest.raises(MfmSourceError, match="artifact is invalid"):
        mfm_faction_payload_from_json_bytes(json.dumps(payload).encode())
    for values in ([], ["other-disposition"], ["take-and-hold", "take-and-hold"]):
        detachment["force_disposition_ids"] = values
        with pytest.raises(MfmSourceError):
            MfmDetachmentRecord.from_payload(detachment)
    murdermind = mfm_2026_10.faction_record("necrons").enhancement_by_id("murdermind")
    assert murdermind.leader_allowance is None
    assert murdermind.support_allowance is not None
    assert murdermind.support_allowance.allowed_bodyguard_unit_ids == (
        "lokhust-heavy-destroyers",
        "ophydian-destroyers",
        "skorpekh-destroyers",
        "lokhust-destroyers",
    )
