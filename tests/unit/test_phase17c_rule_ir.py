from __future__ import annotations

import hashlib
import json
from typing import cast

import pytest

from warhammer40k_core.rules.rule_compiler import (
    CompiledRuleSource,
    RuleCompilerError,
    compile_normalized_rule_text,
    compile_rule_source_text,
    compile_rule_source_texts,
)
from warhammer40k_core.rules.rule_ir import (
    RuleCondition,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleIRPayload,
    RuleTargetKind,
    RuleTriggerKind,
    RuleUnsupportedReason,
    parameter_payload,
)
from warhammer40k_core.rules.source_data import RuleSourceText


def test_phase17c_normalized_source_text_compiles_to_stable_rule_ir() -> None:
    source = RuleSourceText.from_raw(
        source_id="phase17c:rule:combined",
        raw_text=(
            "At the start of your Command phase, select one friendly INFANTRY unit "
            "within 6 inches. Until the end of the phase, add 1 to hit rolls for "
            "ranged weapons equipped by models in that unit and those weapons gain "
            "Lethal Hits. Once per phase."
        ),
    )
    compiled = compile_rule_source_text(source)
    second_compiled = compile_rule_source_text(source)
    payload = cast(RuleIRPayload, json.loads(compiled.rule_ir.to_json_bytes()))
    effects = _effects(compiled.rule_ir)
    conditions = _conditions(compiled.rule_ir)

    assert compiled.to_payload() == second_compiled.to_payload()
    assert RuleIR.from_payload(payload).to_payload() == compiled.rule_ir.to_payload()
    assert (
        CompiledRuleSource.from_payload(compiled.to_payload()).to_payload() == compiled.to_payload()
    )
    assert compiled.rule_ir.is_supported
    assert compiled.rule_ir.parser_version == "phase17c-rule-parser-v1"
    assert compiled.rule_ir.clauses[0].trigger is not None
    assert compiled.rule_ir.clauses[0].trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert compiled.rule_ir.clauses[0].target is not None
    assert compiled.rule_ir.clauses[0].target.kind is RuleTargetKind.FRIENDLY_UNIT
    assert any(condition.kind is RuleConditionKind.KEYWORD_GATE for condition in conditions)
    assert any(condition.kind is RuleConditionKind.DISTANCE_PREDICATE for condition in conditions)
    assert any(
        parameter_payload(effect.parameters) == {"delta": 1, "roll_type": "hit"}
        for effect in effects
        if effect.kind is RuleEffectKind.MODIFY_DICE_ROLL
    )
    assert any(
        parameter_payload(effect.parameters) == {"weapon_ability": "Lethal Hits"}
        for effect in effects
        if effect.kind is RuleEffectKind.GRANT_WEAPON_ABILITY
    )
    assert any(
        condition.kind is RuleConditionKind.FREQUENCY_LIMIT
        and parameter_payload(condition.parameters) == {"scope": "phase"}
        for condition in conditions
    )


def test_phase17c_unsupported_clauses_preserve_source_span_and_reason() -> None:
    source = RuleSourceText.from_raw(
        source_id="phase17c:rule:unsupported",
        raw_text="Roll a scatter die and consult the legacy table.",
    )
    compiled = compile_rule_source_text(source)
    clause = compiled.rule_ir.clauses[0]
    diagnostic = clause.diagnostics[0]

    assert not compiled.rule_ir.is_supported
    assert clause.unsupported_reason is RuleUnsupportedReason.UNSUPPORTED_LANGUAGE
    assert diagnostic.reason is RuleUnsupportedReason.UNSUPPORTED_LANGUAGE
    assert diagnostic.source_span.text == source.normalized_text
    assert (
        source.normalized_text[diagnostic.source_span.start : diagnostic.source_span.end]
        == diagnostic.source_span.text
    )


def test_phase17c_partial_parse_with_unknown_effect_is_unsupported() -> None:
    compiled = _compiled(
        "At the start of your Command phase, roll a scatter die and consult the legacy table."
    )
    clause = compiled.rule_ir.clauses[0]

    assert not compiled.rule_ir.is_supported
    assert not clause.is_supported
    assert clause.trigger is not None
    assert clause.unsupported_reason is RuleUnsupportedReason.UNSUPPORTED_LANGUAGE
    assert clause.diagnostics[0].reason is RuleUnsupportedReason.UNSUPPORTED_LANGUAGE
    assert "scatter die" in clause.diagnostics[0].source_span.text


def test_phase17c_known_effect_plus_unknown_residue_is_unsupported() -> None:
    compiled = _compiled("Gain 1CP and roll a scatter die.")

    assert not compiled.rule_ir.is_supported
    assert any(
        effect.kind is RuleEffectKind.MODIFY_COMMAND_POINTS for effect in _effects(compiled.rule_ir)
    )
    assert any(
        diagnostic.reason is RuleUnsupportedReason.UNSUPPORTED_LANGUAGE
        and "scatter die" in diagnostic.source_span.text
        for diagnostic in compiled.rule_ir.diagnostics
    )


def test_phase17c_death_guard_cloud_of_flies_fixture_text_keeps_residual_explicit() -> None:
    compiled = _compiled("Use in the Shooting phase.")
    clause = compiled.rule_ir.clauses[0]

    assert not compiled.rule_ir.is_supported
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert clause.diagnostics[0].source_span.text == "Use"


@pytest.mark.parametrize(
    ("raw_text", "expected_trigger", "expected_condition", "expected_target", "expected_effect"),
    [
        (
            "At the end of the opponent's Movement phase, select one enemy unit.",
            RuleTriggerKind.TIMING_WINDOW,
            None,
            RuleTargetKind.ENEMY_UNIT,
            None,
        ),
        (
            "Select one friendly GRENADES unit within 8 inches.",
            None,
            RuleConditionKind.KEYWORD_GATE,
            RuleTargetKind.FRIENDLY_UNIT,
            None,
        ),
        (
            "When this unit is destroyed, score 5VP.",
            RuleTriggerKind.UNIT_DESTROYED,
            None,
            RuleTargetKind.THIS_UNIT,
            RuleEffectKind.ADD_VICTORY_POINTS,
        ),
        (
            "After a hit roll, re-roll hit rolls.",
            RuleTriggerKind.DICE_ROLL,
            None,
            None,
            RuleEffectKind.REROLL_PERMISSION,
        ),
        (
            "Add 1 to the Objective Control characteristic.",
            None,
            None,
            None,
            RuleEffectKind.MODIFY_CHARACTERISTIC,
        ),
        (
            "Models in the bearer's unit have a Leadership characteristic of 6+.",
            None,
            None,
            RuleTargetKind.THIS_UNIT,
            RuleEffectKind.SET_CHARACTERISTIC,
        ),
        (
            "Add 2 inches to the Move characteristic.",
            None,
            None,
            None,
            RuleEffectKind.MODIFY_MOVE_DISTANCE,
        ),
        (
            "Add 1 to Charge rolls made for the bearer's unit.",
            None,
            None,
            RuleTargetKind.THIS_UNIT,
            RuleEffectKind.MODIFY_DICE_ROLL,
        ),
        (
            "Gain 1CP and score 3VP.",
            None,
            None,
            RuleTargetKind.PLAYER,
            RuleEffectKind.MODIFY_COMMAND_POINTS,
        ),
        (
            "That unit gains Stealth until the end of the phase.",
            None,
            None,
            RuleTargetKind.SELECTED_UNIT,
            RuleEffectKind.GRANT_ABILITY,
        ),
        (
            "Ranged weapons equipped by models in that unit gain Sustained Hits.",
            None,
            None,
            RuleTargetKind.SELECTED_UNIT,
            RuleEffectKind.GRANT_WEAPON_ABILITY,
        ),
        (
            "This unit can be set up more than 9 inches away from enemy units.",
            RuleTriggerKind.SETUP,
            RuleConditionKind.DISTANCE_PREDICATE,
            RuleTargetKind.THIS_UNIT,
            RuleEffectKind.PLACEMENT_PERMISSION,
        ),
        (
            "Aura: while a friendly unit is within 6 inches, subtract 1 from wound rolls.",
            None,
            RuleConditionKind.AURA,
            RuleTargetKind.AURA_UNITS,
            RuleEffectKind.MODIFY_DICE_ROLL,
        ),
        (
            "Once per turn, move an additional 3 inches.",
            None,
            RuleConditionKind.FREQUENCY_LIMIT,
            None,
            RuleEffectKind.MODIFY_MOVE_DISTANCE,
        ),
    ],
)
def test_phase17c_initial_language_families_compile_to_typed_components(
    raw_text: str,
    expected_trigger: RuleTriggerKind | None,
    expected_condition: RuleConditionKind | None,
    expected_target: RuleTargetKind | None,
    expected_effect: RuleEffectKind | None,
) -> None:
    compiled = _compiled(raw_text)
    triggers = [clause.trigger.kind for clause in compiled.rule_ir.clauses if clause.trigger]
    conditions = [condition.kind for condition in _conditions(compiled.rule_ir)]
    targets = [clause.target.kind for clause in compiled.rule_ir.clauses if clause.target]
    effects = [effect.kind for effect in _effects(compiled.rule_ir)]

    assert compiled.rule_ir.is_supported
    if expected_trigger is not None:
        assert expected_trigger in triggers
    if expected_condition is not None:
        assert expected_condition in conditions
    if expected_target is not None:
        assert expected_target in targets
    if expected_effect is not None:
        assert expected_effect in effects


def test_phase17c_equivalent_roll_modifier_forms_compile_to_same_semantics() -> None:
    add_text = _compiled("Add 1 to hit rolls for that unit.").rule_ir
    signed_text = _compiled("+1 to hit rolls for that unit.").rule_ir
    add_effect = next(
        effect for effect in _effects(add_text) if effect.kind is RuleEffectKind.MODIFY_DICE_ROLL
    )
    signed_effect = next(
        effect for effect in _effects(signed_text) if effect.kind is RuleEffectKind.MODIFY_DICE_ROLL
    )

    assert parameter_payload(add_effect.parameters) == parameter_payload(signed_effect.parameters)


def test_phase17c_optional_wargear_ability_text_compiles_to_bearer_unit_ir() -> None:
    icon = _compiled("Models in the bearer's unit have a Leadership characteristic of 6+.").rule_ir
    instrument = _compiled("Add 1 to Charge rolls made for the bearer's unit.").rule_ir
    icon_effect = next(
        effect for effect in _effects(icon) if effect.kind is RuleEffectKind.SET_CHARACTERISTIC
    )
    instrument_effect = next(
        effect for effect in _effects(instrument) if effect.kind is RuleEffectKind.MODIFY_DICE_ROLL
    )

    assert icon.is_supported
    assert icon.clauses[0].target is not None
    assert icon.clauses[0].target.kind is RuleTargetKind.THIS_UNIT
    assert parameter_payload(icon_effect.parameters) == {
        "characteristic": "leadership",
        "value": "6+",
    }
    assert instrument.is_supported
    assert instrument.clauses[0].target is not None
    assert instrument.clauses[0].target.kind is RuleTargetKind.THIS_UNIT
    assert parameter_payload(instrument_effect.parameters) == {
        "delta": 1,
        "roll_type": "charge",
    }


def test_phase17c_bearer_model_text_is_distinct_from_bearers_unit() -> None:
    bearer = _compiled("The bearer has a Toughness characteristic of 5.").rule_ir
    bearer_unit = _compiled("The bearer's unit has a Toughness characteristic of 5.").rule_ir

    assert bearer.is_supported
    assert bearer.clauses[0].target is not None
    assert bearer.clauses[0].target.kind is RuleTargetKind.THIS_MODEL
    assert bearer_unit.is_supported
    assert bearer_unit.clauses[0].target is not None
    assert bearer_unit.clauses[0].target.kind is RuleTargetKind.THIS_UNIT


def test_phase17c_bearer_feel_no_pain_qualifier_compiles_to_model_source_ir() -> None:
    rule_ir = _compiled(
        "The bearer has the Feel No Pain 3+ ability against Psychic Attacks."
    ).rule_ir
    clause = rule_ir.clauses[0]
    effect = next(
        effect for effect in clause.effects if effect.kind is RuleEffectKind.GRANT_ABILITY
    )

    assert rule_ir.is_supported
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_MODEL
    assert parameter_payload(effect.parameters) == {
        "ability": "Feel No Pain",
        "attack_condition": "psychic_attack",
        "threshold": 3,
    }


def test_phase17c_skullmaster_fury_compiles_to_charge_move_weapon_keyword_grant() -> None:
    rule_ir = _compiled(
        "While this model is leading a unit, each time that unit ends a Charge move, "
        "until the end of the turn, Juggernaut's bladed horns equipped by models in "
        "that unit have the [DEVASTATING WOUNDS] ability."
    ).rule_ir
    clause = rule_ir.clauses[0]
    weapon_effect = next(
        effect for effect in clause.effects if effect.kind is RuleEffectKind.GRANT_WEAPON_ABILITY
    )

    assert rule_ir.is_supported
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert parameter_payload(clause.trigger.parameters) == {
        "edge": "after",
        "phase": "charge",
        "subject": "that_unit",
        "timing_window": "charge_move_end",
    }
    assert any(
        condition.kind is RuleConditionKind.TARGET_CONSTRAINT
        and parameter_payload(condition.parameters) == {"relationship": "this_model_leading_unit"}
        for condition in clause.conditions
    )
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.SELECTED_UNIT
    assert clause.duration is not None
    assert parameter_payload(clause.duration.parameters) == {"endpoint": "turn"}
    assert parameter_payload(weapon_effect.parameters) == {
        "target_scope": "models_in_selected_unit",
        "weapon_ability": "Devastating Wounds",
        "weapon_name": "Juggernaut's bladed horns",
    }


def test_phase17c_hunters_from_the_warp_compiles_to_turn_end_reserve_choice() -> None:
    rule_ir = _compiled(
        "At the end of your opponent's turn, if this unit is not within Engagement Range "
        "of one or more enemy units, you can remove it from the battlefield and place it "
        "into Strategic Reserves."
    ).rule_ir
    clause = rule_ir.clauses[0]
    reserve_effect = next(
        effect for effect in clause.effects if effect.kind is RuleEffectKind.PLACEMENT_PERMISSION
    )

    assert rule_ir.is_supported
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert parameter_payload(clause.trigger.parameters) == {
        "edge": "end",
        "owner": "opponent",
        "phase": "turn",
        "timing_window": "turn_end",
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_UNIT
    assert any(
        condition.kind is RuleConditionKind.DISTANCE_PREDICATE
        and parameter_payload(condition.parameters)
        == {
            "distance_inches": None,
            "negated": True,
            "object_allegiance": "enemy",
            "object_kind": "unit",
            "object_quantity": "one_or_more",
            "predicate": "within_engagement_range",
            "qualifier": None,
            "range_kind": "engagement_range",
            "subject": "this_unit",
        }
        for condition in clause.conditions
    )
    assert parameter_payload(reserve_effect.parameters) == {
        "action": "remove_from_battlefield_to_strategic_reserves",
        "allowed": True,
        "optional": True,
        "placement_kind": "turn_end_reserves",
        "reserve_kind": "strategic_reserves",
    }


@pytest.mark.parametrize(
    ("raw_text", "expected_allegiance"),
    [
        (
            "Aura: while a friendly unit is within 6 inches, subtract 1 from wound rolls.",
            "friendly",
        ),
        (
            "Aura: while an enemy unit is within 6 inches, subtract 1 from wound rolls.",
            "enemy",
        ),
        (
            "Aura: while a unit is within 6 inches, subtract 1 from wound rolls.",
            "any",
        ),
    ],
)
def test_phase17c_aura_targets_preserve_structured_allegiance(
    raw_text: str,
    expected_allegiance: str,
) -> None:
    target = _compiled(raw_text).rule_ir.clauses[0].target

    assert target is not None
    assert target.kind is RuleTargetKind.AURA_UNITS
    assert parameter_payload(target.parameters)["allegiance"] == expected_allegiance


def test_phase17c_compiler_rejects_stale_or_duplicate_source_inputs() -> None:
    source = RuleSourceText.from_raw(source_id="phase17c:rule:stale", raw_text="Gain 1CP.")

    with pytest.raises(RuleCompilerError, match="stale"):
        compile_normalized_rule_text(
            source_id=source.source_id,
            normalized_text="Gain 2CP.",
            parsed_tokens=source.parsed_tokens,
        )
    with pytest.raises(RuleCompilerError, match="duplicate"):
        compile_rule_source_texts((source, source))


def _compiled(raw_text: str) -> CompiledRuleSource:
    source_suffix = hashlib.sha256(raw_text.encode()).hexdigest()[:12]
    return compile_rule_source_text(
        RuleSourceText.from_raw(source_id=f"phase17c:test:{source_suffix}", raw_text=raw_text)
    )


def _effects(rule_ir: RuleIR) -> tuple[RuleEffectSpec, ...]:
    return tuple(effect for clause in rule_ir.clauses for effect in clause.effects)


def _conditions(rule_ir: RuleIR) -> tuple[RuleCondition, ...]:
    return tuple(condition for clause in rule_ir.clauses for condition in clause.conditions)
