"""Order 42: a replacement is an authenticated new choice, never an implicit target."""

from dataclasses import replace

import pytest

from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.target_replacement import (
    DECLINE_TARGET_REPLACEMENT_OPTION_ID,
    TargetReplacementContext,
    TargetReplacementOption,
    replacement_request,
    replacement_selection,
)


def context() -> TargetReplacementContext:
    return TargetReplacementContext(
        action_id="shooting:action-1",
        selection_id="weapon:1",
        actor_id="player-a",
        source_unit_instance_id="army-a:unit-1",
        original_target_ids=("army-b:unit-1",),
        invalid_target_ids=("army-b:unit-1",),
        source_context_hash="a" * 64,
        options=(TargetReplacementOption("target:2", ("army-b:unit-2",)),),
    )


def test_replacement_round_trip_and_explicit_decline() -> None:
    selection_context = context()
    assert (
        TargetReplacementContext.from_payload(selection_context.to_payload()) == selection_context
    )
    request = replacement_request(request_id="request:1", context=selection_context)
    for option in request.options:
        result = DecisionResult(
            result_id="result:1",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=option.option_id,
            payload=option.payload,
        )
        selected = replacement_selection(request=request, result=result, current=selection_context)
        assert selected == (
            None if option.option_id == DECLINE_TARGET_REPLACEMENT_OPTION_ID else ("army-b:unit-2",)
        )


def test_changed_replacement_candidates_are_rejected_before_selection() -> None:
    original = context()
    request = replacement_request(request_id="request:1", context=original)
    option = request.options[0]
    result = DecisionResult(
        result_id="result:1",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=option.option_id,
        payload=option.payload,
    )
    with pytest.raises(DecisionError, match="drift"):
        replacement_selection(request=request, result=result, current=replace(original, options=()))


def test_shooting_replaces_a_moved_target_through_the_facade_and_replays() -> None:
    from tests.phase13b_shooting_declaration_helpers import _decision_request
    from tests.target_replacement_helpers import replacement_scene

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus

    lifecycle, units, request = replacement_scene()
    session = LocalGameSession(lifecycle=lifecycle)
    assert session.advance_until_decision_or_terminal().decision_request == request
    initial = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="order42:resolve-target",
    )
    request = _decision_request(status)
    assert request.decision_type == "select_target_replacement"
    pending = session.lifecycle.to_payload()
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(pending))
    assert session.lifecycle.to_payload() == pending
    session.submit_option(
        request_id=request.request_id,
        option_id=f"target:{units['new'].unit_instance_id}",
        result_id="order42:replacement",
    )
    event = next(
        e
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "target_replacement_resolved"
    )
    assert isinstance(event.payload, dict)
    assert event.payload["replacement_target_ids"] == [units["new"].unit_instance_id]
    artifact = ReplayArtifact.capture(
        artifact_id="order42:replay",
        final_lifecycle=session.lifecycle,
        initial_lifecycle_payload=initial,
    )
    replay = ReplayRunner.from_payload(artifact.to_payload()).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


def test_out_of_phase_replacement_keeps_owner_pools_through_completion_restore_and_replay() -> None:
    """R42-001: the active out-of-phase action owns one consistent pool tuple."""
    from tests.core_stratagem_helpers import _replace_unit_poses
    from tests.phase13b_shooting_declaration_helpers import _decision_request
    from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
    from tests.target_replacement_reaction_helpers import replacement_reaction_scene

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
    from warhammer40k_core.geometry.pose import Pose

    lifecycle, units, request = replacement_reaction_scene(out_of_phase=True)
    assert request.decision_type == "select_resolve_target_unit"
    state = lifecycle.state
    assert state is not None
    _replace_unit_poses(
        state,
        unit_instance_id=units["old"].unit_instance_id,
        poses=tuple(Pose.at(90 + i, 90) for i in range(len(units["old"].own_models))),
    )
    initial = lifecycle.to_payload()
    session = LocalGameSession(lifecycle=lifecycle)
    request = _decision_request(
        session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id="order42:resolution",
        )
    )
    assert request.decision_type == "select_target_replacement"
    checkpoint = session.lifecycle.to_payload()
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(checkpoint))
    assert session.lifecycle.to_payload() == checkpoint
    session.submit_option(
        request_id=request.request_id,
        option_id=f"target:{units['new'].unit_instance_id}",
        result_id="order42:replacement",
    )
    state = session.lifecycle.state
    assert state is not None
    owner = state.out_of_phase_shooting_state
    assert owner is not None
    assert owner.attack_sequence is not None
    assert owner.attack_pools == owner.attack_sequence.attack_pools
    assert {pool.target_unit_instance_id for pool in owner.attack_pools} == {
        units["new"].unit_instance_id,
        units["unchanged"].unit_instance_id,
    }
    replacement_pools = owner.attack_pools
    for _ in range(30):
        checkpoint = session.lifecycle.to_payload()
        session = LocalGameSession(lifecycle=GameLifecycle.from_payload(checkpoint))
        assert session.lifecycle.to_payload() == checkpoint
        state = session.lifecycle.state
        assert state is not None
        owner = state.out_of_phase_shooting_state
        if owner is None:
            break
        assert owner.attack_pools == replacement_pools
        submit_fixture_request(session, pending_request(session))
    else:
        raise AssertionError("The replaced out-of-phase attack did not complete.")
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.retained_shooting_history import (
        validate_retained_shooting_history,
    )

    events = session.lifecycle.decision_controller.event_log.records
    completion = next(e for e in events if e.event_type == "retained_shooting_attacks_completed")
    assert isinstance(completion.payload, dict)
    assert completion.payload["attack_pools"] == [p.to_payload() for p in replacement_pools]
    for removed_type, result_id in (
        ("target_replacement_resolved", None),
        ("decision_recorded", "order42:replacement"),
        ("decision_recorded", "order42:declaration"),
    ):
        removed = next(
            e
            for e in events
            if e.event_type == removed_type
            and (
                result_id is None
                or (
                    isinstance(e.payload, dict)
                    and "result" in e.payload
                    and isinstance(e.payload["result"], dict)
                    and e.payload["result"].get("result_id") == result_id
                )
            )
        )
        with pytest.raises(GameLifecycleError, match=r"[Rr]eplacement"):
            validate_retained_shooting_history(
                state=state, event_records=tuple(e for e in events if e != removed)
            )
    artifact = ReplayArtifact.capture(
        artifact_id="order42:out-of-phase-replay",
        final_lifecycle=session.lifecycle,
        initial_lifecycle_payload=initial,
    )
    replay = ReplayRunner.from_payload(artifact.to_payload()).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


@pytest.mark.parametrize(
    ("use_original", "decline_new"), [(False, False), (False, True), (True, False)]
)
def test_replacement_opens_a_fresh_defensive_window_without_resetting_usage(
    use_original: bool,
    decline_new: bool,
) -> None:
    """R42-002: selection windows are distinct; phase-wide usage stays authoritative."""
    from tests.core_stratagem_helpers import _replace_unit_poses
    from tests.phase13b_shooting_declaration_helpers import _decision_request
    from tests.target_replacement_reaction_helpers import replacement_reaction_scene

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
    from warhammer40k_core.engine.stratagems import stratagem_window_context_from_request
    from warhammer40k_core.geometry.pose import Pose
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        retained_attack_sources_2026_09 as retained_sources,
    )

    profile = retained_sources.stratagem_profile()
    lifecycle, units, request = replacement_reaction_scene(command_points=2 if use_original else 1)
    original_window = stratagem_window_context_from_request(request)
    session = LocalGameSession(lifecycle=lifecycle)
    request = _decision_request(
        session.submit_option(
            request_id=request.request_id,
            option_id=f"use-stratagem:{profile.stratagem_id}:target:{units['old'].unit_instance_id}"
            if use_original
            else "decline_stratagem_window",
            result_id="order42:original-defense",
        )
    )
    assert request.decision_type == "select_resolve_target_unit"
    state = lifecycle.state
    assert state is not None
    assert state.command_point_total("player-b") == 1
    _replace_unit_poses(
        state,
        unit_instance_id=units["old"].unit_instance_id,
        poses=tuple(Pose.at(90 + i, 90) for i in range(len(units["old"].own_models))),
    )
    initial = lifecycle.to_payload()
    request = _decision_request(
        session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id="order42:resolution",
        )
    )
    assert request.decision_type == "select_target_replacement"
    request = _decision_request(
        session.submit_option(
            request_id=request.request_id,
            option_id=f"target:{units['new'].unit_instance_id}",
            result_id="order42:replacement",
        )
    )
    checkpoint = session.lifecycle.to_payload()
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(checkpoint))
    assert session.lifecycle.to_payload() == checkpoint
    if use_original:
        assert request.decision_type == "select_resolve_target_unit"
        assert (
            len(
                [
                    e
                    for e in session.lifecycle.decision_controller.event_log.records
                    if e.event_type == "unit_selected_as_target_stratagem_window_opened"
                ]
            )
            == 1
        )
    else:
        replacement_window = stratagem_window_context_from_request(request)
        assert replacement_window.timing_window_id != original_window.timing_window_id
        assert replacement_window.trigger_payload == {
            "selected_target_unit_instance_ids": [units["new"].unit_instance_id],
            "attacking_unit_instance_id": units["source"].unit_instance_id,
            "attacking_player_id": "player-a",
            "attack_sequence_id": "attack-sequence:order42:declaration",
        }
        assert {option.option_id for option in request.options} == {
            f"use-stratagem:{profile.stratagem_id}:target:{units['new'].unit_instance_id}",
            "decline_stratagem_window",
        }
        request = _decision_request(
            session.submit_option(
                request_id=request.request_id,
                option_id="decline_stratagem_window"
                if decline_new
                else f"use-stratagem:{profile.stratagem_id}:target:{units['new'].unit_instance_id}",
                result_id="order42:new-defense",
            )
        )
        assert request.decision_type == "select_resolve_target_unit"
        state = session.lifecycle.state
        assert state is not None
        assert state.command_point_total("player-b") == (1 if decline_new else 0)
        assert [
            effect.target_unit_instance_ids
            for effect in state.persisting_effects
            if effect.source_rule_id == profile.source_id
        ] == ([] if decline_new else [(units["new"].unit_instance_id,)])
        checkpoint = session.lifecycle.to_payload()
        session = LocalGameSession(lifecycle=GameLifecycle.from_payload(checkpoint))
        assert session.advance_until_decision_or_terminal().decision_request == request
        assert session.lifecycle.to_payload() == checkpoint
    artifact = ReplayArtifact.capture(
        artifact_id="order42:defensive-window-replay",
        final_lifecycle=session.lifecycle,
        initial_lifecycle_payload=initial,
    )
    replay = ReplayRunner.from_payload(artifact.to_payload()).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


@pytest.mark.parametrize(
    ("mode", "decline"),
    [(mode, decline) for mode in ("normal", "one_shot", "random") for decline in (False, True)]
    + [("snap", True)],
)
def test_replacement_preserves_committed_resources_and_snap_target(
    mode: str, decline: bool
) -> None:
    from tests.phase13b_shooting_declaration_helpers import _decision_request
    from tests.target_replacement_helpers import replacement_scene

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.shooting_target_replacement import active_shooting_sequence

    lifecycle, units, initial = replacement_scene(mode=mode)
    state = lifecycle.state
    assert state is not None
    sequence = active_shooting_sequence(state)
    before_rolls = [
        e
        for e in lifecycle.decision_controller.event_log.records
        if e.event_type == "random_characteristic_rolled"
    ]
    before_uses = state.one_shot_weapon_use_records
    session = LocalGameSession(lifecycle=lifecycle)
    request = _decision_request(
        session.submit_option(
            request_id=initial.request_id,
            option_id=initial.options[0].option_id,
            result_id="order42:resolution",
        )
    )
    assert request.decision_type == "select_target_replacement"
    option_id = (
        DECLINE_TARGET_REPLACEMENT_OPTION_ID
        if decline
        else f"target:{units['new'].unit_instance_id}"
    )
    session.submit_option(
        request_id=request.request_id, option_id=option_id, result_id="order42:replacement"
    )
    event = next(
        e
        for e in lifecycle.decision_controller.event_log.records
        if e.event_type == "target_replacement_resolved"
    )
    assert isinstance(event.payload, dict)
    assert state.one_shot_weapon_use_records == before_uses
    assert [
        e
        for e in lifecycle.decision_controller.event_log.records
        if e.event_type == "random_characteristic_rolled"
    ] == before_rolls
    pools = event.payload["attack_pools"]
    assert isinstance(pools, list)
    assert [p["weapon_instance_id"] for p in pools if isinstance(p, dict)] == [
        p.weapon_instance_id for p in sequence.attack_pools
    ]
    if mode == "snap":
        assert event.payload["used_pool_indices"] == ([0, 1] if decline else [])
        assert {str(p["target_unit_instance_id"]) for p in pools if isinstance(p, dict)} == {
            units["old" if decline else "new"].unit_instance_id
        }


def test_no_alternative_is_an_explicit_decline_and_stale_submission_keeps_queue() -> None:
    from tests.core_stratagem_helpers import _replace_unit_poses
    from tests.phase13b_shooting_declaration_helpers import _decision_request
    from tests.target_replacement_helpers import replacement_scene

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.geometry.pose import Pose

    lifecycle, units, initial = replacement_scene(alternatives=False)
    session = LocalGameSession(lifecycle=lifecycle)
    request = _decision_request(
        session.submit_option(
            request_id=initial.request_id,
            option_id=initial.options[0].option_id,
            result_id="order42:resolution",
        )
    )
    assert tuple(o.option_id for o in request.options) == (DECLINE_TARGET_REPLACEMENT_OPTION_ID,)
    state = lifecycle.state
    assert state is not None
    _replace_unit_poses(
        state,
        unit_instance_id=units["new"].unit_instance_id,
        poses=tuple(Pose.at(18 + i, 25) for i in range(5)),
    )
    snapshot = lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id,
        option_id=DECLINE_TARGET_REPLACEMENT_OPTION_ID,
        result_id="order42:stale",
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.to_payload() == snapshot


@pytest.mark.parametrize("response", ["pending", "decline", "use"])
def test_out_of_phase_fidelity_replacement_offers_defense_in_its_parent_phase(
    response: str,
) -> None:
    """R42-002: retained Shooting must consult the same defensive reaction owner."""
    from tests.phase13b_shooting_declaration_helpers import _decision_request
    from tests.target_replacement_reaction_helpers import fidelity_retained_replacement_scene

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
    from warhammer40k_core.engine.stratagems import stratagem_window_context_from_request
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        retained_attack_sources_2026_09 as retained_sources,
    )

    lifecycle, units, request = fidelity_retained_replacement_scene()
    session = LocalGameSession(lifecycle=lifecycle)
    initial = lifecycle.to_payload()
    request = _decision_request(
        session.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id="order42:counterattack-resolution",
        )
    )
    assert request.decision_type == "select_target_replacement"
    checkpoint = session.lifecycle.to_payload()
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(checkpoint))
    assert session.lifecycle.to_payload() == checkpoint
    before_events = session.lifecycle.decision_controller.event_log.records
    request = _decision_request(
        session.submit_option(
            request_id=request.request_id,
            option_id=f"target:{units['new'].unit_instance_id}",
            result_id="order42:counterattack-replacement",
        )
    )
    profile = retained_sources.stratagem_profile()
    expected_option = f"use-stratagem:{profile.stratagem_id}:target:{units['new'].unit_instance_id}"
    assert expected_option in {option.option_id for option in request.options}, request
    context = stratagem_window_context_from_request(request)
    assert context.phase is BattlePhase.FIGHT
    assert context.player_id == "player-a"
    assert isinstance(context.trigger_payload, dict)
    assert context.trigger_payload["selected_target_unit_instance_ids"] == [
        units["new"].unit_instance_id
    ]
    new_events = session.lifecycle.decision_controller.event_log.records[len(before_events) :]
    window_event = next(
        e for e in new_events if e.event_type == "unit_selected_as_target_stratagem_window_opened"
    )
    assert isinstance(window_event.payload, dict)
    assert window_event.payload["phase"] == BattlePhase.FIGHT.value
    assert not any(e.event_type == "attack_sequence_step" for e in new_events)
    checkpoint = session.lifecycle.to_payload()
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(checkpoint))
    assert session.lifecycle.to_payload() == checkpoint
    if response != "pending":
        status = session.submit_option(
            request_id=request.request_id,
            option_id="decline_stratagem_window" if response == "decline" else expected_option,
            result_id="order42:counterattack-defense",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
        state = session.lifecycle.state
        assert state is not None
        assert state.command_point_total("player-a") == (1 if response == "decline" else 0)
        if response == "use":
            effects = [
                e
                for e in state.persisting_effects
                if e.source_rule_id == profile.source_id
                and isinstance(e.effect_payload, dict)
                and e.effect_payload.get("effect_kind") == "generic_rule_execution"
            ]
            assert len(effects) == 2
            assert len({e.effect_id for e in effects}) == 2
            assert {e.owner_player_id for e in effects} == {"player-a", "player-b"}
            assert state.command_point_total("player-b") == 0
    checkpoint = session.lifecycle.to_payload()
    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(checkpoint))
    assert (
        session.advance_until_decision_or_terminal().decision_request
        == session.lifecycle.decision_controller.queue.peek_next()
    )
    assert session.lifecycle.to_payload() == checkpoint
    artifact = ReplayArtifact.capture(
        artifact_id="order42:fidelity-counterattack-replay",
        final_lifecycle=session.lifecycle,
        initial_lifecycle_payload=initial,
    )
    replay = ReplayRunner.from_payload(artifact.to_payload()).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("actor_id", "wrong-player"),
        ("source_rule_id", "wrong-rule"),
        ("target_replacement_authority_sha256", "b" * 64),
        ("unexpected", True),
    ],
)
def test_checkpoint_rejects_replacement_context_drift(field: str, value: object) -> None:
    from tests.target_replacement_helpers import replacement_scene

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import GameLifecycleError

    lifecycle, _, initial = replacement_scene()
    session = LocalGameSession(lifecycle=lifecycle)
    session.submit_option(
        request_id=initial.request_id,
        option_id=initial.options[0].option_id,
        result_id="order42:resolution",
    )
    payload = lifecycle.to_payload()
    pending = payload["decisions"]["queue"]["pending_requests"][0]
    assert isinstance(pending["payload"], dict)
    from warhammer40k_core.engine.event_log import validate_json_value

    pending["payload"][field] = validate_json_value(value)
    with pytest.raises((GameLifecycleError, DecisionError, ValueError)):
        GameLifecycle.from_payload(payload)


def test_charge_target_query_can_use_the_same_serializable_choice_service() -> None:
    from tests.core_stratagem_helpers import _replace_unit_poses
    from tests.phase15a_charge_declaration_helpers import charge_lifecycle

    from warhammer40k_core.engine.phases.charge import legal_charge_target_unit_instance_ids
    from warhammer40k_core.geometry.pose import Pose

    lifecycle, units = charge_lifecycle(
        alpha_unit_ids=("charger",),
        enemy_unit_ids=("old", "new"),
        enemy_model_poses=(Pose.at(17, 10),),
        enemy_origins={"old": Pose.at(17, 10), "new": Pose.at(18, 10)},
        game_id="order42-charge",
    )
    state = lifecycle.state
    assert state is not None
    source_id = units["charger"].unit_instance_id
    old_id = units["old"].unit_instance_id
    original = legal_charge_target_unit_instance_ids(
        state=state,
        unit_instance_id=source_id,
        ruleset_descriptor=lifecycle.config.ruleset_descriptor,
    )
    assert old_id in original
    _replace_unit_poses(
        state,
        unit_instance_id=old_id,
        poses=tuple(Pose.at(90 + i, 90) for i in range(len(units["old"].own_models))),
    )
    legal = legal_charge_target_unit_instance_ids(
        state=state,
        unit_instance_id=source_id,
        ruleset_descriptor=lifecycle.config.ruleset_descriptor,
    )
    assert old_id not in legal
    current = TargetReplacementContext(
        action_id="charge:accepted-action",
        selection_id="targets",
        actor_id="player-a",
        source_unit_instance_id=source_id,
        original_target_ids=(old_id,),
        invalid_target_ids=(old_id,),
        source_context_hash=state.physical_proposal_context_hash(),
        options=tuple(TargetReplacementOption(f"target:{target}", (target,)) for target in legal),
    )
    restored = TargetReplacementContext.from_payload(current.to_payload())
    request = replacement_request(request_id="charge:replacement", context=restored)
    option = next(o for o in request.options if o.option_id != DECLINE_TARGET_REPLACEMENT_OPTION_ID)
    result = DecisionResult(
        result_id="charge:replacement-result",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=option.option_id,
        payload=option.payload,
    )
    assert replacement_selection(request=request, result=result, current=current) == (
        units["new"].unit_instance_id,
    )


@pytest.mark.parametrize("player", ["player-a", "player-b", None])
def test_replacement_projection_and_events_remove_internal_commitments(player: str | None) -> None:
    import json

    from tests.target_replacement_helpers import replacement_scene

    from warhammer40k_core.adapters.access_control import (
        ROLE_POLICY_BY_ROLE,
        PrincipalRole,
        ViewerContext,
    )
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.adapters.redaction import (
        public_decision_request_payload,
        public_event_record_payload,
    )

    lifecycle, _, initial = replacement_scene()
    session = LocalGameSession(lifecycle=lifecycle)
    status = session.submit_option(
        request_id=initial.request_id,
        option_id=initial.options[0].option_id,
        result_id="order42:resolution",
    )
    request = status.decision_request
    assert request is not None
    viewer = (
        ViewerContext.for_player(player)
        if player is not None
        else ViewerContext(
            principal_id="spectator",
            role=PrincipalRole.DELAYED_SPECTATOR,
            viewer_player_id=None,
            policy=ROLE_POLICY_BY_ROLE[PrincipalRole.DELAYED_SPECTATOR],
        )
    )
    projected = public_decision_request_payload(request=request, viewer=viewer)
    assert "target_replacement_authority_sha256" not in json.dumps(projected)
    assert projected["decision_type"] == "select_target_replacement"
    assert "target_replacement_authority_sha256" not in json.dumps(
        session.view_for_context(viewer=viewer)
    )
    session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="order42:replacement",
    )
    events = [
        public_event_record_payload(
            event_id=e.event_id, event_type=e.event_type, payload=e.payload, viewer=viewer
        )
        for e in lifecycle.decision_controller.event_log.records
    ]
    serialized = json.dumps(events)
    assert "target_replacement_authority_sha256" not in serialized
    assert "target_replacement_resolved" in serialized


def test_reviewed_replacement_source_is_pinned_and_executable() -> None:
    from importlib.resources import files

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_target_replacement_2026_09 as source,
    )

    raw = files(source).joinpath("artifacts/package.json").read_bytes()
    artifact = source.validate_source_artifact_bytes(raw)
    assert artifact.rules[0].source_id == source.TARGET_REPLACEMENT_SOURCE_ID
    assert artifact.rules[0].section_id == "04.03.03"
    assert source.source_package().source_catalog.catalog_sha256()
    with pytest.raises(source.TargetReplacementSourceError, match="drifted"):
        source.validate_source_artifact_bytes(raw + b" ")


def test_firing_deck_replacement_keeps_the_embarked_weapon_and_spent_selection() -> None:
    from tests.core_stratagem_helpers import _replace_unit_poses
    from tests.phase13b_shooting_declaration_helpers import (
        _decision_request,
        _proposal_from_request,
        _select_shooting_unit_and_type,
        _shooting_lifecycle,
        _submit_payload,
    )

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.core.weapon_profiles import WeaponKeyword
    from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
    from warhammer40k_core.engine.ranged_weapon_keyword_effects import (
        ranged_weapon_keyword_grant_payload,
    )
    from warhammer40k_core.geometry.pose import Pose

    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("passenger", "transport-1"),
        alpha_datasheets={
            "passenger": ("core-intercessor-like-infantry", "core-intercessor-like", 5),
            "transport-1": ("core-transport", "core-transport", 1),
        },
        embarked_unit_ids=("passenger",),
        enemy_unit_specs=(
            ("old", "core-intercessor-like-infantry", "core-intercessor-like", 5),
            ("new", "core-intercessor-like-infantry", "core-intercessor-like", 5),
        ),
    )
    state = lifecycle.state
    assert state is not None
    state.record_persisting_effect(
        PersistingEffect(
            effect_id="order42:cargo-ignores-cover",
            source_rule_id="test:order42:cargo-ignores-cover",
            owner_player_id="player-a",
            target_unit_instance_ids=(units["passenger"].unit_instance_id,),
            started_battle_round=state.battle_round,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round, player_id="player-a"
            ),
            effect_payload=ranged_weapon_keyword_grant_payload(
                granted_keywords=(WeaponKeyword.IGNORES_COVER,),
                source_movement_request_id="order42:cargo-move",
                source_movement_result_id="order42:cargo-moved",
            ),
        )
    )
    _replace_unit_poses(
        state,
        unit_instance_id=units["new"].unit_instance_id,
        poses=tuple(Pose.at(18 + i, 25) for i in range(5)),
    )
    request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=_decision_request(lifecycle.advance_until_decision_or_terminal()),
        unit_instance_id=units["transport-1"].unit_instance_id,
        selection_result_id="deck:select",
    )
    proposal = _proposal_from_request(
        request=request,
        target_unit_id=units["old"].unit_instance_id,
        firing_deck_unit=units["passenger"],
    )
    proposal = replace(
        proposal,
        declarations=tuple(
            declaration
            if declaration.uses_firing_deck
            else replace(declaration, target_unit_instance_id=units["new"].unit_instance_id)
            for declaration in proposal.declarations
        ),
    )
    initial = _decision_request(
        _submit_payload(
            lifecycle, request=request, payload=proposal.to_payload(), result_id="deck:declaration"
        )
    )
    _replace_unit_poses(
        state,
        unit_instance_id=units["old"].unit_instance_id,
        poses=tuple(Pose.at(90 + i, 90) for i in range(5)),
    )
    session = LocalGameSession(lifecycle=lifecycle)
    request = _decision_request(
        session.submit_option(
            request_id=initial.request_id,
            option_id=initial.options[0].option_id,
            result_id="deck:resolve",
        )
    )
    assert request.decision_type == "select_target_replacement"
    assert state.shooting_phase_state is not None
    used_units = state.shooting_phase_state.shot_unit_ids
    session.submit_option(
        request_id=request.request_id,
        option_id=f"target:{units['new'].unit_instance_id}",
        result_id="deck:replacement",
    )
    assert state.shooting_phase_state is not None
    assert state.shooting_phase_state.shot_unit_ids == used_units
    resolved = next(
        e
        for e in lifecycle.decision_controller.event_log.records
        if e.event_type == "target_replacement_resolved"
    )
    assert isinstance(resolved.payload, dict)
    pools = resolved.payload["attack_pools"]
    assert isinstance(pools, list)
    borrowed = [
        p
        for p in pools
        if isinstance(p, dict) and p["firing_deck_source_unit_instance_id"] is not None
    ]
    assert len(borrowed) == 1
    assert borrowed[0]["firing_deck_source_unit_instance_id"] == units["passenger"].unit_instance_id
    assert borrowed[0]["target_unit_instance_id"] == units["new"].unit_instance_id
    borrowed_profile = borrowed[0]["weapon_profile"]
    assert isinstance(borrowed_profile, dict)
    borrowed_keywords = borrowed_profile["keywords"]
    assert isinstance(borrowed_keywords, list)
    assert WeaponKeyword.IGNORES_COVER.value not in borrowed_keywords
    original = next(d for d in proposal.declarations if d.uses_firing_deck)
    assert borrowed[0]["weapon_instance_id"] == original.weapon_instance_id
    assert (
        borrowed[0]["firing_deck_source_model_instance_id"]
        == original.firing_deck_source_model_instance_id
    )


def test_already_gathered_attacks_are_not_retargeted() -> None:
    from tests.target_replacement_helpers import replacement_scene

    from warhammer40k_core.engine.attack_sequence import gathered_attack_groups_for_target
    from warhammer40k_core.engine.phases.shooting_handler import ShootingPhaseHandler
    from warhammer40k_core.engine.shooting_target_replacement import (
        active_shooting_sequence,
        next_shooting_target_replacement,
    )

    lifecycle, units, _ = replacement_scene()
    state = lifecycle.state
    assert state is not None
    sequence = active_shooting_sequence(state).with_selected_target_unit(
        units["old"].unit_instance_id
    )
    group = gathered_attack_groups_for_target(
        attack_sequence=sequence, target_unit_instance_id=units["old"].unit_instance_id
    )[0]
    gathered = sequence.with_current_gathered_group(group)
    assert (
        next_shooting_target_replacement(
            state=state,
            decisions=lifecycle.decision_controller,
            handler=ShootingPhaseHandler(
                ruleset_descriptor=lifecycle.config.ruleset_descriptor,
                army_catalog=lifecycle.config.army_catalog,
            ),
            sequence=gathered,
        )
        is None
    )


def test_malformed_finite_replacement_payload_does_not_pop_or_mutate() -> None:
    from tests.target_replacement_helpers import replacement_scene

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    lifecycle, units, initial = replacement_scene()
    session = LocalGameSession(lifecycle=lifecycle)
    status = session.submit_option(
        request_id=initial.request_id,
        option_id=initial.options[0].option_id,
        result_id="order42:resolution",
    )
    request = status.decision_request
    assert request is not None
    snapshot = lifecycle.to_payload()
    malformed = DecisionResult(
        result_id="order42:forged",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=f"target:{units['new'].unit_instance_id}",
        payload={"target_ids": []},
    )
    status = lifecycle.submit_decision(malformed)
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert lifecycle.to_payload() == snapshot


def test_target_query_cache_preserves_cold_results_and_invalidates_changed_inputs() -> None:
    from tests.core_stratagem_helpers import _replace_unit_poses
    from tests.target_replacement_helpers import replacement_scene

    from warhammer40k_core.core.weapon_profiles import RangeProfile, WeaponProfile
    from warhammer40k_core.engine.phases.shooting_validation import _battlefield_scenario
    from warhammer40k_core.engine.shooting_target_cache import (
        cached_target_candidate_for_model,
        clear_target_candidate_cache,
    )
    from warhammer40k_core.engine.shooting_target_replacement import active_shooting_sequence
    from warhammer40k_core.engine.shooting_targets import ShootingTargetCandidate
    from warhammer40k_core.geometry.pose import Pose

    lifecycle, units, _ = replacement_scene(moved=False)
    state = lifecycle.state
    assert state is not None
    pool = active_shooting_sequence(state).attack_pools[0]
    _replace_unit_poses(
        state,
        unit_instance_id=units["old"].unit_instance_id,
        poses=tuple(Pose.at(30 + i, 35) for i in range(5)),
    )

    def query(
        profile: WeaponProfile = pool.weapon_profile,
        hidden: tuple[str, ...] = (),
    ) -> ShootingTargetCandidate:
        return cached_target_candidate_for_model(
            scenario=_battlefield_scenario(state),
            ruleset_descriptor=lifecycle.config.ruleset_descriptor,
            attacker_unit=units["source"],
            attacker_model_instance_id=pool.attacker_model_instance_id,
            weapon_profile=profile,
            target_unit_id=units["old"].unit_instance_id,
            terrain_features=(),
            terrain_areas=(),
            hidden_target_model_ids=hidden,
            target_unit_ids_with_recent_ranged_attacks=(),
            target_detection_range_bonus_inches=0,
        )

    clear_target_candidate_cache()
    cold = query()
    assert cold.is_legal
    assert query() is cold
    clear_target_candidate_cache()
    assert query() == cold
    assert not query(replace(pool.weapon_profile, range_profile=RangeProfile.distance(1))).is_legal
    assert query().is_legal
    assert not query(hidden=units["old"].own_model_ids()).is_legal
    assert query().is_legal
    _replace_unit_poses(
        state,
        unit_instance_id=units["old"].unit_instance_id,
        poses=tuple(Pose.at(90 + i, 90) for i in range(5)),
    )
    assert not query().is_legal
    clear_target_candidate_cache()


def test_target_query_cache_handles_casualties_retention_restore_and_independent_games() -> None:
    from tests.target_replacement_helpers import replacement_scene

    from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.phases.shooting_validation import _battlefield_scenario
    from warhammer40k_core.engine.shooting_target_cache import (
        cached_target_candidate_for_model,
        clear_target_candidate_cache,
    )
    from warhammer40k_core.engine.shooting_target_replacement import active_shooting_sequence
    from warhammer40k_core.engine.shooting_targets import (
        ShootingTargetCandidate,
        shooting_target_candidate_for_model,
    )
    from warhammer40k_core.engine.unit_factory import UnitInstance

    lifecycle, units, _ = replacement_scene(moved=False)
    state = lifecycle.state
    assert state is not None
    pool = active_shooting_sequence(state).attack_pools[0]
    original = _battlefield_scenario(state)
    dead_unit = replace(
        units["source"],
        own_models=tuple(
            replace(model, wounds_remaining=0)
            if model.model_instance_id == pool.attacker_model_instance_id
            else model
            for model in units["source"].own_models
        ),
    )
    casualty = replace(
        original,
        armies=tuple(
            replace(
                army,
                units=tuple(
                    dead_unit if unit.unit_instance_id == dead_unit.unit_instance_id else unit
                    for unit in army.units
                ),
            )
            for army in original.armies
        ),
    )
    retained = replace(casualty, present_destroyed_model_ids=(pool.attacker_model_instance_id,))
    cleaned = replace(
        casualty,
        battlefield_state=casualty.battlefield_state.with_removed_models(
            (pool.attacker_model_instance_id,)
        ),
    )
    other_lifecycle, _, _ = replacement_scene(moved=True)
    other_state = other_lifecycle.state
    assert other_state is not None

    def query(
        scenario: BattlefieldScenario, attacker: UnitInstance, *, cached: bool
    ) -> ShootingTargetCandidate:
        candidate_for = (
            cached_target_candidate_for_model if cached else shooting_target_candidate_for_model
        )
        return candidate_for(
            scenario=scenario,
            ruleset_descriptor=lifecycle.config.ruleset_descriptor,
            attacker_unit=attacker,
            attacker_model_instance_id=pool.attacker_model_instance_id,
            weapon_profile=pool.weapon_profile,
            target_unit_id=units["old"].unit_instance_id,
            terrain_features=(),
            terrain_areas=(),
            hidden_target_model_ids=(),
            target_unit_ids_with_recent_ranged_attacks=(),
            target_detection_range_bonus_inches=0,
        )

    clear_target_candidate_cache()
    for scenario, attacker, legal in (
        (original, units["source"], True),
        (casualty, dead_unit, None),
        (retained, dead_unit, True),
        (cleaned, dead_unit, None),
        (BattlefieldScenario.from_payload(retained.to_payload()), dead_unit, True),
        (_battlefield_scenario(other_state), units["source"], False),
        (original, units["source"], True),
    ):
        if legal is None:
            for cached in (False, True):
                with pytest.raises(GameLifecycleError, match="attacker model is not placed"):
                    query(scenario, attacker, cached=cached)
            continue
        cold = query(scenario, attacker, cached=False)
        assert cold.is_legal is legal
        assert query(scenario, attacker, cached=True) == cold
        assert query(scenario, attacker, cached=True) == cold
    clear_target_candidate_cache()
