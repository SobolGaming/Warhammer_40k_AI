"""Catalog-backed casualties followed by actual facade turn-end cleanup."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

from tests.order129_helpers import native_flight_session
from tests.phase11c_command_phase_helpers import (
    destroy_models_with_recorded_mortal_wounds,
    phase11c_config,
    secondary_choice,
)
from tests.phase17n_secondary_mission_helpers import seed_resolved_secondary_mission_selections
from tests.phase17n_step6g_secondary_certification_helpers import seed_completed_fight_phase
from tests.setup_completion_helpers import (
    ensure_army_mustered_events_for_fixture,
    record_current_battlefield_placements_for_fixture,
    record_primary_turn_start_evidence_for_fixture,
)
from warhammer40k_core.adapters.access_control import (
    ROLE_POLICY_BY_ROLE,
    PrincipalRole,
    ViewerContext,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.engine.army_mustering import muster_army
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState, SecondaryMissionMode
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.model_destruction_primary_events import (
    record_primary_destruction_occurrences,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.geometry.pose import Pose


def destruction_session(*, scoring_player: str = "player-a", wounds: int = 10) -> LocalGameSession:
    """The canonical test catalog explicitly supplies W10; this is not a native sheet."""
    base = phase11c_config(game_id=f"order130-{scoring_player}-{wounds}")
    catalog = replace(
        base.army_catalog,
        datasheets=tuple(
            replace(
                sheet,
                model_profiles=tuple(
                    replace(
                        profile,
                        characteristics=tuple(
                            CharacteristicValue.from_raw(Characteristic.WOUNDS, wounds)
                            if value.characteristic is Characteristic.WOUNDS
                            else value
                            for value in profile.characteristics
                        ),
                    )
                    for profile in sheet.model_profiles
                ),
            )
            if sheet.datasheet_id == "core-intercessor-like-infantry"
            else sheet
            for sheet in base.army_catalog.datasheets
        ),
    )
    config = replace(base, army_catalog=catalog)
    state = GameState.from_config(config)
    for request in config.army_muster_requests:
        state.record_army_definition(muster_army(catalog=catalog, request=request))
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="order130-field", armies=tuple(state.army_definitions)
    )
    battlefield = scenario.battlefield_state
    for army in state.army_definitions:
        placement = battlefield.unit_placement_by_id(army.units[0].unit_instance_id)
        y = 12 if army.player_id == scoring_player else 32
        battlefield = battlefield.with_unit_placement(
            replace(
                placement,
                model_placements=tuple(
                    replace(row, pose=Pose.at(x, y))
                    for row, x in zip(
                        placement.model_placements, (10, 11.5, 13, 15.5, 18), strict=True
                    )
                ),
            )
        )
    state.record_battlefield_state(battlefield)
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            secondary_choice(player_id=player, mode=SecondaryMissionMode.FIXED)
        )
        seed_resolved_secondary_mission_selections(state, player_id=player)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.battle_round = 2
    state.active_player_id = scoring_player
    seed_completed_fight_phase(state)
    decisions = DecisionController()
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    enemy = next(army for army in state.army_definitions if army.player_id != scoring_player).units[
        0
    ]
    destroy_models_with_recorded_mortal_wounds(
        state=state,
        decisions=decisions,
        unit_instance_id=enemy.unit_instance_id,
        model_instance_ids=(enemy.own_models[-2].model_instance_id,),
        application_id="order130-bridge",
        destroying_player_id=scoring_player,
    )
    lifecycle = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": decisions.to_payload(),
                "reaction_queue": {"frames": []},
            },
        )
    )
    return session_from_casualty_checkpoint(lifecycle)


def finish_turn(session: LocalGameSession) -> None:
    state = session.lifecycle.state
    assert state is not None
    owner, round_number = state.active_player_id, state.battle_round
    for index in range(30):
        current = session.lifecycle.state
        assert current is not None
        if (current.active_player_id, current.battle_round) != (owner, round_number):
            return
        pending = session.lifecycle.pending_decision_request()
        if pending is None:
            status = session.advance_until_decision_or_terminal()
        else:
            assert pending.decision_type in {
                "resolve_sequencing_order",
                "select_primary_mission_choice",
                "score_tactical_secondary_mission",
            }, pending.decision_type
            status = session.submit_option(
                request_id=pending.request_id,
                option_id=pending.options[0].option_id,
                result_id=f"order130-finish-{index}",
            )
        assert status.status_kind not in {
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }, status
    raise AssertionError("Order130 turn did not complete")


def native_destruction_session() -> LocalGameSession:
    """Preserve the admitted exact Be'lakor sheet, W20 and source-linked geometry."""
    template = native_flight_session()
    state = template.lifecycle.state
    assert state is not None
    state.battle_round = 2
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    for player_id in state.player_ids:
        seed_resolved_secondary_mission_selections(state, player_id=player_id)
    seed_completed_fight_phase(state)
    decisions = template.lifecycle.decision_controller
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    enemy = state.army_definitions[1].units[0]
    destroy_models_with_recorded_mortal_wounds(
        state=state,
        decisions=decisions,
        unit_instance_id=enemy.unit_instance_id,
        model_instance_ids=enemy.own_model_ids(),
        application_id="order130-native-death",
        destroying_player_id="player-a",
    )
    source = next(
        event
        for event in reversed(decisions.event_log.records)
        if event.event_type == "model_destroyed"
    )
    assert isinstance(source.payload, dict)
    record_primary_destruction_occurrences(
        state=state,
        decisions=decisions,
        model_destroyed_events=(),
        physical_component_completion_events=(),
        completion_events=((source.event_id, source.payload),),
    )
    return session_from_casualty_checkpoint(
        GameLifecycle.from_payload(template.lifecycle.to_payload())
    )


def session_from_casualty_checkpoint(lifecycle: GameLifecycle) -> LocalGameSession:
    """Root fixture replay at the engine-generated pre-existing casualty checkpoint.

    The fixture's damage decisions predate the tested turn-end continuation.
    Preserve them and their event provenance in the initial snapshot, just as the
    existing shared casualty fixtures do. All subsequent records are replayed.
    """
    session = LocalGameSession(lifecycle)
    object.__setattr__(session, "_initial_replay_lifecycle_payload", lifecycle.to_payload())
    return session


def assert_destruction_checkpoint(session: LocalGameSession) -> None:
    payload = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(payload)
    fork = session.fork()
    for recovered in (restored, fork):
        assert recovered.to_persistence_payload() == payload
        for role in PrincipalRole:
            for player in (
                ("player-a", "player-b")
                if role in {PrincipalRole.PLAYER, PrincipalRole.COACH}
                else (None,)
            ):
                viewer = ViewerContext(
                    principal_id=f"order130:{role}:{player}",
                    role=role,
                    viewer_player_id=player,
                    policy=ROLE_POLICY_BY_ROLE[role],
                )
                assert recovered.view_for_context(viewer=viewer) == session.view_for_context(
                    viewer=viewer
                )
                assert recovered.events_since_for_context(EventStreamCursor(), viewer=viewer) == (
                    session.events_since_for_context(EventStreamCursor(), viewer=viewer)
                )
    assert fork.lifecycle.state is not session.lifecycle.state
    request = fork.lifecycle.pending_decision_request()
    if request is not None and not request.is_parameterized_submission_request():
        fork.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id="order130-fork-only",
        )
        assert fork.to_persistence_payload() != payload
    assert session.to_persistence_payload() == payload
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="order130")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


def unaffected_unit_with_invalid_coherency_payload(
    session: LocalGameSession,
) -> GameLifecyclePayload:
    """An unrelated placement edit must not acquire the casualty-gap exception."""
    lifecycle = GameLifecycle.from_payload(session.lifecycle.to_payload())
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    friendly = next(
        army for army in state.army_definitions if army.player_id == state.active_player_id
    )
    placement = state.battlefield_state.unit_placement_by_id(friendly.units[0].unit_instance_id)
    last = placement.model_placements[-1]
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        replace(
            placement,
            model_placements=(
                *placement.model_placements[:-1],
                replace(last, pose=Pose.at(45, 12)),
            ),
        )
    )
    return lifecycle.to_payload()
