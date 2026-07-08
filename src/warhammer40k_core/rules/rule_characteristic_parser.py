from __future__ import annotations

import re

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleEffectSpec,
    RuleIRError,
    RuleParameterValue,
    parameters_from_pairs,
)

_CHARACTERISTIC_NAMES = (
    "Armor Penetration|AP|Attacks|Ballistic Skill|BS|Damage|Detection Range|Invulnerable Save|"
    "Leadership|Move|Movement|Objective Control|OC|Range|Save|Strength|Toughness|Weapon Skill|"
    "Wounds|WS"
)
_CHARACTERISTIC_LIST_RE = re.compile(
    rf"\b(?P<verb>add|subtract)\s+(?P<value>\d+)(?:\")?\s+(?:to|from)\s+"
    rf"(?:the\s+)?(?P<characteristics>(?:{_CHARACTERISTIC_NAMES})"
    rf"(?:(?:\s*,\s*|\s+and\s+)(?:{_CHARACTERISTIC_NAMES}))+)\s+characteristics\b"
    r"(?:\s+of\s+(?P<weapon_scope>all|ranged|melee)?\s*weapons?\s+equipped\s+by\s+"
    r"models\s+in\s+(?:this|that|selected|target)\s+unit)?",
    re.IGNORECASE,
)
_CHARACTERISTIC_RE = re.compile(
    rf"\b(?P<verb>add|subtract)\s+(?P<value>\d+)(?:\")?\s+(?:to|from)\s+"
    rf"(?:the\s+)?(?P<characteristic>{_CHARACTERISTIC_NAMES})\s+characteristic\b"
    r"(?:\s+of\s+that\s+attack|\s+of\s+(?P<weapon_scope>all|ranged|melee)?\s*"
    r"weapons?\s+equipped\s+by\s+models\s+in\s+(?:this|that|selected|target)\s+unit)?",
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


def parse_characteristic_effects(clause_span: TextSpan) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    list_spans: list[tuple[int, int]] = []
    for match in _CHARACTERISTIC_LIST_RE.finditer(clause_span.text):
        list_spans.append((match.start(), match.end()))
        value = int(match.group("value"))
        delta = value if _lower_group(match, "verb") == "add" else -value
        for characteristic in _characteristics_from_list(match.group("characteristics")):
            effects.append(
                RuleEffectSpec(
                    kind=_characteristic_effect_kind(characteristic),
                    source_span=_span_from_match(clause_span, match),
                    parameters=parameters_from_pairs(
                        (
                            ("characteristic", characteristic.value),
                            ("delta", delta),
                            *_weapon_scope_parameter_pairs(match),
                        )
                    ),
                )
            )
    for match in _CHARACTERISTIC_RE.finditer(clause_span.text):
        if _match_is_within_any_span(match=match, spans=tuple(list_spans)):
            continue
        characteristic = _characteristic_from_label(match.group("characteristic"))
        value = int(match.group("value"))
        delta = value if _lower_group(match, "verb") == "add" else -value
        effects.append(
            RuleEffectSpec(
                kind=_characteristic_effect_kind(characteristic),
                source_span=_span_from_match(clause_span, match),
                parameters=parameters_from_pairs(
                    (
                        ("characteristic", characteristic.value),
                        ("delta", delta),
                        *_weapon_scope_parameter_pairs(match),
                    )
                ),
            )
        )
    for match in _SET_CHARACTERISTIC_RE.finditer(clause_span.text):
        characteristic = _characteristic_from_label(match.group("characteristic"))
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.SET_CHARACTERISTIC,
                source_span=_span_from_match(clause_span, match),
                parameters=parameters_from_pairs(
                    (
                        ("characteristic", characteristic.value),
                        ("value", match.group("value")),
                    )
                ),
            )
        )
    for match in _ADDITIONAL_MOVE_RE.finditer(clause_span.text):
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.MODIFY_MOVE_DISTANCE,
                source_span=_span_from_match(clause_span, match),
                parameters=parameters_from_pairs((("delta_inches", int(match.group("distance"))),)),
            )
        )
    return tuple(effects)


def _characteristic_effect_kind(characteristic: Characteristic) -> RuleEffectKind:
    if characteristic is Characteristic.MOVEMENT:
        return RuleEffectKind.MODIFY_MOVE_DISTANCE
    return RuleEffectKind.MODIFY_CHARACTERISTIC


def _characteristics_from_list(value: str) -> tuple[Characteristic, ...]:
    characteristics: list[Characteristic] = []
    for token in re.split(r"\s*,\s*|\s+and\s+", value):
        stripped = token.strip()
        if not stripped:
            continue
        characteristics.append(_characteristic_from_label(stripped))
    if len(characteristics) < 2:
        raise RuleIRError("Characteristic list must contain at least two characteristics.")
    return tuple(characteristics)


def _weapon_scope_parameter_pairs(
    match: re.Match[str],
) -> tuple[tuple[str, RuleParameterValue], ...]:
    if "weapon_scope" not in match.groupdict():
        return ()
    weapon_scope = match.group("weapon_scope")
    if weapon_scope is None:
        if "weapon" in match.group(0).lower():
            return (("weapon_scope", "all"),)
        return ()
    return (("weapon_scope", weapon_scope.lower()),)


def _characteristic_from_label(value: str) -> Characteristic:
    key = value.lower().replace("-", " ")
    characteristic = _CHARACTERISTIC_BY_LABEL.get(key)
    if characteristic is None:
        raise RuleIRError(f"Unsupported characteristic label in rule language: {value}.")
    return characteristic


def _span_from_match(clause_span: TextSpan, match: re.Match[str]) -> TextSpan:
    start = clause_span.start + match.start()
    end = clause_span.start + match.end()
    return TextSpan(text=clause_span.text[match.start() : match.end()], start=start, end=end)


def _lower_group(match: re.Match[str], group_name: str) -> str:
    return match.group(group_name).lower().replace(" ", "_").replace("-", "_")


def _match_is_within_any_span(
    *,
    match: re.Match[str],
    spans: tuple[tuple[int, int], ...],
) -> bool:
    return any(start <= match.start() and match.end() <= end for start, end in spans)
