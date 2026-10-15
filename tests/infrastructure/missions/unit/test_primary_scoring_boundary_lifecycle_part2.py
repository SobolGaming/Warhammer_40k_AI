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


def test_restore_rejects_cross_card_secondary_evidence_swap_for_one_player() -> None:
    lifecycle = _same_boundary_bring_it_down_and_assassination_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    bring_it_down = _secondary_transaction_payload(
        payload,
        player_id="player-a",
        source_id="bring-it-down",
        source_kind="fixed_secondary",
    )
    assassination = _secondary_transaction_payload(
        payload,
        player_id="player-a",
        source_id="assassination",
        source_kind="fixed_secondary",
    )
    assert _transaction_record_id(bring_it_down) == _transaction_record_id(assassination)
    _swap_secondary_scoring_evidence_bindings(bring_it_down, assassination)

    with pytest.raises(GameLifecycleError, match="evidence mission identity drifted"):
        GameLifecycle.from_payload(payload)


def test_restore_rejects_fixed_tactical_secondary_evidence_swap_for_dual_mode_card() -> None:
    fixed_payload = deepcopy(
        _single_mode_bring_it_down_lifecycle(SecondaryMissionCardMode.FIXED).to_payload()
    )
    tactical_payload = deepcopy(
        _single_mode_bring_it_down_lifecycle(SecondaryMissionCardMode.TACTICAL).to_payload()
    )
    fixed_donor_payload = deepcopy(fixed_payload)
    tactical_donor_payload = deepcopy(tactical_payload)
    fixed = _secondary_transaction_payload(
        fixed_payload,
        player_id="player-a",
        source_id="bring-it-down",
        source_kind="fixed_secondary",
    )
    tactical = _secondary_transaction_payload(
        tactical_payload,
        player_id="player-a",
        source_id="bring-it-down",
        source_kind="tactical_secondary",
    )
    _replace_secondary_scoring_evidence_binding_from_payload(
        target_payload=fixed_payload,
        target_transaction=fixed,
        donor_payload=tactical_donor_payload,
        donor_transaction=_secondary_transaction_payload(
            tactical_donor_payload,
            player_id="player-a",
            source_id="bring-it-down",
            source_kind="tactical_secondary",
        ),
    )
    _replace_secondary_scoring_evidence_binding_from_payload(
        target_payload=tactical_payload,
        target_transaction=tactical,
        donor_payload=fixed_donor_payload,
        donor_transaction=_secondary_transaction_payload(
            fixed_donor_payload,
            player_id="player-a",
            source_id="bring-it-down",
            source_kind="fixed_secondary",
        ),
    )

    for payload in (fixed_payload, tactical_payload):
        with pytest.raises(GameLifecycleError, match="evidence card mode drifted"):
            GameLifecycle.from_payload(payload)


def test_restore_rejects_cross_round_secondary_evidence_swap_for_same_fixed_card() -> None:
    lifecycle = _two_round_bring_it_down_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    transactions = _secondary_transaction_payloads(
        _ledger_payload(payload, player_id="player-a"),
        source_kind="fixed_secondary",
    )
    bring_it_down = [
        transaction for transaction in transactions if transaction["source_id"] == "bring-it-down"
    ]
    assert len(bring_it_down) == 2
    assert {transaction["battle_round"] for transaction in bring_it_down} == {2, 3}
    _swap_secondary_scoring_evidence_bindings(bring_it_down[0], bring_it_down[1])

    with pytest.raises(GameLifecycleError, match="evidence battle round drifted"):
        GameLifecycle.from_payload(payload)


def test_restore_rejects_duplicate_fixed_secondary_at_same_record() -> None:
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
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP ledger must not repeat a source at one boundary",
    ):
        GameLifecycle.from_payload(payload)


def test_restore_rejects_secondary_moved_to_different_oc_record() -> None:
    lifecycle = _two_player_bring_it_down_scored_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    player_a_ledger = _ledger_payload(payload, player_id="player-a")
    player_b_ledger = _ledger_payload(payload, player_id="player-b")
    player_a_secondary = _secondary_transaction_payloads(
        player_a_ledger,
        source_kind="fixed_secondary",
    )
    player_b_secondary = _secondary_transaction_payloads(
        player_b_ledger,
        source_kind="fixed_secondary",
    )
    assert len(player_a_secondary) == 1
    assert len(player_b_secondary) == 1
    player_a_metadata = _json_object(
        player_a_secondary[0]["metadata"],
        label="player-a secondary metadata",
    )
    player_b_metadata = _json_object(
        player_b_secondary[0]["metadata"],
        label="player-b secondary metadata",
    )
    original_record_id = player_a_metadata["objective_control_record_id"]
    moved_record_id = player_b_metadata["objective_control_record_id"]
    assert original_record_id != moved_record_id
    player_a_metadata["objective_control_record_id"] = moved_record_id
    with pytest.raises(
        GameLifecycleError,
        match="State-backed Secondary VP scoring-boundary checkpoint identity drifted",
    ):
        GameLifecycle.from_payload(payload)


def test_restore_rejects_rewritten_secondary_amount_and_evidence_below_caps() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    ledger = _ledger_payload(payload, player_id="player-a")
    secondary = _secondary_transaction_payloads(ledger, source_kind="fixed_secondary")
    assert len(secondary) == 1
    transaction = secondary[0]
    original_amount = transaction["amount"]
    assert isinstance(original_amount, int)
    new_amount = original_amount + 4
    transaction["amount"] = new_amount
    victory_points = ledger["victory_points"]
    assert isinstance(victory_points, int)
    ledger["victory_points"] = victory_points + 4
    metadata = _json_object(transaction["metadata"], label="secondary metadata")
    score_count_by_rule = _json_object(
        metadata["score_count_by_rule"],
        label="score_count_by_rule",
    )
    victory_points_by_rule = _json_object(
        metadata["victory_points_by_rule"],
        label="victory_points_by_rule",
    )
    evidence_by_rule = _json_object(metadata["evidence_by_rule"], label="evidence_by_rule")
    for rule_id in tuple(score_count_by_rule):
        score_count_by_rule[rule_id] = 2
        victory_points_by_rule[rule_id] = new_amount
        evidence = _json_object(evidence_by_rule[rule_id], label="rule evidence")
        evidence["score_count"] = 2
        destroyed_models = evidence.get("destroyed_model_instance_ids")
        if type(destroyed_models) is list and destroyed_models:
            typed_models = cast(list[object], destroyed_models)
            first_model = typed_models[0]
            assert isinstance(first_model, str)
            evidence["destroyed_model_instance_ids"] = [first_model, f"{first_model}-forged"]
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP transactions drifted from authoritative scoring-state semantics",
    ):
        GameLifecycle.from_payload(payload)


def test_restore_rejects_scored_tactical_card_without_identified_transaction() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    payload = deepcopy(lifecycle.to_payload())
    state_payload = _json_object(payload["state"], label="lifecycle state")
    cards = _json_list(
        state_payload["secondary_mission_card_states"],
        label="secondary mission card states",
    )
    scored_cards = [
        card
        for card in (_json_object(raw_card, label="secondary card") for raw_card in cards)
        if card.get("status") == "scored"
    ]
    assert len(scored_cards) == 1
    scored_cards[0]["scored_transaction_id"] = "victory-point:player-a:round-02:999999"
    with pytest.raises(
        GameLifecycleError,
        match="Scored tactical secondary card does not identify its ledger transaction",
    ):
        GameLifecycle.from_payload(payload)


def test_secondary_cap_bucket_requires_secondary_kind_and_source_backed_mission() -> None:
    setup = phase17n_event_setup(
        layout_id="take-and-hold-vs-take-and-hold-layout-1",
        attacker_force_disposition_id="take-and-hold",
        defender_force_disposition_id="take-and-hold",
    )
    policy = mission_scoring_policies_from_setup(setup).policy_for_player("player-a")
    assert (
        require_source_backed_secondary_cap_bucket(
            policy=policy,
            source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
            source_id="bring-it-down",
        )
        is VictoryPointCapBucket.SECONDARY
    )
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP cap bucket requires a Secondary source kind",
    ):
        require_source_backed_secondary_cap_bucket(
            policy=policy,
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id="bring-it-down",
        )
    with pytest.raises(GameLifecycleError, match="Secondary VP source is not source-backed"):
        require_source_backed_secondary_cap_bucket(
            policy=policy,
            source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
            source_id="not-a-source-backed-secondary",
        )


def test_secondary_binding_identity_and_metadata_guards() -> None:
    assert (
        state_backed_secondary_binding_identity(
            player_id="player-a",
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id="primary-take-and-hold",
            metadata={"objective_control_record_id": "oc-1"},
        )
        is None
    )
    assert (
        state_backed_secondary_objective_control_record_id(
            {"secondary_mission_id": "bring-it-down"}
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="Secondary VP metadata must be an object"):
        state_backed_secondary_objective_control_record_id(["not-an-object"])
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP metadata requires objective_control_record_id",
    ):
        state_backed_secondary_objective_control_record_id({"objective_control_record_id": ""})
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP metadata requires objective_control_record_id",
    ):
        state_backed_secondary_objective_control_record_id({"objective_control_record_id": 12})
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP metadata requires secondary_scoring_provider_kind",
    ):
        state_backed_secondary_binding_identity(
            player_id="player-a",
            source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
            source_id="bring-it-down",
            metadata={"objective_control_record_id": "oc-1"},
        )
    with pytest.raises(
        GameLifecycleError,
        match="State-backed Secondary VP metadata requires objective_control_record_id",
    ):
        state_backed_secondary_binding_identity(
            player_id="player-a",
            source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
            source_id="bring-it-down",
            metadata={
                "secondary_scoring_provider_kind": (
                    SecondaryScoringProviderKind.STATE_BACKED_OBJECTIVE_CONTROL.value
                )
            },
        )


def test_state_backed_secondary_bindings_require_one_matching_record() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    transaction = _secondary_transaction(
        state,
        source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
    )
    award = _award_from_transaction(transaction)
    records = tuple(state.objective_control_records)
    assert validate_state_backed_secondary_ledger_binding(
        transaction=transaction,
        objective_control_records=records,
    ) == (
        transaction.player_id,
        transaction.source_kind,
        transaction.source_id,
        _json_object(transaction.metadata, label="secondary metadata")[
            "objective_control_record_id"
        ],
    )
    assert (
        validate_state_backed_secondary_award_binding(
            award=award,
            objective_control_records=records,
        )[3]
        == _json_object(award.metadata, label="award metadata")["objective_control_record_id"]
    )
    unbound = replace(
        transaction,
        metadata={
            "secondary_scoring_provider_kind": SecondaryScoringProviderKind.LEGACY_PHASE11F.value,
            "secondary_mission_id": "bring-it-down",
            "scoring_rule_id": "bring-it-down-fixed",
        },
    )
    with pytest.raises(
        GameLifecycleError,
        match="State-backed Secondary VP transaction requires a boundary",
    ):
        validate_state_backed_secondary_ledger_binding(
            transaction=unbound,
            objective_control_records=records,
        )
    unbound_award = replace(
        award,
        metadata={
            "secondary_scoring_provider_kind": SecondaryScoringProviderKind.LEGACY_PHASE11F.value,
            "secondary_mission_id": "bring-it-down",
            "scoring_rule_id": "bring-it-down-fixed",
        },
    )
    with pytest.raises(
        GameLifecycleError,
        match="State-backed Secondary VP award requires a boundary",
    ):
        validate_state_backed_secondary_award_binding(
            award=unbound_award,
            objective_control_records=records,
        )
    drifted = replace(transaction, battle_round=transaction.battle_round + 1)
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP transaction timing drifted from its objective-control boundary",
    ):
        validate_state_backed_secondary_ledger_binding(
            transaction=drifted,
            objective_control_records=records,
        )
    drifted_award = replace(award, phase="command")
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP award timing drifted from its objective-control boundary",
    ):
        validate_state_backed_secondary_award_binding(
            award=drifted_award,
            objective_control_records=records,
        )
    missing = replace(
        transaction,
        metadata={
            **_json_map(transaction.metadata, label="secondary metadata"),
            "objective_control_record_id": "missing-objective-control-record",
        },
    )
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP transaction requires one objective-control boundary",
    ):
        validate_state_backed_secondary_ledger_binding(
            transaction=missing,
            objective_control_records=records,
        )


def test_secondary_semantic_validation_rejects_wrong_types_and_source_kinds() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    transaction = _secondary_transaction(
        state,
        source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
    )
    award = _award_from_transaction(transaction)
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP semantic validation requires GameState",
    ):
        validate_secondary_award_semantics(state=cast(GameState, object()), award=award)
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP semantic validation requires an award",
    ):
        validate_secondary_award_semantics(
            state=state,
            award=cast(VictoryPointAward, object()),
        )
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP semantic validation requires a Secondary award",
    ):
        validate_secondary_award_semantics(
            state=state,
            award=replace(award, source_kind=VictoryPointSourceKind.PRIMARY),
        )
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP transaction validation requires GameState",
    ):
        validate_secondary_transaction_semantics(state=cast(GameState, object()))
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP metadata requires secondary_scoring_provider_kind",
    ):
        validate_secondary_award_semantics(
            state=state,
            award=replace(award, metadata={"scoring_rule_id": "legacy-secondary"}),
        )


def test_live_secondary_award_rejects_duplicate_binding_and_amount_drift() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    transaction = _secondary_transaction(
        state,
        source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
    )
    award = _award_from_transaction(transaction)
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP ledger must not repeat a source at one boundary",
    ):
        validate_secondary_award_semantics(state=state, award=award)
    record = state.objective_control_records[-1]
    cloned = replace(record, record_id=f"{record.record_id}-clone")
    state.objective_control_records = [*state.objective_control_records, cloned]
    drifted = replace(
        award,
        amount=award.amount + 1,
        metadata={
            **_json_map(award.metadata, label="award metadata"),
            "objective_control_record_id": cloned.record_id,
        },
    )
    with pytest.raises(
        GameLifecycleError,
        match="State-backed Secondary VP requires one Objective Control authority",
    ):
        validate_secondary_award_semantics(state=state, award=drifted)
    state.secondary_mission_card_states = []
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP source does not identify an active or scored card",
    ):
        validate_secondary_award_semantics(state=state, award=drifted)


def test_live_tactical_award_rejects_repeat_source_and_missing_card() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    transaction = _secondary_transaction(
        state,
        source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
    )
    award = _award_from_transaction(transaction)
    _validate_scored_tactical_card_bindings(state=state, transactions=(transaction,))
    record = state.objective_control_records[-1]
    cloned = replace(record, record_id=f"{record.record_id}-clone")
    state.objective_control_records = [*state.objective_control_records, cloned]
    repeated = replace(
        award,
        metadata={
            **_json_map(award.metadata, label="award metadata"),
            "objective_control_record_id": cloned.record_id,
        },
    )
    with pytest.raises(
        GameLifecycleError,
        match="Tactical Secondary VP ledger must not repeat a source across boundaries",
    ):
        validate_secondary_award_semantics(state=state, award=repeated)
    _reject_duplicate_tactical_source(
        state=state,
        player_id="player-b",
        source_id="defend-stronghold",
    )


def test_restore_tactical_semantics_reject_active_card_and_wrong_transaction() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    transaction = _secondary_transaction(
        state,
        source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
    )
    state.secondary_mission_card_states = [
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            battle_round=2,
            source_result_id="p2-defend-stronghold-active",
        )
    ]
    with pytest.raises(
        GameLifecycleError,
        match="Scored tactical secondary card does not identify its ledger transaction",
    ):
        validate_secondary_transaction_semantics(state=state)
    scored = SecondaryMissionCardState.active_tactical(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        battle_round=2,
        source_result_id="p2-defend-stronghold-scored",
    ).score(transaction_id=transaction.transaction_id)
    mismatched = replace(transaction, player_id="player-b")
    state.secondary_mission_card_states = [scored]
    with pytest.raises(
        GameLifecycleError,
        match="Scored tactical secondary card does not identify its ledger transaction",
    ):
        _validate_scored_tactical_card_bindings(state=state, transactions=(mismatched,))
    kind_mismatch = replace(
        transaction,
        source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
    )
    with pytest.raises(
        GameLifecycleError,
        match="Scored tactical secondary card does not identify its ledger transaction",
    ):
        _validate_scored_tactical_card_bindings(state=state, transactions=(kind_mismatch,))
    source_mismatch = replace(transaction, source_id="bring-it-down")
    with pytest.raises(
        GameLifecycleError,
        match="Scored tactical secondary card does not identify its ledger transaction",
    ):
        _validate_scored_tactical_card_bindings(state=state, transactions=(source_mismatch,))
    record = state.objective_control_records[-1]
    cloned = replace(record, record_id=f"{record.record_id}-clone")
    state.objective_control_records = [*state.objective_control_records, cloned]
    second = replace(
        transaction,
        transaction_id=f"{transaction.transaction_id}-second",
        metadata={
            **_json_map(transaction.metadata, label="secondary metadata"),
            "objective_control_record_id": cloned.record_id,
        },
    )
    ledger = state.victory_point_ledger_for_player("player-a")
    state.victory_point_ledgers = [
        replace(
            ledger,
            victory_points=ledger.victory_points + second.amount,
            transactions=(*ledger.transactions, second),
        )
        if stored.player_id == ledger.player_id
        else stored
        for stored in state.victory_point_ledgers
    ]
    state.secondary_mission_card_states = [scored]
    with pytest.raises(
        GameLifecycleError,
        match="Tactical Secondary VP ledger must not repeat a source across boundaries",
    ):
        validate_secondary_transaction_semantics(state=state)


def test_secondary_scoring_provider_fail_closed_branches() -> None:
    assert (
        secondary_scoring_provider_kind_from_token(SecondaryScoringProviderKind.LEGACY_PHASE11F)
        is SecondaryScoringProviderKind.LEGACY_PHASE11F
    )
    with pytest.raises(
        GameLifecycleError,
        match="Secondary scoring provider kind must be a string",
    ):
        secondary_scoring_provider_kind_from_token(12)
    with pytest.raises(GameLifecycleError, match="Unsupported Secondary scoring provider kind"):
        secondary_scoring_provider_kind_from_token("not-a-provider")
    assert is_registered_phase11f_cap_probe(
        source_id="assassination",
        scoring_rule_id="phase11f-secondary-cap",
    )
    assert not is_registered_phase11f_cap_probe(
        source_id="bring-it-down",
        scoring_rule_id="bring-it-down-destroyed-vehicles",
    )
    legacy = VictoryPointAward(
        player_id="player-a",
        battle_round=1,
        phase="fight",
        amount=5,
        source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
        source_id="bring-it-down",
        scoring_timing="secondary_mission_score",
        metadata={
            "secondary_scoring_provider_kind": SecondaryScoringProviderKind.LEGACY_PHASE11F.value,
            "scoring_rule_id": "bring-it-down-destroyed-vehicles",
        },
    )
    validate_legacy_phase11f_secondary_award(award=legacy, expected=legacy)
    probe = _registered_phase11f_cap_probe_award()
    validate_legacy_phase11f_secondary_award(award=probe, expected=None)
    with pytest.raises(
        GameLifecycleError, match="Registered Phase 11F Secondary VP amount drifted"
    ):
        validate_legacy_phase11f_secondary_award(
            award=replace(probe, amount=5),
            expected=None,
        )
    with pytest.raises(
        GameLifecycleError,
        match="Registered Phase 11F Secondary VP player_id drifted",
    ):
        _validate_registered_phase11f_cap_probe(
            award=replace(probe, player_id="player-b"),
            probe=_require_registered_phase11f_cap_probe(),
        )
    with pytest.raises(
        GameLifecycleError,
        match="Registered Phase 11F Secondary VP battle_round drifted",
    ):
        _validate_registered_phase11f_cap_probe(
            award=replace(probe, battle_round=3),
            probe=_require_registered_phase11f_cap_probe(),
        )
    with pytest.raises(
        GameLifecycleError,
        match="Registered Phase 11F Secondary VP phase drifted",
    ):
        _validate_registered_phase11f_cap_probe(
            award=replace(probe, phase="fight"),
            probe=_require_registered_phase11f_cap_probe(),
        )
    with pytest.raises(
        GameLifecycleError,
        match="Registered Phase 11F Secondary VP source_kind drifted",
    ):
        _validate_registered_phase11f_cap_probe(
            award=replace(probe, source_kind=VictoryPointSourceKind.FIXED_SECONDARY),
            probe=_require_registered_phase11f_cap_probe(),
        )
    with pytest.raises(
        GameLifecycleError,
        match="Registered Phase 11F Secondary VP source_id drifted",
    ):
        _validate_registered_phase11f_cap_probe(
            award=replace(probe, source_id="cleanse"),
            probe=_require_registered_phase11f_cap_probe(),
        )
    with pytest.raises(
        GameLifecycleError,
        match="Registered Phase 11F Secondary VP scoring_timing drifted",
    ):
        _validate_registered_phase11f_cap_probe(
            award=replace(probe, scoring_timing="generic_rule_execution"),
            probe=_require_registered_phase11f_cap_probe(),
        )
    with pytest.raises(
        GameLifecycleError,
        match="Legacy Phase 11F Secondary VP requires scoring_timing secondary_mission_score",
    ):
        validate_legacy_phase11f_secondary_award(
            award=replace(legacy, scoring_timing="generic_rule_execution"),
            expected=legacy,
        )
    with pytest.raises(
        GameLifecycleError,
        match="Legacy Phase 11F Secondary VP requires scoring_rule_id",
    ):
        validate_legacy_phase11f_secondary_award(
            award=replace(
                legacy,
                metadata={
                    "secondary_scoring_provider_kind": (
                        SecondaryScoringProviderKind.LEGACY_PHASE11F.value
                    )
                },
            ),
            expected=legacy,
        )
    with pytest.raises(
        GameLifecycleError,
        match="not a registered probe or score_secondary_mission",
    ):
        validate_legacy_phase11f_secondary_award(award=legacy, expected=None)
    with pytest.raises(
        GameLifecycleError,
        match="drifted from score_secondary_mission authority",
    ):
        validate_legacy_phase11f_secondary_award(
            award=legacy,
            expected=replace(legacy, amount=legacy.amount + 1),
        )
    with pytest.raises(GameLifecycleError, match="Secondary VP provider kind drifted"):
        validate_legacy_phase11f_secondary_award(
            award=replace(
                legacy,
                metadata={
                    "secondary_scoring_provider_kind": (
                        SecondaryScoringProviderKind.GENERIC_RULE_IR.value
                    ),
                    "scoring_rule_id": "bring-it-down-destroyed-vehicles",
                },
            ),
            expected=legacy,
        )
    with pytest.raises(
        GameLifecycleError,
        match="must not carry state-backed authority",
    ):
        validate_legacy_phase11f_secondary_award(
            award=replace(
                legacy,
                metadata={
                    "secondary_scoring_provider_kind": (
                        SecondaryScoringProviderKind.LEGACY_PHASE11F.value
                    ),
                    "scoring_rule_id": "bring-it-down-destroyed-vehicles",
                    "objective_control_record_id": "oc-1",
                },
            ),
            expected=legacy,
        )
    with pytest.raises(GameLifecycleError, match="Secondary VP metadata must be an object"):
        validate_legacy_phase11f_secondary_award(
            award=replace(legacy, metadata=["not-an-object"]),
            expected=legacy,
        )
    rule_ir = VictoryPointAward(
        player_id="player-a",
        battle_round=1,
        phase="fight",
        amount=5,
        source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
        source_id="phase17d-generic-vp",
        scoring_timing="generic_rule_execution",
        metadata=_fabricated_generic_rule_ir_metadata(amount=5),
    )
    validate_generic_rule_ir_secondary_award(award=rule_ir)
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP requires scoring_timing generic_rule_execution",
    ):
        validate_generic_rule_ir_secondary_award(
            award=replace(rule_ir, scoring_timing="secondary_mission_score")
        )
    with pytest.raises(GameLifecycleError, match="Generic RuleIR Secondary VP requires rule_id"):
        validate_generic_rule_ir_secondary_award(
            award=replace(
                rule_ir,
                metadata={
                    "secondary_scoring_provider_kind": (
                        SecondaryScoringProviderKind.GENERIC_RULE_IR.value
                    ),
                    "clause_id": "clause-1",
                    "effect": {
                        "kind": "add_victory_points",
                        "parameters": [{"key": "delta", "value": 5}],
                    },
                },
            )
        )
    with pytest.raises(GameLifecycleError, match="Generic RuleIR Secondary VP requires clause_id"):
        validate_generic_rule_ir_secondary_award(
            award=replace(
                rule_ir,
                metadata={
                    "secondary_scoring_provider_kind": (
                        SecondaryScoringProviderKind.GENERIC_RULE_IR.value
                    ),
                    "rule_id": "phase17d-generic-vp",
                    "effect": {
                        "kind": "add_victory_points",
                        "parameters": [{"key": "delta", "value": 5}],
                    },
                },
            )
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP effect must be an object",
    ):
        validate_generic_rule_ir_secondary_award(
            award=replace(
                rule_ir,
                metadata={
                    "secondary_scoring_provider_kind": (
                        SecondaryScoringProviderKind.GENERIC_RULE_IR.value
                    ),
                    "rule_id": "phase17d-generic-vp",
                    "clause_id": "clause-1",
                    "effect": ["not-an-object"],
                },
            )
        )
    with pytest.raises(GameLifecycleError, match="Generic RuleIR Secondary VP effect kind drifted"):
        validate_generic_rule_ir_secondary_award(
            award=replace(
                rule_ir,
                metadata={
                    "secondary_scoring_provider_kind": (
                        SecondaryScoringProviderKind.GENERIC_RULE_IR.value
                    ),
                    "rule_id": "phase17d-generic-vp",
                    "clause_id": "clause-1",
                    "effect": {"kind": "other", "parameters": [{"key": "delta", "value": 5}]},
                },
            )
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP effect parameters must be a list",
    ):
        validate_generic_rule_ir_secondary_award(
            award=replace(
                rule_ir,
                metadata={
                    "secondary_scoring_provider_kind": (
                        SecondaryScoringProviderKind.GENERIC_RULE_IR.value
                    ),
                    "rule_id": "phase17d-generic-vp",
                    "clause_id": "clause-1",
                    "effect": {"kind": "add_victory_points", "parameters": {"key": "delta"}},
                },
            )
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP effect parameter must be an object",
    ):
        validate_generic_rule_ir_secondary_award(
            award=replace(
                rule_ir,
                metadata={
                    "secondary_scoring_provider_kind": (
                        SecondaryScoringProviderKind.GENERIC_RULE_IR.value
                    ),
                    "rule_id": "phase17d-generic-vp",
                    "clause_id": "clause-1",
                    "effect": {"kind": "add_victory_points", "parameters": ["not-an-object"]},
                },
            )
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP amount drifted from the RuleIR effect delta",
    ):
        validate_generic_rule_ir_secondary_award(
            award=replace(
                rule_ir,
                metadata={
                    "secondary_scoring_provider_kind": (
                        SecondaryScoringProviderKind.GENERIC_RULE_IR.value
                    ),
                    "rule_id": "phase17d-generic-vp",
                    "clause_id": "clause-1",
                    "effect": {
                        "kind": "add_victory_points",
                        "parameters": [{"key": "delta", "value": 4}],
                    },
                },
            )
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP amount drifted from the RuleIR effect delta",
    ):
        validate_generic_rule_ir_secondary_award(
            award=replace(
                rule_ir,
                metadata={
                    "secondary_scoring_provider_kind": (
                        SecondaryScoringProviderKind.GENERIC_RULE_IR.value
                    ),
                    "rule_id": "phase17d-generic-vp",
                    "clause_id": "clause-1",
                    "effect": {
                        "kind": "add_victory_points",
                        "parameters": [{"key": "unit", "value": "target"}],
                    },
                },
            )
        )


def test_secondary_deployment_zone_and_integrity_fail_closed_branches() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    record = state.objective_control_records[-1]
    transaction = _secondary_transaction(
        state,
        source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
    )
    award = _award_from_transaction(transaction)
    with pytest.raises(
        GameLifecycleError,
        match="Deployment-zone secondary scoring requires GameState",
    ):
        enemy_unit_ids_in_player_deployment_zone_from_battlefield(
            state=cast(GameState, object()),
            player_id="player-a",
        )
    with pytest.raises(
        GameLifecycleError,
        match="Deployment-zone secondary scoring requires GameState",
    ):
        enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary(
            state=cast(GameState, object()),
            record=record,
            player_id="player-a",
        )
    with pytest.raises(
        GameLifecycleError,
        match="Deployment-zone secondary scoring requires GameState",
    ):
        enemy_unit_ids_in_player_deployment_zone_from_model_placements(
            state=cast(GameState, object()),
            player_id="player-a",
            model_placements=(),
        )
    missing_battlefield = _bring_it_down_player_a_scored_lifecycle().state
    assert missing_battlefield is not None
    missing_battlefield.battlefield_state = None
    with pytest.raises(
        GameLifecycleError,
        match="Deployment-zone secondary scoring requires battlefield_state",
    ):
        enemy_unit_ids_in_player_deployment_zone_from_battlefield(
            state=missing_battlefield,
            player_id="player-a",
        )
    missing_setup = _bring_it_down_player_a_scored_lifecycle().state
    assert missing_setup is not None
    missing_setup.mission_setup = None
    with pytest.raises(
        GameLifecycleError,
        match="Deployment-zone secondary scoring requires MissionSetup",
    ):
        enemy_unit_ids_in_player_deployment_zone_from_model_placements(
            state=missing_setup,
            player_id="player-a",
            model_placements=(),
        )
    missing_zone_battlefield = _bring_it_down_player_a_scored_lifecycle().state
    assert missing_zone_battlefield is not None
    missing_zone_battlefield.battlefield_state = None
    with pytest.raises(
        GameLifecycleError,
        match="Deployment-zone secondary scoring requires battlefield_state",
    ):
        enemy_unit_ids_in_player_deployment_zone_from_model_placements(
            state=missing_zone_battlefield,
            player_id="player-a",
            model_placements=(),
        )
    with pytest.raises(GameLifecycleError, match="player_id is not in this game"):
        enemy_unit_ids_in_player_deployment_zone_from_model_placements(
            state=state,
            player_id="player-z",
            model_placements=(),
        )
    setup = state.mission_setup
    assert setup is not None
    state.mission_setup = replace(
        setup,
        deployment_zones=tuple(zone.with_player_id("player-b") for zone in setup.deployment_zones),
    )
    with pytest.raises(
        GameLifecycleError,
        match="Deployment-zone secondary scoring requires player zone",
    ):
        enemy_unit_ids_in_player_deployment_zone_from_model_placements(
            state=state,
            player_id="player-a",
            model_placements=(),
        )
    state.mission_setup = setup
    with pytest.raises(
        GameLifecycleError,
        match="Deployment-zone secondary scoring requires ModelPlacement rows",
    ):
        enemy_unit_ids_in_player_deployment_zone_from_model_placements(
            state=state,
            player_id="player-a",
            model_placements=(cast(ModelPlacement, object()),),
        )
    with pytest.raises(GameLifecycleError, match="Secondary VP metadata must be an object"):
        bind_state_backed_secondary_scoring_commit(
            replace(award, metadata=["not-an-object"]),
            state=state,
            record=record,
        )
    with pytest.raises(GameLifecycleError, match="Secondary VP metadata must be an object"):
        require_state_backed_secondary_scoring_commit(
            metadata=["not-an-object"],
            state=state,
            record=record,
        )
    drifted_hash = {
        **_json_map(award.metadata, label="award metadata"),
        SCORING_COMMIT_CHECKPOINT_HASH_KEY: "0" * 64,
    }
    with pytest.raises(
        GameLifecycleError,
        match="State-backed Secondary VP scoring-boundary checkpoint hash drifted",
    ):
        require_state_backed_secondary_scoring_commit(
            metadata=drifted_hash,
            state=state,
            record=record,
        )
    with pytest.raises(GameLifecycleError, match="Secondary VP metadata must be an object"):
        _legacy_score_secondary_mission_award(
            state=state,
            award=replace(award, metadata=["not-an-object"]),
        )
    with pytest.raises(
        GameLifecycleError,
        match="Legacy Phase 11F Secondary VP requires scoring_rule_id",
    ):
        _legacy_score_secondary_mission_award(
            state=state,
            award=replace(
                award,
                metadata={
                    "secondary_scoring_provider_kind": (
                        SecondaryScoringProviderKind.LEGACY_PHASE11F.value
                    )
                },
            ),
        )
    legacy_non_probe = replace(
        award,
        metadata={
            "secondary_scoring_provider_kind": SecondaryScoringProviderKind.LEGACY_PHASE11F.value,
            "scoring_rule_id": "bring-it-down-destroyed-vehicles",
        },
    )
    missing_legacy_setup = _bring_it_down_player_a_scored_lifecycle().state
    assert missing_legacy_setup is not None
    missing_legacy_setup.mission_setup = None
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP semantic validation requires MissionSetup",
    ):
        _legacy_score_secondary_mission_award(state=missing_legacy_setup, award=legacy_non_probe)
    state.secondary_unit_destruction_states = []
    assert (
        _expected_state_backed_secondary_award(
            state=state,
            player_id=award.player_id,
            source_id=award.source_id,
            source_kind=award.source_kind,
            hidden=award.hidden,
            record=record,
            metadata=award.metadata,
        )
        == award
    )
    cloned = replace(record, record_id=f"{record.record_id}-clone")
    original_authority = next(
        authority
        for authority in state.objective_control_record_authorities
        if authority.objective_control_record_id == record.record_id
    )
    state.objective_control_records = [*state.objective_control_records, cloned]
    state.objective_control_record_authorities = [
        *state.objective_control_record_authorities,
        ObjectiveControlRecordAuthority.create(
            record=cloned,
            boundary_checkpoint=original_authority.boundary_checkpoint,
            retained_sticky_objective_control_states=(
                original_authority.retained_sticky_objective_control_states
            ),
        ),
    ]
    unbound_clone = replace(
        award,
        metadata={
            **_json_map(award.metadata, label="award metadata"),
            "objective_control_record_id": cloned.record_id,
        },
    )
    with pytest.raises(
        GameLifecycleError,
        match="Secondary scoring evidence record identity drifted",
    ):
        validate_secondary_award_semantics(state=state, award=unbound_clone)
    scored_fixed = SecondaryMissionCardState.active_fixed(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
    ).score(transaction_id=transaction.transaction_id)
    _validate_scored_tactical_card_bindings(state=state, transactions=(transaction,))
    state.secondary_mission_card_states = [scored_fixed]
    _validate_scored_tactical_card_bindings(state=state, transactions=(transaction,))


__all__: list[str] = []
__all__ += ["ArmyCatalog", "BattlePhaseKind", "DecisionController", "DecisionOption"]
__all__ += ["DecisionRequest", "DecisionResult", "DestructionSourceKind", "DiceExpression"]
__all__ += ["DiceRollManager", "DiceRollResult", "DiceRollSpec", "EventLog", "EventRecord"]
__all__ += ["GENERIC_RULE_IR_EFFECT_INDEX_KEY", "GENERIC_RULE_IR_EXECUTION_CONTEXT_KEY"]
__all__ += ["GENERIC_RULE_IR_EXECUTION_EVENT_ID_KEY", "GENERIC_RULE_IR_HASH_KEY"]
__all__ += ["GENERIC_RULE_IR_SOURCE_ID_KEY", "GameConfig", "GameLifecyclePayload"]
__all__ += ["GameLifecycleStage", "JsonValue", "ModelDestructionAttribution", "ModifierOperation"]
__all__ += ["ModifierTerm", "ObjectiveControlModifierBinding", "ObjectiveControlModifierContext"]
__all__ += ["ObjectiveControlRecord", "ObjectiveControlTiming", "ObjectiveMarkerRole"]
__all__ += ["PARAMETERIZED_DECISION_OPTION_ID", "ObjectiveRuleScope"]
__all__ += ["PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT"]
__all__ += ["PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT"]
__all__ += ["PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION"]
__all__ += ["PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED"]
__all__ += ["PRIMARY_SCORING_PENDING_WINDOW_RETURN_ON_DEATH", "PendingReturnOnDeath", "Pose"]
__all__ += ["PrimaryBattlefieldDepartureState", "PrimaryMissionBoundaryCheckpoint"]
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
__all__ += ["SCORING_COMMIT_CHECKPOINT_ID_KEY", "SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY"]
__all__ += ["SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY"]
__all__ += ["SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE"]
__all__ += ["SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE", "SOURCE_KEYWORD_SEQUENCE_PARTS"]
__all__ += ["SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE", "SecondaryMissionCardStatus"]
__all__ += ["SecondaryMissionMode", "SecondaryScoringConditionContext"]
__all__ += ["TABLE_QUARTER_NORTH_WEST", "StickyObjectiveControlState", "UnitInstance"]
__all__ += ["_OC_SOURCE_RULE_ID", "UnitPlacement", "VictoryPointTransaction", "_add_unit_keyword"]
__all__ += ["_append_player_transaction_from_award"]
__all__ += ["_assert_scoring_commit_differs_from_oc_checkpoint", "_authenticated_move_unit_to"]
__all__ += ["_battlefield_dominance_lifecycle", "_card_for_state_backed_scoring"]
__all__ += ["_checkpoint_with_model_states", "_compiled_generic_vp_rule_ir"]
__all__ += ["_destroy_all_models", "_destroy_first_model", "_destroy_model_with_event"]
__all__ += ["_destroy_unit_with_events", "_emit_objective_control_boundary_event_if_missing"]
__all__ += ["_emit_oc_event", "_empty_rule_ir_authority_index"]
__all__ += ["_execute_generic_vp_on_lifecycle", "_first_unit", "_fixed_secondary_record_ids"]
__all__ += ["_generic_rule_ir_transaction", "_generic_vp_clause_and_effect"]
__all__ += ["_generic_vp_execution_context", "_offset_checkpoint_model_state"]
__all__ += ["_pending_command_boundary_lifecycle", "_pending_final_turn_end_boundary_lifecycle"]
__all__ += ["_place_in_player_deployment_zone_away_from_home"]
__all__ += ["_place_player_away_from_objectives", "_place_player_on_role"]
__all__ += ["_place_unit_interior_non_overlapping", "_queue_pending_window"]
__all__ += ["_record_for_binding", "_rehash_evidence_transactions_and_lifecycles"]
__all__ += ["_rehash_lifecycle_row", "_replace_player_transaction", "_return_destroyed_unit"]
__all__ += ["_rule_ir_authority_index", "_same_boundary_two_player_bring_it_down_lifecycle"]
__all__ += ["_scored_command_boundary_after_mutation"]
__all__ += ["_scored_determined_acquisition_command_lifecycle"]
__all__ += ["_scored_reconnaissance_turn_end_lifecycle", "_set_unit_starting_wounds"]
__all__ += ["_sticky_state_for", "_tactical_secondary_amount"]
__all__ += ["_transaction_objective_control_record_id"]
__all__ += ["_two_defender_battlefield_dominance_lifecycle"]
__all__ += ["_two_model_battlefield_dominance_lifecycle", "_uncapped_award_from_transaction"]
__all__ += ["_validate_secondary_primary_closure", "_zone_anchor_away_from_home"]
__all__ += ["append_authenticated_normal_move", "apply_generic_rule_ir_victory_points"]
__all__ += ["apply_return_on_death_placement_decision", "army_muster_request"]
__all__ += ["bound_primary_scoring_commit_checkpoint"]
__all__ += ["build_primary_rules_unit_membership_from_model_placements"]
__all__ += ["build_primary_scoring_spatial_evidence", "build_primary_scoring_state_evidence"]
__all__ += ["canonical_json", "canonical_payload_sha256", "compile_rule_source_text"]
__all__ += ["complete_setup_through_gate", "create_deterministic_battlefield_scenario"]
__all__ += ["default_rule_execution_registry", "default_unit_selection", "escape"]
__all__ += ["execute_rule_ir", "generic_rule_ir_secondary_award", "json_loads"]
__all__ += ["mark_pending_primary_scoring_boundaries", "mustered_armies"]
__all__ += ["next_generic_rule_ir_victory_point_event_id"]
__all__ += ["pending_primary_scoring_boundary_keys", "phase11c_mission_setup"]
__all__ += ["phase17n_state_with_setup", "primary_mission_model_placements_from_checkpoint"]
__all__ += ["record_new_primary_unit_destruction_events"]
__all__ += ["record_primary_battlefield_departure_event"]
__all__ += ["record_primary_destroyed_model_departures", "record_primary_scoring_state_evidence"]
__all__ += ["record_primary_turn_start_evidence_for_fixture"]
__all__ += ["record_secondary_destruction_for_fixture", "registered_phase11f_cap_probe"]
__all__ += ["request_mission_action_start", "require_generic_rule_ir_loaded_authority"]
__all__ += ["resolve_primary_scoring_boundary_lifecycle"]
__all__ += ["rules_unit_objective_proximity_witness", "ruleset"]
__all__ += ["score_primary_objective_control_boundary", "score_secondary_mission_from_state"]
__all__ += ["secondary_choice", "secondary_scoring_provider_kind_from_metadata"]
__all__ += ["validate_json_value", "validate_primary_scoring_spatial_rows_from_checkpoint"]
__all__ += ["validate_secondary_generic_rule_ir_restore_authority", "with_model_offsets"]
__all__ += ["with_unit_keywords"]
