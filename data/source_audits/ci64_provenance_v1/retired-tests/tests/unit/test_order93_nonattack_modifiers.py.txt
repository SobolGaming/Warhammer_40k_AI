from __future__ import annotations

import pytest
from tests.phase11c_command_phase_helpers import (
    battle_state,
    battle_state_with_center_objective_positions,
)

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm
from warhammer40k_core.core.profile_modifier_trace import CharacteristicModifierTrace
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.nonattack_modifier_evaluation import evaluate_leadership_modifiers
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.objective_control_modifier_evaluation import (
    evaluate_objective_control_modifiers,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    ObjectiveControlModifierBinding,
    ObjectiveControlModifierContext,
    RuntimeModifierRegistry,
    UnitCharacteristicModifierBinding,
    UnitCharacteristicModifierContext,
)


def _leadership_penalty(context: UnitCharacteristicModifierContext) -> tuple[ModifierTerm, ...]:
    return (
        (ModifierTerm(ModifierOperation.ADD, 1),)
        if context.characteristic is Characteristic.LEADERSHIP
        else ()
    )


def _leadership_bonus(context: UnitCharacteristicModifierContext) -> tuple[ModifierTerm, ...]:
    return (
        (ModifierTerm(ModifierOperation.ADD, -1),)
        if context.characteristic is Characteristic.LEADERSHIP
        else ()
    )


def _oc_bonus(_context: ObjectiveControlModifierContext) -> tuple[ModifierTerm, ...]:
    return (ModifierTerm(ModifierOperation.ADD, 2),)


@pytest.mark.parametrize("operation", [ModifierOperation.SET_DASH, ModifierOperation.SET_STAR])
@pytest.mark.parametrize(
    "characteristic",
    [
        Characteristic.MOVEMENT,
        Characteristic.LEADERSHIP,
        Characteristic.OBJECTIVE_CONTROL,
        Characteristic.SAVE,
    ],
)
def test_random_terminal_replacement_retains_source_roll_when_ignored(
    operation: ModifierOperation, characteristic: Characteristic
) -> None:
    import json
    from dataclasses import replace

    from warhammer40k_core.core.attributes import CharacteristicError
    from warhammer40k_core.core.dice import DiceExpression
    from warhammer40k_core.core.modifiers import ModifierScope
    from warhammer40k_core.core.random_profile_values import RandomProfileValue
    from warhammer40k_core.engine.movement_budget_modifiers import (
        MovementBudgetModifierContext,
        generic_rule_movement_modifier_trace,
    )
    from warhammer40k_core.engine.profile_modifiers import resolved_profile_with_modifier_trace

    state = battle_state()
    unit = state.army_definitions[0].units[0]
    model = unit.own_models[0]
    modifier = ModifierTerm(operation, 0).bind(
        modifier_id="source:terminal",
        source_id="source:terminal",
        characteristic=characteristic,
    )
    source = RandomProfileValue(
        characteristic, DiceExpression(1, 6), "source:random-terminal", (modifier,)
    )
    profile = source.evaluate(
        raw=4, evaluation_id="test:terminal", target_id=model.model_instance_id
    )
    assert profile.resolved_value().raw == 0
    assert profile.raw == 4
    assert profile.without_evaluation() == source
    profile = RandomProfileValue.from_payload(json.loads(json.dumps(profile.to_payload())))
    value = resolved_profile_with_modifier_trace(profile)
    assert value.modifier_trace is not None
    assert value.modifier_trace.source_value == 4
    ignored_final = 5 if characteristic is Characteristic.LEADERSHIP else 4
    assert (
        value.modifier_trace.resolve(ignored_modifier_ids=(modifier.modifier_id,)).final
        == ignored_final
    )
    if characteristic is Characteristic.SAVE:
        from warhammer40k_core.engine.save_modifier_operations import profile_trace_for_save

        save_trace = profile_trace_for_save(profile)
        assert save_trace is not None
        assert save_trace.source_value == 4
        assert save_trace.resolve(ignored_modifier_ids=(modifier.modifier_id,)).final == 4
    if characteristic is Characteristic.MOVEMENT:
        context = MovementBudgetModifierContext(
            state=state,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            movement=profile,
        )
        assert generic_rule_movement_modifier_trace(context)[0] == 0
        assert (
            generic_rule_movement_modifier_trace(
                context, ignored_modifier_ids=frozenset((modifier.modifier_id,))
            )[0]
            == 4
        )
    payload = profile.to_payload()
    del payload["evaluation_raw"]
    with pytest.raises(CharacteristicError, match="raw roll"):
        RandomProfileValue.from_payload(payload)
    from typing import cast

    from warhammer40k_core.core.random_profile_values import RandomProfileValuePayload

    for invalid_json_raw in (None, "4", True):
        with pytest.raises(CharacteristicError, match="integer"):
            RandomProfileValue.from_payload(
                cast(
                    RandomProfileValuePayload,
                    {**profile.to_payload(), "evaluation_raw": invalid_json_raw},
                )
            )
    for forged_raw in (0, 7, True):
        with pytest.raises(CharacteristicError, match="expression bounds"):
            replace(profile, evaluation_raw=forged_raw)
    scoped = replace(
        source,
        modifiers=(
            replace(
                modifier,
                scope=ModifierScope(
                    characteristics=frozenset({characteristic}),
                    target_ids=frozenset({model.model_instance_id}),
                ),
            ),
        ),
    ).evaluate(raw=4, evaluation_id="test:scoped-terminal", target_id=model.model_instance_id)
    assert scoped.raw == 4
    assert RandomProfileValue.from_payload(scoped.to_payload()) == scoped
    with pytest.raises(CharacteristicError, match="source or scope"):
        resolved_profile_with_modifier_trace(scoped)


@pytest.mark.parametrize(
    "characteristic", [Characteristic.LEADERSHIP, Characteristic.OBJECTIVE_CONTROL]
)
def test_random_nonattack_profile_owners_preserve_wrapper_operations(
    characteristic: Characteristic,
) -> None:
    from dataclasses import replace

    from warhammer40k_core.core.attributes import CharacteristicError
    from warhammer40k_core.core.dice import DiceExpression
    from warhammer40k_core.core.modifiers import ModifierScope
    from warhammer40k_core.core.random_profile_values import RandomProfileValue
    from warhammer40k_core.engine.nonattack_modifier_evaluation import (
        leadership_modifier_inventories,
    )
    from warhammer40k_core.engine.objective_control import model_objective_control_characteristic
    from warhammer40k_core.engine.profile_modifiers import (
        profile_with_delta,
        resolved_profile_with_modifier_trace,
    )

    state = battle_state()
    army = state.army_definitions[0]
    unit = army.units[0]
    model = unit.own_models[0]
    profile = profile_with_delta(
        profile_with_delta(
            RandomProfileValue(characteristic, DiceExpression(1, 6), "source:random-profile"),
            1,
            source_id="source:positive",
            modifier_id="positive",
        ),
        -1,
        source_id="source:negative",
        modifier_id="negative",
    )
    assert isinstance(profile, RandomProfileValue)
    profile = profile.evaluate(
        raw=6, evaluation_id="test:profile", target_id=model.model_instance_id
    )
    model = replace(
        model,
        characteristics=tuple(
            profile if value.characteristic is characteristic else value
            for value in model.characteristics
        ),
    )
    unit = replace(unit, own_models=(model, *unit.own_models[1:]))
    state.replace_army_definitions(
        [replace(army, units=(unit, *army.units[1:])), *state.army_definitions[1:]]
    )
    if characteristic is Characteristic.LEADERSHIP:
        _, source, operations = leadership_modifier_inventories(
            state=state,
            unit_instance_id=unit.unit_instance_id,
            ability_index=AbilityCatalogIndex.from_records(()),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            model_instance_ids=(model.model_instance_id,),
        )[0]
        assert source == 6
        assert operations == profile.modifiers
    else:
        value = model_objective_control_characteristic(model, battle_shocked=False)
        assert value.modifier_trace is not None
        assert value.modifier_trace.source_value == 6
        assert value.modifier_trace.modifiers == profile.modifiers
    selected = profile.evaluate(
        raw=6,
        evaluation_id="test:profile",
        target_id=model.model_instance_id,
        ignored_modifier_ids=("positive",),
    )
    value = resolved_profile_with_modifier_trace(selected)
    assert value.final == 5
    assert value.modifier_trace is not None
    assert value.modifier_trace.ignored_modifier_ids == ("positive",)
    from warhammer40k_core.engine.catalog_modifier_ignore import ModifierIgnoreKind
    from warhammer40k_core.engine.modifier_evaluation import ModifierEvaluationSubject
    from warhammer40k_core.engine.nonattack_profile_modifiers import (
        selected_nonattack_profile_modifiers,
    )

    retained = selected_nonattack_profile_modifiers(
        decision_records=(),
        occurrence_id="test:no-new-grant",
        subject=ModifierEvaluationSubject(
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            kind=ModifierIgnoreKind.LEADERSHIP_CHARACTERISTIC
            if characteristic is Characteristic.LEADERSHIP
            else ModifierIgnoreKind.OBJECTIVE_CONTROL_CHARACTERISTIC,
        ),
        modifiers=profile.modifiers,
        source_trace=value.modifier_trace,
    )
    assert retained == (profile.modifiers[1],)
    scoped = replace(
        profile,
        modifiers=(
            replace(
                profile.modifiers[0],
                scope=ModifierScope(
                    characteristics=frozenset({characteristic}),
                    target_ids=frozenset({model.model_instance_id}),
                ),
            ),
        ),
    ).evaluate(raw=6, evaluation_id="test:profile", target_id=model.model_instance_id)
    with pytest.raises(CharacteristicError, match="source or scope"):
        resolved_profile_with_modifier_trace(scoped)


def test_random_leadership_runtime_operations_precede_characteristic_bounds() -> None:
    from dataclasses import replace

    from warhammer40k_core.core.dice import DiceExpression
    from warhammer40k_core.core.random_profile_values import RandomProfileValue
    from warhammer40k_core.engine.nonattack_modifier_evaluation import (
        leadership_modifier_inventories,
    )

    state = battle_state()
    army = state.army_definitions[0]
    unit = army.units[0]
    model = unit.own_models[0]
    profile = RandomProfileValue(
        Characteristic.LEADERSHIP, DiceExpression(1, 6), "source:low-leadership"
    ).evaluate(raw=2, evaluation_id="test:raw-two", target_id=model.model_instance_id)
    assert profile.final == 5
    model = replace(
        model,
        characteristics=tuple(
            profile if value.characteristic is Characteristic.LEADERSHIP else value
            for value in model.characteristics
        ),
    )
    unit = replace(unit, own_models=(model, *unit.own_models[1:]))
    state.replace_army_definitions(
        [replace(army, units=(unit, *army.units[1:])), *state.army_definitions[1:]]
    )
    registry = RuntimeModifierRegistry.from_bindings(
        unit_characteristic_modifier_bindings=(
            UnitCharacteristicModifierBinding("penalty-a", "source:a", _leadership_penalty),
            UnitCharacteristicModifierBinding("penalty-b", "source:b", _leadership_penalty),
        )
    )
    _, source, modifiers = leadership_modifier_inventories(
        state=state,
        unit_instance_id=unit.unit_instance_id,
        ability_index=AbilityCatalogIndex.from_records(()),
        runtime_modifier_registry=registry,
        model_instance_ids=(model.model_instance_id,),
    )[0]
    assert source == 2
    assert (
        CharacteristicModifierTrace(Characteristic.LEADERSHIP, source, modifiers).value().final == 5
    )


def test_leadership_boundary_preserves_each_operation_and_model_identity() -> None:
    decisions = DecisionController()
    state = battle_state(decisions=decisions)
    unit = state.army_definitions[0].units[0]
    registry = RuntimeModifierRegistry.from_bindings(
        unit_characteristic_modifier_bindings=(
            UnitCharacteristicModifierBinding("penalty", "source:penalty", _leadership_penalty),
            UnitCharacteristicModifierBinding("bonus", "source:bonus", _leadership_bonus),
        )
    )
    evaluated = evaluate_leadership_modifiers(
        state=state,
        decisions=decisions,
        unit_instance_id=unit.unit_instance_id,
        occurrence_id="test:leadership",
        ability_index=AbilityCatalogIndex.from_records(()),
        runtime_modifier_registry=registry,
        roll_modifiers=(),
        source_context={"continuation": "phase"},
    )
    assert evaluated.pending_status is None
    assert len(evaluated.characteristic_traces) == len(unit.own_models)
    for model_id, trace in evaluated.characteristic_traces:
        model = unit.own_model_by_id(model_id)
        assert trace.resolve().final == model.characteristic(Characteristic.LEADERSHIP).final
        assert {item.modifier_id for item in trace.modifiers} == {"penalty", "bonus"}
        assert trace.resolve(ignored_modifier_ids=("penalty",)).final == trace.source_value - 1
        assert CharacteristicModifierTrace.from_payload(trace.to_payload()) == trace
    assert evaluated.leadership_target == min(
        trace.resolve().final for _, trace in evaluated.characteristic_traces
    )
    assert not decisions.queue.pending_requests


def test_nonattack_oc_preflight_retains_trace_and_keeps_query_pure() -> None:
    decisions = DecisionController()
    state = battle_state_with_center_objective_positions(
        player_a_offsets=((2.0, 0.0),), player_b_offsets=((0.0, 2.0),)
    )
    registry = RuntimeModifierRegistry.from_bindings(
        objective_control_modifier_bindings=(
            ObjectiveControlModifierBinding("oc:bonus", "source:oc-bonus", _oc_bonus),
        )
    )
    context = ObjectiveControlContext.from_game_state(
        state,
        timing=ObjectiveControlTiming.PHASE_END,
        phase=BattlePhase.COMMAND,
        runtime_modifier_registry=registry,
    )
    prepared = evaluate_objective_control_modifiers(
        context,
        decisions=decisions,
        occurrence_id="test:oc",
        ability_indexes_by_player_id={
            owner: AbilityCatalogIndex.from_records(()) for owner in state.player_ids
        },
    )
    assert prepared.pending_status is None
    before = state.to_payload(), decisions.to_payload()
    record = resolve_objective_control(prepared.context)
    assert ObjectiveControlRecord.from_payload(record.to_payload()) == record
    assert (state.to_payload(), decisions.to_payload()) == before
    assert any(result.contributors for result in record.results)
    for result in record.results:
        for contribution in result.contributors:
            assert contribution.modifier_trace is not None
            assert contribution.modifier_trace.resolve().final == contribution.objective_control


def test_leadership_boundary_rejects_non_test_roll_kind() -> None:
    from warhammer40k_core.engine.catalog_modifier_ignore import ModifierIgnoreKind

    decisions = DecisionController()
    state = battle_state(decisions=decisions)
    with pytest.raises(GameLifecycleError, match="Leadership test roll kind"):
        evaluate_leadership_modifiers(
            state=state,
            decisions=decisions,
            unit_instance_id=state.army_definitions[0].units[0].unit_instance_id,
            occurrence_id="test:invalid",
            ability_index=AbilityCatalogIndex.from_records(()),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            roll_modifiers=(),
            roll_kind=ModifierIgnoreKind.HIT_ROLL,
            source_context={},
        )


@pytest.mark.parametrize("random_profile", [False, True])
@pytest.mark.parametrize("selection", ["ignore-remaining", "keep-remaining", "negative-only"])
def test_command_leadership_subset_facade_restore_and_replay(
    selection: str, random_profile: bool
) -> None:
    from tests.order93_nonattack_helpers import command_modifier_session
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

    from warhammer40k_core.engine.event_log import canonical_json
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner

    session = command_modifier_session(random_profile=random_profile)
    state = session.lifecycle.state
    assert state is not None
    initial_snapshot = session.lifecycle.to_payload()
    selections = 0
    for _ in range(25):
        request = pending_request(session)
        if request.decision_type == "select_modifier_ignores":
            assert isinstance(request.payload, dict)
            subject = request.payload["subject"]
            assert isinstance(subject, dict)
            assert subject["kind"] == "leadership_characteristic"
            snapshot = session.lifecycle.to_payload()
            assert GameLifecycle.from_payload(snapshot).to_payload() == snapshot
            assert "source_context" not in canonical_json(session.view(viewer_player_id="player-b"))
            option_id = selection
            if selection == "negative-only":
                inventory = request.payload["modifiers"]
                cursor = request.payload["decided_modifier_ids"]
                assert isinstance(inventory, list)
                assert isinstance(cursor, list)
                item = inventory[len(cursor)]
                assert isinstance(item, dict)
                operation = item["operation"]
                assert isinstance(operation, dict)
                prefix = "ignore:" if operation["operand"] == -1 else "keep:"
                option_id = next(
                    (
                        option.option_id
                        for option in request.options
                        if option.option_id.startswith(prefix)
                    ),
                    "ignore-remaining" if prefix == "ignore:" else "keep-remaining",
                )
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:choice",
                option_id=option_id,
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
            selections += 1
        elif request.decision_type == "submit_stratagem_target_proposal":
            from warhammer40k_core.engine.stratagems import stratagem_decline_payload

            session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"{request.request_id}:decline",
                payload=stratagem_decline_payload(),
            )
        else:
            submit_fixture_request(session, request)
        resolved = [
            event.payload
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "battle_shock_test_resolved"
        ]
        if resolved:
            break
    else:
        pytest.fail("Command Battle-shock did not finish its modifier evaluation.")
    assert selections >= 2
    expected = 7 if selection == "negative-only" else 6
    if random_profile:
        from warhammer40k_core.core.attributes import CharacteristicValue
        from warhammer40k_core.core.random_profile_values import RandomProfileValue

        state = session.lifecycle.state
        assert state is not None
        unit = state.army_definitions[0].units[0]
        profiles = tuple(
            model.characteristic(Characteristic.LEADERSHIP)
            for model in unit.own_models
            if isinstance(model.characteristic(Characteristic.LEADERSHIP), RandomProfileValue)
            and model.characteristic(Characteristic.LEADERSHIP).is_numeric
        )
        assert len(profiles) == 2
        expected = min(
            CharacteristicValue.from_raw(
                Characteristic.LEADERSHIP,
                profile.raw + (1 if selection == "negative-only" else 0),
            ).final
            for profile in profiles
        )
        rolls = [
            event
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "random_characteristic_rolled"
        ]
        assert len(rolls) == 2
    payload = resolved[-1]
    assert isinstance(payload, dict)
    result_payload = payload["battle_shock_result"]
    assert isinstance(result_payload, dict)
    assert result_payload["leadership_target"] == expected
    snapshot = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(snapshot).to_payload() == snapshot
    assert (
        ReplayRunner.from_payload(
            ReplayArtifact.capture(
                artifact_id=f"nonattack-{selection}",
                initial_lifecycle_payload=initial_snapshot,
                final_lifecycle=session.lifecycle,
            ).to_payload()
        )
        .run()
        .reproduced_exactly
    )


@pytest.mark.parametrize("random_profile", [False, True])
def test_phase_end_objective_control_choices_facade_restore_and_replay(
    random_profile: bool,
) -> None:
    from tests.order93_nonattack_helpers import command_modifier_session
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request

    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner

    session = command_modifier_session(
        characteristic_name="objective_control", random_profile=random_profile
    )
    initial = session.lifecycle.to_payload()
    choices = 0
    for _ in range(30):
        request = pending_request(session)
        if request.decision_type == "select_modifier_ignores":
            assert isinstance(request.payload, dict)
            subject = request.payload["subject"]
            assert isinstance(subject, dict)
            assert subject["kind"] == "objective_control_characteristic"
            snapshot = session.lifecycle.to_payload()
            assert GameLifecycle.from_payload(snapshot).to_payload() == snapshot
            option_id = "ignore-remaining"
            if random_profile:
                inventory = request.payload["modifiers"]
                cursor = request.payload["decided_modifier_ids"]
                assert isinstance(inventory, list)
                assert isinstance(cursor, list)
                operation_row = inventory[len(cursor)]
                assert isinstance(operation_row, dict)
                operation = operation_row["operation"]
                assert isinstance(operation, dict)
                ignore = operation["operand"] == 1
                prefix = "ignore:" if ignore else "keep:"
                option_id = next(
                    (
                        option.option_id
                        for option in request.options
                        if option.option_id.startswith(prefix)
                    ),
                    "ignore-remaining" if ignore else "keep-remaining",
                )
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"{request.request_id}:ignore",
                option_id=option_id,
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
            choices += 1
        else:
            submit_fixture_request(session, request)
        if choices and pending_request(session).decision_type != "select_modifier_ignores":
            break
    assert choices == (10 if random_profile else 5)
    if random_profile:
        state = session.lifecycle.state
        assert state is not None
        contributions = [
            contribution
            for result in state.objective_control_records[-1].results
            for contribution in result.contributors
            if contribution.player_id == "player-a"
        ]
        assert len(contributions) == 5
        for contribution in contributions:
            trace = contribution.modifier_trace
            assert trace is not None
            assert sorted(operation.operand for operation in trace.modifiers) == [-1, 1]
            assert trace.ignored_modifier_ids == tuple(
                operation.modifier_id for operation in trace.modifiers if operation.operand == 1
            )
            assert contribution.objective_control == max(0, trace.source_value - 1)
        scopes = [
            event.payload["scope_id"]
            for event in session.lifecycle.decision_controller.event_log.records
            if event.event_type == "random_profile_values_evaluated"
            and isinstance(event.payload, dict)
        ]
        assert len(scopes) == len(set(scopes))
    snapshot = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(snapshot).to_payload() == snapshot
    assert (
        ReplayRunner.from_payload(
            ReplayArtifact.capture(
                artifact_id="oc-phase-end",
                initial_lifecycle_payload=initial,
                final_lifecycle=session.lifecycle,
            ).to_payload()
        )
        .run()
        .reproduced_exactly
    )
