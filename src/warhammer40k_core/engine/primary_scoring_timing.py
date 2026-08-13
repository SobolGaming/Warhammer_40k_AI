from __future__ import annotations

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

SUPPORTED_PRIMARY_SCORING_TIMINGS = frozenset(
    {
        "battle_round_four_onwards_turn_end",
        "battle_rounds_two_and_three_command_phase",
        "command_phase",
        "command_phase_or_round_five_turn_end",
        "end_of_battle",
        "first_and_second_battle_round_turn_end",
        "first_battle_round_turn_end",
        "turn_end",
        "turn_end_from_battle_round_two",
    }
)


def primary_scoring_timing_applies(
    *,
    timing: str,
    battle_round: int,
    phase: str,
    objective_control_timing: ObjectiveControlTiming,
    primary_scoring_phase: str,
    primary_scoring_timing: ObjectiveControlTiming,
    game_length_battle_rounds: int,
    end_of_battle: bool,
) -> bool:
    """Return whether one source timing token applies at an authoritative boundary."""

    requested_timing = _validate_identifier("Primary scoring timing", timing)
    if requested_timing not in SUPPORTED_PRIMARY_SCORING_TIMINGS:
        raise GameLifecycleError("Unsupported primary scoring rule timing.")
    requested_round = _validate_battle_round(
        battle_round=battle_round,
        game_length_battle_rounds=game_length_battle_rounds,
    )
    requested_phase = _validate_identifier("Primary scoring phase", phase)
    configured_command_phase = _validate_identifier(
        "Primary scoring configured phase",
        primary_scoring_phase,
    )
    boundary_timing = _objective_control_timing(objective_control_timing)
    configured_command_timing = _objective_control_timing(primary_scoring_timing)
    requested_end_of_battle = _validate_bool("Primary scoring end_of_battle", end_of_battle)
    is_turn_end = boundary_timing is ObjectiveControlTiming.TURN_END
    if is_turn_end and requested_phase != BattlePhase.FIGHT.value:
        raise GameLifecycleError("Primary scoring TURN_END boundary must be a Fight phase record.")

    if requested_end_of_battle:
        if requested_round != game_length_battle_rounds or not is_turn_end:
            raise GameLifecycleError(
                "Primary scoring end-of-battle context requires the final battle-round "
                "TURN_END boundary."
            )
        return requested_timing == "end_of_battle"
    if requested_timing == "end_of_battle":
        return False

    is_command_boundary = (
        requested_phase == configured_command_phase and boundary_timing is configured_command_timing
    )

    if requested_timing == "command_phase":
        return is_command_boundary
    if requested_timing == "turn_end":
        return is_turn_end
    if requested_timing == "turn_end_from_battle_round_two":
        return requested_round >= 2 and is_turn_end
    if requested_timing == "command_phase_or_round_five_turn_end":
        if game_length_battle_rounds != 5:
            raise GameLifecycleError(
                "Primary scoring round-five timing requires a five-battle-round game."
            )
        return (2 <= requested_round < 5 and is_command_boundary) or (
            requested_round == 5 and is_turn_end
        )
    if requested_timing == "first_and_second_battle_round_turn_end":
        return requested_round in {1, 2} and is_turn_end
    if requested_timing == "first_battle_round_turn_end":
        return requested_round == 1 and is_turn_end
    if requested_timing == "battle_rounds_two_and_three_command_phase":
        return requested_round in {2, 3} and is_command_boundary
    if requested_timing == "battle_round_four_onwards_turn_end":
        return requested_round >= 4 and is_turn_end
    raise GameLifecycleError("Unsupported primary scoring rule timing.")


def _validate_battle_round(*, battle_round: object, game_length_battle_rounds: object) -> int:
    if type(game_length_battle_rounds) is not int or game_length_battle_rounds < 1:
        raise GameLifecycleError(
            "Primary scoring game_length_battle_rounds must be a positive integer."
        )
    if type(battle_round) is not int or not 1 <= battle_round <= game_length_battle_rounds:
        raise GameLifecycleError("Primary scoring battle_round is outside the battle.")
    return battle_round


def _objective_control_timing(value: object) -> ObjectiveControlTiming:
    if type(value) is not ObjectiveControlTiming:
        raise GameLifecycleError(
            "Primary scoring objective_control_timing must be ObjectiveControlTiming."
        )
    return value


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "SUPPORTED_PRIMARY_SCORING_TIMINGS",
    "primary_scoring_timing_applies",
)
