"""Direct physical evidence for foundational movement clauses."""

from __future__ import annotations

from dataclasses import replace
from math import isclose

import pytest
from tests.model_keyword_helpers import mixed_keyword_unit
from tests.unit_keyword_helpers import with_unit_keywords

from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryMeasurementKind,
    GeometryRulesFootprintPolicy,
    GeometrySourceUnits,
    ModelFootprintDefinition,
    ModelFootprintKind,
    ModelFootprintPartDefinition,
    ModelGeometryCatalogRecord,
    ModelGeometrySourceEvidence,
    ModelHeightDefinition,
)
from warhammer40k_core.engine.battlefield_state import ModelPlacement, geometry_model_for_placement
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.geometry.movement_envelope import MovementDistanceWitness
from warhammer40k_core.geometry.pose import Pose


def test_baseless_frame_rotates_upright_about_its_central_axis() -> None:
    footprint_evidence = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id="order97:frame-body",
        evidence_kind=GeometryEvidenceKind.MANUAL_MEASUREMENT,
        measurement_kind=GeometryMeasurementKind.FOOTPRINT,
        source_id="order97:rectangular-frame",
        source_units=GeometrySourceUnits.INCHES,
        source_dimensions=(("length", 4.0), ("width", 2.0)),
        document_reference="Synthetic baseless rectangular body, four by two inches.",
    )
    height_evidence = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id="order97:frame-height",
        evidence_kind=GeometryEvidenceKind.MANUAL_MEASUREMENT,
        measurement_kind=GeometryMeasurementKind.HEIGHT,
        source_id="order97:rectangular-frame",
        source_units=GeometrySourceUnits.INCHES,
        source_dimensions=(("height", 3.0),),
        document_reference="Synthetic baseless rectangular body, three inches tall.",
    )
    unit = with_unit_keywords(mixed_keyword_unit(), keywords=("FRAME",))
    model = unit.own_models[0]
    record = ModelGeometryCatalogRecord(
        model_geometry_id="order97:baseless-frame",
        model_profile_id=model.model_profile_id,
        rules_footprint_policy=GeometryRulesFootprintPolicy.USE_HULL,
        footprint=ModelFootprintDefinition.single_part(
            footprint_id="order97:frame-footprint",
            footprint_kind=ModelFootprintKind.RECTANGULAR,
            part=ModelFootprintPartDefinition.from_evidence(
                part_id="body",
                footprint_kind=ModelFootprintKind.RECTANGULAR,
                evidence=footprint_evidence,
            ),
        ),
        support_base=None,
        z_offset=None,
        height=ModelHeightDefinition.from_evidence(height_evidence),
        evidence=(footprint_evidence, height_evidence),
        source_ids=("order97:rectangular-frame",),
    )
    geometry = ModelGeometry.from_catalog_record(record)
    model = replace(model, geometry=geometry)
    placement = ModelPlacement(
        army_id="keyword-army",
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        model_instance_id=model.model_instance_id,
        pose=Pose.at(10, 10),
    )
    before = geometry_model_for_placement(model=model, placement=placement)
    after = geometry_model_for_placement(
        model=model, placement=replace(placement, pose=Pose.at(10, 10, facing_degrees=90))
    )
    assert record.support_base is None
    assert geometry.geometry_source_id == f"model-geometry:{record.model_geometry_id}"
    assert all(
        isclose(a, b)
        for a, b in zip(
            shapely_backend.footprint_for_base(before.base, before.pose).bounds,
            (8, 9, 12, 11),
            strict=True,
        )
    )
    assert all(
        isclose(a, b)
        for a, b in zip(
            shapely_backend.footprint_for_base(after.base, after.pose).bounds,
            (9, 8, 11, 12),
            strict=True,
        )
    )
    assert after.pose.position == before.pose.position
    assert after.volume.height == before.volume.height == 3
    distance = MovementDistanceWitness.for_model_path(
        model=before, poses=(before.pose, after.pose), max_distance_inches=0
    )
    assert distance.total_distance_inches == 0
    assert distance.rotation_events[0].facing_delta_degrees == 90


@pytest.mark.parametrize("near", [False, True])
def test_engagement_is_mutual_and_one_member_engages_each_unit(near: bool) -> None:
    from tests.core_clause_evidence_helpers import clause_session

    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range

    session = clause_session(phase=BattlePhase.MOVEMENT)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    source = state.battlefield_state.unit_placement_by_id("army-alpha:mover")
    target = state.battlefield_state.unit_placement_by_id("army-beta:enemy")
    if near:
        anchor = source.model_placements[0].pose.position
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            replace(
                target,
                model_placements=(
                    replace(target.model_placements[0], pose=Pose.at(anchor.x + 2, anchor.y)),
                    *target.model_placements[1:],
                ),
            )
        )
    assert (
        unit_within_enemy_engagement_range(state=state, unit_instance_id=source.unit_instance_id)
        is near
    )
    assert (
        unit_within_enemy_engagement_range(state=state, unit_instance_id=target.unit_instance_id)
        is near
    )


def test_mixed_movement_characteristics_set_each_model_own_budget() -> None:
    from tests.core_clause_evidence_helpers import clause_session

    from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
    from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.phases.movement import resolve_normal_move
    from warhammer40k_core.geometry.pathing import PathWitness

    session = clause_session(phase=BattlePhase.MOVEMENT)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    army = state.army_definitions[0]
    unit = army.units[0]
    values = (9, 6, 6, 6, 6)
    unit = replace(
        unit,
        own_models=tuple(
            replace(
                model,
                characteristics=tuple(
                    CharacteristicValue.from_raw(Characteristic.MOVEMENT, movement)
                    if value.characteristic is Characteristic.MOVEMENT
                    else value
                    for value in model.characteristics
                ),
            )
            for model, movement in zip(unit.own_models, values, strict=True)
        ),
    )
    army = replace(army, units=(unit,))
    scenario = BattlefieldScenario(
        armies=(army, state.army_definitions[1]), battlefield_state=state.battlefield_state
    )
    placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=placement,
        path_witness=PathWitness.for_paths(
            tuple(
                (
                    row.model_instance_id,
                    (row.pose, Pose.at(row.pose.position.x + 7, row.pose.position.y)),
                )
                for row in placement.model_placements
            )
        ),
    )
    assert tuple(result.is_valid for result in resolution.path_validation_results) == (
        True,
        False,
        False,
        False,
        False,
    )
    assert not resolution.is_valid


def test_flying_transit_through_engagement_does_not_establish_engagement() -> None:
    from tests.core_clause_evidence_helpers import flying_transit_session

    from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range

    session = flying_transit_session()
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    positions = state.battlefield_state.unit_placement_by_id("army-alpha:mover").model_placements
    assert all(isclose(row.pose.position.y, 26.6) for row in positions)
    assert not unit_within_enemy_engagement_range(state=state, unit_instance_id="army-alpha:mover")
    assert not unit_within_enemy_engagement_range(state=state, unit_instance_id="army-beta:enemy")


def test_if_able_fight_endpoint_cannot_override_real_unit_coherency() -> None:
    from tests.core_clause_evidence_helpers import clause_session

    from warhammer40k_core.core.ruleset_descriptor import MovementMode
    from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
    from warhammer40k_core.engine.fight_resolution import (
        FightMovementProposal,
        resolve_fight_movement,
    )
    from warhammer40k_core.engine.movement_proposals import ProposalKind
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.geometry.pathing import PathWitness

    session = clause_session(phase=BattlePhase.FIGHT, enemy_origin=Pose.at(10, 15.5))
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    before = state.battlefield_state.unit_placement_by_id("army-alpha:mover")
    first, *others = before.model_placements
    witness = PathWitness.for_paths(
        (
            (first.model_instance_id, (first.pose, Pose.at(10, 17))),
            *((row.model_instance_id, (row.pose, row.pose)) for row in others),
        )
    )
    proposal = FightMovementProposal(
        proposal_request_id="order97:if-able",
        proposal_kind=ProposalKind.PILE_IN,
        unit_instance_id=before.unit_instance_id,
        movement_phase_action="pile_in",
        movement_mode=MovementMode.PILE_IN,
        pile_in_target_unit_instance_ids=("army-beta:enemy",),
        witness=witness,
    )
    result = resolve_fight_movement(
        scenario=BattlefieldScenario(
            armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
        ),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        proposal=proposal,
    )
    assert all(row.is_valid for row in result.path_validation_results)
    assert result.coherency_result is not None
    assert not result.coherency_result.is_coherent
    assert not result.is_valid
    assert result.rollback_record is not None
    assert result.rollback_record.before_placement == before


def test_setup_body_overhang_does_not_exempt_base_containment() -> None:
    from tests.order97_gap_probes_01_08 import avoidable_setup_body_overhang_observation

    result = avoidable_setup_body_overhang_observation(y=2)
    assert result["observed"] == [
        "battlefield_edge_crossed",
        "deployment_zone_violation",
        "deployment_zone_violation",
    ]


def test_as_close_setup_reaches_legal_base_contact_and_rejects_farther_endpoint() -> None:
    from tests.disembark_eligibility_helpers import TRANSPORT_ID
    from tests.order60_emergency_disembark_helpers import (
        order60_emergency_session,
        order60_passenger_placement,
        order60_resolve_emergency,
    )

    from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
    from warhammer40k_core.engine.transports import TransportOperationViolationCode
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_emergency_disembark_placement_2026_09 as source,
    )

    session = order60_emergency_session()
    state = session.lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    original = order60_passenger_placement(session)
    first = original.model_placements[0]
    contact = replace(first, pose=Pose.at(first.pose.position.x - 0.02, first.pose.position.y))
    placement = replace(original, model_placements=(contact, *original.model_placements[1:]))
    transport = scenario.battlefield_state.unit_placement_by_id(TRANSPORT_ID).model_placements[0]
    transport_geometry = geometry_model_for_placement(
        model=scenario.model_instance_for_placement(transport), placement=transport
    )
    passenger_geometry = geometry_model_for_placement(
        model=scenario.model_instance_for_placement(contact), placement=contact
    )
    assert isclose(passenger_geometry.range_to(transport_geometry), 0, abs_tol=1e-9)
    accepted = order60_resolve_emergency(session, placement)
    assert accepted.is_valid
    farther = replace(
        contact, pose=Pose.at(contact.pose.position.x + 0.17, contact.pose.position.y)
    )
    rejected = order60_resolve_emergency(
        session, replace(placement, model_placements=(farther, *placement.model_placements[1:]))
    )
    assert not rejected.is_valid
    assert [
        (row.violation_code, row.model_instance_id, row.source_rule_id)
        for row in rejected.violations
    ] == [
        (
            TransportOperationViolationCode.EMERGENCY_DISEMBARK_NOT_CLOSEST,
            first.model_instance_id,
            source.EMERGENCY_DISEMBARK_PLACEMENT_SOURCE_ID,
        )
    ]


@pytest.mark.parametrize(
    ("endpoint_gap", "budget", "within_one"),
    [
        pytest.param(0.0, 2.0, True, id="insufficient-counterfactual-budget"),
        pytest.param(0.2, 20.0, True, id="closer-legal-endpoint-exists"),
        pytest.param(1.01, 20.0, False, id="model-parts-beyond-one-inch"),
    ],
)
def test_deemed_contact_rejects_each_missing_movement_condition(
    endpoint_gap: float, budget: float, within_one: bool
) -> None:
    from tests.order85_overhang_helpers import overhang_charge_session

    from warhammer40k_core.engine.base_contact_authority import (
        contacts_for_validated_move,
        current_deemed_base_contacts,
    )
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.geometry.pathing import PathWitness
    from warhammer40k_core.geometry.physical_model import model_parts_within
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_base_contact_2026_09 as source,
    )

    session, proposal = overhang_charge_session()
    session.submit_parameterized_payload(
        request_id=proposal.proposal_request_id,
        result_id="order97:accepted-overhang-contact",
        payload=validate_json_value(proposal.to_payload()),
    )
    contacts = current_deemed_base_contacts(session.lifecycle.state)
    assert len(contacts) == 1
    contact = contacts[0]
    assert contact.source_rule_id == source.DEEMED_BASE_CONTACT_SOURCE_ID
    query = contact.movement_query
    mover = query.path_context.moving_model
    enemy = next(m for m in query.path_context.enemy_models if m.model_id == contact.enemy_model_id)
    accepted_end = query.path_context.witness.final_pose_for_model(mover.model_id)
    end = Pose.at(accepted_end.position.x, accepted_end.position.y - endpoint_gap)
    witness = PathWitness.for_paths(((mover.model_id, (mover.pose, end)),))
    path = replace(query.path_context, witness=witness, movement_distance_budget_inches=budget)
    terrain = replace(query.terrain_context, witness=witness)
    assert model_parts_within(replace(mover, pose=end), enemy, 1.0) is within_one
    path_result = path.validate()
    terrain_result = terrain.validate()
    assert path_result.is_valid
    assert terrain_result.is_valid
    result = contacts_for_validated_move(
        path_context=path,
        terrain_context=terrain,
        path_result=path_result,
        terrain_result=terrain_result,
        query=replace(query, path_context=path, terrain_context=terrain),
    )
    assert result.is_valid
    assert result.deemed_base_contacts == ()


def test_oversized_deployment_consumer_is_limited_to_pregame_setup() -> None:
    from tests.large_model_setup_helpers import oversized_deployment_case

    from warhammer40k_core.engine.deployment import resolve_deployment_placement
    from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage

    state, request, proposal = oversized_deployment_case()
    assert state.stage is GameLifecycleStage.SETUP
    assert state.active_player_id is None
    result = resolve_deployment_placement(
        state=state,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        request=request,
        proposal=proposal,
    )
    assert result.is_valid
    state.stage = GameLifecycleStage.BATTLE
    with pytest.raises(GameLifecycleError, match="Deployment placement requires setup stage"):
        resolve_deployment_placement(
            state=state,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            request=request,
            proposal=proposal,
        )
