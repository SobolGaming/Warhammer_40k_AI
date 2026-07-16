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
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import mission_scoring_policy_from_setup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.scoring import (
    FinalScoringResult,
    FinalScoringResultPayload,
    VictoryPointAward,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)
from warhammer40k_core.engine.scoring_cap_audit import metadata_with_vp_cap_audit
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack

PHASE16A_MISSION_POOL_ENTRY_ID = "mission-take-and-hold-vs-purge-the-foe-layout-3"


def test_phase11f_game_end_windows_fire_once_and_final_payload_round_trips() -> None:
    state = _battle_state()
    state.battle_round = 5
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)

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
    state = _battle_state()
    primary_transaction = state.award_victory_points(
        VictoryPointAward(
            player_id="player-a",
            battle_round=1,
            phase=BattlePhase.COMMAND.value,
            amount=60,
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id="take-and-hold",
            scoring_timing="end_of_battle",
            metadata={"scoring_rule_id": "phase11f-primary-cap"},
        )
    )
    secondary_transaction = state.award_victory_points(
        VictoryPointAward(
            player_id="player-a",
            battle_round=1,
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
            battle_round=1,
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
            battle_round=1,
            phase=BattlePhase.COMMAND.value,
            amount=60,
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id="take-and-hold",
            scoring_timing="end_of_battle",
            metadata={"scoring_rule_id": "phase11f-opponent-primary-cap"},
        )
    )
    state.battle_round = 5
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)

    state.advance_to_next_battle_phase()
    result = state.game_result_payload()
    audit = cast(dict[str, object], result["scoring_audit"])
    player_scores = cast(list[dict[str, object]], audit["player_scores"])
    player_a_score = next(score for score in player_scores if score["player_id"] == "player-a")
    player_b_score = next(score for score in player_scores if score["player_id"] == "player-b")

    assert primary_transaction.amount == 45
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
    assert player_b_score["raw_primary_vp"] == 45
    assert _cap_reasons(primary_transaction) == ["primary_vp_cap"]
    assert _cap_reasons(secondary_transaction) == ["secondary_vp_cap"]
    assert _cap_reasons(battle_ready_transaction) == ["battle_ready_vp_cap", "total_vp_cap"]


def test_phase11f_mission_action_cap_accounting_is_source_aware() -> None:
    state = _battle_state(mission_pool_entry_id=PHASE16A_MISSION_POOL_ENTRY_ID)
    assert state.mission_setup is not None
    state.mission_setup = replace(state.mission_setup, primary_mission_id="primary-death-trap")
    policy = mission_scoring_policy_from_setup(state.mission_setup)
    for battle_round, amount in ((1, 15), (2, 15), (3, 14)):
        state.award_victory_points(
            VictoryPointAward(
                player_id="player-a",
                battle_round=battle_round,
                phase=BattlePhase.COMMAND.value,
                amount=amount,
                source_kind=VictoryPointSourceKind.PRIMARY,
                source_id="primary-death-trap",
                scoring_timing="phase_end",
                metadata={"scoring_rule_id": "phase11f-primary-action-base"},
            )
        )
    state.award_victory_points(
        VictoryPointAward(
            player_id="player-a",
            battle_round=1,
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
            battle_round=1,
            phase=BattlePhase.SHOOTING.value,
            action_id="cleanse:center:player-a",
            source_id="cleanse",
            amount=5,
        )
    )
    state.battle_round = 5
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)

    state.advance_to_next_battle_phase()
    result = state.game_result_payload()
    audit = cast(dict[str, object], result["scoring_audit"])
    player_scores = cast(list[dict[str, object]], audit["player_scores"])
    player_a_score = next(score for score in player_scores if score["player_id"] == "player-a")

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
        == 2
    )


def test_phase11f_end_of_battle_primary_vp_is_exempt_from_battle_round_cap() -> None:
    state = _battle_state()
    assert state.mission_setup is not None
    state.mission_setup = replace(state.mission_setup, primary_mission_id="take-and-hold")
    state.award_victory_points(
        VictoryPointAward(
            player_id="player-a",
            battle_round=5,
            phase=BattlePhase.FIGHT.value,
            amount=15,
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id="take-and-hold",
            scoring_timing="phase_end",
            metadata={"scoring_rule_id": "phase11f-round-five-primary"},
        )
    )
    round_capped = state.award_victory_points(
        VictoryPointAward(
            player_id="player-a",
            battle_round=5,
            phase=BattlePhase.FIGHT.value,
            amount=5,
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id="take-and-hold",
            scoring_timing="phase_end",
            metadata={"scoring_rule_id": "phase11f-round-five-primary-extra"},
        )
    )
    end_of_battle = state.award_victory_points(
        VictoryPointAward(
            player_id="player-a",
            battle_round=5,
            phase=BattlePhase.FIGHT.value,
            amount=5,
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id="take-and-hold",
            scoring_timing="end_of_battle",
            metadata={"scoring_rule_id": "phase11f-end-of-battle-primary"},
        )
    )

    assert round_capped.amount == 0
    assert _cap_reasons(round_capped) == ["primary_battle_round_vp_cap"]
    assert end_of_battle.amount == 5
    assert state.victory_point_total("player-a") == 20


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
    state.battle_round = 5
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)

    state.advance_to_next_battle_phase()
    state.scoring_window_states = [
        window for window in state.scoring_window_states if window.window != "end_of_battle"
    ]

    with pytest.raises(GameLifecycleError, match="Final scoring requires recorded policy windows"):
        state.game_result_payload()


def _cap_reasons(transaction: VictoryPointTransaction) -> list[str]:
    payload = transaction.metadata
    assert isinstance(payload, dict)
    audit = payload["vp_cap_audit"]
    assert isinstance(audit, dict)
    reasons = audit["capped_reasons"]
    assert isinstance(reasons, list)
    return [str(reason) for reason in reasons]


def _battle_state(*, mission_pool_entry_id: str = PHASE16A_MISSION_POOL_ENTRY_ID) -> GameState:
    config = _config(mission_pool_entry_id=mission_pool_entry_id)
    state = GameState.from_config(config)
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11f-battlefield",
        armies=tuple(state.army_definitions),
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


def _config(*, mission_pool_entry_id: str = PHASE16A_MISSION_POOL_ENTRY_ID) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
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
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id=mission_pool_entry_id,
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
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
