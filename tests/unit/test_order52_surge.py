from __future__ import annotations

import pytest
from tests.surge_helpers import SOURCE, TARGET, surge_descriptor, surge_lifecycle, surge_path

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementEligibleUnit,
    TriggeredMovementKind,
)
from warhammer40k_core.engine.triggered_movement_resolution import (
    resolve_triggered_movement,
)
from warhammer40k_core.engine.triggered_movement_selection import (
    triggered_movement_unit_selection_request,
)


def _session(
    lifecycle: GameLifecycle | None = None,
    *,
    source: str = SOURCE,
    kind: TriggeredMovementKind = TriggeredMovementKind.SURGE,
    reroll: bool = False,
) -> tuple[LocalGameSession, DecisionRequest]:
    from dataclasses import replace

    lifecycle = surge_lifecycle() if lifecycle is None else lifecycle
    state = lifecycle.state
    assert state is not None
    descriptor = replace(surge_descriptor(lifecycle=lifecycle), movement_kind=kind)
    eligible = TriggeredMovementEligibleUnit(source, "test:hook", descriptor.source_rule_id)
    if reroll:
        from warhammer40k_core.core.dice import (
            DiceExpression,
            DiceRollSpec,
            RerollComponentSelectionPolicy,
            RerollPermission,
        )
        from warhammer40k_core.engine.dice import DiceRollManager

        permission = RerollPermission(
            source_id=descriptor.source_rule_id,
            timing_window="after_surge_distance_roll",
            owning_player_id="player-a",
            eligible_roll_type="movement_end_surge.distance",
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        )
        roll = DiceRollManager(
            state.game_id, event_log=lifecycle.decision_controller.event_log
        ).roll(
            DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=6),
                reason="Source granted Surge distance",
                roll_type="movement_end_surge.distance",
                actor_id="player-a",
            )
        )
        descriptor = replace(descriptor, max_distance_inches=float(roll.current_total))
        eligible = replace(
            eligible, distance_roll_state=roll, distance_reroll_permission=permission
        )
    request = triggered_movement_unit_selection_request(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        descriptor=descriptor,
        eligible_units=(eligible,),
    )
    lifecycle.decision_controller.request_decision(request)
    session = LocalGameSession(lifecycle)
    session.advance_until_decision_or_terminal()
    return session, request


def _submit_path(
    session: LocalGameSession,
    request: DecisionRequest,
    distances: tuple[float, ...],
    result_id: str,
) -> LifecycleStatus:
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalPayload,
        MovementProposalRequest,
    )

    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=result_id,
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=proposal.unit_instance_id,
                movement_phase_action="surge_move",
                witness=surge_path(session.lifecycle, distances, unit_id=proposal.unit_instance_id),
            ).to_payload()
        ),
    )


def test_surge_facade_retry_restore_exact_replay_and_phase_lock() -> None:
    import json
    from typing import cast

    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
    from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
    from warhammer40k_core.engine.phase_movement_history import surge_locked
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

    session, request = _session()
    status = session.submit_option(
        request_id=request.request_id,
        result_id="select-surge",
        option_id=f"surge:{SOURCE}:target:{TARGET}",
    )
    assert status.decision_request is not None
    state = session.lifecycle.state
    assert state is not None
    original = state.battlefield_state
    status = _submit_path(session, status.decision_request, (3, 3, 3, 3, 1), "short-surge")
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == original
    assert state.phase_movement_history == []
    pending = session.lifecycle.decision_controller.queue.pending_requests[0]
    checkpoint = cast(GameLifecyclePayload, json.loads(json.dumps(session.lifecycle.to_payload())))
    restored = GameLifecycle.from_payload(checkpoint)
    assert restored.to_payload() == checkpoint
    _submit_path(session, pending, (3, 3, 3, 3, 3), "full-surge")
    assert len(state.phase_movement_history) == 1
    assert state.phase_movement_history[0].is_surge
    # The lifecycle may already have advanced. The recorded source occurrence
    # supplies the exact lock boundary, independently of the next pending phase.
    phase = state.current_battle_phase
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    assert surge_locked(state, SOURCE)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    assert not surge_locked(state, SOURCE)
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    assert not surge_locked(state, SOURCE)
    state.active_player_id = "player-a"
    assert phase is not None
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    artifact = session.replay_artifact(artifact_id="order52-surge")
    assert ReplayRunner.from_payload(artifact).run().status is ReplayRunStatus.REPRODUCED


def test_surge_requires_recorded_granting_trigger_before_offer() -> None:
    from warhammer40k_core.engine.phase import GameLifecycleError

    state = surge_lifecycle().state
    assert state is not None
    descriptor = surge_descriptor()
    with pytest.raises(GameLifecycleError, match="recorded trigger authority"):
        triggered_movement_unit_selection_request(
            state=state,
            player_id="player-a",
            descriptor=descriptor,
            eligible_units=(
                TriggeredMovementEligibleUnit(SOURCE, "hook", descriptor.source_rule_id),
            ),
        )


def test_prior_non_surge_move_prevents_surge_in_same_actual_player_phase() -> None:
    from warhammer40k_core.engine.phase import BattlePhase

    session, selection = _session(kind=TriggeredMovementKind.TRIGGERED)
    status = session.submit_option(
        request_id=selection.request_id,
        result_id="select-normal-reaction",
        option_id=f"triggered:{SOURCE}",
    )
    assert status.decision_request is not None
    _submit_path(session, status.decision_request, (1, 1, 1, 1, 1), "normal-reaction")
    state = session.lifecycle.state
    assert state is not None
    assert len(state.phase_movement_history) == 1
    assert not state.phase_movement_history[0].is_surge
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    descriptor = surge_descriptor(lifecycle=session.lifecycle)
    request = triggered_movement_unit_selection_request(
        state=state,
        decisions=session.lifecycle.decision_controller,
        player_id="player-a",
        descriptor=descriptor,
        eligible_units=(
            TriggeredMovementEligibleUnit(SOURCE, "test:hook", descriptor.source_rule_id),
        ),
    )
    assert [option.option_id for option in request.options] == ["decline_triggered_movement"]


def test_surge_target_survives_distance_reroll_and_checkpoint() -> None:
    from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE
    from warhammer40k_core.engine.movement_proposals import MovementProposalRequest

    session, selection = _session(reroll=True)
    status = session.submit_option(
        request_id=selection.request_id,
        result_id="select-rolled-surge",
        option_id=f"surge:{SOURCE}:target:{TARGET}",
    )
    reroll = status.decision_request
    assert reroll is not None
    assert reroll.decision_type == DICE_REROLL_DECISION_TYPE
    restored = GameLifecycle.from_payload(session.lifecycle.to_payload())
    assert restored.to_payload() == session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=reroll.request_id, result_id="surge-reroll", option_id="reroll:0"
    )
    assert status.decision_request is not None
    proposal = MovementProposalRequest.from_decision_request_payload(
        status.decision_request.payload
    )
    assert isinstance(proposal.context, dict)
    assert proposal.context["surge_target_unit_instance_id"] == TARGET
    restored = GameLifecycle.from_payload(session.lifecycle.to_payload())
    assert restored.to_payload() == session.lifecycle.to_payload()


def test_surge_reroll_revalidates_eligibility_before_consuming_dice() -> None:
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session, selection = _session(reroll=True)
    status = session.submit_option(
        request_id=selection.request_id,
        result_id="select-rolled-surge",
        option_id=f"surge:{SOURCE}:target:{TARGET}",
    )
    reroll = status.decision_request
    assert reroll is not None
    state = session.lifecycle.state
    assert state is not None
    state.battle_shocked_unit_ids.append(SOURCE)
    before = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=reroll.request_id, result_id="invalid-surge-reroll", option_id="reroll:0"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


def test_surge_public_target_is_projected_consistently_to_both_players() -> None:
    session, selection = _session()
    views = tuple(session.view(viewer_player_id=player) for player in ("player-a", "player-b"))
    for view in views:
        pending = view["pending_decision"]
        assert pending is not None
        assert pending["request_id"] == selection.request_id
        assert pending["actor_id"] == "player-a"
        assert {option["option_id"] for option in pending["options"]} == {
            "decline_triggered_movement",
            f"surge:{SOURCE}:target:{TARGET}",
        }
    status = session.submit_option(
        request_id=selection.request_id,
        result_id="public-surge-target",
        option_id=f"surge:{SOURCE}:target:{TARGET}",
    )
    assert status.decision_request is not None
    for player in ("player-a", "player-b"):
        proposal = session.view(viewer_player_id=player)["pending_proposal"]
        assert isinstance(proposal, dict)
        context = proposal["context"]
        assert isinstance(context, dict)
        assert context["surge_target_unit_instance_id"] == TARGET


def test_surge_rejects_changed_target_commitment_on_restore() -> None:
    import json
    from typing import cast

    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
    from warhammer40k_core.engine.phase import GameLifecycleError

    session, request = _session()
    session.submit_option(
        request_id=request.request_id,
        result_id="select-surge",
        option_id=f"surge:{SOURCE}:target:{TARGET}",
    )
    payload = cast(GameLifecyclePayload, json.loads(json.dumps(session.lifecycle.to_payload())))
    pending = payload["decisions"]["queue"]["pending_requests"][0]
    assert isinstance(pending["payload"], dict)
    proposal = pending["payload"]["proposal_request"]
    assert isinstance(proposal, dict)
    assert isinstance(proposal["context"], dict)
    proposal["context"]["surge_target_unit_instance_id"] = "invented-target"
    for event in payload["decisions"]["event_log"]:
        if (
            event["event_type"] == "decision_requested"
            and isinstance(event["payload"], dict)
            and event["payload"].get("request_id") == pending["request_id"]
        ):
            event["payload"] = validate_json_value(pending)
    with pytest.raises(GameLifecycleError, match="Surge target differs"):
        GameLifecycle.from_payload(payload)


def test_surge_finite_choice_commits_the_closest_target() -> None:
    lifecycle = surge_lifecycle()
    state = lifecycle.state
    assert state is not None
    descriptor = surge_descriptor(lifecycle=lifecycle)
    request = triggered_movement_unit_selection_request(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        descriptor=descriptor,
        eligible_units=(
            TriggeredMovementEligibleUnit(SOURCE, "test:hook", descriptor.source_rule_id),
        ),
    )
    choices = [
        option for option in request.options if option.option_id != "decline_triggered_movement"
    ]
    assert len(choices) == 1
    assert isinstance(choices[0].payload, dict)
    assert choices[0].payload["surge_target_unit_instance_id"] == TARGET


@pytest.mark.parametrize("distances", [(0, 0, 0, 0, 0), (3, 3, 3, 3, 1)])
def test_each_surge_model_must_make_maximum_approach(distances: tuple[float, ...]) -> None:
    lifecycle = surge_lifecycle()
    state = lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    resolution = resolve_triggered_movement(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=scenario.battlefield_state.unit_placement_by_id(SOURCE),
        descriptor=surge_descriptor(),
        path_witness=surge_path(lifecycle, distances),
        battle_round=1,
    )
    assert not resolution.is_valid


def test_battle_shocked_unit_is_not_offered_surge() -> None:
    lifecycle = surge_lifecycle()
    state = lifecycle.state
    assert state is not None
    state.battle_shocked_unit_ids.append(SOURCE)
    descriptor = surge_descriptor(lifecycle=lifecycle)
    request = triggered_movement_unit_selection_request(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        descriptor=descriptor,
        eligible_units=(
            TriggeredMovementEligibleUnit(SOURCE, "test:hook", descriptor.source_rule_id),
        ),
    )
    assert [option.option_id for option in request.options] == ["decline_triggered_movement"]


def test_tied_closest_enemies_are_explicit_finite_target_choices() -> None:
    from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses

    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.geometry.pose import Pose

    lifecycle, _ = charge_lifecycle(
        alpha_unit_ids=("source",),
        enemy_unit_ids=("enemy", "other", "far"),
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(10, 30), model_count=5),
        enemy_origins={"other": Pose.at(10, 10), "far": Pose.at(35, 35)},
        game_id="surge-ties",
    )
    assert lifecycle.state is not None
    lifecycle.state.battle_phase_index = lifecycle.state.battle_phase_sequence.index(
        BattlePhase.SHOOTING
    )
    _, request = _session(lifecycle)
    assert {option.option_id for option in request.options} == {
        "decline_triggered_movement",
        f"surge:{SOURCE}:target:{TARGET}",
        f"surge:{SOURCE}:target:army-beta:other",
    }


@pytest.mark.parametrize(("distance", "valid"), [(1.0, False), (3.0, True)])
def test_surge_engages_each_model_when_a_legal_path_reaches_target(
    distance: float, valid: bool
) -> None:
    lifecycle = surge_lifecycle(target_y=25)
    state = lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    resolution = resolve_triggered_movement(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=scenario.battlefield_state.unit_placement_by_id(SOURCE),
        descriptor=surge_descriptor(),
        path_witness=surge_path(lifecycle, (distance,) * 5),
        battle_round=1,
    )
    assert resolution.is_valid is valid
    if not valid:
        assert (
            resolution.restriction_violations[0].violation_code.value
            == "surge_engagement_not_reached"
        )


def test_surge_cannot_end_engaged_with_another_enemy() -> None:
    from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses

    from warhammer40k_core.geometry.pose import Pose

    lifecycle, _ = charge_lifecycle(
        alpha_unit_ids=("source",),
        enemy_unit_ids=("enemy", "other"),
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(10, 25), model_count=5),
        enemy_origins={"other": Pose.at(17, 25)},
        game_id="surge-nontarget",
    )
    state = lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    resolution = resolve_triggered_movement(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=scenario.battlefield_state.unit_placement_by_id(SOURCE),
        descriptor=surge_descriptor(),
        path_witness=surge_path(lifecycle, (3,) * 5),
        battle_round=1,
    )
    assert not resolution.is_valid
    assert "surge_non_target_engagement" in {
        row.violation_code.value for row in resolution.restriction_violations
    }


def test_surge_eligibility_drift_rejects_before_queue_pop() -> None:
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session, request = _session()
    state = session.lifecycle.state
    assert state is not None
    state.battle_shocked_unit_ids.append(SOURCE)
    before = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id,
        result_id="stale-surge",
        option_id=f"surge:{SOURCE}:target:{TARGET}",
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


def test_completed_surge_blocks_other_moves_and_second_surge() -> None:
    from dataclasses import replace

    from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
    from warhammer40k_core.engine.surge_movement import surge_ineligibility
    from warhammer40k_core.engine.triggered_movement import (
        TriggeredMovementHandler,
        TriggeredMovementKind,
    )
    from warhammer40k_core.geometry.pose import Pose

    session, request = _session()
    status = session.submit_option(
        request_id=request.request_id,
        result_id="lock-select",
        option_id=f"surge:{SOURCE}:target:{TARGET}",
    )
    assert status.decision_request is not None
    _submit_path(session, status.decision_request, (3,) * 5, "lock-path")
    state = session.lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    assert surge_ineligibility(state, SOURCE) == "surge_prior_move_this_phase"
    generic = replace(surge_descriptor(), movement_kind=TriggeredMovementKind.TRIGGERED)
    with pytest.raises(GameLifecycleError, match="surge_movement_locked_this_phase"):
        TriggeredMovementHandler(
            ruleset_descriptor=state.runtime_ruleset_descriptor()
        ).request_from_state(
            state=state,
            unit_instance_id=SOURCE,
            descriptor=generic,
            candidate_witnesses=(surge_path(session.lifecycle, (0,) * 5),),
        )
    assert state.battlefield_state is not None
    battlefield = state.battlefield_state
    placement = battlefield.unit_placement_by_id(SOURCE)
    moved = placement.with_model_placements(
        tuple(
            model.with_pose(Pose.at(model.pose.position.x, model.pose.position.y + 1))
            for model in placement.model_placements
        )
    )
    with pytest.raises(GameLifecycleError, match="surge_movement_locked_this_phase"):
        state.replace_battlefield_state(battlefield.with_unit_placement(moved))
    assert state.battlefield_state == battlefield


@pytest.mark.parametrize("tamper", ["phase_history", "endpoint_proof", "completion_target"])
def test_completed_surge_restore_rejects_corrupt_authority(tamper: str) -> None:
    import copy

    from warhammer40k_core.engine.phase import GameLifecycleError

    session, request = _session()
    status = session.submit_option(
        request_id=request.request_id,
        result_id="history-select",
        option_id=f"surge:{SOURCE}:target:{TARGET}",
    )
    assert status.decision_request is not None
    _submit_path(session, status.decision_request, (3,) * 5, "history-path")
    payload = copy.deepcopy(session.lifecycle.to_payload())
    assert GameLifecycle.from_payload(payload).to_payload() == payload
    if tamper == "phase_history":
        assert payload["state"] is not None
        payload["state"]["phase_movement_history"] = []
    else:
        event = next(
            event
            for event in payload["decisions"]["event_log"]
            if event["event_type"] == "triggered_movement_resolved"
        )
        assert isinstance(event["payload"], dict)
        if tamper == "completion_target":
            event["payload"]["surge_target_unit_instance_id"] = "invented"
        else:
            event["payload"]["surge_model_endpoints"] = []
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(payload)


def test_attached_surge_moves_and_locks_every_living_component() -> None:
    from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses

    from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
    from warhammer40k_core.engine.phase_movement_history import surge_locked
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.geometry.pose import Pose

    lifecycle, _ = charge_lifecycle(
        alpha_unit_ids=("source", "leader"),
        alpha_attached_unit_ids=("source", "leader"),
        alpha_origins={"source": Pose.at(10, 20), "leader": Pose.at(10, 21.8)},
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(10, 30), model_count=5),
        game_id="attached-surge",
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    view = rules_unit_view_by_id(state=state, unit_instance_id=SOURCE)
    session, request = _session(lifecycle, source=SOURCE)
    status = session.submit_option(
        request_id=request.request_id,
        result_id="attached-select",
        option_id=f"surge:{view.unit_instance_id}:target:{TARGET}",
    )
    assert status.decision_request is not None
    status = _submit_path(session, status.decision_request, (3,) * 6, "attached-path")
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert len(state.phase_movement_history[-1].model_instance_ids) == 6
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    assert surge_locked(state, SOURCE)
    assert surge_locked(state, "army-alpha:leader")


def test_surge_cannot_take_to_the_skies() -> None:
    from warhammer40k_core.engine.phase import GameLifecycleError

    lifecycle = surge_lifecycle()
    state = lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    with pytest.raises(GameLifecycleError, match="Surge cannot take to the skies"):
        resolve_triggered_movement(
            scenario=scenario,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            unit_placement=scenario.battlefield_state.unit_placement_by_id(SOURCE),
            descriptor=surge_descriptor(),
            path_witness=surge_path(lifecycle, (3,) * 5),
            battle_round=1,
            take_to_the_skies=True,
        )
