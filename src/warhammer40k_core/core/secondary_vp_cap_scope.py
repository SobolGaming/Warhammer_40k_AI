from __future__ import annotations

from enum import StrEnum


class SecondaryVictoryPointCapScope(StrEnum):
    PLAYER_TURN = "player_turn"
    BATTLE_ROUND = "battle_round"


def secondary_vp_cap_scope_from_token(
    token: object, *, error_type: type[Exception]
) -> SecondaryVictoryPointCapScope:
    if isinstance(token, SecondaryVictoryPointCapScope):
        return token
    if type(token) is str:
        for scope in SecondaryVictoryPointCapScope:
            if token == scope.value:
                return scope
    raise error_type("Secondary VP cap scope must be player_turn or battle_round.")
