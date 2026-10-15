from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from tests.shared.repository_root import REPOSITORY_ROOT
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.parsed_tokens import (
    DiceExpressionToken,
    DistancePredicateKind,
    DistancePredicateToken,
    ParsedRuleText,
    ParsedRuleTextPayload,
    RangeExpressionToken,
    RuleTokenError,
    TextSpan,
    distance_predicate_kind_from_token,
    parse_normalized_tokens,
)
from warhammer40k_core.rules.source_data import (
    RuleSourceText,
    RuleSourceTextPayload,
    SourceDataError,
)
from warhammer40k_core.rules.text_normalization import (
    OFFICIAL_STRATAGEM_REFERENCE_ALIAS_SOURCE_ID,
    NormalizedRuleText,
    NormalizedRuleTextPayload,
    TextNormalizationError,
    canonical_stratagem_reference_id,
    canonical_stratagem_reference_name,
    normalize_rule_text,
    normalize_source_characters,
    normalize_structured_source_text,
)

ROOT = REPOSITORY_ROOT
WAHAPEDIA_ABILITY_RULE_SOURCE_JSON_FILES = (
    "Abilities.json",
    "Datasheets_abilities.json",
    "Detachment_abilities.json",
    "Enhancements.json",
    "Stratagems.json",
)
WAHAPEDIA_2026_06_14_JSON_DIR = (
    ROOT
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / ("1" + "0" + "th-edition")
    / "2026-06-14"
    / "json"
)
EXPECTED_WAHAPEDIA_RULE_SOURCE_NON_ASCII_NORMALIZATION = {
    "\u00a0": " ",
    "\u00c9": "\u00c9",
    "\u00cb": "\u00cb",
    "\u00d4": "\u00d4",
    "\u00db": "\u00db",
    "\u00e2": "\u00e2",
    "\u00e4": "\u00e4",
    "\u00ea": "\u00ea",
    "\u00eb": "\u00eb",
    "\u00f4": "\u00f4",
    "\u00fa": "\u00fa",
    "\u00fb": "\u00fb",
    "\u2010": "-",
    "\u2011": "-",
    "\u2013": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2026": "...",
}


__all__: list[str] = []
__all__ += ["DiceExpression", "DiceExpressionToken", "DistancePredicateKind"]
__all__ += ["EXPECTED_WAHAPEDIA_RULE_SOURCE_NON_ASCII_NORMALIZATION", "DistancePredicateToken"]
__all__ += ["NormalizedRuleText", "NormalizedRuleTextPayload"]
__all__ += ["OFFICIAL_STRATAGEM_REFERENCE_ALIAS_SOURCE_ID", "ObjectiveRuleScope"]
__all__ += ["REPOSITORY_ROOT", "ROOT", "ParsedRuleText", "ParsedRuleTextPayload", "Path"]
__all__ += ["RangeExpressionToken", "RuleSourceText", "RuleSourceTextPayload", "RuleTokenError"]
__all__ += ["SourceDataError", "TextNormalizationError", "TextSpan"]
__all__ += ["WAHAPEDIA_2026_06_14_JSON_DIR", "WAHAPEDIA_ABILITY_RULE_SOURCE_JSON_FILES"]
__all__ += ["canonical_stratagem_reference_id", "canonical_stratagem_reference_name", "cast"]
__all__ += ["distance_predicate_kind_from_token", "json", "normalize_rule_text"]
__all__ += ["normalize_source_characters", "normalize_structured_source_text"]
__all__ += ["parse_normalized_tokens", "pytest"]
