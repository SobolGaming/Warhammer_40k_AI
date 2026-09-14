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
