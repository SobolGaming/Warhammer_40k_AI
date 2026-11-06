"""Native transport choices, accepted/rejected proposals and viewer evidence."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from tests.psychic_modifier_helpers import pending_request
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section09_fixtures import begin, events, propose
from tests.support.section18_fixtures import transport_scene
from warhammer40k_core.engine.assault_disembark import assault_disembark_permission_effect
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.effects import EffectExpiration
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.rules_units import rules_unit_is_battle_shocked
from warhammer40k_core.engine.shock_disembark import shock_disembark_permission_effect
from warhammer40k_core.engine.transports import DisembarkModeKind, TransportMovementStatus
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize(
    "mode",
    [
        DisembarkModeKind.TACTICAL_DISEMBARK,
        DisembarkModeKind.RAPID_DISEMBARK,
        DisembarkModeKind.ASSAULT_DISEMBARK,
        DisembarkModeKind.SHOCK_DISEMBARK,
    ],
)
def test_native_facade_disembark_mode_and_aftermath_are_engine_owned_and_json_safe(
    section18_definitions: Section02Definitions,
    mode: DisembarkModeKind,
) -> None:
    s = transport_scene(section18_definitions)
    session = s.session
    if mode in {DisembarkModeKind.ASSAULT_DISEMBARK, DisembarkModeKind.SHOCK_DISEMBARK}:
        factory = (
            assault_disembark_permission_effect
            if mode is DisembarkModeKind.ASSAULT_DISEMBARK
            else shock_disembark_permission_effect
        )
        # Explicit Core grant, not a named native datasheet ability provider.
        s.state.record_persisting_effect(
            factory(
                effect_id="constructed:s18:permission",
                source_rule_id="constructed:s18:grant",
                owner_player_id="owner",
                transport_unit_instance_id=s.transport.unit_instance_id,
                eligible_rules_unit_instance_ids=(s.passenger.unit_instance_id,),
                started_battle_round=1,
                started_phase=BattlePhase.MOVEMENT,
                expiration=EffectExpiration.end_turn(battle_round=1, player_id="owner"),
            )
        )
    request = begin(session)
    if mode is DisembarkModeKind.RAPID_DISEMBARK:
        status = session.submit_option(
            request_id=request.request_id,
            result_id="carrier",
            option_id=s.transport.unit_instance_id,
        )
        assert status.decision_request is not None
        status = session.submit_option(
            request_id=status.decision_request.request_id,
            result_id="normal",
            option_id="normal_move",
        )
        assert status.decision_request is not None
        status = propose(
            session,
            status.decision_request,
            s.transport,
            (Pose.at(20, 20.1),),
            result_id="carrier-path",
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
        assert status.decision_request is not None
        request = status.decision_request
    status = session.submit_option(
        request_id=request.request_id, result_id="passenger", option_id=s.passenger.unit_instance_id
    )
    assert status.decision_request is not None
    action = (
        "disembark"
        if mode in {DisembarkModeKind.TACTICAL_DISEMBARK, DisembarkModeKind.RAPID_DISEMBARK}
        else f"disembark:{mode.value}"
    )
    status = session.submit_option(
        request_id=status.decision_request.request_id, result_id="mode", option_id=action
    )
    assert status.decision_request is not None
    request = status.decision_request
    assert request.decision_type == "submit_placement_proposal"
    context = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert context.context is not None
    assert context.context["disembark_mode"] == mode.value
    selection = s.selection(
        mode,
        TransportMovementStatus.NORMAL_MOVE
        if mode is DisembarkModeKind.RAPID_DISEMBARK
        else TransportMovementStatus.NOT_MOVED,
    )
    raw_overrides = context.context.get("restriction_overrides", [])
    from typing import cast

    from warhammer40k_core.engine.transports import (
        TransportRestrictionOverride,
        TransportRestrictionOverridePayload,
    )

    assert isinstance(raw_overrides, list)
    overrides = tuple(
        TransportRestrictionOverride.from_payload(cast(TransportRestrictionOverridePayload, x))
        for x in raw_overrides
    )
    payload = PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.DISEMBARK,
        unit_instance_id=s.passenger.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_placement=selection.attempted_placement,
        transport_unit_instance_id=s.transport.unit_instance_id,
        disembark_mode=mode,
        transport_movement_status=selection.transport_movement_status,
        restriction_overrides=overrides,
        start_engaged_enemy_unit_instance_ids=()
        if mode is DisembarkModeKind.SHOCK_DISEMBARK
        else None,
    )
    # Malformed input is rejected before recording/popping the live proposal.
    before_state = s.state.to_payload()
    before_decisions = session.lifecycle.decision_controller.to_payload()
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="malformed",
        payload={"proposal_request_id": request.request_id},
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert s.state.to_payload() == before_state
    assert session.lifecycle.decision_controller.to_payload() == before_decisions
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="placed",
        payload=validate_json_value(payload.to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert not s.cargo.embarked_unit_instance_ids
    result = s.state.disembarked_unit_state_for_unit(
        player_id="owner", battle_round=1, unit_instance_id=s.passenger.unit_instance_id
    )
    assert result is not None
    assert result.disembark_mode is mode
    assert result.can_move_further is (mode is DisembarkModeKind.TACTICAL_DISEMBARK)
    assert result.can_declare_charge is (
        mode in {DisembarkModeKind.TACTICAL_DISEMBARK, DisembarkModeKind.ASSAULT_DISEMBARK}
    )
    assert not result.battle_shocked_until
    assert not rules_unit_is_battle_shocked(
        state=s.state, unit_instance_id=s.passenger.unit_instance_id
    )
    assert events(session, "unit_disembarked")[-1]["disembarked_unit_state"] == result.to_payload()
    assert s.cargo.unit_disembarked_this_phase(s.passenger.unit_instance_id)
    history = [
        r
        for r in s.state.phase_movement_history
        if r.unit_instance_id == s.passenger.unit_instance_id
        and r.setup_kind is BattlefieldPlacementKind.DISEMBARK
    ]
    assert history
    assert history[-1].model_instance_ids == s.passenger.own_model_ids()
    for viewer in ("owner", "opponent"):
        view = session.view(viewer_player_id=viewer)
        assert view["pending_decision"] is not None
        assert view["pending_decision"]["actor_id"] == "owner"
        assert json.loads(json.dumps(view)) == view
    records = session.lifecycle.decision_controller.to_payload()
    assert "0x" not in json.dumps(records)
    assert json.loads(json.dumps(records)) == records


def test_native_normal_move_offers_and_commits_embark_after_actual_witness(
    section18_definitions: Section02Definitions,
) -> None:
    s = transport_scene(section18_definitions, embarked=False, passenger_poses=(Pose.at(23, 20),))
    request = begin(s.session)
    status = s.session.submit_option(
        request_id=request.request_id, result_id="passenger", option_id=s.passenger.unit_instance_id
    )
    assert status.decision_request is not None
    status = s.session.submit_option(
        request_id=status.decision_request.request_id, result_id="normal", option_id="normal_move"
    )
    assert status.decision_request is not None
    status = propose(
        s.session, status.decision_request, s.passenger, (Pose.at(23.1, 20),), result_id="path"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert status.decision_request is not None
    request = status.decision_request
    assert request.decision_type == "select_embark_transport"
    assert s.transport.unit_instance_id in {o.option_id for o in request.options}
    status = s.session.submit_option(
        request_id=request.request_id, result_id="embark", option_id=s.transport.unit_instance_id
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert s.cargo.embarked_unit_instance_ids == (s.passenger.unit_instance_id,)
    assert s.state.battlefield_state is not None
    assert s.state.battlefield_state.unit_placement_or_none(s.passenger.unit_instance_id) is None
    assert events(s.session, "unit_embarked")


def test_native_failed_disembark_keeps_cargo_and_allows_a_fresh_legal_retry(
    section18_definitions: Section02Definitions,
) -> None:
    s = transport_scene(section18_definitions)
    request = begin(s.session)
    before_board = s.state.battlefield_state
    before_cargo = s.cargo
    for attempt, valid in (("outside", False), ("retry", True)):
        status = s.session.submit_option(
            request_id=request.request_id,
            result_id=f"{attempt}:passenger",
            option_id=s.passenger.unit_instance_id,
        )
        assert status.decision_request is not None
        status = s.session.submit_option(
            request_id=status.decision_request.request_id,
            result_id=f"{attempt}:mode",
            option_id="disembark",
        )
        assert status.decision_request is not None
        request = status.decision_request
        payload = PlacementProposalPayload(
            proposal_request_id=request.request_id,
            proposal_kind=ProposalKind.DISEMBARK,
            unit_instance_id=s.passenger.unit_instance_id,
            placement_kind=BattlefieldPlacementKind.DISEMBARK,
            attempted_placement=s.selection(
                poses=(Pose.at(23 if valid else 30, 20),)
            ).attempted_placement,
            transport_unit_instance_id=s.transport.unit_instance_id,
            disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        )
        before = s.session.lifecycle.to_payload()
        stale = s.session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"{attempt}:stale",
            payload=validate_json_value(
                replace(payload, proposal_request_id="constructed:s18:stale").to_payload()
            ),
        )
        assert stale.status_kind is LifecycleStatusKind.INVALID
        assert s.session.lifecycle.to_payload() == before
        status = s.session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=attempt,
            payload=validate_json_value(payload.to_payload()),
        )
        assert (status.status_kind is not LifecycleStatusKind.INVALID) is valid
        if not valid:
            assert s.state.battlefield_state == before_board
            assert s.cargo == before_cargo
            assert not events(s.session, "unit_disembarked")
            request = pending_request(s.session)
            assert request.decision_type == "select_movement_unit"
        else:
            assert not s.cargo.embarked_unit_instance_ids
            assert len(events(s.session, "unit_disembarked")) == 1


def test_a32_original_transport_hazards_pending_retry_restore_fork_and_exact_replay() -> None:
    from tests.support.a32_transport import CARRIER, PASSENGER, emergency_payload, pending_emergency
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.damage_allocation import unit_by_id
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

    session = pending_emergency()
    state = session.lifecycle.state
    assert state is not None
    assert not unit_by_id(state=state, unit_instance_id=CARRIER).own_models[0].is_alive
    assert unit_by_id(state=state, unit_instance_id=PASSENGER).own_models[0].wounds_remaining == 4
    before = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(before)
    forked = session.fork()
    assert restored.to_persistence_payload() == forked.to_persistence_payload() == before
    request = pending_request(session)
    assert request.actor_id == "player-a"
    malformed = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="a32:malformed", payload={"bad": True}
    )
    assert malformed.status_kind is LifecycleStatusKind.INVALID
    assert session.to_persistence_payload() == before
    payload = emergency_payload(session, request, far=True)
    state_before = state.to_payload()
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="a32:too-far", payload=payload
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    # Rule-invalid proposals are recorded and issue a new request; wounds, cargo,
    # battlefield and survivor status stay unchanged for legal retry.
    assert state.to_payload()["army_definitions"] == state_before["army_definitions"]
    assert state.to_payload()["battlefield_state"] == state_before["battlefield_state"]
    assert state.to_payload()["transport_cargo_states"] == state_before["transport_cargo_states"]
    assert not rules_unit_is_battle_shocked(state=state, unit_instance_id=PASSENGER)
    assert restored.to_persistence_payload() == before
    request = pending_request(session)
    accepted = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="a32:legal",
        payload=emergency_payload(session, request),
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted.to_payload()
    assert rules_unit_is_battle_shocked(state=state, unit_instance_id=PASSENGER)
    completed = json.loads(json.dumps(session.to_persistence_payload()))
    assert (
        LocalGameSession.from_persistence_payload(completed).to_persistence_payload() == completed
    )
    for branch in (restored, forked):
        branch_request = pending_request(branch)
        rejected = branch.submit_parameterized_payload(
            request_id=branch_request.request_id,
            result_id="a32:too-far",
            payload=emergency_payload(branch, branch_request, far=True),
        )
        assert rejected.status_kind is LifecycleStatusKind.INVALID
        retry = pending_request(branch)
        accepted_branch = branch.submit_parameterized_payload(
            request_id=retry.request_id,
            result_id="a32:legal",
            payload=emergency_payload(branch, retry),
        )
        assert accepted_branch.status_kind is not LifecycleStatusKind.INVALID
        assert branch.to_persistence_payload() == completed
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="a32:exact")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay.to_payload()


def test_a32_starting_cargo_authority_requires_exact_manifest_and_initial_wounds() -> None:
    from copy import deepcopy

    from tests.support.a32_transport import PASSENGER, pending_emergency
    from warhammer40k_core.engine.event_log import EventRecord
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.starting_transport_physical_authority import (
        starting_transport_physical_authority,
    )

    session = pending_emergency()
    state = session.lifecycle.state
    assert state is not None
    records = tuple(session.lifecycle.decision_controller.event_log.records)
    rows = starting_transport_physical_authority(state=state, event_records=records)
    model = next(
        u for a in state.army_definitions for u in a.units if u.unit_instance_id == PASSENGER
    ).own_models[0]
    assert rows[model.model_instance_id].presence == "embarked"
    assert rows[model.model_instance_id].wounds_remaining == 5
    manifest = next(
        e for e in records if e.event_type == "battle_formation_transport_manifest_recorded"
    )
    payload = deepcopy(manifest.payload)
    assert isinstance(payload, dict)
    payload["player_id"] = "player-b"
    changed = EventRecord(
        event_id=manifest.event_id, event_type=manifest.event_type, payload=payload
    )
    with pytest.raises(GameLifecycleError, match="manifest drift"):
        starting_transport_physical_authority(
            state=state, event_records=tuple(changed if e is manifest else e for e in records)
        )
    with pytest.raises(GameLifecycleError, match="manifest drift"):
        starting_transport_physical_authority(state=state, event_records=(*records, manifest))


def test_a32_original_hazard_destroys_all_cargo_without_emergency_or_shock() -> None:
    from tests.support.a32_transport import CARRIER, PASSENGER, pending_emergency
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.damage_allocation import unit_by_id
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

    session = pending_emergency(destroyed_cargo=True)
    state = session.lifecycle.state
    assert state is not None
    assert not unit_by_id(state=state, unit_instance_id=CARRIER).own_models[0].is_alive
    assert not unit_by_id(state=state, unit_instance_id=PASSENGER).own_models[0].is_alive
    assert not state.transport_cargo_states
    assert not rules_unit_is_battle_shocked(state=state, unit_instance_id=PASSENGER)
    assert not any(
        e.event_type == "unit_disembarked"
        for e in session.lifecycle.decision_controller.event_log.records
    )
    payload = json.loads(json.dumps(session.to_persistence_payload()))
    assert LocalGameSession.from_persistence_payload(payload).to_persistence_payload() == payload
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="a32:all-dead")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay.to_payload()


def test_a32_oct14_explicit_recovery_restores_continues_forks_and_replays() -> None:
    import hashlib

    from tests.support.a32_recovery import historical_checkpoint_bytes, recovered_payload
    from tests.support.a32_transport import PASSENGER, emergency_payload
    from warhammer40k_core.adapters.checkpoint_reconstruction import (
        verify_checkpoint_reconstruction,
    )
    from warhammer40k_core.adapters.local_session import (
        LocalGameSession,
        LocalGameSessionPersistenceError,
    )
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

    raw = historical_checkpoint_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "55f23684cedb354050605bb796928bea5971acb73d975ffe54ce230ae2db9370"
    )
    with pytest.raises(LocalGameSessionPersistenceError):
        LocalGameSession.from_persistence_payload(json.loads(raw))
    recovered = recovered_payload()
    session = verify_checkpoint_reconstruction(raw, recovered)
    before = session.to_persistence_payload()
    branches = (session, session.fork(), LocalGameSession.from_persistence_payload(before))
    completed: list[object] = []
    for branch in branches:
        assert branch.to_persistence_payload() == before
        request = pending_request(branch)
        assert request.actor_id == "player-a"
        result = branch.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="a32:recovered:place",
            payload=emergency_payload(branch, request),
        )
        assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
        state = branch.lifecycle.state
        assert state is not None
        assert rules_unit_is_battle_shocked(state=state, unit_instance_id=PASSENGER)
        done = branch.to_persistence_payload()
        assert LocalGameSession.from_persistence_payload(done).to_persistence_payload() == done
        replay = ReplayRunner.from_payload(
            branch.replay_artifact(artifact_id="a32:recovered:completed")
        ).run()
        assert replay.status is ReplayRunStatus.REPRODUCED, replay.to_payload()
        completed.append(done)
    assert completed[0] == completed[1] == completed[2]
    assert historical_checkpoint_bytes() == raw


def test_a32_oct14_reconstruction_is_deterministic_and_keeps_original_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hashlib

    from tests.support.a32_recovery import historical_checkpoint_bytes, recovered_payload
    from warhammer40k_core.adapters.checkpoint_reconstruction import (
        PROFILE_ID,
        reconstruct_local_checkpoint,
    )
    from warhammer40k_core.engine.event_log import canonical_json
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.setup_completion import SetupReplayCheckpoint

    raw = historical_checkpoint_bytes()
    first = recovered_payload()
    original = json.loads(raw)
    old_start = original["lifecycle"]["decisions"]["event_log"][38]["payload"]
    original_capture = SetupReplayCheckpoint.from_state
    observed: set[str] = set()

    def observe_checkpoint(*, state: GameState, checkpoint_kind: str) -> SetupReplayCheckpoint:
        # Passive observation: the real engine result is returned unchanged.
        checkpoint = original_capture(state=state, checkpoint_kind=checkpoint_kind)
        payload = validate_json_value(state.to_payload())
        assert isinstance(payload, dict)
        assert hashlib.sha256(canonical_json(payload).encode()).hexdigest() == checkpoint.state_hash
        assert (
            payload.pop("private_rng_seed")
            == hashlib.sha256(b"a32-exact-artifact-reconstruction-v3:3223").hexdigest()
        )
        assert payload.pop("tactical_secondary_draw_sequence") == 0
        field = (
            "pre_battle_checkpoint"
            if checkpoint_kind == "pre_battle_start"
            else "post_battle_start_checkpoint"
        )
        assert (
            hashlib.sha256(canonical_json(payload).encode()).hexdigest()
            == old_start[field]["state_hash"]
        )
        observed.add(checkpoint_kind)
        return checkpoint

    monkeypatch.setattr(SetupReplayCheckpoint, "from_state", observe_checkpoint)
    second = reconstruct_local_checkpoint(raw, profile_id=PROFILE_ID)
    assert observed == {"pre_battle_start", "post_battle_start"}
    assert canonical_json(first) == canonical_json(second)
    assert isinstance(second, dict)
    checkpoint = second["checkpoint"]
    assert isinstance(checkpoint, dict)
    rng = checkpoint["rng_state"]
    assert isinstance(rng, dict)
    assert rng["history"] == original["rng_state"]["history"]
    assert rng["draw_count"] == original["rng_state"]["draw_count"] == 5
    assert rng["seed"] != original["rng_state"]["seed"]
    assert rng["seed"] == hashlib.sha256(b"a32-exact-artifact-reconstruction-v3:3223").hexdigest()
    lifecycle = checkpoint["lifecycle"]
    assert isinstance(lifecycle, dict)
    config = lifecycle["config"]
    assert isinstance(config, dict)
    state = lifecycle["state"]
    assert isinstance(state, dict)
    assert config["private_rng_seed"] == state["private_rng_seed"] == rng["seed"]
    assert state["tactical_secondary_draw_sequence"] == 0
    decisions = lifecycle["decisions"]
    assert isinstance(decisions, dict)
    events = decisions["event_log"]
    assert isinstance(events, list)
    assert [
        event["payload"]["values"]
        for event in events
        if isinstance(event, dict)
        and event["event_type"] == "dice_rolled"
        and isinstance(event["payload"], dict)
    ] == [[4], [4], [2], [1], [2]]
    assert checkpoint["source_identity"] == {
        **original["source_identity"],
        "game_config_hash": hashlib.sha256(canonical_json(config).encode()).hexdigest(),
        "mission_source_package_hash": (
            "8f76fcf275397bd2ffabf16d3e127f059fb476e0144654bd54e550f5dd16faa1"
        ),
    }
    provenance = second["provenance"]
    assert isinstance(provenance, dict)
    assert provenance["original_event_count"] == 137
    assert provenance["reconstructed_event_count"] == 138
    assert provenance["decision_count"] == 18
    assert provenance["original_byte_replay_claimed"] is False
    assert provenance["recipe_version"] == "recorded-decision-reconstruction-v3-audit-rng"
    assert provenance["original_decisions_and_gameplay_outcomes_preserved"] is True
    assert provenance["original_rng_metadata_preserved"] is False
    assert provenance["secret_competitive_rng_suitable"] is False
    rng_mapping = provenance["rng_metadata_mapping"]
    assert isinstance(rng_mapping, dict)
    assert rng_mapping["original_seed"] == original["rng_state"]["seed"]
    assert rng_mapping["reconstructed_seed"] == rng["seed"]
    assert rng_mapping["preserved_dice_faces"] == [4, 4, 2, 1, 2]
    assert rng_mapping["tactical_secondary_draw_sequence"] == 0
    hash_mappings = provenance["setup_checkpoint_state_hash_mappings"]
    assert isinstance(hash_mappings, list)
    assert len(hash_mappings) == 3
    mapping = provenance["mission_source_identity_mapping"]
    assert isinstance(mapping, dict)
    assert mapping["original"] == original["source_identity"]["mission_source_package_hash"]
    reconstructed_identity = checkpoint["source_identity"]
    assert isinstance(reconstructed_identity, dict)
    assert mapping["reconstructed"] == reconstructed_identity["mission_source_package_hash"]
    assert mapping["added_scoring_value"] == "player_turn"
    assert second["schema_version"] == "local-checkpoint-reconstruction-v3-audit-rng"


@pytest.mark.parametrize(
    "change",
    [
        "missing_completion",
        "changed_state",
        "changed_legacy_event",
        "changed_provenance",
        "unknown_field",
        "missing_checkpoint_field",
        "json_type_alias",
        "changed_mission_pack",
        "changed_mission_hash",
        "changed_other_source_identity",
        "changed_identity_mapping",
        "old_reconstruction_schema",
        "changed_rng_seed",
        "changed_rng_history",
        "changed_rng_draw_count",
        "changed_draw_sequence",
        "missing_history_seed",
        "changed_rng_mapping",
        "changed_setup_checkpoint_hash",
    ],
)
def test_a32_oct14_recovery_rejects_inconsistent_reconstructions(change: str) -> None:
    import hashlib

    from tests.support.a32_recovery import historical_checkpoint_bytes, recovered_payload
    from warhammer40k_core.adapters.checkpoint_reconstruction import (
        CheckpointReconstructionError,
        verify_checkpoint_reconstruction,
    )
    from warhammer40k_core.engine.event_log import canonical_json

    package = recovered_payload()
    assert isinstance(package, dict)
    checkpoint = package["checkpoint"]
    assert isinstance(checkpoint, dict)
    lifecycle = checkpoint["lifecycle"]
    assert isinstance(lifecycle, dict)
    decisions = lifecycle["decisions"]
    assert isinstance(decisions, dict)
    events = decisions["event_log"]
    assert isinstance(events, list)
    if change == "missing_completion":
        decisions["event_log"] = [
            e
            for e in events
            if isinstance(e, dict)
            and e["event_type"] != "attack_sequence_model_completion_state_recorded"
        ]
    elif change == "changed_legacy_event":
        event = events[-1]
        assert isinstance(event, dict)
        event["event_type"] = "unexplained_event"
    elif change == "changed_setup_checkpoint_hash":
        event = events[38]
        assert isinstance(event, dict)
        payload = event["payload"]
        assert isinstance(payload, dict)
        checkpoint_state = payload["pre_battle_checkpoint"]
        assert isinstance(checkpoint_state, dict)
        checkpoint_state["state_hash"] = "0" * 64
    elif change == "changed_state":
        state = lifecycle["state"]
        assert isinstance(state, dict)
        state["game_id"] = "another-game"
    elif change == "missing_checkpoint_field":
        del checkpoint["rng_state"]
    elif change == "json_type_alias":
        state = lifecycle["state"]
        assert isinstance(state, dict)
        state["battle_round"] = True
    elif change in {
        "changed_mission_pack",
        "changed_mission_hash",
        "changed_other_source_identity",
    }:
        identity = checkpoint["source_identity"]
        assert isinstance(identity, dict)
        field = {
            "changed_mission_pack": "mission_pack_id",
            "changed_mission_hash": "mission_source_package_hash",
            "changed_other_source_identity": "catalog_hash",
        }[change]
        identity[field] = "unregistered" if field == "mission_pack_id" else "0" * 64
    elif change == "old_reconstruction_schema":
        package["schema_version"] = "local-checkpoint-reconstruction-v2-mission-scope"
    elif change in {"changed_rng_seed", "changed_rng_history", "changed_rng_draw_count"}:
        rng = checkpoint["rng_state"]
        assert isinstance(rng, dict)
        if change == "changed_rng_seed":
            rng["seed"] = "0" * 64
        elif change == "changed_rng_history":
            rng["history"] = []
        else:
            rng["draw_count"] = 6
    elif change == "changed_draw_sequence":
        state = lifecycle["state"]
        assert isinstance(state, dict)
        state["tactical_secondary_draw_sequence"] = 1
    elif change == "missing_history_seed":
        origin = lifecycle["psychic_modifier_history_origin"]
        assert isinstance(origin, dict)
        state = origin["state"]
        assert isinstance(state, dict)
        del state["private_rng_seed"]
    elif change == "changed_rng_mapping":
        provenance = package["provenance"]
        assert isinstance(provenance, dict)
        rng_mapping = provenance["rng_metadata_mapping"]
        assert isinstance(rng_mapping, dict)
        rng_mapping["reconstructed_seed"] = "0" * 64
    elif change == "changed_identity_mapping":
        provenance = package["provenance"]
        assert isinstance(provenance, dict)
        mapping = provenance["mission_source_identity_mapping"]
        assert isinstance(mapping, dict)
        mapping["reconstructed"] = "0" * 64
    elif change == "changed_provenance":
        provenance = package["provenance"]
        assert isinstance(provenance, dict)
        provenance["original_byte_replay_claimed"] = True
    else:
        package["guessed_history"] = True
    package["content_hash"] = hashlib.sha256(
        canonical_json({k: v for k, v in package.items() if k != "content_hash"}).encode()
    ).hexdigest()
    with pytest.raises(CheckpointReconstructionError):
        verify_checkpoint_reconstruction(historical_checkpoint_bytes(), package)


def test_a32_oct14_recovery_rejects_different_or_underdetermined_source() -> None:
    from tests.support.a32_recovery import historical_checkpoint_bytes
    from warhammer40k_core.adapters.checkpoint_reconstruction import (
        PROFILE_ID,
        CheckpointReconstructionError,
        reconstruct_local_checkpoint,
    )

    raw = historical_checkpoint_bytes()
    for changed in (raw + b" ", b"{}", raw[:-1]):
        with pytest.raises(CheckpointReconstructionError, match="source"):
            reconstruct_local_checkpoint(changed, profile_id=PROFILE_ID)
    with pytest.raises(CheckpointReconstructionError, match="profile"):
        reconstruct_local_checkpoint(raw, profile_id="unknown")


@pytest.mark.parametrize("same_source", [False, True])
def test_a32_oct14_cli_never_overwrites_original_or_existing_output(
    tmp_path: Path, same_source: bool
) -> None:
    import subprocess
    import sys

    from tests.support.a32_recovery import historical_checkpoint_bytes
    from warhammer40k_core.adapters.checkpoint_reconstruction import PROFILE_ID

    source = tmp_path / "original.json"
    raw = historical_checkpoint_bytes()
    source.write_bytes(raw)
    output = source if same_source else tmp_path / "existing.json"
    if not same_source:
        output.write_bytes(b"KEEP")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.reconstruct_local_checkpoint",
            "--source",
            str(source),
            "--profile",
            PROFILE_ID,
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert source.read_bytes() == raw
    assert same_source or output.read_bytes() == b"KEEP"
