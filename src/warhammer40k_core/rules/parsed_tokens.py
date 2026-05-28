from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Self, TypedDict

from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceExpressionPayload,
    DiceRollSpecError,
)
from warhammer40k_core.rules.text_normalization import canonical_keyword_forms


class RuleTokenError(ValueError):
    """Raised when normalized rule text cannot be converted into typed tokens."""


class TextSpanPayload(TypedDict):
    text: str
    start: int
    end: int


class DiceExpressionTokenPayload(TextSpanPayload):
    expression: DiceExpressionPayload


class RangeExpressionTokenPayload(TextSpanPayload):
    distance_inches: int


class DistancePredicateTokenPayload(TextSpanPayload):
    kind: str
    distance_inches: float | None
    qualifier: str | None


class KeywordTokenPayload(TextSpanPayload):
    keyword: str


class ParsedRuleTextPayload(TypedDict):
    normalized_text: str
    dice_expressions: list[DiceExpressionTokenPayload]
    range_expressions: list[RangeExpressionTokenPayload]
    distance_predicates: list[DistancePredicateTokenPayload]
    keywords: list[KeywordTokenPayload]


class DistancePredicateKind(StrEnum):
    WITHIN = "within"
    WHOLLY_WITHIN = "wholly_within"
    MORE_THAN = "more_than"
    AT_LEAST = "at_least"
    AT_MOST = "at_most"
    EXACTLY = "exactly"
    WITHIN_ENGAGEMENT_RANGE = "within_engagement_range"
    OUTSIDE_DETECTION_RANGE = "outside_detection_range"
    HALF_RANGE = "half_range"


_DICE_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?P<quantity>\d+)?D(?P<sides>\d+)"
    r"(?P<modifier>[+-]\d+)?"
    r"(?![A-Za-z0-9_])"
)
_RANGE_INTERVAL_RE = re.compile(r'(?<![A-Za-z0-9_])\d+\s*-\s*\d+\s*"')
_RANGE_TOKEN_RE = re.compile(r'(?<![A-Za-z0-9_-])(?P<distance>\d+)"')
_DISTANCE_VALUE_RE = r'(?P<distance>\d+(?:\.\d+)?)"'
_DISTANCE_PREDICATE_PATTERNS = (
    (
        re.compile(
            rf"(?<![A-Za-z0-9_-])wholly\s+within\s+{_DISTANCE_VALUE_RE}"
            r"(?P<qualifier>\s+if\s+possible)?(?![A-Za-z0-9_-])",
            re.IGNORECASE,
        ),
        DistancePredicateKind.WHOLLY_WITHIN,
    ),
    (
        re.compile(
            rf"(?<![A-Za-z0-9_-])within\s+{_DISTANCE_VALUE_RE}"
            r"(?P<qualifier>\s+if\s+possible)?(?![A-Za-z0-9_-])",
            re.IGNORECASE,
        ),
        DistancePredicateKind.WITHIN,
    ),
    (
        re.compile(
            rf"(?<![A-Za-z0-9_-])more\s+than\s+{_DISTANCE_VALUE_RE}(?![A-Za-z0-9_-])",
            re.IGNORECASE,
        ),
        DistancePredicateKind.MORE_THAN,
    ),
    (
        re.compile(
            rf"(?<![A-Za-z0-9_-])at\s+least\s+{_DISTANCE_VALUE_RE}(?![A-Za-z0-9_-])",
            re.IGNORECASE,
        ),
        DistancePredicateKind.AT_LEAST,
    ),
    (
        re.compile(
            rf"(?<![A-Za-z0-9_-])at\s+most\s+{_DISTANCE_VALUE_RE}(?![A-Za-z0-9_-])",
            re.IGNORECASE,
        ),
        DistancePredicateKind.AT_MOST,
    ),
    (
        re.compile(
            rf"(?<![A-Za-z0-9_-])exactly\s+{_DISTANCE_VALUE_RE}(?![A-Za-z0-9_-])",
            re.IGNORECASE,
        ),
        DistancePredicateKind.EXACTLY,
    ),
    (
        re.compile(
            r"(?<![A-Za-z0-9_-])within\s+Engagement\s+Range(?![A-Za-z0-9_-])",
            re.IGNORECASE,
        ),
        DistancePredicateKind.WITHIN_ENGAGEMENT_RANGE,
    ),
    (
        re.compile(
            r"(?<![A-Za-z0-9_-])outside\s+Detection\s+Range(?![A-Za-z0-9_-])",
            re.IGNORECASE,
        ),
        DistancePredicateKind.OUTSIDE_DETECTION_RANGE,
    ),
    (
        re.compile(r"(?<![A-Za-z0-9_-])Half\s+Range(?![A-Za-z0-9_-])", re.IGNORECASE),
        DistancePredicateKind.HALF_RANGE,
    ),
)
_KEYWORD_TOKEN_PATTERNS = tuple(
    (
        re.compile(
            rf"(?<![A-Za-z0-9_-]){re.escape(keyword).replace(r'\ ', r'\s+')}(?![A-Za-z0-9_-])"
        ),
        keyword,
    )
    for keyword in canonical_keyword_forms()
)


@dataclass(frozen=True, slots=True)
class TextSpan:
    text: str
    start: int
    end: int

    def __post_init__(self) -> None:
        _validate_span(self.text, self.start, self.end)

    def to_payload(self) -> TextSpanPayload:
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
        }


@dataclass(frozen=True, slots=True)
class DiceExpressionToken:
    span: TextSpan
    expression: DiceExpression

    def __post_init__(self) -> None:
        _validate_span_object(self.span)
        _validate_dice_expression(self.expression)

    def to_payload(self) -> DiceExpressionTokenPayload:
        return {
            "text": self.span.text,
            "start": self.span.start,
            "end": self.span.end,
            "expression": self.expression.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: DiceExpressionTokenPayload) -> Self:
        return cls(
            span=TextSpan(
                text=payload["text"],
                start=payload["start"],
                end=payload["end"],
            ),
            expression=DiceExpression.from_payload(payload["expression"]),
        )


@dataclass(frozen=True, slots=True)
class RangeExpressionToken:
    span: TextSpan
    distance_inches: int

    def __post_init__(self) -> None:
        _validate_span_object(self.span)
        if type(self.distance_inches) is not int:
            raise RuleTokenError("RangeExpressionToken distance_inches must be an integer.")
        if self.distance_inches < 0:
            raise RuleTokenError("RangeExpressionToken distance_inches must not be negative.")

    def to_payload(self) -> RangeExpressionTokenPayload:
        return {
            "text": self.span.text,
            "start": self.span.start,
            "end": self.span.end,
            "distance_inches": self.distance_inches,
        }

    @classmethod
    def from_payload(cls, payload: RangeExpressionTokenPayload) -> Self:
        return cls(
            span=TextSpan(
                text=payload["text"],
                start=payload["start"],
                end=payload["end"],
            ),
            distance_inches=payload["distance_inches"],
        )


@dataclass(frozen=True, slots=True)
class DistancePredicateToken:
    span: TextSpan
    kind: DistancePredicateKind
    distance_inches: float | None = None
    qualifier: str | None = None

    def __post_init__(self) -> None:
        _validate_span_object(self.span)
        kind = _validate_distance_predicate_kind(self.kind)
        if kind != self.kind:
            object.__setattr__(self, "kind", kind)

        distance = _validate_distance_predicate_distance(kind, self.distance_inches)
        if distance != self.distance_inches:
            object.__setattr__(self, "distance_inches", distance)

        qualifier = _validate_optional_qualifier(kind, self.qualifier)
        if qualifier != self.qualifier:
            object.__setattr__(self, "qualifier", qualifier)

    def to_payload(self) -> DistancePredicateTokenPayload:
        return {
            "text": self.span.text,
            "start": self.span.start,
            "end": self.span.end,
            "kind": self.kind.value,
            "distance_inches": self.distance_inches,
            "qualifier": self.qualifier,
        }

    @classmethod
    def from_payload(cls, payload: DistancePredicateTokenPayload) -> Self:
        return cls(
            span=TextSpan(
                text=payload["text"],
                start=payload["start"],
                end=payload["end"],
            ),
            kind=distance_predicate_kind_from_token(payload["kind"]),
            distance_inches=payload["distance_inches"],
            qualifier=payload["qualifier"],
        )


@dataclass(frozen=True, slots=True)
class KeywordToken:
    span: TextSpan
    keyword: str

    def __post_init__(self) -> None:
        _validate_span_object(self.span)
        if self.keyword not in canonical_keyword_forms():
            raise RuleTokenError("KeywordToken keyword is not canonical.")
        if self.span.text != self.keyword:
            raise RuleTokenError("KeywordToken span text must match the canonical keyword.")

    def to_payload(self) -> KeywordTokenPayload:
        return {
            "text": self.span.text,
            "start": self.span.start,
            "end": self.span.end,
            "keyword": self.keyword,
        }

    @classmethod
    def from_payload(cls, payload: KeywordTokenPayload) -> Self:
        return cls(
            span=TextSpan(
                text=payload["text"],
                start=payload["start"],
                end=payload["end"],
            ),
            keyword=payload["keyword"],
        )


@dataclass(frozen=True, slots=True)
class ParsedRuleText:
    normalized_text: str
    dice_expressions: tuple[DiceExpressionToken, ...] = ()
    range_expressions: tuple[RangeExpressionToken, ...] = ()
    distance_predicates: tuple[DistancePredicateToken, ...] = ()
    keywords: tuple[KeywordToken, ...] = ()

    def __post_init__(self) -> None:
        _validate_normalized_text(self.normalized_text)
        _validate_token_tuple(self.dice_expressions, DiceExpressionToken, "dice_expressions")
        _validate_token_tuple(self.range_expressions, RangeExpressionToken, "range_expressions")
        _validate_token_tuple(
            self.distance_predicates,
            DistancePredicateToken,
            "distance_predicates",
        )
        _validate_token_tuple(self.keywords, KeywordToken, "keywords")
        _validate_tokens_belong_to_text(
            self.normalized_text,
            self.dice_expressions,
            "dice_expressions",
        )
        _validate_tokens_belong_to_text(
            self.normalized_text,
            self.range_expressions,
            "range_expressions",
        )
        _validate_tokens_belong_to_text(
            self.normalized_text,
            self.distance_predicates,
            "distance_predicates",
        )
        _validate_tokens_belong_to_text(self.normalized_text, self.keywords, "keywords")

    def to_payload(self) -> ParsedRuleTextPayload:
        return {
            "normalized_text": self.normalized_text,
            "dice_expressions": [token.to_payload() for token in self.dice_expressions],
            "range_expressions": [token.to_payload() for token in self.range_expressions],
            "distance_predicates": [token.to_payload() for token in self.distance_predicates],
            "keywords": [token.to_payload() for token in self.keywords],
        }

    @classmethod
    def from_payload(cls, payload: ParsedRuleTextPayload) -> Self:
        return cls(
            normalized_text=payload["normalized_text"],
            dice_expressions=tuple(
                DiceExpressionToken.from_payload(token) for token in payload["dice_expressions"]
            ),
            range_expressions=tuple(
                RangeExpressionToken.from_payload(token) for token in payload["range_expressions"]
            ),
            distance_predicates=tuple(
                DistancePredicateToken.from_payload(token)
                for token in payload["distance_predicates"]
            ),
            keywords=tuple(KeywordToken.from_payload(token) for token in payload["keywords"]),
        )


def parse_normalized_tokens(normalized_text: object) -> ParsedRuleText:
    text = _validate_normalized_text(normalized_text)
    distance_predicates = _parse_distance_predicate_tokens(text)
    return ParsedRuleText(
        normalized_text=text,
        dice_expressions=_parse_dice_tokens(text),
        range_expressions=_parse_range_tokens(
            text,
            tuple((token.span.start, token.span.end) for token in distance_predicates),
        ),
        distance_predicates=distance_predicates,
        keywords=_parse_keyword_tokens(text),
    )


def distance_predicate_kind_from_token(token: object) -> DistancePredicateKind:
    if type(token) is DistancePredicateKind:
        return token
    if type(token) is not str:
        raise RuleTokenError("DistancePredicateKind token must be a string.")
    try:
        return DistancePredicateKind(token)
    except ValueError as exc:
        raise RuleTokenError(f"Unsupported DistancePredicateKind token: {token}.") from exc


def _parse_dice_tokens(text: str) -> tuple[DiceExpressionToken, ...]:
    tokens: list[DiceExpressionToken] = []
    for match in _DICE_TOKEN_RE.finditer(text):
        expression = _dice_expression_from_match(match)
        tokens.append(
            DiceExpressionToken(
                span=TextSpan(text=match.group(0), start=match.start(), end=match.end()),
                expression=expression,
            )
        )
    return tuple(tokens)


def _dice_expression_from_match(match: re.Match[str]) -> DiceExpression:
    quantity_text = match.group("quantity")
    modifier_text = match.group("modifier")
    try:
        return DiceExpression(
            quantity=1 if quantity_text is None else int(quantity_text),
            sides=int(match.group("sides")),
            modifier=0 if modifier_text is None else int(modifier_text),
        )
    except DiceRollSpecError as exc:
        raise RuleTokenError("Dice expression token is invalid.") from exc


def _parse_range_tokens(
    text: str,
    excluded_spans: tuple[tuple[int, int], ...] = (),
) -> tuple[RangeExpressionToken, ...]:
    if _RANGE_INTERVAL_RE.search(text):
        raise RuleTokenError("Range intervals are not supported yet.")

    tokens: list[RangeExpressionToken] = []
    for match in _RANGE_TOKEN_RE.finditer(text):
        if _span_is_inside(match.start(), match.end(), excluded_spans):
            continue
        tokens.append(
            RangeExpressionToken(
                span=TextSpan(text=match.group(0), start=match.start(), end=match.end()),
                distance_inches=int(match.group("distance")),
            )
        )
    return tuple(tokens)


def _parse_distance_predicate_tokens(text: str) -> tuple[DistancePredicateToken, ...]:
    tokens: list[DistancePredicateToken] = []
    for pattern, kind in _DISTANCE_PREDICATE_PATTERNS:
        for match in pattern.finditer(text):
            if _span_overlaps(match.start(), match.end(), tokens):
                continue
            tokens.append(_distance_predicate_token_from_match(match, kind))

    return tuple(
        sorted(tokens, key=lambda token: (token.span.start, token.span.end, token.kind.value))
    )


def _distance_predicate_token_from_match(
    match: re.Match[str],
    kind: DistancePredicateKind,
) -> DistancePredicateToken:
    distance_text = match.groupdict().get("distance")
    qualifier_text = match.groupdict().get("qualifier")
    return DistancePredicateToken(
        span=TextSpan(text=match.group(0), start=match.start(), end=match.end()),
        kind=kind,
        distance_inches=None if distance_text is None else float(distance_text),
        qualifier=None if qualifier_text is None else qualifier_text.strip(),
    )


def _span_is_inside(
    start: int,
    end: int,
    excluded_spans: tuple[tuple[int, int], ...],
) -> bool:
    return any(
        excluded_start <= start and end <= excluded_end
        for excluded_start, excluded_end in excluded_spans
    )


def _span_overlaps(
    start: int,
    end: int,
    tokens: tuple[DistancePredicateToken, ...] | list[DistancePredicateToken],
) -> bool:
    return any(start < token.span.end and token.span.start < end for token in tokens)


def _parse_keyword_tokens(text: str) -> tuple[KeywordToken, ...]:
    tokens: list[KeywordToken] = []
    for pattern, keyword in _KEYWORD_TOKEN_PATTERNS:
        tokens.extend(
            KeywordToken(
                span=TextSpan(text=match.group(0), start=match.start(), end=match.end()),
                keyword=keyword,
            )
            for match in pattern.finditer(text)
        )
    return tuple(
        sorted(tokens, key=lambda token: (token.span.start, token.span.end, token.keyword))
    )


def _validate_normalized_text(normalized_text: object) -> str:
    if type(normalized_text) is not str:
        raise RuleTokenError("Normalized rule text must be a string.")
    if not normalized_text.strip():
        raise RuleTokenError("Normalized rule text must not be empty.")
    return normalized_text


def _validate_span(text: object, start: object, end: object) -> None:
    if type(text) is not str:
        raise RuleTokenError("TextSpan text must be a string.")
    if not text:
        raise RuleTokenError("TextSpan text must not be empty.")
    if type(start) is not int:
        raise RuleTokenError("TextSpan start must be an integer.")
    if type(end) is not int:
        raise RuleTokenError("TextSpan end must be an integer.")
    if start < 0 or end <= start:
        raise RuleTokenError("TextSpan bounds are invalid.")


def _validate_span_object(span: object) -> TextSpan:
    if type(span) is not TextSpan:
        raise RuleTokenError("Token span must be a TextSpan.")
    return span


def _validate_dice_expression(expression: object) -> DiceExpression:
    if type(expression) is not DiceExpression:
        raise RuleTokenError("DiceExpressionToken expression must be a DiceExpression.")
    return expression


def _validate_distance_predicate_kind(kind: object) -> DistancePredicateKind:
    if type(kind) is not DistancePredicateKind:
        raise RuleTokenError("DistancePredicateToken kind must be a DistancePredicateKind.")
    return kind


def _validate_distance_predicate_distance(
    kind: DistancePredicateKind,
    distance_inches: object | None,
) -> float | None:
    if kind in {
        DistancePredicateKind.WITHIN,
        DistancePredicateKind.WHOLLY_WITHIN,
        DistancePredicateKind.MORE_THAN,
        DistancePredicateKind.AT_LEAST,
        DistancePredicateKind.AT_MOST,
        DistancePredicateKind.EXACTLY,
    }:
        if type(distance_inches) is int:
            distance = float(distance_inches)
        elif type(distance_inches) is float:
            distance = distance_inches
        else:
            raise RuleTokenError("DistancePredicateToken distance_inches must be a number.")
        if not isfinite(distance) or distance <= 0.0:
            raise RuleTokenError("DistancePredicateToken distance_inches must be positive.")
        return distance

    if distance_inches is not None:
        raise RuleTokenError(
            "DistancePredicateToken distance_inches must be empty for non-numeric predicates."
        )
    return None


def _validate_optional_qualifier(
    kind: DistancePredicateKind,
    qualifier: object | None,
) -> str | None:
    if qualifier is None:
        return None
    if kind not in {DistancePredicateKind.WITHIN, DistancePredicateKind.WHOLLY_WITHIN}:
        raise RuleTokenError(
            "DistancePredicateToken qualifier is only supported for within predicates."
        )
    if type(qualifier) is not str:
        raise RuleTokenError("DistancePredicateToken qualifier must be a string.")
    stripped = qualifier.strip()
    if not stripped:
        raise RuleTokenError("DistancePredicateToken qualifier must not be empty.")
    return stripped


def _validate_token_tuple(
    tokens: tuple[object, ...],
    expected_type: type[object],
    field_name: str,
) -> None:
    for token in tokens:
        if type(token) is not expected_type:
            raise RuleTokenError(f"ParsedRuleText {field_name} contains an invalid token.")


def _validate_tokens_belong_to_text(
    normalized_text: str,
    tokens: tuple[object, ...],
    field_name: str,
) -> None:
    previous_key: tuple[int, int, str] | None = None

    for token in tokens:
        span = _token_span(token)
        if span.end > len(normalized_text):
            raise RuleTokenError(
                f"ParsedRuleText {field_name} token span is outside normalized_text."
            )
        if normalized_text[span.start : span.end] != span.text:
            raise RuleTokenError(
                f"ParsedRuleText {field_name} token span text does not match normalized_text."
            )

        key = (span.start, span.end, span.text)
        if previous_key is not None and key < previous_key:
            raise RuleTokenError(
                f"ParsedRuleText {field_name} tokens must be deterministically ordered."
            )
        previous_key = key


def _token_span(token: object) -> TextSpan:
    if type(token) is DiceExpressionToken:
        return token.span
    if type(token) is RangeExpressionToken:
        return token.span
    if type(token) is DistancePredicateToken:
        return token.span
    if type(token) is KeywordToken:
        return token.span
    raise RuleTokenError("ParsedRuleText token type is invalid.")
