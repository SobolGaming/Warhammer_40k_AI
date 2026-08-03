from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_shock import battle_shock_leadership_target_for_unit
from warhammer40k_core.engine.catalog_attack_context_rule_runtime import rules_units_within
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.catalog_selectable_ability_mode_support import (
    BEGUILING_FORM_MODE_SEMANTIC,
    CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID,
    DAEMONIC_SPEED_MODE_SEMANTIC,
    ENTHRALLING_HYPNOSIS_MODE_SEMANTIC,
    SelectableAbilityModeOptionDescriptor,
    clause_is_command_phase_ability_mode_choice,
    selectable_ability_mode_option_descriptor,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartHookBinding,
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_view_by_id,
    rules_unit_views_from_armies,
)
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierBinding,
    HitRollModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import RuleClause, parameter_payload

CATALOG_ABILITY_MODE_SELECTED_EVENT = "catalog_command_phase_ability_mode_selected"
CATALOG_ABILITY_MODE_EFFECT_KIND = "catalog_command_phase_ability_mode"
CATALOG_ABILITY_MODE_FIGHTS_FIRST_EFFECT_KIND = "fights_first"
CATALOG_ABILITY_MODE_HIT_MODIFIER_ID = (
    f"{CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID}:hit-roll"
)
CATALOG_FALL_BACK_LEADERSHIP_TEST_EVENT = "catalog_fall_back_leadership_denial_test_resolved"


@dataclass(frozen=True, slots=True)
class _ModeOption:
    record: AbilityCatalogRecord
    clause: RuleClause
    descriptor: SelectableAbilityModeOptionDescriptor

    @property
    def source_rule_id(self) -> str:
        return rule_ir_from_execution_payload(self.record.definition.replay_payload).source_id


@dataclass(frozen=True, slots=True)
class _ModeSource:
    record: AbilityCatalogRecord
    clause: RuleClause
    unit: UnitInstance
    rules_unit: RulesUnitView
    source_model_instance_id: str
    options: tuple[_ModeOption, ...]

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (
            self.rules_unit.unit_instance_id,
            self.source_model_instance_id,
            self.record.record_id,
        )


@dataclass(frozen=True, slots=True)
class CatalogSelectableAbilityModeRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.ability_indexes_by_player_id), Mapping):
            raise GameLifecycleError("Catalog ability mode indexes must be a mapping.")
        if type(self.armies) is not tuple or any(
            type(army) is not ArmyDefinition for army in self.armies
        ):
            raise GameLifecycleError("Catalog ability mode runtime requires armies.")
        if set(self.ability_indexes_by_player_id) != {army.player_id for army in self.armies}:
            raise GameLifecycleError("Catalog ability mode indexes must match armies.")
        object.__setattr__(
            self,
            "ability_indexes_by_player_id",
            MappingProxyType(dict(self.ability_indexes_by_player_id)),
        )

    def bindings(self) -> tuple[CommandPhaseStartHookBinding, ...]:
        if not self._has_records():
            return ()
        return (
            CommandPhaseStartHookBinding(
                hook_id=CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID,
                source_id=CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID,
                request_handler=self.request,
                result_handler=self.apply_result,
            ),
        )

    def request(self, context: CommandPhaseStartRequestContext) -> DecisionRequest | None:
        if type(context) is not CommandPhaseStartRequestContext:
            raise GameLifecycleError("Catalog ability mode requires request context.")
        sources = tuple(
            source
            for player_id in sorted(self.ability_indexes_by_player_id)
            if player_id != context.active_player_id
            for source in self._sources_for_player(
                state=context.state,
                player_id=player_id,
            )
            if not _source_resolved_this_command(
                records=context.decisions.event_log.records,
                state=context.state,
                source=source,
            )
        )
        if not sources:
            return None
        source = sources[0]
        common = _common_payload(state=context.state, source=source)
        return DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
            actor_id=source.rules_unit.owner_player_id,
            payload=validate_json_value(
                {
                    **common,
                    "actor_may_be_non_active": True,
                    "available_mode_source_rule_ids": [
                        option.source_rule_id for option in source.options
                    ],
                }
            ),
            options=tuple(
                DecisionOption(
                    option_id=_option_id(source=source, option=option),
                    label=option.record.definition.name,
                    payload=validate_json_value(
                        {
                            **common,
                            "selected_mode_source_rule_id": option.source_rule_id,
                            "selected_mode_name": option.record.definition.name,
                            "selected_mode_semantic": option.descriptor.semantic,
                        }
                    ),
                )
                for option in source.options
            ),
        )

    def apply_result(self, context: CommandPhaseStartResultContext) -> bool:
        if type(context) is not CommandPhaseStartResultContext:
            raise GameLifecycleError("Catalog ability mode requires result context.")
        if context.request.decision_type != (
            SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
        ):
            return False
        request_payload = _payload_object(context.request.payload)
        if request_payload.get("hook_id") != CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID:
            return False
        context.result.validate_for_request(context.request)
        source = self._source_from_payload(state=context.state, payload=request_payload)
        if _source_resolved_this_command(
            records=context.decisions.event_log.records,
            state=context.state,
            source=source,
        ):
            raise GameLifecycleError("Catalog ability mode source was already resolved.")
        result_payload = _payload_object(context.result.payload)
        selected_source_rule_id = _payload_string(
            result_payload,
            "selected_mode_source_rule_id",
        )
        matches = tuple(
            option for option in source.options if option.source_rule_id == selected_source_rule_id
        )
        if len(matches) != 1:
            raise GameLifecycleError("Catalog ability mode option is no longer available.")
        option = matches[0]
        if context.result.selected_option_id != _option_id(source=source, option=option):
            raise GameLifecycleError("Catalog ability mode option ID drifted.")
        effect_payload: dict[str, JsonValue] = {
            "effect_kind": (
                CATALOG_ABILITY_MODE_FIGHTS_FIRST_EFFECT_KIND
                if option.descriptor.semantic == DAEMONIC_SPEED_MODE_SEMANTIC
                else CATALOG_ABILITY_MODE_EFFECT_KIND
            ),
            "mode_semantic": option.descriptor.semantic,
            "catalog_record_id": source.record.record_id,
            "source_rule_id": rule_ir_from_execution_payload(
                source.record.definition.replay_payload
            ).source_id,
            "source_rule_ir_hash": rule_ir_from_execution_payload(
                source.record.definition.replay_payload
            ).ir_hash(),
            "source_unit_instance_id": source.unit.unit_instance_id,
            "source_rules_unit_instance_id": source.rules_unit.unit_instance_id,
            "source_model_instance_id": source.source_model_instance_id,
            "selected_mode_source_rule_id": option.source_rule_id,
            "selected_mode_clause_id": option.clause.clause_id,
            "selected_mode_name": option.record.definition.name,
            "hit_roll_delta": option.descriptor.hit_roll_delta,
            "aura_range_inches": option.descriptor.aura_range_inches,
        }
        effect = PersistingEffect(
            effect_id=f"{context.result.result_id}:catalog-ability-mode",
            source_rule_id=option.source_rule_id,
            owner_player_id=source.rules_unit.owner_player_id,
            target_unit_instance_ids=(source.rules_unit.unit_instance_id,),
            started_battle_round=context.state.battle_round,
            started_phase=BattlePhaseKind.COMMAND,
            expiration=EffectExpiration.start_phase(
                battle_round=context.state.battle_round + 1,
                phase=BattlePhaseKind.COMMAND,
                player_id=context.active_player_id,
            ),
            effect_payload=validate_json_value(effect_payload),
        )
        context.state.record_persisting_effect(effect)
        context.decisions.event_log.append(
            CATALOG_ABILITY_MODE_SELECTED_EVENT,
            validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "phase": BattlePhase.COMMAND.value,
                    "active_player_id": context.active_player_id,
                    "player_id": source.rules_unit.owner_player_id,
                    "hook_id": CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID,
                    "catalog_record_id": source.record.record_id,
                    "source_rule_id": rule_ir_from_execution_payload(
                        source.record.definition.replay_payload
                    ).source_id,
                    "source_unit_instance_id": source.unit.unit_instance_id,
                    "source_rules_unit_instance_id": source.rules_unit.unit_instance_id,
                    "source_model_instance_id": source.source_model_instance_id,
                    "request_id": context.request.request_id,
                    "result_id": context.result.result_id,
                    "selected_option_id": context.result.selected_option_id,
                    "selected_mode_source_rule_id": option.source_rule_id,
                    "selected_mode_name": option.record.definition.name,
                    "selected_mode_semantic": option.descriptor.semantic,
                    "persisting_effect": effect.to_payload(),
                }
            ),
        )
        return True

    def _has_records(self) -> bool:
        return _has_mode_records(self.ability_indexes_by_player_id)

    def _sources_for_player(
        self,
        *,
        state: object,
        player_id: str,
    ) -> tuple[_ModeSource, ...]:
        from warhammer40k_core.engine.game_state import GameState

        if type(state) is not GameState:
            raise GameLifecycleError("Catalog ability mode source lookup requires GameState.")
        index = self.ability_indexes_by_player_id[player_id]
        sources: list[_ModeSource] = []
        for rules_unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
            if rules_unit.owner_player_id != player_id:
                continue
            for component in rules_unit.components:
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
                    for clause in catalog_rule_clauses_from_record(record):
                        if not clause_is_command_phase_ability_mode_choice(clause):
                            continue
                        options = _options_for_parent(index=index, parent=record, clause=clause)
                        sources.extend(
                            _ModeSource(
                                record=record,
                                clause=clause,
                                unit=unit,
                                rules_unit=rules_unit,
                                source_model_instance_id=model_id,
                                options=options,
                            )
                            for model_id in current_model_ids
                        )
        return tuple(sorted(sources, key=lambda source: source.sort_key))

    def _source_from_payload(
        self,
        *,
        state: object,
        payload: dict[str, JsonValue],
    ) -> _ModeSource:
        matches = tuple(
            source
            for source in self._sources_for_player(
                state=state,
                player_id=_payload_string(payload, "player_id"),
            )
            if source.record.record_id == _payload_string(payload, "catalog_record_id")
            and rule_ir_from_execution_payload(source.record.definition.replay_payload).source_id
            == _payload_string(payload, "source_rule_id")
            and source.clause.clause_id == _payload_string(payload, "clause_id")
            and source.unit.unit_instance_id == _payload_string(payload, "source_unit_instance_id")
            and source.rules_unit.unit_instance_id
            == _payload_string(payload, "source_rules_unit_instance_id")
            and source.source_model_instance_id
            == _payload_string(payload, "source_model_instance_id")
        )
        if len(matches) != 1:
            raise GameLifecycleError("Catalog ability mode source is no longer available.")
        return matches[0]


def catalog_selectable_ability_mode_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[CommandPhaseStartHookBinding, ...]:
    return CatalogSelectableAbilityModeRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).bindings()


def catalog_selectable_ability_mode_hit_roll_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> tuple[HitRollModifierBinding, ...]:
    if not _has_mode_records(ability_indexes_by_player_id):
        return ()
    return (
        HitRollModifierBinding(
            modifier_id=CATALOG_ABILITY_MODE_HIT_MODIFIER_ID,
            source_id=CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID,
            handler=_selected_mode_hit_roll_modifier,
        ),
    )


def _has_mode_records(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    return any(
        clause_is_command_phase_ability_mode_choice(clause)
        for index in ability_indexes_by_player_id.values()
        for record in index.all_records()
        if record.definition.handler_id == GENERIC_RULE_IR_ABILITY_HANDLER_ID
        for clause in catalog_rule_clauses_from_record(record)
    )


def resolve_catalog_fall_back_leadership_denial(
    *,
    state: object,
    decisions: object,
    target_unit_instance_id: str,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> bool:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog Fall Back denial requires GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Catalog Fall Back denial requires DecisionController.")
    target = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_instance_id)
    effects = _fall_back_denial_effects(state=state, target=target)
    if not effects:
        return False
    target_index = ability_indexes_by_player_id.get(target.owner_player_id)
    if target_index is None:
        raise GameLifecycleError("Catalog Fall Back denial missing target ability index.")
    target_components = tuple(
        (
            component,
            catalog_rule_current_placed_alive_model_instance_ids_for_unit(
                state=state,
                unit=component.unit,
            ),
        )
        for component in target.components
    )
    alive_target_components = tuple(
        (component, current_model_ids)
        for component, current_model_ids in target_components
        if current_model_ids
    )
    if not alive_target_components:
        raise GameLifecycleError("Catalog Fall Back denial target has no placed alive models.")
    target_leadership = min(
        battle_shock_leadership_target_for_unit(
            component.unit,
            current_model_ids=current_model_ids,
            ability_index=target_index,
            state=state,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        for component, current_model_ids in alive_target_components
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    for effect in effects:
        payload = _payload_object(effect.effect_payload)
        source_unit_id = _payload_string(payload, "source_rules_unit_instance_id")
        source_model_id = _payload_string(payload, "source_model_instance_id")
        aura_range = _payload_positive_float(payload, "aura_range_inches")
        if (
            state.battlefield_state is None
            or state.battlefield_state.model_placement_or_none(source_model_id) is None
        ):
            continue
        if not rules_units_within(
            state,
            source_unit_id,
            target.unit_instance_id,
            aura_range,
            attacker_model_instance_id=source_model_id,
        ):
            continue
        roll = manager.roll(
            DiceRollSpec(
                expression=DiceExpression(quantity=2, sides=6),
                reason=f"Fall Back Leadership test for {target.unit_instance_id}",
                roll_type="catalog.fall_back_leadership_denial",
                actor_id=target.owner_player_id,
            )
        )
        passed = roll.current_total >= target_leadership
        decisions.event_log.append(
            CATALOG_FALL_BACK_LEADERSHIP_TEST_EVENT,
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.MOVEMENT.value,
                    "active_player_id": state.active_player_id,
                    "target_unit_instance_id": target.unit_instance_id,
                    "target_player_id": target.owner_player_id,
                    "source_rule_id": effect.source_rule_id,
                    "source_unit_instance_id": source_unit_id,
                    "source_model_instance_id": source_model_id,
                    "leadership_target": target_leadership,
                    "roll": roll.to_payload(),
                    "passed": passed,
                    "fall_back_denied": not passed,
                }
            ),
        )
        if not passed:
            return True
    return False


def _options_for_parent(
    *,
    index: AbilityCatalogIndex,
    parent: AbilityCatalogRecord,
    clause: RuleClause,
) -> tuple[_ModeOption, ...]:
    option_ids = parameter_payload(clause.effects[0].parameters).get("option_source_rule_ids")
    if type(option_ids) is not tuple:
        raise GameLifecycleError("Catalog ability mode options are malformed.")
    options: list[_ModeOption] = []
    for source_rule_id in option_ids:
        if type(source_rule_id) is not str:
            raise GameLifecycleError("Catalog ability mode source rule ID is malformed.")
        matches = tuple(
            (record, candidate)
            for record in index.all_records()
            if record.definition.handler_id == GENERIC_RULE_IR_ABILITY_HANDLER_ID
            and rule_ir_from_execution_payload(record.definition.replay_payload).source_id
            == source_rule_id
            for candidate in catalog_rule_clauses_from_record(record)
            if (descriptor := selectable_ability_mode_option_descriptor(candidate)) is not None
        )
        if len(matches) != 1:
            raise GameLifecycleError("Catalog ability mode option source is missing or ambiguous.")
        record, option_clause = matches[0]
        descriptor = selectable_ability_mode_option_descriptor(option_clause)
        if descriptor is None:
            raise GameLifecycleError("Catalog ability mode option descriptor is unavailable.")
        options.append(_ModeOption(record=record, clause=option_clause, descriptor=descriptor))
    return tuple(options)


def _selected_mode_hit_roll_modifier(context: HitRollModifierContext) -> int:
    target = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.target_unit_instance_id,
    )
    modifiers: list[int] = []
    for effect in context.state.persisting_effects:
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if (
            payload.get("effect_kind") != CATALOG_ABILITY_MODE_EFFECT_KIND
            or payload.get("mode_semantic") != BEGUILING_FORM_MODE_SEMANTIC
            or not set(effect.target_unit_instance_ids).intersection(
                (target.unit_instance_id, *target.component_unit_instance_ids)
            )
        ):
            continue
        delta = payload.get("hit_roll_delta")
        if type(delta) is not int:
            raise GameLifecycleError("Catalog ability mode hit modifier is malformed.")
        modifiers.append(delta)
    if len(modifiers) > 1:
        raise GameLifecycleError("Multiple selectable ability mode hit modifiers apply.")
    return modifiers[0] if modifiers else 0


def _fall_back_denial_effects(
    *,
    state: object,
    target: RulesUnitView,
) -> tuple[PersistingEffect, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog Fall Back denial source lookup requires GameState.")
    effects: list[PersistingEffect] = []
    for effect in state.persisting_effects:
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if (
            payload.get("effect_kind") != CATALOG_ABILITY_MODE_EFFECT_KIND
            or payload.get("mode_semantic") != ENTHRALLING_HYPNOSIS_MODE_SEMANTIC
            or effect.owner_player_id == target.owner_player_id
        ):
            continue
        effects.append(effect)
    return tuple(sorted(effects, key=lambda effect: effect.effect_id))


def _common_payload(*, state: object, source: _ModeSource) -> dict[str, JsonValue]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState or state.active_player_id is None:
        raise GameLifecycleError("Catalog ability mode request requires active battle state.")
    rule_ir = rule_ir_from_execution_payload(source.record.definition.replay_payload)
    return {
        "submission_kind": "catalog_command_phase_ability_mode",
        "hook_id": CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID,
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "active_player_id": state.active_player_id,
        "player_id": source.rules_unit.owner_player_id,
        "catalog_record_id": source.record.record_id,
        "source_rule_id": rule_ir.source_id,
        "source_rule_ir_hash": rule_ir.ir_hash(),
        "clause_id": source.clause.clause_id,
        "source_unit_instance_id": source.unit.unit_instance_id,
        "source_rules_unit_instance_id": source.rules_unit.unit_instance_id,
        "source_model_instance_id": source.source_model_instance_id,
    }


def _source_resolved_this_command(
    *,
    records: tuple[EventRecord, ...],
    state: object,
    source: _ModeSource,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog ability mode resolution query requires GameState.")
    return any(
        event.event_type == CATALOG_ABILITY_MODE_SELECTED_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("game_id") == state.game_id
        and event.payload.get("battle_round") == state.battle_round
        and event.payload.get("active_player_id") == state.active_player_id
        and event.payload.get("catalog_record_id") == source.record.record_id
        and event.payload.get("source_model_instance_id") == source.source_model_instance_id
        for event in records
    )


def _option_id(*, source: _ModeSource, option: _ModeOption) -> str:
    return (
        f"{CATALOG_IR_COMMAND_PHASE_ABILITY_MODE_CONSUMER_ID}:"
        f"{source.source_model_instance_id}:{option.record.definition.ability_id}"
    )


def _payload_object(value: object) -> dict[str, JsonValue]:
    payload = validate_json_value(value)
    if not isinstance(payload, dict):
        raise GameLifecycleError("Catalog ability mode payload must be an object.")
    return payload


def _payload_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Catalog ability mode payload {key} must be text.")
    return value


def _payload_positive_float(payload: Mapping[str, object], key: str) -> float:
    value = payload.get(key)
    if not isinstance(value, int | float) or type(value) is bool or float(value) <= 0.0:
        raise GameLifecycleError(f"Catalog ability mode payload {key} must be positive.")
    return float(value)
