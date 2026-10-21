"""Reminder resources never become physical models or movement obstacles."""

from dataclasses import replace

from tests.support.section01_fixtures import minimal_state, place_units
from tests.support.section01_geometry import witnessed_query
from tests.support.section02_fixtures import AVENGERS, Section02Definitions
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.physical_engagement import (
    physical_geometry_models_for_rules_unit,
)
from warhammer40k_core.engine.unit_resources import UnitResourceLedger
from warhammer40k_core.geometry.movement_reachability import MovementGoal
from warhammer40k_core.geometry.pose import Pose


def test_01_02_09_native_aspect_token_never_changes_inventory_or_blocks_path(
    section01_definitions: Section02Definitions,
) -> None:
    unit = section01_definitions.unit(AVENGERS)
    ability = next(a for a in unit.datasheet_abilities if a.name == "Aspect Shrine Token")
    state = minimal_state(section01_definitions, unit)
    place_units(state)
    before = battlefield_scenario_for_state(state=state)
    ledger = UnitResourceLedger("owner", unit.unit_instance_id).initialize(
        resource_kind="aspect_shrine_token", amount=1, source_rule_id=ability.source_id
    )
    state.replace_unit_resource_ledgers([ledger])
    after = battlefield_scenario_for_state(state=state)
    assert after == before
    models = physical_geometry_models_for_rules_unit(
        scenario=after, unit_instance_id=unit.unit_instance_id
    )
    assert len(models) == len(unit.own_models) == 5
    source = models[0]
    endpoint = Pose.at(source.pose.position.x + 1, source.pose.position.y)
    query = witnessed_query(
        source,
        endpoint,
        1,
        MovementGoal(models=(replace(source, pose=endpoint),), range_inches=0),
    )
    assert query.path_context.validate().is_valid
    assert query.terrain_context.validate().is_valid
    assert state.starting_strength_record_for_unit(unit.unit_instance_id).starting_model_count == 5
