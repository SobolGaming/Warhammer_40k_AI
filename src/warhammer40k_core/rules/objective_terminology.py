"""Apply the v931 objective-reference alias only at a declared source boundary."""

from __future__ import annotations

import re
from enum import StrEnum

from warhammer40k_core.rules.text_normalization import TextNormalizationError, normalize_rule_text

OBJECTIVE_TERMINOLOGY_SOURCE_ID = "gw-11e-core-objectives:objective-marker-terminology-faq"
_MARKER_REFERENCE = re.compile(
    r"\b(?P<objective>objective)(?P<gap>\s+)marker(?P<plural>s?)\b", re.IGNORECASE
)


class ObjectiveRuleScope(StrEnum):
    HISTORICAL_TEXT = "historical_text"
    CORE_RULES = "core_rules"
    NON_CORE_RULES = "non_core_rules"


def objective_rule_scope_from_token(value: object) -> ObjectiveRuleScope:
    if type(value) is ObjectiveRuleScope:
        return value
    if type(value) is not str:
        raise TextNormalizationError("Objective terminology scope must be a string token.")
    try:
        return ObjectiveRuleScope(value)
    except ValueError as exc:
        raise TextNormalizationError("Objective terminology scope is unsupported.") from exc


def normalize_objective_rule_text(raw_text: object, *, scope: ObjectiveRuleScope) -> str:
    if type(scope) is not ObjectiveRuleScope:
        raise TextNormalizationError(
            "Objective terminology requires an explicit typed source scope."
        )
    normalized = normalize_rule_text(raw_text)
    if scope is ObjectiveRuleScope.NON_CORE_RULES:
        return _MARKER_REFERENCE.sub(_objective_reference, normalized)
    return normalized


def _objective_reference(match: re.Match[str]) -> str:
    objective = match["objective"]
    plural = match["plural"]
    if not plural:
        return objective
    return objective + ("S" if objective.isupper() else "s")
