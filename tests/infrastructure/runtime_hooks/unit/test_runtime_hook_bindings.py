from __future__ import annotations

from typing import cast

from tests.shared.category_migration.runtime_hook_bindings import (
    Callable,
    FallBackEligibilityContext,
    FallBackEligibilityGrant,
    FallBackEligibilityHookBinding,
    GameLifecycleError,
    HookBinding,
    HookBindingShape,
    LifecycleHookEvent,
    RuntimeHookBinding,
    _fall_back_binding,
    _fall_back_handler,
    _generic_binding,
    _generic_handler,
    _HookRegistryOwner,
    _InvalidHookRegistryOwner,
    _StubHookRegistry,
    combine_any_hook_bindings,
    dataclass,
    hook_bindings_by_event_from_registry_owner,
    hook_bindings_by_event_from_sources,
    hook_bindings_for_event,
    lifecycle_event_for_hook_binding,
    pytest,
    runtime_hook_binding_for,
    validate_any_hook_bindings,
    validate_hook_bindings_by_event,
)


def test_runtime_hook_binding_validation_and_lookup_paths() -> None:
    typed_binding = _fall_back_binding("hook-a", source_id="source-a")
    runtime_binding = RuntimeHookBinding(
        lifecycle_event=LifecycleHookEvent.FALL_BACK_ELIGIBILITY,
        binding=typed_binding,
    )
    generic_binding = _generic_binding("generic-a")
    generic_runtime_binding = RuntimeHookBinding(
        lifecycle_event=LifecycleHookEvent.STRATAGEM_COST_CHOICE,
        binding=generic_binding,
    )

    assert runtime_binding.hook_id == "hook-a"
    assert runtime_binding.source_id == "source-a"
    assert lifecycle_event_for_hook_binding(runtime_binding) is (
        LifecycleHookEvent.FALL_BACK_ELIGIBILITY
    )
    assert lifecycle_event_for_hook_binding(typed_binding) is (
        LifecycleHookEvent.FALL_BACK_ELIGIBILITY
    )
    assert runtime_hook_binding_for(runtime_binding) == runtime_binding
    assert runtime_hook_binding_for(typed_binding) == runtime_binding
    assert hook_bindings_for_event(
        (runtime_binding, generic_runtime_binding),
        LifecycleHookEvent.FALL_BACK_ELIGIBILITY,
        FallBackEligibilityHookBinding,
    ) == (typed_binding,)

    with pytest.raises(GameLifecycleError, match="lifecycle_event is invalid"):
        RuntimeHookBinding(
            lifecycle_event=cast(LifecycleHookEvent, "bad-event"),
            binding=typed_binding,
        )
    with pytest.raises(GameLifecycleError, match="binding is invalid"):
        RuntimeHookBinding(
            lifecycle_event=LifecycleHookEvent.FALL_BACK_ELIGIBILITY,
            binding=cast(HookBindingShape, object()),
        )
    with pytest.raises(GameLifecycleError, match="does not match binding type"):
        RuntimeHookBinding(
            lifecycle_event=LifecycleHookEvent.ADVANCE_MOVE,
            binding=typed_binding,
        )
    with pytest.raises(GameLifecycleError, match="contains invalid values"):
        lifecycle_event_for_hook_binding(object())
    with pytest.raises(GameLifecycleError, match="contains invalid values"):
        runtime_hook_binding_for(object())


def test_any_hook_binding_validation_sorts_and_rejects_invalid_values() -> None:
    fall_back_b = _fall_back_binding("hook-b")
    fall_back_a = _fall_back_binding("hook-a")
    generic_runtime_binding = RuntimeHookBinding(
        lifecycle_event=LifecycleHookEvent.STRATAGEM_COST_CHOICE,
        binding=_generic_binding("generic-a"),
    )

    assert validate_any_hook_bindings((fall_back_b, generic_runtime_binding, fall_back_a)) == (
        RuntimeHookBinding(
            lifecycle_event=LifecycleHookEvent.FALL_BACK_ELIGIBILITY,
            binding=fall_back_a,
        ),
        RuntimeHookBinding(
            lifecycle_event=LifecycleHookEvent.FALL_BACK_ELIGIBILITY,
            binding=fall_back_b,
        ),
        generic_runtime_binding,
    )

    with pytest.raises(GameLifecycleError, match="hook_bindings must be a tuple"):
        validate_any_hook_bindings(cast(tuple[object, ...], []))
    with pytest.raises(GameLifecycleError, match="unique per lifecycle event"):
        validate_any_hook_bindings(
            (
                _fall_back_binding("duplicate-hook", source_id="source-a"),
                _fall_back_binding("duplicate-hook", source_id="source-b"),
            )
        )
    with pytest.raises(GameLifecycleError, match="Stratagem cost choice hook binding IDs"):
        combine_any_hook_bindings(
            (
                RuntimeHookBinding(
                    lifecycle_event=LifecycleHookEvent.STRATAGEM_COST_CHOICE,
                    binding=_generic_binding("duplicate-generic", source_id="source-a"),
                ),
                RuntimeHookBinding(
                    lifecycle_event=LifecycleHookEvent.STRATAGEM_COST_CHOICE,
                    binding=_generic_binding("duplicate-generic", source_id="source-b"),
                ),
            )
        )


def test_hook_bindings_by_event_validation_and_source_combining() -> None:
    typed_binding = _fall_back_binding("hook-a")
    runtime_binding = RuntimeHookBinding(
        lifecycle_event=LifecycleHookEvent.FALL_BACK_ELIGIBILITY,
        binding=typed_binding,
    )
    generic_runtime_binding = RuntimeHookBinding(
        lifecycle_event=LifecycleHookEvent.STRATAGEM_COST_CHOICE,
        binding=_generic_binding("generic-a"),
    )

    by_event = hook_bindings_by_event_from_sources(
        emitted_bindings=(typed_binding,),
        contribution_bindings=(generic_runtime_binding,),
    )
    assert by_event[LifecycleHookEvent.FALL_BACK_ELIGIBILITY] == (runtime_binding,)
    assert by_event[LifecycleHookEvent.STRATAGEM_COST_CHOICE] == (generic_runtime_binding,)
    assert validate_hook_bindings_by_event(by_event) == by_event

    with pytest.raises(GameLifecycleError, match="must be a mapping"):
        validate_hook_bindings_by_event([])
    with pytest.raises(GameLifecycleError, match="contains invalid events"):
        validate_hook_bindings_by_event({"bad-event": (runtime_binding,)})
    with pytest.raises(GameLifecycleError, match="contains mismatched events"):
        validate_hook_bindings_by_event({LifecycleHookEvent.ADVANCE_MOVE: (runtime_binding,)})


__all__: list[str] = []
__all__ += ["Callable", "FallBackEligibilityContext", "FallBackEligibilityGrant", "HookBinding"]
__all__ += ["_HookRegistryOwner", "_InvalidHookRegistryOwner", "_StubHookRegistry"]
__all__ += ["_fall_back_handler", "_generic_handler", "dataclass"]
__all__ += ["hook_bindings_by_event_from_registry_owner"]


def test_acts_of_faith_uses_turn_start_and_preserves_triumph_round_hook() -> None:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adepta_sororitas import (
        army_rule,
    )
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    contribution = army_rule.runtime_contribution()
    assert [
        (row.hook_id, row.source_id) for row in contribution.battle_round_start_hook_bindings
    ] == [
        (
            army_rule.TRIUMPH_RELICS_BATTLE_ROUND_START_HOOK_ID,
            army_rule.TRIUMPH_RELICS_SOURCE_RULE_ID,
        )
    ]
    assert [(row.trigger_kind, row.source_rule_id) for row in contribution.event_subscriptions] == [
        (TimingTriggerKind.START_TURN, army_rule.SOURCE_RULE_ID)
    ]
    assert len(contribution.unit_destroyed_hook_bindings) == 1

    from tests.support.acts_of_faith import session as acts_session
    from warhammer40k_core.engine.faction_content.runtime import build_runtime_content_bundle
    from warhammer40k_core.engine.faction_content.runtime_evidence import (
        RuntimeEvidenceProvider,
        active_runtime_evidence_inventory,
    )

    bundle = build_runtime_content_bundle(acts_session().lifecycle.config)
    records = tuple(
        row
        for row in bundle.faction_rule_execution_registry.all_records()
        if row.rule_name == "Acts of Faith"
    )
    assert len(records) == 1
    assert records[0].handler_id == army_rule.TURN_START_HOOK_ID
    inventory = active_runtime_evidence_inventory(bundle)
    assert any(
        row.provider is RuntimeEvidenceProvider.EVENT_HANDLER
        for row in inventory.records_for_evidence_id(army_rule.TURN_START_HOOK_ID)
    )
    assert any(
        row.provider is RuntimeEvidenceProvider.FACTION_EXECUTION_RECORD
        for row in inventory.records_for_evidence_id(records[0].execution_id)
    )


@pytest.mark.parametrize("both_armies", [False, True])
def test_acts_of_faith_turn_transition_duplicate_restore_and_replay(both_armies: bool) -> None:
    import json

    from tests.psychic_modifier_helpers import submit_fixture_request
    from tests.support.acts_of_faith import session as acts_session
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adepta_sororitas import (
        army_rule,
    )
    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner

    session = acts_session(both_armies=both_armies)
    state = session.lifecycle.state
    assert state is not None
    assert not army_rule.miracle_dice_pool(state, player_id="player-a")
    first = session.advance_until_decision_or_terminal()
    assert first.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    first_checkpoint = session.lifecycle.to_payload()
    assert len(army_rule.miracle_dice_pool(state, player_id="player-a")) == 1
    assert len(army_rule.miracle_dice_pool(state, player_id="player-b")) == int(both_armies)
    assert session.advance_until_decision_or_terminal().decision_request == first.decision_request
    assert session.lifecycle.to_payload() == first_checkpoint
    restored = GameLifecycle.from_payload(
        cast(GameLifecyclePayload, json.loads(json.dumps(first_checkpoint)))
    )
    assert restored.to_payload() == first_checkpoint

    # Traverse real finite decisions through both player turns and the next round.
    seen = {(1, "player-a")}
    for _ in range(120):
        state = session.lifecycle.state
        assert state is not None
        pending = session.lifecycle.decision_controller.queue.pending_requests
        assert len(pending) == 1
        request = pending[0]
        assert request.options, request.to_payload()
        option = next(
            (
                value
                for value in request.options
                if any(token in value.option_id for token in ("end", "decline", "skip", "none"))
            ),
            request.options[0],
        )
        if request.decision_type.startswith("submit_"):
            submit_fixture_request(session, request)
        else:
            status = session.submit_option(
                request_id=request.request_id,
                option_id=option.option_id,
                result_id=f"{request.request_id}:acts-test",
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
        assert state.active_player_id is not None
        current = (state.battle_round, state.active_player_id)
        if current not in seen:
            seen.add(current)
            expected = len(seen)
            assert len(army_rule.miracle_dice_pool(state, player_id="player-a")) == expected
            assert len(army_rule.miracle_dice_pool(state, player_id="player-b")) == expected * int(
                both_armies
            )
            checkpoint = session.lifecycle.to_payload()
            assert GameLifecycle.from_payload(checkpoint).to_payload() == checkpoint
        if current == (2, "player-a"):
            break
    else:
        raise AssertionError("Canonical decisions did not reach round two.")
    assert seen == {(1, "player-a"), (1, "player-b"), (2, "player-a")}
    pool = army_rule.miracle_dice_pool(state, player_id="player-a")
    assert len({die.source_id for die in pool}) == 3
    assert all(die.gain_trigger == army_rule.TURN_START_TRIGGER for die in pool)
    assert all(
        die.roll_state.original_result.spec.reroll_forbidden_rule_ids == (army_rule.SOURCE_RULE_ID,)
        for die in pool
    )
    replay = ReplayRunner(
        ReplayArtifact.from_payload(session.replay_artifact(artifact_id="acts-turns"))
    ).run()
    assert replay.reproduced_exactly, replay
    # Resume a real engine-generated first-turn save and reproduce all remaining decisions.
    resumed = LocalGameSession(restored)
    for record in session.lifecycle.decision_controller.records[
        len(restored.decision_controller.records) :
    ]:
        request = resumed.lifecycle.decision_controller.queue.pending_requests[0]
        status = (
            resumed.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=record.result.result_id,
                payload=record.result.payload,
            )
            if request.is_parameterized_submission_request()
            else resumed.submit_option(
                request_id=request.request_id,
                option_id=record.result.selected_option_id,
                result_id=record.result.result_id,
            )
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert resumed.lifecycle.to_payload() == session.lifecycle.to_payload()


def test_acts_turn_candidates_preserve_spend_destruction_and_source_deduplication() -> None:
    from dataclasses import replace

    from tests.destruction_occurrence_fixture_helpers import destroy_rule_model_for_fixture
    from tests.support.acts_of_faith import session as acts_session
    from warhammer40k_core.engine.faction_content.events import (
        RuntimeContentEvent,
        RuntimeContentEventContext,
    )
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adepta_sororitas import (
        army_rule,
        destruction_sequencing,
        turn_sequencing,
    )
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind
    from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedContext

    session = acts_session(both_armies=True, extra_friendly=True)
    state = session.lifecycle.state
    assert state is not None
    decisions = session.lifecycle.decision_controller
    event = RuntimeContentEvent(
        event_id="canonical-turn-start",
        game_id=state.game_id,
        player_id="player-a",
        battle_round=1,
        trigger_kind=TimingTriggerKind.START_TURN,
        active_player_id="player-a",
    )
    context = RuntimeContentEventContext(
        event=event,
        state=state,
        decisions=decisions,
        ruleset_descriptor=session.lifecycle.config.ruleset_descriptor,
        army_catalog=session.lifecycle.config.army_catalog,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    before = state.to_payload(), decisions.to_payload()
    candidates = turn_sequencing.candidates(context)
    assert len(candidates) == 1
    assert (state.to_payload(), decisions.to_payload()) == before
    assert candidates[0].activate() is None
    pool = army_rule.miracle_dice_pool(state, player_id="player-a")
    assert len(pool) == 1
    gain_count = len(decisions.event_log.records)
    assert turn_sequencing.candidates(context) == ()
    turn_sequencing.resolve_turn_start(context)
    assert len(decisions.event_log.records) == gain_count
    unit = state.army_definitions[0].units[0]
    die = pool[0]
    army_rule.spend_miracle_die(
        state,
        decisions,
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        miracle_die_id=die.miracle_die_id,
        source_id="canonical-acts-spend",
        source_context={},
    )
    assert army_rule.miracle_dice_pool(state, player_id="player-a") == ()
    assert turn_sequencing.candidates(context) == ()
    restored = GameState.from_payload(state.to_payload())
    assert turn_sequencing.candidates(replace(context, state=restored)) == ()
    # Existing destruction provider uses its independent occurrence ID and resource owner.
    enemy = state.army_definitions[1].units[0]
    casualty = state.army_definitions[0].units[1]
    destroyed_event = destroy_rule_model_for_fixture(
        state=state,
        decisions=decisions,
        model_id=casualty.own_models[0].model_instance_id,
        destroying_player_id="player-b",
        source_unit_id=enemy.unit_instance_id,
        source_model_id=enemy.own_models[0].model_instance_id,
    )
    assert isinstance(destroyed_event.payload, dict)
    destroyed = UnitDestroyedContext(
        sequencing_active_player_id="player-a",
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.COMMAND,
        model_destroyed_event_id=destroyed_event.event_id,
        model_destroyed_payload=destroyed_event.payload,
        destroying_player_id="player-b",
        destroyed_unit_instance_id=casualty.unit_instance_id,
        destroyed_player_id="player-a",
    )
    destruction = destruction_sequencing.candidates(destroyed)
    assert len(destruction) == 1
    assert destruction[0].activate() is None
    army_rule.resolve_adepta_sororitas_unit_destroyed(destroyed)
    assert destruction_sequencing.candidates(destroyed) == ()
    destruction_pool = army_rule.miracle_dice_pool(state, player_id="player-a")
    assert len(destruction_pool) == 1
    second = destruction_pool[0]
    assert second.gain_trigger == army_rule.UNIT_DESTROYED_TRIGGER
    # A real second friendly casualty funds the pool while its original spender
    # stays alive: the existing per-phase cap must still reject a second spend.
    before = state.to_payload(), decisions.to_payload()
    with pytest.raises(GameLifecycleError, match="phase limit"):
        army_rule.spend_miracle_die(
            state,
            decisions,
            player_id="player-a",
            unit_instance_id=unit.unit_instance_id,
            miracle_die_id=second.miracle_die_id,
            source_id="canonical-acts-cap",
            source_context={},
        )
    assert (state.to_payload(), decisions.to_payload()) == before
    with pytest.raises(GameLifecycleError, match="Sororitas unit"):
        army_rule.spend_miracle_die(
            state,
            decisions,
            player_id="player-a",
            unit_instance_id=casualty.unit_instance_id,
            miracle_die_id=second.miracle_die_id,
            source_id="canonical-acts-dead",
            source_context={},
        )
    assert (state.to_payload(), decisions.to_payload()) == before
    with pytest.raises(GameLifecycleError, match="player drift"):
        army_rule.spend_miracle_die(
            state,
            decisions,
            player_id="player-b",
            unit_instance_id=unit.unit_instance_id,
            miracle_die_id=second.miracle_die_id,
            source_id="canonical-acts-owner",
            source_context={},
        )
    for invalid in (
        replace(event, trigger_kind=TimingTriggerKind.START_BATTLE_ROUND),
        replace(event, active_player_id="player-b"),
        replace(event, battle_round=2),
    ):
        before = state.to_payload(), decisions.to_payload()
        with pytest.raises(GameLifecycleError, match="boundary drift"):
            turn_sequencing.candidates(replace(context, event=invalid))
        assert (state.to_payload(), decisions.to_payload()) == before


@pytest.mark.parametrize("eligible", [True, False])
def test_acts_actual_casualty_and_native_combat_replay(eligible: bool) -> None:
    from tests.psychic_modifier_helpers import submit_fixture_request
    from tests.support.acts_of_faith import session as acts_session
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adepta_sororitas import (
        army_rule,
    )
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner

    session = acts_session(both_armies=eligible, combat=True)
    state = session.lifecycle.state
    assert state is not None
    session.advance_until_decision_or_terminal()
    for _ in range(80):
        requests = session.lifecycle.decision_controller.queue.pending_requests
        assert len(requests) == 1
        submit_fixture_request(session, requests[0])
        events = session.lifecycle.decision_controller.event_log.records
        if any(event.event_type == "fight_activation_completed" for event in events):
            break
    else:
        raise AssertionError("Canonical native combat did not destroy its target.")
    # Drain any mandatory casualty continuation before inspecting its grant.
    session.advance_until_decision_or_terminal()
    target = state.army_definitions[1].units[0]
    assert not target.alive_own_models()
    assert target.faction_keywords == ()
    pool = army_rule.miracle_dice_pool(state, player_id="player-b")
    assert len(
        [die for die in pool if die.gain_trigger == army_rule.UNIT_DESTROYED_TRIGGER]
    ) == int(eligible)
    checkpoint = session.lifecycle.to_payload()
    restored = GameLifecycle.from_payload(checkpoint)
    assert restored.to_payload() == checkpoint
    assert restored.state is not None
    assert army_rule.miracle_dice_pool(restored.state, player_id="player-b") == pool
    replay = ReplayRunner(
        ReplayArtifact.from_payload(session.replay_artifact(artifact_id="acts-death"))
    ).run()
    assert replay.reproduced_exactly, replay


def test_destruction_keyword_predicate_uses_canonical_retained_physical_models() -> None:
    from tests.destruction_occurrence_fixture_helpers import destroy_rule_model_for_fixture
    from tests.support.acts_of_faith import session as acts_session
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adepta_sororitas import (
        destruction_sequencing,
    )

    session = acts_session(both_armies=False)
    state = session.lifecycle.state
    assert state is not None
    friendly, other = (army.units[0] for army in state.army_definitions)
    # These are the existing domain model keyword assignments, not rule text.
    assert destruction_sequencing._has_retained_sororitas_keyword(friendly)  # pyright: ignore[reportPrivateUsage]
    assert not destruction_sequencing._has_retained_sororitas_keyword(other)  # pyright: ignore[reportPrivateUsage]
    destroy_rule_model_for_fixture(
        state=state,
        decisions=session.lifecycle.decision_controller,
        model_id=other.own_models[0].model_instance_id,
        destroying_player_id="player-a",
        source_unit_id=friendly.unit_instance_id,
        source_model_id=friendly.own_models[0].model_instance_id,
    )
    destroyed = state.army_definitions[1].units[0]
    assert not destroyed.alive_own_models()
    assert not destruction_sequencing._has_retained_sororitas_keyword(destroyed)  # pyright: ignore[reportPrivateUsage]
