"""Order 46: a roll, its current modified result and the move budget are distinct."""

from dataclasses import replace
from typing import cast

import pytest
from tests.generic_modifier_helpers import generic_effect
from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses

from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.charge_declaration import ChargeRollRequest
from warhammer40k_core.engine.charge_movement_budget import current_charge_movement_budget
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize(
    ("distances", "expected_violation"),
    [
        ((0.0, 1.4, 2.8, 4.0, 4.0), "charge_not_closer_to_target"),
        ((3.0, 4.0, 4.0, 4.0, 4.0), "charge_preferred_distance_not_reached"),
    ],
)
def test_order47_leading_model_cannot_satisfy_another_models_endpoint(
    distances: tuple[float, ...], expected_violation: str
) -> None:
    from tests.charge_distance_helpers import (
        NEW,
        SOURCE,
        charge_session,
        select_source,
        select_targets,
    )

    from warhammer40k_core.core.ruleset_descriptor import MovementMode
    from warhammer40k_core.engine.movement_proposals import ProposalKind
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
    from warhammer40k_core.geometry.pathing import PathWitness

    session = charge_session()
    request = select_targets(session, select_source(session), (NEW,))
    state = session.lifecycle.state
    assert state is not None
    before = state.battlefield_state
    assert before is not None
    placement = before.unit_placement_by_id(SOURCE)
    witness = PathWitness.for_paths(
        tuple(
            (
                model.model_instance_id,
                (model.pose, model.pose)
                if distance == 0
                else (
                    model.pose,
                    Pose.at(model.pose.position.x, model.pose.position.y + distance / 2),
                    Pose.at(model.pose.position.x, model.pose.position.y + distance),
                ),
            )
            for model, distance in zip(placement.model_placements, distances, strict=True)
        )
    )
    proposal = ChargeMoveProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        unit_instance_id=SOURCE,
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=(NEW,),
        witness=witness,
    )
    records_before = len(session.lifecycle.decision_controller.records)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order47-invalid-endpoint",
        payload=cast(JsonValue, proposal.to_payload()),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    assert status.payload["violation_code"] == expected_violation
    assert state.battlefield_state == before
    assert len(session.lifecycle.decision_controller.records) == records_before + 1
    pending = session.lifecycle.decision_controller.queue.pending_requests
    assert len(pending) == 1
    assert pending[0].request_id != request.request_id


@pytest.mark.parametrize(
    ("dice", "roll_delta", "distance_delta", "modified", "maximum"),
    [
        ((6, 6), 4, -2, 12, 10.0),
        ((1, 1), -5, -2, 1, 0.0),
        ((3, 4), 1, -2, 8, 6.0),
        ((6, 6), 4, 2.5, 12, 14.5),
    ],
)
def test_charge_budget_applies_move_effects_after_roll_bounds(
    dice: tuple[int, int],
    roll_delta: int,
    distance_delta: float,
    modified: int,
    maximum: float,
) -> None:
    lifecycle, units = charge_lifecycle(
        alpha_unit_ids=("source",),
        game_id="order46-budget",
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(20, 20), model_count=5),
    )
    state = lifecycle.state
    assert state is not None
    unit = units["source"]
    for effect_id, kind, parameters in (
        ("roll", "modify_dice_roll", {"roll_type": "charge", "delta": roll_delta}),
        ("distance", "modify_move_distance", {"delta": distance_delta}),
        (
            "movement-characteristic",
            "modify_characteristic",
            {"characteristic": "movement", "delta": 99},
        ),
    ):
        state.record_persisting_effect(
            generic_effect(
                effect_id=effect_id,
                owner_player_id="player-a",
                target_unit_instance_ids=(unit.unit_instance_id,),
                target_kind="this_unit",
                effect_kind=kind,
                parameters=cast(dict[str, JsonValue], parameters),
            )
        )
    request = ChargeRollRequest(
        request_id="roll",
        game_id=state.game_id,
        battle_round=1,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        source_decision_request_id="selection",
        source_decision_result_id="selected",
        roll_modifiers=(RollModifier(modifier_id="obsolete-snapshot", operand=50),),
    )
    roll = DiceRollManager(state.game_id).roll_fixed(request.spec, dice)
    budget = current_charge_movement_budget(
        state=state,
        request=request,
        roll_state=roll,
        ability_index=AbilityCatalogIndex.from_records(()),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert budget.modified_roll.unmodified.value == sum(dice)
    assert budget.modified_roll.final_value == modified
    assert budget.maximum_distance_inches == maximum
    assert request.roll_modifiers[0].modifier_id == "obsolete-snapshot"
    assert roll.current_values == dice
    assert budget == type(budget).from_payload(budget.to_payload())
    with pytest.raises(ValueError, match=r"budget|distance|trace"):
        replace(budget, maximum_distance_inches=maximum + 1)


def test_charge_targets_are_committed_before_movement_and_restore() -> None:
    from tests.charge_distance_helpers import (
        NEW,
        charge_session,
        move_payload,
        select_source,
        select_targets,
    )

    from warhammer40k_core.engine.lifecycle import GameLifecycle

    session = charge_session()
    request = select_source(session)
    assert request.decision_type == "select_charge_targets"
    checkpoint = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    request = select_targets(session, request, (NEW,))
    checkpoint = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order46-move",
        payload=move_payload(session, request),
    )
    assert status.decision_request is not None, status
    assert any(
        e.event_type == "charge_move_completed"
        for e in session.lifecycle.decision_controller.event_log.records
    )
    checkpoint = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint


@pytest.mark.parametrize("decline", [False, True])
def test_later_distance_reduction_replaces_targets_preserving_dice_and_replay(
    decline: bool,
) -> None:
    from tests.charge_distance_helpers import (
        NEW,
        OLD,
        add_modifier,
        charge_session,
        move_payload,
        request_from,
        select_source,
        select_targets,
    )

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
    from warhammer40k_core.engine.target_replacement import DECLINE_TARGET_REPLACEMENT_OPTION_ID

    session = charge_session()
    move_request = select_targets(session, select_source(session), (OLD,))
    state = session.lifecycle.state
    assert state is not None
    add_modifier(state, effect_id="later-distance-reduction", kind="modify_move_distance", delta=-6)
    before = session.lifecycle.to_payload()
    invalid = session.submit_parameterized_payload(
        request_id=move_request.request_id,
        result_id="order46-stale",
        payload=move_payload(session, move_request, target=OLD, dx=8, dy=0),
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    request = request_from(session.advance_until_decision_or_terminal())
    assert request.decision_type == "select_target_replacement"
    checkpoint = session.lifecycle.to_payload()
    initial = checkpoint
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(checkpoint))
    assert session.lifecycle.to_payload() == checkpoint
    if decline:
        session.submit_option(
            request_id=request.request_id,
            option_id=DECLINE_TARGET_REPLACEMENT_OPTION_ID,
            result_id="order46-decline",
        )
    else:
        request = select_targets(session, request, (NEW,), result_id="order46-replacement")
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="order46-new-move",
            payload=move_payload(session, request),
        )
        assert status.decision_request is not None, status
    events = session.lifecycle.decision_controller.event_log.records
    assert len([e for e in events if e.event_type == "charge_roll_resolved"]) == 1
    checkpoint = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    artifact = ReplayArtifact.capture(
        artifact_id="order46-replay",
        final_lifecycle=session.lifecycle,
        initial_lifecycle_payload=initial,
    )
    replay = ReplayRunner.from_payload(artifact.to_payload()).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


def test_budget_retains_exact_original_distance_terms() -> None:
    from tests.charge_distance_helpers import SOURCE, add_modifier, charge_session

    session = charge_session()
    state = session.lifecycle.state
    assert state is not None
    add_modifier(state, effect_id="decimal-a", kind="modify_move_distance", delta=0.1)
    add_modifier(state, effect_id="decimal-b", kind="modify_move_distance", delta=-0.2)
    request = ChargeRollRequest(
        request_id="decimal-roll",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=SOURCE,
        source_decision_request_id="source-request",
        source_decision_result_id="source-result",
    )
    dice = DiceRollManager(state.game_id).roll_fixed(request.spec, (6, 6))
    budget = current_charge_movement_budget(
        state=state,
        request=request,
        roll_state=dice,
        ability_index=AbilityCatalogIndex.from_records(()),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert tuple(row.delta_inches for row in budget.distance_modifiers) == (0.1, -0.2)
    assert budget.maximum_distance_inches == 11.9
    assert type(budget).from_payload(budget.to_payload()) == budget


@pytest.mark.parametrize("field", ["request_id", "result_id", "target_ids", "unit_instance_id"])
def test_restored_charge_targets_require_the_exact_recorded_choice(field: str) -> None:
    from tests.charge_distance_helpers import NEW, charge_session, select_source, select_targets

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = charge_session()
    select_targets(session, select_source(session), (NEW,))
    payload = session.lifecycle.to_payload()
    phase = payload["state"]["charge_phase_state"]
    assert phase is not None
    selection = phase["target_selection"]
    assert selection is not None
    selection[field] = ["invented-target"] if field == "target_ids" else "invented"
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize("reduction", [-6, -12])
def test_unreachable_required_target_fails_charge_continuation(reduction: int) -> None:
    """R46-001: no legal target set must finish the action without an empty decision."""
    from tests.charge_distance_helpers import (
        OLD,
        SOURCE,
        add_modifier,
        charge_session,
        request_from,
        select_source,
    )
    from tests.support.selected_target_charge_fixtures import (
        selected_target_charge_persisting_effect,
    )

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = charge_session()
    request = select_source(session)
    state = session.lifecycle.state
    assert state is not None
    state.record_persisting_effect(
        selected_target_charge_persisting_effect(
            state=state,
            effect_id="required-original-target",
            owner_player_id="player-a",
            source_rules_unit_instance_id=SOURCE,
            source_component_unit_instance_id=SOURCE,
            selected_target_unit_instance_id=OLD,
        )
    )
    add_modifier(
        state, effect_id="unreachable-target", kind="modify_move_distance", delta=reduction
    )
    before = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="stale-required-target",
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    next_request = request_from(session.advance_until_decision_or_terminal())
    assert next_request.request_id != request.request_id
    assert next_request.decision_type == "select_charging_unit"
    assert SOURCE not in {option.option_id for option in next_request.options}
    phase = state.charge_phase_state
    assert phase is not None
    assert phase.active_selection is None
    assert phase.target_selection is None
    assert phase.declared_target_unit_instance_ids_by_unit[SOURCE] == ()
    assert (
        session.lifecycle.to_payload()["state"]["battlefield_state"]
        == before["state"]["battlefield_state"]
    )
    events = session.lifecycle.decision_controller.event_log.records
    assert sum(e.event_type == "charge_roll_resolved" for e in events) == 1
    assert sum(e.event_type == "charge_continuation_failed" for e in events) == 1
    failure = next(e.payload for e in events if e.event_type == "charge_continuation_failed")
    assert isinstance(failure, dict)
    assert failure["reason"] == "no_legal_charge_target_sets"
    assert isinstance(request.payload, dict)
    assert failure["charge_roll"] == request.payload["charge_roll"]
    budget = failure["movement_budget"]
    assert isinstance(budget, dict)
    assert budget["maximum_distance_inches"] == 12 + reduction
    assert not any(e.event_type == "charge_move_completed" for e in events)
    checkpoint = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    assert request_from(session.advance_until_decision_or_terminal()) == next_request


@pytest.mark.parametrize("pending_kind", ["movement", "replacement", "none"])
def test_restore_rejects_erased_charge_target_commitment(pending_kind: str) -> None:
    """R46-002: absence must agree with historical and pending action authority."""
    from tests.charge_distance_helpers import (
        OLD,
        add_modifier,
        charge_session,
        select_source,
        select_targets,
    )

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = charge_session()
    select_targets(session, select_source(session), (OLD,))
    if pending_kind == "replacement":
        state = session.lifecycle.state
        assert state is not None
        add_modifier(state, effect_id="replacement-pending", kind="modify_move_distance", delta=-6)
        session.advance_until_decision_or_terminal()
    payload = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(payload).to_payload() == payload
    phase = payload["state"]["charge_phase_state"]
    assert phase is not None
    phase["target_selection"] = None
    if pending_kind == "none":
        payload["decisions"]["queue"]["pending_requests"] = []
    with pytest.raises(GameLifecycleError, match=r"Charge.*target.*commitment"):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize("field", ["target_selection", "charge_roll"])
def test_restore_reconciles_pending_charge_movement_authority(field: str) -> None:
    from tests.charge_distance_helpers import NEW, charge_session, select_source, select_targets

    from warhammer40k_core.engine.charge_target_authority import validate_restored_charge_targets
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = charge_session()
    select_targets(session, select_source(session), (NEW,))
    payload = session.lifecycle.to_payload()
    request = payload["decisions"]["queue"]["pending_requests"][0]
    request_payload = request["payload"]
    assert isinstance(request_payload, dict)
    proposal = request_payload["proposal_request"]
    assert isinstance(proposal, dict)
    context = proposal["context"]
    assert isinstance(context, dict)
    context[field] = None
    state = session.lifecycle.state
    assert state is not None
    with pytest.raises(
        GameLifecycleError, match="Charge movement target commitment authority drift"
    ):
        validate_restored_charge_targets(
            state=state,
            decisions=DecisionController.from_payload(payload["decisions"]),
            handler=session.lifecycle._charge_phase_handler,  # pyright: ignore[reportPrivateUsage]
        )
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(payload)


def test_path_cannot_change_committed_targets_and_views_redact_authority_hash() -> None:
    import json

    from tests.charge_distance_helpers import (
        NEW,
        OLD,
        charge_session,
        move_payload,
        select_source,
        select_targets,
    )

    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = charge_session()
    target_request = select_source(session)
    for viewer in ("player-a", "player-b"):
        projection = json.dumps(session.view(viewer_player_id=viewer), sort_keys=True)
        assert "charge_target_authority_sha256" not in projection
        events = json.dumps(session.events_since(EventStreamCursor(), viewer_player_id=viewer))
        assert "charge_target_authority_sha256" not in events
    request = select_targets(session, target_request, (NEW,))
    for viewer in ("player-a", "player-b"):
        events = json.dumps(session.events_since(EventStreamCursor(), viewer_player_id=viewer))
        assert "charge_targets_selected" in events
        assert "charge_target_authority_sha256" not in events
    before = session.lifecycle.to_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="wrong-target",
        payload=move_payload(session, request, target=OLD, dx=8, dy=0),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


def test_budget_increase_refreshes_path_without_reselecting_or_rerolling() -> None:
    from tests.charge_distance_helpers import (
        NEW,
        add_modifier,
        charge_session,
        move_payload,
        request_from,
        select_source,
        select_targets,
    )

    from warhammer40k_core.engine.movement_proposals import MovementProposalRequest

    session = charge_session()
    request = select_targets(session, select_source(session), (NEW,))
    state = session.lifecycle.state
    assert state is not None
    phase = state.charge_phase_state
    assert phase is not None
    selection = phase.target_selection
    add_modifier(state, effect_id="longer-charge-move", kind="modify_move_distance", delta=2.5)
    refreshed = request_from(session.advance_until_decision_or_terminal())
    assert refreshed.request_id != request.request_id
    proposal = MovementProposalRequest.from_decision_request_payload(refreshed.payload)
    assert proposal.context is not None
    assert proposal.context["maximum_distance_inches"] == 14.5
    assert state.charge_phase_state is not None
    assert state.charge_phase_state.target_selection == selection
    session.submit_parameterized_payload(
        request_id=refreshed.request_id,
        result_id="longer-move",
        payload=move_payload(session, refreshed),
    )
    events = session.lifecycle.decision_controller.event_log.records
    assert len([e for e in events if e.event_type == "charge_roll_resolved"]) == 1
    assert len([e for e in events if e.event_type == "charge_targets_selected"]) == 1
    assert any(e.event_type == "charge_move_completed" for e in events)


def test_later_roll_modifier_reuses_dice_and_offers_only_decline_when_nothing_is_reachable() -> (
    None
):
    from tests.charge_distance_helpers import (
        NEW,
        add_modifier,
        charge_session,
        request_from,
        select_source,
        select_targets,
    )

    from warhammer40k_core.engine.target_replacement import DECLINE_TARGET_REPLACEMENT_OPTION_ID

    session = charge_session()
    select_targets(session, select_source(session), (NEW,))
    state = session.lifecycle.state
    assert state is not None
    phase = state.charge_phase_state
    assert phase is not None
    before = phase.distance_states
    add_modifier(state, effect_id="later-roll-penalty", kind="modify_dice_roll", delta=-30)
    request = request_from(session.advance_until_decision_or_terminal())
    assert request.decision_type == "select_target_replacement"
    assert [o.option_id for o in request.options] == [DECLINE_TARGET_REPLACEMENT_OPTION_ID]
    assert state.charge_phase_state is not None
    assert state.charge_phase_state.distance_states == before
    session.submit_option(
        request_id=request.request_id,
        result_id="nothing-reachable",
        option_id=DECLINE_TARGET_REPLACEMENT_OPTION_ID,
    )
    assert not any(
        e.event_type == "charge_move_completed"
        for e in session.lifecycle.decision_controller.event_log.records
    )


@pytest.mark.parametrize(
    "mutation", ["remove", "source", "nested-extra", "maximum", "distance-source", "nonfinite"]
)
def test_movement_budget_payload_rejects_missing_or_forged_provenance(mutation: str) -> None:
    from warhammer40k_core.engine.charge_budget_value import (
        ChargeMoveDistanceModifier,
        ChargeMovementBudget,
    )
    from warhammer40k_core.engine.phase import GameLifecycleError

    request = ChargeRollRequest(
        request_id="budget",
        game_id="budget-game",
        battle_round=1,
        player_id="player-a",
        unit_instance_id="source",
        source_decision_request_id="selection",
        source_decision_result_id="selected",
    )
    roll = DiceRollManager("budget-game").roll_fixed(request.spec, (3, 4))
    budget = ChargeMovementBudget(
        request.resolve_roll(roll),
        (ChargeMoveDistanceModifier("move-effect", "source:rule", -2.0),),
        5.0,
    )
    payload = cast(dict[str, object], budget.to_payload())
    if mutation == "remove":
        del payload["modified_roll"]
    elif mutation == "source":
        payload["unknown_source"] = "invented"
    elif mutation == "nested-extra":
        cast(dict[str, object], payload["modified_roll"])["unknown"] = True
    elif mutation == "maximum":
        payload["maximum_distance_inches"] = 12.0
    else:
        row = cast(list[dict[str, object]], payload["distance_modifiers"])[0]
        row["source_id" if mutation == "distance-source" else "delta_inches"] = (
            "" if mutation == "distance-source" else float("nan")
        )
    with pytest.raises(GameLifecycleError):
        ChargeMovementBudget.from_payload(payload)


def test_target_choice_drift_rejects_then_refreshes_without_rolling_again() -> None:
    from tests.charge_distance_helpers import (
        NEW,
        OLD,
        add_modifier,
        charge_session,
        request_from,
        select_source,
        select_targets,
    )

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = charge_session()
    request = select_source(session)
    old_option = next(
        o
        for o in request.options
        if isinstance(o.payload, dict) and o.payload["target_ids"] == [OLD]
    )
    state = session.lifecycle.state
    assert state is not None
    add_modifier(state, effect_id="before-targets", kind="modify_move_distance", delta=-6)
    before = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id, option_id=old_option.option_id, result_id="stale-targets"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    refreshed = request_from(session.advance_until_decision_or_terminal())
    assert refreshed.decision_type == "select_charge_targets"
    assert refreshed.request_id != request.request_id
    assert all(
        isinstance(o.payload, dict) and o.payload["target_ids"] != [OLD] for o in refreshed.options
    )
    checkpoint = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    select_targets(session, refreshed, (NEW,))
    assert (
        sum(
            e.event_type == "charge_roll_resolved"
            for e in session.lifecycle.decision_controller.event_log.records
        )
        == 1
    )


def test_replacement_history_requires_its_charge_selection_mutation() -> None:
    from tests.charge_distance_helpers import (
        NEW,
        OLD,
        add_modifier,
        charge_session,
        request_from,
        select_source,
        select_targets,
    )

    from warhammer40k_core.engine.charge_target_authority import charge_selection_history
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = charge_session()
    select_targets(session, select_source(session), (OLD,))
    state = session.lifecycle.state
    assert state is not None
    add_modifier(state, effect_id="history-reduction", kind="modify_move_distance", delta=-6)
    request = request_from(session.advance_until_decision_or_terminal())
    select_targets(session, request, (NEW,), result_id="replacement-history")
    decisions = session.lifecycle.decision_controller
    events = tuple(
        e
        for e in decisions.event_log.records
        if not (
            e.event_type == "charge_targets_selected"
            and isinstance(e.payload, dict)
            and e.payload["result_id"] == "replacement-history"
        )
    )
    with pytest.raises(GameLifecycleError, match="history is incomplete"):
        charge_selection_history(event_records=events, decision_records=decisions.records)


def test_larger_movement_budget_preserves_the_separate_twelve_inch_target_gate() -> None:
    from tests.charge_distance_helpers import (
        OLD,
        SOURCE,
        add_modifier,
        charge_session,
        select_source,
    )

    from warhammer40k_core.engine.charge_targets import charge_target_candidates

    session = charge_session(old_origin=Pose.at(30, 20))
    state = session.lifecycle.state
    assert state is not None
    add_modifier(state, effect_id="long-distance", kind="modify_move_distance", delta=2.5)
    target = next(
        candidate
        for candidate in charge_target_candidates(
            state=state,
            unit_instance_id=SOURCE,
            ruleset_descriptor=session.lifecycle.config.ruleset_descriptor,
        )
        if candidate.target_unit_instance_id == OLD
    )
    assert 12 < target.closest_distance_inches <= 14.5
    request = select_source(session)
    assert isinstance(request.payload, dict)
    budget = request.payload["movement_budget"]
    assert isinstance(budget, dict)
    assert budget["maximum_distance_inches"] == 14.5
    for option in request.options:
        assert isinstance(option.payload, dict)
        targets = option.payload["target_ids"]
        assert targets is None or isinstance(targets, list)
        assert targets is None or OLD not in targets


@pytest.mark.parametrize("decline", [False, True])
def test_shooting_interruption_in_charge_keeps_its_replacement_owner(decline: bool) -> None:
    from tests.charge_distance_helpers import request_from
    from tests.target_replacement_helpers import replacement_scene

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
    from warhammer40k_core.engine.shooting_target_replacement_authority import (
        validate_restored_replacements,
    )
    from warhammer40k_core.engine.target_replacement import DECLINE_TARGET_REPLACEMENT_OPTION_ID

    lifecycle, units, request = replacement_scene(mode="charge_interrupt")
    session = LocalGameSession(lifecycle=lifecycle)
    request = request_from(
        session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id="order46:interrupted-resolution",
        )
    )
    assert request.decision_type == "select_target_replacement"
    checkpoint = session.lifecycle.to_payload()
    state = lifecycle.state
    assert state is not None
    validate_restored_replacements(
        state=state,
        decisions=lifecycle.decision_controller,
        handler=lifecycle._shooting_phase_handler,  # pyright: ignore[reportPrivateUsage]
    )
    assert session.lifecycle.to_payload() == checkpoint
    option_id = (
        DECLINE_TARGET_REPLACEMENT_OPTION_ID
        if decline
        else f"target:{units['new'].unit_instance_id}"
    )
    status = session.submit_option(
        request_id=request.request_id,
        option_id=option_id,
        result_id="order46:interrupted-replacement",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    state = session.lifecycle.state
    assert state is not None
    assert state.current_battle_phase is BattlePhase.CHARGE
    assert not any(
        e.event_type == "charge_targets_selected"
        for e in session.lifecycle.decision_controller.event_log.records
    )
    validate_restored_replacements(
        state=state,
        decisions=lifecycle.decision_controller,
        handler=lifecycle._shooting_phase_handler,  # pyright: ignore[reportPrivateUsage]
    )


def test_order47_attached_charger_is_one_canonical_choice() -> None:
    from warhammer40k_core.adapters.local_session import LocalGameSession

    lifecycle, units = charge_lifecycle(
        alpha_unit_ids=("source", "leader", "next"),
        alpha_attached_unit_ids=("source", "leader"),
        alpha_origins={"leader": Pose.at(17, 20)},
        game_id="order47-attached",
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(10, 26), model_count=5),
    )
    request = LocalGameSession(lifecycle).advance_until_decision_or_terminal().decision_request
    assert request is not None
    ids = {option.option_id for option in request.options}
    assert "attached-unit:army-alpha:source" in ids
    assert units["source"].unit_instance_id not in ids
    assert units["leader"].unit_instance_id not in ids


def test_order47_attached_charge_moves_all_components_atomically_and_replays() -> None:
    from tests.charge_distance_helpers import select_targets
    from tests.charge_endpoint_helpers import (
        ATTACHED_SOURCE,
        ATTACHED_TARGET,
        attached_charge_session,
        attached_move_payload,
        select_attached_source,
    )

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus

    session = attached_charge_session()
    session.advance_until_decision_or_terminal()
    initial = session.lifecycle.to_payload()
    request = select_targets(session, select_attached_source(session), (ATTACHED_TARGET,))
    checkpoint = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    payload = attached_move_payload(session, request)
    session.submit_parameterized_payload(
        request_id=request.request_id, result_id="order47-attached-move", payload=payload
    )
    event = next(
        e
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "charge_move_completed"
    )
    assert isinstance(event.payload, dict)
    assert event.payload["unit_instance_id"] == ATTACHED_SOURCE
    endpoints = cast(dict[str, JsonValue], event.payload["endpoint_witness"])
    rows = cast(list[dict[str, JsonValue]], endpoints["model_endpoints"])
    assert len(rows) == 6
    assert {cast(str, r["component_unit_instance_id"]) for r in rows} == {
        "army-alpha:source",
        "army-alpha:leader",
    }
    final = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(final).to_payload() == final
    artifact = ReplayArtifact.capture(
        artifact_id="order47-attached-replay",
        final_lifecycle=session.lifecycle,
        initial_lifecycle_payload=initial,
    )
    replay = ReplayRunner.from_payload(artifact.to_payload()).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


def test_order47_each_model_must_engage_when_a_legal_path_exists() -> None:
    from tests.charge_endpoint_helpers import endpoint_resolution

    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor

    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    ruleset = replace(
        ruleset,
        descriptor_hash="",
        charge_policy=replace(
            ruleset.charge_policy,
            must_reach_preferred_target_distance_if_possible=False,
        ),
    )
    result = endpoint_resolution(distances=(2, 4, 4, 4, 4), ruleset=ruleset)
    assert result.endpoint_violation_code == "charge_model_not_engaged_target"
    trailing = result.endpoint_witness.model_endpoints[0]
    assert trailing.preferred_reachability.status == "not_required"
    assert trailing.engagement_reachability.status == "reachable"
    assert trailing.engagement_reachability.alternative_witness is not None
    assert not result.is_valid


def test_order47_distance_proof_exempts_only_the_model_that_cannot_reach() -> None:
    from tests.charge_endpoint_helpers import endpoint_resolution

    result = endpoint_resolution(distances=(4, 4, 4, 4, 4), first_start_y=18.6, maximum=4)
    assert result.is_valid, result.movement_payload
    trailing = result.endpoint_witness.model_endpoints[0]
    assert trailing.ended_closer
    assert trailing.preferred_reachability.status == "unreachable"
    assert trailing.engagement_reachability.status == "unreachable"
    assert all(
        row.preferred_reachability.status == "satisfied"
        for row in result.endpoint_witness.model_endpoints[1:]
    )


def test_order47_obstacles_use_validated_paths_and_never_grant_an_unresolved_exemption() -> None:
    from tests.charge_endpoint_helpers import endpoint_resolution

    from warhammer40k_core.geometry.pose import Point3
    from warhammer40k_core.geometry.terrain import TerrainVolume

    wall = TerrainVolume(
        terrain_id="charge-wall", bottom_center=Point3(10, 24, 0), width=0.8, depth=0.4, height=5
    )
    open_result = endpoint_resolution()
    routed = endpoint_resolution(terrain=(wall,))
    open_evidence = open_result.endpoint_witness.model_endpoints[0].preferred_reachability
    routed_evidence = routed.endpoint_witness.model_endpoints[0].preferred_reachability
    assert open_evidence.status == routed_evidence.status == "reachable"
    assert open_evidence.alternative_witness != routed_evidence.alternative_witness
    tight = endpoint_resolution(
        distances=(3, 3.75, 3.75, 3.75, 3.75), maximum=3.75, terrain=(wall,)
    )
    assert all(row.is_valid for row in tight.path_validation_results)
    assert all(row.is_valid for row in tight.terrain_path_legality_results)
    assert tight.coherency_result.is_coherent
    assert tight.endpoint_violation_code == "charge_reachability_unresolved"
    assert not tight.is_valid
    assert tight.endpoint_witness.model_endpoints[0].preferred_reachability.status == "unresolved"


def test_order47_empty_target_set_is_a_typed_invalid_endpoint() -> None:
    from tests.charge_endpoint_helpers import endpoint_resolution

    result = endpoint_resolution(targets=())
    assert not result.is_valid
    assert result.endpoint_violation_code == "charge_target_required"


@pytest.mark.parametrize("attached", [False, True], ids=["ordinary", "attached-leader"])
def test_order74_obstacle_exemption_accepts_charge_through_facade_and_replays(
    attached: bool,
) -> None:
    import copy
    import json

    from tests.mandatory_endpoint_helpers import (
        blocked_charge_payload,
        blocked_charge_request,
        blocked_charge_session,
    )

    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus

    session = blocked_charge_session(attached=attached)
    session.advance_until_decision_or_terminal()
    initial = session.lifecycle.to_payload()
    request = blocked_charge_request(session)
    pending = session.lifecycle.to_payload()
    with pytest.raises(GameLifecycleError, match="request_id"):
        session.submit_parameterized_payload(
            request_id=request.request_id + ":stale",
            result_id="stale-terrain-charge",
            payload=blocked_charge_payload(session, request),
        )
    assert session.lifecycle.to_payload() == pending
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order74-legal-charge",
        payload=blocked_charge_payload(session, request),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    events = session.lifecycle.decision_controller.event_log.records
    event = next(row for row in events if row.event_type == "charge_move_completed")
    assert isinstance(event.payload, dict)
    assert event.payload["unit_instance_id"] == (
        "attached-unit:army-alpha:source" if attached else "army-alpha:source"
    )
    assert event.payload["maximum_distance_inches"] == 3.75
    endpoint = cast(dict[str, JsonValue], event.payload["endpoint_witness"])
    models = cast(list[dict[str, JsonValue]], endpoint["model_endpoints"])
    component_id = "army-alpha:leader" if attached else "army-alpha:source"
    exempt = next(row for row in models if row["component_unit_instance_id"] == component_id)
    proof = cast(dict[str, JsonValue], exempt["preferred_reachability"])
    assert proof["status"] == "endpoint_unreachable"
    assert 3.74 < cast(float, proof["distance_lower_bound_inches"]) < 3.75
    assert proof["alternative_witness"] is None
    assert len(models) == (6 if attached else 5)
    assert all(
        cast(dict[str, JsonValue], row["preferred_reachability"])["status"] == "satisfied"
        for row in models
        if row["model_instance_id"] != exempt["model_instance_id"]
    )
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(component_id)
    assert exempt["model_instance_id"] == placement.model_placements[0].model_instance_id
    for viewer in ("player-a", "player-b"):
        json.dumps(session.view(viewer_player_id=viewer), allow_nan=False)
        visible = session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        assert "endpoint_unreachable" in json.dumps(visible, allow_nan=False)
    final = session.lifecycle.to_payload()
    assert json.loads(json.dumps(final, allow_nan=False)) == final
    assert GameLifecycle.from_payload(final).to_payload() == final
    artifact = ReplayArtifact.capture(
        artifact_id="order74-obstacle-charge",
        final_lifecycle=session.lifecycle,
        initial_lifecycle_payload=initial,
    )
    assert (
        ReplayRunner.from_payload(json.loads(json.dumps(artifact.to_payload(), allow_nan=False)))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )
    for field, changed, diagnostic in (
        ("status", "unreachable", "endpoint"),
        ("status", "unresolved", "endpoint"),
        ("distance_lower_bound_inches", 3.5, "reachability bound drifted"),
        ("component_unit_instance_id", "army-alpha:source", "per-model endpoint geometry drifted"),
    ):
        if field == "component_unit_instance_id" and not attached:
            continue
        forged = copy.deepcopy(final)
        completion = next(
            e
            for e in forged["decisions"]["event_log"]
            if e["event_type"] == "charge_move_completed"
        )
        data = cast(dict[str, JsonValue], completion["payload"])
        endpoint = cast(dict[str, JsonValue], data["endpoint_witness"])
        rows = cast(list[dict[str, JsonValue]], endpoint["model_endpoints"])
        row = next(row for row in rows if row["model_instance_id"] == exempt["model_instance_id"])
        if field == "component_unit_instance_id":
            row[field] = changed
        else:
            cast(dict[str, JsonValue], row["preferred_reachability"])[field] = changed
        with pytest.raises(GameLifecycleError, match=diagnostic):
            GameLifecycle.from_payload(forged)


@pytest.mark.parametrize("flies", [False, True])
def test_order47_restored_distance_proof_uses_the_source_movement_metric(flies: bool) -> None:
    from msgspec.structs import replace as replace_struct

    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.charge_endpoint_history import (
        validate_charge_model_reachability_bounds,
    )
    from warhammer40k_core.engine.charge_model_endpoints import (
        EndpointReachabilityEvidence,
        charge_model_endpoint_witness,
    )
    from warhammer40k_core.engine.movement_legality import MovementCapabilitySet
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.geometry.base import CircularBase
    from warhammer40k_core.geometry.movement_reachability import MovementGoal
    from warhammer40k_core.geometry.volume import Model, ModelVolume

    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    capabilities = MovementCapabilitySet.from_keywords(
        keywords=("FLY",) if flies else (),
        ruleset_descriptor=ruleset,
        movement_mode="charge",
        take_to_the_skies=flies,
    )
    assert capabilities.ignores_vertical_distance is flies
    start = Model("source-model", Pose.at(10, 10), CircularBase(0.5), ModelVolume(2))
    target = replace(start, model_id="target-model", pose=Pose.at(10, 20, 10))
    targets: dict[str, tuple[Model, ...]] = {"target": (target,)}
    goal = MovementGoal(models=(target,), range_inches=1)
    ground_bound = goal.distance_lower_bound(start, ignores_vertical_distance=False)
    flying_bound = goal.distance_lower_bound(start, ignores_vertical_distance=True)
    assert ground_bound > flying_bound
    row = charge_model_endpoint_witness(
        start=start,
        end=replace(start, pose=Pose.at(10, 11)),
        targets=targets,
        ruleset=ruleset,
        context=None,
        component_unit_instance_id="source",
    )
    row = replace_struct(
        row,
        preferred_reachability=EndpointReachabilityEvidence(
            "unreachable", flying_bound if flies else ground_bound, None
        ),
    )
    validate_charge_model_reachability_bounds(
        row=row, start=start, targets=targets, ruleset=ruleset, capabilities=capabilities
    )
    drifted = replace_struct(
        row,
        preferred_reachability=EndpointReachabilityEvidence(
            "unreachable", ground_bound if flies else flying_bound, None
        ),
    )
    with pytest.raises(GameLifecycleError, match="reachability bound drifted"):
        validate_charge_model_reachability_bounds(
            row=drifted, start=start, targets=targets, ruleset=ruleset, capabilities=capabilities
        )


def test_order47_checkpoint_authenticates_an_attached_models_distance_exemption() -> None:
    from tests.charge_distance_helpers import add_modifier, select_targets
    from tests.charge_endpoint_helpers import (
        ATTACHED_TARGET,
        attached_move_payload,
        select_attached_source,
    )

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    lifecycle, _ = charge_lifecycle(
        alpha_unit_ids=("source", "leader", "next"),
        alpha_attached_unit_ids=("source", "leader"),
        alpha_origins={"leader": Pose.at(17, 17.6)},
        game_id="order47-exemption-9",
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(10, 26), model_count=5),
    )
    assert lifecycle.state is not None
    add_modifier(lifecycle.state, effect_id="exemption-roll", kind="modify_dice_roll", delta=20)
    add_modifier(
        lifecycle.state, effect_id="exemption-distance", kind="modify_move_distance", delta=-7
    )
    session = LocalGameSession(lifecycle)
    request = select_targets(session, select_attached_source(session), (ATTACHED_TARGET,))
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order47-exempt-attached-move",
        payload=attached_move_payload(session, request),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    event = next(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "charge_move_completed"
    )
    payload = cast(dict[str, JsonValue], event.payload)
    assert payload["maximum_distance_inches"] == 5
    endpoint = cast(dict[str, JsonValue], payload["endpoint_witness"])
    rows = cast(list[dict[str, JsonValue]], endpoint["model_endpoints"])
    leader = next(row for row in rows if row["component_unit_instance_id"] == "army-alpha:leader")
    evidence = cast(dict[str, JsonValue], leader["preferred_reachability"])
    assert evidence["status"] == "unreachable"
    checkpoint = lifecycle.to_payload()
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    # A genuine attached-model distance exemption cannot be relabelled as a
    # terrain proof: this fixture has no constraining feature-owned walls.
    from warhammer40k_core.engine.phase import GameLifecycleError

    event_payload = next(
        row["payload"]
        for row in checkpoint["decisions"]["event_log"]
        if row["event_type"] == "charge_move_completed"
    )
    endpoint_payload = cast(
        dict[str, JsonValue], cast(dict[str, JsonValue], event_payload)["endpoint_witness"]
    )
    historical_rows = cast(list[dict[str, JsonValue]], endpoint_payload["model_endpoints"])
    leader_row = next(
        row for row in historical_rows if row["component_unit_instance_id"] == "army-alpha:leader"
    )
    cast(dict[str, JsonValue], leader_row["preferred_reachability"])["status"] = (
        "endpoint_unreachable"
    )
    with pytest.raises(GameLifecycleError, match="endpoint proof drifted"):
        GameLifecycle.from_payload(checkpoint)


@pytest.mark.parametrize("tamper", ["owner", "distance", "inventory", "source", "status", "bound"])
def test_order47_restore_rejects_tampered_per_model_evidence(tamper: str) -> None:
    from tests.charge_distance_helpers import select_targets
    from tests.charge_endpoint_helpers import (
        ATTACHED_TARGET,
        attached_charge_session,
        attached_move_payload,
        select_attached_source,
    )

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    session = attached_charge_session()
    request = select_targets(session, select_attached_source(session), (ATTACHED_TARGET,))
    session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order47-tamper-move",
        payload=attached_move_payload(session, request),
    )
    checkpoint = session.lifecycle.to_payload()
    # Mutate event evidence while preserving the physical transition and decision.
    events = checkpoint["decisions"]["event_log"]
    completed = next(e for e in events if e["event_type"] == "charge_move_completed")
    payload = cast(dict[str, JsonValue], completed["payload"])
    endpoint = cast(dict[str, JsonValue], payload["endpoint_witness"])
    rows = cast(list[dict[str, JsonValue]], endpoint["model_endpoints"])
    row = rows[0]
    if tamper == "owner":
        row["component_unit_instance_id"] = "army-alpha:forged-component"
    elif tamper == "distance":
        before = cast(dict[str, JsonValue], row["target_distances_before_inches"])
        before[ATTACHED_TARGET] = cast(float, before[ATTACHED_TARGET]) + 0.1
    elif tamper == "inventory":
        rows.pop()
    elif tamper == "source":
        row["source_rule_id"] = "unknown-rule"
    else:
        evidence = cast(dict[str, JsonValue], row["preferred_reachability"])
        if tamper == "status":
            evidence["status"] = "unknown"
        else:
            evidence["distance_lower_bound_inches"] = 99.0
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(checkpoint)


@pytest.mark.parametrize("casualty", ["leader", "source"])
def test_r47_001_historical_fly_charge_survives_a_later_retained_casualty(casualty: str) -> None:
    from tests.charge_distance_helpers import select_targets
    from tests.charge_endpoint_helpers import (
        ATTACHED_TARGET,
        attached_move_payload,
        flying_attached_charge_exemption_session,
        select_attached_source,
    )
    from tests.fight_on_death_helpers import retain_destroyed_model_for_fixture

    from warhammer40k_core.engine.damage_allocation import (
        DamageKind,
        apply_damage_to_model,
        model_by_id,
    )
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session, bundle = flying_attached_charge_exemption_session()
    lifecycle = session.lifecycle
    request = select_targets(
        session, select_attached_source(session, take_to_the_skies=True), (ATTACHED_TARGET,)
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="r47-001-charge",
        payload=attached_move_payload(session, request),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    before = lifecycle.to_payload()
    assert GameLifecycle.from_payload(before, runtime_content_bundle=bundle).to_payload() == before
    event = next(
        e
        for e in lifecycle.decision_controller.event_log.records
        if e.event_type == "charge_move_completed"
    )
    payload = cast(dict[str, JsonValue], event.payload)
    endpoint = cast(dict[str, JsonValue], payload["endpoint_witness"])
    rows = cast(list[dict[str, JsonValue]], endpoint["model_endpoints"])
    leader = next(row for row in rows if row["component_unit_instance_id"] == "army-alpha:leader")
    assert cast(dict[str, JsonValue], leader["preferred_reachability"])["status"] == "unreachable"
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    phase = state.current_battle_phase
    assert phase is not None
    unit_id = f"army-alpha:{casualty}"
    placement = state.battlefield_state.unit_placement_by_id(unit_id).model_placements[0]
    model = model_by_id(state=state, model_instance_id=placement.model_instance_id)
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=unit_id,
        model_instance_id=model.model_instance_id,
        damage=model.current_wounds,
        damage_kind=DamageKind.NORMAL,
        remove_destroyed_model=False,
    )
    retain_destroyed_model_for_fixture(
        state=state,
        placement=placement,
        effect_id="r47-001-retained",
        source_rule_id="r47-001-retained-source",
        source_phase=phase,
        decisions=lifecycle.decision_controller,
    )
    after = lifecycle.to_payload()
    assert GameLifecycle.from_payload(after, runtime_content_bundle=bundle).to_payload() == after


def test_r47_001_component_snapshot_excludes_later_keywords_and_model_inventory() -> None:
    from tests.model_keyword_helpers import mixed_keyword_unit

    from warhammer40k_core.engine.charge_endpoint_history import (
        charge_component_at_physical_boundary,
    )
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
        PhysicalModelAuthority,
    )

    unit = mixed_keyword_unit()
    specialist = next(model for model in unit.own_models if "PSYKER" in model.keywords)
    ordinary, later_model = tuple(model for model in unit.own_models if model != specialist)
    current = replace(
        unit,
        own_models=tuple(
            replace(model, wounds_remaining=0) if model == ordinary else model
            for model in unit.own_models
        ),
    )
    assert "PSYKER" in current.keywords
    physical = (
        PhysicalModelAuthority(
            ordinary.model_instance_id, "battlefield", Pose.at(10, 10), ordinary.initial_wounds
        ),
        PhysicalModelAuthority(specialist.model_instance_id, "destroyed", None, 0),
    )
    historical = charge_component_at_physical_boundary(unit=current, physical=physical)
    assert historical.own_model_ids() == tuple(
        model.model_instance_id for model in unit.own_models if model != later_model
    )
    assert "PSYKER" not in historical.keywords
    assert historical.alive_own_models() == (ordinary,)
    assert current.alive_own_models() == tuple(
        model for model in unit.own_models if model != ordinary
    )
    with pytest.raises(GameLifecycleError, match="no model authority"):
        charge_component_at_physical_boundary(unit=current, physical=())


@pytest.mark.parametrize(
    "tamper", ["missing_component", "foreign_model", "start_pose", "actor_alias"]
)
def test_order47_attached_stale_paths_are_rejected_before_decision_consumption(tamper: str) -> None:
    from tests.charge_distance_helpers import select_targets
    from tests.charge_endpoint_helpers import (
        ATTACHED_TARGET,
        attached_charge_session,
        attached_move_payload,
        select_attached_source,
    )

    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = attached_charge_session()
    request = select_targets(session, select_attached_source(session), (ATTACHED_TARGET,))
    payload = cast(dict[str, JsonValue], attached_move_payload(session, request))
    witness = cast(dict[str, JsonValue], payload["witness"])
    paths = cast(list[dict[str, JsonValue]], witness["model_paths"])
    if tamper == "actor_alias":
        payload["unit_instance_id"] = "army-alpha:source"
    elif tamper == "missing_component":
        paths.pop()
    elif tamper == "foreign_model":
        paths[0]["model_id"] = "foreign-model"
    else:
        poses = cast(list[dict[str, JsonValue]], paths[0]["poses"])
        position = cast(dict[str, JsonValue], poses[0]["position"])
        position["x"] = cast(float, position["x"]) + 0.25
    state = session.lifecycle.state
    assert state is not None
    before = state.battlefield_state
    decisions_before = session.lifecycle.decision_controller.records
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order47-stale-attached",
        payload=payload,
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == before
    assert session.lifecycle.decision_controller.records == decisions_before
    assert session.lifecycle.decision_controller.queue.pending_requests == (request,)


@pytest.mark.parametrize(
    "advanced_id", ["army-alpha:source", "army-alpha:leader", "attached-unit:army-alpha:source"]
)
def test_order47_component_advance_restrictions_apply_to_the_canonical_actor(
    advanced_id: str,
) -> None:
    from tests.charge_endpoint_helpers import ATTACHED_SOURCE, attached_charge_session
    from tests.phase15a_charge_test_support import _advanced_unit_state

    session = attached_charge_session()
    state = session.lifecycle.state
    assert state is not None
    state.record_advanced_unit_state(_advanced_unit_state(advanced_id))
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    assert ATTACHED_SOURCE not in {option.option_id for option in request.options}


@pytest.mark.parametrize("drift", ["inventory", "start"])
def test_order47_heroic_uses_the_shared_stale_path_guard(drift: str) -> None:
    from tests.charge_distance_helpers import request_from
    from tests.phase15a_charge_test_support import (
        _charge_path_witness_for_unit,
        _end_charge_heroic_session,
        _submit_end_charge_heroic_target,
    )

    from warhammer40k_core.core.ruleset_descriptor import MovementMode
    from warhammer40k_core.engine.movement_proposals import ProposalKind
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.phases.charge import ChargeMoveProposal
    from warhammer40k_core.geometry.pathing import PathWitnessPayload

    session, units = _end_charge_heroic_session(
        game_id="order47-heroic-stale",
        maulerfiend_selection_ids=(),
        ordinary_selection_ids=("ordinary",),
        command_points=1,
    )
    opportunity = request_from(session.advance_until_decision_or_terminal())
    source_id = units["ordinary"].unit_instance_id
    request = request_from(
        _submit_end_charge_heroic_target(
            session,
            request=opportunity,
            target_unit_instance_id=source_id,
            result_id="order47-heroic-use",
        )
    )
    path = _charge_path_witness_for_unit(session.lifecycle, unit_instance_id=source_id, dx=0, dy=3)
    proposal = ChargeMoveProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        unit_instance_id=source_id,
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=(units["enemy"].unit_instance_id,),
        witness=path,
    ).to_payload()
    assert "witness" in proposal
    assert proposal["witness"] is not None
    paths = cast(PathWitnessPayload, proposal["witness"])["model_paths"]
    if drift == "inventory":
        paths.pop()
    else:
        paths[0]["poses"][0]["position"]["x"] += 0.25
    state = session.lifecycle.state
    assert state is not None
    before = state.battlefield_state
    records = session.lifecycle.decision_controller.records
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order47-heroic-stale-path",
        payload=cast(JsonValue, proposal),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == before
    assert session.lifecycle.decision_controller.records == records
    assert session.lifecycle.decision_controller.queue.pending_requests == (request,)
