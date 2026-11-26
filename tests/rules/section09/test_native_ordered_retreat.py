"""Native Bloodletters force ordinary Fall Back through Battle-shock and its outcome."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from tests.daemons_native_source_helpers import SELECTED
from tests.support.blood_legion import DETACHMENTS, blood_legion_definitions
from tests.support.faction_batch01 import anchor, events, locate, request, scene, selection
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import grid
from tests.support.section09_fixtures import propose
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battle_shock import BattleShockResult, BattleShockResultPayload
from warhammer40k_core.engine.damage_allocation import (
    MortalWoundApplication,
    MortalWoundApplicationPayload,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mortal_wound_model_allocation import mortal_wound_resolution_progress
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
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
