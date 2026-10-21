"""03.02.03: native Yriel permission and Rangers Infiltrators at redeploy boundary."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import AVENGERS, RANGERS, Section02Definitions
from tests.support.section03_fixtures import YRIEL, grid, native_state, placement
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleStage, SetupStep
from warhammer40k_core.engine.prebattle import (
    PreBattlePlacementProposal,
    redeploy_placement_request_from_selection,
    redeploy_unit_selection_request,
    resolve_prebattle_proposal,
)
from warhammer40k_core.engine.unit_state import StartingStrengthRecord


@pytest.mark.parametrize(
    ("sheet", "x", "valid"),
    [(RANGERS, 25, True), (AVENGERS, 25, False), (AVENGERS, 10, True), (RANGERS, 38, False)],
)
def test_redeploy_removes_before_replacing_under_normal_infiltrator_rules(
    section03_definitions: Section02Definitions,
    section03_setup_mission: MissionSetup,
    sheet: str,
    x: float,
    valid: bool,
) -> None:
    unit = section03_definitions.unit(sheet)
    leader = section03_definitions.unit(YRIEL, identity="permission-source")
    state = native_state(section03_definitions, unit)
    state.army_definitions[:] = [replace(state.army_definitions[0], units=(unit, leader))]
    state.starting_strength_records.append(
        StartingStrengthRecord.from_unit(player_id="owner", unit=leader)
    )
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_added_unit_placement(
        placement(leader, grid(leader, 5, 20))
    )
    state.mission_setup = section03_setup_mission
    state.stage = GameLifecycleStage.SETUP
    state.setup_step_index = state.setup_sequence.index(SetupStep.REDEPLOY_UNITS)
    state.battle_phase_index = None
    state.active_player_id = None
    selection = redeploy_unit_selection_request(
        state=state,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=section03_definitions.package.army_catalog,
        player_id="owner",
    )
    option = next(
        o
        for o in selection.options
        if isinstance(o.payload, dict)
        and o.payload.get("unit_instance_id") == unit.unit_instance_id
        and o.payload.get("action_kind") == "redeploy"
    )
    request = redeploy_placement_request_from_selection(
        state=state,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=section03_definitions.package.army_catalog,
        selection_request=selection,
        result=DecisionResult.for_request(
            result_id="select-redeploy", request=selection, selected_option_id=option.option_id
        ),
    )
    proposal = PreBattlePlacementProposal(
        request.request_id,
        request.proposal_kind,
        state.game_id,
        state.ruleset_descriptor_hash,
        SetupStep.REDEPLOY_UNITS,
        "owner",
        unit.unit_instance_id,
        request.action_kind,
        request.source_rule_id,
        BattlefieldPlacementKind.REDEPLOY,
        placement(unit, grid(unit, x, 10)).model_placements,
        request.context,
    )
    before = state.to_payload()
    result = resolve_prebattle_proposal(
        state=state,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=section03_definitions.package.army_catalog,
        request=request,
        proposal=proposal,
    )
    assert result.is_valid is valid
    assert state.to_payload() == before
    if valid:
        assert result.removal_batch is not None
        assert result.placement_batch is not None
        assert {r.model_instance_id for r in result.removal_batch.removals} == set(
            unit.own_model_ids()
        )
        assert {r.model_instance_id for r in result.placement_batch.placements} == set(
            unit.own_model_ids()
        )
        assert all(
            r.placement_kind is BattlefieldPlacementKind.REDEPLOY
            for r in result.placement_batch.placements
        )
    else:
        assert result.removal_batch is None
        assert result.placement_batch is None
