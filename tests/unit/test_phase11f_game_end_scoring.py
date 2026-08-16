from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.setup_completion_helpers import enter_battle_for_fixture

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.final_scoring import (
    FinalScoreLine,
    FinalScoringResult,
    FinalScoringResultPayload,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    GameStatePayload,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import (
    MissionSetup,
)
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    build_primary_scoring_state_evidence,
    record_primary_scoring_state_evidence,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    record_primary_turn_start_evidence,
)
from warhammer40k_core.engine.scoring import (
    VictoryPointAward,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)
from warhammer40k_core.engine.scoring_cap_audit import metadata_with_vp_cap_audit
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    chapter_approved_2026_27_mission_pack,
    warhammer_event_companion_2026_07_mission_pack,
)

PHASE16A_MISSION_POOL_ENTRY_ID = "mission-take-and-hold-vs-purge-the-foe-layout-3"


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
            metadata={"scoring_rule_id": "phase11f-secondary-cap"},
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
            metadata={"scoring_rule_id": "phase11f-opponent-secondary-cap"},
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
            metadata={"scoring_rule_id": "phase11f-secondary-action-base"},
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


def _immovable_object_primary_award_fixture() -> tuple[GameState, VictoryPointAward]:
    state = _battle_state()
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise AssertionError("Immovable Object award fixture requires MissionSetup.")
    policy = mission_scoring_policies_from_setup(mission_setup).policy_for_player("player-a")
    state.battle_round = 2
    battlefield = state.battlefield_state
    if battlefield is None:
        raise AssertionError("Immovable Object award fixture requires battlefield state.")
    controlled_marker = mission_setup.objective_markers[0]
    player_a_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
    )
    placement = battlefield.unit_placement_by_id(player_a_unit.unit_instance_id)
    offsets = ((0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (0.0, 1.0), (1.0, 1.0))
    state.battlefield_state = battlefield.with_unit_placement(
        replace(
            placement,
            model_placements=tuple(
                replace(
                    model_placement,
                    pose=Pose.at(
                        controlled_marker.x_inches + x_offset,
                        controlled_marker.y_inches + y_offset,
                        model_placement.pose.position.z,
                        facing_degrees=model_placement.pose.facing.degrees,
                    ),
                )
                for model_placement, (x_offset, y_offset) in zip(
                    placement.model_placements,
                    offsets,
                    strict=True,
                )
            ),
        )
    )
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.COMMAND,
        timing=ObjectiveControlTiming.PHASE_END,
        runtime_modifier_registry=None,
    )
    state_evidence = build_primary_scoring_state_evidence(
        state=state,
        record=record,
        end_of_battle=False,
    )
    awards = policy.primary_awards_from_objective_control(
        record=record,
        mission_setup=mission_setup,
        turn_order=state.turn_order,
        turn_start_states=tuple(state.primary_objective_turn_start_states),
        terrain_trap_states=tuple(state.primary_terrain_trap_states),
        unit_destruction_states=tuple(state.primary_unit_destruction_states),
        state_evidence=state_evidence,
    )
    if len(awards) != 1 or awards[0].amount != 5:
        raise AssertionError("Immovable Object fixture requires one 5VP Primary award.")
    metadata = awards[0].metadata
    if not isinstance(metadata, dict) or metadata.get("score_count") != 1:
        raise AssertionError("Immovable Object fixture requires score_count 1 evidence.")
    record_primary_scoring_state_evidence(state=state, evidence=state_evidence)
    return state, awards[0]


def _assert_final_payload_rejected(payload: dict[str, object], message: str) -> None:
    with pytest.raises(GameLifecycleError, match=message):
        FinalScoringResult.from_payload(cast(FinalScoringResultPayload, payload))


def _cap_reasons(transaction: VictoryPointTransaction) -> list[str]:
    payload = transaction.metadata
    assert isinstance(payload, dict)
    audit = payload["vp_cap_audit"]
    assert isinstance(audit, dict)
    reasons = audit["capped_reasons"]
    assert isinstance(reasons, list)
    return [str(reason) for reason in reasons]


def _set_round_five_going_second_fight(state: GameState) -> None:
    state.battle_round = 5
    state.active_player_id = "player-b"
    record_primary_turn_start_evidence(state=state)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)


def _battle_state(
    *,
    mission_pool_entry_id: str = PHASE16A_MISSION_POOL_ENTRY_ID,
    mission_setup: MissionSetup | None = None,
) -> GameState:
    config = _config(
        mission_pool_entry_id=mission_pool_entry_id,
        mission_setup=mission_setup,
    )
    state = GameState.from_config(config)
    assert config.mission_setup is not None
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11f-battlefield",
        armies=tuple(state.army_definitions),
        battlefield_width_inches=config.mission_setup.battlefield_width_inches,
        battlefield_depth_inches=config.mission_setup.battlefield_depth_inches,
        terrain_features=config.mission_setup.terrain_features,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(
            player_id="player-a",
            mode=SecondaryMissionMode.FIXED,
            fixed_mission_ids=("assassination", "bring-it-down"),
        )
    )
    state.record_secondary_mission_choice(
        SecondaryMissionChoice(
            player_id="player-b",
            mode=SecondaryMissionMode.FIXED,
            fixed_mission_ids=("assassination", "bring-it-down"),
        )
    )
    enter_battle_for_fixture(state)
    assert state.stage is GameLifecycleStage.BATTLE
    return GameState.from_payload(state.to_payload())


def _config(
    *,
    mission_pool_entry_id: str = PHASE16A_MISSION_POOL_ENTRY_ID,
    mission_setup: MissionSetup | None = None,
) -> GameConfig:
    source_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        source_catalog,
        detachments=tuple(
            replace(
                detachment,
                force_disposition_ids=("disruption", "purge-the-foe", "take-and-hold"),
            )
            if detachment.detachment_id == "core-combined-arms"
            else detachment
            for detachment in source_catalog.detachments
        ),
    )
    resolved_mission_setup = (
        MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id=mission_pool_entry_id,
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            attacker_force_disposition_id="take-and-hold",
            defender_player_id="player-b",
            defender_force_disposition_id="purge-the-foe",
        )
        if mission_setup is None
        else mission_setup
    )
    return GameConfig(
        game_id="phase11f-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1",),
                force_disposition_id=resolved_mission_setup.force_disposition_id_for_player(
                    "player-a"
                ),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
                force_disposition_id=resolved_mission_setup.force_disposition_id_for_player(
                    "player-b"
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=resolved_mission_setup,
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
        descriptor_version="core-v2-phase11f-test"
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
    force_disposition_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id=force_disposition_id,
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _event_death_trap_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-disruption-layout-1",
        terrain_layout_id="take-and-hold-vs-disruption-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="disruption",
        defender_player_id="player-b",
        defender_force_disposition_id="take-and-hold",
    )
