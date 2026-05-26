from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.rules.parsed_tokens import (
    ParsedRuleText,
    ParsedRuleTextPayload,
    parse_normalized_tokens,
)
from warhammer40k_core.rules.text_normalization import normalize_rule_text


class SourceDataError(ValueError):
    """Raised when rule source data violates the normalization boundary."""


class RuleSourceTextPayload(TypedDict):
    source_id: str
    raw_text: str
    normalized_text: str
    parsed_tokens: ParsedRuleTextPayload


@dataclass(frozen=True, slots=True)
class RuleSourceText:
    source_id: str
    raw_text: str
    normalized_text: str
    parsed_tokens: ParsedRuleText

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _validate_source_id(self.source_id))
        if type(self.raw_text) is not str:
            raise SourceDataError("RuleSourceText raw_text must be a string.")
        if type(self.normalized_text) is not str:
            raise SourceDataError("RuleSourceText normalized_text must be a string.")
        if type(self.parsed_tokens) is not ParsedRuleText:
            raise SourceDataError("RuleSourceText parsed_tokens must be ParsedRuleText.")
        if self.parsed_tokens.normalized_text != self.normalized_text:
            raise SourceDataError("RuleSourceText parsed tokens must match normalized_text.")

    @classmethod
    def from_raw(cls, *, source_id: object, raw_text: object) -> RuleSourceText:
        normalized_text = normalize_rule_text(raw_text)
        return cls(
            source_id=_validate_source_id(source_id),
            raw_text=_validate_raw_text(raw_text),
            normalized_text=normalized_text,
            parsed_tokens=parse_normalized_tokens(normalized_text),
        )

    def to_payload(self) -> RuleSourceTextPayload:
        return {
            "source_id": self.source_id,
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "parsed_tokens": self.parsed_tokens.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: RuleSourceTextPayload) -> Self:
        source = cls(
            source_id=payload["source_id"],
            raw_text=payload["raw_text"],
            normalized_text=payload["normalized_text"],
            parsed_tokens=ParsedRuleText.from_payload(payload["parsed_tokens"]),
        )
        expected = cls.from_raw(source_id=source.source_id, raw_text=source.raw_text)
        if source.to_payload() != expected.to_payload():
            raise SourceDataError("RuleSourceText payload does not match normalized source data.")
        return source


def _validate_source_id(source_id: object) -> str:
    if type(source_id) is not str:
        raise SourceDataError("RuleSourceText source_id must be a string.")
    stripped = source_id.strip()
    if not stripped:
        raise SourceDataError("RuleSourceText source_id must not be empty.")
    return stripped


def _validate_raw_text(raw_text: object) -> str:
    if type(raw_text) is not str:
        raise SourceDataError("RuleSourceText raw_text must be a string.")
    return raw_text
