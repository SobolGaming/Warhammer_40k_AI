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
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.catalog_datasheet_rule_extensions import (
    CatalogMovementTargetPairDescriptor,
    movement_target_pair_descriptor_for_clause,
)
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_MOVEMENT_TARGET_PAIR_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    effect_with_selected_target,
    rules_unit_has_placed_alive_model,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    PersistingEffect,
    generic_rule_persisting_effect,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.finite_decision_validation import invalid_finite_decision_status
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.phases.movement_model import MovementPhaseActionKind
from warhammer40k_core.engine.phases.movement_state import PendingMovementActionSelection
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.rule_target_resolution import (
    canonical_keyword,
    unit_has_required_keywords,
)
from warhammer40k_core.engine.rules_unit_geometry import geometry_models_for_rules_unit
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_view_by_id,
    rules_unit_views_from_armies,
)
from warhammer40k_core.engine.shooting_targets import unit_has_line_of_sight_to_target
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UnitMoveCompletedContext,
    UnitMoveCompletedMortalWoundHookBinding,
)
from warhammer40k_core.rules.rule_ir import RuleClause, RuleIR

SELECT_CATALOG_MOVEMENT_TARGET_PAIR_DECISION_TYPE = "select_catalog_movement_target_pair"
SELECT_CATALOG_MOVEMENT_TARGET_PAIR_SUBMISSION_KIND = "select_catalog_movement_target_pair"
CATALOG_MOVEMENT_TARGET_PAIR_SELECTED_EVENT = "catalog_movement_target_pair_selected"
CATALOG_MOVEMENT_TARGET_PAIR_DECLINED_EVENT = "catalog_movement_target_pair_declined"
CATALOG_MOVEMENT_TARGET_PAIR_EFFECT_KIND = "catalog_movement_target_pair"

_START_EDGE = "start"
_END_EDGE = "end"
_DECLINE_OPTION_SUFFIX = "decline"
_TRIGGERING_MOVEMENT_ACTIONS = frozenset(
    {
        MovementPhaseActionKind.NORMAL_MOVE,
        MovementPhaseActionKind.ADVANCE,
        MovementPhaseActionKind.FALL_BACK,
    }
)
_TRIGGERING_MOVEMENT_ACTION_TOKENS = frozenset(
    action.value for action in _TRIGGERING_MOVEMENT_ACTIONS
)
_NON_TRIGGERING_MOVEMENT_ACTION_TOKENS = frozenset(
    {MovementPhaseActionKind.REMAIN_STATIONARY.value, "set_up"}
)


@dataclass(frozen=True, slots=True)
class _MovementTargetPairSource:
    record: AbilityCatalogRecord
    rule_ir: RuleIR
    clause: RuleClause
    descriptor: CatalogMovementTargetPairDescriptor
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
class CatalogMovementTargetPairRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        if not isinstance(cast(object, self.ability_indexes_by_player_id), Mapping):
            raise GameLifecycleError("Catalog movement target-pair indexes must be a mapping.")
        if type(self.armies) is not tuple or not all(
            type(army) is ArmyDefinition for army in self.armies
        ):
            raise GameLifecycleError("Catalog movement target-pair runtime requires armies.")
        player_ids = {army.player_id for army in self.armies}
        if set(self.ability_indexes_by_player_id) != player_ids:
            raise GameLifecycleError("Catalog movement target-pair indexes must match armies.")
        object.__setattr__(
            self,
            "ability_indexes_by_player_id",
            MappingProxyType(dict(self.ability_indexes_by_player_id)),
        )

    def move_completed_bindings(
        self,
    ) -> tuple[UnitMoveCompletedMortalWoundHookBinding, ...]:
        if not self._has_runtime_records():
            return ()
        return (
            UnitMoveCompletedMortalWoundHookBinding(
                hook_id=CATALOG_IR_MOVEMENT_TARGET_PAIR_CONSUMER_ID,
                source_id=CATALOG_IR_MOVEMENT_TARGET_PAIR_CONSUMER_ID,
                request_handler=self.end_move_request,
            ),
        )

    def start_move_request(
        self,
        *,
        state: object,
        decisions: DecisionController,
        pending_action: PendingMovementActionSelection,
    ) -> LifecycleStatus | None:
        from warhammer40k_core.engine.game_state import GameState

        if type(state) is not GameState:
            raise GameLifecycleError("Catalog movement target-pair start requires GameState.")
        if type(decisions) is not DecisionController:
            raise GameLifecycleError("Catalog movement target-pair start requires decisions.")
        if type(pending_action) is not PendingMovementActionSelection:
            raise GameLifecycleError("Catalog movement target-pair start requires pending action.")
        _validate_movement_state(state)
        if pending_action.player_id != state.active_player_id:
            raise GameLifecycleError("Catalog movement target-pair active player drift.")
        if not _movement_action_triggers_target_pair(pending_action.movement_phase_action):
            return None
        for source in self._sources_for_triggering_rules_unit(
            state=state,
            triggering_unit_instance_id=pending_action.unit_instance_id,
        ):
            if self._source_used_this_turn(state=state, decisions=decisions, source=source):
                continue
            if self._start_edge_resolved_for_action(
                decisions=decisions,
                source=source,
                action_result_id=pending_action.result_id,
            ):
                continue
            status = self._request_for_source(
                state=state,
                decisions=decisions,
                source=source,
                edge=_START_EDGE,
                trigger_event_id=None,
                movement_action=pending_action.movement_phase_action.value,
                movement_action_result_id=pending_action.result_id,
            )
            if status is not None:
                return status
        return None

    def end_move_request(self, context: UnitMoveCompletedContext) -> LifecycleStatus | None:
        if type(context) is not UnitMoveCompletedContext:
            raise GameLifecycleError("Catalog movement target-pair end requires context.")
        if context.decisions is None:
            raise GameLifecycleError("Catalog movement target-pair end requires decisions.")
        if context.completed_phase is not BattlePhase.MOVEMENT:
            return None
        if not _movement_action_triggers_target_pair(context.movement_action):
            return None
        for source in self._sources_for_triggering_rules_unit(
            state=context.state,
            triggering_unit_instance_id=context.triggering_unit_instance_id,
        ):
            if self._source_used_this_turn(
                state=context.state,
                decisions=context.decisions,
                source=source,
            ):
                continue
            if self._end_edge_resolved_for_event(
                decisions=context.decisions,
                source=source,
                trigger_event_id=context.trigger_event_id,
            ):
                continue
            status = self._request_for_source(
                state=context.state,
                decisions=context.decisions,
                source=source,
                edge=_END_EDGE,
                trigger_event_id=context.trigger_event_id,
                movement_action=context.movement_action,
                movement_action_result_id=None,
            )
            if status is not None:
                return status
        return None

    def apply_result(
        self,
        *,
        state: object,
        decisions: DecisionController,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(state) is not GameState:
            raise GameLifecycleError("Catalog movement target-pair result requires GameState.")
        if type(decisions) is not DecisionController:
            raise GameLifecycleError("Catalog movement target-pair result requires decisions.")
        if type(request) is not DecisionRequest or type(result) is not DecisionResult:
            raise GameLifecycleError("Catalog movement target-pair result is invalid.")
        result.validate_for_request(request)
        request_payload = _payload_object(request.payload)
        result_payload = _payload_object(result.payload)
        source = self._current_source_from_payload(state=state, payload=request_payload)
        edge = _payload_edge(request_payload)
        if _payload_string(result_payload, "submission_kind") != (
            SELECT_CATALOG_MOVEMENT_TARGET_PAIR_SUBMISSION_KIND
        ):
            raise GameLifecycleError("Catalog movement target-pair submission kind drift.")
        if result_payload.get("use_ability") is False:
            decisions.event_log.append(
                CATALOG_MOVEMENT_TARGET_PAIR_DECLINED_EVENT,
                _selection_event_payload(
                    state=state,
                    request=request,
                    result=result,
                    source=source,
                    payload=result_payload,
                    edge=edge,
                    effect_payload=None,
                ),
            )
            return
        if result_payload.get("use_ability") is not True:
            raise GameLifecycleError("Catalog movement target-pair use_ability is invalid.")
        friendly_id = _payload_string(result_payload, "friendly_unit_instance_id")
        enemy_id = _payload_string(result_payload, "enemy_unit_instance_id")
        if (friendly_id, enemy_id) not in set(self._eligible_pair_ids(state=state, source=source)):
            raise GameLifecycleError("Catalog movement target-pair selection is no longer legal.")
        effect = _persisting_effect(
            state=state,
            request=request,
            result=result,
            source=source,
            friendly_unit_instance_id=friendly_id,
            enemy_unit_instance_id=enemy_id,
            edge=edge,
        )
        state.record_persisting_effect(effect)
        decisions.event_log.append(
            CATALOG_MOVEMENT_TARGET_PAIR_SELECTED_EVENT,
            _selection_event_payload(
                state=state,
                request=request,
                result=result,
                source=source,
                payload=result_payload,
                edge=edge,
                effect_payload=effect.to_payload(),
            ),
        )

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
            raise GameLifecycleError("Catalog movement target-pair validation requires GameState.")
        request_payload = _payload_object(request.payload)
        if not _request_context_is_current(
            state=state,
            decisions=decisions,
            payload=request_payload,
        ):
            return False
        source = self._current_source_from_payload(state=state, payload=request_payload)
        if self._source_used_this_turn(state=state, decisions=decisions, source=source):
            return False
        result_payload = _payload_object(result.payload)
        if result_payload.get("use_ability") is False:
            return True
        if result_payload.get("use_ability") is not True:
            return False
        pair = (
            _payload_string(result_payload, "friendly_unit_instance_id"),
            _payload_string(result_payload, "enemy_unit_instance_id"),
        )
        return pair in set(self._eligible_pair_ids(state=state, source=source))

    def _request_for_source(
        self,
        *,
        state: object,
        decisions: DecisionController,
        source: _MovementTargetPairSource,
        edge: str,
        trigger_event_id: str | None,
        movement_action: str,
        movement_action_result_id: str | None,
    ) -> LifecycleStatus | None:
        from warhammer40k_core.engine.game_state import GameState

        if type(state) is not GameState:
            raise GameLifecycleError("Catalog movement target-pair request requires GameState.")
        pair_ids = self._eligible_pair_ids(state=state, source=source)
        if not pair_ids:
            return None
        common = _common_request_payload(
            state=state,
            source=source,
            edge=edge,
            trigger_event_id=trigger_event_id,
            movement_action=movement_action,
            movement_action_result_id=movement_action_result_id,
        )
        options = (
            *(
                DecisionOption(
                    option_id=_pair_option_id(
                        source_model_instance_id=source.source_model_instance_id,
                        friendly_unit_instance_id=friendly_id,
                        enemy_unit_instance_id=enemy_id,
                    ),
                    label=f"Spirit Mark: {friendly_id} against {enemy_id}",
                    payload=validate_json_value(
                        {
                            **common,
                            "use_ability": True,
                            "friendly_unit_instance_id": friendly_id,
                            "enemy_unit_instance_id": enemy_id,
                        }
                    ),
                )
                for friendly_id, enemy_id in pair_ids
            ),
            DecisionOption(
                option_id=_decline_option_id(source.source_model_instance_id, edge=edge),
                label=("Defer Spirit Mark" if edge == _START_EDGE else "Do not use Spirit Mark"),
                payload=validate_json_value(
                    {
                        **common,
                        "use_ability": False,
                        "friendly_unit_instance_id": None,
                        "enemy_unit_instance_id": None,
                    }
                ),
            ),
        )
        request = decisions.request_decision(
            DecisionRequest(
                request_id=state.next_decision_request_id(),
                decision_type=SELECT_CATALOG_MOVEMENT_TARGET_PAIR_DECISION_TYPE,
                actor_id=source.source_rules_unit.owner_player_id,
                payload=validate_json_value(common),
                options=options,
            )
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload={
                "phase": BattlePhase.MOVEMENT.value,
                "active_player_id": state.active_player_id,
                "phase_body_status": "catalog_movement_target_pair_pending",
                "timing_edge": edge,
            },
        )

    def _eligible_pair_ids(
        self,
        *,
        state: object,
        source: _MovementTargetPairSource,
    ) -> tuple[tuple[str, str], ...]:
        from warhammer40k_core.engine.game_state import GameState

        if type(state) is not GameState:
            raise GameLifecycleError("Catalog movement target-pair lookup requires GameState.")
        friendly = self._eligible_friendly_units(state=state, source=source)
        enemies = self._eligible_enemy_units(state=state, source=source)
        return tuple(
            (friendly_unit.unit_instance_id, enemy_unit.unit_instance_id)
            for friendly_unit in friendly
            for enemy_unit in enemies
        )

    def _eligible_friendly_units(
        self,
        *,
        state: object,
        source: _MovementTargetPairSource,
    ) -> tuple[RulesUnitView, ...]:
        from warhammer40k_core.engine.game_state import GameState

        if type(state) is not GameState:
            raise GameLifecycleError("Catalog movement target-pair lookup requires GameState.")
        source_models = tuple(
            model
            for model in geometry_models_for_rules_unit(
                state=state,
                unit_instance_id=source.source_rules_unit.unit_instance_id,
            )
            if model.model_id == source.source_model_instance_id
        )
        if len(source_models) != 1:
            raise GameLifecycleError("Catalog movement target-pair source model is not placed.")
        source_model = source_models[0]
        candidates: list[RulesUnitView] = []
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
            keywords = {
                canonical_keyword(keyword) for keyword in (*view.keywords, *view.faction_keywords)
            }
            if any(
                canonical_keyword(keyword) in keywords
                for keyword in source.descriptor.excluded_keywords
            ):
                continue
            target_models = geometry_models_for_rules_unit(
                state=state,
                unit_instance_id=view.unit_instance_id,
            )
            if any(
                source_model.range_to(target_model) <= source.descriptor.distance_inches
                for target_model in target_models
            ):
                candidates.append(view)
        return tuple(sorted(candidates, key=lambda view: view.unit_instance_id))

    def _eligible_enemy_units(
        self,
        *,
        state: object,
        source: _MovementTargetPairSource,
    ) -> tuple[RulesUnitView, ...]:
        from warhammer40k_core.engine.game_state import GameState

        if type(state) is not GameState:
            raise GameLifecycleError("Catalog movement target-pair lookup requires GameState.")
        scenario = battlefield_scenario_for_state(state=state)
        if state.battlefield_state is None:
            raise GameLifecycleError("Catalog movement target-pair requires battlefield state.")
        observing_unit = source.source_rules_unit.component_unit_for_model(
            source.source_model_instance_id
        )
        candidates: list[RulesUnitView] = []
        for view in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
            if view.owner_player_id == source.source_rules_unit.owner_player_id:
                continue
            if not rules_unit_has_placed_alive_model(state=state, rules_unit=view):
                continue
            if unit_has_line_of_sight_to_target(
                scenario=scenario,
                ruleset_descriptor=state.runtime_ruleset_descriptor(),
                observing_unit=observing_unit,
                observer_model_instance_id=source.source_model_instance_id,
                target_unit_id=view.unit_instance_id,
                terrain_features=state.battlefield_state.terrain_features,
            ):
                candidates.append(view)
        return tuple(sorted(candidates, key=lambda view: view.unit_instance_id))

    def _sources_for_triggering_rules_unit(
        self,
        *,
        state: object,
        triggering_unit_instance_id: str,
    ) -> tuple[_MovementTargetPairSource, ...]:
        from warhammer40k_core.engine.game_state import GameState

        if type(state) is not GameState:
            raise GameLifecycleError("Catalog movement target-pair source lookup requires state.")
        view = rules_unit_view_by_id(state=state, unit_instance_id=triggering_unit_instance_id)
        index = self.ability_indexes_by_player_id[view.owner_player_id]
        sources: list[_MovementTargetPairSource] = []
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
                    descriptor = movement_target_pair_descriptor_for_clause(clause)
                    if descriptor is None:
                        continue
                    sources.extend(
                        _MovementTargetPairSource(
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

    def _current_source_from_payload(
        self,
        *,
        state: object,
        payload: dict[str, JsonValue],
    ) -> _MovementTargetPairSource:
        candidates = self._sources_for_triggering_rules_unit(
            state=state,
            triggering_unit_instance_id=_payload_string(payload, "source_rules_unit_instance_id"),
        )
        matches = tuple(
            source
            for source in candidates
            if source.record.record_id == _payload_string(payload, "catalog_record_id")
            and source.record.definition.source_id == _payload_string(payload, "source_rule_id")
            and source.rule_ir.ir_hash() == _payload_string(payload, "source_rule_ir_hash")
            and source.clause.clause_id == _payload_string(payload, "clause_id")
            and source.unit.unit_instance_id == _payload_string(payload, "source_unit_instance_id")
            and source.source_model_instance_id
            == _payload_string(payload, "source_model_instance_id")
        )
        if len(matches) != 1:
            raise GameLifecycleError("Catalog movement target-pair source is no longer available.")
        return matches[0]

    def _source_used_this_turn(
        self,
        *,
        state: object,
        decisions: DecisionController,
        source: _MovementTargetPairSource,
    ) -> bool:
        from warhammer40k_core.engine.game_state import GameState

        if type(state) is not GameState:
            raise GameLifecycleError("Catalog movement target-pair event lookup requires state.")
        return any(
            record.event_type == CATALOG_MOVEMENT_TARGET_PAIR_SELECTED_EVENT
            and _event_matches_source_turn(record, state=state, source=source)
            for record in decisions.event_log.records
        )

    def _start_edge_resolved_for_action(
        self,
        *,
        decisions: DecisionController,
        source: _MovementTargetPairSource,
        action_result_id: str,
    ) -> bool:
        return any(
            record.event_type
            in {
                CATALOG_MOVEMENT_TARGET_PAIR_SELECTED_EVENT,
                CATALOG_MOVEMENT_TARGET_PAIR_DECLINED_EVENT,
            }
            and _event_payload(record).get("timing_edge") == _START_EDGE
            and _event_payload(record).get("movement_action_result_id") == action_result_id
            and _event_payload(record).get("source_model_instance_id")
            == source.source_model_instance_id
            and _event_payload(record).get("source_rule_id") == source.record.definition.source_id
            for record in decisions.event_log.records
        )

    def _end_edge_resolved_for_event(
        self,
        *,
        decisions: DecisionController,
        source: _MovementTargetPairSource,
        trigger_event_id: str,
    ) -> bool:
        return any(
            record.event_type
            in {
                CATALOG_MOVEMENT_TARGET_PAIR_SELECTED_EVENT,
                CATALOG_MOVEMENT_TARGET_PAIR_DECLINED_EVENT,
            }
            and _event_payload(record).get("timing_edge") == _END_EDGE
            and _event_payload(record).get("trigger_event_id") == trigger_event_id
            and _event_payload(record).get("source_model_instance_id")
            == source.source_model_instance_id
            and _event_payload(record).get("source_rule_id") == source.record.definition.source_id
            for record in decisions.event_log.records
        )

    def _has_runtime_records(self) -> bool:
        return any(
            movement_target_pair_descriptor_for_clause(clause) is not None
            for index in self.ability_indexes_by_player_id.values()
            for record in index.all_records()
            if record.definition.handler_id == GENERIC_RULE_IR_ABILITY_HANDLER_ID
            for clause in catalog_rule_clauses_from_record(record)
        )


def request_catalog_movement_target_pair_start_if_available(
    *,
    state: object,
    decisions: DecisionController,
    pending_action: PendingMovementActionSelection,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog movement target-pair start requires GameState.")
    return CatalogMovementTargetPairRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=tuple(state.army_definitions),
    ).start_move_request(state=state, decisions=decisions, pending_action=pending_action)


def catalog_movement_target_pair_move_completed_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[UnitMoveCompletedMortalWoundHookBinding, ...]:
    return CatalogMovementTargetPairRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).move_completed_bindings()


def invalid_catalog_movement_target_pair_status(
    *,
    state: object,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog movement target-pair validation requires GameState.")
    invalid = invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_catalog_movement_target_pair_result",
    )
    if invalid is not None:
        return invalid
    runtime = CatalogMovementTargetPairRuntime(
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
        message="Catalog movement target-pair selection no longer matches game state.",
        payload={
            "invalid_reason": "invalid_catalog_movement_target_pair_result",
            "field": "current_options",
        },
    )


def apply_catalog_movement_target_pair_result(
    *,
    state: object,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog movement target-pair result requires GameState.")
    CatalogMovementTargetPairRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=tuple(state.army_definitions),
    ).apply_result(state=state, decisions=decisions, request=request, result=result)


def _persisting_effect(
    *,
    state: object,
    request: DecisionRequest,
    result: DecisionResult,
    source: _MovementTargetPairSource,
    friendly_unit_instance_id: str,
    enemy_unit_instance_id: str,
    edge: str,
) -> PersistingEffect:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState or state.active_player_id is None:
        raise GameLifecycleError("Catalog movement target-pair effect requires active state.")
    base_effect = source.clause.effects[0]
    selected_effect = effect_with_selected_target(
        base_effect,
        selected_target_unit_instance_id=enemy_unit_instance_id,
        normalized_attack_role="attacker",
        normalized_weapon_scope="all",
    )
    context = RuleExecutionContext(
        game_id=state.game_id,
        player_id=source.source_rules_unit.owner_player_id,
        battle_round=state.battle_round,
        phase=BattlePhaseKind.MOVEMENT,
        active_player_id=state.active_player_id,
        timing_window_id=f"model_{edge}s_move",
        source_unit_instance_id=source.unit.unit_instance_id,
        source_model_instance_id=source.source_model_instance_id,
        target_unit_instance_ids=(friendly_unit_instance_id,),
        source_keywords=tuple(sorted((*source.unit.keywords, *source.unit.faction_keywords))),
        trigger_payload=validate_json_value(
            {
                "friendly_unit_instance_id": friendly_unit_instance_id,
                "enemy_unit_instance_id": enemy_unit_instance_id,
                "timing_edge": edge,
                "request_id": request.request_id,
                "result_id": result.result_id,
            }
        ),
        state=state,
        event_log=None,
        record_persisting_effects=False,
    )
    payload = validate_json_value(
        {
            "effect_kind": GENERIC_RULE_EFFECT_KIND,
            "catalog_effect_kind": CATALOG_MOVEMENT_TARGET_PAIR_EFFECT_KIND,
            "hook_id": CATALOG_IR_MOVEMENT_TARGET_PAIR_CONSUMER_ID,
            "rule_id": source.rule_ir.rule_id,
            "source_id": source.record.definition.source_id,
            "rule_ir_hash": source.rule_ir.ir_hash(),
            "clause_id": source.clause.clause_id,
            "effect_index": 0,
            "source_span": source.clause.source_span.to_payload(),
            "target": None if source.clause.target is None else source.clause.target.to_payload(),
            "target_unit_instance_ids": [friendly_unit_instance_id],
            "duration": (
                None if source.clause.duration is None else source.clause.duration.to_payload()
            ),
            "effect": selected_effect.to_payload(),
            "conditions": [],
            "context": context.to_payload(),
            "selected_friendly_unit_instance_id": friendly_unit_instance_id,
            "selected_enemy_unit_instance_id": enemy_unit_instance_id,
        }
    )
    return generic_rule_persisting_effect(
        effect_id=f"{result.result_id}:catalog-movement-target-pair",
        source_rule_id=source.record.definition.source_id,
        owner_player_id=source.source_rules_unit.owner_player_id,
        target_unit_instance_ids=(friendly_unit_instance_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhaseKind.MOVEMENT,
        expiration=EffectExpiration.start_phase(
            battle_round=state.battle_round + 1,
            phase=BattlePhaseKind.MOVEMENT,
            player_id=source.source_rules_unit.owner_player_id,
        ),
        effect_payload=payload,
    )


def _common_request_payload(
    *,
    state: object,
    source: _MovementTargetPairSource,
    edge: str,
    trigger_event_id: str | None,
    movement_action: str,
    movement_action_result_id: str | None,
) -> dict[str, JsonValue]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog movement target-pair payload requires GameState.")
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.MOVEMENT.value,
                "active_player_id": state.active_player_id,
                "submission_kind": SELECT_CATALOG_MOVEMENT_TARGET_PAIR_SUBMISSION_KIND,
                "hook_id": CATALOG_IR_MOVEMENT_TARGET_PAIR_CONSUMER_ID,
                "catalog_record_id": source.record.record_id,
                "source_rule_id": source.record.definition.source_id,
                "source_rule_ir_hash": source.rule_ir.ir_hash(),
                "clause_id": source.clause.clause_id,
                "source_rules_unit_instance_id": source.source_rules_unit.unit_instance_id,
                "source_unit_instance_id": source.unit.unit_instance_id,
                "source_model_instance_id": source.source_model_instance_id,
                "timing_edge": edge,
                "trigger_event_id": trigger_event_id,
                "movement_action": movement_action,
                "movement_action_result_id": movement_action_result_id,
            }
        ),
    )


def _selection_event_payload(
    *,
    state: object,
    request: DecisionRequest,
    result: DecisionResult,
    source: _MovementTargetPairSource,
    payload: dict[str, JsonValue],
    edge: str,
    effect_payload: object,
) -> JsonValue:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog movement target-pair event requires GameState.")
    return validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": state.active_player_id,
            "player_id": result.actor_id,
            "request_id": request.request_id,
            "result_id": result.result_id,
            "selected_option_id": result.selected_option_id,
            "hook_id": CATALOG_IR_MOVEMENT_TARGET_PAIR_CONSUMER_ID,
            "catalog_record_id": source.record.record_id,
            "source_rule_id": source.record.definition.source_id,
            "source_rule_ir_hash": source.rule_ir.ir_hash(),
            "clause_id": source.clause.clause_id,
            "source_rules_unit_instance_id": source.source_rules_unit.unit_instance_id,
            "source_unit_instance_id": source.unit.unit_instance_id,
            "source_model_instance_id": source.source_model_instance_id,
            "timing_edge": edge,
            "trigger_event_id": payload.get("trigger_event_id"),
            "movement_action": payload.get("movement_action"),
            "movement_action_result_id": payload.get("movement_action_result_id"),
            "use_ability": payload.get("use_ability"),
            "friendly_unit_instance_id": payload.get("friendly_unit_instance_id"),
            "enemy_unit_instance_id": payload.get("enemy_unit_instance_id"),
            "persisting_effect": effect_payload,
        }
    )


def _request_context_is_current(
    *,
    state: object,
    decisions: DecisionController,
    payload: dict[str, JsonValue],
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog movement target-pair validation requires GameState.")
    if (
        state.stage is not GameLifecycleStage.BATTLE
        or state.current_battle_phase is not BattlePhase.MOVEMENT
        or payload.get("game_id") != state.game_id
        or payload.get("battle_round") != state.battle_round
        or payload.get("active_player_id") != state.active_player_id
    ):
        return False
    edge = _payload_edge(payload)
    movement_action = payload.get("movement_action")
    if not _movement_action_triggers_target_pair(movement_action):
        return False
    if edge == _START_EDGE:
        movement_state = state.movement_phase_state
        pending = None if movement_state is None else movement_state.pending_action
        return (
            pending is not None
            and pending.unit_instance_id == payload.get("source_rules_unit_instance_id")
            and pending.result_id == payload.get("movement_action_result_id")
            and pending.movement_phase_action.value == payload.get("movement_action")
        )
    trigger_event_id = payload.get("trigger_event_id")
    return type(trigger_event_id) is str and any(
        record.event_id == trigger_event_id
        and record.event_type == "movement_activation_completed"
        and _event_payload(record).get("unit_instance_id")
        == payload.get("source_rules_unit_instance_id")
        for record in decisions.event_log.records
    )


def _event_matches_source_turn(
    record: EventRecord,
    *,
    state: object,
    source: _MovementTargetPairSource,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog movement target-pair event lookup requires state.")
    payload = _event_payload(record)
    return (
        payload.get("game_id") == state.game_id
        and payload.get("battle_round") == state.battle_round
        and payload.get("active_player_id") == state.active_player_id
        and payload.get("source_rule_id") == source.record.definition.source_id
        and payload.get("source_model_instance_id") == source.source_model_instance_id
    )


def _validate_movement_state(state: object) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog movement target-pair requires GameState.")
    if (
        state.stage is not GameLifecycleStage.BATTLE
        or state.current_battle_phase is not BattlePhase.MOVEMENT
        or state.active_player_id is None
    ):
        raise GameLifecycleError("Catalog movement target-pair requires active Movement phase.")


def _movement_action_triggers_target_pair(value: object) -> bool:
    if type(value) is MovementPhaseActionKind:
        return value in _TRIGGERING_MOVEMENT_ACTIONS
    if type(value) is not str or not value:
        raise GameLifecycleError("Catalog movement target-pair action must be an identifier.")
    if value in _TRIGGERING_MOVEMENT_ACTION_TOKENS:
        return True
    if value in _NON_TRIGGERING_MOVEMENT_ACTION_TOKENS:
        return False
    raise GameLifecycleError(f"Catalog movement target-pair action is unsupported: {value}.")


def _payload_object(value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Catalog movement target-pair payload must be an object.")
    return value


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Catalog movement target-pair payload missing {key}.")
    return value


def _payload_edge(payload: dict[str, JsonValue]) -> str:
    edge = _payload_string(payload, "timing_edge")
    if edge not in {_START_EDGE, _END_EDGE}:
        raise GameLifecycleError("Catalog movement target-pair timing edge is invalid.")
    return edge


def _event_payload(record: EventRecord) -> dict[str, JsonValue]:
    return _payload_object(record.payload)


def _pair_option_id(
    *,
    source_model_instance_id: str,
    friendly_unit_instance_id: str,
    enemy_unit_instance_id: str,
) -> str:
    return (
        f"catalog-movement-target-pair:{source_model_instance_id}:"
        f"{friendly_unit_instance_id}:{enemy_unit_instance_id}"
    )


def _decline_option_id(source_model_instance_id: str, *, edge: str) -> str:
    return (
        f"catalog-movement-target-pair:{source_model_instance_id}:{edge}:{_DECLINE_OPTION_SUFFIX}"
    )


__all__ = (
    "CATALOG_MOVEMENT_TARGET_PAIR_DECLINED_EVENT",
    "CATALOG_MOVEMENT_TARGET_PAIR_SELECTED_EVENT",
    "SELECT_CATALOG_MOVEMENT_TARGET_PAIR_DECISION_TYPE",
    "apply_catalog_movement_target_pair_result",
    "catalog_movement_target_pair_move_completed_bindings",
    "invalid_catalog_movement_target_pair_status",
    "request_catalog_movement_target_pair_start_if_available",
)
