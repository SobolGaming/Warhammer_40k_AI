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


def test_shadow_and_blood_legion_detachment_validators_reject_drift() -> None:
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="requires RuleIR"):
        generic_ir_support._validate_shadow_legion_detachment_rule_ir(cast(RuleIR, object()))
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="supported"):
        generic_ir_support._validate_shadow_legion_detachment_rule_ir(
            _detachment_rule_ir(
                "chaos-daemons:shadow-legion:rule",
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability("marker"),),
                        diagnostics=(_diagnostic(blocking=True),),
                    ),
                ),
            )
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="source ID"):
        generic_ir_support._validate_shadow_legion_detachment_rule_ir(
            _rule_ir(
                source_id="wrong-source",
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability("marker"),),
                    ),
                ),
            )
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="template family"):
        generic_ir_support._validate_shadow_legion_detachment_rule_ir(
            _detachment_rule_ir(
                "chaos-daemons:shadow-legion:rule",
                clauses=(
                    _clause(
                        template_id=MOVEMENT_DISTANCE_TEMPLATE_ID,
                        effects=(_grant_ability("marker"),),
                    ),
                ),
            )
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="granted abilities"):
        generic_ir_support._validate_shadow_legion_detachment_rule_ir(
            _detachment_rule_ir(
                "chaos-daemons:shadow-legion:rule",
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability("marker"),),
                    ),
                    _clause(
                        clause_id="clause-2",
                        template_id=DICE_ROLL_MODIFIER_TEMPLATE_ID,
                        effects=(_effect(RuleEffectKind.MODIFY_DICE_ROLL, ("roll_type", "hit")),),
                    ),
                ),
            )
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="roll types"):
        generic_ir_support._validate_shadow_legion_detachment_rule_ir(
            _shadow_legion_rule_ir(modifier_roll_types=("hit",))
        )

    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="requires RuleIR"):
        generic_ir_support._validate_blood_legion_detachment_rule_ir(cast(RuleIR, object()))
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="supported"):
        generic_ir_support._validate_blood_legion_detachment_rule_ir(
            _detachment_rule_ir(
                "chaos-daemons:blood-legion:rule",
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability(blood_legion_ir.MURDERCALL_SURGE_ABILITY),),
                        diagnostics=(_diagnostic(blocking=True),),
                    ),
                ),
            )
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="source ID"):
        generic_ir_support._validate_blood_legion_detachment_rule_ir(
            _rule_ir(
                source_id="wrong-source",
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability(blood_legion_ir.MURDERCALL_SURGE_ABILITY),),
                    ),
                ),
            )
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="template family"):
        generic_ir_support._validate_blood_legion_detachment_rule_ir(
            _detachment_rule_ir(
                "chaos-daemons:blood-legion:rule",
                clauses=(
                    _clause(
                        template_id=MOVEMENT_DISTANCE_TEMPLATE_ID,
                        effects=(_grant_ability(blood_legion_ir.MURDERCALL_SURGE_ABILITY),),
                    ),
                ),
            )
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="granted abilities"):
        generic_ir_support._validate_blood_legion_detachment_rule_ir(
            _detachment_rule_ir(
                "chaos-daemons:blood-legion:rule",
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability(blood_legion_ir.MURDERCALL_SURGE_ABILITY),),
                    ),
                ),
            )
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="faction keyword"):
        generic_ir_support._validate_blood_legion_detachment_rule_ir(
            _blood_legion_rule_ir(
                required_faction_keyword_sequence=("WRONG",),
                required_keyword_sequence=(blood_legion_ir.KHORNE_KEYWORD,),
            )
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="keyword gate"):
        generic_ir_support._validate_blood_legion_detachment_rule_ir(
            _blood_legion_rule_ir(
                required_faction_keyword_sequence=(blood_legion_ir.LEGIONES_DAEMONICA_KEYWORD,),
                required_keyword_sequence=("WRONG",),
            )
        )


__all__: list[str] = []
__all__ += ["KEYWORD_GATE_TEMPLATE_ID", "RuleClause", "RuleDuration", "RuleDurationKind"]
__all__ += ["RuleEffectSpec", "RuleParseDiagnostic", "RuleUnsupportedReason", "TextSpan"]
__all__ += ["_duration", "_enhancement_row", "_enhancement_source_id"]
__all__ += ["_mixed_enhancement_rule_ir", "_span", "_stratagem_row", "_stratagem_rule_ir"]
__all__ += ["_stratagem_source_id", "corsair_ir", "faction_detachments_2026_27"]
__all__ += ["faction_subrules_2026_27", "parameters_from_pairs", "shadow_legion_ir"]
