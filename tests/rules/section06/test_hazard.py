"""06.03 and FAQs06/07/15: shared dice owner and native plasma weapon completion."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import minimal_state, place_units
from tests.support.section02_consumers import attack_pool
from tests.support.section02_fixtures import (
    INFRACTORS,
    LORD_EXULTANT,
    MAULERFIEND,
    Section02Definitions,
)
from tests.support.section04_fixtures import combat_state
from tests.support.section05_sequence import payloads
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.attack_sequence_hazardous import _resolve_hazardous_tests
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.hazard import (
    failed_hazard_roll_indices,
    hazard_mortal_wounds_per_failed_roll,
    hazard_roll_failed,
    hazard_roll_spec,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.wargear_selections import WargearSelection
from warhammer40k_core.engine.weapon_instances import equipped_weapon_profile_instances_for_model


@pytest.mark.parametrize("roll_type", ["unit_hazard", "hazardous_test"])
@pytest.mark.parametrize("face", range(1, 7))
def test_unit_hazard_single_d6_faces_and_alias(roll_type: str, face: int) -> None:
    dice = DiceRollManager("s06:hazard")
    roll = dice.roll_fixed(
        hazard_roll_spec(reason="06.03", roll_type=roll_type, actor_id="unit"), (face,)
    )
    assert roll.current_values == (face,)
    assert roll.original_result.spec.expression.quantity == 1
    assert roll.original_result.spec.expression.sides == 6
    assert hazard_roll_failed(roll) is (face in (1, 2))
    assert failed_hazard_roll_indices(roll) == ((0,) if face in (1, 2) else ())


def test_requested_hazards_are_one_simultaneous_batch() -> None:
    decisions = DecisionController()
    dice = DiceRollManager("s06:batch", event_log=decisions.event_log)
    roll = dice.roll_fixed(
        hazard_roll_spec(reason="06.03", roll_type="unit_hazard", actor_id="unit", quantity=6),
        (1, 2, 3, 4, 5, 6),
    )
    assert failed_hazard_roll_indices(roll) == (0, 1)
    events = payloads(decisions, "dice_rolled")
    assert len(events) == 1
    assert roll.current_values == (1, 2, 3, 4, 5, 6)


@pytest.mark.parametrize(
    ("native_id", "expected"),
    [(INFRACTORS, 1), (LORD_EXULTANT, 1), (MAULERFIEND, 3), ("000000599", 3)],
)
def test_every_native_model_determines_hazard_damage(
    section06_definitions: Section02Definitions, native_id: str, expected: int
) -> None:
    unit = section06_definitions.unit(native_id)
    assert hazard_mortal_wounds_per_failed_roll(unit) == expected


@pytest.mark.parametrize(
    ("other_id", "keyword", "expected"),
    [
        (LORD_EXULTANT, "INFANTRY", 1),
        ("000000602", "MOUNTED", 1),
        ("000000613", "MONSTER", 3),
        ("000000599", "VEHICLE", 3),
    ],
)
def test_faq06_mixed_native_attached_unit_all_model_condition(
    section06_definitions: Section02Definitions,
    other_id: str,
    keyword: str,
    expected: int,
) -> None:
    d = section06_definitions
    body, leader = d.unit(MAULERFIEND), d.unit(other_id, identity="leader")
    state = minimal_state(d, body, leader)
    # Constructed mixed attachment at real rules-unit evaluator: no native faction permission.
    formation = AttachedUnitFormation(
        "attached-unit:section02:mixed",
        body.unit_instance_id,
        (leader.unit_instance_id,),
        component_unit_instance_ids=tuple(sorted((body.unit_instance_id, leader.unit_instance_id))),
        source_id="constructed:s06:mixed",
        attachment_source_ids=("constructed:s06:mixed",),
    )
    state.army_definitions[0] = replace(state.army_definitions[0], attached_units=(formation,))
    place_units(state)
    view = rules_unit_view_by_id(state=state, unit_instance_id=formation.attached_unit_instance_id)
    assert "VEHICLE" in body.own_models[0].keywords
    assert keyword in leader.own_models[0].keywords
    assert hazard_mortal_wounds_per_failed_roll(view) == expected


@pytest.mark.parametrize("face", [1, 2, 3, 6])
def test_faq07_native_plasma_failure_wounds_unarmed_unit_member(
    section06_definitions: Section02Definitions, face: int
) -> None:
    d = section06_definitions
    sheet = d.package.army_catalog.datasheet_by_id(INFRACTORS)
    option = next(
        o for o in sheet.wargear_options if f"{INFRACTORS}:plasma-pistol" in o.allowed_wargear_ids
    )
    unit = d.unit(
        wargear=(
            WargearSelection(
                option.option_id, option.model_profile_id, (f"{INFRACTORS}:plasma-pistol",)
            ),
        )
    )
    bearer = next(m for m in unit.own_models if f"{INFRACTORS}:plasma-pistol" in m.wargear_ids)
    recipient = next(m for m in unit.own_models if m.model_instance_id != bearer.model_instance_id)
    unit = replace(
        unit,
        own_models=tuple(
            replace(m, wounds_remaining=1)
            if m.model_instance_id == recipient.model_instance_id
            else m
            for m in unit.own_models
        ),
    )
    target = d.unit(LORD_EXULTANT, army_id="enemy", identity="target")
    state = combat_state(d, unit, target=target)
    weapon = next(
        w
        for w in equipped_weapon_profile_instances_for_model(
            model=bearer, army_catalog=d.package.army_catalog
        )
        if w.weapon_profile.profile_id.endswith(":supercharge")
    )
    pool = replace(
        attack_pool(unit, target, weapon.weapon_profile, weapon.wargear_id),
        attacker_model_instance_id=bearer.model_instance_id,
        weapon_instance_id=weapon.weapon_instance_id,
    )
    sequence = AttackSequence(
        "s06:plasma", "owner", unit.unit_instance_id, (pool,), source_phase=BattlePhase.SHOOTING
    )
    spec = hazard_roll_spec(
        reason=f"Hazardous tests for {unit.unit_instance_id} after shooting",
        roll_type="hazardous_test",
        actor_id=unit.unit_instance_id,
    )
    fixed = DiceRollManager("s06:fixed").roll_fixed(spec, (face,)).original_result
    decisions = DecisionController()
    status = _resolve_hazardous_tests(
        state=state,
        decisions=decisions,
        manager=DiceRollManager(
            "s06:plasma", event_log=decisions.event_log, injected_results=(fixed,)
        ),
        attack_sequence=sequence,
    )
    assert status is None
    event = payloads(decisions, "hazardous_test_resolved")[0]
    assert event["mortal_wounds"] == int(face <= 2)
    assert (
        model_by_id(state=state, model_instance_id=bearer.model_instance_id).current_wounds
        == bearer.current_wounds
    )
    assert model_by_id(
        state=state, model_instance_id=recipient.model_instance_id
    ).current_wounds == (0 if face <= 2 else 1)
    allocated = payloads(decisions, "mortal_wound_model_allocated")
    assert [a["selected_model_id"] for a in allocated] == (
        [recipient.model_instance_id] if face <= 2 else []
    )
    assert len(payloads(decisions, "dice_rolled")) == 1
