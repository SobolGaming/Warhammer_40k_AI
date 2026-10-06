"""Catalog-mustered movement with original and native flight source controls."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

from tests.core_clause_evidence_helpers import clause_session
from tests.phase11c_command_phase_helpers import phase11c_config, secondary_choice
from tests.psychic_modifier_helpers import pending_request
from tests.setup_completion_helpers import (
    ensure_army_mustered_events_for_fixture,
    record_current_battlefield_placements_for_fixture,
)
from warhammer40k_core.adapters.access_control import (
    ROLE_POLICY_BY_ROLE,
    PrincipalRole,
    ViewerContext,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState, SecondaryMissionMode
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatus
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_roster_2026_07,
)


def native_flight_session() -> LocalGameSession:
    """Use the exact reconciled Be'lakor sheet, FLY keyword and catalog geometry.

    The detachment's test force-disposition admission is explicit fixture setup;
    no named faction rule or physical provider certification is inferred.
    """
    package = chaos_daemons_roster_2026_07.catalog_package()
    catalog = package.army_catalog
    detachment = next(row for row in catalog.detachments if row.detachment_id == "shadow-legion")
    catalog = replace(
        catalog,
        detachments=(
            replace(detachment, force_disposition_ids=("take-and-hold", "purge-the-foe")),
        ),
    )
    selection = UnitMusterSelection(
        unit_selection_id="mover",
        datasheet_id="000001148",
        model_profile_selections=(ModelProfileSelection("000001148:belakor-epic-hero", 1),),
    )
    config = replace(
        phase11c_config(game_id="order129-native-fly"),
        army_catalog=catalog,
        model_geometries=package.model_geometries,
        army_muster_requests=tuple(
            ArmyMusterRequest(
                army_id=army,
                player_id=player,
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="chaos-daemons", detachment_ids=("shadow-legion",)
                ),
                force_disposition_id=disposition,
                unit_selections=(selection,),
            )
            for army, player, disposition in (
                ("army-alpha", "player-a", "take-and-hold"),
                ("army-beta", "player-b", "purge-the-foe"),
            )
        ),
    )
    state = GameState.from_config(config)
    for request in config.army_muster_requests:
        state.record_army_definition(
            muster_army(catalog=catalog, request=request, model_geometries=package.model_geometries)
        )
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="order129-native-field", armies=tuple(state.army_definitions)
    )
    battlefield = scenario.battlefield_state
    for owner, y in (("army-alpha", 10), ("army-beta", 16)):
        placement = battlefield.unit_placement_by_id(f"{owner}:mover")
        battlefield = battlefield.with_unit_placement(
            replace(
                placement,
                model_placements=tuple(
                    replace(row, pose=Pose.at(25, y)) for row in placement.model_placements
                ),
            )
        )
    state.record_battlefield_state(battlefield)
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            secondary_choice(player_id=player, mode=SecondaryMissionMode.FIXED)
        )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    decisions = DecisionController()
    ensure_army_mustered_events_for_fixture(state, decisions=decisions)
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    return LocalGameSession(
        GameLifecycle.from_payload(
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
    )


def flight_proposal(
    *, native: bool = False, action: str = "advance", flight: bool = True, transit: bool = True
) -> tuple[LocalGameSession, MovementProposalPayload]:
    session = (
        native_flight_session()
        if native
        else clause_session(
            phase=BattlePhase.MOVEMENT,
            fly=True,
            enemy_origin=Pose.at(10, 23)
            if action == "fall_back"
            else Pose.at(10, 23.3)
            if transit
            else Pose.at(30, 20),
        )
    )
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    before = state.battlefield_state.unit_placement_by_id("army-alpha:mover")
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, option_id=before.unit_instance_id, result_id="select"
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        option_id=action
        + (":ordered_retreat" if action == "fall_back" else "")
        + (":fly_take_to_skies" if flight else ""),
        result_id="mode",
    )
    request = pending_request(session)
    context = MovementProposalRequest.from_decision_request_payload(request.payload)
    distance = -2.0 if action == "fall_back" else 12.0 if native else 6.6 if transit else 2.0
    return session, MovementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=context.proposal_kind,
        unit_instance_id=context.unit_instance_id,
        movement_phase_action=action,
        movement_mode="fly_take_to_skies"
        if flight
        else "normal"
        if action == "normal_move"
        else action,
        fall_back_mode="ordered_retreat" if action == "fall_back" else None,
        witness=PathWitness.for_paths(
            tuple(
                (
                    row.model_instance_id,
                    (
                        row.pose,
                        Pose.at(row.pose.position.x, row.pose.position.y + distance / 2),
                        Pose.at(row.pose.position.x, row.pose.position.y + distance),
                    ),
                )
                for row in before.model_placements
            )
        ),
    )


def submit_flight(
    session: LocalGameSession, proposal: MovementProposalPayload, result: str
) -> LifecycleStatus:
    return session.submit_parameterized_payload(
        request_id=proposal.proposal_request_id,
        result_id=result,
        payload=validate_json_value(proposal.to_payload()),
    )


def assert_flight_checkpoint(session: LocalGameSession) -> None:
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
                    principal_id=f"order129:{role}:{player}",
                    role=role,
                    viewer_player_id=player,
                    policy=ROLE_POLICY_BY_ROLE[role],
                )
                assert recovered.view_for_context(viewer=viewer) == session.view_for_context(
                    viewer=viewer
                )
                assert recovered.events_since_for_context(
                    EventStreamCursor(), viewer=viewer
                ) == session.events_since_for_context(EventStreamCursor(), viewer=viewer)
    before = session.to_persistence_payload()
    request = pending_request(fork)
    assert fork.lifecycle.state is not session.lifecycle.state
    if not request.is_parameterized_submission_request():
        fork.submit_option(
            request_id=request.request_id,
            option_id=request.options[0].option_id,
            result_id="fork-only",
        )
        assert fork.to_persistence_payload() != before
    assert session.to_persistence_payload() == before
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="order129-flight")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay
