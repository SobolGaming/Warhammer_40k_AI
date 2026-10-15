from __future__ import annotations

from typing import Any, cast

from tests.shared.category_migration.phase17d_rule_execution import (
    CATALOG_SETUP_REACTIVE_SOURCE_KIND,
    CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
    FIGHTS_FIRST_CHARGE_EFFECT_KIND,
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    ONCE_PER_BATTLE_FIGHT_BOOST_TEXT,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    RULE_FREQUENCY_LIMIT_CONSUMED_EVENT,
    SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE,
    SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE,
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
    SELECTED_TARGET_UNIT_CONTEXT_KEY,
    SETUP_REACTIVE_SHOOT_CHARGE_TEXT,
    SOURCE_KEYWORD_SEQUENCE_PARTS,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilityExecutionContext,
    AbilityResolutionStatus,
    AbilitySourceKind,
    AbilityTimingDescriptor,
    ArmyCatalog,
    ArmyDefinition,
    ArmyMusterRequest,
    AttachmentDeclaration,
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    BattlePhase,
    BattlePhaseKind,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogDatasheetRuleRuntime,
    CatalogJsonObject,
    ChargeMoveProposal,
    ChargeTargetRestrictionHookRegistry,
    CommandPointLedger,
    CommandPointRuleMutationResult,
    CommandPointSourceKind,
    CompiledRuleSource,
    DatasheetAbilityDescriptor,
    DecisionController,
    DecisionOption,
    DecisionRequest,
    DecisionResult,
    DetachmentSelection,
    EffectError,
    EffectExpiration,
    EventLog,
    EventStreamCursor,
    GameConfig,
    GameLifecycle,
    GameLifecycleError,
    GameLifecycleStage,
    GameState,
    HitRollModifierContext,
    JsonValue,
    KeywordGate,
    LifecycleStatusKind,
    LocalGameSession,
    MissionSetup,
    ModelInstance,
    ModelProfileSelection,
    MovementMode,
    MovementProposalRequest,
    ObjectiveRuleScope,
    ParameterizedSubmission,
    PathWitness,
    Pose,
    ProposalKind,
    ReactionQueue,
    ReactionWindow,
    ReplayRunner,
    ReplayRunStatus,
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleExecutionContext,
    RuleExecutionRegistry,
    RuleExecutionResult,
    RuleExecutionStatus,
    RuleIR,
    RuleIRError,
    RuleIRPayload,
    RuleParameter,
    RuleRuntimeBinding,
    RulesetDescriptor,
    RuleSourceText,
    RuleTrigger,
    RuleTriggerKind,
    RuntimeModifierRegistry,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    TextSpan,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
    UnitInstance,
    UnitMusterSelection,
    UnitPlacement,
    WeaponKeyword,
    WeaponProfile,
    WeaponProfileModifierContext,
    WoundRollModifierContext,
    _ability_record,
    _append_setup_reactive_arrival_event,
    _attached_leader_support_muster_request,
    _battle_state,
    _battle_state_with_attached_leader_support,
    _battle_state_with_extra_friendly_unit,
    _battle_state_with_scenario,
    _bodyguard_destroyed_attached_state,
    _catalog_with_champion_slayer_ability,
    _catalog_with_descriptor,
    _champion_slayer_ability_index,
    _champion_slayer_clause_record,
    _champion_slayer_descriptor,
    _champion_slayer_rule_ir,
    _command_point_spend_rule_ir,
    _compiled,
    _desperate_escape_modifier_rule_ir,
    _destroy_model,
    _event_payloads,
    _execution_context,
    _generic_catalog_descriptor,
    _json_object,
    _mission_setup,
    _muster_request,
    _muster_request_with_unit_ids,
    _mustered_armies,
    _mustered_armies_with_extra_friendly_unit,
    _next_psychic_request,
    _non_reaction_movement_request,
    _non_reaction_placement_request,
    _noop_rule_handler,
    _parameterized_result_for_request,
    _path_witness_for_unit_delta,
    _psychic_level_session,
    _reaction_queue_consistency_fixture,
    _reaction_queue_window,
    _record_decision_result,
    _request_setup_reactive_lifecycle_action,
    _rule_ir_with_aura_object_reference,
    _scenario,
    _scenario_with_extra_friendly_unit,
    _set_model_wounds,
    _setup_reactive_charge_move_request,
    _setup_reactive_config,
    _setup_reactive_lifecycle,
    _setup_reactive_single_model_state,
    _skullmaster_fury_text,
    _unit_by_id,
    _weapon_profile,
    _with_unit_keywords,
    _with_unit_model_poses,
    _with_unit_pose,
    apply_catalog_setup_reactive_charge_move,
    apply_catalog_setup_reactive_shoot_charge_result,
    apply_command_point_rule_mutation,
    build_player_ability_index,
    catalog_ability_records_from_catalog,
    catalog_restore_lost_wounds_after_destroying_unit,
    catalog_wound_roll_reroll_permission_for_attack,
    chapter_approved_2026_27_mission_pack,
    command_point_operation_and_delta,
    command_point_operation_shape_reason,
    command_point_rule_unavailable_reason,
    compile_rule_source_text,
    copy,
    create_deterministic_battlefield_scenario,
    datasheet_keyword_lexicon_source,
    default_ability_handler_registry,
    default_rule_execution_registry,
    destroy_model_by_rule,
    ensure_army_mustered_events_for_fixture,
    execute_abilities_from_index,
    execute_rule_ir,
    generic_rule_persisting_effect,
    generic_rule_wound_roll_modifier,
    hashlib,
    initial_command_point_ledgers,
    initial_victory_point_ledgers,
    invalid_catalog_setup_reactive_charge_move_status,
    invalid_catalog_setup_reactive_shoot_charge_status,
    is_catalog_setup_reactive_charge_move_request,
    json,
    muster_army,
    parameter_payload,
    psychic_uses,
    pytest,
    replace,
    request_catalog_setup_reactive_shoot_charge_if_available,
    rule_execution_status_from_token,
    rule_ir_from_execution_payload,
    rules_unit_persisting_effects,
    scoped_rule_ir_from_execution_payload,
    stratagem_decline_payload,
    validate_json_value,
    validate_reaction_queue_consistency,
    with_unit_keywords,
)


def test_phase17d_once_per_battle_activation_consumes_and_modifies_source_model() -> None:
    state = _battle_state_with_attached_leader_support()
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    source_unit = _unit_by_id(state, "army-alpha:leader-unit")
    source_model = source_unit.own_models[0]
    source_rules_unit_id = "attached-unit:army-alpha:bodyguard-unit"
    event_log = EventLog()
    compiled = _compiled(ONCE_PER_BATTLE_FIGHT_BOOST_TEXT)
    context = _execution_context(
        state=state,
        event_log=event_log,
        source_unit_instance_id=source_rules_unit_id,
        source_model_instance_id=source_model.model_instance_id,
        phase=BattlePhaseKind.FIGHT,
    )

    missing_log = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=replace(context, event_log=None),
    )
    applied = execute_rule_ir(rule_ir=compiled.rule_ir, context=context)
    effect_count = len(state.persisting_effects)
    repeated = execute_rule_ir(rule_ir=compiled.rule_ir, context=context)

    assert missing_log.status is RuleExecutionStatus.INVALID
    assert missing_log.reason == "missing_input:event_log"
    assert applied.status is RuleExecutionStatus.APPLIED
    assert len(applied.effect_payloads) == 2
    assert len(state.persisting_effects) == 2
    assert [
        event.event_type
        for event in event_log.records
        if event.event_type == RULE_FREQUENCY_LIMIT_CONSUMED_EVENT
    ] == [RULE_FREQUENCY_LIMIT_CONSUMED_EVENT]
    assert EventLog.from_payload(event_log.to_payload()).to_payload() == event_log.to_payload()
    assert repeated.status is RuleExecutionStatus.INVALID
    assert repeated.reason == "frequency_limit_exhausted:battle"
    assert len(state.persisting_effects) == effect_count

    profile = _weapon_profile("core-leader-blade")
    modified = RuntimeModifierRegistry.empty().modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.FIGHT,
            attacking_unit_instance_id=source_rules_unit_id,
            attacker_model_instance_id=source_model.model_instance_id,
            target_unit_instance_id="army-alpha:bodyguard-unit",
            weapon_profile=profile,
        )
    )

    assert profile.attack_profile.fixed_attacks == 5
    assert modified.attack_profile.fixed_attacks == 8
    assert WeaponKeyword.DEVASTATING_WOUNDS in modified.keywords


def test_phase17d_target_scoped_effect_requires_target_binding() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_target:unit_instance_ids"
    assert result.effect_payloads == ()
    assert result.event_records == ()


def test_phase17d_this_unit_effect_uses_source_unit_binding() -> None:
    source_unit_id = "army-alpha:intercessor-unit-1"
    unrelated_target_unit_id = "army-beta:intercessor-unit-2"
    compiled = _compiled("This unit can be set up more than 9 inches away from enemy units.")

    missing_source = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            record_persisting_effects=False,
        ),
        registry=default_rule_execution_registry(),
    )
    explicit_target_without_source = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            record_persisting_effects=False, target_unit_instance_ids=(unrelated_target_unit_id,)
        ),
        registry=default_rule_execution_registry(),
    )
    applied = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            record_persisting_effects=False,
            source_unit_instance_id=source_unit_id,
            target_unit_instance_ids=(unrelated_target_unit_id,),
        ),
        registry=default_rule_execution_registry(),
    )

    assert missing_source.status is RuleExecutionStatus.INVALID
    assert missing_source.reason == "missing_input:source_unit_instance_id"
    assert explicit_target_without_source.status is RuleExecutionStatus.INVALID
    assert explicit_target_without_source.reason == "missing_input:source_unit_instance_id"
    assert applied.status is RuleExecutionStatus.APPLIED
    assert applied.effect_payloads[0]["target_unit_instance_ids"] == [source_unit_id]


def test_phase17d_optional_wargear_bearer_unit_effects_execute_generically() -> None:
    source_unit_id = "army-alpha:bloodletters-1"
    icon = _compiled("Models in the bearer's unit have a Leadership characteristic of 6+.")
    instrument = _compiled("Add 1 to Charge rolls made for the bearer's unit.")

    icon_result = execute_rule_ir(
        rule_ir=icon.rule_ir,
        context=_execution_context(
            record_persisting_effects=False, source_unit_instance_id=source_unit_id
        ),
        registry=default_rule_execution_registry(),
    )
    instrument_result = execute_rule_ir(
        rule_ir=instrument.rule_ir,
        context=_execution_context(
            record_persisting_effects=False, source_unit_instance_id=source_unit_id
        ),
        registry=default_rule_execution_registry(),
    )

    assert icon_result.status is RuleExecutionStatus.APPLIED
    assert icon_result.effect_payloads[0]["target_unit_instance_ids"] == [source_unit_id]
    assert _json_object(icon_result.effect_payloads[0]["effect"])["parameters"] == [
        {"key": "characteristic", "value": "leadership"},
        {"key": "value", "value": "6+"},
    ]
    assert instrument_result.status is RuleExecutionStatus.APPLIED
    assert instrument_result.effect_payloads[0]["target_unit_instance_ids"] == [source_unit_id]
    assert _json_object(instrument_result.effect_payloads[0]["effect"])["parameters"] == [
        {"key": "delta", "value": 1},
        {"key": "roll_type", "value": "charge"},
    ]


def test_phase17d_generic_reroll_permission_executes() -> None:
    compiled = _compiled("After a hit roll, re-roll hit rolls.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            trigger_payload={"roll_type": "hit"},
            target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        ),
        registry=default_rule_execution_registry(),
    )
    effect = _json_object(result.effect_payloads[0]["effect"])

    assert result.status is RuleExecutionStatus.APPLIED
    assert effect["kind"] == "reroll_permission"
    assert effect["parameters"] == [{"key": "roll_type", "value": "hit"}]


def test_phase17d_once_per_battle_activation_submits_through_local_session_and_replays() -> None:
    catalog = _catalog_with_descriptor(
        _generic_catalog_descriptor(
            ONCE_PER_BATTLE_FIGHT_BOOST_TEXT,
            ability_id="once-per-battle-fight-boost",
        )
    )
    config = _setup_reactive_config(catalog)
    armies = tuple(
        muster_army(catalog=catalog, request=request) for request in config.army_muster_requests
    )
    state = _battle_state()
    for army in armies:
        state.record_army_definition(army)
    state.battlefield_state = create_deterministic_battlefield_scenario(
        battlefield_id="phase17d-once-per-battle",
        armies=armies,
    ).battlefield_state
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    session = LocalGameSession(lifecycle=_setup_reactive_lifecycle(state=state, catalog=catalog))

    request = _next_psychic_request(session)
    assert request is not None
    assert request.decision_type == SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE
    use_option = next(
        option for option in request.options if _json_object(option.payload)["activate"] is True
    )
    malformed = replace(
        DecisionResult.for_request(
            result_id="phase17d:once-per-battle:malformed",
            request=request,
            selected_option_id=use_option.option_id,
        ),
        payload={},
    )
    malformed_status = session.lifecycle.submit_decision(malformed)
    assert malformed_status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.pending_decision_request() == request
    assert session.lifecycle.state is not None
    assert not session.lifecycle.state.persisting_effects

    submitted = session.submit_option(
        request_id=request.request_id,
        option_id=use_option.option_id,
        result_id="phase17d:once-per-battle:local-session",
    )

    assert submitted.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    second_request = _next_psychic_request(session)
    assert second_request is not None
    second_use_option = next(
        option
        for option in second_request.options
        if _json_object(option.payload)["activate"] is True
    )
    second_submitted = session.submit_option(
        request_id=second_request.request_id,
        option_id=second_use_option.option_id,
        result_id="phase17d:once-per-battle:local-session:second-model",
    )
    assert second_submitted.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert session.lifecycle.state is not None
    assert len(session.lifecycle.state.persisting_effects) == 4
    assert len({effect.effect_id for effect in session.lifecycle.state.persisting_effects}) == 4
    player_a_events = session.events_since(EventStreamCursor(), viewer_player_id="player-a")
    player_b_events = session.events_since(EventStreamCursor(), viewer_player_id="player-b")
    player_a_activations = [
        event
        for event in player_a_events["events"]
        if event["event_type"] == "catalog_once_per_battle_ability_activated"
    ]
    player_b_activations = [
        event
        for event in player_b_events["events"]
        if event["event_type"] == "catalog_once_per_battle_ability_activated"
    ]
    assert player_a_activations == player_b_activations
    assert len(player_a_activations) == 2
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="replay:once-per-battle:fight-boost")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


def test_phase17d_player_ability_index_filters_selected_source_records() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    army = _mustered_armies()[0]
    army = replace(
        army,
        detachment_selection=replace(
            army.detachment_selection,
            enhancement_ids=("selected-enhancement",),
        ),
    )
    records = (
        _ability_record("core", AbilitySourceKind.CORE),
        _ability_record(
            "keyword-infantry",
            AbilitySourceKind.KEYWORD,
            keyword_gate=KeywordGate(required_keywords=("Infantry",)),
        ),
        _ability_record(
            "keyword-vehicle",
            AbilitySourceKind.KEYWORD,
            keyword_gate=KeywordGate(required_keywords=("Vehicle",)),
        ),
        _ability_record(
            "faction-match",
            AbilitySourceKind.FACTION,
            faction_id="core-marine-force",
        ),
        _ability_record("faction-miss", AbilitySourceKind.FACTION, faction_id="other-faction"),
        _ability_record(
            "detachment-match",
            AbilitySourceKind.DETACHMENT,
            detachment_id="core-combined-arms",
        ),
        _ability_record(
            "detachment-miss",
            AbilitySourceKind.DETACHMENT,
            detachment_id="other-detachment",
        ),
        _ability_record(
            "enhancement-match",
            AbilitySourceKind.ENHANCEMENT,
            detachment_id="core-combined-arms",
            ability_id="selected-enhancement",
        ),
        _ability_record(
            "enhancement-miss",
            AbilitySourceKind.ENHANCEMENT,
            detachment_id="core-combined-arms",
            ability_id="unselected-enhancement",
        ),
        _ability_record(
            "datasheet-match",
            AbilitySourceKind.DATASHEET,
            datasheet_id="core-intercessor-like-infantry",
        ),
        _ability_record(
            "datasheet-miss",
            AbilitySourceKind.DATASHEET,
            datasheet_id="other-datasheet",
        ),
        _ability_record("wargear-match", AbilitySourceKind.WARGEAR, wargear_id="core-bolt-rifle"),
        _ability_record("wargear-miss", AbilitySourceKind.WARGEAR, wargear_id="other-wargear"),
        _ability_record(
            "weapon-profile-match",
            AbilitySourceKind.WEAPON,
            weapon_profile_id="core-bolt-rifle:standard",
        ),
        _ability_record(
            "weapon-profile-miss",
            AbilitySourceKind.WEAPON,
            weapon_profile_id="other-profile",
        ),
        _ability_record(
            "weapon-keyword-match",
            AbilitySourceKind.WEAPON,
            keyword_gate=KeywordGate(required_keywords=("Assault",)),
        ),
        _ability_record(
            "weapon-keyword-miss",
            AbilitySourceKind.WEAPON,
            keyword_gate=KeywordGate(required_keywords=("Lance",)),
        ),
    )

    with_catalog = {
        record.record_id
        for record in build_player_ability_index(records, army=army, catalog=catalog).all_records()
    }
    without_catalog = {
        record.record_id for record in build_player_ability_index(records, army=army).all_records()
    }

    assert with_catalog == {
        "core",
        "datasheet-match",
        "detachment-match",
        "enhancement-match",
        "faction-match",
        "keyword-infantry",
        "wargear-match",
        "weapon-keyword-match",
        "weapon-profile-match",
    }
    assert without_catalog == with_catalog - {
        "weapon-keyword-match",
        "weapon-profile-match",
    }
    with pytest.raises(GameLifecycleError, match="requires an ArmyDefinition"):
        build_player_ability_index((), army=cast(ArmyDefinition, object()))
    with pytest.raises(GameLifecycleError, match="catalog must be an ArmyCatalog"):
        build_player_ability_index((), army=army, catalog=cast(ArmyCatalog, object()))


def test_phase17d_champion_slayer_heal_does_not_revive_after_source_model_is_full() -> None:
    state = _battle_state_with_scenario()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    source_model = unit.own_models[0]
    destroyed_model = unit.own_models[1]
    ability_index = _champion_slayer_ability_index(datasheet_id=unit.datasheet_id)
    _set_model_wounds(
        state,
        model_instance_id=source_model.model_instance_id,
        wounds_remaining=source_model.initial_wounds - 1,
    )
    _destroy_model(state, model_instance_id=destroyed_model.model_instance_id)
    wounded_unit = _unit_by_id(state, unit.unit_instance_id)

    resolved = catalog_restore_lost_wounds_after_destroying_unit(
        state=state,
        decisions=DecisionController(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        ability_index=ability_index,
        unit=wounded_unit,
        current_model_instance_ids=(source_model.model_instance_id,),
        player_id="player-a",
        destroyed_player_id="player-b",
        destroyed_unit_keywords=("CHARACTER",),
        healing_amount=3,
        source_event_id="event:enemy-character-destroyed",
    )

    assert resolved is not None
    effect, request = resolved
    assert request is None
    assert effect.amount == 1
    assert len(effect.resolved_steps) == 1
    resolved_unit = _unit_by_id(state, unit.unit_instance_id)
    assert resolved_unit.own_models[0].current_wounds == source_model.initial_wounds
    assert resolved_unit.own_models[1].current_wounds == 0
    assert state.battlefield_state is not None
    assert destroyed_model.model_instance_id in state.battlefield_state.removed_model_ids


def test_phase17d_champion_slayer_heal_ignores_other_wounded_model_when_source_full() -> None:
    state = _battle_state_with_scenario()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    source_model = unit.own_models[0]
    other_model = unit.own_models[1]
    ability_index = _champion_slayer_ability_index(datasheet_id=unit.datasheet_id)
    _set_model_wounds(
        state,
        model_instance_id=other_model.model_instance_id,
        wounds_remaining=other_model.initial_wounds - 1,
    )
    wounded_unit = _unit_by_id(state, unit.unit_instance_id)

    resolved = catalog_restore_lost_wounds_after_destroying_unit(
        state=state,
        decisions=DecisionController(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        ability_index=ability_index,
        unit=wounded_unit,
        current_model_instance_ids=(source_model.model_instance_id,),
        player_id="player-a",
        destroyed_player_id="player-b",
        destroyed_unit_keywords=("MONSTER",),
        healing_amount=3,
        source_event_id="event:enemy-monster-destroyed",
    )

    resolved_unit = _unit_by_id(state, unit.unit_instance_id)
    assert resolved is None
    assert resolved_unit.own_models[0].current_wounds == source_model.initial_wounds
    assert resolved_unit.own_models[1].current_wounds == other_model.initial_wounds - 1


def test_phase17d_champion_slayer_heals_source_among_multiple_wounded_models() -> None:
    state = _battle_state_with_scenario()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    source_model = unit.own_models[0]
    other_model = unit.own_models[1]
    ability_index = _champion_slayer_ability_index(datasheet_id=unit.datasheet_id)
    _set_model_wounds(
        state,
        model_instance_id=source_model.model_instance_id,
        wounds_remaining=source_model.initial_wounds - 1,
    )
    _set_model_wounds(
        state,
        model_instance_id=other_model.model_instance_id,
        wounds_remaining=other_model.initial_wounds - 1,
    )
    wounded_unit = _unit_by_id(state, unit.unit_instance_id)

    catalog_restore_lost_wounds_after_destroying_unit(
        state=state,
        decisions=DecisionController(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        ability_index=ability_index,
        unit=wounded_unit,
        current_model_instance_ids=(source_model.model_instance_id,),
        player_id="player-a",
        destroyed_player_id="player-b",
        destroyed_unit_keywords=("MONSTER",),
        healing_amount=3,
        source_event_id="event:enemy-monster-destroyed",
    )
    healed_unit = _unit_by_id(state, unit.unit_instance_id)
    assert healed_unit.own_models[0].current_wounds == source_model.initial_wounds
    assert healed_unit.own_models[1].current_wounds == other_model.initial_wounds - 1


def test_phase17d_champion_slayer_restore_clause_executes_to_generic_payload() -> None:
    state = _battle_state_with_scenario()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    ability_index = _champion_slayer_ability_index(datasheet_id=unit.datasheet_id)

    results = execute_abilities_from_index(
        registry=default_ability_handler_registry(),
        index=ability_index,
        context=AbilityExecutionContext(
            game_id="phase17d-game",
            player_id="player-a",
            battle_round=1,
            phase=None,
            active_player_id="player-a",
            trigger_kind=TimingTriggerKind.AFTER_UNIT_DESTROYED,
            source_unit_instance_id=unit.unit_instance_id,
            source_model_instance_id=unit.own_models[0].model_instance_id,
            trigger_payload={"destroyed_unit_keywords": ["MONSTER"]},
            state=state,
        ),
    )

    assert len(results) == 1
    assert results[0].status is AbilityResolutionStatus.APPLIED
    replay_payload = cast(dict[str, JsonValue], results[0].replay_payload)
    execution_payload = cast(dict[str, JsonValue], replay_payload["rule_execution"])
    effect_payloads = cast(list[JsonValue], execution_payload["effect_payloads"])
    first_effect_payload = cast(dict[str, JsonValue], effect_payloads[0])
    effect = cast(dict[str, JsonValue], first_effect_payload["effect"])
    assert effect["kind"] == "restore_lost_wounds"


def test_phase17d_champion_slayer_heal_ignores_nonqualifying_destroyed_units() -> None:
    state = _battle_state_with_scenario()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    model = unit.own_models[0]
    ability_index = _champion_slayer_ability_index(datasheet_id=unit.datasheet_id)
    _set_model_wounds(state, model_instance_id=model.model_instance_id, wounds_remaining=1)
    wounded_unit = _unit_by_id(state, unit.unit_instance_id)

    non_keyword = catalog_restore_lost_wounds_after_destroying_unit(
        state=state,
        decisions=DecisionController(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        ability_index=ability_index,
        unit=wounded_unit,
        current_model_instance_ids=(model.model_instance_id,),
        player_id="player-a",
        destroyed_player_id="player-b",
        destroyed_unit_keywords=("INFANTRY",),
        healing_amount=3,
        source_event_id="event:enemy-infantry-destroyed",
    )
    friendly_destroyed = catalog_restore_lost_wounds_after_destroying_unit(
        state=state,
        decisions=DecisionController(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        ability_index=ability_index,
        unit=wounded_unit,
        current_model_instance_ids=(model.model_instance_id,),
        player_id="player-a",
        destroyed_player_id="player-a",
        destroyed_unit_keywords=("CHARACTER",),
        healing_amount=3,
        source_event_id="event:friendly-character-destroyed",
    )

    assert non_keyword is None
    assert friendly_destroyed is None
    assert _unit_by_id(state, unit.unit_instance_id).own_models[0].current_wounds == 1


def test_phase17d_generic_vp_scoring_rule_mutates_victory_point_ledger() -> None:
    state = _battle_state()
    event_log = EventLog()
    compiled = _compiled("When this unit is destroyed, score 5VP.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, event_log=event_log),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert state.victory_point_total("player-a") == 5
    assert result.victory_point_transactions[0]["amount"] == 5
    assert result.victory_point_transactions[0]["source_id"] == compiled.rule_ir.source_id
    assert event_log.records[-1].event_type == "rule_execution_victory_points_awarded"


def test_phase17d_generic_cp_rule_mutates_command_point_ledger_and_reports_cap() -> None:
    state = _battle_state()
    event_log = EventLog()
    compiled = _compiled("Gain 1CP and score 3VP.")

    first = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, event_log=event_log),
        registry=default_rule_execution_registry(),
    )
    event_count_after_first = len(event_log.records)
    capped = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, event_log=event_log),
        registry=default_rule_execution_registry(),
    )

    assert first.status is RuleExecutionStatus.APPLIED
    assert state.command_point_total("player-a") == 1
    assert state.victory_point_total("player-a") == 3
    assert first.command_point_transactions[0]["status"] == "applied"
    assert first.command_point_transactions[0]["applied_amount"] == 1
    assert capped.status is RuleExecutionStatus.INVALID
    assert capped.reason == "command_point_gain_capped"
    assert state.command_point_total("player-a") == 1
    assert state.victory_point_total("player-a") == 3
    assert len(event_log.records) == event_count_after_first


def test_phase17d_oversized_generic_cp_gain_applies_only_remaining_round_capacity() -> None:
    state = _battle_state()
    event_log = EventLog()
    compiled = _compiled("Gain 3CP.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, event_log=event_log),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert state.command_point_total("player-a") == 1
    transaction = result.command_point_transactions[0]
    assert transaction["status"] == "capped"
    assert transaction["requested_amount"] == 3
    assert transaction["applied_amount"] == 1
    assert transaction["capped_reason"] == "non_command_cp_gain_cap_reached"


def test_phase17d_later_invalid_effect_does_not_leave_prior_mutation() -> None:
    state = _battle_state()
    event_log = EventLog()
    compiled = _compiled("Gain 1CP and score 3VP.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, event_log=event_log, phase=None),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_phase"
    assert state.command_point_total("player-a") == 0
    assert state.victory_point_total("player-a") == 0
    assert event_log.records == ()


def test_phase17d_generic_cp_spend_rule_uses_command_point_ledger() -> None:
    spend_rule_ir = _command_point_spend_rule_ir()
    insufficient_state = _battle_state()
    funded_state = _battle_state()
    funded_state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="phase17d:seed-cp",
        source_kind=CommandPointSourceKind.OTHER,
        cap_exempt=True,
    )

    insufficient = execute_rule_ir(
        rule_ir=spend_rule_ir,
        context=_execution_context(state=insufficient_state),
        registry=default_rule_execution_registry(),
    )
    applied = execute_rule_ir(
        rule_ir=spend_rule_ir,
        context=_execution_context(state=funded_state),
        registry=default_rule_execution_registry(),
    )

    assert insufficient.status is RuleExecutionStatus.INVALID
    assert insufficient.reason == "insufficient_command_points"
    assert insufficient_state.command_point_total("player-a") == 0
    assert applied.status is RuleExecutionStatus.APPLIED
    assert funded_state.command_point_total("player-a") == 0
    assert applied.command_point_transactions[0]["status"] == "applied"
    assert applied.command_point_transactions[0]["applied_amount"] == 1


def test_phase17d_command_point_mutation_helper_is_strict_and_simulates_refunds() -> None:
    state = _battle_state()
    effect = _compiled("Gain 1CP.").rule_ir.clauses[0].effects[0]

    assert command_point_operation_and_delta(effect) == ("gain", 1)
    with pytest.raises(GameLifecycleError, match="exactly one payload or reason"):
        CommandPointRuleMutationResult()
    with pytest.raises(GameLifecycleError, match="requires RuleEffectSpec"):
        command_point_operation_and_delta(cast(Any, object()))
    with pytest.raises(GameLifecycleError, match="operation must be a string"):
        command_point_operation_and_delta(replace(effect, parameters=(RuleParameter("delta", 1),)))
    with pytest.raises(GameLifecycleError, match="delta must be an integer"):
        command_point_operation_and_delta(
            replace(
                effect,
                parameters=(
                    RuleParameter("delta", "one"),
                    RuleParameter("operation", "gain"),
                ),
            )
        )

    invalid = apply_command_point_rule_mutation(
        state=state,
        player_id="player-a",
        source_id="phase17d:test:invalid-cp",
        operation="gain",
        delta=-1,
    )
    first_refund = apply_command_point_rule_mutation(
        state=state,
        player_id="player-a",
        source_id="phase17d:test:refund-one",
        operation="refund",
        delta=1,
    )
    capped_refund = apply_command_point_rule_mutation(
        state=state,
        player_id="player-a",
        source_id="phase17d:test:refund-two",
        operation="refund",
        delta=1,
    )

    assert invalid.reason == "invalid_command_point_gain_delta"
    assert first_refund.transaction_payload is not None
    assert first_refund.transaction_payload["source_kind"] == "stratagem_refund"
    assert capped_refund.reason == "command_point_refund_capped"

    simulation_state = _battle_state()
    simulated_ledgers: dict[str, CommandPointLedger] = {}
    assert (
        command_point_rule_unavailable_reason(
            state=simulation_state,
            player_id="player-a",
            source_id="phase17d:test:simulated-refund",
            operation="refund",
            delta=1,
            simulated_ledgers=simulated_ledgers,
        )
        is None
    )
    assert (
        command_point_rule_unavailable_reason(
            state=simulation_state,
            player_id="player-a",
            source_id="phase17d:test:simulated-refund-capped",
            operation="refund",
            delta=1,
            simulated_ledgers=simulated_ledgers,
        )
        == "command_point_refund_capped"
    )
    assert (
        command_point_rule_unavailable_reason(
            state=simulation_state,
            player_id="player-a",
            source_id="phase17d:test:simulated-spend",
            operation="spend",
            delta=-1,
            simulated_ledgers=simulated_ledgers,
        )
        is None
    )
    assert (
        command_point_rule_unavailable_reason(
            state=simulation_state,
            player_id="player-b",
            source_id="phase17d:test:simulated-insufficient",
            operation="spend",
            delta=-1,
            simulated_ledgers=simulated_ledgers,
        )
        == "insufficient_command_points"
    )

    assert command_point_operation_shape_reason(operation="gain", delta=0) == (
        "zero_command_point_delta"
    )
    assert (
        command_point_operation_shape_reason(operation="modify_stratagem_cost", delta=1)
        == "stratagem_cost_context_required"
    )
    assert command_point_operation_shape_reason(operation="refund", delta=-1) == (
        "invalid_command_point_refund_delta"
    )
    assert command_point_operation_shape_reason(operation="spend", delta=1) == (
        "invalid_command_point_spend_delta"
    )
    assert command_point_operation_shape_reason(operation="unknown", delta=1) == (
        "unsupported_command_point_operation:unknown"
    )


def test_phase17d_duration_effect_records_generic_persisting_effect() -> None:
    state = _battle_state_with_scenario()
    target_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled("That unit gains Stealth until the end of the phase.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            target_unit_instance_ids=(target_unit_id,),
        ),
        registry=default_rule_execution_registry(),
    )
    effect = result.created_persisting_effects[0]
    payload = effect.to_payload()
    effect_payload = _json_object(payload["effect_payload"])

    assert result.status is RuleExecutionStatus.APPLIED
    assert state.persisting_effects_for_unit(target_unit_id) == (effect,)
    assert payload["started_phase"] == "command"
    assert payload["expiration"]["expiration_kind"] == "end_phase"
    assert effect_payload["effect_kind"] == "generic_rule_execution"


@pytest.mark.parametrize(
    ("raw_text", "expected_expiration_kind"),
    [
        ("That unit gains Stealth until the end of the turn.", "end_turn"),
        ("That unit gains Stealth until the end of the battle.", "end_of_battle"),
    ],
)
def test_phase17d_duration_endpoint_variants_record_persisting_effects(
    raw_text: str,
    expected_expiration_kind: str,
) -> None:
    state = _battle_state_with_scenario()
    target_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled(raw_text)

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            target_unit_instance_ids=(target_unit_id,),
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert len(result.created_persisting_effects) == 1
    assert (
        result.created_persisting_effects[0].to_payload()["expiration"]["expiration_kind"]
        == expected_expiration_kind
    )


def test_phase17d_current_phase_duration_expires_on_active_player_boundary() -> None:
    state = _battle_state_with_scenario()
    state.active_player_id = "player-b"
    target_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled("That unit gains Stealth until the end of the phase.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            target_unit_instance_ids=(target_unit_id,),
            phase=BattlePhaseKind.SHOOTING,
            active_player_id="player-b",
        ),
        registry=default_rule_execution_registry(),
    )
    expiration = result.created_persisting_effects[0].expiration

    assert result.status is RuleExecutionStatus.APPLIED
    assert expiration.expiration_kind.value == "end_phase"
    assert expiration.player_id == "player-b"
    assert expiration.phase is BattlePhaseKind.SHOOTING


@pytest.mark.parametrize(
    ("raw_text", "phase", "active_player_id", "expected_expiration"),
    [
        (
            "That unit has the Stealth ability until your next Command phase.",
            BattlePhaseKind.SHOOTING,
            "player-a",
            {
                "expiration_kind": "start_phase",
                "battle_round": 2,
                "phase": "command",
                "player_id": "player-a",
            },
        ),
        (
            "That unit has the Stealth ability until the end of your next turn.",
            BattlePhaseKind.SHOOTING,
            "player-a",
            {
                "expiration_kind": "end_turn",
                "battle_round": 2,
                "phase": None,
                "player_id": "player-a",
            },
        ),
        (
            "That unit has the Stealth ability until the start of opponent's next turn.",
            BattlePhaseKind.SHOOTING,
            "player-a",
            {
                "expiration_kind": "start_turn",
                "battle_round": 1,
                "phase": None,
                "player_id": "player-b",
            },
        ),
    ],
)
def test_phase17d_relative_duration_endpoints_record_lifecycle_expiration(
    raw_text: str,
    phase: BattlePhaseKind,
    active_player_id: str,
    expected_expiration: dict[str, object],
) -> None:
    state = _battle_state_with_scenario()
    state.active_player_id = active_player_id
    target_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled(raw_text)

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            target_unit_instance_ids=(target_unit_id,),
            phase=phase,
            active_player_id=active_player_id,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.created_persisting_effects[0].expiration.to_payload() == expected_expiration


def test_phase17d_phase_duration_requires_phase_before_mutation() -> None:
    state = _battle_state_with_scenario()
    event_log = EventLog()
    target_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled("That unit gains Stealth until the end of the phase.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            event_log=event_log,
            target_unit_instance_ids=(target_unit_id,),
            phase=None,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_phase"
    assert state.persisting_effects_for_unit(target_unit_id) == ()
    assert event_log.records == ()


def test_phase17d_duration_effect_requires_state_before_applying() -> None:
    target_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled("That unit gains Stealth until the end of the phase.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            target_unit_instance_ids=(target_unit_id,),
            phase=BattlePhaseKind.COMMAND,
            state=None,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_input:game_state"
    assert result.effect_payloads == ()
    assert result.created_persisting_effects == ()


def test_phase17d_handler_invalid_result_propagates_without_merge_exception() -> None:
    state = _battle_state()
    compiled = _compiled("When this unit is destroyed, score 5VP.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, phase=None),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_phase"
    assert state.victory_point_total("player-a") == 0


def test_phase17d_selected_target_binding_uses_trigger_payload_when_unbound() -> None:
    compiled = _compiled("One friendly unit that was selected as the target.")
    first_target_id = "army-alpha:intercessor-unit-1"
    second_target_id = "army-alpha:intercessor-unit-2"

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            trigger_payload={
                SELECTED_TARGET_UNIT_CONTEXT_KEY: [second_target_id, first_target_id],
            },
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.target_bindings == (
        {
            "rule_id": compiled.rule_ir.rule_id,
            "source_id": compiled.rule_ir.source_id,
            "clause_id": compiled.rule_ir.clauses[0].clause_id,
            "target_kind": "selected_target",
            "target_unit_instance_ids": [first_target_id, second_target_id],
            "target_player_id": None,
        },
    )


def test_phase17d_selected_target_effect_uses_trigger_payload_binding() -> None:
    state = _battle_state_with_scenario()
    compiled = _compiled(
        "One friendly unit that was selected as the target gains Stealth until the end "
        "of the phase."
    )
    target_unit_id = "army-alpha:intercessor-unit-1"

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [target_unit_id]},
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.effect_payloads[0]["target_unit_instance_ids"] == [target_unit_id]
    assert state.persisting_effects_for_unit(target_unit_id) == result.created_persisting_effects


def test_phase17d_selected_target_binding_requires_matching_context() -> None:
    compiled = _compiled("One friendly unit that was selected as the target.")
    selected_target_id = "army-alpha:intercessor-unit-1"
    other_target_id = "army-alpha:intercessor-unit-2"

    missing_context = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )
    mismatched_target = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            target_unit_instance_ids=(other_target_id,),
            trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [selected_target_id]},
        ),
        registry=default_rule_execution_registry(),
    )

    assert missing_context.status is RuleExecutionStatus.INVALID
    assert missing_context.reason == "missing_selected_target_context"
    assert mismatched_target.status is RuleExecutionStatus.INVALID
    assert mismatched_target.reason == "unit_not_selected_as_target"
    assert missing_context.target_bindings == ()
    assert mismatched_target.target_bindings == ()


def test_phase17d_missing_registry_binding_produces_typed_unsupported_status() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=RuleExecutionRegistry.empty(),
    )

    assert result.status is RuleExecutionStatus.UNSUPPORTED
    assert result.reason == "missing_effect_handler:modify_dice_roll"
    assert result.event_records == ()


def test_phase17d_no_effect_clause_executes_as_deterministic_noop() -> None:
    compiled = _compiled("At the start of your Command phase.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )
    replay_payload = _json_object(result.replay_payload)

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.applied_clause_ids == (compiled.rule_ir.clauses[0].clause_id,)
    assert result.effect_payloads == ()
    assert result.event_records == ()
    assert replay_payload["executed_clause_count"] == 1
    assert replay_payload["event_count"] == 0


def test_phase17d_execution_payload_and_registry_metadata_are_json_safe() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")
    execution_payload = validate_json_value({"rule_ir": compiled.rule_ir.to_payload()})

    rule_ir = rule_ir_from_execution_payload(execution_payload)
    registry_payload = default_rule_execution_registry().to_payload()

    assert rule_ir.ir_hash() == compiled.rule_ir.ir_hash()
    assert rule_execution_status_from_token("applied") is RuleExecutionStatus.APPLIED
    assert "phase17d:generic-command-points" in {
        binding["binding_id"] for binding in registry_payload
    }
    assert "<" not in json.dumps(registry_payload, sort_keys=True)
    with pytest.raises(GameLifecycleError, match="must be a JSON object"):
        rule_ir_from_execution_payload([])
    with pytest.raises(GameLifecycleError, match="requires rule_ir"):
        rule_ir_from_execution_payload({"missing": None})
    with pytest.raises(GameLifecycleError, match="must be a string"):
        rule_execution_status_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported RuleExecutionStatus"):
        rule_execution_status_from_token("not-a-status")


def test_phase17d_rule_execution_registry_and_binding_validators_fail_fast() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")
    clause = compiled.rule_ir.clauses[0]
    effect = clause.effects[0]
    binding = RuleRuntimeBinding(
        binding_id="phase17d:test-binding",
        template_id=None,
        effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
        handler=_noop_rule_handler,
    )

    assert binding.matches_clause(clause)
    assert binding.matches_effect(clause=clause, effect=effect)
    assert RuleExecutionRegistry.from_bindings((binding,)).all_bindings() == (binding,)
    with pytest.raises(GameLifecycleError, match="state must be a GameState"):
        _execution_context(state=cast(GameState, object()))
    with pytest.raises(GameLifecycleError, match="event_log must be an EventLog"):
        _execution_context(event_log=cast(EventLog, object()))
    with pytest.raises(GameLifecycleError, match="trigger_kind must be RuleTriggerKind"):
        RuleRuntimeBinding(
            binding_id="phase17d:bad-trigger",
            template_id=None,
            effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
            handler=_noop_rule_handler,
            trigger_kind=cast(RuleTriggerKind, "bad"),
        )
    with pytest.raises(GameLifecycleError, match="handler must be callable"):
        RuleRuntimeBinding(
            binding_id="phase17d:bad-handler",
            template_id=None,
            effect_kinds=(RuleEffectKind.MODIFY_DICE_ROLL,),
            handler=cast(Any, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires a template, effect, or target"):
        RuleRuntimeBinding(
            binding_id="phase17d:no-match-surface",
            template_id=None,
            effect_kinds=(),
            handler=_noop_rule_handler,
        )
    with pytest.raises(GameLifecycleError, match="clause match requires a RuleClause"):
        binding.matches_clause(cast(RuleClause, object()))
    with pytest.raises(GameLifecycleError, match="effect match requires RuleEffectSpec"):
        binding.matches_effect(clause=clause, effect=cast(RuleEffectSpec, object()))
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        RuleExecutionRegistry.from_bindings(cast(tuple[RuleRuntimeBinding, ...], []))
    with pytest.raises(GameLifecycleError, match="binding IDs must be unique"):
        RuleExecutionRegistry.from_bindings((binding, binding))
    with pytest.raises(GameLifecycleError, match="binding must be RuleRuntimeBinding"):
        RuleExecutionRegistry.empty().with_binding(cast(RuleRuntimeBinding, object()))
    with pytest.raises(GameLifecycleError, match="requires RuleExecutionContext"):
        execute_rule_ir(
            rule_ir=compiled.rule_ir,
            context=cast(RuleExecutionContext, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires RuleExecutionRegistry"):
        execute_rule_ir(
            rule_ir=compiled.rule_ir,
            context=_execution_context(target_unit_instance_ids=("army-alpha:intercessor-unit-1",)),
            registry=cast(RuleExecutionRegistry, object()),
        )


__all__: list[str] = []
__all__ += ["AbilityCatalogIndex", "AbilityCatalogRecord", "AbilityDefinition"]
__all__ += ["AbilityTimingDescriptor", "ArmyMusterRequest", "AttachmentDeclaration"]
__all__ += ["BattlefieldPlacementKind", "BattlefieldRuntimeState", "BattlefieldScenario"]
__all__ += ["CATALOG_SETUP_REACTIVE_SOURCE_KIND"]
__all__ += ["CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY", "CatalogAbilitySourceKind"]
__all__ += ["CatalogAbilitySupport", "CatalogDatasheetRuleRuntime", "CatalogJsonObject"]
__all__ += ["ChargeMoveProposal", "ChargeTargetRestrictionHookRegistry", "CompiledRuleSource"]
__all__ += ["DatasheetAbilityDescriptor", "DecisionOption", "DecisionRequest"]
__all__ += ["DetachmentSelection", "EffectError", "EffectExpiration"]
__all__ += ["FIGHTS_FIRST_CHARGE_EFFECT_KIND", "GENERIC_RULE_IR_ABILITY_HANDLER_ID", "GameConfig"]
__all__ += ["GameLifecycle", "GameLifecycleStage", "HitRollModifierContext"]
__all__ += ["MOVEMENT_PROPOSAL_DECISION_TYPE", "MissionSetup", "ModelInstance"]
__all__ += ["ModelProfileSelection", "MovementMode", "MovementProposalRequest"]
__all__ += ["PLACEMENT_PROPOSAL_DECISION_TYPE", "ObjectiveRuleScope", "ParameterizedSubmission"]
__all__ += ["PathWitness", "Pose", "ProposalKind", "ReactionQueue", "ReactionWindow"]
__all__ += ["RuleCondition", "RuleConditionKind", "RuleExecutionResult", "RuleIR", "RuleIRError"]
__all__ += ["RuleIRPayload", "RuleSourceText", "RuleTrigger"]
__all__ += ["SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE"]
__all__ += ["SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE"]
__all__ += ["SETUP_REACTIVE_SHOOT_CHARGE_TEXT", "SOURCE_KEYWORD_SEQUENCE_PARTS"]
__all__ += ["STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE", "SecondaryMissionChoice"]
__all__ += ["SecondaryMissionMode", "TextSpan", "TimingWindow", "TimingWindowDescriptor"]
__all__ += ["UnitInstance", "UnitMusterSelection", "UnitPlacement", "WeaponProfile"]
__all__ += ["WoundRollModifierContext", "_append_setup_reactive_arrival_event"]
__all__ += ["_attached_leader_support_muster_request", "_battle_state_with_extra_friendly_unit"]
__all__ += ["_bodyguard_destroyed_attached_state", "_catalog_with_champion_slayer_ability"]
__all__ += ["_champion_slayer_clause_record", "_champion_slayer_descriptor"]
__all__ += ["_champion_slayer_rule_ir", "_desperate_escape_modifier_rule_ir", "_event_payloads"]
__all__ += ["_mission_setup", "_muster_request", "_muster_request_with_unit_ids"]
__all__ += ["_mustered_armies_with_extra_friendly_unit", "_non_reaction_movement_request"]
__all__ += ["_non_reaction_placement_request", "_parameterized_result_for_request"]
__all__ += ["_path_witness_for_unit_delta", "_psychic_level_session"]
__all__ += ["_reaction_queue_consistency_fixture", "_reaction_queue_window"]
__all__ += ["_record_decision_result", "_request_setup_reactive_lifecycle_action"]
__all__ += ["_rule_ir_with_aura_object_reference", "_scenario"]
__all__ += ["_scenario_with_extra_friendly_unit", "_setup_reactive_charge_move_request"]
__all__ += ["_setup_reactive_single_model_state", "_skullmaster_fury_text", "_with_unit_keywords"]
__all__ += ["_with_unit_model_poses", "_with_unit_pose"]
__all__ += ["apply_catalog_setup_reactive_charge_move"]
__all__ += ["apply_catalog_setup_reactive_shoot_charge_result"]
__all__ += ["catalog_ability_records_from_catalog"]
__all__ += ["catalog_wound_roll_reroll_permission_for_attack"]
__all__ += ["chapter_approved_2026_27_mission_pack", "compile_rule_source_text", "copy"]
__all__ += ["datasheet_keyword_lexicon_source", "destroy_model_by_rule"]
__all__ += ["ensure_army_mustered_events_for_fixture", "generic_rule_persisting_effect"]
__all__ += ["generic_rule_wound_roll_modifier", "hashlib", "initial_command_point_ledgers"]
__all__ += ["initial_victory_point_ledgers", "invalid_catalog_setup_reactive_charge_move_status"]
__all__ += ["invalid_catalog_setup_reactive_shoot_charge_status"]
__all__ += ["is_catalog_setup_reactive_charge_move_request", "parameter_payload", "psychic_uses"]
__all__ += ["request_catalog_setup_reactive_shoot_charge_if_available"]
__all__ += ["rules_unit_persisting_effects", "scoped_rule_ir_from_execution_payload"]
__all__ += ["stratagem_decline_payload", "validate_reaction_queue_consistency"]
__all__ += ["with_unit_keywords"]
