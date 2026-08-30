from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.deployment_submission_helpers import (
    default_deployment_pose,
    submit_all_deployments_if_pending,
)
from tests.movement_submission_helpers import (
    submit_action_and_movement_proposal,
    submit_default_movement_proposal_if_pending,
    submit_movement_proposal,
)
from tests.setup_completion_helpers import (
    record_completed_command_occurrences_for_fixture,
    record_current_battlefield_placements_for_fixture,
    record_primary_turn_start_evidence_for_fixture,
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.abilities import AbilityCatalogRecord
from warhammer40k_core.engine.ability_catalog import (
    catalog_ability_records_from_catalog,
)
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelDisplacementKind,
    UnitPlacement,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
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
    _roll_desperate_escape_dice,
    resolve_fall_back_move,
)
from warhammer40k_core.engine.phases.movement_geometry import (
    _enemy_engaged_unit_ids_for_unit_placement,
    _enemy_engagement_model_ids_for_unit,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
    primary_battlefield_departure_id,
    primary_battlefield_departure_states_from_payload,
    record_primary_battlefield_departure,
    validate_primary_battlefield_departure_states,
)
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
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as datasheet_keyword_lexicon_source,
)

_ONE_FAILED_DESPERATE_ESCAPE_GAME_ID = "phase10o-p09a-dice-0003"
_TWO_FAILED_DESPERATE_ESCAPE_GAME_ID = "phase10o-p09a-coherency-0006"
_MULTI_FAILED_DESPERATE_ESCAPE_GAME_ID = "phase10o-terrain-display-02-0001"
_ORDERED_FALL_BACK_OPTION_ID = (
    f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.ORDERED_RETREAT.value}"
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


def test_fall_back_engagement_context_keeps_only_retained_destroyed_enemy_geometry() -> None:
    scenario = _engaged_scenario()
    enemy_unit_id = "army-beta:intercessor-unit-2"
    enemy_placement = scenario.battlefield_state.unit_placement_by_id(enemy_unit_id)
    retained_placement = enemy_placement.model_placements[0]
    distant_placements = tuple(
        placement.with_pose(Pose.at(50.0 + index, 40.0, facing_degrees=180.0))
        for index, placement in enumerate(enemy_placement.model_placements[1:])
    )
    battlefield = scenario.battlefield_state.with_unit_placement(
        enemy_placement.with_model_placements((retained_placement, *distant_placements))
    )
    updated_armies = tuple(
        replace(
            army,
            units=tuple(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=0)
                        if model.model_instance_id == retained_placement.model_instance_id
                        else model
                        for model in unit.own_models
                    ),
                )
                if unit.unit_instance_id == enemy_unit_id
                else unit
                for unit in army.units
            ),
        )
        for army in scenario.armies
    )
    retained_scenario = BattlefieldScenario(
        armies=updated_armies,
        battlefield_state=battlefield,
        present_destroyed_model_ids=(retained_placement.model_instance_id,),
    )
    source_placement = battlefield.unit_placement_by_id("army-alpha:intercessor-unit-1")
    ruleset_descriptor = RulesetDescriptor.warhammer_40000_eleventh()

    assert _enemy_engaged_unit_ids_for_unit_placement(
        scenario=retained_scenario,
        unit_placement=source_placement,
        ruleset_descriptor=ruleset_descriptor,
    ) == (enemy_unit_id,)
    assert _enemy_engagement_model_ids_for_unit(
        scenario=retained_scenario,
        unit_placement=source_placement,
        ruleset_descriptor=ruleset_descriptor,
    ) == ((retained_placement.model_instance_id,), ())

    ordinary_dead_scenario = replace(
        retained_scenario,
        present_destroyed_model_ids=(),
    )
    assert (
        _enemy_engaged_unit_ids_for_unit_placement(
            scenario=ordinary_dead_scenario,
            unit_placement=source_placement,
            ruleset_descriptor=ruleset_descriptor,
        )
        == ()
    )
    assert _enemy_engagement_model_ids_for_unit(
        scenario=ordinary_dead_scenario,
        unit_placement=source_placement,
        ruleset_descriptor=ruleset_descriptor,
    ) == ((), ())


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


def test_generic_movement_transit_auto_passes_enemy_overflight_desperate_escape() -> None:
    scenario = _engaged_scenario(enemy_pose=Pose.at(6.0, 8.0, facing_degrees=180.0))
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    state = _state_for_scenario_with_effects(
        scenario,
        effects=(
            _generic_movement_transit_effect(
                target_unit_instance_id=unit_placement.unit_instance_id
            ),
        ),
    )
    resolution = resolve_fall_back_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        state=state,
        path_witness=_fall_back_witness(unit_placement, first_model_end_pose=Pose.at(6.0, 12.0)),
    )
    battle_shocked_resolution = resolve_fall_back_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        state=state,
        path_witness=_fall_back_witness(unit_placement, first_model_end_pose=Pose.at(6.0, 12.0)),
        battle_shocked_unit_ids=(unit_placement.unit_instance_id,),
    )

    assert resolution.is_valid
    assert resolution.desperate_escape_requirements == ()
    assert len(battle_shocked_resolution.desperate_escape_requirements) == len(
        unit_placement.model_placements
    )
    first_requirement = battle_shocked_resolution.desperate_escape_requirements[0]
    assert first_requirement.reasons == (DesperateEscapeRequirementReason.BATTLE_SHOCKED,)
    assert first_requirement.enemy_model_ids == ()


def test_generic_movement_transit_fall_back_rejects_excluded_titanic_overflight() -> None:
    scenario = _engaged_scenario(
        enemy_pose=Pose.at(6.0, 8.0, facing_degrees=180.0),
        enemy_keywords=("TITANIC",),
    )
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    state = _state_for_scenario_with_effects(
        scenario,
        effects=(
            _generic_movement_transit_effect(
                target_unit_instance_id=unit_placement.unit_instance_id
            ),
        ),
    )

    resolution = resolve_fall_back_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        state=state,
        path_witness=_fall_back_witness(unit_placement, first_model_end_pose=Pose.at(6.0, 12.0)),
    )

    assert not resolution.is_valid
    assert resolution.path_validation_results[0].violations[0].violation_code == (
        "enemy_model_transit_forbidden"
    )
    assert resolution.desperate_escape_requirements == ()


def test_fall_back_full_unit_no_op_witness_emits_only_changed_displacement() -> None:
    base_scenario = _scenario()
    base_unit_placement = base_scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    first_model_pose = base_unit_placement.model_placements[0].pose
    scenario = _engaged_scenario(
        enemy_pose=Pose.at(
            first_model_pose.position.x - 2.0,
            first_model_pose.position.y,
            first_model_pose.position.z,
            facing_degrees=180.0,
        ),
    )
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    moved_model = unit_placement.model_placements[0]
    moved_end_pose = Pose.at(
        moved_model.pose.position.x + 1.0,
        moved_model.pose.position.y + 2.0,
        moved_model.pose.position.z,
        facing_degrees=moved_model.pose.facing.degrees,
    )
    witness = _full_unit_witness_with_only_first_model_moved(
        unit_placement,
        first_model_end_pose=moved_end_pose,
    )

    resolution = resolve_fall_back_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=witness,
    )
    batch = resolution.transition_batch(before=unit_placement, destroyed_model_ids=())
    model_movements = tuple(
        cast(dict[str, object], movement)
        for movement in cast(list[object], resolution.movement_payload["model_movements"])
    )
    no_op_movements = tuple(
        movement for movement in model_movements if movement["start_pose"] == movement["end_pose"]
    )
    displacement = batch.displacements[0]

    assert resolution.is_valid
    assert resolution.desperate_escape_requirements == ()
    assert len(model_movements) == len(unit_placement.model_placements)
    assert len(no_op_movements) == len(unit_placement.model_placements) - 1
    assert batch.removals == ()
    assert len(batch.displacements) == 1
    assert displacement.model_instance_id == moved_model.model_instance_id
    assert displacement.displacement_kind is ModelDisplacementKind.FALL_BACK
    assert displacement.start_pose == moved_model.pose
    assert displacement.end_pose == moved_end_pose
    assert displacement.path_witness is not None
    assert displacement.path_witness.poses_for_model(moved_model.model_instance_id) == (
        witness.poses_for_model(moved_model.model_instance_id)
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


def test_forced_desperate_escape_rolls_every_model() -> None:
    scenario = _engaged_scenario()
    state = _state_for_scenario_with_effects(scenario, effects=())
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    source_rule_id = "phase10o-forced-desperate-escape-source"
    resolution = resolve_fall_back_move(
        scenario=scenario,
        state=state,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_fall_back_witness(
            unit_placement,
            first_model_end_pose=Pose.at(6.0, 12.0),
        ),
        forced_desperate_escape_source_rule_ids=(source_rule_id,),
    )
    decisions = DecisionController()
    rolls = _roll_desperate_escape_dice(
        state=state,
        decisions=decisions,
        resolution=resolution,
    )

    assert len(rolls) == len(unit_placement.model_placements)
    assert all(
        DesperateEscapeRequirementReason.FORCED_BY_RULE in roll.requirement.reasons
        for roll in rolls
    )
    assert not any(
        event.event_type.startswith("forced_desperate_escape_battle_shock")
        for event in decisions.event_log.records
    )


def test_catalog_ability_forces_desperate_escape_on_immediate_fall_back_path() -> None:
    config = _config(
        game_id="phase10o-catalog-forced-desperate-escape",
        with_forced_desperate_escape_ability=True,
    )
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    _move_first_enemy_model_into_side_engagement(lifecycle)
    state = _state(lifecycle)
    target_army = state.army_definition_for_player("player-a")
    assert target_army is not None
    target_unit = target_army.unit_by_id("army-alpha:intercessor-unit-1")
    record = _forced_desperate_escape_catalog_record(config.army_catalog)
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase10o-catalog-select-unit",
            request=_decision_request(movement_status),
            selected_option_id=target_unit.unit_instance_id,
        )
    )
    action_request = _decision_request(action_status)
    proposal_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase10o-catalog-select-ordered-fall-back",
            request=action_request,
            selected_option_id=_ORDERED_FALL_BACK_OPTION_ID,
        )
    )
    proposal_decision_request = _decision_request(proposal_status)
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        proposal_decision_request.payload
    )
    context = proposal_request.context

    assert proposal_decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert context is not None
    assert context["declared_fall_back_mode"] == FallBackModeKind.ORDERED_RETREAT.value
    assert context["fall_back_mode"] == FallBackModeKind.DESPERATE_ESCAPE.value
    assert context["forced_desperate_escape_source_rule_ids"] == [record.definition.source_id]
    sources = cast(list[JsonValue], context["forced_desperate_escape_sources"])
    assert cast(dict[str, JsonValue], sources[0])["catalog_record_id"] == record.record_id

    battlefield = state.battlefield_state
    assert battlefield is not None
    unit_placement = battlefield.unit_placement_by_id(target_unit.unit_instance_id)
    resolution_status = submit_movement_proposal(
        lifecycle,
        request=proposal_decision_request,
        result_id="phase10o-catalog-forced-fall-back-proposal",
        unit_instance_id=target_unit.unit_instance_id,
        movement_phase_action=MovementPhaseActionKind.FALL_BACK,
        movement_mode=MovementMode.FALL_BACK,
        fall_back_mode=FallBackModeKind.DESPERATE_ESCAPE,
        witness=_fall_back_witness(
            unit_placement,
            first_model_end_pose=_fall_back_forward_pose(unit_placement),
        ),
    )

    assert resolution_status.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
    }
    roll_events = _event_payloads(lifecycle, "desperate_escape_roll_resolved")
    assert len(roll_events) == len(unit_placement.model_placements)
    assert all(
        DesperateEscapeRequirementReason.FORCED_BY_RULE.value
        in cast(
            list[str],
            cast(
                dict[str, JsonValue],
                cast(dict[str, JsonValue], event["desperate_escape_roll"])["requirement"],
            )["reasons"],
        )
        for event in roll_events
    )
    battle_shock_event = _last_event_payload(
        lifecycle,
        "forced_desperate_escape_battle_shock_resolved",
    )
    assert battle_shock_event["unit_instance_id"] == target_unit.unit_instance_id
    assert battle_shock_event["source_rule_ids"] == [record.definition.source_id]


def test_failed_desperate_escape_removes_selected_model_and_records_fell_back_state() -> None:
    lifecycle, action_request = _advance_to_fall_back_action_request(
        game_id=_ONE_FAILED_DESPERATE_ESCAPE_GAME_ID,
    )
    state = _state(lifecycle)
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    unit_placement = battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    fall_back_status = submit_action_and_movement_proposal(
        lifecycle,
        request=action_request,
        option_id=_ORDERED_FALL_BACK_OPTION_ID,
        action_result_id="phase10o-result-000004",
        proposal_result_id="phase10o-desperate-failed-proposal",
        unit_instance_id=unit_placement.unit_instance_id,
        movement_phase_action=MovementPhaseActionKind.FALL_BACK,
        movement_mode=MovementMode.FALL_BACK,
        fall_back_mode=FallBackModeKind.DESPERATE_ESCAPE,
        witness=_fall_back_witness(
            unit_placement,
            first_model_end_pose=_fall_back_forward_pose(unit_placement),
        ),
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


def test_fall_back_payload_round_trip() -> None:
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
    assert FallBackActionResult.from_payload(resolution.to_payload()).to_payload() == (
        resolution.to_payload()
    )


def test_fall_back_revalidates_surviving_coherency_after_desperate_escape_selection() -> None:
    lifecycle, action_request = _advance_to_fall_back_action_request(
        game_id=_TWO_FAILED_DESPERATE_ESCAPE_GAME_ID,
    )
    state = _state(lifecycle)
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    before_battlefield_payload = battlefield_state.to_payload()
    unit_placement = battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    fall_back_status = submit_action_and_movement_proposal(
        lifecycle,
        request=action_request,
        option_id=_ORDERED_FALL_BACK_OPTION_ID,
        action_result_id="phase10o-two-failed-action",
        proposal_result_id="phase10o-two-failed-proposal",
        unit_instance_id=unit_placement.unit_instance_id,
        movement_phase_action=MovementPhaseActionKind.FALL_BACK,
        movement_mode=MovementMode.FALL_BACK,
        fall_back_mode=FallBackModeKind.DESPERATE_ESCAPE,
        witness=_fall_back_witness(
            unit_placement,
            first_model_end_pose=_fall_back_forward_pose(unit_placement),
        ),
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
    assert isinstance(surviving_placement, UnitPlacement)

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
        game_id=_MULTI_FAILED_DESPERATE_ESCAPE_GAME_ID,
    )
    fall_back_status = _submit_result(
        lifecycle,
        request=action_request,
        option_id=_ORDERED_FALL_BACK_OPTION_ID,
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
    (departure,) = state.primary_battlefield_departure_states
    expected_source_id = (
        "core-rules:desperate-escape:phase10o-result-000009:army-alpha:intercessor-unit-1"
    )
    assert departure.removal_kind is BattlefieldRemovalKind.DESTROYED
    assert departure.affected_component_unit_instance_ids == ("army-alpha:intercessor-unit-1",)
    assert departure.departed_component_unit_instance_ids == ()
    assert departure.removed_model_instance_ids == tuple(sorted(destroyed_model_ids))
    assert departure.source_id == expected_source_id
    assert departure.occurrence_id == expected_source_id
    assert not state.primary_unit_destruction_states
    assert (
        state.fell_back_unit_state_for_unit(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
        )
        is not None
    )
    completion_payload = cast(
        dict[str, JsonValue],
        next(
            event.payload
            for event in reversed(lifecycle.decision_controller.event_log.records)
            if event.event_type == "movement_activation_completed"
        ),
    )
    assert completion_payload["destroyed_model_ids"] == list(destroyed_model_ids)
    assert completion_payload["desperate_escape_source_mutation_id"] == "phase10o-result-000009"

    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    assert GameLifecycle.from_payload(payload).to_payload() == lifecycle.to_payload()


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("not_object", "payload must be an object"),
        ("missing_field", "payload is missing required field: source_id"),
        ("unexpected_field", "payload contains unexpected field: forged"),
        ("components_not_list", "component_unit_instance_ids must be a list"),
        ("components_empty", "component_unit_instance_ids must not be empty"),
        ("components_duplicate", "component_unit_instance_ids must not contain duplicates"),
        ("affected_not_list", "affected_component_unit_instance_ids must be a list"),
        ("affected_outside_unit", "affected components must belong to the rules unit"),
        ("departed_not_list", "departed_component_unit_instance_ids must be a list"),
        ("departed_outside_affected", "departed components must be affected"),
        ("removed_not_list", "removed_model_instance_ids must be a list"),
        ("removed_duplicate", "removed_model_instance_ids must not contain duplicates"),
        ("battle_round", "battle_round must be a positive integer"),
        ("removal_kind", "removal kind is unsupported"),
        ("source_id", "source_id must not be empty"),
    ],
)
def test_primary_battlefield_departure_payload_fails_closed(
    corruption: str,
    expected_error: str,
) -> None:
    departure = _valid_primary_battlefield_departure()
    payload: object = cast(dict[str, JsonValue], departure.to_payload())
    if corruption == "not_object":
        payload = None
    else:
        assert isinstance(payload, dict)
        if corruption == "missing_field":
            payload.pop("source_id")
        elif corruption == "unexpected_field":
            payload["forged"] = True
        elif corruption == "components_not_list":
            payload["component_unit_instance_ids"] = "unit-a"
        elif corruption == "components_empty":
            payload["component_unit_instance_ids"] = []
        elif corruption == "components_duplicate":
            payload["component_unit_instance_ids"] = ["unit-a", "unit-a"]
        elif corruption == "affected_not_list":
            payload["affected_component_unit_instance_ids"] = "unit-a"
        elif corruption == "affected_outside_unit":
            payload["affected_component_unit_instance_ids"] = ["unit-b"]
        elif corruption == "departed_not_list":
            payload["departed_component_unit_instance_ids"] = "unit-a"
        elif corruption == "departed_outside_affected":
            payload["departed_component_unit_instance_ids"] = ["unit-b"]
        elif corruption == "removed_not_list":
            payload["removed_model_instance_ids"] = "model-a"
        elif corruption == "removed_duplicate":
            payload["removed_model_instance_ids"] = ["model-a", "model-a"]
        elif corruption == "battle_round":
            payload["battle_round"] = 0
        elif corruption == "removal_kind":
            payload["removal_kind"] = "forged-removal"
        elif corruption == "source_id":
            payload["source_id"] = ""
        else:
            raise AssertionError(f"unsupported departure payload corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=expected_error):
        PrimaryBattlefieldDepartureState.from_payload(payload)


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("not_list", "states must be a list"),
        ("untyped", "states must contain typed values"),
        ("game", "game_id drift"),
        ("owner_player", "references an unknown player"),
        ("active_player", "references an unknown player"),
        ("rules_unit", "references an unknown rules unit"),
        ("components", "component identity drift"),
        ("owner", "owner drift"),
        ("removed_model", "model outside its affected components"),
        ("affected_component", "Every affected component must contribute"),
        ("departure_id", "departure_id drift"),
        ("duplicate", "states must be unique"),
    ],
)
def test_primary_battlefield_departure_state_validation_fails_closed(
    corruption: str,
    expected_error: str,
) -> None:
    departure = _valid_primary_battlefield_departure()
    values: object = [departure]
    owner_by_unit_id: dict[str, str] = {"unit-a": "player-a", "unit-b": "player-a"}
    model_ids_by_unit_id: dict[str, tuple[str, ...]] = {
        "unit-a": ("model-a",),
        "unit-b": ("model-b",),
    }
    components_by_id: dict[str, tuple[str, ...]] = {"unit-a": ("unit-a",)}
    if corruption == "not_list":
        values = None
    elif corruption == "untyped":
        values = [departure.to_payload()]
    elif corruption == "game":
        values = [replace(departure, game_id="game-b")]
    elif corruption == "owner_player":
        values = [replace(departure, owner_player_id="player-forged")]
    elif corruption == "active_player":
        values = [replace(departure, active_player_id="player-forged")]
    elif corruption == "rules_unit":
        values = [replace(departure, rules_unit_instance_id="unit-forged")]
    elif corruption == "components":
        values = [
            replace(
                departure,
                component_unit_instance_ids=("unit-a", "unit-b"),
            )
        ]
    elif corruption == "owner":
        values = [replace(departure, owner_player_id="player-b")]
    elif corruption == "removed_model":
        values = [replace(departure, removed_model_instance_ids=("model-forged",))]
    elif corruption == "affected_component":
        values = [
            replace(
                departure,
                component_unit_instance_ids=("unit-a", "unit-b"),
                affected_component_unit_instance_ids=("unit-a", "unit-b"),
            )
        ]
        components_by_id = {"unit-a": ("unit-a", "unit-b")}
    elif corruption == "departure_id":
        values = [replace(departure, departure_id="departure-forged")]
    elif corruption == "duplicate":
        values = [departure, departure]
    else:
        raise AssertionError(f"unsupported departure-state corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=expected_error):
        validate_primary_battlefield_departure_states(
            values,
            game_id="game-a",
            player_ids=("player-a", "player-b"),
            owner_by_unit_id=owner_by_unit_id,
            model_ids_by_unit_id=model_ids_by_unit_id,
            known_rules_unit_components_by_id=components_by_id,
        )


def test_primary_battlefield_departure_collection_and_identity_validation_fail_closed() -> None:
    with pytest.raises(GameLifecycleError, match="payloads must be a list"):
        primary_battlefield_departure_states_from_payload(None)
    with pytest.raises(GameLifecycleError, match="Departed components must be affected"):
        primary_battlefield_departure_id(
            game_id="game-a",
            rules_unit_instance_id="unit-a",
            affected_component_unit_instance_ids=("unit-a",),
            departed_component_unit_instance_ids=("unit-b",),
            removed_model_instance_ids=("model-a",),
            battle_round=1,
            active_player_id="player-a",
            phase=BattlePhase.MOVEMENT.value,
            removal_kind=BattlefieldRemovalKind.DESTROYED,
            occurrence_id="occurrence-a",
            source_id="source-a",
        )


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("state", "tracking requires GameState"),
        ("stage", "can only occur during battle"),
        ("active_phase", "requires active-player phase state"),
        ("affected", "affected components do not belong to the rules unit"),
        ("departed", "departed components must be affected"),
        ("removed_model", "removed models do not belong to an affected component"),
        ("battlefield", "requires battlefield_state"),
        ("still_placed", "removed models must have left the battlefield"),
        ("departed_placed", "departed component must have no current model"),
        ("duplicate", "occurrence already exists"),
        ("affected_not_tuple", "affected_component_unit_instance_ids must be a tuple"),
    ],
)
def test_record_primary_battlefield_departure_fails_closed(
    corruption: str,
    expected_error: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=expected_error):
        _run_primary_battlefield_departure_corruption(corruption)


def _run_primary_battlefield_departure_corruption(corruption: str) -> None:
    if corruption == "state":
        record_primary_battlefield_departure(
            state=cast(GameState, object()),
            rules_unit_instance_id="unit:a",
            affected_component_unit_instance_ids=("unit:a",),
            departed_component_unit_instance_ids=(),
            removed_model_instance_ids=("model:a",),
            removal_kind=BattlefieldRemovalKind.DESTROYED,
            occurrence_id="occurrence:a",
            source_id="source:a",
        )
        return
    lifecycle, _movement_status = _advance_to_movement_unit_selection(_config())
    state = _state(lifecycle)
    battlefield = state.battlefield_state
    if battlefield is None:
        raise AssertionError("departure integrity test requires battlefield state")
    unit_id = "army-alpha:intercessor-unit-1"
    enemy_unit_id = "army-beta:intercessor-unit-2"
    model_id = battlefield.unit_placement_by_id(unit_id).model_placements[0].model_instance_id
    affected: object = (unit_id,)
    departed: tuple[str, ...] = ()
    removed_model_ids = (model_id,)
    if corruption not in {"still_placed", "battlefield"}:
        state.replace_battlefield_state(battlefield.with_removed_models((model_id,)))
    if corruption == "stage":
        state.stage = GameLifecycleStage.SETUP
    elif corruption == "active_phase":
        state.active_player_id = None
    elif corruption == "affected":
        affected = (enemy_unit_id,)
    elif corruption == "departed":
        departed = (enemy_unit_id,)
    elif corruption == "removed_model":
        removed_model_ids = ("army-alpha:intercessor-unit-1:model-forged",)
    elif corruption == "battlefield":
        state.battlefield_state = None
    elif corruption == "departed_placed":
        departed = (unit_id,)
    elif corruption == "affected_not_tuple":
        affected = [unit_id]
    elif corruption == "duplicate":
        record_primary_battlefield_departure(
            state=state,
            rules_unit_instance_id=unit_id,
            affected_component_unit_instance_ids=(unit_id,),
            departed_component_unit_instance_ids=(),
            removed_model_instance_ids=removed_model_ids,
            removal_kind=BattlefieldRemovalKind.DESTROYED,
            occurrence_id="occurrence:departure-validation",
            source_id="source:departure-validation",
        )
    elif corruption != "still_placed":
        raise AssertionError(f"unsupported departure tracking corruption: {corruption}")
    record_primary_battlefield_departure(
        state=state,
        rules_unit_instance_id=unit_id,
        affected_component_unit_instance_ids=cast(tuple[str, ...], affected),
        departed_component_unit_instance_ids=departed,
        removed_model_instance_ids=removed_model_ids,
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        occurrence_id="occurrence:departure-validation",
        source_id="source:departure-validation",
    )


def test_primary_battlefield_departure_is_not_recorded_without_mission_setup() -> None:
    lifecycle, _movement_status = _advance_to_movement_unit_selection(_config())
    state = _state(lifecycle)
    state.mission_setup = None

    assert (
        record_primary_battlefield_departure(
            state=state,
            rules_unit_instance_id="army-alpha:intercessor-unit-1",
            affected_component_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            departed_component_unit_instance_ids=(),
            removed_model_instance_ids=("army-alpha:intercessor-unit-1:core-intercessor-like:001",),
            removal_kind=BattlefieldRemovalKind.DESTROYED,
            occurrence_id="occurrence:no-mission",
            source_id="source:no-mission",
        )
        is None
    )


def _valid_primary_battlefield_departure() -> PrimaryBattlefieldDepartureState:
    departure_id = primary_battlefield_departure_id(
        game_id="game-a",
        rules_unit_instance_id="unit-a",
        affected_component_unit_instance_ids=("unit-a",),
        departed_component_unit_instance_ids=(),
        removed_model_instance_ids=("model-a",),
        battle_round=1,
        active_player_id="player-a",
        phase=BattlePhase.MOVEMENT.value,
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        occurrence_id="occurrence-a",
        source_id="source-a",
    )
    return PrimaryBattlefieldDepartureState(
        departure_id=departure_id,
        game_id="game-a",
        owner_player_id="player-a",
        rules_unit_instance_id="unit-a",
        component_unit_instance_ids=("unit-a",),
        affected_component_unit_instance_ids=("unit-a",),
        departed_component_unit_instance_ids=(),
        removed_model_instance_ids=("model-a",),
        battle_round=1,
        active_player_id="player-a",
        phase=BattlePhase.MOVEMENT.value,
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        occurrence_id="occurrence-a",
        source_id="source-a",
    )


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


def _generic_movement_transit_effect(*, target_unit_instance_id: str) -> PersistingEffect:
    return PersistingEffect(
        effect_id="phase10o-generic-movement-transit",
        source_rule_id="phase10o-source-generic-movement-transit",
        owner_player_id="player-a",
        target_unit_instance_ids=(target_unit_instance_id,),
        started_battle_round=1,
        started_phase=BattlePhase.MOVEMENT,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhase.MOVEMENT,
            player_id="player-a",
        ),
        effect_payload={
            "effect_kind": GENERIC_RULE_EFFECT_KIND,
            "effect": {
                "kind": "movement_transit_permission",
                "parameters": [
                    {"key": "permission", "value": "move_through_models"},
                    {"key": "movement_modes", "value": ["normal", "advance", "fall_back"]},
                    {"key": "model_allegiance", "value": "any"},
                    {"key": "excluded_model_keyword_any", "value": ["TITANIC"]},
                    {"key": "enemy_engagement_range_transit", "value": True},
                    {"key": "enemy_engagement_range_end_allowed", "value": False},
                    {"key": "desperate_escape_tests_auto_passed", "value": True},
                ],
            },
        },
    )


def _forced_desperate_escape_descriptor() -> DatasheetAbilityDescriptor:
    source_text = RuleSourceText.from_raw(
        source_id="phase10o:catalog-ability:forced-desperate-escape",
        raw_text=(
            "Each time an enemy unit (excluding Monsters and Vehicles) that is within "
            "Engagement Range of one or more units from your army with this ability is selected "
            "to Fall Back, models in that enemy unit must take Desperate Escape tests."
        ),
    )
    rule_ir = compile_rule_source_text(
        source_text,
        source_keyword_sequence_parts=(
            datasheet_keyword_lexicon_source.canonical_datasheet_keyword_sequence_parts()
        ),
    ).rule_ir
    return DatasheetAbilityDescriptor(
        ability_id="phase10o:catalog-ability:forced-desperate-escape",
        name="Forced Desperate Escape",
        source_id=source_text.source_id,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description="Force Desperate Escape tests.",
        rule_ir_payload=cast(CatalogJsonObject, rule_ir.to_payload()),
    )


def _catalog_with_forced_desperate_escape_ability(catalog: ArmyCatalog) -> ArmyCatalog:
    descriptor = _forced_desperate_escape_descriptor()
    target_datasheet_id = "core-intercessor-like-infantry"
    matches = tuple(
        datasheet
        for datasheet in catalog.datasheets
        if datasheet.datasheet_id == target_datasheet_id
    )
    if len(matches) != 1:
        raise AssertionError("Forced Desperate Escape fixture datasheet is ambiguous.")
    datasheets = tuple(
        replace(
            datasheet,
            abilities=(*datasheet.abilities, descriptor),
            source_ids=tuple(sorted({*datasheet.source_ids, descriptor.source_id})),
        )
        if datasheet.datasheet_id == target_datasheet_id
        else datasheet
        for datasheet in catalog.datasheets
    )
    return replace(
        catalog,
        datasheets=datasheets,
        source_ids=tuple(sorted({*catalog.source_ids, descriptor.source_id})),
    )


def _forced_desperate_escape_catalog_record(catalog: ArmyCatalog) -> AbilityCatalogRecord:
    matches = tuple(
        record
        for record in catalog_ability_records_from_catalog(catalog)
        if record.definition.source_id == "phase10o:catalog-ability:forced-desperate-escape"
    )
    if len(matches) != 1:
        raise AssertionError("Forced Desperate Escape catalog record is ambiguous.")
    return matches[0]


def _state_for_scenario_with_effects(
    scenario: BattlefieldScenario,
    *,
    effects: tuple[PersistingEffect, ...],
) -> GameState:
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    battle_phases = tuple(ruleset.battle_phase_sequence.phases)
    return GameState(
        game_id="phase10o-generic-transit-auto-pass",
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(ruleset.setup_sequence.steps),
        battle_phase_sequence=battle_phases,
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=battle_phases.index(BattlePhase.MOVEMENT),
        battle_round=1,
        active_player_id="player-a",
        army_definitions=list(scenario.armies),
        battlefield_state=scenario.battlefield_state,
        persisting_effects=list(effects),
    )


def _advance_to_fall_back_action_request(
    *,
    game_id: str = "phase10o-desperate",
) -> tuple[GameLifecycle, DecisionRequest]:
    lifecycle, movement_status = _movement_lifecycle_with_overflight_engagement(
        _config(game_id=game_id, with_forced_desperate_escape_ability=True)
    )
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
        _ORDERED_FALL_BACK_OPTION_ID,
        f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.DESPERATE_ESCAPE.value}",
    }
    return lifecycle, action_request


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
    deployment_status = _submit_result(
        lifecycle,
        request=_decision_request(second_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10o-result-000002",
    )
    movement_status = submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase10o-deploy",
        pose_factory=_fall_back_deployment_pose,
    )
    assert _decision_request(movement_status).decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    return lifecycle, movement_status


def _movement_lifecycle_with_overflight_engagement(
    config: GameConfig,
) -> tuple[GameLifecycle, LifecycleStatus]:
    mission_setup = config.mission_setup
    assert mission_setup is not None
    armies = tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id=f"{config.game_id}-battlefield",
        armies=armies,
        battlefield_width_inches=mission_setup.battlefield_width_inches,
        battlefield_depth_inches=mission_setup.battlefield_depth_inches,
    )
    battlefield = scenario.battlefield_state
    for army in armies:
        for unit in army.units:
            placement = battlefield.unit_placement_by_id(unit.unit_instance_id)
            battlefield = battlefield.with_unit_placement(
                placement.with_model_placements(
                    tuple(
                        model_placement.with_pose(
                            _fall_back_deployment_pose(
                                index,
                                army.player_id,
                                model_placement.model_instance_id,
                            )
                        )
                        for index, model_placement in enumerate(placement.model_placements)
                    )
                )
            )
    friendly = battlefield.unit_placement_by_id("army-alpha:intercessor-unit-1")
    enemy = battlefield.unit_placement_by_id("army-beta:intercessor-unit-2")
    first_friendly_pose = friendly.model_placements[0].pose
    battlefield = battlefield.with_unit_placement(
        _translated_enemy_unit(
            enemy,
            first_model_pose=Pose.at(
                first_friendly_pose.position.x,
                first_friendly_pose.position.y + 2.0,
                first_friendly_pose.position.z,
                facing_degrees=180.0,
            ),
        )
    )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    for player_id in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player_id=player_id,
                mode=SecondaryMissionMode.FIXED,
                fixed_mission_ids=("assassination", "bring_it_down"),
            )
        )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    decisions = DecisionController()
    record_current_battlefield_placements_for_fixture(state, decisions=decisions)
    record_completed_command_occurrences_for_fixture(
        state,
        decisions=decisions,
        config=config,
    )
    record_primary_turn_start_evidence_for_fixture(state, decisions=decisions)
    lifecycle = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            {
                "config": config.to_payload(),
                "parameterized_movement_proposals": True,
                "state": state.to_payload(),
                "decisions": decisions.to_payload(),
                "reaction_queue": {"frames": []},
            },
        )
    )
    movement_status = lifecycle.advance_until_decision_or_terminal()
    assert _decision_request(movement_status).decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    return lifecycle, movement_status


def _submit_result(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=option_id,
        )
    )
    return submit_default_movement_proposal_if_pending(
        lifecycle,
        status,
        result_id=f"{result_id}-proposal",
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
    enemy_keywords: tuple[str, ...] = ("INFANTRY",),
) -> BattlefieldScenario:
    scenario = _scenario()
    active_unit_id = "army-alpha:intercessor-unit-1"
    enemy_unit_id = "army-beta:intercessor-unit-2"
    friendly = scenario.battlefield_state.unit_placement_by_id(active_unit_id)
    enemy = scenario.battlefield_state.unit_placement_by_id(enemy_unit_id)
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
                else replace(unit, keywords=enemy_keywords)
                if unit.unit_instance_id == enemy_unit_id
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


def _config(
    *,
    game_id: str = "phase10o-desperate",
    with_forced_desperate_escape_ability: bool = False,
) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    if with_forced_desperate_escape_ability:
        catalog = _catalog_with_forced_desperate_escape_ability(catalog)
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
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


def _fall_back_deployment_pose(
    index: int,
    player_id: str,
    model_instance_id: str,
) -> Pose:
    unit_instance_id = model_instance_id.rsplit(":", 2)[0]
    if unit_instance_id == "army-alpha:intercessor-unit-1":
        return Pose.at(3.0 + (index * 1.8), 24.0, 0.0, facing_degrees=0.0)
    if unit_instance_id == "army-beta:intercessor-unit-2":
        return Pose.at(43.5 + (index * 1.8), 24.0, 0.0, facing_degrees=180.0)
    return default_deployment_pose(index, player_id, model_instance_id)


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
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
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
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


def _full_unit_witness_with_only_first_model_moved(
    unit_placement: UnitPlacement,
    *,
    first_model_end_pose: Pose,
) -> PathWitness:
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for index, placement in enumerate(unit_placement.model_placements):
        start = placement.pose
        if index == 0:
            midpoint = Pose.at(
                (start.position.x + first_model_end_pose.position.x) / 2.0,
                (start.position.y + first_model_end_pose.position.y) / 2.0,
                (start.position.z + first_model_end_pose.position.z) / 2.0,
                facing_degrees=(start.facing.degrees + first_model_end_pose.facing.degrees) / 2.0,
            )
            model_paths.append(
                (placement.model_instance_id, (start, midpoint, first_model_end_pose))
            )
            continue
        model_paths.append((placement.model_instance_id, (start, start)))
    return PathWitness.for_paths(tuple(model_paths))


def _fall_back_forward_pose(unit_placement: UnitPlacement) -> Pose:
    first_pose = unit_placement.model_placements[0].pose
    return Pose.at(
        first_pose.position.x,
        first_pose.position.y + 6.0,
        first_pose.position.z,
        facing_degrees=first_pose.facing.degrees,
    )


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
