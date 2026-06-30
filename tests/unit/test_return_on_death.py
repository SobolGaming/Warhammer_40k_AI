from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import DiceExpression, DiceRollResult, DiceRollSpec
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine import (
    catalog_return_on_death_runtime as catalog_return_on_death_runtime_module,
)
from warhammer40k_core.engine import return_on_death as return_on_death_module
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.catalog_return_on_death_runtime import CatalogReturnOnDeathRuntime
from warhammer40k_core.engine.catalog_rule_consumption import catalog_rule_clauses_from_record
from warhammer40k_core.engine.command_points import initial_command_point_ledgers
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.return_on_death import (
    SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
    PendingReturnOnDeath,
    ReturnDestroyedTargetScope,
    ReturnRestoreWoundsMode,
    apply_return_on_death_placement_decision,
    build_return_on_death_placement_request,
    invalid_return_on_death_placement_status,
    resolve_pending_return_on_death_phase_end,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import initial_victory_point_ledgers
from warhammer40k_core.engine.sticky_objective_control import PhaseEndObjectiveControlContext
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText

FIRST_DEATH_RETURN_TEXT = (
    "The first time this model is destroyed, at the end of the phase, roll one D6: on "
    "a 2+, set this model back up on the battlefield as close as possible to where it "
    "was destroyed and not within Engagement Range of one or more enemy units, with "
    "3 wounds remaining."
)


def test_return_on_death_failed_roll_resolves_without_restoring_target() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    pending = _pending_return_on_death(state=state, success_threshold=5)
    state.record_pending_return_on_death(pending)
    decisions = DecisionController()
    manager = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
        injected_results=(_roll_result(pending=pending, value=1),),
    )

    request = resolve_pending_return_on_death_phase_end(
        state=state,
        decisions=decisions,
        dice_manager=manager,
    )

    assert request is None
    assert state.pending_return_on_death_by_id(pending.pending_id).resolved
    assert state.battlefield_state is not None
    assert set(_beta_unit(state).own_model_ids()) <= set(state.battlefield_state.removed_model_ids)


def test_return_on_death_success_requests_placement_and_rejects_engagement_range() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    pending = _pending_return_on_death(state=state, success_threshold=2)
    state.record_pending_return_on_death(pending)
    decisions = DecisionController()
    manager = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
        injected_results=(_roll_result(pending=pending, value=6),),
    )

    request = resolve_pending_return_on_death_phase_end(
        state=state,
        decisions=decisions,
        dice_manager=manager,
    )

    assert request is not None
    assert request.decision_type == SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE
    alpha_pose = _first_alpha_model_pose(state)
    result = _placement_result(
        request=request,
        placement=_unit_placement_for_unit(
            state=state,
            unit=_beta_unit(state),
            x=alpha_pose.position.x,
            y=alpha_pose.position.y,
        ),
    )
    status = invalid_return_on_death_placement_status(
        state=state,
        request=request,
        result=result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )

    assert status is not None
    assert not state.pending_return_on_death_by_id(pending.pending_id).resolved


def test_return_on_death_full_health_restores_unit_and_battlefield_placement() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    pending = _pending_return_on_death(state=state, success_threshold=2)
    state.record_pending_return_on_death(pending)
    decisions = DecisionController()
    request = build_return_on_death_placement_request(state=state, pending=pending)
    result = _placement_result(
        request=request,
        placement=_unit_placement_for_unit(state=state, unit=_beta_unit(state), x=20.0, y=20.0),
    )

    resolved = apply_return_on_death_placement_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )

    assert resolved.resolved
    assert all(
        model.wounds_remaining == model.starting_wounds for model in _beta_unit(state).own_models
    )
    assert state.battlefield_state is not None
    assert not (
        set(_beta_unit(state).own_model_ids()) & set(state.battlefield_state.removed_model_ids)
    )


def test_return_on_death_fixed_wounds_restores_exact_remaining_wounds() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    pending = _pending_return_on_death(
        state=state,
        target_scope=ReturnDestroyedTargetScope.DESTROYED_MODEL,
        restore_mode=ReturnRestoreWoundsMode.FIXED_REMAINING,
        wounds_remaining=1,
    )
    state.record_pending_return_on_death(pending)
    decisions = DecisionController()
    request = build_return_on_death_placement_request(state=state, pending=pending)
    destroyed_model_id = pending.destroyed_model_instance_id
    assert destroyed_model_id is not None
    result = _placement_result(
        request=request,
        placement=_unit_placement_for_model(
            state=state,
            unit=_beta_unit(state),
            model_instance_id=destroyed_model_id,
            x=20.0,
            y=20.0,
        ),
    )

    resolved = apply_return_on_death_placement_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )

    returned_model = next(
        model
        for model in _beta_unit(state).own_models
        if model.model_instance_id == destroyed_model_id
    )
    assert resolved.resolved
    assert returned_model.wounds_remaining == 1
    assert state.battlefield_state is not None
    assert destroyed_model_id not in state.battlefield_state.removed_model_ids


def test_return_on_death_stale_pending_submission_rejects_before_mutation() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    pending = _pending_return_on_death(state=state)
    state.record_pending_return_on_death(pending)
    request = build_return_on_death_placement_request(state=state, pending=pending)
    state.resolve_pending_return_on_death(pending.pending_id)
    result = _placement_result(
        request=request,
        placement=_unit_placement_for_unit(state=state, unit=_beta_unit(state), x=20.0, y=20.0),
    )

    status = invalid_return_on_death_placement_status(
        state=state,
        request=request,
        result=result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )

    assert status is not None
    assert state.battlefield_state is not None
    assert set(_beta_unit(state).own_model_ids()) <= set(state.battlefield_state.removed_model_ids)


def test_return_on_death_rejects_zero_fixed_wounds_before_runtime_mutation() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    with pytest.raises(GameLifecycleError, match="wounds_remaining"):
        _pending_return_on_death(
            state=state,
            target_scope=ReturnDestroyedTargetScope.DESTROYED_MODEL,
            restore_mode=ReturnRestoreWoundsMode.FIXED_REMAINING,
            wounds_remaining=0,
        )


def test_return_on_death_pending_payload_round_trips() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    pending = _pending_return_on_death(state=state)

    assert PendingReturnOnDeath.from_payload(pending.to_payload()) == pending


def test_return_on_death_runtime_empty_indexes_have_no_hooks() -> None:
    state = _battle_state_with_scenario()
    runtime = CatalogReturnOnDeathRuntime(
        ability_indexes_by_player_id={
            "player-a": AbilityCatalogIndex.from_records(()),
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        armies=tuple(state.army_definitions),
    )

    assert runtime.unit_destroyed_bindings() == ()
    assert runtime.phase_end_bindings() == ()


def test_return_on_death_runtime_fail_fast_and_phase_end_filter_paths() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    beta = _beta_unit(state)
    destroyed_model_id = beta.own_models[0].model_instance_id
    current_phase = state.current_battle_phase
    assert current_phase is not None
    context = UnitDestroyedContext(
        state=state,
        decisions=DecisionController(),
        completed_phase=current_phase,
        model_destroyed_event_id="event:return-runtime",
        model_destroyed_payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": current_phase.value,
            "destroying_player_id": "player-a",
            "target_unit_instance_id": beta.unit_instance_id,
            "model_instance_id": destroyed_model_id,
            "destroyed_model_placement": {"source": "runtime-test"},
        },
        destroying_player_id="player-a",
        destroyed_unit_instance_id=beta.unit_instance_id,
        destroyed_player_id="player-b",
    )
    runtime_missing_index = CatalogReturnOnDeathRuntime(
        ability_indexes_by_player_id={},
        armies=tuple(state.army_definitions),
    )
    with pytest.raises(GameLifecycleError, match="missing player ability index"):
        runtime_missing_index.unit_destroyed_handler(context)

    runtime = CatalogReturnOnDeathRuntime(
        ability_indexes_by_player_id={
            "player-b": AbilityCatalogIndex.from_records((_return_on_death_record(),))
        },
        armies=tuple(state.army_definitions),
    )
    with pytest.raises(GameLifecycleError, match="destroyed player drift"):
        runtime.unit_destroyed_handler(
            replace(context, destroying_player_id="player-b", destroyed_player_id="player-a")
        )

    filtered_state = _battle_state_with_scenario()
    filtered_decisions = DecisionController()
    filtered_phase = filtered_state.current_battle_phase
    assert filtered_phase is not None
    filtered_decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": "other-game",
            "battle_round": filtered_state.battle_round,
            "active_player_id": filtered_state.active_player_id,
            "phase": filtered_phase.value,
            "target_unit_instance_id": _beta_unit(filtered_state).unit_instance_id,
            "model_instance_id": _beta_unit(filtered_state).own_models[0].model_instance_id,
        },
    )
    filtered_decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": filtered_state.game_id,
            "battle_round": filtered_state.battle_round + 1,
            "active_player_id": filtered_state.active_player_id,
            "phase": filtered_phase.value,
            "target_unit_instance_id": _beta_unit(filtered_state).unit_instance_id,
            "model_instance_id": _beta_unit(filtered_state).own_models[0].model_instance_id,
        },
    )
    filtered_decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": filtered_state.game_id,
            "battle_round": filtered_state.battle_round,
            "active_player_id": "player-b",
            "phase": filtered_phase.value,
            "target_unit_instance_id": _beta_unit(filtered_state).unit_instance_id,
            "model_instance_id": _beta_unit(filtered_state).own_models[0].model_instance_id,
        },
    )
    filtered_decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": filtered_state.game_id,
            "battle_round": filtered_state.battle_round,
            "active_player_id": filtered_state.active_player_id,
            "phase": "movement",
            "target_unit_instance_id": _beta_unit(filtered_state).unit_instance_id,
            "model_instance_id": _beta_unit(filtered_state).own_models[0].model_instance_id,
        },
    )
    runtime.phase_end_handler(
        PhaseEndObjectiveControlContext(
            state=filtered_state,
            event_log=filtered_decisions.event_log,
            completed_phase=filtered_phase,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
    )
    assert filtered_state.pending_return_on_death == []

    malformed_event_decisions = DecisionController()
    malformed_event_decisions.event_log.append("model_destroyed", [])
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        runtime.phase_end_handler(
            PhaseEndObjectiveControlContext(
                state=filtered_state,
                event_log=malformed_event_decisions.event_log,
                completed_phase=filtered_phase,
                runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            )
        )

    missing_index_state = _battle_state_with_scenario()
    missing_index_decisions = DecisionController()
    missing_index_phase = missing_index_state.current_battle_phase
    assert missing_index_phase is not None
    missing_index_beta = _beta_unit(missing_index_state)
    missing_index_decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": missing_index_state.game_id,
            "battle_round": missing_index_state.battle_round,
            "active_player_id": missing_index_state.active_player_id,
            "phase": missing_index_phase.value,
            "target_unit_instance_id": missing_index_beta.unit_instance_id,
            "model_instance_id": missing_index_beta.own_models[0].model_instance_id,
        },
    )
    with pytest.raises(GameLifecycleError, match="missing player ability index"):
        runtime_missing_index.phase_end_handler(
            PhaseEndObjectiveControlContext(
                state=missing_index_state,
                event_log=missing_index_decisions.event_log,
                completed_phase=missing_index_phase,
                runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            )
        )


def test_first_death_return_unit_destroyed_hook_records_pending_once() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    beta = _beta_unit(state)
    destroyed_model_id = beta.own_models[0].model_instance_id
    decisions = DecisionController()
    runtime = CatalogReturnOnDeathRuntime(
        ability_indexes_by_player_id={
            "player-b": AbilityCatalogIndex.from_records((_return_on_death_record(),))
        },
        armies=tuple(state.army_definitions),
    )
    current_phase = state.current_battle_phase
    assert current_phase is not None
    context = UnitDestroyedContext(
        state=state,
        decisions=decisions,
        completed_phase=current_phase,
        model_destroyed_event_id="event:unit-destroyed-return",
        model_destroyed_payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": current_phase.value,
            "destroying_player_id": "player-a",
            "target_unit_instance_id": beta.unit_instance_id,
            "model_instance_id": destroyed_model_id,
            "destroyed_model_placement": {"source": "unit-destroyed-test"},
        },
        destroying_player_id="player-a",
        destroyed_unit_instance_id=beta.unit_instance_id,
        destroyed_player_id="player-b",
    )

    bindings = runtime.unit_destroyed_bindings()
    runtime.unit_destroyed_handler(context)
    runtime.unit_destroyed_handler(context)

    assert len(bindings) == 1
    assert len(state.pending_return_on_death) == 1
    assert state.pending_return_on_death[0].destroyed_model_instance_id == destroyed_model_id


def test_return_on_death_catalog_helpers_reject_malformed_runtime_shapes() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    beta = _beta_unit(state)
    record = _return_on_death_record()
    clause = catalog_rule_clauses_from_record(record)[0]
    current_phase = state.current_battle_phase
    assert current_phase is not None
    destroyed_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": state.active_player_id,
        "phase": current_phase.value,
        "destroying_player_id": "player-a",
        "target_unit_instance_id": beta.unit_instance_id,
        "model_instance_id": beta.own_models[0].model_instance_id,
        "destroyed_model_placement": {"source": "catalog-helper-test"},
    }

    with pytest.raises(GameLifecycleError, match="requires GameState"):
        catalog_return_on_death_runtime_module._pending_return_on_death_for_event(  # pyright: ignore[reportPrivateUsage]
            state=object(),
            completed_phase=current_phase.value,
            model_destroyed_event_id="event:bad-state",
            model_destroyed_payload=destroyed_payload,
            destroyed_player_id="player-b",
            destroyed_unit_instance_id=beta.unit_instance_id,
            record=record,
            clause=clause,
        )
    with pytest.raises(GameLifecycleError, match="missing return effect"):
        catalog_return_on_death_runtime_module._return_effect_parameters(  # pyright: ignore[reportPrivateUsage]
            replace(clause, effects=())
        )
    with pytest.raises(GameLifecycleError, match="missing dice gate"):
        catalog_return_on_death_runtime_module._roll_gate_parameters(  # pyright: ignore[reportPrivateUsage]
            replace(clause, conditions=())
        )
    with pytest.raises(GameLifecycleError, match="missing trigger"):
        catalog_return_on_death_runtime_module._target_scope_for_trigger(  # pyright: ignore[reportPrivateUsage]
            replace(clause, trigger=None)
        )

    pending = catalog_return_on_death_runtime_module._pending_return_on_death_for_event(  # pyright: ignore[reportPrivateUsage]
        state=state,
        completed_phase=current_phase.value,
        model_destroyed_event_id="event:pending",
        model_destroyed_payload=destroyed_payload,
        destroyed_player_id="player-b",
        destroyed_unit_instance_id=beta.unit_instance_id,
        record=record,
        clause=clause,
    )
    assert pending is not None
    state.return_on_death_consumed_keys.append(pending.consumed_key())
    assert not catalog_return_on_death_runtime_module._record_pending_return_on_death(  # pyright: ignore[reportPrivateUsage]
        pending=pending,
        event_log=DecisionController().event_log,
        state=state,
        phase=current_phase.value,
        model_destroyed_event_id="event:pending",
    )
    with pytest.raises(GameLifecycleError, match="capture requires GameState"):
        catalog_return_on_death_runtime_module._record_pending_return_on_death(  # pyright: ignore[reportPrivateUsage]
            pending=pending,
            event_log=DecisionController().event_log,
            state=object(),
            phase=current_phase.value,
            model_destroyed_event_id="event:pending",
        )
    with pytest.raises(GameLifecycleError, match="phase-end capture requires context"):
        catalog_return_on_death_runtime_module._model_destroyed_events_for_phase(  # pyright: ignore[reportPrivateUsage]
            cast(PhaseEndObjectiveControlContext, object())
        )
    with pytest.raises(GameLifecycleError, match="could not find destroyed unit"):
        catalog_return_on_death_runtime_module._army_and_unit_for_unit_id(  # pyright: ignore[reportPrivateUsage]
            armies=tuple(state.army_definitions),
            unit_instance_id="unit:missing",
        )
    with pytest.raises(GameLifecycleError, match="could not find destroyed model"):
        catalog_return_on_death_runtime_module._model_by_id(  # pyright: ignore[reportPrivateUsage]
            unit=beta,
            model_instance_id="model:missing",
        )

    assert not catalog_return_on_death_runtime_module._record_source_matches_destroyed_target(  # pyright: ignore[reportPrivateUsage]
        record=AbilityCatalogRecord(
            record_id="record:core-return",
            definition=record.definition,
            source_kind=AbilitySourceKind.CORE,
        ),
        unit=beta,
        destroyed_model_instance_id=beta.own_models[0].model_instance_id,
        target_scope=ReturnDestroyedTargetScope.DESTROYED_UNIT,
    )
    assert not catalog_return_on_death_runtime_module._record_source_matches_destroyed_target(  # pyright: ignore[reportPrivateUsage]
        record=AbilityCatalogRecord(
            record_id="record:wargear-return",
            definition=record.definition,
            source_kind=AbilitySourceKind.WARGEAR,
            datasheet_id=beta.datasheet_id,
            wargear_id="wargear:missing",
        ),
        unit=beta,
        destroyed_model_instance_id=beta.own_models[0].model_instance_id,
        target_scope=ReturnDestroyedTargetScope.DESTROYED_UNIT,
    )


def test_return_on_death_defensive_validation_rejects_malformed_pending_records() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    pending = _pending_return_on_death(state=state)
    malformed_pending_calls: tuple[Callable[[], PendingReturnOnDeath], ...] = (
        lambda: replace(
            pending,
            target_scope=ReturnDestroyedTargetScope.DESTROYED_MODEL,
            destroyed_model_instance_id=None,
        ),
        lambda: replace(pending, engagement_range_restriction=False),
        lambda: replace(
            pending,
            restore_wounds_mode=ReturnRestoreWoundsMode.FULL_HEALTH,
            wounds_remaining=1,
        ),
        lambda: replace(pending, roll_count=0),
        lambda: replace(pending, success_threshold=1),
        lambda: replace(pending, resolved=cast(bool, "no")),
    )

    for malformed_pending_call in malformed_pending_calls:
        with pytest.raises(GameLifecycleError):
            malformed_pending_call()

    resolved = _pending_return_on_death(state=state, success_threshold=2).mark_resolved()
    assert resolved.mark_resolved() == resolved


def test_return_on_death_decision_and_restore_defensive_paths() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    pending = _pending_return_on_death(state=state)
    state.record_pending_return_on_death(pending)
    request = build_return_on_death_placement_request(state=state, pending=pending)
    placement = _unit_placement_for_unit(state=state, unit=_beta_unit(state), x=20.0, y=20.0)
    result = _placement_result(request=request, placement=placement)
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()

    malformed_inputs = (
        (
            replace(request, decision_type="other_decision"),
            result,
        ),
        (
            replace(
                request,
                payload={
                    **cast(dict[str, JsonValue], request.payload),
                    "submission_kind": "other_submission",
                },
            ),
            result,
        ),
        (
            request,
            replace(result, actor_id="player-a"),
        ),
        (
            request,
            replace(
                result,
                payload={
                    "submission_kind": SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
                    "attempted_placement": "not-an-object",
                },
            ),
        ),
    )
    for malformed_request, malformed_result in malformed_inputs:
        assert (
            invalid_return_on_death_placement_status(
                state=state,
                request=malformed_request,
                result=malformed_result,
                ruleset_descriptor=descriptor,
            )
            is not None
        )

    with pytest.raises(GameLifecycleError, match="placement requires RulesetDescriptor"):
        return_on_death_module._validate_return_on_death_placement(  # pyright: ignore[reportPrivateUsage]
            state=state,
            pending=pending,
            placement=placement,
            ruleset_descriptor=cast(RulesetDescriptor, object()),
        )
    no_battlefield_state = _battle_state_with_destroyed_beta_unit()
    no_battlefield_state.battlefield_state = None
    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        return_on_death_module._validate_return_on_death_placement(  # pyright: ignore[reportPrivateUsage]
            state=no_battlefield_state,
            pending=_pending_return_on_death(state=no_battlefield_state),
            placement=placement,
            ruleset_descriptor=descriptor,
        )
    with pytest.raises(GameLifecycleError, match="currently supports exactly one D6"):
        return_on_death_module._return_on_death_roll_spec(  # pyright: ignore[reportPrivateUsage]
            state=state,
            pending=replace(pending, roll_count=2),
        )
    with pytest.raises(GameLifecycleError, match="requires pending record"):
        build_return_on_death_placement_request(
            state=state,
            pending=cast(PendingReturnOnDeath, object()),
        )
    with pytest.raises(GameLifecycleError, match="model is unknown"):
        return_on_death_module._model_by_id(  # pyright: ignore[reportPrivateUsage]
            state=state,
            model_instance_id="model:missing",
        )
    with pytest.raises(GameLifecycleError, match="unit is unknown"):
        return_on_death_module._unit_by_id(  # pyright: ignore[reportPrivateUsage]
            state=state,
            unit_instance_id="unit:missing",
        )
    with pytest.raises(GameLifecycleError, match="cannot update an unknown model"):
        return_on_death_module._army_definitions_with_model_wounds(  # pyright: ignore[reportPrivateUsage]
            armies=tuple(state.army_definitions),
            model_instance_id="model:missing",
            wounds_remaining=1,
        )
    with pytest.raises(GameLifecycleError, match="cannot update an unknown unit"):
        return_on_death_module._army_definitions_with_unit_full_health(  # pyright: ignore[reportPrivateUsage]
            armies=tuple(state.army_definitions),
            unit_instance_id="unit:missing",
        )


def test_return_on_death_defensive_helpers_reject_malformed_payloads() -> None:
    malformed_calls = (
        lambda: return_on_death_module._payload_object([]),  # pyright: ignore[reportPrivateUsage]
        lambda: return_on_death_module._payload_string(  # pyright: ignore[reportPrivateUsage]
            {},
            key="pending_id",
        ),
        lambda: return_on_death_module._target_scope_from_token(  # pyright: ignore[reportPrivateUsage]
            1
        ),
        lambda: return_on_death_module._target_scope_from_token(  # pyright: ignore[reportPrivateUsage]
            "unsupported"
        ),
        lambda: return_on_death_module._restore_wounds_mode_from_token(  # pyright: ignore[reportPrivateUsage]
            1
        ),
        lambda: return_on_death_module._restore_wounds_mode_from_token(  # pyright: ignore[reportPrivateUsage]
            "unsupported"
        ),
        lambda: return_on_death_module._validate_supported_token(  # pyright: ignore[reportPrivateUsage]
            "placement_anchor",
            "anywhere",
            supported=("destroyed_position",),
        ),
        lambda: return_on_death_module._validate_identifier(  # pyright: ignore[reportPrivateUsage]
            "pending_id",
            1,
        ),
        lambda: return_on_death_module._validate_identifier(  # pyright: ignore[reportPrivateUsage]
            "pending_id",
            "",
        ),
        lambda: return_on_death_module._validate_non_negative_int(  # pyright: ignore[reportPrivateUsage]
            "source_effect_index",
            -1,
        ),
        lambda: return_on_death_module._validate_positive_int(  # pyright: ignore[reportPrivateUsage]
            "roll_count",
            0,
        ),
        lambda: return_on_death_module._validate_d6_threshold(  # pyright: ignore[reportPrivateUsage]
            "success_threshold",
            7,
        ),
    )

    for malformed_call in malformed_calls:
        with pytest.raises(GameLifecycleError):
            malformed_call()


def test_return_on_death_placement_validation_rejects_wrong_target_shapes() -> None:
    state = _battle_state_with_destroyed_beta_unit()
    pending = _pending_return_on_death(
        state=state,
        target_scope=ReturnDestroyedTargetScope.DESTROYED_MODEL,
        restore_mode=ReturnRestoreWoundsMode.FIXED_REMAINING,
        wounds_remaining=1,
    )
    state.record_pending_return_on_death(pending)
    request = build_return_on_death_placement_request(state=state, pending=pending)
    result = _placement_result(
        request=request,
        placement=_unit_placement_for_unit(state=state, unit=_beta_unit(state), x=20.0, y=20.0),
    )

    status = invalid_return_on_death_placement_status(
        state=state,
        request=request,
        result=result,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
    )

    assert status is not None


def test_first_death_return_phase_end_hook_captures_model_destroyed_once() -> None:
    state = _battle_state_with_scenario()
    beta = _beta_unit(state)
    destroyed_model_id = beta.own_models[0].model_instance_id
    assert state.battlefield_state is not None
    destroyed_placement = state.battlefield_state.model_placement_by_id(
        destroyed_model_id
    ).to_payload()
    _set_model_wounds(state, model_instance_id=destroyed_model_id, wounds_remaining=0)
    state.battlefield_state = state.battlefield_state.with_removed_models((destroyed_model_id,))
    decisions = DecisionController()
    model_destroyed_event = decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": "command",
            "destroying_player_id": "player-a",
            "attacking_unit_instance_id": state.army_definitions[0].units[0].unit_instance_id,
            "target_unit_instance_id": beta.unit_instance_id,
            "model_instance_id": destroyed_model_id,
            "damage_kind": "normal",
            "damage_event_id": "damage:event:first-death",
            "destroyed_model_placement": destroyed_placement,
            "destroyed_model_rules_triggered": True,
        },
    )
    runtime = CatalogReturnOnDeathRuntime(
        ability_indexes_by_player_id={
            "player-b": AbilityCatalogIndex.from_records((_return_on_death_record(),))
        },
        armies=tuple(state.army_definitions),
    )
    current_phase = state.current_battle_phase
    assert current_phase is not None

    runtime.phase_end_handler(
        PhaseEndObjectiveControlContext(
            state=state,
            event_log=decisions.event_log,
            completed_phase=current_phase,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
    )
    runtime.phase_end_handler(
        PhaseEndObjectiveControlContext(
            state=state,
            event_log=decisions.event_log,
            completed_phase=current_phase,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
    )

    assert len(state.pending_return_on_death) == 1
    pending = state.pending_return_on_death[0]
    assert pending.target_scope is ReturnDestroyedTargetScope.DESTROYED_MODEL
    assert pending.destroyed_model_instance_id == destroyed_model_id
    assert not pending.resolved
    assert state.battlefield_state is not None
    assert destroyed_model_id in state.battlefield_state.removed_model_ids
    assert pending.destroyed_position_payload == {
        "source": "model_destroyed_event",
        "model_destroyed_event_id": model_destroyed_event.event_id,
        "model_destroyed_payload": model_destroyed_event.payload,
    }


def _placement_result(*, request: DecisionRequest, placement: UnitPlacement) -> DecisionResult:
    return DecisionResult(
        result_id=f"result:{request.request_id}",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=cast(
            JsonValue,
            {
                "submission_kind": SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
                "attempted_placement": placement.to_payload(),
            },
        ),
    )


def _pending_return_on_death(
    *,
    state: GameState,
    success_threshold: int = 2,
    target_scope: ReturnDestroyedTargetScope = ReturnDestroyedTargetScope.DESTROYED_UNIT,
    restore_mode: ReturnRestoreWoundsMode = ReturnRestoreWoundsMode.FULL_HEALTH,
    wounds_remaining: int | None = None,
) -> PendingReturnOnDeath:
    beta = _beta_unit(state)
    return PendingReturnOnDeath(
        pending_id="pending:return",
        source_rule_id="rule:return",
        source_ability_id="ability:return",
        source_clause_id="clause:return",
        source_effect_index=0,
        owner_player_id="player-b",
        target_scope=target_scope,
        destroyed_unit_instance_id=beta.unit_instance_id,
        destroyed_model_instance_id=(
            beta.own_models[0].model_instance_id
            if target_scope is ReturnDestroyedTargetScope.DESTROYED_MODEL
            else None
        ),
        destroyed_position_payload={"source": "test"},
        trigger_battle_round=1,
        trigger_phase="command",
        resolution_timing="phase_end",
        roll_expression="D6",
        roll_count=1,
        success_threshold=success_threshold,
        placement_anchor="destroyed_position",
        placement_preference="as_close_as_possible",
        engagement_range_restriction=True,
        restore_wounds_mode=restore_mode,
        wounds_remaining=wounds_remaining,
        resolved=False,
    )


def _roll_result(*, pending: PendingReturnOnDeath, value: int) -> DiceRollResult:
    return DiceRollResult.from_values(
        roll_id=f"roll:return:{value}",
        spec=DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason="return_on_death_phase_end_gate",
            roll_type="return_on_death",
            actor_id=pending.owner_player_id,
            reroll_forbidden_rule_ids=(pending.source_rule_id,),
        ),
        values=(value,),
        source="injected",
    )


def _battle_state_with_destroyed_beta_unit() -> GameState:
    state = _battle_state_with_scenario()
    beta = _beta_unit(state)
    _set_unit_wounds(state, unit_instance_id=beta.unit_instance_id, wounds_remaining=0)
    assert state.battlefield_state is not None
    state.battlefield_state = state.battlefield_state.with_removed_models(beta.own_model_ids())
    return state


def _set_unit_wounds(
    state: GameState,
    *,
    unit_instance_id: str,
    wounds_remaining: int,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id != unit_instance_id:
                updated_units.append(unit)
                continue
            updated_units.append(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=wounds_remaining)
                        for model in unit.own_models
                    ),
                )
            )
        updated_armies.append(replace(army, units=tuple(updated_units)))
    state.army_definitions = updated_armies


def _set_model_wounds(
    state: GameState,
    *,
    model_instance_id: str,
    wounds_remaining: int,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_units.append(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=wounds_remaining)
                        if model.model_instance_id == model_instance_id
                        else model
                        for model in unit.own_models
                    ),
                )
            )
        updated_armies.append(replace(army, units=tuple(updated_units)))
    state.army_definitions = updated_armies


def _return_on_death_record() -> AbilityCatalogRecord:
    source = RuleSourceText.from_raw(
        source_id="rule:first-death-return",
        raw_text=FIRST_DEATH_RETURN_TEXT,
    )
    rule_ir = compile_rule_source_text(source).rule_ir
    return AbilityCatalogRecord(
        record_id="record:first-death-return",
        definition=AbilityDefinition(
            ability_id="ability:first-death-return",
            name="First Death Return",
            source_id=source.source_id,
            when_descriptor="First destroyed model.",
            effect_descriptor="Set back up at phase end.",
            restrictions_descriptor="Not within Engagement Range.",
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.AFTER_UNIT_DESTROYED),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=cast(JsonValue, {"rule_ir": rule_ir.to_payload()}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="core-intercessor-like-infantry",
    )


def _unit_placement_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
    x: float,
    y: float,
) -> UnitPlacement:
    army = next(
        army for army in state.army_definitions if any(stored == unit for stored in army.units)
    )
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(x + (index * 2.0), y),
            )
            for index, model in enumerate(unit.own_models)
        ),
    )


def _unit_placement_for_model(
    *,
    state: GameState,
    unit: UnitInstance,
    model_instance_id: str,
    x: float,
    y: float,
) -> UnitPlacement:
    army = next(
        army for army in state.army_definitions if any(stored == unit for stored in army.units)
    )
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model_instance_id,
                pose=Pose.at(x, y),
            ),
        ),
    )


def _beta_unit(state: GameState) -> UnitInstance:
    for army in state.army_definitions:
        if army.player_id != "player-b":
            continue
        return army.units[0]
    raise AssertionError("missing beta unit")


def _first_alpha_model_pose(state: GameState) -> Pose:
    assert state.battlefield_state is not None
    for army in state.battlefield_state.placed_armies:
        if army.player_id != "player-a":
            continue
        return army.unit_placements[0].model_placements[0].pose
    raise AssertionError("missing alpha placement")


def _battle_state_with_scenario() -> GameState:
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="return-on-death-battlefield",
        armies=_mustered_armies(),
    )
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    state = GameState(
        game_id="return-on-death-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        setup_step_index=None,
        battle_phase_index=0,
        battle_round=1,
        active_player_id="player-a",
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        command_point_ledgers=initial_command_point_ledgers(("player-a", "player-b")),
        victory_point_ledgers=initial_victory_point_ledgers(("player-a", "player-b")),
    )
    for army in scenario.armies:
        state.record_army_definition(army)
    state.battlefield_state = scenario.battlefield_state
    return state


def _mustered_armies() -> tuple[ArmyDefinition, ...]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return (
        muster_army(
            catalog=catalog,
            request=_muster_request(catalog=catalog, player_id="player-a", army_id="army-alpha"),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(catalog=catalog, player_id="player-b", army_id="army-beta"),
        ),
    )


def _muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=f"{army_id}-unit",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )
