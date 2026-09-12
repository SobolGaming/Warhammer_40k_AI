"""Canonical transport grant fixtures shared by eligibility tests and timing probes."""

from __future__ import annotations

from dataclasses import replace

from tests.core_stratagem_helpers import (
    _clear_terrain,
    _complete_current_command_for_fixture,  # pyright: ignore[reportPrivateUsage]
    _config,
    _mustered_armies,  # pyright: ignore[reportPrivateUsage]
    _record_default_fixed_secondary_choices_for_missing_players,
    _replace_unit_poses,
)
from tests.setup_completion_helpers import enter_battle_for_fixture
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.assault_disembark import assault_disembark_permission_effect
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.shock_disembark import shock_disembark_permission_effect
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    TransportCapacityProfile,
    TransportCargoState,
)
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose

PASSENGER_ID = "army-alpha:intercessor-unit-1"
TRANSPORT_ID = "army-alpha:transport"


def disembark_session(
    modes: tuple[DisembarkModeKind, ...] = (),
    *,
    eligible: bool = True,
) -> LocalGameSession:
    config = _config()
    alpha, beta = config.army_muster_requests
    config = replace(
        config,
        army_muster_requests=(
            replace(
                alpha,
                unit_selections=(
                    *alpha.unit_selections,
                    replace(alpha.unit_selections[0], unit_selection_id="remaining-unit"),
                    UnitMusterSelection(
                        unit_selection_id="transport",
                        datasheet_id="core-transport",
                        model_profile_selections=(
                            ModelProfileSelection(model_profile_id="core-transport", model_count=1),
                        ),
                    ),
                ),
            ),
            beta,
        ),
    )
    state = GameState.from_config(config)
    armies = _mustered_armies(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(battlefield_id="order38", armies=armies)
    state.record_battlefield_state(scenario.battlefield_state)
    _replace_unit_poses(state, unit_instance_id=TRANSPORT_ID, poses=(Pose.at(10, 10),))
    _clear_terrain(state)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.without_unit_placement(PASSENGER_ID)
    state.record_transport_cargo_state(
        TransportCargoState(
            player_id="player-a",
            transport_unit_instance_id=TRANSPORT_ID,
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id="core-transport",
                max_model_count=12,
                allowed_keywords=("INFANTRY",),
                source_id="test:order38:capacity",
            ),
            embarked_unit_instance_ids=(PASSENGER_ID,),
            phase_battle_round=1,
            started_phase_embarked_unit_instance_ids=(PASSENGER_ID,),
        )
    )
    decisions = DecisionController()
    enter_battle_for_fixture(state, decisions=decisions)
    _record_default_fixed_secondary_choices_for_missing_players(state)
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        }
    )
    lifecycle = _complete_current_command_for_fixture(lifecycle)
    assert lifecycle.state is not None
    state = lifecycle.state
    for mode in modes:
        if mode is DisembarkModeKind.ASSAULT_DISEMBARK:
            factory = assault_disembark_permission_effect
        elif mode is DisembarkModeKind.SHOCK_DISEMBARK:
            factory = shock_disembark_permission_effect
        else:
            raise AssertionError("Only source-permitted modes have grant fixtures.")
        state.record_persisting_effect(
            factory(
                effect_id=f"test:order38:{mode.value}",
                source_rule_id=f"test:order38:grant:{mode.value}",
                owner_player_id="player-a",
                transport_unit_instance_id=TRANSPORT_ID,
                eligible_rules_unit_instance_ids=(PASSENGER_ID if eligible else "other-passenger",),
                started_battle_round=1,
                started_phase=BattlePhase.MOVEMENT,
                expiration=EffectExpiration.end_phase(
                    battle_round=1, phase=BattlePhase.MOVEMENT, player_id="player-a"
                ),
            )
        )
    return LocalGameSession(lifecycle=lifecycle)
