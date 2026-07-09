from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilitySourceKind,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.catalog_command_point_support import (
    CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID,
    CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
    clause_is_supported_destroyed_unit_command_point_gain,
    clause_is_supported_phase_command_point_gain,
    clause_is_supported_phase_end_leadership_command_point_gain,
    clause_is_supported_stratagem_cost_modifier,
    command_point_effect_parameters,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_record_current_wargear_bearer_model_ids,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.command_points import CommandPointGainStatus, CommandPointSourceKind
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEventContext,
    RuntimeContentEventHandlerBinding,
    RuntimeContentEventResult,
    RuntimeContentEventSubscription,
    RuntimeEventHandler,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    rules_unit_id_for_unit_id,
    rules_unit_owner_player_id,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.runtime_modifiers import UnitCharacteristicModifierContext
from warhammer40k_core.engine.stratagem_cost_choice_hooks import (
    SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE,
    StratagemCostChoiceHookBinding,
    StratagemCostChoiceRequestContext,
    StratagemCostChoiceResultContext,
    source_result_payload_for_cost_choice,
)
from warhammer40k_core.engine.stratagem_cost_modifiers import (
    StratagemCostModifierBinding,
    StratagemCostModifierContext,
    StratagemCostModifierHandler,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_destroyed_hooks import (
    UnitDestroyedContext,
    UnitDestroyedHookBinding,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleTrigger,
    parameter_payload,
)

CATALOG_IR_STRATAGEM_COST_CHOICE_HOOK_ID = "catalog-ir:stratagem-cost-choice"
CATALOG_IR_STRATAGEM_COST_CHOICE_EVENT = "catalog_ir_stratagem_cost_choice_resolved"
CATALOG_IR_COMMAND_POINT_GAIN_EVENT = "catalog_ir_command_point_gain_resolved"
CATALOG_IR_COMMAND_POINT_PHASE_GAIN_EVENT = "catalog_ir_command_point_phase_gain_resolved"
CATALOG_IR_COMMAND_POINT_LEADERSHIP_TEST_EVENT = "catalog_ir_command_point_leadership_test_resolved"


@dataclass(frozen=True, slots=True)
class _CostSource:
    owner_player_id: str
    record: AbilityCatalogRecord
    clause: RuleClause
    source_unit_instance_id: str
    source_model_instance_id: str
    modifier_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "owner_player_id",
            _validate_identifier("Cost source owner_player_id", self.owner_player_id),
        )
        if type(self.record) is not AbilityCatalogRecord:
            raise GameLifecycleError("Cost source record must be AbilityCatalogRecord.")
        if type(self.clause) is not RuleClause:
            raise GameLifecycleError("Cost source clause must be RuleClause.")
        object.__setattr__(
            self,
            "source_unit_instance_id",
            _validate_identifier(
                "Cost source source_unit_instance_id",
                self.source_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "source_model_instance_id",
            _validate_identifier(
                "Cost source source_model_instance_id",
                self.source_model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "modifier_id",
            _validate_identifier("Cost source modifier_id", self.modifier_id),
        )

    @property
    def opportunity_id(self) -> str:
        return self.modifier_id


@dataclass(frozen=True, slots=True)
class _PhaseGainSource:
    owner_player_id: str
    record: AbilityCatalogRecord
    clause: RuleClause
    handler_id: str
    subscription_id: str


@dataclass(frozen=True, slots=True)
class CatalogCommandPointRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _validate_ability_indexes(self.ability_indexes_by_player_id)
        armies = _validate_armies(self.armies)
        if set(indexes) != {army.player_id for army in armies}:
            raise GameLifecycleError(
                "Catalog CP runtime ability indexes must match army player IDs."
            )
        object.__setattr__(
            self,
            "ability_indexes_by_player_id",
            indexes,
        )
        object.__setattr__(self, "armies", armies)

    def unit_destroyed_hook_bindings(self) -> tuple[UnitDestroyedHookBinding, ...]:
        if not self._has_destroyed_unit_gain_records():
            return ()
        return (
            UnitDestroyedHookBinding(
                hook_id=CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID,
                source_id=CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID,
                handler=self.resolve_unit_destroyed,
            ),
        )

    def stratagem_cost_choice_hook_bindings(self) -> tuple[StratagemCostChoiceHookBinding, ...]:
        if not any(_cost_source_is_optional(source) for source in self._cost_sources()):
            return ()
        return (
            StratagemCostChoiceHookBinding(
                hook_id=CATALOG_IR_STRATAGEM_COST_CHOICE_HOOK_ID,
                source_id=CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
                request_handler=self.stratagem_cost_choice_request,
                result_handler=self.apply_stratagem_cost_choice_result,
            ),
        )

    def stratagem_cost_modifier_bindings(self) -> tuple[StratagemCostModifierBinding, ...]:
        return tuple(
            StratagemCostModifierBinding(
                modifier_id=source.modifier_id,
                source_id=source.record.definition.source_id,
                handler=self._stratagem_cost_modifier_handler(source),
            )
            for source in self._cost_sources()
        )

    def event_handler_bindings(self) -> tuple[RuntimeContentEventHandlerBinding, ...]:
        return tuple(
            RuntimeContentEventHandlerBinding(
                handler_id=source.handler_id,
                handler=self._phase_gain_handler(source),
            )
            for source in self._phase_gain_sources()
        )

    def event_subscriptions(self) -> tuple[RuntimeContentEventSubscription, ...]:
        subscriptions: list[RuntimeContentEventSubscription] = []
        for source in self._phase_gain_sources():
            phase = parameter_payload(_required_trigger(source.clause).parameters)["phase"]
            if type(phase) is not str:
                raise GameLifecycleError("Command-point phase source phase is malformed.")
            subscriptions.append(
                RuntimeContentEventSubscription(
                    subscription_id=source.subscription_id,
                    source_rule_id=source.record.definition.source_id,
                    trigger_kind=source.record.definition.timing.trigger_kind,
                    handler_id=source.handler_id,
                    filters=MappingProxyType({"phase": phase, "player_id": source.owner_player_id}),
                )
            )
        return tuple(subscriptions)

    def resolve_unit_destroyed(self, context: UnitDestroyedContext) -> None:
        if type(context) is not UnitDestroyedContext:
            raise GameLifecycleError("Catalog CP unit-destroyed runtime requires context.")
        attacking_model_id = _payload_identifier(
            context.model_destroyed_payload,
            key="attacking_model_instance_id",
        )
        attacking_component_unit_id = context.state.unit_instance_id_for_model(attacking_model_id)
        army = _army_for_player(self.armies, player_id=context.destroying_player_id)
        unit = _unit_in_army(army, unit_instance_id=attacking_component_unit_id)
        index = self.ability_indexes_by_player_id.get(context.destroying_player_id)
        if index is None:
            raise GameLifecycleError("Catalog CP unit-destroyed runtime is missing ability index.")
        destroyed_view = rules_unit_view_by_id(
            state=context.state,
            unit_instance_id=context.destroyed_unit_instance_id,
        )
        destroyed_keywords = {*destroyed_view.keywords, *destroyed_view.faction_keywords}
        for record in index.records_for(TimingTriggerKind.AFTER_UNIT_DESTROYED):
            if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                continue
            if not _record_source_matches_runtime_unit(
                record=record,
                army=army,
                unit=unit,
                current_model_instance_ids=unit.own_model_ids(),
            ):
                continue
            if not _record_source_model_matches(
                record=record,
                army=army,
                unit=unit,
                source_model_instance_id=attacking_model_id,
            ):
                continue
            for clause in catalog_rule_clauses_from_record(record):
                if not clause_is_supported_destroyed_unit_command_point_gain(clause):
                    continue
                if not _destroyed_keywords_match(clause, destroyed_keywords=destroyed_keywords):
                    continue
                resolution_id = (
                    f"{context.model_destroyed_event_id}:{record.record_id}:{clause.clause_id}:"
                    f"{attacking_model_id}"
                )
                if _command_point_resolution_exists(
                    context.decisions.event_log.records,
                    resolution_id=resolution_id,
                ):
                    continue
                self._gain_command_points_from_destroyed_unit(
                    context=context,
                    record=record,
                    clause=clause,
                    attacking_model_id=attacking_model_id,
                    resolution_id=resolution_id,
                )

    def stratagem_cost_choice_request(
        self,
        context: StratagemCostChoiceRequestContext,
    ) -> DecisionRequest | None:
        if type(context) is not StratagemCostChoiceRequestContext:
            raise GameLifecycleError("Catalog Stratagem cost choice requires context.")
        for source in self._cost_sources():
            if not _cost_source_is_optional(source):
                continue
            if _cost_choice_answered(
                context,
                opportunity_id=source.opportunity_id,
            ):
                continue
            if not self._cost_source_is_eligible(source=source, context=context):
                continue
            return _cost_choice_request(context=context, source=source)
        return None

    def apply_stratagem_cost_choice_result(
        self,
        context: StratagemCostChoiceResultContext,
    ) -> bool:
        if type(context) is not StratagemCostChoiceResultContext:
            raise GameLifecycleError("Catalog Stratagem cost choice result requires context.")
        request_payload = _payload_object(context.request.payload, label="cost choice request")
        if request_payload.get("hook_id") != CATALOG_IR_STRATAGEM_COST_CHOICE_HOOK_ID:
            return False
        result_payload = _payload_object(context.result.payload, label="cost choice result")
        opportunity_id = _payload_identifier(result_payload, key="opportunity_id")
        source = self._cost_source_by_opportunity_id(opportunity_id)
        if not self._cost_source_is_eligible(source=source, context=context):
            raise GameLifecycleError("Catalog Stratagem cost opportunity is no longer eligible.")
        _validate_cost_choice_result_context(
            context=context,
            source=source,
            result_payload=result_payload,
        )
        use_ability = _payload_bool(result_payload, key="use_ability")
        context.decisions.event_log.append(
            CATALOG_IR_STRATAGEM_COST_CHOICE_EVENT,
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "active_player_id": context.eligibility_context.active_player_id,
                "phase": context.eligibility_context.phase.value,
                "player_id": source.owner_player_id,
                "source_rule_id": source.record.definition.source_id,
                "source_record_id": source.record.record_id,
                "source_clause_id": source.clause.clause_id,
                "hook_id": CATALOG_IR_STRATAGEM_COST_CHOICE_HOOK_ID,
                "modifier_id": source.modifier_id,
                "opportunity_id": source.opportunity_id,
                "source_unit_instance_id": source.source_unit_instance_id,
                "source_model_instance_id": source.source_model_instance_id,
                "stratagem_id": context.definition.stratagem_id,
                "stratagem_player_id": context.eligibility_context.player_id,
                "target_unit_instance_id": context.target_binding.target_unit_instance_id,
                "source_decision_request_id": context.source_request.request_id,
                "source_decision_result_id": context.source_result.result_id,
                "request_id": context.request.request_id,
                "result_id": context.result.result_id,
                "selected_option_id": context.result.selected_option_id,
                "use_ability": use_ability,
            },
        )
        return True

    def _gain_command_points_from_destroyed_unit(
        self,
        *,
        context: UnitDestroyedContext,
        record: AbilityCatalogRecord,
        clause: RuleClause,
        attacking_model_id: str,
        resolution_id: str,
    ) -> None:
        amount = _command_point_gain_amount(clause)
        gain = context.state.gain_command_points(
            player_id=context.destroying_player_id,
            amount=amount,
            source_id=record.definition.source_id,
            source_kind=CommandPointSourceKind.OTHER,
            cap_exempt=False,
        )
        context.decisions.event_log.append(
            "command_points_gained"
            if gain.status is CommandPointGainStatus.APPLIED
            else "command_points_gain_capped",
            gain.to_payload(),
        )
        context.decisions.event_log.append(
            CATALOG_IR_COMMAND_POINT_GAIN_EVENT,
            {
                "resolution_id": resolution_id,
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": context.completed_phase.value,
                "player_id": context.destroying_player_id,
                "source_rule_id": record.definition.source_id,
                "source_record_id": record.record_id,
                "source_clause_id": clause.clause_id,
                "source_model_instance_id": attacking_model_id,
                "destroyed_unit_instance_id": context.destroyed_unit_instance_id,
                "model_destroyed_event_id": context.model_destroyed_event_id,
                "command_point_result": gain.to_payload(),
            },
        )

    def _stratagem_cost_modifier_handler(
        self,
        source: _CostSource,
    ) -> StratagemCostModifierHandler:
        def handler(context: StratagemCostModifierContext) -> int:
            if type(context) is not StratagemCostModifierContext:
                raise GameLifecycleError("Catalog Stratagem cost modifier requires context.")
            if not self._cost_source_is_eligible(source=source, context=context):
                return context.current_command_point_cost
            parameters = command_point_effect_parameters(source.clause)
            delta = _mapping_int(parameters, key="delta")
            if _cost_source_is_optional(source):
                if context.source_decision_result_id is None:
                    if delta > 0:
                        return context.current_command_point_cost
                elif not _cost_choice_was_accepted(context=context, source=source):
                    return context.current_command_point_cost
            if (
                parameters.get("stacking") == "non_cumulative_cost_increase"
                and delta > 0
                and context.current_command_point_cost > context.base_command_point_cost
            ):
                return context.current_command_point_cost
            return context.current_command_point_cost + delta

        return handler

    def _phase_gain_handler(self, source: _PhaseGainSource) -> RuntimeEventHandler:
        subscription = RuntimeContentEventSubscription(
            subscription_id=source.subscription_id,
            source_rule_id=source.record.definition.source_id,
            trigger_kind=source.record.definition.timing.trigger_kind,
            handler_id=source.handler_id,
            filters=MappingProxyType({}),
        )

        def handler(context: RuntimeContentEventContext) -> RuntimeContentEventResult:
            if type(context) is not RuntimeContentEventContext:
                raise GameLifecycleError("Catalog CP phase-end runtime requires context.")
            if context.event.active_player_id != source.owner_player_id:
                return RuntimeContentEventResult.applied(
                    subscription,
                    replay_payload={"resolutions": []},
                )
            resolutions: list[JsonValue] = []
            army = _army_for_player(self.armies, player_id=source.owner_player_id)
            for unit in army.units:
                current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
                    state=context.state,
                    unit=unit,
                )
                if not current_model_ids or not _record_source_matches_runtime_unit(
                    record=source.record,
                    army=army,
                    unit=unit,
                    current_model_instance_ids=current_model_ids,
                ):
                    continue
                source_model_ids = _source_model_ids_for_record(
                    record=source.record,
                    army=army,
                    unit=unit,
                    current_model_instance_ids=current_model_ids,
                )
                for model_id in source_model_ids:
                    resolution = _resolve_phase_command_point_gain(
                        context=context,
                        source=source,
                        unit=unit,
                        source_model_instance_id=model_id,
                    )
                    resolutions.append(resolution)
            return RuntimeContentEventResult.applied(
                subscription,
                replay_payload=validate_json_value({"resolutions": resolutions}),
            )

        return handler

    def _cost_source_is_eligible(
        self,
        *,
        source: _CostSource,
        context: StratagemCostChoiceRequestContext
        | StratagemCostChoiceResultContext
        | StratagemCostModifierContext,
    ) -> bool:
        if context.target_binding is None:
            return False
        target_unit_id = context.target_binding.target_unit_instance_id
        target_player_id = context.target_binding.target_player_id
        if target_unit_id is None or target_player_id is None:
            return False
        stratagem_player_id = context.eligibility_context.player_id
        if target_player_id != stratagem_player_id:
            return False
        if (
            rules_unit_owner_player_id(
                state=context.state,
                unit_instance_id=target_unit_id,
            )
            != stratagem_player_id
        ):
            return False
        parameters = command_point_effect_parameters(source.clause)
        affected_player = parameters.get("affected_player")
        if affected_player == "source_player":
            if source.owner_player_id != stratagem_player_id:
                return False
        elif affected_player == "opponent":
            if source.owner_player_id == stratagem_player_id:
                return False
        else:
            raise GameLifecycleError("Catalog Stratagem cost affected_player is malformed.")
        if not _source_model_is_available(context.state, source=source):
            return False
        trigger_parameters = parameter_payload(_required_trigger(source.clause).parameters)
        relationship = trigger_parameters.get("source_relationship")
        if relationship == "stratagem_targets_source_unit":
            if rules_unit_id_for_unit_id(
                armies=self.armies,
                unit_instance_id=source.source_unit_instance_id,
            ) != rules_unit_id_for_unit_id(
                armies=self.armies,
                unit_instance_id=target_unit_id,
            ):
                return False
        elif relationship == "stratagem_targets_unit_within_source_model_range":
            if not _source_model_is_within_target_range(
                state=context.state,
                source_model_instance_id=source.source_model_instance_id,
                target_unit_instance_id=target_unit_id,
                range_inches=_cost_source_range_inches(source.clause),
            ):
                return False
        else:
            raise GameLifecycleError("Catalog Stratagem cost source relationship is malformed.")
        return not _cost_source_frequency_is_exhausted(source=source, context=context)

    def _cost_sources(self) -> tuple[_CostSource, ...]:
        sources: list[_CostSource] = []
        for army in self.armies:
            index = self.ability_indexes_by_player_id.get(army.player_id)
            if index is None:
                raise GameLifecycleError("Catalog CP runtime is missing player ability index.")
            for record in index.all_records():
                if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                    continue
                for clause in catalog_rule_clauses_from_record(record):
                    if not clause_is_supported_stratagem_cost_modifier(clause):
                        continue
                    for unit in army.units:
                        if not _record_source_matches_runtime_unit(
                            record=record,
                            army=army,
                            unit=unit,
                            current_model_instance_ids=unit.own_model_ids(),
                        ):
                            continue
                        model_ids = _source_model_ids_for_record(
                            record=record,
                            army=army,
                            unit=unit,
                            current_model_instance_ids=unit.own_model_ids(),
                        )
                        relationship = parameter_payload(_required_trigger(clause).parameters).get(
                            "source_relationship"
                        )
                        if relationship == "stratagem_targets_source_unit":
                            model_ids = model_ids[:1]
                        for model_id in model_ids:
                            modifier_id = (
                                f"{CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID}:"
                                f"{army.player_id}:{record.record_id}:{model_id}"
                            )
                            sources.append(
                                _CostSource(
                                    owner_player_id=army.player_id,
                                    record=record,
                                    clause=clause,
                                    source_unit_instance_id=unit.unit_instance_id,
                                    source_model_instance_id=model_id,
                                    modifier_id=modifier_id,
                                )
                            )
        return tuple(sorted(sources, key=lambda source: source.modifier_id))

    def _phase_gain_sources(self) -> tuple[_PhaseGainSource, ...]:
        sources: list[_PhaseGainSource] = []
        for player_id, index in self.ability_indexes_by_player_id.items():
            for trigger_kind in (TimingTriggerKind.START_PHASE, TimingTriggerKind.END_PHASE):
                for record in index.records_for(trigger_kind):
                    if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                        continue
                    for clause in catalog_rule_clauses_from_record(record):
                        if not clause_is_supported_phase_command_point_gain(clause):
                            continue
                        if _phase_gain_trigger_kind(clause) is not trigger_kind:
                            raise GameLifecycleError(
                                "Catalog CP phase gain ability timing descriptor drift."
                            )
                        digest = hashlib.sha256(
                            f"{player_id}:{record.record_id}:{clause.clause_id}".encode()
                        ).hexdigest()[:16]
                        sources.append(
                            _PhaseGainSource(
                                owner_player_id=player_id,
                                record=record,
                                clause=clause,
                                handler_id=f"catalog-ir:cp-phase:handler:{digest}",
                                subscription_id=f"catalog-ir:cp-phase:subscription:{digest}",
                            )
                        )
        return tuple(sorted(sources, key=lambda source: source.subscription_id))

    def _has_destroyed_unit_gain_records(self) -> bool:
        return any(
            record.definition.handler_id == GENERIC_RULE_IR_ABILITY_HANDLER_ID
            and any(
                clause_is_supported_destroyed_unit_command_point_gain(clause)
                for clause in catalog_rule_clauses_from_record(record)
            )
            for index in self.ability_indexes_by_player_id.values()
            for record in index.records_for(TimingTriggerKind.AFTER_UNIT_DESTROYED)
        )

    def _cost_source_by_opportunity_id(self, opportunity_id: str) -> _CostSource:
        requested_id = _validate_identifier("opportunity_id", opportunity_id)
        matches = tuple(
            source for source in self._cost_sources() if source.opportunity_id == requested_id
        )
        if len(matches) != 1:
            raise GameLifecycleError("Catalog Stratagem cost opportunity is unknown.")
        return matches[0]


def _cost_choice_request(
    *,
    context: StratagemCostChoiceRequestContext,
    source: _CostSource,
) -> DecisionRequest:
    return DecisionRequest(
        request_id=context.state.next_decision_request_id(),
        decision_type=SELECT_STRATAGEM_COST_MODIFIER_OPTION_DECISION_TYPE,
        actor_id=source.owner_player_id,
        payload={
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "active_player_id": context.eligibility_context.active_player_id,
            "phase": context.eligibility_context.phase.value,
            "source_rule_id": source.record.definition.source_id,
            "source_record_id": source.record.record_id,
            "source_clause_id": source.clause.clause_id,
            "hook_id": CATALOG_IR_STRATAGEM_COST_CHOICE_HOOK_ID,
            "modifier_id": source.modifier_id,
            "opportunity_id": source.opportunity_id,
            "source_unit_instance_id": source.source_unit_instance_id,
            "source_model_instance_id": source.source_model_instance_id,
            "stratagem_id": context.definition.stratagem_id,
            "stratagem_player_id": context.eligibility_context.player_id,
            "target_unit_instance_id": context.target_binding.target_unit_instance_id,
            "source_decision_request_id": context.source_request.request_id,
            "source_decision_result_id": context.source_result.result_id,
            "source_decision_result": source_result_payload_for_cost_choice(context.source_result),
        },
        options=(
            _cost_choice_option(context=context, source=source, use_ability=True),
            _cost_choice_option(context=context, source=source, use_ability=False),
        ),
    )


def _cost_choice_option(
    *,
    context: StratagemCostChoiceRequestContext,
    source: _CostSource,
    use_ability: bool,
) -> DecisionOption:
    action = "use" if use_ability else "decline"
    return DecisionOption(
        option_id=(
            f"catalog-ir:stratagem-cost:{context.source_result.result_id}:"
            f"{source.opportunity_id}:{action}"
        ),
        label="Use CP-altering ability" if use_ability else "Decline CP-altering ability",
        payload={
            "submission_kind": "catalog_ir_stratagem_cost_choice",
            "player_id": source.owner_player_id,
            "source_rule_id": source.record.definition.source_id,
            "source_record_id": source.record.record_id,
            "source_clause_id": source.clause.clause_id,
            "hook_id": CATALOG_IR_STRATAGEM_COST_CHOICE_HOOK_ID,
            "modifier_id": source.modifier_id,
            "opportunity_id": source.opportunity_id,
            "source_unit_instance_id": source.source_unit_instance_id,
            "source_model_instance_id": source.source_model_instance_id,
            "target_unit_instance_id": context.target_binding.target_unit_instance_id,
            "source_decision_request_id": context.source_request.request_id,
            "source_decision_result_id": context.source_result.result_id,
            "use_ability": use_ability,
        },
    )


def _validate_cost_choice_result_context(
    *,
    context: StratagemCostChoiceResultContext,
    source: _CostSource,
    result_payload: dict[str, JsonValue],
) -> None:
    expected = {
        "player_id": source.owner_player_id,
        "source_rule_id": source.record.definition.source_id,
        "source_record_id": source.record.record_id,
        "source_clause_id": source.clause.clause_id,
        "hook_id": CATALOG_IR_STRATAGEM_COST_CHOICE_HOOK_ID,
        "modifier_id": source.modifier_id,
        "opportunity_id": source.opportunity_id,
        "source_unit_instance_id": source.source_unit_instance_id,
        "source_model_instance_id": source.source_model_instance_id,
        "target_unit_instance_id": context.target_binding.target_unit_instance_id,
        "source_decision_request_id": context.source_request.request_id,
        "source_decision_result_id": context.source_result.result_id,
    }
    for key, expected_value in expected.items():
        if result_payload.get(key) != expected_value:
            raise GameLifecycleError(f"Catalog Stratagem cost choice {key} drift.")


def _cost_choice_answered(
    context: StratagemCostChoiceRequestContext,
    *,
    opportunity_id: str,
) -> bool:
    for record in context.decisions.event_log.records:
        if record.event_type != CATALOG_IR_STRATAGEM_COST_CHOICE_EVENT:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Catalog Stratagem cost choice event must be an object.")
        if (
            payload.get("source_decision_result_id") == context.source_result.result_id
            and payload.get("opportunity_id") == opportunity_id
        ):
            return True
    return False


def _cost_choice_was_accepted(
    *,
    context: StratagemCostModifierContext,
    source: _CostSource,
) -> bool:
    if context.decisions is None or context.source_decision_result_id is None:
        return False
    for record in context.decisions.event_log.records:
        if record.event_type != CATALOG_IR_STRATAGEM_COST_CHOICE_EVENT:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Catalog Stratagem cost choice event must be an object.")
        if (
            payload.get("source_decision_result_id") == context.source_decision_result_id
            and payload.get("opportunity_id") == source.opportunity_id
            and payload.get("use_ability") is True
        ):
            return True
    return False


def _cost_source_frequency_is_exhausted(
    *,
    source: _CostSource,
    context: StratagemCostChoiceRequestContext
    | StratagemCostChoiceResultContext
    | StratagemCostModifierContext,
) -> bool:
    scope = _cost_frequency_scope(source.clause)
    if scope is None:
        return False
    usage_scope = parameter_payload(_required_trigger(source.clause).parameters).get("usage_scope")
    modifier_prefix = (
        f"{CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID}:"
        f"{source.owner_player_id}:{source.record.record_id}:"
    )
    for use_record in context.state.stratagem_use_records:
        if not any(
            modifier_id == source.modifier_id
            if usage_scope == "source_model"
            else modifier_id.startswith(modifier_prefix)
            for modifier_id in use_record.command_point_modifier_ids
        ):
            continue
        if scope == "battle":
            return True
        if use_record.battle_round != context.state.battle_round:
            continue
        if scope == "battle round":
            return True
        if use_record.active_player_id != context.eligibility_context.active_player_id:
            continue
        if scope == "turn":
            return True
        if scope == "phase" and use_record.phase is context.eligibility_context.phase:
            return True
    return False


def _cost_frequency_scope(clause: RuleClause) -> str | None:
    frequencies = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.FREQUENCY_LIMIT
    )
    if not frequencies:
        return None
    if len(frequencies) != 1:
        raise GameLifecycleError("Catalog Stratagem cost frequency is ambiguous.")
    scope = parameter_payload(frequencies[0].parameters).get("scope")
    if type(scope) is not str:
        raise GameLifecycleError("Catalog Stratagem cost frequency scope is malformed.")
    return scope


def _cost_source_is_optional(source: _CostSource) -> bool:
    optional = command_point_effect_parameters(source.clause).get("optional")
    if type(optional) is not bool:
        raise GameLifecycleError("Catalog Stratagem cost optional flag is malformed.")
    return optional


def _cost_source_range_inches(clause: RuleClause) -> float:
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.DISTANCE_PREDICATE:
            continue
        distance = parameter_payload(condition.parameters).get("distance_inches")
        if isinstance(distance, int | float) and type(distance) is not bool:
            return float(distance)
    raise GameLifecycleError("Catalog Stratagem cost range is missing.")


def _source_model_is_available(state: object, *, source: _CostSource) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog Stratagem cost source requires GameState.")
    if state.battlefield_state is None:
        return False
    unit = _unit_by_id(tuple(state.army_definitions), source.source_unit_instance_id)
    model = _model_in_unit(unit, model_instance_id=source.source_model_instance_id)
    return (
        model.is_alive
        and state.battlefield_state.model_placement_or_none(source.source_model_instance_id)
        is not None
    )


def _source_model_is_within_target_range(
    *,
    state: object,
    source_model_instance_id: str,
    target_unit_instance_id: str,
    range_inches: float,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog Stratagem cost range requires GameState.")
    if state.battlefield_state is None:
        return False
    source_placement = state.battlefield_state.model_placement_or_none(source_model_instance_id)
    if source_placement is None:
        return False
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    source_model = geometry_model_for_placement(
        model=scenario.model_instance_for_placement(source_placement),
        placement=source_placement,
    )
    target_view = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_instance_id)
    for model in target_view.alive_models():
        target_placement = state.battlefield_state.model_placement_or_none(model.model_instance_id)
        if target_placement is None:
            continue
        target_model = geometry_model_for_placement(model=model, placement=target_placement)
        if source_model.range_to(target_model) <= range_inches:
            return True
    return False


def _resolve_phase_command_point_gain(
    *,
    context: RuntimeContentEventContext,
    source: _PhaseGainSource,
    unit: UnitInstance,
    source_model_instance_id: str,
) -> JsonValue:
    gate = _phase_gain_dice_gate(source.clause)
    roll_payload: JsonValue = None
    leadership_target: int | None = None
    success_threshold: int | None = None
    test_kind = "automatic"
    passed = True
    if gate is not None:
        gate_parameters = parameter_payload(gate.parameters)
        roll_count = _mapping_positive_int(gate_parameters, key="roll_count")
        if gate_parameters.get("roll_type") == "leadership":
            test_kind = "leadership"
            model = _model_in_unit(unit, model_instance_id=source_model_instance_id)
            base_leadership = _model_leadership(model)
            rules_unit_id = rules_unit_id_for_unit_id(
                armies=tuple(context.state.army_definitions),
                unit_instance_id=unit.unit_instance_id,
            )
            leadership_target = context.runtime_modifier_registry.modified_unit_characteristic(
                UnitCharacteristicModifierContext(
                    state=context.state,
                    unit_instance_id=rules_unit_id,
                    characteristic=Characteristic.LEADERSHIP,
                    base_value=base_leadership,
                    current_value=base_leadership,
                )
            )
            success_threshold = leadership_target
            roll_type = "catalog_ir.command_point_leadership_test"
            reason = f"Command-point Leadership test for {source_model_instance_id}"
        elif gate_parameters.get("roll_type") == "command_point_gain":
            test_kind = "fixed_roll"
            success_threshold = _mapping_positive_int(
                gate_parameters,
                key="success_threshold",
            )
            roll_type = "catalog_ir.command_point_gain_test"
            reason = f"Command-point gain test for {source_model_instance_id}"
        else:
            raise GameLifecycleError("Catalog CP phase gain roll_type is unsupported.")
        roll = DiceRollManager(
            context.state.game_id,
            event_log=context.decisions.event_log,
        ).roll(
            DiceRollSpec(
                expression=DiceExpression(quantity=roll_count, sides=6),
                reason=reason,
                roll_type=roll_type,
                actor_id=source_model_instance_id,
            )
        )
        roll_payload = cast(JsonValue, roll.to_payload())
        passed = roll.current_total >= success_threshold
    gain_payload: JsonValue = None
    if passed:
        gain = context.state.gain_command_points(
            player_id=source.owner_player_id,
            amount=_command_point_gain_amount(source.clause),
            source_id=source.record.definition.source_id,
            source_kind=CommandPointSourceKind.OTHER,
            cap_exempt=False,
        )
        gain_payload = cast(JsonValue, gain.to_payload())
        context.decisions.event_log.append(
            "command_points_gained"
            if gain.status is CommandPointGainStatus.APPLIED
            else "command_points_gain_capped",
            gain_payload,
        )
    resolution = validate_json_value(
        {
            "runtime_event_id": context.event.event_id,
            "game_id": context.state.game_id,
            "battle_round": context.state.battle_round,
            "phase": None if context.event.phase is None else context.event.phase.value,
            "player_id": source.owner_player_id,
            "source_rule_id": source.record.definition.source_id,
            "source_record_id": source.record.record_id,
            "source_clause_id": source.clause.clause_id,
            "source_unit_instance_id": unit.unit_instance_id,
            "source_model_instance_id": source_model_instance_id,
            "test_kind": test_kind,
            "success_threshold": success_threshold,
            "roll": roll_payload,
            "leadership_target": leadership_target,
            "leadership_roll": roll_payload if test_kind == "leadership" else None,
            "passed": passed,
            "command_point_result": gain_payload,
        }
    )
    context.decisions.event_log.append(
        (
            CATALOG_IR_COMMAND_POINT_LEADERSHIP_TEST_EVENT
            if clause_is_supported_phase_end_leadership_command_point_gain(source.clause)
            else CATALOG_IR_COMMAND_POINT_PHASE_GAIN_EVENT
        ),
        resolution,
    )
    return resolution


def _phase_gain_dice_gate(clause: RuleClause) -> RuleCondition | None:
    gates = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.DICE_ROLL_GATE
    )
    if len(gates) > 1:
        raise GameLifecycleError("Catalog CP phase gain has ambiguous dice gates.")
    return None if not gates else gates[0]


def _phase_gain_trigger_kind(clause: RuleClause) -> TimingTriggerKind:
    edge = parameter_payload(_required_trigger(clause).parameters).get("edge")
    if edge == "start":
        return TimingTriggerKind.START_PHASE
    if edge == "end":
        return TimingTriggerKind.END_PHASE
    raise GameLifecycleError("Catalog CP phase gain trigger edge is malformed.")


def _command_point_gain_amount(clause: RuleClause) -> int:
    return _mapping_positive_int(command_point_effect_parameters(clause), key="delta")


def _destroyed_keywords_match(clause: RuleClause, *, destroyed_keywords: set[str]) -> bool:
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.KEYWORD_GATE:
            continue
        parameters = parameter_payload(condition.parameters)
        if parameters.get("gate_subject") != "destroyed_unit":
            continue
        required = parameters.get("required_keyword_any")
        if type(required) is not tuple:
            raise GameLifecycleError("Destroyed-unit CP keyword gate is malformed.")
        return bool(set(required) & destroyed_keywords)
    raise GameLifecycleError("Destroyed-unit CP gain is missing keyword gate.")


def _record_source_model_matches(
    *,
    record: AbilityCatalogRecord,
    army: ArmyDefinition,
    unit: UnitInstance,
    source_model_instance_id: str,
) -> bool:
    if record.source_kind is AbilitySourceKind.DATASHEET:
        return source_model_instance_id in unit.own_model_ids()
    if record.source_kind is AbilitySourceKind.WARGEAR:
        return source_model_instance_id in catalog_rule_record_current_wargear_bearer_model_ids(
            record=record,
            unit=unit,
            current_model_instance_ids=unit.own_model_ids(),
        )
    if record.source_kind is AbilitySourceKind.ENHANCEMENT:
        return source_model_instance_id in _source_model_ids_for_record(
            record=record,
            army=army,
            unit=unit,
            current_model_instance_ids=unit.own_model_ids(),
        )
    return False


def _source_model_ids_for_record(
    *,
    record: AbilityCatalogRecord,
    army: ArmyDefinition,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> tuple[str, ...]:
    if record.source_kind is AbilitySourceKind.DATASHEET:
        return current_model_instance_ids
    if record.source_kind is AbilitySourceKind.WARGEAR:
        return catalog_rule_record_current_wargear_bearer_model_ids(
            record=record,
            unit=unit,
            current_model_instance_ids=current_model_instance_ids,
        )
    if record.source_kind is AbilitySourceKind.ENHANCEMENT:
        if not _enhancement_assignment_matches_unit(record=record, army=army, unit=unit):
            return ()
        if len(current_model_instance_ids) != 1:
            raise GameLifecycleError(
                "Catalog CP Enhancement bearer unit must resolve to exactly one current model."
            )
        return current_model_instance_ids
    return ()


def _record_source_matches_runtime_unit(
    *,
    record: AbilityCatalogRecord,
    army: ArmyDefinition,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> bool:
    if record.source_kind is AbilitySourceKind.ENHANCEMENT:
        return _enhancement_assignment_matches_unit(record=record, army=army, unit=unit)
    return catalog_rule_record_source_matches_unit(
        record=record,
        unit=unit,
        current_model_instance_ids=current_model_instance_ids,
    )


def _enhancement_assignment_matches_unit(
    *,
    record: AbilityCatalogRecord,
    army: ArmyDefinition,
    unit: UnitInstance,
) -> bool:
    if record.source_kind is not AbilitySourceKind.ENHANCEMENT:
        return False
    enhancement_id = record.definition.ability_id
    return any(
        assignment.enhancement_id == enhancement_id
        and f"{army.army_id}:{assignment.target_unit_selection_id}" == unit.unit_instance_id
        for assignment in army.enhancement_assignments
    )


def _command_point_resolution_exists(
    records: tuple[EventRecord, ...],
    *,
    resolution_id: str,
) -> bool:
    for record in records:
        if record.event_type != CATALOG_IR_COMMAND_POINT_GAIN_EVENT:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Catalog CP gain event payload must be an object.")
        if payload.get("resolution_id") == resolution_id:
            return True
    return False


def _required_trigger(clause: RuleClause) -> RuleTrigger:
    if clause.trigger is None:
        raise GameLifecycleError("Catalog CP supported clause is missing its trigger.")
    return clause.trigger


def _model_leadership(model: ModelInstance) -> int:
    for value in model.characteristics:
        if value.characteristic is Characteristic.LEADERSHIP:
            return value.final
    raise GameLifecycleError("Catalog CP source model is missing Leadership.")


def _army_for_player(armies: tuple[ArmyDefinition, ...], *, player_id: str) -> ArmyDefinition:
    requested_player = _validate_identifier("player_id", player_id)
    for army in armies:
        if army.player_id == requested_player:
            return army
    raise GameLifecycleError("Catalog CP runtime player army is unknown.")


def _unit_in_army(army: ArmyDefinition, *, unit_instance_id: str) -> UnitInstance:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for unit in army.units:
        if unit.unit_instance_id == requested_id:
            return unit
    raise GameLifecycleError("Catalog CP runtime unit is unknown.")


def _unit_by_id(armies: tuple[ArmyDefinition, ...], unit_instance_id: str) -> UnitInstance:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in armies:
        for unit in army.units:
            if unit.unit_instance_id == requested_id:
                return unit
    raise GameLifecycleError("Catalog CP runtime unit is unknown.")


def _model_in_unit(unit: UnitInstance, *, model_instance_id: str) -> ModelInstance:
    requested_id = _validate_identifier("model_instance_id", model_instance_id)
    for model in unit.own_models:
        if model.model_instance_id == requested_id:
            return model
    raise GameLifecycleError("Catalog CP runtime model is unknown.")


def _validate_ability_indexes(value: object) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Catalog CP runtime ability indexes must be a mapping.")
    indexes: dict[str, AbilityCatalogIndex] = {}
    for raw_player_id, raw_index in cast(Mapping[object, object], value).items():
        player_id = _validate_identifier("ability index player_id", raw_player_id)
        if type(raw_index) is not AbilityCatalogIndex:
            raise GameLifecycleError("Catalog CP runtime indexes must contain ability indexes.")
        indexes[player_id] = raw_index
    return MappingProxyType(dict(sorted(indexes.items())))


def _validate_armies(value: object) -> tuple[ArmyDefinition, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Catalog CP runtime armies must be a tuple.")
    armies: list[ArmyDefinition] = []
    for army in cast(tuple[object, ...], value):
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError("Catalog CP runtime armies must contain ArmyDefinition.")
        armies.append(army)
    return tuple(sorted(armies, key=lambda army: army.player_id))


def _payload_object(value: JsonValue, *, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Catalog Stratagem {label} payload must be an object.")
    return value


def _payload_identifier(payload: Mapping[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Catalog CP payload is missing {key}.")
    return _validate_identifier(key, payload[key])


def _payload_bool(payload: Mapping[str, JsonValue], *, key: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise GameLifecycleError(f"Catalog CP payload {key} must be a boolean.")
    return value


def _mapping_int(payload: Mapping[str, object], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Catalog CP parameter {key} must be an integer.")
    return value


def _mapping_positive_int(payload: Mapping[str, object], *, key: str) -> int:
    value = _mapping_int(payload, key=key)
    if value < 1:
        raise GameLifecycleError(f"Catalog CP parameter {key} must be positive.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)
