from __future__ import annotations

from warhammer40k_core.rules.rule_ir import RuleIRError, RuleParameterValue
from warhammer40k_core.rules.rule_token_normalization import keyword_token as _keyword_token


def keyword_sequence_tokens(
    value: str,
    *,
    source_keyword_sequence_parts: tuple[str, ...],
) -> tuple[str, ...]:
    normalized = " ".join(value.strip().upper().replace("-", " ").split())
    if not normalized:
        raise RuleIRError("Keyword sequence must not be empty.")
    tokens = tuple(
        _keyword_token(token)
        for token in _split_source_keyword_sequence(
            normalized,
            source_keyword_sequence_parts=source_keyword_sequence_parts,
        )
    )
    if not tokens:
        raise RuleIRError("Keyword sequence must contain at least one keyword.")
    return tokens


def keyword_sequence_parameter_pairs(
    value: str,
    *,
    source_keyword_sequence_parts: tuple[str, ...],
) -> tuple[tuple[str, RuleParameterValue], ...]:
    tokens = keyword_sequence_tokens(
        value,
        source_keyword_sequence_parts=source_keyword_sequence_parts,
    )
    if len(tokens) == 1:
        return (("required_keyword", tokens[0]),)
    return (("required_keyword_sequence", tokens),)


def _split_source_keyword_sequence(
    value: str,
    *,
    source_keyword_sequence_parts: tuple[str, ...],
) -> tuple[str, ...]:
    remaining = value
    tokens: list[str] = []
    while remaining:
        match = _longest_source_keyword_prefix(
            remaining,
            source_keyword_sequence_parts=source_keyword_sequence_parts,
        )
        if match is None:
            tokens.append(remaining)
            break
        tokens.append(match)
        remaining = remaining[len(match) :].strip()
    return tuple(tokens)


def _longest_source_keyword_prefix(
    value: str,
    *,
    source_keyword_sequence_parts: tuple[str, ...],
) -> str | None:
    for keyword in source_keyword_sequence_parts:
        if value == keyword or value.startswith(f"{keyword} "):
            return keyword
    return None
