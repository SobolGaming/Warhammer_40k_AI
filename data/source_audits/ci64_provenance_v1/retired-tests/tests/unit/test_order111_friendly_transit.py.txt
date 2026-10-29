"""Order111: the Monster/Vehicle friendly blocker exception is Normal/Advance only."""

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.phase15c_fight_order_helpers import fight_lifecycle

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pathing import PathValidationContext, PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize("keyword", ["VEHICLE", "MONSTER", "INFANTRY"])
@pytest.mark.parametrize(
    "mode",
    [
        MovementMode.NORMAL,
        MovementMode.ADVANCE,
        MovementMode.FALL_BACK,
        MovementMode.CHARGE,
        MovementMode.PILE_IN,
        MovementMode.CONSOLIDATE,
    ],
)
def test_friendly_transit_uses_move_scope_and_retains_endpoint_and_enemy_rules(
    keyword: str, mode: MovementMode
) -> None:
    mover = Model("mover", Pose.at(5, 5), CircularBase(0.5), ModelVolume(1))
    blocker = Model("blocker", Pose.at(7, 5), CircularBase(0.5), ModelVolume(1))
    displacement = {
        MovementMode.NORMAL: ModelDisplacementKind.NORMAL_MOVE,
        MovementMode.ADVANCE: ModelDisplacementKind.ADVANCE,
        MovementMode.FALL_BACK: ModelDisplacementKind.FALL_BACK,
        MovementMode.CHARGE: ModelDisplacementKind.CHARGE_MOVE,
        MovementMode.PILE_IN: ModelDisplacementKind.PILE_IN,
        MovementMode.CONSOLIDATE: ModelDisplacementKind.CONSOLIDATE,
    }[mode]
    legality = MovementLegalityContext.from_keywords(
        keywords=(keyword,),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=mode,
        movement_phase_action=None,
        displacement_kind=displacement,
    )
    witness = PathWitness.for_paths(((mover.model_id, (mover.pose, Pose.at(11, 5))),))
    path = legality.to_path_validation_context(
        moving_model=mover,
        witness=witness,
        battlefield_width_inches=40,
        battlefield_depth_inches=40,
        friendly_models=(blocker,),
        friendly_vehicle_monster_model_ids=(blocker.model_id,),
    )
    restricted = keyword != "INFANTRY" and mode in (MovementMode.NORMAL, MovementMode.ADVANCE)
    result = path.validate()
    assert result.is_valid is not restricted, result.violations
    if restricted:
        assert result.violations[0].violation_code == "friendly_vehicle_monster_transit_forbidden"
    else:
        assert path.friendly_vehicle_monster_model_ids == ()
        assert PathValidationContext.from_payload(path.to_payload()).validate() == result
    endpoint = replace(
        path, witness=PathWitness.for_paths(((mover.model_id, (mover.pose, blocker.pose)),))
    ).validate()
    assert not endpoint.is_valid
    if not restricted:
        assert any(v.violation_code == "end_on_model_overlap" for v in endpoint.violations)
    enemy = legality.to_path_validation_context(
        moving_model=mover,
        witness=witness,
        battlefield_width_inches=40,
        battlefield_depth_inches=40,
        enemy_models=(blocker,),
        enemy_vehicle_monster_model_ids=(blocker.model_id,),
    )
    # Fall Back already has its independent enemy-transit/Desperate Escape rules.
    assert enemy.validate().is_valid is (mode is MovementMode.FALL_BACK)
    excluded = replace(path, friendly_model_transit_blocker_ids=(blocker.model_id,)).validate()
    assert not excluded.is_valid
    if not restricted:
        assert any(
            v.violation_code == "friendly_model_transit_forbidden" for v in excluded.violations
        )


def _catalog(keyword: str) -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return replace(
        catalog,
        model_keyword_assignments=tuple(
            replace(row, keywords=(*row.keywords, keyword))
            if row.datasheet_id == "core-character-leader"
            else row
            for row in catalog.model_keyword_assignments
        ),
        datasheets=tuple(
            replace(
                sheet,
                keywords=replace(sheet.keywords, keywords=(*sheet.keywords.keywords, keyword)),
                model_profiles=tuple(
                    replace(profile, base_size=replace(profile.base_size, diameter_mm=32))
                    for profile in sheet.model_profiles
                ),
            )
            if sheet.datasheet_id == "core-character-leader"
            else sheet
            for sheet in catalog.datasheets
        ),
    )


def _assert_round_trip(session: LocalGameSession) -> None:
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    assert restored.to_persistence_payload() == checkpoint
    forked = session.fork()
    assert forked.to_persistence_payload() == checkpoint
    assert forked.lifecycle is not session.lifecycle
    assert forked.lifecycle.state is not session.lifecycle.state
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(EventStreamCursor(), viewer_player_id=viewer) == (
            session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order111")).run().status
        is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("keyword", ["VEHICLE", "MONSTER"])
def test_fall_back_through_friendly_model_retries_restores_and_replays(keyword: str) -> None:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("mover", "friendly"),
        enemy_unit_ids=("enemy",),
        origins={"mover": Pose.at(10, 10), "friendly": Pose.at(12, 10), "enemy": Pose.at(8, 10)},
        game_id=f"order111-fall-back-{keyword}",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
        catalog=_catalog(keyword),
        battle_phase=BattlePhase.MOVEMENT,
        record_deployment=True,
    )
    session = LocalGameSession(lifecycle)
    assert keyword in units["mover"].keywords
    assert keyword in units["friendly"].keywords
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    for index, option in enumerate((units["mover"].unit_instance_id, "fall_back:ordered_retreat")):
        request = session.submit_option(
            request_id=request.request_id, option_id=option, result_id=f"select-{index}"
        ).decision_request
        assert request is not None
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    before = state.battlefield_state
    mover = before.unit_placement_by_id(units["mover"].unit_instance_id).model_placements[0]
    for index, end in enumerate((Pose.at(12, 10), Pose.at(15, 10))):
        move = MovementProposalRequest.from_decision_request_payload(request.payload)
        payload: dict[str, JsonValue] = {
            "proposal_request_id": request.request_id,
            "proposal_kind": move.proposal_kind.value,
            "unit_instance_id": move.unit_instance_id,
            "movement_phase_action": "fall_back",
            "movement_mode": "fall_back",
            "fall_back_mode": "ordered_retreat",
            "witness": cast(
                JsonValue,
                PathWitness.for_paths(((mover.model_instance_id, (mover.pose, end)),)).to_payload(),
            ),
        }
        forked = None
        if index == 1:
            checkpoint = session.to_persistence_payload()
            forked = session.fork()
            fork_status = forked.submit_parameterized_payload(
                request_id=request.request_id, result_id=f"path-{index}", payload=payload
            )
            assert fork_status.status_kind is not LifecycleStatusKind.INVALID, (
                fork_status.to_payload()
            )
            assert session.to_persistence_payload() == checkpoint
        status = session.submit_parameterized_payload(
            request_id=request.request_id, result_id=f"path-{index}", payload=payload
        )
        if index == 0:
            assert status.status_kind is LifecycleStatusKind.INVALID
            assert state.battlefield_state == before
            assert "end_on_model_overlap" in json.dumps(status.to_payload())
            request = session.advance_until_decision_or_terminal().decision_request
            assert request is not None
        else:
            assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
            assert state.battlefield_state is not None
            assert (
                state.battlefield_state.unit_placement_by_id(move.unit_instance_id)
                .model_placements[0]
                .pose
                == end
            )
            assert forked is not None
            assert session.to_persistence_payload() == forked.to_persistence_payload()
    _assert_round_trip(session)


def test_pile_in_friendly_transit_uses_facade_and_replays() -> None:
    mode = MovementMode.PILE_IN
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("mover", "friendly"),
        enemy_unit_ids=("enemy",),
        origins={
            "mover": Pose.at(10, 10),
            "friendly": Pose.at(11.5, 10),
            "enemy": Pose.at(12, 12.4),
        },
        game_id=f"order111-{mode.value}",
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
        catalog=_catalog("VEHICLE"),
        record_deployment=True,
    )
    session = LocalGameSession(lifecycle)
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    mover = state.battlefield_state.unit_placement_by_id(
        units["mover"].unit_instance_id
    ).model_placements[0]
    status = session.advance_until_decision_or_terminal()
    for index in range(30):
        request = status.decision_request
        assert request is not None, status.to_payload()
        assert request.decision_type == "submit_movement_proposal", request
        move = MovementProposalRequest.from_decision_request_payload(request.payload)
        selected = (
            move.proposal_kind.value == mode.value
            and move.unit_instance_id == units["mover"].unit_instance_id
        )
        payload: dict[str, JsonValue] = {
            "proposal_request_id": request.request_id,
            "proposal_kind": move.proposal_kind.value,
            "unit_instance_id": move.unit_instance_id,
            "movement_phase_action": move.movement_phase_action,
            "movement_mode": move.proposal_kind.value,
        }
        if selected:
            payload["witness"] = cast(
                JsonValue,
                PathWitness.for_paths(
                    ((mover.model_instance_id, (mover.pose, Pose.at(13, 10))),)
                ).to_payload(),
            )
            payload[f"{mode.value}_target_unit_instance_ids"] = [units["enemy"].unit_instance_id]
        status = session.submit_parameterized_payload(
            request_id=request.request_id, result_id=f"fight-path-{index}", payload=payload
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
        if selected:
            assert state.battlefield_state is not None
            assert state.battlefield_state.unit_placement_by_id(
                move.unit_instance_id
            ).model_placements[0].pose == Pose.at(13, 10)
            _assert_round_trip(session)
            return
    pytest.fail("Expected Fight move was not reached through the facade.")
