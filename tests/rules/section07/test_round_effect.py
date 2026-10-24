"""A real round-rule consumer on an explicit constructed source-permission contract."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section07_fixtures import boundary_state
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battle_round_hooks import (
    BattleRoundStartHookRegistry,
    BattleRoundStartRequestContext,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters import army_rule
from warhammer40k_core.engine.list_validation import DetachmentSelection
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.unit_state import StartingStrengthRecord


@pytest.mark.parametrize("first", ["owner", "opponent"])
@pytest.mark.parametrize("battle_round", [1, 2])
def test_constructed_round_permission_resolves_real_effect_before_command_once(
    section07_definitions: Section02Definitions, first: str, battle_round: int
) -> None:
    d = section07_definitions
    state = boundary_state(d, first=first, active=first, battle_round=battle_round)
    native = d.unit("000004078")
    # The selected loader rejects the WE sheet without a representative height.
    # Keep that guard. This explicit source-permission contract retains the
    # supported native body's geometry and calls the real World Eaters owner.
    permission = DatasheetAbilityDescriptor(
        ability_id="constructed:section07:blessings-permission",
        name="Constructed round-rule source permission",
        source_id=army_rule.SOURCE_RULE_ID,
        source_kind=CatalogAbilitySourceKind.FACTION,
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        effect_description="Constructed round-start source permission contract",
    )
    native = replace(native, datasheet_abilities=(*native.datasheet_abilities, permission))
    state.army_definitions[0] = replace(
        state.army_definitions[0],
        units=(native,),
        detachment_selection=DetachmentSelection("world-eaters", ("berzerker-warband",)),
    )
    state.starting_strength_records[:] = [
        StartingStrengthRecord.from_unit(player_id=army.player_id, unit=unit)
        for army in state.army_definitions
        for unit in army.units
    ]
    registry = BattleRoundStartHookRegistry.from_bindings(
        army_rule.runtime_contribution().battle_round_start_hook_bindings
    )
    flow = BattleRoundFlow(
        phase_handlers={BattlePhase.COMMAND: CommandPhaseHandler()},
        battle_round_start_hooks=registry,
    )
    decisions = DecisionController()
    status = flow.advance(state=state, decisions=decisions)
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = status.decision_request
    assert request is not None
    assert request.actor_id == "owner"
    assert state.current_battle_phase is BattlePhase.COMMAND
    assert not any(e.event_type == "battle_phase_completed" for e in decisions.event_log.records)
    assert not army_rule.active_blessings_for_player(state, player_id="owner")
    option = next(
        option
        for option in request.options
        if (
            isinstance(option.payload, dict)
            and isinstance(blessings := option.payload.get("selected_blessing_ids"), list)
            and "unbridled_bloodlust" in blessings
        )
    )
    result = DecisionResult.for_request(
        result_id="s07-blessing", request=request, selected_option_id=option.option_id
    )
    decisions.submit_result(result)
    flow.apply_decision(state=state, result=result, decisions=decisions)
    assert army_rule.BlessingOfKhorne.UNBRIDLED_BLOODLUST in (
        army_rule.active_blessings_for_player(state, player_id="owner")
    )
    assert state.persisting_effects
    assert registry.next_request_for(BattleRoundStartRequestContext(state, decisions)) is None
