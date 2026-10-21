"""Small real-unit consumer states; no lifecycle, deployment or mission traversal."""

from dataclasses import replace

from tests.support.section02_fixtures import Section02Definitions, health_state

from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.pose import Pose


def combat_state(
    definitions: Section02Definitions, attacker: UnitInstance, target: UnitInstance
) -> GameState:
    state = health_state(definitions, definitions.unit(identity="kernel"))
    army = replace(state.army_definitions[0], units=(attacker,))
    enemy = replace(army, army_id="opponent-army", player_id="opponent", units=(target,))
    state.army_definitions[:] = [army, enemy]
    state.record_battlefield_state(
        create_deterministic_battlefield_scenario(
            battlefield_id="section02", armies=(army, enemy)
        ).battlefield_state
    )
    return state


def set_origin(state: GameState, unit: UnitInstance, x: float, y: float) -> None:
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    start = placement.model_placements[0].pose.position
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(
            replace(
                placement,
                model_placements=tuple(
                    replace(
                        p,
                        pose=Pose.at(
                            x + p.pose.position.x - start.x, y + p.pose.position.y - start.y
                        ),
                    )
                    for p in placement.model_placements
                ),
            )
        )
    )


def scenario(state: GameState) -> BattlefieldScenario:
    assert state.battlefield_state is not None
    return BattlefieldScenario(tuple(state.army_definitions), state.battlefield_state)


def attack_pool(
    attacker: UnitInstance, target: UnitInstance, weapon: WeaponProfile, wargear_id: str
) -> RangedAttackPool:
    model = attacker.own_models[0]
    return RangedAttackPool(
        weapon_instance_id=f"{model.model_instance_id}:{wargear_id}:001",
        attacker_model_instance_id=model.model_instance_id,
        wargear_id=wargear_id,
        weapon_profile_id=weapon.profile_id,
        weapon_profile=weapon,
        target_unit_instance_id=target.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=weapon.attack_profile.fixed_attacks or 1,
        target_visible_model_ids=target.own_model_ids(),
        target_in_range_model_ids=target.own_model_ids(),
    )


def payload_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def payload_int(value: JsonValue) -> int:
    assert type(value) is int
    return value


def payload_text(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value
