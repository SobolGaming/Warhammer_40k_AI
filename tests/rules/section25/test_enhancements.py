"""Upgrade and ordinary assignments through real physical roster consumers."""

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
    ArmyDefinition,
    ArmyMusteringError,
    muster_army,
    validate_roster_legality,
)
from warhammer40k_core.engine.enhancement_bearers import enhancement_bearer_unit
from warhammer40k_core.engine.list_validation import AttachmentDeclaration


@pytest.mark.parametrize("copies", [1, 2, 3, 4])
def test_upgrade_copies_pay_each_count_once_and_stop_at_three(
    section25_catalog: ArmyCatalog, copies: int
) -> None:
    c = section25_catalog
    units = (selection(c, "commander"), *(selection(c, f"body-{i}", BODY) for i in range(copies)))
    r = request(
        c,
        units=units,
        assignments=(assignment(units[0]), *(assignment(u, UPGRADE) for u in units[1:])),
    )
    # Exactly the points ceiling after paying every copy; only the Upgrade-copy cap can fail.
    r = replace(
        r,
        unit_points=(
            replace(r.unit_points[0], points=1000 - 10 - 20 * copies - 50 * copies),
            *r.unit_points[1:],
        ),
    )
    codes = {v.violation_code for v in validate_roster_legality(catalog=c, request=r).violations}
    assert codes == ({"upgrade_assignment_limit_exceeded"} if copies == 4 else set())
    if copies <= 3:
        army = muster_army(catalog=c, request=r)
        assert len(army.enhancement_assignments) == copies + 1
        assert army.detachment_selection.enhancement_ids == (ORDINARY[0], UPGRADE)
        assert {
            enhancement_bearer_unit(army, assignment=a).unit_instance_id
            for a in army.enhancement_assignments
        } == {u.unit_instance_id for u in army.units}
    too_many_points = replace(
        r,
        unit_points=(
            replace(r.unit_points[0], points=r.unit_points[0].points + 1),
            *r.unit_points[1:],
        ),
    )
    assert {
        v.violation_code
        for v in validate_roster_legality(catalog=c, request=too_many_points).violations
    } == codes | {"points_limit_exceeded"}


def test_ordinary_duplicate_and_two_different_enhancements_on_one_unit_are_rejected(
    section25_catalog: ArmyCatalog,
) -> None:
    c = section25_catalog
    units = (selection(c, "commander"), selection(c, "second"))
    valid = request(
        c, units=units, assignments=(assignment(units[0]), assignment(units[1], ORDINARY[1]))
    )
    assert muster_army(catalog=c, request=valid).roster_legality_report.is_legal
    repeated = replace(valid, enhancement_assignments=(assignment(units[0]), assignment(units[1])))
    assert {
        v.violation_code for v in validate_roster_legality(catalog=c, request=repeated).violations
    } == {"enhancement_repeated_assignment_forbidden"}
    with pytest.raises(ArmyMusteringError, match="multiple Enhancements"):
        replace(
            valid, enhancement_assignments=(assignment(units[0]), assignment(units[0], ORDINARY[1]))
        )


@pytest.mark.parametrize("epic", [False, True])
def test_attached_upgrade_belongs_to_bodyguard_and_cannot_stack_on_leader(
    section25_catalog: ArmyCatalog, epic: bool
) -> None:
    c = section25_catalog
    if epic:
        leader = c.datasheet_by_id(LEADER)
        leader = replace(
            leader,
            keywords=DatasheetKeywordSet(
                keywords=(*leader.keywords.keywords, "EPIC HERO"),
                faction_keywords=leader.keywords.faction_keywords,
            ),
        )
        c = replace(
            c, datasheets=tuple(leader if d.datasheet_id == LEADER else d for d in c.datasheets)
        )
    units = (selection(c, "commander"), selection(c, "body", BODY))
    r = request(c, units=units, assignments=(assignment(units[1], UPGRADE),))
    r = replace(r, attachment_declarations=(AttachmentDeclaration("commander", "body"),))
    army = muster_army(catalog=c, request=r)
    assert army.roster_legality_report.is_legal
    assert len(army.attached_units) == 1
    assert army.enhancement_assignments[0].target_unit_selection_id == "body"
    assert (
        enhancement_bearer_unit(army, assignment=army.enhancement_assignments[0]).unit_instance_id
        == "s25-army:body"
    )
    assert ArmyDefinition.from_payload(army.to_payload()).to_payload() == army.to_payload()
    both = replace(
        r,
        enhancement_assignments=(*r.enhancement_assignments, assignment(units[0])),
        detachment_selection=replace(
            r.detachment_selection, enhancement_ids=(UPGRADE, ORDINARY[0])
        ),
    )
    assert "attached_squad_enhancement_limit_exceeded" in {
        v.violation_code for v in validate_roster_legality(catalog=c, request=both).violations
    }
    if epic:
        direct = request(c, units=units, assignments=(assignment(units[0]),))
        assert {
            v.violation_code for v in validate_roster_legality(catalog=c, request=direct).violations
        } == {"epic_hero_enhancement_forbidden"}


@pytest.mark.parametrize("upgrade", [False, True])
def test_noncharacter_and_exact_model_bearer_boundary(
    section25_catalog: ArmyCatalog, upgrade: bool
) -> None:
    c = section25_catalog
    units = (selection(c, "commander"), selection(c, "body", BODY))
    r = request(
        c, units=units, assignments=(assignment(units[1], UPGRADE if upgrade else ORDINARY[0]),)
    )
    assert {
        v.violation_code for v in validate_roster_legality(catalog=c, request=r).violations
    } == (set() if upgrade else {"enhancement_character_required"})
    invalid = replace(
        r, enhancement_assignments=(replace(r.enhancement_assignments[0], model_index=99),)
    )
    assert "enhancement_invalid_model_selection" in {
        v.violation_code for v in validate_roster_legality(catalog=c, request=invalid).violations
    }
    with pytest.raises(ArmyMusteringError):
        muster_army(catalog=c, request=invalid)
