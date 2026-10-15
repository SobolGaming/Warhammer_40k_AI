from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase17n_primary_scoring_grammar import (
    SUPPORTED_PRIMARY_SCORING_TIMINGS,
    BattlefieldRuntimeState,
    DestructionSourceKind,
    EndTurnCleanupState,
    EventLog,
    GameLifecycleError,
    GameLifecycleStage,
    GameState,
    MissionPackError,
    MissionScoringPolicies,
    MissionScoringPolicy,
    MissionScoringResolutionMode,
    MissionScoringRuleDefinition,
    MissionSetup,
    ModelDestructionAttribution,
    ModelPlacement,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
    ObjectiveMarkerModelWitness,
    PlayerPrimaryMissionAssignment,
    Pose,
    PrimaryComponentTurnStartMembership,
    PrimaryMissionDefinition,
    PrimaryMissionProgressState,
    PrimaryMissionScoringRule,
    PrimaryObjectiveMarkerWitness,
    PrimaryRulesUnitTurnStartMembership,
    PrimaryRulesUnitTurnStartSnapshot,
    PrimaryScoringBoundaryKind,
    PrimaryScoringResolutionCandidate,
    PrimaryScoringResolutionMode,
    PrimaryScoringStateEvidence,
    PrimaryUnattributedDestructionCause,
    PrimaryUnitDestructionState,
    ResolvedPrimaryScoringCandidate,
    RulesetDescriptor,
    RulesUnitObjectiveProximityWitness,
    UnitInstance,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
    VictoryPointTransaction,
    _attributed_destruction_state,
    _build_tracking_destruction,
    _candidate,
    _catalog_tracking_state,
    _deadly_demise_attribution,
    _evidence_model_placement,
    _minimal_evidence_game_state,
    _record_tracking_destruction_models,
    _runtime_policy,
    _runtime_rule,
    _source_objective_witness,
    _source_primary_mission,
    _source_rule,
    _test_primary_state_evidence,
    _turn_start_component,
    _turn_start_snapshot,
    _unattributed_destruction_state,
    _validate_destruction_states,
    _validate_turn_start_snapshots,
    attached_selected_to_fight_risk_fixture,
    battle_state_with_army,
    bloodcrushers_army,
    bloodcrushers_battlefield_state,
    bloodcrushers_package,
    bloodcrushers_unit,
    build_primary_rules_unit_turn_start_snapshot,
    build_primary_unit_destruction_state,
    chapter_approved_2026_27_mission_pack,
    current_primary_component_turn_start_membership,
    current_primary_rules_unit_turn_start_membership,
    destruction_source_objective_proximity_witness,
    objective_control_record_hash,
    primary_rules_unit_turn_start_membership_for_lineage,
    primary_rules_unit_turn_start_snapshots_from_payload,
    primary_rules_unit_turn_start_snapshots_with_created_unit,
    primary_scoring_resolution_mode_from_token,
    primary_scoring_timing_applies,
    primary_unit_destruction_id,
    pytest,
    record_primary_destroyed_model_departures,
    record_primary_rules_unit_turn_start_snapshot,
    record_primary_turn_start_evidence,
    record_primary_unit_destructions_for_destroyed_models,
    record_primary_unit_destructions_for_end_turn_cleanup,
    replace,
    resolve_primary_scoring_candidates,
    rules_unit_objective_proximity_witness,
    validate_primary_objective_turn_start_states,
    validate_primary_rules_unit_turn_start_snapshots,
    validate_primary_unit_destruction_source_witness_identity,
    validate_primary_unit_destruction_states,
    validate_primary_unit_destruction_turn_start_evidence,
    validate_victory_point_ledger_policy,
    warhammer_event_companion_2026_07_mission_pack,
)


def test_phase17n_independent_primary_rules_remain_independent_awards() -> None:
    first = _candidate(rule_id="rule-a", amount=2)
    second = _candidate(rule_id="rule-b", amount=3)

    resolved = resolve_primary_scoring_candidates((second, first))

    assert tuple(result.candidate for result in resolved) == (first, second)
    assert resolved[0].metadata() == {
        "primary_scoring_resolution_mode": "independent",
        "primary_scoring_resolution_group_id": None,
        "primary_scoring_achieved_rule_ids": ["rule-a"],
        "primary_scoring_selected_rule_ids": ["rule-a"],
        "primary_scoring_suppressed_rule_ids": [],
    }


def test_phase17n_cumulative_primary_rules_select_every_achieved_branch() -> None:
    first = _candidate(
        rule_id="normal-branch",
        amount=3,
        mode=PrimaryScoringResolutionMode.CUMULATIVE,
        group_id="cumulative-group",
    )
    second = _candidate(
        rule_id="bonus-branch",
        amount=2,
        mode=PrimaryScoringResolutionMode.CUMULATIVE,
        group_id="cumulative-group",
    )

    resolved = resolve_primary_scoring_candidates((first, second))

    assert sum(result.candidate.amount for result in resolved) == 5
    assert {result.candidate.rule_id for result in resolved} == {
        "normal-branch",
        "bonus-branch",
    }
    assert all(
        result.metadata()["primary_scoring_selected_rule_ids"] == ["bonus-branch", "normal-branch"]
        for result in resolved
    )
    assert all(
        result.metadata()["primary_scoring_suppressed_rule_ids"] == [] for result in resolved
    )


def test_phase17n_cumulative_primary_awards_share_the_source_backed_round_cap() -> None:
    policy = _runtime_policy(
        (
            _runtime_rule(
                rule_id="determined-acquisition-each-objective",
                timing="command_phase",
                group_id="determined-acquisition-command-primary",
            ),
            _runtime_rule(
                rule_id="determined-acquisition-opponent-territory-bonus",
                timing="command_phase",
                group_id="determined-acquisition-command-primary",
            ),
        )
    )
    assert policy.primary_max_vp_per_turn == 15
    resolved = resolve_primary_scoring_candidates(
        (
            _candidate(
                rule_id="determined-acquisition-each-objective",
                amount=12,
                mode=PrimaryScoringResolutionMode.CUMULATIVE,
                group_id="determined-acquisition-command-primary",
            ),
            _candidate(
                rule_id="determined-acquisition-opponent-territory-bonus",
                amount=6,
                mode=PrimaryScoringResolutionMode.CUMULATIVE,
                group_id="determined-acquisition-command-primary",
            ),
        )
    )
    assert sum(result.candidate.amount for result in resolved) == 18

    record = ObjectiveControlRecord(
        record_id="objective-control:round-02:player-a:command:phase_end",
        game_id="phase17n-primary-round-cap",
        battle_round=2,
        active_player_id="player-a",
        timing=ObjectiveControlTiming.PHASE_END,
        phase="command",
        battlefield_id="phase17n-primary-round-cap-battlefield",
        results=(
            ObjectiveControlResult(
                objective_id="objective-a",
                status=ObjectiveControlStatus.UNCONTROLLED,
                controlled_by_player_id=None,
                scores=(),
            ),
        ),
    )
    state_evidence = _test_primary_state_evidence(record=record, end_of_battle=False)
    ledger = VictoryPointLedger.initial(player_id="player-a")
    transactions: list[VictoryPointTransaction] = []
    for result in resolved:
        rule = next(
            rule
            for rule in policy.primary_scoring_rules
            if rule.rule_id == result.candidate.rule_id
        )
        award = VictoryPointAward(
            player_id="player-a",
            battle_round=2,
            phase="command",
            amount=result.candidate.amount,
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id=policy.primary_mission_id,
            scoring_timing="phase_end",
            metadata={
                **result.metadata(),
                "objective_control_record_id": record.record_id,
                "primary_scoring_state_evidence_id": state_evidence.evidence_id,
                "primary_scoring_state_evidence_hash": state_evidence.evidence_hash,
                "score_count": result.candidate.amount // rule.victory_points,
                "scoring_rule_condition": rule.condition,
                "scoring_rule_id": rule.rule_id,
                "scoring_rule_source_id": rule.source_id,
                "victory_points_per_count": rule.victory_points,
            },
        )
        applied_amount, metadata = policy.capped_award_for_ledger(
            ledger=ledger,
            award=award,
            objective_control_records=(record,),
            primary_scoring_state_evidence_records=(state_evidence,),
            turn_order=("player-a", "player-b"),
            current_active_player_id="player-a",
        )
        ledger, transaction = ledger.award(
            award,
            applied_amount=applied_amount,
            metadata=metadata,
        )
        transactions.append(transaction)

    assert tuple(transaction.amount for transaction in transactions) == (12, 3)
    assert ledger.victory_points == 15
    cap_metadata = transactions[-1].metadata
    assert isinstance(cap_metadata, dict)
    assert cap_metadata["vp_cap_audit"] == {
        "requested_amount": 6,
        "applied_amount": 3,
        "source_cap": 50,
        "source_points_before": 12,
        "source_points_after": 15,
        "total_cap": 100,
        "total_points_before": 12,
        "total_points_after": 15,
        "capped_reasons": ["primary_battle_round_vp_cap"],
        "primary_battle_round_cap": 15,
        "primary_battle_round_points_before": 12,
        "primary_battle_round_points_after": 15,
    }
    assert validate_victory_point_ledger_policy(
        policy=policy,
        ledger=ledger,
        objective_control_records=(record,),
        primary_scoring_state_evidence_records=(state_evidence,),
        turn_order=("player-a", "player-b"),
    ).primary_binding_identities == frozenset(
        (record.record_id, result.candidate.rule_id) for result in resolved
    )


def test_phase17n_round_two_primary_cannot_impersonate_end_of_battle_scoring() -> None:
    rule = _runtime_rule(
        rule_id="assigned-end-of-battle-primary",
        timing="end_of_battle",
        mode=MissionScoringResolutionMode.INDEPENDENT,
        group_id=None,
    )
    policy = _runtime_policy((rule,))
    record = ObjectiveControlRecord(
        record_id="objective-control:round-02:player-b:fight:turn_end",
        game_id="phase17n-primary-eob-spoof",
        battle_round=2,
        active_player_id="player-b",
        timing=ObjectiveControlTiming.TURN_END,
        phase="fight",
        battlefield_id="phase17n-primary-eob-spoof-battlefield",
        results=(
            ObjectiveControlResult(
                objective_id="objective-a",
                status=ObjectiveControlStatus.UNCONTROLLED,
                controlled_by_player_id=None,
                scores=(),
            ),
        ),
    )
    state_evidence = _test_primary_state_evidence(record=record, end_of_battle=True)
    award = VictoryPointAward(
        player_id="player-a",
        battle_round=2,
        phase="fight",
        amount=2,
        source_kind=VictoryPointSourceKind.PRIMARY,
        source_id=policy.primary_mission_id,
        scoring_timing="end_of_battle",
        metadata={
            "objective_control_record_id": record.record_id,
            "primary_scoring_state_evidence_id": state_evidence.evidence_id,
            "primary_scoring_state_evidence_hash": state_evidence.evidence_hash,
            "score_count": 1,
            "scoring_rule_condition": rule.condition,
            "scoring_rule_id": rule.rule_id,
            "scoring_rule_source_id": rule.source_id,
            "victory_points_per_count": rule.victory_points,
        },
    )

    with pytest.raises(GameLifecycleError, match="final Fight-phase TURN_END boundary"):
        policy.capped_award_for_ledger(
            ledger=VictoryPointLedger.initial(player_id="player-a"),
            award=award,
            objective_control_records=(record,),
            primary_scoring_state_evidence_records=(state_evidence,),
            turn_order=("player-a", "player-b"),
            current_active_player_id="player-b",
        )


def test_phase17n_exclusive_primary_rules_select_only_the_highest_vp_branch() -> None:
    lower = _candidate(
        rule_id="three-quarter-branch",
        amount=3,
        mode=PrimaryScoringResolutionMode.EXCLUSIVE_HIGHEST,
        group_id="quarter-group",
    )
    higher = _candidate(
        rule_id="four-quarter-branch",
        amount=6,
        mode=PrimaryScoringResolutionMode.EXCLUSIVE_HIGHEST,
        group_id="quarter-group",
    )

    resolved = resolve_primary_scoring_candidates((lower, higher))

    assert tuple(result.candidate for result in resolved) == (higher,)
    assert resolved[0].metadata() == {
        "primary_scoring_resolution_mode": "exclusive_highest",
        "primary_scoring_resolution_group_id": "quarter-group",
        "primary_scoring_achieved_rule_ids": [
            "four-quarter-branch",
            "three-quarter-branch",
        ],
        "primary_scoring_selected_rule_ids": ["four-quarter-branch"],
        "primary_scoring_suppressed_rule_ids": ["three-quarter-branch"],
    }


def test_phase17n_exclusive_equal_vp_tie_breaks_by_stable_rule_id() -> None:
    later = _candidate(
        rule_id="z-branch",
        amount=3,
        mode=PrimaryScoringResolutionMode.EXCLUSIVE_HIGHEST,
        group_id="equal-vp-group",
    )
    earlier = _candidate(
        rule_id="a-branch",
        amount=3,
        mode=PrimaryScoringResolutionMode.EXCLUSIVE_HIGHEST,
        group_id="equal-vp-group",
    )

    forward = resolve_primary_scoring_candidates((later, earlier))
    reverse = resolve_primary_scoring_candidates((earlier, later))

    assert forward == reverse
    assert tuple(result.candidate.rule_id for result in forward) == ("a-branch",)


def test_phase17n_primary_resolution_fails_closed_for_invalid_groups() -> None:
    with pytest.raises(GameLifecycleError, match="must not have a group ID"):
        _candidate(rule_id="independent", amount=1, group_id="not-allowed")
    with pytest.raises(GameLifecycleError, match="requires a group ID"):
        _candidate(
            rule_id="grouped",
            amount=1,
            mode=PrimaryScoringResolutionMode.CUMULATIVE,
        )

    cumulative = _candidate(
        rule_id="cumulative",
        amount=1,
        mode=PrimaryScoringResolutionMode.CUMULATIVE,
        group_id="shared-group",
    )
    exclusive = _candidate(
        rule_id="exclusive",
        amount=2,
        mode=PrimaryScoringResolutionMode.EXCLUSIVE_HIGHEST,
        group_id="shared-group",
    )
    with pytest.raises(GameLifecycleError, match="must use one resolution mode"):
        resolve_primary_scoring_candidates((cumulative, exclusive))


def test_phase17n_primary_resolution_rejects_duplicates_and_unknown_modes() -> None:
    candidate = _candidate(rule_id="duplicate", amount=1)
    with pytest.raises(GameLifecycleError, match="must not duplicate rule IDs"):
        resolve_primary_scoring_candidates((candidate, candidate))
    with pytest.raises(GameLifecycleError, match="Unsupported Primary scoring resolution mode"):
        primary_scoring_resolution_mode_from_token("select_everything")


@pytest.mark.parametrize(
    ("achieved", "selected", "suppressed", "expected_error"),
    [
        (
            cast(tuple[str, ...], ["rule-a"]),
            ("rule-a",),
            (),
            "achieved_rule_ids must be a tuple",
        ),
        (
            ("rule-a", "rule-a"),
            ("rule-a",),
            (),
            "achieved_rule_ids must not contain duplicates",
        ),
        ((), ("rule-a",), (), "achieved_rule_ids must contain at least 1 values"),
        (
            ("rule-a", "rule-b"),
            ("rule-a",),
            (),
            "selected and suppressed rules must partition achieved rules",
        ),
        (
            ("rule-a",),
            ("rule-a",),
            ("rule-a",),
            "cannot be selected and suppressed",
        ),
        (
            ("rule-a", "rule-b"),
            ("rule-b",),
            ("rule-a",),
            "candidate must be a selected rule",
        ),
    ],
)
def test_phase17n_resolved_primary_candidate_partition_fails_closed(
    achieved: tuple[str, ...],
    selected: tuple[str, ...],
    suppressed: tuple[str, ...],
    expected_error: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=expected_error):
        ResolvedPrimaryScoringCandidate(
            candidate=_candidate(rule_id="rule-a", amount=1),
            achieved_rule_ids=achieved,
            selected_rule_ids=selected,
            suppressed_rule_ids=suppressed,
        )


def test_phase17n_source_scoring_rule_tuple_requires_a_complete_cohesive_group() -> None:
    singleton = _source_rule(rule_id="singleton")
    with pytest.raises(MissionPackError, match="must contain at least two rules"):
        _source_primary_mission((singleton,))

    mismatched_timing = _source_rule(rule_id="timing", timing="command_phase")
    with pytest.raises(
        MissionPackError,
        match="must share timing, source kind, and resolution mode",
    ):
        _source_primary_mission((singleton, mismatched_timing))

    mismatched_source_kind = _source_rule(
        rule_id="source-kind",
        source_kind="fixed_secondary",
    )
    with pytest.raises(
        MissionPackError,
        match="must share timing, source kind, and resolution mode",
    ):
        _source_primary_mission((singleton, mismatched_source_kind))

    mismatched_mode = _source_rule(
        rule_id="mode",
        mode=MissionScoringResolutionMode.EXCLUSIVE_HIGHEST,
    )
    with pytest.raises(
        MissionPackError,
        match="must share timing, source kind, and resolution mode",
    ):
        _source_primary_mission((singleton, mismatched_mode))


def test_phase17n_runtime_primary_policy_requires_a_complete_cohesive_group() -> None:
    singleton = _runtime_rule(rule_id="singleton")
    with pytest.raises(GameLifecycleError, match="must contain at least two rules"):
        _runtime_policy((singleton,))

    mismatched_timing = _runtime_rule(rule_id="timing", timing="command_phase")
    with pytest.raises(
        GameLifecycleError,
        match="must share timing, source kind, and resolution mode",
    ):
        _runtime_policy((singleton, mismatched_timing))

    mismatched_mode = _runtime_rule(
        rule_id="mode",
        mode=MissionScoringResolutionMode.EXCLUSIVE_HIGHEST,
    )
    with pytest.raises(
        GameLifecycleError,
        match="must share timing, source kind, and resolution mode",
    ):
        _runtime_policy((singleton, mismatched_mode))


def test_phase17n_resolution_groups_cannot_span_mission_cards() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    grouped_mission = next(
        mission
        for mission in mission_pack.primary_missions
        if mission.primary_mission_id == "primary-battlefield-dominance"
    )
    target_mission = next(
        mission
        for mission in mission_pack.primary_missions
        if mission.primary_mission_id == "primary-meatgrinder"
    )
    duplicate_group_owner = replace(
        target_mission,
        scoring_rules=tuple(
            replace(
                rule,
                rule_id=f"foreign-{rule.rule_id}",
                source_id=f"foreign:{rule.source_id}",
            )
            for rule in grouped_mission.scoring_rules
            if rule.resolution_group_id is not None
        ),
    )

    with pytest.raises(MissionPackError, match="must not span mission cards"):
        replace(
            mission_pack,
            primary_missions=tuple(
                duplicate_group_owner
                if mission.primary_mission_id == duplicate_group_owner.primary_mission_id
                else mission
                for mission in mission_pack.primary_missions
            ),
        )


def test_phase17n_runtime_resolution_groups_cannot_span_player_cards() -> None:
    player_a = _runtime_policy(
        (_runtime_rule(rule_id="a-normal"), _runtime_rule(rule_id="a-bonus")),
        player_id="player-a",
        primary_mission_id="primary-a",
    )
    player_b = _runtime_policy(
        (_runtime_rule(rule_id="b-normal"), _runtime_rule(rule_id="b-bonus")),
        player_id="player-b",
        primary_mission_id="primary-b",
    )
    assignments = tuple(
        PlayerPrimaryMissionAssignment(
            player_id=policy.player_id,
            force_disposition_id=policy.force_disposition_id,
            primary_mission_id=policy.primary_mission_id,
        )
        for policy in (player_a, player_b)
    )

    with pytest.raises(GameLifecycleError, match="must not span mission cards"):
        MissionScoringPolicies(
            source_id="source:policies",
            mission_setup_source_id="source:setup",
            mission_pool_entry_id="mission-pool-entry",
            primary_mission_assignments=assignments,
            player_policies=(player_a, player_b),
        )


def test_phase17n_scoring_rule_payloads_reject_missing_and_unknown_fields() -> None:
    source_payload = dict(
        _source_rule(
            rule_id="source-payload",
            mode=MissionScoringResolutionMode.INDEPENDENT,
            group_id=None,
        ).to_payload()
    )
    source_payload["unexpected"] = "field"
    with pytest.raises(MissionPackError, match="payload fields are invalid"):
        MissionScoringRuleDefinition.from_payload(source_payload)
    source_payload.pop("unexpected")
    source_payload.pop("resolution_group_id")
    with pytest.raises(MissionPackError, match="payload fields are invalid"):
        MissionScoringRuleDefinition.from_payload(source_payload)

    runtime_payload = dict(
        _runtime_rule(
            rule_id="runtime-payload",
            mode=MissionScoringResolutionMode.INDEPENDENT,
            group_id=None,
        ).to_payload()
    )
    runtime_payload["unexpected"] = "field"
    with pytest.raises(GameLifecycleError, match="payload fields are invalid"):
        PrimaryMissionScoringRule.from_payload(runtime_payload)
    runtime_payload.pop("unexpected")
    runtime_payload.pop("resolution_group_id")
    with pytest.raises(GameLifecycleError, match="payload fields are invalid"):
        PrimaryMissionScoringRule.from_payload(runtime_payload)


def test_phase17n_turn_start_context_and_current_lookup_fail_closed() -> None:
    state, unit = _catalog_tracking_state()
    mission_setup = state.mission_setup
    battlefield = state.battlefield_state
    phase_index = state.battle_phase_index
    assert mission_setup is not None
    assert battlefield is not None
    assert phase_index is not None

    state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="requires an active player"):
        record_primary_turn_start_evidence(state=state)
    state.active_player_id = "player-khorne"

    state.battle_phase_index = None
    with pytest.raises(GameLifecycleError, match="requires a battle phase"):
        record_primary_turn_start_evidence(state=state)
    state.battle_phase_index = phase_index

    state.mission_setup = None
    with pytest.raises(GameLifecycleError, match="requires mission and battlefield state"):
        build_primary_rules_unit_turn_start_snapshot(state=state)
    state.mission_setup = mission_setup

    state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="requires an active player"):
        build_primary_rules_unit_turn_start_snapshot(state=state)
    state.active_player_id = "player-khorne"

    state.battlefield_state = replace(battlefield, terrain_features=())
    with pytest.raises(GameLifecycleError, match="terrain parity"):
        build_primary_rules_unit_turn_start_snapshot(state=state)
    state.battlefield_state = battlefield

    snapshot = build_primary_rules_unit_turn_start_snapshot(state=state)
    state.primary_rules_unit_turn_start_snapshots = [snapshot]
    assert (
        current_primary_rules_unit_turn_start_membership(
            state=state,
            unit_instance_id=unit.unit_instance_id,
        ).rules_unit_instance_id
        == unit.unit_instance_id
    )
    assert (
        current_primary_component_turn_start_membership(
            state=state,
            unit_instance_id=unit.unit_instance_id,
        ).unit_instance_id
        == unit.unit_instance_id
    )

    with pytest.raises(GameLifecycleError, match="lookup requires GameState"):
        current_primary_rules_unit_turn_start_membership(
            state=cast(GameState, object()),
            unit_instance_id=unit.unit_instance_id,
        )
    state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="lookup requires an active player"):
        current_primary_rules_unit_turn_start_membership(
            state=state,
            unit_instance_id=unit.unit_instance_id,
        )
    state.active_player_id = "player-khorne"
    state.primary_rules_unit_turn_start_snapshots = []
    with pytest.raises(GameLifecycleError, match="exactly one current-turn snapshot"):
        current_primary_rules_unit_turn_start_membership(
            state=state,
            unit_instance_id=unit.unit_instance_id,
        )


def test_phase17n_turn_start_snapshot_recording_rejects_context_drift() -> None:
    state, _unit = _catalog_tracking_state()
    snapshot = build_primary_rules_unit_turn_start_snapshot(state=state)
    mission_setup = state.mission_setup
    assert mission_setup is not None

    with pytest.raises(GameLifecycleError, match="must be a typed snapshot"):
        record_primary_rules_unit_turn_start_snapshot(
            state=state,
            snapshot=cast(PrimaryRulesUnitTurnStartSnapshot, object()),
        )
    state.mission_setup = None
    with pytest.raises(GameLifecycleError, match="requires mission and active-player state"):
        record_primary_rules_unit_turn_start_snapshot(state=state, snapshot=snapshot)
    state.mission_setup = mission_setup

    with pytest.raises(GameLifecycleError, match="game_id drift"):
        record_primary_rules_unit_turn_start_snapshot(
            state=state,
            snapshot=replace(snapshot, game_id="game-drift"),
        )
    with pytest.raises(GameLifecycleError, match="must match the current player turn"):
        record_primary_rules_unit_turn_start_snapshot(
            state=state,
            snapshot=replace(snapshot, active_player_id="player-opponent"),
        )
    with pytest.raises(GameLifecycleError, match="does not match authoritative geometry"):
        record_primary_rules_unit_turn_start_snapshot(
            state=state,
            snapshot=replace(snapshot, source_id="source-drift"),
        )

    record_primary_rules_unit_turn_start_snapshot(state=state, snapshot=snapshot)
    with pytest.raises(GameLifecycleError, match="already exists for this player turn"):
        record_primary_rules_unit_turn_start_snapshot(state=state, snapshot=snapshot)


def test_phase17n_turn_start_evidence_is_atomic_per_player_turn() -> None:
    state, _unit = _catalog_tracking_state()
    record_primary_turn_start_evidence(state=state)
    position_snapshot = state.primary_rules_unit_turn_start_snapshots[0]

    state.primary_rules_unit_turn_start_snapshots.clear()
    before = state.to_payload()
    with pytest.raises(GameLifecycleError, match="objective evidence already exists"):
        record_primary_turn_start_evidence(state=state)
    assert state.to_payload() == before

    state.primary_objective_turn_start_states.clear()
    state.primary_rules_unit_turn_start_snapshots = [position_snapshot]
    before = state.to_payload()
    with pytest.raises(GameLifecycleError, match="position evidence already exists"):
        record_primary_turn_start_evidence(state=state)
    assert state.to_payload() == before


def test_phase17n_turn_start_snapshot_round_trip_and_exact_identity_lookups() -> None:
    snapshot = _turn_start_snapshot()
    rules_membership = snapshot.membership_for_rules_unit("unit-a")
    component = rules_membership.component_membership_for_unit("unit-a")

    assert component.objective_marker_ids == ("objective-a",)
    assert snapshot.membership_for_component_unit("unit-a") is rules_membership
    assert snapshot.membership_for_unit_identity("unit-a") is rules_membership
    assert snapshot.component_membership_for_unit("unit-a") is component
    assert primary_rules_unit_turn_start_snapshots_from_payload([snapshot.to_payload()]) == [
        snapshot
    ]

    with pytest.raises(GameLifecycleError, match="no requested component"):
        rules_membership.component_membership_for_unit("unit-missing")
    with pytest.raises(GameLifecycleError, match="no membership for the requested rules unit"):
        snapshot.membership_for_rules_unit("unit-missing")
    with pytest.raises(
        GameLifecycleError, match="exactly one membership for the requested component"
    ):
        snapshot.membership_for_component_unit("unit-missing")
    with pytest.raises(
        GameLifecycleError, match="exactly one membership for the requested unit identity"
    ):
        snapshot.membership_for_unit_identity("unit-missing")


def test_phase17n_turn_start_lineage_lookup_requires_retained_identity() -> None:
    component_a = _turn_start_component("unit-a", "model-a")
    component_b = _turn_start_component("unit-b", "model-b")
    attached_membership = PrimaryRulesUnitTurnStartMembership(
        rules_unit_instance_id="attached-ab",
        component_memberships=(component_a, component_b),
    )
    attached_snapshot = _turn_start_snapshot(memberships=(attached_membership,))

    assert (
        primary_rules_unit_turn_start_membership_for_lineage(
            snapshot=attached_snapshot,
            rules_unit_instance_id="attached-ab",
            component_unit_instance_ids=("unit-a", "unit-b"),
        )
        is attached_membership
    )
    with pytest.raises(GameLifecycleError, match="component identity drift"):
        primary_rules_unit_turn_start_membership_for_lineage(
            snapshot=attached_snapshot,
            rules_unit_instance_id="attached-ab",
            component_unit_instance_ids=("unit-a",),
        )

    split_snapshot = _turn_start_snapshot(
        memberships=(
            PrimaryRulesUnitTurnStartMembership(
                rules_unit_instance_id="unit-a",
                component_memberships=(component_a,),
            ),
            PrimaryRulesUnitTurnStartMembership(
                rules_unit_instance_id="unit-b",
                component_memberships=(component_b,),
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="requires exactly one membership"):
        primary_rules_unit_turn_start_membership_for_lineage(
            snapshot=split_snapshot,
            rules_unit_instance_id="attached-ab",
            component_unit_instance_ids=("unit-a", "unit-b"),
        )

    with pytest.raises(GameLifecycleError, match="requires a snapshot"):
        primary_rules_unit_turn_start_membership_for_lineage(
            snapshot=cast(PrimaryRulesUnitTurnStartSnapshot, object()),
            rules_unit_instance_id="attached-ab",
            component_unit_instance_ids=("unit-a", "unit-b"),
        )
    with pytest.raises(GameLifecycleError, match="at least one component"):
        primary_rules_unit_turn_start_membership_for_lineage(
            snapshot=split_snapshot,
            rules_unit_instance_id="attached-ab",
            component_unit_instance_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="requires exactly one membership"):
        primary_rules_unit_turn_start_membership_for_lineage(
            snapshot=split_snapshot,
            rules_unit_instance_id="attached-ab",
            component_unit_instance_ids=("unit-a", "unit-missing"),
        )


def test_phase17n_created_units_receive_explicit_empty_historical_membership() -> None:
    snapshot = _turn_start_snapshot()
    updated = primary_rules_unit_turn_start_snapshots_with_created_unit(
        [snapshot],
        unit_instance_id="unit-created",
    )

    created = updated[0].membership_for_rules_unit("unit-created")
    assert created.component_memberships == (
        PrimaryComponentTurnStartMembership(
            unit_instance_id="unit-created",
            evaluated_model_instance_ids=(),
            logical_terrain_area_ids=(),
            objective_marker_witnesses=(),
        ),
    )

    with pytest.raises(GameLifecycleError, match="snapshots must be a list"):
        primary_rules_unit_turn_start_snapshots_with_created_unit(
            cast(list[PrimaryRulesUnitTurnStartSnapshot], (snapshot,)),
            unit_instance_id="unit-created",
        )
    with pytest.raises(GameLifecycleError, match="must contain snapshot values"):
        primary_rules_unit_turn_start_snapshots_with_created_unit(
            cast(list[PrimaryRulesUnitTurnStartSnapshot], [object()]),
            unit_instance_id="unit-created",
        )
    with pytest.raises(GameLifecycleError, match="already contains the created unit"):
        primary_rules_unit_turn_start_snapshots_with_created_unit(
            [snapshot],
            unit_instance_id="unit-a",
        )


def test_phase17n_turn_start_typed_collections_fail_closed() -> None:
    component = _turn_start_component("unit-a", "model-a")
    membership = PrimaryRulesUnitTurnStartMembership(
        rules_unit_instance_id="unit-a",
        component_memberships=(component,),
    )

    with pytest.raises(GameLifecycleError, match="model_instance_ids must be a tuple"):
        PrimaryObjectiveMarkerWitness(
            objective_marker_id="objective-a",
            model_instance_ids=cast(tuple[str, ...], ["model-a"]),
        )
    with pytest.raises(GameLifecycleError, match="objective_marker_witnesses must be a tuple"):
        PrimaryComponentTurnStartMembership(
            unit_instance_id="unit-a",
            evaluated_model_instance_ids=("model-a",),
            logical_terrain_area_ids=(),
            objective_marker_witnesses=cast(
                tuple[PrimaryObjectiveMarkerWitness, ...],
                [],
            ),
        )
    with pytest.raises(GameLifecycleError, match="must contain witnesses"):
        PrimaryComponentTurnStartMembership(
            unit_instance_id="unit-a",
            evaluated_model_instance_ids=("model-a",),
            logical_terrain_area_ids=(),
            objective_marker_witnesses=cast(
                tuple[PrimaryObjectiveMarkerWitness, ...],
                (object(),),
            ),
        )
    with pytest.raises(GameLifecycleError, match="component_memberships must be a tuple"):
        PrimaryRulesUnitTurnStartMembership(
            rules_unit_instance_id="unit-a",
            component_memberships=cast(
                tuple[PrimaryComponentTurnStartMembership, ...],
                [component],
            ),
        )
    with pytest.raises(GameLifecycleError, match="must contain memberships"):
        PrimaryRulesUnitTurnStartMembership(
            rules_unit_instance_id="unit-a",
            component_memberships=cast(
                tuple[PrimaryComponentTurnStartMembership, ...],
                (object(),),
            ),
        )
    with pytest.raises(GameLifecycleError, match="rules_unit_memberships must be a tuple"):
        _turn_start_snapshot(
            memberships=cast(
                tuple[PrimaryRulesUnitTurnStartMembership, ...],
                [membership],
            )
        )
    with pytest.raises(GameLifecycleError, match="must contain memberships"):
        _turn_start_snapshot(
            memberships=cast(
                tuple[PrimaryRulesUnitTurnStartMembership, ...],
                (object(),),
            )
        )
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        PrimaryObjectiveMarkerWitness.from_payload(None)


@pytest.mark.parametrize(
    ("known_models", "known_attached", "expected_error"),
    [
        ([], (), "Known component model records must be a tuple"),
        ((["unit-a", ("model-a",)],), (), "must contain pair tuples"),
        ((("unit-a",),), (), "must contain pair tuples"),
        (
            (("unit-a", ("model-a",)), ("unit-a", ("model-b",))),
            (),
            "Known component unit IDs must be unique",
        ),
        (
            (("unit-a", ("model-a",)), ("unit-b", ("model-a",))),
            (),
            "Known component model IDs must not overlap",
        ),
        (
            (("unit-a", ("model-a",)), ("unit-b", ("model-b",))),
            [],
            "Known attached rules-unit records must be a tuple",
        ),
        (
            (("unit-a", ("model-a",)), ("unit-b", ("model-b",))),
            (["attached-ab", ("unit-a", "unit-b")],),
            "must contain pair tuples",
        ),
        (
            (("unit-a", ("model-a",)), ("unit-b", ("model-b",))),
            (("attached-ab",),),
            "must contain pair tuples",
        ),
        (
            (("unit-a", ("model-a",)), ("unit-b", ("model-b",))),
            (("unit-a", ("unit-a", "unit-b")),),
            "identities must be unique and non-physical",
        ),
        (
            (("unit-a", ("model-a",)), ("unit-b", ("model-b",))),
            (("attached-a", ("unit-a",)),),
            "require at least two components",
        ),
        (
            (("unit-a", ("model-a",)), ("unit-b", ("model-b",))),
            (("attached-ab", ("unit-a", "unit-missing")),),
            "component is not a physical unit",
        ),
        (
            (
                ("unit-a", ("model-a",)),
                ("unit-b", ("model-b",)),
                ("unit-c", ("model-c",)),
            ),
            (
                ("attached-ab", ("unit-a", "unit-b")),
                ("attached-bc", ("unit-b", "unit-c")),
            ),
            "components must not overlap",
        ),
    ],
)
def test_phase17n_turn_start_known_identity_records_fail_closed(
    known_models: object,
    known_attached: object,
    expected_error: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=expected_error):
        _validate_turn_start_snapshots(
            [],
            known_models=known_models,
            known_attached=known_attached,
        )


def test_phase17n_turn_start_state_collections_require_typed_lists() -> None:
    with pytest.raises(GameLifecycleError, match="turn-start states must be a list"):
        validate_primary_objective_turn_start_states(
            (),
            game_id="game-a",
            player_ids=("player-a", "player-b"),
            known_objective_marker_ids=("objective-a",),
        )
    with pytest.raises(GameLifecycleError, match="must contain state values"):
        validate_primary_objective_turn_start_states(
            [object()],
            game_id="game-a",
            player_ids=("player-a", "player-b"),
            known_objective_marker_ids=("objective-a",),
        )
    with pytest.raises(GameLifecycleError, match="snapshots must be a list"):
        _validate_turn_start_snapshots(())
    with pytest.raises(GameLifecycleError, match="must contain snapshot values"):
        _validate_turn_start_snapshots([object()])


def test_phase17n_evidence_recorders_require_authoritative_game_state() -> None:
    invalid_state = cast(GameState, object())
    snapshot = _turn_start_snapshot()

    with pytest.raises(GameLifecycleError, match="tracking requires GameState"):
        record_primary_turn_start_evidence(state=invalid_state)
    with pytest.raises(GameLifecycleError, match="tracking requires GameState"):
        build_primary_rules_unit_turn_start_snapshot(state=invalid_state)
    with pytest.raises(GameLifecycleError, match="evidence requires GameState"):
        record_primary_rules_unit_turn_start_snapshot(
            state=invalid_state,
            snapshot=snapshot,
        )
    with pytest.raises(GameLifecycleError, match="tracking requires GameState"):
        record_primary_destroyed_model_departures(
            state=invalid_state,
            destroyed_model_instance_ids=("model-a",),
            source_id="source-a",
        )


def test_phase17n_primary_destruction_builder_requires_complete_battle_context() -> None:
    state, unit = _catalog_tracking_state()
    mission_setup = state.mission_setup
    battlefield = state.battlefield_state
    phase_index = state.battle_phase_index
    assert mission_setup is not None
    assert battlefield is not None
    assert phase_index is not None

    state.mission_setup = None
    with pytest.raises(GameLifecycleError, match="requires MissionSetup"):
        _build_tracking_destruction(state=state, unit=unit)
    state.mission_setup = mission_setup

    state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="requires an active player"):
        _build_tracking_destruction(state=state, unit=unit)
    state.active_player_id = "player-khorne"

    state.battle_phase_index = None
    with pytest.raises(GameLifecycleError, match="requires a battle phase"):
        _build_tracking_destruction(state=state, unit=unit)
    state.battle_phase_index = phase_index

    with pytest.raises(GameLifecycleError, match="requires typed destruction attribution"):
        _build_tracking_destruction(
            state=state,
            unit=unit,
            attribution=cast(ModelDestructionAttribution, object()),
        )
    outside_attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-outside",
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=None,
        source_model_instance_id=None,
    )
    with pytest.raises(GameLifecycleError, match="player_id is not in this game"):
        _build_tracking_destruction(
            state=state,
            unit=unit,
            attribution=outside_attribution,
        )

    state.battlefield_state = None
    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        _build_tracking_destruction(state=state, unit=unit)


def test_phase17n_destroyed_model_tracking_rejects_malformed_mutation_context() -> None:
    state, unit = _catalog_tracking_state()
    model_id = unit.own_models[0].model_instance_id
    mission_setup = state.mission_setup
    battlefield = state.battlefield_state
    assert mission_setup is not None
    assert battlefield is not None

    with pytest.raises(GameLifecycleError, match="tracking requires GameState"):
        _record_tracking_destruction_models(
            state=cast(GameState, object()),
            destroyed_model_instance_ids=(model_id,),
        )
    state.mission_setup = None
    assert (
        _record_tracking_destruction_models(
            state=state,
            destroyed_model_instance_ids=(model_id,),
        )
        == ()
    )
    state.mission_setup = mission_setup

    state.battlefield_state = None
    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        _record_tracking_destruction_models(
            state=state,
            destroyed_model_instance_ids=(model_id,),
        )
    state.battlefield_state = battlefield

    with pytest.raises(GameLifecycleError, match="flag must be bool"):
        _record_tracking_destruction_models(
            state=state,
            destroyed_model_instance_ids=(model_id,),
            left_battlefield=cast(bool, 1),
        )
    with pytest.raises(GameLifecycleError, match="requires typed destruction attribution"):
        _record_tracking_destruction_models(
            state=state,
            destroyed_model_instance_ids=(model_id,),
            attribution=cast(ModelDestructionAttribution, object()),
        )
    with pytest.raises(GameLifecycleError, match="references an unknown model"):
        _record_tracking_destruction_models(
            state=state,
            destroyed_model_instance_ids=("model-unknown",),
        )
    with pytest.raises(GameLifecycleError, match="requires a typed destroyed-unit witness"):
        _record_tracking_destruction_models(
            state=state,
            destroyed_model_instance_ids=(model_id,),
            destroyed_witness=cast(RulesUnitObjectiveProximityWitness, object()),
        )


def test_phase17n_destroyed_model_departure_inputs_fail_closed() -> None:
    state, unit = _catalog_tracking_state()
    model_id = unit.own_models[0].model_instance_id
    mission_setup = state.mission_setup
    battlefield = state.battlefield_state
    assert mission_setup is not None
    assert battlefield is not None

    state.mission_setup = None
    assert (
        record_primary_destroyed_model_departures(
            state=state,
            destroyed_model_instance_ids=(model_id,),
            source_id="source-departure",
        )
        == ()
    )
    state.mission_setup = mission_setup

    invalid_model_id_collections = (
        (cast(tuple[str, ...], [model_id]), "must be a tuple"),
        ((), "must not be empty"),
        ((model_id, model_id), "must not contain duplicates"),
    )
    for model_ids, expected_error in invalid_model_id_collections:
        with pytest.raises(GameLifecycleError, match=expected_error):
            record_primary_destroyed_model_departures(
                state=state,
                destroyed_model_instance_ids=model_ids,
                source_id="source-departure",
            )
    with pytest.raises(GameLifecycleError, match="references an unknown model"):
        record_primary_destroyed_model_departures(
            state=state,
            destroyed_model_instance_ids=("model-unknown",),
            source_id="source-departure",
        )

    state.battlefield_state = None
    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        record_primary_destroyed_model_departures(
            state=state,
            destroyed_model_instance_ids=(model_id,),
            source_id="source-departure",
        )
    state.battlefield_state = battlefield

    state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="requires active-player battle-phase state"):
        record_primary_destroyed_model_departures(
            state=state,
            destroyed_model_instance_ids=(model_id,),
            source_id="source-departure",
        )
    state.active_player_id = "player-khorne"

    invalid_departed_collections = (
        (cast(tuple[str, ...], [unit.unit_instance_id]), "must be a tuple"),
        (
            (unit.unit_instance_id, unit.unit_instance_id),
            "must not contain duplicates",
        ),
        (("unit-unaffected",), "must be affected by the occurrence"),
    )
    for departed_ids, expected_error in invalid_departed_collections:
        with pytest.raises(GameLifecycleError, match=expected_error):
            record_primary_destroyed_model_departures(
                state=state,
                destroyed_model_instance_ids=(model_id,),
                source_id="source-departure",
                fully_departed_component_unit_instance_ids=departed_ids,
            )

    with pytest.raises(GameLifecycleError, match="requires cleanup state"):
        record_primary_unit_destructions_for_end_turn_cleanup(
            state=state,
            cleanup=cast(EndTurnCleanupState, object()),
        )


def test_phase17n_unit_destruction_state_collection_identity_fails_closed() -> None:
    state = _unattributed_destruction_state()

    assert _validate_destruction_states([state]) == [state]
    with pytest.raises(GameLifecycleError, match="states must be a list"):
        _validate_destruction_states(())
    with pytest.raises(GameLifecycleError, match="must contain state values"):
        _validate_destruction_states([object()])
    with pytest.raises(GameLifecycleError, match="game_id drift"):
        _validate_destruction_states([replace(state, game_id="game-drift")])
    with pytest.raises(GameLifecycleError, match="player_id is not in this game"):
        _validate_destruction_states(
            [_attributed_destruction_state(destroying_player_id="player-outside")]
        )
    with pytest.raises(GameLifecycleError, match="unknown destroyed unit"):
        _validate_destruction_states([replace(state, destroyed_unit_instance_id="unit-unknown")])
    with pytest.raises(GameLifecycleError, match="destroyed player drift"):
        _validate_destruction_states(
            [state],
            owner_by_unit_id={"unit-destroyed": "player-a"},
        )
    with pytest.raises(GameLifecycleError, match="destruction_id drift"):
        _validate_destruction_states(
            [replace(state, destruction_id="primary-unit-destruction:forged")]
        )
    with pytest.raises(GameLifecycleError, match="states must be unique"):
        _validate_destruction_states([state, state])


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("unknown_rules_unit", "unknown rules unit"),
        ("component_drift", "component identity drift"),
        ("owner_drift", "must belong to the destroying player"),
        ("source_model_drift", "source model is not in the source rules unit"),
        ("unknown_objective", "unknown objective marker"),
        ("witness_model_drift", "model outside its rules unit"),
    ],
)
def test_phase17n_unit_destruction_source_witness_identity_fails_closed(
    corruption: str,
    expected_error: str,
) -> None:
    witness_component_id = "unit-source"
    witness_model_id = "model-source"
    known_components: dict[str, tuple[str, ...]] = {"rules-unit-source": ("unit-source",)}
    owner_by_unit_id: dict[str, str] = {"unit-source": "player-a"}
    model_ids_by_unit_id: dict[str, tuple[str, ...]] = {"unit-source": ("model-source",)}
    known_objectives: tuple[str, ...] = ("objective-a",)
    if corruption == "unknown_rules_unit":
        known_components = {}
    elif corruption == "component_drift":
        witness_component_id = "unit-other"
    elif corruption == "owner_drift":
        owner_by_unit_id = {"unit-source": "player-b"}
    elif corruption == "source_model_drift":
        model_ids_by_unit_id = {"unit-source": ("model-other",)}
    elif corruption == "unknown_objective":
        known_objectives = ()
    elif corruption == "witness_model_drift":
        witness_model_id = "model-outside"
    else:
        raise AssertionError(f"unsupported witness corruption: {corruption}")
    state = _attributed_destruction_state(
        witness_component_id=witness_component_id,
        witness_model_id=witness_model_id,
    )

    with pytest.raises(GameLifecycleError, match=expected_error):
        validate_primary_unit_destruction_source_witness_identity(
            state,
            owner_by_unit_id=owner_by_unit_id,
            model_ids_by_unit_id=model_ids_by_unit_id,
            known_rules_unit_components_by_id=known_components,
            known_objective_marker_ids=known_objectives,
        )


def test_phase17n_unit_destruction_requires_known_turn_start_lineage() -> None:
    state = _unattributed_destruction_state()
    with pytest.raises(GameLifecycleError, match="no known rules-unit lineage"):
        validate_primary_unit_destruction_turn_start_evidence(
            destruction_states=[state],
            position_snapshots=[_turn_start_snapshot()],
            known_rules_unit_components_by_id={},
        )


__all__: list[str] = []
__all__ += ["BattlefieldRuntimeState", "EventLog", "GameLifecycleStage", "MissionScoringPolicy"]
__all__ += ["MissionSetup", "ModelPlacement", "ObjectiveMarkerModelWitness", "Pose"]
__all__ += ["PrimaryMissionDefinition", "PrimaryMissionProgressState"]
__all__ += ["PrimaryScoringBoundaryKind", "PrimaryScoringResolutionCandidate"]
__all__ += ["PrimaryScoringStateEvidence", "PrimaryUnattributedDestructionCause"]
__all__ += ["PrimaryUnitDestructionState", "RulesetDescriptor"]
__all__ += ["SUPPORTED_PRIMARY_SCORING_TIMINGS", "UnitInstance", "_deadly_demise_attribution"]
__all__ += ["_evidence_model_placement", "_minimal_evidence_game_state"]
__all__ += ["_source_objective_witness", "attached_selected_to_fight_risk_fixture"]
__all__ += ["battle_state_with_army", "bloodcrushers_army", "bloodcrushers_battlefield_state"]
__all__ += ["bloodcrushers_package", "bloodcrushers_unit", "build_primary_unit_destruction_state"]
__all__ += ["chapter_approved_2026_27_mission_pack"]
__all__ += ["destruction_source_objective_proximity_witness", "objective_control_record_hash"]
__all__ += ["primary_scoring_timing_applies", "primary_unit_destruction_id"]
__all__ += ["record_primary_unit_destructions_for_destroyed_models"]
__all__ += ["rules_unit_objective_proximity_witness"]
__all__ += ["validate_primary_rules_unit_turn_start_snapshots"]
__all__ += ["validate_primary_unit_destruction_states"]
