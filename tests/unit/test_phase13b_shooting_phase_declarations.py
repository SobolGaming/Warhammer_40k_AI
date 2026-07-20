from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest
from tests.phase13b_shooting_declaration_helpers import (
    _advanced_unit_state,
    _assert_waiting_for_movement_unit,
    _attack_pool_for_test,
    _attack_step_payloads,
    _blocking_ruin,
    _catalog_with_extra_bolt_profile,
    _catalog_with_lone_operative_datasheet,
    _catalog_with_replaced_bolt_profiles,
    _catalog_with_stealth_datasheet,
    _compact_test_unit_poses,
    _continue_damage_model_choices,
    _decision_request,
    _dense_solid_woods,
    _display_geometry,
    _first_shooting_type,
    _first_weapon_profile,
    _gone_to_ground_detection_context,
    _last_event_payload,
    _non_solid_hill_with_wall,
    _phase13f_cover_effect,
    _phase13f_gate_weapon_profile,
    _proposal_from_declarations,
    _proposal_from_request,
    _replace_unit_instance_in_state,
    _ruleset,
    _save_payload_has_cover,
    _scenario_with_replaced_unit,
    _scenario_with_unit_pose,
    _select_shooting_unit_and_type,
    _shooting_lifecycle,
    _state,
    _submit_payload,
    _submit_phase13f_pending_attack_choices,
    _submit_result,
    _weapon_payload_to_declaration_payload,
    _weapon_profile_by_wargear,
)

from warhammer40k_core.adapters.projection import project_game_view
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    DamagedEffectDefinition,
    DamagedEffectKind,
    DatasheetDefinition,
)
from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponKeyword,
    WeaponProfile,
    WeaponProfilePayload,
)
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    AttackSequenceStep,
    cover_for_allocated_model,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.game_state import (
    GameState,
    GameStatePayload,
    RangedAttackHistoryRecord,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.charge import SELECT_CHARGING_UNIT_DECISION_TYPE
from warhammer40k_core.engine.phases.shooting import (
    COMPLETE_SHOOTING_PHASE_OPTION_ID,
    ShootingPhaseHandler,
    ShootingPhaseState,
    ShootingTypeSelection,
    ShootingUnitSelection,
)
from warhammer40k_core.engine.shooting_targets import (
    LONE_OPERATIVE_RULE_ID,
    STEALTH_RULE_ID,
    ShootingTargetViolationCode,
    shooting_target_candidate_for_model,
    shooting_target_candidates_for_unit,
    shooting_target_violation_code_from_token,
)
from warhammer40k_core.engine.shooting_types import (
    ShootingType,
)
from warhammer40k_core.engine.transports import (
    FiringDeckSelection,
    FiringDeckWeaponSelection,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_abilities import (
    HUNTER_RULE_ID,
    WEAPON_ABILITY_SELECTION_DECISION_TYPE,
)
from warhammer40k_core.engine.weapon_declaration import (
    RangedAttackPool,
    ShootingDeclarationProposal,
    ShootingDeclarationProposalRequest,
    WeaponDeclaration,
    fixed_attacks_for_profile,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)
from warhammer40k_core.geometry.visibility import (
    VisibilityBlockerKind,
)


def test_invalid_shooting_declaration_submissions_do_not_consume_pending_request() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection_request,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        selection_result_id="phase13b-invalid-select",
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

    missing_type_payload = proposal.to_payload()
    missing_type_declaration = cast(dict[str, object], missing_type_payload["declarations"][0])
    del missing_type_declaration["shooting_type"]
    missing_type_status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=missing_type_payload,
        result_id="phase14f-missing-shooting-type",
    )
    missing_type_validation = cast(
        dict[str, object],
        cast(dict[str, object], missing_type_status.payload)["proposal_validation"],
    )
    assert missing_type_status.status_kind is LifecycleStatusKind.INVALID
    assert (
        cast(list[dict[str, object]], missing_type_validation["violations"])[0]["violation_code"]
        == "proposal_schema_invalid"
    )
    assert len(lifecycle.decision_controller.records) == before_records
    assert lifecycle.decision_controller.queue.pending_requests == (declaration_request,)

    invented_type_payload = proposal.to_payload()
    invented_type_declaration = cast(dict[str, object], invented_type_payload["declarations"][0])
    invented_type_declaration["shooting_type"] = ShootingType.SNAP.value
    invented_type_status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=invented_type_payload,
        result_id="phase14f-invented-shooting-type",
    )
    invented_type_validation = cast(
        dict[str, object],
        cast(dict[str, object], invented_type_status.payload)["proposal_validation"],
    )
    assert invented_type_status.status_kind is LifecycleStatusKind.INVALID
    assert (
        cast(list[dict[str, object]], invented_type_validation["violations"])[0]["violation_code"]
        == "shooting_type_unavailable"
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


def test_ctan_power_selection_limits_are_exposed_and_validated_before_queue_pop() -> None:
    catalog = _catalog_with_ctan_power_selection_limit()
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        alpha_datasheets={
            "intercessor-1": ("core-intercessor-like-infantry", "core-intercessor-like", 1)
        },
        catalog=catalog,
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection_request,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        selection_result_id="phase13b-ctan-baseline-select",
    )
    baseline_payload = _shooting_proposal_request_payload(declaration_request)
    baseline_limits = cast(
        list[dict[str, object]],
        baseline_payload["shooting_weapon_selection_limits"],
    )

    assert len(baseline_limits) == 1
    assert baseline_limits[0]["weapon_keyword"] == WeaponKeyword.CTAN_POWER.value
    assert baseline_limits[0]["max_selections"] == 2
    assert baseline_limits[0]["baseline_max_selections"] == 2
    assert baseline_limits[0]["damaged_profile_active"] is False
    assert baseline_limits[0]["weapon_profile_ids"] == [
        "ctan-antimatter-meteor",
        "ctan-cosmic-fire",
        "ctan-times-arrow",
    ]

    over_baseline = _ctan_power_proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
        weapon_count=3,
    )
    over_baseline_status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=over_baseline.to_payload(),
        result_id="phase13b-ctan-baseline-over-limit",
    )
    over_baseline_validation = cast(
        dict[str, object],
        cast(dict[str, object], over_baseline_status.payload)["proposal_validation"],
    )
    over_baseline_violation = cast(
        list[dict[str, object]],
        over_baseline_validation["violations"],
    )[0]
    assert over_baseline_status.status_kind is LifecycleStatusKind.INVALID
    assert over_baseline_violation["violation_code"] == "shooting_weapon_selection_limit_exceeded"
    assert lifecycle.decision_controller.queue.pending_requests == (declaration_request,)

    under_baseline = _ctan_power_proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
        weapon_count=2,
    )
    under_baseline_status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=under_baseline.to_payload(),
        result_id="phase13b-ctan-baseline-under-limit",
    )
    assert under_baseline_status.status_kind is not LifecycleStatusKind.INVALID

    damaged_lifecycle, damaged_units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        alpha_datasheets={
            "intercessor-1": ("core-intercessor-like-infantry", "core-intercessor-like", 1)
        },
        catalog=catalog,
    )
    damaged_unit = _unit_with_first_model_wounds(
        damaged_units["intercessor-1"],
        wounds_remaining=1,
    )
    damaged_state = damaged_lifecycle.state
    assert damaged_state is not None
    _replace_unit_instance_in_state(state=damaged_state, replacement=damaged_unit)
    damaged_units["intercessor-1"] = damaged_unit
    damaged_selection_request = _decision_request(
        damaged_lifecycle.advance_until_decision_or_terminal()
    )
    damaged_declaration_request = _select_shooting_unit_and_type(
        damaged_lifecycle,
        selection_request=damaged_selection_request,
        unit_instance_id=damaged_unit.unit_instance_id,
        selection_result_id="phase13b-ctan-damaged-select",
    )
    damaged_payload = _shooting_proposal_request_payload(damaged_declaration_request)
    damaged_limits = cast(
        list[dict[str, object]],
        damaged_payload["shooting_weapon_selection_limits"],
    )

    assert len(damaged_limits) == 1
    assert damaged_limits[0]["max_selections"] == 1
    assert damaged_limits[0]["baseline_max_selections"] == 2
    assert damaged_limits[0]["damaged_profile_active"] is True

    over_damaged = _ctan_power_proposal_from_request(
        request=damaged_declaration_request,
        target_unit_id=damaged_units["enemy"].unit_instance_id,
        weapon_count=2,
    )
    over_damaged_status = _submit_payload(
        damaged_lifecycle,
        request=damaged_declaration_request,
        payload=over_damaged.to_payload(),
        result_id="phase13b-ctan-damaged-over-limit",
    )
    over_damaged_validation = cast(
        dict[str, object],
        cast(dict[str, object], over_damaged_status.payload)["proposal_validation"],
    )
    over_damaged_violation = cast(
        list[dict[str, object]],
        over_damaged_validation["violations"],
    )[0]
    assert over_damaged_status.status_kind is LifecycleStatusKind.INVALID
    assert over_damaged_violation["violation_code"] == "shooting_weapon_selection_limit_exceeded"
    assert damaged_lifecycle.decision_controller.queue.pending_requests == (
        damaged_declaration_request,
    )

    under_damaged = _ctan_power_proposal_from_request(
        request=damaged_declaration_request,
        target_unit_id=damaged_units["enemy"].unit_instance_id,
        weapon_count=1,
    )
    under_damaged_status = _submit_payload(
        damaged_lifecycle,
        request=damaged_declaration_request,
        payload=under_damaged.to_payload(),
        result_id="phase13b-ctan-damaged-under-limit",
    )
    assert under_damaged_status.status_kind is not LifecycleStatusKind.INVALID


def test_shooting_phase_completion_uses_finite_lifecycle_option() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    complete_option = next(
        option
        for option in request.options
        if option.option_id == COMPLETE_SHOOTING_PHASE_OPTION_ID
    )
    complete_payload = cast(dict[str, object], complete_option.payload)

    status = _submit_result(
        lifecycle,
        request=request,
        option_id=COMPLETE_SHOOTING_PHASE_OPTION_ID,
        result_id="phase13b-complete-shooting",
    )

    _assert_waiting_for_movement_unit(status)
    state = _state(lifecycle)
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    assert state.shooting_phase_state is None
    assert complete_payload["submission_kind"] == COMPLETE_SHOOTING_PHASE_OPTION_ID
    assert complete_payload["skipped_unit_ids"] == [units["intercessor-1"].unit_instance_id]
    assert "shooting_phase_completion_declared" in {
        record.event_type for record in lifecycle.decision_controller.event_log.records
    }
    assert "shooting_phase_completed" in {
        record.event_type for record in lifecycle.decision_controller.event_log.records
    }
    completion_declared = _last_event_payload(lifecycle, "shooting_phase_completion_declared")
    phase_completed = _last_event_payload(lifecycle, "shooting_phase_completed")
    assert completion_declared["skipped_unit_ids"] == [units["intercessor-1"].unit_instance_id]
    assert phase_completed["skipped_unit_ids"] == [units["intercessor-1"].unit_instance_id]


@pytest.mark.slow
def test_phase13f_full_shooting_gate_drains_attacks_before_completion() -> None:
    profile = _phase13f_gate_weapon_profile()
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1", "intercessor-2"),
        enemy_unit_specs=(
            ("enemy", "core-intercessor-like-infantry", "core-intercessor-like", 10),
        ),
        enemy_pose=Pose.at(25.0, 35.0),
        catalog=_catalog_with_extra_bolt_profile(profile),
        game_id="phase13f-full-gate-0000",
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    skipped = units["intercessor-2"]
    defender = units["enemy"]
    state.record_persisting_effect(_phase13f_cover_effect(defender.unit_instance_id))

    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    selected_option = next(
        option
        for option in selection_request.options
        if option.option_id == attacker.unit_instance_id
    )
    assert cast(dict[str, object], selected_option.payload)["unit_instance_id"] == (
        attacker.unit_instance_id
    )
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection_request,
        unit_instance_id=attacker.unit_instance_id,
        selection_result_id="phase13f-select-attacker",
    )
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=defender.unit_instance_id,
        weapon_profile_id=profile.profile_id,
    )

    status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=proposal.to_payload(),
        result_id="phase13f-submit-declaration",
    )
    next_selection_status = _submit_phase13f_pending_attack_choices(
        lifecycle,
        status=status,
        result_id_prefix="phase13f-attack",
    )
    _, drained_next_selection_status = _continue_damage_model_choices(
        lifecycle,
        attack_sequence=None,
        allocated_ids=(),
        status=next_selection_status,
        result_id_prefix="phase13f-full-gate-model",
    )
    assert drained_next_selection_status is not None
    next_selection_status = drained_next_selection_status
    next_selection_request = _decision_request(next_selection_status)
    complete_option = next(
        option
        for option in next_selection_request.options
        if option.option_id == COMPLETE_SHOOTING_PHASE_OPTION_ID
    )
    complete_payload = cast(dict[str, object], complete_option.payload)

    final_status = _submit_result(
        lifecycle,
        request=next_selection_request,
        option_id=COMPLETE_SHOOTING_PHASE_OPTION_ID,
        result_id="phase13f-complete-after-attacks",
    )
    event_types = [event.event_type for event in lifecycle.decision_controller.event_log.records]
    accepted_payload = _last_event_payload(lifecycle, "shooting_declaration_accepted")
    accepted_pool = cast(list[dict[str, object]], accepted_payload["attack_pools"])[0]
    model_destroyed_payload = _last_event_payload(lifecycle, "model_destroyed")
    hit_events = _attack_step_payloads(lifecycle, AttackSequenceStep.HIT)
    save_events = _attack_step_payloads(lifecycle, AttackSequenceStep.SAVE)

    assert final_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert final_status.decision_request is not None
    assert final_status.decision_request.decision_type == SELECT_CHARGING_UNIT_DECISION_TYPE
    assert _state(lifecycle).current_battle_phase is BattlePhase.CHARGE
    assert _state(lifecycle).shooting_phase_state is None
    assert accepted_pool["target_visible_model_ids"]
    assert accepted_pool["target_in_range_model_ids"]
    assert model_destroyed_payload["transition_batch"] == {
        "placements": [],
        "removals": [model_destroyed_payload["removal_record"]],
        "displacements": [],
    }
    assert any(
        cast(dict[str, object], hit_event["payload"])["target_number"] == 4
        for hit_event in hit_events
    )
    assert not any(_save_payload_has_cover(save_event) for save_event in save_events)
    assert event_types.index("attack_sequence_completed") < event_types.index(
        "shooting_phase_completion_declared"
    )
    assert complete_payload["skipped_unit_ids"] == [skipped.unit_instance_id]
    assert _last_event_payload(lifecycle, "shooting_phase_completion_declared")[
        "skipped_unit_ids"
    ] == [skipped.unit_instance_id]


@pytest.mark.slow
def test_phase13f_shooting_completion_runs_for_both_players() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))

    player_a_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    player_a_status = _submit_result(
        lifecycle,
        request=player_a_request,
        option_id=COMPLETE_SHOOTING_PHASE_OPTION_ID,
        result_id="phase13f-player-a-complete",
    )
    state = _state(lifecycle)
    player_a_movement_request = _assert_waiting_for_movement_unit(player_a_status)
    assert state.current_battle_phase is BattlePhase.MOVEMENT

    lifecycle.decision_controller.queue.remove_by_id(player_a_movement_request.request_id)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    state.active_player_id = "player-b"
    player_b_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    player_b_option_ids = {option.option_id for option in player_b_request.options}
    player_b_status = _submit_result(
        lifecycle,
        request=player_b_request,
        option_id=COMPLETE_SHOOTING_PHASE_OPTION_ID,
        result_id="phase13f-player-b-complete",
    )
    player_b_completed = _last_event_payload(lifecycle, "shooting_phase_completed")

    _assert_waiting_for_movement_unit(player_b_status)
    assert player_b_request.actor_id == "player-b"
    assert units["enemy"].unit_instance_id in player_b_option_ids
    assert player_b_completed["active_player_id"] == "player-b"
    assert player_b_completed["skipped_unit_ids"] == [units["enemy"].unit_instance_id]


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
    shooting_type_selection = ShootingTypeSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-1",
        shooting_type=ShootingType.NORMAL,
        request_id="phase13b-state-type-request",
        result_id="phase13b-state-type-result",
    )
    selected_with_type = selected.with_shooting_type_selection(shooting_type_selection)
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    pending_attack_pool = _attack_pool_for_test(
        attacker=attacker,
        defender=defender,
        weapon_profile=_first_weapon_profile(lifecycle, attacker),
        attacks=1,
    )
    completed_sequence = AttackSequence(
        sequence_id="phase13b-pending-completed-sequence",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(pending_attack_pool,),
        source_phase=BattlePhase.SHOOTING,
        used_pool_indices=(0,),
        pool_index=1,
    )
    pending_completed_state = ShootingPhaseState(
        battle_round=1,
        active_player_id="player-a",
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=(pending_attack_pool,),
        pending_completed_attack_sequence=completed_sequence,
    )

    assert ShootingUnitSelection.from_payload(selection.to_payload()) == selection
    assert ShootingTypeSelection.from_payload(shooting_type_selection.to_payload()) == (
        shooting_type_selection
    )
    assert ShootingPhaseState.from_payload(selected_with_type.to_payload()) == selected_with_type
    assert ShootingPhaseState.from_payload(pending_completed_state.to_payload()) == (
        pending_completed_state
    )
    assert (
        pending_completed_state.with_pending_completed_attack_sequence(
            None
        ).pending_completed_attack_sequence
        is None
    )

    with pytest.raises(GameLifecycleError, match="phase_complete"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            phase_complete=cast(bool, "yes"),
        )
    with pytest.raises(GameLifecycleError, match="must not also count as shot"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            shot_unit_ids=("army-alpha:intercessor-1",),
            skipped_unit_ids=("army-alpha:intercessor-1",),
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
    with pytest.raises(GameLifecycleError, match="already been skipped"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("army-alpha:intercessor-1",),
            skipped_unit_ids=("army-alpha:intercessor-1",),
            active_selection=selection,
        )
    with pytest.raises(GameLifecycleError, match="selected_shooting_type must be"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("army-alpha:intercessor-1",),
            active_selection=selection,
            selected_shooting_type=cast(ShootingTypeSelection, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires active_selection"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_shooting_type=shooting_type_selection,
        )
    with pytest.raises(GameLifecycleError, match="active player drift"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("army-alpha:intercessor-1",),
            active_selection=selection,
            selected_shooting_type=replace(shooting_type_selection, player_id="player-b"),
        )
    with pytest.raises(GameLifecycleError, match="battle round drift"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("army-alpha:intercessor-1",),
            active_selection=selection,
            selected_shooting_type=replace(shooting_type_selection, battle_round=2),
        )
    with pytest.raises(GameLifecycleError, match="unit drift"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("army-alpha:intercessor-1",),
            active_selection=selection,
            selected_shooting_type=replace(
                shooting_type_selection,
                unit_instance_id="army-alpha:intercessor-2",
            ),
        )
    with pytest.raises(GameLifecycleError, match="attack_sequence must be"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            attack_sequence=cast(AttackSequence, object()),
        )
    with pytest.raises(GameLifecycleError, match="pending_completed_attack_sequence must be"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            pending_completed_attack_sequence=cast(AttackSequence, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires no active selection"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=("army-alpha:intercessor-1",),
            active_selection=selection,
            pending_completed_attack_sequence=completed_sequence,
        )
    with pytest.raises(GameLifecycleError, match="active and pending completed"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            attack_sequence=completed_sequence,
            pending_completed_attack_sequence=completed_sequence,
        )
    with pytest.raises(GameLifecycleError, match="pending completed attack sequence"):
        pending_completed_state.with_phase_complete()
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
        selected_with_type.with_declaration(attack_pools=()).with_unit_selection(selection)
    with pytest.raises(GameLifecycleError, match="already shot"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            shot_unit_ids=("army-alpha:intercessor-1",),
        ).with_unit_selection(selection)
    with pytest.raises(GameLifecycleError, match="Shooting type selection must be"):
        selected.with_shooting_type_selection(cast(ShootingTypeSelection, object()))
    with pytest.raises(GameLifecycleError, match="after phase completion"):
        state.with_phase_complete().with_shooting_type_selection(shooting_type_selection)
    with pytest.raises(GameLifecycleError, match="requires active_selection"):
        state.with_shooting_type_selection(shooting_type_selection)
    with pytest.raises(GameLifecycleError, match="already been selected"):
        selected_with_type.with_shooting_type_selection(shooting_type_selection)
    with pytest.raises(GameLifecycleError, match="player drift"):
        selected.with_shooting_type_selection(
            replace(shooting_type_selection, player_id="player-b")
        )
    with pytest.raises(GameLifecycleError, match="battle round drift"):
        selected.with_shooting_type_selection(replace(shooting_type_selection, battle_round=2))
    with pytest.raises(GameLifecycleError, match="unit drift"):
        selected.with_shooting_type_selection(
            replace(shooting_type_selection, unit_instance_id="army-alpha:intercessor-2")
        )
    with pytest.raises(GameLifecycleError, match="after phase completion"):
        state.with_phase_complete().with_declaration(attack_pools=())
    with pytest.raises(GameLifecycleError, match="requires active_selection"):
        state.with_declaration(attack_pools=())
    with pytest.raises(GameLifecycleError, match="requires selected_shooting_type"):
        selected.with_declaration(attack_pools=())
    with pytest.raises(GameLifecycleError, match="attack_pools must be attack pools"):
        selected_with_type.with_declaration(
            attack_pools=cast(tuple[RangedAttackPool, ...], (object(),))
        )
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
            shooting_type=ShootingType.NORMAL,
            firing_deck_source_unit_instance_id="source-unit",
        )
    with pytest.raises(GameLifecycleError, match="token must be a string"):
        shooting_target_violation_code_from_token(object())
    with pytest.raises(GameLifecycleError, match="Unsupported shooting target violation"):
        shooting_target_violation_code_from_token("not-a-violation")
    with pytest.raises(GameLifecycleError, match="requires a WeaponProfile"):
        fixed_attacks_for_profile(cast(WeaponProfile, object()))


def test_shooting_phase_state_rejects_declaration_type_and_sequence_drift() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    weapon_profile = _first_weapon_profile(lifecycle, attacker)
    selection = ShootingUnitSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=attacker.unit_instance_id,
        request_id="phase14f-state-declaration-request",
        result_id="phase14f-state-declaration-result",
    )
    type_selection = ShootingTypeSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=attacker.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        request_id="phase14f-state-type-request",
        result_id="phase14f-state-type-result",
    )
    selected_with_type = (
        ShootingPhaseState(battle_round=1, active_player_id="player-a")
        .with_unit_selection(selection)
        .with_shooting_type_selection(type_selection)
    )
    normal_pool = _attack_pool_for_test(
        attacker=attacker,
        defender=defender,
        weapon_profile=weapon_profile,
        attacks=1,
    )
    valid_sequence = AttackSequence.start(
        sequence_id="phase14f-valid-state-sequence",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(normal_pool,),
    )
    type_drift_pool = replace(normal_pool, shooting_type=ShootingType.ASSAULT)
    pool_drift_sequence = AttackSequence.start(
        sequence_id="phase14f-pool-drift-sequence",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(replace(normal_pool, attacks=2),),
    )
    unit_drift_sequence = AttackSequence.start(
        sequence_id="phase14f-unit-drift-sequence",
        attacker_player_id="player-a",
        attacking_unit_instance_id=defender.unit_instance_id,
        attack_pools=(normal_pool,),
    )

    with pytest.raises(GameLifecycleError, match="attack_sequence requires no active_selection"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=(attacker.unit_instance_id,),
            active_selection=selection,
            attack_sequence=valid_sequence,
        )
    with pytest.raises(GameLifecycleError, match="Completed Shooting phase"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            phase_complete=True,
            attack_sequence=valid_sequence,
        )
    with pytest.raises(GameLifecycleError, match="active attack sequence"):
        ShootingPhaseState(
            battle_round=1,
            active_player_id="player-a",
            attack_sequence=valid_sequence,
        ).with_phase_complete()
    with pytest.raises(GameLifecycleError, match="attack pool type drift"):
        selected_with_type.with_declaration(attack_pools=(type_drift_pool,))
    with pytest.raises(GameLifecycleError, match="attack_sequence is invalid"):
        selected_with_type.with_declaration(
            attack_pools=(normal_pool,),
            attack_sequence=cast(AttackSequence, object()),
        )
    with pytest.raises(GameLifecycleError, match="attack_sequence pool drift"):
        selected_with_type.with_declaration(
            attack_pools=(normal_pool,),
            attack_sequence=pool_drift_sequence,
        )
    with pytest.raises(GameLifecycleError, match="attack_sequence unit drift"):
        selected_with_type.with_declaration(
            attack_pools=(normal_pool,),
            attack_sequence=unit_drift_sequence,
        )


def test_advanced_unit_is_eligible_to_shoot_only_when_state_permits() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1", "intercessor-2"))
    state = _state(lifecycle)
    state.record_advanced_unit_state(
        _advanced_unit_state(units["intercessor-1"].unit_instance_id, can_shoot=False)
    )

    request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    assert {option.option_id for option in request.options} == {
        COMPLETE_SHOOTING_PHASE_OPTION_ID,
        units["intercessor-1"].unit_instance_id,
        units["intercessor-2"].unit_instance_id,
    }

    base_profile = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id="core-bolt-rifle:standard",
    )
    non_assault_catalog = _catalog_with_replaced_bolt_profiles(
        (replace(base_profile, keywords=(), abilities=()),)
    )
    restricted_lifecycle, restricted_units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1", "intercessor-2"),
        catalog=non_assault_catalog,
    )
    restricted_state = _state(restricted_lifecycle)
    restricted_state.record_advanced_unit_state(
        _advanced_unit_state(
            restricted_units["intercessor-1"].unit_instance_id,
            can_shoot=False,
        )
    )
    restricted_request = _decision_request(
        restricted_lifecycle.advance_until_decision_or_terminal()
    )
    assert {option.option_id for option in restricted_request.options} == {
        COMPLETE_SHOOTING_PHASE_OPTION_ID,
        restricted_units["intercessor-2"].unit_instance_id,
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
        display_geometry=_display_geometry(
            center_x_inches=20.0,
            center_y_inches=35.0,
            width_inches=4.0,
            depth_inches=4.0,
        ),
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
    assert close_candidates[0].shooting_types == (ShootingType.NORMAL,)


def test_gone_to_ground_reduces_hidden_detection_range_in_solid_terrain() -> None:
    scenario, attacker, target, profile = _gone_to_ground_detection_context()
    solid_woods = _dense_solid_woods()

    gone_to_ground_candidate = shooting_target_candidate_for_model(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        weapon_profile=profile,
        target_unit_id=target.unit_instance_id,
        terrain_features=(solid_woods,),
        hidden_target_unit_ids=(target.unit_instance_id,),
    )
    recent_shot_candidate = shooting_target_candidate_for_model(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        weapon_profile=profile,
        target_unit_id=target.unit_instance_id,
        terrain_features=(solid_woods,),
        hidden_target_unit_ids=(target.unit_instance_id,),
        target_unit_ids_with_recent_ranged_attacks=(target.unit_instance_id,),
    )

    assert gone_to_ground_candidate.violation_code is (
        ShootingTargetViolationCode.OUTSIDE_DETECTION_RANGE
    )
    assert gone_to_ground_candidate.message == (
        "Hidden target is outside the attacker's effective detection range."
    )
    assert recent_shot_candidate.is_legal
    assert recent_shot_candidate.line_of_sight_witness is not None
    assert not recent_shot_candidate.line_of_sight_witness.unit_fully_visible


def test_gone_to_ground_does_not_reduce_detection_when_solid_target_fully_visible() -> None:
    scenario, attacker, target, profile = _gone_to_ground_detection_context()
    towering_attacker = replace(attacker, keywords=(*attacker.keywords, "TOWERING"))

    candidate = shooting_target_candidate_for_model(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=towering_attacker,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        weapon_profile=profile,
        target_unit_id=target.unit_instance_id,
        terrain_features=(_dense_solid_woods(),),
        hidden_target_unit_ids=(target.unit_instance_id,),
    )

    assert candidate.is_legal
    assert candidate.line_of_sight_witness is not None
    assert candidate.line_of_sight_witness.unit_fully_visible


def test_gone_to_ground_does_not_reduce_detection_for_non_solid_obscuring_terrain() -> None:
    scenario, attacker, target, profile = _gone_to_ground_detection_context()
    non_solid_hill = _non_solid_hill_with_wall()

    candidate = shooting_target_candidate_for_model(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        weapon_profile=profile,
        target_unit_id=target.unit_instance_id,
        terrain_features=(non_solid_hill,),
        hidden_target_unit_ids=(target.unit_instance_id,),
    )

    assert candidate.is_legal
    assert candidate.line_of_sight_witness is not None
    assert not candidate.line_of_sight_witness.unit_fully_visible
    assert any(
        record.blocks_full_visibility and record.terrain_feature_kind is TerrainFeatureKind.HILLS
        for record in candidate.line_of_sight_witness.all_blocker_records()
    )


def test_ranged_attack_history_tracks_current_and_previous_player_turns() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    unit_id = units["intercessor-1"].unit_instance_id
    state.record_ranged_attack_history(
        RangedAttackHistoryRecord(
            player_id="player-a",
            unit_instance_id=unit_id,
            battle_round=1,
            active_player_id="player-a",
            phase=BattlePhase.SHOOTING,
            request_id="phase13b-ranged-history-request",
            result_id="phase13b-ranged-history-result",
        )
    )

    assert state.unit_made_ranged_attacks_current_or_previous_turn(unit_instance_id=unit_id)

    state.active_player_id = "player-b"
    restored_state = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))
    )
    assert restored_state.unit_made_ranged_attacks_current_or_previous_turn(
        unit_instance_id=unit_id
    )

    restored_state.battle_round = 2
    restored_state.active_player_id = "player-a"
    assert not restored_state.unit_made_ranged_attacks_current_or_previous_turn(
        unit_instance_id=unit_id
    )


def test_phase13d_lone_operative_within_twelve_is_visible_even_with_closer_enemy() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_specs=(
            ("lone-target", "core-intercessor-like-infantry", "core-intercessor-like", 5),
            ("closer-enemy", "core-intercessor-like-infantry", "core-intercessor-like", 5),
        ),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    profile = _first_weapon_profile(lifecycle, attacker)
    lone_target = replace(
        units["lone-target"],
        keywords=(*units["lone-target"].keywords, "Lone Operative"),
    )
    _replace_unit_instance_in_state(state=state, replacement=lone_target)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=lone_target,
        army_id="army-beta",
        player_id="player-b",
        poses=_compact_test_unit_poses(origin=Pose.at(26.0, 35.0), model_count=5),
    )
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=units["closer-enemy"],
        army_id="army-beta",
        player_id="player-b",
        poses=_compact_test_unit_poses(origin=Pose.at(16.0, 42.0), model_count=5),
    )

    candidates = shooting_target_candidates_for_unit(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=profile,
        target_unit_ids=(lone_target.unit_instance_id,),
    )

    assert candidates[0].is_legal
    assert candidates[0].shooting_types == (ShootingType.NORMAL,)


def test_phase13d_lone_operative_descriptor_blocks_targets_outside_twelve() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_pose=Pose.at(32.0, 35.0),
        catalog=_catalog_with_lone_operative_datasheet(),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    target = units["enemy"]
    profile = _first_weapon_profile(lifecycle, attacker)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )

    blocked_candidates = shooting_target_candidates_for_unit(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=profile,
        target_unit_ids=(target.unit_instance_id,),
    )
    close_scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=target,
        army_id="army-beta",
        player_id="player-b",
        poses=_compact_test_unit_poses(origin=Pose.at(25.0, 35.0), model_count=5),
    )
    close_candidates = shooting_target_candidates_for_unit(
        scenario=close_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=profile,
        target_unit_ids=(target.unit_instance_id,),
    )

    assert blocked_candidates[0].violation_code is ShootingTargetViolationCode.LONE_OPERATIVE
    assert blocked_candidates[0].targeting_rule_ids == (LONE_OPERATIVE_RULE_ID,)
    assert close_candidates[0].is_legal


@pytest.mark.parametrize("dead_side", ["attacker", "target"])
def test_phase13d_lone_operative_targeting_ignores_dead_model_placements(
    dead_side: str,
) -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_pose=Pose.at(32.0, 35.0),
        catalog=_catalog_with_lone_operative_datasheet(),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    target = units["enemy"]
    profile = _first_weapon_profile(lifecycle, attacker)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )

    if dead_side == "attacker":
        attacker = _unit_with_dead_model(attacker, index=0)
        scenario = _scenario_with_replaced_unit(scenario=scenario, replacement=attacker)
        scenario = _scenario_with_unit_pose(
            scenario=scenario,
            unit=attacker,
            army_id="army-alpha",
            player_id="player-a",
            poses=(
                Pose.at(22.0, 35.0),
                Pose.at(10.0, 35.0),
                Pose.at(11.4, 35.0),
                Pose.at(12.8, 35.0),
                Pose.at(14.2, 35.0),
            ),
        )
        scenario = _scenario_with_unit_pose(
            scenario=scenario,
            unit=target,
            army_id="army-beta",
            player_id="player-b",
            poses=_compact_test_unit_poses(origin=Pose.at(32.0, 35.0), model_count=5),
        )
    elif dead_side == "target":
        target = _unit_with_dead_model(target, index=0)
        scenario = _scenario_with_replaced_unit(scenario=scenario, replacement=target)
        scenario = _scenario_with_unit_pose(
            scenario=scenario,
            unit=target,
            army_id="army-beta",
            player_id="player-b",
            poses=(
                Pose.at(22.0, 35.0),
                Pose.at(32.0, 35.0),
                Pose.at(33.4, 35.0),
                Pose.at(34.8, 35.0),
                Pose.at(36.2, 35.0),
            ),
        )
    else:
        raise AssertionError(f"Unsupported dead-side fixture {dead_side}.")

    candidates = shooting_target_candidates_for_unit(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=profile,
        target_unit_ids=(target.unit_instance_id,),
    )

    assert candidates[0].violation_code is ShootingTargetViolationCode.LONE_OPERATIVE
    assert candidates[0].targeting_rule_ids == (LONE_OPERATIVE_RULE_ID,)


def test_phase13d_stealth_descriptor_applies_ranged_hit_roll_penalty() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_pose=Pose.at(25.0, 35.0),
        catalog=_catalog_with_stealth_datasheet(),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    target = units["enemy"]
    profile = _first_weapon_profile(lifecycle, attacker)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )

    candidates = shooting_target_candidates_for_unit(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=profile,
        target_unit_ids=(target.unit_instance_id,),
    )

    assert candidates[0].is_legal
    assert candidates[0].hit_roll_modifier == -1
    assert STEALTH_RULE_ID in candidates[0].targeting_rule_ids
    assert candidates[0] == type(candidates[0]).from_payload(candidates[0].to_payload())


def test_phase14i_hunter_target_candidate_requires_one_listed_keyword() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    infantry_target = replace(units["enemy"], keywords=("INFANTRY",))
    _replace_unit_instance_in_state(state=state, replacement=infantry_target)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    hunter_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14i-hunter-vehicle-monster-gate",
        keywords=(WeaponKeyword.HUNTER,),
        abilities=(AbilityDescriptor.hunter(target_keywords=("VEHICLE/MONSTER",)),),
    )

    invalid_candidates = shooting_target_candidates_for_unit(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=hunter_profile,
        target_unit_ids=(infantry_target.unit_instance_id,),
    )
    assert invalid_candidates[0].violation_code is (
        ShootingTargetViolationCode.HUNTER_TARGET_KEYWORD_MISMATCH
    )
    assert invalid_candidates[0].targeting_rule_ids == (HUNTER_RULE_ID,)

    vehicle_target = replace(infantry_target, keywords=("Vehicle",))
    _replace_unit_instance_in_state(state=state, replacement=vehicle_target)
    legal_scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    legal_candidates = shooting_target_candidates_for_unit(
        scenario=legal_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=hunter_profile,
        target_unit_ids=(vehicle_target.unit_instance_id,),
    )

    assert legal_candidates[0].is_legal
    assert HUNTER_RULE_ID in legal_candidates[0].targeting_rule_ids


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
    assert vehicle_candidates[0].shooting_types == (ShootingType.CLOSE_QUARTERS,)

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
    assert pistol_candidates[0].shooting_types == (ShootingType.CLOSE_QUARTERS,)

    close_quarters_profile = replace(
        infantry_profile,
        keywords=(WeaponKeyword.CLOSE_QUARTERS,),
    )
    close_quarters_candidates = shooting_target_candidates_for_unit(
        scenario=infantry_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=infantry,
        weapon_profile=close_quarters_profile,
        target_unit_ids=(infantry_units["enemy"].unit_instance_id,),
    )
    assert close_quarters_candidates[0].is_legal
    assert close_quarters_candidates[0].hit_roll_modifier == 0
    assert close_quarters_candidates[0].shooting_types == (ShootingType.CLOSE_QUARTERS,)

    blast_profile = replace(
        infantry_profile,
        keywords=(WeaponKeyword.CLOSE_QUARTERS, WeaponKeyword.BLAST),
    )
    blast_candidates = shooting_target_candidates_for_unit(
        scenario=infantry_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=infantry,
        weapon_profile=blast_profile,
        target_unit_ids=(infantry_units["enemy"].unit_instance_id,),
    )
    assert blast_candidates[0].violation_code is ShootingTargetViolationCode.LOCKED_IN_COMBAT


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
    assert monster_candidates[0].shooting_types == (ShootingType.CLOSE_QUARTERS,)

    close_quarters_profile = replace(profile, keywords=(WeaponKeyword.CLOSE_QUARTERS,))
    close_quarters_candidates = shooting_target_candidates_for_unit(
        scenario=monster_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=close_quarters_profile,
        target_unit_ids=(monster_target.unit_instance_id,),
    )
    assert close_quarters_candidates[0].is_legal
    assert close_quarters_candidates[0].hit_roll_modifier == 0

    blast_profile = replace(profile, keywords=(WeaponKeyword.BLAST,))
    blast_candidates = shooting_target_candidates_for_unit(
        scenario=monster_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=blast_profile,
        target_unit_ids=(monster_target.unit_instance_id,),
    )
    assert blast_candidates[0].violation_code is ShootingTargetViolationCode.LOCKED_IN_COMBAT


def test_mixed_close_quarters_and_non_close_quarters_declarations_reject_before_pop() -> None:
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
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection_request,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        selection_result_id="phase13b-pistol-select",
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
        == "mixed_close_quarters_non_close_quarters_declaration"
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
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=first_request,
        unit_instance_id=units["transport-1"].unit_instance_id,
        selection_result_id="phase13b-select-transport",
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
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection_request,
        unit_instance_id=units["transport-1"].unit_instance_id,
        selection_result_id="phase13b-select-firing-deck-two-weapons",
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

    state.battlefield_state = replace(
        scenario.battlefield_state,
        terrain_features=(blocking_ruin,),
    )
    status = lifecycle.advance_until_decision_or_terminal()
    _assert_waiting_for_movement_unit(status)
    assert state.current_battle_phase is BattlePhase.MOVEMENT


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


def test_phase13c_allocated_cover_excludes_attacker_and_target_units_as_blockers() -> None:
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
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=attacker,
        army_id="army-alpha",
        player_id="player-a",
        poses=(
            Pose.at(10.0, 35.0),
            Pose.at(20.0, 35.0),
            Pose.at(10.0, 5.0),
            Pose.at(10.0, 7.0),
            Pose.at(10.0, 9.0),
        ),
    )
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=target,
        army_id="army-beta",
        player_id="player-b",
        poses=(
            Pose.at(35.0, 35.0, facing_degrees=180.0),
            Pose.at(25.0, 35.0, facing_degrees=180.0),
            Pose.at(35.0, 5.0, facing_degrees=180.0),
            Pose.at(35.0, 7.0, facing_degrees=180.0),
            Pose.at(35.0, 9.0, facing_degrees=180.0),
        ),
    )
    far_ruin = TerrainFeatureDefinition(
        feature_id="phase13c-far-cover-ruin",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=80.0,
        footprint_center_y_inches=10.0,
        footprint_width_inches=4.0,
        footprint_depth_inches=4.0,
        display_geometry=_display_geometry(
            center_x_inches=80.0,
            center_y_inches=10.0,
            width_inches=4.0,
            depth_inches=4.0,
        ),
        walls=(
            TerrainWallDefinition(
                wall_id="wall",
                center_x_inches=80.0,
                center_y_inches=10.0,
                bottom_z_inches=0.0,
                width_inches=0.2,
                depth_inches=4.0,
                height_inches=4.0,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="ground-floor",
                center_x_inches=80.0,
                center_y_inches=10.0,
                bottom_z_inches=0.0,
                width_inches=4.0,
                depth_inches=4.0,
                thickness_inches=0.1,
            ),
        ),
    )
    state.battlefield_state = replace(
        scenario.battlefield_state,
        terrain_features=(far_ruin,),
    )
    weapon_profile = _first_weapon_profile(lifecycle, attacker)
    pool = _attack_pool_for_test(
        attacker=attacker,
        defender=target,
        weapon_profile=weapon_profile,
        attacks=1,
    )

    cover = cover_for_allocated_model(
        state=state,
        ruleset_descriptor=_ruleset(),
        pool=pool,
        allocated_model_id=target.own_models[0].model_instance_id,
    )

    assert cover is not None
    assert cover.target_unit_visible is True
    assert cover.target_unit_fully_visible is True
    assert cover.has_benefit is False


def test_weapon_declaration_payload_round_trips_and_preserves_selection_evidence() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection_request,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        selection_result_id="phase13b-select-round-trip",
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


def test_one_shot_weapon_use_is_battle_scoped_and_blocks_redeclaration() -> None:
    one_shot_profile = replace(
        _weapon_profile_by_wargear(
            wargear_id="core-bolt-rifle",
            weapon_profile_id="core-bolt-rifle:standard",
        ),
        profile_id="one-shot-bolt-rifle",
        name="One-shot bolt rifle",
        attack_profile=AttackProfile.fixed(1),
        keywords=(WeaponKeyword.ONE_SHOT,),
    )
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        game_id="one-shot-redeclaration",
        catalog=_catalog_with_replaced_bolt_profiles((one_shot_profile,)),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    used_model = attacker.own_models[0]
    used_wargear_id = attacker.wargear_selections[0].wargear_ids[0]
    state.record_one_shot_weapon_selected(
        model_instance_id=used_model.model_instance_id,
        wargear_id=used_wargear_id,
        weapon_profile_id=one_shot_profile.profile_id,
        source_phase=BattlePhase.SHOOTING,
        selection_id="one-shot-pre-used-selection",
    )

    encoded_state = cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    restored_state = GameState.from_payload(encoded_state)
    assert not restored_state.one_shot_weapon_available(
        model_instance_id=used_model.model_instance_id,
        wargear_id=used_wargear_id,
        weapon_profile_id=one_shot_profile.profile_id,
    )

    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection_request,
        unit_instance_id=attacker.unit_instance_id,
        selection_result_id="one-shot-select-unit",
    )
    request_payload = cast(dict[str, object], declaration_request.payload)
    proposal_request = cast(dict[str, object], request_payload["proposal_request"])
    weapons = cast(list[dict[str, object]], proposal_request["available_weapons"])

    assert all(
        weapon["model_instance_id"] != used_model.model_instance_id
        for weapon in weapons
        if weapon["weapon_profile_id"] == one_shot_profile.profile_id
    )

    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
        weapon_profile_id=one_shot_profile.profile_id,
    )
    stale_payload = proposal.to_payload()
    stale_payload["declarations"][0]["attacker_model_instance_id"] = used_model.model_instance_id
    invalid_status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=stale_payload,
        result_id="one-shot-stale-redeclaration",
    )
    invalid_payload = cast(dict[str, object], invalid_status.payload)
    validation = cast(dict[str, object], invalid_payload["proposal_validation"])
    violation = cast(list[dict[str, object]], validation["violations"])[0]

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert violation["violation_code"] == "weapon_declaration_unavailable"
    assert lifecycle.decision_controller.queue.peek_next() == declaration_request


def test_duplicate_anti_selection_flows_from_declaration_into_wound_resolution() -> None:
    anti_vehicle = AbilityDescriptor.anti_keyword("Vehicle", 4)
    anti_infantry = AbilityDescriptor.anti_keyword("Infantry", 2)
    duplicate_anti_profile = replace(
        _weapon_profile_by_wargear(
            wargear_id="core-bolt-rifle",
            weapon_profile_id="core-bolt-rifle:standard",
        ),
        profile_id="phase14i-duplicate-anti-bolt-rifle",
        name="Phase 14I duplicate Anti bolt rifle",
        attack_profile=AttackProfile.fixed(1),
        keywords=(WeaponKeyword.TORRENT,),
        abilities=(anti_vehicle, anti_infantry),
        damage_profile=DamageProfile.fixed(1),
    )
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        game_id="phase14i-duplicate-anti",
        catalog=_catalog_with_extra_bolt_profile(duplicate_anti_profile),
    )
    state = _state(lifecycle)
    defender_keywords = {
        keyword.upper().replace(" ", "_").replace("-", "_") for keyword in units["enemy"].keywords
    }
    defender = replace(
        units["enemy"],
        keywords=tuple(sorted({*defender_keywords, "INFANTRY", "VEHICLE"})),
    )
    _replace_unit_instance_in_state(state=state, replacement=defender)
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection_request,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        selection_result_id="phase14i-duplicate-anti-select",
    )
    request_payload = cast(dict[str, object], declaration_request.payload)
    proposal_request = cast(dict[str, object], request_payload["proposal_request"])
    target_candidates = cast(list[dict[str, object]], proposal_request["target_candidates"])
    required_selection_payloads = [
        cast(dict[str, object], selection_payload)
        for candidate in target_candidates
        if candidate["target_unit_instance_id"] == defender.unit_instance_id
        for selection_payload in cast(
            list[object],
            candidate["required_weapon_ability_selections"],
        )
    ]
    anti_selection_request = next(
        payload
        for payload in required_selection_payloads
        if payload["decision_type"] == WEAPON_ABILITY_SELECTION_DECISION_TYPE
    )
    anti_options = cast(list[dict[str, object]], anti_selection_request["options"])
    anti_interaction = cast(dict[str, object], anti_selection_request["interaction"])
    nested_requests = cast(list[dict[str, object]], request_payload["nested_interaction_requests"])

    assert {option["option_id"] for option in anti_options} == {
        anti_vehicle.ability_id,
        anti_infantry.ability_id,
    }
    assert anti_selection_request in nested_requests
    assert anti_selection_request["schema_version"] == "annotated-decision-request-v1"
    assert anti_interaction["schema_version"] == "interaction-descriptor-v2-variants"
    assert anti_interaction["interaction_kind"] == "finite_option_list"
    assert (
        cast(dict[str, object], anti_interaction["constraints"])["submission_schema_ref"]
        == "finite-submission.schema.json"
    )
    owner_view = project_game_view(lifecycle=lifecycle, viewer_player_id="player-a")
    opponent_view = project_game_view(lifecycle=lifecycle, viewer_player_id="player-b")
    assert owner_view["nested_interaction_requests"] == nested_requests
    assert opponent_view["nested_interaction_requests"] == nested_requests

    missing_selection_proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=defender.unit_instance_id,
        weapon_profile_id=duplicate_anti_profile.profile_id,
    )
    missing_selection_status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=missing_selection_proposal.to_payload(),
        result_id="phase14i-duplicate-anti-missing-selection",
    )
    missing_selection_validation = cast(
        dict[str, object],
        cast(dict[str, object], missing_selection_status.payload)["proposal_validation"],
    )
    assert missing_selection_status.status_kind is LifecycleStatusKind.INVALID
    assert (
        cast(list[dict[str, object]], missing_selection_validation["violations"])[0][
            "violation_code"
        ]
        == "weapon_ability_selection_required"
    )
    assert lifecycle.decision_controller.queue.peek_next() == declaration_request

    selected_proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=defender.unit_instance_id,
        weapon_profile_id=duplicate_anti_profile.profile_id,
        selected_weapon_ability_ids=(anti_vehicle.ability_id,),
    )
    status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=selected_proposal.to_payload(),
        result_id="phase14i-duplicate-anti-selected",
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION, status.payload
    accepted_payload = _last_event_payload(lifecycle, "shooting_declaration_accepted")
    pool_payload = cast(list[dict[str, object]], accepted_payload["attack_pools"])[0]
    wound_payloads = _attack_step_payloads(lifecycle, AttackSequenceStep.WOUND)

    assert pool_payload["selected_weapon_ability_ids"] == [anti_vehicle.ability_id]
    assert wound_payloads
    assert cast(dict[str, object], wound_payloads[0]["payload"])["selected_weapon_ability_ids"] == [
        anti_vehicle.ability_id
    ]
    assert cast(dict[str, object], wound_payloads[0]["payload"])["critical_threshold"] == 4


def test_shooting_declaration_request_drift_diagnostics_are_typed() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection_request,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        selection_result_id="phase13b-select-drift-diagnostics",
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


def _unit_with_dead_model(unit: UnitInstance, *, index: int) -> UnitInstance:
    models = list(unit.own_models)
    model = models[index]
    models[index] = replace(model, wounds_remaining=0)
    return replace(unit, own_models=tuple(models))


def _unit_with_first_model_wounds(
    unit: UnitInstance,
    *,
    wounds_remaining: int,
) -> UnitInstance:
    models = list(unit.own_models)
    models[0] = replace(models[0], wounds_remaining=wounds_remaining)
    return replace(unit, own_models=tuple(models))


def _shooting_proposal_request_payload(request: DecisionRequest) -> dict[str, object]:
    payload = cast(dict[str, object], request.payload)
    return cast(dict[str, object], payload["proposal_request"])


def _ctan_power_proposal_from_request(
    *,
    request: DecisionRequest,
    target_unit_id: str,
    weapon_count: int,
) -> ShootingDeclarationProposal:
    proposal_request = _shooting_proposal_request_payload(request)
    weapons = [
        weapon
        for weapon in cast(list[dict[str, object]], proposal_request["available_weapons"])
        if _weapon_payload_has_keyword(weapon, WeaponKeyword.CTAN_POWER)
    ]
    if len(weapons) < weapon_count:
        raise AssertionError("Test request did not expose enough C'tan Power weapons.")
    target_candidate = next(
        candidate
        for candidate in cast(list[dict[str, object]], proposal_request["target_candidates"])
        if candidate["target_unit_instance_id"] == target_unit_id and candidate["is_legal"] is True
    )
    declarations = tuple(
        WeaponDeclaration(
            attacker_model_instance_id=cast(str, weapon["model_instance_id"]),
            wargear_id=cast(str, weapon["wargear_id"]),
            weapon_profile_id=cast(str, weapon["weapon_profile_id"]),
            target_unit_instance_id=target_unit_id,
            shooting_type=_first_shooting_type(target_candidate),
        )
        for weapon in weapons[:weapon_count]
    )
    return _proposal_from_declarations(
        request=request,
        declarations=declarations,
    )


def _weapon_payload_has_keyword(
    weapon: dict[str, object],
    keyword: WeaponKeyword,
) -> bool:
    profile_payload = cast(dict[str, object], weapon["weapon_profile"])
    keywords = cast(list[str], profile_payload["keywords"])
    return keyword.value in keywords


def _catalog_with_ctan_power_selection_limit() -> ArmyCatalog:
    base = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id="core-bolt-rifle:standard",
    )
    ctan_profiles = (
        _ctan_power_profile(base, profile_id="ctan-antimatter-meteor", name="Antimatter Meteor"),
        _ctan_power_profile(base, profile_id="ctan-cosmic-fire", name="Cosmic Fire"),
        _ctan_power_profile(base, profile_id="ctan-times-arrow", name="Time's Arrow"),
    )
    catalog = _catalog_with_replaced_bolt_profiles(ctan_profiles)
    damaged_effect = DamagedEffectDefinition(
        damaged_effect_id="core-intercessor-like-infantry:damaged:ctan-power-selection",
        model_profile_id="core-intercessor-like",
        wounds_min=1,
        wounds_max=1,
        effect_kind=DamagedEffectKind.SHOOTING_WEAPON_SELECTION_LIMIT,
        max_selections=1,
        baseline_max_selections=2,
        selection_group="C'tan Powers weapons",
        source_id="datasheet:tesseract-vault:damaged:ctan-power-selection",
    )
    datasheets: list[DatasheetDefinition] = []
    for datasheet in catalog.datasheets:
        if datasheet.datasheet_id == "core-intercessor-like-infantry":
            datasheets.append(
                replace(
                    datasheet,
                    composition=tuple(
                        replace(composition, min_models=1) for composition in datasheet.composition
                    ),
                    damaged_effects=(damaged_effect,),
                )
            )
            continue
        datasheets.append(datasheet)
    return replace(catalog, datasheets=tuple(datasheets))


def _ctan_power_profile(
    base: WeaponProfile,
    *,
    profile_id: str,
    name: str,
) -> WeaponProfile:
    return replace(
        base,
        profile_id=profile_id,
        name=name,
        range_profile=RangeProfile.distance(60),
        attack_profile=AttackProfile.fixed(1),
        damage_profile=DamageProfile.fixed(1),
        keywords=(WeaponKeyword.CTAN_POWER,),
        abilities=(),
        source_ids=(f"datasheet:tesseract-vault:wargear:{profile_id}",),
    )
