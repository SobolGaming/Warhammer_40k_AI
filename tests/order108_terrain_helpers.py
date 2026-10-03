"""Canonical facade fixture with declared physical terrain and legal starting poses."""

from dataclasses import replace

from tests.phase13b_shooting_declaration_helpers import (
    _canonical_catalog,
    _compact_intercessor_catalog,
    _config,
    _configure_shooting_battle_state,
    _mustered_armies,
    _scenario_with_unit_pose,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition


def terrain_session(feature: TerrainFeatureDefinition) -> LocalGameSession:
    config = _config(
        game_id="order108-terrain",
        alpha_unit_ids=("mover",),
        alpha_datasheets=None,
        alpha_unit_specs=(("mover", "core-intercessor-like-infantry", "core-intercessor-like", 1),),
        enemy_datasheet=("core-intercessor-like-infantry", "core-intercessor-like", 1),
        enemy_unit_specs=(("enemy", "core-intercessor-like-infantry", "core-intercessor-like", 1),),
        catalog=_compact_intercessor_catalog(_canonical_catalog()),
    )
    assert config.mission_setup is not None
    config = replace(
        config, mission_setup=replace(config.mission_setup, terrain_features=(feature,))
    )
    armies = _mustered_armies(config)
    units = {unit.unit_instance_id.split(":", 1)[1]: unit for army in armies for unit in army.units}
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="order108-battlefield",
        armies=armies,
        battlefield_width_inches=100,
        battlefield_depth_inches=60,
    )
    for army in armies:
        for unit in army.units:
            scenario = _scenario_with_unit_pose(
                scenario=scenario,
                unit=unit,
                army_id=army.army_id,
                player_id=army.player_id,
                poses=(Pose.at(10, 20) if army.player_id == "player-a" else Pose.at(30, 20),),
            )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.decision_controller.event_log = EventLog()
    assert lifecycle.state is not None
    _configure_shooting_battle_state(
        state=lifecycle.state,
        decisions=lifecycle.decision_controller,
        armies=armies,
        battlefield=replace(scenario.battlefield_state, terrain_features=(feature,)),
        units=units,
        embarked_unit_ids=(),
    )
    lifecycle.state.battle_phase_index = lifecycle.state.battle_phase_sequence.index(
        BattlePhase.MOVEMENT
    )
    return LocalGameSession(lifecycle)
