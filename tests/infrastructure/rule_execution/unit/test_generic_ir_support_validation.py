# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import cast

from tests.shared.category_migration.generic_ir_support_validation import (
    DICE_ROLL_MODIFIER_TEMPLATE_ID,
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
    MOVEMENT_DISTANCE_TEMPLATE_ID,
    RuleClause,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleParseDiagnostic,
    RuleUnsupportedReason,
    TextSpan,
    _blood_legion_rule_ir,
    _clause,
    _detachment_rule_ir,
    _diagnostic,
    _duration,
    _effect,
    _enhancement_row,
    _enhancement_source_id,
    _grant_ability,
    _mixed_enhancement_rule_ir,
    _rule_ir,
    _shadow_legion_rule_ir,
    _span,
    _stratagem_row,
    _stratagem_rule_ir,
    _stratagem_source_id,
    blood_legion_ir,
    corsair_ir,
    faction_detachments_2026_27,
    faction_subrules_2026_27,
    generic_ir_support,
    parameters_from_pairs,
    pytest,
    shadow_legion_ir,
)


def test_generic_ir_support_public_entry_points_fail_fast_on_invalid_inputs() -> None:
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="source row"):
        generic_ir_support.generic_supported_enhancement_rule_ir(
            cast(faction_subrules_2026_27.SourceEnhancementRow, object())
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="source row"):
        generic_ir_support.generic_supported_detachment_rule_ir_hash(
            cast(faction_detachments_2026_27.SourceDetachmentRow, object())
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="source row"):
        generic_ir_support.generic_supported_stratagem_rule_ir_hash(
            cast(faction_subrules_2026_27.SourceStratagemRow, object())
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="not registered"):
        generic_ir_support.generic_rule_ir_by_coverage_descriptor_id("phase17e:missing")
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="not registered"):
        generic_ir_support._validate_supported_enhancement_ir(
            rule_ir=_rule_ir(
                source_id=_enhancement_source_id("enhancement:test-detachment:unknown"),
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability("marker"),),
                    ),
                ),
            ),
            source_row=_enhancement_row("enhancement:test-detachment:unknown"),
        )


def test_supported_effect_family_validation_rejects_static_payload_drift() -> None:
    source_row = _enhancement_row("enhancement:test-detachment:ability")
    source_id = _enhancement_source_id(source_row.source_row_id)

    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="supported RuleIR"):
        generic_ir_support._validate_supported_effect_family_ir(
            rule_ir=_rule_ir(
                source_id=source_id,
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability("marker"),),
                        diagnostics=(_diagnostic(blocking=True),),
                    ),
                ),
            ),
            source_row=source_row,
            expected_template_ids=frozenset({GRANT_ABILITY_TEMPLATE_ID}),
            effect_kind=RuleEffectKind.GRANT_ABILITY,
            effect_family_name="ability",
            expected_effect_count=1,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="template family"):
        generic_ir_support._validate_supported_effect_family_ir(
            rule_ir=_rule_ir(
                source_id=source_id,
                clauses=(
                    _clause(
                        template_id=MOVEMENT_DISTANCE_TEMPLATE_ID,
                        effects=(_grant_ability("marker"),),
                    ),
                ),
            ),
            source_row=source_row,
            expected_template_ids=frozenset({GRANT_ABILITY_TEMPLATE_ID}),
            effect_kind=RuleEffectKind.GRANT_ABILITY,
            effect_family_name="ability",
            expected_effect_count=1,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="diagnostics"):
        generic_ir_support._validate_supported_effect_family_ir(
            rule_ir=_rule_ir(
                source_id=source_id,
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability("marker"),),
                        diagnostics=(_diagnostic(blocking=False),),
                    ),
                ),
            ),
            source_row=source_row,
            expected_template_ids=frozenset({GRANT_ABILITY_TEMPLATE_ID}),
            effect_kind=RuleEffectKind.GRANT_ABILITY,
            effect_family_name="ability",
            expected_effect_count=1,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="effect count"):
        generic_ir_support._validate_supported_effect_family_ir(
            rule_ir=_rule_ir(
                source_id=source_id,
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability("marker"),),
                    ),
                ),
            ),
            source_row=source_row,
            expected_template_ids=frozenset({GRANT_ABILITY_TEMPLATE_ID}),
            effect_kind=RuleEffectKind.GRANT_ABILITY,
            effect_family_name="ability",
            expected_effect_count=2,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="source ID"):
        generic_ir_support._validate_supported_effect_family_ir(
            rule_ir=_rule_ir(
                source_id="wrong-source",
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability("marker"),),
                    ),
                ),
            ),
            source_row=source_row,
            expected_template_ids=frozenset({GRANT_ABILITY_TEMPLATE_ID}),
            effect_kind=RuleEffectKind.GRANT_ABILITY,
            effect_family_name="ability",
            expected_effect_count=1,
        )


def test_mixed_enhancement_validation_rejects_template_effect_and_source_drift() -> None:
    source_row = _enhancement_row(
        "enhancement:emperors-children:court-of-the-phoenician:000010654003"
    )
    source_id = _enhancement_source_id(source_row.source_row_id)

    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="supported"):
        generic_ir_support._validate_supported_court_of_the_phoenician_mixed_enhancement_ir(
            rule_ir=_rule_ir(
                source_id=source_id,
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability("marker"),),
                        diagnostics=(_diagnostic(blocking=True),),
                    ),
                ),
            ),
            source_row=source_row,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="source ID"):
        generic_ir_support._validate_supported_court_of_the_phoenician_mixed_enhancement_ir(
            rule_ir=_mixed_enhancement_rule_ir(source_id="wrong-source"),
            source_row=source_row,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="template family"):
        generic_ir_support._validate_supported_court_of_the_phoenician_mixed_enhancement_ir(
            rule_ir=_rule_ir(
                source_id=source_id,
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability("marker"),),
                    ),
                    _clause(
                        clause_id="clause-2",
                        template_id=MOVEMENT_DISTANCE_TEMPLATE_ID,
                        effects=(_effect(RuleEffectKind.MODIFY_MOVE_DISTANCE),),
                    ),
                ),
            ),
            source_row=source_row,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="diagnostics"):
        generic_ir_support._validate_supported_court_of_the_phoenician_mixed_enhancement_ir(
            rule_ir=_mixed_enhancement_rule_ir(
                source_id=source_id,
                diagnostics=(_diagnostic(blocking=False),),
            ),
            source_row=source_row,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="effect kind"):
        generic_ir_support._validate_supported_court_of_the_phoenician_mixed_enhancement_ir(
            rule_ir=_rule_ir(
                source_id=source_id,
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability("marker"),),
                    ),
                    _clause(
                        clause_id="clause-2",
                        template_id=KEYWORD_GATE_TEMPLATE_ID,
                        effects=(_effect(RuleEffectKind.MODIFY_DICE_ROLL),),
                    ),
                    _clause(
                        clause_id="clause-3",
                        template_id=MOVEMENT_DISTANCE_TEMPLATE_ID,
                        effects=(_effect(RuleEffectKind.MODIFY_MOVE_DISTANCE),),
                    ),
                ),
            ),
            source_row=source_row,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="effect counts"):
        generic_ir_support._validate_supported_court_of_the_phoenician_mixed_enhancement_ir(
            rule_ir=_rule_ir(
                source_id=source_id,
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability("marker"),),
                    ),
                    _clause(
                        clause_id="clause-2",
                        template_id=KEYWORD_GATE_TEMPLATE_ID,
                        effects=(_grant_ability("another-marker"),),
                    ),
                    _clause(
                        clause_id="clause-3",
                        template_id=MOVEMENT_DISTANCE_TEMPLATE_ID,
                        effects=(_effect(RuleEffectKind.MODIFY_MOVE_DISTANCE),),
                    ),
                ),
            ),
            source_row=source_row,
        )


def test_generic_detachment_validators_reject_descriptor_drift() -> None:
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="requires RuleIR"):
        generic_ir_support._validate_cavalcade_of_chaos_detachment_rule_ir(cast(RuleIR, object()))
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="supported"):
        generic_ir_support._validate_cavalcade_of_chaos_detachment_rule_ir(
            _detachment_rule_ir(
                "chaos-daemons:cavalcade-of-chaos:rule",
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability("can_fall_back_and_shoot"),),
                        diagnostics=(_diagnostic(blocking=True),),
                    ),
                ),
            )
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="source ID"):
        generic_ir_support._validate_cavalcade_of_chaos_detachment_rule_ir(
            _rule_ir(
                source_id="wrong-source",
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(
                            _grant_ability("can_fall_back_and_shoot"),
                            _grant_ability("can_fall_back_and_charge"),
                        ),
                    ),
                ),
            )
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="template family"):
        generic_ir_support._validate_cavalcade_of_chaos_detachment_rule_ir(
            _detachment_rule_ir(
                "chaos-daemons:cavalcade-of-chaos:rule",
                clauses=(
                    _clause(
                        template_id=MOVEMENT_DISTANCE_TEMPLATE_ID,
                        effects=(
                            _grant_ability("can_fall_back_and_shoot"),
                            _grant_ability("can_fall_back_and_charge"),
                        ),
                    ),
                ),
            )
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="granted abilities"):
        generic_ir_support._validate_cavalcade_of_chaos_detachment_rule_ir(
            _detachment_rule_ir(
                "chaos-daemons:cavalcade-of-chaos:rule",
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability("can_fall_back_and_shoot"),),
                    ),
                ),
            )
        )


def test_single_effect_family_and_ability_parameter_validation_reject_shape_drift() -> None:
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="one clause"):
        generic_ir_support._validate_single_effect_family(
            rule_ir=_rule_ir(
                source_id="source-a",
                clauses=(
                    _clause(template_id=GRANT_ABILITY_TEMPLATE_ID, effects=(_grant_ability("a"),)),
                    _clause(
                        clause_id="clause-2",
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability("b"),),
                    ),
                ),
            ),
            expected_template_id=GRANT_ABILITY_TEMPLATE_ID,
            expected_effect_kind=RuleEffectKind.GRANT_ABILITY,
            row_name="Test Row",
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="template"):
        generic_ir_support._validate_single_effect_family(
            rule_ir=_rule_ir(
                source_id="source-a",
                clauses=(
                    _clause(
                        template_id=MOVEMENT_DISTANCE_TEMPLATE_ID,
                        effects=(_grant_ability("a"),),
                    ),
                ),
            ),
            expected_template_id=GRANT_ABILITY_TEMPLATE_ID,
            expected_effect_kind=RuleEffectKind.GRANT_ABILITY,
            row_name="Test Row",
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="diagnostics"):
        generic_ir_support._validate_single_effect_family(
            rule_ir=_rule_ir(
                source_id="source-a",
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability("a"),),
                        diagnostics=(_diagnostic(blocking=False),),
                    ),
                ),
            ),
            expected_template_id=GRANT_ABILITY_TEMPLATE_ID,
            expected_effect_kind=RuleEffectKind.GRANT_ABILITY,
            row_name="Test Row",
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="effect"):
        generic_ir_support._validate_single_effect_family(
            rule_ir=_rule_ir(
                source_id="source-a",
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_effect(RuleEffectKind.MODIFY_MOVE_DISTANCE),),
                    ),
                ),
            ),
            expected_template_id=GRANT_ABILITY_TEMPLATE_ID,
            expected_effect_kind=RuleEffectKind.GRANT_ABILITY,
            row_name="Test Row",
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="requires effect"):
        generic_ir_support._ability_parameter(cast(RuleEffectSpec, object()))
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="requires ability"):
        generic_ir_support._ability_parameter(_effect(RuleEffectKind.GRANT_ABILITY))


__all__: list[str] = []
__all__ += ["DICE_ROLL_MODIFIER_TEMPLATE_ID", "RuleClause", "RuleDuration", "RuleDurationKind"]
__all__ += ["RuleParseDiagnostic", "RuleUnsupportedReason", "TextSpan", "_blood_legion_rule_ir"]
__all__ += ["_duration", "_shadow_legion_rule_ir", "_span", "_stratagem_row"]
__all__ += ["_stratagem_rule_ir", "_stratagem_source_id", "blood_legion_ir", "corsair_ir"]
__all__ += ["parameters_from_pairs", "shadow_legion_ir"]
