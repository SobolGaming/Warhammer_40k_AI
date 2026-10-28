"""Core source timing reaches shared discovery and public atomic admission."""

import json
from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest
from tests.order128_helpers import assert_checkpoint
from tests.order135_counteroffensive_helpers import (
    actual_fought_events,
    native_combat_session,
    other_player,
    proposal_from_native_request,
    submit_native_combat_choice,
)
from tests.phase15c_fight_order_helpers import fight_lifecycle
from tests.smokescreen_helpers import smoke_session
from tests.unit_keyword_helpers import with_unit_keywords

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.command_points import CommandPointGainStatus, CommandPointSourceKind
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_order import FightPhaseState, FightsFirstRegistry
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_stratagem_index
from warhammer40k_core.engine.stratagems import (
    CORE_COUNTEROFFENSIVE_HANDLER_ID,
    StratagemCatalogIndex,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetProposal,
    create_stratagem_target_proposal_decision_request,
    stratagem_target_proposal_from_index,
    stratagem_use_options_from_index,
)
from warhammer40k_core.engine.stratagems_generic_metadata import stratagem_turn_unavailable_reason
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.geometry.pose import Pose


def _window(
    *, active_player: str, actor: str
) -> tuple[LocalGameSession, GameState, DecisionController, StratagemTargetProposal]:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("one",),
        enemy_unit_ids=("enemy",),
        origins={"one": Pose.at(10, 10), "enemy": Pose.at(11.7, 10)},
        game_id="order135-core-timing-unit",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
    )
    state = lifecycle.state
    assert state is not None
    state.active_player_id = active_player
    state.fight_phase_state = FightPhaseState.start(
        battle_round=state.battle_round,
        active_player_id=active_player,
        policy=lifecycle.config.ruleset_descriptor.fight_policy,
        engaged_at_fight_step_start_unit_ids=tuple(u.unit_instance_id for u in units.values()),
        fights_first_registry=FightsFirstRegistry(),
    ).with_next_band()
    assert state.command_point_total(actor) == 0
    gain = state.gain_command_points(
        player_id=actor,
        amount=2,
        source_id="order135-b02:unit-fixture-command-phase",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    assert gain.status is CommandPointGainStatus.APPLIED
    target = "army-alpha:one" if actor == "player-a" else "army-beta:enemy"
    fought = "army-beta:enemy" if actor == "player-a" else "army-alpha:one"
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id=actor,
        trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_FOUGHT,
        trigger_payload={
            "fought_unit_instance_id": fought,
            "eligible_unit_instance_ids": [target],
        },
    )
    index = eleventh_edition_stratagem_index()
    record = next(r for r in index.all_records() if r.definition.stratagem_id == "counteroffensive")
    proposal = StratagemTargetProposal.for_request(context=context, catalog_record=record)
    return LocalGameSession(lifecycle), state, lifecycle.decision_controller, proposal


@pytest.mark.parametrize("actor", ["player-a", "player-b"])
@pytest.mark.parametrize("own_turn", [False, True])
def test_core_counteroffensive_requires_opponent_fight_phase(actor: str, own_turn: bool) -> None:
    active = actor if own_turn else ("player-b" if actor == "player-a" else "player-a")
    _session, state, _decisions, proposal = _window(active_player=active, actor=actor)
    discovered = stratagem_target_proposal_from_index(
        state=state,
        index=eleventh_edition_stratagem_index(),
        context=proposal.context,
        handler_id=CORE_COUNTEROFFENSIVE_HANDLER_ID,
    )
    assert (discovered is None) is own_turn
    if discovered is not None:
        assert discovered.catalog_record == proposal.catalog_record


@pytest.mark.parametrize("actor", ["player-a", "player-b"])
def test_core_counteroffensive_own_turn_rejection_is_atomic(actor: str) -> None:
    session, state, decisions, proposal = _window(active_player=actor, actor=actor)
    # The real request factory supplies a well-formed input to public admission.
    # This isolates that consumer; the separate native controls prove discovery.
    request = create_stratagem_target_proposal_decision_request(
        state=state, proposal_request=proposal
    )
    decisions.request_decision(request)
    target = "army-alpha:one" if actor == "player-a" else "army-beta:enemy"
    submitted = proposal.with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id=actor,
            target_unit_instance_id=target,
        )
    )
    before = session.lifecycle.to_payload()
    cp_before = state.command_point_total(actor)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order135-b02:own-turn-denied",
        payload={"proposal": validate_json_value(submitted.to_payload())},
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status.payload == {"invalid_reason": "stratagem_requires_opponent_turn"}
    assert session.lifecycle.to_payload() == before
    assert state.command_point_total(actor) == cp_before == 2
    assert state.stratagem_use_records == []
    assert state.persisting_effects == []
    assert state.fight_phase_state is not None
    assert state.fight_phase_state.fight_order_state.activation_selections == ()


@pytest.mark.parametrize("actor", ["player-a", "player-b"])
@pytest.mark.parametrize(
    "field", ["active_player_id", "trigger_kind", "timing_window_id", "trigger_payload"]
)
def test_engine_admission_context_drift_preserves_queue_history_and_state(
    actor: str, field: str
) -> None:
    # Constructed typed engine admission fixture, separate from native generation.
    session, state, decisions, proposal = _window(active_player=other_player(actor), actor=actor)
    request = create_stratagem_target_proposal_decision_request(
        state=state, proposal_request=proposal
    )
    decisions.request_decision(request)
    target = "army-alpha:one" if actor == "player-a" else "army-beta:enemy"
    submitted = proposal.with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id=actor,
            target_unit_instance_id=target,
        )
    )
    if field == "active_player_id":
        context = replace(submitted.context, active_player_id=actor)
    elif field == "trigger_kind":
        context = replace(submitted.context, trigger_kind=TimingTriggerKind.START_PHASE)
    elif field == "timing_window_id":
        context = replace(submitted.context, timing_window_id="order135-b03:client-drift")
    else:
        assert field == "trigger_payload"
        context = replace(
            submitted.context,
            trigger_payload={
                "fought_unit_instance_id": target,
                "eligible_unit_instance_ids": [target],
            },
        )
    drifted = replace(submitted, context=context)
    before = session.lifecycle.to_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=f"order135-b03:denied:{field}",
        payload={"proposal": validate_json_value(drifted.to_payload())},
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status.payload == {"invalid_reason": "wrong_context"}
    assert session.lifecycle.to_payload() == before
    assert state.command_point_total(actor) == 2
    assert state.stratagem_use_records == []
    assert state.persisting_effects == []


@pytest.mark.parametrize("actor", ["player-a", "player-b"])
@pytest.mark.parametrize("numeric_flag", [1, 1.0])
def test_engine_admission_catalog_json_boolean_drift_is_atomic(
    actor: str, numeric_flag: int | float
) -> None:
    # Qualified admission fixture; native controls below exercise the real request.
    session, state, decisions, proposal = _window(active_player=other_player(actor), actor=actor)
    request = create_stratagem_target_proposal_decision_request(
        state=state, proposal_request=proposal
    )
    decisions.request_decision(request)
    target = "army-alpha:one" if actor == "player-a" else "army-beta:enemy"
    submitted = proposal.with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id=actor,
            target_unit_instance_id=target,
        )
    )
    original = submitted.to_payload()
    changed = deepcopy(original)
    changed["catalog_record"]["definition"]["effect_payload"] = {
        "requires_opponent_turn": numeric_flag
    }
    assert original == changed  # Python equality alone masks the malformed JSON kind.
    before = session.lifecycle.to_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order135-b03:catalog-json-kind-denied",
        payload={"proposal": validate_json_value(changed)},
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status.payload == {"invalid_reason": "wrong_context"}
    assert session.lifecycle.to_payload() == before
    assert state.command_point_total(actor) == 2


@pytest.mark.parametrize("actor", ["player-a", "player-b"])
def test_engine_admission_context_json_kinds_preserve_valid_number_echo(actor: str) -> None:
    # Constructed context metadata tests JSON-kind equality, not a native consumer rule.
    session, state, decisions, proposal = _window(active_player=other_player(actor), actor=actor)
    trigger = cast(dict[str, JsonValue], deepcopy(proposal.context.trigger_payload))
    trigger["order135_json_kind_control"] = {"nested": [True, {"number": 1.0}]}
    proposal = replace(proposal, context=replace(proposal.context, trigger_payload=trigger))
    request = create_stratagem_target_proposal_decision_request(
        state=state, proposal_request=proposal
    )
    decisions.request_decision(request)
    target = "army-alpha:one" if actor == "player-a" else "army-beta:enemy"
    submitted = proposal.with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id=actor,
            target_unit_instance_id=target,
        )
    )
    before = session.lifecycle.to_payload()
    changed = deepcopy(submitted.to_payload())
    assert "trigger_payload" in changed["context"]
    changed_trigger = cast(dict[str, JsonValue], changed["context"]["trigger_payload"])
    changed_trigger["order135_json_kind_control"] = {"nested": [1, {"number": 1.0}]}
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order135-b03:context-json-kind-denied",
        payload={"proposal": validate_json_value(changed)},
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status.payload == {"invalid_reason": "wrong_context"}
    assert session.lifecycle.to_payload() == before
    valid = deepcopy(submitted.to_payload())
    assert "trigger_payload" in valid["context"]
    valid_trigger = cast(dict[str, JsonValue], valid["context"]["trigger_payload"])
    valid_trigger["order135_json_kind_control"] = {"nested": [True, {"number": 1}]}
    # Object insertion order and equal JSON number representations are valid echoes.
    valid["context"]["trigger_payload"] = dict(reversed(valid_trigger.items()))
    accepted = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order135-b03:context-valid-number-echo",
        payload={"proposal": validate_json_value(valid)},
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted.to_payload()
    assert state.command_point_total(actor) == 0
    assert state.stratagem_use_records[-1].stratagem_id == "counteroffensive"


def test_actual_generic_source_retains_opponent_turn_availability() -> None:
    # Source-backed generic consumer in its existing qualified Shooting fixture.
    session, units, _pool = smoke_session()
    state = session.lifecycle.state
    assert state is not None
    record = next(
        r
        for r in eleventh_edition_stratagem_index().all_records()
        if r.definition.stratagem_id == "smokescreen"
    )
    index = StratagemCatalogIndex.from_records((record,))
    context = StratagemEligibilityContext.from_state(
        state=state, player_id="player-b", trigger_kind=TimingTriggerKind.START_PHASE
    )
    options = stratagem_use_options_from_index(state=state, index=index, context=context)
    assert any(
        option.option_id == f"use-stratagem:smokescreen:target:{units['smoke'].unit_instance_id}"
        for option in options
    )
    state.active_player_id = "player-b"
    own_context = StratagemEligibilityContext.from_state(
        state=state, player_id="player-b", trigger_kind=TimingTriggerKind.START_PHASE
    )
    assert stratagem_use_options_from_index(state=state, index=index, context=own_context) == ()


@pytest.mark.parametrize("own_turn", [False, True])
def test_actual_carnival_source_retains_either_turn_availability(own_turn: bool) -> None:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.lords_of_the_warp import (  # noqa: E501
        stratagems,
    )
    from warhammer40k_core.engine.list_validation import DetachmentSelection

    # Qualified domain consumer fixture, not native whole-provider certification.
    session, state, _decisions, proposal = _window(
        active_player="player-a" if own_turn else "player-b", actor="player-a"
    )
    contribution = stratagems.runtime_contribution()
    record = next(
        r for r in contribution.stratagem_records if r.definition.name == "Carnival of Excess"
    )
    assert record.detachment_id is not None
    state.army_definitions = [
        replace(
            army,
            detachment_selection=DetachmentSelection(
                faction_id="CD", detachment_ids=(record.detachment_id,)
            ),
            units=tuple(
                with_unit_keywords(
                    unit,
                    keywords=("CHARACTER", "SLAANESH"),
                    faction_keywords=("LEGIONES DAEMONICA",),
                )
                for unit in army.units
            ),
        )
        if army.player_id == "player-a"
        else army
        for army in state.army_definitions
    ]
    payload = record.definition.effect_payload
    assert isinstance(payload, dict)
    assert "requires_own_turn" not in payload
    assert "requires_opponent_turn" not in payload
    options = stratagem_use_options_from_index(
        state=state, index=StratagemCatalogIndex.from_records((record,)), context=proposal.context
    )
    assert any(
        option.option_id == f"use-stratagem:{record.definition.stratagem_id}:target:army-alpha:one"
        for option in options
    )
    assert state.command_point_total("player-a") == 2
    assert state.stratagem_use_records == []
    assert session.lifecycle.state is state


def test_shared_turn_metadata_retains_strict_short_circuit_and_absent_active_semantics() -> None:
    # Malformed/contradictory source metadata cannot arise through legal gameplay.
    # These qualified definition controls preserve the existing generic contract.
    _session, _state, _decisions, proposal = _window(active_player="player-a", actor="player-a")
    definition = proposal.catalog_record.definition
    own = proposal.context
    opponent = replace(own, active_player_id="player-b")
    absent = replace(own, active_player_id=None)

    def reason(payload: JsonValue, context: StratagemEligibilityContext) -> str | None:
        return stratagem_turn_unavailable_reason(
            definition=replace(definition, effect_payload=payload), context=context
        )

    inactive_payloads: tuple[JsonValue, ...] = (
        None,
        {},
        {"requires_own_turn": None, "requires_opponent_turn": None},
        {"requires_own_turn": False, "requires_opponent_turn": False},
    )
    for payload in inactive_payloads:
        assert reason(payload, own) is None
        assert reason(payload, opponent) is None
        assert reason(payload, absent) is None
    assert reason({"requires_own_turn": True}, own) is None
    assert reason({"requires_own_turn": True}, opponent) == "stratagem_requires_own_turn"
    assert reason({"requires_own_turn": True}, absent) == "stratagem_requires_own_turn"
    assert reason({"requires_opponent_turn": True}, own) == "stratagem_requires_opponent_turn"
    assert reason({"requires_opponent_turn": True}, opponent) is None
    assert reason({"requires_opponent_turn": True}, absent) is None
    both: JsonValue = {"requires_own_turn": True, "requires_opponent_turn": True}
    assert reason(both, opponent) == "stratagem_requires_own_turn"
    assert reason(both, own) == "stratagem_requires_opponent_turn"
    assert (
        reason({"requires_own_turn": True, "requires_opponent_turn": 1}, opponent)
        == "stratagem_requires_own_turn"
    )
    for key in ("requires_own_turn", "requires_opponent_turn"):
        for invalid in (0, 1, "true"):
            with pytest.raises(GameLifecycleError, match=f"{key} must be a bool"):
                reason({key: invalid}, own)
    with pytest.raises(GameLifecycleError, match="requires_opponent_turn must be a bool"):
        reason({"requires_own_turn": True, "requires_opponent_turn": 1}, own)


def _continue_native_fight(session: LocalGameSession, *, first_player: str, target: str) -> None:
    previous = {event.event_id for event in actual_fought_events(session)}
    for _ in range(50):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        completed = [
            event
            for event in actual_fought_events(session)
            if event.event_id not in previous
            and isinstance(event.payload, dict)
            and isinstance(event.payload["activation_selection"], dict)
            and event.payload["activation_selection"]["unit_instance_id"] == target
        ]
        if completed:
            assert len(completed) == 1
            assert isinstance(completed[0].payload, dict)
            assert completed[0].payload["attack_sequence_id"] is not None
            return
        submit_native_combat_choice(session, request, first_player=first_player)
    raise AssertionError("Native legal melee continuation was not completed")


def _assert_native_continuations(
    session: LocalGameSession, *, first_player: str, target: str
) -> None:
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    forked = session.fork()
    for continuation in (session, restored, forked):
        _continue_native_fight(continuation, first_player=first_player, target=target)
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    assert forked.to_persistence_payload() == session.to_persistence_payload()
    assert_checkpoint(session)


@pytest.mark.parametrize("first_player", ["player-a", "player-b"])
def test_native_core_counteroffensive_own_turn_is_not_offered(first_player: str) -> None:
    session = native_combat_session(first_player=first_player)
    for _ in range(400):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        state = session.lifecycle.state
        assert state is not None
        if request.decision_type == "submit_stratagem_target_proposal":
            proposal = proposal_from_native_request(request)
            if proposal.stratagem_id == "counteroffensive":
                assert proposal.player_id != state.active_player_id
        enemy_fought = [
            event
            for event in actual_fought_events(session)
            if isinstance(event.payload, dict)
            and event.payload["battle_round"] == 3
            and isinstance(event.payload["activation_selection"], dict)
            and event.payload["activation_selection"]["player_id"] == other_player(first_player)
        ]
        if (
            state.battle_round == 3
            and state.current_battle_phase is BattlePhase.FIGHT
            and state.active_player_id == first_player
            and enemy_fought
            and request.decision_type == "select_fight_activation"
            and request.actor_id == first_player
        ):
            # A normal remaining friendly selection establishes real eligibility.
            assert state.command_point_total(first_player) >= 2
            assert isinstance(enemy_fought[-1].payload, dict)
            assert enemy_fought[-1].payload["attack_sequence_id"] is not None
            target_payload = cast(dict[str, JsonValue], request.options[0].payload)
            assert target_payload is not None
            assert state.fight_phase_state is not None
            assert state.stratagem_use_records == []
            assert not any(
                selection.interrupt_id is not None
                and selection.interrupt_id.startswith("counteroffensive:")
                for selection in state.fight_phase_state.fight_order_state.activation_selections
            )
            assert not any(
                isinstance(effect.effect_payload, dict)
                and effect.effect_payload.get("effect_kind") == "fights_first"
                for effect in state.persisting_effects
            )
            assert_checkpoint(session)
            before_cp = state.command_point_total(first_player)
            # The actual option payload is the engine's activation selection.
            target = cast(str, target_payload["unit_instance_id"])
            _assert_native_continuations(session, first_player=first_player, target=target)
            assert state.command_point_total(first_player) == before_cp
            assert state.stratagem_use_records == []
            return
        submit_native_combat_choice(session, request, first_player=first_player)
    raise AssertionError(
        "Native own-turn enemy fight with eligible friendly continuation not reached"
    )


@pytest.mark.parametrize("first_player", ["player-a", "player-b"])
def test_native_core_counteroffensive_opponent_turn_acceptance_persists(first_player: str) -> None:
    session = native_combat_session(first_player=first_player)
    actor = other_player(first_player)
    for _ in range(400):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        if request.decision_type == "submit_stratagem_target_proposal":
            proposal = proposal_from_native_request(request)
            if proposal.stratagem_id == "counteroffensive" and proposal.player_id == actor:
                state = session.lifecycle.state
                assert state is not None
                assert proposal.player_id == actor
                assert state.active_player_id == first_player
                assert proposal.context.active_player_id == state.active_player_id
                trigger = cast(dict[str, JsonValue], proposal.context.trigger_payload)
                source_event = next(
                    e
                    for e in actual_fought_events(session)
                    if e.event_id == trigger["trigger_event_id"]
                )
                assert isinstance(source_event.payload, dict)
                assert source_event.payload["attack_sequence_id"] is not None
                assert proposal.catalog_record.definition.effect_payload == {
                    "requires_opponent_turn": True
                }
                targets = cast(list[str], trigger["eligible_unit_instance_ids"])
                target = targets[0]
                submitted = proposal.with_binding(
                    StratagemTargetBinding(
                        target_kind=StratagemTargetKind.FRIENDLY_UNIT,
                        target_player_id=actor,
                        target_unit_instance_id=target,
                    )
                )
                assert_checkpoint(session)
                before = session.lifecycle.to_payload()
                drifted_context = replace(
                    submitted, context=replace(submitted.context, active_player_id=actor)
                )
                context_invalid = session.submit_parameterized_payload(
                    request_id=request.request_id,
                    result_id="order135-b03:client-context-drift",
                    payload={"proposal": validate_json_value(drifted_context.to_payload())},
                )
                assert context_invalid.status_kind is LifecycleStatusKind.INVALID
                assert context_invalid.payload == {"invalid_reason": "wrong_context"}
                assert session.lifecycle.to_payload() == before
                drifted = submitted.to_payload()
                drifted["catalog_record"]["definition"]["effect_payload"] = {
                    "requires_opponent_turn": False
                }
                invalid = session.submit_parameterized_payload(
                    request_id=request.request_id,
                    result_id="order135-b02:client-source-metadata-drift",
                    payload={"proposal": validate_json_value(drifted)},
                )
                assert invalid.status_kind is LifecycleStatusKind.INVALID
                assert session.lifecycle.to_payload() == before
                for numeric_flag in (1, 1.0):
                    malformed = deepcopy(submitted.to_payload())
                    malformed["catalog_record"]["definition"]["effect_payload"] = {
                        "requires_opponent_turn": numeric_flag
                    }
                    type_invalid = session.submit_parameterized_payload(
                        request_id=request.request_id,
                        result_id="order135-b03:native-catalog-json-kind-denied",
                        payload={"proposal": validate_json_value(malformed)},
                    )
                    assert type_invalid.status_kind is LifecycleStatusKind.INVALID
                    assert type_invalid.payload == {"invalid_reason": "wrong_context"}
                    assert session.lifecycle.to_payload() == before
                cp_before = state.command_point_total(actor)
                accepted = session.submit_parameterized_payload(
                    request_id=request.request_id,
                    result_id="order135-b02:legal-opponent-turn",
                    payload={"proposal": validate_json_value(submitted.to_payload())},
                )
                assert accepted.status_kind is not LifecycleStatusKind.INVALID, (
                    accepted.to_payload()
                )
                record = state.stratagem_use_records[-1]
                assert record.stratagem_id == "counteroffensive"
                assert record.player_id == actor
                assert record.command_point_cost == 2
                assert state.command_point_total(actor) == cp_before - 2
                assert state.fight_phase_state is not None
                selection = state.fight_phase_state.fight_order_state.activation_selections[-1]
                assert selection.unit_instance_id == target
                assert selection.interrupt_id is not None
                assert selection.interrupt_id.startswith("counteroffensive:")
                effects = [
                    effect
                    for effect in state.persisting_effects
                    if isinstance(effect.effect_payload, dict)
                    and effect.effect_payload.get("effect_kind") == "fights_first"
                    and target in effect.target_unit_instance_ids
                ]
                assert len(effects) == 1
                assert state.active_player_id is not None
                assert effects[0].expiration == EffectExpiration.end_phase(
                    battle_round=state.battle_round,
                    phase=BattlePhase.FIGHT,
                    player_id=state.active_player_id,
                )
                assert_checkpoint(session)
                _assert_native_continuations(session, first_player=first_player, target=target)
                return
        submit_native_combat_choice(session, request, first_player=first_player)
    raise AssertionError("Native legal opponent-turn Core offer not reached")
