from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.core.ruleset_descriptor import (
    LineOfSightPolicy,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.engine.battlefield_state import SpatialIndexState
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pose import GeometryError, Point3, Pose
from warhammer40k_core.geometry.terrain import (
    ObstacleVolume,
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)
from warhammer40k_core.geometry.terrain_factory import TerrainFactory
from warhammer40k_core.geometry.visibility import (
    BenefitOfCoverResult,
    BenefitOfCoverResultPayload,
    CoverSourceReason,
    CoverSourceRecord,
    LineOfSightWitness,
    LineOfSightWitnessPayload,
    ModelLineOfSightRecord,
    TerrainVisibilityContext,
    VisibilityBlockerKind,
    VisibilityBlockerRecord,
    VisibilityMetrics,
    VisibilityQuery,
    VisibilityResult,
    visibility_blocker_kind_from_token,
)
from warhammer40k_core.geometry.volume import Model, ModelVolume


def _model(
    model_id: str,
    x: float,
    y: float,
    *,
    z: float = 0.0,
    height: float = 2.0,
    radius: float = 0.5,
) -> Model:
    return Model(
        model_id=model_id,
        pose=Pose.at(x=x, y=y, z=z),
        base=CircularBase(radius=radius),
        volume=ModelVolume(height=height),
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase13a-test")


def _visibility_ruin() -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id="visibility-ruin",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=0.0,
        footprint_center_y_inches=0.0,
        footprint_width_inches=4.0,
        footprint_depth_inches=4.0,
        walls=(
            TerrainWallDefinition(
                wall_id="off-axis-wall",
                center_x_inches=0.0,
                center_y_inches=1.75,
                bottom_z_inches=0.0,
                width_inches=1.0,
                depth_inches=0.1,
                height_inches=3.0,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="ground-floor",
                center_x_inches=0.0,
                center_y_inches=0.0,
                bottom_z_inches=0.0,
                width_inches=4.0,
                depth_inches=4.0,
                thickness_inches=0.1,
            ),
        ),
        source_id="phase13a_visibility_ruin",
    )


def test_eleventh_ruleset_has_explicit_ruins_and_woods_visibility_policies() -> None:
    policy = _ruleset().terrain_visibility_policy
    ruins = policy.policy_for_feature_kind(TerrainFeatureKind.RUINS)
    woods = policy.policy_for_feature_kind(TerrainFeatureKind.WOODS)

    assert ruins.line_of_sight_policy is LineOfSightPolicy.AREA_OBSCURING
    assert ruins.blocks_model_visibility_through_footprint
    assert ruins.blocks_full_visibility_through_footprint
    assert ruins.uses_true_los_when_observer_wholly_within_feature
    assert ruins.uses_true_los_when_target_intersects_feature
    assert ruins.aircraft_uses_true_los_through_feature
    assert not ruins.towering_uses_true_los_through_feature
    assert ruins.towering_uses_true_los_when_wholly_within_feature
    assert woods.line_of_sight_policy is LineOfSightPolicy.DENSE_COVER
    assert not woods.blocks_model_visibility_through_footprint
    assert woods.blocks_full_visibility_through_footprint
    assert woods.uses_true_los_when_observer_wholly_within_feature
    assert not woods.uses_true_los_when_target_intersects_feature
    assert woods.aircraft_uses_true_los_through_feature
    assert woods.towering_uses_true_los_through_feature
    assert not woods.towering_uses_true_los_when_wholly_within_feature
    assert woods.cover_policy.non_stacking


def test_ruins_area_visibility_blocks_los_without_physical_wall_intersection() -> None:
    feature = _visibility_ruin()
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key=SpatialIndexState.from_terrain_features((feature,)).los_cache_key(),
        observer_model=_model("observer", -5.0, 0.0),
        target_models=(_model("target", 5.0, 0.0),),
        terrain_features=(feature,),
    )

    witness = context.resolve_line_of_sight()
    blockers = witness.all_blocker_records()

    assert not witness.unit_visible
    assert witness.visible_model_ids == ()
    assert any(
        record.blocker_kind is VisibilityBlockerKind.TERRAIN_FEATURE
        and record.blocker_id == "visibility-ruin"
        and record.line_of_sight_policy is LineOfSightPolicy.AREA_OBSCURING
        and record.blocks_model_visibility
        for record in blockers
    )
    assert not context.benefit_of_cover(witness).has_benefit


def test_ruins_wall_floor_context_records_physical_wall_blockers_not_floors() -> None:
    feature = TerrainFactory.ruins_fixture(center_x_inches=22.0, center_y_inches=30.0)[0]
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key=SpatialIndexState.from_terrain_features((feature,)).los_cache_key(),
        observer_model=_model("observer", 14.0, 30.0),
        target_models=(_model("target", 30.0, 30.0),),
        terrain_features=(feature,),
    )

    witness = context.resolve_line_of_sight()
    volume_blocker_ids = {
        record.blocker_id
        for record in witness.all_blocker_records()
        if record.blocker_kind is VisibilityBlockerKind.TERRAIN_VOLUME
    }

    assert any(blocker_id.endswith(":east-wall-ground") for blocker_id in volume_blocker_ids)
    assert not any(":floor-" in blocker_id for blocker_id in volume_blocker_ids)


def test_towering_outside_ruin_does_not_ignore_area_visibility() -> None:
    feature = _visibility_ruin()
    cache_key = SpatialIndexState.from_terrain_features((feature,)).los_cache_key()
    witness = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key=cache_key,
        observer_model=_model("observer", -5.0, 0.0),
        target_models=(_model("target", 5.0, 0.0),),
        terrain_features=(feature,),
        observer_keywords=("TOWERING",),
    ).resolve_line_of_sight()

    assert not witness.unit_visible
    assert any(
        record.blocker_id == "visibility-ruin" and record.blocks_model_visibility
        for record in witness.all_blocker_records()
    )
    assert {record.exception_applied for record in witness.all_blocker_records()} == {None}


def test_towering_inside_ruin_and_aircraft_exceptions_are_represented_in_witness_records() -> None:
    feature = _visibility_ruin()
    cache_key = SpatialIndexState.from_terrain_features((feature,)).los_cache_key()
    towering_inside = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key=cache_key,
        observer_model=_model("observer", 0.0, 0.0),
        target_models=(_model("target", 5.0, 0.0),),
        terrain_features=(feature,),
        observer_keywords=("TOWERING",),
    ).resolve_line_of_sight()
    aircraft = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key=cache_key,
        observer_model=_model("observer", -5.0, 0.0),
        target_models=(_model("target", 5.0, 0.0),),
        terrain_features=(feature,),
        target_keywords=("AIRCRAFT",),
    ).resolve_line_of_sight()

    assert towering_inside.unit_visible
    assert towering_inside.unit_fully_visible
    assert {record.exception_applied for record in towering_inside.all_blocker_records()} == {
        "towering_wholly_within"
    }
    assert aircraft.unit_visible
    assert aircraft.unit_fully_visible
    assert {record.exception_applied for record in aircraft.all_blocker_records()} == {"aircraft"}


def test_ruins_target_wholly_within_is_visible_and_preserves_cover_source() -> None:
    feature = _visibility_ruin()
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key=SpatialIndexState.from_terrain_features((feature,)).los_cache_key(),
        observer_model=_model("observer", -5.0, 0.0),
        target_models=(_model("target", 0.0, 0.0),),
        terrain_features=(feature,),
    )

    witness = context.resolve_line_of_sight()
    cover = context.benefit_of_cover(witness)

    assert witness.unit_visible
    assert witness.unit_fully_visible
    assert {record.exception_applied for record in witness.all_blocker_records()} == {
        "target_intersects"
    }
    assert cover.has_benefit
    assert cover.source_feature_ids == ("visibility-ruin",)
    assert CoverSourceReason.WHOLLY_WITHIN_FEATURE in {
        record.reason for record in cover.source_records
    }


def test_ruins_partial_footprint_intersection_is_visible_but_not_wholly_within_cover() -> None:
    feature = _visibility_ruin()
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key=SpatialIndexState.from_terrain_features((feature,)).los_cache_key(),
        observer_model=_model("observer", -5.0, 0.0),
        target_models=(_model("target", 2.25, 0.0),),
        terrain_features=(feature,),
    )

    witness = context.resolve_line_of_sight()
    cover = context.benefit_of_cover(witness)

    assert witness.unit_visible
    assert witness.unit_fully_visible
    assert {record.exception_applied for record in witness.all_blocker_records()} == {
        "target_intersects"
    }
    assert not cover.has_benefit


def test_woods_target_wholly_within_preserves_cover_source() -> None:
    feature = TerrainFactory.woods_fixture(center_x_inches=0.0, center_y_inches=0.0)[0]
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key=SpatialIndexState.from_terrain_features((feature,)).los_cache_key(),
        observer_model=_model("observer", -5.0, 0.0),
        target_models=(_model("target", 0.0, 0.0),),
        terrain_features=(feature,),
    )

    witness = context.resolve_line_of_sight()
    cover = context.benefit_of_cover(witness)

    assert witness.unit_visible
    assert not witness.unit_fully_visible
    assert cover.has_benefit
    assert cover.source_feature_ids == ("woods-alpha",)
    assert CoverSourceReason.WHOLLY_WITHIN_FEATURE in {
        record.reason for record in cover.source_records
    }


def test_observer_wholly_within_woods_sees_out_without_granting_target_cover() -> None:
    feature = TerrainFactory.woods_fixture(center_x_inches=0.0, center_y_inches=0.0)[0]
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key=SpatialIndexState.from_terrain_features((feature,)).los_cache_key(),
        observer_model=_model("observer", 0.0, 0.0),
        target_models=(_model("target", 5.0, 0.0),),
        terrain_features=(feature,),
    )

    witness = context.resolve_line_of_sight()
    cover = context.benefit_of_cover(witness)

    assert witness.unit_visible
    assert witness.unit_fully_visible
    assert {record.exception_applied for record in witness.all_blocker_records()} == {
        "observer_wholly_within"
    }
    assert not cover.has_benefit


def test_woods_target_wholly_within_same_feature_is_not_fully_visible_from_inside() -> None:
    feature = TerrainFactory.woods_fixture(center_x_inches=0.0, center_y_inches=0.0)[0]
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key=SpatialIndexState.from_terrain_features((feature,)).los_cache_key(),
        observer_model=_model("observer", -1.0, 0.0),
        target_models=(_model("target", 1.0, 0.0),),
        terrain_features=(feature,),
    )

    witness = context.resolve_line_of_sight()
    cover = context.benefit_of_cover(witness)

    assert witness.unit_visible
    assert not witness.unit_fully_visible
    assert all(
        not record.blocks_model_visibility
        and record.blocks_full_visibility
        and record.exception_applied is None
        for record in witness.all_blocker_records()
    )
    assert cover.has_benefit
    assert CoverSourceReason.WHOLLY_WITHIN_FEATURE in {
        record.reason for record in cover.source_records
    }


def test_towering_and_aircraft_use_true_los_through_woods_without_cover_source() -> None:
    feature = TerrainFactory.woods_fixture(center_x_inches=0.0, center_y_inches=0.0)[0]
    cache_key = SpatialIndexState.from_terrain_features((feature,)).los_cache_key()
    towering_context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key=cache_key,
        observer_model=_model("observer", -5.0, 0.0),
        target_models=(_model("target", 5.0, 0.0),),
        terrain_features=(feature,),
        observer_keywords=("TOWERING",),
    )
    aircraft_context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key=cache_key,
        observer_model=_model("observer", -5.0, 0.0),
        target_models=(_model("target", 5.0, 0.0),),
        terrain_features=(feature,),
        target_keywords=("AIRCRAFT",),
    )

    towering_witness = towering_context.resolve_line_of_sight()
    aircraft_witness = aircraft_context.resolve_line_of_sight()

    assert towering_witness.unit_visible
    assert towering_witness.unit_fully_visible
    assert {record.exception_applied for record in towering_witness.all_blocker_records()} == {
        "towering"
    }
    assert not towering_context.benefit_of_cover(towering_witness).has_benefit
    assert aircraft_witness.unit_visible
    assert aircraft_witness.unit_fully_visible
    assert {record.exception_applied for record in aircraft_witness.all_blocker_records()} == {
        "aircraft"
    }
    assert not aircraft_context.benefit_of_cover(aircraft_witness).has_benefit


def test_woods_visibility_blocks_full_visibility_and_grants_cover_policy_result() -> None:
    feature = TerrainFactory.woods_fixture(center_x_inches=0.0, center_y_inches=0.0)[0]
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key=SpatialIndexState.from_terrain_features((feature,)).los_cache_key(),
        observer_model=_model("observer", -5.0, 0.0),
        target_models=(_model("target", 5.0, 0.0),),
        terrain_features=(feature,),
    )

    witness = context.resolve_line_of_sight()
    cover = context.benefit_of_cover(witness)

    assert witness.unit_visible
    assert not witness.unit_fully_visible
    assert all(
        not record.blocks_model_visibility and record.blocks_full_visibility
        for record in witness.all_blocker_records()
    )
    assert cover.has_benefit
    assert cover.source_feature_ids == ("woods-alpha",)
    assert cover.source_policy_kinds == (LineOfSightPolicy.DENSE_COVER,)
    assert cover.source_records == (
        CoverSourceRecord(
            feature_id="woods-alpha",
            feature_kind=TerrainFeatureKind.WOODS,
            policy_kind=LineOfSightPolicy.DENSE_COVER,
            reason=CoverSourceReason.NOT_FULLY_VISIBLE_BECAUSE_OF_FEATURE,
        ),
    )
    assert cover.non_stacking


def test_model_volume_participates_in_los_visibility_and_full_visibility() -> None:
    low_wall = ObstacleVolume(
        terrain_id="low-wall",
        bottom_center=Point3(0.0, 0.0, 0.0),
        width=0.5,
        depth=4.0,
        height=1.0,
    )
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key="los:manual-low-wall",
        observer_model=_model("observer", -3.0, 0.0, height=4.0),
        target_models=(_model("target", 3.0, 0.0, height=4.0),),
        terrain_volumes=(low_wall,),
    )

    witness = context.resolve_line_of_sight()

    assert witness.unit_visible
    assert not witness.unit_fully_visible
    assert any(
        record.blocker_kind is VisibilityBlockerKind.TERRAIN_VOLUME
        and record.blocker_id == "low-wall"
        for record in witness.all_blocker_records()
    )


def test_phase13a_model_silhouette_sampling_budget_is_explicit() -> None:
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key="los:manual-sampling-budget",
        observer_model=_model("observer", -3.0, 0.0, height=4.0),
        target_models=(_model("target", 3.0, 0.0, height=4.0),),
    )

    witness = context.resolve_line_of_sight()
    record = witness.model_records[0]

    assert record.checked_ray_count == 49
    assert tuple(record.clear_ray_indices) == tuple(range(49))
    assert witness.unit_visible
    assert witness.unit_fully_visible


def test_los_cache_key_changes_when_terrain_revision_changes() -> None:
    observer = _model("observer", -5.0, 0.0)
    target = _model("target", 5.0, 0.0)
    empty_key = SpatialIndexState.from_terrain_features(()).los_cache_key()
    woods = TerrainFactory.woods_fixture(center_x_inches=0.0, center_y_inches=0.0)[0]
    woods_key = SpatialIndexState.from_terrain_features((woods,)).los_cache_key()

    empty_witness = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key=empty_key,
        observer_model=observer,
        target_models=(target,),
    ).resolve_line_of_sight()
    woods_witness = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key=woods_key,
        observer_model=observer,
        target_models=(target,),
        terrain_features=(woods,),
    ).resolve_line_of_sight()

    assert empty_witness.los_cache_key != woods_witness.los_cache_key
    assert empty_witness.unit_fully_visible
    assert not woods_witness.unit_fully_visible


def test_phase13a_visibility_and_cover_payloads_round_trip_without_object_reprs() -> None:
    feature = TerrainFactory.woods_fixture(center_x_inches=0.0, center_y_inches=0.0)[0]
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key=SpatialIndexState.from_terrain_features((feature,)).los_cache_key(),
        observer_model=_model("observer", -5.0, 0.0),
        target_models=(_model("target", 5.0, 0.0),),
        terrain_features=(feature,),
    )
    witness = context.resolve_line_of_sight()
    cover = context.benefit_of_cover(witness)

    context_payload = json.loads(json.dumps(context.to_payload(), sort_keys=True))
    witness_payload = cast(
        LineOfSightWitnessPayload,
        json.loads(json.dumps(witness.to_payload(), sort_keys=True)),
    )
    cover_payload = cast(
        BenefitOfCoverResultPayload,
        json.loads(json.dumps(cover.to_payload(), sort_keys=True)),
    )

    for payload in (context_payload, witness_payload, cover_payload):
        blob = json.dumps(payload, sort_keys=True)
        assert "<" not in blob
        assert "object at 0x" not in blob

    assert TerrainVisibilityContext.from_payload(context.to_payload()).to_payload() == (
        context.to_payload()
    )
    assert LineOfSightWitness.from_payload(witness_payload).to_payload() == witness.to_payload()
    assert BenefitOfCoverResult.from_payload(cover_payload).to_payload() == cover.to_payload()


def test_phase13a_visibility_objects_fail_fast_on_invalid_shapes() -> None:
    blocker = VisibilityBlockerRecord(
        blocker_kind=VisibilityBlockerKind.TERRAIN_FEATURE,
        blocker_id="woods-alpha",
        ray_index=0,
        terrain_feature_id="woods-alpha",
        terrain_feature_kind=TerrainFeatureKind.WOODS,
        line_of_sight_policy=LineOfSightPolicy.DENSE_COVER,
        blocks_model_visibility=False,
        blocks_full_visibility=True,
    )
    record = ModelLineOfSightRecord(
        target_model_id="target",
        model_visible=True,
        model_fully_visible=False,
        checked_ray_count=1,
        clear_ray_indices=(0,),
        blocker_records=(blocker,),
    )

    with pytest.raises(GeometryError, match="model-visibility blockers"):
        VisibilityBlockerRecord(
            blocker_kind=VisibilityBlockerKind.TERRAIN_FEATURE,
            blocker_id="bad",
            ray_index=0,
            terrain_feature_id="bad",
            terrain_feature_kind=TerrainFeatureKind.WOODS,
            line_of_sight_policy=LineOfSightPolicy.DENSE_COVER,
            blocks_model_visibility=True,
            blocks_full_visibility=False,
        )
    with pytest.raises(GeometryError, match="matching feature ID"):
        VisibilityBlockerRecord(
            blocker_kind=VisibilityBlockerKind.TERRAIN_FEATURE,
            blocker_id="bad",
            ray_index=0,
            terrain_feature_id="other",
            terrain_feature_kind=TerrainFeatureKind.WOODS,
            line_of_sight_policy=LineOfSightPolicy.DENSE_COVER,
            blocks_model_visibility=False,
            blocks_full_visibility=True,
        )
    with pytest.raises(GeometryError, match="clear_ray_indices"):
        ModelLineOfSightRecord(
            target_model_id="target",
            model_visible=False,
            model_fully_visible=False,
            checked_ray_count=1,
            clear_ray_indices=(0,),
        )
    with pytest.raises(GeometryError, match="visible_model_ids"):
        LineOfSightWitness(
            ruleset_descriptor_hash="hash",
            los_cache_key="los:key",
            observer_model_id="observer",
            target_model_ids=("target",),
            visible_model_ids=(),
            fully_visible_model_ids=(),
            unit_visible=True,
            unit_fully_visible=False,
            model_records=(record,),
        )
    with pytest.raises(GeometryError, match="requires source_feature_ids"):
        BenefitOfCoverResult(
            has_benefit=True,
            cover_effect=_ruleset().terrain_visibility_policy.cover_effect,
            source_feature_ids=(),
            source_policy_kinds=(LineOfSightPolicy.DENSE_COVER,),
            source_records=(),
            los_cache_key="los:key",
            target_unit_visible=True,
            target_unit_fully_visible=False,
            non_stacking=True,
            ap_zero_save_bonus_excluded_for_save_3_plus_or_better=True,
        )
    with pytest.raises(GeometryError, match="without benefit"):
        BenefitOfCoverResult(
            has_benefit=False,
            cover_effect=_ruleset().terrain_visibility_policy.cover_effect,
            source_feature_ids=("woods-alpha",),
            source_policy_kinds=(),
            source_records=(),
            los_cache_key="los:key",
            target_unit_visible=True,
            target_unit_fully_visible=False,
            non_stacking=True,
            ap_zero_save_bonus_excluded_for_save_3_plus_or_better=True,
        )


def test_phase13a_visibility_context_and_tokens_fail_fast() -> None:
    observer = _model("observer", -5.0, 0.0)
    target = _model("target", 5.0, 0.0)
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key="los:manual",
        observer_model=observer,
        target_models=(target,),
    )
    witness = context.resolve_line_of_sight()

    with pytest.raises(GeometryError, match="explicit RulesetDescriptor"):
        TerrainVisibilityContext.from_ruleset_descriptor(
            ruleset_descriptor=cast(RulesetDescriptor, object()),
            los_cache_key="los:manual",
            observer_model=observer,
            target_models=(target,),
        )
    with pytest.raises(GeometryError, match="must not include observer"):
        TerrainVisibilityContext.from_ruleset_descriptor(
            ruleset_descriptor=_ruleset(),
            los_cache_key="los:manual",
            observer_model=observer,
            target_models=(observer,),
        )
    with pytest.raises(GeometryError, match="exclude observer and target"):
        TerrainVisibilityContext.from_ruleset_descriptor(
            ruleset_descriptor=_ruleset(),
            los_cache_key="los:manual",
            observer_model=observer,
            target_models=(target,),
            dynamic_model_blockers=(target,),
        )
    with pytest.raises(GeometryError, match="LineOfSightWitness"):
        context.benefit_of_cover(cast(LineOfSightWitness, object()))
    with pytest.raises(GeometryError, match="ruleset hash"):
        context.benefit_of_cover(
            LineOfSightWitness(
                ruleset_descriptor_hash="other-hash",
                los_cache_key=witness.los_cache_key,
                observer_model_id=witness.observer_model_id,
                target_model_ids=witness.target_model_ids,
                visible_model_ids=witness.visible_model_ids,
                fully_visible_model_ids=witness.fully_visible_model_ids,
                unit_visible=witness.unit_visible,
                unit_fully_visible=witness.unit_fully_visible,
                model_records=witness.model_records,
            )
        )
    mismatched_target_context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key="los:manual",
        observer_model=observer,
        target_models=(_model("different-target", 5.0, 1.5),),
    )
    with pytest.raises(GeometryError, match="targets do not match"):
        mismatched_target_context.benefit_of_cover(witness)
    mismatched_observer_context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=_ruleset(),
        los_cache_key="los:manual",
        observer_model=_model("different-observer", -5.0, 1.5),
        target_models=(target,),
    )
    with pytest.raises(GeometryError, match="observer does not match"):
        mismatched_observer_context.benefit_of_cover(witness)
    with pytest.raises(GeometryError, match="VisibilityBlockerKind token"):
        visibility_blocker_kind_from_token("unsupported")
    with pytest.raises(GeometryError, match="must not be empty"):
        VisibilityQuery(rays=())
    with pytest.raises(GeometryError, match="Visible VisibilityResult"):
        VisibilityResult(has_line_of_sight=True, checked_ray_count=1, clear_ray_index=None)


def test_phase13a_primitive_visibility_payloads_fail_fast() -> None:
    point = Point3(0.0, 0.0, 0.0)
    ray = (point, Point3(1.0, 0.0, 0.0))
    terrain = ObstacleVolume(
        terrain_id="wall",
        bottom_center=Point3(0.5, 0.0, 0.0),
        width=0.1,
        depth=1.0,
        height=1.0,
    )
    model = _model("blocker", 0.5, 0.0)

    with pytest.raises(GeometryError, match="rays must be a tuple"):
        VisibilityQuery(rays=cast(tuple[tuple[Point3, Point3], ...], []))
    with pytest.raises(GeometryError, match="static_terrain must be a tuple"):
        VisibilityQuery(
            rays=(ray,),
            static_terrain=cast(tuple[ObstacleVolume, ...], [terrain]),
        )
    with pytest.raises(GeometryError, match="dynamic_model_blockers must be a tuple"):
        VisibilityQuery(
            rays=(ray,),
            dynamic_model_blockers=cast(tuple[Model, ...], [model]),
        )
    with pytest.raises(GeometryError, match="Point3 pairs"):
        VisibilityQuery(rays=cast(tuple[tuple[Point3, Point3], ...], ("bad-ray",)))
    with pytest.raises(GeometryError, match="Point3 pairs"):
        VisibilityQuery(rays=cast(tuple[tuple[Point3, Point3], ...], ((point,),)))
    with pytest.raises(GeometryError, match="duplicate IDs"):
        VisibilityQuery(rays=(ray,), static_terrain=(terrain, terrain))
    with pytest.raises(GeometryError, match="duplicate IDs"):
        VisibilityQuery(rays=(ray,), dynamic_model_blockers=(model, model))

    with pytest.raises(GeometryError, match="has_line_of_sight"):
        VisibilityResult(
            has_line_of_sight=cast(bool, "yes"),
            checked_ray_count=1,
            clear_ray_index=0,
        )
    with pytest.raises(GeometryError, match="positive integer"):
        VisibilityResult(
            has_line_of_sight=False,
            checked_ray_count=0,
            clear_ray_index=None,
        )
    with pytest.raises(GeometryError, match="clear_ray_index must be an integer"):
        VisibilityResult(
            has_line_of_sight=True,
            checked_ray_count=1,
            clear_ray_index=cast(int, "0"),
        )
    with pytest.raises(GeometryError, match="outside checked rays"):
        VisibilityResult(has_line_of_sight=True, checked_ray_count=1, clear_ray_index=1)
    with pytest.raises(GeometryError, match="Blocked VisibilityResult"):
        VisibilityResult(has_line_of_sight=False, checked_ray_count=1, clear_ray_index=0)
    with pytest.raises(GeometryError, match="metrics must be VisibilityMetrics"):
        VisibilityResult(
            has_line_of_sight=True,
            checked_ray_count=1,
            clear_ray_index=0,
            metrics=cast(VisibilityMetrics, object()),
        )
    with pytest.raises(GeometryError, match="must not contain duplicate IDs"):
        VisibilityResult(
            has_line_of_sight=True,
            checked_ray_count=1,
            clear_ray_index=0,
            blocking_terrain_ids=("wall", "wall"),
        )


def test_phase13a_context_tuple_validation_fails_fast() -> None:
    observer = _model("observer", -5.0, 0.0)
    target = _model("target", 5.0, 0.0)
    feature = TerrainFactory.woods_fixture(feature_id="woods-alpha")[0]
    duplicate_feature = TerrainFactory.woods_fixture(feature_id="woods-alpha")[0]
    terrain = ObstacleVolume(
        terrain_id="wall",
        bottom_center=Point3(0.0, 0.0, 0.0),
        width=0.1,
        depth=1.0,
        height=1.0,
    )

    with pytest.raises(GeometryError, match="target_models must not be empty"):
        TerrainVisibilityContext.from_ruleset_descriptor(
            ruleset_descriptor=_ruleset(),
            los_cache_key="los:manual",
            observer_model=observer,
            target_models=(),
        )
    with pytest.raises(GeometryError, match="terrain_features must be a tuple"):
        TerrainVisibilityContext.from_ruleset_descriptor(
            ruleset_descriptor=_ruleset(),
            los_cache_key="los:manual",
            observer_model=observer,
            target_models=(target,),
            terrain_features=cast(tuple[TerrainFeatureDefinition, ...], [feature]),
        )
    with pytest.raises(GeometryError, match="duplicate IDs"):
        TerrainVisibilityContext.from_ruleset_descriptor(
            ruleset_descriptor=_ruleset(),
            los_cache_key="los:manual",
            observer_model=observer,
            target_models=(target,),
            terrain_features=(feature, duplicate_feature),
        )
    with pytest.raises(GeometryError, match="terrain_volumes must be a tuple"):
        TerrainVisibilityContext.from_ruleset_descriptor(
            ruleset_descriptor=_ruleset(),
            los_cache_key="los:manual",
            observer_model=observer,
            target_models=(target,),
            terrain_volumes=cast(tuple[ObstacleVolume, ...], [terrain]),
        )
    with pytest.raises(GeometryError, match="duplicate IDs"):
        TerrainVisibilityContext.from_ruleset_descriptor(
            ruleset_descriptor=_ruleset(),
            los_cache_key="los:manual",
            observer_model=observer,
            target_models=(target,),
            terrain_volumes=(terrain, terrain),
        )
    with pytest.raises(GeometryError, match="duplicate keywords"):
        TerrainVisibilityContext.from_ruleset_descriptor(
            ruleset_descriptor=_ruleset(),
            los_cache_key="los:manual",
            observer_model=observer,
            target_models=(target,),
            observer_keywords=("AIRCRAFT", "aircraft"),
        )
