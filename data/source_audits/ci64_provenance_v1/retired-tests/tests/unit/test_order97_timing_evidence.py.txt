"""Non-empty source-owned timing evidence across both players' phase boundaries."""

from __future__ import annotations

import json
from typing import cast

import pytest
from tests.core_clause_evidence_helpers import assert_persistence_viewers_replay
from tests.support.ability_presence_fixtures import ability_presence_fixture

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.stratagems import stratagem_decline_payload


@pytest.mark.parametrize("edge", ["start", "end"])
def test_loaded_command_boundary_rule_repeats_on_its_owners_turn_each_round(
    edge: str,
) -> None:
    config, state, decisions = ability_presence_fixture(
        embarked=False,
        ability_text=f"At the {edge} of your Command phase, roll one D6: on a 1+, you gain 1CP.",
    )
    session = LocalGameSession(
        GameLifecycle.from_payload(
            cast(
                GameLifecyclePayload,
                {
                    "config": config.to_payload(),
                    "state": state.to_payload(),
                    "decisions": decisions.to_payload(),
                    "reaction_queue": ReactionQueue().to_payload(),
                    "parameterized_movement_proposals": True,
                },
            )
        )
    )
    for index in range(150):
        status = session.advance_until_decision_or_terminal()
        current = session.lifecycle.state
        assert current is not None
        if current.battle_round == 3:
            break
        request = status.decision_request
        assert request is not None
        if request.decision_type == "submit_stratagem_target_proposal":
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"order97-timing-{index}",
                payload=stratagem_decline_payload(),
            )
        else:
            options = tuple(
                option
                for option in request.options
                if option.option_id.startswith("complete_")
                or option.option_id in {"remain_stationary", "decline"}
            )
            option = options[0] if options else request.options[0]
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"order97-timing-{index}",
                option_id=option.option_id,
            )
        assert status.status_kind not in {
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }, status
        if index == 7:
            session = LocalGameSession.from_persistence_payload(
                json.loads(json.dumps(session.to_persistence_payload()))
            )
    current = session.lifecycle.state
    assert current is not None
    assert current.battle_round == 3
    events = session.lifecycle.decision_controller.event_log.records
    resolved = [
        cast(dict[str, JsonValue], event.payload)
        for event in events
        if event.event_type == "catalog_ir_command_point_phase_gain_resolved"
    ]
    assert len(resolved) == 3, resolved
    assert [row["battle_round"] for row in resolved] == [1, 2, 3]
    assert all(row["player_id"] == "player-a" for row in resolved)
    assert all(row["phase"] == BattlePhase.COMMAND.value for row in resolved)
    assert_persistence_viewers_replay(session)


def test_loaded_unqualified_fight_trigger_repeats_on_both_players_turns() -> None:
    config, state, decisions = ability_presence_fixture(
        embarked=False,
        ability_text=(
            'At the start of the Fight phase, select one enemy unit within 100" of this model. '
            "Until the end of the phase, each time this model makes a melee attack that "
            "targets that unit, add 1 to the Damage characteristic of that attack."
        ),
    )
    session = LocalGameSession(
        GameLifecycle.from_payload(
            cast(
                GameLifecyclePayload,
                {
                    "config": config.to_payload(),
                    "state": state.to_payload(),
                    "decisions": decisions.to_payload(),
                    "reaction_queue": ReactionQueue().to_payload(),
                    "parameterized_movement_proposals": True,
                },
            )
        )
    )
    for index in range(150):
        status = session.advance_until_decision_or_terminal()
        current = session.lifecycle.state
        assert current is not None
        if current.battle_round == 3:
            break
        request = status.decision_request
        assert request is not None
        if request.decision_type == "submit_stratagem_target_proposal":
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"order97-unqualified-{index}",
                payload=stratagem_decline_payload(),
            )
        else:
            options = tuple(
                option
                for option in request.options
                if option.option_id.startswith("complete_")
                or option.option_id in {"remain_stationary", "decline"}
            )
            option = options[0] if options else request.options[0]
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"order97-unqualified-{index}",
                option_id=option.option_id,
            )
        assert status.status_kind not in {
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }, status
        if index == 7:
            session = LocalGameSession.from_persistence_payload(
                json.loads(json.dumps(session.to_persistence_payload()))
            )
    resolved = [
        cast(dict[str, JsonValue], event.payload)
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "catalog_selected_target_effect_selected"
    ]
    assert [(row["battle_round"], row["active_player_id"]) for row in resolved] == [
        (1, "player-a"),
        (1, "player-b"),
        (2, "player-a"),
        (2, "player-b"),
    ]
    assert all(row["player_id"] == "player-a" and row["phase"] == "fight" for row in resolved)
    for row in resolved:
        effects = cast(list[dict[str, JsonValue]], row["persisting_effects"])
        assert len(effects) == 1
        assert effects[0]["source_rule_id"] == "test:p01c:catalog-rule"
        expiration = cast(dict[str, JsonValue], effects[0]["expiration"])
        assert expiration["player_id"] == row["active_player_id"]
        assert expiration["phase"] == "fight"
    assert_persistence_viewers_replay(session)
