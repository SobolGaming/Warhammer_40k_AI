"""Native Bloodletters force ordinary Fall Back through Battle-shock and its outcome."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from tests.daemons_native_source_helpers import SELECTED
from tests.support.blood_legion import DETACHMENTS, blood_legion_definitions
from tests.support.faction_batch01 import Scene, anchor, events, locate, request, scene, selection
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import grid
from tests.support.section09_fixtures import propose
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battle_shock import BattleShockResult, BattleShockResultPayload
from warhammer40k_core.engine.battle_shock_resolution import BattleShockResolutionResult
from warhammer40k_core.engine.damage_allocation import (
    MortalWoundApplication,
    MortalWoundApplicationPayload,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.engine.mortal_wound_model_allocation import mortal_wound_resolution_progress
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.replay import ReplayRunner
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pose import Pose

BLOODLETTERS = "000001114"
SPAWN = "000004090"
DAEMON_PRINCE = "000004086"
LORD = "000004078"
SUBJECT = "own:retreat"
FORCER = "foe:letters"
SPARE = "own:spare"
ORDINARY = "fall_back:ordered_retreat"
TERROR_APPLIED = "chaos_daemons_daemonic_terror_mortal_wounds_applied"


@pytest.fixture(scope="module")
def retreat_definitions(selected_army_source_index: Path | None) -> Section02Definitions:
    package = _ability_support_catalog_package(
        datasheet_ids=(*SELECTED, "000004080", SPAWN, DAEMON_PRINCE, LORD),
        source_index_dir=selected_army_source_index,
    )
    return blood_legion_definitions(Section02Definitions(package, 0.0))


def _restore(session: LocalGameSession) -> LocalGameSession:
    payload = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(payload)
    assert restored.to_persistence_payload() == payload
    return restored


def _choose(
    session: LocalGameSession,
    choice: DecisionRequest,
    option_id: str,
    result_id: str,
    next_kind: str,
) -> DecisionRequest:
    return request(
        session.submit_option(
            request_id=choice.request_id,
            option_id=option_id,
            result_id=result_id,
        ),
        next_kind,
    )


def _health(session: LocalGameSession) -> int:
    state = session.lifecycle.state
    assert state is not None
    return sum(
        model.current_wounds
        for model in rules_unit_view_by_id(state=state, unit_instance_id=SUBJECT).own_models
    )


def _positions(session: LocalGameSession) -> tuple[Pose, ...]:
    state = session.lifecycle.state
    assert state is not None
    battlefield = state.battlefield_state
    assert battlefield is not None
    return tuple(model.pose for model in battlefield.unit_placement_by_id(SUBJECT).model_placements)


@pytest.mark.parametrize("case", ["territorial-terror", "outside-shadow", "excluded-monster"])
def test_native_ordered_retreat_resolves_and_replays(
    retreat_definitions: Section02Definitions, case: str
) -> None:
    forced = case != "excluded-monster"
    terror = case == "territorial-terror"
    sheet = SPAWN if forced else DAEMON_PRINCE
    mode = "desperate_escape" if forced else "ordered_retreat"
    d = retreat_definitions
    battle = scene(
        d,
        (selection(d, sheet, "retreat"), selection(d, LORD, "spare")),
        (selection(d, BLOODLETTERS, "letters"),),
        detachment_id_by_faction=DETACHMENTS,
        seed=f"core-09-07-01-{mode}",
    )
    if terror:
        battle.state.battle_round = 2
    subject = battle.units[SUBJECT]
    x = 29 if case == "outside-shadow" else 10
    starts = grid(subject, x, 10)
    ends = tuple(Pose.at(p.position.x, p.position.y - 4) for p in starts)
    locate(battle, SUBJECT, starts)
    locate(battle, FORCER, grid(battle.units[FORCER], x, 12.3 if forced else 12.45))
    locate(battle, SPARE, (Pose.at(38 if case == "outside-shadow" else 30, 30),))
    anchor(battle)

    session = battle.session
    health_before = _health(session)
    pick = request(session.advance_until_decision_or_terminal(), "select_movement_unit")
    action = _choose(session, pick, SUBJECT, "audit-select", "select_movement_action")
    proposal = _choose(session, action, ORDINARY, "audit-fall-back", "submit_movement_proposal")
    context = MovementProposalRequest.from_decision_request_payload(proposal.payload).context
    assert context is not None
    assert context["source_selected_option_id"] == ORDINARY
    assert context["fall_back_mode"] == mode
    if forced:
        assert context["declared_fall_back_mode"] == "ordered_retreat"
        sources = cast(list[dict[str, JsonValue]], context["forced_desperate_escape_sources"])
        (source,) = sources
        assert source["source_kind"] == "catalog_rule_ir"
        assert source["ability_id"] == f"{BLOODLETTERS}:bane-of-cowards"
        assert source["forcing_unit_instance_id"] == FORCER
        assert source["fall_back_unit_instance_id"] == SUBJECT
        assert source["required_fall_back_mode"] == "desperate_escape"
    else:
        assert "forced_desperate_escape_sources" not in context

    restored = _restore(session)
    assert restored.lifecycle.pending_decision_request() == proposal
    for current, restore_outcome in ((session, False), (restored, True)):
        status = propose(current, proposal, subject, ends, result_id="audit-witness")
        hazards = events(current, "desperate_escape_roll_resolved")
        assert [row["model_instance_id"] for row in hazards] == (
            list(subject.own_model_ids()) if forced else []
        )
        tests = events(current, "forced_desperate_escape_battle_shock_resolved")
        assert len(tests) == int(forced)
        if forced:
            outcome = BattleShockResult.from_payload(
                cast(BattleShockResultPayload, tests[0]["battle_shock_result"])
            )
            assert not outcome.passed
            assert outcome.leadership_target == 7
            assert outcome.roll_state.current_total == (7 if terror else 6)
            assert outcome.total == 6
            assert [modifier.operand for modifier in outcome.modified_roll.modifiers] == (
                [-1] if terror else []
            )
        if terror:
            allocation = request(status, "select_mortal_wound_model")
            assert mortal_wound_resolution_progress(allocation).mortal_wounds == 2
            assert events(current, "movement_activation_completed") == []
            assert _health(current) == health_before
            assert _positions(current) == starts
            if restore_outcome:
                current = _restore(current)
                restored = current
                assert current.lifecycle.pending_decision_request() == allocation
            second = _choose(
                current,
                allocation,
                allocation.options[0].option_id,
                "allocate-terror-1",
                "select_mortal_wound_model",
            )
            progress = mortal_wound_resolution_progress(second)
            assert progress.remaining_mortal_wounds == 1
            assert progress.ignored_mortal_wounds == 1  # Native Spawn Feel No Pain.
            assert events(current, "movement_activation_completed") == []
            finished = _choose(
                current,
                second,
                second.options[0].option_id,
                "allocate-terror-2",
                "select_movement_unit",
            )
            (applied,) = events(current, TERROR_APPLIED)
            assert applied["target_unit_instance_id"] == SUBJECT
            assert applied["player_id"] == "opponent"
            damage = MortalWoundApplication.from_payload(
                cast(MortalWoundApplicationPayload, applied["mortal_wound_application"])
            )
            assert damage.mortal_wounds == 2
            assert damage.remaining_mortal_wounds_lost == 0
            assert _health(current) == health_before - (2 - damage.ignored_mortal_wounds)
        else:
            finished = request(status, "select_movement_unit")
            assert events(current, TERROR_APPLIED) == []
            assert _health(current) == health_before
        assert SPARE in {option.option_id for option in finished.options}
        assert SUBJECT not in {option.option_id for option in finished.options}
        (completed,) = events(current, "movement_activation_completed")
        assert completed["unit_instance_id"] == SUBJECT
        assert completed["fall_back_mode"] == mode
        assert _positions(current) == ends

    assert session.to_persistence_payload() == restored.to_persistence_payload()
    _restore(session)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id=case)).run()
    assert replay.reproduced_exactly, replay.to_payload()


def _select_review_retreat(
    session: LocalGameSession, unit_id: str, *, prefix: str = "audit"
) -> DecisionRequest:
    pick = request(session.advance_until_decision_or_terminal(), "select_movement_unit")
    action = _choose(session, pick, unit_id, f"{prefix}-select", "select_movement_action")
    return _choose(session, action, ORDINARY, f"{prefix}-fall-back", "submit_movement_proposal")


def _review_scene(d: Section02Definitions, *, two_retreats: bool) -> Scene:
    outside = (selection(d, SPAWN, "outside"),) if two_retreats else ()
    bodyguards = (selection(d, "000004080", "infractors"),) if two_retreats else ()
    outside_letters = (selection(d, BLOODLETTERS, "outside-letters"),) if two_retreats else ()
    battle = scene(
        d,
        (selection(d, SPAWN, "retreat"), *outside, selection(d, LORD, "spare"), *bodyguards),
        (selection(d, BLOODLETTERS, "letters"), *outside_letters),
        attachments=(AttachmentDeclaration("spare", "infractors"),) if two_retreats else (),
        detachment_id_by_faction=DETACHMENTS,
        seed="core-09-07-01-desperate_escape",
    )
    locate(battle, SUBJECT, grid(battle.units[SUBJECT], 10, 10))
    locate(battle, FORCER, grid(battle.units[FORCER], 10, 12.3))
    locate(battle, SPARE, (Pose.at(31, 35),))
    if two_retreats:
        locate(battle, "own:infractors", grid(battle.units["own:infractors"], 33, 35))
        locate(battle, "own:outside", grid(battle.units["own:outside"], 29, 10))
        locate(battle, "foe:outside-letters", grid(battle.units["foe:outside-letters"], 29, 12.3))
    else:
        battle.state.battle_round = 2
    anchor(battle)
    return battle


def test_second_forced_retreat_uses_only_territory_contributors(
    retreat_definitions: Section02Definitions,
) -> None:
    battle = _review_scene(retreat_definitions, two_retreats=True)
    session = battle.session
    first = _select_review_retreat(session, "own:outside")
    request(
        propose(
            session,
            first,
            battle.units["own:outside"],
            (Pose.at(29, 6), Pose.at(31, 6)),
            result_id="audit-witness",
        ),
        "select_movement_unit",
    )
    assert battle.state.battle_shocked_unit_ids == ["own:outside"]
    assert events(session, TERROR_APPLIED) == []
    second = _select_review_retreat(session, SUBJECT, prefix="second")
    restored = _restore(session)

    for current, restore_pending in ((session, False), (restored, True)):
        status = propose(
            current,
            second,
            battle.units[SUBJECT],
            (Pose.at(10, 6), Pose.at(12, 6)),
            result_id="second-witness",
        )
        allocation = request(status, "select_mortal_wound_model")
        progress = mortal_wound_resolution_progress(allocation)
        rolled_mortals = progress.mortal_wounds
        assert ":daemonic-terror:" in progress.application_id
        _, test = events(current, "forced_desperate_escape_battle_shock_resolved")
        result = BattleShockResult.from_payload(
            cast(BattleShockResultPayload, test["battle_shock_result"])
        )
        assert not result.passed
        assert [modifier.operand for modifier in result.modified_roll.modifiers] == [-1]
        assert _positions(current) == (Pose.at(10, 10), Pose.at(12, 10))
        if restore_pending:
            restored = current = _restore(current)
            assert current.lifecycle.pending_decision_request() == allocation
        for index in range(rolled_mortals):
            status = current.submit_option(
                request_id=allocation.request_id,
                option_id=allocation.options[0].option_id,
                result_id=f"second-allocate-{index}",
            )
            if index + 1 < rolled_mortals:
                allocation = request(status, "select_mortal_wound_model")
        hazard = request(status, "select_mortal_wound_model")
        hazard_progress = mortal_wound_resolution_progress(hazard)
        assert hazard_progress.application_id == f"desperate-escape:{second.request_id}:hazards"
        assert hazard_progress.mortal_wounds == 1
        _choose(
            current,
            hazard,
            hazard.options[0].option_id,
            "second-hazard",
            "select_movement_unit",
        )
        (applied,) = events(current, TERROR_APPLIED)
        assert applied["target_unit_instance_id"] == SUBJECT
        damage = MortalWoundApplication.from_payload(
            cast(MortalWoundApplicationPayload, applied["mortal_wound_application"])
        )
        assert damage.mortal_wounds == rolled_mortals
        completed = events(current, "movement_activation_completed")
        assert [row["unit_instance_id"] for row in completed] == ["own:outside", SUBJECT]
        assert _positions(current) == (Pose.at(10, 6), Pose.at(12, 6))

    assert session.to_persistence_payload() == restored.to_persistence_payload()
    _restore(session)
    replay = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="second-forced-escape")
    ).run()
    assert replay.reproduced_exactly, replay.to_payload()


def test_forced_escape_restore_rejects_invented_pretest_shock(
    retreat_definitions: Section02Definitions, monkeypatch: pytest.MonkeyPatch
) -> None:
    from warhammer40k_core.engine import battle_shock_modifier_continuation as continuation

    battle = _review_scene(retreat_definitions, two_retreats=False)
    session = battle.session
    proposal = _select_review_retreat(session, SUBJECT)
    resolve = continuation.resolve_battle_shock_after_modifier_choices

    def forge(**kwargs: Any) -> BattleShockResolutionResult:
        assert kwargs["phase_start_battle_shocked_unit_ids"] == ()
        kwargs["phase_start_battle_shocked_unit_ids"] = (FORCER,)
        return resolve(**kwargs)

    with monkeypatch.context() as patch:
        # Generate the linked records and roll through the real resolver with
        # an invented pre-test inventory. The actual Battle-shock history is intact.
        patch.setattr(continuation, "resolve_battle_shock_after_modifier_choices", forge)
        status = propose(
            session,
            proposal,
            battle.units[SUBJECT],
            (Pose.at(10, 6), Pose.at(12, 6)),
            result_id="audit-witness",
        )
    request(status, "select_movement_unit")
    (event,) = events(session, "forced_desperate_escape_battle_shock_resolved")
    result = BattleShockResult.from_payload(
        cast(BattleShockResultPayload, event["battle_shock_result"])
    )
    assert result.modified_roll.modifiers == ()
    assert result.total == 6
    assert events(session, TERROR_APPLIED) == []
    with pytest.raises(
        GameLifecycleError, match="Forced Desperate Escape pre-test Battle-shock state drifted"
    ):
        GameLifecycle.from_payload(json.loads(json.dumps(session.lifecycle.to_payload())))
