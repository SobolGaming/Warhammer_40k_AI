"""Real attached-unit/cargo fixtures for off-battlefield ability consumers."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from tests.phase11c_command_phase_helpers import (
    complete_setup_through_gate,
    default_unit_selection,
    mustered_armies,
    phase11c_config,
    secondary_choice,
    unit_selection,
)

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameConfig, GameState, SecondaryMissionMode
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reserve_arrival_requirements import reposition_destruction_policy
from warhammer40k_core.engine.reserves import ReserveOrigin, StrategicReserveDeclaration
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.transports import TransportCapacityProfile
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import (
    RuleIR,
    RuleParameter,
    RuleTrigger,
    RuleTriggerKind,
)
from warhammer40k_core.rules.source_data import RuleSourceText


def ability_presence_fixture(
    *,
    embarked: bool = True,
    attached: bool = True,
    ability_text: str | None = None,
    reserves: bool = False,
) -> tuple[GameConfig, GameState, DecisionController]:
    leader = unit_selection(
        unit_selection_id="leader",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    config = phase11c_config(
        game_id="p01c-ability-presence",
        player_a_units=(
            default_unit_selection("passengers"),
            leader,
            unit_selection(
                unit_selection_id="transport",
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        ),
        player_a_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader", bodyguard_unit_selection_id="passengers"
            ),
        )
        if attached
        else (),
    )
    if ability_text is not None:
        rule_ir = compiled_ability_rule(ability_text)
        descriptor = DatasheetAbilityDescriptor(
            ability_id="p01c-test-ability",
            name="P01C test ability",
            source_id=rule_ir.source_id,
            support=CatalogAbilitySupport.GENERIC_RULE_IR,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            effect_description=ability_text,
            rule_ir_payload=cast(CatalogJsonObject, rule_ir.to_payload()),
            rule_ir_diagnostics=tuple(
                cast(CatalogJsonObject, diagnostic.to_payload())
                for diagnostic in rule_ir.diagnostics
            ),
        )
        catalog = replace(
            config.army_catalog,
            datasheets=tuple(
                replace(sheet, abilities=(*sheet.abilities, descriptor))
                if sheet.datasheet_id == "core-character-leader"
                else sheet
                for sheet in config.army_catalog.datasheets
            ),
        )
        config = replace(config, army_catalog=catalog)
    state = GameState.from_config(config)
    decisions = DecisionController()
    for army in mustered_armies(config):
        state.record_army_definition(army)
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:leader")
    if reserves:
        reserve_states = state.apply_strategic_reserve_declarations(
            declarations=(
                StrategicReserveDeclaration(
                    unit_instance_id=view.unit_instance_id,
                    player_id="player-a",
                    unit_points=100,
                    reserve_origin=ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
                    declared_during_step="declare_battle_formations",
                    embarked_unit_points=0,
                    points_limit=1000,
                ),
            ),
            destruction_deadline_policy=reposition_destruction_policy(
                mission_setup=state.mission_setup, destruction_deadline_policy=None
            ),
        )
        for reserve_state in reserve_states:
            decisions.event_log.append(
                "reserve_unit_declared",
                {
                    "game_id": state.game_id,
                    "player_id": "player-a",
                    "unit_instance_id": view.unit_instance_id,
                    "reserve_state": reserve_state.to_payload(),
                },
            )
    elif embarked:
        state.declare_battle_formation_embarkation(
            player_id="player-a",
            transport_unit_instance_id="army-alpha:transport",
            embarked_unit_instance_ids=view.component_unit_instance_ids,
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id="core-transport",
                max_model_count=10,
                allowed_keywords=("INFANTRY",),
            ),
        )
    battlefield = create_deterministic_battlefield_scenario(
        battlefield_id="p01c-battlefield", armies=tuple(state.army_definitions)
    ).battlefield_state
    if embarked or reserves:
        for component_id in view.component_unit_instance_ids:
            battlefield = battlefield.without_unit_placement(component_id)
    state.record_battlefield_state(battlefield)
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            secondary_choice(player_id=player_id, mode=SecondaryMissionMode.FIXED)
        )
    complete_setup_through_gate(state=state, decisions=decisions, config=config)
    return config, state, decisions


def compiled_ability_rule(text: str) -> RuleIR:
    ir = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id="test:p01c:catalog-rule",
            raw_text=text,
            objective_scope=ObjectiveRuleScope.CORE_RULES,
        ),
        source_keyword_sequence_parts=("INFANTRY", "CHARACTER", "PSYKER", "VEHICLE", "TRANSPORT"),
    ).rule_ir
    phrase = "at the start of any phase"
    if phrase in ir.normalized_text:
        # The existing catalog accepts this typed trigger independently of parser coverage.
        start = ir.normalized_text.index(phrase)
        trigger = RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=TextSpan(text=phrase, start=start, end=start + len(phrase)),
            parameters=(RuleParameter("edge", "start"), RuleParameter("phase", "any")),
        )
        ir = replace(ir, clauses=tuple(replace(clause, trigger=trigger) for clause in ir.clauses))
    return ir
