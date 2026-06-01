from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor, TerrainFeatureKind
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import (
    WeaponKeyword,
    WeaponProfile,
    WeaponProfilePayload,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import validate_json_value
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
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    AdvancedUnitState,
    AdvanceRollRequest,
    AdvanceRollResult,
    MovementDiceRecord,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.phases.shooting import (
    COMPLETE_SHOOTING_PHASE_OPTION_ID,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    ShootingPhaseHandler,
    ShootingPhaseState,
    ShootingUnitSelection,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.shooting_targets import (
    ShootingTargetViolationCode,
    shooting_target_candidates_for_unit,
    shooting_target_violation_code_from_token,
)
from warhammer40k_core.engine.transports import (
    FiringDeckSelection,
    FiringDeckWeaponSelection,
    TransportCapacityProfile,
    TransportCargoState,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_declaration import (
    RangedAttackPool,
    ShootingDeclarationProposal,
    ShootingDeclarationProposalRequest,
    WeaponDeclaration,
    WeaponDeclarationPayload,
    fixed_attacks_for_profile,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)
from warhammer40k_core.geometry.visibility import VisibilityBlockerKind
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack


def test_shooting_unit_selection_and_declaration_use_lifecycle_records() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1", "intercessor-2"))
    first_status = lifecycle.advance_until_decision_or_terminal()
    first_request = _decision_request(first_status)

    assert first_request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE
    assert first_request.actor_id == "player-a"
    assert {option.option_id for option in first_request.options} == {
        COMPLETE_SHOOTING_PHASE_OPTION_ID,
        units["intercessor-1"].unit_instance_id,
        units["intercessor-2"].unit_instance_id,
    }

    declaration_status = _submit_result(
        lifecycle,
        request=first_request,
        option_id=units["intercessor-1"].unit_instance_id,
        result_id="phase13b-select-shooter",
    )
    declaration_request = _decision_request(declaration_status)
    assert declaration_request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
    )

    next_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase13b-submit-declaration",
            request_id=declaration_request.request_id,
            decision_type=declaration_request.decision_type,
            actor_id=declaration_request.actor_id,
            selected_option_id="submit_parameterized_payload",
            payload=validate_json_value(proposal.to_payload()),
        )
    )
    next_request = _decision_request(next_status)
    state = _state(lifecycle)
    assert state.shooting_phase_state is not None
    assert state.shooting_phase_state.shot_unit_ids == (units["intercessor-1"].unit_instance_id,)
    assert state.shooting_phase_state.attack_pools[0].target_unit_instance_id == (
        units["enemy"].unit_instance_id
    )
    assert next_request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE
    assert {option.option_id for option in next_request.options} == {
        COMPLETE_SHOOTING_PHASE_OPTION_ID,
        units["intercessor-2"].unit_instance_id,
    }
    encoded = json.dumps(lifecycle.decision_controller.to_payload(), sort_keys=True)
    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert "shooting_declaration_accepted" in {
        record.event_type for record in lifecycle.decision_controller.event_log.records
    }


def test_invalid_shooting_declaration_submissions_do_not_consume_pending_request() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _decision_request(
        _submit_result(
            lifecycle,
            request=selection_request,
            option_id=units["intercessor-1"].unit_instance_id,
            result_id="phase13b-invalid-select",
        )
    )
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
    )
    before_records = len(lifecycle.decision_controller.records)

    stale_status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload={**proposal.to_payload(), "proposal_request_id": "stale-request"},
        result_id="phase13b-stale",
    )
    stale_payload = cast(dict[str, object], stale_status.payload)
    assert stale_status.status_kind is LifecycleStatusKind.INVALID
    assert cast(dict[str, object], stale_payload["proposal_validation"])["status"] == "stale"
    assert len(lifecycle.decision_controller.records) == before_records
    assert lifecycle.decision_controller.queue.pending_requests == (declaration_request,)

    malformed_status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload={
            "proposal_request_id": declaration_request.request_id,
            "proposal_kind": "shooting_declaration",
            "unit_instance_id": units["intercessor-1"].unit_instance_id,
        },
        result_id="phase13b-malformed",
    )
    malformed_validation = cast(
        dict[str, object],
        cast(dict[str, object], malformed_status.payload)["proposal_validation"],
    )
    assert malformed_status.status_kind is LifecycleStatusKind.INVALID
    assert (
        cast(list[dict[str, object]], malformed_validation["violations"])[0]["violation_code"]
        == "proposal_payload_missing_field"
    )
    assert len(lifecycle.decision_controller.records) == before_records
    assert lifecycle.decision_controller.queue.pending_requests == (declaration_request,)

    drift_status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload={**proposal.to_payload(), "unit_instance_id": "army-alpha:wrong-unit"},
        result_id="phase13b-drift",
    )
    drift_validation = cast(
        dict[str, object],
        cast(dict[str, object], drift_status.payload)["proposal_validation"],
    )
    assert drift_status.status_kind is LifecycleStatusKind.INVALID
    assert (
        cast(list[dict[str, object]], drift_validation["violations"])[0]["violation_code"]
        == "proposal_unit_drift"
    )
    assert len(lifecycle.decision_controller.records) == before_records
    assert lifecycle.decision_controller.queue.pending_requests == (declaration_request,)

    schema_status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload={**proposal.to_payload(), "declarations": "not-a-list"},
        result_id="phase13b-schema-invalid",
    )
    schema_validation = cast(
        dict[str, object],
        cast(dict[str, object], schema_status.payload)["proposal_validation"],
    )
    assert schema_status.status_kind is LifecycleStatusKind.INVALID
    assert (
        cast(list[dict[str, object]], schema_validation["violations"])[0]["violation_code"]
        == "proposal_schema_invalid"
    )
    assert len(lifecycle.decision_controller.records) == before_records
    assert lifecycle.decision_controller.queue.pending_requests == (declaration_request,)

    duplicate_payload = proposal.to_payload()
    duplicate_payload["declarations"] = [
        proposal.declarations[0].to_payload(),
        proposal.declarations[0].to_payload(),
    ]
    duplicate_status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=duplicate_payload,
        result_id="phase13b-duplicate-declaration",
    )
    duplicate_validation = cast(
        dict[str, object],
        cast(dict[str, object], duplicate_status.payload)["proposal_validation"],
    )
    assert duplicate_status.status_kind is LifecycleStatusKind.INVALID
    assert (
        cast(list[dict[str, object]], duplicate_validation["violations"])[0]["violation_code"]
        == "duplicate_weapon_declaration"
    )
    assert len(lifecycle.decision_controller.records) == before_records
    assert lifecycle.decision_controller.queue.pending_requests == (declaration_request,)

    unavailable_payload = proposal.to_payload()
    unavailable_payload["declarations"][0]["weapon_profile_id"] = "wrong-profile"
    unavailable_status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=unavailable_payload,
        result_id="phase13b-unavailable-weapon",
    )
    unavailable_validation = cast(
        dict[str, object],
        cast(dict[str, object], unavailable_status.payload)["proposal_validation"],
    )
    assert unavailable_status.status_kind is LifecycleStatusKind.INVALID
    assert (
        cast(list[dict[str, object]], unavailable_validation["violations"])[0]["violation_code"]
        == "weapon_declaration_unavailable"
    )
    assert len(lifecycle.decision_controller.records) == before_records
    assert lifecycle.decision_controller.queue.pending_requests == (declaration_request,)

    friendly_target_payload = proposal.to_payload()
    friendly_target_payload["declarations"][0]["target_unit_instance_id"] = units[
        "intercessor-1"
    ].unit_instance_id
    friendly_target_status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=friendly_target_payload,
        result_id="phase13b-friendly-target",
    )
    friendly_target_validation = cast(
        dict[str, object],
        cast(dict[str, object], friendly_target_status.payload)["proposal_validation"],
    )
    assert friendly_target_status.status_kind is LifecycleStatusKind.INVALID
    assert (
        cast(list[dict[str, object]], friendly_target_validation["violations"])[0]["violation_code"]
        == "target_not_enemy_unit"
    )
    assert len(lifecycle.decision_controller.records) == before_records
    assert lifecycle.decision_controller.queue.pending_requests == (declaration_request,)


def test_shooting_phase_completion_uses_finite_lifecycle_option() -> None:
    lifecycle, _units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    request = _decision_request(lifecycle.advance_until_decision_or_terminal())

    status = _submit_result(
        lifecycle,
        request=request,
        option_id=COMPLETE_SHOOTING_PHASE_OPTION_ID,
        result_id="phase13b-complete-shooting",
    )

    assert status.status_kind is LifecycleStatusKind.UNSUPPORTED
    state = _state(lifecycle)
    assert state.current_battle_phase is BattlePhase.CHARGE
    assert state.shooting_phase_state is None
    assert "shooting_phase_completion_declared" in {
        record.event_type for record in lifecycle.decision_controller.event_log.records
    }
    assert "shooting_phase_completed" in {
        record.event_type for record in lifecycle.decision_controller.event_log.records
    }


def test_shooting_phase_state_fails_fast_on_drift() -> None:
    selection = ShootingUnitSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-1",
        request_id="phase13b-state-request",
        result_id="phase13b-state-result",
    )
    state = ShootingPhaseState(battle_round=1, active_player_id="player-a")
    selected = state.with_unit_selection(selection)

    with pytest.raises(GameLifecycleError, match="phase_complete"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            phase_complete=cast(bool, "yes"),
        )
    with pytest.raises(GameLifecycleError, match="active_selection must be"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("army-alpha:intercessor-1",),
            active_selection=cast(ShootingUnitSelection, object()),
        )
    with pytest.raises(GameLifecycleError, match="active player drift"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-b",
            selected_unit_ids=("army-alpha:intercessor-1",),
            active_selection=selection,
        )
    with pytest.raises(GameLifecycleError, match="battle round drift"):
        ShootingPhaseState(
            battle_round=2,
            active_player_id="player-a",
            selected_unit_ids=("army-alpha:intercessor-1",),
            active_selection=selection,
        )
    with pytest.raises(GameLifecycleError, match="must be selected"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            active_selection=selection,
        )
    with pytest.raises(GameLifecycleError, match="already shot"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("army-alpha:intercessor-1",),
            shot_unit_ids=("army-alpha:intercessor-1",),
            active_selection=selection,
        )
    with pytest.raises(GameLifecycleError, match="Completed Shooting phase"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            phase_complete=True,
            selected_unit_ids=("army-alpha:intercessor-1",),
            active_selection=selection,
        )
    with pytest.raises(GameLifecycleError, match="Shooting selection must be"):
        state.with_unit_selection(cast(ShootingUnitSelection, object()))
    with pytest.raises(GameLifecycleError, match="after phase completion"):
        state.with_phase_complete().with_unit_selection(selection)
    with pytest.raises(GameLifecycleError, match="requires no active selection"):
        selected.with_unit_selection(
            replace(selection, unit_instance_id="army-alpha:intercessor-2")
        )
    with pytest.raises(GameLifecycleError, match="player drift"):
        state.with_unit_selection(replace(selection, player_id="player-b"))
    with pytest.raises(GameLifecycleError, match="battle round drift"):
        state.with_unit_selection(replace(selection, battle_round=2))
    with pytest.raises(GameLifecycleError, match="already selected"):
        selected.with_declaration(attack_pools=()).with_unit_selection(selection)
    with pytest.raises(GameLifecycleError, match="already shot"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            shot_unit_ids=("army-alpha:intercessor-1",),
        ).with_unit_selection(selection)
    with pytest.raises(GameLifecycleError, match="after phase completion"):
        state.with_phase_complete().with_declaration(attack_pools=())
    with pytest.raises(GameLifecycleError, match="requires active_selection"):
        state.with_declaration(attack_pools=())
    with pytest.raises(GameLifecycleError, match="attack_pools must be attack pools"):
        selected.with_declaration(attack_pools=cast(tuple[RangedAttackPool, ...], (object(),)))
    with pytest.raises(GameLifecycleError, match="requires no active selection"):
        selected.with_phase_complete()
    with pytest.raises(GameLifecycleError, match="attack_pools must be a tuple"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            attack_pools=cast(tuple[RangedAttackPool, ...], []),
        )
    with pytest.raises(GameLifecycleError, match="ruleset_descriptor"):
        ShootingPhaseHandler(
            ruleset_descriptor=cast(RulesetDescriptor, object()),
            army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
        )
    with pytest.raises(GameLifecycleError, match="army_catalog"):
        ShootingPhaseHandler(
            ruleset_descriptor=_ruleset(),
            army_catalog=cast(ArmyCatalog, object()),
        )
    with pytest.raises(GameLifecycleError, match="Firing Deck source unit and model"):
        WeaponDeclaration(
            attacker_model_instance_id="model-1",
            wargear_id="wargear-1",
            weapon_profile_id="profile-1",
            target_unit_instance_id="target-1",
            firing_deck_source_unit_instance_id="source-unit",
        )
    with pytest.raises(GameLifecycleError, match="token must be a string"):
        shooting_target_violation_code_from_token(object())
    with pytest.raises(GameLifecycleError, match="Unsupported shooting target violation"):
        shooting_target_violation_code_from_token("not-a-violation")
    with pytest.raises(GameLifecycleError, match="requires a WeaponProfile"):
        fixed_attacks_for_profile(cast(WeaponProfile, object()))


def test_advanced_unit_is_eligible_to_shoot_only_when_state_permits() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1", "intercessor-2"))
    state = _state(lifecycle)
    state.record_advanced_unit_state(
        _advanced_unit_state(units["intercessor-1"].unit_instance_id, can_shoot=False)
    )

    request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    assert {option.option_id for option in request.options} == {
        COMPLETE_SHOOTING_PHASE_OPTION_ID,
        units["intercessor-2"].unit_instance_id,
    }

    permitted_lifecycle, permitted_units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1", "intercessor-2")
    )
    permitted_state = _state(permitted_lifecycle)
    permitted_state.record_advanced_unit_state(
        _advanced_unit_state(permitted_units["intercessor-1"].unit_instance_id, can_shoot=True)
    )
    permitted_request = _decision_request(permitted_lifecycle.advance_until_decision_or_terminal())

    assert permitted_units["intercessor-1"].unit_instance_id in {
        option.option_id for option in permitted_request.options
    }


def test_target_range_visibility_and_lone_operative_gates_are_explicit() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_pose=Pose.at(80.0, 35.0),
    )
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    attacker = units["intercessor-1"]
    target = units["enemy"]
    profile = _first_weapon_profile(lifecycle, attacker)

    far_candidates = shooting_target_candidates_for_unit(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=profile,
        target_unit_ids=(target.unit_instance_id,),
    )
    assert far_candidates[0].violation_code is ShootingTargetViolationCode.OUT_OF_RANGE
    assert far_candidates[0] == type(far_candidates[0]).from_payload(far_candidates[0].to_payload())

    friendly_candidates = shooting_target_candidates_for_unit(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=profile,
        target_unit_ids=(attacker.unit_instance_id,),
    )
    assert friendly_candidates[0].violation_code is ShootingTargetViolationCode.NOT_ENEMY_UNIT

    unplaced_scenario = BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.without_unit_placement(
            target.unit_instance_id
        ),
    )
    unplaced_candidates = shooting_target_candidates_for_unit(
        scenario=unplaced_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=profile,
        target_unit_ids=(target.unit_instance_id,),
    )
    assert unplaced_candidates[0].violation_code is ShootingTargetViolationCode.TARGET_NOT_PLACED

    melee_profile = _weapon_profile_by_wargear(
        wargear_id="core-leader-blade",
        weapon_profile_id="core-leader-blade:standard",
    )
    melee_candidates = shooting_target_candidates_for_unit(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=melee_profile,
        target_unit_ids=(target.unit_instance_id,),
    )
    assert melee_candidates[0].violation_code is ShootingTargetViolationCode.MELEE_WEAPON

    blocking_ruin = TerrainFeatureDefinition(
        feature_id="phase13b-blocking-ruin",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=20.0,
        footprint_center_y_inches=35.0,
        footprint_width_inches=4.0,
        footprint_depth_inches=4.0,
        walls=(
            TerrainWallDefinition(
                wall_id="wall",
                center_x_inches=20.0,
                center_y_inches=35.0,
                bottom_z_inches=0.0,
                width_inches=0.2,
                depth_inches=4.0,
                height_inches=4.0,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="ground-floor",
                center_x_inches=20.0,
                center_y_inches=35.0,
                bottom_z_inches=0.0,
                width_inches=4.0,
                depth_inches=4.0,
                thickness_inches=0.1,
            ),
        ),
    )
    near_scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=target,
        army_id="army-beta",
        player_id="player-b",
        poses=(
            Pose.at(35.0, 35.0),
            Pose.at(37.0, 35.0),
            Pose.at(39.0, 35.0),
            Pose.at(41.0, 35.0),
            Pose.at(43.0, 35.0),
        ),
    )
    visibility_candidates = shooting_target_candidates_for_unit(
        scenario=near_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=profile,
        target_unit_ids=(target.unit_instance_id,),
        terrain_features=(blocking_ruin,),
    )
    assert visibility_candidates[0].violation_code is ShootingTargetViolationCode.NOT_VISIBLE

    lone_target = replace(target, keywords=(*target.keywords, "Lone Operative"))
    lone_scenario = _scenario_with_replaced_unit(
        scenario=near_scenario,
        replacement=lone_target,
    )
    lone_candidates = shooting_target_candidates_for_unit(
        scenario=lone_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=profile,
        target_unit_ids=(lone_target.unit_instance_id,),
    )
    assert lone_candidates[0].violation_code is ShootingTargetViolationCode.LONE_OPERATIVE

    close_lone_scenario = _scenario_with_unit_pose(
        scenario=lone_scenario,
        unit=lone_target,
        army_id="army-beta",
        player_id="player-b",
        poses=(
            Pose.at(26.0, 35.0),
            Pose.at(27.4, 35.0),
            Pose.at(28.8, 35.0),
            Pose.at(30.2, 35.0),
            Pose.at(31.6, 35.0),
        ),
    )
    close_candidates = shooting_target_candidates_for_unit(
        scenario=close_lone_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=profile,
        target_unit_ids=(lone_target.unit_instance_id,),
    )
    assert close_candidates[0].is_legal


def test_locked_in_combat_big_guns_and_pistol_interactions_are_declaration_state() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("transport-1",),
        alpha_datasheets={"transport-1": ("core-transport", "core-transport", 1)},
        enemy_pose=Pose.at(11.0, 35.0),
    )
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    vehicle = units["transport-1"]
    enemy = units["enemy"]
    vehicle_profile = _first_weapon_profile(lifecycle, vehicle)
    vehicle_candidates = shooting_target_candidates_for_unit(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=vehicle,
        weapon_profile=vehicle_profile,
        target_unit_ids=(enemy.unit_instance_id,),
    )
    assert vehicle_candidates[0].is_legal
    assert vehicle_candidates[0].hit_roll_modifier == -1
    assert "big_guns_never_tire" in vehicle_candidates[0].targeting_rule_ids

    infantry_lifecycle, infantry_units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_pose=Pose.at(11.0, 35.0),
    )
    infantry_state = _state(infantry_lifecycle)
    assert infantry_state.battlefield_state is not None
    infantry_scenario = BattlefieldScenario(
        armies=tuple(infantry_state.army_definitions),
        battlefield_state=infantry_state.battlefield_state,
    )
    infantry = infantry_units["intercessor-1"]
    infantry_profile = _first_weapon_profile(infantry_lifecycle, infantry)
    infantry_candidates = shooting_target_candidates_for_unit(
        scenario=infantry_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=infantry,
        weapon_profile=infantry_profile,
        target_unit_ids=(infantry_units["enemy"].unit_instance_id,),
    )
    assert infantry_candidates[0].violation_code is ShootingTargetViolationCode.LOCKED_IN_COMBAT

    pistol_profile = replace(infantry_profile, keywords=(WeaponKeyword.PISTOL,))
    pistol_candidates = shooting_target_candidates_for_unit(
        scenario=infantry_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=infantry,
        weapon_profile=pistol_profile,
        target_unit_ids=(infantry_units["enemy"].unit_instance_id,),
    )
    assert pistol_candidates[0].is_legal
    assert pistol_candidates[0].hit_roll_modifier == 0


def test_target_side_engagement_rejects_engaged_infantry_and_applies_big_guns() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1", "intercessor-2"),
        enemy_pose=Pose.at(35.0, 35.0),
    )
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    attacker = units["intercessor-1"]
    friendly = units["intercessor-2"]
    target = units["enemy"]
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=attacker,
        army_id="army-alpha",
        player_id="player-a",
        poses=tuple(Pose.at(10.0 + index * 1.4, 20.0) for index in range(5)),
    )
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=friendly,
        army_id="army-alpha",
        player_id="player-a",
        poses=tuple(Pose.at(20.0 + index * 1.4, 35.0) for index in range(5)),
    )
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=target,
        army_id="army-beta",
        player_id="player-b",
        poses=tuple(Pose.at(21.0 + index * 1.4, 35.0, facing_degrees=180.0) for index in range(5)),
    )
    profile = _first_weapon_profile(lifecycle, attacker)

    engaged_infantry_candidates = shooting_target_candidates_for_unit(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=profile,
        target_unit_ids=(target.unit_instance_id,),
    )
    assert (
        engaged_infantry_candidates[0].violation_code
        is ShootingTargetViolationCode.LOCKED_IN_COMBAT
    )

    monster_target = replace(target, keywords=(*target.keywords, "Monster"))
    monster_scenario = _scenario_with_replaced_unit(
        scenario=scenario,
        replacement=monster_target,
    )
    monster_candidates = shooting_target_candidates_for_unit(
        scenario=monster_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=profile,
        target_unit_ids=(monster_target.unit_instance_id,),
    )
    assert monster_candidates[0].is_legal
    assert monster_candidates[0].hit_roll_modifier == -1
    assert "big_guns_never_tire" in monster_candidates[0].targeting_rule_ids


def test_mixed_pistol_and_non_pistol_declarations_are_rejected_without_queue_pop() -> None:
    catalog = _catalog_with_extra_bolt_profile(
        replace(
            _weapon_profile_by_wargear(
                wargear_id="core-bolt-rifle",
                weapon_profile_id="core-bolt-rifle:standard",
            ),
            profile_id="phase13b-bolt-pistol:standard",
            name="Phase 13B bolt pistol",
            keywords=(WeaponKeyword.PISTOL,),
        )
    )
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        catalog=catalog,
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _decision_request(
        _submit_result(
            lifecycle,
            request=selection_request,
            option_id=units["intercessor-1"].unit_instance_id,
            result_id="phase13b-pistol-select",
        )
    )
    request_payload = cast(dict[str, object], declaration_request.payload)
    proposal_request = cast(dict[str, object], request_payload["proposal_request"])
    weapons = cast(list[dict[str, object]], proposal_request["available_weapons"])
    first_model_id = units["intercessor-1"].own_models[0].model_instance_id
    first_model_weapons = [
        weapon for weapon in weapons if weapon["model_instance_id"] == first_model_id
    ]
    pistol_weapon = next(
        weapon
        for weapon in first_model_weapons
        if WeaponKeyword.PISTOL.value
        in cast(WeaponProfilePayload, weapon["weapon_profile"])["keywords"]
    )
    rifle_weapon = next(
        weapon
        for weapon in first_model_weapons
        if WeaponKeyword.PISTOL.value
        not in cast(WeaponProfilePayload, weapon["weapon_profile"])["keywords"]
    )
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
    )
    mixed_payload = proposal.to_payload()
    mixed_payload["declarations"] = [
        _weapon_payload_to_declaration_payload(
            weapon=rifle_weapon,
            target_unit_id=units["enemy"].unit_instance_id,
        ),
        _weapon_payload_to_declaration_payload(
            weapon=pistol_weapon,
            target_unit_id=units["enemy"].unit_instance_id,
        ),
    ]
    before_records = len(lifecycle.decision_controller.records)

    status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=mixed_payload,
        result_id="phase13b-mixed-pistol",
    )
    validation = cast(
        dict[str, object],
        cast(dict[str, object], status.payload)["proposal_validation"],
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert (
        cast(list[dict[str, object]], validation["violations"])[0]["violation_code"]
        == "mixed_pistol_non_pistol_declaration"
    )
    assert len(lifecycle.decision_controller.records) == before_records
    assert lifecycle.decision_controller.queue.pending_requests == (declaration_request,)


def test_firing_deck_declaration_consumes_embarked_weapon_and_marks_unit_ineligible() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("passenger-1", "transport-1"),
        alpha_datasheets={
            "passenger-1": ("core-intercessor-like-infantry", "core-intercessor-like", 5),
            "transport-1": ("core-transport", "core-transport", 1),
        },
        embarked_unit_ids=("passenger-1",),
    )
    state = _state(lifecycle)
    first_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    assert {option.option_id for option in first_request.options} == {
        COMPLETE_SHOOTING_PHASE_OPTION_ID,
        units["transport-1"].unit_instance_id,
    }
    declaration_request = _decision_request(
        _submit_result(
            lifecycle,
            request=first_request,
            option_id=units["transport-1"].unit_instance_id,
            result_id="phase13b-select-transport",
        )
    )
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
        firing_deck_unit=units["passenger-1"],
    )
    request_payload = cast(dict[str, object], declaration_request.payload)
    proposal_request = cast(dict[str, object], request_payload["proposal_request"])
    assert proposal_request["firing_deck_value"] == 2
    assert proposal.firing_deck_selection is not None
    assert proposal.firing_deck_selection.firing_deck_value == 2
    status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=proposal.to_payload(),
        result_id="phase13b-firing-deck",
    )

    assert status.status_kind in {
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.UNSUPPORTED,
        LifecycleStatusKind.ADVANCED,
    }
    assert (
        state.shooting_phase_state is not None
        or state.current_battle_phase is not BattlePhase.SHOOTING
    )
    accepted_payload = _last_event_payload(lifecycle, "shooting_declaration_accepted")
    pools = cast(list[dict[str, object]], accepted_payload["attack_pools"])
    firing_deck_pools = [
        pool for pool in pools if pool["firing_deck_source_unit_instance_id"] is not None
    ]
    assert firing_deck_pools[0]["firing_deck_source_unit_instance_id"] == (
        units["passenger-1"].unit_instance_id
    )
    if state.shooting_phase_state is not None:
        assert units["passenger-1"].unit_instance_id in state.shooting_phase_state.shot_unit_ids


def test_firing_deck_exposes_all_weapons_and_rejects_two_from_one_embarked_model() -> None:
    catalog = _catalog_with_extra_bolt_profile(
        replace(
            _weapon_profile_by_wargear(
                wargear_id="core-bolt-rifle",
                weapon_profile_id="core-bolt-rifle:standard",
            ),
            profile_id="phase13b-extra-bolt:standard",
            name="Phase 13B extra bolt weapon",
        )
    )
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("passenger-1", "transport-1"),
        alpha_datasheets={
            "passenger-1": ("core-intercessor-like-infantry", "core-intercessor-like", 5),
            "transport-1": ("core-transport", "core-transport", 1),
        },
        embarked_unit_ids=("passenger-1",),
        catalog=catalog,
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _decision_request(
        _submit_result(
            lifecycle,
            request=selection_request,
            option_id=units["transport-1"].unit_instance_id,
            result_id="phase13b-select-firing-deck-two-weapons",
        )
    )
    request_payload = cast(dict[str, object], declaration_request.payload)
    proposal_request = cast(dict[str, object], request_payload["proposal_request"])
    assert proposal_request["firing_deck_value"] == 2
    weapons = cast(list[dict[str, object]], proposal_request["available_weapons"])
    passenger_model_id = units["passenger-1"].own_models[0].model_instance_id
    firing_deck_weapons = [
        weapon
        for weapon in weapons
        if weapon.get("firing_deck_source_model_instance_id") == passenger_model_id
    ]
    assert {weapon["weapon_profile_id"] for weapon in firing_deck_weapons} == {
        "core-bolt-rifle:standard",
        "phase13b-extra-bolt:standard",
    }

    target_unit_id = units["enemy"].unit_instance_id
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=target_unit_id,
    )
    duplicate_firing_deck_payload = proposal.to_payload()
    duplicate_firing_deck_payload["declarations"] = [
        _weapon_payload_to_declaration_payload(
            weapon=weapon,
            target_unit_id=target_unit_id,
        )
        for weapon in firing_deck_weapons
    ]
    duplicate_firing_deck_payload["firing_deck_selection"] = FiringDeckSelection(
        player_id="player-a",
        battle_round=1,
        transport_unit_instance_id=units["transport-1"].unit_instance_id,
        firing_deck_value=2,
        weapon_selections=tuple(
            FiringDeckWeaponSelection(
                embarked_unit_instance_id=units["passenger-1"].unit_instance_id,
                model_instance_id=passenger_model_id,
                wargear_id=cast(str, weapon["wargear_id"]),
                weapon_profile=WeaponProfile.from_payload(
                    cast(WeaponProfilePayload, weapon["weapon_profile"])
                ),
            )
            for weapon in firing_deck_weapons
        ),
        already_shot_unit_instance_ids=(),
    ).to_payload()
    before_records = len(lifecycle.decision_controller.records)

    status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=duplicate_firing_deck_payload,
        result_id="phase13b-duplicate-firing-deck-model",
    )
    validation = cast(
        dict[str, object],
        cast(dict[str, object], status.payload)["proposal_validation"],
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert (
        cast(list[dict[str, object]], validation["violations"])[0]["violation_code"]
        == "firing_deck_duplicate_model_selection"
    )
    assert len(lifecycle.decision_controller.records) == before_records
    assert lifecycle.decision_controller.queue.pending_requests == (declaration_request,)


def test_unit_level_target_legality_requires_one_model_with_range_and_visibility() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    assert state.mission_setup is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    attacker = units["intercessor-1"]
    target = units["enemy"]
    attacker_poses = (
        Pose.at(10.0, 35.0),
        Pose.at(0.0, 5.0),
        Pose.at(0.0, 7.0),
        Pose.at(0.0, 9.0),
        Pose.at(0.0, 11.0),
    )
    target_poses = tuple(Pose.at(33.0 + index * 1.4, 35.0) for index in range(5))
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=attacker,
        army_id="army-alpha",
        player_id="player-a",
        poses=attacker_poses,
    )
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=target,
        army_id="army-beta",
        player_id="player-b",
        poses=target_poses,
    )
    blocking_ruin = _blocking_ruin()
    profile = _first_weapon_profile(lifecycle, attacker)

    candidates = shooting_target_candidates_for_unit(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=profile,
        target_unit_ids=(target.unit_instance_id,),
        terrain_features=(blocking_ruin,),
    )
    assert candidates[0].violation_code is ShootingTargetViolationCode.NOT_VISIBLE

    state.battlefield_state = scenario.battlefield_state
    state.mission_setup = replace(state.mission_setup, terrain_features=(blocking_ruin,))
    status = lifecycle.advance_until_decision_or_terminal()
    assert status.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert state.current_battle_phase is BattlePhase.CHARGE


def test_shooting_los_uses_third_party_model_blockers() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1", "blocker"),
        alpha_datasheets={"blocker": ("core-vehicle-monster", "core-vehicle-monster", 1)},
        enemy_datasheet=("core-transport", "core-transport", 1),
    )
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    attacker = units["intercessor-1"]
    blocker = units["blocker"]
    target = units["enemy"]
    attacker_poses = (
        Pose.at(10.0, 35.0),
        Pose.at(0.0, 5.0),
        Pose.at(0.0, 7.0),
        Pose.at(0.0, 9.0),
        Pose.at(0.0, 11.0),
    )
    target_poses = (Pose.at(33.0, 35.0, facing_degrees=180.0),)
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=attacker,
        army_id="army-alpha",
        player_id="player-a",
        poses=attacker_poses,
    )
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=target,
        army_id="army-beta",
        player_id="player-b",
        poses=target_poses,
    )
    blocked_scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=blocker,
        army_id="army-alpha",
        player_id="player-a",
        poses=(Pose.at(21.5, 35.0),),
    )
    profile = _first_weapon_profile(lifecycle, attacker)

    blocked_candidates = shooting_target_candidates_for_unit(
        scenario=blocked_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=profile,
        target_unit_ids=(target.unit_instance_id,),
    )

    assert blocked_candidates[0].violation_code is ShootingTargetViolationCode.NOT_VISIBLE
    witness = blocked_candidates[0].line_of_sight_witness
    assert witness is not None
    blocker_model_id = blocker.own_models[0].model_instance_id
    assert any(
        record.blocker_kind is VisibilityBlockerKind.MODEL and record.blocker_id == blocker_model_id
        for record in witness.all_blocker_records()
    )

    clear_scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=blocker,
        army_id="army-alpha",
        player_id="player-a",
        poses=(Pose.at(21.5, 45.0),),
    )
    clear_candidates = shooting_target_candidates_for_unit(
        scenario=clear_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=profile,
        target_unit_ids=(target.unit_instance_id,),
    )

    assert clear_candidates[0].is_legal


def test_weapon_declaration_payload_round_trips_and_preserves_selection_evidence() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _decision_request(
        _submit_result(
            lifecycle,
            request=selection_request,
            option_id=units["intercessor-1"].unit_instance_id,
            result_id="phase13b-select-round-trip",
        )
    )
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
    )
    declaration = proposal.declarations[0]
    pool = RangedAttackPool.from_declaration(
        declaration=declaration,
        weapon_profile=_first_weapon_profile(lifecycle, units["intercessor-1"]),
        attacks=2,
        target_visible_model_ids=("army-beta:enemy:model-001",),
        target_in_range_model_ids=("army-beta:enemy:model-001",),
        hit_roll_modifier=0,
        targeting_rule_ids=(),
    )
    encoded = json.loads(json.dumps({"proposal": proposal.to_payload(), "pool": pool.to_payload()}))

    assert ShootingDeclarationProposal.from_payload(encoded["proposal"]) == proposal
    assert RangedAttackPool.from_payload(encoded["pool"]) == pool
    assert pool.target_visible_model_ids == ("army-beta:enemy:model-001",)
    assert pool.target_in_range_model_ids == ("army-beta:enemy:model-001",)


def test_shooting_declaration_request_drift_diagnostics_are_typed() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _decision_request(
        _submit_result(
            lifecycle,
            request=selection_request,
            option_id=units["intercessor-1"].unit_instance_id,
            result_id="phase13b-select-drift-diagnostics",
        )
    )
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
    )
    request_payload = cast(dict[str, object], declaration_request.payload)
    proposal_request_payload = cast(dict[str, object], request_payload["proposal_request"])
    proposal_request = ShootingDeclarationProposalRequest(
        request_id=cast(str, proposal_request_payload["request_id"]),
        active_player_id=cast(str, proposal_request_payload["active_player_id"]),
        battle_round=cast(int, proposal_request_payload["battle_round"]),
        unit_instance_id=cast(str, proposal_request_payload["unit_instance_id"]),
        source_decision_request_id=cast(
            str,
            proposal_request_payload["source_decision_request_id"],
        ),
        source_decision_result_id=cast(
            str,
            proposal_request_payload["source_decision_result_id"],
        ),
        visibility_cache_key=cast(str, proposal_request_payload["visibility_cache_key"]),
    )

    diagnostics = {
        replace(proposal, proposal_request_id="stale-request")
        .validation_result_for_request(proposal_request)
        .violations[0]
        .violation_code,
        proposal.validation_result_for_request(
            replace(proposal_request, active_player_id="player-b")
        )
        .violations[0]
        .violation_code,
        proposal.validation_result_for_request(replace(proposal_request, battle_round=2))
        .violations[0]
        .violation_code,
        proposal.validation_result_for_request(
            replace(proposal_request, unit_instance_id="army-alpha:other")
        )
        .violations[0]
        .violation_code,
        proposal.validation_result_for_request(
            replace(proposal_request, source_decision_request_id="other-request")
        )
        .violations[0]
        .violation_code,
        proposal.validation_result_for_request(
            replace(proposal_request, source_decision_result_id="other-result")
        )
        .violations[0]
        .violation_code,
        proposal.validation_result_for_request(
            replace(proposal_request, visibility_cache_key="other-cache-key")
        )
        .violations[0]
        .violation_code,
    }

    assert diagnostics == {
        "stale_proposal_request",
        "proposal_player_drift",
        "proposal_battle_round_drift",
        "proposal_unit_drift",
        "source_decision_request_drift",
        "source_decision_result_drift",
        "visibility_cache_key_drift",
    }


def _shooting_lifecycle(
    *,
    alpha_unit_ids: tuple[str, ...],
    alpha_datasheets: dict[str, tuple[str, str, int]] | None = None,
    enemy_datasheet: tuple[str, str, int] | None = None,
    embarked_unit_ids: tuple[str, ...] = (),
    enemy_pose: Pose | None = None,
    catalog: ArmyCatalog | None = None,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    resolved_enemy_pose = Pose.at(35.0, 35.0) if enemy_pose is None else enemy_pose
    config = _config(
        alpha_unit_ids=alpha_unit_ids,
        alpha_datasheets=alpha_datasheets,
        enemy_datasheet=enemy_datasheet,
        catalog=catalog,
    )
    armies = _mustered_armies(config)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase13b-battlefield",
        armies=armies,
    )
    units = {
        unit.unit_instance_id.split(":", maxsplit=1)[1]: unit
        for army in armies
        for unit in army.units
    }
    battlefield = scenario.battlefield_state
    friendly_unit_index = 0
    for unit_key, unit in units.items():
        if unit_key in embarked_unit_ids:
            battlefield = battlefield.without_unit_placement(unit.unit_instance_id)
            continue
        army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
        player_id = "player-a" if army_id == "army-alpha" else "player-b"
        if unit_key == "enemy":
            poses = tuple(
                Pose.at(
                    resolved_enemy_pose.position.x + (index * 1.4),
                    resolved_enemy_pose.position.y,
                    resolved_enemy_pose.position.z,
                    facing_degrees=180.0,
                )
                for index in range(len(unit.own_models))
            )
        elif unit.datasheet_id == "core-transport":
            poses = (Pose.at(10.0, 35.0 + (friendly_unit_index * 10.0)),)
        else:
            friendly_y = 35.0 + (friendly_unit_index * 10.0)
            poses = tuple(
                Pose.at(10.0 + index * 1.4, friendly_y) for index in range(len(unit.own_models))
            )
        battlefield = battlefield.with_unit_placement(
            _unit_placement_at(unit, army_id=army_id, player_id=player_id, poses=poses)
        )
        if army_id == "army-alpha":
            friendly_unit_index += 1
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    state.record_battlefield_state(battlefield)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    state.battle_round = 1
    state.active_player_id = "player-a"
    if embarked_unit_ids:
        transport = units["transport-1"]
        state.record_transport_cargo_state(
            TransportCargoState(
                player_id="player-a",
                transport_unit_instance_id=transport.unit_instance_id,
                capacity_profile=TransportCapacityProfile(
                    transport_datasheet_id=transport.datasheet_id,
                    max_model_count=10,
                    allowed_keywords=("INFANTRY",),
                ),
                embarked_unit_instance_ids=tuple(
                    units[unit_key].unit_instance_id for unit_key in embarked_unit_ids
                ),
                phase_battle_round=1,
                started_phase_embarked_unit_instance_ids=tuple(
                    units[unit_key].unit_instance_id for unit_key in embarked_unit_ids
                ),
            )
        )
    payload = cast(
        GameLifecyclePayload,
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": state.to_payload(),
            "decisions": lifecycle_decisions_payload(),
            "reaction_queue": {"frames": []},
        },
    )
    return GameLifecycle.from_payload(payload), units


def lifecycle_decisions_payload() -> dict[str, object]:
    lifecycle = GameLifecycle()
    return cast(dict[str, object], lifecycle.decision_controller.to_payload())


def _catalog_with_extra_bolt_profile(extra_profile: WeaponProfile) -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    updated_wargear: list[Wargear] = []
    for wargear in catalog.wargear:
        if wargear.wargear_id == "core-bolt-rifle":
            updated_wargear.append(
                replace(
                    wargear,
                    weapon_profiles=(*wargear.weapon_profiles, extra_profile),
                )
            )
            continue
        updated_wargear.append(wargear)
    return replace(catalog, wargear=tuple(updated_wargear))


def _config(
    *,
    alpha_unit_ids: tuple[str, ...],
    alpha_datasheets: dict[str, tuple[str, str, int]] | None,
    enemy_datasheet: tuple[str, str, int] | None,
    catalog: ArmyCatalog | None = None,
) -> GameConfig:
    resolved_catalog = ArmyCatalog.phase9a_canonical_content_pack() if catalog is None else catalog
    enemy_datasheet_id, enemy_model_profile_id, enemy_model_count = (
        ("core-intercessor-like-infantry", "core-intercessor-like", 5)
        if enemy_datasheet is None
        else enemy_datasheet
    )
    return GameConfig(
        game_id="phase13b-game",
        ruleset_descriptor=_ruleset(),
        army_catalog=resolved_catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=resolved_catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_specs=tuple(
                    _alpha_unit_spec(
                        unit_id=unit_id,
                        alpha_datasheets=alpha_datasheets,
                    )
                    for unit_id in alpha_unit_ids
                ),
            ),
            _army_muster_request(
                catalog=resolved_catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_specs=(
                    ("enemy", enemy_datasheet_id, enemy_model_profile_id, enemy_model_count),
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _alpha_unit_spec(
    *,
    unit_id: str,
    alpha_datasheets: dict[str, tuple[str, str, int]] | None,
) -> tuple[str, str, str, int]:
    if alpha_datasheets is not None and unit_id in alpha_datasheets:
        datasheet_id, model_profile_id, model_count = alpha_datasheets[unit_id]
        return (unit_id, datasheet_id, model_profile_id, model_count)
    return (unit_id, "core-intercessor-like-infantry", "core-intercessor-like", 5)


def _mission_setup() -> MissionSetup:
    mission_pack = chapter_approved_2025_26_mission_pack()
    return MissionSetup(
        mission_pack_id=mission_pack.mission_pack_id,
        source_version=mission_pack.source_version,
        source_id=mission_pack.source_id,
        mission_pool_entry_id="mission-a",
        primary_mission_id="take-and-hold",
        deployment_map_id="phase13b-open-map",
        terrain_layout_id="phase13b-open-layout",
        attacker_player_id="player-a",
        defender_player_id="player-b",
        battlefield_width_inches=100.0,
        battlefield_depth_inches=60.0,
        objective_markers=(
            ObjectiveMarkerDefinition(
                objective_marker_id="phase13b-remote-objective",
                name="Phase 13B Remote Objective",
                x_inches=95.0,
                y_inches=55.0,
                source_id="phase13b-test",
            ),
        ),
        deployment_zones=(),
        terrain_features=(),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_specs: tuple[tuple[str, str, str, int], ...],
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
                unit_selection_id=unit_id,
                datasheet_id=datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id=model_profile_id,
                        model_count=model_count,
                    ),
                ),
            )
            for unit_id, datasheet_id, model_profile_id, model_count in unit_specs
        ),
    )


def _proposal_from_request(
    *,
    request: DecisionRequest,
    target_unit_id: str,
    firing_deck_unit: UnitInstance | None = None,
) -> ShootingDeclarationProposal:
    payload = cast(dict[str, object], request.payload)
    proposal_request = cast(dict[str, object], payload["proposal_request"])
    weapons = cast(list[dict[str, object]], proposal_request["available_weapons"])
    target_candidates = cast(list[dict[str, object]], proposal_request["target_candidates"])
    target_candidate = next(
        candidate
        for candidate in target_candidates
        if candidate["target_unit_instance_id"] == target_unit_id and candidate["is_legal"] is True
    )
    selected_weapon = weapons[0]
    declarations = [
        WeaponDeclaration(
            attacker_model_instance_id=cast(str, selected_weapon["model_instance_id"]),
            wargear_id=cast(str, selected_weapon["wargear_id"]),
            weapon_profile_id=cast(str, selected_weapon["weapon_profile_id"]),
            target_unit_instance_id=target_unit_id,
        )
    ]
    firing_deck_selection = None
    if firing_deck_unit is not None:
        passenger_model = firing_deck_unit.own_models[0]
        passenger_wargear_id = firing_deck_unit.wargear_selections[0].wargear_ids[0]
        passenger_profile = next(
            weapon
            for weapon in weapons
            if weapon.get("firing_deck_source_model_instance_id")
            == passenger_model.model_instance_id
        )
        declarations.append(
            WeaponDeclaration(
                attacker_model_instance_id=cast(str, passenger_profile["model_instance_id"]),
                wargear_id=passenger_wargear_id,
                weapon_profile_id=cast(str, passenger_profile["weapon_profile_id"]),
                target_unit_instance_id=target_unit_id,
                firing_deck_source_unit_instance_id=firing_deck_unit.unit_instance_id,
                firing_deck_source_model_instance_id=passenger_model.model_instance_id,
            )
        )
        firing_deck_selection = FiringDeckSelection(
            player_id="player-a",
            battle_round=1,
            transport_unit_instance_id=cast(str, proposal_request["unit_instance_id"]),
            firing_deck_value=cast(int, proposal_request["firing_deck_value"]),
            weapon_selections=(
                FiringDeckWeaponSelection(
                    embarked_unit_instance_id=firing_deck_unit.unit_instance_id,
                    model_instance_id=passenger_model.model_instance_id,
                    wargear_id=passenger_wargear_id,
                    weapon_profile=WeaponProfile.from_payload(
                        cast(WeaponProfilePayload, passenger_profile["weapon_profile"])
                    ),
                ),
            ),
            already_shot_unit_instance_ids=(),
        )
    return ShootingDeclarationProposal(
        proposal_request_id=cast(str, proposal_request["request_id"]),
        proposal_kind="shooting_declaration",
        player_id=cast(str, proposal_request["active_player_id"]),
        battle_round=cast(int, proposal_request["battle_round"]),
        unit_instance_id=cast(str, proposal_request["unit_instance_id"]),
        source_decision_request_id=cast(str, proposal_request["source_decision_request_id"]),
        source_decision_result_id=cast(str, proposal_request["source_decision_result_id"]),
        declarations=tuple(declarations),
        firing_deck_selection=firing_deck_selection,
        visibility_cache_key=cast(str, target_candidate["visibility_cache_key"]),
    )


def _weapon_payload_to_declaration_payload(
    *,
    weapon: dict[str, object],
    target_unit_id: str,
) -> WeaponDeclarationPayload:
    payload: WeaponDeclarationPayload = {
        "attacker_model_instance_id": cast(str, weapon["model_instance_id"]),
        "wargear_id": cast(str, weapon["wargear_id"]),
        "weapon_profile_id": cast(str, weapon["weapon_profile_id"]),
        "target_unit_instance_id": target_unit_id,
        "firing_deck_source_unit_instance_id": None,
        "firing_deck_source_model_instance_id": None,
    }
    if "firing_deck_source_unit_instance_id" in weapon:
        payload["firing_deck_source_unit_instance_id"] = cast(
            str,
            weapon["firing_deck_source_unit_instance_id"],
        )
        payload["firing_deck_source_model_instance_id"] = cast(
            str,
            weapon["firing_deck_source_model_instance_id"],
        )
    return payload


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


def _submit_payload(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    payload: object,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        DecisionResult(
            result_id=result_id,
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id="submit_parameterized_payload",
            payload=validate_json_value(payload),
        )
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _state(lifecycle: GameLifecycle) -> GameState:
    assert lifecycle.state is not None
    return lifecycle.state


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_tenth(descriptor_version="core-v2-phase13b-test")


def _blocking_ruin() -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id="phase13b-blocking-ruin",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=20.0,
        footprint_center_y_inches=35.0,
        footprint_width_inches=4.0,
        footprint_depth_inches=4.0,
        walls=(
            TerrainWallDefinition(
                wall_id="wall",
                center_x_inches=20.0,
                center_y_inches=35.0,
                bottom_z_inches=0.0,
                width_inches=0.2,
                depth_inches=4.0,
                height_inches=4.0,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="ground-floor",
                center_x_inches=20.0,
                center_y_inches=35.0,
                bottom_z_inches=0.0,
                width_inches=4.0,
                depth_inches=4.0,
                thickness_inches=0.1,
            ),
        ),
    )


def _unit_placement_at(
    unit: UnitInstance,
    *,
    army_id: str,
    player_id: str,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(unit.own_models, poses, strict=True)
        ),
    )


def _first_weapon_profile(lifecycle: GameLifecycle, unit: UnitInstance) -> WeaponProfile:
    _state(lifecycle)
    wargear_id = unit.wargear_selections[0].wargear_ids[0]
    return _weapon_profile_by_wargear(
        wargear_id=wargear_id,
        weapon_profile_id=None,
    )


def _weapon_profile_by_wargear(
    *,
    wargear_id: str,
    weapon_profile_id: str | None,
) -> WeaponProfile:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    for wargear in catalog.wargear:
        if wargear.wargear_id == wargear_id:
            if weapon_profile_id is None:
                return wargear.weapon_profiles[0]
            for profile in wargear.weapon_profiles:
                if profile.profile_id == weapon_profile_id:
                    return profile
    raise AssertionError(f"Missing wargear {wargear_id}.")


def _advanced_unit_state(unit_instance_id: str, *, can_shoot: bool) -> AdvancedUnitState:
    request = AdvanceRollRequest.for_unit(
        request_id=f"{unit_instance_id}:advance-roll",
        game_id="phase13b-game",
        battle_round=1,
        player_id="player-a",
        unit_instance_id=unit_instance_id,
    )
    roll_state = DiceRollManager("phase13b-advanced-state").roll_fixed(request.spec, [3])
    return AdvancedUnitState(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=unit_instance_id,
        movement_dice_record=MovementDiceRecord(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=unit_instance_id,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            advance_roll=AdvanceRollResult.from_roll_state(
                request=request,
                roll_state=roll_state,
            ),
        ),
        can_shoot=can_shoot,
    )


def _scenario_with_unit_pose(
    *,
    scenario: BattlefieldScenario,
    unit: UnitInstance,
    army_id: str,
    player_id: str,
    poses: tuple[Pose, ...],
) -> BattlefieldScenario:
    return BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.with_unit_placement(
            _unit_placement_at(unit, army_id=army_id, player_id=player_id, poses=poses)
        ),
    )


def _scenario_with_replaced_unit(
    *,
    scenario: BattlefieldScenario,
    replacement: UnitInstance,
) -> BattlefieldScenario:
    updated_armies: list[ArmyDefinition] = []
    for army in scenario.armies:
        updated_armies.append(
            replace(
                army,
                units=tuple(
                    replacement if unit.unit_instance_id == replacement.unit_instance_id else unit
                    for unit in army.units
                ),
            )
        )
    return BattlefieldScenario(
        armies=tuple(updated_armies),
        battlefield_state=scenario.battlefield_state,
    )


def _last_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, object]:
    for event in reversed(lifecycle.decision_controller.event_log.records):
        if event.event_type == event_type:
            return cast(dict[str, object], event.payload)
    raise AssertionError(f"Missing event type {event_type}.")
