from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast

import pytest
from tests.phase13b_shooting_declaration_helpers import (
    _advanced_unit_state,
    _assert_command_reroll_request,
    _assert_invalid_proposal_status,
    _assert_stale_damage_model_choice_rejected_before_queue_pop,
    _assert_waiting_for_movement_unit,
    _attached_enemy_declarations,
    _attached_enemy_unit_specs,
    _attached_formation_for_player,
    _attack_pool_for_test,
    _attack_sequence_private,
    _attack_step_payload,
    _attack_step_payloads,
    _benefit_of_cover_result,
    _blocking_ruin,
    _catalog_with_core_feel_no_pain_datasheet,
    _catalog_with_deadly_demise_datasheet,
    _catalog_with_extra_bolt_profile,
    _catalog_with_same_profile_id_target_cache_collision_weapons,
    _command_reroll_use_option_id,
    _compact_test_unit_poses,
    _continue_damage_model_choices,
    _damage_model_choice_lifecycle,
    _decision_request,
    _destroyed_transport_hazard_roll_results_for_test,
    _destroyed_transport_pending_for_test,
    _destroyed_transport_placement_payload_for_test,
    _destroyed_transport_proposal_request_for_test,
    _dice_rolled_payloads_for_spec,
    _display_geometry,
    _drain_damage_model_choices_with_manager,
    _event_payloads,
    _first_weapon_profile,
    _fixed_roll_result,
    _grant_command_reroll_cp,
    _last_event_payload,
    _model_with_attached_role,
    _model_with_characteristic,
    _paused_optional_fnp_lifecycle,
    _phase13f_cover_effect,
    _phase13f_gate_weapon_profile,
    _phase14l_multi_group_lifecycle,
    _phase14l_multi_target_declarations,
    _phase14l_submit_multi_group_declaration,
    _phase14l_test1_dice_results,
    _phase14l_test1_target_model,
    _phase17_post_shoot_cover_denial_effect,
    _phase18b_shooting_hit_command_reroll_status,
    _precision_request_for_fixture,
    _proposal_decision_result,
    _proposal_from_declarations,
    _proposal_from_request,
    _record_parameterized_result_for_apply,
    _replace_enemy_with_attached_character_fixture,
    _replace_unit_instance_in_state,
    _replace_unit_toughness,
    _ruleset,
    _scenario_with_replaced_unit,
    _scenario_with_unit_pose,
    _select_shooting_unit_and_type,
    _shooting_lifecycle,
    _shooting_phase_private,
    _single_deadly_demise_source,
    _state,
    _submit_all_pending_fnp_declines,
    _submit_payload,
    _submit_phase13f_pending_attack_choices,
    _submit_result,
    _unit_placement_at,
    _weapon_payload_to_declaration_payload,
    _weapon_profile_by_wargear,
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollResult,
    DiceRollSpec,
    DiceRollState,
    DiceRollStatePayload,
)
from warhammer40k_core.core.modifiers import ModifierStack, RollModifier
from warhammer40k_core.core.ruleset_descriptor import (
    CoverEffect,
    CoverPolicyDescriptor,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AttackProfile,
    DamageProfile,
    DevastatingWoundsEffect,
    WeaponKeyword,
    WeaponProfilePayload,
)
from warhammer40k_core.engine.attack_sequence import (
    SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
    SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE,
    SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
    AttackModifierStackSet,
    AttackResolutionContextPayload,
    AttackSequence,
    AttackSequenceEvent,
    AttackSequenceEventHandler,
    AttackSequenceHooks,
    AttackSequenceStep,
    DeferredMortalWounds,
    FastDiceGroup,
    GatheredAttackGroup,
    HitRoll,
    IdenticalAttackSignature,
    PendingDestroyedTransportDisembark,
    PendingGroupedDamage,
    SaveDieEntryPayload,
    WoundRoll,
    apply_destroyed_transport_disembark_proposal_decision,
    attack_sequence_hit_roll_spec,
    attack_sequence_step_from_token,
    attack_sequence_wound_roll_spec,
    deadly_demise_mortal_wounds_roll_spec,
    deadly_demise_trigger_roll_spec,
    gathered_attack_groups_for_target,
    identical_attack_signature,
    invalid_destroyed_transport_disembark_proposal_status,
    is_destroyed_transport_disembark_proposal_request,
    resolve_attack_sequence_until_blocked,
    wound_roll_target_number,
)
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    record_core_feel_no_pain_sources_for_unit,
)
from warhammer40k_core.engine.core_stratagem_effects import SMOKESCREEN_EFFECT_KIND
from warhammer40k_core.engine.damage_allocation import (
    DECLINE_DESTRUCTION_REACTION_OPTION_ID,
    SELECT_ALLOCATION_ORDER_DECISION_TYPE,
    SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
    SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
    AllocationGroup,
    AllocationGroupPayload,
    AllocationGroupRole,
    AllocationOrderDecision,
    AttackAllocation,
    AttackAllocationConstraint,
    AttackAllocationRuleContext,
    DamageAllocationModelDecision,
    DamageApplication,
    DamageKind,
    DestructionReactionDecision,
    DestructionReactionKind,
    DestructionReactionSource,
    FeelNoPainAttackCondition,
    FeelNoPainDecision,
    FeelNoPainResolution,
    FeelNoPainRoll,
    FeelNoPainSource,
    MortalWoundApplication,
    MortalWoundApplicationProgress,
    MortalWoundRoutingResult,
    allocation_context_for_unit,
    allocation_group_role_from_token,
    allocation_groups_for_context,
    apply_damage_to_model,
    apply_mortal_wounds_to_unit,
    build_allocation_order_request,
    build_destruction_reaction_request,
    build_feel_no_pain_request,
    continue_mortal_wound_application,
    damage_kind_from_token,
    destruction_reaction_kind_from_token,
    feel_no_pain_roll_spec,
    is_mortal_wound_feel_no_pain_request,
    legal_allocation_group_orders,
    model_by_id,
    mortal_wound_feel_no_pain_source_context,
    resolve_mortal_wound_feel_no_pain_decision,
)
from warhammer40k_core.engine.damage_allocation_targets import (
    DamageAllocationTargetState,
    damage_allocation_target_state,
)
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import (
    GENERIC_RULE_EFFECT_KIND,
    EffectExpiration,
    PersistingEffect,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_on_death import (
    model_is_present_on_battlefield,
    remove_models_awaiting_fight_on_death,
    restore_model_awaiting_fight_on_death,
)
from warhammer40k_core.engine.fight_resolution import melee_target_unit_ids
from warhammer40k_core.engine.game_state import (
    GameState,
    GameStatePayload,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.movement_proposals import (
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    PlacementProposalPayload,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    MovementDistanceRecord,
    MovementPhaseState,
)
from warhammer40k_core.engine.phases.shooting import (
    COMPLETE_SHOOTING_PHASE_OPTION_ID,
    SELECT_SHOOTING_TYPE_DECISION_TYPE,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    OutOfPhaseShootingState,
    ShootingPhaseState,
    request_out_of_phase_shooting_declaration,
)
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState
from warhammer40k_core.engine.rules_unit_geometry import geometry_models_for_rules_unit
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.saves import (
    PlungingFireModifier,
    PlungingFireModifierResult,
    SaveKind,
    SaveOption,
    SaveResolutionRule,
    SavingThrow,
    cover_result_has_bonus,
    mandatory_save_option,
    resolve_saving_throw,
    save_kind_from_token,
    save_options_for_model,
    saving_throw_roll_spec,
)
from warhammer40k_core.engine.shooting_targets import (
    PLUNGING_FIRE_RULE_ID,
    ShootingTargetViolationCode,
    shooting_target_candidates_for_unit,
    unit_has_line_of_sight_to_target,
)
from warhammer40k_core.engine.shooting_types import (
    ShootingType,
    shooting_type_from_token,
    validate_shooting_type_tuple,
)
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_stratagem_index
from warhammer40k_core.engine.stratagems import STRATAGEM_WINDOW_DECLINED_EVENT_TYPE
from warhammer40k_core.engine.transports import (
    TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE,
    DisembarkedUnitState,
    DisembarkModeKind,
    TransportCapacityProfile,
    TransportCargoState,
    TransportMovementStatus,
)
from warhammer40k_core.engine.unit_abilities import (
    feel_no_pain_profile_for_unit,
    unit_has_feel_no_pain,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.weapon_abilities import (
    BLAST_RULE_ID,
    FIRE_OVERWATCH_RULE_ID,
    HEAVY_RULE_ID,
    INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID,
    INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,
    INDIRECT_FIRE_NO_VISIBLE_RULE_ID,
    INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID,
    MELTA_RULE_ID,
    PRECISION_RULE_ID,
    RAPID_FIRE_RULE_ID,
    SNAP_SHOOTING_RULE_ID,
)
from warhammer40k_core.engine.weapon_declaration import (
    RangedAttackPool,
    WeaponDeclaration,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)
from warhammer40k_core.geometry.visibility import (
    BenefitOfCoverResult,
)


def test_shooting_unit_selection_and_declaration_use_lifecycle_records() -> None:
    allocation_profile = _phase13f_gate_weapon_profile()
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1", "intercessor-2"),
        game_id="phase13b-allocation-0005",
        catalog=_catalog_with_extra_bolt_profile(allocation_profile),
    )
    state = _state(lifecycle)
    defender = units["enemy"]
    alternate_save_model = replace(
        defender.own_models[1],
        characteristics=tuple(
            CharacteristicValue.from_raw(Characteristic.SAVE, 4)
            if value.characteristic is Characteristic.SAVE
            else value
            for value in defender.own_models[1].characteristics
        ),
    )
    _replace_unit_instance_in_state(
        state=state,
        replacement=replace(
            defender,
            own_models=(defender.own_models[0], alternate_save_model, *defender.own_models[2:]),
        ),
    )
    first_status = lifecycle.advance_until_decision_or_terminal()
    first_request = _decision_request(first_status)

    assert first_request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE
    assert first_request.actor_id == "player-a"
    assert {option.option_id for option in first_request.options} == {
        COMPLETE_SHOOTING_PHASE_OPTION_ID,
        units["intercessor-1"].unit_instance_id,
        units["intercessor-2"].unit_instance_id,
    }

    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=first_request,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        selection_result_id="phase13b-select-shooter",
    )
    assert declaration_request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
        weapon_profile_id=allocation_profile.profile_id,
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
    assert state.shooting_phase_state is not None
    assert state.shooting_phase_state.shot_unit_ids == (units["intercessor-1"].unit_instance_id,)
    assert state.shooting_phase_state.attack_pools[0].target_unit_instance_id == (
        units["enemy"].unit_instance_id
    )
    assert next_request.decision_type == SELECT_ALLOCATION_ORDER_DECISION_TYPE
    assert next_request.actor_id == "player-b"
    assert len(next_request.options) == 2
    assert state.shooting_phase_state.attack_sequence is not None
    allocation_option = next_request.options[0]
    post_allocation_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase13c-submit-allocation",
            request_id=next_request.request_id,
            decision_type=next_request.decision_type,
            actor_id=next_request.actor_id,
            selected_option_id=allocation_option.option_id,
            payload=allocation_option.payload,
        )
    )
    assert post_allocation_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert any(
        record.request.decision_type == SELECT_ALLOCATION_ORDER_DECISION_TYPE
        for record in lifecycle.decision_controller.records
    )
    encoded = json.dumps(lifecycle.decision_controller.to_payload(), sort_keys=True)
    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert "shooting_declaration_accepted" in {
        record.event_type for record in lifecycle.decision_controller.event_log.records
    }


def test_phase14f_select_shooting_type_is_finite_before_declaration() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    unit_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    type_request = _decision_request(
        _submit_result(
            lifecycle,
            request=unit_request,
            option_id=units["intercessor-1"].unit_instance_id,
            result_id="phase14f-select-unit-for-type",
        )
    )

    assert type_request.decision_type == SELECT_SHOOTING_TYPE_DECISION_TYPE
    assert type_request.actor_id == "player-a"
    assert {option.option_id for option in type_request.options} == {ShootingType.NORMAL.value}
    request_payload = cast(dict[str, object], type_request.payload)
    assert request_payload["unit_instance_id"] == units["intercessor-1"].unit_instance_id
    assert request_payload["legal_shooting_types"] == [ShootingType.NORMAL.value]
    option_payload = cast(dict[str, object], type_request.options[0].payload)
    assert option_payload["submission_kind"] == SELECT_SHOOTING_TYPE_DECISION_TYPE
    assert option_payload["shooting_type"] == ShootingType.NORMAL.value
    assert DecisionRequest.from_payload(type_request.to_payload()) == type_request

    declaration_request = _decision_request(
        _submit_result(
            lifecycle,
            request=type_request,
            option_id=ShootingType.NORMAL.value,
            result_id="phase14f-select-normal-type",
        )
    )
    declaration_payload = cast(dict[str, object], declaration_request.payload)
    proposal_request = cast(dict[str, object], declaration_payload["proposal_request"])
    assert declaration_request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE
    assert proposal_request["selected_shooting_type"] == ShootingType.NORMAL.value
    assert _last_event_payload(lifecycle, "shooting_type_selected")["shooting_type"] == (
        ShootingType.NORMAL.value
    )


def test_phase14f_indirect_shooting_type_requires_indirect_fire_weapon_profiles() -> None:
    base_profile = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id="core-bolt-rifle:standard",
    )
    indirect_profile = replace(
        base_profile,
        profile_id="phase14f-mixed-indirect-fire",
        name="Phase 14F mixed Indirect Fire rifle",
        keywords=(WeaponKeyword.INDIRECT_FIRE,),
        abilities=(),
    )
    catalog = _catalog_with_extra_bolt_profile(indirect_profile)
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        catalog=catalog,
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    type_request = _decision_request(
        _submit_result(
            lifecycle,
            request=selection_request,
            option_id=units["intercessor-1"].unit_instance_id,
            result_id="phase14f-mixed-indirect-select-unit",
        )
    )

    assert {option.option_id for option in type_request.options} == {
        ShootingType.NORMAL.value,
        ShootingType.INDIRECT.value,
    }

    declaration_request = _decision_request(
        _submit_result(
            lifecycle,
            request=type_request,
            option_id=ShootingType.INDIRECT.value,
            result_id="phase14f-mixed-indirect-select-type",
        )
    )
    request_payload = cast(dict[str, object], declaration_request.payload)
    proposal_request = cast(dict[str, object], request_payload["proposal_request"])
    weapons = cast(list[dict[str, object]], proposal_request["available_weapons"])
    target_candidates = cast(list[dict[str, object]], proposal_request["target_candidates"])

    assert {weapon["weapon_profile_id"] for weapon in weapons} == {indirect_profile.profile_id}
    assert all(
        WeaponKeyword.INDIRECT_FIRE.value
        in cast(WeaponProfilePayload, weapon["weapon_profile"])["keywords"]
        for weapon in weapons
    )
    assert {
        tuple(cast(list[str], candidate["shooting_types"]))
        for candidate in target_candidates
        if candidate["is_legal"] is True
    } == {(ShootingType.INDIRECT.value,)}

    invalid_proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
        weapon_profile_id=indirect_profile.profile_id,
    )
    invalid_payload = invalid_proposal.to_payload()
    invalid_declaration = invalid_payload["declarations"][0]
    invalid_declaration["weapon_profile_id"] = base_profile.profile_id
    before_records = len(lifecycle.decision_controller.records)

    invalid_status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=invalid_payload,
        result_id="phase14f-mixed-indirect-invalid-normal-profile",
    )
    invalid_validation = cast(
        dict[str, object],
        cast(dict[str, object], invalid_status.payload)["proposal_validation"],
    )
    invalid_violation = cast(list[dict[str, object]], invalid_validation["violations"])[0]

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert invalid_violation["violation_code"] in {
        "weapon_declaration_unavailable",
        "shooting_type_unavailable",
    }
    assert len(lifecycle.decision_controller.records) == before_records
    assert lifecycle.decision_controller.queue.pending_requests == (declaration_request,)

    valid_proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
        weapon_profile_id=indirect_profile.profile_id,
    )
    _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=valid_proposal.to_payload(),
        result_id="phase14f-mixed-indirect-valid",
    )
    accepted_payload = _last_event_payload(lifecycle, "shooting_declaration_accepted")
    pool_payload = cast(list[dict[str, object]], accepted_payload["attack_pools"])[0]
    targeting_rule_ids = cast(list[str], pool_payload["targeting_rule_ids"])

    assert pool_payload["weapon_profile_id"] == indirect_profile.profile_id
    assert pool_payload["shooting_type"] == ShootingType.INDIRECT.value
    assert INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID in targeting_rule_ids
    assert INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID in targeting_rule_ids
    assert INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID in targeting_rule_ids


def test_shooting_target_candidate_cache_uses_full_weapon_profile_identity() -> None:
    catalog = _catalog_with_same_profile_id_target_cache_collision_weapons()
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        catalog=catalog,
        game_id="phase14-profile-cache-key-regression",
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    type_request = _decision_request(
        _submit_result(
            lifecycle,
            request=selection_request,
            option_id=units["intercessor-1"].unit_instance_id,
            result_id="phase14-profile-cache-select-unit",
        )
    )

    assert {option.option_id for option in type_request.options} == {ShootingType.NORMAL.value}

    declaration_request = _decision_request(
        _submit_result(
            lifecycle,
            request=type_request,
            option_id=ShootingType.NORMAL.value,
            result_id="phase14-profile-cache-select-normal",
        )
    )
    request_payload = cast(dict[str, object], declaration_request.payload)
    proposal_request = cast(dict[str, object], request_payload["proposal_request"])
    weapons = cast(list[dict[str, object]], proposal_request["available_weapons"])
    target_candidates = cast(list[dict[str, object]], proposal_request["target_candidates"])
    target_unit_id = units["enemy"].unit_instance_id
    first_model_id = units["intercessor-1"].own_models[0].model_instance_id
    first_model_weapons = [
        weapon for weapon in weapons if weapon["model_instance_id"] == first_model_id
    ]

    assert {weapon["wargear_id"] for weapon in first_model_weapons} == {
        "phase14-cache-long-rifle",
        "phase14-cache-short-mortar",
    }
    assert {weapon["weapon_profile_id"] for weapon in first_model_weapons} == {"default"}
    long_weapon = next(
        weapon
        for weapon in first_model_weapons
        if weapon["wargear_id"] == "phase14-cache-long-rifle"
    )
    short_weapon = next(
        weapon
        for weapon in first_model_weapons
        if weapon["wargear_id"] == "phase14-cache-short-mortar"
    )
    assert (
        cast(WeaponProfilePayload, long_weapon["weapon_profile"])["range_profile"][
            "distance_inches"
        ]
        == 36
    )
    assert (
        cast(WeaponProfilePayload, short_weapon["weapon_profile"])["range_profile"][
            "distance_inches"
        ]
        == 6
    )

    same_profile_candidates = [
        candidate
        for candidate in target_candidates
        if candidate["weapon_profile_id"] == "default"
        and candidate["target_unit_instance_id"] == target_unit_id
    ]
    legal_candidates = [
        candidate for candidate in same_profile_candidates if candidate["is_legal"] is True
    ]
    illegal_candidates = [
        candidate for candidate in same_profile_candidates if candidate["is_legal"] is False
    ]
    assert len(legal_candidates) == len(units["intercessor-1"].own_models)
    assert len(illegal_candidates) == len(units["intercessor-1"].own_models)
    assert {candidate["violation_code"] for candidate in illegal_candidates} == {
        ShootingTargetViolationCode.OUT_OF_RANGE.value
    }

    invalid_short_proposal = _proposal_from_declarations(
        request=declaration_request,
        declarations=(
            WeaponDeclaration.from_payload(
                _weapon_payload_to_declaration_payload(
                    weapon=short_weapon,
                    target_unit_id=target_unit_id,
                )
            ),
        ),
    )
    before_records = len(lifecycle.decision_controller.records)

    invalid_status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=invalid_short_proposal.to_payload(),
        result_id="phase14-profile-cache-invalid-short",
    )
    invalid_validation = cast(
        dict[str, object],
        cast(dict[str, object], invalid_status.payload)["proposal_validation"],
    )
    invalid_violation = cast(list[dict[str, object]], invalid_validation["violations"])[0]

    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert invalid_violation["violation_code"] == "target_out_of_range"
    assert len(lifecycle.decision_controller.records) == before_records
    assert lifecycle.decision_controller.queue.pending_requests == (declaration_request,)


def test_phase14f_select_shooting_type_rejects_drift_before_mutation() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    unit_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    type_request = _decision_request(
        _submit_result(
            lifecycle,
            request=unit_request,
            option_id=units["intercessor-1"].unit_instance_id,
            result_id="phase14f-drift-select-unit",
        )
    )
    before_records = len(lifecycle.decision_controller.records)
    state.record_advanced_unit_state(
        _advanced_unit_state(units["intercessor-1"].unit_instance_id, can_shoot=False)
    )

    status = _submit_result(
        lifecycle,
        request=type_request,
        option_id=ShootingType.NORMAL.value,
        result_id="phase14f-drift-select-normal",
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert cast(dict[str, object], status.payload)["invalid_reason"] == (
        "shooting_type_option_drift"
    )
    assert len(lifecycle.decision_controller.records) == before_records
    assert lifecycle.decision_controller.queue.pending_requests == (type_request,)


def test_phase14f_select_shooting_type_rejects_wrong_actor_and_option_before_mutation() -> None:
    wrong_actor_lifecycle, wrong_actor_units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",)
    )
    wrong_actor_unit_request = _decision_request(
        wrong_actor_lifecycle.advance_until_decision_or_terminal()
    )
    wrong_actor_type_request = _decision_request(
        _submit_result(
            wrong_actor_lifecycle,
            request=wrong_actor_unit_request,
            option_id=wrong_actor_units["intercessor-1"].unit_instance_id,
            result_id="phase14f-wrong-actor-select-unit",
        )
    )
    wrong_actor_option = wrong_actor_type_request.options[0]
    wrong_actor_records = len(wrong_actor_lifecycle.decision_controller.records)

    with pytest.raises(DecisionError, match="actor_id"):
        wrong_actor_lifecycle.submit_decision(
            DecisionResult(
                result_id="phase14f-wrong-actor-select-type",
                request_id=wrong_actor_type_request.request_id,
                decision_type=wrong_actor_type_request.decision_type,
                actor_id="player-b",
                selected_option_id=wrong_actor_option.option_id,
                payload=wrong_actor_option.payload,
            )
        )
    assert len(wrong_actor_lifecycle.decision_controller.records) == wrong_actor_records
    assert wrong_actor_lifecycle.decision_controller.queue.pending_requests == (
        wrong_actor_type_request,
    )

    wrong_option_lifecycle, wrong_option_units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",)
    )
    wrong_option_unit_request = _decision_request(
        wrong_option_lifecycle.advance_until_decision_or_terminal()
    )
    wrong_option_type_request = _decision_request(
        _submit_result(
            wrong_option_lifecycle,
            request=wrong_option_unit_request,
            option_id=wrong_option_units["intercessor-1"].unit_instance_id,
            result_id="phase14f-wrong-option-select-unit",
        )
    )
    wrong_option_records = len(wrong_option_lifecycle.decision_controller.records)

    with pytest.raises(DecisionError):
        wrong_option_lifecycle.submit_decision(
            DecisionResult(
                result_id="phase14f-wrong-option-select-type",
                request_id=wrong_option_type_request.request_id,
                decision_type=wrong_option_type_request.decision_type,
                actor_id=wrong_option_type_request.actor_id,
                selected_option_id=ShootingType.INDIRECT.value,
                payload={"submission_kind": SELECT_SHOOTING_TYPE_DECISION_TYPE},
            )
        )
    assert len(wrong_option_lifecycle.decision_controller.records) == wrong_option_records
    assert wrong_option_lifecycle.decision_controller.queue.pending_requests == (
        wrong_option_type_request,
    )


def test_phase13c_random_attacks_resolve_when_declaration_is_accepted() -> None:
    base_profile = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id=None,
    )
    random_attacks_profile = replace(
        base_profile,
        profile_id="phase13c-random-attacks-bolt-rifle",
        attack_profile=AttackProfile.dice(DiceExpression(quantity=1, sides=3)),
    )
    catalog = _catalog_with_extra_bolt_profile(random_attacks_profile)
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        catalog=catalog,
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection_request,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        selection_result_id="phase13c-random-attacks-select",
    )
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
        weapon_profile_id=random_attacks_profile.profile_id,
    )

    lifecycle.submit_decision(
        DecisionResult(
            result_id="phase13c-random-attacks-declare",
            request_id=declaration_request.request_id,
            decision_type=declaration_request.decision_type,
            actor_id=declaration_request.actor_id,
            selected_option_id="submit_parameterized_payload",
            payload=validate_json_value(proposal.to_payload()),
        )
    )

    accepted_event = next(
        record
        for record in lifecycle.decision_controller.event_log.records
        if record.event_type == "shooting_declaration_accepted"
    )
    accepted_payload = cast(dict[str, object], accepted_event.payload)
    pool_payload = cast(list[dict[str, object]], accepted_payload["attack_pools"])[0]
    random_events = [
        record
        for record in lifecycle.decision_controller.event_log.records
        if record.event_type == "random_characteristic_rolled"
    ]
    assert pool_payload["weapon_profile_id"] == random_attacks_profile.profile_id
    assert len(random_events) == 1
    event_payload = cast(dict[str, object], random_events[0].payload)
    assert event_payload["characteristic"] == "attacks"
    assert event_payload["value"] == pool_payload["attacks"]


def test_phase13d_declaration_applies_rapid_blast_melta_and_heavy_modifiers() -> None:
    base_profile = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id="core-bolt-rifle:standard",
    )
    modifier_profile = replace(
        base_profile,
        profile_id="phase13d-modifier-rifle",
        name="Phase 13D modifier rifle",
        keywords=(
            WeaponKeyword.BLAST,
            WeaponKeyword.HEAVY,
            WeaponKeyword.MELTA,
            WeaponKeyword.RAPID_FIRE,
        ),
        abilities=(
            AbilityDescriptor.heavy(),
            AbilityDescriptor.melta(2),
            AbilityDescriptor.rapid_fire(1),
        ),
    )
    catalog = _catalog_with_extra_bolt_profile(modifier_profile)
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_pose=Pose.at(19.0, 35.0),
        catalog=catalog,
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection_request,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        selection_result_id="phase13d-select-modifier-rifle",
    )
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
        weapon_profile_id=modifier_profile.profile_id,
    )

    _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=proposal.to_payload(),
        result_id="phase13d-declare-modifier-rifle",
    )

    accepted_payload = _last_event_payload(lifecycle, "shooting_declaration_accepted")
    pool_payload = cast(list[dict[str, object]], accepted_payload["attack_pools"])[0]
    targeting_rule_ids = cast(list[str], pool_payload["targeting_rule_ids"])
    assert pool_payload["attacks"] == 4
    assert pool_payload["hit_roll_modifier"] == 1
    assert f"{RAPID_FIRE_RULE_ID}:1" in targeting_rule_ids
    assert f"{BLAST_RULE_ID}:1" in targeting_rule_ids
    assert f"{MELTA_RULE_ID}:2" in targeting_rule_ids
    assert HEAVY_RULE_ID in targeting_rule_ids


def test_phase13d_advanced_unit_allowed_to_shoot_does_not_gain_heavy_modifier() -> None:
    base_profile = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id="core-bolt-rifle:standard",
    )
    assault_heavy_profile = replace(
        base_profile,
        profile_id="phase13d-assault-heavy-rifle",
        name="Phase 13D Assault Heavy rifle",
        keywords=(WeaponKeyword.ASSAULT, WeaponKeyword.HEAVY),
        abilities=(AbilityDescriptor.heavy(),),
    )
    catalog = _catalog_with_extra_bolt_profile(assault_heavy_profile)
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        catalog=catalog,
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    state.record_advanced_unit_state(
        _advanced_unit_state(attacker.unit_instance_id, can_shoot=True)
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection_request,
        unit_instance_id=attacker.unit_instance_id,
        selection_result_id="phase13d-select-advanced-assault-heavy",
        shooting_type=ShootingType.ASSAULT,
    )
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
        weapon_profile_id=assault_heavy_profile.profile_id,
    )

    _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=proposal.to_payload(),
        result_id="phase13d-declare-advanced-assault-heavy",
    )

    accepted_payload = _last_event_payload(lifecycle, "shooting_declaration_accepted")
    pool_payload = cast(list[dict[str, object]], accepted_payload["attack_pools"])[0]
    targeting_rule_ids = cast(list[str], pool_payload["targeting_rule_ids"])
    assert pool_payload["weapon_profile_id"] == assault_heavy_profile.profile_id
    assert pool_payload["hit_roll_modifier"] == 0
    assert HEAVY_RULE_ID not in targeting_rule_ids


def test_phase13d_heavy_applies_after_small_move_but_not_after_more_than_three_inches() -> None:
    base_profile = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id="core-bolt-rifle:standard",
    )
    heavy_profile = replace(
        base_profile,
        profile_id="phase13d-small-move-heavy-rifle",
        name="Phase 13D small move Heavy rifle",
        keywords=(WeaponKeyword.HEAVY,),
        abilities=(AbilityDescriptor.heavy(),),
    )

    for moved_inches, expected_modifier in ((3.0, 1), (3.1, 0)):
        moved_id = str(moved_inches).replace(".", "-")
        catalog = _catalog_with_extra_bolt_profile(heavy_profile)
        lifecycle, units = _shooting_lifecycle(
            alpha_unit_ids=("intercessor-1",),
            game_id=f"phase13d-heavy-moved-{moved_id}",
            catalog=catalog,
        )
        state = _state(lifecycle)
        attacker = units["intercessor-1"]
        state.movement_phase_state = MovementPhaseState(
            battle_round=1,
            active_player_id="player-a",
            selected_unit_ids=(attacker.unit_instance_id,),
            moved_unit_ids=(attacker.unit_instance_id,),
            movement_distance_records=(
                MovementDistanceRecord(
                    unit_instance_id=attacker.unit_instance_id,
                    maximum_model_distance_inches=moved_inches,
                ),
            ),
        )
        selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
        declaration_request = _select_shooting_unit_and_type(
            lifecycle,
            selection_request=selection_request,
            unit_instance_id=attacker.unit_instance_id,
            selection_result_id=f"phase13d-select-heavy-moved-{moved_id}",
        )
        proposal = _proposal_from_request(
            request=declaration_request,
            target_unit_id=units["enemy"].unit_instance_id,
            weapon_profile_id=heavy_profile.profile_id,
        )

        _submit_payload(
            lifecycle,
            request=declaration_request,
            payload=proposal.to_payload(),
            result_id=f"phase13d-declare-heavy-moved-{moved_id}",
        )

        accepted_payload = _last_event_payload(lifecycle, "shooting_declaration_accepted")
        pool_payload = cast(list[dict[str, object]], accepted_payload["attack_pools"])[0]
        targeting_rule_ids = cast(list[str], pool_payload["targeting_rule_ids"])
        assert pool_payload["hit_roll_modifier"] == expected_modifier
        assert (HEAVY_RULE_ID in targeting_rule_ids) is (expected_modifier == 1)


def test_phase13d_heavy_does_not_apply_to_out_of_phase_shooting() -> None:
    base_profile = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id="core-bolt-rifle:standard",
    )
    heavy_profile = replace(
        base_profile,
        profile_id="phase13d-out-of-phase-heavy-rifle",
        name="Phase 13D out-of-phase Heavy rifle",
        keywords=(WeaponKeyword.HEAVY,),
        abilities=(AbilityDescriptor.heavy(),),
    )
    catalog = _catalog_with_extra_bolt_profile(heavy_profile)
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        catalog=catalog,
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.active_player_id = "player-b"
    declaration_request = _decision_request(
        request_out_of_phase_shooting_declaration(
            state=state,
            decisions=lifecycle.decision_controller,
            ruleset_descriptor=_ruleset(),
            army_catalog=catalog,
            player_id="player-a",
            unit_instance_id=attacker.unit_instance_id,
            parent_phase=BattlePhase.MOVEMENT,
            source_rule_id=FIRE_OVERWATCH_RULE_ID,
            source_decision_request_id="phase13d-heavy-fire-overwatch-request",
            source_decision_result_id="phase13d-heavy-fire-overwatch-result",
            source_context={
                "triggering_enemy_unit_instance_id": defender.unit_instance_id,
            },
            target_unit_ids=(defender.unit_instance_id,),
        )
    )
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=defender.unit_instance_id,
        weapon_profile_id=heavy_profile.profile_id,
    )

    _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=proposal.to_payload(),
        result_id="phase13d-declare-out-of-phase-heavy",
    )

    accepted_payload = _last_event_payload(lifecycle, "out_of_phase_shooting_declaration_accepted")
    pool_payload = cast(list[dict[str, object]], accepted_payload["attack_pools"])[0]
    targeting_rule_ids = cast(list[str], pool_payload["targeting_rule_ids"])
    assert pool_payload["hit_roll_modifier"] == 0
    assert HEAVY_RULE_ID not in targeting_rule_ids
    assert FIRE_OVERWATCH_RULE_ID in targeting_rule_ids


def test_out_of_phase_shooting_declaration_records_ranged_attack_history() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.active_player_id = "player-b"
    declaration_request = _decision_request(
        request_out_of_phase_shooting_declaration(
            state=state,
            decisions=lifecycle.decision_controller,
            ruleset_descriptor=_ruleset(),
            army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
            player_id="player-a",
            unit_instance_id=attacker.unit_instance_id,
            parent_phase=BattlePhase.MOVEMENT,
            source_rule_id=FIRE_OVERWATCH_RULE_ID,
            source_decision_request_id="phase13b-history-fire-overwatch-request",
            source_decision_result_id="phase13b-history-fire-overwatch-result",
            source_context={
                "triggering_enemy_unit_instance_id": defender.unit_instance_id,
            },
            target_unit_ids=(defender.unit_instance_id,),
        )
    )
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=defender.unit_instance_id,
    )

    _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=proposal.to_payload(),
        result_id="phase13b-declare-out-of-phase-history",
    )

    assert len(state.ranged_attack_history_records) == 1
    record = state.ranged_attack_history_records[0]
    assert record.player_id == "player-a"
    assert record.unit_instance_id == attacker.unit_instance_id
    assert record.battle_round == 1
    assert record.active_player_id == "player-b"
    assert record.phase is BattlePhase.MOVEMENT
    assert record.request_id == declaration_request.request_id
    assert record.result_id == "phase13b-declare-out-of-phase-history"
    assert state.unit_made_ranged_attacks_current_or_previous_turn(
        unit_instance_id=attacker.unit_instance_id
    )

    accepted_payload = _last_event_payload(lifecycle, "out_of_phase_shooting_declaration_accepted")
    assert accepted_payload["ranged_attack_history_record"] == record.to_payload()


def test_phase13d_heavy_does_not_apply_to_unit_set_up_this_turn() -> None:
    base_profile = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id="core-bolt-rifle:standard",
    )
    heavy_profile = replace(
        base_profile,
        profile_id="phase13d-set-up-heavy-rifle",
        name="Phase 13D set up Heavy rifle",
        keywords=(WeaponKeyword.HEAVY,),
        abilities=(AbilityDescriptor.heavy(),),
    )
    catalog = _catalog_with_extra_bolt_profile(heavy_profile)
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        catalog=catalog,
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    arrived_reserve_state = ReserveState.declared_before_battle(
        player_id="player-a",
        unit_instance_id=attacker.unit_instance_id,
        reserve_kind=ReserveKind.RESERVES,
    ).mark_arrived(
        battle_round=1,
        phase=BattlePhase.MOVEMENT,
        large_model_exception_used=False,
        post_arrival_restrictions=(),
    )
    state.record_reserve_state(arrived_reserve_state)
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection_request,
        unit_instance_id=attacker.unit_instance_id,
        selection_result_id="phase13d-select-set-up-heavy",
    )
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
        weapon_profile_id=heavy_profile.profile_id,
    )

    _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=proposal.to_payload(),
        result_id="phase13d-declare-set-up-heavy",
    )

    accepted_payload = _last_event_payload(lifecycle, "shooting_declaration_accepted")
    pool_payload = cast(list[dict[str, object]], accepted_payload["attack_pools"])[0]
    targeting_rule_ids = cast(list[str], pool_payload["targeting_rule_ids"])
    assert pool_payload["hit_roll_modifier"] == 0
    assert HEAVY_RULE_ID not in targeting_rule_ids


def test_phase13d_heavy_does_not_apply_to_disembarked_unit_set_up_this_turn() -> None:
    base_profile = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id="core-bolt-rifle:standard",
    )
    heavy_profile = replace(
        base_profile,
        profile_id="phase13d-disembarked-heavy-rifle",
        name="Phase 13D disembarked Heavy rifle",
        keywords=(WeaponKeyword.HEAVY,),
        abilities=(AbilityDescriptor.heavy(),),
    )
    catalog = _catalog_with_extra_bolt_profile(heavy_profile)
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        catalog=catalog,
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    state.record_disembarked_unit_state(
        DisembarkedUnitState.for_mode(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=attacker.unit_instance_id,
            transport_unit_instance_id="army-alpha:transport-unit",
            disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
            transport_movement_status=TransportMovementStatus.REMAIN_STATIONARY,
        )
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection_request,
        unit_instance_id=attacker.unit_instance_id,
        selection_result_id="phase13d-select-disembarked-heavy",
    )
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
        weapon_profile_id=heavy_profile.profile_id,
    )

    _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=proposal.to_payload(),
        result_id="phase13d-declare-disembarked-heavy",
    )

    accepted_payload = _last_event_payload(lifecycle, "shooting_declaration_accepted")
    pool_payload = cast(list[dict[str, object]], accepted_payload["attack_pools"])[0]
    targeting_rule_ids = cast(list[str], pool_payload["targeting_rule_ids"])
    assert pool_payload["hit_roll_modifier"] == 0
    assert HEAVY_RULE_ID not in targeting_rule_ids


def test_phase13d_heavy_does_not_apply_to_engaged_unit() -> None:
    base_profile = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id="core-bolt-rifle:standard",
    )
    heavy_pistol_profile = replace(
        base_profile,
        profile_id="phase13d-engaged-heavy-pistol",
        name="Phase 13D engaged Heavy pistol",
        keywords=(WeaponKeyword.HEAVY, WeaponKeyword.PISTOL),
        abilities=(AbilityDescriptor.heavy(),),
    )
    catalog = _catalog_with_extra_bolt_profile(heavy_pistol_profile)
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_pose=Pose.at(11.0, 35.0),
        catalog=catalog,
    )
    attacker = units["intercessor-1"]
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection_request,
        unit_instance_id=attacker.unit_instance_id,
        selection_result_id="phase13d-select-engaged-heavy",
        shooting_type=ShootingType.CLOSE_QUARTERS,
    )
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
        weapon_profile_id=heavy_pistol_profile.profile_id,
    )

    _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=proposal.to_payload(),
        result_id="phase13d-declare-engaged-heavy",
    )

    accepted_payload = _last_event_payload(lifecycle, "shooting_declaration_accepted")
    pool_payload = cast(list[dict[str, object]], accepted_payload["attack_pools"])[0]
    targeting_rule_ids = cast(list[str], pool_payload["targeting_rule_ids"])
    assert pool_payload["hit_roll_modifier"] == 0
    assert HEAVY_RULE_ID not in targeting_rule_ids


def test_phase13d_torrent_anti_and_devastating_wounds_are_attack_sequence_effects() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase13d-torrent-anti-devastating",
        keywords=(WeaponKeyword.DEVASTATING_WOUNDS, WeaponKeyword.TORRENT),
        abilities=(
            AbilityDescriptor.anti_keyword("Infantry", 4),
            AbilityDescriptor.devastating_wounds(),
        ),
    )
    attack_context_id = "phase13d-torrent:pool-001:attack-001"
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    dice_manager = DiceRollManager(
        "phase13d-torrent",
        event_log=lifecycle.decision_controller.event_log,
        injected_results=(
            _fixed_roll_result(
                roll_id="phase13d-torrent-wound",
                spec=wound_spec,
                value=4,
            ),
        ),
    )
    sequence = AttackSequence.start(
        sequence_id="phase13d-torrent",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=dice_manager,
    )

    events = _event_payloads(lifecycle, "attack_sequence_step")
    hit_payload = _attack_step_payload(events, AttackSequenceStep.HIT)
    wound_payload = _attack_step_payload(events, AttackSequenceStep.WOUND)
    damage_payload = _attack_step_payload(events, AttackSequenceStep.DAMAGE)
    assert remaining_sequence is None
    assert status is None
    assert allocated_ids == ()
    assert cast(dict[str, object], hit_payload["payload"])["skipped"] is True
    assert cast(dict[str, object], wound_payload["payload"])["critical_threshold"] == 4
    assert cast(dict[str, object], wound_payload["payload"])["critical"] is True
    assert not any(event["step"] == AttackSequenceStep.ALLOCATE.value for event in events)
    assert not any(event["step"] == AttackSequenceStep.SAVE.value for event in events)
    assert cast(dict[str, object], damage_payload["payload"])["saving_throw"] is None
    deferred_payload = cast(dict[str, object], damage_payload["payload"])["deferred_mortal_wounds"]
    assert cast(dict[str, object], deferred_payload)["mortal_wounds"] == 1
    applied_payload = _last_event_payload(lifecycle, "devastating_wounds_mortal_wounds_applied")
    application = cast(dict[str, object], applied_payload["mortal_wound_application"])
    applications = cast(list[dict[str, object]], application["applications"])
    assert applied_payload["mortal_wounds"] == 1
    assert applications[0]["model_instance_id"] == defender_model.model_instance_id
    assert applications[0]["damage_kind"] == DamageKind.MORTAL.value


def test_phase18b_command_reroll_window_opens_after_shooting_hit_roll() -> None:
    _lifecycle, attacker, _remaining, _allocated, status = (
        _phase18b_shooting_hit_command_reroll_status()
    )

    _assert_command_reroll_request(
        status,
        actor_id="player-a",
        phase_body_status="attack_hit_command_reroll_pending",
        roll_type="attack_sequence.hit",
        affected_unit_instance_id=attacker.unit_instance_id,
    )


def test_phase18b_command_reroll_use_spends_cp_once_and_resumes_shooting_hit_roll() -> None:
    lifecycle, attacker, remaining, allocated, status = (
        _phase18b_shooting_hit_command_reroll_status()
    )
    state = _state(lifecycle)
    request = _assert_command_reroll_request(
        status,
        actor_id="player-a",
        phase_body_status="attack_hit_command_reroll_pending",
        roll_type="attack_sequence.hit",
        affected_unit_instance_id=attacker.unit_instance_id,
    )
    assert remaining is not None
    option_id = _command_reroll_use_option_id(request)
    trigger_payload = cast(
        dict[str, object],
        cast(dict[str, object], cast(dict[str, object], request.payload)["stratagem_context"])[
            "trigger_payload"
        ],
    )
    dice_roll_state_payload = cast(dict[str, object], trigger_payload["dice_roll_state"])
    original_result_payload = cast(dict[str, object], dice_roll_state_payload["original_result"])
    original_roll_id = cast(str, original_result_payload["roll_id"])
    original_hit_spec_payload = cast(dict[str, object], original_result_payload["spec"])
    assert len(_dice_rolled_payloads_for_spec(lifecycle, original_hit_spec_payload)) == 1
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=remaining.attack_pools,
        attack_sequence=remaining,
        allocated_model_ids_this_phase=allocated,
    )

    accepted = lifecycle.submit_decision(
        DecisionResult.for_request(
            request=request,
            selected_option_id=option_id,
            result_id="phase18b-use-command-reroll-hit",
        )
    )

    assert accepted.status_kind is not LifecycleStatusKind.INVALID
    spend_payloads = _event_payloads(lifecycle, "command_points_spent")
    assert len(spend_payloads) == 1
    assert spend_payloads[0]["player_id"] == "player-a"
    assert spend_payloads[0]["requested_amount"] == 1
    assert spend_payloads[0]["applied_amount"] == 1
    resolved_payloads = _event_payloads(lifecycle, "command_reroll_resolved")
    assert len(resolved_payloads) == 1
    updated_state = DiceRollState.from_payload(
        cast(DiceRollStatePayload, resolved_payloads[0]["updated_roll_state"])
    )
    assert updated_state.original_result.roll_id == original_roll_id
    assert len(updated_state.rerolls) == 1
    assert len(_dice_rolled_payloads_for_spec(lifecycle, original_hit_spec_payload)) == 1
    hit_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.HIT,
    )
    resolved_hit = cast(dict[str, object], hit_payload["payload"])
    assert resolved_hit["unmodified_roll"] == updated_state.current_total
    assert cast(dict[str, object], resolved_hit["roll_state"]) == updated_state.to_payload()


def test_phase18b_command_reroll_rejects_stale_shooting_hit_opportunity() -> None:
    lifecycle, attacker, _remaining, _allocated, status = (
        _phase18b_shooting_hit_command_reroll_status()
    )
    request = _assert_command_reroll_request(
        status,
        actor_id="player-a",
        phase_body_status="attack_hit_command_reroll_pending",
        roll_type="attack_sequence.hit",
        affected_unit_instance_id=attacker.unit_instance_id,
    )
    option_id = _command_reroll_use_option_id(request)
    lifecycle.decision_controller.event_log.append(
        "phase18b_unrelated_state_advanced",
        {"reason": "stale Command Re-roll opportunity regression"},
    )

    invalid = lifecycle.submit_decision(
        DecisionResult.for_request(
            request=request,
            selected_option_id=option_id,
            result_id="phase18b-stale-command-reroll-opportunity",
        )
    )

    assert invalid.status_kind is LifecycleStatusKind.INVALID
    payload = cast(dict[str, object], invalid.payload)
    assert payload["invalid_reason"] == "stale_opportunity_state_hash"
    assert lifecycle.decision_controller.queue.pending_requests == (request,)


def test_phase18b_command_reroll_rejects_wrong_opportunity_window_id() -> None:
    lifecycle, attacker, _remaining, _allocated, status = (
        _phase18b_shooting_hit_command_reroll_status()
    )
    request = _assert_command_reroll_request(
        status,
        actor_id="player-a",
        phase_body_status="attack_hit_command_reroll_pending",
        roll_type="attack_sequence.hit",
        affected_unit_instance_id=attacker.unit_instance_id,
    )
    option_id = _command_reroll_use_option_id(request)
    option_payload = cast(dict[str, object], request.option_by_id(option_id).payload)
    opportunity_submission = dict(cast(dict[str, object], option_payload["opportunity_submission"]))
    opportunity_submission["window_id"] = "phase18b-wrong-command-reroll-window"
    tampered_payload = dict(option_payload)
    tampered_payload["opportunity_submission"] = opportunity_submission

    invalid = lifecycle.submit_decision(
        DecisionResult(
            request_id=request.request_id,
            result_id="phase18b-wrong-command-reroll-window",
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=option_id,
            payload=cast(JsonValue, tampered_payload),
        )
    )

    assert invalid.status_kind is LifecycleStatusKind.INVALID
    payload = cast(dict[str, object], invalid.payload)
    assert payload["invalid_reason"] == "opportunity_window_id_mismatch"
    assert lifecycle.decision_controller.queue.pending_requests == (request,)


def test_phase18b_command_reroll_decline_suppresses_same_shooting_hit_opportunity() -> None:
    lifecycle, attacker, remaining, allocated, status = (
        _phase18b_shooting_hit_command_reroll_status()
    )
    request = _assert_command_reroll_request(
        status,
        actor_id="player-a",
        phase_body_status="attack_hit_command_reroll_pending",
        roll_type="attack_sequence.hit",
        affected_unit_instance_id=attacker.unit_instance_id,
    )
    decline = DecisionResult.for_request(
        request=request,
        selected_option_id="decline_stratagem_window",
        result_id="phase18b-decline-command-reroll-hit",
    )
    decline_status = lifecycle.submit_decision(decline)
    assert decline_status.status_kind is not LifecycleStatusKind.INVALID
    assert remaining is not None

    _next_remaining, _next_allocated, repeat_status = resolve_attack_sequence_until_blocked(
        state=_state(lifecycle),
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=remaining,
        already_allocated_model_ids=allocated,
        dice_manager=DiceRollManager(
            "phase18b-command-reroll-hit",
            event_log=lifecycle.decision_controller.event_log,
        ),
        stratagem_index=eleventh_edition_stratagem_index(),
    )

    if repeat_status is not None:
        repeat_request = _decision_request(repeat_status)
        assert repeat_request.decision_type != "use_stratagem"


def test_phase18b_command_reroll_window_opens_after_shooting_wound_roll() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    _grant_command_reroll_cp(state, player_id="player-a")
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase18b-command-reroll-wound",
    )
    sequence_id = "phase18b-command-reroll-wound"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-a",
        reroll_forbidden_rule_ids=(SNAP_SHOOTING_RULE_ID,),
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-a",
    )
    sequence = AttackSequence.start(
        sequence_id=sequence_id,
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            replace(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
                targeting_rule_ids=(SNAP_SHOOTING_RULE_ID,),
            ),
        ),
    )

    _remaining, _allocated, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id=f"{sequence_id}:hit", spec=hit_spec, value=6),
                _fixed_roll_result(roll_id=f"{sequence_id}:wound", spec=wound_spec, value=2),
            ),
        ),
        stratagem_index=eleventh_edition_stratagem_index(),
    )

    _assert_command_reroll_request(
        status,
        actor_id="player-a",
        phase_body_status="attack_wound_command_reroll_pending",
        roll_type="attack_sequence.wound",
        affected_unit_instance_id=attacker.unit_instance_id,
    )


def test_phase18b_command_reroll_decline_then_twin_linked_rerolls_wound_once() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    _grant_command_reroll_cp(state, player_id="player-a")
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase18b-command-reroll-twin-linked",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -6),
        keywords=(WeaponKeyword.TORRENT, WeaponKeyword.TWIN_LINKED),
    )
    sequence_id = "phase18b-command-reroll-twin-linked"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-a",
    )
    reroll_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Reroll selected dice for {wound_spec.reason}",
        roll_type="attack_sequence.wound.reroll",
        actor_id="player-a",
    )
    dice_manager = DiceRollManager(
        sequence_id,
        event_log=lifecycle.decision_controller.event_log,
        injected_results=(
            _fixed_roll_result(
                roll_id="phase18b-command-reroll-twin-linked-wound",
                spec=wound_spec,
                value=1,
            ),
            _fixed_roll_result(
                roll_id="phase18b-command-reroll-twin-linked-reroll",
                spec=reroll_spec,
                value=6,
            ),
        ),
    )
    sequence = AttackSequence.start(
        sequence_id=sequence_id,
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    remaining, allocated, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=dice_manager,
        stratagem_index=eleventh_edition_stratagem_index(),
    )
    request = _assert_command_reroll_request(
        status,
        actor_id="player-a",
        phase_body_status="attack_wound_command_reroll_pending",
        roll_type="attack_sequence.wound",
        affected_unit_instance_id=attacker.unit_instance_id,
    )
    decline = DecisionResult.for_request(
        request=request,
        selected_option_id="decline_stratagem_window",
        result_id="phase18b-decline-command-reroll-before-twin-linked",
    )
    decline_status = lifecycle.submit_decision(decline)
    assert decline_status.status_kind is not LifecycleStatusKind.INVALID
    assert remaining is not None

    completed, _allocated_after_resume, repeat_status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=remaining,
        already_allocated_model_ids=allocated,
        dice_manager=dice_manager,
        stratagem_index=eleventh_edition_stratagem_index(),
    )

    assert completed is None
    assert repeat_status is None
    reroll_payload = _last_event_payload(lifecycle, "weapon_ability_reroll_resolved")
    assert cast(dict[str, object], reroll_payload["wound_roll"])["unmodified_roll"] == 6
    assert len(_event_payloads(lifecycle, "weapon_ability_reroll_resolved")) == 1
    assert len(_event_payloads(lifecycle, STRATAGEM_WINDOW_DECLINED_EVENT_TYPE)) == 1
    command_reroll_requests = [
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "decision_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("decision_type") == "use_stratagem"
    ]
    assert len(command_reroll_requests) == 1


def test_phase18b_command_reroll_window_opens_after_shooting_save_roll() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    _grant_command_reroll_cp(state, player_id="player-b")
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase18b-command-reroll-save",
    )
    sequence_id = "phase18b-command-reroll-save"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-a",
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )
    sequence = AttackSequence.start(
        sequence_id=sequence_id,
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )

    _remaining, _allocated, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id=f"{sequence_id}:hit", spec=hit_spec, value=6),
                _fixed_roll_result(roll_id=f"{sequence_id}:wound", spec=wound_spec, value=6),
                _fixed_roll_result(roll_id=f"{sequence_id}:save", spec=save_spec, value=1),
            ),
        ),
        stratagem_index=eleventh_edition_stratagem_index(),
    )

    _assert_command_reroll_request(
        status,
        actor_id="player-b",
        phase_body_status="attack_save_command_reroll_pending",
        roll_type="attack_sequence.save.armour",
        affected_unit_instance_id=defender.unit_instance_id,
    )


def test_phase18b_command_reroll_window_opens_after_shooting_damage_roll() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    _grant_command_reroll_cp(state, player_id="player-a")
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase18b-command-reroll-damage",
        keywords=(WeaponKeyword.LETHAL_HITS,),
        abilities=(AbilityDescriptor.lethal_hits(),),
        damage_profile=DamageProfile.dice(DiceExpression(quantity=1, sides=3)),
    )
    sequence_id = "phase18b-command-reroll-damage"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-a",
        reroll_forbidden_rule_ids=(SNAP_SHOOTING_RULE_ID,),
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )
    damage_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=3),
        reason="Phase 13C random Damage roll",
        roll_type=f"random_characteristic.damage.per_attack.{attack_context_id}:damage",
        actor_id="player-a",
    )
    sequence = AttackSequence.start(
        sequence_id=sequence_id,
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            replace(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
                targeting_rule_ids=(SNAP_SHOOTING_RULE_ID,),
            ),
        ),
    )

    _remaining, _allocated, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id=f"{sequence_id}:hit", spec=hit_spec, value=6),
                _fixed_roll_result(roll_id=f"{sequence_id}:save", spec=save_spec, value=1),
                _fixed_roll_result(roll_id=f"{sequence_id}:damage", spec=damage_spec, value=2),
            ),
        ),
        stratagem_index=eleventh_edition_stratagem_index(),
    )

    _assert_command_reroll_request(
        status,
        actor_id="player-a",
        phase_body_status="attack_damage_command_reroll_pending",
        roll_type=f"random_characteristic.damage.per_attack.{attack_context_id}:damage",
        affected_unit_instance_id=attacker.unit_instance_id,
    )


def test_phase13d_deferred_devastating_mortal_wounds_route_feel_no_pain_choice() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    source_a = FeelNoPainSource(source_id="phase13d-dev-fnp-a", threshold=5)
    source_b = FeelNoPainSource(source_id="phase13d-dev-fnp-b", threshold=6)
    state.record_model_feel_no_pain_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(source_a, source_b),
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase13d-devastating-fnp-choice",
        keywords=(WeaponKeyword.DEVASTATING_WOUNDS, WeaponKeyword.TORRENT),
        abilities=(AbilityDescriptor.devastating_wounds(),),
    )
    attack_context_id = "phase13d-dev-fnp:pool-001:attack-001"
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    sequence = AttackSequence.start(
        sequence_id="phase13d-dev-fnp",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase13d-dev-fnp",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id="phase13d-dev-fnp-wound", spec=wound_spec, value=6),
            ),
        ),
    )
    request = _decision_request(cast(LifecycleStatus, status))

    assert remaining_sequence is not None
    assert allocated_ids == ()
    assert request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
    assert {option.option_id for option in request.options} == {
        source_a.source_id,
        source_b.source_id,
    }
    assert not _event_payloads(lifecycle, "devastating_wounds_mortal_wounds_applied")


def test_phase13d_deferred_devastating_mortal_wound_queue_survives_fnp_pause() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_specs=(
            ("enemy-a", "core-intercessor-like-infantry", "core-intercessor-like", 5),
            ("enemy-b", "core-intercessor-like-infantry", "core-intercessor-like", 5),
        ),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    target_a = units["enemy-a"]
    target_b = units["enemy-b"]
    source = FeelNoPainSource(source_id="phase13d-dev-queue-fnp", threshold=5)
    state.record_model_feel_no_pain_sources(
        model_instance_id=target_a.own_models[0].model_instance_id,
        sources=(source,),
        decline_allowed=True,
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase13d-dev-queue-profile",
        keywords=(WeaponKeyword.DEVASTATING_WOUNDS,),
        abilities=(AbilityDescriptor.devastating_wounds(),),
    )
    pool_a = _attack_pool_for_test(
        attacker=attacker,
        defender=target_a,
        weapon_profile=weapon_profile,
        attacks=1,
    )
    pool_b = _attack_pool_for_test(
        attacker=attacker,
        defender=target_b,
        weapon_profile=weapon_profile,
        attacks=1,
    )
    deferred_a = DeferredMortalWounds(
        source_rule_id="weapon-ability:devastating-wounds",
        target_unit_instance_id=target_a.unit_instance_id,
        attack_context_id="phase13d-dev-queue:pool-001:attack-001",
        mortal_wounds=1,
    )
    deferred_b = DeferredMortalWounds(
        source_rule_id="weapon-ability:devastating-wounds",
        target_unit_instance_id=target_b.unit_instance_id,
        attack_context_id="phase13d-dev-queue:pool-002:attack-001",
        mortal_wounds=1,
    )
    sequence = AttackSequence(
        sequence_id="phase13d-dev-queue",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(pool_a, pool_b),
        pool_index=2,
        deferred_mortal_wounds=(deferred_a, deferred_b),
    )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase13d-dev-queue",
            event_log=lifecycle.decision_controller.event_log,
        ),
    )
    request = _decision_request(cast(LifecycleStatus, status))

    assert remaining_sequence is not None
    assert allocated_ids == ()
    assert request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
    assert request.options[0].option_id == "decline"
    assert tuple(
        deferred.target_unit_instance_id for deferred in remaining_sequence.deferred_mortal_wounds
    ) == (target_b.unit_instance_id,)
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=remaining_sequence.attack_pools,
        attack_sequence=remaining_sequence,
        allocated_model_ids_this_phase=allocated_ids,
    )
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    restored_state = _state(restored)
    restored_shooting_state = restored_state.shooting_phase_state
    assert restored_shooting_state is not None
    restored_sequence = restored_shooting_state.attack_sequence
    assert restored_sequence is not None
    assert tuple(
        deferred.target_unit_instance_id for deferred in restored_sequence.deferred_mortal_wounds
    ) == (target_b.unit_instance_id,)
    assert len(restored.decision_controller.queue.pending_requests) == 1
    restored_request = restored.decision_controller.queue.pending_requests[0]

    restored.submit_decision(
        DecisionResult.for_request(
            result_id="phase13d-dev-queue-decline-fnp",
            request=restored_request,
            selected_option_id="decline",
        )
    )
    applied_events = _event_payloads(restored, "devastating_wounds_mortal_wounds_applied")
    applied_target_ids = {event["target_unit_instance_id"] for event in applied_events}

    assert target_a.unit_instance_id in applied_target_ids
    assert target_b.unit_instance_id in applied_target_ids
    assert _state(restored).shooting_phase_state is None


def test_phase13d_precision_allocation_can_select_visible_attached_character() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = _replace_enemy_with_attached_character_fixture(state=state, defender=units["enemy"])
    bodyguard_model = defender.own_models[0]
    character_model = defender.own_models[1]
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase13d-precision-rifle",
        keywords=(WeaponKeyword.PRECISION,),
    )
    sequence = AttackSequence.start(
        sequence_id="phase13d-precision",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=(
            f"Hit roll for {weapon_profile.profile_id} attack "
            "phase13d-precision:pool-001:attack-001"
        ),
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=(
            f"Wound roll for {weapon_profile.profile_id} attack "
            "phase13d-precision:pool-001:attack-001"
        ),
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase13d-precision",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id="phase13d-precision-hit", spec=hit_spec, value=6),
                _fixed_roll_result(roll_id="phase13d-precision-wound", spec=wound_spec, value=6),
            ),
        ),
    )
    request = _decision_request(cast(LifecycleStatus, status))

    assert remaining_sequence is not None
    assert request.decision_type == SELECT_PRECISION_ALLOCATION_DECISION_TYPE
    assert request.actor_id == "player-a"
    character_options = tuple(
        option
        for option in request.options
        if character_model.model_instance_id
        in cast(list[str], cast(dict[str, object], option.payload)["selected_model_ids"])
    )
    assert len(character_options) == 1
    character_group_id = character_options[0].option_id
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=remaining_sequence.attack_pools,
        attack_sequence=remaining_sequence,
        allocated_model_ids_this_phase=allocated_ids,
    )
    selected_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase13d-precision-select-character",
            request=request,
            selected_option_id=character_group_id,
        )
    )
    allocation_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.ALLOCATE,
    )
    allocation_step = cast(dict[str, object], allocation_payload["payload"])
    allocation_group = cast(dict[str, object], allocation_step["allocation_group"])
    allocation_context = cast(dict[str, object], allocation_step["allocation_context"])
    attacker_constraint = cast(dict[str, object], allocation_context["attacker_constraint"])
    save_step = cast(
        dict[str, object],
        _attack_step_payload(
            _event_payloads(lifecycle, "attack_sequence_step"),
            AttackSequenceStep.SAVE,
        )["payload"],
    )

    assert selected_status.status_kind in {
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.UNSUPPORTED,
    }
    assert allocation_group["group_id"] == character_group_id
    assert cast(list[str], allocation_group["model_ids"]) == [character_model.model_instance_id]
    assert save_step["allocated_model_id"] == character_model.model_instance_id
    assert attacker_constraint["attacker_selected_group_id"] == character_group_id
    assert attacker_constraint["can_allocate_protected_characters"] is True
    assert PRECISION_RULE_ID in cast(list[str], attacker_constraint["source_rule_ids"])
    assert bodyguard_model.model_instance_id != save_step["allocated_model_id"]


def test_phase13d_precision_decline_or_no_visible_character_uses_bodyguard_allocation() -> None:
    declined_lifecycle, declined_units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    declined_state = _state(declined_lifecycle)
    declined_attacker = declined_units["intercessor-1"]
    declined_defender = _replace_enemy_with_attached_character_fixture(
        state=declined_state,
        defender=declined_units["enemy"],
    )
    bodyguard_model = declined_defender.own_models[0]
    precision_profile = replace(
        _first_weapon_profile(declined_lifecycle, declined_attacker),
        profile_id="phase13d-precision-decline",
        keywords=(WeaponKeyword.PRECISION,),
    )
    request, remaining_sequence, allocated_ids = _precision_request_for_fixture(
        lifecycle=declined_lifecycle,
        attacker=declined_attacker,
        defender=declined_defender,
        weapon_profile=precision_profile,
        sequence_id="phase13d-precision-decline",
    )
    declined_state.shooting_phase_state = ShootingPhaseState(
        battle_round=declined_state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(declined_attacker.unit_instance_id,),
        shot_unit_ids=(declined_attacker.unit_instance_id,),
        attack_pools=remaining_sequence.attack_pools,
        attack_sequence=remaining_sequence,
        allocated_model_ids_this_phase=allocated_ids,
    )

    declined_lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase13d-precision-decline-result",
            request=request,
            selected_option_id="decline_precision",
        )
    )
    declined_allocation_payload = cast(
        dict[str, object],
        _attack_step_payload(
            _event_payloads(declined_lifecycle, "attack_sequence_step"),
            AttackSequenceStep.ALLOCATE,
        )["payload"],
    )
    declined_allocation_group = cast(
        dict[str, object],
        declined_allocation_payload["allocation_group"],
    )
    declined_save_step = cast(
        dict[str, object],
        _attack_step_payload(
            _event_payloads(declined_lifecycle, "attack_sequence_step"),
            AttackSequenceStep.SAVE,
        )["payload"],
    )

    assert bodyguard_model.model_instance_id in cast(
        list[str],
        declined_allocation_group["model_ids"],
    )
    assert declined_save_step["allocated_model_id"] == bodyguard_model.model_instance_id

    hidden_lifecycle, hidden_units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    hidden_state = _state(hidden_lifecycle)
    hidden_attacker = hidden_units["intercessor-1"]
    hidden_defender = _replace_enemy_with_attached_character_fixture(
        state=hidden_state,
        defender=hidden_units["enemy"],
    )
    hidden_bodyguard = hidden_defender.own_models[0]
    hidden_character = hidden_defender.own_models[1]
    hidden_sequence = AttackSequence.start(
        sequence_id="phase13d-precision-hidden-character",
        attacker_player_id="player-a",
        attacking_unit_instance_id=hidden_attacker.unit_instance_id,
        attack_pools=(
            RangedAttackPool(
                attacker_model_instance_id=hidden_attacker.own_models[0].model_instance_id,
                wargear_id=hidden_attacker.wargear_selections[0].wargear_ids[0],
                weapon_profile_id=precision_profile.profile_id,
                weapon_profile=precision_profile,
                target_unit_instance_id=hidden_defender.unit_instance_id,
                shooting_type=ShootingType.NORMAL,
                attacks=1,
                target_visible_model_ids=(hidden_bodyguard.model_instance_id,),
                target_in_range_model_ids=(
                    hidden_bodyguard.model_instance_id,
                    hidden_character.model_instance_id,
                ),
            ),
        ),
    )
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=(
            f"Hit roll for {precision_profile.profile_id} attack "
            "phase13d-precision-hidden-character:pool-001:attack-001"
        ),
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=(
            f"Wound roll for {precision_profile.profile_id} attack "
            "phase13d-precision-hidden-character:pool-001:attack-001"
        ),
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )

    hidden_remaining, _hidden_allocated_ids, hidden_status = resolve_attack_sequence_until_blocked(
        state=hidden_state,
        decisions=hidden_lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=hidden_sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase13d-precision-hidden-character",
            event_log=hidden_lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id="phase13d-precision-hidden-hit", spec=hit_spec, value=6),
                _fixed_roll_result(
                    roll_id="phase13d-precision-hidden-wound",
                    spec=wound_spec,
                    value=6,
                ),
            ),
        ),
    )
    hidden_allocation_payload = cast(
        dict[str, object],
        _attack_step_payload(
            _event_payloads(hidden_lifecycle, "attack_sequence_step"),
            AttackSequenceStep.ALLOCATE,
        )["payload"],
    )
    hidden_allocation_group = cast(
        dict[str, object],
        hidden_allocation_payload["allocation_group"],
    )
    hidden_save_step = cast(
        dict[str, object],
        _attack_step_payload(
            _event_payloads(hidden_lifecycle, "attack_sequence_step"),
            AttackSequenceStep.SAVE,
        )["payload"],
    )

    assert hidden_status is not None or hidden_remaining is None
    assert hidden_status is None or _decision_request(hidden_status).decision_type != (
        SELECT_PRECISION_ALLOCATION_DECISION_TYPE
    )
    assert hidden_bodyguard.model_instance_id in cast(
        list[str],
        hidden_allocation_group["model_ids"],
    )
    assert hidden_save_step["allocated_model_id"] == hidden_bodyguard.model_instance_id


def test_phase14e_precision_selection_persists_for_current_attack_pool() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = _replace_enemy_with_attached_character_fixture(state=state, defender=units["enemy"])
    character_model = defender.own_models[1]
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14e-precision-pool-rifle",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -10),
        keywords=(WeaponKeyword.PRECISION,),
    )
    sequence = AttackSequence.start(
        sequence_id="phase14e-precision-pool",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=2,
            ),
        ),
    )
    injected_results: list[DiceRollResult] = []
    for attack_number in range(1, 3):
        attack_context_id = f"phase14e-precision-pool:pool-001:attack-{attack_number:03d}"
        injected_results.extend(
            (
                _fixed_roll_result(
                    roll_id=f"phase14e-precision-pool-hit-{attack_number}",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}"
                        ),
                        roll_type="attack_sequence.hit",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"phase14e-precision-pool-wound-{attack_number}",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}"
                        ),
                        roll_type="attack_sequence.wound",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
            )
        )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14e-precision-pool",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=tuple(injected_results),
        ),
    )
    request = _decision_request(cast(LifecycleStatus, status))
    character_options = tuple(
        option
        for option in request.options
        if character_model.model_instance_id
        in cast(list[str], cast(dict[str, object], option.payload)["selected_model_ids"])
    )
    assert remaining_sequence is not None
    assert request.decision_type == SELECT_PRECISION_ALLOCATION_DECISION_TYPE
    assert len(character_options) == 1
    precision_character_group_id = character_options[0].option_id
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=remaining_sequence.attack_pools,
        attack_sequence=remaining_sequence,
        allocated_model_ids_this_phase=allocated_ids,
    )
    selected_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase14e-precision-pool-result",
            request=request,
            selected_option_id=precision_character_group_id,
        )
    )
    allocation_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.ALLOCATE,
    )
    allocation_step = cast(dict[str, object], allocation_payload["payload"])
    allocation_group = cast(dict[str, object], allocation_step["allocation_group"])
    allocation_context = cast(dict[str, object], allocation_step["allocation_context"])
    attacker_constraint = cast(dict[str, object], allocation_context["attacker_constraint"])
    save_payloads = [
        cast(dict[str, object], event["payload"])
        for event in _event_payloads(lifecycle, "attack_sequence_step")
        if event["step"] == "save"
    ]
    precision_requests = [
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "decision_requested"
        and cast(dict[str, object], event.payload)["decision_type"]
        == SELECT_PRECISION_ALLOCATION_DECISION_TYPE
    ]

    if selected_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION:
        assert _decision_request(selected_status).decision_type != (
            SELECT_PRECISION_ALLOCATION_DECISION_TYPE
        )
    assert allocation_group["group_id"] == precision_character_group_id
    assert {payload["allocated_model_id"] for payload in save_payloads} == {
        character_model.model_instance_id
    }
    assert attacker_constraint["attacker_selected_group_id"] == precision_character_group_id
    assert len(precision_requests) == 1


def test_phase14e_grouped_saves_roll_before_low_to_high_damage_allocation() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14e-grouped-save-bolt-rifle",
        damage_profile=DamageProfile.fixed(1),
        keywords=(),
        abilities=(),
    )
    sequence = AttackSequence.start(
        sequence_id="phase14e-grouped-saves",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=3,
            ),
        ),
    )
    injected_results: list[DiceRollResult] = []
    for attack_number in range(1, 4):
        attack_context_id = f"phase14e-grouped-saves:pool-001:attack-{attack_number:03d}"
        injected_results.append(
            _fixed_roll_result(
                roll_id=f"phase14e-grouped-hit-{attack_number}",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason=(f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}"),
                    roll_type="attack_sequence.hit",
                    actor_id="player-a",
                ),
                value=6,
            )
        )
        injected_results.append(
            _fixed_roll_result(
                roll_id=f"phase14e-grouped-wound-{attack_number}",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason=(
                        f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}"
                    ),
                    roll_type="attack_sequence.wound",
                    actor_id="player-a",
                ),
                value=6,
            )
        )
    for attack_number, save_value in ((1, 2), (2, 1), (3, 6)):
        attack_context_id = f"phase14e-grouped-saves:pool-001:attack-{attack_number:03d}"
        injected_results.append(
            _fixed_roll_result(
                roll_id=f"phase14e-grouped-save-{attack_number}",
                spec=saving_throw_roll_spec(
                    save_kind=SaveKind.ARMOUR,
                    player_id="player-b",
                    allocated_model_id=defender.own_models[0].model_instance_id,
                    attack_context_id=attack_context_id,
                ),
                value=save_value,
            )
        )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14e-grouped-saves",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=tuple(injected_results),
        ),
    )
    remaining_sequence, status = _continue_damage_model_choices(
        lifecycle,
        attack_sequence=remaining_sequence,
        allocated_ids=allocated_ids,
        status=status,
        result_id_prefix="phase14e-grouped-saves-model",
    )
    attack_events = _event_payloads(lifecycle, "attack_sequence_step")
    all_records = lifecycle.decision_controller.event_log.records
    save_roll_indexes = [
        index
        for index, record in enumerate(all_records)
        if record.event_type == "dice_rolled"
        and cast(
            str,
            cast(dict[str, object], cast(dict[str, object], record.payload)["spec"])["roll_type"],
        ).startswith("attack_sequence.save.")
    ]
    damage_record_indexes = [
        index
        for index, record in enumerate(all_records)
        if record.event_type == "attack_sequence_step"
        and cast(dict[str, object], record.payload)["step"] == "damage"
        and cast(
            dict[str, object],
            cast(dict[str, object], record.payload)["payload"],
        )["damage_application"]
        is not None
    ]
    save_context_ids = [
        event["attack_context_id"] for event in attack_events if event["step"] == "save"
    ]
    damage_context_ids = [
        event["attack_context_id"]
        for event in attack_events
        if event["step"] == "damage"
        and cast(dict[str, object], event["payload"])["damage_application"] is not None
    ]
    grouped_allocation = next(
        cast(dict[str, object], event["payload"])
        for event in attack_events
        if event["step"] == "allocate"
        and cast(dict[str, object], event["payload"]).get("grouped_save_before_allocation") is True
    )

    assert remaining_sequence is None
    assert status is not None
    assert max(save_roll_indexes) < min(damage_record_indexes)
    assert save_context_ids == [
        "phase14e-grouped-saves:pool-001:attack-002",
        "phase14e-grouped-saves:pool-001:attack-001",
        "phase14e-grouped-saves:pool-001:attack-003",
    ]
    assert damage_context_ids == [
        "phase14e-grouped-saves:pool-001:attack-002",
        "phase14e-grouped-saves:pool-001:attack-001",
    ]
    assert grouped_allocation["attack_context_ids"] == [
        "phase14e-grouped-saves:pool-001:attack-001",
        "phase14e-grouped-saves:pool-001:attack-002",
        "phase14e-grouped-saves:pool-001:attack-003",
    ]


def test_phase14k_grouped_damage_requests_defender_model_choice_inside_current_group() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    selected_model = defender.own_models[3]
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14k-current-group-model-choice",
        damage_profile=DamageProfile.fixed(1),
        keywords=(),
        abilities=(),
    )
    sequence = AttackSequence.start(
        sequence_id="phase14k-current-group-model-choice",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    attack_context_id = "phase14k-current-group-model-choice:pool-001:attack-001"
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender.own_models[0].model_instance_id,
        attack_context_id=attack_context_id,
    )
    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14k-current-group-model-choice",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14k-current-group-model-choice-hit",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}"
                        ),
                        roll_type="attack_sequence.hit",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14k-current-group-model-choice-wound",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}"
                        ),
                        roll_type="attack_sequence.wound",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14k-current-group-model-choice-save",
                    spec=save_spec,
                    value=1,
                ),
            ),
        ),
    )
    request = _decision_request(cast(LifecycleStatus, status))
    request_payload = cast(dict[str, object], request.payload)
    option_ids = {option.option_id for option in request.options}

    assert remaining_sequence is not None
    assert remaining_sequence.pending_grouped_damage is not None
    assert allocated_ids == ()
    assert request.decision_type == SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE
    assert request.actor_id == "player-b"
    assert option_ids == {model.model_instance_id for model in defender.own_models}
    assert request_payload["selection_kind"] == "damage_allocation_model"
    assert request_payload["legal_model_ids"] == [
        model.model_instance_id for model in defender.own_models
    ]
    assert all(
        cast(dict[str, object], event["payload"])["damage_application"] is None
        for event in _event_payloads(lifecycle, "attack_sequence_step")
        if event["step"] == "damage"
    )

    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        state.shooting_phase_state = ShootingPhaseState(
            battle_round=state.battle_round,
            active_player_id="player-a",
            selected_unit_ids=(attacker.unit_instance_id,),
            shot_unit_ids=(attacker.unit_instance_id,),
            attack_pools=remaining_sequence.attack_pools,
            attack_sequence=remaining_sequence,
            allocated_model_ids_this_phase=allocated_ids,
        )
    else:
        state.shooting_phase_state = shooting_state.with_attack_sequence_update(
            attack_sequence=remaining_sequence,
            allocated_model_ids_this_phase=allocated_ids,
        )
    selection_result = DecisionResult.for_request(
        result_id="phase14k-current-group-model-choice-select",
        request=request,
        selected_option_id=selected_model.model_instance_id,
    )
    decision = DamageAllocationModelDecision.from_result(
        request=request,
        result=selection_result,
    )
    final_status = lifecycle.submit_decision(selection_result)
    damage_payloads = [
        cast(dict[str, object], cast(dict[str, object], event["payload"])["damage_application"])
        for event in _event_payloads(lifecycle, "attack_sequence_step")
        if event["step"] == "damage"
        and cast(dict[str, object], event["payload"])["damage_application"] is not None
    ]
    save_payloads = [
        cast(dict[str, object], event["payload"])
        for event in _event_payloads(lifecycle, "attack_sequence_step")
        if event["step"] == "save"
    ]

    assert final_status.status_kind in {
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.UNSUPPORTED,
    }
    assert decision.selected_model_id == selected_model.model_instance_id
    assert damage_payloads[-1]["model_instance_id"] == selected_model.model_instance_id
    assert save_payloads[-1]["allocated_model_id"] == selected_model.model_instance_id


def test_phase14k_grouped_damage_auto_selects_only_wounded_model_in_current_group() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    wounded_model = replace(defender.own_models[2], wounds_remaining=1)
    defender = replace(
        defender,
        own_models=(
            *defender.own_models[:2],
            wounded_model,
            *defender.own_models[3:],
        ),
    )
    _replace_unit_instance_in_state(state=state, replacement=defender)
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14k-current-group-wounded-forced",
        damage_profile=DamageProfile.fixed(1),
        keywords=(),
        abilities=(),
    )
    sequence = AttackSequence.start(
        sequence_id="phase14k-current-group-wounded-forced",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    attack_context_id = "phase14k-current-group-wounded-forced:pool-001:attack-001"
    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14k-current-group-wounded-forced",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14k-current-group-wounded-forced-hit",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}"
                        ),
                        roll_type="attack_sequence.hit",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14k-current-group-wounded-forced-wound",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}"
                        ),
                        roll_type="attack_sequence.wound",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14k-current-group-wounded-forced-save",
                    spec=saving_throw_roll_spec(
                        save_kind=SaveKind.ARMOUR,
                        player_id="player-b",
                        allocated_model_id=wounded_model.model_instance_id,
                        attack_context_id=attack_context_id,
                    ),
                    value=1,
                ),
            ),
        ),
    )
    damage_payloads = [
        cast(dict[str, object], cast(dict[str, object], event["payload"])["damage_application"])
        for event in _event_payloads(lifecycle, "attack_sequence_step")
        if event["step"] == "damage"
        and cast(dict[str, object], event["payload"])["damage_application"] is not None
    ]
    model_choice_requests = [
        payload
        for payload in _event_payloads(lifecycle, "decision_requested")
        if payload["decision_type"] == SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE
    ]

    assert remaining_sequence is None
    assert status is None
    assert damage_payloads[-1]["model_instance_id"] == wounded_model.model_instance_id
    assert model_choice_requests == []


def test_phase14k_damage_model_choice_payload_round_trips_json_safe() -> None:
    lifecycle, request, _remaining_sequence, _allocated_ids, defender = (
        _damage_model_choice_lifecycle(sequence_id="phase14k-model-choice-round-trip")
    )
    selected_model = defender.own_models[1]
    request_round_trip = DecisionRequest.from_payload(request.to_payload())
    result = DecisionResult.for_request(
        result_id="phase14k-model-choice-round-trip-result",
        request=request_round_trip,
        selected_option_id=selected_model.model_instance_id,
    )
    result_round_trip = DecisionResult.from_payload(result.to_payload())
    decision = DamageAllocationModelDecision.from_result(
        request=request_round_trip,
        result=result_round_trip,
    )
    decision_payload_json = json.dumps(decision.to_payload(), sort_keys=True)

    assert request_round_trip == request
    assert result_round_trip == result
    assert decision.selected_model_id == selected_model.model_instance_id
    assert "object at 0x" not in decision_payload_json
    assert lifecycle.decision_controller.queue.peek_next() == request


def test_phase14k_damage_model_choice_malformed_payload_rejects_before_queue_pop() -> None:
    lifecycle, request, _remaining_sequence, _allocated_ids, defender = (
        _damage_model_choice_lifecycle(sequence_id="phase14k-model-choice-malformed")
    )
    bad_result = DecisionResult(
        result_id="phase14k-model-choice-malformed-result",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=defender.own_models[1].model_instance_id,
        payload={
            "submission_kind": SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
            "selected_model_id": defender.own_models[2].model_instance_id,
        },
    )
    before_records = lifecycle.decision_controller.records

    status = lifecycle.submit_decision(bad_result)

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert cast(dict[str, object], status.payload)["invalid_reason"] == (
        "invalid_damage_allocation_model_result"
    )
    assert cast(dict[str, object], status.payload)["field"] == "payload"
    assert lifecycle.decision_controller.queue.peek_next() == request
    assert lifecycle.decision_controller.records == before_records


def test_phase14k_damage_model_choice_stale_pending_damage_rejects_before_queue_pop() -> None:
    lifecycle, request, remaining_sequence, allocated_ids, defender = (
        _damage_model_choice_lifecycle(sequence_id="phase14k-model-choice-stale")
    )
    state = _state(lifecycle)
    shooting_state = state.shooting_phase_state
    assert shooting_state is not None
    state.shooting_phase_state = shooting_state.with_attack_sequence_update(
        attack_sequence=remaining_sequence.without_pending_grouped_damage(),
        allocated_model_ids_this_phase=allocated_ids,
    )
    result = DecisionResult.for_request(
        result_id="phase14k-model-choice-stale-result",
        request=request,
        selected_option_id=defender.own_models[1].model_instance_id,
    )
    before_records = lifecycle.decision_controller.records

    status = lifecycle.submit_decision(result)

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert cast(dict[str, object], status.payload)["invalid_reason"] == (
        "invalid_damage_allocation_model_result"
    )
    assert cast(dict[str, object], status.payload)["field"] == "pending_grouped_damage"
    assert lifecycle.decision_controller.queue.peek_next() == request
    assert lifecycle.decision_controller.records == before_records


def test_phase14k_damage_model_choice_dead_selected_model_rejects_before_queue_pop() -> None:
    lifecycle, request, _remaining_sequence, _allocated_ids, defender = (
        _damage_model_choice_lifecycle(sequence_id="phase14k-model-choice-dead-drift")
    )
    selected_model = defender.own_models[1]
    defender_after_drift = replace(
        defender,
        own_models=tuple(
            replace(model, wounds_remaining=0)
            if model.model_instance_id == selected_model.model_instance_id
            else model
            for model in defender.own_models
        ),
    )
    _replace_unit_instance_in_state(state=_state(lifecycle), replacement=defender_after_drift)

    _assert_stale_damage_model_choice_rejected_before_queue_pop(
        lifecycle=lifecycle,
        request=request,
        selected_model_id=selected_model.model_instance_id,
        result_id="phase14k-model-choice-dead-drift-result",
    )


def test_phase14k_damage_model_choice_wounded_priority_drift_rejects_before_queue_pop() -> None:
    lifecycle, request, _remaining_sequence, _allocated_ids, defender = (
        _damage_model_choice_lifecycle(sequence_id="phase14k-model-choice-wounded-drift")
    )
    selected_model = defender.own_models[1]
    wounded_model = defender.own_models[2]
    assert wounded_model.starting_wounds > 1
    defender_after_drift = replace(
        defender,
        own_models=tuple(
            replace(model, wounds_remaining=wounded_model.starting_wounds - 1)
            if model.model_instance_id == wounded_model.model_instance_id
            else model
            for model in defender.own_models
        ),
    )
    _replace_unit_instance_in_state(state=_state(lifecycle), replacement=defender_after_drift)

    _assert_stale_damage_model_choice_rejected_before_queue_pop(
        lifecycle=lifecycle,
        request=request,
        selected_model_id=selected_model.model_instance_id,
        result_id="phase14k-model-choice-wounded-drift-result",
    )


def test_phase14h_pooled_walk_recomputes_save_after_group_transition() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    first_model = replace(
        defender.own_models[0],
        wounds_remaining=1,
        characteristics=tuple(
            CharacteristicValue.from_raw(Characteristic.SAVE, 2)
            if value.characteristic is Characteristic.SAVE
            else value
            for value in defender.own_models[0].characteristics
        ),
    )
    later_models = tuple(
        replace(
            model,
            characteristics=tuple(
                CharacteristicValue.from_raw(Characteristic.SAVE, 4)
                if value.characteristic is Characteristic.SAVE
                else value
                for value in model.characteristics
            ),
        )
        for model in defender.own_models[1:]
    )
    defender = replace(defender, own_models=(first_model, *later_models))
    _replace_unit_instance_in_state(state=state, replacement=defender)
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14h-lazy-save-transition",
        damage_profile=DamageProfile.fixed(1),
        keywords=(),
        abilities=(),
    )
    sequence = AttackSequence.start(
        sequence_id="phase14h-lazy-save-transition",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=2,
            ),
        ),
    )
    injected_results: list[DiceRollResult] = []
    for attack_number in range(1, 3):
        attack_context_id = f"phase14h-lazy-save-transition:pool-001:attack-{attack_number:03d}"
        injected_results.extend(
            (
                _fixed_roll_result(
                    roll_id=f"phase14h-lazy-hit-{attack_number}",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}"
                        ),
                        roll_type="attack_sequence.hit",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"phase14h-lazy-wound-{attack_number}",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}"
                        ),
                        roll_type="attack_sequence.wound",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
            )
        )
    for attack_number, save_value in ((1, 1), (2, 3)):
        attack_context_id = f"phase14h-lazy-save-transition:pool-001:attack-{attack_number:03d}"
        injected_results.append(
            _fixed_roll_result(
                roll_id=f"phase14h-lazy-save-{attack_number}",
                spec=saving_throw_roll_spec(
                    save_kind=SaveKind.ARMOUR,
                    player_id="player-b",
                    allocated_model_id=first_model.model_instance_id,
                    attack_context_id=attack_context_id,
                ),
                value=save_value,
            )
        )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14h-lazy-save-transition",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=tuple(injected_results),
        ),
    )
    remaining_sequence, status = _continue_damage_model_choices(
        lifecycle,
        attack_sequence=remaining_sequence,
        allocated_ids=allocated_ids,
        status=status,
        result_id_prefix="phase14h-lazy-save-transition-model",
    )
    save_payloads = [
        cast(dict[str, object], event["payload"])
        for event in _event_payloads(lifecycle, "attack_sequence_step")
        if event["step"] == "save"
    ]
    damaged_model_ids = [
        cast(
            dict[str, object],
            cast(dict[str, object], event["payload"])["damage_application"],
        )["model_instance_id"]
        for event in _event_payloads(lifecycle, "attack_sequence_step")
        if event["step"] == "damage"
        and cast(dict[str, object], event["payload"])["damage_application"] is not None
    ]

    assert remaining_sequence is None
    assert status is not None
    assert save_payloads[1]["allocated_model_id"] == later_models[0].model_instance_id
    assert save_payloads[1]["target_number"] == 4
    assert save_payloads[1]["final_roll"] == 2
    option = cast(dict[str, object], save_payloads[1]["option"])
    assert option["target_number"] == 5
    assert option["characteristic_target_number"] == 4
    assert save_payloads[1]["successful"] is False
    assert damaged_model_ids[:2] == [
        first_model.model_instance_id,
        later_models[0].model_instance_id,
    ]


def test_phase14i_impossible_armour_save_remains_real_save_roll() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14i-impossible-armour-save",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -6),
        damage_profile=DamageProfile.fixed(1),
        keywords=(),
        abilities=(),
    )
    attack_context_id = "phase14i-impossible-armour-save:pool-001:attack-001"
    sequence = AttackSequence.start(
        sequence_id="phase14i-impossible-armour-save",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14i-impossible-armour-save",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14i-impossible-armour-hit",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}"
                        ),
                        roll_type="attack_sequence.hit",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14i-impossible-armour-wound",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}"
                        ),
                        roll_type="attack_sequence.wound",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14i-impossible-armour-save",
                    spec=saving_throw_roll_spec(
                        save_kind=SaveKind.ARMOUR,
                        player_id="player-b",
                        allocated_model_id=defender_model.model_instance_id,
                        attack_context_id=attack_context_id,
                    ),
                    value=6,
                ),
            ),
        ),
    )
    remaining_sequence, status = _continue_damage_model_choices(
        lifecycle,
        attack_sequence=remaining_sequence,
        allocated_ids=allocated_ids,
        status=status,
        result_id_prefix="phase14i-impossible-armour-model",
    )
    save_payload = next(
        cast(dict[str, object], event["payload"])
        for event in _event_payloads(lifecycle, "attack_sequence_step")
        if event["step"] == "save"
    )
    save_roll_types = [
        cast(
            str,
            cast(dict[str, object], cast(dict[str, object], record.payload)["spec"])["roll_type"],
        )
        for record in lifecycle.decision_controller.event_log.records
        if record.event_type == "dice_rolled"
        and cast(
            str,
            cast(dict[str, object], cast(dict[str, object], record.payload)["spec"])["roll_type"],
        ).startswith("attack_sequence.save.")
    ]
    option = cast(dict[str, object], save_payload["option"])

    assert remaining_sequence is None
    assert status is not None
    assert save_roll_types == ["attack_sequence.save.armour"]
    assert save_payload["save_kind"] == SaveKind.ARMOUR.value
    assert save_payload["target_number"] == 3
    assert save_payload["final_roll"] == 0
    assert save_payload["successful"] is False
    assert save_payload["resolution_rule"] == SaveResolutionRule.FAILED.value
    assert option["save_kind"] == SaveKind.ARMOUR.value
    assert option["target_number"] == 9


def test_phase14i_no_save_damage_order_die_is_not_a_save_roll() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14i-no-save-order",
        damage_profile=DamageProfile.fixed(1),
        keywords=(WeaponKeyword.DEVASTATING_WOUNDS, WeaponKeyword.TORRENT),
        abilities=(AbilityDescriptor.devastating_wounds(DevastatingWoundsEffect.NO_SAVES),),
    )
    attack_context_id = "phase14i-no-save-order:pool-001:attack-001"
    sequence = AttackSequence.start(
        sequence_id="phase14i-no-save-order",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14i-no-save-order",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14i-no-save-order-wound",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}"
                        ),
                        roll_type="attack_sequence.wound",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14i-no-save-order-die",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            "No-save damage order die for "
                            f"{defender_model.model_instance_id} from {attack_context_id}"
                        ),
                        roll_type="attack_sequence.allocation_order.no_save",
                        actor_id="player-b",
                    ),
                    value=6,
                ),
            ),
        ),
    )
    remaining_sequence, status = _continue_damage_model_choices(
        lifecycle,
        attack_sequence=remaining_sequence,
        allocated_ids=allocated_ids,
        status=status,
        result_id_prefix="phase14i-no-save-order-model",
    )
    save_payload = next(
        cast(dict[str, object], event["payload"])
        for event in _event_payloads(lifecycle, "attack_sequence_step")
        if event["step"] == "save"
    )
    roll_types = [
        cast(
            str,
            cast(dict[str, object], cast(dict[str, object], record.payload)["spec"])["roll_type"],
        )
        for record in lifecycle.decision_controller.event_log.records
        if record.event_type == "dice_rolled"
    ]

    assert remaining_sequence is None
    assert status is not None
    assert roll_types == ["attack_sequence.wound", "attack_sequence.allocation_order.no_save"]
    assert save_payload["save_kind"] is None
    assert save_payload["target_number"] is None
    assert save_payload["successful"] is False
    assert save_payload["option"] is None
    assert save_payload["save_options"] == []


def test_phase14h_pending_grouped_damage_round_trips_across_fnp_pause() -> None:
    lifecycle, request = _paused_optional_fnp_lifecycle()
    request_payload = cast(dict[str, object], request.payload)
    lost_wound_context = cast(dict[str, object], request_payload["lost_wound_context"])
    original_model_id = cast(str, lost_wound_context["allocated_model_id"])
    restored_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(restored_payload)

    _submit_all_pending_fnp_declines(lifecycle, request=request)
    restored_request = restored.decision_controller.queue.pending_requests[0]
    _submit_all_pending_fnp_declines(restored, request=restored_request)

    assert restored.decision_controller.event_log.to_payload() == (
        lifecycle.decision_controller.event_log.to_payload()
    )
    original_state = _state(lifecycle)
    restored_state = _state(restored)
    restored_wounds = model_by_id(
        state=restored_state,
        model_instance_id=original_model_id,
    ).wounds_remaining
    original_wounds = model_by_id(
        state=original_state,
        model_instance_id=original_model_id,
    ).wounds_remaining
    assert restored_wounds == original_wounds


def test_phase14h_pending_grouped_damage_payload_validates_fail_fast() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14h-pending-payload",
        damage_profile=DamageProfile.fixed(1),
        keywords=(),
        abilities=(),
    )
    sequence = AttackSequence.start(
        sequence_id="phase14h-pending-payload",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    attack_context_id = "phase14h-pending-payload:pool-001:attack-001"
    hit_roll_state = DiceRollManager("phase14h-pending-hit").roll_fixed(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
            roll_type="attack_sequence.hit",
            actor_id="player-a",
        ),
        [6],
    )
    wound_roll_state = DiceRollManager("phase14h-pending-wound").roll_fixed(
        DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
            roll_type="attack_sequence.wound",
            actor_id="player-a",
        ),
        [6],
    )
    save_roll_state = DiceRollManager("phase14h-pending-save").roll_fixed(
        saving_throw_roll_spec(
            save_kind=SaveKind.ARMOUR,
            player_id="player-b",
            allocated_model_id=defender.own_models[0].model_instance_id,
            attack_context_id=attack_context_id,
        ),
        [2],
    )
    hit_roll = HitRoll(
        target_number=3,
        roll_state=hit_roll_state,
        unmodified_roll=6,
        modifier=0,
        capped_modifier=0,
        final_roll=6,
        successful=True,
        critical=True,
    )
    wound_roll = WoundRoll(
        strength=4,
        toughness=4,
        target_number=4,
        roll_state=wound_roll_state,
        unmodified_roll=6,
        critical_threshold=6,
        modifier=0,
        capped_modifier=0,
        final_roll=6,
        successful=True,
        critical=True,
    )
    attack_context: AttackResolutionContextPayload = {
        "sequence_id": sequence.sequence_id,
        "source_phase": sequence.source_phase.value,
        "attack_context_id": attack_context_id,
        "pool_index": 0,
        "attack_index": 0,
        "generated_hit_index": 0,
        "attacker_player_id": "player-a",
        "defender_player_id": "player-b",
        "attacking_unit_instance_id": attacker.unit_instance_id,
        "attacker_model_instance_id": attacker.own_models[0].model_instance_id,
        "target_unit_instance_id": defender.unit_instance_id,
        "weapon_profile_id": weapon_profile.profile_id,
        "selected_weapon_ability_ids": [],
        "is_psychic_attack": False,
        "damage_profile": weapon_profile.damage_profile.to_payload(),
        "hit_roll": hit_roll.to_payload(),
        "wound_roll": wound_roll.to_payload(),
        "allocation": None,
        "save_options": [],
    }
    save_entry: SaveDieEntryPayload = {
        "roll_state": save_roll_state.to_payload(),
        "value": save_roll_state.current_total,
        "attack_context": attack_context,
    }
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=defender.unit_instance_id,
    )
    allocation_groups = allocation_groups_for_context(
        state=state,
        allocation_context=allocation_context,
        include_priority_tiers=True,
    )

    pending = PendingGroupedDamage(
        sorted_save_dice=(save_entry,),
        ordered_allocation_group_payloads=tuple(group.to_payload() for group in allocation_groups),
        allocation_context_payload=allocation_context.to_payload(),
        allocated_model_ids=(),
    )

    assert PendingGroupedDamage.from_payload(pending.to_payload()) == pending

    with pytest.raises(GameLifecycleError, match="sorted_save_dice must be a tuple"):
        PendingGroupedDamage(
            sorted_save_dice=[save_entry],  # type: ignore[arg-type]
            ordered_allocation_group_payloads=tuple(
                group.to_payload() for group in allocation_groups
            ),
            allocation_context_payload=allocation_context.to_payload(),
            allocated_model_ids=(),
        )

    with pytest.raises(GameLifecycleError, match="Save die entry payload must be an object"):
        PendingGroupedDamage(
            sorted_save_dice=("bad",),  # type: ignore[arg-type]
            ordered_allocation_group_payloads=tuple(
                group.to_payload() for group in allocation_groups
            ),
            allocation_context_payload=allocation_context.to_payload(),
            allocated_model_ids=(),
        )

    bad_roll_state_entry = cast(
        SaveDieEntryPayload,
        {
            **save_entry,
            "roll_state": [],
        },
    )
    with pytest.raises(GameLifecycleError, match="roll_state must be an object"):
        PendingGroupedDamage(
            sorted_save_dice=(bad_roll_state_entry,),
            ordered_allocation_group_payloads=tuple(
                group.to_payload() for group in allocation_groups
            ),
            allocation_context_payload=allocation_context.to_payload(),
            allocated_model_ids=(),
        )

    bad_attack_context_entry = cast(
        SaveDieEntryPayload,
        {
            **save_entry,
            "attack_context": [],
        },
    )
    with pytest.raises(GameLifecycleError, match="attack_context must be an object"):
        PendingGroupedDamage(
            sorted_save_dice=(bad_attack_context_entry,),
            ordered_allocation_group_payloads=tuple(
                group.to_payload() for group in allocation_groups
            ),
            allocation_context_payload=allocation_context.to_payload(),
            allocated_model_ids=(),
        )

    with pytest.raises(GameLifecycleError, match="duplicate attacks"):
        PendingGroupedDamage(
            sorted_save_dice=(save_entry, save_entry),
            ordered_allocation_group_payloads=tuple(
                group.to_payload() for group in allocation_groups
            ),
            allocation_context_payload=allocation_context.to_payload(),
            allocated_model_ids=(),
        )

    bad_value_entry: SaveDieEntryPayload = {
        **save_entry,
        "value": save_roll_state.current_total + 1,
    }
    with pytest.raises(GameLifecycleError, match="value must match roll_state"):
        PendingGroupedDamage(
            sorted_save_dice=(bad_value_entry,),
            ordered_allocation_group_payloads=tuple(
                group.to_payload() for group in allocation_groups
            ),
            allocation_context_payload=allocation_context.to_payload(),
            allocated_model_ids=(),
        )

    with pytest.raises(
        GameLifecycleError,
        match="ordered_allocation_group_payloads must be a tuple",
    ):
        PendingGroupedDamage(
            sorted_save_dice=(save_entry,),
            ordered_allocation_group_payloads=[  # type: ignore[arg-type]
                group.to_payload() for group in allocation_groups
            ],
            allocation_context_payload=allocation_context.to_payload(),
            allocated_model_ids=(),
        )

    with pytest.raises(GameLifecycleError, match="allocation group must be an object"):
        PendingGroupedDamage(
            sorted_save_dice=(save_entry,),
            ordered_allocation_group_payloads=("bad",),  # type: ignore[arg-type]
            allocation_context_payload=allocation_context.to_payload(),
            allocated_model_ids=(),
        )

    first_group_payload = allocation_groups[0].to_payload()
    with pytest.raises(GameLifecycleError, match="allocation groups duplicate IDs"):
        PendingGroupedDamage(
            sorted_save_dice=(save_entry,),
            ordered_allocation_group_payloads=(first_group_payload, first_group_payload),
            allocation_context_payload=allocation_context.to_payload(),
            allocated_model_ids=(),
        )

    with pytest.raises(GameLifecycleError, match="allocation groups must not be empty"):
        PendingGroupedDamage(
            sorted_save_dice=(save_entry,),
            ordered_allocation_group_payloads=(),
            allocation_context_payload=allocation_context.to_payload(),
            allocated_model_ids=(),
        )

    with pytest.raises(GameLifecycleError, match="next_index is outside save dice"):
        PendingGroupedDamage(
            sorted_save_dice=(save_entry,),
            ordered_allocation_group_payloads=tuple(
                group.to_payload() for group in allocation_groups
            ),
            allocation_context_payload=allocation_context.to_payload(),
            allocated_model_ids=(),
            next_index=2,
        )


def test_phase14e_allocation_order_request_after_grouped_wound_pool() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    alternate_save_model = replace(
        defender.own_models[1],
        characteristics=tuple(
            CharacteristicValue.from_raw(Characteristic.SAVE, 4)
            if value.characteristic is Characteristic.SAVE
            else value
            for value in defender.own_models[1].characteristics
        ),
    )
    defender = replace(
        defender,
        own_models=(defender.own_models[0], alternate_save_model, *defender.own_models[2:]),
    )
    _replace_unit_instance_in_state(state=state, replacement=defender)
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14e-allocation-order-grouped-pool",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -10),
        damage_profile=DamageProfile.fixed(1),
        keywords=(),
        abilities=(),
    )
    sequence = AttackSequence.start(
        sequence_id="phase14e-allocation-order-grouped-pool",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=2,
            ),
        ),
    )
    injected_results: list[DiceRollResult] = []
    for attack_number in range(1, 3):
        attack_context_id = (
            f"phase14e-allocation-order-grouped-pool:pool-001:attack-{attack_number:03d}"
        )
        injected_results.append(
            _fixed_roll_result(
                roll_id=f"phase14e-order-hit-{attack_number}",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason=(f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}"),
                    roll_type="attack_sequence.hit",
                    actor_id="player-a",
                ),
                value=6,
            )
        )
        injected_results.append(
            _fixed_roll_result(
                roll_id=f"phase14e-order-wound-{attack_number}",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason=(
                        f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}"
                    ),
                    roll_type="attack_sequence.wound",
                    actor_id="player-a",
                ),
                value=6,
            )
        )

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14e-allocation-order-grouped-pool",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=tuple(injected_results),
        ),
    )
    request = _decision_request(cast(LifecycleStatus, status))
    request_payload = cast(dict[str, object], request.payload)
    attack_contexts = cast(list[dict[str, object]], request_payload["attack_contexts"])
    attack_events = _event_payloads(lifecycle, "attack_sequence_step")

    assert remaining_sequence is not None
    assert remaining_sequence.attack_pools == sequence.attack_pools
    assert remaining_sequence.used_pool_indices == ()
    assert remaining_sequence.selected_target_unit_instance_id == defender.unit_instance_id
    assert remaining_sequence.current_gathered_group is not None
    assert remaining_sequence.current_gathered_group.total_attacks == 2
    assert remaining_sequence.pool_index == 0
    assert request.decision_type == SELECT_ALLOCATION_ORDER_DECISION_TYPE
    assert len(request.options) == 2
    assert [context["attack_context_id"] for context in attack_contexts] == [
        "phase14e-allocation-order-grouped-pool:pool-001:attack-001",
        "phase14e-allocation-order-grouped-pool:pool-001:attack-002",
    ]
    assert sum(1 for event in attack_events if event["step"] == "hit") == 2
    assert sum(1 for event in attack_events if event["step"] == "wound") == 2
    assert not any(event["step"] == "save" for event in attack_events)

    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=remaining_sequence.attack_pools,
        attack_sequence=remaining_sequence,
        allocated_model_ids_this_phase=(),
    )
    final_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase14e-allocation-order-grouped-select",
            request=request,
            selected_option_id=request.options[0].option_id,
        )
    )
    _final_sequence, drained_status = _continue_damage_model_choices(
        lifecycle,
        attack_sequence=None,
        allocated_ids=(),
        status=final_status,
        result_id_prefix="phase14e-allocation-order-grouped-model",
    )
    assert drained_status is not None
    final_status = drained_status
    final_attack_events = _event_payloads(lifecycle, "attack_sequence_step")

    assert final_status.status_kind in {
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.UNSUPPORTED,
    }
    assert sum(1 for event in final_attack_events if event["step"] == "damage") >= 2


def test_phase14e_grouped_failed_saves_transition_to_next_ordered_group() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    first_group_model = replace(
        defender.own_models[0],
        characteristics=tuple(
            CharacteristicValue.from_raw(Characteristic.SAVE, 2)
            if value.characteristic is Characteristic.SAVE
            else value
            for value in defender.own_models[0].characteristics
        ),
    )
    later_group_models = tuple(
        replace(
            model,
            characteristics=tuple(
                CharacteristicValue.from_raw(Characteristic.SAVE, 4)
                if value.characteristic is Characteristic.SAVE
                else value
                for value in model.characteristics
            ),
        )
        for model in defender.own_models[1:]
    )
    defender = replace(defender, own_models=(first_group_model, *later_group_models))
    _replace_unit_instance_in_state(state=state, replacement=defender)
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14e-ordered-group-transition",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -10),
        damage_profile=DamageProfile.fixed(first_group_model.starting_wounds),
        keywords=(),
        abilities=(),
    )
    sequence = AttackSequence.start(
        sequence_id="phase14e-ordered-group-transition",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=2,
            ),
        ),
    )
    injected_results: list[DiceRollResult] = []
    for attack_number in range(1, 3):
        attack_context_id = f"phase14e-ordered-group-transition:pool-001:attack-{attack_number:03d}"
        injected_results.append(
            _fixed_roll_result(
                roll_id=f"phase14e-ordered-transition-hit-{attack_number}",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason=(f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}"),
                    roll_type="attack_sequence.hit",
                    actor_id="player-a",
                ),
                value=6,
            )
        )
        injected_results.append(
            _fixed_roll_result(
                roll_id=f"phase14e-ordered-transition-wound-{attack_number}",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason=(
                        f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}"
                    ),
                    roll_type="attack_sequence.wound",
                    actor_id="player-a",
                ),
                value=6,
            )
        )

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14e-ordered-group-transition",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=tuple(injected_results),
        ),
    )
    request = _decision_request(cast(LifecycleStatus, status))
    request_payload = cast(dict[str, object], request.payload)
    allocation_groups = cast(list[dict[str, object]], request_payload["allocation_groups"])
    one_model_group = next(
        group
        for group in allocation_groups
        if cast(list[str], group["model_ids"]) == [first_group_model.model_instance_id]
    )
    later_group = next(
        group
        for group in allocation_groups
        if first_group_model.model_instance_id not in cast(list[str], group["model_ids"])
    )
    selected_option = next(
        option
        for option in request.options
        if cast(dict[str, object], option.payload)["ordered_group_ids"]
        == [one_model_group["group_id"], later_group["group_id"]]
    )

    assert remaining_sequence is not None
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=remaining_sequence.attack_pools,
        attack_sequence=remaining_sequence,
        allocated_model_ids_this_phase=(),
    )
    final_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase14e-ordered-group-transition-select",
            request=request,
            selected_option_id=selected_option.option_id,
        )
    )
    _final_sequence, drained_status = _continue_damage_model_choices(
        lifecycle,
        attack_sequence=None,
        allocated_ids=(),
        status=final_status,
        result_id_prefix="phase14e-ordered-group-transition-model",
    )
    assert drained_status is not None
    final_status = drained_status
    damage_model_ids = [
        cast(
            dict[str, object],
            cast(dict[str, object], event["payload"])["damage_application"],
        )["model_instance_id"]
        for event in _event_payloads(lifecycle, "attack_sequence_step")
        if event["step"] == "damage"
        and cast(dict[str, object], event["payload"])["damage_application"] is not None
    ]
    grouped_allocation = next(
        cast(dict[str, object], event["payload"])
        for event in _event_payloads(lifecycle, "attack_sequence_step")
        if event["step"] == "allocate"
        and cast(dict[str, object], event["payload"]).get("grouped_save_before_allocation") is True
        and "allocation_order_group_ids" in cast(dict[str, object], event["payload"])
    )

    assert final_status.status_kind in {
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.UNSUPPORTED,
    }
    assert grouped_allocation["allocation_order_group_ids"] == [
        one_model_group["group_id"],
        later_group["group_id"],
    ]
    assert damage_model_ids[:2] == [
        first_group_model.model_instance_id,
        cast(list[str], later_group["model_ids"])[0],
    ]
    assert not model_by_id(
        state=state,
        model_instance_id=first_group_model.model_instance_id,
    ).is_alive


def test_phase14e_allocation_order_only_exposes_same_tier_choices() -> None:
    allocation_context = AttackAllocationRuleContext(
        target_unit_instance_id="phase14e-tier-target",
        alive_model_ids=(
            "phase14e-bodyguard-a",
            "phase14e-character-a",
            "phase14e-character-b",
        ),
    )
    bodyguard_group = AllocationGroup(
        group_id="phase14e-bodyguard-group",
        target_unit_instance_id="phase14e-tier-target",
        model_ids=("phase14e-bodyguard-a",),
        role=AllocationGroupRole.BODYGUARD,
        wounds=2,
        save=3,
        invulnerable_save=None,
    )
    wounded_character_group = AllocationGroup(
        group_id="phase14e-wounded-character-group",
        target_unit_instance_id="phase14e-tier-target",
        model_ids=("phase14e-character-a",),
        role=AllocationGroupRole.CHARACTER,
        wounds=4,
        save=3,
        invulnerable_save=4,
        wounded_model_ids=("phase14e-character-a",),
        character_model_ids=("phase14e-character-a",),
    )
    unwounded_character_group = AllocationGroup(
        group_id="phase14e-unwounded-character-group",
        target_unit_instance_id="phase14e-tier-target",
        model_ids=("phase14e-character-b",),
        role=AllocationGroupRole.SUPPORT,
        wounds=4,
        save=3,
        invulnerable_save=4,
        character_model_ids=("phase14e-character-b",),
    )

    forced_order = legal_allocation_group_orders(
        (wounded_character_group, bodyguard_group, unwounded_character_group)
    )

    assert forced_order == ((bodyguard_group, wounded_character_group, unwounded_character_group),)
    with pytest.raises(GameLifecycleError, match="at least two legal orders"):
        build_allocation_order_request(
            request_id="phase14e-tier-forced-request",
            defender_player_id="player-b",
            attack_context={"attack_context_id": "phase14e-tier-forced"},
            allocation_context=allocation_context,
            allocation_groups=(
                bodyguard_group,
                wounded_character_group,
                unwounded_character_group,
            ),
        )
    with pytest.raises(GameLifecycleError, match="legal allocation order"):
        AllocationOrderDecision(
            request_id="phase14e-tier-illegal-request",
            result_id="phase14e-tier-illegal-result",
            player_id="player-b",
            ordered_group_ids=(
                wounded_character_group.group_id,
                bodyguard_group.group_id,
                unwounded_character_group.group_id,
            ),
            attack_context={"attack_context_id": "phase14e-tier-illegal"},
            allocation_context=allocation_context,
            allocation_groups=(
                bodyguard_group,
                wounded_character_group,
                unwounded_character_group,
            ),
        )

    peer_bodyguard_group = AllocationGroup(
        group_id="phase14e-peer-bodyguard-group",
        target_unit_instance_id="phase14e-tier-target",
        model_ids=("phase14e-bodyguard-b",),
        role=AllocationGroupRole.BODYGUARD,
        wounds=2,
        save=4,
        invulnerable_save=None,
    )
    peer_context = AttackAllocationRuleContext(
        target_unit_instance_id="phase14e-tier-target",
        alive_model_ids=(
            "phase14e-bodyguard-a",
            "phase14e-bodyguard-b",
            "phase14e-character-b",
        ),
    )
    peer_request = build_allocation_order_request(
        request_id="phase14e-tier-peer-request",
        defender_player_id="player-b",
        attack_context={"attack_context_id": "phase14e-tier-peer"},
        allocation_context=peer_context,
        allocation_groups=(
            bodyguard_group,
            peer_bodyguard_group,
            unwounded_character_group,
        ),
    )
    option_orders = tuple(
        tuple(cast(list[str], cast(dict[str, object], option.payload)["ordered_group_ids"]))
        for option in peer_request.options
    )
    selected_option = peer_request.options[0]
    decision = AllocationOrderDecision.from_result(
        request=peer_request,
        result=DecisionResult.for_request(
            result_id="phase14e-tier-peer-result",
            request=peer_request,
            selected_option_id=selected_option.option_id,
        ),
    )

    assert option_orders == (
        (
            bodyguard_group.group_id,
            peer_bodyguard_group.group_id,
            unwounded_character_group.group_id,
        ),
        (
            peer_bodyguard_group.group_id,
            bodyguard_group.group_id,
            unwounded_character_group.group_id,
        ),
    )
    assert cast(dict[str, object], peer_request.payload)["priority_group_ids"] == []
    assert decision.to_payload()["priority_group_ids"] == []

    priority_order = legal_allocation_group_orders(
        (
            bodyguard_group,
            wounded_character_group,
            unwounded_character_group,
        ),
        priority_group_ids=(unwounded_character_group.group_id,),
    )
    assert priority_order == (
        (unwounded_character_group, bodyguard_group, wounded_character_group),
    )


def test_phase14e_grouped_lethal_sustained_hits_use_grouped_host() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14e-grouped-lethal-sustained",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -10),
        keywords=(WeaponKeyword.LETHAL_HITS, WeaponKeyword.SUSTAINED_HITS),
        abilities=(AbilityDescriptor.lethal_hits(), AbilityDescriptor.sustained_hits(1)),
    )
    first_context_id = "phase14e-grouped-lethal-sustained:pool-001:attack-001"
    generated_context_id = f"{first_context_id}:generated-hit-002"
    second_context_id = "phase14e-grouped-lethal-sustained:pool-001:attack-002"
    current_save_model_id = defender.own_models[0].model_instance_id
    sequence = AttackSequence.start(
        sequence_id="phase14e-grouped-lethal-sustained",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=2,
            ),
        ),
    )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14e-grouped-lethal-sustained",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14e-grouped-lethal-sustained-hit-1",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Hit roll for {weapon_profile.profile_id} attack {first_context_id}"
                        ),
                        roll_type="attack_sequence.hit",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14e-grouped-lethal-sustained-wound-generated",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            "Wound roll for "
                            f"{weapon_profile.profile_id} attack {generated_context_id}"
                        ),
                        roll_type="attack_sequence.wound",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14e-grouped-lethal-sustained-hit-2",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Hit roll for {weapon_profile.profile_id} attack {second_context_id}"
                        ),
                        roll_type="attack_sequence.hit",
                        actor_id="player-a",
                    ),
                    value=1,
                ),
                _fixed_roll_result(
                    roll_id="phase14e-grouped-lethal-sustained-armour-save-1",
                    spec=saving_throw_roll_spec(
                        save_kind=SaveKind.ARMOUR,
                        player_id="player-b",
                        allocated_model_id=current_save_model_id,
                        attack_context_id=first_context_id,
                    ),
                    value=1,
                ),
                _fixed_roll_result(
                    roll_id="phase14e-grouped-lethal-sustained-armour-save-generated",
                    spec=saving_throw_roll_spec(
                        save_kind=SaveKind.ARMOUR,
                        player_id="player-b",
                        allocated_model_id=current_save_model_id,
                        attack_context_id=generated_context_id,
                    ),
                    value=2,
                ),
            ),
        ),
    )
    remaining_sequence, status = _continue_damage_model_choices(
        lifecycle,
        attack_sequence=remaining_sequence,
        allocated_ids=allocated_ids,
        status=status,
        result_id_prefix="phase14e-grouped-lethal-sustained-model",
    )
    events = _event_payloads(lifecycle, "attack_sequence_step")
    grouped_allocation = next(
        cast(dict[str, object], event["payload"])
        for event in events
        if event["step"] == "allocate"
        and cast(dict[str, object], event["payload"]).get("grouped_save_before_allocation") is True
    )
    wound_events = [event for event in events if event["step"] == "wound"]
    critical_hit_events = [event for event in events if event["step"] == "critical_hit"]
    damage_context_ids = [
        event["attack_context_id"]
        for event in events
        if event["step"] == "damage"
        and cast(dict[str, object], event["payload"])["damage_application"] is not None
    ]

    assert remaining_sequence is None
    assert status is not None
    assert (
        cast(dict[str, object], _attack_step_payload(events, AttackSequenceStep.HIT)["payload"])[
            "generated_hits"
        ]
        == 2
    )
    assert critical_hit_events[0]["attack_context_id"] == first_context_id
    assert [event["attack_context_id"] for event in wound_events] == [
        first_context_id,
        generated_context_id,
    ]
    assert cast(dict[str, object], wound_events[0]["payload"])["skipped"] is True
    assert grouped_allocation["attack_context_ids"] == [
        first_context_id,
        generated_context_id,
    ]
    assert damage_context_ids == [first_context_id, generated_context_id]


def test_phase14e_grouped_devastating_wounds_cap_each_critical_wound() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14e-grouped-devastating-wounds",
        damage_profile=DamageProfile.fixed(3),
        keywords=(WeaponKeyword.DEVASTATING_WOUNDS, WeaponKeyword.TORRENT),
        abilities=(AbilityDescriptor.devastating_wounds(),),
    )
    first_context_id = "phase14e-grouped-devastating:pool-001:attack-001"
    second_context_id = "phase14e-grouped-devastating:pool-001:attack-002"
    sequence = AttackSequence.start(
        sequence_id="phase14e-grouped-devastating",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=2,
            ),
        ),
    )

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14e-grouped-devastating",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14e-grouped-devastating-wound-1",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Wound roll for {weapon_profile.profile_id} attack {first_context_id}"
                        ),
                        roll_type="attack_sequence.wound",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14e-grouped-devastating-wound-2",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=(
                            f"Wound roll for {weapon_profile.profile_id} attack {second_context_id}"
                        ),
                        roll_type="attack_sequence.wound",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
            ),
        ),
    )
    deferred_events = _event_payloads(lifecycle, "devastating_wounds_deferred")
    applied_events = _event_payloads(lifecycle, "devastating_wounds_mortal_wounds_applied")
    attack_events = _event_payloads(lifecycle, "attack_sequence_step")
    applied_payloads = [
        cast(dict[str, object], event["mortal_wound_application"]) for event in applied_events
    ]
    application_lists = [
        cast(list[dict[str, object]], payload["applications"]) for payload in applied_payloads
    ]

    assert remaining_sequence is None
    assert status is None
    assert [event["attack_context_id"] for event in deferred_events] == [
        first_context_id,
        second_context_id,
    ]
    assert [event["attack_context_ids"] for event in applied_events] == [
        [first_context_id],
        [second_context_id],
    ]
    assert all(payload["mortal_wounds"] == 3 for payload in applied_payloads)
    assert all(payload["spill_over"] is False for payload in applied_payloads)
    assert all(payload["remaining_mortal_wounds_lost"] == 1 for payload in applied_payloads)
    assert all(
        len({application["model_instance_id"] for application in applications}) == 1
        for applications in application_lists
    )
    assert not any(event["step"] == "save" for event in attack_events)
    assert not any(
        event["step"] == "allocate"
        and cast(dict[str, object], event["payload"]).get("grouped_save_before_allocation") is True
        for event in attack_events
    )


def test_phase14e_grouped_precision_promotes_character_then_returns_to_bodyguard() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = _replace_enemy_with_attached_character_fixture(state=state, defender=units["enemy"])
    bodyguard_model = defender.own_models[0]
    character_model = defender.own_models[1]
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14e-grouped-precision",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -10),
        damage_profile=DamageProfile.fixed(character_model.starting_wounds),
        keywords=(WeaponKeyword.PRECISION,),
    )
    sequence = AttackSequence.start(
        sequence_id="phase14e-grouped-precision",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=2,
            ),
        ),
    )
    injected_results: list[DiceRollResult] = []
    for attack_number in range(1, 3):
        attack_context_id = f"phase14e-grouped-precision:pool-001:attack-{attack_number:03d}"
        injected_results.append(
            _fixed_roll_result(
                roll_id=f"phase14e-grouped-precision-hit-{attack_number}",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
                    roll_type="attack_sequence.hit",
                    actor_id="player-a",
                ),
                value=6,
            )
        )
        injected_results.append(
            _fixed_roll_result(
                roll_id=f"phase14e-grouped-precision-wound-{attack_number}",
                spec=DiceRollSpec(
                    expression=DiceExpression(quantity=1, sides=6),
                    reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
                    roll_type="attack_sequence.wound",
                    actor_id="player-a",
                ),
                value=6,
            )
        )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14e-grouped-precision",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=tuple(injected_results),
        ),
    )
    request = _decision_request(cast(LifecycleStatus, status))
    request_payload = cast(dict[str, object], request.payload)
    character_option = next(
        option
        for option in request.options
        if character_model.model_instance_id
        in cast(list[str], cast(dict[str, object], option.payload)["selected_model_ids"])
    )

    assert remaining_sequence is not None
    assert request.decision_type == SELECT_PRECISION_ALLOCATION_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert [
        context["attack_context_id"]
        for context in cast(list[dict[str, object]], request_payload["attack_contexts"])
    ] == [
        "phase14e-grouped-precision:pool-001:attack-001",
        "phase14e-grouped-precision:pool-001:attack-002",
    ]

    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=remaining_sequence.attack_pools,
        attack_sequence=remaining_sequence,
        allocated_model_ids_this_phase=allocated_ids,
    )
    final_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase14e-grouped-precision-select",
            request=request,
            selected_option_id=character_option.option_id,
        )
    )
    attack_events = _event_payloads(lifecycle, "attack_sequence_step")
    grouped_allocation = next(
        cast(dict[str, object], event["payload"])
        for event in attack_events
        if event["step"] == "allocate"
        and cast(dict[str, object], event["payload"]).get("grouped_save_before_allocation") is True
    )
    damage_model_ids = [
        cast(
            dict[str, object],
            cast(dict[str, object], event["payload"])["damage_application"],
        )["model_instance_id"]
        for event in attack_events
        if event["step"] == "damage"
        and cast(dict[str, object], event["payload"])["damage_application"] is not None
    ]

    assert final_status.status_kind in {
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.UNSUPPORTED,
    }
    assert cast(list[str], grouped_allocation["allocation_order_group_ids"])[0] == (
        character_option.option_id
    )
    assert character_model.model_instance_id in cast(
        list[str],
        cast(dict[str, object], grouped_allocation["allocation_group"])["model_ids"],
    )
    assert damage_model_ids[:2] == [
        character_model.model_instance_id,
        bodyguard_model.model_instance_id,
    ]
    assert not model_by_id(
        state=state, model_instance_id=character_model.model_instance_id
    ).is_alive


def test_phase13d_lethal_and_sustained_hits_resolve_generated_hits() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase13d-lethal-sustained",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -6),
        keywords=(WeaponKeyword.LETHAL_HITS, WeaponKeyword.SUSTAINED_HITS),
        abilities=(AbilityDescriptor.lethal_hits(), AbilityDescriptor.sustained_hits(1)),
    )
    first_context_id = "phase13d-sustained:pool-001:attack-001"
    generated_context_id = f"{first_context_id}:generated-hit-002"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {first_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {generated_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    dice_manager = DiceRollManager(
        "phase13d-sustained",
        event_log=lifecycle.decision_controller.event_log,
        injected_results=(
            _fixed_roll_result(roll_id="phase13d-sustained-hit", spec=hit_spec, value=6),
            _fixed_roll_result(roll_id="phase13d-sustained-wound", spec=wound_spec, value=6),
        ),
    )
    sequence = AttackSequence.start(
        sequence_id="phase13d-sustained",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=dice_manager,
    )

    events = _event_payloads(lifecycle, "attack_sequence_step")
    hit_payload = _attack_step_payload(events, AttackSequenceStep.HIT)
    wound_events = [event for event in events if event["step"] == AttackSequenceStep.WOUND.value]
    damage_events = [event for event in events if event["step"] == AttackSequenceStep.DAMAGE.value]
    assert remaining_sequence is None
    assert status is None
    assert cast(dict[str, object], hit_payload["payload"])["generated_hits"] == 2
    assert len(wound_events) == 2
    assert wound_events[0]["attack_context_id"] == first_context_id
    assert cast(dict[str, object], wound_events[0]["payload"])["skipped"] is True
    assert wound_events[1]["attack_context_id"] == generated_context_id
    assert cast(dict[str, object], wound_events[1]["payload"])["skipped"] is False
    assert len(damage_events) == 2


def test_phase14i_lethal_hits_vehicle_gate_controls_auto_wound() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = replace(units["enemy"], keywords=("VEHICLE",))
    _replace_unit_instance_in_state(state=state, replacement=defender)
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14i-lethal-hits-vehicle-gate",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -6),
        keywords=(WeaponKeyword.LETHAL_HITS,),
        abilities=(AbilityDescriptor.lethal_hits(target_keywords=("VEHICLE",)),),
    )
    attack_context_id = "phase14i-lethal-hits-vehicle-gate:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    sequence = AttackSequence.start(
        sequence_id="phase14i-lethal-hits-vehicle-gate",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14i-lethal-hits-vehicle-gate",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14i-lethal-hits-vehicle-gate-hit",
                    spec=hit_spec,
                    value=6,
                ),
            ),
        ),
    )
    wound_events = [
        event
        for event in _event_payloads(lifecycle, "attack_sequence_step")
        if event["step"] == AttackSequenceStep.WOUND.value
    ]

    assert remaining_sequence is None
    assert status is None
    assert len(wound_events) == 1
    assert cast(dict[str, object], wound_events[0]["payload"])["skipped"] is True


def test_phase14h_attached_unit_uses_highest_bodyguard_toughness_for_wounds() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = _replace_enemy_with_attached_character_fixture(state=state, defender=units["enemy"])
    bodyguard_model = _model_with_characteristic(
        _model_with_attached_role(defender.own_models[0], role="bodyguard"),
        characteristic=Characteristic.TOUGHNESS,
        raw_value=5,
    )
    leader_model = _model_with_characteristic(
        _model_with_attached_role(defender.own_models[1], role="leader"),
        characteristic=Characteristic.TOUGHNESS,
        raw_value=7,
    )
    attached_defender = replace(defender, own_models=(bodyguard_model, leader_model))
    _replace_unit_instance_in_state(state=state, replacement=attached_defender)
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14h-attached-bodyguard-toughness",
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 6),
        damage_profile=DamageProfile.fixed(1),
        keywords=(),
        abilities=(),
    )
    attack_context_id = "phase14h-attached-bodyguard-toughness:pool-001:attack-001"

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=AttackSequence.start(
            sequence_id="phase14h-attached-bodyguard-toughness",
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=attached_defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14h-attached-bodyguard-toughness",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14h-attached-bodyguard-hit",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=f"Hit roll for {weapon_profile.profile_id} attack "
                        f"{attack_context_id}",
                        roll_type="attack_sequence.hit",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14h-attached-bodyguard-wound",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=f"Wound roll for {weapon_profile.profile_id} attack "
                        f"{attack_context_id}",
                        roll_type="attack_sequence.wound",
                        actor_id="player-a",
                    ),
                    value=3,
                ),
            ),
        ),
    )
    wound_payload = cast(
        dict[str, object],
        _attack_step_payload(
            _event_payloads(lifecycle, "attack_sequence_step"),
            AttackSequenceStep.WOUND,
        )["payload"],
    )

    assert remaining_sequence is None
    assert status is None
    assert wound_payload["toughness"] == 5
    assert wound_payload["target_number"] == 3
    assert wound_payload["successful"] is True


def test_phase14h_attached_unit_uses_support_toughness_after_bodyguard_destroyed() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = _replace_enemy_with_attached_character_fixture(state=state, defender=units["enemy"])
    bodyguard_model = _model_with_characteristic(
        _model_with_attached_role(
            replace(
                defender.own_models[0],
                wounds_remaining=0,
            ),
            role="bodyguard",
        ),
        characteristic=Characteristic.TOUGHNESS,
        raw_value=5,
    )
    support_model = _model_with_characteristic(
        _model_with_attached_role(defender.own_models[1], role="support"),
        characteristic=Characteristic.TOUGHNESS,
        raw_value=7,
    )
    attached_defender = replace(defender, own_models=(bodyguard_model, support_model))
    _replace_unit_instance_in_state(state=state, replacement=attached_defender)
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.replace_battlefield_state(
        battlefield.with_removed_models((bodyguard_model.model_instance_id,))
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14h-attached-support-toughness",
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 6),
        damage_profile=DamageProfile.fixed(1),
        keywords=(),
        abilities=(),
    )
    attack_context_id = "phase14h-attached-support-toughness:pool-001:attack-001"

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=AttackSequence.start(
            sequence_id="phase14h-attached-support-toughness",
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=attached_defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14h-attached-support-toughness",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14h-attached-support-hit",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=f"Hit roll for {weapon_profile.profile_id} attack "
                        f"{attack_context_id}",
                        roll_type="attack_sequence.hit",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14h-attached-support-wound",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=f"Wound roll for {weapon_profile.profile_id} attack "
                        f"{attack_context_id}",
                        roll_type="attack_sequence.wound",
                        actor_id="player-a",
                    ),
                    value=4,
                ),
            ),
        ),
    )
    wound_payload = cast(
        dict[str, object],
        _attack_step_payload(
            _event_payloads(lifecycle, "attack_sequence_step"),
            AttackSequenceStep.WOUND,
        )["payload"],
    )

    assert remaining_sequence is None
    assert status is None
    assert wound_payload["toughness"] == 7
    assert wound_payload["target_number"] == 5
    assert wound_payload["successful"] is False


def test_phase14h_attached_unit_uses_leader_toughness_after_bodyguard_destroyed() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = _replace_enemy_with_attached_character_fixture(state=state, defender=units["enemy"])
    bodyguard_model = _model_with_characteristic(
        _model_with_attached_role(
            replace(
                defender.own_models[0],
                wounds_remaining=0,
            ),
            role="bodyguard",
        ),
        characteristic=Characteristic.TOUGHNESS,
        raw_value=5,
    )
    leader_model = _model_with_characteristic(
        _model_with_attached_role(defender.own_models[1], role="leader"),
        characteristic=Characteristic.TOUGHNESS,
        raw_value=7,
    )
    attached_defender = replace(defender, own_models=(bodyguard_model, leader_model))
    _replace_unit_instance_in_state(state=state, replacement=attached_defender)
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.replace_battlefield_state(
        battlefield.with_removed_models((bodyguard_model.model_instance_id,))
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14h-attached-leader-toughness",
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 6),
        damage_profile=DamageProfile.fixed(1),
        keywords=(),
        abilities=(),
    )
    attack_context_id = "phase14h-attached-leader-toughness:pool-001:attack-001"

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=AttackSequence.start(
            sequence_id="phase14h-attached-leader-toughness",
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=attached_defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14h-attached-leader-toughness",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14h-attached-leader-hit",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=f"Hit roll for {weapon_profile.profile_id} attack "
                        f"{attack_context_id}",
                        roll_type="attack_sequence.hit",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14h-attached-leader-wound",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=f"Wound roll for {weapon_profile.profile_id} attack "
                        f"{attack_context_id}",
                        roll_type="attack_sequence.wound",
                        actor_id="player-a",
                    ),
                    value=4,
                ),
            ),
        ),
    )
    wound_payload = cast(
        dict[str, object],
        _attack_step_payload(
            _event_payloads(lifecycle, "attack_sequence_step"),
            AttackSequenceStep.WOUND,
        )["payload"],
    )

    assert remaining_sequence is None
    assert status is None
    assert wound_payload["toughness"] == 7
    assert wound_payload["target_number"] == 5
    assert wound_payload["successful"] is False


def test_phase14h_mustered_attached_unit_targets_and_allocates_as_rules_unit() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_specs=_attached_enemy_unit_specs(),
        enemy_attachment_declarations=_attached_enemy_declarations(),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    bodyguard = _replace_unit_toughness(
        state=state,
        unit=units["bodyguard-unit"],
        toughness=5,
    )
    leader = _replace_unit_toughness(
        state=state,
        unit=units["leader-unit"],
        toughness=7,
    )
    support = _replace_unit_toughness(
        state=state,
        unit=units["support-unit"],
        toughness=6,
    )
    formation = _attached_formation_for_player(state=state, player_id="player-b")
    attached_id = formation.attached_unit_instance_id
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    target_candidates = shooting_target_candidates_for_unit(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=_first_weapon_profile(lifecycle, attacker),
        target_unit_ids=(bodyguard.unit_instance_id, leader.unit_instance_id),
    )
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=attached_id,
    )

    assert len(target_candidates) == 1
    assert target_candidates[0].target_unit_instance_id == attached_id
    assert allocation_context.target_unit_instance_id == attached_id
    assert allocation_context.attached_unit_bodyguard_model_ids == tuple(
        sorted(model.model_instance_id for model in bodyguard.own_models)
    )
    assert allocation_context.attached_unit_character_model_ids == tuple(
        sorted(
            (
                leader.own_models[0].model_instance_id,
                support.own_models[0].model_instance_id,
            )
        )
    )
    assert allocation_context.legal_model_ids() == (
        allocation_context.attached_unit_bodyguard_model_ids
    )

    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14h-real-attached-bodyguard-toughness",
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 6),
        damage_profile=DamageProfile.fixed(1),
        keywords=(),
        abilities=(),
    )
    attack_context_id = "phase14h-real-attached-bodyguard-toughness:pool-001:attack-001"
    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=AttackSequence.start(
            sequence_id="phase14h-real-attached-bodyguard-toughness",
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=bodyguard,
                    weapon_profile=weapon_profile,
                    attacks=1,
                    target_unit_instance_id=attached_id,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14h-real-attached-bodyguard-toughness",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14h-real-attached-bodyguard-hit",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=f"Hit roll for {weapon_profile.profile_id} attack "
                        f"{attack_context_id}",
                        roll_type="attack_sequence.hit",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14h-real-attached-bodyguard-wound",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=f"Wound roll for {weapon_profile.profile_id} attack "
                        f"{attack_context_id}",
                        roll_type="attack_sequence.wound",
                        actor_id="player-a",
                    ),
                    value=3,
                ),
            ),
        ),
    )
    wound_payload = cast(
        dict[str, object],
        _attack_step_payload(
            _event_payloads(lifecycle, "attack_sequence_step"),
            AttackSequenceStep.WOUND,
        )["payload"],
    )

    assert remaining_sequence is not None
    assert remaining_sequence.pending_grouped_damage is not None
    pending_context = remaining_sequence.pending_grouped_damage.allocation_context()
    assert pending_context.target_unit_instance_id == attached_id
    assert pending_context.legal_model_ids() == pending_context.attached_unit_bodyguard_model_ids
    assert status is not None
    assert wound_payload["toughness"] == 5
    assert wound_payload["target_number"] == 3
    assert wound_payload["successful"] is True


def test_phase14h_mustered_attached_unit_uses_character_toughness_after_bodyguard_removed() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_specs=_attached_enemy_unit_specs(),
        enemy_attachment_declarations=_attached_enemy_declarations(),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    bodyguard = _replace_unit_toughness(
        state=state,
        unit=units["bodyguard-unit"],
        toughness=5,
    )
    leader = _replace_unit_toughness(
        state=state,
        unit=units["leader-unit"],
        toughness=7,
    )
    support = _replace_unit_toughness(
        state=state,
        unit=units["support-unit"],
        toughness=6,
    )
    formation = _attached_formation_for_player(state=state, player_id="player-b")
    attached_id = formation.attached_unit_instance_id
    removed_bodyguard_ids = tuple(model.model_instance_id for model in bodyguard.own_models)
    _replace_unit_instance_in_state(
        state=state,
        replacement=replace(
            bodyguard,
            own_models=tuple(replace(model, wounds_remaining=0) for model in bodyguard.own_models),
        ),
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(removed_bodyguard_ids)
    )
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=attached_id,
    )
    assert allocation_context.attached_unit_bodyguard_model_ids == ()
    assert allocation_context.legal_model_ids() == tuple(
        sorted(
            (
                leader.own_models[0].model_instance_id,
                support.own_models[0].model_instance_id,
            )
        )
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14h-real-attached-leader-support-toughness",
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 6),
        damage_profile=DamageProfile.fixed(1),
        keywords=(),
        abilities=(),
    )
    attack_context_id = "phase14h-real-attached-leader-support-toughness:pool-001:attack-001"

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=AttackSequence.start(
            sequence_id="phase14h-real-attached-leader-support-toughness",
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=leader,
                    weapon_profile=weapon_profile,
                    attacks=1,
                    target_unit_instance_id=attached_id,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14h-real-attached-leader-support-toughness",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14h-real-attached-leader-support-hit",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=f"Hit roll for {weapon_profile.profile_id} attack "
                        f"{attack_context_id}",
                        roll_type="attack_sequence.hit",
                        actor_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14h-real-attached-leader-support-wound",
                    spec=DiceRollSpec(
                        expression=DiceExpression(quantity=1, sides=6),
                        reason=f"Wound roll for {weapon_profile.profile_id} attack "
                        f"{attack_context_id}",
                        roll_type="attack_sequence.wound",
                        actor_id="player-a",
                    ),
                    value=4,
                ),
            ),
        ),
    )
    wound_payload = cast(
        dict[str, object],
        _attack_step_payload(
            _event_payloads(lifecycle, "attack_sequence_step"),
            AttackSequenceStep.WOUND,
        )["payload"],
    )

    assert remaining_sequence is None
    assert status is None
    assert wound_payload["toughness"] == 7
    assert wound_payload["target_number"] == 5
    assert wound_payload["successful"] is False


def test_phase14h_mustered_attached_unit_selects_to_shoot_as_one_rules_unit() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=(),
        alpha_unit_specs=_attached_enemy_unit_specs(),
        alpha_attachment_declarations=_attached_enemy_declarations(),
    )
    state = _state(lifecycle)
    formation = _attached_formation_for_player(state=state, player_id="player-a")
    attached_id = formation.attached_unit_instance_id
    bodyguard = units["bodyguard-unit"]
    leader = units["leader-unit"]
    support = units["support-unit"]

    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    unit_options = tuple(
        option
        for option in selection_request.options
        if option.option_id != COMPLETE_SHOOTING_PHASE_OPTION_ID
    )

    assert selection_request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE
    assert [option.option_id for option in unit_options] == [attached_id]
    assert bodyguard.unit_instance_id not in {option.option_id for option in unit_options}
    assert leader.unit_instance_id not in {option.option_id for option in unit_options}
    assert support.unit_instance_id not in {option.option_id for option in unit_options}

    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection_request,
        unit_instance_id=attached_id,
        selection_result_id="phase14h-attached-acting-select",
    )
    request_payload = cast(dict[str, object], declaration_request.payload)
    proposal_request = cast(dict[str, object], request_payload["proposal_request"])
    weapons = cast(list[dict[str, object]], proposal_request["available_weapons"])
    model_component_unit_ids = {
        model.model_instance_id: unit.unit_instance_id
        for unit in (bodyguard, leader, support)
        for model in unit.own_models
    }
    weapon_component_unit_ids = {
        model_component_unit_ids[cast(str, weapon["model_instance_id"])] for weapon in weapons
    }

    assert proposal_request["unit_instance_id"] == attached_id
    assert weapon_component_unit_ids == {bodyguard.unit_instance_id}

    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
    )
    status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=proposal.to_payload(),
        result_id="phase14h-attached-acting-declaration",
    )
    state = _state(lifecycle)
    shooting_state = state.shooting_phase_state

    assert status.status_kind in {
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.ADVANCED,
    }
    if shooting_state is not None:
        assert shooting_state.selected_unit_ids == (attached_id,)
        assert shooting_state.shot_unit_ids == (attached_id,)
        assert bodyguard.unit_instance_id not in shooting_state.shot_unit_ids
        assert leader.unit_instance_id not in shooting_state.shot_unit_ids
        assert support.unit_instance_id not in shooting_state.shot_unit_ids
        legal_shooting_unit_ids = _shooting_phase_private("_legal_shooting_unit_ids")
        assert (
            legal_shooting_unit_ids(
                state=state,
                shooting_state=shooting_state,
                ruleset_descriptor=_ruleset(),
                army_catalog=ArmyCatalog.phase9a_canonical_content_pack(),
            )
            == ()
        )
    else:
        selected_payload = _last_event_payload(lifecycle, "shooting_unit_selected")
        accepted_payload = _last_event_payload(lifecycle, "shooting_declaration_accepted")
        completed_payload = _last_event_payload(lifecycle, "shooting_phase_completed")
        assert selected_payload["unit_instance_id"] == attached_id
        assert accepted_payload["unit_instance_id"] == attached_id
        assert bodyguard.unit_instance_id != accepted_payload["unit_instance_id"]
        assert leader.unit_instance_id != accepted_payload["unit_instance_id"]
        assert support.unit_instance_id != accepted_payload["unit_instance_id"]
        assert completed_payload["skipped_unit_ids"] == []


def test_phase14h_attached_target_range_skips_destroyed_unplaced_components() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_specs=_attached_enemy_unit_specs(),
        enemy_attachment_declarations=_attached_enemy_declarations(),
    )
    state = _state(lifecycle)
    formation = _attached_formation_for_player(state=state, player_id="player-b")
    bodyguard = units["bodyguard-unit"]
    removed_bodyguard_ids = tuple(model.model_instance_id for model in bodyguard.own_models)
    _replace_unit_instance_in_state(
        state=state,
        replacement=replace(
            bodyguard,
            own_models=tuple(replace(model, wounds_remaining=0) for model in bodyguard.own_models),
        ),
    )
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.replace_battlefield_state(battlefield.with_removed_models(removed_bodyguard_ids))
    updated_battlefield = state.battlefield_state
    assert updated_battlefield is not None

    unit_target_within_max_range = _shooting_phase_private("_unit_target_within_max_range")

    assert unit_target_within_max_range(
        scenario=BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=updated_battlefield,
        ),
        unit=units["intercessor-1"],
        target_unit_id=formation.attached_unit_instance_id,
        range_inches=240,
    )


def test_phase14i_sustained_hits_slash_keyword_gate_controls_generated_hits() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = replace(units["enemy"], keywords=("INFANTRY",))
    _replace_unit_instance_in_state(state=state, replacement=defender)
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14i-sustained-hits-infantry-beasts-gate",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -6),
        keywords=(WeaponKeyword.SUSTAINED_HITS,),
        abilities=(AbilityDescriptor.sustained_hits(1, target_keywords=("INFANTRY/BEASTS",)),),
    )
    first_context_id = "phase14i-sustained-hits:pool-001:attack-001"
    generated_context_id = f"{first_context_id}:generated-hit-002"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {first_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    first_wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {first_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    generated_wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {generated_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    sequence = AttackSequence.start(
        sequence_id="phase14i-sustained-hits",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14i-sustained-hits",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14i-sustained-hits-hit",
                    spec=hit_spec,
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14i-sustained-hits-wound",
                    spec=first_wound_spec,
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14i-sustained-hits-generated-wound",
                    spec=generated_wound_spec,
                    value=6,
                ),
            ),
        ),
    )
    events = _event_payloads(lifecycle, "attack_sequence_step")
    hit_payload = _attack_step_payload(events, AttackSequenceStep.HIT)
    wound_events = [event for event in events if event["step"] == AttackSequenceStep.WOUND.value]

    assert remaining_sequence is None
    assert status is None
    assert cast(dict[str, object], hit_payload["payload"])["generated_hits"] == 2
    assert [event["attack_context_id"] for event in wound_events] == [
        first_context_id,
        generated_context_id,
    ]


def test_phase13d_twin_linked_consumes_reroll_semantics_once() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase13d-twin-linked",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -6),
        keywords=(WeaponKeyword.TWIN_LINKED,),
    )
    attack_context_id = "phase13d-twin-linked:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    reroll_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Reroll selected dice for {wound_spec.reason}",
        roll_type="attack_sequence.wound.reroll",
        actor_id="player-a",
    )
    dice_manager = DiceRollManager(
        "phase13d-twin-linked",
        event_log=lifecycle.decision_controller.event_log,
        injected_results=(
            _fixed_roll_result(roll_id="phase13d-twin-hit", spec=hit_spec, value=3),
            _fixed_roll_result(roll_id="phase13d-twin-wound", spec=wound_spec, value=1),
            _fixed_roll_result(roll_id="phase13d-twin-reroll", spec=reroll_spec, value=6),
        ),
    )
    sequence = AttackSequence.start(
        sequence_id="phase13d-twin-linked",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=dice_manager,
    )

    reroll_payload = _last_event_payload(lifecycle, "weapon_ability_reroll_resolved")
    assert remaining_sequence is None
    assert status is None
    assert cast(dict[str, object], reroll_payload["wound_roll"])["unmodified_roll"] == 6
    assert cast(dict[str, object], reroll_payload["wound_roll"])["successful"] is True
    assert len(_event_payloads(lifecycle, "weapon_ability_reroll_resolved")) == 1


def test_phase14f_indirect_fire_targets_unseen_units_and_unmodified_one_to_five_fail() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=attacker,
        army_id="army-alpha",
        player_id="player-a",
        poses=(
            Pose.at(10.0, 35.0),
            Pose.at(0.0, 5.0),
            Pose.at(0.0, 7.0),
            Pose.at(0.0, 9.0),
            Pose.at(0.0, 11.0),
        ),
    )
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=defender,
        army_id="army-beta",
        player_id="player-b",
        poses=tuple(Pose.at(33.0 + index * 1.4, 35.0) for index in range(5)),
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase13d-indirect",
        keywords=(WeaponKeyword.INDIRECT_FIRE,),
        abilities=(),
    )
    blocking_ruin = _blocking_ruin()

    candidates = shooting_target_candidates_for_unit(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=weapon_profile,
        target_unit_ids=(defender.unit_instance_id,),
        terrain_features=(blocking_ruin,),
    )

    assert candidates[0].is_legal
    assert candidates[0].target_visible_model_ids == ()
    assert candidates[0].hit_roll_modifier == -1
    assert INDIRECT_FIRE_NO_VISIBLE_RULE_ID in candidates[0].targeting_rule_ids
    assert INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID in candidates[0].targeting_rule_ids
    torrent_profile = replace(
        weapon_profile,
        profile_id="phase13d-indirect-torrent",
        keywords=(WeaponKeyword.INDIRECT_FIRE, WeaponKeyword.TORRENT),
    )
    torrent_candidates = shooting_target_candidates_for_unit(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=torrent_profile,
        target_unit_ids=(defender.unit_instance_id,),
        terrain_features=(blocking_ruin,),
    )
    assert not torrent_candidates[0].is_legal
    assert torrent_candidates[0].violation_code is ShootingTargetViolationCode.NOT_VISIBLE

    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="Hit roll for phase13d-indirect attack phase13d-indirect:pool-001:attack-001",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
        reroll_forbidden_rule_ids=(INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,),
    )
    dice_manager = DiceRollManager(
        "phase13d-indirect",
        event_log=lifecycle.decision_controller.event_log,
        injected_results=(
            _fixed_roll_result(roll_id="phase13d-indirect-hit", spec=hit_spec, value=3),
        ),
    )
    pool = RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id=attacker.wargear_selections[0].wargear_ids[0],
        weapon_profile_id=weapon_profile.profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=defender.unit_instance_id,
        shooting_type=ShootingType.INDIRECT,
        attacks=1,
        target_visible_model_ids=(),
        target_in_range_model_ids=(defender.own_models[0].model_instance_id,),
        targeting_rule_ids=(INDIRECT_FIRE_NO_VISIBLE_RULE_ID, INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID),
    )
    sequence = AttackSequence.start(
        sequence_id="phase13d-indirect",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(pool,),
    )

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=dice_manager,
    )

    hit_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.HIT,
    )
    assert remaining_sequence is None
    assert status is None
    assert cast(dict[str, object], hit_payload["payload"])["minimum_unmodified_success"] == 6
    assert cast(dict[str, object], hit_payload["payload"])["successful"] is False


def test_phase14f_friendly_visibility_query_uses_real_los_evidence() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    observer = units["intercessor-1"]
    defender = units["enemy"]
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=observer,
        army_id="army-alpha",
        player_id="player-a",
        poses=tuple(Pose.at(10.0, 34.0 + index * 0.5) for index in range(5)),
    )
    scenario = _scenario_with_unit_pose(
        scenario=scenario,
        unit=defender,
        army_id="army-beta",
        player_id="player-b",
        poses=tuple(
            Pose.at(33.0 + index * 1.4, 34.0 + index * 0.5, facing_degrees=180.0)
            for index in range(5)
        ),
    )

    assert unit_has_line_of_sight_to_target(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        observing_unit=observer,
        target_unit_id=defender.unit_instance_id,
    )
    assert not unit_has_line_of_sight_to_target(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        observing_unit=observer,
        target_unit_id=defender.unit_instance_id,
        terrain_features=(_blocking_ruin(),),
    )

    unplaced_scenario = BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.without_unit_placement(
            defender.unit_instance_id
        ),
    )
    with pytest.raises(GameLifecycleError, match="requires placed units"):
        unit_has_line_of_sight_to_target(
            scenario=unplaced_scenario,
            ruleset_descriptor=_ruleset(),
            observing_unit=observer,
            target_unit_id=defender.unit_instance_id,
        )
    with pytest.raises(GameLifecycleError, match="requires a BattlefieldScenario"):
        unit_has_line_of_sight_to_target(
            scenario=cast(BattlefieldScenario, object()),
            ruleset_descriptor=_ruleset(),
            observing_unit=observer,
            target_unit_id=defender.unit_instance_id,
        )
    with pytest.raises(GameLifecycleError, match="requires a RulesetDescriptor"):
        unit_has_line_of_sight_to_target(
            scenario=scenario,
            ruleset_descriptor=cast(RulesetDescriptor, object()),
            observing_unit=observer,
            target_unit_id=defender.unit_instance_id,
        )
    with pytest.raises(GameLifecycleError, match="requires a UnitInstance"):
        unit_has_line_of_sight_to_target(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            observing_unit=cast(UnitInstance, object()),
            target_unit_id=defender.unit_instance_id,
        )
    with pytest.raises(GameLifecycleError, match="terrain_features must contain"):
        unit_has_line_of_sight_to_target(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            observing_unit=observer,
            target_unit_id=defender.unit_instance_id,
            terrain_features=cast(tuple[TerrainFeatureDefinition, ...], ("bad-terrain",)),
        )


def test_phase14f_shooting_type_tokens_are_fail_fast() -> None:
    assert shooting_type_from_token(ShootingType.SNAP) is ShootingType.SNAP
    assert validate_shooting_type_tuple(
        "test shooting_types",
        (ShootingType.SNAP, "normal"),
    ) == (ShootingType.NORMAL, ShootingType.SNAP)

    with pytest.raises(GameLifecycleError, match="must be a string"):
        shooting_type_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported shooting type token"):
        shooting_type_from_token("unsupported")
    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        validate_shooting_type_tuple("test shooting_types", ["normal"])
    with pytest.raises(GameLifecycleError, match="must not contain duplicates"):
        validate_shooting_type_tuple("test shooting_types", ("normal", ShootingType.NORMAL))


def test_phase14f_indirect_stationary_friendly_visibility_uses_one_to_three_fail() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14f-indirect-stationary-visible",
        keywords=(WeaponKeyword.INDIRECT_FIRE,),
        abilities=(),
    )
    sequence_id = "phase14f-indirect-stationary-visible"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
        reroll_forbidden_rule_ids=(INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,),
    )
    pool = RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id=attacker.wargear_selections[0].wargear_ids[0],
        weapon_profile_id=weapon_profile.profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=defender.unit_instance_id,
        shooting_type=ShootingType.INDIRECT,
        attacks=1,
        target_visible_model_ids=(),
        target_in_range_model_ids=(defender.own_models[0].model_instance_id,),
        targeting_rule_ids=(
            INDIRECT_FIRE_NO_VISIBLE_RULE_ID,
            INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,
            INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID,
        ),
    )

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=AttackSequence.start(
            sequence_id=sequence_id,
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(pool,),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:hit",
                    spec=hit_spec,
                    value=3,
                ),
            ),
        ),
    )

    hit_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.HIT,
    )
    assert remaining_sequence is None
    assert status is None
    hit = cast(dict[str, object], hit_payload["payload"])
    assert hit["minimum_unmodified_success"] == 4
    assert hit["unmodified_success_threshold_active"] is False
    assert hit["successful"] is False


def test_phase13d_fire_overwatch_hits_only_on_unmodified_sixes() -> None:
    for roll_value in (3, 4, 5, 6):
        lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
        state = _state(lifecycle)
        attacker = units["intercessor-1"]
        defender = units["enemy"]
        weapon_profile = replace(
            _first_weapon_profile(lifecycle, attacker),
            profile_id=f"phase13d-fire-overwatch-hit-{roll_value}",
            skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
        )
        sequence_id = f"phase13d-fire-overwatch-hit-{roll_value}"
        attack_context_id = f"{sequence_id}:pool-001:attack-001"
        hit_spec = DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
            roll_type="attack_sequence.hit",
            actor_id="player-a",
            reroll_forbidden_rule_ids=(SNAP_SHOOTING_RULE_ID,),
        )
        wound_spec = DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
            roll_type="attack_sequence.wound",
            actor_id="player-a",
        )
        pool = replace(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
            shooting_type=ShootingType.SNAP,
            hit_roll_modifier=1,
            targeting_rule_ids=(FIRE_OVERWATCH_RULE_ID,),
        )

        resolve_attack_sequence_until_blocked(
            state=state,
            decisions=lifecycle.decision_controller,
            ruleset_descriptor=_ruleset(),
            attack_sequence=AttackSequence.start(
                sequence_id=sequence_id,
                attacker_player_id="player-a",
                attacking_unit_instance_id=attacker.unit_instance_id,
                attack_pools=(pool,),
            ),
            already_allocated_model_ids=(),
            dice_manager=DiceRollManager(
                sequence_id,
                event_log=lifecycle.decision_controller.event_log,
                injected_results=(
                    _fixed_roll_result(
                        roll_id=f"{sequence_id}:hit",
                        spec=hit_spec,
                        value=roll_value,
                    ),
                    _fixed_roll_result(
                        roll_id=f"{sequence_id}:wound",
                        spec=wound_spec,
                        value=1,
                    ),
                ),
            ),
        )

        hit_payload = _attack_step_payload(
            _event_payloads(lifecycle, "attack_sequence_step"),
            AttackSequenceStep.HIT,
        )
        hit = cast(dict[str, object], hit_payload["payload"])
        assert hit["minimum_unmodified_success"] == 6
        assert hit["unmodified_success_threshold_active"] is False
        assert hit["target_number"] == 3
        assert hit["modifier"] == 1
        assert hit["successful"] is (roll_value == 6)


def test_phase13d_generic_rule_ir_fire_overwatch_threshold_status_applies() -> None:
    cases = (
        (False, 5, 5),
        (True, 4, 4),
    )
    for support_near_target, roll_value, expected_minimum in cases:
        sequence_id = (
            "phase13d-generic-fire-overwatch-threshold-near"
            if support_near_target
            else "phase13d-generic-fire-overwatch-threshold-base"
        )
        lifecycle, units = _shooting_lifecycle(
            alpha_unit_ids=("intercessor-1", "intercessor-2"),
            game_id=sequence_id,
        )
        state = _state(lifecycle)
        attacker = units["intercessor-1"]
        support = replace(
            units["intercessor-2"],
            keywords=tuple(dict.fromkeys((*units["intercessor-2"].keywords, "PSYKER"))),
            faction_keywords=tuple(
                dict.fromkeys((*units["intercessor-2"].faction_keywords, "THOUSAND SONS"))
            ),
        )
        _replace_unit_instance_in_state(state=state, replacement=support)
        defender = units["enemy"]
        if support_near_target:
            assert state.battlefield_state is not None
            state.replace_battlefield_state(
                state.battlefield_state.with_unit_placement(
                    _unit_placement_at(
                        support,
                        army_id="army-alpha",
                        player_id="player-a",
                        poses=_compact_test_unit_poses(
                            origin=Pose.at(30.0, 35.0),
                            model_count=len(support.own_models),
                        ),
                    )
                )
            )
        weapon_profile = replace(
            _first_weapon_profile(lifecycle, attacker),
            profile_id=f"{sequence_id}-profile",
            skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 6),
        )
        state.record_persisting_effect(
            _generic_fire_overwatch_threshold_effect(
                effect_id=f"{sequence_id}:threshold-5",
                owner_player_id="player-a",
                target_unit_instance_ids=(attacker.unit_instance_id,),
                minimum_unmodified_success=5,
            )
        )
        state.record_persisting_effect(
            _generic_fire_overwatch_threshold_effect(
                effect_id=f"{sequence_id}:threshold-4",
                owner_player_id="player-a",
                target_unit_instance_ids=(attacker.unit_instance_id,),
                minimum_unmodified_success=4,
                proximity_required_keywords=("THOUSAND_SONS", "PSYKER"),
            )
        )
        attack_context_id = f"{sequence_id}:pool-001:attack-001"
        hit_spec = DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
            roll_type="attack_sequence.hit",
            actor_id="player-a",
            reroll_forbidden_rule_ids=(SNAP_SHOOTING_RULE_ID,),
        )
        wound_spec = DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
            roll_type="attack_sequence.wound",
            actor_id="player-a",
        )
        pool = replace(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
            shooting_type=ShootingType.SNAP,
            targeting_rule_ids=(FIRE_OVERWATCH_RULE_ID,),
        )

        resolve_attack_sequence_until_blocked(
            state=state,
            decisions=lifecycle.decision_controller,
            ruleset_descriptor=_ruleset(),
            attack_sequence=AttackSequence.start(
                sequence_id=sequence_id,
                attacker_player_id="player-a",
                attacking_unit_instance_id=attacker.unit_instance_id,
                attack_pools=(pool,),
            ),
            already_allocated_model_ids=(),
            dice_manager=DiceRollManager(
                sequence_id,
                event_log=lifecycle.decision_controller.event_log,
                injected_results=(
                    _fixed_roll_result(
                        roll_id=f"{sequence_id}:hit",
                        spec=hit_spec,
                        value=roll_value,
                    ),
                    _fixed_roll_result(
                        roll_id=f"{sequence_id}:wound",
                        spec=wound_spec,
                        value=1,
                    ),
                ),
            ),
        )

        hit_payload = _attack_step_payload(
            _event_payloads(lifecycle, "attack_sequence_step"),
            AttackSequenceStep.HIT,
        )
        hit = cast(dict[str, object], hit_payload["payload"])
        assert hit["minimum_unmodified_success"] == expected_minimum
        assert hit["unmodified_success_threshold_active"] is True
        assert hit["target_number"] == 6
        assert hit["modifier"] == 0
        assert hit["final_roll"] == roll_value
        assert hit["successful"] is True


def _generic_fire_overwatch_threshold_effect(
    *,
    effect_id: str,
    owner_player_id: str,
    target_unit_instance_ids: tuple[str, ...],
    minimum_unmodified_success: int,
    proximity_required_keywords: tuple[str, ...] = (),
) -> PersistingEffect:
    parameters: dict[str, JsonValue] = {
        "attack_role": "attacker",
        "minimum_unmodified_success": minimum_unmodified_success,
        "required_targeting_rule_id": FIRE_OVERWATCH_RULE_ID,
        "roll_type": "hit",
        "status": "minimum_unmodified_hit_success",
    }
    if proximity_required_keywords:
        parameters.update(
            {
                "target_proximity_distance_inches": 9,
                "target_proximity_required_keyword_sequence": list(proximity_required_keywords),
                "target_proximity_unit_allegiance": "friendly",
            }
        )
    parameter_payloads: list[dict[str, JsonValue]] = [
        {"key": key, "value": value} for key, value in sorted(parameters.items())
    ]
    return PersistingEffect(
        effect_id=effect_id,
        source_rule_id=f"source:{effect_id}",
        owner_player_id=owner_player_id,
        target_unit_instance_ids=target_unit_instance_ids,
        started_battle_round=1,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhase.SHOOTING,
            player_id=owner_player_id,
        ),
        effect_payload=validate_json_value(
            {
                "effect_kind": GENERIC_RULE_EFFECT_KIND,
                "rule_id": f"rule:{effect_id}",
                "source_id": f"source:{effect_id}",
                "rule_ir_hash": "0" * 64,
                "clause_id": f"clause:{effect_id}",
                "source_span": {"start": 0, "end": 1, "text": "x"},
                "target": {
                    "kind": "this_unit",
                    "source_span": {"start": 0, "end": 1, "text": "x"},
                    "parameters": [],
                },
                "target_unit_instance_ids": list(target_unit_instance_ids),
                "duration": None,
                "conditions": [],
                "effect": {
                    "kind": "set_contextual_status",
                    "source_span": {"start": 0, "end": 1, "text": "x"},
                    "parameters": parameter_payloads,
                },
                "context": {
                    "state": None,
                    "player_id": owner_player_id,
                    "phase": BattlePhase.SHOOTING.value,
                    "source_model_instance_id": None,
                },
            }
        ),
    )


def test_phase14f_snap_shooting_rule_hits_only_on_unmodified_sixes() -> None:
    for roll_value in (5, 6):
        lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
        state = _state(lifecycle)
        attacker = units["intercessor-1"]
        defender = units["enemy"]
        weapon_profile = replace(
            _first_weapon_profile(lifecycle, attacker),
            profile_id=f"phase14f-snap-hit-{roll_value}",
            skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 2),
        )
        sequence_id = f"phase14f-snap-hit-{roll_value}"
        attack_context_id = f"{sequence_id}:pool-001:attack-001"
        hit_spec = DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
            roll_type="attack_sequence.hit",
            actor_id="player-a",
            reroll_forbidden_rule_ids=(SNAP_SHOOTING_RULE_ID,),
        )
        wound_spec = DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
            roll_type="attack_sequence.wound",
            actor_id="player-a",
        )
        pool = replace(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
            shooting_type=ShootingType.SNAP,
            hit_roll_modifier=1,
            targeting_rule_ids=(SNAP_SHOOTING_RULE_ID,),
        )

        resolve_attack_sequence_until_blocked(
            state=state,
            decisions=lifecycle.decision_controller,
            ruleset_descriptor=_ruleset(),
            attack_sequence=AttackSequence.start(
                sequence_id=sequence_id,
                attacker_player_id="player-a",
                attacking_unit_instance_id=attacker.unit_instance_id,
                attack_pools=(pool,),
            ),
            already_allocated_model_ids=(),
            dice_manager=DiceRollManager(
                sequence_id,
                event_log=lifecycle.decision_controller.event_log,
                injected_results=(
                    _fixed_roll_result(
                        roll_id=f"{sequence_id}:hit",
                        spec=hit_spec,
                        value=roll_value,
                    ),
                    _fixed_roll_result(
                        roll_id=f"{sequence_id}:wound",
                        spec=wound_spec,
                        value=1,
                    ),
                ),
            ),
        )

        hit_payload = _attack_step_payload(
            _event_payloads(lifecycle, "attack_sequence_step"),
            AttackSequenceStep.HIT,
        )
        hit = cast(dict[str, object], hit_payload["payload"])
        assert hit["minimum_unmodified_success"] == 6
        assert hit["unmodified_success_threshold_active"] is False
        assert hit["target_number"] == 2
        assert hit["modifier"] == 1
        assert hit["successful"] is (roll_value == 6)


def test_phase13d_fire_overwatch_torrent_weapons_auto_hit() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase13d-fire-overwatch-torrent",
        keywords=(WeaponKeyword.TORRENT,),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 6),
    )
    sequence_id = "phase13d-fire-overwatch-torrent"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    pool = replace(
        _attack_pool_for_test(
            attacker=attacker,
            defender=defender,
            weapon_profile=weapon_profile,
            attacks=1,
        ),
        shooting_type=ShootingType.SNAP,
        targeting_rule_ids=(FIRE_OVERWATCH_RULE_ID,),
    )

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=AttackSequence.start(
            sequence_id=sequence_id,
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(pool,),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:wound",
                    spec=wound_spec,
                    value=1,
                ),
            ),
        ),
    )

    hit_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.HIT,
    )
    hit = cast(dict[str, object], hit_payload["payload"])
    assert remaining_sequence is None
    assert status is None
    assert hit["skipped"] is True
    assert hit["successful"] is True
    dice_events = [
        cast(dict[str, object], record.payload)
        for record in lifecycle.decision_controller.event_log.records
        if record.event_type == "dice_rolled"
    ]
    assert {
        cast(str, cast(dict[str, object], event["spec"])["roll_type"]) for event in dice_events
    } == {"attack_sequence.wound"}


@pytest.mark.parametrize(
    (
        "hazardous_roll_value",
        "extra_attacker_keywords",
        "expected_successful",
        "expected_mortal_wounds",
    ),
    [
        (1, (), False, 1),
        (2, (), False, 1),
        (3, (), True, 0),
        (1, ("Vehicle",), False, 3),
        (2, ("Vehicle",), False, 3),
        (1, ("Monster",), False, 3),
        (2, ("Monster",), False, 3),
        (3, ("Monster",), True, 0),
    ],
)
def test_phase13d_hazardous_tests_resolve_after_all_attacks(
    hazardous_roll_value: int,
    extra_attacker_keywords: tuple[str, ...],
    expected_successful: bool,
    expected_mortal_wounds: int,
) -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    if extra_attacker_keywords:
        attacker = replace(attacker, keywords=(*attacker.keywords, *extra_attacker_keywords))
        _replace_unit_instance_in_state(state=state, replacement=attacker)
    defender = units["enemy"]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase13d-hazardous",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -6),
        keywords=(WeaponKeyword.HAZARDOUS,),
    )
    attack_context_id = "phase13d-hazardous:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender.own_models[0].model_instance_id,
        attack_context_id=attack_context_id,
    )
    hazardous_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hazardous test for {attacker.unit_instance_id} after shooting",
        roll_type="hazardous_test",
        actor_id=attacker.unit_instance_id,
    )
    dice_manager = DiceRollManager(
        "phase13d-hazardous",
        event_log=lifecycle.decision_controller.event_log,
        injected_results=(
            _fixed_roll_result(roll_id="phase13d-hazardous-hit", spec=hit_spec, value=6),
            _fixed_roll_result(roll_id="phase13d-hazardous-wound", spec=wound_spec, value=6),
            _fixed_roll_result(roll_id="phase13d-hazardous-armour-save", spec=save_spec, value=1),
            _fixed_roll_result(
                roll_id="phase13d-hazardous-test",
                spec=hazardous_spec,
                value=hazardous_roll_value,
            ),
        ),
    )
    sequence = AttackSequence.start(
        sequence_id="phase13d-hazardous",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=dice_manager,
    )

    hazardous_payload = _last_event_payload(lifecycle, "hazardous_test_resolved")
    assert remaining_sequence is None
    assert status is None
    assert hazardous_payload["successful"] is expected_successful
    assert hazardous_payload["mortal_wounds"] == expected_mortal_wounds
    assert hazardous_payload["hazardous_weapon_profile_ids"] == ["phase13d-hazardous"]
    if expected_successful:
        assert hazardous_payload["mortal_wound_application"] is None
        assert hazardous_payload["pending_mortal_wound_request_id"] is None
        assert not _event_payloads(lifecycle, "hazardous_mortal_wounds_applied")
        return

    mortal_wound_application = cast(
        dict[str, object],
        hazardous_payload["mortal_wound_application"],
    )
    applications = cast(list[dict[str, object]], mortal_wound_application["applications"])
    applied_payload = _last_event_payload(lifecycle, "hazardous_mortal_wounds_applied")
    applied_application = cast(dict[str, object], applied_payload["mortal_wound_application"])
    assert hazardous_payload["pending_mortal_wound_request_id"] is None
    assert mortal_wound_application["target_unit_instance_id"] == attacker.unit_instance_id
    assert mortal_wound_application["mortal_wounds"] == expected_mortal_wounds
    assert applied_payload["mortal_wounds"] == expected_mortal_wounds
    assert applied_application == mortal_wound_application
    assert sum(cast(int, application["wounds_lost"]) for application in applications) == (
        expected_mortal_wounds
    )
    assert applications[0]["target_unit_instance_id"] == attacker.unit_instance_id
    assert applications[0]["model_instance_id"] == attacker.own_models[0].model_instance_id


def test_phase14c_hazardous_mortal_wounds_route_optional_fnp_through_lifecycle() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    attacker_model = attacker.own_models[0]
    source = FeelNoPainSource(source_id="phase14c-hazardous-fnp", threshold=5)
    state.record_model_feel_no_pain_sources(
        model_instance_id=attacker_model.model_instance_id,
        sources=(source,),
        decline_allowed=True,
    )
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14c-hazardous-fnp",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -6),
        keywords=(WeaponKeyword.HAZARDOUS,),
    )
    attack_context_id = "phase14c-hazardous-fnp:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender.own_models[0].model_instance_id,
        attack_context_id=attack_context_id,
    )
    hazardous_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hazardous test for {attacker.unit_instance_id} after shooting",
        roll_type="hazardous_test",
        actor_id=attacker.unit_instance_id,
    )
    dice_manager = DiceRollManager(
        "phase14c-hazardous-fnp",
        event_log=lifecycle.decision_controller.event_log,
        injected_results=(
            _fixed_roll_result(roll_id="phase14c-hazardous-fnp-hit", spec=hit_spec, value=6),
            _fixed_roll_result(roll_id="phase14c-hazardous-fnp-wound", spec=wound_spec, value=6),
            _fixed_roll_result(
                roll_id="phase14c-hazardous-fnp-armour-save",
                spec=save_spec,
                value=1,
            ),
            _fixed_roll_result(
                roll_id="phase14c-hazardous-fnp-test",
                spec=hazardous_spec,
                value=2,
            ),
        ),
    )
    sequence = AttackSequence.start(
        sequence_id="phase14c-hazardous-fnp",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=sequence.attack_pools,
        attack_sequence=sequence,
    )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=dice_manager,
    )
    request = _decision_request(cast(LifecycleStatus, status))
    hazardous_payload = _last_event_payload(lifecycle, "hazardous_test_resolved")

    assert remaining_sequence is not None
    assert allocated_ids == (defender.own_models[0].model_instance_id,)
    assert request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
    assert {option.option_id for option in request.options} == {"decline", source.source_id}
    assert hazardous_payload["successful"] is False
    assert hazardous_payload["mortal_wounds"] == 1
    assert hazardous_payload["mortal_wound_application"] is None
    assert hazardous_payload["pending_mortal_wound_request_id"] == request.request_id
    assert not _event_payloads(lifecycle, "hazardous_mortal_wounds_applied")
    assert model_by_id(state=state, model_instance_id=attacker_model.model_instance_id) == (
        attacker_model
    )

    current_shooting_state = state.shooting_phase_state
    assert current_shooting_state is not None
    state.shooting_phase_state = current_shooting_state.with_attack_sequence_update(
        attack_sequence=remaining_sequence,
        allocated_model_ids_this_phase=allocated_ids,
    )
    lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase14c-hazardous-fnp-decline",
            request=request,
            selected_option_id="decline",
        )
    )
    applied_payload = _last_event_payload(lifecycle, "hazardous_mortal_wounds_applied")
    applied_application = cast(dict[str, object], applied_payload["mortal_wound_application"])
    applications = cast(list[dict[str, object]], applied_application["applications"])
    updated_model = model_by_id(state=state, model_instance_id=attacker_model.model_instance_id)

    assert applied_payload["mortal_wounds"] == 1
    assert applications[0]["target_unit_instance_id"] == attacker.unit_instance_id
    assert applications[0]["model_instance_id"] == attacker_model.model_instance_id
    assert updated_model.wounds_remaining == attacker_model.wounds_remaining - 1
    assert state.shooting_phase_state is None


def test_phase13c_wound_roll_table_uses_integer_safe_boundaries() -> None:
    assert wound_roll_target_number(strength=8, toughness=4) == 2
    assert wound_roll_target_number(strength=7, toughness=4) == 3
    assert wound_roll_target_number(strength=4, toughness=4) == 4
    assert wound_roll_target_number(strength=3, toughness=4) == 5
    assert wound_roll_target_number(strength=2, toughness=4) == 6
    assert wound_roll_target_number(strength=10, toughness=5) == 2
    assert wound_roll_target_number(strength=9, toughness=5) == 3
    assert wound_roll_target_number(strength=2, toughness=5) == 6
    assert wound_roll_target_number(strength=3, toughness=5) == 5


def test_phase13c_attached_character_wounded_by_attacker_constraint_is_not_forced_later() -> None:
    base_context = AttackAllocationRuleContext(
        target_unit_instance_id="attached-unit",
        alive_model_ids=("bodyguard-1", "character-1"),
        wounded_model_ids=("character-1",),
        already_allocated_model_ids=("character-1",),
        attached_unit_bodyguard_model_ids=("bodyguard-1",),
        attached_unit_character_model_ids=("character-1",),
    )

    assert base_context.legal_model_ids() == ("bodyguard-1",)

    constrained_context = AttackAllocationRuleContext(
        target_unit_instance_id="attached-unit",
        alive_model_ids=("bodyguard-1", "character-1"),
        wounded_model_ids=(),
        already_allocated_model_ids=(),
        attached_unit_bodyguard_model_ids=("bodyguard-1",),
        attached_unit_character_model_ids=("character-1",),
        attacker_constraint=AttackAllocationConstraint(
            source_rule_ids=("attacker-allocation-constraint",),
            allowed_model_ids=("character-1",),
            can_allocate_protected_characters=True,
            attacker_selected_model_id="character-1",
        ),
    )

    assert constrained_context.legal_model_ids() == ("character-1",)


def test_phase13c_attached_unit_roles_require_runtime_keyword_not_identifier_prefix() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    defender = units["enemy"]
    prefixed_unit_id = "attached-unit:enemy"
    bodyguard_model = replace(
        defender.own_models[0],
        model_instance_id=f"{prefixed_unit_id}:bodyguard",
    )
    character_model = replace(
        defender.own_models[1],
        model_instance_id=f"{prefixed_unit_id}:character",
        source_ids=tuple(
            sorted(
                {
                    *defender.own_models[1].source_ids,
                    "attached-role:character",
                    "datasheet:core-character-leader",
                }
            )
        ),
    )
    prefixed_defender = replace(
        defender,
        unit_instance_id=prefixed_unit_id,
        own_models=(bodyguard_model, character_model),
    )
    state.army_definitions = [
        (
            replace(army, army_id="attached-unit", units=(prefixed_defender,))
            if army.player_id == "player-b"
            else army
        )
        for army in state.army_definitions
    ]
    battlefield = state.battlefield_state
    assert battlefield is not None
    old_placement = battlefield.unit_placement_by_id(defender.unit_instance_id)
    model_placements = tuple(
        ModelPlacement(
            army_id="attached-unit",
            player_id="player-b",
            unit_instance_id=prefixed_unit_id,
            model_instance_id=model.model_instance_id,
            pose=old_model_placement.pose,
        )
        for model, old_model_placement in zip(
            prefixed_defender.own_models,
            old_placement.model_placements[: len(prefixed_defender.own_models)],
            strict=True,
        )
    )
    state.battlefield_state = BattlefieldRuntimeState(
        battlefield_id=battlefield.battlefield_id,
        battlefield_width_inches=battlefield.battlefield_width_inches,
        battlefield_depth_inches=battlefield.battlefield_depth_inches,
        terrain_features=battlefield.terrain_features,
        placed_armies=tuple(
            (
                PlacedArmy(
                    army_id="attached-unit",
                    player_id="player-b",
                    unit_placements=(
                        UnitPlacement(
                            army_id="attached-unit",
                            player_id="player-b",
                            unit_instance_id=prefixed_unit_id,
                            model_placements=model_placements,
                        ),
                    ),
                )
                if placed_army.player_id == "player-b"
                else placed_army
            )
            for placed_army in battlefield.placed_armies
        ),
        removed_model_ids=battlefield.removed_model_ids,
    )

    context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=prefixed_unit_id,
    )

    assert context.attached_unit_bodyguard_model_ids == ()
    assert context.attached_unit_character_model_ids == ()


def test_phase14e_benefit_of_cover_does_not_modify_saves() -> None:
    _lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    model = units["enemy"].own_models[0]
    cover_result = _benefit_of_cover_result()

    ap_zero_options = save_options_for_model(
        model=model,
        armor_penetration=0,
        cover_result=cover_result,
    )
    ap_zero_armour = next(
        option for option in ap_zero_options if option.save_kind is SaveKind.ARMOUR
    )

    assert ap_zero_armour.cover_applied is False
    assert ap_zero_armour.source_rule_ids == ()
    assert ap_zero_armour.target_number == ap_zero_armour.characteristic_target_number

    ap_minus_one_options = save_options_for_model(
        model=model,
        armor_penetration=-1,
        cover_result=cover_result,
    )
    ap_minus_one_armour = next(
        option for option in ap_minus_one_options if option.save_kind is SaveKind.ARMOUR
    )

    assert ap_minus_one_armour.cover_applied is False
    assert ap_minus_one_armour.source_rule_ids == ()
    assert ap_minus_one_armour.target_number == (
        ap_minus_one_armour.characteristic_target_number + 1
    )


def test_phase14i_impossible_save_options_are_not_filtered_out() -> None:
    _lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    model = units["enemy"].own_models[0]

    save_options = save_options_for_model(
        model=model,
        armor_penetration=-6,
    )
    armour_option = next(option for option in save_options if option.save_kind is SaveKind.ARMOUR)

    assert armour_option.target_number == 9
    assert armour_option.can_succeed_on_d6 is False
    assert mandatory_save_option(options=save_options) == armour_option
    assert (
        save_options_for_model(
            model=model,
            armor_penetration=-6,
            no_saves_allowed=True,
        )
        == ()
    )


def test_phase14e_invulnerable_and_armour_save_checks_have_no_save_kind_decision() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = _model_with_characteristic(
        defender.own_models[0],
        characteristic=Characteristic.INVULNERABLE_SAVE,
        raw_value=4,
    )
    _replace_unit_instance_in_state(
        state=state,
        replacement=replace(defender, own_models=(defender_model, *defender.own_models[1:])),
    )
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    weapon_profile = _first_weapon_profile(lifecycle, attacker)
    attack_context_id = "phase14e-mandatory-invulnerable:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.INVULNERABLE,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )

    resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=AttackSequence.start(
            sequence_id="phase14e-mandatory-invulnerable",
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14e-mandatory-invulnerable",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14e-invulnerable-hit",
                    spec=hit_spec,
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14e-invulnerable-wound",
                    spec=wound_spec,
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14e-invulnerable-save",
                    spec=save_spec,
                    value=3,
                ),
            ),
        ),
    )
    save_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.SAVE,
    )
    payload = cast(dict[str, object], save_payload["payload"])

    option = cast(dict[str, object], payload["option"])

    assert payload["save_kind"] == SaveKind.ARMOUR.value
    assert payload["target_number"] == 3
    assert payload["final_roll"] == 2
    assert payload["successful"] is False
    assert payload["resolution_rule"] == SaveResolutionRule.FAILED.value
    assert option["save_kind"] == SaveKind.ARMOUR.value
    assert option["target_number"] == 4
    retired_save_choice_type = "select_" + "saving_throw_kind"
    assert not any(
        event.event_type == "decision_requested"
        and cast(dict[str, object], event.payload)["decision_type"] == retired_save_choice_type
        for event in lifecycle.decision_controller.event_log.records
    )


def test_phase14e_armour_save_can_succeed_after_invulnerable_save_fails() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = _model_with_characteristic(
        defender.own_models[0],
        characteristic=Characteristic.INVULNERABLE_SAVE,
        raw_value=5,
    )
    defender = replace(defender, own_models=(defender_model, *defender.own_models[1:]))
    _replace_unit_instance_in_state(state=state, replacement=defender)
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14e-ordered-save-check",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
    )
    attack_context_id = "phase14e-ordered-save-check:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.INVULNERABLE,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=AttackSequence.start(
            sequence_id="phase14e-ordered-save-check",
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14e-ordered-save-check",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14e-ordered-save-hit",
                    spec=hit_spec,
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14e-ordered-save-wound",
                    spec=wound_spec,
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14e-ordered-save-save",
                    spec=save_spec,
                    value=4,
                ),
            ),
        ),
    )
    save_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.SAVE,
    )
    payload = cast(dict[str, object], save_payload["payload"])
    option = cast(dict[str, object], payload["option"])
    save_options = cast(list[dict[str, object]], payload["save_options"])
    damage_payload = _attack_step_payload(
        tuple(
            event
            for event in _event_payloads(lifecycle, "attack_sequence_step")
            if event["step"] == AttackSequenceStep.DAMAGE.value
        ),
        AttackSequenceStep.DAMAGE,
    )
    damage_event_payload = cast(dict[str, object], damage_payload["payload"])

    assert remaining_sequence is None
    assert status is None
    assert payload["save_kind"] == SaveKind.ARMOUR.value
    assert payload["target_number"] == 3
    assert payload["unmodified_roll"] == 4
    assert payload["final_roll"] == 4
    assert payload["successful"] is True
    assert payload["resolution_rule"] == SaveResolutionRule.ARMOUR_SAVE.value
    assert option["save_kind"] == SaveKind.ARMOUR.value
    assert option["target_number"] == 3
    assert [save_option["save_kind"] for save_option in save_options] == [
        SaveKind.ARMOUR.value,
        SaveKind.INVULNERABLE.value,
    ]
    assert [save_option["target_number"] for save_option in save_options] == [3, 5]
    assert save_options[0] == option
    assert damage_event_payload["damage_application"] is None


def test_phase14e_benefit_of_cover_worsens_ballistic_skill_before_hit_roll() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    state.record_persisting_effect(_phase13f_cover_effect(defender.unit_instance_id))
    weapon_profile = _first_weapon_profile(lifecycle, attacker)
    attack_context_id = "phase14e-cover-hit-skill:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )

    resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=AttackSequence.start(
            sequence_id="phase14e-cover-hit-skill",
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14e-cover-hit-skill",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14e-cover-hit",
                    spec=hit_spec,
                    value=3,
                ),
            ),
        ),
    )
    hit_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.HIT,
    )
    payload = cast(dict[str, object], hit_payload["payload"])

    assert payload["target_number"] == 4
    assert payload["modifier"] == 0
    assert payload["successful"] is False


def test_phase17_post_shoot_cover_denial_suppresses_cover_hit_penalty() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    state.record_persisting_effect(_phase13f_cover_effect(defender.unit_instance_id))
    state.record_persisting_effect(
        _phase17_post_shoot_cover_denial_effect(defender.unit_instance_id)
    )
    weapon_profile = _first_weapon_profile(lifecycle, attacker)
    attack_context_id = "phase17-cover-denial-hit-skill:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )

    resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=AttackSequence.start(
            sequence_id="phase17-cover-denial-hit-skill",
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase17-cover-denial-hit-skill",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase17-cover-denial-hit",
                    spec=hit_spec,
                    value=3,
                ),
            ),
        ),
    )
    hit_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.HIT,
    )
    payload = cast(dict[str, object], hit_payload["payload"])

    assert payload["target_number"] == 3
    assert payload["modifier"] == 0
    assert payload["successful"] is True


def test_phase17_post_shoot_cover_denial_suppresses_cover_save_eligibility() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase17-cover-denial-save-rifle",
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -1),
        damage_profile=DamageProfile.fixed(1),
    )
    cover_result = replace(
        _benefit_of_cover_result(),
        cover_effect=CoverEffect.SAVE_BONUS,
    )
    cover_armour_option = next(
        option
        for option in save_options_for_model(
            model=defender_model,
            armor_penetration=weapon_profile.armor_penetration.final,
            cover_result=cover_result,
        )
        if option.save_kind is SaveKind.ARMOUR
    )
    assert cover_armour_option.cover_applied is True
    assert cover_armour_option.target_number == cover_armour_option.characteristic_target_number

    state.record_persisting_effect(
        replace(
            _phase13f_cover_effect(defender.unit_instance_id),
            effect_id="phase17-save-cover-only",
            source_rule_id="core-stratagem:smokescreen",
            effect_payload={
                "effect_kind": SMOKESCREEN_EFFECT_KIND,
                "benefit_of_cover": True,
                "hit_roll_modifier": 0,
            },
        )
    )
    state.record_persisting_effect(
        _phase17_post_shoot_cover_denial_effect(defender.unit_instance_id)
    )
    base_ruleset = _ruleset()
    save_bonus_ruleset = replace(
        base_ruleset,
        terrain_visibility_policy=replace(
            base_ruleset.terrain_visibility_policy,
            cover_effect=CoverEffect.SAVE_BONUS,
            cover_policy=CoverPolicyDescriptor(cover_effect=CoverEffect.SAVE_BONUS),
        ),
        descriptor_hash="",
    )
    sequence_id = "phase17-cover-denial-save"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-a",
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )

    remaining_sequence, allocated_model_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=save_bonus_ruleset,
        attack_sequence=AttackSequence.start(
            sequence_id=sequence_id,
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id=f"{sequence_id}:hit", spec=hit_spec, value=6),
                _fixed_roll_result(roll_id=f"{sequence_id}:wound", spec=wound_spec, value=6),
                _fixed_roll_result(roll_id=f"{sequence_id}:save", spec=save_spec, value=3),
            ),
        ),
    )
    save_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.SAVE,
    )
    payload = cast(dict[str, object], save_payload["payload"])
    option = cast(dict[str, object], payload["option"])

    assert remaining_sequence is None
    assert allocated_model_ids == (defender_model.model_instance_id,)
    assert status is None
    assert payload["save_kind"] == SaveKind.ARMOUR.value
    assert payload["target_number"] == cover_armour_option.characteristic_target_number
    assert payload["unmodified_roll"] == 3
    assert payload["final_roll"] == 2
    assert payload["successful"] is False
    assert payload["resolution_rule"] == SaveResolutionRule.FAILED.value
    assert option["target_number"] == cover_armour_option.characteristic_target_number + 1
    assert (
        option["characteristic_target_number"] == cover_armour_option.characteristic_target_number
    )
    assert option["cover_result"] is None
    assert option["cover_applied"] is False
    assert option["source_rule_ids"] == []


def test_hit_roll_bonus_cap_applies_after_ballistic_skill_modifier() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    state.record_persisting_effect(_phase13f_cover_effect(defender.unit_instance_id))
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="bs-penalty-hit-roll-bonus-rifle",
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 4),
    )
    sequence_id = "bs-penalty-hit-roll-bonus"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-a",
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-a",
    )

    resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=AttackSequence.start(
            sequence_id=sequence_id,
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                replace(
                    _attack_pool_for_test(
                        attacker=attacker,
                        defender=defender,
                        weapon_profile=weapon_profile,
                        attacks=1,
                    ),
                    hit_roll_modifier=2,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id=f"{sequence_id}:hit", spec=hit_spec, value=4),
                _fixed_roll_result(roll_id=f"{sequence_id}:wound", spec=wound_spec, value=1),
            ),
        ),
    )
    hit_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.HIT,
    )
    payload = cast(dict[str, object], hit_payload["payload"])

    assert payload["target_number"] == 5
    assert payload["modifier"] == 2
    assert payload["capped_modifier"] == 1
    assert payload["final_roll"] == 5
    assert payload["successful"] is True


def test_psychic_attack_can_ignore_detrimental_skill_and_hit_roll_modifiers() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    state.record_persisting_effect(_phase13f_cover_effect(defender.unit_instance_id))
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="psychic-modifier-ignore-rifle",
        keywords=(WeaponKeyword.PSYCHIC,),
    )
    sequence_id = "psychic-modifier-ignore"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    dice_manager = DiceRollManager(
        sequence_id,
        event_log=lifecycle.decision_controller.event_log,
        injected_results=(
            _fixed_roll_result(roll_id=f"{sequence_id}:hit", spec=hit_spec, value=3),
            _fixed_roll_result(roll_id=f"{sequence_id}:wound", spec=wound_spec, value=1),
        ),
    )
    attack_sequence = AttackSequence.start(
        sequence_id=sequence_id,
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            replace(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
                hit_roll_modifier=-1,
            ),
        ),
    )

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=attack_sequence,
        already_allocated_model_ids=(),
        dice_manager=dice_manager,
    )
    assert status is not None
    request = _decision_request(status)
    assert request.decision_type == SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE
    assert cast(dict[str, object], request.payload)["skill_modifier"] == 1
    assert cast(dict[str, object], request.payload)["hit_roll_modifier"] == -1
    assert {option.option_id for option in request.options} >= {
        "keep-all-modifiers",
        "ignore-detrimental-modifiers",
    }

    lifecycle.decision_controller.submit_result(
        DecisionResult.for_request(
            result_id="psychic-modifier-ignore-selection",
            request=request,
            selected_option_id="ignore-detrimental-modifiers",
        )
    )
    completed_sequence, _allocated_ids, follow_up_status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=cast(AttackSequence, remaining_sequence),
        already_allocated_model_ids=(),
        dice_manager=dice_manager,
    )
    hit_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.HIT,
    )
    payload = cast(dict[str, object], hit_payload["payload"])

    assert completed_sequence is None
    assert follow_up_status is None
    assert payload["is_psychic_attack"] is True
    assert payload["target_number"] == 3
    assert payload["modifier"] == 0
    assert payload["successful"] is True


def test_psychic_attack_can_ignore_detrimental_modifiers_and_keep_hit_bonus() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    state.record_persisting_effect(_phase13f_cover_effect(defender.unit_instance_id))
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="psychic-ignore-detrimental-keep-hit-bonus-rifle",
        keywords=(WeaponKeyword.PSYCHIC,),
    )
    sequence_id = "psychic-ignore-detrimental-keep-hit-bonus"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    hit_spec = attack_sequence_hit_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-a",
    )
    wound_spec = attack_sequence_wound_roll_spec(
        weapon_profile_id=weapon_profile.profile_id,
        attack_context_id=attack_context_id,
        attacker_player_id="player-a",
    )
    dice_manager = DiceRollManager(
        sequence_id,
        event_log=lifecycle.decision_controller.event_log,
        injected_results=(
            _fixed_roll_result(roll_id=f"{sequence_id}:hit", spec=hit_spec, value=2),
            _fixed_roll_result(roll_id=f"{sequence_id}:wound", spec=wound_spec, value=1),
        ),
    )
    attack_sequence = AttackSequence.start(
        sequence_id=sequence_id,
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            replace(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
                hit_roll_modifier=2,
            ),
        ),
    )

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=attack_sequence,
        already_allocated_model_ids=(),
        dice_manager=dice_manager,
    )
    assert status is not None
    request = _decision_request(status)
    assert request.decision_type == SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE
    assert cast(dict[str, object], request.payload)["skill_modifier"] == 1
    assert cast(dict[str, object], request.payload)["hit_roll_modifier"] == 2
    option = request.option_by_id("ignore-detrimental-modifiers")
    option_payload = cast(dict[str, object], option.payload)
    assert option_payload["effective_skill_modifier"] == 0
    assert option_payload["effective_hit_roll_modifier"] == 2
    assert option_payload["ignored_skill_modifier"] == 1
    assert option_payload["ignored_hit_roll_modifier"] == 0

    lifecycle.decision_controller.submit_result(
        DecisionResult.for_request(
            result_id="psychic-ignore-detrimental-keep-hit-bonus-selection",
            request=request,
            selected_option_id="ignore-detrimental-modifiers",
        )
    )
    completed_sequence, _allocated_ids, follow_up_status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=cast(AttackSequence, remaining_sequence),
        already_allocated_model_ids=(),
        dice_manager=dice_manager,
    )
    hit_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.HIT,
    )
    payload = cast(dict[str, object], hit_payload["payload"])

    assert completed_sequence is None
    assert follow_up_status is None
    assert payload["is_psychic_attack"] is True
    assert payload["target_number"] == 3
    assert payload["modifier"] == 2
    assert payload["capped_modifier"] == 1
    assert payload["final_roll"] == 3
    assert payload["successful"] is True


def test_phase14e_plunging_fire_evidence_improves_ballistic_skill_before_hit_roll() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    assert state.battlefield_state is not None
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    base_scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    elevated_scenario = _scenario_with_unit_pose(
        scenario=base_scenario,
        unit=attacker,
        army_id="army-alpha",
        player_id="player-a",
        poses=_compact_test_unit_poses(origin=Pose.at(10.0, 35.0, 3.0), model_count=5),
    )
    plunging_ruin = TerrainFeatureDefinition(
        feature_id="phase14e-plunging-ruin",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=12.0,
        footprint_center_y_inches=35.0,
        footprint_width_inches=12.0,
        footprint_depth_inches=6.0,
        display_geometry=_display_geometry(
            center_x_inches=12.0,
            center_y_inches=35.0,
            width_inches=12.0,
            depth_inches=6.0,
        ),
        walls=(
            TerrainWallDefinition(
                wall_id="south-wall",
                center_x_inches=12.0,
                center_y_inches=32.2,
                bottom_z_inches=0.0,
                width_inches=12.0,
                depth_inches=0.2,
                height_inches=3.0,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="ground-floor",
                center_x_inches=12.0,
                center_y_inches=35.0,
                bottom_z_inches=0.0,
                width_inches=12.0,
                depth_inches=6.0,
                thickness_inches=0.1,
            ),
            TerrainFloorDefinition(
                floor_id="upper-floor",
                center_x_inches=12.0,
                center_y_inches=35.0,
                bottom_z_inches=3.0,
                width_inches=12.0,
                depth_inches=6.0,
                thickness_inches=0.1,
            ),
        ),
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14e-plunging-fire-rifle",
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 4),
    )

    candidates = shooting_target_candidates_for_unit(
        scenario=elevated_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=weapon_profile,
        target_unit_ids=(defender.unit_instance_id,),
        terrain_features=(plunging_ruin,),
    )
    plain_candidates = shooting_target_candidates_for_unit(
        scenario=base_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=weapon_profile,
        target_unit_ids=(defender.unit_instance_id,),
    )

    assert candidates[0].is_legal
    assert PLUNGING_FIRE_RULE_ID in candidates[0].targeting_rule_ids
    assert plain_candidates[0].is_legal
    assert PLUNGING_FIRE_RULE_ID not in plain_candidates[0].targeting_rule_ids

    towering_attacker = replace(attacker, keywords=(*attacker.keywords, "Towering"))
    towering_scenario = _scenario_with_replaced_unit(
        scenario=base_scenario,
        replacement=towering_attacker,
    )
    towering_scenario = _scenario_with_unit_pose(
        scenario=towering_scenario,
        unit=defender,
        army_id="army-beta",
        player_id="player-b",
        poses=_compact_test_unit_poses(origin=Pose.at(20.0, 35.0), model_count=5),
    )
    towering_candidates = shooting_target_candidates_for_unit(
        scenario=towering_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=towering_attacker,
        weapon_profile=weapon_profile,
        target_unit_ids=(defender.unit_instance_id,),
    )

    assert towering_candidates[0].is_legal
    assert PLUNGING_FIRE_RULE_ID in towering_candidates[0].targeting_rule_ids

    for label, targeting_rule_ids, expected_target_number, expected_successful in (
        ("with-plunging-fire", (PLUNGING_FIRE_RULE_ID,), 3, True),
        ("without-plunging-fire", (), 4, False),
    ):
        case_lifecycle, case_units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
        case_state = _state(case_lifecycle)
        case_attacker = case_units["intercessor-1"]
        case_defender = case_units["enemy"]
        case_profile = replace(
            _first_weapon_profile(case_lifecycle, case_attacker),
            profile_id=f"phase14e-plunging-fire-{label}",
            skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 4),
        )
        sequence_id = f"phase14e-plunging-fire-{label}"
        attack_context_id = f"{sequence_id}:pool-001:attack-001"
        hit_spec = DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Hit roll for {case_profile.profile_id} attack {attack_context_id}",
            roll_type="attack_sequence.hit",
            actor_id="player-a",
        )
        wound_spec = DiceRollSpec(
            expression=DiceExpression(quantity=1, sides=6),
            reason=f"Wound roll for {case_profile.profile_id} attack {attack_context_id}",
            roll_type="attack_sequence.wound",
            actor_id="player-a",
        )
        resolve_attack_sequence_until_blocked(
            state=case_state,
            decisions=case_lifecycle.decision_controller,
            ruleset_descriptor=_ruleset(),
            attack_sequence=AttackSequence.start(
                sequence_id=sequence_id,
                attacker_player_id="player-a",
                attacking_unit_instance_id=case_attacker.unit_instance_id,
                attack_pools=(
                    replace(
                        _attack_pool_for_test(
                            attacker=case_attacker,
                            defender=case_defender,
                            weapon_profile=case_profile,
                            attacks=1,
                        ),
                        targeting_rule_ids=targeting_rule_ids,
                    ),
                ),
            ),
            already_allocated_model_ids=(),
            dice_manager=DiceRollManager(
                sequence_id,
                event_log=case_lifecycle.decision_controller.event_log,
                injected_results=(
                    _fixed_roll_result(
                        roll_id=f"{sequence_id}:hit",
                        spec=hit_spec,
                        value=3,
                    ),
                    _fixed_roll_result(
                        roll_id=f"{sequence_id}:wound",
                        spec=wound_spec,
                        value=1,
                    ),
                ),
            ),
        )
        hit_payload = _attack_step_payload(
            _event_payloads(case_lifecycle, "attack_sequence_step"),
            AttackSequenceStep.HIT,
        )
        payload = cast(dict[str, object], hit_payload["payload"])

        assert payload["target_number"] == expected_target_number
        assert payload["modifier"] == 0
        assert payload["successful"] is expected_successful


def test_phase13c_no_ability_sequence_resolves_and_emits_ordered_hooks() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    weapon_profile = _first_weapon_profile(lifecycle, attacker)
    attack_context_id = "phase13c-sequence:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )
    dice_manager = DiceRollManager(
        "phase13c-fixed-dice",
        event_log=lifecycle.decision_controller.event_log,
        injected_results=(
            _fixed_roll_result(roll_id="phase13c-hit", spec=hit_spec, value=6),
            _fixed_roll_result(roll_id="phase13c-wound", spec=wound_spec, value=6),
            _fixed_roll_result(roll_id="phase13c-save", spec=save_spec, value=1),
        ),
    )
    pool = RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id=attacker.wargear_selections[0].wargear_ids[0],
        weapon_profile_id=weapon_profile.profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=defender.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=(defender_model.model_instance_id,),
        target_in_range_model_ids=(defender_model.model_instance_id,),
    )
    sequence = AttackSequence.start(
        sequence_id="phase13c-sequence",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(pool,),
    )
    emitted_steps: list[AttackSequenceStep] = []

    def record_no_op(event: AttackSequenceEvent) -> AttackSequenceEvent:
        emitted_steps.append(event.step)
        return event

    remaining_sequence, allocated_model_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        hooks=AttackSequenceHooks(handlers=(record_no_op,)),
        dice_manager=dice_manager,
    )

    assert remaining_sequence is None
    assert status is None
    assert allocated_model_ids == (defender_model.model_instance_id,)
    assert emitted_steps == [
        AttackSequenceStep.HIT,
        AttackSequenceStep.CRITICAL_HIT,
        AttackSequenceStep.WOUND,
        AttackSequenceStep.CRITICAL_WOUND,
        AttackSequenceStep.ALLOCATE,
        AttackSequenceStep.SAVE,
        AttackSequenceStep.DAMAGE,
    ]
    encoded_events = json.dumps(
        lifecycle.decision_controller.event_log.to_payload(),
        sort_keys=True,
    )
    assert "<" not in encoded_events
    assert "object at 0x" not in encoded_events


def test_phase13c_random_damage_is_not_rolled_for_saved_attacks() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        damage_profile=DamageProfile.dice(DiceExpression(quantity=1, sides=3)),
    )
    attack_context_id = "phase13c-random-damage-saved:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )
    dice_manager = DiceRollManager(
        "phase13c-random-damage-saved",
        event_log=lifecycle.decision_controller.event_log,
        injected_results=(
            _fixed_roll_result(roll_id="phase13c-hit", spec=hit_spec, value=6),
            _fixed_roll_result(roll_id="phase13c-wound", spec=wound_spec, value=6),
            _fixed_roll_result(roll_id="phase13c-save", spec=save_spec, value=6),
        ),
    )
    sequence = AttackSequence.start(
        sequence_id="phase13c-random-damage-saved",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=dice_manager,
    )

    assert remaining_sequence is None
    assert status is None
    assert not any(
        record.event_type == "random_characteristic_rolled"
        and cast(dict[str, object], record.payload)["characteristic"] == "damage"
        for record in lifecycle.decision_controller.event_log.records
    )


def test_phase13c_random_damage_rolls_after_failed_save() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        damage_profile=DamageProfile.dice(DiceExpression(quantity=1, sides=3)),
    )
    attack_context_id = "phase13c-random-damage-failed:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )
    dice_manager = DiceRollManager(
        "phase13c-random-damage-failed",
        event_log=lifecycle.decision_controller.event_log,
        injected_results=(
            _fixed_roll_result(roll_id="phase13c-hit", spec=hit_spec, value=6),
            _fixed_roll_result(roll_id="phase13c-wound", spec=wound_spec, value=6),
            _fixed_roll_result(roll_id="phase13c-save", spec=save_spec, value=1),
        ),
    )
    sequence = AttackSequence.start(
        sequence_id="phase13c-random-damage-failed",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )

    resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=dice_manager,
    )

    events = lifecycle.decision_controller.event_log.records
    save_roll_index = next(
        index
        for index, record in enumerate(events)
        if record.event_type == "dice_rolled"
        and cast(
            str,
            cast(dict[str, object], cast(dict[str, object], record.payload)["spec"])["roll_type"],
        ).startswith("attack_sequence.save.")
    )
    damage_roll_index = next(
        index
        for index, record in enumerate(events)
        if record.event_type == "random_characteristic_rolled"
        and cast(dict[str, object], record.payload)["characteristic"] == "damage"
    )
    damage_event = next(
        record
        for record in events
        if record.event_type == "attack_sequence_step"
        and cast(dict[str, object], record.payload)["step"] == AttackSequenceStep.DAMAGE.value
    )
    damage_payload = cast(
        dict[str, object],
        cast(dict[str, object], damage_event.payload)["payload"],
    )
    application = cast(dict[str, object], damage_payload["damage_application"])
    random_damage = cast(dict[str, object], events[damage_roll_index].payload)["value"]

    assert save_roll_index < damage_roll_index
    assert application["requested_damage"] == random_damage


def test_phase13c_attack_payloads_hooks_and_fast_dice_groups() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    weapon_profile = _first_weapon_profile(lifecycle, attacker)
    base_pool = _attack_pool_for_test(
        attacker=attacker,
        defender=defender,
        weapon_profile=weapon_profile,
        attacks=2,
    )
    sequence = AttackSequence.start(
        sequence_id="phase13c-payload-sequence",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(base_pool,),
    )

    assert AttackSequence.from_payload(sequence.to_payload()) == sequence
    deferred = DeferredMortalWounds(
        source_rule_id="devastating_wounds",
        target_unit_instance_id=defender.unit_instance_id,
        attack_context_id=sequence.attack_context_id(),
        mortal_wounds=2,
    )
    assert DeferredMortalWounds.from_payload(deferred.to_payload()) == deferred
    sequence_with_deferred = sequence.with_deferred_mortal_wounds(deferred)
    assert (
        AttackSequence.from_payload(sequence_with_deferred.to_payload()) == sequence_with_deferred
    )
    assert sequence_with_deferred.advanced_after_attack().deferred_mortal_wounds == (deferred,)
    with pytest.raises(GameLifecycleError, match="deferred mortal wounds are invalid"):
        sequence.with_deferred_mortal_wounds(cast(DeferredMortalWounds, object()))
    with pytest.raises(GameLifecycleError, match="deferred_mortal_wounds must be a tuple"):
        AttackSequence(
            sequence_id=sequence.sequence_id,
            attacker_player_id=sequence.attacker_player_id,
            attacking_unit_instance_id=sequence.attacking_unit_instance_id,
            attack_pools=sequence.attack_pools,
            deferred_mortal_wounds=cast(tuple[DeferredMortalWounds, ...], [deferred]),
        )
    with pytest.raises(GameLifecycleError, match="mortal_wounds"):
        DeferredMortalWounds(
            source_rule_id="devastating_wounds",
            target_unit_instance_id=defender.unit_instance_id,
            attack_context_id=sequence.attack_context_id(),
            mortal_wounds=0,
        )
    assert HitRoll.auto_hit(target_number=3).to_payload()["skipped"] is True

    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="phase13c wound payload fixture",
        roll_type="attack_sequence.wound.fixture",
        actor_id="player-a",
    )
    wound_roll_state = DiceRollManager("phase13c-wound-payload").roll_fixed(wound_spec, [5])
    wound_roll = WoundRoll(
        strength=4,
        toughness=4,
        target_number=4,
        roll_state=wound_roll_state,
        unmodified_roll=5,
        modifier=2,
        capped_modifier=1,
        final_roll=6,
        successful=True,
        critical=False,
    )
    assert wound_roll.to_payload()["capped_modifier"] == 1
    with pytest.raises(GameLifecycleError, match="target_number"):
        WoundRoll(
            strength=4,
            toughness=4,
            target_number=3,
            roll_state=wound_roll_state,
            unmodified_roll=5,
            modifier=0,
            capped_modifier=0,
            final_roll=5,
            successful=True,
            critical=False,
        )

    event = AttackSequenceEvent(
        step=AttackSequenceStep.HIT,
        sequence_id=sequence.sequence_id,
        attack_context_id=sequence.attack_context_id(),
        pool_index=0,
        attack_index=0,
        payload={"ok": True},
    )
    moved_event = AttackSequenceEvent(
        step=AttackSequenceStep.WOUND,
        sequence_id=sequence.sequence_id,
        attack_context_id=sequence.attack_context_id(),
        pool_index=0,
        attack_index=0,
        payload={"ok": True},
    )
    with pytest.raises(GameLifecycleError, match="timing windows"):
        AttackSequenceHooks(handlers=(lambda _event: moved_event,)).emit(event)

    def return_same_event(current: AttackSequenceEvent) -> AttackSequenceEvent:
        return current

    with pytest.raises(GameLifecycleError, match="handlers must be a tuple"):
        AttackSequenceHooks(
            handlers=cast(tuple[AttackSequenceEventHandler, ...], [return_same_event])
        )
    with pytest.raises(GameLifecycleError, match="handlers must be callable"):
        AttackSequenceHooks(handlers=(cast(AttackSequenceEventHandler, object()),))
    with pytest.raises(GameLifecycleError, match="emit requires an event"):
        AttackSequenceHooks.empty().emit(cast(AttackSequenceEvent, object()))

    def return_invalid_event(_event: AttackSequenceEvent) -> AttackSequenceEvent:
        return cast(AttackSequenceEvent, object())

    with pytest.raises(GameLifecycleError, match="hook must return"):
        AttackSequenceHooks(handlers=(return_invalid_event,)).emit(event)
    completed_sequence = AttackSequence(
        sequence_id=sequence.sequence_id,
        attacker_player_id=sequence.attacker_player_id,
        attacking_unit_instance_id=sequence.attacking_unit_instance_id,
        attack_pools=sequence.attack_pools,
        pool_index=len(sequence.attack_pools),
    )
    with pytest.raises(GameLifecycleError, match="cannot advance generated hits"):
        completed_sequence.advanced_after_generated_hit(HitRoll.auto_hit(target_number=3))
    with pytest.raises(GameLifecycleError, match="requires a HitRoll"):
        sequence.advanced_after_generated_hit(cast(HitRoll, object()))
    failed_hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="phase13c failed hit payload fixture",
        roll_type="attack_sequence.hit.fixture",
        actor_id="player-a",
    )
    failed_hit_state = DiceRollManager("phase13c-hit-payload").roll_fixed(failed_hit_spec, [1])
    failed_hit = HitRoll(
        target_number=3,
        roll_state=failed_hit_state,
        unmodified_roll=1,
        modifier=0,
        capped_modifier=0,
        final_roll=1,
        successful=False,
        critical=False,
    )
    with pytest.raises(GameLifecycleError, match="requires a successful hit"):
        sequence.advanced_after_generated_hit(failed_hit)

    assert (
        FastDiceGroup.evaluate(
            group_id="phase13c-fast-allowed",
            pools=(base_pool,),
            allocation_order_can_affect_random_damage=False,
        ).allowed
        is True
    )
    assert (
        FastDiceGroup.evaluate(
            group_id="phase13c-fast-empty",
            pools=(),
            allocation_order_can_affect_random_damage=False,
        ).reason
        == "empty_group"
    )

    other_target_pool = _attack_pool_for_test(
        attacker=attacker,
        defender=defender,
        weapon_profile=weapon_profile,
        target_unit_instance_id="other-target-unit",
        attacks=2,
    )
    assert (
        FastDiceGroup.evaluate(
            group_id="phase13c-fast-different",
            pools=(base_pool, other_target_pool),
            allocation_order_can_affect_random_damage=False,
        ).reason
        == "attack_characteristics_or_target_differ"
    )

    random_damage_profile = replace(
        weapon_profile,
        damage_profile=DamageProfile.dice(DiceExpression(quantity=1, sides=3)),
    )
    random_damage_pool = _attack_pool_for_test(
        attacker=attacker,
        defender=defender,
        weapon_profile=random_damage_profile,
        attacks=2,
    )
    assert (
        FastDiceGroup.evaluate(
            group_id="phase13c-fast-random-damage",
            pools=(random_damage_pool,),
            allocation_order_can_affect_random_damage=True,
        ).reason
        == "random_damage_order_can_affect_outcome"
    )


def test_phase14l_identical_attack_signature_and_gathered_group_payloads() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    base_profile = replace(_first_weapon_profile(lifecycle, attacker), keywords=(), abilities=())
    first_pool = _attack_pool_for_test(
        attacker=attacker,
        defender=defender,
        weapon_profile=base_profile,
        attacks=2,
    )
    second_pool = replace(
        first_pool,
        attacks=4,
    )
    sequence = AttackSequence.start(
        sequence_id="phase14l-identical-gather",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(first_pool, second_pool),
    )

    groups = gathered_attack_groups_for_target(
        attack_sequence=sequence,
        target_unit_instance_id=defender.unit_instance_id,
    )
    assert len(groups) == 1
    assert groups[0].total_attacks == 6
    assert groups[0].pool_indices == (0, 1)
    assert groups[0].group_id.startswith("attack-group:")
    assert groups[0].group_id.count(":") == 1
    assert "attacks" not in identical_attack_signature(first_pool).to_payload()
    assert groups[0].signature.attacker_model_instance_id == first_pool.attacker_model_instance_id
    assert groups[0].signature.target_visible_model_ids == first_pool.target_visible_model_ids
    assert groups[0].signature.target_in_range_model_ids == first_pool.target_in_range_model_ids
    assert IdenticalAttackSignature.from_payload(groups[0].signature.to_payload()) == (
        groups[0].signature
    )
    assert GatheredAttackGroup.from_payload(groups[0].to_payload()) == groups[0]
    synthetic_pool = (
        sequence.with_selected_target_unit(defender.unit_instance_id)
        .with_current_gathered_group(groups[0])
        .current_pool()
    )
    assert synthetic_pool.attacks == 6
    assert synthetic_pool.attacker_model_instance_id == first_pool.attacker_model_instance_id
    assert synthetic_pool.wargear_id == f"gathered-wargear:{groups[0].group_id}"
    assert synthetic_pool.weapon_profile_id == f"gathered-profile:{groups[0].group_id}"
    assert synthetic_pool.weapon_profile.profile_id == synthetic_pool.weapon_profile_id
    assert synthetic_pool.target_visible_model_ids == first_pool.target_visible_model_ids
    assert synthetic_pool.target_in_range_model_ids == first_pool.target_in_range_model_ids
    assert synthetic_pool.firing_deck_source_unit_instance_id is None
    assert synthetic_pool.firing_deck_source_model_instance_id is None

    strength_profile = replace(
        base_profile,
        profile_id="phase14l-different-strength",
        strength=CharacteristicValue.from_raw(
            Characteristic.STRENGTH,
            base_profile.strength.final + 1,
        ),
    )
    torrent_profile = replace(
        base_profile,
        profile_id="phase14l-torrent",
        keywords=(WeaponKeyword.TORRENT,),
    )
    lethal_profile = replace(
        base_profile,
        profile_id="phase14l-lethal",
        keywords=(WeaponKeyword.LETHAL_HITS,),
        abilities=(AbilityDescriptor.lethal_hits(),),
    )
    different_pools = (
        first_pool,
        replace(
            first_pool,
            attacker_model_instance_id=attacker.own_models[1].model_instance_id,
        ),
        replace(first_pool, target_visible_model_ids=(defender.own_models[0].model_instance_id,)),
        replace(first_pool, target_in_range_model_ids=(defender.own_models[0].model_instance_id,)),
        replace(
            first_pool,
            firing_deck_source_unit_instance_id="army-alpha:transport-1",
            firing_deck_source_model_instance_id="army-alpha:transport-1:model-001",
        ),
        replace(
            first_pool,
            weapon_profile_id=strength_profile.profile_id,
            weapon_profile=strength_profile,
        ),
        replace(first_pool, hit_roll_modifier=1),
        replace(
            first_pool,
            weapon_profile_id=torrent_profile.profile_id,
            weapon_profile=torrent_profile,
        ),
        replace(
            first_pool,
            weapon_profile_id=lethal_profile.profile_id,
            weapon_profile=lethal_profile,
        ),
    )
    signatures = {identical_attack_signature(pool) for pool in different_pools}
    assert len(signatures) == len(different_pools)
    matching_id_only_pools = (
        first_pool,
        replace(
            first_pool,
            wargear_id="phase14l-other-wargear",
            weapon_profile_id="phase14l-equal-profile-id",
            weapon_profile=replace(base_profile, profile_id="phase14l-equal-profile-id"),
        ),
    )
    assert len({identical_attack_signature(pool) for pool in matching_id_only_pools}) == 1


def test_phase14l_precision_visibility_provenance_prevents_unsafe_gathering() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = _replace_enemy_with_attached_character_fixture(state=state, defender=units["enemy"])
    bodyguard_model = defender.own_models[0]
    character_model = defender.own_models[1]
    precision_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14l-precision-visible-provenance",
        keywords=(WeaponKeyword.PRECISION,),
        abilities=(),
    )
    bodyguard_only_pool = _attack_pool_for_test(
        attacker=attacker,
        defender=defender,
        weapon_profile=precision_profile,
        attacks=1,
    )
    bodyguard_only_pool = replace(
        bodyguard_only_pool,
        target_visible_model_ids=(bodyguard_model.model_instance_id,),
        target_in_range_model_ids=(
            bodyguard_model.model_instance_id,
            character_model.model_instance_id,
        ),
    )
    character_visible_pool = replace(
        bodyguard_only_pool,
        target_visible_model_ids=(
            bodyguard_model.model_instance_id,
            character_model.model_instance_id,
        ),
    )
    sequence = AttackSequence.start(
        sequence_id="phase14l-precision-visible-provenance",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(bodyguard_only_pool, character_visible_pool),
    )

    groups = gathered_attack_groups_for_target(
        attack_sequence=sequence,
        target_unit_instance_id=defender.unit_instance_id,
    )

    assert len(groups) == 2
    assert {group.pool_indices for group in groups} == {(0,), (1,)}
    assert {group.signature.target_visible_model_ids for group in groups} == {
        (bodyguard_model.model_instance_id,),
        (bodyguard_model.model_instance_id, character_model.model_instance_id),
    }


def test_phase14l_attacker_observer_provenance_prevents_unsafe_cover_gathering() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14l-cover-observer-provenance",
        keywords=(),
        abilities=(),
    )
    first_pool = _attack_pool_for_test(
        attacker=attacker,
        defender=defender,
        weapon_profile=weapon_profile,
        attacks=1,
    )
    second_pool = replace(
        first_pool,
        attacker_model_instance_id=attacker.own_models[1].model_instance_id,
    )
    sequence = AttackSequence.start(
        sequence_id="phase14l-cover-observer-provenance",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(first_pool, second_pool),
    )

    groups = gathered_attack_groups_for_target(
        attack_sequence=sequence,
        target_unit_instance_id=defender.unit_instance_id,
    )

    assert len(groups) == 2
    assert {group.pool_indices for group in groups} == {(0,), (1,)}
    assert {group.signature.attacker_model_instance_id for group in groups} == {
        first_pool.attacker_model_instance_id,
        second_pool.attacker_model_instance_id,
    }


def test_phase14l_range_and_firing_deck_provenance_prevent_unsafe_gathering() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="phase14l-range-firing-deck-provenance",
        keywords=(),
        abilities=(),
    )
    first_pool = _attack_pool_for_test(
        attacker=attacker,
        defender=defender,
        weapon_profile=weapon_profile,
        attacks=1,
    )
    range_limited_pool = replace(
        first_pool,
        target_in_range_model_ids=(defender.own_models[0].model_instance_id,),
    )
    firing_deck_pool = replace(
        first_pool,
        firing_deck_source_unit_instance_id="army-alpha:transport-1",
        firing_deck_source_model_instance_id="army-alpha:transport-1:model-001",
    )
    sequence = AttackSequence.start(
        sequence_id="phase14l-range-firing-deck-provenance",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(first_pool, range_limited_pool, firing_deck_pool),
    )

    groups = gathered_attack_groups_for_target(
        attack_sequence=sequence,
        target_unit_instance_id=defender.unit_instance_id,
    )

    assert len(groups) == 3
    assert {group.pool_indices for group in groups} == {(0,), (1,), (2,)}
    assert {group.signature.target_in_range_model_ids for group in groups} == {
        first_pool.target_in_range_model_ids,
        range_limited_pool.target_in_range_model_ids,
    }
    assert any(group.signature.firing_deck_source_unit_instance_id is not None for group in groups)


def test_phase14l_shooting_test1_gathered_save_order_regression() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_pose=Pose.at(23.0, 35.0, facing_degrees=180.0),
        game_id="phase14l-shooting-test1",
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender = replace(
        defender,
        own_models=tuple(_phase14l_test1_target_model(model) for model in defender.own_models),
    )
    _replace_unit_instance_in_state(state=state, replacement=defender)
    base_profile = _first_weapon_profile(lifecycle, attacker)
    boltgun_profile = replace(
        base_profile,
        profile_id="phase14l-test1-bolt-identical",
        name="Phase 14L Test 1 boltgun",
        attack_profile=AttackProfile.fixed(2),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 3),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 4),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
        keywords=(),
        abilities=(),
    )
    bolt_pistol_profile = replace(
        boltgun_profile,
        profile_id="phase14l-test1-bolt-pistol",
        name="Phase 14L Test 1 bolt pistol",
        attack_profile=AttackProfile.fixed(1),
    )
    heavy_bolter_profile = replace(
        base_profile,
        profile_id="phase14l-test1-heavy-bolter",
        name="Phase 14L Test 1 heavy bolter",
        attack_profile=AttackProfile.fixed(3),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 4),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 5),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -1),
        damage_profile=DamageProfile.fixed(1),
        keywords=(),
        abilities=(),
    )
    target_model_ids = tuple(model.model_instance_id for model in defender.own_models)
    safe_attacker_model_id = attacker.own_models[0].model_instance_id
    bolt_pools = (
        RangedAttackPool(
            attacker_model_instance_id=safe_attacker_model_id,
            wargear_id="phase14l-test1-bolt-identical",
            weapon_profile_id=boltgun_profile.profile_id,
            weapon_profile=boltgun_profile,
            target_unit_instance_id=defender.unit_instance_id,
            shooting_type=ShootingType.NORMAL,
            attacks=2,
            target_visible_model_ids=target_model_ids,
            target_in_range_model_ids=target_model_ids,
        ),
        RangedAttackPool(
            attacker_model_instance_id=safe_attacker_model_id,
            wargear_id="phase14l-test1-bolt-identical",
            weapon_profile_id=boltgun_profile.profile_id,
            weapon_profile=boltgun_profile,
            target_unit_instance_id=defender.unit_instance_id,
            shooting_type=ShootingType.NORMAL,
            attacks=2,
            target_visible_model_ids=target_model_ids,
            target_in_range_model_ids=target_model_ids,
        ),
        RangedAttackPool(
            attacker_model_instance_id=safe_attacker_model_id,
            wargear_id="phase14l-test1-bolt-pistol",
            weapon_profile_id=bolt_pistol_profile.profile_id,
            weapon_profile=bolt_pistol_profile,
            target_unit_instance_id=defender.unit_instance_id,
            shooting_type=ShootingType.NORMAL,
            attacks=1,
            target_visible_model_ids=target_model_ids,
            target_in_range_model_ids=target_model_ids,
        ),
    )
    heavy_pool = RangedAttackPool(
        attacker_model_instance_id=safe_attacker_model_id,
        wargear_id="phase14l-test1-heavy-bolter",
        weapon_profile_id=heavy_bolter_profile.profile_id,
        weapon_profile=heavy_bolter_profile,
        target_unit_instance_id=defender.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=3,
        target_visible_model_ids=target_model_ids,
        target_in_range_model_ids=target_model_ids,
    )
    sequence = AttackSequence.start(
        sequence_id="phase14l-shooting-test1",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(*bolt_pools, heavy_pool),
    ).with_selected_target_unit(defender.unit_instance_id)
    groups = gathered_attack_groups_for_target(
        attack_sequence=sequence,
        target_unit_instance_id=defender.unit_instance_id,
    )
    bolt_group = next(group for group in groups if group.total_attacks == 5)
    heavy_group = next(group for group in groups if group.total_attacks == 3)

    assert len(groups) == 2
    assert bolt_group.pool_indices == (0, 1, 2)
    assert tuple(contribution.attacks for contribution in bolt_group.contributions) == (2, 2, 1)
    assert {contribution.weapon_profile_id for contribution in bolt_group.contributions} == {
        boltgun_profile.profile_id,
        bolt_pistol_profile.profile_id,
    }
    assert heavy_group.pool_indices == (3,)
    bolt_synthetic_profile = (
        sequence.with_current_gathered_group(bolt_group).current_pool().weapon_profile
    )

    manager = DiceRollManager(
        "phase14l-shooting-test1",
        event_log=lifecycle.decision_controller.event_log,
        injected_results=_phase14l_test1_dice_results(
            bolt_profile=bolt_synthetic_profile,
            heavy_profile=heavy_bolter_profile,
            first_save_model_id=target_model_ids[0],
            second_save_model_id=target_model_ids[1],
        ),
    )
    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence.with_current_gathered_group(bolt_group),
        already_allocated_model_ids=(),
        dice_manager=manager,
    )
    remaining_sequence, allocated_ids, status = _drain_damage_model_choices_with_manager(
        lifecycle=lifecycle,
        attack_sequence=remaining_sequence,
        allocated_ids=allocated_ids,
        status=status,
        dice_manager=manager,
        result_id_prefix="phase14l-shooting-test1-damage-model",
    )
    hit_payloads = _attack_step_payloads(lifecycle, AttackSequenceStep.HIT)
    wound_payloads = _attack_step_payloads(lifecycle, AttackSequenceStep.WOUND)
    save_payloads = _attack_step_payloads(lifecycle, AttackSequenceStep.SAVE)
    damage_payloads = _attack_step_payloads(lifecycle, AttackSequenceStep.DAMAGE)
    damage_applications = [
        cast(dict[str, object], event["payload"])["damage_application"]
        for event in damage_payloads
        if cast(dict[str, object], event["payload"])["damage_application"] is not None
    ]
    destroyed_payloads = _event_payloads(lifecycle, "model_destroyed")

    assert remaining_sequence is None
    assert status is None
    assert [
        cast(dict[str, object], event["payload"])["unmodified_roll"] for event in hit_payloads
    ] == [2, 4, 6, 4, 3, 4, 4, 2]
    assert [
        cast(dict[str, object], event["payload"])["weapon_profile_id"] for event in hit_payloads[:5]
    ] == [bolt_synthetic_profile.profile_id] * 5
    assert [
        cast(dict[str, object], event["payload"])["unmodified_roll"] for event in wound_payloads
    ] == [6, 3, 5, 1, 3, 6]
    assert [
        cast(dict[str, object], event["payload"])["unmodified_roll"] for event in save_payloads
    ] == [2, 4, 6, 3, 5]
    assert [event["attack_context_id"] for event in save_payloads] == [
        "phase14l-shooting-test1:pool-001:attack-004",
        "phase14l-shooting-test1:pool-001:attack-003",
        "phase14l-shooting-test1:pool-001:attack-002",
        "phase14l-shooting-test1:pool-004:attack-002",
        "phase14l-shooting-test1:pool-004:attack-001",
    ]
    assert [
        cast(dict[str, object], event["payload"])["resolution_rule"] for event in save_payloads
    ] == [
        SaveResolutionRule.FAILED.value,
        SaveResolutionRule.ARMOUR_SAVE.value,
        SaveResolutionRule.INVULNERABLE_SAVE.value,
        SaveResolutionRule.FAILED.value,
        SaveResolutionRule.INVULNERABLE_SAVE.value,
    ]
    assert [cast(dict[str, object], event["payload"])["final_roll"] for event in save_payloads] == [
        2,
        4,
        6,
        2,
        5,
    ]
    assert len(damage_applications) == 2
    assert [
        cast(dict[str, object], application)["destroyed"] for application in damage_applications
    ] == [True, True]
    assert {
        cast(dict[str, object], application)["model_instance_id"]
        for application in damage_applications
    } == {target_model_ids[0], target_model_ids[1]}
    assert {payload["model_instance_id"] for payload in destroyed_payloads} == {
        target_model_ids[0],
        target_model_ids[1],
    }
    assert len(_attack_step_payloads(lifecycle, AttackSequenceStep.CRITICAL_HIT)) == 1
    assert len(_attack_step_payloads(lifecycle, AttackSequenceStep.CRITICAL_WOUND)) == 2


def test_phase14l_gathered_attack_state_fails_fast_on_malformed_shapes() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        keywords=(),
        abilities=(),
    )
    pool = _attack_pool_for_test(
        attacker=attacker,
        defender=defender,
        weapon_profile=weapon_profile,
        attacks=2,
    )
    sequence = AttackSequence.start(
        sequence_id="phase14l-malformed-gather-state",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(pool,),
    ).with_selected_target_unit(defender.unit_instance_id)
    group = gathered_attack_groups_for_target(
        attack_sequence=sequence,
        target_unit_instance_id=defender.unit_instance_id,
    )[0]
    contribution = group.contributions[0]

    with pytest.raises(GameLifecycleError, match="hit_roll_modifier"):
        IdenticalAttackSignature(
            attacker_model_instance_id=group.signature.attacker_model_instance_id,
            target_visible_model_ids=group.signature.target_visible_model_ids,
            target_in_range_model_ids=group.signature.target_in_range_model_ids,
            hit_basis=group.signature.hit_basis,
            hit_roll_modifier=cast(Any, "0"),
            wound_roll_modifiers=group.signature.wound_roll_modifiers,
            strength=group.signature.strength,
            armor_penetration=group.signature.armor_penetration,
            damage=group.signature.damage,
            weapon_rule_tokens=group.signature.weapon_rule_tokens,
            targeting_rule_ids=group.signature.targeting_rule_ids,
            shooting_type=group.signature.shooting_type,
            firing_deck_source_unit_instance_id=(
                group.signature.firing_deck_source_unit_instance_id
            ),
            firing_deck_source_model_instance_id=(
                group.signature.firing_deck_source_model_instance_id
            ),
        )
    with pytest.raises(GameLifecycleError, match="Firing Deck source unit and model"):
        IdenticalAttackSignature(
            attacker_model_instance_id=group.signature.attacker_model_instance_id,
            target_visible_model_ids=group.signature.target_visible_model_ids,
            target_in_range_model_ids=group.signature.target_in_range_model_ids,
            hit_basis=group.signature.hit_basis,
            hit_roll_modifier=group.signature.hit_roll_modifier,
            wound_roll_modifiers=group.signature.wound_roll_modifiers,
            strength=group.signature.strength,
            armor_penetration=group.signature.armor_penetration,
            damage=group.signature.damage,
            weapon_rule_tokens=group.signature.weapon_rule_tokens,
            targeting_rule_ids=group.signature.targeting_rule_ids,
            shooting_type=group.signature.shooting_type,
            firing_deck_source_unit_instance_id="transport",
            firing_deck_source_model_instance_id=None,
        )
    with pytest.raises(GameLifecycleError, match="Firing Deck source unit and model"):
        type(contribution)(
            pool_index=contribution.pool_index,
            attacker_model_instance_id=contribution.attacker_model_instance_id,
            wargear_id=contribution.wargear_id,
            weapon_profile_id=contribution.weapon_profile_id,
            target_unit_instance_id=contribution.target_unit_instance_id,
            attacks=contribution.attacks,
            firing_deck_source_unit_instance_id="transport",
            firing_deck_source_model_instance_id=None,
        )
    with pytest.raises(GameLifecycleError, match="must be an IdenticalAttackSignature"):
        GatheredAttackGroup(
            group_id=group.group_id,
            target_unit_instance_id=group.target_unit_instance_id,
            signature=cast(Any, group.signature.to_payload()),
            pool_indices=group.pool_indices,
            total_attacks=group.total_attacks,
            contributions=group.contributions,
        )
    with pytest.raises(GameLifecycleError, match="total attacks drift"):
        GatheredAttackGroup(
            group_id=group.group_id,
            target_unit_instance_id=group.target_unit_instance_id,
            signature=group.signature,
            pool_indices=group.pool_indices,
            total_attacks=group.total_attacks + 1,
            contributions=group.contributions,
        )
    with pytest.raises(GameLifecycleError, match="contribution target drift"):
        GatheredAttackGroup(
            group_id=group.group_id,
            target_unit_instance_id=group.target_unit_instance_id,
            signature=group.signature,
            pool_indices=group.pool_indices,
            total_attacks=group.total_attacks,
            contributions=(
                replace(contribution, target_unit_instance_id="army-beta:other-target"),
            ),
        )
    with pytest.raises(GameLifecycleError, match="gathered group target drift"):
        AttackSequence(
            sequence_id=sequence.sequence_id,
            attacker_player_id=sequence.attacker_player_id,
            attacking_unit_instance_id=sequence.attacking_unit_instance_id,
            attack_pools=sequence.attack_pools,
            selected_target_unit_instance_id="army-beta:other-target",
            current_gathered_group=group,
            pool_index=group.primary_pool_index,
        )

    missing_descriptor_profile = replace(
        weapon_profile,
        profile_id="phase14l-missing-ability-descriptor",
        keywords=(WeaponKeyword.SUSTAINED_HITS,),
        abilities=(),
    )
    with pytest.raises(GameLifecycleError, match="structured ability descriptor"):
        identical_attack_signature(
            replace(
                pool,
                weapon_profile_id=missing_descriptor_profile.profile_id,
                weapon_profile=missing_descriptor_profile,
            )
        )


def test_phase14l_attack_sequence_round_trips_current_gathered_group_json_safe() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        keywords=(),
        abilities=(),
    )
    pool = _attack_pool_for_test(
        attacker=attacker,
        defender=defender,
        weapon_profile=weapon_profile,
        attacks=1,
    )
    sequence = AttackSequence.start(
        sequence_id="phase14l-round-trip",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(pool,),
    ).with_selected_target_unit(defender.unit_instance_id)
    group = gathered_attack_groups_for_target(
        attack_sequence=sequence,
        target_unit_instance_id=defender.unit_instance_id,
    )[0]
    sequence = sequence.with_current_gathered_group(group)

    encoded = json.loads(json.dumps(sequence.to_payload(), sort_keys=True))
    assert AttackSequence.from_payload(encoded) == sequence
    assert "object at 0x" not in json.dumps(encoded, sort_keys=True)


def test_phase14l_select_target_and_attack_group_branch_precedence_records() -> None:
    base_lifecycle, base_units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    base_profile = _first_weapon_profile(base_lifecycle, base_units["intercessor-1"])
    heavy_profile = replace(
        base_profile,
        profile_id="phase14l-heavy-bolt",
        strength=CharacteristicValue.from_raw(
            Characteristic.STRENGTH,
            base_profile.strength.final + 1,
        ),
    )
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_specs=(
            ("enemy-a", "core-intercessor-like-infantry", "core-intercessor-like", 5),
            ("enemy-b", "core-intercessor-like-infantry", "core-intercessor-like", 5),
        ),
        catalog=_catalog_with_extra_bolt_profile(heavy_profile),
        game_id="phase14l-branch-precedence",
    )
    first_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=first_request,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        selection_result_id="phase14l-branch-select-shooter",
    )
    declarations = _phase14l_multi_target_declarations(
        declaration_request=declaration_request,
        first_target_id=units["enemy-a"].unit_instance_id,
        second_target_id=units["enemy-b"].unit_instance_id,
        extra_profile_id=heavy_profile.profile_id,
    )
    proposal = _proposal_from_declarations(
        request=declaration_request,
        declarations=declarations,
    )
    target_request = _decision_request(
        _submit_payload(
            lifecycle,
            request=declaration_request,
            payload=proposal.to_payload(),
            result_id="phase14l-branch-declaration",
        )
    )

    assert target_request.decision_type == SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE
    assert {option.option_id for option in target_request.options} == {
        f"resolve-target:{units['enemy-a'].unit_instance_id}",
        f"resolve-target:{units['enemy-b'].unit_instance_id}",
    }
    group_request = _decision_request(
        _submit_result(
            lifecycle,
            request=target_request,
            option_id=f"resolve-target:{units['enemy-a'].unit_instance_id}",
            result_id="phase14l-branch-target-a",
        )
    )

    assert group_request.decision_type == SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE
    assert len(group_request.options) == 2
    after_first_group = _submit_result(
        lifecycle,
        request=group_request,
        option_id=group_request.options[0].option_id,
        result_id="phase14l-branch-first-group",
    )
    _submit_phase13f_pending_attack_choices(
        lifecycle,
        status=after_first_group,
        result_id_prefix="phase14l-branch-drain",
    )

    sequence_records = tuple(
        record
        for record in lifecycle.decision_controller.records
        if record.request.decision_type
        in {SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE, SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE}
    )
    target_order = tuple(
        cast(dict[str, object], record.result.payload)["target_unit_instance_id"]
        for record in sequence_records
        if record.request.decision_type == SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE
    )
    group_target_order = tuple(
        cast(dict[str, object], record.result.payload)["target_unit_instance_id"]
        for record in sequence_records
        if record.request.decision_type == SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE
    )

    assert target_order[:2] == (
        units["enemy-a"].unit_instance_id,
        units["enemy-b"].unit_instance_id,
    )
    assert group_target_order[:2] == (
        units["enemy-a"].unit_instance_id,
        units["enemy-a"].unit_instance_id,
    )
    assert any(record.result.result_id.endswith(":auto-result") for record in sequence_records)


def test_phase14l_single_target_and_group_auto_records_finite_choices() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    first_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=first_request,
        unit_instance_id=units["intercessor-1"].unit_instance_id,
        selection_result_id="phase14l-auto-select-shooter",
    )
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=units["enemy"].unit_instance_id,
    )

    _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=proposal.to_payload(),
        result_id="phase14l-auto-declaration",
    )

    auto_records = tuple(
        record
        for record in lifecycle.decision_controller.records
        if record.request.decision_type
        in {SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE, SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE}
    )
    assert tuple(record.request.decision_type for record in auto_records[:2]) == (
        SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
        SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
    )
    assert all(record.result.result_id.endswith(":auto-result") for record in auto_records[:2])


def test_phase14l_attack_sequence_selection_invalid_before_queue_pop() -> None:
    lifecycle, units, heavy_profile = _phase14l_multi_group_lifecycle(
        game_id="phase14l-invalid-before-pop"
    )
    target_request = _phase14l_submit_multi_group_declaration(
        lifecycle=lifecycle,
        units=units,
        heavy_profile=heavy_profile,
        result_prefix="phase14l-invalid",
    )
    before_records = len(lifecycle.decision_controller.records)

    malformed_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase14l-invalid-target-malformed",
            request_id=target_request.request_id,
            decision_type=target_request.decision_type,
            actor_id=target_request.actor_id,
            selected_option_id="not-a-real-option",
            payload={},
        )
    )

    assert malformed_status.status_kind is LifecycleStatusKind.INVALID
    assert len(lifecycle.decision_controller.records) == before_records
    assert lifecycle.decision_controller.queue.pending_requests == (target_request,)

    group_request = _decision_request(
        _submit_result(
            lifecycle,
            request=target_request,
            option_id=f"resolve-target:{units['enemy-a'].unit_instance_id}",
            result_id="phase14l-invalid-target-valid",
        )
    )
    before_group_records = len(lifecycle.decision_controller.records)
    state = _state(lifecycle)
    shooting_state = state.shooting_phase_state
    assert shooting_state is not None
    assert shooting_state.attack_sequence is not None
    state.shooting_phase_state = shooting_state.with_attack_sequence_update(
        attack_sequence=shooting_state.attack_sequence.without_selected_target_unit(),
        allocated_model_ids_this_phase=shooting_state.allocated_model_ids_this_phase,
    )

    drift_status = _submit_result(
        lifecycle,
        request=group_request,
        option_id=group_request.options[0].option_id,
        result_id="phase14l-invalid-group-drift",
    )

    assert drift_status.status_kind is LifecycleStatusKind.INVALID
    assert len(lifecycle.decision_controller.records) == before_group_records
    assert lifecycle.decision_controller.queue.pending_requests == (group_request,)


def test_phase13c_modifier_stack_host_payload_and_validation() -> None:
    attacks_stack = ModifierStack(characteristic=Characteristic.ATTACKS, raw_value=2)
    strength_stack = ModifierStack(characteristic=Characteristic.STRENGTH, raw_value=4)
    ap_stack = ModifierStack(characteristic=Characteristic.ARMOR_PENETRATION, raw_value=0)
    damage_stack = ModifierStack(characteristic=Characteristic.DAMAGE, raw_value=1)
    hit_penalty = RollModifier(modifier_id="hit-penalty", operand=-1, priority=2)
    hit_bonus = RollModifier(modifier_id="hit-bonus", operand=1, priority=1)
    wound_bonus = RollModifier(modifier_id="wound-bonus", operand=1)

    stack_set = AttackModifierStackSet(
        attacks=attacks_stack,
        strength=strength_stack,
        armor_penetration=ap_stack,
        damage=damage_stack,
        hit_roll_modifiers=(hit_penalty, hit_bonus),
        wound_roll_modifiers=(wound_bonus,),
    )

    payload = stack_set.to_payload()
    assert payload["attacks"] is not None
    assert payload["attacks"]["characteristic"] == "attacks"
    assert [modifier["modifier_id"] for modifier in payload["hit_roll_modifiers"]] == [
        "hit-bonus",
        "hit-penalty",
    ]
    assert attack_sequence_step_from_token(AttackSequenceStep.HIT) is AttackSequenceStep.HIT
    assert attack_sequence_step_from_token("damage") is AttackSequenceStep.DAMAGE

    with pytest.raises(GameLifecycleError, match="token must be a string"):
        attack_sequence_step_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported AttackSequenceStep"):
        attack_sequence_step_from_token("not-a-step")
    with pytest.raises(GameLifecycleError, match="stacks must be ModifierStack"):
        AttackModifierStackSet(attacks="bad")  # type: ignore[arg-type]
    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        AttackModifierStackSet(hit_roll_modifiers=[hit_bonus])  # type: ignore[arg-type]
    with pytest.raises(GameLifecycleError, match="RollModifier values"):
        AttackModifierStackSet(wound_roll_modifiers=("bad",))  # type: ignore[arg-type]
    with pytest.raises(GameLifecycleError, match="duplicate modifier IDs"):
        AttackModifierStackSet(hit_roll_modifiers=(hit_bonus, hit_bonus))


def test_phase13c_decision_payloads_validate_fail_fast() -> None:
    allocation_context = AttackAllocationRuleContext(
        target_unit_instance_id="target",
        alive_model_ids=("model-a", "model-b"),
    )
    allocation_context_payload = allocation_context.to_payload()
    assert (
        AttackAllocationRuleContext.from_payload(allocation_context_payload).to_payload()
        == allocation_context_payload
    )

    armour_option = SaveOption(
        save_kind=SaveKind.ARMOUR,
        target_number=3,
        characteristic_target_number=3,
        armor_penetration=0,
    )
    invulnerable_option = SaveOption(
        save_kind=SaveKind.INVULNERABLE,
        target_number=4,
        characteristic_target_number=4,
        armor_penetration=-2,
    )

    assert (
        mandatory_save_option(options=(armour_option, invulnerable_option)) == invulnerable_option
    )
    assert mandatory_save_option(options=(armour_option,)) == armour_option
    assert mandatory_save_option(options=()) is None


def test_phase14e_save_roll_checks_one_invulnerable_then_armour() -> None:
    armour_option = SaveOption(
        save_kind=SaveKind.ARMOUR,
        target_number=3,
        characteristic_target_number=3,
        armor_penetration=0,
    )
    invulnerable_option = SaveOption(
        save_kind=SaveKind.INVULNERABLE,
        target_number=5,
        characteristic_target_number=5,
        armor_penetration=0,
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.INVULNERABLE,
        player_id="player-b",
        allocated_model_id="model-a",
        attack_context_id="phase14e-ordered-save-helper",
    )
    manager = DiceRollManager("phase14e-ordered-save-helper")

    one = resolve_saving_throw(
        options=(armour_option, invulnerable_option),
        roll_state=manager.roll_fixed(save_spec, [1]),
    )
    invulnerable_success = resolve_saving_throw(
        options=(armour_option, invulnerable_option),
        roll_state=manager.roll_fixed(save_spec, [5]),
    )
    armour_success = resolve_saving_throw(
        options=(armour_option, invulnerable_option),
        roll_state=manager.roll_fixed(save_spec, [4]),
    )
    ap_failed_armour_option = SaveOption(
        save_kind=SaveKind.ARMOUR,
        target_number=6,
        characteristic_target_number=3,
        armor_penetration=-3,
    )
    ap_failure = resolve_saving_throw(
        options=(ap_failed_armour_option, invulnerable_option),
        roll_state=manager.roll_fixed(save_spec, [4]),
    )

    assert one.successful is False
    assert one.resolution_rule is SaveResolutionRule.UNMODIFIED_ONE
    assert one.save_kind is SaveKind.ARMOUR
    assert invulnerable_success.successful is True
    assert invulnerable_success.resolution_rule is SaveResolutionRule.INVULNERABLE_SAVE
    assert invulnerable_success.save_kind is SaveKind.INVULNERABLE
    assert armour_success.successful is True
    assert armour_success.resolution_rule is SaveResolutionRule.ARMOUR_SAVE
    assert armour_success.save_kind is SaveKind.ARMOUR
    assert armour_success.final_roll == 4
    assert ap_failure.successful is False
    assert ap_failure.resolution_rule is SaveResolutionRule.FAILED
    assert ap_failure.final_roll == 1


def test_phase14e_allocation_order_decision_payloads_validate_before_mutation() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    defender = units["enemy"]
    alternate_save_model = replace(
        defender.own_models[1],
        characteristics=tuple(
            CharacteristicValue.from_raw(Characteristic.SAVE, 4)
            if value.characteristic is Characteristic.SAVE
            else value
            for value in defender.own_models[1].characteristics
        ),
    )
    defender = replace(
        defender,
        own_models=(defender.own_models[0], alternate_save_model, *defender.own_models[2:]),
    )
    _replace_unit_instance_in_state(state=state, replacement=defender)
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=defender.unit_instance_id,
    )
    allocation_groups = allocation_groups_for_context(
        state=state,
        allocation_context=allocation_context,
    )
    request = build_allocation_order_request(
        request_id="phase14e-allocation-order-request",
        defender_player_id="player-b",
        attack_context={"attack_context_id": "phase14e-allocation-order"},
        allocation_context=allocation_context,
        allocation_groups=allocation_groups,
    )
    selected_option = request.options[0]
    lifecycle.decision_controller.request_decision(request)

    with pytest.raises(DecisionError, match="next queued request"):
        lifecycle.decision_controller.submit_result(
            DecisionResult(
                result_id="phase14e-allocation-order-stale",
                request_id="stale-request",
                decision_type=request.decision_type,
                actor_id=request.actor_id,
                selected_option_id=selected_option.option_id,
                payload=selected_option.payload,
            )
        )
    assert lifecycle.decision_controller.queue.peek_next() == request

    with pytest.raises(DecisionError, match="actor_id"):
        lifecycle.decision_controller.submit_result(
            DecisionResult(
                result_id="phase14e-allocation-order-wrong-actor",
                request_id=request.request_id,
                decision_type=request.decision_type,
                actor_id="player-a",
                selected_option_id=selected_option.option_id,
                payload=selected_option.payload,
            )
        )
    assert lifecycle.decision_controller.queue.peek_next() == request

    with pytest.raises(DecisionError, match="finite action space"):
        lifecycle.decision_controller.submit_result(
            DecisionResult(
                result_id="phase14e-allocation-order-wrong-option",
                request_id=request.request_id,
                decision_type=request.decision_type,
                actor_id=request.actor_id,
                selected_option_id="not-a-group",
                payload={"ordered_group_ids": ["not-a-group"]},
            )
        )
    assert lifecycle.decision_controller.queue.peek_next() == request

    selected_option_payload = cast(dict[str, object], selected_option.payload)
    selected_order = tuple(cast(list[str], selected_option_payload["ordered_group_ids"]))
    valid_result = DecisionResult.for_request(
        result_id="phase14e-allocation-order-valid",
        request=request,
        selected_option_id=selected_option.option_id,
    )
    record = lifecycle.decision_controller.submit_result(valid_result)
    decision = AllocationOrderDecision.from_result(request=record.request, result=record.result)
    encoded = json.dumps(record.to_payload(), sort_keys=True)

    assert cast(dict[str, object], request.payload)["selection_kind"] == "allocation_group_order"
    assert decision.ordered_group_ids == selected_order
    assert decision.selected_group_id == selected_order[0]
    assert len(decision.allocation_groups) == 2
    assert decision.selected_group().group_id == selected_order[0]
    assert tuple(group.group_id for group in decision.ordered_groups()) == selected_order
    assert decision.to_payload()["ordered_group_ids"] == list(selected_order)
    assert "<" not in encoded
    assert "object at 0x" not in encoded

    malformed_request = DecisionRequest(
        request_id="phase14e-allocation-order-malformed-groups",
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        payload={
            **cast(dict[str, JsonValue], request.payload),
            "allocation_groups": "not-a-list",
        },
        options=request.options,
    )
    with pytest.raises(GameLifecycleError, match="groups must be a list"):
        AllocationOrderDecision.from_result(
            request=malformed_request,
            result=DecisionResult.for_request(
                result_id="phase14e-allocation-order-malformed-result",
                request=malformed_request,
                selected_option_id=selected_option.option_id,
            ),
        )
    malformed_order_request = DecisionRequest(
        request_id="phase14e-allocation-order-malformed-order",
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        payload=request.payload,
        options=(
            DecisionOption(
                option_id="phase14e-malformed-order-option",
                label="phase14e-malformed-order-option",
                payload={"submission_kind": SELECT_ALLOCATION_ORDER_DECISION_TYPE},
            ),
        ),
    )
    with pytest.raises(GameLifecycleError, match="missing ordered_group_ids"):
        AllocationOrderDecision.from_result(
            request=malformed_order_request,
            result=DecisionResult.for_request(
                result_id="phase14e-allocation-order-missing-order-result",
                request=malformed_order_request,
                selected_option_id="phase14e-malformed-order-option",
            ),
        )


def test_phase14e_allocation_group_payloads_preserve_roles_and_priority() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    defender = _replace_enemy_with_attached_character_fixture(state=state, defender=units["enemy"])
    bodyguard_model = replace(
        defender.own_models[0],
        source_ids=tuple(
            sorted(
                {
                    *defender.own_models[0].source_ids,
                    "runtime-attached-unit:bodyguard",
                }
            )
        ),
    )
    character_group_id = f"allocation-group:character:{defender.own_models[1].model_instance_id}"
    character_model = replace(
        defender.own_models[1],
        source_ids=tuple(
            sorted(
                {
                    *defender.own_models[1].source_ids,
                    "attached-role:leader",
                    "runtime-attached-unit:leader",
                }
            )
        ),
    )
    attached_defender = replace(defender, own_models=(bodyguard_model, character_model))
    _replace_unit_instance_in_state(state=state, replacement=attached_defender)
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=attached_defender.unit_instance_id,
        attacker_constraint=AttackAllocationConstraint(
            source_rule_ids=(PRECISION_RULE_ID,),
            can_allocate_protected_characters=True,
            attacker_selected_group_id=character_group_id,
        ),
    )
    allocation_groups = allocation_groups_for_context(
        state=state,
        allocation_context=allocation_context,
    )
    bodyguard_group = next(
        group for group in allocation_groups if group.role is AllocationGroupRole.BODYGUARD
    )
    leader_group = next(
        group for group in allocation_groups if group.role is AllocationGroupRole.LEADER
    )
    leader_payload = leader_group.to_payload()

    assert (
        allocation_group_role_from_token(AllocationGroupRole.LEADER) is AllocationGroupRole.LEADER
    )
    assert allocation_group_role_from_token("bodyguard") is AllocationGroupRole.BODYGUARD
    assert bodyguard_group.model_ids == (bodyguard_model.model_instance_id,)
    assert "allocation-role:bodyguard" in bodyguard_group.role_evidence
    assert "runtime-attached-unit:bodyguard" in bodyguard_group.role_evidence
    assert leader_group.group_id == character_group_id
    assert leader_group.character_model_ids == (character_model.model_instance_id,)
    assert "attached-role:leader" in leader_group.role_evidence
    assert "runtime-attached-unit:leader" in leader_group.role_evidence
    assert "attacker_selected_allocation_group" in leader_group.legality_reasons
    assert AllocationGroup.from_payload(leader_payload) == leader_group
    assert (
        allocation_groups_for_context(
            state=state,
            allocation_context=allocation_context,
            visible_model_ids=(),
        )
        == ()
    )

    with pytest.raises(GameLifecycleError, match="Unsupported AllocationGroupRole token"):
        AllocationGroup.from_payload(
            cast(AllocationGroupPayload, {**leader_payload, "role": "not-a-role"})
        )
    with pytest.raises(GameLifecycleError, match="token must be a string"):
        allocation_group_role_from_token(7)
    with pytest.raises(GameLifecycleError, match="requires models"):
        AllocationGroup(
            group_id="phase14e-empty-group",
            target_unit_instance_id=attached_defender.unit_instance_id,
            model_ids=(),
            role=AllocationGroupRole.BODYGUARD,
            wounds=2,
            save=3,
            invulnerable_save=None,
        )
    with pytest.raises(GameLifecycleError, match="at least two legal orders"):
        build_allocation_order_request(
            request_id="phase14e-one-group-request",
            defender_player_id="player-b",
            attack_context={"attack_context_id": "phase14e-one-group"},
            allocation_context=allocation_context,
            allocation_groups=(leader_group,),
        )

    support_model = replace(
        character_model,
        source_ids=tuple(
            sorted(
                (
                    set(character_model.source_ids)
                    - {"attached-role:leader", "runtime-attached-unit:leader"}
                )
                | {"attached-role:support", "runtime-attached-unit:support"}
            )
        ),
    )
    support_defender = replace(attached_defender, own_models=(bodyguard_model, support_model))
    _replace_unit_instance_in_state(state=state, replacement=support_defender)
    support_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=support_defender.unit_instance_id,
        attacker_constraint=AttackAllocationConstraint(
            source_rule_ids=(PRECISION_RULE_ID,),
            can_allocate_protected_characters=True,
        ),
    )
    support_group = next(
        group
        for group in allocation_groups_for_context(
            state=state,
            allocation_context=support_context,
        )
        if group.role is AllocationGroupRole.SUPPORT
    )

    assert support_group.character_model_ids == (support_model.model_instance_id,)
    assert "attached-role:support" in support_group.role_evidence
    assert "runtime-attached-unit:support" in support_group.role_evidence


def test_phase14e_allocation_group_payloads_prioritize_wounded_then_allocated_models() -> None:
    _lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(_lifecycle)
    defender = units["enemy"]
    wounded_model = replace(defender.own_models[1], wounds_remaining=1)
    already_allocated_model = defender.own_models[2]
    updated_defender = replace(
        defender,
        own_models=(
            defender.own_models[0],
            wounded_model,
            *defender.own_models[2:],
        ),
    )
    _replace_unit_instance_in_state(state=state, replacement=updated_defender)
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=updated_defender.unit_instance_id,
        already_allocated_model_ids=(already_allocated_model.model_instance_id,),
    )
    allocation_groups = allocation_groups_for_context(
        state=state,
        allocation_context=allocation_context,
    )
    allocation_group = allocation_groups[0]

    assert len(allocation_groups) == 1
    assert allocation_group.wounded is True
    assert allocation_group.model_ids == (
        wounded_model.model_instance_id,
        already_allocated_model.model_instance_id,
    )
    assert allocation_group.ordered_model_ids_for_damage() == (
        wounded_model.model_instance_id,
        already_allocated_model.model_instance_id,
    )
    assert AllocationGroup.from_payload(allocation_group.to_payload()) == allocation_group

    with pytest.raises(GameLifecycleError, match="ordered groups must match legal groups"):
        AllocationOrderDecision(
            request_id="phase14e-illegal-selected-group-request",
            result_id="phase14e-illegal-selected-group-result",
            player_id="player-b",
            ordered_group_ids=("phase14e-missing-group",),
            attack_context={"attack_context_id": "phase14e-illegal-selected-group"},
            allocation_context=allocation_context,
            allocation_groups=allocation_groups,
        )


def test_phase14e_allocation_order_decision_fails_fast_on_malformed_domain_objects() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    defender = _replace_enemy_with_attached_character_fixture(state=state, defender=units["enemy"])
    allocation_context = AttackAllocationRuleContext(
        target_unit_instance_id=defender.unit_instance_id,
        alive_model_ids=("phase14e-malformed-model-a", "phase14e-malformed-model-b"),
    )
    allocation_groups = (
        AllocationGroup(
            group_id="phase14e-malformed-group-a",
            target_unit_instance_id=defender.unit_instance_id,
            model_ids=("phase14e-malformed-model-a",),
            role=AllocationGroupRole.NON_CHARACTER,
            wounds=2,
            save=3,
            invulnerable_save=None,
        ),
        AllocationGroup(
            group_id="phase14e-malformed-group-b",
            target_unit_instance_id=defender.unit_instance_id,
            model_ids=("phase14e-malformed-model-b",),
            role=AllocationGroupRole.NON_CHARACTER,
            wounds=2,
            save=4,
            invulnerable_save=None,
        ),
    )
    ordered_group_ids = tuple(
        group.group_id for group in legal_allocation_group_orders(allocation_groups)[0]
    )
    request = build_allocation_order_request(
        request_id="phase14e-malformed-allocation-order-request",
        defender_player_id="player-b",
        attack_context={"attack_context_id": "phase14e-malformed-allocation-order"},
        allocation_context=allocation_context,
        allocation_groups=allocation_groups,
    )
    selected_option = request.options[0]
    actorless_request = DecisionRequest(
        request_id="phase14e-actorless-allocation-order-request",
        decision_type=request.decision_type,
        actor_id=None,
        payload=request.payload,
        options=request.options,
    )

    with pytest.raises(GameLifecycleError, match="requires a defender actor"):
        AllocationOrderDecision.from_result(
            request=actorless_request,
            result=DecisionResult.for_request(
                result_id="phase14e-actorless-allocation-order-result",
                request=actorless_request,
                selected_option_id=selected_option.option_id,
            ),
        )
    with pytest.raises(GameLifecycleError, match="allocation_context must be allocation context"):
        AllocationOrderDecision(
            request_id="phase14e-bad-context-request",
            result_id="phase14e-bad-context-result",
            player_id="player-b",
            ordered_group_ids=ordered_group_ids,
            attack_context={"attack_context_id": "phase14e-bad-context"},
            allocation_context=cast(AttackAllocationRuleContext, object()),
            allocation_groups=allocation_groups,
        )
    with pytest.raises(GameLifecycleError, match="Allocation groups must be a tuple"):
        AllocationOrderDecision(
            request_id="phase14e-list-groups-request",
            result_id="phase14e-list-groups-result",
            player_id="player-b",
            ordered_group_ids=ordered_group_ids,
            attack_context={"attack_context_id": "phase14e-list-groups"},
            allocation_context=allocation_context,
            allocation_groups=cast(tuple[AllocationGroup, ...], list(allocation_groups)),
        )
    with pytest.raises(GameLifecycleError, match="must contain AllocationGroup values"):
        AllocationOrderDecision(
            request_id="phase14e-non-group-request",
            result_id="phase14e-non-group-result",
            player_id="player-b",
            ordered_group_ids=ordered_group_ids,
            attack_context={"attack_context_id": "phase14e-non-group"},
            allocation_context=allocation_context,
            allocation_groups=cast(tuple[AllocationGroup, ...], ("not-a-group",)),
        )
    with pytest.raises(GameLifecycleError, match="must not duplicate group IDs"):
        AllocationOrderDecision(
            request_id="phase14e-duplicate-group-request",
            result_id="phase14e-duplicate-group-result",
            player_id="player-b",
            ordered_group_ids=(allocation_groups[0].group_id,),
            attack_context={"attack_context_id": "phase14e-duplicate-group"},
            allocation_context=allocation_context,
            allocation_groups=(allocation_groups[0], allocation_groups[0]),
        )
    with pytest.raises(GameLifecycleError, match="ordered_group_ids must not be empty"):
        AllocationOrderDecision(
            request_id="phase14e-empty-order-request",
            result_id="phase14e-empty-order-result",
            player_id="player-b",
            ordered_group_ids=(),
            attack_context={"attack_context_id": "phase14e-empty-order"},
            allocation_context=allocation_context,
            allocation_groups=allocation_groups,
        )
    with pytest.raises(GameLifecycleError, match="ordered_group_ids must not contain duplicates"):
        AllocationOrderDecision(
            request_id="phase14e-duplicate-order-request",
            result_id="phase14e-duplicate-order-result",
            player_id="player-b",
            ordered_group_ids=(allocation_groups[0].group_id, allocation_groups[0].group_id),
            attack_context={"attack_context_id": "phase14e-duplicate-order"},
            allocation_context=allocation_context,
            allocation_groups=allocation_groups,
        )
    with pytest.raises(GameLifecycleError, match="attacker_constraint must be a constraint"):
        AttackAllocationRuleContext(
            target_unit_instance_id=defender.unit_instance_id,
            alive_model_ids=tuple(model.model_instance_id for model in defender.own_models),
            attacker_constraint=cast(AttackAllocationConstraint, object()),
        )
    with pytest.raises(GameLifecycleError, match="require an allocation context"):
        allocation_groups_for_context(
            state=state,
            allocation_context=cast(AttackAllocationRuleContext, object()),
        )
    with pytest.raises(GameLifecycleError, match="unit_instance_id is unknown"):
        allocation_context_for_unit(
            state=state,
            target_unit_instance_id="phase14e-missing-target-unit",
        )
    with pytest.raises(GameLifecycleError, match="model_instance_id is unknown"):
        allocation_groups_for_context(
            state=state,
            allocation_context=AttackAllocationRuleContext(
                target_unit_instance_id=defender.unit_instance_id,
                alive_model_ids=("phase14e-missing-model",),
            ),
        )
    with pytest.raises(GameLifecycleError, match="forced must be a bool"):
        AttackAllocation(
            target_unit_instance_id=defender.unit_instance_id,
            allocated_model_id=allocation_groups[0].model_ids[0],
            legal_model_ids=allocation_groups[0].model_ids,
            forced=cast(bool, "yes"),
            rule_context=allocation_context,
        )
    with pytest.raises(GameLifecycleError, match="rule_context must be an allocation context"):
        AttackAllocation(
            target_unit_instance_id=defender.unit_instance_id,
            allocated_model_id=allocation_groups[0].model_ids[0],
            legal_model_ids=allocation_groups[0].model_ids,
            forced=True,
            rule_context=cast(AttackAllocationRuleContext, object()),
        )

    all_character_defender = replace(
        defender,
        own_models=tuple(
            replace(
                model,
                source_ids=tuple(sorted({*model.source_ids, "attached-role:character"})),
            )
            for model in defender.own_models
        ),
    )
    _replace_unit_instance_in_state(state=state, replacement=all_character_defender)
    all_character_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=all_character_defender.unit_instance_id,
    )

    assert all_character_context.attached_unit_bodyguard_model_ids == ()
    assert all_character_context.attached_unit_character_model_ids == ()


def test_phase13c_mandatory_saves_and_plunging_fire_are_typed() -> None:
    _lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    model = units["enemy"].own_models[0]
    cover_result = _benefit_of_cover_result()
    armour_option = next(
        option
        for option in save_options_for_model(
            model=model,
            armor_penetration=-1,
            cover_result=cover_result,
        )
        if option.save_kind is SaveKind.ARMOUR
    )
    invulnerable_option = SaveOption(
        save_kind=SaveKind.INVULNERABLE,
        target_number=4,
        characteristic_target_number=4,
        armor_penetration=-3,
        cover_applied=False,
        cover_result=None,
    )
    selected = mandatory_save_option(options=(armour_option, invulnerable_option))
    assert selected is not None
    save_roll = DiceRollManager("phase13c-save-roll").roll_fixed(
        saving_throw_roll_spec(
            save_kind=selected.save_kind,
            player_id="player-b",
            allocated_model_id=model.model_instance_id,
            attack_context_id="phase13c-save-context",
        ),
        [4],
    )
    saving_throw = resolve_saving_throw(option=selected, roll_state=save_roll)

    assert save_kind_from_token("armour") is SaveKind.ARMOUR
    assert saving_throw.successful is True
    assert saving_throw.to_payload()["option"]["save_kind"] == "invulnerable"
    assert SaveOption.from_payload(armour_option.to_payload()) == armour_option
    stronger_invulnerable_option = SaveOption(
        save_kind=SaveKind.INVULNERABLE,
        target_number=3,
        characteristic_target_number=3,
        armor_penetration=-3,
        source_rule_ids=("go-to-ground",),
    )
    assert (
        mandatory_save_option(options=(armour_option, stronger_invulnerable_option))
        == stronger_invulnerable_option
    )
    with pytest.raises(GameLifecycleError, match="SaveKind token"):
        save_kind_from_token(3)

    unsupported = PlungingFireModifier(
        source_rule_id="plunging-fire",
        supported=False,
    ).apply(
        ballistic_skill=4,
        attacker_z_inches=7.0,
        target_z_inches=0.0,
        target_fully_visible=True,
    )
    too_low = PlungingFireModifier(
        source_rule_id="plunging-fire",
        supported=True,
    ).apply(
        ballistic_skill=4,
        attacker_z_inches=2.0,
        target_z_inches=0.0,
        target_fully_visible=True,
    )
    not_visible = PlungingFireModifier(
        source_rule_id="plunging-fire",
        supported=True,
    ).apply(
        ballistic_skill=4,
        attacker_z_inches=7.0,
        target_z_inches=0.0,
        target_fully_visible=False,
    )
    applied = PlungingFireModifier(
        source_rule_id="plunging-fire",
        supported=True,
    ).apply(
        ballistic_skill=4,
        attacker_z_inches=7.0,
        target_z_inches=0.0,
        target_fully_visible=True,
    )

    assert unsupported.status == "unsupported"
    assert too_low.reason == "height_advantage_not_met"
    assert not_visible.reason == "target_not_fully_visible"
    assert applied.to_payload()["final_ballistic_skill"] == 3
    with pytest.raises(GameLifecycleError, match="status"):
        PlungingFireModifierResult(
            source_rule_id="plunging-fire",
            status="wrong",
            reason=None,
            input_ballistic_skill=4,
            final_ballistic_skill=4,
            required_height_advantage_inches=3.0,
            actual_height_advantage_inches=7.0,
            target_fully_visible=True,
        )


def test_phase14e_save_and_plunging_fire_validation_is_fail_fast() -> None:
    valid_option = SaveOption(
        save_kind=SaveKind.ARMOUR,
        target_number=3,
        characteristic_target_number=3,
        armor_penetration=0,
    )
    save_roll = DiceRollManager("phase14e-validation-save").roll_fixed(
        saving_throw_roll_spec(
            save_kind=SaveKind.ARMOUR,
            player_id="player-b",
            allocated_model_id="model-a",
            attack_context_id="phase14e-validation-context",
        ),
        [3],
    )

    with pytest.raises(GameLifecycleError, match="cover_result"):
        SaveOption(
            save_kind=SaveKind.ARMOUR,
            target_number=3,
            characteristic_target_number=3,
            armor_penetration=0,
            cover_result=cast(BenefitOfCoverResult, "bad-cover"),
        )
    with pytest.raises(GameLifecycleError, match="target_number"):
        SaveOption(
            save_kind=SaveKind.ARMOUR,
            target_number=1,
            characteristic_target_number=3,
            armor_penetration=0,
        )
    with pytest.raises(GameLifecycleError, match="source_rule_ids"):
        SaveOption(
            save_kind=SaveKind.ARMOUR,
            target_number=3,
            characteristic_target_number=3,
            armor_penetration=0,
            source_rule_ids=cast(tuple[str, ...], ["bad-list"]),
        )
    with pytest.raises(GameLifecycleError, match="duplicates"):
        SaveOption(
            save_kind=SaveKind.ARMOUR,
            target_number=3,
            characteristic_target_number=3,
            armor_penetration=0,
            source_rule_ids=("same", "same"),
        )
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        SaveOption(
            save_kind=SaveKind.ARMOUR,
            target_number=3,
            characteristic_target_number=3,
            armor_penetration=0,
            source_rule_ids=("",),
        )

    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        mandatory_save_option(options=cast(tuple[SaveOption, ...], [valid_option]))
    with pytest.raises(GameLifecycleError, match="SaveOption values"):
        mandatory_save_option(options=(cast(SaveOption, "not-an-option"),))

    one_roll = DiceRollManager("phase14e-validation-one").roll_fixed(
        saving_throw_roll_spec(
            save_kind=SaveKind.ARMOUR,
            player_id="player-b",
            allocated_model_id="model-a",
            attack_context_id="phase14e-validation-one-context",
        ),
        [1],
    )
    two_roll = DiceRollManager("phase14e-validation-two").roll_fixed(
        saving_throw_roll_spec(
            save_kind=SaveKind.ARMOUR,
            player_id="player-b",
            allocated_model_id="model-a",
            attack_context_id="phase14e-validation-two-context",
        ),
        [2],
    )
    invulnerable_option = SaveOption(
        save_kind=SaveKind.INVULNERABLE,
        target_number=4,
        characteristic_target_number=4,
        armor_penetration=0,
    )

    with pytest.raises(GameLifecycleError, match="target_number must match"):
        SavingThrow(
            save_kind=SaveKind.ARMOUR,
            target_number=4,
            roll_state=save_roll,
            unmodified_roll=4,
            final_roll=4,
            successful=True,
            resolution_rule=SaveResolutionRule.ARMOUR_SAVE,
            option=valid_option,
        )
    with pytest.raises(GameLifecycleError, match="D6 value"):
        SavingThrow(
            save_kind=SaveKind.ARMOUR,
            target_number=3,
            roll_state=save_roll,
            unmodified_roll=7,
            final_roll=7,
            successful=True,
            resolution_rule=SaveResolutionRule.ARMOUR_SAVE,
            option=valid_option,
        )
    with pytest.raises(GameLifecycleError, match="final_roll"):
        SavingThrow(
            save_kind=SaveKind.ARMOUR,
            target_number=3,
            roll_state=save_roll,
            unmodified_roll=3,
            final_roll=cast(int, "bad-roll"),
            successful=True,
            resolution_rule=SaveResolutionRule.ARMOUR_SAVE,
            option=valid_option,
        )
    with pytest.raises(GameLifecycleError, match="successful"):
        SavingThrow(
            save_kind=SaveKind.ARMOUR,
            target_number=3,
            roll_state=save_roll,
            unmodified_roll=3,
            final_roll=3,
            successful=cast(bool, "yes"),
            resolution_rule=SaveResolutionRule.ARMOUR_SAVE,
            option=valid_option,
        )
    with pytest.raises(GameLifecycleError, match="SaveResolutionRule token"):
        SavingThrow(
            save_kind=SaveKind.ARMOUR,
            target_number=3,
            roll_state=save_roll,
            unmodified_roll=3,
            final_roll=3,
            successful=True,
            resolution_rule=cast(SaveResolutionRule, 3),
            option=valid_option,
        )
    with pytest.raises(GameLifecycleError, match="Unsupported SaveResolutionRule"):
        SavingThrow(
            save_kind=SaveKind.ARMOUR,
            target_number=3,
            roll_state=save_roll,
            unmodified_roll=3,
            final_roll=3,
            successful=True,
            resolution_rule=cast(SaveResolutionRule, "not-a-resolution"),
            option=valid_option,
        )
    with pytest.raises(GameLifecycleError, match="Unmodified-one"):
        SavingThrow(
            save_kind=SaveKind.ARMOUR,
            target_number=3,
            roll_state=save_roll,
            unmodified_roll=3,
            final_roll=3,
            successful=False,
            resolution_rule=SaveResolutionRule.UNMODIFIED_ONE,
            option=valid_option,
        )
    with pytest.raises(GameLifecycleError, match="Invulnerable save resolution requires"):
        SavingThrow(
            save_kind=SaveKind.ARMOUR,
            target_number=3,
            roll_state=save_roll,
            unmodified_roll=3,
            final_roll=3,
            successful=True,
            resolution_rule=SaveResolutionRule.INVULNERABLE_SAVE,
            option=valid_option,
        )
    with pytest.raises(GameLifecycleError, match="Invulnerable save resolution does not match"):
        SavingThrow(
            save_kind=SaveKind.INVULNERABLE,
            target_number=4,
            roll_state=save_roll,
            unmodified_roll=3,
            final_roll=3,
            successful=True,
            resolution_rule=SaveResolutionRule.INVULNERABLE_SAVE,
            option=invulnerable_option,
        )
    with pytest.raises(GameLifecycleError, match="Armour save resolution requires"):
        SavingThrow(
            save_kind=SaveKind.INVULNERABLE,
            target_number=4,
            roll_state=save_roll,
            unmodified_roll=4,
            final_roll=4,
            successful=True,
            resolution_rule=SaveResolutionRule.ARMOUR_SAVE,
            option=invulnerable_option,
        )
    with pytest.raises(GameLifecycleError, match="Armour save resolution does not match"):
        SavingThrow(
            save_kind=SaveKind.ARMOUR,
            target_number=3,
            roll_state=two_roll,
            unmodified_roll=2,
            final_roll=2,
            successful=True,
            resolution_rule=SaveResolutionRule.ARMOUR_SAVE,
            option=valid_option,
        )
    with pytest.raises(GameLifecycleError, match="roll of 1"):
        SavingThrow(
            save_kind=SaveKind.ARMOUR,
            target_number=3,
            roll_state=one_roll,
            unmodified_roll=1,
            final_roll=1,
            successful=False,
            resolution_rule=SaveResolutionRule.FAILED,
            option=valid_option,
        )
    with pytest.raises(GameLifecycleError, match="Failed save resolution does not match"):
        SavingThrow(
            save_kind=SaveKind.ARMOUR,
            target_number=3,
            roll_state=save_roll,
            unmodified_roll=3,
            final_roll=3,
            successful=False,
            resolution_rule=SaveResolutionRule.FAILED,
            option=valid_option,
        )
    invalid_roll_state_throw = SavingThrow(
        save_kind=SaveKind.ARMOUR,
        target_number=3,
        roll_state=cast(DiceRollState, "bad-roll-state"),
        unmodified_roll=3,
        final_roll=3,
        successful=True,
        resolution_rule=SaveResolutionRule.ARMOUR_SAVE,
        option=valid_option,
    )
    with pytest.raises(GameLifecycleError, match="roll_state"):
        invalid_roll_state_throw.to_payload()
    with pytest.raises(GameLifecycleError, match="option or options"):
        resolve_saving_throw(
            option=valid_option,
            options=(valid_option,),
            roll_state=save_roll,
        )
    with pytest.raises(GameLifecycleError, match="option must be SaveOption"):
        resolve_saving_throw(
            option=cast(SaveOption, "bad-option"),
            roll_state=save_roll,
        )
    with pytest.raises(GameLifecycleError, match="requires save options"):
        resolve_saving_throw(roll_state=save_roll)
    with pytest.raises(GameLifecycleError, match="at least one save option"):
        resolve_saving_throw(options=(), roll_state=save_roll)

    with pytest.raises(GameLifecycleError, match="supported"):
        PlungingFireModifier(
            source_rule_id="plunging-fire",
            supported=cast(bool, "yes"),
        )
    with pytest.raises(GameLifecycleError, match="required height"):
        PlungingFireModifier(
            source_rule_id="plunging-fire",
            supported=True,
            required_height_advantage_inches=cast(float, "six"),
        )
    with pytest.raises(GameLifecycleError, match="positive"):
        PlungingFireModifier(
            source_rule_id="plunging-fire",
            supported=True,
            required_height_advantage_inches=0.0,
        )
    with pytest.raises(GameLifecycleError, match="BS modifier"):
        PlungingFireModifier(
            source_rule_id="plunging-fire",
            supported=True,
            ballistic_skill_modifier=cast(int, "minus-one"),
        )

    plunging_fire = PlungingFireModifier(source_rule_id="plunging-fire", supported=True)
    with pytest.raises(GameLifecycleError, match="attacker height"):
        plunging_fire.apply(
            ballistic_skill=4,
            attacker_z_inches=cast(float, 7),
            target_z_inches=0.0,
            target_fully_visible=True,
        )
    with pytest.raises(GameLifecycleError, match="target height"):
        plunging_fire.apply(
            ballistic_skill=4,
            attacker_z_inches=7.0,
            target_z_inches=cast(float, 0),
            target_fully_visible=True,
        )
    with pytest.raises(GameLifecycleError, match="visibility"):
        plunging_fire.apply(
            ballistic_skill=4,
            attacker_z_inches=7.0,
            target_z_inches=0.0,
            target_fully_visible=cast(bool, "yes"),
        )

    with pytest.raises(GameLifecycleError, match="required height"):
        PlungingFireModifierResult(
            source_rule_id="plunging-fire",
            status="applied",
            reason=None,
            input_ballistic_skill=4,
            final_ballistic_skill=3,
            required_height_advantage_inches=cast(float, 6),
            actual_height_advantage_inches=7.0,
            target_fully_visible=True,
        )
    with pytest.raises(GameLifecycleError, match="actual height"):
        PlungingFireModifierResult(
            source_rule_id="plunging-fire",
            status="applied",
            reason=None,
            input_ballistic_skill=4,
            final_ballistic_skill=3,
            required_height_advantage_inches=3.0,
            actual_height_advantage_inches=cast(float, 7),
            target_fully_visible=True,
        )
    with pytest.raises(GameLifecycleError, match="visibility"):
        PlungingFireModifierResult(
            source_rule_id="plunging-fire",
            status="applied",
            reason=None,
            input_ballistic_skill=4,
            final_ballistic_skill=3,
            required_height_advantage_inches=3.0,
            actual_height_advantage_inches=7.0,
            target_fully_visible=cast(bool, "yes"),
        )
    with pytest.raises(GameLifecycleError, match="must not include a reason"):
        PlungingFireModifierResult(
            source_rule_id="plunging-fire",
            status="applied",
            reason="bad-reason",
            input_ballistic_skill=4,
            final_ballistic_skill=3,
            required_height_advantage_inches=3.0,
            actual_height_advantage_inches=7.0,
            target_fully_visible=True,
        )
    with pytest.raises(GameLifecycleError, match="requires a reason"):
        PlungingFireModifierResult(
            source_rule_id="plunging-fire",
            status="not_applicable",
            reason=None,
            input_ballistic_skill=4,
            final_ballistic_skill=4,
            required_height_advantage_inches=3.0,
            actual_height_advantage_inches=3.0,
            target_fully_visible=True,
        )


def test_phase13c_damage_mortal_wounds_and_feel_no_pain_hosts_round_trip() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    defender = units["enemy"]
    defender_model = defender.own_models[0]

    damage = apply_damage_to_model(
        state=state,
        target_unit_instance_id=defender.unit_instance_id,
        model_instance_id=defender_model.model_instance_id,
        damage=1,
        damage_kind=DamageKind.NORMAL,
    )
    assert DamageApplication.from_payload(damage.to_payload()) == damage
    assert damage.wounds_lost == 1
    assert damage.destroyed is False

    mortal_application = apply_mortal_wounds_to_unit(
        state=state,
        target_unit_instance_id=defender.unit_instance_id,
        mortal_wounds=3,
        spill_over=True,
    )
    assert mortal_application.to_payload()["mortal_wounds"] == 3
    assert mortal_application.applications
    assert damage_kind_from_token("mortal") is DamageKind.MORTAL

    no_spill_lifecycle, no_spill_units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    no_spill_state = _state(no_spill_lifecycle)
    no_spill_defender = no_spill_units["enemy"]
    no_spill_application = apply_mortal_wounds_to_unit(
        state=no_spill_state,
        target_unit_instance_id=no_spill_defender.unit_instance_id,
        mortal_wounds=3,
        spill_over=False,
    )
    assert no_spill_application.remaining_mortal_wounds_lost == 1

    overkill_lifecycle, overkill_units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    overkill_state = _state(overkill_lifecycle)
    overkill_defender = overkill_units["enemy"]
    overkill_application = apply_mortal_wounds_to_unit(
        state=overkill_state,
        target_unit_instance_id=overkill_defender.unit_instance_id,
        mortal_wounds=99,
        spill_over=True,
    )
    assert overkill_application.applications
    assert overkill_application.remaining_mortal_wounds_lost > 0

    source_a = FeelNoPainSource(source_id="feel-no-pain-a", threshold=5)
    source_b = FeelNoPainSource(source_id="feel-no-pain-b", threshold=6)
    source_c = FeelNoPainSource(
        source_id="feel-no-pain-psychic-mortal",
        threshold=4,
        attack_condition=FeelNoPainAttackCondition.PSYCHIC_ATTACK,
        mortal_wounds=True,
    )
    request = build_feel_no_pain_request(
        request_id="phase13c-fnp-request",
        defender_player_id="player-b",
        lost_wound_context={"model_instance_id": defender_model.model_instance_id},
        sources=(source_a, source_b),
        decline_allowed=True,
    )
    result = DecisionResult(
        result_id="phase13c-fnp-result",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=source_a.source_id,
        payload={"source_id": source_a.source_id},
    )
    decision = FeelNoPainDecision.from_result(request=request, result=result)
    fnp_spec = feel_no_pain_roll_spec(
        source=source_a,
        player_id="player-b",
        model_instance_id=defender_model.model_instance_id,
        wound_index=1,
    )

    assert source_a.to_payload()["threshold"] == 5
    assert FeelNoPainSource.from_payload(source_a.to_payload()) == source_a
    assert source_c.to_payload().get("mortal_wounds") is True
    assert FeelNoPainSource.from_payload(source_c.to_payload()) == source_c
    assert decision.to_payload()["selected_source_id"] == source_a.source_id
    assert fnp_spec.roll_type == "attack_sequence.feel_no_pain"
    assert defender_model.model_instance_id in fnp_spec.reason

    decline_result = DecisionResult(
        result_id="phase13c-fnp-decline",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id="decline",
        payload={"source_id": None},
    )
    decline_decision = FeelNoPainDecision.from_result(
        request=request,
        result=decline_result,
    )
    assert decline_decision.selected_source_id is None

    malformed_fnp_request = DecisionRequest(
        request_id="phase13c-fnp-malformed",
        decision_type=request.decision_type,
        actor_id="player-b",
        payload={"lost_wound_context": {"model_instance_id": defender_model.model_instance_id}},
        options=(DecisionOption(option_id="bad", label="Bad", payload={"source_id": 3}),),
    )
    with pytest.raises(GameLifecycleError, match="source_id must be a string or null"):
        FeelNoPainDecision.from_result(
            request=malformed_fnp_request,
            result=DecisionResult(
                result_id="phase13c-fnp-malformed-result",
                request_id=malformed_fnp_request.request_id,
                decision_type=malformed_fnp_request.decision_type,
                actor_id=malformed_fnp_request.actor_id,
                selected_option_id="bad",
                payload={"source_id": 3},
            ),
        )


def test_phase13c_forced_single_source_feel_no_pain_reduces_failed_save_damage() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    source = FeelNoPainSource(source_id="phase13c-fnp-5-plus", threshold=5)
    state.record_model_feel_no_pain_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(source,),
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        damage_profile=DamageProfile.fixed(2),
    )
    attack_context_id = "phase13c-forced-fnp:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )
    fnp_spec_1 = feel_no_pain_roll_spec(
        source=source,
        player_id="player-b",
        model_instance_id=defender_model.model_instance_id,
        wound_index=1,
    )
    fnp_spec_2 = feel_no_pain_roll_spec(
        source=source,
        player_id="player-b",
        model_instance_id=defender_model.model_instance_id,
        wound_index=2,
    )
    dice_manager = DiceRollManager(
        "phase13c-forced-fnp",
        event_log=lifecycle.decision_controller.event_log,
        injected_results=(
            _fixed_roll_result(roll_id="phase13c-hit", spec=hit_spec, value=6),
            _fixed_roll_result(roll_id="phase13c-wound", spec=wound_spec, value=6),
            _fixed_roll_result(roll_id="phase13c-save", spec=save_spec, value=1),
            _fixed_roll_result(roll_id="phase13c-fnp-1", spec=fnp_spec_1, value=5),
            _fixed_roll_result(roll_id="phase13c-fnp-2", spec=fnp_spec_2, value=2),
        ),
    )

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=AttackSequence.start(
            sequence_id="phase13c-forced-fnp",
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=dice_manager,
    )
    updated_model = model_by_id(state=state, model_instance_id=defender_model.model_instance_id)
    damage_event = next(
        record
        for record in lifecycle.decision_controller.event_log.records
        if record.event_type == "attack_sequence_step"
        and cast(dict[str, object], record.payload)["step"] == AttackSequenceStep.DAMAGE.value
    )
    payload = cast(dict[str, object], cast(dict[str, object], damage_event.payload)["payload"])
    fnp_payload = cast(dict[str, object], payload["feel_no_pain"])
    application = cast(dict[str, object], payload["damage_application"])

    assert remaining_sequence is None
    assert status is None
    assert fnp_payload["ignored_wounds"] == 1
    assert application["requested_damage"] == 1
    assert updated_model.wounds_remaining == defender_model.wounds_remaining - 1


def test_psychic_attack_classification_enables_psychic_only_feel_no_pain() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    source = FeelNoPainSource(
        source_id="psychic-only-fnp",
        threshold=5,
        attack_condition=FeelNoPainAttackCondition.PSYCHIC_ATTACK,
    )
    state.record_model_feel_no_pain_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(source,),
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        profile_id="psychic-only-fnp-rifle",
        keywords=(WeaponKeyword.PSYCHIC,),
        damage_profile=DamageProfile.fixed(2),
    )
    attack_context_id = "psychic-only-fnp:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )
    fnp_spec_1 = feel_no_pain_roll_spec(
        source=source,
        player_id="player-b",
        model_instance_id=defender_model.model_instance_id,
        wound_index=1,
    )
    fnp_spec_2 = feel_no_pain_roll_spec(
        source=source,
        player_id="player-b",
        model_instance_id=defender_model.model_instance_id,
        wound_index=2,
    )

    completed_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=AttackSequence.start(
            sequence_id="psychic-only-fnp",
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "psychic-only-fnp",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id="psychic-only-fnp-hit", spec=hit_spec, value=6),
                _fixed_roll_result(roll_id="psychic-only-fnp-wound", spec=wound_spec, value=6),
                _fixed_roll_result(roll_id="psychic-only-fnp-save", spec=save_spec, value=1),
                _fixed_roll_result(roll_id="psychic-only-fnp-1", spec=fnp_spec_1, value=5),
                _fixed_roll_result(roll_id="psychic-only-fnp-2", spec=fnp_spec_2, value=2),
            ),
        ),
    )
    hit_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.HIT,
    )
    damage_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.DAMAGE,
    )
    damage_event_payload = cast(dict[str, object], damage_payload["payload"])
    fnp_payload = cast(dict[str, object], damage_event_payload["feel_no_pain"])
    source_payload = cast(dict[str, object], fnp_payload["source"])
    updated_model = model_by_id(state=state, model_instance_id=defender_model.model_instance_id)

    assert completed_sequence is None
    assert status is None
    assert cast(dict[str, object], hit_payload["payload"])["is_psychic_attack"] is True
    assert source_payload["attack_condition"] == FeelNoPainAttackCondition.PSYCHIC_ATTACK.value
    assert updated_model.wounds_remaining == defender_model.wounds_remaining - 1


def test_phase13c_optional_feel_no_pain_choice_routes_through_lifecycle() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    source_a = FeelNoPainSource(source_id="phase13c-fnp-a", threshold=5)
    source_b = FeelNoPainSource(source_id="phase13c-fnp-b", threshold=6)
    state.record_model_feel_no_pain_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(source_a, source_b),
        decline_allowed=True,
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        damage_profile=DamageProfile.fixed(2),
    )
    sequence = AttackSequence.start(
        sequence_id="phase13c-optional-fnp",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=sequence.attack_pools,
        attack_sequence=sequence,
    )
    attack_context_id = "phase13c-optional-fnp:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )
    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase13c-optional-fnp",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id="phase13c-hit", spec=hit_spec, value=6),
                _fixed_roll_result(roll_id="phase13c-wound", spec=wound_spec, value=6),
                _fixed_roll_result(roll_id="phase13c-save", spec=save_spec, value=1),
            ),
        ),
    )
    assert status is not None
    request = _decision_request(status)
    assert request.decision_type == "select_feel_no_pain"
    assert {option.option_id for option in request.options} == {
        "decline",
        source_a.source_id,
        source_b.source_id,
    }
    state.shooting_phase_state = state.shooting_phase_state.with_attack_sequence_update(
        attack_sequence=remaining_sequence,
        allocated_model_ids_this_phase=allocated_ids,
    )

    final_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase13c-optional-fnp-decline",
            request=request,
            selected_option_id="decline",
        )
    )
    updated_model = model_by_id(state=state, model_instance_id=defender_model.model_instance_id)

    _assert_waiting_for_movement_unit(final_status)
    assert updated_model.is_alive is False


@pytest.mark.parametrize(
    ("selected_source_kind", "expected_action_host"),
    [
        (DestructionReactionKind.SHOOT_ON_DEATH, BattlePhase.SHOOTING.value),
        (DestructionReactionKind.FIGHT_ON_DEATH, BattlePhase.FIGHT.value),
    ],
)
def test_phase13e_destroyed_model_reaction_choice_records_removal_and_selection(
    selected_source_kind: DestructionReactionKind,
    expected_action_host: str,
) -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    shoot_source = DestructionReactionSource(
        source_id="phase13e-shoot-on-death",
        reaction_kind=DestructionReactionKind.SHOOT_ON_DEATH,
        source_rule_id="phase13e-shoot-on-death-rule",
    )
    fight_source = DestructionReactionSource(
        source_id="phase13e-fight-on-death",
        reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
        source_rule_id="phase13e-fight-on-death-rule",
    )
    state.record_model_destruction_reaction_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(shoot_source, fight_source),
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        damage_profile=DamageProfile.fixed(defender_model.wounds_remaining),
    )
    sequence = AttackSequence.start(
        sequence_id="phase13e-destruction-reaction",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=sequence.attack_pools,
        attack_sequence=sequence,
    )
    attack_context_id = "phase13e-destruction-reaction:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase13e-destruction-reaction",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id="phase13e-hit", spec=hit_spec, value=6),
                _fixed_roll_result(roll_id="phase13e-wound", spec=wound_spec, value=6),
                _fixed_roll_result(roll_id="phase13e-save", spec=save_spec, value=1),
            ),
        ),
    )
    request = _decision_request(cast(LifecycleStatus, status))
    state.shooting_phase_state = state.shooting_phase_state.with_attack_sequence_update(
        attack_sequence=remaining_sequence,
        allocated_model_ids_this_phase=allocated_ids,
    )

    assert request.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE
    assert {option.option_id for option in request.options} == {
        DECLINE_DESTRUCTION_REACTION_OPTION_ID,
        shoot_source.source_id,
        fight_source.source_id,
    }
    destroyed_payload = _last_event_payload(lifecycle, "model_destroyed")
    removal_record = cast(dict[str, object], destroyed_payload["removal_record"])
    transition_batch = cast(dict[str, object], destroyed_payload["transition_batch"])
    updated_battlefield = state.battlefield_state
    assert updated_battlefield is not None
    assert removal_record["model_instance_id"] == defender_model.model_instance_id
    assert removal_record["removal_kind"] == "destroyed"
    assert cast(list[object], transition_batch["removals"]) == [removal_record]
    assert defender_model.model_instance_id not in updated_battlefield.placed_model_ids()

    selected_reaction_source = shoot_source
    if selected_source_kind is DestructionReactionKind.FIGHT_ON_DEATH:
        selected_reaction_source = fight_source

    final_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=f"phase13e-select-{selected_source_kind.value}",
            request=request,
            selected_option_id=selected_reaction_source.source_id,
        )
    )
    reaction_payload = _last_event_payload(lifecycle, "destruction_reaction_resolved")
    selected_source = cast(dict[str, object], reaction_payload["selected_source"])

    _assert_waiting_for_movement_unit(final_status)
    assert selected_source["source_id"] == selected_reaction_source.source_id
    assert selected_source["reaction_kind"] == selected_source_kind.value
    assert reaction_payload["selected_reaction_kind"] == selected_source_kind.value
    assert reaction_payload["action_host"] == expected_action_host
    assert reaction_payload["execution_status"] == "recorded_for_action_host"
    assert any(
        record.result.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE
        for record in lifecycle.decision_controller.records
    )
    awaiting_events = _event_payloads(lifecycle, "fight_on_death_model_awaiting_attack")
    cleanup_events = _event_payloads(lifecycle, "fight_on_death_models_removed")
    if selected_source_kind is DestructionReactionKind.FIGHT_ON_DEATH:
        assert [payload["model_instance_id"] for payload in awaiting_events] == [
            defender_model.model_instance_id
        ]
        assert any(payload["reason"] == "phase_end" for payload in cleanup_events)
    else:
        assert awaiting_events == ()


def test_phase13e_fight_on_death_model_is_present_but_does_not_contribute_keywords() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    original_placement = battlefield.model_placement_by_id(defender_model.model_instance_id)
    _replace_unit_instance_in_state(
        state=state,
        replacement=replace(
            defender,
            own_models=tuple(replace(model, wounds_remaining=0) for model in defender.own_models),
        ),
    )
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models)
    )

    restore_model_awaiting_fight_on_death(
        state=state,
        placement=original_placement,
        effect_id="test-fight-on-death-awaiting",
        source_rule_id="test-fight-on-death-rule",
        source_phase=BattlePhase.SHOOTING,
    )

    assert model_is_present_on_battlefield(
        state=state,
        model_instance_id=defender_model.model_instance_id,
    )
    assert [
        model.model_id
        for model in geometry_models_for_rules_unit(
            state=state,
            unit_instance_id=defender.unit_instance_id,
        )
    ] == [defender_model.model_instance_id]
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=defender.unit_instance_id,
    )
    assert rules_unit.keywords == ()
    assert rules_unit.faction_keywords == ()
    replayed_state = GameState.from_payload(state.to_payload())
    assert model_is_present_on_battlefield(
        state=replayed_state,
        model_instance_id=defender_model.model_instance_id,
    )

    removed_model_ids = remove_models_awaiting_fight_on_death(state=state)

    assert removed_model_ids == (defender_model.model_instance_id,)
    assert not model_is_present_on_battlefield(
        state=state,
        model_instance_id=defender_model.model_instance_id,
    )


def test_phase13e_fight_on_death_only_unit_accepts_ranged_declaration_without_allocation() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    battlefield = state.battlefield_state
    assert battlefield is not None
    awaiting_model = defender.own_models[0]
    awaiting_placement = battlefield.model_placement_by_id(awaiting_model.model_instance_id)
    destroyed_model_ids = tuple(model.model_instance_id for model in defender.own_models)
    _replace_unit_instance_in_state(
        state=state,
        replacement=replace(
            defender,
            own_models=tuple(replace(model, wounds_remaining=0) for model in defender.own_models),
        ),
    )
    state.replace_battlefield_state(battlefield.with_removed_models(destroyed_model_ids))
    restore_model_awaiting_fight_on_death(
        state=state,
        placement=awaiting_placement,
        effect_id="phase13e-ranged-target-awaiting",
        source_rule_id="phase13e-ranged-target-rule",
        source_phase=BattlePhase.SHOOTING,
    )

    assert (
        damage_allocation_target_state(
            state=state,
            target_unit_instance_id=defender.unit_instance_id,
        )
        is DamageAllocationTargetState.PRESENT_WITHOUT_LIVING_MODELS
    )
    with pytest.raises(
        GameLifecycleError,
        match="present but has no living models",
    ):
        allocation_context_for_unit(
            state=state,
            target_unit_instance_id=defender.unit_instance_id,
        )

    lifecycle = replace(lifecycle, state=GameState.from_payload(state.to_payload()))
    state = _state(lifecycle)
    assert (
        damage_allocation_target_state(
            state=state,
            target_unit_instance_id=defender.unit_instance_id,
        )
        is DamageAllocationTargetState.PRESENT_WITHOUT_LIVING_MODELS
    )
    selection_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    declaration_request = _select_shooting_unit_and_type(
        lifecycle,
        selection_request=selection_request,
        unit_instance_id=attacker.unit_instance_id,
        selection_result_id="phase13e-fod-ranged-select",
    )
    proposal = _proposal_from_request(
        request=declaration_request,
        target_unit_id=defender.unit_instance_id,
    )

    status = _submit_payload(
        lifecycle,
        request=declaration_request,
        payload=proposal.to_payload(),
        result_id="phase13e-fod-ranged-declaration",
    )

    assert status.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
    }
    accepted = _last_event_payload(lifecycle, "shooting_declaration_accepted")
    assert (
        cast(list[dict[str, object]], accepted["attack_pools"])[0]["target_unit_instance_id"]
        == defender.unit_instance_id
    )
    assert _event_payloads(lifecycle, "attack_pool_not_allocated") == (
        {
            "sequence_id": "attack-sequence:phase13e-fod-ranged-declaration",
            "pool_index": 0,
            "target_unit_instance_id": defender.unit_instance_id,
            "reason": "target_present_without_living_models",
        },
    )
    assert _event_payloads(lifecycle, "attack_sequence_completed")


def test_phase13e_fight_target_enumeration_includes_fight_on_death_only_unit() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_pose=Pose.at(11.0, 35.0),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    battlefield = state.battlefield_state
    assert battlefield is not None
    awaiting_model = defender.own_models[0]
    awaiting_placement = battlefield.model_placement_by_id(awaiting_model.model_instance_id)
    _replace_unit_instance_in_state(
        state=state,
        replacement=replace(
            defender,
            own_models=tuple(replace(model, wounds_remaining=0) for model in defender.own_models),
        ),
    )
    state.replace_battlefield_state(
        battlefield.with_removed_models(
            tuple(model.model_instance_id for model in defender.own_models)
        )
    )
    restore_model_awaiting_fight_on_death(
        state=state,
        placement=awaiting_placement,
        effect_id="phase13e-fight-target-awaiting",
        source_rule_id="phase13e-fight-target-rule",
        source_phase=BattlePhase.FIGHT,
    )
    scenario = battlefield_scenario_for_state(state=state)

    assert melee_target_unit_ids(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_instance_id=attacker.unit_instance_id,
        state=state,
    ) == (defender.unit_instance_id,)


def test_phase13e_mixed_fight_on_death_target_replays_geometry_and_living_allocation() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    battlefield = state.battlefield_state
    assert battlefield is not None
    awaiting_model = defender.own_models[0]
    awaiting_placement = battlefield.model_placement_by_id(awaiting_model.model_instance_id)
    replacement = replace(
        defender,
        own_models=(
            replace(awaiting_model, wounds_remaining=0),
            *defender.own_models[1:],
        ),
    )
    _replace_unit_instance_in_state(state=state, replacement=replacement)
    state.replace_battlefield_state(
        battlefield.with_removed_models((awaiting_model.model_instance_id,))
    )
    restore_model_awaiting_fight_on_death(
        state=state,
        placement=awaiting_placement,
        effect_id="phase13e-mixed-target-awaiting",
        source_rule_id="phase13e-mixed-target-rule",
        source_phase=BattlePhase.SHOOTING,
    )
    scenario = battlefield_scenario_for_state(state=state)
    weapon_profile = _first_weapon_profile(lifecycle, attacker)
    candidate = shooting_target_candidates_for_unit(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=attacker,
        weapon_profile=weapon_profile,
        target_unit_ids=(defender.unit_instance_id,),
    )[0]
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=defender.unit_instance_id,
    )

    assert candidate.is_legal
    assert awaiting_model.model_instance_id in candidate.target_in_range_model_ids
    assert awaiting_model.model_instance_id in candidate.target_visible_model_ids
    assert awaiting_model.model_instance_id not in allocation_context.alive_model_ids
    assert allocation_context.alive_model_ids == tuple(
        model.model_instance_id for model in replacement.own_models[1:]
    )
    assert BattlefieldScenario.from_payload(scenario.to_payload()) == scenario

    replayed_state = GameState.from_payload(state.to_payload())
    replayed_scenario = battlefield_scenario_for_state(state=replayed_state)
    replayed_attacker = (
        rules_unit_view_by_id(
            state=replayed_state,
            unit_instance_id=attacker.unit_instance_id,
        )
        .components[0]
        .unit
    )
    replayed_candidate = shooting_target_candidates_for_unit(
        scenario=replayed_scenario,
        ruleset_descriptor=_ruleset(),
        attacker_unit=replayed_attacker,
        weapon_profile=weapon_profile,
        target_unit_ids=(defender.unit_instance_id,),
    )[0]
    replayed_allocation_context = allocation_context_for_unit(
        state=replayed_state,
        target_unit_instance_id=defender.unit_instance_id,
    )

    assert replayed_candidate.to_payload() == candidate.to_payload()
    assert replayed_allocation_context.to_payload() == allocation_context.to_payload()


def test_phase13e_deadly_demise_is_mandatory_and_not_a_decline_choice() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    deadly_demise_source = DestructionReactionSource(
        source_id="phase13e-deadly-demise",
        reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
        source_rule_id="phase13e-deadly-demise-rule",
        payload={
            "trigger_roll_threshold": 6,
            "range_inches": 6.0,
            "mortal_wounds": {"kind": "fixed", "value": 1},
        },
        optional=False,
    )
    state.record_model_destruction_reaction_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(deadly_demise_source,),
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        damage_profile=DamageProfile.fixed(defender_model.wounds_remaining),
    )
    sequence = AttackSequence.start(
        sequence_id="phase13e-deadly-demise-reaction",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=sequence.attack_pools,
        attack_sequence=sequence,
    )
    attack_context_id = "phase13e-deadly-demise-reaction:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )
    deadly_demise_spec = deadly_demise_trigger_roll_spec(
        source=deadly_demise_source,
        player_id="player-b",
        model_instance_id=defender_model.model_instance_id,
    )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase13e-deadly-demise-reaction",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id="phase13e-deadly-hit", spec=hit_spec, value=6),
                _fixed_roll_result(roll_id="phase13e-deadly-wound", spec=wound_spec, value=6),
                _fixed_roll_result(roll_id="phase13e-deadly-save", spec=save_spec, value=1),
                _fixed_roll_result(
                    roll_id="phase13e-deadly-demise-failed",
                    spec=deadly_demise_spec,
                    value=1,
                ),
            ),
        ),
    )
    reaction_payload = _last_event_payload(lifecycle, "destruction_reaction_resolved")
    selected_source = cast(dict[str, object], reaction_payload["selected_source"])
    deadly_demise_payload = cast(dict[str, object], reaction_payload["deadly_demise"])
    updated_battlefield = state.battlefield_state
    assert updated_battlefield is not None

    assert remaining_sequence is None
    assert allocated_ids == (defender_model.model_instance_id,)
    assert status is None
    assert lifecycle.decision_controller.queue.pending_requests == ()
    assert not any(
        record.result.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE
        for record in lifecycle.decision_controller.records
    )
    assert reaction_payload["resolution_kind"] == "mandatory"
    assert reaction_payload["decision"] is None
    assert selected_source["source_id"] == deadly_demise_source.source_id
    assert selected_source["reaction_kind"] == DestructionReactionKind.DEADLY_DEMISE.value
    assert selected_source["optional"] is False
    assert reaction_payload["action_host"] == "destruction_reaction"
    assert reaction_payload["execution_status"] == "resolved_no_effect"
    assert deadly_demise_payload["triggered"] is False
    assert _event_payloads(lifecycle, "deadly_demise_mortal_wounds_applied") == ()
    assert defender_model.model_instance_id not in updated_battlefield.placed_model_ids()
    event_types = tuple(
        event.event_type for event in lifecycle.decision_controller.event_log.records
    )
    assert event_types.index("destruction_reaction_resolved") < event_types.index("model_destroyed")


@pytest.mark.slow
def test_phase14h_destroyed_transport_disembarks_before_removal_and_deadly_demise() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        game_id="phase14h-destroyed-transport",
        enemy_unit_specs=(
            ("enemy-transport", "core-transport", "core-transport", 1),
            ("enemy-passenger", "core-intercessor-like-infantry", "core-intercessor-like", 5),
        ),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    transport = units["enemy-transport"]
    passenger = units["enemy-passenger"]
    transport_model = transport.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.without_unit_placement(passenger.unit_instance_id)
    state.record_transport_cargo_state(
        TransportCargoState(
            player_id="player-b",
            transport_unit_instance_id=transport.unit_instance_id,
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=transport.datasheet_id,
                max_model_count=10,
                allowed_keywords=("INFANTRY",),
            ),
            embarked_unit_instance_ids=(passenger.unit_instance_id,),
            phase_battle_round=1,
            started_phase_embarked_unit_instance_ids=(passenger.unit_instance_id,),
        )
    )
    deadly_demise_source = DestructionReactionSource(
        source_id="phase14h-transport-deadly-demise",
        reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
        source_rule_id="phase14h-transport-deadly-demise-rule",
        payload={
            "trigger_roll_threshold": 6,
            "range_inches": 0.1,
            "mortal_wounds": {"kind": "fixed", "value": 1},
        },
        optional=False,
    )
    state.record_model_destruction_reaction_sources(
        model_instance_id=transport_model.model_instance_id,
        sources=(deadly_demise_source,),
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
        damage_profile=DamageProfile.fixed(transport_model.wounds_remaining),
    )
    sequence_id = "phase14h-destroyed-transport"
    sequence = AttackSequence.start(
        sequence_id=sequence_id,
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=transport,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=sequence.attack_pools,
        attack_sequence=sequence,
    )
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=transport_model.model_instance_id,
        attack_context_id=attack_context_id,
    )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14h-destroyed-transport",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14h-destroyed-transport-hit",
                    spec=hit_spec,
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14h-destroyed-transport-wound",
                    spec=wound_spec,
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14h-destroyed-transport-save",
                    spec=save_spec,
                    value=1,
                ),
            ),
        ),
    )
    request = _decision_request(cast(LifecycleStatus, status))
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    proposal_context = proposal_request.context or {}
    battlefield_before_disembark = state.battlefield_state
    assert battlefield_before_disembark is not None
    state.shooting_phase_state = state.shooting_phase_state.with_attack_sequence_update(
        attack_sequence=remaining_sequence,
        allocated_model_ids_this_phase=allocated_ids,
    )

    assert request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
    assert request.actor_id == "player-b"
    assert proposal_request.unit_instance_id == passenger.unit_instance_id
    assert proposal_context["destruction_timing"] == "destroyed_transport"
    assert proposal_context["disembark_mode"] == (DisembarkModeKind.EMERGENCY_DISEMBARK.value)
    assert proposal_context["transport_unit_instance_id"] == transport.unit_instance_id
    assert transport_model.model_instance_id in battlefield_before_disembark.placed_model_ids()
    assert not any(
        payload["model_instance_id"] == transport_model.model_instance_id
        for payload in _event_payloads(lifecycle, "model_destroyed")
    )

    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-beta",
        player_id="player-b",
        poses=(
            Pose.at(38.1, 33.5),
            Pose.at(39.0, 34.8),
            Pose.at(39.0, 36.2),
            Pose.at(38.1, 37.5),
            Pose.at(37.8, 35.5),
        ),
    )
    placement_payload = PlacementProposalPayload(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        unit_instance_id=passenger.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_placement=attempted_placement,
        transport_unit_instance_id=transport.unit_instance_id,
        disembark_mode=DisembarkModeKind.EMERGENCY_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
    ).to_payload()

    _submit_payload(
        lifecycle,
        request=request,
        payload=placement_payload,
        result_id="phase14h-destroyed-transport-emergency-placement",
    )
    updated_battlefield = state.battlefield_state
    assert updated_battlefield is not None
    disembarked_state = state.disembarked_unit_state_for_unit(
        player_id="player-b",
        battle_round=1,
        unit_instance_id=passenger.unit_instance_id,
    )
    event_records = lifecycle.decision_controller.event_log.records
    event_types = tuple(record.event_type for record in event_records)
    unit_disembarked_event = next(
        record for record in event_records if record.event_type == "unit_disembarked"
    )
    hazard_event = next(
        record
        for record in event_records
        if record.event_type == TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE
    )
    deadly_demise_event = next(
        record for record in event_records if record.event_type == "destruction_reaction_resolved"
    )
    transport_destroyed_event = next(
        record
        for record in event_records
        if record.event_type == "model_destroyed"
        and cast(dict[str, object], record.payload)["model_instance_id"]
        == transport_model.model_instance_id
    )

    assert transport_model.model_instance_id not in updated_battlefield.placed_model_ids()
    assert state.transport_cargo_state_for_transport(transport.unit_instance_id) is None
    assert disembarked_state is not None
    assert disembarked_state.disembark_mode is DisembarkModeKind.EMERGENCY_DISEMBARK
    assert disembarked_state.battle_shocked_until == "end_of_turn"
    assert event_types.index("destroyed_transport_disembark_placement_requested") < (
        event_records.index(unit_disembarked_event)
    )
    assert event_records.index(unit_disembarked_event) < event_records.index(hazard_event)
    assert event_records.index(hazard_event) < event_records.index(deadly_demise_event)
    assert event_records.index(deadly_demise_event) < event_records.index(transport_destroyed_event)


@pytest.mark.slow
def test_phase14h_pending_destroyed_transport_state_round_trips_and_rejects_drift() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        game_id="phase14h-pending-destroyed-transport",
        enemy_unit_specs=(
            ("enemy-transport", "core-transport", "core-transport", 1),
            ("enemy-passenger", "core-intercessor-like-infantry", "core-intercessor-like", 5),
        ),
    )
    attacker = units["intercessor-1"]
    transport = units["enemy-transport"]
    passenger = units["enemy-passenger"]
    pending = _destroyed_transport_pending_for_test(
        sequence_id="phase14h-pending-destroyed-transport",
        attacker=attacker,
        transport=transport,
        passenger=passenger,
    )
    sequence = AttackSequence.start(
        sequence_id="phase14h-pending-destroyed-transport",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=transport,
                weapon_profile=_first_weapon_profile(lifecycle, attacker),
                attacks=1,
            ),
        ),
    ).with_pending_destroyed_transport_disembark(pending)
    rehydrated = AttackSequence.from_payload(sequence.to_payload())
    without_pending = rehydrated.without_pending_destroyed_transport_disembark()
    non_destroyed_damage = DamageApplication(
        target_unit_instance_id=transport.unit_instance_id,
        model_instance_id=transport.own_models[0].model_instance_id,
        damage_kind=DamageKind.NORMAL,
        requested_damage=1,
        wounds_lost=0,
        excess_damage_lost=1,
        starting_wounds_remaining=transport.own_models[0].wounds_remaining,
        final_wounds_remaining=transport.own_models[0].wounds_remaining,
        destroyed=False,
    )
    drifted_damage = DamageApplication(
        target_unit_instance_id=passenger.unit_instance_id,
        model_instance_id=transport.own_models[0].model_instance_id,
        damage_kind=DamageKind.NORMAL,
        requested_damage=transport.own_models[0].wounds_remaining,
        wounds_lost=transport.own_models[0].wounds_remaining,
        excess_damage_lost=0,
        starting_wounds_remaining=transport.own_models[0].wounds_remaining,
        final_wounds_remaining=0,
        destroyed=True,
    )

    assert pending.next_unit_instance_id == passenger.unit_instance_id
    assert PendingDestroyedTransportDisembark.from_payload(pending.to_payload()) == pending
    assert rehydrated.pending_destroyed_transport_disembark == pending
    assert without_pending.pending_destroyed_transport_disembark is None
    with pytest.raises(GameLifecycleError, match="attack_context must be an object"):
        PendingDestroyedTransportDisembark(
            attack_context=cast(AttackResolutionContextPayload, "not-a-context"),
            damage_application=pending.damage_application,
            saving_throw_payload=pending.saving_throw_payload,
            feel_no_pain=pending.feel_no_pain,
            destroyed_model_controller_player_id=pending.destroyed_model_controller_player_id,
            transport_unit_instance_id=pending.transport_unit_instance_id,
            pending_unit_instance_ids=pending.pending_unit_instance_ids,
        )
    with pytest.raises(GameLifecycleError, match="damage_application must be DamageApplication"):
        PendingDestroyedTransportDisembark(
            attack_context=pending.attack_context,
            damage_application=cast(DamageApplication, pending.damage_application.to_payload()),
            saving_throw_payload=pending.saving_throw_payload,
            feel_no_pain=pending.feel_no_pain,
            destroyed_model_controller_player_id=pending.destroyed_model_controller_player_id,
            transport_unit_instance_id=pending.transport_unit_instance_id,
            pending_unit_instance_ids=pending.pending_unit_instance_ids,
        )
    with pytest.raises(GameLifecycleError, match="requires destroyed damage"):
        PendingDestroyedTransportDisembark(
            attack_context=pending.attack_context,
            damage_application=non_destroyed_damage,
            saving_throw_payload=pending.saving_throw_payload,
            feel_no_pain=pending.feel_no_pain,
            destroyed_model_controller_player_id=pending.destroyed_model_controller_player_id,
            transport_unit_instance_id=pending.transport_unit_instance_id,
            pending_unit_instance_ids=pending.pending_unit_instance_ids,
        )
    with pytest.raises(GameLifecycleError, match="damage target drift"):
        PendingDestroyedTransportDisembark(
            attack_context=pending.attack_context,
            damage_application=drifted_damage,
            saving_throw_payload=pending.saving_throw_payload,
            feel_no_pain=pending.feel_no_pain,
            destroyed_model_controller_player_id=pending.destroyed_model_controller_player_id,
            transport_unit_instance_id=pending.transport_unit_instance_id,
            pending_unit_instance_ids=pending.pending_unit_instance_ids,
        )
    with pytest.raises(GameLifecycleError, match="feel_no_pain must be FeelNoPainResolution"):
        PendingDestroyedTransportDisembark(
            attack_context=pending.attack_context,
            damage_application=pending.damage_application,
            saving_throw_payload=pending.saving_throw_payload,
            feel_no_pain=cast(FeelNoPainResolution, object()),
            destroyed_model_controller_player_id=pending.destroyed_model_controller_player_id,
            transport_unit_instance_id=pending.transport_unit_instance_id,
            pending_unit_instance_ids=pending.pending_unit_instance_ids,
        )
    with pytest.raises(GameLifecycleError, match="Resolved destroyed Transport disembark"):
        pending.with_resolved_disembark(cast(Any, object()))


@pytest.mark.slow
def test_phase14h_destroyed_transport_proposal_prevalidation_rejects_invalid_payloads() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        game_id="phase14h-destroyed-transport-prevalidation",
        enemy_unit_specs=(
            ("enemy-transport", "core-transport", "core-transport", 1),
            ("enemy-passenger", "core-intercessor-like-infantry", "core-intercessor-like", 5),
        ),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    transport = units["enemy-transport"]
    passenger = units["enemy-passenger"]
    pending = _destroyed_transport_pending_for_test(
        sequence_id="phase14h-destroyed-transport-prevalidation",
        attacker=attacker,
        transport=transport,
        passenger=passenger,
    )
    base_sequence = AttackSequence.start(
        sequence_id="phase14h-destroyed-transport-prevalidation",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=transport,
                weapon_profile=_first_weapon_profile(lifecycle, attacker),
                attacks=1,
            ),
        ),
    )
    sequence = base_sequence.with_pending_destroyed_transport_disembark(pending)
    request = _destroyed_transport_proposal_request_for_test(
        state=state,
        pending=pending,
        sequence=sequence,
        unit_instance_id=passenger.unit_instance_id,
        request_id="phase14h-destroyed-transport-placement",
    )
    valid_payload = _destroyed_transport_placement_payload_for_test(
        proposal_request=MovementProposalRequest.from_decision_request_payload(request.payload),
        unit=passenger,
        transport=transport,
    )

    assert is_destroyed_transport_disembark_proposal_request(request)
    assert (
        invalid_destroyed_transport_disembark_proposal_status(
            state=state,
            request=request,
            result=_proposal_decision_result(
                request=request,
                payload=valid_payload,
                result_id="phase14h-destroyed-transport-valid",
            ),
            decisions=lifecycle.decision_controller,
            attack_sequence=sequence,
        )
        is None
    )

    missing_context_status = invalid_destroyed_transport_disembark_proposal_status(
        state=state,
        request=request,
        result=_proposal_decision_result(
            request=request,
            payload=valid_payload,
            result_id="phase14h-destroyed-transport-no-context",
        ),
        decisions=lifecycle.decision_controller,
        attack_sequence=base_sequence,
    )
    malformed_payload = dict(valid_payload)
    malformed_payload.pop("attempted_placement")
    malformed_status = invalid_destroyed_transport_disembark_proposal_status(
        state=state,
        request=request,
        result=_proposal_decision_result(
            request=request,
            payload=malformed_payload,
            result_id="phase14h-destroyed-transport-malformed",
        ),
        decisions=lifecycle.decision_controller,
        attack_sequence=sequence,
    )
    stale_payload = dict(valid_payload)
    stale_payload["proposal_request_id"] = "phase14h-destroyed-transport-stale"
    stale_status = invalid_destroyed_transport_disembark_proposal_status(
        state=state,
        request=request,
        result=_proposal_decision_result(
            request=request,
            payload=stale_payload,
            result_id="phase14h-destroyed-transport-stale",
        ),
        decisions=lifecycle.decision_controller,
        attack_sequence=sequence,
    )
    incomplete_payload = dict(valid_payload)
    incomplete_payload.pop("transport_unit_instance_id")
    incomplete_status = invalid_destroyed_transport_disembark_proposal_status(
        state=state,
        request=request,
        result=_proposal_decision_result(
            request=request,
            payload=incomplete_payload,
            result_id="phase14h-destroyed-transport-incomplete",
        ),
        decisions=lifecycle.decision_controller,
        attack_sequence=sequence,
    )
    drifted_request = _destroyed_transport_proposal_request_for_test(
        state=state,
        pending=pending,
        sequence=sequence,
        unit_instance_id=transport.unit_instance_id,
        request_id="phase14h-destroyed-transport-drifted-unit",
    )
    drifted_payload = _destroyed_transport_placement_payload_for_test(
        proposal_request=MovementProposalRequest.from_decision_request_payload(
            drifted_request.payload
        ),
        unit=transport,
        transport=transport,
    )
    drifted_status = invalid_destroyed_transport_disembark_proposal_status(
        state=state,
        request=drifted_request,
        result=_proposal_decision_result(
            request=drifted_request,
            payload=drifted_payload,
            result_id="phase14h-destroyed-transport-unit-drift",
        ),
        decisions=lifecycle.decision_controller,
        attack_sequence=sequence,
    )
    transport_drift_payload = dict(valid_payload)
    transport_drift_payload["transport_unit_instance_id"] = passenger.unit_instance_id
    transport_drift_status = invalid_destroyed_transport_disembark_proposal_status(
        state=state,
        request=request,
        result=_proposal_decision_result(
            request=request,
            payload=transport_drift_payload,
            result_id="phase14h-destroyed-transport-transport-drift",
        ),
        decisions=lifecycle.decision_controller,
        attack_sequence=sequence,
    )
    base_proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    mode_drift_request = replace(
        base_proposal_request,
        request_id="phase14h-destroyed-transport-mode-drift",
        context={
            **dict(base_proposal_request.context or {}),
            "allowed_disembark_modes": [DisembarkModeKind.RAPID_DISEMBARK.value],
        },
    ).to_decision_request()
    mode_drift_payload = _destroyed_transport_placement_payload_for_test(
        proposal_request=MovementProposalRequest.from_decision_request_payload(
            mode_drift_request.payload
        ),
        unit=passenger,
        transport=transport,
    )
    mode_drift_payload["disembark_mode"] = DisembarkModeKind.RAPID_DISEMBARK.value
    mode_drift_status = invalid_destroyed_transport_disembark_proposal_status(
        state=state,
        request=mode_drift_request,
        result=_proposal_decision_result(
            request=mode_drift_request,
            payload=mode_drift_payload,
            result_id="phase14h-destroyed-transport-mode-drift",
        ),
        decisions=lifecycle.decision_controller,
        attack_sequence=sequence,
    )
    status_drift_request = replace(
        base_proposal_request,
        request_id="phase14h-destroyed-transport-status-drift",
        context={
            **dict(base_proposal_request.context or {}),
            "transport_movement_status": TransportMovementStatus.NORMAL_MOVE.value,
        },
    ).to_decision_request()
    status_drift_payload = _destroyed_transport_placement_payload_for_test(
        proposal_request=MovementProposalRequest.from_decision_request_payload(
            status_drift_request.payload
        ),
        unit=passenger,
        transport=transport,
    )
    status_drift_payload["transport_movement_status"] = TransportMovementStatus.NORMAL_MOVE.value
    status_drift_status = invalid_destroyed_transport_disembark_proposal_status(
        state=state,
        request=status_drift_request,
        result=_proposal_decision_result(
            request=status_drift_request,
            payload=status_drift_payload,
            result_id="phase14h-destroyed-transport-status-drift",
        ),
        decisions=lifecycle.decision_controller,
        attack_sequence=sequence,
    )
    invalid_events = _event_payloads(
        lifecycle,
        "destroyed_transport_disembark_proposal_invalid",
    )

    _assert_invalid_proposal_status(
        missing_context_status,
        expected_code="destroyed_transport_context_missing",
        expected_field=None,
    )
    _assert_invalid_proposal_status(
        malformed_status,
        expected_code="proposal_payload_missing_field",
        expected_field="attempted_placement",
    )
    _assert_invalid_proposal_status(
        stale_status,
        expected_code="stale_proposal_request",
        expected_field="proposal_request_id",
    )
    _assert_invalid_proposal_status(
        incomplete_status,
        expected_code="proposal_payload_missing_field",
        expected_field="transport_unit_instance_id",
    )
    _assert_invalid_proposal_status(
        drifted_status,
        expected_code="destroyed_transport_unit_drift",
        expected_field="unit_instance_id",
    )
    _assert_invalid_proposal_status(
        transport_drift_status,
        expected_code="destroyed_transport_transport_drift",
        expected_field="transport_unit_instance_id",
    )
    _assert_invalid_proposal_status(
        mode_drift_status,
        expected_code="destroyed_transport_mode_drift",
        expected_field="disembark_mode",
    )
    _assert_invalid_proposal_status(
        status_drift_status,
        expected_code="destroyed_transport_status_drift",
        expected_field="transport_movement_status",
    )
    assert len(invalid_events) == 8


def test_phase14h_destroyed_transport_fail_fast_guards_preserve_state_requirements() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        game_id="phase14h-destroyed-transport-fail-fast",
        enemy_unit_specs=(
            ("enemy-transport", "core-transport", "core-transport", 1),
            ("enemy-passenger", "core-intercessor-like-infantry", "core-intercessor-like", 5),
        ),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    transport = units["enemy-transport"]
    passenger = units["enemy-passenger"]
    pending = _destroyed_transport_pending_for_test(
        sequence_id="phase14h-destroyed-transport-fail-fast",
        attacker=attacker,
        transport=transport,
        passenger=passenger,
    )
    sequence = AttackSequence.start(
        sequence_id="phase14h-destroyed-transport-fail-fast",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=transport,
                weapon_profile=_first_weapon_profile(lifecycle, attacker),
                attacks=1,
            ),
        ),
    )
    request = _destroyed_transport_proposal_request_for_test(
        state=state,
        pending=pending,
        sequence=sequence,
        unit_instance_id=passenger.unit_instance_id,
        request_id="phase14h-destroyed-transport-fail-fast-placement",
    )
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    attempted_placement = _unit_placement_at(
        passenger,
        army_id="army-beta",
        player_id="player-b",
        poses=tuple(
            Pose.at(38.0 + (0.7 * index), 34.0 + (0.5 * index))
            for index, _model in enumerate(passenger.own_models)
        ),
    )
    submission_without_mode = PlacementProposalPayload(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        unit_instance_id=passenger.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_placement=attempted_placement,
        transport_unit_instance_id=transport.unit_instance_id,
        disembark_mode=None,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
    )
    submission_without_cargo = replace(
        submission_without_mode,
        disembark_mode=DisembarkModeKind.EMERGENCY_DISEMBARK,
    )
    continue_pending = _attack_sequence_private("_continue_pending_destroyed_transport_disembark")
    request_placement = _attack_sequence_private("_request_destroyed_transport_disembark_placement")
    remove_cargo = _attack_sequence_private("_remove_resolved_destroyed_transport_cargo_state")
    cargo_for_damage = _attack_sequence_private("_destroyed_transport_cargo_state_for_damage")
    resolve_submission = _attack_sequence_private(
        "_resolve_destroyed_transport_disembark_submission"
    )
    retry_request = _attack_sequence_private(
        "_request_destroyed_transport_disembark_placement_retry"
    )
    transport_placement = _attack_sequence_private("_destroyed_transport_placement")
    battlefield_scenario = _attack_sequence_private("_battlefield_scenario_for_attack_sequence")
    objective_markers = _attack_sequence_private("_objective_markers_for_attack_sequence")

    with pytest.raises(GameLifecycleError, match="continuation requires pending state"):
        continue_pending(
            state=state,
            decisions=lifecycle.decision_controller,
            ruleset_descriptor=_ruleset(),
            manager=DiceRollManager("phase14h-fail-fast"),
            attack_sequence=sequence,
            allocated_model_ids=(),
            hooks=AttackSequenceHooks.empty(),
        )
    with pytest.raises(GameLifecycleError, match="requires pending cargo"):
        request_placement(
            state=state,
            decisions=lifecycle.decision_controller,
            attack_sequence=sequence,
            pending=replace(pending, pending_unit_instance_ids=()),
        )
    with pytest.raises(GameLifecycleError, match="cargo state is missing before removal"):
        remove_cargo(
            state=state,
            transport_unit_instance_id=transport.unit_instance_id,
        )
    state.record_transport_cargo_state(
        TransportCargoState(
            player_id="player-b",
            transport_unit_instance_id=transport.unit_instance_id,
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=transport.datasheet_id,
                max_model_count=10,
                allowed_keywords=("INFANTRY",),
            ),
            embarked_unit_instance_ids=(passenger.unit_instance_id,),
            phase_battle_round=1,
            started_phase_embarked_unit_instance_ids=(passenger.unit_instance_id,),
        )
    )
    with pytest.raises(GameLifecycleError, match="cargo state still has embarked units"):
        remove_cargo(
            state=state,
            transport_unit_instance_id=transport.unit_instance_id,
        )
    with pytest.raises(GameLifecycleError, match="Destroyed model is not in the damaged unit"):
        cargo_for_damage(
            state=state,
            damage=replace(
                pending.damage_application,
                model_instance_id=passenger.own_models[0].model_instance_id,
            ),
        )
    with pytest.raises(GameLifecycleError, match="submission is incomplete"):
        resolve_submission(
            state=state,
            ruleset_descriptor=_ruleset(),
            pending=pending,
            submission=submission_without_mode,
            dice_manager=DiceRollManager("phase14h-fail-fast-incomplete"),
        )
    state_without_cargo = _state(
        _shooting_lifecycle(
            alpha_unit_ids=("intercessor-1",),
            game_id="phase14h-destroyed-transport-no-cargo",
            enemy_unit_specs=(
                ("enemy-transport", "core-transport", "core-transport", 1),
                ("enemy-passenger", "core-intercessor-like-infantry", "core-intercessor-like", 5),
            ),
        )[0]
    )
    with pytest.raises(GameLifecycleError, match="cargo state is missing"):
        resolve_submission(
            state=state_without_cargo,
            ruleset_descriptor=_ruleset(),
            pending=pending,
            submission=submission_without_cargo,
            dice_manager=DiceRollManager("phase14h-fail-fast-no-cargo"),
        )
    with pytest.raises(GameLifecycleError, match="retry missing attack_sequence_id"):
        retry_request(
            state=state,
            decisions=lifecycle.decision_controller,
            proposal_request=replace(
                proposal_request,
                context={"destruction_timing": "destroyed_transport"},
            ),
            pending=pending,
            rejected_result=_proposal_decision_result(
                request=proposal_request.to_decision_request(),
                payload=submission_without_cargo.to_payload(),
                result_id="phase14h-destroyed-transport-retry-missing-sequence",
            ),
        )
    with pytest.raises(GameLifecycleError, match="retry missing attack_context_id"):
        retry_request(
            state=state,
            decisions=lifecycle.decision_controller,
            proposal_request=replace(
                proposal_request,
                context={
                    "destruction_timing": "destroyed_transport",
                    "attack_sequence_id": sequence.sequence_id,
                },
            ),
            pending=pending,
            rejected_result=_proposal_decision_result(
                request=proposal_request.to_decision_request(),
                payload=submission_without_cargo.to_payload(),
                result_id="phase14h-destroyed-transport-retry-missing-context",
            ),
        )

    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = None
    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        transport_placement(state=state, pending=pending)
    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        battlefield_scenario(state)
    state.mission_setup = None
    assert objective_markers(state) == ()
    state.battlefield_state = battlefield.without_unit_placement(transport.unit_instance_id)
    with pytest.raises(GameLifecycleError, match="must still be placed"):
        transport_placement(state=state, pending=pending)


@pytest.mark.slow
def test_phase14h_destroyed_transport_invalid_placement_retries_before_removal() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        game_id="phase14h-destroyed-transport-invalid-retry",
        enemy_unit_specs=(
            ("enemy-transport", "core-transport", "core-transport", 1),
            ("enemy-passenger", "core-intercessor-like-infantry", "core-intercessor-like", 5),
        ),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    transport = units["enemy-transport"]
    passenger = units["enemy-passenger"]
    transport_model = transport.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.without_unit_placement(passenger.unit_instance_id)
    state.record_transport_cargo_state(
        TransportCargoState(
            player_id="player-b",
            transport_unit_instance_id=transport.unit_instance_id,
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=transport.datasheet_id,
                max_model_count=10,
                allowed_keywords=("INFANTRY",),
            ),
            embarked_unit_instance_ids=(passenger.unit_instance_id,),
            phase_battle_round=1,
            started_phase_embarked_unit_instance_ids=(passenger.unit_instance_id,),
        )
    )
    pending = _destroyed_transport_pending_for_test(
        sequence_id="phase14h-destroyed-transport-invalid-retry",
        attacker=attacker,
        transport=transport,
        passenger=passenger,
    )
    sequence = AttackSequence.start(
        sequence_id="phase14h-destroyed-transport-invalid-retry",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=transport,
                weapon_profile=_first_weapon_profile(lifecycle, attacker),
                attacks=1,
            ),
        ),
    ).with_pending_destroyed_transport_disembark(pending)
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=sequence.attack_pools,
        attack_sequence=sequence,
    )
    request = _destroyed_transport_proposal_request_for_test(
        state=state,
        pending=pending,
        sequence=sequence,
        unit_instance_id=passenger.unit_instance_id,
        request_id=state.next_decision_request_id(),
    )
    lifecycle.decision_controller.request_decision(request)
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    invalid_placement_payload = PlacementProposalPayload(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        unit_instance_id=passenger.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_placement=_unit_placement_at(
            passenger,
            army_id="army-beta",
            player_id="player-b",
            poses=tuple(
                Pose.at(1.0 + (1.0 * index), 1.0 + (0.3 * index))
                for index, _model in enumerate(passenger.own_models)
            ),
        ),
        transport_unit_instance_id=transport.unit_instance_id,
        disembark_mode=DisembarkModeKind.EMERGENCY_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
    ).to_payload()

    status = _submit_payload(
        lifecycle,
        request=request,
        payload=invalid_placement_payload,
        result_id="phase14h-destroyed-transport-invalid-placement",
    )
    retry_request = lifecycle.decision_controller.queue.pending_requests[0]
    retry_proposal = MovementProposalRequest.from_decision_request_payload(retry_request.payload)
    invalid_event = _last_event_payload(
        lifecycle,
        "destroyed_transport_disembark_placement_invalid",
    )
    retry_event = _last_event_payload(
        lifecycle,
        "destroyed_transport_disembark_placement_requested",
    )
    battlefield_after_invalid = state.battlefield_state
    assert battlefield_after_invalid is not None

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert retry_request.request_id != request.request_id
    assert retry_proposal.unit_instance_id == passenger.unit_instance_id
    assert retry_event["previous_proposal_request_id"] == request.request_id
    assert retry_event["rejected_result_id"] == "phase14h-destroyed-transport-invalid-placement"
    assert invalid_event["phase_body_status"] == "invalid"
    assert transport_model.model_instance_id in battlefield_after_invalid.placed_model_ids()
    assert state.transport_cargo_state_for_transport(transport.unit_instance_id) is not None
    assert not any(
        payload["model_instance_id"] == transport_model.model_instance_id
        for payload in _event_payloads(lifecycle, "model_destroyed")
    )


@pytest.mark.slow
def test_phase14h_destroyed_transport_requests_each_embarked_unit_before_removal() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        game_id="phase14h-destroyed-transport-multi-cargo",
        enemy_unit_specs=(
            ("enemy-transport", "core-transport", "core-transport", 1),
            ("enemy-passenger-a", "core-intercessor-like-infantry", "core-intercessor-like", 5),
            ("enemy-passenger-b", "core-intercessor-like-infantry", "core-intercessor-like", 5),
        ),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    transport = units["enemy-transport"]
    passenger_a = units["enemy-passenger-a"]
    passenger_b = units["enemy-passenger-b"]
    transport_model = transport.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.without_unit_placement(
        passenger_a.unit_instance_id
    ).without_unit_placement(passenger_b.unit_instance_id)
    state.record_transport_cargo_state(
        TransportCargoState(
            player_id="player-b",
            transport_unit_instance_id=transport.unit_instance_id,
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=transport.datasheet_id,
                max_model_count=10,
                allowed_keywords=("INFANTRY",),
            ),
            embarked_unit_instance_ids=(
                passenger_a.unit_instance_id,
                passenger_b.unit_instance_id,
            ),
            phase_battle_round=1,
            started_phase_embarked_unit_instance_ids=(
                passenger_a.unit_instance_id,
                passenger_b.unit_instance_id,
            ),
        )
    )
    pending = replace(
        _destroyed_transport_pending_for_test(
            sequence_id="phase14h-destroyed-transport-multi-cargo",
            attacker=attacker,
            transport=transport,
            passenger=passenger_a,
        ),
        pending_unit_instance_ids=(passenger_a.unit_instance_id, passenger_b.unit_instance_id),
    )
    sequence = AttackSequence.start(
        sequence_id="phase14h-destroyed-transport-multi-cargo",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=transport,
                weapon_profile=_first_weapon_profile(lifecycle, attacker),
                attacks=1,
            ),
        ),
    ).with_pending_destroyed_transport_disembark(pending)
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=sequence.attack_pools,
        attack_sequence=sequence,
    )
    request = _destroyed_transport_proposal_request_for_test(
        state=state,
        pending=pending,
        sequence=sequence,
        unit_instance_id=passenger_a.unit_instance_id,
        request_id=state.next_decision_request_id(),
    )
    lifecycle.decision_controller.request_decision(request)
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    attempted_placement = _unit_placement_at(
        passenger_a,
        army_id="army-beta",
        player_id="player-b",
        poses=(
            Pose.at(38.1, 33.5),
            Pose.at(39.0, 34.8),
            Pose.at(39.0, 36.2),
            Pose.at(38.1, 37.5),
            Pose.at(37.8, 35.5),
        ),
    )
    result = _proposal_decision_result(
        request=request,
        payload=PlacementProposalPayload(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            unit_instance_id=passenger_a.unit_instance_id,
            placement_kind=BattlefieldPlacementKind.DISEMBARK,
            attempted_placement=attempted_placement,
            transport_unit_instance_id=transport.unit_instance_id,
            disembark_mode=DisembarkModeKind.EMERGENCY_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ).to_payload(),
        result_id="phase14h-destroyed-transport-passenger-a",
    )
    lifecycle.decision_controller.submit_result(result)

    updated_sequence, allocated_ids, status = apply_destroyed_transport_disembark_proposal_decision(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        result=result,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase14h-destroyed-transport-multi-cargo",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=_destroyed_transport_hazard_roll_results_for_test(
                attempted_placement,
                values=(6, 6, 6, 6, 6),
                roll_id_prefix="phase14h-destroyed-transport-passenger-a",
            ),
        ),
    )
    next_request = _decision_request(cast(LifecycleStatus, status))
    next_proposal_request = MovementProposalRequest.from_decision_request_payload(
        next_request.payload
    )
    cargo_state = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    battlefield_after_first_disembark = state.battlefield_state
    assert updated_sequence is not None
    assert battlefield_after_first_disembark is not None

    assert allocated_ids == ()
    assert next_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
    assert next_proposal_request.unit_instance_id == passenger_b.unit_instance_id
    assert updated_sequence.pending_destroyed_transport_disembark is not None
    assert (
        updated_sequence.pending_destroyed_transport_disembark.next_unit_instance_id
        == passenger_b.unit_instance_id
    )
    assert cargo_state is not None
    assert cargo_state.embarked_unit_instance_ids == (passenger_b.unit_instance_id,)
    assert transport_model.model_instance_id in battlefield_after_first_disembark.placed_model_ids()
    assert (
        state.disembarked_unit_state_for_unit(
            player_id="player-b",
            battle_round=1,
            unit_instance_id=passenger_a.unit_instance_id,
        )
        is not None
    )
    assert not any(
        payload["model_instance_id"] == transport_model.model_instance_id
        for payload in _event_payloads(lifecycle, "model_destroyed")
    )


def test_phase14h_destroyed_transport_apply_rejects_invalid_recorded_contexts() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        game_id="phase14h-destroyed-transport-apply-invalid",
        enemy_unit_specs=(
            ("enemy-transport", "core-transport", "core-transport", 1),
            ("enemy-passenger", "core-intercessor-like-infantry", "core-intercessor-like", 5),
        ),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    transport = units["enemy-transport"]
    passenger = units["enemy-passenger"]
    pending = _destroyed_transport_pending_for_test(
        sequence_id="phase14h-destroyed-transport-apply-invalid",
        attacker=attacker,
        transport=transport,
        passenger=passenger,
    )
    base_sequence = AttackSequence.start(
        sequence_id="phase14h-destroyed-transport-apply-invalid",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=transport,
                weapon_profile=_first_weapon_profile(lifecycle, attacker),
                attacks=1,
            ),
        ),
    )
    sequence = base_sequence.with_pending_destroyed_transport_disembark(pending)
    request = _destroyed_transport_proposal_request_for_test(
        state=state,
        pending=pending,
        sequence=sequence,
        unit_instance_id=passenger.unit_instance_id,
        request_id="phase14h-destroyed-transport-apply-request",
    )
    valid_payload = _destroyed_transport_placement_payload_for_test(
        proposal_request=MovementProposalRequest.from_decision_request_payload(request.payload),
        unit=passenger,
        transport=transport,
    )
    malformed_payload = dict(valid_payload)
    malformed_payload.pop("attempted_placement")
    malformed_result = _record_parameterized_result_for_apply(
        lifecycle,
        request=request,
        payload=malformed_payload,
        result_id="phase14h-destroyed-transport-apply-malformed",
    )

    same_sequence, allocated_ids, malformed_status = (
        apply_destroyed_transport_disembark_proposal_decision(
            state=state,
            decisions=lifecycle.decision_controller,
            ruleset_descriptor=_ruleset(),
            attack_sequence=sequence,
            result=malformed_result,
            already_allocated_model_ids=("already-allocated",),
        )
    )

    missing_pending_request = _destroyed_transport_proposal_request_for_test(
        state=state,
        pending=pending,
        sequence=sequence,
        unit_instance_id=passenger.unit_instance_id,
        request_id="phase14h-destroyed-transport-apply-no-pending",
    )
    missing_pending_result = _record_parameterized_result_for_apply(
        lifecycle,
        request=missing_pending_request,
        payload=valid_payload,
        result_id="phase14h-destroyed-transport-apply-no-pending",
    )
    incomplete_request = _destroyed_transport_proposal_request_for_test(
        state=state,
        pending=pending,
        sequence=sequence,
        unit_instance_id=passenger.unit_instance_id,
        request_id="phase14h-destroyed-transport-apply-incomplete",
    )
    incomplete_payload = dict(valid_payload)
    incomplete_payload["proposal_request_id"] = incomplete_request.request_id
    incomplete_payload.pop("transport_unit_instance_id")
    incomplete_result = _record_parameterized_result_for_apply(
        lifecycle,
        request=incomplete_request,
        payload=incomplete_payload,
        result_id="phase14h-destroyed-transport-apply-incomplete",
    )
    unsupported_request = DecisionRequest(
        request_id="phase14h-destroyed-transport-unsupported",
        decision_type="phase14h_destroyed_transport_unsupported",
        actor_id="player-b",
        payload={},
        options=(DecisionOption(option_id="noop", label="Noop", payload={}),),
    )
    lifecycle.decision_controller.request_decision(unsupported_request)
    unsupported_result = DecisionResult.for_request(
        result_id="phase14h-destroyed-transport-unsupported",
        request=unsupported_request,
        selected_option_id="noop",
    )
    lifecycle.decision_controller.submit_result(unsupported_result)

    assert same_sequence == sequence
    assert allocated_ids == ("already-allocated",)
    assert malformed_status is not None
    assert malformed_status.status_kind is LifecycleStatusKind.INVALID
    with pytest.raises(GameLifecycleError, match="requires pending state"):
        apply_destroyed_transport_disembark_proposal_decision(
            state=state,
            decisions=lifecycle.decision_controller,
            ruleset_descriptor=_ruleset(),
            attack_sequence=base_sequence,
            result=missing_pending_result,
            already_allocated_model_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="submission drifted"):
        apply_destroyed_transport_disembark_proposal_decision(
            state=state,
            decisions=lifecycle.decision_controller,
            ruleset_descriptor=_ruleset(),
            attack_sequence=sequence,
            result=incomplete_result,
            already_allocated_model_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="received unsupported request"):
        invalid_destroyed_transport_disembark_proposal_status(
            state=state,
            request=unsupported_request,
            result=unsupported_result,
            decisions=lifecycle.decision_controller,
            attack_sequence=sequence,
        )
    with pytest.raises(GameLifecycleError, match="routing requires a DecisionRequest"):
        is_destroyed_transport_disembark_proposal_request(cast(DecisionRequest, object()))
    with pytest.raises(GameLifecycleError, match="received unsupported request"):
        apply_destroyed_transport_disembark_proposal_decision(
            state=state,
            decisions=lifecycle.decision_controller,
            ruleset_descriptor=_ruleset(),
            attack_sequence=sequence,
            result=unsupported_result,
            already_allocated_model_ids=(),
        )


@pytest.mark.slow
def test_phase13e_successful_deadly_demise_applies_mortal_wounds_before_removal() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_pose=Pose.at(14.0, 35.0),
        catalog=_catalog_with_deadly_demise_datasheet(token="D3"),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    attacker_model = attacker.own_models[0]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    deadly_demise_source = _single_deadly_demise_source(
        state=state,
        model_instance_id=defender_model.model_instance_id,
    )
    assert deadly_demise_source.source_rule_id == (
        "datasheet:core-intercessor-like-infantry:ability:deadly-demise"
    )
    assert deadly_demise_source.payload == {
        "trigger_roll_threshold": 6,
        "range_inches": 6.0,
        "mortal_wounds": {"kind": "d3"},
    }
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        damage_profile=DamageProfile.fixed(defender_model.wounds_remaining),
    )
    sequence = AttackSequence.start(
        sequence_id="phase13e-success-deadly-demise",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=sequence.attack_pools,
        attack_sequence=sequence,
    )
    attack_context_id = "phase13e-success-deadly-demise:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )
    deadly_demise_spec = deadly_demise_trigger_roll_spec(
        source=deadly_demise_source,
        player_id="player-b",
        model_instance_id=defender_model.model_instance_id,
    )
    deadly_demise_mortal_wounds_spec = DiceRollManager.d3_source_spec(
        reason=(
            f"Deadly Demise mortal wounds for {deadly_demise_source.source_id} "
            f"into {attacker.unit_instance_id}"
        ),
        roll_type="destruction_reaction.deadly_demise.mortal_wounds",
        actor_id="player-b",
    )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase13e-success-deadly-demise",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id="phase13e-success-hit", spec=hit_spec, value=6),
                _fixed_roll_result(roll_id="phase13e-success-wound", spec=wound_spec, value=6),
                _fixed_roll_result(roll_id="phase13e-success-save", spec=save_spec, value=1),
                _fixed_roll_result(
                    roll_id="phase13e-success-deadly-demise",
                    spec=deadly_demise_spec,
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase13e-success-deadly-demise-d3",
                    spec=deadly_demise_mortal_wounds_spec,
                    value=3,
                ),
            ),
        ),
    )
    applied = _last_event_payload(lifecycle, "deadly_demise_mortal_wounds_applied")
    application = cast(dict[str, object], applied["mortal_wound_application"])
    applications = cast(list[dict[str, object]], application["applications"])
    updated_battlefield = state.battlefield_state
    assert updated_battlefield is not None

    assert remaining_sequence is None
    assert allocated_ids == (defender_model.model_instance_id,)
    assert status is None
    assert applied["target_unit_instance_id"] == attacker.unit_instance_id
    assert applications[0]["model_instance_id"] == attacker_model.model_instance_id
    assert applied["mortal_wounds"] == 2
    assert sum(cast(int, application["wounds_lost"]) for application in applications) == 2
    assert applications[0]["wounds_lost"] == 1
    assert (
        model_by_id(
            state=state, model_instance_id=attacker_model.model_instance_id
        ).wounds_remaining
        == 0
    )
    assert defender_model.model_instance_id not in updated_battlefield.placed_model_ids()
    event_types = tuple(
        event.event_type for event in lifecycle.decision_controller.event_log.records
    )
    assert event_types.index("deadly_demise_mortal_wounds_applied") < event_types.index(
        "model_destroyed"
    )


def test_phase13e_deadly_demise_descriptor_registers_sources_for_each_model() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        catalog=_catalog_with_deadly_demise_datasheet(token="2"),
    )
    state = _state(lifecycle)
    defender = units["enemy"]

    sources_by_model = {
        model.model_instance_id: state.destruction_reaction_sources_for_model(
            model_instance_id=model.model_instance_id
        )
        for model in defender.own_models
    }
    payload = cast(dict[str, object], state.to_payload())

    assert set(sources_by_model) == {model.model_instance_id for model in defender.own_models}
    for model in defender.own_models:
        sources = sources_by_model[model.model_instance_id]
        assert len(sources) == 1
        source = sources[0]
        assert source.source_id == (
            "datasheet:core-intercessor-like-infantry:ability:deadly-demise:"
            f"{model.model_instance_id}:deadly-demise"
        )
        assert source.reaction_kind is DestructionReactionKind.DEADLY_DEMISE
        assert source.source_rule_id == (
            "datasheet:core-intercessor-like-infantry:ability:deadly-demise"
        )
        assert source.optional is False
        assert source.payload == {
            "trigger_roll_threshold": 6,
            "range_inches": 6.0,
            "mortal_wounds": {"kind": "fixed", "value": 2},
        }
    assert "<" not in json.dumps(payload, sort_keys=True)
    assert "object at 0x" not in json.dumps(payload, sort_keys=True)
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()


def test_phase13c_feel_no_pain_descriptor_registers_sources_for_each_model() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        catalog=_catalog_with_core_feel_no_pain_datasheet(token="5+"),
    )
    state = _state(lifecycle)
    defender = units["enemy"]

    duplicate_sources = record_core_feel_no_pain_sources_for_unit(
        state=state,
        unit=defender,
    )
    sources_by_model = {
        model.model_instance_id: state.feel_no_pain_sources_for_model(
            model_instance_id=model.model_instance_id
        )
        for model in defender.own_models
    }
    payload = cast(dict[str, object], state.to_payload())

    assert unit_has_feel_no_pain(defender)
    assert len(duplicate_sources) == len(defender.own_models)
    assert set(sources_by_model) == {model.model_instance_id for model in defender.own_models}
    for model in defender.own_models:
        sources = sources_by_model[model.model_instance_id]
        assert len(sources) == 1
        source = sources[0]
        assert source.source_id == (
            "datasheet:core-intercessor-like-infantry:ability:feel-no-pain:"
            f"{model.model_instance_id}:feel-no-pain"
        )
        assert source.threshold == 5
        assert source.attack_condition is None
    assert "<" not in json.dumps(payload, sort_keys=True)
    assert "object at 0x" not in json.dumps(payload, sort_keys=True)
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()


def test_phase13c_feel_no_pain_keyword_without_descriptor_fails_fast() -> None:
    _lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    defender = replace(
        units["enemy"],
        keywords=(*units["enemy"].keywords, "Feel No Pain"),
    )

    with pytest.raises(GameLifecycleError, match="Feel No Pain keyword requires"):
        feel_no_pain_profile_for_unit(defender)


def test_phase13e_deadly_demise_fnp_pauses_before_destroyed_model_removal() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_pose=Pose.at(14.0, 35.0),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    attacker_model = attacker.own_models[0]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    state.record_model_feel_no_pain_sources(
        model_instance_id=attacker_model.model_instance_id,
        sources=(FeelNoPainSource(source_id="phase13e-deadly-demise-fnp", threshold=5),),
        decline_allowed=True,
    )
    deadly_demise_source = DestructionReactionSource(
        source_id="phase13e-fnp-deadly-demise",
        reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
        source_rule_id="phase13e-fnp-deadly-demise-rule",
        payload={
            "trigger_roll_threshold": 6,
            "range_inches": 6.0,
            "mortal_wounds": {"kind": "d6"},
        },
        optional=False,
    )
    state.record_model_destruction_reaction_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(deadly_demise_source,),
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        damage_profile=DamageProfile.fixed(defender_model.wounds_remaining),
    )
    sequence = AttackSequence.start(
        sequence_id="phase13e-fnp-deadly-demise",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=sequence.attack_pools,
        attack_sequence=sequence,
    )
    attack_context_id = "phase13e-fnp-deadly-demise:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )
    deadly_demise_spec = deadly_demise_trigger_roll_spec(
        source=deadly_demise_source,
        player_id="player-b",
        model_instance_id=defender_model.model_instance_id,
    )
    deadly_demise_mortal_wounds_spec = deadly_demise_mortal_wounds_roll_spec(
        source=deadly_demise_source,
        player_id="player-b",
        target_unit_instance_id=attacker.unit_instance_id,
        sides=6,
    )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase13e-fnp-deadly-demise",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id="phase13e-fnp-hit", spec=hit_spec, value=6),
                _fixed_roll_result(roll_id="phase13e-fnp-wound", spec=wound_spec, value=6),
                _fixed_roll_result(roll_id="phase13e-fnp-save", spec=save_spec, value=1),
                _fixed_roll_result(
                    roll_id="phase13e-fnp-deadly-demise",
                    spec=deadly_demise_spec,
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase13e-fnp-deadly-demise-mortal-wounds",
                    spec=deadly_demise_mortal_wounds_spec,
                    value=1,
                ),
            ),
        ),
    )
    request = _decision_request(cast(LifecycleStatus, status))
    battlefield_before_fnp = state.battlefield_state
    assert battlefield_before_fnp is not None
    state.shooting_phase_state = state.shooting_phase_state.with_attack_sequence_update(
        attack_sequence=remaining_sequence,
        allocated_model_ids_this_phase=allocated_ids,
    )

    assert request.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert defender_model.model_instance_id in battlefield_before_fnp.placed_model_ids()
    assert (
        model_by_id(
            state=state, model_instance_id=defender_model.model_instance_id
        ).wounds_remaining
        == 0
    )
    assert _event_payloads(lifecycle, "model_destroyed") == ()

    final_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase13e-fnp-decline-deadly-demise",
            request=request,
            selected_option_id="decline",
        )
    )
    updated_battlefield = state.battlefield_state
    assert updated_battlefield is not None

    _assert_waiting_for_movement_unit(final_status)
    assert defender_model.model_instance_id not in updated_battlefield.placed_model_ids()
    assert _event_payloads(lifecycle, "deadly_demise_mortal_wounds_applied")
    assert _event_payloads(lifecycle, "model_destroyed")


def test_phase13e_deadly_demise_secondary_casualty_gets_removal_record_and_reaction() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_pose=Pose.at(14.0, 35.0),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    attacker_model = attacker.own_models[0]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    secondary_reaction_source = DestructionReactionSource(
        source_id="phase13e-secondary-shoot-on-death",
        reaction_kind=DestructionReactionKind.SHOOT_ON_DEATH,
        source_rule_id="phase13e-secondary-shoot-on-death-rule",
    )
    state.record_model_destruction_reaction_sources(
        model_instance_id=attacker_model.model_instance_id,
        sources=(secondary_reaction_source,),
    )
    deadly_demise_source = DestructionReactionSource(
        source_id="phase13e-secondary-casualty-deadly-demise",
        reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
        source_rule_id="phase13e-secondary-casualty-deadly-demise-rule",
        payload={
            "trigger_roll_threshold": 6,
            "range_inches": 6.0,
            "mortal_wounds": {"kind": "fixed", "value": attacker_model.wounds_remaining},
        },
        optional=False,
    )
    state.record_model_destruction_reaction_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(deadly_demise_source,),
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        damage_profile=DamageProfile.fixed(defender_model.wounds_remaining),
    )
    sequence = AttackSequence.start(
        sequence_id="phase13e-secondary-casualty",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=sequence.attack_pools,
        attack_sequence=sequence,
    )
    attack_context_id = "phase13e-secondary-casualty:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )
    deadly_demise_spec = deadly_demise_trigger_roll_spec(
        source=deadly_demise_source,
        player_id="player-b",
        model_instance_id=defender_model.model_instance_id,
    )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase13e-secondary-casualty",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id="phase13e-secondary-hit", spec=hit_spec, value=6),
                _fixed_roll_result(roll_id="phase13e-secondary-wound", spec=wound_spec, value=6),
                _fixed_roll_result(roll_id="phase13e-secondary-save", spec=save_spec, value=1),
                _fixed_roll_result(
                    roll_id="phase13e-secondary-deadly-demise",
                    spec=deadly_demise_spec,
                    value=6,
                ),
            ),
        ),
    )
    request = _decision_request(cast(LifecycleStatus, status))
    destroyed_payloads = _event_payloads(lifecycle, "model_destroyed")
    secondary_destroyed_payloads = tuple(
        payload
        for payload in destroyed_payloads
        if payload["model_instance_id"] == attacker_model.model_instance_id
    )
    updated_battlefield = state.battlefield_state
    assert updated_battlefield is not None

    assert remaining_sequence is not None
    assert remaining_sequence.pending_grouped_damage is not None
    assert allocated_ids == (defender_model.model_instance_id,)
    assert request.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert {option.option_id for option in request.options} == {
        DECLINE_DESTRUCTION_REACTION_OPTION_ID,
        secondary_reaction_source.source_id,
    }
    assert len(secondary_destroyed_payloads) == 1
    secondary_destroyed = secondary_destroyed_payloads[0]
    removal_record = cast(dict[str, object], secondary_destroyed["removal_record"])
    transition_batch = cast(dict[str, object], secondary_destroyed["transition_batch"])
    assert removal_record["model_instance_id"] == attacker_model.model_instance_id
    assert removal_record["removal_kind"] == "destroyed"
    assert cast(list[object], transition_batch["removals"]) == [removal_record]
    assert attacker_model.model_instance_id not in updated_battlefield.placed_model_ids()
    assert defender_model.model_instance_id in updated_battlefield.placed_model_ids()

    shooting_state = state.shooting_phase_state
    assert shooting_state is not None
    state.shooting_phase_state = shooting_state.with_attack_sequence_update(
        attack_sequence=remaining_sequence,
        allocated_model_ids_this_phase=allocated_ids,
    )
    final_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase13e-secondary-shoot-on-death-selected",
            request=request,
            selected_option_id=secondary_reaction_source.source_id,
        )
    )
    final_battlefield = state.battlefield_state
    assert final_battlefield is not None
    final_destroyed_payloads = _event_payloads(lifecycle, "model_destroyed")
    final_reaction_payloads = _event_payloads(lifecycle, "destruction_reaction_resolved")
    secondary_reaction_payloads = tuple(
        payload
        for payload in final_reaction_payloads
        if cast(dict[str, object], payload["selected_source"])["source_id"]
        == secondary_reaction_source.source_id
    )
    primary_reaction_payloads = tuple(
        payload
        for payload in final_reaction_payloads
        if cast(dict[str, object], payload["selected_source"])["source_id"]
        == deadly_demise_source.source_id
    )

    _assert_waiting_for_movement_unit(final_status)
    assert defender_model.model_instance_id not in final_battlefield.placed_model_ids()
    assert any(
        payload["model_instance_id"] == defender_model.model_instance_id
        for payload in final_destroyed_payloads
    )
    assert len(secondary_reaction_payloads) == 1
    assert len(primary_reaction_payloads) == 1
    assert secondary_reaction_payloads[0]["execution_status"] == "recorded_for_action_host"
    assert primary_reaction_payloads[0]["execution_status"] == "resolved"


def test_phase13e_deadly_demise_secondary_deadly_demise_chains_before_removal() -> None:
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_pose=Pose.at(14.0, 35.0),
    )
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    attacker_model = attacker.own_models[0]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    secondary_deadly_demise_source = DestructionReactionSource(
        source_id="phase13e-secondary-chain-deadly-demise",
        reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
        source_rule_id="phase13e-secondary-chain-deadly-demise-rule",
        payload={
            "trigger_roll_threshold": 6,
            "range_inches": 6.0,
            "mortal_wounds": {"kind": "fixed", "value": 1},
        },
        optional=False,
    )
    state.record_model_destruction_reaction_sources(
        model_instance_id=attacker_model.model_instance_id,
        sources=(secondary_deadly_demise_source,),
    )
    deadly_demise_source = DestructionReactionSource(
        source_id="phase13e-primary-chain-deadly-demise",
        reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
        source_rule_id="phase13e-primary-chain-deadly-demise-rule",
        payload={
            "trigger_roll_threshold": 6,
            "range_inches": 6.0,
            "mortal_wounds": {"kind": "fixed", "value": attacker_model.wounds_remaining},
        },
        optional=False,
    )
    state.record_model_destruction_reaction_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(deadly_demise_source,),
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        damage_profile=DamageProfile.fixed(defender_model.wounds_remaining),
    )
    sequence = AttackSequence.start(
        sequence_id="phase13e-secondary-chain",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=sequence.attack_pools,
        attack_sequence=sequence,
    )
    attack_context_id = "phase13e-secondary-chain:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )
    primary_deadly_demise_spec = deadly_demise_trigger_roll_spec(
        source=deadly_demise_source,
        player_id="player-b",
        model_instance_id=defender_model.model_instance_id,
    )
    secondary_deadly_demise_spec = deadly_demise_trigger_roll_spec(
        source=secondary_deadly_demise_source,
        player_id="player-a",
        model_instance_id=attacker_model.model_instance_id,
    )

    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase13e-secondary-chain",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id="phase13e-chain-hit", spec=hit_spec, value=6),
                _fixed_roll_result(roll_id="phase13e-chain-wound", spec=wound_spec, value=6),
                _fixed_roll_result(roll_id="phase13e-chain-save", spec=save_spec, value=1),
                _fixed_roll_result(
                    roll_id="phase13e-chain-primary-deadly-demise",
                    spec=primary_deadly_demise_spec,
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase13e-chain-secondary-deadly-demise",
                    spec=secondary_deadly_demise_spec,
                    value=6,
                ),
            ),
        ),
    )
    event_records = lifecycle.decision_controller.event_log.records
    reaction_events = tuple(
        event for event in event_records if event.event_type == "destruction_reaction_resolved"
    )
    deadly_demise_source_ids = tuple(
        cast(dict[str, object], cast(dict[str, object], event.payload)["selected_source"])[
            "source_id"
        ]
        for event in reaction_events
        if cast(dict[str, object], cast(dict[str, object], event.payload)["selected_source"])[
            "reaction_kind"
        ]
        == DestructionReactionKind.DEADLY_DEMISE.value
    )
    secondary_reaction_event = next(
        event
        for event in reaction_events
        if cast(dict[str, object], cast(dict[str, object], event.payload)["selected_source"])[
            "source_id"
        ]
        == secondary_deadly_demise_source.source_id
    )
    primary_reaction_event = next(
        event
        for event in reaction_events
        if cast(dict[str, object], cast(dict[str, object], event.payload)["selected_source"])[
            "source_id"
        ]
        == deadly_demise_source.source_id
    )
    secondary_destroyed_event = next(
        event
        for event in event_records
        if event.event_type == "model_destroyed"
        and cast(dict[str, object], event.payload)["model_instance_id"]
        == attacker_model.model_instance_id
    )
    primary_destroyed_event = next(
        event
        for event in event_records
        if event.event_type == "model_destroyed"
        and cast(dict[str, object], event.payload)["model_instance_id"]
        == defender_model.model_instance_id
    )

    assert remaining_sequence is None
    assert allocated_ids == (defender_model.model_instance_id,)
    assert status is None
    assert deadly_demise_source_ids == (
        secondary_deadly_demise_source.source_id,
        deadly_demise_source.source_id,
    )
    assert event_records.index(secondary_reaction_event) < event_records.index(
        secondary_destroyed_event
    )
    assert event_records.index(primary_reaction_event) < event_records.index(
        primary_destroyed_event
    )
    assert event_records.index(secondary_destroyed_event) < event_records.index(
        primary_destroyed_event
    )
    assert (
        json.loads(json.dumps(primary_reaction_event.payload, sort_keys=True))
        == primary_reaction_event.payload
    )
    assert (
        json.loads(json.dumps(secondary_reaction_event.payload, sort_keys=True))
        == secondary_reaction_event.payload
    )


def test_phase13e_destruction_reaction_invalid_submission_does_not_mutate_queue() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models[1:])
    )
    source = DestructionReactionSource(
        source_id="phase13e-invalid-shoot-on-death",
        reaction_kind=DestructionReactionKind.SHOOT_ON_DEATH,
        source_rule_id="phase13e-invalid-rule",
    )
    state.record_model_destruction_reaction_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(source,),
    )
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        damage_profile=DamageProfile.fixed(defender_model.wounds_remaining),
    )
    sequence = AttackSequence.start(
        sequence_id="phase13e-invalid-reaction",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=weapon_profile,
                attacks=1,
            ),
        ),
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attacker.unit_instance_id,),
        shot_unit_ids=(attacker.unit_instance_id,),
        attack_pools=sequence.attack_pools,
        attack_sequence=sequence,
    )
    attack_context_id = "phase13e-invalid-reaction:pool-001:attack-001"
    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id="player-a",
    )
    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile.profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id="player-a",
    )
    save_spec = saving_throw_roll_spec(
        save_kind=SaveKind.ARMOUR,
        player_id="player-b",
        allocated_model_id=defender_model.model_instance_id,
        attack_context_id=attack_context_id,
    )
    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=sequence,
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            "phase13e-invalid-reaction",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(roll_id="phase13e-invalid-hit", spec=hit_spec, value=6),
                _fixed_roll_result(roll_id="phase13e-invalid-wound", spec=wound_spec, value=6),
                _fixed_roll_result(roll_id="phase13e-invalid-save", spec=save_spec, value=1),
            ),
        ),
    )
    request = _decision_request(cast(LifecycleStatus, status))
    state.shooting_phase_state = state.shooting_phase_state.with_attack_sequence_update(
        attack_sequence=remaining_sequence,
        allocated_model_ids_this_phase=allocated_ids,
    )
    before_records = len(lifecycle.decision_controller.records)

    stale_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase13e-stale-destruction-reaction",
            request_id="wrong-request",
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=source.source_id,
            payload={"source_id": source.source_id, "reaction_kind": source.reaction_kind.value},
        )
    )
    malformed_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase13e-malformed-destruction-reaction",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=source.source_id,
            payload={
                "source_id": source.source_id,
                "reaction_kind": DestructionReactionKind.FIGHT_ON_DEATH.value,
            },
        )
    )

    assert stale_status.status_kind is LifecycleStatusKind.INVALID
    assert malformed_status.status_kind is LifecycleStatusKind.INVALID
    assert len(lifecycle.decision_controller.records) == before_records
    assert lifecycle.decision_controller.queue.pending_requests == (request,)

    decline_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase13e-decline-destruction-reaction",
            request=request,
            selected_option_id=DECLINE_DESTRUCTION_REACTION_OPTION_ID,
        )
    )
    reaction_payload = _last_event_payload(lifecycle, "destruction_reaction_resolved")

    _assert_waiting_for_movement_unit(decline_status)
    assert reaction_payload["selected_source"] is None
    assert reaction_payload["action_host"] is None
    assert reaction_payload["execution_status"] == "declined"


def test_phase13e_destruction_reaction_payloads_round_trip() -> None:
    source = DestructionReactionSource(
        source_id="phase13e-round-trip-fight",
        reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
        source_rule_id="phase13e-round-trip-rule",
        payload={"trigger_roll_threshold": 4},
    )
    request = build_destruction_reaction_request(
        request_id="phase13e-round-trip-request",
        defender_player_id="player-b",
        destruction_context={"context_kind": "test-destruction"},
        sources=(source,),
    )
    decoded_request = DecisionRequest.from_payload(
        json.loads(json.dumps(request.to_payload(), sort_keys=True))
    )
    result = DecisionResult.for_request(
        result_id="phase13e-round-trip-result",
        request=decoded_request,
        selected_option_id=source.source_id,
    )
    decision = DestructionReactionDecision.from_result(
        request=decoded_request,
        result=result,
    )

    assert DestructionReactionSource.from_payload(source.to_payload()) == source
    assert destruction_reaction_kind_from_token("fight_on_death") is (
        DestructionReactionKind.FIGHT_ON_DEATH
    )
    assert decision.selected_source_id == source.source_id
    assert decision.selected_reaction_kind is DestructionReactionKind.FIGHT_ON_DEATH
    assert decision.destruction_context == {"context_kind": "test-destruction"}

    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    model_id = units["enemy"].own_models[0].model_instance_id
    state.record_model_destruction_reaction_sources(model_instance_id=model_id, sources=(source,))
    decoded_state = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))
    )

    assert decoded_state.destruction_reaction_sources_for_model(model_instance_id=model_id) == (
        source,
    )
    decoded_state.clear_model_destruction_reaction_sources(model_instance_id=model_id)
    assert decoded_state.destruction_reaction_sources_for_model(model_instance_id=model_id) == ()


def test_phase13e_destruction_reaction_validation_errors_are_typed() -> None:
    with pytest.raises(GameLifecycleError, match="token must be a string"):
        destruction_reaction_kind_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported DestructionReactionKind"):
        destruction_reaction_kind_from_token("not-a-destruction-reaction")
    with pytest.raises(GameLifecycleError, match=r"Deadly Demise.*mandatory"):
        DestructionReactionSource(
            source_id="phase13e-optional-deadly-demise",
            reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
            source_rule_id="phase13e-optional-deadly-demise-rule",
        )
    with pytest.raises(GameLifecycleError, match="requires a source"):
        deadly_demise_trigger_roll_spec(
            source=cast(DestructionReactionSource, object()),
            player_id="player-b",
            model_instance_id="phase13e-model",
        )
    with pytest.raises(GameLifecycleError, match="requires a Deadly Demise source"):
        deadly_demise_trigger_roll_spec(
            source=DestructionReactionSource(
                source_id="phase13e-not-deadly-demise",
                reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
                source_rule_id="phase13e-not-deadly-demise-rule",
            ),
            player_id="player-b",
            model_instance_id="phase13e-model",
        )
    with pytest.raises(GameLifecycleError, match="mortal-wound roll requires a source"):
        deadly_demise_mortal_wounds_roll_spec(
            source=cast(DestructionReactionSource, object()),
            player_id="player-b",
            target_unit_instance_id="phase13e-target",
            sides=6,
        )
    mandatory_source = DestructionReactionSource(
        source_id="phase13e-mandatory-fight",
        reaction_kind=DestructionReactionKind.FIGHT_ON_DEATH,
        source_rule_id="phase13e-mandatory-fight-rule",
        optional=False,
    )
    with pytest.raises(GameLifecycleError, match="player choice"):
        build_destruction_reaction_request(
            request_id="phase13e-mandatory-request",
            defender_player_id="player-b",
            destruction_context={"context_kind": "test"},
            sources=(mandatory_source,),
        )
    with pytest.raises(GameLifecycleError, match="source and reaction kind"):
        DestructionReactionDecision(
            request_id="phase13e-invalid-decision-request",
            result_id="phase13e-invalid-decision-result",
            player_id="player-a",
            selected_source_id="phase13e-invalid-source",
            selected_reaction_kind=None,
            destruction_context={"context_kind": "test"},
        )

    option = DecisionOption(
        option_id="phase13e-no-actor-source",
        label="No Actor Source",
        payload={
            "source_id": "phase13e-no-actor-source",
            "reaction_kind": DestructionReactionKind.SHOOT_ON_DEATH.value,
        },
    )
    request = DecisionRequest(
        request_id="phase13e-no-actor-request",
        decision_type=SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
        actor_id=None,
        payload={"destruction_context": {"context_kind": "test"}},
        options=(option,),
    )
    result = DecisionResult.for_request(
        result_id="phase13e-no-actor-result",
        request=request,
        selected_option_id=option.option_id,
    )
    with pytest.raises(GameLifecycleError, match="requires an actor"):
        DestructionReactionDecision.from_result(request=request, result=result)


def test_phase13c_mortal_wounds_use_forced_feel_no_pain_per_wound() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    source = FeelNoPainSource(source_id="phase13c-mortal-fnp", threshold=5)
    state.record_model_feel_no_pain_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(source,),
    )
    fnp_spec = feel_no_pain_roll_spec(
        source=source,
        player_id="player-b",
        model_instance_id=defender_model.model_instance_id,
        wound_index=1,
    )

    application = apply_mortal_wounds_to_unit(
        state=state,
        target_unit_instance_id=defender.unit_instance_id,
        mortal_wounds=1,
        dice_manager=DiceRollManager(
            "phase13c-mortal-fnp",
            injected_results=(
                _fixed_roll_result(roll_id="phase13c-mortal-fnp", spec=fnp_spec, value=5),
            ),
        ),
        defender_player_id="player-b",
    )

    assert application.ignored_mortal_wounds == 1
    assert application.applications == ()
    assert application.feel_no_pain_resolutions[0].ignored_wounds == 1
    assert (
        model_by_id(
            state=state, model_instance_id=defender_model.model_instance_id
        ).wounds_remaining
        == defender_model.wounds_remaining
    )


def test_phase13c_mortal_wounds_use_psychic_attack_source_with_mortal_wound_scope() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    source = FeelNoPainSource(
        source_id="phase13c-psychic-mortal-fnp",
        threshold=5,
        attack_condition=FeelNoPainAttackCondition.PSYCHIC_ATTACK,
        mortal_wounds=True,
    )
    state.record_model_feel_no_pain_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(source,),
    )
    fnp_spec = feel_no_pain_roll_spec(
        source=source,
        player_id="player-b",
        model_instance_id=defender_model.model_instance_id,
        wound_index=1,
    )

    application = apply_mortal_wounds_to_unit(
        state=state,
        target_unit_instance_id=defender.unit_instance_id,
        mortal_wounds=1,
        dice_manager=DiceRollManager(
            "phase13c-psychic-mortal-fnp",
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase13c-psychic-mortal-fnp",
                    spec=fnp_spec,
                    value=5,
                ),
            ),
        ),
        defender_player_id="player-b",
    )

    assert application.ignored_mortal_wounds == 1
    assert application.applications == ()
    assert application.feel_no_pain_resolutions[0].source == source
    assert application.feel_no_pain_resolutions[0].ignored_wounds == 1


def test_phase13c_mortal_wounds_ignore_psychic_attack_source_without_mortal_wound_scope() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    source = FeelNoPainSource(
        source_id="phase13c-psychic-only-mortal-fnp",
        threshold=5,
        attack_condition=FeelNoPainAttackCondition.PSYCHIC_ATTACK,
    )
    state.record_model_feel_no_pain_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(source,),
    )

    application = apply_mortal_wounds_to_unit(
        state=state,
        target_unit_instance_id=defender.unit_instance_id,
        mortal_wounds=1,
    )

    assert application.ignored_mortal_wounds == 0
    assert application.feel_no_pain_resolutions == ()
    assert application.applications[0].wounds_lost == 1


def test_phase13d_direct_mortal_wound_helper_rejects_choice_routing_contexts() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    source_a = FeelNoPainSource(source_id="phase13d-direct-mortal-a", threshold=5)
    source_b = FeelNoPainSource(source_id="phase13d-direct-mortal-b", threshold=6)
    roll_spec = feel_no_pain_roll_spec(
        source=source_a,
        player_id="player-b",
        model_instance_id=defender_model.model_instance_id,
        wound_index=1,
    )
    roll_state = DiceRollState.from_result(
        _fixed_roll_result(roll_id="phase13d-direct-mortal-roll", spec=roll_spec, value=5)
    )

    with pytest.raises(GameLifecycleError, match="between 2 and 6"):
        FeelNoPainSource(source_id="phase13d-invalid-threshold", threshold=7)
    with pytest.raises(GameLifecycleError, match="must be an int"):
        FeelNoPainSource(
            source_id="phase13d-invalid-threshold-type",
            threshold=cast(int, "5"),
        )
    with pytest.raises(GameLifecycleError, match="source must be a FeelNoPainSource"):
        FeelNoPainRoll(
            source=cast(FeelNoPainSource, object()),
            roll_state=roll_state,
            successful=True,
        )
    with pytest.raises(GameLifecycleError, match="roll_state must be DiceRollState"):
        FeelNoPainRoll(
            source=source_a,
            roll_state=cast(DiceRollState, object()),
            successful=True,
        )
    with pytest.raises(GameLifecycleError, match="successful must be a bool"):
        FeelNoPainRoll(
            source=source_a,
            roll_state=roll_state,
            successful=cast(bool, "yes"),
        )
    with pytest.raises(GameLifecycleError, match="source must be a FeelNoPainSource"):
        FeelNoPainResolution(
            source=cast(FeelNoPainSource, object()),
            requested_wounds=1,
        )

    no_actor_request = DecisionRequest(
        request_id="phase13d-no-actor-fnp",
        decision_type=SELECT_FEEL_NO_PAIN_DECISION_TYPE,
        actor_id=None,
        payload=cast(
            JsonValue,
            {
                "lost_wound_context": {"context_kind": "lost_wound"},
                "sources": [source_a.to_payload()],
                "decline_allowed": True,
            },
        ),
        options=(
            DecisionOption(
                option_id="decline",
                label="Decline",
                payload={"source_id": None},
            ),
        ),
    )
    with pytest.raises(GameLifecycleError, match="requires a defender"):
        FeelNoPainDecision.from_result(
            request=no_actor_request,
            result=DecisionResult.for_request(
                result_id="phase13d-no-actor-fnp-result",
                request=no_actor_request,
                selected_option_id="decline",
            ),
        )
    with pytest.raises(GameLifecycleError, match="spill_over must be a bool"):
        apply_mortal_wounds_to_unit(
            state=state,
            target_unit_instance_id=defender.unit_instance_id,
            mortal_wounds=1,
            spill_over=cast(bool, "yes"),
        )

    state.record_model_feel_no_pain_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(source_a,),
        decline_allowed=False,
    )
    with pytest.raises(GameLifecycleError, match="requires dice manager and defender"):
        apply_mortal_wounds_to_unit(
            state=state,
            target_unit_instance_id=defender.unit_instance_id,
            mortal_wounds=1,
        )

    state.record_model_feel_no_pain_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(source_a, source_b),
        decline_allowed=False,
    )
    with pytest.raises(GameLifecycleError, match="choices require lifecycle routing"):
        apply_mortal_wounds_to_unit(
            state=state,
            target_unit_instance_id=defender.unit_instance_id,
            mortal_wounds=1,
        )

    state.record_model_feel_no_pain_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(source_a,),
        decline_allowed=True,
    )
    with pytest.raises(GameLifecycleError, match="choices require lifecycle routing"):
        apply_mortal_wounds_to_unit(
            state=state,
            target_unit_instance_id=defender.unit_instance_id,
            mortal_wounds=1,
        )


def test_phase13d_mortal_wound_lifecycle_progress_round_trip() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    defender = units["enemy"]
    defender_model = defender.own_models[0]
    source_a = FeelNoPainSource(source_id="phase13d-mortal-progress-a", threshold=5)
    source_b = FeelNoPainSource(source_id="phase13d-mortal-progress-b", threshold=6)
    state.record_model_feel_no_pain_sources(
        model_instance_id=defender_model.model_instance_id,
        sources=(source_a, source_b),
    )
    progress = MortalWoundApplicationProgress.start(
        application_id="phase13d-mortal-progress",
        source_rule_id="phase13d:test-mortal",
        source_context={"source_kind": "phase13d_progress_test"},
        target_unit_instance_id=defender.unit_instance_id,
        defender_player_id="player-b",
        mortal_wounds=1,
        spill_over=True,
    )

    routing = continue_mortal_wound_application(
        state=state,
        request_id="phase13d-mortal-progress-fnp",
        progress=progress,
    )
    request = routing.request

    assert request is not None
    assert routing.application is None
    assert is_mortal_wound_feel_no_pain_request(request)
    assert mortal_wound_feel_no_pain_source_context(request) == {
        "source_kind": "phase13d_progress_test"
    }
    assert {option.option_id for option in request.options} == {
        source_a.source_id,
        source_b.source_id,
    }
    request_payload = cast(dict[str, object], request.payload)
    restored_progress = MortalWoundApplicationProgress.from_feel_no_pain_context(
        validate_json_value(request_payload["lost_wound_context"])
    )
    fnp_spec = feel_no_pain_roll_spec(
        source=source_a,
        player_id="player-b",
        model_instance_id=defender_model.model_instance_id,
        wound_index=1,
    )
    completed = resolve_mortal_wound_feel_no_pain_decision(
        state=state,
        request=request,
        result=DecisionResult.for_request(
            result_id="phase13d-mortal-progress-source-a",
            request=request,
            selected_option_id=source_a.source_id,
        ),
        next_request_id="phase13d-mortal-progress-next",
        dice_manager=DiceRollManager(
            "phase13d-mortal-progress",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase13d-mortal-progress-fnp-roll",
                    spec=fnp_spec,
                    value=1,
                ),
            ),
        ),
    )
    application = completed.application

    assert restored_progress == progress
    assert application is not None
    assert completed.request is None
    assert MortalWoundApplication.from_payload(application.to_payload()) == application
    assert application.applications[0].wounds_lost == 1
    assert application.feel_no_pain_resolutions[0].remaining_wounds == 1


def test_phase13d_mortal_wound_lifecycle_value_objects_fail_fast() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("unit-1",))
    state = _state(lifecycle)
    defender = units["enemy"]
    target_model_id = defender.own_models[0].model_instance_id
    source = FeelNoPainSource(source_id="phase13d-validation-fnp", threshold=5)
    other_source = FeelNoPainSource(source_id="phase13d-validation-other-fnp", threshold=6)
    roll_spec = feel_no_pain_roll_spec(
        source=source,
        player_id="player-b",
        model_instance_id=target_model_id,
        wound_index=1,
    )
    roll_state = DiceRollState.from_result(
        _fixed_roll_result(roll_id="phase13d-validation-fnp-roll", spec=roll_spec, value=5)
    )
    roll = FeelNoPainRoll(source=source, roll_state=roll_state, successful=True)

    assert FeelNoPainRoll.from_payload(roll.to_payload()) == roll
    assert (
        FeelNoPainResolution(
            source=source,
            requested_wounds=1,
            rolls=(roll,),
        ).remaining_wounds
        == 0
    )

    with pytest.raises(GameLifecycleError, match="must be a string"):
        FeelNoPainSource(source_id=cast(str, 1), threshold=5)
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        FeelNoPainSource(source_id=" ", threshold=5)
    with pytest.raises(GameLifecycleError, match="success flag drift"):
        FeelNoPainRoll(source=source, roll_state=roll_state, successful=False)
    with pytest.raises(GameLifecycleError, match="Declined Feel No Pain must not include rolls"):
        FeelNoPainResolution(source=None, requested_wounds=1, rolls=(roll,))
    with pytest.raises(GameLifecycleError, match="rolls must match requested wounds"):
        FeelNoPainResolution(source=source, requested_wounds=2, rolls=(roll,))
    with pytest.raises(GameLifecycleError, match="roll source drift"):
        FeelNoPainResolution(source=other_source, requested_wounds=1, rolls=(roll,))
    with pytest.raises(GameLifecycleError, match="wound accounting drift"):
        MortalWoundApplication(
            target_unit_instance_id=defender.unit_instance_id,
            mortal_wounds=1,
            spill_over=True,
            applications=(),
            feel_no_pain_resolutions=(),
            ignored_mortal_wounds=0,
            remaining_mortal_wounds_lost=0,
        )
    with pytest.raises(GameLifecycleError, match="remaining wound drift"):
        MortalWoundApplicationProgress(
            application_id="phase13d-invalid-progress",
            source_rule_id="phase13d:validation",
            source_context={"source_kind": "validation"},
            target_unit_instance_id=defender.unit_instance_id,
            defender_player_id="player-b",
            mortal_wounds=1,
            remaining_mortal_wounds=2,
            spill_over=True,
        )
    with pytest.raises(GameLifecycleError, match="spill_over must be a bool"):
        MortalWoundApplicationProgress(
            application_id="phase13d-invalid-progress",
            source_rule_id="phase13d:validation",
            source_context={"source_kind": "validation"},
            target_unit_instance_id=defender.unit_instance_id,
            defender_player_id="player-b",
            mortal_wounds=1,
            remaining_mortal_wounds=1,
            spill_over=cast(bool, "yes"),
        )
    with pytest.raises(GameLifecycleError, match="wound accounting drift"):
        MortalWoundApplicationProgress(
            application_id="phase13d-invalid-progress",
            source_rule_id="phase13d:validation",
            source_context={"source_kind": "validation"},
            target_unit_instance_id=defender.unit_instance_id,
            defender_player_id="player-b",
            mortal_wounds=1,
            remaining_mortal_wounds=1,
            spill_over=True,
            ignored_mortal_wounds=1,
        )
    with pytest.raises(GameLifecycleError, match="must be at least 1"):
        MortalWoundApplicationProgress.start(
            application_id="phase13d-invalid-progress",
            source_rule_id="phase13d:validation",
            source_context={"source_kind": "validation"},
            target_unit_instance_id=defender.unit_instance_id,
            defender_player_id="player-b",
            mortal_wounds=0,
            spill_over=True,
        )
    with pytest.raises(GameLifecycleError, match="must not be negative"):
        MortalWoundApplicationProgress(
            application_id="phase13d-invalid-progress",
            source_rule_id="phase13d:validation",
            source_context={"source_kind": "validation"},
            target_unit_instance_id=defender.unit_instance_id,
            defender_player_id="player-b",
            mortal_wounds=1,
            remaining_mortal_wounds=1,
            spill_over=True,
            ignored_mortal_wounds=-1,
        )
    with pytest.raises(GameLifecycleError, match="context must be an object"):
        MortalWoundApplicationProgress.from_feel_no_pain_context(None)
    with pytest.raises(GameLifecycleError, match="context kind is invalid"):
        MortalWoundApplicationProgress.from_feel_no_pain_context({"context_kind": "lost_wound"})

    progress = MortalWoundApplicationProgress.start(
        application_id="phase13d-validation-progress",
        source_rule_id="phase13d:validation",
        source_context={"source_kind": "validation"},
        target_unit_instance_id=defender.unit_instance_id,
        defender_player_id="player-b",
        mortal_wounds=1,
        spill_over=True,
    )
    context_payload = cast(
        dict[str, JsonValue],
        dict(progress.to_feel_no_pain_context(model_instance_id=target_model_id)),
    )
    context_payload["applications"] = {}
    with pytest.raises(GameLifecycleError, match="applications must be a list"):
        MortalWoundApplicationProgress.from_feel_no_pain_context(
            validate_json_value(context_payload)
        )
    with pytest.raises(GameLifecycleError, match="Incomplete mortal wound progress"):
        progress.to_application()

    lost_progress = progress.with_remaining_lost()
    assert lost_progress.to_application().remaining_mortal_wounds_lost == 1
    with pytest.raises(GameLifecycleError, match="no wound to resolve"):
        lost_progress.after_wound_resolution(
            state=state,
            model_instance_id=target_model_id,
            resolution=FeelNoPainResolution.declined(requested_wounds=1),
        )
    with pytest.raises(GameLifecycleError, match="remove_destroyed_model must be a bool"):
        progress.after_wound_resolution(
            state=state,
            model_instance_id=target_model_id,
            resolution=FeelNoPainResolution.declined(requested_wounds=1),
            remove_destroyed_model=cast(bool, "yes"),
        )
    with pytest.raises(GameLifecycleError, match="exactly one request or application"):
        MortalWoundRoutingResult(progress=progress)
    with pytest.raises(GameLifecycleError, match="request is invalid"):
        MortalWoundRoutingResult(
            progress=progress,
            request=cast(DecisionRequest, object()),
        )


def test_phase13d_mortal_wound_routing_rejects_invalid_lifecycle_edges() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("unit-1",))
    state = _state(lifecycle)
    defender = units["enemy"]
    source = FeelNoPainSource(source_id="phase13d-routing-fnp", threshold=5)
    other_source = FeelNoPainSource(source_id="phase13d-routing-other-fnp", threshold=6)

    with pytest.raises(GameLifecycleError, match="can_allocate_protected_characters"):
        AttackAllocationConstraint(can_allocate_protected_characters=cast(bool, "yes"))
    with pytest.raises(GameLifecycleError, match="attacker selection must be allowed"):
        AttackAllocationConstraint(
            allowed_model_ids=("phase13d-allowed-model",),
            attacker_selected_model_id="phase13d-disallowed-model",
        )
    with pytest.raises(GameLifecycleError, match="requires alive models"):
        AttackAllocationRuleContext(
            target_unit_instance_id=defender.unit_instance_id,
            alive_model_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="outside alive_model_ids"):
        AttackAllocationRuleContext(
            target_unit_instance_id=defender.unit_instance_id,
            alive_model_ids=("phase13d-alive-model",),
            wounded_model_ids=("phase13d-missing-model",),
        )
    single_model_context = AttackAllocationRuleContext(
        target_unit_instance_id=defender.unit_instance_id,
        alive_model_ids=("phase13d-only-model",),
    )
    assert single_model_context.legal_model_ids() == ("phase13d-only-model",)
    with pytest.raises(GameLifecycleError, match="requires a player choice"):
        build_feel_no_pain_request(
            request_id="phase13d-single-fnp",
            defender_player_id="player-b",
            lost_wound_context={"context_kind": "lost_wound"},
            sources=(source,),
            decline_allowed=False,
        )
    with pytest.raises(GameLifecycleError, match="requires a request"):
        is_mortal_wound_feel_no_pain_request(cast(DecisionRequest, object()))

    non_fnp_request = DecisionRequest(
        request_id="phase13d-non-fnp",
        decision_type="phase13d-other-decision",
        actor_id="player-b",
        payload={},
        options=(DecisionOption(option_id="phase13d-option", label="Option"),),
    )
    malformed_payload_request = DecisionRequest(
        request_id="phase13d-non-object-fnp",
        decision_type=SELECT_FEEL_NO_PAIN_DECISION_TYPE,
        actor_id="player-b",
        payload=[],
        options=(DecisionOption(option_id="phase13d-option", label="Option"),),
    )
    missing_context_request = DecisionRequest(
        request_id="phase13d-missing-context-fnp",
        decision_type=SELECT_FEEL_NO_PAIN_DECISION_TYPE,
        actor_id="player-b",
        payload={"lost_wound_context": []},
        options=(DecisionOption(option_id="phase13d-option", label="Option"),),
    )
    assert not is_mortal_wound_feel_no_pain_request(non_fnp_request)
    assert not is_mortal_wound_feel_no_pain_request(malformed_payload_request)
    assert not is_mortal_wound_feel_no_pain_request(missing_context_request)

    no_models_progress = MortalWoundApplicationProgress.start(
        application_id="phase13d-no-model-routing",
        source_rule_id="phase13d:routing",
        source_context={"source_kind": "no_models"},
        target_unit_instance_id=defender.unit_instance_id,
        defender_player_id="player-b",
        mortal_wounds=1,
        spill_over=True,
    )
    battlefield = state.battlefield_state
    assert battlefield is not None
    state.battlefield_state = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in defender.own_models)
    )
    no_models_routing = continue_mortal_wound_application(
        state=state,
        request_id="phase13d-no-model-request",
        progress=no_models_progress,
    )
    no_models_application = no_models_routing.application
    assert no_models_routing.request is None
    assert no_models_application is not None
    assert no_models_application.applications == ()
    assert no_models_application.remaining_mortal_wounds_lost == 1

    routed_lifecycle, routed_units = _shooting_lifecycle(alpha_unit_ids=("unit-1",))
    routed_state = _state(routed_lifecycle)
    routed_defender = routed_units["enemy"]
    routed_model = routed_defender.own_models[0]
    routed_state.record_model_feel_no_pain_sources(
        model_instance_id=routed_model.model_instance_id,
        sources=(source,),
        decline_allowed=False,
    )
    single_source_progress = MortalWoundApplicationProgress.start(
        application_id="phase13d-single-source-routing",
        source_rule_id="phase13d:routing",
        source_context={"source_kind": "single_source"},
        target_unit_instance_id=routed_defender.unit_instance_id,
        defender_player_id="player-b",
        mortal_wounds=1,
        spill_over=True,
    )
    with pytest.raises(GameLifecycleError, match="requires dice manager"):
        continue_mortal_wound_application(
            state=routed_state,
            request_id="phase13d-single-source-request",
            progress=single_source_progress,
        )
    with pytest.raises(GameLifecycleError, match="remove_destroyed_models must be a bool"):
        continue_mortal_wound_application(
            state=routed_state,
            request_id="phase13d-invalid-removal-flag",
            progress=single_source_progress,
            remove_destroyed_models=cast(bool, "yes"),
        )

    routed_state.record_model_feel_no_pain_sources(
        model_instance_id=routed_model.model_instance_id,
        sources=(source, other_source),
        decline_allowed=False,
    )
    choice_routing = continue_mortal_wound_application(
        state=routed_state,
        request_id="phase13d-source-choice-request",
        progress=single_source_progress,
    )
    request = choice_routing.request
    assert request is not None
    with pytest.raises(GameLifecycleError, match="remove_destroyed_models must be a bool"):
        resolve_mortal_wound_feel_no_pain_decision(
            state=routed_state,
            request=request,
            result=DecisionResult.for_request(
                result_id="phase13d-source-choice-invalid-removal-flag",
                request=request,
                selected_option_id=source.source_id,
            ),
            next_request_id="phase13d-source-choice-next",
            remove_destroyed_models=cast(bool, "yes"),
        )
    with pytest.raises(GameLifecycleError, match="decision requires dice manager"):
        resolve_mortal_wound_feel_no_pain_decision(
            state=routed_state,
            request=request,
            result=DecisionResult.for_request(
                result_id="phase13d-source-choice-no-dice",
                request=request,
                selected_option_id=source.source_id,
            ),
            next_request_id="phase13d-source-choice-next",
        )

    request_payload = cast(dict[str, JsonValue], request.payload)
    inconsistent_request_payload = dict(request_payload)
    inconsistent_request_payload["sources"] = cast(JsonValue, [other_source.to_payload()])
    inconsistent_request = DecisionRequest(
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        payload=validate_json_value(inconsistent_request_payload),
        options=request.options,
    )
    with pytest.raises(GameLifecycleError, match="not in the request"):
        resolve_mortal_wound_feel_no_pain_decision(
            state=routed_state,
            request=inconsistent_request,
            result=DecisionResult.for_request(
                result_id="phase13d-source-choice-bad-payload",
                request=inconsistent_request,
                selected_option_id=source.source_id,
            ),
            next_request_id="phase13d-source-choice-next",
        )
    broken_request_payload = dict(request_payload)
    broken_request_payload["sources"] = {}
    broken_request = DecisionRequest(
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        payload=validate_json_value(broken_request_payload),
        options=request.options,
    )
    with pytest.raises(GameLifecycleError, match="sources must be a list"):
        resolve_mortal_wound_feel_no_pain_decision(
            state=routed_state,
            request=broken_request,
            result=DecisionResult.for_request(
                result_id="phase13d-source-choice-bad-sources",
                request=broken_request,
                selected_option_id=source.source_id,
            ),
            next_request_id="phase13d-source-choice-next",
        )


def test_phase13d_out_of_phase_shooting_state_payload_round_trip() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    attack_pool = _attack_pool_for_test(
        attacker=attacker,
        defender=defender,
        weapon_profile=_first_weapon_profile(lifecycle, attacker),
        attacks=1,
    )
    attack_sequence = AttackSequence.start(
        sequence_id="phase13d-oop-state",
        attacker_player_id="player-a",
        attacking_unit_instance_id=attacker.unit_instance_id,
        attack_pools=(attack_pool,),
    )
    state = OutOfPhaseShootingState(
        battle_round=1,
        player_id="player-a",
        parent_phase=BattlePhase.MOVEMENT,
        source_rule_id="core:fire-overwatch",
        source_decision_request_id="phase13d-oop-request",
        source_decision_result_id="phase13d-oop-result",
        source_context={"source_kind": "fire_overwatch"},
        selected_unit_instance_id=attacker.unit_instance_id,
    )
    declared = state.with_declaration(
        attack_pools=(attack_pool,),
        attack_sequence=attack_sequence,
    )
    updated = declared.with_attack_sequence_update(
        attack_sequence=None,
        allocated_model_ids=(defender.own_models[0].model_instance_id,),
    )

    assert OutOfPhaseShootingState.from_payload(updated.to_payload()) == updated
    with pytest.raises(GameLifecycleError, match="unit drift"):
        OutOfPhaseShootingState(
            battle_round=1,
            player_id="player-a",
            parent_phase=BattlePhase.MOVEMENT,
            source_rule_id="core:fire-overwatch",
            source_decision_request_id="phase13d-oop-request",
            source_decision_result_id="phase13d-oop-result",
            source_context={"source_kind": "fire_overwatch"},
            selected_unit_instance_id=defender.unit_instance_id,
            attack_pools=(attack_pool,),
            attack_sequence=attack_sequence,
        )


def test_phase13c_invalid_attack_save_and_damage_payloads_fail_fast() -> None:
    _lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    model = units["enemy"].own_models[0]
    cover_result = _benefit_of_cover_result()
    armour_option = next(
        option
        for option in save_options_for_model(
            model=model,
            armor_penetration=-1,
            cover_result=cover_result,
        )
        if option.save_kind is SaveKind.ARMOUR
    )
    armour_payload = armour_option.to_payload()
    assert SaveOption.from_payload(armour_payload).to_payload() == armour_payload

    with pytest.raises(GameLifecycleError, match="armor_penetration"):
        SaveOption(
            save_kind=SaveKind.ARMOUR,
            target_number=3,
            characteristic_target_number=3,
            armor_penetration="bad",  # type: ignore[arg-type]
            cover_applied=False,
            cover_result=None,
        )
    with pytest.raises(GameLifecycleError, match="cover_applied"):
        SaveOption(
            save_kind=SaveKind.ARMOUR,
            target_number=3,
            characteristic_target_number=3,
            armor_penetration=0,
            cover_applied="bad",  # type: ignore[arg-type]
            cover_result=None,
        )
    with pytest.raises(GameLifecycleError, match="Benefit of Cover"):
        SaveOption(
            save_kind=SaveKind.INVULNERABLE,
            target_number=4,
            characteristic_target_number=4,
            armor_penetration=0,
            cover_applied=True,
            cover_result=None,
        )
    with pytest.raises(GameLifecycleError, match="Unsupported SaveKind"):
        save_kind_from_token("not-a-save")
    with pytest.raises(GameLifecycleError, match="ModelInstance"):
        save_options_for_model(
            model="not-a-model",  # type: ignore[arg-type]
            armor_penetration=0,
        )
    with pytest.raises(GameLifecycleError, match="AP must be an integer"):
        save_options_for_model(
            model=model,
            armor_penetration="bad",  # type: ignore[arg-type]
        )
    with pytest.raises(GameLifecycleError, match="no_saves_allowed must be a bool"):
        save_options_for_model(
            model=model,
            armor_penetration=0,
            no_saves_allowed="bad",  # type: ignore[arg-type]
        )
    assert cover_result_has_bonus(None) is False
    with pytest.raises(GameLifecycleError, match="cover_result must be BenefitOfCoverResult"):
        cover_result_has_bonus("bad")  # type: ignore[arg-type]
    assert (
        save_options_for_model(
            model=model,
            armor_penetration=0,
            no_saves_allowed=True,
        )
        == ()
    )

    save_roll = DiceRollManager("phase13c-invalid-save").roll_fixed(
        saving_throw_roll_spec(
            save_kind=SaveKind.ARMOUR,
            player_id="player-b",
            allocated_model_id=model.model_instance_id,
            attack_context_id="phase13c-invalid-save-context",
        ),
        [4],
    )
    with pytest.raises(GameLifecycleError, match="success flag"):
        resolve_saving_throw(option=armour_option, roll_state=save_roll).__class__(
            save_kind=SaveKind.ARMOUR,
            target_number=armour_option.characteristic_target_number,
            roll_state=save_roll,
            unmodified_roll=4,
            final_roll=3,
            successful=False,
            resolution_rule=SaveResolutionRule.ARMOUR_SAVE,
            option=armour_option,
        )
    with pytest.raises(GameLifecycleError, match="save_kind must match option"):
        SavingThrow(
            save_kind=SaveKind.INVULNERABLE,
            target_number=armour_option.characteristic_target_number,
            roll_state=save_roll,
            unmodified_roll=3,
            final_roll=2,
            successful=True,
            resolution_rule=SaveResolutionRule.ARMOUR_SAVE,
            option=armour_option,
        )
    with pytest.raises(GameLifecycleError, match="roll_state must be DiceRollState"):
        resolve_saving_throw(
            option=armour_option,
            roll_state="bad",  # type: ignore[arg-type]
        )
    assert mandatory_save_option(options=(armour_option,)) == armour_option
    with pytest.raises(GameLifecycleError, match="duplicate save kinds"):
        mandatory_save_option(options=(armour_option, armour_option))

    hit_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="phase13c invalid hit fixture",
        roll_type="attack_sequence.hit.fixture",
        actor_id="player-a",
    )
    hit_roll_state = DiceRollManager("phase13c-invalid-hit").roll_fixed(hit_spec, [2])
    threshold_hit_roll_state = DiceRollManager("phase13c-threshold-hit").roll_fixed(hit_spec, [5])
    threshold_hit = HitRoll(
        target_number=6,
        roll_state=threshold_hit_roll_state,
        unmodified_roll=5,
        modifier=0,
        capped_modifier=0,
        final_roll=5,
        successful=True,
        critical=False,
        minimum_unmodified_success=5,
        unmodified_success_threshold_active=True,
    )
    assert threshold_hit.to_payload()["unmodified_success_threshold_active"] is True
    assert HitRoll.from_payload(threshold_hit.to_payload()) == threshold_hit
    with pytest.raises(GameLifecycleError, match="success flag"):
        HitRoll(
            target_number=3,
            roll_state=hit_roll_state,
            unmodified_roll=2,
            modifier=0,
            capped_modifier=0,
            final_roll=2,
            successful=True,
            critical=False,
        )
    with pytest.raises(GameLifecycleError, match="unmodified_success_threshold_active"):
        HitRoll(
            target_number=3,
            roll_state=hit_roll_state,
            unmodified_roll=2,
            modifier=0,
            capped_modifier=0,
            final_roll=2,
            successful=False,
            critical=False,
            unmodified_success_threshold_active="bad",  # type: ignore[arg-type]
        )
    with pytest.raises(GameLifecycleError, match="Skipped HitRoll"):
        HitRoll(
            target_number=3,
            roll_state=hit_roll_state,
            unmodified_roll=2,
            modifier=0,
            capped_modifier=0,
            final_roll=None,
            successful=True,
            critical=False,
            skipped=True,
        )
    with pytest.raises(GameLifecycleError, match="unmodified success threshold"):
        HitRoll(
            target_number=3,
            roll_state=None,
            unmodified_roll=None,
            modifier=0,
            capped_modifier=0,
            final_roll=None,
            successful=True,
            critical=False,
            unmodified_success_threshold_active=True,
            skipped=True,
        )
    with pytest.raises(GameLifecycleError, match="capped_modifier must be an integer"):
        HitRoll(
            target_number=3,
            roll_state=hit_roll_state,
            unmodified_roll=2,
            modifier=0,
            capped_modifier="bad",  # type: ignore[arg-type]
            final_roll=2,
            successful=False,
            critical=False,
        )
    with pytest.raises(GameLifecycleError, match="modifier cap"):
        HitRoll(
            target_number=3,
            roll_state=hit_roll_state,
            unmodified_roll=2,
            modifier=2,
            capped_modifier=2,
            final_roll=4,
            successful=True,
            critical=False,
        )
    with pytest.raises(GameLifecycleError, match="successful must be a bool"):
        HitRoll(
            target_number=3,
            roll_state=hit_roll_state,
            unmodified_roll=2,
            modifier=0,
            capped_modifier=0,
            final_roll=2,
            successful="bad",  # type: ignore[arg-type]
            critical=False,
        )
    with pytest.raises(GameLifecycleError, match="critical flag"):
        HitRoll(
            target_number=3,
            roll_state=hit_roll_state,
            unmodified_roll=6,
            modifier=0,
            capped_modifier=0,
            final_roll=6,
            successful=True,
            critical=False,
        )
    with pytest.raises(GameLifecycleError, match="requires a roll_state"):
        HitRoll(
            target_number=3,
            roll_state=None,
            unmodified_roll=2,
            modifier=0,
            capped_modifier=0,
            final_roll=2,
            successful=False,
            critical=False,
        )
    with pytest.raises(GameLifecycleError, match="Skipped HitRoll must not include a final"):
        HitRoll(
            target_number=3,
            roll_state=None,
            unmodified_roll=None,
            modifier=0,
            capped_modifier=0,
            final_roll=3,
            successful=True,
            critical=False,
            skipped=True,
        )
    with pytest.raises(GameLifecycleError, match="generate successful"):
        HitRoll(
            target_number=3,
            roll_state=None,
            unmodified_roll=None,
            modifier=0,
            capped_modifier=0,
            final_roll=None,
            successful=False,
            critical=False,
            skipped=True,
        )
    with pytest.raises(GameLifecycleError, match="Critical Hit"):
        HitRoll(
            target_number=3,
            roll_state=None,
            unmodified_roll=None,
            modifier=0,
            capped_modifier=0,
            final_roll=None,
            successful=True,
            critical=True,
            skipped=True,
        )

    wound_spec = DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason="phase13c invalid wound fixture",
        roll_type="attack_sequence.wound.fixture",
        actor_id="player-a",
    )
    wound_roll_state = DiceRollManager("phase13c-invalid-wound").roll_fixed(wound_spec, [2])
    with pytest.raises(GameLifecycleError, match="roll_state must be DiceRollState"):
        WoundRoll(
            strength=4,
            toughness=4,
            target_number=4,
            roll_state="bad",  # type: ignore[arg-type]
            unmodified_roll=2,
            modifier=0,
            capped_modifier=0,
            final_roll=2,
            successful=False,
            critical=False,
        )
    with pytest.raises(GameLifecycleError, match="modifier must be an integer"):
        WoundRoll(
            strength=4,
            toughness=4,
            target_number=4,
            roll_state=wound_roll_state,
            unmodified_roll=2,
            modifier="bad",  # type: ignore[arg-type]
            capped_modifier=0,
            final_roll=2,
            successful=False,
            critical=False,
        )
    with pytest.raises(GameLifecycleError, match="modifier cap"):
        WoundRoll(
            strength=4,
            toughness=4,
            target_number=4,
            roll_state=wound_roll_state,
            unmodified_roll=2,
            modifier=-2,
            capped_modifier=-2,
            final_roll=0,
            successful=False,
            critical=False,
        )
    with pytest.raises(GameLifecycleError, match="final_roll must be an integer"):
        WoundRoll(
            strength=4,
            toughness=4,
            target_number=4,
            roll_state=wound_roll_state,
            unmodified_roll=2,
            modifier=0,
            capped_modifier=0,
            final_roll="bad",  # type: ignore[arg-type]
            successful=False,
            critical=False,
        )
    with pytest.raises(GameLifecycleError, match="successful must be a bool"):
        WoundRoll(
            strength=4,
            toughness=4,
            target_number=4,
            roll_state=wound_roll_state,
            unmodified_roll=2,
            modifier=0,
            capped_modifier=0,
            final_roll=2,
            successful="bad",  # type: ignore[arg-type]
            critical=False,
        )
    with pytest.raises(GameLifecycleError, match="critical flag"):
        WoundRoll(
            strength=4,
            toughness=4,
            target_number=4,
            roll_state=wound_roll_state,
            unmodified_roll=6,
            modifier=0,
            capped_modifier=0,
            final_roll=6,
            successful=True,
            critical=False,
        )
    attack_pool = _attack_pool_for_test(
        attacker=units["intercessor-1"],
        defender=units["enemy"],
        weapon_profile=_first_weapon_profile(_lifecycle, units["intercessor-1"]),
        attacks=1,
    )
    completed_sequence = AttackSequence(
        sequence_id="phase13c-completed",
        attacker_player_id="player-a",
        attacking_unit_instance_id=units["intercessor-1"].unit_instance_id,
        attack_pools=(attack_pool,),
        pool_index=1,
        attack_index=0,
    )
    assert completed_sequence.is_complete is True
    with pytest.raises(GameLifecycleError, match="no current pool"):
        completed_sequence.current_pool()
    with pytest.raises(GameLifecycleError, match="no attack context"):
        completed_sequence.attack_context_id()
    with pytest.raises(GameLifecycleError, match="cannot advance"):
        completed_sequence.advanced_after_attack()
    with pytest.raises(GameLifecycleError, match="pool_index is outside"):
        AttackSequence(
            sequence_id="phase13c-bad-pool-index",
            attacker_player_id="player-a",
            attacking_unit_instance_id=units["intercessor-1"].unit_instance_id,
            attack_pools=(attack_pool,),
            pool_index=2,
            attack_index=0,
        )
    with pytest.raises(GameLifecycleError, match="Completed AttackSequence"):
        AttackSequence(
            sequence_id="phase13c-bad-completed-index",
            attacker_player_id="player-a",
            attacking_unit_instance_id=units["intercessor-1"].unit_instance_id,
            attack_pools=(attack_pool,),
            pool_index=1,
            attack_index=1,
        )
    with pytest.raises(GameLifecycleError, match="attack_index is outside"):
        AttackSequence(
            sequence_id="phase13c-bad-attack-index",
            attacker_player_id="player-a",
            attacking_unit_instance_id=units["intercessor-1"].unit_instance_id,
            attack_pools=(attack_pool,),
            pool_index=0,
            attack_index=1,
        )
    with pytest.raises(GameLifecycleError, match="allowed must be a bool"):
        FastDiceGroup(
            group_id="phase13c-fast-bad-allowed",
            attack_pool_ids=("pool-a",),
            allowed="bad",  # type: ignore[arg-type]
            reason=None,
            attacks=1,
        )
    with pytest.raises(GameLifecycleError, match="Allowed FastDiceGroup"):
        FastDiceGroup(
            group_id="phase13c-fast-allowed-reason",
            attack_pool_ids=("pool-a",),
            allowed=True,
            reason="has-reason",
            attacks=1,
        )
    with pytest.raises(GameLifecycleError, match="requires reason"):
        FastDiceGroup(
            group_id="phase13c-fast-rejected-no-reason",
            attack_pool_ids=("pool-a",),
            allowed=False,
            reason=None,
            attacks=1,
        )

    constraint_payload = AttackAllocationConstraint(
        source_rule_ids=("constraint",),
        allowed_model_ids=("model-a", "model-b"),
        can_allocate_protected_characters=True,
        attacker_selected_model_id="model-a",
    ).to_payload()
    assert (
        AttackAllocationConstraint.from_payload(constraint_payload).to_payload()
        == constraint_payload
    )
    with pytest.raises(GameLifecycleError, match="attacker selection"):
        AttackAllocationConstraint(
            allowed_model_ids=("model-a",),
            attacker_selected_model_id="model-b",
        )
    with pytest.raises(GameLifecycleError, match="outside alive_model_ids"):
        AttackAllocationRuleContext(
            target_unit_instance_id="target",
            alive_model_ids=("model-a",),
            wounded_model_ids=("model-b",),
        )
    constrained_context = AttackAllocationRuleContext(
        target_unit_instance_id="target",
        alive_model_ids=("model-a", "model-b"),
        attacker_constraint=AttackAllocationConstraint(
            attacker_selected_model_id="model-c",
        ),
    )
    with pytest.raises(GameLifecycleError, match="not legal"):
        constrained_context.legal_model_ids()

    context = AttackAllocationRuleContext(
        target_unit_instance_id="target",
        alive_model_ids=("model-a", "model-b"),
    )
    allocation = AttackAllocation.from_context(
        context,
        allocated_model_id="model-a",
        forced=False,
    )
    assert AttackAllocation.from_payload(allocation.to_payload()) == allocation
    with pytest.raises(GameLifecycleError, match="legal"):
        AttackAllocation.from_context(context, allocated_model_id="model-c", forced=False)

    with pytest.raises(GameLifecycleError, match="damage accounting"):
        DamageApplication(
            target_unit_instance_id="target",
            model_instance_id="model-a",
            damage_kind=DamageKind.NORMAL,
            requested_damage=2,
            wounds_lost=1,
            excess_damage_lost=0,
            starting_wounds_remaining=2,
            final_wounds_remaining=1,
            destroyed=False,
        )
    with pytest.raises(GameLifecycleError, match="DamageKind token"):
        damage_kind_from_token(3)
    with pytest.raises(GameLifecycleError, match="Unsupported DamageKind"):
        damage_kind_from_token("not-damage")
    valid_damage = DamageApplication(
        target_unit_instance_id="target",
        model_instance_id="model-a",
        damage_kind=DamageKind.NORMAL,
        requested_damage=1,
        wounds_lost=1,
        excess_damage_lost=0,
        starting_wounds_remaining=2,
        final_wounds_remaining=1,
        destroyed=False,
    )
    with pytest.raises(GameLifecycleError, match="wound accounting"):
        MortalWoundApplication(
            target_unit_instance_id="target",
            mortal_wounds=2,
            spill_over=True,
            applications=(valid_damage,),
        )
    with pytest.raises(GameLifecycleError, match="Feel No Pain request"):
        build_feel_no_pain_request(
            request_id="phase13c-single-fnp",
            defender_player_id="player-b",
            lost_wound_context={},
            sources=(FeelNoPainSource(source_id="feel-no-pain", threshold=5),),
            decline_allowed=False,
        )
    with pytest.raises(GameLifecycleError, match="duplicate source IDs"):
        build_feel_no_pain_request(
            request_id="phase13c-duplicate-fnp",
            defender_player_id="player-b",
            lost_wound_context={},
            sources=(
                FeelNoPainSource(source_id="feel-no-pain", threshold=5),
                FeelNoPainSource(source_id="feel-no-pain", threshold=6),
            ),
            decline_allowed=True,
        )
    with pytest.raises(GameLifecycleError, match="Feel No Pain roll"):
        feel_no_pain_roll_spec(
            source="not-source",  # type: ignore[arg-type]
            player_id="player-b",
            model_instance_id=model.model_instance_id,
            wound_index=1,
        )
