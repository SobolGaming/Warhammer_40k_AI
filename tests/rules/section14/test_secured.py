"""Core14.03 and FAQ19: retained control, expiry, and source producer gates."""

import json
from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section14_boundaries import boundary_case, constructed_sticky, move_checkpoint
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.catalog_sticky_objective_runtime import (
    catalog_sticky_objective_hook_bindings,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlContext,
    PhaseEndObjectiveControlHookRegistry,
    StickyObjectiveControlState,
    apply_sticky_objective_control,
    sticky_objective_control_state_is_expired,
)


@pytest.mark.parametrize(
    ("owner_present", "enemy_present", "expected", "expired"),
    [
        (False, False, "owner", False),
        (True, True, "owner", False),
        (False, True, "opponent", True),
        (True, False, "owner", False),
    ],
)
def test_secured_zero_tie_and_strictly_greater_enemy_control(
    section14_definitions: Section02Definitions,
    owner_present: bool,
    enemy_present: bool,
    expected: str,
    expired: bool,
) -> None:
    state, unit, enemy = boundary_case(section14_definitions)
    assert state.mission_setup is not None
    marker = state.mission_setup.objective_markers[0]
    sticky = constructed_sticky(state, unit, marker.objective_marker_id)
    state.record_sticky_objective_control_state(sticky)
    move_checkpoint(state, unit, marker.x_inches + (0 if owner_present else 20), marker.y_inches)
    move_checkpoint(state, enemy, marker.x_inches + (0 if enemy_present else 25), marker.y_inches)
    raw = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.MOVEMENT,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        )
    )
    retained = apply_sticky_objective_control(record=raw, states=(sticky,))
    result = retained.result_by_objective_id(marker.objective_marker_id)
    assert result.controlled_by_player_id == expected
    assert (
        sticky_objective_control_state_is_expired(
            state=sticky, record=raw, player_ids=state.player_ids
        )
        is expired
    )
    assert (result.retained_control_source_id is None) is expired
    assert (
        StickyObjectiveControlState.from_payload(json.loads(json.dumps(sticky.to_payload())))
        == sticky
    )
    committed = state.record_objective_control_boundary(
        completed_phase=BattlePhase.MOVEMENT,
        timing=ObjectiveControlTiming.PHASE_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert committed == retained
    assert (sticky not in state.sticky_objective_control_states) is expired
    assert all(
        r.retained_control_source_id is None
        for r in committed.results
        if r.objective_id != marker.objective_marker_id
    )


@pytest.mark.parametrize("phase", [BattlePhase.COMMAND, BattlePhase.MOVEMENT])
@pytest.mark.parametrize("active", ["owner", "opponent"])
def test_native_tormentors_source_produces_secured_state_only_at_own_command_end(
    section14_definitions: Section02Definitions,
    phase: BattlePhase,
    active: str,
) -> None:
    state, unit, _ = boundary_case(section14_definitions, phase=phase, sheet="000004079")
    state.active_player_id = active
    catalog = section14_definitions.package.army_catalog
    # Filter by stable source identity, then exercise the native catalog producer.
    records = tuple(
        r
        for r in catalog_ability_records_from_catalog(catalog)
        if r.definition.source_id in {a.source_id for a in unit.datasheet_abilities}
    )
    assert records
    indexes = {
        "owner": AbilityCatalogIndex.from_records(records),
        "opponent": AbilityCatalogIndex.from_records(()),
    }
    registry = PhaseEndObjectiveControlHookRegistry.from_bindings(
        catalog_sticky_objective_hook_bindings(
            ability_indexes_by_player_id=indexes, armies=tuple(state.army_definitions)
        )
    )
    assert registry.bindings
    before = state.to_payload()
    states = registry.states_for(
        PhaseEndObjectiveControlContext(
            state=state,
            event_log=DecisionController().event_log,
            completed_phase=phase,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
    )
    assert state.to_payload() == before
    assert bool(states) is (phase is BattlePhase.COMMAND and active == "owner")
    for sticky in states:
        assert sticky.originating_unit_instance_id == unit.unit_instance_id
        assert sticky.source_rule_id in {a.source_id for a in unit.datasheet_abilities}
        assert sticky.player_id == "owner"
        state.record_sticky_objective_control_state(sticky)
        assert state.mission_setup is not None
        marker = next(
            m
            for m in state.mission_setup.objective_markers
            if m.objective_marker_id == sticky.objective_id
        )
        move_checkpoint(state, unit, marker.x_inches + 20, marker.y_inches)
        record = state.record_objective_control_boundary(
            completed_phase=phase,
            timing=ObjectiveControlTiming.PHASE_END,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        assert record.result_by_objective_id(sticky.objective_id).controlled_by_player_id == "owner"


def test_secured_state_rejects_duplicate_wrong_game_and_opponent_owner_atomically(
    section14_definitions: Section02Definitions,
) -> None:
    state, unit, _ = boundary_case(section14_definitions)
    assert state.mission_setup is not None
    sticky = constructed_sticky(
        state, unit, state.mission_setup.objective_markers[0].objective_marker_id
    )
    state.record_sticky_objective_control_state(sticky)
    before = state.to_payload()
    for invalid in (
        sticky,
        replace(sticky, state_id="different", game_id="wrong"),
        replace(sticky, state_id="opponent", player_id="opponent"),
    ):
        with pytest.raises(GameLifecycleError):
            state.record_sticky_objective_control_state(invalid)
        assert state.to_payload() == before
