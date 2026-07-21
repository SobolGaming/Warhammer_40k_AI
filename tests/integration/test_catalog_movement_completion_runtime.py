# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.support.catalog_package_fixtures import (
    flesh_hounds_army,
    flesh_hounds_package,
    flesh_hounds_unit,
)
from tests.support.catalog_rule_ir_fixtures import (
    charge_end_mortal_wounds_record,
    charge_end_mortal_wounds_rule_ir,
)
from tests.support.catalog_runtime_fixtures import (
    battle_state_with_armies,
    flesh_hounds_battlefield_state,
)

from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptor,
)
from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
    CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_SELECTED_EVENT,
    SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE,
    SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_SUBMISSION_KIND,
    _clause_is_supported_unit_move_completed_mortal_wounds,
    _record_can_select_catalog_unit_move_completed_mortal_wounds_target,
    catalog_rule_ir_consumers_for_rule,
    catalog_rule_ir_hook_ids_for_rule,
)
from warhammer40k_core.engine.catalog_unit_move_completed_mortal_wounds_runtime import (
    CatalogUnitMoveCompletedMortalWoundsRuntime,
    apply_catalog_unit_move_completed_mortal_wounds_target_result,
    invalid_catalog_unit_move_completed_mortal_wounds_target_status,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_ROLLED_EVENT,
    UnitMoveCompletedContext,
    UnitMoveCompletedMortalWoundHookRegistry,
    resolve_unit_move_completed_mortal_wound_hooks,
)
from warhammer40k_core.rules.rule_ir import (
    RuleConditionKind,
    RuleEffectKind,
    RuleTargetKind,
    parameter_payload,
)


def test_phase17k_charge_end_catalog_mortal_wounds_selects_target_and_rolls_per_model() -> None:
    package = flesh_hounds_package()
    unit = flesh_hounds_unit(package=package)
    target_unit = flesh_hounds_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-flesh-hounds-1",
    )
    army = flesh_hounds_army(package=package, unit=unit)
    enemy_army = flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    rule_ir = charge_end_mortal_wounds_rule_ir()
    clause = rule_ir.clauses[0]
    distance_conditions = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.DISTANCE_PREDICATE
    )
    effect_parameters = parameter_payload(clause.effects[0].parameters)
    record = charge_end_mortal_wounds_record(rule_ir=rule_ir, datasheet_id=unit.datasheet_id)
    ability_index = AbilityCatalogIndex.from_records((record,))
    enemy_index = AbilityCatalogIndex.from_records(())
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    battlefield = flesh_hounds_battlefield_state(
        army=army,
        unit=unit,
        enemy_army=enemy_army,
        enemy_unit=target_unit,
        enemy_x=13.0,
    )
    state = battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.CHARGE,
    )
    state.game_id = "phase17k-charge-mw-7"
    decisions = DecisionController()
    runtime = CatalogUnitMoveCompletedMortalWoundsRuntime(
        ability_indexes_by_player_id={
            army.player_id: ability_index,
            enemy_army.player_id: enemy_index,
        },
        armies=(army, enemy_army),
    )
    registry = UnitMoveCompletedMortalWoundHookRegistry.from_bindings(runtime.bindings())

    assert rule_ir.is_supported
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.ENEMY_UNIT
    assert len(distance_conditions) == 1
    distance_parameters = parameter_payload(distance_conditions[0].parameters)
    assert distance_parameters["negated"] is False
    assert distance_parameters["object_kind"] == "unit"
    assert distance_parameters["object_reference"] == "this"
    assert distance_parameters["predicate"] == "within_engagement_range"
    assert distance_parameters["range_kind"] == "engagement_range"
    assert clause.effects[0].kind is RuleEffectKind.INFLICT_MORTAL_WOUNDS
    assert effect_parameters == {
        "damage_kind": "mortal_wounds",
        "mortal_wounds_expression": "D3",
        "roll_count": 1,
        "roll_count_scope": "each_model_in_this_unit",
        "roll_expression": "D6",
        "success_threshold": 4,
        "target_scope": "selected_enemy_unit",
    }
    assert _clause_is_supported_unit_move_completed_mortal_wounds(clause)
    assert _record_can_select_catalog_unit_move_completed_mortal_wounds_target(record)
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
    )

    decisions.event_log.append(
        "charge_move_completed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.CHARGE.value,
            "active_player_id": army.player_id,
            "unit_instance_id": unit.unit_instance_id,
            "movement_phase_action": "charge_move",
        },
    )
    status = resolve_unit_move_completed_mortal_wound_hooks(
        state=state,
        decisions=decisions,
        registry=registry,
        ruleset_descriptor=ruleset,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        completed_phase=BattlePhase.CHARGE,
        event_type="charge_move_completed",
        movement_actions=("charge_move",),
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = status.decision_request
    assert request is not None
    request_payload = cast(dict[str, object], request.payload)
    assert (
        request.decision_type
        == SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_DECISION_TYPE
    )
    assert request.actor_id == army.player_id
    assert type(request).from_payload(request.to_payload()).to_payload() == request.to_payload()
    assert request_payload["submission_kind"] == (
        SELECT_CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_SUBMISSION_KIND
    )
    assert request_payload["roll_model_instance_ids"] == [
        model.model_instance_id for model in unit.own_models
    ]
    assert [option.payload for option in request.options] == [
        {
            **{
                key: value
                for key, value in request_payload.items()
                if key
                not in {
                    "available_target_unit_instance_ids",
                    "available_unit_move_completed_mortal_wounds_target_options",
                }
            },
            "selected_unit_move_completed_mortal_wounds_target": {
                "option_id": request.options[0].option_id,
                "target_unit_instance_id": target_unit.unit_instance_id,
                "target_player_id": enemy_army.player_id,
            },
        }
    ]

    result = DecisionResult.for_request(
        result_id="phase17k-charge-mw-target",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    stale_state = battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.FIGHT,
    )
    stale_state.game_id = state.game_id
    stale_status = invalid_catalog_unit_move_completed_mortal_wounds_target_status(
        state=stale_state,
        request=request,
        result=result,
        ruleset_descriptor=ruleset,
    )
    assert stale_status is not None
    stale_payload = cast(dict[str, JsonValue], stale_status.payload)
    assert stale_payload["invalid_reason"] == "phase_drift"

    drifted_state = battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=flesh_hounds_battlefield_state(
            army=army,
            unit=unit,
            enemy_army=enemy_army,
            enemy_unit=target_unit,
            enemy_x=30.0,
        ),
        active_player_id=army.player_id,
        phase=BattlePhase.CHARGE,
    )
    drifted_state.game_id = state.game_id
    drift_status = invalid_catalog_unit_move_completed_mortal_wounds_target_status(
        state=drifted_state,
        request=request,
        result=result,
        ruleset_descriptor=ruleset,
    )
    assert drift_status is not None
    drift_payload = cast(dict[str, JsonValue], drift_status.payload)
    assert drift_payload["invalid_reason"] == "target_drift"

    malformed_status = invalid_catalog_unit_move_completed_mortal_wounds_target_status(
        state=state,
        request=request,
        result=DecisionResult(
            result_id="phase17k-charge-mw-target-malformed",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id="phase17k-missing-option",
            payload=request.options[0].payload,
        ),
        ruleset_descriptor=ruleset,
    )
    assert malformed_status is not None
    malformed_payload = cast(dict[str, JsonValue], malformed_status.payload)
    assert malformed_payload["field"] == "selected_option_id"

    base_request_payload = cast(dict[str, JsonValue], request.payload)
    base_option_payload = cast(dict[str, JsonValue], request.options[0].payload)

    def invalid_reason_for_payload(
        *,
        expected_reason: str,
        option_payload: dict[str, JsonValue],
        request_payload: dict[str, JsonValue] | JsonValue | None = None,
    ) -> str:
        updated_request = replace(
            request,
            payload=validate_json_value(
                base_request_payload if request_payload is None else request_payload
            ),
            options=(
                replace(
                    request.options[0],
                    payload=validate_json_value(option_payload),
                ),
            ),
        )
        status = invalid_catalog_unit_move_completed_mortal_wounds_target_status(
            state=state,
            request=updated_request,
            result=DecisionResult(
                result_id=f"phase17k-charge-mw-target-{expected_reason}",
                request_id=updated_request.request_id,
                decision_type=updated_request.decision_type,
                actor_id=updated_request.actor_id,
                selected_option_id=updated_request.options[0].option_id,
                payload=validate_json_value(option_payload),
            ),
            ruleset_descriptor=ruleset,
        )
        assert status is not None
        payload = cast(dict[str, JsonValue], status.payload)
        return cast(str, payload["invalid_reason"])

    for key, value, expected_reason in (
        ("submission_kind", "changed", "submission_kind_drift"),
        ("hook_id", "changed", "hook_id_drift"),
        ("game_id", "changed", "game_id_drift"),
        ("battle_round", 2, "battle_round_drift"),
        ("phase", BattlePhase.FIGHT.value, "payload_phase_drift"),
        ("active_player_id", enemy_army.player_id, "active_player_drift"),
        ("player_id", enemy_army.player_id, "actor_player_drift"),
    ):
        payload = dict(base_option_payload)
        payload[key] = cast(JsonValue, value)
        assert (
            invalid_reason_for_payload(
                expected_reason=expected_reason,
                option_payload=payload,
            )
            == expected_reason
        )

    for key, value, expected_reason in (
        ("hook_id", "changed", "request_hook_id_drift"),
        ("game_id", "changed", "request_game_id_drift"),
        ("battle_round", 2, "request_battle_round_drift"),
        ("phase", BattlePhase.FIGHT.value, "request_phase_drift"),
        ("active_player_id", enemy_army.player_id, "request_active_player_drift"),
    ):
        payload = dict(base_request_payload)
        payload[key] = cast(JsonValue, value)
        assert (
            invalid_reason_for_payload(
                expected_reason=expected_reason,
                option_payload=dict(base_option_payload),
                request_payload=payload,
            )
            == expected_reason
        )

    selected_not_object_payload = dict(base_option_payload)
    selected_not_object_payload["selected_unit_move_completed_mortal_wounds_target"] = "changed"
    assert (
        invalid_reason_for_payload(
            expected_reason="selected_payload_not_object",
            option_payload=selected_not_object_payload,
        )
        == "selected_payload_not_object"
    )

    selected_option_drift_payload = dict(base_option_payload)
    selected_payload = dict(
        cast(
            dict[str, JsonValue],
            selected_option_drift_payload["selected_unit_move_completed_mortal_wounds_target"],
        )
    )
    selected_payload["option_id"] = "changed"
    selected_option_drift_payload["selected_unit_move_completed_mortal_wounds_target"] = (
        selected_payload
    )
    assert (
        invalid_reason_for_payload(
            expected_reason="selected_option_payload_drift",
            option_payload=selected_option_drift_payload,
        )
        == "selected_option_payload_drift"
    )

    selected_target_type_payload = dict(base_option_payload)
    selected_payload = dict(
        cast(
            dict[str, JsonValue],
            selected_target_type_payload["selected_unit_move_completed_mortal_wounds_target"],
        )
    )
    selected_payload["target_unit_instance_id"] = 1
    selected_target_type_payload["selected_unit_move_completed_mortal_wounds_target"] = (
        selected_payload
    )
    assert (
        invalid_reason_for_payload(
            expected_reason="selected_target_payload_drift",
            option_payload=selected_target_type_payload,
        )
        == "selected_target_payload_drift"
    )

    source_rules_unit_type_payload = dict(base_option_payload)
    source_rules_unit_type_payload["source_rules_unit_instance_id"] = 1
    assert (
        invalid_reason_for_payload(
            expected_reason="source_rules_unit_payload_drift",
            option_payload=source_rules_unit_type_payload,
        )
        == "source_rules_unit_payload_drift"
    )

    source_rules_unit_owner_payload = dict(base_option_payload)
    source_rules_unit_owner_payload["source_rules_unit_instance_id"] = target_unit.unit_instance_id
    assert (
        invalid_reason_for_payload(
            expected_reason="source_rules_unit_owner_drift",
            option_payload=source_rules_unit_owner_payload,
        )
        == "source_rules_unit_owner_drift"
    )

    assert (
        invalid_catalog_unit_move_completed_mortal_wounds_target_status(
            state=state,
            request=request,
            result=result,
            ruleset_descriptor=ruleset,
        )
        is None
    )
    decisions.submit_result(result)
    assert (
        apply_catalog_unit_move_completed_mortal_wounds_target_result(
            state=state,
            decisions=decisions,
            result=result,
            ruleset_descriptor=ruleset,
        )
        is None
    )
    selected_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_TARGET_SELECTED_EVENT
    )
    assert len(selected_events) == 1
    selected_payload = cast(dict[str, JsonValue], selected_events[0].payload)
    assert selected_payload["target_unit_instance_id"] == target_unit.unit_instance_id

    assert (
        resolve_unit_move_completed_mortal_wound_hooks(
            state=state,
            decisions=decisions,
            registry=registry,
            ruleset_descriptor=ruleset,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            completed_phase=BattlePhase.CHARGE,
            event_type="charge_move_completed",
            movement_actions=("charge_move",),
        )
        is None
    )
    rolled_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_ROLLED_EVENT
    )
    assert len(rolled_events) == len(unit.own_models)
    rolled_model_ids: set[str] = set()
    for event in rolled_events:
        payload = cast(dict[str, JsonValue], event.payload)
        assert payload["hook_id"] == CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID
        assert payload["source_rule_id"] == record.definition.source_id
        assert payload["source_rule_id"] != CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID
        replay_payload = cast(
            dict[str, JsonValue],
            payload["replay_payload"],
        )
        assert replay_payload["catalog_source_rule_id"] == record.definition.source_id
        roll_model_id = replay_payload["roll_model_instance_id"]
        assert type(roll_model_id) is str
        rolled_model_ids.add(roll_model_id)
    assert rolled_model_ids == {model.model_instance_id for model in unit.own_models}
    assert "object at 0x" not in json.dumps(decisions.to_payload(), sort_keys=True)


def test_phase17k_charge_end_catalog_mortal_wounds_runtime_noops_and_fail_fast() -> None:
    package = flesh_hounds_package()
    unit = flesh_hounds_unit(package=package)
    target_unit = flesh_hounds_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-flesh-hounds-1",
    )
    army = flesh_hounds_army(package=package, unit=unit)
    enemy_army = flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    rule_ir = charge_end_mortal_wounds_rule_ir()
    record = charge_end_mortal_wounds_record(rule_ir=rule_ir, datasheet_id=unit.datasheet_id)
    ability_index = AbilityCatalogIndex.from_records((record,))
    enemy_index = AbilityCatalogIndex.from_records(())
    empty_index = AbilityCatalogIndex.from_records(())
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    state = battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=flesh_hounds_battlefield_state(
            army=army,
            unit=unit,
            enemy_army=enemy_army,
            enemy_unit=target_unit,
            enemy_x=30.0,
        ),
        active_player_id=army.player_id,
        phase=BattlePhase.CHARGE,
    )
    decisions = DecisionController()
    context = UnitMoveCompletedContext(
        state=state,
        ruleset_descriptor=ruleset,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        completed_phase=BattlePhase.CHARGE,
        trigger_event_id="charge-move-completed-001",
        trigger_event_payload={
            "unit_instance_id": unit.unit_instance_id,
            "movement_phase_action": "charge_move",
        },
        triggering_unit_instance_id=unit.unit_instance_id,
        triggering_player_id=army.player_id,
        movement_action="charge_move",
        decisions=decisions,
    )

    with pytest.raises(GameLifecycleError, match="missing player ability index"):
        CatalogUnitMoveCompletedMortalWoundsRuntime(
            ability_indexes_by_player_id={army.player_id: ability_index},
            armies=(army, enemy_army),
        )

    empty_runtime = CatalogUnitMoveCompletedMortalWoundsRuntime(
        ability_indexes_by_player_id={
            army.player_id: empty_index,
            enemy_army.player_id: empty_index,
        },
        armies=(army, enemy_army),
    )
    runtime = CatalogUnitMoveCompletedMortalWoundsRuntime(
        ability_indexes_by_player_id={
            army.player_id: ability_index,
            enemy_army.player_id: enemy_index,
        },
        armies=(army, enemy_army),
    )

    assert empty_runtime.bindings() == ()
    with pytest.raises(GameLifecycleError, match="requires context"):
        runtime.request_handler(cast(UnitMoveCompletedContext, object()))
    with pytest.raises(GameLifecycleError, match="requires context"):
        runtime.effect_handler(cast(UnitMoveCompletedContext, object()))
    assert runtime.request_handler(context) is None
    assert runtime.effect_handler(context) == ()
