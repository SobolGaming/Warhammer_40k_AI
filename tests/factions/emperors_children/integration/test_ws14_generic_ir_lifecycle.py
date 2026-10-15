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
def test_ws14_spectacle_of_slaughter_page_four_rows_execute_from_lifecycle_bundle() -> None:
    config = _spectacle_lifecycle_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.advance_until_decision_or_terminal()

    bundle = _runtime_content_bundle(lifecycle)

    assert "emperors-children" in bundle.activation.selected_faction_ids
    assert "spectacle-of-slaughter" in bundle.activation.selected_detachment_ids
    assert set(_SPECTACLE_GENERIC_EXECUTION_IDS).issubset(
        bundle.activation.selected_execution_record_ids
    )

    context = FactionRuleExecutionContext(
        game_id=config.game_id,
        player_id="player-a",
        battle_round=1,
        phase=BattlePhaseKind.FIGHT,
        active_player_id="player-a",
        source_unit_instance_id="army-alpha:blades-1",
        target_unit_instance_ids=("army-alpha:blades-1",),
        trigger_payload={"event": "ws14-spectacle-generic-ir-demo"},
    )
    results = tuple(
        bundle.faction_rule_execution_registry.execute(
            execution_id=execution_id,
            context=context,
        )
        for execution_id in _SPECTACLE_ENHANCEMENT_EXECUTION_IDS
    )

    assert tuple(result.status for result in results) == (
        FactionRuleExecutionStatus.APPLIED,
        FactionRuleExecutionStatus.APPLIED,
    )
    for result in results:
        record = bundle.faction_rule_execution_registry.record_by_execution_id(result.execution_id)
        assert record.execution_status is Phase17FExecutionStatus.EXECUTABLE_GENERIC_IR
        assert record.rule_ir_hash is not None
        assert FactionRuleExecutionResult.from_payload(result.to_payload()) == result

    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()
    assert "object at 0x" not in json.dumps(lifecycle.to_payload(), sort_keys=True)


@pytest.mark.integration
def test_ws14_spectacle_of_slaughter_rule_and_enhancements_bind_to_runtime_hooks() -> None:
    lifecycle = _spectacle_battle_lifecycle()
    state = _state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)

    assignment_payloads = sorted(
        (
            assignment.to_payload()
            for assignment in bundle.activation.selected_enhancement_assignments
            if assignment.player_id == "player-a"
        ),
        key=lambda payload: str(payload["assignment_id"]),
    )
    assert assignment_payloads == [
        {
            "bearer_model_instance_id": "army-alpha:blades-1:core-boyz-like:001",
            "assignment_id": "army-alpha:000010900002:blades-1",
            "player_id": "player-a",
            "army_id": "army-alpha",
            "enhancement_id": "000010900002",
            "target_unit_selection_id": "blades-1",
            "bearer_unit_instance_id": "army-alpha:blades-1",
            "source_id": "ws14-spectacle:assignment:blades-1:000010900002",
        },
        {
            "bearer_model_instance_id": "army-alpha:blades-2:core-boyz-like:001",
            "assignment_id": "army-alpha:000010900003:blades-2",
            "player_id": "player-a",
            "army_id": "army-alpha",
            "enhancement_id": "000010900003",
            "target_unit_selection_id": "blades-2",
            "bearer_unit_instance_id": "army-alpha:blades-2",
            "source_id": "ws14-spectacle:assignment:blades-2:000010900003",
        },
    ]

    fights_first = FightsFirstRegistry.from_state(state)
    assert fights_first.has_unit("army-alpha:blades-1")
    assert fights_first.has_unit("army-alpha:blades-2")

    eager_model_id = _first_model_id(state, unit_instance_id="army-alpha:blades-2")
    assert (
        bundle.runtime_modifier_registry.modified_movement_inches(
            MovementBudgetModifierContext(
                state=state,
                unit_instance_id="army-alpha:blades-2",
                model_instance_id=eager_model_id,
                movement=CharacteristicValue(Characteristic.MOVEMENT, int(6.0), int(6.0), int(6.0)),
            )
        )
        == 8.0
    )

    snap_restrictions = bundle.shooting_target_restriction_hook_registry.restrictions_for(
        ShootingTargetRestrictionContext(
            state=state,
            player_id="player-b",
            battle_round=state.battle_round,
            attacking_unit_instance_id="army-beta:blades-3",
            target_unit_instance_id="army-alpha:blades-1",
            attacker_model_instance_id=_first_model_id(
                state, unit_instance_id="army-beta:blades-3"
            ),
            shooting_type=ShootingType.SNAP,
        )
    )
    assert len(snap_restrictions) == 1
    assert snap_restrictions[0].violation_code == (
        "spectacle_of_slaughter_beguiling_grotesquerie_snap_target_forbidden"
    )
    normal_restrictions = bundle.shooting_target_restriction_hook_registry.restrictions_for(
        ShootingTargetRestrictionContext(
            state=state,
            player_id="player-b",
            battle_round=state.battle_round,
            attacking_unit_instance_id="army-beta:blades-3",
            target_unit_instance_id="army-alpha:blades-1",
            attacker_model_instance_id=_first_model_id(
                state, unit_instance_id="army-beta:blades-3"
            ),
            shooting_type=ShootingType.NORMAL,
        )
    )
    assert normal_restrictions == ()
    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()


@pytest.mark.integration
def test_ws14_court_of_the_phoenician_rows_execute_from_lifecycle_bundle() -> None:
    config = _court_lifecycle_config()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.advance_until_decision_or_terminal()

    bundle = _runtime_content_bundle(lifecycle)

    assert "emperors-children" in bundle.activation.selected_faction_ids
    assert "court-of-the-phoenician" in bundle.activation.selected_detachment_ids
    assert set(_COURT_GENERIC_EXECUTION_IDS).issubset(
        bundle.activation.selected_execution_record_ids
    )

    context = FactionRuleExecutionContext(
        game_id=config.game_id,
        player_id="player-a",
        battle_round=1,
        phase=BattlePhaseKind.FIGHT,
        active_player_id="player-a",
        source_unit_instance_id="army-alpha:fulgrim-1",
        target_unit_instance_ids=("army-alpha:fulgrim-1",),
        trigger_payload={"event": "ws14-court-generic-ir-demo"},
    )
    results = tuple(
        bundle.faction_rule_execution_registry.execute(
            execution_id=execution_id,
            context=context,
        )
        for execution_id in _COURT_ENHANCEMENT_EXECUTION_IDS
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

    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()
    assert "object at 0x" not in json.dumps(lifecycle.to_payload(), sort_keys=True)


@pytest.mark.integration
def test_ws14_court_of_the_phoenician_rule_and_enhancements_bind_to_runtime_hooks() -> None:
    lifecycle = _court_battle_lifecycle()
    state = _state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)

    court_effects = tuple(
        effect
        for effect in state.persisting_effects_for_unit("army-alpha:fulgrim-1")
        if effect.source_rule_id == "gw-11e-phase17e-faction-coverage-2026-27:phase17e:"
        "emperors-children:court-of-the-phoenician:rule:source-text"
    )
    assert len(court_effects) == 4
    assert any(
        _effect_parameter(_json_object(_json_object(effect.effect_payload)["effect"]), "ability")
        == "sensational_performance"
        for effect in court_effects
    )

    lord_model_id = _first_model_id(state, unit_instance_id="army-alpha:lord-exultant-1")
    assert (
        bundle.runtime_modifier_registry.modified_movement_inches(
            MovementBudgetModifierContext(
                state=state,
                unit_instance_id="army-alpha:lord-exultant-1",
                model_instance_id=lord_model_id,
                movement=CharacteristicValue(Characteristic.MOVEMENT, int(6.0), int(6.0), int(6.0)),
            )
        )
        == 7.0
    )

    daemon_model_id = _first_model_id(state, unit_instance_id="army-alpha:daemon-prince-1")
    daemon_base = _court_blade_profile()
    daemon_profile = bundle.runtime_modifier_registry.modified_weapon_profile(
        _court_weapon_profile_context(
            state=state,
            weapon_profile=daemon_base,
            attacker_model_id=daemon_model_id,
            attacking_unit_id="army-alpha:daemon-prince-1",
            target_unit_id="army-beta:enemy-character-1",
            source_phase=BattlePhase.FIGHT,
        )
    )
    assert daemon_profile.strength.final == daemon_base.strength.final + 1
    assert daemon_base.attack_profile.fixed_attacks is not None
    assert daemon_profile.attack_profile.fixed_attacks == (
        daemon_base.attack_profile.fixed_attacks + 1
    )

    fulgrim_model_id = _first_model_id(state, unit_instance_id="army-alpha:fulgrim-1")
    sensational_base = _court_blade_profile()
    pre_charge_profile = bundle.runtime_modifier_registry.modified_weapon_profile(
        _court_weapon_profile_context(
            state=state,
            weapon_profile=sensational_base,
            attacker_model_id=fulgrim_model_id,
            attacking_unit_id="army-alpha:fulgrim-1",
            target_unit_id="army-beta:enemy-character-1",
            source_phase=BattlePhase.FIGHT,
        )
    )
    assert pre_charge_profile.strength == sensational_base.strength
    assert pre_charge_profile.armor_penetration == sensational_base.armor_penetration

    _record_charge_move_effect(state, unit_instance_id="army-alpha:fulgrim-1")
    post_charge_profile = bundle.runtime_modifier_registry.modified_weapon_profile(
        _court_weapon_profile_context(
            state=state,
            weapon_profile=sensational_base,
            attacker_model_id=fulgrim_model_id,
            attacking_unit_id="army-alpha:fulgrim-1",
            target_unit_id="army-beta:enemy-character-1",
            source_phase=BattlePhase.FIGHT,
        )
    )
    assert post_charge_profile.strength.final == sensational_base.strength.final + 1
    assert post_charge_profile.armor_penetration.final == (
        sensational_base.armor_penetration.final - 1
    )
    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()


__all__: list[str] = []
__all__ += ["AbilityKind", "ArmyCatalog", "ArmyMusterRequest", "BattleFormationRequestContext"]
__all__ += ["CHARGE_FIGHTS_FIRST_EFFECT_KIND", "CommandPointGainStatus", "CommandPointSourceKind"]
__all__ += ["DESTROYED_TARGET_UNIT_CONTEXT_KEY", "DatasheetKeywordSet", "DecisionResult"]
__all__ += ["ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY", "DetachmentDefinition", "DetachmentSelection"]
__all__ += ["EffectExpiration", "EnhancementAssignment", "EnhancementDefinition"]
__all__ += ["FALL_BACK_UNIT_CONTEXT_KEY", "FactionDefinition", "FightPhaseState", "GameConfig"]
__all__ += ["GameLifecycleError", "GameLifecycleStage", "GameState", "HitRollModifierContext"]
__all__ += ["JUST_SHOT_UNIT_CONTEXT_KEY", "JsonValue", "LifecycleStatus", "LifecycleStatusKind"]
__all__ += ["MissionSetup", "ModelProfileSelection", "MovementCapabilitySet", "MovementMode"]
__all__ += ["ObjectiveControlModifierContext", "PersistingEffect", "Pose", "ReactionQueue"]
__all__ += ["RulesetDescriptor", "RuntimeContentBundle"]
__all__ += ["SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE"]
__all__ += ["SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE", "STRATAGEM_DECISION_TYPE"]
__all__ += ["SecondaryMissionChoice", "SecondaryMissionMode", "SetupStep", "ShootingPhaseState"]
__all__ += ["StratagemDefinition", "StratagemEligibilityContext", "StratagemUseRecord"]
__all__ += ["TimingTriggerKind", "UnitCharacteristicModifierContext", "UnitMusterSelection"]
__all__ += ["WeaponKeyword", "WeaponProfile", "WeaponProfileModifierContext"]
__all__ += ["_MORE_DAKKA_ENHANCEMENT_EXECUTION_IDS", "WoundRollModifierContext"]
__all__ += ["_MORE_DAKKA_GENERIC_EXECUTION_IDS", "_apply_battle_formation_hooks_from_bundle"]
__all__ += ["_clear_terrain", "_court_catalog", "_court_datasheet_id_for_selection"]
__all__ += ["_court_muster_request", "_court_shoota_profile", "_court_stratagem"]
__all__ += ["_court_stratagem_decision_result", "_grant_cp", "_last_event_payload"]
__all__ += ["_leader_blade_profile", "_mission_setup", "_mob_shoota_profile"]
__all__ += ["_more_dakka_battle_lifecycle", "_more_dakka_catalog", "_more_dakka_lifecycle_config"]
__all__ += ["_more_dakka_muster_request", "_more_dakka_stratagem"]
__all__ += ["_more_dakka_stratagem_decision_result", "_option_stratagem_id"]
__all__ += ["_option_target_unit_id", "_place_units_for_court_within_12"]
__all__ += ["_place_units_for_more_dakka_shooting", "_prepare_battle_phase"]
__all__ += ["_profile_has_ability", "_record_fixed_secondary_choices_for_fixture"]
__all__ += ["_replace_unit_poses", "_set_current_battle_phase", "_spectacle_catalog"]
__all__ += ["_spectacle_muster_request", "_spectacle_stratagem"]
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
