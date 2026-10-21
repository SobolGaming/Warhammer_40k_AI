"""03.03: cleanup destruction and retained source-correct owner-choice regression."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import CHAOS_SPAWN, INFRACTORS, Section02Definitions
from tests.support.section03_cleanup import apply_chosen_cleanup, chosen_cleanup
from tests.support.section03_fixtures import native_state, scenario
from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rule_model_destruction_unplaced import (
    destroy_end_turn_coherency_models,
)
from warhammer40k_core.engine.unit_coherency import unit_placement_coherency_result
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("chosen_index", [0, 1])
@pytest.mark.parametrize("turn_player", ["owner", "opponent"])
def test_cleanup_removal_is_destruction_without_destroyed_rule_trigger(
    section03_definitions: Section02Definitions, turn_player: str, chosen_index: int
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    state = native_state(section03_definitions, unit, (Pose.at(10, 10), Pose.at(20, 10)))
    state.active_player_id = turn_player
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    # Explicit post-choice contract: do not call D13's unchosen automatic boundary.
    decisions = DecisionController()
    chosen_id = unit.own_model_ids()[chosen_index]
    cleanup = chosen_cleanup(state, unit, chosen_id, decisions)
    before = state.to_payload()
    with pytest.raises(GameLifecycleError, match="authority drift"):
        destroy_end_turn_coherency_models(
            state=state,
            cleanup=replace(
                cleanup, removals=(replace(cleanup.removals[0], player_id="opponent"),)
            ),
        )
    assert state.to_payload() == before
    assert len(decisions.records) == 1
    assert decisions.records[0].request.actor_id == "owner"
    apply_chosen_cleanup(state, cleanup)
    assert cleanup.removed_model_instance_ids == (chosen_id,)
    assert len(cleanup.removals) == 1
    removed = cleanup.removals[0]
    assert removed.player_id == "owner"
    assert removed.removal_kind is BattlefieldRemovalKind.DESTROYED
    assert not removed.destroyed_model_rules_triggered
    assert not model_by_id(state=state, model_instance_id=removed.model_instance_id).is_alive
    board = scenario(state)
    assert unit_placement_coherency_result(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
    ).is_coherent
    with pytest.raises(AssertionError, match="once coherent"):
        chosen_cleanup(state, unit, unit.own_model_ids()[1 - chosen_index], decisions)
    assert len(decisions.records) == 1


@pytest.mark.parametrize("turn_player", ["owner", "opponent"])
def test_owner_must_choose_before_coherency_casualty_is_committed(
    section03_definitions: Section02Definitions, turn_player: str
) -> None:
    """SF03-001: neither legal casualty has been selected by its controlling player."""
    unit = section03_definitions.unit(CHAOS_SPAWN)
    state = native_state(section03_definitions, unit, (Pose.at(10, 10), Pose.at(20, 10)))
    state.active_player_id = turn_player
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    before = tuple(m.model_instance_id for m in unit.own_models if m.is_alive)
    state.resolve_end_turn_cleanup_boundary(completed_phase=BattlePhase.FIGHT)
    remaining = tuple(m for m in before if model_by_id(state=state, model_instance_id=m).is_alive)
    assert remaining == before, (
        "03.03 requires the controlling player's casualty choice; "
        "engine chose and killed a model without it"
    )


@pytest.mark.parametrize("turn_player", ["owner", "opponent"])
def test_multiple_cleanup_removals_are_separate_chosen_inputs_until_coherent(
    section03_definitions: Section02Definitions,
    turn_player: str,
) -> None:
    """Post-choice contract only; D13's missing native choice producer stays open."""
    unit = section03_definitions.unit(INFRACTORS)
    state = native_state(
        section03_definitions,
        unit,
        (Pose.at(10, 10), Pose.at(12, 10), Pose.at(14, 10), Pose.at(30, 10), Pose.at(40, 10)),
    )
    state.active_player_id = turn_player
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    decisions = DecisionController()
    for index in (4, 3):
        prior_ids = {
            row.model_instance_id
            for row in scenario(state)
            .battlefield_state.unit_placement_by_id(unit.unit_instance_id)
            .model_placements
        }
        cleanup = chosen_cleanup(state, unit, unit.own_model_ids()[index], decisions)
        assert {o.option_id for o in decisions.records[-1].request.options} == prior_ids
        assert all(model_by_id(state=state, model_instance_id=m).is_alive for m in prior_ids)
        apply_chosen_cleanup(state, cleanup)
        assert {
            row.model_instance_id
            for row in scenario(state)
            .battlefield_state.unit_placement_by_id(unit.unit_instance_id)
            .model_placements
        } == prior_ids - {unit.own_model_ids()[index]}
    board = scenario(state)
    assert unit_placement_coherency_result(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
    ).is_coherent
    with pytest.raises(AssertionError, match="once coherent"):
        chosen_cleanup(state, unit, unit.own_model_ids()[0], decisions)
    assert len(decisions.records) == 2


@pytest.mark.parametrize("turn_player", ["owner", "opponent"])
@pytest.mark.parametrize("chosen_index", [0, 1])
def test_native_owner_choice_applies_only_the_selected_casualty(
    section03_definitions: Section02Definitions,
    section03_cleanup_mission: MissionSetup,
    turn_player: str,
    chosen_index: int,
) -> None:
    from tests.support.section03_coherency_choices import cleanup_session, reach_cleanup
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = cleanup_session(
        section03_definitions, section03_cleanup_mission, turn_player=turn_player
    )
    state = session.lifecycle.state
    assert state is not None
    from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect

    # Explicit expiration contract; this effect grants no gameplay permission.
    effect = PersistingEffect(
        effect_id="sf03:expiry-control",
        source_rule_id="constructed:turn-end-expiry",
        owner_player_id="owner",
        target_unit_instance_ids=(state.army_definitions[-1].units[0].unit_instance_id,),
        started_battle_round=1,
        started_phase=BattlePhase.FIGHT,
        expiration=EffectExpiration.end_turn(battle_round=1, player_id=turn_player),
        effect_payload={"scope": "expiration control"},
    )
    state.record_persisting_effect(effect)
    request = reach_cleanup(session)
    assert effect in state.persisting_effects
    assert request.actor_id == "owner"
    model_ids = tuple(o.option_id for o in request.options)
    assert len(model_ids) == 2
    assert all(model_by_id(state=state, model_instance_id=m).is_alive for m in model_ids)
    chosen = model_ids[chosen_index]
    status = session.submit_option(
        request_id=request.request_id, result_id="chosen", option_id=chosen
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert not model_by_id(state=state, model_instance_id=chosen).is_alive
    assert model_by_id(state=state, model_instance_id=model_ids[1 - chosen_index]).is_alive
    assert sum(len(row.removals) for row in state.end_turn_cleanup_states) == 1
    assert sum(row.completes_boundary for row in state.end_turn_cleanup_states) == 1
    from typing import cast

    from warhammer40k_core.engine.turn_cleanup import EndTurnCleanupState

    casualty_step = next(row for row in state.end_turn_cleanup_states if row.removals)
    assert not casualty_step.completes_boundary
    invalid_marker = casualty_step.to_payload()
    invalid_marker["completes_boundary"] = cast(bool, "false")
    with pytest.raises(GameLifecycleError, match="completes_boundary must be a bool"):
        EndTurnCleanupState.from_payload(invalid_marker)
    assert effect not in state.persisting_effects
    assert not any(
        e.event_type == "model_destroyed"
        for e in session.lifecycle.decision_controller.event_log.records
    )


@pytest.mark.parametrize("turn_player", ["owner", "opponent"])
def test_native_all_models_are_legal_and_cleanup_rechecks_after_each_choice(
    section03_definitions: Section02Definitions,
    section03_cleanup_mission: MissionSetup,
    turn_player: str,
) -> None:
    from tests.support.section03_coherency_choices import cleanup_session, reach_cleanup

    unit = section03_definitions.unit(INFRACTORS)
    session = cleanup_session(
        section03_definitions,
        section03_cleanup_mission,
        turn_player=turn_player,
        unit=unit,
        poses=tuple(Pose.at(x, 10) for x in (10, 12, 14, 30, 40)),
    )
    state = session.lifecycle.state
    assert state is not None
    request = reach_cleanup(session)
    for index in (1, 4, 3, 2):
        assert request.actor_id == "owner"
        assert {o.option_id for o in request.options} == {
            m
            for m in unit.own_model_ids()
            if model_by_id(state=state, model_instance_id=m).is_alive
        }
        model_id = unit.own_model_ids()[index]
        assert model_by_id(state=state, model_instance_id=model_id).is_alive
        status = session.submit_option(
            request_id=request.request_id, result_id=f"remove-{index}", option_id=model_id
        )
        assert not model_by_id(state=state, model_instance_id=model_id).is_alive
        if index != 2:
            assert status.decision_request is not None
            request = status.decision_request
            assert request.decision_type == "select_coherency_casualty"
            assert not any(row.completes_boundary for row in state.end_turn_cleanup_states)
    assert model_by_id(state=state, model_instance_id=unit.own_model_ids()[0]).is_alive
    assert sum(len(row.removals) for row in state.end_turn_cleanup_states) == 4
    assert sum(row.completes_boundary for row in state.end_turn_cleanup_states) == 1


@pytest.mark.parametrize("invalid_kind", ["actor", "stale", "foreign", "payload", "geometry"])
def test_native_invalid_casualty_does_not_consume_choice_and_legal_retry_succeeds(
    section03_definitions: Section02Definitions,
    section03_cleanup_mission: MissionSetup,
    invalid_kind: str,
) -> None:
    from tests.support.section03_coherency_choices import cleanup_session, reach_cleanup
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = cleanup_session(section03_definitions, section03_cleanup_mission)
    request = reach_cleanup(session)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    result = DecisionResult.for_request(
        request=request, result_id="rejected", selected_option_id=request.options[0].option_id
    )
    original = state.battlefield_state
    if invalid_kind == "actor":
        result = replace(result, actor_id="opponent")
    elif invalid_kind == "stale":
        result = replace(result, request_id="stale")
    elif invalid_kind == "foreign":
        result = replace(result, selected_option_id="enemy:foreign")
    elif invalid_kind == "payload":
        result = replace(result, payload={"model_instance_id": "wrong"})
    else:
        placed = original.unit_placement_by_id(
            state.unit_instance_id_for_model(result.selected_option_id)
        )
        state.replace_battlefield_state(
            original.with_unit_placement(
                placed.with_model_placements(
                    tuple(
                        row.with_pose(Pose.at(25, 10))
                        if row.model_instance_id == result.selected_option_id
                        else row
                        for row in placed.model_placements
                    )
                )
            )
        )
    before_state = state.to_payload()
    before_decisions = session.lifecycle.decision_controller.to_payload()
    rejected = session.lifecycle.submit_decision(result)
    assert rejected.status_kind is LifecycleStatusKind.INVALID
    assert state.to_payload() == before_state
    assert session.lifecycle.decision_controller.to_payload() == before_decisions
    state.replace_battlefield_state(original)
    session.submit_option(
        request_id=request.request_id, result_id="accepted", option_id=request.options[0].option_id
    )
    assert not model_by_id(state=state, model_instance_id=request.options[0].option_id).is_alive


@pytest.mark.parametrize("turn_player", ["owner", "opponent"])
def test_native_pending_cleanup_restore_fork_alternative_continuation_and_exact_replay(
    section03_definitions: Section02Definitions,
    section03_cleanup_mission: MissionSetup,
    turn_player: str,
) -> None:
    import json

    from tests.support.section03_coherency_choices import casualty_checkpoint, reach_cleanup
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

    session = casualty_checkpoint(
        section03_definitions, section03_cleanup_mission, turn_player=turn_player
    )
    request = reach_cleanup(session)
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    from warhammer40k_core.engine.lifecycle import GameLifecycle

    invalid = json.loads(json.dumps(session.lifecycle.to_payload()))
    invalid["decisions"]["queue"]["pending_requests"][0]["actor_id"] = "opponent"
    with pytest.raises(GameLifecycleError, match="restored pending request drift"):
        GameLifecycle.from_payload(invalid)
    fork = session.fork()
    assert restored.to_persistence_payload() == checkpoint
    assert fork.to_persistence_payload() == checkpoint
    for viewer in ("owner", "opponent"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
    # The isolated last bearer is one legal choice; choosing the first connected
    # bearer instead requires further native choices and leaves a different unit.
    first, last = request.options[0].option_id, request.options[-1].option_id
    restored.submit_option(request_id=request.request_id, result_id="last", option_id=last)
    fork.submit_option(request_id=request.request_id, result_id="first", option_id=first)
    pending = fork.lifecycle.pending_decision_request()
    assert pending is not None
    assert pending.decision_type == "select_coherency_casualty"
    fork_checkpoint = json.loads(json.dumps(fork.to_persistence_payload()))
    fork = LocalGameSession.from_persistence_payload(fork_checkpoint)
    fork.submit_option(request_id=pending.request_id, result_id="then-last", option_id=last)
    for completed in (restored, fork):
        saved = json.loads(json.dumps(completed.to_persistence_payload()))
        assert LocalGameSession.from_persistence_payload(saved).to_persistence_payload() == saved
        assert ReplayRunner.from_payload(
            completed.replay_artifact(artifact_id="sf03")
        ).run().status is (ReplayRunStatus.REPRODUCED)
    state = session.lifecycle.state
    assert state is not None
    assert model_by_id(state=state, model_instance_id=first).is_alive
    assert model_by_id(state=state, model_instance_id=last).is_alive


@pytest.mark.parametrize("turn_player", ["owner", "opponent"])
def test_native_attached_casualty_choices_keep_physical_leader_ownership(
    section03_definitions: Section02Definitions,
    section03_cleanup_mission: MissionSetup,
    turn_player: str,
) -> None:
    from tests.support.section03_coherency_choices import cleanup_session, reach_cleanup
    from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies

    unit = section03_definitions.unit(INFRACTORS)
    session = cleanup_session(
        section03_definitions,
        section03_cleanup_mission,
        turn_player=turn_player,
        unit=unit,
        poses=tuple(Pose.at(x, 10) for x in (10, 12, 14, 16, 18)),
        leader_pose=Pose.at(30, 10),
    )
    state = session.lifecycle.state
    assert state is not None
    view = next(
        view
        for view in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
        if view.owner_player_id == "owner"
    )
    assert view.attached_unit is not None
    request = reach_cleanup(session)
    assert request.actor_id == "owner"
    assert {o.option_id for o in request.options} == {
        m.model_instance_id for m in view.alive_models()
    }
    from warhammer40k_core.engine.objective_control import ObjectiveControlTiming

    frozen = next(
        record
        for record in state.objective_control_records
        if record.timing is ObjectiveControlTiming.TURN_END
    )
    leader_id = view.attached_unit.leader_unit_instance_ids[0]
    leader_model_id = next(
        m.model_instance_id
        for c in view.components
        if c.unit.unit_instance_id == leader_id
        for m in c.unit.own_models
    )
    session.submit_option(
        request_id=request.request_id, result_id="leader-choice", option_id=leader_model_id
    )
    casualty = next(row.removals[0] for row in state.end_turn_cleanup_states if row.removals)
    assert casualty.unit_instance_id == leader_id
    assert casualty.model_instance_id == leader_model_id
    assert not casualty.destroyed_model_rules_triggered
    assert not model_by_id(state=state, model_instance_id=leader_model_id).is_alive
    assert all(model_by_id(state=state, model_instance_id=m).is_alive for m in unit.own_model_ids())
    assert frozen in state.objective_control_records
    from warhammer40k_core.engine.secondary_model_destruction_history import (
        secondary_model_destructions_for_boundary,
    )

    assert {
        model.model_instance_id
        for row in secondary_model_destructions_for_boundary(state=state, record=frozen)
        for model in row.destroyed_models
    } == {leader_model_id}


def test_native_attached_coherency_uses_leader_as_a_real_group_neighbor(
    section03_definitions: Section02Definitions,
    section03_cleanup_mission: MissionSetup,
) -> None:
    from tests.support.section03_coherency_choices import cleanup_session
    from warhammer40k_core.engine.coherency_cleanup_decisions import next_coherency_request

    unit = section03_definitions.unit(INFRACTORS)
    session = cleanup_session(
        section03_definitions,
        section03_cleanup_mission,
        unit=unit,
        poses=tuple(Pose.at(x, 10) for x in (10, 12, 14, 18, 20)),
        leader_pose=Pose.at(16, 10),
    )
    state = session.lifecycle.state
    assert state is not None
    board = scenario(state)
    assert not unit_placement_coherency_result(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
    ).is_coherent
    assert next_coherency_request(state=state) is None
    from tests.setup_completion_helpers import (
        ensure_army_mustered_events_for_fixture,
        record_current_battlefield_placements_for_fixture,
        record_primary_turn_start_evidence_for_fixture,
    )
    from warhammer40k_core.engine.lifecycle import GameLifecycle

    decisions = session.lifecycle.decision_controller
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    assert GameLifecycle.from_payload(session.lifecycle.to_payload()).state is not None


@pytest.mark.parametrize(
    ("gap", "vertical", "needs_choice"),
    [
        (1.999, 0.0, False),
        (2.0, 0.0, False),
        (2.001, 0.0, True),
        (2.0, 5.0, False),
        (2.0, 5.001, True),
    ],
)
def test_native_choice_discovery_preserves_exact_coherency_geometry(
    section03_definitions: Section02Definitions,
    gap: float,
    vertical: float,
    needs_choice: bool,
) -> None:
    from tests.support.section03_fixtures import geometry
    from warhammer40k_core.engine.coherency_cleanup_decisions import next_coherency_request
    from warhammer40k_core.geometry.base import CircularBase

    unit = section03_definitions.unit(CHAOS_SPAWN)
    first, second = geometry(unit, (Pose.at(10, 10), Pose.at(15, 10)))
    assert isinstance(first.base, CircularBase)
    assert isinstance(second.base, CircularBase)
    state = native_state(
        section03_definitions,
        unit,
        (
            first.pose,
            Pose.at(
                10 + first.base.radius + second.base.radius + gap,
                10,
                z=first.volume.height + vertical if vertical else 0,
            ),
        ),
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    request = next_coherency_request(state=state)
    assert (request is not None) is needs_choice
    if request is not None:
        assert {option.option_id for option in request.options} == set(unit.own_model_ids())


def test_native_ten_model_definition_rechecks_seven_to_six_survivor_boundary(
    section03_definitions: Section02Definitions,
    section03_cleanup_mission: MissionSetup,
) -> None:
    from tests.phase11c_command_phase_helpers import destroy_models_with_recorded_mortal_wounds
    from tests.support.section03_coherency_choices import cleanup_session, reach_cleanup
    from warhammer40k_core.engine.wargear_selections import ModelProfileSelection

    sheet = section03_definitions.package.army_catalog.datasheet_by_id(INFRACTORS)
    unit = section03_definitions.unit(
        INFRACTORS,
        composition=tuple(
            ModelProfileSelection(row.model_profile_id, row.max_models) for row in sheet.composition
        ),
    )
    assert len(unit.own_models) == 10
    # Explicit current-seven-survivor geometry contract over a native ten-model
    # definition. Existing recorded mortal-wound authority creates the casualties.
    session = cleanup_session(
        section03_definitions,
        section03_cleanup_mission,
        unit=unit,
        poses=tuple(Pose.at(10 + 2 * i, 10) for i in range(10)),
    )
    state = session.lifecycle.state
    assert state is not None
    destroy_models_with_recorded_mortal_wounds(
        state=state,
        decisions=session.lifecycle.decision_controller,
        unit_instance_id=unit.unit_instance_id,
        model_instance_ids=unit.own_model_ids()[7:],
        application_id="count-boundary",
        destroying_player_id="opponent",
    )
    request = reach_cleanup(session)
    assert len(request.options) == 7
    session.submit_option(
        request_id=request.request_id, result_id="seven-to-six", option_id=unit.own_model_ids()[6]
    )
    assert (
        sum(model_by_id(state=state, model_instance_id=m).is_alive for m in unit.own_model_ids())
        == 6
    )
    assert sum(len(row.removals) for row in state.end_turn_cleanup_states) == 1
    assert sum(row.completes_boundary for row in state.end_turn_cleanup_states) == 1


def test_owner_can_choose_from_either_of_two_broken_units(
    section03_definitions: Section02Definitions,
) -> None:
    from tests.support.section03_fixtures import placement
    from warhammer40k_core.engine.coherency_cleanup_decisions import next_coherency_request

    first = section03_definitions.unit(CHAOS_SPAWN)
    second = section03_definitions.unit(CHAOS_SPAWN, identity="second")
    state = native_state(section03_definitions, first, (Pose.at(10, 10), Pose.at(20, 10)))
    state.army_definitions[:] = [replace(state.army_definitions[0], units=(first, second))]
    assert state.battlefield_state is not None
    army = state.battlefield_state.placed_armies[0]
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=(
                replace(
                    army,
                    unit_placements=(
                        *army.unit_placements,
                        placement(second, (Pose.at(30, 10), Pose.at(40, 10))),
                    ),
                ),
            ),
        )
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    request = next_coherency_request(state=state)
    assert request is not None
    assert request.actor_id == "owner"
    assert {o.option_id for o in request.options} == {
        *first.own_model_ids(),
        *second.own_model_ids(),
    }
