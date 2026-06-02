from __future__ import annotations

import json
from dataclasses import replace
from datetime import date

import pytest

from warhammer40k_core.core.objectives import ObjectiveAnchorKind
from warhammer40k_core.core.ruleset import RulesetError, RulesetId
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    CoherencyPolicyDescriptor,
    CoherencyPolicyKind,
    MovementMode,
    MovementModePolicy,
    MovementPolicyDescriptor,
    ObjectivePolicyDescriptor,
    RulesetDescriptor,
    RulesetDescriptorError,
    SetupStepKind,
    TerrainEndpointSupportPolicy,
    TerrainFeatureKind,
    TerrainFeatureMovementPolicy,
    TerrainMovementPolicy,
    TerrainObjectiveControlPolicy,
    TerrainTraversalMode,
)


def test_ruleset_descriptor_payload_round_trips_with_eleventh_edition_identity() -> None:
    descriptors = (
        RulesetDescriptor.warhammer_40000_eleventh(source_date=date(2026, 6, 1)),
        RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2025_26(),
    )

    for descriptor in descriptors:
        payload = descriptor.to_payload()
        blob = json.dumps(payload, sort_keys=True)

        assert payload["ruleset_id"]["game"] == "warhammer_40000"
        assert payload["ruleset_id"]["edition"] == "11e"
        assert "<" not in blob
        assert "object at 0x" not in blob
        assert len(descriptor.descriptor_hash) == 64
        assert RulesetDescriptor.from_payload(json.loads(blob)).to_payload() == payload


def test_ruleset_id_rejects_retired_payload_editions() -> None:
    retired_editions = ("".join(("1", "0", "e")), "11e" + "_" + "preview")

    for edition in retired_editions:
        with pytest.raises(RulesetError, match="Unsupported RulesetEdition"):
            RulesetId.from_payload(
                {
                    "game": "warhammer_40000",
                    "edition": edition,
                    "version": "retired",
                }
            )


def test_descriptor_hash_is_deterministic_and_rejects_policy_payload_drift() -> None:
    first = RulesetDescriptor.warhammer_40000_eleventh()
    second = RulesetDescriptor.warhammer_40000_eleventh()

    assert first.descriptor_hash == second.descriptor_hash

    payload = first.to_payload()
    for movement_mode in payload["movement_policy"]["movement_modes"]:
        if movement_mode["movement_mode"] == MovementMode.NORMAL.value:
            movement_mode["may_transit_enemy_engagement"] = True

    with pytest.raises(RulesetDescriptorError, match="descriptor_hash"):
        RulesetDescriptor.from_payload(payload)


def test_descriptor_hash_includes_setup_and_battle_phase_sequences() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
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


def test_eleventh_migration_baseline_has_explicit_policy_data() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    normal_move = descriptor.movement_policy.policy_for_mode(MovementMode.NORMAL)

    assert descriptor.engagement_policy.horizontal_inches == 2.0
    assert descriptor.engagement_policy.vertical_inches == 5.0
    assert not normal_move.may_transit_enemy_engagement
    assert descriptor.objective_policy.supported_anchor_kinds == (ObjectiveAnchorKind.POINT,)
    assert descriptor.coherency_policy.policy_kind is CoherencyPolicyKind.NEIGHBOR_COUNT
    assert descriptor.coherency_policy.required_neighbors_small_unit == 1
    assert descriptor.coherency_policy.large_unit_model_count_threshold is None
    assert descriptor.coherency_policy.max_unit_span_inches == 9.0


def test_eleventh_terrain_movement_policy_uses_two_inch_free_traversal_threshold() -> None:
    policy = RulesetDescriptor.warhammer_40000_eleventh().terrain_movement_policy
    payload = policy.to_payload()

    assert policy.freely_traversable_height_threshold_inches == 2.0
    assert policy.climb_vertical_distance_counts
    assert not policy.may_end_mid_climb
    assert policy.requires_permission_to_move_through_features
    assert policy.infantry_beast_ruins_wall_traversal_mode is TerrainTraversalMode.THROUGH_FEATURE
    assert policy.fly_traversal_mode is TerrainTraversalMode.AIR_PATH
    assert policy.fly_uses_air_path_measurement
    ruins_policy = policy.policy_for_feature_kind(TerrainFeatureKind.RUINS)
    assert ruins_policy.endpoint_support_policy is (
        TerrainEndpointSupportPolicy.ALLOWED_ON_ANY_FLOOR_WITH_NO_OVERHANG
    )
    assert ruins_policy.no_overhang_required
    assert ruins_policy.ground_floor_only_unless_keyword
    assert "INFANTRY" in ruins_policy.through_terrain_allowed_keywords
    assert "FLY" in ruins_policy.upper_floor_allowed_keywords
    barricade_policy = policy.policy_for_feature_kind(TerrainFeatureKind.BARRICADE_AND_FUEL_PIPES)
    assert (
        barricade_policy.endpoint_support_policy is TerrainEndpointSupportPolicy.NOT_ALLOWED_ON_TOP
    )
    assert TerrainMovementPolicy.from_payload(payload).to_payload() == payload


def test_terrain_movement_policy_rejects_invalid_shapes() -> None:
    with pytest.raises(RulesetDescriptorError, match="greater than 0"):
        TerrainMovementPolicy(
            freely_traversable_height_threshold_inches=0.0,
            climb_vertical_distance_counts=True,
            may_end_mid_climb=False,
            requires_permission_to_move_through_features=True,
            infantry_beast_ruins_wall_traversal_mode=TerrainTraversalMode.THROUGH_FEATURE,
            fly_traversal_mode=TerrainTraversalMode.AIR_PATH,
            fly_uses_air_path_measurement=True,
            feature_policies=_terrain_feature_policies(),
        )

    with pytest.raises(RulesetDescriptorError, match="requires AIR_PATH"):
        TerrainMovementPolicy(
            freely_traversable_height_threshold_inches=2.0,
            climb_vertical_distance_counts=True,
            may_end_mid_climb=False,
            requires_permission_to_move_through_features=True,
            infantry_beast_ruins_wall_traversal_mode=TerrainTraversalMode.THROUGH_FEATURE,
            fly_traversal_mode=TerrainTraversalMode.CLIMB,
            fly_uses_air_path_measurement=True,
            feature_policies=_terrain_feature_policies(),
        )

    with pytest.raises(RulesetDescriptorError, match="no-overhang endpoint policy"):
        TerrainFeatureMovementPolicy(
            terrain_feature_kind=TerrainFeatureKind.HILLS,
            can_move_over=True,
            can_move_through=False,
            freely_moved_over_height_inches=2.0,
            endpoint_support_policy=TerrainEndpointSupportPolicy.ALLOWED_ON_TOP_WITH_NO_OVERHANG,
            no_overhang_required=False,
        )


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


def test_eleventh_engagement_and_coherency_descriptors_match_phase14c_values() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    payload = descriptor.coherency_policy.to_payload()

    assert descriptor.engagement_policy.horizontal_inches == 2.0
    assert descriptor.engagement_policy.vertical_inches == 5.0
    assert payload["policy_kind"] == CoherencyPolicyKind.NEIGHBOR_COUNT.value
    assert payload["required_neighbors_small_unit"] == 1
    assert payload["required_neighbors_large_unit"] is None
    assert payload["large_unit_model_count_threshold"] is None
    assert payload["max_horizontal_inches"] == 2.0
    assert payload["max_vertical_inches"] == 5.0
    assert payload["max_unit_span_inches"] == 9.0
    assert CoherencyPolicyDescriptor.from_payload(payload).to_payload() == payload


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
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    changed = replace(
        descriptor,
        coherency_policy=CoherencyPolicyDescriptor(
            policy_kind=CoherencyPolicyKind.NEIGHBOR_COUNT,
            required_neighbors_small_unit=1,
            max_horizontal_inches=2.0,
            max_vertical_inches=5.0,
            max_unit_span_inches=10.0,
        ),
        descriptor_hash="",
    )

    assert changed.descriptor_hash != descriptor.descriptor_hash


def test_descriptor_hash_changes_if_terrain_movement_policy_changes() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    changed = replace(
        descriptor,
        terrain_movement_policy=TerrainMovementPolicy(
            freely_traversable_height_threshold_inches=1.0,
            climb_vertical_distance_counts=True,
            may_end_mid_climb=False,
            requires_permission_to_move_through_features=True,
            infantry_beast_ruins_wall_traversal_mode=TerrainTraversalMode.THROUGH_FEATURE,
            fly_traversal_mode=TerrainTraversalMode.AIR_PATH,
            fly_uses_air_path_measurement=True,
            feature_policies=_terrain_feature_policies(),
        ),
        descriptor_hash="",
    )

    assert changed.descriptor_hash != descriptor.descriptor_hash


def _terrain_feature_policies() -> tuple[TerrainFeatureMovementPolicy, ...]:
    return RulesetDescriptor.warhammer_40000_eleventh().terrain_movement_policy.feature_policies
