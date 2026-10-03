"""Selected P13B physical terrain obligations and positive controls."""

import json
import math
from collections.abc import Callable
from dataclasses import replace

import pytest
from tests.core_clause_evidence_helpers import assert_persistence_viewers_replay
from tests.order97_gap_probes_09_17 import (
    enclosed_window_feature,
    probe_dense_floor_crossing,
    probe_solid_window,
    probe_solid_window_endpoint,
    probe_vertical_contact,
)
from tests.order108_terrain_helpers import terrain_session
from tests.psychic_modifier_helpers import pending_request

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.core.terrain_areas import (
    PlacedTerrainArea,
    TerrainAreaFootprintTemplate,
    aggregate_logical_terrain_area_classification,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry, TerrainDisplayPoint
from warhammer40k_core.core.visibility import TerrainVisibilityContext
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.geometry.base import CircularBase, RectangularBase
from warhammer40k_core.geometry.model_body import ModelBodyPart
from warhammer40k_core.geometry.pathing import PathWitness, TerrainPathLegalityContext
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainFloorDefinition
from warhammer40k_core.geometry.terrain_classification import (
    TerrainAreaClassification,
    terrain_area_classification_from_token,
)
from warhammer40k_core.geometry.terrain_solid import solid_endpoint_intersection
from warhammer40k_core.geometry.terrain_transit import path_retains_climbing_contact
from warhammer40k_core.geometry.volume import Model, ModelVolume


def test_exposed_is_an_explicit_round_tripped_classification() -> None:
    classification = terrain_area_classification_from_token("exposed")
    feature = replace(enclosed_window_feature(), classification=classification)
    assert classification.value == "exposed"
    assert TerrainFeatureDefinition.from_payload(feature.to_payload()) == feature


@pytest.mark.parametrize("probe", [probe_dense_floor_crossing, probe_vertical_contact])
def test_forbidden_terrain_paths_are_rejected(probe: Callable[[], dict[str, JsonValue]]) -> None:
    result = probe()
    observed = result["observed_answer"]
    assert isinstance(observed, dict)
    assert observed["is_valid"] is False


def test_solid_window_blocks_continuous_visibility() -> None:
    assert probe_solid_window()["observed_answer"] == {"visible": False}


def test_shared_setup_endpoint_rejects_solid_window() -> None:
    assert probe_solid_window_endpoint()["observed_answer"] == {"legal": False}


def test_solid_volume_fills_only_enclosed_low_openings() -> None:
    feature = enclosed_window_feature()
    assert len(feature.visibility_volumes()) > len(feature.walls)
    assert len(feature.terrain_volumes()) == len(feature.walls)
    assert (
        len(
            replace(
                feature, walls=tuple(w for w in feature.walls if w.wall_id != "lintel")
            ).visibility_volumes()
        )
        == 3
    )
    assert (
        len(replace(feature, classification=TerrainAreaClassification.LIGHT).terrain_volumes()) == 4
    )


@pytest.mark.parametrize("classification", ["exposed", "light", "dense"])
@pytest.mark.parametrize("keyword", ["INFANTRY", "BEAST", "SWARM", "MOBILE", "VEHICLE"])
def test_floor_transit_permissions_and_valid_context_persistence(
    classification: str, keyword: str
) -> None:
    feature = replace(
        enclosed_window_feature(),
        classification=terrain_area_classification_from_token(classification),
        walls=(),
        floors=(TerrainFloorDefinition("floor", 0, 0, 1, 4, 4, 0.01),),
    )
    mover = Model("mover", Pose.at(0, 0), CircularBase(0.25), ModelVolume(0.2))
    path = (mover.pose, Pose.at(0, 0, 2), Pose.at(0.5, 0, 2), Pose.at(0.5, 0))
    context = _context(mover, path, feature, keyword)
    restored = TerrainPathLegalityContext.from_payload(context.to_payload())
    expected = classification != "dense" or keyword in {"INFANTRY", "BEAST", "SWARM"}
    assert context.validate().is_valid is expected
    assert restored.validate() == context.validate()


def _context(
    model: Model,
    path: tuple[Pose, ...],
    feature: TerrainFeatureDefinition,
    keyword: str = "INFANTRY",
) -> TerrainPathLegalityContext:
    return MovementLegalityContext.from_keywords(
        keywords=(keyword,),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.NORMAL,
        movement_phase_action="normal_move",
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    ).to_terrain_path_legality_context(
        moving_model=model,
        witness=PathWitness.for_paths(((model.model_id, path),)),
        terrain=(),
        terrain_features=(feature,),
        sample_interval_inches=10,
    )


@pytest.mark.parametrize("angle", [0, 37, 90, 180])
@pytest.mark.parametrize("door", [False, True])
def test_solid_windows_and_doors_share_visibility_and_endpoint_volume(
    angle: float, door: bool
) -> None:
    feature = _feature_area(enclosed_window_feature(), 0, 0)
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    feature = replace(
        feature,
        walls=tuple(
            replace(
                w,
                center_x_inches=c * w.center_x_inches - s * w.center_y_inches,
                center_y_inches=s * w.center_x_inches + c * w.center_y_inches,
                rotation_degrees=angle,
            )
            for w in feature.walls
            if not door or w.wall_id != "sill"
        ),
    )
    observer = Model("observer", Pose.at(0, 0, 1.4), CircularBase(0.1), ModelVolume(0.2))
    target = replace(observer, model_id="target", pose=Pose.at(3 * c, 3 * s, 1.4))
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        los_cache_key="order108",
        observer_model=observer,
        target_models=(target,),
        terrain_features=(feature,),
        target_model_keywords=(("target", ("INFANTRY",)),),
    )
    assert not context.resolve_line_of_sight().unit_visible
    inside = replace(observer, pose=Pose.at(c, s, 1.4))
    assert solid_endpoint_intersection(inside, feature) is not None
    assert solid_endpoint_intersection(observer, feature) is None


def test_high_opening_and_body_protrusion_boundaries() -> None:
    feature = enclosed_window_feature()
    feature = replace(
        feature,
        walls=tuple(replace(w, bottom_z_inches=w.bottom_z_inches + 2) for w in feature.walls),
    )
    model = Model("mover", Pose.at(1, 0, 3.1), CircularBase(0.1), ModelVolume(0.2))
    assert solid_endpoint_intersection(model, feature) is None
    observer = replace(model, model_id="observer", pose=Pose.at(0, 0, 3.4))
    target = replace(model, model_id="target", pose=Pose.at(3, 0, 3.4))
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        los_cache_key="order108-high-window",
        observer_model=observer,
        target_models=(target,),
        terrain_features=(feature,),
        target_model_keywords=(("target", ("INFANTRY",)),),
    )
    assert context.resolve_line_of_sight().unit_visible
    low = enclosed_window_feature()
    body = ModelBodyPart("gun", CircularBase(0.1), 1, 0, 1.4, 0.2, "test:gun")
    overhang = Model("overhang", Pose.at(0, 0), CircularBase(0.1), ModelVolume(0.2), (body,))
    assert solid_endpoint_intersection(overhang, low) is not None
    assert solid_endpoint_intersection(replace(overhang, body_parts=()), low) is None


def test_solid_door_does_not_become_a_physical_transit_blocker() -> None:
    feature = enclosed_window_feature()
    feature = replace(
        feature,
        walls=tuple(
            replace(w, height_inches=4) if w.wall_id == "lintel" else w
            for w in feature.walls
            if w.wall_id != "sill"
        ),
    )
    mover = Model("vehicle", Pose.at(0, 0), CircularBase(0.1), ModelVolume(0.2))
    path = (mover.pose, Pose.at(1, 0), Pose.at(2, 0))
    assert _context(mover, path, feature, "VEHICLE").validate().is_valid
    assert solid_endpoint_intersection(replace(mover, pose=path[1]), feature) is not None


def test_contact_uses_base_edge_and_continuous_union_not_sampled_poses() -> None:
    feature = enclosed_window_feature()
    terrain = feature.wall_volumes()
    model = Model("mover", Pose.at(0.35, 0), CircularBase(0.1), ModelVolume(0.2))
    # The wall is at x=.95: exactly .5 from this base edge.
    assert path_retains_climbing_contact(model, (model.pose, Pose.at(0.35, 0, 3)), terrain)
    assert not path_retains_climbing_contact(
        model, (Pose.at(0.349, 0), Pose.at(0.349, 0, 3)), terrain
    )
    separated = (
        replace(terrain[0], bottom_center=replace(terrain[0].bottom_center, y=-3), depth=1),
        replace(terrain[0], bottom_center=replace(terrain[0].bottom_center, y=3), depth=1),
    )
    assert not path_retains_climbing_contact(
        model, (Pose.at(0.35, -3), Pose.at(0.35, 3, 2)), separated
    )


def test_rotating_contact_accepts_clearance_and_rejects_lost_contact() -> None:
    wall = enclosed_window_feature().wall_volumes()[0]
    model = Model("rectangle", Pose.at(0.8, -1.5), RectangularBase(0.2, 0.1), ModelVolume(0.2))
    assert path_retains_climbing_contact(
        model, (model.pose, Pose.at(0.8, -1.5, 1, facing_degrees=90)), (wall,)
    )
    assert not path_retains_climbing_contact(
        model, (Pose.at(0, -1.5), Pose.at(0, -1.5, 1, facing_degrees=90)), (wall,)
    )


@pytest.mark.parametrize("classification", ["dense", "exposed"])
def test_facade_terrain_rejection_retry_pending_completed_restore_and_replay(
    classification: str,
) -> None:
    feature = enclosed_window_feature()
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=11,
        center_y_inches=20,
        width_inches=8,
        depth_inches=8,
        display_template_id="order108-transit",
    )
    feature = replace(
        feature,
        footprint_center_x_inches=11,
        footprint_center_y_inches=20,
        footprint_width_inches=8,
        footprint_depth_inches=8,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        classification=terrain_area_classification_from_token(classification),
        walls=tuple(
            replace(
                w, center_x_inches=w.center_x_inches + 11, center_y_inches=w.center_y_inches + 20
            )
            for w in feature.walls
        ),
    )
    session = terrain_session(feature)
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, option_id="army-alpha:mover", result_id="unit"
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, option_id="normal_move", result_id="action"
    )
    request = pending_request(session)
    assert request.decision_type == "submit_movement_proposal"
    assert_persistence_viewers_replay(session)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    before = state.battlefield_state
    model_id = before.unit_placement_by_id("army-alpha:mover").model_placements[0].model_instance_id
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    for label, path, expected in (
        (
            "free-climb",
            (Pose.at(10, 20), Pose.at(10, 20, 0.5), Pose.at(12, 20, 0.5), Pose.at(14, 20)),
            LifecycleStatusKind.INVALID,
        ),
        (
            "legal-transit",
            (Pose.at(10, 20), Pose.at(12, 20), Pose.at(14, 20)),
            LifecycleStatusKind.WAITING_FOR_DECISION,
        ),
    ):
        request = pending_request(session)
        proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
        outcome = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=label,
            payload=validate_json_value(
                MovementProposalPayload(
                    proposal_request_id=request.request_id,
                    proposal_kind=proposal.proposal_kind,
                    unit_instance_id="army-alpha:mover",
                    movement_phase_action="normal_move",
                    movement_mode="normal",
                    witness=PathWitness.for_paths(((model_id, path),)),
                ).to_payload()
            ),
        )
        assert outcome.status_kind is expected, outcome.to_payload()
        if expected is LifecycleStatusKind.INVALID:
            assert "climbing_contact_required" in json.dumps(outcome.to_payload())
            assert session.lifecycle.state is not None
            assert session.lifecycle.state.battlefield_state == before
        assert_persistence_viewers_replay(session)
        session = LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(session.to_persistence_payload()))
        )
    assert session.lifecycle.state is not None
    assert session.lifecycle.state.battlefield_state is not None
    assert session.lifecycle.state.battlefield_state.unit_placement_by_id(
        "army-alpha:mover"
    ).model_placements[0].pose == Pose.at(14, 20)


def _feature_area(
    feature: TerrainFeatureDefinition, x: float, y: float
) -> TerrainFeatureDefinition:
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=x,
        center_y_inches=y,
        width_inches=8,
        depth_inches=8,
        display_template_id="order108-area",
    )
    return replace(
        feature,
        footprint_center_x_inches=x,
        footprint_center_y_inches=y,
        footprint_width_inches=8,
        footprint_depth_inches=8,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
    )


@pytest.mark.parametrize("other", ["exposed", "light", "dense"])
def test_exposed_logical_area_preserves_other_members_classification(other: str) -> None:
    template = TerrainAreaFootprintTemplate(
        footprint_template_id="order108-template",
        name="Order 108 template",
        bounding_width_inches=2,
        bounding_depth_inches=2,
        polygon_vertices_inches=(
            TerrainDisplayPoint(-1, -1),
            TerrainDisplayPoint(1, -1),
            TerrainDisplayPoint(1, 1),
            TerrainDisplayPoint(-1, 1),
        ),
        source_id="order108-template",
    )
    exposed = PlacedTerrainArea.from_template(
        terrain_area_id="exposed",
        logical_terrain_area_id="group",
        template=template,
        terrain_feature_kind="ruins",
        classification=TerrainAreaClassification.EXPOSED,
        center_x_inches=0,
        center_y_inches=0,
        rotation_degrees=0,
        source_layout_id="order108-layout",
        source_id="order108-exposed",
    )
    companion = replace(
        exposed,
        terrain_area_id="companion",
        classification=terrain_area_classification_from_token(other),
    )
    assert PlacedTerrainArea.from_payload(exposed.to_payload()) == exposed
    assert (
        aggregate_logical_terrain_area_classification("group", (exposed, companion)).value == other
    )
