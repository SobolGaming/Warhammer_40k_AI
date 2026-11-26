"""Native Lord of Change profile offers at a constructed Shooting start."""

from __future__ import annotations

import json
from dataclasses import replace
from fractions import Fraction
from typing import cast

import pytest

from tests.generic_modifier_helpers import generic_effect
from tests.phase15c_fight_order_helpers import fight_config, unit_placement_at
from tests.setup_completion_helpers import (
    record_current_battlefield_placements_for_fixture,
    record_primary_turn_start_evidence_for_fixture,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.ordinary_ranged_profile_policy import (
    RangedProfileAdmission,
    RangedProfileGap,
    RangedProfileGapReason,
    generate_ordinary_ranged_profile_candidates,
    ordinary_ranged_profile_registration,
)
from warhammer40k_core.ai.player_policy import (
    PlayerDecisionContext,
    PolicyAction,
    PolicyError,
    PolicyRouter,
    payload_digest,
)
from warhammer40k_core.ai.runner import BoundedPolicyRunner, RunLimits, RunnerError
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import muster_army
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatusKind
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_cavalcade_2026_11,
)

LORD = "000001120"
BOLT = f"{LORD}:bolt-of-change"
ACTOR = "player-a"
DEFENDER = "player-b"
SHOOTER = "army-alpha:attacker"
TARGET = "army-beta:defender"


def _shooting_session(
    *,
    target_wounds: int,
    shooter_wounds: int = 18,
    grant: str = "Ignores Cover",
    wound_bonus: bool = False,
) -> tuple[LocalGameSession, PlayerDecisionContext]:
    package = chaos_daemons_cavalcade_2026_11.catalog_package()
    config = replace(
        fight_config(
            game_id="stage3-bolt-of-change",
            alpha_unit_ids=("attacker",),
            enemy_unit_ids=("defender",),
            datasheet_id=LORD,
            model_profile_id=f"{LORD}:lord-of-change",
            model_count=1,
            alpha_faction_id="chaos-daemons",
            enemy_faction_id="chaos-daemons",
            alpha_detachment_ids=("cavalcade-of-chaos", "shadow-legion"),
            enemy_detachment_ids=("cavalcade-of-chaos", "shadow-legion"),
            catalog=package.army_catalog,
        ),
        model_geometries=package.model_geometries,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="stage3-shooting-profile-fixture",
        ),
    )
    armies = tuple(
        muster_army(
            catalog=config.army_catalog, request=request, model_geometries=config.model_geometries
        )
        for request in config.army_muster_requests
    )
    mission = config.mission_setup
    assert mission is not None
    battlefield = create_deterministic_battlefield_scenario(
        battlefield_id=f"{config.game_id}-battlefield",
        armies=armies,
        battlefield_width_inches=mission.battlefield_width_inches,
        battlefield_depth_inches=mission.battlefield_depth_inches,
    ).battlefield_state
    state = GameState.from_config(config)
    for army, pose, wounds in zip(
        armies, (Pose.at(20, 20), Pose.at(34, 20)), (shooter_wounds, target_wounds), strict=True
    ):
        (unit,) = army.units
        (model,) = unit.own_models
        unit = replace(unit, own_models=(replace(model, wounds_remaining=wounds),))
        state.record_army_definition(replace(army, units=(unit,)))
        battlefield = battlefield.with_unit_placement(
            unit_placement_at(unit, army_id=army.army_id, player_id=army.player_id, poses=(pose,))
        )
    state.record_battlefield_state(battlefield)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    state.battle_round = 1
    state.active_player_id = ACTOR
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player, SecondaryMissionMode.FIXED, ("assassination", "bring_it_down")
            )
        )
    if wound_bonus:
        effect = generic_effect(
            effect_id="stage3-contextual-shooting-wound-bonus",
            owner_player_id=ACTOR,
            target_unit_instance_ids=(SHOOTER,),
            target_kind="this_unit",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "wound", "delta": 1},
        )
        state.record_persisting_effect(
            replace(
                effect,
                started_phase=BattlePhase.SHOOTING,
                expiration=EffectExpiration.end_phase(
                    battle_round=1, phase=BattlePhase.SHOOTING, player_id=ACTOR
                ),
            )
        )
    decisions = DecisionController()
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    session = LocalGameSession(
        GameLifecycle.from_payload(
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": decisions.to_payload(),
                "reaction_queue": {"frames": []},
            }
        )
    )
    for index in range(12):
        status = session.advance_until_decision_or_terminal()
        request = status.decision_request
        assert request is not None
        assert request.actor_id is not None
        actor = request.actor_id
        view = session.view(viewer_player_id=actor)
        pending = view["pending_decision"]
        assert pending is not None
        family = pending["decision_type"]
        if family == "submit_shooting_declaration":
            return session, PlayerDecisionContext.from_view(view, choice_seed=7)
        viewer = ViewerContext.for_player(actor)
        result_id = f"shooting-profile-prefix:{index}"
        if family == "submit_stratagem_target_proposal":
            status = session.submit_viewer_parameterized_payload(
                viewer=viewer,
                request_id=pending["request_id"],
                result_id=result_id,
                payload=stratagem_decline_payload(),
            )
        else:
            if family == "select_faction_rule_shooting_phase_start_option":
                option = next(
                    option["option_id"]
                    for option in pending["options"]
                    if cast(
                        dict[str, JsonValue],
                        cast(dict[str, JsonValue], option["payload"])[
                            "selected_named_weapon_ability_choice"
                        ],
                    )["keyword"]
                    == grant
                )
            else:
                option = {
                    "select_shooting_unit": SHOOTER,
                    "select_shooting_type": "normal",
                    "use_stratagem": "decline_stratagem_window",
                    "resolve_reaction_window": "decline",
                }[family]
            status = session.submit_viewer_option(
                viewer=viewer,
                request_id=pending["request_id"],
                option_id=option,
                result_id=result_id,
            )
        assert status.status_kind not in (
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        )
    raise AssertionError("Native Shooting declaration was not reached.")


def _proposal(action: PolicyAction) -> dict[str, JsonValue]:
    assert action.proposal_json is not None
    return cast(dict[str, JsonValue], json.loads(action.proposal_json))


def _finish_volley(session: LocalGameSession) -> None:
    for index in range(32):
        if any(
            event.event_type == "attack_sequence_completed"
            for event in session.lifecycle.decision_controller.event_log.records
        ):
            return
        status = session.advance_until_decision_or_terminal()
        request = status.decision_request
        assert request is not None
        family = request.decision_type
        if family in {"select_shooting_unit", "select_charging_unit"}:
            return
        assert request.actor_id is not None
        actor = request.actor_id
        pending = session.view(viewer_player_id=actor)["pending_decision"]
        assert pending is not None
        viewer = ViewerContext.for_player(actor)
        result_id = f"shooting-profile-resolution:{index}"
        if family == "submit_stratagem_target_proposal":
            status = session.submit_viewer_parameterized_payload(
                viewer=viewer,
                request_id=pending["request_id"],
                result_id=result_id,
                payload=stratagem_decline_payload(),
            )
        else:
            assert family in {
                "resolve_sequencing_order",
                "select_resolve_target_unit",
                "select_attack_weapon_group",
                "select_damage_allocation_model",
                "select_allocation_order",
                "select_mortal_wound_model",
                "select_saving_throw",
                "select_save",
                "use_stratagem",
                "resolve_reaction_window",
            }, family
            if family == "resolve_sequencing_order":
                option = pending["options"][0]
            else:
                (option,) = pending["options"]
            status = session.submit_viewer_option(
                viewer=viewer,
                request_id=pending["request_id"],
                option_id=option["option_id"],
                result_id=result_id,
            )
        assert status.status_kind not in {
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }
    raise AssertionError("Native volley did not finish.")


@pytest.mark.parametrize(
    ("target_wounds", "expected_target", "best"),
    [
        pytest.param(
            18,
            (Fraction(1650744790765, 293534171136), Fraction(15, 8)),
            "focused-witchfire",
            id="full",
        ),
        pytest.param(1, (1 - Fraction(19, 24) ** 9,) * 2, "witchfire", id="one-left"),
    ],
)
def test_bolt_profile_comparison_commits_and_replays(
    target_wounds: int, expected_target: tuple[Fraction, Fraction], best: str
) -> None:
    session, context = _shooting_session(target_wounds=target_wounds)
    admission = RangedProfileAdmission(context.observation_hash, TARGET)
    candidates = generate_ordinary_ranged_profile_candidates(context, admission=admission)
    assert tuple(c.profile_id for c in candidates) == (
        f"{BOLT}:focused-witchfire",
        f"{BOLT}:witchfire",
    )
    assert tuple(c.expected_target_wounds for c in candidates) == expected_target
    assert tuple(c.expected_hazardous_wounds for c in candidates) == (Fraction(1), Fraction())

    choice = next(c for c in candidates if c.profile_id == f"{BOLT}:{best}")
    proposals = [_proposal(candidate.action) for candidate in candidates]
    rows = [cast(list[JsonValue], proposal["declarations"])[0] for proposal in proposals]
    assert all(isinstance(row, dict) and row["target_unit_instance_id"] == TARGET for row in rows)
    focused_row, witchfire_row = (cast(dict[str, JsonValue], row) for row in rows)
    assert focused_row["weapon_instance_id"] == witchfire_row["weapon_instance_id"]
    initial = session.lifecycle.to_payload()
    before = session.decision_record_count()
    viewer = ViewerContext.for_player(ACTOR)

    duplicate = session.fork()
    status = duplicate.submit_viewer_parameterized_payload(
        viewer=viewer,
        request_id=context.request["request_id"],
        payload={**proposals[0], "declarations": rows},
        result_id="invalid-bolt-double-profile",
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert "duplicate_weapon_declaration" in repr(status.payload)
    assert duplicate.decision_record_count() == before

    # Check the otherwise unchosen single-profile action through native authority.
    other = next(candidate for candidate in candidates if candidate != choice)
    status = session.fork().submit_viewer_parameterized_payload(
        viewer=viewer,
        request_id=context.request["request_id"],
        payload=_proposal(other.action),
        result_id="legal-other-bolt-profile",
    )
    assert status.status_kind not in {LifecycleStatusKind.INVALID, LifecycleStatusKind.UNSUPPORTED}
    assert session.lifecycle.to_payload() == initial

    router = PolicyRouter(
        (
            ordinary_ranged_profile_registration(
                ACTOR,
                admission=admission,
                admitted_checkpoint_hash=payload_digest(session.to_persistence_payload()),
            ),
        )
    )
    with pytest.raises(RunnerError) as stopped:
        BoundedPolicyRunner(
            session=session,
            router=router,
            limits=RunLimits(policy_seed=7, max_decisions=1, max_seconds=120.0),
        ).run()
    assert stopped.value.report.failure_reason == "decision_limit"
    (attempt,) = stopped.value.report.decisions
    assert attempt.submission_outcome == "accepted"
    expected_rows = _proposal(choice.action)["declarations"]
    result = cast(
        dict[str, JsonValue], session.lifecycle.decision_controller.records[before].result.payload
    )
    assert result["declarations"] == expected_rows

    _finish_volley(session)
    events = session.lifecycle.decision_controller.event_log.records
    assert sum(event.event_type == "attack_sequence_completed" for event in events) == 1
    hits = [
        cast(dict[str, JsonValue], event.payload["payload"])
        for event in events
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload["step"] == "hit"
    ]
    assert len(hits) == 9
    assert all(roll["target_number"] == 2 and roll["capped_modifier"] == 0 for roll in hits)
    wounds = [
        cast(dict[str, JsonValue], event.payload["payload"])
        for event in events
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload["step"] == "wound"
    ]
    assert wounds
    assert all(roll["target_number"] == 4 and roll["capped_modifier"] == 0 for roll in wounds)
    saves = [
        cast(dict[str, JsonValue], event.payload["payload"])
        for event in events
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload["step"] == "save"
    ]
    actual_saves = [roll for roll in saves if roll["save_kind"] is not None]
    assert actual_saves
    for roll in actual_saves:
        unmodified = roll["unmodified_roll"]
        assert type(unmodified) is int
        assert roll["successful"] is (unmodified >= 4)
        options = cast(list[dict[str, JsonValue]], roll["save_options"])
        assert any(
            option["save_kind"] == "invulnerable" and option["target_number"] == 4
            for option in options
        )
        assert all(option["cover_applied"] is False for option in options)
    hazard_tests = [
        cast(dict[str, JsonValue], event.payload)
        for event in events
        if event.event_type == "hazardous_test_resolved"
    ]
    if best == "focused-witchfire":
        (hazard,) = hazard_tests
        assert hazard["hazardous_weapon_profile_ids"] == [choice.profile_id]
        assert hazard["mortal_wounds_per_failed_roll"] == 3
    else:
        assert not hazard_tests
    assert session.fork().lifecycle.to_payload() == session.lifecycle.to_payload()
    artifact = ReplayArtifact.capture(
        artifact_id="stage3-bolt-of-change",
        initial_lifecycle_payload=initial,
        final_lifecycle=session.lifecycle,
    )
    replay = ReplayRunner(ReplayArtifact.from_payload(artifact.to_payload())).run()
    assert replay.reproduced_exactly, replay.to_payload()


@pytest.mark.parametrize(
    ("shooter_wounds", "grant", "reason"),
    [
        pytest.param(7, "Ignores Cover", RangedProfileGapReason.SHOOTER, id="damaged"),
        pytest.param(18, "Lethal Hits", RangedProfileGapReason.PROFILE, id="lethal"),
        pytest.param(18, "Sustained Hits", RangedProfileGapReason.PROFILE, id="sustained"),
    ],
)
def test_unsupported_native_bolt_context_declines(
    shooter_wounds: int, grant: str, reason: RangedProfileGapReason
) -> None:
    _session, context = _shooting_session(
        target_wounds=18, shooter_wounds=shooter_wounds, grant=grant
    )
    with pytest.raises(RangedProfileGap) as gap:
        generate_ordinary_ranged_profile_candidates(
            context, admission=RangedProfileAdmission(context.observation_hash, TARGET)
        )
    assert gap.value.reason is reason


def test_bolt_profile_admission_blocks_unreviewed_contextual_modifier() -> None:
    admitted, context = _shooting_session(target_wounds=18)
    modified, modified_context = _shooting_session(target_wounds=18, wound_bonus=True)
    assert modified_context == context
    initial = modified.to_persistence_payload()
    with pytest.raises(PolicyError, match="own pending actor"):
        PlayerDecisionContext.from_view(modified.view(viewer_player_id=DEFENDER), choice_seed=7)
    entry = ordinary_ranged_profile_registration(
        ACTOR,
        admission=RangedProfileAdmission(context.observation_hash, TARGET),
        admitted_checkpoint_hash=payload_digest(admitted.to_persistence_payload()),
    )
    with pytest.raises(RunnerError) as blocked:
        BoundedPolicyRunner(
            session=modified,
            router=PolicyRouter((entry,)),
            limits=RunLimits(policy_seed=7, max_decisions=1, max_seconds=120.0),
        ).run()
    assert blocked.value.report.failure_reason == "unadmitted_checkpoint"
    (attempt,) = blocked.value.report.decisions
    assert attempt.submission_outcome == "not_submitted"
    assert modified.to_persistence_payload() == initial
