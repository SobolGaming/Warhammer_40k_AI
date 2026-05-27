from __future__ import annotations

import json
from dataclasses import replace
from datetime import date

import pytest

from warhammer40k_core.core.objectives import ObjectiveAnchorKind
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    ChargeEndpointRequirement,
    ChargeTargetSelectionTiming,
    CoherencyPolicyDescriptor,
    CoherencyPolicyKind,
    CoverEffect,
    MovementMode,
    MovementModePolicy,
    MovementPolicyDescriptor,
    ObjectivePolicyDescriptor,
    RulesetDescriptor,
    RulesetDescriptorError,
    SetupStepKind,
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


def test_descriptor_hash_includes_setup_and_battle_phase_sequences() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_tenth()
    payload = descriptor.to_payload()

    assert payload["setup_sequence"]["steps"] == [
        SetupStepKind.MUSTER_ARMIES.value,
        SetupStepKind.SELECT_MISSION.value,
        SetupStepKind.CREATE_BATTLEFIELD.value,
        SetupStepKind.DETERMINE_ATTACKER_DEFENDER.value,
        SetupStepKind.SELECT_SECONDARY_MISSIONS.value,
        SetupStepKind.DECLARE_BATTLE_FORMATIONS.value,
        SetupStepKind.DEPLOY_ARMIES.value,
        SetupStepKind.REDEPLOY_UNITS.value,
        SetupStepKind.DETERMINE_FIRST_TURN.value,
        SetupStepKind.RESOLVE_PREBATTLE_ACTIONS.value,
    ]
    assert payload["battle_phase_sequence"]["phases"] == [
        BattlePhaseKind.COMMAND.value,
        BattlePhaseKind.MOVEMENT.value,
        BattlePhaseKind.SHOOTING.value,
        BattlePhaseKind.CHARGE.value,
        BattlePhaseKind.FIGHT.value,
    ]

    payload["battle_phase_sequence"]["phases"] = [
        BattlePhaseKind.COMMAND.value,
        BattlePhaseKind.SHOOTING.value,
        BattlePhaseKind.MOVEMENT.value,
        BattlePhaseKind.CHARGE.value,
        BattlePhaseKind.FIGHT.value,
    ]

    with pytest.raises(RulesetDescriptorError, match="descriptor_hash"):
        RulesetDescriptor.from_payload(payload)


def test_ruleset_descriptors_capture_engagement_and_movement_mode_differences() -> None:
    tenth = RulesetDescriptor.warhammer_40000_tenth()
    preview = RulesetDescriptor.warhammer_40000_eleventh_preview()

    tenth_normal = tenth.movement_policy.policy_for_mode(MovementMode.NORMAL)
    preview_normal = preview.movement_policy.policy_for_mode(MovementMode.NORMAL)

    assert tenth.engagement_policy.horizontal_inches == 1.0
    assert tenth.engagement_policy.vertical_inches == 5.0
    assert preview.engagement_policy.horizontal_inches == 2.0
    assert preview.engagement_policy.vertical_inches == 5.0
    assert not tenth_normal.may_transit_enemy_engagement
    assert not tenth_normal.may_end_in_enemy_engagement
    assert preview_normal.may_transit_enemy_engagement
    assert not preview_normal.may_end_in_enemy_engagement

    preview_fly = preview.movement_policy.policy_for_mode(MovementMode.FLY_TAKE_TO_SKIES)
    assert preview_fly.movement_distance_modifier == -2.0
    assert preview_fly.ignores_vertical_distance
    assert preview_fly.ignores_models
    assert preview_fly.ignores_terrain


def test_ruleset_descriptors_capture_charge_timing_without_execution() -> None:
    tenth = RulesetDescriptor.warhammer_40000_tenth()
    preview = RulesetDescriptor.warhammer_40000_eleventh_preview()

    assert tenth.charge_policy.target_selection_timing is ChargeTargetSelectionTiming.BEFORE_ROLL
    assert (
        tenth.charge_policy.endpoint_requirement
        is ChargeEndpointRequirement.DECLARED_TARGET_ENGAGEMENT
    )
    assert preview.charge_policy.target_selection_timing is ChargeTargetSelectionTiming.AFTER_ROLL
    assert (
        preview.charge_policy.endpoint_requirement
        is ChargeEndpointRequirement.SELECTED_TARGET_BASE_CONTACT
    )


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

    assert tenth.coherency_policy.policy_kind is CoherencyPolicyKind.NEIGHBOR_COUNT
    assert tenth.coherency_policy.required_neighbors_small_unit == 1
    assert tenth.coherency_policy.required_neighbors_large_unit == 2
    assert tenth.coherency_policy.large_unit_model_count_threshold == 7
    assert tenth.coherency_policy.max_horizontal_inches == 2.0
    assert tenth.coherency_policy.max_vertical_inches == 5.0
    assert tenth.coherency_policy.max_all_models_distance_inches is None
    assert tenth.coherency_policy.max_unit_span_inches is None
    assert preview.coherency_policy.policy_kind is CoherencyPolicyKind.ALL_MODELS_WITHIN_DISTANCE
    assert preview.coherency_policy.required_neighbors_small_unit is None
    assert preview.coherency_policy.required_neighbors_large_unit is None
    assert preview.coherency_policy.large_unit_model_count_threshold is None
    assert preview.coherency_policy.max_horizontal_inches is None
    assert preview.coherency_policy.max_vertical_inches is None
    assert preview.coherency_policy.max_all_models_distance_inches == 9.0
    assert not tenth.terrain_visibility_policy.hidden_supported
    assert tenth.terrain_visibility_policy.cover_effect is CoverEffect.SAVE_BONUS
    assert preview.terrain_visibility_policy.hidden_supported
    assert preview.terrain_visibility_policy.hidden_detection_range_inches == 15.0
    assert preview.terrain_visibility_policy.hidden_requires_keywords == ("Hidden",)
    assert preview.terrain_visibility_policy.hidden_requires_terrain_area_occupancy
    assert preview.fly_policy.take_to_the_skies_supported
    assert preview.fly_policy.movement_penalty_inches == 2.0
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


def test_tenth_coherency_descriptor_round_trips_with_threshold_seven() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_tenth()
    payload = descriptor.coherency_policy.to_payload()

    assert payload["policy_kind"] == CoherencyPolicyKind.NEIGHBOR_COUNT.value
    assert payload["large_unit_model_count_threshold"] == 7
    assert CoherencyPolicyDescriptor.from_payload(payload).to_payload() == payload


def test_preview_coherency_descriptor_uses_all_models_distance_policy() -> None:
    policy = RulesetDescriptor.warhammer_40000_eleventh_preview().coherency_policy

    assert policy.policy_kind is CoherencyPolicyKind.ALL_MODELS_WITHIN_DISTANCE
    assert policy.max_all_models_distance_inches == 9.0
    assert policy.required_neighbors_small_unit is None
    assert policy.max_horizontal_inches is None


def test_coherency_policy_rejects_invalid_mixed_policy_fields() -> None:
    with pytest.raises(RulesetDescriptorError, match="requires small-unit"):
        CoherencyPolicyDescriptor(
            policy_kind=CoherencyPolicyKind.NEIGHBOR_COUNT,
            required_neighbors_small_unit=None,
            max_horizontal_inches=2.0,
            max_vertical_inches=5.0,
        )
    with pytest.raises(RulesetDescriptorError, match="both be set or unset"):
        CoherencyPolicyDescriptor(
            policy_kind=CoherencyPolicyKind.NEIGHBOR_COUNT,
            required_neighbors_small_unit=1,
            required_neighbors_large_unit=2,
            large_unit_model_count_threshold=None,
            max_horizontal_inches=2.0,
            max_vertical_inches=5.0,
        )
    with pytest.raises(RulesetDescriptorError, match="must not set neighbor-count"):
        CoherencyPolicyDescriptor(
            policy_kind=CoherencyPolicyKind.ALL_MODELS_WITHIN_DISTANCE,
            required_neighbors_small_unit=1,
            max_all_models_distance_inches=9.0,
        )
    with pytest.raises(RulesetDescriptorError, match="greater than 0"):
        CoherencyPolicyDescriptor(
            policy_kind=CoherencyPolicyKind.ALL_MODELS_WITHIN_DISTANCE,
            max_all_models_distance_inches=0.0,
        )


def test_descriptor_hash_changes_if_coherency_policy_changes() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_tenth()
    changed = replace(
        descriptor,
        coherency_policy=CoherencyPolicyDescriptor(
            policy_kind=CoherencyPolicyKind.NEIGHBOR_COUNT,
            required_neighbors_small_unit=1,
            required_neighbors_large_unit=2,
            large_unit_model_count_threshold=8,
            max_horizontal_inches=2.0,
            max_vertical_inches=5.0,
        ),
        descriptor_hash="",
    )

    assert changed.descriptor_hash != descriptor.descriptor_hash
