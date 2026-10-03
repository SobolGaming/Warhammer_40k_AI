"""Core 14.02: controlling units need positive OC, independently of model range."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from tests.order109_helpers import LEADER, SOURCE, SUPPORT, control_session

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlResult,
    ObjectiveControlScore,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.stratagems_generic_metadata import (
    controlled_objective_effect_selection_ids_for_binding,
    objective_marker_effect_selection,
    objective_selection_error,
)
from warhammer40k_core.engine.stratagems_model import (
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
)
from warhammer40k_core.engine.stratagems_targeting import (
    _target_unit_within_controlled_objective_range,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_objective_control import (
    boundary_unit_objective_control,
    current_unit_objective_control,
)


def test_control_requires_controller_and_range_even_with_positive_member() -> None:
    session = control_session(attached=True)
    state = session.lifecycle.state
    assert state is not None
    result = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.FIGHT,
        )
    ).results[0]
    control = current_unit_objective_control(state=state, unit_instance_id=SOURCE)
    assert control.controls(result)
    # A secured objective can retain player control at zero score, while unit
    # control still needs unit range and a positive member somewhere in that unit.
    secured = replace(
        result,
        scores=(ObjectiveControlScore("player-a", 0),),
        retained_control_source_id="source:secured",
    )
    assert control.controls(secured)
    assert not control.controls(replace(secured, contributors=()))
    assert not control.controls(
        replace(
            secured,
            controlled_by_player_id="player-b",
            scores=(ObjectiveControlScore("player-b", 0),),
        )
    )
    assert not control.controls(
        ObjectiveControlResult(
            objective_id=result.objective_id,
            status=ObjectiveControlStatus.CONTESTED,
            controlled_by_player_id=None,
            scores=(ObjectiveControlScore("player-a", 1), ObjectiveControlScore("player-b", 1)),
            contributors=result.contributors,
        )
    )


def test_positive_oc_uses_runtime_modifiers_and_battle_shock() -> None:
    from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm
    from warhammer40k_core.engine.runtime_modifiers import (
        ObjectiveControlModifierBinding,
        ObjectiveControlModifierContext,
        RuntimeModifierRegistry,
    )

    session = control_session()
    state = session.lifecycle.state
    assert state is not None
    result = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.FIGHT,
        )
    ).results[0]

    def bonus(context: ObjectiveControlModifierContext) -> tuple[ModifierTerm, ...]:
        return (
            (ModifierTerm(ModifierOperation.ADD, 1),) if context.unit_instance_id == SOURCE else ()
        )

    registry = RuntimeModifierRegistry.from_bindings(
        objective_control_modifier_bindings=(
            ObjectiveControlModifierBinding("order109:bonus", "source:order109:bonus", bonus),
        )
    )
    assert not current_unit_objective_control(state=state, unit_instance_id=SOURCE).controls(result)
    assert current_unit_objective_control(
        state=state, unit_instance_id=SOURCE, runtime_modifier_registry=registry
    ).controls(result)
    state.battle_shocked_unit_ids.append(SOURCE)
    assert not current_unit_objective_control(
        state=state, unit_instance_id=SOURCE, runtime_modifier_registry=registry
    ).controls(result)


@pytest.mark.parametrize("retained", [False, True])
def test_positive_member_follows_existing_rules_presence(retained: bool) -> None:
    from tests.fight_on_death_helpers import retain_destroyed_model_for_fixture
    from tests.order57_destroyed_referent_helpers import (
        destroy_and_remove_order57_model,
        set_order57_model_wounds,
    )

    session = control_session(attached=True)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    unit = rules_unit_view_by_id(state=state, unit_instance_id=SOURCE)
    leader = next(
        component.unit for component in unit.components if component.unit.unit_instance_id == LEADER
    )
    model = leader.own_models[0]
    placement = state.battlefield_state.model_placement_by_id(model.model_instance_id)
    if retained:
        set_order57_model_wounds(
            state, model_instance_id=model.model_instance_id, wounds_remaining=0
        )
        retain_destroyed_model_for_fixture(
            state=state,
            placement=placement,
            effect_id="order109:retained-leader",
            source_rule_id="source:order109:retained-leader",
            source_phase=BattlePhase.FIGHT,
            decisions=session.lifecycle.decision_controller,
        )
    else:
        destroy_and_remove_order57_model(
            state=state,
            event_log=session.lifecycle.decision_controller.event_log,
            model=model,
            cause_id="order109:removed-leader",
        )
    result = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state, timing=ObjectiveControlTiming.PHASE_END, phase=BattlePhase.FIGHT
        )
    ).results[0]
    assert result.controlled_by_player_id == "player-a"
    assert (
        current_unit_objective_control(state=state, unit_instance_id=SOURCE).controls(result)
        is retained
    )


def test_outside_range_member_gets_recorded_random_oc_preparation() -> None:
    from warhammer40k_core.core.attributes import Characteristic
    from warhammer40k_core.engine.random_objective_control import prepare_objective_control

    session = control_session(attached=True, random_oc=True)
    state = session.lifecycle.state
    assert state is not None
    context = ObjectiveControlContext.from_game_state(
        state,
        timing=ObjectiveControlTiming.PHASE_END,
        phase=BattlePhase.FIGHT,
    )
    prepared = prepare_objective_control(
        context,
        decisions=session.lifecycle.decision_controller,
        scope_id="order109:random",
    )
    result = resolve_objective_control(prepared).results[0]
    unit = rules_unit_view_by_id(state=state, unit_instance_id=LEADER)
    leader = next(
        component.unit for component in unit.components if component.unit.unit_instance_id == LEADER
    )
    assert all(
        model.characteristic(Characteristic.OBJECTIVE_CONTROL).is_numeric
        for model in leader.own_models
    )
    assert all(row.unit_instance_id != LEADER for row in result.contributors)
    assert current_unit_objective_control(state=state, unit_instance_id=SOURCE).controls(result)


def test_outside_range_member_gets_modifier_preparation() -> None:
    from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm
    from warhammer40k_core.engine.abilities import AbilityCatalogIndex
    from warhammer40k_core.engine.objective_control_modifier_evaluation import (
        evaluate_objective_control_modifiers,
    )
    from warhammer40k_core.engine.runtime_modifiers import (
        ObjectiveControlModifierBinding,
        ObjectiveControlModifierContext,
        RuntimeModifierRegistry,
    )

    session = control_session(attached=True)
    state = session.lifecycle.state
    assert state is not None

    def penalty(context: ObjectiveControlModifierContext) -> tuple[ModifierTerm, ...]:
        return (
            (ModifierTerm(ModifierOperation.SUBTRACT, 1),)
            if context.unit_instance_id == LEADER
            else ()
        )

    registry = RuntimeModifierRegistry.from_bindings(
        objective_control_modifier_bindings=(
            ObjectiveControlModifierBinding("order109:penalty", "source:order109:penalty", penalty),
        )
    )
    context = ObjectiveControlContext.from_game_state(
        state,
        timing=ObjectiveControlTiming.PHASE_END,
        phase=BattlePhase.FIGHT,
        runtime_modifier_registry=registry,
    )
    prepared = evaluate_objective_control_modifiers(
        context,
        decisions=session.lifecycle.decision_controller,
        occurrence_id="order109:oc",
        ability_indexes_by_player_id={
            player: AbilityCatalogIndex.from_records(()) for player in state.player_ids
        },
    )
    assert prepared.pending_status is None
    unit = rules_unit_view_by_id(state=state, unit_instance_id=SOURCE)
    leader_ids = {
        model.model_instance_id
        for component in unit.components
        if component.unit.unit_instance_id == LEADER
        for model in component.unit.own_models
    }
    assert leader_ids.issubset(dict(prepared.context.modifier_traces))
    result = resolve_objective_control(prepared.context).results[0]
    assert result.controlled_by_player_id == "player-a"
    assert not current_unit_objective_control(
        state=state,
        unit_instance_id=SOURCE,
        runtime_modifier_registry=prepared.context.runtime_modifier_registry,
    ).controls(result)


@pytest.mark.parametrize(
    ("source_oc", "attached", "expected"), [(0, False, False), (1, False, True), (0, True, True)]
)
def test_mission_completion_uses_frozen_all_model_control(
    source_oc: int, attached: bool, expected: bool
) -> None:
    from warhammer40k_core.engine.actions import MissionActionState
    from warhammer40k_core.engine.mission_action_policies import mission_action_policy_for_id
    from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
        PrimaryMissionActionCompletionEvidence,
    )
    from warhammer40k_core.engine.primary_mission_action_lifecycle_policy import (
        capture_primary_mission_action_completion_evidence,
        validate_primary_mission_action_completion_evidence,
    )
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

    session = control_session(source_oc=source_oc, attached=attached)
    state = session.lifecycle.state
    assert state is not None
    assert state.mission_setup is not None
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    target = record.results[0].objective_id
    unit = rules_unit_view_by_id(state=state, unit_instance_id=SOURCE)
    policy = mission_action_policy_for_id("maintain-control")
    # A real typed completion subject; facade start eligibility is covered by
    # the mission action suite. Here we isolate the changed completion predicate.
    action = MissionActionState.start(
        action_id="order109:completion",
        mission_action_id=policy.mission_action_id,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        target_id=target,
        condition_target_id=target,
        mission_id=policy.primary_mission_id,
        battle_round=state.battle_round,
        phase=BattlePhase.SHOOTING.value,
        start_timing=policy.start_timing,
        completion_timing=policy.completion_timing,
        eligible_unit_instance_ids=(unit.unit_instance_id,),
        interruption_conditions=(),
        scoring_source_id=policy.source_id,
        victory_points=0,
    )
    evidence = capture_primary_mission_action_completion_evidence(
        state=state,
        action=action,
        policy=policy,
        completed_phase=BattlePhase.FIGHT,
        objective_control_record=record,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert evidence.completion_condition_met is expected
    assert evidence.action_unit_contributor_model_instance_ids
    restored = PrimaryMissionActionCompletionEvidence.from_payload(
        json.loads(json.dumps(evidence.to_payload()))
    )
    assert (
        validate_primary_mission_action_completion_evidence(
            state=state,
            action=action,
            policy=policy,
            evidence=restored,
            objective_control_record=record,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("source_oc", "attached", "expected"), [(0, False, False), (1, False, True), (0, True, True)]
)
def test_shared_stratagem_control_separates_range_and_positive_oc(
    source_oc: int, attached: bool, expected: bool
) -> None:
    session = control_session(source_oc=source_oc, attached=attached)
    state = session.lifecycle.state
    assert state is not None
    assert state.mission_setup is not None
    marker = state.mission_setup.objective_markers[0]
    unit = rules_unit_view_by_id(state=state, unit_instance_id=SOURCE)
    result = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state, timing=ObjectiveControlTiming.PHASE_END, phase=BattlePhase.FIGHT
        )
    ).results[0]
    assert result.controlled_by_player_id == "player-a"
    assert current_unit_objective_control(state=state, unit_instance_id=SUPPORT).controls(result)
    assert (
        current_unit_objective_control(state=state, unit_instance_id=SOURCE).controls(result)
        is expected
    )
    if attached:
        assert LEADER in unit.component_unit_instance_ids
        assert all(row.unit_instance_id != LEADER for row in result.contributors)
        assert sum(row.effective_objective_control for row in result.contributors) == 1
    context = StratagemEligibilityContext(
        game_id=state.game_id,
        player_id="player-a",
        battle_round=state.battle_round,
        phase=BattlePhase.FIGHT,
        active_player_id="player-a",
        trigger_kind=TimingTriggerKind.END_PHASE,
    )
    binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id="player-a",
        target_unit_instance_id=unit.unit_instance_id,
    )
    assert controlled_objective_effect_selection_ids_for_binding(
        state=state, context=context, target_binding=binding
    ) == ((marker.objective_marker_id,) if expected else ())
    assert objective_selection_error(
        state=state,
        context=context,
        target_binding=binding,
        effect_selection=objective_marker_effect_selection(marker.objective_marker_id),
    ) == (None if expected else "no_controlled_objective_marker")
    # Source clauses requiring only range of a player-controlled objective still allow OC0.
    assert _target_unit_within_controlled_objective_range(
        state=state,
        player_id="player-a",
        context=context,
        target_binding=binding,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
    )


@pytest.mark.parametrize("within_range", [False, True])
def test_stratagem_selection_only_resolves_oc_for_in_range_candidates(within_range: bool) -> None:
    from warhammer40k_core.core.attributes import Characteristic
    from warhammer40k_core.engine.random_objective_control import prepare_objective_control
    from warhammer40k_core.geometry.pose import Pose

    session = control_session(attached=True, random_oc=True)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    if not within_range:
        battlefield = state.battlefield_state
        for component_id in (SOURCE, LEADER):
            placement = battlefield.unit_placement_by_id(component_id)
            battlefield = battlefield.with_unit_placement(
                placement.with_model_placements(
                    tuple(
                        model.with_pose(Pose.at(model.pose.position.x, model.pose.position.y - 12))
                        for model in placement.model_placements
                    )
                )
            )
        state.battlefield_state = battlefield
    session = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    state = session.lifecycle.state
    assert state is not None
    assert state.mission_setup is not None
    prepared = prepare_objective_control(
        ObjectiveControlContext.from_game_state(
            state, timing=ObjectiveControlTiming.PHASE_END, phase=BattlePhase.FIGHT
        ),
        decisions=session.lifecycle.decision_controller,
        scope_id="order109:candidate-preparation",
    )
    result = resolve_objective_control(prepared).results[0]
    assert result.controlled_by_player_id == "player-a"
    assert all(row.unit_instance_id != LEADER for row in result.contributors)
    assert any(row.unit_instance_id == SOURCE for row in result.contributors) is within_range
    unit = rules_unit_view_by_id(state=state, unit_instance_id=SOURCE)
    leader = next(
        component.unit for component in unit.components if component.unit.unit_instance_id == LEADER
    )
    assert (
        leader.own_models[0].characteristic(Characteristic.OBJECTIVE_CONTROL).is_numeric
        is within_range
    )
    context = StratagemEligibilityContext(
        game_id=state.game_id,
        player_id="player-a",
        battle_round=state.battle_round,
        phase=BattlePhase.FIGHT,
        active_player_id="player-a",
        trigger_kind=TimingTriggerKind.END_PHASE,
    )
    binding = StratagemTargetBinding(
        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
        target_player_id="player-a",
        target_unit_instance_id=SOURCE,
    )
    marker_id = state.mission_setup.objective_markers[0].objective_marker_id
    assert controlled_objective_effect_selection_ids_for_binding(
        state=state, context=context, target_binding=binding
    ) == ((marker_id,) if within_range else ())
    assert objective_selection_error(
        state=state,
        context=context,
        target_binding=binding,
        effect_selection=objective_marker_effect_selection(marker_id),
    ) == (None if within_range else "no_controlled_objective_marker")


@pytest.mark.parametrize(
    ("source_oc", "attached", "expected"), [(0, False, False), (1, False, True), (0, True, True)]
)
def test_frozen_unit_control_survives_facade_boundary_restore_and_exact_replay(
    source_oc: int, attached: bool, expected: bool
) -> None:
    session = control_session(source_oc=source_oc, attached=attached)
    initial = session.lifecycle.to_payload()
    session.advance_until_decision_or_terminal()
    state = session.lifecycle.state
    assert state is not None
    record = next(
        row
        for row in state.objective_control_records
        if row.timing is ObjectiveControlTiming.TURN_END
    )
    unit = rules_unit_view_by_id(state=state, unit_instance_id=SOURCE)
    control = boundary_unit_objective_control(
        state=state,
        record_id=record.record_id,
        player_id="player-a",
        unit_identity_ids=(unit.unit_instance_id, *unit.component_unit_instance_ids),
    )
    assert control.controls(record.results[0]) is expected
    assert record.results[0].controlled_by_player_id == "player-a"
    persisted = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(persisted)))
    assert restored.to_persistence_payload() == persisted
    for viewer in state.player_ids:
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    artifact = ReplayArtifact.capture(
        artifact_id="order109:replay",
        initial_lifecycle_payload=initial,
        final_lifecycle=session.lifecycle,
    )
    assert (
        ReplayRunner.from_payload(artifact.to_payload()).run().status is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("score_first", [False, True])
def test_mixed_unit_mission_action_facade_restore_and_exact_replay(score_first: bool) -> None:
    from warhammer40k_core.engine.actions import MissionActionStatus

    session = control_session(attached=True, primary_mission=True)
    initial = session.lifecycle.to_payload()
    state = session.lifecycle.state
    assert state is not None
    unit = rules_unit_view_by_id(state=state, unit_instance_id=SOURCE)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    assert request.decision_type == "start_mission_action"
    option = next(
        option
        for option in request.options
        if option.option_id.startswith(f"start:maintain-control:{unit.unit_instance_id}:")
    )
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="order109:action-start"
    )
    request = status.decision_request
    assert request is not None
    assert request.decision_type == "select_shooting_unit"
    status = session.submit_option(
        request_id=request.request_id,
        option_id="complete_shooting_phase",
        result_id="order109:shooting-complete",
    )
    request = status.decision_request
    assert request is not None
    assert request.decision_type == "resolve_sequencing_order"
    record = next(
        row
        for row in state.objective_control_records
        if row.timing is ObjectiveControlTiming.TURN_END
    )
    action = state.mission_action_states[0]
    result = next(result for result in record.results if result.objective_id == action.target_id)
    assert result.controlled_by_player_id == "player-a"
    assert any(row.unit_instance_id == SOURCE for row in result.contributors)
    assert all(row.unit_instance_id != LEADER for row in result.contributors)
    assert all(
        row.effective_objective_control == 0
        for row in result.contributors
        if row.unit_instance_id == SOURCE
    )
    pending = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(pending)))
    assert restored.to_persistence_payload() == pending
    prefix = "next:primary-scoring:" if score_first else "next:primary-action:"
    choice = next(
        option.option_id for option in request.options if option.option_id.startswith(prefix)
    )
    for active in (session, restored):
        active.submit_option(
            request_id=request.request_id, option_id=choice, result_id="order109:sequence"
        )
        active_state = active.lifecycle.state
        assert active_state is not None
        assert active_state.mission_action_states[0].status is MissionActionStatus.COMPLETED
        assert any(
            marker.source_action_id == action.action_id
            for marker in active_state.primary_mission_progress_state.markers
        )
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    completed = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    assert completed.to_persistence_payload() == session.to_persistence_payload()
    for viewer in state.player_ids:
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    artifact = ReplayArtifact.capture(
        artifact_id="order109:mission-replay",
        initial_lifecycle_payload=initial,
        final_lifecycle=session.lifecycle,
    )
    assert (
        ReplayRunner.from_payload(artifact.to_payload()).run().status is ReplayRunStatus.REPRODUCED
    )
