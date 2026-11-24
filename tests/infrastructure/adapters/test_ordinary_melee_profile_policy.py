"""Source-backed Great axe alternatives through the player Fight contract."""

from __future__ import annotations

import json
from dataclasses import replace
from fractions import Fraction
from typing import cast

import pytest

from tests.generic_modifier_helpers import generic_effect
from tests.phase15c_fight_order_helpers import (
    fight_config,
    record_fights_first_effect,
    unit_placement_at,
)
from tests.random_melee_helpers import melee_boundary
from tests.setup_completion_helpers import (
    record_current_battlefield_placements_for_fixture,
    record_primary_turn_start_evidence_for_fixture,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.ordinary_melee_profile_policy import (
    MeleeProfileAdmission,
    MeleeProfileGap,
    MeleeProfileGapReason,
    generate_ordinary_melee_profile_candidates,
    ordinary_melee_profile_registration,
)
from warhammer40k_core.ai.player_policy import (
    PlayerDecisionContext,
    PolicyError,
    PolicyRouter,
    payload_digest,
)
from warhammer40k_core.ai.runner import (
    BoundedPolicyRunner,
    PolicyCheckpointGap,
    RunLimits,
    RunnerError,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import muster_army
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.fight_order import FIGHTS_FIRST_EFFECT_KIND
from warhammer40k_core.engine.game_state import (
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatusKind
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_cavalcade_2026_11,
)

BLOODTHIRSTER = "000002582"
SEEKERS = "000001145"
GREAT_AXE = f"{BLOODTHIRSTER}:great-axe-of-khorne"
ACTOR = "player-a"
DEFENDER = "player-b"


def _fight_session(
    defender: str, *, wounded: bool = False, wound_bonus: bool = False
) -> LocalGameSession:
    package = chaos_daemons_cavalcade_2026_11.catalog_package()
    config = fight_config(
        game_id=f"stage3-profile-{defender}",
        alpha_unit_ids=("attacker",),
        enemy_unit_ids=("defender",),
        datasheet_id=BLOODTHIRSTER,
        model_profile_id=f"{BLOODTHIRSTER}:bloodthirster",
        model_count=1,
        alpha_faction_id="chaos-daemons",
        enemy_faction_id="chaos-daemons",
        alpha_detachment_ids=("cavalcade-of-chaos", "shadow-legion"),
        enemy_detachment_ids=("cavalcade-of-chaos", "shadow-legion"),
        catalog=package.army_catalog,
    )
    attacker_request, defender_request = config.army_muster_requests
    (selection,) = defender_request.unit_selections
    poses: tuple[Pose, ...] = (Pose.at(25, 20),)
    if defender == SEEKERS:
        selection = replace(
            selection,
            datasheet_id=SEEKERS,
            model_profile_selections=(
                ModelProfileSelection(f"{SEEKERS}:heartseeker", 1),
                ModelProfileSelection(f"{SEEKERS}:seekers", 4),
            ),
        )
        poses = (
            Pose.at(23.45, 20),
            Pose.at(25.90, 20),
            Pose.at(23.45, 21.65),
            Pose.at(25.90, 21.65),
            Pose.at(23.45, 23.30),
        )
    config = replace(
        config,
        army_muster_requests=(
            attacker_request,
            replace(defender_request, unit_selections=(selection,)),
        ),
        model_geometries=package.model_geometries,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="stage3-profile-fixture",
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
    for army, placement in zip(armies, ((Pose.at(20, 20),), poses), strict=True):
        (unit,) = army.units
        if wounded and army.player_id == DEFENDER:
            (model,) = unit.own_models
            unit = replace(unit, own_models=(replace(model, wounds_remaining=1),))
            army = replace(army, units=(unit,))
        state.record_army_definition(army)
        battlefield = battlefield.with_unit_placement(
            unit_placement_at(unit, army_id=army.army_id, player_id=army.player_id, poses=placement)
        )
    state.record_battlefield_state(battlefield)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.battle_round = 1
    state.active_player_id = ACTOR
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player, SecondaryMissionMode.FIXED, ("assassination", "bring_it_down")
            )
        )
    decisions = DecisionController()
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    record_fights_first_effect(
        state=state, unit=armies[0].units[0], effect_kind=FIGHTS_FIRST_EFFECT_KIND
    )
    if wound_bonus:
        effect = generic_effect(
            effect_id="stage3-contextual-wound-bonus",
            owner_player_id=ACTOR,
            target_unit_instance_ids=(armies[0].units[0].unit_instance_id,),
            target_kind="this_unit",
            effect_kind="modify_dice_roll",
            parameters={"roll_type": "wound", "delta": 1},
        )
        state.record_persisting_effect(
            replace(
                effect,
                started_phase=BattlePhase.FIGHT,
                expiration=EffectExpiration.end_phase(
                    battle_round=1, phase=BattlePhase.FIGHT, player_id=ACTOR
                ),
            )
        )
    return LocalGameSession(
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


def _actor_offer(
    session: LocalGameSession,
) -> tuple[PlayerDecisionContext, MeleeProfileAdmission]:
    context = PlayerDecisionContext.from_view(session.view(viewer_player_id=ACTOR), choice_seed=7)
    body = cast(dict[str, JsonValue], context.request["payload"])
    offer = cast(dict[str, JsonValue], body["proposal_request"])
    rows = cast(list[dict[str, JsonValue]], offer["available_weapons"])
    selection = cast(dict[str, JsonValue], rows[0]["weapon_ability_selection_context"])
    source_id = selection["source_request_id"]
    assert isinstance(source_id, str)
    assert source_id != offer["source_decision_result_id"]
    return context, MeleeProfileAdmission(context.observation_hash, source_id)


@pytest.mark.parametrize(
    ("defender", "expected", "best"),
    [
        pytest.param(SEEKERS, (6.389217063, 9.576614232), "sweep", id="seekers"),
        pytest.param(BLOODTHIRSTER, (10.036506171, 3.888885582), "strike", id="bloodthirster"),
    ],
)
def test_great_axe_actor_offer_selects_applied_wounds_and_replays(
    defender: str, expected: tuple[float, float], best: str
) -> None:
    session = _fight_session(defender)
    request = melee_boundary(session)
    assert request.decision_type == "submit_melee_declaration"
    assert request.actor_id == ACTOR
    context, admission = _actor_offer(session)
    candidates = generate_ordinary_melee_profile_candidates(context, admission=admission)
    assert tuple(candidate.profile_id for candidate in candidates) == (
        f"{GREAT_AXE}:strike",
        f"{GREAT_AXE}:sweep",
    )
    assert all(
        abs(float(candidate.expected_applied_wounds) - control) <= 1e-9
        for candidate, control in zip(candidates, expected, strict=True)
    )
    assert candidates[0].action != candidates[1].action
    assert all(c.action.observation_hash == context.observation_hash for c in candidates)

    with pytest.raises(PolicyError, match="own pending actor"):
        PlayerDecisionContext.from_view(session.view(viewer_player_id=DEFENDER), choice_seed=7)
    with pytest.raises(MeleeProfileGap) as refused:
        generate_ordinary_melee_profile_candidates(
            context, admission=replace(admission, observation_hash="0" * 64)
        )
    assert refused.value.reason is MeleeProfileGapReason.OBSERVATION

    with pytest.raises(MeleeProfileGap) as wrong_source:
        generate_ordinary_melee_profile_candidates(
            context, admission=replace(admission, weapon_selection_source_id=ACTOR)
        )
    assert wrong_source.value.reason is MeleeProfileGapReason.OFFER

    entry = ordinary_melee_profile_registration(
        ACTOR,
        admission=admission,
        admitted_checkpoint_hash=payload_digest(session.to_persistence_payload()),
    )
    action = PolicyRouter((entry,)).resolve(context.route).policy.choose(context)
    assert action == next(c.action for c in candidates if c.profile_id == f"{GREAT_AXE}:{best}")

    initial = session.lifecycle.to_payload()
    before = session.decision_record_count()
    for candidate in candidates:
        fork = session.fork()
        action = candidate.action
        assert action.proposal_json is not None
        payload = cast(dict[str, JsonValue], json.loads(action.proposal_json))
        status = fork.submit_viewer_parameterized_payload(
            viewer=ViewerContext.for_player(ACTOR),
            request_id=action.request_id,
            payload=payload,
            result_id=f"stage3:{candidate.profile_id}",
        )
        assert status.status_kind not in {
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }
        assert fork.decision_record_count() > before
        declaration = fork.lifecycle.decision_controller.records[before]
        assert declaration.request == request
        accepted = declaration.result.payload
        assert isinstance(accepted, dict)
        assert accepted["proposal_request_id"] == request.request_id
        assert accepted["declarations"] == payload["declarations"]
        if candidate.profile_id == f"{GREAT_AXE}:{best}":
            assert fork.fork().lifecycle.to_payload() == fork.lifecycle.to_payload()
            artifact = ReplayArtifact.capture(
                artifact_id="stage3-great-axe",
                initial_lifecycle_payload=initial,
                final_lifecycle=fork.lifecycle,
            )
            replay = ReplayRunner(ReplayArtifact.from_payload(artifact.to_payload())).run()
            assert replay.reproduced_exactly, replay.to_payload()
    assert session.lifecycle.to_payload() == initial


def test_great_axe_dispatch_rejects_identical_view_at_unadmitted_checkpoint() -> None:
    ordinary = _fight_session(BLOODTHIRSTER, wounded=True)
    modified = _fight_session(BLOODTHIRSTER, wounded=True, wound_bonus=True)
    ordinary_request = melee_boundary(ordinary)
    modified_request = melee_boundary(modified)
    assert (
        ordinary_request.decision_type
        == modified_request.decision_type
        == "submit_melee_declaration"
    )

    context, admission = _actor_offer(ordinary)
    assert (context, admission) == _actor_offer(modified)
    ordinary_checkpoint = payload_digest(ordinary.to_persistence_payload())
    modified_checkpoint = modified.to_persistence_payload()
    assert ordinary_checkpoint != payload_digest(modified_checkpoint)
    (strike, sweep) = generate_ordinary_melee_profile_candidates(context, admission=admission)
    assert (strike.profile_id, sweep.profile_id) == (f"{GREAT_AXE}:strike", f"{GREAT_AXE}:sweep")

    # One wound remains, so positive damage amounts all kill. Compute the
    # probability of at least one unsaved wound directly from D6 face counts.
    def kill_chance(attacks: int, wound_faces: int) -> Fraction:
        return 1 - (1 - Fraction(5, 6) * Fraction(wound_faces, 6) * Fraction(3, 6)) ** attacks

    assert strike.expected_applied_wounds == kill_chance(7, 4)
    assert sweep.expected_applied_wounds == kill_chance(14, 2)
    assert strike.expected_applied_wounds > sweep.expected_applied_wounds
    assert kill_chance(7, 5) < kill_chance(14, 3)

    router = PolicyRouter(
        (
            ordinary_melee_profile_registration(
                ACTOR, admission=admission, admitted_checkpoint_hash=ordinary_checkpoint
            ),
        )
    )
    limits = RunLimits(policy_seed=7, max_decisions=1, max_seconds=60.0)
    with pytest.raises(RunnerError) as gap:
        BoundedPolicyRunner(session=modified, router=router, limits=limits).run()
    assert isinstance(gap.value.__cause__, PolicyCheckpointGap)
    assert gap.value.report.failure_reason == "unadmitted_checkpoint"
    (blocked,) = gap.value.report.decisions
    assert blocked.failure_stage == "validation"
    assert blocked.choice_seconds == 0
    assert blocked.submission_outcome == "not_submitted"
    assert blocked.recorded_decisions == 0
    assert modified.to_persistence_payload() == modified_checkpoint

    ordinary_initial = ordinary.lifecycle.to_payload()
    modified_initial = modified.lifecycle.to_payload()
    before = ordinary.decision_record_count()
    direct = ordinary.fork()
    with pytest.raises(RunnerError) as stopped:
        BoundedPolicyRunner(session=ordinary, router=router, limits=limits).run()
    assert stopped.value.report.failure_reason == "decision_limit"
    (attempt,) = stopped.value.report.decisions
    assert attempt.submission_outcome == "accepted"
    assert attempt.observation_hash == blocked.observation_hash == context.observation_hash

    for session, action, result_id in (
        (direct, strike.action, f"ai:{attempt.choice_seed:064x}"),
        (modified, sweep.action, "stage3:modified-sweep"),
    ):
        assert action.proposal_json is not None
        status = session.submit_viewer_parameterized_payload(
            viewer=ViewerContext.for_player(ACTOR),
            request_id=action.request_id,
            payload=cast(dict[str, JsonValue], json.loads(action.proposal_json)),
            result_id=result_id,
        )
        assert status.status_kind in {
            LifecycleStatusKind.ADVANCED,
            LifecycleStatusKind.WAITING_FOR_DECISION,
            LifecycleStatusKind.TERMINAL,
        }
        if status.status_kind is LifecycleStatusKind.ADVANCED:
            session.advance_until_decision_or_terminal()

    assert ordinary.lifecycle.to_payload() == direct.lifecycle.to_payload()
    assert ordinary.lifecycle.decision_controller.records[before].request == ordinary_request
    for session, initial in ((ordinary, ordinary_initial), (modified, modified_initial)):
        artifact = ReplayArtifact.capture(
            artifact_id="stage3-checkpoint-admission",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        )
        replay = ReplayRunner(artifact).run()
        assert replay.reproduced_exactly, replay.to_payload()

    for session, expected_modifier in ((ordinary, 0), (modified, 1)):
        modifiers: set[int] = set()
        for event in session.lifecycle.decision_controller.event_log.records:
            if (
                event.event_type == "attack_sequence_step"
                and isinstance(event.payload, dict)
                and event.payload["step"] == "wound"
            ):
                roll = cast(dict[str, JsonValue], event.payload["payload"])
                modifier = roll["capped_modifier"]
                assert type(modifier) is int
                modifiers.add(modifier)
        assert modifiers == {expected_modifier}


def test_wounded_seeker_first_changes_applied_wound_expectation() -> None:
    from warhammer40k_core.ai.ordinary_melee_profile_policy import (
        _Defense,  # pyright: ignore[reportPrivateUsage]
        _expected_applied_wounds,  # pyright: ignore[reportPrivateUsage]
    )

    catalog = chaos_daemons_cavalcade_2026_11.catalog_package().army_catalog
    gear = next(gear for gear in catalog.wargear if gear.wargear_id == GREAT_AXE)
    strike, sweep = gear.weapon_profiles
    assert strike.attack_profile.fixed_attacks == 7
    assert strike.damage_profile.dice_expression is not None
    assert strike.damage_profile.dice_expression.canonical() == "D6+2"
    assert sweep.attack_profile.fixed_attacks == 14
    assert sweep.damage_profile.fixed_damage == 2
    defense = _Defense(toughness=4, armour=7, invulnerable=5, starting_wounds=2)
    expected = tuple(
        _expected_applied_wounds(profile, defense, (1, 2, 2, 2, 2))
        for profile in gear.weapon_profiles
    )
    assert all(isinstance(value, Fraction) for value in expected)
    strike_expected, sweep_expected = map(float, expected)
    assert abs(strike_expected - 5.402100438) <= 1e-9
    assert abs(sweep_expected - 8.576780213) <= 1e-9
