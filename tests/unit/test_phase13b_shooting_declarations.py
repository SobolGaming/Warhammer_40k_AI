from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpression, DiceRollResult, DiceRollSpec, DiceRollState
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition
from warhammer40k_core.core.modifiers import ModifierStack, RollModifier
from warhammer40k_core.core.ruleset_descriptor import (
    CoverEffect,
    LineOfSightPolicy,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AttackProfile,
    DamageProfile,
    WeaponKeyword,
    WeaponProfile,
    WeaponProfilePayload,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.attack_sequence import (
    AttackModifierStackSet,
    AttackSequence,
    AttackSequenceEvent,
    AttackSequenceEventHandler,
    AttackSequenceHooks,
    AttackSequenceStep,
    DeferredMortalWounds,
    FastDiceGroup,
    HitRoll,
    WoundRoll,
    attack_sequence_step_from_token,
    cover_for_allocated_model,
    deadly_demise_mortal_wounds_roll_spec,
    deadly_demise_trigger_roll_spec,
    resolve_attack_sequence_until_blocked,
    wound_roll_target_number,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.core_stratagem_effects import GO_TO_GROUND_EFFECT_KIND
from warhammer40k_core.engine.damage_allocation import (
    DECLINE_DESTRUCTION_REACTION_OPTION_ID,
    SELECT_ALLOCATION_ORDER_DECISION_TYPE,
    SELECT_ATTACK_ALLOCATION_DECISION_TYPE,
    SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
    AllocationGroup,
    AllocationGroupPayload,
    AllocationGroupRole,
    AllocationOrderDecision,
    AttackAllocation,
    AttackAllocationConstraint,
    AttackAllocationDecision,
    AttackAllocationRuleContext,
    DamageApplication,
    DamageKind,
    DestructionReactionDecision,
    DestructionReactionKind,
    DestructionReactionSource,
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
    build_attack_allocation_request,
    build_destruction_reaction_request,
    build_feel_no_pain_request,
    continue_mortal_wound_application,
    damage_kind_from_token,
    destruction_reaction_kind_from_token,
    feel_no_pain_roll_spec,
    is_mortal_wound_feel_no_pain_request,
    model_by_id,
    mortal_wound_feel_no_pain_source_context,
    resolve_mortal_wound_feel_no_pain_decision,
)
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameState, GameStatePayload
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
    SELECT_SHOOTING_TYPE_DECISION_TYPE,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    OutOfPhaseShootingState,
    ShootingPhaseHandler,
    ShootingPhaseState,
    ShootingTypeSelection,
    ShootingUnitSelection,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.saves import (
    PlungingFireModifier,
    PlungingFireModifierResult,
    SaveKind,
    SaveOption,
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
    shooting_target_violation_code_from_token,
    unit_has_line_of_sight_to_target,
)
from warhammer40k_core.engine.shooting_types import (
    ShootingType,
    shooting_type_from_token,
    validate_shooting_type_tuple,
)
from warhammer40k_core.engine.transports import (
    FiringDeckSelection,
    FiringDeckWeaponSelection,
    TransportCapacityProfile,
    TransportCargoState,
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
from warhammer40k_core.geometry.visibility import (
    BenefitOfCoverResult,
    CoverSourceReason,
    CoverSourceRecord,
    VisibilityBlockerKind,
)
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack


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
    allocation = cast(dict[str, object], allocation_step["allocation"])
    allocation_group = cast(dict[str, object], allocation_step["allocation_group"])
    allocation_context = cast(dict[str, object], allocation["rule_context"])
    attacker_constraint = cast(dict[str, object], allocation_context["attacker_constraint"])

    assert selected_status.status_kind in {
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.UNSUPPORTED,
    }
    assert allocation_group["group_id"] == character_group_id
    assert cast(list[str], allocation_group["model_ids"]) == [character_model.model_instance_id]
    assert allocation["allocated_model_id"] == character_model.model_instance_id
    assert attacker_constraint["attacker_selected_group_id"] == character_group_id
    assert attacker_constraint["can_allocate_protected_characters"] is True
    assert PRECISION_RULE_ID in cast(list[str], attacker_constraint["source_rule_ids"])
    assert bodyguard_model.model_instance_id != allocation["allocated_model_id"]


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
    declined_allocation = cast(dict[str, object], declined_allocation_payload["allocation"])

    assert declined_allocation["allocated_model_id"] == bodyguard_model.model_instance_id

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
    hidden_allocation = cast(dict[str, object], hidden_allocation_payload["allocation"])

    assert hidden_status is not None or hidden_remaining is None
    assert hidden_status is None or _decision_request(hidden_status).decision_type != (
        SELECT_PRECISION_ALLOCATION_DECISION_TYPE
    )
    assert hidden_allocation["allocated_model_id"] == hidden_bodyguard.model_instance_id


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
    precision_allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=defender.unit_instance_id,
        attacker_constraint=AttackAllocationConstraint(
            source_rule_ids=(PRECISION_RULE_ID,),
            can_allocate_protected_characters=True,
        ),
    )
    precision_character_group = next(
        group
        for group in allocation_groups_for_context(
            state=state,
            allocation_context=precision_allocation_context,
            visible_model_ids=tuple(model.model_instance_id for model in defender.own_models),
        )
        if character_model.model_instance_id in group.model_ids
    )
    precision_character_group_payload = validate_json_value(precision_character_group.to_payload())
    precision_request = DecisionRequest(
        request_id="phase14e-precision-pool-request",
        decision_type=SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
        actor_id="player-a",
        payload={
            "attack_context": {
                "sequence_id": sequence.sequence_id,
                "pool_index": 0,
            },
            "eligible_character_groups": [precision_character_group_payload],
        },
        options=(
            DecisionOption(
                option_id="decline_precision",
                label="Decline Precision",
                payload={"selected_group_id": None, "selected_model_ids": []},
            ),
            DecisionOption(
                option_id=precision_character_group.group_id,
                label=precision_character_group.group_id,
                payload={
                    "selected_group_id": precision_character_group.group_id,
                    "selected_model_ids": list(precision_character_group.model_ids),
                },
            ),
        ),
    )
    lifecycle.decision_controller.request_decision(precision_request)
    lifecycle.decision_controller.submit_result(
        DecisionResult.for_request(
            result_id="phase14e-precision-pool-result",
            request=precision_request,
            selected_option_id=precision_character_group.group_id,
        )
    )
    second_attack = AttackSequence(
        sequence_id=sequence.sequence_id,
        attacker_player_id=sequence.attacker_player_id,
        attacking_unit_instance_id=sequence.attacking_unit_instance_id,
        attack_pools=sequence.attack_pools,
        attack_index=1,
    )
    attack_context_id = "phase14e-precision-pool:pool-001:attack-002"
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

    _remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=_ruleset(),
        attack_sequence=second_attack,
        already_allocated_model_ids=(character_model.model_instance_id,),
        dice_manager=DiceRollManager(
            "phase14e-precision-pool",
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id="phase14e-precision-pool-hit",
                    spec=hit_spec,
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id="phase14e-precision-pool-wound",
                    spec=wound_spec,
                    value=6,
                ),
            ),
        ),
    )
    allocation_payload = _attack_step_payload(
        _event_payloads(lifecycle, "attack_sequence_step"),
        AttackSequenceStep.ALLOCATE,
    )
    allocation_step = cast(dict[str, object], allocation_payload["payload"])
    allocation = cast(dict[str, object], allocation_step["allocation"])
    allocation_context = cast(dict[str, object], allocation["rule_context"])
    attacker_constraint = cast(dict[str, object], allocation_context["attacker_constraint"])
    precision_requests = [
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "decision_requested"
        and cast(dict[str, object], event.payload)["decision_type"]
        == SELECT_PRECISION_ALLOCATION_DECISION_TYPE
    ]

    assert status is None
    assert allocation["allocated_model_id"] == character_model.model_instance_id
    assert attacker_constraint["attacker_selected_group_id"] == precision_character_group.group_id
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
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=defender.unit_instance_id,
    )
    allocation_group = allocation_groups_for_context(
        state=state,
        allocation_context=allocation_context,
    )[0]
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
                    allocated_model_id=allocation_group.group_id,
                    attack_context_id=attack_context_id,
                ),
                value=save_value,
            )
        )

    remaining_sequence, _allocated_ids, status = resolve_attack_sequence_until_blocked(
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
    attack_events = _event_payloads(lifecycle, "attack_sequence_step")
    save_event_indexes = [
        index for index, event in enumerate(attack_events) if event["step"] == "save"
    ]
    damage_event_indexes = [
        index
        for index, event in enumerate(attack_events)
        if event["step"] == "damage"
        and cast(dict[str, object], event["payload"])["damage_application"] is not None
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
    assert status is None
    assert max(save_event_indexes) < min(damage_event_indexes)
    assert damage_context_ids == [
        "phase14e-grouped-saves:pool-001:attack-002",
        "phase14e-grouped-saves:pool-001:attack-001",
    ]
    assert grouped_allocation["attack_context_ids"] == [
        "phase14e-grouped-saves:pool-001:attack-001",
        "phase14e-grouped-saves:pool-001:attack-002",
        "phase14e-grouped-saves:pool-001:attack-003",
    ]


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
    assert remaining_sequence == sequence
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
        abilities=(AbilityDescriptor.sustained_hits(1),),
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
    assert cast(dict[str, object], hit_payload["payload"])["minimum_unmodified_success"] == 4
    assert cast(dict[str, object], hit_payload["payload"])["successful"] is False


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
        assert hit["target_number"] == 3
        assert hit["modifier"] == 1
        assert hit["successful"] is (roll_value == 6)


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


def test_phase14e_invulnerable_save_is_mandatory_without_save_kind_decision() -> None:
    lifecycle, units = _shooting_lifecycle(alpha_unit_ids=("intercessor-1",))
    state = _state(lifecycle)
    attacker = units["intercessor-1"]
    defender = units["enemy"]
    defender_model = replace(
        defender.own_models[0],
        characteristics=(
            *defender.own_models[0].characteristics,
            CharacteristicValue.from_raw(Characteristic.INVULNERABLE_SAVE, 4),
        ),
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

    assert payload["save_kind"] == SaveKind.INVULNERABLE.value
    assert payload["target_number"] == 4
    assert payload["successful"] is False
    retired_save_choice_type = "select_" + "saving_throw_kind"
    assert not any(
        event.event_type == "decision_requested"
        and cast(dict[str, object], event.payload)["decision_type"] == retired_save_choice_type
        for event in lifecycle.decision_controller.event_log.records
    )


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
    allocation_request = build_attack_allocation_request(
        request_id="phase13c-allocation-request",
        defender_player_id="player-b",
        attack_context={"attack_context_id": "phase13c-allocation"},
        allocation_context=allocation_context,
    )
    allocation_result = DecisionResult(
        result_id="phase13c-allocation-result",
        request_id=allocation_request.request_id,
        decision_type=allocation_request.decision_type,
        actor_id=allocation_request.actor_id,
        selected_option_id="model-b",
        payload=allocation_request.option_by_id("model-b").payload,
    )
    allocation_decision = AttackAllocationDecision.from_result(
        request=allocation_request,
        result=allocation_result,
    )
    assert allocation_decision.to_payload()["selected_model_id"] == "model-b"

    missing_model_request = DecisionRequest(
        request_id="phase13c-allocation-missing",
        decision_type=SELECT_ATTACK_ALLOCATION_DECISION_TYPE,
        actor_id="player-b",
        payload={"attack_context": {"attack_context_id": "missing-model"}},
        options=(DecisionOption(option_id="bad", label="Bad", payload={}),),
    )
    with pytest.raises(GameLifecycleError, match="missing model_instance_id"):
        AttackAllocationDecision.from_result(
            request=missing_model_request,
            result=DecisionResult(
                result_id="phase13c-allocation-missing-result",
                request_id=missing_model_request.request_id,
                decision_type=missing_model_request.decision_type,
                actor_id=missing_model_request.actor_id,
                selected_option_id="bad",
                payload={},
            ),
        )
    typed_model_request = DecisionRequest(
        request_id="phase13c-allocation-typed",
        decision_type=SELECT_ATTACK_ALLOCATION_DECISION_TYPE,
        actor_id="player-b",
        payload={"attack_context": {"attack_context_id": "typed-model"}},
        options=(DecisionOption(option_id="bad", label="Bad", payload={"model_instance_id": 3}),),
    )
    with pytest.raises(GameLifecycleError, match="model_instance_id must be a string"):
        AttackAllocationDecision.from_result(
            request=typed_model_request,
            result=DecisionResult(
                result_id="phase13c-allocation-typed-result",
                request_id=typed_model_request.request_id,
                decision_type=typed_model_request.decision_type,
                actor_id=typed_model_request.actor_id,
                selected_option_id="bad",
                payload={"model_instance_id": 3},
            ),
        )
    actorless_allocation_request = DecisionRequest(
        request_id="phase13c-allocation-actorless",
        decision_type=SELECT_ATTACK_ALLOCATION_DECISION_TYPE,
        actor_id=None,
        payload={"attack_context": {"attack_context_id": "actorless-allocation"}},
        options=(
            DecisionOption(
                option_id="model-a",
                label="model-a",
                payload={"model_instance_id": "model-a"},
            ),
        ),
    )
    with pytest.raises(GameLifecycleError, match="requires a defender actor"):
        AttackAllocationDecision.from_result(
            request=actorless_allocation_request,
            result=DecisionResult(
                result_id="phase13c-allocation-actorless-result",
                request_id=actorless_allocation_request.request_id,
                decision_type=actorless_allocation_request.decision_type,
                actor_id=None,
                selected_option_id="model-a",
                payload={"model_instance_id": "model-a"},
            ),
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
    with pytest.raises(GameLifecycleError, match="at least two legal groups"):
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
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=defender.unit_instance_id,
        attacker_constraint=AttackAllocationConstraint(
            source_rule_ids=(PRECISION_RULE_ID,),
            can_allocate_protected_characters=True,
        ),
    )
    allocation_groups = allocation_groups_for_context(
        state=state,
        allocation_context=allocation_context,
    )
    ordered_group_ids = tuple(group.group_id for group in allocation_groups)
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

    with pytest.raises(GameLifecycleError, match="target_number must match"):
        SavingThrow(
            save_kind=SaveKind.ARMOUR,
            target_number=4,
            roll_state=save_roll,
            unmodified_roll=4,
            final_roll=4,
            successful=True,
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
            option=valid_option,
        )
    invalid_roll_state_throw = SavingThrow(
        save_kind=SaveKind.ARMOUR,
        target_number=3,
        roll_state=cast(DiceRollState, "bad-roll-state"),
        unmodified_roll=3,
        final_roll=3,
        successful=True,
        option=valid_option,
    )
    with pytest.raises(GameLifecycleError, match="roll_state"):
        invalid_roll_state_throw.to_payload()

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

    source_a = FeelNoPainSource(source_id="feel-no-pain-a", threshold=5)
    source_b = FeelNoPainSource(source_id="feel-no-pain-b", threshold=6)
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

    assert final_status.status_kind is LifecycleStatusKind.UNSUPPORTED
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

    assert final_status.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert selected_source["source_id"] == selected_reaction_source.source_id
    assert selected_source["reaction_kind"] == selected_source_kind.value
    assert reaction_payload["selected_reaction_kind"] == selected_source_kind.value
    assert reaction_payload["action_host"] == expected_action_host
    assert reaction_payload["execution_status"] == "recorded_for_action_host"
    assert any(
        record.result.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE
        for record in lifecycle.decision_controller.records
    )


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


def test_phase13e_successful_deadly_demise_applies_mortal_wounds_before_removal() -> None:
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
    deadly_demise_source = DestructionReactionSource(
        source_id="phase13e-success-deadly-demise",
        reaction_kind=DestructionReactionKind.DEADLY_DEMISE,
        source_rule_id="phase13e-success-deadly-demise-rule",
        payload={
            "trigger_roll_threshold": 6,
            "range_inches": 6.0,
            "mortal_wounds": {"kind": "d3"},
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

    assert final_status.status_kind is LifecycleStatusKind.UNSUPPORTED
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

    assert remaining_sequence == sequence
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

    assert final_status.status_kind is LifecycleStatusKind.UNSUPPORTED
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

    assert decline_status.status_kind is LifecycleStatusKind.UNSUPPORTED
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
    with pytest.raises(GameLifecycleError, match="requires at least two legal models"):
        build_attack_allocation_request(
            request_id="phase13d-single-allocation",
            defender_player_id="player-b",
            attack_context={"attack_id": "phase13d-routing"},
            allocation_context=single_model_context,
        )
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
    with pytest.raises(GameLifecycleError, match="requires alive models"):
        continue_mortal_wound_application(
            state=state,
            request_id="phase13d-no-model-request",
            progress=no_models_progress,
        )

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
            target_number=armour_option.target_number,
            roll_state=save_roll,
            unmodified_roll=4,
            final_roll=4,
            successful=False,
            option=armour_option,
        )
    with pytest.raises(GameLifecycleError, match="save_kind must match option"):
        SavingThrow(
            save_kind=SaveKind.INVULNERABLE,
            target_number=armour_option.target_number,
            roll_state=save_roll,
            unmodified_roll=3,
            final_roll=3,
            successful=True,
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

    assert status.status_kind is LifecycleStatusKind.UNSUPPORTED
    state = _state(lifecycle)
    assert state.current_battle_phase is BattlePhase.CHARGE
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


def test_phase13f_full_shooting_gate_drains_attacks_before_completion() -> None:
    profile = _phase13f_gate_weapon_profile()
    lifecycle, units = _shooting_lifecycle(
        alpha_unit_ids=("intercessor-1", "intercessor-2"),
        enemy_unit_specs=(
            ("enemy", "core-intercessor-like-infantry", "core-intercessor-like", 10),
        ),
        enemy_pose=Pose.at(25.0, 35.0),
        catalog=_catalog_with_extra_bolt_profile(profile),
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

    assert final_status.status_kind is LifecycleStatusKind.UNSUPPORTED
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
    assert player_a_status.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert state.current_battle_phase is BattlePhase.CHARGE

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

    assert player_b_status.status_kind is LifecycleStatusKind.UNSUPPORTED
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

    assert ShootingUnitSelection.from_payload(selection.to_payload()) == selection
    assert ShootingTypeSelection.from_payload(shooting_type_selection.to_payload()) == (
        shooting_type_selection
    )
    assert ShootingPhaseState.from_payload(selected_with_type.to_payload()) == selected_with_type

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
    state.battlefield_state = scenario.battlefield_state
    state.mission_setup = replace(state.mission_setup, terrain_features=(far_ruin,))
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


def _phase13f_gate_weapon_profile() -> WeaponProfile:
    base = _weapon_profile_by_wargear(
        wargear_id="core-bolt-rifle",
        weapon_profile_id="core-bolt-rifle:standard",
    )
    return replace(
        base,
        profile_id="phase13f-gate-rifle",
        name="Phase 13F gate rifle",
        attack_profile=AttackProfile.fixed(4),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, -3),
        damage_profile=DamageProfile.fixed(3),
        keywords=(WeaponKeyword.TORRENT,),
        abilities=(),
    )


def _phase13f_cover_effect(target_unit_instance_id: str) -> PersistingEffect:
    return PersistingEffect(
        effect_id="phase13f-go-to-ground-cover",
        source_rule_id="core-stratagem:go-to-ground",
        owner_player_id="player-b",
        target_unit_instance_ids=(target_unit_instance_id,),
        started_battle_round=1,
        started_phase=BattlePhase.SHOOTING,
        expiration=EffectExpiration.end_phase(
            battle_round=1,
            phase=BattlePhase.SHOOTING,
            player_id="player-a",
        ),
        effect_payload={
            "effect_kind": GO_TO_GROUND_EFFECT_KIND,
            "benefit_of_cover": True,
        },
    )


def _submit_phase13f_pending_attack_choices(
    lifecycle: GameLifecycle,
    *,
    status: LifecycleStatus,
    result_id_prefix: str,
) -> LifecycleStatus:
    attack_decision_types = {
        SELECT_ATTACK_ALLOCATION_DECISION_TYPE,
        SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
        SELECT_FEEL_NO_PAIN_DECISION_TYPE,
        SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    }
    current = status
    for index in range(128):
        if current.status_kind is LifecycleStatusKind.UNSUPPORTED:
            return current
        request = _decision_request(current)
        if request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE:
            return current
        if request.decision_type not in attack_decision_types:
            raise AssertionError(f"Unexpected Phase 13F decision type {request.decision_type}.")
        option = request.options[0]
        current = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=f"{result_id_prefix}-{index:03d}",
                request=request,
                selected_option_id=option.option_id,
            )
        )
    raise AssertionError("Phase 13F attack sequence did not drain.")


def _attack_step_payloads(
    lifecycle: GameLifecycle,
    step: AttackSequenceStep,
) -> tuple[dict[str, object], ...]:
    return tuple(
        event
        for event in _event_payloads(lifecycle, "attack_sequence_step")
        if event["step"] == step.value
    )


def _save_payload_has_cover(event: dict[str, object]) -> bool:
    payload = cast(dict[str, object], event["payload"])
    option = cast(dict[str, object], payload["option"])
    cover_result = option.get("cover_result")
    if option["cover_applied"] is not True or not isinstance(cover_result, dict):
        return False
    cover_payload = cast(dict[str, object], cover_result)
    return cover_payload.get("has_benefit") is True


def _shooting_lifecycle(
    *,
    alpha_unit_ids: tuple[str, ...],
    game_id: str = "phase13b-game",
    alpha_datasheets: dict[str, tuple[str, str, int]] | None = None,
    enemy_datasheet: tuple[str, str, int] | None = None,
    enemy_unit_specs: tuple[tuple[str, str, str, int], ...] | None = None,
    embarked_unit_ids: tuple[str, ...] = (),
    enemy_pose: Pose | None = None,
    catalog: ArmyCatalog | None = None,
) -> tuple[GameLifecycle, dict[str, UnitInstance]]:
    resolved_enemy_pose = Pose.at(35.0, 35.0) if enemy_pose is None else enemy_pose
    config = _config(
        game_id=game_id,
        alpha_unit_ids=alpha_unit_ids,
        alpha_datasheets=alpha_datasheets,
        enemy_datasheet=enemy_datasheet,
        enemy_unit_specs=enemy_unit_specs,
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
    enemy_unit_index = 0
    for unit_key, unit in units.items():
        if unit_key in embarked_unit_ids:
            battlefield = battlefield.without_unit_placement(unit.unit_instance_id)
            continue
        army_id = unit.unit_instance_id.split(":", maxsplit=1)[0]
        player_id = "player-a" if army_id == "army-alpha" else "player-b"
        if army_id == "army-beta":
            poses = _compact_test_unit_poses(
                origin=Pose.at(
                    resolved_enemy_pose.position.x,
                    resolved_enemy_pose.position.y + (enemy_unit_index * 10.0),
                    resolved_enemy_pose.position.z,
                    facing_degrees=180.0,
                ),
                model_count=len(unit.own_models),
            )
            enemy_unit_index += 1
        elif unit.datasheet_id == "core-transport":
            poses = (Pose.at(10.0, 35.0 + (friendly_unit_index * 10.0)),)
        else:
            friendly_y = 35.0 + (friendly_unit_index * 10.0)
            poses = _compact_test_unit_poses(
                origin=Pose.at(10.0, friendly_y),
                model_count=len(unit.own_models),
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


def _compact_test_unit_poses(*, origin: Pose, model_count: int) -> tuple[Pose, ...]:
    if type(model_count) is not int or model_count < 1:
        raise AssertionError("Test unit poses require at least one model.")
    return tuple(
        Pose.at(
            origin.position.x + ((index % 5) * 1.4),
            origin.position.y + ((index // 5) * 1.4),
            origin.position.z,
            facing_degrees=origin.facing.degrees,
        )
        for index in range(model_count)
    )


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


def _catalog_with_replaced_bolt_profiles(
    weapon_profiles: tuple[WeaponProfile, ...],
) -> ArmyCatalog:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    updated_wargear: list[Wargear] = []
    for wargear in catalog.wargear:
        if wargear.wargear_id == "core-bolt-rifle":
            updated_wargear.append(replace(wargear, weapon_profiles=weapon_profiles))
            continue
        updated_wargear.append(wargear)
    return replace(catalog, wargear=tuple(updated_wargear))


def _config(
    *,
    game_id: str = "phase13b-game",
    alpha_unit_ids: tuple[str, ...],
    alpha_datasheets: dict[str, tuple[str, str, int]] | None,
    enemy_datasheet: tuple[str, str, int] | None,
    enemy_unit_specs: tuple[tuple[str, str, str, int], ...] | None = None,
    catalog: ArmyCatalog | None = None,
) -> GameConfig:
    resolved_catalog = ArmyCatalog.phase9a_canonical_content_pack() if catalog is None else catalog
    enemy_datasheet_id, enemy_model_profile_id, enemy_model_count = (
        ("core-intercessor-like-infantry", "core-intercessor-like", 5)
        if enemy_datasheet is None
        else enemy_datasheet
    )
    beta_unit_specs = (
        (("enemy", enemy_datasheet_id, enemy_model_profile_id, enemy_model_count),)
        if enemy_unit_specs is None
        else enemy_unit_specs
    )
    return GameConfig(
        game_id=game_id,
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
                unit_specs=beta_unit_specs,
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
    weapon_profile_id: str | None = None,
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
    selected_weapon = (
        weapons[0]
        if weapon_profile_id is None
        else next(weapon for weapon in weapons if weapon["weapon_profile_id"] == weapon_profile_id)
    )
    declarations = [
        WeaponDeclaration(
            attacker_model_instance_id=cast(str, selected_weapon["model_instance_id"]),
            wargear_id=cast(str, selected_weapon["wargear_id"]),
            weapon_profile_id=cast(str, selected_weapon["weapon_profile_id"]),
            target_unit_instance_id=target_unit_id,
            shooting_type=_first_shooting_type(target_candidate),
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
                shooting_type=_first_shooting_type(target_candidate),
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
    shooting_type: ShootingType = ShootingType.NORMAL,
) -> WeaponDeclarationPayload:
    payload: WeaponDeclarationPayload = {
        "attacker_model_instance_id": cast(str, weapon["model_instance_id"]),
        "wargear_id": cast(str, weapon["wargear_id"]),
        "weapon_profile_id": cast(str, weapon["weapon_profile_id"]),
        "target_unit_instance_id": target_unit_id,
        "shooting_type": shooting_type.value,
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


def _first_shooting_type(target_candidate: dict[str, object]) -> ShootingType:
    shooting_types = cast(list[str], target_candidate["shooting_types"])
    if not shooting_types:
        raise AssertionError("Target candidate has no shooting types.")
    return ShootingType(shooting_types[0])


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


def _select_shooting_unit_and_type(
    lifecycle: GameLifecycle,
    *,
    selection_request: DecisionRequest,
    unit_instance_id: str,
    selection_result_id: str,
    shooting_type: ShootingType = ShootingType.NORMAL,
    type_result_id: str | None = None,
) -> DecisionRequest:
    type_request = _decision_request(
        _submit_result(
            lifecycle,
            request=selection_request,
            option_id=unit_instance_id,
            result_id=selection_result_id,
        )
    )
    assert type_request.decision_type == SELECT_SHOOTING_TYPE_DECISION_TYPE
    type_payload = cast(dict[str, object], type_request.payload)
    assert type_payload["unit_instance_id"] == unit_instance_id
    assert shooting_type.value in {option.option_id for option in type_request.options}

    declaration_request = _decision_request(
        _submit_result(
            lifecycle,
            request=type_request,
            option_id=shooting_type.value,
            result_id=type_result_id or f"{selection_result_id}-type",
        )
    )
    assert declaration_request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE
    return declaration_request


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
    return RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase13b-test")


def _benefit_of_cover_result() -> BenefitOfCoverResult:
    source_record = CoverSourceRecord(
        feature_id="phase13c-cover-ruin",
        feature_kind=TerrainFeatureKind.RUINS,
        policy_kind=LineOfSightPolicy.TRUE_LINE_OF_SIGHT,
        reason=CoverSourceReason.NOT_FULLY_VISIBLE_BECAUSE_OF_FEATURE,
    )
    return BenefitOfCoverResult(
        has_benefit=True,
        cover_effect=CoverEffect.ATTACKER_BS_MODIFIER,
        source_feature_ids=("phase13c-cover-ruin",),
        source_policy_kinds=(LineOfSightPolicy.TRUE_LINE_OF_SIGHT,),
        source_records=(source_record,),
        los_cache_key="phase13c-cover-cache",
        target_unit_visible=True,
        target_unit_fully_visible=False,
        non_stacking=True,
        ap_zero_save_bonus_excluded_for_save_3_plus_or_better=True,
    )


def _fixed_roll_result(
    *,
    roll_id: str,
    spec: DiceRollSpec,
    value: int,
) -> DiceRollResult:
    return DiceRollResult.from_values(
        roll_id=roll_id,
        spec=spec,
        values=(value,),
        source="fixed",
    )


def _attack_pool_for_test(
    *,
    attacker: UnitInstance,
    defender: UnitInstance,
    weapon_profile: WeaponProfile,
    attacks: int,
    target_unit_instance_id: str | None = None,
) -> RangedAttackPool:
    defender_model_ids = tuple(model.model_instance_id for model in defender.own_models)
    return RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id=attacker.wargear_selections[0].wargear_ids[0],
        weapon_profile_id=weapon_profile.profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=(
            defender.unit_instance_id
            if target_unit_instance_id is None
            else target_unit_instance_id
        ),
        shooting_type=ShootingType.NORMAL,
        attacks=attacks,
        target_visible_model_ids=defender_model_ids,
        target_in_range_model_ids=defender_model_ids,
    )


def _replace_enemy_with_attached_character_fixture(
    *,
    state: GameState,
    defender: UnitInstance,
) -> UnitInstance:
    bodyguard_model = defender.own_models[0]
    character_model = replace(
        defender.own_models[1],
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
    attached_defender = replace(
        defender,
        keywords=tuple(sorted({*defender.keywords, "ATTACHED_UNIT"})),
        own_models=(bodyguard_model, character_model),
    )
    _replace_unit_instance_in_state(state=state, replacement=attached_defender)
    battlefield = state.battlefield_state
    assert battlefield is not None
    placement = battlefield.unit_placement_by_id(defender.unit_instance_id)
    kept_model_ids = {model.model_instance_id for model in attached_defender.own_models}
    state.replace_battlefield_state(
        battlefield.with_unit_placement(
            placement.with_model_placements(
                tuple(
                    model_placement
                    for model_placement in placement.model_placements
                    if model_placement.model_instance_id in kept_model_ids
                )
            )
        )
    )
    return attached_defender


def _replace_unit_instance_in_state(
    *,
    state: GameState,
    replacement: UnitInstance,
) -> None:
    for army_index, army in enumerate(state.army_definitions):
        units = tuple(
            replacement if unit.unit_instance_id == replacement.unit_instance_id else unit
            for unit in army.units
        )
        if units != army.units:
            state.army_definitions[army_index] = replace(army, units=units)
            return
    raise AssertionError(f"Missing unit {replacement.unit_instance_id}.")


def _precision_request_for_fixture(
    *,
    lifecycle: GameLifecycle,
    attacker: UnitInstance,
    defender: UnitInstance,
    weapon_profile: WeaponProfile,
    sequence_id: str,
) -> tuple[DecisionRequest, AttackSequence, tuple[str, ...]]:
    state = _state(lifecycle)
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
    remaining_sequence, allocated_ids, status = resolve_attack_sequence_until_blocked(
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
            ),
        ),
    )
    if remaining_sequence is None:
        raise AssertionError("Precision fixture unexpectedly completed.")
    return _decision_request(cast(LifecycleStatus, status)), remaining_sequence, allocated_ids


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


def _event_payloads(lifecycle: GameLifecycle, event_type: str) -> tuple[dict[str, object], ...]:
    return tuple(
        cast(dict[str, object], event.payload)
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == event_type
    )


def _attack_step_payload(
    events: tuple[dict[str, object], ...],
    step: AttackSequenceStep,
) -> dict[str, object]:
    for event in events:
        if event["step"] == step.value:
            return event
    raise AssertionError(f"Missing attack sequence step {step.value}.")
