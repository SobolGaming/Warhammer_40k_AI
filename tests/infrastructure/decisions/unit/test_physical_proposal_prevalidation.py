from __future__ import annotations

import cProfile
from dataclasses import asdict, replace
from types import CodeType

from tests.shared.category_migration.physical_proposal_prevalidation import (
    FAMILIES,
    EventStreamCursor,
    JsonValue,
    LifecycleStatusKind,
    LocalGameSession,
    ReplayRunner,
    ReplayRunStatus,
    copy,
    json,
    proposal_session,
    pytest,
    submit_network_parameterized_payload,
)
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.redaction import (
    public_decision_request_payload,
    viewer_identity_map,
)
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.adapters.viewer_identity import ViewerIdentityMap
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyRoute, payload_digest
from warhammer40k_core.engine.event_log import canonical_json


def _projection_work(profile: cProfile.Profile) -> int:
    return sum(
        entry.callcount
        for entry in profile.getstats()
        if isinstance(entry.code, CodeType)
        and entry.code.co_name == "viewer_identity_map"
        and entry.code.co_filename.replace("\\", "/").endswith("/adapters/redaction.py")
    )


def _projection_session() -> tuple[LocalGameSession, ViewerContext]:
    session = LocalGameSession()
    session.start(canonical_setup_prebattle_smoke_config(game_id="projection-cache-authority"))
    status = session.advance_until_decision_or_terminal()
    assert status.decision_request is not None
    assert status.decision_request.actor_id is not None
    return session, ViewerContext.for_player(status.decision_request.actor_id)


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("change", ["empty", "kind", "unit", "request", "shape", "nested"])
def test_malformed_physical_proposal_is_typed_and_leaves_all_authority_unchanged(
    family: str,
    change: str,
) -> None:
    session, request, payload = proposal_session(family)
    assert request.actor_id is not None
    public_request = session.view(viewer_player_id=request.actor_id)["pending_decision"]
    assert public_request is not None
    payload = {**payload, "proposal_request_id": public_request["request_id"]}
    malformed: JsonValue = copy.deepcopy(payload)
    assert isinstance(malformed, dict)
    if change == "empty":
        malformed = {}
    elif change == "shape":
        malformed = []
    elif change == "nested":
        malformed["attempted_placement" if family == "placement" else "witness"] = {
            "model_paths": [None]
        }
    else:
        malformed[
            {"kind": "proposal_kind", "unit": "unit_instance_id", "request": "proposal_request_id"}[
                change
            ]
        ] = "not-the-pending-value"
    before = copy.deepcopy(session.lifecycle.to_payload())
    views = {viewer: session.view(viewer_player_id=viewer) for viewer in ("player-a", "player-b")}
    deltas = {
        viewer: session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        for viewer in views
    }
    outcome = submit_network_parameterized_payload(
        session,
        {
            "request_id": public_request["request_id"],
            "result_id": "order76-malformed",
            "payload": malformed,
        },
    )
    assert outcome.status_kind is LifecycleStatusKind.INVALID
    json.dumps(outcome.to_payload(), allow_nan=False)
    assert session.lifecycle.to_payload() == before
    assert session.lifecycle.pending_decision_request() == request
    for viewer in views:
        assert session.view(viewer_player_id=viewer) == views[viewer]
        assert session.events_since(EventStreamCursor(), viewer_player_id=viewer) == deltas[viewer]


@pytest.mark.parametrize("family", FAMILIES)
def test_rejected_physical_proposal_restores_and_replays_before_and_after_valid_retry(
    family: str,
) -> None:
    session, request, payload = proposal_session(family)
    malformed = {**payload, "proposal_kind": "not-a-kind"}
    outcome = session.submit_parameterized_payload(
        request_id=request.request_id, payload=malformed, result_id="order76-reject"
    )
    assert outcome.status_kind is LifecycleStatusKind.INVALID
    for stage in ("rejected", "retried"):
        if stage == "retried":
            outcome = session.submit_parameterized_payload(
                request_id=request.request_id, payload=payload, result_id="order76-retry"
            )
            assert outcome.status_kind is not LifecycleStatusKind.INVALID
        replay = ReplayRunner.from_payload(
            session.replay_artifact(artifact_id=f"order76-{family}-{stage}")
        ).run()
        assert replay.status is ReplayRunStatus.REPRODUCED, replay.to_payload()
        checkpoint = json.loads(json.dumps(session.to_persistence_payload(), allow_nan=False))
        restored = LocalGameSession.from_persistence_payload(checkpoint)
        assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()


@pytest.mark.parametrize("family", ["surge", "charge", "normal", "placement", "fight"])
def test_spatial_drift_diagnostic_is_pure_and_retry_replays_after_context_is_restored(
    family: str,
) -> None:
    from warhammer40k_core.geometry.pose import Pose

    session, request, payload = proposal_session(family)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    original = state.battlefield_state
    # Deliberately drift real authoritative geometry at this boundary; restore it
    # before replay, which must never contain this fixture-only change.
    placement = next(
        placement for army in original.placed_armies for placement in army.unit_placements
    )
    moved = placement.with_model_placements(
        tuple(
            model.with_pose(
                Pose.at(model.pose.position.x + 0.01, model.pose.position.y, model.pose.position.z)
            )
            for model in placement.model_placements
        )
    )
    state.replace_battlefield_state(original.with_unit_placement(moved))
    before = copy.deepcopy(session.lifecycle.to_payload())
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order76-spatial-drift"
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(invalid.payload, dict)
    assert "spatial_context_drift" in json.dumps(invalid.payload)
    assert session.lifecycle.to_payload() == before
    state.replace_battlefield_state(original)
    status = session.submit_parameterized_payload(
        request_id=request.request_id, payload=payload, result_id="order76-spatial-retry"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="spatial-retry")).run().status
        is ReplayRunStatus.REPRODUCED
    )


def test_headless_malformed_submission_uses_the_same_pure_boundary() -> None:
    from dataclasses import dataclass

    from warhammer40k_core.adapters.headless import submit_headless_decision
    from warhammer40k_core.adapters.projection import GameViewPayload
    from warhammer40k_core.engine.decision_request import DecisionRequest

    @dataclass(frozen=True)
    class Producer:
        payload: JsonValue

        def choose_option(self, *, request: DecisionRequest, view: GameViewPayload) -> str:
            return request.options[0].option_id

        def generate_payload(self, *, request: DecisionRequest, view: GameViewPayload) -> JsonValue:
            return self.payload

    session, request, _ = proposal_session("surge")
    status = session.advance_until_decision_or_terminal()
    before = copy.deepcopy(session.lifecycle.to_payload())
    producer = Producer({})
    assert request.actor_id is not None
    result = submit_headless_decision(
        session=session,
        status=status,
        viewer_player_id=request.actor_id,
        result_id="order76-headless",
        finite_option_ranker=producer,
        parameterized_payload_generator=producer,
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


def test_projection_snapshot_reuse_keeps_returns_detached() -> None:
    session, viewer = _projection_session()
    assert viewer.viewer_player_id is not None
    with cProfile.Profile() as profile:
        first = session.view_for_context(viewer=viewer)
        expected = copy.deepcopy(first)
        first["player_ids"].append("caller-only")
        second = session.view(viewer_player_id=viewer.viewer_player_id)
    assert second == expected
    assert first != second
    assert _projection_work(profile) == 1


def test_projection_snapshot_binds_complete_viewer_context() -> None:
    session, viewer = _projection_session()
    contexts = (
        viewer,
        replace(viewer, authorization_epoch=1),
        replace(viewer, principal_id="another-authorized-principal"),
        replace(viewer, policy=replace(viewer.policy, may_view_support=False)),
    )
    with cProfile.Profile() as profile:
        views = [session.view_for_context(viewer=context) for context in contexts]
    assert all(view == views[0] for view in views)
    assert _projection_work(profile) == len(contexts)


def test_projection_snapshot_detects_authoritative_geometry_drift_without_record_progress() -> None:
    from warhammer40k_core.geometry.pose import Pose

    session, request, _ = proposal_session("normal")
    assert request.actor_id is not None
    state = session.lifecycle.state
    assert state is not None
    original = state.battlefield_state
    assert original is not None
    placement = next(p for army in original.placed_armies for p in army.unit_placements)
    moved = placement.with_model_placements(
        tuple(
            model.with_pose(
                Pose.at(model.pose.position.x + 0.01, model.pose.position.y, model.pose.position.z)
            )
            for model in placement.model_placements
        )
    )
    records = session.decision_record_count()
    before = session.view(viewer_player_id=request.actor_id)
    state.replace_battlefield_state(original.with_unit_placement(moved))
    after = session.view(viewer_player_id=request.actor_id)
    assert after != before
    assert session.decision_record_count() == records
    state.replace_battlefield_state(original)
    assert session.view(viewer_player_id=request.actor_id) == before


def test_viewer_identity_cache_rechecks_history_visibility_without_count_progress() -> None:
    session, viewer = _projection_session()
    assert viewer.viewer_player_id is not None
    event_log = session.lifecycle.decision_controller.event_log
    count = len(event_log.records)
    with cProfile.Profile() as profile:
        before = session.view_for_context(viewer=viewer)
        event_log.mark_secret_suffix(
            start_index=count - 1,
            player_id=viewer.viewer_player_id,
            visibility_source="declare_battle_formations",
        )
        after = session.view_for_context(viewer=viewer)
    assert len(event_log.records) == count
    assert before == after
    assert _projection_work(profile) == 2


@pytest.mark.parametrize("reconstruct", ["fork", "restore"])
def test_projection_snapshot_is_not_shared_across_reconstructed_sessions(reconstruct: str) -> None:
    session, viewer = _projection_session()
    expected = session.view_for_context(viewer=viewer)
    clone = (
        session.fork()
        if reconstruct == "fork"
        else LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    )
    with cProfile.Profile() as profile:
        assert clone.view_for_context(viewer=viewer) == expected
        assert session.view_for_context(viewer=viewer) == expected
    assert _projection_work(profile) == 1
    assert (
        ReplayRunner.from_payload(clone.replay_artifact(artifact_id="projection-cache-clone"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


def test_projection_snapshot_reuses_only_the_narrow_submission_identity_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, viewer = _projection_session()
    request = session.lifecycle.pending_decision_request()
    assert request is not None
    expected_map = viewer_identity_map(
        event_log=session.lifecycle.decision_controller.event_log, viewer=viewer
    )
    expected_map.project(public_decision_request_payload(request, viewer=viewer))
    observed: list[dict[str, object]] = []
    original_resolve = ViewerIdentityMap.resolve

    def resolve_with_observation(
        identities: ViewerIdentityMap, value: JsonValue, *, key: str = ""
    ) -> JsonValue:
        if not observed:
            observed.append(asdict(identities))
        return original_resolve(identities, value, key=key)

    monkeypatch.setattr(ViewerIdentityMap, "resolve", resolve_with_observation)
    with cProfile.Profile() as profile:
        view = session.view_for_context(viewer=viewer)
        pending = view["pending_decision"]
        assert pending is not None
        status = session.submit_viewer_option(
            viewer=viewer,
            request_id=pending["request_id"],
            option_id=pending["options"][0]["option_id"],
            result_id="cached-projection-choice",
        )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert observed == [asdict(expected_map)]
    assert _projection_work(profile) == 1


@pytest.mark.parametrize("pretty", [False, True])
def test_immutable_player_observation_hash_uses_its_canonical_json_without_decoding(
    pretty: bool,
) -> None:
    session, viewer = _projection_session()
    view = session.view_for_context(viewer=viewer)
    context = PlayerDecisionContext(
        PolicyRoute.from_view(view),
        json.dumps(view, indent=2 if pretty else None, sort_keys=pretty),
        3,
    )
    expected = payload_digest(view)
    assert context.observation_json == canonical_json(view)
    with cProfile.Profile() as profile:
        assert [context.observation_hash for _ in range(8)] == [expected] * 8
    decodes = sum(
        entry.callcount
        for entry in profile.getstats()
        if isinstance(entry.code, CodeType)
        and entry.code.co_name == "loads"
        and entry.code.co_filename.replace("\\", "/").endswith("/json/__init__.py")
    )
    assert decodes == 0
    context.observation["player_ids"].append("caller-only")
    assert context.observation_hash == expected
    assert context.observation == view


def test_policy_payload_digest_performs_one_complete_json_validation() -> None:
    payload = {"nested": [{"finite": 1.5, "text": "detached"}], "tuple": (1, 2)}
    profiles = []
    for operation in (canonical_json, payload_digest):
        with cProfile.Profile() as profile:
            operation(payload)
        profiles.append(
            sum(
                entry.callcount
                for entry in profile.getstats()
                if isinstance(entry.code, CodeType)
                and entry.code.co_name == "validate_json_value"
                and entry.code.co_filename.replace("\\", "/").endswith("/engine/event_log.py")
            )
        )
    assert profiles[0] > 1
    assert profiles[1] == profiles[0]
