from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battle_shock import BattleShockedUnitState
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelDisplacementKind,
    UnitPlacement,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    DesperateEscapeRequirement,
    DesperateEscapeRequirementReason,
    DesperateEscapeRoll,
    FallBackActionResult,
    FallBackModeKind,
    FellBackUnitState,
    MovementPhaseActionKind,
    MovementPhaseStepKind,
    resolve_fall_back_move,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.unit_coherency import (
    MovementRollbackRecord,
    UnitCoherencyResult,
    unit_placement_coherency_result,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack

_ONE_FAILED_DESPERATE_ESCAPE_GAME_ID = "phase10o-one-v2-0000"
_TWO_FAILED_DESPERATE_ESCAPE_GAME_ID = "phase10o-two-fixed-new-0005"
_ALL_FAILED_DESPERATE_ESCAPE_GAME_ID = "phase10o-five-fixed-0272"
_ORDERED_FALL_BACK_OPTION_ID = (
    f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.ORDERED_RETREAT.value}"
)
_DESPERATE_FALL_BACK_OPTION_ID = (
    f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.DESPERATE_ESCAPE.value}"
)


def test_fall_back_domain_payloads_round_trip_without_object_reprs() -> None:
    requirement = DesperateEscapeRequirement(
        requirement_id="phase10o-desperate-escape-000001",
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
        model_instance_id="army-alpha:intercessor-unit-1:core-intercessor-like:001",
        reasons=(DesperateEscapeRequirementReason.ENEMY_MODEL_OVERFLIGHT,),
        enemy_model_ids=("army-beta:intercessor-unit-2:core-intercessor-like:001",),
    )
    roll_state = DiceRollManager("phase10o-rolls").roll_fixed(
        requirement.roll_spec(),
        [2],
    )
    roll = DesperateEscapeRoll.from_roll_state(
        requirement=requirement,
        roll_state=roll_state,
    )
    fell_back_state = FellBackUnitState(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
        desperate_escape_rolls=(roll,),
    )

    requirement_payload = json.loads(json.dumps(requirement.to_payload(), sort_keys=True))
    roll_payload = json.loads(json.dumps(roll.to_payload(), sort_keys=True))
    state_payload = json.loads(json.dumps(fell_back_state.to_payload(), sort_keys=True))
    blob = json.dumps(
        {
            "requirement": requirement_payload,
            "roll": roll_payload,
            "state": state_payload,
        },
        sort_keys=True,
    )

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert DesperateEscapeRequirement.from_payload(requirement_payload) == requirement
    assert DesperateEscapeRoll.from_payload(roll_payload) == roll
    assert FellBackUnitState.from_payload(state_payload) == fell_back_state
    assert roll.is_failed
    assert not fell_back_state.can_shoot
    assert not fell_back_state.can_declare_charge


def test_fall_back_allows_engagement_transit_but_rejects_endpoint_in_engagement() -> None:
    scenario = _engaged_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    valid_resolution = resolve_fall_back_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_fall_back_witness(unit_placement, first_model_end_pose=Pose.at(6.0, 12.0)),
    )
    invalid_resolution = resolve_fall_back_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_fall_back_witness(unit_placement, first_model_end_pose=Pose.at(5.8, 6.0)),
    )

    assert valid_resolution.is_valid
    assert not invalid_resolution.is_valid
    assert (
        invalid_resolution.path_validation_results[0].violations[0].violation_code
        == "enemy_engagement_range_end_forbidden"
    )


def test_fall_back_enemy_model_overflight_creates_one_desperate_escape_requirement() -> None:
    scenario = _engaged_scenario(enemy_pose=Pose.at(6.0, 8.0, facing_degrees=180.0))
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    resolution = resolve_fall_back_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_fall_back_witness(unit_placement, first_model_end_pose=Pose.at(6.0, 12.0)),
    )

    assert resolution.is_valid
    assert len(resolution.desperate_escape_requirements) == 1
    requirement = resolution.desperate_escape_requirements[0]
    assert requirement.model_instance_id == unit_placement.model_placements[0].model_instance_id
    assert requirement.reasons == (DesperateEscapeRequirementReason.ENEMY_MODEL_OVERFLIGHT,)
    assert requirement.enemy_model_ids == (
        "army-beta:intercessor-unit-2:core-intercessor-like:001",
    )


def test_fly_and_titanic_fall_back_overflight_avoid_desperate_escape_requirement() -> None:
    for keywords in (("FLY", "INFANTRY"), ("TITANIC", "VEHICLE")):
        scenario = _engaged_scenario(
            enemy_pose=Pose.at(6.0, 8.0, facing_degrees=180.0),
            active_keywords=keywords,
        )
        unit_placement = scenario.battlefield_state.unit_placement_by_id(
            "army-alpha:intercessor-unit-1"
        )
        resolution = resolve_fall_back_move(
            scenario=scenario,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            unit_placement=unit_placement,
            path_witness=_fall_back_witness(
                unit_placement,
                first_model_end_pose=Pose.at(6.0, 12.0),
            ),
        )

        assert resolution.is_valid
        assert resolution.desperate_escape_requirements == ()


def test_battle_shocked_fall_back_requires_desperate_escape_for_every_model() -> None:
    scenario = _engaged_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    resolution = resolve_fall_back_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_fall_back_witness(unit_placement, first_model_end_pose=Pose.at(6.0, 12.0)),
        battle_shocked_unit_ids=("army-alpha:intercessor-unit-1",),
    )

    assert resolution.is_valid
    assert len(resolution.desperate_escape_requirements) == len(unit_placement.model_placements)
    assert all(
        DesperateEscapeRequirementReason.BATTLE_SHOCKED in requirement.reasons
        for requirement in resolution.desperate_escape_requirements
    )


def test_failed_desperate_escape_removes_selected_model_and_records_fell_back_state() -> None:
    lifecycle, action_request = _advance_to_fall_back_action_request(
        game_id=_ONE_FAILED_DESPERATE_ESCAPE_GAME_ID,
    )
    fall_back_status = _submit_result(
        lifecycle,
        request=action_request,
        option_id=_DESPERATE_FALL_BACK_OPTION_ID,
        result_id="phase10o-result-000004",
    )
    removal_request = _decision_request(fall_back_status)

    assert removal_request.decision_type == SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE
    selected_option = removal_request.options[0]
    status = _submit_result(
        lifecycle,
        request=removal_request,
        option_id=selected_option.option_id,
        result_id="phase10o-result-000005",
    )
    state = _state(lifecycle)
    fell_back_state = state.fell_back_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
    )
    terminal_event = _last_event_payload(lifecycle, "movement_activation_completed")
    batch = _transition_batch_from_event_payload(terminal_event)
    selected_option_payload = cast(dict[str, object], selected_option.payload)
    destroyed_model_ids = tuple(cast(list[str], selected_option_payload["destroyed_model_ids"]))
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None

    assert status.status_kind is not None
    assert fell_back_state is not None
    assert not fell_back_state.can_shoot
    assert not fell_back_state.can_declare_charge
    assert destroyed_model_ids
    assert set(destroyed_model_ids) <= set(battlefield_state.removed_model_ids)
    assert set(destroyed_model_ids).isdisjoint(battlefield_state.placed_model_ids())
    assert len(batch.removals) == len(destroyed_model_ids)
    assert {removal.model_instance_id for removal in batch.removals} == set(destroyed_model_ids)
    assert all(
        removal.removal_kind is BattlefieldRemovalKind.DESTROYED for removal in batch.removals
    )
    assert all(removal.source_phase == BattlePhase.MOVEMENT.value for removal in batch.removals)
    assert all(
        removal.source_step == MovementPhaseStepKind.MOVE_UNITS.value for removal in batch.removals
    )
    assert all(removal.source_rule_id == "desperate_escape" for removal in batch.removals)
    assert batch.displacements
    assert all(
        displacement.displacement_kind is ModelDisplacementKind.FALL_BACK
        for displacement in batch.displacements
    )
    assert terminal_event["movement_phase_action"] == MovementPhaseActionKind.FALL_BACK.value
    assert terminal_event["desperate_escape_rolls"] == [
        roll.to_payload() for roll in fell_back_state.desperate_escape_rolls
    ]

    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    assert GameLifecycle.from_payload(payload).to_payload() == lifecycle.to_payload()


def test_fall_back_without_desperate_escape_completes_immediately() -> None:
    lifecycle, movement_status = _advance_to_movement_unit_selection(_config())
    _move_first_enemy_model_into_side_engagement(lifecycle)
    action_status = _submit_result(
        lifecycle,
        request=_decision_request(movement_status),
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase10o-result-000006",
    )
    action_request = _decision_request(action_status)

    status = _submit_result(
        lifecycle,
        request=action_request,
        option_id=_ORDERED_FALL_BACK_OPTION_ID,
        result_id="phase10o-result-000007",
    )
    status = _decline_optional_stratagem_if_pending(
        lifecycle,
        status=status,
        result_id="phase10o-decline-fire-overwatch",
    )
    state = _state(lifecycle)
    fell_back_state = state.fell_back_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
    )
    terminal_event = _last_event_payload(lifecycle, "movement_activation_completed")
    batch = _transition_batch_from_event_payload(terminal_event)

    assert status.decision_request is not None
    assert status.decision_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert fell_back_state is not None
    assert fell_back_state.desperate_escape_rolls == ()
    assert terminal_event["movement_phase_action"] == MovementPhaseActionKind.FALL_BACK.value
    assert terminal_event["desperate_escape_rolls"] == []
    assert terminal_event["destroyed_model_ids"] == []
    assert batch.removals == ()
    assert batch.displacements
    assert all(
        displacement.displacement_kind is ModelDisplacementKind.FALL_BACK
        for displacement in batch.displacements
    )


def test_fall_back_payload_round_trip_and_drift_codes() -> None:
    scenario = _engaged_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    resolution = resolve_fall_back_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_fall_back_witness(unit_placement, first_model_end_pose=Pose.at(6.0, 12.0)),
    )
    payload = json.loads(
        json.dumps(
            {
                "witness": resolution.witness.to_payload(),
                **resolution.movement_payload,
            },
            sort_keys=True,
        )
    )

    assert isinstance(payload, dict)
    fall_back_payload = cast(dict[str, JsonValue], payload)
    assert resolution.selected_payload_drift_code(fall_back_payload) is None
    assert FallBackActionResult.from_payload(resolution.to_payload()).to_payload() == (
        resolution.to_payload()
    )

    drifted_witness_payload = {
        "witness": _fall_back_witness(
            unit_placement,
            first_model_end_pose=Pose.at(6.0, 11.0),
        ).to_payload(),
        **resolution.movement_payload,
    }
    assert (
        resolution.selected_payload_drift_code(cast(dict[str, JsonValue], drifted_witness_payload))
        == "fall_back_witness_drift"
    )

    model_movement_payload = cast(dict[str, JsonValue], payload)
    model_movements = cast(list[dict[str, JsonValue]], model_movement_payload["model_movements"])
    model_movements[0]["distance_used_inches"] = 5.0
    assert (
        resolution.selected_payload_drift_code(model_movement_payload)
        == "fall_back_model_movement_witness_drift"
    )


def test_fall_back_revalidates_surviving_coherency_after_desperate_escape_selection() -> None:
    lifecycle, action_request = _advance_to_fall_back_action_request(
        game_id=_TWO_FAILED_DESPERATE_ESCAPE_GAME_ID,
    )
    state = _state(lifecycle)
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    before_battlefield_payload = battlefield_state.to_payload()
    fall_back_status = _submit_result(
        lifecycle,
        request=action_request,
        option_id=_DESPERATE_FALL_BACK_OPTION_ID,
        result_id="phase10o-fall-back-failed-0001",
    )
    removal_request = _decision_request(fall_back_status)
    destroyed_model_ids = (
        "army-alpha:intercessor-unit-1:core-intercessor-like:001",
        "army-alpha:intercessor-unit-1:core-intercessor-like:003",
    )
    destroyed_option_id = "destroy:" + ",".join(destroyed_model_ids)

    assert removal_request.decision_type == SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE
    assert destroyed_option_id in {option.option_id for option in removal_request.options}
    status = _submit_result(
        lifecycle,
        request=removal_request,
        option_id=destroyed_option_id,
        result_id="phase10o-result-000008",
    )
    state = _state(lifecycle)
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert status.message == "Fall Back surviving endpoint violates unit coherency."
    assert battlefield_state.to_payload() == before_battlefield_payload
    assert (
        state.fell_back_unit_state_for_unit(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
        )
        is None
    )
    assert _event_payloads(lifecycle, "movement_activation_completed") == ()


def test_fall_back_destruction_selection_can_make_otherwise_incoherent_endpoint_valid() -> None:
    scenario = _engaged_scenario(enemy_pose=Pose.at(4.0, 6.0, facing_degrees=180.0))
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    destroyed_model_id = "army-alpha:intercessor-unit-1:core-intercessor-like:003"
    attempted_end_poses = {
        "army-alpha:intercessor-unit-1:core-intercessor-like:001": Pose.at(6.0, 12.0),
        "army-alpha:intercessor-unit-1:core-intercessor-like:002": Pose.at(8.0, 12.0),
        destroyed_model_id: Pose.at(10.0, 6.1),
        "army-alpha:intercessor-unit-1:core-intercessor-like:004": Pose.at(10.3, 11.75),
        "army-alpha:intercessor-unit-1:core-intercessor-like:005": Pose.at(12.3, 11.75),
    }
    resolution = resolve_fall_back_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_fall_back_witness_with_end_poses(unit_placement, attempted_end_poses),
        battle_shocked_unit_ids=("army-alpha:intercessor-unit-1",),
    )
    rolls = tuple(
        DesperateEscapeRoll.from_roll_state(
            requirement=requirement,
            roll_state=DiceRollManager("phase10o-rolls").roll_fixed(
                requirement.roll_spec(),
                [1 if requirement.model_instance_id == destroyed_model_id else 3],
            ),
        )
        for requirement in resolution.desperate_escape_requirements
    )
    result = FallBackActionResult.with_desperate_escape_rolls(
        resolution=resolution,
        desperate_escape_rolls=rolls,
    )
    surviving_placement = result.surviving_attempted_placement(
        destroyed_model_ids=(destroyed_model_id,),
    )
    assert surviving_placement is not None

    survivor_coherency = unit_placement_coherency_result(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=surviving_placement,
    )
    batch = result.transition_batch(
        before=unit_placement,
        destroyed_model_ids=(destroyed_model_id,),
    )

    assert not resolution.coherency_result.is_coherent
    assert resolution.rollback_record is None
    assert resolution.is_valid
    assert survivor_coherency.is_coherent
    assert {removal.model_instance_id for removal in batch.removals} == {destroyed_model_id}
    assert destroyed_model_id not in {
        displacement.model_instance_id for displacement in batch.displacements
    }


def test_fall_back_result_rejects_destruction_selection_drift() -> None:
    scenario = _engaged_scenario(enemy_pose=Pose.at(6.0, 8.0, facing_degrees=180.0))
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    resolution = resolve_fall_back_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_fall_back_witness(unit_placement, first_model_end_pose=Pose.at(6.0, 12.0)),
    )
    roll_state = DiceRollManager("phase10o-rolls").roll_fixed(
        resolution.desperate_escape_requirements[0].roll_spec(),
        [1],
    )
    result = FallBackActionResult.with_desperate_escape_rolls(
        resolution=resolution,
        desperate_escape_rolls=(
            DesperateEscapeRoll.from_roll_state(
                requirement=resolution.desperate_escape_requirements[0],
                roll_state=roll_state,
            ),
        ),
    )

    with pytest.raises(GameLifecycleError, match="failed Desperate Escape"):
        result.transition_batch(before=unit_placement, destroyed_model_ids=())
    with pytest.raises(GameLifecycleError, match="eligible"):
        result.transition_batch(
            before=unit_placement,
            destroyed_model_ids=("army-beta:intercessor-unit-2:core-intercessor-like:001",),
        )


def test_fall_back_transition_batch_rejects_unresolved_desperate_escape_requirements() -> None:
    scenario = _engaged_scenario(enemy_pose=Pose.at(6.0, 8.0, facing_degrees=180.0))
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    resolution = resolve_fall_back_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_fall_back_witness(unit_placement, first_model_end_pose=Pose.at(6.0, 12.0)),
    )

    with pytest.raises(GameLifecycleError, match="before Desperate Escape rolls are resolved"):
        resolution.transition_batch(before=unit_placement, destroyed_model_ids=())


def test_fall_back_result_fail_fast_paths_and_surviving_placement() -> None:
    scenario = _engaged_scenario(enemy_pose=Pose.at(6.0, 8.0, facing_degrees=180.0))
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    invalid_resolution = resolve_fall_back_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_fall_back_witness(unit_placement, first_model_end_pose=Pose.at(5.8, 6.0)),
    )
    resolution = resolve_fall_back_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_fall_back_witness(unit_placement, first_model_end_pose=Pose.at(6.0, 12.0)),
    )
    requirement = resolution.desperate_escape_requirements[0]
    roll_state = DiceRollManager("phase10o-rolls").roll_fixed(requirement.roll_spec(), [1])
    failed_roll = DesperateEscapeRoll.from_roll_state(
        requirement=requirement,
        roll_state=roll_state,
    )
    unknown_requirement = replace(
        requirement,
        requirement_id="phase10o-desperate-escape-unknown",
    )
    unknown_roll_state = DiceRollManager("phase10o-rolls").roll_fixed(
        unknown_requirement.roll_spec(),
        [4],
    )
    drifted_requirement = replace(
        requirement,
        enemy_model_ids=("army-beta:intercessor-unit-2:core-intercessor-like:005",),
    )
    drifted_roll_state = DiceRollManager("phase10o-rolls").roll_fixed(
        drifted_requirement.roll_spec(),
        [4],
    )
    result = FallBackActionResult.with_desperate_escape_rolls(
        resolution=resolution,
        desperate_escape_rolls=(failed_roll,),
    )
    destroyed_model_id = unit_placement.model_placements[0].model_instance_id

    with pytest.raises(GameLifecycleError, match="Invalid Fall Back"):
        invalid_resolution.transition_batch(before=unit_placement, destroyed_model_ids=())
    with pytest.raises(GameLifecycleError, match="must be a FallBackActionResult"):
        FallBackActionResult.with_desperate_escape_rolls(
            resolution=cast(FallBackActionResult, object()),
            desperate_escape_rolls=(),
        )
    with pytest.raises(GameLifecycleError, match="must match a Desperate Escape requirement"):
        replace(
            resolution,
            desperate_escape_rolls=(
                DesperateEscapeRoll.from_roll_state(
                    requirement=unknown_requirement,
                    roll_state=unknown_roll_state,
                ),
            ),
        )
    with pytest.raises(GameLifecycleError, match="roll requirement drift"):
        replace(
            resolution,
            desperate_escape_rolls=(
                DesperateEscapeRoll.from_roll_state(
                    requirement=drifted_requirement,
                    roll_state=drifted_roll_state,
                ),
            ),
        )
    partial_resolution = resolve_fall_back_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_fall_back_witness(
            unit_placement,
            first_model_end_pose=Pose.at(6.0, 12.0),
        ),
        battle_shocked_unit_ids=("army-alpha:intercessor-unit-1",),
    )
    partial_requirement = partial_resolution.desperate_escape_requirements[0]
    partial_roll_state = DiceRollManager("phase10o-rolls").roll_fixed(
        partial_requirement.roll_spec(),
        [4],
    )
    with pytest.raises(GameLifecycleError, match="roll either no Desperate Escape tests"):
        replace(
            partial_resolution,
            desperate_escape_rolls=(
                DesperateEscapeRoll.from_roll_state(
                    requirement=partial_requirement,
                    roll_state=partial_roll_state,
                ),
            ),
        )
    with pytest.raises(GameLifecycleError, match="coherency_result must be"):
        replace(
            resolution,
            coherency_result=cast(UnitCoherencyResult, object()),
        )
    with pytest.raises(GameLifecycleError, match="rollback_record must be"):
        replace(
            resolution,
            rollback_record=cast(MovementRollbackRecord, object()),
        )

    surviving = result.surviving_attempted_placement(
        destroyed_model_ids=(destroyed_model_id,),
    )
    assert surviving is not None
    assert destroyed_model_id not in {
        placement.model_instance_id for placement in surviving.model_placements
    }


def test_fall_back_desperate_escape_can_destroy_failed_model_set_without_replay_drift() -> None:
    lifecycle, action_request = _advance_to_fall_back_action_request(
        game_id=_ALL_FAILED_DESPERATE_ESCAPE_GAME_ID,
    )
    fall_back_status = _submit_result(
        lifecycle,
        request=action_request,
        option_id=_DESPERATE_FALL_BACK_OPTION_ID,
        result_id="phase10o-desperate-destroy-set-0001",
    )
    removal_request = _decision_request(fall_back_status)
    all_unit_model_ids = tuple(
        f"army-alpha:intercessor-unit-1:core-intercessor-like:{index:03d}" for index in range(1, 6)
    )
    selected_option = removal_request.options[-1]
    selected_payload = cast(dict[str, object], selected_option.payload)
    destroyed_model_ids = tuple(cast(list[str], selected_payload["destroyed_model_ids"]))

    assert removal_request.decision_type == SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE
    assert set(destroyed_model_ids) < set(all_unit_model_ids)
    status = _submit_result(
        lifecycle,
        request=removal_request,
        option_id=selected_option.option_id,
        result_id="phase10o-result-000009",
    )
    state = _state(lifecycle)
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None

    assert status.decision_request is not None
    assert status.decision_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    surviving_placement = battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    assert set(destroyed_model_ids) <= set(battlefield_state.removed_model_ids)
    assert set(destroyed_model_ids).isdisjoint(battlefield_state.placed_model_ids())
    assert {placement.model_instance_id for placement in surviving_placement.model_placements} == (
        set(all_unit_model_ids) - set(destroyed_model_ids)
    )
    assert (
        state.fell_back_unit_state_for_unit(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
        )
        is not None
    )

    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    assert GameLifecycle.from_payload(payload).to_payload() == lifecycle.to_payload()


def test_game_state_records_and_clears_fell_back_unit_state() -> None:
    lifecycle, _movement_status = _advance_to_movement_unit_selection(_config())
    state = _state(lifecycle)
    fell_back = FellBackUnitState(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
    )

    state.record_fell_back_unit_state(fell_back)

    assert (
        state.fell_back_unit_state_for_unit(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
        )
        == fell_back
    )
    with pytest.raises(GameLifecycleError, match="already exists"):
        state.record_fell_back_unit_state(fell_back)
    for _phase in state.battle_phase_sequence:
        state.advance_to_next_battle_phase()
    assert (
        state.fell_back_unit_state_for_unit(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
        )
        is None
    )


def test_desperate_escape_domain_validators_fail_fast() -> None:
    requirement = DesperateEscapeRequirement(
        requirement_id="phase10o-desperate-escape-000001",
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
        model_instance_id="army-alpha:intercessor-unit-1:core-intercessor-like:001",
        reasons=(DesperateEscapeRequirementReason.BATTLE_SHOCKED,),
    )
    other_requirement = DesperateEscapeRequirement(
        requirement_id="phase10o-desperate-escape-000002",
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-2",
        model_instance_id="army-alpha:intercessor-unit-2:core-intercessor-like:001",
        reasons=(DesperateEscapeRequirementReason.BATTLE_SHOCKED,),
    )
    other_roll_state = DiceRollManager("phase10o-rolls").roll_fixed(
        other_requirement.roll_spec(),
        [4],
    )

    with pytest.raises(GameLifecycleError, match="must belong to unit_instance_id"):
        DesperateEscapeRequirement(
            requirement_id="phase10o-desperate-escape-invalid-000001",
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
            model_instance_id="army-alpha:intercessor-unit-2:core-intercessor-like:001",
            reasons=(DesperateEscapeRequirementReason.BATTLE_SHOCKED,),
        )
    with pytest.raises(GameLifecycleError, match="must not contain duplicates"):
        DesperateEscapeRequirement(
            requirement_id="phase10o-desperate-escape-invalid-000002",
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
            model_instance_id="army-alpha:intercessor-unit-1:core-intercessor-like:001",
            reasons=(
                DesperateEscapeRequirementReason.BATTLE_SHOCKED,
                DesperateEscapeRequirementReason.BATTLE_SHOCKED,
            ),
        )
    with pytest.raises(GameLifecycleError, match="requires enemy_model_ids"):
        DesperateEscapeRequirement(
            requirement_id="phase10o-desperate-escape-invalid-000003",
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
            model_instance_id="army-alpha:intercessor-unit-1:core-intercessor-like:001",
            reasons=(DesperateEscapeRequirementReason.ENEMY_MODEL_OVERFLIGHT,),
        )
    with pytest.raises(GameLifecycleError, match="spec must match requirement"):
        DesperateEscapeRoll(
            requirement=requirement,
            roll_state=other_roll_state,
            value=other_roll_state.current_total,
        )
    with pytest.raises(GameLifecycleError, match="cleanup_point must be end_of_turn"):
        FellBackUnitState(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
            cleanup_point="end_of_phase",
        )


def _advance_to_fall_back_action_request(
    *,
    game_id: str = "phase10o-desperate",
) -> tuple[GameLifecycle, DecisionRequest]:
    lifecycle, movement_status = _advance_to_movement_unit_selection(_config(game_id=game_id))
    _mark_first_unit_battle_shocked(_state(lifecycle))
    _move_first_enemy_model_into_overflight_engagement(lifecycle)
    action_status = _submit_result(
        lifecycle,
        request=_decision_request(movement_status),
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase10o-result-000003",
    )
    action_request = _decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    assert {option.option_id for option in action_request.options} == {
        MovementPhaseActionKind.REMAIN_STATIONARY.value,
        _DESPERATE_FALL_BACK_OPTION_ID,
    }
    return lifecycle, action_request


def _mark_first_unit_battle_shocked(state: GameState) -> None:
    unit_id = "army-alpha:intercessor-unit-1"
    army = state.army_definition_for_player("player-a")
    assert army is not None
    unit = army.unit_by_id(unit_id)
    state.battle_shocked_unit_ids = [unit_id]
    state.battle_shocked_unit_states = [
        BattleShockedUnitState(
            player_id="player-a",
            unit_instance_id=unit_id,
            model_instance_ids=unit.own_model_ids(),
            source_result_id="phase10o-battle-shock-fixture",
            battle_round_started=1,
            expires_at_player_command_phase_start="player-a",
            expires_at_battle_round=2,
        )
    ]


def _advance_to_movement_unit_selection(
    config: GameConfig,
) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    first_status = lifecycle.advance_until_decision_or_terminal()
    assert _decision_request(first_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    second_status = _submit_result(
        lifecycle,
        request=_decision_request(first_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10o-result-000001",
    )
    assert _decision_request(second_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    movement_status = _submit_result(
        lifecycle,
        request=_decision_request(second_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10o-result-000002",
    )
    assert _decision_request(movement_status).decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    return lifecycle, movement_status


def _submit_result(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=option_id,
        )
    )


def _decline_optional_stratagem_if_pending(
    lifecycle: GameLifecycle,
    *,
    status: LifecycleStatus,
    result_id: str,
) -> LifecycleStatus:
    request = _decision_request(status)
    if request.decision_type != STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        return status
    return lifecycle.submit_decision(
        DecisionResult(
            result_id=result_id,
            request_id=request.request_id,
            decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=stratagem_decline_payload(),
        )
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.decision_request is not None
    return status.decision_request


def _state(lifecycle: GameLifecycle) -> GameState:
    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is not None
    return lifecycle.state


def _engaged_scenario(
    *,
    enemy_pose: Pose | None = None,
    active_keywords: tuple[str, ...] = ("INFANTRY",),
) -> BattlefieldScenario:
    scenario = _scenario()
    active_unit_id = "army-alpha:intercessor-unit-1"
    friendly = scenario.battlefield_state.unit_placement_by_id(active_unit_id)
    enemy = scenario.battlefield_state.unit_placement_by_id("army-beta:intercessor-unit-2")
    first_friendly_pose = friendly.model_placements[0].pose
    updated_enemy = _with_first_model_pose(
        enemy,
        enemy_pose
        or Pose.at(
            first_friendly_pose.position.x + 2.0,
            first_friendly_pose.position.y,
            first_friendly_pose.position.z,
            facing_degrees=180.0,
        ),
    )
    updated_armies = tuple(
        replace(
            army,
            units=tuple(
                replace(unit, keywords=active_keywords)
                if unit.unit_instance_id == active_unit_id
                else unit
                for unit in army.units
            ),
        )
        for army in scenario.armies
    )
    return BattlefieldScenario(
        armies=updated_armies,
        battlefield_state=scenario.battlefield_state.with_unit_placement(updated_enemy),
    )


def _scenario() -> BattlefieldScenario:
    config = _config()
    return create_deterministic_battlefield_scenario(
        battlefield_id="phase10o-battlefield",
        armies=tuple(
            muster_army(catalog=config.army_catalog, request=request)
            for request in config.army_muster_requests
        ),
    )


def _config(*, game_id: str = "phase10o-desperate") -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id=game_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase10o-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1", "intercessor-unit-2"),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-2",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2025_26_mission_pack(),
        mission_pool_entry_id="mission-a",
        terrain_layout_id="layout-1",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_id="core-combined-arms",
        ),
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
    )


def _move_first_enemy_model_into_overflight_engagement(lifecycle: GameLifecycle) -> None:
    state = _state(lifecycle)
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    friendly = battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    enemy = battlefield_state.unit_placement_by_id("army-beta:intercessor-unit-2")
    first_friendly_pose = friendly.model_placements[0].pose
    target_pose = Pose.at(
        first_friendly_pose.position.x,
        first_friendly_pose.position.y + 2.0,
        first_friendly_pose.position.z,
        facing_degrees=180.0,
    )
    updated_enemy = _translated_enemy_unit(enemy, first_model_pose=target_pose)
    state.battlefield_state = battlefield_state.with_unit_placement(updated_enemy)


def _move_first_enemy_model_into_side_engagement(lifecycle: GameLifecycle) -> None:
    state = _state(lifecycle)
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    friendly = battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    enemy = battlefield_state.unit_placement_by_id("army-beta:intercessor-unit-2")
    first_friendly_pose = friendly.model_placements[0].pose
    target_pose = Pose.at(
        first_friendly_pose.position.x - 2.0,
        first_friendly_pose.position.y,
        first_friendly_pose.position.z,
        facing_degrees=180.0,
    )
    updated_enemy = _with_first_model_pose(enemy, target_pose)
    state.battlefield_state = battlefield_state.with_unit_placement(updated_enemy)


def _with_first_model_pose(unit_placement: UnitPlacement, pose: Pose) -> UnitPlacement:
    first, *rest = unit_placement.model_placements
    return unit_placement.with_model_placements((first.with_pose(pose), *rest))


def _translated_enemy_unit(
    unit_placement: UnitPlacement,
    *,
    first_model_pose: Pose,
) -> UnitPlacement:
    first = unit_placement.model_placements[0]
    delta_x = first_model_pose.position.x - first.pose.position.x
    delta_y = first_model_pose.position.y - first.pose.position.y
    delta_z = first_model_pose.position.z - first.pose.position.z
    return unit_placement.with_model_placements(
        tuple(
            placement.with_pose(
                Pose.at(
                    placement.pose.position.x + delta_x,
                    placement.pose.position.y + delta_y,
                    placement.pose.position.z + delta_z,
                    facing_degrees=first_model_pose.facing.degrees,
                )
            )
            for placement in unit_placement.model_placements
        )
    )


def _fall_back_witness(
    unit_placement: UnitPlacement,
    *,
    first_model_end_pose: Pose,
) -> PathWitness:
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for index, placement in enumerate(unit_placement.model_placements):
        start = placement.pose
        end = (
            first_model_end_pose
            if index == 0
            else Pose.at(
                start.position.x,
                start.position.y + 6.0,
                start.position.z,
                facing_degrees=start.facing.degrees,
            )
        )
        midpoint = Pose.at(
            (start.position.x + end.position.x) / 2.0,
            (start.position.y + end.position.y) / 2.0,
            (start.position.z + end.position.z) / 2.0,
            facing_degrees=(start.facing.degrees + end.facing.degrees) / 2.0,
        )
        model_paths.append((placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(tuple(model_paths))


def _fall_back_witness_with_end_poses(
    unit_placement: UnitPlacement,
    end_poses_by_model_id: dict[str, Pose],
) -> PathWitness:
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement in unit_placement.model_placements:
        start = placement.pose
        end = end_poses_by_model_id.get(
            placement.model_instance_id,
            Pose.at(
                start.position.x,
                start.position.y + 6.0,
                start.position.z,
                facing_degrees=start.facing.degrees,
            ),
        )
        midpoint = Pose.at(
            (start.position.x + end.position.x) / 2.0,
            (start.position.y + end.position.y) / 2.0,
            (start.position.z + end.position.z) / 2.0,
            facing_degrees=(start.facing.degrees + end.facing.degrees) / 2.0,
        )
        model_paths.append((placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(tuple(model_paths))


def _last_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, object]:
    for event in reversed(lifecycle.decision_controller.event_log.records):
        if event.event_type == event_type:
            assert isinstance(event.payload, dict)
            return cast(dict[str, object], event.payload)
    raise AssertionError(f"Missing event type: {event_type}")


def _event_payloads(lifecycle: GameLifecycle, event_type: str) -> tuple[dict[str, object], ...]:
    payloads: list[dict[str, object]] = []
    for event in lifecycle.decision_controller.event_log.records:
        if event.event_type == event_type:
            assert isinstance(event.payload, dict)
            payloads.append(cast(dict[str, object], event.payload))
    return tuple(payloads)


def _transition_batch_from_event_payload(
    payload: dict[str, object],
) -> BattlefieldTransitionBatch:
    transition_payload = cast(BattlefieldTransitionBatchPayload, payload["transition_batch"])
    return BattlefieldTransitionBatch.from_payload(transition_payload)
