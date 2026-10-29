"""Constructed compiled text drives real phase effects; no ordering policy supplied."""

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
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.catalog_command_point_runtime import CatalogCommandPointRuntime
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEventHandlerRegistry,
    RuntimeContentEventIndex,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.engine.phases.shooting import ShootingPhaseHandler
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText


def timing_session(
    definitions: Section02Definitions, state: GameState, timing: str
) -> LocalGameSession:
    source = "constructed:section09:phase-effect"
    text = f"{timing}, roll one D6: on a 1+, you gain 1CP."
    rule = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id=source, raw_text=text, objective_scope=ObjectiveRuleScope.CORE_RULES
        ),
        source_keyword_sequence_parts=("CHARACTER", "INFANTRY"),
    ).rule_ir
    assert not rule.diagnostics
    assert all(c.is_supported for c in rule.clauses)
    ability = DatasheetAbilityDescriptor(
        ability_id=source,
        name="Constructed Movement timing contract",
        source_id=source,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )
    catalog = replace(
        definitions.package.army_catalog,
        datasheets=tuple(
            replace(s, abilities=(*s.abilities, ability)) if s.datasheet_id == "000004078" else s
            for s in definitions.package.army_catalog.datasheets
        ),
    )
    state.army_definitions[:] = [
        replace(
            a,
            units=tuple(
                replace(u, datasheet_abilities=(*u.datasheet_abilities, ability)) for u in a.units
            ),
        )
        if a.player_id == "owner"
        else a
        for a in state.army_definitions
    ]
    records = tuple(
        r for r in catalog_ability_records_from_catalog(catalog) if r.definition.source_id == source
    )
    assert records
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
    movement = MovementPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor, army_catalog=catalog
    )
    shooting = ShootingPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor, army_catalog=catalog
    )
    flow = BattleRoundFlow(
        phase_handlers={BattlePhase.MOVEMENT: movement, BattlePhase.SHOOTING: shooting},
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=catalog,
        runtime_event_index=index,
    )
    return LocalGameSession(
        GameLifecycle(
            state=state,
            _config=config,
            _movement_phase_handler=movement,
            _shooting_phase_handler=shooting,
            _battle_round_flow=flow,
        )
    )
