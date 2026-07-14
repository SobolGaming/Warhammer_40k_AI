from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_formation_hooks import (
    BattleFormationHookBinding,
    BattleFormationRequestContext,
)
from warhammer40k_core.engine.battle_round_hooks import (
    BattleRoundStartHookBinding,
    BattleRoundStartRequestContext,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_TRACKED_TARGET_DESTROYED_RESELECT_CONSUMER_ID,
    CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID,
    catalog_rule_clause_is_supported_tracked_target_destroyed_reselect,
    catalog_rule_clause_is_supported_tracked_target_selection,
    catalog_rule_clauses_from_record,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_record_current_wargear_bearer_model_ids,
    catalog_rule_record_source_matches_unit,
    catalog_rule_tracked_target_supported_attack_roll_pairs_for_clause,
    catalog_rule_unit_scoped_generic_records,
)
from warhammer40k_core.engine.catalog_tracked_target_selection_descriptors import (
    START_BATTLE_TRACKED_TARGET_SELECTION_TEMPLATE_ID,
    tracked_target_selection_descriptor_for_clause,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id, rules_unit_view_from_armies
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.tracked_targets import (
    TRACKED_TARGET_EXPIRED_EVENT_TYPE,
    TrackedTargetOwnerScope,
    TrackedTargetRecord,
    TrackedTargetRole,
    build_select_tracked_target_request,
)
from warhammer40k_core.engine.unit_destroyed_hooks import (
    UnitDestroyedContext,
    UnitDestroyedHookBinding,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleEffectSpec,
    RuleTriggerKind,
    parameter_payload,
)


@dataclass(frozen=True, slots=True)
class CatalogTrackedTargetRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def battle_formation_bindings(self) -> tuple[BattleFormationHookBinding, ...]:
        if not _has_start_battle_tracked_target_selection_records(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id
        ):
            return ()
        return (
            BattleFormationHookBinding(
                hook_id=f"{CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID}:start-battle",
                source_id=CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID,
                request_handler=self.battle_formation_request,
            ),
        )

    def battle_round_start_bindings(self) -> tuple[BattleRoundStartHookBinding, ...]:
        if not _has_tracked_target_selection_records(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id
        ):
            return ()
        return (
            BattleRoundStartHookBinding(
                hook_id=CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID,
                source_id=CATALOG_IR_TRACKED_TARGET_SELECTION_CONSUMER_ID,
                request_handler=self.battle_round_start_request,
            ),
        )

    def unit_destroyed_bindings(self) -> tuple[UnitDestroyedHookBinding, ...]:
        if not _has_tracked_target_reselection_records(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id
        ):
            return ()
        return (
            UnitDestroyedHookBinding(
                hook_id=CATALOG_IR_TRACKED_TARGET_DESTROYED_RESELECT_CONSUMER_ID,
                source_id=CATALOG_IR_TRACKED_TARGET_DESTROYED_RESELECT_CONSUMER_ID,
                handler=self.unit_destroyed_handler,
            ),
        )

    def battle_round_start_request(
        self,
        context: BattleRoundStartRequestContext,
    ) -> DecisionRequest | None:
        for request in _tracked_target_initial_selection_requests(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=context,
        ):
            return request
        return None

    def battle_formation_request(
        self,
        context: BattleFormationRequestContext,
    ) -> DecisionRequest | None:
        for request in _tracked_target_start_battle_selection_requests(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=context,
        ):
            return request
        return None

    def unit_destroyed_handler(self, context: UnitDestroyedContext) -> None:
        if context.decisions.queue.pending_requests:
            return
        for record in context.state.tracked_targets_for_destroyed_unit(
            destroyed_unit_instance_id=context.destroyed_unit_instance_id
        ):
            expired = context.state.expire_tracked_target(record.record_id)
            context.decisions.event_log.append(
                TRACKED_TARGET_EXPIRED_EVENT_TYPE,
                {
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "phase": context.completed_phase.value,
                    "destroyed_unit_instance_id": context.destroyed_unit_instance_id,
                    "model_destroyed_event_id": context.model_destroyed_event_id,
                    "tracked_target_record": expired.to_payload(),
                },
            )
            request = _tracked_target_reselection_request(
                ability_indexes_by_player_id=self.ability_indexes_by_player_id,
                armies=self.armies,
                context=context,
                expired_record=expired,
            )
            if request is not None:
                context.decisions.request_decision(request)
                return


def catalog_tracked_target_battle_round_start_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[BattleRoundStartHookBinding, ...]:
    return CatalogTrackedTargetRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).battle_round_start_bindings()


def catalog_tracked_target_battle_formation_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[BattleFormationHookBinding, ...]:
    return CatalogTrackedTargetRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).battle_formation_bindings()


def catalog_tracked_target_unit_destroyed_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[UnitDestroyedHookBinding, ...]:
    return CatalogTrackedTargetRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).unit_destroyed_bindings()


def _tracked_target_initial_selection_requests(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    context: BattleRoundStartRequestContext,
) -> tuple[DecisionRequest, ...]:
    requests: list[DecisionRequest] = []
    for army in sorted(armies, key=lambda item: item.player_id):
        index = ability_indexes_by_player_id.get(army.player_id)
        if index is None:
            raise GameLifecycleError("Tracked-target runtime missing player ability index.")
        for unit in sorted(army.units, key=lambda item: item.unit_instance_id):
            current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
                state=context.state,
                unit=unit,
            )
            if not current_model_ids:
                continue
            for record in catalog_rule_unit_scoped_generic_records(
                ability_index=index,
                unit=unit,
                current_model_instance_ids=current_model_ids,
                trigger_kind=TimingTriggerKind.START_BATTLE_ROUND,
            ):
                requests.extend(
                    _initial_selection_requests_for_record(
                        context=context,
                        army=army,
                        unit=unit,
                        current_model_instance_ids=current_model_ids,
                        record=record,
                        related_records=index.all_records(),
                    )
                )
    return tuple(sorted(requests, key=lambda request: request.request_id))


def _tracked_target_start_battle_selection_requests(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    context: BattleFormationRequestContext,
) -> tuple[DecisionRequest, ...]:
    requests: list[DecisionRequest] = []
    for army in sorted(armies, key=lambda item: item.player_id):
        index = ability_indexes_by_player_id.get(army.player_id)
        if index is None:
            raise GameLifecycleError("Tracked-target runtime missing player ability index.")
        for unit in sorted(army.units, key=lambda item: item.unit_instance_id):
            current_model_ids = unit.own_model_ids()
            for record in index.all_records():
                if not catalog_rule_record_source_matches_unit(
                    record=record,
                    unit=unit,
                    current_model_instance_ids=current_model_ids,
                ):
                    continue
                requests.extend(
                    _initial_selection_requests_for_record(
                        context=context,
                        army=army,
                        unit=unit,
                        current_model_instance_ids=current_model_ids,
                        record=record,
                        related_records=index.all_records(),
                        timing_matcher=_selection_clause_matches_start_battle,
                    )
                )
    return tuple(sorted(requests, key=lambda request: request.request_id))


def _initial_selection_requests_for_record(
    *,
    context: BattleFormationRequestContext | BattleRoundStartRequestContext,
    army: ArmyDefinition,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    record: AbilityCatalogRecord,
    related_records: tuple[AbilityCatalogRecord, ...],
    timing_matcher: Callable[[RuleClause, int], bool] | None = None,
) -> tuple[DecisionRequest, ...]:
    matcher: Callable[[RuleClause, int], bool] = _selection_clause_matches_battle_round_start
    if timing_matcher is not None:
        matcher = timing_matcher
    requests: list[DecisionRequest] = []
    for clause in catalog_rule_clauses_from_record(record):
        if not catalog_rule_clause_is_supported_tracked_target_selection(clause):
            continue
        if not matcher(clause, context.state.battle_round):
            continue
        for effect_index, effect in enumerate(clause.effects):
            if effect.kind is not RuleEffectKind.SELECT_TRACKED_TARGET:
                continue
            if parameter_payload(effect.parameters).get("replacement") is True:
                continue
            for source_model_id in _tracked_target_source_model_ids(
                record=record,
                unit=unit,
                current_model_instance_ids=current_model_instance_ids,
                effect=effect,
            ):
                request = _build_request_from_effect(
                    context=context,
                    actor_player_id=army.player_id,
                    record=record,
                    clause=clause,
                    effect_index=effect_index,
                    effect=effect,
                    unit=unit,
                    source_model_instance_id=source_model_id,
                    related_records=related_records,
                )
                if request is not None:
                    requests.append(request)
    return tuple(requests)


def _tracked_target_reselection_request(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    context: UnitDestroyedContext,
    expired_record: TrackedTargetRecord,
) -> DecisionRequest | None:
    rules_unit = rules_unit_view_from_armies(
        armies=armies,
        unit_instance_id=expired_record.source_unit_instance_id,
    )
    army = next(
        (candidate for candidate in armies if candidate.player_id == rules_unit.owner_player_id),
        None,
    )
    if army is None:
        raise GameLifecycleError("Tracked-target reselection source army is unknown.")
    if army.player_id != expired_record.owner_player_id:
        raise GameLifecycleError("Tracked-target reselection owner drift.")
    index = ability_indexes_by_player_id.get(expired_record.owner_player_id)
    if index is None:
        raise GameLifecycleError("Tracked-target reselection missing player ability index.")
    for component in rules_unit.components:
        unit = component.unit
        current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
            state=context.state,
            unit=unit,
        )
        if not current_model_ids:
            continue
        for record in index.records_for(TimingTriggerKind.AFTER_UNIT_DESTROYED):
            if not catalog_rule_record_source_matches_unit(
                record=record,
                unit=unit,
                current_model_instance_ids=current_model_ids,
            ):
                continue
            for clause in catalog_rule_clauses_from_record(record):
                if not catalog_rule_clause_is_supported_tracked_target_destroyed_reselect(clause):
                    continue
                request = _reselection_request_for_clause(
                    context=context,
                    expired_record=expired_record,
                    record=record,
                    clause=clause,
                    unit=unit,
                    related_records=index.all_records(),
                )
                if request is not None:
                    return request
    return None


def _reselection_request_for_clause(
    *,
    context: UnitDestroyedContext,
    expired_record: TrackedTargetRecord,
    record: AbilityCatalogRecord,
    clause: RuleClause,
    unit: UnitInstance,
    related_records: tuple[AbilityCatalogRecord, ...],
) -> DecisionRequest | None:
    source_rules_unit_instance_id = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=unit.unit_instance_id,
    ).unit_instance_id
    if source_rules_unit_instance_id != expired_record.source_unit_instance_id:
        raise GameLifecycleError("Tracked-target reselection source unit drift.")
    for effect_index, effect in enumerate(clause.effects):
        if effect.kind is not RuleEffectKind.SELECT_TRACKED_TARGET:
            continue
        parameters = parameter_payload(effect.parameters)
        if parameters.get("replacement") is not True:
            continue
        if parameters.get("tracked_target_role") != expired_record.role.value:
            continue
        if parameters.get("tracked_target_owner") != expired_record.owner_scope.value:
            continue
        return _build_request_from_effect(
            context=context,
            actor_player_id=expired_record.owner_player_id,
            record=record,
            clause=clause,
            effect_index=effect_index,
            effect=effect,
            unit=unit,
            source_model_instance_id=expired_record.source_model_instance_id,
            related_records=related_records,
        )
    return None


def _build_request_from_effect(
    *,
    context: BattleFormationRequestContext | BattleRoundStartRequestContext | UnitDestroyedContext,
    actor_player_id: str,
    record: AbilityCatalogRecord,
    clause: RuleClause,
    effect_index: int,
    effect: RuleEffectSpec,
    unit: UnitInstance,
    source_model_instance_id: str | None,
    related_records: tuple[AbilityCatalogRecord, ...],
) -> DecisionRequest | None:
    parameters = parameter_payload(effect.parameters)
    descriptor = tracked_target_selection_descriptor_for_clause(clause)
    if (
        clause.template_id == START_BATTLE_TRACKED_TARGET_SELECTION_TEMPLATE_ID
        and descriptor is None
    ):
        raise GameLifecycleError("Tracked-target selection descriptor classification drift.")
    supported_attack_roll_pairs = _supported_attack_roll_pairs_for_selection_effect(
        record=record,
        effect=effect,
        related_records=related_records,
    )
    if not supported_attack_roll_pairs:
        return None
    return build_select_tracked_target_request(
        state=context.state,
        actor_player_id=actor_player_id,
        source_rule_id=record.definition.source_id,
        source_ability_id=record.definition.ability_id,
        source_clause_id=clause.clause_id,
        source_effect_index=effect_index,
        source_unit_instance_id=unit.unit_instance_id,
        source_model_instance_id=source_model_instance_id,
        owner_scope=(
            descriptor.owner_scope
            if descriptor is not None
            else TrackedTargetOwnerScope(str(parameters["tracked_target_owner"]))
        ),
        role=(
            descriptor.role
            if descriptor is not None
            else TrackedTargetRole(str(parameters["tracked_target_role"]))
        ),
        supported_attack_roll_pairs=supported_attack_roll_pairs,
        target_allegiance=(
            descriptor.target_allegiance
            if descriptor is not None
            else str(parameters["target_allegiance"])
        ),
        target_scope=(
            descriptor.target_scope if descriptor is not None else str(parameters["target_scope"])
        ),
        replacement=(
            descriptor.replacement if descriptor is not None else bool(parameters["replacement"])
        ),
    )


def _supported_attack_roll_pairs_for_selection_effect(
    *,
    record: AbilityCatalogRecord,
    effect: RuleEffectSpec,
    related_records: tuple[AbilityCatalogRecord, ...],
) -> tuple[tuple[str, str], ...]:
    selection_parameters = parameter_payload(effect.parameters)
    tracked_owner = selection_parameters.get("tracked_target_owner")
    tracked_role = selection_parameters.get("tracked_target_role")
    supported: set[tuple[str, str]] = set()
    for related_record in related_records:
        if related_record.definition.source_id != record.definition.source_id:
            continue
        for clause in catalog_rule_clauses_from_record(related_record):
            if not _clause_matches_tracked_target_reference(
                clause=clause,
                tracked_owner=tracked_owner,
                tracked_role=tracked_role,
            ):
                continue
            supported.update(
                catalog_rule_tracked_target_supported_attack_roll_pairs_for_clause(clause)
            )
    return tuple(
        (attack_kind, roll_type)
        for attack_kind in ("melee", "ranged")
        for roll_type in ("attack_sequence.hit", "attack_sequence.wound")
        if (attack_kind, roll_type) in supported
    )


def _clause_matches_tracked_target_reference(
    *,
    clause: RuleClause,
    tracked_owner: object,
    tracked_role: object,
) -> bool:
    trigger = clause.trigger
    if trigger is not None and trigger.kind is RuleTriggerKind.DICE_ROLL:
        trigger_parameters = parameter_payload(trigger.parameters)
        return (
            trigger_parameters.get("tracked_target_owner") == tracked_owner
            and trigger_parameters.get("tracked_target_role") == tracked_role
        )
    return any(
        parameter_payload(effect.parameters).get("tracked_target_owner") == tracked_owner
        and parameter_payload(effect.parameters).get("tracked_target_role") == tracked_role
        for effect in clause.effects
    )


def _selection_clause_matches_battle_round_start(clause: RuleClause, battle_round: int) -> bool:
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    parameters = parameter_payload(trigger.parameters)
    configured_round = parameters.get("battle_round")
    return (
        parameters.get("phase") == "battle_round"
        and parameters.get("edge") == "start"
        and parameters.get("timing_window") == "battle_round_start"
        and (configured_round is None or configured_round == battle_round)
    )


def _selection_clause_matches_start_battle(clause: RuleClause, battle_round: int) -> bool:
    if type(battle_round) is not int or battle_round < 0:
        raise GameLifecycleError(
            "Tracked-target start-battle selection requires battle round state."
        )
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    parameters = parameter_payload(trigger.parameters)
    return (
        parameters.get("phase") == "battle"
        and parameters.get("edge") == "start"
        and parameters.get("timing_window") == "start_battle"
    )


def _tracked_target_source_model_ids(
    *,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
    effect: RuleEffectSpec,
) -> tuple[str | None, ...]:
    parameters = parameter_payload(effect.parameters)
    owner_scope = TrackedTargetOwnerScope(str(parameters["tracked_target_owner"]))
    if owner_scope is TrackedTargetOwnerScope.THIS_UNIT:
        return (None,)
    wargear_bearer_ids = catalog_rule_record_current_wargear_bearer_model_ids(
        record=record,
        unit=unit,
        current_model_instance_ids=current_model_instance_ids,
    )
    if wargear_bearer_ids:
        return wargear_bearer_ids
    return current_model_instance_ids


def _has_tracked_target_selection_records(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    return any(
        _record_has_supported_tracked_target_selection(record)
        for index in ability_indexes_by_player_id.values()
        for record in index.records_for(TimingTriggerKind.START_BATTLE_ROUND)
    )


def _has_start_battle_tracked_target_selection_records(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    return any(
        catalog_rule_clause_is_supported_tracked_target_selection(clause)
        and _selection_clause_matches_start_battle(clause, 1)
        for index in ability_indexes_by_player_id.values()
        for record in index.all_records()
        if record.definition.handler_id == GENERIC_RULE_IR_ABILITY_HANDLER_ID
        for clause in catalog_rule_clauses_from_record(record)
    )


def _has_tracked_target_reselection_records(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    return any(
        _record_has_supported_tracked_target_reselection(record)
        for index in ability_indexes_by_player_id.values()
        for record in index.records_for(TimingTriggerKind.AFTER_UNIT_DESTROYED)
    )


def _record_has_supported_tracked_target_selection(record: AbilityCatalogRecord) -> bool:
    return any(
        catalog_rule_clause_is_supported_tracked_target_selection(clause)
        for clause in catalog_rule_clauses_from_record(record)
    )


def _record_has_supported_tracked_target_reselection(record: AbilityCatalogRecord) -> bool:
    return any(
        catalog_rule_clause_is_supported_tracked_target_destroyed_reselect(clause)
        for clause in catalog_rule_clauses_from_record(record)
    )
