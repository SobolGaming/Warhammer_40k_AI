from __future__ import annotations

from tests.shared.category_migration.ws14_generic_ir_lifecycle import (
    _COURT_ENHANCEMENT_EXECUTION_IDS,
    _COURT_GENERIC_EXECUTION_IDS,
    _MORE_DAKKA_ENHANCEMENT_EXECUTION_IDS,
    _MORE_DAKKA_GENERIC_EXECUTION_IDS,
    _SPECTACLE_ENHANCEMENT_EXECUTION_IDS,
    _SPECTACLE_GENERIC_EXECUTION_IDS,
    CHARGE_FIGHTS_FIRST_EFFECT_KIND,
    DESTROYED_TARGET_UNIT_CONTEXT_KEY,
    ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY,
    FALL_BACK_UNIT_CONTEXT_KEY,
    JUST_SHOT_UNIT_CONTEXT_KEY,
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
    STRATAGEM_DECISION_TYPE,
    AbilityKind,
    ArmyCatalog,
    ArmyMusterRequest,
    BattleFormationRequestContext,
    BattlePhase,
    BattlePhaseKind,
    Characteristic,
    CharacteristicValue,
    CommandPointGainStatus,
    CommandPointSourceKind,
    DatasheetKeywordSet,
    DecisionResult,
    DetachmentDefinition,
    DetachmentSelection,
    EffectExpiration,
    EnhancementAssignment,
    EnhancementDefinition,
    FactionDefinition,
    FactionRuleExecutionContext,
    FactionRuleExecutionResult,
    FactionRuleExecutionStatus,
    FightPhaseState,
    FightsFirstRegistry,
    GameConfig,
    GameLifecycle,
    GameLifecycleError,
    GameLifecycleStage,
    GameState,
    HitRollModifierContext,
    JsonValue,
    LifecycleStatus,
    LifecycleStatusKind,
    MissionSetup,
    ModelProfileSelection,
    MovementBudgetModifierContext,
    MovementCapabilitySet,
    MovementMode,
    ObjectiveControlModifierContext,
    PersistingEffect,
    Phase17FExecutionStatus,
    Pose,
    ReactionQueue,
    RulesetDescriptor,
    RuntimeContentBundle,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    SetupStep,
    ShootingPhaseState,
    ShootingTargetRestrictionContext,
    ShootingType,
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemUseRecord,
    TimingTriggerKind,
    UnitCharacteristicModifierContext,
    UnitMusterSelection,
    WeaponKeyword,
    WeaponProfile,
    WeaponProfileModifierContext,
    WoundRollModifierContext,
    _apply_battle_formation_hooks_from_bundle,
    _clear_terrain,
    _court_battle_lifecycle,
    _court_blade_profile,
    _court_catalog,
    _court_datasheet_id_for_selection,
    _court_lifecycle_config,
    _court_muster_request,
    _court_shoota_profile,
    _court_stratagem,
    _court_stratagem_decision_result,
    _court_weapon_profile_context,
    _effect_parameter,
    _first_model_id,
    _grant_cp,
    _json_object,
    _last_event_payload,
    _leader_blade_profile,
    _mission_setup,
    _mob_shoota_profile,
    _more_dakka_battle_lifecycle,
    _more_dakka_catalog,
    _more_dakka_lifecycle_config,
    _more_dakka_muster_request,
    _more_dakka_stratagem,
    _more_dakka_stratagem_decision_result,
    _option_stratagem_id,
    _option_target_unit_id,
    _place_units_for_court_within_12,
    _place_units_for_more_dakka_shooting,
    _prepare_battle_phase,
    _profile_has_ability,
    _record_charge_move_effect,
    _record_fixed_secondary_choices_for_fixture,
    _replace_unit_poses,
    _runtime_content_bundle,
    _set_current_battle_phase,
    _spectacle_battle_lifecycle,
    _spectacle_catalog,
    _spectacle_lifecycle_config,
    _spectacle_muster_request,
    _spectacle_stratagem,
    _spectacle_stratagem_decision_result,
    _spectacle_weapon_profile_context,
    _state,
    _use_court_stratagem,
    _use_court_stratagem_through_lifecycle,
    _use_more_dakka_stratagem,
    _use_more_dakka_stratagem_through_lifecycle,
    _use_spectacle_stratagem,
    _use_spectacle_stratagem_through_lifecycle,
    _weapon_profile_context,
    apply_stratagem_decision,
    chapter_approved_2026_27_mission_pack,
    charge_transit_through_non_vehicle_monster_models_allowed,
    court_ir,
    create_deterministic_battlefield_scenario,
    emperors_children_july,
    enter_battle_for_fixture,
    json,
    july_faction_packs_2026_07,
    movement_transit_through_terrain_features_allowed,
    muster_army,
    pytest,
    replace,
    request_stratagem_use_from_index,
    source_backed_reroll_permission_context_for_unit,
)


@pytest.mark.integration
def test_ws14_more_dakka_generic_ir_rows_execute_from_lifecycle_runtime_bundle() -> None:
    config = _more_dakka_lifecycle_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.advance_until_decision_or_terminal()

    bundle = _runtime_content_bundle(lifecycle)

    assert "orks" in bundle.activation.selected_faction_ids
    assert "more-dakka" in bundle.activation.selected_detachment_ids
    assert set(_MORE_DAKKA_GENERIC_EXECUTION_IDS).issubset(
        bundle.activation.selected_execution_record_ids
    )

    context = FactionRuleExecutionContext(
        game_id=config.game_id,
        player_id="player-a",
        battle_round=1,
        phase=BattlePhaseKind.SHOOTING,
        active_player_id="player-a",
        source_unit_instance_id="army-alpha:boyz-1",
        trigger_payload={"event": "ws14-more-dakka-generic-ir-demo"},
    )
    results = tuple(
        bundle.faction_rule_execution_registry.execute(
            execution_id=execution_id,
            context=context,
        )
        for execution_id in _MORE_DAKKA_ENHANCEMENT_EXECUTION_IDS
    )

    assert tuple(result.status for result in results) == (
        FactionRuleExecutionStatus.APPLIED,
        FactionRuleExecutionStatus.APPLIED,
        FactionRuleExecutionStatus.APPLIED,
        FactionRuleExecutionStatus.APPLIED,
    )
    for result in results:
        record = bundle.faction_rule_execution_registry.record_by_execution_id(result.execution_id)
        assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
        assert record.rule_ir_hash is not None
        assert FactionRuleExecutionResult.from_payload(result.to_payload()) == result
        replay_payload = _json_object(result.replay_payload)
        rule_result_payload = _json_object(replay_payload["generic_rule_execution_result"])
        assert rule_result_payload["status"] == "applied"

    payload = lifecycle.to_payload()
    rebuilt = GameLifecycle.from_payload(payload)

    assert _runtime_content_bundle(rebuilt).to_summary_payload() == bundle.to_summary_payload()
    assert "object at 0x" not in json.dumps(payload, sort_keys=True)


@pytest.mark.integration
def test_ws14_more_dakka_generic_enhancement_ir_binds_to_assigned_bearer() -> None:
    lifecycle = _more_dakka_battle_lifecycle()
    state = _state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)

    assignment_payloads = [
        assignment.to_payload()
        for assignment in bundle.activation.selected_enhancement_assignments
        if assignment.player_id == "player-a"
    ]
    assert assignment_payloads == [
        {
            "bearer_model_instance_id": "army-alpha:boyz-1:core-boyz-like:001",
            "assignment_id": "army-alpha:000009991004:boyz-1",
            "player_id": "player-a",
            "army_id": "army-alpha",
            "enhancement_id": "000009991004",
            "target_unit_selection_id": "boyz-1",
            "bearer_unit_instance_id": "army-alpha:boyz-1",
            "source_id": "ws14-more-dakka:assignment:boyz-1:000009991004",
        }
    ]

    bearer_effects = tuple(state.persisting_effects_for_unit("army-alpha:boyz-1"))
    generic_hit_effects = tuple(
        effect
        for effect in bearer_effects
        if _json_object(effect.effect_payload).get("execution_id")
        == "phase17f:phase17e:enhancement:orks:more-dakka:000009991004"
    )
    assert len(generic_hit_effects) == 1
    effect_payload = _json_object(generic_hit_effects[0].effect_payload)
    assert effect_payload["effect_kind"] == "generic_rule_execution"
    assert effect_payload["target_unit_instance_ids"] == ["army-alpha:boyz-1"]
    effect = _json_object(effect_payload["effect"])
    assert effect["kind"] == "modify_dice_roll"
    assignment = _json_object(effect_payload["enhancement_assignment"])
    assert assignment["bearer_unit_instance_id"] == "army-alpha:boyz-1"

    weapon_profile = next(
        wargear
        for wargear in _more_dakka_catalog().wargear
        if wargear.wargear_id == "core-mob-shoota"
    ).weapon_profiles[0]
    model_instance_id = state.army_definitions[0].units[0].own_models[0].model_instance_id
    assert (
        bundle.runtime_modifier_registry.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id="army-alpha:boyz-1",
                attacker_model_instance_id=model_instance_id,
                target_unit_instance_id="army-beta:boyz-2",
                weapon_profile=weapon_profile,
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == 1
    )
    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()
    assert "object at 0x" not in json.dumps(lifecycle.to_payload(), sort_keys=True)


__all__: list[str] = []
__all__ += ["AbilityKind", "ArmyCatalog", "ArmyMusterRequest", "BattleFormationRequestContext"]
__all__ += ["CHARGE_FIGHTS_FIRST_EFFECT_KIND", "Characteristic", "CharacteristicValue"]
__all__ += ["CommandPointGainStatus", "CommandPointSourceKind"]
__all__ += ["DESTROYED_TARGET_UNIT_CONTEXT_KEY", "DatasheetKeywordSet", "DecisionResult"]
__all__ += ["ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY", "DetachmentDefinition", "DetachmentSelection"]
__all__ += ["EffectExpiration", "EnhancementAssignment", "EnhancementDefinition"]
__all__ += ["FALL_BACK_UNIT_CONTEXT_KEY", "FactionDefinition", "FightPhaseState"]
__all__ += ["FightsFirstRegistry", "GameConfig", "GameLifecycleError", "GameLifecycleStage"]
__all__ += ["JUST_SHOT_UNIT_CONTEXT_KEY", "GameState", "JsonValue", "LifecycleStatus"]
__all__ += ["LifecycleStatusKind", "MissionSetup", "ModelProfileSelection"]
__all__ += ["MovementBudgetModifierContext", "MovementCapabilitySet", "MovementMode"]
__all__ += ["ObjectiveControlModifierContext", "PersistingEffect", "Pose", "ReactionQueue"]
__all__ += ["RulesetDescriptor", "RuntimeContentBundle"]
__all__ += ["SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE"]
__all__ += ["SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE", "STRATAGEM_DECISION_TYPE"]
__all__ += ["SecondaryMissionChoice", "SecondaryMissionMode", "SetupStep", "ShootingPhaseState"]
__all__ += ["ShootingTargetRestrictionContext", "ShootingType", "StratagemDefinition"]
__all__ += ["StratagemEligibilityContext", "StratagemUseRecord", "TimingTriggerKind"]
__all__ += ["UnitCharacteristicModifierContext", "UnitMusterSelection", "WeaponKeyword"]
__all__ += ["WeaponProfile", "WeaponProfileModifierContext", "WoundRollModifierContext"]
__all__ += ["_COURT_ENHANCEMENT_EXECUTION_IDS", "_COURT_GENERIC_EXECUTION_IDS"]
__all__ += ["_SPECTACLE_ENHANCEMENT_EXECUTION_IDS", "_SPECTACLE_GENERIC_EXECUTION_IDS"]
__all__ += ["_apply_battle_formation_hooks_from_bundle", "_clear_terrain"]
__all__ += ["_court_battle_lifecycle", "_court_blade_profile", "_court_catalog"]
__all__ += ["_court_datasheet_id_for_selection", "_court_lifecycle_config"]
__all__ += ["_court_muster_request", "_court_shoota_profile", "_court_stratagem"]
__all__ += ["_court_stratagem_decision_result", "_court_weapon_profile_context"]
__all__ += ["_effect_parameter", "_first_model_id", "_grant_cp", "_last_event_payload"]
__all__ += ["_leader_blade_profile", "_mission_setup", "_mob_shoota_profile"]
__all__ += ["_more_dakka_muster_request", "_more_dakka_stratagem"]
__all__ += ["_more_dakka_stratagem_decision_result", "_option_stratagem_id"]
__all__ += ["_option_target_unit_id", "_place_units_for_court_within_12"]
__all__ += ["_place_units_for_more_dakka_shooting", "_prepare_battle_phase"]
__all__ += ["_profile_has_ability", "_record_charge_move_effect"]
__all__ += ["_record_fixed_secondary_choices_for_fixture", "_replace_unit_poses"]
__all__ += ["_set_current_battle_phase", "_spectacle_battle_lifecycle", "_spectacle_catalog"]
__all__ += ["_spectacle_lifecycle_config", "_spectacle_muster_request", "_spectacle_stratagem"]
__all__ += ["_spectacle_stratagem_decision_result", "_spectacle_weapon_profile_context"]
__all__ += ["_use_court_stratagem", "_use_court_stratagem_through_lifecycle"]
__all__ += ["_use_more_dakka_stratagem", "_use_more_dakka_stratagem_through_lifecycle"]
__all__ += ["_use_spectacle_stratagem", "_use_spectacle_stratagem_through_lifecycle"]
__all__ += ["_weapon_profile_context", "apply_stratagem_decision"]
__all__ += ["chapter_approved_2026_27_mission_pack"]
__all__ += ["charge_transit_through_non_vehicle_monster_models_allowed", "court_ir"]
__all__ += ["create_deterministic_battlefield_scenario", "emperors_children_july"]
__all__ += ["enter_battle_for_fixture", "july_faction_packs_2026_07"]
__all__ += ["movement_transit_through_terrain_features_allowed", "muster_army", "replace"]
__all__ += ["request_stratagem_use_from_index"]
__all__ += ["source_backed_reroll_permission_context_for_unit"]
