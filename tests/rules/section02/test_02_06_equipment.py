"""02.06/02.07: physical bearer, composition and legal wargear changes."""

import pytest

from tests.support.section02_fixtures import AVENGERS, INFRACTORS, Section02Definitions
from warhammer40k_core.engine.unit_factory import UnitFactoryError
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection, WargearSelection


def test_02_06_defaults_belong_to_the_correct_real_model_type(
    section02_definitions: Section02Definitions,
) -> None:
    unit = section02_definitions.unit()
    regular = tuple(m for m in unit.own_models if m.model_profile_id == f"{INFRACTORS}:infractors")
    champion = tuple(
        m for m in unit.own_models if m.model_profile_id == f"{INFRACTORS}:obsessionist"
    )
    assert (len(regular), len(champion)) == (4, 1)
    assert all(
        m.wargear_ids == (f"{INFRACTORS}:bolt-pistol", f"{INFRACTORS}:duelling-sabre")
        for m in regular
    )
    assert champion[0].wargear_ids == (f"{INFRACTORS}:bolt-pistol", f"{INFRACTORS}:power-sword")
    assert {w for m in unit.own_models for w in m.wargear_ids} == {
        f"{INFRACTORS}:bolt-pistol",
        f"{INFRACTORS}:duelling-sabre",
        f"{INFRACTORS}:power-sword",
    }


@pytest.mark.parametrize("count", [3, 10])
def test_02_06_invalid_composition_is_rejected(
    section02_definitions: Section02Definitions,
    count: int,
) -> None:
    with pytest.raises(UnitFactoryError):
        section02_definitions.unit(
            composition=(
                ModelProfileSelection(f"{INFRACTORS}:infractors", count),
                ModelProfileSelection(f"{INFRACTORS}:obsessionist", 1),
            )
        )


def test_02_06_01_and_02_07_replacement_affects_only_its_bearer(
    section02_definitions: Section02Definitions,
) -> None:
    option = WargearSelection(
        f"{INFRACTORS}:obsessionist-plasma-pistol:option-1",
        f"{INFRACTORS}:obsessionist",
        (f"{INFRACTORS}:plasma-pistol",),
    )
    changed = section02_definitions.unit(wargear=(option,))
    for model in changed.own_models:
        champion = model.model_profile_id == f"{INFRACTORS}:obsessionist"
        assert (f"{INFRACTORS}:plasma-pistol" in model.wargear_ids) is champion
        assert (f"{INFRACTORS}:bolt-pistol" in model.wargear_ids) is not champion
    assert all(
        f"{INFRACTORS}:plasma-pistol" not in m.wargear_ids
        for m in section02_definitions.unit().own_models
    )


@pytest.mark.parametrize(
    ("profile", "weapon"),
    [
        (f"{INFRACTORS}:infractors", f"{INFRACTORS}:plasma-pistol"),
        (f"{INFRACTORS}:obsessionist", f"{AVENGERS}:avenger-shuriken-catapult"),
    ],
)
def test_02_07_wrong_model_or_foreign_equipment_is_rejected(
    section02_definitions: Section02Definitions,
    profile: str,
    weapon: str,
) -> None:
    with pytest.raises(UnitFactoryError):
        section02_definitions.unit(
            wargear=(
                WargearSelection(
                    f"{INFRACTORS}:obsessionist-plasma-pistol:option-1", profile, (weapon,)
                ),
            )
        )


@pytest.mark.parametrize(
    ("regular", "champion", "valid"), [(4, 1, True), (9, 1, True), (4, 0, False), (4, 2, False)]
)
def test_02_06_composition_bounds_apply_to_each_model_type(
    section02_definitions: Section02Definitions, regular: int, champion: int, valid: bool
) -> None:
    composition = (
        ModelProfileSelection(f"{INFRACTORS}:infractors", regular),
        *((ModelProfileSelection(f"{INFRACTORS}:obsessionist", champion),) if champion else ()),
    )
    if valid:
        assert (
            len(section02_definitions.unit(composition=composition).own_models)
            == regular + champion
        )
    else:
        with pytest.raises((UnitFactoryError, ValueError)):
            section02_definitions.unit(composition=composition)


def test_02_06_01_enhancement_bearer_remains_the_selected_character(
    section02_definitions: Section02Definitions,
) -> None:
    from dataclasses import replace

    from tests.support.section02_fixtures import LORD_EXULTANT, health_state
    from warhammer40k_core.engine.army_mustering import EnhancementAssignment
    from warhammer40k_core.engine.enhancement_bearers import enhancement_bearer_model
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        faction_subrules_2026_27,
    )

    leader = section02_definitions.unit(LORD_EXULTANT, identity="leader")
    bodyguard = section02_definitions.unit(identity="bodyguard")
    row = next(
        r
        for r in faction_subrules_2026_27.enhancement_rows()
        if r.detachment_id == "mercurial-host" and r.enhancement_id == "000009998004"
    )
    assignment = EnhancementAssignment(
        model_profile_id=leader.own_models[0].model_profile_id,
        model_index=1,
        enhancement_id=row.enhancement_id,
        target_unit_selection_id="leader",
        source_id=row.source_ids[0],
    )
    army = replace(
        health_state(section02_definitions, bodyguard).army_definitions[0],
        units=(bodyguard, leader),
        enhancement_assignments=(assignment,),
    )
    bearer = enhancement_bearer_model(army, assignment=assignment)
    assert bearer.model_instance_id == leader.own_models[0].model_instance_id
    assert bearer.model_instance_id not in bodyguard.own_model_ids()
