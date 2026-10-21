"""Native Leader eligibility plus explicit Core Support role at formation owner."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.support.section03_session import movement_session
from tests.support.section24_fixtures import BODY, LORD, with_core
from warhammer40k_core.core.attachment_eligibility import AttachmentRole
from warhammer40k_core.engine.army_mustering import ArmyMusteringError
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.roster_attachment_validation import resolve_attached_unit_formations
from warhammer40k_core.engine.unit_factory import UnitInstance


@pytest.mark.parametrize("second_support", [False, True])
def test_default_bodyguard_can_have_one_leader_and_one_support_but_not_two_supports(
    section24_definitions: Section02Definitions, second_support: bool
) -> None:
    d = section24_definitions
    body = d.unit(BODY, identity="body")
    leader = d.unit(LORD, identity="leader")
    support = with_core(d.unit(LORD, identity="support"), "support")
    sheet = d.package.army_catalog.datasheet_by_id(LORD)
    # Explicit Core role transplant retaining the native eligible bodyguard;
    # this does not admit Lord Exultant as a native Support provider.
    support_sheet = replace(
        sheet,
        abilities=support.datasheet_abilities,
        attachment_eligibilities=tuple(
            replace(e, role=AttachmentRole.SUPPORT) for e in sheet.attachment_eligibilities
        ),
    )
    state = native_state(d, body, enemy=d.unit(LORD, army_id="enemy", identity="target"))
    request = next(
        r
        for r in movement_session(d, state).lifecycle.config.army_muster_requests
        if r.player_id == "owner"
    )
    declarations: tuple[AttachmentDeclaration, ...] = (
        AttachmentDeclaration("leader", "body"),
        AttachmentDeclaration("support", "body"),
    )
    units: tuple[UnitInstance, ...] = (body, leader, support)
    sheets = {
        "body": d.package.army_catalog.datasheet_by_id(BODY),
        "leader": sheet,
        "support": support_sheet,
    }
    if second_support:
        units = (*units, with_core(d.unit(LORD, identity="second"), "support"))
        sheets["second"] = support_sheet
        declarations = (*declarations, AttachmentDeclaration("second", "body"))
    request = replace(request, attachment_declarations=declarations)
    before = tuple(u.to_payload() for u in units)
    if second_support:
        with pytest.raises(ArmyMusteringError, match="one Leader or one Support"):
            resolve_attached_unit_formations(
                request=request, units=units, datasheets_by_selection_id=sheets
            )
    else:
        _, formations = resolve_attached_unit_formations(
            request=request, units=units, datasheets_by_selection_id=sheets
        )
        (formation,) = formations
        assert formation.leader_unit_instance_ids == (leader.unit_instance_id,)
        assert formation.support_unit_instance_ids == (support.unit_instance_id,)
    assert tuple(u.to_payload() for u in units) == before
