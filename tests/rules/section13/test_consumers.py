"""Native producer-to-consumer scenes through the shared LocalGameSession facade."""

from dataclasses import replace
from typing import cast

import pytest

from tests.support.section02_fixtures import (
    AVENGERS,
    LORD_EXULTANT,
    MAULERFIEND,
    Section02Definitions,
)
from tests.support.section04_fixtures import (
    declare_shooting,
    finish_attacks,
    pending,
    shooting_payload,
    shooting_request,
    weapon_rows,
)
from tests.support.section09_fixtures import choose, events, movement_case, propose, select
from tests.support.section13_fixtures import area, feature, scene, shooting_session
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainFeatureKind
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification as C


def _r2_mixed_scene(
    definitions: Section02Definitions,
    kind: TerrainFeatureKind,
) -> tuple[LocalGameSession, GameState, UnitInstance, TerrainFeatureDefinition, tuple[Pose, ...]]:
    from tests.support.section03_fixtures import native_state
    from tests.support.section03_session import movement_session
    from tests.support.section09_fixtures import add_unit, attach_mission
    from tests.unit_keyword_helpers import with_model_keywords

    original = definitions.unit(AVENGERS)
    unit = replace(
        original,
        own_models=(
            with_model_keywords(original.own_models[0], keywords=("VEHICLE",)),
            *original.own_models[1:],
        ),
    )
    assert unit.own_model_ids() == original.own_model_ids()
    assert all(
        a.geometry == b.geometry for a, b in zip(unit.own_models, original.own_models, strict=True)
    )
    starts = tuple(Pose.at(12, 8 + 1.5 * i, 3) for i in range(len(unit.own_models)))
    state = native_state(
        definitions,
        unit,
        starts,
        enemy=definitions.unit(
            LORD_EXULTANT,
            identity="enemy",
            army_id="enemy",
        ),
    )
    attach_mission(state)
    add_unit(state, definitions.unit(LORD_EXULTANT, identity="spare"), (Pose.at(10, 30),))
    terrain = replace(
        feature(C.DENSE, x=16, y=16, width=12, depth=24, height=3, floor=True), feature_kind=kind
    )
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    state.mission_setup = replace(state.mission_setup, terrain_features=(terrain,))
    state.replace_battlefield_state(replace(state.battlefield_state, terrain_features=(terrain,)))
    # Complete native inventory/envelopes; only the first physical keyword is constructed.
    # Already-supported upper checkpoint, not legal admission/deployment/prior ascent.
    return movement_session(definitions, state), state, unit, terrain, starts


@pytest.mark.parametrize("keyword", ["SWARM", "INFANTRY"])
def test_r2_public_physical_swarm_and_dense_infantry_keep_upper_retry(
    section13_definitions: Section02Definitions,
    keyword: str,
) -> None:
    from tests.support.section03_fixtures import placement
    from tests.unit_keyword_helpers import with_unit_keywords

    session, state, unit = movement_case(section13_definitions, datasheet=LORD_EXULTANT)
    original_geometry = unit.own_models[0].geometry
    if keyword == "SWARM":
        # Constructed SWARM on unchanged native Lord envelope, never native Ripper admission.
        unit = with_unit_keywords(unit, keywords=("SWARM",))
        state.army_definitions[:] = [
            replace(
                a,
                units=tuple(
                    unit if u.unit_instance_id == unit.unit_instance_id else u for u in a.units
                ),
            )
            for a in state.army_definitions
        ]
    assert unit.own_models[0].geometry == original_geometry
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    kind = (
        TerrainFeatureKind.RUINS
        if keyword == "SWARM"
        else TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY
    )
    terrain = replace(feature(width=6, depth=6, height=3, floor=True), feature_kind=kind)
    state.mission_setup = replace(state.mission_setup, terrain_features=(terrain,))
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            terrain_features=(terrain,),
            placed_armies=tuple(
                replace(
                    a,
                    unit_placements=tuple(
                        placement(unit, (Pose.at(12, 10, 3),))
                        if p.unit_instance_id == unit.unit_instance_id
                        else p
                        for p in a.unit_placements
                    ),
                )
                for a in state.battlefield_state.placed_armies
            ),
        )
    )
    request = choose(session, select(session, unit), "normal_move")
    before = state.battlefield_state
    rejected = propose(session, request, unit, (Pose.at(17, 10, 3),), result_id="r2-overhang")
    assert rejected.status_kind is LifecycleStatusKind.INVALID, rejected.to_payload()
    assert state.battlefield_state == before
    assert not events(session, "movement_activation_completed")
    accepted = propose(
        session, pending(session), unit, (Pose.at(14, 10, 3),), result_id="r2-supported"
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted.to_payload()
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_by_id(unit.unit_instance_id).model_placements[
        0
    ].pose == Pose.at(14, 10, 3)
    assert len(events(session, "movement_activation_completed")) == 1
    assert pending(session).decision_type == "select_movement_unit"


@pytest.mark.parametrize(
    "kind", [TerrainFeatureKind.RUINS, TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY]
)
def test_r2_public_mixed_vehicle_upper_endpoint_rejects_atomically(
    section13_definitions: Section02Definitions,
    kind: TerrainFeatureKind,
) -> None:
    from tests.support.section13_fixtures import native_models
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.endpoint_placement import terrain_endpoint_placement_violation

    session, state, unit, terrain, starts = _r2_mixed_scene(section13_definitions, kind)
    request = choose(session, select(session, unit), "normal_move")
    before = state.battlefield_state
    ends = tuple(Pose.at(14, p.position.y, 3) for p in starts)
    rejected = propose(session, request, unit, ends, result_id="r2-borrowed")
    assert rejected.status_kind is LifecycleStatusKind.INVALID, rejected.to_payload()
    assert state.battlefield_state == before
    assert not events(session, "movement_activation_completed")
    assert pending(session).decision_type == "submit_movement_proposal"
    assert (
        terrain_endpoint_placement_violation(
            model=native_models(unit, ends)[0],
            unit=unit,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            terrain_features=(terrain,),
            violation_code="r2:mixed",
            placement_label="same physical model",
        )
        is not None
    )


def test_r2_public_mixed_rejection_then_qualified_ground_retry(
    section13_definitions: Section02Definitions,
) -> None:
    from tests.support.section13_fixtures import native_models
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalPayload,
        MovementProposalRequest,
    )
    from warhammer40k_core.geometry.pathing import PathWitness

    session, state, unit, _, starts = _r2_mixed_scene(
        section13_definitions, TerrainFeatureKind.RUINS
    )
    request = choose(session, select(session, unit), "normal_move")
    before = state.battlefield_state
    assert before is not None
    rejected = propose(session, request, unit, tuple(Pose.at(14, p.position.y, 3) for p in starts))
    assert rejected.status_kind is LifecycleStatusKind.INVALID, rejected.to_payload()
    assert state.battlefield_state == before
    assert not events(session, "movement_activation_completed")
    request = pending(session)
    context = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert context.context is not None
    mode = context.context["movement_mode"]
    action = context.movement_phase_action
    assert isinstance(mode, str)
    assert isinstance(action, str)
    outside_x = 10 - native_models(unit, starts)[0].base.max_radius() - 0.1
    ends = (Pose.at(outside_x, 8, 0), Pose.at(11.5, 9.5, 3), *starts[2:])
    paths = tuple(
        (
            model.model_instance_id,
            (start, Pose.at(outside_x, 8, 3), end) if i == 0 else (start, end),
        )
        for i, (model, start, end) in enumerate(zip(unit.own_models, starts, ends, strict=True))
    )
    accepted = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="r2-ground-retry",
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=context.proposal_kind,
                unit_instance_id=unit.unit_instance_id,
                movement_phase_action=action,
                movement_mode=mode,
                fall_back_mode=None,
                witness=PathWitness.for_paths(paths),
            ).to_payload()
        ),
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted.to_payload()
    after = state.battlefield_state
    assert after is not None
    assert (
        tuple(p.pose for p in after.unit_placement_by_id(unit.unit_instance_id).model_placements)
        == ends
    )
    assert len(events(session, "movement_activation_completed")) == 1
    assert pending(session).decision_type == "select_movement_unit"
    for army in before.placed_armies:
        for placed in army.unit_placements:
            if placed.unit_instance_id != unit.unit_instance_id:
                assert after.unit_placement_by_id(placed.unit_instance_id) == placed


def test_repaired_native_dense_upper_surface_rejects_overhang_then_continues(
    section13_definitions: Section02Definitions,
) -> None:
    from tests.support.section03_fixtures import placement
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.endpoint_placement import terrain_endpoint_placement_violation
    from warhammer40k_core.geometry.terrain import TerrainFeatureKind

    session, state, unit = movement_case(section13_definitions, datasheet=LORD_EXULTANT)
    assert state.battlefield_state is not None
    assert state.mission_setup is not None
    f = replace(
        feature(width=6, depth=6, floor=True, height=3),
        feature_kind=TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
    )
    # Fresh checkpoint starts the unchanged native model on a supported upper floor.
    # This does not claim prior ascent, setup admission or mission history.
    state.mission_setup = replace(state.mission_setup, terrain_features=(f,))
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            terrain_features=(f,),
            placed_armies=tuple(
                replace(
                    a,
                    unit_placements=tuple(
                        placement(unit, (Pose.at(12, 10, 3),))
                        if p.unit_instance_id == unit.unit_instance_id
                        else p
                        for p in a.unit_placements
                    ),
                )
                if a.player_id == "owner"
                else a
                for a in state.battlefield_state.placed_armies
            ),
        )
    )
    request = choose(session, select(session, unit), "normal_move")
    before = state.battlefield_state
    invalid = propose(session, request, unit, (Pose.at(17, 10, 3),))
    assert invalid.status_kind is LifecycleStatusKind.INVALID, invalid.to_payload()
    assert state.battlefield_state == before
    assert not events(session, "movement_activation_completed")
    accepted = propose(
        session, pending(session), unit, (Pose.at(14, 10, 3),), result_id="supported"
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted.to_payload()
    after = state.battlefield_state
    assert after is not None
    endpoint = after.unit_placement_by_id(unit.unit_instance_id).model_placements[0].pose
    assert endpoint == Pose.at(14, 10, 3)
    from tests.support.section13_fixtures import native_models

    assert (
        terrain_endpoint_placement_violation(
            model=native_models(unit, (endpoint,))[0],
            unit=unit,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            terrain_features=(f,),
            violation_code="s13:shared",
            placement_label="native shared endpoint",
        )
        is None
    )
    assert len(events(session, "movement_activation_completed")) == 1
    assert pending(session).decision_type == "select_movement_unit"
    assert after.unit_placement_by_id("section02:spare") == before.unit_placement_by_id(
        "section02:spare"
    )


@pytest.mark.parametrize("sheet", [LORD_EXULTANT, MAULERFIEND])
@pytest.mark.parametrize("classification", [C.EXPOSED, C.LIGHT, C.DENSE])
def test_native_movement_category_gate_rejection_retry_and_owner_mutation(
    section13_definitions: Section02Definitions, sheet: str, classification: C
) -> None:
    d = section13_definitions
    session, state, unit = movement_case(d, datasheet=sheet)
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    f = feature(classification, x=13 if sheet == LORD_EXULTANT else 14, width=0.25)
    state.mission_setup = replace(state.mission_setup, terrain_features=(f,))
    state.replace_battlefield_state(replace(state.battlefield_state, terrain_features=(f,)))
    request = choose(session, select(session, unit), "normal_move")
    before = state.battlefield_state
    result = propose(session, request, unit, (Pose.at(16 if sheet == LORD_EXULTANT else 18, 10),))
    permitted = sheet == LORD_EXULTANT or classification is not C.DENSE
    assert (result.status_kind is not LifecycleStatusKind.INVALID) is permitted, result.to_payload()
    if not permitted:
        assert state.battlefield_state == before
        assert not events(session, "movement_activation_completed")
        # Legal route goes around the narrow feature instead of tunnelling through.
        result = propose(
            session, pending(session), unit, (Pose.at(9, 10),), result_id="legal-retry"
        )
        assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    after = state.battlefield_state
    assert after is not None
    assert after != before
    assert after.unit_placement_by_id("section02:spare") == before.unit_placement_by_id(
        "section02:spare"
    )
    assert after.unit_placement_by_id("enemy:enemy") == before.unit_placement_by_id("enemy:enemy")
    complete = events(session, "movement_activation_completed")
    assert len(complete) == 1
    assert complete[0]["unit_instance_id"] == unit.unit_instance_id
    assert pending(session).decision_type == "select_movement_unit"
    assert session.view(viewer_player_id="owner")
    assert session.events_since(EventStreamCursor(), viewer_player_id="opponent")


@pytest.mark.parametrize("cover", [False, True])
def test_native_cover_producer_changes_actual_hit_ballistic_skill_and_continues(
    section13_definitions: Section02Definitions, cover: bool
) -> None:
    d = section13_definitions
    state, attacker, target = scene(d, target_x=20, areas=(area(),) if cover else ())
    session = shooting_session(d, state)
    request = shooting_request(session, attacker.unit_instance_id)
    rows = [
        r
        for r in weapon_rows(request)
        if cast(str, r["wargear_id"]).endswith(":avenger-shuriken-catapult")
    ][:1]
    assert len(rows) == 1
    declare_shooting(session, request, rows, [target.unit_instance_id])
    finish_attacks(session)
    records = session.lifecycle.decision_controller.event_log.records
    complete = next(e for e in records if e.event_type == "attack_sequence_completed")
    seq = completed_attack_sequence(
        event_records=records,
        sequence_id=cast(str, cast(dict[str, JsonValue], complete.payload)["sequence_id"]),
    )
    assert seq.is_complete
    assert len(seq.attack_pools) == 1
    # These are actual resolved rolls after the terrain producer populated the pool.
    hit_steps = [
        e.payload
        for e in records
        if e.event_type == "attack_sequence_step"
        and isinstance(e.payload, dict)
        and e.payload.get("step") == "hit"
    ]
    assert hit_steps, [e.to_payload() for e in records if e.event_type == "attack_sequence_step"]
    for step in hit_steps:
        assert isinstance(step, dict)
        assert cast(dict[str, JsonValue], step["payload"])["target_number"] == seq.attack_pools[
            0
        ].weapon_profile.skill.final + int(cover)
    assert pending(session).decision_type == "select_shooting_unit"
    assert state.unit_made_ranged_attacks_current_or_previous_turn(
        unit_instance_id=attacker.unit_instance_id
    )
    assert session.events_since(EventStreamCursor(), viewer_player_id="owner")


def test_faq44_attacker_specific_cover_reaches_native_grouping_with_physical_provenance(
    section13_definitions: Section02Definitions,
) -> None:
    d = section13_definitions
    # Two native bearers see the same target from different angles. A partial Light
    # screen obstructs the first while the second has an unobstructed line.
    state, attacker, target = scene(
        d, target_x=20, features=(feature(C.LIGHT, x=19, y=10, width=0.25, depth=8, height=2.2),)
    )
    # Constructed already-placed, post-casualty incoherency checkpoint. Shooting
    # does not move this unit or certify a prior casualty/Movement history.
    from tests.support.section03_fixtures import placement

    assert state.battlefield_state is not None
    poses = tuple(
        Pose.at(10, 10) if i == 0 else Pose.at(20, 18 + 1.5 * i)
        for i in range(len(attacker.own_models))
    )
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=tuple(
                replace(a, unit_placements=(placement(attacker, poses),))
                if a.player_id == "owner"
                else a
                for a in state.battlefield_state.placed_armies
            ),
        )
    )
    session = shooting_session(d, state)
    request = shooting_request(session, attacker.unit_instance_id)
    rows = [
        r
        for r in weapon_rows(request)
        if cast(str, r["wargear_id"]).endswith(":avenger-shuriken-catapult")
    ][:2]
    assert len(rows) == 2
    assert rows[0]["model_instance_id"] != rows[1]["model_instance_id"]
    declare_shooting(session, request, rows, [target.unit_instance_id] * 2)
    accepted = events(session, "shooting_declaration_accepted")
    assert len(accepted) == 1
    # Finish then read the authenticated native sequence, preserving source pools.
    finish_attacks(session)
    records = session.lifecycle.decision_controller.event_log.records
    complete = next(e for e in records if e.event_type == "attack_sequence_completed")
    seq = completed_attack_sequence(
        event_records=records,
        sequence_id=cast(str, cast(dict[str, JsonValue], complete.payload)["sequence_id"]),
    )
    pools = seq.attack_pools
    assert len(pools) == 2
    assert {p.attacker_model_instance_id for p in pools} == {
        cast(str, r["model_instance_id"]) for r in rows
    }
    assert pools[0].targeting_rule_ids != pools[1].targeting_rule_ids
    thresholds: dict[int, set[int]] = {}
    for e in records:
        if (
            e.event_type == "attack_sequence_step"
            and isinstance(e.payload, dict)
            and e.payload.get("step") == "hit"
        ):
            index = cast(int, e.payload["pool_index"])
            roll = cast(dict[str, JsonValue], e.payload["payload"])
            thresholds.setdefault(index, set()).add(cast(int, roll["target_number"]))
    # Different attack dice were actually resolved at distinct BS values; this
    # asserts the downstream behavior, beyond a test-name/group metadata binding.
    assert thresholds == {0: {4}, 1: {3}}


@pytest.mark.parametrize("kind", ["hidden", "obscuring", "solid"])
def test_forbidden_native_shooting_declaration_preserves_state_and_can_decline(
    section13_definitions: Section02Definitions, kind: str
) -> None:
    from tests.support.section13_fixtures import window

    d = section13_definitions
    # Keep one clear native target so declaration is available, then propose the
    # protected one. The second target is a constructed pre-placed checkpoint.
    state, attacker, target = scene(
        d,
        target_x=28 if kind == "hidden" else 20,
        areas=(area(x=28),)
        if kind == "hidden"
        else (area(x=15, width=2, depth=18),)
        if kind == "obscuring"
        else (),
        features=(window(),) if kind == "solid" else (),
    )
    from tests.support.section04_fixtures import add_enemy

    add_enemy(d, state, identity="clear", x=18, y=30)
    session = shooting_session(d, state)
    request = shooting_request(session, attacker.unit_instance_id)
    rows = [
        r
        for r in weapon_rows(request)
        if cast(str, r["wargear_id"]).endswith(":avenger-shuriken-catapult")
    ][:1]
    before = session.lifecycle.to_payload()
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="forbidden",
        payload=shooting_payload(request, rows, [target.unit_instance_id]),
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID, invalid.to_payload()
    assert session.lifecycle.to_payload() == before
    assert pending(session) == request
    declare_shooting(session, request, [], [])
    assert pending(session).decision_type == "select_shooting_unit"
    assert not events(session, "attack_sequence_step")
