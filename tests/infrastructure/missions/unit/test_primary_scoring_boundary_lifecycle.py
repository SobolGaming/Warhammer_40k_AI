from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase17n_primary_scoring_boundary_lifecycle import (
    _OC_SOURCE_RULE_ID,
    GENERIC_RULE_IR_EFFECT_INDEX_KEY,
    GENERIC_RULE_IR_EXECUTION_CONTEXT_KEY,
    GENERIC_RULE_IR_EXECUTION_EVENT_ID_KEY,
    GENERIC_RULE_IR_HASH_KEY,
    GENERIC_RULE_IR_SOURCE_ID_KEY,
    PARAMETERIZED_DECISION_OPTION_ID,
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
    PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
    PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION,
    PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED,
    PRIMARY_SCORING_PENDING_WINDOW_RETURN_ON_DEATH,
    RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE,
    RULE_EXECUTION_VICTORY_POINTS_AWARDED_EVENT_TYPE,
    SCORING_COMMIT_CHECKPOINT_HASH_KEY,
    SCORING_COMMIT_CHECKPOINT_ID_KEY,
    SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY,
    SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY,
    SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE,
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    SOURCE_KEYWORD_SEQUENCE_PARTS,
    SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
    TABLE_QUARTER_NORTH_WEST,
    ArmyCatalog,
    BattlePhase,
    BattlePhaseKind,
    DecisionController,
    DecisionOption,
    DecisionRequest,
    DecisionResult,
    DestructionSourceKind,
    DiceExpression,
    DiceRollManager,
    DiceRollResult,
    DiceRollSpec,
    EventLog,
    EventRecord,
    GameConfig,
    GameLifecycle,
    GameLifecycleError,
    GameLifecyclePayload,
    GameLifecycleStage,
    GameState,
    JsonValue,
    ModelDestructionAttribution,
    ModelPlacement,
    ModifierOperation,
    ModifierTerm,
    ObjectiveControlModifierBinding,
    ObjectiveControlModifierContext,
    ObjectiveControlRecord,
    ObjectiveControlRecordAuthority,
    ObjectiveControlTiming,
    ObjectiveMarkerRole,
    ObjectiveRuleScope,
    PendingReturnOnDeath,
    Pose,
    PrimaryBattlefieldDepartureState,
    PrimaryMissionBoundaryCheckpoint,
    PrimaryMissionBoundaryModelState,
    PrimaryMissionObjectiveControlModifierSource,
    PrimaryScoringBoundaryKind,
    PrimaryScoringBoundaryLifecyclePayload,
    PrimaryScoringBoundaryStatus,
    PrimaryScoringRulesUnitPositionWitnessPayload,
    PrimaryScoringStateEvidence,
    PrimaryScoringStateEvidencePayload,
    PrimaryTerritoryUnitWitness,
    RegisteredPhase11FCapProbe,
    ReturnDestroyedTargetScope,
    ReturnRestoreWoundsMode,
    RuleClause,
    RuleEffectKind,
    RuleEffectSpec,
    RuleExecutionContext,
    RuleExecutionStatus,
    RuleIR,
    RuleParameter,
    RulesetDescriptor,
    RuleSourceText,
    RuntimeModifierRegistry,
    RuntimeRuleIRAuthorityIndex,
    RuntimeRuleIRSourceKey,
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    SecondaryMissionMode,
    SecondaryScoringConditionContext,
    SecondaryScoringProviderKind,
    StickyObjectiveControlState,
    UnitInstance,
    UnitPlacement,
    VictoryPointAward,
    VictoryPointCapBucket,
    VictoryPointSourceKind,
    VictoryPointTransaction,
    _add_unit_keyword,
    _append_player_transaction_from_award,
    _assert_scoring_commit_differs_from_oc_checkpoint,
    _authenticated_move_unit_to,
    _award_from_transaction,
    _battlefield_dominance_lifecycle,
    _bring_it_down_player_a_scored_lifecycle,
    _card_for_state_backed_scoring,  # pyright: ignore[reportPrivateUsage]
    _checkpoint_with_model_states,
    _compiled_generic_vp_rule_ir,
    _defend_stronghold_ready_lifecycle,
    _destroy_all_models,
    _destroy_first_model,
    _destroy_model_with_event,
    _destroy_unit_with_events,
    _emit_objective_control_boundary_event_if_missing,  # pyright: ignore[reportPrivateUsage]
    _emit_oc_event,
    _empty_rule_ir_authority_index,
    _execute_generic_vp_on_lifecycle,
    _expected_state_backed_secondary_award,  # pyright: ignore[reportPrivateUsage]
    _fabricated_generic_rule_ir_metadata,
    _first_unit,
    _fixed_secondary_record_ids,
    _generic_rule_ir_transaction,
    _generic_vp_clause_and_effect,
    _generic_vp_execution_context,
    _json_list,
    _json_map,
    _json_object,
    _ledger_payload,
    _legacy_score_secondary_mission_award,  # pyright: ignore[reportPrivateUsage]
    _offset_checkpoint_model_state,
    _pending_command_boundary_lifecycle,
    _pending_final_turn_end_boundary_lifecycle,
    _place_in_player_deployment_zone_away_from_home,
    _place_player_away_from_objectives,
    _place_player_on_role,
    _place_unit_interior_non_overlapping,
    _queue_pending_window,
    _record_for_binding,  # pyright: ignore[reportPrivateUsage]
    _registered_phase11f_cap_probe_award,
    _rehash_evidence_transactions_and_lifecycles,
    _rehash_lifecycle_row,
    _reject_duplicate_tactical_source,  # pyright: ignore[reportPrivateUsage]
    _replace_player_transaction,
    _replace_secondary_scoring_evidence_binding_from_payload,
    _require_registered_phase11f_cap_probe,
    _return_destroyed_unit,
    _rule_ir_authority_index,
    _same_boundary_bring_it_down_and_assassination_lifecycle,
    _same_boundary_two_player_bring_it_down_lifecycle,
    _scored_command_boundary_after_mutation,
    _scored_determined_acquisition_command_lifecycle,
    _scored_reconnaissance_turn_end_lifecycle,
    _secondary_transaction,
    _secondary_transaction_payload,
    _secondary_transaction_payloads,
    _set_unit_starting_wounds,
    _single_mode_bring_it_down_lifecycle,
    _sticky_state_for,
    _swap_secondary_scoring_evidence_bindings,
    _tactical_secondary_amount,
    _transaction_objective_control_record_id,  # pyright: ignore[reportPrivateUsage]
    _transaction_record_id,
    _two_defender_battlefield_dominance_lifecycle,
    _two_model_battlefield_dominance_lifecycle,
    _two_player_bring_it_down_scored_lifecycle,
    _two_round_bring_it_down_lifecycle,
    _uncapped_award_from_transaction,  # pyright: ignore[reportPrivateUsage]
    _validate_registered_phase11f_cap_probe,  # pyright: ignore[reportPrivateUsage]
    _validate_scored_tactical_card_bindings,  # pyright: ignore[reportPrivateUsage]
    _validate_secondary_primary_closure,  # pyright: ignore[reportPrivateUsage]
    _zone_anchor_away_from_home,
    append_authenticated_normal_move,
    apply_generic_rule_ir_victory_points,
    apply_return_on_death_placement_decision,
    army_muster_request,
    bind_state_backed_secondary_scoring_commit,
    bound_primary_scoring_commit_checkpoint,
    build_primary_rules_unit_membership_from_model_placements,
    build_primary_scoring_spatial_evidence,
    build_primary_scoring_state_evidence,
    canonical_json,
    canonical_payload_sha256,
    compile_rule_source_text,
    complete_setup_through_gate,
    create_deterministic_battlefield_scenario,
    deepcopy,
    default_rule_execution_registry,
    default_unit_selection,
    enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary,
    enemy_unit_ids_in_player_deployment_zone_from_battlefield,
    enemy_unit_ids_in_player_deployment_zone_from_model_placements,
    escape,
    execute_rule_ir,
    generic_rule_ir_secondary_award,
    is_registered_phase11f_cap_probe,
    json_loads,
    mark_pending_primary_scoring_boundaries,
    mission_scoring_policies_from_setup,
    mustered_armies,
    next_generic_rule_ir_victory_point_event_id,
    pending_primary_scoring_boundary_keys,
    phase11c_mission_setup,
    phase17n_event_setup,
    phase17n_state_with_setup,
    primary_mission_model_placements_from_checkpoint,
    pytest,
    record_new_primary_unit_destruction_events,
    record_primary_battlefield_departure_event,
    record_primary_destroyed_model_departures,
    record_primary_scoring_state_evidence,
    record_primary_turn_start_evidence_for_fixture,
    record_secondary_destruction_for_fixture,
    registered_phase11f_cap_probe,
    replace,
    request_mission_action_start,
    require_generic_rule_ir_loaded_authority,
    require_source_backed_secondary_cap_bucket,
    require_state_backed_secondary_scoring_commit,
    resolve_primary_scoring_boundary_lifecycle,
    rules_unit_objective_proximity_witness,
    ruleset,
    score_primary_objective_control_boundary,
    score_secondary_mission_from_state,
    secondary_choice,
    secondary_scoring_provider_kind_from_metadata,
    secondary_scoring_provider_kind_from_token,
    state_backed_secondary_binding_identity,
    state_backed_secondary_objective_control_record_id,
    validate_generic_rule_ir_secondary_award,
    validate_json_value,
    validate_legacy_phase11f_secondary_award,
    validate_primary_scoring_spatial_rows_from_checkpoint,
    validate_secondary_award_semantics,
    validate_secondary_generic_rule_ir_restore_authority,
    validate_secondary_transaction_semantics,
    validate_state_backed_secondary_award_binding,
    validate_state_backed_secondary_ledger_binding,
    with_model_offsets,
    with_unit_keywords,
)


def test_scoreable_command_boundary_restores_while_end_phase_decision_is_pending() -> None:
    lifecycle = _pending_command_boundary_lifecycle()
    payload = lifecycle.to_payload()
    restored = GameLifecycle.from_payload(deepcopy(payload))
    assert restored.to_payload() == payload
    state = restored.state
    assert state is not None
    assert pending_primary_scoring_boundary_keys(state=state)
    assert all(
        row.status is PrimaryScoringBoundaryStatus.PENDING
        for row in state.primary_scoring_boundary_lifecycles
    )
    assert state.primary_scoring_state_evidence_records == []


def test_final_turn_end_boundary_restores_while_step_four_choice_is_pending() -> None:
    lifecycle = _pending_final_turn_end_boundary_lifecycle()
    payload = lifecycle.to_payload()
    restored = GameLifecycle.from_payload(deepcopy(payload))
    assert restored.to_payload() == payload
    state = restored.state
    assert state is not None
    assert any(
        row.scoring_boundary_kind.value == "end_of_battle"
        and row.status is PrimaryScoringBoundaryStatus.PENDING
        for row in state.primary_scoring_boundary_lifecycles
    )


def test_resolving_pending_command_boundary_closes_exactly_once() -> None:
    lifecycle = _pending_command_boundary_lifecycle()
    state = lifecycle.state
    assert state is not None
    request = lifecycle.decision_controller.queue.peek_next()
    lifecycle.decision_controller.submit_result(
        DecisionResult.for_request(
            result_id=f"{request.request_id}-resolved",
            request=request,
            selected_option_id="continue",
        )
    )
    record = state.objective_control_records[-1]
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=lifecycle.decision_controller.event_log,
    )
    evidence_ids = tuple(
        evidence.evidence_id for evidence in state.primary_scoring_state_evidence_records
    )
    transaction_ids = tuple(
        transaction.transaction_id
        for ledger in state.victory_point_ledgers
        for transaction in ledger.transactions
        if transaction.source_kind is VictoryPointSourceKind.PRIMARY
    )
    assert evidence_ids
    assert all(
        row.status is PrimaryScoringBoundaryStatus.RESOLVED
        for row in state.primary_scoring_boundary_lifecycles
    )
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert (
        tuple(evidence.evidence_id for evidence in state.primary_scoring_state_evidence_records)
        == evidence_ids
    )
    assert (
        tuple(
            transaction.transaction_id
            for ledger in state.victory_point_ledgers
            for transaction in ledger.transactions
            if transaction.source_kind is VictoryPointSourceKind.PRIMARY
        )
        == transaction_ids
    )
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()


def test_restore_rejects_pending_boundary_without_queue_authority() -> None:
    lifecycle = _pending_command_boundary_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    payload["decisions"]["queue"]["pending_requests"] = []
    with pytest.raises(
        GameLifecycleError,
        match=escape("Pending Primary scoring boundary has no corresponding queue authority."),
    ):
        GameLifecycle.from_payload(payload)


def test_unmet_secondary_leaves_lifecycle_payload_unchanged_when_primary_would_score() -> None:
    lifecycle = _battlefield_dominance_lifecycle(
        phase=BattlePhase.FIGHT,
        battle_round=2,
        player_a_secondary=SecondaryMissionMode.TACTICAL,
    )
    state = lifecycle.state
    assert state is not None
    _place_player_on_role(state, player_id="player-a", role=ObjectiveMarkerRole.CENTRAL)
    _place_player_away_from_objectives(state, player_id="player-b")
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            battle_round=2,
            source_result_id="p2-unmet-bring-it-down",
        )
    )
    before = canonical_json(lifecycle.to_payload())
    with pytest.raises(
        GameLifecycleError,
        match=escape("State-backed secondary mission requirements are not met."),
    ):
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=lifecycle.decision_controller.event_log,
        )
    assert canonical_json(lifecycle.to_payload()) == before
    assert state.objective_control_records == []
    assert state.primary_scoring_state_evidence_records == []


def test_unmet_secondary_at_zero_award_primary_boundary_leaves_no_oc_or_evidence() -> None:
    lifecycle = _battlefield_dominance_lifecycle(
        phase=BattlePhase.FIGHT,
        battle_round=1,
        player_a_secondary=SecondaryMissionMode.TACTICAL,
    )
    state = lifecycle.state
    assert state is not None
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            battle_round=1,
            source_result_id="p2-zero-award-bring-it-down",
        )
    )
    with pytest.raises(
        GameLifecycleError,
        match=escape("State-backed secondary mission requirements are not met."),
    ):
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=lifecycle.decision_controller.event_log,
        )
    assert state.objective_control_records == []
    assert state.objective_control_record_authorities == []
    assert state.primary_scoring_state_evidence_records == []


def test_successful_state_backed_scoring_restores_full_lifecycle_without_manual_event() -> None:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.FIGHT, battle_round=2)
    state = lifecycle.state
    assert state is not None
    state.active_player_id = "player-b"
    _place_player_on_role(state, player_id="player-a", role=ObjectiveMarkerRole.ATTACKER_HOME)
    _place_player_on_role(state, player_id="player-b", role=ObjectiveMarkerRole.DEFENDER_HOME)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            battle_round=2,
            source_result_id="p2-defend-stronghold",
        )
    )
    scored = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert scored.status.value == "scored"
    assert any(
        event.event_type == "end_boundary_objective_control_determined"
        for event in lifecycle.decision_controller.event_log.records
    )
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()
    assert restored.decision_controller.to_payload() == lifecycle.decision_controller.to_payload()


@pytest.mark.parametrize("drift_kind", ["player", "record", "mission_setup"])
def test_secondary_policy_rejects_condition_context_invocation_drift(
    drift_kind: str,
) -> None:
    _lifecycle, state = _defend_stronghold_ready_lifecycle()
    setup = state.mission_setup
    assert setup is not None
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=None,
    )
    context = SecondaryScoringConditionContext(
        record=record,
        mission_setup=setup,
        player_id="player-a",
        unit_destruction_states=(),
        objective_cleanse_states=(),
        terrain_plunder_states=(),
        enemy_unit_ids_in_player_deployment_zone=(),
        starting_strength_records=(),
    )
    if drift_kind == "player":
        context = replace(context, player_id="player-b")
    elif drift_kind == "record":
        context = replace(context, record=replace(record, record_id=f"{record.record_id}-drift"))
    else:
        context = replace(
            context,
            mission_setup=replace(setup, source_version=f"{setup.source_version}-drift"),
        )

    policies = mission_scoring_policies_from_setup(setup)
    with pytest.raises(
        GameLifecycleError,
        match=rf"condition context {drift_kind.replace('_', ' ')} drift",
    ):
        policies.secondary_award_from_mission_state(
            player_id="player-a",
            battle_round=record.battle_round,
            phase=record.phase,
            secondary_mission_id="defend-stronghold",
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            hidden=False,
            record=record,
            mission_setup=setup,
            unit_destruction_states=(),
            objective_cleanse_states=(),
            terrain_plunder_states=(),
            enemy_unit_ids_in_player_deployment_zone=(),
            condition_context=context,
        )


def test_secondary_ledger_failure_rolls_back_entire_aggregate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    original = GameState.award_victory_points

    def _fail_secondary(self: GameState, award: VictoryPointAward) -> VictoryPointTransaction:
        if self is state and award.source_kind is VictoryPointSourceKind.TACTICAL_SECONDARY:
            raise GameLifecycleError("injected secondary ledger failure")
        return original(self, award)

    monkeypatch.setattr(GameState, "award_victory_points", _fail_secondary)
    before = canonical_json(lifecycle.to_payload())
    with pytest.raises(GameLifecycleError, match="injected secondary ledger failure"):
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=lifecycle.decision_controller.event_log,
        )
    assert canonical_json(lifecycle.to_payload()) == before


def test_tactical_card_failure_rolls_back_ledgers_and_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    original = GameState.replace_secondary_mission_card_state

    def _fail_card(self: GameState, card_state: SecondaryMissionCardState) -> None:
        if self is state:
            raise GameLifecycleError("injected tactical card failure")
        original(self, card_state)

    monkeypatch.setattr(GameState, "replace_secondary_mission_card_state", _fail_card)
    before = canonical_json(lifecycle.to_payload())
    with pytest.raises(GameLifecycleError, match="injected tactical card failure"):
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=lifecycle.decision_controller.event_log,
        )
    assert canonical_json(lifecycle.to_payload()) == before


def test_second_state_backed_scoring_call_is_deterministic() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    first = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    after_first = canonical_json(lifecycle.to_payload())
    second = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert second == first
    assert canonical_json(lifecycle.to_payload()) == after_first
    primary_ids = tuple(
        transaction.transaction_id
        for ledger in state.victory_point_ledgers
        for transaction in ledger.transactions
        if transaction.source_kind is VictoryPointSourceKind.PRIMARY
    )
    secondary_ids = tuple(
        transaction.transaction_id
        for ledger in state.victory_point_ledgers
        for transaction in ledger.transactions
        if transaction.source_kind is VictoryPointSourceKind.TACTICAL_SECONDARY
    )
    assert len(primary_ids) == len(set(primary_ids))
    assert len(secondary_ids) == 1


def test_primary_rescore_after_tactical_card_commit_uses_frozen_evidence() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    turn_end_records = tuple(
        record
        for record in state.objective_control_records
        if record.timing is ObjectiveControlTiming.TURN_END
    )
    assert len(turn_end_records) == 1
    evidence_before = tuple(state.primary_scoring_state_evidence_records)
    ledgers_before = tuple(state.victory_point_ledgers)
    score_primary_objective_control_boundary(
        state=state,
        record=turn_end_records[0],
        end_of_battle=False,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert tuple(state.primary_scoring_state_evidence_records) == evidence_before
    assert tuple(state.victory_point_ledgers) == ledgers_before


def test_authenticated_destruction_between_oc_and_scoring_round_trips() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="destroy")
    payload = lifecycle.to_payload()
    restored = GameLifecycle.from_payload(deepcopy(payload))
    assert restored.to_payload() == payload
    _assert_scoring_commit_differs_from_oc_checkpoint(lifecycle)


def test_authenticated_return_on_death_between_oc_and_scoring_round_trips() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="return_on_death")
    payload = lifecycle.to_payload()
    restored = GameLifecycle.from_payload(deepcopy(payload))
    assert restored.to_payload() == payload
    _assert_scoring_commit_differs_from_oc_checkpoint(lifecycle)


@pytest.mark.parametrize(
    ("surviving_model", "later_destroy_survivor"), [(False, False), (True, False), (True, True)]
)
def test_restore_rejects_coordinated_return_setup_history_tampering(
    surviving_model: bool, later_destroy_survivor: bool
) -> None:
    lifecycle = _two_model_battlefield_dominance_lifecycle(
        phase=BattlePhase.COMMAND, battle_round=2
    )
    state = lifecycle.state
    assert state is not None
    target = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    assert state.battlefield_state is not None
    assert state.mission_setup is not None
    marker = next(
        marker
        for marker in state.mission_setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(
            with_model_offsets(
                state.battlefield_state.unit_placement_by_id(target.unit_instance_id),
                marker,
                offsets=((0.0, 0.0), (2.0, 0.0)),
            )
        )
    )
    original_placement = _destroy_unit_with_events(
        state=state,
        decisions=lifecycle.decision_controller,
        unit_instance_id=target.unit_instance_id,
        return_model_only=surviving_model,
        leave_surviving_model=surviving_model,
    )
    _return_destroyed_unit(
        state=state,
        decisions=lifecycle.decision_controller,
        original_placement=original_placement,
        return_model_only=surviving_model,
    )
    if later_destroy_survivor:
        from tests.destruction_occurrence_fixture_helpers import destroy_rule_model_for_fixture

        source = state.army_definitions[0].units[0]
        destroy_rule_model_for_fixture(
            state=state,
            decisions=lifecycle.decision_controller,
            model_id=original_placement.model_placements[1].model_instance_id,
            destroying_player_id="player-a",
            source_unit_id=source.unit_instance_id,
            source_model_id=source.own_models[0].model_instance_id,
        )
    payload = lifecycle.to_payload()
    assert GameLifecycle.from_payload(deepcopy(payload)).to_payload() == payload
    completion = next(
        event
        for event in payload["decisions"]["event_log"]
        if event["event_type"] == "return_on_death_set_back_up_completed"
    )
    detail = completion["payload"]
    assert isinstance(detail, dict)
    assert detail["unit_set_up"] is not surviving_model
    detail["unit_set_up"] = surviving_model
    raw_state = payload["state"]
    assert raw_state is not None
    if surviving_model:
        placement = detail["placement"]
        assert isinstance(placement, dict)
        raw_state["phase_movement_history"].append(
            {
                "event_id": completion["event_id"],
                "battle_round": state.battle_round,
                "turn_player_id": "player-a",
                "phase": BattlePhase.COMMAND.value,
                "unit_instance_id": target.unit_instance_id,
                "model_instance_ids": [original_placement.model_placements[0].model_instance_id],
                "is_surge": False,
                "is_ingress": False,
                "setup_kind": "return_to_battlefield",
            }
        )
    else:
        raw_state["phase_movement_history"] = []
    with pytest.raises(GameLifecycleError, match=r"Return-on-death setup.*authority"):
        GameLifecycle.from_payload(payload)


def test_return_setup_authority_is_bound_to_the_accepted_target() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="return_on_death")
    payload = lifecycle.to_payload()
    assert lifecycle.state is not None
    completion = next(
        event
        for event in payload["decisions"]["event_log"]
        if event["event_type"] == "return_on_death_set_back_up_completed"
    )
    detail = completion["payload"]
    assert isinstance(detail, dict)
    detail["unit_instance_id"] = lifecycle.state.army_definitions[0].units[0].unit_instance_id
    detail["unit_set_up"] = False
    assert payload["state"] is not None
    payload["state"]["phase_movement_history"] = []
    with pytest.raises(GameLifecycleError, match="Return-on-death setup rules-unit authority"):
        GameLifecycle.from_payload(payload)


def test_partial_return_repeated_destruction_projects_only_fresh_model() -> None:
    lifecycle = _two_model_battlefield_dominance_lifecycle(
        phase=BattlePhase.COMMAND,
        battle_round=2,
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert state.mission_setup is not None
    target = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    model_ids = tuple(sorted(model.model_instance_id for model in target.own_models))
    assert len(model_ids) == 2
    marker = next(
        candidate
        for candidate in state.mission_setup.objective_markers
        if candidate.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    placement = state.battlefield_state.unit_placement_by_id(target.unit_instance_id)
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(
            with_model_offsets(
                placement,
                marker,
                offsets=((0.0, 0.0), (2.0, 0.0)),
            )
        )
    )

    original_placement = _destroy_unit_with_events(
        state=state,
        decisions=lifecycle.decision_controller,
        unit_instance_id=target.unit_instance_id,
        return_model_only=True,
    )
    first_projection = state.secondary_unit_destruction_states[-1]
    assert (
        tuple(model.model_instance_id for model in first_projection.destroyed_models) == model_ids
    )

    returned_model_id = original_placement.model_placements[0].model_instance_id
    _return_destroyed_unit(
        state=state,
        decisions=lifecycle.decision_controller,
        original_placement=original_placement,
        return_model_only=True,
    )
    target_after_return = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    assert tuple(model.model_instance_id for model in target_after_return.alive_own_models()) == (
        returned_model_id,
    )

    second_projection = record_secondary_destruction_for_fixture(
        state,
        destroyed_unit_instance_id=target.unit_instance_id,
        destroying_player_id="player-a",
        source_id="phase17n-partial-return-second-destruction",
        event_log=lifecycle.decision_controller.event_log,
    )
    assert tuple(model.model_instance_id for model in second_projection.destroyed_models) == (
        returned_model_id,
    )

    payload = lifecycle.to_payload()
    restored = GameLifecycle.from_payload(deepcopy(payload))
    assert restored.to_payload() == payload


def test_coordinated_rewrite_of_post_oc_mutation_and_scoring_checkpoint_fails() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="move")
    payload = deepcopy(lifecycle.to_payload())
    events = payload["decisions"]["event_log"]
    commit_event = next(
        event for event in events if event["event_type"] == PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT
    )
    assert isinstance(commit_event, dict)
    raw_payload = commit_event["payload"]
    assert isinstance(raw_payload, dict)
    checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(raw_payload["checkpoint"])
    rewritten_states = tuple(_offset_checkpoint_model_state(row) for row in checkpoint.model_states)
    rewritten = PrimaryMissionBoundaryCheckpoint.create(
        boundary_kind=checkpoint.boundary_kind,
        game_id=checkpoint.game_id,
        player_id=checkpoint.player_id,
        active_player_id=checkpoint.active_player_id,
        battle_round=checkpoint.battle_round,
        phase=checkpoint.phase,
        battlefield_id=checkpoint.battlefield_id,
        model_states=rewritten_states,
        attached_unit_formation_jsons=checkpoint.attached_unit_formation_jsons,
        battle_shocked_unit_instance_ids=checkpoint.battle_shocked_unit_instance_ids,
        advanced_unit_state_jsons=checkpoint.advanced_unit_state_jsons,
        fell_back_unit_state_jsons=checkpoint.fell_back_unit_state_jsons,
        shot_unit_instance_ids=checkpoint.shot_unit_instance_ids,
        objective_control_modifier_sources=checkpoint.objective_control_modifier_sources,
        active_primary_marker_jsons=checkpoint.active_primary_marker_jsons,
        active_secondary_mission_card_jsons=checkpoint.active_secondary_mission_card_jsons,
        completed_mission_action_state_jsons=checkpoint.completed_mission_action_state_jsons,
        primary_unit_destruction_state_jsons=checkpoint.primary_unit_destruction_state_jsons,
        starting_strength_record_jsons=checkpoint.starting_strength_record_jsons,
        active_secondary_mission_ids=checkpoint.active_secondary_mission_ids,
        mission_action_prior_use_jsons=checkpoint.mission_action_prior_use_jsons,
    )
    raw_payload["checkpoint"] = rewritten.to_payload()
    evidence = payload["state"]["primary_scoring_state_evidence_records"][0]
    old_evidence_id = evidence["evidence_id"]
    evidence["scoring_commit_checkpoint_id"] = rewritten.checkpoint_id
    evidence["scoring_commit_checkpoint_hash"] = rewritten.checkpoint_hash
    content = {
        key: value for key, value in evidence.items() if key not in {"evidence_id", "evidence_hash"}
    }
    digest = canonical_payload_sha256(content)
    evidence["evidence_id"] = f"primary-scoring-state-evidence:{digest}"
    evidence["evidence_hash"] = digest
    for ledger in payload["state"]["victory_point_ledgers"]:
        for transaction in ledger["transactions"]:
            metadata = transaction["metadata"]
            if not isinstance(metadata, dict):
                continue
            if metadata.get("primary_scoring_state_evidence_id") != old_evidence_id:
                continue
            metadata["primary_scoring_state_evidence_id"] = evidence["evidence_id"]
            metadata["primary_scoring_state_evidence_hash"] = digest
    for row in payload["state"]["primary_scoring_boundary_lifecycles"]:
        if row["evidence_id"] != old_evidence_id:
            continue
        row["evidence_id"] = evidence["evidence_id"]
        row["scoring_commit_checkpoint_id"] = rewritten.checkpoint_id
        row["scoring_commit_checkpoint_hash"] = rewritten.checkpoint_hash
        lifecycle_content = {
            key: value
            for key, value in row.items()
            if key not in {"lifecycle_id", "lifecycle_hash"}
        }
        lifecycle_digest = canonical_payload_sha256(lifecycle_content)
        row["lifecycle_id"] = f"primary-scoring-boundary-lifecycle:{lifecycle_digest}"
        row["lifecycle_hash"] = lifecycle_digest
    with pytest.raises(GameLifecycleError, match="movement history"):
        GameLifecycle.from_payload(payload)


def test_evidence_without_scoring_commit_checkpoint_event_fails_restore() -> None:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.COMMAND, battle_round=2)
    state = lifecycle.state
    assert state is not None
    decisions = lifecycle.decision_controller
    record = state.determine_current_phase_end_objective_control()
    _emit_oc_event(decisions=decisions, record=record)
    evidence = build_primary_scoring_state_evidence(
        scoring_player_id=record.active_player_id,
        state=state,
        record=record,
        end_of_battle=False,
    )
    assert state.mission_setup is not None
    awards = mission_scoring_policies_from_setup(
        state.mission_setup
    ).primary_awards_from_objective_control(
        record=record,
        authoritative_state=state,
        end_of_battle=False,
    )
    record_primary_scoring_state_evidence(state=state, evidence=evidence)
    for award in awards:
        state.award_victory_points(award)
    resolve_primary_scoring_boundary_lifecycle(
        scoring_player_id=record.active_player_id,
        state=state,
        record=record,
        scoring_boundary_kind=PrimaryScoringBoundaryKind.ORDINARY,
        scoring_commit_checkpoint_id=evidence.scoring_commit_checkpoint_id,
        scoring_commit_checkpoint_hash=evidence.scoring_commit_checkpoint_hash,
        evidence_id=evidence.evidence_id,
    )
    with pytest.raises(
        GameLifecycleError,
        match=escape(
            "Primary scoring position evidence requires exactly one scoring-commit checkpoint."
        ),
    ):
        GameLifecycle.from_payload(lifecycle.to_payload())


def test_forged_table_quarter_witness_fails_restore_after_coordinated_rehash() -> None:
    lifecycle = _scored_reconnaissance_turn_end_lifecycle()
    state = lifecycle.state
    assert state is not None
    payload = deepcopy(lifecycle.to_payload())
    evidence = payload["state"]["primary_scoring_state_evidence_records"][0]
    spatial_rows = evidence["primary_scoring_spatial_evidence_by_player_id"]
    assert spatial_rows
    unit = next(
        candidate
        for army in state.army_definitions
        if army.player_id == "player-a"
        for candidate in army.units
    )
    spatial_rows[0]["table_quarter_unit_witnesses"] = [
        {
            "rules_unit_instance_id": unit.unit_instance_id,
            "quarter_id": TABLE_QUARTER_NORTH_WEST,
            "model_instance_ids": [unit.own_models[0].model_instance_id],
        }
    ]
    _rehash_evidence_transactions_and_lifecycles(payload, evidence=evidence)
    with pytest.raises(GameLifecycleError, match="spatial evidence drifted"):
        GameLifecycle.from_payload(payload)


def test_forged_territory_witness_fails_restore_after_coordinated_rehash() -> None:
    lifecycle = _scored_determined_acquisition_command_lifecycle()
    state = lifecycle.state
    assert state is not None
    payload = deepcopy(lifecycle.to_payload())
    evidence = payload["state"]["primary_scoring_state_evidence_records"][0]
    spatial_rows = evidence["primary_scoring_spatial_evidence_by_player_id"]
    assert spatial_rows
    territory_row = next(
        row
        for row in spatial_rows
        if "each_controlled_objective_in_opponent_territory" in row["requested_condition_ids"]
    )
    assert state.mission_setup is not None
    marker_id = next(
        marker.objective_marker_id
        for marker in state.mission_setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.DEFENDER_HOME
    )
    authentic = list(territory_row["opponent_territory_objective_ids"])
    if marker_id in authentic:
        territory_row["opponent_territory_objective_ids"] = [
            objective_id for objective_id in authentic if objective_id != marker_id
        ]
    else:
        territory_row["opponent_territory_objective_ids"] = [*authentic, marker_id]
    _rehash_evidence_transactions_and_lifecycles(payload, evidence=evidence)
    with pytest.raises(GameLifecycleError, match="spatial evidence"):
        GameLifecycle.from_payload(payload)


def test_forged_territory_unit_witness_fails_checkpoint_spatial_rebuild() -> None:
    setup = phase17n_event_setup(
        layout_id="reconnaissance-vs-priority-assets-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="priority-assets",
    )
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-a",
        phase=BattlePhase.FIGHT,
        battle_round=5,
    )
    state.turn_order = ("player-b", "player-a")
    _place_player_on_role(state, player_id="player-b", role=ObjectiveMarkerRole.ATTACKER_HOME)
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=None,
    )
    checkpoint = bound_primary_scoring_commit_checkpoint(
        scoring_player_id=record.active_player_id,
        state=state,
        record=record,
        scoring_commit_checkpoint=None,
        runtime_modifier_registry=None,
    )
    evidence = build_primary_scoring_state_evidence(
        scoring_player_id=record.active_player_id,
        state=state,
        record=record,
        end_of_battle=True,
        scoring_commit_checkpoint=checkpoint,
    )
    payload = evidence.to_payload()
    spatial_row = next(
        row
        for row in payload["primary_scoring_spatial_evidence_by_player_id"]
        if PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION in row["requested_condition_ids"]
    )
    enemy = next(
        candidate
        for army in state.army_definitions
        if army.player_id == "player-b"
        for candidate in army.units
    )
    authentic = list(spatial_row["enemy_units_wholly_within_own_territory"])
    if authentic:
        spatial_row["enemy_units_wholly_within_own_territory"] = [
            {
                "rules_unit_instance_id": authentic[0]["rules_unit_instance_id"],
                "model_instance_ids": [enemy.own_models[0].model_instance_id],
            }
        ]
    else:
        spatial_row["enemy_units_wholly_within_own_territory"] = [
            PrimaryTerritoryUnitWitness(
                rules_unit_instance_id=enemy.unit_instance_id,
                model_instance_ids=(enemy.own_models[0].model_instance_id,),
            ).to_payload()
        ]
    content = {
        key: value for key, value in payload.items() if key not in {"evidence_id", "evidence_hash"}
    }
    digest = canonical_payload_sha256(content)
    payload["evidence_id"] = f"primary-scoring-state-evidence:{digest}"
    payload["evidence_hash"] = digest
    forged_evidence = PrimaryScoringStateEvidence.from_payload(payload)
    placements = primary_mission_model_placements_from_checkpoint(
        state=state,
        checkpoint=checkpoint,
    )
    with pytest.raises(GameLifecycleError, match="spatial evidence drifted"):
        validate_primary_scoring_spatial_rows_from_checkpoint(
            state=state,
            evidence=forged_evidence,
            model_placements=placements,
        )


def test_forged_commit_checkpoint_pose_without_physical_event_fails_restore() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="move")
    state = lifecycle.state
    assert state is not None
    payload = deepcopy(lifecycle.to_payload())
    events = payload["decisions"]["event_log"]
    commit_event = next(
        event for event in events if event["event_type"] == PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT
    )
    raw_payload = commit_event["payload"]
    assert isinstance(raw_payload, dict)
    checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(raw_payload["checkpoint"])
    rewritten_states = tuple(_offset_checkpoint_model_state(row) for row in checkpoint.model_states)
    rewritten = _checkpoint_with_model_states(checkpoint, rewritten_states)
    raw_payload["checkpoint"] = rewritten.to_payload()
    evidence = payload["state"]["primary_scoring_state_evidence_records"][0]
    forged_placements = primary_mission_model_placements_from_checkpoint(
        state=state,
        checkpoint=rewritten,
    )
    rebuilt_witnesses: list[PrimaryScoringRulesUnitPositionWitnessPayload] = []
    for witness in evidence["current_rules_unit_position_witnesses"]:
        membership_payload = witness["rules_unit_membership"]
        component_unit_instance_ids = tuple(
            component["unit_instance_id"]
            for component in membership_payload["component_memberships"]
        )
        membership = build_primary_rules_unit_membership_from_model_placements(
            state=state,
            rules_unit_instance_id=membership_payload["rules_unit_instance_id"],
            owner_player_id=witness["owner_player_id"],
            component_unit_instance_ids=component_unit_instance_ids,
            model_placements=forged_placements,
        )
        rebuilt_witnesses.append(
            {
                "owner_player_id": witness["owner_player_id"],
                "rules_unit_membership": membership.to_payload(),
            }
        )
    evidence["current_rules_unit_position_witnesses"] = rebuilt_witnesses
    record = state.objective_control_records[-1]
    evidence["primary_scoring_spatial_evidence_by_player_id"] = [
        build_primary_scoring_spatial_evidence(
            state=state,
            player_id=row["player_id"],
            record=record,
            requested_condition_ids=tuple(row["requested_condition_ids"]),
            model_placements=forged_placements,
        ).to_payload()
        if row["requested_condition_ids"]
        else row
        for row in evidence["primary_scoring_spatial_evidence_by_player_id"]
    ]
    evidence["scoring_commit_checkpoint_id"] = rewritten.checkpoint_id
    evidence["scoring_commit_checkpoint_hash"] = rewritten.checkpoint_hash
    _rehash_evidence_transactions_and_lifecycles(
        payload,
        evidence=evidence,
        scoring_commit_checkpoint=rewritten,
    )
    with pytest.raises(GameLifecycleError, match="movement history"):
        GameLifecycle.from_payload(payload)


def test_sticky_control_satisfies_secondary_at_opponent_turn_end() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    home = next(
        marker
        for marker in state.mission_setup.objective_markers  # type: ignore[union-attr]
        if marker.objective_role is ObjectiveMarkerRole.ATTACKER_HOME
    )
    sticky = _sticky_state_for(
        state,
        player_id="player-a",
        objective_id=home.objective_marker_id,
        active_player_id="player-b",
    )
    state.record_sticky_objective_control_state(sticky)
    _place_player_away_from_objectives(state, player_id="player-a")
    scored = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert scored.status.value == "scored"
    record = state.objective_control_records[-1]
    home_result = record.result_by_objective_id(home.objective_marker_id)
    assert home_result.retained_control_source_id is not None


def test_preexisting_canonical_sticky_record_is_reused_exactly() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    home = next(
        marker
        for marker in state.mission_setup.objective_markers  # type: ignore[union-attr]
        if marker.objective_role is ObjectiveMarkerRole.ATTACKER_HOME
    )
    sticky = _sticky_state_for(
        state,
        player_id="player-a",
        objective_id=home.objective_marker_id,
        active_player_id="player-b",
    )
    state.record_sticky_objective_control_state(sticky)
    stored = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=None,
    )
    _place_player_away_from_objectives(state, player_id="player-a")
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert state.objective_control_records == [stored]


def test_secondary_retry_without_applicable_primary_evidence() -> None:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.FIGHT, battle_round=3)
    state = lifecycle.state
    assert state is not None
    state.active_player_id = "player-b"
    _place_player_on_role(state, player_id="player-a", role=ObjectiveMarkerRole.ATTACKER_HOME)
    _place_player_on_role(state, player_id="player-b", role=ObjectiveMarkerRole.DEFENDER_HOME)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            battle_round=3,
            source_result_id="p2-no-primary-retry",
        )
    )
    first = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert state.primary_scoring_state_evidence_records == []
    second = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert second == first
    secondary_ids = tuple(
        transaction.transaction_id
        for ledger in state.victory_point_ledgers
        for transaction in ledger.transactions
        if transaction.source_kind is VictoryPointSourceKind.TACTICAL_SECONDARY
    )
    assert len(secondary_ids) == 1


def test_fixed_bring_it_down_scores_distinct_turn_end_records() -> None:
    lifecycle = _battlefield_dominance_lifecycle(phase=BattlePhase.FIGHT, battle_round=3)
    state = lifecycle.state
    assert state is not None
    player_a_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
    )
    player_b_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    _set_unit_starting_wounds(state, player_a_unit.unit_instance_id, wounds=10)
    _set_unit_starting_wounds(state, player_b_unit.unit_instance_id, wounds=10)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_fixed(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
        )
    )
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_fixed(
            player_id="player-b",
            secondary_mission_id="bring-it-down",
        )
    )
    state.active_player_id = "player-a"
    record_secondary_destruction_for_fixture(
        state,
        destroying_player_id="player-a",
        destroyed_unit_instance_id=player_b_unit.unit_instance_id,
        source_id="p2-bring-it-down-a",
        event_log=lifecycle.decision_controller.event_log,
    )
    first = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    first_record_id = state.objective_control_records[-1].record_id
    state.active_player_id = "player-b"
    record_secondary_destruction_for_fixture(
        state,
        destroying_player_id="player-b",
        destroyed_unit_instance_id=player_a_unit.unit_instance_id,
        source_id="p2-bring-it-down-b",
        event_log=lifecycle.decision_controller.event_log,
    )
    second = state.score_secondary_mission_from_state(
        player_id="player-b",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    second_record_id = state.objective_control_records[-1].record_id
    assert first.status.value == "active"
    assert second.status.value == "active"
    assert first_record_id != second_record_id
    record_ids = _fixed_secondary_record_ids(state)
    assert record_ids == (first_record_id, second_record_id)
    state.active_player_id = "player-a"
    retry_a = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    state.active_player_id = "player-b"
    retry_b = state.score_secondary_mission_from_state(
        player_id="player-b",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert retry_a == first
    assert retry_b == second
    assert record_ids == _fixed_secondary_record_ids(state)
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()


def test_fixed_bring_it_down_same_card_scores_two_turn_end_records() -> None:
    lifecycle = _two_defender_battlefield_dominance_lifecycle(
        phase=BattlePhase.FIGHT,
        battle_round=3,
    )
    state = lifecycle.state
    assert state is not None
    defender_units = tuple(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    assert len(defender_units) == 2
    for unit in defender_units:
        _set_unit_starting_wounds(state, unit.unit_instance_id, wounds=10)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_fixed(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
        )
    )
    state.active_player_id = "player-a"
    record_secondary_destruction_for_fixture(
        state,
        destroying_player_id="player-a",
        destroyed_unit_instance_id=defender_units[0].unit_instance_id,
        source_id="p2-bring-it-down-same-card-a",
        event_log=lifecycle.decision_controller.event_log,
    )
    first = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    first_record_id = state.objective_control_records[-1].record_id
    state.active_player_id = "player-b"
    record_secondary_destruction_for_fixture(
        state,
        destroying_player_id="player-a",
        destroyed_unit_instance_id=defender_units[1].unit_instance_id,
        source_id="p2-bring-it-down-same-card-b",
        event_log=lifecycle.decision_controller.event_log,
    )
    second = state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    second_record_id = state.objective_control_records[-1].record_id
    assert first.status.value == "active"
    assert second.status.value == "active"
    assert first_record_id != second_record_id
    assert _fixed_secondary_record_ids(state) == (first_record_id, second_record_id)
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()


def test_restore_rejects_cross_player_secondary_evidence_swap_at_same_boundary() -> None:
    lifecycle = _same_boundary_two_player_bring_it_down_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    player_a = _secondary_transaction_payload(
        payload,
        player_id="player-a",
        source_id="bring-it-down",
        source_kind="fixed_secondary",
    )
    player_b = _secondary_transaction_payload(
        payload,
        player_id="player-b",
        source_id="bring-it-down",
        source_kind="fixed_secondary",
    )
    assert _transaction_record_id(player_a) == _transaction_record_id(player_b)
    _swap_secondary_scoring_evidence_bindings(player_a, player_b)

    with pytest.raises(GameLifecycleError, match="evidence player identity drifted"):
        GameLifecycle.from_payload(payload)


__all__: list[str] = []
__all__ += ["ArmyCatalog", "BattlePhaseKind", "DecisionController", "DecisionOption"]
__all__ += ["DecisionRequest", "DestructionSourceKind", "DiceExpression", "DiceRollManager"]
__all__ += ["DiceRollResult", "DiceRollSpec", "EventLog", "EventRecord"]
__all__ += ["GENERIC_RULE_IR_EFFECT_INDEX_KEY", "GENERIC_RULE_IR_EXECUTION_CONTEXT_KEY"]
__all__ += ["GENERIC_RULE_IR_EXECUTION_EVENT_ID_KEY", "GENERIC_RULE_IR_HASH_KEY"]
__all__ += ["GENERIC_RULE_IR_SOURCE_ID_KEY", "GameConfig", "GameLifecyclePayload"]
__all__ += ["GameLifecycleStage", "JsonValue", "ModelDestructionAttribution", "ModelPlacement"]
__all__ += ["ModifierOperation", "ModifierTerm", "ObjectiveControlModifierBinding"]
__all__ += ["ObjectiveControlModifierContext", "ObjectiveControlRecord"]
__all__ += ["ObjectiveControlRecordAuthority", "ObjectiveRuleScope"]
__all__ += ["PARAMETERIZED_DECISION_OPTION_ID", "PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT"]
__all__ += ["PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED"]
__all__ += ["PRIMARY_SCORING_PENDING_WINDOW_RETURN_ON_DEATH", "PendingReturnOnDeath", "Pose"]
__all__ += ["PrimaryBattlefieldDepartureState", "PrimaryMissionBoundaryModelState"]
__all__ += ["PrimaryMissionObjectiveControlModifierSource"]
__all__ += ["PrimaryScoringBoundaryLifecyclePayload", "PrimaryScoringStateEvidencePayload"]
__all__ += ["RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE"]
__all__ += ["RULE_EXECUTION_VICTORY_POINTS_AWARDED_EVENT_TYPE", "RegisteredPhase11FCapProbe"]
__all__ += ["ReturnDestroyedTargetScope", "ReturnRestoreWoundsMode", "RuleClause"]
__all__ += ["RuleEffectKind", "RuleEffectSpec", "RuleExecutionContext", "RuleExecutionStatus"]
__all__ += ["RuleIR", "RuleParameter", "RuleSourceText", "RulesetDescriptor"]
__all__ += ["RuntimeModifierRegistry", "RuntimeRuleIRAuthorityIndex", "RuntimeRuleIRSourceKey"]
__all__ += ["SCORING_COMMIT_CHECKPOINT_HASH_KEY", "SCORING_COMMIT_CHECKPOINT_ID_KEY"]
__all__ += ["SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY"]
__all__ += ["SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY"]
__all__ += ["SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE"]
__all__ += ["SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE", "SOURCE_KEYWORD_SEQUENCE_PARTS"]
__all__ += ["SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE", "SecondaryMissionCardStatus"]
__all__ += ["SecondaryScoringProviderKind", "StickyObjectiveControlState", "UnitInstance"]
__all__ += ["_OC_SOURCE_RULE_ID", "UnitPlacement", "VictoryPointCapBucket", "_add_unit_keyword"]
__all__ += ["_append_player_transaction_from_award", "_authenticated_move_unit_to"]
__all__ += ["_award_from_transaction", "_bring_it_down_player_a_scored_lifecycle"]
__all__ += ["_card_for_state_backed_scoring", "_compiled_generic_vp_rule_ir"]
__all__ += ["_destroy_all_models", "_destroy_first_model", "_destroy_model_with_event"]
__all__ += ["_emit_objective_control_boundary_event_if_missing", "_empty_rule_ir_authority_index"]
__all__ += ["_execute_generic_vp_on_lifecycle", "_expected_state_backed_secondary_award"]
__all__ += ["_fabricated_generic_rule_ir_metadata", "_first_unit", "_generic_rule_ir_transaction"]
__all__ += ["_generic_vp_clause_and_effect", "_generic_vp_execution_context", "_json_list"]
__all__ += ["_json_map", "_json_object", "_ledger_payload"]
__all__ += ["_legacy_score_secondary_mission_award"]
__all__ += ["_place_in_player_deployment_zone_away_from_home"]
__all__ += ["_place_unit_interior_non_overlapping", "_queue_pending_window"]
__all__ += ["_record_for_binding", "_registered_phase11f_cap_probe_award"]
__all__ += ["_rehash_lifecycle_row", "_reject_duplicate_tactical_source"]
__all__ += ["_replace_player_transaction"]
__all__ += ["_replace_secondary_scoring_evidence_binding_from_payload"]
__all__ += ["_require_registered_phase11f_cap_probe", "_rule_ir_authority_index"]
__all__ += ["_same_boundary_bring_it_down_and_assassination_lifecycle", "_secondary_transaction"]
__all__ += ["_secondary_transaction_payloads", "_single_mode_bring_it_down_lifecycle"]
__all__ += ["_tactical_secondary_amount", "_transaction_objective_control_record_id"]
__all__ += ["_two_player_bring_it_down_scored_lifecycle", "_two_round_bring_it_down_lifecycle"]
__all__ += ["_uncapped_award_from_transaction", "_validate_registered_phase11f_cap_probe"]
__all__ += ["_validate_scored_tactical_card_bindings", "_validate_secondary_primary_closure"]
__all__ += ["_zone_anchor_away_from_home", "append_authenticated_normal_move"]
__all__ += ["apply_generic_rule_ir_victory_points", "apply_return_on_death_placement_decision"]
__all__ += ["army_muster_request", "bind_state_backed_secondary_scoring_commit", "cast"]
__all__ += ["compile_rule_source_text", "complete_setup_through_gate"]
__all__ += ["create_deterministic_battlefield_scenario", "default_rule_execution_registry"]
__all__ += ["default_unit_selection"]
__all__ += ["enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary"]
__all__ += ["enemy_unit_ids_in_player_deployment_zone_from_battlefield"]
__all__ += ["enemy_unit_ids_in_player_deployment_zone_from_model_placements", "execute_rule_ir"]
__all__ += ["generic_rule_ir_secondary_award", "is_registered_phase11f_cap_probe", "json_loads"]
__all__ += ["mark_pending_primary_scoring_boundaries", "mustered_armies"]
__all__ += ["next_generic_rule_ir_victory_point_event_id", "phase11c_mission_setup"]
__all__ += ["record_new_primary_unit_destruction_events"]
__all__ += ["record_primary_battlefield_departure_event"]
__all__ += ["record_primary_destroyed_model_departures"]
__all__ += ["record_primary_turn_start_evidence_for_fixture", "registered_phase11f_cap_probe"]
__all__ += ["request_mission_action_start", "require_generic_rule_ir_loaded_authority"]
__all__ += ["require_source_backed_secondary_cap_bucket"]
__all__ += ["require_state_backed_secondary_scoring_commit"]
__all__ += ["rules_unit_objective_proximity_witness", "ruleset"]
__all__ += ["score_secondary_mission_from_state", "secondary_choice"]
__all__ += ["secondary_scoring_provider_kind_from_metadata"]
__all__ += ["secondary_scoring_provider_kind_from_token"]
__all__ += ["state_backed_secondary_binding_identity"]
__all__ += ["state_backed_secondary_objective_control_record_id"]
__all__ += ["validate_generic_rule_ir_secondary_award", "validate_json_value"]
__all__ += ["validate_legacy_phase11f_secondary_award", "validate_secondary_award_semantics"]
__all__ += ["validate_secondary_generic_rule_ir_restore_authority"]
__all__ += ["validate_secondary_transaction_semantics"]
__all__ += ["validate_state_backed_secondary_award_binding"]
__all__ += ["validate_state_backed_secondary_ledger_binding", "with_unit_keywords"]
