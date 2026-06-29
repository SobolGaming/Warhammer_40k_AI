from __future__ import annotations

import re
from dataclasses import dataclass

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.weapon_profiles import canonical_weapon_keyword_tokens
from warhammer40k_core.rules.parsed_tokens import DistancePredicateToken, ParsedRuleText, TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleIRError,
    RuleParameterValue,
    RuleParseDiagnostic,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    RuleUnsupportedReason,
    parameters_from_pairs,
)
from warhammer40k_core.rules.rule_templates import (
    AURA_TEMPLATE_ID,
    CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
    CHARACTERISTIC_SET_TEMPLATE_ID,
    DICE_ROLL_MODIFIER_TEMPLATE_ID,
    DISTANCE_PREDICATE_TEMPLATE_ID,
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
    MOVEMENT_DISTANCE_TEMPLATE_ID,
    PLACEMENT_TEMPLATE_ID,
    REROLL_PERMISSION_TEMPLATE_ID,
    RESOURCE_MODIFIER_TEMPLATE_ID,
    SELECTED_TARGET_TEMPLATE_ID,
    TIMING_WINDOW_TEMPLATE_ID,
    WEAPON_ABILITY_GRANT_TEMPLATE_ID,
    rule_template_by_id,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14,
)

RULE_PARSER_VERSION = "phase17c-rule-parser-v1"

_PHASES = "command|movement|shooting|charge|fight"
_ROLL_TYPES = (
    "advance|battle-shock|charge|critical hit|critical wound|damage|feel no pain|hazardous|"
    "hit|invulnerable save|leadership|save|wound"
)
_TIMING_OWNER_PATTERN = (
    r"your\s+opponent(?:'|\u2019)s|the\s+opponent(?:'|\u2019)s|"
    r"opponent(?:'|\u2019)s|your|the"
)
_START_END_PHASE_RE = re.compile(
    rf"\bat\s+the\s+(?P<edge>start|end)\s+of\s+"
    rf"(?:(?P<owner>{_TIMING_OWNER_PATTERN})\s+)?(?P<phase>{_PHASES})\s+phase\b",
    re.IGNORECASE,
)
_START_END_TURN_RE = re.compile(
    r"\bat\s+the\s+(?P<edge>start|end)\s+of\s+"
    rf"(?P<owner>{_TIMING_OWNER_PATTERN})\s+turn\b",
    re.IGNORECASE,
)
_IN_PHASE_RE = re.compile(
    rf"\b(?:in|during)\s+(?:(?P<owner>{_TIMING_OWNER_PATTERN})\s+)?"
    rf"(?P<phase>{_PHASES})\s+phase\b",
    re.IGNORECASE,
)
_IN_TURN_RE = re.compile(
    rf"\b(?:in|during)\s+(?P<owner>{_TIMING_OWNER_PATTERN})\s+turn\b",
    re.IGNORECASE,
)
_DESTROYED_UNIT_RE = re.compile(r"\bwhen\s+this\s+unit\s+is\s+destroyed\b", re.IGNORECASE)
_DESTROYED_MODEL_RE = re.compile(r"\bwhen\s+.*\bmodel\s+is\s+destroyed\b", re.IGNORECASE)
_CHARGE_MOVE_END_RE = re.compile(
    r"\b(?:each\s+time|when)\s+(?P<subject>that\s+unit|this\s+unit|a\s+unit)\s+ends\s+"
    r"a\s+charge\s+move\b",
    re.IGNORECASE,
)
_SETUP_RE = re.compile(r"\b(?:deployment|before\s+the\s+battle|set\s+up)\b", re.IGNORECASE)
_DICE_TRIGGER_RE = re.compile(
    rf"\b(?:after|when|each\s+time)\s+.*\b(?P<roll>{_ROLL_TYPES})\s+roll", re.IGNORECASE
)
_ONCE_PER_RE = re.compile(
    r"\bonce\s+per\s+(?P<scope>phase|turn|battle|battle round)\b", re.IGNORECASE
)
_AURA_RE = re.compile(r"(?:\bAura\b|^\s*Aura\s*:)", re.IGNORECASE)
_LEADING_UNIT_RE = re.compile(
    r"\bwhile\s+this\s+model\s+is\s+leading\s+a\s+unit\b",
    re.IGNORECASE,
)
_TARGET_RE = re.compile(
    r"\b(?:select\s+)?(?:one\s+)?(?P<allegiance>friendly|enemy)\s+"
    r"(?:(?P<keyword>[A-Z][A-Z0-9_'-]*(?:\s+[A-Z0-9_'-]+){0,5})\s+)?"
    r"(?:model|unit)\b",
    re.IGNORECASE,
)
_THIS_UNIT_RE = re.compile(r"\bthis\s+unit\b", re.IGNORECASE)
_BEARER_APOSTROPHE_RE = r"(?:'|\u2019)?"
_BEARERS_UNIT_RE = re.compile(
    rf"\b(?:models\s+in\s+)?(?:the\s+)?bearer{_BEARER_APOSTROPHE_RE}s\s+unit\b|"
    rf"\bmade\s+for\s+(?:the\s+)?bearer{_BEARER_APOSTROPHE_RE}s\s+unit\b",
    re.IGNORECASE,
)
_BEARER_MODEL_RE = re.compile(
    r"\b(?:the\s+)?bearer\b|\bmade\s+for\s+(?:the\s+)?bearer\b",
    re.IGNORECASE,
)
_THAT_UNIT_RE = re.compile(r"\b(?:that|selected|target)\s+unit\b", re.IGNORECASE)
_PLAYER_RE = re.compile(r"\b(?:you|that\s+player|the\s+player)\b", re.IGNORECASE)
_RESOURCE_TARGET_RE = re.compile(
    r"\b(?:gain|score|add|spend|lose|remove|refund)\s+\d+\s*"
    r"(?:CP|VP|Command Points?|Command point|Victory Points?)\b",
    re.IGNORECASE,
)
_HAS_KEYWORD_RE = re.compile(
    r"\b(?:has|have|with)\s+the\s+(?P<keyword>[A-Z][A-Z0-9_'-]*(?:\s+[A-Z0-9_'-]+){0,5})"
    r"\s+keyword\b"
)
_KEYWORD_UNIT_RE = re.compile(
    r"\b(?P<keyword>[A-Z][A-Z0-9_'-]*(?:\s+[A-Z0-9_'-]+){0,5})\s+(?:model|unit)\b"
)
_ADD_ROLL_RE = re.compile(
    rf"\b(?P<verb>add|subtract)\s+(?P<value>\d+)\s+(?:to|from)\s+"
    rf"(?:the\s+)?(?P<roll>{_ROLL_TYPES})\s+rolls?\b",
    re.IGNORECASE,
)
_SIGNED_ROLL_RE = re.compile(
    rf"(?<![A-Za-z0-9_])(?P<sign>[+-])(?P<value>\d+)\s+to\s+"
    rf"(?:the\s+)?(?P<roll>{_ROLL_TYPES})\s+rolls?\b",
    re.IGNORECASE,
)
_REROLL_ROLL_LIST_RE = re.compile(
    rf"\b(?:(?:you\s+)?can\s+)?(?:re-roll|reroll)\s+"
    rf"(?P<rolls>(?:{_ROLL_TYPES})(?:\s*,\s*|\s+and\s+)"
    rf"(?:{_ROLL_TYPES})(?:(?:\s*,\s*|\s+and\s+)(?:{_ROLL_TYPES}))*)\s+rolls?\b"
    r"(?:\s+made\s+for\s+(?:this|that|selected|target)\s+unit)?",
    re.IGNORECASE,
)
_REROLL_RE = re.compile(
    rf"\b(?:(?:you\s+)?can\s+)?(?:re-roll|reroll)\s+(?P<roll>{_ROLL_TYPES})\s+rolls?\b"
    r"(?:\s+made\s+for\s+(?:this|that|selected|target)\s+unit)?",
    re.IGNORECASE,
)
_CHARACTERISTIC_NAMES = (
    "Armor Penetration|AP|Attacks|Ballistic Skill|BS|Damage|Detection Range|Invulnerable Save|"
    "Leadership|Move|Movement|Objective Control|OC|Range|Save|Strength|Toughness|Weapon Skill|"
    "Wounds|WS"
)
_CHARACTERISTIC_RE = re.compile(
    rf"\b(?P<verb>add|subtract)\s+(?P<value>\d+)(?:\")?\s+(?:to|from)\s+"
    rf"(?:the\s+)?(?P<characteristic>{_CHARACTERISTIC_NAMES})\s+characteristic\b",
    re.IGNORECASE,
)
_SET_CHARACTERISTIC_RE = re.compile(
    rf"\b(?:have|has)\s+a\s+(?P<characteristic>{_CHARACTERISTIC_NAMES})\s+"
    r"characteristic\s+of\s+(?P<value>[A-Za-z0-9+/-]+)(?=[\s.,;)]|$)",
    re.IGNORECASE,
)
_ADDITIONAL_MOVE_RE = re.compile(
    r"\bmove\s+an\s+additional\s+(?P<distance>\d+)(?:\")?\b",
    re.IGNORECASE,
)
_CP_RE = re.compile(
    r"\b(?P<verb>gain|add|refund|spend|lose|remove)\s+(?P<value>\d+)\s*"
    r"(?:CP|Command Points?|Command point)\b",
    re.IGNORECASE,
)
_VP_RE = re.compile(
    r"\b(?P<verb>score|gain|add)\s+(?P<value>\d+)\s*(?:VP|Victory Points?)\b",
    re.IGNORECASE,
)
_UNTIL_RE = re.compile(
    r"\buntil\s+(?:the\s+)?end\s+of\s+(?:the\s+|this\s+|that\s+|your\s+|opponent's\s+)?"
    r"(?P<endpoint>phase|turn|battle round|battle)\b",
    re.IGNORECASE,
)
_GRANT_ABILITY_RE = re.compile(
    r"\b(?:gains?|have|has)\s+(?P<ability>[A-Z][A-Za-z0-9 -]*(?:\s+\d+)?)\s+until\b",
    re.IGNORECASE,
)
_CHARGE_ELIGIBILITY_AFTER_MOVE_RE = re.compile(
    r"\b(?:(?:this|that|selected|target)\s+unit\s+)?"
    r"(?:is\s+)?eligible\s+to\s+declare\s+a\s+charge\s+in\s+a\s+turn\s+"
    r"in\s+which\s+(?:it|this\s+unit|that\s+unit|the\s+unit)\s+"
    r"(?P<movement>Advanced|Fell\s+Back)\b",
    re.IGNORECASE,
)
_FEEL_NO_PAIN_ABILITY_RE = re.compile(
    r"\b(?:gains?|have|has)\s+(?:the\s+)?Feel\s+No\s+Pain\s+"
    r"(?P<threshold>[2-6])\+\s+ability"
    r"(?:\s+against\s+(?P<attack_condition>Psychic\s+Attacks?))?\b",
    re.IGNORECASE,
)
_WEAPON_KEYWORD_PATTERN = "|".join(
    re.escape(keyword)
    for keyword in sorted(canonical_weapon_keyword_tokens(), key=len, reverse=True)
)
_WEAPON_ABILITY_RE = re.compile(
    rf"\b(?:ranged\s+|melee\s+)?weapons?.{{0,100}}\b(?:gain|gains|have|has)\s+"
    rf"(?:the\s+)?\[?(?P<ability>{_WEAPON_KEYWORD_PATTERN})\]?"
    rf"(?:\s+ability)?\b",
    re.IGNORECASE,
)
_NAMED_WEAPON_ABILITY_RE = re.compile(
    rf"\b(?P<weapon_name>[A-Z][A-Za-z0-9 '\u2019:-]+?)\s+equipped\s+by\s+models\s+"
    rf"in\s+(?:that|this|the\s+selected)\s+unit\s+(?:gain|gains|have|has)\s+"
    rf"(?:the\s+)?\[?(?P<ability>{_WEAPON_KEYWORD_PATTERN})\]?"
    rf"(?:\s+ability)?\b",
    re.IGNORECASE,
)
_PLACEMENT_PERMISSION_RE = re.compile(r"\bcan\s+be\s+set\s+up\b", re.IGNORECASE)
_PLACEMENT_RESTRICTION_RE = re.compile(
    r"\b(?:cannot|can't|can\s+only)\s+be\s+set\s+up\b",
    re.IGNORECASE,
)
_REMOVE_TO_STRATEGIC_RESERVES_RE = re.compile(
    r"\b(?:you\s+can\s+)?remove\s+it\s+from\s+the\s+battlefield\s+and\s+"
    r"place\s+it\s+into\s+Strategic\s+Reserves\b",
    re.IGNORECASE,
)
_DISTANCE_RELATION_RE = re.compile(
    r"\b(?:(?P<subject>this\s+unit|this\s+model|that\s+unit|selected\s+unit|"
    r"target\s+unit)\s+is\s+)?"
    r"(?P<negated>not\s+)?"
    r"(?P<predicate>wholly\s+within|within)\s+"
    r"(?P<range>Engagement\s+Range|Objective\s+Marker\s+Range|\d+(?:\.\d+)?\")\s+"
    r"of\s+"
    r"(?:(?P<quantity>one\s+or\s+more|any|a|an)\s+)?"
    r"(?:(?P<allegiance>enemy|friendly)\s+)?"
    r"(?:(?P<object_reference>this|that|selected|target)\s+)?"
    r"(?:(?P<keyword>[A-Z][A-Z0-9_'-]*(?:\s+[A-Z0-9_'-]+){0,5})\s+)?"
    r"(?P<object_kind>units?|models?|objective\s+markers?)\b",
    re.IGNORECASE,
)
_RESIDUAL_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_+'-]*")
_RESIDUAL_CONNECTOR_TOKENS = frozenset(
    {
        "a",
        "an",
        "and",
        "any",
        "are",
        "away",
        "be",
        "by",
        "can",
        "cannot",
        "each",
        "enemies",
        "enemy",
        "equipped",
        "every",
        "for",
        "friendly",
        "from",
        "has",
        "have",
        "if",
        "in",
        "into",
        "is",
        "its",
        "melee",
        "model",
        "models",
        "of",
        "on",
        "one",
        "only",
        "opponent",
        "opponents",
        "or",
        "phase",
        "player",
        "ranged",
        "select",
        "selected",
        "that",
        "the",
        "their",
        "these",
        "this",
        "those",
        "to",
        "towards",
        "turn",
        "unit",
        "units",
        "weapon",
        "weapons",
        "when",
        "while",
        "with",
        "within",
        "without",
        "your",
    }
)

_CHARACTERISTIC_BY_LABEL = {
    "armor penetration": Characteristic.ARMOR_PENETRATION,
    "ap": Characteristic.ARMOR_PENETRATION,
    "attacks": Characteristic.ATTACKS,
    "ballistic skill": Characteristic.BALLISTIC_SKILL,
    "bs": Characteristic.BALLISTIC_SKILL,
    "damage": Characteristic.DAMAGE,
    "detection range": Characteristic.DETECTION_RANGE,
    "invulnerable save": Characteristic.INVULNERABLE_SAVE,
    "leadership": Characteristic.LEADERSHIP,
    "move": Characteristic.MOVEMENT,
    "movement": Characteristic.MOVEMENT,
    "objective control": Characteristic.OBJECTIVE_CONTROL,
    "oc": Characteristic.OBJECTIVE_CONTROL,
    "range": Characteristic.RANGE,
    "save": Characteristic.SAVE,
    "strength": Characteristic.STRENGTH,
    "toughness": Characteristic.TOUGHNESS,
    "weapon skill": Characteristic.WEAPON_SKILL,
    "wounds": Characteristic.WOUNDS,
    "ws": Characteristic.WEAPON_SKILL,
}
_SOURCE_KEYWORD_SEQUENCE_PARTS = (
    datasheet_keyword_lexicon_2026_06_14.canonical_datasheet_keyword_sequence_parts()
)


@dataclass(frozen=True, slots=True)
class _ClauseText:
    span: TextSpan

    @property
    def text(self) -> str:
        return self.span.text

    @property
    def start(self) -> int:
        return self.span.start


def parse_rule_ir(
    *,
    source_id: str,
    parsed_text: ParsedRuleText,
    rule_id: str | None = None,
) -> RuleIR:
    if type(source_id) is not str or not source_id.strip():
        raise RuleIRError("Rule parser source_id must be a non-empty string.")
    if type(parsed_text) is not ParsedRuleText:
        raise RuleIRError("Rule parser parsed_text must be ParsedRuleText.")
    compiled_clauses = tuple(
        _compile_clause(
            source_id=source_id.strip(),
            clause_index=index,
            clause_text=clause_text,
            parsed_text=parsed_text,
        )
        for index, clause_text in enumerate(
            _split_clause_text(parsed_text.normalized_text), start=1
        )
    )
    return RuleIR(
        rule_id=source_id.strip() if rule_id is None else rule_id,
        source_id=source_id.strip(),
        normalized_text=parsed_text.normalized_text,
        parser_version=RULE_PARSER_VERSION,
        clauses=compiled_clauses,
        diagnostics=tuple(
            diagnostic for clause in compiled_clauses for diagnostic in clause.diagnostics
        ),
    )


def _split_clause_text(normalized_text: str) -> tuple[_ClauseText, ...]:
    clauses: list[_ClauseText] = []
    start = 0
    for index, character in enumerate(normalized_text):
        if character not in {"\n", ";"}:
            continue
        _append_clause_span(
            clauses=clauses, normalized_text=normalized_text, start=start, end=index
        )
        start = index + 1
    _append_clause_span(
        clauses=clauses,
        normalized_text=normalized_text,
        start=start,
        end=len(normalized_text),
    )
    if not clauses:
        full_span = TextSpan(text=normalized_text, start=0, end=len(normalized_text))
        return (_ClauseText(span=full_span),)
    return tuple(clauses)


def _append_clause_span(
    *,
    clauses: list[_ClauseText],
    normalized_text: str,
    start: int,
    end: int,
) -> None:
    while start < end and normalized_text[start].isspace():
        start += 1
    while end > start and normalized_text[end - 1].isspace():
        end -= 1
    if start == end:
        return
    clauses.append(
        _ClauseText(span=TextSpan(text=normalized_text[start:end], start=start, end=end))
    )


def _compile_clause(
    *,
    source_id: str,
    clause_index: int,
    clause_text: _ClauseText,
    parsed_text: ParsedRuleText,
) -> RuleClause:
    trigger = _parse_trigger(clause_text)
    conditions = _dedupe_conditions(
        (
            *_parse_aura_conditions(clause_text),
            *_parse_leading_unit_conditions(clause_text),
            *_parse_frequency_conditions(clause_text),
            *_parse_keyword_conditions(clause_text),
            *_parse_distance_conditions(clause_text, parsed_text),
        )
    )
    target = _parse_target(clause_text)
    duration = _parse_duration(clause_text)
    effects = _dedupe_effects(
        (
            *_parse_dice_roll_modifier_effects(clause_text),
            *_parse_reroll_effects(clause_text),
            *_parse_characteristic_effects(clause_text),
            *_parse_resource_effects(clause_text),
            *_parse_grant_ability_effects(clause_text),
            *_parse_weapon_ability_effects(clause_text),
            *_parse_placement_effects(clause_text),
        )
    )
    template_id = _template_id_for_clause(
        trigger=trigger,
        conditions=conditions,
        target=target,
        effects=effects,
    )
    clause_id = f"{source_id}:clause:{clause_index:03d}"
    residual_diagnostic = _residual_diagnostic(
        clause_text=clause_text,
        trigger=trigger,
        conditions=conditions,
        target=target,
        effects=effects,
        duration=duration,
    )
    if trigger is None and not conditions and target is None and not effects and duration is None:
        diagnostic = RuleParseDiagnostic(
            reason=RuleUnsupportedReason.UNSUPPORTED_LANGUAGE,
            message="Rule clause is not represented by Phase 17C language templates.",
            source_span=clause_text.span,
        )
        return RuleClause(
            clause_id=clause_id,
            source_span=clause_text.span,
            unsupported_reason=RuleUnsupportedReason.UNSUPPORTED_LANGUAGE,
            diagnostics=(diagnostic,),
            template_id=None,
        )
    diagnostics = () if residual_diagnostic is None else (residual_diagnostic,)
    return RuleClause(
        clause_id=clause_id,
        source_span=clause_text.span,
        trigger=trigger,
        conditions=conditions,
        target=target,
        effects=effects,
        duration=duration,
        unsupported_reason=(
            None if residual_diagnostic is None else RuleUnsupportedReason.UNSUPPORTED_LANGUAGE
        ),
        diagnostics=diagnostics,
        template_id=template_id,
    )


def _parse_trigger(clause_text: _ClauseText) -> RuleTrigger | None:
    for match in _START_END_PHASE_RE.finditer(clause_text.text):
        return RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs(
                (
                    ("edge", _lower_group(match, "edge")),
                    ("phase", _lower_group(match, "phase")),
                    ("owner", _owner_token(match.group("owner"))),
                )
            ),
        )
    for match in _START_END_TURN_RE.finditer(clause_text.text):
        edge = _lower_group(match, "edge")
        return RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs(
                (
                    ("edge", edge),
                    ("phase", "turn"),
                    ("owner", _owner_token(match.group("owner"))),
                    ("timing_window", f"turn_{edge}"),
                )
            ),
        )
    for match in _IN_PHASE_RE.finditer(clause_text.text):
        return RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs(
                (
                    ("edge", "during"),
                    ("phase", _lower_group(match, "phase")),
                    ("owner", _owner_token(match.group("owner"))),
                )
            ),
        )
    for match in _IN_TURN_RE.finditer(clause_text.text):
        return RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs(
                (
                    ("edge", "during"),
                    ("phase", "turn"),
                    ("owner", _owner_token(match.group("owner"))),
                    ("timing_window", "turn_during"),
                )
            ),
        )
    unit_destroyed_match = _DESTROYED_UNIT_RE.search(clause_text.text)
    if unit_destroyed_match is not None:
        return RuleTrigger(
            kind=RuleTriggerKind.UNIT_DESTROYED,
            source_span=_span_from_match(clause_text, unit_destroyed_match),
        )
    model_destroyed_match = _DESTROYED_MODEL_RE.search(clause_text.text)
    if model_destroyed_match is not None:
        return RuleTrigger(
            kind=RuleTriggerKind.MODEL_DESTROYED,
            source_span=_span_from_match(clause_text, model_destroyed_match),
        )
    charge_move_end_match = _CHARGE_MOVE_END_RE.search(clause_text.text)
    if charge_move_end_match is not None:
        return RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span_from_match(clause_text, charge_move_end_match),
            parameters=parameters_from_pairs(
                (
                    ("edge", "after"),
                    ("phase", "charge"),
                    ("timing_window", "charge_move_end"),
                    ("subject", _lower_group(charge_move_end_match, "subject")),
                )
            ),
        )
    dice_trigger_match = _DICE_TRIGGER_RE.search(clause_text.text)
    if dice_trigger_match is not None:
        return RuleTrigger(
            kind=RuleTriggerKind.DICE_ROLL,
            source_span=_span_from_match(clause_text, dice_trigger_match),
            parameters=parameters_from_pairs(
                (("roll_type", _roll_type(dice_trigger_match.group("roll"))),)
            ),
        )
    setup_match = _SETUP_RE.search(clause_text.text)
    if setup_match is not None:
        return RuleTrigger(
            kind=RuleTriggerKind.SETUP, source_span=_span_from_match(clause_text, setup_match)
        )
    return None


def _parse_aura_conditions(clause_text: _ClauseText) -> tuple[RuleCondition, ...]:
    match = _AURA_RE.search(clause_text.text)
    if match is None:
        return ()
    return (
        RuleCondition(
            kind=RuleConditionKind.AURA,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs((("source", "aura"),)),
        ),
    )


def _parse_leading_unit_conditions(clause_text: _ClauseText) -> tuple[RuleCondition, ...]:
    match = _LEADING_UNIT_RE.search(clause_text.text)
    if match is None:
        return ()
    return (
        RuleCondition(
            kind=RuleConditionKind.TARGET_CONSTRAINT,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs((("relationship", "this_model_leading_unit"),)),
        ),
    )


def _parse_frequency_conditions(clause_text: _ClauseText) -> tuple[RuleCondition, ...]:
    conditions: list[RuleCondition] = []
    for match in _ONCE_PER_RE.finditer(clause_text.text):
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.FREQUENCY_LIMIT,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs((("scope", _lower_group(match, "scope")),)),
            )
        )
    return tuple(conditions)


def _parse_keyword_conditions(clause_text: _ClauseText) -> tuple[RuleCondition, ...]:
    conditions: list[RuleCondition] = []
    target_match_ranges: list[tuple[int, int]] = []
    for match in _TARGET_RE.finditer(clause_text.text):
        keyword_text = match.group("keyword")
        if keyword_text is None:
            continue
        target_match_ranges.append((match.start(), match.end()))
        conditions.extend(_keyword_gate_conditions_from_match(clause_text=clause_text, match=match))
    for pattern in (_HAS_KEYWORD_RE, _KEYWORD_UNIT_RE):
        for match in pattern.finditer(clause_text.text):
            if pattern is _KEYWORD_UNIT_RE and _match_inside_ranges(match, target_match_ranges):
                continue
            conditions.extend(
                _keyword_gate_conditions_from_match(clause_text=clause_text, match=match)
            )
    return tuple(conditions)


def _keyword_gate_conditions_from_match(
    *,
    clause_text: _ClauseText,
    match: re.Match[str],
) -> tuple[RuleCondition, ...]:
    return tuple(
        RuleCondition(
            kind=RuleConditionKind.KEYWORD_GATE,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs((("required_keyword", keyword),)),
        )
        for keyword in _keyword_sequence_tokens(match.group("keyword"))
    )


def _parse_distance_conditions(
    clause_text: _ClauseText,
    parsed_text: ParsedRuleText,
) -> tuple[RuleCondition, ...]:
    conditions: list[RuleCondition] = []
    for token in parsed_text.distance_predicates:
        if not _token_inside_clause(token, clause_text):
            continue
        relation_match = _distance_relation_match_for_token(clause_text=clause_text, token=token)
        pairs: tuple[tuple[str, RuleParameterValue], ...] = (
            ("predicate", token.kind.value),
            ("distance_inches", token.distance_inches),
            ("qualifier", token.qualifier),
            *_distance_relation_parameter_pairs(relation_match),
        )
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.DISTANCE_PREDICATE,
                source_span=(
                    token.span
                    if relation_match is None
                    else _span_from_match(clause_text, relation_match)
                ),
                parameters=parameters_from_pairs(pairs),
            )
        )
    return tuple(conditions)


def _parse_target(clause_text: _ClauseText) -> RuleTargetSpec | None:
    if _AURA_RE.search(clause_text.text) is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.AURA_UNITS,
            source_span=clause_text.span,
            parameters=parameters_from_pairs(_aura_target_parameter_pairs(clause_text)),
        )
    match = _TARGET_RE.search(clause_text.text)
    if match is not None:
        allegiance = _lower_group(match, "allegiance")
        target_kind = (
            RuleTargetKind.FRIENDLY_UNIT if allegiance == "friendly" else RuleTargetKind.ENEMY_UNIT
        )
        pairs: list[tuple[str, RuleParameterValue]] = [("allegiance", allegiance)]
        keyword_text = match.group("keyword")
        if keyword_text is not None:
            pairs.extend(_keyword_sequence_parameter_pairs(keyword_text))
        return RuleTargetSpec(
            kind=target_kind,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs(tuple(pairs)),
        )
    match = _THIS_UNIT_RE.search(clause_text.text)
    if match is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.THIS_UNIT, source_span=_span_from_match(clause_text, match)
        )
    match = _BEARERS_UNIT_RE.search(clause_text.text)
    if match is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.THIS_UNIT, source_span=_span_from_match(clause_text, match)
        )
    match = _BEARER_MODEL_RE.search(clause_text.text)
    if match is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.THIS_MODEL, source_span=_span_from_match(clause_text, match)
        )
    match = _THAT_UNIT_RE.search(clause_text.text)
    if match is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.SELECTED_UNIT,
            source_span=_span_from_match(clause_text, match),
        )
    match = _PLAYER_RE.search(clause_text.text)
    if match is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.PLAYER, source_span=_span_from_match(clause_text, match)
        )
    match = _RESOURCE_TARGET_RE.search(clause_text.text)
    if match is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.PLAYER, source_span=_span_from_match(clause_text, match)
        )
    return None


def _aura_target_parameter_pairs(
    clause_text: _ClauseText,
) -> tuple[tuple[str, RuleParameterValue], ...]:
    pairs: list[tuple[str, RuleParameterValue]] = [("eligible_target", "aura_units")]
    match = _TARGET_RE.search(clause_text.text)
    if match is None:
        pairs.append(("allegiance", "any"))
        return tuple(pairs)
    pairs.append(("allegiance", _lower_group(match, "allegiance")))
    keyword_text = match.group("keyword")
    if keyword_text is not None:
        pairs.extend(_keyword_sequence_parameter_pairs(keyword_text))
    return tuple(pairs)


def _parse_duration(clause_text: _ClauseText) -> RuleDuration | None:
    match = _UNTIL_RE.search(clause_text.text)
    if match is not None:
        return RuleDuration(
            kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            source_span=_span_from_match(clause_text, match),
            parameters=parameters_from_pairs((("endpoint", _lower_group(match, "endpoint")),)),
        )
    if _AURA_RE.search(clause_text.text) is not None and "while" in clause_text.text.lower():
        return RuleDuration(
            kind=RuleDurationKind.WHILE_CONDITION_TRUE,
            source_span=clause_text.span,
            parameters=parameters_from_pairs((("condition", "aura"),)),
        )
    return None


def _parse_dice_roll_modifier_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _ADD_ROLL_RE.finditer(clause_text.text):
        value = int(match.group("value"))
        delta = value if _lower_group(match, "verb") == "add" else -value
        effects.append(_dice_modifier_effect(clause_text=clause_text, match=match, delta=delta))
    for match in _SIGNED_ROLL_RE.finditer(clause_text.text):
        value = int(match.group("value"))
        delta = value if match.group("sign") == "+" else -value
        effects.append(_dice_modifier_effect(clause_text=clause_text, match=match, delta=delta))
    return tuple(effects)


def _dice_modifier_effect(
    *,
    clause_text: _ClauseText,
    match: re.Match[str],
    delta: int,
) -> RuleEffectSpec:
    return RuleEffectSpec(
        kind=RuleEffectKind.MODIFY_DICE_ROLL,
        source_span=_span_from_match(clause_text, match),
        parameters=parameters_from_pairs(
            (
                ("roll_type", _roll_type(match.group("roll"))),
                ("delta", delta),
            )
        ),
    )


def _parse_reroll_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    list_spans: list[tuple[int, int]] = []
    for match in _REROLL_ROLL_LIST_RE.finditer(clause_text.text):
        list_spans.append((match.start(), match.end()))
        for roll in _roll_list_values(match.group("rolls")):
            effects.append(
                RuleEffectSpec(
                    kind=RuleEffectKind.REROLL_PERMISSION,
                    source_span=_span_from_match(clause_text, match),
                    parameters=parameters_from_pairs((("roll_type", _roll_type(roll)),)),
                )
            )
    for match in _REROLL_RE.finditer(clause_text.text):
        if _match_is_within_any_span(match=match, spans=tuple(list_spans)):
            continue
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.REROLL_PERMISSION,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs((("roll_type", _roll_type(match.group("roll"))),)),
            )
        )
    return tuple(effects)


def _roll_list_values(value: str) -> tuple[str, ...]:
    rolls: list[str] = []
    for raw_roll in re.split(r"\s*,\s*|\s+and\s+", value.strip(), flags=re.IGNORECASE):
        roll = raw_roll.strip()
        if roll:
            rolls.append(roll)
    return tuple(rolls)


def _match_is_within_any_span(
    *,
    match: re.Match[str],
    spans: tuple[tuple[int, int], ...],
) -> bool:
    return any(start <= match.start() and match.end() <= end for start, end in spans)


def _parse_characteristic_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _CHARACTERISTIC_RE.finditer(clause_text.text):
        characteristic = _characteristic_from_label(match.group("characteristic"))
        value = int(match.group("value"))
        delta = value if _lower_group(match, "verb") == "add" else -value
        effect_kind = (
            RuleEffectKind.MODIFY_MOVE_DISTANCE
            if characteristic is Characteristic.MOVEMENT
            else RuleEffectKind.MODIFY_CHARACTERISTIC
        )
        effects.append(
            RuleEffectSpec(
                kind=effect_kind,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (
                        ("characteristic", characteristic.value),
                        ("delta", delta),
                    )
                ),
            )
        )
    for match in _SET_CHARACTERISTIC_RE.finditer(clause_text.text):
        characteristic = _characteristic_from_label(match.group("characteristic"))
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.SET_CHARACTERISTIC,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (
                        ("characteristic", characteristic.value),
                        ("value", match.group("value")),
                    )
                ),
            )
        )
    for match in _ADDITIONAL_MOVE_RE.finditer(clause_text.text):
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.MODIFY_MOVE_DISTANCE,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs((("delta_inches", int(match.group("distance"))),)),
            )
        )
    return tuple(effects)


def _parse_resource_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _CP_RE.finditer(clause_text.text):
        verb = _lower_group(match, "verb")
        value = int(match.group("value"))
        delta = -value if verb in {"spend", "lose", "remove"} else value
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.MODIFY_COMMAND_POINTS,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs((("delta", delta),)),
            )
        )
    for match in _VP_RE.finditer(clause_text.text):
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.ADD_VICTORY_POINTS,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs((("delta", int(match.group("value"))),)),
            )
        )
    return tuple(effects)


def _parse_grant_ability_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _CHARGE_ELIGIBILITY_AFTER_MOVE_RE.finditer(clause_text.text):
        movement = " ".join(match.group("movement").lower().split())
        ability = (
            "can_fall_back_and_charge" if movement == "fell back" else "can_advance_and_charge"
        )
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.GRANT_ABILITY,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs((("ability", ability),)),
            )
        )
    for match in _FEEL_NO_PAIN_ABILITY_RE.finditer(clause_text.text):
        parameter_pairs: list[tuple[str, RuleParameterValue]] = [
            ("ability", "Feel No Pain"),
            ("threshold", int(match.group("threshold"))),
        ]
        attack_condition = match.group("attack_condition")
        if attack_condition is not None:
            parameter_pairs.append(
                ("attack_condition", _feel_no_pain_attack_condition_token(attack_condition))
            )
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.GRANT_ABILITY,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(tuple(parameter_pairs)),
            )
        )
    for match in _GRANT_ABILITY_RE.finditer(clause_text.text):
        if _span_matches_existing_effect(
            clause_text=clause_text,
            match=match,
            effects=tuple(effects),
        ):
            continue
        ability = _ability_token(match.group("ability"))
        if _is_weapon_keyword(ability):
            continue
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.GRANT_ABILITY,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs((("ability", ability),)),
            )
        )
    return tuple(effects)


def _parse_weapon_ability_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _NAMED_WEAPON_ABILITY_RE.finditer(clause_text.text):
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.GRANT_WEAPON_ABILITY,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (
                        ("weapon_ability", _ability_token(match.group("ability"))),
                        ("weapon_name", _weapon_name_token(match.group("weapon_name"))),
                        ("target_scope", "models_in_selected_unit"),
                    )
                ),
            )
        )
    for match in _WEAPON_ABILITY_RE.finditer(clause_text.text):
        if _span_matches_existing_effect(
            clause_text=clause_text,
            match=match,
            effects=tuple(effects),
        ):
            continue
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.GRANT_WEAPON_ABILITY,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (("weapon_ability", _ability_token(match.group("ability"))),)
                ),
            )
        )
    return tuple(effects)


def _parse_placement_effects(clause_text: _ClauseText) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _REMOVE_TO_STRATEGIC_RESERVES_RE.finditer(clause_text.text):
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.PLACEMENT_PERMISSION,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs(
                    (
                        ("allowed", True),
                        ("optional", True),
                        ("placement_kind", "turn_end_reserves"),
                        ("reserve_kind", "strategic_reserves"),
                        ("action", "remove_from_battlefield_to_strategic_reserves"),
                    )
                ),
            )
        )
    for match in _PLACEMENT_RESTRICTION_RE.finditer(clause_text.text):
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.PLACEMENT_RESTRICTION,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs((("allowed", False),)),
            )
        )
    for match in _PLACEMENT_PERMISSION_RE.finditer(clause_text.text):
        if _span_matches_existing_effect(
            clause_text=clause_text, match=match, effects=tuple(effects)
        ):
            continue
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.PLACEMENT_PERMISSION,
                source_span=_span_from_match(clause_text, match),
                parameters=parameters_from_pairs((("allowed", True),)),
            )
        )
    return tuple(effects)


def _residual_diagnostic(
    *,
    clause_text: _ClauseText,
    trigger: RuleTrigger | None,
    conditions: tuple[RuleCondition, ...],
    target: RuleTargetSpec | None,
    effects: tuple[RuleEffectSpec, ...],
    duration: RuleDuration | None,
) -> RuleParseDiagnostic | None:
    residual_span = _meaningful_residual_span(
        clause_text=clause_text,
        recognized_spans=_recognized_component_spans(
            trigger=trigger,
            conditions=conditions,
            target=target,
            effects=effects,
            duration=duration,
        ),
    )
    if residual_span is None:
        return None
    return RuleParseDiagnostic(
        reason=RuleUnsupportedReason.UNSUPPORTED_LANGUAGE,
        message="Rule clause contains unrepresented residual language.",
        source_span=residual_span,
    )


def _recognized_component_spans(
    *,
    trigger: RuleTrigger | None,
    conditions: tuple[RuleCondition, ...],
    target: RuleTargetSpec | None,
    effects: tuple[RuleEffectSpec, ...],
    duration: RuleDuration | None,
) -> tuple[TextSpan, ...]:
    spans: list[TextSpan] = []
    if trigger is not None:
        spans.append(trigger.source_span)
    spans.extend(condition.source_span for condition in conditions)
    if target is not None:
        spans.append(target.source_span)
    spans.extend(effect.source_span for effect in effects)
    if duration is not None:
        spans.append(duration.source_span)
    return tuple(spans)


def _meaningful_residual_span(
    *,
    clause_text: _ClauseText,
    recognized_spans: tuple[TextSpan, ...],
) -> TextSpan | None:
    for start, end in _residual_ranges(
        clause_start=clause_text.span.start,
        clause_end=clause_text.span.end,
        recognized_spans=recognized_spans,
    ):
        residual_text = clause_text.span.text[
            start - clause_text.span.start : end - clause_text.span.start
        ]
        token_matches = tuple(_RESIDUAL_TOKEN_RE.finditer(residual_text))
        meaningful_matches = tuple(
            match for match in token_matches if _is_meaningful_residual_token(match.group(0))
        )
        if not meaningful_matches:
            continue
        span_start = start + meaningful_matches[0].start()
        span_end = start + meaningful_matches[-1].end()
        return TextSpan(
            text=clause_text.span.text[
                span_start - clause_text.span.start : span_end - clause_text.span.start
            ],
            start=span_start,
            end=span_end,
        )
    return None


def _residual_ranges(
    *,
    clause_start: int,
    clause_end: int,
    recognized_spans: tuple[TextSpan, ...],
) -> tuple[tuple[int, int], ...]:
    merged_spans = _merged_spans(
        clause_start=clause_start,
        clause_end=clause_end,
        recognized_spans=recognized_spans,
    )
    ranges: list[tuple[int, int]] = []
    cursor = clause_start
    for start, end in merged_spans:
        if cursor < start:
            ranges.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < clause_end:
        ranges.append((cursor, clause_end))
    return tuple(ranges)


def _merged_spans(
    *,
    clause_start: int,
    clause_end: int,
    recognized_spans: tuple[TextSpan, ...],
) -> tuple[tuple[int, int], ...]:
    clipped = tuple(
        sorted(
            (
                (max(clause_start, span.start), min(clause_end, span.end))
                for span in recognized_spans
                if span.start < clause_end and clause_start < span.end
            ),
            key=lambda value: (value[0], value[1]),
        )
    )
    merged: list[tuple[int, int]] = []
    for start, end in clipped:
        if start >= end:
            continue
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
            continue
        previous_start, previous_end = merged[-1]
        merged[-1] = (previous_start, max(previous_end, end))
    return tuple(merged)


def _is_meaningful_residual_token(token: str) -> bool:
    normalized = token.lower().strip("'")
    if not normalized or normalized in _RESIDUAL_CONNECTOR_TOKENS:
        return False
    return not normalized.isdigit()


def _template_id_for_clause(
    *,
    trigger: RuleTrigger | None,
    conditions: tuple[RuleCondition, ...],
    target: RuleTargetSpec | None,
    effects: tuple[RuleEffectSpec, ...],
) -> str | None:
    candidates: list[str] = []
    if any(condition.kind is RuleConditionKind.AURA for condition in conditions):
        candidates.append(AURA_TEMPLATE_ID)
    for effect in effects:
        if effect.kind is RuleEffectKind.GRANT_WEAPON_ABILITY:
            candidates.append(WEAPON_ABILITY_GRANT_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.GRANT_ABILITY:
            candidates.append(GRANT_ABILITY_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.MODIFY_DICE_ROLL:
            candidates.append(DICE_ROLL_MODIFIER_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.REROLL_PERMISSION:
            candidates.append(REROLL_PERMISSION_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.MODIFY_CHARACTERISTIC:
            candidates.append(CHARACTERISTIC_MODIFIER_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.SET_CHARACTERISTIC:
            candidates.append(CHARACTERISTIC_SET_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.MODIFY_MOVE_DISTANCE:
            candidates.append(MOVEMENT_DISTANCE_TEMPLATE_ID)
        elif effect.kind in {
            RuleEffectKind.MODIFY_COMMAND_POINTS,
            RuleEffectKind.ADD_VICTORY_POINTS,
        }:
            candidates.append(RESOURCE_MODIFIER_TEMPLATE_ID)
        elif effect.kind in {
            RuleEffectKind.PLACEMENT_PERMISSION,
            RuleEffectKind.PLACEMENT_RESTRICTION,
        }:
            candidates.append(PLACEMENT_TEMPLATE_ID)
    if target is not None:
        candidates.append(SELECTED_TARGET_TEMPLATE_ID)
    for condition in conditions:
        if condition.kind is RuleConditionKind.KEYWORD_GATE:
            candidates.append(KEYWORD_GATE_TEMPLATE_ID)
        elif condition.kind is RuleConditionKind.DISTANCE_PREDICATE:
            candidates.append(DISTANCE_PREDICATE_TEMPLATE_ID)
    if trigger is not None:
        candidates.append(TIMING_WINDOW_TEMPLATE_ID)
    if not candidates:
        return None
    template_id = candidates[0]
    rule_template_by_id(template_id)
    return template_id


def _dedupe_conditions(conditions: tuple[RuleCondition, ...]) -> tuple[RuleCondition, ...]:
    deduped = {json_key(condition): condition for condition in conditions}
    return tuple(
        deduped[key]
        for key in sorted(
            deduped,
            key=lambda value: (
                deduped[value].source_span.start,
                deduped[value].source_span.end,
                deduped[value].kind.value,
                value,
            ),
        )
    )


def _dedupe_effects(effects: tuple[RuleEffectSpec, ...]) -> tuple[RuleEffectSpec, ...]:
    deduped = {json_key(effect): effect for effect in effects}
    return tuple(
        deduped[key]
        for key in sorted(
            deduped,
            key=lambda value: (
                deduped[value].source_span.start,
                deduped[value].source_span.end,
                deduped[value].kind.value,
                value,
            ),
        )
    )


def json_key(value: RuleCondition | RuleEffectSpec) -> str:
    if type(value) is RuleCondition or type(value) is RuleEffectSpec:
        payload = value.to_payload()
    else:
        raise RuleIRError("Unsupported rule parser dedupe value.")
    return repr(payload)


def _distance_relation_match_for_token(
    *,
    clause_text: _ClauseText,
    token: DistancePredicateToken,
) -> re.Match[str] | None:
    token_start = token.span.start - clause_text.span.start
    token_end = token.span.end - clause_text.span.start
    for match in _DISTANCE_RELATION_RE.finditer(clause_text.text):
        if match.start("predicate") <= token_start and token_end <= match.end("range"):
            return match
    return None


def _distance_relation_parameter_pairs(
    match: re.Match[str] | None,
) -> tuple[tuple[str, RuleParameterValue], ...]:
    if match is None:
        return ()
    pairs: list[tuple[str, RuleParameterValue]] = [
        ("negated", match.group("negated") is not None),
        ("range_kind", _range_kind_token(match.group("range"))),
        ("object_kind", _object_kind_token(match.group("object_kind"))),
    ]
    subject = match.group("subject")
    if subject is not None:
        pairs.append(("subject", _subject_token(subject)))
    quantity = match.group("quantity")
    if quantity is not None:
        pairs.append(("object_quantity", _quantity_token(quantity)))
    allegiance = match.group("allegiance")
    if allegiance is not None:
        pairs.append(("object_allegiance", allegiance.lower()))
    keyword_text = match.group("keyword")
    if keyword_text is not None:
        pairs.extend(_keyword_sequence_parameter_pairs(keyword_text))
    object_reference = match.group("object_reference")
    if object_reference is not None:
        pairs.append(("object_reference", _subject_token(object_reference)))
    return tuple(pairs)


def _span_from_match(clause_text: _ClauseText, match: re.Match[str]) -> TextSpan:
    start = clause_text.start + match.start()
    end = clause_text.start + match.end()
    return TextSpan(text=clause_text.span.text[match.start() : match.end()], start=start, end=end)


def _token_inside_clause(token: DistancePredicateToken, clause_text: _ClauseText) -> bool:
    return clause_text.span.start <= token.span.start and token.span.end <= clause_text.span.end


def _lower_group(match: re.Match[str], group_name: str) -> str:
    return match.group(group_name).lower().replace(" ", "_").replace("-", "_")


def _owner_token(owner: str | None) -> str | None:
    if owner is None:
        return None
    lowered = owner.lower()
    if "opponent" in lowered:
        return "opponent"
    if lowered == "your":
        return "active_player"
    return None


def _roll_type(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "_")


def _subject_token(value: str) -> str:
    return value.lower().replace(" ", "_").replace("-", "_")


def _range_kind_token(value: str) -> str:
    stripped = value.strip()
    if stripped.endswith('"'):
        return "numeric_range"
    return stripped.lower().replace(" ", "_").replace("-", "_")


def _object_kind_token(value: str) -> str:
    normalized = value.lower().replace(" ", "_").replace("-", "_")
    if normalized in {"units", "unit"}:
        return "unit"
    if normalized in {"models", "model"}:
        return "model"
    if normalized in {"objective_markers", "objective_marker"}:
        return "objective_marker"
    raise RuleIRError(f"Unsupported distance relation object kind: {value}.")


def _quantity_token(value: str) -> str:
    return value.lower().replace(" ", "_").replace("-", "_")


def _keyword_token(value: str) -> str:
    return value.strip().upper().replace(" ", "_").replace("-", "_")


def _keyword_sequence_tokens(value: str) -> tuple[str, ...]:
    normalized = " ".join(value.strip().upper().replace("-", " ").split())
    if not normalized:
        raise RuleIRError("Keyword sequence must not be empty.")
    tokens = tuple(_keyword_token(token) for token in _split_source_keyword_sequence(normalized))
    if not tokens:
        raise RuleIRError("Keyword sequence must contain at least one keyword.")
    return tokens


def _keyword_sequence_parameter_pairs(value: str) -> tuple[tuple[str, RuleParameterValue], ...]:
    tokens = _keyword_sequence_tokens(value)
    if len(tokens) == 1:
        return (("required_keyword", tokens[0]),)
    return (("required_keyword_sequence", "|".join(tokens)),)


def _split_source_keyword_sequence(value: str) -> tuple[str, ...]:
    remaining = value
    tokens: list[str] = []
    while remaining:
        match = _longest_source_keyword_prefix(remaining)
        if match is None:
            tokens.append(remaining)
            break
        tokens.append(match)
        remaining = remaining[len(match) :].strip()
    return tuple(tokens)


def _longest_source_keyword_prefix(value: str) -> str | None:
    for keyword in _SOURCE_KEYWORD_SEQUENCE_PARTS:
        if value == keyword or value.startswith(f"{keyword} "):
            return keyword
    return None


def _ability_token(value: str) -> str:
    stripped = value.strip(" []().,;:")
    return " ".join(stripped.split())


def _feel_no_pain_attack_condition_token(value: str) -> str:
    normalized = value.strip().lower().replace("-", " ")
    if normalized in {"psychic attack", "psychic attacks"}:
        return "psychic_attack"
    raise RuleIRError(f"Unsupported Feel No Pain attack qualifier: {value}.")


def _weapon_name_token(value: str) -> str:
    stripped = value.strip(" []().,;:")
    return " ".join(stripped.split())


def _is_weapon_keyword(value: str) -> bool:
    return value.lower() in {keyword.lower() for keyword in canonical_weapon_keyword_tokens()}


def _characteristic_from_label(value: str) -> Characteristic:
    key = value.lower().replace("-", " ")
    characteristic = _CHARACTERISTIC_BY_LABEL.get(key)
    if characteristic is None:
        raise RuleIRError(f"Unsupported characteristic label in rule language: {value}.")
    return characteristic


def _span_matches_existing_effect(
    *,
    clause_text: _ClauseText,
    match: re.Match[str],
    effects: tuple[RuleEffectSpec, ...],
) -> bool:
    span = _span_from_match(clause_text, match)
    return any(
        span.start >= effect.source_span.start and span.end <= effect.source_span.end
        for effect in effects
    )


def _match_inside_ranges(
    match: re.Match[str],
    ranges: list[tuple[int, int]],
) -> bool:
    return any(start <= match.start() and match.end() <= end for start, end in ranges)
