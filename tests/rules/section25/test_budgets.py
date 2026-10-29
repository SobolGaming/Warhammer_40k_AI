"""Inclusive source-table limits through the actual roster consumer."""

from dataclasses import replace

import pytest

from tests.support.section25_fixtures import (
    BODY,
    LEADER,
    ORDINARY,
    UPGRADE,
    assignment,
    request,
    selection,
)
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import DatasheetKeywordSet
from warhammer40k_core.engine.army_mustering import (
    ArmyMusteringError,
    DedicatedTransportCapacityProfile,
    DedicatedTransportManifest,
    muster_army,
    validate_roster_legality,
)
from warhammer40k_core.engine.list_validation import BattleSize
from warhammer40k_core.engine.roster_points import RosterUnitPointValue


@pytest.mark.parametrize(
    ("size", "cap"), [(BattleSize.INCURSION, 1000), (BattleSize.STRIKE_FORCE, 2000)]
)
def test_points_exact_cap_and_one_over_includes_each_enhancement(
    section25_catalog: ArmyCatalog,
    size: BattleSize,
    cap: int,
) -> None:
    c = section25_catalog
    u = selection(c, "commander")
    r = request(c, size=size, units=(u,), assignments=(assignment(u),))
    r = replace(
        r, unit_points=(RosterUnitPointValue("commander", cap - 10, "constructed:s25:cap"),)
    )
    before = r.to_payload()
    army = muster_army(catalog=c, request=r)
    assert army.roster_legality_report.is_legal
    bad = replace(r, unit_points=(replace(r.unit_points[0], points=cap - 9),))
    report = validate_roster_legality(catalog=c, request=bad)
    assert {v.violation_code for v in report.violations} == {"points_limit_exceeded"}
    with pytest.raises(ArmyMusteringError, match="RosterLegalityReport"):
        muster_army(catalog=c, request=bad)
    assert r.to_payload() == before


@pytest.mark.parametrize(
    ("size", "base_cap"), [(BattleSize.INCURSION, 2), (BattleSize.STRIKE_FORCE, 3)]
)
@pytest.mark.parametrize(
    "keywords",
    [(), ("BATTLELINE",), ("DEDICATED TRANSPORT",), ("BATTLELINE", "DEDICATED TRANSPORT")],
)
def test_datasheet_limit_counts_physical_units_and_category_exception_once(
    section25_catalog: ArmyCatalog,
    size: BattleSize,
    base_cap: int,
    keywords: tuple[str, ...],
) -> None:
    c = section25_catalog
    body = c.datasheet_by_id(BODY)
    body = replace(
        body,
        keywords=DatasheetKeywordSet(
            keywords=(
                "INFANTRY",
                *keywords,
                *(("TRANSPORT",) if "DEDICATED TRANSPORT" in keywords else ()),
            ),
            faction_keywords=body.keywords.faction_keywords,
        ),
    )
    c = replace(c, datasheets=tuple(body if d.datasheet_id == BODY else d for d in c.datasheets))
    cap = base_cap * (2 if keywords else 1)
    units = (selection(c, "commander"), *(selection(c, f"body-{i}", BODY) for i in range(cap)))
    r = request(c, size=size, units=units)
    if "DEDICATED TRANSPORT" in keywords:
        r = replace(
            r,
            dedicated_transport_manifests=tuple(
                DedicatedTransportManifest(
                    transport_unit_selection_id=u.unit_selection_id,
                    embarked_unit_selection_ids=(),
                    capacity_profile=DedicatedTransportCapacityProfile(BODY, 10),
                    source_id=f"constructed:s25:empty:{u.unit_selection_id}",
                )
                for u in units[1:]
            ),
        )
    assert muster_army(catalog=c, request=r).roster_legality_report.is_legal
    extra = selection(c, "extra", BODY)
    bad = replace(
        r,
        unit_selections=(*units, extra),
        unit_points=(*r.unit_points, RosterUnitPointValue("extra", 50, "constructed:s25:extra")),
    )
    if "DEDICATED TRANSPORT" in keywords:
        bad = replace(
            bad,
            dedicated_transport_manifests=(
                *r.dedicated_transport_manifests,
                replace(
                    r.dedicated_transport_manifests[0],
                    transport_unit_selection_id="extra",
                    source_id="constructed:s25:empty:extra",
                ),
            ),
        )
    violations = validate_roster_legality(catalog=c, request=bad).violations
    assert {v.violation_code for v in violations} == {"unit_limit_exceeded"}
    assert violations[0].source_id is not None
    assert violations[0].source_id.endswith(BODY)


@pytest.mark.parametrize("size", [BattleSize.INCURSION, BattleSize.STRIKE_FORCE])
def test_epic_hero_cap_overrides_even_battleline_exception(
    section25_catalog: ArmyCatalog, size: BattleSize
) -> None:
    c = section25_catalog
    leader = c.datasheet_by_id(LEADER)
    leader = replace(
        leader,
        keywords=DatasheetKeywordSet(
            keywords=("CHARACTER", "EPIC HERO", "BATTLELINE"),
            faction_keywords=leader.keywords.faction_keywords,
        ),
    )
    c = replace(
        c, datasheets=tuple(leader if d.datasheet_id == LEADER else d for d in c.datasheets)
    )
    r = request(c, size=size)
    assert muster_army(catalog=c, request=r).roster_legality_report.is_legal
    two = request(c, size=size, units=(selection(c, "commander"), selection(c, "duplicate")))
    assert {
        v.violation_code for v in validate_roster_legality(catalog=c, request=two).violations
    } == {"epic_hero_not_unique"}


@pytest.mark.parametrize(("size", "cap"), [(BattleSize.INCURSION, 2), (BattleSize.STRIKE_FORCE, 4)])
def test_enhancement_budget_counts_distinct_ordinary_and_one_upgrade_kind(
    section25_catalog: ArmyCatalog,
    size: BattleSize,
    cap: int,
) -> None:
    c = section25_catalog
    leader = c.datasheet_by_id(LEADER)
    extra_sheets = tuple(
        replace(leader, datasheet_id=f"s25-character-{i}", name=f"Analytical character {i}")
        for i in range(cap + 1)
    )
    c = replace(
        c,
        datasheets=(*c.datasheets, *extra_sheets),
        detachments=(
            replace(
                c.detachments[0],
                unit_datasheet_ids=(
                    *c.detachments[0].unit_datasheet_ids,
                    *(d.datasheet_id for d in extra_sheets),
                ),
            ),
        ),
    )
    units = tuple(selection(c, f"bearer-{i}", d.datasheet_id) for i, d in enumerate(extra_sheets))
    assignments = tuple(assignment(u, ORDINARY[i]) for i, u in enumerate(units[:cap]))
    r = request(c, size=size, units=units, assignments=assignments)
    assert muster_army(catalog=c, request=r).roster_legality_report.is_legal
    bad = replace(
        r,
        enhancement_assignments=(*assignments, assignment(units[-1], UPGRADE)),
        detachment_selection=replace(
            r.detachment_selection, enhancement_ids=(*ORDINARY[:cap], UPGRADE)
        ),
    )
    assert {
        v.violation_code for v in validate_roster_legality(catalog=c, request=bad).violations
    } == {"enhancement_limit_exceeded"}
