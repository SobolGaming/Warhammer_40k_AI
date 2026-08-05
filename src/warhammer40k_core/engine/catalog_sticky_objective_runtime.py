from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.catalog_sticky_objective_support import (
    CATALOG_IR_COMMAND_END_STICKY_OBJECTIVE_CONSUMER_ID,
    clause_is_command_end_sticky_objective_control,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_id_for_unit_id, rules_unit_view_by_id
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlContext,
    PhaseEndObjectiveControlHandler,
    PhaseEndObjectiveControlHookBinding,
    StickyObjectiveControlState,
    apply_sticky_objective_control,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import RuleClause


@dataclass(frozen=True, slots=True)
class _StickySource:
    owner_player_id: str
    record: AbilityCatalogRecord
    clause: RuleClause

    @property
    def binding_id(self) -> str:
        return (
            f"{CATALOG_IR_COMMAND_END_STICKY_OBJECTIVE_CONSUMER_ID}:"
            f"{self.owner_player_id}:{self.record.record_id}:{self.clause.clause_id}"
        )


@dataclass(frozen=True, slots=True)
class CatalogStickyObjectiveRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        if set(self.ability_indexes_by_player_id) != {army.player_id for army in self.armies}:
            raise GameLifecycleError("Catalog sticky-objective indexes must match army player IDs.")

    def bindings(self) -> tuple[PhaseEndObjectiveControlHookBinding, ...]:
        return tuple(
            PhaseEndObjectiveControlHookBinding(
                hook_id=source.binding_id,
                source_id=source.record.definition.source_id,
                handler=self._handler(source),
            )
            for source in self._sources()
        )

    def _handler(self, source: _StickySource) -> PhaseEndObjectiveControlHandler:
        def handler(
            context: PhaseEndObjectiveControlContext,
        ) -> tuple[StickyObjectiveControlState, ...]:
            if context.completed_phase is not BattlePhase.COMMAND:
                return ()
            if context.state.active_player_id != source.owner_player_id:
                return ()
            army = _army_for_player(self.armies, source.owner_player_id)
            record = _current_objective_control_record(context)
            states: list[StickyObjectiveControlState] = []
            for unit in army.units:
                current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
                    state=context.state,
                    unit=unit,
                )
                if not current_model_ids or not catalog_rule_record_source_matches_unit(
                    record=source.record,
                    unit=unit,
                    current_model_instance_ids=current_model_ids,
                ):
                    continue
                states.extend(
                    _states_for_unit(
                        context=context,
                        source=source,
                        unit=unit,
                        army=army,
                        record=record,
                    )
                )
            return tuple(sorted(states, key=lambda state: state.state_id))

        return handler

    def _sources(self) -> tuple[_StickySource, ...]:
        sources: list[_StickySource] = []
        for player_id, index in self.ability_indexes_by_player_id.items():
            for record in index.records_for(TimingTriggerKind.END_PHASE):
                if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                    continue
                sources.extend(
                    _StickySource(
                        owner_player_id=player_id,
                        record=record,
                        clause=clause,
                    )
                    for clause in catalog_rule_clauses_from_record(record)
                    if clause_is_command_end_sticky_objective_control(clause)
                )
        return tuple(sorted(sources, key=lambda source: source.binding_id))


def catalog_sticky_objective_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[PhaseEndObjectiveControlHookBinding, ...]:
    return CatalogStickyObjectiveRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).bindings()


def _current_objective_control_record(
    context: PhaseEndObjectiveControlContext,
) -> ObjectiveControlRecord:
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            context.state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=context.completed_phase,
            ruleset_descriptor=context.state.runtime_ruleset_descriptor(),
            runtime_modifier_registry=context.runtime_modifier_registry,
        )
    )
    return apply_sticky_objective_control(
        record=record,
        states=tuple(context.state.sticky_objective_control_states),
    )


def _states_for_unit(
    *,
    context: PhaseEndObjectiveControlContext,
    source: _StickySource,
    unit: UnitInstance,
    army: ArmyDefinition,
    record: ObjectiveControlRecord,
) -> tuple[StickyObjectiveControlState, ...]:
    rules_unit_id = rules_unit_id_for_unit_id(
        armies=tuple(context.state.army_definitions),
        unit_instance_id=unit.unit_instance_id,
    )
    rules_unit = rules_unit_view_by_id(state=context.state, unit_instance_id=rules_unit_id)
    component_ids = set(rules_unit.component_unit_instance_ids)
    states: list[StickyObjectiveControlState] = []
    for result in record.results:
        if result.controlled_by_player_id != army.player_id or not any(
            contribution.unit_instance_id in component_ids for contribution in result.contributors
        ):
            continue
        source_event_id = (
            f"catalog-sticky-command-end:{context.state.game_id}:"
            f"round-{context.state.battle_round:02d}:{army.player_id}:"
            f"{result.objective_id}:{source.record.record_id}"
        )
        states.append(
            StickyObjectiveControlState(
                state_id=f"{source_event_id}:{rules_unit_id}",
                game_id=context.state.game_id,
                player_id=army.player_id,
                objective_id=result.objective_id,
                source_rule_id=source.record.definition.source_id,
                source_event_id=source_event_id,
                battle_round=context.state.battle_round,
                phase=context.completed_phase.value,
                active_player_id=army.player_id,
                originating_unit_instance_id=rules_unit_id,
                destroyed_unit_instance_id=rules_unit_id,
                replay_payload={
                    "catalog_record_id": source.record.record_id,
                    "source_clause_id": source.clause.clause_id,
                    "source_rule_id": source.record.definition.source_id,
                    "objective_id": result.objective_id,
                    "originating_unit_instance_id": rules_unit_id,
                    "retention_end_condition": (
                        "opponent_level_of_control_greater_than_source_player"
                    ),
                },
            )
        )
    return tuple(states)


def _army_for_player(armies: tuple[ArmyDefinition, ...], player_id: str) -> ArmyDefinition:
    for army in armies:
        if army.player_id == player_id:
            return army
    raise GameLifecycleError("Catalog sticky-objective player army is unknown.")
