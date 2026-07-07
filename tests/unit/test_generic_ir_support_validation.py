# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import cast

import pytest

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleParseDiagnostic,
    RuleUnsupportedReason,
    parameters_from_pairs,
)
from warhammer40k_core.rules.rule_templates import (
    DICE_ROLL_MODIFIER_TEMPLATE_ID,
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
    MOVEMENT_DISTANCE_TEMPLATE_ID,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_aeldari_corsair_coterie_ir_support_2026_27 as corsair_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as blood_legion_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27,
    faction_subrules_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_generic_ir_support_2026_27 as generic_ir_support,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_shadow_legion_ir_support_2026_27 as shadow_legion_ir,
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


def _span() -> TextSpan:
    return TextSpan(text="effect", start=0, end=6)


def _diagnostic(*, blocking: bool) -> RuleParseDiagnostic:
    return RuleParseDiagnostic(
        reason=RuleUnsupportedReason.UNSUPPORTED_LANGUAGE,
        message="bad",
        source_span=_span(),
        blocking=blocking,
    )


def _effect(
    kind: RuleEffectKind,
    *parameters: tuple[str, str | int | float | bool | None | tuple[str, ...]],
) -> RuleEffectSpec:
    return RuleEffectSpec(
        kind=kind,
        source_span=_span(),
        parameters=parameters_from_pairs(parameters),
    )


def _grant_ability(
    ability: str,
    *extra_parameters: tuple[str, str | int | float | bool | None | tuple[str, ...]],
) -> RuleEffectSpec:
    return _effect(
        RuleEffectKind.GRANT_ABILITY,
        ("ability", ability),
        *extra_parameters,
    )


def _duration(endpoint: str) -> RuleDuration:
    return RuleDuration(
        kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
        source_span=_span(),
        parameters=parameters_from_pairs((("endpoint", endpoint),)),
    )


def _clause(
    *,
    template_id: str,
    effects: tuple[RuleEffectSpec, ...],
    clause_id: str = "clause-1",
    duration: RuleDuration | None = None,
    diagnostics: tuple[RuleParseDiagnostic, ...] = (),
) -> RuleClause:
    return RuleClause(
        clause_id=clause_id,
        template_id=template_id,
        source_span=_span(),
        effects=effects,
        duration=duration,
        diagnostics=diagnostics,
    )


def _rule_ir(
    *,
    source_id: str,
    clauses: tuple[RuleClause, ...],
) -> RuleIR:
    return RuleIR(
        rule_id="test-rule",
        source_id=source_id,
        normalized_text="effect",
        parser_version="test-parser",
        clauses=clauses,
    )


def _enhancement_row(source_row_id: str) -> faction_subrules_2026_27.SourceEnhancementRow:
    return faction_subrules_2026_27.SourceEnhancementRow(
        source_row_id=source_row_id,
        faction_id="test-faction",
        faction_name="Test Faction",
        detachment_id="test-detachment",
        detachment_name="Test Detachment",
        enhancement_id="test-enhancement",
        name="Test Enhancement",
        points=10,
        source_ids=("source-a",),
    )


def _stratagem_row(source_row_id: str) -> faction_subrules_2026_27.SourceStratagemRow:
    return faction_subrules_2026_27.SourceStratagemRow(
        source_row_id=source_row_id,
        faction_id="test-faction",
        faction_name="Test Faction",
        detachment_id="test-detachment",
        detachment_name="Test Detachment",
        stratagem_id="test-stratagem",
        name="Test Stratagem",
        command_point_cost=1,
        timing_descriptor="test timing",
        category="battle tactic",
        source_ids=("source-a",),
    )


def _enhancement_source_id(source_row_id: str) -> str:
    return f"{generic_ir_support.SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text"


def _stratagem_source_id(source_row_id: str) -> str:
    return f"{generic_ir_support.SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text"


def _detachment_rule_ir(
    descriptor_id: str,
    *,
    clauses: tuple[RuleClause, ...],
) -> RuleIR:
    return _rule_ir(
        source_id=f"{generic_ir_support.SOURCE_PACKAGE_ID}:phase17e:{descriptor_id}:source-text",
        clauses=clauses,
    )


def _mixed_enhancement_rule_ir(
    *,
    source_id: str,
    diagnostics: tuple[RuleParseDiagnostic, ...] = (),
) -> RuleIR:
    return _rule_ir(
        source_id=source_id,
        clauses=(
            _clause(
                template_id=GRANT_ABILITY_TEMPLATE_ID,
                effects=(_grant_ability("marker"),),
                diagnostics=diagnostics,
            ),
            _clause(
                clause_id="clause-2",
                template_id=KEYWORD_GATE_TEMPLATE_ID,
                effects=(_grant_ability("keyword-marker"),),
            ),
            _clause(
                clause_id="clause-3",
                template_id=MOVEMENT_DISTANCE_TEMPLATE_ID,
                effects=(_effect(RuleEffectKind.MODIFY_MOVE_DISTANCE),),
            ),
        ),
    )


def _shadow_legion_rule_ir(*, modifier_roll_types: tuple[str, ...]) -> RuleIR:
    grant_effects = tuple(
        _grant_ability(ability)
        for ability in (
            shadow_legion_ir.CAN_ADVANCE_AND_SHOOT_AND_CHARGE_ABILITY,
            shadow_legion_ir.SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY,
            shadow_legion_ir.SHADOW_LEGION_DARK_PACT_LETHAL_HITS_CHOICE_ABILITY,
            shadow_legion_ir.SHADOW_LEGION_DARK_PACT_SUSTAINED_HITS_1_CHOICE_ABILITY,
        )
    )
    modifier_effects = tuple(
        _effect(RuleEffectKind.MODIFY_DICE_ROLL, ("roll_type", roll_type))
        for roll_type in modifier_roll_types
    )
    return _detachment_rule_ir(
        "chaos-daemons:shadow-legion:rule",
        clauses=(
            _clause(template_id=GRANT_ABILITY_TEMPLATE_ID, effects=grant_effects),
            _clause(
                clause_id="clause-2",
                template_id=DICE_ROLL_MODIFIER_TEMPLATE_ID,
                effects=modifier_effects,
            ),
        ),
    )


def _blood_legion_rule_ir(
    *,
    required_faction_keyword_sequence: tuple[str, ...],
    required_keyword_sequence: tuple[str, ...],
) -> RuleIR:
    effects = tuple(
        _grant_ability(
            ability,
            ("required_faction_keyword_sequence", required_faction_keyword_sequence),
            ("required_keyword_sequence", required_keyword_sequence),
        )
        for ability in (
            blood_legion_ir.MURDERCALL_SURGE_ABILITY,
            blood_legion_ir.BLOOD_TAINTED_STICKY_OBJECTIVE_ABILITY,
        )
    )
    return _detachment_rule_ir(
        "chaos-daemons:blood-legion:rule",
        clauses=(
            _clause(
                template_id=GRANT_ABILITY_TEMPLATE_ID,
                effects=(*effects, _effect(RuleEffectKind.MODIFY_MOVE_DISTANCE)),
            ),
        ),
    )


def _stratagem_rule_ir(
    source_row_id: str,
    *,
    effects: tuple[RuleEffectSpec, ...],
    duration: RuleDuration | None = None,
    diagnostics: tuple[RuleParseDiagnostic, ...] = (),
) -> RuleIR:
    return _rule_ir(
        source_id=_stratagem_source_id(source_row_id),
        clauses=(
            _clause(
                template_id=GRANT_ABILITY_TEMPLATE_ID,
                effects=effects,
                duration=duration,
                diagnostics=diagnostics,
            ),
        ),
    )
