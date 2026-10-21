"""Model-owned Warlord grants and mustering-only attachment obligations."""

from dataclasses import replace

import pytest

from tests.support.section25_fixtures import (
    BODY,
    LEADER,
    SUPPORT,
    assignment,
    request,
    selection,
)
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    MUSTERING_WARLORD_FORBIDDEN,
    MUSTERING_WARLORD_REQUIRED,
    MUSTERING_WARLORD_RULE_KEY,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusteringError,
    ArmyMusterRequest,
    muster_army,
    validate_roster_legality,
)
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection


@pytest.mark.parametrize("index", [1, 2])
def test_exact_selected_character_gets_warlord_and_bearer_record(
    section25_catalog: ArmyCatalog, index: int
) -> None:
    c = section25_catalog
    leader = c.datasheet_by_id(LEADER)
    leader = replace(
        leader, composition=tuple(replace(p, max_models=2) for p in leader.composition)
    )
    c = replace(
        c, datasheets=tuple(leader if d.datasheet_id == LEADER else d for d in c.datasheets)
    )
    unit = replace(
        selection(c, "commander"),
        model_profile_selections=(
            ModelProfileSelection(leader.composition[0].model_profile_id, 2),
        ),
    )
    r = request(c, units=(unit,), assignments=(replace(assignment(unit), model_index=index),))
    assert r.warlord_selection is not None
    r = replace(r, warlord_selection=replace(r.warlord_selection, model_index=index))
    army = muster_army(catalog=c, request=r)
    assert ["WARLORD" in m.keywords for m in army.units[0].own_models] == [index == 1, index == 2]
    assert army.enhancement_assignments[0].model_index == index
    assert ArmyMusterRequest.from_payload(r.to_payload()) == r
    assert ArmyDefinition.from_payload(army.to_payload()).to_payload() == army.to_payload()
    assert r.warlord_selection is not None
    bad = replace(r, warlord_selection=replace(r.warlord_selection, model_index=3))
    assert {
        v.violation_code for v in validate_roster_legality(catalog=c, request=bad).violations
    } == {"warlord_invalid_model_selection"}
    diagnostic = muster_army(catalog=c, request=replace(bad, roster_legality_required=False))
    assert all("WARLORD" not in m.keywords for u in diagnostic.units for m in u.own_models)


@pytest.mark.parametrize("forbid_selected", [False, True])
def test_mandatory_candidates_and_prohibition_precedence(
    section25_catalog: ArmyCatalog, forbid_selected: bool
) -> None:
    c = section25_catalog
    leader = c.datasheet_by_id(LEADER)
    required = DatasheetAbilityDescriptor(
        ability_id="s25-required",
        name="Analytical requirement",
        source_id="constructed:s25:required",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="Supported mustering input",
        timing_tags=("mustering", "warlord"),
        rule_ir_payload={MUSTERING_WARLORD_RULE_KEY: MUSTERING_WARLORD_REQUIRED},
    )
    forbidden = replace(
        required,
        ability_id="s25-forbidden",
        source_id="constructed:s25:forbidden",
        rule_ir_payload={MUSTERING_WARLORD_RULE_KEY: MUSTERING_WARLORD_FORBIDDEN},
    )
    mandatory = replace(
        leader,
        datasheet_id="s25-mandatory",
        name="Analytical mandatory",
        abilities=(*leader.abilities, required, *((forbidden,) if forbid_selected else ())),
    )
    c = replace(c, datasheets=(*c.datasheets, mandatory))
    units = (selection(c, "commander", mandatory.datasheet_id), selection(c, "ordinary"))
    r = request(c, units=units)
    codes = {v.violation_code for v in validate_roster_legality(catalog=c, request=r).violations}
    assert codes == ({"warlord_forbidden"} if forbid_selected else set())
    assert r.warlord_selection is not None
    other = replace(r, warlord_selection=replace(r.warlord_selection, unit_selection_id="ordinary"))
    other_codes = {
        v.violation_code for v in validate_roster_legality(catalog=c, request=other).violations
    }
    assert other_codes == (set() if forbid_selected else {"supreme_commander_warlord_required"})
    legal = other if forbid_selected else r
    assert muster_army(catalog=c, request=legal).roster_legality_report.is_legal


def test_support_requires_permitted_bodyguard_and_leader_can_stand_alone(
    section25_catalog: ArmyCatalog,
) -> None:
    c = section25_catalog
    units = (
        selection(c, "commander"),
        selection(c, "body", BODY),
        selection(c, "support", SUPPORT),
    )
    r = request(c, units=units)
    assert {
        v.violation_code for v in validate_roster_legality(catalog=c, request=r).violations
    } == {"attachment_declaration_invalid"}
    with pytest.raises(ArmyMusteringError, match="Support units must be declared"):
        muster_army(catalog=c, request=r)
    legal = replace(r, attachment_declarations=(AttachmentDeclaration("support", "body"),))
    army = muster_army(catalog=c, request=legal)
    assert army.attached_units[0].support_unit_instance_ids == ("s25-army:support",)
    assert army.attached_units[0].leader_unit_instance_ids == ()
    assert "ATTACHED_UNIT" not in army.unit_by_id("s25-army:commander").keywords
    wrong = replace(r, attachment_declarations=(AttachmentDeclaration("support", "commander"),))
    assert {
        v.violation_code for v in validate_roster_legality(catalog=c, request=wrong).violations
    } == {"attachment_declaration_invalid"}
