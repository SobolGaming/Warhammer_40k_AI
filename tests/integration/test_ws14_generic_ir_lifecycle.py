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
def test_ws14_more_dakka_stratagem_activation_binds_target_through_lifecycle_bundle() -> None:
    lifecycle = _more_dakka_battle_lifecycle()
    state = _state(lifecycle)
    _set_current_battle_phase(state, BattlePhase.COMMAND)
    _grant_cp(state, player_id="player-a", amount=2)
    bundle = _runtime_content_bundle(lifecycle)
    player_index = bundle.stratagem_indexes_by_player_id["player-a"]
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.START_PHASE,
    )

    status = request_stratagem_use_from_index(
        state=state,
        decisions=lifecycle.decision_controller,
        index=player_index,
        context=context,
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = lifecycle.pending_decision_request()
    assert request is not None
    assert request.decision_type == STRATAGEM_DECISION_TYPE
    selected_option = next(
        option
        for option in request.options
        if _option_stratagem_id(option.payload) == "000009992003"
    )

    result = DecisionResult.for_request(
        result_id="ws14-more-dakka-get-stuck-in-result",
        request=request,
        selected_option_id=selected_option.option_id,
    )
    submit_status = lifecycle.submit_decision(result)

    assert submit_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    command_start_request = lifecycle.pending_decision_request()
    assert command_start_request is not None
    assert (
        command_start_request.decision_type
        == SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE
    )
    decline_waaagh_option = next(
        option
        for option in command_start_request.options
        if _json_object(option.payload).get("selected_waaagh_option") == "decline"
    )
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="ws14-more-dakka-decline-waaagh-result",
            request=command_start_request,
            selected_option_id=decline_waaagh_option.option_id,
        )
    )

    assert state.command_point_total("player-a") == 1
    use_record = state.stratagem_use_records[-1]
    assert use_record.stratagem_id == "000009992003"
    assert use_record.command_point_cost == 2
    spent = _last_event_payload(lifecycle, "command_points_spent")
    assert spent["player_id"] == "player-a"
    assert spent["requested_amount"] == 2
    assert spent["applied_amount"] == 2
    assert spent["source_id"] == use_record.use_id
    assert spent["source_kind"] == "stratagem_spend"
    spent_transaction = _json_object(spent["transaction"])
    assert spent_transaction["amount"] == -2
    assert spent_transaction["transaction_id"] == use_record.command_point_transaction_id
    assert use_record.targeted_unit_instance_ids == ("army-alpha:boyz-1",)
    target_bound = _last_event_payload(lifecycle, "rule_execution_target_bound")
    assert target_bound["target_kind"] == "friendly_unit"
    assert target_bound["target_unit_instance_ids"] == ["army-alpha:boyz-1"]
    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()
    assert "object at 0x" not in json.dumps(lifecycle.to_payload(), sort_keys=True)


@pytest.mark.integration
def test_ws14_more_dakka_detachment_rule_and_get_stuck_in_use_ir_runtime_hooks() -> None:
    lifecycle = _more_dakka_battle_lifecycle()
    state = _state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)
    weapon_profile = _mob_shoota_profile()
    attacker_model_id = _first_model_id(state, unit_instance_id="army-alpha:boyz-1")
    _prepare_battle_phase(state, phase=BattlePhase.SHOOTING, active_player_id="player-a")

    baseline_profile = bundle.runtime_modifier_registry.modified_weapon_profile(
        _weapon_profile_context(
            state=state,
            weapon_profile=weapon_profile,
            attacker_model_id=attacker_model_id,
        )
    )

    assert WeaponKeyword.ASSAULT in baseline_profile.keywords
    assert not _profile_has_ability(baseline_profile, AbilityKind.SUSTAINED_HITS)

    _use_more_dakka_stratagem(
        lifecycle,
        stratagem_id="000009992003",
        target_unit_id="army-alpha:boyz-1",
        phase=BattlePhase.COMMAND,
        command_points=2,
    )
    _prepare_battle_phase(state, phase=BattlePhase.SHOOTING, active_player_id="player-a")
    waaagh_profile = bundle.runtime_modifier_registry.modified_weapon_profile(
        _weapon_profile_context(
            state=state,
            weapon_profile=weapon_profile,
            attacker_model_id=attacker_model_id,
        )
    )

    assert _profile_has_ability(waaagh_profile, AbilityKind.SUSTAINED_HITS)
    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()


@pytest.mark.integration
def test_ws14_more_dakka_stratagem_ir_effects_drive_runtime_hooks() -> None:
    orks_lifecycle = _more_dakka_battle_lifecycle()
    orks_state = _state(orks_lifecycle)
    _use_more_dakka_stratagem(
        orks_lifecycle,
        stratagem_id="000009992002",
        target_unit_id="army-alpha:boyz-1",
        phase=BattlePhase.FIGHT,
    )
    reroll_context = source_backed_reroll_permission_context_for_unit(
        state=orks_state,
        player_id="player-a",
        unit_instance_id="army-alpha:boyz-1",
        model_instance_id=_first_model_id(orks_state, unit_instance_id="army-alpha:boyz-1"),
        roll_type="attack_sequence.wound",
        timing_window="attack.wound",
        target_unit_instance_id="army-beta:boyz-2",
    )
    assert reroll_context is not None
    assert reroll_context.source_payload["conditional_wound_reroll"] == {
        "reroll_unmodified_values": [1],
        "full_reroll_if_target_within_objective_range": True,
    }

    huge_lifecycle = _more_dakka_battle_lifecycle()
    huge_state = _state(huge_lifecycle)
    huge_bundle = _runtime_content_bundle(huge_lifecycle)
    _use_more_dakka_stratagem(
        huge_lifecycle,
        stratagem_id="000009992004",
        target_unit_id="army-alpha:walker-1",
        phase=BattlePhase.COMMAND,
    )
    walker_model_id = _first_model_id(huge_state, unit_instance_id="army-alpha:walker-1")
    assert (
        huge_bundle.runtime_modifier_registry.modified_movement_inches(
            MovementBudgetModifierContext(
                state=huge_state,
                unit_instance_id="army-alpha:walker-1",
                model_instance_id=walker_model_id,
                movement=CharacteristicValue(Characteristic.MOVEMENT, int(6.0), int(6.0), int(6.0)),
            )
        )
        == 7.0
    )
    assert (
        huge_bundle.runtime_modifier_registry.modified_objective_control(
            ObjectiveControlModifierContext(
                state=huge_state,
                unit_instance_id="army-alpha:walker-1",
                model_instance_id=walker_model_id,
                base_objective_control=2,
                current_objective_control=2,
            )
        )
        == 3
    )
    assert (
        huge_bundle.runtime_modifier_registry.modified_unit_characteristic(
            UnitCharacteristicModifierContext(
                state=huge_state,
                unit_instance_id="army-alpha:walker-1",
                characteristic=Characteristic.LEADERSHIP,
                base_value=7,
                current_value=7,
            )
        )
        == 6
    )
    assert (
        huge_bundle.runtime_modifier_registry.hit_roll_modifier(
            HitRollModifierContext(
                state=huge_state,
                attacking_unit_instance_id="army-alpha:walker-1",
                attacker_model_instance_id=walker_model_id,
                target_unit_instance_id="army-beta:boyz-2",
                weapon_profile=_mob_shoota_profile(),
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == 1
    )

    long_lifecycle = _more_dakka_battle_lifecycle()
    long_state = _state(long_lifecycle)
    long_bundle = _runtime_content_bundle(long_lifecycle)
    _use_more_dakka_stratagem(
        long_lifecycle,
        stratagem_id="000009992005",
        target_unit_id="army-alpha:boyz-1",
        phase=BattlePhase.SHOOTING,
    )
    long_profile = long_bundle.runtime_modifier_registry.modified_weapon_profile(
        _weapon_profile_context(
            state=long_state,
            weapon_profile=_mob_shoota_profile(),
            attacker_model_id=_first_model_id(long_state, unit_instance_id="army-alpha:boyz-1"),
        )
    )
    assert WeaponKeyword.IGNORES_COVER in long_profile.keywords

    shells_lifecycle = _more_dakka_battle_lifecycle()
    shells_state = _state(shells_lifecycle)
    _place_units_for_more_dakka_shooting(shells_state)
    shells_bundle = _runtime_content_bundle(shells_lifecycle)
    _use_more_dakka_stratagem(
        shells_lifecycle,
        stratagem_id="000009992006",
        target_unit_id="army-alpha:boyz-1",
        phase=BattlePhase.SHOOTING,
    )
    shells_profile = shells_bundle.runtime_modifier_registry.modified_weapon_profile(
        _weapon_profile_context(
            state=shells_state,
            weapon_profile=_mob_shoota_profile(),
            attacker_model_id=_first_model_id(shells_state, unit_instance_id="army-alpha:boyz-1"),
        )
    )
    assert shells_profile.armor_penetration.final == -1


@pytest.mark.integration
def test_ws14_more_dakka_call_dat_dakka_binds_destroyed_target_and_requests_shooting() -> None:
    from tests.dice_result_semantics_helpers import assert_active_player_history, open_phase

    lifecycle = _more_dakka_battle_lifecycle()
    state = _state(lifecycle)
    _place_units_for_more_dakka_shooting(state)
    _prepare_battle_phase(state, phase=BattlePhase.SHOOTING, active_player_id="player-b")
    open_phase(lifecycle)

    use_record, submit_status = _use_more_dakka_stratagem_through_lifecycle(
        lifecycle,
        stratagem_id="000009992007",
        target_unit_id="army-alpha:boyz-1",
        phase=BattlePhase.SHOOTING,
        active_player_id="player-b",
        trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_SHOT,
        trigger_payload={
            JUST_SHOT_UNIT_CONTEXT_KEY: "army-beta:boyz-2",
            DESTROYED_TARGET_UNIT_CONTEXT_KEY: ["army-alpha:boyz-1"],
        },
    )

    assert use_record.targeted_unit_instance_ids == ("army-alpha:boyz-1",)
    assert state.out_of_phase_shooting_state is not None
    assert state.out_of_phase_shooting_state.player_id == "player-a"
    assert state.out_of_phase_shooting_state.selected_unit_instance_id == "army-alpha:boyz-1"
    assert state.out_of_phase_shooting_state.target_unit_ids == ("army-beta:boyz-2",)
    assert (
        _last_event_payload(lifecycle, "generic_stratagem_out_of_phase_shooting_requested")[
            "target_unit_instance_id"
        ]
        == "army-beta:boyz-2"
    )
    assert submit_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert submit_status.decision_request is not None
    assert submit_status.decision_request.decision_type == "submit_shooting_declaration"
    request = lifecycle.pending_decision_request()
    assert request is not None
    assert request == submit_status.decision_request
    assert request.decision_type == "submit_shooting_declaration"
    assert GameLifecycle.from_payload(lifecycle.to_payload()).to_payload() == lifecycle.to_payload()

    assert_active_player_history(lifecycle, expected_player="player-a")


@pytest.mark.integration
def test_ws14_spectacle_of_slaughter_stratagems_execute_through_lifecycle() -> None:
    honour_lifecycle = _spectacle_battle_lifecycle()
    use_record, submit_status = _use_spectacle_stratagem_through_lifecycle(
        honour_lifecycle,
        stratagem_id="000010901002",
        target_unit_id="army-alpha:blades-1",
        phase=BattlePhase.FIGHT,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
    )
    assert use_record.targeted_unit_instance_ids == ("army-alpha:blades-1",)
    assert submit_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    honour_effect_payload = _last_event_payload(honour_lifecycle, "rule_execution_effect_applied")
    honour_effect = _json_object(honour_effect_payload["effect"])
    assert honour_effect["kind"] == "grant_weapon_ability"
    assert honour_effect_payload["target_unit_instance_ids"] == ["army-alpha:blades-1"]

    honour_hook_lifecycle = _spectacle_battle_lifecycle()
    honour_hook_state = _state(honour_hook_lifecycle)
    honour_hook_bundle = _runtime_content_bundle(honour_hook_lifecycle)
    _use_spectacle_stratagem(
        honour_hook_lifecycle,
        stratagem_id="000010901002",
        target_unit_id="army-alpha:blades-1",
        phase=BattlePhase.FIGHT,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT,
    )
    precision_profile = honour_hook_bundle.runtime_modifier_registry.modified_weapon_profile(
        _spectacle_weapon_profile_context(
            state=honour_hook_state,
            weapon_profile=_leader_blade_profile(),
            attacker_model_id=_first_model_id(
                honour_hook_state,
                unit_instance_id="army-alpha:blades-1",
            ),
            source_phase=BattlePhase.FIGHT,
        )
    )
    assert WeaponKeyword.PRECISION in precision_profile.keywords

    single_lifecycle = _spectacle_battle_lifecycle()
    _use_record, submit_status = _use_spectacle_stratagem_through_lifecycle(
        single_lifecycle,
        stratagem_id="000010901003",
        target_unit_id="army-alpha:blades-1",
        phase=BattlePhase.CHARGE,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
    )
    assert submit_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    single_effect_payload = _last_event_payload(single_lifecycle, "rule_execution_effect_applied")
    single_effect = _json_object(single_effect_payload["effect"])
    assert single_effect["kind"] == "movement_transit_permission"
    assert single_effect_payload["target_unit_instance_ids"] == ["army-alpha:blades-1"]

    single_hook_lifecycle = _spectacle_battle_lifecycle()
    single_hook_state = _state(single_hook_lifecycle)
    _use_spectacle_stratagem(
        single_hook_lifecycle,
        stratagem_id="000010901003",
        target_unit_id="army-alpha:blades-1",
        phase=BattlePhase.CHARGE,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
    )
    assert charge_transit_through_non_vehicle_monster_models_allowed(
        tuple(single_hook_state.persisting_effects_for_unit("army-alpha:blades-1")),
        owner_player_id="player-a",
    )

    intoxicated_lifecycle = _spectacle_battle_lifecycle()
    use_record, submit_status = _use_spectacle_stratagem_through_lifecycle(
        intoxicated_lifecycle,
        stratagem_id="000010901004",
        target_unit_id="army-alpha:blades-1",
        phase=BattlePhase.MOVEMENT,
        active_player_id="player-b",
        trigger_kind=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
        trigger_payload={
            FALL_BACK_UNIT_CONTEXT_KEY: "army-beta:blades-3",
            ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY: ["army-alpha:blades-1"],
        },
    )
    assert use_record.targeted_unit_instance_ids == ("army-alpha:blades-1",)
    assert submit_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = intoxicated_lifecycle.pending_decision_request()
    assert request is not None
    assert request.decision_type == SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE
    request_payload = _json_object(request.payload)
    eligible_units = request_payload["eligible_units"]
    assert isinstance(eligible_units, list)
    assert len(eligible_units) == 1
    eligible_unit = _json_object(eligible_units[0])
    assert eligible_unit["unit_instance_id"] == "army-alpha:blades-1"
    descriptor = _json_object(request_payload["descriptor"])
    max_distance = descriptor["max_distance_inches"]
    assert isinstance(max_distance, int | float)
    assert 4 <= max_distance <= 6
    event_payload = _last_event_payload(
        intoxicated_lifecycle,
        "generic_stratagem_triggered_normal_move_requested",
    )
    assert event_payload["unit_instance_id"] == "army-alpha:blades-1"
    assert "object at 0x" not in json.dumps(intoxicated_lifecycle.to_payload(), sort_keys=True)
    assert (
        GameLifecycle.from_payload(intoxicated_lifecycle.to_payload()).to_payload()
        == intoxicated_lifecycle.to_payload()
    )


@pytest.mark.integration
def test_ws14_july_exalted_patron_mustering_and_lifecycle_remove_attachment_grant() -> None:
    current_catalog = emperors_children_july.current_army_catalog(_court_catalog())
    valid_request = replace(
        _court_muster_request(
            catalog=current_catalog,
            army_id="army-alpha",
            player_id="player-a",
            unit_selection_ids=("lord-exultant-1",),
            enhancement_assignments=(("000010654003", "lord-exultant-1"),),
        ),
        roster_legality_required=False,
    )
    mustered = muster_army(catalog=current_catalog, request=valid_request)
    assert not any(
        violation.violation_code == "enhancement_target_keyword_required"
        for violation in mustered.roster_legality_report.violations
    )

    invalid_request = replace(
        _court_muster_request(
            catalog=current_catalog,
            army_id="army-alpha",
            player_id="player-a",
            unit_selection_ids=("tears-1",),
            enhancement_assignments=(("000010654003", "tears-1"),),
        ),
        roster_legality_required=False,
    )
    invalid_mustered = muster_army(catalog=current_catalog, request=invalid_request)
    assert any(
        violation.violation_code == "enhancement_target_keyword_required"
        for violation in invalid_mustered.roster_legality_report.violations
    )

    lifecycle = _court_battle_lifecycle()
    state = _state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)
    artifact = july_faction_packs_2026_07.exalted_patron()
    record = bundle.faction_rule_execution_registry.record_by_execution_id(
        artifact.phase17f_execution_id
    )
    assert record.rule_ir_hash == artifact.rule_ir().ir_hash()
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
    current_effect_payload = json.dumps(
        [
            effect.to_payload()
            for effect in state.persisting_effects_for_unit("army-alpha:lord-exultant-1")
        ],
        sort_keys=True,
    )
    assert "may_attach_to_flawless_blades" not in current_effect_payload
    assert "FLAWLESS BLADES" not in current_effect_payload


@pytest.mark.integration
def test_ws14_court_of_the_phoenician_stratagems_execute_through_lifecycle() -> None:
    prideful_lifecycle = _court_battle_lifecycle()
    use_record, submit_status = _use_court_stratagem_through_lifecycle(
        prideful_lifecycle,
        stratagem_id="000010655003",
        target_unit_id="army-alpha:fulgrim-1",
        phase=BattlePhase.FIGHT,
        command_points=0,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    assert use_record.command_point_cost == 0
    assert (
        "warhammer_40000_11th:emperors_children:detachment:"
        "court_of_the_phoenician:master_of_the_pageant:cp_cost_reduction"
        in use_record.command_point_modifier_ids
    )
    assert submit_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    prideful_effect_lifecycle = _court_battle_lifecycle()
    _use_court_stratagem(
        prideful_effect_lifecycle,
        stratagem_id="000010655003",
        target_unit_id="army-alpha:fulgrim-1",
        phase=BattlePhase.FIGHT,
        command_points=0,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    prideful_state = _state(prideful_effect_lifecycle)
    reroll_context = source_backed_reroll_permission_context_for_unit(
        state=prideful_state,
        player_id="player-a",
        unit_instance_id="army-alpha:fulgrim-1",
        model_instance_id=_first_model_id(prideful_state, unit_instance_id="army-alpha:fulgrim-1"),
        roll_type="attack_sequence.hit",
        timing_window="attack_sequence.hit",
        target_unit_instance_id="army-beta:enemy-character-1",
    )
    assert reroll_context is not None

    restriction_lifecycle = _court_battle_lifecycle()
    restriction_state = _state(restriction_lifecycle)
    _prepare_battle_phase(
        restriction_state,
        phase=BattlePhase.CHARGE,
        active_player_id="player-a",
    )
    _grant_cp(restriction_state, player_id="player-a", amount=1)
    restriction_context = StratagemEligibilityContext.from_state(
        state=restriction_state,
        player_id="player-a",
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    restriction_status = request_stratagem_use_from_index(
        state=restriction_state,
        decisions=restriction_lifecycle.decision_controller,
        index=_runtime_content_bundle(restriction_lifecycle).stratagem_indexes_by_player_id[
            "player-a"
        ],
        context=restriction_context,
        stratagem_cost_modifier_registry=(
            _runtime_content_bundle(restriction_lifecycle).stratagem_cost_modifier_registry
        ),
    )
    assert restriction_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = restriction_lifecycle.pending_decision_request()
    assert request is not None
    assert not any(
        _option_stratagem_id(option.payload) == "000010655004"
        and _option_target_unit_id(option.payload) == "army-alpha:tears-1"
        for option in request.options
    )
    assert any(
        _option_stratagem_id(option.payload) == "000010655004"
        and _option_target_unit_id(option.payload) == "army-alpha:fulgrim-1"
        for option in request.options
    )

    sinuous_lifecycle = _court_battle_lifecycle()
    sinuous_state = _state(sinuous_lifecycle)
    _use_court_stratagem(
        sinuous_lifecycle,
        stratagem_id="000010655004",
        target_unit_id="army-alpha:fulgrim-1",
        phase=BattlePhase.CHARGE,
        command_points=0,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    sinuous_effects = tuple(sinuous_state.persisting_effects_for_unit("army-alpha:fulgrim-1"))
    assert movement_transit_through_terrain_features_allowed(
        sinuous_effects,
        owner_player_id="player-a",
        movement_mode="charge",
        unit_keywords=(
            court_ir.FULGRIM_KEYWORD,
            court_ir.DAEMON_KEYWORD,
            court_ir.CHARACTER_KEYWORD,
        ),
    )
    sinuous_capabilities = MovementCapabilitySet.from_keywords(
        (
            court_ir.FULGRIM_KEYWORD,
            court_ir.DAEMON_KEYWORD,
            court_ir.CHARACTER_KEYWORD,
        ),
        ruleset_descriptor=sinuous_lifecycle.config.ruleset_descriptor,
        movement_mode=MovementMode.CHARGE,
        unit_persisting_effects=sinuous_effects,
        owner_player_id="player-a",
    )
    assert sinuous_capabilities.can_move_through_terrain

    contempt_lifecycle = _court_battle_lifecycle()
    contempt_state = _state(contempt_lifecycle)
    contempt_bundle = _runtime_content_bundle(contempt_lifecycle)
    _use_court_stratagem(
        contempt_lifecycle,
        stratagem_id="000010655002",
        target_unit_id="army-alpha:fulgrim-1",
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    assert (
        contempt_bundle.runtime_modifier_registry.wound_roll_modifier(
            WoundRollModifierContext(
                state=contempt_state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id="army-beta:enemy-character-1",
                attacker_model_instance_id=_first_model_id(
                    contempt_state,
                    unit_instance_id="army-beta:enemy-character-1",
                ),
                target_unit_instance_id="army-alpha:fulgrim-1",
                weapon_profile=_court_shoota_profile(),
                strength=10,
                toughness=8,
            )
        )
        == -1
    )
    assert (
        contempt_bundle.runtime_modifier_registry.wound_roll_modifier(
            WoundRollModifierContext(
                state=contempt_state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id="army-beta:enemy-character-1",
                attacker_model_instance_id=_first_model_id(
                    contempt_state,
                    unit_instance_id="army-beta:enemy-character-1",
                ),
                target_unit_instance_id="army-alpha:fulgrim-1",
                weapon_profile=_court_shoota_profile(),
                strength=8,
                toughness=8,
            )
        )
        == 0
    )

    close_lifecycle = _court_battle_lifecycle()
    close_state = _state(close_lifecycle)
    _place_units_for_court_within_12(close_state)
    close_bundle = _runtime_content_bundle(close_lifecycle)
    close_base = _court_shoota_profile()
    _use_court_stratagem(
        close_lifecycle,
        stratagem_id="000010655005",
        target_unit_id="army-alpha:fulgrim-1",
        phase=BattlePhase.SHOOTING,
        trigger_kind=TimingTriggerKind.START_PHASE,
    )
    close_profile = close_bundle.runtime_modifier_registry.modified_weapon_profile(
        _court_weapon_profile_context(
            state=close_state,
            weapon_profile=close_base,
            attacker_model_id=_first_model_id(close_state, unit_instance_id="army-alpha:fulgrim-1"),
            attacking_unit_id="army-alpha:fulgrim-1",
            target_unit_id="army-beta:enemy-character-1",
            source_phase=BattlePhase.SHOOTING,
        )
    )
    assert close_profile.strength.final == close_base.strength.final + 1
    assert close_profile.armor_penetration.final == close_base.armor_penetration.final - 1
    assert GameLifecycle.from_payload(close_lifecycle.to_payload()).to_payload() == (
        close_lifecycle.to_payload()
    )


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyMusterRequest", "BattleFormationRequestContext"]
__all__ += ["CHARGE_FIGHTS_FIRST_EFFECT_KIND", "BattlePhaseKind", "CommandPointGainStatus"]
__all__ += ["CommandPointSourceKind", "DatasheetKeywordSet", "DetachmentDefinition"]
__all__ += ["DetachmentSelection", "EffectExpiration", "EnhancementAssignment"]
__all__ += ["EnhancementDefinition", "FactionDefinition", "FactionRuleExecutionContext"]
__all__ += ["FactionRuleExecutionResult", "FactionRuleExecutionStatus", "FightPhaseState"]
__all__ += ["FightsFirstRegistry", "GameConfig", "GameLifecycleError", "GameLifecycleStage"]
__all__ += ["GameState", "JsonValue", "LifecycleStatus", "MissionSetup", "ModelProfileSelection"]
__all__ += ["PersistingEffect", "Phase17FExecutionStatus", "Pose", "ReactionQueue"]
__all__ += ["RulesetDescriptor", "RuntimeContentBundle", "SecondaryMissionChoice"]
__all__ += ["SecondaryMissionMode", "SetupStep", "ShootingPhaseState"]
__all__ += ["ShootingTargetRestrictionContext", "ShootingType", "StratagemDefinition"]
__all__ += ["StratagemUseRecord", "UnitMusterSelection", "WeaponProfile"]
__all__ += ["_COURT_ENHANCEMENT_EXECUTION_IDS", "WeaponProfileModifierContext"]
__all__ += ["_COURT_GENERIC_EXECUTION_IDS", "_MORE_DAKKA_ENHANCEMENT_EXECUTION_IDS"]
__all__ += ["_MORE_DAKKA_GENERIC_EXECUTION_IDS", "_SPECTACLE_ENHANCEMENT_EXECUTION_IDS"]
__all__ += ["_SPECTACLE_GENERIC_EXECUTION_IDS", "_apply_battle_formation_hooks_from_bundle"]
__all__ += ["_clear_terrain", "_court_blade_profile", "_court_datasheet_id_for_selection"]
__all__ += ["_court_lifecycle_config", "_court_stratagem", "_court_stratagem_decision_result"]
__all__ += ["_effect_parameter", "_mission_setup", "_more_dakka_catalog"]
__all__ += ["_more_dakka_lifecycle_config", "_more_dakka_muster_request", "_more_dakka_stratagem"]
__all__ += ["_more_dakka_stratagem_decision_result", "_record_charge_move_effect"]
__all__ += ["_record_fixed_secondary_choices_for_fixture", "_replace_unit_poses"]
__all__ += ["_spectacle_catalog", "_spectacle_lifecycle_config", "_spectacle_muster_request"]
__all__ += ["_spectacle_stratagem", "_spectacle_stratagem_decision_result"]
__all__ += ["apply_stratagem_decision", "chapter_approved_2026_27_mission_pack"]
__all__ += ["create_deterministic_battlefield_scenario", "enter_battle_for_fixture"]
