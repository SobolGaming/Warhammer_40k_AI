"""19.01 formation eligibility at its shared owner, no unrelated mustering."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_session import movement_session
from tests.support.section19_fixtures import AVENGERS, BODY, LORD, attached_scene
from warhammer40k_core.engine.army_mustering import ArmyMusteringError
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.roster_attachment_validation import resolve_attached_unit_formations
from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies
from warhammer40k_core.engine.unit_factory import UnitInstance


@pytest.mark.parametrize("target", [BODY, AVENGERS])
def test_native_leader_can_attach_only_to_its_structured_friendly_bodyguard(
    section19_definitions: Section02Definitions,
    target: str,
) -> None:
    d = section19_definitions
    s = attached_scene(d)
    request = next(
        r
        for r in movement_session(d, s.state).lifecycle.config.army_muster_requests
        if r.player_id == "owner"
    )
    request = replace(request, attachment_declarations=(AttachmentDeclaration("leader", "body"),))
    units = (d.unit(target, identity="body"), s.leader)
    sheets = {
        "body": d.package.army_catalog.datasheet_by_id(target),
        "leader": d.package.army_catalog.datasheet_by_id(LORD),
    }
    if target != BODY:
        before = tuple(u.to_payload() for u in units)
        with pytest.raises(ArmyMusteringError, match="not allowed"):
            resolve_attached_unit_formations(
                request=request, units=units, datasheets_by_selection_id=sheets
            )
        assert tuple(u.to_payload() for u in units) == before
        return
    resolved, formations = resolve_attached_unit_formations(
        request=request, units=units, datasheets_by_selection_id=sheets
    )
    assert len(formations) == 1
    f = formations[0]
    assert f.bodyguard_unit_instance_id == s.body.unit_instance_id
    assert f.leader_unit_instance_ids == (s.leader.unit_instance_id,)
    eligibility = sheets["leader"].attachment_eligibilities[0].targets[0]
    assert f.attachment_source_ids == eligibility.source_ids
    own = s.state.army_definition_for_player("owner")
    assert own is not None
    army = replace(own, units=resolved, attached_units=formations)
    views = rules_unit_views_from_armies(armies=(army,))
    assert len(views) == 1
    assert len(views[0].alive_models()) == 6


@pytest.mark.parametrize("invalid", ["enemy_source", "enemy_target", "no_role", "two_leaders"])
def test_formation_rejects_nonfriendly_or_unpermitted_components_without_mutating_units(
    section19_definitions: Section02Definitions,
    invalid: str,
) -> None:
    d = section19_definitions
    s = attached_scene(d)
    req = next(
        r
        for r in movement_session(d, s.state).lifecycle.config.army_muster_requests
        if r.player_id == "owner"
    )
    decl = AttachmentDeclaration(
        "enemy" if invalid == "enemy_source" else "body" if invalid == "no_role" else "leader",
        "enemy" if invalid == "enemy_target" else "leader" if invalid == "no_role" else "body",
    )
    units: tuple[UnitInstance, ...] = (s.body, s.leader)
    sheets = {
        "body": d.package.army_catalog.datasheet_by_id(BODY),
        "leader": d.package.army_catalog.datasheet_by_id(LORD),
    }
    declarations: tuple[AttachmentDeclaration, ...] = (decl,)
    if invalid == "two_leaders":
        units = (*units, d.unit(LORD, identity="second"))
        sheets["second"] = sheets["leader"]
        declarations = (*declarations, AttachmentDeclaration("second", "body"))
    req = replace(req, attachment_declarations=declarations)
    before = tuple(u.to_payload() for u in units)
    with pytest.raises(
        ArmyMusteringError, match=r"not mustered|no attachment eligibility|exceeds one"
    ):
        resolve_attached_unit_formations(
            request=req, units=units, datasheets_by_selection_id=sheets
        )
    assert tuple(u.to_payload() for u in units) == before
