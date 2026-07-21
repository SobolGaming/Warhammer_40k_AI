# pyright: reportPrivateUsage=false
from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from tests.support.catalog_package_fixtures import (
    advance_charge_package,
    advance_charge_unit,
    flesh_hounds_army,
    flesh_hounds_package,
    flesh_hounds_unit,
    model_reroll_package,
    split_fall_back_package,
    split_model_reroll_package,
)
from tests.support.catalog_runtime_fixtures import (
    battle_state_with_armies,
    battle_state_with_army,
    bloodcrushers_battlefield_state,
    flesh_hounds_battlefield_state,
    player_ability_index,
    record_by_runtime_clause_suffix,
    single_model_unit_placement,
)
from tests.support.catalog_runtime_fixtures import (
    current_model_ids as fixture_current_model_ids,
)

from warhammer40k_core.core.dice import RerollComponentSelectionPolicy
from warhammer40k_core.core.weapon_profiles import (
    AbilityKind,
    RangeProfile,
    WeaponKeyword,
)
from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.advance_eligibility_hooks import (
    AdvanceEligibilityContext,
    AdvanceEligibilityHookRegistry,
)
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
    CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
    CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
    CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
    CatalogAdvanceEligibilityRuntime,
    CatalogFallBackEligibilityRuntime,
    _catalog_roll_reroll_permission,
    catalog_advance_roll_reroll_permission_for_unit,
    catalog_charge_roll_reroll_permission_for_unit,
    catalog_rule_ir_consumers_for_rule,
    catalog_rule_ir_hook_ids_for_rule,
    catalog_weapon_keyword_grants_for_unit,
    catalog_weapon_profile_modifier_bindings,
)
from warhammer40k_core.engine.catalog_turn_end_reserves import (
    CATALOG_TURN_END_RESERVES_USED_EVENT,
    CatalogTurnEndReserveRuntime,
)
from warhammer40k_core.engine.charge_roll_permissions import charge_reroll_permission_for_unit
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.fall_back_hooks import (
    FallBackEligibilityContext,
    FallBackEligibilityHookRegistry,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
)
from warhammer40k_core.engine.phases.movement import _advance_reroll_permission_for_unit
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndHookRegistry,
    TurnEndRequestContext,
    TurnEndResultContext,
)
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleIR,
    RuleIRPayload,
    RuleTargetKind,
)


def test_phase17k_flesh_hounds_hunters_from_the_warp_uses_generic_turn_end_reserves() -> None:
    package = flesh_hounds_package()
    unit = flesh_hounds_unit(package=package)
    enemy_unit = flesh_hounds_unit(
        package=package,
        army_id="army-opponent",
        unit_selection_id="enemy-flesh-hounds-1",
    )
    army = flesh_hounds_army(package=package, unit=unit)
    enemy_army = flesh_hounds_army(
        package=package,
        unit=enemy_unit,
        army_id="army-opponent",
        player_id="player-opponent",
    )
    player_index = player_ability_index(package=package, army=army)
    enemy_index = player_ability_index(package=package, army=enemy_army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    hunters_record = records_by_name["Hunters from the Warp"]
    replay_payload = hunters_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    hunters_rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    runtime = CatalogTurnEndReserveRuntime(
        ability_indexes_by_player_id={
            army.player_id: player_index,
            enemy_army.player_id: enemy_index,
        },
        armies=(army, enemy_army),
    )
    registry = TurnEndHookRegistry.from_bindings(runtime.bindings())
    engaged_state = battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=flesh_hounds_battlefield_state(
            army=army,
            unit=unit,
            enemy_army=enemy_army,
            enemy_unit=enemy_unit,
            enemy_x=12.0,
        ),
        active_player_id=enemy_army.player_id,
        phase=BattlePhase.FIGHT,
    )

    assert hunters_record.definition.timing.trigger_kind is TimingTriggerKind.END_TURN
    assert catalog_rule_ir_consumers_for_rule(hunters_rule_ir) == (
        CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(hunters_rule_ir)) == {
        CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
    }
    assert (
        registry.next_request_for(
            TurnEndRequestContext(
                state=engaged_state,
                decisions=DecisionController(),
                completed_phase=BattlePhase.FIGHT,
            )
        )
        is None
    )

    state = battle_state_with_armies(
        armies=(army, enemy_army),
        battlefield=flesh_hounds_battlefield_state(
            army=army,
            unit=unit,
            enemy_army=enemy_army,
            enemy_unit=enemy_unit,
            enemy_x=30.0,
        ),
        active_player_id=enemy_army.player_id,
        phase=BattlePhase.FIGHT,
    )
    decisions = DecisionController()
    request = registry.next_request_for(
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.FIGHT,
        )
    )
    assert request is not None
    use_option = next(option for option in request.options if option.option_id.endswith(":use"))
    result = DecisionResult.for_request(
        result_id="result-flesh-hounds-hunters-use",
        request=request,
        selected_option_id=use_option.option_id,
    )

    handled = registry.apply_result(
        TurnEndResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    )

    reserve_state = state.reserve_state_for_unit(unit.unit_instance_id)
    assert request.decision_type == SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
    assert request.actor_id == army.player_id
    assert handled is True
    assert reserve_state is not None
    assert reserve_state.source_rule_ids == (hunters_record.definition.source_id,)
    assert state.battlefield_state is not None
    assert all(
        unit_placement.unit_instance_id != unit.unit_instance_id
        for placed_army in state.battlefield_state.placed_armies
        for unit_placement in placed_army.unit_placements
    )
    used_events = tuple(
        record
        for record in decisions.event_log.records
        if record.event_type == CATALOG_TURN_END_RESERVES_USED_EVENT
    )
    assert len(used_events) == 1


def test_phase17k_datasheet_advance_charge_text_uses_generic_advance_eligibility() -> None:
    package = advance_charge_package()
    unit = advance_charge_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    advance_charge_record = records_by_name["Bounding Advance"]
    replay_payload = advance_charge_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    runtime = CatalogAdvanceEligibilityRuntime(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    registry = AdvanceEligibilityHookRegistry.from_bindings(runtime.bindings())
    state = battle_state_with_army(
        army=army,
        battlefield=bloodcrushers_battlefield_state(army=army, unit=unit),
    )

    grants = registry.grants_for(
        AdvanceEligibilityContext(
            state=state,
            player_id=army.player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            movement_request_id="phase17k-advance-charge-request",
            movement_result_id="phase17k-advance-charge-result",
        )
    )

    assert advance_charge_record.definition.timing.trigger_kind is TimingTriggerKind.PASSIVE_QUERY
    assert rule_ir.is_supported
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
    }
    assert tuple(binding.hook_id for binding in registry.all_bindings()) == (
        CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID,
    )
    assert len(grants) == 1
    assert grants[0].hook_id == CATALOG_IR_CAN_ADVANCE_AND_CHARGE_CONSUMER_ID
    assert grants[0].can_declare_charge is True
    assert grants[0].can_shoot is False
    assert grants[0].replay_payload == {
        "ability": "can_advance_and_charge",
        "ability_ids": [advance_charge_record.definition.ability_id],
        "catalog_record_ids": [advance_charge_record.record_id],
        "source_rule_ids": [advance_charge_record.definition.source_id],
    }


def test_phase17k_datasheet_fall_back_shoot_text_uses_generic_fall_back_eligibility() -> None:
    package = advance_charge_package()
    unit = advance_charge_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    fall_back_shoot_record = records_by_name["Slip Away"]
    replay_payload = fall_back_shoot_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    runtime = CatalogFallBackEligibilityRuntime(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    registry = FallBackEligibilityHookRegistry.from_bindings(runtime.bindings())
    state = battle_state_with_army(
        army=army,
        battlefield=bloodcrushers_battlefield_state(army=army, unit=unit),
    )

    grants = registry.grants_for(
        FallBackEligibilityContext(
            state=state,
            player_id=army.player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            movement_request_id="phase17k-fall-back-shoot-request",
            movement_result_id="phase17k-fall-back-shoot-result",
        )
    )

    assert fall_back_shoot_record.definition.timing.trigger_kind is TimingTriggerKind.PASSIVE_QUERY
    assert rule_ir.is_supported
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
    }
    assert tuple(binding.hook_id for binding in registry.all_bindings()) == (
        CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID,
    )
    assert len(grants) == 1
    assert grants[0].hook_id == CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID
    assert grants[0].can_shoot is True
    assert grants[0].can_declare_charge is False
    assert grants[0].replay_payload == {
        "ability": "can_fall_back_and_shoot",
        "ability_ids": [fall_back_shoot_record.definition.ability_id],
        "catalog_record_ids": [fall_back_shoot_record.record_id],
        "source_rule_ids": [fall_back_shoot_record.definition.source_id],
    }


def test_phase17k_fall_back_shoot_runtime_uses_scoped_catalog_clause_record() -> None:
    package = split_fall_back_package()
    unit = advance_charge_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    split_records = tuple(
        record
        for record in player_index.all_records()
        if record.definition.name == "Split Slip Away"
    )
    unrelated_record = record_by_runtime_clause_suffix(split_records, suffix=":clause:001")
    fall_back_record = record_by_runtime_clause_suffix(split_records, suffix=":clause:002")
    runtime = CatalogFallBackEligibilityRuntime(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    registry = FallBackEligibilityHookRegistry.from_bindings(runtime.bindings())
    state = battle_state_with_army(
        army=army,
        battlefield=bloodcrushers_battlefield_state(army=army, unit=unit),
    )

    grants = registry.grants_for(
        FallBackEligibilityContext(
            state=state,
            player_id=army.player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
            movement_request_id="phase17k-split-fall-back-shoot-request",
            movement_result_id="phase17k-split-fall-back-shoot-result",
        )
    )

    assert len(split_records) == 2
    assert unrelated_record.definition.timing.trigger_kind is TimingTriggerKind.PASSIVE_QUERY
    assert fall_back_record.definition.timing.trigger_kind is TimingTriggerKind.PASSIVE_QUERY
    assert len(grants) == 1
    assert grants[0].hook_id == CATALOG_IR_CAN_FALLBACK_AND_SHOOT_CONSUMER_ID
    grant_payload = grants[0].replay_payload
    assert isinstance(grant_payload, dict)
    catalog_record_ids = grant_payload["catalog_record_ids"]
    assert isinstance(catalog_record_ids, list)
    assert catalog_record_ids == [fall_back_record.record_id]
    assert unrelated_record.record_id not in catalog_record_ids


def test_phase17k_leading_model_reroll_text_uses_generic_advance_charge_rerolls() -> None:
    package = advance_charge_package()
    unit = advance_charge_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    reroll_record = records_by_name["Lead the Hunt"]
    replay_payload = reroll_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    battlefield = bloodcrushers_battlefield_state(army=army, unit=unit)
    state = battle_state_with_army(army=army, battlefield=battlefield)
    current_model_ids = fixture_current_model_ids(battlefield=battlefield, unit=unit)
    advance_permission = catalog_advance_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )
    charge_permission = catalog_charge_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )
    advance_phase_permission = _advance_reroll_permission_for_unit(
        state=state,
        unit=unit,
        unit_instance_id=unit.unit_instance_id,
        player_id=army.player_id,
        keywords=unit.keywords,
        ability_index=player_index,
        current_model_instance_ids=current_model_ids,
    )
    charge_phase_permission = charge_reroll_permission_for_unit(
        state=state,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        ability_index=player_index,
    )
    keyword_permission = _advance_reroll_permission_for_unit(
        state=state,
        unit=unit,
        unit_instance_id=unit.unit_instance_id,
        player_id=army.player_id,
        keywords=("ADVANCE_REROLL",),
        ability_index=AbilityCatalogIndex.from_records(()),
        current_model_instance_ids=(),
    )
    empty_index = AbilityCatalogIndex.from_records(())
    duplicate_index = AbilityCatalogIndex.from_records(
        (
            *player_index.all_records(),
            replace(reroll_record, record_id=f"{reroll_record.record_id}:duplicate"),
        )
    )

    assert reroll_record.definition.timing.trigger_kind is TimingTriggerKind.AFTER_DICE_ROLL
    assert rule_ir.is_supported
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    }
    assert advance_permission is not None
    assert advance_permission.eligible_roll_type == "advance_roll"
    assert advance_permission.timing_window == "after_advance_roll"
    assert advance_permission.owning_player_id == army.player_id
    assert (
        advance_permission.component_selection_policy is RerollComponentSelectionPolicy.WHOLE_ROLL
    )
    assert charge_permission is not None
    assert charge_permission.eligible_roll_type == "charge_roll"
    assert charge_permission.timing_window == "after_charge_roll"
    assert charge_permission.owning_player_id == army.player_id
    assert charge_permission.component_selection_policy is RerollComponentSelectionPolicy.WHOLE_ROLL
    assert advance_phase_permission == advance_permission
    assert charge_phase_permission == charge_permission
    assert keyword_permission is not None
    assert keyword_permission.source_id == f"{unit.unit_instance_id}:advance-reroll"
    assert keyword_permission.eligible_roll_type == "advance_roll"
    assert (
        catalog_advance_roll_reroll_permission_for_unit(
            ability_index=empty_index,
            unit=unit,
            current_model_instance_ids=current_model_ids,
            player_id=army.player_id,
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="Multiple catalog roll reroll permissions"):
        catalog_advance_roll_reroll_permission_for_unit(
            ability_index=duplicate_index,
            unit=unit,
            current_model_instance_ids=current_model_ids,
            player_id=army.player_id,
        )
    with pytest.raises(GameLifecycleError, match="requires an ability record"):
        _catalog_roll_reroll_permission(
            record=cast(AbilityCatalogRecord, object()),
            clause=rule_ir.clauses[0],
            effect_index=0,
            player_id=army.player_id,
            roll_type="advance_roll",
            timing_window="after_advance_roll",
        )
    with pytest.raises(GameLifecycleError, match="requires a rule clause"):
        _catalog_roll_reroll_permission(
            record=reroll_record,
            clause=cast(RuleClause, object()),
            effect_index=0,
            player_id=army.player_id,
            roll_type="advance_roll",
            timing_window="after_advance_roll",
        )
    with pytest.raises(GameLifecycleError, match="effect_index must be non-negative"):
        _catalog_roll_reroll_permission(
            record=reroll_record,
            clause=rule_ir.clauses[0],
            effect_index=-1,
            player_id=army.player_id,
            roll_type="advance_roll",
            timing_window="after_advance_roll",
        )


def test_phase17k_this_model_reroll_text_uses_generic_advance_charge_rerolls() -> None:
    package = model_reroll_package()
    unit = advance_charge_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    reroll_record = records_by_name["Swift Instincts"]
    replay_payload = reroll_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    battlefield = bloodcrushers_battlefield_state(army=army, unit=unit)
    current_model_ids = fixture_current_model_ids(battlefield=battlefield, unit=unit)
    advance_permission = catalog_advance_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )
    charge_permission = catalog_charge_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )
    clause = rule_ir.clauses[0]

    assert reroll_record.definition.timing.trigger_kind is TimingTriggerKind.AFTER_DICE_ROLL
    assert rule_ir.is_supported
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_MODEL
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_ADVANCE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_CHARGE_ROLL_REROLL_CONSUMER_ID,
    }
    assert advance_permission is not None
    assert advance_permission.eligible_roll_type == "advance_roll"
    assert advance_permission.timing_window == "after_advance_roll"
    assert advance_permission.owning_player_id == army.player_id
    assert (
        advance_permission.component_selection_policy is RerollComponentSelectionPolicy.WHOLE_ROLL
    )
    assert charge_permission is not None
    assert charge_permission.eligible_roll_type == "charge_roll"
    assert charge_permission.timing_window == "after_charge_roll"
    assert charge_permission.owning_player_id == army.player_id
    assert charge_permission.component_selection_policy is RerollComponentSelectionPolicy.WHOLE_ROLL


def test_phase17k_model_reroll_runtime_uses_scoped_catalog_clause_record() -> None:
    package = split_model_reroll_package()
    unit = advance_charge_unit(package=package)
    army = flesh_hounds_army(package=package, unit=unit)
    player_index = player_ability_index(package=package, army=army)
    split_records = tuple(
        record
        for record in player_index.all_records()
        if record.definition.name == "Split Swift Instincts"
    )
    unrelated_record = record_by_runtime_clause_suffix(split_records, suffix=":clause:001")
    reroll_record = record_by_runtime_clause_suffix(split_records, suffix=":clause:002")
    battlefield = bloodcrushers_battlefield_state(army=army, unit=unit)
    current_model_ids = fixture_current_model_ids(battlefield=battlefield, unit=unit)

    advance_permission = catalog_advance_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )
    charge_permission = catalog_charge_roll_reroll_permission_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
        player_id=army.player_id,
    )

    assert len(split_records) == 2
    assert unrelated_record.definition.timing.trigger_kind is TimingTriggerKind.AFTER_DICE_ROLL
    assert reroll_record.definition.timing.trigger_kind is TimingTriggerKind.AFTER_DICE_ROLL
    assert advance_permission is not None
    assert advance_permission.eligible_roll_type == "advance_roll"
    assert advance_permission.source_id.startswith(f"{reroll_record.record_id}:")
    assert not advance_permission.source_id.startswith(f"{unrelated_record.record_id}:")
    assert charge_permission is not None
    assert charge_permission.eligible_roll_type == "charge_roll"
    assert charge_permission.source_id.startswith(f"{reroll_record.record_id}:")
    assert not charge_permission.source_id.startswith(f"{unrelated_record.record_id}:")


def test_phase17k_leading_model_weapon_keyword_text_modifies_scoped_weapon_profiles() -> None:
    package = advance_charge_package()
    unit = advance_charge_unit(package=package)
    bodyguard = advance_charge_unit(
        package=package,
        unit_selection_id="advance-charge-bodyguard-1",
    )
    attached_id = "attached-unit:army-daemons:advance-charge-test"
    formation = AttachedUnitFormation(
        attached_unit_instance_id=attached_id,
        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
        leader_unit_instance_ids=(unit.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((bodyguard.unit_instance_id, unit.unit_instance_id))
        ),
        source_id="test:phase17k:leading-weapon-grant",
        attachment_source_ids=("test:phase17k:leading-weapon-grant:eligibility",),
    )
    army = replace(
        flesh_hounds_army(package=package, unit=unit),
        units=(unit, bodyguard),
        attached_units=(formation,),
    )
    player_index = player_ability_index(package=package, army=army)
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    weapon_grant_record = records_by_name["Pack Killers"]
    replay_payload = weapon_grant_record.definition.replay_payload
    assert isinstance(replay_payload, dict)
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, replay_payload["rule_ir"]))
    battlefield = bloodcrushers_battlefield_state(army=army, unit=unit)
    placed_army = battlefield.placed_armies[0]
    battlefield = replace(
        battlefield,
        placed_armies=(
            replace(
                placed_army,
                unit_placements=(
                    *placed_army.unit_placements,
                    single_model_unit_placement(army, bodyguard, x=14.0),
                ),
            ),
        ),
    )
    state = battle_state_with_army(army=army, battlefield=battlefield)
    current_model_ids = fixture_current_model_ids(battlefield=battlefield, unit=unit)
    swift_claws = next(
        wargear
        for wargear in package.army_catalog.wargear
        if wargear.wargear_id == "test-advance-charge-unit:swift-claws"
    )
    melee_profile = swift_claws.weapon_profiles[0]
    ranged_profile = replace(
        melee_profile,
        profile_id=f"{melee_profile.profile_id}:ranged-copy",
        range_profile=RangeProfile.distance(12),
    )
    grants = catalog_weapon_keyword_grants_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=current_model_ids,
    )
    bindings = catalog_weapon_profile_modifier_bindings(
        ability_indexes_by_player_id={army.player_id: player_index},
        armies=(army,),
    )
    registry = RuntimeModifierRegistry.from_bindings(
        weapon_profile_modifier_bindings=bindings,
    )
    attacker_model_id = unit.own_models[0].model_instance_id
    melee_context = WeaponProfileModifierContext(
        state=state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id=attached_id,
        attacker_model_instance_id=attacker_model_id,
        target_unit_instance_id=attached_id,
        weapon_profile=melee_profile,
    )
    ranged_context = replace(melee_context, weapon_profile=ranged_profile)
    modified_melee = registry.modified_weapon_profile(melee_context)
    modified_ranged = registry.modified_weapon_profile(ranged_context)

    assert weapon_grant_record.definition.timing.trigger_kind is TimingTriggerKind.PASSIVE_QUERY
    assert rule_ir.is_supported
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        "catalog-ir:weapon-keyword-grant:lethal-hits",
    )
    assert set(catalog_rule_ir_hook_ids_for_rule(rule_ir)) == {
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        "catalog-ir:weapon-keyword-grant:lethal-hits",
    }
    assert tuple(binding.modifier_id for binding in bindings) == (
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
    )
    assert len(grants) == 1
    assert grants[0].keyword is WeaponKeyword.LETHAL_HITS
    assert grants[0].weapon_scope == "melee"
    assert grants[0].ability is not None
    assert grants[0].ability.ability_kind is AbilityKind.LETHAL_HITS
    assert WeaponKeyword.LETHAL_HITS in modified_melee.keywords
    assert any(
        ability.ability_kind is AbilityKind.LETHAL_HITS for ability in modified_melee.abilities
    )
    assert grants[0].source_id in modified_melee.source_ids
    assert modified_ranged == ranged_profile
