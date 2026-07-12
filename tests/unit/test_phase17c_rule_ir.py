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
from warhammer40k_core.engine.abilities import (
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilityTimingDescriptor,
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
from warhammer40k_core.engine.catalog_command_point_support import (
    CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID,
    CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
    clause_is_supported_command_point_gain,
    clause_is_supported_destroyed_unit_command_point_gain,
    clause_is_supported_phase_command_point_gain,
    clause_is_supported_stratagem_cost_modifier,
    command_point_consumer_ids_for_clause,
    command_point_effect,
)
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_FIGHT_ACTIVATION_MOVEMENT_DISTANCE_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_movement_transit import (
    movement_mode_tokens_or_none as _movement_mode_tokens_or_none,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
    CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_DESPERATE_ESCAPE_ROLL_MODIFIER_CONSUMER_ID,
    CATALOG_IR_DESTROYED_UNIT_RESTORE_LOST_WOUNDS_CONSUMER_ID,
    CATALOG_IR_FIRST_DEATH_RETURN_CONSUMER_ID,
    CATALOG_IR_FIRST_DEATH_RETURN_PHASE_END_CONSUMER_ID,
    CATALOG_IR_FORCE_DESPERATE_ESCAPE_CONSUMER_ID,
    CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID,
    CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_MINIMUM_UNMODIFIED_HIT_SUCCESS_CONSUMER_ID,
    CATALOG_IR_MOVEMENT_TRANSIT_PERMISSION_CONSUMER_ID,
    CATALOG_IR_NAMED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
    CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID,
    CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
    CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
    CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID,
    CATALOG_IR_SETUP_REACTIVE_SHOOT_CHARGE_CONSUMER_ID,
    CATALOG_IR_TRACKED_TARGET_DESTROYED_RESELECT_CONSUMER_ID,
    CATALOG_IR_TRACKED_TARGET_REROLL_CONSUMER_ID,
    CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID,
    CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
    CATALOG_IR_WOUND_ROLL_MODIFIER_CONSUMER_ID,
    CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID,
    _feel_no_pain_source_from_effect,  # pyright: ignore[reportPrivateUsage]
    _movement_transit_permissions_from_clause,  # pyright: ignore[reportPrivateUsage]
    catalog_rule_ir_consumers_for_rule,
    catalog_rule_ir_hook_ids_for_rule,
)
from warhammer40k_core.engine.catalog_unit_move_completed_battle_shock_support import (
    CATALOG_IR_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_CONSUMER_ID,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.hit_success_threshold_parser import hit_success_threshold_effects
from warhammer40k_core.rules.parsed_tokens import (
    ParsedRuleText,
    ParsedRuleTextPayload,
    TextSpan,
)
from warhammer40k_core.rules.rule_compiler import (
    CompiledRuleSource,
    RuleCompilerError,
    compiler_identity_payload,
)
from warhammer40k_core.rules.rule_compiler import (
    compile_normalized_rule_text as _compile_normalized_rule_text,
)
from warhammer40k_core.rules.rule_compiler import (
    compile_normalized_rule_text_payload as _compile_normalized_rule_text_payload,
)
from warhammer40k_core.rules.rule_compiler import (
    compile_rule_source_text as _compile_rule_source_text,
)
from warhammer40k_core.rules.rule_compiler import (
    compile_rule_source_texts as _compile_rule_source_texts,
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
from warhammer40k_core.rules.rule_keyword_sequences import keyword_sequence_tokens
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)

SOURCE_KEYWORD_SEQUENCE_PARTS = (
    datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
)


def compile_rule_source_text(source_text: RuleSourceText) -> CompiledRuleSource:
    return _compile_rule_source_text(
        source_text,
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    )


def compile_rule_source_texts(
    source_texts: tuple[RuleSourceText, ...],
) -> tuple[CompiledRuleSource, ...]:
    return _compile_rule_source_texts(
        source_texts,
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    )


def compile_normalized_rule_text(
    *,
    source_id: str,
    normalized_text: str,
    parsed_tokens: ParsedRuleText,
) -> RuleIR:
    return _compile_normalized_rule_text(
        source_id=source_id,
        normalized_text=normalized_text,
        parsed_tokens=parsed_tokens,
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    )


def compile_normalized_rule_text_payload(
    *,
    source_id: str,
    normalized_text: str,
    parsed_tokens: ParsedRuleTextPayload,
) -> RuleIR:
    return _compile_normalized_rule_text_payload(
        source_id=source_id,
        normalized_text=normalized_text,
        parsed_tokens=parsed_tokens,
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    )


CHAMPION_SLAYER_TEXT = (
    "Each time this model makes a melee attack that targets a Character or Monster unit, "
    "you can re-roll the Wound roll. Each time this model destroys an enemy Character or "
    "Monster unit, this model regains up to D6 lost wounds."
)
SKULLS_FOR_KHORNE_TEXT = (
    "Each time this model makes an attack that targets a Character unit, you can re-roll "
    "the Hit roll and you can re-roll the Wound roll. Each time this model destroys an "
    "enemy Character unit, you gain 1CP."
)
OPPONENT_STRATAGEM_COST_TEXT = (
    'Once per turn, when your opponent targets a unit from their army within 12" of this '
    "model with a stratagem, you can use this ability. If you do, increase the CP cost of "
    "the use of that stratagem by 1CP."
)
OWN_STRATAGEM_COST_TEXT = (
    "Once per battle round, one unit from your army with this ability can use it when its "
    "unit is targeted with a Stratagem. If it does, reduce the CP cost of that use of that "
    "Stratagem by 1CP."
)
DIRECT_OWN_STRATAGEM_COST_TEXT = (
    "Once per turn, when you target this model with a Stratagem, you may reduce the CP cost "
    "of that use of that Stratagem by 1CP."
)
UNNAMED_ZERO_CP_STRATAGEM_COST_TEXT = (
    "Once per battle round, you can target a friendly unit with a Stratagem for 0CP."
)
NAMED_ZERO_CP_STRATAGEM_COST_TEXT = (
    "Once per battle round, you can target this unit with the Fire Overwatch Stratagem for 0CP."
)
POST_TRIGGER_RANGE_STRATAGEM_COST_TEXT = (
    "Each time your opponent targets a unit from their army with a Stratagem, if that unit "
    'is within 12" of the bearer, increase the cost of that use of that Stratagem by 1CP '
    "(this is not cumulative with any other rules that would increase the CP cost of that "
    "Stratagem)."
)
LEADERSHIP_COMMAND_POINT_TEXT = (
    "At the end of your Command phase, if this model is on the battlefield, take a "
    "Leadership test for this model; if that test is passed, you gain 1CP."
)
DIRECT_PHASE_COMMAND_POINT_TEXT = (
    "At the start of your Command phase, if this model is on the battlefield, you gain 1CP."
)
FIXED_ROLL_COMMAND_POINT_TEXT = (
    "At the end of your Command phase, roll one D6: on a 4+, you gain 1CP."
)
THIS_MODEL_NOT_BELOW_HALF_HIT_MODIFIER_TEXT = (
    "Each time this model makes an attack that targets an enemy unit that is not below "
    "Half-strength, add 1 to the Hit roll."
)
PREY_TARGET_TEXT = (
    "At the start of the first battle round, select one enemy unit to be this model\u2019s "
    "prey. Each time a model in this model\u2019s unit makes a melee attack that targets "
    "its prey, you can re\u2011roll the Wound roll. Each time this model\u2019s prey is "
    "destroyed, select one new enemy unit to be this model\u2019s prey."
)
QUARRY_TARGET_TEXT = (
    "At the start of the first battle round, select one enemy unit to be this model's "
    "quarry. Each time this model makes a melee attack that targets its quarry, you can "
    "re-roll the Hit roll and you can re-roll the Wound roll. Each time this model's "
    "quarry is destroyed, select one new enemy unit to be this model's quarry."
)
FIRST_DEATH_RETURN_TEXT = (
    "The first time this model is destroyed, at the end of the phase, roll one D6: on "
    "a 2+, set this model back up on the battlefield as close as possible to where it "
    "was destroyed and not within Engagement Range of one or more enemy units, with "
    "3 wounds remaining."
)
FIRST_DEATH_RETURN_FULL_HEALTH_TEXT = (
    "The first time this unit is destroyed, at the end of the phase, roll one D6: on "
    "a 5+, set this unit back up on the battlefield as close as possible to where it "
    "was destroyed and not within Engagement Range of one or more enemy units, at "
    "full health."
)
MOVE_OVER_MONSTER_VEHICLE_TERRAIN_TEXT = (
    "Each time this model makes a Normal or Advance move, it can move over friendly "
    'Monster and Vehicle models and terrain features that are 4" or less in height '
    "as if they were not there."
)
MOVE_THROUGH_MODELS_TERRAIN_AUTO_PASS_TEXT = (
    "Each time this unit makes a Normal, Advance or Fall Back move, it can move "
    "through models (excluding Titanic models) and terrain features. When doing so, "
    "it can move within Engagement Range of enemy models, but cannot end that move "
    "within Engagement Range of them, and any Desperate Escape test is automatically passed."
)
SETUP_REACTIVE_SHOOT_CHARGE_TEXT = (
    "At the end of your opponent's Movement phase, you can select one enemy unit that was "
    'set up on the battlefield within 12" of this model; this model can then either: '
    "Shoot at that unit, but only if it is an eligible target. Declare a charge. This unit "
    "must end that charge move engaged with the enemy unit you selected (note that even if "
    "this charge is successful, this unit does not receive any Charge bonus this turn)."
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
        CompiledRuleSource.from_payload(
            compiled.to_payload(),
            source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
        ).to_payload()
        == compiled.to_payload()
    )
    assert compiled.rule_ir.is_supported
    assert compiled.rule_ir.parser_version == "phase17c-rule-parser-v2"
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


def test_phase17c_once_per_battle_optional_activation_compiles_to_generic_ir() -> None:
    compiled = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="wahapedia:datasheet-ability:finest-hour",
            raw_text=(
                "Once per battle, at the start of the Fight phase, this model can use this "
                "ability. If it does, until the end of the phase, add 3 to the Attacks "
                "characteristic of melee weapons equipped by this model and those weapons "
                "have the [DEVASTATING WOUNDS] ability."
            ),
        )
    )
    rule_ir = compiled.rule_ir
    clause = rule_ir.clauses[0]

    assert rule_ir.is_supported
    assert len(rule_ir.clauses) == 1
    assert clause.trigger is not None
    assert parameter_payload(clause.trigger.parameters) == {
        "edge": "start",
        "owner": None,
        "phase": "fight",
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_MODEL
    assert [
        parameter_payload(condition.parameters)
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.FREQUENCY_LIMIT
    ] == [
        {
            "activation_kind": "optional_ability_use",
            "max_uses": 1,
            "scope": "battle",
            "usage_subject": "this_model",
        }
    ]
    assert [(effect.kind, parameter_payload(effect.parameters)) for effect in clause.effects] == [
        (
            RuleEffectKind.MODIFY_CHARACTERISTIC,
            {"characteristic": "attacks", "delta": 3, "weapon_scope": "melee"},
        ),
        (
            RuleEffectKind.GRANT_WEAPON_ABILITY,
            {"weapon_ability": "Devastating Wounds", "weapon_scope": "melee"},
        ),
    ]
    assert clause.duration is not None
    assert parameter_payload(clause.duration.parameters) == {"endpoint": "phase"}
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID,
    )
    assert CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID in (
        catalog_rule_ir_hook_ids_for_rule(rule_ir)
    )


def test_phase17c_once_per_battle_without_runtime_timing_is_not_execution_supported() -> None:
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="phase17c:once-per-battle:shooting-start",
            raw_text=(
                "Once per battle, at the start of the Shooting phase, this model can use "
                "this ability. If it does, until the end of the phase, add 3 to the Attacks "
                "characteristic of melee weapons equipped by this model."
            ),
        )
    ).rule_ir

    assert rule_ir.is_supported
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == ()
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == ()


def test_phase17c_once_per_battle_when_it_does_continuation_merges() -> None:
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="phase17c:once-per-battle:when-it-does",
            raw_text=(
                "Once per battle, at the start of the Fight phase, this model can use this "
                "ability. When it does, until the end of the phase, add 3 to the Attacks "
                "characteristic of melee weapons equipped by this model."
            ),
        )
    ).rule_ir

    assert rule_ir.is_supported
    assert len(rule_ir.clauses) == 1
    assert CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID in (
        catalog_rule_ir_consumers_for_rule(rule_ir)
    )


def test_phase17c_setup_reactive_shoot_charge_compiles_to_generic_out_of_phase_actions() -> None:
    rule_ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="phase17c:test:setup-reactive-shoot-charge",
            raw_text=SETUP_REACTIVE_SHOOT_CHARGE_TEXT,
        )
    ).rule_ir

    assert rule_ir.is_supported is True
    assert len(rule_ir.clauses) == 1
    clause = rule_ir.clauses[0]
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert parameter_payload(clause.trigger.parameters) == {
        "edge": "end",
        "owner": "opponent",
        "phase": "movement",
        "timing_window": "end_opponent_movement_phase",
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.ENEMY_UNIT
    assert tuple(effect.kind for effect in clause.effects) == (
        RuleEffectKind.OUT_OF_PHASE_ACTION,
        RuleEffectKind.OUT_OF_PHASE_ACTION,
    )
    effect_parameters = tuple(parameter_payload(effect.parameters) for effect in clause.effects)
    assert effect_parameters[0]["action"] == "shoot"
    assert effect_parameters[0]["eligible_target_required"] is True
    assert effect_parameters[1]["action"] == "charge"
    assert effect_parameters[1]["must_end_engaged_with_selected_unit"] is True
    assert effect_parameters[1]["suppress_charge_bonus"] is True
    assert effect_parameters[1]["suppressed_charge_bonus"] == "fights_first"
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_SETUP_REACTIVE_SHOOT_CHARGE_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_SETUP_REACTIVE_SHOOT_CHARGE_CONSUMER_ID,
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


def test_phase17c_command_point_gain_after_destroying_character_is_structured() -> None:
    rule_ir = _compiled(SKULLS_FOR_KHORNE_TEXT).rule_ir
    attack_clause, gain_clause = rule_ir.clauses

    assert rule_ir.is_supported
    assert RuleIR.from_payload(rule_ir.to_payload()).to_payload() == rule_ir.to_payload()
    assert attack_clause.trigger is not None
    assert parameter_payload(attack_clause.trigger.parameters) == {
        "actor": "this_model",
        "roll_types": ("hit", "wound"),
        "timing_window": "attack_sequence.roll",
    }
    assert tuple(parameter_payload(effect.parameters) for effect in attack_clause.effects) == (
        {"roll_type": "hit"},
        {"roll_type": "wound"},
    )
    assert _condition_payload(attack_clause, RuleConditionKind.TARGET_CONSTRAINT) == {
        "gate_subject": "attack_target",
        "relationship": "this_model_makes_attack",
    }
    assert gain_clause.trigger is not None
    assert gain_clause.trigger.kind is RuleTriggerKind.UNIT_DESTROYED
    assert parameter_payload(gain_clause.trigger.parameters) == {
        "actor": "this_model",
        "destroyed_allegiance": "enemy",
        "destroyed_unit_kind": "unit",
    }
    assert gain_clause.target is not None
    assert gain_clause.target.kind is RuleTargetKind.PLAYER
    assert _condition_payload(gain_clause, RuleConditionKind.KEYWORD_GATE) == {
        "gate_subject": "destroyed_unit",
        "required_keyword_any": ("CHARACTER",),
    }
    assert parameter_payload(gain_clause.effects[0].parameters) == {
        "affected_player": "source_player",
        "delta": 1,
        "operation": "gain",
    }
    assert CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID in catalog_rule_ir_consumers_for_rule(rule_ir)


@pytest.mark.parametrize(
    (
        "text",
        "delta",
        "affected_player",
        "frequency_scope",
        "relationship",
        "usage_scope",
    ),
    [
        (
            OPPONENT_STRATAGEM_COST_TEXT,
            1,
            "opponent",
            "turn",
            "stratagem_targets_unit_within_source_model_range",
            "source_model",
        ),
        (
            OWN_STRATAGEM_COST_TEXT,
            -1,
            "source_player",
            "battle round",
            "stratagem_targets_source_unit",
            "army_ability",
        ),
        (
            DIRECT_OWN_STRATAGEM_COST_TEXT,
            -1,
            "source_player",
            "turn",
            "stratagem_targets_source_unit",
            "source_model",
        ),
    ],
)
def test_phase17c_stratagem_cost_modifiers_are_current_use_semantics(
    text: str,
    delta: int,
    affected_player: str,
    frequency_scope: str,
    relationship: str,
    usage_scope: str,
) -> None:
    rule_ir = _compiled(text).rule_ir
    clause = rule_ir.clauses[0]

    assert rule_ir.is_supported
    assert len(rule_ir.clauses) == 1
    assert RuleIR.from_payload(rule_ir.to_payload()).to_payload() == rule_ir.to_payload()
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.UNIT_SELECTED
    assert parameter_payload(clause.trigger.parameters) == {
        "selected_unit_allegiance": "enemy" if delta > 0 else "friendly",
        "selection": "stratagem_target",
        "source_relationship": relationship,
        "stratagem_user": "opponent" if delta > 0 else "source_player",
        "timing_window": "after_unit_selected_as_stratagem_target",
        "usage_scope": usage_scope,
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.STRATAGEM_USE
    assert _condition_payload(clause, RuleConditionKind.FREQUENCY_LIMIT) == {
        "scope": frequency_scope,
    }
    assert _condition_payload(clause, RuleConditionKind.TARGET_CONSTRAINT) == {
        "gate_subject": "stratagem_target",
        "relationship": relationship,
        "selected_unit_allegiance": "enemy" if delta > 0 else "friendly",
    }
    assert parameter_payload(clause.effects[0].parameters) == {
        "affected_player": affected_player,
        "application_scope": "current_stratagem_use",
        "delta": delta,
        "minimum_cost": 0,
        "operation": "modify_stratagem_cost",
        "optional": True,
        "stacking": "cumulative",
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
    )


def test_phase17c_stratagem_cost_range_after_trigger_and_stacking_are_structured() -> None:
    rule_ir = _compiled(POST_TRIGGER_RANGE_STRATAGEM_COST_TEXT).rule_ir
    clause = rule_ir.clauses[0]

    assert rule_ir.is_supported
    assert clause.trigger is not None
    assert parameter_payload(clause.trigger.parameters) == {
        "selected_unit_allegiance": "enemy",
        "selection": "stratagem_target",
        "source_relationship": "stratagem_targets_unit_within_source_model_range",
        "stratagem_user": "opponent",
        "timing_window": "after_unit_selected_as_stratagem_target",
        "usage_scope": "source_model",
    }
    assert _condition_payload(clause, RuleConditionKind.TARGET_CONSTRAINT) == {
        "gate_subject": "stratagem_target",
        "relationship": "stratagem_targets_unit_within_source_model_range",
        "selected_unit_allegiance": "enemy",
    }
    assert parameter_payload(clause.effects[0].parameters) == {
        "affected_player": "opponent",
        "application_scope": "current_stratagem_use",
        "delta": 1,
        "minimum_cost": 0,
        "operation": "modify_stratagem_cost",
        "optional": False,
        "stacking": "non_cumulative_cost_increase",
    }


def test_phase17c_unnamed_zero_cp_stratagem_rule_reduces_current_use_cost_by_one() -> None:
    rule_ir = _compiled(UNNAMED_ZERO_CP_STRATAGEM_COST_TEXT).rule_ir
    clause = rule_ir.clauses[0]

    assert rule_ir.is_supported
    assert clause.trigger is not None
    assert parameter_payload(clause.trigger.parameters) == {
        "selected_unit_allegiance": "friendly",
        "selection": "stratagem_target",
        "source_relationship": "stratagem_targets_friendly_unit",
        "stratagem_user": "source_player",
        "timing_window": "after_unit_selected_as_stratagem_target",
        "usage_scope": "source_model",
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.STRATAGEM_USE
    assert _condition_payload(clause, RuleConditionKind.FREQUENCY_LIMIT) == {
        "scope": "battle round",
    }
    assert _condition_payload(clause, RuleConditionKind.TARGET_CONSTRAINT) == {
        "gate_subject": "stratagem_target",
        "relationship": "stratagem_targets_friendly_unit",
        "selected_unit_allegiance": "friendly",
    }
    assert parameter_payload(clause.effects[0].parameters) == {
        "affected_player": "source_player",
        "application_scope": "current_stratagem_use",
        "delta": -1,
        "minimum_cost": 0,
        "operation": "modify_stratagem_cost",
        "optional": True,
        "stacking": "cumulative",
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
    )


def test_phase17c_named_zero_cp_stratagem_rule_is_not_reinterpreted_as_reduction() -> None:
    rule_ir = _compiled(NAMED_ZERO_CP_STRATAGEM_COST_TEXT).rule_ir

    assert all(
        effect.kind is not RuleEffectKind.MODIFY_COMMAND_POINTS
        for clause in rule_ir.clauses
        for effect in clause.effects
    )
    assert CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID not in (
        catalog_rule_ir_consumers_for_rule(rule_ir)
    )


def test_phase17c_leadership_gated_command_point_gain_is_structured() -> None:
    rule_ir = _compiled(LEADERSHIP_COMMAND_POINT_TEXT).rule_ir
    clause = rule_ir.clauses[0]

    assert rule_ir.is_supported
    assert RuleIR.from_payload(rule_ir.to_payload()).to_payload() == rule_ir.to_payload()
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert parameter_payload(clause.trigger.parameters) == {
        "edge": "end",
        "owner": "active_player",
        "phase": "command",
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.PLAYER
    assert _condition_payload(clause, RuleConditionKind.TARGET_CONSTRAINT) == {
        "gate_subject": "source_model",
        "relationship": "source_model_on_battlefield",
    }
    assert _condition_payload(clause, RuleConditionKind.DICE_ROLL_GATE) == {
        "comparison": "greater_or_equal",
        "roll_count": 2,
        "roll_expression": "2D6",
        "roll_type": "leadership",
        "success_threshold_source": "target_leadership",
        "test_target": "this_model",
    }
    assert parameter_payload(clause.effects[0].parameters) == {
        "affected_player": "source_player",
        "delta": 1,
        "operation": "gain",
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID,
    )


@pytest.mark.parametrize(
    ("text", "edge", "dice_gate"),
    [
        (DIRECT_PHASE_COMMAND_POINT_TEXT, "start", None),
        (
            FIXED_ROLL_COMMAND_POINT_TEXT,
            "end",
            {
                "comparison": "greater_or_equal",
                "roll_count": 1,
                "roll_expression": "D6",
                "roll_type": "command_point_gain",
                "success_threshold": 4,
            },
        ),
    ],
)
def test_phase17c_phase_command_point_gains_are_structured(
    text: str,
    edge: str,
    dice_gate: dict[str, object] | None,
) -> None:
    rule_ir = _compiled(text).rule_ir
    clause = rule_ir.clauses[0]

    assert rule_ir.is_supported
    assert clause.trigger is not None
    assert parameter_payload(clause.trigger.parameters) == {
        "edge": edge,
        "owner": "active_player",
        "phase": "command",
    }
    gates = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.DICE_ROLL_GATE
    )
    assert tuple(parameter_payload(gate.parameters) for gate in gates) == (
        () if dice_gate is None else (dice_gate,)
    )
    assert parameter_payload(clause.effects[0].parameters) == {
        "affected_player": "source_player",
        "delta": 1,
        "operation": "gain",
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID,
    )


def test_phase17c_command_point_consumer_classifiers_fail_closed_on_ir_drift() -> None:
    destroyed_clause = _compiled(SKULLS_FOR_KHORNE_TEXT).rule_ir.clauses[1]
    phase_clause = _compiled(DIRECT_PHASE_COMMAND_POINT_TEXT).rule_ir.clauses[0]
    fixed_roll_clause = _compiled(FIXED_ROLL_COMMAND_POINT_TEXT).rule_ir.clauses[0]
    cost_clause = _compiled(OPPONENT_STRATAGEM_COST_TEXT).rule_ir.clauses[0]

    with pytest.raises(GameLifecycleError, match="requires RuleClause"):
        command_point_consumer_ids_for_clause(cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="exactly one CP effect"):
        command_point_effect(replace(phase_clause, effects=()))

    assert not clause_is_supported_destroyed_unit_command_point_gain(
        replace(
            destroyed_clause,
            trigger=replace(
                cast(RuleTrigger, destroyed_clause.trigger),
                parameters=(RuleParameter("actor", "this_unit"),),
            ),
        )
    )
    assert not clause_is_supported_destroyed_unit_command_point_gain(
        replace(
            destroyed_clause,
            conditions=tuple(
                condition
                for condition in destroyed_clause.conditions
                if condition.kind is not RuleConditionKind.TARGET_CONSTRAINT
            ),
        )
    )
    assert not clause_is_supported_command_point_gain(
        replace(
            phase_clause,
            target=replace(
                cast(RuleTargetSpec, phase_clause.target),
                parameters=(RuleParameter("relationship", "opponent"),),
            ),
        )
    )
    assert not clause_is_supported_phase_command_point_gain(
        replace(
            phase_clause,
            trigger=replace(
                cast(RuleTrigger, phase_clause.trigger),
                parameters=(
                    RuleParameter("edge", "start"),
                    RuleParameter("owner", "opponent"),
                    RuleParameter("phase", "command"),
                ),
            ),
        )
    )
    frequency = next(
        condition
        for condition in cost_clause.conditions
        if condition.kind is RuleConditionKind.FREQUENCY_LIMIT
    )
    assert not clause_is_supported_phase_command_point_gain(
        replace(phase_clause, conditions=(*phase_clause.conditions, frequency))
    )
    battlefield_constraint = next(
        condition
        for condition in phase_clause.conditions
        if condition.kind is RuleConditionKind.TARGET_CONSTRAINT
    )
    assert not clause_is_supported_phase_command_point_gain(
        replace(
            phase_clause,
            conditions=(battlefield_constraint, replace(battlefield_constraint)),
        )
    )
    assert not clause_is_supported_phase_command_point_gain(
        replace(
            phase_clause,
            conditions=(
                replace(
                    battlefield_constraint,
                    parameters=(
                        RuleParameter("gate_subject", "source_model"),
                        RuleParameter("relationship", "wrong_relationship"),
                    ),
                ),
            ),
        )
    )
    dice_gate = next(
        condition
        for condition in fixed_roll_clause.conditions
        if condition.kind is RuleConditionKind.DICE_ROLL_GATE
    )
    assert not clause_is_supported_phase_command_point_gain(
        replace(
            fixed_roll_clause,
            conditions=(*fixed_roll_clause.conditions, replace(dice_gate)),
        )
    )

    unsupported_cost_clause = replace(
        cost_clause,
        unsupported_reason=RuleUnsupportedReason.UNSUPPORTED_LANGUAGE,
        diagnostics=(
            RuleParseDiagnostic(
                reason=RuleUnsupportedReason.UNSUPPORTED_LANGUAGE,
                message="Unrepresented test residue.",
                source_span=cost_clause.source_span,
            ),
        ),
    )
    assert not clause_is_supported_stratagem_cost_modifier(unsupported_cost_clause)
    assert not clause_is_supported_stratagem_cost_modifier(replace(cost_clause, trigger=None))
    assert not clause_is_supported_stratagem_cost_modifier(
        replace(
            cost_clause,
            target=replace(cast(RuleTargetSpec, cost_clause.target), kind=RuleTargetKind.PLAYER),
        )
    )
    trigger = cast(RuleTrigger, cost_clause.trigger)
    trigger_parameters = parameter_payload(trigger.parameters)
    assert not clause_is_supported_stratagem_cost_modifier(
        replace(
            cost_clause,
            trigger=replace(
                trigger,
                parameters=tuple(
                    RuleParameter(key, "unknown")
                    if key == "usage_scope"
                    else RuleParameter(key, value)
                    for key, value in trigger_parameters.items()
                ),
            ),
        )
    )
    assert not clause_is_supported_stratagem_cost_modifier(
        replace(
            cost_clause,
            conditions=tuple(
                condition
                for condition in cost_clause.conditions
                if condition.kind is not RuleConditionKind.TARGET_CONSTRAINT
            ),
        )
    )
    assert not clause_is_supported_stratagem_cost_modifier(
        replace(
            cost_clause,
            conditions=tuple(
                condition
                for condition in cost_clause.conditions
                if condition.kind is not RuleConditionKind.DISTANCE_PREDICATE
            ),
        )
    )
    assert not clause_is_supported_stratagem_cost_modifier(replace(cost_clause, effects=()))
    effect = cost_clause.effects[0]
    effect_parameters = parameter_payload(effect.parameters)

    def cost_effect(**overrides: RuleParameterValue) -> RuleEffectSpec:
        return replace(
            effect,
            parameters=tuple(
                RuleParameter(key, overrides.get(key, value))
                for key, value in effect_parameters.items()
            ),
        )

    assert not clause_is_supported_stratagem_cost_modifier(
        replace(cost_clause, effects=(cost_effect(delta=0),))
    )
    assert not clause_is_supported_stratagem_cost_modifier(
        replace(cost_clause, effects=(cost_effect(affected_player="source_player"),))
    )
    source_trigger = replace(
        trigger,
        parameters=tuple(
            RuleParameter(key, "source_player")
            if key == "stratagem_user"
            else RuleParameter(key, "friendly")
            if key == "selected_unit_allegiance"
            else RuleParameter(key, value)
            for key, value in trigger_parameters.items()
        ),
    )
    assert not clause_is_supported_stratagem_cost_modifier(
        replace(
            cost_clause,
            trigger=source_trigger,
            effects=(cost_effect(delta=1, affected_player="source_player"),),
        )
    )
    assert not clause_is_supported_stratagem_cost_modifier(
        replace(cost_clause, effects=(cost_effect(delta=-1),))
    )


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
        "required_keyword_any": ("CHARACTER", "MONSTER"),
    }
    assert tuple(effect.kind for effect in clause.effects) == (RuleEffectKind.REROLL_PERMISSION,)
    assert parameter_payload(clause.effects[0].parameters) == {"roll_type": "wound"}


def test_phase17c_this_model_half_strength_attack_hit_modifier_compiles_to_generic_ir() -> None:
    rule_ir = _compiled(THIS_MODEL_NOT_BELOW_HALF_HIT_MODIFIER_TEXT).rule_ir
    clause = rule_ir.clauses[0]

    assert rule_ir.is_supported
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.DICE_ROLL
    assert parameter_payload(clause.trigger.parameters) == {
        "actor": "this_model",
        "roll_type": "hit",
        "target_allegiance": "enemy",
        "timing_window": "attack_sequence.hit",
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_MODEL
    assert _condition_payload(clause, RuleConditionKind.TARGET_CONSTRAINT) == {
        "gate_subject": "attack_target",
        "relationship": "this_model_makes_attack",
        "target_allegiance": "enemy",
        "target_constraint": "target_not_below_half_strength",
    }
    assert tuple(effect.kind for effect in clause.effects) == (RuleEffectKind.MODIFY_DICE_ROLL,)
    assert parameter_payload(clause.effects[0].parameters) == {
        "delta": 1,
        "roll_type": "hit",
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID,
    )
    assert CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID in catalog_rule_ir_hook_ids_for_rule(rule_ir)


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
        "required_keyword_any": ("CHARACTER", "MONSTER"),
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


def test_phase17c_prey_selection_reselection_and_attack_gate_compile_to_semantic_ir() -> None:
    rule_ir = _compiled(PREY_TARGET_TEXT).rule_ir
    selection_clause = rule_ir.clauses[0]
    attack_clause = rule_ir.clauses[1]
    reselection_clause = rule_ir.clauses[2]

    assert rule_ir.is_supported
    assert RuleIR.from_payload(rule_ir.to_payload()).to_payload() == rule_ir.to_payload()
    assert len(rule_ir.clauses) == 3
    assert selection_clause.template_id == "phase17c:tracked-target-selection"
    assert selection_clause.trigger is not None
    assert selection_clause.trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert parameter_payload(selection_clause.trigger.parameters) == {
        "battle_round": 1,
        "edge": "start",
        "phase": "battle_round",
        "timing_window": "battle_round_start",
    }
    assert selection_clause.target is not None
    assert selection_clause.target.kind is RuleTargetKind.ENEMY_UNIT
    assert parameter_payload(selection_clause.target.parameters) == {"allegiance": "enemy"}
    assert tuple(effect.kind for effect in selection_clause.effects) == (
        RuleEffectKind.SELECT_TRACKED_TARGET,
    )
    assert parameter_payload(selection_clause.effects[0].parameters) == {
        "replacement": False,
        "selection_kind": "select_one",
        "target_allegiance": "enemy",
        "target_lifecycle": "until_destroyed",
        "target_scope": "enemy_unit",
        "tracked_target_owner": "this_model",
        "tracked_target_role": "prey",
    }

    assert attack_clause.trigger is not None
    assert attack_clause.trigger.kind is RuleTriggerKind.DICE_ROLL
    assert parameter_payload(attack_clause.trigger.parameters) == {
        "actor": "model_in_this_models_unit",
        "attack_kind": "melee",
        "roll_type": "wound",
        "target_reference": "tracked_target",
        "timing_window": "attack_sequence.wound",
        "tracked_target_owner": "this_model",
        "tracked_target_role": "prey",
    }
    assert attack_clause.target is not None
    assert attack_clause.target.kind is RuleTargetKind.THIS_UNIT
    assert parameter_payload(attack_clause.target.parameters) == {"scope": "this_models_unit"}
    assert _condition_payload(attack_clause, RuleConditionKind.TARGET_CONSTRAINT) == {
        "actor": "model_in_this_models_unit",
        "attack_kind": "melee",
        "gate_subject": "attack_target",
        "relationship": "attack_targets_tracked_target",
        "target_reference": "tracked_target",
        "tracked_target_owner": "this_model",
        "tracked_target_role": "prey",
    }
    assert tuple(effect.kind for effect in attack_clause.effects) == (
        RuleEffectKind.REROLL_PERMISSION,
    )
    assert parameter_payload(attack_clause.effects[0].parameters) == {
        "roll_type": "wound",
        "target_reference": "tracked_target",
        "tracked_target_owner": "this_model",
        "tracked_target_role": "prey",
    }

    assert reselection_clause.trigger is not None
    assert reselection_clause.trigger.kind is RuleTriggerKind.UNIT_DESTROYED
    assert parameter_payload(reselection_clause.trigger.parameters) == {
        "destroyed_unit_kind": "unit",
        "timing_window": "tracked_target_destroyed",
        "tracked_target_owner": "this_model",
        "tracked_target_role": "prey",
    }
    assert reselection_clause.target is not None
    assert reselection_clause.target.kind is RuleTargetKind.ENEMY_UNIT
    assert _condition_payload(reselection_clause, RuleConditionKind.TARGET_CONSTRAINT) == {
        "gate_subject": "destroyed_unit",
        "relationship": "tracked_target_destroyed",
        "target_reference": "tracked_target",
        "tracked_target_owner": "this_model",
        "tracked_target_role": "prey",
    }
    assert tuple(effect.kind for effect in reselection_clause.effects) == (
        RuleEffectKind.SELECT_TRACKED_TARGET,
    )
    assert parameter_payload(reselection_clause.effects[0].parameters) == {
        "replacement": True,
        "selection_kind": "select_one",
        "target_allegiance": "enemy",
        "target_lifecycle": "until_destroyed",
        "target_scope": "enemy_unit",
        "tracked_target_owner": "this_model",
        "tracked_target_role": "prey",
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_TRACKED_TARGET_DESTROYED_RESELECT_CONSUMER_ID,
        CATALOG_IR_TRACKED_TARGET_REROLL_CONSUMER_ID,
        CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_TRACKED_TARGET_DESTROYED_RESELECT_CONSUMER_ID,
        CATALOG_IR_TRACKED_TARGET_REROLL_CONSUMER_ID,
        CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID,
    )
    assert (
        ability_support_rollup_for_rule_ir(
            source_ability_id="source:prey",
            ability_name="Prey",
            rule_ir=rule_ir,
        ).overall_ability_support
        is AbilityOverallSupport.FULL
    )


def test_phase17c_quarry_selection_supports_this_model_hit_and_wound_rerolls() -> None:
    rule_ir = _compiled(QUARRY_TARGET_TEXT).rule_ir
    selection_clause = rule_ir.clauses[0]
    attack_clause = rule_ir.clauses[1]
    reselection_clause = rule_ir.clauses[2]

    assert rule_ir.is_supported
    assert RuleIR.from_payload(rule_ir.to_payload()).to_payload() == rule_ir.to_payload()
    assert parameter_payload(selection_clause.effects[0].parameters)["tracked_target_role"] == (
        "quarry"
    )
    assert attack_clause.trigger is not None
    assert attack_clause.trigger.kind is RuleTriggerKind.DICE_ROLL
    assert parameter_payload(attack_clause.trigger.parameters) == {
        "actor": "this_model",
        "attack_kind": "melee",
        "roll_types": ("hit", "wound"),
        "target_reference": "tracked_target",
        "timing_window": "attack_sequence.roll",
        "tracked_target_owner": "this_model",
        "tracked_target_role": "quarry",
    }
    assert attack_clause.target is not None
    assert attack_clause.target.kind is RuleTargetKind.THIS_MODEL
    assert tuple(effect.kind for effect in attack_clause.effects) == (
        RuleEffectKind.REROLL_PERMISSION,
        RuleEffectKind.REROLL_PERMISSION,
    )
    assert tuple(parameter_payload(effect.parameters) for effect in attack_clause.effects) == (
        {
            "roll_type": "hit",
            "target_reference": "tracked_target",
            "tracked_target_owner": "this_model",
            "tracked_target_role": "quarry",
        },
        {
            "roll_type": "wound",
            "target_reference": "tracked_target",
            "tracked_target_owner": "this_model",
            "tracked_target_role": "quarry",
        },
    )
    assert parameter_payload(reselection_clause.effects[0].parameters) == {
        "replacement": True,
        "selection_kind": "select_one",
        "target_allegiance": "enemy",
        "target_lifecycle": "until_destroyed",
        "target_scope": "enemy_unit",
        "tracked_target_owner": "this_model",
        "tracked_target_role": "quarry",
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_TRACKED_TARGET_DESTROYED_RESELECT_CONSUMER_ID,
        CATALOG_IR_TRACKED_TARGET_REROLL_CONSUMER_ID,
        CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_TRACKED_TARGET_DESTROYED_RESELECT_CONSUMER_ID,
        CATALOG_IR_TRACKED_TARGET_REROLL_CONSUMER_ID,
        CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID,
    )


def test_phase17c_first_death_return_fixed_wounds_compiles_to_semantic_ir() -> None:
    rule_ir = _compiled(FIRST_DEATH_RETURN_TEXT).rule_ir
    clause = rule_ir.clauses[0]

    assert rule_ir.is_supported
    assert RuleIR.from_payload(rule_ir.to_payload()).to_payload() == rule_ir.to_payload()
    assert len(rule_ir.clauses) == 1
    assert clause.template_id == "phase17c:first-death-return"
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.MODEL_DESTROYED
    assert parameter_payload(clause.trigger.parameters) == {
        "destroyed_target": "this_model",
        "event_order": "first",
        "resolution_timing": "phase_end",
        "timing_window": "phase_end_after_destroyed",
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_MODEL
    assert _condition_payload(clause, RuleConditionKind.FREQUENCY_LIMIT) == {
        "event": "target_destroyed",
        "event_order": "first",
        "scope": "battle",
    }
    assert _condition_payload(clause, RuleConditionKind.DICE_ROLL_GATE) == {
        "comparison": "greater_or_equal",
        "roll_count": 1,
        "roll_expression": "D6",
        "success_threshold": 2,
    }
    distance = next(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.DISTANCE_PREDICATE
    )
    assert parameter_payload(distance.parameters) == {
        "distance_inches": None,
        "negated": True,
        "object_allegiance": "enemy",
        "object_kind": "unit",
        "object_quantity": "one_or_more",
        "predicate": "within_engagement_range",
        "qualifier": None,
        "range_kind": "engagement_range",
    }
    assert tuple(effect.kind for effect in clause.effects) == (
        RuleEffectKind.RETURN_DESTROYED_TARGET,
    )
    assert parameter_payload(clause.effects[0].parameters) == {
        "action": "set_back_up",
        "placement_anchor": "destroyed_position",
        "placement_kind": "battlefield_set_up",
        "placement_preference": "as_close_as_possible",
        "restore_wounds_mode": "fixed_remaining",
        "target": "this_model",
        "target_lifecycle": "destroyed",
        "target_scope": "destroyed_model",
        "wounds_remaining": 3,
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_FIRST_DEATH_RETURN_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_FIRST_DEATH_RETURN_CONSUMER_ID,
        CATALOG_IR_FIRST_DEATH_RETURN_PHASE_END_CONSUMER_ID,
    )
    assert (
        ability_support_rollup_for_rule_ir(
            source_ability_id="source:first-death-return",
            ability_name="First Death Return",
            rule_ir=rule_ir,
        ).overall_ability_support
        is AbilityOverallSupport.FULL
    )


def test_phase17c_first_death_return_full_health_unit_variant_is_semantic_ir() -> None:
    rule_ir = _compiled(FIRST_DEATH_RETURN_FULL_HEALTH_TEXT).rule_ir
    clause = rule_ir.clauses[0]

    assert rule_ir.is_supported
    assert RuleIR.from_payload(rule_ir.to_payload()).to_payload() == rule_ir.to_payload()
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.UNIT_DESTROYED
    assert parameter_payload(clause.trigger.parameters) == {
        "destroyed_target": "this_unit",
        "event_order": "first",
        "resolution_timing": "phase_end",
        "timing_window": "phase_end_after_destroyed",
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_UNIT
    assert _condition_payload(clause, RuleConditionKind.DICE_ROLL_GATE) == {
        "comparison": "greater_or_equal",
        "roll_count": 1,
        "roll_expression": "D6",
        "success_threshold": 5,
    }
    assert tuple(effect.kind for effect in clause.effects) == (
        RuleEffectKind.RETURN_DESTROYED_TARGET,
    )
    assert parameter_payload(clause.effects[0].parameters) == {
        "action": "set_back_up",
        "placement_anchor": "destroyed_position",
        "placement_kind": "battlefield_set_up",
        "placement_preference": "as_close_as_possible",
        "restore_wounds_mode": "full_health",
        "target": "this_unit",
        "target_lifecycle": "destroyed",
        "target_scope": "destroyed_unit",
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_FIRST_DEATH_RETURN_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_FIRST_DEATH_RETURN_CONSUMER_ID,
        CATALOG_IR_FIRST_DEATH_RETURN_PHASE_END_CONSUMER_ID,
    )


def test_phase17c_move_over_friendly_monsters_vehicles_and_terrain_compiles_to_semantic_ir() -> (
    None
):
    rule_ir = _compiled(MOVE_OVER_MONSTER_VEHICLE_TERRAIN_TEXT).rule_ir
    clause = rule_ir.clauses[0]
    assert clause.trigger is not None
    assert clause.target is not None

    assert rule_ir.is_supported
    assert len(rule_ir.clauses) == 1
    assert clause.trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert parameter_payload(clause.trigger.parameters) == {
        "edge": "during",
        "movement_modes": ("advance", "normal"),
        "phase": "movement",
        "subject": "this_model",
        "timing_window": "model_makes_move",
    }
    assert clause.target.kind is RuleTargetKind.THIS_MODEL
    assert tuple(effect.kind for effect in clause.effects) == (
        RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION,
    )
    assert parameter_payload(clause.effects[0].parameters) == {
        "model_allegiance": "friendly",
        "model_keyword_any": ("MONSTER", "VEHICLE"),
        "movement_modes": ("advance", "normal"),
        "permission": "move_over_as_if_not_there",
        "terrain_height_max_inches": 4.0,
        "terrain_scope": "terrain_features",
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_MOVEMENT_TRANSIT_PERMISSION_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_MOVEMENT_TRANSIT_PERMISSION_CONSUMER_ID,
    )


def test_phase17c_move_over_permission_supports_single_move_mode_and_decimal_height() -> None:
    rule_ir = _compiled(
        "Each time this model makes a Normal move, it can move over friendly "
        'Vehicle and Monster models and terrain features that are 3.5" or less '
        "in height as if they were not there."
    ).rule_ir
    clause = rule_ir.clauses[0]
    assert clause.trigger is not None

    assert rule_ir.is_supported
    assert parameter_payload(clause.trigger.parameters)["movement_modes"] == ("normal",)
    assert parameter_payload(clause.effects[0].parameters) == {
        "model_allegiance": "friendly",
        "model_keyword_any": ("MONSTER", "VEHICLE"),
        "movement_modes": ("normal",),
        "permission": "move_over_as_if_not_there",
        "terrain_height_max_inches": 3.5,
        "terrain_scope": "terrain_features",
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_MOVEMENT_TRANSIT_PERMISSION_CONSUMER_ID,
    )


def test_phase17c_move_through_models_terrain_and_auto_pass_compiles_to_semantic_ir() -> None:
    rule_ir = _compiled(MOVE_THROUGH_MODELS_TERRAIN_AUTO_PASS_TEXT).rule_ir
    clause = rule_ir.clauses[0]
    assert clause.trigger is not None
    assert clause.target is not None

    assert rule_ir.is_supported
    assert len(rule_ir.clauses) == 1
    assert clause.trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert parameter_payload(clause.trigger.parameters) == {
        "edge": "during",
        "movement_modes": ("advance", "fall_back", "normal"),
        "phase": "movement",
        "subject": "this_unit",
        "timing_window": "unit_makes_move",
    }
    assert clause.target.kind is RuleTargetKind.THIS_UNIT
    assert tuple(effect.kind for effect in clause.effects) == (
        RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION,
        RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION,
    )
    assert parameter_payload(clause.effects[0].parameters) == {
        "desperate_escape_tests_auto_passed": True,
        "enemy_engagement_range_end_allowed": False,
        "enemy_engagement_range_transit": True,
        "excluded_model_keyword_any": ("TITANIC",),
        "model_allegiance": "any",
        "movement_modes": ("advance", "fall_back", "normal"),
        "permission": "move_through_models",
    }
    assert parameter_payload(clause.effects[1].parameters) == {
        "movement_modes": ("advance", "fall_back", "normal"),
        "permission": "move_through_terrain_features",
        "terrain_features": True,
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_MOVEMENT_TRANSIT_PERMISSION_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_MOVEMENT_TRANSIT_PERMISSION_CONSUMER_ID,
    )


def test_phase17c_movement_transit_consumer_normalizes_mode_order() -> None:
    rule_ir = _compiled(MOVE_OVER_MONSTER_VEHICLE_TERRAIN_TEXT).rule_ir
    clause = rule_ir.clauses[0]
    trigger = clause.trigger
    effect = clause.effects[0]
    assert trigger is not None

    reordered_clause = replace(
        clause,
        trigger=_trigger_with_parameter(
            trigger,
            key="movement_modes",
            value=("normal", "advance"),
        ),
        effects=(
            replace(
                effect,
                parameters=_parameters_with_value(
                    effect.parameters,
                    key="movement_modes",
                    value=("normal", "advance"),
                ),
            ),
        ),
    )
    reordered_rule_ir = replace(rule_ir, clauses=(reordered_clause,))

    assert catalog_rule_ir_consumers_for_rule(reordered_rule_ir) == (
        CATALOG_IR_MOVEMENT_TRANSIT_PERMISSION_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(reordered_rule_ir) == (
        CATALOG_IR_MOVEMENT_TRANSIT_PERMISSION_CONSUMER_ID,
    )


def test_phase17c_movement_transit_consumer_fails_closed_for_malformed_mode_tokens() -> None:
    rule_ir = _compiled(MOVE_OVER_MONSTER_VEHICLE_TERRAIN_TEXT).rule_ir
    clause = rule_ir.clauses[0]
    trigger = clause.trigger
    assert trigger is not None

    malformed_values: tuple[RuleParameterValue, ...] = (
        ("normal", "normal"),
        ("normal", "charge"),
    )

    for malformed_value in malformed_values:
        malformed_rule_ir = replace(
            rule_ir,
            clauses=(
                replace(
                    clause,
                    trigger=_trigger_with_parameter(
                        trigger,
                        key="movement_modes",
                        value=malformed_value,
                    ),
                ),
            ),
        )

        assert catalog_rule_ir_consumers_for_rule(malformed_rule_ir) == ()
        assert catalog_rule_ir_hook_ids_for_rule(malformed_rule_ir) == ()
    assert _movement_mode_tokens_or_none(cast(tuple[str, ...], "normal")) is None
    assert _movement_mode_tokens_or_none(()) is None


def test_phase17c_movement_transit_clause_extraction_rejects_wrong_types() -> None:
    rule_ir = _compiled(MOVE_OVER_MONSTER_VEHICLE_TERRAIN_TEXT).rule_ir
    clause = rule_ir.clauses[0]
    record = AbilityCatalogRecord(
        record_id="phase17c:test:movement-transit",
        definition=AbilityDefinition(
            ability_id="phase17c:test:movement-transit",
            name="Movement Transit",
            source_id="phase17c:test:movement-transit:source",
            when_descriptor="Passive query.",
            effect_descriptor="Movement transit permission.",
            restrictions_descriptor="None.",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.PASSIVE_QUERY),
        ),
    )

    with pytest.raises(GameLifecycleError, match="ability record"):
        _movement_transit_permissions_from_clause(
            record=cast(AbilityCatalogRecord, object()),
            clause=clause,
        )
    with pytest.raises(GameLifecycleError, match="RuleClause"):
        _movement_transit_permissions_from_clause(
            record=record,
            clause=cast(RuleClause, object()),
        )


def test_phase17c_malformed_movement_transit_ir_fails_closed_for_catalog_consumers() -> None:
    rule_ir = _compiled(MOVE_OVER_MONSTER_VEHICLE_TERRAIN_TEXT).rule_ir
    clause = rule_ir.clauses[0]
    trigger = clause.trigger
    target = clause.target
    effect = clause.effects[0]
    assert trigger is not None
    assert target is not None

    malformed_clauses = (
        replace(clause, target=None),
        replace(clause, target=replace(target, kind=RuleTargetKind.THIS_UNIT)),
        replace(clause, trigger=None),
        replace(clause, trigger=_trigger_with_parameter(trigger, key="edge", value="after")),
        replace(clause, trigger=_trigger_with_parameter(trigger, key="phase", value="shooting")),
        replace(
            clause,
            trigger=_trigger_with_parameter(
                trigger,
                key="subject",
                value="this_unit",
            ),
        ),
        replace(
            clause,
            trigger=_trigger_with_parameter(
                trigger,
                key="timing_window",
                value="unit_makes_move",
            ),
        ),
        replace(
            clause,
            trigger=_trigger_with_parameter(
                trigger,
                key="movement_modes",
                value=("fall_back",),
            ),
        ),
        replace(clause, effects=()),
        replace(clause, effects=(effect, effect)),
        replace(
            clause,
            effects=(
                replace(
                    effect,
                    parameters=_parameters_with_value(
                        effect.parameters,
                        key="permission",
                        value="unsupported_permission",
                    ),
                ),
            ),
        ),
        replace(
            clause,
            effects=(
                replace(
                    effect,
                    parameters=_parameters_with_value(
                        effect.parameters,
                        key="model_allegiance",
                        value="enemy",
                    ),
                ),
            ),
        ),
        replace(
            clause,
            effects=(
                replace(
                    effect,
                    parameters=_parameters_with_value(
                        effect.parameters,
                        key="terrain_scope",
                        value="battlefield",
                    ),
                ),
            ),
        ),
        replace(
            clause,
            effects=(
                replace(
                    effect,
                    parameters=_parameters_with_value(
                        effect.parameters,
                        key="model_keyword_any",
                        value=("INFANTRY", "VEHICLE"),
                    ),
                ),
            ),
        ),
    )

    for malformed_clause in malformed_clauses:
        malformed_rule_ir = replace(rule_ir, clauses=(malformed_clause,))
        assert catalog_rule_ir_consumers_for_rule(malformed_rule_ir) == ()
        assert catalog_rule_ir_hook_ids_for_rule(malformed_rule_ir) == ()


def test_phase17c_malformed_tracked_target_ir_fails_closed_for_catalog_consumers() -> None:
    rule_ir = _compiled(PREY_TARGET_TEXT).rule_ir
    selection_clause, attack_clause, reselection_clause = rule_ir.clauses
    selection_effect = selection_clause.effects[0]
    attack_effect = attack_clause.effects[0]
    attack_trigger = attack_clause.trigger
    reselection_trigger = reselection_clause.trigger
    assert attack_trigger is not None
    assert reselection_trigger is not None
    malformed_clauses = (
        replace(selection_clause, target=None),
        replace(selection_clause, effects=()),
        replace(
            selection_clause,
            effects=(
                replace(
                    selection_effect,
                    parameters=_parameters_with_value(
                        selection_effect.parameters,
                        key="replacement",
                        value="true",
                    ),
                ),
            ),
        ),
        replace(
            selection_clause,
            effects=(
                replace(
                    selection_effect,
                    parameters=_parameters_with_value(
                        selection_effect.parameters,
                        key="target_scope",
                        value="friendly_unit",
                    ),
                ),
            ),
        ),
        replace(
            attack_clause,
            trigger=_trigger_with_parameter(
                attack_trigger,
                key="target_reference",
                value="other_target",
            ),
        ),
        replace(
            attack_clause,
            trigger=_trigger_with_parameter(
                attack_trigger,
                key="tracked_target_owner",
                value="other_owner",
            ),
        ),
        replace(
            attack_clause,
            trigger=_trigger_with_parameter(
                attack_trigger,
                key="tracked_target_role",
                value="other_role",
            ),
        ),
        replace(
            attack_clause,
            trigger=_trigger_with_parameter(attack_trigger, key="attack_kind", value="psychic"),
        ),
        replace(
            attack_clause,
            trigger=_trigger_with_parameter(attack_trigger, key="actor", value="other_actor"),
        ),
        replace(attack_clause, conditions=()),
        replace(attack_clause, effects=(attack_effect, selection_effect)),
        replace(
            attack_clause,
            effects=(
                replace(
                    attack_effect,
                    parameters=_parameters_with_value(
                        attack_effect.parameters,
                        key="roll_type",
                        value="save",
                    ),
                ),
            ),
        ),
    )
    malformed_reselection_clauses = (
        replace(
            reselection_clause,
            trigger=_trigger_with_parameter(
                reselection_trigger,
                key="timing_window",
                value="other_window",
            ),
        ),
        replace(reselection_clause, conditions=()),
    )

    for clause in malformed_clauses:
        malformed_rule_ir = replace(rule_ir, clauses=(clause,))
        assert catalog_rule_ir_consumers_for_rule(malformed_rule_ir) == ()
        assert catalog_rule_ir_hook_ids_for_rule(malformed_rule_ir) == ()
    for clause in malformed_reselection_clauses:
        malformed_rule_ir = replace(rule_ir, clauses=(clause,))
        assert CATALOG_IR_TRACKED_TARGET_DESTROYED_RESELECT_CONSUMER_ID not in (
            catalog_rule_ir_consumers_for_rule(malformed_rule_ir)
        )
        assert CATALOG_IR_TRACKED_TARGET_DESTROYED_RESELECT_CONSUMER_ID not in (
            catalog_rule_ir_hook_ids_for_rule(malformed_rule_ir)
        )


def test_phase17c_malformed_first_death_return_ir_fails_closed_for_catalog_consumers() -> None:
    rule_ir = _compiled(FIRST_DEATH_RETURN_TEXT).rule_ir
    clause = rule_ir.clauses[0]
    trigger = clause.trigger
    assert trigger is not None
    frequency_conditions = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is not RuleConditionKind.FREQUENCY_LIMIT
    )
    dice_gate = next(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.DICE_ROLL_GATE
    )
    distance_conditions = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is not RuleConditionKind.DISTANCE_PREDICATE
    )
    effect = clause.effects[0]
    malformed_clauses = (
        replace(clause, trigger=None),
        replace(
            clause, trigger=_trigger_with_parameter(trigger, key="event_order", value="second")
        ),
        replace(
            clause,
            trigger=_trigger_with_parameter(trigger, key="resolution_timing", value="immediate"),
        ),
        replace(
            clause,
            trigger=_trigger_with_parameter(trigger, key="timing_window", value="phase_start"),
        ),
        replace(clause, conditions=frequency_conditions),
        replace(
            clause,
            conditions=(
                *tuple(
                    condition
                    for condition in clause.conditions
                    if condition.kind is not RuleConditionKind.DICE_ROLL_GATE
                ),
                replace(
                    dice_gate,
                    parameters=_parameters_with_value(
                        dice_gate.parameters,
                        key="roll_count",
                        value=0,
                    ),
                ),
            ),
        ),
        replace(
            clause,
            conditions=(
                *tuple(
                    condition
                    for condition in clause.conditions
                    if condition.kind is not RuleConditionKind.DICE_ROLL_GATE
                ),
                replace(
                    dice_gate,
                    parameters=_parameters_with_value(
                        dice_gate.parameters,
                        key="roll_count",
                        value=2,
                    ),
                ),
            ),
        ),
        replace(
            clause,
            conditions=(
                *tuple(
                    condition
                    for condition in clause.conditions
                    if condition.kind is not RuleConditionKind.DICE_ROLL_GATE
                ),
                replace(
                    dice_gate,
                    parameters=_parameters_with_value(
                        dice_gate.parameters,
                        key="success_threshold",
                        value=7,
                    ),
                ),
            ),
        ),
        replace(clause, conditions=distance_conditions),
        replace(clause, effects=(effect, effect)),
        replace(
            clause,
            effects=(
                replace(
                    effect,
                    parameters=_parameters_with_value(
                        effect.parameters,
                        key="wounds_remaining",
                        value=0,
                    ),
                ),
            ),
        ),
        replace(
            clause,
            effects=(
                replace(
                    effect,
                    parameters=_parameters_with_value(
                        _parameters_with_value(
                            effect.parameters,
                            key="restore_wounds_mode",
                            value="full_health",
                        ),
                        key="wounds_remaining",
                        value=1,
                    ),
                ),
            ),
        ),
        replace(
            clause,
            effects=(
                replace(
                    effect,
                    parameters=_parameters_with_value(
                        effect.parameters,
                        key="restore_wounds_mode",
                        value="unsupported",
                    ),
                ),
            ),
        ),
    )

    for malformed_clause in malformed_clauses:
        malformed_rule_ir = replace(rule_ir, clauses=(malformed_clause,))
        assert catalog_rule_ir_consumers_for_rule(malformed_rule_ir) == ()
        assert catalog_rule_ir_hook_ids_for_rule(malformed_rule_ir) == ()


def test_phase17c_first_death_return_target_shape_mismatches_fail_closed() -> None:
    model_rule_ir = _compiled(FIRST_DEATH_RETURN_TEXT).rule_ir
    model_clause = model_rule_ir.clauses[0]
    model_effect = model_clause.effects[0]
    assert model_clause.target is not None

    unit_rule_ir = _compiled(FIRST_DEATH_RETURN_FULL_HEALTH_TEXT).rule_ir
    unit_clause = unit_rule_ir.clauses[0]
    unit_effect = unit_clause.effects[0]
    unit_trigger = unit_clause.trigger
    assert unit_clause.target is not None
    assert unit_trigger is not None

    malformed_cases = (
        (
            model_rule_ir,
            replace(
                model_clause,
                target=replace(model_clause.target, kind=RuleTargetKind.THIS_UNIT),
            ),
        ),
        (
            model_rule_ir,
            replace(
                model_clause,
                effects=(
                    replace(
                        model_effect,
                        parameters=_parameters_with_value(
                            _parameters_with_value(
                                model_effect.parameters,
                                key="target",
                                value="this_unit",
                            ),
                            key="target_scope",
                            value="destroyed_unit",
                        ),
                    ),
                ),
            ),
        ),
        (
            unit_rule_ir,
            replace(
                unit_clause,
                trigger=_trigger_with_parameter(
                    unit_trigger,
                    key="destroyed_target",
                    value="this_model",
                ),
            ),
        ),
        (
            unit_rule_ir,
            replace(
                unit_clause,
                effects=(
                    replace(
                        unit_effect,
                        parameters=_parameters_with_value(
                            _parameters_with_value(
                                unit_effect.parameters,
                                key="target",
                                value="this_model",
                            ),
                            key="target_scope",
                            value="destroyed_model",
                        ),
                    ),
                ),
            ),
        ),
    )

    for base_rule_ir, malformed_clause in malformed_cases:
        malformed_rule_ir = replace(base_rule_ir, clauses=(malformed_clause,))
        assert catalog_rule_ir_consumers_for_rule(malformed_rule_ir) == ()
        assert catalog_rule_ir_hook_ids_for_rule(malformed_rule_ir) == ()


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
            (
                "One friendly INFANTRY unit that was selected as the target gains Stealth "
                "until the end of the phase."
            ),
            None,
            RuleConditionKind.KEYWORD_GATE,
            RuleTargetKind.SELECTED_TARGET,
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


def test_phase17c_selected_target_source_text_preserves_structured_target_context() -> None:
    compiled = _compiled(
        "One ADEPTUS CUSTODES CHARACTER unit from your army that was selected as the "
        "target of one or more attacks gains Stealth until the end of the phase."
    )
    clause = compiled.rule_ir.clauses[0]

    assert compiled.rule_ir.is_supported
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.SELECTED_TARGET
    assert parameter_payload(clause.target.parameters) == {
        "allegiance": "friendly",
        "required_keyword_sequence": ("ADEPTUS_CUSTODES", "CHARACTER"),
        "source_context": "selected_target",
    }


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


def test_phase17c_bearer_feel_no_pain_psychic_and_mortal_wounds_compiles_to_ir() -> None:
    rule_ir = _compiled(
        "The bearer has the Feel No Pain 3+ ability against Psychic Attacks and mortal wounds."
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
        "mortal_wounds": True,
        "threshold": 3,
    }


def test_phase17c_bare_mortal_wounds_feel_no_pain_scope_is_not_unconditional() -> None:
    rule_ir = _compiled("The bearer has the Feel No Pain 3+ ability against mortal wounds.").rule_ir

    assert not rule_ir.is_supported
    assert rule_ir.clauses[0].unsupported_reason is RuleUnsupportedReason.UNSUPPORTED_LANGUAGE
    assert any(
        diagnostic.reason is RuleUnsupportedReason.UNSUPPORTED_LANGUAGE
        and "against mortal wounds" in diagnostic.source_span.text
        for diagnostic in rule_ir.diagnostics
    )


def test_phase17c_structured_fnp_mortal_scope_without_attack_condition_fails_closed() -> None:
    source_text = "The bearer has the Feel No Pain 3+ ability against mortal wounds."
    source_span = TextSpan(text=source_text, start=0, end=len(source_text))
    effect = RuleEffectSpec(
        kind=RuleEffectKind.GRANT_ABILITY,
        source_span=source_span,
        parameters=(
            RuleParameter(key="ability", value="Feel No Pain"),
            RuleParameter(key="threshold", value=3),
            RuleParameter(key="mortal_wounds", value=True),
        ),
    )
    clause = RuleClause(
        clause_id="phase17c:test:structured-fnp-mortal-only:clause:001",
        template_id="phase17c:test:structured-fnp-mortal-only",
        source_span=source_span,
        target=RuleTargetSpec(kind=RuleTargetKind.THIS_MODEL, source_span=source_span),
        effects=(effect,),
    )
    record = AbilityCatalogRecord(
        record_id="phase17c:test:structured-fnp-mortal-only",
        definition=AbilityDefinition(
            ability_id="phase17c:test:structured-fnp-mortal-only",
            name="Structured Feel No Pain Mortal Only",
            source_id="phase17c:test:structured-fnp-mortal-only:source",
            when_descriptor="Passive query.",
            effect_descriptor="Malformed structured FNP source.",
            restrictions_descriptor="None.",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.PASSIVE_QUERY),
        ),
    )

    with pytest.raises(
        GameLifecycleError,
        match="FeelNoPainSource mortal_wounds scope requires an attack condition",
    ):
        _feel_no_pain_source_from_effect(
            record=record,
            clause=clause,
            effect_index=0,
            effect=effect,
        )


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


def test_phase17c_post_shoot_hit_target_cover_denial_compiles_to_semantic_ir() -> None:
    rule_ir = _compiled(
        "In your Shooting phase, after this model has shot, select one enemy unit hit by "
        "one or more of those attacks. Until the end of the phase, that unit cannot have "
        "the Benefit of Cover."
    ).rule_ir
    clause = rule_ir.clauses[0]
    effect = clause.effects[0]

    assert rule_ir.is_supported
    assert RuleIR.from_payload(rule_ir.to_payload()).to_payload() == rule_ir.to_payload()
    assert len(rule_ir.clauses) == 1
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert parameter_payload(clause.trigger.parameters) == {
        "edge": "after",
        "owner": "active_player",
        "phase": "shooting",
        "subject": "this_model",
        "target_relationship": "hit_by_those_attacks",
        "timing_window": "just_after_friendly_unit_has_shot",
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.ENEMY_UNIT
    assert clause.duration is not None
    assert clause.duration.kind is RuleDurationKind.UNTIL_TIMING_ENDPOINT
    assert parameter_payload(clause.duration.parameters) == {"endpoint": "phase"}
    assert effect.kind is RuleEffectKind.SET_CONTEXTUAL_STATUS
    assert parameter_payload(effect.parameters) == {
        "operation": "deny",
        "rules_context": "status_denial",
        "status": "benefit_of_cover",
        "status_label": "Benefit of Cover",
        "target_scope": "selected_unit",
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
    )
    assert (
        ability_support_rollup_for_rule_ir(
            source_ability_id="source:cover-denial",
            ability_name="Cover Denial",
            rule_ir=rule_ir,
        ).overall_ability_support
        is AbilityOverallSupport.FULL
    )


def test_phase17c_hit_target_cover_denial_effect_clause_compiles_to_semantic_ir() -> None:
    rule_ir = _compiled(
        "Select one enemy unit hit by one or more of those attacks. Until the end of the phase, "
        "that enemy unit cannot have the Benefit of Cover."
    ).rule_ir
    clause = rule_ir.clauses[0]
    effect = clause.effects[0]

    assert rule_ir.is_supported
    assert clause.trigger is None
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.ENEMY_UNIT
    assert parameter_payload(clause.target.parameters) == {
        "allegiance": "enemy",
        "target_relationship": "hit_by_those_attacks",
    }
    assert clause.duration is not None
    assert parameter_payload(clause.duration.parameters) == {"endpoint": "phase"}
    assert effect.kind is RuleEffectKind.SET_CONTEXTUAL_STATUS
    assert parameter_payload(effect.parameters) == {
        "operation": "deny",
        "rules_context": "status_denial",
        "status": "benefit_of_cover",
        "status_label": "Benefit of Cover",
        "target_scope": "selected_unit",
    }


def test_phase17c_fire_overwatch_hit_threshold_compiles_to_generic_status_ir() -> None:
    rule_ir = _compiled(
        "Each time you target this unit with the Fire Overwatch Stratagem, hits are scored "
        "on unmodified Hit rolls of 5+ when resolving that Stratagem. For each of those "
        'attacks that targets an enemy unit within 9" of one or more Thousand Sons Psyker '
        "units from your army, a hit is scored on an unmodified Hit roll of 4+ instead."
    ).rule_ir
    clause = rule_ir.clauses[0]

    assert rule_ir.is_supported
    assert len(rule_ir.clauses) == 1
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.DICE_ROLL
    assert parameter_payload(clause.trigger.parameters) == {"roll_type": "hit"}
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_UNIT
    assert tuple(effect.kind for effect in clause.effects) == (
        RuleEffectKind.SET_CONTEXTUAL_STATUS,
        RuleEffectKind.SET_CONTEXTUAL_STATUS,
    )
    assert tuple(parameter_payload(effect.parameters) for effect in clause.effects) == (
        {
            "attack_role": "attacker",
            "minimum_unmodified_success": 5,
            "required_targeting_rule_id": "core:fire-overwatch",
            "roll_type": "hit",
            "status": "minimum_unmodified_hit_success",
        },
        {
            "attack_role": "attacker",
            "minimum_unmodified_success": 4,
            "required_targeting_rule_id": "core:fire-overwatch",
            "roll_type": "hit",
            "status": "minimum_unmodified_hit_success",
            "target_proximity_distance_inches": 9,
            "target_proximity_required_keyword_sequence": ("THOUSAND_SONS", "PSYKER"),
            "target_proximity_unit_allegiance": "friendly",
        },
    )
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_MINIMUM_UNMODIFIED_HIT_SUCCESS_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_MINIMUM_UNMODIFIED_HIT_SUCCESS_CONSUMER_ID,
    )


def test_phase17c_fire_overwatch_hit_threshold_accepts_decimal_proximity_distance() -> None:
    rule_ir = _compiled(
        "Each time you target this unit with the Fire Overwatch Stratagem, hits are scored "
        "on unmodified Hit rolls of 5+ when resolving that Stratagem. For each of those "
        'attacks that targets an enemy unit within 4.5" of one or more Thousand Sons '
        "Psyker units from your army, a hit is scored on an unmodified Hit roll of 4+ "
        "instead."
    ).rule_ir

    assert parameter_payload(rule_ir.clauses[0].effects[1].parameters) == {
        "attack_role": "attacker",
        "minimum_unmodified_success": 4,
        "required_targeting_rule_id": "core:fire-overwatch",
        "roll_type": "hit",
        "status": "minimum_unmodified_hit_success",
        "target_proximity_distance_inches": 4.5,
        "target_proximity_required_keyword_sequence": ("THOUSAND_SONS", "PSYKER"),
        "target_proximity_unit_allegiance": "friendly",
    }


def test_phase17c_hit_threshold_helper_without_targeting_rule_keeps_status_payload() -> None:
    effects = hit_success_threshold_effects(
        clause_text="Hits are scored on unmodified Hit rolls of 5+.",
        clause_start=12,
        source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
    )

    assert tuple(parameter_payload(effect.parameters) for effect in effects) == (
        {
            "attack_role": "attacker",
            "minimum_unmodified_success": 5,
            "roll_type": "hit",
            "status": "minimum_unmodified_hit_success",
        },
    )
    assert effects[0].source_span.start == 12


def test_phase17c_keyword_sequence_tokens_reject_empty_text() -> None:
    with pytest.raises(RuleIRError, match="Keyword sequence must not be empty"):
        keyword_sequence_tokens(
            "   ",
            source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
        )


@pytest.mark.parametrize(
    ("raw_text", "expected_parameters"),
    [
        (
            "That unit gains Stealth until your next Command phase.",
            {
                "boundary": "start",
                "endpoint": "phase",
                "owner": "self",
                "phase": "command",
                "relative": "next",
            },
        ),
        (
            "That unit gains Stealth until the end of your next turn.",
            {
                "boundary": "end",
                "endpoint": "turn",
                "owner": "self",
                "relative": "next",
            },
        ),
        (
            "That unit gains Stealth until the start of opponent's next turn.",
            {
                "boundary": "start",
                "endpoint": "turn",
                "owner": "opponent",
                "relative": "next",
            },
        ),
    ],
)
def test_phase17c_relative_duration_endpoints_compile_to_structured_parameters(
    raw_text: str,
    expected_parameters: dict[str, object],
) -> None:
    rule_ir = _compiled(raw_text).rule_ir
    clause = rule_ir.clauses[0]

    assert rule_ir.is_supported
    assert clause.duration is not None
    assert clause.duration.kind is RuleDurationKind.UNTIL_TIMING_ENDPOINT
    assert parameter_payload(clause.duration.parameters) == expected_parameters


def test_phase17c_contextual_status_denial_is_not_cover_specific() -> None:
    rule_ir = _compiled(
        "In your Shooting phase, after this model has shot, select one enemy unit hit by "
        "one or more of those attacks. Until the end of the phase, that unit cannot have "
        "Objective Secured."
    ).rule_ir
    effect = rule_ir.clauses[0].effects[0]

    assert rule_ir.is_supported
    assert parameter_payload(effect.parameters) == {
        "operation": "deny",
        "rules_context": "status_denial",
        "status": "objective_secured",
        "status_label": "Objective Secured",
        "target_scope": "selected_unit",
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == ()
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == ()


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
            "weapon_names": ("storm staff", "prism cannon"),
        },
        {
            "selection_group_id": "weapon_ability_choice_0024",
            "selection_kind": "select_one",
            "selection_option_id": "option_002_sustained_hits_1",
            "selection_option_index": 2,
            "target_scope": "models_in_this_unit",
            "weapon_ability": "Sustained Hits",
            "weapon_ability_value": 1,
            "weapon_names": ("storm staff", "prism cannon"),
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
        "excluded_keyword_any": ("MONSTER", "VEHICLE"),
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


def test_phase17c_enemy_selected_to_fall_back_desperate_escape_aura_compiles() -> None:
    rule_ir = _compiled(
        "Each time an enemy unit (excluding Monsters and Vehicles) that is within "
        "Engagement Range of one or more units from your army with this ability is selected "
        "to Fall Back, models in that enemy unit must take Desperate Escape tests. If that "
        "enemy unit is also Battle-shocked, subtract 1 from each of those Desperate Escape "
        "tests."
    ).rule_ir

    assert rule_ir.is_supported
    assert len(rule_ir.clauses) == 2
    force_trigger = rule_ir.clauses[0].trigger
    modifier_trigger = rule_ir.clauses[1].trigger
    assert force_trigger is not None
    assert modifier_trigger is not None
    assert parameter_payload(force_trigger.parameters) == {
        "selected_unit_allegiance": "enemy",
        "selection": "fall_back",
        "timing_window": "just_after_enemy_unit_selected_to_fall_back",
    }
    assert parameter_payload(modifier_trigger.parameters) == {
        "roll_type": "desperate_escape",
        "source_context": "previous_effect",
        "timing_window": "desperate_escape_test",
    }
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) >= {
        CATALOG_IR_DESPERATE_ESCAPE_ROLL_MODIFIER_CONSUMER_ID,
        CATALOG_IR_FORCE_DESPERATE_ESCAPE_CONSUMER_ID,
    }


def test_phase17c_charge_move_plural_weapon_characteristics_compile() -> None:
    rule_ir = _compiled(
        "Each time this unit ends a Charge move, until the end of the phase, add 1 to "
        "the Strength and Damage characteristics of melee weapons equipped by models in "
        "this unit."
    ).rule_ir
    clause = rule_ir.clauses[0]

    assert rule_ir.is_supported
    assert clause.trigger is not None
    assert parameter_payload(clause.trigger.parameters) == {
        "edge": "after",
        "phase": "charge",
        "subject": "this_unit",
        "timing_window": "charge_move_end",
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_UNIT
    assert tuple(
        tuple(sorted(parameter_payload(effect.parameters).items())) for effect in clause.effects
    ) == (
        (("characteristic", "damage"), ("delta", 1), ("weapon_scope", "melee")),
        (("characteristic", "strength"), ("delta", 1), ("weapon_scope", "melee")),
    )


def test_phase17c_leader_lethal_hits_with_critical_hit_threshold_compiles() -> None:
    rule_ir = _compiled(
        "While this model is leading a unit, melee weapons equipped by models in that unit "
        "have the [LETHAL HITS] ability and each time a model in that unit makes an attack, "
        "a successful unmodified Hit roll of 5+ scores a Critical Hit."
    ).rule_ir
    clause = rule_ir.clauses[0]
    minimum_hit_effect = next(
        effect for effect in clause.effects if effect.kind is RuleEffectKind.SET_CONTEXTUAL_STATUS
    )

    assert rule_ir.is_supported
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.SELECTED_UNIT
    assert parameter_payload(minimum_hit_effect.parameters) == {
        "attack_role": "attacker",
        "minimum_unmodified_success": 5,
        "roll_type": "hit",
        "status": "minimum_unmodified_hit_success",
    }
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) >= {
        CATALOG_IR_MINIMUM_UNMODIFIED_HIT_SUCCESS_CONSUMER_ID,
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
    }


def test_phase17c_selected_unit_this_model_damage_bonus_compiles() -> None:
    rule_ir = _compiled(
        "At the start of the Fight phase, select one enemy unit within Engagement Range "
        "of this model. Until the end of the phase, each time this model makes a melee "
        "attack that targets that unit, add 1 to the Damage characteristic of that attack."
    ).rule_ir
    damage_clause = rule_ir.clauses[1]
    damage_effect = damage_clause.effects[0]

    assert rule_ir.is_supported
    assert damage_clause.trigger is not None
    assert parameter_payload(damage_clause.trigger.parameters) == {
        "actor": "this_model",
        "attack_kind": "melee",
        "target_reference": "selected_unit",
        "timing_window": "attack_sequence.attack",
    }
    assert damage_clause.target is not None
    assert damage_clause.target.kind is RuleTargetKind.THIS_MODEL
    assert _condition_payload(damage_clause, RuleConditionKind.TARGET_CONSTRAINT) == {
        "attack_kind": "melee",
        "gate_subject": "attack_target",
        "relationship": "this_model_makes_attack",
        "target_reference": "selected_unit",
    }
    assert parameter_payload(damage_effect.parameters) == {
        "characteristic": "damage",
        "delta": 1,
    }
    assert CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID in catalog_rule_ir_consumers_for_rule(
        rule_ir
    )
    assert CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID in catalog_rule_ir_hook_ids_for_rule(
        rule_ir
    )


def test_phase17c_post_shoot_hit_target_effect_compiles_to_selected_target_consumer() -> None:
    rule_ir = _compiled(
        "In your Shooting phase, after this unit has shot, select one enemy unit hit by "
        "one or more of those attacks. Until the end of the phase, each time a friendly "
        "Nurgle Legiones Daemonica unit makes an attack that targets that unit, you can "
        "re-roll the Wound roll."
    ).rule_ir
    selection_clause = rule_ir.clauses[0]
    reroll_clause = rule_ir.clauses[1]
    reroll_effect = reroll_clause.effects[0]

    assert rule_ir.is_supported
    assert selection_clause.trigger is not None
    assert parameter_payload(selection_clause.trigger.parameters) == {
        "edge": "after",
        "owner": "active_player",
        "phase": "shooting",
        "subject": "this_unit",
        "target_relationship": "hit_by_those_attacks",
        "timing_window": "just_after_friendly_unit_has_shot",
    }
    assert reroll_clause.target is not None
    assert reroll_clause.target.kind is RuleTargetKind.FRIENDLY_UNIT
    assert parameter_payload(reroll_effect.parameters) == {"roll_type": "wound"}
    assert CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID in (
        catalog_rule_ir_consumers_for_rule(rule_ir)
    )
    assert CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID in (
        catalog_rule_ir_hook_ids_for_rule(rule_ir)
    )


def test_phase17c_conditional_objective_hit_reroll_compiles_to_single_permission() -> None:
    rule_ir = _compiled(
        "Each time a model in this model's unit makes an attack, you can re-roll a Hit "
        "roll of 1. If the target of that attack is within range of an objective marker, "
        "you can re-roll the Hit roll instead."
    ).rule_ir
    clause = rule_ir.clauses[0]
    reroll_effects = tuple(
        effect for effect in clause.effects if effect.kind is RuleEffectKind.REROLL_PERMISSION
    )

    assert rule_ir.is_supported
    assert len(rule_ir.clauses) == 1
    assert len(reroll_effects) == 1
    assert parameter_payload(reroll_effects[0].parameters) == {
        "full_reroll_if_target_within_objective_range": True,
        "reroll_unmodified_value": 1,
        "roll_type": "hit",
    }
    assert CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID in catalog_rule_ir_hook_ids_for_rule(rule_ir)


def test_phase17c_selected_enemy_attack_wound_debuff_marks_attacker_role() -> None:
    rule_ir = _compiled(
        'At the start of the Fight phase, select one enemy unit within 6" of this model. '
        "Until the end of the phase, each time a friendly Slaanesh Legiones Daemonica "
        "unit makes a melee attack that targets that unit, add 1 to the Wound roll; and "
        "each time a model in that enemy unit makes an attack, subtract 1 from the Wound "
        "roll."
    ).rule_ir
    enemy_clause = rule_ir.clauses[2]
    enemy_effect = enemy_clause.effects[0]

    assert rule_ir.is_supported
    assert enemy_clause.target is not None
    assert enemy_clause.target.kind is RuleTargetKind.ENEMY_UNIT
    assert parameter_payload(enemy_effect.parameters) == {
        "attack_role": "attacker",
        "delta": -1,
        "roll_type": "wound",
    }
    assert CATALOG_IR_WOUND_ROLL_MODIFIER_CONSUMER_ID in catalog_rule_ir_hook_ids_for_rule(rule_ir)
    assert CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID in catalog_rule_ir_hook_ids_for_rule(
        rule_ir
    )


def test_phase17c_leading_unit_wound_roll_bonus_is_runtime_consumed() -> None:
    rule_ir = _compiled(
        "While this model is leading a unit, each time a model in that unit makes an "
        "attack, add 1 to the Wound roll."
    ).rule_ir
    clause = rule_ir.clauses[0]
    condition = clause.conditions[0]
    effect = clause.effects[0]

    assert rule_ir.is_supported
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.DICE_ROLL
    assert parameter_payload(clause.trigger.parameters) == {"roll_type": "wound"}
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.SELECTED_UNIT
    assert condition.kind is RuleConditionKind.TARGET_CONSTRAINT
    assert parameter_payload(condition.parameters) == {"relationship": "this_model_leading_unit"}
    assert effect.kind is RuleEffectKind.MODIFY_DICE_ROLL
    assert parameter_payload(effect.parameters) == {
        "attack_role": "attacker",
        "delta": 1,
        "roll_type": "wound",
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_WOUND_ROLL_MODIFIER_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_WOUND_ROLL_MODIFIER_CONSUMER_ID,
    )


def test_phase17c_consolidation_distance_modifier_is_runtime_consumed() -> None:
    rule_ir = _compiled(
        'Each time this model\'s unit Consolidates, it can move up to 6" instead of up to 3".'
    ).rule_ir
    clause = rule_ir.clauses[0]
    effect = clause.effects[0]

    assert rule_ir.is_supported
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert parameter_payload(clause.trigger.parameters) == {
        "edge": "during",
        "movement_mode": "consolidate",
        "phase": "fight",
        "subject": "this_unit",
        "timing_window": "consolidate_move",
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_UNIT
    assert effect.kind is RuleEffectKind.MODIFY_MOVE_DISTANCE
    assert parameter_payload(effect.parameters) == {
        "distance_inches": 6.0,
        "movement_mode": "consolidate",
        "operation": "set_maximum",
        "optional": True,
        "replaced_distance_inches": 3.0,
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_FIGHT_ACTIVATION_MOVEMENT_DISTANCE_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_FIGHT_ACTIVATION_MOVEMENT_DISTANCE_CONSUMER_ID,
    )


def test_phase17c_charge_end_engagement_battle_shock_is_runtime_consumed() -> None:
    rule_ir = _compiled(
        "Each time this model's unit ends a Charge move, each enemy unit within Engagement "
        "Range of that unit must take a Battle-shock test."
    ).rule_ir
    clause = rule_ir.clauses[0]
    condition = clause.conditions[0]
    effect = clause.effects[0]

    assert rule_ir.is_supported
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert parameter_payload(clause.trigger.parameters) == {
        "edge": "after",
        "phase": "charge",
        "subject": "this_unit",
        "timing_window": "charge_move_end",
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.ENEMY_UNIT
    assert condition.kind is RuleConditionKind.DISTANCE_PREDICATE
    assert parameter_payload(condition.parameters) == {
        "distance_inches": None,
        "negated": False,
        "object_kind": "unit",
        "object_reference": "that",
        "predicate": "within_engagement_range",
        "qualifier": None,
        "range_kind": "engagement_range",
    }
    assert effect.kind is RuleEffectKind.SET_CONTEXTUAL_STATUS
    assert parameter_payload(effect.parameters) == {
        "range_anchor": "this_unit",
        "reason": "forced_by_ability",
        "required": True,
        "rules_context": "battle_shock",
        "status": "force_battle_shock_test",
        "target_scope": "enemy_units_within_engagement_range",
    }
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_CONSUMER_ID,
    )


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
        "required_keyword_sequence": ("KHORNE", "LEGIONES_DAEMONICA"),
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
        "required_keyword_sequence": (allegiance.upper(), "LEGIONES_DAEMONICA"),
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
        "compiler_version": "phase17c-rule-compiler-v2",
        "parser_version": "phase17c-rule-parser-v2",
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
        CompiledRuleSource.from_payload(
            stale_compiled_payload,
            source_keyword_sequence_parts=SOURCE_KEYWORD_SEQUENCE_PARTS,
        )
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
    raw_roll_types_payload = cast(Any, rule_ir.to_payload())
    raw_roll_types_payload["clauses"][0]["effects"][0]["parameters"] = [
        {"key": "roll_types", "value": "hit|wound"}
    ]
    raw_weapon_scope_payload = cast(Any, rule_ir.to_payload())
    raw_weapon_scope_payload["clauses"][0]["effects"][0]["parameters"] = [
        {"key": "weapon_scope", "value": "all weapons"}
    ]
    raw_keyword_sequence_payload = cast(
        Any,
        _compiled(
            "Daemon Lord of Khorne (Aura): While a friendly Khorne Legiones Daemonica "
            'unit is within 6" of this model, each time a model in that unit makes a '
            "melee attack, add 1 to the Hit roll."
        ).rule_ir.to_payload(),
    )
    raw_keyword_sequence_payload["clauses"][0]["target"]["parameters"] = [
        {"key": "allegiance", "value": "friendly"},
        {"key": "eligible_target", "value": "aura_units"},
        {"key": "required_keyword_sequence", "value": "KHORNE|LEGIONES_DAEMONICA"},
    ]

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
    with pytest.raises(RuleIRError, match="roll_types must be a string tuple"):
        RuleIR.from_payload(cast(RuleIRPayload, raw_roll_types_payload))
    with pytest.raises(RuleIRError, match="required_keyword_sequence must be a string tuple"):
        RuleIR.from_payload(cast(RuleIRPayload, raw_keyword_sequence_payload))
    with pytest.raises(RuleIRError, match="weapon_scope must be all, melee, or ranged"):
        RuleIR.from_payload(cast(RuleIRPayload, raw_weapon_scope_payload))
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


def _parameters_with_value(
    parameters: tuple[RuleParameter, ...],
    *,
    key: str,
    value: RuleParameterValue,
) -> tuple[RuleParameter, ...]:
    payload = parameter_payload(parameters)
    payload[key] = value
    return tuple(
        RuleParameter(key=parameter_key, value=payload[parameter_key])
        for parameter_key in sorted(payload)
    )


def _trigger_with_parameter(
    trigger: RuleTrigger,
    *,
    key: str,
    value: RuleParameterValue,
) -> RuleTrigger:
    return replace(
        trigger,
        parameters=_parameters_with_value(trigger.parameters, key=key, value=value),
    )


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
