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


def test_psychic_level_use_is_shared_by_attached_components() -> None:
    state = _battle_state_with_attached_leader_support()
    state = _with_unit_keywords(
        state, unit_instance_id="army-alpha:leader-unit", keywords=("PSYKER",), faction_keywords=()
    )
    rule_ir = _compiled("Gain 1CP.").rule_ir
    clause = rule_ir.clauses[0]
    condition = RuleCondition(
        kind=RuleConditionKind.FREQUENCY_LIMIT,
        source_span=clause.source_span,
        parameters=(
            RuleParameter("activation_kind", "psychic_ability_use"),
            RuleParameter("psychic_level", 1),
            RuleParameter("scope", "phase"),
            RuleParameter("max_uses", 1),
        ),
    )
    rule_ir = replace(
        rule_ir, clauses=(replace(clause, conditions=(*clause.conditions, condition)),)
    )
    event_log = EventLog()
    leader = _unit_by_id(state, "army-alpha:leader-unit")
    support = _unit_by_id(state, "army-alpha:support-unit")
    context = _execution_context(
        state=state,
        event_log=event_log,
        source_unit_instance_id=leader.unit_instance_id,
        source_model_instance_id=leader.own_models[0].model_instance_id,
    )
    first = execute_rule_ir(rule_ir=rule_ir, context=context)
    before = (state.to_payload(), event_log.to_payload())
    repeated = execute_rule_ir(
        rule_ir=replace(rule_ir, rule_id="duplicate-physical-instance"),
        context=replace(
            context,
            source_unit_instance_id=support.unit_instance_id,
            source_model_instance_id=support.own_models[0].model_instance_id,
        ),
    )
    assert first.status is RuleExecutionStatus.APPLIED
    assert repeated.status is RuleExecutionStatus.INVALID
    assert repeated.reason == "psychic_ability_used_this_phase"
    assert (state.to_payload(), event_log.to_payload()) == before


def test_psychic_catalog_activation_uses_one_model_per_unit_and_restores() -> None:
    session = _psychic_level_session()
    request = _next_psychic_request(session)
    assert request is not None
    assert request.actor_id == "player-a"
    use = next(option for option in request.options if _json_object(option.payload)["activate"])
    malformed = replace(
        DecisionResult.for_request(
            result_id="psychic:malformed", request=request, selected_option_id=use.option_id
        ),
        payload={},
    )
    before = session.lifecycle.to_payload()
    assert session.lifecycle.submit_decision(malformed).status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    status = session.submit_option(
        request_id=request.request_id, option_id=use.option_id, result_id="psychic:first"
    )
    next_request = status.decision_request
    assert next_request is not None
    assert next_request.actor_id == "player-b"
    uses = psychic_uses(session.lifecycle.decision_controller.event_log)
    assert len(uses) == 1
    assert uses[0].rules_unit_instance_id == "army-alpha:intercessor-unit-1"
    payload = session.lifecycle.to_payload()
    restored = GameLifecycle.from_payload(copy.deepcopy(payload))
    assert restored.to_payload() == payload
    for field, replacement in (
        ("rules_unit_instance_id", "army-beta:intercessor-unit-2"),
        ("source_component_unit_instance_id", "army-beta:intercessor-unit-2"),
        ("source_model_instance_id", "unknown-model"),
        ("catalog_record_id", "unknown-record"),
        ("phase", "shooting"),
        ("psychic_level", 2),
    ):
        altered = copy.deepcopy(payload)
        event = next(
            event
            for event in altered["decisions"]["event_log"]
            if event["event_type"] == "psychic_ability_used"
        )
        _json_object(event["payload"])[field] = replacement
        with pytest.raises(GameLifecycleError, match="Psychic"):
            GameLifecycle.from_payload(altered)
    for viewer in ("player-a", "player-b"):
        public = session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        assert any(event["event_type"] == "psychic_ability_used" for event in public["events"])
        json.dumps(public, allow_nan=False)
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="replay:psychic-level")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


def test_psychic_facade_preserves_historical_uses_after_phase_and_round_transitions() -> None:
    session = _psychic_level_session(any_phase=True, start_phase=BattlePhase.COMMAND)
    expected_occurrences = (
        (1, "player-a", BattlePhase.COMMAND),
        (1, "player-a", BattlePhase.MOVEMENT),
        (2, "player-a", BattlePhase.COMMAND),
    )
    status = session.advance_until_decision_or_terminal()
    for index in range(200):
        state = session.lifecycle.state
        assert state is not None
        uses = psychic_uses(session.lifecycle.decision_controller.event_log)
        if len(uses) == len(expected_occurrences):
            break
        request = status.decision_request
        assert request is not None, status.payload
        if request.decision_type == SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE:
            activate = (
                request.actor_id == "player-a"
                and (
                    state.battle_round,
                    state.active_player_id,
                    state.current_battle_phase,
                )
                == expected_occurrences[len(uses)]
            )
            option = next(
                option
                for option in request.options
                if _json_object(option.payload)["activate"] is activate
            )
        elif request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"psychic:history:decline-stratagem:{index}",
                payload=stratagem_decline_payload(),
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status.payload
            continue
        elif request.decision_type in {"select_movement_unit", "resolve_sequencing_order"}:
            option = request.options[0]
        else:
            options = tuple(
                option
                for option in request.options
                if option.option_id
                in {
                    "remain_stationary",
                    "complete_shooting_phase",
                    "complete_charge_phase",
                    "decline_stratagem_window",
                }
            )
            assert len(options) == 1, request.to_payload()
            option = options[0]
        status = session.submit_option(
            request_id=request.request_id,
            option_id=option.option_id,
            result_id=f"psychic:history:option:{index}",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.payload
    else:
        pytest.fail("The Psychic facade scenario did not reach the next battle round.")

    assert (state.battle_round, state.active_player_id, state.current_battle_phase) == (
        expected_occurrences[-1]
    )
    assert tuple((use.battle_round, use.active_player_id, use.phase) for use in uses) == (
        expected_occurrences
    )
    assert len({use.rules_unit_instance_id for use in uses}) == 1
    assert len({use.ability_source_id for use in uses}) == 1
    assert len({use.usage_key for use in uses}) == 3
    # Once-per-battle physical-source limits still apply independently of the Psychic phase limit.
    assert len({use.source_model_instance_id for use in uses}) == 3
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(copy.deepcopy(checkpoint))
    assert restored.to_persistence_payload() == checkpoint
    assert psychic_uses(restored.lifecycle.decision_controller.event_log) == uses
    for viewer in ("player-a", "player-b"):
        original_events = session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        restored_events = restored.events_since(EventStreamCursor(), viewer_player_id=viewer)
        assert restored_events == original_events
        assert tuple(
            event["payload"]
            for event in restored_events["events"]
            if event["event_type"] == "psychic_ability_used"
        ) == tuple(use.to_payload() for use in uses)
    replay = ReplayRunner.from_payload(
        restored.replay_artifact(artifact_id="replay:psychic:historical-phases")
    ).run()
    assert replay.reproduced_exactly, replay.to_payload()


def test_psychic_used_source_is_not_requeued_and_stale_use_is_rejected() -> None:
    session = _psychic_level_session(any_phase=True)
    first = _next_psychic_request(session)
    assert first is not None
    use = next(option for option in first.options if _json_object(option.payload)["activate"])
    second = session.submit_option(
        request_id=first.request_id, option_id=use.option_id, result_id="psychic:queued:first"
    ).decision_request
    second = _next_psychic_request(session)
    assert second.actor_id != first.actor_id
    before = session.lifecycle.to_payload()
    rejected = session.lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="psychic:stale-repeat", request=first, selected_option_id=use.option_id
        )
    )
    assert rejected.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    decline = next(
        option for option in second.options if not _json_object(option.payload)["activate"]
    )
    session.submit_option(
        request_id=second.request_id,
        option_id=decline.option_id,
        result_id="psychic:queued:decline",
    )
    assert len(psychic_uses(session.lifecycle.decision_controller.event_log)) == 1
    restored = GameLifecycle.from_payload(session.lifecycle.to_payload())
    assert restored.to_payload() == session.lifecycle.to_payload()
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="psychic:queued"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


def test_psychic_attached_use_survives_bodyguard_and_source_model_loss() -> None:
    from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
    from warhammer40k_core.engine.rule_model_destruction import destroy_model_with_rule_reactions

    session = _psychic_level_session(attached=True)
    first = _next_psychic_request(session)
    assert first is not None
    use = next(option for option in first.options if _json_object(option.payload)["activate"])
    session.submit_option(
        request_id=first.request_id, option_id=use.option_id, result_id="psychic:attached"
    )
    state = session.lifecycle.state
    assert state is not None
    uses = psychic_uses(session.lifecycle.decision_controller.event_log)
    assert len(uses) == 1
    assert uses[0].rules_unit_instance_id == "attached-unit:army-alpha:bodyguard-unit"
    assert uses[0].source_component_unit_instance_id == "army-alpha:leader-unit"
    casualty_phase = state.current_battle_phase
    assert casualty_phase is not None
    for unit_id in (
        "army-alpha:bodyguard-unit",
        "army-alpha:leader-unit",
        "army-alpha:support-unit",
    ):
        for model_id in _unit_by_id(state, unit_id).own_model_ids():
            state.record_persisting_effect(
                PersistingEffect(
                    effect_id="psychic-test-casualties",
                    source_rule_id="psychic-test-casualties",
                    owner_player_id="player-a",
                    target_unit_instance_ids=(uses[0].rules_unit_instance_id,),
                    started_battle_round=state.battle_round,
                    started_phase=casualty_phase,
                    expiration=EffectExpiration.end_phase(
                        battle_round=state.battle_round, phase=casualty_phase, player_id="player-a"
                    ),
                    effect_payload={"effect_kind": "fixture_casualties"},
                )
            )
            destroy_model_with_rule_reactions(
                state=state,
                decisions=session.lifecycle.decision_controller,
                model_instance_id=model_id,
                rules_unit_instance_id=uses[0].rules_unit_instance_id,
                destroying_player_id="player-b",
                source_rule_id="psychic-test-casualties",
                source_effect_ids=("psychic-test-casualties",),
                source_phase=casualty_phase,
                source_step="ability_resolution",
                source_result_id=f"casualty:{model_id}",
                completion_event_type="test_psychic_casualty",
                completion_event_payload={"model_instance_id": model_id},
            )
        restored = GameLifecycle.from_payload(session.lifecycle.to_payload())
        assert restored.to_payload() == session.lifecycle.to_payload()


def test_psychic_restore_rejects_missing_duplicate_and_invented_use_records() -> None:
    session = _psychic_level_session()
    first = _next_psychic_request(session)
    assert first is not None
    use = next(option for option in first.options if _json_object(option.payload)["activate"])
    session.submit_option(
        request_id=first.request_id, option_id=use.option_id, result_id="psychic:integrity"
    )
    original = session.lifecycle.to_payload()
    for alteration in ("missing", "duplicate", "unknown_field", "hash", "source", "decision"):
        payload = copy.deepcopy(original)
        events = payload["decisions"]["event_log"]
        event = next(row for row in events if row["event_type"] == "psychic_ability_used")
        evidence = _json_object(event["payload"])
        if alteration == "missing":
            events.remove(event)
        elif alteration == "duplicate":
            repeated = copy.deepcopy(event)
            repeated["event_id"] = "psychic:duplicate"
            events.append(repeated)
        elif alteration == "hash":
            evidence["source_rule_ir_hash"] = "0" * 64
        elif alteration == "source":
            evidence["restriction_source_id"] = "wrong-core-rule"
        elif alteration == "decision":
            evidence["result_id"] = "not-an-accepted-result"
        else:
            evidence["unrecognized"] = True
        for index, row in enumerate(events, start=1):
            row["event_id"] = f"event-{index:06d}"
        with pytest.raises(GameLifecycleError):
            GameLifecycle.from_payload(payload)


def test_psychic_phase_identity_distinguishes_turns_rounds_units_and_source_abilities() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    for unit in state.army_definitions[0].units:
        _with_unit_keywords(
            state, unit_instance_id=unit.unit_instance_id, keywords=("PSYKER",), faction_keywords=()
        )
    ir = _compiled("Might (Psychic level 1): Add 1 to hit rolls.").rule_ir
    assert ir.is_supported
    log = EventLog()
    context = _execution_context(
        state=state, event_log=log, source_unit_instance_id=source.unit_instance_id
    )
    assert execute_rule_ir(rule_ir=ir, context=context).status is RuleExecutionStatus.APPLIED
    # A higher-level copy of the same stable source is still the same ability.
    higher = replace(
        ir,
        clauses=tuple(
            replace(
                clause,
                conditions=tuple(
                    replace(
                        condition,
                        parameters=tuple(
                            replace(parameter, value=2)
                            if parameter.key == "psychic_level"
                            else parameter
                            for parameter in condition.parameters
                        ),
                    )
                    for condition in clause.conditions
                ),
            )
            for clause in ir.clauses
        ),
    )
    assert (
        execute_rule_ir(rule_ir=higher, context=context).reason == "psychic_ability_used_this_phase"
    )
    distinct = replace(
        ir, source_id="another-stable-source", rule_id="same-display-name-other-source"
    )
    assert execute_rule_ir(rule_ir=distinct, context=context).status is RuleExecutionStatus.APPLIED
    other = next(
        unit
        for unit in state.army_definitions[0].units
        if unit.unit_instance_id != source.unit_instance_id
    )
    assert (
        execute_rule_ir(
            rule_ir=ir, context=replace(context, source_unit_instance_id=other.unit_instance_id)
        ).status
        is RuleExecutionStatus.APPLIED
    )
    for phase, active, round_number in (
        (BattlePhase.MOVEMENT, "player-a", 1),
        (BattlePhase.COMMAND, "player-b", 1),
        (BattlePhase.COMMAND, "player-a", 2),
    ):
        state.battle_phase_index = state.battle_phase_sequence.index(phase)
        state.active_player_id = active
        state.battle_round = round_number
        context = replace(context, phase=phase, active_player_id=active, battle_round=round_number)
        assert execute_rule_ir(rule_ir=ir, context=context).status is RuleExecutionStatus.APPLIED
        assert (
            execute_rule_ir(rule_ir=ir, context=context).reason == "psychic_ability_used_this_phase"
        )
    assert len(psychic_uses(EventLog.from_payload(log.to_payload()))) == 6


@pytest.mark.parametrize(
    "field", ["state", "event_log", "source", "model", "owner", "phase", "psyker"]
)
def test_psychic_invalid_source_and_phase_context_never_consumes_a_use(field: str) -> None:
    state = _battle_state_with_attached_leader_support()
    source_id = "army-alpha:leader-unit"
    _with_unit_keywords(
        state, unit_instance_id=source_id, keywords=("PSYKER",), faction_keywords=()
    )
    log = EventLog()
    context = _execution_context(state=state, event_log=log, source_unit_instance_id=source_id)
    if field == "state":
        context = replace(context, state=None)
    elif field == "event_log":
        context = replace(context, event_log=None)
    elif field == "source":
        context = replace(context, source_unit_instance_id=None)
    elif field == "model":
        context = replace(context, source_model_instance_id="unknown-model")
    elif field == "owner":
        context = replace(context, player_id="player-b")
    elif field == "phase":
        context = replace(context, phase=BattlePhase.SHOOTING)
    else:
        _with_unit_keywords(state, unit_instance_id=source_id, keywords=(), faction_keywords=())
    before = state.to_payload()
    ir = _compiled("Might (Psychic level 1): Add 1 to hit rolls.").rule_ir
    assert execute_rule_ir(rule_ir=ir, context=context).status is RuleExecutionStatus.INVALID
    assert state.to_payload() == before
    assert log.records == ()


def test_psychic_malformed_descriptor_fails_closed() -> None:
    from warhammer40k_core.rules.psychic_ability_identity import psychic_ability_level

    ir = _compiled("Might (Psychic level 1): Add 1 to hit rolls.").rule_ir
    clause = ir.clauses[0]
    condition = next(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.FREQUENCY_LIMIT
    )
    invalid = replace(
        condition,
        parameters=tuple(
            replace(parameter, value=True) if parameter.key == "psychic_level" else parameter
            for parameter in condition.parameters
        ),
    )
    with pytest.raises(RuleIRError, match="malformed"):
        psychic_ability_level(replace(ir, clauses=(replace(clause, conditions=(invalid,)),)))


def test_overlapping_aura_effect_instances_apply_once_without_erasing_evidence() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_id = "army-alpha:intercessor-unit-1"
    rule_ir = _compiled(
        'Aura: while a friendly unit is within 6" of this unit, subtract 1 from wound rolls.'
    ).rule_ir
    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=_execution_context(
            state=state,
            source_unit_instance_id=source_id,
        ),
    )
    payload = result.effect_payloads[0]
    for index in range(2):
        state.record_persisting_effect(
            generic_rule_persisting_effect(
                effect_id=f"aura-emitter-{index}",
                source_rule_id=rule_ir.source_id,
                owner_player_id="player-a",
                target_unit_instance_ids=(source_id,),
                started_battle_round=1,
                started_phase=BattlePhaseKind.COMMAND,
                expiration=EffectExpiration.end_of_battle(),
                effect_payload=payload,
            )
        )
    assert len(state.persisting_effects) == 2
    assert len(state.persisting_effects_for_unit(source_id)) == 1
    enemy_id = "army-beta:intercessor-unit-2"
    attack = WoundRollModifierContext(
        state=state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=enemy_id,
        attacker_model_instance_id=_unit_by_id(state, enemy_id).own_models[0].model_instance_id,
        target_unit_instance_id=source_id,
        weapon_profile=_weapon_profile("core-bolt-rifle"),
        strength=4,
        toughness=4,
    )
    assert generic_rule_wound_roll_modifier(attack) == -1
    restored = GameState.from_payload(state.to_payload())
    assert len(restored.persisting_effects) == 2
    assert restored.persisting_effects_for_unit(source_id) == state.persisting_effects_for_unit(
        source_id
    )


@pytest.mark.parametrize(
    "target",
    [
        "another friendly unit",
        "another friendly INFANTRY unit",
        "a friendly unit (excluding this unit)",
    ],
)
def test_aura_explicit_source_exclusion_survives_compilation_and_round_trip(target: str) -> None:
    state = _battle_state_with_extra_friendly_unit()
    rule_ir = _compiled(
        f'Aura: while {target} is within 6" of this unit, subtract 1 from wound rolls.'
    ).rule_ir
    assert rule_ir.is_supported
    rule_ir = RuleIR.from_payload(rule_ir.to_payload())
    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=_execution_context(
            state=state, source_unit_instance_id="army-alpha:intercessor-unit-1"
        ),
    )
    assert result.status is RuleExecutionStatus.APPLIED
    affected = result.aura_evaluations[0]["affected_unit_instance_ids"]
    assert isinstance(affected, list)
    assert "army-alpha:intercessor-unit-1" not in affected


def test_aura_emission_preserves_identical_effect_slots() -> None:
    state = _battle_state_with_extra_friendly_unit()
    rule_ir = _compiled(
        'Aura: while a friendly unit is within 6" of this unit, add 1 to hit rolls.'
    ).rule_ir
    clause = rule_ir.clauses[0]
    rule_ir = replace(rule_ir, clauses=(replace(clause, effects=clause.effects * 2),))
    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=_execution_context(
            state=state, source_unit_instance_id="army-alpha:intercessor-unit-1"
        ),
    )
    assert result.status is RuleExecutionStatus.APPLIED
    assert [payload["effect_index"] for payload in result.effect_payloads] == [0, 1]


def test_aura_overlap_across_attached_aliases_keeps_distinct_sources_and_effect_slots() -> None:
    state = _battle_state_with_attached_leader_support()
    state.battlefield_state = create_deterministic_battlefield_scenario(
        battlefield_id="attached-aura",
        armies=tuple(state.army_definitions),
    ).battlefield_state
    ir = _compiled(
        'Aura: while a friendly unit is within 6" of this unit, add 1 to hit rolls.'
    ).rule_ir
    result = execute_rule_ir(
        rule_ir=ir,
        context=_execution_context(state=state, source_unit_instance_id="army-alpha:leader-unit"),
    )
    payload = result.effect_payloads[0]
    for index, target in enumerate(("army-alpha:leader-unit", "army-alpha:support-unit")):
        state.record_persisting_effect(
            generic_rule_persisting_effect(
                effect_id=f"aura:attached:{index}",
                source_rule_id=ir.source_id,
                owner_player_id="player-a",
                target_unit_instance_ids=(target,),
                started_battle_round=1,
                started_phase=BattlePhase.COMMAND,
                expiration=EffectExpiration.end_of_battle(),
                effect_payload=payload,
            )
        )
    canonical = "attached-unit:army-alpha:bodyguard-unit"
    assert len(rules_unit_persisting_effects(state, canonical)) == 1
    first = state.persisting_effects[0]
    for index, changed in enumerate(
        (
            {**payload, "source_id": "different-aura-source"},
            {**payload, "effect_index": 1},
        )
    ):
        state.record_persisting_effect(
            replace(first, effect_id=f"aura:distinct:{index}", effect_payload=changed)
        )
    assert len(rules_unit_persisting_effects(state, canonical)) == 3
    assert len(state.persisting_effects) == 4
    conflicting = {**payload, "rule_ir_hash": "0" * 64}
    state.record_persisting_effect(
        replace(first, effect_id="aura:conflict", effect_payload=conflicting)
    )
    with pytest.raises(GameLifecycleError, match="conflicting source semantics"):
        rules_unit_persisting_effects(state, canonical)


@pytest.mark.parametrize("exclude_source", [False, True])
def test_catalog_stealth_aura_uses_shared_source_inclusion(exclude_source: bool) -> None:
    text = (
        'Aura: while a friendly unit is within 6" of this model, '
        "that unit has the [STEALTH] ability."
    )
    if exclude_source:
        text = text.replace("a friendly unit", "another friendly unit")
    descriptor = _generic_catalog_descriptor(text)
    ir = RuleIR.from_payload(cast(RuleIRPayload, descriptor.rule_ir_payload))
    # Canonical catalog fixture supplies the structured grant, as source providers do.
    ir = replace(
        ir,
        clauses=tuple(
            replace(
                clause,
                effects=(
                    RuleEffectSpec(
                        kind=RuleEffectKind.GRANT_ABILITY,
                        source_span=clause.source_span,
                        parameters=(RuleParameter("ability", "stealth"),),
                    ),
                ),
            )
            for clause in ir.clauses
        ),
    )
    catalog = _catalog_with_descriptor(
        replace(descriptor, rule_ir_payload=cast(CatalogJsonObject, ir.to_payload()))
    )
    armies = tuple(
        muster_army(catalog=catalog, request=request)
        for request in _setup_reactive_config(catalog).army_muster_requests
    )
    state = _battle_state()
    for army in armies:
        state.record_army_definition(army)
    state.battlefield_state = create_deterministic_battlefield_scenario(
        battlefield_id="aura-catalog", armies=armies
    ).battlefield_state
    records = catalog_ability_records_from_catalog(catalog)
    runtime = CatalogDatasheetRuleRuntime(
        {
            army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
            for army in armies
        },
        armies,
    )
    registry = RuntimeModifierRegistry.from_bindings(
        hit_roll_modifier_bindings=runtime.hit_roll_modifier_bindings()
    )
    attacker = armies[1].units[0]
    context = HitRollModifierContext(
        state=state,
        attacking_unit_instance_id=attacker.unit_instance_id,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        target_unit_instance_id=armies[0].units[0].unit_instance_id,
        weapon_profile=_weapon_profile("core-bolt-rifle"),
        source_phase=BattlePhase.SHOOTING,
    )
    from warhammer40k_core.engine.stealth import rules_unit_stealth_sources

    assert registry.hit_roll_modifier(context) == 0
    grants = RuntimeModifierRegistry.from_bindings(
        model_ability_grant_bindings=runtime.model_ability_grant_bindings()
    )
    assert (
        rules_unit_stealth_sources(
            state=state,
            target_unit_instance_id=context.target_unit_instance_id,
            runtime_modifier_registry=grants,
        )
        is None
    ) is exclude_source


def test_phase17d_generic_modifier_rule_executes_as_source_linked_effect() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")
    context = _execution_context(
        record_persisting_effects=False,
        target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
    )

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=context,
        registry=default_rule_execution_registry(),
    )
    effect_payload = result.effect_payloads[0]
    effect = _json_object(effect_payload["effect"])

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.reason is None
    assert result.applied_clause_ids == (compiled.rule_ir.clauses[0].clause_id,)
    assert effect["kind"] == "modify_dice_roll"
    assert effect["parameters"] == [
        {"key": "delta", "value": 1},
        {"key": "roll_type", "value": "hit"},
    ]
    assert result.event_records[0].event_type == "rule_execution_effect_applied"
    assert result.to_payload()["source_id"] == compiled.rule_ir.source_id


def test_phase17d_catalog_setup_reactive_shoot_charge_requests_finite_actions_and_drift() -> None:
    descriptor = _generic_catalog_descriptor(
        SETUP_REACTIVE_SHOOT_CHARGE_TEXT,
        ability_id="setup-reactive-shoot-charge",
    )
    catalog = _catalog_with_descriptor(descriptor)
    armies = (
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
    )
    state = _battle_state()
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17d-setup-reactive",
        armies=armies,
    )
    state.battlefield_state = scenario.battlefield_state
    target_unit_id = "army-alpha:intercessor-unit-1"
    source_unit_id = "army-beta:intercessor-unit-2"
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=target_unit_id,
        pose=Pose.at(0.0, 10.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=source_unit_id,
        pose=Pose.at(16.0, 10.0),
    )
    source_unit = _unit_by_id(state, source_unit_id)
    source_model = source_unit.own_models[0]
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_armies.append(
            replace(
                army,
                units=tuple(
                    replace(unit, own_models=(source_model,))
                    if unit.unit_instance_id == source_unit_id
                    else unit
                    for unit in army.units
                ),
            )
        )
    state.army_definitions = updated_armies
    assert state.battlefield_state is not None
    source_placement = state.battlefield_state.unit_placement_by_id(source_unit_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        replace(
            source_placement,
            model_placements=(
                next(
                    placement
                    for placement in source_placement.model_placements
                    if placement.model_instance_id == source_model.model_instance_id
                ),
            ),
        )
    )
    records = catalog_ability_records_from_catalog(catalog)
    player_b_index = build_player_ability_index(
        records,
        army=state.army_definitions[1],
        catalog=catalog,
    )
    decisions = DecisionController()
    reaction_queue = ReactionQueue()
    setup_event = decisions.event_log.append(
        "reinforcement_unit_arrived",
        {
            "player_id": "player-a",
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": "player-a",
            "phase": BattlePhase.MOVEMENT.value,
            "step": "move_units",
            "unit_instance_id": target_unit_id,
            "placement_kind": "strategic_reserves",
            "request_id": "phase17d-setup-request",
            "result_id": "phase17d-setup-result",
            "phase_body_status": "reinforcement_unit_arrived",
        },
    )

    status = request_catalog_setup_reactive_shoot_charge_if_available(
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        ability_indexes_by_player_id={"player-b": player_b_index},
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    request = status.decision_request
    assert request.decision_type == SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE
    assert request.actor_id == "player-b"
    assert {option.option_id for option in request.options} == {"decline", "shoot", "charge"}
    charge_payload = cast(dict[str, JsonValue], request.option_by_id("charge").payload)
    assert charge_payload["trigger_event_id"] == setup_event.event_id
    assert charge_payload["source_unit_instance_id"] == source_unit_id
    assert charge_payload["target_unit_instance_id"] == target_unit_id
    assert charge_payload["action"] == "charge"

    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=target_unit_id,
        pose=Pose.at(40.0, 10.0),
    )
    invalid_status = invalid_catalog_setup_reactive_shoot_charge_status(
        state=state,
        request=request,
        result=DecisionResult.for_request(
            result_id="phase17d-setup-reactive-charge",
            request=request,
            selected_option_id="charge",
        ),
        decisions=decisions,
        ability_indexes_by_player_id={"player-b": player_b_index},
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
    )

    assert invalid_status is not None
    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert invalid_status.payload == {
        "invalid_reason": "setup_reactive_distance_drift",
        "field": "payload",
    }


@pytest.mark.parametrize(("roll_delta", "distance_delta"), [(0, 0.0), (10, -2.0), (-1, 2.5)])
def test_phase17d_catalog_setup_reactive_charge_suppresses_charge_bonus(
    roll_delta: int,
    distance_delta: float,
) -> None:
    state, catalog, player_b_index = _setup_reactive_single_model_state(
        target_pose=Pose.at(6.5, 10.0),
        source_pose=Pose.at(16.0, 10.0),
    )
    target_unit_id = "army-alpha:intercessor-unit-1"
    source_unit_id = "army-beta:intercessor-unit-2"
    from tests.generic_modifier_helpers import generic_effect

    from warhammer40k_core.engine.charge_declaration import (
        ChargeRollResult,
        ChargeRollResultPayload,
    )

    for effect_id, kind, parameters in (
        ("reactive-roll", "modify_dice_roll", {"delta": roll_delta, "roll_type": "charge"}),
        ("reactive-distance", "modify_move_distance", {"delta": distance_delta}),
    ):
        state.record_persisting_effect(
            generic_effect(
                effect_id=effect_id,
                owner_player_id="player-b",
                target_unit_instance_ids=(source_unit_id,),
                target_kind="this_unit",
                effect_kind=kind,
                parameters=cast(dict[str, JsonValue], parameters),
            )
        )
    decisions = DecisionController()
    reaction_queue = ReactionQueue()
    decisions.event_log.append(
        "reinforcement_unit_arrived",
        {
            "player_id": "player-a",
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": "player-a",
            "phase": BattlePhase.MOVEMENT.value,
            "step": "move_units",
            "unit_instance_id": target_unit_id,
            "placement_kind": "strategic_reserves",
            "request_id": "phase17d-setup-request",
            "result_id": "phase17d-setup-result",
            "phase_body_status": "reinforcement_unit_arrived",
        },
    )
    ruleset_descriptor = RulesetDescriptor.warhammer_40000_eleventh()

    status = request_catalog_setup_reactive_shoot_charge_if_available(
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        ability_indexes_by_player_id={"player-b": player_b_index},
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
    )

    assert status is not None
    assert status.decision_request is not None
    action_request = status.decision_request
    assert {option.option_id for option in action_request.options} == {
        "decline",
        "shoot",
        "charge",
    }
    action_result = DecisionResult.for_request(
        result_id="phase17d-setup-reactive-charge-action",
        request=action_request,
        selected_option_id="charge",
    )
    _record_decision_result(decisions=decisions, result=action_result)

    charge_status = apply_catalog_setup_reactive_shoot_charge_result(
        state=state,
        decisions=decisions,
        result=action_result,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=catalog,
        ability_index=player_b_index,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
    )

    assert charge_status is not None
    assert charge_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert charge_status.decision_request is not None
    charge_request = charge_status.decision_request
    assert charge_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    proposal_request = MovementProposalRequest.from_decision_request_payload(charge_request.payload)
    assert proposal_request.proposal_kind is ProposalKind.CHARGE_MOVE
    assert proposal_request.actor_id == "player-b"
    proposal_context = cast(dict[str, JsonValue], proposal_request.context)
    assert proposal_context[CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY] == [target_unit_id]
    assert proposal_context["charge_bonus_suppressed"] is True
    assert proposal_context["suppressed_charge_bonus"] == "fights_first"
    assert proposal_context["suppressed_charge_bonus_effect_kind"] == (
        FIGHTS_FIRST_CHARGE_EFFECT_KIND
    )

    roll = ChargeRollResult.from_payload(
        cast(ChargeRollResultPayload, proposal_context["charge_roll"])
    )
    expected_roll = min(12, max(1, roll.roll_state.current_total + roll_delta))
    assert roll.value == expected_roll
    assert proposal_context["maximum_distance_inches"] == expected_roll + distance_delta
    assert roll.movement_budget.maximum_distance_inches == expected_roll + distance_delta

    move_proposal = ChargeMoveProposal(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        unit_instance_id=proposal_request.unit_instance_id,
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=(target_unit_id,),
        witness=_path_witness_for_unit_delta(
            state=state,
            unit_instance_id=source_unit_id,
            dx=-1.25,
        ),
    )
    move_result = _parameterized_result_for_request(
        request=charge_request,
        result_id="phase17d-setup-reactive-charge-move",
        payload=cast(JsonValue, move_proposal.to_payload()),
    )
    _record_decision_result(decisions=decisions, result=move_result)

    move_status = apply_catalog_setup_reactive_charge_move(
        state=state,
        request=charge_request,
        result=move_result,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
    )

    completed_payloads = _event_payloads(decisions, "catalog_setup_reactive_charge_move_completed")
    assert move_status is None
    assert len(completed_payloads) == 1
    assert completed_payloads[0]["charge_bonus_suppressed"] is True
    assert "persisting_effect" not in completed_payloads[0]
    assert all(
        isinstance(effect.effect_payload, dict)
        and effect.effect_payload["effect_kind"] != FIGHTS_FIRST_CHARGE_EFFECT_KIND
        for effect in state.persisting_effects_for_unit(source_unit_id)
    )


@pytest.mark.parametrize("flight", [False, True])
def test_phase17d_catalog_setup_reactive_charge_submits_through_lifecycle(flight: bool) -> None:
    from warhammer40k_core.engine.charge_declaration import (
        ChargeRollResult,
        ChargeRollResultPayload,
    )

    state, catalog, player_b_index = _setup_reactive_single_model_state(
        target_pose=Pose.at(6.5, 10.0),
        source_pose=Pose.at(16.0, 10.0),
        fly=True,
    )
    lifecycle = _setup_reactive_lifecycle(state=state, catalog=catalog)
    target_unit_id = "army-alpha:intercessor-unit-1"
    source_unit_id = "army-beta:intercessor-unit-2"
    lifecycle.decision_controller.event_log.append(
        "reinforcement_unit_arrived",
        {
            "player_id": "player-a",
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": "player-a",
            "phase": BattlePhase.MOVEMENT.value,
            "step": "move_units",
            "unit_instance_id": target_unit_id,
            "placement_kind": "strategic_reserves",
            "request_id": "phase17d-lifecycle-setup-request",
            "result_id": "phase17d-lifecycle-setup-result",
            "phase_body_status": "reinforcement_unit_arrived",
        },
    )
    status = request_catalog_setup_reactive_shoot_charge_if_available(
        state=state,
        decisions=lifecycle.decision_controller,
        reaction_queue=lifecycle.reaction_queue,
        ability_indexes_by_player_id={"player-b": player_b_index},
        ruleset_descriptor=lifecycle.config.ruleset_descriptor,
        army_catalog=catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
    )

    assert status is not None
    assert status.decision_request is not None
    action_request = status.decision_request
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17d-setup-reactive-charge-action",
            request=action_request,
            selected_option_id="charge:take_to_the_skies" if flight else "charge",
        )
    )

    assert action_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    charge_request = lifecycle.pending_decision_request()
    assert charge_request is not None
    assert charge_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    proposal_request = MovementProposalRequest.from_decision_request_payload(charge_request.payload)
    malformed_status = lifecycle.submit_decision(
        _parameterized_result_for_request(
            request=charge_request,
            result_id="phase17d-lifecycle-setup-reactive-malformed-charge-move",
            payload={},
        )
    )
    assert malformed_status.status_kind is LifecycleStatusKind.INVALID
    assert _json_object(malformed_status.payload)["phase_body_status"] == "invalid"
    assert lifecycle.pending_decision_request() == charge_request

    invalid_move_proposal = ChargeMoveProposal(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        unit_instance_id=proposal_request.unit_instance_id,
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=(target_unit_id,),
        witness=_path_witness_for_unit_delta(
            state=state,
            unit_instance_id=source_unit_id,
            dx=0.0,
        ),
    )
    invalid_move_status = lifecycle.submit_decision(
        _parameterized_result_for_request(
            request=charge_request,
            result_id="phase17d-lifecycle-setup-reactive-invalid-charge-move",
            payload=cast(JsonValue, invalid_move_proposal.to_payload()),
        )
    )

    assert invalid_move_status.status_kind is LifecycleStatusKind.INVALID
    assert _json_object(invalid_move_status.payload)["phase_body_status"] == (
        "catalog_setup_reactive_charge_move_invalid"
    )
    retry_request = lifecycle.pending_decision_request()
    assert retry_request is not None
    assert retry_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    retry_proposal_request = MovementProposalRequest.from_decision_request_payload(
        retry_request.payload
    )
    move_proposal = ChargeMoveProposal(
        proposal_request_id=retry_proposal_request.request_id,
        proposal_kind=retry_proposal_request.proposal_kind,
        unit_instance_id=retry_proposal_request.unit_instance_id,
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=(target_unit_id,),
        witness=_path_witness_for_unit_delta(
            state=state,
            unit_instance_id=source_unit_id,
            dx=-1.25,
        ),
    )
    move_status = lifecycle.submit_decision(
        _parameterized_result_for_request(
            request=retry_request,
            result_id="phase17d-lifecycle-setup-reactive-charge-move",
            payload=cast(JsonValue, move_proposal.to_payload()),
        )
    )

    completed_payloads = _event_payloads(
        lifecycle.decision_controller,
        "catalog_setup_reactive_charge_move_completed",
    )
    assert move_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert len(completed_payloads) == 1
    assert completed_payloads[0]["charge_bonus_suppressed"] is True
    assert "persisting_effect" not in completed_payloads[0]
    rolls = _event_payloads(
        lifecycle.decision_controller, "catalog_setup_reactive_charge_roll_resolved"
    )
    roll = ChargeRollResult.from_payload(cast(ChargeRollResultPayload, rolls[0]["roll_result"]))
    assert roll.request.take_to_the_skies is flight
    assert roll.movement_budget.maximum_distance_inches == max(0, roll.value - (2 if flight else 0))
    assert lifecycle.state is not None
    assert len(lifecycle.state.model_movement_history) == 1
    assert state.persisting_effects_for_unit(source_unit_id) == ()


def test_phase17d_catalog_setup_reactive_decline_submits_through_lifecycle() -> None:
    state, catalog, player_b_index = _setup_reactive_single_model_state(
        target_pose=Pose.at(6.5, 10.0),
        source_pose=Pose.at(16.0, 10.0),
    )
    lifecycle = _setup_reactive_lifecycle(state=state, catalog=catalog)
    lifecycle_state = lifecycle.state
    assert lifecycle_state is not None
    action_request = _request_setup_reactive_lifecycle_action(
        lifecycle=lifecycle,
        state=lifecycle_state,
        catalog=catalog,
        player_b_index=player_b_index,
    )

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17d-lifecycle-setup-reactive-decline",
            request=action_request,
            selected_option_id="decline",
        )
    )

    declined_payloads = _event_payloads(
        lifecycle.decision_controller,
        "catalog_setup_reactive_shoot_charge_declined",
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.reaction_queue.frames == ()
    assert len(declined_payloads) == 1
    assert declined_payloads[0]["source_unit_instance_id"] == "army-beta:intercessor-unit-2"
    assert declined_payloads[0]["target_unit_instance_id"] == "army-alpha:intercessor-unit-1"


def test_phase17d_catalog_setup_reactive_shoot_submits_through_lifecycle() -> None:
    from tests.dice_result_semantics_helpers import assert_active_player_history, open_phase

    state, catalog, player_b_index = _setup_reactive_single_model_state(
        target_pose=Pose.at(6.5, 10.0),
        source_pose=Pose.at(16.0, 10.0),
    )
    lifecycle = _setup_reactive_lifecycle(state=state, catalog=catalog)
    lifecycle_state = lifecycle.state
    assert lifecycle_state is not None
    open_phase(lifecycle)
    action_request = _request_setup_reactive_lifecycle_action(
        lifecycle=lifecycle,
        state=lifecycle_state,
        catalog=catalog,
        player_b_index=player_b_index,
    )

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17d-lifecycle-setup-reactive-shoot",
            request=action_request,
            selected_option_id="shoot",
        )
    )

    shoot_payloads = _event_payloads(
        lifecycle.decision_controller,
        "catalog_setup_reactive_shoot_requested",
    )
    pending_request = lifecycle.pending_decision_request()
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert pending_request is not None
    assert lifecycle.reaction_queue.frames[-1].request_id == pending_request.request_id
    assert lifecycle_state.out_of_phase_shooting_state is not None
    assert lifecycle_state.out_of_phase_shooting_state.selected_unit_instance_id == (
        "army-beta:intercessor-unit-2"
    )
    assert lifecycle_state.out_of_phase_shooting_state.target_unit_ids == (
        "army-alpha:intercessor-unit-1",
    )
    assert len(shoot_payloads) == 1
    assert shoot_payloads[0]["action"] == "shoot"

    assert_active_player_history(lifecycle, expected_player="player-b")


@pytest.mark.parametrize(
    ("drift_case", "expected_message"),
    [
        ("wrong_stage", "Lifecycle reaction queue requires battle stage."),
        ("missing_phase", "Lifecycle reaction queue requires a current battle phase."),
        ("missing_pending", "Lifecycle reaction queue requires a pending decision."),
        ("wrong_decision_type", "Lifecycle reaction queue pending decision_type drift."),
        ("placement_drift", "Lifecycle reaction queue pending placement decision drift."),
        ("movement_drift", "Lifecycle reaction queue pending movement decision drift."),
        ("missing_request_id", "Lifecycle reaction queue frame requires request_id."),
        ("duplicate_request_id", "Lifecycle reaction queue request_ids must be unique."),
        ("game_id_drift", "Lifecycle reaction queue frame game_id drift."),
        ("phase_drift", "Lifecycle reaction queue frame phase drift."),
    ],
)
def test_phase17d_reaction_queue_consistency_rejects_drift(
    drift_case: str,
    expected_message: str,
) -> None:
    state = _battle_state()
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    decisions, reaction_queue, request = _reaction_queue_consistency_fixture(state=state)
    pending_request: DecisionRequest | None = request
    allowlist = {request.decision_type}

    if drift_case == "wrong_stage":
        state.stage = GameLifecycleStage.SETUP
    elif drift_case == "missing_phase":
        state.battle_phase_index = None
    elif drift_case == "missing_pending":
        pending_request = None
    elif drift_case == "wrong_decision_type":
        allowlist = {SELECT_CATALOG_SETUP_REACTIVE_SHOOT_CHARGE_DECISION_TYPE}
    elif drift_case == "placement_drift":
        pending_request = _non_reaction_placement_request(
            state=state,
            request_id=request.request_id,
        )
        allowlist = {PLACEMENT_PROPOSAL_DECISION_TYPE}
    elif drift_case == "movement_drift":
        pending_request = _non_reaction_movement_request(
            state=state,
            request_id=request.request_id,
        )
        allowlist = {MOVEMENT_PROPOSAL_DECISION_TYPE}
    elif drift_case == "missing_request_id":
        payload = reaction_queue.to_payload()
        payload["frames"][0]["request_id"] = None
        reaction_queue = ReactionQueue.from_payload(payload)
    elif drift_case == "duplicate_request_id":
        second = reaction_queue.emit_decision_request(
            state=state,
            decisions=decisions,
            reaction_window=_reaction_queue_window(
                state=state,
                window_id="phase17d-reaction-consistency-duplicate",
            ),
            parent_phase=BattlePhase.MOVEMENT,
            parent_step="end_movement_phase_reactions",
            resume_token="phase17d-reaction-consistency-duplicate-resume",
            actor_id="player-b",
            options=(
                DecisionOption(option_id="decline", label="Decline", payload={"action": "decline"}),
            ),
            payload={"source": "phase17d-reaction-consistency-duplicate"},
        )
        pending_request = second.decision_request
        payload = reaction_queue.to_payload()
        payload["frames"][1]["request_id"] = payload["frames"][0]["request_id"]
        reaction_queue = ReactionQueue.from_payload(payload)
    elif drift_case == "game_id_drift":
        state.game_id = "phase17d-other-game"
    elif drift_case == "phase_drift":
        state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    else:
        raise AssertionError(f"Unhandled drift case: {drift_case}")

    with pytest.raises(GameLifecycleError, match=expected_message):
        validate_reaction_queue_consistency(
            state=state,
            reaction_queue=reaction_queue,
            pending_request=pending_request,
            reaction_frame_decision_types=allowlist,
        )


def test_phase17d_catalog_setup_reactive_records_unsupported_multi_model_source_once() -> None:
    from warhammer40k_core.engine.catalog_setup_reactive_sequencing import (
        setup_reactive_end_candidates,
    )
    from warhammer40k_core.engine.turn_end_hooks import TurnEndRequestContext

    state, catalog, player_b_index = _setup_reactive_single_model_state(
        target_pose=Pose.at(6.5, 10.0),
        source_pose=Pose.at(16.0, 10.0),
        keep_all_source_models=True,
    )
    decisions = DecisionController()
    reaction_queue = ReactionQueue()
    _append_setup_reactive_arrival_event(
        decisions=decisions,
        state=state,
        target_unit_id="army-alpha:intercessor-unit-1",
    )

    before = state.to_payload(), decisions.to_payload(), reaction_queue.to_payload()
    candidates = setup_reactive_end_candidates(
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=BattlePhase.MOVEMENT,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=catalog,
            reaction_queue=reaction_queue,
        ),
        ability_indexes={"player-b": player_b_index},
    )
    assert len(candidates) == 1
    assert (state.to_payload(), decisions.to_payload(), reaction_queue.to_payload()) == before
    for attempt in range(2):
        status = request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id={"player-b": player_b_index},
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )
        if attempt == 0:
            assert status is not None
            assert status.status_kind is LifecycleStatusKind.UNSUPPORTED
        else:
            assert status is None

    unsupported_payloads = _event_payloads(
        decisions,
        "catalog_setup_reactive_shoot_charge_unsupported",
    )
    assert len(unsupported_payloads) == 1
    assert unsupported_payloads[0]["source_unit_instance_id"] == ("army-beta:intercessor-unit-2")
    assert unsupported_payloads[0]["target_unit_instance_id"] == ("army-alpha:intercessor-unit-1")
    assert unsupported_payloads[0]["unsupported_reason"] == (
        "model_scoped_action_requires_single_placed_alive_model"
    )


@pytest.mark.parametrize(
    ("payload_field", "payload_value", "diagnostic_field"),
    [
        ("proposal_kind", ProposalKind.NORMAL_MOVE.value, "proposal_kind"),
        ("movement_mode", MovementMode.NORMAL.value, "movement_mode"),
        ("movement_phase_action", "normal_move", "movement_phase_action"),
        ("charge_target_unit_instance_ids", [1], "charge_target_unit_instance_ids"),
        ("witness", {"model_paths": []}, "witness"),
    ],
)
def test_phase17d_catalog_setup_reactive_charge_move_malformed_fields_are_typed(
    payload_field: str,
    payload_value: JsonValue,
    diagnostic_field: str,
) -> None:
    state, catalog, player_b_index = _setup_reactive_single_model_state(
        target_pose=Pose.at(6.5, 10.0),
        source_pose=Pose.at(16.0, 10.0),
    )
    decisions, charge_request = _setup_reactive_charge_move_request(
        state=state,
        catalog=catalog,
        player_b_index=player_b_index,
    )
    proposal_request = MovementProposalRequest.from_decision_request_payload(charge_request.payload)
    valid_payload = ChargeMoveProposal(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        unit_instance_id=proposal_request.unit_instance_id,
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        witness=_path_witness_for_unit_delta(
            state=state,
            unit_instance_id="army-beta:intercessor-unit-2",
            dx=-1.25,
        ),
    ).to_payload()
    malformed_payload = dict(valid_payload)
    malformed_payload[payload_field] = payload_value

    status = invalid_catalog_setup_reactive_charge_move_status(
        ability_index=AbilityCatalogIndex.from_records(()),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        state=state,
        request=charge_request,
        result=_parameterized_result_for_request(
            request=charge_request,
            result_id=f"phase17d-malformed-setup-reactive-{payload_field}",
            payload=cast(JsonValue, malformed_payload),
        ),
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    validation = _json_object(_json_object(status.payload)["proposal_validation"])
    violations = cast(list[JsonValue], validation["violations"])
    violation = _json_object(violations[0])
    assert violation["field"] == diagnostic_field


def test_phase17d_catalog_setup_reactive_charge_move_no_move_records_decline() -> None:
    state = _battle_state()
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    decisions = DecisionController()
    request = MovementProposalRequest(
        request_id="phase17d-setup-reactive-charge-no-move",
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id="player-b",
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id="army-beta:intercessor-unit-2",
        proposal_kind=ProposalKind.CHARGE_MOVE,
        source_decision_request_id="phase17d-setup-reactive-action-request",
        source_decision_result_id="phase17d-setup-reactive-action-result",
        spatial_context_hash=state.physical_proposal_context_hash(),
        movement_phase_action="charge_move",
        context={
            "source_kind": CATALOG_SETUP_REACTIVE_SOURCE_KIND,
            "movement_mode": MovementMode.CHARGE.value,
            "maximum_distance_inches": 0,
            "reachable_target_unit_instance_ids": [],
            "reachable_target_distances_inches": {},
        },
    ).to_decision_request()
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    proposal = ChargeMoveProposal(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        unit_instance_id=proposal_request.unit_instance_id,
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=(),
        witness=None,
    )
    result = _parameterized_result_for_request(
        request=request,
        result_id="phase17d-setup-reactive-charge-no-move-result",
        payload=cast(JsonValue, proposal.to_payload()),
    )

    status = apply_catalog_setup_reactive_charge_move(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )

    declined_payloads = _event_payloads(
        decisions,
        "catalog_setup_reactive_charge_move_declined",
    )
    assert status is None
    assert len(declined_payloads) == 1
    assert declined_payloads[0]["unit_instance_id"] == "army-beta:intercessor-unit-2"
    assert declined_payloads[0]["proposal_request_id"] == proposal_request.request_id


def test_phase17d_catalog_setup_reactive_charge_move_request_check_is_strict() -> None:
    ordinary_request = DecisionRequest(
        request_id="phase17d-ordinary-request",
        decision_type="ordinary_decision",
        actor_id="player-b",
        payload={"source": "phase17d"},
        options=(
            DecisionOption(option_id="decline", label="Decline", payload={"action": "decline"}),
        ),
    )

    assert is_catalog_setup_reactive_charge_move_request(ordinary_request) is False
    with pytest.raises(GameLifecycleError, match="requires request"):
        is_catalog_setup_reactive_charge_move_request(cast(DecisionRequest, object()))


def test_phase17d_catalog_setup_reactive_request_validates_dependencies() -> None:
    state, catalog, player_b_index = _setup_reactive_single_model_state(
        target_pose=Pose.at(6.5, 10.0),
        source_pose=Pose.at(16.0, 10.0),
    )
    decisions = DecisionController()
    reaction_queue = ReactionQueue()
    ruleset_descriptor = RulesetDescriptor.warhammer_40000_eleventh()

    assert (
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=None,
            ability_indexes_by_player_id={"player-b": player_b_index},
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="requires decisions"):
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=cast(DecisionController, object()),
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id={"player-b": player_b_index},
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )
    with pytest.raises(GameLifecycleError, match="ability indexes must be a mapping"):
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id=cast(dict[str, AbilityCatalogIndex], []),
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )
    with pytest.raises(GameLifecycleError, match="ability index mapping contained drift"):
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id={
                "player-b": cast(AbilityCatalogIndex, object()),
            },
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )
    with pytest.raises(GameLifecycleError, match="requires a RulesetDescriptor"):
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id={"player-b": player_b_index},
            ruleset_descriptor=cast(RulesetDescriptor, object()),
            army_catalog=catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )
    with pytest.raises(GameLifecycleError, match="requires an ArmyCatalog"):
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id={"player-b": player_b_index},
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=cast(ArmyCatalog, object()),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )
    with pytest.raises(GameLifecycleError, match="requires runtime modifiers"):
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id={"player-b": player_b_index},
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=catalog,
            runtime_modifier_registry=cast(RuntimeModifierRegistry, object()),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )
    with pytest.raises(GameLifecycleError, match="requires charge target restrictions"):
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id={"player-b": player_b_index},
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=cast(ChargeTargetRestrictionHookRegistry, object()),
        )
    state.active_player_id = None
    with pytest.raises(
        GameLifecycleError, match="End rules require a current phase and player turn"
    ):
        request_catalog_setup_reactive_shoot_charge_if_available(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            ability_indexes_by_player_id={"player-b": player_b_index},
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=catalog,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
        )


def test_phase17d_catalog_setup_reactive_finite_result_malformed_is_typed() -> None:
    state, catalog, player_b_index = _setup_reactive_single_model_state(
        target_pose=Pose.at(6.5, 10.0),
        source_pose=Pose.at(16.0, 10.0),
    )
    decisions = DecisionController()
    reaction_queue = ReactionQueue()
    _append_setup_reactive_arrival_event(
        decisions=decisions,
        state=state,
        target_unit_id="army-alpha:intercessor-unit-1",
    )
    status = request_catalog_setup_reactive_shoot_charge_if_available(
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        ability_indexes_by_player_id={"player-b": player_b_index},
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        charge_target_restriction_hooks=ChargeTargetRestrictionHookRegistry.empty(),
    )
    assert status is not None
    assert status.decision_request is not None

    invalid_status = invalid_catalog_setup_reactive_shoot_charge_status(
        state=state,
        request=status.decision_request,
        result=DecisionResult(
            result_id="phase17d-setup-reactive-invalid-action",
            request_id=status.decision_request.request_id,
            decision_type=status.decision_request.decision_type,
            actor_id=status.decision_request.actor_id,
            selected_option_id="not-an-option",
            payload=status.decision_request.option_by_id("decline").payload,
        ),
        decisions=decisions,
        ability_indexes_by_player_id={"player-b": player_b_index},
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
    )

    assert invalid_status is not None
    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert invalid_status.payload == {
        "invalid_reason": "invalid_catalog_setup_reactive_action_result",
        "detail": "DecisionRequest option_id is not in the finite action space.",
    }


def test_phase17d_desperate_escape_modifier_executes_when_target_is_battle_shocked() -> None:
    rule_ir = _desperate_escape_modifier_rule_ir()
    target_unit_id = "army-beta:enemy-unit-1"

    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=_execution_context(
            record_persisting_effects=False,
            target_unit_instance_ids=(target_unit_id,),
            trigger_payload={"target_unit_is_battle_shocked": True},
            phase=BattlePhaseKind.MOVEMENT,
        ),
        registry=default_rule_execution_registry(),
    )
    effect_payload = _json_object(result.effect_payloads[0])
    effect = _json_object(effect_payload["effect"])

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.applied_clause_ids == (rule_ir.clauses[0].clause_id,)
    assert effect["kind"] == "modify_dice_roll"
    assert effect["parameters"] == [
        {"key": "delta", "value": -1},
        {"key": "roll_type", "value": "desperate_escape"},
    ]
    assert effect_payload["target_unit_instance_ids"] == [target_unit_id]


def test_phase17d_desperate_escape_modifier_is_invalid_when_target_not_battle_shocked() -> None:
    rule_ir = _desperate_escape_modifier_rule_ir()

    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=_execution_context(
            target_unit_instance_ids=("army-beta:enemy-unit-1",),
            trigger_payload={"target_unit_statuses": []},
            phase=BattlePhaseKind.MOVEMENT,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "condition_not_met:target_unit_has_status"
    assert result.effect_payloads == ()
    assert result.event_records == ()


def test_phase17d_desperate_escape_modifier_requires_target_status_evidence() -> None:
    rule_ir = _desperate_escape_modifier_rule_ir()

    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=_execution_context(
            target_unit_instance_ids=("army-beta:enemy-unit-1",),
            trigger_payload={},
            phase=BattlePhaseKind.MOVEMENT,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_input:target_unit_status"
    assert result.effect_payloads == ()
    assert result.event_records == ()


def test_phase17d_desperate_escape_modifier_uses_state_backed_battle_shock_status() -> None:
    rule_ir = _desperate_escape_modifier_rule_ir()
    state = _battle_state_with_scenario()
    target_unit_id = "army-beta:intercessor-unit-2"
    state.battle_shocked_unit_ids.append(target_unit_id)
    state.battle_shocked_unit_ids.sort()

    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=_execution_context(
            state=state,
            target_unit_instance_ids=(target_unit_id,),
            trigger_payload={},
            phase=BattlePhaseKind.MOVEMENT,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.applied_clause_ids == (rule_ir.clauses[0].clause_id,)
    assert result.effect_payloads[0]["target_unit_instance_ids"] == [target_unit_id]


def test_phase17d_champion_slayer_wound_reroll_only_applies_to_qualifying_melee_attack() -> None:
    state = _battle_state_with_scenario()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    source_model_id = unit.own_models[0].model_instance_id
    ability_index = _champion_slayer_ability_index(datasheet_id=unit.datasheet_id)

    qualifying = catalog_wound_roll_reroll_permission_for_attack(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=(source_model_id,),
        player_id="player-a",
        attack_kind="melee",
        target_keywords=("CHARACTER",),
    )
    ranged = catalog_wound_roll_reroll_permission_for_attack(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=(source_model_id,),
        player_id="player-a",
        attack_kind="ranged",
        target_keywords=("CHARACTER",),
    )
    non_keyword_target = catalog_wound_roll_reroll_permission_for_attack(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=(source_model_id,),
        player_id="player-a",
        attack_kind="melee",
        target_keywords=("INFANTRY",),
    )

    assert qualifying is not None
    assert qualifying.eligible_roll_type == "attack_sequence.wound"
    assert qualifying.timing_window == "attack_sequence.wound"
    assert ranged is None
    assert non_keyword_target is None


def test_phase17d_champion_slayer_clause_records_share_source_identity_and_split_timings() -> None:
    ability_index = _champion_slayer_ability_index(datasheet_id="core-intercessor-like-infantry")
    wound_records = ability_index.records_for(TimingTriggerKind.AFTER_DICE_ROLL)
    destroy_records = ability_index.records_for(TimingTriggerKind.AFTER_UNIT_DESTROYED)

    assert len(wound_records) == 1
    assert len(destroy_records) == 1
    assert wound_records[0].definition.ability_id == destroy_records[0].definition.ability_id
    assert wound_records[0].definition.source_id == destroy_records[0].definition.source_id
    wound_payload = cast(dict[str, JsonValue], wound_records[0].definition.replay_payload)
    destroy_payload = cast(dict[str, JsonValue], destroy_records[0].definition.replay_payload)
    assert cast(str, wound_payload["runtime_clause_id"]).endswith(":clause:001")
    assert cast(str, destroy_payload["runtime_clause_id"]).endswith(":clause:002")


def test_phase17d_catalog_builder_emits_clause_records_for_compound_ability() -> None:
    catalog = _catalog_with_champion_slayer_ability()

    records = tuple(
        record
        for record in catalog_ability_records_from_catalog(catalog)
        if record.definition.ability_id == "champion-slayer"
    )
    replay_payloads = tuple(
        cast(dict[str, JsonValue], record.definition.replay_payload) for record in records
    )

    assert len(records) == 2
    assert tuple(record.record_id for record in records) == (
        f"{catalog.source_package_id}:catalog-ability:core-intercessor-like-infantry:"
        "champion-slayer:phase17d:test:champion-slayer:clause:001",
        f"{catalog.source_package_id}:catalog-ability:core-intercessor-like-infantry:"
        "champion-slayer:phase17d:test:champion-slayer:clause:002",
    )
    assert {record.definition.source_id for record in records} == {"phase17d:test:champion-slayer"}
    assert tuple(record.definition.timing.trigger_kind for record in records) == (
        TimingTriggerKind.AFTER_DICE_ROLL,
        TimingTriggerKind.AFTER_UNIT_DESTROYED,
    )
    assert tuple(cast(str, payload["runtime_clause_id"]) for payload in replay_payloads) == (
        "phase17d:test:champion-slayer:clause:001",
        "phase17d:test:champion-slayer:clause:002",
    )


def test_p24f_catalog_builder_keeps_model_and_unit_destruction_timings_distinct() -> None:
    model_descriptor = _generic_catalog_descriptor(
        "The first time this model is destroyed, at the end of the phase, roll one D6: on "
        "a 2+, set this model back up on the battlefield as close as possible to where it "
        "was destroyed and not within Engagement Range of one or more enemy units, with "
        "3 wounds remaining.",
        ability_id="p24f-first-death-return",
    )
    model_records = tuple(
        record
        for record in catalog_ability_records_from_catalog(
            _catalog_with_descriptor(model_descriptor)
        )
        if record.definition.ability_id == "p24f-first-death-return"
    )
    unit_records = tuple(
        record
        for record in catalog_ability_records_from_catalog(_catalog_with_champion_slayer_ability())
        if record.definition.ability_id == "champion-slayer"
    )

    assert tuple(record.definition.timing.trigger_kind for record in model_records) == (
        TimingTriggerKind.AFTER_MODEL_DESTROYED,
    )
    assert tuple(record.definition.timing.trigger_kind for record in unit_records) == (
        TimingTriggerKind.AFTER_DICE_ROLL,
        TimingTriggerKind.AFTER_UNIT_DESTROYED,
    )


@pytest.mark.parametrize(
    ("raw_text", "expected_trigger_kind"),
    [
        (
            (
                "At the end of your opponent's turn, if this unit is not within Engagement "
                "Range of one or more enemy units, you can remove it from the battlefield "
                "and place it into Strategic Reserves."
            ),
            TimingTriggerKind.END_TURN,
        ),
        (
            (
                "In your opponent's Movement phase, if an enemy unit ends a move within 8\" "
                "of this unit, if this unit is not within Engagement Range of one or more "
                'enemy units, this unit can make a Normal move of up to D6".'
            ),
            TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
        ),
        (
            "This unit is eligible to declare a charge in a turn in  which it Advanced.",
            TimingTriggerKind.PASSIVE_QUERY,
        ),
        (
            "Daemonic Shadow (Aura): While a friendly Khorne Legiones Daemonica unit is "
            'within 6" of this model, that unit is within your army\u2019s Shadow of Chaos.',
            TimingTriggerKind.PASSIVE_QUERY,
        ),
        (
            "The bearer has a Toughness characteristic of 5.",
            TimingTriggerKind.PASSIVE_QUERY,
        ),
        (
            "The bearer has the Feel No Pain 3+ ability against Psychic Attacks.",
            TimingTriggerKind.PASSIVE_QUERY,
        ),
        (
            "Weapons equipped by models in that unit have the [LANCE] ability.",
            TimingTriggerKind.PASSIVE_QUERY,
        ),
        (ONCE_PER_BATTLE_FIGHT_BOOST_TEXT, TimingTriggerKind.START_PHASE),
        ("After a hit roll, re-roll hit rolls.", TimingTriggerKind.AFTER_DICE_ROLL),
        ("Gain 1CP.", TimingTriggerKind.ANY_PHASE),
    ],
)
def test_phase17d_catalog_builder_classifies_single_clause_generic_timing(
    raw_text: str,
    expected_trigger_kind: TimingTriggerKind,
) -> None:
    descriptor = _generic_catalog_descriptor(raw_text)

    records = catalog_ability_records_from_catalog(_catalog_with_descriptor(descriptor))

    assert len(records) == 1
    assert records[0].definition.timing.trigger_kind is expected_trigger_kind
    assert (
        _json_object(records[0].definition.replay_payload)["rule_ir"] == descriptor.rule_ir_payload
    )
    if raw_text == ONCE_PER_BATTLE_FIGHT_BOOST_TEXT:
        assert records[0].definition.timing.phase is BattlePhaseKind.FIGHT
    if raw_text.startswith("In your opponent's Movement phase"):
        assert records[0].definition.timing.phase is BattlePhaseKind.MOVEMENT


def test_phase17d_catalog_builder_rejects_malformed_generic_ir_descriptors() -> None:
    missing_rule_ir = _generic_catalog_descriptor("Gain 1CP.", ability_id="missing-rule-ir")
    object.__setattr__(missing_rule_ir, "rule_ir_payload", None)
    invalid_rule_ir = _generic_catalog_descriptor("Gain 1CP.", ability_id="invalid-rule-ir")
    invalid_payload = dict(cast(dict[str, JsonValue], invalid_rule_ir.rule_ir_payload))
    invalid_payload["ir_hash"] = "stale"
    object.__setattr__(invalid_rule_ir, "rule_ir_payload", invalid_payload)
    unsupported_source = _generic_catalog_descriptor(
        "Gain 1CP.",
        ability_id="unsupported-source",
        source_kind=CatalogAbilitySourceKind.CORE,
    )
    missing_wargear_source = _generic_catalog_descriptor(
        "Gain 1CP.",
        ability_id="missing-wargear-source",
        source_kind=CatalogAbilitySourceKind.WARGEAR,
        source_wargear_id="core-bolt-rifle",
    )
    object.__setattr__(missing_wargear_source, "source_wargear_id", None)

    with pytest.raises(GameLifecycleError, match="missing rule_ir"):
        catalog_ability_records_from_catalog(_catalog_with_descriptor(missing_rule_ir))
    with pytest.raises(GameLifecycleError, match="invalid IR"):
        catalog_ability_records_from_catalog(_catalog_with_descriptor(invalid_rule_ir))
    with pytest.raises(GameLifecycleError, match="source kind is unsupported"):
        catalog_ability_records_from_catalog(_catalog_with_descriptor(unsupported_source))
    with pytest.raises(GameLifecycleError, match="missing source_wargear_id"):
        catalog_ability_records_from_catalog(_catalog_with_descriptor(missing_wargear_source))


def test_phase17d_champion_slayer_heal_only_applies_after_enemy_character_or_monster() -> None:
    state = _battle_state_with_scenario()
    unit = _unit_by_id(state, "army-alpha:intercessor-unit-1")
    model = unit.own_models[0]
    ability_index = _champion_slayer_ability_index(datasheet_id=unit.datasheet_id)
    _set_model_wounds(state, model_instance_id=model.model_instance_id, wounds_remaining=1)
    wounded_unit = _unit_by_id(state, unit.unit_instance_id)

    resolved = catalog_restore_lost_wounds_after_destroying_unit(
        state=state,
        decisions=DecisionController(),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        ability_index=ability_index,
        unit=wounded_unit,
        current_model_instance_ids=(model.model_instance_id,),
        player_id="player-a",
        destroyed_player_id="player-b",
        destroyed_unit_keywords=("MONSTER",),
        healing_amount=3,
        source_event_id="event:enemy-monster-destroyed",
    )

    assert resolved is not None
    effect, request = resolved
    assert request is None
    assert effect.amount == 1
    assert len(effect.resolved_steps) == 1
    assert effect.source_context == {
        "catalog_record_id": (
            "phase17d:test:catalog-ability:core-intercessor-like-infantry:"
            "champion-slayer:phase17d:test:champion-slayer:clause:002"
        ),
        "clause_id": "phase17d:test:champion-slayer:clause:002",
        "destroyed_unit_keywords": ["MONSTER"],
        "effect_kind": "restore_lost_wounds",
        "source_model_instance_id": model.model_instance_id,
        "healing_model_instance_id": model.model_instance_id,
        "source_event_id": "event:enemy-monster-destroyed",
    }
    healed_unit = _unit_by_id(state, unit.unit_instance_id)
    assert healed_unit.own_models[0].current_wounds == model.initial_wounds


def test_phase17d_this_model_half_strength_hit_modifier_persists_source_model_conditions() -> None:
    state = _battle_state_with_scenario()
    source_unit_id = "army-alpha:intercessor-unit-1"
    source_model_id = _unit_by_id(state, source_unit_id).own_models[0].model_instance_id
    compiled = _compiled(
        "Until the end of the phase, each time this model makes an attack that targets "
        "an enemy unit that is not below Half-strength, add 1 to the Hit roll."
    )

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            source_unit_instance_id=source_unit_id,
            source_model_instance_id=source_model_id,
        ),
        registry=default_rule_execution_registry(),
    )
    effect = result.created_persisting_effects[0]
    effect_payload = _json_object(effect.effect_payload)
    conditions = cast(list[JsonValue], effect_payload["conditions"])
    target_constraint = _json_object(conditions[0])

    assert result.status is RuleExecutionStatus.APPLIED
    assert effect.target_unit_instance_ids == (source_unit_id,)
    assert state.persisting_effects_for_unit(source_unit_id) == (effect,)
    assert effect_payload["target_unit_instance_ids"] == [source_unit_id]
    assert _json_object(effect_payload["context"])["source_model_instance_id"] == source_model_id
    assert _json_object(effect_payload["target"])["kind"] == "this_model"
    assert target_constraint["kind"] == "target_constraint"
    assert target_constraint["parameters"] == [
        {"key": "gate_subject", "value": "attack_target"},
        {"key": "relationship", "value": "this_model_makes_attack"},
        {"key": "target_allegiance", "value": "enemy"},
        {"key": "target_constraint", "value": "target_not_below_half_strength"},
    ]


def test_phase17d_this_model_half_strength_hit_modifier_requires_source_model() -> None:
    state = _battle_state_with_scenario()
    source_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled(
        "Until the end of the phase, each time this model makes an attack that targets "
        "an enemy unit that is not below Half-strength, add 1 to the Hit roll."
    )

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            source_unit_instance_id=source_unit_id,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_input:source_model_instance_id"
    assert state.persisting_effects_for_unit(source_unit_id) == ()


def test_phase17d_preflight_rejects_missing_state_before_vp_mutation() -> None:
    compiled = _compiled("When this unit is destroyed, score 5VP.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_input:game_state"
    assert result.event_records == ()


def test_phase17d_generic_stratagem_target_binding_executes() -> None:
    compiled = _compiled("Select one enemy unit.")
    target_unit_id = "army-beta:intercessor-unit-2"

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            target_unit_instance_ids=(target_unit_id,),
            trigger_payload={"stratagem_id": "phase17d:test-stratagem"},
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.target_bindings == (
        {
            "rule_id": compiled.rule_ir.rule_id,
            "source_id": compiled.rule_ir.source_id,
            "clause_id": compiled.rule_ir.clauses[0].clause_id,
            "target_kind": "enemy_unit",
            "target_unit_instance_ids": [target_unit_id],
            "target_player_id": None,
        },
    )
    assert result.event_records[0].event_type == "rule_execution_target_bound"


def test_phase17d_selected_target_binding_enforces_target_keywords_with_state() -> None:
    state = _battle_state_with_scenario()
    infantry = _compiled("One friendly INFANTRY unit that was selected as the target.")
    vehicle = _compiled("One friendly VEHICLE unit that was selected as the target.")
    target_unit_id = "army-alpha:intercessor-unit-1"

    applied = execute_rule_ir(
        rule_ir=infantry.rule_ir,
        context=_execution_context(
            state=state,
            trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [target_unit_id]},
        ),
        registry=default_rule_execution_registry(),
    )
    missing_state = execute_rule_ir(
        rule_ir=infantry.rule_ir,
        context=_execution_context(
            trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [target_unit_id]},
        ),
        registry=default_rule_execution_registry(),
    )
    keyword_mismatch = execute_rule_ir(
        rule_ir=vehicle.rule_ir,
        context=_execution_context(
            state=state,
            trigger_payload={SELECTED_TARGET_UNIT_CONTEXT_KEY: [target_unit_id]},
        ),
        registry=default_rule_execution_registry(),
    )

    assert applied.status is RuleExecutionStatus.APPLIED
    assert applied.target_bindings[0]["target_unit_instance_ids"] == [target_unit_id]
    assert missing_state.status is RuleExecutionStatus.INVALID
    assert missing_state.reason == "missing_input:game_state"
    assert keyword_mismatch.status is RuleExecutionStatus.INVALID
    assert keyword_mismatch.reason == "unit_missing_required_keyword"


def test_phase17d_preflight_rejects_missing_target_binding() -> None:
    compiled = _compiled("Select one enemy unit.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.INVALID
    assert result.reason == "missing_target:unit_instance_ids"
    assert result.target_bindings == ()


def test_phase17d_friendly_aura_evaluation_ignores_enemy_units_in_range() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_unit_id = "army-alpha:intercessor-unit-1"
    friendly_unit_id = "army-alpha:intercessor-unit-3"
    enemy_unit_id = "army-beta:intercessor-unit-2"
    compiled = _compiled(
        'Aura: while a friendly unit is within 6" of this unit, subtract 1 from wound rolls.'
    )

    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=friendly_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=enemy_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, source_unit_instance_id=source_unit_id),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [
        source_unit_id,
        friendly_unit_id,
    ]
    assert result.effect_payloads[0]["target_unit_instance_ids"] == [
        source_unit_id,
        friendly_unit_id,
    ]


def test_phase17d_enemy_aura_evaluation_ignores_friendly_units_in_range() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_unit_id = "army-alpha:intercessor-unit-1"
    friendly_unit_id = "army-alpha:intercessor-unit-3"
    enemy_unit_id = "army-beta:intercessor-unit-2"
    compiled = _compiled(
        'Aura: while an enemy unit is within 6" of this unit, subtract 1 from wound rolls.'
    )

    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=friendly_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=enemy_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, source_unit_instance_id=source_unit_id),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [enemy_unit_id]
    assert result.effect_payloads[0]["target_unit_instance_ids"] == [enemy_unit_id]


def test_phase17d_any_aura_evaluation_affects_all_allegiances_in_range() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_unit_id = "army-alpha:intercessor-unit-1"
    friendly_unit_id = "army-alpha:intercessor-unit-3"
    enemy_unit_id = "army-beta:intercessor-unit-2"
    compiled = _compiled(
        'Aura: while a unit is within 6" of this unit, subtract 1 from wound rolls.'
    )

    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=friendly_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=enemy_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(state=state, source_unit_instance_id=source_unit_id),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [
        source_unit_id,
        friendly_unit_id,
        enemy_unit_id,
    ]


def test_phase17d_aura_keyword_gates_match_target_faction_keywords() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-alpha:intercessor-unit-3"
    excluded_unit_id = "army-beta:intercessor-unit-2"
    compiled = _compiled(
        "Daemon Lord of Khorne (Aura): While a friendly Khorne Legiones Daemonica "
        'unit is within 6" of this model, each time a model in that unit makes a '
        "melee attack, add 1 to the Hit roll."
    )

    state = _with_unit_keywords(
        state,
        unit_instance_id=source_unit_id,
        keywords=("CHARACTER",),
        faction_keywords=("LEGIONES DAEMONICA", "KHORNE"),
    )
    state = _with_unit_keywords(
        state,
        unit_instance_id=target_unit_id,
        keywords=("INFANTRY",),
        faction_keywords=("LEGIONES DAEMONICA", "KHORNE"),
    )
    state = _with_unit_keywords(
        state,
        unit_instance_id=excluded_unit_id,
        keywords=("INFANTRY",),
        faction_keywords=("LEGIONES DAEMONICA",),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=target_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=excluded_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            source_unit_instance_id=source_unit_id,
            source_model_instance_id=_unit_by_id(state, source_unit_id)
            .own_models[0]
            .model_instance_id,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [
        source_unit_id,
        target_unit_id,
    ]
    assert result.effect_payloads[0]["target_unit_instance_ids"] == [source_unit_id, target_unit_id]


def test_phase17d_shadow_of_chaos_aura_status_targets_matching_daemons() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-alpha:intercessor-unit-3"
    excluded_unit_id = "army-beta:intercessor-unit-2"
    compiled = _compiled(
        'Daemonic Shadow (Aura): While a friendly Nurgle Legiones Daemonica unit is within 6" '
        "of this model, that unit is within your army's Shadow of Chaos."
    )

    state = _with_unit_keywords(
        state,
        unit_instance_id=source_unit_id,
        keywords=("CHARACTER",),
        faction_keywords=("LEGIONES DAEMONICA", "NURGLE"),
    )
    state = _with_unit_keywords(
        state,
        unit_instance_id=target_unit_id,
        keywords=("INFANTRY",),
        faction_keywords=("LEGIONES DAEMONICA", "NURGLE"),
    )
    state = _with_unit_keywords(
        state,
        unit_instance_id=excluded_unit_id,
        keywords=("INFANTRY",),
        faction_keywords=("LEGIONES DAEMONICA", "KHORNE"),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=target_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=excluded_unit_id,
        pose=Pose.at(8.0, 6.0),
    )
    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            source_unit_instance_id=source_unit_id,
            source_model_instance_id=_unit_by_id(state, source_unit_id)
            .own_models[0]
            .model_instance_id,
        ),
        registry=default_rule_execution_registry(),
    )
    effect = _json_object(result.effect_payloads[0]["effect"])

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [
        source_unit_id,
        target_unit_id,
    ]
    assert result.effect_payloads[0]["target_unit_instance_ids"] == [source_unit_id, target_unit_id]
    assert effect["kind"] == "set_contextual_status"
    assert parameter_payload(compiled.rule_ir.clauses[0].effects[0].parameters) == {
        "owner": "your_army",
        "rules_context": "shadow_of_chaos",
        "status": "within_shadow_of_chaos",
    }


def test_phase17d_enemy_aura_keyword_gate_applies_only_to_matching_enemy_units() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_unit_id = "army-beta:intercessor-unit-2"
    target_unit_id = "army-alpha:intercessor-unit-3"
    excluded_unit_id = "army-alpha:intercessor-unit-1"
    compiled = _compiled(
        'Ded Glowy Ammo (Aura): While an enemy Infantry unit is within 6" of this '
        "model, subtract 1 from the Toughness characteristic of models in that unit."
    )

    state = _with_unit_keywords(
        state,
        unit_instance_id=target_unit_id,
        keywords=("INFANTRY",),
        faction_keywords=(),
    )
    state = _with_unit_keywords(
        state,
        unit_instance_id=excluded_unit_id,
        keywords=("VEHICLE",),
        faction_keywords=(),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=source_unit_id,
        pose=Pose.at(0.0, 0.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=target_unit_id,
        pose=Pose.at(2.0, 0.0),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=excluded_unit_id,
        pose=Pose.at(2.0, 1.0),
    )
    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            source_unit_instance_id=source_unit_id,
            source_model_instance_id=_unit_by_id(state, source_unit_id)
            .own_models[0]
            .model_instance_id,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [target_unit_id]
    assert result.effect_payloads[0]["target_unit_instance_ids"] == [target_unit_id]


def test_phase17d_this_model_aura_anchors_only_to_the_selected_source_model() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-alpha:intercessor-unit-3"
    source_models = _unit_by_id(state, source_unit_id).own_models
    state.battlefield_state = _with_unit_model_poses(
        state.battlefield_state,
        unit_instance_id=source_unit_id,
        poses=(
            Pose.at(0.0, 10.0),
            Pose.at(20.0, 10.0),
            Pose.at(30.0, 10.0),
            Pose.at(32.0, 10.0),
            Pose.at(34.0, 10.0),
        ),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=target_unit_id,
        pose=Pose.at(20.0, 10.0),
    )
    compiled = _compiled(
        'Aura: while a friendly unit is within 6" of this model, subtract 1 from wound rolls.'
    )

    distant_anchor = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            source_unit_instance_id=source_unit_id,
            source_model_instance_id=source_models[0].model_instance_id,
        ),
        registry=default_rule_execution_registry(),
    )
    nearby_anchor = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            source_unit_instance_id=source_unit_id,
            source_model_instance_id=source_models[1].model_instance_id,
        ),
        registry=default_rule_execution_registry(),
    )

    assert distant_anchor.aura_evaluations[0]["affected_unit_instance_ids"] == [source_unit_id]
    assert nearby_anchor.aura_evaluations[0]["affected_unit_instance_ids"] == [
        source_unit_id,
        target_unit_id,
    ]


def test_order64_repositioned_target_rechecks_aura_presence_and_distance() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_id = "army-alpha:intercessor-unit-1"
    target_id = "army-alpha:intercessor-unit-3"
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state, unit_instance_id=source_id, pose=Pose.at(10, 10)
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state, unit_instance_id=target_id, pose=Pose.at(12, 10)
    )
    compiled = _compiled(
        'Aura: while a friendly unit is within 6" of this unit, subtract 1 from wound rolls.'
    )

    def affected() -> bool:
        result = execute_rule_ir(
            rule_ir=compiled.rule_ir,
            context=_execution_context(state=state, source_unit_instance_id=source_id),
            registry=default_rule_execution_registry(),
        )
        return target_id in cast(
            list[str], result.aura_evaluations[0]["affected_unit_instance_ids"]
        )

    assert affected()
    assert state.battlefield_state is not None
    placed = state.battlefield_state
    state.battlefield_state = placed.without_unit_placement(target_id)
    assert not affected()
    state.battlefield_state = _with_unit_pose(
        placed, unit_instance_id=target_id, pose=Pose.at(35, 30)
    )
    assert not affected()
    state.battlefield_state = placed
    assert affected()


def test_phase17d_this_unit_aura_ignores_incidental_source_model_context() -> None:
    state = _battle_state_with_extra_friendly_unit()
    source_unit_id = "army-alpha:intercessor-unit-1"
    target_unit_id = "army-alpha:intercessor-unit-3"
    source_models = _unit_by_id(state, source_unit_id).own_models
    state.battlefield_state = _with_unit_model_poses(
        state.battlefield_state,
        unit_instance_id=source_unit_id,
        poses=(
            Pose.at(0.0, 10.0),
            Pose.at(20.0, 10.0),
            Pose.at(30.0, 10.0),
            Pose.at(32.0, 10.0),
            Pose.at(34.0, 10.0),
        ),
    )
    state.battlefield_state = _with_unit_pose(
        state.battlefield_state,
        unit_instance_id=target_unit_id,
        pose=Pose.at(20.0, 10.0),
    )
    compiled = _compiled(
        'Aura: while a friendly unit is within 6" of this unit, subtract 1 from wound rolls.'
    )

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=state,
            source_unit_instance_id=source_unit_id,
            source_model_instance_id=source_models[0].model_instance_id,
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.aura_evaluations[0]["affected_unit_instance_ids"] == [
        source_unit_id,
        target_unit_id,
    ]


def test_phase17d_this_model_aura_fails_closed_without_source_model() -> None:
    state = _battle_state_with_extra_friendly_unit()
    compiled = _compiled(
        'Aura: while a friendly unit is within 6" of this model, subtract 1 from wound rolls.'
    )

    with pytest.raises(
        GameLifecycleError,
        match="Aura this_model anchor requires source_model_instance_id",
    ):
        execute_rule_ir(
            rule_ir=compiled.rule_ir,
            context=_execution_context(
                state=state,
                source_unit_instance_id="army-alpha:intercessor-unit-1",
            ),
            registry=default_rule_execution_registry(),
        )


@pytest.mark.parametrize(
    ("object_reference", "error_message"),
    [
        (None, "Aura distance predicate requires object_reference"),
        ("that", "Aura distance predicate object_reference is unsupported"),
    ],
)
def test_phase17d_aura_fails_closed_for_missing_or_unsupported_source_reference(
    object_reference: str | None,
    error_message: str,
) -> None:
    state = _battle_state_with_extra_friendly_unit()
    compiled = _compiled(
        'Aura: while a friendly unit is within 6" of this unit, subtract 1 from wound rolls.'
    )
    rule_ir = _rule_ir_with_aura_object_reference(
        compiled.rule_ir,
        object_reference=object_reference,
    )

    with pytest.raises(GameLifecycleError, match=error_message):
        execute_rule_ir(
            rule_ir=rule_ir,
            context=_execution_context(
                state=state,
                source_unit_instance_id="army-alpha:intercessor-unit-1",
            ),
            registry=default_rule_execution_registry(),
        )


def test_phase17d_unsupported_rule_ir_produces_typed_unsupported_status() -> None:
    compiled = _compiled("Roll a scatter die and consult the legacy table.")

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.UNSUPPORTED
    assert result.reason == "unsupported_rule_ir"
    assert result.applied_clause_ids == ()
    assert result.event_records == ()


def test_phase17d_rule_ir_payload_round_trips_through_execution_result() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")
    rule_ir_payload = cast(RuleIRPayload, json.loads(compiled.rule_ir.to_json_bytes()))

    result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            record_persisting_effects=False,
            target_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        ),
        registry=default_rule_execution_registry(),
    )

    assert result.status is RuleExecutionStatus.APPLIED
    assert result.to_payload()["rule_ir_hash"] == rule_ir_payload["ir_hash"]
    assert "<" not in json.dumps(result.to_payload(), sort_keys=True)
    assert "object at 0x" not in json.dumps(result.to_payload(), sort_keys=True)


def test_phase17d_runtime_clause_payload_scopes_rule_ir_or_fails_closed() -> None:
    rule_ir = _champion_slayer_rule_ir()

    scoped = scoped_rule_ir_from_execution_payload(
        validate_json_value(
            {
                "rule_ir": rule_ir.to_payload(),
                "runtime_clause_id": "phase17d:test:champion-slayer:clause:002",
            }
        )
    )

    assert len(scoped.clauses) == 1
    assert scoped.clauses[0].clause_id == "phase17d:test:champion-slayer:clause:002"
    with pytest.raises(GameLifecycleError, match="runtime_clause_id is unknown"):
        scoped_rule_ir_from_execution_payload(
            validate_json_value(
                {
                    "rule_ir": rule_ir.to_payload(),
                    "runtime_clause_id": "phase17d:test:champion-slayer:clause:999",
                }
            )
        )


def test_phase17d_ability_bridge_executes_compiled_rule_ir_payload() -> None:
    compiled = _compiled("Add 1 to hit rolls for that unit.")
    record = AbilityCatalogRecord(
        record_id="phase17d:ability-record",
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="phase17d:datasheet",
        definition=AbilityDefinition(
            ability_id="phase17d:ability",
            name="phase17d generic ability",
            source_id="phase17d:ability-source",
            when_descriptor="phase17d:when",
            effect_descriptor="phase17d:effect",
            restrictions_descriptor="phase17d:restrictions",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": compiled.rule_ir.to_payload()}),
        ),
    )

    result = default_ability_handler_registry().execute(
        record=record,
        context=AbilityExecutionContext(
            game_id="phase17d-game",
            player_id="player-a",
            battle_round=1,
            phase=BattlePhaseKind.COMMAND,
            active_player_id="player-a",
            trigger_kind=TimingTriggerKind.ANY_PHASE,
            target_unit_instance_id="army-alpha:intercessor-unit-1",
            source_keywords=(),
            state=_battle_state_with_scenario(),
        ),
    )
    replay_payload = _json_object(result.replay_payload)
    rule_execution = _json_object(replay_payload["rule_execution"])

    assert result.status is AbilityResolutionStatus.APPLIED
    assert rule_execution["status"] == "applied"
    assert rule_execution["rule_ir_hash"] == compiled.rule_ir.ir_hash()


def test_phase17d_leading_model_condition_survives_destroyed_bodyguard() -> None:
    leader_state = _bodyguard_destroyed_attached_state()
    support_state = _bodyguard_destroyed_attached_state()
    bodyguard_state = _bodyguard_destroyed_attached_state()
    bodyguard_id = "army-alpha:bodyguard-unit"
    leader_id = "army-alpha:leader-unit"
    support_id = "army-alpha:support-unit"
    compiled = _compiled(_skullmaster_fury_text())

    leader_result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=leader_state,
            source_model_instance_id=f"{leader_id}:core-character-leader:001",
            target_unit_instance_ids=(leader_id,),
            phase=BattlePhaseKind.CHARGE,
        ),
        registry=default_rule_execution_registry(),
    )
    support_result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=support_state,
            source_unit_instance_id=support_id,
            target_unit_instance_ids=(support_id,),
            phase=BattlePhaseKind.CHARGE,
        ),
        registry=default_rule_execution_registry(),
    )
    bodyguard_result = execute_rule_ir(
        rule_ir=compiled.rule_ir,
        context=_execution_context(
            state=bodyguard_state,
            source_unit_instance_id=bodyguard_id,
            target_unit_instance_ids=(leader_id,),
            phase=BattlePhaseKind.CHARGE,
        ),
        registry=default_rule_execution_registry(),
    )

    assert len(leader_state.army_definitions[0].attached_units) == 1
    assert leader_state.unit_started_battle_as_attached_leader_or_support(leader_id)
    assert leader_state.unit_started_battle_as_attached_leader_or_support(support_id)
    assert (
        GameState.from_payload(leader_state.to_payload()).to_payload() == leader_state.to_payload()
    )
    assert leader_result.status is RuleExecutionStatus.APPLIED
    assert support_result.status is RuleExecutionStatus.APPLIED
    assert bodyguard_result.status is RuleExecutionStatus.INVALID
    assert bodyguard_result.reason == "condition_not_met:this_model_leading_unit"


__all__: list[str] = []
__all__ += ["Any", "ArmyMusterRequest", "AttachmentDeclaration", "BattlefieldPlacementKind"]
__all__ += ["BattlefieldRuntimeState", "BattlefieldScenario", "CatalogAbilitySupport"]
__all__ += ["CommandPointLedger", "CommandPointRuleMutationResult", "CommandPointSourceKind"]
__all__ += ["CompiledRuleSource", "DatasheetAbilityDescriptor", "DetachmentSelection"]
__all__ += ["EffectError", "GameConfig", "KeywordGate", "MissionSetup", "ModelInstance"]
__all__ += ["ModelProfileSelection", "ObjectiveRuleScope", "ParameterizedSubmission"]
__all__ += ["RULE_FREQUENCY_LIMIT_CONSUMED_EVENT", "PathWitness", "ReactionWindow", "RuleClause"]
__all__ += ["RuleExecutionContext", "RuleExecutionRegistry", "RuleExecutionResult"]
__all__ += ["RuleRuntimeBinding", "RuleSourceText", "RuleTrigger", "RuleTriggerKind"]
__all__ += ["SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE"]
__all__ += ["SOURCE_KEYWORD_SEQUENCE_PARTS", "SecondaryMissionChoice", "SecondaryMissionMode"]
__all__ += ["TextSpan", "TimingWindow", "TimingWindowDescriptor", "UnitInstance"]
__all__ += ["UnitMusterSelection", "UnitPlacement", "WeaponKeyword", "WeaponProfile"]
__all__ += ["WeaponProfileModifierContext", "_ability_record"]
__all__ += ["_attached_leader_support_muster_request", "_champion_slayer_clause_record"]
__all__ += ["_champion_slayer_descriptor", "_command_point_spend_rule_ir", "_destroy_model"]
__all__ += ["_mission_setup", "_muster_request_with_unit_ids", "_mustered_armies"]
__all__ += ["_mustered_armies_with_extra_friendly_unit", "_noop_rule_handler", "_scenario"]
__all__ += ["_scenario_with_extra_friendly_unit", "apply_command_point_rule_mutation"]
__all__ += ["chapter_approved_2026_27_mission_pack", "command_point_operation_and_delta"]
__all__ += ["command_point_operation_shape_reason", "command_point_rule_unavailable_reason"]
__all__ += ["compile_rule_source_text", "datasheet_keyword_lexicon_source"]
__all__ += ["destroy_model_by_rule", "ensure_army_mustered_events_for_fixture"]
__all__ += ["execute_abilities_from_index", "hashlib", "initial_command_point_ledgers"]
__all__ += ["initial_victory_point_ledgers", "rule_execution_status_from_token"]
__all__ += ["rule_ir_from_execution_payload", "with_unit_keywords"]
