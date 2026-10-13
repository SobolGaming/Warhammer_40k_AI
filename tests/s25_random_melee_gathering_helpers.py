"""Random WS declared before muster in an admitted Core Fight fixture root."""

from dataclasses import replace
from math import cos, radians, sin
from typing import cast

from tests.epic_challenge_helpers import submit_all_melee
from tests.fight_completion_helpers import submit_completion_request
from tests.phase15c_fight_order_helpers import fight_config, mustered_armies, unit_placement_at
from tests.psychic_modifier_helpers import pending_request
from tests.setup_completion_helpers import (
    record_current_battlefield_placements_for_fixture,
    record_primary_turn_start_evidence_for_fixture,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import DiceExpression
from warhammer40k_core.core.random_profile_values import RandomProfileValue
from warhammer40k_core.core.weapon_profiles import AttackProfile, WeaponKeyword
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.geometry.pose import Pose


def random_ws_melee_request(player: str) -> tuple[LocalGameSession, DecisionRequest]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    blade = next(
        item for item in catalog.wargear if item.wargear_id == "core-leader-blade"
    ).weapon_profiles[0]
    source = "analytical:s25-predeclared-melee-skill"
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                item,
                weapon_profiles=(
                    replace(
                        blade,
                        profile_id="core-bolt-rifle:standard",
                        attack_profile=AttackProfile.fixed(2),
                        skill=RandomProfileValue(
                            Characteristic.WEAPON_SKILL, DiceExpression(1, 3, 1), source
                        ),
                        keywords=(*blade.keywords, WeaponKeyword.TWIN_LINKED),
                        source_ids=(*blade.source_ids, source),
                    ),
                ),
            )
            if item.wargear_id == "core-bolt-rifle"
            else item
            for item in catalog.wargear
        ),
    )
    alpha = ("attacker",) if player == "player-a" else ("target",)
    beta = ("target",) if player == "player-a" else ("attacker",)
    subjects = {"attacker": ("core-intercessor-like-infantry", "core-intercessor-like", 5)}
    targets = {"target": ("core-character-leader", "core-character-leader", 1)}
    config = fight_config(
        game_id="s25-random-ws:" + player,
        alpha_unit_ids=alpha,
        enemy_unit_ids=beta,
        datasheet_id="core-intercessor-like-infantry",
        model_profile_id="core-intercessor-like",
        model_count=5,
        catalog=catalog,
        alpha_unit_specs=subjects if player == "player-a" else targets,
        enemy_unit_specs=targets if player == "player-a" else subjects,
    )
    other = "player-b" if player == "player-a" else "player-a"
    config = replace(config, turn_order=(player, other))
    armies = mustered_armies(config)
    mission = config.mission_setup
    assert mission is not None
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id=config.game_id + ":battlefield",
        armies=armies,
        battlefield_width_inches=mission.battlefield_width_inches,
        battlefield_depth_inches=mission.battlefield_depth_inches,
    )
    battlefield = scenario.battlefield_state
    for army in armies:
        for unit in army.units:
            poses = (
                tuple(
                    Pose.at(20 + 1.8 * cos(radians(72 * i)), 20 + 1.8 * sin(radians(72 * i)))
                    for i in range(5)
                )
                if unit.unit_instance_id.endswith(":attacker")
                else (Pose.at(20, 20),)
            )
            battlefield = battlefield.with_unit_placement(
                unit_placement_at(unit, army_id=army.army_id, player_id=army.player_id, poses=poses)
            )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_round = 1
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.active_player_id = player
    for owner in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=owner,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    decisions = DecisionController()
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    root = cast(
        GameLifecyclePayload,
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": {"frames": []},
        },
    )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(root))
    for _ in range(80):
        request = pending_request(session)
        if request.decision_type == "submit_melee_declaration" and request.actor_id == player:
            return session, request
        if request.decision_type == "submit_melee_declaration":
            submit_all_melee(session, request)
        else:
            submit_completion_request(session)
    raise AssertionError("Random WS fixture did not reach its real native melee declaration.")
