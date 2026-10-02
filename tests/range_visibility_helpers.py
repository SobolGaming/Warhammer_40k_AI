"""Coherent physical targets whose range and visibility witnesses differ."""

from dataclasses import replace

from tests.phase13b_shooting_declaration_helpers import (
    _blocking_ruin,
    _canonical_catalog,
    _compact_intercessor_catalog,
    _config,
    _configure_shooting_battle_state,
    _display_geometry,
    _mustered_armies,
    _scenario_with_unit_pose,
)
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AttackProfile,
    RangeProfile,
    WeaponKeyword,
)
from warhammer40k_core.engine.command_points import CommandPointSourceKind
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.movement import MovementPhaseState
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose

SHOOTER = "army-alpha:shooter"
TARGET = "army-beta:enemy"


def range_visibility_scene(
    *,
    attached: bool = False,
    overwatch: bool = False,
    rapid_fire: bool = False,
    separate_units: bool = False,
) -> tuple[LocalGameSession, dict[str, UnitInstance]]:
    catalog = _compact_intercessor_catalog(_canonical_catalog())
    catalog = replace(
        catalog,
        wargear=tuple(
            replace(
                item,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        range_profile=RangeProfile.distance(42 if rapid_fire else 21),
                        attack_profile=AttackProfile.fixed(2),
                        keywords=(WeaponKeyword.RAPID_FIRE,) if rapid_fire else (),
                        abilities=(AbilityDescriptor.rapid_fire(1),) if rapid_fire else (),
                    )
                    if profile.range_profile.distance_inches is not None
                    else profile
                    for profile in item.weapon_profiles
                ),
            )
            for item in catalog.wargear
        ),
    )
    config = _config(
        game_id="order104-range-visibility",
        alpha_unit_ids=("shooter",),
        alpha_datasheets=None,
        alpha_unit_specs=(
            ("shooter", "core-intercessor-like-infantry", "core-intercessor-like", 1),
        ),
        enemy_datasheet=None,
        enemy_unit_specs=(
            (
                "enemy",
                "core-intercessor-like-infantry",
                "core-intercessor-like",
                1 if attached else 2,
            ),
            *(
                ((("leader", "core-character-leader", "core-character-leader", 1),))
                if attached
                else ()
            ),
        ),
        enemy_attachment_declarations=(AttachmentDeclaration("leader", "enemy"),)
        if attached and not separate_units
        else (),
        catalog=catalog,
    )
    ruin = _blocking_ruin()
    geometry = _display_geometry(
        center_x_inches=30, center_y_inches=35, width_inches=0.2, depth_inches=1.5
    )
    terrain = (
        replace(
            ruin,
            footprint_center_x_inches=30,
            footprint_width_inches=0.2,
            footprint_depth_inches=1.5,
            rules_footprint_polygon=geometry.footprint_polygon,
            display_geometry=geometry,
            walls=tuple(replace(wall, center_x_inches=30, depth_inches=1.5) for wall in ruin.walls),
            floors=tuple(
                replace(floor, center_x_inches=30, width_inches=0.2, depth_inches=1.5)
                for floor in ruin.floors
            ),
        ),
    )
    assert config.mission_setup is not None
    config = replace(config, mission_setup=replace(config.mission_setup, terrain_features=terrain))
    armies = _mustered_armies(config)
    units = {unit.unit_instance_id.split(":", 1)[1]: unit for army in armies for unit in army.units}
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="order104-battlefield",
        armies=armies,
        battlefield_width_inches=100.0,
        battlefield_depth_inches=60.0,
    )
    for army in armies:
        for unit in army.units:
            key = unit.unit_instance_id.split(":", 1)[1]
            poses = (
                (Pose.at(10, 35),)
                if key == "shooter"
                else tuple(
                    Pose.at(32 + 0.5 * index, 35 + 3 * index)
                    for index in (range(1, 2) if key == "leader" else range(len(unit.own_models)))
                )
            )
            scenario = _scenario_with_unit_pose(
                scenario=scenario,
                unit=unit,
                army_id=army.army_id,
                player_id=army.player_id,
                poses=poses,
            )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.decision_controller.event_log = EventLog()
    assert lifecycle.state is not None
    state = lifecycle.state
    _configure_shooting_battle_state(
        state=state,
        decisions=lifecycle.decision_controller,
        armies=armies,
        battlefield=replace(scenario.battlefield_state, terrain_features=terrain),
        units=units,
        embarked_unit_ids=(),
    )
    if overwatch:
        state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
        state.active_player_id = "player-b"
        state.movement_phase_state = MovementPhaseState(
            battle_round=state.battle_round, active_player_id="player-b", move_units_completed=True
        )
        state.gain_command_points(
            player_id="player-a",
            amount=1,
            source_id="order104:cp",
            source_kind=CommandPointSourceKind.OTHER,
            cap_exempt=True,
        )
        record_primary_turn_start_evidence_for_fixture(
            state, decisions=lifecycle.decision_controller
        )
    return LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload())), units
