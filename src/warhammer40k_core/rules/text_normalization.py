from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.core.weapon_profiles import canonical_weapon_keyword_tokens
from warhammer40k_core.rules.keywords import canonical_rule_keyword_tokens


class TextNormalizationError(ValueError):
    """Raised when raw rule text cannot be normalized at the data boundary."""


class NormalizedRuleTextPayload(TypedDict):
    raw_text: str
    normalized_text: str


_CHARACTER_TRANSLATION = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u2032": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u2033": '"',
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\u00a0": " ",
        "\u1680": " ",
        "\u2000": " ",
        "\u2001": " ",
        "\u2002": " ",
        "\u2003": " ",
        "\u2004": " ",
        "\u2005": " ",
        "\u2006": " ",
        "\u2007": " ",
        "\u2008": " ",
        "\u2009": " ",
        "\u200a": " ",
        "\u202f": " ",
        "\u205f": " ",
        "\u3000": " ",
        "\u00d7": "x",
        "\u2715": "x",
        "\u2716": "x",
    }
)

_DICE_EXPRESSION_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?:(?P<quantity>\d+)\s*)?"
    r"[dD]\s*(?P<sides>\d+)"
    r"(?:\s*(?P<sign>[+-])\s*(?P<modifier>\d+))?"
    r"(?![A-Za-z0-9_])"
)
_RANGE_WORD_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?P<distance>\d+)\s*(?:inches|inch|in)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_RANGE_QUOTE_RE = re.compile(r'(?<![A-Za-z0-9_])(?P<distance>\d+)\s*"')
_WHITESPACE_RE = re.compile(r"\s+")
_LINEBREAK_RE = re.compile(r"\r\n?|\n")

_CANONICAL_KEYWORDS = (*canonical_weapon_keyword_tokens(), *canonical_rule_keyword_tokens())
_KEYWORD_PATTERNS = tuple(
    (
        re.compile(
            rf"(?<![A-Za-z0-9_-]){re.escape(keyword).replace(r'\ ', r'\s+')}(?![A-Za-z0-9_-])",
            re.IGNORECASE,
        ),
        keyword,
    )
    for keyword in _CANONICAL_KEYWORDS
)


@dataclass(frozen=True, slots=True)
class NormalizedRuleText:
    raw_text: str
    normalized_text: str

    def __post_init__(self) -> None:
        expected = normalize_rule_text(self.raw_text)
        if self.normalized_text != expected:
            raise TextNormalizationError(
                "NormalizedRuleText normalized_text does not match raw_text."
            )

    @classmethod
    def from_raw(cls, raw_text: object) -> Self:
        raw = _validate_raw_text(raw_text)
        return cls(raw_text=raw, normalized_text=normalize_rule_text(raw))

    def to_payload(self) -> NormalizedRuleTextPayload:
        return {
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
        }

    @classmethod
    def from_payload(cls, payload: NormalizedRuleTextPayload) -> Self:
        return cls(
            raw_text=payload["raw_text"],
            normalized_text=payload["normalized_text"],
        )


def normalize_rule_text(raw_text: object) -> str:
    text = _validate_raw_text(raw_text)
    text = _normalize_unicode(text)
    text = _collapse_whitespace(text)
    text = _canonicalize_dice_expressions(text)
    text = _canonicalize_range_expressions(text)
    text = _canonicalize_keywords(text)
    return _collapse_whitespace(text)


def normalize_structured_source_text(raw_text: object) -> str:
    text = _validate_raw_text(raw_text)
    text = _normalize_unicode(text)
    blocks: list[str] = []
    for line in _LINEBREAK_RE.split(text):
        collapsed_line = _collapse_whitespace(line)
        if not collapsed_line:
            continue
        if collapsed_line.startswith("- "):
            normalized_line = f"- {normalize_rule_text(collapsed_line[2:])}"
        else:
            normalized_line = normalize_rule_text(collapsed_line)
        blocks.append(normalized_line)
    if not blocks:
        raise TextNormalizationError("Structured source text must contain normalized text.")
    return "\n".join(blocks)


def canonical_keyword_forms() -> tuple[str, ...]:
    return _CANONICAL_KEYWORDS


def _validate_raw_text(raw_text: object) -> str:
    if type(raw_text) is not str:
        raise TextNormalizationError("Raw rule text must be a string.")
    if not raw_text.strip():
        raise TextNormalizationError("Raw rule text must not be empty.")
    for character in raw_text:
        if character in "\t\n\r":
            continue
        if unicodedata.category(character) == "Cc":
            raise TextNormalizationError("Raw rule text must not contain control characters.")
    return raw_text


def _normalize_unicode(text: str) -> str:
    translated = text.translate(_CHARACTER_TRANSLATION)
    normalized = unicodedata.normalize("NFKC", translated)
    return normalized.translate(_CHARACTER_TRANSLATION)


def _collapse_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _canonicalize_dice_expressions(text: str) -> str:
    return _DICE_EXPRESSION_RE.sub(_dice_replacement, text)


def _dice_replacement(match: re.Match[str]) -> str:
    quantity_text = match.group("quantity")
    sides = int(match.group("sides"))
    quantity = 1 if quantity_text is None else int(quantity_text)
    base = f"{quantity}D{sides}" if quantity != 1 else f"D{sides}"

    sign = match.group("sign")
    modifier = match.group("modifier")
    if sign is None or modifier is None:
        return base
    return f"{base}{sign}{int(modifier)}"


def _canonicalize_range_expressions(text: str) -> str:
    text = _RANGE_WORD_RE.sub(r'\g<distance>"', text)
    return _RANGE_QUOTE_RE.sub(r'\g<distance>"', text)


def _canonicalize_keywords(text: str) -> str:
    canonical = text
    for pattern, keyword in _KEYWORD_PATTERNS:
        canonical = pattern.sub(keyword, canonical)
    return canonical
