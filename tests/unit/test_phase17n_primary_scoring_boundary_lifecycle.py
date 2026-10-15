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


def test_restore_rejects_unclosed_scoreable_boundary_after_lifecycle_advances() -> None:
    lifecycle = _pending_command_boundary_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    payload["state"]["battle_round"] = 3
    with pytest.raises(
        GameLifecycleError,
        match=escape("Primary scoring boundary remains unclosed after the lifecycle has advanced."),
    ):
        GameLifecycle.from_payload(payload)


def test_tactical_action_request_checkpoint_omits_secondary_scoring_authority_witnesses() -> None:
    lifecycle = _battlefield_dominance_lifecycle(
        phase=BattlePhase.SHOOTING,
        battle_round=2,
        player_a_secondary=SecondaryMissionMode.TACTICAL,
    )
    state = lifecycle.state
    assert state is not None
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="cleanse",
            battle_round=2,
            source_result_id="phase17n-non-oc-secondary-action",
        )
    )
    _place_player_on_role(state, player_id="player-a", role=ObjectiveMarkerRole.CENTRAL)

    waiting = request_mission_action_start(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        mission_action_id="cleanse-objective",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    request = waiting.decision_request
    assert request is not None
    checkpoint_events = tuple(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT
    )
    assert len(checkpoint_events) == 1
    checkpoint_payload = checkpoint_events[0].payload
    assert isinstance(checkpoint_payload, dict)
    assert checkpoint_payload["boundary_kind"] == "action_request"
    assert {
        "active_secondary_mission_card_jsons",
        "completed_mission_action_state_jsons",
        "primary_unit_destruction_state_jsons",
        "starting_strength_record_jsons",
    }.isdisjoint(checkpoint_payload)

    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17n-non-oc-secondary-action-start",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
    )
    action_id = "mission-action:phase17n-non-oc-secondary-action-start"
    assert state.mission_action_state_by_id(action_id).status.value == "started"
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.state is not None
    assert restored.state.mission_action_state_by_id(action_id).status.value == "started"


def test_authenticated_movement_between_oc_and_scoring_round_trips() -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="move")
    payload = lifecycle.to_payload()
    restored = GameLifecycle.from_payload(deepcopy(payload))
    assert restored.to_payload() == payload
    _assert_scoring_commit_differs_from_oc_checkpoint(lifecycle)


@pytest.mark.parametrize(
    "value_kind", ["numeric", "replacement_zero", "replacement_dash", "replacement_star"]
)
def test_forged_commit_checkpoint_modifier_source_fails_registry_restore(value_kind: str) -> None:
    lifecycle = _scored_command_boundary_after_mutation(kind="move")
    payload = deepcopy(lifecycle.to_payload())
    events = payload["decisions"]["event_log"]
    commit_event = next(
        event for event in events if event["event_type"] == PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT
    )
    raw_payload = commit_event["payload"]
    assert isinstance(raw_payload, dict)
    checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(raw_payload["checkpoint"])
    first = checkpoint.model_states[0]
    resolved_payload = validate_json_value(json_loads(first.resolved_objective_control_json))
    assert isinstance(resolved_payload, dict)
    raw_applied = resolved_payload.get("applied_modifier_ids")
    applied: list[str] = []
    if isinstance(raw_applied, list):
        for modifier_id in raw_applied:
            assert isinstance(modifier_id, str)
            applied.append(modifier_id)
    applied.append("p2-forged-oc-modifier")
    resolved_payload["applied_modifier_ids"] = validate_json_value(applied)
    if value_kind != "numeric":
        resolved_payload["value_kind"] = value_kind
        resolved_payload["base"] = 0
        resolved_payload["final"] = 0
        if value_kind != "replacement_zero":
            resolved_payload["raw"] = 0
    rewritten_states = (
        replace(first, resolved_objective_control_json=canonical_json(resolved_payload)),
        *checkpoint.model_states[1:],
    )
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
        objective_control_modifier_sources=(
            *checkpoint.objective_control_modifier_sources,
            PrimaryMissionObjectiveControlModifierSource(
                modifier_id="p2-forged-oc-modifier",
                source_id="p2-forged-oc-source",
                source_effect_id=None,
                source_effect_json=None,
            ),
        ),
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
    evidence["scoring_commit_checkpoint_id"] = rewritten.checkpoint_id
    evidence["scoring_commit_checkpoint_hash"] = rewritten.checkpoint_hash
    _rehash_evidence_transactions_and_lifecycles(
        payload,
        evidence=evidence,
        scoring_commit_checkpoint=rewritten,
    )
    with pytest.raises(GameLifecycleError, match="unregistered"):
        GameLifecycle.from_payload(payload)


def test_sticky_control_expires_during_successful_atomic_secondary() -> None:
    lifecycle, state = _defend_stronghold_ready_lifecycle()
    central = next(
        marker
        for marker in state.mission_setup.objective_markers  # type: ignore[union-attr]
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    sticky = _sticky_state_for(
        state,
        player_id="player-a",
        objective_id=central.objective_marker_id,
        active_player_id="player-b",
    )
    state.record_sticky_objective_control_state(sticky)
    _place_player_on_role(state, player_id="player-b", role=ObjectiveMarkerRole.CENTRAL)
    assert state.sticky_objective_control_states
    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=lifecycle.decision_controller.event_log,
    )
    assert state.sticky_objective_control_states == []


def test_runtime_oc_modifier_changes_secondary_scoring_result() -> None:
    def _zero_oc(context: ObjectiveControlModifierContext) -> tuple[ModifierTerm, ...]:
        assert context.current_objective_control >= 0
        return (ModifierTerm(ModifierOperation.SET, 0),)

    registry = RuntimeModifierRegistry.from_bindings(
        objective_control_modifier_bindings=(
            ObjectiveControlModifierBinding(
                modifier_id="p2-zero-oc",
                source_id="p2-zero-oc-source",
                handler=_zero_oc,
            ),
        )
    )
    modified_lifecycle, modified_state = _defend_stronghold_ready_lifecycle()
    modified_state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=modified_lifecycle.decision_controller.event_log,
        runtime_modifier_registry=registry,
    )
    baseline_lifecycle, baseline_state = _defend_stronghold_ready_lifecycle()
    scored = baseline_state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
        event_log=baseline_lifecycle.decision_controller.event_log,
    )
    assert scored.status.value == "scored"
    assert _tactical_secondary_amount(
        modified_state,
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
    ) != _tactical_secondary_amount(
        baseline_state,
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
    )


def test_failure_after_canonical_oc_projection_restores_sticky_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    original = GameState.award_victory_points

    def _fail_secondary(self: GameState, award: VictoryPointAward) -> VictoryPointTransaction:
        if self is state and award.source_kind is VictoryPointSourceKind.TACTICAL_SECONDARY:
            raise GameLifecycleError("injected secondary ledger failure")
        return original(self, award)

    monkeypatch.setattr(GameState, "award_victory_points", _fail_secondary)
    before = tuple(state.sticky_objective_control_states)
    with pytest.raises(GameLifecycleError, match="injected secondary ledger failure"):
        state.score_secondary_mission_from_state(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            mode=SecondaryMissionCardMode.TACTICAL,
            phase=BattlePhase.FIGHT,
            event_log=lifecycle.decision_controller.event_log,
        )
    assert tuple(state.sticky_objective_control_states) == before


def test_restore_rejects_secondary_transaction_with_unknown_source_id() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    ledger = _ledger_payload(payload, player_id="player-a")
    secondary = _secondary_transaction_payloads(ledger, source_kind="fixed_secondary")
    assert len(secondary) == 1
    secondary[0]["source_id"] = "unknown-secondary-mission"
    metadata = _json_object(secondary[0]["metadata"], label="secondary metadata")
    metadata["secondary_mission_id"] = "unknown-secondary-mission"
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP source is not source-backed",
    ):
        GameLifecycle.from_payload(payload)


def test_restore_secondary_semantics_cover_duplicate_and_setup_guards() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    ledger = state.victory_point_ledger_for_player("player-a")
    transaction = _secondary_transaction(
        state,
        source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
    )
    duplicate = replace(
        transaction,
        transaction_id=f"{transaction.transaction_id}-duplicate",
    )
    state.victory_point_ledgers = [
        replace(
            ledger,
            victory_points=ledger.victory_points + duplicate.amount,
            transactions=(*ledger.transactions, duplicate),
        )
        if stored.player_id == ledger.player_id
        else stored
        for stored in state.victory_point_ledgers
    ]
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP ledger must not repeat a source at one boundary",
    ):
        validate_secondary_transaction_semantics(state=state)
    restored = _bring_it_down_player_a_scored_lifecycle()
    restored_state = restored.state
    assert restored_state is not None
    restored_state.mission_setup = None
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP semantic validation requires MissionSetup",
    ):
        validate_secondary_transaction_semantics(state=restored_state)
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP semantic validation requires MissionSetup",
    ):
        _expected_state_backed_secondary_award(
            state=restored_state,
            player_id="player-a",
            source_id="bring-it-down",
            source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
            hidden=False,
            record=restored_state.objective_control_records[-1],
            metadata=transaction.metadata,
        )
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP semantic validation requires one objective-control boundary",
    ):
        _record_for_binding(
            state=restored_state,
            binding=(
                "player-a",
                VictoryPointSourceKind.FIXED_SECONDARY,
                "bring-it-down",
                "missing-objective-control-record",
            ),
        )
    drifted_lifecycle = _bring_it_down_player_a_scored_lifecycle()
    drifted_state = drifted_lifecycle.state
    assert drifted_state is not None
    drifted_transaction = _secondary_transaction(
        drifted_state,
        source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
    )
    drifted_ledger = drifted_state.victory_point_ledger_for_player("player-a")
    rewritten = replace(drifted_transaction, amount=drifted_transaction.amount + 1)
    drifted_state.victory_point_ledgers = [
        replace(
            drifted_ledger,
            victory_points=drifted_ledger.victory_points + 1,
            transactions=tuple(
                rewritten
                if stored_tx.transaction_id == drifted_transaction.transaction_id
                else stored_tx
                for stored_tx in drifted_ledger.transactions
            ),
        )
        if stored.player_id == drifted_ledger.player_id
        else stored
        for stored in drifted_state.victory_point_ledgers
    ]
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP transactions drifted from authoritative scoring-state semantics",
    ):
        validate_secondary_transaction_semantics(state=drifted_state)


def test_uncapped_secondary_award_from_transaction_validates_cap_audit() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    transaction = _secondary_transaction(
        state,
        source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
    )
    metadata = _json_map(transaction.metadata, label="secondary metadata")
    awarded = _uncapped_award_from_transaction(transaction)
    assert awarded.amount == transaction.amount
    valid_audit = replace(
        transaction,
        metadata={
            **metadata,
            "vp_cap_audit": {
                "requested_amount": transaction.amount + 1,
                "applied_amount": transaction.amount,
            },
        },
    )
    uncapped = _uncapped_award_from_transaction(valid_audit)
    assert uncapped.amount == transaction.amount + 1
    assert isinstance(uncapped.metadata, dict)
    assert "vp_cap_audit" not in uncapped.metadata
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP transaction cap audit must be an object",
    ):
        _uncapped_award_from_transaction(
            replace(transaction, metadata={**metadata, "vp_cap_audit": ["not-an-object"]})
        )
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP transaction cap audit requires positive requested_amount",
    ):
        _uncapped_award_from_transaction(
            replace(
                transaction,
                metadata={
                    **metadata,
                    "vp_cap_audit": {
                        "requested_amount": 0,
                        "applied_amount": transaction.amount,
                    },
                },
            )
        )
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP transaction cap audit applied_amount drifted",
    ):
        _uncapped_award_from_transaction(
            replace(
                transaction,
                metadata={
                    **metadata,
                    "vp_cap_audit": {
                        "requested_amount": transaction.amount + 2,
                        "applied_amount": transaction.amount + 1,
                    },
                },
            )
        )
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP transaction cap audit applied_amount exceeds requested_amount",
    ):
        _uncapped_award_from_transaction(
            replace(
                transaction,
                amount=transaction.amount + 1,
                metadata={
                    **metadata,
                    "vp_cap_audit": {
                        "requested_amount": transaction.amount,
                        "applied_amount": transaction.amount + 1,
                    },
                },
            )
        )


def test_generic_rule_ir_secondary_award_requires_execution_identity() -> None:
    award = VictoryPointAward(
        player_id="player-a",
        battle_round=1,
        phase="fight",
        amount=5,
        source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
        source_id="phase17d-generic-vp",
        scoring_timing="generic_rule_execution",
        metadata=_fabricated_generic_rule_ir_metadata(amount=5),
    )
    validate_generic_rule_ir_secondary_award(award=award)
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP requires source_kind fixed_secondary",
    ):
        validate_generic_rule_ir_secondary_award(
            award=replace(award, source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY)
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP source_id drifted from the award",
    ):
        validate_generic_rule_ir_secondary_award(
            award=replace(
                award,
                metadata=_fabricated_generic_rule_ir_metadata(
                    amount=5,
                    source_id="other-source",
                ),
            )
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP requires a SHA-256 rule_ir_hash",
    ):
        validate_generic_rule_ir_secondary_award(
            award=replace(
                award,
                metadata=_fabricated_generic_rule_ir_metadata(
                    amount=5,
                    rule_ir_hash="not-a-hash",
                ),
            )
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP requires a non-negative effect_index",
    ):
        validate_generic_rule_ir_secondary_award(
            award=replace(
                award,
                metadata=_fabricated_generic_rule_ir_metadata(amount=5, effect_index=-1),
            )
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP requires execution_event_id",
    ):
        validate_generic_rule_ir_secondary_award(
            award=replace(
                award,
                metadata=_fabricated_generic_rule_ir_metadata(
                    amount=5,
                    execution_event_id="",
                ),
            )
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP execution_context must be an object",
    ):
        validate_generic_rule_ir_secondary_award(
            award=replace(
                award,
                metadata=_fabricated_generic_rule_ir_metadata(
                    amount=5,
                    execution_context=["not-an-object"],
                ),
            )
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP execution_context player_id drifted",
    ):
        validate_generic_rule_ir_secondary_award(
            award=replace(
                award,
                metadata=_fabricated_generic_rule_ir_metadata(
                    amount=5,
                    execution_context={
                        "player_id": "player-b",
                        "battle_round": 1,
                        "phase": "fight",
                    },
                ),
            )
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP execution_context battle_round drifted",
    ):
        validate_generic_rule_ir_secondary_award(
            award=replace(
                award,
                metadata=_fabricated_generic_rule_ir_metadata(
                    amount=5,
                    execution_context={
                        "player_id": "player-a",
                        "battle_round": 2,
                        "phase": "fight",
                    },
                ),
            )
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP execution_context phase drifted",
    ):
        validate_generic_rule_ir_secondary_award(
            award=replace(
                award,
                metadata=_fabricated_generic_rule_ir_metadata(
                    amount=5,
                    execution_context={
                        "player_id": "player-a",
                        "battle_round": 1,
                        "phase": "command",
                    },
                ),
            )
        )


def test_restore_rejects_scored_tactical_rewritten_as_generic_rule_ir() -> None:
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
    _replace_player_transaction(
        state,
        replace(
            transaction,
            scoring_timing="generic_rule_execution",
            metadata=_fabricated_generic_rule_ir_metadata(
                amount=transaction.amount,
                source_id=transaction.source_id,
                execution_context={
                    "player_id": "player-a",
                    "battle_round": transaction.battle_round,
                    "phase": transaction.phase,
                },
            ),
        ),
    )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP requires source_kind fixed_secondary",
    ):
        validate_secondary_generic_rule_ir_restore_authority(
            state=state,
            event_records=lifecycle.decision_controller.event_log.records,
            rule_ir_authority_index=_empty_rule_ir_authority_index(),
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP requires source_kind fixed_secondary",
    ):
        GameLifecycle.from_payload(lifecycle.to_payload())


def test_restore_rejects_generic_rule_ir_secondary_without_execution_event() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    phase = state.current_battle_phase
    assert phase is not None
    state.award_victory_points(
        VictoryPointAward(
            player_id="player-a",
            battle_round=state.battle_round,
            phase=phase.value,
            amount=5,
            source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
            source_id="phase17d-generic-vp",
            scoring_timing="generic_rule_execution",
            metadata=_fabricated_generic_rule_ir_metadata(
                amount=5,
                execution_context={
                    "player_id": "player-a",
                    "battle_round": state.battle_round,
                    "phase": phase.value,
                },
            ),
        )
    )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP requires loaded RuleIR authority",
    ):
        GameLifecycle.from_payload(lifecycle.to_payload())
    with pytest.raises(
        GameLifecycleError,
        match="requires rule_execution_victory_points_awarded",
    ):
        validate_secondary_generic_rule_ir_restore_authority(
            state=state,
            event_records=lifecycle.decision_controller.event_log.records,
            rule_ir_authority_index=_empty_rule_ir_authority_index(),
        )


def test_restore_rejects_generic_rule_ir_hash_and_clause_absent_from_loaded_rule() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    rule_ir = _execute_generic_vp_on_lifecycle(lifecycle)
    transaction = _generic_rule_ir_transaction(state)
    drifted_hash = replace(
        transaction,
        metadata={
            **_json_map(transaction.metadata, label="generic metadata"),
            GENERIC_RULE_IR_HASH_KEY: "ab" * 32,
        },
    )
    _replace_player_transaction(state, drifted_hash)
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP execution event drifted from the ledger transaction",
    ):
        validate_secondary_generic_rule_ir_restore_authority(
            state=state,
            event_records=lifecycle.decision_controller.event_log.records,
            rule_ir_authority_index=_rule_ir_authority_index(rule_ir, player_id="player-a"),
        )
    award = _award_from_transaction(transaction)
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP rule_ir_hash drifted from RuleIR",
    ):
        require_generic_rule_ir_loaded_authority(
            award=replace(
                award,
                metadata={
                    **_json_map(award.metadata, label="award metadata"),
                    GENERIC_RULE_IR_HASH_KEY: "ab" * 32,
                },
            ),
            rule_ir=rule_ir,
        )
    matching_hash = replace(
        transaction,
        metadata={
            **_json_map(transaction.metadata, label="generic metadata"),
            GENERIC_RULE_IR_HASH_KEY: "ab" * 32,
        },
    )
    matching_event_records = tuple(
        EventRecord(
            event_id=record.event_id,
            event_type=record.event_type,
            payload=validate_json_value(matching_hash.to_payload()),
        )
        if record.event_type == RULE_EXECUTION_VICTORY_POINTS_AWARDED_EVENT_TYPE
        else record
        for record in lifecycle.decision_controller.event_log.records
    )
    _replace_player_transaction(state, matching_hash)
    with pytest.raises(
        GameLifecycleError,
        match="Runtime RuleIR source is not authoritative for this bundle",
    ):
        validate_secondary_generic_rule_ir_restore_authority(
            state=state,
            event_records=matching_event_records,
            rule_ir_authority_index=_rule_ir_authority_index(rule_ir, player_id="player-a"),
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP rule_id drifted from RuleIR",
    ):
        require_generic_rule_ir_loaded_authority(
            award=replace(
                award,
                metadata={
                    **_json_map(award.metadata, label="award metadata"),
                    "rule_id": "other-rule",
                },
            ),
            rule_ir=rule_ir,
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP clause is not in the loaded RuleIR",
    ):
        require_generic_rule_ir_loaded_authority(
            award=replace(
                award,
                metadata={
                    **_json_map(award.metadata, label="award metadata"),
                    "clause_id": "missing-clause",
                },
            ),
            rule_ir=rule_ir,
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP effect is not in the loaded RuleIR clause",
    ):
        require_generic_rule_ir_loaded_authority(
            award=replace(
                award,
                metadata={
                    **_json_map(award.metadata, label="award metadata"),
                    "effect": {
                        "kind": "add_victory_points",
                        "parameters": [{"key": "delta", "value": award.amount}],
                    },
                },
            ),
            rule_ir=rule_ir,
        )


def test_restore_rejects_duplicated_generic_rule_ir_execution() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    rule_ir = _execute_generic_vp_on_lifecycle(lifecycle)
    transaction = _generic_rule_ir_transaction(state)
    _append_player_transaction_from_award(state, _award_from_transaction(transaction))
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP execution event is bound to multiple transactions",
    ):
        validate_secondary_generic_rule_ir_restore_authority(
            state=state,
            event_records=lifecycle.decision_controller.event_log.records,
            rule_ir_authority_index=_rule_ir_authority_index(rule_ir, player_id="player-a"),
        )


def test_restore_rejects_legacy_tactical_transaction_without_scored_card() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    assert state.mission_setup is not None
    phase = state.current_battle_phase
    assert phase is not None
    award = mission_scoring_policies_from_setup(state.mission_setup).secondary_award(
        player_id="player-a",
        battle_round=state.battle_round,
        phase=phase.value,
        secondary_mission_id="behind-enemy-lines",
        source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
        hidden=False,
    )
    _append_player_transaction_from_award(state, award)
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP source does not identify an active or scored card",
    ):
        validate_secondary_transaction_semantics(state=state)


def test_restore_rejects_removed_generic_rule_ir_execution_event() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    rule_ir = _execute_generic_vp_on_lifecycle(lifecycle)
    filtered_records = tuple(
        record
        for record in lifecycle.decision_controller.event_log.records
        if record.event_type != RULE_EXECUTION_VICTORY_POINTS_AWARDED_EVENT_TYPE
    )
    assert len(filtered_records) == len(lifecycle.decision_controller.event_log.records) - 1
    with pytest.raises(
        GameLifecycleError,
        match="requires rule_execution_victory_points_awarded",
    ):
        validate_secondary_generic_rule_ir_restore_authority(
            state=state,
            event_records=filtered_records,
            rule_ir_authority_index=_rule_ir_authority_index(rule_ir, player_id="player-a"),
        )


def test_restore_preserves_registered_phase11f_and_genuine_rule_ir_secondary_awards() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    state.award_victory_points(_registered_phase11f_cap_probe_award())
    restored_probe = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored_probe.to_payload() == lifecycle.to_payload()
    rule_ir = _execute_generic_vp_on_lifecycle(lifecycle)
    event_records = lifecycle.decision_controller.event_log.records
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP requires loaded RuleIR authority",
    ):
        validate_secondary_generic_rule_ir_restore_authority(
            state=state,
            event_records=event_records,
            rule_ir_authority_index=None,
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP requires loaded RuleIR authority",
    ):
        GameLifecycle.from_payload(lifecycle.to_payload())
    validate_secondary_generic_rule_ir_restore_authority(
        state=state,
        event_records=event_records,
        rule_ir_authority_index=_rule_ir_authority_index(rule_ir, player_id="player-a"),
    )
    with pytest.raises(
        GameLifecycleError,
        match="Runtime RuleIR source is not authoritative for this bundle",
    ):
        validate_secondary_generic_rule_ir_restore_authority(
            state=state,
            event_records=event_records,
            rule_ir_authority_index=_empty_rule_ir_authority_index(),
        )


def test_restore_rejects_opponent_only_generic_rule_ir_authority() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    rule_ir = _execute_generic_vp_on_lifecycle(lifecycle)
    event_records = lifecycle.decision_controller.event_log.records
    opponent_index = _rule_ir_authority_index(rule_ir, player_id="player-b")
    with pytest.raises(
        GameLifecycleError,
        match="Runtime RuleIR source is not authoritative for this player",
    ):
        validate_secondary_generic_rule_ir_restore_authority(
            state=state,
            event_records=event_records,
            rule_ir_authority_index=opponent_index,
        )
    with pytest.raises(
        GameLifecycleError,
        match="Runtime RuleIR source is not authoritative for this player",
    ):
        opponent_index.rule_ir_for_scoring_player(
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            player_id="player-a",
        )


def test_restore_accepts_generic_rule_ir_authoritative_for_both_players() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    rule_ir = _execute_generic_vp_on_lifecycle(lifecycle, player_id="player-a")
    _execute_generic_vp_on_lifecycle(lifecycle, player_id="player-b")
    shared_index = _rule_ir_authority_index(
        rule_ir,
        player_ids=("player-a", "player-b"),
    )
    validate_secondary_generic_rule_ir_restore_authority(
        state=state,
        event_records=lifecycle.decision_controller.event_log.records,
        rule_ir_authority_index=shared_index,
    )
    for player_id in ("player-a", "player-b"):
        assert (
            shared_index.rule_ir_for_scoring_player(
                source_id=rule_ir.source_id,
                rule_ir_hash=rule_ir.ir_hash(),
                player_id=player_id,
            )
            == rule_ir
        )


def test_restore_accepts_explicitly_global_generic_rule_ir_authority() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    rule_ir = _execute_generic_vp_on_lifecycle(lifecycle)
    global_index = _rule_ir_authority_index(rule_ir, globally_registered=True)
    validate_secondary_generic_rule_ir_restore_authority(
        state=state,
        event_records=lifecycle.decision_controller.event_log.records,
        rule_ir_authority_index=global_index,
    )
    assert (
        global_index.rule_ir_for_scoring_player(
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            player_id="player-b",
        )
        == rule_ir
    )


def test_restore_rejects_empty_player_inventory_without_global_rule_ir_registration() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    rule_ir = _execute_generic_vp_on_lifecycle(lifecycle)
    unregistered = _rule_ir_authority_index(rule_ir, player_ids=())
    with pytest.raises(
        GameLifecycleError,
        match="Runtime RuleIR source is not globally registered",
    ):
        validate_secondary_generic_rule_ir_restore_authority(
            state=state,
            event_records=lifecycle.decision_controller.event_log.records,
            rule_ir_authority_index=unregistered,
        )
    with pytest.raises(GameLifecycleError, match="player_id"):
        unregistered.rule_ir_for_scoring_player(
            source_id=rule_ir.source_id,
            rule_ir_hash=rule_ir.ir_hash(),
            player_id="",
        )


def test_generic_rule_ir_scoring_authority_fail_closed_branches() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    state = lifecycle.state
    assert state is not None
    rule_ir = _compiled_generic_vp_rule_ir()
    clause, effect = _generic_vp_clause_and_effect(rule_ir)
    context = _generic_vp_execution_context(state, event_log=EventLog())
    next_generic_rule_ir_victory_point_event_id(event_log=None, fallback_id="rule-event:fallback")
    assert (
        next_generic_rule_ir_victory_point_event_id(
            event_log=EventLog(),
            fallback_id="rule-event:fallback",
        )
        == "event-000001"
    )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP event_log must be an EventLog",
    ):
        next_generic_rule_ir_victory_point_event_id(
            event_log=object(),
            fallback_id="rule-event:fallback",
        )
    with pytest.raises(GameLifecycleError, match="Generic RuleIR Secondary VP requires RuleIR"):
        generic_rule_ir_secondary_award(
            rule_ir=cast(RuleIR, object()),
            clause=clause,
            effect=effect,
            context=context,
            amount=5,
            execution_event_id="event-000001",
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP requires a RuleClause",
    ):
        generic_rule_ir_secondary_award(
            rule_ir=rule_ir,
            clause=cast(RuleClause, object()),
            effect=effect,
            context=context,
            amount=5,
            execution_event_id="event-000001",
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP requires a RuleEffectSpec",
    ):
        generic_rule_ir_secondary_award(
            rule_ir=rule_ir,
            clause=clause,
            effect=cast(RuleEffectSpec, object()),
            context=context,
            amount=5,
            execution_event_id="event-000001",
        )
    missing_phase = replace(context, phase=None)
    with pytest.raises(GameLifecycleError, match="Generic RuleIR Secondary VP requires a phase"):
        generic_rule_ir_secondary_award(
            rule_ir=rule_ir,
            clause=clause,
            effect=effect,
            context=missing_phase,
            amount=5,
            execution_event_id="event-000001",
        )
    empty_clause = replace(clause, effects=())
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP effect does not identify one clause",
    ):
        generic_rule_ir_secondary_award(
            rule_ir=rule_ir,
            clause=empty_clause,
            effect=effect,
            context=context,
            amount=5,
            execution_event_id="event-000001",
        )
    with pytest.raises(GameLifecycleError, match="Rule execution handler requires an effect"):
        apply_generic_rule_ir_victory_points(rule_ir, clause, None, context)
    missing_state = replace(context, state=None)
    with pytest.raises(GameLifecycleError, match="Rule execution requires GameState"):
        apply_generic_rule_ir_victory_points(rule_ir, clause, effect, missing_state)
    invalid_phase = apply_generic_rule_ir_victory_points(rule_ir, clause, effect, missing_phase)
    assert invalid_phase.status is RuleExecutionStatus.INVALID
    assert invalid_phase.reason == "missing_phase"
    zero_delta = replace(effect, parameters=(RuleParameter("delta", 0),))
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP requires a positive effect delta",
    ):
        apply_generic_rule_ir_victory_points(rule_ir, clause, zero_delta, context)
    fallback_context = _generic_vp_execution_context(state, event_log=None)
    fallback_result = apply_generic_rule_ir_victory_points(
        rule_ir,
        clause,
        effect,
        fallback_context,
    )
    assert fallback_result.status is RuleExecutionStatus.APPLIED
    assert fallback_result.event_records[0].event_type == (
        RULE_EXECUTION_VICTORY_POINTS_AWARDED_EVENT_TYPE
    )
    require_generic_rule_ir_loaded_authority(
        award=_award_from_transaction(_generic_rule_ir_transaction(state)),
        rule_ir=rule_ir,
    )
    with pytest.raises(GameLifecycleError, match="Generic RuleIR Secondary VP requires RuleIR"):
        require_generic_rule_ir_loaded_authority(
            award=_award_from_transaction(_generic_rule_ir_transaction(state)),
            rule_ir=cast(RuleIR, object()),
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP restore requires GameState",
    ):
        validate_secondary_generic_rule_ir_restore_authority(
            state=cast(GameState, object()),
            event_records=(),
            rule_ir_authority_index=None,
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP restore requires EventRecord values",
    ):
        validate_secondary_generic_rule_ir_restore_authority(
            state=state,
            event_records=cast(tuple[EventRecord, ...], [object()]),
            rule_ir_authority_index=None,
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP restore requires RuntimeRuleIRAuthorityIndex",
    ):
        validate_secondary_generic_rule_ir_restore_authority(
            state=state,
            event_records=(),
            rule_ir_authority_index=cast(RuntimeRuleIRAuthorityIndex, object()),
        )
    leftover_state = _bring_it_down_player_a_scored_lifecycle().state
    assert leftover_state is not None
    leftover = EventRecord(
        event_id="event-000001",
        event_type=RULE_EXECUTION_VICTORY_POINTS_AWARDED_EVENT_TYPE,
        payload={"transaction_id": "missing"},
    )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP execution events must match ledger transactions",
    ):
        validate_secondary_generic_rule_ir_restore_authority(
            state=leftover_state,
            event_records=(leftover,),
            rule_ir_authority_index=None,
        )
    duplicate_events = (
        leftover,
        EventRecord(
            event_id="event-000001",
            event_type=RULE_EXECUTION_VICTORY_POINTS_AWARDED_EVENT_TYPE,
            payload={"transaction_id": "other"},
        ),
    )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP execution events are not unique",
    ):
        validate_secondary_generic_rule_ir_restore_authority(
            state=leftover_state,
            event_records=duplicate_events,
            rule_ir_authority_index=None,
        )
    authentic = _bring_it_down_player_a_scored_lifecycle()
    authentic_state = authentic.state
    assert authentic_state is not None
    _execute_generic_vp_on_lifecycle(authentic)
    generic = _generic_rule_ir_transaction(authentic_state)
    owned_index = _rule_ir_authority_index(rule_ir, player_id="player-a")
    cap_invalid = replace(
        generic,
        metadata={
            **_json_map(generic.metadata, label="generic metadata"),
            "vp_cap_audit": ["not-an-object"],
        },
    )
    _replace_player_transaction(authentic_state, cap_invalid)
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP transaction cap audit must be an object",
    ):
        validate_secondary_generic_rule_ir_restore_authority(
            state=authentic_state,
            event_records=authentic.decision_controller.event_log.records,
            rule_ir_authority_index=owned_index,
        )
    cap_missing_amount = replace(
        generic,
        metadata={
            **_json_map(generic.metadata, label="generic metadata"),
            "vp_cap_audit": {"requested_amount": 0},
        },
    )
    _replace_player_transaction(authentic_state, cap_missing_amount)
    with pytest.raises(
        GameLifecycleError,
        match="Secondary VP transaction cap audit requires positive requested_amount",
    ):
        validate_secondary_generic_rule_ir_restore_authority(
            state=authentic_state,
            event_records=authentic.decision_controller.event_log.records,
            rule_ir_authority_index=owned_index,
        )
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP effect_index is outside its clause",
    ):
        require_generic_rule_ir_loaded_authority(
            award=replace(
                _award_from_transaction(generic),
                metadata={
                    **_json_map(generic.metadata, label="generic metadata"),
                    GENERIC_RULE_IR_EFFECT_INDEX_KEY: 99,
                },
            ),
            rule_ir=rule_ir,
        )
    generic_metadata = _json_map(generic.metadata, label="generic metadata")
    with pytest.raises(
        GameLifecycleError,
        match="Generic RuleIR Secondary VP source_id drifted from RuleIR",
    ):
        require_generic_rule_ir_loaded_authority(
            award=replace(
                _award_from_transaction(generic),
                source_id="other-source",
                metadata={
                    **generic_metadata,
                    GENERIC_RULE_IR_SOURCE_ID_KEY: "other-source",
                },
            ),
            rule_ir=rule_ir,
        )


def test_scored_tactical_card_rejects_generic_rule_ir_binding() -> None:
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
    rewritten = replace(
        transaction,
        source_kind=VictoryPointSourceKind.FIXED_SECONDARY,
        scoring_timing="generic_rule_execution",
        metadata=_fabricated_generic_rule_ir_metadata(
            amount=transaction.amount,
            source_id=transaction.source_id,
            execution_context={
                "player_id": transaction.player_id,
                "battle_round": transaction.battle_round,
                "phase": transaction.phase,
            },
        ),
    )
    with pytest.raises(
        GameLifecycleError,
        match="Scored tactical secondary card does not identify its ledger transaction",
    ):
        _validate_scored_tactical_card_bindings(state=state, transactions=(rewritten,))
    still_tactical = replace(
        transaction,
        scoring_timing="generic_rule_execution",
        metadata=_fabricated_generic_rule_ir_metadata(
            amount=transaction.amount,
            source_id=transaction.source_id,
            execution_context={
                "player_id": transaction.player_id,
                "battle_round": transaction.battle_round,
                "phase": transaction.phase,
            },
        ),
    )
    with pytest.raises(
        GameLifecycleError,
        match="Scored tactical secondary card cannot bind a generic RuleIR transaction",
    ):
        _validate_scored_tactical_card_bindings(state=state, transactions=(still_tactical,))


def test_restore_rejects_removed_objective_control_id_on_fixed_secondary() -> None:
    lifecycle = _bring_it_down_player_a_scored_lifecycle()
    payload = deepcopy(lifecycle.to_payload())
    ledger = _ledger_payload(payload, player_id="player-a")
    secondary = _secondary_transaction_payloads(ledger, source_kind="fixed_secondary")
    assert len(secondary) == 1
    metadata = _json_object(secondary[0]["metadata"], label="secondary metadata")
    metadata.pop("objective_control_record_id")
    with pytest.raises(
        GameLifecycleError,
        match="State-backed Secondary VP metadata requires objective_control_record_id",
    ):
        GameLifecycle.from_payload(payload)


def test_restore_rejects_removed_objective_control_id_on_scored_tactical() -> None:
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
    metadata = _json_object(secondary[0]["metadata"], label="secondary metadata")
    metadata.pop("objective_control_record_id")
    with pytest.raises(
        GameLifecycleError,
        match="State-backed Secondary VP metadata requires objective_control_record_id",
    ):
        GameLifecycle.from_payload(payload)


__all__: list[str] = []
__all__ += ["ArmyCatalog", "BattlePhaseKind", "DecisionController", "DecisionOption"]
__all__ += ["DecisionRequest", "DestructionSourceKind", "DiceExpression", "DiceRollManager"]
__all__ += ["GENERIC_RULE_IR_EXECUTION_CONTEXT_KEY", "DiceRollResult", "DiceRollSpec"]
__all__ += ["GENERIC_RULE_IR_EXECUTION_EVENT_ID_KEY", "GameConfig", "GameLifecyclePayload"]
__all__ += ["GameLifecycleStage", "JsonValue", "ModelDestructionAttribution", "ModelPlacement"]
__all__ += ["ObjectiveControlRecord", "ObjectiveControlRecordAuthority", "ObjectiveControlTiming"]
__all__ += ["PARAMETERIZED_DECISION_OPTION_ID", "ObjectiveRuleScope"]
__all__ += ["PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION"]
__all__ += ["PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED"]
__all__ += ["PRIMARY_SCORING_PENDING_WINDOW_RETURN_ON_DEATH", "PendingReturnOnDeath", "Pose"]
__all__ += ["PrimaryBattlefieldDepartureState", "PrimaryMissionBoundaryModelState"]
__all__ += ["PrimaryScoringBoundaryKind", "PrimaryScoringBoundaryLifecyclePayload"]
__all__ += ["PrimaryScoringBoundaryStatus", "PrimaryScoringRulesUnitPositionWitnessPayload"]
__all__ += ["PrimaryScoringStateEvidence", "PrimaryScoringStateEvidencePayload"]
__all__ += ["RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE", "PrimaryTerritoryUnitWitness"]
__all__ += ["RegisteredPhase11FCapProbe", "ReturnDestroyedTargetScope", "ReturnRestoreWoundsMode"]
__all__ += ["RuleEffectKind", "RuleExecutionContext", "RuleSourceText", "RulesetDescriptor"]
__all__ += ["SCORING_COMMIT_CHECKPOINT_HASH_KEY", "RuntimeRuleIRSourceKey"]
__all__ += ["SCORING_COMMIT_CHECKPOINT_ID_KEY", "SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY"]
__all__ += ["SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY"]
__all__ += ["SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE"]
__all__ += ["SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE", "SOURCE_KEYWORD_SEQUENCE_PARTS"]
__all__ += ["SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE", "SecondaryMissionCardStatus"]
__all__ += ["SecondaryScoringConditionContext", "SecondaryScoringProviderKind"]
__all__ += ["TABLE_QUARTER_NORTH_WEST", "StickyObjectiveControlState", "UnitInstance"]
__all__ += ["_OC_SOURCE_RULE_ID", "UnitPlacement", "VictoryPointCapBucket", "_add_unit_keyword"]
__all__ += ["_authenticated_move_unit_to", "_card_for_state_backed_scoring"]
__all__ += ["_checkpoint_with_model_states", "_destroy_all_models", "_destroy_first_model"]
__all__ += ["_destroy_model_with_event", "_destroy_unit_with_events"]
__all__ += ["_emit_objective_control_boundary_event_if_missing", "_emit_oc_event", "_first_unit"]
__all__ += ["_fixed_secondary_record_ids", "_json_list", "_legacy_score_secondary_mission_award"]
__all__ += ["_offset_checkpoint_model_state", "_pending_final_turn_end_boundary_lifecycle"]
__all__ += ["_place_in_player_deployment_zone_away_from_home"]
__all__ += ["_place_player_away_from_objectives", "_place_unit_interior_non_overlapping"]
__all__ += ["_queue_pending_window", "_rehash_lifecycle_row", "_reject_duplicate_tactical_source"]
__all__ += ["_replace_secondary_scoring_evidence_binding_from_payload"]
__all__ += ["_require_registered_phase11f_cap_probe", "_return_destroyed_unit"]
__all__ += ["_same_boundary_bring_it_down_and_assassination_lifecycle"]
__all__ += ["_same_boundary_two_player_bring_it_down_lifecycle"]
__all__ += ["_scored_determined_acquisition_command_lifecycle"]
__all__ += ["_scored_reconnaissance_turn_end_lifecycle", "_secondary_transaction_payload"]
__all__ += ["_set_unit_starting_wounds", "_single_mode_bring_it_down_lifecycle"]
__all__ += ["_swap_secondary_scoring_evidence_bindings"]
__all__ += ["_transaction_objective_control_record_id", "_transaction_record_id"]
__all__ += ["_two_defender_battlefield_dominance_lifecycle"]
__all__ += ["_two_model_battlefield_dominance_lifecycle"]
__all__ += ["_two_player_bring_it_down_scored_lifecycle", "_two_round_bring_it_down_lifecycle"]
__all__ += ["_validate_registered_phase11f_cap_probe", "_validate_secondary_primary_closure"]
__all__ += ["_zone_anchor_away_from_home", "append_authenticated_normal_move"]
__all__ += ["apply_return_on_death_placement_decision", "army_muster_request"]
__all__ += ["bind_state_backed_secondary_scoring_commit"]
__all__ += ["bound_primary_scoring_commit_checkpoint"]
__all__ += ["build_primary_rules_unit_membership_from_model_placements"]
__all__ += ["build_primary_scoring_spatial_evidence", "build_primary_scoring_state_evidence"]
__all__ += ["canonical_payload_sha256", "compile_rule_source_text", "complete_setup_through_gate"]
__all__ += ["create_deterministic_battlefield_scenario", "default_rule_execution_registry"]
__all__ += ["default_unit_selection"]
__all__ += ["enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary"]
__all__ += ["enemy_unit_ids_in_player_deployment_zone_from_battlefield"]
__all__ += ["enemy_unit_ids_in_player_deployment_zone_from_model_placements", "execute_rule_ir"]
__all__ += ["is_registered_phase11f_cap_probe", "mark_pending_primary_scoring_boundaries"]
__all__ += ["mustered_armies", "pending_primary_scoring_boundary_keys", "phase11c_mission_setup"]
__all__ += ["phase17n_event_setup", "phase17n_state_with_setup"]
__all__ += ["primary_mission_model_placements_from_checkpoint"]
__all__ += ["record_new_primary_unit_destruction_events"]
__all__ += ["record_primary_battlefield_departure_event"]
__all__ += ["record_primary_destroyed_model_departures", "record_primary_scoring_state_evidence"]
__all__ += ["record_primary_turn_start_evidence_for_fixture"]
__all__ += ["record_secondary_destruction_for_fixture", "registered_phase11f_cap_probe"]
__all__ += ["require_source_backed_secondary_cap_bucket"]
__all__ += ["require_state_backed_secondary_scoring_commit"]
__all__ += ["resolve_primary_scoring_boundary_lifecycle"]
__all__ += ["rules_unit_objective_proximity_witness", "ruleset"]
__all__ += ["score_primary_objective_control_boundary", "score_secondary_mission_from_state"]
__all__ += ["secondary_choice", "secondary_scoring_provider_kind_from_metadata"]
__all__ += ["secondary_scoring_provider_kind_from_token"]
__all__ += ["state_backed_secondary_binding_identity"]
__all__ += ["state_backed_secondary_objective_control_record_id"]
__all__ += ["validate_legacy_phase11f_secondary_award"]
__all__ += ["validate_primary_scoring_spatial_rows_from_checkpoint"]
__all__ += ["validate_secondary_award_semantics", "validate_state_backed_secondary_award_binding"]
__all__ += ["validate_state_backed_secondary_ledger_binding", "with_model_offsets"]
__all__ += ["with_unit_keywords"]
