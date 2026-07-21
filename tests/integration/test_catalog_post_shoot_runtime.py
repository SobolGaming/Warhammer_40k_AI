# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

from tests.support.catalog_package_fixtures import (
    flesh_hounds_army,
    named_weapon_choice_unit,
    post_shoot_cover_denial_package,
    post_shoot_selected_target_effect_package,
)
from tests.support.catalog_rule_ir_fixtures import (
    multi_clause_post_shoot_cover_denial_record,
    multi_clause_post_shoot_cover_denial_rule_ir,
)
from tests.support.catalog_runtime_fixtures import (
    battle_state_with_armies,
    completed_post_shoot_attack_sequence,
    emit_successful_hit,
    emit_wound_result,
    flesh_hounds_battlefield_state,
    pending_completed_attack_sequence_for_test,
    player_ability_index,
)

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceRollResult
from warhammer40k_core.core.ruleset_descriptor import (
    CoverEffect,
    CoverPolicyDescriptor,
    RulesetDescriptor,
)
from warhammer40k_core.core.weapon_profiles import (
    DamageProfile,
)
from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
)
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    AttackSequenceStep,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    AttackSequenceCompletedHookRegistry,
    successful_hit_target_unit_ids_for_sequence,
)
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
    CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
    CATALOG_POST_SHOOT_HIT_TARGET_STATUS_EFFECT_KIND,
    CATALOG_POST_SHOOT_HIT_TARGET_STATUS_SELECTED_EVENT,
    SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE,
    SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_SUBMISSION_KIND,
    CatalogPostShootHitTargetStatusRuntime,
    _available_catalog_post_shoot_hit_target_status_groups,
    _record_can_select_catalog_post_shoot_hit_target_status,
    apply_catalog_post_shoot_hit_target_status_result,
    catalog_rule_ir_consumers_for_rule,
    catalog_rule_ir_hook_ids_for_rule,
    invalid_catalog_post_shoot_hit_target_status_status,
)
from warhammer40k_core.engine.catalog_selected_target_effects import (
    CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
    SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE,
    SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SUBMISSION_KIND,
    CatalogSelectedTargetEffectRuntime,
    apply_catalog_post_shoot_hit_target_effect_result,
    invalid_catalog_post_shoot_hit_target_effect_status,
)
from warhammer40k_core.engine.core_stratagem_effects import SMOKESCREEN_EFFECT_KIND
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import (
    BattlePhase,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.shooting import ShootingPhaseHandler, ShootingPhaseState
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.saves import (
    SaveKind,
    SaveResolutionRule,
    saving_throw_roll_spec,
)
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.rules.rule_ir import (
    RuleIR,
    RuleIRPayload,
)


def test_phase17k_post_shoot_hit_target_cover_denial_records_and_applies_effect() -> None:
    package = post_shoot_cover_denial_package()
    unit = named_weapon_choice_unit(package=package)
    target_unit = named_weapon_choice_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-lord-of-change-1",
    )
    army = flesh_hounds_army(package=package, unit=unit)
    enemy_army = flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    player_index = player_ability_index(package=package, army=army)
    enemy_player_index = player_ability_index(package=package, army=enemy_army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    cover_record = records_by_name["Purge and Cleanse"]
    replay_payload = cast(dict[str, JsonValue], cover_record.definition.replay_payload)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    battlefield = flesh_hounds_battlefield_state(
        army=army,
        unit=unit,
        enemy_army=enemy_army,
        enemy_unit=target_unit,
        enemy_x=24.0,
    )
    state = battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    decisions = DecisionController()
    attack_sequence = completed_post_shoot_attack_sequence(
        package=package,
        attacker=unit,
        target=target_unit,
    )
    emit_successful_hit(
        decisions=decisions,
        attack_sequence=attack_sequence,
        successful=True,
    )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": army.player_id,
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    context = AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=attack_sequence,
        attack_sequence_completed_event_id=completed_event.event_id,
    )
    runtime = CatalogPostShootHitTargetStatusRuntime(
        ability_indexes_by_player_id={
            army.player_id: player_index,
            enemy_army.player_id: enemy_player_index,
        },
        armies=(army, enemy_army),
    )

    groups = _available_catalog_post_shoot_hit_target_status_groups(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army, enemy_army),
        context=context,
    )
    status = runtime.request_handler(context)

    assert _record_can_select_catalog_post_shoot_hit_target_status(cover_record)
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
    )
    assert catalog_rule_ir_hook_ids_for_rule(rule_ir) == (
        CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
    )
    assert len(groups) == 1
    assert groups[0].record.record_id == cover_record.record_id
    assert groups[0].clause.clause_id == rule_ir.clauses[0].clause_id
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = decisions.queue.peek_next()
    assert request is not None
    assert request.decision_type == SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE
    assert request.actor_id == army.player_id
    assert type(request).from_payload(request.to_payload()).to_payload() == request.to_payload()
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["submission_kind"] == (
        SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_SUBMISSION_KIND
    )
    assert request_payload["catalog_record_id"] == cover_record.record_id
    assert request_payload["status"] == "benefit_of_cover"
    assert request_payload["available_target_unit_instance_ids"] == [target_unit.unit_instance_id]
    assert tuple(option.label for option in request.options) == (
        f"Deny Benefit of Cover to {target_unit.unit_instance_id}",
    )

    result = DecisionResult.for_request(
        result_id="phase17k-post-shoot-cover-denial",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    assert (
        invalid_catalog_post_shoot_hit_target_status_status(
            state=state,
            request=request,
            result=result,
        )
        is None
    )
    decisions.submit_result(result)
    apply_status = apply_catalog_post_shoot_hit_target_status_result(
        state=state,
        decisions=decisions,
        result=result,
    )
    effects = state.persisting_effects_for_unit(target_unit.unit_instance_id)

    assert apply_status is None
    assert len(effects) == 1
    effect_payload = cast(dict[str, JsonValue], effects[0].effect_payload)
    assert effect_payload["effect_kind"] == CATALOG_POST_SHOOT_HIT_TARGET_STATUS_EFFECT_KIND
    assert effect_payload["benefit_of_cover_denied"] is True
    assert effect_payload["catalog_record_id"] == cover_record.record_id
    assert effect_payload["rule_ir_hash"] == rule_ir.ir_hash()
    assert effects[0].expiration == EffectExpiration.end_phase(
        battle_round=state.battle_round,
        phase=BattlePhase.SHOOTING,
        player_id=army.player_id,
    )
    selected_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_POST_SHOOT_HIT_TARGET_STATUS_SELECTED_EVENT
    )
    assert len(selected_events) == 1
    assert "object at 0x" not in json.dumps(decisions.to_payload(), sort_keys=True)

    stale_state = battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.FIGHT,
    )
    stale_status = invalid_catalog_post_shoot_hit_target_status_status(
        state=stale_state,
        request=request,
        result=result,
    )
    assert stale_status is not None
    stale_payload = cast(dict[str, JsonValue], stale_status.payload)
    assert stale_payload["invalid_reason"] == "phase_drift"

    drifted_payload = dict(cast(dict[str, JsonValue], request.options[0].payload))
    drifted_payload["status"] = "changed"
    drift_status = invalid_catalog_post_shoot_hit_target_status_status(
        state=state,
        request=request,
        result=DecisionResult(
            result_id="phase17k-post-shoot-cover-denial-drift",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=request.options[0].option_id,
            payload=drifted_payload,
        ),
    )
    assert drift_status is not None
    drift_payload = cast(dict[str, JsonValue], drift_status.payload)
    assert drift_payload["field"] == "payload"

    malformed_status = invalid_catalog_post_shoot_hit_target_status_status(
        state=state,
        request=request,
        result=DecisionResult(
            result_id="phase17k-post-shoot-cover-denial-malformed",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id="phase17k-missing-option",
            payload=request.options[0].payload,
        ),
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
        status = invalid_catalog_post_shoot_hit_target_status_status(
            state=state,
            request=updated_request,
            result=DecisionResult(
                result_id=f"phase17k-post-shoot-cover-denial-{expected_reason}",
                request_id=updated_request.request_id,
                decision_type=updated_request.decision_type,
                actor_id=updated_request.actor_id,
                selected_option_id=updated_request.options[0].option_id,
                payload=validate_json_value(option_payload),
            ),
        )
        assert status is not None
        payload = cast(dict[str, JsonValue], status.payload)
        return cast(str, payload["invalid_reason"])

    for key, value, expected_reason in (
        ("submission_kind", "changed", "submission_kind_drift"),
        ("hook_id", "changed", "hook_id_drift"),
        ("game_id", "changed", "game_id_drift"),
        ("battle_round", 2, "battle_round_drift"),
        ("phase", "fight", "payload_phase_drift"),
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
        ("phase", "fight", "request_phase_drift"),
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

    assert (
        invalid_reason_for_payload(
            expected_reason="request_payload_not_object",
            option_payload=dict(base_option_payload),
            request_payload="not-an-object",
        )
        == "request_payload_not_object"
    )

    selected_not_object_payload = dict(base_option_payload)
    selected_not_object_payload["selected_post_shoot_hit_target_status"] = "not-an-object"
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
            selected_option_drift_payload["selected_post_shoot_hit_target_status"],
        )
    )
    selected_payload["option_id"] = "changed"
    selected_option_drift_payload["selected_post_shoot_hit_target_status"] = selected_payload
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
            selected_target_type_payload["selected_post_shoot_hit_target_status"],
        )
    )
    selected_payload["target_unit_instance_id"] = 1
    selected_target_type_payload["selected_post_shoot_hit_target_status"] = selected_payload
    assert (
        invalid_reason_for_payload(
            expected_reason="selected_target_payload_drift",
            option_payload=selected_target_type_payload,
        )
        == "selected_target_payload_drift"
    )

    target_drift_payload = dict(base_option_payload)
    selected_payload = dict(
        cast(dict[str, JsonValue], target_drift_payload["selected_post_shoot_hit_target_status"])
    )
    selected_payload["target_unit_instance_id"] = unit.unit_instance_id
    target_drift_payload["selected_post_shoot_hit_target_status"] = selected_payload
    assert (
        invalid_reason_for_payload(
            expected_reason="target_drift",
            option_payload=target_drift_payload,
        )
        == "target_drift"
    )

    for key, value, expected_reason in (
        ("source_phase", BattlePhase.FIGHT.value, "attack_sequence_phase_drift"),
        ("sequence_id", "changed-sequence", "attack_sequence_id_drift"),
        ("attacker_player_id", enemy_army.player_id, "attack_sequence_attacker_drift"),
        ("attacking_unit_instance_id", target_unit.unit_instance_id, "attack_sequence_unit_drift"),
    ):
        payload = dict(base_option_payload)
        attack_sequence_payload = dict(cast(dict[str, JsonValue], payload["attack_sequence"]))
        attack_sequence_payload[key] = value
        payload["attack_sequence"] = attack_sequence_payload
        assert (
            invalid_reason_for_payload(
                expected_reason=expected_reason,
                option_payload=payload,
            )
            == expected_reason
        )

    assert successful_hit_target_unit_ids_for_sequence(
        decisions=decisions,
        sequence=attack_sequence,
        attacker_model_instance_id=unit.own_models[0].model_instance_id,
        wargear_ids=(attack_sequence.attack_pools[0].wargear_id,),
        weapon_profile_ids=(attack_sequence.attack_pools[0].weapon_profile_id,),
    ) == (target_unit.unit_instance_id,)
    assert (
        successful_hit_target_unit_ids_for_sequence(
            decisions=decisions,
            sequence=attack_sequence,
            attacker_model_instance_id="phase17k-other-model",
        )
        == ()
    )
    assert (
        successful_hit_target_unit_ids_for_sequence(
            decisions=decisions,
            sequence=attack_sequence,
            wargear_ids=("phase17k-other-wargear",),
        )
        == ()
    )
    assert (
        successful_hit_target_unit_ids_for_sequence(
            decisions=decisions,
            sequence=attack_sequence,
            weapon_profile_ids=("phase17k-other-profile",),
        )
        == ()
    )


def test_phase17k_post_shoot_selected_target_effect_records_generic_rule_effect() -> None:
    package = post_shoot_selected_target_effect_package()
    unit = named_weapon_choice_unit(package=package)
    target_unit = named_weapon_choice_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-lord-of-change-1",
    )
    army = flesh_hounds_army(package=package, unit=unit)
    enemy_army = flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    player_index = player_ability_index(package=package, army=army)
    enemy_player_index = player_ability_index(package=package, army=enemy_army)
    record = next(
        record
        for record in player_index.all_records()
        if record.definition.name == "Warpflame Locus" and record.record_id.endswith(":clause:001")
    )
    replay_payload = cast(dict[str, JsonValue], record.definition.replay_payload)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    battlefield = flesh_hounds_battlefield_state(
        army=army,
        unit=unit,
        enemy_army=enemy_army,
        enemy_unit=target_unit,
        enemy_x=24.0,
    )
    state = battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    decisions = DecisionController()
    attack_sequence = completed_post_shoot_attack_sequence(
        package=package,
        attacker=unit,
        target=target_unit,
    )
    emit_successful_hit(
        decisions=decisions,
        attack_sequence=attack_sequence,
        successful=True,
    )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": army.player_id,
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    context = AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=attack_sequence,
        attack_sequence_completed_event_id=completed_event.event_id,
    )
    status = CatalogSelectedTargetEffectRuntime(
        ability_indexes_by_player_id={
            army.player_id: player_index,
            enemy_army.player_id: enemy_player_index,
        },
        armies=(army, enemy_army),
    ).post_shoot_hit_target_request(context)

    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
    )
    assert CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID in (
        catalog_rule_ir_hook_ids_for_rule(rule_ir)
    )
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = decisions.queue.peek_next()
    assert request is not None
    assert request.decision_type == SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE
    assert request.actor_id == army.player_id
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["submission_kind"] == (
        SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SUBMISSION_KIND
    )
    assert request_payload["catalog_record_id"] == record.record_id
    assert request_payload["available_target_unit_instance_ids"] == [target_unit.unit_instance_id]
    option_payload = cast(dict[str, JsonValue], request.options[0].payload)
    effect_records = cast(list[dict[str, JsonValue]], option_payload["generic_rule_effect_records"])
    assert len(effect_records) == 1
    assert effect_records[0]["target_unit_instance_ids"] == [unit.unit_instance_id]

    result = DecisionResult.for_request(
        result_id="phase17k-post-shoot-selected-target-effect",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    assert (
        invalid_catalog_post_shoot_hit_target_effect_status(
            state=state,
            request=request,
            result=result,
        )
        is None
    )
    decisions.submit_result(result)
    assert (
        apply_catalog_post_shoot_hit_target_effect_result(
            state=state,
            decisions=decisions,
            result=result,
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            ability_indexes_by_player_id={
                army.player_id: player_index,
                enemy_army.player_id: enemy_player_index,
            },
        )
        is None
    )
    effects = state.persisting_effects_for_unit(unit.unit_instance_id)
    assert len(effects) == 1
    effect_payload = cast(dict[str, JsonValue], effects[0].effect_payload)
    selected_payload = cast(dict[str, JsonValue], effect_payload["catalog_selected_target"])
    effect_spec_payload = cast(dict[str, JsonValue], effect_payload["effect"])
    effect_parameters = {
        cast(str, item["key"]): item["value"]
        for item in cast(list[dict[str, JsonValue]], effect_spec_payload["parameters"])
    }

    assert effect_payload["effect_kind"] == GENERIC_RULE_EFFECT_KIND
    assert effect_payload["rule_ir_hash"] == rule_ir.ir_hash()
    assert selected_payload["selected_target_unit_instance_id"] == target_unit.unit_instance_id
    assert selected_payload["attack_sequence_completed_event_id"] == completed_event.event_id
    assert effect_parameters["characteristic"] == "damage"
    assert effect_parameters["delta"] == 1
    assert effect_parameters["selected_target_unit_instance_id"] == target_unit.unit_instance_id
    assert effects[0].expiration == EffectExpiration.end_phase(
        battle_round=state.battle_round,
        phase=BattlePhase.SHOOTING,
        player_id=army.player_id,
    )
    selected_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT
    )
    assert len(selected_events) == 1

    stale_state = battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.FIGHT,
    )
    stale_status = invalid_catalog_post_shoot_hit_target_effect_status(
        state=stale_state,
        request=request,
        result=result,
    )
    assert stale_status is not None
    stale_payload = cast(dict[str, JsonValue], stale_status.payload)
    assert stale_payload["field"] == "state_phase"

    drifted_payload = dict(option_payload)
    drifted_payload["hook_id"] = "changed"
    drift_status = invalid_catalog_post_shoot_hit_target_effect_status(
        state=state,
        request=request,
        result=DecisionResult(
            result_id="phase17k-post-shoot-selected-target-effect-drift",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=request.options[0].option_id,
            payload=drifted_payload,
        ),
    )
    assert drift_status is not None
    drift_payload = cast(dict[str, JsonValue], drift_status.payload)
    assert drift_payload["field"] == "payload"

    malformed_status = invalid_catalog_post_shoot_hit_target_effect_status(
        state=state,
        request=request,
        result=DecisionResult(
            result_id="phase17k-post-shoot-selected-target-effect-malformed",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id="phase17k-missing-option",
            payload=request.options[0].payload,
        ),
    )
    assert malformed_status is not None
    malformed_payload = cast(dict[str, JsonValue], malformed_status.payload)
    assert malformed_payload["field"] == "selected_option_id"
    assert "object at 0x" not in json.dumps(decisions.to_payload(), sort_keys=True)


def test_phase17k_datasheet_post_shoot_cover_denial_suppresses_save_cover() -> None:
    package = post_shoot_cover_denial_package()
    unit = named_weapon_choice_unit(package=package)
    target_unit_with_invulnerable = named_weapon_choice_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-lord-of-change-1",
    )
    target_model = replace(
        target_unit_with_invulnerable.own_models[0],
        characteristics=tuple(
            CharacteristicValue.from_raw(Characteristic.SAVE, 2)
            if characteristic.characteristic is Characteristic.SAVE
            else characteristic
            for characteristic in target_unit_with_invulnerable.own_models[0].characteristics
            if characteristic.characteristic is not Characteristic.INVULNERABLE_SAVE
        ),
    )
    target_unit = replace(target_unit_with_invulnerable, own_models=(target_model,))
    army = flesh_hounds_army(package=package, unit=unit)
    enemy_army = flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    player_index = player_ability_index(package=package, army=army)
    enemy_player_index = player_ability_index(package=package, army=enemy_army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    cover_record = records_by_name["Purge and Cleanse"]
    replay_payload = cast(dict[str, JsonValue], cover_record.definition.replay_payload)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    battlefield = flesh_hounds_battlefield_state(
        army=army,
        unit=unit,
        enemy_army=enemy_army,
        enemy_unit=target_unit,
        enemy_x=24.0,
    )
    state = battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    decisions = DecisionController()
    completed_sequence = completed_post_shoot_attack_sequence(
        package=package,
        attacker=unit,
        target=target_unit,
    )
    emit_successful_hit(
        decisions=decisions,
        attack_sequence=completed_sequence,
        successful=True,
    )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": completed_sequence.sequence_id,
            "attacker_player_id": army.player_id,
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    status = CatalogPostShootHitTargetStatusRuntime(
        ability_indexes_by_player_id={
            army.player_id: player_index,
            enemy_army.player_id: enemy_player_index,
        },
        armies=(army, enemy_army),
    ).request_handler(
        AttackSequenceCompletedContext(
            state=state,
            decisions=decisions,
            dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            source_phase=BattlePhase.SHOOTING,
            attack_sequence=completed_sequence,
            attack_sequence_completed_event_id=completed_event.event_id,
        )
    )
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = decisions.queue.peek_next()
    result = DecisionResult.for_request(
        result_id="phase17k-datasheet-cover-denial-save-consumer",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    decisions.submit_result(result)
    assert (
        apply_catalog_post_shoot_hit_target_status_result(
            state=state,
            decisions=decisions,
            result=result,
        )
        is None
    )
    denial_effects = state.persisting_effects_for_unit(target_unit.unit_instance_id)
    assert len(denial_effects) == 1
    denial_payload = cast(dict[str, JsonValue], denial_effects[0].effect_payload)
    assert denial_payload["effect_kind"] == CATALOG_POST_SHOOT_HIT_TARGET_STATUS_EFFECT_KIND
    assert denial_payload["benefit_of_cover_denied"] is True
    assert denial_payload["rule_ir_hash"] == rule_ir.ir_hash()

    state.record_persisting_effect(
        PersistingEffect(
            effect_id="phase17k-target-cover-grant",
            source_rule_id=SMOKESCREEN_EFFECT_KIND,
            owner_player_id=enemy_army.player_id,
            target_unit_instance_ids=(target_unit.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhase.SHOOTING,
            expiration=EffectExpiration.end_phase(
                battle_round=state.battle_round,
                phase=BattlePhase.SHOOTING,
                player_id=army.player_id,
            ),
            effect_payload=validate_json_value(
                {
                    "effect_kind": SMOKESCREEN_EFFECT_KIND,
                    "benefit_of_cover": True,
                }
            ),
        )
    )
    weapon_profile = replace(
        completed_sequence.attack_pools[0].weapon_profile,
        profile_id="phase17k-cover-denial-save-bolt",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -1),
        damage_profile=DamageProfile.fixed(1),
    )
    save_sequence_id = "phase17k-cover-denial-save-consumer"
    attack_context_id = f"{save_sequence_id}:pool-001:attack-001"
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id=army.player_id,
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id=army.player_id,
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id=enemy_army.player_id,
        allocated_model_id=target_model.model_instance_id,
        attack_context_id=attack_context_id,
    )
    base_ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    save_bonus_ruleset = replace(
        base_ruleset,
        terrain_visibility_policy=replace(
            base_ruleset.terrain_visibility_policy,
            cover_effect=CoverEffect.SAVE_BONUS,
            cover_policy=CoverPolicyDescriptor(cover_effect=CoverEffect.SAVE_BONUS),
        ),
        descriptor_hash="",
    )

    remaining_sequence, allocated_model_ids, resolve_status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=save_bonus_ruleset,
        attack_sequence=AttackSequence.start(
            sequence_id=save_sequence_id,
            attacker_player_id=army.player_id,
            attacking_unit_instance_id=unit.unit_instance_id,
            attack_pools=(
                replace(
                    completed_sequence.attack_pools[0],
                    weapon_profile_id=weapon_profile.profile_id,
                    weapon_profile=weapon_profile,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            save_sequence_id,
            event_log=decisions.event_log,
            injected_results=(
                DiceRollResult.from_values(
                    roll_id=f"{save_sequence_id}:hit",
                    spec=hit_spec,
                    values=(6,),
                    source="fixed",
                ),
                DiceRollResult.from_values(
                    roll_id=f"{save_sequence_id}:wound",
                    spec=wound_spec,
                    values=(6,),
                    source="fixed",
                ),
                DiceRollResult.from_values(
                    roll_id=f"{save_sequence_id}:save",
                    spec=save_spec,
                    values=(2,),
                    source="fixed",
                ),
            ),
        ),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    save_events = tuple(
        cast(dict[str, object], event.payload)
        for event in decisions.event_log.records
        if event.event_type == "attack_sequence_step"
        and cast(dict[str, object], event.payload).get("sequence_id") == save_sequence_id
        and cast(dict[str, object], event.payload).get("step") == AttackSequenceStep.SAVE.value
    )
    assert len(save_events) == 1
    save_payload = cast(dict[str, object], save_events[0]["payload"])
    save_option = cast(dict[str, object], save_payload["option"])

    assert remaining_sequence is None
    assert allocated_model_ids == (target_model.model_instance_id,)
    assert resolve_status is None
    assert save_payload["save_kind"] == SaveKind.ARMOUR.value
    assert save_payload["target_number"] == 2
    assert save_payload["unmodified_roll"] == 2
    assert save_payload["final_roll"] == 1
    assert save_payload["successful"] is False
    assert save_payload["resolution_rule"] == SaveResolutionRule.FAILED.value
    assert save_option["target_number"] == 3
    assert save_option["cover_result"] is None
    assert save_option["cover_applied"] is False
    assert save_option["source_rule_ids"] == []


def test_phase17k_post_shoot_hit_target_status_requires_successful_hit_not_wound() -> None:
    package = post_shoot_cover_denial_package()
    unit = named_weapon_choice_unit(package=package)
    target_unit = named_weapon_choice_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-lord-of-change-1",
    )
    army = flesh_hounds_army(package=package, unit=unit)
    enemy_army = flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    player_index = player_ability_index(package=package, army=army)
    enemy_player_index = player_ability_index(package=package, army=enemy_army)
    battlefield = flesh_hounds_battlefield_state(
        army=army,
        unit=unit,
        enemy_army=enemy_army,
        enemy_unit=target_unit,
        enemy_x=24.0,
    )
    state = battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    attack_sequence = completed_post_shoot_attack_sequence(
        package=package,
        attacker=unit,
        target=target_unit,
    )
    runtime = CatalogPostShootHitTargetStatusRuntime(
        ability_indexes_by_player_id={
            army.player_id: player_index,
            enemy_army.player_id: enemy_player_index,
        },
        armies=(army, enemy_army),
    )

    miss_decisions = DecisionController()
    emit_successful_hit(
        decisions=miss_decisions,
        attack_sequence=attack_sequence,
        successful=False,
    )
    miss_completed_event = miss_decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": army.player_id,
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    miss_context = AttackSequenceCompletedContext(
        state=state,
        decisions=miss_decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=miss_decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=attack_sequence,
        attack_sequence_completed_event_id=miss_completed_event.event_id,
    )

    assert (
        successful_hit_target_unit_ids_for_sequence(
            decisions=miss_decisions,
            sequence=attack_sequence,
        )
        == ()
    )
    assert (
        _available_catalog_post_shoot_hit_target_status_groups(
            ability_indexes_by_player_id={army.player_id: player_index},
            armies=(army, enemy_army),
            context=miss_context,
        )
        == ()
    )
    assert runtime.request_handler(miss_context) is None
    assert miss_decisions.queue.pending_requests == ()

    failed_wound_decisions = DecisionController()
    emit_successful_hit(
        decisions=failed_wound_decisions,
        attack_sequence=attack_sequence,
        successful=True,
    )
    emit_wound_result(
        decisions=failed_wound_decisions,
        attack_sequence=attack_sequence,
        successful=False,
    )
    failed_wound_completed_event = failed_wound_decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": army.player_id,
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    failed_wound_context = AttackSequenceCompletedContext(
        state=state,
        decisions=failed_wound_decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=failed_wound_decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=attack_sequence,
        attack_sequence_completed_event_id=failed_wound_completed_event.event_id,
    )
    failed_wound_groups = _available_catalog_post_shoot_hit_target_status_groups(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army, enemy_army),
        context=failed_wound_context,
    )
    failed_wound_status = runtime.request_handler(failed_wound_context)

    assert successful_hit_target_unit_ids_for_sequence(
        decisions=failed_wound_decisions,
        sequence=attack_sequence,
    ) == (target_unit.unit_instance_id,)
    assert len(failed_wound_groups) == 1
    assert failed_wound_status is not None
    assert failed_wound_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert failed_wound_decisions.queue.peek_next().decision_type == (
        SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE
    )


def test_phase17k_post_shoot_hit_target_status_processes_all_source_groups() -> None:
    package = post_shoot_cover_denial_package()
    unit = named_weapon_choice_unit(package=package, model_count=2)
    target_unit = named_weapon_choice_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-lord-of-change-1",
    )
    army = flesh_hounds_army(package=package, unit=unit)
    enemy_army = flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    player_index = player_ability_index(package=package, army=army)
    enemy_player_index = player_ability_index(package=package, army=enemy_army)
    battlefield = flesh_hounds_battlefield_state(
        army=army,
        unit=unit,
        enemy_army=enemy_army,
        enemy_unit=target_unit,
        enemy_x=24.0,
    )
    state = battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    decisions = DecisionController()
    attacker_model_ids = tuple(sorted(model.model_instance_id for model in unit.own_models))
    attack_sequence = completed_post_shoot_attack_sequence(
        package=package,
        attacker=unit,
        target=target_unit,
        attacker_model_instance_ids=attacker_model_ids,
    )
    for pool_index in range(len(attack_sequence.attack_pools)):
        emit_successful_hit(
            decisions=decisions,
            attack_sequence=attack_sequence,
            successful=True,
            pool_index=pool_index,
        )
    decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": army.player_id,
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id=army.player_id,
        shot_unit_ids=(unit.unit_instance_id,),
        attack_pools=attack_sequence.attack_pools,
        pending_completed_attack_sequence=attack_sequence,
    )
    handler = ShootingPhaseHandler(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=package.army_catalog,
        stratagem_index=StratagemCatalogIndex.from_records(()),
        attack_sequence_completed_hooks=AttackSequenceCompletedHookRegistry.from_bindings(
            CatalogPostShootHitTargetStatusRuntime(
                ability_indexes_by_player_id={
                    army.player_id: player_index,
                    enemy_army.player_id: enemy_player_index,
                },
                armies=(army, enemy_army),
            ).bindings()
        ),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    first_status = handler.begin_phase(state=state, decisions=decisions)
    assert first_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    first_request = decisions.queue.peek_next()
    first_payload = cast(dict[str, JsonValue], first_request.payload)
    assert first_payload["source_model_instance_id"] == attacker_model_ids[0]
    assert pending_completed_attack_sequence_for_test(state) == attack_sequence

    first_result = DecisionResult.for_request(
        result_id="phase17k-post-shoot-cover-denial-source-001",
        request=first_request,
        selected_option_id=first_request.options[0].option_id,
    )
    decisions.submit_result(first_result)
    assert handler.apply_decision(state=state, result=first_result, decisions=decisions) is None

    second_status = handler.begin_phase(state=state, decisions=decisions)
    assert second_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    second_request = decisions.queue.peek_next()
    second_payload = cast(dict[str, JsonValue], second_request.payload)
    assert second_request.request_id != first_request.request_id
    assert second_request.decision_type == SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE
    assert second_payload["source_model_instance_id"] == attacker_model_ids[1]
    assert pending_completed_attack_sequence_for_test(state) == attack_sequence

    second_result = DecisionResult.for_request(
        result_id="phase17k-post-shoot-cover-denial-source-002",
        request=second_request,
        selected_option_id=second_request.options[0].option_id,
    )
    decisions.submit_result(second_result)
    assert handler.apply_decision(state=state, result=second_result, decisions=decisions) is None

    completion_status = handler.begin_phase(state=state, decisions=decisions)
    assert completion_status.status_kind is LifecycleStatusKind.ADVANCED
    assert pending_completed_attack_sequence_for_test(state) is None
    selected_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_POST_SHOOT_HIT_TARGET_STATUS_SELECTED_EVENT
    )
    requested_events = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "catalog_post_shoot_hit_target_status_requested"
    )
    effects = state.persisting_effects_for_unit(target_unit.unit_instance_id)

    assert len(requested_events) == 2
    assert len(selected_events) == 2
    assert [
        cast(dict[str, JsonValue], event.payload)["source_model_instance_id"]
        for event in selected_events
    ] == list(attacker_model_ids)
    assert len(effects) == 2
    assert all(
        cast(dict[str, JsonValue], effect.effect_payload)["effect_kind"]
        == CATALOG_POST_SHOOT_HIT_TARGET_STATUS_EFFECT_KIND
        for effect in effects
    )
    assert "object at 0x" not in json.dumps(decisions.to_payload(), sort_keys=True)


def test_phase17k_post_shoot_hit_target_status_uses_runtime_clause_scoped_records() -> None:
    package = post_shoot_cover_denial_package()
    unit = named_weapon_choice_unit(package=package)
    target_unit = named_weapon_choice_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-lord-of-change-1",
    )
    army = flesh_hounds_army(package=package, unit=unit)
    enemy_army = flesh_hounds_army(
        package=package,
        unit=target_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    rule_ir = multi_clause_post_shoot_cover_denial_rule_ir()
    clause_001_record = multi_clause_post_shoot_cover_denial_record(
        rule_ir=rule_ir,
        clause_index=0,
        datasheet_id=unit.datasheet_id,
        trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
    )
    clause_002_record = multi_clause_post_shoot_cover_denial_record(
        rule_ir=rule_ir,
        clause_index=1,
        datasheet_id=unit.datasheet_id,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
    )
    ability_index = AbilityCatalogIndex.from_records((clause_001_record, clause_002_record))
    enemy_ability_index = AbilityCatalogIndex.from_records(())
    battlefield = flesh_hounds_battlefield_state(
        army=army,
        unit=unit,
        enemy_army=enemy_army,
        enemy_unit=target_unit,
        enemy_x=24.0,
    )
    state = battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=battlefield,
        active_player_id=army.player_id,
        phase=BattlePhase.SHOOTING,
    )
    decisions = DecisionController()
    attack_sequence = completed_post_shoot_attack_sequence(
        package=package,
        attacker=unit,
        attacker_player_id=army.player_id,
        target=target_unit,
    )
    emit_successful_hit(
        decisions=decisions,
        attack_sequence=attack_sequence,
        successful=True,
    )
    completed_event = decisions.event_log.append(
        "attack_sequence_completed",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacker_player_id": army.player_id,
            "attacking_unit_instance_id": unit.unit_instance_id,
        },
    )
    context = AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=attack_sequence,
        attack_sequence_completed_event_id=completed_event.event_id,
    )

    groups = _available_catalog_post_shoot_hit_target_status_groups(
        ability_indexes_by_player_id={army.player_id: ability_index},
        armies=(army, enemy_army),
        context=context,
    )
    status = CatalogPostShootHitTargetStatusRuntime(
        ability_indexes_by_player_id={
            army.player_id: ability_index,
            enemy_army.player_id: enemy_ability_index,
        },
        armies=(army, enemy_army),
    ).request_handler(context)

    assert not _record_can_select_catalog_post_shoot_hit_target_status(clause_001_record)
    assert _record_can_select_catalog_post_shoot_hit_target_status(clause_002_record)
    assert len(groups) == 1
    assert groups[0].record.record_id == clause_002_record.record_id
    assert groups[0].clause.clause_id == rule_ir.clauses[1].clause_id
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = decisions.queue.peek_next()
    assert request is not None
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["catalog_record_id"] == clause_002_record.record_id
    assert len(request.options) == 1
