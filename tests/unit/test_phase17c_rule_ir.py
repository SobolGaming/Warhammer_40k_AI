from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any, cast

import pytest

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.ability_coverage import (
    AbilityClauseCoverageRow,
    AbilityCoverageAbilityDatasheetPair,
    AbilityCoverageCategoryRow,
    AbilityCoverageRow,
    AbilityCoverageSupportStage,
    AbilityOverallSupport,
    AbilitySupportRollup,
    ability_clause_coverage_rows_for_ability,
    ability_clause_coverage_rows_for_rule_ir,
    ability_coverage_category_rows,
    ability_coverage_category_rows_payload,
    ability_coverage_rows_payload,
    ability_support_rollup_for_ability,
    ability_support_rollup_for_rule_ir,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
    CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_DESPERATE_ESCAPE_ROLL_MODIFIER_CONSUMER_ID,
    CATALOG_IR_DESTROYED_UNIT_RESTORE_LOST_WOUNDS_CONSUMER_ID,
    CATALOG_IR_FORCE_DESPERATE_ESCAPE_CONSUMER_ID,
    CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
    CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
    CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID,
    catalog_rule_ir_consumers_for_rule,
    catalog_rule_ir_hook_ids_for_rule,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_compiler import (
    CompiledRuleSource,
    RuleCompilerError,
    compile_normalized_rule_text,
    compile_normalized_rule_text_payload,
    compile_rule_source_text,
    compile_rule_source_texts,
    compiler_identity_payload,
)
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleIRError,
    RuleIRPayload,
    RuleParameter,
    RuleParameterValue,
    RuleParseDiagnostic,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    RuleUnsupportedReason,
    parameter_payload,
    rule_condition_kind_from_token,
    rule_duration_kind_from_token,
    rule_effect_kind_from_token,
    rule_target_kind_from_token,
    rule_trigger_kind_from_token,
    rule_unsupported_reason_from_token,
)
from warhammer40k_core.rules.source_data import RuleSourceText

CHAMPION_SLAYER_TEXT = (
    "Each time this model makes a melee attack that targets a Character or Monster unit, "
    "you can re-roll the Wound roll. Each time this model destroys an enemy Character or "
    "Monster unit, this model regains up to D6 lost wounds."
)


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
        parameter_payload(effect.parameters)
        == {"weapon_ability": "Lethal Hits", "weapon_scope": "ranged"}
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


def test_phase17c_champion_slayer_compiles_to_two_independent_clauses() -> None:
    rule_ir = _compiled(CHAMPION_SLAYER_TEXT).rule_ir

    assert rule_ir.is_supported
    assert len(rule_ir.clauses) == 2
    assert rule_ir.clauses[0].source_span.text.startswith("Each time this model makes")
    assert rule_ir.clauses[1].source_span.text.startswith("Each time this model destroys")


def test_phase17c_champion_slayer_clause_one_has_melee_target_gate_and_wound_reroll() -> None:
    clause = _compiled(CHAMPION_SLAYER_TEXT).rule_ir.clauses[0]

    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.DICE_ROLL
    assert parameter_payload(clause.trigger.parameters) == {
        "actor": "this_model",
        "attack_kind": "melee",
        "roll_type": "wound",
        "timing_window": "attack_sequence.wound",
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_MODEL
    assert _condition_payload(clause, RuleConditionKind.TARGET_CONSTRAINT) == {
        "attack_kind": "melee",
        "gate_subject": "attack_target",
        "relationship": "this_model_makes_attack",
    }
    assert _condition_payload(clause, RuleConditionKind.KEYWORD_GATE) == {
        "gate_subject": "attack_target",
        "required_keyword_any": "CHARACTER|MONSTER",
    }
    assert tuple(effect.kind for effect in clause.effects) == (RuleEffectKind.REROLL_PERMISSION,)
    assert parameter_payload(clause.effects[0].parameters) == {"roll_type": "wound"}


def test_phase17c_champion_slayer_clause_two_has_destroyed_unit_gate_and_heal() -> None:
    clause = _compiled(CHAMPION_SLAYER_TEXT).rule_ir.clauses[1]

    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.UNIT_DESTROYED
    assert parameter_payload(clause.trigger.parameters) == {
        "actor": "this_model",
        "destroyed_allegiance": "enemy",
        "destroyed_unit_kind": "unit",
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_MODEL
    assert _condition_payload(clause, RuleConditionKind.TARGET_CONSTRAINT) == {
        "destroyed_allegiance": "enemy",
        "gate_subject": "destroyed_unit",
        "relationship": "this_model_destroyed_unit",
    }
    assert _condition_payload(clause, RuleConditionKind.KEYWORD_GATE) == {
        "gate_subject": "destroyed_unit",
        "required_keyword_any": "CHARACTER|MONSTER",
    }
    assert tuple(effect.kind for effect in clause.effects) == (RuleEffectKind.RESTORE_LOST_WOUNDS,)
    assert parameter_payload(clause.effects[0].parameters) == {
        "amount": "D6",
        "cap": "lost_wounds",
        "optional": True,
        "target": "this_model",
    }


def test_phase17c_champion_slayer_clause_coverage_rolls_up_partial_and_full() -> None:
    rule_ir = _compiled(CHAMPION_SLAYER_TEXT).rule_ir
    descriptor = _descriptor_from_rule_ir(rule_ir)
    clause_rows = ability_clause_coverage_rows_for_rule_ir(
        source_ability_id="source:champion-slayer",
        ability_name="Champion Slayer",
        rule_ir=rule_ir,
    )
    descriptor_clause_rows = ability_clause_coverage_rows_for_ability(descriptor)
    partial_rollup = ability_support_rollup_for_rule_ir(
        source_ability_id="source:champion-slayer",
        ability_name="Champion Slayer",
        rule_ir=rule_ir,
        runtime_consumers_by_clause_id={
            rule_ir.clauses[0].clause_id: (CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID,),
        },
    )
    full_rollup = ability_support_rollup_for_rule_ir(
        source_ability_id="source:champion-slayer",
        ability_name="Champion Slayer",
        rule_ir=rule_ir,
    )
    descriptor_rollup = ability_support_rollup_for_ability(descriptor)

    assert tuple(row.runtime_consumer_ids for row in clause_rows) == (
        (CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID,),
        (CATALOG_IR_DESTROYED_UNIT_RESTORE_LOST_WOUNDS_CONSUMER_ID,),
    )
    assert [row.to_payload() for row in descriptor_clause_rows] == [
        row.to_payload() for row in clause_rows
    ]
    assert partial_rollup.total_clause_count == 2
    assert partial_rollup.consumed_clause_count == 1
    assert partial_rollup.overall_ability_support is AbilityOverallSupport.PARTIAL
    assert full_rollup.total_clause_count == 2
    assert full_rollup.consumed_clause_count == 2
    assert full_rollup.unsupported_clause_count == 0
    assert full_rollup.overall_ability_support is AbilityOverallSupport.FULL
    assert descriptor_rollup is not None
    assert descriptor_rollup.to_payload() == full_rollup.to_payload()


def test_phase17c_descriptor_without_rule_ir_has_no_clause_rollup() -> None:
    descriptor = DatasheetAbilityDescriptor(
        ability_id="descriptor-only",
        name="Descriptor Only",
        source_id="phase17c:test:descriptor-only",
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="Descriptor-only test ability.",
    )

    assert ability_clause_coverage_rows_for_ability(descriptor) == ()
    assert ability_support_rollup_for_ability(descriptor) is None


def test_phase17c_ability_coverage_rows_and_validators_are_fail_fast() -> None:
    row = AbilityCoverageRow(
        catalog_id="catalog",
        datasheet_id="datasheet",
        datasheet_name="Datasheet",
        ability_id="ability",
        ability_name="Ability",
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        source_wargear_id=None,
        catalog_support=CatalogAbilitySupport.GENERIC_RULE_IR,
        support_stage=AbilityCoverageSupportStage.ENGINE_CONSUMED,
        semantic_categories=("custom.category",),
        runtime_consumer_ids=("consumer",),
    )
    category_rows = ability_coverage_category_rows((row,))
    category_payload = ability_coverage_category_rows_payload(category_rows)[0]
    row_payload = ability_coverage_rows_payload((row,))[0]
    span = TextSpan(start=0, end=4, text="Test")
    pair = AbilityCoverageAbilityDatasheetPair(
        coverage_row_id=row.coverage_row_id,
        ability_id=row.ability_id,
        ability_name=row.ability_name,
        datasheet_id=row.datasheet_id,
        datasheet_name=row.datasheet_name,
        source_kind=row.source_kind,
    )

    assert row_payload["coverage_row_id"] == "catalog/datasheet/datasheet/ability/none"
    assert category_payload["category_name"] == "Custom Category"
    assert category_payload["runtime_consumer_ids"] == ["consumer"]
    assert pair.to_payload()["source_kind"] == "datasheet"
    with pytest.raises(GameLifecycleError, match="source_span must be TextSpan"):
        AbilityClauseCoverageRow(
            source_ability_id="source",
            ability_name="Ability",
            clause_id="clause",
            source_span=cast(TextSpan, object()),
            trigger_kind=None,
            effect_kinds=(),
            runtime_consumer_ids=(),
            support_stage=AbilityCoverageSupportStage.ENGINE_CONSUMED,
        )
    with pytest.raises(
        GameLifecycleError, match="support_stage must be AbilityCoverageSupportStage"
    ):
        AbilityClauseCoverageRow(
            source_ability_id="source",
            ability_name="Ability",
            clause_id="clause",
            source_span=span,
            trigger_kind=None,
            effect_kinds=(),
            runtime_consumer_ids=(),
            support_stage=cast(AbilityCoverageSupportStage, "bad"),
        )
    with pytest.raises(GameLifecycleError, match="total_clause_count must be non-negative"):
        AbilitySupportRollup(
            source_ability_id="source",
            ability_name="Ability",
            total_clause_count=-1,
            consumed_clause_count=0,
            unsupported_clause_count=0,
            overall_ability_support=AbilityOverallSupport.UNSUPPORTED,
        )
    with pytest.raises(GameLifecycleError, match="consumed count exceeds total"):
        AbilitySupportRollup(
            source_ability_id="source",
            ability_name="Ability",
            total_clause_count=1,
            consumed_clause_count=2,
            unsupported_clause_count=0,
            overall_ability_support=AbilityOverallSupport.PARTIAL,
        )
    with pytest.raises(GameLifecycleError, match="unsupported count exceeds total"):
        AbilitySupportRollup(
            source_ability_id="source",
            ability_name="Ability",
            total_clause_count=1,
            consumed_clause_count=0,
            unsupported_clause_count=2,
            overall_ability_support=AbilityOverallSupport.PARTIAL,
        )
    with pytest.raises(GameLifecycleError, match="overall support must be AbilityOverallSupport"):
        AbilitySupportRollup(
            source_ability_id="source",
            ability_name="Ability",
            total_clause_count=1,
            consumed_clause_count=0,
            unsupported_clause_count=0,
            overall_ability_support=cast(AbilityOverallSupport, "bad"),
        )
    with pytest.raises(GameLifecycleError, match="source_kind must be CatalogAbilitySourceKind"):
        AbilityCoverageAbilityDatasheetPair(
            coverage_row_id=row.coverage_row_id,
            ability_id=row.ability_id,
            ability_name=row.ability_name,
            datasheet_id=row.datasheet_id,
            datasheet_name=row.datasheet_name,
            source_kind=cast(CatalogAbilitySourceKind, "bad"),
        )
    with pytest.raises(GameLifecycleError, match="category_id must be a string"):
        AbilityCoverageCategoryRow(
            category_id="",
            category_name="Category",
            coverage_row_count=1,
            coverage_row_ids=(row.coverage_row_id,),
            ability_datasheet_pairs=(pair,),
            source_kind_counts=(("datasheet", 1),),
            support_stages=(AbilityCoverageSupportStage.ENGINE_CONSUMED,),
            runtime_consumer_ids=(),
            ability_names=(row.ability_name,),
            datasheet_names=(row.datasheet_name,),
        )
    with pytest.raises(GameLifecycleError, match="coverage_row_ids must match"):
        AbilityCoverageCategoryRow(
            category_id="custom.category",
            category_name="Category",
            coverage_row_count=1,
            coverage_row_ids=(),
            ability_datasheet_pairs=(pair,),
            source_kind_counts=(("datasheet", 1),),
            support_stages=(AbilityCoverageSupportStage.ENGINE_CONSUMED,),
            runtime_consumer_ids=(),
            ability_names=(row.ability_name,),
            datasheet_names=(row.datasheet_name,),
        )
    with pytest.raises(GameLifecycleError, match="source_kind_counts keys must be unique"):
        AbilityCoverageCategoryRow(
            category_id="custom.category",
            category_name="Category",
            coverage_row_count=2,
            coverage_row_ids=("row-a", "row-b"),
            ability_datasheet_pairs=(pair, pair),
            source_kind_counts=(("datasheet", 1), ("datasheet", 1)),
            support_stages=(AbilityCoverageSupportStage.ENGINE_CONSUMED,),
            runtime_consumer_ids=(),
            ability_names=(row.ability_name,),
            datasheet_names=(row.datasheet_name,),
        )
    with pytest.raises(GameLifecycleError, match="Ability coverage rows must be a tuple"):
        ability_coverage_category_rows(cast(tuple[AbilityCoverageRow, ...], []))
    with pytest.raises(GameLifecycleError, match="require coverage rows"):
        ability_coverage_category_rows(cast(tuple[AbilityCoverageRow, ...], (object(),)))
    with pytest.raises(GameLifecycleError, match="category rows must be a tuple"):
        ability_coverage_category_rows_payload(cast(tuple[AbilityCoverageCategoryRow, ...], []))


def test_phase17c_champion_slayer_residual_unsupported_text_preserves_source_span() -> None:
    rule_ir = _compiled(f"{CHAMPION_SLAYER_TEXT} Consult the legacy table.").rule_ir
    diagnostic = rule_ir.diagnostics[0]

    assert not rule_ir.is_supported
    assert diagnostic.reason is RuleUnsupportedReason.UNSUPPORTED_LANGUAGE
    assert diagnostic.source_span.text == "Consult the legacy table."
    assert (
        rule_ir.normalized_text[diagnostic.source_span.start : diagnostic.source_span.end]
        == diagnostic.source_span.text
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
            "This unit is eligible to declare a charge in a turn in  which it Advanced.",
            None,
            None,
            RuleTargetKind.THIS_UNIT,
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


def test_phase17c_advance_charge_eligibility_compiles_to_rule_exception_grant() -> None:
    rule_ir = _compiled(
        "This unit is eligible to declare a charge in a turn in  which it Advanced."
    ).rule_ir
    clause = rule_ir.clauses[0]
    effect = next(
        effect for effect in clause.effects if effect.kind is RuleEffectKind.GRANT_ABILITY
    )

    assert rule_ir.is_supported
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_UNIT
    assert parameter_payload(effect.parameters) == {"ability": "can_advance_and_charge"}


def test_phase17c_fall_back_shoot_eligibility_compiles_to_rule_exception_grant() -> None:
    rule_ir = _compiled("This unit is eligible to shoot in a turn in  which it Fell Back.").rule_ir
    clause = rule_ir.clauses[0]
    effect = next(
        effect for effect in clause.effects if effect.kind is RuleEffectKind.GRANT_ABILITY
    )

    assert rule_ir.is_supported
    assert RuleIR.from_payload(rule_ir.to_payload()).to_payload() == rule_ir.to_payload()
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_UNIT
    assert parameter_payload(effect.parameters) == {"ability": "can_fall_back_and_shoot"}
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
    )


def test_phase17c_leading_model_advance_charge_rerolls_compile_to_two_permissions() -> None:
    rule_ir = _compiled(
        "While this model is leading a unit, you can re-roll  Advance and Charge rolls "
        "made for that unit."
    ).rule_ir
    clause = rule_ir.clauses[0]
    reroll_effects = tuple(
        effect for effect in clause.effects if effect.kind is RuleEffectKind.REROLL_PERMISSION
    )

    assert rule_ir.is_supported
    assert any(
        condition.kind is RuleConditionKind.TARGET_CONSTRAINT
        and parameter_payload(condition.parameters) == {"relationship": "this_model_leading_unit"}
        for condition in clause.conditions
    )
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.SELECTED_UNIT
    assert tuple(parameter_payload(effect.parameters) for effect in reroll_effects) == (
        {"roll_type": "advance"},
        {"roll_type": "charge"},
    )


def test_phase17c_this_model_advance_charge_rerolls_compile_to_two_permissions() -> None:
    raw_text = "You can re\u2011roll Advance and Charge rolls made for this model."
    compiled = _compiled(raw_text)
    clause = compiled.rule_ir.clauses[0]
    reroll_effects = tuple(
        effect for effect in clause.effects if effect.kind is RuleEffectKind.REROLL_PERMISSION
    )

    assert compiled.source_text.normalized_text == (
        "You can re-roll Advance and Charge rolls made for this model."
    )
    assert compiled.rule_ir.is_supported
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_MODEL
    assert tuple(parameter_payload(effect.parameters) for effect in reroll_effects) == (
        {"roll_type": "advance"},
        {"roll_type": "charge"},
    )
    assert catalog_rule_ir_consumers_for_rule(compiled.rule_ir) == (
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(compiled.rule_ir)) == {
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    }


def test_phase17c_leading_model_scoped_weapon_keyword_grant_compiles_to_generic_scope() -> None:
    rule_ir = _compiled(
        "While this model is leading a unit, melee weapons equipped by models in that unit "
        "have the  [LETHAL HITS] ability."
    ).rule_ir
    clause = rule_ir.clauses[0]
    weapon_effect = next(
        effect for effect in clause.effects if effect.kind is RuleEffectKind.GRANT_WEAPON_ABILITY
    )

    assert rule_ir.is_supported
    assert any(
        condition.kind is RuleConditionKind.TARGET_CONSTRAINT
        and parameter_payload(condition.parameters) == {"relationship": "this_model_leading_unit"}
        for condition in clause.conditions
    )
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.SELECTED_UNIT
    assert parameter_payload(weapon_effect.parameters) == {
        "target_scope": "models_in_selected_unit",
        "weapon_ability": "Lethal Hits",
        "weapon_scope": "melee",
    }


@pytest.mark.parametrize(
    ("raw_text", "expected_scope", "expected_parameters"),
    [
        (
            "Ranged weapons equipped by models in that unit have the [DEVASTATING WOUNDS] ability.",
            "ranged",
            {
                "target_scope": "models_in_selected_unit",
                "weapon_ability": "Devastating Wounds",
                "weapon_scope": "ranged",
            },
        ),
        (
            "All weapons equipped by models in that unit have the [SUSTAINED HITS 1] ability.",
            "all",
            {
                "target_scope": "models_in_selected_unit",
                "weapon_ability": "Sustained Hits",
                "weapon_ability_value": 1,
                "weapon_scope": "all",
            },
        ),
        (
            "Weapons equipped by models in that unit have the [LANCE] ability.",
            "all",
            {
                "target_scope": "models_in_selected_unit",
                "weapon_ability": "Lance",
                "weapon_scope": "all",
            },
        ),
    ],
)
def test_phase17c_scoped_weapon_keyword_grant_variants_compile_to_generic_scope(
    raw_text: str,
    expected_scope: str,
    expected_parameters: dict[str, object],
) -> None:
    rule_ir = _compiled(raw_text).rule_ir
    effect = next(
        effect for effect in _effects(rule_ir) if effect.kind is RuleEffectKind.GRANT_WEAPON_ABILITY
    )
    parameters = parameter_payload(effect.parameters)

    assert rule_ir.is_supported
    assert parameters["weapon_scope"] == expected_scope
    assert parameters == expected_parameters


def test_phase17c_single_charge_reroll_permission_compiles_with_unit_target_suffix() -> None:
    rule_ir = _compiled("This unit can re-roll Charge rolls made for this unit.").rule_ir
    clause = rule_ir.clauses[0]
    effect = next(
        effect for effect in clause.effects if effect.kind is RuleEffectKind.REROLL_PERMISSION
    )

    assert rule_ir.is_supported
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_UNIT
    assert parameter_payload(effect.parameters) == {"roll_type": "charge"}


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


def test_phase17c_lord_of_change_named_weapon_choice_compiles_to_semantic_ir() -> None:
    rule_ir = _compiled(
        "In your Shooting phase, select one of the following abilities: [IGNORES COVER]; "
        "[LETHAL HITS]; [SUSTAINED HITS D3]. Until the end of the phase, this model's "
        "Bolt of Change has that ability."
    ).rule_ir
    clause = rule_ir.clauses[0]

    assert rule_ir.is_supported
    assert RuleIR.from_payload(rule_ir.to_payload()).to_payload() == rule_ir.to_payload()
    assert len(rule_ir.clauses) == 1
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert parameter_payload(clause.trigger.parameters) == {
        "edge": "during",
        "owner": "active_player",
        "phase": "shooting",
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_MODEL
    assert clause.duration is not None
    assert clause.duration.kind is RuleDurationKind.UNTIL_TIMING_ENDPOINT
    assert parameter_payload(clause.duration.parameters) == {"endpoint": "phase"}
    assert tuple(parameter_payload(effect.parameters) for effect in clause.effects) == (
        {
            "selection_group_id": "weapon_ability_choice_0024",
            "selection_kind": "select_one",
            "selection_option_id": "option_001_ignores_cover",
            "selection_option_index": 1,
            "target_scope": "this_model",
            "weapon_ability": "Ignores Cover",
            "weapon_name": "Bolt of Change",
        },
        {
            "selection_group_id": "weapon_ability_choice_0024",
            "selection_kind": "select_one",
            "selection_option_id": "option_002_lethal_hits",
            "selection_option_index": 2,
            "target_scope": "this_model",
            "weapon_ability": "Lethal Hits",
            "weapon_name": "Bolt of Change",
        },
        {
            "selection_group_id": "weapon_ability_choice_0024",
            "selection_kind": "select_one",
            "selection_option_id": "option_003_sustained_hits_d3",
            "selection_option_index": 3,
            "target_scope": "this_model",
            "weapon_ability": "Sustained Hits",
            "weapon_ability_value": "D3",
            "weapon_name": "Bolt of Change",
        },
    )
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        "catalog-ir:weapon-keyword-grant:ignores-cover",
        "catalog-ir:weapon-keyword-grant:lethal-hits",
        "catalog-ir:weapon-keyword-grant:sustained-hits",
    )
    assert (
        ability_support_rollup_for_rule_ir(
            source_ability_id="source:daemonspark",
            ability_name="Daemonspark",
            rule_ir=rule_ir,
        ).overall_ability_support
        is AbilityOverallSupport.FULL
    )


def test_phase17c_named_weapon_choice_generalizes_to_multiple_weapon_names() -> None:
    rule_ir = _compiled(
        "In your Shooting phase, select one of the following abilities: [LETHAL HITS]; "
        "[SUSTAINED HITS 1]. Until the end of the phase, this unit's storm staff and "
        "prism cannon have that ability."
    ).rule_ir
    clause = rule_ir.clauses[0]

    assert rule_ir.is_supported
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_UNIT
    assert tuple(parameter_payload(effect.parameters) for effect in clause.effects) == (
        {
            "selection_group_id": "weapon_ability_choice_0024",
            "selection_kind": "select_one",
            "selection_option_id": "option_001_lethal_hits",
            "selection_option_index": 1,
            "target_scope": "models_in_this_unit",
            "weapon_ability": "Lethal Hits",
            "weapon_names": "storm staff|prism cannon",
        },
        {
            "selection_group_id": "weapon_ability_choice_0024",
            "selection_kind": "select_one",
            "selection_option_id": "option_002_sustained_hits_1",
            "selection_option_index": 2,
            "target_scope": "models_in_this_unit",
            "weapon_ability": "Sustained Hits",
            "weapon_ability_value": 1,
            "weapon_names": "storm staff|prism cannon",
        },
    )
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        "catalog-ir:weapon-keyword-grant:lethal-hits",
        "catalog-ir:weapon-keyword-grant:sustained-hits",
    )


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


def test_phase17c_enemy_fall_back_desperate_escape_aura_compiles_to_semantic_ir() -> None:
    rule_ir = _compiled(
        "Each time an enemy unit (excluding Monsters and Vehicles) within Engagement Range "
        "of one or more units from your army with this ability Falls Back, models in that "
        "enemy unit must take Desperate Escape tests. When doing so, if that enemy unit is "
        "also Battle\u2011shocked, subtract 1 from each of those Desperate Escape tests."
    ).rule_ir
    force_clause = rule_ir.clauses[0]
    modifier_clause = rule_ir.clauses[1]
    force_effect = force_clause.effects[0]
    modifier_effect = modifier_clause.effects[0]
    force_distance = next(
        condition
        for condition in force_clause.conditions
        if condition.kind is RuleConditionKind.DISTANCE_PREDICATE
    )
    force_keyword_gate = next(
        condition
        for condition in force_clause.conditions
        if condition.kind is RuleConditionKind.KEYWORD_GATE
    )

    assert rule_ir.is_supported
    assert RuleIR.from_payload(rule_ir.to_payload()).to_payload() == rule_ir.to_payload()
    assert len(rule_ir.clauses) == 2
    assert force_clause.template_id == "phase17c:desperate-escape-requirement"
    assert force_clause.trigger is not None
    assert force_clause.trigger.kind is RuleTriggerKind.UNIT_SELECTED
    assert parameter_payload(force_clause.trigger.parameters) == {
        "selected_unit_allegiance": "enemy",
        "selection": "fall_back",
        "timing_window": "just_after_enemy_unit_selected_to_fall_back",
    }
    assert force_clause.target is not None
    assert force_clause.target.kind is RuleTargetKind.ENEMY_UNIT
    assert parameter_payload(force_keyword_gate.parameters) == {
        "excluded_keyword_any": "MONSTER|VEHICLE",
        "gate_subject": "falling_back_unit",
    }
    assert parameter_payload(force_distance.parameters) == {
        "distance_inches": None,
        "negated": False,
        "object_ability_scope": "this_ability",
        "object_kind": "unit",
        "object_owner": "your_army",
        "object_quantity": "one_or_more",
        "predicate": "within_engagement_range",
        "qualifier": None,
        "range_kind": "engagement_range",
    }
    assert force_effect.kind is RuleEffectKind.FORCE_DESPERATE_ESCAPE_TESTS
    assert parameter_payload(force_effect.parameters) == {
        "required": True,
        "roll_type": "desperate_escape",
        "target_scope": "models_in_target_unit",
    }
    assert modifier_clause.trigger is not None
    assert modifier_clause.trigger.kind is RuleTriggerKind.DICE_ROLL
    assert parameter_payload(modifier_clause.trigger.parameters) == {
        "roll_type": "desperate_escape",
        "source_context": "previous_effect",
        "timing_window": "desperate_escape_test",
    }
    assert modifier_clause.target is not None
    assert modifier_clause.target.kind is RuleTargetKind.ENEMY_UNIT
    assert _condition_payload(modifier_clause, RuleConditionKind.TARGET_CONSTRAINT) == {
        "gate_subject": "that_enemy_unit",
        "relationship": "target_unit_has_status",
        "status": "battle_shocked",
    }
    assert modifier_effect.kind is RuleEffectKind.MODIFY_DICE_ROLL
    assert parameter_payload(modifier_effect.parameters) == {
        "delta": -1,
        "roll_type": "desperate_escape",
    }
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) >= {
        CATALOG_IR_DESPERATE_ESCAPE_ROLL_MODIFIER_CONSUMER_ID,
        CATALOG_IR_FORCE_DESPERATE_ESCAPE_CONSUMER_ID,
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


def test_phase17c_aura_target_faction_keyword_sequence_compiles_to_keyword_gates() -> None:
    rule_ir = _compiled(
        "Daemon Lord of Khorne (Aura): While a friendly Khorne Legiones Daemonica "
        'unit is within 6" of this model, each time a model in that unit makes a '
        "melee attack, add 1 to the Hit roll."
    ).rule_ir
    clause = rule_ir.clauses[0]
    target = clause.target
    keyword_gates = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.KEYWORD_GATE
    )
    distance_condition = next(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.DISTANCE_PREDICATE
    )

    assert rule_ir.is_supported
    assert target is not None
    assert target.kind is RuleTargetKind.AURA_UNITS
    assert parameter_payload(target.parameters) == {
        "allegiance": "friendly",
        "eligible_target": "aura_units",
        "required_keyword_sequence": "KHORNE|LEGIONES_DAEMONICA",
    }
    assert tuple(
        parameter_payload(condition.parameters)["required_keyword"] for condition in keyword_gates
    ) == ("KHORNE", "LEGIONES_DAEMONICA")
    assert parameter_payload(distance_condition.parameters) == {
        "distance_inches": 6.0,
        "negated": False,
        "object_kind": "model",
        "object_reference": "this",
        "predicate": "within",
        "qualifier": None,
        "range_kind": "numeric_range",
    }


@pytest.mark.parametrize("allegiance", ["Khorne", "Nurgle", "Tzeentch", "Slaanesh"])
def test_phase17c_shadow_of_chaos_aura_compiles_to_contextual_status(
    allegiance: str,
) -> None:
    rule_ir = _compiled(
        f"Daemonic Shadow (Aura): While a friendly {allegiance} Legiones Daemonica "
        'unit is within 6" of this model, that unit is within your army\u2019s Shadow of Chaos.'
    ).rule_ir
    clause = rule_ir.clauses[0]
    target = clause.target
    status_effect = next(
        effect for effect in clause.effects if effect.kind is RuleEffectKind.SET_CONTEXTUAL_STATUS
    )
    keyword_gates = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.KEYWORD_GATE
    )

    assert rule_ir.is_supported
    assert target is not None
    assert target.kind is RuleTargetKind.AURA_UNITS
    assert parameter_payload(target.parameters) == {
        "allegiance": "friendly",
        "eligible_target": "aura_units",
        "required_keyword_sequence": f"{allegiance.upper()}|LEGIONES_DAEMONICA",
    }
    assert {
        parameter_payload(condition.parameters)["required_keyword"] for condition in keyword_gates
    } == {allegiance.upper(), "LEGIONES_DAEMONICA"}
    assert parameter_payload(status_effect.parameters) == {
        "owner": "your_army",
        "rules_context": "shadow_of_chaos",
        "status": "within_shadow_of_chaos",
    }


def test_phase17c_enemy_aura_target_keyword_compiles_to_keyword_gate() -> None:
    rule_ir = _compiled(
        'Ded Glowy Ammo (Aura): While an enemy Infantry unit is within 6" of this '
        "model, subtract 1 from the Toughness characteristic of models in that unit."
    ).rule_ir
    clause = rule_ir.clauses[0]
    target = clause.target
    keyword_gates = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.KEYWORD_GATE
    )
    effect = clause.effects[0]

    assert rule_ir.is_supported
    assert target is not None
    assert target.kind is RuleTargetKind.AURA_UNITS
    assert parameter_payload(target.parameters) == {
        "allegiance": "enemy",
        "eligible_target": "aura_units",
        "required_keyword": "INFANTRY",
    }
    assert tuple(
        parameter_payload(condition.parameters)["required_keyword"] for condition in keyword_gates
    ) == ("INFANTRY",)
    assert effect.kind is RuleEffectKind.MODIFY_CHARACTERISTIC
    assert parameter_payload(effect.parameters) == {"characteristic": "toughness", "delta": -1}


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


def test_phase17c_compiler_payload_boundary_is_fail_fast() -> None:
    source = RuleSourceText.from_raw(
        source_id="phase17c:rule:payload-boundary",
        raw_text="Gain 1CP.",
    )
    compiled = compile_rule_source_text(source)
    second_source = RuleSourceText.from_raw(
        source_id="phase17c:rule:payload-boundary:second",
        raw_text="Score 1VP.",
    )
    stale_effect = replace(
        compiled.rule_ir.clauses[0].effects[0],
        parameters=(RuleParameter(key="delta", value=2),),
    )
    stale_rule_ir = replace(
        compiled.rule_ir,
        clauses=(
            replace(
                compiled.rule_ir.clauses[0],
                effects=(stale_effect,),
            ),
        ),
    )
    stale_compiled_payload = compiled.to_payload()
    stale_compiled_payload["rule_ir"] = stale_rule_ir.to_payload()
    identity = compiler_identity_payload()
    invalid_parsed_payload = source.parsed_tokens.to_payload()
    invalid_parsed_payload["keywords"] = [
        {
            "text": "BAD",
            "start": 0,
            "end": 3,
            "keyword": "BAD",
        }
    ]

    assert (
        compile_normalized_rule_text_payload(
            source_id=source.source_id,
            normalized_text=source.normalized_text,
            parsed_tokens=source.parsed_tokens.to_payload(),
        ).to_payload()
        == compiled.rule_ir.to_payload()
    )
    assert identity == {
        "compiler_version": "phase17c-rule-compiler-v1",
        "parser_version": "phase17c-rule-parser-v1",
        "ir_schema_version": "phase17c-rule-ir-v1",
    }
    assert tuple(
        compiled_source.source_text.source_id
        for compiled_source in compile_rule_source_texts((second_source, source))
    ) == (source.source_id, second_source.source_id)
    with pytest.raises(RuleCompilerError, match="requires RuleSourceText"):
        compile_rule_source_text(cast(RuleSourceText, object()))
    with pytest.raises(RuleCompilerError, match="source_texts must be a tuple"):
        compile_rule_source_texts(cast(tuple[RuleSourceText, ...], []))
    with pytest.raises(RuleCompilerError, match="parsed_tokens must be ParsedRuleText"):
        compile_normalized_rule_text(
            source_id=source.source_id,
            normalized_text=source.normalized_text,
            parsed_tokens=cast(Any, object()),
        )
    with pytest.raises(RuleCompilerError, match="payload contains stale rule_ir"):
        CompiledRuleSource.from_payload(stale_compiled_payload)
    with pytest.raises(RuleCompilerError, match="source_text must be RuleSourceText"):
        CompiledRuleSource(
            source_text=cast(RuleSourceText, object()),
            rule_ir=compiled.rule_ir,
        )
    with pytest.raises(RuleCompilerError, match="rule_ir must be RuleIR"):
        CompiledRuleSource(
            source_text=source,
            rule_ir=cast(RuleIR, object()),
        )
    with pytest.raises(RuleCompilerError, match="source_id must match"):
        CompiledRuleSource(
            source_text=RuleSourceText.from_raw(
                source_id="phase17c:rule:different-source",
                raw_text="Gain 1CP.",
            ),
            rule_ir=compiled.rule_ir,
        )
    with pytest.raises(RuleCompilerError, match="normalized_text must match"):
        CompiledRuleSource(
            source_text=RuleSourceText.from_raw(
                source_id=source.source_id,
                raw_text="Gain 2CP.",
            ),
            rule_ir=compiled.rule_ir,
        )
    with pytest.raises(RuleCompilerError, match="compiler_version must not be empty"):
        CompiledRuleSource(source_text=source, rule_ir=compiled.rule_ir, compiler_version="")
    with pytest.raises(RuleCompilerError, match="compiler_version must be a string"):
        CompiledRuleSource(
            source_text=source,
            rule_ir=compiled.rule_ir,
            compiler_version=cast(str, 1),
        )
    with pytest.raises(RuleCompilerError, match="Parsed rule-text payload is invalid"):
        compile_normalized_rule_text_payload(
            source_id=source.source_id,
            normalized_text=source.normalized_text,
            parsed_tokens=invalid_parsed_payload,
        )


def test_phase17c_rule_ir_structural_validators_are_fail_fast() -> None:
    span = TextSpan(text="Gain 1CP.", start=0, end=9)
    second_span = TextSpan(text="Move.", start=10, end=15)
    command_point_effect = RuleEffectSpec(
        kind=RuleEffectKind.MODIFY_COMMAND_POINTS,
        source_span=span,
        parameters=(RuleParameter(key="delta", value=1),),
    )
    move_effect = RuleEffectSpec(
        kind=RuleEffectKind.MODIFY_MOVE_DISTANCE,
        source_span=second_span,
        parameters=(RuleParameter(key="delta_inches", value=1),),
    )
    clause = RuleClause(
        clause_id="phase17c:rule:structural:clause:001",
        source_span=span,
        effects=(command_point_effect,),
    )
    rule_ir = RuleIR(
        rule_id="phase17c:rule:structural",
        source_id="phase17c:rule:structural",
        normalized_text="Gain 1CP.",
        parser_version="phase17c-rule-parser-v1",
        clauses=(clause,),
    )
    stale_payload = rule_ir.to_payload()
    stale_payload["ir_hash"] = "stale"

    assert RuleIR.from_payload(rule_ir.to_payload()).to_payload() == rule_ir.to_payload()
    with pytest.raises(RuleIRError, match="blocking must be a boolean"):
        RuleParseDiagnostic(
            reason=RuleUnsupportedReason.UNSUPPORTED_LANGUAGE,
            message="Unsupported.",
            source_span=span,
            blocking=cast(bool, "yes"),
        )
    with pytest.raises(RuleIRError, match="trigger must be a RuleTrigger"):
        RuleClause(
            clause_id="phase17c:rule:bad-trigger",
            source_span=span,
            trigger=cast(RuleTrigger, object()),
            effects=(command_point_effect,),
        )
    with pytest.raises(RuleIRError, match="target must be a RuleTargetSpec"):
        RuleClause(
            clause_id="phase17c:rule:bad-target",
            source_span=span,
            target=cast(RuleTargetSpec, object()),
            effects=(command_point_effect,),
        )
    with pytest.raises(RuleIRError, match="duration must be a RuleDuration"):
        RuleClause(
            clause_id="phase17c:rule:bad-duration",
            source_span=span,
            duration=cast(RuleDuration, object()),
            effects=(command_point_effect,),
        )
    with pytest.raises(RuleIRError, match="supported components or unsupported_reason"):
        RuleClause(clause_id="phase17c:rule:empty-clause", source_span=span)
    with pytest.raises(RuleIRError, match="Unsupported RuleClause must include diagnostics"):
        RuleClause(
            clause_id="phase17c:rule:unsupported-without-diagnostic",
            source_span=span,
            unsupported_reason=RuleUnsupportedReason.UNSUPPORTED_LANGUAGE,
        )
    with pytest.raises(RuleIRError, match="clauses must not be empty"):
        RuleIR(
            rule_id="phase17c:rule:no-clauses",
            source_id="phase17c:rule:no-clauses",
            normalized_text="Gain 1CP.",
            parser_version="phase17c-rule-parser-v1",
            clauses=(),
        )
    with pytest.raises(RuleIRError, match="ir_hash is stale"):
        RuleIR.from_payload(stale_payload)
    with pytest.raises(RuleIRError, match="RuleParameter key must be a string"):
        RuleParameter(key=cast(str, 1), value=1)
    with pytest.raises(RuleIRError, match="RuleParameter key must not be empty"):
        RuleParameter(key="", value=1)
    with pytest.raises(RuleIRError, match="float must be finite"):
        RuleParameter(key="amount", value=float("inf"))
    with pytest.raises(RuleIRError, match="JSON scalar"):
        RuleParameter(key="amount", value=cast(RuleParameterValue, object()))
    with pytest.raises(RuleIRError, match="source_span must be a TextSpan"):
        RuleEffectSpec(
            kind=RuleEffectKind.MODIFY_COMMAND_POINTS,
            source_span=cast(TextSpan, object()),
        )
    with pytest.raises(RuleIRError, match="parameters must be a tuple"):
        RuleEffectSpec(
            kind=RuleEffectKind.MODIFY_COMMAND_POINTS,
            source_span=span,
            parameters=cast(tuple[RuleParameter, ...], []),
        )
    with pytest.raises(RuleIRError, match="parameters must contain RuleParameter values"):
        RuleEffectSpec(
            kind=RuleEffectKind.MODIFY_COMMAND_POINTS,
            source_span=span,
            parameters=cast(tuple[RuleParameter, ...], (object(),)),
        )
    with pytest.raises(RuleIRError, match="parameters must not contain duplicate keys"):
        RuleEffectSpec(
            kind=RuleEffectKind.MODIFY_COMMAND_POINTS,
            source_span=span,
            parameters=(
                RuleParameter(key="delta", value=1),
                RuleParameter(key="delta", value=2),
            ),
        )
    with pytest.raises(RuleIRError, match="conditions must be a tuple"):
        RuleClause(
            clause_id="phase17c:rule:bad-condition-tuple",
            source_span=span,
            conditions=cast(tuple[RuleCondition, ...], []),
            effects=(command_point_effect,),
        )
    with pytest.raises(RuleIRError, match="conditions contains an invalid value"):
        RuleClause(
            clause_id="phase17c:rule:bad-condition-value",
            source_span=span,
            conditions=cast(tuple[RuleCondition, ...], (object(),)),
            effects=(command_point_effect,),
        )
    with pytest.raises(RuleIRError, match="clause IDs must be unique"):
        RuleIR(
            rule_id="phase17c:rule:duplicate-clauses",
            source_id="phase17c:rule:duplicate-clauses",
            normalized_text="Gain 1CP.",
            parser_version="phase17c-rule-parser-v1",
            clauses=(clause, clause),
        )
    with pytest.raises(RuleIRError, match="deterministically ordered"):
        RuleIR(
            rule_id="phase17c:rule:clause-order",
            source_id="phase17c:rule:clause-order",
            normalized_text="Gain 1CP. Move.",
            parser_version="phase17c-rule-parser-v1",
            clauses=(
                RuleClause(
                    clause_id="phase17c:rule:clause-order:002",
                    source_span=second_span,
                    effects=(move_effect,),
                ),
                clause,
            ),
        )
    with pytest.raises(RuleIRError, match="outside normalized_text"):
        RuleIR(
            rule_id="phase17c:rule:outside-span",
            source_id="phase17c:rule:outside-span",
            normalized_text="Gain",
            parser_version="phase17c-rule-parser-v1",
            clauses=(clause,),
        )
    with pytest.raises(RuleIRError, match="text does not match normalized_text"):
        RuleIR(
            rule_id="phase17c:rule:mismatched-span",
            source_id="phase17c:rule:mismatched-span",
            normalized_text="Lost 1CP.",
            parser_version="phase17c-rule-parser-v1",
            clauses=(clause,),
        )


@pytest.mark.parametrize(
    ("converter", "non_string_error", "unsupported_error"),
    [
        (rule_trigger_kind_from_token, "RuleTriggerKind token must be a string", "Unsupported"),
        (
            rule_condition_kind_from_token,
            "RuleConditionKind token must be a string",
            "Unsupported",
        ),
        (rule_target_kind_from_token, "RuleTargetKind token must be a string", "Unsupported"),
        (rule_effect_kind_from_token, "RuleEffectKind token must be a string", "Unsupported"),
        (rule_duration_kind_from_token, "RuleDurationKind token must be a string", "Unsupported"),
        (
            rule_unsupported_reason_from_token,
            "RuleUnsupportedReason token must be a string",
            "Unsupported",
        ),
    ],
)
def test_phase17c_rule_ir_token_converters_reject_invalid_tokens(
    converter: Any,
    non_string_error: str,
    unsupported_error: str,
) -> None:
    with pytest.raises(RuleIRError, match=non_string_error):
        converter(1)
    with pytest.raises(RuleIRError, match=unsupported_error):
        converter("not-a-token")


def _compiled(raw_text: str) -> CompiledRuleSource:
    source_suffix = hashlib.sha256(raw_text.encode()).hexdigest()[:12]
    return compile_rule_source_text(
        RuleSourceText.from_raw(source_id=f"phase17c:test:{source_suffix}", raw_text=raw_text)
    )


def _effects(rule_ir: RuleIR) -> tuple[RuleEffectSpec, ...]:
    return tuple(effect for clause in rule_ir.clauses for effect in clause.effects)


def _conditions(rule_ir: RuleIR) -> tuple[RuleCondition, ...]:
    return tuple(condition for clause in rule_ir.clauses for condition in clause.conditions)


def _condition_payload(
    clause: RuleClause,
    condition_kind: RuleConditionKind,
) -> dict[str, RuleParameterValue]:
    matches = tuple(
        condition for condition in clause.conditions if condition.kind is condition_kind
    )
    assert len(matches) == 1
    return parameter_payload(matches[0].parameters)


def _descriptor_from_rule_ir(rule_ir: RuleIR) -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id="champion-slayer",
        name="Champion Slayer",
        source_id="source:champion-slayer",
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="Champion Slayer compound ability.",
        rule_ir_payload=cast(CatalogJsonObject, rule_ir.to_payload()),
        rule_ir_diagnostics=tuple(
            cast(CatalogJsonObject, diagnostic.to_payload()) for diagnostic in rule_ir.diagnostics
        ),
    )
