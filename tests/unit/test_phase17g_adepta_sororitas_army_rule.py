from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest
from tests.unit.test_phase11c_command_phase import (
    _battle_state,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_round_hooks import (
    BattleRoundStartHookRegistry,
    BattleRoundStartRequestContext,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adepta_sororitas import (
    army_rule,
)
from warhammer40k_core.engine.game_state import GameState, GameStatePayload
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext
from warhammer40k_core.engine.unit_factory import UnitInstance


def test_battle_round_start_gains_miracle_die_once_for_adepta_army() -> None:
    state = _battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-a")
    decisions = DecisionController()
    registry = BattleRoundStartHookRegistry.from_bindings(
        army_rule.runtime_contribution().battle_round_start_hook_bindings
    )

    request = registry.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )

    assert request is None
    pool = army_rule.miracle_dice_pool(state, player_id="player-a")
    assert len(pool) == 1
    assert 1 <= pool[0].value <= 6
    assert pool[0].roll_state.original_result.spec.roll_type == (
        army_rule.MIRACLE_DIE_GAIN_ROLL_TYPE
    )
    assert pool[0].roll_state.original_result.spec.reroll_forbidden_rule_ids == (
        army_rule.SOURCE_RULE_ID,
    )
    payload = _last_event_payload(decisions, army_rule.MIRACLE_DIE_GAINED_EVENT)
    assert payload["player_id"] == "player-a"
    assert payload["trigger"] == army_rule.BATTLE_ROUND_START_TRIGGER
    assert _dice_roll_count(decisions) == 1

    second_request = registry.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )

    assert second_request is None
    assert len(army_rule.miracle_dice_pool(state, player_id="player-a")) == 1
    assert _dice_roll_count(decisions) == 1


def test_battle_round_start_ignores_non_adepta_armies() -> None:
    state = _battle_state()
    decisions = DecisionController()
    registry = BattleRoundStartHookRegistry.from_bindings(
        army_rule.runtime_contribution().battle_round_start_hook_bindings
    )

    request = registry.next_request_for(
        BattleRoundStartRequestContext(state=state, decisions=decisions)
    )

    assert request is None
    assert army_rule.miracle_dice_pool(state, player_id="player-a") == ()
    assert _event_payloads(decisions, army_rule.MIRACLE_DIE_GAINED_EVENT) == ()


def test_destroyed_adepta_sororitas_unit_gains_miracle_die_for_owner() -> None:
    state = _battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-b")
    target_unit = _unit_for_player(state, player_id="player-b")
    decisions = DecisionController()
    destroyed_event = _append_destroyed_model_event(
        state=state,
        decisions=decisions,
        destroying_player_id="player-a",
        target_unit=target_unit,
    )
    context = UnitDestroyedContext(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.SHOOTING,
        model_destroyed_event_id=destroyed_event.event_id,
        model_destroyed_payload=cast(dict[str, JsonValue], destroyed_event.payload),
        destroying_player_id="player-a",
        destroyed_unit_instance_id=target_unit.unit_instance_id,
        destroyed_player_id="player-b",
    )

    army_rule.resolve_adepta_sororitas_unit_destroyed(context)

    pool = army_rule.miracle_dice_pool(state, player_id="player-b")
    assert len(pool) == 1
    assert army_rule.miracle_dice_pool(state, player_id="player-a") == ()
    payload = _last_event_payload(decisions, army_rule.MIRACLE_DIE_GAINED_EVENT)
    assert payload["player_id"] == "player-b"
    assert payload["trigger"] == army_rule.UNIT_DESTROYED_TRIGGER
    source_context = cast(dict[str, JsonValue], payload["source_context"])
    assert source_context["destroyed_unit_instance_id"] == target_unit.unit_instance_id
    assert source_context["model_destroyed_event_id"] == destroyed_event.event_id

    army_rule.resolve_adepta_sororitas_unit_destroyed(context)

    assert len(army_rule.miracle_dice_pool(state, player_id="player-b")) == 1


def test_destroyed_non_adepta_unit_in_adepta_army_does_not_gain_miracle_die() -> None:
    state = _battle_state()
    _mark_player_as_adepta_sororitas(
        state,
        player_id="player-b",
        faction_keywords=("AGENTS OF THE IMPERIUM",),
    )
    target_unit = _unit_for_player(state, player_id="player-b")
    decisions = DecisionController()
    destroyed_event = _append_destroyed_model_event(
        state=state,
        decisions=decisions,
        destroying_player_id="player-a",
        target_unit=target_unit,
    )

    army_rule.resolve_adepta_sororitas_unit_destroyed(
        UnitDestroyedContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.SHOOTING,
            model_destroyed_event_id=destroyed_event.event_id,
            model_destroyed_payload=cast(dict[str, JsonValue], destroyed_event.payload),
            destroying_player_id="player-a",
            destroyed_unit_instance_id=target_unit.unit_instance_id,
            destroyed_player_id="player-b",
        )
    )

    assert army_rule.miracle_dice_pool(state, player_id="player-b") == ()
    assert _event_payloads(decisions, army_rule.MIRACLE_DIE_GAINED_EVENT) == ()


def test_miracle_die_pool_spend_and_game_state_payload_round_trip() -> None:
    state = _battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-a")
    decisions = DecisionController()
    die = army_rule.gain_miracle_die(
        state,
        decisions,
        player_id="player-a",
        trigger=army_rule.BATTLE_ROUND_START_TRIGGER,
        source_id="phase17g-adepta-test:manual-gain",
        source_context={"test": "manual"},
    )
    assert die is not None

    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    spent = army_rule.spend_miracle_die(
        state,
        decisions,
        player_id="player-a",
        miracle_die_id=die.miracle_die_id,
        source_id="phase17g-adepta-test:manual-spend",
        source_context={"test": "manual"},
    )
    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    )

    assert spent == die
    assert army_rule.miracle_dice_pool(state, player_id="player-a") == ()
    assert army_rule.miracle_dice_pool(restored, player_id="player-a") == ()
    payload = _last_event_payload(decisions, army_rule.MIRACLE_DIE_SPENT_EVENT)
    miracle_die_payload = cast(dict[str, JsonValue], payload["miracle_die"])
    assert miracle_die_payload["miracle_die_id"] == die.miracle_die_id
    assert payload["phase"] == BattlePhase.SHOOTING.value

    with pytest.raises(GameLifecycleError, match="not available"):
        army_rule.spend_miracle_die(
            state,
            decisions,
            player_id="player-a",
            miracle_die_id=die.miracle_die_id,
            source_id="phase17g-adepta-test:manual-spend-again",
            source_context={"test": "manual"},
        )


def test_acts_of_faith_runtime_contribution_exposes_hooks() -> None:
    contribution = army_rule.runtime_contribution()

    assert contribution.contribution_id == army_rule.CONTRIBUTION_ID
    assert tuple(binding.hook_id for binding in contribution.battle_round_start_hook_bindings) == (
        army_rule.BATTLE_ROUND_START_HOOK_ID,
    )
    assert tuple(binding.hook_id for binding in contribution.unit_destroyed_hook_bindings) == (
        army_rule.UNIT_DESTROYED_HOOK_ID,
    )


def test_acts_of_faith_handlers_fail_fast_on_malformed_inputs() -> None:
    state = _battle_state()
    _mark_player_as_adepta_sororitas(state, player_id="player-a")
    decisions = DecisionController()

    invalid_cases: tuple[Callable[[], object], ...] = (
        lambda: army_rule.resolve_battle_round_start(
            cast(BattleRoundStartRequestContext, object())
        ),
        lambda: army_rule.resolve_adepta_sororitas_unit_destroyed(
            cast(UnitDestroyedContext, object())
        ),
        lambda: army_rule.gain_miracle_die(
            cast(GameState, object()),
            decisions,
            player_id="player-a",
            trigger=army_rule.BATTLE_ROUND_START_TRIGGER,
            source_id="phase17g-adepta-test:invalid-state",
            source_context={},
        ),
        lambda: army_rule.gain_miracle_die(
            state,
            decisions,
            player_id="player-a",
            trigger="unsupported_trigger",
            source_id="phase17g-adepta-test:invalid-trigger",
            source_context={},
        ),
        lambda: army_rule.spend_miracle_die(
            state,
            decisions,
            player_id="player-a",
            miracle_die_id="missing-die",
            source_id="phase17g-adepta-test:missing-spend",
            source_context={},
        ),
    )
    for invalid_case in invalid_cases:
        with pytest.raises(GameLifecycleError):
            invalid_case()


def _mark_player_as_adepta_sororitas(
    state: GameState,
    *,
    player_id: str,
    faction_keywords: tuple[str, ...] = (army_rule.ADEPTA_SORORITAS_FACTION_KEYWORD,),
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_armies.append(
            replace(
                army,
                detachment_selection=replace(
                    army.detachment_selection,
                    faction_id=army_rule.ADEPTA_SORORITAS_FACTION_ID,
                ),
                units=tuple(
                    replace(
                        unit,
                        faction_keywords=faction_keywords,
                    )
                    for unit in army.units
                ),
            )
        )
    state.army_definitions = updated_armies


def _unit_for_player(state: GameState, *, player_id: str) -> UnitInstance:
    army = state.army_definition_for_player(player_id)
    if army is None:
        raise AssertionError(f"Missing army for {player_id}.")
    return army.units[0]


def _append_destroyed_model_event(
    *,
    state: GameState,
    decisions: DecisionController,
    destroying_player_id: str,
    target_unit: UnitInstance,
) -> EventRecord:
    return decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            "destroying_player_id": destroying_player_id,
            "target_unit_instance_id": target_unit.unit_instance_id,
            "model_instance_id": target_unit.own_models[-1].model_instance_id,
        },
    )


def _event_payloads(
    decisions: DecisionController,
    event_type: str,
) -> tuple[dict[str, JsonValue], ...]:
    return tuple(
        cast(dict[str, JsonValue], event.payload)
        for event in decisions.event_log.records
        if event.event_type == event_type
    )


def _last_event_payload(decisions: DecisionController, event_type: str) -> dict[str, JsonValue]:
    events = _event_payloads(decisions, event_type)
    if not events:
        raise AssertionError(f"Missing event {event_type}.")
    return events[-1]


def _dice_roll_count(decisions: DecisionController) -> int:
    return sum(1 for event in decisions.event_log.records if event.event_type == "dice_rolled")
