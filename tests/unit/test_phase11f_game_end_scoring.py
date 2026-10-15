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


def test_phase11f_mission_action_cap_accounting_is_source_aware() -> None:
    state = _battle_state(mission_setup=_event_death_trap_setup())
    assert state.mission_setup is not None
    policy = mission_scoring_policies_from_setup(state.mission_setup).policy_for_player("player-a")
    for battle_round, amount in ((1, 15), (2, 15), (3, 14)):
        state.battle_round = battle_round
        state.award_victory_points(
            policy.mission_action_award(
                player_id="player-a",
                battle_round=battle_round,
                phase=BattlePhase.COMMAND.value,
                action_id=f"phase11f:death-trap-base:round-{battle_round}",
                source_id="primary-death-trap",
                amount=amount,
            )
        )
    state.battle_round = 4
    state.award_victory_points(
        VictoryPointAward(
            player_id="player-a",
            battle_round=4,
            phase=BattlePhase.COMMAND.value,
            amount=44,
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            source_id="cleanse",
            scoring_timing="secondary_mission_score",
            metadata={
                "secondary_scoring_provider_kind": (
                    SecondaryScoringProviderKind.LEGACY_PHASE11F.value
                ),
                "scoring_rule_id": "phase11f-secondary-action-base",
            },
        )
    )

    death_trap_transaction = state.award_victory_points(
        policy.mission_action_award(
            player_id="player-a",
            battle_round=4,
            phase=BattlePhase.SHOOTING.value,
            action_id="death-trap:center:player-a",
            source_id="primary-death-trap",
            amount=5,
        )
    )
    cleanse_transaction = state.award_victory_points(
        policy.mission_action_award(
            player_id="player-a",
            battle_round=4,
            phase=BattlePhase.SHOOTING.value,
            action_id="cleanse:center:player-a",
            source_id="cleanse",
            amount=5,
        )
    )
    player_a_score = FinalScoreLine.from_ledger(
        ledger=state.victory_point_ledger_for_player("player-a"),
        policy=policy,
    ).to_payload()

    assert death_trap_transaction.amount == 1
    assert cleanse_transaction.amount == 1
    assert _cap_reasons(death_trap_transaction) == ["primary_vp_cap"]
    assert _cap_reasons(cleanse_transaction) == ["secondary_vp_cap"]
    assert player_a_score["raw_primary_vp"] == 45
    assert player_a_score["raw_secondary_vp"] == 45
    assert player_a_score["capped_primary_vp"] == 45
    assert player_a_score["capped_secondary_vp"] == 45
    assert (
        state.victory_point_ledger_for_player("player-a").points_from_source_kind(
            VictoryPointSourceKind.MISSION_ACTION
        )
        == 46
    )
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()

    forged_uncapped_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    forged_uncapped_ledger = next(
        ledger
        for ledger in forged_uncapped_payload["victory_point_ledgers"]
        if ledger["player_id"] == "player-a"
    )
    forged_uncapped_transaction = next(
        transaction
        for transaction in forged_uncapped_ledger["transactions"]
        if transaction["source_kind"] == "mission_action"
        and isinstance(transaction["metadata"], dict)
        and "vp_cap_audit" not in transaction["metadata"]
    )
    forged_uncapped_metadata = cast(
        dict[str, JsonValue],
        forged_uncapped_transaction["metadata"],
    )
    forged_uncapped_metadata["vp_cap_audit"] = {
        "requested_amount": forged_uncapped_transaction["amount"],
        "applied_amount": forged_uncapped_transaction["amount"],
        "source_cap": 999,
        "source_points_before": 777,
        "source_points_after": 1,
        "total_cap": 1,
        "total_points_before": 999,
        "total_points_after": 0,
        "capped_reasons": ["forged_reason"],
    }
    with pytest.raises(
        GameLifecycleError,
        match="cap audit drifted from chronological ledger policy",
    ):
        GameState.from_payload(forged_uncapped_payload)

    tampered_capped_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    tampered_capped_ledger = next(
        ledger
        for ledger in tampered_capped_payload["victory_point_ledgers"]
        if ledger["player_id"] == "player-a"
    )
    tampered_capped_transaction = next(
        transaction
        for transaction in tampered_capped_ledger["transactions"]
        if transaction["source_kind"] == "mission_action"
        and transaction["source_id"] == "primary-death-trap"
        and isinstance(transaction["metadata"], dict)
        and "vp_cap_audit" in transaction["metadata"]
    )
    tampered_capped_metadata = cast(
        dict[str, JsonValue],
        tampered_capped_transaction["metadata"],
    )
    tampered_capped_audit = cast(
        dict[str, JsonValue],
        tampered_capped_metadata["vp_cap_audit"],
    )
    tampered_capped_audit["source_points_before"] = 999
    with pytest.raises(
        GameLifecycleError,
        match="cap audit drifted from chronological ledger policy",
    ):
        GameState.from_payload(tampered_capped_payload)


def test_phase11f_scoring_policy_rejects_source_geometry_drift() -> None:
    state = _battle_state()
    assert state.mission_setup is not None
    policies = mission_scoring_policies_from_setup(state.mission_setup)
    first_marker = state.mission_setup.objective_markers[0]
    drifted_setup = replace(
        state.mission_setup,
        objective_markers=(
            replace(first_marker, x_inches=first_marker.x_inches + 0.25),
            *state.mission_setup.objective_markers[1:],
        ),
    )

    with pytest.raises(GameLifecycleError, match="canonical layoutless setup drifted from source"):
        policies.validate_mission_setup(drifted_setup)


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyDefinition", "ArmyMusterRequest", "DetachmentSelection"]
__all__ += ["FinalScoringResult", "FinalScoringResultPayload", "GameConfig", "GameLifecycleStage"]
__all__ += ["MissionSetup", "ModelProfileSelection", "ObjectiveControlTiming"]
__all__ += ["PHASE16A_MISSION_POOL_ENTRY_ID", "Pose", "RulesetDescriptor"]
__all__ += ["SecondaryMissionChoice", "SecondaryMissionMode", "UnitMusterSelection"]
__all__ += ["VictoryPointTransaction", "_army_muster_request", "_assert_final_payload_rejected"]
__all__ += ["_config", "_immovable_object_primary_award_fixture", "_mustered_armies", "_ruleset"]
__all__ += ["_set_round_five_going_second_fight", "build_primary_scoring_state_evidence"]
__all__ += ["chapter_approved_2026_27_mission_pack", "create_deterministic_battlefield_scenario"]
__all__ += ["enter_battle_for_fixture", "metadata_with_vp_cap_audit", "muster_army"]
__all__ += ["record_primary_scoring_state_evidence", "record_primary_turn_start_evidence"]
__all__ += ["resolve_primary_scoring_boundary_lifecycle"]
__all__ += ["warhammer_event_companion_2026_07_mission_pack"]
