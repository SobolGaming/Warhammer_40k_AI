"""Native, predeclared analytical fixtures for the scoped Heavy repair."""

from __future__ import annotations

import json
from dataclasses import replace
from math import sqrt
from typing import cast

from tests.phase13b_shooting_declaration_helpers import _proposal_from_request
from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses
from tests.psychic_modifier_helpers import pending_request, submit_fixture_request
from tests.sequential_translation_helpers import leading_first_translation_paths
from warhammer40k_core.adapters.access_control import AuthenticatedPrincipal, PrincipalRole
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import (
    canonical_rules_unit_view_from_armies,
    rules_unit_view_from_armies,
)
from warhammer40k_core.engine.stratagems import stratagem_decline_payload
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

SHOOTER = "army-alpha:mover"


def heavy_session(
    *,
    assault: bool = True,
    attached: bool = False,
    fly: bool = False,
    profile: WeaponProfile | None = None,
) -> LocalGameSession:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet, keywords=replace(sheet.keywords, keywords=(*sheet.keywords.keywords, "FLY"))
            )
            if fly
            else sheet
            for sheet in catalog.datasheets
        ),
        wargear=tuple(
            replace(
                item,
                weapon_profiles=tuple(
                    profile
                    if profile is not None and item.wargear_id == "core-bolt-rifle"
                    else replace(
                        existing,
                        keywords=(WeaponKeyword.ASSAULT, WeaponKeyword.HEAVY)
                        if assault
                        else (WeaponKeyword.HEAVY,),
                        abilities=(AbilityDescriptor.heavy(),),
                    )
                    if item.wargear_id == "core-bolt-rifle"
                    else existing
                    for existing in item.weapon_profiles
                ),
            )
            for item in catalog.wargear
        ),
    )
    lifecycle, _ = charge_lifecycle(
        alpha_unit_ids=("mover", "leader") if attached else ("mover",),
        alpha_attached_unit_ids=("mover", "leader") if attached else None,
        alpha_origins={"mover": Pose.at(10, 20), "leader": Pose.at(10, 21.8)},
        enemy_unit_ids=("enemy", "enemy-leader") if attached else ("enemy",),
        enemy_attached_unit_ids=("enemy", "enemy-leader") if attached else None,
        enemy_origins={"enemy": Pose.at(30, 20), "enemy-leader": Pose.at(30, 21.8)},
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(30, 20), model_count=5),
        game_id=f"d09-heavy-{assault}-{attached}-{fly}",
        catalog=catalog,
    )
    state = lifecycle.state
    assert state is not None
    # Define the analytical replay root before the first facade request. All
    # movement, dice, histories and later phase transitions are engine-owned.
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    return LocalGameSession(lifecycle)


def heavy_unit_id(session: LocalGameSession) -> str:
    state = session.lifecycle.state
    assert state is not None
    component = SHOOTER if state.active_player_id == "player-a" else "army-beta:enemy"
    return rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=component,
    ).unit_instance_id


def reach_second_player_movement(session: LocalGameSession) -> None:
    for _ in range(80):
        request = pending_request(session)
        state = session.lifecycle.state
        assert state is not None
        if (
            state.active_player_id == "player-b"
            and state.current_battle_phase is BattlePhase.MOVEMENT
        ):
            assert request.decision_type == "select_movement_unit"
            return
        if request.decision_type == "submit_stratagem_target_proposal":
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=request.request_id + ":d09-skip",
                payload=stratagem_decline_payload(),
            )
        else:
            options = [
                option
                for option in request.options
                if option.option_id.startswith("complete_")
                or "decline" in option.option_id
                or option.option_id == "remain_stationary"
            ]
            if not options:
                assert request.decision_type == "select_movement_unit", request
                options = list(request.options)
            status = session.submit_option(
                request_id=request.request_id,
                option_id=options[0].option_id,
                result_id=request.request_id + ":d09-skip",
            )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    raise AssertionError("D09 native progression did not reach second player's Movement.")


def decline_native_windows(session: LocalGameSession) -> DecisionRequest:
    for _ in range(20):
        request = pending_request(session)
        if request.decision_type == "submit_stratagem_target_proposal":
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=request.request_id + ":d09-decline",
                payload=stratagem_decline_payload(),
            )
        elif request.decision_type == "use_stratagem":
            option = next(option for option in request.options if "decline" in option.option_id)
            status = session.submit_option(
                request_id=request.request_id,
                option_id=option.option_id,
                result_id=request.request_id + ":d09-decline",
            )
        else:
            return request
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    raise AssertionError("D09 native optional windows did not finish.")


def move_heavy_unit(
    session: LocalGameSession,
    *,
    advance: bool,
    distance: float,
    returning_model: bool = False,
    vertical: bool = False,
    flying: bool = False,
    expect_shooting: bool = True,
) -> None:
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        option_id=heavy_unit_id(session),
        result_id="d09-select-mover",
    )
    action = "advance" if advance else "normal_move"
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        option_id=action + ":fly_take_to_skies" if flying else action,
        result_id="d09-select-action",
    )
    request = pending_request(session)
    assert request.decision_type == "submit_movement_proposal"
    move = MovementProposalRequest.from_decision_request_payload(request.payload)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    moving_player = state.active_player_id
    assert moving_player is not None
    view = canonical_rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=move.unit_instance_id,
        owner_player_id=moving_player,
    )
    placement = RulesUnitPlacement.from_battlefield(
        view=view, battlefield_state=state.battlefield_state
    )
    long_model_id = next(
        (
            row.model_instance_id
            for row in placement.model_placements
            if row.unit_instance_id.endswith("leader")
        ),
        placement.model_placements[-1].model_instance_id,
    )
    witness = PathWitness.for_paths(
        leading_first_translation_paths(
            tuple(
                (
                    model.model_instance_id,
                    (
                        model.pose,
                        Pose.at(
                            model.pose.position.x,
                            model.pose.position.y
                            + (
                                2.5
                                if returning_model and model.model_instance_id == long_model_id
                                else distance / 2
                            ),
                            1.5 if vertical else 0,
                        ),
                        Pose.at(model.pose.position.x, model.pose.position.y + distance),
                    ),
                )
                for model in placement.model_placements
            ),
            dx=0,
            dy=distance,
        )
    )
    payload = validate_json_value(
        MovementProposalPayload(
            proposal_request_id=request.request_id,
            proposal_kind=move.proposal_kind,
            unit_instance_id=move.unit_instance_id,
            movement_phase_action=action,
            movement_mode="fly_take_to_skies" if flying else "advance" if advance else "normal",
            witness=witness,
        ).to_payload()
    )
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    malformed = cast(dict[str, JsonValue], json.loads(json.dumps(payload)))
    malformed["proposal_request_id"] = "d09-stale-proposal"
    status = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="d09-invalid-move", payload=malformed
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.to_persistence_payload() == checkpoint
    status = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="d09-valid-move", payload=payload
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    rows = [row for row in state.model_movement_history if row.turn_player_id == moving_player]
    assert len(rows) == len(placement.model_placements)
    for row in rows:
        expected = (
            4
            if returning_model and row.model_instance_id == long_model_id
            else (sqrt(distance * distance + 9) if vertical and not flying else distance)
        )
        assert abs(row.distance_inches - expected) < 1e-9
    if expect_shooting:
        decline_native_windows(session)
        assert bool(state.advanced_unit_states) is advance
        assert state.current_battle_phase is BattlePhase.SHOOTING, (
            state.current_battle_phase,
            status,
        )
    if advance:
        assert any(
            event.event_type == "advance_roll_resolved"
            for event in session.lifecycle.decision_controller.event_log.records
        )


def complete_heavy_attack(
    session: LocalGameSession,
    *,
    advance: bool,
    profile_id: str = "core-bolt-rifle:standard",
) -> list[dict[str, JsonValue]]:
    shooter_id = heavy_unit_id(session)
    state = session.lifecycle.state
    assert state is not None
    target_component = "army-beta:enemy" if shooter_id.endswith("mover") else "army-alpha:mover"
    target_id = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=target_component,
    ).unit_instance_id
    request = decline_native_windows(session)
    session.submit_option(
        request_id=request.request_id, option_id=shooter_id, result_id="d09-select-shooter"
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        option_id="assault" if advance else "normal",
        result_id="d09-select-shooting-type",
    )
    request = pending_request(session)
    proposal = _proposal_from_request(
        request=request,
        target_unit_id=target_id,
        weapon_profile_id=profile_id,
    )
    payload = validate_json_value(proposal.to_payload())
    before = session.to_persistence_payload()
    malformed = cast(dict[str, JsonValue], json.loads(json.dumps(payload)))
    malformed["proposal_request_id"] = "d09-stale-shooting"
    status = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="d09-invalid-shot", payload=malformed
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.to_persistence_payload() == before
    status = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="d09-valid-shot", payload=payload
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    for _ in range(60):
        events = session.lifecycle.decision_controller.event_log.records
        if any(event.event_type == "attack_sequence_completed" for event in events):
            break
        submit_fixture_request(session, pending_request(session))
    events = session.lifecycle.decision_controller.event_log.records
    assert any(event.event_type == "attack_sequence_completed" for event in events)
    state = session.lifecycle.state
    assert state is not None
    assert any(row.unit_instance_id == shooter_id for row in state.ranged_attack_history_records)
    accepted = next(
        event.payload for event in events if event.event_type == "shooting_declaration_accepted"
    )
    assert isinstance(accepted, dict)
    return cast(list[dict[str, JsonValue]], accepted["attack_pools"])


def assert_heavy_checkpoint(session: LocalGameSession) -> LocalGameSession:
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    fork = session.fork()
    assert restored.to_persistence_payload() == fork.to_persistence_payload() == checkpoint
    assert restored.lifecycle is not session.lifecycle
    assert fork.lifecycle is not session.lifecycle
    assert fork.lifecycle.state is not session.lifecycle.state
    for role in PrincipalRole:
        players = (
            ("player-a", "player-b")
            if role in {PrincipalRole.PLAYER, PrincipalRole.COACH}
            else (None,)
        )
        for player in players:
            viewer = AuthenticatedPrincipal(
                principal_id=f"d09-{role.value}-{player}", role=role, player_id=player
            ).bind_to_session(player_ids=("player-a", "player-b"))
            assert restored.view_for_context(viewer=viewer) == session.view_for_context(
                viewer=viewer
            )
            assert restored.events_since_for_context(
                EventStreamCursor(), viewer=viewer
            ) == session.events_since_for_context(EventStreamCursor(), viewer=viewer)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="d09-heavy")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay
    return restored
