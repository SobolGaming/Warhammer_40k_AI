from __future__ import annotations

from typing import cast

from tests.factions.world_eaters.world_eaters_helpers import (
    ENEMY_UNIT_ID,
    WORLD_EATERS_UNIT_ID,
    _append_model_destroyed_event,
    _battle_ready_lifecycle,
    _battle_ready_state,
    _cloned_battle_ready_state,
    _destroy_enemy_unit,
    _icon_bearer_model_id,
    _remove_models,
    _require_state,
)

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters import (
    army_rule,
)


def test_icon_of_khorne_bloodshed_points_require_live_bearer() -> None:
    live_state = _battle_ready_state()
    live_decisions = DecisionController()
    _destroy_enemy_unit(
        state=live_state,
        decisions=live_decisions,
        attacking_unit_id=WORLD_EATERS_UNIT_ID,
    )

    assert (
        army_rule.bloodshed_points_available(
            live_state,
            event_log=live_decisions.event_log,
            player_id="player-a",
        )
        == 1
    )

    destroyed_state = _battle_ready_state()
    destroyed_decisions = DecisionController()
    icon_bearer_id = _icon_bearer_model_id(destroyed_state)
    _remove_models(destroyed_state, (icon_bearer_id,))
    _append_model_destroyed_event(
        state=destroyed_state,
        decisions=destroyed_decisions,
        destroying_player_id="player-b",
        attacking_unit_id=ENEMY_UNIT_ID,
        target_unit_id=WORLD_EATERS_UNIT_ID,
        model_instance_id=icon_bearer_id,
        event_suffix="icon-bearer",
    )
    _destroy_enemy_unit(
        state=destroyed_state,
        decisions=destroyed_decisions,
        attacking_unit_id=WORLD_EATERS_UNIT_ID,
    )

    assert (
        army_rule.bloodshed_points_available(
            destroyed_state,
            event_log=destroyed_decisions.event_log,
            player_id="player-a",
        )
        == 0
    )


def test_bloodshed_points_add_blessings_roll_dice() -> None:
    lifecycle = _battle_ready_lifecycle()
    state = _require_state(lifecycle)
    _destroy_enemy_unit(
        state=state,
        decisions=lifecycle.decision_controller,
        attacking_unit_id=WORLD_EATERS_UNIT_ID,
    )

    status = lifecycle.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    payload = cast(dict[str, JsonValue], request.payload)
    assert payload["bloodshed_points_spent"] == 1
    assert len(cast(list[JsonValue], payload["dice_values"])) == 9


def test_bloodshed_points_require_world_eaters_and_battlefield() -> None:
    state = _battle_ready_state()

    assert (
        army_rule.bloodshed_points_available(
            state,
            event_log=DecisionController().event_log,
            player_id="player-b",
        )
        == 0
    )

    state_without_battlefield = _cloned_battle_ready_state()
    state_without_battlefield.battlefield_state = None
    assert (
        army_rule.bloodshed_points_available(
            state_without_battlefield,
            event_log=DecisionController().event_log,
            player_id="player-a",
        )
        == 0
    )
