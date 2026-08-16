from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from tests.support.catalog_package_fixtures import (
    bloodcrushers_army,
    bloodcrushers_package,
    bloodcrushers_unit,
)
from tests.support.catalog_runtime_fixtures import (
    battle_state_with_army,
    bloodcrushers_battlefield_state,
)
from tests.support.selected_to_fight_risk_fixtures import (
    attached_selected_to_fight_risk_fixture,
)

from warhammer40k_core.core.missions import (
    MissionPackError,
    MissionScoringResolutionMode,
    MissionScoringRuleDefinition,
    PrimaryMissionDefinition,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState, ModelPlacement
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_scoring_policies import MissionScoringPolicies
from warhammer40k_core.engine.mission_setup import MissionSetup, PlayerPrimaryMissionAssignment
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.primary_destruction_evidence import (
    ObjectiveMarkerModelWitness,
    PrimaryUnattributedDestructionCause,
    RulesUnitObjectiveProximityWitness,
    destruction_source_objective_proximity_witness,
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.primary_mission_state import PrimaryMissionProgressState
from warhammer40k_core.engine.primary_scoring_resolution import (
    PrimaryScoringResolutionCandidate,
    PrimaryScoringResolutionMode,
    ResolvedPrimaryScoringCandidate,
    primary_scoring_resolution_mode_from_token,
    resolve_primary_scoring_candidates,
)
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    objective_control_record_hash,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PrimaryScoringBoundaryKind,
    PrimaryScoringStateEvidence,
)
from warhammer40k_core.engine.primary_scoring_timing import (
    SUPPORTED_PRIMARY_SCORING_TIMINGS,
    primary_scoring_timing_applies,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    PrimaryComponentTurnStartMembership,
    PrimaryObjectiveMarkerWitness,
    PrimaryRulesUnitTurnStartMembership,
    PrimaryRulesUnitTurnStartSnapshot,
    build_primary_rules_unit_turn_start_snapshot,
    current_primary_component_turn_start_membership,
    current_primary_rules_unit_turn_start_membership,
    primary_rules_unit_turn_start_membership_for_lineage,
    primary_rules_unit_turn_start_snapshots_from_payload,
    primary_rules_unit_turn_start_snapshots_with_created_unit,
    record_primary_rules_unit_turn_start_snapshot,
    record_primary_turn_start_evidence,
    validate_primary_objective_turn_start_states,
    validate_primary_rules_unit_turn_start_snapshots,
    validate_primary_unit_destruction_turn_start_evidence,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    build_primary_unit_destruction_state,
    primary_unit_destruction_id,
    record_primary_destroyed_model_departures,
    record_primary_unit_destructions_for_destroyed_models,
    record_primary_unit_destructions_for_end_turn_cleanup,
    validate_primary_unit_destruction_source_witness_identity,
    validate_primary_unit_destruction_states,
)
from warhammer40k_core.engine.primary_victory_point_policy import (
    validate_victory_point_ledger_policy,
)
from warhammer40k_core.engine.scoring import (
    MissionScoringPolicy,
    PrimaryMissionScoringRule,
    PrimaryUnitDestructionState,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)
from warhammer40k_core.engine.turn_cleanup import EndTurnCleanupState
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    chapter_approved_2026_27_mission_pack,
    warhammer_event_companion_2026_07_mission_pack,
)


@pytest.mark.parametrize(
    ("timing", "battle_round", "phase", "boundary", "end_of_battle"),
    [
        (
            "battle_round_four_onwards_turn_end",
            4,
            "fight",
            ObjectiveControlTiming.TURN_END,
            False,
        ),
        (
            "battle_rounds_two_and_three_command_phase",
            2,
            "command",
            ObjectiveControlTiming.PHASE_END,
            False,
        ),
        (
            "command_phase",
            3,
            "command",
            ObjectiveControlTiming.PHASE_END,
            False,
        ),
        (
            "command_phase_or_round_five_turn_end",
            3,
            "command",
            ObjectiveControlTiming.PHASE_END,
            False,
        ),
        (
            "end_of_battle",
            5,
            "fight",
            ObjectiveControlTiming.TURN_END,
            True,
        ),
        (
            "first_and_second_battle_round_turn_end",
            2,
            "fight",
            ObjectiveControlTiming.TURN_END,
            False,
        ),
        (
            "first_battle_round_turn_end",
            1,
            "fight",
            ObjectiveControlTiming.TURN_END,
            False,
        ),
        (
            "turn_end",
            3,
            "fight",
            ObjectiveControlTiming.TURN_END,
            False,
        ),
        (
            "turn_end_from_battle_round_two",
            2,
            "fight",
            ObjectiveControlTiming.TURN_END,
            False,
        ),
    ],
)
def test_phase17n_every_primary_scoring_timing_has_an_executable_boundary(
    timing: str,
    battle_round: int,
    phase: str,
    boundary: ObjectiveControlTiming,
    end_of_battle: bool,
) -> None:
    assert set(SUPPORTED_PRIMARY_SCORING_TIMINGS) == {
        "battle_round_four_onwards_turn_end",
        "battle_rounds_two_and_three_command_phase",
        "command_phase",
        "command_phase_or_round_five_turn_end",
        "end_of_battle",
        "first_and_second_battle_round_turn_end",
        "first_battle_round_turn_end",
        "turn_end",
        "turn_end_from_battle_round_two",
    }
    assert primary_scoring_timing_applies(
        timing=timing,
        battle_round=battle_round,
        phase=phase,
        objective_control_timing=boundary,
        primary_scoring_phase="command",
        primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
        game_length_battle_rounds=5,
        end_of_battle=end_of_battle,
    )


@pytest.mark.parametrize(
    ("timing", "battle_round", "phase", "boundary"),
    [
        (
            "battle_round_four_onwards_turn_end",
            3,
            "fight",
            ObjectiveControlTiming.TURN_END,
        ),
        (
            "battle_rounds_two_and_three_command_phase",
            4,
            "command",
            ObjectiveControlTiming.PHASE_END,
        ),
        ("command_phase", 3, "movement", ObjectiveControlTiming.PHASE_END),
        (
            "command_phase_or_round_five_turn_end",
            5,
            "command",
            ObjectiveControlTiming.PHASE_END,
        ),
        (
            "command_phase_or_round_five_turn_end",
            1,
            "command",
            ObjectiveControlTiming.PHASE_END,
        ),
        (
            "first_and_second_battle_round_turn_end",
            3,
            "fight",
            ObjectiveControlTiming.TURN_END,
        ),
        (
            "first_battle_round_turn_end",
            2,
            "fight",
            ObjectiveControlTiming.TURN_END,
        ),
        ("turn_end", 3, "fight", ObjectiveControlTiming.PHASE_END),
        (
            "turn_end_from_battle_round_two",
            1,
            "fight",
            ObjectiveControlTiming.TURN_END,
        ),
    ],
)
def test_phase17n_primary_scoring_timing_rejects_wrong_boundaries(
    timing: str,
    battle_round: int,
    phase: str,
    boundary: ObjectiveControlTiming,
) -> None:
    assert not primary_scoring_timing_applies(
        timing=timing,
        battle_round=battle_round,
        phase=phase,
        objective_control_timing=boundary,
        primary_scoring_phase="command",
        primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
        game_length_battle_rounds=5,
        end_of_battle=False,
    )


def test_phase17n_primary_scoring_timing_rejects_forged_boundary_context() -> None:
    with pytest.raises(GameLifecycleError, match="TURN_END boundary must be a Fight phase"):
        primary_scoring_timing_applies(
            timing="turn_end",
            battle_round=3,
            phase="command",
            objective_control_timing=ObjectiveControlTiming.TURN_END,
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=5,
            end_of_battle=False,
        )
    with pytest.raises(GameLifecycleError, match="final battle-round TURN_END boundary"):
        primary_scoring_timing_applies(
            timing="end_of_battle",
            battle_round=1,
            phase="fight",
            objective_control_timing=ObjectiveControlTiming.TURN_END,
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="final battle-round TURN_END boundary"):
        primary_scoring_timing_applies(
            timing="end_of_battle",
            battle_round=5,
            phase="fight",
            objective_control_timing=ObjectiveControlTiming.PHASE_END,
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="requires a five-battle-round game"):
        primary_scoring_timing_applies(
            timing="command_phase_or_round_five_turn_end",
            battle_round=3,
            phase="fight",
            objective_control_timing=ObjectiveControlTiming.TURN_END,
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=3,
            end_of_battle=False,
        )


def test_phase17n_round_five_command_or_turn_end_timing_uses_turn_end_only() -> None:
    assert primary_scoring_timing_applies(
        timing="command_phase_or_round_five_turn_end",
        battle_round=5,
        phase="fight",
        objective_control_timing=ObjectiveControlTiming.TURN_END,
        primary_scoring_phase="command",
        primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
        game_length_battle_rounds=5,
        end_of_battle=False,
    )


def test_phase17n_end_of_battle_is_an_exclusive_timing_context() -> None:
    assert not primary_scoring_timing_applies(
        timing="turn_end",
        battle_round=5,
        phase="fight",
        objective_control_timing=ObjectiveControlTiming.TURN_END,
        primary_scoring_phase="command",
        primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
        game_length_battle_rounds=5,
        end_of_battle=True,
    )
    assert not primary_scoring_timing_applies(
        timing="end_of_battle",
        battle_round=5,
        phase="fight",
        objective_control_timing=ObjectiveControlTiming.TURN_END,
        primary_scoring_phase="command",
        primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
        game_length_battle_rounds=5,
        end_of_battle=False,
    )


def test_phase17n_primary_scoring_timing_fails_closed_for_unknown_or_invalid_context() -> None:
    with pytest.raises(GameLifecycleError, match="Unsupported primary scoring rule timing"):
        primary_scoring_timing_applies(
            timing="invented_timing",
            battle_round=1,
            phase="command",
            objective_control_timing=ObjectiveControlTiming.PHASE_END,
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=5,
            end_of_battle=False,
        )
    with pytest.raises(GameLifecycleError, match="outside the battle"):
        primary_scoring_timing_applies(
            timing="turn_end",
            battle_round=6,
            phase="fight",
            objective_control_timing=ObjectiveControlTiming.TURN_END,
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=5,
            end_of_battle=False,
        )
    with pytest.raises(GameLifecycleError, match="must be ObjectiveControlTiming"):
        primary_scoring_timing_applies(
            timing="turn_end",
            battle_round=1,
            phase="fight",
            objective_control_timing="turn_end",  # type: ignore[arg-type]
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=5,
            end_of_battle=False,
        )
    with pytest.raises(GameLifecycleError, match="must be a positive integer"):
        primary_scoring_timing_applies(
            timing="turn_end",
            battle_round=1,
            phase="fight",
            objective_control_timing=ObjectiveControlTiming.TURN_END,
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=0,
            end_of_battle=False,
        )
    with pytest.raises(GameLifecycleError, match="end_of_battle must be a bool"):
        primary_scoring_timing_applies(
            timing="turn_end",
            battle_round=1,
            phase="fight",
            objective_control_timing=ObjectiveControlTiming.TURN_END,
            primary_scoring_phase="command",
            primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
            game_length_battle_rounds=5,
            end_of_battle=cast(bool, 0),
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


def test_phase17n_primary_resolution_typed_contract_fails_closed() -> None:
    candidate = _candidate(rule_id="rule-a", amount=1)

    with pytest.raises(GameLifecycleError, match="amount must be a positive integer"):
        _candidate(rule_id="zero-amount", amount=0)
    with pytest.raises(GameLifecycleError, match="mode token must be a string"):
        primary_scoring_resolution_mode_from_token(None)
    with pytest.raises(GameLifecycleError, match="candidates must be a tuple"):
        resolve_primary_scoring_candidates(
            cast(tuple[PrimaryScoringResolutionCandidate, ...], [candidate])
        )
    with pytest.raises(GameLifecycleError, match="requires typed candidates"):
        resolve_primary_scoring_candidates(
            cast(tuple[PrimaryScoringResolutionCandidate, ...], (object(),))
        )
    with pytest.raises(GameLifecycleError, match="requires a typed candidate"):
        ResolvedPrimaryScoringCandidate(
            candidate=cast(PrimaryScoringResolutionCandidate, object()),
            achieved_rule_ids=("rule-a",),
            selected_rule_ids=("rule-a",),
            suppressed_rule_ids=(),
        )


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


def test_phase17n_objective_proximity_requires_authoritative_domain_inputs() -> None:
    state = _minimal_evidence_game_state()
    placement = _evidence_model_placement()
    attribution = _deadly_demise_attribution()

    with pytest.raises(GameLifecycleError, match="evidence requires GameState"):
        rules_unit_objective_proximity_witness(
            state=cast(GameState, object()),
            rules_unit_instance_id="army-source:unit-source",
        )
    with pytest.raises(GameLifecycleError, match="evidence requires EventLog"):
        destruction_source_objective_proximity_witness(
            state=state,
            event_log=cast(EventLog, object()),
            attribution=attribution,
            destroyed_model_placement=placement,
        )
    with pytest.raises(GameLifecycleError, match="requires typed attribution"):
        destruction_source_objective_proximity_witness(
            state=state,
            event_log=EventLog(),
            attribution=cast(ModelDestructionAttribution, object()),
            destroyed_model_placement=placement,
        )
    with pytest.raises(GameLifecycleError, match="requires its source model identity"):
        destruction_source_objective_proximity_witness(
            state=state,
            event_log=EventLog(),
            attribution=_deadly_demise_attribution(source_model_instance_id=None),
            destroyed_model_placement=placement,
        )


def test_phase17n_deadly_demise_objective_evidence_inherits_exact_event_witness() -> None:
    state = _minimal_evidence_game_state()
    placement = _evidence_model_placement()
    attribution = _deadly_demise_attribution()
    witness = _source_objective_witness()

    missing_witness_log = EventLog()
    missing_witness_log.append(
        "model_destroyed",
        {"model_instance_id": placement.model_instance_id},
    )
    with pytest.raises(GameLifecycleError, match="lacks objective proximity evidence"):
        destruction_source_objective_proximity_witness(
            state=state,
            event_log=missing_witness_log,
            attribution=attribution,
            destroyed_model_placement=placement,
        )

    inherited_log = EventLog()
    inherited_log.append(
        "model_destroyed",
        {
            "model_instance_id": placement.model_instance_id,
            "destroyed_rules_unit_objective_proximity_witness": witness.to_payload(),
        },
    )
    assert (
        destruction_source_objective_proximity_witness(
            state=state,
            event_log=inherited_log,
            attribution=attribution,
            destroyed_model_placement=placement,
        )
        == witness
    )

    drifted_witness = replace(witness, rules_unit_instance_id="army-source:unit-other")
    drifted_log = EventLog()
    drifted_log.append(
        "model_destroyed",
        {
            "model_instance_id": placement.model_instance_id,
            "destroyed_rules_unit_objective_proximity_witness": drifted_witness.to_payload(),
        },
    )
    with pytest.raises(GameLifecycleError, match="source identity drift"):
        destruction_source_objective_proximity_witness(
            state=state,
            event_log=drifted_log,
            attribution=attribution,
            destroyed_model_placement=placement,
        )


def test_phase17n_deadly_demise_requires_live_or_historical_source_placement() -> None:
    placement = _evidence_model_placement()
    attribution = _deadly_demise_attribution()

    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        destruction_source_objective_proximity_witness(
            state=_minimal_evidence_game_state(),
            event_log=EventLog(),
            attribution=attribution,
            destroyed_model_placement=placement,
        )
    with pytest.raises(GameLifecycleError, match="either an inherited source destruction witness"):
        destruction_source_objective_proximity_witness(
            state=_minimal_evidence_game_state(
                battlefield=BattlefieldRuntimeState(
                    battlefield_id="evidence-battlefield",
                    battlefield_width_inches=60.0,
                    battlefield_depth_inches=44.0,
                    placed_armies=(),
                )
            ),
            event_log=EventLog(),
            attribution=attribution,
            destroyed_model_placement=placement,
        )


def test_phase17n_catalog_objective_evidence_rejects_invalid_destroyed_model_context() -> None:
    package = bloodcrushers_package()
    unit = bloodcrushers_unit(
        package=package,
        selected_wargear_id="000001115:instrument-of-chaos",
    )
    army = bloodcrushers_army(package=package, unit=unit)
    battlefield = bloodcrushers_battlefield_state(army=army, unit=unit)
    state = battle_state_with_army(army=army, battlefield=battlefield)
    state.mission_setup = MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id=army.player_id,
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-opponent",
        defender_force_disposition_id="purge-the-foe",
    )

    state.battlefield_state = None
    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=unit.unit_instance_id,
        )
    state.battlefield_state = battlefield

    with pytest.raises(GameLifecycleError, match="must be a ModelPlacement"):
        rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=unit.unit_instance_id,
            included_destroyed_model_placement=cast(ModelPlacement, object()),
        )
    outside_placement = ModelPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_instance_id=f"{unit.unit_instance_id}:outside-model",
        pose=Pose.at(12.0, 12.0),
    )
    with pytest.raises(GameLifecycleError, match="outside the rules unit"):
        rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=unit.unit_instance_id,
            included_destroyed_model_placement=outside_placement,
        )
    known_model = unit.own_models[0]
    drifted_component_id = known_model.model_instance_id.rsplit(":", maxsplit=1)[0]
    assert drifted_component_id != unit.unit_instance_id
    component_drift_placement = ModelPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=drifted_component_id,
        model_instance_id=known_model.model_instance_id,
        pose=Pose.at(12.0, 12.0),
    )
    with pytest.raises(GameLifecycleError, match="component identity drift"):
        rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=unit.unit_instance_id,
            included_destroyed_model_placement=component_drift_placement,
        )


def test_phase17n_objective_evidence_requires_canonical_attached_rules_unit_id() -> None:
    state, _runtime, _controller, bodyguard, _leader, _enemy, _attached_id = (
        attached_selected_to_fight_risk_fixture(pre_split=False)
    )

    with pytest.raises(GameLifecycleError, match="canonical rules-unit identity"):
        rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=bodyguard.unit_instance_id,
        )


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
    with pytest.raises(GameLifecycleError, match="objective evidence already exists"):
        record_primary_turn_start_evidence(state=state)

    state.primary_objective_turn_start_states.clear()
    state.primary_rules_unit_turn_start_snapshots = [position_snapshot]
    with pytest.raises(GameLifecycleError, match="position evidence already exists"):
        record_primary_turn_start_evidence(state=state)


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


def test_phase17n_turn_start_lineage_lookup_reassembles_split_components() -> None:
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
    reconstructed = primary_rules_unit_turn_start_membership_for_lineage(
        snapshot=split_snapshot,
        rules_unit_instance_id="attached-ab",
        component_unit_instance_ids=("unit-a", "unit-b"),
    )
    assert reconstructed.rules_unit_instance_id == "attached-ab"
    assert reconstructed.component_unit_instance_ids == ("unit-a", "unit-b")

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
    with pytest.raises(GameLifecycleError, match="exactly one membership per component"):
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


def _minimal_evidence_game_state(
    *,
    battlefield: BattlefieldRuntimeState | None = None,
) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    return GameState(
        game_id="primary-evidence-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=0,
        battle_round=1,
        active_player_id="player-a",
        battlefield_state=battlefield,
    )


def _catalog_tracking_state() -> tuple[GameState, UnitInstance]:
    package = bloodcrushers_package()
    unit = bloodcrushers_unit(
        package=package,
        selected_wargear_id="000001115:instrument-of-chaos",
    )
    army = bloodcrushers_army(package=package, unit=unit)
    initial_battlefield = bloodcrushers_battlefield_state(army=army, unit=unit)
    state = battle_state_with_army(army=army, battlefield=initial_battlefield)
    mission_setup = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-1",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-1",
        attacker_player_id=army.player_id,
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-opponent",
        defender_force_disposition_id="take-and-hold",
    )
    state.mission_setup = mission_setup
    state.battlefield_state = replace(
        initial_battlefield,
        battlefield_width_inches=mission_setup.battlefield_width_inches,
        battlefield_depth_inches=mission_setup.battlefield_depth_inches,
        terrain_features=mission_setup.terrain_features,
    )
    return state, unit


def _evidence_model_placement() -> ModelPlacement:
    return ModelPlacement(
        army_id="army-source",
        player_id="player-a",
        unit_instance_id="army-source:unit-source",
        model_instance_id="army-source:unit-source:model-source",
        pose=Pose.at(12.0, 12.0),
    )


def _deadly_demise_attribution(
    *,
    source_model_instance_id: str | None = "army-source:unit-source:model-source",
) -> ModelDestructionAttribution:
    return ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.DEADLY_DEMISE,
        source_rules_unit_instance_id="army-source:unit-source",
        source_model_instance_id=source_model_instance_id,
    )


def _source_objective_witness() -> RulesUnitObjectiveProximityWitness:
    return RulesUnitObjectiveProximityWitness(
        rules_unit_instance_id="army-source:unit-source",
        component_unit_instance_ids=("army-source:unit-source",),
        objective_marker_witnesses=(
            ObjectiveMarkerModelWitness(
                objective_marker_id="objective-a",
                model_instance_ids=("army-source:unit-source:model-source",),
            ),
        ),
    )


def _turn_start_component(
    unit_instance_id: str,
    model_instance_id: str,
) -> PrimaryComponentTurnStartMembership:
    return PrimaryComponentTurnStartMembership(
        unit_instance_id=unit_instance_id,
        evaluated_model_instance_ids=(model_instance_id,),
        logical_terrain_area_ids=("area-a",),
        objective_marker_witnesses=(
            PrimaryObjectiveMarkerWitness(
                objective_marker_id="objective-a",
                model_instance_ids=(model_instance_id,),
            ),
        ),
    )


def _turn_start_snapshot(
    *,
    memberships: tuple[PrimaryRulesUnitTurnStartMembership, ...] | None = None,
) -> PrimaryRulesUnitTurnStartSnapshot:
    if memberships is None:
        component = _turn_start_component("unit-a", "model-a")
        memberships = (
            PrimaryRulesUnitTurnStartMembership(
                rules_unit_instance_id="unit-a",
                component_memberships=(component,),
            ),
        )
    return PrimaryRulesUnitTurnStartSnapshot(
        snapshot_id="primary-rules-unit-turn-start:game-a:round-01:player-a",
        game_id="game-a",
        active_player_id="player-a",
        battle_round=1,
        rules_unit_memberships=memberships,
        source_id="game-a:primary-rules-unit-turn-start:round-01:player-a",
    )


def _validate_turn_start_snapshots(
    snapshots: object,
    *,
    known_models: object = (("unit-a", ("model-a",)),),
    known_attached: object = (),
) -> list[PrimaryRulesUnitTurnStartSnapshot]:
    return validate_primary_rules_unit_turn_start_snapshots(
        snapshots,
        game_id="game-a",
        player_ids=("player-a", "player-b"),
        known_component_model_ids_by_unit=cast(
            tuple[tuple[str, tuple[str, ...]], ...],
            known_models,
        ),
        known_attached_component_ids_by_rules_unit=cast(
            tuple[tuple[str, tuple[str, ...]], ...],
            known_attached,
        ),
        known_logical_terrain_area_ids=("area-a",),
        known_objective_marker_ids=("objective-a",),
    )


def _validate_destruction_states(
    states: object,
    *,
    owner_by_unit_id: dict[str, str] | None = None,
) -> list[PrimaryUnitDestructionState]:
    if owner_by_unit_id is None:
        owner_by_unit_id = {"unit-destroyed": "player-b"}
    return validate_primary_unit_destruction_states(
        states,
        game_id="game-a",
        player_ids=("player-a", "player-b"),
        owner_by_unit_id=owner_by_unit_id,
        model_ids_by_unit_id={"unit-destroyed": ("model-destroyed",)},
        known_rules_unit_components_by_id={"unit-destroyed": ("unit-destroyed",)},
        known_objective_marker_ids=("objective-a",),
    )


def _build_tracking_destruction(
    *,
    state: GameState,
    unit: UnitInstance,
    attribution: ModelDestructionAttribution | None = None,
) -> PrimaryUnitDestructionState:
    return build_primary_unit_destruction_state(
        state=state,
        destruction_attribution=attribution,
        source_model_destroyed_event_id=(None if attribution is None else "event-model-destroyed"),
        source_rules_unit_objective_proximity_witness=None,
        source_battlefield_departure_ids=(),
        unattributed_cause=(
            PrimaryUnattributedDestructionCause.RESERVE_DEADLINE if attribution is None else None
        ),
        source_mutation_id=("mutation-reserve-deadline" if attribution is None else None),
        destroyed_unit_instance_id=unit.unit_instance_id,
        source_id="source-destruction-build",
    )


def _record_tracking_destruction_models(
    *,
    state: GameState,
    destroyed_model_instance_ids: tuple[str, ...],
    left_battlefield: bool = False,
    attribution: ModelDestructionAttribution | None = None,
    destroyed_witness: RulesUnitObjectiveProximityWitness | None = None,
) -> tuple[PrimaryUnitDestructionState, ...]:
    return record_primary_unit_destructions_for_destroyed_models(
        state=state,
        destroyed_model_instance_ids=destroyed_model_instance_ids,
        destruction_attribution=attribution,
        source_model_destroyed_event_id=(None if attribution is None else "event-model-destroyed"),
        source_rules_unit_objective_proximity_witness=None,
        destroyed_rules_unit_objective_proximity_witness=destroyed_witness,
        unattributed_cause=(
            PrimaryUnattributedDestructionCause.RESERVE_DEADLINE if attribution is None else None
        ),
        source_mutation_id=("mutation-destruction" if attribution is None else None),
        left_battlefield=left_battlefield,
        source_id="source-destruction-mutation",
    )


def _unattributed_destruction_state() -> PrimaryUnitDestructionState:
    source_id = "source-destruction-a"
    return PrimaryUnitDestructionState(
        destruction_id=primary_unit_destruction_id(
            game_id="game-a",
            source_id=source_id,
            destroyed_unit_instance_id="unit-destroyed",
        ),
        game_id="game-a",
        destroying_player_id=None,
        destruction_attribution=None,
        source_model_destroyed_event_id=None,
        source_rules_unit_objective_proximity_witness=None,
        source_battlefield_departure_ids=(),
        unattributed_cause=PrimaryUnattributedDestructionCause.RESERVE_DEADLINE,
        source_mutation_id="mutation-reserve-deadline-a",
        destroyed_player_id="player-b",
        active_player_id="player-a",
        battle_round=1,
        phase="command",
        destroyed_unit_instance_id="unit-destroyed",
        started_turn_terrain_feature_ids=("area-a",),
        started_turn_objective_marker_ids=("objective-a",),
        source_id=source_id,
    )


def _attributed_destruction_state(
    *,
    destroying_player_id: str = "player-a",
    witness_component_id: str = "unit-source",
    witness_model_id: str = "model-source",
) -> PrimaryUnitDestructionState:
    source_id = "source-destruction-attributed-a"
    attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id=destroying_player_id,
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id="rules-unit-source",
        source_model_instance_id="model-source",
    )
    witness = RulesUnitObjectiveProximityWitness(
        rules_unit_instance_id="rules-unit-source",
        component_unit_instance_ids=(witness_component_id,),
        objective_marker_witnesses=(
            ObjectiveMarkerModelWitness(
                objective_marker_id="objective-a",
                model_instance_ids=(witness_model_id,),
            ),
        ),
    )
    return PrimaryUnitDestructionState(
        destruction_id=primary_unit_destruction_id(
            game_id="game-a",
            source_id=source_id,
            destroyed_unit_instance_id="unit-destroyed",
        ),
        game_id="game-a",
        destroying_player_id=destroying_player_id,
        destruction_attribution=attribution,
        source_model_destroyed_event_id="event-model-destroyed-a",
        source_rules_unit_objective_proximity_witness=witness,
        source_battlefield_departure_ids=("departure-a",),
        unattributed_cause=None,
        source_mutation_id=None,
        destroyed_player_id="player-b",
        active_player_id="player-a",
        battle_round=1,
        phase="shooting",
        destroyed_unit_instance_id="unit-destroyed",
        started_turn_terrain_feature_ids=("area-a",),
        started_turn_objective_marker_ids=("objective-a",),
        source_id=source_id,
    )


def _source_rule(
    *,
    rule_id: str,
    timing: str = "turn_end",
    source_kind: str = "primary",
    mode: MissionScoringResolutionMode = MissionScoringResolutionMode.CUMULATIVE,
    group_id: str | None = "shared-group",
) -> MissionScoringRuleDefinition:
    return MissionScoringRuleDefinition(
        rule_id=rule_id,
        timing=timing,
        source_kind=source_kind,
        victory_points=2,
        cap=None,
        condition="each-controlled-objective",
        resolution_mode=mode,
        resolution_group_id=group_id,
        source_id=f"source:{rule_id}",
    )


def _source_primary_mission(
    rules: tuple[MissionScoringRuleDefinition, ...],
) -> PrimaryMissionDefinition:
    return PrimaryMissionDefinition(
        primary_mission_id="primary-resolution-test",
        name="Resolution Test",
        source_id="source:primary-resolution-test",
        scoring_kind="structured-primary",
        scoring_rules=rules,
    )


def _runtime_rule(
    *,
    rule_id: str,
    timing: str = "turn_end",
    mode: MissionScoringResolutionMode = MissionScoringResolutionMode.CUMULATIVE,
    group_id: str | None = "shared-group",
) -> PrimaryMissionScoringRule:
    return PrimaryMissionScoringRule(
        rule_id=rule_id,
        timing=timing,
        source_kind=VictoryPointSourceKind.PRIMARY,
        victory_points=2,
        cap=None,
        condition="each-controlled-objective",
        resolution_mode=mode,
        resolution_group_id=group_id,
        source_id=f"source:{rule_id}",
    )


def _runtime_policy(
    rules: tuple[PrimaryMissionScoringRule, ...],
    *,
    player_id: str = "player-a",
    primary_mission_id: str = "primary-resolution-test",
) -> MissionScoringPolicy:
    return MissionScoringPolicy(
        player_id=player_id,
        force_disposition_id="force-a",
        mission_pack_id="mission-pack",
        primary_mission_id=primary_mission_id,
        primary_scoring_supported=True,
        game_length_battle_rounds=5,
        primary_scoring_phase="command",
        primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
        primary_scoring_rule_id=None,
        primary_scoring_rule_condition=None,
        primary_scoring_rule_source_id=None,
        primary_vp_per_controlled_objective=None,
        primary_max_vp_per_turn=15,
        primary_scoring_rules=rules,
        secondary_vp_per_score=5,
        secondary_scoring_rules=(),
        mission_action_scoring_rules=(),
        mission_action_vp=3,
        reserve_destruction_timing="battle-round-end",
        reserve_destruction_battle_round=None,
        reserve_destruction_excludes_during_battle_strategic_reserves=True,
        reserve_destruction_only_declare_battle_formations=True,
        primary_vp_cap=50,
        secondary_vp_cap=40,
        battle_ready_vp=10,
        total_vp_cap=100,
        end_of_round_scoring_windows=("end-of-round",),
        end_of_game_scoring_windows=("end-of-game",),
        source_id="source:mission-policy",
    )


def _test_primary_state_evidence(
    *,
    record: ObjectiveControlRecord,
    end_of_battle: bool,
) -> PrimaryScoringStateEvidence:
    return PrimaryScoringStateEvidence.create(
        game_id=record.game_id,
        battlefield_id=record.battlefield_id,
        battle_round=record.battle_round,
        active_player_id=record.active_player_id,
        phase=record.phase,
        timing=record.timing,
        scoring_boundary_kind=(
            PrimaryScoringBoundaryKind.END_OF_BATTLE
            if end_of_battle
            else PrimaryScoringBoundaryKind.ORDINARY
        ),
        objective_control_record_id=record.record_id,
        objective_control_record_hash=objective_control_record_hash(record),
        primary_mission_progress_state=PrimaryMissionProgressState.empty(),
        primary_mission_action_states=(),
        primary_battlefield_departure_states=(),
        primary_unit_destruction_state_ids=(),
        current_rules_unit_position_witnesses=(),
        primary_scoring_spatial_evidence_by_player_id=(),
    )


def _candidate(
    *,
    rule_id: str,
    amount: int,
    mode: PrimaryScoringResolutionMode = PrimaryScoringResolutionMode.INDEPENDENT,
    group_id: str | None = None,
) -> PrimaryScoringResolutionCandidate:
    return PrimaryScoringResolutionCandidate(
        rule_id=rule_id,
        amount=amount,
        resolution_mode=mode,
        resolution_group_id=group_id,
    )
