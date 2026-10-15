from __future__ import annotations

from tests.shared.category_migration.ruleset_descriptor import (
    BattlePhaseKind,
    CoherencyPolicyDescriptor,
    CoherencyPolicyKind,
    MovementMode,
    MovementModePolicy,
    MovementPolicyDescriptor,
    ObjectiveAnchorKind,
    ObjectivePolicyDescriptor,
    RulesetDescriptor,
    RulesetDescriptorError,
    RulesetError,
    RulesetId,
    SetupStepKind,
    TerrainEndpointSupportPolicy,
    TerrainFeatureKind,
    TerrainFeatureMovementPolicy,
    TerrainMovementPolicy,
    TerrainObjectiveControlPolicy,
    TerrainTraversalMode,
    _terrain_feature_policies,
    date,
    json,
    pytest,
    replace,
    tacoma_open_2026,
)


def test_ruleset_descriptor_payload_round_trips_with_eleventh_edition_identity() -> None:
    descriptors = (
        RulesetDescriptor.warhammer_40000_eleventh(source_date=date(2026, 6, 1)),
        RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(),
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
    take_to_the_skies = descriptor.movement_policy.policy_for_mode(MovementMode.FLY_TAKE_TO_SKIES)
    terrain_visibility_policy = descriptor.terrain_visibility_policy

    assert descriptor.engagement_policy.horizontal_inches == 2.0
    assert descriptor.engagement_policy.vertical_inches == 5.0
    assert terrain_visibility_policy.hidden_supported
    assert terrain_visibility_policy.hidden_detection_range_inches == 15.0
    assert terrain_visibility_policy.hidden_gone_to_ground_detection_penalty_inches == 3.0
    assert terrain_visibility_policy.hidden_requires_keywords == ("BEAST", "INFANTRY", "SWARM")
    assert terrain_visibility_policy.hidden_requires_terrain_area_occupancy
    assert terrain_visibility_policy.hidden_lost_after_shooting
    assert not normal_move.may_transit_enemy_engagement
    assert descriptor.objective_policy.supported_anchor_kinds == (
        ObjectiveAnchorKind.POINT,
        ObjectiveAnchorKind.TERRAIN,
    )
    assert descriptor.objective_policy.terrain_objective_control_policy is (
        TerrainObjectiveControlPolicy.TERRAIN_AREA_OCCUPANCY
    )
    assert descriptor.coherency_policy.policy_kind is CoherencyPolicyKind.NEIGHBOR_COUNT
    assert descriptor.coherency_policy.required_neighbors_small_unit == 1
    assert descriptor.coherency_policy.large_unit_model_count_threshold is None
    assert descriptor.coherency_policy.max_unit_span_inches == 9.0
    assert descriptor.fly_policy.take_to_the_skies_supported
    assert descriptor.fly_policy.movement_penalty_inches == 2.0
    assert descriptor.fly_policy.ignores_vertical_distance
    assert descriptor.fly_policy.may_move_through_models
    assert descriptor.fly_policy.may_move_through_terrain
    assert take_to_the_skies.movement_distance_modifier == -2.0
    assert take_to_the_skies.ignores_vertical_distance
    assert take_to_the_skies.ignores_models
    assert take_to_the_skies.ignores_terrain


__all__: list[str] = []
__all__ += ["CoherencyPolicyDescriptor", "MovementModePolicy", "MovementPolicyDescriptor"]
__all__ += ["ObjectivePolicyDescriptor", "TerrainEndpointSupportPolicy", "TerrainFeatureKind"]
__all__ += ["TerrainFeatureMovementPolicy", "TerrainMovementPolicy", "TerrainTraversalMode"]
__all__ += ["_terrain_feature_policies", "replace", "tacoma_open_2026"]
