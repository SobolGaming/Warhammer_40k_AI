"""Real facade fixtures for the Order 97 cross-category evidence."""

from __future__ import annotations

import json
from dataclasses import replace

from tests.phase15a_charge_test_support import _charge_lifecycle, _compact_test_unit_poses
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, WeaponKeyword
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.geometry.pose import Pose

_DEFAULT_ENEMY_ORIGIN = Pose.at(30, 20)


def clause_session(
    *, phase: BattlePhase, fly: bool = False, enemy_origin: Pose = _DEFAULT_ENEMY_ORIGIN
) -> LocalGameSession:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet, keywords=replace(sheet.keywords, keywords=(*sheet.keywords.keywords, "FLY"))
            )
            if fly and sheet.datasheet_id == "core-intercessor-like-infantry"
            else sheet
            for sheet in catalog.datasheets
        ),
        wargear=tuple(
            replace(
                item,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        keywords=(WeaponKeyword.HEAVY,),
                        abilities=(AbilityDescriptor.heavy(),),
                    )
                    if item.wargear_id == "core-bolt-rifle"
                    else profile
                    for profile in item.weapon_profiles
                ),
            )
            for item in catalog.wargear
        ),
    )
    lifecycle, _ = _charge_lifecycle(
        alpha_unit_ids=("mover",),
        enemy_model_poses=_compact_test_unit_poses(origin=enemy_origin, model_count=5),
        game_id=f"order97-{phase.value}-{fly}",
        catalog=catalog,
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    return LocalGameSession(lifecycle)


def assert_persistence_viewers_replay(session: LocalGameSession) -> None:
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="order97")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay


def flying_transit_session() -> LocalGameSession:
    from tests.psychic_modifier_helpers import pending_request
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalPayload,
        MovementProposalRequest,
    )
    from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
    from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range
    from warhammer40k_core.geometry.pathing import PathWitness

    session = clause_session(phase=BattlePhase.MOVEMENT, fly=True, enemy_origin=Pose.at(10, 23.3))
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    source = state.battlefield_state.unit_placement_by_id("army-alpha:mover")
    assert not unit_within_enemy_engagement_range(
        state=state, unit_instance_id=source.unit_instance_id
    )
    before = state.battlefield_state
    midpoint = replace(
        source,
        model_placements=tuple(
            replace(row, pose=Pose.at(row.pose.position.x, row.pose.position.y + 3.3, 0))
            for row in source.model_placements
        ),
    )
    state.battlefield_state = before.with_unit_placement(midpoint)
    assert unit_within_enemy_engagement_range(state=state, unit_instance_id=source.unit_instance_id)
    state.battlefield_state = before
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, option_id=source.unit_instance_id, result_id="select"
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        option_id="advance:fly_take_to_skies",
        result_id="fly",
    )
    request = pending_request(session)
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    witness = PathWitness.for_paths(
        tuple(
            (
                row.model_instance_id,
                (
                    row.pose,
                    Pose.at(row.pose.position.x, row.pose.position.y + 3.3, 0),
                    Pose.at(row.pose.position.x, row.pose.position.y + 6.6),
                ),
            )
            for row in source.model_placements
        )
    )
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="cross",
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=proposal.unit_instance_id,
                movement_phase_action="advance",
                movement_mode="fly_take_to_skies",
                witness=witness,
            ).to_payload()
        ),
    )
    assert result.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert state.battlefield_state.unit_placement_by_id(
        source.unit_instance_id
    ).model_placements == (
        tuple(
            replace(row, pose=Pose.at(row.pose.position.x, row.pose.position.y + 6.6))
            for row in source.model_placements
        )
    )
    assert not unit_within_enemy_engagement_range(
        state=state, unit_instance_id=source.unit_instance_id
    )
    return session
