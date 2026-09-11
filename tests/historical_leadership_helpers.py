from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from tests.phase11c_command_phase_helpers import (
    complete_setup_through_gate,
    mustered_armies,
    phase11c_config,
    secondary_choice,
)
from tests.support.ability_presence_fixtures import compiled_ability_rule
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.battle_shock import (
    BattleShockTestRequest,
    BattleShockTestRequestPayload,
)
from warhammer40k_core.engine.battle_shock_historical_authority import (
    HistoricalBattleShockAuthorityContext,
    historical_battle_shock_authority_context,
)
from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState, SecondaryMissionMode
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionStatus,
    execute_rule_ir,
)
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText


def historical_leadership_lifecycle(
    *, registered: bool = False, duplicate: bool = False, expires: bool = False
) -> GameLifecycle:
    source = RuleSourceText.from_raw(
        objective_scope=ObjectiveRuleScope.CORE_RULES,
        source_id="fixture:historical-leadership",
        raw_text=(
            (
                "Once per battle, at the start of any phase, this model can use this ability. "
                "If it does, "
                if duplicate
                else ""
            )
            + ("until" if duplicate else "Until")
            + f" the end of the {'phase' if expires else 'turn'}, add 1 to the Leadership "
            + (
                "characteristic of this model."
                if duplicate
                else "characteristic of models in this unit."
            )
        ),
    )
    rule_ir = compiled_ability_rule(source.raw_text, source_id=source.source_id)
    config = phase11c_config(game_id="historical-generic-leadership")
    assert config.army_catalog is not None
    catalog = config.army_catalog
    target_sheet = catalog.datasheet_by_id(
        config.army_muster_requests[0].unit_selections[0].datasheet_id
    )
    ability = DatasheetAbilityDescriptor(
        ability_id="historical-leadership",
        name="Historical Leadership fixture",
        source_id=source.source_id,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=source.raw_text,
        rule_ir_payload=cast(CatalogJsonObject, rule_ir.to_payload()),
    )
    additions: tuple[DatasheetAbilityDescriptor, ...] = (ability,)
    if registered:
        registered_text = (
            'While this unit is within 12" of one or more friendly Infantry Battleline models, '
            "models in this unit have a Leadership characteristic of 5+ and each time a model "
            "in this unit makes an attack, add 1 to the Hit roll."
        )
        registered_ir = compile_rule_source_text(
            RuleSourceText.from_raw(
                objective_scope=ObjectiveRuleScope.CORE_RULES,
                source_id="fixture:registered-leadership",
                raw_text=registered_text,
            ),
            source_keyword_sequence_parts=("INFANTRY", "BATTLELINE"),
        ).rule_ir
        additions += (
            replace(
                ability,
                ability_id="registered-leadership",
                source_id=registered_ir.source_id,
                name="Registered Leadership fixture",
                effect_description=registered_text,
                rule_ir_payload=cast(CatalogJsonObject, registered_ir.to_payload()),
            ),
        )
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(sheet, abilities=(*sheet.abilities, *additions))
            if sheet.datasheet_id == target_sheet.datasheet_id
            else sheet
            for sheet in catalog.datasheets
        ),
    )
    config = replace(config, army_catalog=catalog)
    state = GameState.from_config(config)
    decisions = DecisionController()
    for army in mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="historical-leadership-battlefield", armies=tuple(state.army_definitions)
    )
    state.record_battlefield_state(scenario.battlefield_state)
    target = state.army_definitions[0].units[0]
    for model in target.own_models[:3]:
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=target.unit_instance_id,
            model_instance_id=model.model_instance_id,
            damage=model.wounds_remaining,
            damage_kind=DamageKind.NORMAL,
        )
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            secondary_choice(player_id=player, mode=SecondaryMissionMode.FIXED)
        )
    complete_setup_through_gate(state=state, decisions=decisions, config=config)
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": {"frames": []},
        }
    )
    assert lifecycle.state is not None
    target = lifecycle.state.army_definitions[0].units[0]
    if duplicate:
        return lifecycle
    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=RuleExecutionContext(
            game_id=state.game_id,
            player_id="player-a",
            battle_round=1,
            phase=state.current_battle_phase,
            active_player_id="player-a",
            source_unit_instance_id=target.unit_instance_id,
            target_unit_instance_ids=(target.unit_instance_id,),
            state=lifecycle.state,
            event_log=lifecycle.decision_controller.event_log,
        ),
    )
    assert result.status is RuleExecutionStatus.APPLIED
    assert len(result.created_persisting_effects) == 1
    return lifecycle


def completed_historical_leadership_session(
    *, registered: bool = False, duplicate: bool = False, expires: bool = False
) -> LocalGameSession:
    lifecycle = historical_leadership_lifecycle(
        registered=registered, duplicate=duplicate, expires=expires
    )
    session = LocalGameSession(lifecycle=lifecycle)
    status = session.advance_until_decision_or_terminal()
    for index in range(32):
        assert lifecycle.state is not None
        if lifecycle.state.current_battle_phase is not BattlePhase.COMMAND:
            break
        request = status.decision_request
        assert request is not None
        if request.decision_type == "resolve_sequencing_order":
            status = session.submit_option(
                request_id=request.request_id,
                option_id=request.options[0].option_id,
                result_id=f"historical-leadership-order-{index}",
            )
            continue
        if (
            request.options
            and isinstance(request.options[0].payload, dict)
            and "activate" in request.options[0].payload
        ):
            option = next(
                option
                for option in request.options
                if isinstance(option.payload, dict)
                and option.payload.get("activate") is (request.actor_id == "player-a")
            )
            status = session.submit_option(
                request_id=request.request_id,
                option_id=option.option_id,
                result_id=f"historical-leadership-activate-{index}",
            )
            continue
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            payload=stratagem_decline_payload(),
            result_id=f"historical-leadership-decline-{index}",
        )
    else:
        pytest.fail("Command phase did not complete.")
    return session


def completed_leadership_history(
    session: LocalGameSession,
) -> HistoricalBattleShockAuthorityContext:
    lifecycle = session.lifecycle
    assert lifecycle.state is not None
    events = lifecycle.decision_controller.event_log.records
    index, event = next(
        (index, event)
        for index, event in enumerate(events)
        if event.event_type == "battle_shock_modifier_applications_recorded"
    )
    assert isinstance(event.payload, dict)
    return historical_battle_shock_authority_context(
        state=lifecycle.state,
        event_records=events,
        decision_records=lifecycle.decision_controller.records,
        boundary_event_index=index,
        request=BattleShockTestRequest.from_payload(
            cast(BattleShockTestRequestPayload, event.payload["battle_shock_test_request"])
        ),
        active_player_id="player-a",
        phase=BattlePhase.COMMAND,
        phase_start_battle_shocked_unit_ids=(),
    )
