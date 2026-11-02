from __future__ import annotations

from dataclasses import dataclass
from typing import NotRequired, Self, TypedDict

from warhammer40k_core.rules.objective_terminology import (
    ObjectiveRuleScope,
    normalize_objective_rule_text,
    objective_rule_scope_from_token,
)
from warhammer40k_core.rules.parsed_tokens import (
    ParsedRuleText,
    ParsedRuleTextPayload,
    parse_normalized_tokens,
)
from warhammer40k_core.rules.text_normalization import (
    SourceTextNormalizationMode,
    source_text_normalization_mode_from_token,
)


class SourceDataError(ValueError):
    """Raised when rule source data violates the normalization boundary."""


class RuleSourceTextPayload(TypedDict):
    source_id: str
    raw_text: str
    normalized_text: str
    parsed_tokens: ParsedRuleTextPayload
    objective_scope: str
    normalization_mode: NotRequired[str]


@dataclass(frozen=True, slots=True)
class RuleSourceText:
    source_id: str
    raw_text: str
    normalized_text: str
    parsed_tokens: ParsedRuleText
    objective_scope: ObjectiveRuleScope
    normalization_mode: SourceTextNormalizationMode = SourceTextNormalizationMode.FLAT

    def __post_init__(self) -> None:
        if type(self.normalization_mode) is not SourceTextNormalizationMode:
            raise SourceDataError("RuleSourceText normalization mode must be typed.")
        if type(self.objective_scope) is not ObjectiveRuleScope:
            raise SourceDataError("RuleSourceText objective_scope must be ObjectiveRuleScope.")
        object.__setattr__(self, "source_id", _validate_source_id(self.source_id))
        if type(self.raw_text) is not str:
            raise SourceDataError("RuleSourceText raw_text must be a string.")
        if type(self.normalized_text) is not str:
            raise SourceDataError("RuleSourceText normalized_text must be a string.")
        if type(self.parsed_tokens) is not ParsedRuleText:
            raise SourceDataError("RuleSourceText parsed_tokens must be ParsedRuleText.")
        if self.parsed_tokens.normalized_text != self.normalized_text:
            raise SourceDataError("RuleSourceText parsed tokens must match normalized_text.")
        if (
            self.objective_scope is not ObjectiveRuleScope.HISTORICAL_TEXT
            and normalize_objective_rule_text(
                self.raw_text,
                scope=self.objective_scope,
                normalization_mode=self.normalization_mode,
            )
            != self.normalized_text
        ):
            raise SourceDataError("RuleSourceText scope does not match normalized source data.")

    @classmethod
    def from_raw(
        cls,
        *,
        source_id: object,
        raw_text: object,
        objective_scope: ObjectiveRuleScope,
        normalization_mode: SourceTextNormalizationMode = SourceTextNormalizationMode.FLAT,
    ) -> RuleSourceText:
        normalized_text = normalize_objective_rule_text(
            raw_text, scope=objective_scope, normalization_mode=normalization_mode
        )
        return cls(
            source_id=_validate_source_id(source_id),
            raw_text=_validate_raw_text(raw_text),
            normalized_text=normalized_text,
            parsed_tokens=parse_normalized_tokens(normalized_text),
            objective_scope=objective_scope,
            normalization_mode=normalization_mode,
        )

    def to_payload(self) -> RuleSourceTextPayload:
        payload: RuleSourceTextPayload = {
            "source_id": self.source_id,
            "raw_text": self.raw_text,
            "normalized_text": self.normalized_text,
            "parsed_tokens": self.parsed_tokens.to_payload(),
            "objective_scope": self.objective_scope.value,
        }
        # Preserve every existing flat-mode payload and catalog fingerprint byte-for-byte.
        if self.normalization_mode is not SourceTextNormalizationMode.FLAT:
            payload["normalization_mode"] = self.normalization_mode.value
        return payload

    @classmethod
    def from_payload(cls, payload: RuleSourceTextPayload) -> Self:
        source = cls(
            source_id=payload["source_id"],
            raw_text=payload["raw_text"],
            normalized_text=payload["normalized_text"],
            parsed_tokens=ParsedRuleText.from_payload(payload["parsed_tokens"]),
            objective_scope=objective_rule_scope_from_token(payload["objective_scope"]),
            normalization_mode=source_text_normalization_mode_from_token(
                payload.get("normalization_mode", SourceTextNormalizationMode.FLAT)
            ),
        )
        expected = cls.from_raw(
            source_id=source.source_id,
            raw_text=source.raw_text,
            objective_scope=source.objective_scope,
            normalization_mode=source.normalization_mode,
        )
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
