from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase11f_game_end_scoring import (
    PHASE16A_MISSION_POOL_ENTRY_ID,
    ArmyCatalog,
    ArmyDefinition,
    ArmyMusterRequest,
    BattlePhase,
    DetachmentSelection,
    FinalScoreLine,
    FinalScoringResult,
    FinalScoringResultPayload,
    GameConfig,
    GameLifecycleError,
    GameLifecycleStage,
    GameState,
    GameStatePayload,
    JsonValue,
    MissionSetup,
    ModelProfileSelection,
    ObjectiveControlTiming,
    Pose,
    RulesetDescriptor,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    SecondaryScoringProviderKind,
    UnitMusterSelection,
    VictoryPointAward,
    VictoryPointSourceKind,
    VictoryPointTransaction,
    _army_muster_request,
    _assert_final_payload_rejected,
    _battle_state,
    _cap_reasons,
    _config,
    _event_death_trap_setup,
    _immovable_object_primary_award_fixture,
    _mustered_armies,
    _ruleset,
    _set_round_five_going_second_fight,
    build_primary_scoring_state_evidence,
    chapter_approved_2026_27_mission_pack,
    create_deterministic_battlefield_scenario,
    enter_battle_for_fixture,
    json,
    metadata_with_vp_cap_audit,
    mission_scoring_policies_from_setup,
    muster_army,
    pytest,
    record_primary_scoring_state_evidence,
    record_primary_turn_start_evidence,
    replace,
    resolve_primary_scoring_boundary_lifecycle,
    warhammer_event_companion_2026_07_mission_pack,
)


def test_phase11f_final_scoring_requires_the_owning_player_policy() -> None:
    state = _battle_state()
    assert state.mission_setup is not None
    policies = mission_scoring_policies_from_setup(state.mission_setup)
    player_b_ledger = state.victory_point_ledger_for_player("player-b")

    with pytest.raises(GameLifecycleError, match="ledger and MissionScoringPolicy players"):
        FinalScoreLine.from_ledger(
            ledger=player_b_ledger,
            policy=policies.policy_for_player("player-a"),
        )


def test_phase11f_game_end_windows_fire_once_and_final_payload_round_trips() -> None:
    state = _battle_state()
    _set_round_five_going_second_fight(state)

    completed_phase = state.advance_to_next_battle_phase()
    first_payload = state.game_result_payload()
    second_payload = state.game_result_payload()
    encoded = json.dumps(first_payload, sort_keys=True)
    decoded = cast(FinalScoringResultPayload, json.loads(encoded))
    round_tripped = FinalScoringResult.from_payload(decoded).to_payload()
    audit = cast(dict[str, object], first_payload["scoring_audit"])
    windows = cast(list[dict[str, object]], audit["scoring_windows"])

    assert completed_phase is BattlePhase.FIGHT
    assert state.stage is GameLifecycleStage.COMPLETE
    assert state.current_battle_phase is None
    assert first_payload == second_payload
    assert round_tripped == decoded
    assert first_payload["game_length_battle_rounds"] == 5
    assert first_payload["primary_mission_assignments"] == [
        {
            "player_id": "player-a",
            "force_disposition_id": "take-and-hold",
            "primary_mission_id": "primary-immovable-object",
        },
        {
            "player_id": "player-b",
            "force_disposition_id": "purge-the-foe",
            "primary_mission_id": "primary-unstoppable-force",
        },
    ]
    assert first_payload["winner_player_ids"] == ["player-a", "player-b"]
    assert first_payload["is_draw"] is True
    assert {(window["window_kind"], window["window"]) for window in windows} == {
        ("end_of_round", "battle_round_end"),
        ("end_of_game", "turn_end_round_five_going_second"),
        ("end_of_game", "end_of_battle"),
    }
    assert len(state.scoring_window_states) == 3
    assert "<" not in encoded
    assert "object at 0x" not in encoded


def test_phase11f_vp_caps_are_enforced_before_winner_determination() -> None:
    state = _battle_state(mission_setup=_event_death_trap_setup())
    assert state.mission_setup is not None
    policies = mission_scoring_policies_from_setup(state.mission_setup)
    for battle_round in (1, 2, 3):
        state.battle_round = battle_round
        state.award_victory_points(
            policies.mission_action_award(
                player_id="player-a",
                battle_round=battle_round,
                phase=BattlePhase.COMMAND.value,
                action_id=f"phase11f:player-a:death-trap:round-{battle_round}",
                source_id="primary-death-trap",
                amount=15,
            )
        )
    state.battle_round = 4
    primary_cap_transaction = state.award_victory_points(
        policies.mission_action_award(
            player_id="player-a",
            battle_round=4,
            phase=BattlePhase.COMMAND.value,
            action_id="phase11f:player-a:death-trap:cap-probe",
            source_id="primary-death-trap",
            amount=15,
        )
    )
    secondary_transaction = state.award_victory_points(
        VictoryPointAward(
            player_id="player-a",
            battle_round=4,
            phase=BattlePhase.COMMAND.value,
            amount=46,
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            source_id="assassination",
            scoring_timing="secondary_mission_score",
            metadata={
                "secondary_scoring_provider_kind": (
                    SecondaryScoringProviderKind.LEGACY_PHASE11F.value
                ),
                "scoring_rule_id": "phase11f-secondary-cap",
            },
        )
    )
    battle_ready_transaction = state.award_victory_points(
        VictoryPointAward(
            player_id="player-a",
            battle_round=4,
            phase=BattlePhase.COMMAND.value,
            amount=15,
            source_kind=VictoryPointSourceKind.BATTLE_READY,
            source_id="battle-ready",
            scoring_timing="game_end",
            metadata={"scoring_rule_id": "phase11f-battle-ready-cap"},
        )
    )
    state.award_victory_points(
        VictoryPointAward(
            player_id="player-b",
            battle_round=4,
            phase=BattlePhase.COMMAND.value,
            amount=60,
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            source_id="assassination",
            scoring_timing="secondary_mission_score",
            metadata={
                "secondary_scoring_provider_kind": (
                    SecondaryScoringProviderKind.LEGACY_PHASE11F.value
                ),
                "scoring_rule_id": "phase11f-opponent-secondary-cap",
            },
        )
    )
    _set_round_five_going_second_fight(state)

    state.advance_to_next_battle_phase()
    result = state.game_result_payload()
    audit = cast(dict[str, object], result["scoring_audit"])
    player_scores = cast(list[dict[str, object]], audit["player_scores"])
    player_a_score = next(score for score in player_scores if score["player_id"] == "player-a")
    player_b_score = next(score for score in player_scores if score["player_id"] == "player-b")

    assert primary_cap_transaction.amount == 0
    assert secondary_transaction.amount == 45
    assert battle_ready_transaction.amount == 10
    assert state.victory_point_total("player-a") == 100
    assert state.victory_point_total("player-b") == 45
    assert result["final_scores"] == [
        {"player_id": "player-a", "victory_points": 100},
        {"player_id": "player-b", "victory_points": 45},
    ]
    assert result["winner_player_ids"] == ["player-a"]
    assert result["is_draw"] is False
    assert player_a_score["raw_victory_points"] == 100
    assert player_a_score["cap_adjustment"] == 0
    assert player_b_score["raw_secondary_vp"] == 45
    assert _cap_reasons(primary_cap_transaction) == ["primary_vp_cap"]
    assert _cap_reasons(secondary_transaction) == ["secondary_vp_cap"]
    assert _cap_reasons(battle_ready_transaction) == ["battle_ready_vp_cap", "total_vp_cap"]


def test_phase11f_vp_cap_audit_metadata_shapes_and_validation_are_explicit() -> None:
    def audit(
        metadata: object,
        *,
        requested_amount: int = 5,
        applied_amount: int = 3,
        capped_reasons: tuple[str, ...] = ("primary_battle_round_vp_cap",),
    ) -> object:
        return metadata_with_vp_cap_audit(
            cast(JsonValue, metadata),
            requested_amount=requested_amount,
            applied_amount=applied_amount,
            source_cap=10,
            source_points_before=7,
            source_points_after=10,
            total_cap=100,
            total_points_before=20,
            total_points_after=23,
            capped_reasons=capped_reasons,
        )

    empty_metadata = audit(None)
    scalar_metadata = cast(dict[str, object], audit("source-audit"))

    assert empty_metadata == {
        "vp_cap_audit": {
            "requested_amount": 5,
            "applied_amount": 3,
            "source_cap": 10,
            "source_points_before": 7,
            "source_points_after": 10,
            "total_cap": 100,
            "total_points_before": 20,
            "total_points_after": 23,
            "capped_reasons": ["primary_battle_round_vp_cap"],
        }
    }
    assert scalar_metadata["original_metadata"] == "source-audit"
    with pytest.raises(GameLifecycleError, match="already contains vp_cap_audit"):
        audit({"vp_cap_audit": {}})
    with pytest.raises(GameLifecycleError, match="requested_amount must be a positive integer"):
        audit(None, requested_amount=0)
    with pytest.raises(GameLifecycleError, match="applied_amount must be a non-negative integer"):
        audit(None, applied_amount=-1)
    with pytest.raises(GameLifecycleError, match="capped_reasons must be a non-empty tuple"):
        audit(None, capped_reasons=())
    with pytest.raises(GameLifecycleError, match="capped_reasons must not contain duplicates"):
        audit(None, capped_reasons=("total_vp_cap", "total_vp_cap"))


def test_phase11f_final_result_requires_policy_scoring_windows() -> None:
    state = _battle_state()
    _set_round_five_going_second_fight(state)

    state.advance_to_next_battle_phase()
    state.scoring_window_states = [
        window for window in state.scoring_window_states if window.window != "end_of_battle"
    ]

    with pytest.raises(GameLifecycleError, match="Final scoring requires recorded policy windows"):
        state.game_result_payload()


def test_phase11f_primary_vp_rejects_opponent_and_forged_source_ids() -> None:
    state = _battle_state()
    assert state.mission_setup is not None
    opponent_primary = state.mission_setup.primary_mission_id_for_player("player-b")

    for source_id in (opponent_primary, "primary-forged-source"):
        with pytest.raises(
            GameLifecycleError,
            match="Primary VP source does not match the player's assigned Primary mission",
        ):
            state.award_victory_points(
                VictoryPointAward(
                    player_id="player-a",
                    battle_round=1,
                    phase=BattlePhase.COMMAND.value,
                    amount=5,
                    source_kind=VictoryPointSourceKind.PRIMARY,
                    source_id=source_id,
                    scoring_timing="phase_end",
                )
            )


@pytest.mark.parametrize("source_kind", ["opponent", "forged"])
def test_phase11f_state_restore_rejects_primary_ledger_source_drift(
    source_kind: str,
) -> None:
    state, award = _immovable_object_primary_award_fixture()
    assert state.mission_setup is not None
    opponent_primary = state.mission_setup.primary_mission_id_for_player("player-b")
    state.award_victory_points(award)
    payload = state.to_payload()
    player_a_ledger = next(
        ledger for ledger in payload["victory_point_ledgers"] if ledger["player_id"] == "player-a"
    )
    player_a_ledger["transactions"][0]["source_id"] = (
        opponent_primary if source_kind == "opponent" else "primary-forged-source"
    )

    with pytest.raises(
        GameLifecycleError,
        match="Primary VP source does not match the player's assigned Primary mission",
    ):
        GameState.from_payload(payload)


def test_phase11f_state_restore_revalidates_primary_score_count_semantics() -> None:
    state, award = _immovable_object_primary_award_fixture()
    transaction = state.award_victory_points(award)
    assert transaction.amount == 5
    assert state.victory_point_total("player-a") == 5
    evidence = state.primary_scoring_state_evidence_records[-1]
    record = next(
        stored
        for stored in state.objective_control_records
        if stored.record_id == evidence.objective_control_record_id
    )
    resolve_primary_scoring_boundary_lifecycle(
        scoring_player_id=record.active_player_id,
        state=state,
        record=record,
        scoring_boundary_kind=evidence.scoring_boundary_kind,
        scoring_commit_checkpoint_id=evidence.scoring_commit_checkpoint_id,
        scoring_commit_checkpoint_hash=evidence.scoring_commit_checkpoint_hash,
        evidence_id=evidence.evidence_id,
    )

    payload = state.to_payload()
    player_a_ledger = next(
        ledger for ledger in payload["victory_point_ledgers"] if ledger["player_id"] == "player-a"
    )
    transaction_payload = player_a_ledger["transactions"][0]
    metadata = cast(dict[str, object], transaction_payload["metadata"])
    assert metadata["score_count"] == 1
    assert "vp_cap_audit" not in metadata
    metadata["score_count"] = 2
    transaction_payload["amount"] = 10
    player_a_ledger["victory_points"] = 10

    with pytest.raises(GameLifecycleError, match="Primary VP"):
        GameState.from_payload(payload)


def test_phase11f_live_primary_award_revalidates_score_count_semantics() -> None:
    state, award = _immovable_object_primary_award_fixture()
    forged_metadata = dict(cast(dict[str, JsonValue], award.metadata))
    assert forged_metadata["score_count"] == 1
    forged_metadata["score_count"] = 2
    forged_award = replace(award, amount=10, metadata=forged_metadata)

    with pytest.raises(GameLifecycleError, match="Primary VP"):
        state.award_victory_points(forged_award)
    assert state.victory_point_total("player-a") == 0


def test_phase11f_final_result_payload_rejects_policy_and_score_tampering() -> None:
    state = _battle_state()
    _set_round_five_going_second_fight(state)
    state.advance_to_next_battle_phase()
    baseline = state.game_result_payload()

    def payload_copy() -> dict[str, object]:
        return cast(dict[str, object], json.loads(json.dumps(baseline, sort_keys=True)))

    result_id_drift = payload_copy()
    result_id_drift["result_id"] = "forged-final-result"
    _assert_final_payload_rejected(result_id_drift, "result_id drifted")

    policy_drift = payload_copy()
    cast(dict[str, object], policy_drift["scoring_audit"])["policy_source_id"] = "forged-policy"
    _assert_final_payload_rejected(policy_drift, "policy_source_id drifted")

    missing_windows = payload_copy()
    cast(dict[str, object], missing_windows["scoring_audit"])["scoring_windows"] = []
    _assert_final_payload_rejected(missing_windows, "recorded policy windows exactly")

    extra_windows = payload_copy()
    extra_audit = cast(dict[str, object], extra_windows["scoring_audit"])
    extra_window_rows = cast(list[dict[str, object]], extra_audit["scoring_windows"])
    extra_window_rows.append(
        {
            "window_id": "scoring-window:phase11f-game:round-05:end_of_round:forged",
            "game_id": "phase11f-game",
            "battle_round": 5,
            "window_kind": "end_of_round",
            "window": "forged",
            "source_id": f"{extra_audit['policy_source_id']}:window:end_of_round:forged",
        }
    )
    _assert_final_payload_rejected(extra_windows, "recorded policy windows exactly")

    raw_total_drift = payload_copy()
    raw_total_score = cast(
        list[dict[str, object]],
        cast(dict[str, object], raw_total_drift["scoring_audit"])["player_scores"],
    )[0]
    raw_total_score["raw_victory_points"] = 10
    raw_total_score["cap_adjustment"] = 10
    _assert_final_payload_rejected(raw_total_drift, "raw_victory_points must match raw totals")

    capped_downward = payload_copy()
    downward_audit = cast(dict[str, object], capped_downward["scoring_audit"])
    downward_score = cast(list[dict[str, object]], downward_audit["player_scores"])[0]
    downward_score.update(
        {
            "raw_victory_points": 10,
            "raw_primary_vp": 10,
            "victory_points": 1,
            "capped_primary_vp": 1,
            "cap_adjustment": 9,
        }
    )
    cast(list[dict[str, object]], capped_downward["final_scores"])[0]["victory_points"] = 1
    capped_downward["winner_player_ids"] = ["player-a"]
    capped_downward["is_draw"] = False
    _assert_final_payload_rejected(capped_downward, "cap transform drifted")

    assignment_drift = payload_copy()
    assignments = cast(list[dict[str, object]], assignment_drift["primary_mission_assignments"])
    assignments[0]["primary_mission_id"] = assignments[1]["primary_mission_id"]
    _assert_final_payload_rejected(assignment_drift, "directional matrix")


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyDefinition", "ArmyMusterRequest", "DetachmentSelection"]
__all__ += ["GameConfig", "GameStatePayload", "MissionSetup", "ModelProfileSelection"]
__all__ += ["PHASE16A_MISSION_POOL_ENTRY_ID", "ObjectiveControlTiming", "Pose"]
__all__ += ["RulesetDescriptor", "SecondaryMissionChoice", "SecondaryMissionMode"]
__all__ += ["UnitMusterSelection", "VictoryPointTransaction", "_army_muster_request", "_config"]
__all__ += ["_mustered_armies", "_ruleset", "build_primary_scoring_state_evidence"]
__all__ += ["chapter_approved_2026_27_mission_pack", "create_deterministic_battlefield_scenario"]
__all__ += ["enter_battle_for_fixture", "muster_army", "record_primary_scoring_state_evidence"]
__all__ += ["record_primary_turn_start_evidence"]
__all__ += ["warhammer_event_companion_2026_07_mission_pack"]
