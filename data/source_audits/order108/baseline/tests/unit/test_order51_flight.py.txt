from __future__ import annotations

import json
from dataclasses import replace
from math import isclose
from typing import cast

import pytest
from tests.phase15a_charge_test_support import (
    _charge_lifecycle,
    _compact_test_unit_poses,
    _decision_request,
    _state,
    _submit_option,
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.engine.charge_declaration import ChargeRollResult, ChargeRollResultPayload
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.geometry.pose import Pose


def _flight_catalog(*, hover: bool = False) -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                keywords=replace(
                    sheet.keywords,
                    keywords=(*sheet.keywords.keywords, "FLY", *(("HOVER",) if hover else ())),
                ),
            )
            if sheet.datasheet_id == "core-intercessor-like-infantry"
            else sheet
            for sheet in catalog.datasheets
        ),
    )


@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize("hover", [False, True])
@pytest.mark.parametrize("action", ["normal_move", "advance"])
def test_movement_flight_choice_precedes_roll_and_history_survives_shooting(
    selected: bool, hover: bool, action: str
) -> None:
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalPayload,
        MovementProposalRequest,
    )
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.geometry.pathing import PathWitness

    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("mover",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(30, 20), model_count=5),
        game_id=f"order51-movement-{selected}-{hover}-{action}",
        catalog=_flight_catalog(hover=hover),
    )
    state = _state(lifecycle)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    session = LocalGameSession(lifecycle=lifecycle)
    request = _decision_request(session.advance_until_decision_or_terminal())
    request = _decision_request(
        session.submit_option(
            request_id=request.request_id,
            option_id=units["mover"].unit_instance_id,
            result_id="select-mover",
        )
    )
    choices = tuple(
        option
        for option in request.options
        if isinstance(option.payload, dict)
        and option.payload.get("movement_phase_action") == action
    )
    assert len(choices) == 2
    assert not any(
        event.event_type == "advance_roll_resolved"
        for event in lifecycle.decision_controller.event_log.records
    )
    option = next(
        option
        for option in choices
        if isinstance(option.payload, dict)
        and (option.payload["movement_mode"] == "fly_take_to_skies") is selected
    )
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="select-flight"
    )
    request = _decision_request(status)
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(units["mover"].unit_instance_id)
    witness = PathWitness.for_paths(
        tuple(
            (
                model.model_instance_id,
                (
                    model.pose,
                    Pose.at(
                        model.pose.position.x + 2,
                        model.pose.position.y,
                        facing_degrees=model.pose.facing.degrees,
                    ),
                ),
            )
            for model in placement.model_placements
        )
    )
    assert isinstance(option.payload, dict)
    payload = MovementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=proposal.unit_instance_id,
        movement_phase_action=action,
        movement_mode=cast(str, option.payload["movement_mode"]),
        witness=witness,
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="move",
        payload=validate_json_value(payload.to_payload()),
    )
    assert len(state.model_movement_history) == 5
    assert all(
        isclose(row.distance_inches, 2.0, abs_tol=1e-9) for row in state.model_movement_history
    )
    assert state.current_battle_phase is BattlePhase.SHOOTING
    assert state.movement_phase_state is None
    checkpoint = cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    from warhammer40k_core.engine.phase import GameLifecycleError

    corrupted = cast(GameLifecyclePayload, json.loads(json.dumps(checkpoint)))
    assert corrupted["state"] is not None
    corrupted["state"]["model_movement_history"][0]["distance_inches"] = 1.0
    with pytest.raises(GameLifecycleError, match="differs from accepted movement evidence"):
        GameLifecycle.from_payload(corrupted)
    event = next(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "movement_activation_completed"
    )
    assert isinstance(event.payload, dict)
    movements = event.payload["model_movements"]
    assert isinstance(movements, list)
    for model_payload in movements:
        assert isinstance(model_payload, dict)
        assert model_payload["movement_distance_modifier_inches"] == (
            -2 if selected and not hover else 0
        )
    own = session.view(viewer_player_id="player-a")
    opponent = session.view(viewer_player_id="player-b")
    assert "model_movement_history" not in own
    assert "model_movement_history" not in opponent
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="flight-history"))
    assert replay.run().status is ReplayRunStatus.REPRODUCED


@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize("hover", [False, True])
def test_charge_flight_is_committed_before_dice_and_survives_restore(
    selected: bool, hover: bool
) -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                keywords=replace(
                    sheet.keywords,
                    keywords=(*sheet.keywords.keywords, "FLY", *(("HOVER",) if hover else ())),
                ),
            )
            if sheet.datasheet_id == "core-intercessor-like-infantry"
            else sheet
            for sheet in catalog.datasheets
        ),
    )
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("charger",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20, 20), model_count=5),
        game_id=f"order51-charge-{selected}-{hover}",
        catalog=catalog,
    )
    request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    unit_id = units["charger"].unit_instance_id
    walking = request.option_by_id(unit_id).payload
    assert isinstance(walking, dict)
    assert walking["take_to_the_skies"] is False
    flying = request.option_by_id(f"{unit_id}:take_to_the_skies")
    assert isinstance(flying.payload, dict)
    assert flying.payload["take_to_the_skies"] is True
    assert not any(
        e.event_type == "charge_roll_started"
        for e in lifecycle.decision_controller.event_log.records
    )
    _submit_option(
        lifecycle,
        request=request,
        option_id=flying.option_id if selected else unit_id,
        result_id="order51-charge-choice",
    )
    events = lifecycle.decision_controller.event_log.records
    choice_index = next(i for i, e in enumerate(events) if e.event_type == "charging_unit_selected")
    roll_index = next(i for i, e in enumerate(events) if e.event_type == "charge_roll_started")
    assert choice_index < roll_index
    payload = next(e.payload for e in events if e.event_type == "charge_roll_resolved")
    assert isinstance(payload, dict)
    roll = ChargeRollResult.from_payload(cast(ChargeRollResultPayload, payload["roll_result"]))
    assert roll.request.take_to_the_skies is selected
    penalty = 2 if selected and not hover else 0
    assert roll.movement_budget.maximum_distance_inches == max(0, roll.value - penalty)
    checkpoint = cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    phase = _state(lifecycle).charge_phase_state
    if phase is not None and phase.active_selection is not None:
        assert phase.active_selection.take_to_the_skies is selected


@pytest.mark.parametrize("selected", [False, True])
def test_mixed_unit_flight_benefits_belong_only_to_flying_models(selected: bool) -> None:
    from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
    from warhammer40k_core.engine.movement_legality import MovementCapabilitySet

    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("mixed",),
        catalog=_flight_catalog(),
        game_id="order51-mixed",
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(30, 20), model_count=5),
    )
    unit = units["mixed"]
    unit = replace(
        unit,
        own_models=tuple(
            model
            if index == 0
            else replace(
                model,
                keyword_assignment=replace(
                    model.keyword_assignment,
                    keywords=tuple(k for k in model.keywords if k != "FLY"),
                ),
            )
            for index, model in enumerate(unit.own_models)
        ),
    )
    for index, model in enumerate(unit.own_models):
        capabilities = MovementCapabilitySet.from_keywords(
            unit.keywords,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            movement_mode=MovementMode.CHARGE,
            take_to_the_skies=selected,
            unit=unit,
            model_instance_id=model.model_instance_id,
            current_model_instance_ids=tuple(m.model_instance_id for m in unit.own_models),
        )
        assert capabilities.has_fly is (index == 0)
        assert capabilities.can_move_through_models is (selected and index == 0)
        # Infantry retains its separate Ruins permission in either flight mode.
        assert capabilities.can_traverse_ruins_walls
        assert capabilities.ignores_vertical_distance is (selected and index == 0)
    assert _state(lifecycle).model_movement_history == []


def test_stale_charge_flight_is_rejected_before_queue_pop_or_roll() -> None:
    from tests.unit_keyword_helpers import with_unit_keywords

    from warhammer40k_core.engine.phase import LifecycleStatusKind

    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("charger",),
        catalog=_flight_catalog(),
        game_id="order51-stale",
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20, 20), model_count=5),
    )
    request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    state = _state(lifecycle)
    unit = units["charger"]
    grounded = with_unit_keywords(unit, keywords=tuple(k for k in unit.keywords if k != "FLY"))
    state.army_definitions = [
        replace(
            army,
            units=tuple(
                grounded if model_unit.unit_instance_id == unit.unit_instance_id else model_unit
                for model_unit in army.units
            ),
        )
        for army in state.army_definitions
    ]
    before = state.to_payload()
    count = len(lifecycle.decision_controller.records)
    status = _submit_option(
        lifecycle,
        request=request,
        option_id=f"{unit.unit_instance_id}:take_to_the_skies",
        result_id="stale-flight",
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.to_payload() == before
    assert len(lifecycle.decision_controller.records) == count
    assert lifecycle.decision_controller.queue.pending_requests[0] == request


def test_restore_rejects_changed_charge_flight_after_dice() -> None:
    from warhammer40k_core.engine.phase import GameLifecycleError

    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("charger",),
        catalog=_flight_catalog(),
        game_id="order51-restore",
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20, 20), model_count=5),
    )
    request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    _submit_option(
        lifecycle,
        request=request,
        option_id=units["charger"].unit_instance_id,
        result_id="select-ground",
    )
    checkpoint = cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
    raw = cast(dict[str, object], checkpoint["state"])
    phase = cast(dict[str, object], raw["charge_phase_state"])
    selection = cast(dict[str, object], phase["active_selection"])
    selection["take_to_the_skies"] = True
    with pytest.raises(GameLifecycleError, match="flight"):
        GameLifecycle.from_payload(checkpoint)


@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize("mixed", [False, True])
def test_heavy_uses_each_models_accepted_vertical_distance(selected: bool, mixed: bool) -> None:
    from math import sqrt

    from warhammer40k_core.core.ruleset_descriptor import MovementMode
    from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
    from warhammer40k_core.engine.model_movement_history import (
        models_within_turn_distance,
        validate_model_movement_history,
    )
    from warhammer40k_core.engine.move_completion_triggers import record_move_completion_event
    from warhammer40k_core.engine.phases.movement import resolve_normal_move
    from warhammer40k_core.geometry.pathing import PathWitness

    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("mover",),
        catalog=_flight_catalog(),
        game_id="order51-distance",
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(30, 20), model_count=5),
    )
    state = _state(lifecycle)
    unit = units["mover"]
    if mixed:
        unit = replace(
            unit,
            own_models=tuple(
                model
                if index == 0
                else replace(
                    model,
                    keyword_assignment=replace(
                        model.keyword_assignment,
                        keywords=tuple(k for k in model.keywords if k != "FLY"),
                    ),
                )
                for index, model in enumerate(unit.own_models)
            ),
        )
        state.army_definitions = [
            replace(
                army,
                units=tuple(
                    unit if item.unit_instance_id == unit.unit_instance_id else item
                    for item in army.units
                ),
            )
            for army in state.army_definitions
        ]
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    witness = PathWitness.for_paths(
        tuple(
            (
                model.model_instance_id,
                (
                    model.pose,
                    Pose.at(model.pose.position.x + 1, model.pose.position.y, 1.5),
                    Pose.at(model.pose.position.x + 2, model.pose.position.y),
                ),
            )
            for model in placement.model_placements
        )
    )
    resolution = resolve_normal_move(
        scenario=BattlefieldScenario(
            armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
        ),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=placement,
        path_witness=witness,
        movement_mode=MovementMode.FLY_TAKE_TO_SKIES if selected else MovementMode.NORMAL,
    )
    assert resolution.is_valid
    record_move_completion_event(
        state=state,
        decisions=lifecycle.decision_controller,
        event_type="movement_activation_completed",
        payload={
            **resolution.movement_payload,
            "transition_batch": validate_json_value(
                resolution.transition_batch(before=placement).to_payload()
            ),
            "witness": validate_json_value(witness.to_payload()),
            "game_id": state.game_id,
            "battle_round": 1,
            "active_player_id": "player-a",
            "phase": "movement",
            "movement_phase_action": "normal_move",
            "unit_instance_id": unit.unit_instance_id,
            "request_id": "distance-request",
            "result_id": "distance-result",
        },
    )
    rows = {row.model_instance_id: row for row in state.model_movement_history}
    for model in unit.own_models:
        expected = 2 if selected and "FLY" in model.keywords else sqrt(13)
        assert isclose(rows[model.model_instance_id].distance_inches, expected, abs_tol=1e-9)
    ids = tuple(model.model_instance_id for model in unit.own_models)
    assert models_within_turn_distance(state=state, model_ids=ids, maximum_inches=3) is (
        selected and not mixed
    )
    validate_model_movement_history(state, lifecycle.decision_controller.event_log.records)
    # Several individually short accepted moves accumulate within the turn.
    if selected and not mixed:
        record_move_completion_event(
            state=state,
            decisions=lifecycle.decision_controller,
            event_type="movement_activation_completed",
            payload={
                **resolution.movement_payload,
                "transition_batch": validate_json_value(
                    resolution.transition_batch(before=placement).to_payload()
                ),
                "witness": validate_json_value(witness.to_payload()),
                "game_id": state.game_id,
                "battle_round": 1,
                "active_player_id": "player-a",
                "phase": "shooting",
                "movement_phase_action": "normal_move",
                "unit_instance_id": unit.unit_instance_id,
                "request_id": "second-distance-request",
                "result_id": "second-distance-result",
            },
        )
        assert not models_within_turn_distance(state=state, model_ids=ids, maximum_inches=3)
        state.battle_round = 2
        assert models_within_turn_distance(state=state, model_ids=ids, maximum_inches=3)


@pytest.mark.parametrize("hover", [False, True])
@pytest.mark.parametrize("attached", [False, True])
def test_heroic_flight_is_selected_before_roll_and_penalty_follows_cap(
    hover: bool, attached: bool
) -> None:
    from tests.charge_reroll_helpers import heroic_session
    from tests.heroic_intervention_helpers import (
        add_heroic_modifier,
        latest_heroic_roll,
        use_heroic,
    )

    session, unit_id = heroic_session(
        natural=False, catalog=_flight_catalog(hover=hover), attached=attached
    )
    add_heroic_modifier(session, unit_id, delta=20)
    declaration = use_heroic(session, unit_id)
    session.submit_option(
        request_id=declaration.request_id,
        option_id=f"{unit_id}:take_to_the_skies",
        result_id="heroic-flight",
    )
    roll = latest_heroic_roll(session)
    assert roll.request.take_to_the_skies
    assert roll.value == 6
    assert roll.movement_budget.maximum_distance_inches == (6 if hover else 4)
    checkpoint = cast(GameLifecyclePayload, json.loads(json.dumps(session.lifecycle.to_payload())))
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint


def test_live_charge_flight_drift_rejects_before_recording_targets() -> None:
    from tests.charge_distance_helpers import add_modifier

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("charger",),
        catalog=_flight_catalog(),
        game_id="order51-live-drift",
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(20, 20), model_count=5),
    )
    state = _state(lifecycle)
    unit_id = units["charger"].unit_instance_id
    add_modifier(
        state,
        effect_id="test:guarantee-target-window",
        kind="modify_dice_roll",
        delta=20,
        unit_instance_id=unit_id,
    )
    session = LocalGameSession(lifecycle=lifecycle)
    selection = _decision_request(session.advance_until_decision_or_terminal())
    targets = _decision_request(
        session.submit_option(
            request_id=selection.request_id, option_id=unit_id, result_id="ground-charge"
        )
    )
    phase = state.charge_phase_state
    assert phase is not None
    assert phase.active_selection is not None
    state.replace_charge_phase_state(
        replace(phase, active_selection=replace(phase.active_selection, take_to_the_skies=True))
    )
    before = state.to_payload()
    count = len(lifecycle.decision_controller.records)
    status = session.submit_option(
        request_id=targets.request_id,
        option_id=targets.options[0].option_id,
        result_id="drifted-charge",
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.to_payload() == before
    assert len(lifecycle.decision_controller.records) == count
    assert lifecycle.decision_controller.queue.pending_requests[0] == targets


@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize("hover", [False, True])
def test_reactive_flight_is_bound_through_retry_and_restore(selected: bool, hover: bool) -> None:
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalPayload,
        MovementProposalRequest,
    )
    from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
    from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
    from warhammer40k_core.engine.triggered_movement import (
        TriggeredMovementDescriptor,
        TriggeredMovementEligibleUnit,
        TriggeredMovementKind,
    )
    from warhammer40k_core.engine.triggered_movement_selection import (
        triggered_movement_unit_selection_request,
    )
    from warhammer40k_core.geometry.pathing import PathWitness

    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("mover",),
        catalog=_flight_catalog(hover=hover),
        game_id="order51-reactive",
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(30, 20), model_count=5),
    )
    state = _state(lifecycle)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    descriptor = TriggeredMovementDescriptor(
        movement_kind=TriggeredMovementKind.TRIGGERED,
        source_rule_id="test:reactive-normal",
        trigger_timing=ReactionWindow(
            phase=BattlePhase.MOVEMENT,
            window_kind=ReactionWindowKind.RULE_TRIGGER,
            source_step=None,
            source_event_id=None,
        ),
        max_distance_inches=4,
    )
    unit_id = units["mover"].unit_instance_id
    request = triggered_movement_unit_selection_request(
        state=state,
        player_id="player-a",
        descriptor=descriptor,
        eligible_units=(
            TriggeredMovementEligibleUnit(
                unit_instance_id=unit_id,
                hook_id="test:normal-move",
                source_id=descriptor.source_rule_id,
            ),
        ),
    )
    lifecycle.decision_controller.request_decision(request)
    session = LocalGameSession(lifecycle=lifecycle)
    proposal_request = _decision_request(
        session.submit_option(
            request_id=request.request_id,
            option_id=f"triggered:{unit_id}" + (":take_to_the_skies" if selected else ""),
            result_id="reactive-flight",
        )
    )
    checkpoint = cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
    assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(unit_id)
    maximum_distance = 2.0 if selected and not hover else 4.0
    accepted_distance = min(maximum_distance, 3.0)
    for distance, result_id in (
        (maximum_distance + 1.0, "too-far"),
        (accepted_distance, "valid-retry"),
    ):
        proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
        assert proposal.context is not None
        assert proposal.context["take_to_the_skies"] is selected
        witness = PathWitness.for_straight_line_endpoints(
            tuple(
                (
                    model.model_instance_id,
                    model.pose,
                    Pose.at(model.pose.position.x + distance, model.pose.position.y),
                )
                for model in placement.model_placements
            )
        )
        payload = MovementProposalPayload(
            proposal_request_id=proposal.request_id,
            proposal_kind=proposal.proposal_kind,
            unit_instance_id=unit_id,
            movement_phase_action=cast(str, proposal.movement_phase_action),
            witness=witness,
        )
        before_battlefield = state.battlefield_state
        status = session.submit_parameterized_payload(
            request_id=proposal_request.request_id,
            payload=validate_json_value(payload.to_payload()),
            result_id=result_id,
        )
        if result_id == "too-far":
            assert status.status_kind is LifecycleStatusKind.INVALID
            assert state.battlefield_state == before_battlefield
            assert state.model_movement_history == []
            assert not any(
                event.event_type == "triggered_movement_resolved"
                for event in lifecycle.decision_controller.event_log.records
            )
            proposal_request = lifecycle.decision_controller.queue.pending_requests[0]
            checkpoint = cast(GameLifecyclePayload, json.loads(json.dumps(lifecycle.to_payload())))
            assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
        else:
            assert status.status_kind is not LifecycleStatusKind.INVALID
    assert len(state.model_movement_history) == 5
    assert all(
        isclose(row.distance_inches, accepted_distance, abs_tol=1e-9)
        for row in state.model_movement_history
    )
    completion = next(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "triggered_movement_resolved"
    )
    assert isinstance(completion.payload, dict)
    assert completion.payload["movement_inches"] == maximum_distance
    results = cast(list[dict[str, object]], completion.payload["path_validation_results"])
    assert len(results) == 5
    for result in results:
        witness_payload = cast(dict[str, object], result["movement_distance_witness"])
        budget = cast(dict[str, object], witness_payload["budget"])
        assert budget["max_distance_inches"] == maximum_distance


@pytest.mark.parametrize("selected", [False, True])
def test_fall_back_commits_flight_in_its_finite_mode_choice(selected: bool) -> None:
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalPayload,
        MovementProposalRequest,
    )
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.geometry.pathing import PathWitness

    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("mover",),
        catalog=_flight_catalog(),
        game_id="order51-fall-back",
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(10, 23), model_count=5),
    )
    state = _state(lifecycle)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    session = LocalGameSession(lifecycle=lifecycle)
    unit_id = units["mover"].unit_instance_id
    request = _decision_request(session.advance_until_decision_or_terminal())
    actions = _decision_request(
        session.submit_option(
            request_id=request.request_id, option_id=unit_id, result_id="fallback-unit"
        )
    )
    option_id = "fall_back:ordered_retreat" + (":fly_take_to_skies" if selected else "")
    request = _decision_request(
        session.submit_option(
            request_id=actions.request_id, option_id=option_id, result_id="fallback-flight"
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(unit_id)
    witness = PathWitness.for_straight_line_endpoints(
        tuple(
            (
                model.model_instance_id,
                model.pose,
                Pose.at(model.pose.position.x, model.pose.position.y - 2),
            )
            for model in placement.model_placements
        )
    )
    submission = MovementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=unit_id,
        movement_phase_action="fall_back",
        movement_mode="fly_take_to_skies" if selected else "fall_back",
        fall_back_mode="ordered_retreat",
        witness=witness,
    )
    session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="fallback-move",
        payload=validate_json_value(submission.to_payload()),
    )
    assert len(state.model_movement_history) == 5
    assert all(
        isclose(row.distance_inches, 2, abs_tol=1e-9) for row in state.model_movement_history
    )
