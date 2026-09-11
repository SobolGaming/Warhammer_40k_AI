"""Fail-closed boundaries for persisted Order 36 trigger and batch authority."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.battlefield_state import ModelPlacement
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_trigger_state import (
    RuleTrigger,
    RuleTriggerKind,
    RuleTriggerPayload,
    complete_rule_trigger,
    observe_rule_trigger,
    release_rule_trigger,
    rule_trigger_history,
)
from warhammer40k_core.engine.sequencing import (
    SequencingConflictContext,
    SequencingParticipant,
    SequencingRequirement,
)
from warhammer40k_core.engine.timing_batch_state import TimingBatch, TimingBatchPayload
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)


def _batch() -> TimingBatch:
    window = TimingWindow(
        window_id="order36-authority-window",
        descriptor=TimingWindowDescriptor(
            descriptor_id="order36-authority-descriptor",
            trigger_kind=TimingTriggerKind.START_PHASE,
            source_rule_id="order36-source",
            phase=BattlePhaseKind.MOVEMENT,
        ),
        game_id="order36-authority",
        battle_round=1,
        active_player_id="player-a",
        phase=BattlePhaseKind.MOVEMENT,
    )
    return TimingBatch.open(
        context=SequencingConflictContext(
            conflict_id="order36-authority-conflict",
            game_id=window.game_id,
            timing_window=window,
            player_ids=("player-a", "player-b"),
            active_player_id="player-a",
        ),
        participants=tuple(
            SequencingParticipant(
                participant_id=player,
                player_id=player,
                source_rule_id="order36-source",
                requirement=SequencingRequirement.MANDATORY,
            )
            for player in ("player-a", "player-b")
        ),
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("context", None, "conflict context"),
        ("generation", True, "non-negative integer"),
        ("generation", -1, "non-negative integer"),
        ("participants", (), "immutable participant"),
        ("participants", [], "immutable participant"),
        ("deferred_participants", [], "must be a tuple"),
        ("completed_participant_ids", [], "completed prefix is invalid"),
        ("completed_participant_ids", (False,), "completed prefix is invalid"),
        ("completed_participant_ids", ("absent",), "completed prefix is invalid"),
        ("completed_participant_ids", ("player-a", "player-a"), "completed prefix is invalid"),
        ("completed_participant_ids", ("player-b",), "prefix violates tier"),
        ("selected_participant_id", 1, "must be an identifier"),
        ("selected_participant_id", "player-b", "not eligible"),
    ],
)
def test_timing_batch_rejects_forged_owner_progress(field: str, value: Any, message: str) -> None:
    with pytest.raises(GameLifecycleError, match=message):
        replace(_batch(), **{field: value})


def test_timing_batch_requires_selected_completion_and_closed_original_population() -> None:
    batch = _batch()
    with pytest.raises(GameLifecycleError, match="not eligible"):
        batch.select("player-b")
    with pytest.raises(GameLifecycleError, match="before the batch completes"):
        batch.release_deferred()
    with pytest.raises(GameLifecycleError, match="selected"):
        batch.complete("player-a")
    selected = batch.select("player-a")
    with pytest.raises(GameLifecycleError, match="already has a selected"):
        selected.select("player-a")
    completed = selected.complete("player-a").select("player-b").complete("player-b")
    assert completed.release_deferred() is None
    with pytest.raises(GameLifecycleError, match="cannot acquire new triggers"):
        completed.defer(batch.participants)
    payload = cast(dict[str, Any], batch.to_payload())
    payload["unrecorded_progress"] = True
    with pytest.raises(GameLifecycleError, match="schema drifted"):
        TimingBatch.from_payload(cast(TimingBatchPayload, payload))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("kind", False, "must be a string"),
        ("kind", "unsupported", "unsupported"),
        ("context", [], "must be an object"),
        ("parent_batch_id", "missing-parent", "requires both"),
        ("parent_participant_id", "missing-parent", "requires both"),
        ("trigger_id", "forged-trigger", "identity drift"),
        ("extra", True, "schema drift"),
    ],
)
def test_rule_trigger_payload_rejects_forged_occurrence(
    field: str, value: Any, message: str
) -> None:
    trigger = RuleTrigger(RuleTriggerKind.MOVE_COMPLETION, {"trigger_event_id": "move"}, None, None)
    payload = cast(dict[str, Any], trigger.to_payload())
    payload[field] = value
    with pytest.raises(GameLifecycleError, match=message):
        RuleTrigger.from_payload(cast(RuleTriggerPayload, payload))


@pytest.mark.parametrize("kind", list(RuleTriggerKind))
def test_rule_trigger_requires_its_own_source_identity(kind: RuleTriggerKind) -> None:
    with pytest.raises(GameLifecycleError, match="requires"):
        _ = RuleTrigger(kind, {}, None, None).conflict_id


def test_rule_trigger_rejects_untyped_kind_and_incomplete_parent_identifiers() -> None:
    with pytest.raises(GameLifecycleError, match="must be typed"):
        RuleTrigger(cast(RuleTriggerKind, "move_completion"), {}, None, None)
    with pytest.raises(GameLifecycleError, match="parent_batch_id"):
        RuleTrigger(RuleTriggerKind.MOVE_COMPLETION, {}, "", "selected")


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("bad_observation", "observation requires an object"),
        ("duplicate_observation", "observation is duplicated"),
        ("unknown_parent", "lacks its selected parent"),
        ("bad_disposition", "disposition requires its exact identity"),
        ("unknown_disposition", "no observed occurrence"),
        ("completion_before_release", "lacks a unique release"),
        ("out_of_order_release", "bypasses an earlier occurrence"),
        ("duplicate_release", "before its parent batch completed"),
        ("interrupt_release", "interrupts another released occurrence"),
        ("duplicate_completion", "lacks a unique release"),
    ],
)
def test_trigger_history_rejects_reordered_or_invented_lifecycle_events(
    case: str, message: str
) -> None:
    decisions = DecisionController()
    first = observe_rule_trigger(
        decisions=decisions,
        kind=RuleTriggerKind.MOVE_COMPLETION,
        context={"trigger_event_id": "first"},
    )
    second = observe_rule_trigger(
        decisions=decisions,
        kind=RuleTriggerKind.MOVE_COMPLETION,
        context={"trigger_event_id": "second"},
    )
    event_type, payload = "rule_trigger_released", cast(Any, {"trigger_id": first.trigger_id})
    if case == "bad_observation":
        event_type, payload = "rule_trigger_observed", []
    elif case == "duplicate_observation":
        event_type, payload = "rule_trigger_observed", first.to_payload()
    elif case == "unknown_parent":
        event_type = "rule_trigger_observed"
        payload = RuleTrigger(
            RuleTriggerKind.MOVE_COMPLETION, {}, "absent", "selected"
        ).to_payload()
    elif case == "bad_disposition":
        payload = {"trigger_id": first.trigger_id, "extra": True}
    elif case == "unknown_disposition":
        payload = {"trigger_id": "absent"}
    elif case == "completion_before_release":
        event_type = "rule_trigger_completed"
    elif case == "out_of_order_release":
        payload = {"trigger_id": second.trigger_id}
    else:
        assert release_rule_trigger(decisions=decisions, trigger=first)
        if case == "interrupt_release":
            payload = {"trigger_id": second.trigger_id}
        elif case == "duplicate_completion":
            complete_rule_trigger(decisions=decisions, trigger=first)
            event_type = "rule_trigger_completed"
    decisions.event_log.append(event_type, cast(JsonValue, payload))
    with pytest.raises(GameLifecycleError, match=message):
        rule_trigger_history(decisions)


def _move_endpoint_fixture(
    event_type: str,
) -> tuple[GameState, EventRecord, tuple[ModelPlacement, ...]]:
    from tests.rapid_ingress_helpers import ingress_session

    from warhammer40k_core.engine.battlefield_state import (
        BattlefieldPlacementKind,
        BattlefieldTransitionBatch,
        ModelDisplacementKind,
        ModelDisplacementRecord,
        ModelPlacementRecord,
    )
    from warhammer40k_core.engine.event_log import EventRecord, validate_json_value
    from warhammer40k_core.geometry.pathing import PathWitness
    from warhammer40k_core.geometry.pose import Pose

    state = ingress_session(battle_round=2, inventory=("INFANTRY",)).lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    placement = state.battlefield_state.placed_armies[0].unit_placements[0]
    expected = tuple(
        row.with_pose(Pose.at(row.pose.position.x + 0.1, row.pose.position.y, row.pose.position.z))
        for row in placement.model_placements
    )
    transition = BattlefieldTransitionBatch(
        displacements=tuple(
            ModelDisplacementRecord(
                model_instance_id=old.model_instance_id,
                displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
                start_pose=old.pose,
                end_pose=new.pose,
                path_witness=PathWitness.for_paths(
                    ((old.model_instance_id, (old.pose, new.pose)),)
                ),
            )
            for old, new in zip(placement.model_placements, expected, strict=True)
        )
    )
    if event_type in {"unit_disembarked", "reinforcement_unit_arrived"}:
        transition = BattlefieldTransitionBatch(
            placements=tuple(
                ModelPlacementRecord(
                    model_instance_id=row.model_instance_id,
                    placement_kind=BattlefieldPlacementKind.DISEMBARK,
                    pose=row.pose,
                )
                for row in expected
            )
        )
    event = EventRecord(
        event_id="event-000001",
        event_type=event_type,
        payload={
            "unit_instance_id": placement.unit_instance_id,
            "transition_batch": validate_json_value(transition.to_payload()),
            "witness": validate_json_value(
                PathWitness.for_paths(
                    tuple(
                        (old.model_instance_id, (old.pose, new.pose))
                        for old, new in zip(placement.model_placements, expected, strict=True)
                    )
                ).to_payload()
            ),
            "model_movements": [
                {
                    "model_instance_id": row.model_instance_id,
                    "end_pose": validate_json_value(row.pose.to_payload()),
                }
                for row in expected
            ],
        },
    )
    return state, event, expected


@pytest.mark.parametrize(
    "event_type",
    [
        "movement_activation_completed",
        "unit_disembarked",
        "reinforcement_unit_arrived",
        "charge_move_completed",
        "triggered_movement_resolved",
        "heroic_intervention_charge_move_completed",
        "catalog_setup_reactive_charge_move_completed",
    ],
)
def test_deferred_move_endpoints_use_accepted_evidence_for_every_source_family(
    event_type: str,
) -> None:
    from warhammer40k_core.engine.move_completion_geometry import completed_move_model_placements

    state, event, expected = _move_endpoint_fixture(event_type)
    assert completed_move_model_placements(state=state, event=event) == expected


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("no_unit", "requires its moving unit"),
        ("no_transition", "requires its transition batch"),
        ("no_witness", "requires its PathWitness"),
        ("setup_displacements", "requires placement records"),
        ("no_movements", "requires per-model movements"),
        ("malformed_movement", "invalid model movement"),
        ("duplicate_model", "model evidence is duplicated"),
        ("drifted_displacement", "differs from its accepted displacement"),
        ("unknown_model", "model ownership drift"),
        ("unsupported_event", "unsupported source event"),
    ],
)
def test_deferred_move_endpoint_evidence_rejects_drift(case: str, message: str) -> None:
    from warhammer40k_core.engine.move_completion_geometry import completed_move_model_placements

    event_type = (
        "movement_activation_completed" if case == "no_witness" else "charge_move_completed"
    )
    state, event, _ = _move_endpoint_fixture(event_type)
    payload = cast(dict[str, Any], event.payload)
    if case == "no_unit":
        del payload["unit_instance_id"]
    elif case == "no_transition":
        del payload["transition_batch"]
    elif case == "no_witness":
        del payload["witness"]
    elif case == "setup_displacements":
        event = replace(event, event_type="unit_disembarked")
    elif case == "no_movements":
        payload["model_movements"] = []
    elif case == "malformed_movement":
        payload["model_movements"] = [False]
    elif case == "duplicate_model":
        payload["model_movements"].append(payload["model_movements"][0])
    elif case == "drifted_displacement":
        payload["model_movements"][0]["end_pose"] = payload["transition_batch"]["displacements"][0][
            "start_pose"
        ]
    elif case == "unknown_model":
        payload["transition_batch"]["displacements"] = []
        payload["model_movements"][0]["model_instance_id"] = "foreign-model"
    else:
        event = replace(event, event_type="unrelated_event")
    with pytest.raises(GameLifecycleError, match=message):
        completed_move_model_placements(state=state, event=event)


def _captured_move_fixture() -> tuple[GameState, DecisionController, RuleTrigger]:
    from tests.phase17n_primary_mission_helpers import append_authenticated_normal_move

    from warhammer40k_core.geometry.pose import Pose

    state, endpoint, _ = _move_endpoint_fixture("movement_activation_completed")
    assert isinstance(endpoint.payload, dict)
    unit_id = endpoint.payload["unit_instance_id"]
    assert isinstance(unit_id, str)
    decisions = DecisionController()
    append_authenticated_normal_move(
        state=state,
        decisions=decisions,
        unit_instance_id=unit_id,
        suffix="order36-capture-authority",
        pose_transform=lambda pose: Pose.at(
            pose.position.x + 0.1, pose.position.y, pose.position.z
        ),
    )
    return state, decisions, rule_trigger_history(decisions).observed[-1]


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        ("missing_capture", "unique trigger-time population"),
        ("duplicate_capture", "unique trigger-time population"),
        ("shifted_capture", "exact observation boundary"),
        ("wrong_game", "schema or provider identity drift"),
        ("wrong_providers", "schema or provider identity drift"),
        ("malformed_population", "schema or provider identity drift"),
        ("invented_participant", "population or source evidence drift"),
        ("extra_field", "schema or provider identity drift"),
    ],
)
def test_deferred_move_registry_rejects_forged_captured_population(
    tamper: str, message: str
) -> None:
    from warhammer40k_core.engine.decision_controller import DecisionControllerPayload
    from warhammer40k_core.engine.faction_content.unit_move_completed import (
        move_completion_rule_registry,
    )
    from warhammer40k_core.engine.move_completion_triggers import move_context_for_trigger
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

    state, decisions, trigger = _captured_move_fixture()
    payload = cast(dict[str, Any], decisions.to_payload())
    events = payload["event_log"]
    captured = next(row for row in events if row["event_type"] == "move_rule_candidates_observed")
    if tamper == "missing_capture":
        captured["event_type"] = "unrelated_event"
    elif tamper == "duplicate_capture":
        events.append({**captured, "event_id": f"event-{len(events) + 1:06d}"})
    elif tamper == "shifted_capture":
        events.append({**captured, "event_id": f"event-{len(events) + 1:06d}"})
        captured["event_type"] = "unrelated_event"
    elif tamper == "wrong_game":
        captured["payload"]["game_id"] = "different-game"
    elif tamper == "wrong_providers":
        captured["payload"]["hook_ids"] = []
    elif tamper == "malformed_population":
        captured["payload"]["participants"] = False
    elif tamper == "invented_participant":
        captured["payload"]["participants"] = [_batch().participants[0].to_payload()]
    else:
        captured["payload"]["extra"] = True
    restored = DecisionController.from_payload(cast(DecisionControllerPayload, payload))
    context = move_context_for_trigger(
        state=state,
        decisions=restored,
        trigger=trigger,
        runtime_modifiers=RuntimeModifierRegistry.empty(),
        ability_indexes={},
    )
    before = (state.to_payload(), restored.to_payload())
    with pytest.raises(GameLifecycleError, match=message):
        move_completion_rule_registry().candidates_for(context)
    assert (state.to_payload(), restored.to_payload()) == before


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        ("wrong_kind", "typed trigger"),
        ("missing_source", "source authority drift"),
        ("wrong_context", "source authority drift"),
        ("missing_observation", "source event's parent timing batch"),
        ("shifted_observation", "source event's parent timing batch"),
        ("wrong_game", "source game or round drift"),
        ("wrong_round", "source game or round drift"),
        ("wrong_player", "source player is invalid"),
        ("wrong_event", "no supported source event"),
        ("malformed_event", "object source event"),
    ],
)
def test_move_trigger_rejects_forged_source_or_parent_boundary(tamper: str, message: str) -> None:
    from warhammer40k_core.engine.decision_controller import DecisionControllerPayload
    from warhammer40k_core.engine.move_completion_triggers import move_context_for_trigger
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

    state, decisions, trigger = _captured_move_fixture()
    payload = cast(dict[str, Any], decisions.to_payload())
    events = payload["event_log"]
    source = next(row for row in events if row["event_type"] == "movement_activation_completed")
    observed = next(row for row in events if row["event_type"] == "rule_trigger_observed")
    if tamper == "wrong_kind":
        trigger = replace(trigger, kind=RuleTriggerKind.ATTACK_COMPLETION)
    elif tamper in {"missing_source", "wrong_context"}:
        context = cast(dict[str, Any], trigger.context).copy()
        context["trigger_event_id" if tamper == "missing_source" else "movement_action"] = "forged"
        trigger = replace(trigger, context=context)
    elif tamper == "missing_observation":
        observed["event_type"] = "unrelated_event"
    elif tamper == "shifted_observation":
        events.append({**observed, "event_id": f"event-{len(events) + 1:06d}"})
        observed["event_type"] = "unrelated_event"
    elif tamper == "wrong_game":
        source["payload"]["game_id"] = "different-game"
    elif tamper == "wrong_round":
        source["payload"]["battle_round"] = True
    elif tamper == "wrong_player":
        source["payload"]["active_player_id"] = "absent-player"
    elif tamper == "wrong_event":
        source["event_type"] = "unrelated_event"
    else:
        source["payload"] = []
    restored = DecisionController.from_payload(cast(DecisionControllerPayload, payload))
    before = (state.to_payload(), restored.to_payload())
    with pytest.raises(GameLifecycleError, match=message):
        move_context_for_trigger(
            state=state,
            decisions=restored,
            trigger=trigger,
            runtime_modifiers=RuntimeModifierRegistry.empty(),
            ability_indexes={},
        )
    assert (state.to_payload(), restored.to_payload()) == before


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        ("untyped_kind", "typed action kind"),
        ("untyped_scopes", "tuple of typed scopes"),
        ("untyped_scope", "tuple of typed scopes"),
        ("duplicate", "Duplicate active-player scope"),
        ("foreign_player", "owner is not in this game"),
        ("wrong_owner", "unit ownership drift"),
        ("repeat_selection", "already selected"),
        ("empty_pop", "nested scope order"),
        ("parent_pop", "nested scope order"),
    ],
)
def test_active_player_scope_rejects_invalid_ownership_and_stack_order(
    tamper: str, message: str
) -> None:
    from warhammer40k_core.engine.active_player_scopes import (
        ActivePlayerScope,
        ActivePlayerScopeKind,
        pop_scope,
        push_scope,
        validate_scopes,
    )

    state, _, placements = _move_endpoint_fixture("movement_activation_completed")
    scope = ActivePlayerScope(
        kind=ActivePlayerScopeKind.REACTIVE_MOVE,
        player_id=placements[0].player_id,
        unit_instance_id=placements[0].unit_instance_id,
        source_rule_id="order36-source",
        selection_request_id="order36-request",
        selection_result_id="order36-result",
    )

    def reject_invalid_scope() -> None:
        if tamper == "untyped_kind":
            replace(scope, kind=cast(ActivePlayerScopeKind, "reactive_move"))
        elif tamper in {"untyped_scopes", "untyped_scope", "duplicate"}:
            state.active_player_scopes = cast(
                tuple[ActivePlayerScope, ...],
                {
                    "untyped_scopes": [scope],
                    "untyped_scope": (False,),
                    "duplicate": (scope, scope),
                }[tamper],
            )
            validate_scopes(state)
        elif tamper in {"foreign_player", "wrong_owner"}:
            owner = (
                "foreign"
                if tamper == "foreign_player"
                else next(p for p in state.player_ids if p != scope.player_id)
            )
            push_scope(state, replace(scope, player_id=owner))
        elif tamper == "empty_pop":
            pop_scope(state, scope)
        else:
            push_scope(state, scope)
            if tamper == "repeat_selection":
                push_scope(state, scope)
            else:
                push_scope(state, replace(scope, selection_request_id="nested-request"))
                pop_scope(state, scope)

    with pytest.raises(GameLifecycleError, match=message):
        reject_invalid_scope()


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("bad_event", "exact transition and batch"),
        ("extra_event_field", "exact transition and batch"),
        ("unopened", "no authoritative opening"),
        ("unknown_transition", "not permitted"),
        ("ineligible_without_progress", "exactly one rule"),
        ("drifted_opening", "authority drifted"),
        ("drifted_context", "trigger authority drifted"),
    ],
)
def test_batch_history_rejects_unauthorised_transition(case: str, message: str) -> None:
    from warhammer40k_core.engine.timing_batch_runtime import timing_batches_for_context

    batch = _batch()
    decisions = DecisionController()
    payload = cast(Any, {"transition": "opened", "batch": batch.to_payload()})
    if case == "bad_event":
        payload = []
    elif case == "extra_event_field":
        payload["extra"] = True
    elif case == "unopened":
        payload["transition"] = "selected"
        payload["batch"] = batch.select("player-a").to_payload()
    elif case == "drifted_opening":
        payload["batch"] = replace(batch, generation=1).to_payload()
    elif case == "drifted_context":
        payload["batch"] = replace(
            batch, context=replace(batch.context, active_player_id="player-b")
        ).to_payload()
    else:
        decisions.event_log.append("timing_batch_transition", cast(JsonValue, payload))
        payload = {
            "transition": "ineligible" if case == "ineligible_without_progress" else "invented",
            "batch": batch.to_payload(),
        }
    decisions.event_log.append("timing_batch_transition", cast(JsonValue, payload))
    with pytest.raises(GameLifecycleError, match=message):
        timing_batches_for_context(decisions, batch.context)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("duplicate_candidates", "duplicate participant identities"),
        ("drifted_owner", "source or owner authority drifted"),
        ("wrong_completion", "does not match the active rule"),
        ("new_after_completion", "observation before batch completion"),
        ("completion_without_batch", "without a timing batch"),
        ("completion_without_selection", "has no selected rule"),
    ],
)
def test_batch_runtime_rejects_candidate_and_completion_drift(case: str, message: str) -> None:
    from warhammer40k_core.engine.timing_batch_runtime import (
        complete_timing_participant,
        select_timing_participant,
    )

    batch = _batch()
    decisions = DecisionController()
    participants = batch.participants
    if case != "completion_without_batch":
        selected = select_timing_participant(
            decisions=decisions,
            context=batch.context,
            unresolved_participants=participants,
            next_request_id=lambda: "order36-choice",
        )
        assert selected.participant_id == "player-a"
    completed = None
    if case == "duplicate_candidates":
        participants = (*participants, participants[0])
    elif case == "drifted_owner":
        participants = (replace(participants[0], player_id="player-b"), participants[1])
    elif case == "wrong_completion":
        completed = "player-b"
    elif case in {"new_after_completion", "completion_without_selection"}:
        for identifier in ("player-a", "player-b"):
            select_timing_participant(
                decisions=decisions,
                context=batch.context,
                unresolved_participants=participants,
                completed_participant_id=identifier,
                next_request_id=lambda: "order36-choice",
            )
        if case == "new_after_completion":
            participants = (replace(participants[0], participant_id="new-source"),)
        else:
            completed = "player-b"
    if case == "completion_without_batch":
        with pytest.raises(GameLifecycleError, match=message):
            complete_timing_participant(
                decisions=decisions, context=batch.context, participant_id="player-a"
            )
    else:
        with pytest.raises(GameLifecycleError, match=message):
            select_timing_participant(
                decisions=decisions,
                context=batch.context,
                unresolved_participants=participants,
                completed_participant_id=completed,
                next_request_id=lambda: "order36-choice",
            )


def _destruction_fixture() -> tuple[GameState, DecisionController, RuleTrigger]:
    from tests.destruction_occurrence_fixture_helpers import destroy_rule_model_for_fixture

    state, _, placements = _move_endpoint_fixture("movement_activation_completed")
    decisions = DecisionController()
    destroy_rule_model_for_fixture(
        state=state,
        decisions=decisions,
        model_id=placements[0].model_instance_id,
        destroying_player_id=next(
            player for player in state.player_ids if player != placements[0].player_id
        ),
        source_unit_id=None,
        source_model_id=None,
    )
    return (
        state,
        decisions,
        next(
            trigger
            for trigger in rule_trigger_history(decisions).observed
            if trigger.kind is RuleTriggerKind.MODEL_DESTRUCTION
        ),
    )


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("wrong_kind", "typed model-destruction trigger"),
        ("extra_context", "trigger schema drift"),
        ("missing_event", "unique source event"),
        ("wrong_game", "source identity drift"),
        ("wrong_round", "source identity drift"),
        ("wrong_turn", "source identity drift"),
        ("wrong_active", "source identity drift"),
        ("wrong_phase", "source identity drift"),
        ("observation_boundary", "exact observation boundary"),
    ],
)
def test_destruction_trigger_rejects_invented_or_rebound_casualty(case: str, message: str) -> None:
    from warhammer40k_core.engine.decision_controller import DecisionControllerPayload
    from warhammer40k_core.engine.model_destruction_triggers import destruction_source_event

    state, decisions, trigger = _destruction_fixture()
    if case == "wrong_kind":
        trigger = replace(trigger, kind=RuleTriggerKind.MOVE_COMPLETION)
    elif case == "observation_boundary":
        payload = cast(dict[str, Any], decisions.to_payload())
        next(row for row in payload["event_log"] if row["event_type"] == "rule_trigger_observed")[
            "event_type"
        ] = "unrelated_event"
        decisions = DecisionController.from_payload(cast(DecisionControllerPayload, payload))
    else:
        context = cast(dict[str, Any], trigger.context).copy()
        key, value = {
            "extra_context": ("extra", True),
            "missing_event": ("trigger_event_id", "absent"),
            "wrong_game": ("game_id", "other"),
            "wrong_round": ("battle_round", 3),
            "wrong_turn": ("turn_player_id", "absent"),
            "wrong_active": ("active_player_id", "absent"),
            "wrong_phase": ("phase", "absent"),
        }[case]
        context[key] = value
        trigger = replace(trigger, context=context)
    with pytest.raises(GameLifecycleError, match=message):
        destruction_source_event(state=state, decisions=decisions, trigger=trigger)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("malformed_observation", "object payload"),
        ("missing_identity", "lacks trigger identity"),
        ("malformed_occurrence", "record schema drift"),
        ("unobserved_occurrence", "unique prior trigger"),
        ("repeated_occurrence", "unique prior trigger"),
    ],
)
def test_destruction_occurrence_history_rejects_missing_or_duplicate_authority(
    case: str, message: str
) -> None:
    from warhammer40k_core.engine.model_destruction_triggers import (
        recorded_model_destruction_occurrences,
    )

    decisions = DecisionController()
    observation = cast(
        Any, {"kind": RuleTriggerKind.MODEL_DESTRUCTION.value, "trigger_id": "casualty"}
    )
    if case == "malformed_observation":
        observation = []
    elif case == "missing_identity":
        observation["trigger_id"] = False
    decisions.event_log.append("rule_trigger_observed", cast(JsonValue, observation))
    occurrence = cast(Any, {"trigger_id": "casualty"})
    if case == "malformed_occurrence":
        occurrence = []
    elif case == "unobserved_occurrence":
        occurrence["trigger_id"] = "absent"
    elif case == "repeated_occurrence":
        decisions.event_log.append(
            "model_destruction_occurrence_recorded", cast(JsonValue, occurrence)
        )
    decisions.event_log.append("model_destruction_occurrence_recorded", cast(JsonValue, occurrence))
    with pytest.raises(GameLifecycleError, match=message):
        recorded_model_destruction_occurrences(decisions)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("untyped_bindings", "typed bindings"),
        ("untyped_binding", "typed bindings"),
        ("duplicate_binding", "duplicate bindings"),
        ("noncallable_provider", "candidate discovery"),
        ("discovery_without_decisions", "typed decision context"),
        ("capture_without_decisions", "capture requires decisions"),
        ("resume_without_decisions", "continuation requires decisions"),
        ("late_capture", "source observation"),
        ("drifted_observation", "source observation identity drift"),
    ],
)
def test_move_registry_requires_loaded_providers_and_exact_observation(
    case: str, message: str
) -> None:
    from warhammer40k_core.engine.faction_content.unit_move_completed import (
        move_completion_rule_registry,
    )
    from warhammer40k_core.engine.move_completion_rule_hooks import (
        MoveCompletionRuleBinding,
        MoveCompletionRuleRegistry,
    )
    from warhammer40k_core.engine.move_completion_triggers import move_context_for_trigger
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

    state, decisions, trigger = _captured_move_fixture()
    registry = move_completion_rule_registry()
    context = move_context_for_trigger(
        state=state,
        decisions=decisions,
        trigger=trigger,
        runtime_modifiers=RuntimeModifierRegistry.empty(),
        ability_indexes={},
    )
    binding = registry.bindings[0]

    def reject_invalid_authority() -> None:
        if case in {"untyped_bindings", "untyped_binding", "duplicate_binding"}:
            MoveCompletionRuleRegistry(
                cast(
                    tuple[MoveCompletionRuleBinding, ...],
                    {
                        "untyped_bindings": [binding],
                        "untyped_binding": (False,),
                        "duplicate_binding": (binding, binding),
                    }[case],
                )
            )
        elif case == "noncallable_provider":
            replace(binding, candidates=cast(Any, None))
        elif case == "discovery_without_decisions":
            registry.discover_for(replace(context, decisions=None))
        elif case == "capture_without_decisions":
            registry.capture_for(replace(context, decisions=None))
        elif case == "resume_without_decisions":
            registry.candidates_for(replace(context, decisions=None))
        elif case == "late_capture":
            registry.capture_for(context)
        else:
            from warhammer40k_core.engine.decision_controller import DecisionControllerPayload

            payload = cast(dict[str, Any], decisions.to_payload())
            payload["event_log"].pop()  # Recreate the source observation boundary before capture.
            payload["event_log"][-1]["payload"]["context"]["trigger_event_id"] = "other-source"
            restored = DecisionController.from_payload(cast(DecisionControllerPayload, payload))
            registry.capture_for(replace(context, decisions=restored))

    with pytest.raises(GameLifecycleError, match=message):
        reject_invalid_authority()


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("changed_context", "timing context authority drifted"),
        ("reopened_completed", "reopened its timing batch"),
        ("parent_bypassed", "bypasses the current selected rule"),
        ("root_bypassed", "unfinished timing batch"),
    ],
)
def test_trigger_history_preserves_selected_parent_and_closed_occurrences(
    case: str, message: str
) -> None:
    decisions = DecisionController()
    batch = _batch()
    if case == "reopened_completed":
        trigger = observe_rule_trigger(
            decisions=decisions,
            kind=RuleTriggerKind.MOVE_COMPLETION,
            context={"trigger_event_id": "closed-move"},
        )
        assert release_rule_trigger(decisions=decisions, trigger=trigger)
        complete_rule_trigger(decisions=decisions, trigger=trigger)
        batch = replace(batch, context=replace(batch.context, conflict_id=trigger.conflict_id))
    decisions.event_log.append(
        "timing_batch_transition", {"transition": "opened", "batch": batch.to_payload()}
    )
    if case == "changed_context":
        altered = replace(batch, context=replace(batch.context, active_player_id="player-b"))
        decisions.event_log.append(
            "timing_batch_transition",
            {"transition": "selected", "batch": altered.select("player-b").to_payload()},
        )
    elif case in {"parent_bypassed", "root_bypassed"}:
        decisions.event_log.append(
            "timing_batch_transition",
            {"transition": "selected", "batch": batch.select("player-a").to_payload()},
        )
        if case == "parent_bypassed":
            inner = replace(batch, context=replace(batch.context, conflict_id="nested-conflict"))
            decisions.event_log.append(
                "timing_batch_transition", {"transition": "opened", "batch": inner.to_payload()}
            )
            decisions.event_log.append(
                "timing_batch_transition",
                {"transition": "selected", "batch": inner.select("player-a").to_payload()},
            )
        trigger = RuleTrigger(
            RuleTriggerKind.MOVE_COMPLETION,
            {"trigger_event_id": "child"},
            batch.batch_id if case == "parent_bypassed" else None,
            "player-a" if case == "parent_bypassed" else None,
        )
        decisions.event_log.append("rule_trigger_observed", trigger.to_payload())
    with pytest.raises(GameLifecycleError, match=message):
        rule_trigger_history(decisions)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("late_observation", "observed at its source event"),
        ("missing_phase", "current phase and players"),
        ("missing_observation", "exact trigger observations"),
    ],
)
def test_destruction_observation_cannot_be_delayed_or_omitted(case: str, message: str) -> None:
    from warhammer40k_core.engine.model_destruction_triggers import (
        observe_model_destruction,
        validate_model_destruction_observations,
    )

    state, decisions, trigger = _destruction_fixture()
    assert isinstance(trigger.context, dict)
    event = next(
        row
        for row in decisions.event_log.records
        if row.event_id == trigger.context["trigger_event_id"]
    )
    if case == "missing_phase":
        state.battle_phase_index = None
    if case == "missing_observation":
        empty = DecisionController()
        empty.event_log.append(event.event_type, event.payload)
        with pytest.raises(GameLifecycleError, match=message):
            validate_model_destruction_observations(state=state, decisions=empty)
    else:
        with pytest.raises(GameLifecycleError, match=message):
            observe_model_destruction(state=state, decisions=decisions, event=event)
