"""Icon of Khorne: actual killing attack, one point, later native spend."""

from typing import cast

from tests.factions.world_eaters.gameplay_helpers import (
    ENEMY,
    SOURCE,
    complete_activation,
    events,
    gameplay_session,
    reach,
)
from tests.factions.world_eaters.world_eaters_helpers import _unit_by_id
from tests.fight_completion_positive_helpers import assert_completed_melee

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters import army_rule
from warhammer40k_core.engine.phase import LifecycleStatusKind


def test_icon_killing_attack_credits_one_point_then_next_blessings_spends_once() -> None:
    session = gameplay_session(game_id="we-icon-outcome-0", lethal=True)
    complete_activation(session, SOURCE)
    assert_completed_melee(session.lifecycle, unit_instance_id=SOURCE)
    state = session.lifecycle.state
    assert state is not None
    assert not _unit_by_id(state, ENEMY).own_models[0].is_alive
    decisions = session.lifecycle.decision_controller
    assert len(events(session, "model_destroyed")) == 1
    for _ in range(2):
        assert (
            army_rule.bloodshed_points_available(
                state, event_log=decisions.event_log, player_id="player-a"
            )
            == 1
        )
    request = reach(session, "select_faction_rule_battle_round_option", limit=80)
    assert state.battle_round == 2
    payload = cast(dict[str, JsonValue], request.payload)
    assert payload["bloodshed_points_spent"] == 1
    assert len(cast(list[JsonValue], payload["dice_values"])) == 9
    status = session.submit_option(
        request_id=request.request_id,
        result_id="we-icon-spend",
        option_id="world_eaters:blessings:none",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert (
        army_rule.bloodshed_points_available(
            state, event_log=decisions.event_log, player_id="player-a"
        )
        == 0
    )
    spent = events(session, "world_eaters_blessings_of_khorne_selected")
    assert len(spent) == 1
    assert spent[0]["bloodshed_points_spent"] == 1
