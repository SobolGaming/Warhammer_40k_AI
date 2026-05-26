from __future__ import annotations

import json
from datetime import date

import pytest

from warhammer40k_core.core.objectives import ObjectiveAnchorKind
from warhammer40k_core.core.ruleset_descriptor import (
    ChargeTargetSelectionTiming,
    CoverEffect,
    MovementMode,
    MovementModePolicy,
    MovementPolicyDescriptor,
    ObjectivePolicyDescriptor,
    RulesetDescriptor,
    RulesetDescriptorError,
    TerrainObjectiveControlPolicy,
)


def test_ruleset_descriptor_payload_round_trips_without_object_reprs() -> None:
    descriptors = (
        RulesetDescriptor.warhammer_40000_tenth(source_date=date(2023, 6, 24)),
        RulesetDescriptor.warhammer_40000_eleventh_preview(),
    )

    for descriptor in descriptors:
        payload = descriptor.to_payload()
        blob = json.dumps(payload, sort_keys=True)

        assert "<" not in blob
        assert "object at 0x" not in blob
        assert len(descriptor.descriptor_hash) == 64
        assert RulesetDescriptor.from_payload(json.loads(blob)).to_payload() == payload


def test_descriptor_hash_rejects_policy_payload_drift() -> None:
    payload = RulesetDescriptor.warhammer_40000_tenth().to_payload()
    for movement_mode in payload["movement_policy"]["movement_modes"]:
        if movement_mode["movement_mode"] == MovementMode.NORMAL.value:
            movement_mode["may_transit_enemy_engagement"] = True

    with pytest.raises(RulesetDescriptorError, match="descriptor_hash"):
        RulesetDescriptor.from_payload(payload)


def test_ruleset_descriptors_capture_engagement_and_movement_mode_differences() -> None:
    tenth = RulesetDescriptor.warhammer_40000_tenth()
    preview = RulesetDescriptor.warhammer_40000_eleventh_preview()

    tenth_normal = tenth.movement_policy.policy_for_mode(MovementMode.NORMAL)
    preview_normal = preview.movement_policy.policy_for_mode(MovementMode.NORMAL)

    assert tenth.engagement_policy.horizontal_inches == 1.0
    assert tenth.engagement_policy.vertical_inches == 5.0
    assert not tenth_normal.may_transit_enemy_engagement
    assert not tenth_normal.may_end_in_enemy_engagement
    assert preview_normal.may_transit_enemy_engagement
    assert not preview_normal.may_end_in_enemy_engagement


def test_ruleset_descriptors_capture_charge_timing_without_execution() -> None:
    tenth = RulesetDescriptor.warhammer_40000_tenth()
    preview = RulesetDescriptor.warhammer_40000_eleventh_preview()

    assert tenth.charge_policy.target_selection_timing is ChargeTargetSelectionTiming.BEFORE_ROLL
    assert tenth.charge_policy.endpoint_requires_declared_target_engagement
    assert not tenth.charge_policy.endpoint_allows_any_enemy_engagement
    assert preview.charge_policy.target_selection_timing is ChargeTargetSelectionTiming.AFTER_ROLL
    assert not preview.charge_policy.endpoint_requires_declared_target_engagement
    assert preview.charge_policy.endpoint_allows_any_enemy_engagement


def test_ruleset_descriptors_capture_objective_anchor_policy() -> None:
    tenth = RulesetDescriptor.warhammer_40000_tenth()
    preview = RulesetDescriptor.warhammer_40000_eleventh_preview()

    assert tenth.objective_policy.supported_anchor_kinds == (ObjectiveAnchorKind.POINT,)
    assert preview.objective_policy.supported_anchor_kinds == (
        ObjectiveAnchorKind.POINT,
        ObjectiveAnchorKind.TERRAIN,
    )
    assert (
        preview.objective_policy.terrain_objective_control_policy
        is TerrainObjectiveControlPolicy.UNSUPPORTED
    )


def test_ruleset_descriptors_capture_coherency_hidden_and_fly_policy() -> None:
    tenth = RulesetDescriptor.warhammer_40000_tenth()
    preview = RulesetDescriptor.warhammer_40000_eleventh_preview()

    assert tenth.coherency_policy.required_neighbors_small_unit == 1
    assert tenth.coherency_policy.required_neighbors_large_unit == 2
    assert tenth.coherency_policy.large_unit_model_count_threshold == 6
    assert tenth.coherency_policy.max_unit_span_inches is None
    assert not tenth.terrain_visibility_policy.hidden_supported
    assert tenth.terrain_visibility_policy.cover_effect is CoverEffect.SAVE_BONUS
    assert preview.terrain_visibility_policy.hidden_supported
    assert preview.terrain_visibility_policy.hidden_detection_range_inches is None
    assert preview.terrain_visibility_policy.hidden_requires_keywords == ("Hidden",)
    assert preview.terrain_visibility_policy.hidden_requires_terrain_area_occupancy
    assert preview.fly_policy.take_to_the_skies_supported
    assert preview.fly_policy.ignores_vertical_distance


def test_ruleset_descriptor_rejects_duplicate_movement_modes() -> None:
    policy = MovementModePolicy(
        movement_mode=MovementMode.NORMAL,
        may_transit_enemy_engagement=False,
        may_end_in_enemy_engagement=False,
        requires_charge_target=False,
        ignores_vertical_distance=False,
        ignores_models=False,
        ignores_terrain=False,
    )

    with pytest.raises(RulesetDescriptorError):
        MovementPolicyDescriptor(movement_modes=(policy, policy))


def test_objective_policy_rejects_duplicate_anchor_kinds() -> None:
    with pytest.raises(RulesetDescriptorError):
        ObjectivePolicyDescriptor(
            supported_anchor_kinds=(ObjectiveAnchorKind.POINT, ObjectiveAnchorKind.POINT),
            default_point_control_radius_inches=3.0,
            terrain_objective_control_policy=TerrainObjectiveControlPolicy.UNSUPPORTED,
        )
