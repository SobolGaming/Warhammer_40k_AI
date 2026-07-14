from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_fight_end_triggered_movement_support import (
    CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID,
    clause_is_fight_end_triggered_movement,
    fight_end_triggered_movement_descriptor,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.fight_eligibility_queries import (
    unit_was_eligible_to_fight_this_phase,
)
from warhammer40k_core.engine.fight_order import unit_is_currently_engaged
from warhammer40k_core.engine.fight_phase_end_hooks import (
    FightPhaseEndHookBinding,
    FightPhaseEndRequestContext,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementEligibleUnit,
    TriggeredMovementKind,
    triggered_movement_unit_selection_request,
)
from warhammer40k_core.rules.rule_ir import RuleClause

CATALOG_FIGHT_END_TRIGGERED_MOVEMENT_ROLL_TYPE = "catalog_ir.fight_end_triggered_movement_d3"


@dataclass(frozen=True, slots=True)
class _CatalogFightEndMovementCandidate:
    owner_player_id: str
    rules_unit_instance_id: str
    record: AbilityCatalogRecord
    clause: RuleClause
    is_engaged: bool


@dataclass(frozen=True, slots=True)
class CatalogFightEndTriggeredMovementRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ability_indexes_by_player_id",
            _validate_ability_indexes(self.ability_indexes_by_player_id),
        )
        object.__setattr__(self, "armies", _validate_armies(self.armies))

    def bindings(self) -> tuple[FightPhaseEndHookBinding, ...]:
        if not _has_supported_records_for_unattached_units(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
        ):
            return ()
        return (
            FightPhaseEndHookBinding(
                hook_id=CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID,
                source_id=CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID,
                request_handler=self.next_request,
            ),
        )

    def next_request(self, context: FightPhaseEndRequestContext) -> DecisionRequest | None:
        if type(context) is not FightPhaseEndRequestContext:
            raise GameLifecycleError("Catalog Fight-end movement requires request context.")
        state = context.state
        if state.current_battle_phase is not BattlePhase.FIGHT:
            raise GameLifecycleError("Catalog Fight-end movement requires the Fight phase.")
        fight_state = state.fight_phase_state
        if fight_state is None:
            raise GameLifecycleError("Catalog Fight-end movement requires fight phase state.")
        candidates = self._candidates(context)
        if not candidates:
            return None
        candidate = candidates[0]
        semantic = fight_end_triggered_movement_descriptor(candidate.clause)
        d3_result = DiceRollManager(
            state.game_id,
            event_log=context.decisions.event_log,
        ).roll_d3(
            reason=(
                f"{candidate.record.definition.source_id} Fight-end movement for "
                f"{candidate.rules_unit_instance_id}"
            ),
            roll_type=CATALOG_FIGHT_END_TRIGGERED_MOVEMENT_ROLL_TYPE,
            actor_id=candidate.owner_player_id,
        )
        movement_mode = semantic.movement_mode_for_engagement_state(is_engaged=candidate.is_engaged)
        selected_effect = semantic.effect_for_engagement_state(is_engaged=candidate.is_engaged)
        descriptor = TriggeredMovementDescriptor(
            movement_kind=TriggeredMovementKind.TRIGGERED,
            source_rule_id=candidate.record.definition.source_id,
            trigger_timing=ReactionWindow(
                phase=BattlePhaseKind.FIGHT,
                window_kind=ReactionWindowKind.RULE_TRIGGER,
                source_step="fight_phase_end",
            ),
            max_distance_inches=float(d3_result.value + semantic.distance_bonus),
            movement_mode=movement_mode,
            allow_battle_shocked=True,
            allow_within_engagement_range=candidate.is_engaged,
            one_per_phase=False,
            optional=True,
        )
        return triggered_movement_unit_selection_request(
            state=state,
            player_id=candidate.owner_player_id,
            descriptor=descriptor,
            eligible_units=(
                TriggeredMovementEligibleUnit(
                    unit_instance_id=candidate.rules_unit_instance_id,
                    hook_id=CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID,
                    source_id=candidate.record.definition.source_id,
                    replay_payload=validate_json_value(
                        {
                            "consumer_id": CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID,
                            "catalog_record_id": candidate.record.record_id,
                            "clause_id": candidate.clause.clause_id,
                            "generic_rule_effect": selected_effect.to_payload(),
                            "distance_roll": d3_result.to_payload(),
                            "is_engaged": candidate.is_engaged,
                            "movement_mode": movement_mode.value,
                        }
                    ),
                    decision_effect_payload=None,
                ),
            ),
        )

    def _candidates(
        self, context: FightPhaseEndRequestContext
    ) -> tuple[_CatalogFightEndMovementCandidate, ...]:
        state = context.state
        fight_state = state.fight_phase_state
        if fight_state is None:
            raise GameLifecycleError("Catalog Fight-end movement requires fight phase state.")
        candidates: list[_CatalogFightEndMovementCandidate] = []
        seen: set[tuple[str, str, str]] = set()
        for army in self.armies:
            index = self.ability_indexes_by_player_id.get(army.player_id)
            if index is None:
                raise GameLifecycleError("Catalog Fight-end movement is missing ability index.")
            for source_unit in army.units:
                current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
                    state=state,
                    unit=source_unit,
                )
                if not current_model_ids:
                    continue
                for record in index.records_for(TimingTriggerKind.END_PHASE):
                    if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                        continue
                    if record.definition.timing.phase is not BattlePhaseKind.FIGHT:
                        continue
                    if not catalog_rule_record_source_matches_unit(
                        record=record,
                        unit=source_unit,
                        current_model_instance_ids=current_model_ids,
                    ):
                        continue
                    rules_unit = rules_unit_view_by_id(
                        state=state,
                        unit_instance_id=source_unit.unit_instance_id,
                    )
                    if rules_unit.is_attached_rules_unit:
                        continue
                    for clause in catalog_rule_clauses_from_record(record):
                        if not clause_is_fight_end_triggered_movement(clause):
                            continue
                        key = (
                            rules_unit.unit_instance_id,
                            record.definition.source_id,
                            clause.clause_id,
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        if _movement_was_handled(
                            records=context.decisions.event_log.records,
                            state_battle_round=state.battle_round,
                            rules_unit_instance_id=rules_unit.unit_instance_id,
                            source_rule_id=record.definition.source_id,
                        ):
                            continue
                        if not unit_was_eligible_to_fight_this_phase(
                            state=state,
                            fight_state=fight_state,
                            unit_instance_id=rules_unit.unit_instance_id,
                            policy=state.runtime_ruleset_descriptor().fight_policy,
                        ):
                            continue
                        candidates.append(
                            _CatalogFightEndMovementCandidate(
                                owner_player_id=rules_unit.owner_player_id,
                                rules_unit_instance_id=rules_unit.unit_instance_id,
                                record=record,
                                clause=clause,
                                is_engaged=unit_is_currently_engaged(
                                    state=state,
                                    unit_instance_id=rules_unit.unit_instance_id,
                                ),
                            )
                        )
        return tuple(
            sorted(
                candidates,
                key=lambda item: (
                    item.owner_player_id,
                    item.rules_unit_instance_id,
                    item.record.record_id,
                    item.clause.clause_id,
                ),
            )
        )


def catalog_fight_end_triggered_movement_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[FightPhaseEndHookBinding, ...]:
    return CatalogFightEndTriggeredMovementRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).bindings()


def _has_supported_records_for_unattached_units(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> bool:
    for army in armies:
        index = ability_indexes_by_player_id.get(army.player_id)
        if index is None:
            continue
        attached_component_unit_ids = _attached_component_unit_ids(army)
        for source_unit in army.units:
            if source_unit.unit_instance_id in attached_component_unit_ids:
                continue
            current_model_ids = tuple(
                sorted(
                    model.model_instance_id for model in source_unit.own_models if model.is_alive
                )
            )
            if not current_model_ids:
                continue
            for record in index.records_for(TimingTriggerKind.END_PHASE):
                if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                    continue
                if record.definition.timing.phase is not BattlePhaseKind.FIGHT:
                    continue
                if not catalog_rule_record_source_matches_unit(
                    record=record,
                    unit=source_unit,
                    current_model_instance_ids=current_model_ids,
                ):
                    continue
                if any(
                    clause_is_fight_end_triggered_movement(clause)
                    for clause in catalog_rule_clauses_from_record(record)
                ):
                    return True
    return False


def _attached_component_unit_ids(army: ArmyDefinition) -> frozenset[str]:
    return frozenset(
        unit_id
        for attached_unit in army.attached_units
        for unit_id in attached_unit.component_unit_instance_ids
    )


def _movement_was_handled(
    *,
    records: tuple[EventRecord, ...],
    state_battle_round: int,
    rules_unit_instance_id: str,
    source_rule_id: str,
) -> bool:
    for event in records:
        if event.event_type not in {
            "triggered_movement_declined",
            "triggered_movement_unit_selected",
        }:
            continue
        payload = _event_payload(event)
        if (
            payload.get("battle_round") != state_battle_round
            or payload.get("phase") != BattlePhase.FIGHT.value
            or payload.get("source_rule_id") != source_rule_id
        ):
            continue
        if event.event_type == "triggered_movement_unit_selected":
            if payload.get("unit_instance_id") == rules_unit_instance_id:
                return True
            continue
        raw_units = payload.get("eligible_units")
        if not isinstance(raw_units, list):
            raise GameLifecycleError("Triggered movement decline event units are invalid.")
        for raw_unit in raw_units:
            if not isinstance(raw_unit, dict):
                raise GameLifecycleError("Triggered movement decline event unit is invalid.")
            if raw_unit.get("unit_instance_id") == rules_unit_instance_id:
                return True
    return False


def _event_payload(event: EventRecord) -> dict[str, JsonValue]:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Triggered movement event payload must be an object.")
    return event.payload


def _validate_ability_indexes(
    value: object,
) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Catalog Fight-end movement indexes must be a mapping.")
    validated: dict[str, AbilityCatalogIndex] = {}
    for player_id, index in cast(Mapping[object, object], value).items():
        if type(player_id) is not str or not player_id.strip() or player_id != player_id.strip():
            raise GameLifecycleError("Catalog Fight-end movement player id is invalid.")
        if type(index) is not AbilityCatalogIndex:
            raise GameLifecycleError("Catalog Fight-end movement index is invalid.")
        validated[player_id] = index
    return MappingProxyType(validated)


def _validate_armies(value: tuple[ArmyDefinition, ...]) -> tuple[ArmyDefinition, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Catalog Fight-end movement armies must be a tuple.")
    for army in value:
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError("Catalog Fight-end movement army is invalid.")
    player_ids = tuple(army.player_id for army in value)
    if len(set(player_ids)) != len(player_ids):
        raise GameLifecycleError("Catalog Fight-end movement armies duplicate player ids.")
    return tuple(sorted(value, key=lambda army: army.player_id))
