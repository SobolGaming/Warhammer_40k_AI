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


__all__: list[str] = []
__all__ += ["DICE_ROLL_MODIFIER_TEMPLATE_ID", "GRANT_ABILITY_TEMPLATE_ID"]
__all__ += ["KEYWORD_GATE_TEMPLATE_ID", "MOVEMENT_DISTANCE_TEMPLATE_ID", "RuleClause"]
__all__ += ["RuleDuration", "RuleDurationKind", "RuleEffectKind", "RuleEffectSpec", "RuleIR"]
__all__ += ["RuleParseDiagnostic", "RuleUnsupportedReason", "TextSpan", "_blood_legion_rule_ir"]
__all__ += ["_clause", "_detachment_rule_ir", "_diagnostic", "_duration", "_effect"]
__all__ += ["_enhancement_row", "_enhancement_source_id", "_grant_ability"]
__all__ += ["_mixed_enhancement_rule_ir", "_rule_ir", "_shadow_legion_rule_ir", "_span"]
__all__ += ["_stratagem_row", "_stratagem_rule_ir", "_stratagem_source_id", "blood_legion_ir"]
__all__ += ["cast", "corsair_ir", "faction_detachments_2026_27", "faction_subrules_2026_27"]
__all__ += ["generic_ir_support", "parameters_from_pairs", "pytest", "shadow_legion_ir"]
