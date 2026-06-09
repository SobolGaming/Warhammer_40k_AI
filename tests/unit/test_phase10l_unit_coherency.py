from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import (
    CoherencyPolicyDescriptor,
    CoherencyPolicyKind,
    RulesetDescriptor,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelDisplacementKind,
    ModelPlacement,
    PlacementError,
    UnitPlacement,
)
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.unit_coherency import (
    MovementRollbackRecord,
    MovementRollbackRecordPayload,
    UnitCoherencyContext,
    UnitCoherencyError,
    UnitCoherencyResult,
    UnitCoherencyResultPayload,
    UnitCoherencyStatus,
    UnitCoherencyViolation,
    assert_battlefield_units_in_coherency,
    resolve_unit_movement_endpoint_coherency,
    unit_coherency_status_from_token,
    unit_placement_coherency_result,
)
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


def test_eleventh_five_model_unit_requires_one_neighbor_per_model() -> None:
    context = UnitCoherencyContext.from_ruleset_descriptor(
        RulesetDescriptor.warhammer_40000_eleventh(),
        unit_instance_id="army-alpha:intercessor-unit-1",
    )

    result = context.validate_models(
        (
            _model("model-1", x=0.0),
            _model("model-2", x=2.5),
            _model("model-3", x=5.0),
            _model("model-4", x=7.5),
            _model("model-5", x=10.0),
        )
    )

    assert result.is_coherent
    assert result.offending_model_instance_ids == ()


def test_eleventh_two_disconnected_two_model_groups_are_not_coherent() -> None:
    context = UnitCoherencyContext.from_ruleset_descriptor(
        RulesetDescriptor.warhammer_40000_eleventh(),
        unit_instance_id="army-alpha:split-unit",
    )

    result = context.validate_models(
        (
            _model("model-1", x=0.0),
            _model("model-2", x=3.0),
            _model("model-3", x=50.0),
            _model("model-4", x=53.0),
        )
    )

    assert not result.is_coherent
    assert "unit_coherency_not_single_group" in {
        violation.violation_code for violation in result.violations
    }
    assert any(
        violation.violation_code == "unit_coherency_not_single_group"
        for violation in result.violations
    )


def test_eleventh_large_unit_with_two_locally_coherent_clusters_is_not_coherent() -> None:
    context = UnitCoherencyContext.from_ruleset_descriptor(
        RulesetDescriptor.warhammer_40000_eleventh(),
        unit_instance_id="army-alpha:split-large-unit",
    )

    result = context.validate_models(
        (
            _model("model-1", x=0.0, y=0.0),
            _model("model-2", x=0.0, y=3.0),
            _model("model-3", x=3.0, y=0.0),
            _model("model-4", x=3.0, y=3.0),
            _model("model-5", x=50.0, y=0.0),
            _model("model-6", x=50.0, y=3.0),
            _model("model-7", x=53.0, y=0.0),
            _model("model-8", x=53.0, y=3.0),
        )
    )

    assert not result.is_coherent
    assert "unit_coherency_not_single_group" in {
        violation.violation_code for violation in result.violations
    }
    assert all(violation.neighbor_count is None for violation in result.violations)


def test_eleventh_seven_model_unit_requires_one_neighbor_per_model_and_span_limit() -> None:
    context = UnitCoherencyContext.from_ruleset_descriptor(
        RulesetDescriptor.warhammer_40000_eleventh(),
        unit_instance_id="army-alpha:boyz-unit-1",
    )

    result = context.validate_models(
        tuple(_model(f"model-{index}", x=(index - 1) * 1.5) for index in range(1, 8))
    )

    assert result.is_coherent
    assert result.offending_model_instance_ids == ()


def test_eleventh_unit_span_limit_is_enforced_after_neighbor_coherency() -> None:
    context = UnitCoherencyContext.from_ruleset_descriptor(
        RulesetDescriptor.warhammer_40000_eleventh(),
        unit_instance_id="army-alpha:span-unit-1",
    )

    result = context.validate_models(
        tuple(_model(f"model-{index}", x=(index - 1) * 3.0) for index in range(1, 6))
    )

    assert not result.is_coherent
    assert {violation.violation_code for violation in result.violations} == {"unit_span_exceeded"}
    assert result.violations[0].max_unit_span_inches == 9.0


def test_eleventh_broken_coherency_identifies_offending_model_ids() -> None:
    context = UnitCoherencyContext.from_ruleset_descriptor(
        RulesetDescriptor.warhammer_40000_eleventh(),
        unit_instance_id="army-alpha:intercessor-unit-1",
    )

    result = context.validate_models(
        (
            _model("model-1", x=0.0),
            _model("model-2", x=2.5),
            _model("model-3", x=5.0),
            _model("model-4", x=7.5),
            _model("model-5", x=4.0, y=4.0),
        )
    )

    assert not result.is_coherent
    assert result.offending_model_instance_ids == ("model-5",)
    assert result.violations[0].model_instance_id == "model-5"
    assert result.violations[0].violation_code == "insufficient_coherency_neighbors"


def test_all_models_within_distance_policy_validates_pairwise_distance() -> None:
    context = UnitCoherencyContext.from_ruleset_descriptor(
        _descriptor_with_all_models_distance_coherency(),
        unit_instance_id="army-alpha:all-models-distance-unit-1",
    )

    result = context.validate_models(
        (
            _model("model-1", x=0.0),
            _model("model-2", x=10.0),
            _model("model-3", x=12.0),
        )
    )

    assert not result.is_coherent
    assert result.offending_model_instance_ids == ("model-1", "model-3")
    assert result.violations[0].violation_code == "all_models_distance_exceeded"
    assert result.violations[0].related_model_instance_ids == ("model-3",)
    assert result.violations[1].related_model_instance_ids == ("model-1",)


def test_invalid_normal_move_endpoint_rolls_back_to_previous_placement() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    scenario = _scenario()
    before = scenario.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    attempted = _with_model_pose(
        before,
        model_index=-1,
        pose=Pose.at(x=50.0, y=50.0, z=0.0, facing_degrees=0.0),
    )

    resolved, result, rollback = resolve_unit_movement_endpoint_coherency(
        scenario=scenario,
        ruleset_descriptor=descriptor,
        before=before,
        attempted=attempted,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )

    assert not result.is_coherent
    assert resolved == before
    assert rollback is not None
    assert rollback.unit_instance_id == before.unit_instance_id
    assert rollback.displacement_kind is ModelDisplacementKind.NORMAL_MOVE
    assert rollback.before_placement == before
    assert rollback.attempted_placement == attempted
    assert rollback.coherency_result == result


def test_movement_endpoint_coherency_rejects_attempted_missing_model_even_if_coherent() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    scenario = _scenario()
    before = scenario.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    attempted = replace(before, model_placements=before.model_placements[:-1])

    with pytest.raises(UnitCoherencyError, match="same model_instance_ids"):
        resolve_unit_movement_endpoint_coherency(
            scenario=scenario,
            ruleset_descriptor=descriptor,
            before=before,
            attempted=attempted,
            displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        )


def test_movement_endpoint_coherency_rejects_attempted_extra_or_swapped_model() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    scenario = _scenario()
    before = scenario.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    extra_placement = ModelPlacement(
        army_id=before.army_id,
        player_id=before.player_id,
        unit_instance_id=before.unit_instance_id,
        model_instance_id=f"{before.unit_instance_id}:extra-model:999",
        pose=before.model_placements[-1].pose,
    )

    for attempted in (
        replace(before, model_placements=(*before.model_placements, extra_placement)),
        replace(before, model_placements=(*before.model_placements[:-1], extra_placement)),
    ):
        with pytest.raises(UnitCoherencyError, match="same model_instance_ids"):
            resolve_unit_movement_endpoint_coherency(
                scenario=scenario,
                ruleset_descriptor=descriptor,
                before=before,
                attempted=attempted,
                displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
            )


def test_movement_endpoint_coherency_rejects_army_or_player_drift() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    scenario = _scenario()
    before = scenario.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    player_drift_attempt = UnitPlacement(
        army_id=before.army_id,
        player_id="player-c",
        unit_instance_id=before.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=placement.army_id,
                player_id="player-c",
                unit_instance_id=placement.unit_instance_id,
                model_instance_id=placement.model_instance_id,
                pose=placement.pose,
            )
            for placement in before.model_placements
        ),
    )
    army_drift_attempt = scenario.battlefield_state.unit_placement_by_id(
        "army-beta:intercessor-unit-2"
    )

    for attempted in (player_drift_attempt, army_drift_attempt):
        with pytest.raises(UnitCoherencyError, match="same unit"):
            resolve_unit_movement_endpoint_coherency(
                scenario=scenario,
                ruleset_descriptor=descriptor,
                before=before,
                attempted=attempted,
                displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
            )


def test_deployment_placement_outside_coherency_is_rejected() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    scenario = _scenario()
    placed_army = scenario.battlefield_state.placed_army_for_player("player-a")
    other_army = scenario.battlefield_state.placed_army_for_player("player-b")
    broken_unit = _with_model_pose(
        placed_army.unit_placements[0],
        model_index=-1,
        pose=Pose.at(x=50.0, y=50.0, z=0.0, facing_degrees=0.0),
    )
    broken_scenario = BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=BattlefieldRuntimeState(
            battlefield_id=scenario.battlefield_state.battlefield_id,
            placed_armies=(
                replace(placed_army, unit_placements=(broken_unit,)),
                other_army,
            ),
        ),
    )

    with pytest.raises(PlacementError, match="must be set up in coherency"):
        assert_battlefield_units_in_coherency(
            scenario=broken_scenario,
            ruleset_descriptor=descriptor,
        )


def test_coherency_result_and_rollback_payloads_round_trip() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    context = UnitCoherencyContext.from_ruleset_descriptor(
        descriptor,
        unit_instance_id="army-alpha:intercessor-unit-1",
    )
    result = context.validate_models(
        (
            _model("model-1", x=0.0),
            _model("model-2", x=30.0),
        )
    )
    scenario = _scenario()
    before = scenario.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    attempted = _with_model_pose(
        before,
        model_index=-1,
        pose=Pose.at(x=50.0, y=50.0, z=0.0, facing_degrees=0.0),
    )
    rollback = MovementRollbackRecord(
        unit_instance_id=before.unit_instance_id,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        before_placement=before,
        attempted_placement=attempted,
        coherency_result=result,
    )

    result_payload = cast(
        UnitCoherencyResultPayload,
        json.loads(json.dumps(result.to_payload(), sort_keys=True)),
    )
    rollback_payload = cast(
        MovementRollbackRecordPayload,
        json.loads(json.dumps(rollback.to_payload(), sort_keys=True)),
    )

    assert "<" not in json.dumps(result_payload, sort_keys=True)
    assert "object at 0x" not in json.dumps(result_payload, sort_keys=True)
    assert UnitCoherencyResult.from_payload(result_payload).to_payload() == result_payload
    assert MovementRollbackRecord.from_payload(rollback_payload).to_payload() == rollback_payload


def test_single_model_context_payload_and_coherent_move_endpoint_round_trip() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    context = UnitCoherencyContext.from_ruleset_descriptor(
        descriptor,
        unit_instance_id="army-alpha:character-unit-1",
    )
    context_payload = json.loads(json.dumps(context.to_payload(), sort_keys=True))
    result = UnitCoherencyContext.from_payload(context_payload).validate_models(
        (_model("model-1", x=0.0),)
    )
    scenario = _scenario()
    before = scenario.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    attempted = UnitPlacement(
        army_id=before.army_id,
        player_id=before.player_id,
        unit_instance_id=before.unit_instance_id,
        model_placements=tuple(
            placement.with_pose(
                Pose.at(
                    x=placement.pose.position.x + 1.0,
                    y=placement.pose.position.y,
                    z=placement.pose.position.z,
                    facing_degrees=placement.pose.facing.degrees,
                )
            )
            for placement in before.model_placements
        ),
    )
    resolved, move_result, rollback = resolve_unit_movement_endpoint_coherency(
        scenario=scenario,
        ruleset_descriptor=descriptor,
        before=before,
        attempted=attempted,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )

    assert result.is_coherent
    assert result.model_instance_ids == ("model-1",)
    assert resolved == attempted
    assert move_result.is_coherent
    assert rollback is None


def test_coherency_value_objects_fail_fast_on_invalid_shapes() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    violation = UnitCoherencyViolation(
        model_instance_id="model-1",
        violation_code="insufficient_coherency_neighbors",
        neighbor_count=0,
        required_neighbor_count=1,
        max_horizontal_inches=2.0,
        max_vertical_inches=5.0,
    )

    with pytest.raises(UnitCoherencyError, match="requires violations"):
        UnitCoherencyResult(
            status=UnitCoherencyStatus.BROKEN,
            ruleset_descriptor_hash=descriptor.descriptor_hash,
            unit_instance_id="unit-1",
            coherency_policy=descriptor.coherency_policy,
            model_instance_ids=("model-1",),
        )
    with pytest.raises(UnitCoherencyError, match="must not include violations"):
        UnitCoherencyResult(
            status=UnitCoherencyStatus.COHERENT,
            ruleset_descriptor_hash=descriptor.descriptor_hash,
            unit_instance_id="unit-1",
            coherency_policy=descriptor.coherency_policy,
            model_instance_ids=("model-1",),
            violations=(violation,),
        )
    with pytest.raises(UnitCoherencyError, match="must be in model_instance_ids"):
        UnitCoherencyResult(
            status=UnitCoherencyStatus.BROKEN,
            ruleset_descriptor_hash=descriptor.descriptor_hash,
            unit_instance_id="unit-1",
            coherency_policy=descriptor.coherency_policy,
            model_instance_ids=("model-2",),
            violations=(violation,),
        )
    payload = UnitCoherencyResult(
        status=UnitCoherencyStatus.BROKEN,
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        unit_instance_id="unit-1",
        coherency_policy=descriptor.coherency_policy,
        model_instance_ids=("model-1",),
        violations=(violation,),
    ).to_payload()
    payload["offending_model_instance_ids"] = []
    with pytest.raises(UnitCoherencyError, match="offending_model_instance_ids"):
        UnitCoherencyResult.from_payload(payload)
    with pytest.raises(UnitCoherencyError, match="Unsupported UnitCoherencyStatus"):
        unit_coherency_status_from_token("bad-status")
    with pytest.raises(UnitCoherencyError, match="requires an explicit RulesetDescriptor"):
        UnitCoherencyContext.from_ruleset_descriptor(
            cast(RulesetDescriptor, "bad-descriptor"),
            unit_instance_id="unit-1",
        )
    with pytest.raises(UnitCoherencyError, match="CoherencyPolicyDescriptor"):
        UnitCoherencyContext(
            ruleset_descriptor_hash=descriptor.descriptor_hash,
            unit_instance_id="unit-1",
            coherency_policy=cast(CoherencyPolicyDescriptor, "bad-policy"),
        )
    with pytest.raises(UnitCoherencyError, match="must not be empty"):
        UnitCoherencyContext.from_ruleset_descriptor(
            descriptor,
            unit_instance_id="unit-1",
        ).validate_models(())
    with pytest.raises(UnitCoherencyError, match="must contain Model values"):
        UnitCoherencyContext.from_ruleset_descriptor(
            descriptor,
            unit_instance_id="unit-1",
        ).validate_models(cast(tuple[Model, ...], ("bad-model",)))
    with pytest.raises(UnitCoherencyError, match="duplicate model_ids"):
        UnitCoherencyContext.from_ruleset_descriptor(
            descriptor,
            unit_instance_id="unit-1",
        ).validate_models((_model("model-1", x=0.0), _model("model-1", x=3.0)))
    with pytest.raises(UnitCoherencyError, match="must not be negative"):
        UnitCoherencyViolation(
            model_instance_id="model-1",
            violation_code="bad",
            neighbor_count=-1,
        )
    with pytest.raises(UnitCoherencyError, match="must be greater than 0"):
        UnitCoherencyViolation(
            model_instance_id="model-1",
            violation_code="bad",
            max_horizontal_inches=0.0,
        )
    with pytest.raises(UnitCoherencyError, match="must be a string"):
        unit_coherency_status_from_token(1)
    with pytest.raises(UnitCoherencyError, match="scenario must be a scenario"):
        unit_placement_coherency_result(
            scenario=cast(BattlefieldScenario, "bad-scenario"),
            ruleset_descriptor=descriptor,
            unit_placement=_scenario().battlefield_state.unit_placement_by_id(
                "army-alpha:intercessor-unit-1"
            ),
        )


def test_movement_rollback_record_rejects_mismatched_shapes() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    scenario = _scenario()
    before = scenario.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    attempted = _with_model_pose(
        before,
        model_index=-1,
        pose=Pose.at(x=50.0, y=50.0, z=0.0, facing_degrees=0.0),
    )
    _resolved, result, _rollback = resolve_unit_movement_endpoint_coherency(
        scenario=scenario,
        ruleset_descriptor=descriptor,
        before=before,
        attempted=attempted,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )
    coherent_result = UnitCoherencyContext.from_ruleset_descriptor(
        descriptor,
        unit_instance_id=before.unit_instance_id,
    ).validate_models(tuple(_model(f"model-{index}", x=float(index)) for index in range(1, 3)))

    with pytest.raises(UnitCoherencyError, match="must be broken"):
        MovementRollbackRecord(
            unit_instance_id=before.unit_instance_id,
            displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
            before_placement=before,
            attempted_placement=before,
            coherency_result=coherent_result,
        )
    with pytest.raises(UnitCoherencyError, match="before_placement must match"):
        MovementRollbackRecord(
            unit_instance_id="army-alpha:other-unit",
            displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
            before_placement=before,
            attempted_placement=attempted,
            coherency_result=result,
        )


def _model(model_id: str, *, x: float, y: float = 0.0, z: float = 0.0) -> Model:
    return Model(
        model_id=model_id,
        pose=Pose.at(x=x, y=y, z=z),
        base=CircularBase(radius=0.5),
        volume=ModelVolume(height=2.0),
    )


def _scenario() -> BattlefieldScenario:
    return create_deterministic_battlefield_scenario(
        battlefield_id="phase10l-unit-battlefield",
        armies=_mustered_armies(),
    )


def _mustered_armies() -> tuple[ArmyDefinition, ...]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return (
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
    )


def _muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )


def _descriptor_with_all_models_distance_coherency() -> RulesetDescriptor:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    return replace(
        descriptor,
        coherency_policy=CoherencyPolicyDescriptor(
            policy_kind=CoherencyPolicyKind.ALL_MODELS_WITHIN_DISTANCE,
            max_all_models_distance_inches=9.0,
        ),
        descriptor_hash="",
    )


def _with_model_pose(
    unit_placement: UnitPlacement,
    *,
    model_index: int,
    pose: Pose,
) -> UnitPlacement:
    model_placements = list(unit_placement.model_placements)
    model_placements[model_index] = ModelPlacement(
        army_id=unit_placement.army_id,
        player_id=unit_placement.player_id,
        unit_instance_id=unit_placement.unit_instance_id,
        model_instance_id=model_placements[model_index].model_instance_id,
        pose=pose,
    )
    return replace(unit_placement, model_placements=tuple(model_placements))
