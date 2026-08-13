from __future__ import annotations

from dataclasses import replace

import pytest

from warhammer40k_core.core.missions import (
    MissionPackError,
    MissionScoringResolutionMode,
    MissionScoringRuleDefinition,
    PrimaryMissionDefinition,
)
from warhammer40k_core.engine.mission_scoring_policies import MissionScoringPolicies
from warhammer40k_core.engine.mission_setup import PlayerPrimaryMissionAssignment
from warhammer40k_core.engine.objective_control import ObjectiveControlTiming
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_scoring_resolution import (
    PrimaryScoringResolutionCandidate,
    PrimaryScoringResolutionMode,
    primary_scoring_resolution_mode_from_token,
    resolve_primary_scoring_candidates,
)
from warhammer40k_core.engine.primary_scoring_timing import (
    SUPPORTED_PRIMARY_SCORING_TIMINGS,
    primary_scoring_timing_applies,
)
from warhammer40k_core.engine.scoring import (
    MissionScoringPolicy,
    PrimaryMissionScoringRule,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)
from warhammer40k_core.rules.mission_pack_import import (
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
                group_id="determined-acquisition-command-primary",
            ),
            _runtime_rule(
                rule_id="determined-acquisition-opponent-territory-bonus",
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

    ledger = VictoryPointLedger.initial(player_id="player-a")
    transactions: list[VictoryPointTransaction] = []
    for result in resolved:
        award = VictoryPointAward(
            player_id="player-a",
            battle_round=2,
            phase="command",
            amount=result.candidate.amount,
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id=policy.primary_mission_id,
            scoring_timing="phase_end",
            metadata=result.metadata(),
        )
        applied_amount, metadata = policy.capped_award_for_ledger(
            ledger=ledger,
            award=award,
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

    end_of_battle_award = VictoryPointAward(
        player_id="player-a",
        battle_round=2,
        phase="fight",
        amount=5,
        source_kind=VictoryPointSourceKind.PRIMARY,
        source_id=policy.primary_mission_id,
        scoring_timing="end_of_battle",
        metadata={"scoring_rule_id": "end-of-battle-primary"},
    )
    applied_amount, metadata = policy.capped_award_for_ledger(
        ledger=ledger,
        award=end_of_battle_award,
    )
    ledger, end_of_battle_transaction = ledger.award(
        end_of_battle_award,
        applied_amount=applied_amount,
        metadata=metadata,
    )

    assert end_of_battle_transaction.amount == 5
    assert end_of_battle_transaction.metadata == {"scoring_rule_id": "end-of-battle-primary"}
    assert ledger.victory_points == 20


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
