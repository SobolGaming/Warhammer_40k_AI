"""Selected inventory, canonical identities and simultaneous construction rules."""

from dataclasses import replace

import pytest

from tests.support.section25_fixtures import BODY, ORDINARY, request, selection
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.construction_constraints import (
    ConstructionConstraint,
    ConstructionConstraintKind,
    DatasheetUnitSelector,
    DetachmentSelector,
)
from warhammer40k_core.core.detachment import DetachmentCatalogError
from warhammer40k_core.engine.army_mustering import (
    ArmyMusteringError,
    muster_army,
    validate_roster_legality,
)
from warhammer40k_core.engine.list_validation import (
    BattleSize,
    DetachmentSelection,
    validate_detachment_selection,
)
from warhammer40k_core.engine.list_validation_errors import ListValidationError


@pytest.mark.parametrize(
    ("costs", "legal"),
    [((2,), True), ((3,), True), ((4,), False), ((1, 1), True), ((2, 1), False), ((3, 0), False)],
)
def test_incursion_three_dp_exception_requires_sole_detachment(
    section25_catalog: ArmyCatalog, costs: tuple[int, ...], legal: bool
) -> None:
    c = section25_catalog
    if any(cost < 1 or cost > 3 for cost in costs):
        with pytest.raises(DetachmentCatalogError, match="between 1 and 3"):
            replace(
                c.detachments[0],
                detachment_point_cost=next(cost for cost in costs if cost < 1 or cost > 3),
            )
        return
    detachments = tuple(
        replace(
            c.detachments[0],
            detachment_id=f"s25-{i}",
            canonical_detachment_id=f"s25-{i}",
            detachment_point_cost=cost,
        )
        for i, cost in enumerate(costs)
    )
    c = replace(c, detachments=detachments)
    selected = DetachmentSelection(
        detachments[0].faction_id, tuple(d.detachment_id for d in detachments)
    )
    if legal:
        _, resolved = validate_detachment_selection(
            catalog=c, selection=selected, battle_size=BattleSize.INCURSION
        )
        assert {d.detachment_id for d in resolved} == set(selected.detachment_ids)
    else:
        with pytest.raises(ListValidationError, match="Detachment Points"):
            validate_detachment_selection(
                catalog=c, selection=selected, battle_size=BattleSize.INCURSION
            )


def test_alias_faction_and_selected_inventory_boundaries(section25_catalog: ArmyCatalog) -> None:
    c = section25_catalog
    owner = c.detachments[0]
    alias = replace(owner, detachment_id="s25-alias", name="Different public name")
    c = replace(c, detachments=(owner, alias))
    with pytest.raises(ListValidationError, match="same detachment"):
        validate_detachment_selection(
            catalog=c,
            selection=DetachmentSelection(
                owner.faction_id, (owner.detachment_id, alias.detachment_id)
            ),
        )
    foreign = replace(alias, faction_id="other-faction", canonical_detachment_id="s25-foreign")
    c = replace(
        c,
        detachments=(owner, foreign),
        factions=(*c.factions, replace(c.factions[0], faction_id="other-faction")),
    )
    with pytest.raises(ListValidationError, match="does not belong"):
        validate_detachment_selection(
            catalog=c, selection=DetachmentSelection(owner.faction_id, (foreign.detachment_id,))
        )
    selected = DetachmentSelection(
        owner.faction_id, (owner.detachment_id,), (ORDINARY[0],), owner.stratagem_ids
    )
    faction, grants = validate_detachment_selection(catalog=c, selection=selected)
    assert faction.faction_id == owner.faction_id
    assert grants[0].force_disposition_ids == owner.force_disposition_ids
    assert ORDINARY[0] in grants[0].enhancement_ids
    assert grants[0].stratagem_ids == owner.stratagem_ids
    stripped = replace(c, detachments=(replace(owner, enhancement_ids=()),))
    with pytest.raises(ListValidationError, match="not allowed"):
        validate_detachment_selection(catalog=stripped, selection=selected)


@pytest.mark.parametrize(
    "kind", [ConstructionConstraintKind.REQUIRED_UNIT, ConstructionConstraintKind.PROHIBITED_UNIT]
)
def test_required_and_prohibited_units_enforced_by_report_and_muster(
    section25_catalog: ArmyCatalog, kind: ConstructionConstraintKind
) -> None:
    c = section25_catalog
    rule = ConstructionConstraint(
        "s25:constraint",
        "constructed:s25:restriction",
        kind,
        unit_selector=DatasheetUnitSelector(datasheet_ids=(BODY,)),
    )
    c = replace(c, detachments=(replace(c.detachments[0], construction_constraints=(rule,)),))
    with_body = request(c, units=(selection(c, "commander"), selection(c, "body", BODY)))
    without = request(c)
    good, bad = (
        (with_body, without)
        if kind is ConstructionConstraintKind.REQUIRED_UNIT
        else (without, with_body)
    )
    assert muster_army(catalog=c, request=good).roster_legality_report.is_legal
    bad = replace(bad, roster_legality_required=False)
    violations = validate_roster_legality(catalog=c, request=bad).violations
    assert {v.violation_code for v in violations} == {kind.value}
    assert violations[0].source_id == rule.source_id
    with pytest.raises(ArmyMusteringError, match="construction"):
        muster_army(catalog=c, request=bad)


@pytest.mark.parametrize("required", [False, True])
def test_required_and_prohibited_other_detachments_use_canonical_owner(
    section25_catalog: ArmyCatalog, required: bool
) -> None:
    c = section25_catalog
    owner = c.detachments[0]
    other = replace(owner, detachment_id="s25-other", canonical_detachment_id="s25-other-canonical")
    kind = (
        ConstructionConstraintKind.REQUIRED_OTHER_DETACHMENT
        if required
        else ConstructionConstraintKind.PROHIBITED_OTHER_DETACHMENT
    )
    rule = ConstructionConstraint(
        "s25:other",
        "constructed:s25:other",
        kind,
        detachment_selector=DetachmentSelector(detachment_ids=(other.canonical_detachment_id,)),
    )
    owner = replace(owner, construction_constraints=(rule,))
    c = replace(c, detachments=(owner, other))
    r = request(c)
    with_other = replace(
        r,
        detachment_selection=replace(
            r.detachment_selection, detachment_ids=(owner.detachment_id, other.detachment_id)
        ),
    )
    good, bad = (with_other, r) if required else (r, with_other)
    assert muster_army(catalog=c, request=good).roster_legality_report.is_legal
    assert {
        v.violation_code for v in validate_roster_legality(catalog=c, request=bad).violations
    } == {kind.value}
