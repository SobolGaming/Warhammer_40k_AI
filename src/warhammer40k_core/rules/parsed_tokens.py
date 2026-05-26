from __future__ import annotations

import re
from dataclasses import dataclass
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


class KeywordTokenPayload(TextSpanPayload):
    keyword: str


class ParsedRuleTextPayload(TypedDict):
    normalized_text: str
    dice_expressions: list[DiceExpressionTokenPayload]
    range_expressions: list[RangeExpressionTokenPayload]
    keywords: list[KeywordTokenPayload]


_DICE_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?P<quantity>\d+)?D(?P<sides>\d+)"
    r"(?P<modifier>[+-]\d+)?"
    r"(?![A-Za-z0-9_])"
)
_RANGE_TOKEN_RE = re.compile(r'(?<![A-Za-z0-9_-])(?P<distance>\d+)"')
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
    keywords: tuple[KeywordToken, ...] = ()

    def __post_init__(self) -> None:
        _validate_normalized_text(self.normalized_text)
        _validate_token_tuple(self.dice_expressions, DiceExpressionToken, "dice_expressions")
        _validate_token_tuple(self.range_expressions, RangeExpressionToken, "range_expressions")
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
        _validate_tokens_belong_to_text(self.normalized_text, self.keywords, "keywords")

    def to_payload(self) -> ParsedRuleTextPayload:
        return {
            "normalized_text": self.normalized_text,
            "dice_expressions": [token.to_payload() for token in self.dice_expressions],
            "range_expressions": [token.to_payload() for token in self.range_expressions],
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
            keywords=tuple(KeywordToken.from_payload(token) for token in payload["keywords"]),
        )


def parse_normalized_tokens(normalized_text: object) -> ParsedRuleText:
    text = _validate_normalized_text(normalized_text)
    return ParsedRuleText(
        normalized_text=text,
        dice_expressions=_parse_dice_tokens(text),
        range_expressions=_parse_range_tokens(text),
        keywords=_parse_keyword_tokens(text),
    )


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


def _parse_range_tokens(text: str) -> tuple[RangeExpressionToken, ...]:
    return tuple(
        RangeExpressionToken(
            span=TextSpan(text=match.group(0), start=match.start(), end=match.end()),
            distance_inches=int(match.group("distance")),
        )
        for match in _RANGE_TOKEN_RE.finditer(text)
    )


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
    if type(token) is KeywordToken:
        return token.span
    raise RuleTokenError("ParsedRuleText token type is invalid.")
