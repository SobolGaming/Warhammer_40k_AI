"""Typed passive permission inputs, with fresh source-record payloads per consumer."""

from typing import cast

from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.catalog_modifier_ignore import ModifierIgnoreKind
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleTargetKind,
    RuleTargetSpec,
    parameters_from_pairs,
)

PERMISSION_TEXT = "This model can ignore any or all modifiers to its Hit rolls."
SPAN = TextSpan(text=PERMISSION_TEXT, start=0, end=len(PERMISSION_TEXT))
PERMISSION_IR = RuleIR(
    rule_id="combat:retained-permission:rule",
    source_id="analytical:retained-permission",
    normalized_text=PERMISSION_TEXT,
    parser_version="combat-typed-contract-v1",
    clauses=(
        RuleClause(
            clause_id="combat:retained-permission:hit",
            source_span=SPAN,
            target=RuleTargetSpec(kind=RuleTargetKind.THIS_MODEL, source_span=SPAN),
            effects=(
                RuleEffectSpec(
                    kind=RuleEffectKind.GRANT_ABILITY,
                    source_span=SPAN,
                    parameters=parameters_from_pairs(
                        (
                            ("ability", "modifier_ignore_permission"),
                            ("modifier_kinds", (ModifierIgnoreKind.HIT_ROLL.value,)),
                            ("selection", "any_or_all"),
                        )
                    ),
                ),
            ),
            duration=RuleDuration(kind=RuleDurationKind.WHILE_CONDITION_TRUE, source_span=SPAN),
        ),
    ),
)
PERMISSION_SOURCE_KINDS = (AbilitySourceKind.DATASHEET, AbilitySourceKind.WARGEAR)


def retained_permission_index(unit: UnitInstance, kind: AbilitySourceKind) -> AbilityCatalogIndex:
    return AbilityCatalogIndex.from_records(
        (
            AbilityCatalogRecord(
                record_id="combat:retained-permission:" + kind.value,
                definition=AbilityDefinition(
                    ability_id="combat:retained-permission:ability",
                    name="Retained Hit permission",
                    source_id=PERMISSION_IR.source_id,
                    when_descriptor="Passive subject query",
                    effect_descriptor=PERMISSION_TEXT,
                    restrictions_descriptor="Authenticated bearer presence",
                    timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.PASSIVE_QUERY),
                    handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
                    replay_payload=validate_json_value(
                        {"rule_ir": cast(JsonValue, PERMISSION_IR.to_payload())}
                    ),
                ),
                source_kind=kind,
                datasheet_id=unit.datasheet_id,
                wargear_id=unit.own_models[0].wargear_ids[0]
                if kind is AbilitySourceKind.WARGEAR
                else None,
            ),
        )
    )
