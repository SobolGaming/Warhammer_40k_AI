from __future__ import annotations

import re

from warhammer40k_core.rules.rule_ir import RuleIRError


def keyword_token(value: str) -> str:
    return value.strip().upper().replace(" ", "_").replace("-", "_")


def keyword_any_tokens(value: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for raw_token in re.split(r"\s+or\s+|\s*,\s*", value.strip(), flags=re.IGNORECASE):
        token = raw_token.strip()
        if token:
            tokens.append(keyword_token(token))
    if not tokens:
        raise RuleIRError("Keyword any gate must contain at least one keyword.")
    return tuple(dict.fromkeys(tokens))


def model_keyword_any_token(first: str, second: str) -> tuple[str, ...]:
    tokens = tuple(dict.fromkeys((singular_keyword_token(first), singular_keyword_token(second))))
    if len(tokens) != 2:
        raise RuleIRError("Model keyword-any token requires two distinct keywords.")
    return tuple(sorted(tokens))


def movement_modes_token(value: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for raw_token in re.split(r"\s+or\s+|\s+and\s+|\s*,\s*", value.strip(), flags=re.IGNORECASE):
        token = raw_token.strip()
        if token:
            tokens.append(token.lower().replace(" ", "_").replace("-", "_"))
    if not tokens:
        raise RuleIRError("Movement modes token must contain at least one mode.")
    unique_tokens = tuple(dict.fromkeys(tokens))
    allowed_tokens = {"advance", "fall_back", "normal"}
    if not set(unique_tokens).issubset(allowed_tokens):
        raise RuleIRError("Movement modes token contains unsupported movement modes.")
    return tuple(sorted(unique_tokens))


def keyword_list_tokens(value: str) -> tuple[str, ...]:
    tokens: list[str] = []
    for raw_token in re.split(r"\s+or\s+|\s+and\s+|\s*,\s*", value.strip(), flags=re.IGNORECASE):
        token = raw_token.strip()
        if token:
            tokens.append(singular_keyword_token(token))
    if not tokens:
        raise RuleIRError("Keyword list gate must contain at least one keyword.")
    return tuple(dict.fromkeys(tokens))


def singular_keyword_token(value: str) -> str:
    token = keyword_token(value)
    if token == "TITANIC_MODELS":
        return "TITANIC"
    if token in {"CHARACTERS", "MONSTERS", "VEHICLES"}:
        return token[:-1]
    return token
