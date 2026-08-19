from __future__ import annotations

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_scoring_departure_conditions import (
    CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
)
from warhammer40k_core.engine.primary_scoring_timing import primary_scoring_timing_applies

OWN_PLAYER_TURN = "own_player_turn"
ANY_PLAYER_TURN = "any_player_turn"

SUPPORTED_PRIMARY_SCORING_TURN_SCOPES = frozenset({OWN_PLAYER_TURN, ANY_PLAYER_TURN})

PRIMARY_SCORING_ANY_PLAYER_TURN_CONDITIONS = frozenset(
    {
        CONDEMNED_ENEMY_UNITS_LEFT_BATTLEFIELD_THIS_TURN,
    }
)


def primary_scoring_turn_scope_for_condition(condition: str) -> str:
    condition_id = _identifier("Primary scoring condition", condition)
    if condition_id in PRIMARY_SCORING_ANY_PLAYER_TURN_CONDITIONS:
        return ANY_PLAYER_TURN
    return OWN_PLAYER_TURN


def primary_scoring_turn_scope_applies(
    *,
    turn_scope: str,
    scoring_player_id: str,
    active_player_id: str,
    end_of_battle: bool,
) -> bool:
    requested_scope = _identifier("Primary scoring turn_scope", turn_scope)
    if requested_scope not in SUPPORTED_PRIMARY_SCORING_TURN_SCOPES:
        raise GameLifecycleError("Unsupported primary scoring turn_scope.")
    if type(end_of_battle) is not bool:
        raise GameLifecycleError("Primary scoring end_of_battle must be a bool.")
    scoring_player = _identifier("Primary scoring player_id", scoring_player_id)
    active_player = _identifier("Primary scoring active_player_id", active_player_id)
    if end_of_battle or requested_scope == ANY_PLAYER_TURN:
        return True
    return scoring_player == active_player


def primary_scoring_rule_applies_at_record(
    *,
    timing: str,
    condition: str,
    record: ObjectiveControlRecord,
    scoring_player_id: str,
    primary_scoring_phase: str,
    primary_scoring_timing: ObjectiveControlTiming,
    game_length_battle_rounds: int,
    end_of_battle: bool,
) -> bool:
    if type(record) is not ObjectiveControlRecord:
        raise GameLifecycleError(
            "Primary scoring rule application requires ObjectiveControlRecord."
        )
    if not primary_scoring_timing_applies(
        timing=timing,
        battle_round=record.battle_round,
        phase=record.phase,
        objective_control_timing=record.timing,
        primary_scoring_phase=primary_scoring_phase,
        primary_scoring_timing=primary_scoring_timing,
        game_length_battle_rounds=game_length_battle_rounds,
        end_of_battle=end_of_battle,
    ):
        return False
    return primary_scoring_turn_scope_applies(
        turn_scope=primary_scoring_turn_scope_for_condition(condition),
        scoring_player_id=scoring_player_id,
        active_player_id=record.active_player_id,
        end_of_battle=end_of_battle,
    )


_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "ANY_PLAYER_TURN",
    "OWN_PLAYER_TURN",
    "PRIMARY_SCORING_ANY_PLAYER_TURN_CONDITIONS",
    "SUPPORTED_PRIMARY_SCORING_TURN_SCOPES",
    "primary_scoring_rule_applies_at_record",
    "primary_scoring_turn_scope_applies",
    "primary_scoring_turn_scope_for_condition",
)
