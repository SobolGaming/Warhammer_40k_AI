from __future__ import annotations

# This extracted sibling consumes the catalog module's internal typed primitives.
# pyright: reportPrivateUsage=false
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.engine import catalog_rule_consumption as _catalog
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.faction_content.bundle_validation import (
    validate_identifier as _validate_identifier,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UnitMoveCompletedContext,
    UnitMoveCompletedMortalWoundEffect,
    UnitMoveCompletedMortalWoundHookBinding,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


@dataclass(frozen=True, slots=True)
class CatalogUnitMoveCompletedMortalWoundsRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _catalog._validate_ability_index_mapping(self.ability_indexes_by_player_id)
        armies = _catalog._validate_armies(self.armies)
        missing_ids = {army.player_id for army in armies} - set(indexes)
        if missing_ids:
            raise GameLifecycleError(
                "Catalog move-completed mortal wounds missing player ability index."
            )
        object.__setattr__(self, "ability_indexes_by_player_id", MappingProxyType(dict(indexes)))
        object.__setattr__(self, "armies", armies)

    def bindings(self) -> tuple[UnitMoveCompletedMortalWoundHookBinding, ...]:
        if not _catalog._has_catalog_unit_move_completed_mortal_wounds_records(
            self.ability_indexes_by_player_id
        ):
            return ()
        return (
            UnitMoveCompletedMortalWoundHookBinding(
                hook_id=_catalog.CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
                source_id=_catalog.CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
                handler=self.effect_handler,
                request_handler=self.request_handler,
            ),
        )

    def request_handler(self, context: UnitMoveCompletedContext) -> LifecycleStatus | None:
        if type(context) is not UnitMoveCompletedContext:
            raise GameLifecycleError("Catalog move-completed mortal wounds requires context.")
        decisions = _catalog._unit_move_completed_decisions(context)
        groups = _catalog._available_catalog_unit_move_completed_mortal_wounds_groups(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=context,
        )
        if not groups:
            return None
        selected_group_keys = _catalog._resolved_unit_move_completed_mortal_wounds_group_keys(
            decisions
        )
        unresolved_groups = tuple(
            group
            for group in groups
            if _catalog._unit_move_completed_mortal_wounds_group_key(group)
            not in selected_group_keys
        )
        if not unresolved_groups:
            return None
        group = unresolved_groups[0]
        request = DecisionRequest(
            request_id=context.state.next_decision_request_id(),
            decision_type=(
                _catalog.SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE
            ),
            actor_id=context.triggering_player_id,
            payload=validate_json_value(
                _catalog._unit_move_completed_mortal_wounds_target_request_payload(
                    state=context.state,
                    group=group,
                )
            ),
            options=(
                *(
                    (
                        DecisionOption(
                            option_id=(
                                _catalog._unit_move_completed_mortal_wounds_decline_option_id(group)
                            ),
                            label="Decline ability",
                            payload=validate_json_value(
                                _catalog._unit_move_completed_mortal_wounds_decline_payload(
                                    state=context.state,
                                    group=group,
                                )
                            ),
                        ),
                    )
                    if group.optional
                    else ()
                ),
                *tuple(
                    DecisionOption(
                        option_id=option.option_id,
                        label=_catalog._unit_move_completed_mortal_wounds_target_option_label(
                            option
                        ),
                        payload=validate_json_value(
                            _catalog._unit_move_completed_mortal_wounds_target_option_payload(
                                state=context.state,
                                group=group,
                                option=option,
                            )
                        ),
                    )
                    for option in group.options
                ),
            ),
        )
        decisions.request_decision(request)
        decisions.event_log.append(
            "catalog_unit_move_completed_mortal_wounds_target_requested",
            validate_json_value(
                {
                    "game_id": context.state.game_id,
                    "battle_round": context.state.battle_round,
                    "phase": context.completed_phase.value,
                    "active_player_id": context.state.active_player_id,
                    "player_id": context.triggering_player_id,
                    "hook_id": _catalog.CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
                    "request_id": request.request_id,
                    "catalog_record_id": group.record.record_id,
                    "source_rule_id": group.record.definition.source_id,
                    "source_rules_unit_instance_id": group.source_rules_unit_instance_id,
                    "source_unit_instance_id": group.source_unit.unit_instance_id,
                    "clause_id": group.clause.clause_id,
                    "effect_index": group.effect_index,
                    "trigger_event_id": group.trigger_event_id,
                    "movement_action": group.movement_action,
                    "available_target_unit_instance_ids": [
                        option.target_unit_instance_id for option in group.options
                    ],
                    "phase_body_status": (
                        "catalog_unit_move_completed_mortal_wounds_target_pending"
                    ),
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload=validate_json_value(
                {
                    "phase": context.completed_phase.value,
                    "battle_round": context.state.battle_round,
                    "active_player_id": context.state.active_player_id,
                    "player_id": context.triggering_player_id,
                    "pending_request_id": request.request_id,
                    "phase_body_status": (
                        "catalog_unit_move_completed_mortal_wounds_target_pending"
                    ),
                }
            ),
        )

    def effect_handler(
        self,
        context: UnitMoveCompletedContext,
    ) -> tuple[UnitMoveCompletedMortalWoundEffect, ...]:
        if type(context) is not UnitMoveCompletedContext:
            raise GameLifecycleError("Catalog move-completed mortal wounds requires context.")
        decisions = _catalog._unit_move_completed_decisions(context)
        selected_targets = _catalog._selected_unit_move_completed_mortal_wounds_targets(decisions)
        if not selected_targets:
            return ()
        effects: list[UnitMoveCompletedMortalWoundEffect] = []
        for group in _catalog._available_catalog_unit_move_completed_mortal_wounds_groups(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=context,
        ):
            selected = selected_targets.get(
                _catalog._unit_move_completed_mortal_wounds_group_key(group)
            )
            if selected is None:
                continue
            option_by_target = {option.target_unit_instance_id: option for option in group.options}
            option = option_by_target.get(selected.target_unit_instance_id)
            if option is None:
                raise GameLifecycleError(
                    "Catalog move-completed mortal wounds selected target drifted."
                )
            for roll_model_id in group.roll_model_instance_ids:
                effects.append(
                    UnitMoveCompletedMortalWoundEffect(
                        hook_id=(_catalog.CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID),
                        source_id=(
                            _catalog.CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID
                        ),
                        source_rule_id=group.record.definition.source_id,
                        target_unit_instance_id=option.target_unit_instance_id,
                        target_player_id=option.target_player_id,
                        rolling_player_id=context.triggering_player_id,
                        trigger_event_id=context.trigger_event_id,
                        roll_threshold=group.roll_threshold,
                        mortal_wounds_expression=group.mortal_wounds_expression,
                        maximum_total_mortal_wounds=group.maximum_mortal_wounds,
                        mortal_wound_cap_group_id=(
                            (
                                f"{group.trigger_event_id}:{group.record.record_id}:"
                                f"{group.clause.clause_id}:{option.target_unit_instance_id}"
                            )
                            if group.maximum_mortal_wounds is not None
                            else None
                        ),
                        replay_payload=(
                            _catalog._unit_move_completed_mortal_wounds_effect_payload(
                                group=group,
                                option=option,
                                roll_model_instance_id=roll_model_id,
                            )
                        ),
                    )
                )
        return tuple(effects)


def catalog_unit_move_completed_mortal_wound_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[UnitMoveCompletedMortalWoundHookBinding, ...]:
    return CatalogUnitMoveCompletedMortalWoundsRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).bindings()


def invalid_catalog_unit_move_completed_mortal_wounds_target_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    invalid_status = _catalog_unit_move_completed_mortal_wounds_target_finite_invalid_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_catalog_unit_move_completed_mortal_wounds_target_result",
    )
    if invalid_status is not None:
        return invalid_status
    drift_reason = _catalog_unit_move_completed_mortal_wounds_target_drift_reason(
        state=state,
        request=request,
        result=result,
        ruleset_descriptor=ruleset_descriptor,
    )
    if drift_reason is None:
        return None
    return _catalog_unit_move_completed_mortal_wounds_target_invalid_status(
        state=state,
        actor_id=result.actor_id,
        invalid_reason=drift_reason,
    )


def apply_catalog_unit_move_completed_mortal_wounds_target_result(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Catalog move-completed mortal wounds apply requires decisions.")
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Catalog move-completed mortal wounds apply requires result.")
    record = decisions.record_for_result(result)
    invalid_status = invalid_catalog_unit_move_completed_mortal_wounds_target_status(
        state=state,
        request=record.request,
        result=record.result,
        ruleset_descriptor=ruleset_descriptor,
    )
    if invalid_status is not None:
        return invalid_status
    payload = _catalog._payload_object(record.result.payload)
    if payload.get("declined_unit_move_completed_mortal_wounds") is True:
        decisions.event_log.append(
            _catalog.CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_DECLINED_EVENT,
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": _catalog._payload_string(payload, key="phase"),
                    "active_player_id": state.active_player_id,
                    "player_id": record.result.actor_id,
                    "request_id": record.request.request_id,
                    "result_id": record.result.result_id,
                    "selected_option_id": record.result.selected_option_id,
                    "catalog_record_id": _catalog._payload_string(payload, key="catalog_record_id"),
                    "source_rule_id": _catalog._payload_string(payload, key="source_rule_id"),
                    "source_rules_unit_instance_id": _catalog._payload_string(
                        payload, key="source_rules_unit_instance_id"
                    ),
                    "source_unit_instance_id": _catalog._payload_string(
                        payload, key="source_unit_instance_id"
                    ),
                    "clause_id": _catalog._payload_string(payload, key="clause_id"),
                    "effect_index": _catalog._payload_int(payload, key="effect_index"),
                    "trigger_event_id": _catalog._payload_string(payload, key="trigger_event_id"),
                    "movement_action": _catalog._payload_string(payload, key="movement_action"),
                }
            ),
        )
        return None
    selected_payload = _catalog._unit_move_completed_mortal_wounds_selected_payload(payload)
    decisions.event_log.append(
        _catalog.CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_SELECTED_EVENT,
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": _catalog._payload_string(payload, key="phase"),
                "active_player_id": state.active_player_id,
                "player_id": record.result.actor_id,
                "request_id": record.request.request_id,
                "result_id": record.result.result_id,
                "selected_option_id": record.result.selected_option_id,
                "hook_id": _catalog.CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
                "catalog_record_id": _catalog._payload_string(payload, key="catalog_record_id"),
                "source_rule_id": _catalog._payload_string(payload, key="source_rule_id"),
                "source_rules_unit_instance_id": _catalog._payload_string(
                    payload, key="source_rules_unit_instance_id"
                ),
                "source_unit_instance_id": _catalog._payload_string(
                    payload, key="source_unit_instance_id"
                ),
                "clause_id": _catalog._payload_string(payload, key="clause_id"),
                "effect_index": _catalog._payload_int(payload, key="effect_index"),
                "trigger_event_id": _catalog._payload_string(payload, key="trigger_event_id"),
                "movement_action": _catalog._payload_string(payload, key="movement_action"),
                "target_unit_instance_id": _catalog._payload_string(
                    selected_payload, key="target_unit_instance_id"
                ),
                "target_player_id": _catalog._payload_string(
                    selected_payload, key="target_player_id"
                ),
            }
        ),
    )
    _record_catalog_move_completed_stratagem_target_restriction(
        state=state,
        payload=payload,
        result_id=record.result.result_id,
    )
    return None


def _record_catalog_move_completed_stratagem_target_restriction(
    *,
    state: GameState,
    payload: Mapping[str, object],
    result_id: str,
) -> None:
    handler_ids = _catalog._optional_payload_string_tuple(
        payload, key="forbidden_stratagem_handler_ids"
    )
    if not handler_ids:
        return
    source_unit_id = _catalog._payload_string(payload, key="source_rules_unit_instance_id")
    player_id = _catalog._payload_string(payload, key="player_id")
    effect = PersistingEffect(
        effect_id=(
            f"{_validate_identifier('result_id', result_id)}:catalog-stratagem-target-restriction"
        ),
        source_rule_id=_catalog._payload_string(payload, key="source_rule_id"),
        owner_player_id=player_id,
        target_unit_instance_ids=(source_unit_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhaseKind.MOVEMENT,
        expiration=EffectExpiration.end_turn(
            battle_round=state.battle_round,
            player_id=player_id,
        ),
        effect_payload=validate_json_value(
            {
                "effect_kind": _catalog.CATALOG_STRATAGEM_TARGET_RESTRICTION_EFFECT_KIND,
                "catalog_record_id": _catalog._payload_string(payload, key="catalog_record_id"),
                "source_rule_id": _catalog._payload_string(payload, key="source_rule_id"),
                "source_rules_unit_instance_id": source_unit_id,
                "forbidden_stratagem_handler_ids": list(handler_ids),
            }
        ),
    )
    state.record_persisting_effect(effect)


def _catalog_unit_move_completed_mortal_wounds_target_invalid_status(
    *,
    state: GameState,
    actor_id: str | None,
    invalid_reason: str,
) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=GameLifecycleStage.BATTLE,
        message="Catalog move-completed mortal wounds target choice is no longer valid.",
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "player_id": actor_id,
                "battle_round": state.battle_round,
                "phase": (
                    None if state.current_battle_phase is None else state.current_battle_phase.value
                ),
                "invalid_reason": _validate_identifier("invalid_reason", invalid_reason),
            }
        ),
    )


def _catalog_unit_move_completed_mortal_wounds_target_finite_invalid_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    invalid_reason: str,
) -> LifecycleStatus | None:
    fields = (
        (result.request_id != request.request_id, "request_id"),
        (result.decision_type != request.decision_type, "decision_type"),
        (result.actor_id != request.actor_id, "actor_id"),
    )
    for invalid, field in fields:
        if invalid:
            return _catalog_unit_move_completed_mortal_wounds_target_invalid_field_status(
                state=state,
                invalid_reason=invalid_reason,
                field=field,
            )
    selected_option = next(
        (option for option in request.options if option.option_id == result.selected_option_id),
        None,
    )
    if selected_option is None:
        return _catalog_unit_move_completed_mortal_wounds_target_invalid_field_status(
            state=state,
            invalid_reason=invalid_reason,
            field="selected_option_id",
        )
    if result.payload != selected_option.payload:
        return _catalog_unit_move_completed_mortal_wounds_target_invalid_field_status(
            state=state,
            invalid_reason=invalid_reason,
            field="payload",
        )
    return None


def _catalog_unit_move_completed_mortal_wounds_target_invalid_field_status(
    *,
    state: GameState,
    invalid_reason: str,
    field: str,
) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Catalog move-completed mortal wounds target result is invalid.",
        payload=validate_json_value(
            {
                "invalid_reason": _validate_identifier("invalid_reason", invalid_reason),
                "field": _validate_identifier("field", field),
            }
        ),
    )


def _catalog_unit_move_completed_mortal_wounds_target_drift_reason(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> str | None:
    decision_type = _catalog.SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE
    if request.decision_type != decision_type:
        return "request_decision_type_drift"
    if result.decision_type != decision_type:
        return "result_decision_type_drift"
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Catalog move-completed mortal wounds requires ruleset.")
    request_payload = _catalog._optional_payload_object(request.payload)
    if request_payload is None:
        return "request_payload_not_object"
    result_payload = _catalog._optional_payload_object(result.payload)
    if result_payload is None:
        return "payload_not_object"
    if result_payload.get("submission_kind") != (
        _catalog.SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_SUBMISSION_KIND
    ):
        return "submission_kind_drift"
    hook_id = _catalog.CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID
    if result_payload.get("hook_id") != hook_id:
        return "hook_id_drift"
    if request_payload.get("hook_id") != hook_id:
        return "request_hook_id_drift"
    phase_value = result_payload.get("phase")
    if type(phase_value) is not str:
        return "payload_phase_drift"
    try:
        expected_phase = BattlePhase(phase_value)
    except ValueError:
        return "payload_phase_drift"
    if expected_phase not in {BattlePhase.CHARGE, BattlePhase.MOVEMENT}:
        return "payload_phase_drift"
    if state.current_battle_phase is not expected_phase:
        return "phase_drift"
    drift_checks = (
        (result_payload.get("game_id") != state.game_id, "game_id_drift"),
        (request_payload.get("game_id") != state.game_id, "request_game_id_drift"),
        (result_payload.get("battle_round") != state.battle_round, "battle_round_drift"),
        (
            request_payload.get("battle_round") != state.battle_round,
            "request_battle_round_drift",
        ),
        (request_payload.get("phase") != expected_phase.value, "request_phase_drift"),
        (
            result_payload.get("active_player_id") != state.active_player_id,
            "active_player_drift",
        ),
        (
            request_payload.get("active_player_id") != state.active_player_id,
            "request_active_player_drift",
        ),
    )
    for drifted, reason in drift_checks:
        if drifted:
            return reason
    actor_id = _validate_identifier("actor_id", result.actor_id)
    if result_payload.get("player_id") != actor_id:
        return "actor_player_drift"
    if result_payload.get("declined_unit_move_completed_mortal_wounds") is True:
        if result_payload.get("optional") is not True:
            return "decline_not_optional"
        return None
    selected_payload = result_payload.get("selected_unit_move_completed_mortal_wounds_target")
    if not isinstance(selected_payload, dict):
        return "selected_payload_not_object"
    selected_payload_object = cast(dict[str, object], selected_payload)
    if selected_payload_object.get("option_id") != result.selected_option_id:
        return "selected_option_payload_drift"
    selected_target_id = selected_payload_object.get("target_unit_instance_id")
    selected_target_player_id = selected_payload_object.get("target_player_id")
    if type(selected_target_id) is not str or type(selected_target_player_id) is not str:
        return "selected_target_payload_drift"
    source_rules_unit_id = result_payload.get("source_rules_unit_instance_id")
    if type(source_rules_unit_id) is not str:
        return "source_rules_unit_payload_drift"
    source_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=source_rules_unit_id,
    )
    if source_rules_unit.owner_player_id != actor_id:
        return "source_rules_unit_owner_drift"
    if not _catalog._unit_move_completed_mortal_wounds_target_is_eligible(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        source_rules_unit_instance_id=source_rules_unit_id,
        target_unit_instance_id=selected_target_id,
        target_player_id=selected_target_player_id,
        target_range_inches=_catalog._optional_payload_positive_int(
            result_payload, key="target_range_inches"
        ),
        target_requires_visibility=result_payload.get("target_requires_visibility") is True,
    ):
        return "target_drift"
    return None
