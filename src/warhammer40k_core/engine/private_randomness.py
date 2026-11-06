"""Operator-only game entropy, persisted explicitly and never derived from public IDs."""

from __future__ import annotations

import secrets
from collections.abc import Mapping

from warhammer40k_core.engine.phase import GameLifecycleError


def new_private_rng_seed() -> str:
    return secrets.token_hex(32)


def validate_private_rng_seed(value: object, *, game_id: str | None = None) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise GameLifecycleError("Private RNG seed must be a 256-bit lowercase hexadecimal value.")
    if value == game_id:
        raise GameLifecycleError("Private RNG seed must differ from public game identity.")
    return value


def private_rng_seed_from_payload(payload: Mapping[str, object]) -> str:
    if "private_rng_seed" not in payload:
        raise GameLifecycleError(
            "Legacy game payload has no private RNG seed; "
            "public-identity seeded saves are unsupported."
        )
    game_id = payload["game_id"]
    if type(game_id) is not str:
        raise GameLifecycleError("Private RNG seed requires a valid game identity.")
    return validate_private_rng_seed(payload["private_rng_seed"], game_id=game_id)


def validate_private_rng_seed_pair(*, state_seed: str, config_seed: str) -> None:
    if state_seed != config_seed:
        raise GameLifecycleError("Lifecycle state private RNG seed does not match config.")


def validate_tactical_draw_sequence(value: object) -> int:
    if type(value) is not int or value < 0:
        raise GameLifecycleError("Private tactical draw sequence must be a nonnegative integer.")
    return value


def tactical_draw_sequence_from_payload(payload: Mapping[str, object]) -> int:
    if "tactical_secondary_draw_sequence" not in payload:
        raise GameLifecycleError("Game payload has no private tactical draw sequence.")
    return validate_tactical_draw_sequence(payload["tactical_secondary_draw_sequence"])
