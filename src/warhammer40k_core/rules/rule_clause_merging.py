from __future__ import annotations

import re

from warhammer40k_core.rules.parsed_tokens import TextSpan

_POST_SHOOT_HIT_TARGET_SELECTION_RE = re.compile(
    r"\b(?:(?:in|during)\s+your\s+Shooting\s+phase,\s*)?"
    r"(?:(?:after|each\s+time)\s+)?"
    r"(?P<subject>this\s+model|this\s+unit|the\s+bearer|bearer)\s+has\s+shot,\s+"
    r"select\s+one\s+enemy\s+unit\s+(?:that\s+was\s+)?hit\s+by\s+one\s+or\s+more\s+of\s+"
    r"those\s+attacks\b",
    re.IGNORECASE,
)
_HIT_BY_THOSE_ATTACKS_TARGET_SELECTION_RE = re.compile(
    r"\bselect\s+one\s+enemy\s+unit\s+(?:that\s+was\s+)?hit\s+by\s+one\s+or\s+"
    r"more\s+of\s+those\s+attacks\b",
    re.IGNORECASE,
)
_POST_SHOOT_OR_HIT_TARGET_SELECTION_RE = re.compile(
    rf"(?:{_POST_SHOOT_HIT_TARGET_SELECTION_RE.pattern})|"
    rf"(?:{_HIT_BY_THOSE_ATTACKS_TARGET_SELECTION_RE.pattern})",
    re.IGNORECASE,
)
_CONTEXTUAL_STATUS_DENIAL_RE = re.compile(
    r"\b(?P<subject>"
    r"that\s+enemy\s+unit|that\s+unit|selected\s+unit|target\s+unit|"
    r"models\s+in\s+that\s+enemy\s+unit|models\s+in\s+that\s+unit|"
    r"models\s+in\s+the\s+selected\s+unit|models\s+in\s+the\s+target\s+unit"
    r")\s+cannot\s+have\s+(?:the\s+)?"
    r"(?P<status>[A-Z][A-Za-z0-9 +'_-]+?)(?=\s*(?:\.|,|;|$))",
    re.IGNORECASE,
)
_ABILITY_CHOICE_PREFIX_RE = re.compile(
    r"\bselect\s+one\s+of\s+the\s+following\s+abilities\s*:",
    re.IGNORECASE,
)
_THAT_ABILITY_APPLICATION_RE = re.compile(r"\bthat\s+ability\b", re.IGNORECASE)
_THIS_UNIT_NORMAL_ADVANCE_FALL_BACK_MOVE_RE = re.compile(
    r"\beach\s+time\s+this\s+unit\s+makes\s+a\s+"
    r"(?P<modes>(?:Normal|Advance|Fall\s+Back)"
    r"(?:(?:\s*,\s*|\s+or\s+|\s+and\s+)(?:Normal|Advance|Fall\s+Back))*)"
    r"\s+move\b",
    re.IGNORECASE,
)
_MOVE_THROUGH_MODELS_AND_TERRAIN_RE = re.compile(
    r"\bit\s+can\s+move\s+through\s+models"
    r"(?:\s+\(excluding\s+(?P<excluded_model_keywords>[^)]+)\))?"
    r"\s+and\s+terrain\s+features\b",
    re.IGNORECASE,
)
_MOVE_THROUGH_ENGAGEMENT_AUTO_PASS_RE = re.compile(
    r"\bwhen\s+doing\s+so,\s+it\s+can\s+move\s+within\s+Engagement\s+Range\s+of\s+"
    r"enemy\s+models,\s+but\s+cannot\s+end\s+that\s+move\s+within\s+Engagement\s+"
    r"Range\s+of\s+them,\s+and\s+any\s+Desperate\s+Escape\s+test\s+is\s+"
    r"automatically\s+passed\b",
    re.IGNORECASE,
)
_FIRE_OVERWATCH_HIT_SUCCESS_THRESHOLD_BASE_RE = re.compile(
    r"\beach\s+time\s+you\s+target\s+this\s+unit\s+with\s+the\s+"
    r"Fire\s+Overwatch\s+Stratagem,\s+hits\s+are\s+scored\s+on\s+"
    r"unmodified\s+Hit\s+rolls\s+of\s+[2-6]\+",
    re.IGNORECASE,
)
_WHEN_RESOLVING_THAT_STRATAGEM_RE = re.compile(
    r"\bwhen\s+resolving\s+that\s+Stratagem\b",
    re.IGNORECASE,
)
_FIRE_OVERWATCH_HIT_SUCCESS_THRESHOLD_RE = re.compile(
    r"\beach\s+time\s+you\s+target\s+this\s+unit\s+with\s+the\s+"
    r"Fire\s+Overwatch\s+Stratagem,\s+hits\s+are\s+scored\s+on\s+"
    r"unmodified\s+Hit\s+rolls\s+of\s+[2-6]\+\s+when\s+resolving\s+"
    r"that\s+Stratagem\b",
    re.IGNORECASE,
)
_THOSE_ATTACKS_PROXIMITY_HIT_SUCCESS_THRESHOLD_RE = re.compile(
    r"\bfor\s+each\s+of\s+those\s+attacks\s+that\s+targets\s+an\s+enemy\s+unit\s+"
    r"within\s+\d+(?:\.\d+)?\"\s+of\s+one\s+or\s+more\s+.+?\s+units\s+from\s+"
    r"your\s+army,\s+a\s+hit\s+is\s+scored\s+on\s+an?\s+unmodified\s+Hit\s+roll\s+"
    r"of\s+[2-6]\+\s+instead\b",
    re.IGNORECASE,
)


def merge_rule_clause_spans(
    normalized_text: str,
    spans: tuple[TextSpan, ...],
) -> tuple[TextSpan, ...]:
    merged = _merge_adjacent_clause_spans(
        normalized_text=normalized_text,
        spans=spans,
        current_patterns=(_ABILITY_CHOICE_PREFIX_RE,),
        next_pattern=_THAT_ABILITY_APPLICATION_RE,
    )
    merged = _merge_adjacent_clause_spans(
        normalized_text=normalized_text,
        spans=merged,
        current_patterns=(_POST_SHOOT_OR_HIT_TARGET_SELECTION_RE,),
        next_pattern=_CONTEXTUAL_STATUS_DENIAL_RE,
    )
    merged = _merge_adjacent_clause_spans(
        normalized_text=normalized_text,
        spans=merged,
        current_patterns=(_FIRE_OVERWATCH_HIT_SUCCESS_THRESHOLD_BASE_RE,),
        next_pattern=_WHEN_RESOLVING_THAT_STRATAGEM_RE,
    )
    merged = _merge_adjacent_clause_spans(
        normalized_text=normalized_text,
        spans=merged,
        current_patterns=(_FIRE_OVERWATCH_HIT_SUCCESS_THRESHOLD_RE,),
        next_pattern=_THOSE_ATTACKS_PROXIMITY_HIT_SUCCESS_THRESHOLD_RE,
    )
    return _merge_adjacent_clause_spans(
        normalized_text=normalized_text,
        spans=merged,
        current_patterns=(
            _THIS_UNIT_NORMAL_ADVANCE_FALL_BACK_MOVE_RE,
            _MOVE_THROUGH_MODELS_AND_TERRAIN_RE,
        ),
        next_pattern=_MOVE_THROUGH_ENGAGEMENT_AUTO_PASS_RE,
    )


def _merge_adjacent_clause_spans(
    *,
    normalized_text: str,
    spans: tuple[TextSpan, ...],
    current_patterns: tuple[re.Pattern[str], ...],
    next_pattern: re.Pattern[str],
) -> tuple[TextSpan, ...]:
    merged: list[TextSpan] = []
    index = 0
    while index < len(spans):
        current = spans[index]
        if (
            index + 1 < len(spans)
            and all(pattern.search(current.text) is not None for pattern in current_patterns)
            and next_pattern.search(spans[index + 1].text) is not None
        ):
            next_span = spans[index + 1]
            merged.append(
                TextSpan(
                    text=normalized_text[current.start : next_span.end],
                    start=current.start,
                    end=next_span.end,
                )
            )
            index += 2
            continue
        merged.append(current)
        index += 1
    return tuple(merged)
