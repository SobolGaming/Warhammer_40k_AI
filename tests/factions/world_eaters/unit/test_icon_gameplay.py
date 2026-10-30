"""Icon of Khorne: actual killing attack, one point, later native spend."""

from typing import cast

import pytest
from tests.factions.world_eaters.gameplay_helpers import (
    ENEMY,
    SOURCE,
    attached_gameplay_session,
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
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner


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


@pytest.mark.parametrize("icon", [True, False])
def test_attached_leader_kill_credits_bodyguard_icon_once_and_spends(icon: bool) -> None:
    session = attached_gameplay_session(game_id="we-attached-icon-1", icon=icon)
    source_id = "attached-unit:army-alpha:bodyguard"
    complete_activation(session, source_id)
    assert_completed_melee(session.lifecycle, unit_instance_id=source_id)
    state = session.lifecycle.state
    assert state is not None
    assert not _unit_by_id(state, ENEMY).own_models[0].is_alive
    destroyed = events(session, "model_destroyed")
    assert len(destroyed) == 1
    assert destroyed[0]["source_rules_unit_instance_id"] == source_id
    assert cast(str, destroyed[0]["source_model_instance_id"]).startswith("army-alpha:leader:")
    decisions = session.lifecycle.decision_controller
    assert army_rule.bloodshed_points_available(
        state, event_log=decisions.event_log, player_id="player-a"
    ) == int(icon)
    request = reach(session, "select_faction_rule_battle_round_option", limit=80)
    payload = cast(dict[str, JsonValue], request.payload)
    assert payload["bloodshed_points_spent"] == int(icon)
    assert len(cast(list[JsonValue], payload["dice_values"])) == 8 + int(icon)
    status = session.submit_option(
        request_id=request.request_id,
        result_id="we-attached-spend",
        option_id="world_eaters:blessings:none",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert (
        army_rule.bloodshed_points_available(
            state, event_log=decisions.event_log, player_id="player-a"
        )
        == 0
    )

    replay = ReplayRunner(
        ReplayArtifact.from_payload(session.replay_artifact(artifact_id="we-attached-icon"))
    ).run()
    assert replay.reproduced_exactly, replay


@pytest.mark.parametrize("destroy_before_kill", [True, False])
def test_icon_credit_preserves_casualty_order_after_bodyguard_destruction(
    destroy_before_kill: bool,
) -> None:
    from tests.destruction_occurrence_fixture_helpers import destroy_rule_model_for_fixture

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    session = attached_gameplay_session(
        game_id="we-attached-icon-before-0" if destroy_before_kill else "we-attached-icon-1"
    )
    state = session.lifecycle.state
    assert state is not None
    decisions = session.lifecycle.decision_controller

    def remove_bodyguards() -> None:
        for model in _unit_by_id(state, "army-alpha:bodyguard").own_models:
            destroy_rule_model_for_fixture(
                state=state,
                decisions=decisions,
                model_id=model.model_instance_id,
                destroying_player_id="player-b",
                source_unit_id=ENEMY,
                source_model_id=_unit_by_id(state, ENEMY).own_models[0].model_instance_id,
            )

    if destroy_before_kill:
        remove_bodyguards()
    source_id = rules_unit_view_by_id(
        state=state, unit_instance_id="army-alpha:leader"
    ).unit_instance_id
    complete_activation(session, source_id)
    assert not _unit_by_id(state, ENEMY).own_models[0].is_alive
    if not destroy_before_kill:
        remove_bodyguards()
    assert (
        rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader").unit_instance_id
        == "attached-unit:army-alpha:bodyguard"
    )
    assert army_rule.bloodshed_points_available(
        state, event_log=decisions.event_log, player_id="player-a"
    ) == int(not destroy_before_kill)
    checkpoint = session.lifecycle.to_payload()
    restored = GameLifecycle.from_payload(checkpoint)
    assert restored.to_payload() == checkpoint
    assert restored.state is not None
    assert army_rule.bloodshed_points_available(
        restored.state, event_log=restored.decision_controller.event_log, player_id="player-a"
    ) == int(not destroy_before_kill)
