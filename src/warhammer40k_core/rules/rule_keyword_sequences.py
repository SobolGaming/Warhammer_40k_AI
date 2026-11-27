from __future__ import annotations

from warhammer40k_core.core.keyword_numbers import keyword_number_spellings
from warhammer40k_core.rules.rule_ir import RuleIRError, RuleParameterValue
from warhammer40k_core.rules.rule_token_normalization import keyword_token as _keyword_token


def keyword_sequence_tokens(
    value: str,
    *,
    source_keyword_sequence_parts: tuple[str, ...],
) -> tuple[str, ...]:
    normalized = _normalize_source_keyword_sequence(value)
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


def is_known_source_keyword_sequence(
    value: str, *, source_keyword_sequence_parts: tuple[str, ...]
) -> bool:
    """Require the entire qualifier to be a conjunction of known keyword terms."""
    return bool(
        _split_source_keyword_sequence(
            _normalize_source_keyword_sequence(value),
            source_keyword_sequence_parts=source_keyword_sequence_parts,
            allow_unknown_tail=False,
        )
    )


def _normalize_source_keyword_sequence(value: str) -> str:
    return " ".join(value.strip().upper().replace("-", " ").split())


def _split_source_keyword_sequence(
    value: str,
    *,
    source_keyword_sequence_parts: tuple[str, ...],
    allow_unknown_tail: bool = True,
) -> tuple[str, ...]:
    remaining = value
    tokens: list[str] = []
    while remaining:
        match = _longest_source_keyword_prefix(
            remaining,
            source_keyword_sequence_parts=source_keyword_sequence_parts,
        )
        if match is None:
            if not allow_unknown_tail:
                return ()
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
    spellings = {
        spelling
        for keyword in source_keyword_sequence_parts
        for spelling in keyword_number_spellings(keyword)
    }
    for keyword in sorted(spellings, key=lambda token: (-len(token), token)):
        if value == keyword or value.startswith(f"{keyword} "):
            return keyword
    return None
