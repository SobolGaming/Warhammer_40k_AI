from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.rules.parsed_tokens import (
    ParsedRuleText,
    ParsedRuleTextPayload,
    RuleTokenError,
)
from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload
from warhammer40k_core.rules.rule_parser import RULE_PARSER_VERSION, parse_rule_ir
from warhammer40k_core.rules.source_data import RuleSourceText, RuleSourceTextPayload

RULE_COMPILER_VERSION = "phase17c-rule-compiler-v1"


class RuleCompilerError(ValueError):
    """Raised when Phase 17C rule compilation violates source-boundary invariants."""


class CompiledRuleSourcePayload(TypedDict):
    source_text: RuleSourceTextPayload
    rule_ir: RuleIRPayload
    compiler_version: str


@dataclass(frozen=True, slots=True)
class CompiledRuleSource:
    source_text: RuleSourceText
    rule_ir: RuleIR
    compiler_version: str = RULE_COMPILER_VERSION

    def __post_init__(self) -> None:
        if type(self.source_text) is not RuleSourceText:
            raise RuleCompilerError("CompiledRuleSource source_text must be RuleSourceText.")
        if type(self.rule_ir) is not RuleIR:
            raise RuleCompilerError("CompiledRuleSource rule_ir must be RuleIR.")
        if self.rule_ir.source_id != self.source_text.source_id:
            raise RuleCompilerError("CompiledRuleSource rule_ir source_id must match source_text.")
        if self.rule_ir.normalized_text != self.source_text.normalized_text:
            raise RuleCompilerError(
                "CompiledRuleSource rule_ir normalized_text must match source_text."
            )
        object.__setattr__(
            self,
            "compiler_version",
            _validate_identifier("compiler_version", self.compiler_version),
        )

    def to_payload(self) -> CompiledRuleSourcePayload:
        return {
            "source_text": self.source_text.to_payload(),
            "rule_ir": self.rule_ir.to_payload(),
            "compiler_version": self.compiler_version,
        }

    @classmethod
    def from_payload(
        cls,
        payload: CompiledRuleSourcePayload,
        *,
        source_keyword_sequence_parts: tuple[str, ...],
    ) -> Self:
        source_text = RuleSourceText.from_payload(payload["source_text"])
        compiled = cls(
            source_text=source_text,
            rule_ir=RuleIR.from_payload(payload["rule_ir"]),
            compiler_version=payload["compiler_version"],
        )
        expected = compile_rule_source_text(
            source_text,
            source_keyword_sequence_parts=source_keyword_sequence_parts,
        )
        if compiled.rule_ir.to_payload() != expected.rule_ir.to_payload():
            raise RuleCompilerError("CompiledRuleSource payload contains stale rule_ir.")
        return compiled


def compile_rule_source_text(
    source_text: RuleSourceText,
    *,
    source_keyword_sequence_parts: tuple[str, ...],
) -> CompiledRuleSource:
    if type(source_text) is not RuleSourceText:
        raise RuleCompilerError("Rule compiler requires RuleSourceText.")
    return CompiledRuleSource(
        source_text=source_text,
        rule_ir=parse_rule_ir(
            source_id=source_text.source_id,
            parsed_text=source_text.parsed_tokens,
            source_keyword_sequence_parts=source_keyword_sequence_parts,
        ),
    )


def compile_rule_source_texts(
    source_texts: tuple[RuleSourceText, ...],
    *,
    source_keyword_sequence_parts: tuple[str, ...],
) -> tuple[CompiledRuleSource, ...]:
    if type(source_texts) is not tuple:
        raise RuleCompilerError("Rule compiler source_texts must be a tuple.")
    compiled = tuple(
        compile_rule_source_text(
            source_text,
            source_keyword_sequence_parts=source_keyword_sequence_parts,
        )
        for source_text in source_texts
    )
    seen: set[str] = set()
    for source in compiled:
        if source.source_text.source_id in seen:
            raise RuleCompilerError("Rule compiler source_texts must not duplicate source IDs.")
        seen.add(source.source_text.source_id)
    return tuple(sorted(compiled, key=lambda source: source.source_text.source_id))


def compile_normalized_rule_text(
    *,
    source_id: str,
    normalized_text: str,
    parsed_tokens: ParsedRuleText,
    source_keyword_sequence_parts: tuple[str, ...],
) -> RuleIR:
    if type(parsed_tokens) is not ParsedRuleText:
        raise RuleCompilerError(
            "compile_normalized_rule_text parsed_tokens must be ParsedRuleText."
        )
    if parsed_tokens.normalized_text != normalized_text:
        raise RuleCompilerError("compile_normalized_rule_text parsed tokens are stale.")
    return parse_rule_ir(
        source_id=source_id,
        parsed_text=parsed_tokens,
        source_keyword_sequence_parts=source_keyword_sequence_parts,
    )


def compile_normalized_rule_text_payload(
    *,
    source_id: str,
    normalized_text: str,
    parsed_tokens: ParsedRuleTextPayload,
    source_keyword_sequence_parts: tuple[str, ...],
) -> RuleIR:
    try:
        parsed = ParsedRuleText.from_payload(parsed_tokens)
    except RuleTokenError as exc:
        raise RuleCompilerError("Parsed rule-text payload is invalid.") from exc
    return compile_normalized_rule_text(
        source_id=source_id,
        normalized_text=normalized_text,
        parsed_tokens=parsed,
        source_keyword_sequence_parts=source_keyword_sequence_parts,
    )


def compiler_identity_payload() -> dict[str, str]:
    return {
        "compiler_version": RULE_COMPILER_VERSION,
        "parser_version": RULE_PARSER_VERSION,
        "ir_schema_version": "phase17c-rule-ir-v1",
    }


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise RuleCompilerError(f"Rule compiler {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise RuleCompilerError(f"Rule compiler {field_name} must not be empty.")
    return stripped
