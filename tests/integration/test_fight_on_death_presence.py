from __future__ import annotations

import json
from dataclasses import replace

import pytest
from tests.order32_visibility_helpers import retained_observer_session, visible_enemy_selection
from tests.phase13b_shooting_declaration_helpers import (
    _destroyed_transport_placement_payload_for_test,
    _proposal_from_request,
    _shooting_lifecycle,
)
from tests.phase15c_fight_order_helpers import fight_lifecycle
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from tests.retained_attack_helpers import (
    lethal_retained_attack_catalog,
    pending_retained_attack,
)

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.ability_presence import ability_presence
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    eligible_selection_target_unit_ids,
)
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionKind,
    DestructionReactionSource,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.retained_destruction_state import retained_destructions
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.transports import TransportCapacityProfile, TransportCargoState
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("retain", [False, True])
def test_r32_retained_only_observer_eligibility_restores_replays_and_cleans_up(
    attached: bool,
    retain: bool,
) -> None:
    session, observer_id, target_id = retained_observer_session(attached=attached)
    pending_request(session)
    initial = session.lifecycle.to_payload()
    for _ in range(30):
        request = pending_request(session)
        if request.decision_type == "select_destruction_reaction":
            break
        if request.decision_type == "submit_shooting_declaration":
            state = session.lifecycle.state
            assert state is not None
            target_view = rules_unit_view_by_id(
                state=state, unit_instance_id=state.unit_instance_id_for_model(observer_id)
            )
            proposal = _proposal_from_request(
                request=request, target_unit_id=target_view.unit_instance_id
            )
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id="r32-lethal-shot",
                payload=validate_json_value(proposal.to_payload()),
            )
            assert status.status_kind is not LifecycleStatusKind.INVALID
        else:
            submit_fixture_request(session, request)
    else:
        raise AssertionError("The real lethal shot did not offer observer retention.")
    status = session.submit_option(
        request_id=request.request_id,
        result_id="r32-observer-retention-choice",
        option_id="r32-retain-observer" if retain else "decline_destruction_reaction",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID

    def assert_eligibility(candidate: LocalGameSession, *, expected: bool) -> None:
        state = candidate.lifecycle.state
        assert state is not None
        source_id = state.unit_instance_id_for_model(observer_id)
        view = rules_unit_view_by_id(state=state, unit_instance_id=source_id)
        observer_component = view.component_unit_for_model(observer_id)
        assert not any(model.is_alive for model in observer_component.own_models)
        presence = ability_presence(state=state, rules_unit=view)
        assert (observer_id in presence.active_model_ids) is expected
        for scope in ("this_model", "this_unit"):
            assert eligible_selection_target_unit_ids(
                state=state,
                source_player_id="player-b",
                source_unit_instance_id=source_id,
                source_model_instance_id=observer_id if scope == "this_model" else None,
                selection_clause=visible_enemy_selection(observer=scope),
                explicit_target_unit_ids=(target_id,),
            ) == ((target_id,) if expected else ())
        if attached:
            # The surviving component is deliberately blocked; it cannot mask the lost observer.
            leader_view = rules_unit_view_by_id(state=state, unit_instance_id="army-beta:leader")
            leader = next(
                component.unit
                for component in leader_view.components
                if component.unit.unit_instance_id == "army-beta:leader"
            )
            assert leader.own_models[0].is_alive
            leader_id = leader.own_models[0].model_instance_id
            assert (
                eligible_selection_target_unit_ids(
                    state=state,
                    source_player_id="player-b",
                    source_unit_instance_id=leader_view.unit_instance_id,
                    source_model_instance_id=leader_id,
                    selection_clause=visible_enemy_selection(observer="this_model"),
                    explicit_target_unit_ids=(target_id,),
                )
                == ()
            )

    assert_eligibility(session, expected=retain)
    checkpoint = session.lifecycle.to_payload()
    standalone = LocalGameSession(lifecycle=GameLifecycle.from_payload(checkpoint))
    restored = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    for candidate in (standalone, restored):
        assert candidate.lifecycle.to_payload() == checkpoint
        assert_eligibility(candidate, expected=retain)
        for viewer in ("player-a", "player-b"):
            assert candidate.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
            events = candidate.events_since(EventStreamCursor(), viewer_player_id=viewer)
            assert events == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
            public = json.dumps({"view": candidate.view(viewer_player_id=viewer), "events": events})
            for private in ('"cause_id"', '"owner_context"', '"retention_sha256"'):
                assert private not in public
    artifact = ReplayArtifact.capture(
        artifact_id=f"r32-observer-retained:{attached}:{retain}",
        initial_lifecycle_payload=initial,
        final_lifecycle=restored.lifecycle,
    )
    replay = ReplayRunner.from_payload(artifact.to_payload()).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay

    if retain:
        for _ in range(40):
            state = restored.lifecycle.state
            assert state is not None
            assert state.battlefield_state is not None
            if observer_id in state.battlefield_state.removed_model_ids:
                break
            request = pending_request(restored)
            if any(option.option_id == "complete_shooting_phase" for option in request.options):
                status = restored.submit_option(
                    request_id=request.request_id,
                    result_id="r32-complete-shooting",
                    option_id="complete_shooting_phase",
                )
                assert status.status_kind is not LifecycleStatusKind.INVALID
            else:
                submit_fixture_request(restored, request)
        else:
            raise AssertionError("Retained observer cleanup was not reached.")
        assert_eligibility(restored, expected=False)
        cleaned = GameLifecycle.from_payload(restored.lifecycle.to_payload())
        assert cleaned.to_payload() == restored.lifecycle.to_payload()
        assert_eligibility(LocalGameSession(lifecycle=cleaned), expected=False)
        artifact = ReplayArtifact.capture(
            artifact_id=f"r32-observer-cleanup:{attached}",
            initial_lifecycle_payload=checkpoint,
            final_lifecycle=cleaned,
        )
        replay = ReplayRunner.from_payload(artifact.to_payload()).run()
        assert replay.status is ReplayRunStatus.REPRODUCED, replay


def test_order_30_expired_grant_rejects_selection_before_queue_pop() -> None:
    session, _model_id = pending_retained_attack(conditional_grant=True)
    state = session.lifecycle.state
    assert state is not None
    state.persisting_effects = [
        effect for effect in state.persisting_effects if effect.effect_id != "order-30-grant-effect"
    ]
    request = pending_request(session)
    before = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id,
        result_id="expired-grant",
        option_id="order-30-fight-on-death",
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    with pytest.raises(GameLifecycleError, match="granting conditions drift"):
        GameLifecycle.from_payload(before)


def test_order_30_multiple_grants_select_exactly_one_source() -> None:
    session, model_id = pending_retained_attack(additional_grant=True)
    request = pending_request(session)
    assert {option.option_id for option in request.options} == {
        "order-30-fight-on-death",
        "order-30-alternate-grant",
        "decline_destruction_reaction",
    }
    session.submit_option(
        request_id=request.request_id,
        result_id="alternate-grant",
        option_id="order-30-alternate-grant",
    )
    state = session.lifecycle.state
    assert state is not None
    records = retained_destructions(state=state)
    assert len(records) == 1
    assert records[0].model_instance_id == model_id
    assert records[0].selected_source_id == "order-30-alternate-grant"
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )


def test_order_30_failed_trigger_continues_destruction_without_retention() -> None:
    session, model_id = pending_retained_attack(trigger_threshold=6, stop_after_removal=True)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert model_id in state.battlefield_state.removed_model_ids
    assert not retained_destructions(state=state)
    trigger = next(
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "fight_on_death_retention_trigger_resolved"
    )
    assert isinstance(trigger.payload, dict)
    assert trigger.payload["triggered"] is False
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )


def test_order_30_pending_reaction_does_not_remove_model() -> None:
    session, model_id = pending_retained_attack()
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert model_id in state.battlefield_state.placed_model_ids()
    assert model_id not in state.battlefield_state.removed_model_ids


def test_order_30_accepted_model_retains_datasheet_ability_presence() -> None:
    session, model_id = pending_retained_attack()
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        result_id="order-30-accept",
        option_id="order-30-fight-on-death",
    )
    state = session.lifecycle.state
    assert state is not None
    view = rules_unit_view_by_id(
        state=state, unit_instance_id=state.unit_instance_id_for_model(model_id)
    )
    presence = ability_presence(state=state, rules_unit=view)
    assert model_id in presence.active_model_ids
    assert model_id in presence.battlefield_model_ids


def test_order_30_other_destruction_triggers_wait_for_retained_model_completion() -> None:
    session, model_id = pending_retained_attack(deadly_demise=True)
    assert not any(
        event.event_type == "destruction_reaction_resolved"
        and isinstance(event.payload, dict)
        and event.payload.get("model_instance_id") == model_id
        and event.payload.get("selected_reaction_kind") == "deadly_demise"
        for event in session.lifecycle.decision_controller.event_log.records
    )


def test_order_30_pending_retention_restores_with_original_cause_and_placement() -> None:
    session, model_id = pending_retained_attack()
    restored = GameLifecycle.from_payload(session.lifecycle.to_payload())
    assert restored.to_payload() == session.lifecycle.to_payload()
    assert restored.state is not None
    assert restored.state.battlefield_state is not None
    assert model_id in restored.state.battlefield_state.placed_model_ids()


def test_order_30_accepted_retention_restores_without_removal_history() -> None:
    session, model_id = pending_retained_attack()
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        result_id="accept-retention",
        option_id="order-30-fight-on-death",
    )
    restored = GameLifecycle.from_payload(session.lifecycle.to_payload())
    assert restored.to_payload() == session.lifecycle.to_payload()
    assert not any(
        event.event_type == "model_destroyed"
        and isinstance(event.payload, dict)
        and event.payload.get("model_instance_id") == model_id
        for event in restored.decision_controller.event_log.records
    )


def test_order_30_declined_retention_completes_original_destruction_once() -> None:
    session, model_id = pending_retained_attack()
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        result_id="decline-retention",
        option_id="decline_destruction_reaction",
    )
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert model_id in state.battlefield_state.removed_model_ids
    assert (
        sum(
            event.event_type == "model_destroyed"
            and isinstance(event.payload, dict)
            and event.payload.get("model_instance_id") == model_id
            for event in session.lifecycle.decision_controller.event_log.records
        )
        == 1
    )


def test_order_30_phase_end_resolves_delayed_triggers_before_single_removal() -> None:
    session, model_id = pending_retained_attack(deadly_demise=True)
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        result_id="accept-retention",
        option_id="order-30-fight-on-death",
    )
    for _ in range(40):
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        if model_id in state.battlefield_state.removed_model_ids:
            break
        assert state.current_battle_phase is BattlePhase.SHOOTING
        request = pending_request(session)
        submit_fixture_request(session, request)
    else:
        raise AssertionError("Phase-end retention cleanup was not reached.")
    events = session.lifecycle.decision_controller.event_log.records
    completed = tuple(
        event for event in events if event.event_type == "fight_on_death_destruction_completed"
    )
    assert len(completed) == 1
    assert isinstance(completed[0].payload, dict)
    assert completed[0].payload["model_instance_id"] == model_id
    assert (
        sum(
            event.event_type == "model_destroyed"
            and isinstance(event.payload, dict)
            and event.payload.get("model_instance_id") == model_id
            for event in events
        )
        == 1
    )
    restored = GameLifecycle.from_payload(session.lifecycle.to_payload())
    assert restored.to_payload() == session.lifecycle.to_payload()


def test_order_30_cleanup_feel_no_pain_pauses_and_restores_before_source_removal() -> None:
    session, model_id = pending_retained_attack(deadly_demise=True, cleanup_feel_no_pain=True)
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        result_id="accept-retention",
        option_id="order-30-fight-on-death",
    )
    for _ in range(40):
        request = pending_request(session)
        if request.decision_type == "select_feel_no_pain":
            break
        submit_fixture_request(session, request)
    else:
        raise AssertionError("Delayed Deadly Demise did not request Feel No Pain.")
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert model_id in state.battlefield_state.placed_model_ids()
    restored = GameLifecycle.from_payload(session.lifecycle.to_payload())
    assert restored.to_payload() == session.lifecycle.to_payload()
    session = LocalGameSession(lifecycle=restored)
    for _ in range(20):
        submit_fixture_request(session, pending_request(session))
        current = session.lifecycle.state
        assert current is not None
        assert current.battlefield_state is not None
        assert (
            GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
            == session.lifecycle.to_payload()
        )
        if model_id in current.battlefield_state.removed_model_ids:
            break
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert model_id in state.battlefield_state.removed_model_ids
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )


def test_order_30_retained_model_fights_from_original_base_then_is_removed() -> None:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={"intercessor-1": Pose.at(10, 10), "enemy": Pose.at(12, 10)},
        game_id="order-30-retained-fight",
        model_count=1,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        catalog=lethal_retained_attack_catalog(),
        fights_first_unit_keys=("intercessor-1",),
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    model_id = units["enemy"].own_models[0].model_instance_id
    placement = state.battlefield_state.model_placement_or_none(model_id)
    assert placement is not None
    state.record_model_destruction_reaction_sources(
        model_instance_id=model_id,
        sources=(
            DestructionReactionSource(
                source_id="order-30-fight-on-death",
                source_rule_id="order-30-fight-on-death",
                reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
            ),
        ),
    )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
    accepted = False
    retained_melee = False
    for _ in range(50):
        request = pending_request(session)
        if request.decision_type == "select_destruction_reaction":
            session.submit_option(
                request_id=request.request_id,
                result_id="accept-retention",
                option_id="order-30-fight-on-death",
            )
            accepted = True
        else:
            if accepted and request.decision_type == "submit_melee_declaration":
                retained_melee = True
            submit_fixture_request(session, request)
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        if model_id in state.battlefield_state.removed_model_ids:
            break
        assert state.battlefield_state.model_placement_or_none(model_id) == placement
        restored = GameLifecycle.from_payload(session.lifecycle.to_payload())
        assert restored.to_payload() == session.lifecycle.to_payload()
    assert accepted
    assert retained_melee
    assert state.battlefield_state is not None
    assert model_id in state.battlefield_state.removed_model_ids
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )


@pytest.mark.parametrize("accept_child", [True, False])
def test_order_30_collateral_retention_preserves_parent_cleanup_and_restores(
    accept_child: bool,
) -> None:
    session, model_id = pending_retained_attack(deadly_demise=True, collateral_retention=True)
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        result_id="accept-parent-retention",
        option_id="order-30-fight-on-death",
    )
    for _ in range(45):
        request = pending_request(session)
        if any(
            option.option_id == "order-30-collateral-fight-on-death" for option in request.options
        ):
            break
        submit_fixture_request(session, request)
    else:
        raise AssertionError("Collateral retention decision was not offered.")
    restored = GameLifecycle.from_payload(session.lifecycle.to_payload())
    assert restored.to_payload() == session.lifecycle.to_payload()
    session = LocalGameSession(lifecycle=restored)
    session.submit_option(
        request_id=request.request_id,
        result_id="accept-child-retention",
        option_id="order-30-collateral-fight-on-death"
        if accept_child
        else "decline_destruction_reaction",
    )
    for _ in range(30):
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        restored = GameLifecycle.from_payload(session.lifecycle.to_payload())
        assert restored.to_payload() == session.lifecycle.to_payload()
        if model_id in state.battlefield_state.removed_model_ids:
            break
        submit_fixture_request(session, pending_request(session))
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert model_id in state.battlefield_state.removed_model_ids
    completions = tuple(
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "fight_on_death_destruction_completed"
    )
    assert len(completions) == (2 if accept_child else 1)


def test_order_30_retained_transport_defers_cargo_placement_and_restores_cleanup() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        catalog=lethal_retained_attack_catalog(),
        game_id="order32-retained-transport-0",
        enemy_unit_specs=(
            ("enemy", "core-transport", "core-transport", 1),
            ("passenger", "core-intercessor-like-infantry", "core-intercessor-like", 5),
        ),
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    transport = units["enemy"]
    passenger = units["passenger"]
    model_id = transport.own_models[0].model_instance_id
    placement = state.battlefield_state.model_placement_by_id(model_id)
    state.replace_battlefield_state(
        state.battlefield_state.without_unit_placement(passenger.unit_instance_id)
    )
    state.record_transport_cargo_state(
        TransportCargoState(
            player_id="player-b",
            transport_unit_instance_id=transport.unit_instance_id,
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=transport.datasheet_id,
                max_model_count=10,
                allowed_keywords=("INFANTRY",),
            ),
            embarked_unit_instance_ids=(passenger.unit_instance_id,),
            phase_battle_round=1,
            started_phase_embarked_unit_instance_ids=(passenger.unit_instance_id,),
        )
    )
    state.record_model_destruction_reaction_sources(
        model_instance_id=model_id,
        sources=(
            DestructionReactionSource(
                source_id="order-30-transport-retention",
                source_rule_id="order-30-transport-retention",
                reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
            ),
        ),
    )
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(lifecycle.to_payload()))
    accepted = False
    for _ in range(50):
        request = pending_request(session)
        if request.decision_type == "select_destruction_reaction":
            session.submit_option(
                request_id=request.request_id,
                result_id="retain-transport",
                option_id="order-30-transport-retention",
            )
            accepted = True
        elif request.decision_type == "submit_placement_proposal":
            assert accepted
            break
        else:
            submit_fixture_request(session, request)
    else:
        raise AssertionError("Deferred cargo placement was not reached.")
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert state.battlefield_state.model_placement_by_id(model_id) == placement
    restored = GameLifecycle.from_payload(session.lifecycle.to_payload())
    assert restored.to_payload() == session.lifecycle.to_payload()
    session = LocalGameSession(lifecycle=restored)
    placement_payload = _destroyed_transport_placement_payload_for_test(
        proposal_request=MovementProposalRequest.from_decision_request_payload(request.payload),
        unit=passenger,
        transport=transport,
    )
    placement_payload["attempted_placement"] = validate_json_value(
        UnitPlacement(
            army_id="army-beta",
            player_id="player-b",
            unit_instance_id=passenger.unit_instance_id,
            model_placements=tuple(
                ModelPlacement(
                    army_id="army-beta",
                    player_id="player-b",
                    unit_instance_id=passenger.unit_instance_id,
                    model_instance_id=model.model_instance_id,
                    pose=Pose.at(38, 32 + 1.5 * index),
                )
                for index, model in enumerate(
                    rules_unit_view_by_id(
                        state=state,
                        unit_instance_id=passenger.unit_instance_id,
                    ).alive_models()
                )
            ),
        ).to_payload()
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="place-retained-transport-cargo",
        payload=placement_payload,
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert model_id in state.battlefield_state.removed_model_ids
    assert not retained_destructions(state=state)
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )


@pytest.mark.parametrize("drift", ["source", "phase", "owner"])
def test_order_30_retention_drift_is_rejected_before_queue_pop(drift: str) -> None:
    session, model_id = pending_retained_attack()
    request = pending_request(session)
    state = session.lifecycle.state
    assert state is not None
    if drift == "source":
        state.clear_model_destruction_reaction_sources(model_instance_id=model_id)
    elif drift == "phase":
        state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    else:
        effect = next(
            effect
            for effect in state.persisting_effects
            if effect.effect_id.startswith("retained-destruction:")
        )
        state.persisting_effects = [
            replace(item, owner_player_id="player-a")
            if item.effect_id == effect.effect_id
            else item
            for item in state.persisting_effects
        ]
    before = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id,
        result_id="invalid-retention",
        option_id="order-30-fight-on-death",
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


def test_order_30_restore_rejects_retention_owner_snapshot_drift() -> None:
    session, _model_id = pending_retained_attack()
    payload = session.lifecycle.to_payload()
    state = payload["state"]
    assert state is not None
    effect = next(
        item
        for item in state["persisting_effects"]
        if item["effect_id"].startswith("retained-destruction:")
    )
    effect_payload = effect["effect_payload"]
    assert isinstance(effect_payload, dict)
    retained = effect_payload["destruction"]
    assert isinstance(retained, dict)
    context = retained["owner_context"]
    assert isinstance(context, dict)
    context["sequence_id"] = "forged-owner-sequence"
    with pytest.raises(GameLifecycleError, match="retained state differs"):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("owner_kind", "unregistered-owner"),
        ("stage", "unregistered-stage"),
        ("placement", []),
        ("owner_context", []),
        ("sources", []),
        ("sources", "invalid-inventory"),
        ("eligible_sources", []),
        ("request_id", None),
        ("result_id", "unsubmitted-result"),
        ("selected_source_id", "unselected-source"),
        ("selected_action", "shoot"),
        ("completion_reason", "phase_end"),
        ("completion_reason", "unregistered-boundary"),
        ("owner_progress", {}),
        ("owner_progress", []),
        ("stage", "waiting_for_unit_attack"),
        ("stage", "not_triggered"),
        ("stage", "declined"),
    ],
)
def test_order_30_restore_rejects_impossible_retention_checkpoints(
    field: str, value: object
) -> None:
    session, _model_id = pending_retained_attack()
    checkpoint = session.lifecycle.to_payload()
    payload = json.loads(json.dumps(checkpoint))
    effect = next(
        item
        for item in payload["state"]["persisting_effects"]
        if item["effect_id"].startswith("retained-destruction:")
    )
    effect["effect_payload"]["destruction"][field] = value
    with pytest.raises(GameLifecycleError, match=r"[Rr]etain|[Rr]etention"):
        GameLifecycle.from_payload(payload)
    assert session.lifecycle.to_payload() == checkpoint


@pytest.mark.parametrize(
    "mutation",
    ["missing_action", "extra_effect_field", "effect_source", "target", "duplicate_sources"],
)
def test_order_30_restore_rejects_retention_identity_inventory_drift(mutation: str) -> None:
    session, _model_id = pending_retained_attack()
    payload = json.loads(json.dumps(session.lifecycle.to_payload()))
    effect = next(
        item
        for item in payload["state"]["persisting_effects"]
        if item["effect_id"].startswith("retained-destruction:")
    )
    record = effect["effect_payload"]["destruction"]
    if mutation == "missing_action":
        del record["selected_action"]
    elif mutation == "extra_effect_field":
        effect["effect_payload"]["unregistered_permission"] = True
    elif mutation == "effect_source":
        effect["source_rule_id"] = "unregistered-retention-rule"
    elif mutation == "target":
        effect["target_unit_instance_ids"] = ["army-alpha:intercessor-1"]
    else:
        record["sources"].append(record["sources"][0])
    with pytest.raises(GameLifecycleError, match=r"[Rr]etain|[Rr]etention"):
        GameLifecycle.from_payload(payload)


def test_order_30_retention_trigger_roll_and_outcome_restore_exactly() -> None:
    session, _model_id = pending_retained_attack(trigger_threshold=1)
    original = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(original).to_payload() == original
    forged = json.loads(json.dumps(original))
    trigger = next(
        event
        for event in forged["decisions"]["event_log"]
        if event["event_type"] == "fight_on_death_retention_trigger_resolved"
    )
    trigger_payload = trigger["payload"]
    assert isinstance(trigger_payload, dict)
    trigger_payload["triggered"] = False
    with pytest.raises(GameLifecycleError, match="trigger outcome drift"):
        GameLifecycle.from_payload(forged)

    forged = json.loads(json.dumps(original))
    trigger = next(
        event
        for event in forged["decisions"]["event_log"]
        if event["event_type"] == "fight_on_death_retention_trigger_resolved"
    )
    trigger_payload = trigger["payload"]
    assert isinstance(trigger_payload, dict)
    trigger_payload["applicable"] = False
    trigger_payload["triggered"] = False
    trigger_payload["trigger_roll"] = None
    with pytest.raises(GameLifecycleError, match="trigger applicability drift"):
        GameLifecycle.from_payload(forged)

    from warhammer40k_core.engine.retained_destruction_state import pending_cause_for_model
    from warhammer40k_core.engine.retained_destruction_trigger_history import (
        validate_retention_trigger_history,
    )

    state = session.lifecycle.state
    assert state is not None
    record = retained_destructions(state=state)[0]
    cause = pending_cause_for_model(state=state, model_instance_id=record.model_instance_id)
    events = session.lifecycle.decision_controller.event_log.records
    trigger_event = next(
        event for event in events if event.event_type == "fight_on_death_retention_trigger_resolved"
    )
    assert isinstance(trigger_event.payload, dict)
    changes: tuple[tuple[str, object, str], ...] = (
        ("trigger_roll", None, "roll is missing or malformed"),
        ("model_instance_id", "wrong-model", "trigger provenance drift"),
        ("source", {}, "exact trigger evidence"),
    )
    for field, value, diagnostic in changes:
        changed = replace(
            trigger_event, payload={**trigger_event.payload, field: validate_json_value(value)}
        )
        with pytest.raises(GameLifecycleError, match=diagnostic):
            validate_retention_trigger_history(
                record=record,
                cause=cause,
                battle_round=state.battle_round,
                active_player_id="player-a",
                phase="shooting",
                event_records=tuple(
                    changed if event == trigger_event else event for event in events
                ),
            )
    for event_type, diagnostic in (
        ("fight_on_death_retention_trigger_resolved", "trigger inventory drift"),
        ("dice_rolled", "dice authority drift"),
    ):
        with pytest.raises(GameLifecycleError, match=diagnostic):
            validate_retention_trigger_history(
                record=record,
                cause=cause,
                battle_round=state.battle_round,
                active_player_id="player-a",
                phase="shooting",
                event_records=tuple(event for event in events if event.event_type != event_type),
            )


def test_order_30_retention_authority_is_private_for_both_viewers() -> None:
    session, model_id = pending_retained_attack()
    request = pending_request(session)
    for viewer_id in ("player-a", "player-b"):
        public = json.dumps(
            {
                "view": session.view(viewer_player_id=viewer_id),
                "events": session.events_since(EventStreamCursor(), viewer_player_id=viewer_id),
            }
        )
        for private in (
            "fight_on_death_retention_opened",
            '"cause_id"',
            '"logical_death_event_id"',
            '"retention_sha256"',
            '"owner_context"',
            '"owner_progress"',
        ):
            assert private not in public
    session.submit_option(
        request_id=request.request_id,
        result_id="accept-public-retention",
        option_id="order-30-fight-on-death",
    )
    for viewer_id in ("player-a", "player-b"):
        events = session.events_since(EventStreamCursor(), viewer_player_id=viewer_id)
        selected = next(
            event
            for event in events["events"]
            if event["event_type"] == "fight_on_death_retention_selected"
        )
        payload = selected["payload"]
        assert isinstance(payload, dict)
        assert payload["model_instance_id"] == model_id
        assert "cause_id" not in payload
        assert "logical_death_event_id" not in payload


def test_order_30_collateral_retention_owns_unretained_parent_continuation() -> None:
    session, parent_model_id = pending_retained_attack(
        deadly_demise=True,
        collateral_retention=True,
        parent_retention=False,
    )
    request = pending_request(session)
    assert any(
        option.option_id == "order-30-collateral-fight-on-death" for option in request.options
    )
    assert (
        GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
        == session.lifecycle.to_payload()
    )
    session.submit_option(
        request_id=request.request_id,
        result_id="retain-collateral-only",
        option_id="order-30-collateral-fight-on-death",
    )
    for _ in range(30):
        assert (
            GameLifecycle.from_payload(session.lifecycle.to_payload()).to_payload()
            == session.lifecycle.to_payload()
        )
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        if parent_model_id in state.battlefield_state.removed_model_ids:
            break
        submit_fixture_request(session, pending_request(session))
    else:
        raise AssertionError("Unretained parent destruction did not complete.")
    assert not retained_destructions(state=state)
