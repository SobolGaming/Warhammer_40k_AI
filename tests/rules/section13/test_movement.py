"""13.06 witnessed traversal; keyword cases are constructed permission matrices."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import LORD_EXULTANT, Section02Definitions
from tests.support.section13_fixtures import feature, native_models, tiny, transit, window
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.endpoint_placement import terrain_endpoint_placement_violation
from warhammer40k_core.engine.model_movement_permission import model_movement_terrain_context
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pathing import PathWitness, TerrainPathLegalityContext
from warhammer40k_core.geometry.pose import Point3, Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFeatureKind,
    TerrainVolume,
)
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification as C


def _r2_bound_endpoint(
    definitions: Section02Definitions,
    physical_keyword: str,
    group_keywords: tuple[str, ...],
    kind: TerrainFeatureKind,
    grants: tuple[str, ...] = (),
) -> tuple[UnitInstance, TerrainPathLegalityContext, TerrainFeatureDefinition]:
    from tests.unit_keyword_helpers import with_unit_keywords

    # Explicit keyword/small-envelope kernel; no native SWARM admission or height claim.
    unit = with_unit_keywords(definitions.unit(LORD_EXULTANT), keywords=(physical_keyword,))
    model = tiny(unit.own_model_ids()[0], x=12, z=3)
    terrain = replace(feature(width=6, depth=6, floor=True, height=3), feature_kind=kind)
    context = MovementLegalityContext.from_keywords(
        keywords=group_keywords,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.NORMAL,
        movement_phase_action="normal_move",
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    ).to_terrain_path_legality_context(
        moving_model=model,
        witness=PathWitness.for_paths(((model.model_id, (model.pose, Pose.at(14, 10, 3))),)),
        terrain=(),
        terrain_features=(terrain,),
        contact_footprint_available=True,
    )
    return (
        unit,
        model_movement_terrain_context(
            model=unit.own_models[0],
            context=context,
            granted_keywords=grants,
        ),
        terrain,
    )


@pytest.mark.parametrize(
    "kind", [TerrainFeatureKind.RUINS, TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY]
)
@pytest.mark.parametrize("physical", ["VEHICLE", "MOBILE"])
@pytest.mark.parametrize("borrowed", ["INFANTRY", "SWARM", "FLY"])
def test_r2_physical_endpoint_cannot_borrow_sibling_keyword(
    section13_definitions: Section02Definitions,
    kind: TerrainFeatureKind,
    physical: str,
    borrowed: str,
) -> None:
    from warhammer40k_core.engine.emergency_disembark_placement import (
        _setup_terrain,  # pyright: ignore[reportPrivateUsage]
    )

    unit, bound, terrain = _r2_bound_endpoint(
        section13_definitions,
        physical,
        (physical, borrowed),
        kind,
    )
    narrowed = bound.terrain_movement_policy.policy_for_feature_kind(kind)
    assert borrowed not in narrowed.upper_floor_allowed_keywords
    assert not bound.validate().is_valid, bound.validate().to_payload()
    restored = TerrainPathLegalityContext.from_payload(bound.to_payload())
    assert restored == bound
    assert not restored.validate().is_valid
    setup = terrain_endpoint_placement_violation(
        model=replace(bound.moving_model, pose=Pose.at(14, 10, 3)),
        unit=unit,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        terrain_features=(terrain,),
        violation_code="r2:physical",
        placement_label="physical endpoint",
    )
    assert setup is not None
    assert not _setup_terrain(
        terrain,
        unit.own_models[0],
        RulesetDescriptor.warhammer_40000_eleventh(),
    ).elevated_allowed


@pytest.mark.parametrize(
    "kind", [TerrainFeatureKind.RUINS, TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY]
)
@pytest.mark.parametrize("physical", ["INFANTRY", "SWARM", "BEAST", "FLY", "MONSTER"])
def test_r2_physical_source_keyword_survives_classification(
    section13_definitions: Section02Definitions,
    kind: TerrainFeatureKind,
    physical: str,
) -> None:
    from warhammer40k_core.engine.emergency_disembark_placement import (
        _setup_terrain,  # pyright: ignore[reportPrivateUsage]
    )

    unit, bound, terrain = _r2_bound_endpoint(
        section13_definitions,
        physical,
        ("VEHICLE", physical),
        kind,
    )
    narrowed = bound.terrain_movement_policy.policy_for_feature_kind(kind)
    classified = bound.terrain_movement_policy.policy_for_feature_kind(
        kind,
        endpoint_classification=C.DENSE,
    )
    assert classified.upper_floor_allowed_keywords == narrowed.upper_floor_allowed_keywords
    assert bound.validate().is_valid, bound.validate().to_payload()
    assert _setup_terrain(
        terrain,
        unit.own_models[0],
        RulesetDescriptor.warhammer_40000_eleventh(),
    ).elevated_allowed
    assert (
        terrain_endpoint_placement_violation(
            model=replace(bound.moving_model, pose=Pose.at(14, 10, 3)),
            unit=unit,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            terrain_features=(terrain,),
            violation_code="r2:physical",
            placement_label="physical endpoint",
        )
        is None
    )


@pytest.mark.parametrize(
    "kind", [TerrainFeatureKind.RUINS, TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY]
)
@pytest.mark.parametrize("grant", [False, True])
def test_r2_borrowed_fly_requires_explicit_physical_move_grant(
    section13_definitions: Section02Definitions,
    kind: TerrainFeatureKind,
    grant: bool,
) -> None:
    # Existing trusted all-model grant seam; no native ability/admission is invented.
    _, bound, _ = _r2_bound_endpoint(
        section13_definitions,
        "VEHICLE",
        ("VEHICLE", "FLY"),
        kind,
        ("FLY",) if grant else (),
    )
    assert bound.validate().is_valid is grant, bound.validate().to_payload()


@pytest.mark.parametrize("classification", [C.EXPOSED, C.LIGHT, C.DENSE])
@pytest.mark.parametrize("keyword", ["INFANTRY", "BEAST", "SWARM", "MOBILE", "VEHICLE", "MONSTER"])
@pytest.mark.parametrize("vertical", [False, True])
def test_category_and_direction_permissions(
    classification: C, keyword: str, vertical: bool
) -> None:
    m = tiny()
    f = feature(classification)
    poses = (
        (m.pose, Pose.at(13, 10), Pose.at(14, 10, 2), Pose.at(15, 10), Pose.at(18, 10))
        if vertical
        else (m.pose, Pose.at(18, 10))
    )
    result = transit(m, poses, keywords=(keyword,), features=(f,))
    permitted = classification is not C.DENSE or keyword in {"INFANTRY", "BEAST", "SWARM"}
    if not vertical and keyword == "MOBILE":
        permitted = True
    assert result.is_valid is permitted, result.to_payload()
    if permitted:
        assert result.segments
        assert any(s.vertical_distance_inches > 0 for s in result.segments) is vertical
    else:
        assert result.violations


@pytest.mark.parametrize(
    ("height", "accepted"), [(1.999, True), (2, True), (2.001, False), (4, False)]
)
@pytest.mark.parametrize("keyword", ["VEHICLE", "MONSTER", "MOUNTED"])
def test_other_models_dense_two_inch_threshold(height: float, accepted: bool, keyword: str) -> None:
    m = tiny()
    result = transit(
        m, (m.pose, Pose.at(18, 10)), keywords=(keyword,), features=(feature(height=height),)
    )
    assert result.is_valid is accepted, result.to_payload()
    if accepted:
        assert all(s.vertical_distance_inches == 0 for s in result.segments)


@pytest.mark.parametrize("keywords", [("INFANTRY",), ("VEHICLE",)])
def test_terrain_area_without_physical_feature_does_not_impede_move(
    keywords: tuple[str, ...],
) -> None:
    m = tiny()
    result = transit(m, (m.pose, Pose.at(18, 10)), keywords=keywords)
    assert result.is_valid
    assert result.segments == ()


@pytest.mark.parametrize("keyword", ["VEHICLE", "MOBILE", "MONSTER", "INFANTRY"])
def test_dense_floor_cannot_be_crossed_without_vertical_permission(keyword: str) -> None:
    m = tiny(x=14)
    floor = feature(width=6, depth=6, floor=True, height=3)
    result = transit(
        m,
        (m.pose, Pose.at(14, 10, 4), Pose.at(17.75, 10, 4), Pose.at(17.75, 10)),
        keywords=(keyword,),
        features=(floor,),
    )
    assert result.is_valid is (keyword == "INFANTRY"), result.to_payload()


@pytest.mark.parametrize(("offset", "accepted"), [(0.5, True), (0.501, False), (2, False)])
def test_ascent_and_descent_remain_within_half_inch_of_feature(
    offset: float, accepted: bool
) -> None:
    # Wall edge x13.5; tiny base right edge x13.5-offset. Rise then return.
    m = tiny(x=13.25 - offset)
    result = transit(
        m,
        (m.pose, Pose.at(m.pose.position.x, 10, 3), m.pose),
        keywords=("INFANTRY",),
        features=(feature(),),
    )
    assert result.is_valid is accepted, result.to_payload()


def test_climb_counts_ascent_and_descent_plus_horizontal_distance() -> None:
    m = tiny(x=10)
    obstacle = TerrainVolume("s13:stack", Point3(14, 10, 0), 1, 2, 3)
    result = transit(
        m,
        (
            m.pose,
            Pose.at(13.25, 10),
            Pose.at(13.25, 10, 3),
            Pose.at(14.75, 10, 3),
            Pose.at(14.75, 10),
            Pose.at(18, 10),
        ),
        keywords=("VEHICLE",),
        terrain=(obstacle,),
    )
    assert result.is_valid, result.to_payload()
    assert sum(s.vertical_distance_inches for s in result.segments) == 6
    assert (
        sum(s.counted_distance_inches - s.horizontal_distance_inches for s in result.segments) == 6
    )


@pytest.mark.parametrize(
    ("keyword", "accepted"),
    [
        ("INFANTRY", True),
        ("BEAST", True),
        ("SWARM", True),
        ("FLY", True),
        ("MONSTER", True),
        ("VEHICLE", False),
        ("MOBILE", False),
    ],
)
def test_upper_floor_endpoint_keyword_gate(keyword: str, accepted: bool) -> None:
    # Explicit physical-keyword checkpoint; not a claim that native Lord has FLY etc.
    m = tiny(x=10.5)
    result = transit(
        m,
        (m.pose, Pose.at(10.5, 10, 3), Pose.at(14, 10, 3)),
        keywords=(keyword,),
        features=(feature(width=6, depth=6, floor=True, height=3),),
    )
    assert result.is_valid is accepted, result.to_payload()


@pytest.mark.parametrize(
    ("x", "accepted"), [(14, True), (16.75, True), (16.751, False), (18, False)]
)
def test_upper_floor_stability_and_no_base_overhang(x: float, accepted: bool) -> None:
    m = tiny(x=10.5)
    result = transit(
        m,
        (m.pose, Pose.at(10.5, 10, 3), Pose.at(x, 10, 3)),
        keywords=("INFANTRY",),
        features=(feature(width=6, depth=6, floor=True, height=3),),
    )
    assert result.is_valid is accepted, result.to_payload()


@pytest.mark.parametrize("classification", [C.DENSE, C.LIGHT])
@pytest.mark.parametrize(("z", "accepted"), [(1.25, False), (2.5, False), (3.01, True)])
def test_solid_endpoint_enclosed_opening_and_high_control(
    section13_definitions: Section02Definitions, classification: C, z: float, accepted: bool
) -> None:
    d = section13_definitions
    u = d.unit(LORD_EXULTANT)
    # Constructed small physical envelope isolates Solid from support/overhang.
    m = replace(tiny(u.own_model_ids()[0], x=14, z=z), pose=Pose.at(14, 10, z))
    result = terrain_endpoint_placement_violation(
        model=m,
        unit=u,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        terrain_features=(window(classification=classification),),
        violation_code="s13:solid",
        placement_label="s13 probe",
    )
    assert (result is None) is (accepted or classification is C.LIGHT), result
    if result is not None:
        assert "Solid" in result.message


def test_endpoint_uses_physical_owner_and_native_base_overhang(
    section13_definitions: Section02Definitions,
) -> None:
    d = section13_definitions
    u = d.unit(LORD_EXULTANT)
    stranger = d.unit(LORD_EXULTANT, identity="stranger")
    m = native_models(u, (Pose.at(14, 10, 3),))[0]
    f = feature(width=6, depth=6, floor=True, height=3)
    assert (
        terrain_endpoint_placement_violation(
            model=m,
            unit=u,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            terrain_features=(f,),
            violation_code="s13:end",
            placement_label="s13",
        )
        is None
    )
    result = terrain_endpoint_placement_violation(
        model=m,
        unit=stranger,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        terrain_features=(f,),
        violation_code="s13:end",
        placement_label="s13",
    )
    assert result is not None
    assert "physical unit" in result.message
    overhang = replace(m, pose=Pose.at(17, 10, 3))
    assert (
        terrain_endpoint_placement_violation(
            model=overhang,
            unit=u,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            terrain_features=(f,),
            violation_code="s13:end",
            placement_label="s13",
        )
        is not None
    )


def test_any_protruding_model_part_cannot_penetrate_low_solid_opening(
    section13_definitions: Section02Definitions,
) -> None:
    from warhammer40k_core.geometry.base import CircularBase
    from warhammer40k_core.geometry.model_body import ModelBodyPart

    u = section13_definitions.unit(LORD_EXULTANT)
    m = tiny(u.own_model_ids()[0], x=13, z=1.25)
    m = replace(
        m,
        body_parts=(
            ModelBodyPart(
                "protrusion",
                CircularBase(0.25),
                1,
                0,
                0,
                0.5,
                "constructed:s13:physical-protrusion",
            ),
        ),
    )
    result = terrain_endpoint_placement_violation(
        model=m,
        unit=u,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        terrain_features=(window(),),
        violation_code="s13:body",
        placement_label="protrusion",
    )
    assert result is not None
    assert "Solid" in result.message
    clear = terrain_endpoint_placement_violation(
        model=replace(m, body_parts=()),
        unit=u,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        terrain_features=(window(),),
        violation_code="s13:body",
        placement_label="protrusion",
    )
    assert clear is None


def test_stable_upper_surface_of_classified_dense_nonruins_feature_is_legal(
    section13_definitions: Section02Definitions,
) -> None:
    from warhammer40k_core.geometry.terrain import TerrainFeatureKind

    u = section13_definitions.unit(LORD_EXULTANT)
    m = native_models(u, (Pose.at(14, 10, 3),))[0]
    f = replace(
        feature(width=6, depth=6, floor=True, height=3),
        feature_kind=TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
    )
    result = terrain_endpoint_placement_violation(
        model=m,
        unit=u,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        terrain_features=(f,),
        violation_code="s13:surface",
        placement_label="stable Dense surface",
    )
    assert result is None, result


@pytest.mark.parametrize("classification", [C.EXPOSED, C.LIGHT, C.DENSE])
@pytest.mark.parametrize("kind", ["ruins", "battlefield_debris_and_statuary", "crater_and_rubble"])
@pytest.mark.parametrize("keyword", ["INFANTRY", "SWARM", "VEHICLE", "MOBILE"])
def test_repaired_surface_keyword_scope_and_shared_consumers(
    section13_definitions: Section02Definitions, classification: C, kind: str, keyword: str
) -> None:
    from tests.unit_keyword_helpers import with_unit_keywords
    from warhammer40k_core.geometry.terrain import TerrainFeatureKind

    # Explicit constructed physical-keyword checkpoint, not native SWARM admission.
    u = with_unit_keywords(section13_definitions.unit(LORD_EXULTANT), keywords=(keyword,))
    m = tiny(u.own_model_ids()[0], x=12, z=3)
    f = replace(
        feature(classification, width=6, depth=6, floor=True, height=3),
        feature_kind=TerrainFeatureKind(kind),
    )
    endpoint = Pose.at(14, 10, 3)
    result = transit(m, (m.pose, endpoint), keywords=(keyword,), features=(f,))
    placement = terrain_endpoint_placement_violation(
        model=replace(m, pose=endpoint),
        unit=u,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        terrain_features=(f,),
        violation_code="s13:surface",
        placement_label="surface control",
    )
    assert result.is_valid is (keyword in {"INFANTRY", "SWARM"}), result.to_payload()
    assert (placement is None) is result.is_valid, placement


@pytest.mark.parametrize("keyword", ["INFANTRY", "SWARM"])
@pytest.mark.parametrize("case", ["edge", "overhang", "outside", "unsupported", "above"])
def test_repaired_surface_support_and_exact_boundary_controls(
    section13_definitions: Section02Definitions, keyword: str, case: str
) -> None:
    from tests.unit_keyword_helpers import with_unit_keywords
    from warhammer40k_core.geometry.endpoint_support import model_has_endpoint_support
    from warhammer40k_core.geometry.terrain import TerrainFeatureKind

    u = with_unit_keywords(section13_definitions.unit(LORD_EXULTANT), keywords=(keyword,))
    m = tiny(u.own_model_ids()[0], x=12, z=3)
    f = replace(
        feature(width=6, depth=6, floor=True, height=3),
        feature_kind=TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
    )
    if case == "unsupported":
        f = replace(f, floors=())
    x = {"edge": 16.75, "overhang": 16.751, "outside": 18}.get(case, 14)
    endpoint = Pose.at(x, 10, 3.01 if case == "above" else 3)
    result = transit(m, (m.pose, endpoint), keywords=(keyword,), features=(f,))
    placement = terrain_endpoint_placement_violation(
        model=replace(m, pose=endpoint),
        unit=u,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        terrain_features=(f,),
        violation_code="s13:support",
        placement_label="support control",
    )
    assert result.is_valid is (case == "edge"), result.to_payload()
    # Setup composes per-feature restrictions with global physical support.
    supported = model_has_endpoint_support(replace(m, pose=endpoint), terrain=(), features=(f,))
    assert (placement is None and supported) is result.is_valid, placement


@pytest.mark.parametrize("classification", [C.UNKNOWN, C.MIXED])
def test_unclassified_legacy_nonruins_surface_exclusion_is_preserved(
    section13_definitions: Section02Definitions, classification: C
) -> None:
    from warhammer40k_core.geometry.terrain import TerrainFeatureKind

    u = section13_definitions.unit(LORD_EXULTANT)
    m = native_models(u, (Pose.at(12, 10, 3),))[0]
    f = replace(
        feature(classification, width=6, depth=6, floor=True, height=3),
        feature_kind=TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
    )
    result = transit(m, (m.pose, Pose.at(14, 10, 3)), keywords=("INFANTRY",), features=(f,))
    assert not result.is_valid
    assert any(v.violation_code == "end_on_forbidden_terrain" for v in result.violations)
    placement = terrain_endpoint_placement_violation(
        model=m,
        unit=u,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        terrain_features=(f,),
        violation_code="s13:legacy",
        placement_label="legacy control",
    )
    assert placement is not None
    assert "cannot end on this terrain feature" in placement.message
