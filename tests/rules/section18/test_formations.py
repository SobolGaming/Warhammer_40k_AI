"""18.01 starting cargo and empty native Dedicated Transport boundary."""

from typing import TypedDict

import pytest

from tests.support.section01_fixtures import minimal_state
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section18_fixtures import AVENGERS, WAVE, YRIEL
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState
from warhammer40k_core.engine.damage_allocation import unit_by_id
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.empty_dedicated_transport_destruction import (
    apply_empty_dedicated_transport_destruction,
)
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, SetupStep
from warhammer40k_core.engine.transports import TransportCapacityProfile


class FormationArguments(TypedDict):
    player_id: str
    transport_unit_instance_id: str
    embarked_unit_instance_ids: tuple[str, ...]
    capacity_profile: TransportCapacityProfile


@pytest.mark.parametrize(
    ("capacity", "allowed", "valid"),
    [(6, ("INFANTRY",), True), (5, ("INFANTRY",), False), (6, ("VEHICLE",), False)],
)
def test_formations_admit_multiple_whole_units_only_with_remaining_type_and_capacity(
    section18_definitions: Section02Definitions,
    capacity: int,
    allowed: tuple[str, ...],
    valid: bool,
) -> None:
    d = section18_definitions
    carrier, leader, squad = (
        d.unit(WAVE, identity="carrier"),
        d.unit(YRIEL, identity="leader"),
        d.unit(AVENGERS, identity="squad"),
    )
    state = minimal_state(d, carrier, leader, squad)
    state.stage = GameLifecycleStage.SETUP
    state.setup_step_index = state.setup_sequence.index(SetupStep.DECLARE_BATTLE_FORMATIONS)
    state.battle_phase_index = None
    kwargs: FormationArguments = {
        "player_id": "owner",
        "transport_unit_instance_id": carrier.unit_instance_id,
        "embarked_unit_instance_ids": tuple(
            sorted((leader.unit_instance_id, squad.unit_instance_id))
        ),
        "capacity_profile": TransportCapacityProfile(
            WAVE, capacity, allowed, source_id="constructed:s18:formations-capacity"
        ),
    }
    if valid:
        result = state.declare_battle_formation_embarkation(**kwargs)
        assert result.embarked_unit_instance_ids == tuple(
            sorted((leader.unit_instance_id, squad.unit_instance_id))
        )
        assert state.transport_cargo_state_for_embarked_unit(leader.unit_instance_id) == result
        assert state.transport_cargo_state_for_embarked_unit(squad.unit_instance_id) == result
    else:
        before = state.to_payload()
        with pytest.raises(GameLifecycleError, match=r"capacity|eligible"):
            state.declare_battle_formation_embarkation(**kwargs)
        assert state.to_payload() == before


@pytest.mark.parametrize("loaded", [False, True])
def test_formation_end_destroys_only_empty_native_dedicated_transport_without_reactions(
    section18_definitions: Section02Definitions,
    loaded: bool,
) -> None:
    d = section18_definitions
    carrier, passenger = d.unit(WAVE, identity="carrier"), d.unit(YRIEL, identity="passenger")
    assert "DEDICATED TRANSPORT" in carrier.keywords
    state = minimal_state(d, carrier, passenger)
    state.stage = GameLifecycleStage.SETUP
    state.setup_step_index = state.setup_sequence.index(SetupStep.DECLARE_BATTLE_FORMATIONS)
    state.battle_phase_index = None
    state.record_battlefield_state(
        BattlefieldRuntimeState("constructed:s18:predeployment", 60, 44, ())
    )
    if loaded:
        state.declare_battle_formation_embarkation(
            player_id="owner",
            transport_unit_instance_id=carrier.unit_instance_id,
            embarked_unit_instance_ids=(passenger.unit_instance_id,),
            capacity_profile=TransportCapacityProfile(WAVE, 12, ("INFANTRY",)),
        )
    decisions = DecisionController()
    result = apply_empty_dedicated_transport_destruction(state=state, decisions=decisions)
    assert not result.destroyed_model_rules_triggered
    assert bool(result.destroyed_units) is not loaded
    current = unit_by_id(state=state, unit_instance_id=carrier.unit_instance_id)
    assert current.own_models[0].is_alive is loaded
    assert state.battlefield_state is not None
    assert (
        carrier.own_models[0].model_instance_id in state.battlefield_state.removed_model_ids
    ) is not loaded
    events = decisions.event_log.records
    assert {e.event_type for e in events} == (
        set() if loaded else {"empty_dedicated_transports_destroyed"}
    )
    if not loaded:
        assert result.destroyed_units[0].model_instance_ids == carrier.own_model_ids()
        # A second boundary application does not destroy/trigger anything twice.
        again = apply_empty_dedicated_transport_destruction(state=state, decisions=decisions)
        assert not again.destroyed_units
        assert decisions.event_log.records == events
