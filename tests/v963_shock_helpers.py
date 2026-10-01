"""Real Tactical mission pause after Shock, with all fixture data preceding history."""

from dataclasses import replace

from tests.core_stratagem_helpers import (
    _clear_terrain,
    _config,
    _mustered_armies,  # pyright: ignore[reportPrivateUsage]
    _record_default_fixed_secondary_choices_for_missing_players,
    _replace_unit_poses,
)
from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID
from tests.psychic_modifier_helpers import pending_request
from tests.setup_completion_helpers import enter_battle_for_fixture
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.shock_disembark import shock_disembark_permission_effect
from warhammer40k_core.engine.transports import TransportCapacityProfile, TransportCargoState
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose


def tactical_shock_session() -> LocalGameSession:
    # Same real-object fixture assembly as disembark_session; choose Tactical
    # before battle and place the spare unit at Centre Ground before history starts.
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
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="v963:late-mission", armies=armies
    )
    state.record_battlefield_state(scenario.battlefield_state)
    _clear_terrain(state)
    _replace_unit_poses(state, unit_instance_id=TRANSPORT_ID, poses=(Pose.at(10, 10),))
    _replace_unit_poses(
        state,
        unit_instance_id="army-beta:enemy-unit",
        poses=tuple(Pose.at(18, 7.2 + 1.4 * i) for i in range(5)),
    )
    assert state.mission_setup is not None
    center_x = state.mission_setup.battlefield_width_inches / 2
    center_y = state.mission_setup.battlefield_depth_inches / 2
    _replace_unit_poses(
        state,
        unit_instance_id="army-alpha:remaining-unit",
        poses=tuple(Pose.at(center_x + (i - 2) * 1.4, center_y) for i in range(5)),
    )
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
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(player_id="player-a", mode=SecondaryMissionMode.TACTICAL)
    )
    _record_default_fixed_secondary_choices_for_missing_players(state)
    decisions = DecisionController()
    enter_battle_for_fixture(state, decisions=decisions)
    state.record_persisting_effect(
        shock_disembark_permission_effect(
            effect_id="v963:late-mission:shock-grant",
            source_rule_id="test:order38:grant:shock_disembark",
            owner_player_id="player-a",
            transport_unit_instance_id=TRANSPORT_ID,
            eligible_rules_unit_instance_ids=(PASSENGER_ID,),
            started_battle_round=1,
            started_phase=BattlePhase.COMMAND,
            expiration=EffectExpiration.end_phase(
                battle_round=1, phase=BattlePhase.MOVEMENT, player_id="player-a"
            ),
        )
    )
    session = LocalGameSession(
        GameLifecycle.from_payload(
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": decisions.to_payload(),
                "reaction_queue": ReactionQueue().to_payload(),
            }
        )
    )
    for i in range(10):
        request = pending_request(session)
        assert session.lifecycle.state is not None
        if session.lifecycle.state.current_battle_phase is BattlePhase.MOVEMENT:
            break
        options = tuple(option.option_id for option in request.options)
        if request.decision_type == "draw_tactical_secondary_missions":
            chosen = "draw"
        elif "decline_tactical_secondary_replacement" in options:
            chosen = "decline_tactical_secondary_replacement"
        elif "decline_stratagem_window" in options:
            chosen = "decline_stratagem_window"
        else:
            assert len(options) == 1, (request.decision_type, options)
            chosen = options[0]
        status = session.submit_option(
            request_id=request.request_id, result_id=f"v963:fixture-command:{i}", option_id=chosen
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert session.lifecycle.state is not None
    state = session.lifecycle.state
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    return session
