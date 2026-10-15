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


def test_cavalcade_and_aeldari_stratagem_validators_reject_drift() -> None:
    source_row = _stratagem_row(generic_ir_support.CAVALCADE_OF_CHAOS_WARP_RIDERS_SOURCE_ROW_ID)

    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="requires RuleIR"):
        generic_ir_support._validate_cavalcade_of_chaos_stratagem_rule_ir(
            rule_ir=cast(RuleIR, object()),
            source_row=source_row,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="source row"):
        generic_ir_support._validate_cavalcade_of_chaos_stratagem_rule_ir(
            rule_ir=_stratagem_rule_ir(
                source_row.source_row_id,
                effects=(_grant_ability("warp-riders"),),
                duration=_duration("phase"),
            ),
            source_row=cast(faction_subrules_2026_27.SourceStratagemRow, object()),
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="supported"):
        generic_ir_support._validate_cavalcade_of_chaos_stratagem_rule_ir(
            rule_ir=_stratagem_rule_ir(
                source_row.source_row_id,
                effects=(_grant_ability("warp-riders"),),
                duration=_duration("phase"),
                diagnostics=(_diagnostic(blocking=True),),
            ),
            source_row=source_row,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="source ID"):
        generic_ir_support._validate_cavalcade_of_chaos_stratagem_rule_ir(
            rule_ir=_rule_ir(
                source_id="wrong-source",
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_grant_ability("warp-riders"),),
                        duration=_duration("phase"),
                    ),
                ),
            ),
            source_row=source_row,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="timing endpoint"):
        generic_ir_support._validate_cavalcade_of_chaos_stratagem_rule_ir(
            rule_ir=_stratagem_rule_ir(
                source_row.source_row_id,
                effects=(_grant_ability("warp-riders"),),
            ),
            source_row=source_row,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="end of the phase"):
        generic_ir_support._validate_cavalcade_of_chaos_stratagem_rule_ir(
            rule_ir=_stratagem_rule_ir(
                source_row.source_row_id,
                effects=(_grant_ability("warp-riders"),),
                duration=_duration("turn"),
            ),
            source_row=source_row,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="not registered"):
        generic_ir_support._validate_cavalcade_of_chaos_stratagem_rule_ir(
            rule_ir=_stratagem_rule_ir(
                "stratagem:test-detachment:unregistered",
                effects=(_grant_ability("marker"),),
            ),
            source_row=_stratagem_row("stratagem:test-detachment:unregistered"),
        )

    aeldari_source_row = _stratagem_row(corsair_ir.CLOAK_AND_SHADOW_SOURCE_ROW_ID)
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="requires RuleIR"):
        generic_ir_support._validate_aeldari_stratagem_rule_ir(
            rule_ir=cast(RuleIR, object()),
            source_row=aeldari_source_row,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="source row"):
        generic_ir_support._validate_aeldari_stratagem_rule_ir(
            rule_ir=_stratagem_rule_ir(
                aeldari_source_row.source_row_id,
                effects=(_effect(RuleEffectKind.SET_CONTEXTUAL_STATUS),),
            ),
            source_row=cast(faction_subrules_2026_27.SourceStratagemRow, object()),
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="supported"):
        generic_ir_support._validate_aeldari_stratagem_rule_ir(
            rule_ir=_stratagem_rule_ir(
                aeldari_source_row.source_row_id,
                effects=(_effect(RuleEffectKind.SET_CONTEXTUAL_STATUS),),
                diagnostics=(_diagnostic(blocking=True),),
            ),
            source_row=aeldari_source_row,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="source ID"):
        generic_ir_support._validate_aeldari_stratagem_rule_ir(
            rule_ir=_rule_ir(
                source_id="wrong-source",
                clauses=(
                    _clause(
                        template_id=GRANT_ABILITY_TEMPLATE_ID,
                        effects=(_effect(RuleEffectKind.SET_CONTEXTUAL_STATUS),),
                    ),
                ),
            ),
            source_row=aeldari_source_row,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="diagnostics"):
        generic_ir_support._validate_aeldari_stratagem_rule_ir(
            rule_ir=_stratagem_rule_ir(
                aeldari_source_row.source_row_id,
                effects=(_effect(RuleEffectKind.SET_CONTEXTUAL_STATUS),),
                diagnostics=(_diagnostic(blocking=False),),
            ),
            source_row=aeldari_source_row,
        )
    with pytest.raises(generic_ir_support.Phase17FGenericIrSupportError, match="include effects"):
        generic_ir_support._validate_aeldari_stratagem_rule_ir(
            rule_ir=_stratagem_rule_ir(
                aeldari_source_row.source_row_id,
                effects=(),
                duration=_duration("phase"),
            ),
            source_row=aeldari_source_row,
        )


__all__: list[str] = []
__all__ += ["DICE_ROLL_MODIFIER_TEMPLATE_ID", "KEYWORD_GATE_TEMPLATE_ID"]
__all__ += ["MOVEMENT_DISTANCE_TEMPLATE_ID", "RuleClause", "RuleDuration", "RuleDurationKind"]
__all__ += ["RuleEffectSpec", "RuleParseDiagnostic", "RuleUnsupportedReason", "TextSpan"]
__all__ += ["_blood_legion_rule_ir", "_detachment_rule_ir", "_enhancement_row"]
__all__ += ["_enhancement_source_id", "_mixed_enhancement_rule_ir", "_shadow_legion_rule_ir"]
__all__ += ["_span", "_stratagem_source_id", "blood_legion_ir", "faction_detachments_2026_27"]
__all__ += ["parameters_from_pairs", "shadow_legion_ir"]
