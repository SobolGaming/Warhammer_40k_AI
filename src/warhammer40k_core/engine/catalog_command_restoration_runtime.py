from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from warhammer40k_core.core.dice import D3RollResult, DiceExpression, DiceRollSpec
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_datasheet_rule_extensions import (
    CatalogCommandRestorationDescriptor,
    command_restoration_descriptor_for_clause,
)
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_COMMAND_RESTORATION_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    rules_unit_has_placed_alive_model,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartHookBinding,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.healing import HealingEffect, resolve_healing_until_blocked
from warhammer40k_core.engine.healing_geometry import (
    healing_opposing_player_id,
    healing_phase_start_enemy_engagement_model_ids,
    healing_phase_start_model_ids,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rule_execution import (
    rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.rule_target_resolution import unit_has_required_keywords
from warhammer40k_core.engine.rules_unit_geometry import geometry_models_for_rules_unit
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_views_from_armies
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import RuleClause, RuleIR

CATALOG_COMMAND_RESTORATION_SELECTION_KIND = "catalog_command_restoration"
CATALOG_COMMAND_RESTORATION_SELECTED_EVENT = "catalog_command_restoration_selected"
CATALOG_COMMAND_RESTORATION_ROLL_TYPE = "catalog.command_restoration_d3"


@dataclass(frozen=True, slots=True)
class _CommandRestorationSource:
    record: AbilityCatalogRecord
    rule_ir: RuleIR
    clause: RuleClause
    descriptor: CatalogCommandRestorationDescriptor
    unit: UnitInstance
    source_rules_unit: RulesUnitView
    source_model_instance_id: str

    @property
    def sort_key(self) -> tuple[str, str, str, str]:
        return (
            self.source_rules_unit.unit_instance_id,
            self.source_model_instance_id,
            self.record.record_id,
            self.clause.clause_id,
        )


@dataclass(frozen=True, slots=True)
class CatalogCommandRestorationRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.ability_indexes_by_player_id), Mapping):
            raise GameLifecycleError("Catalog command restoration indexes must be a mapping.")
        if type(self.armies) is not tuple or not all(
            type(army) is ArmyDefinition for army in self.armies
        ):
            raise GameLifecycleError("Catalog command restoration requires armies.")
        player_ids = {army.player_id for army in self.armies}
        if set(self.ability_indexes_by_player_id) != player_ids:
            raise GameLifecycleError("Catalog command restoration indexes must match armies.")
        object.__setattr__(
            self,
            "ability_indexes_by_player_id",
            MappingProxyType(dict(self.ability_indexes_by_player_id)),
        )

    def bindings(self) -> tuple[CommandPhaseStartHookBinding, ...]:
        if not self._has_runtime_records():
            return ()
        return (
            CommandPhaseStartHookBinding(
                hook_id=CATALOG_IR_COMMAND_RESTORATION_CONSUMER_ID,
                source_id=CATALOG_IR_COMMAND_RESTORATION_CONSUMER_ID,
                request_handler=self.request,
                result_handler=self.apply_result,
            ),
        )

    def request(self, context: CommandPhaseStartRequestContext) -> DecisionRequest | None:
        if type(context) is not CommandPhaseStartRequestContext:
            raise GameLifecycleError("Catalog command restoration requires request context.")
        sources = self._sources_for_player(
            state=context.state,
            player_id=context.active_player_id,
        )
        selected_target_ids = _selected_target_ids_this_turn(
            records=context.decisions.event_log.records,
            state=context.state,
            player_id=context.active_player_id,
        )
        for source in sources:
            if _source_resolved_this_turn(
                records=context.decisions.event_log.records,
                state=context.state,
                source=source,
            ):
                continue
            targets = tuple(
                target
                for target in self._eligible_targets(state=context.state, source=source)
                if target.unit_instance_id not in selected_target_ids
            )
            if not targets:
                continue
            common = _common_payload(state=context.state, source=source)
            return DecisionRequest(
                request_id=context.state.next_decision_request_id(),
                decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
                actor_id=context.active_player_id,
                payload=validate_json_value(common),
                options=tuple(
                    DecisionOption(
                        option_id=_option_id(
                            source_model_instance_id=source.source_model_instance_id,
                            target_unit_instance_id=target.unit_instance_id,
                        ),
                        label=f"Tears of Isha: {_rules_unit_label(target)}",
                        payload=validate_json_value(
                            {
                                **common,
                                "target_unit_instance_id": target.unit_instance_id,
                                "target_unit_name": _rules_unit_label(target),
                                "target_component_unit_instance_ids": list(
                                    target.component_unit_instance_ids
                                ),
                            }
                        ),
                    )
                    for target in targets
                ),
            )
        return None

    def apply_result(self, context: CommandPhaseStartResultContext) -> bool:
        if type(context) is not CommandPhaseStartResultContext:
            raise GameLifecycleError("Catalog command restoration requires result context.")
        if (
            context.request.decision_type
            != SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
        ):
            return False
        request_payload = _payload_object(context.request.payload)
        if request_payload.get("hook_id") != CATALOG_IR_COMMAND_RESTORATION_CONSUMER_ID:
            return False
        context.result.validate_for_request(context.request)
        result_payload = _payload_object(context.result.payload)
        source = self._source_from_payload(state=context.state, payload=request_payload)
        target_id = _payload_string(result_payload, "target_unit_instance_id")
        target = next(
            (
                candidate
                for candidate in self._eligible_targets(state=context.state, source=source)
                if candidate.unit_instance_id == target_id
            ),
            None,
        )
        if target is None:
            raise GameLifecycleError("Catalog command restoration target is no longer eligible.")
        if target_id in _selected_target_ids_this_turn(
            records=context.decisions.event_log.records,
            state=context.state,
            player_id=context.active_player_id,
        ):
            raise GameLifecycleError("Catalog command restoration target was already selected.")
        if context.result.selected_option_id != _option_id(
            source_model_instance_id=source.source_model_instance_id,
            target_unit_instance_id=target_id,
        ):
            raise GameLifecycleError("Catalog command restoration option ID drift.")
        d3_result = None
        if _rules_unit_has_destroyed_models(state=context.state, rules_unit=target):
            amount = source.descriptor.returned_models
            source_flags = {
                "revive_destroyed_models_only": True,
                "revive_model_full_health": True,
            }
        else:
            d3_result = _roll_restoration_d3(
                state=context.state,
                decisions=context.decisions,
                source=source,
                target=target,
            )
            amount = d3_result.value
            source_flags = {
                "heal_wounded_models_only": True,
                "single_model_heal": True,
            }
        source_context = validate_json_value(
            {
                "hook_id": CATALOG_IR_COMMAND_RESTORATION_CONSUMER_ID,
                "selection_kind": CATALOG_COMMAND_RESTORATION_SELECTION_KIND,
                "battle_round": context.state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "player_id": context.active_player_id,
                "source_rule_id": source.record.definition.source_id,
                "source_model_instance_id": source.source_model_instance_id,
                "target_unit_instance_id": target.unit_instance_id,
                "request_id": context.request.request_id,
                "result_id": context.result.result_id,
                "selected_option_id": context.result.selected_option_id,
                "d3_result": None if d3_result is None else d3_result.to_payload(),
                **source_flags,
            }
        )
        effect = HealingEffect(
            effect_id=(f"{CATALOG_IR_COMMAND_RESTORATION_CONSUMER_ID}:{context.result.result_id}"),
            target_unit_instance_id=target.unit_instance_id,
            amount=amount,
            opposing_player_id=healing_opposing_player_id(
                state=context.state,
                player_id=context.active_player_id,
            ),
            selection_actor_player_id=context.active_player_id,
            source_rule_id=source.record.definition.source_id,
            source_context=source_context,
            phase_start_model_ids=healing_phase_start_model_ids(
                state=context.state,
                rules_unit=target,
            ),
            phase_start_enemy_engagement_model_ids=(
                healing_phase_start_enemy_engagement_model_ids(
                    state=context.state,
                    rules_unit=target,
                )
            ),
        )
        resolved_effect, pending_request = resolve_healing_until_blocked(
            state=context.state,
            decisions=context.decisions,
            ruleset_descriptor=context.state.runtime_ruleset_descriptor(),
            effect=effect,
        )
        context.decisions.event_log.append(
            CATALOG_COMMAND_RESTORATION_SELECTED_EVENT,
            validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "phase": BattlePhase.COMMAND.value,
                    "player_id": context.active_player_id,
                    "hook_id": CATALOG_IR_COMMAND_RESTORATION_CONSUMER_ID,
                    "selection_kind": CATALOG_COMMAND_RESTORATION_SELECTION_KIND,
                    "catalog_record_id": source.record.record_id,
                    "source_rule_id": source.record.definition.source_id,
                    "source_rule_ir_hash": source.rule_ir.ir_hash(),
                    "clause_id": source.clause.clause_id,
                    "source_rules_unit_instance_id": (source.source_rules_unit.unit_instance_id),
                    "source_unit_instance_id": source.unit.unit_instance_id,
                    "source_model_instance_id": source.source_model_instance_id,
                    "target_unit_instance_id": target.unit_instance_id,
                    "request_id": context.request.request_id,
                    "result_id": context.result.result_id,
                    "selected_option_id": context.result.selected_option_id,
                    "d3_result": None if d3_result is None else d3_result.to_payload(),
                    "healing_effect": resolved_effect.to_payload(),
                    "pending_healing_request_id": (
                        None if pending_request is None else pending_request.request_id
                    ),
                }
            ),
        )
        return True

    def selection_is_current(
        self,
        *,
        state: object,
        decisions: DecisionController,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> bool:
        from warhammer40k_core.engine.game_state import GameState

        if type(state) is not GameState:
            raise GameLifecycleError("Catalog command restoration validation requires state.")
        if (
            state.current_battle_phase is not BattlePhase.COMMAND
            or state.active_player_id != request.actor_id
        ):
            return False
        request_payload = _payload_object(request.payload)
        source = self._source_from_payload(state=state, payload=request_payload)
        if _source_resolved_this_turn(
            records=decisions.event_log.records,
            state=state,
            source=source,
        ):
            return False
        target_id = _payload_string(_payload_object(result.payload), "target_unit_instance_id")
        if target_id in _selected_target_ids_this_turn(
            records=decisions.event_log.records,
            state=state,
            player_id=source.source_rules_unit.owner_player_id,
        ):
            return False
        return target_id in {
            target.unit_instance_id for target in self._eligible_targets(state=state, source=source)
        }

    def _sources_for_player(
        self,
        *,
        state: object,
        player_id: str,
    ) -> tuple[_CommandRestorationSource, ...]:
        from warhammer40k_core.engine.game_state import GameState

        if type(state) is not GameState:
            raise GameLifecycleError("Catalog command restoration source lookup requires state.")
        index = self.ability_indexes_by_player_id[player_id]
        sources: list[_CommandRestorationSource] = []
        for view in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
            if view.owner_player_id != player_id:
                continue
            for component in view.components:
                unit = component.unit
                current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
                    state=state,
                    unit=unit,
                )
                if not current_model_ids:
                    continue
                for record in index.all_records():
                    if (
                        record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID
                        or not catalog_rule_record_source_matches_unit(
                            record=record,
                            unit=unit,
                            current_model_instance_ids=current_model_ids,
                        )
                    ):
                        continue
                    rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
                    for clause in catalog_rule_clauses_from_record(record):
                        descriptor = command_restoration_descriptor_for_clause(clause)
                        if descriptor is None:
                            continue
                        sources.extend(
                            _CommandRestorationSource(
                                record=record,
                                rule_ir=rule_ir,
                                clause=clause,
                                descriptor=descriptor,
                                unit=unit,
                                source_rules_unit=view,
                                source_model_instance_id=model_id,
                            )
                            for model_id in current_model_ids
                        )
        return tuple(sorted(sources, key=lambda source: source.sort_key))

    def _source_from_payload(
        self,
        *,
        state: object,
        payload: dict[str, JsonValue],
    ) -> _CommandRestorationSource:
        matches = tuple(
            source
            for source in self._sources_for_player(
                state=state,
                player_id=_payload_string(payload, "player_id"),
            )
            if source.record.record_id == _payload_string(payload, "catalog_record_id")
            and source.record.definition.source_id == _payload_string(payload, "source_rule_id")
            and source.rule_ir.ir_hash() == _payload_string(payload, "source_rule_ir_hash")
            and source.clause.clause_id == _payload_string(payload, "clause_id")
            and source.source_rules_unit.unit_instance_id
            == _payload_string(payload, "source_rules_unit_instance_id")
            and source.unit.unit_instance_id == _payload_string(payload, "source_unit_instance_id")
            and source.source_model_instance_id
            == _payload_string(payload, "source_model_instance_id")
        )
        if len(matches) != 1:
            raise GameLifecycleError("Catalog command restoration source is no longer available.")
        return matches[0]

    def _eligible_targets(
        self,
        *,
        state: object,
        source: _CommandRestorationSource,
    ) -> tuple[RulesUnitView, ...]:
        from warhammer40k_core.engine.game_state import GameState

        if type(state) is not GameState:
            raise GameLifecycleError("Catalog command restoration target lookup requires state.")
        source_models = tuple(
            model
            for model in geometry_models_for_rules_unit(
                state=state,
                unit_instance_id=source.source_rules_unit.unit_instance_id,
            )
            if model.model_id == source.source_model_instance_id
        )
        if len(source_models) != 1:
            raise GameLifecycleError("Catalog command restoration source model is not placed.")
        source_model = source_models[0]
        targets: list[RulesUnitView] = []
        for view in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
            if view.owner_player_id != source.source_rules_unit.owner_player_id:
                continue
            if not rules_unit_has_placed_alive_model(state=state, rules_unit=view):
                continue
            if not unit_has_required_keywords(
                unit_keywords=view.keywords,
                faction_keywords=view.faction_keywords,
                required_keywords=source.descriptor.required_keyword_sequence,
            ):
                continue
            if any(
                source_model.range_to(target_model) <= source.descriptor.distance_inches
                for target_model in geometry_models_for_rules_unit(
                    state=state,
                    unit_instance_id=view.unit_instance_id,
                )
            ):
                targets.append(view)
        return tuple(sorted(targets, key=lambda target: target.unit_instance_id))

    def _has_runtime_records(self) -> bool:
        return any(
            command_restoration_descriptor_for_clause(clause) is not None
            for index in self.ability_indexes_by_player_id.values()
            for record in index.all_records()
            if record.definition.handler_id == GENERIC_RULE_IR_ABILITY_HANDLER_ID
            for clause in catalog_rule_clauses_from_record(record)
        )


def catalog_command_restoration_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[CommandPhaseStartHookBinding, ...]:
    return CatalogCommandRestorationRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).bindings()


def invalid_catalog_command_restoration_status(
    *,
    state: object,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog command restoration validation requires state.")
    request_payload = _payload_object(request.payload)
    if request_payload.get("hook_id") != CATALOG_IR_COMMAND_RESTORATION_CONSUMER_ID:
        return None
    runtime = CatalogCommandRestorationRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=tuple(state.army_definitions),
    )
    if runtime.selection_is_current(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    ):
        return None
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Catalog command restoration selection no longer matches game state.",
        payload={
            "invalid_reason": "invalid_catalog_command_restoration_result",
            "field": "current_options",
        },
    )


def _roll_restoration_d3(
    *,
    state: object,
    decisions: DecisionController,
    source: _CommandRestorationSource,
    target: RulesUnitView,
) -> D3RollResult:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog command restoration roll requires GameState.")
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Command restoration for {_rules_unit_label(target)}",
            roll_type=CATALOG_COMMAND_RESTORATION_ROLL_TYPE,
            actor_id=source.source_model_instance_id,
        )
    )
    return D3RollResult.from_source_d6_result(roll_state.original_result)


def _rules_unit_has_destroyed_models(*, state: object, rules_unit: RulesUnitView) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState or state.battlefield_state is None:
        raise GameLifecycleError("Catalog command restoration requires battlefield state.")
    removed_ids = set(state.battlefield_state.removed_model_ids)
    return any(
        not model.is_alive and model.model_instance_id in removed_ids
        for model in rules_unit.own_models
    )


def _selected_target_ids_this_turn(
    *,
    records: tuple[EventRecord, ...],
    state: object,
    player_id: str,
) -> set[str]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog command restoration event lookup requires state.")
    selected: set[str] = set()
    for record in records:
        if record.event_type != CATALOG_COMMAND_RESTORATION_SELECTED_EVENT:
            continue
        payload = _event_payload(record)
        if (
            payload.get("game_id") == state.game_id
            and payload.get("battle_round") == state.battle_round
            and payload.get("player_id") == player_id
            and payload.get("phase") == BattlePhase.COMMAND.value
        ):
            selected.add(_payload_string(payload, "target_unit_instance_id"))
    return selected


def _source_resolved_this_turn(
    *,
    records: tuple[EventRecord, ...],
    state: object,
    source: _CommandRestorationSource,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog command restoration event lookup requires state.")
    return any(
        record.event_type == CATALOG_COMMAND_RESTORATION_SELECTED_EVENT
        and _event_payload(record).get("game_id") == state.game_id
        and _event_payload(record).get("battle_round") == state.battle_round
        and _event_payload(record).get("player_id") == source.source_rules_unit.owner_player_id
        and _event_payload(record).get("source_rule_id") == source.record.definition.source_id
        and _event_payload(record).get("source_model_instance_id")
        == source.source_model_instance_id
        for record in records
    )


def _common_payload(
    *,
    state: object,
    source: _CommandRestorationSource,
) -> dict[str, JsonValue]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog command restoration payload requires state.")
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.COMMAND.value,
                "active_player_id": state.active_player_id,
                "player_id": source.source_rules_unit.owner_player_id,
                "hook_id": CATALOG_IR_COMMAND_RESTORATION_CONSUMER_ID,
                "selection_kind": CATALOG_COMMAND_RESTORATION_SELECTION_KIND,
                "catalog_record_id": source.record.record_id,
                "source_rule_id": source.record.definition.source_id,
                "source_rule_ir_hash": source.rule_ir.ir_hash(),
                "clause_id": source.clause.clause_id,
                "source_rules_unit_instance_id": source.source_rules_unit.unit_instance_id,
                "source_unit_instance_id": source.unit.unit_instance_id,
                "source_model_instance_id": source.source_model_instance_id,
            }
        ),
    )


def _rules_unit_label(rules_unit: RulesUnitView) -> str:
    return " + ".join(component.unit.name for component in rules_unit.components)


def _option_id(*, source_model_instance_id: str, target_unit_instance_id: str) -> str:
    return f"catalog-command-restoration:{source_model_instance_id}:{target_unit_instance_id}"


def _payload_object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Catalog command restoration payload must be an object.")
    return value


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Catalog command restoration payload missing {key}.")
    return value


def _event_payload(record: EventRecord) -> dict[str, JsonValue]:
    return _payload_object(record.payload)


__all__ = (
    "CATALOG_COMMAND_RESTORATION_SELECTED_EVENT",
    "catalog_command_restoration_bindings",
    "invalid_catalog_command_restoration_status",
)
