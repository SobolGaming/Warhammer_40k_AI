"""02.05/02.05.01; exact matching and casualty FAQ live with their owner."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import (
    AVENGERS,
    INFRACTORS,
    LORD_EXULTANT,
    Section02Definitions,
)
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.rule_target_resolution import unit_has_required_keywords
from warhammer40k_core.engine.rules_units import RulesUnitComponent, RulesUnitView
from warhammer40k_core.rules.rule_keyword_sequences import keyword_sequence_tokens


@pytest.mark.parametrize(
    ("keywords", "expected"),
    [
        (("AELDARI",), True),
        (("ASURYANI",), True),
        (("AELDARI", "INFANTRY"), True),
        (("AELDARI", "VEHICLE"), False),
        (("DIRE AVENGERS",), True),
        (("AVENGERS",), False),
        (("DIRE",), False),
    ],
)
def test_02_05_faction_and_other_keywords_share_exact_conjunctive_matching(
    section02_definitions: Section02Definitions,
    keywords: tuple[str, ...],
    expected: bool,
) -> None:
    unit = section02_definitions.unit(AVENGERS)
    assert (
        unit_has_required_keywords(
            unit_keywords=unit.keywords,
            faction_keywords=unit.faction_keywords,
            required_keywords=keywords,
            name_keywords=unit.datasheet_name_keywords,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("text", "tokens"),
    [
        ("AELDARI INFANTRY", ("AELDARI", "INFANTRY")),
        ("ASPECT WARRIORS", ("ASPECT_WARRIOR",)),
        ("GRENADES", ("GRENADES",)),
    ],
)
def test_02_05_01_declared_keyword_numbers_preserve_multiword_identity(
    section02_definitions: Section02Definitions,
    text: str,
    tokens: tuple[str, ...],
) -> None:
    unit = section02_definitions.unit(AVENGERS)
    assert keyword_sequence_tokens(text, source_keyword_sequence_parts=unit.keywords) == tokens


def test_02_05_01_real_attachment_keeps_model_keywords_and_removes_casualty_contribution(
    section02_definitions: Section02Definitions,
) -> None:
    bodyguard = section02_definitions.unit(INFRACTORS, identity="bodyguard")
    leader = section02_definitions.unit(LORD_EXULTANT, identity="leader")
    source = section02_definitions.package.army_catalog.datasheet_by_id(LORD_EXULTANT)
    target = next(
        t
        for eligibility in source.attachment_eligibilities
        for t in eligibility.targets
        if t.bodyguard_datasheet_id == INFRACTORS
    )
    assert target.required_wargear_ids == ()
    formation = AttachedUnitFormation(
        attached_unit_instance_id="attached-unit:section02:bodyguard",
        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
        leader_unit_instance_ids=(leader.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
        ),
        source_id=target.source_ids[0],
        attachment_source_ids=target.source_ids,
    )
    view = RulesUnitView(
        formation.attached_unit_instance_id,
        "owner",
        (RulesUnitComponent(bodyguard, "bodyguard"), RulesUnitComponent(leader, "leader")),
        formation,
    )
    assert "CHARACTER" in view.keywords
    assert "CHARACTER" not in bodyguard.own_models[0].keywords
    assert "CHARACTER" in leader.own_models[0].keywords
    assert set(view.keywords) == set(bodyguard.keywords) | set(leader.keywords)
    # A casualty fixture changes health only; source stats/keywords remain intact.
    casualty = replace(leader, own_models=(replace(leader.own_models[0], wounds_remaining=0),))
    after = replace(
        view,
        components=(
            RulesUnitComponent(bodyguard, "bodyguard"),
            RulesUnitComponent(casualty, "leader"),
        ),
    )
    assert "CHARACTER" not in after.keywords
    assert "LORD EXULTANT" not in after.keywords
    assert "EMPEROR'S CHILDREN" in after.faction_keywords
    # Section05 retained-death exception: presence retains keywords until removal.
    retained = replace(after, retained_model_ids=(casualty.own_models[0].model_instance_id,))
    assert "CHARACTER" in retained.keywords
    assert "CHARACTER" not in after.keywords


def test_02_05_01_faq_6575_embedded_word_does_not_match(
    section02_definitions: Section02Definitions,
) -> None:
    unit = section02_definitions.unit(INFRACTORS)
    assert unit_has_required_keywords(
        unit_keywords=unit.keywords,
        faction_keywords=unit.faction_keywords,
        required_keywords=("EMPEROR'S CHILDREN",),
    )
    assert not unit_has_required_keywords(
        unit_keywords=unit.keywords,
        faction_keywords=unit.faction_keywords,
        required_keywords=("CHILDREN",),
    )
