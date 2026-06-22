from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest
from tests.deployment_submission_helpers import submit_all_deployments_if_pending
from tests.movement_submission_helpers import (
    straight_line_witness_for_unit,
    submit_action_and_movement_proposal,
)
from tests.unit.test_phase10o_fall_back import (
    _advance_to_movement_unit_selection,  # pyright: ignore[reportPrivateUsage]
    _decision_request,  # pyright: ignore[reportPrivateUsage]
    _fall_back_forward_pose,  # pyright: ignore[reportPrivateUsage]
    _fall_back_witness,  # pyright: ignore[reportPrivateUsage]
    _move_first_enemy_model_into_side_engagement,  # pyright: ignore[reportPrivateUsage]
    _state,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.adapters.contracts import ParameterizedSubmission
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import (
    DatasheetDefinition,
    DatasheetKeywordSet,
    DatasheetWargearOption,
)
from warhammer40k_core.core.detachment import (
    DetachmentDefinition,
    EnhancementDefinition,
    EnhancementSubtype,
)
from warhammer40k_core.core.detachment import (
    StratagemDefinition as CatalogStratagemDefinition,
)
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import (
    FightEligibilityKind,
    FightOrderingBandKind,
    FightTypeKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyMusterRequest,
    EnhancementAssignment,
    validate_roster_legality,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.command_points import (
    CommandPointGainStatus,
    CommandPointSourceKind,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.cavalcade_of_chaos import (  # noqa: E501
    enhancements,
    rule,
    stratagems,
)
from warhammer40k_core.engine.fall_back_hooks import (
    FallBackEligibilityContext,
    FallBackEligibilityGrant,
    FallBackEligibilityHookBinding,
    FallBackEligibilityHookRegistry,
)
from warhammer40k_core.engine.fight_activation_abilities import (
    FIGHT_ACTIVATION_ABILITY_DECISION_TYPE,
    FightActivationAbilityContext,
    FightActivationAbilityHookBinding,
    FightActivationAbilityHookRegistry,
    FightActivationAbilityOption,
)
from warhammer40k_core.engine.fight_order import (
    FIGHT_ACTIVATION_DECISION_TYPE,
    FightActivationSelection,
    fight_activation_option_id,
)
from warhammer40k_core.engine.fight_resolution import (
    MELEE_DECLARATION_PROPOSAL_KIND,
    SUBMIT_MELEE_DECLARATION_DECISION_TYPE,
    MeleeDeclarationProposal,
    MeleeDeclarationProposalRequest,
    MeleeTargetAllocation,
    MeleeWeaponDeclaration,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalRequest,
    PlacementProposalPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.charge import (
    COMPLETE_CHARGE_PHASE_OPTION_ID,
    SELECT_CHARGING_UNIT_DECISION_TYPE,
    ChargePhaseHandler,
)
from warhammer40k_core.engine.phases.movement import (
    COMPLETE_REINFORCEMENTS_OPTION_ID,
    SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    SELECT_REINFORCEMENT_UNIT_DECISION_TYPE,
    DesperateEscapeRequirementReason,
    FallBackModeKind,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.phases.shooting import (
    COMPLETE_SHOOTING_PHASE_OPTION_ID,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    ShootingPhaseHandler,
)
from warhammer40k_core.engine.reserve_declarations import (
    SELECT_RESERVE_DECLARATION_DECISION_TYPE,
)
from warhammer40k_core.engine.reserves import (
    ReserveKind,
    ReserveStatus,
    ReserveUnitPointValue,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    STRATAGEM_DECISION_TYPE,
)
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionRecord,
)

_CAVALCADE_TEST_DATASHEET_ID = "phase17g-cavalcade-mounted-daemon"
_CAVALCADE_UNIT_ID = "army-alpha:intercessor-unit-1"
_CAVALCADE_RESERVE_UNIT_ID = "army-alpha:reserve-unit"
_ENEMY_UNIT_ID = "army-beta:intercessor-unit-2"
_OTHER_DAEMON_DETACHMENT_ID = "phase17g-other-daemon-detachment"
_ORDERED_FALL_BACK_OPTION_ID = (
    f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.ORDERED_RETREAT.value}"
)


def test_cavalcade_unholy_avalanche_grants_fall_back_shoot_and_charge_permissions() -> None:
    config = _cavalcade_config()
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    _move_first_enemy_model_into_side_engagement(lifecycle)
    state = _state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)
    summary = bundle.to_summary_payload()

    assert rule.HOOK_ID in summary["fall_back_hook_ids"]
    assert rule.SOURCE_RULE_ID in summary["selected_execution_record_ids"]
    assert any(
        path.endswith(".chaos_daemons.detachments.cavalcade_of_chaos.manifest")
        for path in summary["selected_module_paths"]
    )

    selection_request = _decision_request(movement_status)
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-cavalcade-select-mounted",
            request=selection_request,
            selected_option_id=_CAVALCADE_UNIT_ID,
        )
    )
    action_status = _decline_stratagem_window_if_present(
        lifecycle,
        action_status,
        result_id="phase17g-cavalcade-decline-warp-riders",
    )
    action_request = _decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    assert _ORDERED_FALL_BACK_OPTION_ID in {option.option_id for option in action_request.options}
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    unit_placement = state.battlefield_state.unit_placement_by_id(_CAVALCADE_UNIT_ID)

    fall_back_status = submit_action_and_movement_proposal(
        lifecycle,
        request=action_request,
        option_id=_ORDERED_FALL_BACK_OPTION_ID,
        action_result_id="phase17g-cavalcade-fall-back-action",
        proposal_result_id="phase17g-cavalcade-fall-back-proposal",
        unit_instance_id=_CAVALCADE_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.FALL_BACK,
        movement_mode=MovementMode.FALL_BACK,
        fall_back_mode=FallBackModeKind.ORDERED_RETREAT,
        witness=_fall_back_witness(
            unit_placement,
            first_model_end_pose=_fall_back_forward_pose(unit_placement),
        ),
    )

    assert fall_back_status.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
    }
    fell_back_state = state.fell_back_unit_state_for_unit(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_CAVALCADE_UNIT_ID,
    )
    assert fell_back_state is not None
    assert fell_back_state.can_shoot
    assert fell_back_state.can_declare_charge
    grant_event = _event_payload(lifecycle, "fall_back_eligibility_hooks_resolved")
    grants = cast(list[JsonValue], grant_event["grants"])
    grant = cast(dict[str, JsonValue], grants[0])
    replay_payload = cast(dict[str, JsonValue], grant["replay_payload"])
    assert grant["hook_id"] == rule.HOOK_ID
    assert grant["source_id"] == rule.SOURCE_RULE_ID
    assert grant["can_shoot"] is True
    assert grant["can_declare_charge"] is True
    assert replay_payload["effect_kind"] == "unholy_avalanche"
    assert replay_payload["unit_instance_id"] == _CAVALCADE_UNIT_ID

    shooting_state = _state_at_phase(state, BattlePhase.SHOOTING)
    shooting_status = ShootingPhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
        army_catalog=config.army_catalog,
    ).begin_phase(state=shooting_state, decisions=DecisionController())
    shooting_request = _decision_request(shooting_status)
    assert shooting_request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE
    assert {option.option_id for option in shooting_request.options} >= {
        _CAVALCADE_UNIT_ID,
        COMPLETE_SHOOTING_PHASE_OPTION_ID,
    }

    charge_state = _state_at_phase(state, BattlePhase.CHARGE)
    charge_status = ChargePhaseHandler(
        ruleset_descriptor=config.ruleset_descriptor,
    ).begin_phase(state=charge_state, decisions=DecisionController())
    charge_request = _decision_request(charge_status)
    assert charge_request.decision_type == SELECT_CHARGING_UNIT_DECISION_TYPE
    assert {option.option_id for option in charge_request.options} >= {
        _CAVALCADE_UNIT_ID,
        COMPLETE_CHARGE_PHASE_OPTION_ID,
    }


def test_cavalcade_warp_riders_registers_for_selected_mounted_unit_only() -> None:
    config = _cavalcade_config()
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    state = _state(lifecycle)
    _grant_cp(state, player_id="player-a", amount=1)
    bundle = _runtime_content_bundle(lifecycle)
    summary = bundle.to_summary_payload()

    assert stratagems.WARP_RIDERS_HANDLER_ID in summary["stratagem_handler_ids"]
    assert stratagems.WARP_RIDERS_SOURCE_RULE_ID in summary["selected_execution_record_ids"]
    assert (
        stratagems.WARP_RIDERS_RECORD_ID
        in summary["stratagem_index_record_ids_by_player_id"]["player-a"]
    )
    assert (
        stratagems.WARP_RIDERS_RECORD_ID
        not in summary["stratagem_index_record_ids_by_player_id"]["player-b"]
    )

    selection_request = _decision_request(movement_status)
    stratagem_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-warp-riders-select-mounted",
            request=selection_request,
            selected_option_id=_CAVALCADE_UNIT_ID,
        )
    )
    stratagem_request = _decision_request(stratagem_status)
    assert stratagem_request.decision_type == STRATAGEM_DECISION_TYPE
    warp_option = _required_option_id_containing(
        stratagem_request,
        stratagems.WARP_RIDERS_STRATAGEM_ID,
    )
    command_points_before_use = state.command_point_total("player-a")

    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-warp-riders-use",
            request=stratagem_request,
            selected_option_id=warp_option,
        )
    )
    action_request = _decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    assert state.command_point_total("player-a") == command_points_before_use - 1

    effect_event = _event_payload(lifecycle, "warp_riders_mobile_granted")
    persisting_effect = cast(dict[str, JsonValue], effect_event["persisting_effect"])
    effect_payload = cast(dict[str, JsonValue], persisting_effect["effect_payload"])
    assert effect_event["player_id"] == "player-a"
    assert effect_payload["effect_kind"] == "movement_keyword_grant"
    assert effect_payload["granted_keywords"] == ["MOBILE"]
    assert persisting_effect["target_unit_instance_ids"] == [_CAVALCADE_UNIT_ID]

    move_status = submit_action_and_movement_proposal(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        action_result_id="phase17g-warp-riders-normal-move-action",
        proposal_result_id="phase17g-warp-riders-normal-move-proposal",
        unit_instance_id=_CAVALCADE_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_CAVALCADE_UNIT_ID,
            dx=1.0,
        ),
    )

    assert move_status.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
    }
    movement_event = _event_payload(lifecycle, "movement_activation_completed")
    model_movements = cast(list[JsonValue], movement_event["model_movements"])
    first_model_movement = cast(dict[str, JsonValue], model_movements[0])
    assert "MOBILE" in cast(list[str], first_model_movement["movement_keywords"])
    assert first_model_movement["temporary_movement_keywords"] == ["MOBILE"]


def test_cavalcade_warp_riders_not_offered_for_non_mounted_selected_unit() -> None:
    config = _cavalcade_config(friendly_keywords=("Khorne",))
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    _grant_cp(_state(lifecycle), player_id="player-a", amount=1)

    selection_request = _decision_request(movement_status)
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-warp-riders-select-not-mounted",
            request=selection_request,
            selected_option_id=_CAVALCADE_UNIT_ID,
        )
    )
    action_request = _decision_request(action_status)

    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE


def test_cavalcade_warp_riders_not_registered_without_cavalcade_detachment() -> None:
    config = _non_cavalcade_daemon_config()
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    _grant_cp(_state(lifecycle), player_id="player-a", amount=1)
    summary = _runtime_content_bundle(lifecycle).to_summary_payload()

    assert stratagems.WARP_RIDERS_HANDLER_ID not in summary["stratagem_handler_ids"]
    assert (
        stratagems.WARP_RIDERS_RECORD_ID
        not in summary["stratagem_index_record_ids_by_player_id"]["player-a"]
    )
    assert (
        stratagems.FROM_BEYOND_THE_VEIL_RECORD_ID
        not in summary["stratagem_index_record_ids_by_player_id"]["player-a"]
    )
    assert (
        stratagems.INESCAPABLE_MANIFESTATIONS_RECORD_ID
        not in summary["stratagem_index_record_ids_by_player_id"]["player-a"]
    )

    selection_request = _decision_request(movement_status)
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-warp-riders-select-non-cavalcade",
            request=selection_request,
            selected_option_id=_CAVALCADE_UNIT_ID,
        )
    )
    action_request = _decision_request(action_status)

    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE


def test_cavalcade_from_beyond_the_veil_arrives_from_strategic_reserves_round_one() -> None:
    config = _cavalcade_config(include_reserve_unit=True)
    lifecycle, movement_status = _advance_to_movement_unit_selection_with_reserve(config)
    state = _state(lifecycle)
    reserve_state = state.reserve_state_for_unit(_CAVALCADE_RESERVE_UNIT_ID)
    assert reserve_state is not None
    assert reserve_state.status is ReserveStatus.IN_RESERVES
    assert reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES
    _grant_cp(state, player_id="player-a", amount=1)
    command_points_before_use = state.command_point_total("player-a")
    summary = _runtime_content_bundle(lifecycle).to_summary_payload()

    assert (
        stratagems.FROM_BEYOND_THE_VEIL_RECORD_ID
        in summary["stratagem_index_record_ids_by_player_id"]["player-a"]
    )
    assert (
        stratagems.FROM_BEYOND_THE_VEIL_RECORD_ID
        not in summary["stratagem_index_record_ids_by_player_id"]["player-b"]
    )

    selection_request = _decision_request(movement_status)
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-from-veil-select-board-unit",
            request=selection_request,
            selected_option_id=_CAVALCADE_UNIT_ID,
        )
    )
    action_status = _decline_stratagem_window_if_present(
        lifecycle,
        action_status,
        result_id="phase17g-from-veil-decline-warp-riders",
    )
    action_request = _decision_request(action_status)
    movement_status = submit_action_and_movement_proposal(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        action_result_id="phase17g-from-veil-normal-move-action",
        proposal_result_id="phase17g-from-veil-normal-move-proposal",
        unit_instance_id=_CAVALCADE_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_CAVALCADE_UNIT_ID,
            dx=1.0,
        ),
    )
    reinforcement_request = _decision_request(movement_status)
    assert reinforcement_request.decision_type == SELECT_REINFORCEMENT_UNIT_DECISION_TYPE
    movement_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-from-veil-complete-normal-reinforcements",
            request=reinforcement_request,
            selected_option_id=COMPLETE_REINFORCEMENTS_OPTION_ID,
        )
    )
    stratagem_request = _decision_request(movement_status)
    assert stratagem_request.decision_type == STRATAGEM_DECISION_TYPE
    from_beyond_option = _required_option_id_containing(
        stratagem_request,
        stratagems.FROM_BEYOND_THE_VEIL_STRATAGEM_ID,
    )

    placement_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-from-veil-use",
            request=stratagem_request,
            selected_option_id=from_beyond_option,
        )
    )
    placement_request = _decision_request(placement_status)
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        placement_request.payload
    )
    assert placement_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
    assert proposal_request.proposal_kind is ProposalKind.STRATEGIC_RESERVES
    assert proposal_request.placement_kinds == (BattlefieldPlacementKind.STRATEGIC_RESERVES,)
    assert proposal_request.context is not None
    assert proposal_request.context["stratagem_handler_id"] == "generic:ingress-move"
    assert proposal_request.context["from_start_of_battle"] is True
    assert _state(lifecycle).command_point_total("player-a") == command_points_before_use - 1

    final_status = _submit_placement_proposal(
        lifecycle,
        request=placement_request,
        result_id="phase17g-from-veil-placement",
        unit_instance_id=reserve_state.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        attempted_placement=_strategic_reserve_placement(
            state,
            unit_instance_id=reserve_state.unit_instance_id,
        ),
    )

    assert final_status.status_kind is not LifecycleStatusKind.INVALID
    arrived_state = _state(lifecycle).reserve_state_for_unit(reserve_state.unit_instance_id)
    assert arrived_state is not None
    assert arrived_state.status is ReserveStatus.ARRIVED
    movement_phase_state = _state(lifecycle).movement_phase_state
    assert movement_phase_state is not None
    assert reserve_state.unit_instance_id in movement_phase_state.moved_unit_ids
    resolved_event = _event_payload(lifecycle, "rapid_ingress_resolved")
    stratagem_use = cast(dict[str, JsonValue], resolved_event["stratagem_use"])
    assert stratagem_use["stratagem_id"] == stratagems.FROM_BEYOND_THE_VEIL_STRATAGEM_ID
    assert stratagem_use["handler_id"] == "generic:ingress-move"


def test_cavalcade_inescapable_manifestations_forces_desperate_escape_mode() -> None:
    config = _cavalcade_config(turn_order=("player-b", "player-a"))
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    state = _state(lifecycle)
    _move_first_enemy_model_into_side_engagement(lifecycle)
    _grant_cp(state, player_id="player-a", amount=1)
    command_points_before_use = state.command_point_total("player-a")

    selection_request = _decision_request(movement_status)
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-inescapable-select-enemy",
            request=selection_request,
            selected_option_id=_ENEMY_UNIT_ID,
        )
    )
    action_request = _decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    assert _ORDERED_FALL_BACK_OPTION_ID in {option.option_id for option in action_request.options}

    stratagem_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-inescapable-fall-back-action",
            request=action_request,
            selected_option_id=_ORDERED_FALL_BACK_OPTION_ID,
        )
    )
    stratagem_request = _decision_request(stratagem_status)
    assert stratagem_request.decision_type == STRATAGEM_DECISION_TYPE
    inescapable_option = _required_option_id_containing(
        stratagem_request,
        stratagems.INESCAPABLE_MANIFESTATIONS_STRATAGEM_ID,
    )

    proposal_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-inescapable-use",
            request=stratagem_request,
            selected_option_id=inescapable_option,
        )
    )
    proposal_decision_request = _decision_request(proposal_status)
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        proposal_decision_request.payload
    )
    assert proposal_decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert proposal_request.proposal_kind is ProposalKind.FALL_BACK
    assert proposal_request.context is not None
    assert proposal_request.context["fall_back_mode"] == FallBackModeKind.DESPERATE_ESCAPE.value
    assert proposal_request.context["declared_fall_back_mode"] == (
        FallBackModeKind.ORDERED_RETREAT.value
    )
    assert proposal_request.context["forced_desperate_escape_source_rule_ids"] == [
        stratagems.INESCAPABLE_MANIFESTATIONS_SOURCE_RULE_ID
    ]
    assert _state(lifecycle).command_point_total("player-a") == command_points_before_use - 1

    effect_event = _event_payload(lifecycle, "forced_fall_back_desperate_escape_registered")
    assert effect_event["fall_back_unit_instance_id"] == _ENEMY_UNIT_ID
    assert effect_event["forcing_unit_instance_id"] == _CAVALCADE_UNIT_ID

    unit_placement = _unit_placement(state, _ENEMY_UNIT_ID)
    movement_payload = MovementProposalPayload(
        proposal_request_id=proposal_decision_request.request_id,
        proposal_kind=ProposalKind.FALL_BACK,
        unit_instance_id=_ENEMY_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.FALL_BACK.value,
        movement_mode=MovementMode.FALL_BACK.value,
        fall_back_mode=FallBackModeKind.DESPERATE_ESCAPE.value,
        witness=_fall_back_witness(
            unit_placement,
            first_model_end_pose=_fall_back_forward_pose(unit_placement),
        ),
    )
    final_status = lifecycle.submit_decision(
        DecisionResult(
            result_id="phase17g-inescapable-fall-back-proposal",
            request_id=proposal_decision_request.request_id,
            decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=proposal_decision_request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(movement_payload.to_payload()),
        )
    )

    assert final_status.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
    }
    if final_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION:
        assert _decision_request(final_status).decision_type == (
            SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE
        )
    roll_events = [
        cast(dict[str, JsonValue], event.payload)
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "desperate_escape_roll_resolved"
    ]
    assert len(roll_events) == 5
    first_roll = cast(dict[str, JsonValue], roll_events[0]["desperate_escape_roll"])
    first_requirement = cast(dict[str, JsonValue], first_roll["requirement"])
    assert DesperateEscapeRequirementReason.FORCED_BY_RULE.value in cast(
        list[str],
        first_requirement["reasons"],
    )


def test_cavalcade_apocalyptic_steeds_applies_movement_upgrade_through_lifecycle() -> None:
    config = _cavalcade_config(apocalyptic_steeds=True)
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    state = _state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)
    summary = bundle.to_summary_payload()
    army = state.army_definitions[0]
    unit = army.unit_by_id(_CAVALCADE_UNIT_ID)

    assert enhancements.EFFECT_ID in summary["enhancement_effect_binding_ids"]
    assert (
        enhancements.APOCALYPTIC_STEEDS_SOURCE_RULE_ID in summary["selected_execution_record_ids"]
    )
    assert all(
        enhancements.MODIFIER_ID
        in _characteristic_for_model(model, Characteristic.MOVEMENT).applied_modifier_ids
        for model in unit.own_models
    )
    assert {_model_movement_inches(model) for model in unit.own_models} == {7}

    effect_event = _event_payload(lifecycle, "enhancement_effects_applied")
    effect_payloads = cast(list[JsonValue], effect_event["effects"])
    effect_payload = cast(dict[str, JsonValue], effect_payloads[0])
    replay_payload = cast(dict[str, JsonValue], effect_payload["replay_payload"])
    model_payloads = cast(list[JsonValue], effect_payload["model_modifiers"])
    first_model_payload = cast(dict[str, JsonValue], model_payloads[0])
    assert effect_payload["effect_id"] == enhancements.EFFECT_ID
    assert effect_payload["source_id"] == enhancements.APOCALYPTIC_STEEDS_SOURCE_RULE_ID
    assert effect_payload["enhancement_id"] == enhancements.ENHANCEMENT_ID
    assert replay_payload["effect_kind"] == "apocalyptic_steeds_upgrade"
    assert replay_payload["enhancement_source_id"] == enhancements.ENHANCEMENT_SOURCE_ID
    assert first_model_payload["before_final"] == 6
    assert first_model_payload["after_final"] == 7

    selection_request = _decision_request(movement_status)
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-cavalcade-select-apocalyptic-steeds",
            request=selection_request,
            selected_option_id=_CAVALCADE_UNIT_ID,
        )
    )
    action_status = _decline_stratagem_window_if_present(
        lifecycle,
        action_status,
        result_id="phase17g-cavalcade-apocalyptic-decline-warp-riders",
    )
    action_request = _decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    move_status = submit_action_and_movement_proposal(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        action_result_id="phase17g-cavalcade-normal-move-action",
        proposal_result_id="phase17g-cavalcade-normal-move-proposal",
        unit_instance_id=_CAVALCADE_UNIT_ID,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=_CAVALCADE_UNIT_ID,
            dx=7.0,
        ),
    )

    assert move_status.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
    }


def test_cavalcade_apocalyptic_steeds_roster_requires_mounted_target() -> None:
    config = _cavalcade_config(
        apocalyptic_steeds=True,
        friendly_keywords=("Khorne",),
    )

    report = validate_roster_legality(
        catalog=config.army_catalog,
        request=config.army_muster_requests[0],
    )

    assert "enhancement_target_keyword_required" in {
        violation.violation_code for violation in report.violations
    }


def test_cavalcade_soul_shattering_charge_extends_melee_targeting_through_lifecycle() -> None:
    config = _cavalcade_config(soul_shattering_charge=True)
    lifecycle, _movement_status = _advance_to_movement_unit_selection(config)
    state = _state(lifecycle)
    army = state.army_definition_for_player("player-a")
    if army is None:
        raise AssertionError("test state requires player-a army")
    unit = army.unit_by_id(_CAVALCADE_UNIT_ID)
    engaged_model_id = unit.own_models[0].model_instance_id
    extended_model_id = unit.own_models[1].model_instance_id

    _place_soul_shattering_charge_positions(state)
    _record_charge_move_for_unit(state, unit_instance_id=_CAVALCADE_UNIT_ID)
    _advance_lifecycle_state_to_phase(lifecycle, BattlePhase.FIGHT)
    lifecycle = _rehydrate_lifecycle_with_empty_decisions(lifecycle)
    state = _state(lifecycle)
    bundle = _runtime_content_bundle(lifecycle)
    summary = bundle.to_summary_payload()

    assert (
        enhancements.SOUL_SHATTERING_CHARGE_HOOK_ID in summary["fight_activation_ability_hook_ids"]
    )
    assert (
        enhancements.SOUL_SHATTERING_CHARGE_SOURCE_RULE_ID
        in summary["selected_execution_record_ids"]
    )

    activation_request = _decision_request(
        _drain_fight_movement_requests(
            lifecycle,
            lifecycle.advance_until_decision_or_terminal(),
        )
    )
    assert activation_request.decision_type == FIGHT_ACTIVATION_DECISION_TYPE
    ability_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-soul-shattering-activation",
            request=activation_request,
            selected_option_id=fight_activation_option_id(
                unit_instance_id=_CAVALCADE_UNIT_ID,
                fight_type=FightTypeKind.NORMAL,
            ),
        )
    )
    ability_request = _decision_request(ability_status)
    assert ability_request.decision_type == FIGHT_ACTIVATION_ABILITY_DECISION_TYPE
    ability_option_id = f"use:{enhancements.SOUL_SHATTERING_CHARGE_ABILITY_ID}"
    assert ability_option_id in {option.option_id for option in ability_request.options}

    melee_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase17g-soul-shattering-use",
            request=ability_request,
            selected_option_id=ability_option_id,
        )
    )
    melee_request = _decision_request(melee_status)
    assert melee_request.decision_type == SUBMIT_MELEE_DECLARATION_DECISION_TYPE
    proposal_request = MeleeDeclarationProposalRequest.from_decision_request(melee_request)
    engaged_weapon = _required_melee_weapon_for_model(
        proposal_request,
        model_instance_id=engaged_model_id,
    )
    extended_weapon = _required_melee_weapon_for_model(
        proposal_request,
        model_instance_id=extended_model_id,
    )

    assert _ENEMY_UNIT_ID in _engaged_target_ids(engaged_weapon)
    assert _ENEMY_UNIT_ID in _engaged_target_ids(extended_weapon)

    accepted_status = lifecycle.submit_decision(
        ParameterizedSubmission(
            request_id=melee_request.request_id,
            result_id="phase17g-soul-shattering-melee",
            payload=_melee_proposal_payload(
                proposal_request=proposal_request,
                declarations=(
                    _melee_declaration_for_weapon(engaged_weapon),
                    _melee_declaration_for_weapon(extended_weapon),
                ),
            ),
        ).to_result(melee_request)
    )

    assert accepted_status.status_kind in {
        LifecycleStatusKind.ADVANCED,
        LifecycleStatusKind.WAITING_FOR_DECISION,
    }
    used_event = _event_payload(lifecycle, "fight_activation_ability_used")
    ability_use = cast(dict[str, JsonValue], used_event["ability_use"])
    persisting_effect = cast(dict[str, JsonValue], used_event["persisting_effect"])
    effect_payload = cast(dict[str, JsonValue], persisting_effect["effect_payload"])
    assert ability_use["hook_id"] == enhancements.SOUL_SHATTERING_CHARGE_HOOK_ID
    assert ability_use["source_id"] == enhancements.SOUL_SHATTERING_CHARGE_SOURCE_RULE_ID
    assert ability_use["enhancement_id"] == enhancements.SOUL_SHATTERING_CHARGE_ENHANCEMENT_ID
    assert effect_payload["effect_kind"] == "fight_activation_melee_targeting_distance"

    accepted_event = _event_payload(lifecycle, "melee_declaration_accepted")
    accepted_proposal = cast(dict[str, JsonValue], accepted_event["proposal"])
    assert accepted_proposal["unit_instance_id"] == _CAVALCADE_UNIT_ID
    fight_state = state.fight_phase_state
    assert fight_state is not None
    assert fight_state.attack_sequence is not None
    extended_pools = tuple(
        pool
        for pool in fight_state.attack_sequence.attack_pools
        if pool.attacker_model_instance_id == extended_model_id
        and pool.target_unit_instance_id == _ENEMY_UNIT_ID
    )
    assert len(extended_pools) == 1
    assert (
        enhancements.SOUL_SHATTERING_CHARGE_SOURCE_RULE_ID in extended_pools[0].targeting_rule_ids
    )


def test_cavalcade_soul_shattering_charge_roster_requires_mounted_target() -> None:
    config = _cavalcade_config(
        soul_shattering_charge=True,
        friendly_keywords=("Khorne",),
    )

    report = validate_roster_legality(
        catalog=config.army_catalog,
        request=config.army_muster_requests[0],
    )

    assert "enhancement_target_keyword_required" in {
        violation.violation_code for violation in report.violations
    }


def test_cavalcade_enhancement_effect_uses_phase17f_execution_source_id() -> None:
    record = _cavalcade_enhancement_execution_record(enhancements.APOCALYPTIC_STEEDS_SOURCE_RULE_ID)
    contribution = enhancements.runtime_contribution()
    binding = contribution.enhancement_effect_bindings[0]

    assert record.execution_id == enhancements.APOCALYPTIC_STEEDS_SOURCE_RULE_ID
    assert binding.source_id == record.execution_id


def test_cavalcade_soul_shattering_charge_hook_uses_phase17f_execution_source_id() -> None:
    record = _cavalcade_enhancement_execution_record(
        enhancements.SOUL_SHATTERING_CHARGE_SOURCE_RULE_ID
    )
    contribution = enhancements.runtime_contribution()
    binding = contribution.fight_activation_ability_hook_bindings[0]

    assert record.execution_id == enhancements.SOUL_SHATTERING_CHARGE_SOURCE_RULE_ID
    assert binding.source_id == record.execution_id


def test_cavalcade_warp_riders_uses_phase17f_execution_source_id() -> None:
    record = _cavalcade_stratagem_execution_record(stratagems.WARP_RIDERS_SOURCE_RULE_ID)
    contribution = stratagems.runtime_contribution()
    binding = contribution.stratagem_handler_bindings[0]
    catalog_record = contribution.stratagem_records[0]

    assert record.execution_id == stratagems.WARP_RIDERS_SOURCE_RULE_ID
    assert binding.handler_id == stratagems.WARP_RIDERS_HANDLER_ID
    assert catalog_record.definition.source_id == record.execution_id


def test_cavalcade_rule_hook_uses_phase17f_execution_source_id() -> None:
    record = _cavalcade_rule_execution_record()
    contribution = rule.runtime_contribution()
    binding = contribution.fall_back_hook_bindings[0]

    assert record.execution_id == rule.SOURCE_RULE_ID
    assert binding.source_id == record.execution_id


def test_cavalcade_rule_requires_target_unit_owned_by_selected_player() -> None:
    lifecycle, _movement_status = _advance_to_movement_unit_selection(
        _cavalcade_config(
            enemy_faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
            enemy_detachment_id=rule.CAVALCADE_DETACHMENT_ID,
            enemy_datasheet_id=_CAVALCADE_TEST_DATASHEET_ID,
        )
    )
    state = _state(lifecycle)
    context = FallBackEligibilityContext(
        state=state,
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_ENEMY_UNIT_ID,
        movement_request_id="phase17g-cavalcade-enemy-unit-request",
        movement_result_id="phase17g-cavalcade-enemy-unit-result",
    )

    with pytest.raises(GameLifecycleError, match="not in the selected player army"):
        rule.fall_back_eligibility_grant(context)


def test_fall_back_hook_registry_rejects_cavalcade_handler_identity_drift() -> None:
    context = FallBackEligibilityContext(
        state=GameState.from_config(_cavalcade_config()),
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_CAVALCADE_UNIT_ID,
        movement_request_id="phase17g-cavalcade-request",
        movement_result_id="phase17g-cavalcade-result",
    )

    def hook_id_drift(
        _context: FallBackEligibilityContext,
    ) -> FallBackEligibilityGrant:
        return FallBackEligibilityGrant(
            hook_id="phase17g:wrong-hook",
            source_id=rule.SOURCE_RULE_ID,
            can_shoot=True,
            can_declare_charge=True,
        )

    hook_drift_registry = FallBackEligibilityHookRegistry.from_bindings(
        (
            FallBackEligibilityHookBinding(
                hook_id=rule.HOOK_ID,
                source_id=rule.SOURCE_RULE_ID,
                handler=hook_id_drift,
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="hook_id drift"):
        hook_drift_registry.grants_for(context)

    def source_id_drift(
        _context: FallBackEligibilityContext,
    ) -> FallBackEligibilityGrant:
        return FallBackEligibilityGrant(
            hook_id=rule.HOOK_ID,
            source_id="phase17g:wrong-source",
            can_shoot=True,
            can_declare_charge=True,
        )

    source_drift_registry = FallBackEligibilityHookRegistry.from_bindings(
        (
            FallBackEligibilityHookBinding(
                hook_id=rule.HOOK_ID,
                source_id=rule.SOURCE_RULE_ID,
                handler=source_id_drift,
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="source_id drift"):
        source_drift_registry.grants_for(context)


def test_fight_activation_ability_registry_rejects_cavalcade_handler_identity_drift() -> None:
    activation = FightActivationSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=_CAVALCADE_UNIT_ID,
        ordering_band=FightOrderingBandKind.FIGHTS_FIRST,
        fight_type=FightTypeKind.NORMAL,
        eligibility_reasons=(
            FightEligibilityKind.CHARGED_THIS_TURN,
            FightEligibilityKind.CURRENTLY_ENGAGED,
        ),
        request_id="phase17g-soul-shattering-activation-request",
        result_id="phase17g-soul-shattering-activation-result",
    )
    context = FightActivationAbilityContext(
        state=GameState.from_config(_cavalcade_config(soul_shattering_charge=True)),
        game_id="phase17g-soul-shattering-drift",
        battle_round=1,
        active_player_id="player-a",
        player_id="player-a",
        unit_instance_id=_CAVALCADE_UNIT_ID,
        activation=activation,
        target_unit_instance_ids=(_ENEMY_UNIT_ID,),
    )

    def hook_id_drift(
        _context: FightActivationAbilityContext,
    ) -> FightActivationAbilityOption:
        return FightActivationAbilityOption(
            hook_id="phase17g:wrong-hook",
            source_id=enhancements.SOUL_SHATTERING_CHARGE_SOURCE_RULE_ID,
            ability_id=enhancements.SOUL_SHATTERING_CHARGE_ABILITY_ID,
            enhancement_id=enhancements.SOUL_SHATTERING_CHARGE_ENHANCEMENT_ID,
            model_proximity_inches=3.0,
        )

    hook_drift_registry = FightActivationAbilityHookRegistry.from_bindings(
        (
            FightActivationAbilityHookBinding(
                hook_id=enhancements.SOUL_SHATTERING_CHARGE_HOOK_ID,
                source_id=enhancements.SOUL_SHATTERING_CHARGE_SOURCE_RULE_ID,
                handler=hook_id_drift,
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="hook_id drift"):
        hook_drift_registry.options_for(context)

    def source_id_drift(
        _context: FightActivationAbilityContext,
    ) -> FightActivationAbilityOption:
        return FightActivationAbilityOption(
            hook_id=enhancements.SOUL_SHATTERING_CHARGE_HOOK_ID,
            source_id="phase17g:wrong-source",
            ability_id=enhancements.SOUL_SHATTERING_CHARGE_ABILITY_ID,
            enhancement_id=enhancements.SOUL_SHATTERING_CHARGE_ENHANCEMENT_ID,
            model_proximity_inches=3.0,
        )

    source_drift_registry = FightActivationAbilityHookRegistry.from_bindings(
        (
            FightActivationAbilityHookBinding(
                hook_id=enhancements.SOUL_SHATTERING_CHARGE_HOOK_ID,
                source_id=enhancements.SOUL_SHATTERING_CHARGE_SOURCE_RULE_ID,
                handler=source_id_drift,
            ),
        )
    )
    with pytest.raises(GameLifecycleError, match="source_id drift"):
        source_drift_registry.options_for(context)


def _cavalcade_rule_execution_record() -> Phase17FExecutionRecord:
    records = tuple(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.faction_id == rule.CHAOS_DAEMONS_FACTION_ID
        and record.coverage_kind is Phase17ECoverageKind.DETACHMENT_RULE
        and record.detachment_id == rule.CAVALCADE_DETACHMENT_ID
    )
    if len(records) != 1:
        raise AssertionError("expected one Cavalcade of Chaos detachment-rule execution record")
    return records[0]


def _cavalcade_enhancement_execution_record(source_rule_id: str) -> Phase17FExecutionRecord:
    records = tuple(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.faction_id == rule.CHAOS_DAEMONS_FACTION_ID
        and record.coverage_kind is Phase17ECoverageKind.DETACHMENT_ENHANCEMENT
        and record.detachment_id == rule.CAVALCADE_DETACHMENT_ID
        and record.execution_id == source_rule_id
    )
    if len(records) != 1:
        raise AssertionError("expected one Cavalcade of Chaos enhancement execution record")
    return records[0]


def _cavalcade_stratagem_execution_record(source_rule_id: str) -> Phase17FExecutionRecord:
    records = tuple(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.faction_id == rule.CHAOS_DAEMONS_FACTION_ID
        and record.coverage_kind is Phase17ECoverageKind.DETACHMENT_STRATAGEM
        and record.detachment_id == rule.CAVALCADE_DETACHMENT_ID
        and record.execution_id == source_rule_id
    )
    if len(records) != 1:
        raise AssertionError("expected one Cavalcade of Chaos stratagem execution record")
    return records[0]


def _characteristic_for_model(
    model: ModelInstance,
    characteristic: Characteristic,
) -> CharacteristicValue:
    for value in model.characteristics:
        if value.characteristic is characteristic:
            return value
    raise AssertionError(f"model is missing {characteristic.value}")


def _model_movement_inches(model: ModelInstance) -> int:
    value = _characteristic_for_model(model, Characteristic.MOVEMENT)
    return value.final


def _runtime_content_bundle(lifecycle: GameLifecycle) -> RuntimeContentBundle:
    require_runtime_content_bundle = cast(
        Callable[[], RuntimeContentBundle],
        object.__getattribute__(lifecycle, "_require_runtime_content_bundle"),
    )
    return require_runtime_content_bundle()


def _rehydrate_lifecycle_with_empty_decisions(lifecycle: GameLifecycle) -> GameLifecycle:
    payload = lifecycle.to_payload()
    payload["decisions"] = DecisionController().to_payload()
    return GameLifecycle.from_payload(payload)


def _state_at_phase(state: GameState, phase: BattlePhase) -> GameState:
    phase_state = GameState.from_payload(state.to_payload())
    while phase_state.current_battle_phase is not phase:
        if phase_state.current_battle_phase is None:
            raise AssertionError("battle state ended before expected phase")
        phase_state.advance_to_next_battle_phase()
    return phase_state


def _advance_to_movement_unit_selection_with_reserve(
    config: GameConfig,
) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    status = lifecycle.advance_until_decision_or_terminal()
    secondary_index = 1
    while (
        status.decision_request is not None
        and status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    ):
        request = _decision_request(status)
        status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=f"phase17g-reserve-secondary-{secondary_index:06d}",
                request=request,
                selected_option_id="fixed:assassination:bring_it_down",
            )
        )
        secondary_index += 1
    reserve_index = 1
    while (
        status.decision_request is not None
        and status.decision_request.decision_type == SELECT_RESERVE_DECLARATION_DECISION_TYPE
    ):
        request = _decision_request(status)
        declare_option_id = f"declare_strategic_reserves:{_CAVALCADE_RESERVE_UNIT_ID}"
        option_ids = {option.option_id for option in request.options}
        selected_option_id = (
            declare_option_id
            if declare_option_id in option_ids
            else "complete_reserve_declarations"
        )
        status = lifecycle.submit_decision(
            DecisionResult.for_request(
                result_id=f"phase17g-reserve-declaration-{reserve_index:06d}",
                request=request,
                selected_option_id=selected_option_id,
            )
        )
        reserve_index += 1
    movement_status = submit_all_deployments_if_pending(
        lifecycle,
        status,
        result_id_prefix="phase17g-reserve-deploy",
    )
    assert _decision_request(movement_status).decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    return lifecycle, movement_status


def _cavalcade_config(
    *,
    apocalyptic_steeds: bool = False,
    soul_shattering_charge: bool = False,
    friendly_keywords: tuple[str, ...] = (rule.MOUNTED, "Khorne"),
    enemy_faction_id: str = "core-marine-force",
    enemy_detachment_id: str = "core-combined-arms",
    enemy_datasheet_id: str = "core-intercessor-like-infantry",
    turn_order: tuple[str, str] = ("player-a", "player-b"),
    include_reserve_unit: bool = False,
) -> GameConfig:
    catalog = _cavalcade_catalog(friendly_keywords=friendly_keywords)
    return GameConfig(
        game_id="phase17g-cavalcade-unholy-avalanche",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase17g-cavalcade-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_id=rule.CAVALCADE_DETACHMENT_ID,
                unit_selection_id="intercessor-unit-1",
                datasheet_id=_CAVALCADE_TEST_DATASHEET_ID,
                apocalyptic_steeds=apocalyptic_steeds,
                soul_shattering_charge=soul_shattering_charge,
                extra_unit_selection_ids=("reserve-unit",) if include_reserve_unit else (),
            ),
            _army_muster_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                faction_id=enemy_faction_id,
                detachment_id=enemy_detachment_id,
                unit_selection_id="intercessor-unit-2",
                datasheet_id=enemy_datasheet_id,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=turn_order,
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
        reserve_unit_points=(
            (
                ReserveUnitPointValue(
                    unit_instance_id=_CAVALCADE_RESERVE_UNIT_ID,
                    points=100,
                    source_id="phase17g:test:cavalcade-reserve-unit:points",
                ),
            )
            if include_reserve_unit
            else ()
        ),
    )


def _non_cavalcade_daemon_config() -> GameConfig:
    catalog = _catalog_with_other_daemon_detachment(_cavalcade_catalog())
    return GameConfig(
        game_id="phase17g-non-cavalcade-daemon",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase17g-non-cavalcade-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                army_id="army-alpha",
                player_id="player-a",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_id=_OTHER_DAEMON_DETACHMENT_ID,
                unit_selection_id="intercessor-unit-1",
                datasheet_id=_CAVALCADE_TEST_DATASHEET_ID,
            ),
            _army_muster_request(
                catalog=catalog,
                army_id="army-beta",
                player_id="player-b",
                faction_id="core-marine-force",
                detachment_id="core-combined-arms",
                unit_selection_id="intercessor-unit-2",
                datasheet_id="core-intercessor-like-infantry",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _cavalcade_catalog(
    *,
    friendly_keywords: tuple[str, ...] = (rule.MOUNTED, "Khorne"),
) -> ArmyCatalog:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base_datasheet = base_catalog.datasheet_by_id("core-intercessor-like-infantry")
    daemon_datasheet = _cavalcade_datasheet(base_datasheet, keywords=friendly_keywords)
    return replace(
        base_catalog,
        datasheets=(*base_catalog.datasheets, daemon_datasheet),
        factions=(
            *base_catalog.factions,
            FactionDefinition(
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                name="Chaos Daemons",
                faction_keywords=("Legiones Daemonica",),
                source_ids=("gw-11e-faction-detachments-2026-27:faction:chaos-daemons",),
            ),
        ),
        detachments=(
            *base_catalog.detachments,
            DetachmentDefinition(
                detachment_id=rule.CAVALCADE_DETACHMENT_ID,
                name="Cavalcade of Chaos",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(_CAVALCADE_TEST_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force",),
                enhancement_ids=(
                    enhancements.ENHANCEMENT_ID,
                    enhancements.SOUL_SHATTERING_CHARGE_ENHANCEMENT_ID,
                ),
                stratagem_ids=(
                    stratagems.WARP_RIDERS_STRATAGEM_ID,
                    stratagems.FROM_BEYOND_THE_VEIL_STRATAGEM_ID,
                    stratagems.INESCAPABLE_MANIFESTATIONS_STRATAGEM_ID,
                ),
                source_ids=(
                    "gw-11e-faction-detachments-2026-27:detachment:"
                    "chaos-daemons:cavalcade-of-chaos",
                ),
            ),
        ),
        enhancements=(
            *base_catalog.enhancements,
            EnhancementDefinition(
                enhancement_id=enhancements.ENHANCEMENT_ID,
                name="Apocalyptic Steeds Upgrade",
                source_id=enhancements.ENHANCEMENT_SOURCE_ID,
                subtypes=(EnhancementSubtype.UPGRADE,),
                points=0,
                target_required_keywords=(enhancements.MOUNTED,),
                target_required_faction_keywords=(enhancements.LEGIONES_DAEMONICA,),
            ),
            EnhancementDefinition(
                enhancement_id=enhancements.SOUL_SHATTERING_CHARGE_ENHANCEMENT_ID,
                name="Soul-Shattering Charge Upgrade",
                source_id=enhancements.SOUL_SHATTERING_CHARGE_ENHANCEMENT_SOURCE_ID,
                subtypes=(EnhancementSubtype.UPGRADE,),
                points=0,
                target_required_keywords=(enhancements.MOUNTED,),
                target_required_faction_keywords=(enhancements.LEGIONES_DAEMONICA,),
            ),
        ),
        stratagems=(
            *base_catalog.stratagems,
            CatalogStratagemDefinition(
                stratagem_id=stratagems.WARP_RIDERS_STRATAGEM_ID,
                name="Warp-Riders",
                source_id=stratagems.WARP_RIDERS_SOURCE_RULE_ID,
                command_point_cost=1,
                timing_tags=("movement:selected-to-move",),
            ),
            CatalogStratagemDefinition(
                stratagem_id=stratagems.FROM_BEYOND_THE_VEIL_STRATAGEM_ID,
                name="From Beyond the Veil",
                source_id=stratagems.FROM_BEYOND_THE_VEIL_SOURCE_RULE_ID,
                command_point_cost=1,
                timing_tags=("movement:end-phase", "strategic-reserves:ingress"),
            ),
            CatalogStratagemDefinition(
                stratagem_id=stratagems.INESCAPABLE_MANIFESTATIONS_STRATAGEM_ID,
                name="Inescapable Manifestations",
                source_id=stratagems.INESCAPABLE_MANIFESTATIONS_SOURCE_RULE_ID,
                command_point_cost=1,
                timing_tags=("movement:selected-to-fall-back",),
            ),
        ),
    )


def _catalog_with_other_daemon_detachment(catalog: ArmyCatalog) -> ArmyCatalog:
    return replace(
        catalog,
        detachments=(
            *catalog.detachments,
            DetachmentDefinition(
                detachment_id=_OTHER_DAEMON_DETACHMENT_ID,
                name="Other Daemon Detachment",
                faction_id=rule.CHAOS_DAEMONS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(_CAVALCADE_TEST_DATASHEET_ID,),
                force_disposition_ids=("phase17g-force",),
                source_ids=("phase17g:test:other-daemon-detachment",),
            ),
        ),
    )


def _cavalcade_datasheet(
    base_datasheet: DatasheetDefinition,
    *,
    keywords: tuple[str, ...],
) -> DatasheetDefinition:
    return replace(
        base_datasheet,
        datasheet_id=_CAVALCADE_TEST_DATASHEET_ID,
        name="Mounted Manifestation Daemon",
        keywords=DatasheetKeywordSet(
            keywords=keywords,
            faction_keywords=("Legiones Daemonica",),
        ),
        wargear_options=(
            *base_datasheet.wargear_options,
            DatasheetWargearOption(
                option_id=f"{_CAVALCADE_TEST_DATASHEET_ID}:melee-wargear",
                model_profile_id="core-intercessor-like",
                default_wargear_ids=("core-leader-blade",),
                allowed_wargear_ids=("core-leader-blade",),
                min_selections=1,
                max_selections=1,
            ),
        ),
        attachment_eligibilities=(),
        source_ids=("phase17g:test:chaos-daemons:cavalcade-mounted-daemon",),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    army_id: str,
    player_id: str,
    faction_id: str,
    detachment_id: str,
    unit_selection_id: str,
    datasheet_id: str,
    apocalyptic_steeds: bool = False,
    soul_shattering_charge: bool = False,
    extra_unit_selection_ids: tuple[str, ...] = (),
) -> ArmyMusterRequest:
    selected_enhancement_ids = _selected_cavalcade_enhancement_ids(
        faction_id=faction_id,
        detachment_id=detachment_id,
        apocalyptic_steeds=apocalyptic_steeds,
        soul_shattering_charge=soul_shattering_charge,
    )
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(detachment_id,),
            enhancement_ids=selected_enhancement_ids,
        ),
        unit_selections=(
            _unit_muster_selection(
                unit_selection_id=unit_selection_id,
                datasheet_id=datasheet_id,
            ),
            *(
                _unit_muster_selection(
                    unit_selection_id=extra_unit_selection_id,
                    datasheet_id=datasheet_id,
                )
                for extra_unit_selection_id in extra_unit_selection_ids
            ),
        ),
        enhancement_assignments=(
            tuple(
                EnhancementAssignment(
                    enhancement_id=enhancement_id,
                    target_unit_selection_id=unit_selection_id,
                    source_id=f"phase17g:test:{enhancement_id}:assignment",
                )
                for enhancement_id in selected_enhancement_ids
            )
        ),
    )


def _unit_muster_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
    )


def _selected_cavalcade_enhancement_ids(
    *,
    faction_id: str,
    detachment_id: str,
    apocalyptic_steeds: bool,
    soul_shattering_charge: bool,
) -> tuple[str, ...]:
    if not (
        faction_id == rule.CHAOS_DAEMONS_FACTION_ID
        and detachment_id == rule.CAVALCADE_DETACHMENT_ID
    ):
        return ()
    selected: list[str] = []
    if apocalyptic_steeds:
        selected.append(enhancements.ENHANCEMENT_ID)
    if soul_shattering_charge:
        selected.append(enhancements.SOUL_SHATTERING_CHARGE_ENHANCEMENT_ID)
    return tuple(selected)


def _advance_lifecycle_state_to_phase(lifecycle: GameLifecycle, phase: BattlePhase) -> None:
    state = _state(lifecycle)
    while state.current_battle_phase is not phase:
        if state.current_battle_phase is None:
            raise AssertionError("battle state ended before expected phase")
        state.advance_to_next_battle_phase()


def _place_soul_shattering_charge_positions(state: GameState) -> None:
    friendly_placement = _with_model_poses(
        _unit_placement(state, _CAVALCADE_UNIT_ID),
        poses=(
            Pose.at(10.0, 20.0),
            Pose.at(10.0, 21.9),
            Pose.at(10.0, 23.8),
            Pose.at(10.0, 25.7),
            Pose.at(10.0, 27.6),
        ),
    )
    enemy_placement = _with_model_poses(
        _unit_placement(state, _ENEMY_UNIT_ID),
        poses=(
            Pose.at(12.15, 20.0),
            Pose.at(14.05, 20.0),
            Pose.at(15.95, 20.0),
            Pose.at(17.85, 20.0),
            Pose.at(19.75, 20.0),
        ),
    )
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(friendly_placement).with_unit_placement(
            enemy_placement
        )
    )


def _unit_placement(state: GameState, unit_instance_id: str) -> UnitPlacement:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield_state")
    return state.battlefield_state.unit_placement_by_id(unit_instance_id)


def _strategic_reserve_placement(state: GameState, *, unit_instance_id: str) -> UnitPlacement:
    army = state.army_definition_for_player("player-a")
    if army is None:
        raise AssertionError("player-a army is missing")
    unit = army.unit_by_id(unit_instance_id)
    return UnitPlacement(
        army_id=army.army_id,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(3.0, 32.0 + index * 2.0, facing_degrees=0.0),
            )
            for index, model in enumerate(unit.own_models)
        ),
    )


def _submit_placement_proposal(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    result_id: str,
    unit_instance_id: str,
    placement_kind: BattlefieldPlacementKind,
    attempted_placement: UnitPlacement,
) -> LifecycleStatus:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    payload = PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        unit_instance_id=unit_instance_id,
        placement_kind=placement_kind,
        attempted_placement=attempted_placement,
    )
    return lifecycle.submit_decision(
        DecisionResult(
            result_id=result_id,
            request_id=request.request_id,
            decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(payload.to_payload()),
        )
    )


def _with_model_poses(
    unit_placement: UnitPlacement,
    *,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    if len(poses) != len(unit_placement.model_placements):
        raise AssertionError("test pose fixture must match unit model count")
    return UnitPlacement(
        army_id=unit_placement.army_id,
        player_id=unit_placement.player_id,
        unit_instance_id=unit_placement.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=placement.army_id,
                player_id=placement.player_id,
                unit_instance_id=placement.unit_instance_id,
                model_instance_id=placement.model_instance_id,
                pose=pose,
            )
            for placement, pose in zip(unit_placement.model_placements, poses, strict=True)
        ),
    )


def _record_charge_move_for_unit(state: GameState, *, unit_instance_id: str) -> None:
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"phase17g-soul-shattering:{unit_instance_id}:charge-fights-first",
            source_rule_id="core-rules:charge:fights-first",
            owner_player_id="player-a",
            target_unit_instance_ids=(unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhase.CHARGE,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round,
                player_id="player-a",
            ),
            effect_payload={
                "effect_kind": "charge_grants_fights_first",
                "proposal_request_id": "phase17g-soul-shattering-charge-request",
                "decision_result_id": "phase17g-soul-shattering-charge-result",
            },
        )
    )


def _drain_fight_movement_requests(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
) -> LifecycleStatus:
    current = status
    while (
        current.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        and current.decision_request is not None
        and current.decision_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    ):
        request = current.decision_request
        proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
        assert proposal_request.proposal_kind in {
            ProposalKind.PILE_IN,
            ProposalKind.CONSOLIDATE,
        }
        context = cast(dict[str, JsonValue], proposal_request.context)
        current = lifecycle.submit_decision(
            ParameterizedSubmission(
                request_id=request.request_id,
                result_id=f"{request.request_id}:phase17g-no-move",
                payload=cast(
                    JsonValue,
                    {
                        "proposal_request_id": proposal_request.request_id,
                        "proposal_kind": proposal_request.proposal_kind.value,
                        "unit_instance_id": proposal_request.unit_instance_id,
                        "movement_phase_action": proposal_request.movement_phase_action,
                        "movement_mode": context["movement_mode"],
                    },
                ),
            ).to_result(request)
        )
    return current


def _required_melee_weapon_for_model(
    request: MeleeDeclarationProposalRequest,
    *,
    model_instance_id: str,
) -> dict[str, JsonValue]:
    for weapon in request.available_weapons:
        payload = cast(dict[str, JsonValue], weapon)
        if payload["model_instance_id"] != model_instance_id:
            continue
        if payload["is_extra_attacks"] is True:
            continue
        if _ENEMY_UNIT_ID in _engaged_target_ids(payload):
            return payload
    raise AssertionError(f"missing required melee weapon for model {model_instance_id}")


def _engaged_target_ids(weapon_payload: dict[str, JsonValue]) -> tuple[str, ...]:
    return tuple(cast(list[str], weapon_payload["engaged_target_unit_instance_ids"]))


def _melee_declaration_for_weapon(
    weapon_payload: dict[str, JsonValue],
) -> MeleeWeaponDeclaration:
    return MeleeWeaponDeclaration(
        attacker_model_instance_id=cast(str, weapon_payload["model_instance_id"]),
        wargear_id=cast(str, weapon_payload["wargear_id"]),
        weapon_profile_id=cast(str, weapon_payload["weapon_profile_id"]),
        target_allocations=(MeleeTargetAllocation(_ENEMY_UNIT_ID),),
    )


def _melee_proposal_payload(
    *,
    proposal_request: MeleeDeclarationProposalRequest,
    declarations: tuple[MeleeWeaponDeclaration, ...],
) -> JsonValue:
    return cast(
        JsonValue,
        MeleeDeclarationProposal(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=MELEE_DECLARATION_PROPOSAL_KIND,
            player_id=proposal_request.actor_id,
            battle_round=proposal_request.battle_round,
            unit_instance_id=proposal_request.unit_instance_id,
            source_decision_request_id=proposal_request.source_decision_request_id,
            source_decision_result_id=proposal_request.source_decision_result_id,
            declarations=declarations,
        ).to_payload(),
    )


def _event_payload(lifecycle: GameLifecycle, event_type: str) -> dict[str, JsonValue]:
    for event in lifecycle.decision_controller.event_log.records:
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"missing event {event_type}")


def _decline_stratagem_window_if_present(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    *,
    result_id: str,
) -> LifecycleStatus:
    request = _decision_request(status)
    if request.decision_type != STRATAGEM_DECISION_TYPE:
        return status
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        )
    )


def _required_option_id_containing(request: DecisionRequest, expected_fragment: str) -> str:
    option_ids = tuple(option.option_id for option in request.options)
    matches = tuple(option_id for option_id in option_ids if expected_fragment in option_id)
    if len(matches) != 1:
        raise AssertionError(f"expected one option containing {expected_fragment}: {option_ids}")
    return matches[0]


def _grant_cp(state: GameState, *, player_id: str, amount: int) -> None:
    result = state.gain_command_points(
        player_id=player_id,
        amount=amount,
        source_id=f"phase17g-grant:{player_id}:{amount}",
        source_kind=CommandPointSourceKind.COMMAND_PHASE_START,
    )
    assert result.status is CommandPointGainStatus.APPLIED
