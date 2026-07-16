from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any, cast

import pytest
from tests.deployment_submission_helpers import submit_all_deployments_if_pending
from tests.movement_submission_helpers import (
    straight_line_witness_for_unit,
    submit_movement_proposal,
)
from tests.phase11c_command_phase_helpers import (
    battle_state,
    battle_state_with_center_objective_positions,
    default_unit_selection,
    unit_by_id,
)

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import DatasheetDefinition, DatasheetKeywordSet
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.advance_eligibility_hooks import (
    AdvanceEligibilityContext,
    AdvanceEligibilityGrant,
    AdvanceEligibilityHookBinding,
    AdvanceEligibilityHookRegistry,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.deployment import (
    SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
    SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
)
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.runtime import build_runtime_content_bundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.emperors_children import (
    army_rule,
)
from warhammer40k_core.engine.fall_back_hooks import FallBackEligibilityContext
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import MOVEMENT_PROPOSAL_DECISION_TYPE
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.phases.charge import (
    SELECT_CHARGING_UNIT_DECISION_TYPE,
    ChargePhaseState,
    _charge_target_candidates,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.phases.movement import (
    COMPLETE_REINFORCEMENTS_OPTION_ID,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    SELECT_REINFORCEMENT_UNIT_DECISION_TYPE,
    AdvancedUnitState,
    AdvanceRollRequest,
    AdvanceRollResult,
    FellBackUnitState,
    MovementDiceRecord,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.phases.shooting import (
    COMPLETE_SHOOTING_PHASE_OPTION_ID,
    SELECT_SHOOTING_TYPE_DECISION_TYPE,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
    ShootingPhaseState,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.target_restriction_hooks import (
    ChargeTargetRestrictionContext,
    ChargeTargetRestrictionHookBinding,
    ChargeTargetRestrictionHookRegistry,
    ShootingTargetRestrictionContext,
    ShootingTargetRestrictionHookBinding,
    ShootingTargetRestrictionHookRegistry,
    TargetRestriction,
)
from warhammer40k_core.engine.turn_start_engagement import (
    TURN_START_ENGAGEMENT_SNAPSHOT_EFFECT_KIND,
    record_turn_start_engagement_snapshot,
    turn_start_enemy_unit_ids_for_friendly_unit,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.engine.weapon_declaration import (
    RangedAttackPool,
    ShootingDeclarationProposal,
    WeaponDeclaration,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    chapter_approved_2026_27_mission_pack,
)

EMPERORS_CHILDREN_TEST_DATASHEET_ID = "phase17g-emperors-children-noise-marine"
EMPERORS_CHILDREN_UNIT_ID = "army-alpha:intercessor-unit-1"
ENEMY_UNIT_ID = "army-beta:intercessor-unit-3"
EMPERORS_CHILDREN_LIFECYCLE_UNIT_ID = "army-alpha:noise-marine"
EMPERORS_CHILDREN_RESTRICTED_TARGET_ID = "army-beta:restricted-target"
EMPERORS_CHILDREN_LEGAL_TARGET_ID = "army-beta:legal-target"


def test_runtime_bundle_loads_thrill_seekers_opt_in_surfaces() -> None:
    bundle = build_runtime_content_bundle(_emperors_children_config())
    summary_payload = bundle.to_summary_payload()

    assert army_rule.ADVANCE_ELIGIBILITY_HOOK_ID in summary_payload["advance_eligibility_hook_ids"]
    assert army_rule.FALL_BACK_ELIGIBILITY_HOOK_ID in summary_payload["fall_back_hook_ids"]
    assert (
        army_rule.SHOOTING_TARGET_RESTRICTION_HOOK_ID
        in summary_payload["shooting_target_restriction_hook_ids"]
    )
    assert (
        army_rule.CHARGE_TARGET_RESTRICTION_HOOK_ID
        in summary_payload["charge_target_restriction_hook_ids"]
    )


def test_thrill_seekers_advance_eligibility_is_consumed_by_movement_lifecycle() -> None:
    lifecycle, movement_request = _emperors_children_lifecycle_to_movement_unit_selection(
        enemy_unit_ids=("enemy-unit",),
        pose_factory=_shooting_and_charge_reachable_deployment_pose,
    )

    action_request = _decision_request(
        _submit_result(
            lifecycle,
            request=movement_request,
            option_id=EMPERORS_CHILDREN_LIFECYCLE_UNIT_ID,
            result_id="phase17g-ec-select-advance-unit",
        )
    )
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE

    proposal_request = _decision_request(
        _submit_result(
            lifecycle,
            request=action_request,
            option_id=MovementPhaseActionKind.ADVANCE.value,
            result_id="phase17g-ec-select-advance-action",
        )
    )
    assert proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    proposal_status = submit_movement_proposal(
        lifecycle,
        request=proposal_request,
        result_id="phase17g-ec-submit-advance-proposal",
        unit_instance_id=EMPERORS_CHILDREN_LIFECYCLE_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.ADVANCE,
        movement_mode=MovementMode.ADVANCE,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=EMPERORS_CHILDREN_LIFECYCLE_UNIT_ID,
            dx=1.0,
        ),
    )
    proposal_status = _decline_optional_stratagem_if_pending(
        lifecycle,
        status=proposal_status,
        result_id="phase17g-ec-decline-post-advance-stratagem",
    )

    state = _state(lifecycle)
    advanced = state.advanced_unit_state_for_unit(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=EMPERORS_CHILDREN_LIFECYCLE_UNIT_ID,
    )
    assert advanced is not None
    assert advanced.can_shoot is True
    assert advanced.can_declare_charge is True

    resolved_payload = _last_event_payload(lifecycle, "advance_eligibility_hooks_resolved")
    grants = cast(list[dict[str, object]], resolved_payload["grants"])
    assert [grant["hook_id"] for grant in grants] == [army_rule.ADVANCE_ELIGIBILITY_HOOK_ID]
    assert grants[0]["can_shoot"] is True
    assert grants[0]["can_declare_charge"] is True

    shooting_request = _decision_request_of_type(
        lifecycle,
        status=proposal_status,
        decision_type=SELECT_SHOOTING_UNIT_DECISION_TYPE,
        result_id_prefix="phase17g-ec-after-advance",
    )
    assert EMPERORS_CHILDREN_LIFECYCLE_UNIT_ID in {
        option.option_id for option in shooting_request.options
    }

    charge_request = _decision_request_of_type(
        lifecycle,
        status=_submit_result(
            lifecycle,
            request=shooting_request,
            option_id=COMPLETE_SHOOTING_PHASE_OPTION_ID,
            result_id="phase17g-ec-complete-shooting-after-advance",
        ),
        decision_type=SELECT_CHARGING_UNIT_DECISION_TYPE,
        result_id_prefix="phase17g-ec-after-shooting",
    )
    assert EMPERORS_CHILDREN_LIFECYCLE_UNIT_ID in {
        option.option_id for option in charge_request.options
    }


def test_thrill_seekers_shooting_restriction_is_consumed_by_declaration_path() -> None:
    lifecycle, _movement_request = _emperors_children_lifecycle_to_movement_unit_selection(
        enemy_unit_ids=("restricted-target", "legal-target"),
        pose_factory=_turn_start_engagement_deployment_pose,
    )
    state = _state(lifecycle)
    _reseed_turn_start_engagement_snapshot_from_current_positions(state)

    assert turn_start_enemy_unit_ids_for_friendly_unit(
        state,
        player_id="player-a",
        battle_round=state.battle_round,
        friendly_unit_instance_id=EMPERORS_CHILDREN_LIFECYCLE_UNIT_ID,
    ) == (EMPERORS_CHILDREN_RESTRICTED_TARGET_ID,)

    _replace_unit_poses(
        state,
        unit_instance_id=EMPERORS_CHILDREN_LIFECYCLE_UNIT_ID,
        poses=_compact_poses(origin=Pose.at(19.0, 20.0), model_count=5),
    )
    state.record_fell_back_unit_state(
        FellBackUnitState(
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=EMPERORS_CHILDREN_LIFECYCLE_UNIT_ID,
            can_shoot=True,
            can_declare_charge=True,
        )
    )
    state.advance_to_next_battle_phase()
    lifecycle_payload = lifecycle.to_payload()
    lifecycle_payload["decisions"] = DecisionController().to_payload()
    lifecycle = GameLifecycle.from_payload(lifecycle_payload)

    shooting_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    assert shooting_request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE
    assert EMPERORS_CHILDREN_LIFECYCLE_UNIT_ID in {
        option.option_id for option in shooting_request.options
    }
    shooting_type_request = _decision_request(
        _submit_result(
            lifecycle,
            request=shooting_request,
            option_id=EMPERORS_CHILDREN_LIFECYCLE_UNIT_ID,
            result_id="phase17g-ec-select-shooter-with-restricted-target",
        )
    )
    assert shooting_type_request.decision_type == SELECT_SHOOTING_TYPE_DECISION_TYPE
    declaration_request = _decision_request(
        _submit_result(
            lifecycle,
            request=shooting_type_request,
            option_id=ShootingType.NORMAL.value,
            result_id="phase17g-ec-select-normal-shooting",
        )
    )
    assert declaration_request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE

    proposal_request = _shooting_proposal_request_payload(declaration_request)
    target_candidates = cast(list[dict[str, object]], proposal_request["target_candidates"])
    restricted_candidates = tuple(
        candidate
        for candidate in target_candidates
        if candidate["target_unit_instance_id"] == EMPERORS_CHILDREN_RESTRICTED_TARGET_ID
    )
    legal_candidates = tuple(
        candidate
        for candidate in target_candidates
        if candidate["target_unit_instance_id"] == EMPERORS_CHILDREN_LEGAL_TARGET_ID
    )
    assert restricted_candidates
    assert all(candidate["is_legal"] is False for candidate in restricted_candidates)
    assert {candidate["violation_code"] for candidate in restricted_candidates} == {
        "runtime_target_restriction"
    }
    assert all(
        army_rule.SHOOTING_TARGET_RESTRICTION_HOOK_ID
        in cast(list[str], candidate["targeting_rule_ids"])
        for candidate in restricted_candidates
    )
    assert any(candidate["is_legal"] is True for candidate in legal_candidates)

    invalid_proposal = _shooting_declaration_for_target(
        request=declaration_request,
        target_unit_id=EMPERORS_CHILDREN_RESTRICTED_TARGET_ID,
    )
    before_records = len(lifecycle.decision_controller.records)
    invalid_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17g-ec-invalid-restricted-shooting-target",
            request_id=declaration_request.request_id,
            decision_type=declaration_request.decision_type,
            actor_id=declaration_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(invalid_proposal.to_payload()),
        )
    )

    validation = cast(
        dict[str, object],
        cast(dict[str, object], invalid_status.payload)["proposal_validation"],
    )
    violations = cast(list[dict[str, object]], validation["violations"])
    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert validation["status"] == "invalid"
    assert violations[0]["violation_code"] == "target_runtime_target_restriction"
    assert lifecycle.decision_controller.queue.pending_requests == (declaration_request,)
    assert len(lifecycle.decision_controller.records) == before_records
    shooting_phase_state = _state(lifecycle).shooting_phase_state
    assert shooting_phase_state is not None
    assert shooting_phase_state.attack_pools == ()


def test_thrill_seekers_grants_shoot_and_charge_after_advance_and_fall_back() -> None:
    state = _emperors_children_battle_state()

    advance_grant = army_rule.thrill_seekers_advance_eligibility(
        AdvanceEligibilityContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
            movement_request_id="phase17g-ec-advance-request",
            movement_result_id="phase17g-ec-advance-result",
        )
    )
    fall_back_grant = army_rule.thrill_seekers_fall_back_eligibility(
        FallBackEligibilityContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
            movement_request_id="phase17g-ec-fall-back-request",
            movement_result_id="phase17g-ec-fall-back-result",
        )
    )

    assert advance_grant is not None
    assert advance_grant.can_shoot is True
    assert advance_grant.can_declare_charge is True
    assert fall_back_grant is not None
    assert fall_back_grant.can_shoot is True
    assert fall_back_grant.can_declare_charge is True


def test_thrill_seekers_does_not_apply_to_non_emperors_children_army() -> None:
    state = battle_state()

    grant = army_rule.thrill_seekers_advance_eligibility(
        AdvanceEligibilityContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
            movement_request_id="phase17g-ec-non-faction-advance-request",
            movement_result_id="phase17g-ec-non-faction-advance-result",
        )
    )

    assert grant is None


def test_thrill_seekers_blocks_target_engaged_with_unit_at_turn_start() -> None:
    state = _emperors_children_battle_state(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((0.0, 0.0),),
    )
    record_turn_start_engagement_snapshot(
        state=state,
        player_id="player-a",
    )
    state.record_advanced_unit_state(
        _advanced_unit_state(state=state, unit_instance_id=EMPERORS_CHILDREN_UNIT_ID)
    )
    _advance_state_to_phase(state, BattlePhase.SHOOTING)

    restriction = army_rule.thrill_seekers_shooting_target_restriction(
        ShootingTargetRestrictionContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            attacking_unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
            target_unit_instance_id=ENEMY_UNIT_ID,
        )
    )

    assert restriction is not None
    assert restriction.violation_code == "thrill_seekers_turn_start_engagement"


def test_thrill_seekers_blocks_target_attacked_by_another_unit_this_phase() -> None:
    state = _emperors_children_battle_state()
    acting_attacker = unit_by_id(state, EMPERORS_CHILDREN_UNIT_ID)
    other_attacker = _copy_unit_for_test(
        acting_attacker,
        unit_instance_id="army-alpha:noise-marine-unit-2",
    )
    _append_unit_to_player_army(state, player_id="player-a", unit=other_attacker)
    defender = unit_by_id(state, ENEMY_UNIT_ID)
    state.record_advanced_unit_state(
        _advanced_unit_state(state=state, unit_instance_id=EMPERORS_CHILDREN_UNIT_ID)
    )
    _advance_state_to_phase(state, BattlePhase.SHOOTING)
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        attack_pools=(
            _attack_pool_for_test(
                attacker=other_attacker,
                defender=defender,
                weapon_profile=_first_weapon_profile_for_unit(other_attacker),
            ),
        ),
    )

    restriction = army_rule.thrill_seekers_shooting_target_restriction(
        ShootingTargetRestrictionContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            attacking_unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
            target_unit_instance_id=ENEMY_UNIT_ID,
        )
    )

    assert restriction is not None
    assert restriction.violation_code == "thrill_seekers_target_already_selected"


def test_thrill_seekers_allows_target_already_attacked_by_same_unit_this_phase() -> None:
    state = _emperors_children_battle_state()
    attacker = unit_by_id(state, EMPERORS_CHILDREN_UNIT_ID)
    defender = unit_by_id(state, ENEMY_UNIT_ID)
    state.record_advanced_unit_state(
        _advanced_unit_state(state=state, unit_instance_id=EMPERORS_CHILDREN_UNIT_ID)
    )
    _advance_state_to_phase(state, BattlePhase.SHOOTING)
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        attack_pools=(
            _attack_pool_for_test(
                attacker=attacker,
                defender=defender,
                weapon_profile=_first_weapon_profile_for_unit(attacker),
            ),
        ),
    )

    restriction = army_rule.thrill_seekers_shooting_target_restriction(
        ShootingTargetRestrictionContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            attacking_unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
            target_unit_instance_id=ENEMY_UNIT_ID,
        )
    )

    assert restriction is None


def test_thrill_seekers_charge_target_restriction_reaches_charge_candidate_filter() -> None:
    state = _emperors_children_battle_state(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((6.0, 0.0),),
    )
    state.record_fell_back_unit_state(
        FellBackUnitState(
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
            can_shoot=True,
            can_declare_charge=True,
        )
    )
    _advance_state_to_phase(state, BattlePhase.CHARGE)
    state.charge_phase_state = ChargePhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        declared_target_unit_instance_ids_by_unit={
            "army-alpha:previous-charger": (ENEMY_UNIT_ID,),
        },
    )

    candidates = _charge_target_candidates(
        state=state,
        unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        charge_target_restriction_hooks=(
            build_runtime_content_bundle(
                _emperors_children_config()
            ).charge_target_restriction_hook_registry
        ),
    )

    assert len(candidates) == 1
    assert candidates[0].target_unit_instance_id == ENEMY_UNIT_ID
    assert candidates[0].is_legal is False
    assert candidates[0].violation_code == "thrill_seekers_target_already_selected"


def test_thrill_seekers_charge_restriction_requires_advance_or_fall_back() -> None:
    state = _emperors_children_battle_state()
    _advance_state_to_phase(state, BattlePhase.CHARGE)
    state.charge_phase_state = ChargePhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        declared_target_unit_instance_ids_by_unit={
            "army-alpha:previous-charger": (ENEMY_UNIT_ID,),
        },
    )

    restriction = army_rule.thrill_seekers_charge_target_restriction(
        ChargeTargetRestrictionContext(
            state=state,
            player_id="player-a",
            battle_round=state.battle_round,
            charging_unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
            target_unit_instance_id=ENEMY_UNIT_ID,
        )
    )

    assert restriction is None


def test_advance_eligibility_registry_fails_fast_on_invalid_bindings() -> None:
    state = _emperors_children_battle_state()
    context = AdvanceEligibilityContext(
        state=state,
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
        movement_request_id="phase17g-ec-registry-request",
        movement_result_id="phase17g-ec-registry-result",
    )

    def _stubbed_invalid_advance_handler(_context: AdvanceEligibilityContext) -> object:
        return object()

    invalid_binding = AdvanceEligibilityHookBinding(
        hook_id="phase17g:advance:invalid",
        source_id="phase17g:advance:source",
        handler=cast(Any, _stubbed_invalid_advance_handler),
    )
    with pytest.raises(GameLifecycleError, match="return grants or None"):
        AdvanceEligibilityHookRegistry.from_bindings((invalid_binding,)).grants_for(context)

    def _stubbed_drift_advance_handler(
        _context: AdvanceEligibilityContext,
    ) -> AdvanceEligibilityGrant:
        return AdvanceEligibilityGrant(
            hook_id="phase17g:advance:other",
            source_id="phase17g:advance:source",
            can_shoot=True,
            can_declare_charge=False,
        )

    drift_binding = AdvanceEligibilityHookBinding(
        hook_id="phase17g:advance:drift",
        source_id="phase17g:advance:source",
        handler=_stubbed_drift_advance_handler,
    )
    with pytest.raises(GameLifecycleError, match="hook_id drift"):
        AdvanceEligibilityHookRegistry.from_bindings((drift_binding,)).grants_for(context)

    with pytest.raises(GameLifecycleError, match="handler must be callable"):
        AdvanceEligibilityHookBinding(
            hook_id="phase17g:advance:not-callable",
            source_id="phase17g:advance:source",
            handler=cast(Any, None),
        )
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        AdvanceEligibilityHookRegistry(bindings=cast(Any, []))
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        AdvanceEligibilityHookRegistry.from_bindings((drift_binding, drift_binding))
    with pytest.raises(GameLifecycleError, match="must grant at least one permission"):
        AdvanceEligibilityGrant(
            hook_id="phase17g:advance:no-permission",
            source_id="phase17g:advance:source",
            can_shoot=False,
            can_declare_charge=False,
        )


def test_target_restriction_registries_fail_fast_on_invalid_bindings() -> None:
    state = _emperors_children_battle_state()
    shooting_context = ShootingTargetRestrictionContext(
        state=state,
        player_id="player-a",
        battle_round=state.battle_round,
        attacking_unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
        target_unit_instance_id=ENEMY_UNIT_ID,
    )
    charge_context = ChargeTargetRestrictionContext(
        state=state,
        player_id="player-a",
        battle_round=state.battle_round,
        charging_unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
        target_unit_instance_id=ENEMY_UNIT_ID,
    )

    def _stubbed_invalid_shooting_restriction_handler(
        _context: ShootingTargetRestrictionContext,
    ) -> object:
        return object()

    shooting_binding = ShootingTargetRestrictionHookBinding(
        hook_id="phase17g:shooting:invalid",
        source_id="phase17g:restriction:source",
        handler=cast(Any, _stubbed_invalid_shooting_restriction_handler),
    )
    with pytest.raises(GameLifecycleError, match="return restrictions or None"):
        ShootingTargetRestrictionHookRegistry.from_bindings((shooting_binding,)).restrictions_for(
            shooting_context
        )

    def _stubbed_drift_charge_restriction_handler(
        _context: ChargeTargetRestrictionContext,
    ) -> TargetRestriction:
        return TargetRestriction(
            hook_id="phase17g:charge:other",
            source_id="phase17g:restriction:source",
            violation_code="phase17g_restriction",
            message="Target is restricted by the test hook.",
        )

    charge_binding = ChargeTargetRestrictionHookBinding(
        hook_id="phase17g:charge:drift",
        source_id="phase17g:restriction:source",
        handler=_stubbed_drift_charge_restriction_handler,
    )
    with pytest.raises(GameLifecycleError, match="hook_id drift"):
        ChargeTargetRestrictionHookRegistry.from_bindings((charge_binding,)).restrictions_for(
            charge_context
        )

    with pytest.raises(GameLifecycleError, match="handler must be callable"):
        ShootingTargetRestrictionHookBinding(
            hook_id="phase17g:shooting:not-callable",
            source_id="phase17g:restriction:source",
            handler=cast(Any, None),
        )
    with pytest.raises(GameLifecycleError, match="bindings must be a tuple"):
        ChargeTargetRestrictionHookRegistry(bindings=cast(Any, []))
    with pytest.raises(GameLifecycleError, match="hook IDs must be unique"):
        ChargeTargetRestrictionHookRegistry.from_bindings((charge_binding, charge_binding))
    with pytest.raises(GameLifecycleError, match="message must not be empty"):
        TargetRestriction(
            hook_id="phase17g:restriction:empty-message",
            source_id="phase17g:restriction:source",
            violation_code="phase17g_restriction",
            message=" ",
        )


def test_turn_start_engagement_snapshot_is_idempotent_and_fails_fast() -> None:
    state = _emperors_children_battle_state(
        player_a_offsets=((0.0, 0.0),),
        player_b_offsets=((0.0, 0.0),),
    )

    first_snapshot = record_turn_start_engagement_snapshot(state=state, player_id="player-a")
    second_snapshot = record_turn_start_engagement_snapshot(state=state, player_id="player-a")

    assert first_snapshot is not None
    assert second_snapshot is first_snapshot
    assert turn_start_enemy_unit_ids_for_friendly_unit(
        state,
        player_id="player-a",
        battle_round=state.battle_round,
        friendly_unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
    ) == (ENEMY_UNIT_ID,)

    with pytest.raises(GameLifecycleError, match="requires a GameState"):
        record_turn_start_engagement_snapshot(state=cast(Any, object()), player_id="player-a")
    with pytest.raises(GameLifecycleError, match="lookup requires a GameState"):
        turn_start_enemy_unit_ids_for_friendly_unit(
            cast(Any, object()),
            player_id="player-a",
            battle_round=state.battle_round,
            friendly_unit_instance_id=EMPERORS_CHILDREN_UNIT_ID,
        )


def _emperors_children_lifecycle_to_movement_unit_selection(
    *,
    enemy_unit_ids: tuple[str, ...],
    pose_factory: Callable[[int, str, str], Pose],
) -> tuple[GameLifecycle, DecisionRequest]:
    lifecycle = GameLifecycle()
    lifecycle.start(_emperors_children_config(enemy_unit_ids=enemy_unit_ids))

    first_secondary_request = _decision_request(lifecycle.advance_until_decision_or_terminal())
    assert first_secondary_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    second_secondary_status = _submit_result(
        lifecycle,
        request=first_secondary_request,
        option_id="fixed:assassination:bring_it_down",
        result_id="phase17g-ec-secondary-player-a",
    )
    second_secondary_request = _decision_request(second_secondary_status)
    assert second_secondary_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    deployment_status = _submit_result(
        lifecycle,
        request=second_secondary_request,
        option_id="fixed:assassination:bring_it_down",
        result_id="phase17g-ec-secondary-player-b",
    )
    while deployment_status.decision_request is None:
        deployment_status = lifecycle.advance_until_decision_or_terminal()
    deployment_status = _submit_all_deployments_through_step(
        lifecycle,
        status=deployment_status,
    )
    _apply_fixture_poses_from_factory(_state(lifecycle), pose_factory=pose_factory)
    movement_request = _decision_request_of_type(
        lifecycle,
        status=deployment_status,
        decision_type=SELECT_MOVEMENT_UNIT_DECISION_TYPE,
        result_id_prefix="phase17g-ec-post-deployment",
    )
    assert _state(lifecycle).battle_round == 1
    return lifecycle, movement_request


def _submit_all_deployments_through_step(
    lifecycle: GameLifecycle,
    *,
    status: LifecycleStatus,
) -> LifecycleStatus:
    current = status
    for _index in range(48):
        if _state(lifecycle).current_setup_step is not SetupStep.DEPLOY_ARMIES:
            return current
        if current.decision_request is None:
            current = lifecycle._advance_once()  # pyright: ignore[reportPrivateUsage]
            continue
        if current.decision_request.decision_type not in {
            SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
            SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
        }:
            raise AssertionError(
                f"Expected deployment request, got {current.decision_request.decision_type}."
            )
        current = submit_all_deployments_if_pending(
            lifecycle,
            current,
            result_id_prefix="phase17g-ec-deploy",
            pose_factory=_legal_deployment_pose_for_lifecycle_fixture,
        )
        if current.status_kind is LifecycleStatusKind.INVALID:
            raise AssertionError(
                f"Deployment fixture submission failed: {current.message} {current.payload}"
            )
    raise AssertionError("Deployment fixture submission exceeded deterministic guard.")


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


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
    request = status.decision_request
    if request is None or request.decision_type != STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        return status
    return lifecycle.submit_decision(
        DecisionResult(
            result_id=result_id,
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=stratagem_decline_payload(),
        )
    )


def _decision_request_of_type(
    lifecycle: GameLifecycle,
    *,
    status: LifecycleStatus,
    decision_type: str,
    result_id_prefix: str,
) -> DecisionRequest:
    current = status
    for index in range(24):
        request = current.decision_request
        if request is None:
            current = lifecycle.advance_until_decision_or_terminal()
            continue
        if request.decision_type == decision_type:
            return request
        if request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
            current = _decline_optional_stratagem_if_pending(
                lifecycle,
                status=current,
                result_id=f"{result_id_prefix}-decline-stratagem-{index}",
            )
            continue
        if request.decision_type == SELECT_REINFORCEMENT_UNIT_DECISION_TYPE:
            current = _submit_result(
                lifecycle,
                request=request,
                option_id=COMPLETE_REINFORCEMENTS_OPTION_ID,
                result_id=f"{result_id_prefix}-complete-reinforcements-{index}",
            )
            continue
        raise AssertionError(f"Expected {decision_type}, got {request.decision_type}.")
    raise AssertionError(f"Expected {decision_type}, but no matching request was emitted.")


def _state(lifecycle: GameLifecycle) -> GameState:
    state = lifecycle.state
    assert state is not None
    return state


def _reseed_turn_start_engagement_snapshot_from_current_positions(state: GameState) -> None:
    existing_snapshot_ids = tuple(
        effect.effect_id
        for effect in state.persisting_effects
        if isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind") == TURN_START_ENGAGEMENT_SNAPSHOT_EFFECT_KIND
        and effect.owner_player_id == "player-a"
        and effect.started_battle_round == state.battle_round
    )
    state.remove_persisting_effects_by_id(existing_snapshot_ids)
    snapshot = record_turn_start_engagement_snapshot(state=state, player_id="player-a")
    assert snapshot is not None


def _last_event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, JsonValue]:
    for event in reversed(lifecycle.decision_controller.event_log.records):
        if event.event_type == event_type:
            payload = event.payload
            assert isinstance(payload, dict)
            return payload
    raise AssertionError(f"Missing event {event_type}.")


def _shooting_and_charge_reachable_deployment_pose(
    index: int,
    _player_id: str,
    model_instance_id: str,
) -> Pose:
    unit_instance_id = _unit_instance_id_from_model_instance_id(model_instance_id)
    if unit_instance_id == EMPERORS_CHILDREN_LIFECYCLE_UNIT_ID:
        return _compact_poses(origin=Pose.at(10.0, 20.0), model_count=5)[index]
    if unit_instance_id == "army-beta:enemy-unit":
        return _compact_poses(
            origin=Pose.at(20.0, 20.0, facing_degrees=180.0),
            model_count=5,
        )[index]
    raise AssertionError(f"Unexpected unit {unit_instance_id}.")


def _turn_start_engagement_deployment_pose(
    index: int,
    _player_id: str,
    model_instance_id: str,
) -> Pose:
    unit_instance_id = _unit_instance_id_from_model_instance_id(model_instance_id)
    if unit_instance_id == EMPERORS_CHILDREN_LIFECYCLE_UNIT_ID:
        return _compact_poses(origin=Pose.at(10.0, 20.0), model_count=5)[index]
    if unit_instance_id == EMPERORS_CHILDREN_RESTRICTED_TARGET_ID:
        return _compact_poses(
            origin=Pose.at(10.0, 20.0, facing_degrees=180.0),
            model_count=5,
        )[index]
    if unit_instance_id == EMPERORS_CHILDREN_LEGAL_TARGET_ID:
        return _compact_poses(
            origin=Pose.at(28.0, 20.0, facing_degrees=180.0),
            model_count=5,
        )[index]
    raise AssertionError(f"Unexpected unit {unit_instance_id}.")


def _legal_deployment_pose_for_lifecycle_fixture(
    index: int,
    player_id: str,
    model_instance_id: str,
) -> Pose:
    unit_instance_id = _unit_instance_id_from_model_instance_id(model_instance_id)
    base_y_by_unit_id = {
        EMPERORS_CHILDREN_LIFECYCLE_UNIT_ID: 3.0,
        "army-beta:enemy-unit": 24.0,
        EMPERORS_CHILDREN_RESTRICTED_TARGET_ID: 24.0,
        EMPERORS_CHILDREN_LEGAL_TARGET_ID: 33.0,
    }
    base_y = base_y_by_unit_id[unit_instance_id]
    row = index // 3
    column = index % 3
    if player_id == "player-b":
        return Pose.at(57.0 - (row * 1.8), base_y + (column * 1.8), facing_degrees=180.0)
    return Pose.at(3.0 + (row * 1.8), base_y + (column * 1.8))


def _compact_poses(*, origin: Pose, model_count: int) -> tuple[Pose, ...]:
    return tuple(
        Pose.at(
            origin.position.x + ((index % 5) * 1.4),
            origin.position.y + ((index // 5) * 1.4),
            origin.position.z,
            facing_degrees=origin.facing.degrees,
        )
        for index in range(model_count)
    )


def _unit_instance_id_from_model_instance_id(model_instance_id: str) -> str:
    return model_instance_id.rsplit(":", 2)[0]


def _replace_unit_poses(
    state: GameState,
    *,
    unit_instance_id: str,
    poses: tuple[Pose, ...],
) -> None:
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    placement = battlefield_state.unit_placement_by_id(unit_instance_id)
    assert len(poses) == len(placement.model_placements)
    updated_placement = placement.with_model_placements(
        tuple(
            model_placement.with_pose(pose)
            for model_placement, pose in zip(placement.model_placements, poses, strict=True)
        )
    )
    state.replace_battlefield_state(battlefield_state.with_unit_placement(updated_placement))


def _apply_fixture_poses_from_factory(
    state: GameState,
    *,
    pose_factory: Callable[[int, str, str], Pose],
) -> None:
    battlefield_state = state.battlefield_state
    assert battlefield_state is not None
    updated_battlefield = battlefield_state
    for army in state.army_definitions:
        for unit in army.units:
            placement = updated_battlefield.unit_placement_by_id(unit.unit_instance_id)
            updated_placement = placement.with_model_placements(
                tuple(
                    model_placement.with_pose(
                        pose_factory(
                            index,
                            model_placement.player_id,
                            model_placement.model_instance_id,
                        )
                    )
                    for index, model_placement in enumerate(placement.model_placements)
                )
            )
            updated_battlefield = updated_battlefield.with_unit_placement(updated_placement)
    state.replace_battlefield_state(updated_battlefield)


def _shooting_proposal_request_payload(request: DecisionRequest) -> dict[str, JsonValue]:
    payload = cast(dict[str, JsonValue], request.payload)
    return cast(dict[str, JsonValue], payload["proposal_request"])


def _shooting_declaration_for_target(
    *,
    request: DecisionRequest,
    target_unit_id: str,
) -> ShootingDeclarationProposal:
    proposal_request = _shooting_proposal_request_payload(request)
    available_weapons = cast(list[dict[str, JsonValue]], proposal_request["available_weapons"])
    selected_weapon = available_weapons[0]
    return ShootingDeclarationProposal(
        proposal_request_id=cast(str, proposal_request["request_id"]),
        proposal_kind=cast(str, proposal_request["proposal_kind"]),
        player_id=cast(str, proposal_request["active_player_id"]),
        battle_round=cast(int, proposal_request["battle_round"]),
        unit_instance_id=cast(str, proposal_request["unit_instance_id"]),
        source_decision_request_id=cast(str, proposal_request["source_decision_request_id"]),
        source_decision_result_id=cast(str, proposal_request["source_decision_result_id"]),
        declarations=(
            WeaponDeclaration(
                attacker_model_instance_id=cast(str, selected_weapon["model_instance_id"]),
                wargear_id=cast(str, selected_weapon["wargear_id"]),
                weapon_profile_id=cast(str, selected_weapon["weapon_profile_id"]),
                target_unit_instance_id=target_unit_id,
                shooting_type=ShootingType.NORMAL,
            ),
        ),
        firing_deck_selection=None,
        visibility_cache_key=cast(str, proposal_request["visibility_cache_key"]),
    )


def _emperors_children_battle_state(
    *,
    player_a_offsets: tuple[tuple[float, float], ...] = ((0.0, 0.0),),
    player_b_offsets: tuple[tuple[float, float], ...] = ((6.0, 0.0),),
) -> GameState:
    state = battle_state_with_center_objective_positions(
        player_a_offsets=player_a_offsets,
        player_b_offsets=player_b_offsets,
    )
    _mark_player_as_emperors_children(state, player_id="player-a")
    return state


def _mark_player_as_emperors_children(state: GameState, *, player_id: str) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        if army.player_id != player_id:
            updated_armies.append(army)
            continue
        updated_armies.append(
            replace(
                army,
                detachment_selection=replace(
                    army.detachment_selection,
                    faction_id=army_rule.EMPERORS_CHILDREN_FACTION_ID,
                ),
                units=tuple(
                    replace(unit, faction_keywords=(army_rule.EMPERORS_CHILDREN_FACTION_KEYWORD,))
                    for unit in army.units
                ),
            )
        )
    state.army_definitions = updated_armies


def _copy_unit_for_test(unit: UnitInstance, *, unit_instance_id: str) -> UnitInstance:
    return replace(
        unit,
        unit_instance_id=unit_instance_id,
        own_models=tuple(
            replace(model, model_instance_id=f"{unit_instance_id}:model-{index + 1}")
            for index, model in enumerate(unit.own_models)
        ),
    )


def _append_unit_to_player_army(state: GameState, *, player_id: str, unit: UnitInstance) -> None:
    state.army_definitions = [
        replace(army, units=(*army.units, unit)) if army.player_id == player_id else army
        for army in state.army_definitions
    ]


def _advanced_unit_state(*, state: GameState, unit_instance_id: str) -> AdvancedUnitState:
    request = AdvanceRollRequest.for_unit(
        request_id=f"phase17g-ec-advance-{unit_instance_id}",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=unit_instance_id,
    )
    roll_state = DiceRollManager("phase17g-ec-advance-state").roll_fixed(
        request.spec,
        [3],
    )
    advance_roll = AdvanceRollResult.from_roll_state(request=request, roll_state=roll_state)
    return AdvancedUnitState(
        player_id="player-a",
        battle_round=state.battle_round,
        unit_instance_id=unit_instance_id,
        movement_dice_record=MovementDiceRecord(
            player_id="player-a",
            battle_round=state.battle_round,
            unit_instance_id=unit_instance_id,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            advance_roll=advance_roll,
        ),
        can_shoot=True,
        can_declare_charge=True,
    )


def _advance_state_to_phase(state: GameState, phase: BattlePhase) -> None:
    while state.current_battle_phase is not phase:
        if state.current_battle_phase is None:
            raise AssertionError("battle state ended before expected phase")
        state.advance_to_next_battle_phase()


def _attack_pool_for_test(
    *,
    attacker: UnitInstance,
    defender: UnitInstance,
    weapon_profile: WeaponProfile,
) -> RangedAttackPool:
    defender_model_ids = tuple(model.model_instance_id for model in defender.own_models)
    return RangedAttackPool(
        attacker_model_instance_id=attacker.own_models[0].model_instance_id,
        wargear_id=attacker.wargear_selections[0].wargear_ids[0],
        weapon_profile_id=weapon_profile.profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=defender.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=defender_model_ids,
        target_in_range_model_ids=defender_model_ids,
    )


def _first_weapon_profile_for_unit(unit: UnitInstance) -> WeaponProfile:
    wargear_id = unit.wargear_selections[0].wargear_ids[0]
    for wargear in ArmyCatalog.phase9a_canonical_content_pack().wargear:
        if wargear.wargear_id == wargear_id:
            return wargear.weapon_profiles[0]
    raise AssertionError(f"Missing test wargear {wargear_id}.")


def _emperors_children_config(
    *,
    enemy_unit_ids: tuple[str, ...] = ("enemy-unit",),
) -> GameConfig:
    catalog = _emperors_children_catalog()
    return GameConfig(
        game_id="phase17g-emperors-children-lifecycle-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
            descriptor_version="core-v2-phase17g-emperors-children-test",
        ),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id=army_rule.EMPERORS_CHILDREN_FACTION_ID,
                    detachment_ids=("frenzied-host",),
                ),
                force_disposition_id="phase17g-force",
                unit_selections=(
                    UnitMusterSelection(
                        unit_selection_id="noise-marine",
                        datasheet_id=EMPERORS_CHILDREN_TEST_DATASHEET_ID,
                        model_profile_selections=(
                            ModelProfileSelection(
                                model_profile_id="core-intercessor-like",
                                model_count=5,
                            ),
                        ),
                    ),
                ),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id="purge-the-foe",
                unit_selections=tuple(
                    default_unit_selection(unit_id) for unit_id in enemy_unit_ids
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=_emperors_children_mission_setup(),
    )


def _emperors_children_mission_setup() -> MissionSetup:
    return replace(
        MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
        terrain_features=(),
        terrain_areas=(),
        battlefield_regions=(),
        objective_terrain_areas=(),
    )


def _emperors_children_catalog() -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    return replace(
        base_catalog,
        datasheets=(*base_catalog.datasheets, _emperors_children_datasheet(base_datasheet)),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=army_rule.EMPERORS_CHILDREN_FACTION_ID,
                name="Emperor's Children",
                faction_keywords=(army_rule.EMPERORS_CHILDREN_FACTION_KEYWORD,),
                source_ids=("gw-11e-faction-detachments-2026-27:faction:emperors-children",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id="frenzied-host",
                name="Frenzied Host",
                faction_id=army_rule.EMPERORS_CHILDREN_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(EMPERORS_CHILDREN_TEST_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force",),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:emperors-children:frenzied-host",
                ),
            ),
        ),
    )


def _emperors_children_datasheet(base_datasheet: DatasheetDefinition) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=EMPERORS_CHILDREN_TEST_DATASHEET_ID,
        name="Noise Marine",
        keywords=DatasheetKeywordSet(
            keywords=("Infantry", "Battleline"),
            faction_keywords=(army_rule.EMPERORS_CHILDREN_FACTION_KEYWORD,),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:emperors-children:noise-marine",),
    )
