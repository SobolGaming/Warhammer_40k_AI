"""Admit the exact constructed A4 Normal Move origin for a single scoped test."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import cast
from unittest.mock import patch

import pytest

from tests import phase15a_charge_declaration_helpers as fixture
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, payload_digest
from warhammer40k_core.ai.training_admission import TrainingAdmissionError, VerifiedEpisodeOrigin
from warhammer40k_core.build_identity import current_engine_build_id
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.command_core_cp_history import (
    expected_core_command_occurrence_keys,
    validate_core_command_point_anchor,
)
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.primary_victory_point_policy import (
    validate_victory_point_ledger_policy,
)
from warhammer40k_core.engine.replay import ReplayArtifactPayload, ReplayRunner
from warhammer40k_core.engine.return_placement_legality import validate_model_placement_endpoints
from warhammer40k_core.engine.unit_coherency import UnitCoherencyContext, UnitCoherencyStatus
from warhammer40k_core.geometry.pose import Pose

_GAME = "stage2-e-cooperation-screen-before-denial-v1"
_PLAYERS = ("player-a", "player-b")
_SCREEN = "army-alpha:screen"
_RUNTIME = (
    "warhammer40k-core-v2:runtime-tree-sha256-v1:"
    "1bfd3b67d2fbe5eb2df35cd0c17ab30974c90d1efdf3b0fe2e7167a16655198a"
)
_CONFIG = "f94eb419965e3b3facb41f2691176fafac0f4bbbc57c59a148e5d8485399bc1d"
_ORIGIN = "0ed84a89e5b03dcad8ccdebd2fa29400928111a66fb1144c76ea70a9a55cb6a8"
_ORIGIN_VIEWS = "0f0cc20286e9263047add26d9de74d7f9cca42339a5b03cf2e5c0c6927fed977"
_S_OFFER = "2919cce290824fd387e2eba766d4c9375730e6d81571f55a40255419bc8c222f"
_S_VIEWS = "6ad816c71a5b1a3496db6e62c69a468e66168969eff4012ed5df31b627179db0"
_S_EVENT_LOG = "111083e38972569788bb2a9bb906e25969e2acbb9f681f674f992964dd58b174"


def _construct_v1() -> LocalGameSession:
    """Reuse the locked Phase 15A helper; this is not a startup history."""
    mission = fixture.mission_setup()
    marker = replace(
        mission.objective_markers[0],
        name="Cooperation Control Central",
        x_inches=30.0,
        y_inches=30.0,
    )
    with patch.object(
        fixture, "mission_setup", return_value=replace(mission, objective_markers=(marker,))
    ):
        lifecycle, _ = fixture.charge_lifecycle(
            game_id=_GAME,
            alpha_unit_ids=("screen", "exploiter"),
            alpha_origins={"screen": Pose.at(23.7, 40.8), "exploiter": Pose.at(27.2, 22.8)},
            enemy_unit_ids=("denial",),
            enemy_model_poses=fixture.compact_test_unit_poses(
                origin=Pose.at(32.8, 33), model_count=5
            ),
            battle_round=4,
        )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    record_primary_turn_start_evidence_for_fixture(state, decisions=lifecycle.decision_controller)
    session = LocalGameSession(lifecycle)
    assert (
        session.advance_until_decision_or_terminal().status_kind
        is LifecycleStatusKind.WAITING_FOR_DECISION
    )
    return session


def _check_rosters_and_placement(session: LocalGameSession) -> None:
    state = session.lifecycle.state
    assert state is not None
    mission = state.mission_setup
    assert mission is not None
    assert mission.deployment_zones == ()
    assert mission.terrain_features == ()
    assert session.lifecycle.config.allow_legacy_non_strict_rosters is True
    expected_unpriced_units = {"army-alpha": {"screen", "exploiter"}, "army-beta": {"denial"}}
    assert {army.army_id for army in state.army_definitions} == expected_unpriced_units.keys()
    assert state.battlefield_state is not None
    board = state.battlefield_state
    ruleset = session.lifecycle.config.ruleset_descriptor
    scenario = BattlefieldScenario(armies=tuple(state.army_definitions), battlefield_state=board)
    for army in state.army_definitions:
        assert army.warlord_selection is None
        assert army.points_source_package_id is None
        violations = army.roster_legality_report.violations
        actual = {(row.violation_code, row.unit_selection_id) for row in violations}
        expected = {
            ("source_awaiting_unit_points", key) for key in expected_unpriced_units[army.army_id]
        }
        assert actual == {*expected, ("missing_warlord_selection", None)}
        assert len(violations) == len(actual)
        for unit in army.units:
            placements = board.unit_placement_by_id(unit.unit_instance_id).model_placements
            assert len(placements) == len(unit.own_models) == 5
            validate_model_placement_endpoints(
                scenario=scenario,
                ruleset_descriptor=ruleset,
                placements=placements,
                placement_label="Constructed A4 placement",
            )
            by_id = {model.model_instance_id: model for model in unit.own_models}
            models = tuple(
                geometry_model_for_placement(model=by_id[row.model_instance_id], placement=row)
                for row in placements
            )
            result = UnitCoherencyContext.from_ruleset_descriptor(
                ruleset, unit_instance_id=unit.unit_instance_id
            ).validate_models(models)
            assert result.status is UnitCoherencyStatus.COHERENT
    assert len(board.placed_model_ids()) == 15
    screen = board.unit_placement_by_id(_SCREEN).model_placements
    overlap = (replace(screen[0], pose=screen[1].pose), *screen[1:])
    with pytest.raises(GameLifecycleError, match="models overlap each other"):
        validate_model_placement_endpoints(
            scenario=scenario,
            ruleset_descriptor=ruleset,
            placements=overlap,
            placement_label="Constructed A4 negative control",
        )


def _check_cp_vp_provenance(session: LocalGameSession) -> None:
    state = session.lifecycle.state
    assert state is not None
    records = session.lifecycle.decision_controller.event_log.records
    command_keys: list[tuple[int, str]] = []
    for index, event in enumerate(records):
        if event.event_type == "command_step_started":
            payload = event.payload
            assert isinstance(payload, dict)
            battle_round, player = payload["battle_round"], payload["active_player_id"]
            assert isinstance(battle_round, int)
            assert isinstance(player, str)
            command_keys.append((battle_round, player))
            validate_core_command_point_anchor(
                state=state, event_records=records, anchor_index=index, payload=payload
            )
    assert tuple(command_keys) == expected_core_command_occurrence_keys(state)
    assert tuple(command_keys) == (*((r, p) for r in (1, 2, 3) for p in _PLAYERS), (4, "player-a"))
    assert [
        (ledger.command_points, len(ledger.transactions)) for ledger in state.command_point_ledgers
    ] == [(7, 7), (7, 7)]

    mission = state.mission_setup
    assert mission is not None
    policies = mission_scoring_policies_from_setup(mission)
    expected = {
        (
            f"objective-control:round-{r:02}:player-b:command:phase_end",
            "meatgrinder-objective-control",
        )
        for r in (2, 3)
    }
    assert tuple(ledger.victory_points for ledger in state.victory_point_ledgers) == (0, 8)
    for ledger in state.victory_point_ledgers:
        result = validate_victory_point_ledger_policy(
            policy=policies.policy_for_player(ledger.player_id),
            ledger=ledger,
            objective_control_records=tuple(state.objective_control_records),
            primary_scoring_state_evidence_records=tuple(
                state.primary_scoring_state_evidence_records
            ),
            turn_order=state.turn_order,
        )
        assert result.primary_binding_identities == (
            expected if ledger.player_id == "player-b" else set()
        )
    # These are native scoring boundaries from the constructed Command occurrences.
    # They do not prove that either player reached them through ordinary deployment.
    commits: set[str] = set()
    for event in records:
        if event.event_type != "primary_scoring_commit_checkpoint_recorded":
            continue
        payload = event.payload
        assert isinstance(payload, dict)
        if payload["scoring_player_id"] == "player-b":
            record_id = payload["objective_control_record_id"]
            assert isinstance(record_id, str)
            commits.add(record_id)
    assert commits == {record_id for record_id, _rule in expected}


def _viewer_digest(session: LocalGameSession) -> str:
    return payload_digest(
        {
            player: {
                "view": session.view(viewer_player_id=player),
                "events": session.events_since(EventStreamCursor(), viewer_player_id=player),
            }
            for player in _PLAYERS
        }
    )


def test_constructed_normal_move_origin_v1_admits_only_test_fixture() -> None:
    assert current_engine_build_id() == _RUNTIME
    session = _construct_v1()
    config = session.lifecycle.config
    assert payload_digest(config.to_payload()) == _CONFIG
    assert payload_digest(session.lifecycle.to_payload()) == _ORIGIN
    assert _viewer_digest(session) == _ORIGIN_VIEWS
    assert (session.decision_record_count(), session.event_record_count()) == (0, 159)
    _check_rosters_and_placement(session)
    _check_cp_vp_provenance(session)
    with pytest.raises(TrainingAdmissionError, match="does not start from ordinary config"):
        VerifiedEpisodeOrigin.from_session(session, config=config)

    viewer = ViewerContext.for_player("player-a")
    context = PlayerDecisionContext.from_view(
        session.view_for_context(viewer=viewer), choice_seed=0
    )
    assert context.route.decision_type == "select_movement_unit"
    action = FiniteCandidateSet.from_context(context).select(context, _SCREEN)
    assert action.option_id is not None
    result = session.submit_viewer_option(
        viewer=viewer,
        request_id=action.request_id,
        option_id=action.option_id,
        result_id="common:A4:S:unit",
    )
    assert result.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert (session.decision_record_count(), session.event_record_count()) == (1, 162)
    context = PlayerDecisionContext.from_view(
        session.view_for_context(viewer=viewer), choice_seed=0
    )
    assert context.route.decision_type == "select_movement_action"
    assert set(FiniteCandidateSet.from_context(context).candidate_ids) == {
        "remain_stationary",
        "normal_move",
        "advance",
    }
    assert _viewer_digest(session) == _S_VIEWS
    checkpoint = session.to_persistence_payload()
    assert isinstance(checkpoint, dict)
    assert checkpoint["content_hash"] == _S_OFFER
    assert checkpoint["event_log_hash"] == _S_EVENT_LOG
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    assert restored.to_persistence_payload() == checkpoint
    assert _viewer_digest(restored) == _S_VIEWS
    replay = ReplayRunner.from_payload(
        cast(ReplayArtifactPayload, checkpoint["replay_artifact"])
    ).run()
    assert replay.reproduced_exactly
    assert replay.final_event_log_hash == _S_EVENT_LOG
