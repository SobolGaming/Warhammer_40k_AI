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


def test_state_backed_secondary_scoring_helpers_fail_closed() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    event_log = lifecycle.decision_controller.event_log
    record = state.objective_control_records[-1]
    transaction = _secondary_transaction(
        state,
        source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
    )
    with pytest.raises(
        GameLifecycleError,
        match="State-backed secondary scoring requires GameState",
    ):
        score_secondary_mission_from_state(
            state=cast(GameState, object()),
            event_log=event_log,
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            mode=SecondaryMissionCardMode.FIXED,
            phase=BattlePhase.FIGHT,
        )
    with pytest.raises(
        GameLifecycleError,
        match="State-backed secondary scoring requires EventLog",
    ):
        score_secondary_mission_from_state(
            state=state,
            event_log=cast(EventLog, object()),
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            mode=SecondaryMissionCardMode.FIXED,
            phase=BattlePhase.FIGHT,
        )
    missing_setup = _bring_it_down_player_a_scored_lifecycle().state
    assert missing_setup is not None
    missing_setup.mission_setup = None
    with pytest.raises(
        GameLifecycleError,
        match="State-backed secondary scoring requires MissionSetup",
    ):
        score_secondary_mission_from_state(
            state=missing_setup,
            event_log=event_log,
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            mode=SecondaryMissionCardMode.FIXED,
            phase=BattlePhase.FIGHT,
        )
    with pytest.raises(
        GameLifecycleError,
        match="State-backed secondary scoring phase must be a BattlePhase",
    ):
        score_secondary_mission_from_state(
            state=state,
            event_log=event_log,
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            mode=SecondaryMissionCardMode.FIXED,
            phase=cast(BattlePhase, object()),
        )
    scored_card = SecondaryMissionCardState(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        battle_round=state.battle_round,
        status=SecondaryMissionCardStatus.SCORED,
        scored_transaction_id=f"{transaction.transaction_id}-scored-a",
    )
    state.secondary_mission_card_states = [scored_card]
    found = _card_for_state_backed_scoring(
        state=state,
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
    )
    assert found == scored_card
    state.secondary_mission_card_states = [
        scored_card,
        replace(
            scored_card,
            scored_transaction_id=f"{transaction.transaction_id}-scored-b",
        ),
    ]
    with pytest.raises(GameLifecycleError, match="Multiple scored secondary card states found"):
        _card_for_state_backed_scoring(
            state=state,
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            mode=SecondaryMissionCardMode.FIXED,
        )
    state.secondary_mission_card_states = []
    with pytest.raises(GameLifecycleError, match="Secondary mission card is not active"):
        _card_for_state_backed_scoring(
            state=state,
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            mode=SecondaryMissionCardMode.FIXED,
        )
    with pytest.raises(
        GameLifecycleError,
        match="Secondary scoring retry requires a VictoryPointTransaction",
    ):
        _transaction_objective_control_record_id(object())
    with pytest.raises(
        GameLifecycleError,
        match="Secondary scoring transaction metadata must include objective_control_record_id",
    ):
        _transaction_objective_control_record_id(replace(transaction, metadata=["not-an-object"]))
    with pytest.raises(
        GameLifecycleError,
        match="Secondary scoring transaction metadata must include objective_control_record_id",
    ):
        _transaction_objective_control_record_id(
            replace(
                transaction,
                metadata={
                    **_json_map(transaction.metadata, label="secondary metadata"),
                    "objective_control_record_id": 12,
                },
            )
        )
    with pytest.raises(
        GameLifecycleError,
        match="Secondary scoring Primary closure requires scoring policies",
    ):
        _validate_secondary_primary_closure(state=state, record=record, policies=object())
    _emit_objective_control_boundary_event_if_missing(event_log=event_log, record=record)
    command = _scored_command_boundary_after_mutation(kind="move")
    command_state = command.state
    assert command_state is not None
    assert command_state.mission_setup is not None
    command_record = command_state.objective_control_records[-1]
    command_policies = mission_scoring_policies_from_setup(command_state.mission_setup)
    _validate_secondary_primary_closure(
        state=command_state,
        record=command_record,
        policies=command_policies,
    )
    command_state.primary_scoring_state_evidence_records = []
    with pytest.raises(
        GameLifecycleError,
        match="State-backed secondary scoring found a Secondary award without Primary evidence",
    ):
        _validate_secondary_primary_closure(
            state=command_state,
            record=command_record,
            policies=command_policies,
        )
    restored_command = _scored_command_boundary_after_mutation(kind="move")
    restored_state = restored_command.state
    assert restored_state is not None
    assert restored_state.mission_setup is not None
    restored_record = restored_state.objective_control_records[-1]
    restored_policies = mission_scoring_policies_from_setup(restored_state.mission_setup)
    restored_state.primary_scoring_boundary_lifecycles = []
    with pytest.raises(
        GameLifecycleError,
        match="without a resolved Primary lifecycle",
    ):
        _validate_secondary_primary_closure(
            state=restored_state,
            record=restored_record,
            policies=restored_policies,
        )


def test_restore_rejects_registered_phase11f_probe_with_arbitrary_amount() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    probe = _registered_phase11f_cap_probe_award()
    _append_player_transaction_from_award(state, replace(probe, amount=5))
    with pytest.raises(
        GameLifecycleError,
        match="Registered Phase 11F Secondary VP amount drifted",
    ):
        validate_secondary_transaction_semantics(state=state)


def test_restore_rejects_duplicate_registered_phase11f_probe() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    probe = _registered_phase11f_cap_probe_award()
    state.award_victory_points(probe)
    with pytest.raises(
        GameLifecycleError,
        match="Registered Phase 11F Secondary VP probe must not repeat",
    ):
        state.award_victory_points(probe)
    _append_player_transaction_from_award(state, probe)
    with pytest.raises(
        GameLifecycleError,
        match="Registered Phase 11F Secondary VP probe must not repeat",
    ):
        validate_secondary_transaction_semantics(state=state)


def test_restore_rejects_downgraded_secondary_amount_rewrite_below_caps() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    ledger = _ledger_payload(payload, player_id="player-a")
    secondary = _secondary_transaction_payloads(ledger, source_kind="fixed_secondary")
    assert len(secondary) == 1
    transaction = secondary[0]
    original_amount = transaction["amount"]
    assert isinstance(original_amount, int)
    transaction["amount"] = original_amount + 1
    transaction["scoring_timing"] = "secondary_mission_score"
    victory_points = ledger["victory_points"]
    assert isinstance(victory_points, int)
    ledger["victory_points"] = victory_points + 1
    metadata = _json_object(transaction["metadata"], label="secondary metadata")
    for key in (
        "objective_control_record_id",
        "scoring_rule_ids",
        "scoring_rule_conditions",
        "scoring_rule_source_ids",
        "score_count_by_rule",
        "victory_points_by_rule",
        "evidence_by_rule",
        "scoring_commit_checkpoint_id",
        "scoring_commit_checkpoint_hash",
    ):
        metadata.pop(key, None)
    metadata["secondary_scoring_provider_kind"] = SecondaryScoringProviderKind.LEGACY_PHASE11F.value
    metadata["scoring_rule_id"] = "bring-it-down-fixed"
    with pytest.raises(
        GameLifecycleError,
        match=(
            r"Legacy Phase 11F Secondary VP drifted from score_secondary_mission authority|"
            r"Non-state-backed Secondary VP metadata must not carry state-backed authority"
        ),
    ):
        GameLifecycle.from_payload(payload)


def test_restore_rejects_duplicate_same_source_after_provider_downgrade() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    ledger = _ledger_payload(payload, player_id="player-a")
    secondary = _secondary_transaction_payloads(ledger, source_kind="fixed_secondary")
    assert len(secondary) == 1
    duplicate = deepcopy(secondary[0])
    transactions = _json_list(ledger["transactions"], label="victory point transactions")
    battle_round = duplicate["battle_round"]
    assert isinstance(battle_round, int)
    duplicate["transaction_id"] = (
        f"victory-point:player-a:round-{battle_round:02d}:{len(transactions) + 1:06d}"
    )
    transactions.append(duplicate)
    amount = duplicate["amount"]
    assert isinstance(amount, int)
    victory_points = ledger["victory_points"]
    assert isinstance(victory_points, int)
    ledger["victory_points"] = victory_points + amount
    for row in (secondary[0], duplicate):
        metadata = _json_object(row["metadata"], label="secondary metadata")
        metadata.pop("objective_control_record_id")
    with pytest.raises(
        GameLifecycleError,
        match="State-backed Secondary VP metadata requires objective_control_record_id",
    ):
        GameLifecycle.from_payload(payload)


def test_defend_stronghold_restore_survives_later_enemy_entering_deployment_zone() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    record = state.objective_control_records[-1]
    scored_zone = enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary(
        state=state,
        record=record,
        player_id="player-a",
    )
    assert scored_zone == ()
    metadata = _json_object(
        _secondary_transaction(
            state,
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
        ).metadata,
        label="secondary metadata",
    )
    authority = next(
        stored
        for stored in state.objective_control_record_authorities
        if stored.objective_control_record_id == record.record_id
    )
    assert metadata[SCORING_COMMIT_CHECKPOINT_ID_KEY] == authority.boundary_checkpoint.checkpoint_id
    enemy = _first_unit(state, player_id="player-b")
    target = _zone_anchor_away_from_home(state, zone_player_id="player-a")
    _authenticated_move_unit_to(
        lifecycle=lifecycle,
        unit_instance_id=enemy.unit_instance_id,
        x=target[0],
        y=target[1],
        suffix="enter-player-a-zone",
    )
    assert (
        enemy_unit_ids_in_player_deployment_zone_from_battlefield(
            state=state,
            player_id="player-a",
        )
        != scored_zone
    )
    assert (
        enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary(
            state=state,
            record=record,
            player_id="player-a",
        )
        == scored_zone
    )
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.to_payload() == lifecycle.to_payload()


def test_defend_stronghold_restore_survives_later_enemy_leaving_deployment_zone() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    _place_in_player_deployment_zone_away_from_home(
        state,
        moving_player_id="player-b",
        zone_player_id="player-a",
    )
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    record = state.objective_control_records[-1]
    scored_zone = enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary(
        state=state,
        record=record,
        player_id="player-a",
    )
    assert scored_zone
    defender_home = next(
        marker
        for marker in state.mission_setup.objective_markers  # type: ignore[union-attr]
        if marker.objective_role is ObjectiveMarkerRole.DEFENDER_HOME
    )
    _authenticated_move_unit_to(
        lifecycle=lifecycle,
        unit_instance_id=_first_unit(state, player_id="player-b").unit_instance_id,
        x=defender_home.x_inches,
        y=defender_home.y_inches,
        suffix="leave-player-a-zone",
    )
    assert (
        enemy_unit_ids_in_player_deployment_zone_from_battlefield(
            state=state,
            player_id="player-a",
        )
        != scored_zone
    )
    assert (
        enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary(
            state=state,
            record=record,
            player_id="player-a",
        )
        == scored_zone
    )
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.to_payload() == lifecycle.to_payload()


def test_defend_stronghold_restore_survives_later_enemy_destruction() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    _place_in_player_deployment_zone_away_from_home(
        state,
        moving_player_id="player-b",
        zone_player_id="player-a",
    )
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    record = state.objective_control_records[-1]
    scored_zone = enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary(
        state=state,
        record=record,
        player_id="player-a",
    )
    assert scored_zone
    _destroy_all_models(
        state=state,
        decisions=lifecycle.decision_controller,
        unit_instance_id=_first_unit(state, player_id="player-b").unit_instance_id,
    )
    assert (
        enemy_unit_ids_in_player_deployment_zone_from_battlefield(
            state=state,
            player_id="player-a",
        )
        != scored_zone
    )
    assert (
        enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary(
            state=state,
            record=record,
            player_id="player-a",
        )
        == scored_zone
    )
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.to_payload() == lifecycle.to_payload()


def test_restore_rejects_rewritten_defend_stronghold_zone_witness() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    payload = deepcopy(lifecycle.to_payload())
    ledger = _ledger_payload(payload, player_id="player-a")
    secondary = _secondary_transaction_payloads(ledger, source_kind="tactical_secondary")
    assert len(secondary) == 1
    transaction = secondary[0]
    original_amount = transaction["amount"]
    assert isinstance(original_amount, int)
    transaction["amount"] = original_amount - 2
    victory_points = ledger["victory_points"]
    assert isinstance(victory_points, int)
    ledger["victory_points"] = victory_points - 2
    metadata = _json_object(transaction["metadata"], label="secondary metadata")
    victory_points_by_rule = _json_object(
        metadata["victory_points_by_rule"],
        label="victory_points_by_rule",
    )
    evidence_by_rule = _json_object(metadata["evidence_by_rule"], label="evidence_by_rule")
    rule_id = "defend-stronghold-no-enemy-in-deployment-zone"
    victory_points_by_rule[rule_id] = 0
    evidence = _json_object(evidence_by_rule[rule_id], label="zone evidence")
    evidence["score_count"] = 0
    evidence["enemy_unit_instance_ids"] = ["army-beta:forged-intruder"]
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP transactions drifted from authoritative scoring-state semantics",
    ):
        GameLifecycle.from_payload(payload)


def test_deleted_resolved_lifecycle_row_fails_restore() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="move")
    payload = deepcopy(lifecycle.to_payload())
    rows = payload["state"]["primary_scoring_boundary_lifecycles"]
    assert rows
    payload["state"]["primary_scoring_boundary_lifecycles"] = rows[1:]
    with pytest.raises(
        GameLifecycleError,
        match="lifecycle registry is incomplete or unexpected",
    ):
        GameLifecycle.from_payload(payload)


def test_deleted_all_resolved_lifecycle_rows_fails_restore() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="move")
    payload = deepcopy(lifecycle.to_payload())
    payload["state"]["primary_scoring_boundary_lifecycles"] = []
    with pytest.raises(
        GameLifecycleError,
        match="lifecycle registry is incomplete or unexpected",
    ):
        GameLifecycle.from_payload(payload)


def test_incorrect_legal_pending_window_fails_restore() -> None:
    lifecycle = _pending_command_boundary_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    for row in payload["state"]["primary_scoring_boundary_lifecycles"]:
        row["pending_window"] = PRIMARY_SCORING_PENDING_WINDOW_RETURN_ON_DEATH
        _rehash_lifecycle_row(row)
    with pytest.raises(
        GameLifecycleError,
        match="window does not match the queue-head decision family",
    ):
        GameLifecycle.from_payload(payload)


def test_pending_row_bound_to_unrelated_queue_head_fails_restore() -> None:
    lifecycle = _pending_command_boundary_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    queue = payload["decisions"]["queue"]["pending_requests"]
    queue[0]["decision_type"] = SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
    for event in payload["decisions"]["event_log"]:
        if event["event_type"] != "decision_requested":
            continue
        request_payload = event["payload"]
        if (
            isinstance(request_payload, dict)
            and request_payload.get("request_id") == queue[0]["request_id"]
        ):
            request_payload["decision_type"] = SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE
    with pytest.raises(
        GameLifecycleError,
        match="window does not match the queue-head decision family",
    ):
        GameLifecycle.from_payload(payload)


def test_coordinated_lifecycle_deletion_with_evidence_and_ledger_rewrite_fails() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="move")
    payload = deepcopy(lifecycle.to_payload())
    payload["state"]["primary_scoring_boundary_lifecycles"] = []
    payload["state"]["primary_scoring_state_evidence_records"] = []
    for ledger in payload["state"]["victory_point_ledgers"]:
        ledger["transactions"] = [
            transaction
            for transaction in ledger["transactions"]
            if transaction["source_kind"] != "primary"
        ]
        ledger["victory_points"] = sum(
            transaction["amount"] for transaction in ledger["transactions"]
        )
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(payload)


__all__: list[str] = []
__all__ += ["ArmyCatalog", "BattlePhaseKind", "DecisionController", "DecisionOption"]
__all__ += ["DecisionRequest", "DecisionResult", "DestructionSourceKind", "DiceExpression"]
__all__ += ["DiceRollManager", "DiceRollResult", "DiceRollSpec", "EventRecord"]
__all__ += ["GENERIC_RULE_IR_EFFECT_INDEX_KEY", "GENERIC_RULE_IR_EXECUTION_CONTEXT_KEY"]
__all__ += ["GENERIC_RULE_IR_EXECUTION_EVENT_ID_KEY", "GENERIC_RULE_IR_HASH_KEY"]
__all__ += ["GENERIC_RULE_IR_SOURCE_ID_KEY", "GameConfig", "GameLifecyclePayload"]
__all__ += ["GameLifecycleStage", "JsonValue", "ModelDestructionAttribution", "ModelPlacement"]
__all__ += ["ModifierOperation", "ModifierTerm", "ObjectiveControlModifierBinding"]
__all__ += ["ObjectiveControlModifierContext", "ObjectiveControlRecord"]
__all__ += ["ObjectiveControlRecordAuthority", "ObjectiveControlTiming", "ObjectiveRuleScope"]
__all__ += ["PARAMETERIZED_DECISION_OPTION_ID", "PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT"]
__all__ += ["PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT"]
__all__ += ["PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION"]
__all__ += ["PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED", "PendingReturnOnDeath"]
__all__ += ["Pose", "PrimaryBattlefieldDepartureState", "PrimaryMissionBoundaryCheckpoint"]
__all__ += ["PrimaryMissionBoundaryModelState", "PrimaryMissionObjectiveControlModifierSource"]
__all__ += ["PrimaryScoringBoundaryKind", "PrimaryScoringBoundaryLifecyclePayload"]
__all__ += ["PrimaryScoringBoundaryStatus", "PrimaryScoringRulesUnitPositionWitnessPayload"]
__all__ += ["PrimaryScoringStateEvidence", "PrimaryScoringStateEvidencePayload"]
__all__ += ["RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE", "PrimaryTerritoryUnitWitness"]
__all__ += ["RULE_EXECUTION_VICTORY_POINTS_AWARDED_EVENT_TYPE", "RegisteredPhase11FCapProbe"]
__all__ += ["ReturnDestroyedTargetScope", "ReturnRestoreWoundsMode", "RuleClause"]
__all__ += ["RuleEffectKind", "RuleEffectSpec", "RuleExecutionContext", "RuleExecutionStatus"]
__all__ += ["RuleIR", "RuleParameter", "RuleSourceText", "RulesetDescriptor"]
__all__ += ["RuntimeModifierRegistry", "RuntimeRuleIRAuthorityIndex", "RuntimeRuleIRSourceKey"]
__all__ += ["SCORING_COMMIT_CHECKPOINT_HASH_KEY", "SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY"]
__all__ += ["SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY"]
__all__ += ["SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE"]
__all__ += ["SOURCE_KEYWORD_SEQUENCE_PARTS", "SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE"]
__all__ += ["SecondaryMissionMode", "SecondaryScoringConditionContext"]
__all__ += ["TABLE_QUARTER_NORTH_WEST", "StickyObjectiveControlState", "UnitInstance"]
__all__ += ["UnitPlacement", "VictoryPointAward", "VictoryPointCapBucket"]
__all__ += ["_OC_SOURCE_RULE_ID", "VictoryPointTransaction", "_add_unit_keyword"]
__all__ += ["_assert_scoring_commit_differs_from_oc_checkpoint", "_award_from_transaction"]
__all__ += ["_battlefield_dominance_lifecycle", "_checkpoint_with_model_states"]
__all__ += ["_compiled_generic_vp_rule_ir", "_destroy_first_model", "_destroy_model_with_event"]
__all__ += ["_destroy_unit_with_events", "_emit_oc_event", "_empty_rule_ir_authority_index"]
__all__ += ["_execute_generic_vp_on_lifecycle", "_expected_state_backed_secondary_award"]
__all__ += ["_fabricated_generic_rule_ir_metadata", "_fixed_secondary_record_ids"]
__all__ += ["_generic_rule_ir_transaction", "_generic_vp_clause_and_effect"]
__all__ += ["_generic_vp_execution_context", "_legacy_score_secondary_mission_award"]
__all__ += ["_offset_checkpoint_model_state", "_pending_final_turn_end_boundary_lifecycle"]
__all__ += ["_place_player_away_from_objectives", "_place_player_on_role"]
__all__ += ["_place_unit_interior_non_overlapping", "_queue_pending_window"]
__all__ += ["_record_for_binding", "_rehash_evidence_transactions_and_lifecycles"]
__all__ += ["_reject_duplicate_tactical_source", "_replace_player_transaction"]
__all__ += ["_replace_secondary_scoring_evidence_binding_from_payload"]
__all__ += ["_require_registered_phase11f_cap_probe", "_return_destroyed_unit"]
__all__ += ["_rule_ir_authority_index"]
__all__ += ["_same_boundary_bring_it_down_and_assassination_lifecycle"]
__all__ += ["_same_boundary_two_player_bring_it_down_lifecycle"]
__all__ += ["_scored_determined_acquisition_command_lifecycle"]
__all__ += ["_scored_reconnaissance_turn_end_lifecycle", "_secondary_transaction_payload"]
__all__ += ["_set_unit_starting_wounds", "_single_mode_bring_it_down_lifecycle"]
__all__ += ["_sticky_state_for", "_swap_secondary_scoring_evidence_bindings"]
__all__ += ["_tactical_secondary_amount", "_transaction_record_id"]
__all__ += ["_two_defender_battlefield_dominance_lifecycle"]
__all__ += ["_two_model_battlefield_dominance_lifecycle"]
__all__ += ["_two_player_bring_it_down_scored_lifecycle", "_two_round_bring_it_down_lifecycle"]
__all__ += ["_uncapped_award_from_transaction", "_validate_registered_phase11f_cap_probe"]
__all__ += ["_validate_scored_tactical_card_bindings", "append_authenticated_normal_move"]
__all__ += ["apply_generic_rule_ir_victory_points", "apply_return_on_death_placement_decision"]
__all__ += ["army_muster_request", "bind_state_backed_secondary_scoring_commit"]
__all__ += ["bound_primary_scoring_commit_checkpoint"]
__all__ += ["build_primary_rules_unit_membership_from_model_placements"]
__all__ += ["build_primary_scoring_spatial_evidence", "build_primary_scoring_state_evidence"]
__all__ += ["canonical_json", "canonical_payload_sha256", "compile_rule_source_text"]
__all__ += ["complete_setup_through_gate", "create_deterministic_battlefield_scenario"]
__all__ += ["default_rule_execution_registry", "default_unit_selection"]
__all__ += ["enemy_unit_ids_in_player_deployment_zone_from_model_placements", "escape"]
__all__ += ["execute_rule_ir", "generic_rule_ir_secondary_award"]
__all__ += ["is_registered_phase11f_cap_probe", "json_loads"]
__all__ += ["mark_pending_primary_scoring_boundaries", "mustered_armies"]
__all__ += ["next_generic_rule_ir_victory_point_event_id"]
__all__ += ["pending_primary_scoring_boundary_keys", "phase11c_mission_setup"]
__all__ += ["phase17n_event_setup", "phase17n_state_with_setup"]
__all__ += ["primary_mission_model_placements_from_checkpoint"]
__all__ += ["record_new_primary_unit_destruction_events"]
__all__ += ["record_primary_battlefield_departure_event"]
__all__ += ["record_primary_destroyed_model_departures", "record_primary_scoring_state_evidence"]
__all__ += ["record_primary_turn_start_evidence_for_fixture"]
__all__ += ["record_secondary_destruction_for_fixture", "registered_phase11f_cap_probe"]
__all__ += ["request_mission_action_start", "require_generic_rule_ir_loaded_authority"]
__all__ += ["require_source_backed_secondary_cap_bucket"]
__all__ += ["require_state_backed_secondary_scoring_commit"]
__all__ += ["resolve_primary_scoring_boundary_lifecycle"]
__all__ += ["rules_unit_objective_proximity_witness", "ruleset"]
__all__ += ["score_primary_objective_control_boundary", "secondary_choice"]
__all__ += ["secondary_scoring_provider_kind_from_metadata"]
__all__ += ["secondary_scoring_provider_kind_from_token"]
__all__ += ["state_backed_secondary_binding_identity"]
__all__ += ["state_backed_secondary_objective_control_record_id"]
__all__ += ["validate_generic_rule_ir_secondary_award", "validate_json_value"]
__all__ += ["validate_legacy_phase11f_secondary_award"]
__all__ += ["validate_primary_scoring_spatial_rows_from_checkpoint"]
__all__ += ["validate_secondary_award_semantics"]
__all__ += ["validate_secondary_generic_rule_ir_restore_authority"]
__all__ += ["validate_state_backed_secondary_award_binding"]
__all__ += ["validate_state_backed_secondary_ledger_binding", "with_model_offsets"]
__all__ += ["with_unit_keywords"]
