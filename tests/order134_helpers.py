"""Constructed qualifying contexts, not admitted in-turn deployment providers."""

from __future__ import annotations

from typing import cast

from tests.support.ability_presence_fixtures import ability_presence_fixture
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.large_model_deployment_restrictions import (
    record_conditional_deployment_restriction,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id


def conditional_deployment_session(*, opponent_turn: bool = False) -> LocalGameSession:
    config, state, decisions = ability_presence_fixture(embarked=False, attached=True)
    if opponent_turn:
        state.active_player_id = "player-b"
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:passengers")
    record_conditional_deployment_restriction(
        state=state,
        unit_instance_id=view.unit_instance_id,
        qualifying_model_instance_ids=(view.own_models[-1].model_instance_id,),
        setup_occasion_id="order134-constructed-condition-1",
    )
    return LocalGameSession(
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
