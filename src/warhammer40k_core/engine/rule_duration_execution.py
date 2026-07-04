from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    battle_phase_kind_from_token,
)
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_target_resolution import clause_requires_unit_target
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleDuration,
    RuleDurationKind,
    RuleParameterValue,
    parameter_payload,
)


class RuleDurationExecutionContext(Protocol):
    @property
    def state(self) -> GameState | None: ...

    @property
    def player_id(self) -> str: ...

    @property
    def battle_round(self) -> int: ...

    @property
    def phase(self) -> BattlePhaseKind | None: ...

    @property
    def active_player_id(self) -> str | None: ...


def expiration_for_duration(
    *,
    duration: RuleDuration,
    context: RuleDurationExecutionContext,
) -> EffectExpiration | None:
    if duration.kind is RuleDurationKind.IMMEDIATE:
        return None
    if duration.kind is RuleDurationKind.PERMANENT:
        return EffectExpiration.end_of_battle()
    parameters = parameter_payload(duration.parameters)
    endpoint = parameters.get("endpoint")
    if duration.kind is RuleDurationKind.UNTIL_TIMING_ENDPOINT:
        if endpoint == "phase":
            if context.phase is None:
                raise GameLifecycleError("Phase duration requires execution phase.")
            if parameters.get("relative") == "next":
                phase = _duration_phase_parameter(parameters)
                player_id = _duration_owner_player_id(parameters=parameters, context=context)
                battle_round = _relative_phase_battle_round(
                    context=context,
                    player_id=player_id,
                    phase=phase,
                )
                return _phase_expiration(
                    boundary=_duration_boundary(parameters),
                    battle_round=battle_round,
                    phase=phase,
                    player_id=player_id,
                )
            return EffectExpiration.end_phase(
                battle_round=context.battle_round,
                phase=context.phase,
                player_id=_current_active_player_id(context),
            )
        if endpoint == "turn":
            if parameters.get("relative") == "next":
                player_id = _duration_owner_player_id(parameters=parameters, context=context)
                return _turn_expiration(
                    boundary=_duration_boundary(parameters),
                    battle_round=_relative_turn_battle_round(
                        context=context,
                        player_id=player_id,
                        force_future=True,
                    ),
                    player_id=player_id,
                )
            owner = parameters.get("owner")
            if owner is not None:
                player_id = _duration_owner_player_id(parameters=parameters, context=context)
                return _turn_expiration(
                    boundary=_duration_boundary(parameters),
                    battle_round=_relative_turn_battle_round(
                        context=context,
                        player_id=player_id,
                        force_future=False,
                    ),
                    player_id=player_id,
                )
            return EffectExpiration.end_turn(
                battle_round=context.battle_round,
                player_id=_current_active_player_id(context),
            )
        if endpoint == "battle round":
            return EffectExpiration.end_battle_round(battle_round=context.battle_round)
        if endpoint == "battle":
            return EffectExpiration.end_of_battle()
        raise GameLifecycleError("Unsupported rule duration endpoint.")
    if duration.kind is RuleDurationKind.WHILE_CONDITION_TRUE:
        return None
    raise GameLifecycleError("Unsupported rule duration kind.")


def rule_duration_unavailable_reason(
    *,
    clause: RuleClause,
    context: RuleDurationExecutionContext,
) -> str | None:
    if clause.duration is None:
        return None
    if (
        clause.duration.kind is not RuleDurationKind.IMMEDIATE
        and clause_requires_unit_target(clause)
        and context.state is None
    ):
        return "missing_input:game_state"
    if clause.duration.kind is not RuleDurationKind.UNTIL_TIMING_ENDPOINT:
        return None
    parameters = parameter_payload(clause.duration.parameters)
    endpoint = parameters.get("endpoint")
    if endpoint in {"phase", "turn"} and context.active_player_id is None:
        return "missing_active_player"
    if (
        parameters.get("relative") == "next" or parameters.get("owner") is not None
    ) and context.state is None:
        return "missing_input:game_state"
    if endpoint == "phase" and context.phase is None:
        return "missing_phase"
    return None


def _duration_boundary(parameters: Mapping[str, RuleParameterValue]) -> str:
    boundary = parameters.get("boundary")
    if boundary is None:
        return "end"
    if type(boundary) is not str:
        raise GameLifecycleError("Rule duration boundary must be a string.")
    if boundary not in {"start", "end"}:
        raise GameLifecycleError("Unsupported rule duration boundary.")
    return boundary


def _duration_phase_parameter(parameters: Mapping[str, RuleParameterValue]) -> BattlePhaseKind:
    phase = parameters.get("phase")
    if type(phase) is not str:
        raise GameLifecycleError("Relative phase duration requires a phase parameter.")
    return battle_phase_kind_from_token(phase)


def _phase_expiration(
    *,
    boundary: str,
    battle_round: int,
    phase: BattlePhaseKind,
    player_id: str,
) -> EffectExpiration:
    if boundary == "start":
        return EffectExpiration.start_phase(
            battle_round=battle_round,
            phase=phase,
            player_id=player_id,
        )
    if boundary == "end":
        return EffectExpiration.end_phase(
            battle_round=battle_round,
            phase=phase,
            player_id=player_id,
        )
    raise GameLifecycleError("Unsupported rule duration boundary.")


def _turn_expiration(*, boundary: str, battle_round: int, player_id: str) -> EffectExpiration:
    if boundary == "start":
        return EffectExpiration.start_turn(battle_round=battle_round, player_id=player_id)
    if boundary == "end":
        return EffectExpiration.end_turn(battle_round=battle_round, player_id=player_id)
    raise GameLifecycleError("Unsupported rule duration boundary.")


def _duration_owner_player_id(
    *,
    parameters: Mapping[str, RuleParameterValue],
    context: RuleDurationExecutionContext,
) -> str:
    owner = parameters.get("owner")
    if owner is None or owner == "self":
        return context.player_id
    if owner != "opponent":
        raise GameLifecycleError("Unsupported rule duration owner.")
    state = _require_state(context)
    opponents = tuple(player_id for player_id in state.player_ids if player_id != context.player_id)
    if len(opponents) != 1:
        raise GameLifecycleError("Opponent-relative duration requires exactly one opponent.")
    return opponents[0]


def _current_active_player_id(context: RuleDurationExecutionContext) -> str:
    if context.active_player_id is None:
        raise GameLifecycleError("Current duration endpoint requires active_player_id.")
    return context.active_player_id


def _relative_turn_battle_round(
    *,
    context: RuleDurationExecutionContext,
    player_id: str,
    force_future: bool,
) -> int:
    state = _require_state(context)
    active_player_id = _current_active_player_id(context)
    active_index = state.turn_order.index(active_player_id)
    player_index = state.turn_order.index(player_id)
    if force_future:
        if player_index > active_index:
            return context.battle_round
        return context.battle_round + 1
    if player_index >= active_index:
        return context.battle_round
    return context.battle_round + 1


def _relative_phase_battle_round(
    *,
    context: RuleDurationExecutionContext,
    player_id: str,
    phase: BattlePhaseKind,
) -> int:
    state = _require_state(context)
    active_player_id = _current_active_player_id(context)
    active_index = state.turn_order.index(active_player_id)
    player_index = state.turn_order.index(player_id)
    if player_index > active_index:
        return context.battle_round
    if player_index < active_index:
        return context.battle_round + 1
    if context.phase is None:
        raise GameLifecycleError("Relative phase duration requires execution phase.")
    current_phase_index = state.battle_phase_sequence.index(context.phase)
    target_phase_index = state.battle_phase_sequence.index(phase)
    if target_phase_index > current_phase_index:
        return context.battle_round
    return context.battle_round + 1


def _require_state(context: RuleDurationExecutionContext) -> GameState:
    state = context.state
    if state is None:
        raise GameLifecycleError("Rule duration execution requires game_state.")
    return state
