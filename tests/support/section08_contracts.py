# pyright: reportPrivateUsage=false
"""Constructed source text contracts wired through real generic CP consumers."""

from dataclasses import replace
from typing import cast

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_session import movement_session

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine import runtime_event_phase_hooks
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.catalog_command_point_runtime import CatalogCommandPointRuntime
from warhammer40k_core.engine.command_phase_start_hooks import CommandPhaseStartHookRegistry
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEventHandlerRegistry,
    RuntimeContentEventIndex,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.engine.turn_end_hooks import TurnEndHookRegistry
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText


def command_session(
    definitions: Section02Definitions, state: GameState, timings: tuple[str, ...] = ()
) -> LocalGameSession:
    abilities: list[DatasheetAbilityDescriptor] = []
    for i, timing in enumerate(timings):
        source = f"constructed:section08:timing:{i}"
        text = f"{timing}, roll one D6: on a 1+, you gain 1CP."
        rule = compile_rule_source_text(
            RuleSourceText.from_raw(
                source_id=source, raw_text=text, objective_scope=ObjectiveRuleScope.CORE_RULES
            ),
            source_keyword_sequence_parts=("INFANTRY", "CHARACTER"),
        ).rule_ir
        assert not rule.diagnostics
        assert all(c.is_supported for c in rule.clauses)
        abilities.append(
            DatasheetAbilityDescriptor(
                ability_id=source,
                name="Constructed Section08 timing contract",
                source_id=source,
                support=CatalogAbilitySupport.GENERIC_RULE_IR,
                source_kind=CatalogAbilitySourceKind.DATASHEET,
                effect_description=text,
                rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
            )
        )
    catalog = replace(
        definitions.package.army_catalog,
        datasheets=tuple(
            replace(sheet, abilities=(*sheet.abilities, *abilities))
            if sheet.datasheet_id == "000004078"
            else sheet
            for sheet in definitions.package.army_catalog.datasheets
        ),
    )
    state.army_definitions[:] = [
        replace(
            army,
            units=tuple(
                replace(unit, datasheet_abilities=(*unit.datasheet_abilities, *abilities))
                if unit.datasheet_id == "000004078"
                else unit
                for unit in army.units
            ),
        )
        if army.player_id == "owner"
        else army
        for army in state.army_definitions
    ]
    records = tuple(
        r
        for r in catalog_ability_records_from_catalog(catalog)
        if r.definition.source_id.startswith("constructed:section08:")
    )
    runtime = CatalogCommandPointRuntime(
        {
            "owner": AbilityCatalogIndex.from_records(records),
            "opponent": AbilityCatalogIndex.from_records(()),
        },
        tuple(state.army_definitions),
    )
    index = RuntimeContentEventIndex.from_subscriptions(
        runtime.event_subscriptions(),
        handler_registry=RuntimeContentEventHandlerRegistry.from_bindings(
            runtime.event_handler_bindings()
        ),
    )
    config = replace(movement_session(definitions, state).lifecycle.config, army_catalog=catalog)
    command = CommandPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=catalog,
        runtime_event_index=index,
        command_phase_start_hooks=CommandPhaseStartHookRegistry.from_bindings(
            runtime_event_phase_hooks.command_start_bindings(index)
        ),
    )
    movement = MovementPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor, army_catalog=catalog
    )
    flow = BattleRoundFlow(
        phase_handlers={BattlePhase.COMMAND: command, BattlePhase.MOVEMENT: movement},
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=catalog,
        runtime_event_index=index,
        turn_end_hooks=TurnEndHookRegistry.from_bindings(
            runtime_event_phase_hooks.end_bindings(index)
        ),
    )
    return LocalGameSession(
        GameLifecycle(
            state=state,
            _config=config,
            _command_phase_handler=command,
            _movement_phase_handler=movement,
            _battle_round_flow=flow,
        )
    )
