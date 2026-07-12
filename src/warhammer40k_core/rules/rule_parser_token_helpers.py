from __future__ import annotations

import re

from warhammer40k_core.core.weapon_profiles import canonical_weapon_keyword_tokens
from warhammer40k_core.rules.rule_ir import RuleIRError


def owner_token(owner: str | None) -> str | None:
    if owner is None:
        return None
    lowered = owner.lower()
    if "opponent" in lowered:
        return "opponent"
    if lowered == "your":
        return "active_player"
    return None


def battle_round_number(value: str) -> int:
    token = value.lower().strip()
    ordinal_numbers = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
    }
    ordinal = ordinal_numbers.get(token)
    if ordinal is not None:
        return ordinal
    suffixes = ("st", "nd", "rd", "th")
    for suffix in suffixes:
        if token.endswith(suffix):
            token = token[: -len(suffix)]
            break
    if token.isdecimal():
        return int(token)
    raise RuleIRError(f"Unsupported battle round ordinal in rule language: {value}.")


def roll_type(value: str) -> str:
    return value.lower().replace("-", "_").replace(" ", "_")


def subject_token(value: str) -> str:
    return value.lower().replace(" ", "_").replace("-", "_")


def post_shoot_subject_token(value: str) -> str:
    token = subject_token(value.removeprefix("the "))
    if token in {"bearer", "this_model", "this_unit"}:
        return token
    raise RuleIRError(f"Unsupported post-shoot subject in rule language: {value}.")


def contextual_status_target_scope_token(match: re.Match[str]) -> str:
    subject = subject_token(match.group("subject").removeprefix("the "))
    if subject.startswith("models_in_"):
        return "models_in_selected_unit"
    if subject in {"that_enemy_unit", "that_unit", "selected_unit", "target_unit"}:
        return "selected_unit"
    raise RuleIRError(f"Unsupported contextual status target in rule language: {subject}.")


def range_kind_token(value: str) -> str:
    stripped = value.strip()
    if stripped.endswith('"'):
        return "numeric_range"
    return stripped.lower().replace(" ", "_").replace("-", "_")


def object_kind_token(value: str) -> str:
    normalized = value.lower().replace(" ", "_").replace("-", "_")
    if normalized in {"units", "unit"}:
        return "unit"
    if normalized in {"models", "model"}:
        return "model"
    if normalized in {"objective_markers", "objective_marker"}:
        return "objective_marker"
    raise RuleIRError(f"Unsupported distance relation object kind: {value}.")


def quantity_token(value: str) -> str:
    return value.lower().replace(" ", "_").replace("-", "_")


def ability_token(value: str) -> str:
    stripped = value.strip(" []().,;:")
    return " ".join(stripped.split())


def is_weapon_keyword(value: str) -> bool:
    return value.lower() in {keyword.lower() for keyword in canonical_weapon_keyword_tokens()}


def catalog_like_token(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")
