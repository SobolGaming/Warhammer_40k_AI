"""Core modifier inputs applied to genuine equipped profiles at dispatcher boundary."""

import pytest

from tests.support.section02_fixtures import MAULERFIEND, RANGERS, Section02Definitions
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.rule_ir_weapon_modifiers import rule_ir_modified_weapon_profile
from warhammer40k_core.engine.weapon_declaration import attacks_for_profile
from warhammer40k_core.engine.weapon_instances import equipped_weapon_profile_instances_for_model


@pytest.mark.parametrize(
    ("datasheet", "characteristic"),
    [(MAULERFIEND, Characteristic.WEAPON_SKILL), (RANGERS, Characteristic.BALLISTIC_SKILL)],
)
def test_02_02_01_model_skill_operation_reaches_every_matching_equipped_profile(
    section02_definitions: Section02Definitions, datasheet: str, characteristic: Characteristic
) -> None:
    model = section02_definitions.unit(datasheet).own_models[0]
    equipped = equipped_weapon_profile_instances_for_model(
        model=model, army_catalog=section02_definitions.package.army_catalog
    )
    matching = [e for e in equipped if e.weapon_profile.skill.characteristic is characteristic]
    assert len(matching) >= 2
    for entry in equipped:
        original = entry.weapon_profile
        changed = rule_ir_modified_weapon_profile(
            parameters={"characteristic": characteristic.value, "delta": -1},
            profile=original,
            source_id="rule:02:02.02.01:1",
            modifier_id="model-skill",
        )
        if original.skill.characteristic is characteristic:
            assert changed.skill.final == max(2, original.skill.final - 1)
            assert changed.skill.raw == original.skill.raw
            assert changed.skill.applied_modifier_ids == ("model-skill",)
        else:
            assert changed == original


def test_02_02_01_faq_bonus_generates_one_extra_attack_per_ranged_weapon(
    section02_definitions: Section02Definitions,
) -> None:
    model = section02_definitions.unit(RANGERS).own_models[0]
    equipped = equipped_weapon_profile_instances_for_model(
        model=model, army_catalog=section02_definitions.package.army_catalog
    )
    ranged_count = 0
    manager = DiceRollManager("faq-A")
    for entry in equipped:
        original = entry.weapon_profile
        changed = rule_ir_modified_weapon_profile(
            parameters={"characteristic": "attacks", "delta": 1, "weapon_scope": "ranged"},
            profile=original,
            source_id="faq:66be2ad9-24af-4edf-890a-c0e55004bf76",
            modifier_id="unit-ranged-attacks",
        )
        actual = attacks_for_profile(
            changed, manager=manager, scope_id=entry.weapon_instance_id, actor_id="owner"
        )
        if original.skill.characteristic is Characteristic.BALLISTIC_SKILL:
            ranged_count += 1
            assert original.attack_profile.fixed_attacks is not None
            assert actual == original.attack_profile.fixed_attacks + 1
        else:
            assert changed == original
    assert ranged_count == 2
    assert manager.event_log.to_payload() == []
