"""Every save face, native armour/InSv and clearly labelled impossible-armour contracts."""

from pathlib import Path

import pytest

from tests.support.section02_fixtures import (
    INFRACTORS,
    LORD_EXULTANT,
    Section02Definitions,
)
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.saves import (
    SaveKind,
    SaveResolutionRule,
    resolve_saving_throw,
    save_options_for_model,
    saving_throw_roll_spec,
)


@pytest.mark.parametrize("datasheet", [INFRACTORS, LORD_EXULTANT])
@pytest.mark.parametrize("ap", [0, -1, -4, -10])
@pytest.mark.parametrize("raw", range(1, 7))
def test_native_save_faces_ap_and_invulnerable_priority(
    section05_definitions: Section02Definitions, datasheet: str, ap: int, raw: int
) -> None:
    model = section05_definitions.unit(datasheet).own_models[0]
    options = save_options_for_model(model=model, armor_penetration=ap)
    inv = next(
        (
            v.final
            for v in model.characteristics
            if v.characteristic is Characteristic.INVULNERABLE_SAVE and v.final > 0
        ),
        None,
    )
    armour = model.characteristic(Characteristic.SAVE).final
    spec = saving_throw_roll_spec(
        save_kind=SaveKind.INVULNERABLE if inv else SaveKind.ARMOUR,
        player_id="opponent",
        allocated_model_id=model.model_instance_id,
        attack_context_id="s05:save",
    )
    assert (spec.expression.quantity, spec.expression.sides, spec.actor_id) == (
        1,
        6,
        "opponent",
    )
    roll = DiceRollManager("physical").roll_fixed(spec, (raw,))
    save = resolve_saving_throw(roll_state=roll, options=options)
    expected = raw != 1 and ((inv is not None and raw >= inv) or raw + ap >= armour)
    assert save.successful is expected
    if raw != 1 and inv is not None and raw >= inv:
        assert save.resolution_rule is SaveResolutionRule.INVULNERABLE_SAVE
    elif raw != 1 and raw + ap >= armour:
        assert save.resolution_rule is SaveResolutionRule.ARMOUR_SAVE
    assert save.unmodified_roll == raw
    assert resolve_saving_throw(roll_state=roll, options=tuple(reversed(options))) == save


@pytest.mark.parametrize("ap", [0, -1, -4])
@pytest.mark.parametrize("raw", range(1, 7))
def test_native_save7_faces_keep_armour_and_invulnerable(
    selected_army_source_index: Path | None, ap: int, raw: int
) -> None:
    import json

    from tests.save7_allocation_helpers import native_target
    from warhammer40k_core.engine.saves import SaveOption

    model = native_target(selected_army_source_index).own_models[0]
    options = save_options_for_model(model=model, armor_penetration=ap)
    assert [(o.save_kind, o.characteristic_target_number, o.target_number) for o in options] == [
        (SaveKind.ARMOUR, 7, 7 - ap),
        (SaveKind.INVULNERABLE, 5, 5),
    ]
    assert (
        tuple(SaveOption.from_payload(json.loads(json.dumps(o.to_payload()))) for o in options)
        == options
    )
    roll = DiceRollManager("save7-faces").roll_fixed(
        saving_throw_roll_spec(
            save_kind=SaveKind.INVULNERABLE,
            player_id="opponent",
            allocated_model_id=model.model_instance_id,
            attack_context_id="save7:face",
        ),
        (raw,),
    )
    result = resolve_saving_throw(roll_state=roll, options=options)
    assert result.successful is (raw >= 5)
    assert result.resolution_rule is (
        SaveResolutionRule.UNMODIFIED_ONE
        if raw == 1
        else SaveResolutionRule.INVULNERABLE_SAVE
        if raw >= 5
        else SaveResolutionRule.FAILED
    )
    armour = resolve_saving_throw(roll_state=roll, options=options[:1])
    assert not armour.successful
    assert armour.target_number == 7
    assert save_options_for_model(model=model, armor_penetration=ap, no_saves_allowed=True) == ()


def test_effective_save7_improvement_worsening_and_current_cover(
    selected_army_source_index: Path | None,
) -> None:
    from dataclasses import replace

    from tests.phase13b_shooting_declaration_helpers import _benefit_of_cover_result
    from tests.save7_allocation_helpers import modified_model, native_target
    from warhammer40k_core.core.ruleset_descriptor import CoverEffect, RulesetDescriptor

    native = native_target(selected_army_source_index).own_models[0]
    model = replace(
        native,
        characteristics=tuple(
            v
            for v in native.characteristics
            if v.characteristic is not Characteristic.INVULNERABLE_SAVE
        ),
    )
    spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="opponent",
        allocated_model_id=model.model_instance_id,
        attack_context_id="save7:modifier",
    )
    roll = DiceRollManager("save7-modifier").roll_fixed(spec, (6,))
    for delta, succeeds in ((0, False), (1, False), (-1, True)):
        changed = modified_model(model, Characteristic.SAVE, delta)
        value = changed.characteristic(Characteristic.SAVE)
        assert (value.raw, value.final) == (7, 7 + delta)
        assert value.applied_modifier_ids
        options = save_options_for_model(model=changed, armor_penetration=0)
        assert options[0].characteristic_target_number == 7 + delta
        assert resolve_saving_throw(roll_state=roll, options=options).successful is succeeds
    restored = modified_model(
        modified_model(model, Characteristic.SAVE, 1), Characteristic.SAVE, -1
    )
    assert restored.characteristic(Characteristic.SAVE).final == 7
    cover = _benefit_of_cover_result()
    assert cover.cover_effect is CoverEffect.ATTACKER_BS_MODIFIER
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    assert descriptor.terrain_visibility_policy.cover_effect is CoverEffect.ATTACKER_BS_MODIFIER
    options = save_options_for_model(model=model, armor_penetration=0, cover_result=cover)
    assert not options[0].cover_applied
    assert options[0].target_number == 7
    assert not resolve_saving_throw(roll_state=roll, options=options).successful
    # Existing alternate-policy kernel control; this is not active 11th Cover.
    alternate = replace(cover, cover_effect=CoverEffect.SAVE_BONUS)
    options = save_options_for_model(model=model, armor_penetration=0, cover_result=alternate)
    assert options[0].cover_applied
    assert resolve_saving_throw(roll_state=roll, options=options).successful


@pytest.mark.parametrize("conditional", [False, True])
@pytest.mark.parametrize("threshold", [True, 2.0, "2", -1, 0, 1, 2, 6, 7, 8])
def test_effective_save_widening_keeps_invulnerable_grant_bounds(
    threshold: object,
    conditional: bool,
) -> None:
    from dataclasses import replace
    from typing import cast

    from warhammer40k_core.engine.catalog_datasheet_rule_descriptors import (
        conditional_invulnerable_save_descriptor_for_clause,
        invulnerable_save_descriptor_for_clause,
    )
    from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
    from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
    from warhammer40k_core.rules.rule_ir import RuleIR, RuleParameter, RuleParameterValue
    from warhammer40k_core.rules.source_data import RuleSourceText

    source = RuleSourceText.from_raw(
        source_id="save7:constructed-grant",
        raw_text="This model has a 5+ invulnerable save.",
        objective_scope=ObjectiveRuleScope.NON_CORE_RULES,
    )
    clause = compile_rule_source_text(
        source, source_keyword_sequence_parts=("INFANTRY",)
    ).rule_ir.clauses[0]
    if conditional:
        # Reuse the admitted Rangers descriptor, not newly parsed source grammar.
        import json

        catalog_path = Path(__file__).resolve().parents[3] / (
            "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
            "court_of_slaughter_anvanth_2026_08/artifacts/catalog.json"
        )
        catalog = json.loads(catalog_path.read_text())["army_catalog"]
        ranger = next(
            sheet for sheet in catalog["datasheets"] if sheet["datasheet_id"] == "000000592"
        )
        clause = next(
            item
            for ability in ranger["abilities"]
            if ability["rule_ir_payload"] is not None
            for item in RuleIR.from_payload(ability["rule_ir_payload"]).clauses
            if item.template_id == "phase17c:conditional-ranged-invulnerable-save"
        )
    reader = (
        conditional_invulnerable_save_descriptor_for_clause
        if conditional
        else invulnerable_save_descriptor_for_clause
    )
    assert reader(clause) is not None
    effect = clause.effects[0]
    changed = replace(
        clause,
        effects=(
            replace(
                effect,
                parameters=tuple(
                    RuleParameter(p.key, cast(RuleParameterValue, threshold))
                    if p.key == "value"
                    else p
                    for p in effect.parameters
                ),
            ),
        ),
    )
    descriptor = reader(changed)
    if type(threshold) is int and 2 <= threshold <= 6:
        assert descriptor is not None
        assert descriptor.target_number == threshold
    else:
        assert descriptor is None


@pytest.mark.parametrize("devastating", [False, True])
def test_effective_save7_is_real_save_except_devastating_wounds(
    section05_definitions: Section02Definitions,
    devastating: bool,
) -> None:
    from dataclasses import replace

    from tests.save7_allocation_helpers import modified_model
    from tests.support.section05_sequence import (
        fixed_sequence_dice,
        native_sequence,
        payloads,
        resolve,
    )
    from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, WeaponKeyword
    from warhammer40k_core.engine.damage_allocation import model_by_id

    target = section05_definitions.unit(LORD_EXULTANT, army_id="enemy", identity="target")
    model = modified_model(
        target.own_models[0],
        Characteristic.SAVE,
        7 - target.own_models[0].characteristic(Characteristic.SAVE).final,
    )
    # Labelled armour-only Core control on a genuine native character body.
    model = replace(
        model,
        characteristics=tuple(
            value
            for value in model.characteristics
            if value.characteristic is not Characteristic.INVULNERABLE_SAVE
        ),
    )
    target = replace(target, own_models=(model,))
    state, target, sequence = native_sequence(section05_definitions, target=target)
    if devastating:
        pool = sequence.attack_pools[0]
        profile = replace(
            pool.weapon_profile,
            keywords=(*pool.weapon_profile.keywords, WeaponKeyword.DEVASTATING_WOUNDS),
            abilities=(*pool.weapon_profile.abilities, AbilityDescriptor.devastating_wounds()),
        )
        sequence = replace(sequence, attack_pools=(replace(pool, weapon_profile=profile),))
    dice = fixed_sequence_dice(sequence, target, (6,), (6,), (1,))
    decisions, remaining, status = resolve(state, sequence, dice[:2] if devastating else dice)
    assert remaining is None
    assert status is None
    saves = [item for item in payloads(decisions, "attack_sequence_step") if item["step"] == "save"]
    assert len(saves) == (0 if devastating else 1)
    assert len(payloads(decisions, "dice_rolled")) == (2 if devastating else 3)
    assert bool(payloads(decisions, "devastating_wounds_mortal_wounds_applied")) is devastating
    assert (
        model_by_id(state=state, model_instance_id=model.model_instance_id).current_wounds
        == model.current_wounds - 1
    )


def test_effective_save7_current_cover_penalizes_bs_only(
    selected_army_source_index: Path | None,
) -> None:
    from dataclasses import replace

    from tests.daemons_native_source_helpers import native_definitions
    from tests.save7_allocation_helpers import native_target
    from tests.support.section05_sequence import native_sequence
    from warhammer40k_core.engine.attack_sequence_hit_wound import _hit_skill_modifier
    from warhammer40k_core.engine.shooting_targets import BENEFIT_OF_COVER_RULE_ID

    d = native_definitions(selected_army_source_index)
    target = native_target(selected_army_source_index)
    state, _, sequence = native_sequence(d, target=target)
    pool = sequence.attack_pools[0]
    covered = replace(pool, targeting_rule_ids=(*pool.targeting_rule_ids, BENEFIT_OF_COVER_RULE_ID))
    assert _hit_skill_modifier(state=state, pool=pool) == 0
    assert _hit_skill_modifier(state=state, pool=covered) == 1
    assert target.own_models[0].characteristic(Characteristic.SAVE).final == 7
