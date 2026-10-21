"""The second 09.07.01 source node: native ability-forced hazards and Battle-shock."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import grid, native_state
from tests.support.section03_session import movement_session
from tests.support.section09_fixtures import (
    add_unit,
    anchor_hazard_scene,
    attach_mission,
    choose,
    events,
    finish_hazard_choices,
    propose,
    select,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("shocked", [False, True])
def test_native_forced_test_rolls_for_every_model_and_tests_battle_shock(
    section09_definitions: Section02Definitions,
    shocked: bool,
) -> None:
    unit = section09_definitions.unit("000004090")
    bloodletters = section09_definitions.unit("000001114", army_id="enemy", identity="bloodletters")
    state = native_state(
        section09_definitions, unit, enemy=bloodletters, enemy_poses=grid(bloodletters, 10, 13.3)
    )
    state.game_id = "section09-forced-escape-2"
    add_unit(
        state,
        section09_definitions.unit("000004090", identity="spare"),
        (Pose.at(10, 30), Pose.at(12.5, 30)),
    )
    attach_mission(state)
    if shocked:
        state.battle_shocked_unit_ids.append(unit.unit_instance_id)
    config = movement_session(section09_definitions, state).lifecycle.config
    index = AbilityCatalogIndex.from_records(
        catalog_ability_records_from_catalog(config.army_catalog)
    )
    handler = MovementPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
        ability_indexes_by_player_id={"owner": index, "opponent": index},
    )
    session = LocalGameSession(
        GameLifecycle(state=state, _config=config, _movement_phase_handler=handler)
    )
    from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

    record_primary_turn_start_evidence_for_fixture(
        state, decisions=session.lifecycle.decision_controller
    )
    request = select(session, unit)
    assert "fall_back:desperate_escape" in {o.option_id for o in request.options}
    anchor_hazard_scene(session)
    request = choose(session, request, "fall_back:desperate_escape")
    status = propose(session, request, unit, (Pose.at(10, 6), Pose.at(12.5, 6)))
    rolls = events(session, "desperate_escape_roll_resolved")
    assert len(rolls) == 2
    for event in rolls:
        roll = event["desperate_escape_roll"]
        assert isinstance(roll, dict)
        modifiers = roll["roll_modifiers"]
        assert isinstance(modifiers, list)
        assert len(modifiers) == int(shocked)
    if not shocked:
        status = finish_hazard_choices(session, status)
    # The shocked parameter is a constructed prior state without its prior
    # event authority. It proves the native modifier at intake, not continuation
    # through a new forced test. The unshocked case completes the packet.
    forced = events(session, "forced_desperate_escape_battle_shock_resolved")
    assert len(forced) == 1
    source = forced[0]["source_rule_id"]
    assert isinstance(source, str)
    assert source.endswith("09.07.01-forced-desperate-escape")
