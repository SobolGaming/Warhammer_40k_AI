from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.movement_legality import (
    EngagementMovementPolicy,
    EngagementMovementPolicyPayload,
    MovementCapabilitySet,
    MovementCapabilitySetPayload,
    MovementLegalityContext,
    MovementLegalityContextPayload,
    MovementLegalityError,
    MovementLegalityResult,
    MovementLegalityResultPayload,
    MovementLegalityStatus,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.phases.movement import (
    MovementPhaseActionKind,
    movement_mode_for_phase_action,
    movement_phase_action_kind_from_token,
)


def test_fly_resolves_as_capability_not_movement_action() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_tenth()
    capabilities = MovementCapabilitySet.from_keywords(
        ("Fly", "Infantry"),
        ruleset_descriptor=descriptor,
    )

    assert capabilities.has_fly
    assert capabilities.can_move_through_models
    assert capabilities.can_traverse_ruins_walls
    assert (
        movement_mode_for_phase_action(MovementPhaseActionKind.NORMAL_MOVE) is MovementMode.NORMAL
    )
    with pytest.raises(GameLifecycleError, match="Unsupported MovementPhaseActionKind"):
        movement_phase_action_kind_from_token("fly")

    payload = capabilities.to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)

    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert (
        MovementCapabilitySet.from_payload(cast(MovementCapabilitySetPayload, decoded)).to_payload()
        == payload
    )


def test_infantry_and_beast_receive_terrain_traversal_permissions() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_tenth()

    infantry = MovementCapabilitySet.from_keywords(
        ("INFANTRY",),
        ruleset_descriptor=descriptor,
    )
    beast = MovementCapabilitySet.from_keywords(("BEAST",), ruleset_descriptor=descriptor)
    vehicle = MovementCapabilitySet.from_keywords(
        ("VEHICLE",),
        ruleset_descriptor=descriptor,
    )

    assert infantry.can_traverse_ruins_walls
    assert infantry.can_move_through_terrain
    assert beast.can_traverse_ruins_walls
    assert beast.can_move_through_terrain
    assert not vehicle.can_traverse_ruins_walls
    assert not vehicle.can_move_through_terrain


def test_vehicle_monster_restrictions_are_capability_constraints() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_tenth()

    vehicle = MovementCapabilitySet.from_keywords(
        ("Vehicle", "Walker"),
        ruleset_descriptor=descriptor,
    )
    monster = MovementCapabilitySet.from_keywords(
        ("Monster",),
        ruleset_descriptor=descriptor,
    )

    assert vehicle.is_vehicle
    assert vehicle.is_walker
    assert vehicle.blocks_friendly_vehicle_monster_pass_through
    assert monster.is_monster
    assert monster.blocks_friendly_vehicle_monster_pass_through
    assert "vehicle" not in {action.value for action in MovementPhaseActionKind}
    assert "monster" not in {action.value for action in MovementPhaseActionKind}


def test_tenth_normal_move_cannot_end_in_enemy_engagement_range() -> None:
    descriptor = RulesetDescriptor.warhammer_40000_tenth()
    context = MovementLegalityContext.from_keywords(
        keywords=("INFANTRY",),
        ruleset_descriptor=descriptor,
        movement_mode=MovementMode.NORMAL,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )

    result = context.validate_end_position_enemy_engagement(
        enemy_horizontal_distance_inches=1.0,
        enemy_vertical_distance_inches=0.0,
    )
    legal_result = context.validate_end_position_enemy_engagement(
        enemy_horizontal_distance_inches=1.01,
        enemy_vertical_distance_inches=0.0,
    )

    assert context.movement_phase_action == MovementPhaseActionKind.NORMAL_MOVE.value
    assert context.displacement_kind is ModelDisplacementKind.NORMAL_MOVE
    assert context.engagement_policy.horizontal_inches == 1.0
    assert context.engagement_policy.vertical_inches == 5.0
    assert result.status is MovementLegalityStatus.INVALID
    assert not result.is_legal
    assert result.violation_code == "enemy_engagement_range_end_forbidden"
    assert legal_result.is_legal

    payload = context.to_payload()
    result_payload = result.to_payload()
    encoded_context = json.dumps(payload, sort_keys=True)
    encoded_result = json.dumps(result_payload, sort_keys=True)

    assert "<" not in encoded_context
    assert "object at 0x" not in encoded_context
    assert (
        MovementLegalityContext.from_payload(
            cast(MovementLegalityContextPayload, json.loads(encoded_context))
        ).to_payload()
        == payload
    )
    assert (
        MovementLegalityResult.from_payload(
            cast(MovementLegalityResultPayload, json.loads(encoded_result))
        ).to_payload()
        == result_payload
    )


def test_preview_and_unsupported_policy_require_explicit_descriptor() -> None:
    tenth = RulesetDescriptor.warhammer_40000_tenth()
    preview = RulesetDescriptor.warhammer_40000_eleventh_preview()

    with pytest.raises(MovementLegalityError, match="explicit RulesetDescriptor"):
        EngagementMovementPolicy.from_ruleset_descriptor(
            None,
            movement_mode=MovementMode.NORMAL,
        )
    with pytest.raises(MovementLegalityError, match="does not define movement legality"):
        EngagementMovementPolicy.from_ruleset_descriptor(
            tenth,
            movement_mode=MovementMode.FLY_TAKE_TO_SKIES,
        )

    policy = EngagementMovementPolicy.from_ruleset_descriptor(
        preview,
        movement_mode=MovementMode.FLY_TAKE_TO_SKIES,
    )

    assert policy.horizontal_inches == 2.0
    assert policy.may_transit_enemy_engagement
    assert not policy.may_end_in_enemy_engagement
    assert policy.movement_mode is MovementMode.FLY_TAKE_TO_SKIES

    payload = policy.to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert (
        EngagementMovementPolicy.from_payload(
            cast(EngagementMovementPolicyPayload, json.loads(encoded))
        )
        == policy
    )
