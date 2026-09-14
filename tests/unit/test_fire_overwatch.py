from __future__ import annotations

from typing import cast

import pytest
from tests.fire_overwatch_helpers import (
    ENEMIES,
    choose_enemy,
    choose_shooter,
    overwatch_session,
    pending_overwatch,
)

from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus, LifecycleStatusKind


def test_overwatch_discovery_requires_its_catalog_without_mutation() -> None:
    from warhammer40k_core.engine.core_movement_end_sequencing import core_movement_end_candidates
    from warhammer40k_core.engine.phase import GameLifecycleError
    from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_stratagem_index
    from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
    from warhammer40k_core.engine.turn_end_hooks import TurnEndRequestContext

    session = overwatch_session()
    state = session.lifecycle.state
    assert state is not None
    before = session.lifecycle.to_payload()
    context = TurnEndRequestContext(
        state=state,
        decisions=session.lifecycle.decision_controller,
        completed_phase=BattlePhase.MOVEMENT,
    )
    with pytest.raises(GameLifecycleError, match="requires the army catalog"):
        core_movement_end_candidates(
            context,
            indexes={player: eleventh_edition_stratagem_index() for player in state.player_ids},
            cost_modifiers=StratagemCostModifierRegistry.empty(),
        )
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize("moved", [False, True])
@pytest.mark.parametrize("enemy", ENEMIES)
def test_phase_end_overwatch_offers_every_eligible_enemy(moved: bool, enemy: str) -> None:
    session = overwatch_session(moved=moved)
    request = pending_overwatch(session)
    assert isinstance(request.payload, dict)
    proposal = cast(dict[str, object], request.payload["proposal_request"])
    context = cast(dict[str, object], proposal["context"])
    assert context["trigger_payload"] == {
        "timing_window_id": "fire-overwatch-end-movement-round-01-player-player-a",
        "trigger_window": "end_opponent_movement_phase",
    }
    status = choose_shooter(session, request)
    request = _require_request(status)
    assert request is not None
    assert request.decision_type == "submit_shooting_declaration"
    assert isinstance(request.payload, dict)
    proposal = cast(dict[str, object], request.payload["proposal_request"])
    candidates = cast(list[dict[str, object]], proposal["target_candidates"])
    assert {c["target_unit_instance_id"] for c in candidates if c["is_legal"]} == set(ENEMIES)
    assert all(c["shooting_types"] == ["snap"] for c in candidates if c["is_legal"])
    status = choose_enemy(session, request, enemy)
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    state = session.lifecycle.state
    assert state is not None
    assert state.command_point_total("player-a") == 0
    assert len(state.stratagem_use_records) == 1
    assert state.current_battle_phase is BattlePhase.MOVEMENT


@pytest.mark.parametrize("checkpoint", ["stratagem", "declaration", "attacks"])
@pytest.mark.parametrize("enemy", ENEMIES)
def test_overwatch_restore_replay_and_phase_end_continuation(checkpoint: str, enemy: str) -> None:
    from tests.fire_overwatch_helpers import finish_overwatch

    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus

    session = overwatch_session(cp=2, attacks=18)
    request = pending_overwatch(session)
    initial = session.lifecycle.to_payload()
    if checkpoint != "stratagem":
        status = choose_shooter(session, request)
        request = _require_request(status)
        assert request is not None
        if checkpoint == "attacks":
            status = choose_enemy(session, request, enemy)
    restored = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
    for candidate in (session, restored):
        pending = candidate.lifecycle.decision_controller.queue.pending_requests
        assert pending
        request = pending[0]
        if checkpoint == "stratagem":
            status = choose_shooter(candidate, request)
            request = _require_request(status)
            assert request is not None
        if checkpoint != "attacks":
            status = choose_enemy(candidate, request, enemy)
        else:
            status = candidate.advance_until_decision_or_terminal()
        finish_overwatch(candidate, status)
        state = candidate.lifecycle.state
        assert state is not None
        assert state.out_of_phase_shooting_state is None
        candidate.advance_until_decision_or_terminal()
        assert state.current_battle_phase is BattlePhase.SHOOTING
        assert state.active_player_id == "player-b"
        assert state.command_point_total("player-a") == 1
        assert len(state.stratagem_use_records) == 1
        assert (
            len(
                [
                    r
                    for r in candidate.lifecycle.decision_controller.records
                    if r.request.decision_type == "submit_stratagem_target_proposal"
                ]
            )
            == 1
        )
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            cursor=EventStreamCursor(0), viewer_player_id=viewer
        ) == session.events_since(cursor=EventStreamCursor(0), viewer_player_id=viewer)
    artifact = ReplayArtifact.capture(
        artifact_id="order45:replay",
        initial_lifecycle_payload=initial,
        final_lifecycle=session.lifecycle,
    )
    assert (
        ReplayRunner.from_payload(artifact.to_payload()).run().status is ReplayRunStatus.REPRODUCED
    )


@pytest.mark.parametrize("cp", [0, 1])
def test_decline_and_unaffordable_overwatch_do_not_repeat_or_spend(cp: int) -> None:
    from warhammer40k_core.engine.stratagems import stratagem_decline_payload

    session = overwatch_session(cp=cp)
    if cp:
        request = pending_overwatch(session)
        session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="order45:decline",
            payload=stratagem_decline_payload(),
        )
    session.advance_until_decision_or_terminal()
    state = session.lifecycle.state
    assert state is not None
    assert state.current_battle_phase is BattlePhase.SHOOTING
    assert state.command_point_total("player-a") == cp
    assert state.stratagem_use_records == []
    assert state.out_of_phase_shooting_state is None


@pytest.mark.parametrize(
    "fault",
    ["malformed", "wrong-player", "round", "phase", "occurrence", "trigger", "unknown-shooter"],
)
def test_stratagem_submission_drift_fails_before_recording(fault: str) -> None:
    from copy import deepcopy
    from dataclasses import replace

    from tests.fire_overwatch_helpers import shooter_proposal

    from warhammer40k_core.engine.event_log import validate_json_value

    session = overwatch_session()
    request = pending_overwatch(session)
    proposal = shooter_proposal(request)
    if fault == "wrong-player":
        proposal = replace(proposal, context=replace(proposal.context, player_id="player-b"))
    elif fault == "round":
        proposal = replace(proposal, context=replace(proposal.context, battle_round=2))
    elif fault == "phase":
        proposal = replace(proposal, context=replace(proposal.context, phase=BattlePhase.SHOOTING))
    elif fault == "occurrence":
        proposal = replace(
            proposal, context=replace(proposal.context, timing_window_id="other-window")
        )
    elif fault == "trigger":
        proposal = replace(
            proposal, context=replace(proposal.context, trigger_payload={"unexpected": "data"})
        )
    elif fault == "unknown-shooter":
        assert proposal.target_binding is not None
        proposal = replace(
            proposal,
            target_binding=replace(proposal.target_binding, target_unit_instance_id="unknown-unit"),
        )
    payload = {} if fault == "malformed" else {"proposal": proposal.to_payload()}
    before = deepcopy(session.lifecycle.to_payload())
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order45:bad-source",
        payload=validate_json_value(payload),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize("late", [False, True])
@pytest.mark.parametrize(
    "fault",
    ["titanic", "engaged", "off-battlefield", "destroyed", "no-targets", "action", "battle-shock"],
)
def test_shooter_ineligibility_filters_window_or_rejects_proposal(fault: str, late: bool) -> None:
    from copy import deepcopy

    from tests.core_stratagem_helpers import (
        _move_unit_to_reserves,
        _replace_unit_keywords,
        _replace_unit_poses,
    )
    from tests.fire_overwatch_helpers import SHOOTER

    from warhammer40k_core.engine.activity_restrictions import build_activity_restriction
    from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
    from warhammer40k_core.engine.effects import EffectExpiration
    from warhammer40k_core.geometry.pose import Pose

    session = overwatch_session()
    request = pending_overwatch(session) if late else None
    state = session.lifecycle.state
    assert state is not None
    if fault == "titanic":
        _replace_unit_keywords(state, unit_instance_id=SHOOTER, keywords=("INFANTRY", "TITANIC"))
    elif fault == "engaged":
        _replace_unit_poses(state, unit_instance_id=ENEMIES[0], poses=(Pose.at(11.5, 10),))
    elif fault == "off-battlefield":
        _move_unit_to_reserves(session.lifecycle, player_id="player-a", unit_instance_id=SHOOTER)
    elif fault == "destroyed":
        army = state.army_definition_for_player("player-a")
        assert army is not None
        model = army.unit_by_id(SHOOTER).own_models[0]
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=SHOOTER,
            model_instance_id=model.model_instance_id,
            damage=99,
            damage_kind=DamageKind.NORMAL,
        )
    elif fault == "battle-shock":
        from warhammer40k_core.engine.battle_shock import BattleShockedUnitState

        army = state.army_definition_for_player("player-a")
        assert army is not None
        unit = army.unit_by_id(SHOOTER)
        state.replace_battle_shock_state(
            (
                [SHOOTER],
                [
                    BattleShockedUnitState(
                        player_id="player-a",
                        unit_instance_id=SHOOTER,
                        model_instance_ids=tuple(
                            model.model_instance_id for model in unit.own_models
                        ),
                        source_result_id="order45:preexisting-battle-shock",
                        battle_round_started=state.battle_round,
                    )
                ],
            )
        )
    elif fault == "no-targets":
        for index, enemy in enumerate(ENEMIES):
            _replace_unit_poses(state, unit_instance_id=enemy, poses=(Pose.at(50, 10 + index * 5),))
    else:
        state.record_persisting_effect(
            build_activity_restriction(
                owner_player_id="player-a",
                target_unit_instance_ids=(SHOOTER,),
                activity="started_action",
                activity_id="order45:action",
                battle_round=1,
                phase=BattlePhase.MOVEMENT,
                expiration=EffectExpiration.end_turn(battle_round=1, player_id="player-b"),
            )
        )
    if request is None and fault in {
        "titanic",
        "engaged",
        "off-battlefield",
        "destroyed",
        "action",
    }:
        status = session.advance_until_decision_or_terminal()
        pending = status.decision_request
        if pending is not None and pending.decision_type == "submit_stratagem_target_proposal":
            assert isinstance(pending.payload, dict)
            proposal = cast(dict[str, object], pending.payload["proposal_request"])
            assert proposal["stratagem_id"] != "fire-overwatch"
        assert not state.stratagem_use_records
        return
    if request is None:
        request = pending_overwatch(session)
    before = deepcopy(session.lifecycle.to_payload())
    status = choose_shooter(session, request)
    assert status.status_kind is LifecycleStatusKind.INVALID, status
    assert session.lifecycle.to_payload() == before
    assert state.command_point_total("player-a") == 1


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("protection", ["overwatch", "runtime-range"])
@pytest.mark.parametrize("late", [False, True])
def test_protected_enemy_stays_excluded_before_and_after_shooter_selection(
    protection: str, late: bool, attached: bool
) -> None:
    from copy import deepcopy

    from tests.fire_overwatch_helpers import SHOOTER
    from tests.generic_modifier_helpers import generic_effect
    from tests.phase13b_shooting_declaration_helpers import _proposal_from_request

    from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    session = overwatch_session(attached=attached)
    request = pending_overwatch(session)
    state = session.lifecycle.state
    assert state is not None
    target_id = rules_unit_view_by_id(state=state, unit_instance_id=ENEMIES[0]).unit_instance_id
    shooter_id = rules_unit_view_by_id(state=state, unit_instance_id=SHOOTER).unit_instance_id
    declaration = None
    if late:
        status = choose_shooter(session, request)
        request = _require_request(status)
        assert request is not None
        declaration = _proposal_from_request(request=request, target_unit_id=target_id)
    if protection == "overwatch":
        effect = PersistingEffect(
            effect_id="order45:protection",
            source_rule_id="test:order45:protection",
            owner_player_id="player-b",
            target_unit_instance_ids=(ENEMIES[0],),
            started_battle_round=1,
            started_phase=BattlePhase.MOVEMENT,
            expiration=EffectExpiration.end_turn(battle_round=1, player_id="player-b"),
            effect_payload={"fire_overwatch_forbidden": True},
        )
    else:
        # Generic RuleIR persists the canonical target binding; the legacy
        # movement-grant protection above can be bound to a physical component.
        effect = generic_effect(
            effect_id="order45:protection",
            owner_player_id="player-b",
            target_unit_instance_ids=(target_id,),
            target_kind="this_unit",
            effect_kind="set_contextual_status",
            parameters={
                "status": "shooting_target_range_restriction",
                "targeting_max_range_inches": 5,
            },
        )
    state.record_persisting_effect(effect)
    if late:
        assert declaration is not None
        before = deepcopy(session.lifecycle.to_payload())
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="order45:protected-target",
            payload=validate_json_value(declaration.to_payload()),
        )
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert session.lifecycle.to_payload() == before
    else:
        status = choose_shooter(session, request)
        request = _require_request(status)
        assert request is not None
        assert isinstance(request.payload, dict)
        proposal = cast(dict[str, object], request.payload["proposal_request"])
        candidates = cast(list[dict[str, object]], proposal["target_candidates"])
        assert {c["target_unit_instance_id"] for c in candidates if c["is_legal"]} == {ENEMIES[1]}
        assert state.out_of_phase_shooting_state is not None
        assert state.out_of_phase_shooting_state.selected_unit_instance_id == shooter_id
    assert choose_enemy(session, request, ENEMIES[1]).status_kind is not LifecycleStatusKind.INVALID


def _require_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.decision_request is not None, status
    return status.decision_request


@pytest.mark.parametrize("distance", [23.999, 24.0, 24.001])
def test_snap_24_inch_boundary_is_shared_by_offer_and_submission(distance: float) -> None:
    from tests.core_stratagem_helpers import _replace_unit_poses
    from tests.fire_overwatch_helpers import SHOOTER

    from warhammer40k_core.geometry.pose import Pose

    session = overwatch_session(weapon_range=48)
    state = session.lifecycle.state
    assert state is not None
    army = state.army_definition_for_player("player-a")
    assert army is not None
    radius = army.unit_by_id(SHOOTER).own_models[0].geometry.parts[0].radius_x_inches
    _replace_unit_poses(
        state, unit_instance_id=ENEMIES[0], poses=(Pose.at(10 + 2 * radius + distance, 10),)
    )
    request = _require_request(choose_shooter(session, pending_overwatch(session)))
    assert isinstance(request.payload, dict)
    proposal = cast(dict[str, object], request.payload["proposal_request"])
    candidates = cast(list[dict[str, object]], proposal["target_candidates"])
    legal = {c["target_unit_instance_id"] for c in candidates if c["is_legal"]}
    assert (ENEMIES[0] in legal) == (distance <= 24)
    if distance <= 24:
        assert (
            choose_enemy(session, request, ENEMIES[0]).status_kind
            is not LifecycleStatusKind.INVALID
        )
    else:
        from copy import deepcopy
        from dataclasses import replace

        from tests.phase13b_shooting_declaration_helpers import _proposal_from_request

        from warhammer40k_core.engine.event_log import validate_json_value

        declaration = _proposal_from_request(request=request, target_unit_id=ENEMIES[1])
        declaration = replace(
            declaration,
            declarations=(
                replace(declaration.declarations[0], target_unit_instance_id=ENEMIES[0]),
            ),
        )
        before = deepcopy(session.lifecycle.to_payload())
        status = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="order45:outside-snap-range",
            payload=validate_json_value(declaration.to_payload()),
        )
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert session.lifecycle.to_payload() == before


def test_snap_range_is_measured_from_rules_unit_instead_of_firing_model() -> None:
    from tests.core_stratagem_helpers import _replace_unit_poses
    from tests.fire_overwatch_helpers import SHOOTER
    from tests.phase13b_shooting_declaration_helpers import _proposal_from_request

    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.geometry.pose import Pose

    session = overwatch_session(shooter_models=2, weapon_range=48)
    state = session.lifecycle.state
    assert state is not None
    _replace_unit_poses(state, unit_instance_id=ENEMIES[0], poses=(Pose.at(37, 10),))
    request = _require_request(choose_shooter(session, pending_overwatch(session)))
    proposal = _proposal_from_request(request=request, target_unit_id=ENEMIES[0])
    army = state.army_definition_for_player("player-a")
    assert army is not None
    assert (
        proposal.declarations[0].attacker_model_instance_id
        == army.unit_by_id(SHOOTER).own_models[0].model_instance_id
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order45:distant-firing-model",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID


@pytest.mark.parametrize("distance", [23.51, 23.999, 24.0, 24.001])
def test_r45_001_snap_boundary_uses_other_attached_component(distance: float) -> None:
    _assert_attached_snap_boundary(distance=distance)


@pytest.mark.parametrize("restriction", ["weapon-range", "model-visibility", "removed-component"])
def test_r45_001_group_range_preserves_weapon_visibility_and_present_model_limits(
    restriction: str,
) -> None:
    _assert_attached_snap_boundary(distance=23.51, restriction=restriction)


def _assert_attached_snap_boundary(*, distance: float, restriction: str | None = None) -> None:
    from dataclasses import replace

    from tests.core_stratagem_helpers import _replace_unit_poses
    from tests.fire_overwatch_helpers import SHOOTER
    from tests.phase13b_shooting_declaration_helpers import (
        _display_geometry,
        _proposal_from_declarations,
    )

    from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
    from warhammer40k_core.engine.battlefield_state import geometry_model_for_placement
    from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.engine.shooting_types import ShootingType
    from warhammer40k_core.engine.weapon_declaration import WeaponDeclaration
    from warhammer40k_core.geometry.pose import Pose
    from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition

    session = overwatch_session(
        attached=True, weapon_range=24 if restriction == "weapon-range" else 48
    )
    state = session.lifecycle.state
    assert state is not None
    army = state.army_definition_for_player("player-a")
    enemy_army = state.army_definition_for_player("player-b")
    assert army is not None
    assert enemy_army is not None
    near_id = "army-alpha:leader"
    far_id = SHOOTER
    near_model = army.unit_by_id(near_id).own_models[0]
    far_model = army.unit_by_id(far_id).own_models[0]
    target_model = enemy_army.unit_by_id(ENEMIES[0]).own_models[0]
    target_x = (
        12.15
        + distance
        + near_model.geometry.parts[0].radius_x_inches
        + target_model.geometry.parts[0].radius_x_inches
    )
    far_x = (
        10
        + near_model.geometry.parts[0].radius_x_inches
        - far_model.geometry.parts[0].radius_x_inches
    )
    for unit_id, pose in (
        (far_id, Pose.at(far_x, 10)),
        (near_id, Pose.at(12.15, 10)),
        (ENEMIES[0], Pose.at(target_x, 10)),
        ("army-beta:enemy-leader", Pose.at(target_x + 2, 10)),
    ):
        _replace_unit_poses(state, unit_instance_id=unit_id, poses=(pose,))
    assert state.battlefield_state is not None
    battlefield = state.battlefield_state
    target_geometry = geometry_model_for_placement(
        model=target_model,
        placement=battlefield.model_placement_by_id(target_model.model_instance_id),
    )
    near_distance = geometry_model_for_placement(
        model=near_model, placement=battlefield.model_placement_by_id(near_model.model_instance_id)
    ).range_to(target_geometry)
    assert abs(near_distance - distance) <= 1e-9
    far_distance = geometry_model_for_placement(
        model=far_model, placement=battlefield.model_placement_by_id(far_model.model_instance_id)
    ).range_to(target_geometry)
    assert abs(far_distance - (distance + 2.15)) <= 1e-9
    assert far_distance > 24
    if restriction == "model-visibility":
        display = _display_geometry(
            center_x_inches=11, center_y_inches=10, width_inches=0.1, depth_inches=1.8
        )
        wall = TerrainFeatureDefinition(
            feature_id="r45-001:wall",
            feature_kind=TerrainFeatureKind.HILLS,
            footprint_center_x_inches=11,
            footprint_center_y_inches=10,
            footprint_width_inches=0.1,
            footprint_depth_inches=1.8,
            rules_footprint_polygon=display.footprint_polygon,
            display_geometry=display,
            walls=(TerrainWallDefinition("wall", 11, 10, 0, 0.1, 1.8, 5),),
            source_id="test:r45-001:wall",
        )
        state.replace_battlefield_state(replace(battlefield, terrain_features=(wall,)))
    if restriction == "removed-component":
        apply_damage_to_model(
            state=state,
            target_unit_instance_id=near_id,
            model_instance_id=near_model.model_instance_id,
            damage=99,
            damage_kind=DamageKind.NORMAL,
        )
    if distance == 23.51 and restriction is None:
        # The unarmed Leader supplies range; only the distant Bodyguard can shoot.
        _replace_unit_poses(state, unit_instance_id=ENEMIES[1], poses=(Pose.at(55, 16),))
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.lifecycle import GameLifecycle

    session = LocalGameSession(lifecycle=GameLifecycle.from_payload(session.lifecycle.to_payload()))
    state = session.lifecycle.state
    assert state is not None
    window = pending_overwatch(session)
    initial = session.lifecycle.to_payload()
    request = _require_request(choose_shooter(session, window))
    assert isinstance(request.payload, dict)
    raw = cast(dict[str, object], request.payload["proposal_request"])
    weapons = cast(list[dict[str, object]], raw["available_weapons"])
    weapon = next(w for w in weapons if w["model_instance_id"] == far_model.model_instance_id)
    target_id = rules_unit_view_by_id(state=state, unit_instance_id=ENEMIES[0]).unit_instance_id
    candidates = cast(list[dict[str, object]], raw["target_candidates"])
    candidate = next(
        c
        for c in candidates
        if c["target_unit_instance_id"] == target_id
        and c["weapon_instance_id"] == weapon["weapon_instance_id"]
    )
    legal = distance <= 24 and restriction is None
    assert candidate["is_legal"] is legal, candidate
    assert candidate["shooting_types"] == (["snap"] if legal else [])
    proposal = _proposal_from_declarations(
        request=request,
        declarations=(
            WeaponDeclaration(
                attacker_model_instance_id=far_model.model_instance_id,
                weapon_instance_id=cast(str, weapon["weapon_instance_id"]),
                wargear_id=cast(str, weapon["wargear_id"]),
                weapon_profile_id=cast(str, weapon["weapon_profile_id"]),
                target_unit_instance_id=target_id,
                shooting_type=ShootingType.SNAP,
            ),
        ),
    )
    before = session.lifecycle.to_payload()
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="r45-001:far-component-shot",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert (status.status_kind is not LifecycleStatusKind.INVALID) is legal, status
    if not legal:
        assert session.lifecycle.to_payload() == before

    elif distance == 24.0:
        from tests.fire_overwatch_helpers import finish_overwatch

        from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus

        finish_overwatch(session, status)
        artifact = ReplayArtifact.capture(
            artifact_id="r45-001:boundary-replay",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        )
        assert (
            ReplayRunner.from_payload(artifact.to_payload()).run().status
            is ReplayRunStatus.REPRODUCED
        )
        session.advance_until_decision_or_terminal()
        restored = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
        assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()


@pytest.mark.parametrize(
    "fault",
    [
        "split-targets",
        "normal",
        "unknown-target",
        "friendly-target",
        "stale-request",
        "source-request",
        "visibility",
        "malformed",
    ],
)
def test_shooting_proposal_faults_preserve_pending_request_and_state(fault: str) -> None:
    from copy import deepcopy
    from dataclasses import replace

    from tests.fire_overwatch_helpers import SHOOTER
    from tests.phase13b_shooting_declaration_helpers import _proposal_from_request

    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.shooting_types import ShootingType

    session = overwatch_session(shooter_models=2)
    request = _require_request(choose_shooter(session, pending_overwatch(session)))
    proposal = _proposal_from_request(request=request, target_unit_id=ENEMIES[0])
    assert isinstance(request.payload, dict)
    raw = cast(dict[str, object], request.payload["proposal_request"])
    first = proposal.declarations[0]
    if fault == "split-targets":
        weapons = cast(list[dict[str, object]], raw["available_weapons"])
        other = next(
            w
            for w in weapons
            if w["model_instance_id"] != first.attacker_model_instance_id
            and w["weapon_profile_id"] == first.weapon_profile_id
        )
        proposal = replace(
            proposal,
            declarations=(
                first,
                replace(
                    first,
                    attacker_model_instance_id=cast(str, other["model_instance_id"]),
                    weapon_instance_id=cast(str, other["weapon_instance_id"]),
                    target_unit_instance_id=ENEMIES[1],
                ),
            ),
        )
    elif fault == "normal":
        proposal = replace(
            proposal, declarations=(replace(first, shooting_type=ShootingType.NORMAL),)
        )
    elif fault in ("unknown-target", "friendly-target"):
        proposal = replace(
            proposal,
            declarations=(
                replace(
                    first,
                    target_unit_instance_id="unknown" if fault == "unknown-target" else SHOOTER,
                ),
            ),
        )
    elif fault == "stale-request":
        proposal = replace(proposal, proposal_request_id="stale")
    elif fault == "source-request":
        proposal = replace(proposal, source_decision_request_id="stale")
    elif fault == "visibility":
        proposal = replace(proposal, visibility_cache_key="stale")
    before = deepcopy(session.lifecycle.to_payload())
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order45:bad-declaration",
        payload={} if fault == "malformed" else validate_json_value(proposal.to_payload()),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID, status
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize("blocked", [False, True])
def test_invisible_enemy_is_excluded_even_with_indirect_weapon(blocked: bool) -> None:
    from dataclasses import replace

    from tests.phase13b_shooting_declaration_helpers import _display_geometry

    from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
    from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition

    session = overwatch_session(indirect=True)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    if blocked:
        display = _display_geometry(
            center_x_inches=15, center_y_inches=10, width_inches=0.1, depth_inches=2.5
        )
        wall = TerrainFeatureDefinition(
            feature_id="order45:wall",
            feature_kind=TerrainFeatureKind.HILLS,
            footprint_center_x_inches=15,
            footprint_center_y_inches=10,
            footprint_width_inches=0.1,
            footprint_depth_inches=2.5,
            rules_footprint_polygon=display.footprint_polygon,
            display_geometry=display,
            walls=(TerrainWallDefinition("wall", 15, 10, 0, 0.1, 2.5, 5),),
            source_id="test:order45:wall",
        )
        state.replace_battlefield_state(replace(state.battlefield_state, terrain_features=(wall,)))
    request = _require_request(choose_shooter(session, pending_overwatch(session)))
    assert isinstance(request.payload, dict)
    proposal = cast(dict[str, object], request.payload["proposal_request"])
    candidates = cast(list[dict[str, object]], proposal["target_candidates"])
    assert {c["target_unit_instance_id"] for c in candidates if c["is_legal"]} == (
        {ENEMIES[1]} if blocked else set(ENEMIES)
    )


@pytest.mark.parametrize("attacks", [2, 18])
def test_attached_shooter_and_target_use_canonical_rules_unit_identities(attacks: int) -> None:
    from tests.fire_overwatch_helpers import SHOOTER, finish_overwatch

    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    session = overwatch_session(attached=True, attacks=attacks)
    state = session.lifecycle.state
    assert state is not None
    source = rules_unit_view_by_id(state=state, unit_instance_id=SHOOTER)
    target = rules_unit_view_by_id(state=state, unit_instance_id=ENEMIES[0])
    assert source.is_attached_rules_unit
    assert target.is_attached_rules_unit
    request = pending_overwatch(session)
    initial = session.lifecycle.to_payload()
    request = _require_request(choose_shooter(session, request))
    out = state.out_of_phase_shooting_state
    assert out is not None
    assert out.selected_unit_instance_id == source.unit_instance_id
    finish_overwatch(session, choose_enemy(session, request, target.unit_instance_id))
    use = state.stratagem_use_records[0]
    assert use.affected_unit_instance_ids == (source.unit_instance_id,)
    artifact = ReplayArtifact.capture(
        artifact_id="order45:attached",
        initial_lifecycle_payload=initial,
        final_lifecycle=session.lifecycle,
    )
    assert (
        ReplayRunner.from_payload(artifact.to_payload()).run().status is ReplayRunStatus.REPRODUCED
    )
    from warhammer40k_core.adapters.local_session import LocalGameSession

    session.advance_until_decision_or_terminal()
    restored = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
    assert state.current_battle_phase is BattlePhase.SHOOTING
    assert session.lifecycle.to_payload() == restored.lifecycle.to_payload()


@pytest.mark.parametrize("attacks", [2, 18])
def test_phase_end_snap_preserves_raw_six_no_hit_reroll_and_action_lock(attacks: int) -> None:
    from tests.fire_overwatch_helpers import SHOOTER, finish_overwatch

    from warhammer40k_core.engine.mission_action_eligibility import (
        MISSION_ACTION_UNIT_ALREADY_SHOT,
        mission_action_unit_ineligibility_reason,
    )
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

    session = overwatch_session(cp=2, attacks=attacks)
    request = _require_request(choose_shooter(session, pending_overwatch(session)))
    finish_overwatch(session, choose_enemy(session, request, ENEMIES[0]))
    hits: list[int] = []
    wounds = 0
    for event in session.lifecycle.decision_controller.event_log.records:
        if event.event_type != "dice_rolled":
            continue
        assert isinstance(event.payload, dict)
        spec = event.payload["spec"]
        assert isinstance(spec, dict)
        if spec["roll_type"] == "attack_sequence.hit":
            assert spec["reroll_forbidden_rule_ids"] == ["core:snap-shooting"]
            values = event.payload["values"]
            assert isinstance(values, list)
            assert type(values[0]) is int
            hits.append(values[0])
        elif spec["roll_type"] == "attack_sequence.wound":
            assert hits[-1] == 6
            wounds += 1
    assert any(3 <= raw <= 5 for raw in hits)
    assert wounds == hits.count(6)
    if attacks == 18:
        assert wounds > 0
    state = session.lifecycle.state
    assert state is not None
    if attacks == 2:
        assert state.current_battle_phase is BattlePhase.MOVEMENT
        assert (
            mission_action_unit_ineligibility_reason(
                state=state,
                player_id="player-a",
                unit_instance_id=SHOOTER,
                runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            )
            == MISSION_ACTION_UNIT_ALREADY_SHOT
        )
        session.advance_until_decision_or_terminal()
    assert state.current_battle_phase is BattlePhase.SHOOTING
    assert (
        mission_action_unit_ineligibility_reason(
            state=state,
            player_id="player-a",
            unit_instance_id=SHOOTER,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        is None
    )


@pytest.mark.parametrize("retained", [False, True])
def test_overwatch_target_scope_uses_current_living_or_retained_group_presence(
    retained: bool,
) -> None:
    from tests.fight_on_death_helpers import retain_destroyed_model_for_fixture

    from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model
    from warhammer40k_core.engine.fire_overwatch import fire_overwatch_target_unit_ids

    session = overwatch_session()
    state = session.lifecycle.state
    assert state is not None
    army = state.army_definition_for_player("player-b")
    assert army is not None
    model = army.unit_by_id(ENEMIES[0]).own_models[0]
    assert state.battlefield_state is not None
    placement = state.battlefield_state.model_placement_or_none(model.model_instance_id)
    assert placement is not None
    apply_damage_to_model(
        state=state,
        target_unit_instance_id=ENEMIES[0],
        model_instance_id=model.model_instance_id,
        damage=99,
        damage_kind=DamageKind.NORMAL,
    )
    if retained:
        retain_destroyed_model_for_fixture(
            state=state,
            placement=placement,
            effect_id="order45:retained-target",
            source_rule_id="test:order45:retention",
            source_phase=BattlePhase.MOVEMENT,
            decisions=session.lifecycle.decision_controller,
        )
    assert (ENEMIES[0] in fire_overwatch_target_unit_ids(state=state, player_id="player-a")) == (
        retained
    )
    request = _require_request(choose_shooter(session, pending_overwatch(session)))
    assert isinstance(request.payload, dict)
    proposal = cast(dict[str, object], request.payload["proposal_request"])
    candidates = cast(list[dict[str, object]], proposal["target_candidates"])
    legal = {c["target_unit_instance_id"] for c in candidates if c["is_legal"]}
    # The shared phase-end cleanup releases this Movement-scoped retention before
    # the Stratagem decision, so the declaration must use the current presence.
    from warhammer40k_core.engine.retained_model_presence import model_is_present_on_battlefield

    assert not model_is_present_on_battlefield(
        state=state, model_instance_id=model.model_instance_id
    )
    assert ENEMIES[0] not in legal
