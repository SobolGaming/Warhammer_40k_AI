"""Source-bound Psychic level descriptors; runtime consumers never parse labels."""

from __future__ import annotations

import re
from dataclasses import replace

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleCondition,
    RuleConditionKind,
    RuleIR,
    RuleIRError,
    parameter_payload,
    parameters_from_pairs,
)

PSYCHIC_ABILITY_USE = "psychic_ability_use"
_LEVEL_TAG = re.compile(r"^[^:\n]*\(psychic level ([1-9][0-9]*)\)\s*:", re.IGNORECASE)


def bind_psychic_level_at_source_boundary(rule_ir: RuleIR) -> RuleIR:
    match = _LEVEL_TAG.match(rule_ir.normalized_text)
    if match is None:
        return rule_ir
    level = int(match.group(1))
    return replace(
        rule_ir,
        clauses=tuple(
            clause
            if any(
                parameter_payload(condition.parameters).get("activation_kind")
                == PSYCHIC_ABILITY_USE
                for condition in clause.conditions
            )
            else replace(
                clause,
                conditions=(
                    *clause.conditions,
                    RuleCondition(
                        kind=RuleConditionKind.FREQUENCY_LIMIT,
                        source_span=clause.source_span,
                        parameters=parameters_from_pairs(
                            (
                                ("activation_kind", PSYCHIC_ABILITY_USE),
                                ("psychic_level", level),
                                ("scope", "phase"),
                                ("max_uses", 1),
                            )
                        ),
                    ),
                ),
            )
            for clause in rule_ir.clauses
        ),
    )


def parse_psychic_level_condition(span: TextSpan) -> tuple[RuleCondition, ...]:
    match = _LEVEL_TAG.match(span.text)
    if match is None:
        return ()
    return (
        RuleCondition(
            kind=RuleConditionKind.FREQUENCY_LIMIT,
            source_span=TextSpan(
                text=match.group(), start=span.start, end=span.start + match.end()
            ),
            parameters=parameters_from_pairs(
                (
                    ("activation_kind", PSYCHIC_ABILITY_USE),
                    ("psychic_level", int(match.group(1))),
                    ("scope", "phase"),
                    ("max_uses", 1),
                )
            ),
        ),
    )


def psychic_ability_level(rule_ir: RuleIR) -> int | None:
    levels: set[int] = set()
    for clause in rule_ir.clauses:
        for condition in clause.conditions:
            if condition.kind is not RuleConditionKind.FREQUENCY_LIMIT:
                continue
            parameters = parameter_payload(condition.parameters)
            if parameters.get("activation_kind") != PSYCHIC_ABILITY_USE:
                continue
            level = parameters.get("psychic_level")
            if (
                set(parameters) != {"activation_kind", "psychic_level", "scope", "max_uses"}
                or type(level) is not int
                or level < 1
                or parameters["scope"] != "phase"
                or type(parameters["max_uses"]) is not int
                or parameters["max_uses"] != 1
            ):
                raise RuleIRError("Psychic ability frequency descriptor is malformed.")
            levels.add(level)
    if len(levels) > 1:
        raise RuleIRError("One psychic ability has conflicting level descriptors.")
    return next(iter(levels)) if levels else None
