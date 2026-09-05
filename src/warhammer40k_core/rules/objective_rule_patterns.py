"""Source-boundary objective forms; Core marker wording retains its distinct token."""

import re

OBJECTIVE_REROLL_INSTEAD_RE = re.compile(
    r"\bif\s+the\s+target\s+of\s+that\s+attack\s+is\s+within\s+range\s+of\s+"
    r"an?\s+objective(?:\s+marker)?,\s+you\s+can\s+(?:re-roll|reroll)\s+"
    r"(?:the\s+)?(?P<roll>hit|wound|damage|save)\s+roll\s+instead\b",
    re.IGNORECASE,
)


DISTANCE_RELATION_RE = re.compile(
    r"\b(?:(?P<subject>this\s+unit|this\s+model|that\s+unit|selected\s+unit|"
    r"target\s+unit)\s+is\s+)?"
    r"(?P<negated>not\s+)?"
    r"(?P<predicate>wholly\s+within|within)\s+"
    r"(?P<range>Engagement\s+Range|Objective(?:\s+Marker)?\s+Range|\d+(?:\.\d+)?\")\s+"
    r"of\s+(?:and\s+visible\s+to\s+)?"
    r"(?:(?P<quantity>one\s+or\s+more|any|a|an)\s+)?"
    r"(?:(?P<allegiance>enemy|friendly)\s+)?"
    r"(?:(?P<object_reference>this|that|selected|target)\s+)?"
    r"(?:(?P<keyword>[A-Z][A-Z0-9_'-]*(?:\s+[A-Z0-9_'-]+){0,5})\s+)?"
    r"(?P<object_kind>units?|models?|objective\s+markers?|objectives?|fortifications?)"
    r"(?:\s+from\s+(?P<object_owner>your\s+army)"
    r"(?:\s+with\s+(?P<object_ability_scope>this\s+ability))?)?\b",
    re.IGNORECASE,
)
