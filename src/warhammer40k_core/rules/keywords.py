from __future__ import annotations

from enum import StrEnum


class RuleKeyword(StrEnum):
    BATTLE_SHOCK = "Battle-shock"
    FEEL_NO_PAIN = "Feel No Pain"


def canonical_rule_keyword_tokens() -> tuple[str, ...]:
    return tuple(keyword.value for keyword in RuleKeyword)
